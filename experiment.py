#!/usr/bin/env python3
from __future__ import annotations
"""
Radio OS Station Runtime Engine
Content-agnostic AI radio loop with modular feeds, event routing, audio, and UI.
"""

# =======================
# Voice Path Resolution
# =======================
def resolve_voice_path(p: str) -> str:
    """
    Resolve a voice model path, honoring station dir, RADIO_OS_ROOT/voices, and GLOBAL_VOICES_DIR.
    """
    p = (p or "").strip()
    if not p:
        return ""
    if os.path.isabs(p) and os.path.exists(p):
        return p
    # Try station dir
    cand = os.path.join(STATION_DIR, p)
    if os.path.exists(cand):
        return cand
    # Try RADIO_OS_ROOT/voices
    if RADIO_OS_ROOT:
        voices_dir = os.path.join(RADIO_OS_ROOT, "voices")
        cand = os.path.join(voices_dir, p)
        if os.path.exists(cand):
            return cand
    # Try GLOBAL_VOICES_DIR
    if GLOBAL_VOICES_DIR:
        cand = os.path.join(GLOBAL_VOICES_DIR, p)
        if os.path.exists(cand):
            return cand
    # Fallback to plain relative
    return p

import os, time, json, re, tempfile, subprocess, queue, sqlite3, random, hashlib
from typing import Any, Dict, List, Optional, Tuple
import importlib.util
import glob
import json
import time
import os
from time import sleep
import sys
import platform

# Platform detection
IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

# Allow plugins to do: from your_runtime import event_q, StationEvent, log, now_ts, sha1, ui_q, producer_kick
sys.modules.setdefault("your_runtime", sys.modules[__name__])
import inspect

import requests
import sounddevice as sd
import soundfile as sf
import numpy as np
import tkinter as tk
from tkinter import ttk, colorchooser, filedialog, messagebox
import threading
import asyncio
import yaml

# Character Context Engine
try:
    from context_engine import query_context_engine, format_context_for_prompt
    HAS_CONTEXT_ENGINE = True
except ImportError:
    HAS_CONTEXT_ENGINE = False

# Optional PIL for advanced image/gradient support
try:
    from PIL import Image as PILImage, ImageDraw as PILDraw, ImageTk as PILImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from dataclasses import dataclass, field
from collections import deque
import math

status_lock = threading.Lock()


# =======================
# Manifest & Environment
# =======================
# =======================
# Safe Host Defaults
# =======================

STATION_DIR = os.environ.get("STATION_DIR", ".")
DB_PATH = os.environ.get("STATION_DB_PATH", "station.sqlite")
MEMORY_PATH = os.environ.get("STATION_MEMORY_PATH", "station_memory.json")

RADIO_OS_ROOT = os.environ.get("RADIO_OS_ROOT", "")
GLOBAL_VOICES_DIR = os.environ.get("RADIO_OS_VOICES", "")
GLOBAL_PLUGINS_DIR = os.environ.get("RADIO_OS_PLUGINS", "")

CONTEXT_MODEL = os.environ.get("CONTEXT_MODEL", "")
HOST_MODEL = os.environ.get("HOST_MODEL", "")

# =======================
# Live Feed Config Reloader
# =======================
import threading
_FEED_CONFIGS = {}
_FEED_CONFIG_LOCK = threading.Lock()
def _start_feed_config_reloader(feeds_dict, poll_sec=2.0):
    """Background thread to reload manifest and update feed configs live."""
    import time
    def _reload_loop():
        last_manifest = None
        import yaml
        while True:
            try:
                path = os.path.join(STATION_DIR, "manifest.yaml")
                with open(path, "r", encoding="utf-8") as f:
                    manifest = f.read()
                if manifest != last_manifest:
                    last_manifest = manifest
                    cfg = yaml.safe_load(manifest) or {}
                    feeds = (cfg.get("feeds") or {})
                    with _FEED_CONFIG_LOCK:
                        for k, v in feeds.items():
                            if k in feeds_dict:
                                # Update the config dict in-place only
                                feeds_dict[k].clear()
                                feeds_dict[k].update(v)
                                print(f"[RELOADER DEBUG] feed '{k}' config id={id(feeds_dict[k])} enabled={feeds_dict[k].get('enabled')} contents={feeds_dict[k]}")
                time.sleep(poll_sec)
            except Exception as e:
                print(f"[RELOADER DEBUG] Exception: {e}")
                time.sleep(poll_sec)
    t = threading.Thread(target=_reload_loop, daemon=True)
    t.start()

# =======================
# 📝 PROMPT REGISTRY
# =======================

DEFAULT_PROMPTS = {
        # -------------------
        # Visual Reader Prompts
        # -------------------
        "visual_throwaway_comment": "Let's watch this video together. {comment}",
        "visual_realtime_reaction": "Material: {material}\n\nReact in real time to what you see in the video. Speak ONE natural concise sentence.",
        "visual_summarize_reaction": "Material: {material}\n\nThe video has ended. Summarize your reaction as if you just finished watching. Speak naturally, as if talking to a friend on air.",
        # -------------------
        # Curator (Procedural Discovery)
        # -------------------
        "producer_system_context": """You are the CURATOR for {show_name}.

You do NOT script or host. You discover what belongs in the station's world state.

Goal: emit procedural "discoveries" that are on-topic, fresh, and usable by the Navigator.

Discovery types:
- frontier: brand‑new angle or concept
- echo: builds on an existing theme
- resolution: closes an open loop

Rules:
- short, crisp angles
- no filler or generic advice
- tags are reusable, snake_case, 1–4 words

Output STRICT JSON only:

{{
    "discoveries": [
        {{
            "post_id": "...",
            "type": "frontier|echo|resolution",
            "title": "...",
            "angle": "...",
            "why": "...",
            "key_points": ["..."],
            "tags": ["..."],
            "priority": 0-100,
            "depth": "quick|deep",
            "host_hint": "..."
        }}
    ]
}}

Current themes:
{themes}

Open loops:
{callbacks}

Live nudges:
{live_nudges}""",

        "producer_candidates_prompt": """Choose discoveries for the world state:

{candidates_list}""",

        "navigator_system": """You are the NAVIGATOR for {show_name}.

You select the next procedural move and which discovery to explore.

Moves:
- explore
- contrast
- deepen
- resolve
- reframe
- tease

Output STRICT JSON only:

{{
    "queue": [
        {{
            "target_id": "post_id",
            "move": "explore|contrast|deepen|resolve|reframe|tease",
            "focus": "tag_or_concept",
            "energy": "low|medium|high",
            "open_loop": "question to carry forward",
            "lead_voice": "optional character name"
        }}
    ]
}}""",

        "navigator_user": """WORLD STATE:
{world_state}

DISCOVERIES:
{discoveries}

Choose the next moves.""",

    # -------------------
    # Flow (Continuity Layer)
    # -------------------
    "flow_intro_prompt": "We are transitioning into a track. Song: {track} by {artist}. {system_context}. Keep it under 2 sentences. Cool, smooth, professional.",
    
    "flow_reaction_prompt": "We are listening to {track} by {artist}. {system_context}. One short sentence reaction. Vibe check only.",
    
    "flow_outro_prompt": "Song {track} by {artist} is ending. {system_context}. Smoothly bridge to the next segment or talk break. Under 2 sentences.",

    "producer_bridge": """Write a very short (1 sentence) radio bridge throwing back to the music. Energy: high. Context: talk break ending.""",

    "producer_bridge_system": """You are a radio host. Return ONE sentence only.""",

    # -------------------
    # Host (Generic)
    # -------------------
    "host_system": """You are the live host of {show_name}.

Tone: natural, smart, calm.
Spoken words only.
No announcements of actions.
No stock phrases.
No disclaimers.

Continuity:
Themes: {themes}
Callbacks: {callbacks}""",

    # -------------------
    # Cold Open
    # -------------------
    "cold_open_system": """You are the live host of an ongoing audio program.

Your task is to generate a natural cold open — the first spoken moment of a show.

Principles:
- Sound like a human host thinking out loud, not reading a script
- Do not greet the audience or reference the show starting
- Flow naturally into the subject matter
- Connect ideas rather than listing them
- Favor insight, curiosity, or tension over summary

Constraints:
- 2 to 4 sentences only
- Designed for spoken audio
- No formatting, no bullet points
- Subtly reflect the provided mood, focus, tags, and themes
- Avoid clichés and filler phrases

Return STRICT JSON in this format:

{{
  "host_intro": "...",
  "panel": [],
  "host_takeaway": "..."
}}""",

    "cold_open_user": """Mood: {mood}
Focus: {focus}

{station_context}

Recent tags: {hot_tags}
Active themes: {themes}

Create a cold open that naturally reflects this context.
Use the Station name and implied identity from the sources to ground the show's voice.""",

    # -------------------
    # Host Packet (Manifest)
    # -------------------
        "host_packet_system": """You are the LEAD VOICE for {show_name}.
    Lead voice identity: {lead_voice}

You interpret a procedural move and discovery into spoken audio.
You are not required to identify as a host or radio personality.

Panel voices available:
{roster}

Rules:
- Spoken words only
- Natural flow, no bullet points
- No stage directions
- Do not invent facts not supported by the material
- Keep it on-topic and agentic

Output STRICT JSON only:

{{
    "lead_line": "...",
    "followup_line": "...",
    "supporting_lines": [
        {{ "voice": "{allowed_p_str}", "line": "..." }}
    ],
    "takeaway": "...",
    "callback": "optional"
}}

Themes: {themes}
Open loops: {callbacks}""",

        "host_packet_user": """LEAD VOICE: {lead_voice}

MOVE: {move}
FOCUS: {focus}
ENERGY: {energy}
OPEN LOOP: {open_loop}

DISCOVERY:
TITLE: {title}
ANGLE: {angle}
WHY: {why}
KEY POINTS: {key_points}
TAGS: {tags}

MATERIAL:
{material}

COMMENTS:
{comments}""",

        "host_packet_repair_user": """We already have this packet JSON (keep lead_line/followup_line/takeaway the same):
{existing_json}

This segment material:
TITLE: {title}
ANGLE: {angle}
WHY: {why}
KEY POINTS: {key_points}
MATERIAL: {material}

Task:
Return STRICT JSON only.
Keep existing fields unchanged.
ONLY modify "supporting_lines" by adding entries until it has at least {min_n} items.
Use distinct voices. Each line must be ONE concise sentence.""",

    # -------------------
    # Feature: Music Breaks
    # -------------------
    "music_pre": """You are on air. A music break is about to happen.
Write ONE sentence that tees up a track emotionally without sounding scripted.
Track: {track}
No greetings, no announcements.""",

    "music_post": """You are back on air after a music break.
Write ONE sentence that bridges from the vibe of the track back into discussion.
Track: {track}
No greetings, no announcements.""",

    # -------------------
    # Feature: Voice Reaction
    # -------------------
    "voice_reaction_user": """Material:
{material}

Intent: {intent}
Focus: {focus}
Context: {context}
Tone: {tone}

{live_block}

Speak ONE natural concise sentence adding your unique angle.""",

    # -------------------
    # Feature: Visuals
    # -------------------
    "visual_prompt_system": """You create visual direction for a live radio show overlay.

Return ONE concise image prompt.
Focus on mood, metaphor, atmosphere.
Avoid logos, text overlays, and branding.""",

    "visual_prompt_user": """Title: {title}
Angle: {angle}
Material: {body}

{live_block}

Return ONE visual prompt.""",

    # -------------------
    # Feature: Evergreen Riff
    # -------------------
    "evergreen_riff_user": """You have a short gap on air.

Talk naturally for about {duration} seconds.

Reflect on recent themes or connect ideas.

Themes:
{themes}

Callbacks:
{callbacks}

No filler. Conversational tone.""",

    "host_riff_system": """You are a radio host filling a short gap naturally.""",
}


def get_prompt(mem: Dict[str, Any], key: str, **kwargs) -> str:
    # 1. Try manifest first (configuration source of truth)
    cust = CFG.get("prompts", {})
    if not isinstance(cust, dict):
        cust = {}
    raw = cust.get(key)
    
    # 2. Try custom prompts in memory (legacy/runtime overrides)
    if not raw:
        cust_mem = mem.get("custom_prompts", {})
        if isinstance(cust_mem, dict):
            raw = cust_mem.get(key)
    
    # 3. Fallback to default
    if not raw:
        raw = DEFAULT_PROMPTS.get(key, "")

    # 4. Format
    try:
        return raw.format(**kwargs)
    except Exception as e:
        # If formatting fails (missing keys), return raw or a safe error
        return f"[PROMPT FORMAT ERROR: {e}] {raw}"

# ====================================================
# 🎵 MUSIC BREAKS GLOBAL STATE
# ====================================================

MUSIC_STATE: dict = {
    "playing": False,
    "title": "",
    "artist": "",
    "album": "",
    "source_app": "",
    "position_sec": None,
    "duration_sec": None,
    "remaining_sec": None,
    "track_sig": "",
    "ts": 0,
    # user toggles (driven by widget)
    "allow_background_music": False,
    "duck_level": 0.25,      # 0.0..1.0
    "fade_sec": 1.25,
}
def music_allow_bg() -> bool:
    try:
        return bool(MUSIC_STATE.get("allow_background_music", False))
    except Exception:
        return False

def music_duck_level() -> float:
    try:
        x = float(MUSIC_STATE.get("duck_level", 0.25))
        return max(0.0, min(1.0, x))
    except Exception:
        return 0.25

def music_fade_sec() -> float:
    try:
        x = float(MUSIC_STATE.get("fade_sec", 1.25))
        return max(0.05, min(8.0, x))
    except Exception:
        return 1.25


def wait_until_track_end(stop_event: threading.Event, poll_sec: float = 0.25, settle_sec: float = 0.8) -> None:
    """
    Blocks until Windows media stops playing OR remaining_sec hits ~0.
    settle_sec avoids false-end glitches on session switches.
    """
    last_playing = False
    settled = 0.0

    while not stop_event.is_set():

        if SHOW_INTERRUPT.is_set():
            return

        st = MUSIC_STATE or {}
        playing = bool(st.get("playing", False))
        rem = st.get("remaining_sec")

        if playing:
            last_playing = True
            settled = 0.0

        # if we were playing and now not playing, start settling
        if last_playing and not playing:
            settled += poll_sec
            if settled >= settle_sec:
                return

        # if remaining seconds known and tiny, return
        try:
            if isinstance(rem, (int, float)) and rem <= 0.35:
                return
        except Exception:
            pass

        time.sleep(max(poll_sec, 0.05))
def duck_external_audio(app_hint: str, level: float, log_fn=None) -> bool:
    """
    Best-effort volume ducking for external apps (Spotify/Chrome/etc).
    Uses pycaw. Returns True if applied to >=1 sessions.
    app_hint = substring match on process name OR app id.
    """
    try:
        from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume  # type: ignore
    except Exception:
        return False

    try:
        sessions = AudioUtilities.GetAllSessions()
        hit = 0
        hint = (app_hint or "").lower()

        for s in sessions:
            try:
                proc = s.Process
                pname = (proc.name() if proc else "") or ""
                pname_l = pname.lower()

                if hint and (hint in pname_l):
                    vol = s._ctl.QueryInterface(ISimpleAudioVolume)
                    vol.SetMasterVolume(float(level), None)
                    hit += 1
            except Exception:
                continue

        if hit and callable(log_fn):
            log_fn("music", f"duck_external_audio applied to {hit} sessions hint={app_hint} level={level}")
        return bool(hit)
    except Exception:
        return False


# =======================
# Global Synchronization
# =======================

SHOW_INTERRUPT = threading.Event()
WIDGETS = None  # Will be initialized after WidgetRegistry class definition
STATION_MEMORY: Dict[str, Any] = {}  # Will be set in main()

# Global widget registry (plugins may register into this)
def wait_until_track_end(stop_event):
    """
    Blocks host flow while external music is playing.
    MVP version will be driven by Windows media session state.
    """

    while is_music_playing():
        time.sleep(0.5)
def is_music_playing():
    # Only respect music state if flows plugin is enabled
    if not MUSIC_STATE.get("flows_enabled", False):
        return False
    return MUSIC_STATE.get("playing", False)

class WidgetRegistry:
    """
    Global registry for widget factories.
    Plugins register widgets here, UI can instantiate them into panels.
    """
    def __init__(self):
        # key -> spec dict
        self._specs: Dict[str, Dict[str, Any]] = {}

    def register(self, key: str, factory, *, title: Optional[str] = None, default_panel: str = "right"):
        key = (key or "").strip().lower()
        if not key:
            return
        self._specs[key] = {
            "key": key,
            "title": title or key,
            "factory": factory,
            "default_panel": (default_panel or "right").strip().lower(),
        }

    def keys(self) -> List[str]:
        return sorted(self._specs.keys())

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self._specs.get((key or "").strip().lower())


def load_feed_plugins(cfg_override: Optional[Dict[str, Any]] = None):
    """
    Loads plugins/*.py once.
    - If plugin has feed_worker -> registers as feed
    - If plugin has register_widgets(registry, runtime_stub) -> registers widgets
    """
    plugins = {}
    
    current_cfg = cfg_override or {}

    plugin_dir = GLOBAL_PLUGINS_DIR or os.path.join(RADIO_OS_ROOT, "plugins")

    # runtime stub for registration-time (no UI yet, but plugins can register factories)
    runtime_stub = {
        "log": log,
        "config": current_cfg,
        "ui_q": ui_q,
        "ui_cmd_q": ui_cmd_q,   # ✅ add this
        "now_ts": now_ts,
        "sha1": sha1,
        "tk": tk,
        "StationEvent": StationEvent,
        "event_q": event_q,
        "MUSIC_STATE": MUSIC_STATE,  # ✅ add this too (see next section)
        "SHOW_INTERRUPT": SHOW_INTERRUPT,  # ✅ for graceful voice interruption
    }

    for path in glob.glob(os.path.join(plugin_dir, "*.py")):
        name = os.path.splitext(os.path.basename(path))[0]

        try:
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            # Feed worker
            # Feed worker (only if marked as feed)

            is_feed = bool(getattr(mod, "IS_FEED", True))  # default = feed

            if hasattr(mod, "feed_worker") and is_feed:
                fn = mod.feed_worker

                plugins[name] = fn

                declared = getattr(mod, "PLUGIN_NAME", None)
                if isinstance(declared, str) and declared.strip():
                    plugins[declared.strip().lower()] = fn

                print(f"Loaded FEED plugin: {name}")


            # Widget registration (optional)
            if hasattr(mod, "register_widgets") and callable(getattr(mod, "register_widgets")):
                try:
                    mod.register_widgets(WIDGETS, runtime_stub)
                    print(f"Registered widgets: {name}")
                except Exception as e:
                    print(f"Widget registration failed {name}: {e}")

        except Exception as e:
            print(f"Plugin load failed {name}: {e}")

    return plugins

def load_station_manifest() -> Dict[str, Any]:
    try:
        path = os.path.join(STATION_DIR, "manifest.yaml")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

def save_station_manifest(cfg: Dict[str, Any]) -> None:
    try:
        path = os.path.join(STATION_DIR, "manifest.yaml")
        # simpler dump, preserving structure as much as yaml allows
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    except Exception as e:
        log("ERR", f"Failed to save manifest: {e}")


CFG = load_station_manifest()

# =======================
# Character Runtime Layer
# =======================

CHARACTERS: Dict[str, str] = {}


# =======================
# Station Metadata
# =======================
def resolve_cfg_path(p: str) -> str:
    """
    Resolve relative paths against:
      1) STATION_DIR
      2) RADIO_OS_ROOT
      3) GLOBAL_VOICES_DIR (for voice models)
    """
    p = (p or "").strip()
    if not p:
        return ""
    if os.path.isabs(p):
        return p

    # Try STATION_DIR
    cand = os.path.join(STATION_DIR, p)
    if os.path.exists(cand):
        return cand

    # Try RADIO_OS_ROOT
    if RADIO_OS_ROOT:
        cand = os.path.join(RADIO_OS_ROOT, p)
        if os.path.exists(cand):
            return cand
            
    # Try GLOBAL_VOICES_DIR
    if GLOBAL_VOICES_DIR:
        cand = os.path.join(GLOBAL_VOICES_DIR, p)
        if os.path.exists(cand):
            return cand

    return p



def _auto_detect_piper_bin() -> str:
    """
    Auto-detect piper binary based on platform.
    Searches in GLOBAL_VOICES_DIR (RADIO_OS_VOICES) or RADIO_OS_ROOT/voices/
    
    Returns: absolute path to piper binary or empty string if not found
    """
    # Determine platform-specific paths to search
    if IS_WINDOWS:
        candidates = [
            "piper_windows_amd64/piper/piper.exe",
            "piper_windows/piper.exe",
            "piper.exe",
        ]
    elif IS_MAC:
        candidates = [
            "piper_macos_amd64/piper/piper",
            "piper_macos_arm64/piper/piper",
            "piper_macos/piper",
            "piper",
        ]
    elif IS_LINUX:
        candidates = [
            "piper_linux_amd64/piper/piper",
            "piper_linux_x86_64/piper/piper",
            "piper_linux/piper",
            "piper",
        ]
    else:
        return ""
    
    # Search locations
    search_dirs = []
    
    # 1. GLOBAL_VOICES_DIR if set
    if GLOBAL_VOICES_DIR and os.path.isdir(GLOBAL_VOICES_DIR):
        search_dirs.append(GLOBAL_VOICES_DIR)
    
    # 2. RADIO_OS_ROOT/voices/
    if RADIO_OS_ROOT:
        voices_dir = os.path.join(RADIO_OS_ROOT, "voices")
        if os.path.isdir(voices_dir):
            search_dirs.append(voices_dir)
    
    # 3. Relative to current working directory
    if os.path.isdir("voices"):
        search_dirs.append("voices")
    
    # Try each candidate in each search directory
    for search_dir in search_dirs:
        for candidate in candidates:
            full_path = os.path.join(search_dir, candidate)
            if os.path.exists(full_path) and os.access(full_path, os.X_OK):
                return os.path.abspath(full_path)
    
    return ""


STATION_NAME = CFG.get("station", {}).get("name", "Radio OS Station")
HOST_NAME = CFG.get("station", {}).get("host", "Host")


# =======================
# Queues & Buses
# =======================

subtitle_q: "queue.Queue[str]" = queue.Queue()

dj_q: "queue.Queue[Tuple[str, Any]]" = queue.Queue()

ui_q: "queue.Queue[Tuple[str, Any]]" = queue.Queue()

event_q = queue.Queue()
ui_cmd_q: "queue.Queue[Tuple[str, Any]]" = queue.Queue()
music_cmd_q: "queue.Queue[Tuple[str, Any]]" = queue.Queue()


# =======================
# Scheduler Settings
# =======================




# =======================
# Pacing Defaults
# =======================

PACE = CFG.get("pacing", {})

HOST_IDLE_RIFF_SEC = int(PACE.get("idle_riff_sec", 20))
HOST_BETWEEN_SEGMENTS_SEC = int(PACE.get("between_segments_sec", 2))

QUEUE_TARGET_DEPTH = int(PACE.get("queue_target_depth", 16))
QUEUE_MAX_DEPTH = int(PACE.get("queue_max_depth", 64))

PRODUCER_TICK_SEC = float(PACE.get("producer_tick_sec", 30))


# =======================
# Audio Buffering
# =======================

AUDIO_TARGET_DEPTH = int(PACE.get("audio_target_depth", 8))
AUDIO_MAX_DEPTH = int(PACE.get("audio_max_depth", 10))
AUDIO_TICK_SLEEP = float(PACE.get("audio_tick_sleep", 0.05))

# =======================
# Runtime Globals (ONE FILE)
# =======================

SHOW_NAME = CFG.get("station", {}).get("name", STATION_NAME)

# unify scheduler config (supports both schema variants)
_scheduler_cfg = CFG.get("scheduler", {}) if isinstance(CFG.get("scheduler", {}), dict) else {}
SOURCE_QUOTAS = (
    _scheduler_cfg.get("quotas")
    or _scheduler_cfg.get("source_quotas")
    or {}
)
if not isinstance(SOURCE_QUOTAS, dict):
    SOURCE_QUOTAS = {}
FAIR_WINDOW = int(sum(int(v) for v in SOURCE_QUOTAS.values())) if SOURCE_QUOTAS else 1

# audio buffer queue must exist
audio_queue: "queue.Queue[AudioItem]" = queue.Queue(maxsize=AUDIO_MAX_DEPTH)

# producer kick event must exist
producer_kick = threading.Event()

# claim timeout safety (reclaim stuck claimed rows)
CLAIM_TIMEOUT_SEC = int(_scheduler_cfg.get("claim_timeout_sec", 10 * 60))

def cfg_get(path: str, default=None):
    """
    Safe CFG lookup: cfg_get("tts.min_gap_sec", 8)
    """
    cur = CFG
    for part in (path or "").split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur
HOST_CFG = CFG.get("host", {}) if isinstance(CFG.get("host", {}), dict) else {}

HOST_MAX_COMMENTS        = int(cfg_get("host.max_comments", HOST_CFG.get("max_comments", 6)))
HOST_MAX_TOKENS          = int(cfg_get("host.max_tokens", HOST_CFG.get("max_tokens", 300)))
HOST_TEMPERATURE         = float(cfg_get("host.temperature", HOST_CFG.get("temperature", 0.75)))

HOST_STATION_ID_SEC      = int(cfg_get("host.station_id_sec", HOST_CFG.get("station_id_sec", 18 * 60)))
HOST_IDLE_RIFF_SEC_CFG   = int(cfg_get("host.idle_riff_sec", HOST_CFG.get("idle_riff_sec", HOST_IDLE_RIFF_SEC)))
HOST_BETWEEN_SEGMENTS_SEC_CFG = float(cfg_get("host.between_segments_sec", HOST_CFG.get("between_segments_sec", HOST_BETWEEN_SEGMENTS_SEC)))

def _normalize_source_alias(src: str) -> str:
    """Normalize source name aliases."""
    src = (src or "").strip().lower()
    # Add any source aliases here
    return src

def normalize_source(src: str) -> str:
    src = (src or "").strip().lower()
    src = _normalize_source_alias(src)
    return src if src else "feed"

def save_cfg_to_manifest():
    """
    Persist the current in-memory CFG back to manifest.yaml.
    """
    try:
        path = os.path.join(STATION_DIR, "manifest.yaml")
        # We need to preserve comments if possible, but standard yaml dump won't.
        # For now, just dump. Users should know this might reformat their file.
        # To be safe, we only modify specific sections if we could, but CFG is monolithic.
        # Using a simple locking approach to avoid partial writes.
        
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(CFG, f, sort_keys=False, allow_unicode=True)
        log("system", "Saved configuration to manifest.yaml")
    except Exception as e:
        log("system", f"Failed to save manifest: {e}")



def normalize_event_type(t: str) -> str:
    t = (t or "").strip().lower()
    return t if t else "item"

# =======================
# Core Data Structures
# =======================
@dataclass
class AudioItem:
    bundle: List[Tuple[str, str]]
    seg: Dict[str, Any]

@dataclass
class StationEvent:
    source: str
    type: str
    ts: int
    severity: float = 0.0
    priority: float = 50.0
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataPoint:
    ts: int
    fields: Dict[str, float]


class DataBuffer:
    def __init__(self, maxlen: int = 500):
        self.buf = deque(maxlen=maxlen)

    def add(self, p: DataPoint):
        self.buf.append(p)

    def values(self, key: str) -> List[float]:
        return [x.fields.get(key, 0.0) for x in self.buf]

    def last(self) -> Optional[DataPoint]:
        return self.buf[-1] if self.buf else None


# =======================
# Utilities
# =======================



def sha1(s: Any) -> str:
    s = "" if s is None else str(s)
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()


def get_visual_model_config() -> dict:
    """
    Get visual model configuration from environment variables.
    Returns a dict with keys: model_type, local_model, api_provider, api_model, 
    api_key, api_endpoint, max_image_size, image_quality.
    """
    return {
        "model_type": os.getenv("VISUAL_MODEL_TYPE", "local"),
        "local_model": os.getenv("VISUAL_MODEL_LOCAL", ""),
        "api_provider": os.getenv("VISUAL_MODEL_API_PROVIDER", ""),
        "api_model": os.getenv("VISUAL_MODEL_API_MODEL", ""),
        "api_key": os.getenv("VISUAL_MODEL_API_KEY", ""),
        "api_endpoint": os.getenv("VISUAL_MODEL_API_ENDPOINT", ""),
        "max_image_size": int(os.getenv("VISUAL_MODEL_MAX_IMAGE_SIZE", "1024")),
        "image_quality": int(os.getenv("VISUAL_MODEL_IMAGE_QUALITY", "85")),
    }


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def ewma(prev: float, x: float, alpha: float) -> float:
    return prev + alpha * (x - prev)




def extract_first_json_object(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip()

    # Fast path
    if s.startswith("{") and s.endswith("}"):
        return s

    # Scan for first balanced {...}
    start = s.find("{")
    if start < 0:
        return ""

    depth = 0
    in_str = False
    esc = False

    for i in range(start, len(s)):
        ch = s[i]

        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start:i+1]

    return ""


def parse_json_strictish(raw: str) -> Dict[str, Any]:
    """
    Guaranteed behavior:
    - returns dict or raises JSONDecodeError/ValueError
    - extracts first JSON object if raw contains extra text
    """
    j = extract_first_json_object(raw)
    if not j:
        raise ValueError("No JSON object found in LLM output")
    return json.loads(j)
def llm_json_with_repair(prompt: str, system: str, model: str,
                         num_predict: int, temperature: float, timeout: int,
                         *, repair_round: bool = True) -> Dict[str, Any]:
    raw = llm_generate(prompt, system, model, num_predict, temperature, timeout, force_json=True)

    try:
        obj = parse_json_strictish(raw)
        if isinstance(obj, dict):
            return obj
        raise ValueError("LLM JSON was not a dict")
    except Exception as e:
        if not repair_round:
            raise

        # One repair attempt: model must output ONLY JSON
        repair_sys = system + "\n\nYou MUST output ONLY valid JSON. No prose. No markdown."
        repair_prompt = f"""
The previous output was invalid JSON.

Return the SAME content as STRICT JSON only.
Do not add new fields. Do not add comments.

INVALID_OUTPUT:
{raw}
""".strip()

        raw2 = llm_generate(repair_prompt, repair_sys, model, num_predict, temperature, timeout, force_json=True)
        obj2 = parse_json_strictish(raw2)
        if not isinstance(obj2, dict):
            raise ValueError("Repaired JSON was not a dict")
        return obj2

# =======================
# Logging
# =======================

# =======================
# Logging
# =======================

print_lock = threading.Lock()

def _console_safe(s: str) -> str:
    """
    Force any message to be printable on Windows consoles (cp1252, etc.)
    without throwing UnicodeEncodeError.
    """
    try:
        enc = (getattr(sys.stdout, "encoding", None) or "utf-8")
        return str(s).encode(enc, errors="backslashreplace").decode(enc, errors="ignore")
    except Exception:
        return str(s).encode("utf-8", errors="backslashreplace").decode("utf-8", errors="ignore")

def log(role: str, msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    with print_lock:
        safe_role = _console_safe(role.upper())
        safe_msg  = _console_safe(msg)
        print(f"[{safe_role:>8} {ts}] {safe_msg}", flush=True)

def log_every(mem: Dict[str, Any], key: str, every_sec: int, role: str, msg: str) -> None:
    now = now_ts()
    lk = mem.setdefault("_log_last", {})
    last = int(lk.get(key, 0))

    if now - last >= every_sec:
        lk[key] = now
        mem["_log_last"] = lk
        log(role, msg)




# =======================
# Feed Helper Utilities
# =======================

def is_image_url(url: str) -> bool:
    return url.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))


def download_temp_image(url: str) -> Optional[str]:
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        fd, path = tempfile.mkstemp(suffix=".png")
        with os.fdopen(fd, "wb") as f:
            f.write(r.content)
        return path
    except Exception:
        return None
# =======================
# Event → Segment Mapping
# =======================

def event_to_segment(evt: StationEvent, mem: Dict[str, Any]) -> Dict[str, Any]:
    pri = max(0.0, min(100.0, float(evt.priority)))

    title = evt.payload.get("title") or evt.type
    body = evt.payload.get("body") or json.dumps(evt.payload, ensure_ascii=False)

    src = normalize_source(evt.source)
    etype = normalize_event_type(evt.type)

    return {
        "id": sha1(f"evt|{src}|{etype}|{evt.ts}|{random.random()}"),
        "post_id": sha1(f"evtkey|{src}|{etype}|{evt.ts}"),
        "source": src,
        "event_type": etype,
        "title": str(title)[:240],
        "body": clamp_text(str(body), 1400),
        "comments": [],
        "angle": evt.payload.get("angle", "React naturally to what just happened."),
        "why": evt.payload.get("why", "Live update from a feed source."),
        "key_points": evt.payload.get("key_points", ["what changed", "why it matters"]),
        "priority": pri,
        "host_hint": evt.payload.get("host_hint", "Quick live update."),
    }

# =======================
# Database Helpers
# =======================
def db_depth_claimed(conn) -> int:
    cur = conn.execute("SELECT COUNT(*) FROM segments WHERE status='claimed';")
    return int(cur.fetchone()[0])

def db_flush_queue():
    conn = db_connect()
    conn.execute("DELETE FROM segments;")
    conn.commit()
    conn.close()


def db_reset_claimed(conn: sqlite3.Connection) -> None:
    """
    Reclaim inflight work from previous runs.
    """
    conn.execute(
        "UPDATE segments SET status='queued', claimed_ts=NULL WHERE status='claimed';"
    )
    conn.commit()

# =======================
# DB Queue Safety
# =======================

def db_reclaim_stuck_claims(conn: sqlite3.Connection, *, older_than_sec: int = CLAIM_TIMEOUT_SEC) -> int:
    """
    If a worker dies mid-segment, rows can remain claimed forever.
    Reclaim them if claimed_ts is too old.
    """
    cutoff = now_ts() - int(older_than_sec)
    cur = conn.execute(
        "UPDATE segments SET status='queued', claimed_ts=NULL "
        "WHERE status='claimed' AND COALESCE(claimed_ts, 0) < ?;",
        (cutoff,)
    )
    conn.commit()
    return int(getattr(cur, "rowcount", 0) or 0)

def db_return_to_queue(conn: sqlite3.Connection, seg_id: str) -> None:
    conn.execute(
        "UPDATE segments SET status='queued', claimed_ts=NULL WHERE id=?;",
        (seg_id,)
    )
    conn.commit()


# =======================
# Event Router
# =======================

def event_router_worker(
    stop_event: threading.Event,
    mem: Dict[str, Any],
    *,
    poll_timeout: float = 0.25,
    loop_sleep: float = 0.03,
    batch_max: int = 12,
    batch_time_budget: float = 0.20,
    dedupe_window_sec: int = 90,
) -> None:
    """
    Routes StationEvent objects into the SQLite segment queue.

    Guarantees:
      - Own DB connection
      - Batch processing
      - Soft dedupe
      - Never crashes station loop
    """

    conn = db_connect()
    migrate_segments_table(conn)

    dedupe: Dict[str, int] = {}

    def dedupe_key(evt: StationEvent) -> str:
        t = str(evt.payload.get("title", ""))[:200]
        b = str(evt.payload.get("body", ""))[:200]
        return sha1(f"{evt.source}|{evt.type}|{t}|{b}")

    def dedupe_ok(evt: StationEvent) -> bool:
        now = now_ts()
        k = dedupe_key(evt)
        last = int(dedupe.get(k, 0))

        if now - last < dedupe_window_sec:
            return False

        dedupe[k] = now

        # prune map periodically
        if len(dedupe) > 600:
            cutoff = now - (dedupe_window_sec * 4)
            for kk, ts in list(dedupe.items()):
                if ts < cutoff:
                    dedupe.pop(kk, None)

        return True

    def enqueue_from_event(evt: StationEvent) -> None:
        seg = event_to_segment(evt, mem)
        if not seg:
            return

        db_enqueue_segment(conn, seg)

        try:
            producer_kick.set()
        except Exception as e:
            log("ERR", f"{type(e).__name__}: {e}")

        try:
            save_memory_throttled(mem, min_interval_sec=1.0)
        except Exception:
            pass

        try:
            ui_q.put(("set_segment_display", seg))
            ui_q.put(("widget_update", {
                "widget_key": "timeline_replay",
                "data": {"push": seg}
            }))

        except Exception as e:
            log("ERR", f"{type(e).__name__}: {e}")

    while not stop_event.is_set():
        # -------------------
        # Clean boot cold open
        # -------------------
        if not mem.get("_boot_open_played"):
            try:
                # If absolutely nothing in system yet, seed + force render
                if db_depth_total(conn) == 0:
                    enqueue_cold_open(conn, mem)

                # Let TTS pick it up naturally
                producer_kick.set()

                mem["_boot_open_played"] = True
                save_memory_throttled(mem, min_interval_sec=1.0)

            except Exception as e:
                log("host", f"boot open error: {type(e).__name__}: {e}")

        t_start = time.time()
        routed = 0

        try:
            # Primary blocking pull
            try:
                evt = event_q.get(timeout=poll_timeout)
                if isinstance(evt, StationEvent) and dedupe_ok(evt):
                    enqueue_from_event(evt)
                    routed += 1
            except queue.Empty:
                pass

            # Opportunistic batch drain
            while routed < batch_max and (time.time() - t_start) <= batch_time_budget:
                try:
                    evt = event_q.get_nowait()
                except queue.Empty:
                    break

                if isinstance(evt, StationEvent) and dedupe_ok(evt):
                    enqueue_from_event(evt)
                    routed += 1

        except Exception as e:
            log("router", f"Router error: {type(e).__name__}: {e}")

        try:
            log_every(
                mem,
                "router_heartbeat",
                8,
                "router",
                f"heartbeat routed={routed} queued={db_depth_queued(conn)}"
            )
        except Exception as e:
            log("ERR", f"{type(e).__name__}: {e}")

        time.sleep(loop_sleep)

    try:
        conn.close()
    except Exception:
        pass

# =======================
# Tag Heat Memory System
# =======================

def ensure_heat_store(mem: Dict[str, Any]) -> None:
    if "tag_heat" not in mem:
        mem["tag_heat"] = {}

def db_gc_done(conn: sqlite3.Connection, *, older_than_sec: int = 7*24*3600) -> int:
    cutoff = now_ts() - int(older_than_sec)
    cur = conn.execute(
        "DELETE FROM segments WHERE status='done' AND created_ts < ?;",
        (cutoff,)
    )
    conn.commit()
    return int(getattr(cur, "rowcount", 0) or 0)
# Put near other locks / globals
status_lock = threading.Lock()
memory_lock = threading.Lock()

def _atomic_write_json(path: str, data: Dict[str, Any], *, retries: int = 12, base_sleep: float = 0.03) -> bool:
    """
    Windows-safe atomic JSON writer.

    Why this exists:
      - os.replace() can fail with WinError 5 if the destination is momentarily locked
        (indexers, OneDrive, antivirus, another reader, etc.).
      - We retry a few times with small backoff.
      - If it still fails, we write a fallback file instead of crashing a worker.
    """
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)

    # Use a unique temp name per attempt to avoid collisions.
    for i in range(retries):
        tmp = os.path.join(folder, f".{os.path.basename(path)}.{os.getpid()}.{threading.get_ident()}.{i}.tmp")
        try:
            # Write temp file fully
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())

            # Atomic replace
            os.replace(tmp, path)
            return True

        except PermissionError as e:
            # Cleanup tmp if possible
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            time.sleep(base_sleep * (1.0 + i * 0.35))
            continue

        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            return False

    # Final fallback: write a non-atomic "status_fallback.json"
    try:
        fb = os.path.join(folder, "status_fallback.json")
        with open(fb, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return True
    except Exception:
        return False


def write_status(station_dir: str, data: Dict[str, Any]) -> None:
    try:
        path = os.path.join(station_dir, "status.json")
        data["ts"] = int(time.time())

        with status_lock:
            ok = _atomic_write_json(path, data, retries=12, base_sleep=0.03)

        if not ok:
            # Never crash; just log once in a while
            # (mem isn't available here, so keep it simple)
            log("status", "write_status failed (non-fatal)")

    except Exception as e:
        log("ERR", f"{type(e).__name__}: {e}")


def bump_tag_heat(
    mem: Dict[str, Any],
    tags: List[str],
    boost: float = 10.0,
    default_half_life: float = 48.0
) -> None:
    ensure_heat_store(mem)
    now = now_ts()

    for tag in tags:
        tag = tag.lower().strip()
        if not tag:
            continue

        if tag not in mem["tag_heat"]:
            mem["tag_heat"][tag] = {
                "heat": 0.0,
                "half_life_hours": default_half_life,
                "last_touched": now
            }

        mem["tag_heat"][tag]["heat"] += boost
        mem["tag_heat"][tag]["last_touched"] = now


def decay_tag_heat(mem: Dict[str, Any]) -> None:
    ensure_heat_store(mem)
    now = now_ts()

    for tag, data in list(mem["tag_heat"].items()):
        heat = float(data.get("heat", 0))
        half_life = float(data.get("half_life_hours", 48))
        last = int(data.get("last_touched", now))

        if heat <= 0:
            continue

        dt_hours = max((now - last) / 3600.0, 0)
        decayed = heat * (0.5 ** (dt_hours / max(half_life, 0.01)))

        if decayed < 0.5:
            del mem["tag_heat"][tag]
            continue

        data["heat"] = decayed


def pick_hot_tags(
    mem: Dict[str, Any],
    k: int = 3,
    min_heat: float = 5.0,
    cooldown_sec: int = 12 * 60,
    explore_prob: float = 0.35
) -> List[str]:

    ensure_heat_store(mem)
    decay_tag_heat(mem)

    now = now_ts()
    last_spoken = mem.setdefault("tag_last_spoken", {})

    pool, weights = [], []

    for tag, data in mem["tag_heat"].items():
        heat = float(data.get("heat", 0))
        if heat < min_heat:
            continue

        last = int(last_spoken.get(tag, 0))
        if now - last < cooldown_sec:
            continue

        pool.append(tag)
        weights.append(heat)

    chosen = []

    recent = mem.get("recent_riff_tags", [])[-12:]
    recent_set = set(recent)

    catalog = CFG.get("riff", {}).get("tag_catalog", [])

    def add_explore_tag():
        candidates = [t for t in catalog if t not in recent_set]
        if not candidates:
            candidates = catalog[:]
        if candidates:
            t = random.choice(candidates)
            if t not in chosen:
                chosen.append(t)

    if not pool:
        while len(chosen) < k and catalog:
            add_explore_tag()
    else:
        for _ in range(k):
            if pool and (random.random() > explore_prob or not chosen):
                t = random.choices(pool, weights=weights, k=1)[0]
                idx = pool.index(t)
                pool.pop(idx)
                weights.pop(idx)
                if t not in chosen:
                    chosen.append(t)
            else:
                add_explore_tag()

    for t in chosen:
        last_spoken[t] = now
        mem.setdefault("recent_riff_tags", []).append(t)

    mem["recent_riff_tags"] = mem["recent_riff_tags"][-60:]
    save_memory(mem)

    return chosen


# =======================
# Riff Generation Shapes
# =======================

RIFF_SHAPES = CFG.get("riff", {}).get("shapes", [
    "connect_two",
    "myth_bust",
    "failure_mode",
    "tradeoff",
    "tease_next"
])


def next_riff_shape(mem: Dict[str, Any]) -> str:
    lru = mem.setdefault("riff_style_lru", [])

    if not lru:
        lru = RIFF_SHAPES[:]
        random.shuffle(lru)

    shape = lru.pop(0)
    mem["riff_style_lru"] = lru
    save_memory(mem)

    return shape


def heat_riff_prompt(mem: Dict[str, Any]) -> str:
    hot_tags = pick_hot_tags(mem, k=3)
    shape = next_riff_shape(mem)

    if not hot_tags:
        return ""

    return f"""
You have a short natural gap on air. Speak casually for about {HOST_IDLE_RIFF_SEC} seconds.

Tags:
{hot_tags}

Riff shape: {shape}

Tone:
- Conversational radio flow
- No bullet points
- No announcements
""".strip()


# =======================
# Cold Open Seeding
# =======================

def enqueue_cold_open(conn: sqlite3.Connection, mem: Dict[str, Any]) -> None:
    """
    Seeds a generative cold open when the queue is empty.

    Cold opens are contextual seeds, not literal spoken content.
    """

    if db_depth_total(conn) > 0:
        return

    hot_tags = pick_hot_tags(mem, k=6)
    recent_themes = mem.get("themes", [])[-8:]
    recent_callbacks = mem.get("callbacks", [])[-6:]

    seed_context = {
        "hot_tags": hot_tags,
        "themes": recent_themes,
        "callbacks": recent_callbacks,
        "mood": random.choice([
            "reflective",
            "curious",
            "energetic",
            "grounded",
            "optimistic",
            "analytical"
        ]),
        "focus": random.choice([
            "recent events",
            "emerging patterns",
            "unexpected changes",
            "what people are missing",
            "big picture trends"
        ])
    }

    seg_obj = {
        "id": sha1(f"coldopen|{now_ts()}|{random.random()}"),
        "post_id": sha1(f"coldopen_seed|{now_ts()}"),

        "source": "station",
        "event_type": "cold_open",

        "title": "Live show opening",

        "body": json.dumps(seed_context, ensure_ascii=False),

        "comments": [],

        "angle": "Generate a natural evolving opening thought.",
        "why": "Set tone and continuity.",
        "key_points": hot_tags[:3] if hot_tags else [],

        "priority": 94.0,
        "host_hint": "open_dynamic",
        "lead_voice": resolve_lead_voice(mem=mem)
    }

    db_enqueue_segment(conn, seg_obj)

    if hot_tags:
        bump_tag_heat(mem, hot_tags, boost=20.0)

    save_memory(mem)


# =======================
# Text Cleaning (Generic)
# =======================
def clamp_text(t: str, max_len: int) -> str:
    t = (t or "").strip()
    if len(t) <= max_len:
        return t
    return t[:max_len - 3].rstrip() + "..."
def normalize_text(t: str) -> str:
    if not t:
        return ""
    return (
        t.replace("\u2011", "-")
         .replace("\u2013", "-")
         .replace("\u2014", "-")
         .replace("\u2019", "'")
         .replace("\u201c", '"')
         .replace("\u201d", '"')
    )

def clean(t: str) -> str:
    if not t:
        return ""

    t = re.sub(r"\[.*?\]", "", t)
    t = re.sub(r"\*+", "", t)
    t = re.sub(r"_+", "", t)
    t = re.sub(r"~+", "", t)
    t = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", t)

    t = t.replace(":", "").replace(";", "")

    t = t.replace("\r", " ")
    t = re.sub(r"\s+", " ", t.strip())

    return t
# =======================
# Time & Hash Helpers
# =======================

def now_ts() -> int:
    return int(time.time())








# =======================
# Memory Persistence
# =======================

def load_memory() -> Dict[str, Any]:
    if os.path.exists(MEMORY_PATH):
        try:
            with open(MEMORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log("ERR", f"{type(e).__name__}: {e}")


    return {
        "themes": [],
        "callbacks": [],
        "recent_riff_tags": [],
        "tag_heat": {},
        "tag_last_spoken": {},
        "riff_style_lru": [],
    }


def save_memory(mem: Dict[str, Any]) -> None:
    try:
        folder = os.path.dirname(MEMORY_PATH) or "."
        os.makedirs(folder, exist_ok=True)
        with memory_lock:
            _atomic_write_json(MEMORY_PATH, mem, retries=8, base_sleep=0.02)
    except Exception as e:
        log("ERR", f"save_memory error: {type(e).__name__}: {e}")


# =======================
# Audio Playback + TTS
# =======================

audio_lock = threading.Lock()


def play_wav(path: str) -> None:
    for _ in range(10):
        if os.path.exists(path) and os.path.getsize(path) > 44:
            break
        time.sleep(0.02)

    try:
        data, sr = sf.read(path, dtype="float32")
    except Exception:
        return

    if data.ndim == 1:
        data = data.reshape(-1, 1)

    sd.play(data, sr)
    sd.wait()
def merged_voice_map() -> Dict[str, str]:
    """
    Merge CFG['voices'] with CFG['audio']['voices'] (audio overrides),
    and return a resolved map.
    """
    voice_map = CFG.get("voices", {}) if isinstance(CFG.get("voices"), dict) else {}
    audio_cfg = CFG.get("audio", {}) if isinstance(CFG.get("audio"), dict) else {}
    audio_voices = audio_cfg.get("voices", {}) if isinstance(audio_cfg.get("voices"), dict) else {}

    merged = dict(voice_map)
    merged.update(audio_voices)

    # Resolve all paths
    out: Dict[str, str] = {}
    for k, v in merged.items():
        if not v:
            continue
        out[str(k).strip().lower()] = resolve_voice_path(str(v))
    return out


def voice_is_playable(voice_key: str) -> bool:
    """
    A voice is playable if:
      - Provider is configured
      - Voice file/ID exists for that key (or falls back to 'host')
    
    For local Piper: checks if voice file exists.
    For API providers: checks if API key is available.
    """
    voice_key = (voice_key or "").strip().lower()
    if not voice_key:
        return False

    try:
        audio_cfg = CFG.get("audio", {}) if isinstance(CFG.get("audio"), dict) else {}
        voice_provider_type = (audio_cfg.get("voices_provider") or "piper").strip().lower()

        # For local Piper, verify file exists
        if voice_provider_type == "piper":
            piper_bin = resolve_cfg_path((audio_cfg.get("piper_bin", "") or "").strip())
            if not piper_bin or not os.path.exists(piper_bin):
                return False

            vm = merged_voice_map()
            vp = vm.get(voice_key) or vm.get("host")
            return bool(vp and os.path.exists(vp))

        # For API providers, just check that the provider can be instantiated
        # (which validates API key presence)
        else:
            from voice_provider import get_voice_provider
            try:
                _provider = get_voice_provider(CFG, audio_cfg)
                return True
            except Exception:
                return False

    except Exception:
        return False

import numpy as np

AUDIO_LEVEL = 0.0
_AUDIO_SMOOTH = 0.85   # 0.7 = snappy, 0.9 = smooth


def speak(text: str, voice_key: str = None):

    global AUDIO_LEVEL

    # -----------------------------
    # Normalize
    # -----------------------------
    
    # Default to lead character if no voice specified
    if not voice_key:
        voice_key = resolve_lead_voice(mem=STATION_MEMORY)

    text = normalize_text(clean(text))
    if not text:
        return

    if SHOW_INTERRUPT.is_set():
        return
        
    # Apply global volume/speed (Radio Dial)
    try:
        audio_cfg = CFG.get("audio", {})
        vol = float(audio_cfg.get("volume", 1.0))
        spd = float(audio_cfg.get("speed", 1.0))
        
        # Volume (simple gain)
        if vol != 1.0:
            data = data * vol
            
        # Speed (playback rate modification - chipmunk key)
        # Higher speed = higher sample rate to consume samples faster
        if spd != 1.0:
            sr = int(sr * spd)
    except Exception:
        pass


    # =====================================================
    # HARD MUSIC GATE (pre-play)
    # =====================================================

    try:
        flows_enabled = bool(MUSIC_STATE.get("flows_enabled", False))
        playing = bool(MUSIC_STATE.get("playing", False)) if flows_enabled else False
        allow_bg = bool(MUSIC_STATE.get("allow_background_music", False))
    except Exception:
        playing = False
        allow_bg = False

    if playing and not allow_bg:
        
        # Check if this speak() is for a music break boundary (which should interrupt music)
        # But speak() has no context of "why" it was called usually.
        # However, music_breaks logic in host_loop() pauses music BEFORE calling speak() for breaks.
        # So usually if we are here, music IS playing and we are trying to talk over it.

        # If the host loop specifically requested music pause, it might take a second to reflect in MUSIC_STATE.
        # But if we block here forever, we might deadlock if the music never updates state.
        
        # Workaround: if we have waited > 15s, just talk anyway?
        # Better: check if we are in a 'break' mode?
        
        log("audio", "Music active → blocking TTS output")

        # wait until music stops
        fail_safe = 0
        while not SHOW_INTERRUPT.is_set():

            try:
                flows_enabled = bool(MUSIC_STATE.get("flows_enabled", False))
                music_still_playing = bool(MUSIC_STATE.get("playing", False)) if flows_enabled else False
                if not music_still_playing:
                    break
            except Exception:
                pass
            
            time.sleep(0.2)
            fail_safe += 1
            if fail_safe > 25: # 5 seconds max wait then force talk
                 log("audio", "Music gate timeout -> speaking anyway")
                 break

            time.sleep(0.1)

        # small settle delay
        try:
            time.sleep(float(MUSIC_STATE.get("fade_sec", 0.25)))
        except Exception:
            pass


    # =====================================================
    # Voice Synthesis (Multi-Provider)
    # =====================================================

    audio_cfg = CFG.get("audio", {}) if isinstance(CFG.get("audio"), dict) else {}
    voice_provider_type = (audio_cfg.get("voices_provider") or "piper").strip().lower()

    # Build merged voice map for provider
    voice_map = CFG.get("voices", {}) if isinstance(CFG.get("voices"), dict) else {}
    audio_voices = audio_cfg.get("voices", {}) if isinstance(audio_cfg.get("voices"), dict) else {}
    
    merged_voice_map = dict(voice_map)
    merged_voice_map.update(audio_voices)

    # For Piper (local), resolve paths; for APIs, keep IDs as-is
    if voice_provider_type == "piper":
        for k in merged_voice_map:
            merged_voice_map[k] = resolve_voice_path(str(merged_voice_map[k]))

    with audio_lock:

        if SHOW_INTERRUPT.is_set():
            return

        try:
            from voice_provider import get_voice_provider

            provider = get_voice_provider(CFG, audio_cfg)
            data, sr = provider.synthesize(
                voice_key=voice_key,
                text=text,
                voice_map=merged_voice_map,
            )

            log("audio", f"TTS provider={voice_provider_type} voice={voice_key} chars={len(text)}")

        except Exception as e:
            log("audio", f"TTS error [{voice_provider_type}]: {type(e).__name__}: {e}")
            return

    if data is None or sr is None:
        return

    if getattr(data, "ndim", 0) == 1:
        data = data.reshape(-1, 1)


    # =====================================================
    # Subtitle pacing (audio timeline)
    # =====================================================

    words = text.split()

    duration = len(data) / float(sr) if sr else 0.0

    if duration <= 0:
        duration = max(len(words) * 0.25, 1.0)

    word_time = max((duration / max(len(words), 1)) * 0.75, 0.08)

    next_word_at = word_time
    progress = []


    # =====================================================
    # Stream playback + synced subtitles + waveform
    # =====================================================

    chunk = 512

    try:
        with sd.OutputStream(
            samplerate=sr,
            channels=data.shape[1],
            dtype="float32"
        ) as stream:

            total = len(data)
            pos = 0

            while pos < total:

                if SHOW_INTERRUPT.is_set():
                    break

                # -----------------------------
                # MID-PLAY MUSIC CUT
                # -----------------------------

                try:
                    # Only cut voice for music if flows plugin is enabled
                    flows_enabled = MUSIC_STATE.get("flows_enabled", False)
                    if flows_enabled and MUSIC_STATE.get("playing") and not MUSIC_STATE.get("allow_background_music"):
                        log("audio", "Music resumed mid-TTS → cutting voice")
                        break
                except Exception:
                    pass


                end = min(pos + chunk, total)
                block = data[pos:end]

                stream.write(block)

                # -----------------------------
                # RMS waveform level
                # -----------------------------

                samples = block[:, 0]
                rms = np.sqrt(np.mean(samples * samples))
                level = min(rms * 6.0, 1.0)

                AUDIO_LEVEL = (_AUDIO_SMOOTH * AUDIO_LEVEL) + ((1 - _AUDIO_SMOOTH) * level)

                pos = end


                # -----------------------------
                # Subtitle progression (audio time)
                # -----------------------------

                audio_t = pos / float(sr)

                while words and audio_t >= next_word_at:

                    progress.append(words.pop(0))

                    display = f"{voice_key.upper()}: " + " ".join(progress)

                    subtitle_q.put(display)

                    next_word_at += word_time

    except Exception as e:
        log("audio", f"audio stream failed: {type(e).__name__}: {e}")
        return


    # =====================================================
    # Cleanup
    # =====================================================

    subtitle_q.put("")
    AUDIO_LEVEL = 0.0
    
    # =====================================================
    # Character Mix Tracking
    # =====================================================
    
    try:
        # Track character speech for balance monitoring
        from plugins.character_mix import track_character_speech
        track_character_speech(voice_key, STATION_MEMORY)
    except Exception:
        pass  # Plugin not loaded or error - no problem


def normalize_audio_config_paths():
    audio_cfg = CFG.get("audio", {}) if isinstance(CFG.get("audio"), dict) else {}
    if not isinstance(audio_cfg, dict):
        audio_cfg = {}

    # normalize piper_bin with platform-specific auto-detection
    pb = (audio_cfg.get("piper_bin") or "").strip()
    
    if pb:
        # User specified a path - resolve it
        pb = resolve_cfg_path(pb)
    else:
        # Auto-detect piper binary based on platform
        pb = _auto_detect_piper_bin()
    
    if pb:
        audio_cfg["piper_bin"] = pb

    # normalize voice files in BOTH places (voices + audio.voices)
    def norm_voice_map(m):
        if not isinstance(m, dict):
            return {}
        out = {}
        for k, v in m.items():
            out[k] = resolve_voice_path(str(v)) if v else ""
        return out

    top_voices = CFG.get("voices", {}) if isinstance(CFG.get("voices"), dict) else {}
    audio_voices = audio_cfg.get("voices", {}) if isinstance(audio_cfg.get("voices"), dict) else {}

    CFG["voices"] = norm_voice_map(top_voices)
    audio_cfg["voices"] = norm_voice_map(audio_voices)
    CFG["audio"] = audio_cfg

def play_audio_bundle(bundle):
    merged = []
    cur_voice = None
    cur_text = []

    for voice, text in bundle:
        if voice == cur_voice:
            cur_text.append(text)
        else:
            if cur_text:
                merged.append((cur_voice, " ".join(cur_text)))
            cur_voice = voice
            cur_text = [text]

    if cur_text:
        merged.append((cur_voice, " ".join(cur_text)))

    for voice_key, text in merged:
        speak(text, voice_key)


# =======================
# Generic Station UI
# =======================
# =======================
# Widget System (Core UI)
# =======================


class BaseWidget:
    """
    Optional interface. Factories may return any tkinter widget, but if it implements
    .on_update(payload), UI will forward updates.
    """
    def on_update(self, payload: Any) -> None:
        pass

    def on_close(self) -> None:
        pass


class TextViewerWidget(tk.Frame, BaseWidget):
    """
    Built-in widget: a scrollable read-only text viewer.
    Great for 'current post', 'current article', 'portfolio numbers', etc.
    """
    def __init__(self, parent, *, title: str = "", font=("Segoe UI", 11)):
        super().__init__(parent, bg="#0e0e0e")
        self._title = title

        self.text = tk.Text(self, wrap="word", bg="#121212", fg="#e8e8e8", font=font)
        self.text.pack(fill="both", expand=True)

        self.text.config(state="disabled")

    def set_text(self, s: str):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", (s or "").strip())
        self.text.config(state="disabled")

    def on_update(self, payload: Any) -> None:
        # Accept dict or str
        if isinstance(payload, dict):
            # Common pattern: {title, body, comment, ...}
            lines = []
            for k, v in payload.items():
                lines.append(f"{str(k).upper()}:\n{v}\n")
            self.set_text("\n".join(lines).strip())
        else:
            self.set_text(str(payload or ""))


class WidgetPanel(tk.Frame):
    """
    A resizable panel area containing multiple widgets as tabs.
    """
    def __init__(self, parent, *, name: str, registry: WidgetRegistry, ui_theme: Dict[str, str]):
        super().__init__(parent, bg=ui_theme.get("bg", "#0e0e0e"))
        self.name = name
        self.registry = registry
        self.UI = ui_theme

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

        # map tab_id -> widget instance
        self._tab_widgets: Dict[str, Any] = {}
        # map widget_key -> list[tab_id]
        self._widget_tabs: Dict[str, List[str]] = {}

    def current_tab_id(self) -> Optional[str]:
        try:
            return self.nb.select()
        except Exception:
            return None
    def all_widget_instances(self) -> List[Any]:
        return [w for w in self._tab_widgets.values() if w is not None]

    def add_widget(self, widget_key: str, runtime: Dict[str, Any], *, title: Optional[str] = None) -> bool:
        spec = self.registry.get(widget_key)
        if not spec:
            return False

        factory = spec["factory"]
        tab = tk.Frame(self.nb, bg=self.UI.get("panel", "#121212"))

        # Factory may return:
        # - a tk widget (Frame, Canvas, etc.) already parented to tab
        # - OR may return an object with .root attribute
        try:
            w = factory(tab, runtime)
        except TypeError:
            # Back-compat: factory(tab) only
            w = factory(tab)

        widget_instance = None
        if isinstance(w, tk.Widget):
            w.pack(fill="both", expand=True)
            widget_instance = w
        elif hasattr(w, "root") and isinstance(getattr(w, "root"), tk.Widget):
            w.root.pack(fill="both", expand=True)
            widget_instance = w
        else:
            # fall back: wrap text view showing repr
            tv = TextViewerWidget(tab, title=title or spec["title"])
            tv.pack(fill="both", expand=True)
            tv.set_text(f"(bad widget return type)\n\n{repr(w)}")
            widget_instance = tv

        tab_title = title or spec["title"]
        self.nb.add(tab, text=tab_title)

        tab_id = str(tab)
        self._tab_widgets[tab_id] = widget_instance
        self._widget_tabs.setdefault(spec["key"], []).append(tab_id)

        self.nb.select(tab)
        return True

    def remove_current_widget(self) -> bool:
        tab_id = self.current_tab_id()
        if not tab_id:
            return False

        w = self._tab_widgets.get(tab_id)
        try:
            if hasattr(w, "on_close"):
                w.on_close()
        except Exception:
            pass

        # remove from tracking
        for k, ids in list(self._widget_tabs.items()):
            if tab_id in ids:
                ids.remove(tab_id)
                if not ids:
                    self._widget_tabs.pop(k, None)

        self._tab_widgets.pop(tab_id, None)

        try:
            self.nb.forget(tab_id)
        except Exception:
            return False
        return True

    def widget_instances_by_key(self, widget_key: str) -> List[Any]:
        widget_key = (widget_key or "").strip().lower()
        out = []
        for tab_id in self._widget_tabs.get(widget_key, []) or []:
            w = self._tab_widgets.get(tab_id)
            if w is not None:
                out.append(w)
        return out

    def serialize_layout(self) -> Dict[str, Any]:
        # Just tab order + keys (best-effort)
        tabs = []
        for tab_id in self.nb.tabs():
            # find which widget_key owns this tab
            owner_key = None
            for k, ids in self._widget_tabs.items():
                if tab_id in ids:
                    owner_key = k
                    break
            tabs.append({
                "widget_key": owner_key,
                "title": self.nb.tab(tab_id, "text"),
            })
        return {"tabs": tabs}

    def restore_layout(self, layout: Dict[str, Any], runtime: Dict[str, Any]) -> None:
        # wipe existing
        for tab_id in list(self.nb.tabs()):
            try:
                self.nb.forget(tab_id)
            except Exception:
                pass
        self._tab_widgets.clear()
        self._widget_tabs.clear()

        for t in (layout or {}).get("tabs", []) or []:
            wk = (t.get("widget_key") or "").strip().lower()
            if wk and self.registry.get(wk):
                self.add_widget(wk, runtime, title=t.get("title"))


class FloatingWindow:
    """A draggable, resizable window container for widgets with tab support."""
    
    GRID_SIZE = 60  # Snap to 60px grid
    TITLE_HEIGHT = 30
    MIN_WIDTH = 200
    MIN_HEIGHT = 150
    
    def __init__(self, parent, window_id, title, x, y, width=400, height=300):
        self.parent = parent
        self.window_id = window_id
        self.title_text = title
        self.is_minimized = False
        self.z_order = 0
        self.geometry = {"x": x, "y": y, "width": width, "height": height}
        
        # Main frame (the window itself)
        self.frame = tk.Frame(parent, bg="#121212", relief="solid", bd=1, highlightthickness=1, highlightbackground="#2a2a2a")
        self.frame.place(x=x, y=y, width=width, height=height)
        
        # Title bar with icon and title
        self.title_bar = tk.Frame(self.frame, bg="#1a1a1a", height=self.TITLE_HEIGHT)
        self.title_bar.pack(fill="x", side="top")
        self.title_bar.pack_propagate(False)
        
        # Title text with icon placeholder
        title_lbl = tk.Label(self.title_bar, text=f"◆ {title}", bg="#1a1a1a", fg="#e8e8e8", 
                             font=("Segoe UI", 9, "bold"))
        title_lbl.pack(side="left", padx=8, pady=4)
        
        # Minimize button on title bar (callback will be bound by StationUI)
        self.min_btn = tk.Button(self.title_bar, text="−", command=self.minimize, 
                           bg="#1a1a1a", fg="#999", relief="flat", font=("Segoe UI", 10), 
                           width=2, padx=0)
        self.min_btn.pack(side="right", padx=2, pady=2)
        
        # Content area (holds tabs + widget content)
        self.content_frame = tk.Frame(self.frame, bg="#121212")
        self.content_frame.pack(fill="both", expand=True, side="top")
        
        # Tab bar for multiple widgets
        self.tab_bar = tk.Frame(self.content_frame, bg="#0e0e0e", height=24)
        self.tab_bar.pack(fill="x", side="top")
        self.tab_bar.pack_propagate(False)
        
        self.tabs = {}  # {widget_key: tab_label}
        self.widgets = {}  # {widget_key: widget_frame}
        self.active_tab = None
        
        # Widget display area
        self.widget_container = tk.Frame(self.content_frame, bg="#121212")
        self.widget_container.pack(fill="both", expand=True, side="top")
        
        # Resize handle (bottom-right corner) - place in frame with proper stacking
        self.resize_handle = tk.Label(self.frame, text="◢", bg="#121212", fg="#444", 
                                     font=("Segoe UI", 16), width=3, height=2)
        self.resize_handle.pack(side="bottom", anchor="se", padx=2, pady=2)
        self.resize_handle.lift()  # Ensure handle stays on top
        
        # Drag/resize state
        self._drag_data = {"x": 0, "y": 0}
        self._resize_data = {"x": 0, "y": 0}
        
        # Bind events
        self.title_bar.bind("<Button-1>", self._start_drag)
        self.title_bar.bind("<B1-Motion>", self._drag)
        self.title_bar.bind("<ButtonRelease-1>", self._end_drag)
        
        self.resize_handle.bind("<Button-1>", self._start_resize)
        self.resize_handle.bind("<B1-Motion>", self._resize)
        self.resize_handle.bind("<ButtonRelease-1>", self._end_resize)
    
    def _start_drag(self, event):
        self._drag_data["x"] = event.x_root - self.frame.winfo_x()
        self._drag_data["y"] = event.y_root - self.frame.winfo_y()
        self.frame.lift()
    
    def _drag(self, event):
        x = event.x_root - self._drag_data["x"]
        y = event.y_root - self._drag_data["y"]
        
        # Keep within parent bounds
        x = max(0, x)
        y = max(0, y)
        
        self.geometry["x"] = x
        self.geometry["y"] = y
        self.frame.place(x=x, y=y)
    
    def _end_drag(self, event):
        pass
    
    def _start_resize(self, event):
        self._resize_data["x"] = event.x_root
        self._resize_data["y"] = event.y_root
    
    def _resize(self, event):
        dx = event.x_root - self._resize_data["x"]
        dy = event.y_root - self._resize_data["y"]
        
        new_w = max(self.MIN_WIDTH, self.geometry["width"] + dx)
        new_h = max(self.MIN_HEIGHT, self.geometry["height"] + dy)
        
        self.geometry["width"] = new_w
        self.geometry["height"] = new_h
        self.frame.place(width=new_w, height=new_h)
        
        self._resize_data["x"] = event.x_root
        self._resize_data["y"] = event.y_root
    
    def _end_resize(self, event):
        pass
    
    def add_tab(self, widget_key, widget_frame, title):
        """Add a widget as a tab in this window."""
        # Create tab label
        tab = tk.Label(self.tab_bar, text=f"◆ {title}", bg="#1a1a1a", fg="#e8e8e8",
                      font=("Segoe UI", 8), padx=8, pady=3, relief="flat")
        tab.pack(side="left", padx=2, pady=2)
        
        # Make tab clickable to show widget
        tab.bind("<Button-1>", lambda e: self.show_tab(widget_key))
        
        self.tabs[widget_key] = tab
        self.widgets[widget_key] = widget_frame
        
        # Hide widget initially
        widget_frame.pack_forget()
        
        # Show first tab
        if self.active_tab is None:
            self.show_tab(widget_key)
    
    def show_tab(self, widget_key):
        """Display the specified tab's widget."""
        if self.active_tab and self.active_tab in self.widgets:
            self.widgets[self.active_tab].pack_forget()
            self.tabs[self.active_tab].configure(bg="#1a1a1a", fg="#999")
        
        self.active_tab = widget_key
        self.widgets[widget_key].pack(fill="both", expand=True)
        self.tabs[widget_key].configure(bg="#2a2a2a", fg="#4cc9f0")
    
    def minimize(self, on_minimize_callback=None):
        """Minimize this window to taskbar."""
        self.is_minimized = True
        self.frame.place_forget()
        if on_minimize_callback:
            on_minimize_callback(self.window_id)
    
    def restore(self):
        """Restore minimized window."""
        self.is_minimized = False
        self.frame.place(x=self.geometry["x"], y=self.geometry["y"], 
                        width=self.geometry["width"], height=self.geometry["height"])
        self.frame.lift()
    
    def serialize(self):
        """Save window state to dict."""
        return {
            "window_id": self.window_id,
            "geometry": self.geometry.copy(),
            "is_minimized": self.is_minimized,
            "active_tab": self.active_tab,
            "tabs": list(self.tabs.keys())
        }


class StationUI:
    def __init__(self, widget_registry: WidgetRegistry):
        self.widgets = widget_registry
        self._theme_editor_open = False  # Singleton check

        # =========================
        # LOAD ART / THEME FIRST
        # =========================

        DEFAULT_ART = {
            "global_bg": {"type": "color", "value": "#0e0e0e", "path": ""},
            "panels": {
                "left": {"type": "color", "value": "#121212"},
                "center": {"type": "color", "value": "#121212"},
                "right": {"type": "color", "value": "#121212"},
                "toolbar": {"type": "color", "value": "#0e0e0e"},
                "subtitle": {"type": "color", "value": "#0e0e0e"},
            },
            "accent": "#4cc9f0",
            "subtitle_wave": True
        }

        self.art = CFG.get("art") or DEFAULT_ART

        # ensure missing keys don’t crash UI
        for k, v in DEFAULT_ART.items():
            if k not in self.art:
                self.art[k] = v
        for p in DEFAULT_ART["panels"]:
            self.art["panels"].setdefault(p, DEFAULT_ART["panels"][p])

        # =========================
        # ROOT WINDOW
        # =========================

        self.root = tk.Tk()
        self.root.title(STATION_NAME)
        self.root.geometry("1400x820")

        bg = self.art["global_bg"]

        # Support 'video' type config, attempt load as image first (gifs works),
        # real mp4 support would require opencv/ffmpeg frame piping.
        if bg.get("type") in ["image", "video"] and bg.get("path"):
            try:
                self._bg_img = tk.PhotoImage(file=bg["path"])
                self._bg_lbl = tk.Label(self.root, image=self._bg_img, bd=0)
                self._bg_lbl.place(x=0, y=0, relwidth=1, relheight=1)
            except Exception as e:
                print(f"Background load failed ({bg.get('path')}): {e}")
                self.root.configure(bg=bg.get("value", "#0e0e0e"))
        else:
            self.root.configure(bg=bg.get("value", "#0e0e0e"))

        self.root.rowconfigure(0, weight=0)  # toolbar
        self.root.rowconfigure(1, weight=1)  # main panels
        self.root.rowconfigure(2, weight=0)  # subtitles
        self.root.columnconfigure(0, weight=1)
        
        # Bind window resize for GIF animation
        self.root.bind('<Configure>', self._on_window_resize)

        # =========================
        # TOOLBAR
        # =========================

        # self._build_toolbar() -> Deferred until after window_canvas init


        # =========================
        # FLOATING WINDOW CANVAS
        # =========================
        
        # Canvas container for floating windows (replaces main_paned)
        # Use the fallback color for now, background image is applied via root window label
        self.window_canvas = tk.Frame(self.root, bg=bg.get("value", "#0e0e0e"))
        self.window_canvas.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        
        # Window manager state
        self.floating_windows = {}  # {window_id: FloatingWindow}
        self.widget_panels = {}  # {window_id: WidgetPanel}
        
        # Create 3 default floating windows filling canvas area
        # Canvas is ~1400px wide, 600px tall (after toolbar)
        canvas_width = 1400
        canvas_height = 600
        window_width = canvas_width // 3  # ~466px each
        gap = 0  # No gaps for clean fill
        
        # Window 1 (left position)
        self._create_floating_window(
            "window_1", "Window 1", 
            x=0, y=0,
            width=window_width, height=canvas_height
        )
        
        # Window 2 (center position)
        self._create_floating_window(
            "window_2", "Window 2",
            x=window_width, y=0,
            width=window_width, height=canvas_height
        )
        
        # Window 3 (right position)
        self._create_floating_window(
            "window_3", "Window 3",
            x=window_width * 2, y=0,
            width=window_width, height=canvas_height
        )
        
        # Maintain backward compatibility references
        self.panel_left = self.widget_panels["window_1"]
        self.panel_center = self.widget_panels["window_2"]
        self.panel_right = self.widget_panels["window_3"]

        # =========================
        # TOOLBAR (Built deferred)
        # =========================
        # Must be built after canvas/windows exist because apply_art/load_layout depend on them
        self._build_toolbar()

        # =========================
        # DEFAULT WIDGETS
        # =========================

        self._install_builtin_widgets()

        # =========================
        # MINIMIZE TASKBAR (inside canvas at bottom, hidden by default)
        # =========================
        
        self.taskbar = tk.Frame(self.window_canvas, bg="#0a0a0a", height=40)
        self.taskbar.pack(side="bottom", fill="x")
        self.taskbar.pack_forget()  # Hidden initially
        
        self.taskbar_tabs = {}  # {window_id: tab_button}

        # =========================
        # SUBTITLE + WAVEFORM AREA
        # =========================

        sub_bg = self.art["panels"]["subtitle"].get("value", "#0e0e0e")

        bottom = tk.Frame(self.root, bg=sub_bg)
        bottom.grid(row=2, column=0, sticky="ew")

        bottom.columnconfigure(0, weight=1)
        bottom.columnconfigure(1, weight=0)

        self.sub_canvas = tk.Canvas(
            bottom,
            height=70,
            bg=sub_bg,
            highlightthickness=0
        )

        # self.sub_canvas.pack(fill="x", expand=True) # removed for grid

        def draw_rounded_rect(canvas, x1, y1, x2, y2, r, **kwargs):
            r = min(r, (x2 - x1) // 2, (y2 - y1) // 2)

            canvas.create_arc(x1, y1, x1+2*r, y1+2*r, start=90, extent=90, style="pieslice", **kwargs)
            canvas.create_arc(x2-2*r, y1, x2, y1+2*r, start=0, extent=90, style="pieslice", **kwargs)
            canvas.create_arc(x2-2*r, y2-2*r, x2, y2, start=270, extent=90, style="pieslice", **kwargs)
            canvas.create_arc(x1, y2-2*r, x1+2*r, y2, start=180, extent=90, style="pieslice", **kwargs)

            canvas.create_rectangle(x1+r, y1, x2-r, y2, **kwargs)
            canvas.create_rectangle(x1, y1+r, x2, y2-r, **kwargs)


        def redraw_sub_canvas(event=None):

            self.sub_canvas.delete("panel")

            w = self.sub_canvas.winfo_width()
            h = self.sub_canvas.winfo_height()

            # Draw panel background across full width
            draw_rounded_rect(
                self.sub_canvas,
                6, 6,
                w - 6, h - 6,
                r=18,
                fill=sub_bg,
                outline="",
                tags="panel"
            )

            self.sub_canvas.tag_lower("panel")

            # Center subtitle text across full width
            self.sub_canvas.coords(
                self.sub_label_window,
                w // 2,
                h // 2
            )

            self.sub_canvas.itemconfigure(
                self.sub_label_window,
                width=w - 20
            )



        self.sub_canvas.bind("<Configure>", redraw_sub_canvas)

        self.sub_canvas.grid(row=0, column=0, sticky="nsew")

        self.sub_label = tk.Label(
            self.sub_canvas,
            text="",
            font=("Segoe UI", 20),
            fg=self.art.get("text_color", "#e8e8e8"),
            bg=sub_bg,
            anchor="center",
            justify="center",
            relief="flat",
            highlightthickness=0,
            borderwidth=0
        )

        self.sub_label_window = self.sub_canvas.create_window(
            0, 0,
            anchor="center",
            window=self.sub_label
        )


        # subtitle engine state
        self._subtitle_max_chars = 120
        self._subtitle_last_text = ""
        self._subtitle_clear_job = None

        bottom.bind("<Configure>", self._resize_subtitle)

        # =========================
        # WAVEFORM ANIMATION
        # =========================

        # =========================
        # WAVEFORM ENGINE STATE
        # =========================

        self._wave_phase = 0
        self._wave_history = [0.0] * 120

        if self.art.get("subtitle_wave", True):
            self._animate_wave()


        # =========================
        # CONTROL BUTTONS
        # =========================

        btn_frame = tk.Frame(bottom, bg=sub_bg)
        btn_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        flush_btn = tk.Button(
            btn_frame,
            text="Flush Producer Queue",
            command=lambda: ui_cmd_q.put(("flush_queue", None)),
            bg="#2a2a2a",
            fg="#ffffff",
            relief="flat",
            padx=12,
            pady=6
        )
        flush_btn.pack(side="left", padx=12)

        # =========================
        # START UI LOOP
        # =========================

        self.root.after(40, self._poll_queues)


    # -----------------------
    # Toolbar
    # -----------------------
    def _build_toolbar(self):
        # Create background label for toolbar (supports gradients/images)
        toolbar_bg = self.art.get("panels", {}).get("toolbar", {}).get("value", "#0e0e0e")
        self._toolbar_bg_label = tk.Label(self.root, bg=toolbar_bg, bd=0)
        self._toolbar_bg_label.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        self._toolbar_bg_label.lower()
        
        bar = tk.Frame(self.root, bg=toolbar_bg)
        self._toolbar_frame = bar
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8,0))
        bar.columnconfigure(20, weight=1)

        # Helper to create styled toolbar buttons with hover effects
        def create_toolbar_button(parent, text, command, icon="", bg_color="#1e3a4d", fg_color="#4cc9f0", hover_bg="#2a4f65"):
            """Create a styled button with hover effects."""
            btn_text = f"{icon} {text}" if icon else text
            btn = tk.Button(
                parent, 
                text=btn_text,
                command=command,
                bg=bg_color, 
                fg=fg_color, 
                relief="solid",
                bd=1,
                font=("Segoe UI", 8),
                padx=8, 
                pady=4,
                activebackground=hover_bg,
                activeforeground=fg_color,
                highlightthickness=0,
                cursor="hand2"
            )
            
            # Add hover effects
            def on_enter(e):
                btn.configure(bg=hover_bg)
            
            def on_leave(e):
                btn.configure(bg=bg_color)
            
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            
            return btn

        tk.Label(bar, text="Panel:", bg="#0e0e0e", fg="#9a9a9a", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(6,6))

        self._panel_choice = tk.StringVar(value="1")
        panel_menu = ttk.Combobox(
            bar,
            textvariable=self._panel_choice,
            values=["1","2","3"],
            width=10,
            state="readonly"
        )
        panel_menu.pack(side="left", padx=(0,10))

        tk.Label(bar, text="Widget:", bg="#0e0e0e", fg="#9a9a9a", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0,6))

        self._widget_choice = tk.StringVar(value="")
        self._widget_menu = ttk.Combobox(
            bar,
            textvariable=self._widget_choice,
            values=self.widgets.keys(),
            width=17,
            state="readonly"
        )
        self._widget_menu.pack(side="left", padx=(0,10))

        # "Theme" - Purple
        create_toolbar_button(bar, "Theme…", self._open_theme_editor, "🎨", bg_color="#5e3c7d", fg_color="#e6d5f0", hover_bg="#704895").pack(side="left", padx=(0,8))
        
        # "Add Widget" - Green
        create_toolbar_button(bar, "Add Widget", self._ui_add_widget, "➕", bg_color="#2e5c3c", fg_color="#d0f0d0", hover_bg="#387049").pack(side="left", padx=(0,8))
        
        # "Remove Current" - Red
        create_toolbar_button(bar, "Remove Current", self._ui_remove_widget, "➖", bg_color="#7d2e2e", fg_color="#f0d0d0", hover_bg="#953838").pack(side="left", padx=(0,14))
        
        # "Save Layout" - Blue
        create_toolbar_button(bar, "Save Layout", lambda: ui_cmd_q.put(("save_ui_layout", None)), "💾", bg_color="#2e4a7d", fg_color="#d0e0f0", hover_bg="#385a95").pack(side="left", padx=(0,8))
        
        # "Load Layout" - Orangeish Brown
        create_toolbar_button(bar, "Load Layout", lambda: ui_cmd_q.put(("load_ui_layout", None)), "📂", bg_color="#7d5e2e", fg_color="#f0e6d0", hover_bg="#957038").pack(side="left", padx=(0,8))
        
        # "Reset Layout" - Teal
        create_toolbar_button(bar, "Reset Layout", lambda: ui_cmd_q.put(("reset_ui_layout", None)), "🔄", bg_color="#2e7d7d", fg_color="#d0f0f0", hover_bg="#389595").pack(side="left", padx=(0,8))
        
        # "Reset Windows" - Dark Grey
        create_toolbar_button(bar, "Reset Windows", self._reset_window_positions, "⊞", bg_color="#4a4a4a", fg_color="#ffffff", hover_bg="#5e5e5e").pack(side="left", padx=(0,12))
        
        # "Prompts" - Magenta
        create_toolbar_button(bar, "Prompts", self._open_prompts_editor, "📝", bg_color="#7d2e5e", fg_color="#f0d0e6", hover_bg="#953870").pack(side="left", padx=(0,12))


        # =====================================
        # 🎵 TOOLBAR WAVEFORM MINI PANEL
        # =====================================

        wave_frame = tk.Frame(
            bar,
            bg="#000000",
            highlightbackground="#2a2a2a",
            highlightthickness=1
        )
        wave_frame.pack(side="left", padx=(6,6))

        self.wave_canvas = tk.Canvas(
            wave_frame,
            width=160,
            height=36,
            bg="#000000",
            highlightthickness=0
        )
        self.wave_canvas.pack(padx=4, pady=4)
        
        # Auto-load layout from manifest on startup
        try:
            self._load_layout_file()
        except Exception as e:
            log("ui", f"Failed to auto-load layout: {e}")
        
        # Apply art/theme from manifest on startup
        try:
            self.apply_art()
        except Exception as e:
            log("ui", f"Failed to apply theme on startup: {e}")

    def _open_theme_editor(self):
        """
        Advanced Theme Editor: Colors, Gradients, Wallpapers (Images/GIFs/MP4s), with live previews.
        Only one instance allowed at a time (singleton).
        """
        try:
            log("ui", "Theme editor opening...")
            self._open_theme_editor_impl()
            log("ui", "Theme editor opened successfully")
        except Exception as e:
            import traceback
            log("ui", f"CRITICAL: Theme editor failed: {type(e).__name__}: {e}")
            log("ui", f"Traceback: {traceback.format_exc()}")
            self._theme_editor_open = False

    def _open_theme_editor_impl(self):
        if self._theme_editor_open:
            return  # Theme editor already open
        
        self._theme_editor_open = True
        
        win = tk.Toplevel(self.root)
        win.title("Station Theme Editor")
        win.geometry("750x900")
        win.configure(bg="#121212")
        # Keep theme editor on top of runtime window
        win.attributes('-topmost', True)
        
        # Clean up singleton flag on close
        def on_close():
            self._theme_editor_open = False
            win.destroy()
        
        win.protocol("WM_DELETE_WINDOW", on_close)

        # Work directly with self.art to show live values (not a deep copy)
        import copy

        # Scrollable container
        canvas = tk.Canvas(win, bg="#121212", highlightthickness=0)
        scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#121212")

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Mouse wheel scrolling support
        def _on_mousewheel(event):
            """Handle mouse wheel scrolling on Windows and Linux."""
            if event.num == 5 or event.delta < 0:  # Scroll down
                canvas.yview_scroll(3, "units")
            elif event.num == 4 or event.delta > 0:  # Scroll up
                canvas.yview_scroll(-3, "units")

        # Bind mouse wheel events
        canvas.bind("<MouseWheel>", _on_mousewheel)  # Windows
        canvas.bind("<Button-4>", _on_mousewheel)    # Linux scroll up
        canvas.bind("<Button-5>", _on_mousewheel)    # Linux scroll down
        scroll_frame.bind("<MouseWheel>", _on_mousewheel)  # Windows (on frame)
        scroll_frame.bind("<Button-4>", _on_mousewheel)    # Linux scroll up (on frame)
        scroll_frame.bind("<Button-5>", _on_mousewheel)    # Linux scroll down (on frame)

        def section_lbl(txt):
            tk.Label(scroll_frame, text=txt, bg="#121212", fg="#4cc9f0", 
                     font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(15, 5))

        def make_preview_swatch(parent, size=60):
            """Create a preview label that can display colors, gradients, or images."""
            swatch = tk.Label(parent, width=size, height=3, relief="sunken", bd=2, bg="#1a1a1a")
            return swatch

        def make_color_row(parent, label, get_fn, set_fn, show_preview=True):
            """Enhanced color row with large preview swatch."""
            row = tk.Frame(parent, bg="#1a1a1a", relief="groove", bd=1)
            row.pack(fill="x", padx=12, pady=6, ipady=6)
            
            tk.Label(row, text=label, bg="#1a1a1a", fg="#4cc9f0", width=16, anchor="w", 
                     font=("Segoe UI", 9, "bold")).pack(side="left", padx=10)
            
            curr = get_fn()
            
            # Large swatch preview
            if show_preview:
                swatch = tk.Label(row, width=8, height=2, relief="sunken", bd=2, bg=curr)
                swatch.pack(side="left", padx=8)
            else:
                swatch = None
            
            # Hex entry
            var = tk.StringVar(value=curr)
            ent = tk.Entry(row, textvariable=var, bg="#1e1e1e", fg="#e8e8e8", width=10, relief="flat")
            ent.pack(side="left", padx=5)

            def on_pick():
                try:
                    c = colorchooser.askcolor(color=var.get(), title=f"Choose {label}", parent=win)
                    if c and c[1]:
                        var.set(c[1])
                        if swatch:
                            swatch.configure(bg=c[1])
                        set_fn(c[1])
                except Exception as e:
                    log("ui", f"Color picker error: {type(e).__name__}: {e}")
                try:
                    win.lift()  # Bring theme editor back to front
                    win.attributes('-topmost', True)  # Keep it topmost
                except:
                    pass

            tk.Button(row, text="Pick", command=on_pick, bg="#2a2a2a", fg="#ffffff", 
                      relief="flat", font=("Segoe UI", 8), padx=8).pack(side="left", padx=2)
            
            # Update on focus out to prevent keystroke race conditions
            def on_focus_out(event):
                try:
                    set_fn(var.get())
                    if swatch:
                        swatch.configure(bg=var.get())
                except:
                    pass
            
            ent.bind("<FocusOut>", on_focus_out)
            return swatch

        def make_gradient_editor(parent, label, get_fn, set_fn):
            """Create a gradient editor UI with two color pickers."""
            container = tk.Frame(parent, bg="#121212")
            container.pack(fill="x", padx=15, pady=8)
            
            tk.Label(container, text=label, bg="#121212", fg="#e8e8e8", 
                     font=("Segoe UI", 9, "bold")).pack(anchor="w")
            
            grad_type = tk.StringVar(value=get_fn().get("type", "linear"))
            
            type_frame = tk.Frame(container, bg="#121212")
            type_frame.pack(fill="x", padx=10, pady=3)
            
            tk.Label(type_frame, text="Type:", bg="#121212", fg="#e8e8e8").pack(side="left")
            for gtype in ["linear", "radial"]:
                tk.Radiobutton(type_frame, text=gtype.title(), variable=grad_type, 
                               value=gtype, bg="#121212", fg="#e8e8e8", 
                               selectcolor="#2a2a2a", activebackground="#121212").pack(side="left", padx=5)
            
            colors_frame = tk.Frame(container, bg="#121212")
            colors_frame.pack(fill="x", padx=10, pady=5)
            
            gradient_data = get_fn()
            c1_val = gradient_data.get("color1") or "#0e0e0e"
            c2_val = gradient_data.get("color2") or "#1e1e1e"
            
            # Validate color format
            if not c1_val or not isinstance(c1_val, str) or len(c1_val) < 4:
                log("ui", f"Gradient editor: Invalid color1 from get_fn(): {repr(c1_val)}, using default")
                c1_val = "#0e0e0e"
            if not c2_val or not isinstance(c2_val, str) or len(c2_val) < 4:
                log("ui", f"Gradient editor: Invalid color2 from get_fn(): {repr(c2_val)}, using default")
                c2_val = "#1e1e1e"
            
            c1_var = tk.StringVar(value=c1_val)
            c2_var = tk.StringVar(value=c2_val)
            
            # Color 1
            tk.Label(colors_frame, text="From:", bg="#121212", fg="#e8e8e8", width=8).pack(side="left")
            c1_swatch = tk.Label(colors_frame, width=6, height=1, relief="sunken", bd=2, bg=c1_var.get())
            c1_swatch.pack(side="left", padx=5)
            
            def pick_c1():
                c = colorchooser.askcolor(color=c1_var.get(), title="Gradient Start Color", parent=win)
                if c and c[1]:
                    c1_var.set(c[1])
                    c1_swatch.configure(bg=c[1])
                    update_gradient()
                win.lift()  # Bring theme editor back to front
                win.attributes('-topmost', True)
            
            tk.Button(colors_frame, text="Pick", command=pick_c1, bg="#2a2a2a", 
                      fg="#fff", relief="flat", font=("Segoe UI", 8), padx=6).pack(side="left")
            
            # Color 2
            tk.Label(colors_frame, text="To:", bg="#121212", fg="#e8e8e8", width=8).pack(side="left", padx=(20,0))
            c2_swatch = tk.Label(colors_frame, width=6, height=1, relief="sunken", bd=2, bg=c2_var.get())
            c2_swatch.pack(side="left", padx=5)
            
            def pick_c2():
                c = colorchooser.askcolor(color=c2_var.get(), title="Gradient End Color", parent=win)
                if c and c[1]:
                    c2_var.set(c[1])
                    c2_swatch.configure(bg=c[1])
                    update_gradient()
                win.lift()  # Bring theme editor back to front
                win.attributes('-topmost', True)
            
            tk.Button(colors_frame, text="Pick", command=pick_c2, bg="#2a2a2a", 
                      fg="#fff", relief="flat", font=("Segoe UI", 8), padx=6).pack(side="left")
            
            # Gradient preview
            preview_frame = tk.Frame(container, bg="#121212", height=40)
            preview_frame.pack(fill="x", padx=10, pady=8)
            preview_canvas = tk.Canvas(preview_frame, bg="#1a1a1a", height=40, 
                                      highlightthickness=1, highlightbackground="#2a2a2a")
            preview_canvas.pack(fill="x")
            
            def update_gradient():
                c1_current = c1_var.get()
                c2_current = c2_var.get()
                
                # Validate before updating
                if not c1_current or len(c1_current) < 4:
                    log("ui", f"Gradient editor: update_gradient - c1_var is invalid: {repr(c1_current)}")
                    c1_current = "#0e0e0e"
                    c1_var.set(c1_current)
                if not c2_current or len(c2_current) < 4:
                    log("ui", f"Gradient editor: update_gradient - c2_var is invalid: {repr(c2_current)}")
                    c2_current = "#1e1e1e"
                    c2_var.set(c2_current)
                
                new_grad = {
                    "type": grad_type.get(),
                    "color1": c1_current,
                    "color2": c2_current
                }
                set_fn(new_grad)
                draw_gradient_preview()
            
            def draw_gradient_preview():
                try:
                    w = preview_canvas.winfo_width()
                    if w <= 1: w = 300
                    
                    if HAS_PIL:
                        # Create gradient image using PIL
                        try:
                            from PIL import Image as PILImage, ImageDraw as PILDraw, ImageTk as PILImageTk
                            
                            img = PILImage.new("RGB", (w, 40))
                            draw = PILDraw.Draw(img)
                            
                            c1_rgb = tuple(int(c1_var.get().lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
                            c2_rgb = tuple(int(c2_var.get().lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
                            
                            if grad_type.get() == "linear":
                                for x in range(w):
                                    ratio = x / max(w, 1)
                                    r = int(c1_rgb[0] * (1 - ratio) + c2_rgb[0] * ratio)
                                    g = int(c1_rgb[1] * (1 - ratio) + c2_rgb[1] * ratio)
                                    b = int(c1_rgb[2] * (1 - ratio) + c2_rgb[2] * ratio)
                                    draw.line([(x, 0), (x, 40)], fill=(r, g, b))
                            
                            preview_canvas._grad_img = PILImageTk.PhotoImage(img)
                            preview_canvas.create_image(0, 0, image=preview_canvas._grad_img, anchor="nw")
                        except Exception as e:
                            log("ui", f"Gradient preview failed: {e}")
                except Exception:
                    pass
            
            preview_canvas.bind("<Configure>", lambda e: draw_gradient_preview())
            draw_gradient_preview()
            
            grad_type.trace_add("write", lambda *a: update_gradient())
            c1_var.trace_add("write", lambda *a: draw_gradient_preview())
            c2_var.trace_add("write", lambda *a: draw_gradient_preview())

        def make_media_row(parent, label, get_fn, set_fn, media_types=["color", "image", "gradient"]):
            """Create unified media editor - pick ONE type, show relevant controls."""
            import copy
            
            container = tk.Frame(parent, bg="#121212")
            container.pack(fill="x", padx=15, pady=8)
            
            tk.Label(container, text=label, bg="#121212", fg="#e8e8e8", 
                     font=("Segoe UI", 9, "bold")).pack(anchor="w")
            
            # Get current config from backing storage
            current_cfg = copy.deepcopy(get_fn())
            media_type = tk.StringVar(value=current_cfg.get("type", "color"))
            
            # Type selector radio buttons - ALL on one line
            type_frame = tk.Frame(container, bg="#121212")
            type_frame.pack(fill="x", anchor="w", padx=10, pady=5)
            
            # Options frame (will be cleared and repopulated based on type selection)
            opts_frame = tk.Frame(container, bg="#121212")
            opts_frame.pack(fill="x", padx=10, pady=5)
            
            # Define refresh_media BEFORE using it in radio buttons
            def refresh_media():
                # Clear all option controls
                for w in opts_frame.winfo_children(): 
                    w.destroy()
                
                t = media_type.get()
                # Always fetch FRESH from backing storage
                cfg = copy.deepcopy(get_fn())
                
                # Update type in config
                cfg["type"] = t
                
                # CLEAR all other type data when switching types
                if t == "color":
                    cfg = {"type": "color", "value": cfg.get("value", "#121212")}
                elif t == "gradient":
                    cfg = {"type": "gradient", "gradient": cfg.get("gradient", {"type": "linear", "color1": "#121212", "color2": "#1e1e1e"})}
                elif t == "image":
                    cfg = {"type": "image", "path": cfg.get("path", "")}
                
                # Persist the type change immediately
                set_fn(cfg)
                
                if t == "color":
                    color_val = [cfg.get("value", "#121212")]  # mutable container to track changes
                    
                    def get_color():
                        return color_val[0]
                    
                    def set_color(v):
                        color_val[0] = v
                        cfg["value"] = v
                        set_fn(cfg)
                    
                    make_color_row(
                        opts_frame, "Color", 
                        get_color, set_color,
                        show_preview=True
                    )
                
                elif t == "gradient":
                    grad_data = [cfg.get("gradient", {"type": "linear", "color1": "#121212", "color2": "#1e1e1e"})]
                    
                    def get_grad():
                        return grad_data[0]
                    
                    def set_grad(v):
                        grad_data[0] = v
                        cfg["gradient"] = v
                        set_fn(cfg)
                    
                    make_gradient_editor(
                        opts_frame, "Gradient Settings", 
                        get_grad, set_grad
                    )
                
                elif t == "image":
                    path_val = [cfg.get("path", "")]
                    
                    img_row = tk.Frame(opts_frame, bg="#121212")
                    img_row.pack(fill="x", padx=5, pady=3)
                    
                    path_var = tk.StringVar(value=path_val[0])
                    tk.Entry(img_row, textvariable=path_var, bg="#1e1e1e", fg="#e8e8e8", 
                             font=("Segoe UI", 8)).pack(side="left", fill="x", expand=True, padx=5)
                    
                    def on_path_change(*args):
                        """Update on entry change"""
                        new_path = path_var.get()
                        path_val[0] = new_path
                        cfg["path"] = new_path
                        set_fn(cfg)
                    
                    path_var.trace_add("write", on_path_change)
                    
                    def browse_img():
                        try:
                            f = filedialog.askopenfilename(
                                parent=win,
                                title=f"Select {label} Image",
                                filetypes=[("Images", "*.png *.jpg *.jpeg *.gif"), ("All", "*.*")]
                            )
                            if f:
                                path_var.set(f)
                                path_val[0] = f
                                cfg["path"] = f
                                set_fn(cfg)
                        except Exception as e:
                            log("ui", f"Image browse error: {type(e).__name__}: {e}")
                        try:
                            win.lift()
                            win.attributes('-topmost', True)
                        except:
                            pass
                    
                    tk.Button(img_row, text="Browse", command=browse_img, bg="#2a2a2a", 
                              fg="#fff", relief="flat", font=("Segoe UI", 8), padx=8).pack(side="left", padx=5)
                    
                    # Preview
                    preview_lbl = tk.Label(opts_frame, bg="#1a1a1a", width=40, height=3, 
                                          text="[Image Preview]", fg="#666")
                    preview_lbl.pack(fill="x", padx=5, pady=5)
                    
                    if path_val[0] and os.path.exists(path_val[0]):
                        try:
                            if HAS_PIL:
                                from PIL import Image as PILImage, ImageTk as PILImageTk
                                img = PILImage.open(path_val[0])
                                img.thumbnail((200, 60))
                                preview_lbl._img = PILImageTk.PhotoImage(img)
                                preview_lbl.configure(image=preview_lbl._img, text="")
                        except Exception as e:
                            log("ui", f"Preview image load error: {type(e).__name__}: {e}")
                            preview_lbl.configure(text=f"Preview error: {str(e)[:30]}")
            
            # Create radio buttons + Clear button
            btn_row = tk.Frame(type_frame, bg="#121212")
            btn_row.pack(fill="x", side="left", expand=True, padx=0, pady=0)
            
            for mtype in media_types:
                tk.Radiobutton(btn_row, text=mtype.title(), variable=media_type, 
                               value=mtype, bg="#121212", fg="#e8e8e8", 
                               selectcolor="#2a2a2a", activebackground="#121212",
                               command=refresh_media).pack(side="left", padx=3)
            
            def clear_media():
                """Clear the current tab's data and refresh UI."""
                current_type = media_type.get()
                
                # Build cleared config
                if current_type == "color":
                    cleared_cfg = {"type": "color", "value": "#0e0e0e"}
                elif current_type == "gradient":
                    cleared_cfg = {"type": "gradient", "gradient": {"type": "linear", "color1": "#0e0e0e", "color2": "#1e1e1e"}}
                elif current_type == "image":
                    cleared_cfg = {"type": "image", "path": ""}
                else:
                    cleared_cfg = {"type": "color", "value": "#0e0e0e"}
                
                # Update backing storage
                set_fn(cleared_cfg)
                
                log("ui", f"Cleared {current_type} for {label}")
                
                # Refresh UI
                refresh_media()
            
            tk.Button(btn_row, text="Clear", command=clear_media, bg="#666", fg="#fff",
                     relief="flat", font=("Segoe UI", 8), padx=6).pack(side="right", padx=3)
            
            # Initial population
            refresh_media()

        # --- SECTIONS ---

        # 1. GLOBAL BACKGROUND (Canvas Area)
        section_lbl("🎨 Canvas Background / Wallpaper")
        tk.Label(scroll_frame, text="Supports: Colors, Gradients, Images (PNG/JPG/GIF)", 
                 bg="#121212", fg="#9a9a9a", font=("Segoe UI", 8)).pack(anchor="w", padx=15)
        
        g_bg = self.art.setdefault("global_bg", {})
        make_media_row(scroll_frame, "Background", 
                      lambda: copy.deepcopy(g_bg), 
                      lambda v: g_bg.update(v),
                      media_types=["color", "image", "gradient"])

        # 2. WIDGET PANELS STYLING (left, center, right)
        section_lbl("📌 Widget Panels")
        
        panels = self.art.setdefault("panels", {})
        
        for p in ["left", "center", "right"]:
            if p not in panels: panels[p] = {"type": "color", "value": "#121212"}
            
            make_media_row(scroll_frame, f"{p.title()} Panel", 
                          lambda p=p: copy.deepcopy(panels.get(p, {"type": "color", "value": "#121212"})),
                          lambda v, p=p: panels[p].update(v),
                          media_types=["color", "gradient", "image"])

        # 3. TOOLBAR & SUBTITLE STYLING
        section_lbl("🎴 UI Panel Styling")
        
        for p in ["toolbar", "subtitle"]:
            if p not in panels: panels[p] = {"type": "color", "value": "#121212"}
            
            make_media_row(scroll_frame, f"{p.title()} Panel", 
                          lambda p=p: copy.deepcopy(panels.get(p, {"type": "color", "value": "#121212"})),
                          lambda v, p=p: panels[p].update(v),
                          media_types=["color", "gradient", "image"])

        # 4. TEXT & ACCENT COLORS
        section_lbl("✨ Text & Accent Colors")
        
        make_color_row(scroll_frame, "Accent Color", 
                      lambda: self.art.get("accent", "#4cc9f0"), 
                      lambda v: self.art.update({"accent": v}),
                      show_preview=True)
        
        make_color_row(scroll_frame, "Text Color", 
                      lambda: self.art.get("text_color", "#e8e8e8"), 
                      lambda v: self.art.update({"text_color": v}),
                      show_preview=True)

        # SAVE + RESET BUTTONS
        btn_frame = tk.Frame(win, bg="#121212", pady=20)
        btn_frame.pack(fill="x", side="bottom")

        def save():
            # self.art is already updated live, just save manifest
            CFG["art"] = self.art
            save_station_manifest(CFG)
            
            # Apply immediately
            self.apply_art()
            
            log("ui", "Theme saved and applied!")
            self._theme_editor_open = False
            win.destroy()

        def reset_to_default():
            if messagebox.askyesno("Reset Theme", "Reset to plain default theme?\n\nThe application will restart to apply changes."):
                # Restore DEFAULT_ART
                DEFAULT_ART = {
                    "global_bg": {"type": "color", "value": "#0e0e0e", "path": ""},
                    "panels": {
                        "left": {"bg": "#121212"},
                        "center": {"bg": "#121212"},
                        "right": {"bg": "#121212"},
                        "toolbar": {"bg": "#0e0e0e"},
                        "subtitle": {"bg": "#0e0e0e"},
                    },
                    "accent": "#4cc9f0",
                    "subtitle_wave": True
                }
                self.art.clear()
                self.art.update(DEFAULT_ART)
                CFG["art"] = self.art
                save_station_manifest(CFG)
                
                # Close editor and restart app
                win.destroy()
                self.root.destroy()
                
                # Restart
                import subprocess
                import sys
                subprocess.Popen([sys.executable] + sys.argv)

        tk.Button(btn_frame, text="Save & Apply", command=save, 
                  bg="#4cc9f0", fg="#000000", font=("Segoe UI", 10, "bold"), 
                  padx=20, pady=8).pack(side="left", padx=5)
        
        tk.Button(btn_frame, text="Reset to Default", command=reset_to_default,
                  bg="#666666", fg="#ffffff", font=("Segoe UI", 10),
                  padx=20, pady=8).pack(side="left", padx=5)


    
    def _open_prompts_editor(self):
        win = tk.Toplevel(self.root)
        win.title("LLM Prompts")
        win.geometry("900x700")
        win.configure(bg="#121212")

        # Access mem
        mem = getattr(self, "mem", None)
        if mem is None:
            tk.Label(win, text="Memory not linked - cannot edit.", bg="#121212", fg="#ff4d6d").pack()
            return

        # Container
        container = tk.Frame(win, bg="#121212")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        # Left Listbox
        left = tk.Frame(container, bg="#121212", width=200)
        left.pack(side="left", fill="y", padx=(0,10))
        
        entry_list = tk.Listbox(left, bg="#1e1e1e", fg="#e8e8e8", borderwidth=0, highlightthickness=0, font=("Segoe UI", 10))
        entry_list.pack(fill="both", expand=True)

        # Right Editor
        right = tk.Frame(container, bg="#121212")
        right.pack(side="left", fill="both", expand=True)

        text_area = tk.Text(right, bg="#1e1e1e", fg="#e8e8e8", insertbackground="white", font=("Consolas", 10), borderwidth=0, wrap="word")
        text_area.pack(fill="both", expand=True)

        # Populate
        all_keys = sorted(DEFAULT_PROMPTS.keys())
        for k in all_keys:
            entry_list.insert("end", k)

        current_key = None

        def load_selected(event=None):
            nonlocal current_key
            sel = entry_list.curselection()
            if not sel:
                return
            key = entry_list.get(sel[0])
            current_key = key
            
            # Get current value (manifest > memory > default)
            val = None
            
            # 1. Manifest
            prompts_cfg = CFG.get("prompts", {})
            if isinstance(prompts_cfg, dict):
                val = prompts_cfg.get(key)

            # 2. Legacy memory
            if val is None:
                cust = mem.get("custom_prompts", {})
                val = cust.get(key)

            # 3. Default
            if val is None:
                val = DEFAULT_PROMPTS.get(key, "")
            
            text_area.delete("1.0", "end")
            text_area.insert("1.0", val)

        entry_list.bind("<<ListboxSelect>>", load_selected)

        # Buttons
        bar = tk.Frame(win, bg="#121212")
        bar.pack(fill="x", padx=10, pady=(0, 10))

        def save():
            if not current_key:
                return
            new_val = text_area.get("1.0", "end-1c") # strip trailing newline
            
            # Save to manifest
            cust = CFG.setdefault("prompts", {})
            cust[current_key] = new_val
            save_station_manifest(CFG)
            
            tk.messagebox.showinfo("Saved", f"Updated {current_key} in manifest.yaml")

        def reset():
            if not current_key:
                return
            if tk.messagebox.askyesno("Reset", f"Reset {current_key} to default?"):
                # Remove from manifest
                cust = CFG.get("prompts", {})
                if current_key in cust:
                    del cust[current_key]
                    save_station_manifest(CFG)
                
                # Remove from legacy memory (cleanup)
                mem_cust = mem.get("custom_prompts", {})
                if current_key in mem_cust:
                    del mem_cust[current_key]
                    save_memory(mem)
                
                load_selected() # Reload default

        tk.Button(bar, text="Save Prompt", command=save, bg="#2a2a2a", fg="white", relief="flat", padx=12, pady=6).pack(side="right", padx=5)
        tk.Button(bar, text="Reset to Default", command=reset, bg="#2a2a2a", fg="white", relief="flat", padx=12, pady=6).pack(side="right", padx=5)
        
        # Load first if exists
        if all_keys:
            entry_list.select_set(0)
            load_selected()

    def _panel_obj(self, name: str) -> WidgetPanel:
        name = (name or "").strip()
        if name == "2":
            return self.panel_center
        if name == "3":
            return self.panel_right
        return self.panel_left
    def _resize_subtitle(self, e):

        usable_width = int(e.width * 0.66)

        try:
            self._subtitle_max_chars = max(int(usable_width / 12), 40)
        except Exception:
            self._subtitle_max_chars = 120



    def _ui_add_widget(self):
        panel = self._panel_obj(self._panel_choice.get())
        wk = (self._widget_choice.get() or "").strip().lower()
        if not wk:
            return
        runtime = self._runtime_for_ui()
        ok = panel.add_widget(wk, runtime)
        if ok:
            # refresh menu options in case plugins registered after UI launch (rare)
            self._widget_menu.configure(values=self.widgets.keys())

    def _ui_remove_widget(self):
        panel = self._panel_obj(self._panel_choice.get())
        panel.remove_current_widget()
    def _on_window_resize(self, event=None):
        """Reload background when window resizes (animated GIF or static image)."""
        # Throttle resize events to avoid excessive redraws
        if hasattr(self, '_resize_job'):
            self.root.after_cancel(self._resize_job)
        
        def do_resize():
            # Check if we have a background to resize
            has_frames = hasattr(self, '_canvas_bg_frames') and self._canvas_bg_frames
            has_static = hasattr(self, '_canvas_bg_img')
            
            if has_frames or has_static:
                try:
                    path = getattr(self, '_current_bg_path', None)
                    if path:
                        self.apply_art()  # Reload and rescale the background
                except Exception as e:
                    log("ui", f"Background resize error: {e}")
        
        self._resize_job = self.root.after(300, do_resize)  # Throttle to 300ms

    def _animate_canvas_bg(self):
        """Animate canvas background if it's an animated GIF."""
        if not hasattr(self, '_canvas_bg_frames') or not self._canvas_bg_frames:
            return
        
        # Pause animation when window is minimized/hidden
        if not self.root.winfo_viewable():
            self.root.after(500, self._animate_canvas_bg)
            return
        
        try:
            from PIL import ImageTk as PILImageTk
            
            frames = self._canvas_bg_frames
            idx = self._canvas_bg_frame_idx
            duration = self._canvas_bg_durations[idx]
            
            # Convert current frame to PhotoImage (frames already pre-converted to RGB)
            photo = PILImageTk.PhotoImage(frames[idx])
            self._canvas_bg_photo = photo  # Keep reference
            self._canvas_bg_lbl.configure(image=photo)
            
            # Move to next frame
            self._canvas_bg_frame_idx = (idx + 1) % len(frames)
            
            # Schedule next frame update
            delay = max(duration, 16)  # Min 16ms (~60fps)
            self.root.after(delay, self._animate_canvas_bg)
        except Exception as e:
            log("ui", f"GIF animation error: {e}")

    def apply_art(self):
        """
        Live-apply CFG['art'] to:
        - root background (color, image, gradient, or video)
        - panel backgrounds (color, image, or gradient)
        - toolbar + subtitle backgrounds
        - waveform accent
        Supports: PNG, JPG, GIF, MP4 for wallpapers; colors and gradients for all elements.
        """
        art = self.art or {}
        panels = art.get("panels") or {}

        def _apply_bg_to_widget(widget, cfg, fallback_color="#0e0e0e"):
            """Apply a background configuration (color/image/gradient) to a widget."""
            if not cfg:
                widget.configure(bg=fallback_color)
                return
            
            cfg_type = cfg.get("type", "color")
            
            if cfg_type == "color":
                try:
                    value = cfg.get("value", fallback_color)
                    if value:  # Only apply if value is not empty
                        widget.configure(bg=value)
                    else:
                        widget.configure(bg=fallback_color)
                except Exception:
                    widget.configure(bg=fallback_color)
            
            elif cfg_type == "image" and cfg.get("path"):
                # Images can only be applied to Label widgets
                if not isinstance(widget, tk.Label):
                    widget.configure(bg=fallback_color)
                    return
                
                try:
                    path = cfg["path"]
                    if not os.path.exists(path):
                        widget.configure(bg=fallback_color)
                        return
                    
                    if HAS_PIL:
                        from PIL import Image as PILImage, ImageTk as PILImageTk
                        img = PILImage.open(path)
                        img.thumbnail((1920, 1080))
                        widget._img_obj = img  # Keep reference
                        photo = PILImageTk.PhotoImage(img)
                        widget._photo = photo
                        widget.configure(image=photo)
                    else:
                        # Fall back to tkinter PhotoImage
                        widget._bg_img = tk.PhotoImage(file=path)
                        widget.configure(image=widget._bg_img)
                except Exception as e:
                    log("ui", f"Apply image bg failed: {type(e).__name__}: {e}")
                    widget.configure(bg=fallback_color)
            
            elif cfg_type == "gradient" and cfg.get("gradient"):
                # Gradients can only be applied to Label widgets
                if not isinstance(widget, tk.Label):
                    widget.configure(bg=fallback_color)
                    return
                
                try:
                    if HAS_PIL:
                        from PIL import Image as PILImage, ImageDraw as PILDraw, ImageTk as PILImageTk
                        
                        grad = cfg["gradient"]
                        w = widget.winfo_width() or 400
                        h = widget.winfo_height() or 100
                        
                        if w <= 1: w = 400
                        if h <= 1: h = 100
                        
                        img = PILImage.new("RGB", (w, h))
                        draw = PILDraw.Draw(img)
                        
                        # Validate and extract color values with defaults
                        c1_val = grad.get("color1", "#121212")
                        c2_val = grad.get("color2", "#1e1e1e")
                        
                        # Ensure colors are valid hex strings
                        if not c1_val or not isinstance(c1_val, str):
                            c1_val = "#121212"
                        if not c2_val or not isinstance(c2_val, str):
                            c2_val = "#1e1e1e"
                        
                        c1_str = c1_val.lstrip('#') or "121212"
                        c2_str = c2_val.lstrip('#') or "1e1e1e"
                        
                        # Validate hex format (must be 6 chars)
                        if len(c1_str) != 6:
                            c1_str = "121212"
                        if len(c2_str) != 6:
                            c2_str = "1e1e1e"
                        
                        try:
                            c1_rgb = tuple(int(c1_str[i:i+2], 16) for i in (0, 2, 4))
                            c2_rgb = tuple(int(c2_str[i:i+2], 16) for i in (0, 2, 4))
                        except ValueError:
                            # Invalid hex, use defaults
                            c1_rgb = (0x12, 0x12, 0x12)
                            c2_rgb = (0x1e, 0x1e, 0x1e)
                        
                        if grad.get("type") == "radial":
                            # Simple radial: center fades outward
                            cx, cy = w // 2, h // 2
                            max_dist = ((w // 2) ** 2 + (h // 2) ** 2) ** 0.5
                            for y in range(h):
                                for x in range(w):
                                    dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                                    ratio = min(dist / max_dist, 1.0)
                                    r = int(c1_rgb[0] * (1 - ratio) + c2_rgb[0] * ratio)
                                    g = int(c1_rgb[1] * (1 - ratio) + c2_rgb[1] * ratio)
                                    b = int(c1_rgb[2] * (1 - ratio) + c2_rgb[2] * ratio)
                                    draw.point((x, y), fill=(r, g, b))
                        else:
                            # Linear: left to right
                            for x in range(w):
                                ratio = x / max(w, 1)
                                r = int(c1_rgb[0] * (1 - ratio) + c2_rgb[0] * ratio)
                                g = int(c1_rgb[1] * (1 - ratio) + c2_rgb[1] * ratio)
                                b = int(c1_rgb[2] * (1 - ratio) + c2_rgb[2] * ratio)
                                draw.line([(x, 0), (x, h)], fill=(r, g, b))
                        
                        photo = PILImageTk.PhotoImage(img)
                        widget._gradient = photo
                        widget.configure(image=photo)
                    else:
                        widget.configure(bg=cfg.get("gradient", {}).get("color1", fallback_color))
                except Exception as e:
                    log("ui", f"Apply gradient failed: {type(e).__name__}: {e}")
                    widget.configure(bg=fallback_color)
            
            else:
                # Fallback to color
                widget.configure(bg=fallback_color)

        # ---- Window Canvas background (color, image, gradient) - this is the primary wallpaper area
        bg = art.get("global_bg") or {}
        
        # First, apply color/gradient/image to the canvas
        if bg.get("type") == "color":
            self.window_canvas.configure(bg=bg.get("value", "#0e0e0e"))
        
        elif bg.get("type") == "gradient" and bg.get("gradient"):
            try:
                if HAS_PIL:
                    from PIL import Image as PILImage, ImageDraw as PILDraw, ImageTk as PILImageTk
                    
                    grad = bg["gradient"]
                    w = self.window_canvas.winfo_width() or 1400
                    h = self.window_canvas.winfo_height() or 600
                    
                    if w <= 1: w = 1400
                    if h <= 1: h = 600
                    
                    img = PILImage.new("RGB", (w, h))
                    draw = PILDraw.Draw(img)
                    
                    # Validate gradient colors with proper error reporting
                    c1_val = grad.get("color1", "#121212")
                    c2_val = grad.get("color2", "#1e1e1e")
                    
                    if not c1_val or not isinstance(c1_val, str):
                        log("ui", f"Canvas gradient: Invalid color1: {repr(c1_val)}, using default")
                        c1_val = "#121212"
                    if not c2_val or not isinstance(c2_val, str):
                        log("ui", f"Canvas gradient: Invalid color2: {repr(c2_val)}, using default")
                        c2_val = "#1e1e1e"
                    
                    c1_str = c1_val.lstrip('#') or "121212"
                    c2_str = c2_val.lstrip('#') or "1e1e1e"
                    
                    if len(c1_str) != 6:
                        log("ui", f"Canvas gradient: Invalid hex length for color1: {repr(c1_str)}")
                        c1_str = "121212"
                    if len(c2_str) != 6:
                        log("ui", f"Canvas gradient: Invalid hex length for color2: {repr(c2_str)}")
                        c2_str = "1e1e1e"
                    
                    try:
                        c1_rgb = tuple(int(c1_str[i:i+2], 16) for i in (0, 2, 4))
                        c2_rgb = tuple(int(c2_str[i:i+2], 16) for i in (0, 2, 4))
                    except ValueError as ve:
                        log("ui", f"Canvas gradient: Invalid hex values: c1={repr(c1_str)}, c2={repr(c2_str)}, error={ve}")
                        c1_rgb = (0x12, 0x12, 0x12)
                        c2_rgb = (0x1e, 0x1e, 0x1e)
                    
                    if grad.get("type") == "radial":
                        cx, cy = w // 2, h // 2
                        max_dist = ((w // 2) ** 2 + (h // 2) ** 2) ** 0.5
                        for y in range(h):
                            for x in range(w):
                                dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                                ratio = min(dist / max_dist, 1.0)
                                r = int(c1_rgb[0] * (1 - ratio) + c2_rgb[0] * ratio)
                                g = int(c1_rgb[1] * (1 - ratio) + c2_rgb[1] * ratio)
                                b = int(c1_rgb[2] * (1 - ratio) + c2_rgb[2] * ratio)
                                draw.point((x, y), fill=(r, g, b))
                    else:
                        # Linear
                        for x in range(w):
                            ratio = x / max(w, 1)
                            r = int(c1_rgb[0] * (1 - ratio) + c2_rgb[0] * ratio)
                            g = int(c1_rgb[1] * (1 - ratio) + c2_rgb[1] * ratio)
                            b = int(c1_rgb[2] * (1 - ratio) + c2_rgb[2] * ratio)
                            draw.line([(x, 0), (x, h)], fill=(r, g, b))
                    
                    photo = PILImageTk.PhotoImage(img)
                    self._canvas_gradient = photo
                    
                    if not hasattr(self, "_canvas_bg_lbl"):
                        self._canvas_bg_lbl = tk.Label(self.window_canvas, image=photo, bd=0)
                        self._canvas_bg_lbl.place(x=0, y=0, width=w, height=h)
                        self._canvas_bg_lbl.lower()
                    else:
                        self._canvas_bg_lbl.configure(image=photo)
                        self._canvas_bg_lbl.place(x=0, y=0, width=w, height=h)
                        self._canvas_bg_lbl.lower()
            except Exception as e:
                log("ui", f"Canvas gradient failed: {e}")
                self.window_canvas.configure(bg=bg.get("value", "#0e0e0e"))
        
        elif bg.get("type") in ["image", "video"] and bg.get("path"):
            try:
                path = bg["path"]
                self._current_bg_path = path  # Store for resize handler
                if os.path.exists(path):
                    path_lower = path.lower()
                    # For image formats (PNG, JPG, GIF), use PIL
                    if path_lower.endswith(('.gif', '.png', '.jpg', '.jpeg')):
                        try:
                            import imageio
                            from PIL import Image as PILImage, ImageTk as PILImageTk
                            
                            # Get canvas dimensions
                            w = self.window_canvas.winfo_width() or 1400
                            h = self.window_canvas.winfo_height() or 600
                            if w <= 1: w = 1400
                            if h <= 1: h = 600
                            
                            # Use imageio for animated GIFs - handles all color modes cleanly
                            if path_lower.endswith('.gif'):
                                try:
                                    reader = imageio.get_reader(path)
                                    is_animated = reader.get_length() > 1
                                except:
                                    is_animated = False
                                
                                if is_animated:
                                    # Animated GIF via imageio
                                    frames = []
                                    durations = []
                                    
                                    for frame_data in reader:
                                        # imageio returns numpy arrays; convert to PIL
                                        frame = PILImage.fromarray(frame_data)
                                        
                                        # Resize frame
                                        img_w, img_h = frame.size
                                        scale_w = w / img_w if img_w > 0 else 1
                                        scale_h = h / img_h if img_h > 0 else 1
                                        scale = max(scale_w, scale_h)
                                        new_w = int(img_w * scale)
                                        new_h = int(img_h * scale)
                                        frame = frame.resize((new_w, new_h), PILImage.Resampling.LANCZOS)
                                        
                                        # Ensure RGB
                                        if frame.mode != 'RGB':
                                            frame = frame.convert('RGB')
                                        
                                        frames.append(frame)
                                        durations.append(100)  # imageio doesn't expose frame timing reliably
                                    
                                    self._canvas_bg_frames = frames
                                    self._canvas_bg_durations = durations
                                    self._canvas_bg_frame_idx = 0
                                    
                                    if not hasattr(self, "_canvas_bg_lbl"):
                                        self._canvas_bg_lbl = tk.Label(self.window_canvas, bd=0)
                                        self._canvas_bg_lbl.place(x=0, y=0, width=w, height=h)
                                        self._canvas_bg_lbl.lower()
                                    
                                    # Start animation loop
                                    self._animate_canvas_bg()
                                    log("ui", f"Loaded animated GIF background: {path} ({len(frames)} frames)")
                                    reader.close()
                                else:
                                    # Static or single-frame image
                                    img = PILImage.open(path)
                                    img_w, img_h = img.size
                                    scale_w = w / img_w if img_w > 0 else 1
                                    scale_h = h / img_h if img_h > 0 else 1
                                    scale = max(scale_w, scale_h)
                                    
                                    new_w = int(img_w * scale)
                                    new_h = int(img_h * scale)
                                    img = img.resize((new_w, new_h), PILImage.Resampling.LANCZOS)
                                    
                                    if img.mode != 'RGB':
                                        img = img.convert('RGB')
                            else:
                                # PNG, JPG, JPEG - always static
                                img = PILImage.open(path)
                                img_w, img_h = img.size
                                scale_w = w / img_w if img_w > 0 else 1
                                scale_h = h / img_h if img_h > 0 else 1
                                scale = max(scale_w, scale_h)
                                
                                new_w = int(img_w * scale)
                                new_h = int(img_h * scale)
                                img = img.resize((new_w, new_h), PILImage.Resampling.LANCZOS)
                                
                                if img.mode != 'RGB':
                                    img = img.convert('RGB')
                            
                            # Display static image (either from GIF single-frame or PNG/JPG/JPEG)
                            self._canvas_bg_img = img
                            photo = PILImageTk.PhotoImage(img)
                            self._canvas_bg_photo = photo
                            
                            if not hasattr(self, "_canvas_bg_lbl"):
                                self._canvas_bg_lbl = tk.Label(self.window_canvas, image=photo, bd=0)
                                self._canvas_bg_lbl.place(x=0, y=0, relwidth=1, relheight=1)
                                self._canvas_bg_lbl.lower()
                            else:
                                self._canvas_bg_lbl.configure(image=photo)
                                self._canvas_bg_lbl.place(x=0, y=0, relwidth=1, relheight=1)
                                self._canvas_bg_lbl.lower()
                            
                            log("ui", f"Loaded canvas background: {path}")
                        except Exception as pil_e:
                            log("ui", f"PIL canvas image load failed: {type(pil_e).__name__}: {pil_e}")
                            self.window_canvas.configure(bg=bg.get("value", "#0e0e0e"))
                    else:
                        self.window_canvas.configure(bg=bg.get("value", "#0e0e0e"))
            except Exception as e:
                log("ui", f"Canvas background load failed: {e}")
                self.window_canvas.configure(bg=bg.get("value", "#0e0e0e"))
        else:
            # Default fallback
            self.window_canvas.configure(bg=bg.get("value", "#0e0e0e"))
        try:
            self.main_paned.configure(bg=bg.get("value", "#0e0e0e"))
        except Exception:
            pass

        # Helper to extract fallback color
        def _get_fallback_color(panel_name):
            p = panels.get(panel_name, {})
            if isinstance(p, dict) and p.get("value"):
                return p["value"]
            return "#121212"

        # Apply to each panel (supports color, image, gradient)
        panels_to_apply = []
        if hasattr(self, 'panel_left'):
            panels_to_apply.append(("left", self.panel_left))
        if hasattr(self, 'panel_center'):
            panels_to_apply.append(("center", self.panel_center))
        if hasattr(self, 'panel_right'):
            panels_to_apply.append(("right", self.panel_right))
            
        for pname, widget in panels_to_apply:
            if widget and pname in panels:
                try:
                    panel_cfg = panels[pname]
                    _apply_bg_to_widget(widget, panel_cfg, _get_fallback_color(pname))
                except Exception as e:
                    log("ui", f"Failed to apply {pname} panel theme: {e}")

        # ---- Toolbar bg
        if hasattr(self, "_toolbar_bg_label") and "toolbar" in panels:
            try:
                _apply_bg_to_widget(self._toolbar_bg_label, panels["toolbar"], 
                                   bg.get("value", "#0e0e0e"))
            except Exception:
                pass

        # ---- Subtitle bg
        if "subtitle" in panels:
            try:
                subtitle_cfg = panels["subtitle"]
                
                # Apply to canvas
                if hasattr(self, "sub_canvas"):
                    _apply_bg_to_widget(self.sub_canvas, subtitle_cfg, 
                                       bg.get("value", "#0e0e0e"))
                
                # For subtitle label: only use solid color bg (no images/gradients on text)
                # This ensures text is always readable and layered properly
                if hasattr(self, "sub_label"):
                    if subtitle_cfg.get("type") == "color":
                        bg_color = subtitle_cfg.get("value", "#0e0e0e")
                        self.sub_label.configure(bg=bg_color)
                    else:
                        # For image/gradient on canvas, label should use a semi-transparent approach
                        # Default to dark background for text readability
                        self.sub_label.configure(bg=bg.get("value", "#0e0e0e"))
            except Exception as e:
                log("ui", f"Subtitle theming error: {e}")
    
    def _create_floating_window(self, window_id, title, x, y, width, height):
        """Create a floating window with a WidgetPanel inside."""
        # Create the floating window
        floating_win = FloatingWindow(self.window_canvas, window_id, title, x, y, width, height)
        self.floating_windows[window_id] = floating_win
        
        # Override minimize button to use our callback for dynamic taskbar
        floating_win.min_btn.configure(command=lambda: self._on_window_minimize(window_id))
        
        # Create a WidgetPanel inside the floating window's widget_container
        bg = self.art["global_bg"]
        panel_theme = self.art["panels"].get(window_id.replace("window_", ""), {"bg": "#121212"})
        
        widget_panel = WidgetPanel(
            floating_win.widget_container,
            name=window_id,
            registry=self.widgets,
            ui_theme={
                "bg": bg.get("value", "#0e0e0e"),
                "panel": panel_theme.get("bg", "#121212")
            }
        )
        
        # Store reference
        self.widget_panels[window_id] = widget_panel
        
        # Pack the panel into the window (WidgetPanel IS a Frame)
        widget_panel.pack(fill="both", expand=True)
        
        return floating_win, widget_panel
    
    def _on_window_minimize(self, window_id):
        """Handle window minimize - show taskbar tab."""
        floating_win = self.floating_windows[window_id]
        floating_win.minimize()
        
        # Create taskbar tab for this window if it doesn't exist
        if window_id not in self.taskbar_tabs:
            tab = tk.Button(
                self.taskbar,
                text=f"◆ {floating_win.title_text}",
                bg="#2a2a2a",
                fg="#4cc9f0",
                activebackground="#3a3a3a",
                activeforeground="#4cc9f0",
                font=("Segoe UI", 9),
                relief="flat",
                padx=12,
                pady=6,
                command=lambda: self._on_window_restore(window_id)
            )
            tab.pack(side="left", padx=4, pady=4)
            self.taskbar_tabs[window_id] = tab
        
        # Show taskbar if hidden
        self.taskbar.pack(side="bottom", fill="x")
    
    def _on_window_restore(self, window_id):
        """Handle window restore - hide taskbar tab."""
        floating_win = self.floating_windows[window_id]
        floating_win.restore()
        
        # Remove taskbar tab
        if window_id in self.taskbar_tabs:
            self.taskbar_tabs[window_id].destroy()
            del self.taskbar_tabs[window_id]
        
        # Hide taskbar if no more tabs
        if not self.taskbar_tabs:
            self.taskbar.pack_forget()

    def _runtime_for_ui(self) -> Dict[str, Any]:
        def get_memory():
            """Access station memory from widgets."""
            return getattr(self, "mem", {})
        
        def save_memory_wrapped(mem_dict):
            """Save station memory from widgets."""
            if hasattr(self, "mem"):
                self.mem = mem_dict
            save_memory(mem_dict)
        
        return {
            "log": log,
            "ui_q": ui_q,
            "ui_cmd_q": ui_cmd_q,
            "event_q": event_q,
            "StationEvent": StationEvent,
            "now_ts": now_ts,
            "sha1": sha1,
            "tk": tk,
            "MUSIC_STATE": MUSIC_STATE,
            "get_memory": get_memory,
            "save_memory": save_memory_wrapped,
        }


    def _broadcast_station_event(self, evt: str, payload: Any):
        # Send to every widget instance in every panel
        for panel in (self.panel_left, self.panel_center, self.panel_right):
            for inst in panel.all_widget_instances():
                try:
                    if hasattr(inst, "on_station_event"):
                        inst.on_station_event(evt, payload)
                except Exception:
                    pass

    # -----------------------
    # Built-in widgets (wrap your existing panels)
    # -----------------------
    def _install_builtin_widgets(self):
        # Register built-ins (only if not already registered)
        if not self.widgets.get("segment_meta"):
            self.widgets.register("segment_meta", self._factory_segment_meta, title="Segment • Meta", default_panel="left")
        if not self.widgets.get("segment_body"):
            self.widgets.register("segment_body", self._factory_segment_body, title="Segment • Body", default_panel="center")
        if not self.widgets.get("segment_comments"):
            self.widgets.register("segment_comments", self._factory_segment_comments, title="Segment • Comments", default_panel="right")
        if not self.widgets.get("visual_prompt"):
            self.widgets.register("visual_prompt", self._factory_visual_prompt, title="Visual • Prompt", default_panel="left")
        if not self.widgets.get("live_prompts"):
            self.widgets.register("live_prompts", self._factory_live_prompts, title="Live • Prompts", default_panel="left")

        rt = self._runtime_for_ui()

        # default layout = current behavior
        self.panel_left.add_widget("segment_meta", rt)
        self.panel_left.add_widget("visual_prompt", rt)
        self.panel_left.add_widget("live_prompts", rt)

        self.panel_center.add_widget("segment_body", rt)
        self.panel_right.add_widget("segment_comments", rt)

        # make toolbar default widget choice sensible
        ks = self.widgets.keys()
        self._widget_choice.set(ks[0] if ks else "")

    def _factory_segment_meta(self, parent, runtime):
        # your Meta tab (was a Notebook; now a widget)
        frame = tk.Frame(parent, bg="#0e0e0e")
        self.meta = tk.Text(frame, wrap="word", bg="#121212", fg="#e8e8e8", font=("Segoe UI", 12))
        self.meta.pack(fill="both", expand=True)
        self.meta.config(state="disabled")
        return frame

    def _factory_segment_body(self, parent, runtime):
        frame = tk.Frame(parent, bg="#0e0e0e")
        self.body = tk.Text(frame, wrap="word", bg="#111111", fg="#e8e8e8", font=("Segoe UI", 12))
        self.body.pack(fill="both", expand=True)
        return frame

    def _factory_segment_comments(self, parent, runtime):
        frame = tk.Frame(parent, bg="#0e0e0e")
        self.comments = tk.Text(frame, wrap="word", bg="#101010", fg="#e8e8e8", font=("Segoe UI", 11))
        self.comments.pack(fill="both", expand=True)
        return frame

    def _factory_visual_prompt(self, parent, runtime):
        frame = tk.Frame(parent, bg="#0e0e0e")
        self.visual_prompt = tk.Text(frame, wrap="word", bg="#121212", fg="#e8e8e8", font=("Segoe UI", 11))
        self.visual_prompt.pack(fill="both", expand=True, padx=6, pady=6)
        self.visual_prompt.config(state="disabled")
        return frame

    def _factory_live_prompts(self, parent, runtime):
        # this reproduces your old Live Prompts tab content (but as a widget)
        frame = tk.Frame(parent, bg="#0e0e0e")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        canvas = tk.Canvas(frame, bg="#0e0e0e", highlightthickness=0)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)

        scroll.grid(row=0, column=1, sticky="ns")
        canvas.grid(row=0, column=0, sticky="nsew")

        inner = tk.Frame(canvas, bg="#0e0e0e")
        canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_config(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_config)

        self.live_inner = inner
        self.live_prompt_boxes = {}

        row = 0
        roles = ["host", "producer"]
        for name in (CFG.get("characters", {}) or {}).keys():
            if name not in roles:
                roles.append(name)

        for role in roles:
            lbl = tk.Label(inner, text=role.upper(), bg="#0e0e0e", fg="#9a9a9a", font=("Segoe UI", 10, "bold"))
            lbl.grid(row=row, column=0, sticky="w", padx=8, pady=(10,2))

            box = tk.Text(inner, height=3, wrap="word", bg="#121212", fg="#e8e8e8", font=("Segoe UI", 11))
            box.grid(row=row+1, column=0, sticky="ew", padx=8)

            inner.columnconfigure(0, weight=1)

            self.live_prompt_boxes[role] = box
            row += 2

        apply_btn = tk.Button(
            inner, text="Apply Live Prompts",
            command=self._apply_live_prompts,
            bg="#2a2a2a", fg="#ffffff", relief="flat", padx=12, pady=8
        )
        apply_btn.grid(row=row, column=0, pady=16)

        return frame

    def _apply_live_prompts(self):
        payload = {}
        for role, box in self.live_prompt_boxes.items():
            txt = box.get("1.0", "end").strip()
            if txt:
                payload[role] = txt
        if payload:
            ui_cmd_q.put(("apply_live_prompts", payload))


    def _wrap_subtitle(self, text: str, maxc: int, max_lines: int = 2) -> str:
        """
        Soft wrap only by words.
        Never hard cut characters.
        Keeps last visible lines cleanly.
        """

        words = (text or "").split()
        if not words:
            return ""

        lines = []
        cur = ""

        for w in words:
            if not cur:
                cur = w
            elif len(cur) + 1 + len(w) <= maxc:
                cur += " " + w
            else:
                lines.append(cur)
                cur = w

        if cur:
            lines.append(cur)

        # Only trim by line count (never characters)
        if len(lines) > max_lines:
            lines = lines[-max_lines:]

        return "\n".join(lines)

    def _schedule_subtitle_clear(self, ms: int = 6000):
        # Auto-clear is optional; disable by setting ms <= 0
        if ms <= 0:
            return
        try:
            if self._subtitle_clear_job is not None:
                self.root.after_cancel(self._subtitle_clear_job)
        except Exception:
            pass
        self._subtitle_clear_job = self.root.after(ms, lambda: self.set_subtitle(""))
    def set_subtitle(self, text: str):

        raw = str(text or "").strip()

        if not raw:
            self.sub_label.config(text="")
            self._subtitle_last_text = ""
            return

        wrapped = self._wrap_subtitle(
            raw,
            self._subtitle_max_chars,
            max_lines=2
        )

        # Prevent flicker but allow progressive growth
        if wrapped == self._subtitle_last_text:
            return

        self._subtitle_last_text = wrapped
        self.sub_label.config(text=wrapped)

        # -----------------------
        # UI Polling
        # -----------------------
    def _poll_queues(self):

        # -----------------------
        # Subtitles (stream live)
        # -----------------------
        try:
            while True:
                txt = subtitle_q.get_nowait()
                self.set_subtitle(txt)
        except queue.Empty:
            pass


        # -----------------------
        # UI / runtime events
        # -----------------------
        try:
            while True:
                evt, payload = ui_q.get_nowait()

                # -----------------
                # Visual prompt
                # -----------------
                if evt == "visual_prompt":
                    self._set_visual_prompt(str(payload or ""))

                # -----------------
                # Layout controls
                # -----------------
                elif evt == "ui_snapshot_layout":
                    self._save_layout_file()

                elif evt == "ui_load_layout":
                    self._load_layout_file()

                elif evt == "ui_reset_layout":
                    self._reset_layout()

                # =============================
                # 🎨 SAVE STATION ART / THEME
                # =============================
                elif evt == "save_station_art":
                    try:
                        art = (payload or {}).get("art") or {}

                        mp = os.path.join(STATION_DIR, "manifest.yaml")
                        with open(mp, "r", encoding="utf-8") as f:
                            cfg = yaml.safe_load(f) or {}

                        cfg["art"] = art

                        with open(mp, "w", encoding="utf-8") as f:
                            yaml.safe_dump(
                                cfg,
                                f,
                                sort_keys=False,
                                allow_unicode=True
                            )

                        log("ui", "Saved art/theme to manifest.yaml")

                    except Exception as e:
                        log("ui", f"Save art failed: {type(e).__name__}: {e}")

                # -----------------
                # Segment start
                # -----------------
                elif evt == "now_playing_on":
                    self._broadcast_station_event("now_playing_on", payload)

                # -----------------
                # Segment end
                # -----------------
                elif evt == "now_playing_off":
                    self._broadcast_station_event("now_playing_off", payload)

                # -----------------
                # Legacy segment display
                # -----------------
                elif evt == "set_segment_display":
                    self.set_segment_display(payload)
                    self._broadcast_station_event("now_playing_on", payload)

                # -----------------
                # Targeted widget updates
                # -----------------
                elif evt == "widget_update":
                    if isinstance(payload, dict):
                        wk = (payload.get("widget_key") or "").strip().lower()
                        data = payload.get("data")
                        self._dispatch_widget_update(wk, data)

                # -----------------
                # Unknown event
                # -----------------
                else:
                    pass

        except queue.Empty:
            pass


        # -----------------------
        # Continue polling loop
        # -----------------------
        self.root.after(30, self._poll_queues)

    def _animate_wave(self):
        if not self.art.get("subtitle_wave", True):
            return

        if not hasattr(self, "wave_canvas"):
            self.root.after(33, self._animate_wave)
            return

        c = self.wave_canvas
        c.delete("wave")

        w = c.winfo_width()
        h = c.winfo_height()

        if w <= 1 or h <= 1:
            self.root.after(33, self._animate_wave)
            return

        mid = h // 2

        # -----------------------
        # Pull live audio level
        # -----------------------
        try:
            level = float(globals().get("AUDIO_LEVEL", 0.0))
        except Exception:
            level = 0.0

        level = max(0.0, min(level, 1.0))

        self._wave_history.append(level)
        self._wave_history.pop(0)

        n = len(self._wave_history)
        step = max(int(w / n), 1)

        points = []

        for i, v in enumerate(self._wave_history):
            x = i * step
            amp = v * (h * 0.45)
            y = mid - amp
            points.extend([x, y])

        for i, v in reversed(list(enumerate(self._wave_history))):
            x = i * step
            amp = v * (h * 0.45)
            y = mid + amp
            points.extend([x, y])

        c.create_polygon(
            points,
            fill=self.art.get("accent", "#4cc9f0"),
            outline="",
            tags="wave"
        )

        self.root.after(33, self._animate_wave)


    def _dispatch_widget_update(self, widget_key: str, data: Any):
        # broadcast to all instances of widget_key in all panels
        for panel in (self.panel_left, self.panel_center, self.panel_right):
            for inst in panel.widget_instances_by_key(widget_key):
                try:
                    if hasattr(inst, "on_update"):
                        inst.on_update(data)
                except Exception:
                    pass
    def _layout_path(self) -> str:
        """Deprecated - layouts now stored in manifest."""
        return os.path.join(STATION_DIR, "ui_layout.json")

    def _save_layout_file(self):
        """Save layout to manifest including floating window positions."""
        try:
            layout = {
                "windows": {},
                "panes": {
                    "left": {},
                    "center": {},
                    "right": {},
                }
            }
            
            # Save panel layouts if they exist and have serialize_layout method
            if hasattr(self, 'panel_left') and self.panel_left and hasattr(self.panel_left, 'serialize_layout'):
                try:
                    layout["panes"]["left"] = self.panel_left.serialize_layout()
                except Exception as e:
                    log("ui", f"Warning: Failed to serialize panel_left: {e}")
            
            if hasattr(self, 'panel_center') and self.panel_center and hasattr(self.panel_center, 'serialize_layout'):
                try:
                    layout["panes"]["center"] = self.panel_center.serialize_layout()
                except Exception as e:
                    log("ui", f"Warning: Failed to serialize panel_center: {e}")
            
            if hasattr(self, 'panel_right') and self.panel_right and hasattr(self.panel_right, 'serialize_layout'):
                try:
                    layout["panes"]["right"] = self.panel_right.serialize_layout()
                except Exception as e:
                    log("ui", f"Warning: Failed to serialize panel_right: {e}")
            
            # Save floating window states
            if hasattr(self, 'floating_windows') and self.floating_windows:
                for window_id, floating_win in self.floating_windows.items():
                    try:
                        if hasattr(floating_win, 'serialize'):
                            layout["windows"][window_id] = floating_win.serialize()
                    except Exception as e:
                        log("ui", f"Warning: Failed to serialize window {window_id}: {e}")
            
            # Save to manifest
            if "ui_layout" not in CFG:
                CFG["ui_layout"] = {}
            CFG["ui_layout"].update(layout)
            save_station_manifest(CFG)
            log("ui", f"Saved UI layout with window positions to manifest")
        except Exception as e:
            log("ui", f"Save layout failed: {type(e).__name__}: {e}")

    def _load_layout_file(self):
        """Load layout from manifest including floating window positions."""
        try:
            # Try to load from manifest first
            layout = CFG.get("ui_layout")
            if not layout:
                # Fallback to old JSON file for backward compatibility
                p = self._layout_path()
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as f:
                        layout = json.load(f) or {}
                else:
                    log("ui", "No layout found in manifest or ui_layout.json")
                    return
            
            if not isinstance(layout, dict):
                log("ui", "Invalid layout format in manifest")
                return

            # Restore floating window positions and states
            windows_data = layout.get("windows", {})
            if hasattr(self, 'floating_windows') and self.floating_windows and isinstance(windows_data, dict):
                for window_id, win_data in windows_data.items():
                    if window_id in self.floating_windows:
                        try:
                            floating_win = self.floating_windows[window_id]
                            geom = win_data.get("geometry", {})
                            
                            # Restore position and size
                            x = geom.get("x", floating_win.x)
                            y = geom.get("y", floating_win.y)
                            w = geom.get("width", floating_win.width)
                            h = geom.get("height", floating_win.height)
                            
                            floating_win.x = x
                            floating_win.y = y
                            floating_win.width = w
                            floating_win.height = h
                            floating_win.frame.place(x=x, y=y, width=w, height=h)
                            
                            # Restore minimize state
                            if win_data.get("is_minimized", False) and hasattr(floating_win, 'minimize'):
                                floating_win.minimize()
                            
                            # Restore active tab
                            active_tab = win_data.get("active_tab")
                            if active_tab and hasattr(floating_win, 'tabs') and active_tab in floating_win.tabs:
                                if hasattr(floating_win, 'show_tab'):
                                    floating_win.show_tab(active_tab)
                        except Exception as e:
                            log("ui", f"Warning: Failed to restore window {window_id}: {e}")

            # Restore panel widget tabs (backward compatibility)
            # Only if panels are initialized
            if hasattr(self, 'panel_left') and hasattr(self, 'panel_center') and hasattr(self, 'panel_right'):
                rt = self._runtime_for_ui()
                panes = (layout.get("panes") or {})
                
                if self.panel_left and hasattr(self.panel_left, 'restore_layout'):
                    try:
                        self.panel_left.restore_layout(panes.get("left") or {}, rt)
                    except Exception as e:
                        log("ui", f"Warning: Failed to restore panel_left: {e}")
                
                if self.panel_center and hasattr(self.panel_center, 'restore_layout'):
                    try:
                        self.panel_center.restore_layout(panes.get("center") or {}, rt)
                    except Exception as e:
                        log("ui", f"Warning: Failed to restore panel_center: {e}")
                
                if self.panel_right and hasattr(self.panel_right, 'restore_layout'):
                    try:
                        self.panel_right.restore_layout(panes.get("right") or {}, rt)
                    except Exception as e:
                        log("ui", f"Warning: Failed to restore panel_right: {e}")

            log("ui", "Loaded UI layout with window positions from manifest")
        except Exception as e:
            log("ui", f"Load layout failed: {type(e).__name__}: {e}")

    def _reset_layout(self):
        try:
            # wipe and restore built-in default
            rt = self._runtime_for_ui()
            for p in (self.panel_left, self.panel_center, self.panel_right):
                p.restore_layout({"tabs":[]}, rt)
            self._install_builtin_widgets()
            log("ui", "Reset UI layout to default")
        except Exception as e:
            log("ui", f"Reset layout failed: {type(e).__name__}: {e}")

    def _reset_window_positions(self):
        """Reset all floating windows to their default 3-column layout."""
        try:
            # Calculate default sizes
            canvas_width = 1400
            canvas_height = 600
            window_width = canvas_width // 3
            
            # Reset each window to default position and size
            default_geom = {
                "window_1": {"x": 0, "y": 0, "width": window_width, "height": canvas_height},
                "window_2": {"x": window_width, "y": 0, "width": window_width, "height": canvas_height},
                "window_3": {"x": window_width * 2, "y": 0, "width": window_width, "height": canvas_height},
            }
            
            for window_id, geom in default_geom.items():
                if window_id in self.floating_windows:
                    win = self.floating_windows[window_id]
                    win.geometry.update(geom)
                    win.frame.place(x=geom["x"], y=geom["y"], width=geom["width"], height=geom["height"])
            
            log("ui", "Window positions reset to default")
        except Exception as e:
            log("ui", f"Reset window positions failed: {type(e).__name__}: {e}")

    # -----------------------
    # Display helpers (existing behavior)
    # -----------------------
    def _set_visual_prompt(self, text: str):
        if not hasattr(self, "visual_prompt"):
            return
        self.visual_prompt.config(state="normal")
        self.visual_prompt.delete("1.0", "end")
        self.visual_prompt.insert("1.0", text.strip() + "\n")
        self.visual_prompt.config(state="disabled")

    def set_segment_display(self, seg: Dict[str, Any]):
        meta = (
            f"SOURCE: {seg.get('source','')}\n"
            f"TITLE: {seg.get('title','')}\n"
            f"ID: {seg.get('post_id','')}\n"
        )

        if hasattr(self, "meta"):
            self.meta.config(state="normal")
            self.meta.delete("1.0", "end")
            self.meta.insert("1.0", meta)
            self.meta.config(state="disabled")

        if hasattr(self, "body"):
            self.body.delete("1.0", "end")
            self.body.insert("1.0", seg.get("body", ""))

        if hasattr(self, "comments"):
            self.comments.delete("1.0", "end")
            for i, c in enumerate(seg.get("comments", []) or []):
                self.comments.insert("end", f"[{i}] {c}\n\n")

        try:
            ui_cmd_q.put(("ui_last_seg", seg))
        except Exception as e:
            log("ERR", f"{type(e).__name__}: {e}")

# =======================
# LLM Client (Multi-Provider)
# =======================

def llm_generate(prompt: str, system: str, model: str, num_predict: int,
                 temperature: float, timeout: int = 10,
                 *, force_json: bool = False) -> str:
    """
    Generate text from LLM using configured provider (Ollama, Claude, GPT, Gemini, etc).
    
    Automatically detects provider from CFG and routes to correct implementation.
    Falls back to Ollama if provider not specified (backward compatibility).
    """
    from model_provider import get_llm_provider

    llm_cfg = CFG.get("llm") if isinstance(CFG.get("llm"), dict) else {}
    provider_type = (llm_cfg.get("provider") or "ollama").strip().lower()

    model = (model or "").strip()
    if not model:
        raise RuntimeError("LLM model missing")

    try:
        log("llm", f"req provider={provider_type} model={model} tok={int(num_predict)} timeout={int(timeout)}s json={force_json}")
        t0 = time.time()

        provider = get_llm_provider(CFG)
        out = provider.generate(
            model=model,
            prompt=prompt,
            system=system,
            num_predict=num_predict,
            temperature=temperature,
            timeout=timeout,
            force_json=force_json,
        )

        log("llm", f"ok provider={provider_type} model={model} dt={time.time()-t0:.2f}s chars={len(out)}")
        return out

    except Exception as e:
        log("llm", f"error: {type(e).__name__}: {e}")
        raise


def extractive_packet(seg: Dict[str, Any]) -> Dict[str, Any]:
    """
    NO GENERATED LANGUAGE.
    Only reuses text already present in the segment fields.
    """
    title = clean(seg.get("title", ""))[:500]
    angle = clean(seg.get("angle", ""))[:700]
    why   = clean(seg.get("why", ""))[:700]
    body  = clean((seg.get("body", "") or "")[:1200])

    # Build minimal “packet” fields that your renderer already supports.
    # Only include non-empty fields; no filler defaults.
    pkt: Dict[str, Any] = {"panel": []}

    if title:
        pkt["host_intro"] = title
    if body:
        pkt["summary"] = body
    elif angle:
        pkt["summary"] = angle
    elif why:
        pkt["summary"] = why

    # Host takeaway must also be extractive
    if why:
        pkt["host_takeaway"] = why
    elif angle:
        pkt["host_takeaway"] = angle

    return pkt

# =======================
# SQLite Queue (Core Runtime)
# =======================

def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)

    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS scheduler_state (
        k TEXT PRIMARY KEY,
        v TEXT
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS segments (
        id TEXT PRIMARY KEY,
        created_ts INTEGER,
        priority REAL,
        status TEXT,
        claimed_ts INTEGER,

        post_id TEXT,
        source TEXT,
        event_type TEXT,

        title TEXT,
        body TEXT,
        comments_json TEXT,

        angle TEXT,
        why TEXT,
        key_points_json TEXT,
        host_hint TEXT
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS seen_items (
        post_id TEXT PRIMARY KEY,
        first_seen_ts INTEGER
    );
    """)

    conn.commit()
    return conn


def migrate_segments_table(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(segments);")
    cols = {r[1] for r in cur.fetchall()}

    def ensure(col, sql):
        if col not in cols:
            conn.execute(sql)

    ensure("source", "ALTER TABLE segments ADD COLUMN source TEXT;")
    ensure("event_type", "ALTER TABLE segments ADD COLUMN event_type TEXT;")
    ensure("claimed_ts", "ALTER TABLE segments ADD COLUMN claimed_ts INTEGER;")

    conn.commit()





def db_seen_set(conn: sqlite3.Connection) -> set:
    cur = conn.execute("SELECT post_id FROM seen_items;")
    return set(r[0] for r in cur.fetchall())


def db_mark_seen(conn: sqlite3.Connection, post_ids: List[str]) -> None:
    ts = now_ts()
    for pid in post_ids:
        conn.execute(
            "INSERT OR IGNORE INTO seen_items(post_id, first_seen_ts) VALUES (?, ?);",
            (pid, ts)
        )
    conn.commit()


def db_enqueue_segment(conn: sqlite3.Connection, seg: Dict[str, Any]) -> bool:
    source = seg.get("source", "feed")
    event_type = seg.get("event_type", "item")

    cur = conn.execute("""
    INSERT OR IGNORE INTO segments (
        id, created_ts, priority, status,
        post_id, source, event_type,
        title, body,
        comments_json, angle, why, key_points_json, host_hint
    ) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        seg["id"],
        now_ts(),
        float(seg.get("priority", 50.0)),
        seg["post_id"],
        source,
        event_type,
        seg.get("title",""),
        seg.get("body",""),
        json.dumps(seg.get("comments", []), ensure_ascii=False),
        seg.get("angle",""),
        seg.get("why",""),
        json.dumps(seg.get("key_points", []), ensure_ascii=False),
        seg.get("host_hint",""),
    ))
    conn.commit()
    return int(getattr(cur, "rowcount", 0) or 0) > 0




def db_pop_next_segment(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    oversample = max(FAIR_WINDOW * 6, 40)

    rows = conn.execute("""
        SELECT
            id, created_ts, priority,
            post_id, source, event_type,
            title, body, comments_json,
            angle, why, key_points_json, host_hint
        FROM segments
        WHERE status='queued'
        ORDER BY priority DESC, created_ts ASC
        LIMIT ?;
    """, (oversample,)).fetchall()

    if not rows:
        return None

    buckets: Dict[str, List[tuple]] = {}
    for r in rows:
        src = (r[4] or "feed").strip().lower() or "feed"
        buckets.setdefault(src, []).append(r)

    sources = sorted(buckets.keys())

    # build schedule (quota slots)
    schedule: List[str] = []
    for s in sources:
        q = int(SOURCE_QUOTAS.get(s, 1) or 1)
        schedule.extend([s] * max(q, 1))
    if not schedule:
        schedule = sources[:] or ["feed"]

    # fetch pointer (no commit)
    rr_ptr = 0
    try:
        c = conn.execute("SELECT v FROM scheduler_state WHERE k='rr_ptr';").fetchone()
        rr_ptr = int(c[0]) if c and str(c[0]).isdigit() else 0
    except Exception:
        rr_ptr = 0

    rr_ptr = rr_ptr % len(schedule)
    rotated = schedule[rr_ptr:] + schedule[:rr_ptr]

    picked_row = None
    for s in rotated:
        if buckets.get(s):
            picked_row = buckets[s][0]
            break

    if not picked_row:
        picked_row = rows[0]

    seg_id = picked_row[0]
    next_ptr = (rr_ptr + 1) % len(schedule)

    # single transaction: advance ptr + claim segment
    try:
        conn.execute("BEGIN;")

        conn.execute(
            "INSERT INTO scheduler_state(k,v) VALUES('rr_ptr', ?) "
            "ON CONFLICT(k) DO UPDATE SET v=excluded.v;",
            (str(int(next_ptr)),)
        )

        res = conn.execute(
            "UPDATE segments SET status='claimed', claimed_ts=? "
            "WHERE id=? AND status='queued';",
            (now_ts(), seg_id)
        )

        conn.execute("COMMIT;")

    except Exception:
        try:
            conn.execute("ROLLBACK;")
        except Exception:
            pass
        return None

    if int(getattr(res, "rowcount", 0) or 0) == 0:
        return None

    # decode JSON
    try:
        comments = json.loads(picked_row[8]) if picked_row[8] else []
    except Exception:
        comments = []
    try:
        key_points = json.loads(picked_row[11]) if picked_row[11] else []
    except Exception:
        key_points = []

    return {
        "id": picked_row[0],
        "created_ts": picked_row[1],
        "priority": float(picked_row[2] or 50.0),
        "post_id": picked_row[3],
        "source": picked_row[4],
        "event_type": picked_row[5],
        "title": picked_row[6],
        "body": picked_row[7],
        "comments": comments,
        "angle": picked_row[9],
        "why": picked_row[10],
        "key_points": key_points,
        "host_hint": picked_row[12],
    }


def db_mark_done(conn: sqlite3.Connection, seg_id: str) -> None:
    conn.execute(
        "UPDATE segments SET status='done' WHERE id=?;",
        (seg_id,)
    )
    conn.commit()

def save_memory_throttled(mem: Dict[str, Any], *, min_interval_sec: float = 2.0) -> None:
    now = now_ts()
    last = int(mem.get("_mem_last_save_ts", 0) or 0)
    if now - last < min_interval_sec:
        return
    mem["_mem_last_save_ts"] = now
    save_memory(mem)

# =======================
# Producer Prompt (Generic)
# =======================
def cfg_text(path: str, default: str = "") -> str:
    v = cfg_get(path, default)
    return (v or "").strip()

def cfg_list(path: str, default: Optional[List[str]] = None) -> List[str]:
    v = cfg_get(path, default if default is not None else [])
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    return default if default is not None else []

def clamp_priority(x: Any, fallback: float = 50.0) -> float:
    try:
        v = float(x)
    except Exception:
        v = float(fallback)
    return max(0.0, min(100.0, v))
def parse_json_lenient(raw: str) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        obj = parse_json_strictish(raw)  # uses your extract_first_json_object()
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}

def resolve_lead_voice(seg: Optional[Dict[str, Any]] = None, mem: Optional[Dict[str, Any]] = None) -> str:
    """
    Resolve the lead voice for a segment or station.
    Falls back to "host" for compatibility.
    """
    voice = ""
    if isinstance(seg, dict):
        voice = (seg.get("lead_voice") or "").strip()
    if not voice and isinstance(mem, dict):
        voice = (mem.get("lead_voice") or "").strip()
    if not voice:
        voice = (cfg_get("voices.lead", "") or cfg_get("station.lead_voice", "") or "").strip()
    return (voice or "host").strip().lower()

def ensure_world_state(mem: Dict[str, Any]) -> Dict[str, Any]:
    ws = mem.setdefault("world_state", {})
    if not isinstance(ws, dict):
        ws = {}
        mem["world_state"] = ws

    ws.setdefault("focus_seed", "")
    ws.setdefault("frontier_tags", [])
    ws.setdefault("tension_meter", 0.35)
    ws.setdefault("arcs", [])
    ws.setdefault("open_loops", [])
    ws.setdefault("recent_moves", [])
    return ws

def world_state_summary(ws: Dict[str, Any]) -> str:
    focus = ws.get("focus_seed", "")
    tags = ws.get("frontier_tags", [])[:10]
    tension = ws.get("tension_meter", 0.35)
    arcs = ws.get("arcs", [])[-6:]
    loops = ws.get("open_loops", [])[-6:]
    moves = ws.get("recent_moves", [])[-6:]

    return json.dumps({
        "focus_seed": focus,
        "frontier_tags": tags,
        "tension_meter": tension,
        "arcs": arcs,
        "open_loops": loops,
        "recent_moves": moves
    }, ensure_ascii=False)

def update_world_state(ws: Dict[str, Any], discovery: Dict[str, Any], move: Dict[str, Any]) -> None:
    if not isinstance(ws, dict):
        return

    focus = (move.get("focus") or "").strip()
    if not focus:
        tags = discovery.get("tags", []) if isinstance(discovery.get("tags"), list) else []
        focus = (tags[0] if tags else "").strip()

    if focus:
        ws["focus_seed"] = focus

    tags = discovery.get("tags", []) if isinstance(discovery.get("tags"), list) else []
    frontier = ws.get("frontier_tags", []) if isinstance(ws.get("frontier_tags"), list) else []
    for t in tags:
        tt = str(t).strip()
        if tt and tt not in frontier:
            frontier.append(tt)
    ws["frontier_tags"] = frontier[-20:]

    open_loop = (move.get("open_loop") or "").strip()
    if open_loop:
        loops = ws.get("open_loops", []) if isinstance(ws.get("open_loops"), list) else []
        if open_loop not in loops:
            loops.append(open_loop)
        ws["open_loops"] = loops[-12:]

    energy = (move.get("energy") or "").strip().lower()
    tension = float(ws.get("tension_meter", 0.35) or 0.35)
    if energy == "high":
        tension = min(1.0, tension + 0.08)
    elif energy == "low":
        tension = max(0.0, tension - 0.06)
    else:
        tension = min(1.0, max(0.0, tension + 0.01))
    ws["tension_meter"] = round(tension, 3)

    move_name = (move.get("move") or "").strip().lower()
    recent = ws.get("recent_moves", []) if isinstance(ws.get("recent_moves"), list) else []
    if move_name:
        recent.append(move_name)
        ws["recent_moves"] = recent[-12:]

def curator_system_context(mem: Dict[str, Any]) -> str:
    themes = mem.get("themes", [])[-12:]
    callbacks = mem.get("callbacks", [])[-10:]

    return get_prompt(
        mem, "producer_system_context",
        show_name=SHOW_NAME,
        themes=themes,
        callbacks=callbacks,
        live_nudges=mem_live_prompt_block(mem)
    ).strip()

def init_characters() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for name, cfg in CFG.get("characters", {}).items():
        out[name] = compile_character_prompt(cfg)
    return out

def curator_candidates_prompt(mem: Dict[str, Any], candidates: List[Dict[str, Any]]) -> str:
    """
    IMPORTANT:
    - The curator returns "post_id" in its JSON discoveries.
    - So we MUST display candidates keyed by post_id (not id),
      otherwise the curator will select IDs that don't map back.
    """
    lines = []

    for i, c in enumerate(candidates, 1):
        post_id = c.get("post_id") or c.get("id") or ""
        src = c.get("source", "feed")
        heur = float(c.get("heur", 0.0) or 0.0)

        title = c.get("title", "")
        body = (c.get("body", "") or "")[:520]

        lines.append(
            f"{i}) post_id={post_id} source={src} heur={heur:.1f}\n"
            f"Title: {title}\n"
            f"Body: {body}\n"
        )
    
    cand_str = "\n".join(lines)
    return get_prompt(mem, "producer_candidates_prompt", candidates_list=cand_str)

def navigator_prompt(mem: Dict[str, Any], discoveries: List[Dict[str, Any]]) -> Tuple[str, str]:
    ws = ensure_world_state(mem)
    world_state = world_state_summary(ws)
    return (
        get_prompt(mem, "navigator_system", show_name=SHOW_NAME).strip(),
        get_prompt(mem, "navigator_user", world_state=world_state, discoveries=json.dumps(discoveries, ensure_ascii=False)).strip()
    )

def _discovery_from_candidate(c: Dict[str, Any]) -> Dict[str, Any]:
    title = (c.get("title") or "").strip()
    angle = title or (c.get("body") or "").strip()[:120]
    heur = clamp_priority(c.get("heur", 50.0), fallback=50.0)
    return {
        "post_id": c.get("post_id") or c.get("id") or "",
        "type": "frontier",
        "title": title or "Untitled",
        "angle": angle,
        "why": "Introduce a fresh signal into the world state.",
        "key_points": [angle] if angle else [],
        "tags": [],
        "priority": heur,
        "depth": "quick",
        "host_hint": ""
    }

# =======================
# Host System Prompts (Generic)
# =======================

def host_system(mem: Dict[str, Any]) -> str:
    themes = mem.get("themes", [])[-12:]
    callbacks = mem.get("callbacks", [])[-10:]

    return get_prompt(mem, "host_system", show_name=SHOW_NAME, themes=themes, callbacks=callbacks).strip()
def generate_cold_open_packet(seg: Dict[str, Any], mem: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Generates a natural cold open (2–4 spoken sentences) using only meta context.
    Nothing hardcoded to a show, topic, or domain.
    """

    # ----------------------------
    # Pull seed context if present
    # ----------------------------
    seed_raw = (seg.get("body") or "").strip()
    seed = {}

    try:
        if seed_raw.startswith("{"):
            seed = json.loads(seed_raw)
    except Exception:
        seed = {}

    hot_tags = seed.get("hot_tags") or mem.get("recent_riff_tags", [])

    if not hot_tags:
        hot_tags = (CFG.get("riff", {}).get("tag_catalog") or [])[:6]

    themes   = mem.get("themes", [])[-10:]
    mood     = seed.get("mood") or mem.get("mood") or "neutral"
    focus    = seed.get("focus") or mem.get("focus") or "what matters right now"

    # 🚫 Do NOT cold open until some inferred context exists
    if not hot_tags and not themes:
        return None

    # ----------------------------
    # Meta system prompt (generic)
    # ----------------------------
    sys = get_prompt(mem, "cold_open_system").strip()

    # ----------------------------
    # Meta user prompt (context)
    # ----------------------------
    feeds_active = list(CFG.get("feeds", {}).keys())
    feed_context = ", ".join(feeds_active) if feeds_active else "general news"
    station_context = f"Station: {SHOW_NAME}\nInput Sources: {feed_context}"

    prm = get_prompt(mem, "cold_open_user", mood=mood, focus=focus, hot_tags=hot_tags, themes=themes, station_context=station_context).strip()

    # ----------------------------
    # LLM call + parse
    # ----------------------------
    try:
        raw = llm_generate(
            prompt=prm,
            system=sys,
            model=CFG["models"]["host"],
            num_predict=180,
            temperature=0.85,
            timeout=35,
            force_json=True,
        )

        pkt = parse_json_lenient(raw)
        if not isinstance(pkt, dict):
            return None

        host_intro = clean(str(pkt.get("host_intro", "")))[:700]
        takeaway   = clean(str(pkt.get("host_takeaway", "")))[:500]

        if not host_intro:
            return None

        return {
            "host_intro": host_intro,
            "panel": [],
            "host_takeaway": takeaway
        }

    except Exception as e:
        log("coldopen", f"LLM error: {type(e).__name__}: {e}")
        return None


def host_packet_system(mem: Dict[str, Any]) -> str:
    lead = resolve_lead_voice(mem=mem)
    allowed_voices = [lead] + [k for k in (CFG.get("characters", {}) or {}).keys() if k != lead]
    allowed_voice_str = ", ".join(allowed_voices)

    themes = mem.get("themes", [])[-12:]
    callbacks = mem.get("callbacks", [])[-10:]

    # -------------------------
    # Build side voice section dynamically
    # -------------------------

    side_lines = []

    lead = resolve_lead_voice(mem=mem)
    for name, cfg in CFG.get("characters", {}).items():

        if name.lower().strip() == lead:
            continue

        role = cfg.get("role", "")
        traits = cfg.get("traits", [])
        focus = cfg.get("focus", [])

        desc_parts = []

        if role:
            desc_parts.append(f"role={role}")

        if traits:
            desc_parts.append("traits: " + ", ".join(traits))

        if focus:
            desc_parts.append("focus: " + ", ".join(focus))

        if not desc_parts:
            continue

        side_lines.append(
            f"{name.upper()} → " + " | ".join(desc_parts)
        )

    side_voice_block = "\n".join(side_lines) if side_lines else "(no side voices defined)"

    # -------------------------
    # Final system prompt
    # -------------------------

    return f"""
You are the live host of {SHOW_NAME}.

You are mid-show.

Natural radio flow.
No scripts.
No bullet points.
No announcements.

---

SOURCE TYPES:

FEED:
- Raw material from station feeds.
- Paraphrase then react.

EVENT:
- Concrete state or system updates.

NARRATIVE:
- Long-horizon continuity moments.

---

SIDE VOICES:

Each voice brings a distinct perspective:

{side_voice_block}

No two voices repeat the same angle.

---

EPISTEMIC HYGIENE:

Separate:

• HARD FACTS  
• SOFT CLAIMS  
• OPINIONS  
• UNKNOWNS  

Never invent data.

---

OUTPUT STRICT JSON:
"voice" MUST be one of: {allowed_voice_str}

{{
  "grounding": {{
    "hard_facts": [{{"text":"", "source":"", "confidence":0.0}}],
    "soft_claims": [{{"text":"", "basis":"", "confidence":0.0}}],
    "opinions": [{{"text":"", "voice":""}}],
    "unknowns": [{{"text":"", "why_unknown":""}}]
  }},

  "host_intro": "...",
  "summary": "...",

  "comment_reads": [
    {{ "comment_index": 0, "read_line": "..." }}
  ],

  "perspectives": [
    {{
      "sentiment": "...",
      "voice": "...",
      "line": "...",
      "comment_index": 0
    }}
  ],

  "host_takeaway": "...",
  "callback": "optional"
}}

---

Themes: {themes}
Callbacks: {callbacks}

Sound like a real flowing show.
""".strip()

# =======================
# Host Prompt Builder
# =======================

def host_prompt_for_segment(seg: Dict[str, Any]) -> str:

    comments = seg.get("comments", []) or []

    comment_block = "\n".join(
        f"[{i}] {c}" for i, c in enumerate(comments[:HOST_MAX_COMMENTS])
    ) or "(no comments available)"

    return f"""
You are going on air for ONE segment.

SOURCE: {seg.get("source")}
TYPE: {seg.get("event_type")}

TITLE:
{seg.get("title","")}

PRODUCER NOTES:
angle: {seg.get("angle","")}
why: {seg.get("why","")}
key_points: {seg.get("key_points", [])}
opening_hint: {seg.get("host_hint","")}

PRIMARY MATERIAL:
{(seg.get("body","") or "")[:1200]}

COMMENTS:
{comment_block}

Generate the structured packet JSON now.
""".strip()

# =======================
# Producer Loop (Generic)
# =======================
def pick_diverse_candidates(
    candidates: List[Dict[str, Any]],
    seen: set,
    *,
    need: int,
    per_source_cap: int = 4,
    max_prompt: int = 36,
) -> List[Dict[str, Any]]:
    # filter seen + require stable id
    filt: List[Dict[str, Any]] = []
    for c in (candidates or []):
        pid = c.get("post_id") or c.get("id")
        if not pid:
            continue
        if pid in seen:
            continue
        filt.append(c)

    if not filt:
        return []

    # sort by heur desc, then recency
    def score(c: Dict[str, Any]):
        h = float(c.get("heur", 50.0) or 50.0)
        ts = int(c.get("ts", 0) or 0)
        return (h, ts)

    filt.sort(key=score, reverse=True)

    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for c in filt:
        src = (c.get("source") or "feed").strip().lower() or "feed"
        buckets.setdefault(src, []).append(c)

    sources = sorted(buckets.keys())
    chosen: List[Dict[str, Any]] = []
    per_src = {s: 0 for s in sources}

    # round robin
    while len(chosen) < max_prompt:
        progressed = False
        for s in sources:
            if len(chosen) >= max_prompt:
                break
            if per_src[s] >= per_source_cap:
                continue
            if not buckets.get(s):
                continue
            chosen.append(buckets[s].pop(0))
            per_src[s] += 1
            progressed = True
        if not progressed:
            break

    return chosen
def db_counts_by_source(conn, statuses=("queued", "claimed")):
    ph = ",".join(["?"] * len(statuses))
    rows = conn.execute(
        f"""
        SELECT COALESCE(source,'feed') AS s, COUNT(*) 
        FROM segments
        WHERE status IN ({ph})
        GROUP BY COALESCE(source,'feed')
        """,
        tuple(statuses)
    ).fetchall()

    out = {}
    for s, n in rows:
        key = (s or "feed").strip().lower()
        out[key] = out.get(key, 0) + int(n or 0)
    return out

def can_enqueue_source(conn: sqlite3.Connection, source: str) -> bool:
    # normalize incoming
    src = _normalize_source_alias(source)

    limits_all = cfg_get("producer.source_limits", {}) or {}
    # allow config to use either raw or aliased keys
    limits = limits_all.get(src) or limits_all.get(source) or {}
    if not isinstance(limits, dict) or not limits:
        return True

    # count only active work (queued+claimed), and normalize sources
    rows = conn.execute(
        """
        SELECT COALESCE(source,'feed') AS s, COUNT(*)
        FROM segments
        WHERE status IN ('queued','claimed')
        GROUP BY COALESCE(source,'feed');
        """
    ).fetchall()

    counts: Dict[str, int] = {}
    for s, c in rows:
        k = _normalize_source_alias(s)
        counts[k] = counts.get(k, 0) + int(c or 0)

    total = sum(counts.values())

    # free mixing when queue small
    if total < 5:
        return True

    src_count = counts.get(src, 0)

    max_abs = limits.get("max_abs")
    if max_abs is not None and src_count >= int(max_abs):
        return False

    max_share = limits.get("max_share")
    if max_share is not None and total > 0:
        if (src_count + 1) / (total + 1) > float(max_share):
            return False

    return True

import math
from collections import defaultdict

def _normalize_weights(w: Dict[str, float]) -> Dict[str, float]:
    out = {}
    s = 0.0
    for k, v in (w or {}).items():
        try:
            fv = float(v)
        except Exception:
            continue
        if fv > 0:
            kk = str(k).strip().lower()
            out[kk] = fv
            s += fv
    if s <= 0:
        return {}
    for k in list(out.keys()):
        out[k] = out[k] / s
    return out

def apply_mix_budget(
    candidates_all: List[Dict[str, Any]],
    seen: set,
    need: int,
    max_prompt: int,
    per_source_cap: int,
    mix_weights_raw: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Enforce manifest mix.weights at *prompt-candidate* time (not enqueue time).
    This is the key to stopping RSS from dominating the producer plan.

    Returns at most max_prompt candidates, biased toward the target mix.
    """
    mix_w = _normalize_weights(mix_weights_raw or {})

    # If no mix provided, do nothing special.
    if not mix_w:
        return candidates_all[:max_prompt]

    # Bucket by source, excluding seen
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    
    # Pre-calculate counts for debug
    total_in = len(candidates_all)
    skipped_seen = 0
    
    for c in candidates_all:
        pid = c.get("post_id") or c.get("id")
        if not pid:
            continue
        if str(pid) in seen:
            skipped_seen += 1
            # DEBUG: Uncomment to trace what's being skipped
            # print(f"[MIX TRACE] Skipped seen: {c.get('source')} | {pid} | {c.get('title')[:30]}")
            continue
        src = (c.get("source") or "feed").strip().lower()
        buckets[src].append(c)

    # Sort each bucket by heur desc (best first)
    def cscore(c: Dict[str, Any]) -> float:
        try:
            return float(c.get("heur", 50.0) or 50.0)
        except Exception:
            return 50.0

    for src in list(buckets.keys()):
        buckets[src].sort(key=cscore, reverse=True)

    # DEBUG: Log candidate distribution
    debug_counts = {s: len(buckets[s]) for s in buckets}
    if total_in > 0:
         print(f"[MIX DEBUG] Total={total_in}, Skipped(Seen)={skipped_seen}, Pool={debug_counts}")
    
    # Determine which sources participate:
    # - only those that have candidates
    # - if a source isn't in mix.weights, give it a tiny default weight so it can still appear
    present = [s for s in buckets.keys() if buckets[s]]
    if not present:
        return []

    # Fill missing weights with a small epsilon so new feeds can still surface
    eps = 0.01
    w = {}
    for s in present:
        w[s] = float(mix_w.get(s, eps))
    # Renormalize over present sources
    sw = sum(w.values())
    for s in list(w.keys()):
        w[s] = w[s] / sw if sw > 0 else 1.0 / len(w)

    # We choose a target pick count per source for the prompt set.
    # Use max_prompt as the “pie runtime slice” for the *planning universe*.
    # Enforce per_source_cap so we don’t blow diversity.
    targets: Dict[str, int] = {}
    for s in present:
        targets[s] = max(1, int(round(w[s] * max_prompt)))

    # Fix rounding drift to exactly max_prompt (or less if not enough)
    # Greedy adjust: if sum too high, shave from the most over-allocated; if too low, add to under-allocated.
    def total_targets() -> int:
        return sum(targets.values())

    # Cap each target by available and per_source_cap*something? (leave per_source_cap to later)
    for s in present:
        targets[s] = min(targets[s], len(buckets[s]))

    # Rounding adjust to max_prompt
    # If too many, reduce from biggest targets first
    while total_targets() > max_prompt:
        smax = max(present, key=lambda s: targets.get(s, 0))
        if targets.get(smax, 0) <= 1:
            break
        targets[smax] -= 1
    # If too few, add to sources that still have availability
    while total_targets() < max_prompt:
        # pick source with best remaining availability and smallest current target share vs weight
        addable = [s for s in present if targets.get(s, 0) < len(buckets[s])]
        if not addable:
            break
        # heuristic: add to source with max deficit (weight - current_share)
        cur_total = max(1, total_targets())
        def deficit(s: str) -> float:
            cur_share = targets.get(s, 0) / cur_total
            return w.get(s, 0.0) - cur_share
        s_add = max(addable, key=deficit)
        targets[s_add] = targets.get(s_add, 0) + 1

    # Build the prompt candidate list respecting targets and a hard per-source cap
    out: List[Dict[str, Any]] = []
    per_src_used: Dict[str, int] = defaultdict(int)

    # Prompt Universe Cap:
    # We allow the prompt pool to be slightly larger than the strict *enqueue* per_source_cap
    # so the LLM has some choice. 
    # BUT: We must clamp low-weight sources so they don't flood the context just because
    # they are the only ones available (the "RSS takeover" fix).
    
    def get_prompt_cap_for_source(src: str) -> int:
        # Base cap from config (e.g. 2)
        base = max(1, per_source_cap)
        
        # Source weight
        sw = w.get(src, 0.0)
        
        # If this is a "filler" source (low weight), restrict expansion.
        if sw < 0.15: 
            # For small sources, allow at most +50% or +1 item over base cap
            return int(base * 1.5) + 1
            
        # For main sources, allow 3x expansion (let the LLM see variety)
        return base * 3

    # Prepare iterators
    idx = {s: 0 for s in present}

    # Keep looping until no progress
    while len(out) < max_prompt:
        progressed = False
        for s in present:
            if len(out) >= max_prompt:
                break
            
            # Use dynamic cap based on weight
            pcap = get_prompt_cap_for_source(s)
            
            if per_src_used[s] >= min(targets.get(s, 0), pcap):
                continue
            i = idx[s]
            if i >= len(buckets[s]):
                continue
            out.append(buckets[s][i])
            idx[s] += 1
            per_src_used[s] += 1
            progressed = True
        if not progressed:
            break

    return out[:max_prompt]

def producer_loop(stop_event: threading.Event, mem: Dict[str, Any]) -> None:
    """
    Zero show-language hardcoding.
    Fail-open uses only:
      - candidate fields already present
      - manifest-provided producer.failopen.* defaults (or empty)

    HARD MUTE:
      - mix.weights[src] <= 0 blocks that source entirely, including fail-open.
    """


    conn = db_connect()
    migrate_segments_table(conn)

    def _int(path: str, default: int) -> int:
        try:
            return int(cfg_get(path, default))
        except Exception:
            return default

    def _float(path: str, default: float) -> float:
        try:
            return float(cfg_get(path, default))
        except Exception:
            return default

    target_depth_cfg = max(_int("producer.target_depth", QUEUE_TARGET_DEPTH), 1)
    max_depth_cfg    = max(_int("producer.max_depth", QUEUE_MAX_DEPTH), target_depth_cfg)
    tick_sec         = max(_float("producer.tick_sec", PRODUCER_TICK_SEC), 0.25)

    prompt_max_candidates  = max(_int("producer.prompt_max_candidates", 36), 12)
    max_enqueue_per_cycle  = max(_int("producer.max_enqueue_per_cycle", 8), 2)

    producer_model = (cfg_get("models.producer", "") or "").strip()
    max_tokens     = max(_int("producer.max_tokens", 220), 80)
    temperature    = _float("producer.temperature", 0.6)

    min_db_runway      = max(_int("producer.min_db_runway", target_depth_cfg), 4)
    audio_low_water    = max(_int("producer.audio_low_water", max(2, AUDIO_TARGET_DEPTH // 2)), 1)
    audio_runway_boost = max(_int("producer.audio_runway_boost", 8), 2)

    # FAIL-OPEN defaults (manifest-driven)
    FO_ANGLE  = cfg_text("producer.failopen.angle", "")
    FO_WHY    = cfg_text("producer.failopen.why", "")
    FO_HINT   = cfg_text("producer.failopen.host_hint", "")
    FO_KEYPTS = cfg_list("producer.failopen.key_points", [])

    mem.setdefault("feed_candidates", [])
    mem.setdefault("_log_last", {})

    def _is_muted(src: str, mix_weights: Dict[str, Any]) -> bool:
        """
        Hard mute rule:
          if mix.weights has an explicit key for src and it's <= 0 -> muted
        If src not present in mix.weights -> treat as allowed (fail-open friendly).
        """
        try:
            if src in mix_weights:
                return float(mix_weights.get(src, 0.0) or 0.0) <= 0.0
        except Exception:
            pass
        return False


    # Threshold for opportunistic music resume (when queue is low)
    # Don't resume immediately after queue hits 0; wait for a confirmed gap using a threshold
    # Higher = safer (less cutoff), Lower = tighter (less dead air)
    resume_threshold = 2

    # Reset counter for forced drain if stuck
    drain_attempts = 0

    while not stop_event.is_set():
        # LIVE CONFIG UPDATE: refresh producer settings from CFG every tick
        target_depth_cfg = max(_int("producer.target_depth", QUEUE_TARGET_DEPTH), 1)
        max_depth_cfg    = max(_int("producer.max_depth", QUEUE_MAX_DEPTH), target_depth_cfg)
        tick_sec         = max(_float("producer.tick_sec", PRODUCER_TICK_SEC), 0.25)
        prompt_max_candidates  = max(_int("producer.prompt_max_candidates", 36), 12)
        max_enqueue_per_cycle  = max(_int("producer.max_enqueue_per_cycle", 8), 2)
        producer_model = (cfg_get("models.producer", "") or "").strip()
        max_tokens     = max(_int("producer.max_tokens", 220), 80)
        temperature    = _float("producer.temperature", 0.6)
        min_db_runway      = max(_int("producer.min_db_runway", target_depth_cfg), 4)
        audio_low_water    = max(_int("producer.audio_low_water", max(2, AUDIO_TARGET_DEPTH // 2)), 1)
        audio_runway_boost = max(_int("producer.audio_runway_boost", 8), 2)

        try:
            try:
                queued = db_depth_queued(conn)
            except Exception:
                queued = 0
            try:
                claimed = db_depth_inflight(conn)
            except Exception:
                claimed = 0
            # AUDIO_QUEUE SIZE IS THE KEY METRIC FOR "IS THE HOST TALKING?"
            try:
                # adjust queue size by -8 to account for the baseline buffer we always keep full
                # this treats 8 as "empty" (just buffer) and >8 as "actually talking"
                raw_q = int(audio_queue.qsize())
                audio_q = max(0, raw_q - 8)
            except Exception:
                audio_q = 0

            desired_runway = max(min_db_runway, target_depth_cfg)
            if audio_q <= audio_low_water:
                desired_runway = min(max_depth_cfg, desired_runway + audio_runway_boost)

            total_work = queued + claimed

            # explicit resume scheduling removed here — promotion handled
            # within producer decision logic so mix weights remain authoritative.
            
            # Sync DB stats to mem for plugins (like music_breaks)
            mem["_sys_db_queued"] = queued
            mem["_sys_db_claimed"] = claimed

            # heartbeat
            try:
                n_cand = len(mem.get("feed_candidates", []) or [])
                log_every(
                    mem, "producer_heartbeat", 6, "producer",
                    f"heartbeat db_queued={queued} claimed={claimed} audio_q={audio_q} "
                    f"desired_runway={desired_runway} candidates={n_cand} kick={producer_kick.is_set()}"
                )
            except Exception:
                pass

            # Hard block producer while visual_reader is actively running
            if mem.get("_visual_reader_active") is True:
                log_every(mem, "producer_blocked_visual", 2, "producer", "visual_reader active → blocking new segment generation")
                producer_kick.wait(timeout=tick_sec)
                producer_kick.clear()
                continue

            # FORCE refill when runway empty or low
            # if total_work < desired_runway:
            #    producer_kick.set()

            boundary_ts = mem.get("_music_boundary_active")

            boundary_live = (
                isinstance(boundary_ts, int) and
                (now_ts() - boundary_ts) <= 6   # 👈 6 second control window
            )

            # ✅ Check if we're managing a music pause
            paused_for_talk = mem.get("_music_paused_for_talk")
            managing_music_pause = isinstance(paused_for_talk, int)
            # If music is not playing (paused/stopped externally), treat as resume candidate.
            # This signals producer that resumption is allowed/preferred.
            # BUT: skip if allow_background_music=True (user wants always-on music + ducking)
            # AND: skip if music_breaks is hard-muted (weight <= 0)
            try:
                allow_bg = bool(MUSIC_STATE.get("allow_background_music", False))
                if allow_bg:
                    # Always-on mode: don't mess with pause/resume, just duck TTS
                    mem.pop("_producer_wants_music_candidate", None)
                else:
                    # Check if music is hard-muted before marking candidate
                    mix_weights = cfg_get("mix.weights", {}) or {}
                    music_w = 0.0
                    for k in ("music_breaks", "music", "music.breaks"):
                        if k in mix_weights:
                            try:
                                music_w = float(mix_weights.get(k) or 0.0)
                            except Exception:
                                music_w = 0.0
                            break
                    
                    if music_w <= 0.0:
                        # Music is hard-muted, don't even mark candidate
                        mem.pop("_producer_wants_music_candidate", None)
                    else:
                        # Interrupt mode: candidate logic applies
                        # But skip re-marking if we already have a decision flag pending
                        flows_enabled = bool(MUSIC_STATE.get("flows_enabled", False))
                        music_playing = bool(MUSIC_STATE.get("playing", False)) if flows_enabled else False
                        # Only treat a TRUE decision as pending; allow re-evaluation after a NO
                        has_decision_pending = mem.get("_producer_wants_music") is True
                        
                        if not music_playing and not has_decision_pending:
                            # Check for active break deadline (enforced by music_breaks)
                            break_deadline = mem.get("_mb_break_deadline", 0)
                            active_break = isinstance(break_deadline, (int, float)) and now_ts() < break_deadline
                            
                            if not active_break:
                                if not mem.get("_producer_wants_music_candidate"):
                                    mem["_producer_wants_music_candidate"] = True
                                    log("producer", "detected music not playing → marked resume candidate")
                            else:
                                # If break is active, ensure we DON'T have a candidate
                                mem.pop("_producer_wants_music_candidate", None)
                        else:
                            # music is playing or decision already pending, clear any stale candidate
                            if music_playing:
                                mem.pop("_producer_wants_music_candidate", None)
            except Exception as e:
                log("producer", f"ERROR checking music candidate: {e}")
            # Check if we have a candidate to promote (music paused by user)
            has_candidate = bool(mem.get("_producer_wants_music_candidate"))
            
            # Check if we're in a boundary talk window (queue-driven, not time-driven)
            # After boundary fires, suppress music requests until audio queue drains below threshold
            suppress_music_for_boundary = mem.get("_suppress_music_until_queue_drained", False)
            in_talk_window = suppress_music_for_boundary and audio_q > 2
            
            # If boundary flag is set but queue is idle, clear it (content has finished)
            if suppress_music_for_boundary and audio_q <= 1:
                mem.pop("_suppress_music_until_queue_drained", None)
                in_talk_window = False
            
            if not boundary_live and not managing_music_pause and not has_candidate:
                if total_work >= desired_runway or queued >= max_depth_cfg:
                    producer_kick.wait(timeout=tick_sec)
                    producer_kick.clear()
                    continue
            else:
                # Handle music boundary (initial trigger)
                if boundary_live:
                    # Check background music override
                    allow_bg = bool(MUSIC_STATE.get("allow_background_music", False))
                    
                    if allow_bg:
                        # Just clear the flag so we don't react again, but DO NOT pause
                        mem.pop("_music_boundary_active", None)
                        if callable(log):
                             log("producer", "music boundary (bg mode) → ignoring pause, ducking should handle it")
                    else:
                        log("producer", "music boundary → producer taking control")
                        
                        # Pause music for talk NOW
                        mem["_producer_wants_talk"] = now_ts()
                        mem["_music_paused_for_talk"] = now_ts()
                        mem.pop("_producer_wants_music", None)  # Clear any stale music request
                        
                        # Set queue-driven talk gate (suppress music until audio queue drains)
                        mem["_suppress_music_until_queue_drained"] = True
                        mem["_skip_music_decision_this_cycle"] = True

                        # reset any running music streak when we intentionally pause
                        mem["_music_streak"] = 0

                        # Do NOT schedule automatic resume—let the producer's decision loop
                        # (which respects mix.weights hard-mute) decide when to resume.
                        # Clear boundary so it doesn't retrigger
                        mem.pop("_music_boundary_active", None)
                
                # ✅ While waiting for resume, keep producer active but don't spam logs
                # ✅ While managing pause, keep producer active
                # ✅ Also run decision when there's a resume candidate (user paused)
                
                # Allow decision to run after boundary; music_breaks plugin enforces audio_q check
                # before actually playing to avoid competing with TTS
                debug_gate = (managing_music_pause or has_candidate) and not mem.get("_skip_music_decision_this_cycle")
                if not debug_gate and has_candidate:
                    skip_reason = ""
                    if mem.get("_skip_music_decision_this_cycle"):
                        skip_reason = "skip_flag_set"
                    log_every(mem, "producer_candidate_blocked", 3, "producer", f"candidate marked but gate blocked: {skip_reason}")
                
                if debug_gate:

                    if managing_music_pause:
                        
                        # Only permit resume decision if audio queue is genuinely draining
                        # If audio_q is HIGH, we are still actively "talking" even if no new segments claimed
                        if audio_q > resume_threshold:

                            # Detect STUCK queue (if audio_q never drops)
                            drain_attempts += 1
                            if drain_attempts > 100: # ~25 seconds of being stuck @ 4 polls/sec
                                 log("producer", f"WARNING: audio_q stuck at {audio_q} for too long -> forcing resume")
                                 drain_attempts = 0
                                 # FALL THROUGH to allow resume
                            else:
                                log_every(
                                    mem, "producer_resume_drain", 3, "producer",
                                    f"resume drain mode audio_q={audio_q} threshold={resume_threshold}"
                                )
                                # Wait for it to drain
                                producer_kick.wait(timeout=1.0)
                                continue
                        
                        # Reset stuck counter if we dip below threshold
                        drain_attempts = 0

                        log_every(
                            mem, "producer_managing_pause", 5, "producer",
                            f"managing music pause audio_q={audio_q}"
                        )
                    else:
                        log_every(
                            mem, "producer_candidate_promo", 5, "producer",
                            f"promoting resume candidate audio_q={audio_q}"
                        )
                    
                    # Producer can decide even if audio is queued; only the ACTUAL resume waits for silence
                    # (the decision just sets a flag; music_breaks plugin checks audio_q before resuming)
                    if True:  # Always allow decision to run if candidate/pause

                        # Probabilistic explicit-music decision
                        try:
                            # Check break window inside try block to leverage exception-based fallback
                            break_deadline = mem.get("_mb_break_deadline", 0)
                            if (isinstance(break_deadline, (int, float)) and 
                                now_ts() < break_deadline and 
                                managing_music_pause):
                                mem["_producer_wants_music"] = False
                                log_every(mem, "producer_break_suppress", 5, "producer", "break active → suppressing music resume")
                                raise Exception("break active")
                            mix_weights = cfg_get("mix.weights", {}) or {}
                            # find likely music weight (accept common keys)
                            music_w = 0.0
                            for k in ("music_breaks", "music", "music.breaks"):
                                if k in mix_weights:
                                    try:
                                        music_w = float(mix_weights.get(k) or 0.0)
                                    except Exception:
                                        music_w = 0.0
                                    break

                            # HARD MUTE: if music explicitly set to 0, don't even try to promote
                            if music_w <= 0.0:
                                mem.pop("_producer_wants_music_candidate", None)
                                mem.pop("_producer_wants_music", None)  # Also clear any existing request
                                log_every(mem, "music_hard_mute", 2, "producer", "music_breaks weight is 0 (hard muted) → skip resume")
                            else:
                                total_w = 0.0
                                for v in (mix_weights or {}).values():
                                    try:
                                        total_w += max(0.0, float(v or 0.0))
                                    except Exception:
                                        continue
                                norm_music = (music_w / total_w) if total_w > 0 else 0.0
                                
                                log_every(
                                    mem, "producer_mix_weights", 4, "producer",
                                    f"mix.weights: music={music_w:.2f} norm={norm_music:.2f} total_w={total_w:.2f}"
                                )

                                # Tag heat: high heat -> prefer talk; low heat -> safer to play
                                tag_heat = mem.get("tag_heat", {}) or {}
                                max_heat = 0.0
                                for tdata in tag_heat.values():
                                    try:
                                        h = float(tdata.get("heat", 0.0)) if isinstance(tdata, dict) else float(tdata or 0.0)
                                        if h > max_heat:
                                            max_heat = h
                                    except Exception:
                                        continue
                                heat_factor = max_heat / (max_heat + 20.0) if max_heat >= 0 else 0.0

                                streak = int(mem.get("_music_streak", 0) or 0)

                                # Promote candidate influence if present (paused session)
                                candidate = bool(mem.get("_producer_wants_music_candidate"))

                                # Compose a subjective probability
                                base = 0.05 + 0.7 * norm_music - 0.6 * heat_factor + 0.12 * min(streak, 4)

                                # If the music pause was user-triggered (candidate), bias
                                # the decision toward resuming, but still allow mix_weights
                                # and randomness to control outcome.
                                if candidate:
                                    base += 0.25

                                prob = max(0.01, min(0.92, base + (random.random() - 0.5) * 0.24))

                                # STICKY DECISION LOGIC:
                                # Once the producer decides to go to music, keep it active until satisfied.
                                # Unless explicitly cleared by music_breaks starting playback.
                                already_decided = mem.get("_producer_wants_music", False)
                                
                                # We stay in music mode if:
                                # 1. We were already in it (sticky), OR
                                # 2. We roll a new decision to enter it
                                should_music = already_decided or (random.random() < prob)

                                if should_music:
                                    # ✅ If no dedicated bridge has been spoken recently, FORCE one now
                                    # This ensures we don't just cut to music silently.
                                    last_bridge = mem.get("_last_music_bridge_ts", 0)
                                    resume_signaled = mem.get("_mb_resume_signaled")  # set by music_breaks on timeout

                                    # Only generate if we are not responding to an explicit deadline timeout (which usually already has a candidate)
                                    # AND we haven't bridged recently (last 30s)
                                    if (now_ts() - last_bridge > 30) and not resume_signaled:
                                        log("producer", "Music resume deciding -> generating bridge segment first")
                                        try:
                                            bridge_txt = clean(llm_generate(
                                                "Write a very short (1 sentence) radio bridge throwing back to the music. Energy: high. Context: talk break ending.",
                                                "You are a radio host. Return ONE sentence only.",
                                                model=CFG["models"]["host"],
                                                num_predict=80,
                                                temperature=0.8,
                                                timeout=20
                                            ))
                                            
                                            if bridge_txt:
                                                # Inject segment immediately
                                                seg = {
                                                    "id": sha1(f"bridge|{now_ts()}"),
                                                    "source": "producer_bridge",
                                                    "event_type": "bridge",
                                                    "title": "Back to Music",
                                                    "body": bridge_txt,
                                                    "priority": 100.0, # MAX PRIORITY
                                                    "host_hint": "High energy throw to music"
                                                }
                                                db_enqueue_segment(conn, seg)
                                                mem["_last_music_bridge_ts"] = now_ts()
                                                
                                                # Update queued stat so music_breaks sees it immediately if it checks
                                                queued += 1
                                                mem["_sys_db_queued"] = queued
                                        except Exception as e:
                                            log("producer", f"Bridge gen failed: {e}")

                                    mem["_producer_wants_music"] = True
                                    mem["_music_streak"] = streak + 1
                                    # Clear candidate when promoted
                                    try:
                                        mem.pop("_producer_wants_music_candidate", None)
                                    except Exception:
                                        pass
                                    if callable(log):
                                        log("producer", f"decide→music YES p={prob:.2f} norm_music={norm_music:.2f} heat={max_heat:.1f} streak={streak} candidate={candidate}")
                                else:
                                    # Only allow switching OFF music mode if we weren't already committed
                                    # (Sticky logic handles the 'should_music' check above)
                                    mem["_producer_wants_music"] = False
                                    if callable(log):
                                        log("producer", f"decide→music NO p={prob:.2f} norm_music={norm_music:.2f} heat={max_heat:.1f} streak={streak} candidate={candidate}")
                        except Exception:
                            # conservative fallback
                            try:
                                # Don't clear if sticky
                                if not mem.get("_producer_wants_music"):
                                    mem["_producer_wants_music"] = False
                            except Exception:
                                pass




            # Always clear the one-cycle skip flag at the end of the cycle
            mem.pop("_skip_music_decision_this_cycle", None)

            # ✅ Producer wants music back? Stop filling the queue so it can drain naturally.
            if mem.get("_producer_wants_music"):
                log_every(mem, "producer_wants_music_blocking", 4, "producer", "Producer wants music → blocking new segment generation")

                # INJECT TRANSITION SEGMENT (once per cycle)
                # This ensures the host "throws" to music at the END of the queue, not randomly before.
                if not mem.get("_music_transition_queued"):
                    try:
                        # Check last 5 seconds of segments to dedupe (noisy flip-flop protection)
                        # We don't want to re-queue if we just did it.
                        recent = conn.execute(
                            "SELECT created_ts FROM segments WHERE event_type='music_transition' AND created_ts > ? LIMIT 1;",
                            (int(time.time()) - 15,)
                        ).fetchone()
                        
                        if not recent:
                            # Only inject if we actually have a queue that needs a distinct ending.
                            # (priority=50.0 + current time ensures it slots at the END of the existing queue)
                            trans_seg = {
                                "id": "music_transition_" + str(int(time.time())),
                                "post_id": "music_transition",
                                "source": "system",
                                "event_type": "music_transition",
                                "title": "Music Transition",
                                "body": "Coming up next: Music.",
                                "angle": "Music is starting soon",
                                "why": "Transition to music",
                                "priority": 50.0,
                                "host_hint": "Brief, high energy throw to music.", 
                            }
                            if db_enqueue_segment(conn, trans_seg):
                                mem["_music_transition_queued"] = True
                                log("producer", "Injected music transition segment at end of queue")
                    except Exception as e:
                        log("producer", f"Failed to inject transition: {e}")

                producer_kick.wait(timeout=tick_sec)
                producer_kick.clear()
                continue
            
            # Reset transition flag only if we successfully stayed in TALK mode for a full tick
            # (clearing immediately on a flaky NO decision causes double-injection)
            mem.pop("_music_transition_queued", None)

            # If music is paused and we want to resume, drain audio queue before enqueueing more TTS
            resume_block_threshold = int(cfg_get("music.resume_block_audio_q", 2))
            if (managing_music_pause or has_candidate) and audio_q > resume_block_threshold:
                log_every(
                    mem, "producer_resume_drain", 4, "producer",
                    f"resume drain mode audio_q={audio_q} threshold={resume_block_threshold}"
                )
                producer_kick.wait(timeout=tick_sec)
                producer_kick.clear()
                continue

            need = min(desired_runway - total_work, max_enqueue_per_cycle)
            if need <= 0:
                producer_kick.wait(timeout=tick_sec)
                producer_kick.clear()
                continue

            # seen set
            try:
                seen = db_seen_set(conn)
            except Exception:
                seen = set()

            # candidates
            candidates_all = mem.get("feed_candidates", []) or []
            
            # Simple list cleaner to prevent corruption
            if not isinstance(candidates_all, list):
                candidates_all = []
            
            # Filter out malformed candidates to avoid downstream errors
            candidates_all = [c for c in candidates_all if isinstance(c, dict) and c.get("source")]
            
            mem["feed_candidates"] = candidates_all[-800:]
            candidates_all = mem["feed_candidates"]

            mix_weights = cfg_get("mix.weights", {}) or {}
            per_src_cap = _int("producer.per_source_cap", 4)

            budgeted_universe = apply_mix_budget(
                candidates_all=candidates_all,
                seen=seen,
                need=need,
                max_prompt=prompt_max_candidates,
                per_source_cap=per_src_cap,
                mix_weights_raw=mix_weights,
            )

            prompt_cands = pick_diverse_candidates(
                budgeted_universe, seen,
                need=need,
                per_source_cap=per_src_cap,
                max_prompt=prompt_max_candidates
            )

            if not prompt_cands:
                producer_kick.wait(timeout=0.5)
                producer_kick.clear()
                continue

            # -----------------------------
            # Curator discoveries
            # -----------------------------
            discoveries: List[Dict[str, Any]] = []
            if producer_model:
                try:
                    sys_prompt = curator_system_context(mem)
                    user_prompt = curator_candidates_prompt(mem, prompt_cands)

                    raw = llm_generate(
                        user_prompt,
                        sys_prompt,
                        model=producer_model,
                        num_predict=max_tokens,
                        temperature=temperature,
                        timeout=int(cfg_get("producer.timeout_sec", 60)),
                        force_json=True
                    )
                    plan = parse_json_lenient(raw) if raw else {}
                    if isinstance(plan, dict):
                        discoveries = plan.get("discoveries", []) if isinstance(plan.get("discoveries"), list) else []
                except Exception as e:
                    log("producer", f"curator error: {type(e).__name__}: {e}")
                    discoveries = []

            if not discoveries:
                discoveries = [_discovery_from_candidate(c) for c in prompt_cands[:max(need, 3)]]

            # sanitize discoveries
            discoveries = [d for d in discoveries if isinstance(d, dict) and (d.get("post_id") or d.get("id"))]
            if not discoveries:
                producer_kick.wait(timeout=0.5)
                producer_kick.clear()
                continue

            # lookup by post_id + id
            by_id: Dict[str, Dict[str, Any]] = {}
            for c in prompt_cands:
                if c.get("post_id"):
                    by_id[str(c["post_id"])] = c
                if c.get("id"):
                    by_id[str(c["id"])] = c

            discoveries_by_id: Dict[str, Dict[str, Any]] = {}
            for d in discoveries:
                pid = d.get("post_id") or d.get("id")
                if pid:
                    discoveries_by_id[str(pid)] = d

            # -----------------------------
            # Navigator decisions
            # -----------------------------
            nav_queue: List[Dict[str, Any]] = []
            navigator_model = (cfg_get("models.navigator", "") or producer_model).strip()
            if navigator_model:
                try:
                    nav_sys, nav_user = navigator_prompt(mem, discoveries)
                    raw = llm_generate(
                        nav_user,
                        nav_sys,
                        model=navigator_model,
                        num_predict=int(cfg_get("navigator.max_tokens", 160)),
                        temperature=float(cfg_get("navigator.temperature", 0.55)),
                        timeout=int(cfg_get("navigator.timeout_sec", 45)),
                        force_json=True
                    )
                    nav = parse_json_lenient(raw) if raw else {}
                    if isinstance(nav, dict):
                        nav_queue = nav.get("queue", []) if isinstance(nav.get("queue"), list) else []
                except Exception as e:
                    log("producer", f"navigator error: {type(e).__name__}: {e}")
                    nav_queue = []

            if not nav_queue:
                nav_queue = []
                for d in discoveries[:max(need, 3)]:
                    tags = d.get("tags", []) if isinstance(d.get("tags"), list) else []
                    nav_queue.append({
                        "target_id": d.get("post_id") or d.get("id"),
                        "move": "explore",
                        "focus": (tags[0] if tags else ""),
                        "energy": "medium",
                        "open_loop": "",
                        "lead_voice": ""
                    })

            enqueued = 0
            ws = ensure_world_state(mem)

            # -------------- enqueue from navigator --------------
            for decision in nav_queue:
                if enqueued >= need:
                    break
                if db_depth_queued(conn) >= max_depth_cfg:
                    break
                if not isinstance(decision, dict):
                    continue

                target_id = decision.get("target_id") or decision.get("post_id") or decision.get("id")
                if not target_id:
                    continue
                target_id = str(target_id)

                discovery = discoveries_by_id.get(target_id)
                base = by_id.get(target_id)
                if not discovery or not base:
                    continue

                src = (base.get("source") or "feed").strip().lower()
                if _is_muted(src, mix_weights):
                    log_every(mem, f"skip_mute_{src}", 3, "producer", f"skip_queuing muted_src={src} (weight<=0)")
                    continue
                if not can_enqueue_source(conn, src):
                    continue

                real_pid = base.get("post_id") or base.get("id")
                if not real_pid:
                    continue
                real_pid = str(real_pid)
                if real_pid in seen:
                    continue

                angle = (discovery.get("angle") or "").strip() or FO_ANGLE
                why = (discovery.get("why") or "").strip() or FO_WHY
                hint = (discovery.get("host_hint") or "").strip() or FO_HINT

                kps = discovery.get("key_points", [])
                if not isinstance(kps, list):
                    kps = []
                kps = [str(x)[:120] for x in kps if str(x).strip()][:5] or FO_KEYPTS

                pri = clamp_priority(discovery.get("priority"), fallback=float(base.get("heur", 50.0) or 50.0))

                seg_obj = {
                    "id": sha1(real_pid + "|" + str(now_ts()) + "|" + str(random.random())),
                    "post_id": real_pid,
                    "source": base.get("source", "feed"),
                    "event_type": base.get("event_type") or base.get("type") or "item",
                    "title": base.get("title", ""),
                    "body": base.get("body", ""),
                    "comments": base.get("comments", []),

                    "angle": angle,
                    "why": why,
                    "key_points": kps,
                    "priority": pri,
                    "host_hint": hint,

                    "discovery_type": discovery.get("type", "frontier"),
                    "discovery_tags": discovery.get("tags", []),
                    "move": decision.get("move", "explore"),
                    "focus": decision.get("focus", ""),
                    "open_loop": decision.get("open_loop", ""),
                    "energy": decision.get("energy", ""),
                    "lead_voice": decision.get("lead_voice", "")
                }

                if db_enqueue_segment(conn, seg_obj):
                    db_mark_seen(conn, [real_pid])
                    seen.add(real_pid)
                    enqueued += 1
                    update_world_state(ws, discovery, decision)

            save_memory_throttled(mem, min_interval_sec=1.5)

        except Exception as e:
            log("producer", f"error: {type(e).__name__}: {e}")

        time.sleep(tick_sec)

def update_themes_from_packet(packet, mem, max_themes=40):
    themes = mem.setdefault("themes", [])

    # Pull from grounding + summary
    new = []

    for f in packet.get("grounding", {}).get("hard_facts", []):
        txt = f.get("text","").lower()
        if txt:
            new.append(txt[:80])

    summary = packet.get("summary","").lower()
    if summary:
        new.append(summary[:80])

    for t in new:
        if t not in themes:
            themes.append(t)

    mem["themes"] = themes[-max_themes:]
    save_memory(mem)

# =======================
# Audio Rendering Engine
def render_segment_audio(seg: Dict[str, Any], mem: Dict[str, Any]) -> List[Tuple[str, str]]:
    """
    Deterministic flow compiler.

    Takes structured host packet content and outputs
    a conversational radio-style sequence.

    HARD RULE: NO LLM calls here.
    """

    bundle: List[Tuple[str, str]] = []

    lead_voice = resolve_lead_voice(seg, mem)

    # -------------------------
    # Cold open
    # -------------------------
    if seg.get("event_type") == "cold_open":
        # Prefer packet fields; fall back to body if needed
        line = clean(seg.get("host_intro", "")) or clean(seg.get("summary", ""))
        if not line:
            line = clean(seg.get("body", ""))
        return [(lead_voice, line)] if line else []

    # -------------------------
    # Host intro + summary
    # -------------------------
    intro = clean(seg.get("host_intro", ""))
    summary = clean(seg.get("summary", ""))

    if intro:
        bundle.append((lead_voice, intro))

    # Only speak summary if it's meaningfully different
    if summary:
        if not intro or summary[:120].lower() not in intro.lower():
            bundle.append((lead_voice, summary))


    # -------------------------
    # Comment reads (schema-safe)
    # -------------------------
    for cr in (seg.get("comment_reads") or []):
        line = clean(cr.get("read_line", "") or cr.get("line", ""))
        if line:
            bundle.append((lead_voice, line))

    # -------------------------
    # Perspectives (panel)
    # -------------------------
    perspectives = seg.get("panel") or seg.get("perspectives") or []

    for p in perspectives:
        voice = (p.get("voice") or "").strip().lower()
        line = clean(p.get("line", ""))

        if not voice or not line:
            continue

        bundle.append((voice, line))

    # -------------------------
    # Host takeaway
    # -------------------------
    takeaway = clean(seg.get("host_takeaway", ""))

    if takeaway:
        bundle.append((lead_voice, takeaway))

    # -------------------------
    # Final cleanup + pacing
    # -------------------------
    bundle = [(v, t) for v, t in bundle if t]

    max_lines = int(cfg_get("flow.max_lines_per_segment", 10))
    if max_lines > 0:
        bundle = bundle[:max_lines]

    return bundle

def make_teaser_bundle(seg: Dict[str, Any]) -> List[Tuple[str, str]]:
    title = clean(seg.get("title", ""))
    src   = clean(seg.get("source", ""))
    if not title:
        title = "Alright—quick update."
    # ultra-short, no cringe, no meta
    line = f"{title}"
    # optional tiny source tag (kept subtle)
    if src and src not in ("feed", "reddit"):
        line = f"{line}"
    return [("host", line)]

def claim_reaper_worker(
    stop_event: threading.Event,
    mem: Dict[str, Any],
    *,
    every_sec: int = 3,
    older_than_sec: int = 45,
) -> None:
    """
    Independent safety net:
    - If TTS hangs after claiming, this worker requeues the claim.
    - Must have its own DB connection (never shares with TTS).
    """
    conn = db_connect()
    migrate_segments_table(conn)

    while not stop_event.is_set():
        try:
            n = db_reclaim_stuck_claims(conn, older_than_sec=older_than_sec)
            if n:
                log("reaper", f"Requeued stuck claimed rows n={n} older_than_sec={older_than_sec}")
                # wake producer/host pipelines
                producer_kick.set()
        except Exception as e:
            log("reaper", f"error: {type(e).__name__}: {e}")

        time.sleep(max(1, int(every_sec)))

    try:
        conn.close()
    except Exception:
        pass


def rebalancer_worker(
    stop_event: threading.Event,
    mem: Dict[str, Any],
    *,
    every_sec: int = 10,
    max_prune_per_run: int = 128,
) -> None:
    """
    Background rebalancer:
    - Ensures the queued segments do not exceed `producer.max_depth` (or pacing.queue_max_depth fallback).
    - Respects `producer.source_limits` when pruning.
    - Prunes only `queued` rows (never claimed) and favors low-priority/old rows.
    - Uses its own DB connection.
    """
    conn = db_connect()
    migrate_segments_table(conn)

    while not stop_event.is_set():
        try:
            try:
                queued = db_depth_queued(conn)
            except Exception:
                queued = 0

            # determine configured max depth
            try:
                max_depth_cfg = max(int(cfg_get("producer.max_depth", QUEUE_MAX_DEPTH)), 1)
            except Exception:
                max_depth_cfg = QUEUE_MAX_DEPTH

            if queued <= max_depth_cfg:
                time.sleep(max(1, int(every_sec)))
                continue
            
            # Log when we're about to prune
            log_every(mem, "rebalancer_need_prune", 3, "rebalancer",
                     f"queue excess: queued={queued} > max_depth={max_depth_cfg}, need to prune {queued - max_depth_cfg} rows")

            need = min(int(queued - max_depth_cfg), int(max_prune_per_run))

            limits_all = cfg_get("producer.source_limits", {}) or {}

            # First, try to prune from sources that explicitly exceed their max_abs
            counts = db_counts_by_source(conn, statuses=("queued",))
            pruned = 0

            for src, limits in (limits_all or {}).items():
                if not isinstance(limits, dict):
                    continue
                try:
                    max_abs = limits.get("max_abs")
                    if max_abs is None:
                        continue
                    key = _normalize_source_alias(src)
                    cur_count = int(counts.get(key, 0) or 0)
                    if cur_count > int(max_abs) and need > 0:
                        to_prune = min(need, cur_count - int(max_abs))
                        cur = conn.execute(
                            "SELECT id FROM segments WHERE status='queued' AND COALESCE(source,'feed')=? ORDER BY priority ASC, created_ts ASC LIMIT ?;",
                            (src, to_prune)
                        ).fetchall()
                        ids = [r[0] for r in cur]
                        if ids:
                            qmarks = ",".join(["?"] * len(ids))
                            conn.execute(f"DELETE FROM segments WHERE id IN ({qmarks});", tuple(ids))
                            conn.commit()
                            pruned += len(ids)
                            need -= len(ids)
                            log("rebalancer", f"pruned n={len(ids)} src={src} (cur={cur_count} > max_abs={max_abs})")
                        if need <= 0:
                            break
                except Exception:
                    continue

            # If still need to prune, fall back to global oldest low-priority queued rows
            if need > 0:
                cur = conn.execute(
                    "SELECT id FROM segments WHERE status='queued' ORDER BY priority ASC, created_ts ASC LIMIT ?;",
                    (need,)
                ).fetchall()
                ids = [r[0] for r in cur]
                if ids:
                    qmarks = ",".join(["?"] * len(ids))
                    conn.execute(f"DELETE FROM segments WHERE id IN ({qmarks});", tuple(ids))
                    conn.commit()
                    pruned += len(ids)
                    need -= len(ids)
                    log("rebalancer", f"pruned {len(ids)} queued rows globally to reduce queue")

            if pruned:
                producer_kick.set()
                log("rebalancer", f"Pruned total n={pruned} to enforce producer.max_depth={max_depth_cfg}")

        except Exception as e:
            log("rebalancer", f"error: {type(e).__name__}: {e}")

        time.sleep(max(1, int(every_sec)))

    try:
        conn.close()
    except Exception:
        pass

# =======================
# TTS Worker
# =======================
def _allowed_panel_voices() -> List[str]:
    """
    Manifest-driven: all characters except the lead character.
    Does NOT depend on audio playability.
    """
    chars = CFG.get("characters", {}) or {}
    lead = resolve_lead_voice(mem=STATION_MEMORY)
    out = []
    for name in chars.keys():
        n = (name or "").strip().lower()
        if n and n != lead:
            out.append(n)
    return out


def _panel_min_count() -> int:
    # optional manifest knob: tts.panel_min (default 2)
    try:
        return int(cfg_get("tts.panel_min", 2))
    except Exception:
        return 2

WIDGETS = WidgetRegistry()
def _panel_max_count() -> int:
    # optional manifest knob: tts.panel_max (default 3)
    try:
        return int(cfg_get("tts.panel_max", 3))
    except Exception:
        return 3


def _normalize_packet(pkt: Dict[str, Any], allowed: List[str]) -> Dict[str, Any]:
    """
    Validation + normalization only. No content invention.
    """
    if not isinstance(pkt, dict):
        pkt = {}

    host_intro = clean(str(pkt.get("host_intro", "")))[:700]
    summary    = clean(str(pkt.get("summary", "")))[:900]
    takeaway   = clean(str(pkt.get("host_takeaway", "")))[:550]

    panel_in = pkt.get("panel", [])
    if not isinstance(panel_in, list):
        panel_in = []

    seen = set()
    panel_out: List[Dict[str, str]] = []

    for p in panel_in:
        if not isinstance(p, dict):
            continue

        v = (p.get("voice") or "").strip().lower()
        line = clean(str(p.get("line", "")))[:320]

        if not v or not line:
            continue
        if v not in allowed:
            continue
        if v in seen:
            continue

        seen.add(v)
        panel_out.append({"voice": v, "line": line})

    # clamp only (do not fill)
    mx = max(0, _panel_max_count())
    if mx > 0:
        panel_out = panel_out[:mx]

    return {
        "host_intro": host_intro,
        "summary": summary,
        "panel": panel_out,
        "host_takeaway": takeaway,
    }


def _host_packet_system_manifest(mem: Dict[str, Any], allowed: List[str], lead_voice: str) -> str:
    """
    Manifest-driven system prompt. No hardcoded characters.
    Uses compiled character prompts (already derived from manifest roles/traits/focus).
    """
    # Build a readable roster from manifest
    roster_lines = []
    chars = CFG.get("characters", {}) or {}
    for v in allowed:
        cfg = chars.get(v, {}) or {}
        role = (cfg.get("role") or "").strip()
        traits = cfg.get("traits") or []
        focus = cfg.get("focus") or []
        parts = []
        if role:
            parts.append(f"role={role}")
        if traits:
            parts.append("traits=" + ", ".join([str(x) for x in traits]))
        if focus:
            parts.append("focus=" + ", ".join([str(x) for x in focus]))
        if parts:
            roster_lines.append(f"- {v}: " + " | ".join(parts))

    roster = "\n".join(roster_lines) if roster_lines else "(no panel voices configured)"

    show = SHOW_NAME
    themes = mem.get("themes", [])[-12:]
    callbacks = mem.get("callbacks", [])[-10:]
    min_n = _panel_min_count()
    max_n = _panel_max_count()

    allowed_p_str = '|'.join(allowed)

    return get_prompt(
        mem, "host_packet_system",
        show_name=show,
        min_n=min_n,
        max_n=max_n,
        roster=roster,
        allowed_p_str=allowed_p_str,
        themes=themes,
        callbacks=callbacks,
        lead_voice=lead_voice
    ).strip()


def _panel_repair(pkt: Dict[str, Any], seg: Dict[str, Any], mem: Dict[str, Any], allowed: List[str], lead_voice: str) -> Dict[str, Any]:
    """
    One extra LLM call ONLY if panel is missing/short.
    This does not 'program characters' — it asks the model to fill missing entries.
    """
    min_n = _panel_min_count()
    if min_n <= 0:
        return pkt

    cur_panel = pkt.get("panel", []) if isinstance(pkt.get("panel"), list) else []
    if len(cur_panel) >= min_n:
        return pkt

    sys = _host_packet_system_manifest(mem, allowed, lead_voice)

    # Provide the existing packet and ask ONLY to add missing panel lines.
    prm = get_prompt(
        mem, "host_packet_repair_user",
        existing_json=json.dumps(pkt, ensure_ascii=False),
        title=seg.get("title",""),
        angle=seg.get("angle",""),
        why=seg.get("why",""),
        key_points=seg.get("key_points", []),
        material=(seg.get("body","") or "")[:900],
        min_n=min_n
    ).strip()

    raw = llm_generate(
        prompt=prm,
        system=sys,
        model=CFG["models"]["host"],
        num_predict=int(cfg_get("host.max_tokens", 180)),
        temperature=float(cfg_get("host.temperature", 0.6)),
        timeout=35,
        force_json=True,
    )

    repaired = parse_json_lenient(raw)
    repaired = _normalize_packet(repaired, allowed)

    # Ensure we didn’t accidentally blank host content
    if not repaired.get("host_intro") and pkt.get("host_intro"):
        repaired["host_intro"] = pkt["host_intro"]
    if not repaired.get("summary") and pkt.get("summary"):
        repaired["summary"] = pkt["summary"]
    if not repaired.get("host_takeaway") and pkt.get("host_takeaway"):
        repaired["host_takeaway"] = pkt["host_takeaway"]

    return repaired


# =======================
# Character Manager (Context Engine Router)
# =======================

def _normalize_context_sources(context_engine: Any) -> List[Dict[str, Any]]:
    """Normalize context_engine config into a list of enabled sources."""
    if not context_engine:
        return []

    if isinstance(context_engine, dict) and context_engine.get("enabled") is False:
        return []

    sources: List[Dict[str, Any]] = []
    if isinstance(context_engine, list):
        sources = [s for s in context_engine if isinstance(s, dict)]
    elif isinstance(context_engine, dict) and isinstance(context_engine.get("sources"), list):
        sources = [s for s in (context_engine.get("sources") or []) if isinstance(s, dict)]
    elif isinstance(context_engine, dict):
        sources = [context_engine]

    out: List[Dict[str, Any]] = []
    for i, src in enumerate(sources, 1):
        if src.get("enabled") is False:
            continue
        normalized = dict(src)
        normalized.setdefault("id", normalized.get("name") or normalized.get("label") or f"source_{i}")
        out.append(normalized)

    return out


def _format_context_block(
    result: Any,
    engine_type: str,
    char_name: str,
    source_cfg: Dict[str, Any],
    reason: str
) -> str:
    """Format context engine data with per-source flags for prompt injection."""
    source_id = source_cfg.get("id") or source_cfg.get("name") or "source"
    header = f"[{char_name} Context:{source_id} - {reason}]"
    flags = []
    if source_cfg.get("hard_facts_only"):
        flags.append("HARD FACTS ONLY: use only verified facts below")
    if source_cfg.get("motivation"):
        flags.append("MOTIVATION MODE: use this to shape character intent")
    notes = source_cfg.get("notes")
    if notes:
        flags.append(f"Notes: {notes}")

    formatted = format_context_for_prompt(result, engine_type)
    if flags:
        return header + "\n" + "\n".join(flags) + "\n" + formatted
    return header + "\n" + formatted

def character_manager_lookup(seg: Dict[str, Any], panel_voices: List[str], mem: Dict[str, Any]) -> Tuple[Optional[str], List[str]]:
    """
    Character Manager: Decides which characters are relevant and queries their context engines.
    
    Args:
        seg: Segment being generated
        panel_voices: Available panel voices for this segment
        mem: Station memory
    
    Returns:
        Tuple of (formatted context string or None, prioritized character list)
    """
    if not HAS_CONTEXT_ENGINE:
        return None, panel_voices
    
    # Get character configs
    chars = CFG.get("characters", {})
    if not chars:
        return None, panel_voices
    
    # Find characters with context engines enabled
    context_chars = {}
    for char_name in panel_voices:
        char_cfg = chars.get(char_name, {})
        ctx_engine = char_cfg.get("context_engine", {})
        sources = _normalize_context_sources(ctx_engine)
        if sources:
            context_chars[char_name] = {
                "config": char_cfg,
                "sources": sources
            }
    
    # Use Character Manager model to decide character relevance
    manager_model = cfg_get("models.character_manager") or CFG["models"].get("host")
    
    # Build prompt for Character Manager - show ALL characters
    char_summaries = []
    all_char_names = []
    for char_name in panel_voices:
        char_cfg = chars.get(char_name, {})
        all_char_names.append(char_name)
        focus = char_cfg.get("focus", [])
        role = char_cfg.get("role", "")
        traits = char_cfg.get("traits", [])
        
        parts = []
        if role:
            parts.append(f"Role: {role}")
        if focus:
            parts.append(f"Focus: {', '.join(focus)}")
        if traits:
            parts.append(f"Traits: {', '.join(traits)}")
        
        # Check if has context engine
        has_engine = char_name in context_chars
        if has_engine:
            parts.append("[Has context engine]")
        
        char_summaries.append(
            f"- {char_name}: {' | '.join(parts) if parts else 'general contributor'}"
        )
    
    manager_prompt = f"""You are the Character Manager for a radio station.

AVAILABLE CHARACTERS:
{chr(10).join(char_summaries)}

CURRENT SEGMENT:
Title: {seg.get('title', '')}
Angle: {seg.get('angle', '')}
Why: {seg.get('why', '')}
Key Points: {', '.join(seg.get('key_points', []))}
Content: {(seg.get('body', '') or '')[:400]}

Your job: 
1. Rank ALL characters by relevance to this segment (most relevant first)
2. For relevant characters with context engines, specify what data to fetch

Output JSON:
{{
  "priority_order": ["char1", "char2", "char3", ...],
  "context_queries": [
    {{
      "character": "character_name",
      "source_id": "source_id",
      "query_params": {{"param1": "value1"}},
      "reason": "why this data is needed"
    }}
  ]
}}

Rules:
- priority_order must include ALL characters, ranked by segment relevance
- context_queries only for characters with [Has context engine] that need data
- Empty context_queries [] if no context needed"""

    try:
        raw = llm_generate(
            prompt=manager_prompt,
            system="You are a character relevance analyzer. Output valid JSON only.",
            model=manager_model,
            num_predict=300,
            temperature=0.3,
            timeout=20,
            force_json=True
        )
        
        response = parse_json_lenient(raw)
        if not isinstance(response, dict):
            return None, panel_voices
        
        priority_order = response.get("priority_order", [])
        context_queries = response.get("context_queries", [])
        
        # Validate priority order contains known characters
        valid_priority = [c for c in priority_order if c in all_char_names]
        # Add any missing characters at the end
        for char in all_char_names:
            if char not in valid_priority:
                valid_priority.append(char)
        
        if not isinstance(context_queries, list):
            context_queries = []
        
    except Exception as e:
        log("char_mgr", f"Character Manager decision error: {e}")
        return None, panel_voices
    
    # Execute context queries
    context_results = []
    station_dir = STATION_DIR
    
    for decision in context_queries:
        char_name = decision.get("character")
        source_id = decision.get("source_id")
        query_params = decision.get("query_params", {})
        reason = decision.get("reason", "")
        
        if char_name not in context_chars:
            continue

        sources = context_chars[char_name]["sources"]
        engine_config = None
        if source_id:
            engine_config = next((s for s in sources if s.get("id") == source_id), None)
        if engine_config is None and len(sources) == 1:
            engine_config = sources[0]
        if engine_config is None:
            continue

        embedding_model = (cfg_get("models.embedding", "") or "").strip()
        embedding_enabled = bool(cfg_get("embedding.enabled", False))
        if embedding_model:
            llm_cfg = CFG.get("llm") if isinstance(CFG.get("llm"), dict) else {}
            engine_config = dict(engine_config)
            engine_config["embedding_model"] = embedding_model
            engine_config["embedding_provider"] = (llm_cfg.get("provider") or "ollama").strip().lower()
            engine_config["embedding_endpoint"] = (llm_cfg.get("endpoint") or "").strip()
            engine_config["embedding_api_key_env"] = (llm_cfg.get("api_key_env") or "").strip()
            engine_config["embedding_enabled"] = embedding_enabled
        
        # Query the context engine
        try:
            result = query_context_engine(engine_config, query_params, station_dir)
            if result:
                engine_type = engine_config.get("type", "unknown")
                formatted = _format_context_block(result, engine_type, char_name, engine_config, reason)
                context_results.append(formatted)
                log("char_mgr", f"Context fetched for {char_name}: {reason}")
        except Exception as e:
            log("char_mgr", f"Context query error for {char_name}: {e}")
            continue
    
    # Return both context data and priority order
    context_data = "\n\n".join(context_results) if context_results else None
    return context_data, valid_priority


def generate_host_packet(seg: Dict[str, Any], mem: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Manifest-driven structured packet generation.
    No Python-side panel composition. No voice playability gating.
    """
    lead_voice = resolve_lead_voice(seg, mem)
    allowed = ["host"] + _allowed_panel_voices()
    panel_allowed = [v for v in allowed if v != "host"]

    # ============================================
    # CHARACTER MANAGER: Context Engine Lookup & Priority
    # ============================================
    context_data = None
    prioritized_chars = panel_allowed  # Default to manifest order
    if HAS_CONTEXT_ENGINE:
        try:
            context_data, prioritized_chars = character_manager_lookup(seg, panel_allowed, mem)
        except Exception as e:
            log("tts", f"Character Manager error: {e}")
            context_data, prioritized_chars = None, panel_allowed

    # Use prioritized character order for system prompt
    sys = _host_packet_system_manifest(mem, prioritized_chars, lead_voice)

    # Build prompt with optional context injection
    comments = seg.get("comments", []) or []
    comment_block = "\n".join(
        f"[{i}] {c}" for i, c in enumerate(comments[:HOST_MAX_COMMENTS])
    ) or "(no comments)"

    prm = get_prompt(
        mem, "host_packet_user",
        lead_voice=lead_voice,
        move=seg.get("move", ""),
        focus=seg.get("focus", ""),
        energy=seg.get("energy", ""),
        open_loop=seg.get("open_loop", ""),
        title=seg.get("title", ""),
        angle=seg.get("angle", ""),
        why=seg.get("why", ""),
        key_points=seg.get("key_points", []),
        tags=seg.get("discovery_tags", []) or seg.get("tags", []),
        material=(seg.get("body", "") or "")[:900],
        comments=comment_block
    ).strip()
    
    # Inject context data if available
    if context_data:
        prm = context_data + "\n\n" + prm

    try:
        raw = llm_generate(
            prompt=prm,
            system=sys,
            model=CFG["models"]["host"],
            num_predict=int(cfg_get("host.max_tokens", 180)),
            temperature=float(cfg_get("host.temperature", 0.6)),
            timeout=35,
            force_json=True,
        )
        raw_pkt = parse_json_lenient(raw)
    except Exception as e:
        log("tts", f"host packet exception: {type(e).__name__}: {e}")
        raw_pkt = {}

    # Map interpreter schema to legacy packet fields
    pkt = raw_pkt if isinstance(raw_pkt, dict) else {}
    if any(k in pkt for k in ("lead_line", "supporting_lines", "takeaway")):
        pkt = {
            "host_intro": pkt.get("lead_line", ""),
            "summary": pkt.get("followup_line", ""),
            "panel": pkt.get("supporting_lines", []),
            "host_takeaway": pkt.get("takeaway", ""),
            "callback": pkt.get("callback", "")
        }

    pkt = _normalize_packet(pkt, panel_allowed)
    pkt["lead_voice"] = lead_voice

    # Fail only if we truly got nothing useful
    if not pkt.get("host_intro") and not pkt.get("summary"):
        return None

    return pkt


def select_voice_intents(seg: Dict[str, Any], mem: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    text = " ".join([
        " ".join(seg.get("key_points", []) or []),
        seg.get("angle",""),
        seg.get("why",""),
        (seg.get("title","") or ""),
        (seg.get("body","") or "")[:1200],
    ]).lower()

    chars = (CFG.get("characters") or {})
    lead = resolve_lead_voice(mem=mem)
    names = [n for n in chars.keys() if n and n.lower().strip() != lead]
    if not names:
        return []

    scored = []
    for name, cfg in chars.items():
        if name.lower().strip() == lead:
            continue
        focus  = [str(x).lower() for x in (cfg.get("focus") or [])]
        traits = [str(x).lower() for x in (cfg.get("traits") or [])]
        signals = [s for s in (focus + traits) if s]

        score = 0
        for s in signals:
            if s in text:
                score += 2
            # tiny fuzz: word-level contains
            if any(tok == s for tok in text.split()):
                score += 1

        scored.append((name, score, cfg))

    scored.sort(key=lambda x: x[1], reverse=True)

    # how many voices?
    max_voices = int(cfg_get("voices.max_per_segment", 2))
    max_voices = max(1, min(max_voices, 3))

    # if nothing matches, use balance_boost to favor underused voices
    if scored and scored[0][1] <= 0:
        def diversity_boost(name):
            lru = mem.setdefault("voice_lru", [])
            return -5 if name in lru[-5:] else 0
        
        def balance_boost(name):
            """Boost underused characters to ensure equal airtime."""
            try:
                from plugins.character_mix import get_balance_boost
                return get_balance_boost(name, mem)
            except Exception:
                return 0.0
        
        # Score each voice by balance + diversity
        balanced_scores = [
            (name, diversity_boost(name) + balance_boost(name), cfg)
            for name, _, cfg in scored
        ]
        balanced_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Pick the most underutilized voice
        pick = balanced_scores[0][0]
        
        # Update LRU
        lru = mem.setdefault("voice_lru", [])
        lru.append(pick)
        mem["voice_lru"] = lru[-20:]
        save_memory_throttled(mem, min_interval_sec=2.0)

        cfg = chars.get(pick, {})
        meta = {
            "intent": "fresh angle",
            "focus": ", ".join(cfg.get("focus", [])),
            "context": seg.get("angle",""),
            "emotion": "neutral",
            "relevance_score": 0
        }
        return [(pick, meta)]

    # otherwise take top relevant voices
    lru = mem.setdefault("voice_lru", [])

    def diversity_boost(name):
        return -5 if name in lru[-5:] else 0
    
    def balance_boost(name):
        """Boost underused characters to ensure equal airtime."""
        try:
            from plugins.character_mix import get_balance_boost
            return get_balance_boost(name, mem)
        except Exception:
            return 0.0

    scored2 = [
    (name, score + diversity_boost(name) + balance_boost(name), cfg)
    for name, score, cfg in scored
    ]

    scored2.sort(key=lambda x: x[1], reverse=True)
    chosen = scored2[:max_voices]
    out = []
    for name, score, cfg in chosen:
        # Allow slightly negative scores if character has strong balance boost
        # (they were already chosen as top candidates)
        if score < -3:
            continue
        meta = {
            "intent": "relevant reaction",
            "focus": ", ".join(cfg.get("focus", [])),
            "context": seg.get("angle",""),
            "emotion": "neutral",
            "relevance_score": score
        }
        out.append((name, meta))

        # still empty? guarantee one
        # still empty? guarantee one
        if not out:
            pick = scored[0][0]
            cfg = chars.get(pick, {})
            out = [(pick, {
                "intent": "fresh angle",
                "focus": ", ".join(cfg.get("focus", [])),
                "context": seg.get("angle",""),
                "emotion": "neutral",
                "relevance_score": 0
            })]

        # --------------------
        # Update LRU with chosen voices
        # --------------------
        lru = mem.setdefault("voice_lru", [])

        for name, _ in out:
            if name in lru:
                lru.remove(name)
            lru.append(name)

        mem["voice_lru"] = lru[-20:]
        save_memory_throttled(mem, min_interval_sec=2.0)

        return out


# =======================
# Segment Rejection System
# =======================

def check_segment_rejection(seg: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Check if a segment should be rejected based on rejection keywords from manifest.

    Returns:
        (is_rejected, reason) - is_rejected is True if segment should be filtered out
    """
    rejection_cfg = CFG.get("rejection", {})
    if not isinstance(rejection_cfg, dict):
        return (False, None)

    keywords = rejection_cfg.get("keywords", [])
    if not keywords or not isinstance(keywords, list):
        return (False, None)

    # Check case-insensitive keywords in title, body, and post_id
    title = (seg.get("title", "") or "").lower()
    body = (seg.get("body", "") or "").lower()
    post_id = (seg.get("post_id", "") or "").lower()

    search_text = f"{title} {body} {post_id}"

    for keyword in keywords:
        keyword = (keyword or "").strip().lower()
        if not keyword:
            continue

        if keyword in search_text:
            return (True, f"keyword '{keyword}' found")

    return (False, None)


def tts_worker(stop_event: threading.Event, mem: Dict[str, Any]) -> None:
    """
    Parallel buffered TTS pipeline.

    Guarantees:
      - Claimed segments NEVER stall the station
      - LLM failure never causes silence
      - NO hardcoded language
      - Uses extractive fallback only
      - NEVER nukes a valid packet
    """

    conn = db_connect()
    migrate_segments_table(conn)

    empty_sleep = float(cfg_get("tts.empty_sleep_sec", 0.05))
    backpressure_sleep = float(cfg_get("tts.backpressure_sleep_sec", 0.05))

    # -------------------------
    # Extractive fail-open packet
    # -------------------------
    def extractive_packet(seg: Dict[str, Any]) -> Dict[str, Any]:
        title = clean(seg.get("title", ""))[:500]
        body  = clean((seg.get("body", "") or "")[:1200])

        pkt: Dict[str, Any] = {"panel": []}

        if title:
            pkt["host_intro"] = title

        if body:
            pkt["summary"] = body

        pkt["host_takeaway"] = ""

        return pkt

    while not stop_event.is_set():

        try:
            # -------------------------
            # Heartbeat
            # -------------------------
            log_every(
                mem,
                "tts_heartbeat",
                6,
                "tts",
                f"heartbeat db_queued={db_depth_queued(conn)} audio_q={audio_queue.qsize()}"
            )

            # =====================================================
            # Fill audio buffer
            # =====================================================
            while audio_queue.qsize() < AUDIO_TARGET_DEPTH:

                if stop_event.is_set():
                    break

                seg = db_pop_next_segment(conn)
                if not seg:
                    break

                # -------------------------
                # Rejection filter
                # -------------------------
                is_rejected, reject_reason = check_segment_rejection(seg)
                if is_rejected:
                    source = (seg.get("source") or "feed").lower()
                    title  = (seg.get("title") or "")[:60]
                    log("tts", f"REJECTED seg source={source} title={title} reason={reject_reason}")
                    try:
                        db_mark_done(conn, seg["id"])
                    except Exception:
                        pass
                    continue

                source = (seg.get("source") or "feed").lower()
                title  = (seg.get("title") or "")[:60]

                log("tts", f"Claimed seg source={source} title={title}")

                pkt: Optional[Dict[str, Any]] = None

                # -------------------------
                # Cold open
                # -------------------------
                if (seg.get("event_type") or "").strip().lower() == "cold_open":
                    try:
                        pkt = generate_cold_open_packet(seg, mem)
                    except Exception as e:
                        log("tts", f"cold open exception: {type(e).__name__}: {e}")
                        pkt = None

                # -------------------------
                # Normal host packet
                # -------------------------
                if pkt is None:
                    try:
                        pkt = generate_host_packet(seg, mem)
                    except Exception as e:
                        log("tts", f"host packet exception: {type(e).__name__}: {e}")
                        pkt = None

                # -------------------------
                # FAIL OPEN (ONLY ON TRUE FAILURE)
                # -------------------------
                if pkt is None or not isinstance(pkt, dict):
                    pkt = extractive_packet(seg)

                # -------------------------
                # HARDEN PACKET (never wipe fields)
                # -------------------------
                if "panel" not in pkt or not isinstance(pkt.get("panel"), list):
                    pkt["panel"] = []

                if "host_intro" not in pkt:
                    pkt["host_intro"] = ""

                if "summary" not in pkt:
                    pkt["summary"] = ""

                if "host_takeaway" not in pkt:
                    pkt["host_takeaway"] = ""

                seg2 = dict(seg)
                seg2.update(pkt)
                try:
                    log("tts", f"PACKET lens intro={len(seg2.get('host_intro','') or '')} "
                            f"summary={len(seg2.get('summary','') or '')} "
                            f"panel={len(seg2.get('panel') or [])} "
                            f"takeaway={len(seg2.get('host_takeaway','') or '')}")
                except Exception:
                    pass

                # -------------------------
                # Render bundle
                # -------------------------
                try:
                    bundle = render_segment_audio(seg2, mem)
                except Exception as e:
                    log("tts", f"render error: {type(e).__name__}: {e}")
                    bundle = []

                # -------------------------
                # If nothing to play → mark done
                # -------------------------
                if not bundle:
                    try:
                        db_mark_done(conn, seg["id"])
                    except Exception:
                        pass
                    continue

                # -------------------------
                # Backpressure
                # -------------------------
                while audio_queue.qsize() >= AUDIO_MAX_DEPTH:
                    if stop_event.is_set():
                        break
                    time.sleep(backpressure_sleep)

                if stop_event.is_set():
                    break

                # -------------------------
                # Buffer audio
                # -------------------------
                audio_queue.put(AudioItem(bundle=bundle, seg=seg2))

                log(
                    "tts",
                    f"Buffered bundle lines={len(bundle)} audio_q={audio_queue.qsize()}"
                )

                # -------------------------
                # Mark segment done
                # -------------------------
                try:
                    db_mark_done(conn, seg["id"])
                except Exception:
                    pass

            # =====================================================
            # Idle sleep
            # =====================================================
            if audio_queue.qsize() == 0 and db_depth_queued(conn) == 0:
                time.sleep(empty_sleep)
            else:
                time.sleep(0.01)

        except Exception as e:
            log("tts", f"WORKER ERROR: {type(e).__name__}: {e}")
            time.sleep(0.15)

    try:
        conn.close()
    except Exception:
        pass


def run_thread(name: str, fn, *args, **kwargs):
    try:
        log("boot", f"{name} starting")
        fn(*args, **kwargs)
        log("boot", f"{name} exited normally")
    except Exception as e:
        # This is the missing piece: threads DO die silently otherwise
        log("FATAL", f"{name} crashed: {type(e).__name__}: {e}")
        import traceback
        tb = traceback.format_exc()
        for line in tb.splitlines()[-30:]:
            log("FATAL", line)


def station_id(mem: Dict[str, Any]) -> None:
    """
    Periodic on-air station identifier.
    Safe against missing config and racey memory writes.
    """

    last = int(mem.get("last_station_id", 0) or 0)

    if now_ts() - last < HOST_STATION_ID_SEC:
        return

    try:
        speak(f"You’re tuned to {SHOW_NAME}.", resolve_lead_voice(mem=mem))
    except Exception as e:
        log("audio", f"station_id speak error: {type(e).__name__}: {e}")

    mem["last_station_id"] = now_ts()
    save_memory_throttled(mem, min_interval_sec=1.0)

def db_distinct_queued_sources(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT COUNT(DISTINCT COALESCE(source,'feed')) FROM segments WHERE status='queued';")
    return int(cur.fetchone()[0] or 0)


# =======================
# Evergreen filler riff
# =======================

def evergreen_riff(mem: Dict[str, Any]) -> str:
    """
    Natural filler riff when the station is idle.
    """

    themes = mem.get("themes", [])[-12:]
    callbacks = mem.get("callbacks", [])[-8:]

    return get_prompt(
        mem, "evergreen_riff_user",
        duration=HOST_IDLE_RIFF_SEC_CFG,
        themes=themes,
        callbacks=callbacks
    ).strip()


def get_role_def(role_name: str) -> Dict[str, Any]:
    return CFG.get("roles", {}).get(role_name, {})
def compile_character_prompt(char_cfg: Dict[str, Any]) -> str:

    role_name = char_cfg.get("role", "")
    role_def = get_role_def(role_name)

    base = role_def.get("base", "")
    behavior = role_def.get("behavior", [])

    traits = char_cfg.get("traits", [])
    focus = char_cfg.get("focus", [])

    parts = []

    if base:
        parts.append(base)

    if behavior:
        parts.append("Core behaviors:")
        parts.extend(f"- {b}" for b in behavior)

    if traits:
        parts.append("Personality traits:")
        parts.append(", ".join(traits))

    if focus:
        parts.append("Primary focus areas:")
        parts.append(", ".join(focus))

    parts.append("Stay consistent and natural in this role.")

    return "\n".join(parts)

# =======================
# Host Loop
# =======================
def _narrative_line_for_music(mem: Dict[str, Any], phase: str) -> str:
    """
    phase: 'pre' or 'post'
    Generates 1 short spoken line. No hardcoded domain.
    """
    st = MUSIC_STATE or {}
    title = (st.get("title") or "").strip()
    artist = (st.get("artist") or "").strip()
    track = f"{artist} — {title}".strip(" —")

    if phase == "pre":
        prm = get_prompt(
            mem, "music_pre",
            track=track or "(unknown track)"
        ).strip()
    else:
        prm = get_prompt(
            mem, "music_post",
            track=track or "(unknown track)"
        ).strip()

    try:
        out = clean(llm_generate(
            prm,
            "You are a natural on-air voice. One sentence only.",
            model=CFG["models"]["host"],
            num_predict=80,
            temperature=0.75,
            timeout=20
        ))
        return (out or "").strip()
    except Exception:
        return ""


def host_loop(stop_event: threading.Event, mem: Dict[str, Any]) -> None:

    conn = db_connect()
    migrate_segments_table(conn)

    while not stop_event.is_set():

        # -------------------
        # Periodic station ID
        # -------------------
        station_id(mem)

        # -------------------
        # Play buffered audio
        # -------------------
        try:
            item = audio_queue.get_nowait()
            if not isinstance(item, AudioItem):
                bundle = item
                segmeta = {}
            else:
                bundle = item.bundle
                segmeta = item.seg or {}

            src = (segmeta.get("source") or "feed").strip().lower()
            etype = (segmeta.get("event_type") or "").strip().lower()
            title = (segmeta.get("title") or "")[:80]

            log("host", f"Playing bundle lines={len(bundle)} src={src} type={etype} title={title}")

            # NOW PLAYING ON
            try:
                ui_q.put(("now_playing_on", segmeta))
            except Exception:
                pass

            # ====================================================
            # 🎵 MUSIC BREAKS SPECIAL HANDLING
            # ====================================================
            if src == "music_breaks" and etype == "track_start":
                lead_voice = resolve_lead_voice(segmeta, mem)

                # If NOT background mode: do not talk over it (true "break")
                if not music_allow_bg():

                    # Optional: 1-line pre-tease (before the song)
                    pre = _narrative_line_for_music(mem, "pre")
                    if pre:
                        play_audio_bundle([(lead_voice, pre)])
                        time.sleep(0.15)

                    # Block until track ends (only if music is actually playing)
                    flows_enabled = bool(MUSIC_STATE.get("flows_enabled", False))
                    music_playing = bool(MUSIC_STATE.get("playing", False)) if flows_enabled else False
                    if music_playing:
                        wait_until_track_end(stop_event)
                    else:
                        log("host", "track_start received but music not playing — skip wait")

                    # Optional: 1-line post-bridge (after the song)
                    post = _narrative_line_for_music(mem, "post")
                    if post:
                        play_audio_bundle([(lead_voice, post)])
                        time.sleep(0.15)

                    # NOW PLAYING OFF
                    try:
                        ui_q.put(("now_playing_off", {"source": src}))
                    except Exception:
                        pass

                    time.sleep(HOST_BETWEEN_SEGMENTS_SEC_CFG)
                    continue

                # Background mode:
                # - duck external audio (best effort)
                # - host continues to talk normally (bundle already contains speech)
                else:
                    app_hint = (MUSIC_STATE.get("source_app") or "spotify").lower()
                    level = music_duck_level()
                    fade = music_fade_sec()

                    # quick fade-ish: ramp volume down in steps
                    ok = False
                    steps = max(3, int(fade / 0.15))
                    for i in range(steps):
                        x = 1.0 - (i + 1) / steps
                        ok = duck_external_audio(app_hint, max(level, x * 1.0), log_fn=log) or ok
                        time.sleep(0.03)

                    # Speak bundle normally
                    play_audio_bundle(bundle)

                    # restore to full after
                    for i in range(steps):
                        x = level + (i + 1) / steps * (1.0 - level)
                        duck_external_audio(app_hint, float(x), log_fn=None)
                        time.sleep(0.03)

                    # NOW PLAYING OFF
                    try:
                        ui_q.put(("now_playing_off", {"source": src}))
                    except Exception:
                        pass

                    time.sleep(HOST_BETWEEN_SEGMENTS_SEC_CFG)
                    continue

            # ====================================================
            # Normal segment playback
            # ====================================================

            play_audio_bundle(bundle)

            # NOW PLAYING OFF
            try:
                ui_q.put(("now_playing_off", {"source": src}))
            except Exception:
                pass

            time.sleep(HOST_BETWEEN_SEGMENTS_SEC_CFG)
            continue

        except queue.Empty:
            pass

        # -------------------
        # Check DB state
        # -------------------
        try:
            queued = db_depth_queued(conn)
            inflight = db_depth_inflight(conn)
        except Exception:
            queued = 0
            inflight = 0

        if queued > 0 or inflight > 0:
            log_every(
                mem,
                "host_wait",
                8,
                "host",
                f"Waiting for TTS… queued={queued} inflight={inflight} audio_q=0"
            )
            time.sleep(0.25)
            continue

        producer_kick.set()

        try:
            if db_depth_total(conn) == 0:
                # User Disabled: "hardcoded shitty riff system"
                # If we want filling, it should come from a plugin (like mix_rebalance or similar)
                # try:
                #     riff = clean(llm_generate(
                #         evergreen_riff(mem),
                #         "You are a radio host filling a short gap naturally.",
                #         model=CFG["models"]["host"],
                #         num_predict=120,
                #         temperature=0.85,
                #         timeout=40
                #     ))
                #     if riff:
                #         play_audio_bundle([("host", riff)])
                # except Exception as e:
                #     log("host", f"riff error: {type(e).__name__}: {e}")

                time.sleep(0.4)
                continue
        except Exception:
            pass

        time.sleep(0.25)


# =======================
# DB helpers (generic)
# =======================

def db_depth_queued(conn) -> int:
    cur = conn.execute("SELECT COUNT(*) FROM segments WHERE status='queued';")
    return int(cur.fetchone()[0])

def db_depth_inflight(conn) -> int:
    cur = conn.execute("SELECT COUNT(*) FROM segments WHERE status='claimed';")
    return int(cur.fetchone()[0])

def db_depth_total(conn) -> int:
    cur = conn.execute("SELECT COUNT(*) FROM segments WHERE status IN ('queued','claimed');")
    return int(cur.fetchone()[0])


# =======================
# Live Prompt System
# =======================

CALLIN_SAMPLE_RATE = 16000
CALLIN_CHANNELS = 1
CALLIN_MAX_SEC = 45

SHOW_INTERRUPT = threading.Event()



visual_q: "queue.Queue[Tuple[str, Any]]" = queue.Queue()

def compute_live_roles() -> List[str]:
    roles = ["host", "producer"]
    for name in (CFG.get("characters", {}) or {}).keys():
        n = (name or "").strip().lower()
        if n and n not in roles:
            roles.append(n)
    return roles

def mem_set_live_prompt(mem: Dict[str, Any], role: str, text: str) -> None:
    role = (role or "").strip().lower()
    roles = globals().get("LIVE_ROLES") or []
    if role not in roles:
        return


    mem.setdefault("live_prompts", {})
    mem["live_prompts"][role] = {
        "text": (text or "")[:900],
        "ts": now_ts(),
    }
    save_memory(mem)


def mem_live_prompt_block(mem: Dict[str, Any], *, max_age_sec: int = 6*3600) -> str:

    lp = mem.get("live_prompts") or {}
    if not isinstance(lp, dict):
        return ""

    now = now_ts()
    lines = []

    for role in LIVE_ROLES:
        item = lp.get(role)
        if not item:
            continue

        ts = int(item.get("ts", 0))
        if ts and (now - ts) > max_age_sec:
            continue

        txt = (item.get("text") or "").strip()
        if txt:
            lines.append(f"- {role}: {txt}")

    if not lines:
        return ""

    return "LIVE NUDGES (background only):\n" + "\n".join(lines)


def maybe_interrupt_for_callin():
    """
    Must be able to stop audio immediately.
    Never take audio_lock here (it can be held by speak()).
    """
    if SHOW_INTERRUPT.is_set():
        try:
            sd.stop()
        except Exception as e:
            log("ERR", f"{type(e).__name__}: {e}")


# =======================
# Voice Reaction Generator
# =======================

def generate_voice_reaction(
    voice: str,
    meta: Dict[str, str],
    seg: Dict[str, Any],
    mem: Dict[str, Any]
) -> str:

    live_block = mem_live_prompt_block(mem)

    prompt = get_prompt(
        mem, "voice_reaction_user",
        material=(seg.get("body","") or "")[:450],
        intent=meta.get("intent"),
        focus=meta.get("focus"),
        context=meta.get("context"),
        tone=meta.get("emotion"),
        live_block=live_block
    ).strip()

    # Pull character system prompt from manifest-compiled runtime layer
    system = CHARACTERS.get(voice, "You are a commentator.")

    try:
        return clean(llm_generate(
            prompt,
            system,
            model=CFG["models"]["host"],
            num_predict=55,
            temperature=0.92,
            timeout=40
        ))
    except Exception:
        return ""

# CALL-IN SEGMENT INJECTION
# =====================================================

def enqueue_callin_segment(transcript: str, mem: Dict[str, Any]) -> None:

    transcript = (transcript or "").strip()
    if not transcript:
        return

    is_fallback = "unintelligible" in transcript.lower()

    conn = db_connect()
    migrate_segments_table(conn)

    seg = {
        "id": sha1("callin|" + str(now_ts()) + "|" + str(random.random())),
        "post_id": sha1("callinpost|" + str(now_ts())),

        "subreddit": "callin",
        "source": "callin",
        "event_type": "caller",

        "title": "Live caller",
        "body": clamp_text(transcript, 1400),
        "comments": [],

        "angle": "Treat as a live interruption. If audio is unintelligible, comment on the bad connection." if is_fallback else "Treat as a live interruption and respond naturally.",
        "why": "The operator is shaping the show in real time.",
        "key_points": ["listen carefully", "respond directly"],
        "priority": 99.0,
        "host_hint": "caller_unintelligible" if is_fallback else "caller_interrupt"
    }

    db_enqueue_segment(conn, seg)
    conn.close()
def dj_worker(stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            dj_q.get(timeout=0.5)
        except queue.Empty:
            pass

def generate_host_takeaway(seg, mem, bundle):
    return ""




# =====================================================
# AUDIO TRANSCRIPTION (pluggable)
# =====================================================

def transcribe_audio_wav(wav_path: str) -> str:

    whisper_bin = os.environ.get("WHISPER_CPP_BIN", "").strip()

    if whisper_bin and os.path.exists(whisper_bin):

        try:
            model_path = os.environ.get("WHISPER_CPP_MODEL", "").strip()
            if not model_path:
                return ""

            out_txt = wav_path + ".txt"

            subprocess.run(
                [whisper_bin, "-m", model_path, "-f", wav_path, "-otxt"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120
            )

            if os.path.exists(out_txt):
                with open(out_txt, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read().strip()

        except Exception:
            pass
            
    # Fallback: simple offline/online SpeechRecognition if installed
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio = r.record(source)
        # 5s timeout, google default key
        return str(r.recognize_google(audio, timeout=5) or "")
    except Exception:
        pass

    return ""


# =====================================================
# VISUAL PROMPT ENGINE
# =====================================================

def build_visual_prompt(seg: Dict[str, Any], mem: Dict[str, Any]) -> str:

    title = (seg.get("title") or "")[:240]
    body = (seg.get("body") or "")[:700]
    angle = (seg.get("angle") or "")[:260]

    live_block = mem_live_prompt_block(mem)

    sys = get_prompt(mem, "visual_prompt_system").strip()

    prm = get_prompt(
        mem, "visual_prompt_user",
        title=title,
        angle=angle,
        body=body,
        live_block=live_block
    ).strip().strip()

    try:
        return clean(llm_generate(
            prm,
            sys,
            model=CFG["models"]["host"],
            num_predict=90,
            temperature=0.95,
            timeout=50
        ))
    except Exception:
        return ""


def visual_prompt_worker(stop_event: threading.Event, mem: Dict[str, Any]) -> None:

    last_hash = ""
    last_ts = 0

    while not stop_event.is_set():

        try:
            seg = mem.get("ui_last_seg")

            if isinstance(seg, dict):

                key = sha1(
                    (seg.get("id","") + "|" +
                     seg.get("title","") +
                     seg.get("body","")[:120]).strip()
                )

                now = now_ts()

                if key != last_hash and (now - last_ts) > 6:

                    last_hash = key
                    last_ts = now

                    vp = build_visual_prompt(seg, mem)

                    if vp:
                        visual_q.put(("visual_prompt", vp))

        except Exception as e:
            log("ERR", f"{type(e).__name__}: {e}")


        time.sleep(0.35)


# =====================================================
# UI EVENT SERIALIZER
# =====================================================
def ui_event_worker(stop_event: threading.Event, mem: Dict[str, Any]) -> None:

    rec_stream = None
    rec_frames = []
    rec_start_ts = 0
    rec_dev = None

    def _rec_callback(indata, frames, time_info, status):
        rec_frames.append(indata.copy())
        # Update UI while recording
        try:
           v = float(np.max(np.abs(indata)))
           ui_q.put_nowait(("widget_update", {
               "widget_key": "callin",
               "data": {"level": v}
           }))
        except Exception as e:
            # Avoid spamming log in high-freq callback, but maybe once?
            pass

    while not stop_event.is_set():

        # -------------------------
        # Drain visual prompt queue
        # -------------------------
        try:
            while True:
                ve, vp = visual_q.get_nowait()
                if ve == "visual_prompt":
                    ui_q.put(("visual_prompt", vp))
        except queue.Empty:
            pass

        # -------------------------
        # Pull UI command
        # -------------------------
        try:
            evt, payload = ui_cmd_q.get(timeout=0.25)
        except queue.Empty:
            continue

        try:

            # =====================================================
            # FLUSH PRODUCER QUEUE
            # =====================================================
            if evt == "music_cmd":
                try:
                    music_cmd_q.put((evt, payload))
                except Exception:
                    pass

            elif evt == "flush_queue":
                try:
                    conn = db_connect()
                    migrate_segments_table(conn)

                    # wipe playback queue
                    conn.execute("DELETE FROM segments;")
                    conn.execute("DELETE FROM seen_items;")   # <-- ADD THIS

                    # wipe "already seen" filter so producer can re-emit reddit/portfolio/document immediately
                    conn.execute("DELETE FROM seen_items;")

                    # reset scheduler pointer so fair rotation restarts clean
                    conn.execute("DELETE FROM scheduler_state WHERE k='rr_ptr';")

                    conn.commit()
                    conn.close()

                    # Clear in-memory candidates too (otherwise it will instantly reuse the same old backlog)
                    try:
                        with _feed_lock:
                            mem["feed_candidates"] = []
                    except Exception:
                        pass

                    save_memory_throttled(mem, min_interval_sec=0.5)

                    # Wake pipelines
                    producer_kick.set()

                    log("ui", "Producer queue flushed (segments + seen_items + rr_ptr + candidates)")

                except Exception as e:
                    log("ERR", f"flush_queue error: {type(e).__name__}: {e}")

            elif evt == "tune_station":
                try:
                    target_id = str(payload).strip()
                    log("sys", f"Tuning request -> {target_id}")

                    # Resolve paths
                    root = RADIO_OS_ROOT or os.getcwd()
                    
                    # Request Shell to switch via file + exit code
                    req_path = os.path.join(root, ".switch_request")
                    try:
                        with open(req_path, "w", encoding="utf-8") as f:
                            json.dump({"station_id": target_id}, f)
                        log("sys", f"wrote switch request to {req_path}")
                    except Exception as e:
                        log("ERR", f"Failed to write switch request: {e}")
                    
                    log("sys", "Exiting (code 20) to trigger station switch...")
                    sys.stdout.flush()
                    sys.stderr.flush()
                    # Exit with magic code 20 — use os._exit to kill all threads immediately
                    os._exit(20)
                    
                except Exception as e:
                    log("ERR", f"tune_station failed: {e}")


            # =====================================================
            # APPLY LIVE PROMPTS
            # =====================================================
            elif evt == "apply_live_prompts":

                if isinstance(payload, dict):
                    for role, txt in payload.items():
                        mem_set_live_prompt(mem, role, txt)

                save_memory(mem)


            elif evt == "save_ui_layout":
                try:
                    # UI writes layout itself (via ui_q request) OR we store in mem and file here.
                    # Keep it simple: ask UI thread to snapshot layout and return it via ui_q not needed.
                    # Instead: store a request, UI will write file directly in main thread for safety.
                    ui_q.put(("ui_snapshot_layout", None))
                except Exception:
                    pass

            elif evt == "load_ui_layout":
                try:
                    ui_q.put(("ui_load_layout", None))
                except Exception:
                    pass

            elif evt == "reset_ui_layout":
                try:
                    ui_q.put(("ui_reset_layout", None))
                except Exception:
                    pass

            elif evt == "update_config":
                # Generic config update from UI
                # payload: {"config": {...}} (merged)
                try:
                    updates = payload.get("config", {})
                    if updates:
                        mem.setdefault("config", {}).update(updates)
                        save_memory_throttled(mem, min_interval_sec=1.0)
                        log("ui", f"Config updated: {list(updates.keys())}")
                        
                        # --- PERSIST TO MANIFEST ---
                        try:
                            mp = os.path.join(STATION_DIR, "manifest.yaml")
                            if os.path.exists(mp):
                                # Read-modify-write to preserve other keys
                                with open(mp, "r", encoding="utf-8") as f:
                                    cur_yaml = yaml.safe_load(f) or {}
                                
                                dirty = False
                                for k, v in updates.items():
                                    if cur_yaml.get(k) != v:
                                        cur_yaml[k] = v
                                        dirty = True
                                        
                                if dirty:
                                    with open(mp, "w", encoding="utf-8") as f:
                                        yaml.safe_dump(cur_yaml, f, default_flow_style=False, sort_keys=False)
                                    log("sys", "Persisted settings to manifest.yaml")
                        except Exception as ye:
                            log("ERR", f"Manifest persist failed: {ye}")
                        # ---------------------------
                except Exception as e:
                    log("ERR", f"Config update failed: {e}")

            elif evt == "callin_on":

                SHOW_INTERRUPT.set()
                maybe_interrupt_for_callin()

                rec_frames = []
                rec_start_ts = now_ts()

                # Allow selecting device from payload
                if isinstance(payload, dict):
                    rec_dev = payload.get("device")

                # Try multiple sample rates if strict hardware (e.g. 16k might fail)
                rates_to_try = [CALLIN_SAMPLE_RATE, 44100, 48000, None]
                
                for sr in rates_to_try:
                    try:
                        log("audio", f"Starting callin stream dev={rec_dev} sr={sr}")
                        rec_stream = sd.InputStream(
                            samplerate=sr,
                            channels=CALLIN_CHANNELS,
                            dtype="float32",
                            callback=_rec_callback,
                            device=rec_dev
                        )
                        rec_stream.start()
                        log("audio", f"Callin stream started OK at {sr if sr else 'auto'}Hz")
                        break
                    except Exception as e:
                        log("ERR", f"Callin stream failed at {sr}: {e}")
                        rec_stream = None
                
                if not rec_stream:
                    log("ERR", "Callin stream could not be started on any common sample rate.")



            # =====================================================
            # CALL-IN STOP + TRANSCRIBE
            # =====================================================
            elif evt == "callin_off":

                dj_q.put(("callin_off", None))

                try:
                    if rec_stream:
                        rec_stream.stop()
                        rec_stream.close()
                except Exception as e:
                    log("ERR", f"{type(e).__name__}: {e}")

                rec_stream = None
                SHOW_INTERRUPT.clear()

                if not rec_frames:
                    continue

                # Check if we should skip transcription (e.g. text-only call or custom)
                skip_tx = False
                if isinstance(payload, dict) and payload.get("skip_transcribe"):
                    skip_tx = True
                
                if skip_tx:
                    continue

                try:
                    audio = np.concatenate(rec_frames, axis=0)

                    if audio.ndim > 1 and audio.shape[1] > 1:
                        audio = audio.mean(axis=1, keepdims=True)

                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        wav_path = f.name

                    sf.write(wav_path, audio, CALLIN_SAMPLE_RATE)

                    tx = transcribe_audio_wav(wav_path)

                    try:
                        os.remove(wav_path)
                    except Exception as e:
                        log("ERR", f"{type(e).__name__}: {e}")

                    if tx:
                        enqueue_callin_segment(tx, mem)
                        producer_kick.set()
                    elif rec_frames:
                        # Fallback: if we have audio coverage but no transcript (e.g. no whisper),
                        # send a generic "unintelligible" or "garbled" event so the host reacts.
                        log("audio", "Call-in fallback: audio recorded but no transcript. Sending generic event.")
                        enqueue_callin_segment("[Caller audio signal received - static/unintelligible]", mem)
                        producer_kick.set()

                except Exception as e:
                    log("ERR", f"{type(e).__name__}: {e}")



            # =====================================================
            # LAST SEGMENT FOR UI/VISUALS
            # =====================================================
            elif evt == "ui_last_seg":

                mem["ui_last_seg"] = payload
            # =====================================================
            # RADIO DIAL — VOLUME / SPEED / STATION
            # =====================================================

            elif evt == "set_volume":
                try:
                    v = float(payload)
                    v = max(0.0, min(1.5, v))
                    # Update mem for host_loop and CFG for speak()
                    mem["audio_volume"] = v
                    CFG.setdefault("audio", {})["volume"] = v
                    
                    ui_q.put(("widget_update", {
                        "widget_key": "radio_dial",
                        "data": {"volume": v}
                    }))
                except Exception:
                    pass

            elif evt == "set_speed":
                try:
                    s = float(payload)
                    s = max(0.6, min(1.6, s))
                    # Update mem for host_loop and CFG for speak()
                    mem["audio_speed"] = s
                    CFG.setdefault("audio", {})["speed"] = s
                    
                    ui_q.put(("widget_update", {
                        "widget_key": "radio_dial",
                        "data": {"speed": s}
                    }))
                except Exception:
                    pass

            elif evt == "switch_station":
                sid = str(payload or "").strip()
                if sid:
                    mem["station_switch_requested"] = {
                        "station_id": sid,
                        "ts": now_ts()
                    }
                    ui_q.put(("widget_update", {
                        "widget_key": "radio_dial",
                        "data": {"station": sid}
                    }))
                    ui_q.put(("station_switch_requested", sid))
            # =====================================================
            # TIMELINE REPLAY
            # =====================================================

            elif evt == "timeline_replay":

                seg_id = None
                if isinstance(payload, dict):
                    seg_id = payload.get("seg_id")

                if not seg_id:
                    continue

                try:
                    conn = db_connect()
                    migrate_segments_table(conn)

                    row = db_get_segment_by_id(conn, seg_id)
                    conn.close()

                    if isinstance(row, dict):
                        # Re-enqueue directly into playback queue
                        conn2 = db_connect()
                        migrate_segments_table(conn2)

                        cols = ",".join(row.keys())
                        qs = ",".join(["?"] * len(row))
                        conn2.execute(
                            f"INSERT INTO segments ({cols}) VALUES ({qs})",
                            tuple(row.values())
                        )
                        conn2.commit()
                        conn2.close()

                        producer_kick.set()

                except Exception as e:
                    log("ERR", f"timeline replay error: {type(e).__name__}: {e}")
            # =====================================================
            # NOTES
            # =====================================================

            elif evt == "notes_add":

                if not isinstance(payload, dict):
                    continue

                note = {
                    "id": sha1(f"note|{now_ts()}|{random.random()}"),
                    "ts": now_ts(),
                    "title": (payload.get("title") or "").strip()[:240],
                    "body": (payload.get("body") or "").strip()[:8000],
                    "tags": payload.get("tags") or [],
                    "source": payload.get("source") or "",
                    "seg_id": payload.get("seg_id") or "",
                }

                mem.setdefault("notes", [])
                mem["notes"].insert(0, note)

                save_memory_throttled(mem)

                ui_q.put(("widget_update", {
                    "widget_key": "notes",
                    "data": {"notes": mem["notes"]}
                }))

            elif evt == "notes_delete":

                nid = str(payload or "").strip()
                if not nid:
                    continue

                mem["notes"] = [
                    n for n in mem.get("notes", [])
                    if str(n.get("id")) != nid
                ]

                save_memory_throttled(mem)

                ui_q.put(("widget_update", {
                    "widget_key": "notes",
                    "data": {"notes": mem["notes"]}
                }))
            # =====================================================
            # CONTEXT MEMORY
            # =====================================================

            elif evt == "context_pin":

                if not isinstance(payload, dict):
                    continue

                pin = {
                    "id": sha1(f"pin|{now_ts()}|{random.random()}"),
                    "ts": now_ts(),
                    "title": (payload.get("title") or "").strip()[:240],
                    "body": (payload.get("body") or "").strip()[:4000],
                    "kind": (payload.get("kind") or "segment"),
                }

                mem.setdefault("context_pins", [])
                mem["context_pins"].insert(0, pin)

                save_memory_throttled(mem)

                ui_q.put(("widget_update", {
                    "widget_key": "context_memory",
                    "data": {"pins": mem["context_pins"]}
                }))

            elif evt == "context_unpin":

                pid = str(payload or "").strip()
                if not pid:
                    continue

                mem["context_pins"] = [
                    p for p in mem.get("context_pins", [])
                    if str(p.get("id")) != pid
                ]

                save_memory_throttled(mem)

                ui_q.put(("widget_update", {
                    "widget_key": "context_memory",
                    "data": {"pins": mem["context_pins"]}
                }))



        except Exception as e:
            log("ERR", f"{type(e).__name__}: {e}")

def db_get_segment_by_id(conn, seg_id: str) -> Optional[Dict[str, Any]]:
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM segments WHERE id = ?", (seg_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        return {cols[i]: row[i] for i in range(len(cols))}
    except Exception:
        return None

def status_worker(stop_event, station_dir, mem):
    """
    Writes station_dir/status.json every 0.5s.
    Must NEVER crash. Uses its own DB connection.
    """

    # own DB connection: thread-safe and avoids undefined 'conn'
    conn = None
    try:
        conn = db_connect()
        migrate_segments_table(conn)
    except Exception:
        conn = None

    last_ok_ts = 0

    while not stop_event.is_set():
        try:
            db_queued = -1
            db_claimed = -1
            audio_depth = -1

            # DB counts (if DB is available)
            if conn is not None:
                try:
                    db_queued = db_depth_queued(conn)
                except Exception:
                    db_queued = -1
                try:
                    db_claimed = db_depth_claimed(conn)  # uses alias above
                except Exception:
                    db_claimed = -1

            # Audio depth (global queue)
            try:
                audio_depth = audio_queue.qsize()
            except Exception:
                audio_depth = -1

            # Optional: include some “alive” signals for shell diagnostics
            data = {
                "station": SHOW_NAME,
                "host": HOST_NAME,
                "db_queued": db_queued,
                "db_claimed": db_claimed,
                "audio_q": audio_depth,
                "threads": {
                    "producer_kick_set": bool(producer_kick.is_set()),
                },
                "last_event": mem.get("last_event"),
                "last_title": mem.get("last_title"),
                "last_source": mem.get("last_source"),
            }

            write_status(station_dir, data)
            last_ok_ts = now_ts()

        except Exception as e:
            # absolutely never die; just keep looping
            try:
                if mem.get("debug_plugins") or mem.get("debug_status"):
                    log("status", f"status_worker error: {type(e).__name__}: {e}")
            except Exception as e:
                log("ERR", f"{type(e).__name__}: {e}")


        time.sleep(0.5)

    try:
        if conn is not None:
            conn.close()
    except Exception as e:
        log("ERR", f"{type(e).__name__}: {e}")

_feed_lock = threading.Lock()
_feed_lock = threading.Lock()

def _normalize_source_alias(src: str) -> str:
    s = (src or "").strip().lower()
    if not s:
        return "feed"

    # unify common drift across plugins / configs
    alias = {
        "market": "markets",
        "mkt": "markets",
        "portfolio": "portfolio_event",
        "portfolioevents": "portfolio_event",
        "port_event": "portfolio_event",
        "docs": "document",
        "documents": "document",
        "bsky": "bluesky",
    }
    return alias.get(s, s)

def normalize_feed_item(cand: Dict[str, Any]) -> Dict[str, Any]:
    """
    Central normalization for all incoming feed items.
    Ensures consistent shape, cleaning, and defaults before storage.
    """
    if not isinstance(cand, dict):
        return {}

    # Copy to avoid side effects
    item = cand.copy()

    # 1. Source Normalization
    src = item.get("source", "feed")
    item["source"] = _normalize_source_alias(src)

    # 2. Basic Text Fields (ensure strings)
    for k in ["title", "body", "author", "url"]:
        if k in item and item[k] is None:
            item[k] = ""
        elif k in item:
            item[k] = str(item[k]).strip()
        else:
            item[k] = ""

    # 3. Timestamps
    if "ts" not in item:
        item["ts"] = now_ts()
    
    # 4. Type & Defaults
    item.setdefault("type", "item")
    if "event_type" not in item:
        item["event_type"] = item["type"]
    
    item.setdefault("comments", [])
    item.setdefault("tags", [])
    item.setdefault("metrics", {})
    # symbol intentionally optional

    # 5. Priority / Weight
    # Promote "priority" -> "heur" (0-100)
    p = item.get("priority")
    if "heur" not in item or item["heur"] is None:
        try:
            item["heur"] = float(p if p is not None else 50.0)
        except (ValueError, TypeError):
            item["heur"] = 50.0

    # 6. ID Stability
    # If no post_id, generate one from content
    if not item.get("post_id"):
        base = (item.get("title","") + "|" + (item.get("body","") or "")[:200]).strip()
        item["post_id"] = sha1(base)

    return item

def _emit_candidate(mem: Dict[str, Any], cand: Dict[str, Any]) -> None:
    if not isinstance(cand, dict):
        return

    # Use the central normalizer
    final_cand = normalize_feed_item(cand)

    with _feed_lock:
        mem.setdefault("feed_candidates", [])
        mem["feed_candidates"].append(final_cand)

        # bounded memory
        mem["feed_candidates"] = mem["feed_candidates"][-800:]

    try:
        producer_kick.set()
    except Exception:
        pass

    save_memory_throttled(mem, min_interval_sec=1.0)

def feed_debug_heartbeat(stop_event: threading.Event, mem: Dict[str, Any]) -> None:
    while not stop_event.is_set():
        try:
            n = len(mem.get("feed_candidates", []) or [])
            last = (mem.get("feed_candidates", []) or [])[-1] if n else None
            log("feed", f"heartbeat candidates={n} last_source={last.get('source') if last else None}")
        except Exception as e:
            log("feed", f"heartbeat error: {type(e).__name__}: {e}")
        time.sleep(8)

# =====================================================
# MAIN RUNTIME BOOTSTRAP
# =====================================================
def main():

    global CFG, CHARACTERS, LIVE_ROLES

    # ------------------
    # Load manifest
    # ------------------

    CFG = load_station_manifest()

    # ------------------
    # Load plugins ONCE
    # ------------------

    feed_registry = load_feed_plugins(CFG)

    feeds_cfg = CFG.get("feeds", {})
    if not isinstance(feeds_cfg, dict):
        feeds_cfg = {}

    log("feed", f"manifest feeds: {list(feeds_cfg.keys())}")
    log("feed", f"registered plugins: {list(feed_registry.keys())}")
    log("ui", f"registered widgets: {list(WIDGETS.keys())}")  # <--- CORRECTED

    # ------------------
    # Audio diagnostics
    # ------------------

    audio_cfg = CFG.get("audio", {}) if isinstance(CFG.get("audio"), dict) else {}
    voices_a = CFG.get("voices", {}) if isinstance(CFG.get("voices"), dict) else {}
    voices_b = audio_cfg.get("voices", {}) if isinstance(audio_cfg.get("voices"), dict) else {}

    voice_keys = sorted(set(list(voices_a.keys()) + list(voices_b.keys())))

    log("config", f"Using piper_bin={audio_cfg.get('piper_bin')}")
    log("audio", f"Voice keys available: {voice_keys}")

    try:
        log("audio", f"sounddevice default device: {sd.default.device}")
    except Exception as e:
        log("audio", f"sounddevice error: {e}")

    # ------------------
    # UI
    # ------------------

    ui = StationUI(WIDGETS)
    ui.root.update_idletasks()
    ui.root.update()

    # ------------------
    # Memory
    # ------------------

    mem = load_memory()
    ui.mem = mem # 📝 Attach for UI editors
    
    # ✅ Set global STATION_MEMORY for plugins/runtime access
    global STATION_MEMORY
    STATION_MEMORY = mem

    mem.setdefault("feed_candidates", [])
    mem.setdefault("recent_riff_tags", [])
    mem.setdefault("tag_heat", {})
    mem.setdefault("tag_last_spoken", {})
    mem.setdefault("riff_style_lru", [])
    mem.setdefault("live_prompts", {})
    mem.setdefault("_log_last", {})
    # ✅ Clear any stale music pause state from previous run
    mem.pop("_music_paused_for_talk", None)
    mem.pop("_music_resume_at", None)
    mem.pop("_music_resume_cmd", None)
    mem.pop("_music_boundary_active", None)
        # ------------------
    # Characters
    # ------------------

    CHARACTERS = init_characters()
    LIVE_ROLES = compute_live_roles()

    # ------------------
    # Stop event
    # ------------------

    stop_event = threading.Event()

    def on_close():
        stop_event.set()
        try:
            ui.root.quit()
            ui.root.destroy()
        except Exception:
            pass

    ui.root.protocol("WM_DELETE_WINDOW", on_close)

    # ------------------
    # DB seed
    # ------------------

    conn = db_connect()
    migrate_segments_table(conn)
    db_reset_claimed(conn)
    enqueue_cold_open(conn, mem)
    conn.close()

    threads: List[threading.Thread] = []

    # ------------------
    # Core workers
    # ------------------

    threads.extend([
        
        threading.Thread(target=status_worker, args=(stop_event, STATION_DIR, mem), daemon=True),
        threading.Thread(target=dj_worker, args=(stop_event,), daemon=True),
        threading.Thread(target=event_router_worker, args=(stop_event, mem), daemon=True),
        threading.Thread(target=producer_loop, args=(stop_event, mem), daemon=True),
        threading.Thread(target=run_thread, args=("tts_worker", tts_worker, stop_event, mem), daemon=True),
        threading.Thread(target=host_loop, args=(stop_event, mem), daemon=True),
        threading.Thread(target=ui_event_worker, args=(stop_event, mem), daemon=True),
        threading.Thread(target=visual_prompt_worker, args=(stop_event, mem), daemon=True),
        threading.Thread(target=feed_debug_heartbeat, args=(stop_event, mem), daemon=True),
        threading.Thread(target=rebalancer_worker, args=(stop_event, mem), daemon=True),


    ])

    # =====================================================
    # Feed plugins (clean + safe)
    # =====================================================
    def safe_feed_runner(feed_name, worker, stop_event, mem, payload):
        runtime = {
            "StationEvent": StationEvent,
            "event_q": event_q,
            "ui_q": ui_q,
            "ui_cmd_q": ui_cmd_q,       # pass raw ui_cmd_q just in case
            "music_cmd_q": music_cmd_q, # dedicated music command channel
            "MUSIC_STATE": MUSIC_STATE,
            "SHOW_INTERRUPT": SHOW_INTERRUPT,  # for graceful voice interruption
            "audio_queue_size": lambda: audio_queue.qsize(),

            "log": log,
            "now_ts": now_ts,
            "sha1": sha1,
            "producer_kick": producer_kick,

            # helper: emit StationEvent safely (normalize source for scheduler cohesion)
            "emit_event": lambda evt: event_q.put(
                StationEvent(
                    source=normalize_source(getattr(evt, "source", feed_name)),
                    type=getattr(evt, "type", "item"),
                    ts=getattr(evt, "ts", now_ts()),
                    severity=float(getattr(evt, "severity", 0.0) or 0.0),
                    priority=float(getattr(evt, "priority", 50.0) or 50.0),
                    payload=dict(getattr(evt, "payload", {}) or {}),
                )
            ) if isinstance(evt, StationEvent) else event_q.put(evt),

            # helper: emit candidate safely (forces normalized source + stable ids)
            "emit_candidate": lambda cand, _p=payload: _emit_candidate(mem, {
                **(cand or {}),
                "priority": (cand or {}).get("priority", _p.get("priority", 60)),
                "source": (cand or {}).get("source", feed_name),
            }),             "ui_widget_update": lambda widget_key, data: ui_q.put((
                "widget_update",
                {"widget_key": (widget_key or "").strip().lower(), "data": data}
            )),

        }

        try:
            # Prefer the new 4-arg calling convention:
            #   worker(stop_event, mem, payload, runtime)
            try:
                worker(stop_event, mem, payload, runtime)
                return
            except TypeError:
                pass

            # Back-compat 3-arg:
            #   worker(stop_event, mem, payload)
            try:
                worker(stop_event, mem, payload)
                return
            except TypeError:
                pass

            # Rare alt:
            #   worker(stop_event, mem, runtime)
            worker(stop_event, mem, runtime)

        except Exception as e:
            mem.setdefault("feed_errors", {})
            mem["feed_errors"][feed_name] = f"{type(e).__name__}: {e}"
            save_memory_throttled(mem, min_interval_sec=1.0)
            log("feed", f"{feed_name} crashed: {type(e).__name__}: {e}")


    active_feed_configs = {}

    for feed_name, feed_cfg in feeds_cfg.items():

        if not isinstance(feed_cfg, dict):
            log("feed", f"Skipping {feed_name}: bad config")
            continue

        if not feed_cfg.get("enabled", False):
            log("feed", f"Skipping {feed_name}: disabled")
            continue

        # Allow manifest to choose plugin module explicitly.
        # If omitted, default to feed_name (back-compat).
        plugin_key = (feed_cfg.get("plugin") or feed_name or "").strip().lower()

        worker = feed_registry.get(plugin_key)

        if not worker:
            log("feed", f"Feed '{feed_name}' enabled but plugin '{plugin_key}' not registered")
            continue

        payload = dict(feed_cfg)
        payload.pop("enabled", None)

        # helpful: keep identity fields around (safe, non-breaking)
        payload.setdefault("feed_name", feed_name)
        payload.setdefault("plugin", plugin_key)

        # Track for live config reloading
        active_feed_configs[feed_name] = payload

        threads.append(threading.Thread(
            target=safe_feed_runner,
            args=(feed_name, worker, stop_event, mem, payload),
            daemon=True
        ))

        log("feed", f"Started feed: {feed_name} (plugin={plugin_key})")

    # Start config reloader
    _start_feed_config_reloader(active_feed_configs)

    # ------------------
    # Start threads
    # ------------------

    for t in threads:
        t.start()

    try:
        ui.root.mainloop()
    finally:
        stop_event.set()
        time.sleep(0.3)

if __name__ == "__main__":
    main()
