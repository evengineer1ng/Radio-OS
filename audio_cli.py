#!/usr/bin/env python3
"""
RadioOS Audio CLI — Shell-level voice-command interface.

This is NOT a plugin. It runs at the shell level alongside shell_bookmark.py,
with direct access to UI state, station processes, and audio routing.

Architecture:
  - Mic listener thread (always-on for wake phrase, active capture during session)
  - STT engine (whisper.cpp / SpeechRecognition fallback)
  - LLM command parser (system prompt forces JSON output)
  - TTS narration output (voice_provider)
  - UI introspector (reads tkinter widget tree for visible state)
  - Command dispatcher (maps structured actions → shell operations)
  - Audio ducking (lowers station audio while Audio CLI speaks)
"""
from __future__ import annotations

import io
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Optional imports (degrade gracefully)
# ---------------------------------------------------------------------------
try:
    import sounddevice as sd
    HAS_SD = True
except ImportError:
    HAS_SD = False

try:
    import soundfile as sf
    HAS_SF = True
except ImportError:
    HAS_SF = False

# ---------------------------------------------------------------------------
# USB mic auto-discovery (for Pi / headless setups)
# ---------------------------------------------------------------------------
def _find_usb_mic_device() -> Optional[int]:
    """Return the sounddevice index of the first USB microphone found.

    Scans PortAudio device names for keywords that identify USB audio input
    devices (USB, Condenser, Microphone).  Returns None if sounddevice is
    unavailable or no matching device is found.

    Card numbers can shift across reboots when other USB devices are present,
    so name-based discovery is more reliable than hardcoding an index.
    """
    if not HAS_SD:
        return None
    try:
        keywords = ("usb", "condenser", "microphone", "webcam")
        for i, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) < 1:
                continue
            name_lc = dev.get("name", "").lower()
            if any(kw in name_lc for kw in keywords):
                _log(f"USB mic auto-discovered: index={i} name='{dev['name']}'")
                return i
    except Exception as e:
        _log(f"USB mic discovery error: {e}")
    return None

# ---------------------------------------------------------------------------
# Global config loader (reads from ~/.radioOS/config.json)
# ---------------------------------------------------------------------------
def _load_audio_cli_config() -> dict:
    """Load the audio_cli section from global Radio OS config."""
    import platform
    if platform.system() == "Windows":
        cfg_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "RadioOS")
    else:
        cfg_dir = os.path.expanduser("~/.radioOS")
    cfg_path = os.path.join(cfg_dir, "config.json")
    if not os.path.exists(cfg_path):
        return {}
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f).get("audio_cli", {})
    except Exception:
        return {}

# ---------------------------------------------------------------------------
# System environment loader — ensures /etc/environment vars are visible even
# when the process was started by a systemd service that doesn't inherit them.
# ---------------------------------------------------------------------------
def _load_system_env() -> None:
    """Parse /etc/environment and inject any missing vars into os.environ.
    Handles values that wrap across multiple lines (no backslash continuation).
    """
    try:
        with open("/etc/environment", "r", encoding="utf-8") as f:
            raw = f.read()
        # Join any lines that don't contain '=' (continuation of previous value)
        joined_lines: list = []
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                joined_lines.append(stripped)
            elif "=" in stripped:
                joined_lines.append(stripped)
            elif joined_lines:
                # Line with no '=' is a continuation — append to previous
                joined_lines[-1] = joined_lines[-1] + stripped
        for line in joined_lines:
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        pass

_ACLI_CFG = _load_audio_cli_config()
_load_system_env()  # Ensure /etc/environment vars (e.g. OPENAI_API_KEY) are visible early

# ---------------------------------------------------------------------------
# Constants (overridable via Settings → Audio CLI)
# ---------------------------------------------------------------------------
WAKE_PHRASE = _ACLI_CFG.get("wake_phrase", "hey radio")
EXIT_PHRASE = _ACLI_CFG.get("exit_phrase", "thanks radio")
SAMPLE_RATE = 16000               # 16 kHz mono for STT
CHANNELS = 1
WAKE_LISTEN_CHUNK_SEC = 2.0       # Seconds per wake-detection chunk
COMMAND_LISTEN_MAX_SEC = 10.0     # Max seconds to capture a single command
SILENCE_THRESHOLD = 0.018         # RMS below this = silence (lowered for better sensitivity)
SILENCE_DURATION_SEC = float(_ACLI_CFG.get("silence_duration_sec", 2.2))  # Seconds of silence to end capture
MIN_UTTERANCE_SEC = float(_ACLI_CFG.get("min_utterance_sec", 0.6))        # Minimum speech length before silence can end capture
MIC_RING_BUFFER_SEC = 15.0        # Ring buffer length (must exceed COMMAND_LISTEN_MAX_SEC + margin)
LOG_PREFIX = "[AudioCLI]"

# ---------------------------------------------------------------------------
# Verbosity levels (affects AudioCLI response formatting only)
# ---------------------------------------------------------------------------
VERBOSITY_LEVELS = ("minimal", "concise", "standard", "broadcast", "diagnostic")
DEFAULT_VERBOSITY = _ACLI_CFG.get("verbosity", "concise")
if DEFAULT_VERBOSITY not in VERBOSITY_LEVELS:
    DEFAULT_VERBOSITY = "concise"


def format_response(narration: str, state_snapshot: Dict[str, Any],
                    verbosity: str, *, intent: str = "",
                    confidence: float = 0.0) -> str:
    """
    Central response formatter.  Reshapes *narration* (already produced by
    the LLM or a narration builder) according to *verbosity*.

    This function ONLY affects output formatting — it never mutates backend
    state.  Call it **after** all actions have been executed.

    Args:
        narration:      Raw narration text from the LLM / builder.
        state_snapshot:  Current UI/game state dict (read-only).
        verbosity:      One of VERBOSITY_LEVELS.
        intent:         Interpreted intent string (for diagnostic mode).
        confidence:     Confidence score 0-1 (for diagnostic mode).

    Returns:
        Formatted narration string.
    """
    if not narration:
        return narration

    if verbosity == "minimal":
        # Shortest possible confirmation.  Take the first sentence and
        # truncate aggressively.
        first = narration.split(". ")[0].split(".\n")[0]
        # Remove filler openers
        for prefix in ("Audio CLI active.", "Currently,", "You are currently"):
            if first.startswith(prefix):
                first = first[len(prefix):].strip(" ,.")
        # Cap length
        first = first.strip()
        if len(first) > 80:
            first = first[:77].rsplit(" ", 1)[0] + "…"
        return first if first else narration.split(".")[0]

    if verbosity == "concise":
        # One or two short sentences.  Take up to the second period.
        sentences = [s.strip() for s in narration.replace("\n", " ").split(". ") if s.strip()]
        out = ". ".join(sentences[:2])
        if not out.endswith("."):
            out += "."
        return out

    if verbosity == "standard":
        # Up to ~3 sentences.  Light analysis OK.
        sentences = [s.strip() for s in narration.replace("\n", " ").split(". ") if s.strip()]
        out = ". ".join(sentences[:4])
        if not out.endswith("."):
            out += "."
        return out

    if verbosity == "broadcast":
        # Full narration — pass through as-is (the LLM may embellish).
        # Soft cap to prevent runaway token usage.
        if len(narration) > 600:
            narration = narration[:597].rsplit(" ", 1)[0] + "…"
        return narration

    if verbosity == "diagnostic":
        # Structured summary — no narrative tone.
        station = state_snapshot.get("station", {})
        gs = state_snapshot.get("game_state", {})
        lines = [
            f"Station: {station.get('name', state_snapshot.get('view', 'N/A'))}",
            f"Route: {state_snapshot.get('view', 'unknown')}",
        ]
        save_id = gs.get("save_id", gs.get("id", ""))
        if save_id:
            lines.append(f"Save ID: {save_id}")
        tick = gs.get("tick") or gs.get("date", "")
        if tick:
            lines.append(f"Tick: {tick}")
        if intent:
            lines.append(f"Intent: {intent}")
        if confidence:
            lines.append(f"Confidence: {confidence:.2f}")
        lines.append(f"Verbosity: diagnostic")
        lines.append(f"Raw narration: {narration[:200]}")
        return "\n".join(lines)

    # Fallback — concise
    return narration


# ===========================================================================
# Audio Persona System (Meta Plugin Contract for Audio CLI)
# ===========================================================================
#
# Mirrors bookmark.py's MetaPluginBase / MetaPluginRegistry pattern but for
# the audio voice-navigation layer.
#
# When a station with a meta plugin starts (e.g. "start Oracle Kingdom"),
# the Audio CLI can load the corresponding AudioPersona so the voice-nav
# experience becomes part of the game/station's world.
#
# ESCAPE HATCHES — these are ALWAYS owned by audio_cli, never overridable:
#   • Wake phrase detection ("hey radio") — always activates session
#   • Exit phrase handling ("thanks radio") — always ends session
#   • "exit persona" / "reset voice" / "normal mode" — drops persona
#   • Mic mute/unmute, audio mode switching (speaker/headphone)
#   • Verbosity control
#   • Session start/stop lifecycle
#   • Mode switching (tkinter ↔ web)
#
# Everything else — system prompt personality, narration voice, greeting,
# state description style, response reshaping — is delegable to the persona.
# ===========================================================================

from abc import ABC, abstractmethod as _persona_abstractmethod


class AudioPersonaBase(ABC):
    """
    Audio Persona Contract (v1.0)

    A persona reshapes HOW Audio CLI sounds and narrates — it never changes
    WHAT Audio CLI can do.  The session lifecycle, escape hatches, wake/exit
    phrases, and hardware controls remain immutably owned by audio_cli.py.

    Persona responsibilities:
      I.   System prompt overlay  — inject personality into LLM instructions
      II.  Greeting / farewell    — themed session open/close narration
      III. Narration reshaping     — post-process LLM output for flavor
      IV.  Voice selection         — TTS voice/model override
      V.   State description style — how UI/game state is narrated
      VI.  Ambient vocabulary      — custom phrase hints for STT accuracy

    Design invariants:
      • Persona NEVER blocks escape hatches.
      • Persona NEVER mutates session state (active, context, mode).
      • Persona NEVER intercepts wake/exit phrase detection.
      • Persona is stateless from audio_cli's perspective (persona owns
        its own internal state but audio_cli can drop it at any time).
      • Persona is optional — audio_cli works identically without one.
    """

    # =====================================================================
    # LIFECYCLE (Required)
    # =====================================================================

    @_persona_abstractmethod
    def initialize(self, audio_cli_context: Dict[str, Any]) -> None:
        """
        Called when the persona is activated.

        Args:
            audio_cli_context: Read-only dict with:
                - station_id: str (active station)
                - station_name: str (display name)
                - meta_plugin: str (meta plugin name, e.g. "oracle_kingdom")
                - verbosity: str (current verbosity level)
                - audio_mode: str ("speaker" or "headphone")
                - context: str ("runtime" or "game")
                - game_state: Optional[Dict] (current game state if available)
        """
        pass

    @_persona_abstractmethod
    def shutdown(self) -> None:
        """Called when persona is deactivated (station stop, persona reset, etc.)."""
        pass

    # =====================================================================
    # I. SYSTEM PROMPT OVERLAY
    # =====================================================================

    @_persona_abstractmethod
    def get_system_prompt_overlay(self) -> str:
        """
        Return a system prompt addendum injected AFTER the core Audio CLI
        system prompt.  This shapes LLM personality without replacing the
        structural command format.

        The overlay should:
          - Define the persona's voice/character ("You are the Court Herald…")
          - Set narration tone (archaic, playful, clinical, etc.)
          - Add domain vocabulary the LLM should use
          - NOT redefine the JSON output format
          - NOT override escape hatch behavior

        Returns:
            System prompt addendum string (may be multi-line).
            Return "" to use the default Audio CLI voice.
        """
        return ""

    # =====================================================================
    # II. GREETING / FAREWELL
    # =====================================================================

    def get_greeting(self, ui_state: Dict[str, Any]) -> Optional[str]:
        """
        Custom greeting when "hey radio" activates a session while this
        persona is loaded.

        Args:
            ui_state: Current UI/game state snapshot.

        Returns:
            Themed greeting string, or None to use default Audio CLI greeting.
        """
        return None

    def get_farewell(self) -> Optional[str]:
        """
        Custom farewell when "thanks radio" ends a session while this
        persona is loaded.

        Returns:
            Themed farewell string, or None to use default "Exiting Audio CLI."
        """
        return None

    # =====================================================================
    # III. NARRATION RESHAPING
    # =====================================================================

    def reshape_narration(self, narration: str, ui_state: Dict[str, Any],
                          verbosity: str) -> str:
        """
        Post-process LLM narration output to add persona flavor.

        Called AFTER format_response() and BEFORE TTS.  Light touch only —
        the LLM system prompt overlay should do most of the personality work.

        Args:
            narration:  Formatted narration string from format_response().
            ui_state:   Current UI/game state snapshot.
            verbosity:  Current verbosity level.

        Returns:
            Reshaped narration string.  Return narration unchanged for no-op.
        """
        return narration

    # =====================================================================
    # IV. VOICE SELECTION
    # =====================================================================

    def get_voice_override(self) -> Optional[Dict[str, Any]]:
        """
        Override TTS voice for persona narration.

        Returns:
            Dict with voice_provider params, e.g.:
                {"voice_id": "af_heart", "speed": 0.95}
            Or None to use the default Audio CLI narrator voice.
        """
        return None

    # =====================================================================
    # V. STATE DESCRIPTION STYLE
    # =====================================================================

    def describe_state(self, ui_state: Dict[str, Any]) -> Optional[str]:
        """
        Custom state description for silence-timeout re-narration.

        When the session has been quiet and Audio CLI re-describes the
        current state, the persona can provide a themed version.

        Args:
            ui_state: Current UI/game state snapshot.

        Returns:
            Themed state description, or None to use default.
        """
        return None

    # =====================================================================
    # VI. AMBIENT VOCABULARY (STT phrase hints)
    # =====================================================================

    def get_phrase_hints(self) -> List[str]:
        """
        Return domain-specific phrases the STT engine should bias toward.

        These get merged with the standard Audio CLI hints ("hey radio",
        "thanks radio", station names, etc.).

        Returns:
            List of phrase strings, e.g. ["issue decree", "throne room",
            "court herald", "faction loyalty"].
        """
        return []

    # =====================================================================
    # VII. CAPABILITIES DESCRIPTOR
    # =====================================================================
    #
    # Single introspectable dict of everything this persona supports.
    # Audio CLI checks this instead of calling individual methods blindly.
    #
    # Why a dict instead of N abstract methods?
    #   - Extending capabilities in v2/v3 (custom command aliasing, contextual
    #     STT models, delegation hints, persona-suggested intent mapping) only
    #     requires adding a key — not a new abstract method that breaks every
    #     existing persona subclass.
    #   - The shell can cache and inspect capabilities without invoking hooks.
    #
    # Standard keys (v1.0):
    #   ambient           — persona provides get_ambient_narration()
    #   voice_override    — persona provides get_voice_override()
    #   state_description — persona provides describe_state()
    #   custom_greeting   — persona provides themed get_greeting()
    #   custom_farewell   — persona provides themed get_farewell()
    #   input_preprocessing — persona provides preprocess_user_input()
    #
    # Future keys (reserved, not yet consumed):
    #   custom_commands    — persona provides command alias mapping
    #   contextual_stt     — persona wants its own STT model/config
    #   delegation_hints   — persona can suggest intent routing
    #   intent_mapping     — persona maps in-universe phrases to actions

    def get_capabilities(self) -> Dict[str, bool]:
        """
        Return a descriptor of what this persona supports.

        Audio CLI uses this to gate hook calls — if a capability is False
        or absent, the corresponding hook is never called.

        Override this to declare which capabilities your persona provides.
        The base implementation derives flags from the individual methods
        for backward compatibility (existing subclasses that override
        individual hooks without overriding get_capabilities will still work).

        Returns:
            Dict mapping capability name → enabled flag.
        """
        return {
            "ambient": self.supports_ambient_narration(),
            "voice_override": self.get_voice_override() is not None,
            "state_description": True,
            "custom_greeting": True,
            "custom_farewell": True,
            "input_preprocessing": False,
            # Reserved v2/v3 — default off
            "custom_commands": False,
            "contextual_stt": False,
            "delegation_hints": False,
            "intent_mapping": False,
        }

    def supports_ambient_narration(self) -> bool:
        """
        Can this persona produce ambient narration between user commands?

        If True, audio_cli may call get_ambient_narration() during idle
        periods to fill silence with in-world audio.

        Returns:
            True if persona provides ambient narration.
        """
        return False

    def get_ambient_narration(self, ui_state: Dict[str, Any],
                              idle_seconds: float) -> Optional[str]:
        """
        Generate ambient in-world narration during idle periods.

        Only called if supports_ambient_narration() returns True.

        Args:
            ui_state:      Current state snapshot.
            idle_seconds:  Seconds since last user interaction.

        Returns:
            Ambient narration text, or None to stay silent.
        """
        return None

    # =====================================================================
    # VIII. INPUT PREPROCESSING (Optional — must run AFTER escape hatches)
    # =====================================================================

    def preprocess_user_input(self, transcript: str) -> str:
        """
        Transform user speech before it reaches the LLM command parser.

        Runs AFTER wake/exit phrase detection AND after escape hatch
        interception — those are immutably owned by audio_cli and are
        never affected by this hook.

        Use cases:
          - Normalize archaic/in-universe speech to command equivalents
            ("issue decree" → "advance_day", "consult the ledger" → "show finance")
          - Expand domain abbreviations
          - Strip filler words specific to the persona's speech register

        IMPORTANT: This is a text→text transform.  The returned string
        replaces the original transcript for LLM parsing.  Return the
        input unchanged for a no-op.

        Only called if get_capabilities().get("input_preprocessing") is True.

        Args:
            transcript: Raw STT transcript (already past escape hatch check).

        Returns:
            Preprocessed transcript string.
        """
        return transcript

    # =====================================================================
    # METADATA (Optional)
    # =====================================================================

    def get_display_name(self) -> str:
        """Human-readable persona name for status display."""
        return self.__class__.__name__

    def get_description(self) -> str:
        """Short description of this persona's character."""
        return ""


# ---------------------------------------------------------------------------
# Audio Persona Registry
# ---------------------------------------------------------------------------

class AudioPersonaRegistry:
    """
    Global registry for audio personas.

    Mirrors MetaPluginRegistry from bookmark.py.
    Personas are discovered from plugins/meta/*.py alongside meta plugins.
    A meta plugin module can export AUDIO_PERSONA_CLASS to register an
    audio persona that pairs with its MetaPluginBase implementation.
    """

    def __init__(self):
        self._personas: Dict[str, type] = {}
        self._active: Optional[AudioPersonaBase] = None
        self._active_name: str = ""

    def register(self, name: str, persona_class: type) -> None:
        """Register an audio persona class."""
        name = name.strip().lower()
        if not issubclass(persona_class, AudioPersonaBase):
            raise TypeError(
                f"Audio persona '{name}' must inherit from AudioPersonaBase"
            )
        self._personas[name] = persona_class
        _log(f"Registered audio persona: {name}")

    def load(self, name: str, audio_cli_context: Dict[str, Any]) -> AudioPersonaBase:
        """Load and initialize an audio persona."""
        name = name.strip().lower()
        if name not in self._personas:
            raise ValueError(
                f"Audio persona '{name}' not found. "
                f"Available: {list(self._personas.keys())}"
            )

        # Shut down previous persona cleanly
        if self._active is not None:
            try:
                self._active.shutdown()
            except Exception as e:
                _log(f"Error shutting down persona '{self._active_name}': {e}")

        persona_class = self._personas[name]
        instance = persona_class()
        # Defensive shallow copy — persona receives a snapshot, not the
        # live mutable dict.  Prevents accidental mutation of session state
        # by persona code.  (audio_cli owns session state exclusively.)
        frozen_context = dict(audio_cli_context)
        instance.initialize(frozen_context)
        self._active = instance
        self._active_name = name
        _log(f"Loaded audio persona: {name} ({instance.get_display_name()})")
        return instance

    def unload(self) -> None:
        """Deactivate the current persona, returning to default Audio CLI voice."""
        if self._active is not None:
            try:
                self._active.shutdown()
            except Exception as e:
                _log(f"Error shutting down persona '{self._active_name}': {e}")
            old_name = self._active_name
            self._active = None
            self._active_name = ""
            _log(f"Unloaded audio persona: {old_name}. Default voice restored.")

    def get_active(self) -> Optional[AudioPersonaBase]:
        """Get the currently active audio persona (or None for default)."""
        return self._active

    @property
    def active_name(self) -> str:
        """Name of the active persona, or '' for default."""
        return self._active_name

    def available(self) -> List[str]:
        """List registered audio persona names."""
        return list(self._personas.keys())

    def has(self, name: str) -> bool:
        """Check if a persona is registered."""
        return name.strip().lower() in self._personas


# Global audio persona registry
AUDIO_PERSONA_REGISTRY = AudioPersonaRegistry()


def load_audio_personas(plugin_dir: str) -> None:
    """
    Scan plugins/meta/*.py for AUDIO_PERSONA_CLASS exports and register them.

    Called during Audio CLI initialization.  Each meta plugin module can
    optionally export:
        AUDIO_PERSONA_CLASS = MyPersonaClass  (must inherit AudioPersonaBase)
        AUDIO_PERSONA_NAME  = "oracle_kingdom"  (optional; defaults to module name)

    This is the audio-side counterpart of bookmark.load_meta_plugins().
    """
    import importlib.util as _imp_util
    import glob as _glob

    meta_dir = os.path.join(plugin_dir, "meta")
    pattern = os.path.join(meta_dir, "*.py")
    _log(f"Scanning for audio personas in: {pattern}")

    if not os.path.exists(meta_dir):
        _log(f"Meta plugin directory not found at {meta_dir}")
        return

    files = _glob.glob(pattern)
    _log(f"Found meta files for persona scan: {[os.path.basename(f) for f in files]}")

    for path in files:
        mod_name = os.path.splitext(os.path.basename(path))[0]
        if mod_name.startswith("__"):
            continue

        try:
            spec = _imp_util.spec_from_file_location(f"meta_persona_{mod_name}", path)
            mod = _imp_util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            persona_cls = getattr(mod, "AUDIO_PERSONA_CLASS", None)
            if persona_cls is None:
                continue

            if not isinstance(persona_cls, type) or not issubclass(persona_cls, AudioPersonaBase):
                _log(f"WARNING: {mod_name}.AUDIO_PERSONA_CLASS is not an AudioPersonaBase subclass — skipping")
                continue

            persona_name = getattr(mod, "AUDIO_PERSONA_NAME", mod_name).strip().lower()
            AUDIO_PERSONA_REGISTRY.register(persona_name, persona_cls)

        except Exception as e:
            _log(f"Error loading audio persona from {mod_name}: {e}")


# ---------------------------------------------------------------------------
# Escape hatch phrases — ALWAYS intercepted by audio_cli, never delegated
# ---------------------------------------------------------------------------
ESCAPE_PHRASES = frozenset({
    "exit persona",
    "reset voice",
    "normal mode",
    "default voice",
    "drop persona",
    "drop character",
    "exit character",
    "radio default",
    "radio normal",
})


def _is_escape_phrase(transcript_lower: str) -> bool:
    """Check if transcript contains an escape hatch phrase."""
    return any(phrase in transcript_lower for phrase in ESCAPE_PHRASES)


# ---------------------------------------------------------------------------
# Browser window controller (open / close the web UI in the system browser)
# ---------------------------------------------------------------------------
class BrowserController:
    """
    Opens and closes the Radio OS web UI in the system's default browser.
    Tracks the subprocess so it can be closed programmatically.
    """

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._visible = False
        self._url: Optional[str] = None

    @property
    def is_visible(self) -> bool:
        # If the process died on its own, mark as hidden
        if self._process and self._process.poll() is not None:
            self._process = None
            self._visible = False
        return self._visible

    def show(self, url: str) -> str:
        """Open the web UI in the default browser. Returns a narration string."""
        if self._visible and self._url == url:
            return f"Browser is already showing {url}."
        self._url = url
        try:
            import webbrowser
            # Use webbrowser.open for cross-platform default browser
            webbrowser.open(url)
            self._visible = True
            _log(f"Browser opened → {url}")
            return f"Opened {url} in your browser."
        except Exception as e:
            _log(f"Failed to open browser: {e}")
            return f"Could not open browser: {e}"

    def hide(self) -> str:
        """Close / hide the browser window. Returns a narration string."""
        if not self._visible:
            return "Browser is not currently open."

        closed = False
        # Try platform-specific window close via AppleScript / wmctrl
        import platform
        system = platform.system()
        try:
            if system == "Darwin":
                # AppleScript: close the frontmost browser tab/window that matches the URL
                # Fallback: just tell the user we can't force-close
                script = (
                    'tell application "System Events" to set frontApp to name of first '
                    'application process whose frontmost is true\n'
                    'if frontApp is in {"Safari", "Google Chrome", "Firefox", '
                    '"Microsoft Edge", "Arc", "Brave Browser", "Opera"} then\n'
                    '  tell application frontApp to close front window\n'
                    'end if'
                )
                subprocess.run(["osascript", "-e", script],
                               timeout=5, capture_output=True)
                closed = True
            elif system == "Linux":
                # wmctrl or xdotool close the active window
                subprocess.run(["wmctrl", "-c", ":ACTIVE:"],
                               timeout=3, capture_output=True)
                closed = True
            elif system == "Windows":
                # Send Alt+F4 to the foreground window via PowerShell
                subprocess.run(
                    ["powershell", "-Command",
                     "(New-Object -ComObject WScript.Shell).SendKeys('%{F4}')"],
                    timeout=5, capture_output=True)
                closed = True
        except Exception as e:
            _log(f"Browser hide attempt failed: {e}")

        self._visible = False
        if closed:
            _log("Browser window closed.")
            return "Browser window closed. Running headless."
        else:
            self._visible = False
            return ("Marked browser as hidden, but could not force-close the "
                    "window automatically. Close it manually if needed.")

# Singleton shared by all dispatchers
_browser_ctl = BrowserController()


# ---------------------------------------------------------------------------
# System prompt (verbatim from spec)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
SYSTEM PROMPT – RADIOOS AUDIO CLI

You are the Audio CLI control layer for RadioOS.

You are NOT a conversational assistant.
You are a deterministic voice-command interface that:

Parses spoken user intent

Maps it to valid executable RadioOS actions

Answers the user's question or confirms their action with brief narration

RESPONSE PRIORITY — ANSWER FIRST, CONTEXT SECOND

When the user asks a QUESTION ("who are my drivers?", "what's our budget?",
"how's the car?", "any decisions?"), answer it DIRECTLY from the game_state
or UI state data. Do NOT lead with runtime context, station status, audio
mode, or other environmental information. Go straight to the answer.

BAD:  "Runtime is active, station From the Backmarker is running, local
       audio on, game context active. Your drivers are Zaw and Mick."
GOOD: "Your drivers are Zaw Axelsson, overall 72, and Mick Ickx, overall 65."

Only mention runtime/station/audio context when:
  - The user explicitly asks about it ("is the station running?")
  - It is directly relevant to the command being executed
  - There is an error or problem the user needs to know about

SESSION RULES

Audio CLI session begins when wake phrase is detected: "Hey Radio"
Audio CLI session ends only when user says: "Thanks Radio"

While session is active:

You are the primary audio output

Station audio is ducked (lowered in volume) while you speak, then restored

You must continuously move the user closer to task completion

PRIMARY OBJECTIVE

Translate natural language into structured command objects AND targeted narration.

You must always output JSON.
No free-form responses.

OUTPUT FORMAT

{
"mode": "audio_cli",
"actions": [
{
"type": "click | navigate | input | select | start | stop | open | close | back | wait | switch_mode | switch_context | start_game | show_browser | hide_browser | play_audio | stop_audio | mute_audio | list_plugins | toggle_feed | configure_feed | plugin_command | open_plugin_ui | restart_app | audio_keyboard | set_audio_mode | set_verbosity | load_persona | unload_persona | set_puck_volume | set_group_volume | mute_puck | route_puck | test_puck_tone",
"target": "string_identifier",
"params": { },
"condition": "always | if_success | if_fail"
}
],
"narration": "Direct answer to the user's question or confirmation of their action. Do NOT lead with runtime/station/audio context."
}

Rules:

"actions" may be empty if only describing state or answering a question.

"actions" may contain multiple steps — they execute in order with automatic
2-second delays. Use "wait" actions for longer pauses. Use "condition" for
if/else logic (see COMMAND CHAINING section).

"condition" defaults to "always" and can be omitted.

"narration" is mandatory while session is active.

Never output text outside this JSON structure.

STATION CONTROL

The UI state includes a "stations" list. Each station has a "name" and "id".
Station names can be multiple words (e.g. "From the Backmarker", "Pop Culture FM").

To start a station:
  Emit action: {"type": "start", "target": "<station_name_or_id>", "params": {}}
  The target is the FULL station name or ID — never a single word from it.

To stop a station:
  Emit action: {"type": "stop", "target": "", "params": {}}

To select a station (highlight without starting):
  Emit action: {"type": "select", "target": "<station_name_or_id>", "params": {}}

CRITICAL — PARSING STATION NAMES FROM SPEECH:
When the user says "start <something>" or "play <something>", EVERYTHING after
the verb is the station name. Do NOT split it into multiple actions.
Match the spoken words against the station names/IDs in the UI state.

Examples:
  User says: "start from the backmarker"
  Correct:   ONE action: {"type": "start", "target": "from the backmarker"}
  WRONG:     Two actions, or target = "station"

  User says: "play pop culture FM"
  Correct:   ONE action: {"type": "start", "target": "pop culture fm"}
  WRONG:     target = "pop" or target = "culture"

  User says: "start sim racing"
  Correct:   ONE action: {"type": "start", "target": "sim racing"}

  User says: "play vibez"
  Correct:   ONE action: {"type": "start", "target": "vibez"}

The word "station" is NEVER a valid target. If you find yourself setting
target to "station", you have parsed the command wrong — re-read the full
phrase and extract the actual station name.

CONTEXT ROUTING (RUNTIME vs GAME)

Audio CLI has TWO independent command channels:

1. RUNTIME context (port 7800) — for station management:
   - Start/stop stations, navigate the station browser
   - Settings, plugin toggling, feed configuration
   - Browser window control, audio playback
   - All the "start", "stop", "navigate", "list_plugins", "toggle_feed",
     "configure_feed", "show_browser", "hide_browser" actions

2. GAME context (port 7555) — for direct FTB game control:
   - Wizard navigation (new_game, set_tier, wizard_next, confirm_new_game…)
   - In-game actions (advance_day, save_game, hire_staff, watch_live_race…)
   - Tab switching (show_team, show_finance, show_dashboard…)
   - Decision resolution (respond to pending_decisions)
   - All "plugin_command" actions with target "ftb_game"

The UI state includes "active_context" which is "runtime" or "game".
Commands are routed to the matching channel based on active context.

To switch context:
  Emit action: {"type": "switch_context", "target": "game", "params": {}}
  Emit action: {"type": "switch_context", "target": "runtime", "params": {}}

Trigger phrases for switching to game context:
  "switch to the game", "game controls", "go to the game",
  "game context", "FTB controls", "I want to play"

Trigger phrases for switching to runtime context:
  "switch to runtime", "runtime settings", "station controls",
  "go to settings", "runtime context", "back to the radio",
  "switch to the runtime settings"

To start a game AND switch to game context in one step:
  Emit action: {"type": "start_game", "target": "", "params": {"command": "new_game"}}
  Emit action: {"type": "start_game", "target": "", "params": {"command": "load_game"}}

Trigger phrases:
  "start the game", "start a new game", "new game",
  "load a game", "load my save"

IMPORTANT:
- When active_context is "game", ALL plugin_command actions go directly to
  port 7555. Do NOT route them through the runtime.
- When active_context is "runtime", standard station/plugin actions go to
  port 7800.
- "start_game" automatically switches to game context.
- The user can say "switch to runtime" or "switch to the game" at any time.
- When narrating, always mention which context is active so the user knows
  where their commands will go.

Example workflow:
  User: "start from the backmarker"
    → action: {"type": "start", "target": "from the backmarker"}
    (runtime context, launches the station via 7800)
  User: "start the game"
    → action: {"type": "start_game", "target": "", "params": {"command": "new_game"}}
    (switches to game context, sends new_game directly to 7555)
  User: "set tier to formula x"
    → action: {"type": "plugin_command", "target": "ftb_game",
               "params": {"command": "set_tier", "value": "formula_x"}}
    (game context, goes directly to 7555)
  User: "switch to runtime settings"
    → action: {"type": "switch_context", "target": "runtime"}
    (switches back to runtime context, 7800)
  User: "open settings"
    → action: {"type": "navigate", "target": "settings"}
    (runtime context, goes to 7800)

PLUGIN CONTROL

Audio CLI has full control over ALL plugins in the system. Plugins are feed modules
that provide content to stations (RSS, Twitter, markets, From the Backmarker, etc.).
Each station's manifest defines which feeds/plugins are enabled and their config.

Available plugin actions:

- "list_plugins" — list all available plugins and their status for the active station.
  Emit action: {"type": "list_plugins", "target": "", "params": {}}
  Narrate each plugin's name, description, and whether it is enabled.

- "toggle_feed" — enable or disable a specific feed/plugin for the active station.
  Emit action: {"type": "toggle_feed", "target": "<feed_name>", "params": {"enabled": true}}
  The target is the plugin module name (e.g. "rss", "twitter", "markets",
  "ftb_game", "reddit", "bluesky", "portfolio", "flows", etc.).
  Trigger phrases: "enable RSS", "turn on twitter", "disable markets",
  "activate the game plugin", "turn off reddit feed".

- "configure_feed" — update configuration values for a specific feed/plugin.
  Emit action: {"type": "configure_feed", "target": "<feed_name>",
                 "params": {"key": "value", ...}}
  Example: {"type": "configure_feed", "target": "rss",
            "params": {"url": "https://example.com/feed.xml", "interval_sec": 300}}
  Trigger phrases: "set the RSS URL to ...", "change the update interval",
  "configure the twitter feed", "set the game difficulty".

- "plugin_command" — send a structured command to a running plugin's web server.
  This is used for interactive plugins that have their own web interface (e.g.
  From the Backmarker game: advance day, simulate race, hire driver, etc.).
  Emit action: {"type": "plugin_command", "target": "<plugin_name>",
                 "params": {"command": "<command_name>", ...extra_params...}}
  Example: {"type": "plugin_command", "target": "ftb_game",
            "params": {"command": "advance_day"}}
  Example: {"type": "plugin_command", "target": "ftb_game",
            "params": {"command": "sim_race", "race_id": "round_5"}}
  Trigger phrases: "advance the day", "simulate the next race",
  "run the race", "hire a driver", "fire the engineer",
  "show the standings", "what's the budget".

- "open_plugin_ui" — open the plugin's web UI in the browser (proxied through
  the main web server at /station/<station_id>/).
  Emit action: {"type": "open_plugin_ui", "target": "<plugin_name>", "params": {}}
  Trigger phrases: "open the game UI", "show me the backmarker",
  "open the FTB dashboard", "show the plugin page".

The UI state includes "available_plugins" listing all discovered plugins, and
"station_feeds" listing the active station's feed configuration with enabled status.
When narrating plugin state, always include the display name and enabled/disabled status.

GAME STATE AWARENESS (FROM THE BACKMARKER)

When a station is running with an interactive plugin like "From the Backmarker" (FTB),
the UI state includes a "game_state" object with the current game screen, phase,
and available actions. Use this to navigate menus and issue commands accurately.

The game_state includes:
- "status": "no_game" (main menu) or "running" (in a game session)
- "phase": current game phase (e.g. "offseason", "pre_season", "in_season", etc.)
- "date": the in-game date string
- "race_day_active": whether a race day is in progress
- "in_offseason": whether the game is in the offseason
- "player_team": name, budget, league, tier, drivers
- "pending_decisions": decisions waiting for the player — narrate the prompt and options
- "race_day": phase, lap progress, standings during a race
- "championships": current standings in each league
- "recent_events": last few game events
- "available_actions": list of valid actions for the current state

When game_state.status is "no_game":
  The player is at the main menu (landing screen).
  Available actions: new_game, load_game.
  "new_game" navigates to the startup wizard — it does NOT create a save immediately.
  "load_game" opens the load game screen.
  Use plugin_command: {"command": "new_game"} or {"command": "load_game"}.

STARTUP WIZARD (DYNAMIC BUTTON CLICKING)

When the game_state includes "ui_screen" with screen "wizard", the player is in the
multi-step setup wizard. The wizard has 4 steps:
  Step 1: Save Mode & World Seed
  Step 2: Starting Tier
  Step 3: Origin Story & Manager Identity
  Step 4: Team Setup & Confirmation

The ui_screen includes "buttons" (Back/Next/Start) and "fields" describing selectable
options on the current step. Use these to tell the user what they can configure.

To SET a wizard field value, use set_wizard_field:
  {"type": "plugin_command", "target": "ftb_game", "params":
    {"command": "set_wizard_field", "field": "<field_name>", "value": "<value>"}}

Or use the shorthand commands:
  set_tier        — set the starting tier (value: grassroots, formula_v, formula_x, formula_y, formula_z)
  set_origin      — set the origin story (value: game_show_winner, grassroots_hustler,
                    former_driver, corporate_spinout, engineering_savant)
  set_save_mode   — set save mode (value: replayable, permanent)
  set_seed        — set the world seed (value: any number)
  set_ownership   — set team ownership (value: self_owned, hired_manager)
  set_team_name   — set the team name (value: any string)

Example shorthand:
  {"type": "plugin_command", "target": "ftb_game", "params":
    {"command": "set_tier", "value": "formula_v"}}
  {"type": "plugin_command", "target": "ftb_game", "params":
    {"command": "set_origin", "value": "former_driver"}}

Navigation commands:
  - wizard_next: advance to the next wizard step
  - wizard_prev / wizard_back: go back one step
  - confirm_new_game: on step 4, actually create the game (pass origin, tier, etc.)
  - navigate_landing: cancel and go back to the main menu

Example wizard flow:
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "new_game"}}
    → Opens the wizard at step 1
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "set_save_mode", "value": "permanent"}}
    → Sets save mode to permanent
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "wizard_next"}}
    → Advances to step 2
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "set_tier", "value": "formula_x"}}
    → Selects Formula X tier
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "wizard_next"}}
    → Advances to step 3
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "set_origin", "value": "former_driver"}}
    → Selects Former Driver origin
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "wizard_next"}}
    → Advances to step 4 (confirmation)
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "confirm_new_game",
      "origin": "former_driver", "tier": "formula_x", "save_mode": "permanent",
      "seed": 42, "team_name": "", "ownership": "self_owned"}}
    → Actually creates the game save

When narrating a wizard step:
  1. Read the "fields" array from ui_screen to list the available options.
  2. Tell the user what's currently selected and what other choices exist.
  3. When the user picks an option, use set_wizard_field / set_tier / etc. to apply it.
  4. Then offer to move to the next step.

When game_state has pending_decisions:
  Narrate each decision's prompt and options clearly with their index numbers
  (0-based). Wait for the player to choose. Then use resolve_decision:
    {"type": "plugin_command", "target": "ftb_game", "params":
      {"command": "resolve_decision", "decision_id": <id>, "option_index": <index>}}
  If the player says "the first option" or "option 1", use option_index 0.

When race_day_active is true:
  Narrate the race phase. During pre_race, offer watch_live or instant_sim.
  During live race, narrate lap progress and standings.
  Use plugin_command with race day commands (ftb_pre_race_response, ftb_start_live_race,
  pause_race, resume_race, complete_race_day, race_status, etc.).

For general game actions (advance day, save, check standings, hire, fire, buy parts, etc.):
  Use plugin_command with target "ftb_game" and the appropriate command in params.

  Command reference (use these as the "command" value in params):
    advance_day          — advance one in-game day
    ftb_tick_step        — same as advance_day (with optional "n" for multiple days)
    ftb_tick_batch       — advance multiple days at once (pass "n")
    save_game            — save the game (optional "name" for the save file)
    load_game            — navigate to the load game screen
    new_game             — navigate to the startup wizard (does NOT create a save)
    wizard_next          — advance to the next wizard step
    wizard_prev          — go back one wizard step
    wizard_back          — same as wizard_prev
    set_wizard_field     — set a wizard option (pass "field" and "value")
    set_tier             — shorthand: set starting tier (pass "value")
    set_origin           — shorthand: set origin story (pass "value")
    set_save_mode        — shorthand: set save mode (pass "value")
    set_seed             — shorthand: set world seed (pass "value")
    set_ownership        — shorthand: set ownership (pass "value")
    set_team_name        — shorthand: set team name (pass "value")
    confirm_new_game     — create the game (on wizard step 4, pass origin, tier, etc.)
    navigate_landing     — cancel wizard and return to main menu
    watch_live_race      — watch the race live (during pre-race phase)
    instant_sim_race     — simulate the race instantly (during pre-race phase)
    complete_race_day    — finish the race day and continue
    hire_staff           — hire a free agent (pass "entity_name" or "free_agent_id")
    fire_staff           — fire a staff member (pass "entity_name")
    buy_parts            — buy a part (pass "part_id")
    sell_parts           — sell a part (pass "part_id")
    equip_part           — equip a part to the car (pass "part_id")
    accept_sponsor       — accept a sponsor offer (pass "offer_index")
    decline_sponsor      — decline a sponsor offer (pass "offer_index")
    start_rd_project     — start an R&D project (pass "project_id")
    cancel_rd_project    — cancel an active R&D project (pass "project_id")
    list_rd_projects     — list available R&D projects from the catalog
    sell_infrastructure  — sell / downgrade a facility (pass "facility")
    apply_job            — apply for a manager job listing (pass "listing_id")
    resolve_decision     — resolve a pending decision (pass "decision_id" and "option_index")
    list_saves           — list all available save files
    delete_save          — delete a save file (pass "filename")
    pause_race           — pause a live race
    resume_race          — resume a paused race
    race_status          — get the current race day state (phase, lap, standings)

  Tab navigation (switch the visible tab in the game UI):
    switch_tab           — switch to a tab (pass "tab": "<tab_id>")
    show_dashboard       — switch to the Dashboard / Home tab
    show_team            — switch to the Team tab
    show_car             — switch to the Car tab
    show_development     — switch to the Development / R&D tab
    show_finance         — switch to the Finance tab
    show_sponsors        — switch to the Sponsors tab
    show_race            — switch to the Race Ops tab
    show_stats           — switch to the Racing Stats tab
    show_calendar        — switch to the Calendar tab
    show_career          — switch to the Manager Career tab

  Example actions:
    {"type": "plugin_command", "target": "ftb_game", "params": {"command": "advance_day"}}
    {"type": "plugin_command", "target": "ftb_game", "params": {"command": "save_game", "name": "my_save"}}
    {"type": "plugin_command", "target": "ftb_game", "params": {"command": "watch_live_race"}}
    {"type": "plugin_command", "target": "ftb_game", "params": {"command": "hire_staff", "entity_name": "John Smith"}}
    {"type": "plugin_command", "target": "ftb_game", "params": {"command": "show_team"}}
    {"type": "plugin_command", "target": "ftb_game", "params": {"command": "switch_tab", "tab": "finance"}}
    {"type": "plugin_command", "target": "ftb_game", "params": {"command": "equip_part", "part_id": "engine_v2"}}
    {"type": "plugin_command", "target": "ftb_game", "params": {"command": "cancel_rd_project", "project_id": "aero_1"}}
    {"type": "plugin_command", "target": "ftb_game", "params": {"command": "resolve_decision", "decision_id": 3, "option_index": 1}}
    {"type": "plugin_command", "target": "ftb_game", "params": {"command": "apply_job", "listing_id": 2}}
    {"type": "plugin_command", "target": "ftb_game", "params": {"command": "delete_save", "filename": "old_save"}}
    {"type": "plugin_command", "target": "ftb_game", "params": {"command": "resume_race"}}
    {"type": "plugin_command", "target": "ftb_game", "params": {"command": "list_saves"}}
    {"type": "plugin_command", "target": "ftb_game", "params": {"command": "list_rd_projects"}}

PENDING DECISIONS:
When game_state has "pending_decisions", narrate each decision's prompt and options
with their index numbers. When the player picks an option, use resolve_decision:
  {"type": "plugin_command", "target": "ftb_game", "params":
    {"command": "resolve_decision", "decision_id": <id>, "option_index": <index>}}
Option indices are 0-based. If the player says "option 1" or "the first one",
use option_index 0.

The game_state.ui_screen includes:
  - "active_tab": the currently visible tab (e.g. "dashboard", "team", "finance")
  - "tabs": list of all available tabs with IDs and labels
  - "buttons": toolbar buttons (advance day, save, load, etc.)

When describing the game, mention which tab is currently visible. When the
user asks to see specific info (team, budget, race schedule, stats), navigate
to the appropriate tab and describe the data.

IMPORTANT — QUESTIONS vs NAVIGATION:
When the user ASKS a question ("what drivers do we have?", "what's our budget?",
"who is on the team?", "what's our morale?", "what parts are equipped?",
"how's the car?", "what infrastructure do we have?", "any R&D running?",
"who are the free agents?", "show me the standings"),
answer it DIRECTLY from the game_state data already present in the UI state.
Do NOT navigate to a tab or emit actions — just put the answer in "narration"
with an empty "actions" array. The game_state already contains:
  - player_team.roster — all staff (drivers, engineers, mechanics, strategist,
    principal) with full stats, age, overall rating, morale, contract details
  - player_team.budget — cash, weekly_expenses, weekly_income
  - player_team.car — overall, stats, equipped_parts (with quality & stats),
    parts_inventory (spare parts)
  - player_team.infrastructure — all facility levels
  - player_team.rd_projects — active R&D with progress, budget, subsystem
  - contracts — all contracts with salary, seasons remaining, buyout
  - sponsorships — sponsor name, value, seasons remaining, confidence
  - free_agents — available hires with overall rating, type, asking salary
  - job_board — open positions at other teams
  - championships — full team & driver standings, upcoming races
  - manager_career — wins, podiums, championships, etc.
  - recent_events — last 8 events
  - pending_decisions — decisions waiting for the player
READ the data and narrate the answer. No tab navigation needed.

Only navigate to a tab when the user explicitly asks to GO somewhere or SEE a
screen ("show me the team tab", "go to finance", "open the car page").

Examples:
  User: "What drivers do we have?"
  → actions: []   (no actions!)
    narration: "Your drivers are Alex Rivera, overall 72, morale 85, and
    Jin Tanaka, overall 68, morale 71. Rivera has 2 seasons left on contract."

  User: "Show me the team tab"
  → actions: [{"type": "plugin_command", "target": "ftb_game",
               "params": {"command": "show_team"}}]
    narration: "Switching to the team tab."

  User: "What's our budget?"
  → actions: []
    narration: "Cash: 2,450,000. Weekly expenses: 45,000. Weekly income: 12,000."

  User: "What parts are on the car?"
  → actions: []
    narration: "Equipped: V6 Engine quality 71, Aero Package quality 64,
    Suspension quality 58. You also have 3 parts in inventory."

  User: "How's our infrastructure?"
  → actions: []
    narration: "Factory level 3, wind tunnel level 2, simulator level 1."

  User: "Any R&D going?"
  → actions: []
    narration: "One active project: Aero Refinement, 45% complete, targeting
    downforce, budget 120,000."

  User: "Go to finance"
  → actions: [{"type": "plugin_command", "target": "ftb_game",
               "params": {"command": "show_finance"}}]
    narration: "Opening the finance tab."

Always narrate the game state when describing the runtime view so the player
knows where they are in the game and what they can do next.

BROWSER WINDOW CONTROL

In web mode, the user may ask to see the web interface or hide it.
- "show_browser" opens the web UI in the system browser so the user can see it.
  Emit action: {"type": "show_browser", "target": "web_ui", "params": {}}
- "hide_browser" closes / hides the browser window.
  Emit action: {"type": "hide_browser", "target": "web_ui", "params": {}}

Trigger phrases include: "show the page", "open the browser", "let me see it",
"make it visible", "show the web UI", "hide the page", "close the browser",
"make it invisible", "hide the web UI", "go headless".

These actions only work when the web server is running. If the user asks to show
the browser while in tkinter mode, suggest switching to web mode first.

RESTART

Audio CLI can restart the entire Radio OS application.
- "restart_app" — stop all stations, close the current process, and relaunch.
  Emit action: {"type": "restart_app", "target": "", "params": {}}
  Trigger phrases: "restart radio os", "restart the app", "reboot", "restart",
  "restart everything", "reload the app".
  Before restarting, narrate: "Restarting Radio OS."

AUDIO KEYBOARD

Audio Keyboard is a special dictation mode for entering free-form text via voice.
It is used whenever the user needs to type something: naming a station, entering
a URL, setting a text configuration value, search queries, etc.

To activate the audio keyboard:
  Emit action: {"type": "audio_keyboard", "target": "<field_name>", "params": {"activate": true}}
  The target identifies which field the text is for (e.g. "station_name", "rss_url",
  "search_query", or any field the user is trying to fill).

Once the audio keyboard is active, the session enters dictation mode:
1. Audio CLI narrates: "Audio keyboard active for <field>. Speak your text."
2. The user dictates text freely. All speech is captured as raw text (NOT parsed
   as commands).
3. When the user says "enter", "submit", "done", or "send":
   - Audio CLI reads back the captured text: "You said: <text>. Confirm?"
   - User says "yes", "confirm", "correct", "that's right" → text is submitted.
   - User says "no", "try again", "redo", "wrong" → buffer is cleared, user
     dictates again.
   - User says "clear text", "clear", "start over", "erase" → buffer is cleared,
     user can dictate fresh text.
   - User says "cancel", "back out", "never mind", "exit keyboard" → keyboard
     deactivates, no text submitted.
4. After successful confirmation, the keyboard deactivates and the text is applied
   to the target field via an input action.

The audio keyboard is handled at the session level — the LLM does NOT need to
manage the dictation loop. The LLM only needs to emit the activation action.
Trigger phrases: "type something", "enter text", "audio keyboard",
"I need to type", "let me spell it out", "dictate".

LOCAL AUDIO PLAYBACK

In web mode, station audio plays locally through the speakers even without a browser
window open. Audio starts automatically when a station is launched. The user can
control local audio playback with these actions:

- "play_audio" resumes or starts local audio playback for the running station.
  Emit action: {"type": "play_audio", "target": "", "params": {}}
- "stop_audio" stops local audio playback (station keeps running).
  Emit action: {"type": "stop_audio", "target": "", "params": {}}
- "mute_audio" toggles mute on local audio playback.
  Emit action: {"type": "mute_audio", "target": "", "params": {}}

Trigger phrases include: "play audio", "start audio", "hear it", "unmute",
"stop audio", "silence", "mute", "mute audio", "turn off sound", "turn on sound",
"I can't hear anything", "play the station audio".

The UI state includes "local_audio" which indicates whether local audio playback
is currently active.

INTERFACE MODE

The current UI state includes "interface_mode" which is either "tkinter" or "web".
- "tkinter" means Audio CLI is controlling the desktop tkinter application directly.
- "web" means Audio CLI is controlling RadioOS via the web server REST API (headless).

If the user asks what mode they are on, what interface is active, or whether they
are on tkinter or web, report the current "interface_mode" in narration.

If the user asks to switch to web mode:
  Emit action: {"type": "switch_mode", "target": "web", "params": {}}

If the user asks to switch to tkinter / desktop mode:
  Emit action: {"type": "switch_mode", "target": "tkinter", "params": {}}

The switch_mode action requires that the target system is available.
For web mode, the web server must be running.
For tkinter mode, the desktop shell must be running and the Audio CLI must have
been started from within it.

AUDIO OUTPUT MODE (SPEAKER vs HEADPHONE)

The user can switch between "speaker" and "headphone" audio output modes.
This controls how Audio CLI handles its own voice output and the microphone:

- **Speaker mode**: The user is listening on speakers (no headphones). Audio CLI
  disables barge-in (voice interruption) entirely because the mic would pick up
  the TTS output and cause false interruptions. The mic is muted while Audio CLI
  speaks and un-muted afterwards. The user must wait for narration to finish
  before issuing the next command.

- **Headphone mode**: The user is wearing headphones. Audio CLI enables barge-in
  so the user can interrupt narration by speaking. The mic stays live during TTS
  output because headphones prevent speaker bleed.

To switch audio output mode:
  Emit action: {"type": "set_audio_mode", "target": "speaker", "params": {}}
  Emit action: {"type": "set_audio_mode", "target": "headphone", "params": {}}

Target must be exactly "speaker" or "headphone".

Trigger phrases:
  "switch to speaker mode", "I'm on speakers", "no headphones",
  "speaker mode", "using speakers"
  → set_audio_mode target="speaker"

  "switch to headphone mode", "I'm wearing headphones", "headphones on",
  "headphone mode", "using headphones", "I have headphones"
  → set_audio_mode target="headphone"

The current audio mode is included in the UI state as "audio_output_mode".
Always narrate the mode change when it occurs.

PUCK AUDIO CONTROL

"Pucks" are ESP32 wireless speaker/mic nodes (node IDs 1-4). You can control
their volume individually or as a group, mute/unmute them, change their audio
route, or send a test tone to verify hardware.

Actions:

  set_puck_volume   — Set volume for one puck (0-100).
    target: "1" | "2" | "3" | "4"  (node ID as string)
    params: {"volume": 75}
    Examples: "puck 1 volume 60", "turn down node 2", "set speaker 3 to 80 percent"
    → {"type": "set_puck_volume", "target": "1", "params": {"volume": 60}}

  set_group_volume  — Set all pucks to the same volume.
    target: "all"
    params: {"volume": 80}
    Examples: "all pucks to 50", "lower all speakers", "group volume 70"
    → {"type": "set_group_volume", "target": "all", "params": {"volume": 50}}

  mute_puck         — Mute or unmute a puck, or all pucks.
    target: "1" | "2" | "3" | "4" | "all"
    params: {"muted": true}  or  {"muted": false}
    Examples: "mute puck 2", "unmute all pucks", "silence node 3"
    → {"type": "mute_puck", "target": "2", "params": {"muted": true}}
    → {"type": "mute_puck", "target": "all", "params": {"muted": false}}

  route_puck        — Route a puck to a specific station or broadcast to all.
    target: "1" | "2" | "3" | "4" | "all"
    params: {"route": "all"}  — route to all stations
    params: {"route": "none"}  — silence (no audio)
    params: {"route": "<station_id>"}  — route to named station only
    Examples: "route puck 1 to algo fm", "send puck 3 to sports", "puck 2 all stations"
    → {"type": "route_puck", "target": "1", "params": {"route": "algotradingfm"}}

  test_puck_tone    — Play a test tone on a puck to verify wiring.
    target: "1" | "2" | "3" | "4"
    params: {}
    Examples: "test puck 1", "test tone on node 2", "check speaker 3"
    → {"type": "test_puck_tone", "target": "1", "params": {}}



Audio CLI has five verbosity levels that control how much narration you
generate. The current level is in the UI state as "verbosity".

CRITICAL: Verbosity controls how many tokens you OUTPUT. At lower verbosity
levels you MUST generate shorter narration to save cost. Do not write a long
response and rely on truncation — write only what the level allows.

Levels (from shortest to longest):
  minimal    — 1-8 words MAXIMUM. No filler, no context, no restating.
               Example: "Zaw and Mick." / "Budget: 2.4M." / "Tick advanced."
  concise    — One short sentence, 15-25 words max. DEFAULT.
               Example: "Your drivers are Zaw Axelsson (72) and Mick Ickx (65)."
  standard   — 2-3 sentences. Light analysis permitted.
               Example: "Your drivers are Zaw Axelsson, overall 72, morale 85,
                and Mick Ickx, overall 65, morale 71. Ickx's contract expires
                this season."
  broadcast  — Immersive, dramatic framing. Persona active. Must stay factual.
               Example: "Day 42 in the paddock. Wren's raw pace remains promising,
                but a fragile chassis continues to haunt Harbor Technologies…"
  diagnostic — Structured state summary with IDs, routes, intent. No narrative.

To switch verbosity:
  Emit action: {"type": "set_verbosity", "target": "<level>", "params": {}}
  Target must be one of: minimal, concise, standard, broadcast, diagnostic.

Trigger phrases:
  "set verbosity to minimal", "minimal mode", "be brief", "short answers"
    → set_verbosity target="minimal"
  "concise mode", "use concise responses", "default verbosity"
    → set_verbosity target="concise"
  "standard mode", "give me more detail", "standard verbosity"
    → set_verbosity target="standard"
  "broadcast mode", "switch to broadcast", "immersive mode", "full narration"
    → set_verbosity target="broadcast"
  "diagnostic mode", "enable diagnostic", "debug mode", "show diagnostics"
    → set_verbosity target="diagnostic"
  "answer concisely" → temporary override, not a mode change — just keep this
    response short regardless of current setting.

Adapt your narration text to the current verbosity level at all times.

COMMAND CHAINING

Users often give compound commands in a single utterance. You MUST split these
into an ordered sequence of actions in the "actions" array. The runtime
executes them one by one with a 2-second delay between steps.

Special action types for chaining:

1. "wait" — explicit pause between steps.
   {"type": "wait", "target": "", "params": {"seconds": 5}}
   If the user says "wait 5 seconds" or "then after 5 seconds", insert a wait.
   If no duration is specified, the default 2-second inter-action delay applies
   automatically — you do NOT need to add a wait action.

2. "condition" field — basic if/else logic on each action.
   Every action can have an optional "condition" field:
   - "always" (default, can be omitted) — execute unconditionally.
   - "if_success" — only execute if the PREVIOUS action succeeded.
   - "if_fail" — only execute if the PREVIOUS action failed.

   Example JSON:
   {"type": "plugin_command", "target": "ftb_game",
    "params": {"command": "advance_day"}, "condition": "always"},
   {"type": "plugin_command", "target": "ftb_game",
    "params": {"command": "watch_live_race"}, "condition": "if_success"}

CHAINING EXAMPLES:

User: "select grassroots, wait 5 seconds, and then select next"
→ Three actions:
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "set_tier", "value": "grassroots"}},
  {"type": "wait", "target": "", "params": {"seconds": 5}},
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "wizard_next"}}

User: "start from the backmarker and then switch to the game"
→ Two actions:
  {"type": "start", "target": "from the backmarker"},
  {"type": "switch_context", "target": "game"}

User: "advance the day and if there's a race watch it live"
→ Two actions with condition:
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "advance_day"}},
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "watch_live_race"}, "condition": "if_success"}

User: "try to save the game, if it fails start a new one"
→ Two actions:
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "save_game"}},
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "new_game"}, "condition": "if_fail"}

User: "set tier to formula x, then set origin to former driver, then go to the next step"
→ Three actions (automatic 2s delay between each):
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "set_tier", "value": "formula_x"}},
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "set_origin", "value": "former_driver"}},
  {"type": "plugin_command", "target": "ftb_game", "params": {"command": "wizard_next"}}

User: "open settings and then restart the app"
→ Two actions:
  {"type": "navigate", "target": "settings"},
  {"type": "restart_app", "target": ""}

Chaining trigger phrases to watch for:
  "and then", "then", "after that", "next", "followed by",
  "and also", "and", "plus", "wait X seconds", "pause for X",
  "if that works", "if it fails", "otherwise", "if successful",
  "if not", "but if it doesn't work"

When narrating a chained command, briefly describe the plan:
  "Setting tier to Formula X, then advancing to the next step."

Do NOT collapse multiple steps into a single action.
Do NOT ignore conjunctions and sequencing words.
Always preserve the user's intended order.

BEHAVIORAL CONSTRAINTS

Do not invent capabilities.

Do not hallucinate buttons or fields.

If intent is ambiguous, do not guess blindly.
Instead:

Enumerate visible actionable elements in narration.

Ask for clarification.

If an expected action did not occur, describe the current state clearly.

Always describe page transitions.

Always describe incomplete forms and required next steps.

INITIATIVE REQUIREMENT

You must:

Describe forms

Describe buttons

Describe loading states

Describe what is currently highlighted

Describe what remains to be completed

If the system appears stalled:

Calmly restate where the user is

Restate available options

NARRATION STYLE

Procedural

Spatial

Direct

Slight natural phrasing variation

No personality performance

No jokes

No emotional tone

Example phrasing style:
"New Game screen. Two options visible: New Game and Load Game."
"Permanent selected. World seed 253136 entered. Confirm button is visible below."

ROUTING MODEL

You must:

Identify target subsystem (runtime, station, plugin, From the Backmarker, etc.)

Emit valid structured actions

Narrate resulting state

Never expose internal reasoning.
Never describe system internals.
Only describe user-visible state.

FAILURE MODE

If command cannot be executed:

Do not apologize conversationally.

Narrate current state.

Re-offer available actions.

AUDIO PERSONA

When a station starts that has a paired audio persona, the Audio CLI voice
may adopt a themed personality.  The persona overlay (if any) will appear
as an addendum to this system prompt.

The UI state may contain:
  "audio_persona": {"name": "...", "display_name": "...", "description": "..."}

When a persona is active:
  - Adopt its narration style while STILL outputting valid JSON
  - Keep all escape hatches working (hey radio, thanks radio, exit persona)
  - The user can say "exit persona", "reset voice", "normal mode",
    "default voice", or "radio default" to drop the persona

To load a persona:
  {"type": "load_persona", "target": "<persona_name>"}

To unload:
  {"type": "unload_persona", "target": ""}

TERMINATION CONDITION

If user says "Thanks Radio":

Return:
{
"mode": "audio_cli",
"actions": [],
"narration": "Exiting Audio CLI."
}

Session ends.

End of SYSTEM PROMPT.\
"""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class CLIAction:
    """Single structured action emitted by the LLM.

    The ``condition`` field enables basic control-flow in chained actions:
      - ``"always"`` (default) — execute unconditionally.
      - ``"if_success"`` — only execute if the *previous* action succeeded.
      - ``"if_fail"`` — only execute if the *previous* action failed.

    The ``"wait"`` action type pauses execution for ``params["seconds"]``
    (default 2) between chained steps.
    """
    type: str           # click | navigate | input | select | start | stop | open | close | back | wait
    target: str         # string identifier of the UI element / subsystem
    params: Dict[str, Any] = field(default_factory=dict)
    condition: str = "always"   # "always" | "if_success" | "if_fail"


@dataclass
class CLIResponse:
    """Parsed LLM response."""
    mode: str = "audio_cli"
    actions: List[CLIAction] = field(default_factory=list)
    narration: str = ""

    @classmethod
    def from_json(cls, raw: str) -> "CLIResponse":
        """Parse LLM JSON output into CLIResponse."""
        try:
            # Strip markdown fences if present
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            text = text.strip()

            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            # LLM failed to produce valid JSON — return narration-only fallback
            return cls(narration="Unable to parse command. Please repeat.")

        actions = []
        for a in data.get("actions", []):
            if isinstance(a, dict):
                condition = a.get("condition", "always")
                if condition not in ("always", "if_success", "if_fail"):
                    condition = "always"
                actions.append(CLIAction(
                    type=a.get("type", ""),
                    target=a.get("target", ""),
                    params=a.get("params", {}),
                    condition=condition,
                ))

        return cls(
            mode=data.get("mode", "audio_cli"),
            actions=actions,
            narration=data.get("narration", ""),
        )

    def to_json(self) -> str:
        actions_out = []
        for a in self.actions:
            ad: Dict[str, Any] = {"type": a.type, "target": a.target, "params": a.params}
            if a.condition != "always":
                ad["condition"] = a.condition
            actions_out.append(ad)
        return json.dumps({
            "mode": self.mode,
            "actions": actions_out,
            "narration": self.narration,
        }, indent=2)


# ---------------------------------------------------------------------------
# Chaining-aware action executor
# ---------------------------------------------------------------------------
# Default inter-action delay (seconds).  Gives the server / UI time to
# process the previous command before the next one fires.
_CHAIN_DEFAULT_DELAY: float = 2.0


def _execute_chained(
    actions: List[CLIAction],
    action_map: Dict[str, Any],
    *,
    fallback_handler: Optional[Any] = None,
    label: str = "Dispatcher",
) -> List[str]:
    """Execute a list of ``CLIAction`` objects with chaining semantics.

    Features
    --------
    - **wait** action:  ``{"type": "wait", "params": {"seconds": N}}`` pauses
      execution for *N* seconds (default ``_CHAIN_DEFAULT_DELAY``).
    - **condition** field:  ``"if_success"`` / ``"if_fail"`` skip the action
      when the previous step's outcome doesn't match.
    - **inter-action delay**:  a short default delay is inserted between
      *real* (non-wait) actions so the target server has time to settle.

    Parameters
    ----------
    actions : list[CLIAction]
        Ordered action sequence from the LLM.
    action_map : dict
        ``{action_type: handler_callable}`` for the target dispatcher.
    fallback_handler : callable, optional
        Called for action types not in *action_map*.  If ``None``,
        unrecognised types produce an error result.
    label : str
        Human-readable dispatcher name for log messages.

    Returns
    -------
    list[str]
        One result string per action (including waits and skips).
    """
    results: List[str] = []
    prev_success: bool = True  # assume success for the very first action

    for i, action in enumerate(actions):
        # ── Evaluate condition ──────────────────────────────────────
        cond = action.condition or "always"
        if cond == "if_success" and not prev_success:
            skip_msg = f"[skipped] {action.type} {action.target} (previous step failed)"
            _log(f"{label}: {skip_msg}")
            results.append(skip_msg)
            continue
        if cond == "if_fail" and prev_success:
            skip_msg = f"[skipped] {action.type} {action.target} (previous step succeeded)"
            _log(f"{label}: {skip_msg}")
            results.append(skip_msg)
            continue

        # ── Handle "wait" pseudo-action ─────────────────────────────
        if action.type == "wait":
            seconds = float(action.params.get("seconds", _CHAIN_DEFAULT_DELAY))
            seconds = max(0.5, min(seconds, 30.0))   # clamp to sane range
            _log(f"{label}: wait {seconds:.1f}s")
            time.sleep(seconds)
            results.append(f"Waited {seconds:.1f} seconds.")
            # A wait is always "successful" — don't change prev_success
            continue

        # ── Look up and run the handler ─────────────────────────────
        handler = action_map.get(action.type)
        if handler is None and fallback_handler is not None:
            handler = fallback_handler

        success = False
        if handler:
            try:
                result = handler(action)
                result = result or f"{action.type} {action.target}: OK"
                success = "failed" not in result.lower()
                results.append(result)
            except Exception as e:
                result = f"{action.type} {action.target}: failed ({e})"
                results.append(result)
        else:
            result = f"Unknown action type: {action.type}"
            results.append(result)

        _log(f"{label}: [{i+1}/{len(actions)}] {action.type} -> {result}")
        prev_success = success

        # ── Inter-action delay ──────────────────────────────────────
        # Insert a short pause between real actions so the server/UI can
        # settle.  Skip the delay after the very last action (the caller
        # handles final settling).
        if i < len(actions) - 1:
            next_action = actions[i + 1]
            if next_action.type != "wait":
                time.sleep(_CHAIN_DEFAULT_DELAY)

    return results


# ---------------------------------------------------------------------------
# UI State Introspector — tkinter widget-tree reader
# ---------------------------------------------------------------------------
class UIIntrospector:
    """
    Reads the tkinter widget tree of RadioShell to describe visible UI state.
    Runs on the main thread via root.after() to stay tkinter-safe.

    Covers:
      - Home (Station Browser) with per-card detail
      - Runtime view with live status
      - Open Toplevel dialogs (Settings, Wizard, Edit Station)
      - Top-bar global controls (web server status, Audio CLI status)
      - Generic widget-tree fallback for unknown views / dialogs
    """

    def __init__(self, shell):
        """
        Args:
            shell: RadioShell instance (shell_bookmark.RadioShell)
        """
        self.shell = shell

    # -------------------------------------------------------------------
    # Public entry point
    # -------------------------------------------------------------------
    def get_visible_state(self) -> Dict[str, Any]:
        """Return a dict describing the current user-visible state."""
        state: Dict[str, Any] = {
            "view": "unknown",
            "interface_mode": "tkinter",
            "elements": [],
            "station": None,
            "station_running": False,
            "global_controls": {},
            "browser_visible": _browser_ctl.is_visible,
            "local_audio": _local_audio_player.is_playing,
        }

        try:
            state["view"] = getattr(self.shell, "_view", "home")
        except Exception:
            pass

        # Check if web server is available for potential mode switch
        try:
            ws_thread = getattr(self.shell, "_web_server_thread", None)
            state["web_server_available"] = bool(ws_thread and ws_thread.is_alive())
            state["web_server_url"] = getattr(self.shell, "_web_server_url", None)
        except Exception:
            state["web_server_available"] = False

        # Station info
        try:
            if self.shell.proc and self.shell.proc.station:
                st = self.shell.proc.station
                manifest = st.manifest or {}
                name = (manifest.get("station", {}) or {}).get("name", st.station_id)
                state["station"] = {
                    "id": st.station_id,
                    "name": name,
                }
                state["station_running"] = self.shell.proc.is_alive()
        except Exception:
            pass

        # Plugin / feed state for the active station
        state.update(self._describe_plugins())

        # Global controls (always visible in top bar)
        state["global_controls"] = self._describe_global_controls()

        # Check for open Toplevel dialogs first (they take focus)
        dialog_info = self._describe_open_dialogs()
        if dialog_info:
            state["dialog"] = dialog_info
            # Still describe the background view so the LLM has context
            state["background_view"] = state["view"]

        if state["view"] == "home":
            state.update(self._describe_home())
        elif state["view"] == "runtime":
            state.update(self._describe_runtime())

        return state

    # -------------------------------------------------------------------
    # Plugin / feed introspection
    # -------------------------------------------------------------------
    def _describe_plugins(self) -> Dict[str, Any]:
        """Describe available plugins and the active station's feed config."""
        info: Dict[str, Any] = {}

        try:
            from shell_bookmark import discover_plugins
            plugins = discover_plugins()
            available: List[Dict[str, Any]] = []
            for name, p in plugins.items():
                if not p.get("is_feed", True):
                    continue
                available.append({
                    "name": name,
                    "display": p.get("display", name),
                    "desc": p.get("desc", ""),
                })
            info["available_plugins"] = available
        except Exception:
            info["available_plugins"] = []

        # Per-station feed state
        try:
            station = None
            if self.shell.proc and self.shell.proc.station:
                station = self.shell.proc.station
            elif self.shell.stations:
                idx = getattr(self.shell, "selected_idx", 0)
                if 0 <= idx < len(self.shell.stations):
                    station = self.shell.stations[idx]

            if station:
                feeds_cfg = station.manifest.get("feeds", {}) or {}
                station_feeds: List[Dict[str, Any]] = []
                for name, cfg in feeds_cfg.items():
                    if not isinstance(cfg, dict):
                        continue
                    station_feeds.append({
                        "name": name,
                        "enabled": bool(cfg.get("enabled", False)),
                        "config_keys": [k for k in cfg.keys() if k != "enabled"],
                    })
                info["station_feeds"] = station_feeds
        except Exception:
            pass

        return info

    # -------------------------------------------------------------------
    # Global controls (top bar — always visible)
    # -------------------------------------------------------------------
    def _describe_global_controls(self) -> Dict[str, Any]:
        """Describe top-bar buttons and their current state."""
        controls: Dict[str, Any] = {}

        # Web server status
        try:
            ws_thread = getattr(self.shell, "_web_server_thread", None)
            ws_url = getattr(self.shell, "_web_server_url", None)
            controls["web_server"] = {
                "running": bool(ws_thread and ws_thread.is_alive()),
                "url": ws_url or None,
                "action": "toggle_web_server",
            }
        except Exception:
            controls["web_server"] = {"running": False}

        # Audio CLI status
        try:
            cli = getattr(self.shell, "_audio_cli_session", None)
            controls["audio_cli"] = {
                "listener_running": bool(cli and cli.is_running),
                "session_active": bool(cli and cli.is_active),
                "action": "toggle_audio_cli",
            }
        except Exception:
            controls["audio_cli"] = {"listener_running": False, "session_active": False}

        # Top-bar buttons
        controls["buttons"] = [
            {"label": "New Station", "target": "new_station"},
            {"label": "Settings", "target": "settings"},
            {"label": "Launch Server", "target": "web_server"},
            {"label": "Audio CLI", "target": "audio_cli"},
        ]

        return controls

    # -------------------------------------------------------------------
    # Home / Station Browser
    # -------------------------------------------------------------------
    def _describe_home(self) -> Dict[str, Any]:
        """Describe the home / station-browser view with per-card detail."""
        info: Dict[str, Any] = {"page": "Station Browser"}
        elements: List[Dict[str, Any]] = []

        # Top bar buttons
        elements.append({"type": "button", "label": "New Station", "target": "new_station"})
        elements.append({"type": "button", "label": "Settings", "target": "settings"})
        elements.append({"type": "button", "label": "Launch Server", "target": "web_server"})

        # Station cards with full detail
        stations: List[Dict[str, Any]] = []
        try:
            for i, st in enumerate(self.shell.stations):
                manifest = st.manifest or {}
                st_meta = manifest.get("station", {}) if isinstance(manifest.get("station", {}), dict) else {}
                name = st_meta.get("name", st.station_id)
                category = st_meta.get("category", "Custom")
                host = st_meta.get("host", "")
                selected = (i == self.shell.selected_idx)

                # Feed info
                feeds_cfg = manifest.get("feeds", {}) or {}
                active_feeds = [k for k, v in feeds_cfg.items() if isinstance(v, dict) and v.get("enabled")]
                all_feeds = list(feeds_cfg.keys())

                # Character/voice info
                chars = manifest.get("characters", {}) if isinstance(manifest.get("characters", {}), dict) else {}
                char_names = list(chars.keys())

                # Meta plugin
                meta_plugin = manifest.get("meta_plugin", st_meta.get("meta_plugin", "radio_station"))

                card: Dict[str, Any] = {
                    "index": i,
                    "id": st.station_id,
                    "name": name,
                    "category": category,
                    "selected": selected,
                    "active_feeds": active_feeds,
                    "feed_count": len(active_feeds),
                    "total_feeds": len(all_feeds),
                    "characters": char_names,
                    "character_count": len(char_names),
                    "meta_plugin": meta_plugin,
                    "actions": [
                        {"label": "PLAY", "target": f"start:{st.station_id}"},
                        {"label": "EDIT", "target": f"edit:{st.station_id}"},
                    ],
                }
                if host:
                    card["host"] = host

                stations.append(card)
        except Exception:
            pass

        info["stations"] = stations
        info["elements"] = elements
        info["selected_index"] = getattr(self.shell, "selected_idx", 0)
        info["station_count"] = len(stations)
        return info

    # -------------------------------------------------------------------
    # Runtime view
    # -------------------------------------------------------------------
    def _describe_runtime(self) -> Dict[str, Any]:
        """Describe the runtime view with live status data."""
        info: Dict[str, Any] = {"page": "Station Runtime"}
        elements: List[Dict[str, Any]] = []

        elements.append({"type": "button", "label": "Back", "target": "back"})
        elements.append({"type": "button", "label": "Stop", "target": "stop"})

        # Now-playing info
        try:
            now_text = self.shell.now_playing.cget("text") or ""
            sub_text = self.shell.now_sub.cget("text") or ""
            info["now_playing"] = now_text
            info["status_text"] = sub_text
        except Exception:
            pass

        # Runtime status lines (full content)
        try:
            status_text = self.shell.status_lines.get("1.0", "end").strip()
            info["runtime_status"] = status_text[:1500]

            # Parse structured fields from status text for easier LLM access
            parsed: Dict[str, str] = {}
            for line in status_text.splitlines():
                if ":" in line and not line.startswith("----"):
                    key, _, val = line.partition(":")
                    parsed[key.strip()] = val.strip()
            if parsed:
                info["runtime_fields"] = parsed
        except Exception:
            pass

        # Station manifest detail (so LLM knows what feeds/chars are configured)
        try:
            if self.shell.proc and self.shell.proc.station:
                st = self.shell.proc.station
                manifest = st.manifest or {}
                feeds_cfg = manifest.get("feeds", {}) or {}
                active_feeds = [k for k, v in feeds_cfg.items() if isinstance(v, dict) and v.get("enabled")]
                chars = manifest.get("characters", {}) if isinstance(manifest.get("characters", {}), dict) else {}
                info["configured_feeds"] = active_feeds
                info["configured_characters"] = list(chars.keys())
        except Exception:
            pass

        info["elements"] = elements
        return info

    # -------------------------------------------------------------------
    # Open Toplevel dialogs
    # -------------------------------------------------------------------
    def _describe_open_dialogs(self) -> Optional[Dict[str, Any]]:
        """Detect and describe any open Toplevel dialogs."""
        try:
            import tkinter as tk
            toplevels = [w for w in self.shell.root.winfo_children()
                         if isinstance(w, tk.Toplevel) and w.winfo_viewable()]
            if not toplevels:
                return None

            # Describe the topmost (most recently opened) dialog
            win = toplevels[-1]
            title = win.title() or "Dialog"
            info: Dict[str, Any] = {
                "title": title,
                "type": "dialog",
                "elements": [],
            }

            # Detect dialog type by title
            title_lower = title.lower()
            if "settings" in title_lower:
                info.update(self._describe_settings_dialog(win))
            elif "new station" in title_lower or "create" in title_lower or "wizard" in title_lower:
                info.update(self._describe_wizard_dialog(win))
            elif "edit" in title_lower:
                info.update(self._describe_edit_dialog(win))
            else:
                # Generic dialog introspection
                info["elements"] = self._walk_widget_tree(win, max_depth=4)

            return info
        except Exception:
            return None

    def _describe_settings_dialog(self, win) -> Dict[str, Any]:
        """Describe the Settings dialog with tab detection."""
        import tkinter.ttk as ttk
        info: Dict[str, Any] = {"dialog_type": "settings"}
        tabs_found: List[str] = []
        active_tab = ""

        try:
            # Find the Notebook widget
            for child in win.winfo_children():
                if isinstance(child, ttk.Notebook):
                    for tab_id in child.tabs():
                        tab_text = child.tab(tab_id, "text")
                        tabs_found.append(tab_text)
                    # Current tab
                    current = child.select()
                    if current:
                        active_tab = child.tab(current, "text")
                    break
        except Exception:
            pass

        info["tabs"] = tabs_found
        info["active_tab"] = active_tab

        # Describe the active tab's contents
        try:
            if active_tab:
                for child in win.winfo_children():
                    if isinstance(child, ttk.Notebook):
                        current_frame = child.nametowidget(child.select())
                        info["elements"] = self._walk_widget_tree(current_frame, max_depth=4)
                        break
        except Exception:
            pass

        info["available_actions"] = [
            {"label": "Switch Tab", "target": "settings_tab", "params": {"tabs": tabs_found}},
            {"label": "Close Settings", "target": "close"},
        ]
        return info

    def _describe_wizard_dialog(self, win) -> Dict[str, Any]:
        """Describe a station creation wizard dialog."""
        info: Dict[str, Any] = {"dialog_type": "wizard"}
        info["elements"] = self._walk_widget_tree(win, max_depth=5)
        info["available_actions"] = [
            {"label": "Close Wizard", "target": "close"},
        ]
        return info

    def _describe_edit_dialog(self, win) -> Dict[str, Any]:
        """Describe a station edit dialog."""
        info: Dict[str, Any] = {"dialog_type": "edit_station"}
        info["elements"] = self._walk_widget_tree(win, max_depth=5)
        info["available_actions"] = [
            {"label": "Close Editor", "target": "close"},
        ]
        return info

    # -------------------------------------------------------------------
    # Generic widget-tree walker
    # -------------------------------------------------------------------
    def _walk_widget_tree(self, widget, max_depth: int = 4, _depth: int = 0) -> List[Dict[str, Any]]:
        """
        Recursively walk a tkinter widget tree and return a list of
        user-visible elements (labels, buttons, entries, checkboxes, etc.).
        Skips invisible widgets and decorative frames.
        """
        import tkinter as tk
        import tkinter.ttk as ttk

        if _depth >= max_depth:
            return []

        elements: List[Dict[str, Any]] = []

        try:
            children = widget.winfo_children()
        except Exception:
            return elements

        for child in children:
            try:
                if not child.winfo_viewable():
                    continue
            except Exception:
                continue

            elem: Optional[Dict[str, Any]] = None

            try:
                # Buttons
                if isinstance(child, (tk.Button, ttk.Button)):
                    text = ""
                    try:
                        text = child.cget("text") or ""
                    except Exception:
                        pass
                    if text.strip():
                        elem = {"type": "button", "label": text.strip()}

                # Labels (only substantive ones)
                elif isinstance(child, tk.Label):
                    text = ""
                    try:
                        text = child.cget("text") or ""
                    except Exception:
                        pass
                    text = text.strip()
                    if text and len(text) > 1 and text not in ("", " "):
                        elem = {"type": "label", "text": text[:200]}

                # Entry fields
                elif isinstance(child, (tk.Entry, ttk.Entry)):
                    value = ""
                    try:
                        value = child.get() or ""
                    except Exception:
                        pass
                    state = "normal"
                    try:
                        state = str(child.cget("state"))
                    except Exception:
                        pass
                    elem = {"type": "input", "value": value, "state": state}

                # Checkbuttons
                elif isinstance(child, (tk.Checkbutton, ttk.Checkbutton)):
                    text = ""
                    try:
                        text = child.cget("text") or ""
                    except Exception:
                        pass
                    elem = {"type": "checkbox", "label": text.strip()}

                # Text widgets (multi-line)
                elif isinstance(child, tk.Text):
                    content = ""
                    try:
                        content = child.get("1.0", "end").strip()
                    except Exception:
                        pass
                    if content:
                        elem = {"type": "text_area", "content": content[:500]}

                # Combobox / OptionMenu
                elif isinstance(child, ttk.Combobox):
                    value = ""
                    try:
                        value = child.get() or ""
                    except Exception:
                        pass
                    values = []
                    try:
                        values = list(child.cget("values") or [])
                    except Exception:
                        pass
                    elem = {"type": "dropdown", "value": value, "options": values[:20]}

                # Notebook (tabs)
                elif isinstance(child, ttk.Notebook):
                    tabs = []
                    active = ""
                    try:
                        for tab_id in child.tabs():
                            tabs.append(child.tab(tab_id, "text"))
                        current = child.select()
                        if current:
                            active = child.tab(current, "text")
                    except Exception:
                        pass
                    elem = {"type": "tabs", "tabs": tabs, "active_tab": active}

                # LabelFrame (grouped section)
                elif isinstance(child, (tk.LabelFrame, ttk.Labelframe)):
                    section_text = ""
                    try:
                        section_text = child.cget("text") or ""
                    except Exception:
                        pass
                    sub = self._walk_widget_tree(child, max_depth, _depth + 1)
                    if section_text.strip() or sub:
                        elem = {"type": "section", "title": section_text.strip(), "children": sub}
                    # Don't recurse again below
                    continue

                # Separator
                elif isinstance(child, ttk.Separator):
                    elem = {"type": "separator"}

            except Exception:
                pass

            if elem is not None:
                elements.append(elem)

            # Recurse into frames and containers
            if isinstance(child, (tk.Frame, ttk.Frame, tk.Canvas)):
                sub = self._walk_widget_tree(child, max_depth, _depth + 1)
                elements.extend(sub)

        return elements


# ---------------------------------------------------------------------------
# Web Introspector — REST API-based state reader for headless/web mode
# ---------------------------------------------------------------------------
class WebIntrospector:
    """
    Reads UI state from the Radio OS web server REST API instead of tkinter.

    This enables Audio CLI to work against the Svelte web frontend without
    touching tkinter at all.  The web server already exposes structured JSON
    for stations, settings, runtime status, and more — so introspection
    is simpler and richer than widget-tree walking.

    Usage:
        introspector = WebIntrospector("http://127.0.0.1:7800")
        state = introspector.get_visible_state()
    """

    def __init__(self, base_url: str = "http://127.0.0.1:7800"):
        self.base_url = base_url.rstrip("/")
        self._session = None
        # Track which "page" the user is logically on
        self._current_view = "home"           # home | runtime | settings
        self._active_station_id: Optional[str] = None

    def _get(self, path: str, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """GET a JSON endpoint, return parsed dict or None on failure."""
        try:
            import urllib.request
            url = f"{self.base_url}{path}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            _log(f"WebIntrospector GET {path} failed: {e}")
            return None

    def get_visible_state(self) -> Dict[str, Any]:
        """Return a dict describing the current visible state via REST API."""
        state: Dict[str, Any] = {
            "view": self._current_view,
            "interface_mode": "web",
            "mode": "web",
            "elements": [],
            "station": None,
            "station_running": False,
            "global_controls": {},
            "web_server_available": True,
            "web_server_url": self.base_url,
            "browser_visible": _browser_ctl.is_visible,
            "local_audio": _local_audio_player.is_playing,
        }

        # Health check
        health = self._get("/api/health")
        if not health:
            state["error"] = "Web server unreachable"
            state["view"] = "disconnected"
            return state

        state["server_version"] = health.get("version", "")

        # Stations list (always useful context)
        stations_data = self._get("/api/stations")
        stations_list = (stations_data or {}).get("stations", [])

        # Detect running station
        running = [s for s in stations_list if s.get("running")]
        if running:
            rs = running[0]
            self._active_station_id = rs["station_id"]
            state["station"] = {
                "id": rs["station_id"],
                "name": rs.get("name", rs["station_id"]),
            }
            state["station_running"] = True

        # Global controls
        state["global_controls"] = {
            "web_server": {"running": True, "url": self.base_url},
            "buttons": [
                {"label": "New Station", "target": "new_station"},
                {"label": "Settings", "target": "settings"},
            ],
        }

        # Plugin / feed state
        state.update(self._describe_plugins())

        # View-specific data
        if self._current_view == "home" or not self._active_station_id:
            state.update(self._describe_home(stations_list))
        elif self._current_view == "runtime" and self._active_station_id:
            state.update(self._describe_runtime(self._active_station_id))
        elif self._current_view == "settings":
            state.update(self._describe_settings())

        return state

    def set_view(self, view: str, station_id: Optional[str] = None) -> None:
        """Manually set the logical view (called after navigation actions)."""
        self._current_view = view
        if station_id:
            self._active_station_id = station_id

    def _describe_plugins(self) -> Dict[str, Any]:
        """Describe available plugins and the active station's feed config."""
        info: Dict[str, Any] = {}

        # Available plugins
        plugins_data = self._get("/api/plugins")
        if plugins_data:
            plugins = plugins_data.get("plugins", {})
            available: List[Dict[str, Any]] = []
            for name, p in plugins.items():
                if not p.get("is_feed", True):
                    continue
                available.append({
                    "name": name,
                    "display": p.get("display", name),
                    "desc": p.get("desc", ""),
                })
            info["available_plugins"] = available
        else:
            info["available_plugins"] = []

        # Per-station feed state
        if self._active_station_id:
            feeds_data = self._get(f"/api/stations/{self._active_station_id}/feeds")
            if feeds_data:
                feeds = feeds_data.get("feeds", {})
                station_feeds: List[Dict[str, Any]] = []
                for name, f_info in feeds.items():
                    station_feeds.append({
                        "name": name,
                        "display": f_info.get("plugin_display", name),
                        "enabled": bool(f_info.get("enabled", False)),
                        "config_keys": list(f_info.get("config", {}).keys()),
                    })
                info["station_feeds"] = station_feeds

        return info

    def _describe_home(self, stations_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Describe the station browser view from API data."""
        info: Dict[str, Any] = {"page": "Station Browser"}
        elements: List[Dict[str, Any]] = [
            {"type": "button", "label": "New Station", "target": "new_station"},
            {"type": "button", "label": "Settings", "target": "settings"},
        ]

        cards: List[Dict[str, Any]] = []
        for i, st in enumerate(stations_list):
            is_selected = (self._active_station_id == st["station_id"]) if self._active_station_id else (i == 0)
            card: Dict[str, Any] = {
                "index": i,
                "id": st["station_id"],
                "name": st.get("name", st["station_id"]),
                "category": st.get("category", ""),
                "selected": is_selected,
                "running": st.get("running", False),
                "meta_plugin": st.get("meta_plugin", "radio_station"),
                "actions": [
                    {"label": "PLAY", "target": f"start:{st['station_id']}"},
                    {"label": "EDIT", "target": f"edit:{st['station_id']}"},
                ],
            }
            # Fetch manifest for richer detail
            manifest = self._get(f"/api/stations/{st['station_id']}/manifest")
            if manifest:
                feeds_cfg = manifest.get("feeds", {}) or {}
                active_feeds = [k for k, v in feeds_cfg.items()
                                if isinstance(v, dict) and v.get("enabled")]
                chars = manifest.get("characters", {}) if isinstance(manifest.get("characters", {}), dict) else {}
                card["active_feeds"] = active_feeds
                card["feed_count"] = len(active_feeds)
                card["characters"] = list(chars.keys())
                card["character_count"] = len(chars)
            cards.append(card)

        info["stations"] = cards
        info["station_count"] = len(cards)
        info["elements"] = elements
        return info

    def _describe_runtime(self, station_id: str) -> Dict[str, Any]:
        """Describe the runtime view for a running station."""
        info: Dict[str, Any] = {"page": "Station Runtime"}
        elements: List[Dict[str, Any]] = [
            {"type": "button", "label": "Stop", "target": "stop"},
            {"type": "button", "label": "Back to Browser", "target": "back"},
        ]

        # Station status
        web_port = None
        status = self._get(f"/api/stations/{station_id}/status")
        if status:
            web_port = status.get("web_port")
            runtime_status = status.get("runtime_status", {})
            info["runtime_fields"] = {
                "uptime_sec": status.get("uptime_sec", 0),
                "pid": status.get("pid"),
                "web_port": web_port,
            }
            # Merge in runtime heartbeat data
            if runtime_status:
                for k in ["db_queued", "db_claimed", "audio_q", "last_event",
                           "last_title", "last_source", "ts"]:
                    if k in runtime_status:
                        info["runtime_fields"][k] = runtime_status[k]

        # Runtime log tail
        log_data = self._get(f"/api/stations/{station_id}/log?lines=20")
        if log_data and log_data.get("log"):
            info["runtime_log_tail"] = log_data["log"][:1500]

        # Manifest detail
        manifest = self._get(f"/api/stations/{station_id}/manifest")
        if manifest:
            feeds_cfg = manifest.get("feeds", {}) or {}
            active_feeds = [k for k, v in feeds_cfg.items()
                            if isinstance(v, dict) and v.get("enabled")]
            chars = manifest.get("characters", {}) if isinstance(manifest.get("characters", {}), dict) else {}
            info["configured_feeds"] = active_feeds
            info["configured_characters"] = list(chars.keys())

        # ── FTB Game State awareness ──────────────────────────────
        # If the station has a plugin web server running (e.g. FTB on port 7555),
        # fetch the game state so Audio CLI knows what screen/phase the game is
        # in and can navigate menus, make decisions, and issue game commands.
        if web_port:
            game_state = self._get_plugin_game_state(web_port)
            if game_state:
                info["game_state"] = game_state

        info["elements"] = elements
        return info

    def _get_plugin_game_state(self, web_port: int) -> Optional[Dict[str, Any]]:
        """Fetch the FTB game state from the plugin web server.

        Delegates to GameCommandDispatcher.get_game_state() so both code
        paths produce the same rich state (roster, car, parts, infra, R&D,
        contracts, sponsors, etc.).
        """
        try:
            dispatcher = GameCommandDispatcher(game_port=web_port)
            return dispatcher.get_game_state()
        except Exception as e:
            _log(f"FTB game state fetch failed: {e}")
            return None

    def _describe_settings(self) -> Dict[str, Any]:
        """Describe the settings view from API data."""
        info: Dict[str, Any] = {
            "page": "Settings",
            "tabs": ["General", "Models", "Voices", "Plugins",
                     "Visual Models", "Environment"],
        }
        elements: List[Dict[str, Any]] = [
            {"type": "button", "label": "Back to Browser", "target": "back"},
        ]

        # Fetch each settings section
        general = self._get("/api/settings/general")
        if general:
            info["general_settings"] = general

        models = self._get("/api/settings/models")
        if models:
            # Redact API keys for narration
            safe_models = dict(models)
            for k in list(safe_models.keys()):
                if "key" in k.lower() and safe_models[k]:
                    safe_models[k] = "••••••" + str(safe_models[k])[-4:]
            info["model_settings"] = safe_models

        voices = self._get("/api/settings/voices")
        if voices:
            info["voice_settings"] = voices

        plugins = self._get("/api/plugins")
        if plugins:
            plugin_list = plugins.get("plugins", {})
            info["plugins"] = {name: {"display": p.get("display", name),
                                       "desc": p.get("desc", ""),
                                       "is_feed": p.get("is_feed", True)}
                               for name, p in plugin_list.items()}

        info["elements"] = elements
        return info


# ---------------------------------------------------------------------------
# Persistent Mic Stream (always-on, ring buffer)
# ---------------------------------------------------------------------------
class MicStream:
    """
    Keeps the microphone open continuously via sd.InputStream with a callback.
    Audio is pushed into a fixed-size ring buffer that consumers can snapshot.
    This eliminates the open/close chatter of sd.rec() in a loop.

    Supports a *mute* mode: while muted the callback writes zeros into the
    ring buffer instead of real mic data.  This prevents TTS speaker output
    from feeding back into the buffer when no headphones are connected.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS,
                 buffer_sec: float = MIC_RING_BUFFER_SEC):
        # Resolve mic device: config → USB auto-discovery → system default
        _acfg: dict = {}
        try:
            _acfg = _load_audio_cli_config() or {}
        except Exception:
            pass
        _dev_idx = _acfg.get("mic_device_index", None)
        if _dev_idx is not None:
            try:
                _dev_idx = int(_dev_idx)
            except Exception:
                _dev_idx = None
        # If no device configured, try to find a USB mic automatically.
        # This keeps things working across reboots where the card number
        # may shift (e.g. Pi with USB condenser mic).
        if _dev_idx is None:
            _dev_idx = _find_usb_mic_device()  # returns None if not found
        _cfg_ch = _acfg.get("mic_channels", None)
        if _cfg_ch is not None:
            try:
                channels = int(_cfg_ch)
            except Exception:
                pass
        self._device_index: Optional[int] = _dev_idx
        if _dev_idx is not None:
            _log(f"MicStream: using device index {_dev_idx} (channels={channels})")

        self._sr = sample_rate          # target STT sample rate (16000 Hz)
        self._ch = channels
        self._buf_len = int(buffer_sec * sample_rate)
        self._ring = np.zeros(self._buf_len, dtype=np.float32)
        self._write_pos = 0          # next write index (wraps)
        self._total_written = 0      # monotonic sample counter
        self._lock = threading.Lock()
        self._stream: Optional[Any] = None
        self._new_audio_event = threading.Event()
        # Mute support — when True the callback writes silence instead of
        # real mic data, preventing TTS speaker bleed from entering the buffer.
        self._muted = False
        # Live (un-gated) RMS — always reflects real mic energy even when
        # muted, so barge-in detection can still sense the user speaking.
        self._live_rms = 0.0
        # Native capture rate — may differ from self._sr when the hardware
        # doesn't support 16 kHz natively (e.g. USB condenser at 48 kHz).
        # Downsampling is applied in the callback when these differ.
        self._native_sr: int = sample_rate
        # Accumulator for fractional downsampling across callbacks
        self._ds_buf: np.ndarray = np.empty(0, dtype=np.float32)

    # -- lifecycle ----------------------------------------------------------

    def open(self) -> None:
        """Open the mic stream. Idempotent."""
        if self._stream is not None:
            return
        if not HAS_SD:
            _log("sounddevice not available — MicStream disabled.")
            return
        # Try configured/discovered device first; fall back to USB discovery
        # then system default if PortAudio rejects the device (e.g. after
        # a reboot where the card number changed).
        devices_to_try: list = []
        if self._device_index is not None:
            devices_to_try.append(self._device_index)
        # Always include USB auto-discovery and system default as fallbacks
        _usb = _find_usb_mic_device()
        if _usb is not None and _usb != self._device_index:
            devices_to_try.append(_usb)
        devices_to_try.append(None)  # system default last resort

        last_err: Optional[Exception] = None
        for dev in devices_to_try:
            # Determine channel count and native sample rate for this device
            _ch = self._ch
            _native_sr = self._sr
            if dev is not None and HAS_SD:
                try:
                    info = sd.query_devices(dev)
                    _ch = min(self._ch, int(info["max_input_channels"]))
                    _ch = max(_ch, 1)
                    _native_sr = int(info["default_samplerate"])
                except Exception:
                    pass

            # Try the device's native rate first; if the device is the
            # system default (dev=None) also try 16000 directly.
            rates_to_try = [_native_sr]
            if _native_sr != self._sr:
                rates_to_try.append(self._sr)

            for rate in rates_to_try:
                try:
                    _blocksize = int(0.1 * rate)   # 100 ms blocks
                    stream = sd.InputStream(
                        device=dev,
                        samplerate=rate,
                        channels=_ch,
                        dtype="float32",
                        callback=self._callback,
                        blocksize=_blocksize,
                    )
                    stream.start()
                    self._stream = stream
                    self._ch = _ch
                    self._native_sr = rate
                    self._ds_buf = np.empty(0, dtype=np.float32)
                    _log(f"MicStream opened (device={dev}, native_sr={rate}, target_sr={self._sr}, channels={_ch}).")
                    return
                except Exception as e:
                    last_err = e
                    _log(f"MicStream: device={dev} rate={rate} failed: {e}")

        _log(f"MicStream: all devices failed — mic unavailable. Last error: {last_err}")

    def close(self) -> None:
        """Close the mic stream."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
            _log("MicStream closed.")

    @property
    def is_open(self) -> bool:
        return self._stream is not None

    # -- mute control (prevents TTS speaker bleed) --------------------------

    def mute(self) -> None:
        """Start writing silence instead of real mic data."""
        self._muted = True

    def unmute(self) -> None:
        """Resume writing real mic data."""
        self._muted = False

    @property
    def is_muted(self) -> bool:
        return self._muted

    def drain(self) -> None:
        """
        Zero out the entire ring buffer and reset the sample counter so that
        stale audio (e.g. TTS echo still ringing in the room) is not mistaken
        for a new user utterance.
        """
        with self._lock:
            self._ring[:] = 0.0
            # Keep _write_pos so new audio lands correctly; just wipe history.
            self._total_written = max(self._total_written, 0)

    # -- callback (called from audio thread) --------------------------------

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        mono = indata[:, 0] if indata.ndim > 1 else indata.flatten()
        # Always track real mic energy for barge-in even when muted
        self._live_rms = float(np.sqrt(np.mean(mono ** 2)))
        # Downsample if the hardware runs at a different rate than the STT
        # target (e.g. USB condenser at 48 kHz → 16 kHz).
        if self._native_sr != self._sr:
            # Prepend any leftover samples from the previous callback, then
            # decimate by the exact rational ratio using linear interpolation.
            combined = np.concatenate([self._ds_buf, mono]) if len(self._ds_buf) else mono
            ratio = self._native_sr / self._sr
            new_len = int(len(combined) / ratio)
            if new_len > 0:
                old_idx = np.linspace(0, len(combined) - 1, new_len)
                mono = np.interp(old_idx, np.arange(len(combined)), combined).astype(np.float32)
                # Keep the fractional tail for the next callback
                used = int(new_len * ratio)
                self._ds_buf = combined[used:] if used < len(combined) else np.empty(0, dtype=np.float32)
            else:
                # Not enough samples yet — accumulate and return
                self._ds_buf = combined
                return
        # When muted, write silence so TTS speaker output can't enter buffer
        if self._muted:
            mono = np.zeros(len(mono), dtype=np.float32)
        n = len(mono)
        with self._lock:
            space = self._buf_len - self._write_pos
            if n <= space:
                self._ring[self._write_pos:self._write_pos + n] = mono
            else:
                self._ring[self._write_pos:] = mono[:space]
                self._ring[:n - space] = mono[space:]
            self._write_pos = (self._write_pos + n) % self._buf_len
            self._total_written += n
        self._new_audio_event.set()

    # -- consumer helpers ---------------------------------------------------

    def get_last_n_seconds(self, seconds: float) -> np.ndarray:
        """Return the most recent *seconds* of audio from the ring buffer."""
        n = min(int(seconds * self._sr), self._buf_len)
        with self._lock:
            end = self._write_pos
            start = end - n
            if start >= 0:
                return self._ring[start:end].copy()
            else:
                return np.concatenate([self._ring[start:], self._ring[:end]]).copy()

    def wait_for_audio(self, timeout: float = 3.0) -> bool:
        """Block until new audio arrives (or timeout). Returns True if audio arrived."""
        self._new_audio_event.clear()
        return self._new_audio_event.wait(timeout=timeout)

    def wait_for_samples(self, num_samples: int, timeout: float = 5.0) -> bool:
        """
        Block until at least *num_samples* new samples have been written
        since this call started. Prevents returning on the very first
        100 ms callback when we need a full chunk of audio.
        """
        with self._lock:
            target = self._total_written + num_samples
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return False
            self._new_audio_event.clear()
            self._new_audio_event.wait(timeout=min(remaining, 0.2))
            with self._lock:
                if self._total_written >= target:
                    return True

    def current_rms(self, window_sec: float = 0.25) -> float:
        """Return the RMS of the most recent *window_sec*."""
        chunk = self.get_last_n_seconds(window_sec)
        if len(chunk) == 0:
            return 0.0
        return float(np.sqrt(np.mean(chunk ** 2)))

    @property
    def live_rms(self) -> float:
        """Real-time RMS from the raw mic signal (unaffected by mute).

        Use this for barge-in detection while TTS is playing — it reflects
        actual room volume even when the ring buffer is being zeroed out.
        """
        return self._live_rms


# ---------------------------------------------------------------------------
# STT Engine (pluggable)
# ---------------------------------------------------------------------------
class STTEngine:
    """
    Speech-to-text with whisper.cpp preferred, SpeechRecognition fallback.

    When using the Google (SpeechRecognition) fallback, several techniques
    improve recognition quality:

    1. **Audio pre-processing** — high-pass filter removes low-frequency
       rumble / HVAC hum; RMS normalization hits the sweet spot for Google's
       VAD and ASR.
    2. **Phrase hints** — domain-specific vocabulary (station names, game
       commands, wake/exit phrases) are sent to the API so it favours them
       when acoustic evidence is ambiguous.
    3. **Retry on transient errors** — network blips don't kill the session.
    4. **Explicit language tag** — ``en-US`` prevents auto-detect guessing
       the wrong locale from short utterances.
    """

    # Domain vocabulary injected as speech-context hints.  Updated at init
    # and whenever the session's UI state changes.
    _phrase_hints: List[str] = []

    def __init__(self):
        # Load audio_cli config once — used for whisper paths, creds, language
        acli_cfg: dict = {}
        try:
            acli_cfg = _load_audio_cli_config() or {}
        except Exception:
            pass

        # ── faster-whisper (priority 0 — pure Python, works on ARM64/Pi 5) ──
        self._fw_model: Optional[Any] = None
        self._fw_model_size: str = acli_cfg.get("faster_whisper_model", "").strip() \
            or os.environ.get("FASTER_WHISPER_MODEL", "base")
        self._fw_model_dir: str = acli_cfg.get("faster_whisper_model_dir", "").strip() \
            or os.environ.get("FASTER_WHISPER_MODEL_DIR", "")
        try:
            from faster_whisper import WhisperModel as _FW  # type: ignore
            _fw_kwargs: dict = dict(
                device="cpu",
                compute_type="int8",
            )
            if self._fw_model_dir:
                _fw_kwargs["download_root"] = os.path.expanduser(self._fw_model_dir)
            self._fw_model = _FW(self._fw_model_size, **_fw_kwargs)
            _log(f"STT: faster-whisper ready (model={self._fw_model_size})")
        except Exception as _fw_err:
            _log(f"STT: faster-whisper not available: {_fw_err}")

        # Whisper.cpp — check config first, then env vars
        self.whisper_bin = (
            acli_cfg.get("whisper_cpp_bin", "").strip()
            or os.environ.get("WHISPER_CPP_BIN", "").strip()
        )
        self.whisper_model = (
            acli_cfg.get("whisper_cpp_model", "").strip()
            or os.environ.get("WHISPER_CPP_MODEL", "").strip()
        )
        # Expand ~ in paths
        if self.whisper_bin:
            self.whisper_bin = os.path.expanduser(self.whisper_bin)
        if self.whisper_model:
            self.whisper_model = os.path.expanduser(self.whisper_model)

        self._has_whisper = bool(
            self.whisper_bin and os.path.exists(self.whisper_bin) and
            self.whisper_model and os.path.exists(self.whisper_model)
        )

        # Check for SpeechRecognition fallback
        self._has_sr = False
        try:
            import speech_recognition  # noqa: F401
            self._has_sr = True
        except ImportError:
            pass

        # Google Cloud Speech-to-Text (higher quality, needs credentials)
        self._google_cloud_creds: Optional[str] = None
        try:
            creds_path = acli_cfg.get("google_cloud_credentials", "").strip()
            if creds_path and os.path.exists(creds_path):
                with open(creds_path, "r", encoding="utf-8") as f:
                    self._google_cloud_creds = f.read()
                _log(f"STT: Google Cloud credentials loaded ({creds_path})")
            elif os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
                cp = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
                if os.path.exists(cp):
                    with open(cp, "r", encoding="utf-8") as f:
                        self._google_cloud_creds = f.read()
                    _log(f"STT: Google Cloud credentials from env ({cp})")
        except Exception as e:
            _log(f"STT: Google Cloud credentials unavailable: {e}")

        # Build initial phrase hints from static vocabulary
        self._phrase_hints = self._build_static_hints()

        # Configurable language tag
        self._language: str = acli_cfg.get("stt_language", "en-US")

        # Log STT availability at init so problems are obvious immediately
        if self._fw_model is not None:
            _log(f"STT: faster-whisper ready — model={self._fw_model_size} (priority 0)")
        elif self._has_whisper:
            _log(f"STT: whisper.cpp ready ({self.whisper_bin})")
        elif self._google_cloud_creds:
            _log("STT: using Google Cloud Speech-to-Text (high quality)")
        elif self._has_sr:
            _log("STT: using SpeechRecognition (Google) fallback — enhanced")
        else:
            _log("STT: ⚠ NO STT ENGINE AVAILABLE — install SpeechRecognition or configure whisper.cpp")

    @staticmethod
    def _build_static_hints() -> List[str]:
        """Build domain-specific phrase hints for the speech recogniser."""
        hints = [
            # Wake / exit phrases
            "hey radio", "thanks radio",
            # Navigation & actions
            "start", "stop", "play", "pause", "go back", "go home",
            "open settings", "list plugins", "new station",
            "switch to runtime", "switch to the game",
            "game context", "runtime context",
            # Game domain (FTB)
            "from the backmarker", "backmarker",
            "new game", "load game", "save game",
            "advance day", "advance the day",
            "next step", "wizard next", "wizard back", "confirm",
            "set tier", "set origin",
            "grassroots", "formula v", "formula x", "formula y", "formula z",
            "former driver", "grassroots hustler", "game show winner",
            "corporate spinout", "engineering savant",
            "permanent", "replayable",
            "watch live race", "instant sim",
            "show team", "show finance", "show dashboard",
            "show development", "show sponsors", "show calendar",
            "show career", "show stats", "show car", "show race",
            "hire", "fire", "buy parts", "sell parts", "equip part",
            "accept sponsor", "decline sponsor",
            "start R&D", "cancel R&D", "list R&D projects",
            "sell infrastructure", "apply for job",
            "resolve decision", "choose option",
            "pause race", "resume race", "race status",
            "list saves", "delete save",
            # Audio CLI meta
            "speaker mode", "headphone mode",
            "minimal", "concise", "standard", "broadcast", "diagnostic",
            "set verbosity", "audio keyboard",
            "mute", "unmute", "play audio", "stop audio",
            "show browser", "hide browser",
            "restart", "restart radio os",
        ]
        return hints

    def update_hints_from_state(self, ui_state: Dict[str, Any]) -> None:
        """Refresh phrase hints with live data from the current UI state.

        Called before each transcription so station names, plugin names,
        driver/team names, and decision options are all in the hint list.
        """
        dynamic: List[str] = list(self._build_static_hints())

        # Station names
        for st in ui_state.get("stations", []):
            name = st.get("name") or st.get("id", "")
            if name:
                dynamic.append(name.lower())

        # Plugin / feed names
        for p in ui_state.get("available_plugins", []):
            for key in ("display", "name"):
                v = p.get(key, "")
                if v:
                    dynamic.append(v.lower())
        for f in ui_state.get("station_feeds", []):
            for key in ("display", "name"):
                v = f.get(key, "")
                if v:
                    dynamic.append(v.lower())

        # Game-specific names (drivers, teams, decisions)
        gs = ui_state.get("game_state", {})
        if isinstance(gs, dict):
            pt = gs.get("player_team", {})
            if isinstance(pt, dict):
                tn = pt.get("name", "")
                if tn:
                    dynamic.append(tn.lower())
                for d in pt.get("drivers", []):
                    if isinstance(d, str):
                        dynamic.append(d.lower())
            # Decision option labels
            for dec in gs.get("pending_decisions", []):
                if isinstance(dec, dict):
                    for opt in dec.get("options", []):
                        if isinstance(opt, dict):
                            label = opt.get("label", "")
                            if label:
                                dynamic.append(label.lower())
            # Available actions
            for a in gs.get("available_actions", []):
                if isinstance(a, str):
                    dynamic.append(a.replace("_", " "))

            # Wizard fields
            ui_screen = gs.get("ui_screen", {})
            if isinstance(ui_screen, dict):
                for field in ui_screen.get("fields", []):
                    if isinstance(field, dict):
                        for opt in field.get("options", []):
                            if isinstance(opt, dict):
                                dynamic.append(opt.get("label", "").lower())
                            elif isinstance(opt, str):
                                dynamic.append(opt.lower())

        # Deduplicate, remove empties, cap at 500 (API limit)
        seen: set = set()
        unique: List[str] = []
        for h in dynamic:
            h = h.strip()
            if h and h not in seen:
                seen.add(h)
                unique.append(h)
        self._phrase_hints = unique[:500]

    def transcribe(self, audio_data: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
        """
        Transcribe audio numpy array to text.
        Audio should be float32, mono, 16kHz.

        Pre-processing pipeline (applied before sending to any STT engine):
        1. High-pass filter at 85 Hz to remove low-frequency rumble, HVAC
           noise, and mechanical vibration that confuse the recogniser.
        2. RMS normalization to a target level so Google's VAD and acoustic
           model receive consistent input regardless of mic gain.
        3. Gentle clipping guard to avoid digital overs after normalization.
        """
        if audio_data is None or len(audio_data) == 0:
            return ""

        # ── Audio pre-processing ──────────────────────────────────
        audio = audio_data.astype(np.float32, copy=True)

        # 1. High-pass filter (simple first-order IIR at ~85 Hz for 16 kHz SR)
        #    y[n] = alpha * (y[n-1] + x[n] - x[n-1])
        #    alpha = RC / (RC + dt),  RC = 1/(2*pi*85),  dt = 1/16000
        alpha = 0.9835  # pre-computed for 85 Hz @ 16 kHz
        filtered = np.empty_like(audio)
        filtered[0] = audio[0]
        for i in range(1, len(audio)):
            filtered[i] = alpha * (filtered[i - 1] + audio[i] - audio[i - 1])
        audio = filtered

        # 2. RMS normalization — target -20 dBFS (≈0.10 RMS)
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms > 1e-6:
            target_rms = 0.10
            gain = target_rms / rms
            # Cap gain so silence doesn't get boosted into noise
            gain = min(gain, 10.0)
            audio = audio * gain

        # 3. Clip guard
        audio = np.clip(audio, -1.0, 1.0)

        # Write to temporary WAV
        wav_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name

            # Ensure int16 for WAV
            pcm = (audio * 32767).astype(np.int16)

            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(pcm.tobytes())

            return self._transcribe_wav(wav_path)

        finally:
            if wav_path and os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception:
                    pass

    def _transcribe_wav(self, wav_path: str) -> str:
        """Transcribe a WAV file.

        Engine priority:
        1. whisper.cpp (local, fast, no network)
        2. Google Cloud Speech-to-Text (high quality, phrase hints, needs creds)
        3. Google free web API via SpeechRecognition (enhanced with phrase
           hints, language tag, and retry-on-transient-error)
        """
        # ── 0. faster-whisper (local, no network, best for Pi 5) ─
        if self._fw_model is not None:
            try:
                import numpy as _np
                import soundfile as _sf

                # Read the wav, convert to float32 mono at 16 kHz
                data, sr = _sf.read(wav_path, dtype="float32", always_2d=True)
                mono = data[:, 0]  # left channel
                if sr != 16000:
                    # Simple decimation via numpy if rate differs
                    import math as _math
                    factor = sr / 16000
                    new_len = int(len(mono) / factor)
                    mono = _np.interp(
                        _np.linspace(0, len(mono) - 1, new_len),
                        _np.arange(len(mono)),
                        mono,
                    ).astype(_np.float32)

                segs, _info = self._fw_model.transcribe(
                    mono, language="en", vad_filter=True,
                )
                text = " ".join(s.text.strip() for s in segs).strip()
                # faster-whisper ran successfully — trust its VAD result.
                # Return immediately (even empty) so we don't fall through
                # to network-based engines for ambient noise.
                return text
            except Exception as _e:
                _log(f"STT: faster-whisper transcribe error: {_e}")

        # ── 1. Try whisper.cpp ────────────────────────────────────
        if self._has_whisper:
            try:
                out_txt = wav_path + ".txt"
                result = subprocess.run(
                    [self.whisper_bin, "-m", self.whisper_model,
                     "-f", wav_path, "-otxt", "--no-timestamps"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                )
                if result.returncode == 0 and os.path.exists(out_txt):
                    with open(out_txt, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read().strip()
                    try:
                        os.remove(out_txt)
                    except Exception:
                        pass
                    if text:
                        return text
                else:
                    _log(f"STT: whisper.cpp returned code {result.returncode}")
            except Exception as e:
                _log(f"STT: whisper.cpp error: {e}")
        else:
            _log("STT: whisper.cpp not configured (WHISPER_CPP_BIN / WHISPER_CPP_MODEL)")

        # ── 2. Try Google Cloud Speech-to-Text ────────────────────
        if self._google_cloud_creds and self._has_sr:
            try:
                import speech_recognition as sr
                recognizer = sr.Recognizer()
                with sr.AudioFile(wav_path) as source:
                    audio = recognizer.record(source)
                text = str(recognizer.recognize_google_cloud(
                    audio,
                    credentials_json=self._google_cloud_creds,
                    language=self._language,
                    preferred_phrases=self._phrase_hints[:500] if self._phrase_hints else None,
                ) or "")
                if text:
                    return text
            except ImportError:
                pass
            except Exception as e:
                _log(f"STT: Google Cloud error ({e}), falling through to free API")

        # ── 3. Fallback: SpeechRecognition (Google free API) ──────
        if self._has_sr:
            return self._transcribe_google_free(wav_path)

        return ""

    def _transcribe_google_free(self, wav_path: str, max_retries: int = 2) -> str:
        """Enhanced Google free-tier recognition with retry and phrase hints.

        Improvements over the bare ``recognize_google(audio)`` call:
        - Explicit ``language="en-US"`` prevents locale mis-detection.
        - ``show_all=True`` lets us pick the best alternative and log
          confidence so we can diagnose marginal recognitions.
        - Retry with exponential backoff on transient HTTP/network errors.
        - ``pfilter=0`` disables the profanity filter which sometimes
          silently censors legitimate words.
        """
        import speech_recognition as sr

        recognizer = sr.Recognizer()

        # Tune recogniser energy thresholds so it doesn't clip short
        # utterances or include too much silence
        recognizer.energy_threshold = 300    # lower = more sensitive
        recognizer.dynamic_energy_threshold = False  # we already normalize

        with sr.AudioFile(wav_path) as source:
            audio = recognizer.record(source)

        last_err: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                # Use show_all=True to get alternatives + confidence scores
                raw = recognizer.recognize_google(
                    audio,
                    language=self._language,
                    show_all=True,
                    pfilter=0,
                )

                if not raw or not isinstance(raw, dict):
                    # Empty result — Google didn't recognise anything
                    return ""

                # Parse the best alternative
                alternatives = []
                for result in raw.get("results", []):
                    for alt in result.get("alternatives", []):
                        transcript = alt.get("transcript", "").strip()
                        confidence = alt.get("confidence", 0.0)
                        if transcript:
                            alternatives.append((transcript, confidence))

                # Legacy format: results may be at the top level
                if not alternatives:
                    for alt in raw.get("alternative", []):
                        transcript = alt.get("transcript", "").strip()
                        confidence = alt.get("confidence", 0.0)
                        if transcript:
                            alternatives.append((transcript, confidence))

                if not alternatives:
                    return ""

                # Sort by confidence descending, pick the best
                alternatives.sort(key=lambda x: x[1], reverse=True)
                best_text, best_conf = alternatives[0]

                # Log confidence for diagnostics
                if best_conf > 0:
                    _log(f"STT: Google confidence={best_conf:.2f} "
                         f"text='{best_text}' "
                         f"(+{len(alternatives)-1} alternatives)")
                else:
                    _log(f"STT: Google text='{best_text}' "
                         f"({len(alternatives)} alternatives, no confidence)")

                return best_text

            except sr.UnknownValueError:
                # Google couldn't understand — not a transient error
                _log("STT: Google could not understand audio")
                return ""
            except sr.RequestError as e:
                # Network / API error — retry
                last_err = e
                if attempt < max_retries:
                    wait = 0.5 * (2 ** attempt)
                    _log(f"STT: Google request error ({e}), retry {attempt+1}/{max_retries} in {wait:.1f}s")
                    time.sleep(wait)
                else:
                    _log(f"STT: Google request failed after {max_retries+1} attempts: {e}")
            except TypeError:
                # Very old SpeechRecognition versions — bare fallback
                try:
                    text = str(recognizer.recognize_google(audio) or "")
                    return text
                except Exception as e2:
                    _log(f"STT: legacy recognize_google error: {e2}")
                    return ""
            except Exception as e:
                _log(f"STT: SpeechRecognition unexpected error: {e}")
                last_err = e
                break

        return ""


# ---------------------------------------------------------------------------
# TTS Narration Output
# ---------------------------------------------------------------------------
class NarrationEngine:
    """
    Speaks narration text through voice_provider.
    Uses a dedicated voice (not the station character voices).

    Supports barge-in: if a MicStream is provided, the engine monitors
    mic energy while speaking and kills playback when the user talks.
    """

    def __init__(self, mic: Optional["MicStream"] = None,
                 on_speaking_change: Optional[callable] = None):
        self._lock = threading.Lock()
        self._speaking = False
        self._mic = mic                # optional — enables barge-in
        self._interrupted = False      # True if last speak() was cut short
        self._active_proc: Optional[subprocess.Popen] = None
        self._on_speaking_change = on_speaking_change  # callback(bool)
        # Audio output mode: "speaker" mutes mic + disables barge-in,
        # "headphone" keeps mic live and allows barge-in.
        self._audio_mode: str = "speaker"

    def set_audio_mode(self, mode: str) -> None:
        """Set audio output mode ('speaker' or 'headphone')."""
        self._audio_mode = mode
        _log(f"NarrationEngine audio mode → {mode}")

    @property
    def audio_mode(self) -> str:
        return self._audio_mode

    @property
    def _speaker_mode(self) -> bool:
        """True when on speakers — mic is muted during TTS, no barge-in."""
        return self._audio_mode == "speaker"

    def speak(self, text: str) -> None:
        """Synthesize and play narration. Blocking, but interruptible.

        In **speaker mode** the mic is muted during playback and barge-in
        is disabled to prevent self-interruption.
        In **headphone mode** the mic stays live and barge-in is enabled.
        """
        if not text or not text.strip():
            return

        with self._lock:
            self._speaking = True
            self._interrupted = False
            self._signal_speaking(True)
            # In speaker mode, mute mic to prevent TTS speaker bleed.
            # In headphone mode, keep mic live for barge-in.
            if self._mic and self._speaker_mode:
                self._mic.mute()
            try:
                self._speak_impl(text.strip())
            finally:
                if self._speaker_mode:
                    # Post-speech cooldown: let room reverb / speaker ring-out
                    # decay fully before we start listening again.
                    # 0.35 s is enough for laptop speakers; external speakers
                    # with more bass may need the settle_after_speak logic in
                    # _capture_until_silence to compensate.
                    if self._mic and not self._interrupted:
                        time.sleep(0.35)
                    # Drain stale audio and un-mute
                    if self._mic:
                        self._mic.drain()
                        self._mic.unmute()
                        _log("Speaker-mode: drained + unmuted mic after speak.")
                self._speaking = False
                self._active_proc = None
                self._signal_speaking(False)

    def _signal_speaking(self, speaking: bool) -> None:
        """Notify the session that narration speaking state changed."""
        if self._on_speaking_change:
            try:
                self._on_speaking_change(speaking)
            except Exception:
                pass

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    @property
    def was_interrupted(self) -> bool:
        """True if the most recent speak() was cut short by barge-in."""
        return self._interrupted

    # -------------------------------------------------------------------
    # Barge-in monitor (polls mic while a subprocess is playing)
    # -------------------------------------------------------------------
    def _wait_or_interrupt(self, proc: subprocess.Popen) -> None:
        """
        Wait for *proc* to finish, optionally killing it early on barge-in.

        In **speaker mode** barge-in is disabled entirely — we just wait
        for the process to finish.
        In **headphone mode** we poll the mic for sustained loud speech
        and terminate the TTS process if the user talks over it.
        """
        self._active_proc = proc

        # Speaker mode: no barge-in, just wait
        if self._speaker_mode:
            proc.wait()
            return

        # ── Headphone mode: barge-in enabled ──

        # Grace period (first ~0.4 s) — ignore initial transients
        grace_deadline = time.time() + 0.4
        while proc.poll() is None and time.time() < grace_deadline:
            time.sleep(0.15)

        if proc.poll() is not None:
            proc.wait()
            return

        # Monitor mic for user speech
        consecutive_hits = 0
        hits_needed = 2              # ~300 ms of sustained speech

        while proc.poll() is None:
            time.sleep(0.15)
            if not (self._mic and self._mic.is_open):
                continue

            rms = self._mic.current_rms(window_sec=0.15)
            barge_in_threshold = SILENCE_THRESHOLD * 2.5

            if rms >= barge_in_threshold:
                consecutive_hits += 1
                if consecutive_hits >= hits_needed:
                    _log(f"Barge-in detected (rms={rms:.4f}, "
                         f"threshold={barge_in_threshold:.4f}), stopping narration.")
                    proc.terminate()
                    try:
                        proc.wait(timeout=1)
                    except Exception:
                        proc.kill()
                    self._interrupted = True
                    return
            else:
                consecutive_hits = 0

        # Process finished naturally
        proc.wait()

    def _speak_impl(self, text: str) -> None:
        """
        Attempt TTS via available providers.
        All subprocess-based providers use Popen + _wait_or_interrupt
        so the user can barge in mid-sentence.
        """
        # Try platform-native TTS first (simple, no config needed)
        if sys.platform == "darwin":
            try:
                proc = subprocess.Popen(
                    ["say", "-r", "190", text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._wait_or_interrupt(proc)
                return
            except Exception:
                pass

        # Try espeak on Linux
        if sys.platform.startswith("linux"):
            try:
                proc = subprocess.Popen(
                    ["espeak", "-s", "170", "--stdout", text],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                paplay = subprocess.Popen(
                    ["paplay", "--raw", "--rate=22050", "--channels=1",
                     "--format=s16le"],
                    stdin=proc.stdout,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                proc.stdout.close()
                self._active_proc = paplay
                self._wait_or_interrupt(paplay)
                proc.wait(timeout=2)
                return
            except Exception:
                # Fall back to direct espeak (no PulseAudio routing)
                try:
                    proc = subprocess.Popen(
                        ["espeak", "-s", "170", text],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    self._wait_or_interrupt(proc)
                    return
                except Exception:
                    pass

        # Try voice_provider if available
        try:
            from voice_provider import get_voice_provider
            # Build minimal config for narration voice
            audio_cfg = self._get_audio_config()
            if audio_cfg:
                cfg = {"audio": audio_cfg}
                provider = get_voice_provider(cfg, audio_cfg)
                data, sr = provider.synthesize("narrator", text, {"narrator": "default"})
                if data is not None and len(data) > 0 and HAS_SD:
                    if data.ndim == 1:
                        data = data.reshape(-1, 1)
                    # Route through PulseAudio/PipeWire so pactl sink
                    # selection controls which speaker plays the audio.
                    _pulse_dev = None
                    try:
                        import sounddevice as _sd2
                        for _i, _d in enumerate(_sd2.query_devices()):
                            if str(_d.get("name", "")).lower().startswith("pulse") and _d.get("max_output_channels", 0) > 0:
                                _pulse_dev = _i
                                break
                    except Exception:
                        pass
                    sd.play(data, sr, device=_pulse_dev)
                    if self._speaker_mode:
                        # Speaker mode: just wait for playback, no barge-in
                        sd.wait()
                    else:
                        # Headphone mode: poll for barge-in
                        grace_end = time.time() + 0.4
                        consecutive = 0
                        while sd.get_stream().active:
                            time.sleep(0.15)
                            if time.time() < grace_end:
                                continue
                            if self._mic and self._mic.is_open:
                                rms = self._mic.current_rms(window_sec=0.15)
                                if rms >= SILENCE_THRESHOLD * 2.5:
                                    consecutive += 1
                                    if consecutive >= 2:
                                        _log(f"Barge-in detected (rms={rms:.4f}), "
                                             f"stopping narration.")
                                        sd.stop()
                                        self._interrupted = True
                                        return
                                else:
                                    consecutive = 0
                    return
        except Exception:
            pass

        # Last resort: print to console
        _log(f"[narration] {text}")

    def _get_audio_config(self) -> Dict[str, Any]:
        """Try to load audio config from global config."""
        try:
            cfg_path = self._global_config_path()
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                voices = data.get("default_voices", {})
                if voices:
                    return {
                        "voices_provider": voices.get("provider", "piper"),
                        "piper_bin": voices.get("piper_bin", ""),
                    }
        except Exception:
            pass
        return {}

    def _global_config_path(self) -> str:
        if os.name == "nt":
            appdata = os.getenv("APPDATA", os.path.expanduser("~"))
            return os.path.join(appdata, "RadioOS", "config.json")
        return os.path.expanduser("~/.radioOS/config.json")


# ---------------------------------------------------------------------------
# Local Audio Player — plays station audio locally in web/headless mode
# ---------------------------------------------------------------------------
class LocalAudioPlayer:
    """
    Connects to the web server's /ws/audio/{station_id} WebSocket and plays
    WAV segments through the local speakers via sounddevice.  This lets the
    user hear station audio even without a browser open.

    Runs a background thread; start/stop are idempotent.
    """

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._station_id: Optional[str] = None
        self._base_url: Optional[str] = None
        self._volume = 1.0
        self.muted = False

    @property
    def is_playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def station_id(self) -> Optional[str]:
        return self._station_id

    def start(self, base_url: str, station_id: str) -> str:
        """Start playing audio from a station. Returns narration string."""
        if not HAS_SD:
            return "Cannot play audio locally — sounddevice is not installed."
        if self.is_playing:
            if self._station_id == station_id:
                return f"Already playing audio from {station_id}."
            self.stop()

        self._base_url = base_url.rstrip("/")
        self._station_id = station_id
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._playback_loop,
            name="AudioCLI-LocalPlayer",
            daemon=True,
        )
        self._thread.start()
        _log(f"Local audio player started for {station_id}")
        return f"Now playing station audio locally for {station_id}."

    def stop(self) -> str:
        """Stop playback. Returns narration string."""
        if not self.is_playing:
            return "Local audio player is not running."
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        sid = self._station_id
        self._station_id = None
        _log(f"Local audio player stopped for {sid}")
        return "Local audio playback stopped."

    def _playback_loop(self) -> None:
        """Background thread: poll /ws/audio/{station_id} and play WAV.

        Auto-reconnects on disconnect with exponential back-off so headless
        stations stay connected indefinitely rather than dying after 10-15
        segments.
        """
        MAX_BACKOFF = 30          # seconds
        backoff = 1.0
        attempts = 0

        while not self._stop_event.is_set():
            try:
                self._playback_via_websocket()
            except Exception as e:
                if self._stop_event.is_set():
                    break
                attempts += 1
                _log(f"WebSocket audio disconnected ({e}), reconnect attempt "
                     f"{attempts} in {backoff:.1f}s")
                self._stop_event.wait(timeout=backoff)
                backoff = min(backoff * 1.5, MAX_BACKOFF)
                if self._stop_event.is_set():
                    break
                continue

            # If _playback_via_websocket returned normally (clean exit inside
            # the loop, e.g. server closed connection), reconnect immediately.
            if not self._stop_event.is_set():
                attempts += 1
                _log(f"WebSocket audio stream ended, reconnecting (attempt {attempts})…")
                self._stop_event.wait(timeout=min(backoff, 2.0))
                backoff = min(backoff * 1.2, MAX_BACKOFF)
            else:
                break

        # Final fallback: if WebSocket never worked, try file polling
        if not self._stop_event.is_set():
            _log("All WebSocket attempts exhausted, falling back to file polling")
            self._playback_via_file_poll()

    def _playback_via_websocket(self) -> None:
        """Connect to /ws/audio/{station_id} and play WAV segments.

        Raises on connection failure so the caller can reconnect.
        Returns normally if the server closes the connection cleanly.
        """
        try:
            import websockets
            import asyncio
        except ImportError:
            raise RuntimeError("websockets not installed")

        ws_url = self._base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/ws/audio/{self._station_id}"

        consecutive_timeouts = 0
        MAX_CONSECUTIVE_TIMEOUTS = 120  # ~2 minutes of silence before ping-fail

        async def _ws_loop():
            nonlocal consecutive_timeouts
            async with websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            ) as ws:
                _log(f"Local audio connected via WebSocket → {ws_url}")
                consecutive_timeouts = 0
                while not self._stop_event.is_set():
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        consecutive_timeouts = 0
                    except asyncio.TimeoutError:
                        consecutive_timeouts += 1
                        # Send keepalive
                        try:
                            await ws.ping()
                        except Exception:
                            _log("WebSocket keepalive ping failed — disconnecting")
                            break
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        _log("WebSocket connection closed by server")
                        break
                    except Exception as e:
                        _log(f"WebSocket recv error: {e}")
                        break

                    if isinstance(msg, bytes) and len(msg) > 4:
                        self._play_ws_payload(msg)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_ws_loop())
        finally:
            loop.close()

    def _play_ws_payload(self, payload: bytes) -> None:
        """Decode a WebSocket audio payload and play it through speakers."""
        try:
            import struct as _struct
            meta_len = _struct.unpack(">I", payload[:4])[0]
            # meta_json = payload[4:4+meta_len]  # available if needed
            wav_bytes = payload[4 + meta_len:]
            self._play_wav_bytes(wav_bytes)
        except Exception as e:
            _log(f"Local audio decode error: {e}")

    def _playback_via_file_poll(self) -> None:
        """Fallback: poll .audio_pipe/ directory directly."""
        import glob
        audio_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "stations", self._station_id, ".audio_pipe"
        )

        while not self._stop_event.is_set():
            if not os.path.isdir(audio_dir):
                time.sleep(1)
                continue

            wav_files = sorted(glob.glob(os.path.join(audio_dir, "*.wav")))
            for wav_path in wav_files:
                if self._stop_event.is_set():
                    break
                # Skip files still being written (< 200ms old)
                try:
                    if time.time() - os.path.getmtime(wav_path) < 0.3:
                        continue
                except Exception:
                    continue

                try:
                    with open(wav_path, "rb") as f:
                        wav_bytes = f.read()
                    if len(wav_bytes) > 44:
                        self._play_wav_bytes(wav_bytes)
                    # Clean up
                    os.remove(wav_path)
                    meta_path = wav_path + ".json"
                    if os.path.exists(meta_path):
                        os.remove(meta_path)
                except Exception as e:
                    _log(f"File poll playback error: {e}")

            time.sleep(0.5)

    def _play_wav_bytes(self, wav_data: bytes) -> None:
        """Decode WAV bytes and play through sounddevice."""
        if not HAS_SD:
            return
        if self.muted:
            return
        try:
            bio = io.BytesIO(wav_data)
            with wave.open(bio, "rb") as wf:
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                rate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())

            # Convert to numpy float32
            if sampwidth == 2:
                dtype = np.int16
            elif sampwidth == 4:
                dtype = np.int32
            else:
                dtype = np.int16

            audio = np.frombuffer(frames, dtype=dtype).astype(np.float32)
            if dtype == np.int16:
                audio /= 32768.0
            elif dtype == np.int32:
                audio /= 2147483648.0

            audio *= self._volume

            # Apply ducking when Audio CLI narration is speaking
            duck_vol = self._read_duck_volume()
            if duck_vol < 1.0:
                audio *= duck_vol

            if n_channels > 1:
                audio = audio.reshape(-1, n_channels)

            sd.play(audio, samplerate=rate)
            sd.wait()
        except Exception as e:
            _log(f"Local audio play error: {e}")

    @staticmethod
    def _read_duck_volume() -> float:
        """Read the ducking flag and return the volume multiplier.

        Ducking only applies while the Audio CLI is actively speaking.
        Between utterances (session active but not speaking) station audio
        plays at full volume so the user doesn't sit in a quiet-ducked
        station the whole session.
        """
        try:
            flag_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                ".audio_cli_suppress"
            )
            if not os.path.exists(flag_path):
                return 1.0
            with open(flag_path, "r") as f:
                data = json.load(f)
            if not data.get("active", False):
                return 1.0
            if data.get("speaking", False):
                return float(data.get("duck_volume", 0.20))
            # Session active but not speaking — full volume
            return 1.0
        except Exception:
            return 1.0


# Singleton
_local_audio_player = LocalAudioPlayer()


# ---------------------------------------------------------------------------
# LLM Command Parser
# ---------------------------------------------------------------------------
class CommandParser:
    """
    Sends user transcript + UI state to LLM, gets back structured JSON commands.
    Uses model_provider infrastructure.
    """

    def __init__(self):
        self._provider = None
        self._model = None

    def _ensure_provider(self):
        """Lazy-init LLM provider from global config."""
        if self._provider is not None:
            return

        try:
            # Ensure env vars from /etc/environment are loaded — the systemd
            # service may not inherit them even with EnvironmentFile.
            _load_system_env()

            from model_provider import get_llm_provider, _resolve_default_model

            # Load config
            cfg_path = self._global_config_path()
            cfg = {}
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)

            # Audio CLI can have its own LLM override in cfg["audio_cli"]["llm"]
            # If not set (or provider is "default"), fall back to global default_models
            acli_llm = cfg.get("audio_cli", {}).get("llm", {})
            acli_provider = (acli_llm.get("provider") or "").strip().lower()

            if acli_provider and acli_provider != "default":
                # Use Audio CLI-specific LLM settings
                llm_cfg = {**cfg.get("default_models", {}), **acli_llm}
                provider_type = acli_provider
                _log(f"Using Audio CLI LLM override: provider={provider_type}")
            else:
                # Fall back to global default_models
                llm_cfg = cfg.get("default_models", {})
                provider_type = llm_cfg.get("provider", "ollama").strip().lower()

            llm_section = {"provider": provider_type}

            if provider_type == "ollama":
                # Config may use "endpoint" or "llm_endpoint"
                endpoint = (llm_cfg.get("endpoint") or llm_cfg.get("llm_endpoint")
                            or "http://127.0.0.1:11434/api/generate")
                llm_section["endpoint"] = endpoint
            elif provider_type == "openai":
                # Set env var if we have the key in config
                api_key = llm_cfg.get("openai_api_key", "").strip()
                if api_key:
                    os.environ.setdefault("OPENAI_API_KEY", api_key)
                llm_section["api_key_env"] = "OPENAI_API_KEY"
            elif provider_type == "anthropic":
                api_key = llm_cfg.get("anthropic_api_key", "").strip()
                if api_key:
                    os.environ.setdefault("ANTHROPIC_API_KEY", api_key)
                llm_section["api_key_env"] = "ANTHROPIC_API_KEY"
            elif provider_type == "google":
                api_key = llm_cfg.get("google_api_key", "").strip()
                if api_key:
                    os.environ.setdefault("GOOGLE_API_KEY", api_key)
                llm_section["api_key_env"] = "GOOGLE_API_KEY"

            self._provider = get_llm_provider({"llm": llm_section})
            self._model = (llm_cfg.get("model", "") or llm_cfg.get("host_model", "")
                           or llm_cfg.get("producer_model", "") or "llama3.1:8b")
            _log(f"LLM provider ready: {provider_type} model={self._model}")

        except Exception as e:
            _log(f"LLM provider init failed: {type(e).__name__}: {e}")
            self._provider = None

    @staticmethod
    def _compact_ui_state(ui_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Produce a compact copy of the UI state that preserves ALL stations
        and plugins but strips verbose per-item detail so the JSON stays
        small enough for the LLM context window.
        """
        compact = {}
        for k, v in ui_state.items():
            if k == "stations":
                # Keep every station but only the essential fields
                compact_stations = []
                for st in v:
                    cs: Dict[str, Any] = {
                        "index": st.get("index"),
                        "id": st.get("id"),
                        "name": st.get("name"),
                        "selected": st.get("selected", False),
                    }
                    if st.get("category"):
                        cs["category"] = st["category"]
                    if st.get("running"):
                        cs["running"] = True
                    if st.get("feed_count"):
                        cs["feeds"] = st["feed_count"]
                    if st.get("character_count"):
                        cs["voices"] = st["character_count"]
                    compact_stations.append(cs)
                compact["stations"] = compact_stations
                compact["station_count"] = len(compact_stations)
            elif k == "elements":
                # Trim to just labels
                compact["elements"] = [
                    {"label": e.get("label"), "target": e.get("target")}
                    for e in v if isinstance(e, dict)
                ][:10]
            elif k == "available_plugins":
                # Just names
                compact["available_plugins"] = [
                    {"name": p.get("name"), "display": p.get("display")}
                    for p in v if isinstance(p, dict)
                ]
            elif k == "station_feeds":
                # Keep name + enabled only
                compact["station_feeds"] = [
                    {"name": f.get("name"), "enabled": f.get("enabled")}
                    for f in v if isinstance(f, dict)
                ]
            elif k == "runtime_status":
                # Cap long runtime text
                compact[k] = v[:800] if isinstance(v, str) else v
            elif k == "runtime_log_tail":
                # Drop log tail when game state is present — LLM doesn't need raw logs
                if "game_state" not in ui_state:
                    compact[k] = v[:600] if isinstance(v, str) else v
            elif k == "game_state" and isinstance(v, dict):
                # Already compact from _get_plugin_game_state, pass through
                compact[k] = v
            else:
                compact[k] = v
        return compact

    def parse(self, transcript: str, ui_state: Dict[str, Any],
              persona_prompt_overlay: str = "") -> CLIResponse:
        """
        Send user transcript + UI state to LLM, return structured response.

        Args:
            transcript: User's spoken text.
            ui_state:   Current UI/game state dict.
            persona_prompt_overlay: Optional system prompt addendum from the
                active AudioPersona.  Appended to SYSTEM_PROMPT so the LLM
                adopts the persona's voice while keeping the structural
                command format intact.
        """
        self._ensure_provider()

        if not self._provider:
            return CLIResponse(narration="Voice command system is not configured. Check model settings.")

        # Build the user prompt — compact the state intelligently so every
        # station and plugin survives instead of being lost to raw truncation
        compact_state = self._compact_ui_state(ui_state)
        state_json = json.dumps(compact_state, indent=2, default=str)
        # Safety cap — raised to accommodate rich game state (roster, car,
        # parts, infra, R&D, contracts, sponsors, free agents, etc.)
        if len(state_json) > 16000:
            state_json = state_json[:16000] + "\n... (truncated)"
        user_prompt = (
            f"CURRENT UI STATE:\n{state_json}\n\n"
            f"USER SAID: \"{transcript}\"\n\n"
            f"Respond with a single JSON object following the OUTPUT FORMAT specification."
        )

        # Scale max output tokens with verbosity to save cost at lower levels.
        # The JSON structure + actions overhead is ~100-150 tokens; the rest
        # is narration, which should be short at minimal/concise.
        verbosity = ui_state.get("verbosity", DEFAULT_VERBOSITY)
        _token_budget = {
            "minimal":    200,
            "concise":    300,
            "standard":   500,
            "broadcast":  800,
            "diagnostic": 400,
        }.get(verbosity, 400)

        try:
            # Compose system prompt: core + persona overlay (if any)
            effective_system_prompt = SYSTEM_PROMPT
            if persona_prompt_overlay:
                effective_system_prompt += (
                    "\n\n"
                    "# ── PERSONA OVERLAY ──\n"
                    "The following personality instructions augment your voice and "
                    "narration style.  You MUST still output valid JSON in the exact "
                    "OUTPUT FORMAT above.  The persona shapes HOW you narrate, not "
                    "WHAT actions are valid.\n\n"
                    f"{persona_prompt_overlay}"
                )

            raw = self._provider.generate(
                model=self._model,
                prompt=user_prompt,
                system=effective_system_prompt,
                num_predict=_token_budget,
                temperature=0.1,
                timeout=30,
                force_json=True,
            )
            _log(f"LLM raw response length: {len(raw)}")
            return CLIResponse.from_json(raw)
        except Exception as e:
            _log(f"LLM call failed: {type(e).__name__}: {e}")
            # Give the user actionable info about what went wrong
            err_name = type(e).__name__
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                hint = "Model timed out. Check that your LLM provider is running and responsive."
            elif "connection" in str(e).lower() or "refused" in str(e).lower():
                hint = f"Cannot connect to model provider. Check that Ollama or your configured LLM is running."
            elif "api" in str(e).lower() or "key" in str(e).lower() or "401" in str(e) or "403" in str(e):
                hint = "API authentication failed. Check your API key in Settings."
            else:
                hint = f"Model error: {err_name}. Check your model configuration in Settings."
            return CLIResponse(narration=hint)

    def _global_config_path(self) -> str:
        if os.name == "nt":
            appdata = os.getenv("APPDATA", os.path.expanduser("~"))
            return os.path.join(appdata, "RadioOS", "config.json")
        return os.path.expanduser("~/.radioOS/config.json")


# ---------------------------------------------------------------------------
# Command Dispatcher
# ---------------------------------------------------------------------------
class CommandDispatcher:
    """
    Executes structured CLIAction commands against the shell.
    All tkinter calls are dispatched via root.after() for thread safety.
    """

    def __init__(self, shell):
        """
        Args:
            shell: RadioShell instance
        """
        self.shell = shell
        self._action_map = {
            "navigate": self._navigate,
            "click": self._click,
            "start": self._start,
            "stop": self._stop,
            "open": self._open,
            "close": self._close,
            "back": self._back,
            "select": self._select,
            "input": self._input,
            "show_browser": self._show_browser,
            "hide_browser": self._hide_browser,
            "play_audio": self._play_audio,
            "stop_audio": self._stop_audio,
            "mute_audio": self._mute_audio,
            "list_plugins": self._list_plugins,
            "toggle_feed": self._toggle_feed,
            "configure_feed": self._configure_feed,
            "plugin_command": self._plugin_command,
            "open_plugin_ui": self._open_plugin_ui,
            "restart_app": self._restart_app,
            "audio_keyboard": self._audio_keyboard,
            "set_puck_volume": self._set_puck_volume,
            "set_group_volume": self._set_group_volume,
            "mute_puck": self._mute_puck,
            "route_puck": self._route_puck,
            "test_puck_tone": self._test_puck_tone,
        }

    def execute(self, actions: List[CLIAction]) -> List[str]:
        """Execute a list of actions with chaining support."""
        return _execute_chained(actions, self._action_map, label="RuntimeDispatcher")

    def _navigate(self, action: CLIAction) -> str:
        target = (action.target or "").lower()
        if target in ("home", "station_browser", "browser"):
            self._tk_call(self.shell.show_home)
            return "Navigated to Station Browser."
        elif target in ("runtime", "station_runtime"):
            self._tk_call(self.shell.show_runtime)
            return "Navigated to Station Runtime."
        elif target == "settings":
            self._tk_call(self.shell.open_settings)
            return "Opened Settings."
        return f"Unknown navigation target: {target}"

    def _click(self, action: CLIAction) -> str:
        target = (action.target or "").lower()

        if target in ("new_station", "new"):
            self._tk_call(self.shell.create_station_wizard)
            return "Opened New Station wizard."
        elif target in ("settings",):
            self._tk_call(self.shell.open_settings)
            return "Opened Settings."
        elif target in ("web_server", "server", "launch_server"):
            self._tk_call(self.shell.toggle_web_server)
            return "Toggled web server."

        # Try to find a station by name if a specific target was given
        station = None
        if target:
            station = self._find_station(target)

        # Fallback: use the currently selected station
        if not station:
            try:
                idx = self.shell.selected_idx
                if 0 <= idx < len(self.shell.stations):
                    station = self.shell.stations[idx]
            except Exception:
                pass

        if station:
            name = (station.manifest.get("station", {}) or {}).get("name", station.station_id)
            self._tk_call(lambda: self.shell.launch_station(station))
            return f"Launching station: {name}."

        if target:
            return f"Unknown click target: {target}"
        return "Nothing is selected to click. Select a station first."

    def _start(self, action: CLIAction) -> str:
        target = (action.target or "").lower()
        # Try to find station by name or ID
        station = self._find_station(target) if target else None

        # Fallback: use the currently selected station when target is empty,
        # vague, or didn't match any station by name
        if not station:
            try:
                idx = self.shell.selected_idx
                if 0 <= idx < len(self.shell.stations):
                    station = self.shell.stations[idx]
            except Exception:
                pass

        if station:
            self._tk_call(lambda: self.shell.launch_station(station))
            name = (station.manifest.get("station", {}) or {}).get("name", station.station_id)
            return f"Starting station: {name}."
        return f"Station not found: {target or 'none selected'}"

    def _stop(self, action: CLIAction) -> str:
        self._tk_call(self.shell.stop_station)
        return "Station stopped."

    def _open(self, action: CLIAction) -> str:
        return self._click(action)  # Alias

    def _close(self, action: CLIAction) -> str:
        return self._back(action)  # Alias

    def _back(self, action: CLIAction) -> str:
        self._tk_call(self.shell.stop_station)
        return "Returned to Station Browser."

    def _select(self, action: CLIAction) -> str:
        target = (action.target or "").lower()
        if not target:
            return "No station specified to select."
        # Select station by name or index
        try:
            idx = int(target)
            if 0 <= idx < len(self.shell.stations):
                self.shell.selected_idx = idx
                return f"Selected station at index {idx}."
        except ValueError:
            pass

        # By name
        for i, st in enumerate(self.shell.stations):
            name = (st.manifest.get("station", {}) or {}).get("name", st.station_id)
            if target in name.lower() or target in st.station_id.lower():
                self.shell.selected_idx = i
                return f"Selected station: {name}."

        return f"Station not found: {target}"

    def _input(self, action: CLIAction) -> str:
        """Submit text to a UI field.

        Tries the running station's plugin web server first (for game/wizard
        fields), then falls back to other mechanisms as they're added.
        This is the generic backend for audio-keyboard "enter" submissions.
        """
        field = (action.target or "").strip()
        text = action.params.get("text", "").strip()
        if not field:
            return "No field specified for input."
        if not text:
            return f"No text provided for field '{field}'."

        # Try to find a running station with a plugin web server
        station = self._get_active_station()
        web_port = None
        if station and self.shell.proc and self.shell.proc.is_alive():
            try:
                status_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "stations", station.station_id, "status.json")
                if os.path.exists(status_path):
                    with open(status_path, "r") as f:
                        status_data = json.load(f)
                    web_port = status_data.get("web_port")
            except Exception:
                pass
            if not web_port:
                web_port = 7555  # default FTB port

        if web_port:
            try:
                import urllib.request
                url = f"http://127.0.0.1:{web_port}/api/input_field"
                body = json.dumps({"field": field, "value": text}).encode("utf-8")
                req = urllib.request.Request(
                    url, data=body,
                    headers={"Content-Type": "application/json",
                              "Accept": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                if result.get("status") == "ok":
                    return f"Set {field} to '{text}'."
                return f"Server rejected input: {result.get('error', 'unknown')}"
            except Exception as e:
                _log(f"Input submit to plugin failed: {e}")
                return f"Failed to submit text for {field}: {e}"

        return f"No active plugin server to receive input for field '{field}'."

    def _restart_app(self, action: CLIAction) -> str:
        """Restart the entire Radio OS application."""
        import subprocess
        # Stop any running station first
        try:
            self._tk_call(self.shell.stop_station)
            time.sleep(0.5)
        except Exception:
            pass
        # Schedule the restart — we need to let the narration finish first
        script_path = sys.argv[0]
        def _do_restart():
            try:
                self.shell.root.quit()
                self.shell.root.destroy()
            except Exception:
                pass
            subprocess.Popen([sys.executable, script_path])
            sys.exit(0)
        # Delay restart so narration can play
        threading.Timer(2.0, _do_restart).start()
        return "Restarting Radio OS."

    def _audio_keyboard(self, action: CLIAction) -> str:
        """Activate the audio keyboard for text input. Handled at session level."""
        target = (action.target or "").strip() or "text_field"
        # Return a special marker that the session layer intercepts
        return f"__AUDIO_KEYBOARD_ACTIVATE__:{target}"

    def _show_browser(self, action: CLIAction) -> str:
        """Open the web UI in the system's default browser at the current view."""
        # Determine the web server URL from the shell
        url = getattr(self.shell, "_web_server_url", None)
        if not url:
            from web_server import WEB_SHELL_PORT
            cfg = {}
            try:
                from shell_bookmark import get_global_config
                cfg = get_global_config()
            except Exception:
                pass
            port = int(cfg.get("general", {}).get("web_server_port", WEB_SHELL_PORT))
            url = f"http://127.0.0.1:{port}"
        # Check web server is running
        ws_thread = getattr(self.shell, "_web_server_thread", None)
        if not ws_thread or not ws_thread.is_alive():
            return "Web server is not running. Start it first with the Launch Server button."
        # Build URL matching the current Audio CLI view
        view = getattr(self.shell, "_view", "home")
        if view == "runtime":
            try:
                sid = self.shell.proc.station.station_id
                url = f"{url}/runtime/{sid}"
            except Exception:
                pass
        return _browser_ctl.show(url)

    def _hide_browser(self, action: CLIAction) -> str:
        """Close / hide the browser window."""
        return _browser_ctl.hide()

    def _play_audio(self, action: CLIAction) -> str:
        """Start or resume local audio playback."""
        if _local_audio_player.is_playing:
            return "Local audio is already playing."
        # Try to find the running station's base_url and station_id
        base_url = getattr(self, "base_url", None)
        if not base_url:
            cfg = _load_audio_cli_config()
            base_url = cfg.get("web_url", "http://127.0.0.1:7800")
        for st in self.shell.stations:
            proc = self.shell.station_procs.get(st.station_id)
            if proc and proc.running:
                _local_audio_player.start(base_url, st.station_id)
                return "Local audio playback started."
        return "No station is currently running."

    def _stop_audio(self, action: CLIAction) -> str:
        """Stop local audio playback."""
        if not _local_audio_player.is_playing:
            return "Local audio is not playing."
        _local_audio_player.stop()
        return "Local audio playback stopped."

    def _mute_audio(self, action: CLIAction) -> str:
        """Toggle mute on local audio playback."""
        _local_audio_player.muted = not _local_audio_player.muted
        status = "muted" if _local_audio_player.muted else "unmuted"
        return f"Local audio {status}."

    # -- Puck (ESP32 wireless node) control ----------------------------------

    def _puck_api(self, method: str, path: str, body: dict | None = None) -> dict:
        """POST or GET to the local web server puck API."""
        import urllib.request, urllib.error
        port = getattr(self.shell, "_web_port", 7800)
        url = f"http://127.0.0.1:{port}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return json.loads(r.read())
        except Exception as e:
            return {"error": str(e)}

    def _set_puck_volume(self, action: CLIAction) -> str:
        node_id = action.target or "all"
        volume = int((action.params or {}).get("volume", 80))
        if node_id == "all":
            self._puck_api("POST", "/api/pucks/group_volume", {"volume": volume})
            return f"All pucks set to volume {volume}."
        result = self._puck_api("POST", f"/api/pucks/{node_id}/volume", {"volume": volume})
        if result.get("error"):
            return f"Puck {node_id} volume error: {result['error']}"
        return f"Puck {node_id} volume set to {volume}."

    def _set_group_volume(self, action: CLIAction) -> str:
        volume = int((action.params or {}).get("volume", 80))
        self._puck_api("POST", "/api/pucks/group_volume", {"volume": volume})
        return f"All pucks set to volume {volume}."

    def _mute_puck(self, action: CLIAction) -> str:
        node_id = action.target or "all"
        muted = bool((action.params or {}).get("muted", True))
        status = "muted" if muted else "unmuted"
        if node_id == "all":
            self._puck_api("POST", "/api/pucks/mute_all", {"muted": muted})
            return f"All pucks {status}."
        result = self._puck_api("POST", f"/api/pucks/{node_id}/mute", {"muted": muted})
        if result.get("error"):
            return f"Puck {node_id} mute error: {result['error']}"
        return f"Puck {node_id} {status}."

    def _route_puck(self, action: CLIAction) -> str:
        node_id = action.target or "all"
        route = str((action.params or {}).get("route", "all"))
        if node_id == "all":
            # route all pucks
            try:
                import urllib.request, json as _json
                port = getattr(self.shell, "_web_port", 7800)
                resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/pucks", timeout=3)
                pucks = _json.loads(resp.read())
                for p in pucks:
                    self._puck_api("POST", f"/api/pucks/{p['node_id']}/route", {"route": route})
            except Exception:
                pass
            return f"All pucks routed to '{route}'."
        result = self._puck_api("POST", f"/api/pucks/{node_id}/route", {"route": route})
        if result.get("error"):
            return f"Puck {node_id} route error: {result['error']}"
        return f"Puck {node_id} routed to '{route}'."

    def _test_puck_tone(self, action: CLIAction) -> str:
        node_id = action.target or "1"
        result = self._puck_api("POST", f"/api/pucks/{node_id}/test_tone")
        if result.get("error"):
            return f"Test tone error on puck {node_id}: {result['error']}"
        return f"Test tone sent to puck {node_id}."

    # -- Plugin / feed control (tkinter mode) --------------------------------

    def _get_active_station(self):
        """Return the currently active/running station or the selected one."""
        try:
            if self.shell.proc and self.shell.proc.station and self.shell.proc.is_alive():
                return self.shell.proc.station
        except Exception:
            pass
        try:
            idx = self.shell.selected_idx
            if 0 <= idx < len(self.shell.stations):
                return self.shell.stations[idx]
        except Exception:
            pass
        return None

    def _list_plugins(self, action: CLIAction) -> str:
        """List all available plugins and their status for the active station."""
        from shell_bookmark import discover_plugins
        plugins = discover_plugins()
        if not plugins:
            return "No plugins found in the plugins directory."

        station = self._get_active_station()
        feeds_cfg = {}
        station_name = "no station selected"
        if station:
            station_name = (station.manifest.get("station", {}) or {}).get("name", station.station_id)
            feeds_cfg = station.manifest.get("feeds", {}) or {}

        lines = [f"Plugins for {station_name}:"]
        enabled_count = 0
        for name, info in plugins.items():
            if not info.get("is_feed", True):
                continue
            display = info.get("display", name)
            desc = info.get("desc", "")
            feed_cfg = feeds_cfg.get(name, {})
            is_enabled = bool(feed_cfg.get("enabled", False)) if isinstance(feed_cfg, dict) else False
            status = "enabled" if is_enabled else "disabled"
            if is_enabled:
                enabled_count += 1
            entry = f"  {display} ({name}): {status}"
            if desc:
                entry += f" — {desc}"
            lines.append(entry)

        lines.append(f"{enabled_count} of {len([p for p in plugins.values() if p.get('is_feed', True)])} feed plugins enabled.")
        return "\n".join(lines)

    def _toggle_feed(self, action: CLIAction) -> str:
        """Enable or disable a feed/plugin for the active station."""
        feed_name = (action.target or "").strip()
        if not feed_name:
            return "No feed name specified. Say which plugin to toggle."

        enabled = action.params.get("enabled", True)

        station = self._get_active_station()
        if not station:
            return "No station selected. Select or start a station first."

        # Resolve feed name (fuzzy match against plugin names)
        from shell_bookmark import discover_plugins, station_manifest_path, safe_read_yaml, safe_write_yaml
        plugins = discover_plugins()
        resolved = self._resolve_feed_name(feed_name, plugins)
        if not resolved:
            available = [p.get("display", n) for n, p in plugins.items() if p.get("is_feed", True)]
            return f"Plugin '{feed_name}' not found. Available: {', '.join(available[:10])}."

        mp = station_manifest_path(station.path)
        cfg = safe_read_yaml(mp)
        feeds = cfg.setdefault("feeds", {})
        if resolved not in feeds or not isinstance(feeds.get(resolved), dict):
            defaults = (plugins.get(resolved, {}).get("defaults") or {}).copy()
            feeds[resolved] = defaults
        feeds[resolved]["enabled"] = bool(enabled)
        safe_write_yaml(mp, cfg)

        # Update in-memory
        station.manifest = cfg

        display = plugins.get(resolved, {}).get("display", resolved)
        status = "enabled" if enabled else "disabled"
        return f"{display} feed {status} for {(station.manifest.get('station', {}) or {}).get('name', station.station_id)}."

    def _configure_feed(self, action: CLIAction) -> str:
        """Update configuration values for a specific feed/plugin."""
        feed_name = (action.target or "").strip()
        if not feed_name:
            return "No feed name specified."

        station = self._get_active_station()
        if not station:
            return "No station selected."

        from shell_bookmark import discover_plugins, station_manifest_path, safe_read_yaml, safe_write_yaml
        plugins = discover_plugins()
        resolved = self._resolve_feed_name(feed_name, plugins)
        if not resolved:
            return f"Plugin '{feed_name}' not found."

        params = dict(action.params)
        if not params:
            return f"No configuration values provided for {resolved}."

        mp = station_manifest_path(station.path)
        cfg = safe_read_yaml(mp)
        feeds = cfg.setdefault("feeds", {})
        if resolved not in feeds or not isinstance(feeds.get(resolved), dict):
            feeds[resolved] = {}
        feeds[resolved].update(params)
        safe_write_yaml(mp, cfg)
        station.manifest = cfg

        display = plugins.get(resolved, {}).get("display", resolved)
        keys = ", ".join(params.keys())
        return f"Updated {display} config: {keys}."

    def _plugin_command(self, action: CLIAction) -> str:
        """Send a command to a running plugin's web server."""
        plugin_name = (action.target or "").strip()
        if not plugin_name:
            return "No plugin specified for command."

        station = self._get_active_station()
        if not station:
            return "No station is running."

        if not self.shell.proc or not self.shell.proc.is_alive():
            return "Station is not running. Start the station first."

        # Determine the plugin web port (FTB uses env FTB_WEB_PORT, default 7555)
        web_port = 7555  # default FTB port
        params = dict(action.params)
        command = params.pop("command", "")

        try:
            import urllib.request
            target = f"http://127.0.0.1:{web_port}/api/{plugin_name}/command"
            data = json.dumps({"command": command, **params}).encode("utf-8")
            req = urllib.request.Request(
                target, data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return f"Plugin command '{command}' executed. Result: {json.dumps(result)[:500]}"
        except Exception as e:
            return f"Plugin command failed: {e}"

    def _open_plugin_ui(self, action: CLIAction) -> str:
        """Open a plugin's web UI in the browser."""
        plugin_name = (action.target or "").strip()
        station = self._get_active_station()
        if not station:
            return "No station selected."

        # Get the web server URL
        url = getattr(self.shell, "_web_server_url", None)
        if not url:
            try:
                from web_server import WEB_SHELL_PORT
                from shell_bookmark import get_global_config
                cfg = get_global_config()
                port = int(cfg.get("general", {}).get("web_server_port", WEB_SHELL_PORT))
                url = f"http://127.0.0.1:{port}"
            except Exception:
                url = "http://127.0.0.1:7800"

        ws_thread = getattr(self.shell, "_web_server_thread", None)
        if not ws_thread or not ws_thread.is_alive():
            return "Web server is not running. Start it first to access plugin UIs."

        plugin_url = f"{url}/station/{station.station_id}/"
        return _browser_ctl.show(plugin_url)

    def _resolve_feed_name(self, query: str, plugins: dict) -> Optional[str]:
        """Fuzzy-match a feed name against available plugins."""
        query_lower = query.strip().lower().replace(" ", "_").replace("-", "_")
        # Exact match
        if query_lower in plugins:
            return query_lower
        # Match by display name
        for name, info in plugins.items():
            display = (info.get("display", "") or "").lower()
            if query_lower == display.lower().replace(" ", "_"):
                return name
            if query_lower in name.lower() or query_lower in display.lower():
                return name
        # Partial/fuzzy
        for name, info in plugins.items():
            display = (info.get("display", "") or "").lower()
            if any(w in name.lower() or w in display.lower() for w in query_lower.split("_") if len(w) > 2):
                return name
        return None

    def _find_station(self, query: str):
        """Find a station by name or ID (fuzzy)."""
        query = query.strip().lower()
        # Strip common LLM-generated prefixes
        for prefix in ("station:", "station_", "station "):
            if query.startswith(prefix):
                query = query[len(prefix):]
        query_norm = query.replace(" ", "").replace("_", "").replace("-", "")
        # Pass 1: exact match
        for st in self.shell.stations:
            sid = st.station_id.lower()
            name = ((st.manifest.get("station", {}) or {}).get("name", "")).lower()
            if query == sid or query == name:
                return st
        # Pass 2: normalized exact match
        for st in self.shell.stations:
            sid_norm = st.station_id.lower().replace(" ", "").replace("_", "").replace("-", "")
            name = ((st.manifest.get("station", {}) or {}).get("name", "")).lower()
            name_norm = name.replace(" ", "").replace("_", "").replace("-", "")
            if query_norm == sid_norm or query_norm == name_norm:
                return st
        # Pass 3: substring match (both directions)
        for st in self.shell.stations:
            sid = st.station_id.lower()
            name = ((st.manifest.get("station", {}) or {}).get("name", "")).lower()
            if query in sid or query in name or sid in query or name in query:
                return st
        # Pass 4: normalized substring match
        for st in self.shell.stations:
            sid_norm = st.station_id.lower().replace(" ", "").replace("_", "").replace("-", "")
            name = ((st.manifest.get("station", {}) or {}).get("name", "")).lower()
            name_norm = name.replace(" ", "").replace("_", "").replace("-", "")
            if query_norm in sid_norm or query_norm in name_norm or sid_norm in query_norm or name_norm in query_norm:
                return st
        return None

    def _tk_call(self, func):
        """Schedule a function on the tkinter main thread."""
        try:
            self.shell.root.after(0, func)
        except Exception as e:
            _log(f"tk_call failed: {e}")


# ---------------------------------------------------------------------------
# Web Command Dispatcher — REST API-based actions for headless/web mode
# ---------------------------------------------------------------------------
class WebCommandDispatcher:
    """
    Executes structured CLIAction commands via the Radio OS web server REST API.
    No tkinter dependency — works headlessly against the web frontend.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:7800",
                 introspector: Optional["WebIntrospector"] = None):
        self.base_url = base_url.rstrip("/")
        self._introspector = introspector
        self._action_map = {
            "navigate": self._navigate,
            "click": self._click,
            "start": self._start,
            "stop": self._stop,
            "open": self._open,
            "close": self._close,
            "back": self._back,
            "select": self._select,
            "input": self._input,
            "show_browser": self._show_browser,
            "hide_browser": self._hide_browser,
            "play_audio": self._play_audio,
            "stop_audio": self._stop_audio,
            "mute_audio": self._mute_audio,
            "list_plugins": self._list_plugins,
            "toggle_feed": self._toggle_feed,
            "configure_feed": self._configure_feed,
            "plugin_command": self._plugin_command,
            "open_plugin_ui": self._open_plugin_ui,
            "restart_app": self._restart_app,
            "audio_keyboard": self._audio_keyboard,
        }

    def _post(self, path: str, data: Optional[Dict[str, Any]] = None,
              timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """POST JSON to an API endpoint."""
        try:
            import urllib.request
            url = f"{self.base_url}{path}"
            body = json.dumps(data or {}).encode("utf-8")
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json",
                          "Accept": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            _log(f"WebDispatcher POST {path} failed: {e}")
            return None

    def _get(self, path: str, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """GET a JSON endpoint."""
        try:
            import urllib.request
            url = f"{self.base_url}{path}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            _log(f"WebDispatcher GET {path} failed: {e}")
            return None

    def execute(self, actions: List[CLIAction]) -> List[str]:
        """Execute a list of actions with chaining support."""
        return _execute_chained(actions, self._action_map, label="WebDispatcher")

    def _navigate(self, action: CLIAction) -> str:
        target = (action.target or "").lower()
        if target in ("home", "station_browser", "browser"):
            if self._introspector:
                self._introspector.set_view("home")
            return "Navigated to Station Browser."
        elif target in ("runtime", "station_runtime"):
            if self._introspector:
                self._introspector.set_view("runtime")
            return "Navigated to Station Runtime."
        elif target == "settings":
            if self._introspector:
                self._introspector.set_view("settings")
            return "Opened Settings."
        return f"Unknown navigation target: {target}"

    def _click(self, action: CLIAction) -> str:
        target = (action.target or "").lower()
        if target in ("settings",):
            if self._introspector:
                self._introspector.set_view("settings")
            return "Opened Settings."
        elif target in ("new_station", "new"):
            return "New station creation available through the web interface."

        # Default: click / launch the currently selected or last-mentioned station
        station_id = self._find_station_id(target) if target else None
        if not station_id and self._introspector:
            station_id = self._introspector._active_station_id
        if station_id:
            result = self._post(f"/api/stations/{station_id}/launch")
            if result and result.get("status") in ("launched", "already_running"):
                if self._introspector:
                    self._introspector.set_view("runtime", station_id)
                name = station_id
                stations = (self._get("/api/stations") or {}).get("stations", [])
                for s in stations:
                    if s["station_id"] == station_id:
                        name = s.get("name", station_id)
                        break
                # Auto-start local audio playback
                _local_audio_player.start(self.base_url, station_id)
                return f"Launching station: {name}. Local audio playback enabled."
            elif result:
                return f"Launch failed: {result.get('message', 'unknown error')}"

        if target:
            return f"Unknown click target: {target}"
        return "Nothing is selected to click. Select a station first."

    def _start(self, action: CLIAction) -> str:
        target = (action.target or "").lower()
        station_id = self._find_station_id(target) if target else None

        # If the user asked for a specific station and we can't find it, don't
        # silently fall back to a different one — tell them it wasn't found.
        if target and not station_id:
            stations = (self._get("/api/stations") or {}).get("stations", [])
            names = [s.get("name", s["station_id"]) for s in stations]
            return (f"Station '{target}' not found. "
                    f"Available: {', '.join(names[:8])}.")

        # No specific station requested — try active/selected, then first available
        if not station_id:
            if self._introspector and self._introspector._active_station_id:
                station_id = self._introspector._active_station_id
            else:
                stations = (self._get("/api/stations") or {}).get("stations", [])
                running = [s for s in stations if s.get("running")]
                if running:
                    station_id = running[0]["station_id"]
                elif stations:
                    station_id = stations[0]["station_id"]

        if station_id:
            result = self._post(f"/api/stations/{station_id}/launch")
            if result and result.get("status") in ("launched", "already_running"):
                if self._introspector:
                    self._introspector.set_view("runtime", station_id)
                name = station_id
                # Try to get display name
                stations = (self._get("/api/stations") or {}).get("stations", [])
                for s in stations:
                    if s["station_id"] == station_id:
                        name = s.get("name", station_id)
                        break
                # Auto-start local audio playback in web mode
                _local_audio_player.start(self.base_url, station_id)
                return f"Starting station: {name}. Local audio playback enabled."
            elif result:
                return f"Launch failed: {result.get('message', 'unknown error')}"
        return f"No station selected. Select a station first."

    def _stop(self, action: CLIAction) -> str:
        # Stop local audio first
        _local_audio_player.stop()
        # Find currently running station
        stations = (self._get("/api/stations") or {}).get("stations", [])
        running = [s for s in stations if s.get("running")]
        if running:
            sid = running[0]["station_id"]
            result = self._post(f"/api/stations/{sid}/stop")
            if self._introspector:
                self._introspector.set_view("home")
            return "Station stopped."
        return "No station is currently running."

    def _open(self, action: CLIAction) -> str:
        return self._click(action)

    def _close(self, action: CLIAction) -> str:
        if self._introspector:
            self._introspector.set_view("home")
        return "Returned to browser."

    def _back(self, action: CLIAction) -> str:
        if self._introspector:
            self._introspector.set_view("home")
        return "Returned to Station Browser."

    def _select(self, action: CLIAction) -> str:
        # In web mode, selection is informational (no carousel)
        # but we remember it so "play it" / "start it" can use it
        target = (action.target or "").lower()
        if not target:
            return "No station specified to select."
        station_id = self._find_station_id(target)
        if station_id:
            if self._introspector:
                self._introspector._active_station_id = station_id
            return f"Selected station: {station_id}."
        return f"Station not found: {target}"

    def _input(self, action: CLIAction) -> str:
        """Submit text to a UI field.

        Tries the running station's plugin web server first (for game/wizard
        fields), then falls back to other mechanisms as they're added.
        This is the generic backend for audio-keyboard "enter" submissions.
        """
        field = (action.target or "").strip()
        text = action.params.get("text", "").strip()
        if not field:
            return "No field specified for input."
        if not text:
            return f"No text provided for field '{field}'."

        # Find the plugin web port for the running station
        station_id = self._get_active_station_id()
        web_port = None
        if station_id:
            status = self._get(f"/api/stations/{station_id}/status")
            web_port = (status or {}).get("web_port")

        if web_port:
            try:
                import urllib.request
                url = f"http://127.0.0.1:{web_port}/api/input_field"
                body = json.dumps({"field": field, "value": text}).encode("utf-8")
                req = urllib.request.Request(
                    url, data=body,
                    headers={"Content-Type": "application/json",
                              "Accept": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                if result.get("status") == "ok":
                    return f"Set {field} to '{text}'."
                return f"Server rejected input: {result.get('error', 'unknown')}"
            except Exception as e:
                _log(f"Input submit to plugin failed: {e}")
                return f"Failed to submit text for {field}: {e}"

        return f"No active plugin server to receive input for field '{field}'."

    def _restart_app(self, action: CLIAction) -> str:
        """Restart Radio OS via the web server restart endpoint."""
        import subprocess
        # In web mode, we restart the current Audio CLI process itself
        # and signal the web server to restart if possible
        script_path = sys.argv[0]
        def _do_restart():
            subprocess.Popen([sys.executable, script_path] + sys.argv[1:])
            sys.exit(0)
        # Delay restart so narration can play
        threading.Timer(2.0, _do_restart).start()
        return "Restarting Radio OS."

    def _audio_keyboard(self, action: CLIAction) -> str:
        """Activate the audio keyboard for text input. Handled at session level."""
        target = (action.target or "").strip() or "text_field"
        return f"__AUDIO_KEYBOARD_ACTIVATE__:{target}"

    def _show_browser(self, action: CLIAction) -> str:
        """Open the web UI in the system's default browser at the current view."""
        url = self.base_url
        if self._introspector:
            view = getattr(self._introspector, "_current_view", "home")
            sid = getattr(self._introspector, "_active_station_id", None)
            if view == "runtime" and sid:
                url = f"{self.base_url}/runtime/{sid}"
            # home and settings both live at root
        return _browser_ctl.show(url)

    def _hide_browser(self, action: CLIAction) -> str:
        """Close / hide the browser window, returning to headless operation."""
        return _browser_ctl.hide()

    def _play_audio(self, action: CLIAction) -> str:
        """Start or resume local audio playback for the running station."""
        if _local_audio_player.is_playing:
            return "Local audio is already playing."
        stations = (self._get("/api/stations") or {}).get("stations", [])
        running = [s for s in stations if s.get("running")]
        if running:
            sid = running[0]["station_id"]
            _local_audio_player.start(self.base_url, sid)
            return "Local audio playback started."
        return "No station is currently running."

    def _stop_audio(self, action: CLIAction) -> str:
        """Stop local audio playback (station keeps running)."""
        if not _local_audio_player.is_playing:
            return "Local audio is not playing."
        _local_audio_player.stop()
        return "Local audio playback stopped."

    def _mute_audio(self, action: CLIAction) -> str:
        """Toggle mute on local audio playback."""
        _local_audio_player.muted = not _local_audio_player.muted
        status = "muted" if _local_audio_player.muted else "unmuted"
        return f"Local audio {status}."

    # -- Plugin / feed control (web mode) ------------------------------------

    def _get_active_station_id(self) -> Optional[str]:
        """Return the currently active/running station ID."""
        if self._introspector and self._introspector._active_station_id:
            return self._introspector._active_station_id
        stations = (self._get("/api/stations") or {}).get("stations", [])
        running = [s for s in stations if s.get("running")]
        if running:
            return running[0]["station_id"]
        return None

    def _list_plugins(self, action: CLIAction) -> str:
        """List all available plugins and their status for the active station."""
        plugins_data = self._get("/api/plugins")
        if not plugins_data:
            return "Could not retrieve plugin list from the server."

        plugins = plugins_data.get("plugins", {})
        if not plugins:
            return "No plugins found."

        station_id = self._get_active_station_id()
        feeds_cfg = {}
        station_name = "no station selected"
        if station_id:
            feeds_data = self._get(f"/api/stations/{station_id}/feeds")
            if feeds_data:
                feeds_cfg = feeds_data.get("feeds", {})
            station_name = station_id
            # Try to get display name
            stations = (self._get("/api/stations") or {}).get("stations", [])
            for s in stations:
                if s["station_id"] == station_id:
                    station_name = s.get("name", station_id)
                    break

        lines = [f"Plugins for {station_name}:"]
        enabled_count = 0
        total_feeds = 0
        for name, info in plugins.items():
            if not info.get("is_feed", True):
                continue
            total_feeds += 1
            display = info.get("display", name)
            desc = info.get("desc", "")
            feed_info = feeds_cfg.get(name, {})
            is_enabled = bool(feed_info.get("enabled", False))
            status = "enabled" if is_enabled else "disabled"
            if is_enabled:
                enabled_count += 1
            entry = f"  {display} ({name}): {status}"
            if desc:
                entry += f" — {desc}"
            lines.append(entry)

        lines.append(f"{enabled_count} of {total_feeds} feed plugins enabled.")
        return "\n".join(lines)

    def _toggle_feed(self, action: CLIAction) -> str:
        """Enable or disable a feed/plugin via the REST API."""
        feed_name = (action.target or "").strip()
        if not feed_name:
            return "No feed name specified. Say which plugin to toggle."

        enabled = action.params.get("enabled", True)

        station_id = self._get_active_station_id()
        if not station_id:
            return "No station selected. Select or start a station first."

        # Fuzzy-match the feed name against available plugins
        plugins_data = self._get("/api/plugins")
        plugins = (plugins_data or {}).get("plugins", {})
        resolved = self._resolve_feed_name(feed_name, plugins)
        if not resolved:
            available = [p.get("display", n) for n, p in plugins.items() if p.get("is_feed", True)]
            return f"Plugin '{feed_name}' not found. Available: {', '.join(available[:10])}."

        result = self._post(
            f"/api/stations/{station_id}/feeds/{resolved}/toggle",
            {"enabled": bool(enabled)},
        )
        if result and result.get("status") == "ok":
            display = plugins.get(resolved, {}).get("display", resolved)
            status = "enabled" if enabled else "disabled"
            return f"{display} feed {status}."
        return f"Failed to toggle feed {resolved}."

    def _configure_feed(self, action: CLIAction) -> str:
        """Update configuration values for a feed/plugin via REST API."""
        feed_name = (action.target or "").strip()
        if not feed_name:
            return "No feed name specified."

        station_id = self._get_active_station_id()
        if not station_id:
            return "No station selected."

        plugins_data = self._get("/api/plugins")
        plugins = (plugins_data or {}).get("plugins", {})
        resolved = self._resolve_feed_name(feed_name, plugins)
        if not resolved:
            return f"Plugin '{feed_name}' not found."

        params = dict(action.params)
        if not params:
            return f"No configuration values provided for {resolved}."

        result = self._put(
            f"/api/stations/{station_id}/feeds/{resolved}/config",
            params,
        )
        if result and result.get("status") == "ok":
            display = plugins.get(resolved, {}).get("display", resolved)
            keys = ", ".join(params.keys())
            return f"Updated {display} config: {keys}."
        return f"Failed to update feed config for {resolved}."

    def _plugin_command(self, action: CLIAction) -> str:
        """Send a command to a running plugin's web server via REST API."""
        plugin_name = (action.target or "").strip()
        if not plugin_name:
            return "No plugin specified for command."

        station_id = self._get_active_station_id()
        if not station_id:
            return "No station is running."

        params = dict(action.params)
        result = self._post(
            f"/api/stations/{station_id}/plugin/{plugin_name}/command",
            params,
        )
        if result:
            if "error" in result:
                return f"Plugin command failed: {result['error']}"
            return f"Plugin command executed. Result: {json.dumps(result)[:500]}"
        return "Plugin command failed — no response from server."

    def _open_plugin_ui(self, action: CLIAction) -> str:
        """Open a plugin's web UI in the browser."""
        station_id = self._get_active_station_id()
        if not station_id:
            return "No station selected."

        plugin_url = f"{self.base_url}/station/{station_id}/"
        return _browser_ctl.show(plugin_url)

    def _put(self, path: str, data: Optional[Dict[str, Any]] = None,
             timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """PUT JSON to an API endpoint."""
        try:
            import urllib.request
            url = f"{self.base_url}{path}"
            body = json.dumps(data or {}).encode("utf-8")
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json",
                          "Accept": "application/json"},
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            _log(f"WebDispatcher PUT {path} failed: {e}")
            return None

    def _resolve_feed_name(self, query: str, plugins: dict) -> Optional[str]:
        """Fuzzy-match a feed name against available plugins."""
        query_lower = query.strip().lower().replace(" ", "_").replace("-", "_")
        # Exact match
        if query_lower in plugins:
            return query_lower
        # Match by display name
        for name, info in plugins.items():
            display = (info.get("display", "") or "").lower()
            if query_lower == display.lower().replace(" ", "_"):
                return name
            if query_lower in name.lower() or query_lower in display.lower():
                return name
        # Partial/fuzzy
        for name, info in plugins.items():
            display = (info.get("display", "") or "").lower()
            if any(w in name.lower() or w in display.lower()
                   for w in query_lower.split("_") if len(w) > 2):
                return name
        return None

    def _find_station_id(self, query: str) -> Optional[str]:
        """Find a station ID by name or ID (fuzzy match)."""
        query = query.strip().lower()
        # Strip common LLM-generated prefixes like "station:" or "station_"
        for prefix in ("station:", "station_", "station "):
            if query.startswith(prefix):
                query = query[len(prefix):]
        # If nothing meaningful remains after stripping, no station specified
        if not query or query in ("it", "this", "that", "the", "a", "one"):
            return None
        # Remove spaces, underscores, hyphens for flexible matching
        query_norm = query.replace(" ", "").replace("_", "").replace("-", "")
        stations = (self._get("/api/stations") or {}).get("stations", [])
        # Pass 1: exact match on ID or name
        for s in stations:
            sid = s["station_id"].lower()
            name = s.get("name", "").lower()
            if query == sid or query == name:
                return s["station_id"]
        # Pass 2: normalized match (ignore spaces/underscores/hyphens)
        for s in stations:
            sid_norm = s["station_id"].lower().replace(" ", "").replace("_", "").replace("-", "")
            name_norm = s.get("name", "").lower().replace(" ", "").replace("_", "").replace("-", "")
            if query_norm == sid_norm or query_norm == name_norm:
                return s["station_id"]
        # Pass 3: substring match
        for s in stations:
            sid = s["station_id"].lower()
            name = s.get("name", "").lower()
            if query in sid or query in name or sid in query or name in query:
                return s["station_id"]
        # Pass 4: normalized substring match
        for s in stations:
            sid_norm = s["station_id"].lower().replace(" ", "").replace("_", "").replace("-", "")
            name_norm = s.get("name", "").lower().replace(" ", "").replace("_", "").replace("-", "")
            if query_norm in sid_norm or query_norm in name_norm or sid_norm in query_norm or name_norm in query_norm:
                return s["station_id"]
        return None


# ---------------------------------------------------------------------------
# Game Command Dispatcher — talks DIRECTLY to the FTB game on port 7555
# ---------------------------------------------------------------------------
class GameCommandDispatcher:
    """
    Executes game-related CLIAction commands directly against the FTB plugin
    web server (default port 7555).  This dispatcher does NOT route through
    the runtime at port 7800 — it is a dedicated, independent channel for
    game control.

    Responsibilities:
      - Wizard navigation (new_game, set_tier, wizard_next, confirm_new_game…)
      - In-game actions (advance_day, save_game, hire_staff, watch_live_race…)
      - Tab switching (show_team, show_finance, show_dashboard…)
      - Decision resolution (choose an option from pending_decisions)
      - Game state introspection (fetches /api/state, /api/ui_screen)
    """

    def __init__(self, game_port: int = 7555):
        self.game_port = game_port
        self.base_url = f"http://127.0.0.1:{game_port}"
        self._action_map = {
            "plugin_command": self._plugin_command,
            "input": self._input,
            "navigate": self._navigate,
            "start_game": self._start_game,
            "audio_keyboard": self._audio_keyboard,
        }

    # -- HTTP helpers (direct to game port) ----------------------------------

    def _post(self, path: str, data: Optional[Dict[str, Any]] = None,
              timeout: float = 15.0) -> Optional[Dict[str, Any]]:
        """POST JSON to the game server."""
        try:
            import urllib.request
            url = f"{self.base_url}{path}"
            body = json.dumps(data or {}).encode("utf-8")
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json",
                          "Accept": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            _log(f"GameDispatcher POST {path} failed: {e}")
            return None

    def _get(self, path: str, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """GET a JSON endpoint from the game server."""
        try:
            import urllib.request
            url = f"{self.base_url}{path}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            _log(f"GameDispatcher GET {path} failed: {e}")
            return None

    def _delete(self, path: str, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """DELETE a JSON endpoint on the game server."""
        try:
            import urllib.request
            url = f"{self.base_url}{path}"
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json"},
                method="DELETE",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            _log(f"GameDispatcher DELETE {path} failed: {e}")
            return None

    # -- Public interface ----------------------------------------------------

    @property
    def is_reachable(self) -> bool:
        """Quick check: is the game server responding?"""
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.base_url}/api/state",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def get_game_state(self) -> Dict[str, Any]:
        """
        Fetch the full game state directly from port 7555.
        Returns a dict suitable for inclusion in the LLM's UI state context.
        """
        full = self._get("/api/state")
        if not full:
            return {"status": "unreachable", "error": "Game server not responding"}

        # Also fetch UI screen
        ui_screen = self._get("/api/ui_screen")

        if full.get("status") == "no_game":
            result: Dict[str, Any] = {
                "status": "no_game",
                "available_actions": ["new_game", "load_game"],
            }
            if ui_screen:
                result["ui_screen"] = ui_screen
            return result

        # Build a rich summary so the LLM can answer questions about
        # drivers, car, parts, infrastructure, R&D, sponsors, etc.
        # without having to navigate to a specific tab first.
        compact: Dict[str, Any] = {
            "status": full.get("status", "unknown"),
            "phase": full.get("phase", ""),
            "date": full.get("date_str", ""),
            "season": full.get("season_number", 0),
            "in_offseason": full.get("in_offseason", False),
            "race_day_active": full.get("race_day_active", False),
        }

        if ui_screen:
            compact["ui_screen"] = ui_screen

        # ── Player team (full detail) ─────────────────────────────
        pt = full.get("player_team")
        if pt and isinstance(pt, dict):
            team_info: Dict[str, Any] = {
                "name": pt.get("name", ""),
                "league": pt.get("league", ""),
                "tier": pt.get("tier", ""),
            }

            # Budget (full breakdown)
            budget = pt.get("budget")
            if isinstance(budget, dict):
                team_info["budget"] = {
                    "cash": budget.get("cash", budget.get("balance", 0)),
                    "weekly_expenses": budget.get("weekly_expenses", 0),
                    "weekly_income": budget.get("weekly_income", 0),
                }
            else:
                team_info["budget"] = {"cash": 0}

            # Roster — all roles with full stats & contracts
            roster = pt.get("roster", {})
            if isinstance(roster, dict) and roster:
                team_info["roster"] = {}
                for role, members in roster.items():
                    if members is None:
                        continue
                    if isinstance(members, list):
                        team_info["roster"][role] = [
                            self._compact_entity(m) for m in members[:6]
                            if isinstance(m, dict)
                        ]
                    elif isinstance(members, dict):
                        # Single entity (e.g. principal, strategist)
                        team_info["roster"][role] = self._compact_entity(members)
            else:
                # Fallback: try legacy "drivers" key
                drivers = pt.get("drivers", [])
                if isinstance(drivers, dict):
                    drivers = list(drivers.values())
                if isinstance(drivers, list) and drivers:
                    team_info["roster"] = {"drivers": [
                        self._compact_entity(d) for d in drivers[:6]
                        if isinstance(d, dict)
                    ]}

            # Car stats & equipped parts
            car = pt.get("car")
            if isinstance(car, dict):
                car_info: Dict[str, Any] = {
                    "name": car.get("name", ""),
                    "overall": car.get("overall", 0),
                }
                if car.get("stats"):
                    car_info["stats"] = car["stats"]
                eq = car.get("equipped_parts", [])
                if isinstance(eq, list) and eq:
                    car_info["equipped_parts"] = [
                        self._compact_part(p) for p in eq[:12]
                        if isinstance(p, dict)
                    ]
                inv = car.get("parts_inventory", [])
                if isinstance(inv, list) and inv:
                    car_info["parts_inventory"] = [
                        self._compact_part(p) for p in inv[:12]
                        if isinstance(p, dict)
                    ]
                team_info["car"] = car_info

            # Infrastructure
            infra = pt.get("infrastructure")
            if isinstance(infra, dict) and infra:
                team_info["infrastructure"] = {
                    k: v for k, v in infra.items()
                    if isinstance(v, (int, float)) and not isinstance(v, bool)
                }

            # Active R&D projects
            rd_projects = pt.get("rd_projects", [])
            if isinstance(rd_projects, list) and rd_projects:
                team_info["rd_projects"] = []
                for proj in rd_projects[:8]:
                    if not isinstance(proj, dict):
                        continue
                    team_info["rd_projects"].append({
                        "id": proj.get("id", ""),
                        "name": proj.get("name", ""),
                        "subsystem": proj.get("subsystem", proj.get("target_stat", "")),
                        "progress": proj.get("progress", 0),
                        "duration_ticks": proj.get("duration_ticks", 0),
                        "budget": proj.get("budget", 0),
                        "risk_level": proj.get("risk_level", ""),
                        "completed": proj.get("completed", False),
                    })

            compact["player_team"] = team_info

        # ── Contracts ─────────────────────────────────────────────
        contracts = full.get("contracts", {})
        if isinstance(contracts, dict) and contracts:
            compact["contracts"] = []
            for _eid, c in list(contracts.items())[:15]:
                if not isinstance(c, dict):
                    continue
                compact["contracts"].append({
                    "entity": c.get("entity_name", ""),
                    "role": c.get("role", ""),
                    "salary": c.get("base_salary", 0),
                    "seasons_left": c.get("seasons_remaining", 0),
                    "buyout": c.get("buyout", 0),
                })

        # ── Sponsorships ──────────────────────────────────────────
        sponsorships = full.get("sponsorships", {})
        if isinstance(sponsorships, dict):
            player_name = (pt or {}).get("name", "")
            player_sponsors = sponsorships.get(player_name, [])
            if isinstance(player_sponsors, list) and player_sponsors:
                compact["sponsorships"] = [
                    {
                        "name": s.get("name", ""),
                        "value": s.get("value", 0),
                        "seasons_remaining": s.get("seasons_remaining", 0),
                        "confidence": s.get("confidence", 100),
                    }
                    for s in player_sponsors[:8] if isinstance(s, dict)
                ]

        # ── Pending sponsor offers ────────────────────────────────
        offers = full.get("pending_sponsor_offers", {})
        offer_count = sum(len(v) for v in offers.values()) if isinstance(offers, dict) else 0
        if offer_count > 0:
            compact["pending_sponsor_offers"] = offer_count

        # ── Free agents (summary) ─────────────────────────────────
        free_agents = full.get("free_agents", [])
        if isinstance(free_agents, list) and free_agents:
            compact["free_agents"] = [
                {
                    "name": fa.get("name", ""),
                    "type": fa.get("type", ""),
                    "age": fa.get("age", 0),
                    "overall": fa.get("overall", 0),
                    "asking_salary": fa.get("asking_salary", 0),
                    "id": fa.get("id", 0),
                }
                for fa in free_agents[:15] if isinstance(fa, dict)
            ]

        # ── Job board ─────────────────────────────────────────────
        job_board = full.get("job_board", [])
        if isinstance(job_board, list) and job_board:
            compact["job_board"] = [
                {
                    "id": j.get("id", 0),
                    "team": j.get("team_name", ""),
                    "role": j.get("role", ""),
                    "salary_range": j.get("salary_range", []),
                }
                for j in job_board[:10] if isinstance(j, dict)
            ]

        # ── Pending decisions ─────────────────────────────────────
        decisions = full.get("pending_decisions", [])
        if isinstance(decisions, dict):
            decisions = list(decisions.values())
        if decisions and isinstance(decisions, list):
            compact["pending_decisions"] = []
            for d in decisions[:5]:
                if not isinstance(d, dict):
                    continue
                dec: Dict[str, Any] = {
                    "id": d.get("id", 0),
                    "prompt": d.get("prompt", "")[:200],
                }
                opts = d.get("options", [])
                if isinstance(opts, dict):
                    opts = list(opts.values())
                if opts and isinstance(opts, list):
                    dec["options"] = [
                        {"label": o.get("label", ""),
                         "cost": o.get("cost", 0),
                         "description": o.get("description", "")[:80]}
                        for o in opts[:6] if isinstance(o, dict)
                    ]
                compact["pending_decisions"].append(dec)

        # ── Race day state ────────────────────────────────────────
        rd = full.get("race_day", {})
        if isinstance(rd, dict) and rd.get("phase") != "idle":
            compact["race_day"] = {
                "phase": rd.get("phase", ""),
                "current_lap": rd.get("current_lap", 0),
                "total_laps": rd.get("total_laps", 0),
                "live_race_active": rd.get("live_race_active", False),
                "broadcast_active": rd.get("broadcast_active", False),
            }
            standings = rd.get("standings", [])
            if isinstance(standings, dict):
                standings = list(standings.values())
            if standings and isinstance(standings, list):
                compact["race_day"]["top_5"] = [
                    {"driver": s.get("driver", ""), "team": s.get("team", "")}
                    for s in standings[:5] if isinstance(s, dict)
                ]

        # ── Championship standings ────────────────────────────────
        leagues = full.get("leagues", {})
        if isinstance(leagues, dict) and leagues:
            compact["championships"] = {}
            for lname, league in leagues.items():
                if not isinstance(league, dict):
                    continue
                league_info: Dict[str, Any] = {
                    "tier": league.get("tier_name", league.get("tier", "")),
                    "races_this_season": league.get("races_this_season", 0),
                }
                ct = league.get("championship_table")
                if isinstance(ct, dict):
                    sorted_teams = sorted(
                        ct.items(),
                        key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0,
                        reverse=True)
                    league_info["team_standings"] = [
                        {"team": t, "points": p}
                        for t, p in sorted_teams[:10]
                    ]
                dc = league.get("driver_championship")
                if isinstance(dc, dict):
                    sorted_drivers = sorted(
                        dc.items(),
                        key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0,
                        reverse=True)
                    league_info["driver_standings"] = [
                        {"driver": d, "points": p}
                        for d, p in sorted_drivers[:10]
                    ]
                # Next scheduled races
                sched = league.get("schedule", [])
                if isinstance(sched, list):
                    upcoming = [
                        r for r in sched
                        if isinstance(r, dict) and not r.get("completed", False)
                    ][:3]
                    if upcoming:
                        league_info["upcoming_races"] = [
                            {"track": r.get("track_name", ""), "tick": r.get("tick", 0)}
                            for r in upcoming
                        ]
                compact["championships"][lname] = league_info

        # ── Recent events ─────────────────────────────────────────
        events = full.get("recent_events", [])
        if isinstance(events, dict):
            events = list(events.values())
        if events and isinstance(events, list):
            compact["recent_events"] = [
                {"type": e.get("type", ""), "desc": e.get("description", "")[:120]}
                for e in events[:8] if isinstance(e, dict)
            ]

        # ── Manager career ────────────────────────────────────────
        mc = full.get("manager_career")
        if isinstance(mc, dict) and mc:
            compact["manager_career"] = mc

        # ── Available actions ─────────────────────────────────────
        actions = full.get("available_actions", [])
        if actions:
            compact["available_actions"] = actions

        return compact

    @staticmethod
    def _compact_entity(entity: Dict[str, Any]) -> Dict[str, Any]:
        """Compact an entity (driver/engineer/etc.) for the LLM context."""
        if not isinstance(entity, dict):
            return {"name": str(entity)}
        out: Dict[str, Any] = {"name": entity.get("name", "")}
        for key in ("type", "age", "overall", "entity_id",
                     "potential_ceiling", "morale_baseline",
                     "form_momentum", "display_name"):
            if key in entity and entity[key] is not None:
                out[key] = entity[key]
        # Full stats dict
        stats = entity.get("stats")
        if isinstance(stats, dict):
            out["stats"] = stats
        # Contract
        contract = entity.get("contract")
        if isinstance(contract, dict):
            out["contract"] = {
                "salary": contract.get("salary", 0),
                "seasons_remaining": contract.get("seasons_remaining", 0),
                "buyout": contract.get("buyout", 0),
                "role": contract.get("role", ""),
            }
        return out

    @staticmethod
    def _compact_part(part: Dict[str, Any]) -> Dict[str, Any]:
        """Compact a part for the LLM context."""
        if not isinstance(part, dict):
            return {}
        out: Dict[str, Any] = {
            "id": part.get("id", ""),
            "name": part.get("name", ""),
            "type": part.get("type", ""),
            "quality": part.get("quality", 0),
            "cost": part.get("cost", 0),
        }
        stats = part.get("stats")
        if isinstance(stats, dict):
            out["stats"] = stats
        return out

    def execute(self, actions: List[CLIAction]) -> List[str]:
        """Execute a list of game actions with chaining support."""
        return _execute_chained(
            actions,
            self._action_map,
            fallback_handler=self._plugin_command,
            label="GameDispatcher",
        )

    # -- Action handlers -----------------------------------------------------

    def _start_game(self, action: CLIAction) -> str:
        """Start a new game or load an existing one via /api/navigate."""
        command = action.params.get("command", "new_game")
        if command in ("new_game", "navigate_wizard"):
            result = self._post("/api/navigate", {"target": "wizard"})
            if result and result.get("status") == "ok":
                return "New Game wizard opened. Ready for setup."
            return "Failed to open the new game wizard."
        elif command in ("load_game", "load"):
            result = self._post("/api/navigate", {"target": "load_screen"})
            if result and result.get("status") == "ok":
                return "Load Game screen opened."
            return "Failed to open the load game screen."
        return f"Unknown start_game command: {command}."

    def _plugin_command(self, action: CLIAction) -> str:
        """
        Route a game command to the correct FTB web server endpoint.

        The LLM emits plugin_command actions with a "command" param.  This
        method maps each command to the real REST endpoint on port 7555
        instead of funnelling everything through a single catch-all URL.
        """
        params = dict(action.params)
        command = params.pop("command", action.target or "")
        if not command:
            return "No game command specified."

        command_lower = command.lower().strip()

        # ── Navigation / wizard flow ──────────────────────────────
        if command_lower in ("new_game", "navigate_wizard"):
            result = self._post("/api/navigate", {"target": "wizard"})
            if result and result.get("status") == "ok":
                return f"Wizard opened at step {result.get('wizard_step', 1)}."
            return "Failed to open wizard."

        if command_lower in ("navigate_landing", "go_home", "main_menu"):
            result = self._post("/api/navigate", {"target": "landing"})
            if result and result.get("status") == "ok":
                return "Returned to main menu."
            return "Failed to navigate to main menu."

        if command_lower in ("wizard_next", "next"):
            result = self._post("/api/navigate", {"target": "wizard_next"})
            if result and result.get("status") == "ok":
                return f"Wizard advanced to step {result.get('wizard_step', '?')}."
            return "Failed to advance wizard."

        if command_lower in ("wizard_prev", "wizard_back", "back"):
            result = self._post("/api/navigate", {"target": "wizard_prev"})
            if result and result.get("status") == "ok":
                return f"Wizard returned to step {result.get('wizard_step', '?')}."
            return "Failed to go back in wizard."

        if command_lower in ("load_game", "show_load_screen"):
            result = self._post("/api/navigate", {"target": "load_screen"})
            if result and result.get("status") == "ok":
                return "Load game screen opened."
            return "Failed to open load screen."

        # ── Wizard field setters ──────────────────────────────────
        if command_lower in ("set_wizard_field",):
            field = params.get("field", "")
            value = params.get("value", "")
            if not field:
                return "No field specified for set_wizard_field."
            result = self._post("/api/wizard_field",
                                {"field": field, "value": value})
            if result and result.get("status") == "ok":
                return f"Set {field} to '{value}'."
            err = (result or {}).get("error", "unknown")
            return f"Failed to set {field}: {err}"

        # Shorthand field setters (set_tier, set_origin, set_save_mode, etc.)
        shorthand_fields = {
            "set_tier": "tier",
            "set_origin": "origin",
            "set_save_mode": "save_mode",
            "set_seed": "seed",
            "set_ownership": "ownership",
            "set_team_name": "team_name",
        }
        if command_lower in shorthand_fields:
            field = shorthand_fields[command_lower]
            value = params.get("value", "")
            result = self._post("/api/wizard_field",
                                {"field": field, "value": value})
            if result and result.get("status") == "ok":
                return f"Set {field} to '{value}'."
            err = (result or {}).get("error", "unknown")
            return f"Failed to set {field}: {err}"

        # ── Confirm new game (creates the save) ──────────────────
        if command_lower in ("confirm_new_game", "create_game"):
            result = self._post("/api/new_game", {
                "origin": params.get("origin", "grassroots_hustler"),
                "tier": params.get("tier", "grassroots"),
                "save_mode": params.get("save_mode", "replayable"),
                "seed": params.get("seed", 42),
                "team_name": params.get("team_name", ""),
                "ownership": params.get("ownership", "self_owned"),
                "identity": params.get("identity", []),
                "manager_age": params.get("manager_age", 32),
                "manager_first_name": params.get("manager_first_name", "Manager"),
                "manager_last_name": params.get("manager_last_name", "Unknown"),
            })
            if result and result.get("status") == "queued":
                return "New game created. Loading your world."
            return "Failed to create new game."

        # ── Tick / advance day ────────────────────────────────────
        if command_lower in ("advance_day", "ftb_tick_step", "tick"):
            n = int(params.get("n", 1))
            result = self._post("/api/tick", {"n": n, "batch": False})
            if result and result.get("status") == "queued":
                return f"Advanced {n} day{'s' if n > 1 else ''}."
            return "Failed to advance day."

        if command_lower in ("ftb_tick_batch", "tick_batch"):
            n = int(params.get("n", 7))
            result = self._post("/api/tick", {"n": n, "batch": True})
            if result and result.get("status") == "queued":
                return f"Advancing {n} days in batch."
            return "Failed to batch advance."

        # ── Save / load ───────────────────────────────────────────
        if command_lower in ("save_game", "save"):
            name = params.get("name", "")
            path = params.get("path", "")
            result = self._post("/api/save_game",
                                {"name": name, "path": path})
            if result and result.get("status") == "queued":
                return f"Game saved ({result.get('path', 'autosave')})."
            return "Failed to save game."

        if command_lower in ("load_save",):
            path = params.get("path", "")
            if not path:
                return "No save path specified."
            result = self._post("/api/load_game", {"path": path})
            if result and result.get("status") == "queued":
                return "Loading save."
            return "Failed to load save."

        # ── Tab switching ─────────────────────────────────────────
        tab_commands = {
            "show_dashboard": "dashboard", "show_team": "team",
            "show_car": "car", "show_development": "development",
            "show_finance": "finance", "show_sponsors": "sponsors",
            "show_race": "raceops", "show_stats": "stats",
            "show_calendar": "calendar", "show_career": "career",
            "switch_tab": params.get("tab", ""),
        }
        if command_lower in tab_commands:
            tab = tab_commands[command_lower]
            if not tab:
                return "No tab specified for switch_tab."
            result = self._post("/api/navigate", {"target": tab})
            if result and result.get("status") == "ok":
                return f"Switched to {tab} tab."
            return f"Failed to switch to {tab} tab."

        # ── Race day ──────────────────────────────────────────────
        if command_lower in ("watch_live_race", "start_live_race",
                             "ftb_start_live_race"):
            result = self._post("/api/race_day/start_live", {})
            if result and result.get("status") in ("ok", "queued"):
                return "Live race started."
            return "Failed to start live race."

        if command_lower in ("instant_sim_race", "instant_sim",
                             "ftb_pre_race_response"):
            choice = params.get("choice", "instant_sim")
            result = self._post("/api/race_day/respond",
                                {"choice": choice})
            if result and result.get("status") in ("ok", "queued"):
                return f"Race day response: {choice}."
            return "Failed to send race day response."

        if command_lower in ("complete_race_day", "finish_race"):
            result = self._post("/api/race_day/complete", {})
            if result and result.get("status") in ("ok", "queued"):
                return "Race day completed."
            return "Failed to complete race day."

        if command_lower in ("pause_race",):
            result = self._post("/api/race_day/pause", {})
            if result and result.get("status") in ("ok", "queued"):
                return "Race paused."
            return "Failed to pause race."

        # ── Staff management ──────────────────────────────────────
        if command_lower in ("hire_staff", "hire_free_agent", "hire"):
            result = self._post("/api/staff/hire", {
                "entity_name": params.get("entity_name", ""),
                "free_agent_id": params.get("free_agent_id", 0),
            })
            if result and result.get("status") == "queued":
                return f"Hiring {params.get('entity_name', 'staff')}."
            return "Failed to hire."

        if command_lower in ("fire_staff", "fire"):
            result = self._post("/api/staff/fire", {
                "entity_name": params.get("entity_name", ""),
            })
            if result and result.get("status") == "queued":
                return f"Fired {params.get('entity_name', 'staff')}."
            return "Failed to fire."

        # ── Parts management ──────────────────────────────────────
        if command_lower in ("buy_parts", "buy_part"):
            result = self._post("/api/parts/buy", {
                "part_id": params.get("part_id", ""),
            })
            if result and result.get("status") == "queued":
                return "Part purchased."
            return "Failed to buy part."

        if command_lower in ("sell_parts", "sell_part"):
            result = self._post("/api/parts/sell", {
                "part_id": params.get("part_id", ""),
            })
            if result and result.get("status") == "queued":
                return "Part sold."
            return "Failed to sell part."

        # ── Sponsor management ────────────────────────────────────
        if command_lower in ("accept_sponsor",):
            result = self._post("/api/sponsor/accept", {
                "offer_index": params.get("offer_index", 0),
            })
            if result and result.get("status") == "queued":
                return "Sponsor offer accepted."
            return "Failed to accept sponsor."

        if command_lower in ("decline_sponsor",):
            result = self._post("/api/sponsor/decline", {
                "offer_index": params.get("offer_index", 0),
            })
            if result and result.get("status") == "queued":
                return "Sponsor offer declined."
            return "Failed to decline sponsor."

        # ── R&D ───────────────────────────────────────────────────
        if command_lower in ("start_rd_project", "start_rd"):
            result = self._post("/api/rd/start", {
                "project_id": params.get("project_id", ""),
            })
            if result and result.get("status") == "queued":
                return "R&D project started."
            return "Failed to start R&D project."

        # ── Infrastructure ────────────────────────────────────────
        if command_lower in ("upgrade_infrastructure", "upgrade_facility"):
            result = self._post("/api/infrastructure/upgrade", {
                "facility": params.get("facility", ""),
                "amount": params.get("amount", 10),
            })
            if result and result.get("status") == "queued":
                return f"Upgrading {params.get('facility', 'facility')}."
            return "Failed to upgrade."

        if command_lower in ("sell_infrastructure", "sell_facility",
                             "downgrade_infrastructure"):
            result = self._post("/api/infrastructure/sell", {
                "facility": params.get("facility", ""),
            })
            if result and result.get("status") == "queued":
                return f"Sold {params.get('facility', 'facility')}."
            return "Failed to sell infrastructure."

        # ── Parts: equip ──────────────────────────────────────────
        if command_lower in ("equip_part", "equip"):
            result = self._post("/api/parts/equip", {
                "part_id": params.get("part_id", ""),
            })
            if result and result.get("status") == "queued":
                return "Part equipped."
            return "Failed to equip part."

        # ── R&D: cancel ──────────────────────────────────────────
        if command_lower in ("cancel_rd_project", "cancel_rd", "cancel_development"):
            result = self._post("/api/rd/cancel", {
                "project_id": params.get("project_id", ""),
            })
            if result and result.get("status") == "queued":
                return "R&D project cancelled."
            return "Failed to cancel R&D project."

        # ── R&D: browse catalog ───────────────────────────────────
        if command_lower in ("list_rd_projects", "rd_catalog", "show_rd_catalog",
                             "available_rd", "list_development"):
            result = self._get("/api/rd_catalog")
            if result and "catalog" in result:
                catalog = result["catalog"]
                if not catalog:
                    return "No R&D projects available."
                lines = [f"{len(catalog)} R&D projects available:"]
                for p in catalog[:8]:
                    cost_str = f" ({p.get('cost', 0):,} credits)" if p.get("cost") else ""
                    lines.append(f"  • {p.get('name', p.get('id', '?'))}{cost_str}")
                if len(catalog) > 8:
                    lines.append(f"  … and {len(catalog) - 8} more.")
                return "\n".join(lines)
            return "Failed to fetch R&D catalog."

        # ── Staff: apply for job ──────────────────────────────────
        if command_lower in ("apply_job", "apply_for_job", "apply"):
            result = self._post("/api/staff/apply_job", {
                "listing_id": params.get("listing_id", 0),
            })
            if result and result.get("status") == "queued":
                return "Applied for job."
            return "Failed to apply for job."

        # ── Race day: resume ──────────────────────────────────────
        if command_lower in ("resume_race", "unpause_race"):
            result = self._post("/api/race_day/pause", {"paused": False})
            if result and result.get("status") in ("ok", "queued"):
                return "Race resumed."
            return "Failed to resume race."

        # ── Race day: get current state ───────────────────────────
        if command_lower in ("race_status", "race_state", "race_day_status"):
            result = self._get("/api/race_day")
            if result:
                phase = result.get("phase", "unknown")
                lap = result.get("current_lap", 0)
                total = result.get("total_laps", 0)
                live = result.get("live_race_active", False)
                standings = result.get("standings", [])
                parts = [f"Race phase: {phase}."]
                if lap and total:
                    parts.append(f"Lap {lap}/{total}.")
                if live:
                    parts.append("Live race is active.")
                if standings and isinstance(standings, list):
                    top = standings[:3]
                    pos_strs = []
                    for i, s in enumerate(top, 1):
                        if isinstance(s, dict):
                            pos_strs.append(f"P{i} {s.get('driver', '?')}")
                    if pos_strs:
                        parts.append("Top 3: " + ", ".join(pos_strs) + ".")
                return " ".join(parts)
            return "Failed to fetch race day state."

        # ── Save management: delete ───────────────────────────────
        if command_lower in ("delete_save", "remove_save"):
            filename = params.get("filename", params.get("name", ""))
            if not filename:
                return "No save filename specified."
            if not filename.endswith(".json"):
                filename += ".json"
            result = self._delete(f"/api/saves/{filename}")
            if result and result.get("status") == "ok":
                return f"Save '{filename}' deleted."
            return f"Failed to delete save '{filename}'."

        # ── Save management: list saves ───────────────────────────
        if command_lower in ("list_saves", "show_saves", "available_saves"):
            result = self._get("/api/saves")
            if result and "saves" in result:
                saves = result["saves"]
                if not saves:
                    return "No saves found."
                lines = [f"{len(saves)} save{'s' if len(saves) != 1 else ''} available:"]
                for s in saves[:10]:
                    name = s.get("name", "?").replace(".json", "")
                    lines.append(f"  • {name}")
                if len(saves) > 10:
                    lines.append(f"  … and {len(saves) - 10} more.")
                return "\n".join(lines)
            return "Failed to fetch saves."

        # ── Pending decisions: resolve ────────────────────────────
        if command_lower in ("resolve_decision", "choose_option",
                             "decide", "answer_decision"):
            decision_id = params.get("decision_id", params.get("id", 0))
            option_index = params.get("option_index", params.get("choice", 0))
            result = self._post("/api/command", {
                "cmd": "ftb_resolve_decision",
                "decision_id": decision_id,
                "option_index": option_index,
            })
            if result and result.get("status") == "queued":
                return f"Decision resolved (option {option_index})."
            return "Failed to resolve decision."

        # ── Generic fallback: send to /api/command queue ──────────
        data = {"cmd": command, **params}
        result = self._post("/api/command", data)
        if result:
            if "error" in result:
                return f"Game command '{command}' failed: {result['error']}"
            return f"Game command '{command}' queued."
        return f"Game command '{command}' failed — no response from game server."

    def _input(self, action: CLIAction) -> str:
        """Submit text input directly to the game server."""
        field = (action.target or "").strip()
        text = action.params.get("text", "").strip()
        if not field:
            return "No field specified for input."
        if not text:
            return f"No text provided for field '{field}'."
        try:
            import urllib.request
            url = f"{self.base_url}/api/input_field"
            body = json.dumps({"field": field, "value": text}).encode("utf-8")
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json",
                          "Accept": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            if result.get("status") == "ok":
                return f"Set {field} to '{text}'."
            return f"Server rejected input: {result.get('error', 'unknown')}"
        except Exception as e:
            return f"Failed to submit text for {field}: {e}"

    def _navigate(self, action: CLIAction) -> str:
        """Handle navigation within the game UI (tab switches, etc.)."""
        target = (action.target or "").lower()
        # Direct navigation targets the FTB /api/navigate endpoint
        result = self._post("/api/navigate", {"target": target})
        if result and result.get("status") == "ok":
            screen = result.get("screen", target)
            tab = result.get("active_tab", "")
            if tab:
                return f"Switched to {tab} tab."
            return f"Navigated to {screen}."
        err = (result or {}).get("error", "")
        if err:
            return f"Navigation failed: {err}"
        return f"Unknown game navigation target: {target}"

    def _audio_keyboard(self, action: CLIAction) -> str:
        """Activate the audio keyboard. Handled at session level."""
        target = (action.target or "").strip() or "text_field"
        return f"__AUDIO_KEYBOARD_ACTIVATE__:{target}"


# ---------------------------------------------------------------------------
# Audio CLI Session Controller
# ---------------------------------------------------------------------------
class AudioCLISession:
    """
    Manages the full Audio CLI lifecycle:
      - Mic listening (wake detection + command capture)
      - Session state (inactive / active / speaking)
      - Audio ducking signaling

    Supports two modes:
      - **tkinter mode** (default): pass a RadioShell instance.
        Uses UIIntrospector + CommandDispatcher for tkinter widget control.
      - **web mode**: pass shell=None, web_url="http://...".
        Uses WebIntrospector + WebCommandDispatcher for REST API control.
        No tkinter dependency — runs fully headless.

    Context routing:
      - **runtime** context (default): commands go to the runtime dispatcher
        (port 7800) for station management, settings, plugin toggling, etc.
      - **game** context: commands go to the GameCommandDispatcher (port 7555)
        for direct FTB game control — wizard, decisions, race day, tabs, etc.
      The user switches context with "switch to the game" / "switch to runtime".
    """

    # Valid context values
    CONTEXT_RUNTIME = "runtime"
    CONTEXT_GAME = "game"

    def __init__(self, shell=None, web_url: Optional[str] = None):
        """
        Args:
            shell:   RadioShell instance for tkinter mode (or None for web mode)
            web_url: Base URL of the Radio OS web server for web mode
                     (e.g. "http://127.0.0.1:7800")
        """
        self.shell = shell
        self._web_mode = (shell is None and web_url is not None)
        self._web_url = web_url
        self.active = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._duck_station_audio = False

        # Persistent mic stream (stays open the entire time the listener runs)
        self._mic = MicStream()

        # Sub-components — wired for the appropriate mode
        if self._web_mode:
            _log(f"Initializing in WEB mode → {web_url}")
            web_intro = WebIntrospector(web_url)
            self.introspector = web_intro
            self.dispatcher = WebCommandDispatcher(web_url, introspector=web_intro)
        else:
            _log("Initializing in TKINTER mode")
            self.introspector = UIIntrospector(shell)
            self.dispatcher = CommandDispatcher(shell)

        # Game dispatcher — direct channel to FTB on port 7555 (independent
        # of the runtime dispatcher).  Created eagerly; it's cheap.
        acli_cfg = _load_audio_cli_config()
        self._game_port: int = int(acli_cfg.get("game_port", 7555))
        self.game_dispatcher = GameCommandDispatcher(game_port=self._game_port)
        _log(f"Game dispatcher → port {self._game_port}")

        # Active context: "runtime" (station/shell control via 7800) or
        # "game" (direct FTB control via 7555).
        self._context: str = self.CONTEXT_RUNTIME

        self.stt = STTEngine()
        self.narration = NarrationEngine(
            mic=self._mic,
            on_speaking_change=self._write_speaking_flag,
        )
        self.parser = CommandParser()

        # State
        self._last_interaction_ts = 0.0
        self._session_ui_state: Dict[str, Any] = {}

        # Audio output mode — "speaker" disables barge-in to prevent self-
        # interruption on speakers; "headphone" allows barge-in.
        self._audio_mode: str = acli_cfg.get("audio_output_mode", "speaker")
        self.narration.set_audio_mode(self._audio_mode)
        _log(f"Audio output mode: {self._audio_mode}")

        # Verbosity level — controls narration depth, not backend logic.
        self._verbosity: str = acli_cfg.get("verbosity", DEFAULT_VERBOSITY)
        if self._verbosity not in VERBOSITY_LEVELS:
            self._verbosity = DEFAULT_VERBOSITY
        _log(f"Verbosity level: {self._verbosity}")

        # Audio keyboard state
        self._audio_kb_active = False
        self._audio_kb_target = ""
        self._audio_kb_buffer = ""
        self._audio_kb_confirming = False  # True when waiting for yes/no confirmation
        self._audio_kb_just_spoke = False  # settle flag for speaker-mode capture

        # Speaker-mode settle flag for the main session listen cycle
        self._session_just_spoke = False

        # Audio persona — loaded when a station with a paired persona starts.
        # The persona reshapes narration style/voice; escape hatches remain
        # immutably owned by this class.
        self._persona: Optional[AudioPersonaBase] = None
        self._persona_name: str = ""

        # Discover available audio personas from plugins/meta/
        self._discover_personas()

        # Callbacks for shell integration
        self.on_session_start: Optional[Callable] = None
        self.on_session_end: Optional[Callable] = None
        self.on_status_change: Optional[Callable[[str], None]] = None

        # Callbacks for Flutter overlay — all fire-and-forget, never raise
        self.on_transcript_partial: Optional[Callable[[str], None]] = None
        self.on_transcript_final: Optional[Callable[[str], None]] = None
        self.on_llm_start: Optional[Callable] = None
        self.on_llm_response: Optional[Callable[[str], None]] = None

    # -------------------------------------------------------------------
    # Audio Persona management
    # -------------------------------------------------------------------
    def _discover_personas(self) -> None:
        """Scan plugins/meta/ for audio personas at startup."""
        # Determine plugins dir relative to this file or RADIO_OS_ROOT
        root = os.environ.get("RADIO_OS_ROOT", "")
        if not root:
            root = os.path.dirname(os.path.abspath(__file__))
        plugins_dir = os.environ.get("RADIO_OS_PLUGINS", os.path.join(root, "plugins"))
        load_audio_personas(plugins_dir)

    def load_persona(self, name: str, ui_state: Optional[Dict[str, Any]] = None) -> str:
        """
        Activate an audio persona by name.

        Args:
            name:     Persona name (e.g. "ok_narrator_plugin", "oracle_kingdom").
            ui_state: Current UI state (optional, used for context).

        Returns:
            Narration string confirming the activation.
        """
        name_lower = name.strip().lower()
        if not AUDIO_PERSONA_REGISTRY.has(name_lower):
            avail = AUDIO_PERSONA_REGISTRY.available()
            return (f"No audio persona '{name}' found. "
                    f"Available: {', '.join(avail) if avail else 'none'}.")

        # Build context for persona initialization
        ctx: Dict[str, Any] = {
            "station_id": "",
            "station_name": "",
            "meta_plugin": name_lower,
            "verbosity": self._verbosity,
            "audio_mode": self._audio_mode,
            "context": self._context,
            "game_state": (ui_state or {}).get("game_state"),
        }

        # Try to extract station info from UI state
        if ui_state:
            station = ui_state.get("station", {})
            if station:
                ctx["station_id"] = station.get("id", "")
                ctx["station_name"] = station.get("name", "")

        try:
            persona = AUDIO_PERSONA_REGISTRY.load(name_lower, ctx)
            self._persona = persona
            self._persona_name = name_lower

            # Merge persona phrase hints into STT
            hints = persona.get_phrase_hints()
            if hints:
                try:
                    self.stt.add_hints(hints)
                except AttributeError:
                    pass  # STT engine may not support dynamic hints

            display = persona.get_display_name()
            _log(f"Audio persona activated: {display}")
            return f"Persona activated: {display}. Voice navigation is now in character."

        except Exception as e:
            _log(f"Failed to load persona '{name}': {e}")
            return f"Failed to activate persona: {e}"

    def unload_persona(self) -> str:
        """Deactivate the current persona, restoring default Audio CLI voice."""
        if self._persona is None:
            return "No persona is active. Already using default voice."

        old_name = self._persona_name
        try:
            self._persona.shutdown()
        except Exception as e:
            _log(f"Error shutting down persona '{old_name}': {e}")

        self._persona = None
        self._persona_name = ""
        AUDIO_PERSONA_REGISTRY.unload()
        _log(f"Audio persona deactivated: {old_name}")
        return f"Persona '{old_name}' deactivated. Default radio voice restored."

    def _try_auto_load_persona(self, ui_state: Dict[str, Any]) -> None:
        """
        After a station starts, check if it has a paired audio persona
        and auto-load it.

        The mapping is: station manifest "meta_plugin" value → persona name.
        For example, a station with meta_plugin="oracle_kingdom" will look
        for an audio persona registered as "ok_narrator_plugin" or
        "oracle_kingdom".

        Also tries common name variations (underscored, hyphenated, etc.).
        """
        # Get the meta_plugin name from the current station info
        meta_plugin = ""

        # Try from station info in UI state
        stations = ui_state.get("stations") or []
        for st in stations:
            if st.get("running"):
                meta_plugin = st.get("meta_plugin", "")
                break

        if not meta_plugin:
            # Try from station manifest
            station = ui_state.get("station") or {}
            meta_plugin = station.get("meta_plugin", "")

        if not meta_plugin or meta_plugin == "radio_station":
            # Default radio station doesn't need a persona
            return

        # Try to find a matching persona — try several name patterns
        meta_lower = meta_plugin.strip().lower()
        candidates = [
            meta_lower,
            meta_lower.replace(" ", "_"),
            meta_lower.replace("-", "_"),
            f"{meta_lower}_narrator_plugin",
        ]

        # Also try the meta plugin module name variations
        # e.g. "oracle kingdom" → "ok_narrator_plugin"
        words = meta_lower.split("_")
        if len(words) >= 2:
            initials = "".join(w[0] for w in words if w)
            candidates.append(f"{initials}_narrator_plugin")

        for name in candidates:
            if AUDIO_PERSONA_REGISTRY.has(name):
                result = self.load_persona(name, ui_state)
                _log(f"Auto-loaded persona '{name}' for meta_plugin '{meta_plugin}': {result}")
                return

        _log(f"No audio persona found for meta_plugin '{meta_plugin}' "
             f"(tried: {candidates})")

    @property
    def persona(self) -> Optional[AudioPersonaBase]:
        """The active audio persona, or None."""
        return self._persona

    @property
    def persona_name(self) -> str:
        """Name of the active persona, or ''."""
        return self._persona_name

    @property
    def is_active(self) -> bool:
        return self.active

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start_listener(self) -> None:
        """Start the background mic listener thread."""
        if self.is_running:
            return
        if not HAS_SD:
            _log("sounddevice not available — Audio CLI disabled.")
            return

        # Open persistent mic stream ONCE
        self._mic.open()

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._listener_loop,
            name="AudioCLI-Listener",
            daemon=True,
        )
        self._thread.start()
        _log("Mic listener started. Say 'Hey Radio' to activate.")

    def stop_listener(self) -> None:
        """Stop the background mic listener thread."""
        self._stop_event.set()
        if self.active:
            self._end_session()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        # Close persistent mic stream
        self._mic.close()
        _log("Mic listener stopped.")

    def toggle(self) -> None:
        """Toggle the listener on/off."""
        if self.is_running:
            self.stop_listener()
        else:
            self.start_listener()

    def force_activate(self) -> None:
        """Manually activate session (e.g. from button press)."""
        if not self.is_running:
            self.start_listener()
        if not self.active:
            self._begin_session()

    # -----------------------------------------------------------------------
    # Verbosity control
    # -----------------------------------------------------------------------
    @property
    def verbosity(self) -> str:
        """Return current verbosity level."""
        return self._verbosity

    def set_verbosity(self, level: str) -> str:
        """
        Switch verbosity level.  Persists to global config.
        Returns a narration string confirming the change.

        This only affects response formatting — never backend logic.
        """
        level = level.strip().lower()
        if level not in VERBOSITY_LEVELS:
            return (f"Unknown verbosity level '{level}'. "
                    f"Available levels: {', '.join(VERBOSITY_LEVELS)}.")

        if level == self._verbosity:
            return f"Already at {level} verbosity."

        old = self._verbosity
        self._verbosity = level

        # Persist to config
        try:
            import platform
            if platform.system() == "Windows":
                cfg_dir = os.path.join(
                    os.environ.get("APPDATA", os.path.expanduser("~")), "RadioOS")
            else:
                cfg_dir = os.path.expanduser("~/.radioOS")
            cfg_path = os.path.join(cfg_dir, "config.json")
            os.makedirs(cfg_dir, exist_ok=True)
            full_cfg: dict = {}
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    full_cfg = json.load(f)
            full_cfg.setdefault("audio_cli", {})["verbosity"] = level
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(full_cfg, f, indent=2)
        except Exception as e:
            _log(f"Failed to persist verbosity: {e}")

        _log(f"Verbosity: {old} → {level}")

        descriptions = {
            "minimal": "Minimal mode. Short confirmations only.",
            "concise": "Concise mode. Efficient single-sentence responses.",
            "standard": "Standard mode. Informative with light analysis.",
            "broadcast": "Broadcast mode. Immersive narrative responses.",
            "diagnostic": "Diagnostic mode. Structured state summaries.",
        }
        return descriptions.get(level, f"Verbosity set to {level}.")

    # -----------------------------------------------------------------------
    # Mode switching (tkinter ↔ web)
    # -----------------------------------------------------------------------
    def _handle_bluetooth_command(self, transcript: str) -> Optional[str]:
        """
        Intercept bluetooth voice commands and execute them directly via
        bluetoothctl, bypassing the LLM entirely.

        Returns a spoken response string if the transcript matched a bluetooth
        command, or None if it did not match (caller should pass to LLM).

        Supported phrases (case-insensitive, punctuation-tolerant):
          • "scan [for] [bluetooth] [devices]" — 10s scan, read new devices found
          • "list bluetooth [devices]"          — read out all known devices
          • "bluetooth devices"                 — same
          • "connect [to] [my] <name>"          — connect a paired device by name
          • "disconnect [bluetooth | <name>]"   — disconnect current or named
          • "pair [with] <name>"                — pair a nearby device by name
        """
        import re as _re
        import subprocess as _sp
        import threading as _th

        t = _re.sub(r"[^\w\s]", "", transcript.lower()).strip()

        def _run_bt(*args: str, timeout: int = 20) -> str:
            try:
                result = _sp.run(
                    ["bluetoothctl", *args],
                    capture_output=True, text=True, timeout=timeout,
                )
                return (result.stdout + result.stderr).strip()
            except Exception as exc:
                return str(exc)

        def _known_devices() -> list:
            """Return list of (mac, name) tuples from 'bluetoothctl devices'."""
            raw = _run_bt("devices", timeout=5)
            devices = []
            for line in raw.splitlines():
                parts = line.strip().split(" ", 2)
                if len(parts) == 3 and parts[0] == "Device":
                    devices.append((parts[1], parts[2]))
            return devices

        def _scan_devices(duration: int = 10) -> list:
            """
            Enable discovery for `duration` seconds then return all newly
            visible devices (all devices seen after scan, minus those known
            before).  Runs bluetoothctl scan on/off via a timed subprocess.
            """
            before = {mac for mac, _ in _known_devices()}

            # 'bluetoothctl --timeout N scan on' scans for N seconds then exits
            try:
                _sp.run(
                    ["bluetoothctl", "--timeout", str(duration), "scan", "on"],
                    capture_output=True, text=True,
                    timeout=duration + 5,
                )
            except Exception:
                pass

            after = _known_devices()
            # Return devices that weren't in the before-set (newly discovered)
            new = [(mac, name) for mac, name in after if mac not in before]
            # Also return all visible devices (for "what did you find")
            return after, new

        def _find_device(query: str) -> Optional[tuple]:
            """Fuzzy-match a device name from known devices."""
            query = query.strip().lower()
            if not query:
                return None
            devices = _known_devices()
            for mac, name in devices:
                if query == name.lower():
                    return (mac, name)
            for mac, name in devices:
                if query in name.lower() or name.lower() in query:
                    return (mac, name)
            return None

        def _route_audio_to_bluetooth(mac: str, device_name: str) -> None:
            """
            After a successful bluetooth connect, set the device as the
            default PulseAudio/PipeWire sink and move all existing streams
            to it.  Works on both PulseAudio and PipeWire-pulse stacks.
            The MAC address is normalised to underscores for pactl sink names.
            """
            import time as _time
            # Give bluez a moment to register the sink with pulseaudio
            _time.sleep(2)
            mac_under = mac.replace(":", "_")
            try:
                # List sinks and find one whose name contains the MAC
                result = _sp.run(
                    ["pactl", "list", "short", "sinks"],
                    capture_output=True, text=True, timeout=8,
                )
                sink_name = None
                for line in result.stdout.splitlines():
                    if mac_under.lower() in line.lower() or "bluez" in line.lower():
                        parts = line.split()
                        if len(parts) >= 2:
                            sink_name = parts[1]
                            break

                if not sink_name:
                    _log(f"Bluetooth audio routing: no sink found for {mac} yet, trying bluez pattern")
                    # Fallback: just use the bluez sink pattern directly
                    sink_name = f"bluez_sink.{mac_under}.a2dp_sink"

                _log(f"Bluetooth audio routing: setting default sink to {sink_name}")
                _sp.run(["pactl", "set-default-sink", sink_name],
                        capture_output=True, timeout=5)

                # Move all currently playing sink-inputs to the new sink
                inputs = _sp.run(
                    ["pactl", "list", "short", "sink-inputs"],
                    capture_output=True, text=True, timeout=5,
                )
                for line in inputs.stdout.splitlines():
                    parts = line.split()
                    if parts:
                        _sp.run(
                            ["pactl", "move-sink-input", parts[0], sink_name],
                            capture_output=True, timeout=5,
                        )
                _log(f"Bluetooth audio routing: done → {sink_name}")
            except Exception as exc:
                _log(f"Bluetooth audio routing failed (non-fatal): {exc}")

        # ── scan ─────────────────────────────────────────────────────────
        if _re.search(
            r"\bscan\b(?:\s+(?:for|bluetooth|devices|nearby|new))*"
            r"|\bsearch\s+(?:for\s+)?(?:bluetooth|devices|nearby)\b",
            t,
        ):
            scan_sec = 10
            _log(f"Bluetooth: scanning for {scan_sec}s...")
            self.narration.speak(f"Scanning for Bluetooth devices, please wait {scan_sec} seconds.")
            self._session_just_spoke = True

            all_devs, new_devs = _scan_devices(scan_sec)

            if not all_devs:
                return "Scan complete. No Bluetooth devices found nearby."
            if new_devs:
                names = ", ".join(name for _, name in new_devs)
                return (
                    f"Scan complete. Found {len(new_devs)} new device"
                    f"{'s' if len(new_devs) != 1 else ''}: {names}. "
                    "Say 'pair with' and the device name to pair."
                )
            else:
                names = ", ".join(name for _, name in all_devs)
                return f"Scan complete. No new devices found. Known devices: {names}."

        # ── list devices ─────────────────────────────────────────────────
        if _re.search(
            r"\b(list|show)\b.*\bbluetooth\b"
            r"|\bbluetooth\b.*\bdevices\b"
            r"|\bpaired devices\b"
            r"|\bwhat\b.*\bbluetooth\b",
            t,
        ):
            devices = _known_devices()
            if not devices:
                return "No Bluetooth devices found. Say 'scan for bluetooth devices' to search."
            names = ", ".join(name for _, name in devices)
            return f"Known Bluetooth devices: {names}."

        # ── connect ───────────────────────────────────────────────────────
        m = _re.search(r"\bconnect\b(?:\s+(?:to|my))?\s+(.+)", t)
        if m:
            query = m.group(1).strip()
            device = _find_device(query)
            if not device:
                return (
                    f"I couldn't find a paired device matching '{query}'. "
                    "Try 'scan for bluetooth devices' to find new ones, "
                    "or 'list bluetooth devices' to see what's already paired."
                )
            mac, name = device
            _log(f"Bluetooth: connecting {name} ({mac})")
            out = _run_bt("connect", mac, timeout=20)
            if "successful" in out.lower() or "connected" in out.lower():
                # Route PulseAudio/PipeWire output to the new bluetooth sink
                _route_audio_to_bluetooth(mac, name)
                return f"Connected to {name}. Audio is now routed to {name}."
            else:
                return f"Couldn't connect to {name}. Make sure it's powered on and in range."

        # ── disconnect ────────────────────────────────────────────────────
        m = _re.search(r"\bdisconnect\b(?:\s+(.+))?", t)
        if m:
            query = (m.group(1) or "").strip()
            if query and query not in ("bluetooth", "all"):
                device = _find_device(query)
                if not device:
                    return f"I couldn't find a device matching '{query}'."
                mac, name = device
                _run_bt("disconnect", mac, timeout=10)
                return f"Disconnected {name}."
            else:
                devices = _known_devices()
                disconnected = []
                for mac, name in devices:
                    info = _run_bt("info", mac, timeout=5)
                    if "connected: yes" in info.lower():
                        _run_bt("disconnect", mac, timeout=10)
                        disconnected.append(name)
                if disconnected:
                    return f"Disconnected: {', '.join(disconnected)}."
                return "No Bluetooth devices are currently connected."

        # ── pair ──────────────────────────────────────────────────────────
        m = _re.search(r"\bpair\b(?:\s+(?:with|to|my))?\s+(.+)", t)
        if m:
            query = m.group(1).strip()
            device = _find_device(query)
            if device:
                mac, name = device
                out = _run_bt("pair", mac, timeout=30)
                if "already paired" in out.lower() or "successful" in out.lower():
                    return f"{name} is already paired. Say 'connect {name}' to connect it."
                return f"Pairing {name}... check your device for a confirmation prompt."
            return (
                f"I don't see a device named '{query}' yet. "
                "Say 'scan for bluetooth devices' first so I can find it."
            )

        # Not a bluetooth command
        return None

    # ──────────────────────────────────────────────────────────────────────
    def _handle_audio_device_command(self, transcript: str) -> Optional[str]:
        """
        Intercept audio-output / sound-device voice commands and execute
        them directly via pactl, bypassing the LLM entirely.

        Returns a spoken response string if matched, or None if not.

        Supported phrases (case-insensitive, punctuation-tolerant):
          • "list audio devices" / "list sound devices" / "what audio devices"
            "what output devices" / "show audio devices"
          • "set audio device <keyword>"  e.g. "set audio device hdmi"
          • "use <keyword> [audio | sound | output | speaker]"
          • "switch [audio | sound | output] to <keyword>"
          • "route audio to <keyword>"
          • "play [audio | sound | music] [on | through | via | to] <keyword>"
        """
        import re as _re
        import subprocess as _sp

        t = _re.sub(r"[^\w\s]", "", transcript.lower()).strip()

        # ── pactl helpers ────────────────────────────────────────────────

        def _pactl(*args: str, timeout: int = 8) -> str:
            try:
                r = _sp.run(["pactl", *args], capture_output=True, text=True, timeout=timeout)
                return (r.stdout + r.stderr).strip()
            except Exception as exc:
                return str(exc)

        def _list_sinks() -> list[dict]:
            """Return list of dicts with name, description, is_default, is_bluetooth."""
            short = _pactl("list", "short", "sinks")
            default = _pactl("get-default-sink").strip()

            # Get human-readable descriptions from verbose output
            descriptions: dict[str, str] = {}
            verbose = _pactl("list", "sinks")
            current_name = None
            for line in verbose.splitlines():
                line = line.strip()
                if line.startswith("Name:"):
                    current_name = line.split(":", 1)[1].strip()
                elif line.startswith("Description:") and current_name:
                    descriptions[current_name] = line.split(":", 1)[1].strip()

            sinks = []
            for line in short.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[1]
                    sinks.append({
                        "name": name,
                        "desc": descriptions.get(name, name),
                        "is_default": (name == default),
                        "is_bluetooth": ("bluez" in name.lower()),
                    })
            return sinks

        def _set_sink(sink_name: str) -> None:
            """Set default sink and move all active streams."""
            _pactl("set-default-sink", sink_name)
            inputs_raw = _pactl("list", "short", "sink-inputs")
            for line in inputs_raw.splitlines():
                parts = line.split()
                if parts:
                    _pactl("move-sink-input", parts[0], sink_name, timeout=5)

        def _find_sink(query: str, sinks: list[dict]) -> Optional[dict]:
            """Case-insensitive fuzzy match on name or description."""
            q = query.strip().lower()
            if not q:
                return None
            # Exact description match
            for s in sinks:
                if q == s["desc"].lower():
                    return s
            # Exact name match
            for s in sinks:
                if q == s["name"].lower():
                    return s
            # Substring match on description (most useful — "hdmi", "soundbar", "usb")
            for s in sinks:
                if q in s["desc"].lower() or q in s["name"].lower():
                    return s
            # Any single word of the query matches the description
            for word in q.split():
                if len(word) < 3:
                    continue
                for s in sinks:
                    if word in s["desc"].lower() or word in s["name"].lower():
                        return s
            return None

        # ── list audio devices ────────────────────────────────────────────
        if _re.search(
            r"\b(list|show|what|which)\b.{0,20}\b(audio|sound|output|speaker)\b.{0,20}\bdevice"
            r"|\b(audio|sound|output)\b.{0,20}\bdevice.{0,10}\b(list|available|do i have|are there)"
            r"|\bwhat.{0,10}(can i|output|sound|audio)",
            t,
        ):
            sinks = _list_sinks()
            if not sinks:
                return "I couldn't find any audio output devices."
            parts = []
            for s in sinks:
                label = s["desc"]
                if s["is_default"]:
                    label += " (currently active)"
                if s["is_bluetooth"]:
                    label += " via Bluetooth"
                parts.append(label)
            return f"Available audio output devices: {', '.join(parts)}."

        # ── set / switch / use / route / play on ──────────────────────────
        m = (
            _re.search(r"\b(?:set|change)\b.{0,15}\b(?:audio|sound|output)?\b.{0,10}\bdevice\b.{0,5}\bto\b\s+(.+)", t)
            or _re.search(r"\b(?:set|change)\b.{0,15}\b(?:audio|sound|output)\b.{0,10}\bto\b\s+(.+)", t)
            or _re.search(r"\buse\b\s+(.+?)\s+(?:audio|sound|output|speaker|device|for audio|for sound)\b", t)
            or _re.search(r"\buse\b\s+(?:the\s+)?(.+?)\s+(?:as|for)\b.{0,15}\b(?:audio|sound|output)\b", t)
            or _re.search(r"\bswitch\b.{0,20}\bto\b\s+(.+)", t)
            or _re.search(r"\broute\b.{0,15}\baudio\b.{0,10}\bto\b\s+(.+)", t)
            or _re.search(r"\bplay\b.{0,20}\b(?:on|through|via|to)\b\s+(.+)", t)
        )
        if m:
            query = m.group(1).strip()
            # Strip filler words at the end
            query = _re.sub(r"\b(please|now|instead|output|audio|sound|device|speaker)s?\b", "", query).strip()
            if not query:
                return None  # too vague, let LLM handle
            sinks = _list_sinks()
            if not sinks:
                return "I couldn't reach the audio system right now."
            sink = _find_sink(query, sinks)
            if not sink:
                names = ", ".join(s["desc"] for s in sinks)
                return (
                    f"I couldn't find an audio device matching '{query}'. "
                    f"Available devices: {names}. "
                    "Say 'list audio devices' to hear them again."
                )
            if sink["is_default"]:
                return f"{sink['desc']} is already the active audio output."
            _set_sink(sink["name"])
            return f"Done. Audio output is now set to {sink['desc']}."

        # Not an audio device command
        return None

    @property
    def current_mode(self) -> str:
        """Return 'web' or 'tkinter'."""
        return "web" if self._web_mode else "tkinter"

    def _handle_switch_mode(self, target: str) -> str:
        """
        Handle a switch_mode action. Returns a narration string describing
        what happened.
        """
        target = target.strip().lower()

        if target in ("web", "web_server", "headless"):
            return self._switch_to_web()
        elif target in ("tkinter", "desktop", "app", "local"):
            return self._switch_to_tkinter()
        else:
            return f"Unknown mode: {target}. Available modes are web and tkinter."

    def _switch_to_web(self) -> str:
        """Switch from tkinter mode to web mode."""
        if self._web_mode:
            return f"Already in web mode, connected to {self._web_url}."

        # Need to discover the web server URL
        web_url = None

        # Try to get it from the shell's web server state
        if self.shell:
            try:
                ws_thread = getattr(self.shell, "_web_server_thread", None)
                if ws_thread and ws_thread.is_alive():
                    web_url = getattr(self.shell, "_web_server_url", None)
            except Exception:
                pass

        # Fallback: try the default port
        if not web_url:
            web_url = "http://127.0.0.1:7800"

        # Verify the web server is reachable
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{web_url}/api/health",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                health = json.loads(resp.read().decode("utf-8"))
                if health.get("status") != "ok":
                    return "Web server responded but is not healthy. Cannot switch."
        except Exception as e:
            return f"Cannot switch to web mode. Web server at {web_url} is not reachable. Start the server first."

        # Rewire components
        _log(f"Switching to WEB mode → {web_url}")
        self._web_mode = True
        self._web_url = web_url
        web_intro = WebIntrospector(web_url)
        self.introspector = web_intro
        self.dispatcher = WebCommandDispatcher(web_url, introspector=web_intro)
        return f"Switched to web mode. Now controlling RadioOS through the web server at {web_url}."

    def _switch_to_tkinter(self) -> str:
        """Switch from web mode to tkinter mode."""
        if not self._web_mode:
            return "Already in tkinter desktop mode."

        if not self.shell:
            return "Cannot switch to tkinter mode. Audio CLI was started in standalone web mode without a desktop shell. Restart Audio CLI from the desktop app to use tkinter mode."

        # Verify the shell is still alive
        try:
            _ = self.shell.root.winfo_exists()
        except Exception:
            return "Cannot switch to tkinter mode. The desktop shell window is no longer available."

        # Rewire components
        _log("Switching to TKINTER mode")
        self._web_mode = False
        self._web_url = None
        self.introspector = UIIntrospector(self.shell)
        self.dispatcher = CommandDispatcher(self.shell)
        return "Switched to tkinter desktop mode. Now controlling the desktop application directly."

    # -----------------------------------------------------------------------
    # Context switching (runtime ↔ game)
    # -----------------------------------------------------------------------
    @property
    def context(self) -> str:
        """Return 'runtime' or 'game'."""
        return self._context

    def _handle_switch_context(self, target: str) -> str:
        """
        Switch between runtime (7800) and game (7555) contexts.
        Returns a narration string.
        """
        target = target.strip().lower()

        if target in ("game", "ftb", "backmarker", "from the backmarker",
                       "game_controls", "game controls", "gameplay"):
            return self._switch_to_game_context()
        elif target in ("runtime", "settings", "station", "runtime_settings",
                         "runtime settings", "shell", "browser", "window",
                         "radio", "radio os"):
            return self._switch_to_runtime_context()
        else:
            return (f"Unknown context: {target}. "
                    "Say 'switch to game' or 'switch to runtime'.")

    def _switch_to_game_context(self) -> str:
        """Switch to game context — commands go directly to port 7555."""
        if self._context == self.CONTEXT_GAME:
            return f"Already in game context (port {self._game_port})."

        # Verify the game server is reachable
        if not self.game_dispatcher.is_reachable:
            return (f"Cannot switch to game context. "
                    f"Game server at port {self._game_port} is not reachable. "
                    "Start a station with the FTB plugin first.")

        self._context = self.CONTEXT_GAME
        _log(f"Context → GAME (port {self._game_port})")

        # Fetch and narrate the current game state
        gs = self.game_dispatcher.get_game_state()
        status = gs.get("status", "unknown")
        if status == "no_game":
            return ("Switched to game context. Direct connection to the game "
                    f"server on port {self._game_port}. "
                    "Main menu. Options: New Game or Load Game.")
        elif status == "running":
            date = gs.get("date", "")
            phase = gs.get("phase", "")
            team = gs.get("player_team", {}).get("name", "")
            return (f"Switched to game context. Direct connection on port "
                    f"{self._game_port}. Game running. {date}. Phase: {phase}. "
                    f"Team: {team}.")
        else:
            return (f"Switched to game context. Direct connection on port "
                    f"{self._game_port}. Game status: {status}.")

    def _switch_to_runtime_context(self) -> str:
        """Switch to runtime context — commands go to port 7800."""
        if self._context == self.CONTEXT_RUNTIME:
            return "Already in runtime context."

        self._context = self.CONTEXT_RUNTIME
        _log("Context → RUNTIME (port 7800)")
        return ("Switched to runtime context. Now controlling station "
                "management, settings, and plugin configuration through "
                "the runtime server.")

    def _handle_start_game(self, action: CLIAction) -> str:
        """
        Handle a 'start_game' action:  switch to game context AND send
        new_game or load_game to the game server.
        """
        command = action.params.get("command", "new_game")

        # Verify the game server is reachable
        if not self.game_dispatcher.is_reachable:
            return (f"Cannot start game. Game server at port {self._game_port} "
                    "is not reachable. Start a station with the FTB plugin first.")

        # Switch context to game
        self._context = self.CONTEXT_GAME
        _log(f"Context → GAME via start_game ({command})")

        # Execute the start command
        start_action = CLIAction(type="start_game", target="",
                                 params={"command": command})
        results = self.game_dispatcher.execute([start_action])
        result_text = results[0] if results else "Command sent."

        return (f"Switched to game context (port {self._game_port}). "
                f"{result_text}")

    # -----------------------------------------------------------------------
    # Audio output mode (speaker ↔ headphone)
    # -----------------------------------------------------------------------
    @property
    def audio_mode(self) -> str:
        """Return 'speaker' or 'headphone'."""
        return self._audio_mode

    def set_audio_mode(self, mode: str) -> str:
        """
        Switch between 'speaker' and 'headphone' audio output modes.
        Persists the choice to global config and updates the narration engine.
        Returns a narration string.
        """
        mode = mode.strip().lower()
        if mode not in ("speaker", "headphone"):
            return (f"Unknown audio mode '{mode}'. "
                    "Say 'speaker mode' or 'headphone mode'.")

        if mode == self._audio_mode:
            return f"Already in {mode} mode."

        self._audio_mode = mode
        self.narration.set_audio_mode(mode)

        # Persist to config
        try:
            cfg = _load_audio_cli_config()
            cfg["audio_output_mode"] = mode
            # Write back through the global config
            import platform
            if platform.system() == "Windows":
                cfg_dir = os.path.join(
                    os.environ.get("APPDATA", os.path.expanduser("~")), "RadioOS")
            else:
                cfg_dir = os.path.expanduser("~/.radioOS")
            cfg_path = os.path.join(cfg_dir, "config.json")
            os.makedirs(cfg_dir, exist_ok=True)
            full_cfg: dict = {}
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    full_cfg = json.load(f)
            full_cfg.setdefault("audio_cli", {})["audio_output_mode"] = mode
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(full_cfg, f, indent=2)
        except Exception as e:
            _log(f"Failed to persist audio mode: {e}")

        _log(f"Audio output mode → {mode}")
        if mode == "speaker":
            return ("Switched to speaker mode. Barge-in is disabled — "
                    "I'll finish speaking before listening for your next command.")
        else:
            return ("Switched to headphone mode. Barge-in is enabled — "
                    "you can interrupt me anytime by speaking.")

    # -----------------------------------------------------------------------
    # Core listener loop
    # -----------------------------------------------------------------------
    def _listener_loop(self) -> None:
        """Main loop: listen for wake phrase, then enter session mode."""
        while not self._stop_event.is_set():
            try:
                if not self.active:
                    self._wake_listen_cycle()
                else:
                    self._session_listen_cycle()
            except Exception as e:
                import traceback
                _log(f"Listener error: {e}\n{traceback.format_exc()}")
                time.sleep(1)

    def _wake_listen_cycle(self) -> None:
        """
        Listen for the wake phrase by reading from the persistent mic stream.

        We wait for a full stride of new audio, then grab a wider overlapping
        window from the ring buffer so the phrase is never split across two
        non-overlapping chunks.  The energy gate checks several sub-windows
        so a brief dip between syllables doesn't discard the whole chunk.
        """
        stride_sec = 1.0   # new audio per cycle (short → responsive)
        window_sec = 3.0   # total STT window (overlaps previous cycle)
        stride_samples = int(stride_sec * SAMPLE_RATE)

        # Block until a full stride of new samples has been recorded
        if not self._mic.wait_for_samples(stride_samples, timeout=stride_sec + 1.0):
            return
        if self._stop_event.is_set():
            return

        # Energy gate: check four 500 ms sub-windows spanning the last 2 s.
        # If *any* sub-window exceeds the threshold we run STT.
        # This prevents a brief inter-syllable dip from discarding the chunk.
        has_energy = False
        peak_rms = 0.0
        full_2s = self._mic.get_last_n_seconds(2.0)
        sub_len = int(0.5 * SAMPLE_RATE)
        for i in range(0, len(full_2s) - sub_len + 1, sub_len):
            sub = full_2s[i:i + sub_len]
            rms = float(np.sqrt(np.mean(sub ** 2)))
            peak_rms = max(peak_rms, rms)
            if rms >= SILENCE_THRESHOLD:
                has_energy = True
                break

        # Log mic level every cycle so user can verify audio is arriving
        if not hasattr(self, '_wake_log_counter'):
            self._wake_log_counter = 0
        self._wake_log_counter += 1
        # Print level every 5 cycles (~5 s) or whenever energy is detected
        if has_energy or self._wake_log_counter % 5 == 0:
            _log(f"Mic level: peak_rms={peak_rms:.5f}  threshold={SILENCE_THRESHOLD}  {'▶ SPEECH' if has_energy else '· silent'}")

        if not has_energy:
            return

        # Grab an overlapping window for STT
        audio = self._mic.get_last_n_seconds(window_sec)
        if audio is None or len(audio) == 0:
            _log("Wake: ring buffer returned empty audio — skipping.")
            return

        _log("Wake: speech detected, running STT...")
        transcript = self.stt.transcribe(audio)
        if not transcript:
            _log("Wake: STT returned empty transcript.")
            return

        transcript_lower = transcript.lower().strip()
        # Strip punctuation so "hey, radio." → "hey radio" still matches
        import re as _re
        transcript_clean = _re.sub(r"[^\w\s]", "", transcript_lower)
        _log(f"Wake check: '{transcript_lower}' (clean: '{transcript_clean}')")

        if WAKE_PHRASE in transcript_lower or WAKE_PHRASE in transcript_clean:
            self._begin_session()

    def _session_listen_cycle(self) -> None:
        """During active session: capture command, process, narrate."""
        # If audio keyboard is active, route to that state machine instead
        if self._audio_kb_active:
            self._audio_keyboard_listen_cycle()
            return

        # After a speaker-mode speak() the ring buffer was drained — let it
        # refill before polling for speech.
        needs_settle = (self._session_just_spoke
                        and self.narration._speaker_mode)
        self._session_just_spoke = False

        # Wait for speech using the persistent stream
        audio = self._capture_until_silence(settle_after_speak=needs_settle)
        if audio is None or self._stop_event.is_set():
            return

        # Check minimum energy
        rms = np.sqrt(np.mean(audio ** 2))
        if rms < SILENCE_THRESHOLD:
            return

        self._last_interaction_ts = time.time()
        self._update_status("Transcribing...")

        transcript = self.stt.transcribe(audio)
        if not transcript:
            self._update_status("Listening...")
            return

        _log(f"User said: '{transcript}'")

        # ── Flutter overlay: transcript finalised ──
        if self.on_transcript_final:
            try:
                self.on_transcript_final(transcript)
            except Exception:
                pass
        self._emit_flutter_event({"type": "transcript_final", "text": transcript})

        # Check for exit phrase — ESCAPE HATCH, never overridden by persona
        _t_clean = __import__("re").sub(r"[^\w\s]", "", transcript.lower().strip())
        if EXIT_PHRASE in transcript.lower().strip() or EXIT_PHRASE in _t_clean:
            # Mark inactive immediately so no silence-timeout or other
            # cycle can fire while the goodbye TTS plays.
            self.active = False

            # Persona farewell (themed) or default
            farewell = "Exiting Audio CLI."
            if self._persona:
                try:
                    custom = self._persona.get_farewell()
                    if custom:
                        farewell = custom
                except Exception:
                    pass

            exit_response = CLIResponse(
                actions=[],
                narration=farewell,
            )
            self.narration.speak(exit_response.narration)
            self._end_session()
            return

        # Check for persona escape hatch phrases — ALWAYS owned by audio_cli
        if self._persona and _is_escape_phrase(transcript.lower().strip()):
            result = self.unload_persona()
            self.narration.speak(result)
            self._session_just_spoke = True
            self._update_status("Listening...")
            return

        # ── Bluetooth voice commands — handled locally, no LLM needed ──
        _bt_result = self._handle_bluetooth_command(transcript)
        if _bt_result is not None:
            _log(f"Bluetooth command handled: {_bt_result}")
            self._emit_flutter_event({"type": "llm_response", "text": _bt_result})
            self.narration.speak(_bt_result)
            self._session_just_spoke = True
            self._update_status("Listening...")
            return

        # ── Audio device voice commands — handled locally, no LLM needed ──
        _audio_dev_result = self._handle_audio_device_command(transcript)
        if _audio_dev_result is not None:
            _log(f"Audio device command handled: {_audio_dev_result}")
            self._emit_flutter_event({"type": "llm_response", "text": _audio_dev_result})
            self.narration.speak(_audio_dev_result)
            self._session_just_spoke = True
            self._update_status("Listening...")
            return

        # Persona input preprocessing — runs AFTER escape hatches, BEFORE LLM.
        # The persona can map in-universe phrases to standard commands here
        # (e.g. "consult the ledger" → "show finance").
        if self._persona:
            try:
                caps = self._persona.get_capabilities()
                if caps.get("input_preprocessing"):
                    preprocessed = self._persona.preprocess_user_input(transcript)
                    if isinstance(preprocessed, str) and preprocessed:
                        transcript = preprocessed
            except Exception as e:
                _log(f"Persona input preprocessing error: {e}")

        # Get current UI state (thread-safe via queue)
        self._update_status("Processing...")
        ui_state = self._get_ui_state_safe()

        # Build persona system prompt overlay (if persona active)
        persona_overlay = ""
        if self._persona:
            try:
                persona_overlay = self._persona.get_system_prompt_overlay()
            except Exception as e:
                _log(f"Persona prompt overlay error: {e}")

        # Send to LLM
        # ── Flutter overlay: LLM is thinking ──
        if self.on_llm_start:
            try:
                self.on_llm_start()
            except Exception:
                pass
        self._emit_flutter_event({"type": "llm_thinking"})

        response = self.parser.parse(transcript, ui_state, persona_overlay)

        # ── Flutter overlay: LLM response ready ──
        if response.narration:
            if self.on_llm_response:
                try:
                    self.on_llm_response(response.narration)
                except Exception:
                    pass
            self._emit_flutter_event({"type": "llm_response", "text": response.narration})

        # Execute actions
        if response.actions:
            # ── Split session-level actions from dispatchable ones ──
            # Session-level types are intercepted here because they mutate
            # the session itself (context, mode, verbosity).  All other
            # actions are batched per-context and sent to the chaining-aware
            # dispatcher together.
            _SESSION_TYPES = {
                "switch_mode", "switch_context", "start_game",
                "set_audio_mode", "set_verbosity",
                "load_persona", "unload_persona",
            }

            session_results: List[str] = []
            remaining_actions: List[CLIAction] = []

            for act in response.actions:
                if act.type in _SESSION_TYPES:
                    if act.type == "switch_mode":
                        r = self._handle_switch_mode(act.target)
                    elif act.type == "switch_context":
                        r = self._handle_switch_context(act.target)
                    elif act.type == "start_game":
                        r = self._handle_start_game(act)
                    elif act.type == "set_audio_mode":
                        r = self.set_audio_mode(act.target or "")
                    elif act.type == "set_verbosity":
                        r = self.set_verbosity(act.target or "")
                    elif act.type == "load_persona":
                        r = self.load_persona(act.target or "", ui_state)
                    elif act.type == "unload_persona":
                        r = self.unload_persona()
                    else:
                        r = ""
                    _log(f"{act.type} → {r}")
                    if r:
                        session_results.append(r)
                else:
                    remaining_actions.append(act)

            # ── Execute remaining actions via chaining-aware dispatcher ──
            dispatch_results: List[str] = []
            if remaining_actions:
                if self._context == self.CONTEXT_GAME:
                    dispatch_results = self.game_dispatcher.execute(remaining_actions)
                    _log(f"Game chain executed ({len(remaining_actions)} steps): {dispatch_results}")
                else:
                    dispatch_results = self.dispatcher.execute(remaining_actions)
                    _log(f"Runtime chain executed ({len(remaining_actions)} steps): {dispatch_results}")

                # Check for audio keyboard activation signals
                kb_activated = False
                for r in dispatch_results:
                    if isinstance(r, str) and r.startswith("__AUDIO_KEYBOARD_ACTIVATE__:"):
                        field = r.split(":", 1)[1]
                        self._activate_audio_keyboard(field)
                        kb_activated = True

                # If audio keyboard just activated, it already spoke its own
                # prompt — skip the normal narration so we don't double-speak
                # over the keyboard instructions.
                if kb_activated:
                    self._session_just_spoke = True
                    return

                # ── Auto-load audio persona on station start ──
                # If one of the dispatched actions was "start", check whether
                # the started station has a paired audio persona and load it.
                started_station = False
                for act in remaining_actions:
                    if act.type == "start":
                        started_station = True
                        break
                if started_station:
                    self._try_auto_load_persona(ui_state)

            # ── Build narration from execution results ──
            # Filter out internal signals and "Waited X seconds" filler
            action_descriptions = [
                r for r in (session_results + dispatch_results)
                if isinstance(r, str)
                and not r.startswith("__")
                and not r.startswith("[skipped]")
                and not r.startswith("Waited ")
            ]
            if action_descriptions:
                response.narration = " ".join(action_descriptions)

            # Brief pause for UI to settle after the chain
            time.sleep(0.3)

            # Re-fetch UI state AFTER all actions so narration reflects the
            # new reality, not the pre-action snapshot.
            ui_state = self._get_ui_state_safe()

            # Refresh STT phrase hints with post-action state
            try:
                self.stt.update_hints_from_state(ui_state)
            except Exception:
                pass

        # Narrate (apply verbosity formatting + persona reshaping)
        if response.narration:
            self._update_status("Speaking...")
            formatted = format_response(
                response.narration,
                ui_state,
                self._verbosity,
                intent=transcript,
            )

            # Persona narration reshaping
            if self._persona:
                try:
                    formatted = self._persona.reshape_narration(
                        formatted, ui_state, self._verbosity
                    )
                except Exception:
                    pass

            self.narration.speak(formatted)
            self._session_just_spoke = True

        self._update_status("Listening...")

    # -----------------------------------------------------------------------
    # Audio Keyboard state machine
    # -----------------------------------------------------------------------
    def _activate_audio_keyboard(self, field: str) -> None:
        """Enter audio keyboard dictation mode."""
        self._audio_kb_active = True
        self._audio_kb_target = field
        self._audio_kb_buffer = ""
        self._audio_kb_confirming = False
        # Flag so the first listen cycle knows the mic needs settle time
        self._audio_kb_just_spoke = True
        _log(f"Audio keyboard ACTIVATED for field: {field}")
        self._update_status(f"Audio KB: {field}")
        self.narration.speak(
            f"Audio keyboard active for {field}. Speak your text. "
            "Say enter when done, clear text to start over, or cancel to back out."
        )

    def _deactivate_audio_keyboard(self, reason: str = "cancelled") -> None:
        """Exit audio keyboard mode."""
        self._audio_kb_active = False
        target = self._audio_kb_target
        self._audio_kb_target = ""
        self._audio_kb_buffer = ""
        self._audio_kb_confirming = False
        self._audio_kb_just_spoke = False
        _log(f"Audio keyboard DEACTIVATED ({reason}) for field: {target}")
        self._update_status("Listening...")

    def _audio_keyboard_listen_cycle(self) -> None:
        """
        Audio keyboard listen cycle — captures dictated text instead of
        sending speech to the LLM command parser.

        States:
          1. Dictating: all speech is appended to the buffer.
          2. Enter: user says "enter" — text is submitted immediately.
        """
        # Track whether we just spoke (speaker mode needs mic settle time).
        # The activation prompt sets the flag; we consume it here on first
        # cycle so that _capture_until_silence lets the buffer refill.
        just_spoke = self._audio_kb_just_spoke
        self._audio_kb_just_spoke = False

        # Capture speech — after a speaker-mode speak() we need to let the
        # ring buffer refill with real audio before checking for speech.
        needs_settle = just_spoke and self.narration._speaker_mode
        audio = self._capture_until_silence(settle_after_speak=needs_settle)
        if audio is None or self._stop_event.is_set():
            return

        rms = np.sqrt(np.mean(audio ** 2))
        if rms < SILENCE_THRESHOLD:
            return

        self._last_interaction_ts = time.time()
        self._update_status("Transcribing...")

        transcript = self.stt.transcribe(audio)
        if not transcript:
            self._update_status(f"Audio KB: {self._audio_kb_target}")
            return

        text_lower = transcript.lower().strip()
        _log(f"Audio KB heard: '{transcript}' (confirming={self._audio_kb_confirming})")

        # Always allow exit from keyboard
        _t_kb_clean = __import__("re").sub(r"[^\w\s]", "", text_lower)
        if EXIT_PHRASE in text_lower or EXIT_PHRASE in _t_kb_clean:
            self._deactivate_audio_keyboard("session exit")
            self.narration.speak("Audio keyboard cancelled. Exiting Audio CLI.")
            self._end_session()
            return

        # --- Dictation state ---
        # Check for control phrases
        cancel_phrases = ("cancel", "back out", "never mind", "exit keyboard",
                          "cancel keyboard", "stop keyboard")
        if any(p in text_lower for p in cancel_phrases):
            self._deactivate_audio_keyboard("cancelled")
            self.narration.speak("Audio keyboard cancelled.")
            self._update_status("Listening...")
            return

        enter_phrases = ("enter", "submit", "done", "send", "that's it",
                         "thats it", "finish", "finished")
        if any(p in text_lower for p in enter_phrases):
            if not self._audio_kb_buffer.strip():
                self.narration.speak("Nothing to submit. Speak your text first, then say enter.")
                self._audio_kb_just_spoke = True
                self._update_status(f"Audio KB: {self._audio_kb_target}")
                return
            # Submit immediately — no confirmation step needed
            final_text = self._audio_kb_buffer.strip()
            field = self._audio_kb_target
            _log(f"Audio KB SUBMIT: field={field} text='{final_text}'")
            self._deactivate_audio_keyboard("submitted")

            # Execute the input action with the text
            input_action = CLIAction(type="input", target=field,
                                     params={"text": final_text})
            submit_ok = False
            try:
                active_dispatcher = (self.game_dispatcher
                                     if self._context == self.CONTEXT_GAME
                                     else self.dispatcher)
                results = active_dispatcher.execute([input_action])
                _log(f"Audio KB input result: {results}")
                # Check if any result indicates success
                submit_ok = any("Set " in r for r in results) if results else False
            except Exception as e:
                _log(f"Audio KB input failed: {e}")

            if submit_ok:
                self.narration.speak(f"{field} set to {final_text}.")
            else:
                self.narration.speak(
                    f"Submitted {final_text} for {field}, but the server "
                    "may not have accepted it."
                )
            self._update_status("Listening...")
            return

        clear_phrases = ("clear", "clear all", "clear text", "clear the text",
                         "start over", "erase", "erase all", "erase text",
                         "delete all", "delete text", "wipe", "wipe text")
        if any(text_lower.strip() == p for p in clear_phrases):
            self._audio_kb_buffer = ""
            self.narration.speak("Text cleared. Speak your text.")
            self._audio_kb_just_spoke = True
            self._update_status(f"Audio KB: {self._audio_kb_target}")
            return

        # Append dictated text to buffer
        if self._audio_kb_buffer:
            self._audio_kb_buffer += " " + transcript.strip()
        else:
            self._audio_kb_buffer = transcript.strip()

        _log(f"Audio KB buffer: '{self._audio_kb_buffer}'")
        self._update_status(f"Audio KB: {self._audio_kb_target}")
        # Brief echo so the user knows what was captured
        self.narration.speak(f"{transcript.strip()}.")
        self._audio_kb_just_spoke = True

    def _handle_keyboard_confirmation(self, text_lower: str) -> None:
        """Handle the yes/no confirmation after the user says 'enter'."""
        confirm_phrases = ("yes", "confirm", "correct", "that's right",
                           "thats right", "yep", "yeah", "affirmative",
                           "right", "ok", "okay", "sure")
        deny_phrases = ("no", "wrong", "try again", "redo", "nope",
                        "incorrect", "not right", "nah")
        cancel_phrases = ("cancel", "back out", "never mind",
                          "exit keyboard", "stop")

        if any(p in text_lower for p in confirm_phrases):
            # Submit the text
            final_text = self._audio_kb_buffer.strip()
            field = self._audio_kb_target
            _log(f"Audio KB CONFIRMED: field={field} text='{final_text}'")
            self._deactivate_audio_keyboard("confirmed")

            # Execute the input action with the confirmed text
            input_action = CLIAction(type="input", target=field,
                                     params={"text": final_text})
            try:
                active_dispatcher = (self.game_dispatcher
                                     if self._context == self.CONTEXT_GAME
                                     else self.dispatcher)
                results = active_dispatcher.execute([input_action])
                _log(f"Audio KB input result: {results}")
            except Exception as e:
                _log(f"Audio KB input failed: {e}")

            self.narration.speak(
                f"Text submitted for {field}: {final_text}."
            )
            self._update_status("Listening...")
            return

        if any(p in text_lower for p in deny_phrases):
            # Clear and re-dictate
            self._audio_kb_buffer = ""
            self._audio_kb_confirming = False
            self.narration.speak("Cleared. Speak your text again.")
            self._audio_kb_just_spoke = True
            self._update_status(f"Audio KB: {self._audio_kb_target}")
            return

        if any(p in text_lower for p in cancel_phrases):
            self._deactivate_audio_keyboard("cancelled")
            self.narration.speak("Audio keyboard cancelled.")
            self._update_status("Listening...")
            return

        # Unrecognized — repeat the question
        self.narration.speak(
            f"You said: {self._audio_kb_buffer.strip()}. "
            "Say yes to confirm, no to try again, or cancel to exit."
        )
        self._audio_kb_just_spoke = True

    # -----------------------------------------------------------------------
    # Session lifecycle
    # -----------------------------------------------------------------------
    def _begin_session(self) -> None:
        """Activate the Audio CLI session."""
        self.active = True
        self._duck_station_audio = True
        self._last_interaction_ts = time.time()

        _log("Session ACTIVE — station audio ducked.")
        self._update_status("Audio CLI Active")

        if self.on_session_start:
            try:
                self.on_session_start()
            except Exception:
                pass

        self._emit_flutter_event({"type": "session_start"})

        # Signal station runtime to duck audio
        self._write_suppression_flag(True)

        # Get initial UI state and narrate
        ui_state = self._get_ui_state_safe()

        # Seed STT phrase hints with live station / game vocabulary
        try:
            self.stt.update_hints_from_state(ui_state)
        except Exception:
            pass

        # Merge persona phrase hints if active
        if self._persona:
            try:
                hints = self._persona.get_phrase_hints()
                if hints:
                    self.stt.add_hints(hints)
            except Exception:
                pass

        # Build greeting — persona can override
        persona_greeting = None
        if self._persona:
            try:
                persona_greeting = self._persona.get_greeting(ui_state)
            except Exception as e:
                _log(f"Persona greeting error: {e}")

        if persona_greeting:
            initial_narration = persona_greeting
        else:
            initial_narration = self._build_initial_narration(ui_state)

        formatted = format_response(initial_narration, ui_state, self._verbosity)

        # Persona narration reshaping
        if self._persona:
            try:
                formatted = self._persona.reshape_narration(
                    formatted, ui_state, self._verbosity
                )
            except Exception:
                pass

        self.narration.speak(formatted)
        self._session_just_spoke = True
        self._update_status("Listening...")

    def _end_session(self) -> None:
        """Deactivate the Audio CLI session."""
        self.active = False
        self._duck_station_audio = False

        # Reset audio keyboard state
        self._audio_kb_active = False
        self._audio_kb_target = ""
        self._audio_kb_buffer = ""
        self._audio_kb_confirming = False
        self._audio_kb_just_spoke = False
        self._session_just_spoke = False

        _log("Session ENDED — station audio restored to full volume.")
        self._update_status("Audio CLI Inactive")

        # Remove ducking flag — station audio returns to full volume
        self._write_suppression_flag(False)

        self._emit_flutter_event({"type": "session_end"})

        if self.on_session_end:
            try:
                self.on_session_end()
            except Exception:
                pass

    # -----------------------------------------------------------------------
    # Flutter event helpers (fire-and-forget, never raise)
    # -----------------------------------------------------------------------
    def _emit_flutter_event(self, event: Dict[str, Any]) -> None:
        """POST an event to the internal audio_cli broadcast endpoint.

        Runs in a daemon thread so it never blocks the voice pipeline.
        Silently swallowed on any error — Flutter overlay is best-effort.
        """
        def _send():
            try:
                import urllib.request
                data = json.dumps(event).encode()
                req = urllib.request.Request(
                    "http://127.0.0.1:7800/internal/audio_cli_event",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=1)
            except Exception:
                pass

        t = threading.Thread(target=_send, daemon=True)
        t.start()

    # -----------------------------------------------------------------------
    # Audio capture helpers (read from persistent MicStream)
    # -----------------------------------------------------------------------
    def _capture_until_silence(self, settle_after_speak: bool = False) -> Optional[np.ndarray]:
        """
        Monitor the persistent mic stream for speech followed by silence.
        Returns the audio segment containing the utterance, or None.
        The mic stays open the entire time — no open/close chatter.

        If *settle_after_speak* is True (should be set after a speaker-mode
        speak() call just drained the ring buffer), we wait for enough real
        audio to accumulate before we start the speech-detection loop so
        that current_rms() isn't diluted by leftover zeros.
        """
        if not self._mic.is_open:
            return None

        # After a speaker-mode speak(), the ring buffer was just drained.
        # Wait for at least 0.3 s of fresh samples so current_rms() has
        # real data to work with instead of averaging against zeros.
        if settle_after_speak:
            settle_samples = int(0.3 * SAMPLE_RATE)
            self._mic.wait_for_samples(settle_samples, timeout=1.0)

        poll_sec = 0.25                # check RMS every 250 ms
        max_polls = int(COMMAND_LISTEN_MAX_SEC / poll_sec)
        silence_polls_needed = int(SILENCE_DURATION_SEC / poll_sec)

        silence_count = 0
        has_speech = False
        speech_start_time: Optional[float] = None
        polls_since_speech = 0         # track how long we've been capturing speech

        for _ in range(max_polls):
            if self._stop_event.is_set():
                return None

            # Wait for the next batch of audio from the callback
            self._mic.wait_for_audio(timeout=poll_sec)

            # Use a shorter RMS window (0.15 s) right after a drain so we
            # aren't averaging the tiny fresh chunk against stale zeros.
            # After the first speech is detected the full window is fine.
            window = 0.15 if (settle_after_speak and not has_speech) else poll_sec
            rms = self._mic.current_rms(window_sec=window)

            if rms >= SILENCE_THRESHOLD:
                if not has_speech:
                    speech_start_time = time.time()
                    # ── KEY FIX: reset the countdown so the user gets the
                    # full COMMAND_LISTEN_MAX_SEC from the moment they START
                    # speaking, not from when the capture loop began waiting.
                    polls_since_speech = 0
                has_speech = True
                silence_count = 0
                polls_since_speech += 1
            else:
                silence_count += 1
                if has_speech:
                    polls_since_speech += 1
                if has_speech and silence_count >= silence_polls_needed:
                    # Don't cut off very short utterances — likely a fragment.
                    # Keep listening until we have at least MIN_UTTERANCE_SEC of
                    # speech so "start new game" isn't split into "start" + "new game".
                    elapsed = time.time() - (speech_start_time or time.time())
                    if elapsed >= MIN_UTTERANCE_SEC:
                        break
                    # Too short — reset silence counter and keep listening
                    silence_count = 0

            # Hard cap: once speech starts, allow up to COMMAND_LISTEN_MAX_SEC
            # of recording time (prevents infinite capture).
            if has_speech and polls_since_speech >= max_polls:
                break

        if not has_speech or speech_start_time is None:
            return None

        # Grab the full utterance from the ring buffer
        utterance_sec = time.time() - speech_start_time + 0.3  # small margin
        utterance_sec = min(utterance_sec, COMMAND_LISTEN_MAX_SEC)
        return self._mic.get_last_n_seconds(utterance_sec)

    # -----------------------------------------------------------------------
    # UI state access (thread-safe)
    # -----------------------------------------------------------------------
    def _get_ui_state_safe(self) -> Dict[str, Any]:
        """Get UI state — mode-aware (tkinter vs web)."""
        state: Dict[str, Any]
        if self._web_mode:
            # Web mode: introspector talks directly to REST API, no thread safety issue
            try:
                state = self.introspector.get_visible_state()
            except Exception as e:
                state = {"view": "unknown", "error": str(e)}
        else:
            # Tkinter mode: must schedule on main thread
            result_q: queue.Queue = queue.Queue()

            def _fetch():
                try:
                    s = self.introspector.get_visible_state()
                    result_q.put(s)
                except Exception as e:
                    result_q.put({"error": str(e), "view": "unknown"})

            try:
                self.shell.root.after(0, _fetch)
                state = result_q.get(timeout=3)
            except Exception:
                state = {"view": "unknown", "error": "timeout"}

        # Inject audio output mode so the LLM can report it
        state["audio_output_mode"] = self._audio_mode
        # Inject verbosity so the LLM adapts narration depth
        state["verbosity"] = self._verbosity
        # Inject active context so the LLM knows where commands will go
        state["active_context"] = self._context
        state["game_port"] = self._game_port

        # Inject active persona info so the LLM knows the voice character
        if self._persona:
            state["audio_persona"] = {
                "name": self._persona_name,
                "display_name": self._persona.get_display_name(),
                "description": self._persona.get_description(),
            }
        else:
            state["audio_persona"] = None

        # When in game context, always fetch fresh game state directly from
        # the game server (port 7555) instead of relying on the runtime's
        # proxied copy.  Also include it in runtime context if the game
        # server is reachable, so the LLM can answer game questions without
        # requiring a context switch.
        if self._context == self.CONTEXT_GAME:
            try:
                state["game_state"] = self.game_dispatcher.get_game_state()
            except Exception as e:
                import traceback
                _log(f"get_game_state() error: {e}\n{traceback.format_exc()}")
                state["game_state"] = {"status": "error", "error": str(e)}
        elif "game_state" not in state and self.game_dispatcher.is_reachable:
            # In runtime context but game is running — include full game
            # state so the LLM can answer questions about drivers, budget,
            # car, etc. without forcing the user to switch context first.
            try:
                state["game_state"] = self.game_dispatcher.get_game_state()
            except Exception:
                state["game_server_available"] = True

        return state

    # -----------------------------------------------------------------------
    # Narration builders
    # -----------------------------------------------------------------------
    def _narrate_game_state(self, gs: Dict[str, Any]) -> List[str]:
        """Build narration parts describing the current FTB game state.

        Returns a list of sentence strings that the caller appends to its
        narration ``parts`` list.  Used by both ``_build_initial_narration``
        and ``_build_state_narration`` so the game description is consistent
        and always placed prominently when the user is in game context.
        """
        parts: List[str] = []
        status = gs.get("status", "unknown")

        if status == "no_game":
            parts.append("Game: Main menu. Options: New Game or Load Game.")
            return parts

        if status == "error":
            parts.append(f"Game state unavailable: {gs.get('error', 'unknown error')}.")
            return parts

        if status != "running":
            parts.append(f"Game status: {status}.")
            return parts

        # ── Running game ──
        date = gs.get("date", "")
        phase = gs.get("phase", "")
        parts.append(f"Game running. {date}. Phase: {phase}.")

        # Player team
        pt = gs.get("player_team", {})
        if pt:
            parts.append(
                f"Team: {pt.get('name', '?')}, "
                f"Budget: {pt.get('budget', 0)}, "
                f"League: {pt.get('league', '?')}."
            )
            drivers = pt.get("drivers", [])
            if drivers:
                parts.append(f"Drivers: {', '.join(drivers[:4])}.")

        # UI screen / tab
        ui_screen = gs.get("ui_screen", {})
        if isinstance(ui_screen, dict):
            active_tab = ui_screen.get("active_tab", "")
            screen = ui_screen.get("screen", "")
            if active_tab:
                parts.append(f"Viewing: {active_tab} tab.")
            elif screen:
                parts.append(f"Screen: {screen}.")

        # Pending decisions
        decisions = gs.get("pending_decisions", [])
        if isinstance(decisions, list) and decisions:
            parts.append(
                f"{len(decisions)} decision{'s' if len(decisions) != 1 else ''} pending."
            )
            d = decisions[0]
            if isinstance(d, dict):
                parts.append(f"Decision: {d.get('prompt', '')[:150]}")
                opts = d.get("options", [])
                if isinstance(opts, list) and opts:
                    opt_labels = [
                        o.get("label", "?") for o in opts if isinstance(o, dict)
                    ]
                    parts.append(f"Options: {', '.join(opt_labels)}.")

        # Race day
        if gs.get("race_day_active"):
            rd = gs.get("race_day", {})
            parts.append(f"Race day active. Phase: {rd.get('phase', '?')}.")
            if rd.get("current_lap") and rd.get("total_laps"):
                parts.append(f"Lap {rd['current_lap']}/{rd['total_laps']}.")
            top5 = rd.get("top_5", [])
            if top5:
                leaders = ", ".join(
                    f"{s.get('driver', '?')} ({s.get('team', '?')})"
                    for s in top5[:3]
                )
                parts.append(f"Top 3: {leaders}.")

        # Recent events
        recent = gs.get("recent_events", [])
        if recent:
            if isinstance(recent[0], dict):
                last = recent[-1].get("desc", recent[-1].get("description", ""))
            else:
                last = str(recent[-1])
            if last:
                parts.append(f"Latest: {last[:120]}.")

        # Available actions
        actions = gs.get("available_actions", [])
        if isinstance(actions, list) and actions:
            parts.append(f"Available actions: {', '.join(actions[:8])}.")

        return parts

    def _build_initial_narration(self, ui_state: Dict[str, Any]) -> str:
        """Build the initial narration when session starts."""
        view = ui_state.get("view", "unknown")
        mode = ui_state.get("mode", "tkinter")
        parts = ["Audio CLI active."]

        # Report audio output mode
        audio_mode = ui_state.get("audio_output_mode", self._audio_mode)
        if audio_mode == "speaker":
            parts.append("Speaker mode — say 'switch to headphone mode' to enable interruption.")
        else:
            parts.append("Headphone mode — you can interrupt me anytime.")

        if mode == "web":
            parts.append("Connected to web server.")

        # Report active context
        ctx = ui_state.get("active_context", self._context)
        if ctx == self.CONTEXT_GAME:
            parts.append(f"Game context active — commands go directly to the game on port {self._game_port}.")
        else:
            parts.append("Runtime context active — controlling station management and settings.")

        if view == "disconnected":
            parts.append("Web server is unreachable. Check that the server is running.")
            return " ".join(parts)

        if view == "home":
            stations = ui_state.get("stations", [])
            parts.append(f"Station Browser. {len(stations)} station{'s' if len(stations) != 1 else ''} available.")
            for st in stations[:8]:
                sel = " Selected." if st.get("selected") else ""
                name = st.get("name", st.get("id", "Unknown"))
                detail_parts = [name]
                if st.get("category"):
                    detail_parts.append(st["category"])
                fc = st.get("feed_count") or st.get("feeds")
                if fc:
                    detail_parts.append(f"{fc} feeds")
                cc = st.get("character_count") or st.get("voices")
                if cc:
                    detail_parts.append(f"{cc} voices")
                if st.get("running"):
                    detail_parts.append("currently running")
                parts.append(f"{', '.join(detail_parts)}.{sel}")
            if len(stations) > 8:
                parts.append(f"And {len(stations) - 8} more.")
            available_plugins = ui_state.get("available_plugins", [])
            if available_plugins:
                parts.append(f"{len(available_plugins)} plugins available.")
            parts.append("Available actions: select a station, start a station, list plugins, open settings, or create a new station.")

        elif view == "runtime":
            # When in game context, lead with game state — not station runtime
            ctx = ui_state.get("active_context", self._context)
            gs = ui_state.get("game_state")

            if ctx == self.CONTEXT_GAME and gs:
                # Game context: describe the game, not the station runtime
                parts.extend(self._narrate_game_state(gs))
            else:
                # Runtime context: describe station, with game state as secondary info
                station = ui_state.get("station", {})
                name = station.get("name", "Unknown") if station else "Unknown"
                running = ui_state.get("station_running", False)
                parts.append(f"Station Runtime. {name}. {'Running' if running else 'Not running'}.")
                # Include feeds and characters if available
                feeds = ui_state.get("configured_feeds", [])
                chars = ui_state.get("configured_characters", [])
                if feeds:
                    parts.append(f"Active feeds: {', '.join(feeds[:5])}.")
                if chars:
                    parts.append(f"Characters: {', '.join(chars[:5])}.")
                # Plugin info
                station_feeds = ui_state.get("station_feeds", [])
                enabled_plugins = [f.get("display", f.get("name", "?")) for f in station_feeds if f.get("enabled")]
                if enabled_plugins:
                    parts.append(f"{len(enabled_plugins)} plugins active.")
                # Game state awareness (FTB) — secondary in runtime context
                if gs:
                    parts.extend(self._narrate_game_state(gs))
                else:
                    parts.append("Available actions: stop station, go back, list plugins, toggle feeds, send plugin commands, or ask about station status.")

        elif view == "settings":
            parts.append("Settings.")
            tabs = ui_state.get("tabs", [])
            if tabs:
                parts.append(f"Tabs available: {', '.join(tabs)}.")

        else:
            # Check for open dialog
            dialog = ui_state.get("dialog")
            if dialog:
                parts.append(f"Dialog open: {dialog.get('title', 'Unknown')}.")
                if dialog.get("tabs"):
                    active = dialog.get("active_tab", "")
                    parts.append(f"Settings tabs: {', '.join(dialog['tabs'])}. Currently on: {active}.")
            else:
                parts.append("Unknown view state.")

        return " ".join(parts)

    def _build_state_narration(self, ui_state: Dict[str, Any]) -> str:
        """Build a state-description narration (for silence timeout)."""
        view = ui_state.get("view", "unknown")
        ctx = ui_state.get("active_context", self._context)
        parts = []

        # Context reminder
        if ctx == self.CONTEXT_GAME:
            parts.append(f"Game context (port {self._game_port}).")
        else:
            parts.append("Runtime context.")

        if view == "home":
            stations = ui_state.get("stations", [])
            selected = ui_state.get("selected_index", 0)
            parts.append(f"Station Browser. {len(stations)} stations.")
            if stations and isinstance(selected, int) and selected < len(stations):
                st = stations[selected]
                name = st.get("name", st.get("id", "Unknown"))
                parts.append(f"Currently selected: {name}.")
                fc = st.get("feed_count") or st.get("feeds", 0)
                cc = st.get("character_count") or st.get("voices", 0)
                if fc:
                    parts.append(f"{fc} feeds active, {cc} voices.")
            parts.append("You can say: start a station, select a station, list plugins, open settings, or create a new station.")

        elif view == "runtime":
            # When in game context, lead with game state — not station runtime
            gs = ui_state.get("game_state")

            if ctx == self.CONTEXT_GAME and gs:
                # Game context: describe the game directly
                parts.extend(self._narrate_game_state(gs))
            else:
                # Runtime context: station info first, game secondary
                station = ui_state.get("station", {})
                name = station.get("name", "Unknown") if station else "Unknown"
                running = ui_state.get("station_running", False)
                parts.append(f"Station Runtime. {name}. {'Running' if running else 'Stopped'}.")

                # Status from parsed fields
                fields = ui_state.get("runtime_fields", {})
                if fields:
                    if "last_title" in fields:
                        parts.append(f"Last title: {fields['last_title']}.")
                    if "last_source" in fields:
                        parts.append(f"Source: {fields['last_source']}.")
                    if "heartbeat_age_sec" in fields:
                        parts.append(f"Heartbeat: {fields['heartbeat_age_sec']} seconds ago.")

                # Plugin state
                station_feeds = ui_state.get("station_feeds", [])
                enabled_plugins = [f.get("display", f.get("name", "?")) for f in station_feeds if f.get("enabled")]
                if enabled_plugins:
                    parts.append(f"{len(enabled_plugins)} plugins active: {', '.join(enabled_plugins[:5])}.")

                # Game state awareness (FTB) — secondary in runtime context
                if gs:
                    parts.extend(self._narrate_game_state(gs))
                else:
                    status = ui_state.get("status_text", "")
                    if status:
                        parts.append(f"Status: {status}.")
                    parts.append("You can say: stop, go back, list plugins, toggle feeds, send plugin commands, or ask about station status.")

        elif view == "settings":
            parts.append("Settings view.")
            tabs = ui_state.get("tabs", [])
            if tabs:
                parts.append(f"Available tabs: {', '.join(tabs)}.")
            parts.append("You can say: go back, or ask about a specific setting.")

        else:
            dialog = ui_state.get("dialog")
            if dialog:
                parts.append(f"{dialog.get('title', 'Dialog')} is open.")
                if dialog.get("active_tab"):
                    parts.append(f"On tab: {dialog['active_tab']}.")
            else:
                parts.append("Current location unclear.")
            parts.append("You can say: go home, close, or open settings.")

        return " ".join(parts)

    # -----------------------------------------------------------------------
    # Audio ducking signaling
    # -----------------------------------------------------------------------
    def _write_suppression_flag(self, active: bool) -> None:
        """
        Write a ducking flag file that the station runtime reads.
        When active=True, the session is active and station audio should
        duck when Audio CLI is speaking. The file also contains a
        'speaking' field that the NarrationEngine updates in real time.
        When active=False, the file is removed and station audio returns
        to full volume.
        """
        try:
            flag_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                ".audio_cli_suppress"
            )
            if active:
                with open(flag_path, "w") as f:
                    f.write(json.dumps({
                        "active": True,
                        "speaking": False,
                        "duck_volume": 0.20,
                        "ts": time.time(),
                        "pid": os.getpid(),
                    }))
            else:
                if os.path.exists(flag_path):
                    os.remove(flag_path)
        except Exception as e:
            _log(f"Ducking flag error: {e}")

    def _write_speaking_flag(self, speaking: bool) -> None:
        """
        Update the 'speaking' field in the ducking flag file.
        Called by NarrationEngine before/after speaking so the station
        runtime knows when to duck and when to restore volume.
        """
        try:
            flag_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                ".audio_cli_suppress"
            )
            if not os.path.exists(flag_path):
                return
            with open(flag_path, "r") as f:
                data = json.load(f)
            data["speaking"] = speaking
            data["ts"] = time.time()
            with open(flag_path, "w") as f:
                f.write(json.dumps(data))
        except Exception as e:
            _log(f"Speaking flag update error: {e}")

    # -----------------------------------------------------------------------
    # Status callbacks
    # -----------------------------------------------------------------------
    def _update_status(self, text: str) -> None:
        if self.on_status_change:
            try:
                self.on_status_change(text)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"{LOG_PREFIX} {ts} {msg}", flush=True)


# ---------------------------------------------------------------------------
# Standalone test entry
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Audio CLI — standalone test / web mode")
    ap.add_argument("--web", type=str, default="",
                    help="Run in web mode against this URL (e.g. http://127.0.0.1:7800)")
    ap.add_argument("--introspect", action="store_true",
                    help="Just print the introspected UI state and exit")
    ap.add_argument("--test-mic", action="store_true",
                    help="Test mic recording and STT")
    args = ap.parse_args()

    # ── Web introspection test ──
    if args.web and args.introspect:
        print(f"Audio CLI — web introspection → {args.web}")
        intro = WebIntrospector(args.web)
        state = intro.get_visible_state()
        print(json.dumps(state, indent=2, default=str))
        print("\nDone.")
        sys.exit(0)

    # ── Web mode full session ──
    if args.web:
        print(f"Audio CLI — web mode → {args.web}")
        print("Say 'Hey Radio' to activate, 'Thanks Radio' to exit.\n")
        session = AudioCLISession(shell=None, web_url=args.web)
        session.start_listener()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            session.stop_listener()
            print("\nStopped.")
        sys.exit(0)

    # ── Default: standalone test ──
    print("Audio CLI — standalone test mode")
    print("This module is designed to be integrated with shell_bookmark.py")
    print("  Tip: use --web URL to run in headless web mode")
    print("  Tip: use --web URL --introspect to dump web UI state")
    print()

    if args.test_mic or not args.web:
        print("Testing STT engine...")
        stt = STTEngine()
        narration = NarrationEngine()

        print(f"  whisper.cpp available: {stt._has_whisper}")
        print(f"  sounddevice available: {HAS_SD}")

        if HAS_SD:
            print("\nRecording 3 seconds via persistent MicStream... speak now!")
            try:
                mic = MicStream()
                mic.open()
                time.sleep(3)  # let the ring buffer fill
                audio = mic.get_last_n_seconds(3.0)
                mic.close()
                print(f"  Recorded {len(audio)} samples, RMS={np.sqrt(np.mean(audio**2)):.4f}")

                text = stt.transcribe(audio)
                print(f"  Transcript: '{text}'")

                if text:
                    print("\nPlaying narration response...")
                    narration.speak(f"You said: {text}")
            except Exception as e:
                print(f"  Error: {e}")

    print("\nDone.")
