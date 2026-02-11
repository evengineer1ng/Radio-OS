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
        
        if self.music_channel:
            # Pygame doesn't have smooth volume ramp, so do instant change
            # (could implement manual ramp with thread if needed)
            self.music_channel.set_volume(target_volume)
    
    def stop(self) -> None:
        """Stop music playback"""
        if self.music_channel:
            self.music_channel.stop()
        if self.crossfade_channel:
            self.crossfade_channel.stop()


# =======================
# World Audio Controller
# =======================

class WorldAudioController:
    """
    Manages race audio: engines, crashes, ambient motorsport texture.
    """
    
    def __init__(self, audio_dir: str, runtime: Dict[str, Any], config: Dict[str, Any]):
        self.audio_dir = Path(audio_dir)
        self.runtime = runtime
        self.config = config
        
        # Channels
        self.engine_channel = None
        self.crash_channel = None
        self.ambient_channel = None
        
        # State
        self.current_engine_league = None
        self.silence_until = 0  # Timestamp for post-crash silence
        
        self.volume = config.get('channel_volumes', {}).get('world', 0.5)
    
    def play_engine_loop(self, league_tier: str) -> None:
        """
        Play engine audio loop for current league tier.
        
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
        
        # Pick random variant
        engine_files = list(engine_dir.glob('*.ogg')) + list(engine_dir.glob('*.wav'))
        if not engine_files:
            return
        
        engine_file = random.choice(engine_files)
        
        try:
            sound = pygame.mixer.Sound(str(engine_file))
            if self.engine_channel is None:
                self.engine_channel = pygame.mixer.Channel(2)
            self.engine_channel.play(sound, loops=-1)
            self.engine_channel.set_volume(self.volume * 0.4)  # Engines at 40% of world volume
            self.current_engine_league = league_tier
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
        crash_file = crash_dir / f'{crash_type}.wav'
        
        if not crash_file.exists():
            # Try finding any crash file
            crash_files = list(crash_dir.glob(f'{crash_type}*.wav'))
            if crash_files:
                crash_file = random.choice(crash_files)
            else:
                return
        
        try:
            sound = pygame.mixer.Sound(str(crash_file))
            if self.crash_channel is None:
                self.crash_channel = pygame.mixer.Channel(3)
            self.crash_channel.play(sound)
            self.crash_channel.set_volume(self.volume * 0.6)  # Crashes at 60%
            
            # Post-crash silence
            if silence_duration > 0:
                self.silence_until = time.time() + silence_duration
                if self.engine_channel:
                    self.engine_channel.set_volume(0.0)
        except Exception as e:
            self.runtime.get('log', print)(f"[ftb_audio_engine] Crash audio error: {e}")
    
    def update(self) -> None:
        """Check for end of post-crash silence"""
        if self.silence_until > 0 and time.time() >= self.silence_until:
            self.silence_until = 0
            if self.engine_channel:
                self.engine_channel.set_volume(self.volume * 0.4)
    
    def stop_engine(self) -> None:
        """Stop engine loop (race ended)"""
        if self.engine_channel:
            self.engine_channel.stop()
        self.current_engine_league = None


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
                    pygame.mixer.set_num_channels(8)  # Reserve channels for different types
                    log_fn = self.runtime.get('log', lambda role, msg: print(f"[{role}] {msg}"))
                    log_fn("ftb_audio", "pygame.mixer initialized")
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
                self.world_controller.update()
                
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
        
        elif event.audio_type == 'world':
            # World audio (crash, engine change)
            action = event.metadata.get('action')
            if action == 'crash':
                severity = event.metadata.get('severity', 0.5)
                self.world_controller.play_crash(severity)
            elif action == 'engine_start':
                league_tier = event.metadata.get('league_tier', 'midformula')
                self.world_controller.play_engine_loop(league_tier)
            elif action == 'engine_stop':
                self.world_controller.stop_engine()
        
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


def feed_worker(runtime: Dict[str, Any]) -> None:
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
    
    # Note: Feed workers in the modern runtime run in managed threads
    # and don't need explicit stop_event checking as they're daemon threads
    try:
        while True:
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
