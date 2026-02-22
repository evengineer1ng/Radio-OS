#!/usr/bin/env python3
"""
Oracle Kingdom Audio Engine
═══════════════════════════

Consumes AudioMixState from ok_narrator_plugin and maps it to
spatial ambient playback across 9 palace rooms.

Architecture
────────────
  ok_narrator_plugin  ──(audio_mix_update)──►  ok_audio_engine
       │                                            │
  AudioMixPolicy.compute_mix()              RoomAmbientManager
  (deterministic state→mix)                 CrowdTextureManager
                                            ReactionStingerManager
                                            LifecycleAudioManager
                                                    │
                                              pygame.mixer
                                                    │
                                         R Unit speaker / Pucks

Directory layout (stations/OracleKingdom/audio/):
    rooms/<location_id>/      bed_*.ogg, texture_*.ogg
    crowd/murmurs/            murmur_*.ogg
    crowd/whispers/           whisper_*.ogg
    crowd/reactions/          gasp_*, hush_*, audience_*.ogg
    stingers/                 decree_chime.ogg, ...
    lifecycle/                oracle_waking.ogg, ...

Author: Radio OS
"""

import os
import sys
import time
import math
import threading
import queue
import random
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from collections import deque

try:
    import pygame
    import pygame.mixer
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False
    print("[ok_audio] WARNING: pygame not installed. Audio engine disabled.",
          file=sys.stderr)

# ── Plugin metadata ──────────────────────────────────────────
PLUGIN_NAME = "ok_audio_engine"
PLUGIN_DESC = "Spatial ambient audio engine for Oracle Kingdom"
IS_FEED = True

# ── Channel allocation ───────────────────────────────────────
#
# pygame.mixer channels (16 total):
#   0      — room ambient bed (active room)
#   1      — room ambient bed alt (crossfade partner)
#   2      — texture layer A (active room)
#   3      — texture layer B (active room)
#   4      — crowd murmur loop
#   5      — crowd murmur loop (overlap)
#   6      — whisper one-shot
#   7      — reaction one-shot (gasp/hush/shock)
#   8      — stinger one-shot (decree chime, etc.)
#   9      — lifecycle (oracle waking gong, etc.)
#  10..15  — reserved for narrator TTS / puck bleed

CH_BED_A      = 0
CH_BED_B      = 1
CH_TEXTURE_A  = 2
CH_TEXTURE_B  = 3
CH_MURMUR_A   = 4
CH_MURMUR_B   = 5
CH_WHISPER    = 6
CH_REACTION   = 7
CH_STINGER    = 8
CH_LIFECYCLE  = 9

TOTAL_CHANNELS = 16


# ════════════════════════════════════════════════════════════
# ROOM SOUND REGISTRY
# ════════════════════════════════════════════════════════════
#
# Maps each LocationId to its audio assets (relative to audio_dir).
# bed_* files loop continuously. texture_* files fade in/out on
# their own schedules like FTB's AmbientAudioManager.

ROOM_SOUNDS: Dict[str, Dict[str, Any]] = {
    "COURTYARD": {
        "beds": [
            "rooms/courtyard/bed_market.ogg",
            "rooms/courtyard/bed_marketplace.ogg",
        ],
        "textures": [
            {
                "file": "rooms/courtyard/texture_busyarea.ogg",
                "target_vol": 0.35,
                "fade_in":  (3.0, 8.0),
                "fade_out": (4.0, 10.0),
                "silence":  (8.0, 20.0),
            },
            {
                "file": "rooms/courtyard/texture_busyarea2.ogg",
                "target_vol": 0.25,
                "fade_in":  (4.0, 10.0),
                "fade_out": (6.0, 15.0),
                "silence":  (12.0, 30.0),
            },
            {
                "file": "rooms/courtyard/texture_cartwheels.ogg",
                "target_vol": 0.20,
                "fade_in":  (5.0, 12.0),
                "fade_out": (8.0, 18.0),
                "silence":  (15.0, 40.0),
            },
            {
                "file": "rooms/courtyard/texture_market_calls.ogg",
                "target_vol": 0.30,
                "fade_in":  (3.0, 7.0),
                "fade_out": (5.0, 12.0),
                "silence":  (10.0, 25.0),
            },
            {
                "file": "rooms/courtyard/texture_market_chatter.ogg",
                "target_vol": 0.28,
                "fade_in":  (4.0, 9.0),
                "fade_out": (6.0, 14.0),
                "silence":  (12.0, 30.0),
            },
        ],
        "bed_volume": 0.40,
        "character": "bright",  # audio character hint for future DSP
    },
    "WAR_CHAMBER": {
        "beds": [
            "rooms/war_chamber/bed_firecrackle.ogg",
        ],
        "textures": [
            {
                "file": "rooms/war_chamber/texture_stone_room.ogg",
                "target_vol": 0.20,
                "fade_in":  (6.0, 15.0),
                "fade_out": (10.0, 20.0),
                "silence":  (15.0, 40.0),
            },
            {
                "file": "rooms/war_chamber/texture_staircase.ogg",
                "target_vol": 0.15,
                "fade_in":  (5.0, 12.0),
                "fade_out": (8.0, 18.0),
                "silence":  (20.0, 50.0),
            },
        ],
        "bed_volume": 0.30,
        "character": "dry",
    },
    "TEMPLE": {
        "beds": [
            "rooms/temple/bed_cathedral.ogg",
        ],
        "textures": [
            {
                "file": "rooms/temple/texture_echoing_space.ogg",
                "target_vol": 0.25,
                "fade_in":  (8.0, 18.0),
                "fade_out": (12.0, 25.0),
                "silence":  (10.0, 30.0),
            },
            {
                "file": "rooms/temple/texture_brass_chime.ogg",
                "target_vol": 0.18,
                "fade_in":  (4.0, 8.0),
                "fade_out": (6.0, 12.0),
                "silence":  (25.0, 60.0),
            },
        ],
        "bed_volume": 0.35,
        "character": "reverb_wet",
    },
    "HARBOR": {
        "beds": [
            "rooms/harbor/bed_harbor.ogg",
            "rooms/harbor/bed_harbor_alt.ogg",
        ],
        "textures": [
            {
                "file": "rooms/harbor/texture_water.ogg",
                "target_vol": 0.30,
                "fade_in":  (5.0, 12.0),
                "fade_out": (8.0, 18.0),
                "silence":  (8.0, 20.0),
            },
            {
                "file": "rooms/harbor/texture_waterflow.ogg",
                "target_vol": 0.22,
                "fade_in":  (6.0, 14.0),
                "fade_out": (10.0, 22.0),
                "silence":  (12.0, 30.0),
            },
        ],
        "bed_volume": 0.35,
        "character": "bright",
    },
    "LIBRARY": {
        "beds": [
            "rooms/library/bed_quiet.ogg",
        ],
        "textures": [
            {
                "file": "rooms/library/texture_quill.ogg",
                "target_vol": 0.15,
                "fade_in":  (6.0, 15.0),
                "fade_out": (10.0, 20.0),
                "silence":  (15.0, 45.0),
            },
            {
                "file": "rooms/library/texture_parchment.ogg",
                "target_vol": 0.12,
                "fade_in":  (5.0, 12.0),
                "fade_out": (8.0, 18.0),
                "silence":  (20.0, 50.0),
            },
            {
                "file": "rooms/library/texture_rustling.ogg",
                "target_vol": 0.10,
                "fade_in":  (4.0, 10.0),
                "fade_out": (6.0, 15.0),
                "silence":  (25.0, 60.0),
            },
        ],
        "bed_volume": 0.18,   # quietest room
        "character": "intimate",
    },
    "OBSERVATORY": {
        "beds": [
            "rooms/observatory/bed_night_wind.ogg",
            "rooms/observatory/bed_night_wind_alt.ogg",
        ],
        "textures": [
            {
                "file": "rooms/observatory/texture_owls.ogg",
                "target_vol": 0.15,
                "fade_in":  (8.0, 18.0),
                "fade_out": (12.0, 25.0),
                "silence":  (20.0, 60.0),
            },
            {
                "file": "rooms/observatory/texture_telescope.ogg",
                "target_vol": 0.10,
                "fade_in":  (4.0, 10.0),
                "fade_out": (6.0, 12.0),
                "silence":  (30.0, 80.0),
            },
        ],
        "bed_volume": 0.25,
        "character": "vast",
    },
    "TREASURY": {
        "beds": [
            "rooms/treasury/bed_coins.ogg",
        ],
        "textures": [
            {
                "file": "rooms/treasury/texture_counting.ogg",
                "target_vol": 0.18,
                "fade_in":  (4.0, 10.0),
                "fade_out": (6.0, 14.0),
                "silence":  (15.0, 40.0),
            },
        ],
        "bed_volume": 0.25,
        "character": "dry",
    },
    "RAMPARTS": {
        "beds": [
            "rooms/ramparts/bed_wind.ogg",
        ],
        "textures": [
            {
                "file": "rooms/ramparts/texture_watchfire.ogg",
                "target_vol": 0.22,
                "fade_in":  (6.0, 15.0),
                "fade_out": (10.0, 22.0),
                "silence":  (12.0, 35.0),
            },
        ],
        "bed_volume": 0.30,
        "character": "exposed",
    },
    "THRONE_ROOM": {
        "beds": [
            "rooms/throne_room/bed_great_hall.ogg",
        ],
        "textures": [
            {
                "file": "rooms/throne_room/texture_vast_silence.ogg",
                "target_vol": 0.15,
                "fade_in":  (10.0, 20.0),
                "fade_out": (15.0, 30.0),
                "silence":  (10.0, 25.0),
            },
            {
                "file": "rooms/throne_room/texture_robes.ogg",
                "target_vol": 0.10,
                "fade_in":  (4.0, 8.0),
                "fade_out": (6.0, 12.0),
                "silence":  (25.0, 60.0),
            },
        ],
        "bed_volume": 0.22,
        "character": "cavernous",
    },
}

# ── Crowd asset pools ────────────────────────────────────────

CROWD_MURMURS = [
    "crowd/murmurs/murmur_crowd.ogg",
    "crowd/murmurs/murmur_talking.ogg",
    "crowd/murmurs/murmur_chatter.ogg",
]

CROWD_WHISPERS = [
    "crowd/whispers/whisper_long.ogg",
    "crowd/whispers/whisper_short.ogg",
    "crowd/whispers/whisper_conspire.ogg",
]

CROWD_REACTIONS = {
    "gasp": [
        "crowd/reactions/gasp_quick.ogg",
        "crowd/reactions/gasp_sharp.ogg",
        "crowd/reactions/gasp_crowd.ogg",
    ],
    "hush": [
        "crowd/reactions/hush_wave.ogg",
        "crowd/reactions/hush_sharp.ogg",
    ],
    "shock": [
        "crowd/reactions/audience_shock.ogg",
    ],
}

STINGERS = {
    "decree": "stingers/decree_chime.ogg",
}

LIFECYCLE_SOUNDS = {
    "oracle_waking": "lifecycle/oracle_waking.ogg",
}


# ════════════════════════════════════════════════════════════
# TEXTURE FADER — single ambient sound with fade state machine
# ════════════════════════════════════════════════════════════
# Same pattern as FTB AmbientAudioManager, per-sound instance.

@dataclass
class TextureFader:
    """
    Independent fade-in/hold/fade-out state machine for one
    ambient texture loop.  Mirrors FTB's per-sound state model.
    """
    file_rel: str
    target_vol: float
    fade_in_range: Tuple[float, float]
    fade_out_range: Tuple[float, float]
    silence_range: Tuple[float, float]

    # Runtime state
    state: str = "silent"          # silent | fading_in | playing | fading_out
    current_vol: float = 0.0
    state_timer: float = 0.0
    next_duration: float = 0.0
    _sound_obj: Any = None         # pygame.mixer.Sound or None
    _rng_seed: int = 0

    def init_timer(self, seed: int = 0):
        """Stagger start — random initial silence."""
        self._rng_seed = seed
        rng = random.Random(seed)
        self.next_duration = rng.uniform(*self.silence_range)
        self.state_timer = 0.0

    def _rng(self) -> random.Random:
        self._rng_seed += 1
        return random.Random(self._rng_seed)

    def update(self, dt: float, channel: Optional[Any],
               audio_dir: Path, mix_scalar: float, log_fn) -> None:
        """
        Advance state machine.

        mix_scalar (0–1): global multiplier from AudioMixState
            (e.g. crowd_energy for courtyard textures).
        """
        if not HAS_PYGAME or channel is None:
            return

        effective_vol = self.target_vol * max(0.05, mix_scalar)
        self.state_timer += dt

        if self.state == "silent":
            if self.state_timer >= self.next_duration:
                self._start_fade_in(channel, audio_dir, log_fn)

        elif self.state == "fading_in":
            progress = self.state_timer / max(0.01, self.next_duration)
            if progress >= 1.0:
                self.state = "playing"
                self.state_timer = 0.0
                self.next_duration = self._rng().uniform(12.0, 40.0)
                self.current_vol = effective_vol
            else:
                self.current_vol = effective_vol * progress
            channel.set_volume(self.current_vol)

        elif self.state == "playing":
            # Update volume reactively even while playing
            self.current_vol = effective_vol
            channel.set_volume(self.current_vol)
            if self.state_timer >= self.next_duration:
                self._start_fade_out()

        elif self.state == "fading_out":
            progress = self.state_timer / max(0.01, self.next_duration)
            if progress >= 1.0:
                self.state = "silent"
                self.state_timer = 0.0
                self.next_duration = self._rng().uniform(*self.silence_range)
                self.current_vol = 0.0
                channel.stop()
            else:
                self.current_vol = effective_vol * (1.0 - progress)
                channel.set_volume(self.current_vol)

    def _start_fade_in(self, channel, audio_dir: Path, log_fn):
        sound_path = audio_dir / self.file_rel
        if not sound_path.exists():
            log_fn("ok_audio", f"[texture] Missing: {sound_path}")
            # Reset to silence with longer wait
            self.next_duration = self._rng().uniform(*self.silence_range) * 2
            self.state_timer = 0.0
            return
        try:
            self._sound_obj = pygame.mixer.Sound(str(sound_path))
            channel.play(self._sound_obj, loops=-1)
            channel.set_volume(0.0)
            self.state = "fading_in"
            self.state_timer = 0.0
            self.next_duration = self._rng().uniform(*self.fade_in_range)
        except Exception as e:
            log_fn("ok_audio", f"[texture] Play error {self.file_rel}: {e}")

    def _start_fade_out(self):
        self.state = "fading_out"
        self.state_timer = 0.0
        self.next_duration = self._rng().uniform(*self.fade_out_range)

    def stop(self, channel):
        if channel:
            channel.stop()
        self.state = "silent"
        self.current_vol = 0.0
        self.state_timer = 0.0


# ════════════════════════════════════════════════════════════
# ROOM AMBIENT MANAGER
# ════════════════════════════════════════════════════════════

class RoomAmbientManager:
    """
    Manages the ambient bed + texture layers for the active room.
    Handles crossfade when the Oracle transitions between rooms.
    """

    def __init__(self, audio_dir: Path, log_fn):
        self.audio_dir = audio_dir
        self.log = log_fn
        self.active_room: str = ""
        self._bed_sound: Any = None
        self._active_bed_channel: int = CH_BED_A
        self._textures: List[TextureFader] = []
        self._transition_fade_sec: float = 3.0
        self._transition_timer: float = 0.0
        self._transitioning: bool = False
        self._prev_bed_channel: int = CH_BED_B

    def set_room(self, location_id: str) -> None:
        """Switch to a new room.  Crossfades the bed, resets textures."""
        loc = location_id.upper()
        if loc == self.active_room:
            return
        if loc not in ROOM_SOUNDS:
            self.log("ok_audio", f"[room] Unknown location: {loc}")
            return

        self.log("ok_audio", f"[room] Transition: {self.active_room} → {loc}")

        # Start crossfade on beds
        if HAS_PYGAME and pygame.mixer.get_init():
            # Old bed → fade out on partner channel
            old_ch = self._active_bed_channel
            new_ch = CH_BED_B if old_ch == CH_BED_A else CH_BED_A
            self._prev_bed_channel = old_ch
            self._active_bed_channel = new_ch
            self._transitioning = True
            self._transition_timer = 0.0

            # Load new bed
            room_cfg = ROOM_SOUNDS[loc]
            beds = room_cfg["beds"]
            bed_file = self.audio_dir / beds[0]
            if bed_file.exists():
                try:
                    snd = pygame.mixer.Sound(str(bed_file))
                    ch = pygame.mixer.Channel(new_ch)
                    ch.play(snd, loops=-1)
                    ch.set_volume(0.0)
                    self._bed_sound = snd
                except Exception as e:
                    self.log("ok_audio", f"[room] Bed play error: {e}")

        # Stop old textures
        for tex in self._textures:
            ch_idx = CH_TEXTURE_A  # simplified — only 2 texture channels
            if HAS_PYGAME and pygame.mixer.get_init():
                tex.stop(pygame.mixer.Channel(ch_idx))
        self._textures.clear()

        # Build new textures
        if loc in ROOM_SOUNDS:
            room_cfg = ROOM_SOUNDS[loc]
            for i, tex_cfg in enumerate(room_cfg.get("textures", [])):
                fader = TextureFader(
                    file_rel=tex_cfg["file"],
                    target_vol=tex_cfg["target_vol"],
                    fade_in_range=tex_cfg["fade_in"],
                    fade_out_range=tex_cfg["fade_out"],
                    silence_range=tex_cfg["silence"],
                )
                fader.init_timer(seed=hash(loc) + i * 37)
                self._textures.append(fader)

        self.active_room = loc

    def update(self, dt: float, mix: Dict[str, float]) -> None:
        """Tick all room audio layers."""
        if not HAS_PYGAME or not pygame.mixer.get_init():
            return

        # Bed crossfade
        if self._transitioning:
            self._transition_timer += dt
            progress = min(1.0, self._transition_timer / self._transition_fade_sec)
            room_cfg = ROOM_SOUNDS.get(self.active_room, {})
            bed_vol = room_cfg.get("bed_volume", 0.30)

            # New bed fades in
            try:
                pygame.mixer.Channel(self._active_bed_channel).set_volume(
                    bed_vol * progress
                )
            except Exception:
                pass
            # Old bed fades out
            try:
                pygame.mixer.Channel(self._prev_bed_channel).set_volume(
                    bed_vol * (1.0 - progress)
                )
            except Exception:
                pass

            if progress >= 1.0:
                self._transitioning = False
                try:
                    pygame.mixer.Channel(self._prev_bed_channel).stop()
                except Exception:
                    pass

        # Texture layers — round-robin across the 2 texture channels
        # Mix scalar: use crowd_energy as base modulator for textures
        tex_scalar = mix.get("crowd_energy", 0.3) + 0.3   # floor of 0.3
        tex_scalar = min(1.0, tex_scalar)

        for i, fader in enumerate(self._textures):
            ch_idx = CH_TEXTURE_A if (i % 2 == 0) else CH_TEXTURE_B
            try:
                channel = pygame.mixer.Channel(ch_idx)
            except Exception:
                continue
            fader.update(dt, channel, self.audio_dir, tex_scalar, self.log)

    def stop_all(self) -> None:
        if not HAS_PYGAME or not pygame.mixer.get_init():
            return
        for ch in (CH_BED_A, CH_BED_B, CH_TEXTURE_A, CH_TEXTURE_B):
            try:
                pygame.mixer.Channel(ch).stop()
            except Exception:
                pass
        self._textures.clear()


# ════════════════════════════════════════════════════════════
# CROWD TEXTURE MANAGER
# ════════════════════════════════════════════════════════════

class CrowdTextureManager:
    """
    Non-verbal crowd layer: murmur loops + whisper one-shots.
    Driven by AudioMixState.murmur_density and whisper_frequency.
    """

    def __init__(self, audio_dir: Path, log_fn):
        self.audio_dir = audio_dir
        self.log = log_fn
        self._murmur_sounds: List[Any] = []
        self._murmur_idx: int = 0
        self._murmur_timer: float = 0.0
        self._murmur_interval: float = 15.0    # seconds between murmur clip swaps
        self._whisper_timer: float = 0.0
        self._whisper_interval: float = 30.0
        self._loaded: bool = False

    def _ensure_loaded(self):
        if self._loaded or not HAS_PYGAME or not pygame.mixer.get_init():
            return
        for rel in CROWD_MURMURS:
            p = self.audio_dir / rel
            if p.exists():
                try:
                    self._murmur_sounds.append(pygame.mixer.Sound(str(p)))
                except Exception as e:
                    self.log("ok_audio", f"[crowd] Load error {rel}: {e}")
        self._loaded = True

    def update(self, dt: float, mix: Dict[str, float]) -> None:
        if not HAS_PYGAME or not pygame.mixer.get_init():
            return
        self._ensure_loaded()

        density = mix.get("murmur_density", 0.3)
        whisper_freq = mix.get("whisper_frequency", 0.1)

        # ── Murmur loop management ──
        # density controls volume of the murmur channel and swap interval
        # high density → louder murmurs, more frequent swaps
        self._murmur_interval = max(5.0, 25.0 - density * 20.0)
        self._murmur_timer += dt

        murmur_vol = min(0.5, density * 0.6)
        try:
            ch_a = pygame.mixer.Channel(CH_MURMUR_A)
            ch_a.set_volume(murmur_vol)
        except Exception:
            pass

        if self._murmur_timer >= self._murmur_interval and self._murmur_sounds:
            self._murmur_timer = 0.0
            self._murmur_idx = (self._murmur_idx + 1) % len(self._murmur_sounds)
            try:
                ch = pygame.mixer.Channel(CH_MURMUR_A)
                if not ch.get_busy():
                    ch.play(self._murmur_sounds[self._murmur_idx], loops=-1)
                    ch.set_volume(murmur_vol)
            except Exception:
                pass

        # Start initial murmur if nothing playing
        try:
            ch_a = pygame.mixer.Channel(CH_MURMUR_A)
            if not ch_a.get_busy() and self._murmur_sounds:
                ch_a.play(self._murmur_sounds[0], loops=-1)
                ch_a.set_volume(murmur_vol)
        except Exception:
            pass

        # ── Whisper one-shots ──
        # whisper_frequency controls how often a whisper fires
        self._whisper_interval = max(8.0, 40.0 - whisper_freq * 35.0)
        self._whisper_timer += dt

        if self._whisper_timer >= self._whisper_interval:
            self._whisper_timer = 0.0
            self._play_whisper(whisper_freq)

    def _play_whisper(self, freq: float):
        pool = CROWD_WHISPERS
        if not pool:
            return
        rel = pool[int(time.time()) % len(pool)]
        p = self.audio_dir / rel
        if not p.exists():
            return
        try:
            snd = pygame.mixer.Sound(str(p))
            ch = pygame.mixer.Channel(CH_WHISPER)
            vol = min(0.4, freq * 0.5 + 0.05)
            ch.play(snd)
            ch.set_volume(vol)
        except Exception:
            pass

    def stop_all(self):
        if not HAS_PYGAME or not pygame.mixer.get_init():
            return
        for ch_id in (CH_MURMUR_A, CH_MURMUR_B, CH_WHISPER):
            try:
                pygame.mixer.Channel(ch_id).stop()
            except Exception:
                pass


# ════════════════════════════════════════════════════════════
# REACTION STINGER MANAGER
# ════════════════════════════════════════════════════════════

class ReactionManager:
    """
    One-shot crowd reactions (gasps, hushes, shock) and event stingers.
    Triggered by events from the narrator plugin, not by mix state.
    """

    def __init__(self, audio_dir: Path, log_fn):
        self.audio_dir = audio_dir
        self.log = log_fn
        self._cooldowns: Dict[str, float] = {}
        self._min_gap: float = 3.0   # seconds between same category

    def play_reaction(self, category: str, volume: float = 0.5) -> None:
        """
        Play a crowd reaction one-shot.
        category: "gasp", "hush", "shock"
        """
        if not HAS_PYGAME or not pygame.mixer.get_init():
            return
        now = time.time()
        if now - self._cooldowns.get(category, 0) < self._min_gap:
            return

        pool = CROWD_REACTIONS.get(category, [])
        if not pool:
            return
        rel = pool[int(now * 7) % len(pool)]
        p = self.audio_dir / rel
        if not p.exists():
            self.log("ok_audio", f"[reaction] Missing: {p}")
            return
        try:
            snd = pygame.mixer.Sound(str(p))
            ch = pygame.mixer.Channel(CH_REACTION)
            ch.play(snd)
            ch.set_volume(min(0.7, volume))
            self._cooldowns[category] = now
        except Exception as e:
            self.log("ok_audio", f"[reaction] Play error: {e}")

    def play_stinger(self, stinger_id: str, volume: float = 0.6) -> None:
        """Play an event stinger (decree chime, etc.)."""
        if not HAS_PYGAME or not pygame.mixer.get_init():
            return
        rel = STINGERS.get(stinger_id)
        if not rel:
            return
        p = self.audio_dir / rel
        if not p.exists():
            return
        try:
            snd = pygame.mixer.Sound(str(p))
            ch = pygame.mixer.Channel(CH_STINGER)
            ch.play(snd)
            ch.set_volume(min(0.7, volume))
        except Exception as e:
            self.log("ok_audio", f"[stinger] Play error: {e}")

    def play_lifecycle(self, lifecycle_id: str, volume: float = 0.5) -> None:
        """Play a lifecycle sound (oracle waking, etc.)."""
        if not HAS_PYGAME or not pygame.mixer.get_init():
            return
        rel = LIFECYCLE_SOUNDS.get(lifecycle_id)
        if not rel:
            return
        p = self.audio_dir / rel
        if not p.exists():
            return
        try:
            snd = pygame.mixer.Sound(str(p))
            ch = pygame.mixer.Channel(CH_LIFECYCLE)
            ch.play(snd)
            ch.set_volume(min(0.7, volume))
        except Exception as e:
            self.log("ok_audio", f"[lifecycle] Play error: {e}")


# ════════════════════════════════════════════════════════════
# MASTER ENGINE
# ════════════════════════════════════════════════════════════

class OKAudioEngine:
    """
    Master audio engine for Oracle Kingdom.

    Consumes AudioMixState dicts emitted by ok_narrator_plugin
    (via "audio_mix_update" segments on ui_q) and drives all
    audio layers accordingly.

    Follows the same pattern as FTBAudioEngine:
      - Lives in a feed worker thread
      - Reads events from an internal queue
      - Updates managers every tick
    """

    def __init__(self, runtime: Dict[str, Any], config: Dict[str, Any]):
        self.runtime = runtime
        self.config = config
        self.running = False

        station_dir = os.environ.get("STATION_DIR", "")
        self.audio_dir = Path(os.path.join(station_dir, "audio"))

        self.log_fn = runtime.get("log", lambda role, msg: print(f"[{role}] {msg}"))

        # Current mix state (updated each tick from narrator plugin)
        self.current_mix: Dict[str, float] = {
            "murmur_density": 0.3,
            "whisper_frequency": 0.1,
            "silence_depth": 0.5,
            "harmonic_brightness": 0.5,
            "tension_drone": 0.0,
            "crowd_energy": 0.3,
            "sacred_hum": 0.0,
            "threat_rumble": 0.0,
        }

        # Current location
        self.current_location: str = "COURTYARD"

        # Event queue (fed by feed_worker)
        self.event_queue: queue.Queue = queue.Queue()

        # Managers (initialized on start)
        self.room_mgr: Optional[RoomAmbientManager] = None
        self.crowd_mgr: Optional[CrowdTextureManager] = None
        self.reaction_mgr: Optional[ReactionManager] = None

        # Worker thread
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Initialize pygame mixer and all managers."""
        if not HAS_PYGAME:
            self.log_fn("ok_audio", "pygame not available — engine disabled")
            return

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                pygame.mixer.set_num_channels(TOTAL_CHANNELS)
                self.log_fn("ok_audio", f"pygame.mixer initialized ({TOTAL_CHANNELS} channels)")
            else:
                # Ensure enough channels
                if pygame.mixer.get_num_channels() < TOTAL_CHANNELS:
                    pygame.mixer.set_num_channels(TOTAL_CHANNELS)
                self.log_fn("ok_audio", "Using existing pygame.mixer")
        except Exception as e:
            self.log_fn("ok_audio", f"mixer init failed: {e}")
            return

        self.room_mgr = RoomAmbientManager(self.audio_dir, self.log_fn)
        self.crowd_mgr = CrowdTextureManager(self.audio_dir, self.log_fn)
        self.reaction_mgr = ReactionManager(self.audio_dir, self.log_fn)

        # Set initial room
        self.room_mgr.set_room(self.current_location)

        self.running = True
        self._thread = threading.Thread(target=self._worker_loop,
                                        daemon=True, name="ok_audio_worker")
        self._thread.start()
        self.log_fn("ok_audio", "Oracle Kingdom audio engine started")

    def stop(self) -> None:
        self.running = False
        if self.room_mgr:
            self.room_mgr.stop_all()
        if self.crowd_mgr:
            self.crowd_mgr.stop_all()
        self.log_fn("ok_audio", "Oracle Kingdom audio engine stopped")

    def _worker_loop(self):
        """Main audio tick loop — runs at ~20 Hz."""
        tick_interval = 0.05    # 50ms
        last_time = time.time()

        while self.running:
            now = time.time()
            dt = now - last_time
            last_time = now

            # Drain event queue
            while not self.event_queue.empty():
                try:
                    evt = self.event_queue.get_nowait()
                    self._handle_event(evt)
                except queue.Empty:
                    break

            # Update managers
            if self.room_mgr:
                self.room_mgr.update(dt, self.current_mix)
            if self.crowd_mgr:
                self.crowd_mgr.update(dt, self.current_mix)

            time.sleep(tick_interval)

    def _handle_event(self, evt) -> None:
        """Process an audio event (always a dict from push_event)."""
        if not isinstance(evt, dict):
            return
        etype = evt.get("type", "")

        if etype == "audio_mix_update":
            # Update mix state from narrator plugin
            mix_data = evt.get("mix", {})
            if isinstance(mix_data, dict):
                self.current_mix.update(mix_data)

        elif etype == "room_change":
            loc = evt.get("location", "").upper()
            if loc and self.room_mgr:
                self.room_mgr.set_room(loc)
                self.current_location = loc

        elif etype == "reaction":
            cat = evt.get("category", "")
            vol = evt.get("volume", 0.5)
            if self.reaction_mgr:
                self.reaction_mgr.play_reaction(cat, vol)

        elif etype == "stinger":
            sid = evt.get("stinger_id", "")
            vol = evt.get("volume", 0.6)
            if self.reaction_mgr:
                self.reaction_mgr.play_stinger(sid, vol)

        elif etype == "lifecycle":
            lid = evt.get("lifecycle_id", "")
            vol = evt.get("volume", 0.5)
            if self.reaction_mgr:
                self.reaction_mgr.play_lifecycle(lid, vol)

        elif etype == "session_fade":
            # Oracle going dormant — fade everything to silence
            mix_data = evt.get("mix", {})
            if isinstance(mix_data, dict):
                self.current_mix.update(mix_data)

    def push_event(self, evt: Dict[str, Any]) -> None:
        """Thread-safe event push (used by feed_worker bridge)."""
        self.event_queue.put(evt)


# ════════════════════════════════════════════════════════════
# FEED WORKER (Radio OS plugin contract)
# ════════════════════════════════════════════════════════════

_engine_instance: Optional[OKAudioEngine] = None
_engine_lock = threading.Lock()


def _get_engine(runtime: Dict[str, Any], cfg: Dict[str, Any]) -> OKAudioEngine:
    """Singleton engine access."""
    global _engine_instance
    with _engine_lock:
        if _engine_instance is None:
            _engine_instance = OKAudioEngine(runtime, cfg)
            _engine_instance.start()
        return _engine_instance


def feed_worker(stop_event, mem: Dict[str, Any], payload: Dict[str, Any],
                runtime: Dict[str, Any] = None) -> None:
    """
    Radio OS feed_worker entry point.

    Runs in its own thread. Listens for audio_mix_update events
    on ui_q and forwards them to the engine.

    Args:
        stop_event: threading.Event — set when station is shutting down
        mem:        persistent memory dict
        payload:    feed config dict (poll_sec, feed_name, …)
        runtime:    runtime stub dict (event_q, ui_q, log, …)
    """
    runtime = runtime or {}
    cfg = payload or {}
    log = runtime.get("log", lambda role, msg: print(f"[{role}] {msg}"))
    log("ok_audio", "feed_worker starting")

    engine = _get_engine(runtime, cfg)

    # The feed worker's job is to bridge events from the runtime
    # queues into the audio engine's internal queue.
    event_q = runtime.get("event_q")
    ui_q = runtime.get("ui_q")

    poll_interval = cfg.get("poll_sec", 0.1)

    while not stop_event.is_set():
        stop_event.wait(poll_interval)

        # Check ui_q for audio_mix_update segments from narrator plugin
        if ui_q is not None:
            try:
                while not ui_q.empty():
                    item = ui_q.get_nowait()
                    if isinstance(item, dict):
                        meta = item.get("metadata", {})
                        if isinstance(meta, dict):
                            mtype = meta.get("type", "")
                            if mtype in ("audio_mix_update", "audio_mix_state",
                                         "session_fade"):
                                engine.push_event({
                                    "type": mtype,
                                    "mix": meta.get("mix", {}),
                                })
                            elif mtype == "room_change":
                                engine.push_event({
                                    "type": "room_change",
                                    "location": meta.get("location", ""),
                                })
            except Exception:
                pass

        # Check event_q for game events that trigger reactions/stingers
        if event_q is not None:
            try:
                while not event_q.empty():
                    item = event_q.get_nowait()
                    if isinstance(item, dict):
                        _route_game_event(item, engine)
                    elif hasattr(item, 'type') and hasattr(item, 'payload'):
                        # StationEvent dataclass — convert to dict for routing
                        evt_dict = {
                            "type": getattr(item, "type", ""),
                            "event_type": getattr(item, "type", ""),
                            "source": getattr(item, "source", ""),
                        }
                        evt_dict.update(getattr(item, "payload", {}) or {})
                        _route_game_event(evt_dict, engine)
            except Exception:
                pass


def _route_game_event(evt: Dict[str, Any], engine: OKAudioEngine) -> None:
    """
    Map simulation events to audio reactions/stingers.

    Event types from oracle_kingdom.py SimEvent and oracle_court.py:
      decree_issued → decree chime + hush
      famine_*      → gasp
      schism_*      → shock
      military_*    → gasp
      lifecycle_*   → lifecycle sounds
    """
    etype = evt.get("event_type", "") or evt.get("type", "")
    etype_lower = etype.lower()

    # Decree announced
    if "decree" in etype_lower:
        engine.push_event({"type": "stinger", "stinger_id": "decree", "volume": 0.6})
        engine.push_event({"type": "reaction", "category": "hush", "volume": 0.5})

    # Famine / shortage
    elif "famine" in etype_lower or "shortage" in etype_lower:
        engine.push_event({"type": "reaction", "category": "gasp", "volume": 0.5})

    # Schism / religious fracture
    elif "schism" in etype_lower or "fracture" in etype_lower:
        engine.push_event({"type": "reaction", "category": "shock", "volume": 0.6})

    # Military event
    elif "military" in etype_lower or "defiance" in etype_lower:
        engine.push_event({"type": "reaction", "category": "gasp", "volume": 0.45})

    # Oracle lifecycle
    elif "oracle_waking" in etype_lower or "lifecycle_waking" in etype_lower:
        engine.push_event({"type": "lifecycle", "lifecycle_id": "oracle_waking",
                           "volume": 0.5})

    # Room change
    elif "presence_change" in etype_lower or "room_change" in etype_lower:
        loc = evt.get("location", "") or evt.get("location_id", "")
        if loc:
            engine.push_event({"type": "room_change", "location": loc})


# ════════════════════════════════════════════════════════════
# WIDGET REGISTRATION (optional — for shell UI controls)
# ════════════════════════════════════════════════════════════

def register_widgets(registry: Dict, runtime_stub: Dict[str, Any]) -> None:
    """Register audio control widgets with the shell."""
    # Placeholder — can add volume sliders, room selectors, etc.
    pass


# ── Default feed config (read by shell.discover_plugins) ─────

FEED_DEFAULTS = {
    "enabled": True,
    "poll_sec": 0.1,
}

DEFAULT_FEED_CFG = FEED_DEFAULTS
