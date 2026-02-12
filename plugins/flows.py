# === PATCH: event-driven media backend + mac autodetect (best-effort) ===
# Drop this into your plugin (flows.py) and REPLACE:
#   - the GSMTC helper section (_get_manager/_pick_session/_read_now_playing/_control)
#   - the media init + _cmd_listener + "Read media" polling in feed_worker
#
# Notes:
# - Windows: uses GSMTC *events* (PlaybackInfoChanged/MediaPropertiesChanged/TimelinePropertiesChanged/CurrentSessionChanged)
#   so you regain “awareness” instead of asyncio.run polling.
# - macOS: autodetects Music.app or Spotify via AppleScript polling (no true OS-level event bus without extra deps).
#   It’s optional; if osascript fails, it falls back cleanly.

from __future__ import annotations
import random
import sys
import time
import threading
import asyncio
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, Callable

# =====================================================
# Platform detection
# =====================================================
IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# =====================================================
# Windows GSMTC imports
# =====================================================
_GSMTC = None
_PB = None

if IS_WINDOWS:
    try:
        from winsdk.windows.media.control import (  # type: ignore
            GlobalSystemMediaTransportControlsSessionManager as _GSMTC,
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as _PB,
        )
    except Exception:
        try:
            from winrt.windows.media.control import (  # type: ignore
                GlobalSystemMediaTransportControlsSessionManager as _GSMTC,
                GlobalSystemMediaTransportControlsSessionPlaybackStatus as _PB,
            )
        except Exception:
            _GSMTC = None
            _PB = None


# =====================================================
# Helpers
# =====================================================
def now_ts() -> int:
    return int(time.time())

def _safe_str(x: Any, default: str = "") -> str:
    try:
        return default if x is None else str(x)
    except Exception:
        return default

def _td_total_seconds(td) -> Optional[float]:
    try:
        return float(td.total_seconds())
    except Exception:
        return None

def _track_sig(st: Dict[str, Any]) -> str:
    import hashlib
    s = "|".join([
        _safe_str(st.get("title"), ""),
        _safe_str(st.get("artist"), ""),
        _safe_str(st.get("album"), ""),
        _safe_str(st.get("source_app"), ""),
    ])
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()


# =====================================================
# Media Backend (Windows event-driven + mac optional)
# =====================================================
DEFAULT_STATE: Dict[str, Any] = {
    "backend": "none",
    "ok": False,
    "playing": False,
    "title": "",
    "artist": "",
    "album": "",
    "source_app": "",
    "track_sig": "",
    "position_sec": None,
    "duration_sec": None,
    "remaining_sec": None,
    "last_update_ts": 0,
}

class MediaBackend:
    def __init__(self, log=None, runtime_music_state=None):
        self.log = log
        self.state = dict(DEFAULT_STATE)
        self._lock = threading.Lock()
        self.runtime_music_state = runtime_music_state


    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            snap = dict(self.state)
            return snap

    def update(self, patch: Dict[str, Any]) -> None:
        with self._lock:
            # Compute track signature when title/artist changes
            if "title" in patch or "artist" in patch or "album" in patch:
                sig = _track_sig({
                    "title": patch.get("title", self.state.get("title", "")),
                    "artist": patch.get("artist", self.state.get("artist", "")),
                    "album": patch.get("album", self.state.get("album", "")),
                    "source_app": self.state.get("source_app", "")
                })
                patch["track_sig"] = sig
            
            self.state.update(patch)
            self.state["last_update_ts"] = now_ts()
            # Also update runtime music state immediately for UI responsiveness
            if self.runtime_music_state is not None:
                try:
                    self.runtime_music_state.update(self.state)
                except Exception:
                    pass

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def control(self, cmd: str) -> bool:
        return False


class WindowsGSMTCBackend(MediaBackend):
    def __init__(self, log=None, runtime_music_state=None):
        super().__init__(log=log, runtime_music_state=runtime_music_state)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._mgr = None
        self._session = None
        self._timeline_poller_stop = threading.Event()
        self._last_position_sec = None  # Track position to detect track changes

    def start(self) -> None:
        if not _GSMTC:
            self.update({"backend": "windows_gsmtc", "ok": False})
            return

        def runner():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._init_and_listen())

        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()

        # Timeline poller (GSMTC does NOT always fire timeline events frequently)
        self._poller_tick_count = 0
        self._last_track_sig = None
        
        def timeline_poller():
            while not self._timeline_poller_stop.is_set():
                try:
                    self._poller_tick_count += 1
                    st = self.snapshot()
                    
                    # RECOVERY: If no session, try to find one (every ~2 seconds)
                    if self._session is None and self._poller_tick_count % 4 == 0:
                        if self._loop:
                            asyncio.run_coroutine_threadsafe(self._check_session_recovery(), self._loop)
                    
                    # Check track signature for changes
                    current_sig = _track_sig(st)
                    track_changed = False
                    
                    if st.get("ok"):
                        # Always refresh timeline when playing
                        if st.get("playing"):
                            current_pos = st.get("position_sec")
                            
                            # Detect track change by signature
                            if self._last_track_sig and current_sig != self._last_track_sig:
                                track_changed = True
                                if callable(self.log):
                                    self.log("flows", f"[POLLER] Track sig changed: {self._last_track_sig[:8]} -> {current_sig[:8]}")
                            
                            # Also detect by position reset
                            if self._last_position_sec is not None and current_pos is not None:
                                if current_pos < 3.0 and self._last_position_sec > 5.0:
                                    track_changed = True
                                    if callable(self.log):
                                        self.log("flows", f"[POLLER] Position reset detected: {self._last_position_sec:.1f}s -> {current_pos:.1f}s")
                                elif current_pos < self._last_position_sec - 5.0:
                                    track_changed = True
                                    if callable(self.log):
                                        self.log("flows", f"[POLLER] Position jump back: {self._last_position_sec:.1f}s -> {current_pos:.1f}s")
                            
                            self._last_position_sec = current_pos
                            self._last_track_sig = current_sig
                            
                            # Refresh: full if track changed, otherwise alternate between timeline and full
                            if self._loop:
                                if track_changed:
                                    asyncio.run_coroutine_threadsafe(self._refresh_full(), self._loop)
                                elif self._poller_tick_count % 2 == 0:
                                    # Every 1 second (2 ticks * 0.5s), do full refresh to catch track changes
                                    asyncio.run_coroutine_threadsafe(self._refresh_full(), self._loop)
                                else:
                                    asyncio.run_coroutine_threadsafe(self._refresh_timeline_only(), self._loop)
                        else:
                            # Not playing - do occasional full check
                            if self._poller_tick_count % 6 == 0 and self._loop:
                                asyncio.run_coroutine_threadsafe(self._refresh_full(), self._loop)
                except Exception as e:
                    if callable(self.log):
                        self.log("flows", f"[ERROR] Timeline poller: {e}")
                time.sleep(0.5)

        threading.Thread(target=timeline_poller, daemon=True).start()
        if callable(self.log):
            self.log("flows", "[BACKEND] Timeline poller thread started")

    def stop(self) -> None:
        self._timeline_poller_stop.set()
        try:
            if self._loop:
                self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass

    async def _check_session_recovery(self) -> None:
        try:
            session = self._safe_get_current_session()
            if session and session != self._session:
                 if callable(self.log):
                     self.log("flows", f"[RECOVERY] Found new session: {getattr(session, 'source_app_user_model_id', 'unknown')}")
                 await self._set_session(session)
        except Exception:
            pass

    async def _init_and_listen(self) -> None:
        try:
            self._mgr = await _GSMTC.request_async()  # type: ignore
            self.update({"backend": "windows_gsmtc", "ok": True})
            if callable(self.log):
                self.log("flows", "[BACKEND] GSMTC manager initialized successfully")
        except Exception as e:
            if callable(self.log):
                self.log("flows", f"[ERROR] GSMTC init failed: {e}")
            self.update({"backend": "windows_gsmtc", "ok": False})
            return

        # Listen for session switches
        try:
            self._mgr.current_session_changed += self._on_current_session_changed  # type: ignore
        except Exception:
            # Some projections expose CurrentSessionChanged; fall back quietly
            try:
                self._mgr.CurrentSessionChanged += self._on_current_session_changed  # type: ignore
            except Exception:
                pass

        current_session = self._safe_get_current_session()
        if callable(self.log):
            self.log("flows", f"[BACKEND] Initial session: {'Found' if current_session else 'None'}")
        await self._set_session(current_session)

        # Keep loop alive
        while True:
            await asyncio.sleep(3600)

    def _safe_get_current_session(self):
        try:
            s = self._mgr.get_current_session()  # type: ignore
            if s is not None:
                return s
        except Exception:
            pass
        # fallback: pick first “best” session (playing > paused > others)
        best = None
        best_rank = -1
        try:
            sessions = list(self._mgr.get_sessions() or [])  # type: ignore
        except Exception:
            sessions = []
        for s in sessions:
            try:
                pb = s.get_playback_info()
                status = pb.playback_status if pb is not None else None
                rank = 10
                if status == _PB.PLAYING:  # type: ignore
                    rank = 100
                elif status == _PB.PAUSED:  # type: ignore
                    rank = 60
                if rank > best_rank:
                    best = s
                    best_rank = rank
            except Exception:
                continue
        return best

    def _on_current_session_changed(self, *_args, **_kwargs):
        # Called from WinRT thread context; bounce into asyncio loop safely
        try:
            if callable(self.log):
                self.log("flows", "[GSMTC EVENT] Current session changed")
            if self._loop:
                asyncio.run_coroutine_threadsafe(self._set_session(self._safe_get_current_session()), self._loop)
        except Exception as e:
            if callable(self.log):
                self.log("flows", f"[ERROR] Session changed handler: {e}")

    async def _set_session(self, session):
        # Detach old handlers
        try:
            if self._session is not None:
                try:
                    self._session.playback_info_changed -= self._on_playback_info_changed  # type: ignore
                except Exception:
                    pass
                try:
                    self._session.media_properties_changed -= self._on_media_properties_changed  # type: ignore
                except Exception:
                    pass
                try:
                    self._session.timeline_properties_changed -= self._on_timeline_properties_changed  # type: ignore
                except Exception:
                    pass
        except Exception:
            pass

        self._session = session
        self._last_position_sec = None  # Reset position tracking for new session
        self._last_track_sig = None  # Reset track signature tracking
        
        if self._session is None:
            if callable(self.log):
                self.log("flows", "[SESSION] No active media session")
            self.update({"playing": False, "title": "", "artist": "", "album": "", "source_app": ""})
            return

        if callable(self.log):
            try:
                app = _safe_str(self._session.source_app_user_model_id, "unknown")
                self.log("flows", f"[SESSION] Set active session: {app}")
            except Exception:
                self.log("flows", "[SESSION] Set active session (unknown app)")

        # Attach new handlers
        try:
            self._session.playback_info_changed += self._on_playback_info_changed  # type: ignore
        except Exception:
            try:
                self._session.PlaybackInfoChanged += self._on_playback_info_changed  # type: ignore
            except Exception:
                pass
        try:
            self._session.media_properties_changed += self._on_media_properties_changed  # type: ignore
        except Exception:
            try:
                self._session.MediaPropertiesChanged += self._on_media_properties_changed  # type: ignore
            except Exception:
                pass
        try:
            self._session.timeline_properties_changed += self._on_timeline_properties_changed  # type: ignore
        except Exception:
            try:
                self._session.TimelinePropertiesChanged += self._on_timeline_properties_changed  # type: ignore
            except Exception:
                pass

        await self._refresh_full()

    def _on_playback_info_changed(self, *_args, **_kwargs):
        try:
            if callable(self.log):
                self.log("flows", "[GSMTC EVENT] Playback info changed")
            if self._loop:
                asyncio.run_coroutine_threadsafe(self._refresh_playback_only(), self._loop)
        except Exception as e:
            if callable(self.log):
                self.log("flows", f"[ERROR] Playback info changed handler: {e}")
            pass

    def _on_media_properties_changed(self, *_args, **_kwargs):
        try:
            if callable(self.log):
                self.log("flows", "[GSMTC EVENT] Media properties changed")
            if self._loop:
                asyncio.run_coroutine_threadsafe(self._refresh_media_only(), self._loop)
        except Exception as e:
            if callable(self.log):
                self.log("flows", f"[ERROR] Media properties changed handler: {e}")
            pass

    def _on_timeline_properties_changed(self, *_args, **_kwargs):
        try:
            if callable(self.log):
                self.log("flows", "[GSMTC EVENT] Timeline properties changed")
            if self._loop:
                asyncio.run_coroutine_threadsafe(self._refresh_timeline_only(), self._loop)
        except Exception as e:
            if callable(self.log):
                self.log("flows", f"[ERROR] Timeline properties changed handler: {e}")
            pass

    async def _refresh_full(self):
        if callable(self.log):
            self.log("flows", "[REFRESH] Full refresh triggered")
        await self._refresh_media_only()
        await self._refresh_playback_only()
        await self._refresh_timeline_only()

    async def _refresh_media_only(self):
        if self._session is None:
            return
        patch: Dict[str, Any] = {}
        try:
            try:
                patch["source_app"] = _safe_str(self._session.source_app_user_model_id, "")
            except Exception:
                pass
            props = await self._session.try_get_media_properties_async()
            if props is not None:
                patch["title"] = _safe_str(getattr(props, "title", ""), "")
                patch["artist"] = _safe_str(getattr(props, "artist", ""), "")
                patch["album"] = _safe_str(getattr(props, "album_title", ""), "")
                if callable(self.log) and (patch.get("title") or patch.get("artist")):
                    self.log("flows", f"[REFRESH] Media: '{patch.get('title', '')}' by '{patch.get('artist', '')}'")
        except Exception as e:
            msg = str(e)
            if "RPC server" in msg or "0x800706BA" in msg:
                if callable(self.log):
                     self.log("flows", f"[ERROR] RPC Error (Session Dead): {e}")
                self._session = None # Force re-discovery
            elif callable(self.log):
                self.log("flows", f"[ERROR] Refresh media: {e}")
        if patch:
            self.update(patch)

    async def _refresh_playback_only(self):
        if self._session is None:
            return
        try:
            pb = self._session.get_playback_info()
            status = pb.playback_status if pb is not None else None
            playing = bool(status == _PB.PLAYING) if status is not None else False  # type: ignore
            old_playing = self.snapshot().get("playing", False)
            if playing != old_playing and callable(self.log):
                self.log("flows", f"[REFRESH] Playback: {'PLAYING' if playing else 'PAUSED/STOPPED'}")
            self.update({"playing": playing})
        except Exception as e:
            msg = str(e)
            if "RPC server" in msg or "0x800706BA" in msg:
                 self._session = None
            if callable(self.log):
                self.log("flows", f"[ERROR] Refresh playback: {e}")

    async def _refresh_timeline_only(self):
        if self._session is None:
            return
        try:
            tl = self._session.get_timeline_properties()
            if tl is None:
                if callable(self.log):
                    self.log("flows", "[DEBUG] Timeline properties returned None")
                return
            
            pos = getattr(tl, "position", None)
            end = getattr(tl, "end_time", None)
            
            if callable(self.log):
                self.log("flows", f"[DEBUG] Timeline raw: pos={pos} end={end}")
            
            pos_s = _td_total_seconds(pos)
            end_s = _td_total_seconds(end)

            patch: Dict[str, Any] = {
                "position_sec": pos_s,
                "duration_sec": end_s,
            }
            if isinstance(pos_s, (int, float)) and isinstance(end_s, (int, float)) and end_s > 0:
                patch["remaining_sec"] = max(0.0, end_s - pos_s)
            self.update(patch)
        except Exception as e:
            msg = str(e)
            if "RPC server" in msg or "0x800706BA" in msg:
                 self._session = None
            if callable(self.log):
                self.log("flows", f"[ERROR] Refresh timeline: {e}")

    def control(self, cmd: str) -> bool:
        if self._loop is None:
            return False

        async def _do():
            try:
                if self._session is None:
                    return False
                c = (cmd or "").lower().strip()
                if c in ("play_pause", "toggle"):
                    return bool(await self._session.try_toggle_play_pause_async())
                if c == "pause":
                    return bool(await self._session.try_pause_async())
                if c == "play":
                    return bool(await self._session.try_play_async())
                if c == "stop":
                    return bool(await self._session.try_stop_async())
                if c in ("next", "skip"):
                    return bool(await self._session.try_skip_next_async())
                if c in ("prev", "previous", "back"):
                    return bool(await self._session.try_skip_previous_async())
                return False
            except Exception:
                return False

        try:
            fut = asyncio.run_coroutine_threadsafe(_do(), self._loop)
            return bool(fut.result(timeout=2.0))
        except Exception:
            return False


class MacAppleScriptBackend(MediaBackend):
    """
    Optional macOS backend:
    - Autodetects Music.app or Spotify.
    - Uses osascript polling for state/metadata.
    - Control commands via AppleScript (best-effort).
    """
    def __init__(self, log=None, runtime_music_state=None):
        super().__init__(log=log, runtime_music_state=runtime_music_state)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._player: str = "none"  # "Music" | "Spotify" | "none"

    def start(self) -> None:
        self.update({"backend": "mac_applescript", "ok": True})
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _osascript(self, script: str) -> str:
        p = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if p.returncode != 0:
            return ""
        return (p.stdout or "").strip()

    def _detect_player(self) -> str:
        # Prefer whichever is actively playing; fallback to running app
        # Music
        music_playing = self._osascript('tell application "Music" to if it is running then return (player state as string) else return ""')
        if (music_playing or "").lower() == "playing":
            return "Music"
        # Spotify
        spot_playing = self._osascript('tell application "Spotify" to if it is running then return (player state as string) else return ""')
        if (spot_playing or "").lower() == "playing":
            return "Spotify"
        # running?
        if music_playing:
            return "Music"
        if spot_playing:
            return "Spotify"
        return "none"

    def _read_player(self, app: str) -> Dict[str, Any]:
        st = dict(DEFAULT_STATE)
        st["backend"] = "mac_applescript"
        st["ok"] = True
        st["source_app"] = app

        if app == "none":
            return st

        # Common fields
        state = self._osascript(f'tell application "{app}" to return (player state as string)')
        st["playing"] = (state or "").lower() == "playing"

        # Metadata
        title = self._osascript(f'tell application "{app}" to return (name of current track as string)')
        artist = self._osascript(f'tell application "{app}" to return (artist of current track as string)')
        album = self._osascript(f'tell application "{app}" to return (album of current track as string)')
        st["title"] = title or ""
        st["artist"] = artist or ""
        st["album"] = album or ""

        # Position / duration (best-effort)
        # Music: player position seconds; Spotify: player position ms
        if app == "Music":
            pos = self._osascript('tell application "Music" to return (player position as string)')
            dur = self._osascript('tell application "Music" to return (duration of current track as string)')  # seconds
            try:
                st["position_sec"] = float(pos) if pos else None
            except Exception:
                st["position_sec"] = None
            try:
                st["duration_sec"] = float(dur) if dur else None
            except Exception:
                st["duration_sec"] = None
        elif app == "Spotify":
            pos = self._osascript('tell application "Spotify" to return (player position as string)')  # seconds
            dur = self._osascript('tell application "Spotify" to return (duration of current track as string)')  # ms
            try:
                st["position_sec"] = float(pos) if pos else None
            except Exception:
                st["position_sec"] = None
            try:
                st["duration_sec"] = (float(dur) / 1000.0) if dur else None
            except Exception:
                st["duration_sec"] = None

        if isinstance(st.get("position_sec"), (int, float)) and isinstance(st.get("duration_sec"), (int, float)):
            st["remaining_sec"] = max(0.0, float(st["duration_sec"]) - float(st["position_sec"]))

        return st

    def _run(self) -> None:
        # Polling loop (0.5–1.0s is fine)
        while not self._stop.is_set():
            try:
                self._player = self._detect_player()
                st = self._read_player(self._player)
                self.update(st)
            except Exception:
                pass
            time.sleep(0.75)

    def control(self, cmd: str) -> bool:
        app = self.snapshot().get("source_app") or self._player
        if app not in ("Music", "Spotify"):
            return False
        c = (cmd or "").lower().strip()
        if c in ("play_pause", "toggle"):
            out = self._osascript(f'tell application "{app}" to playpause')
            return True if out is not None else True  # osascript often returns empty
        if c == "pause":
            self._osascript(f'tell application "{app}" to pause')
            return True
        if c == "play":
            self._osascript(f'tell application "{app}" to play')
            return True
        if c in ("next", "skip"):
            self._osascript(f'tell application "{app}" to next track')
            return True
        if c in ("prev", "previous", "back"):
            self._osascript(f'tell application "{app}" to previous track')
            return True
        return False


def make_media_backend(log=None, runtime_music_state=None) -> MediaBackend:
    if IS_WINDOWS and _GSMTC:
        return WindowsGSMTCBackend(log=log, runtime_music_state=runtime_music_state)
    if IS_MAC:
        return MacAppleScriptBackend(log=log, runtime_music_state=runtime_music_state)
    b = MediaBackend(log=log, runtime_music_state=runtime_music_state)
    b.update({"backend": "none", "ok": False})
    return b


# =====================================================
# FEED WORKER PATCH: replace your GSMTC init + cmd listener + polling
# =====================================================
def feed_worker(stop_event, mem, cfg, runtime=None):
    if not runtime:
        return

    event_q = runtime.get("event_q")
    ui_cmd_q = runtime.get("ui_cmd_q")
    log = runtime.get("log")
    StationEvent = runtime.get("StationEvent")
    producer_kick = runtime.get("producer_kick")
    db_connect = runtime.get("db_connect")
    
    # DEBUG: Confirm feed worker started
    if callable(log):
        log("flows", "=== FLOWS FEED WORKER STARTED ===")
        log("flows", f"Config: {cfg}")
    
    # Get SHOW_INTERRUPT for graceful host speech cutting
    SHOW_INTERRUPT = runtime.get("SHOW_INTERRUPT")

    music_state = runtime.get("MUSIC_STATE")
    if music_state is None:
        music_state = {}
        runtime["MUSIC_STATE"] = music_state

    music_state.setdefault("allow_background_music", False)


    # --- start backend (event-driven on Windows, optional polling on Mac) ---
    if callable(log):
        log("flows", "Initializing media backend...")
    backend = make_media_backend(log=log if callable(log) else None, runtime_music_state=music_state)
    backend.start()
    if callable(log):
        log("flows", f"Backend started: {backend.snapshot().get('backend', 'unknown')}")

    # --- ui_cmd_q listener: handle music control + config updates ---
    def _cmd_listener():
        if not ui_cmd_q:
            return
        import queue
        while not stop_event.is_set():
            try:
                evt, payload = ui_cmd_q.get(timeout=0.25)
                if evt == "music_cmd":
                    backend.control((payload or {}).get("cmd", ""))
                elif evt == "update_config":
                    # Update config in-place so feed_worker sees it
                    cfg_updates = (payload or {}).get("config", {})
                    if cfg_updates:
                        cfg.update(cfg_updates)
                        if callable(log):
                            log("flows", f"Config updated: {cfg_updates}")
            except queue.Empty:
                # Timeout is expected when queue is empty, not an error
                pass
            except Exception as e:
                if callable(log):
                    log("flows", f"Cmd listener error: {e}")

    threading.Thread(target=_cmd_listener, daemon=True).start()

    # =========================================================================
    # STATE TRACKING - SIMPLE TEXT COMPARISON
    # =========================================================================
    
    last_title = None
    last_artist = None
    last_playing = False
    
    flow_count = 1  # How many songs have played in this flow
    flow_target = None  # Will be set in loop
    
    in_talk_break = False
    talk_segments_target = None
    break_start_ts = 0  # Timestamp when break mode started
    music_incoming_sent = False
    last_reaction_ts = 0
    last_state_log_ts = 0

    if callable(log):
        log("flows", f"[INIT] Flow logic started. Initial flow_count={flow_count}")

    while not stop_event.is_set():
        # 1. READ CONFIG & STATE
        try:
            st = backend.snapshot()
            playing = bool(st.get("playing"))
            title = (st.get("title") or "").strip()
            artist = (st.get("artist") or "").strip()
            
            # Config
            enabled = bool(cfg.get("enabled", False))
            music_state["flows_enabled"] = enabled
        except Exception as e:
            if callable(log): log("flows", f"[ERROR] State read failed: {e}")
            time.sleep(1)
            continue

        now = now_ts()

        # Update Flow Target if missing
        if flow_target is None:
            fmin = int(cfg.get("flow_songs_min", 1))
            fmax = int(cfg.get("flow_songs_max", 3))
            frnd = bool(cfg.get("flow_songs_random", True))
            lo, hi = min(fmin, fmax), max(fmin, fmax)
            flow_target = random.randint(lo, hi) if frnd else lo
            if callable(log):
                log("flows", f"[TARGET] New flow target set: {flow_target} songs")

        # ---------------------------------------------------------------------
        # MODE 1: TALK BREAK (Enforce Silence / Wait for Host)
        # ---------------------------------------------------------------------
        if in_talk_break:
            # ENFORCE SILENCE: If music is playing during break, PAUSE IT
            if playing:
                if callable(log):
                    log("flows", "[BREAK] Music playing during break -> PAUSING")
                backend.control("pause")
                time.sleep(0.5) # Give it time to react
                continue

            # CHECK FOR RESUME (Host finished talking)
            if talk_segments_target is not None:
                # Debug logging for break status (throttled)
                if callable(log) and (now - last_state_log_ts > 3):
                     log("flows", f"[BREAK MODE] Checking. Target={talk_segments_target}, BreakTS={break_start_ts}")
                     last_state_log_ts = now

                try:
                    if callable(db_connect):
                        db = db_connect()
                        # Count only segments routed AFTER entering break mode
                        cursor = db.execute("SELECT COUNT(*) FROM segments WHERE routed_ts > ?", (break_start_ts,))
                        segments_since_break = cursor.fetchone()[0]
                        db.close()
                        
                        # Log count every check (it's already throttled above)
                        if callable(log):
                             log("flows", f"[BREAK] Segments aired since break: {segments_since_break} (Need {talk_segments_target})")

                        if segments_since_break >= talk_segments_target:
                            if callable(log):
                                log("flows", f"[BREAK] Target reached ({segments_since_break}/{talk_segments_target}) -> RESUMING MUSIC")
                            
                            # Try to resume
                            resume_ok = backend.control("play")
                            if callable(log): 
                                if resume_ok:
                                    log("flows", "[BREAK] Resume command sent successfully.")
                                else:
                                    log("flows", "[BREAK] Resume command returned False, but exiting break mode anyway.")
                            
                            # Always exit break mode after reaching target - music flow will redetect tracks
                            in_talk_break = False
                            talk_segments_target = None
                            break_start_ts = 0
                            flow_count = 1 # Start new flow
                            flow_target = None # Regen target
                            last_title = None # Force re-detect
                            time.sleep(0.5) # Give backend time to process
                    else:
                         if callable(log):
                              log("flows", "[ERROR] db_connect is not callable! Cannot track segments.")
                except Exception as e:
                     import traceback
                     if callable(log): 
                         log("flows", f"[ERROR] DB check exception: {e}")
                         log("flows", f"[ERROR] Traceback: {traceback.format_exc()}")
            
            time.sleep(1.0)
            continue
            
        # ---------------------------------------------------------------------
        # MODE 2: MUSIC FLOW (Monitor Tracks)
        # ---------------------------------------------------------------------
        
        # Initialize History on First Song
        if last_title is None and title:
            last_title = title
            last_artist = artist
            last_playing = playing
            if callable(log):
                log("flows", f"[INIT] First track detected: '{title}' (Flow 1/{flow_target})")

        # Detect Track Change
        has_changed = False
        
        # Debug transition logic
        if callable(log) and (title != last_title):
             # Only log if substantial strings are involved to avoid spamming on startup/shutdown
             if title or last_title:
                 log("flows", f"[DEBUG] Checking Change: Now='{title}' was='{last_title}'. Match={(title and last_title and title != last_title)}")

        if (title and last_title and title != last_title) or (artist and last_artist and artist != last_artist):
            has_changed = True
            flow_count += 1
            if callable(log):
                log("flows", f"[FLOW] TRACK CHANGE Detected! {flow_count}/{flow_target}")
                log("flows", f"       Old: {last_title}")
                log("flows", f"       New: {title}")
            
            # Update History
            last_title = title
            last_artist = artist
            
            # Send intro event
            if enabled and event_q and StationEvent:
                try:
                    event_q.put(StationEvent(
                        source="flows",
                        text=f"New track: {title} ({flow_count}/{flow_target})",
                        payload={
                            "type": "flow_intro",
                            "title": f"Song {flow_count}/{flow_target}",
                            "track": title,
                            "artist": artist,
                            "flow_count": flow_count,
                            "flow_target": flow_target,
                            "angle": "Introduce this track.",
                            "host_hint": "Quick intro."
                        }
                    ), timeout=1.0)
                except Exception as e:
                    if callable(log): log("flows", f"[WARN] Failed to put intro event: {e}")

                if callable(producer_kick):
                     try: producer_kick()
                     except: pass

        # CHECK BOUNDARY (Stop if we exceeded target)
        # Logic: If target is 3, we play 1, 2, 3.
        # When Song 4 starts -> flow_count becomes 4.
        # 4 > 3 -> STOP.
        if enabled and flow_count > flow_target:
            if callable(log):
                log("flows", f"[LIMIT] Flow count {flow_count} > target {flow_target}. STOPPING MUSIC.")
            
            # Pause
            backend.control("pause")
            
            # Set Break State
            in_talk_break = True
            
            # Setup Break Duration
            tmin = int(cfg.get("talk_segments_min", 2))
            tmax = int(cfg.get("talk_segments_max", 5))
            talk_segments_target = random.randint(tmin, tmax)
            
            # Record timestamp when entering break mode
            break_start_ts = now_ts()
                
            if callable(log):
                 log("flows", f"[LIMIT] Entering break mode. Waiting for {talk_segments_target} segments.")
                 log("flows", f"[LIMIT] Break state set: in_talk_break={in_talk_break}, break_start_ts={break_start_ts}")

            # Send Event
            if event_q and StationEvent:
                event_q.put(StationEvent(
                    source="flows",
                    text="Flow complete. Talk break.",
                    payload={
                        "type": "flow_boundary",
                        "title": "Flow Complete",
                        "body": f"Finished {flow_count-1} songs.",
                        "flow_count": flow_count-1,
                        "angle": "Talk break.",
                        "priority": 100.0
                    }
                ))
                if callable(producer_kick):
                    producer_kick()
            
            time.sleep(0.5)
            continue

        # Debug Heartbeat (Every 5s to confirm loop liveness)
        if callable(log) and (now - last_state_log_ts > 5):
            log("flows", f"[STATUS] Song {flow_count}/{flow_target} | '{title}' | Playing: {playing} | Loop Alive")
            last_state_log_ts = now
            
        # Detect Manual Resume (if user hit play but we weren't in break)
        if playing and not last_playing:
            # Just came back from a pause (not a flow break)
            # Maybe interrupt host?
            if SHOW_INTERRUPT:
                try: 
                    SHOW_INTERRUPT.set()
                    time.sleep(0.1) 
                    SHOW_INTERRUPT.clear()
                except: pass
        
        last_playing = playing
        time.sleep(0.25)


    # on stop
    try:
        backend.stop()
    except Exception:
        pass
# =====================================================
# Widget
# =====================================================
# =====================================================
# Widget
# =====================================================

def register_widgets(registry, runtime):

    tk = runtime["tk"]
    ui_cmd_q = runtime.get("ui_cmd_q")

    BG = "#0e0e0e"
    SURFACE = "#121212"
    CARD = "#161616"
    TXT = "#e8e8e8"
    MUTED = "#9a9a9a"
    ACCENT = "#4cc9f0"
    GOOD = "#2ee59d"

    # Load manifest to get initial flows config
    try:
        import os, yaml
        station_dir = os.environ.get("STATION_DIR", ".")
        manifest_path = os.path.join(station_dir, "manifest.yaml")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f) or {}
        flows_cfg = (manifest.get("feeds") or {}).get("flows") or {}
    except Exception:
        flows_cfg = {}

    def widget_factory(parent, runtime):
        return FlowControlWidget(parent, runtime, ui_cmd_q, flows_cfg, BG, SURFACE, CARD, TXT, MUTED, ACCENT, GOOD)

    registry.register(
        "flows_control",
        widget_factory,
        title="Flows",
        default_panel="left"
    )


class FlowControlWidget:
    def __init__(self, parent, runtime, ui_cmd_q, flows_cfg, BG, SURFACE, CARD, TXT, MUTED, ACCENT, GOOD):

        self.runtime = runtime
        self.tk = runtime["tk"]
        self.ui_cmd_q = ui_cmd_q
        self.flows_cfg = flows_cfg

        self.BG = BG
        self.SURFACE = SURFACE
        self.CARD = CARD
        self.TXT = TXT
        self.MUTED = MUTED
        self.ACCENT = ACCENT
        self.GOOD = GOOD

        self.root = self.tk.Frame(parent, bg=self.BG)

        box = self.tk.Frame(
            self.root,
            bg=self.SURFACE,
            highlightbackground="#2a2a2a",
            highlightthickness=1
        )
        box.pack(fill="both", expand=True, padx=4, pady=4)

        # Header
        hdr = self.tk.Frame(box, bg=self.SURFACE)
        hdr.pack(fill="x", padx=10, pady=(10, 6))

        self.tk.Label(
            hdr,
            text="FLOWS",
            fg=self.ACCENT,
            bg=self.SURFACE,
            font=("Segoe UI", 10, "bold")
        ).pack(side="left")

        self.status = self.tk.Label(
            hdr,
            text="• idle",
            fg=self.MUTED,
            bg=self.SURFACE,
            font=("Segoe UI", 10)
        )
        self.status.pack(side="right")

        # Use the flows config loaded from manifest
        cfg = self.flows_cfg

        # Enable toggle
        self.v_enabled = self.tk.BooleanVar(value=bool(cfg.get("enabled", False)))

        self.tk.Checkbutton(
            box,
            text="Enable Flows Plugin",
            variable=self.v_enabled,
            bg=self.SURFACE,
            fg=self.TXT,
            selectcolor=self.SURFACE,
            activebackground=self.SURFACE,
            activeforeground=self.TXT,
            command=self._on_cfg_change
        ).pack(anchor="w", padx=10, pady=(0, 8))

        music_state = self.runtime.get("MUSIC_STATE") or {}

        # Talk-over toggle
        self.v_talk_over = self.tk.BooleanVar(
            value=bool(music_state.get("allow_background_music", False))
        )

        self.tk.Checkbutton(
            box,
            text="Talk over music (duck instead of pause)",
            variable=self.v_talk_over,
            bg=self.SURFACE,
            fg=self.TXT,
            selectcolor=self.SURFACE,
            activebackground=self.SURFACE,
            activeforeground=self.TXT,
            command=self._on_talk_over_change
        ).pack(anchor="w", padx=10, pady=(0, 8))

        # Track display
        self.track = self.tk.Label(
            box,
            text="(no track)",
            fg=self.TXT,
            bg=self.SURFACE,
            font=("Segoe UI", 11, "bold"),
            anchor="w"
        )
        self.track.pack(fill="x", padx=10)

        self.meta = self.tk.Label(
            box,
            text="",
            fg=self.MUTED,
            bg=self.SURFACE,
            font=("Segoe UI", 9),
            anchor="w"
        )
        self.meta.pack(fill="x", padx=10, pady=(0, 8))

        # Controls
        controls = self.tk.Frame(box, bg=self.SURFACE)
        controls.pack(fill="x", padx=10, pady=(0, 8))

        def btn(txt, cmd):
            b = self.tk.Button(
                controls,
                text=txt,
                command=cmd,
                bg=self.CARD,
                fg=self.TXT,
                relief="flat",
                padx=8,
                pady=4
            )
            b.pack(side="left", padx=(0, 4))

        def send(cmd):
            if self.ui_cmd_q:
                self.ui_cmd_q.put(("music_cmd", {"cmd": cmd}))

        btn("⏮", lambda: send("prev"))
        btn("⏯", lambda: send("play_pause"))
        btn("⏭", lambda: send("next"))

        # Duck slider
        row = self.tk.Frame(box, bg=self.SURFACE)
        row.pack(fill="x", padx=10)

        self.tk.Label(
            row,
            text="Duck",
            fg=self.MUTED,
            bg=self.SURFACE,
            font=("Segoe UI", 8)
        ).pack(side="left")

        self.v_duck = self.tk.DoubleVar(
            value=float(music_state.get("duck_level", 0.25) or 0.25)
        )

        self.tk.Scale(
            row,
            from_=0,
            to=1,
            resolution=0.05,
            orient="horizontal",
            variable=self.v_duck,
            bg=self.SURFACE,
            fg=self.TXT,
            highlightthickness=0,
            command=self._on_duck_change,
            length=180
        ).pack(side="right")

        # Flow pacing
        pacing = self.tk.LabelFrame(
            box,
            text="Music Flow (songs per cycle)",
            bg=self.SURFACE,
            fg=self.TXT,
            font=("Segoe UI", 8, "bold"),
            bd=1
        )
        pacing.pack(fill="x", padx=10, pady=(10, 5))

        self.v_flow_min = self.tk.IntVar(value=int(cfg.get("flow_songs_min", 1)))
        self.v_flow_max = self.tk.IntVar(value=int(cfg.get("flow_songs_max", 3)))
        self.v_flow_rnd = self.tk.BooleanVar(value=bool(cfg.get("flow_songs_random", True)))
        
        # Talk break pacing
        self.v_talk_min = self.tk.IntVar(value=int(cfg.get("talk_segments_min", 2)))
        self.v_talk_max = self.tk.IntVar(value=int(cfg.get("talk_segments_max", 5)))
        self.v_talk_rnd = self.tk.BooleanVar(value=bool(cfg.get("talk_segments_random", True)))

        self.tk.Checkbutton(
            pacing,
            text="Random flow length",
            variable=self.v_flow_rnd,
            bg=self.SURFACE,
            fg=self.TXT,
            selectcolor=self.SURFACE,
            activebackground=self.SURFACE,
            activeforeground=self.TXT,
            command=self._on_cfg_change
        ).pack(anchor="w", padx=6, pady=(4, 2))

        def slider(parent, label, var, lo, hi):
            r = self.tk.Frame(parent, bg=self.SURFACE)
            r.pack(fill="x", pady=2)

            self.tk.Label(
                r,
                text=label,
                fg=self.MUTED,
                bg=self.SURFACE,
                width=12,
                anchor="w",
                font=("Segoe UI", 8)
            ).pack(side="left")

            self.tk.Scale(
                r,
                from_=lo,
                to=hi,
                orient="horizontal",
                variable=var,
                bg=self.SURFACE,
                fg=self.TXT,
                highlightthickness=0,
                length=180,
                command=self._on_cfg_change
            ).pack(side="right")

        slider(pacing, "Min", self.v_flow_min, 1, 10)
        slider(pacing, "Max", self.v_flow_max, 1, 20)

        # Talk break pacing
        talk_pacing = self.tk.LabelFrame(
            box,
            text="Talk Break (segments to play)",
            bg=self.SURFACE,
            fg=self.TXT,
            font=("Segoe UI", 8, "bold"),
            bd=1
        )
        talk_pacing.pack(fill="x", padx=10, pady=(5, 10))

        self.tk.Checkbutton(
            talk_pacing,
            text="Random talk length",
            variable=self.v_talk_rnd,
            bg=self.SURFACE,
            fg=self.TXT,
            selectcolor=self.SURFACE,
            activebackground=self.SURFACE,
            activeforeground=self.TXT,
            command=self._on_cfg_change
        ).pack(anchor="w", padx=6, pady=(4, 2))

        slider(talk_pacing, "Min", self.v_talk_min, 1, 10)
        slider(talk_pacing, "Max", self.v_talk_max, 1, 20)

        # Reaction frequency
        freq = self.tk.LabelFrame(
            box,
            text="Reaction Frequency",
            bg=self.SURFACE,
            fg=self.TXT,
            font=("Segoe UI", 8, "bold"),
            bd=1
        )
        freq.pack(fill="x", padx=10, pady=(0, 10))

        self.v_freq = self.tk.DoubleVar(value=float(cfg.get("reaction_frequency", 0.2)))

        self.tk.Scale(
            freq,
            from_=0,
            to=1,
            resolution=0.05,
            orient="horizontal",
            variable=self.v_freq,
            bg=self.SURFACE,
            fg=self.TXT,
            highlightthickness=0,
            command=self._on_cfg_change
        ).pack(fill="x", padx=6, pady=6)

        self._tick()

    def _on_talk_over_change(self):
        st = self.runtime.get("MUSIC_STATE")
        if not isinstance(st, dict):
            st = {}
            self.runtime["MUSIC_STATE"] = st
        st["allow_background_music"] = bool(self.v_talk_over.get())

    def _on_cfg_change(self, _v=None):
        updates = {
            "enabled": bool(self.v_enabled.get()),
            "flow_songs_min": int(self.v_flow_min.get()),
            "flow_songs_max": int(self.v_flow_max.get()),
            "flow_songs_random": bool(self.v_flow_rnd.get()),
            "talk_segments_min": int(self.v_talk_min.get()),
            "talk_segments_max": int(self.v_talk_max.get()),
            "talk_segments_random": bool(self.v_talk_rnd.get()),
            "reaction_frequency": float(self.v_freq.get()),
        }
        if self.ui_cmd_q:
            self.ui_cmd_q.put(("update_config", {"config": updates}))

    def _on_duck_change(self, _v=None):
        st = self.runtime.get("MUSIC_STATE")
        if not isinstance(st, dict):
            st = {}
            self.runtime["MUSIC_STATE"] = st
        st["duck_level"] = float(self.v_duck.get())

    def _tick(self):
        self._refresh()
        self.root.after(250, self._tick)  # 250ms = 4Hz refresh rate for responsive UI

    def _refresh(self):
        st = self.runtime.get("MUSIC_STATE") or {}

        playing = bool(st.get("playing"))
        title = st.get("title") or ""
        artist = st.get("artist") or ""

        if title:
            self.track.config(text=f"{artist} — {title}")
        else:
            self.track.config(text="(no track)")

        rem = st.get("remaining_sec")
        self.meta.config(
            text=f"{int(rem)}s remaining" if isinstance(rem, (int, float)) else ""
        )

        self.status.config(
            text="• playing" if playing else "• idle",
            fg=self.GOOD if playing else self.MUTED
        )
