#!/usr/bin/env python3
"""
FromTheBackmarker Audio Engine
Four-channel audio system: world, music, narrator, ui

Implements:
- Modal drift music system (performance-based theme variants)
- World audio (engines, crashes, ambient motorsport)
- Narrator-music ducking integration
- UI tactile feedback

Author: Radio OS
"""

import os
import sys
import time
import threading
import queue
import random
import sqlite3
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

try:
    import pygame
    import pygame.mixer
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False
    print("[ftb_audio_engine] WARNING: pygame not installed. Audio engine disabled.", file=sys.stderr)

# Plugin metadata
PLUGIN_NAME = "ftb_audio_engine"
PLUGIN_DESC = "Multi-channel audio engine for FromTheBackmarker"
IS_FEED = True  # Feed plugin - runs audio engine worker

# =======================
# Audio Event Types
# =======================

@dataclass
class AudioEvent:
    """Audio event for file-based playback"""
    audio_type: str  # 'world', 'music', 'ui', 'narrator_duck'
    file_path: Optional[str] = None
    volume: float = 1.0
    fade_in: float = 0.0
    fade_out: float = 0.0
    loop: bool = False
    priority: int = 50
    metadata: Dict[str, Any] = field(default_factory=dict)


# =======================
# Performance Scalar Calculator
# =======================

class PerformanceScalarCalculator:
    """
    Calculates -1.0 to +1.0 performance scalar from game state.
    Drives modal drift music system.
    """
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        Args:
            weights: Dict of metric weights (morale, reputation, legitimacy, position, budget)
        """
        self.weights = weights or {
            'morale': 0.25,
            'reputation': 0.20,
            'legitimacy': 0.15,
            'position': 0.25,
            'budget': 0.15
        }
        self.smoothed_scalar = 0.0
        self.smoothing_alpha = 0.15  # Exponential moving average for inertia
        
    def normalize_metric(self, value: float, min_val: float, max_val: float, invert: bool = False) -> float:
        """Normalize metric to [-1, 1] range"""
        if max_val == min_val:
            return 0.0
        normalized = (value - min_val) / (max_val - min_val)  # [0, 1]
        normalized = normalized * 2.0 - 1.0  # [-1, 1]
        if invert:
            normalized = -normalized
        return max(-1.0, min(1.0, normalized))
    
    def calculate(self, state_data: Dict[str, Any]) -> float:
        """
        Calculate performance scalar from game state.
        
        Args:
            state_data: Dict with keys: morale, reputation, legitimacy, position, budget, etc.
        
        Returns:
            Smoothed scalar in [-1.0, 1.0]
        """
        # Extract metrics with defaults
        morale = state_data.get('morale', 0.5)
        reputation = state_data.get('reputation', 0.5)
        legitimacy = state_data.get('legitimacy', 0.5)
        position = state_data.get('position', 10)  # Championship position
        max_position = state_data.get('max_position', 20)  # Total teams
        budget = state_data.get('budget', 0)
        budget_baseline = state_data.get('budget_baseline', 1000000)
        
        # Normalize each metric to [-1, 1]
        norm_morale = self.normalize_metric(morale, 0.0, 1.0)
        norm_reputation = self.normalize_metric(reputation, 0.0, 1.0)
        norm_legitimacy = self.normalize_metric(legitimacy, 0.0, 1.0)
        
        # Position: lower is better, so invert
        norm_position = self.normalize_metric(position, 1, max_position, invert=True)
        
        # Budget: compare to baseline
        if budget_baseline > 0:
            budget_ratio = budget / budget_baseline
            norm_budget = self.normalize_metric(budget_ratio, 0.5, 2.0)  # ±50% to ±200% of baseline
        else:
            norm_budget = 0.0
        
        # Weighted sum
        raw_scalar = (
            self.weights['morale'] * norm_morale +
            self.weights['reputation'] * norm_reputation +
            self.weights['legitimacy'] * norm_legitimacy +
            self.weights['position'] * norm_position +
            self.weights['budget'] * norm_budget
        )
        
        # Apply smoothing (morale inertia)
        self.smoothed_scalar = (
            self.smoothing_alpha * raw_scalar +
            (1.0 - self.smoothing_alpha) * self.smoothed_scalar
        )
        
        return max(-1.0, min(1.0, self.smoothed_scalar))


# =======================
# State Music Controller
# =======================

class StateMusicController:
    """
    Modal drift music system.
    Manages theme variants (minor/neutral/major) with crossfade.
    """
    
    def __init__(self, audio_dir: str, runtime: Dict[str, Any], config: Dict[str, Any]):
        self.audio_dir = Path(audio_dir)
        self.runtime = runtime
        self.config = config
        
        # Theme variants
        self.variants = {
            'minor': str(self.audio_dir / 'music' / 'theme_minor.ogg'),
            'neutral': str(self.audio_dir / 'music' / 'theme_neutral.ogg'),
            'major': str(self.audio_dir / 'music' / 'theme_major.ogg')
        }
        
        # State
        self.current_variant = 'neutral'
        self.target_variant = 'neutral'
        self.crossfade_progress = 1.0  # 1.0 = fully at current, 0.0 = mid-crossfade
        self.crossfade_duration = config.get('crossfade_duration', 6.0)
        self.is_ducking = False
        self.duck_volume = 0.02  # Very faint during speech
        self.normal_volume = config.get('channel_volumes', {}).get('music', 0.08)  # Very low background volume
        self.pbp_muted = False  # True when PBP mode has muted music entirely
        
        # Pygame channels
        self.music_channel = None
        self.crossfade_channel = None
        
    def select_variant(self, scalar: float) -> str:
        """Select theme variant based on performance scalar"""
        if scalar < -0.4:
            return 'minor'
        elif scalar > 0.4:
            return 'major'
        else:
            return 'neutral'
    
    def update(self, performance_scalar: float, dt: float) -> None:
        """
        Update music state based on performance.
        
        Args:
            performance_scalar: Current performance [-1, 1]
            dt: Delta time in seconds
        """
        # Determine target variant
        new_target = self.select_variant(performance_scalar)
        
        # Start crossfade if target changed
        if new_target != self.target_variant and self.crossfade_progress >= 1.0:
            self.target_variant = new_target
            self.crossfade_progress = 0.0
            self._start_crossfade()
        
        # Update crossfade progress
        if self.crossfade_progress < 1.0:
            self.crossfade_progress += dt / self.crossfade_duration
            if self.crossfade_progress >= 1.0:
                self.crossfade_progress = 1.0
                self._complete_crossfade()
    
    def _start_crossfade(self) -> None:
        """Begin crossfade to target variant"""
        if not HAS_PYGAME or not pygame.mixer.get_init():
            return
        
        target_file = self.variants.get(self.target_variant)
        if not target_file or not os.path.exists(target_file):
            self.runtime.get('log', print)(f"[ftb_audio_engine] Music file not found: {target_file}")
            self.crossfade_progress = 1.0
            return
        
        try:
            # Load and play target on crossfade channel
            sound = pygame.mixer.Sound(target_file)
            if self.crossfade_channel is None:
                self.crossfade_channel = pygame.mixer.Channel(1)
            self.crossfade_channel.play(sound, loops=-1)
            self.crossfade_channel.set_volume(0.0)
        except Exception as e:
            self.runtime.get('log', print)(f"[ftb_audio_engine] Crossfade start error: {e}")
    
    def _complete_crossfade(self) -> None:
        """Complete crossfade, swap channels"""
        if not HAS_PYGAME or not pygame.mixer.get_init():
            return
        
        # Swap channels
        if self.music_channel:
            self.music_channel.stop()
        self.music_channel = self.crossfade_channel
        self.crossfade_channel = None
        self.current_variant = self.target_variant
        
        # Set correct volume (ducking or normal)
        target_volume = self.duck_volume if self.is_ducking else self.normal_volume
        if self.music_channel:
            self.music_channel.set_volume(target_volume)
    
    def start(self) -> None:
        """Start playing initial theme"""
        if not HAS_PYGAME or not pygame.mixer.get_init():
            return
        
        initial_file = self.variants.get(self.current_variant)
        if not initial_file or not os.path.exists(initial_file):
            self.runtime.get('log', print)(f"[ftb_audio_engine] Initial music file not found: {initial_file}")
            return
        
        try:
            sound = pygame.mixer.Sound(initial_file)
            if self.music_channel is None:
                self.music_channel = pygame.mixer.Channel(0)
            self.music_channel.play(sound, loops=-1)
            self.music_channel.set_volume(self.normal_volume)
        except Exception as e:
            self.runtime.get('log', print)(f"[ftb_audio_engine] Music start error: {e}")
    
    def set_ducking(self, ducking: bool, duration: float = 1.5) -> None:
        """Duck music for narrator (gradually reduce volume)"""
        self.is_ducking = ducking
        target_volume = self.duck_volume if ducking else self.normal_volume
        
        # PBP mute overrides ducking
        if self.pbp_muted:
            return
        
        if self.music_channel:
            self.music_channel.set_volume(target_volume)
    
    def set_pbp_mute(self, muted: bool) -> None:
        """
        Mute / unmute music for PBP mode.
        Uses a smooth fade via a background thread.
        When muted, volume → 0.  When unmuted, restore to normal/duck level.
        """
        self.pbp_muted = muted
        target = 0.0 if muted else (self.duck_volume if self.is_ducking else self.normal_volume)
        
        if self.music_channel:
            # Threaded fade over ~2 seconds (40 steps × 50ms)
            def _fade():
                ch = self.music_channel
                if not ch:
                    return
                start_vol = ch.get_volume()
                steps = 40
                for i in range(1, steps + 1):
                    vol = start_vol + (target - start_vol) * (i / steps)
                    try:
                        ch.set_volume(max(0.0, vol))
                    except Exception:
                        break
                    time.sleep(0.05)
            threading.Thread(target=_fade, daemon=True, name="MusicFade").start()
    
    def stop(self) -> None:
        """Stop music playback"""
        if self.music_channel:
            self.music_channel.stop()
        if self.crossfade_channel:
            self.crossfade_channel.stop()


# =======================
# Ambient Audio Manager
# =======================

class AmbientAudioManager:
    """
    Manages looping ambient sounds that fade in/out independently:
    - garage.ogg, toolbox.ogg (mechanical ambient)
    - distantchatter.ogg, distantpa.ogg (crowd/PA ambient)
    Each sound loops and fades on its own schedule for layered atmosphere.
    """
    
    def __init__(self, audio_dir: str, runtime: Dict[str, Any], config: Dict[str, Any]):
        self.audio_dir = Path(audio_dir)
        self.runtime = runtime
        self.config = config
        
        self.base_volume = config.get('channel_volumes', {}).get('ambient', 0.15)
        
        # Ambient sound definitions
        self.ambient_sounds = {
            'garage': {
                'file': 'world/ambient/garage.ogg',
                'channel': None,
                'fade_in_duration': (3.0, 8.0),  # Random range
                'fade_out_duration': (5.0, 12.0),
                'silence_duration': (10.0, 30.0),
                'target_volume': 0.3,
                'current_volume': 0.0,
                'state': 'silent',  # silent, fading_in, playing, fading_out
                'state_timer': 0.0,
                'next_duration': 0.0
            },
            'toolbox': {
                'file': 'world/ambient/toolbox.ogg',
                'channel': None,
                'fade_in_duration': (4.0, 10.0),
                'fade_out_duration': (6.0, 15.0),
                'silence_duration': (15.0, 45.0),
                'target_volume': 0.25,
                'current_volume': 0.0,
                'state': 'silent',
                'state_timer': 0.0,
                'next_duration': 0.0
            },
            'distantchatter': {
                'file': 'world/ambient/distantchatter.ogg',
                'channel': None,
                'fade_in_duration': (5.0, 12.0),
                'fade_out_duration': (8.0, 20.0),
                'silence_duration': (5.0, 20.0),
                'target_volume': 0.4,
                'current_volume': 0.0,
                'state': 'silent',
                'state_timer': 0.0,
                'next_duration': 0.0
            },
            'distantpa': {
                'file': 'world/ambient/distantpa.ogg',
                'channel': None,
                'fade_in_duration': (6.0, 15.0),
                'fade_out_duration': (10.0, 25.0),
                'silence_duration': (20.0, 60.0),
                'target_volume': 0.2,
                'current_volume': 0.0,
                'state': 'silent',
                'state_timer': 0.0,
                'next_duration': 0.0
            }
        }
        
        self.channel_offset = 10  # Start at channel 10
        self._assign_channels()
        self._init_timers()
    
    def _assign_channels(self):
        """Assign pygame channels to each ambient sound"""
        if not HAS_PYGAME or not pygame.mixer.get_init():
            return
        
        for idx, sound_name in enumerate(self.ambient_sounds.keys()):
            self.ambient_sounds[sound_name]['channel'] = pygame.mixer.Channel(self.channel_offset + idx)
    
    def _init_timers(self):
        """Initialize random timers for staggered starts"""
        for sound_name, sound_data in self.ambient_sounds.items():
            # Start with random silence before first fade-in
            sound_data['next_duration'] = random.uniform(*sound_data['silence_duration'])
            sound_data['state_timer'] = 0.0
    
    def update(self, dt: float):
        """Update all ambient sounds (fade in/out logic)"""
        if not HAS_PYGAME or not pygame.mixer.get_init():
            return
        
        for sound_name, sound_data in self.ambient_sounds.items():
            sound_data['state_timer'] += dt
            
            if sound_data['state'] == 'silent':
                if sound_data['state_timer'] >= sound_data['next_duration']:
                    self._start_fade_in(sound_name)
            
            elif sound_data['state'] == 'fading_in':
                progress = sound_data['state_timer'] / sound_data['next_duration']
                if progress >= 1.0:
                    sound_data['state'] = 'playing'
                    sound_data['state_timer'] = 0.0
                    sound_data['next_duration'] = random.uniform(15.0, 45.0)  # Play duration
                    sound_data['current_volume'] = sound_data['target_volume']
                else:
                    sound_data['current_volume'] = sound_data['target_volume'] * progress
                
                if sound_data['channel']:
                    sound_data['channel'].set_volume(sound_data['current_volume'] * self.base_volume)
            
            elif sound_data['state'] == 'playing':
                if sound_data['state_timer'] >= sound_data['next_duration']:
                    self._start_fade_out(sound_name)
            
            elif sound_data['state'] == 'fading_out':
                progress = sound_data['state_timer'] / sound_data['next_duration']
                if progress >= 1.0:
                    sound_data['state'] = 'silent'
                    sound_data['state_timer'] = 0.0
                    sound_data['next_duration'] = random.uniform(*sound_data['silence_duration'])
                    sound_data['current_volume'] = 0.0
                    if sound_data['channel']:
                        sound_data['channel'].stop()
                else:
                    sound_data['current_volume'] = sound_data['target_volume'] * (1.0 - progress)
                
                if sound_data['channel']:
                    sound_data['channel'].set_volume(sound_data['current_volume'] * self.base_volume)
    
    def _start_fade_in(self, sound_name: str):
        """Begin fade-in for an ambient sound"""
        sound_data = self.ambient_sounds[sound_name]
        sound_file = self.audio_dir / sound_data['file']
        
        if not sound_file.exists():
            self.runtime.get('log', print)(f"[ambient] File not found: {sound_file}")
            return
        
        try:
            sound = pygame.mixer.Sound(str(sound_file))
            channel = sound_data['channel']
            if channel:
                channel.play(sound, loops=-1)
                channel.set_volume(0.0)
                sound_data['state'] = 'fading_in'
                sound_data['state_timer'] = 0.0
                sound_data['next_duration'] = random.uniform(*sound_data['fade_in_duration'])
        except Exception as e:
            self.runtime.get('log', print)(f"[ambient] Error playing {sound_name}: {e}")
    
    def _start_fade_out(self, sound_name: str):
        """Begin fade-out for an ambient sound"""
        sound_data = self.ambient_sounds[sound_name]
        sound_data['state'] = 'fading_out'
        sound_data['state_timer'] = 0.0
        sound_data['next_duration'] = random.uniform(*sound_data['fade_out_duration'])
    
    def stop_all(self):
        """Stop all ambient sounds"""
        for sound_data in self.ambient_sounds.values():
            if sound_data['channel']:
                sound_data['channel'].stop()
            sound_data['state'] = 'silent'
            sound_data['current_volume'] = 0.0


# =======================
# World Audio Controller
# =======================

class WorldAudioController:
    """
    Manages race audio: engines, crashes, crowd reactions, ambient motorsport texture.
    """
    
    def __init__(self, audio_dir: str, runtime: Dict[str, Any], config: Dict[str, Any]):
        self.audio_dir = Path(audio_dir)
        self.runtime = runtime
        self.config = config
        
        # Channels
        self.engine_channel = None
        self.crash_channel = None
        self.crowd_channel = None
        
        # State
        self.current_engine_league = None
        self.current_engine_sound = None  # Keep reference to loaded sound
        self.engine_loop_start_pos = 20.0  # Start loops at 20 seconds in
        self.engine_first_play = True
        self.silence_until = 0  # Timestamp for post-crash silence
        
        self.volume = config.get('channel_volumes', {}).get('world', 0.5)
        
        # Ambient manager
        self.ambient_manager = AmbientAudioManager(audio_dir, runtime, config)
    
    def play_engine_loop(self, league_tier: str) -> None:
        """
        Play engine audio loop for current league tier.
        These are full onboard lap recordings that should loop continuously
        as ambient background audio throughout the race.
        
        Args:
            league_tier: 'grassroots', 'midformula', 'formulaz'
        """
        if not HAS_PYGAME or not pygame.mixer.get_init():
            return
        
        if self.current_engine_league == league_tier:
            return  # Already playing correct engine
        
        engine_dir = self.audio_dir / 'world' / 'engines' / league_tier
        if not engine_dir.exists():
            return
        
        # Pick random variant (OGG preferred, then WAV)
        engine_files = list(engine_dir.glob('*.ogg'))
        if not engine_files:
            engine_files = list(engine_dir.glob('*.wav'))
        if not engine_files:
            return
        
        engine_file = random.choice(engine_files)
        
        try:
            sound = pygame.mixer.Sound(str(engine_file))
            if self.engine_channel is None:
                self.engine_channel = pygame.mixer.Channel(2)
            
            # Loop indefinitely - pygame will handle seamless looping
            # Note: For loop point at 20s, would need pygame.mixer.music or custom implementation
            # For now, loop from beginning which works for most onboard audio
            self.engine_channel.play(sound, loops=-1)
            self.engine_channel.set_volume(self.volume * 0.3)  # Engines at 30% - ambient background
            self.current_engine_league = league_tier
            
            self.runtime.get('log', print)(f"[ftb_audio_engine] Engine audio started: {league_tier}")
        except Exception as e:
            self.runtime.get('log', print)(f"[ftb_audio_engine] Engine audio error: {e}")
    
    def play_crash(self, severity: float) -> None:
        """
        Play crash audio based on severity.
        
        Args:
            severity: 0.0-1.0, determines crash intensity
        """
        if not HAS_PYGAME or not pygame.mixer.get_init():
            return
        
        # Determine crash type
        if severity > 0.7:
            crash_type = 'hard'
            silence_duration = 2.0
        elif severity > 0.3:
            crash_type = 'medium'
            silence_duration = 0.5
        else:
            crash_type = 'light'
            silence_duration = 0.0
        
        crash_dir = self.audio_dir / 'world' / 'crashes'
        
        # Try .ogg first, then .wav
        crash_files = list(crash_dir.glob(f'{crash_type}*.ogg'))
        if not crash_files:
            crash_files = list(crash_dir.glob(f'{crash_type}*.wav'))
        
        if not crash_files:
            return
        
        crash_file = random.choice(crash_files)
        
        try:
            sound = pygame.mixer.Sound(str(crash_file))
            if self.crash_channel is None:
                self.crash_channel = pygame.mixer.Channel(3)
            self.crash_channel.play(sound)
            self.crash_channel.set_volume(self.volume * 0.6)  # Crashes at 60%
            
            # Post-crash silence (fade out engines briefly)
            if silence_duration > 0:
                self.silence_until = time.time() + silence_duration
                if self.engine_channel:
                    self.engine_channel.set_volume(0.0)
        except Exception as e:
            self.runtime.get('log', print)(f"[ftb_audio_engine] Crash audio error: {e}")
    
    def play_crowd_reaction(self, reaction_type: str = 'cheer') -> None:
        """
        Play crowd reaction sound.
        
        Args:
            reaction_type: 'cheer', 'chatter', 'whoop' for different crowd reactions
        """
        if not HAS_PYGAME or not pygame.mixer.get_init():
            return
        
        crowd_dir = self.audio_dir / 'world' / 'ambient'
        
        # Map reaction types to files
        sound_map = {
            'cheer': 'crowdcheer_oneshot.ogg',
            'chatter': 'crowdchatter_oneshot.ogg',
            'whoop': 'crowdwhoop.ogg'
        }
        
        sound_file = crowd_dir / sound_map.get(reaction_type, 'crowdcheer_oneshot.ogg')
        
        if not sound_file.exists():
            return
        
        try:
            sound = pygame.mixer.Sound(str(sound_file))
            if self.crowd_channel is None:
                self.crowd_channel = pygame.mixer.Channel(4)
            self.crowd_channel.play(sound)
            self.crowd_channel.set_volume(self.volume * 0.5)
        except Exception as e:
            self.runtime.get('log', print)(f"[ftb_audio_engine] Crowd audio error: {e}")
    
    def update(self, dt: float = 0.05) -> None:
        """
        Update world audio state.
        
        Args:
            dt: Delta time in seconds
        """
        # Check for end of post-crash silence
        if self.silence_until > 0 and time.time() >= self.silence_until:
            self.silence_until = 0
            if self.engine_channel:
                self.engine_channel.set_volume(self.volume * 0.4)
        
        # Update ambient sounds
        self.ambient_manager.update(dt)
    
    def stop_engine(self) -> None:
        """Stop engine loop (race ended)"""
        if self.engine_channel:
            self.engine_channel.stop()
        self.current_engine_league = None
        
        # Stop ambient sounds too
        self.ambient_manager.stop_all()


# =======================
# UI Audio Controller
# =======================

class UIAudioController:
    """
    Tactile UI feedback sounds.
    Dry, mechanical, non-musical.
    """
    
    def __init__(self, audio_dir: str, runtime: Dict[str, Any], config: Dict[str, Any]):
        self.audio_dir = Path(audio_dir)
        self.runtime = runtime
        self.config = config
        
        self.enabled = config.get('ui_audio_enabled', True)
        self.volume = config.get('channel_volumes', {}).get('ui', 0.15)
        
        # Preload UI sounds
        self.sounds = {}
        self._load_sounds()
    
    def _load_sounds(self) -> None:
        """Preload UI sound files"""
        if not HAS_PYGAME or not pygame.mixer.get_init():
            return
        
        ui_dir = self.audio_dir / 'ui'
        if not ui_dir.exists():
            return
        
        sound_types = ['click', 'confirm', 'error', 'toggle', 'alert']
        for stype in sound_types:
            sound_file = ui_dir / f'{stype}.wav'
            if sound_file.exists():
                try:
                    self.sounds[stype] = pygame.mixer.Sound(str(sound_file))
                except Exception as e:
                    self.runtime.get('log', print)(f"[ftb_audio_engine] Failed to load {stype}: {e}")
    
    def play(self, sound_type: str) -> None:
        """
        Play UI sound.
        
        Args:
            sound_type: 'click', 'confirm', 'error', 'toggle', 'alert'
        """
        if not self.enabled or not HAS_PYGAME:
            return
        
        sound = self.sounds.get(sound_type)
        if sound:
            sound.set_volume(self.volume)
            sound.play()


# =======================
# Narrator-Music Bridge
# =======================

class NarratorMusicBridge:
    """
    Coordinates narrator voice with music ducking.
    """
    
    def __init__(self, music_controller: StateMusicController):
        self.music_controller = music_controller
        self.is_narrator_active = False
        self.duck_start_time = 0
        self.restore_delay = 1.5  # Seconds after narration ends
    
    def narrator_started(self) -> None:
        """Called when narrator begins speaking"""
        if not self.is_narrator_active:
            self.music_controller.set_ducking(True)
            self.is_narrator_active = True
            self.duck_start_time = time.time()
    
    def narrator_ended(self) -> None:
        """Called when narrator finishes speaking"""
        if self.is_narrator_active:
            self.is_narrator_active = False
            # Schedule restore (would need timer in main loop)
            # For now, restore immediately with delay handled by music controller
            threading.Timer(self.restore_delay, self._restore_music).start()
    
    def _restore_music(self) -> None:
        """Restore music volume after narration"""
        if not self.is_narrator_active:
            self.music_controller.set_ducking(False)


# =======================
# Main Audio Engine
# =======================

class FTBAudioEngine:
    """
    Master audio engine coordinating all channels.
    """
    
    def __init__(self, runtime: Dict[str, Any], config: Dict[str, Any]):
        self.runtime = runtime
        self.config = config
        self.running = False
        
        # Audio directory
        station_dir = os.environ.get('STATION_DIR', '')
        self.audio_dir = os.path.join(station_dir, 'audio')
        
        # Initialize pygame mixer (only if not already initialized)
        if HAS_PYGAME:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                    pygame.mixer.set_num_channels(16)  # Reserve more channels for ambient sounds
                    log_fn = self.runtime.get('log', lambda role, msg: print(f"[{role}] {msg}"))
                    log_fn("ftb_audio", "pygame.mixer initialized with 16 channels")
                else:
                    log_fn = self.runtime.get('log', lambda role, msg: print(f"[{role}] {msg}"))
                    log_fn("ftb_audio", "Using existing pygame.mixer")
            except Exception as e:
                print(f"[ftb_audio_engine] pygame.mixer init failed: {e}", file=sys.stderr)
        
        # Controllers
        self.performance_calc = PerformanceScalarCalculator(
            weights=config.get('performance_weights', {})
        )
        self.music_controller = StateMusicController(self.audio_dir, runtime, config)
        self.world_controller = WorldAudioController(self.audio_dir, runtime, config)
        self.ui_controller = UIAudioController(self.audio_dir, runtime, config)
        self.narrator_bridge = NarratorMusicBridge(self.music_controller)
        
        # State
        self.current_scalar = 0.0
        self.last_update = time.time()
        
        # Event queue
        self.audio_event_queue = queue.Queue()
        
        # Thread
        self.worker_thread = None
    
    def start(self) -> None:
        """Start audio engine"""
        if not HAS_PYGAME:
            self.runtime.get('log', print)("[ftb_audio_engine] Pygame not available, engine disabled")
            return
        
        self.running = True
        self.music_controller.start()
        
        # Start worker thread
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="AudioEngine")
        self.worker_thread.start()
        
        self.runtime.get('log', print)("[ftb_audio_engine] Audio engine started")
    
    def stop(self) -> None:
        """Stop audio engine"""
        self.running = False
        self.music_controller.stop()
        self.world_controller.stop_engine()
        if self.worker_thread:
            self.worker_thread.join(timeout=2.0)
    
    def _worker_loop(self) -> None:
        """Main audio engine loop"""
        while self.running:
            try:
                # Process audio events
                self._process_events()
                
                # Update music based on performance
                now = time.time()
                dt = now - self.last_update
                self.last_update = now
                
                self.music_controller.update(self.current_scalar, dt)
                self.world_controller.update(dt)
                
                time.sleep(0.05)  # 20 Hz update rate
            except Exception as e:
                self.runtime.get('log', print)(f"[ftb_audio_engine] Worker error: {e}")
                time.sleep(1.0)
    
    def _process_events(self) -> None:
        """Process pending audio events"""
        while not self.audio_event_queue.empty():
            try:
                event = self.audio_event_queue.get_nowait()
                self._handle_audio_event(event)
            except queue.Empty:
                break
            except Exception as e:
                self.runtime.get('log', print)(f"[ftb_audio_engine] Event processing error: {e}")
    
    def _handle_audio_event(self, event: AudioEvent) -> None:
        """Handle a single audio event"""
        if event.audio_type == 'narrator_duck':
            # Narrator started/ended
            if event.metadata.get('started'):
                self.narrator_bridge.narrator_started()
            else:
                self.narrator_bridge.narrator_ended()
        
        elif event.audio_type == 'pbp_mode':
            # Play-by-play mode: fade music to 0 or restore
            active = event.metadata.get('active', False)
            self.music_controller.set_pbp_mute(active)
            log_fn = self.runtime.get('log', lambda r, m: print(f"[{r}] {m}"))
            log_fn("ftb_audio", f"PBP mode {'ACTIVE – music fading to 0' if active else 'ENDED – music restoring'}")
        
        elif event.audio_type == 'world':
            # World audio (crash, engine change, crowd reactions)
            action = event.metadata.get('action')
            if action == 'crash':
                severity = event.metadata.get('severity', 0.5)
                self.world_controller.play_crash(severity)
            elif action == 'engine_start':
                league_tier = event.metadata.get('league_tier', 'midformula')
                self.world_controller.play_engine_loop(league_tier)
            elif action == 'engine_stop':
                self.world_controller.stop_engine()
            elif action == 'crowd_reaction':
                reaction_type = event.metadata.get('reaction_type', 'cheer')
                self.world_controller.play_crowd_reaction(reaction_type)
        
        elif event.audio_type == 'ui':
            # UI feedback
            sound_type = event.metadata.get('sound_type', 'click')
            self.ui_controller.play(sound_type)
        
        elif event.audio_type == 'performance_update':
            # Update performance scalar
            state_data = event.metadata.get('state_data', {})
            self.current_scalar = self.performance_calc.calculate(state_data)
    
    def emit_audio_event(self, event: AudioEvent) -> None:
        """Queue an audio event for processing"""
        self.audio_event_queue.put(event)


# =======================
# Global Engine Instance
# =======================

_audio_engine: Optional[FTBAudioEngine] = None


def set_pbp_mode(active: bool) -> None:
    """
    Public helper – call from game controller to fade music in/out for PBP.
    Bypasses event_q so it cannot be swallowed by another consumer.
    """
    if _audio_engine:
        _audio_engine.music_controller.set_pbp_mute(active)
        log_fn = _audio_engine.runtime.get('log', lambda r, m: print(f"[{r}] {m}"))
        log_fn("ftb_audio", f"set_pbp_mode({active}) – music {'fading to 0' if active else 'restoring'}")
    else:
        print(f"[ftb_audio_engine] set_pbp_mode({active}) called but engine not initialized")


def start_engine_audio(league_tier: str = 'midformula') -> None:
    """
    Public helper – start engine loop for the given league tier.
    Bypasses event_q so it cannot be swallowed by another consumer.
    """
    if _audio_engine:
        _audio_engine.world_controller.play_engine_loop(league_tier)
        log_fn = _audio_engine.runtime.get('log', lambda r, m: print(f"[{r}] {m}"))
        log_fn("ftb_audio", f"start_engine_audio('{league_tier}') – engine loop started")
    else:
        print(f"[ftb_audio_engine] start_engine_audio('{league_tier}') called but engine not initialized")


def stop_engine_audio() -> None:
    """
    Public helper – stop engine loop.
    Bypasses event_q so it cannot be swallowed by another consumer.
    """
    if _audio_engine:
        _audio_engine.world_controller.stop_engine()
        log_fn = _audio_engine.runtime.get('log', lambda r, m: print(f"[{r}] {m}"))
        log_fn("ftb_audio", "stop_engine_audio() – engine loop stopped")
    else:
        print(f"[ftb_audio_engine] stop_engine_audio() called but engine not initialized")


def feed_worker(stop_event, mem: Dict[str, Any], payload: Dict[str, Any], runtime: Dict[str, Any]) -> None:
    """
    Audio engine worker (runs as background thread manager).
    Subscribes to event_q and routes audio events.
    """
    global _audio_engine
    
    log = runtime.get('log', print)
    event_q = runtime.get('event_q')
    ui_cmd_q = runtime.get('ui_cmd_q')
    
    if not HAS_PYGAME:
        log("[ftb_audio_engine] pygame not available, skipping audio engine")
        return
    
    # Get audio config from runtime manifest
    manifest = runtime.get('manifest', {})
    audio_config = manifest.get('audio', {})
    
    # Initialize engine
    _audio_engine = FTBAudioEngine(runtime, audio_config)
    _audio_engine.start()
    
    log("[ftb_audio_engine] Feed worker started, listening for events")
    
    # Use stop_event for graceful shutdown
    try:
        while not stop_event.is_set():
            # Check for station events
            try:
                station_event = event_q.get(timeout=0.5)
                
                # Route relevant events to audio engine
                if station_event.type == 'audio':
                    # Direct audio event
                    audio_evt = AudioEvent(
                        audio_type=station_event.payload.get('audio_type', 'world'),
                        file_path=station_event.payload.get('file_path'),
                        volume=station_event.payload.get('volume', 1.0),
                        metadata=station_event.payload
                    )
                    _audio_engine.emit_audio_event(audio_evt)
                
                elif station_event.source == 'ftb' and station_event.type == 'narrator_segment':
                    # Narrator started speaking
                    _audio_engine.emit_audio_event(AudioEvent(
                        audio_type='narrator_duck',
                        metadata={'started': True}
                    ))
                
                elif station_event.source == 'ftb' and station_event.type == 'state_update':
                    # Performance state update
                    _audio_engine.emit_audio_event(AudioEvent(
                        audio_type='performance_update',
                        metadata={'state_data': station_event.payload}
                    ))
                
            except queue.Empty:
                continue
            except Exception as e:
                log(f"[ftb_audio_engine] Event routing error: {e}")
    
    finally:
        if _audio_engine:
            _audio_engine.stop()
        log("[ftb_audio_engine] Feed worker stopped")


def register_widgets(registry: Any, runtime_stub: Dict[str, Any]) -> None:
    """Register audio control widgets"""
    # TODO: Implement audio mixer widget panel
    pass


if __name__ == '__main__':
    print("ftb_audio_engine: Not meant to be run directly")
