#!/usr/bin/env python3
"""
oled_broadcast.py — RadioOS → OLED Soul Display runtime bridge.

Translates RadioOS runtime events (from event_q / direct calls) into
UDP JSON packets consumed by oled_soul_daemon.py.

Usage — inside a station or plugin:
    from tools.oled_broadcast import OledBroadcast
    oled = OledBroadcast()
    oled.on_listening_start()
    oled.on_llm_start()
    oled.on_tts_end()

Or attach it to the runtime event_q automatically:
    oled = OledBroadcast()
    oled.attach_to_runtime(runtime)

Plugin motion-profile auto-registration:
    Any meta-plugin module that exposes OLED_MOTION_PROFILE will have its
    profile registered when attach_to_runtime() or register_plugin_profiles()
    is called.  The daemon's station motif layer will then use the correct
    animation for that station.

Design notes:
  • All sends are fire-and-forget UDP — never blocks the caller.
  • Debounce on rapid amplitude feeds (mic / speech) to avoid UDP flood.
  • station_id is tracked internally; sent with station events.
"""

from __future__ import annotations

import importlib
import os
import sys
import threading
import time
from typing import Any, Dict, Optional

try:
    from tools.oled_event_client import send_oled_event, DEFAULT_UDP_HOST, DEFAULT_UDP_PORT
except Exception:
    try:
        from oled_event_client import send_oled_event, DEFAULT_UDP_HOST, DEFAULT_UDP_PORT  # type: ignore
    except Exception:
        # Absolute fallback — inline the minimal sender so this module is
        # always importable even in environments without the tools/ path.
        import json, socket as _socket

        DEFAULT_UDP_HOST = "127.0.0.1"
        DEFAULT_UDP_PORT = 5115

        def send_oled_event(
            event: Dict[str, Any],
            host: str = DEFAULT_UDP_HOST,
            port: int = DEFAULT_UDP_PORT,
        ) -> None:
            payload = json.dumps(event, separators=(",", ":")).encode("utf-8")
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            try:
                s.sendto(payload, (host, port))
            finally:
                s.close()


_AMPLITUDE_DEBOUNCE_S = 0.08   # minimum interval between amplitude events


class OledBroadcast:
    """Thin facade for sending structured OLED events from the RadioOS runtime.

    All methods are thread-safe and non-blocking (UDP fire-and-forget).
    """

    def __init__(
        self,
        host: str = DEFAULT_UDP_HOST,
        port: int = DEFAULT_UDP_PORT,
        station_id: str = "",
        enabled: bool = True,
    ) -> None:
        self._host       = host
        self._port       = port
        self._station_id = station_id
        self._enabled    = enabled
        self._lock       = threading.Lock()

        # Debounce timestamps for amplitude floods
        self._last_mic_send:    float = 0.0
        self._last_speech_send: float = 0.0

    # ── internal ──────────────────────────────────────────────────────────────

    def _send(self, event: Dict[str, Any]) -> None:
        if not self._enabled:
            return
        if self._station_id and "station_id" not in event:
            event = dict(event, station_id=self._station_id)
        try:
            send_oled_event(event, host=self._host, port=self._port)
        except Exception:
            pass  # never raise from non-blocking broadcast

    # ── station management ────────────────────────────────────────────────────

    def set_station(self, station_id: str) -> None:
        """Update the station_id included with all subsequent events."""
        with self._lock:
            self._station_id = station_id

    # ── Tier-0: power / system ────────────────────────────────────────────────

    def on_boot(self) -> None:
        self._send({"type": "boot"})

    def on_wake(self) -> None:
        self._send({"type": "wake"})

    def on_shutdown(self) -> None:
        self._send({"type": "shutdown"})

    def on_mute(self) -> None:
        self._send({"type": "muted"})

    def on_unmute(self) -> None:
        self._send({"type": "unmute"})

    def on_error(self, message: str = "") -> None:
        self._send({"type": "error", "message": message})

    def on_error_clear(self) -> None:
        self._send({"type": "clear_error"})

    # ── Tier-1: interaction mode ──────────────────────────────────────────────

    def on_wake_word(self) -> None:
        """User said the wake phrase — collapse animation then listening state."""
        self._send({"type": "wake_word_detected"})

    def on_listening_start(self) -> None:
        self._send({"type": "listening_start"})

    def on_listening_stop(self) -> None:
        self._send({"type": "listening_stop"})

    def on_mic_amplitude(self, value: float) -> None:
        """Feed live microphone amplitude (0.0–1.0) to the waveform ring.

        Debounced at ~12 Hz to avoid UDP saturation.
        """
        now = time.monotonic()
        if now - self._last_mic_send < _AMPLITUDE_DEBOUNCE_S:
            return
        self._last_mic_send = now
        self._send({"type": "mic_amplitude", "value": round(float(value), 3)})

    def on_llm_start(self) -> None:
        self._send({"type": "thinking_start"})

    def on_llm_end(self) -> None:
        self._send({"type": "thinking_end"})

    def on_tts_start(self) -> None:
        self._send({"type": "tts_start"})

    def on_tts_end(self) -> None:
        self._send({"type": "tts_end"})

    def on_speech_amplitude(self, value: float) -> None:
        """Feed TTS syllable envelope (0.0–1.0) to the ripple emission loop.

        Debounced at ~12 Hz.
        """
        now = time.monotonic()
        if now - self._last_speech_send < _AMPLITUDE_DEBOUNCE_S:
            return
        self._last_speech_send = now
        self._send({"type": "speech_amplitude", "value": round(float(value), 3)})

    # ── Tier-2: station lifecycle ──────────────────────────────────────────────

    def on_station_start(self, station_id: str = "") -> None:
        sid = station_id or self._station_id
        self._send({"type": "enter_station", "station_id": sid})

    def on_station_stop(self) -> None:
        self._send({"type": "exit_station"})

    def on_simulation_start(self) -> None:
        self._send({"type": "simulation_start"})

    # ── Navigation / UI ───────────────────────────────────────────────────────

    def on_confirm(self) -> None:
        self._send({"type": "confirm"})

    def on_transition(self) -> None:
        self._send({"type": "transition"})

    def on_volume_change(self, delta: int) -> None:
        self._send({"type": "volume_delta", "delta": int(delta)})

    def on_scroll_left(self) -> None:
        self._send({"type": "scroll_left"})

    def on_scroll_right(self) -> None:
        self._send({"type": "scroll_right"})

    # ── Runtime auto-attach ───────────────────────────────────────────────────

    def attach_to_runtime(self, runtime: Any) -> None:
        """Wire this broadcaster into a RadioOS runtime object.

        Looks for well-known attributes on the runtime:
          • runtime.event_q  — subscribes an event-listener thread
          • runtime.station_id — used as the initial station context

        Also calls register_plugin_profiles() to auto-load OLED_MOTION_PROFILE
        from all loaded meta-plugins.
        """
        if hasattr(runtime, "station_id"):
            self.set_station(getattr(runtime, "station_id", "") or "")

        self.register_plugin_profiles()

        if hasattr(runtime, "event_q") and runtime.event_q is not None:
            t = threading.Thread(
                target=self._event_q_listener,
                args=(runtime.event_q,),
                daemon=True,
                name="oled-broadcast-listener",
            )
            t.start()

    def _event_q_listener(self, q: Any) -> None:
        """Pull StationEvent objects off the queue and translate to OLED events."""
        import queue as _queue

        _EVENT_MAP: Dict[str, str] = {
            # (event.type or event.category) → oled event type
            "listening_start":     "listening_start",
            "listening_stop":      "listening_stop",
            "wake_word":           "wake_word_detected",
            "llm_start":           "thinking_start",
            "llm_end":             "thinking_end",
            "tts_start":           "tts_start",
            "tts_end":             "tts_end",
            "station_start":       "enter_station",
            "station_stop":        "exit_station",
            "simulation_start":    "simulation_start",
            "error":               "error",
            "recover":             "clear_error",
            "volume_up":           "volume_delta",
            "volume_down":         "volume_delta",
            "mute":                "muted",
            "unmute":              "unmute",
            "confirm":             "confirm",
            "transition":          "transition",
        }

        while True:
            try:
                event = q.get(timeout=1.0)
                if event is None:
                    break
                etype = getattr(event, "type", None) or getattr(event, "category", "")
                etype = str(etype).strip().lower().replace("-", "_")
                oled_type = _EVENT_MAP.get(etype)
                if oled_type:
                    payload: Dict[str, Any] = {"type": oled_type}
                    sid = getattr(event, "station_id", "") or self._station_id
                    if sid:
                        payload["station_id"] = sid
                    if oled_type == "volume_delta":
                        payload["delta"] = 1 if etype == "volume_up" else -1
                    self._send(payload)
                q.task_done()
            except _queue.Empty:
                continue
            except Exception:
                pass

    def register_plugin_profiles(self) -> None:
        """Scan loaded meta-plugin modules for OLED_MOTION_PROFILE and register them.

        Tries to import tools.oled_soul_daemon.register_station_motion_profile.
        Safe to call even when the daemon module is not loaded.
        """
        try:
            from tools.oled_soul_daemon import register_station_motion_profile
        except Exception:
            try:
                from oled_soul_daemon import register_station_motion_profile  # type: ignore
            except Exception:
                return  # daemon not importable in this env — skip silently

        _meta_modules = [
            "plugins.meta.ok_narrator_plugin",
            "plugins.meta.from_the_backmarker",
        ]
        for modname in _meta_modules:
            try:
                mod = importlib.import_module(modname)
                profile = getattr(mod, "OLED_MOTION_PROFILE", None)
                if isinstance(profile, dict) and "station_id" in profile:
                    register_station_motion_profile(profile["station_id"], profile)
            except Exception:
                pass

        # Also scan already-imported sys.modules for any module exposing OLED_MOTION_PROFILE
        for modname, mod in list(sys.modules.items()):
            if mod is None:
                continue
            profile = getattr(mod, "OLED_MOTION_PROFILE", None)
            if isinstance(profile, dict) and "station_id" in profile:
                try:
                    register_station_motion_profile(profile["station_id"], profile)
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Module-level singleton — import and use directly for zero-config wiring
# ---------------------------------------------------------------------------

_default: Optional[OledBroadcast] = None


def get_default(
    host: str = DEFAULT_UDP_HOST,
    port: int = DEFAULT_UDP_PORT,
) -> OledBroadcast:
    """Return (or lazily create) the module-level default broadcaster."""
    global _default
    if _default is None:
        _default = OledBroadcast(host=host, port=port)
    return _default
