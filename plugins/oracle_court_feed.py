"""
oracle_court_feed.py — Tick-driver for Oracle Kingdom narration pipeline.

This feed plugin bridges the gap between the Oracle Kingdom simulation
(oracle_kingdom.py OKController) and the Radio OS TTS pipeline (bookmark.py
producer → host → tts_worker).

Without this feed, the narrator meta plugin's process_input() is never called,
so the TTS pipeline stays dry (candidates=0 forever).

Architecture:
  1. Each tick, we call ACTIVE_META_PLUGIN.process_input({"input_type": "tick"})
  2. The meta plugin returns narration segments (text + voice + priority)
  3. We route those segments as candidates via runtime["emit_candidate"]
  4. The producer loop picks them up, host_loop scripts them, tts_worker speaks

The manifest entry should use `plugin: oracle_court_feed` to override the
default oracle_court plugin key (which has no feed_worker).
"""

from __future__ import annotations

import time
import threading
from typing import Any, Dict, List, Optional

PLUGIN_NAME = "oracle_court_feed"
PLUGIN_DESC = "Drives Oracle Kingdom narration ticks into the TTS pipeline"
IS_FEED = True

FEED_DEFAULTS = {
    "enabled": True,
    "tick_sec": 6.0,         # narration tick interval (seconds)
    "startup_delay": 8.0,    # wait for controller + court init before first tick
}
DEFAULT_FEED_CFG = FEED_DEFAULTS


def feed_worker(stop_event: threading.Event, mem: Dict[str, Any],
                payload: Dict[str, Any], runtime: Dict[str, Any] = None) -> None:
    """
    Tick-driver feed worker.

    Periodically calls the active meta plugin's process_input with
    input_type='tick' and routes returned narration segments into
    the candidate pipeline for TTS.
    """
    runtime = runtime or {}
    cfg = payload or {}

    log = runtime.get("log", lambda role, msg: print(f"[{role}] {msg}"))
    emit_candidate = runtime.get("emit_candidate")
    ui_q = runtime.get("ui_q")

    tick_sec = float(cfg.get("tick_sec", 6.0))
    startup_delay = float(cfg.get("startup_delay", 8.0))

    log("ok_court_feed", f"starting (tick_sec={tick_sec}, startup_delay={startup_delay})")

    # ── Wait for startup ───────────────────────────────────
    # Give the controller, court, and meta plugin time to initialise.
    if stop_event.wait(startup_delay):
        return  # station shutting down

    # ── Resolve meta plugin ────────────────────────────────
    meta_plugin = _resolve_meta_plugin(runtime, log)
    if not meta_plugin:
        log("ok_court_feed", "ERROR: no active meta plugin found — feed cannot produce narration")
        # Keep checking periodically in case it's loaded late
        while not stop_event.is_set():
            if stop_event.wait(5.0):
                return
            meta_plugin = _resolve_meta_plugin(runtime, log)
            if meta_plugin:
                log("ok_court_feed", f"meta plugin found: {type(meta_plugin).__name__}")
                break
        if not meta_plugin:
            return

    # ── Wait for a game to be loaded before starting narration ──
    # The user creates/loads a game via the web UI, which may happen
    # well after the feed starts.  Poll until the controller has state.
    _session_started = False
    controller = _find_controller(runtime, log)

    if controller and controller.state:
        log("ok_court_feed", "game already loaded — sending session_start immediately")
        _send_session_start(meta_plugin, emit_candidate, ui_q, log)
        _session_started = True
    else:
        has_ctrl = controller is not None
        has_state = has_ctrl and controller.state is not None
        log("ok_court_feed", f"waiting for game (controller={'found' if has_ctrl else 'NOT FOUND'}, state={'yes' if has_state else 'no'})")

    # ── Main tick loop ─────────────────────────────────────
    tick_count = 0
    _wait_log_counter = 0
    while not stop_event.is_set():
        if stop_event.wait(tick_sec):
            break

        # Check if a game appeared (user clicked New Game / Load)
        if not _session_started:
            controller = _find_controller(runtime, log)
            if controller and controller.state:
                log("ok_court_feed", f"game detected — sending session_start (tick={getattr(controller.state.player_kingdom, 'tick', '?') if controller.state else '?'})")
                _send_session_start(meta_plugin, emit_candidate, ui_q, log)
                _session_started = True
            else:
                _wait_log_counter += 1
                if _wait_log_counter % 10 == 1:  # log every ~60s
                    has_ctrl = controller is not None
                    log("ok_court_feed", f"still waiting for game... (controller={'found' if has_ctrl else 'NOT FOUND'}, checks={_wait_log_counter})")
                continue  # no game yet, skip tick

        tick_count += 1
        try:
            _do_tick(meta_plugin, emit_candidate, ui_q, log, tick_count)
        except Exception as e:
            log("ok_court_feed", f"tick error: {type(e).__name__}: {e}")

    # ── Shutdown ───────────────────────────────────────────
    try:
        _send_session_end(meta_plugin, emit_candidate, ui_q, log)
    except Exception:
        pass
    log("ok_court_feed", f"stopped after {tick_count} ticks")


# ════════════════════════════════════════════════════════════
# INTERNALS
# ════════════════════════════════════════════════════════════

def _resolve_meta_plugin(runtime: Dict[str, Any], log):
    """Try to find the active meta plugin instance."""
    # Method 1: runtime dict (added by bookmark.py at line 9313)
    mp = runtime.get("ACTIVE_META_PLUGIN")
    if mp and hasattr(mp, "process_input"):
        return mp

    # Method 2: import bookmark module global
    try:
        import bookmark
        mp = getattr(bookmark, "ACTIVE_META_PLUGIN", None)
        if mp and hasattr(mp, "process_input"):
            return mp
    except ImportError:
        pass

    # Method 3: shared_runtime
    try:
        import bookmark
        sr = getattr(bookmark, "shared_runtime", None)
        if sr and isinstance(sr, dict):
            mp = sr.get("ACTIVE_META_PLUGIN")
            if mp and hasattr(mp, "process_input"):
                return mp
    except Exception:
        pass

    return None


def _find_controller(runtime: Dict[str, Any], log):
    """Find the OKController instance."""
    # Method 1: runtime dict (feeds get a subset — usually not here)
    ctrl = runtime.get("ok_controller")
    if ctrl:
        return ctrl

    # Method 2: via the active meta plugin's context (most reliable)
    # The meta plugin's context dict has ok_controller forwarded by bookmark.py
    try:
        import bookmark
        mp = getattr(bookmark, "ACTIVE_META_PLUGIN", None)
        if mp and hasattr(mp, "context"):
            ctrl = mp.context.get("ok_controller")
            if ctrl:
                return ctrl
    except Exception:
        pass

    # Method 3: bookmark module-level shared_runtime (may not exist)
    try:
        import bookmark
        sr = getattr(bookmark, "shared_runtime", None)
        if sr and isinstance(sr, dict):
            ctrl = sr.get("ok_controller")
            if ctrl:
                return ctrl
    except Exception:
        pass

    return None


def _do_tick(meta_plugin, emit_candidate, ui_q, log, tick_count: int):
    """Run one narration tick."""
    segments = meta_plugin.process_input({"input_type": "tick"})
    if not segments:
        if tick_count <= 5 or tick_count % 10 == 0:
            log("ok_court_feed", f"tick {tick_count}: 0 segments from process_input")
        return

    emitted = 0
    system_segs = 0
    empty_text = 0
    for seg in segments:
        if not isinstance(seg, dict):
            continue

        text = (seg.get("text") or "").strip()
        voice = seg.get("voice", "narrator")
        priority = seg.get("priority", 50.0)
        metadata = seg.get("metadata", {})

        # System segments (audio_mix_update etc.) → push to ui_q only
        if voice == "_system" or not text:
            if voice == "_system":
                system_segs += 1
            else:
                empty_text += 1
            if ui_q and metadata:
                try:
                    ui_q.put({"type": "segment", "metadata": metadata})
                except Exception:
                    pass
            continue

        # Narration segment → emit as candidate for TTS pipeline
        if emit_candidate and text:
            candidate = {
                "source": "oracle_court_feed",
                "title": "",
                "body": text,
                "voice": voice,
                "lead_voice": voice,   # DB column name used by producer/TTS
                "priority": priority,
                "type": "narration",
                "_literal": True,  # body is final LLM text — skip host LLM rewrite
                "event_type": metadata.get("type", "narration"),
                "metadata": metadata,
            }
            # Propagate script atoms for multi-voice dialogue
            if seg.get("script") and isinstance(seg["script"], list):
                candidate["script"] = seg["script"]
            emit_candidate(candidate)
            emitted += 1

    if emitted or tick_count <= 5 or tick_count % 10 == 0:
        log("ok_court_feed", f"tick {tick_count}: {len(segments)} segs, emitted={emitted}, system={system_segs}, empty={empty_text}")


def _send_session_start(meta_plugin, emit_candidate, ui_q, log):
    """Send a session_start event to the meta plugin for the opening ritual."""
    try:
        segments = meta_plugin.process_input({
            "input_type": "session_start",
            "timestamp": time.time(),
        })
        if not segments:
            log("ok_court_feed", "session_start: process_input returned 0 segments")
            return
        emitted = 0
        skipped_system = 0
        skipped_empty = 0
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            text = (seg.get("text") or "").strip()
            voice = seg.get("voice", "narrator")
            priority = seg.get("priority", 60.0)
            metadata = seg.get("metadata", {})
            if voice == "_system" or not text:
                if not text:
                    skipped_empty += 1
                else:
                    skipped_system += 1
                if ui_q and metadata:
                    try:
                        ui_q.put({"type": "segment", "metadata": metadata})
                    except Exception:
                        pass
                continue
            if emit_candidate and text:
                emit_candidate({
                    "source": "oracle_court_feed",
                    "title": "",
                    "body": text,
                    "voice": voice,
                    "lead_voice": voice,
                    "priority": priority,
                    "type": "session_start",
                    "_literal": True,
                    "metadata": metadata,
                })
                emitted += 1
        log("ok_court_feed", f"session_start: {len(segments)} segments, emitted={emitted}, skipped_system={skipped_system}, skipped_empty={skipped_empty}")
    except Exception as e:
        log("ok_court_feed", f"session_start error: {type(e).__name__}: {e}")


def _send_session_end(meta_plugin, emit_candidate, ui_q, log):
    """Send a session_end event for the closing fade."""
    try:
        segments = meta_plugin.process_input({
            "input_type": "session_end",
            "timestamp": time.time(),
        })
        if segments:
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                text = (seg.get("text") or "").strip()
                voice = seg.get("voice", "narrator")
                metadata = seg.get("metadata", {})
                if voice == "_system" or not text:
                    if ui_q and metadata:
                        try:
                            ui_q.put({"type": "segment", "metadata": metadata})
                        except Exception:
                            pass
                    continue
                if emit_candidate and text:
                    emit_candidate({
                        "source": "oracle_court_feed",
                        "body": text,
                        "voice": voice,
                        "lead_voice": voice,
                        "priority": 70.0,
                        "type": "session_end",
                        "_literal": True,
                        "metadata": metadata,
                    })
    except Exception as e:
        log("ok_court_feed", f"session_end error: {type(e).__name__}: {e}")
