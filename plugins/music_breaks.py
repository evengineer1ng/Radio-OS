from __future__ import annotations

import sys
import time
import random
import threading
from typing import Any, Dict, Optional, Tuple

PLUGIN_NAME = "music_breaks"
IS_FEED = True

DEFAULT_CONFIG = {
    "break_duration_min": 20,
    "break_duration_max": 150,
    "break_duration_random": True,
    "flow_songs_min": 1,
    "flow_songs_max": 3,
    "flow_songs_random": True,
}

# =====================================================
# Platform detection
# =====================================================
IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


# =====================================================
# Helper: log_every (de-duplication helper)
# =====================================================
def log_every(mem: Dict[str, Any], key: str, every_sec: int, role: str, msg: str) -> None:
    """Only log if at least every_sec have passed since last time."""
    now = time.time()
    last_time = mem.get(f"_log_every_{key}", 0)
    if now - last_time >= every_sec:
        mem[f"_log_every_{key}"] = now
        import your_runtime as rt
        if callable(rt.log):
            rt.log(role, msg)

# -----------------------------
# Win API import (winsdk / winrt)
# -----------------------------
_GSMTC = None
_PB = None

if IS_WINDOWS:
    try:
        from winsdk.windows.media.control import (  # type: ignore
            GlobalSystemMediaTransportControlsSessionManager as _GSMTC,  # type: ignore
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as _PB,  # type: ignore
        )
    except Exception:
        try:
            from winrt.windows.media.control import (  # type: ignore
                GlobalSystemMediaTransportControlsSessionManager as _GSMTC,  # type: ignore
                GlobalSystemMediaTransportControlsSessionPlaybackStatus as _PB,  # type: ignore
            )
        except Exception:
            _GSMTC = None
            _PB = None

# -----------------------------
# Mac API import (PyObjC)
# -----------------------------
_MPNowPlayingInfoCenter = None
_MPMusicPlayerController = None

if IS_MAC:
    try:
        from Foundation import NSObject  # type: ignore
        from AppKit import NSWorkspace  # type: ignore
        import objc  # type: ignore
        # MediaPlayer framework for now playing info
        try:
            objc.loadBundle(
                "MediaPlayer",
                bundle_path="/System/Library/Frameworks/MediaPlayer.framework",
                module_globals=globals(),
            )
            from MediaPlayer import (  # type: ignore
                MPNowPlayingInfoCenter,
                MPMusicPlayerController,
            )
            _MPNowPlayingInfoCenter = MPNowPlayingInfoCenter
            _MPMusicPlayerController = MPMusicPlayerController
        except Exception:
            pass
    except Exception:
        pass


# =====================================================
# Helpers
# =====================================================
def _init_winrt_apartment() -> bool:
    """
    Some environments require initializing the WinRT apartment in the
    current thread before calling GSMTC APIs.
    Best-effort across winrt/winsdk variations.
    """
    # Try winrt package helpers
    try:
        import winrt  # type: ignore
        if hasattr(winrt, "init_apartment"):
            winrt.init_apartment()  # type: ignore
            return True
    except Exception:
        pass

    # Try internal winrt hook
    try:
        import winrt._winrt as _w  # type: ignore
        if hasattr(_w, "init_apartment"):
            _w.init_apartment()  # type: ignore
            return True
    except Exception:
        pass

    return False

def now_ts() -> int:
    return int(time.time())


def _sha1(x: Any) -> str:
    import hashlib
    return hashlib.sha1(str(x).encode("utf-8", errors="ignore")).hexdigest()


def _safe_str(x: Any, default: str = "") -> str:
    try:
        return default if x is None else str(x)
    except Exception:
        return default


def _clamp_text(t: str, n: int = 1400) -> str:
    t = (t or "").strip()
    if len(t) <= n:
        return t
    return t[: n - 3].rstrip() + "..."


def _td_total_seconds(td) -> Optional[float]:
    try:
        return float(td.total_seconds())
    except Exception:
        return None


def _track_sig(st: Dict[str, Any]) -> str:
    return _sha1("|".join([
        _safe_str(st.get("title"), ""),
        _safe_str(st.get("artist"), ""),
        _safe_str(st.get("album"), ""),
        _safe_str(st.get("source_app"), ""),
    ]))


def _format_track_line(st: Dict[str, Any]) -> str:
    title = (st.get("title") or "").strip()
    artist = (st.get("artist") or "").strip()
    album = (st.get("album") or "").strip()

    if title and artist:
        base = f"{artist} — {title}"
    else:
        base = title or artist or "(unknown track)"

    if album:
        base += f"  •  {album}"
    return base


# =====================================================
# GSMTC async helpers
# =====================================================

async def _get_manager():
    return await _GSMTC.request_async()  # type: ignore


async def _pick_session(manager):
    """
    Prefer current session, else enumerate all sessions and pick:
      1) PLAYING
      2) PAUSED with metadata
      3) any session with metadata
    """
    # 1) try current session first
    try:
        s = manager.get_current_session()
        if s is not None:
            return s
    except Exception:
        pass

    # 2) enumerate sessions
    sessions = []
    try:
        sessions = list(manager.get_sessions() or [])
    except Exception:
        sessions = []

    best = None
    best_rank = -1

    for s in sessions:
        try:
            pb = s.get_playback_info()
            status = pb.playback_status if pb is not None else None

            # default rank
            rank = 0

            # playback rank
            if status is not None:
                try:
                    if status == _PB.PLAYING:  # type: ignore
                        rank = 100
                    elif status == _PB.PAUSED:  # type: ignore
                        rank = 60
                    else:
                        rank = 10
                except Exception:
                    rank = 10

            # metadata bump
            try:
                props = await s.try_get_media_properties_async()
                title = _safe_str(getattr(props, "title", ""), "") if props is not None else ""
                artist = _safe_str(getattr(props, "artist", ""), "") if props is not None else ""
                if (title or artist):
                    rank += 15
            except Exception:
                pass

            if rank > best_rank:
                best = s
                best_rank = rank
        except Exception:
            continue

    return best



async def _read_now_playing(manager) -> Tuple[bool, Dict[str, Any]]:
    state: Dict[str, Any] = {
        "playing": False,
        "title": "",
        "artist": "",
        "album": "",
        "source_app": "",
        "position_sec": None,
        "duration_sec": None,
        "remaining_sec": None,
        "ts": now_ts(),
    }

    try:
        session = await _pick_session(manager)
        if session is None:
            return True, state

        pb = session.get_playback_info()
        status = pb.playback_status if pb is not None else None
        playing = bool(status == _PB.PLAYING) if status is not None else False  # type: ignore
        # Expose raw playback status as a simple string for consumers
        try:
            if status == _PB.PLAYING:  # type: ignore
                status_str = "playing"
            elif status == _PB.PAUSED:  # type: ignore
                status_str = "paused"
            elif status is None:
                status_str = "unknown"
            else:
                # Fallback to a lowercase name or repr
                try:
                    status_str = str(status).lower()
                except Exception:
                    status_str = "other"
        except Exception:
            status_str = "other"

        state["playing"] = playing
        state["playback_status"] = status_str

        try:
            state["source_app"] = _safe_str(session.source_app_user_model_id, "")
        except Exception:
            state["source_app"] = ""

        props = await session.try_get_media_properties_async()
        if props is not None:
            state["title"] = _safe_str(getattr(props, "title", ""), "")
            state["artist"] = _safe_str(getattr(props, "artist", ""), "")
            state["album"] = _safe_str(getattr(props, "album_title", ""), "")

        try:
            tl = session.get_timeline_properties()
            if tl is not None:
                pos = getattr(tl, "position", None)
                end = getattr(tl, "end_time", None)

                pos_s = _td_total_seconds(pos)
                end_s = _td_total_seconds(end)

                state["position_sec"] = pos_s
                state["duration_sec"] = end_s

                if isinstance(pos_s, (int, float)) and isinstance(end_s, (int, float)) and end_s > 0:
                    state["remaining_sec"] = max(0.0, float(end_s) - float(pos_s))
        except Exception:
            pass

        return True, state

    except Exception:
        return False, state


async def _control(manager, cmd: str) -> bool:
    """
    cmd: play_pause | next | prev | stop | play | pause
    Best-effort; many apps restrict these.
    """
    try:
        session = await _pick_session(manager)
        if session is None:
            return False

        # winsdk/winrt names differ slightly across bindings; try safest paths
        cmd = (cmd or "").strip().lower()

        if cmd in ("play_pause", "toggle"):
            try:
                r = await session.try_toggle_play_pause_async()
                return bool(r)
            except Exception:
                pass

        if cmd == "pause":
            try:
                r = await session.try_pause_async()
                return bool(r)
            except Exception:
                pass

        if cmd == "play":
            try:
                r = await session.try_play_async()
                return bool(r)
            except Exception:
                pass

        if cmd == "stop":
            try:
                r = await session.try_stop_async()
                return bool(r)
            except Exception:
                pass

        if cmd in ("next", "skip"):
            try:
                r = await session.try_skip_next_async()
                return bool(r)
            except Exception:
                pass

        if cmd in ("prev", "previous", "back"):
            try:
                r = await session.try_skip_previous_async()
                return bool(r)
            except Exception:
                pass

        return False
    except Exception:
        return False


# =====================================================
# Mac OS Media Control (via PyObjC)
# =====================================================

def _read_now_playing_mac() -> Tuple[bool, Dict[str, Any]]:
    """
    Mac implementation using MPNowPlayingInfoCenter and AppleScript
    Returns: (success: bool, state: dict)
    """
    state: Dict[str, Any] = {
        "playing": False,
        "title": "",
        "artist": "",
        "album": "",
        "source_app": "",
        "position_sec": None,
        "duration_sec": None,
        "remaining_sec": None,
        "playback_status": "unknown",
        "ts": now_ts(),
    }

    if not IS_MAC:
        return False, state

    try:
        # Try to get now playing info from MPNowPlayingInfoCenter
        if _MPNowPlayingInfoCenter is not None:
            center = _MPNowPlayingInfoCenter.defaultCenter()
            info = center.nowPlayingInfo()
            
            if info:
                # Extract metadata
                title = info.get("kMPMediaItemPropertyTitle") or info.get("MPMediaItemPropertyTitle")
                artist = info.get("kMPMediaItemPropertyArtist") or info.get("MPMediaItemPropertyArtist")
                album = info.get("kMPMediaItemPropertyAlbumTitle") or info.get("MPMediaItemPropertyAlbumTitle")
                duration = info.get("MPNowPlayingInfoPropertyElapsedPlaybackTime")
                playback_rate = info.get("MPNowPlayingInfoPropertyPlaybackRate", 0)
                
                state["title"] = _safe_str(title)
                state["artist"] = _safe_str(artist)
                state["album"] = _safe_str(album)
                
                # Playback rate > 0 means playing
                state["playing"] = bool(playback_rate and float(playback_rate) > 0)
                state["playback_status"] = "playing" if state["playing"] else "paused"
                
                if duration is not None:
                    try:
                        state["duration_sec"] = float(duration)
                    except Exception:
                        pass
                
                return True, state
    except Exception:
        pass

    # Fallback: Use AppleScript to query Music.app or Spotify
    try:
        import subprocess
        
        # Try Music.app first
        script = '''
        tell application "Music"
            if it is running then
                if player state is playing then
                    set trackName to name of current track
                    set trackArtist to artist of current track
                    set trackAlbum to album of current track
                    set trackPos to player position
                    set trackDur to duration of current track
                    return trackName & "|" & trackArtist & "|" & trackAlbum & "|playing|" & trackPos & "|" & trackDur
                else if player state is paused then
                    set trackName to name of current track
                    set trackArtist to artist of current track
                    set trackAlbum to album of current track
                    set trackPos to player position
                    set trackDur to duration of current track
                    return trackName & "|" & trackArtist & "|" & trackAlbum & "|paused|" & trackPos & "|" & trackDur
                else
                    return "|||stopped|||"
                end if
            else
                return "|||stopped|||"
            end if
        end tell
        '''
        
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        if result.returncode == 0 and result.stdout:
            parts = result.stdout.strip().split('|')
            if len(parts) >= 6:
                state["title"] = parts[0]
                state["artist"] = parts[1]
                state["album"] = parts[2]
                state["playback_status"] = parts[3]
                state["playing"] = (parts[3] == "playing")
                state["source_app"] = "Music.app"
                
                try:
                    pos = float(parts[4])
                    dur = float(parts[5])
                    state["position_sec"] = pos
                    state["duration_sec"] = dur
                    if dur > 0:
                        state["remaining_sec"] = max(0.0, dur - pos)
                except Exception:
                    pass
                
                return True, state
    except Exception:
        pass

    # Try Spotify as fallback
    try:
        import subprocess
        
        script = '''
        tell application "Spotify"
            if it is running then
                if player state is playing then
                    set trackName to name of current track
                    set trackArtist to artist of current track
                    set trackAlbum to album of current track
                    set trackPos to player position
                    set trackDur to duration of current track
                    return trackName & "|" & trackArtist & "|" & trackAlbum & "|playing|" & trackPos & "|" & trackDur
                else if player state is paused then
                    set trackName to name of current track
                    set trackArtist to artist of current track
                    set trackAlbum to album of current track
                    set trackPos to player position
                    set trackDur to duration of current track
                    return trackName & "|" & trackArtist & "|" & trackAlbum & "|paused|" & trackPos & "|" & trackDur
                else
                    return "|||stopped|||"
                end if
            else
                return "|||stopped|||"
            end if
        end tell
        '''
        
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        if result.returncode == 0 and result.stdout:
            parts = result.stdout.strip().split('|')
            if len(parts) >= 6:
                state["title"] = parts[0]
                state["artist"] = parts[1]
                state["album"] = parts[2]
                state["playback_status"] = parts[3]
                state["playing"] = (parts[3] == "playing")
                state["source_app"] = "Spotify"
                
                try:
                    pos = float(parts[4])
                    dur = float(parts[5]) / 1000.0  # Spotify returns milliseconds
                    state["position_sec"] = pos
                    state["duration_sec"] = dur
                    if dur > 0:
                        state["remaining_sec"] = max(0.0, dur - pos)
                except Exception:
                    pass
                
                return True, state
    except Exception:
        pass

    return False, state


def _control_mac(cmd: str) -> bool:
    """
    Mac media control via AppleScript
    cmd: play_pause | next | prev | stop | play | pause
    """
    if not IS_MAC:
        return False

    try:
        import subprocess
        
        cmd = (cmd or "").strip().lower()
        
        # Try Music.app first, then Spotify
        for app in ["Music", "Spotify"]:
            script = None
            
            if cmd in ("play_pause", "toggle"):
                script = f'tell application "{app}" to playpause'
            elif cmd == "play":
                script = f'tell application "{app}" to play'
            elif cmd == "pause":
                script = f'tell application "{app}" to pause'
            elif cmd == "stop":
                script = f'tell application "{app}" to stop'
            elif cmd in ("next", "skip"):
                script = f'tell application "{app}" to next track'
            elif cmd in ("prev", "previous", "back"):
                script = f'tell application "{app}" to previous track'
            
            if script:
                try:
                    result = subprocess.run(
                        ['osascript', '-e', script],
                        capture_output=True,
                        timeout=2
                    )
                    if result.returncode == 0:
                        return True
                except Exception:
                    continue
        
        return False
    except Exception:
        return False


# =====================================================
# Feed Worker
# =====================================================

def feed_worker(stop_event, mem, cfg, runtime=None):

    StationEvent = None
    event_q = None
    ui_q = None
    ui_cmd_q = None
    log = None
    producer_kick = None   # 👈 ADD THIS

    # -----------------------------
    # Runtime injection
    # -----------------------------
    if isinstance(runtime, dict):
        StationEvent   = runtime.get("StationEvent")
        event_q        = runtime.get("event_q")
        ui_q           = runtime.get("ui_q")
        ui_cmd_q       = runtime.get("ui_cmd_q")
        music_cmd_q    = runtime.get("music_cmd_q") # Dedicated channel
        log            = runtime.get("log")
        producer_kick = runtime.get("producer_kick")   # 👈 ADD THIS

    if StationEvent is None or event_q is None:
        return

    # If producer_kick missing, fail soft (no proactive mode)
    if producer_kick is None:
        if callable(log):
            log("feed", "music_breaks: producer_kick not injected (passive mode)")


    # -----------------------------
    # Shared MUSIC_STATE bridge
    # -----------------------------
    music_state = None
    if isinstance(runtime, dict):
        music_state = runtime.get("MUSIC_STATE")

    if not isinstance(music_state, dict):
        music_state = {}

    # Make mem point to the same dict for persistence/debug
    mem["_music_state"] = music_state


    music_state.setdefault("playing", False)

    # -----------------------------
    # Config
    # -----------------------------
    poll_sec = float(cfg.get("poll_sec", 1.0))
    emit_only_when_playing = bool(cfg.get("emit_only_when_playing", True))
    min_emit_gap_sec = float(cfg.get("min_emit_gap_sec", 3.0))
    pri_track = float(cfg.get("track_start_priority", 92.0))

    angle = str(cfg.get(
        "angle",
        "Treat this as a music break. Do NOT talk over the track."
    )).strip()

    host_hint = str(cfg.get(
        "host_hint",
        "Music break — let the track breathe."
    )).strip()

    allow_apps = cfg.get("allow_apps", []) or []
    deny_apps  = cfg.get("deny_apps", []) or []

    if not isinstance(allow_apps, list):
        allow_apps = []

    if not isinstance(deny_apps, list):
        deny_apps = []

    # -----------------------------
    # Platform-specific availability check
    # -----------------------------
    if callable(log):
        log("feed", f"music_breaks: Detected platform: {'Windows' if IS_WINDOWS else 'macOS' if IS_MAC else 'Unknown'}")
    
    if IS_WINDOWS and _GSMTC is None:
        if callable(log):
            log("feed", "music_breaks: Windows media API (winsdk/winrt) missing — disabled.")
        while not stop_event.is_set():
            time.sleep(2.0)
        return
    
    if IS_MAC:
        # Mac doesn't require initialization; uses AppleScript
        if callable(log):
            log("feed", "music_breaks: Using macOS AppleScript media control")

    if not IS_WINDOWS and not IS_MAC:
        if callable(log):
            log("feed", "music_breaks: Unsupported platform — disabled.")
        while not stop_event.is_set():
            time.sleep(2.0)
        return

    import asyncio

    state_mem = mem.setdefault("_music_breaks_state", {})
    last_emit_ts = int(state_mem.get("last_emit_ts", 0) or 0)
    last_sig     = str(state_mem.get("last_sig", "") or "")
    last_remaining = state_mem.get("last_remaining")


    # =====================================================
    # Init GSMTC manager (Windows only)
    # =====================================================

    mgr = None

    if IS_WINDOWS:
        async def _init_mgr():
            nonlocal mgr
            mgr = await _get_manager()

        try:
            asyncio.run(_init_mgr())
        except Exception as e:
            if callable(log):
                log("feed", f"music_breaks Windows init failed: {e}")
            while not stop_event.is_set():
                time.sleep(2.0)
            return

        if mgr is None:
            if callable(log):
                log("feed", "music_breaks: GSMTC manager None")
            while not stop_event.is_set():
                time.sleep(2.0)
            return

    # =====================================================
    # Command listener thread
    # =====================================================

    def _cmd_listener():

        # Prefer dedicated queue if available, else shared (which might race)
        q = music_cmd_q if music_cmd_q else ui_cmd_q

        if not q:
            return

        async def _cmd_loop():
            while not stop_event.is_set():
                try:
                    evt, payload = q.get(timeout=0.25)
                except Exception:
                    continue

                if evt != "music_cmd":
                    continue


                cmd = ""
                if isinstance(payload, dict):
                    cmd = str(payload.get("cmd", "")).strip().lower()

                if not cmd:
                    continue

                # Platform-specific control
                if IS_WINDOWS:
                    ok = await _control(mgr, cmd)
                elif IS_MAC:
                    ok = _control_mac(cmd)
                else:
                    ok = False

                try:
                    if ui_q:
                        ui_q.put(("toast", {
                            "text": f"music: {cmd} {'OK' if ok else 'NO'}"
                        }))
                except Exception:
                    pass

        try:
            asyncio.run(_cmd_loop())
        except Exception:
            return

    if music_cmd_q or ui_cmd_q:
        threading.Thread(
            target=_cmd_listener,
            daemon=True
        ).start()

    # =====================================================
    # Poll loop
    # =====================================================

    async def _loop():
        nonlocal last_emit_ts, last_sig, last_remaining
        mem.setdefault("_station_start_ts", now_ts())

        first_poll = True

        def prune_music_candidates():
            cands = mem.get("feed_candidates", [])
            if not cands:
                 return
            # Remove ALL old music_breaks candidates to avoid stale track info
            # (e.g. host talking about a track that just finished as if it's starting)
            clean = [c for c in cands if c.get("source") != "music_breaks"]
            mem["feed_candidates"] = clean

        while not stop_event.is_set():

            # Platform-specific read
            if IS_WINDOWS:
                ok, st = await _read_now_playing(mgr)
            elif IS_MAC:
                ok, st = _read_now_playing_mac()
            else:
                ok, st = False, {}

            now = now_ts()

            # -----------------------------
            # Throttled poll logging
            # -----------------------------
            if callable(log):
                last_log = state_mem.get("last_poll_log", 0)
                if now - last_log >= 5:
                    state_mem["last_poll_log"] = now
                    log(
                        "music",
                        f"poll playing={st.get('playing')} "
                        f"{st.get('artist')} — {st.get('title')} "
                        f"rem={st.get('remaining_sec')}"
                    )


            if not ok:
                await asyncio.sleep(max(poll_sec, 0.5))
                continue
            # -----------------------------
            # Producer-scheduled return to music
            # -----------------------------

            # -----------------------------
            # App allow/deny
            # -----------------------------
            appid = (st.get("source_app") or "").lower()

            if deny_apps and any(s.lower() in appid for s in deny_apps):
                st["playing"] = False

            if allow_apps and not any(s.lower() in appid for s in allow_apps):
                st["playing"] = False

            # -----------------------------
            # Track signature
            # -----------------------------
            sig = _track_sig(st)
            st["track_sig"] = sig

            # -----------------------------
            # Timing memory
            # -----------------------------
            if sig and sig != state_mem.get("current_sig"):
                state_mem["current_sig"] = sig
                state_mem["track_start_ts"] = now
                state_mem["boundary_fired"] = False

            track_start_ts = state_mem.get("track_start_ts")
            
            rem = st.get("remaining_sec")
            last_rem = state_mem.get("last_remaining")

            if first_poll:
                last_rem = rem
                state_mem["last_remaining"] = rem
                first_poll = False

            # -----------------------------
            # ALWAYS update MUSIC_STATE (for UI)
            # -----------------------------
            try:
                allow_bg = bool(music_state.get("allow_background_music", False))
                duck     = music_state.get("duck_level", 0.25)
                fade     = music_state.get("fade_sec", 1.25)

                music_state.update({
                    "playing": bool(st.get("playing")),
                    "playback_status": st.get("playback_status") or "",
                    "title": st.get("title") or "",
                    "artist": st.get("artist") or "",
                    "album": st.get("album") or "",
                    "source_app": st.get("source_app") or "",
                    "position_sec": st.get("position_sec"),
                    "duration_sec": st.get("duration_sec"),
                    "remaining_sec": rem,
                    "track_sig": sig,
                    "ts": st.get("ts"),
                    "allow_background_music": allow_bg,
                    "duck_level": duck,
                    "fade_sec": fade,
                })
            
            except Exception:
                pass

            # =====================================================
            # TALK CONTROL (after state update)
            # =====================================================
            # -----------------------------
            # Producer handoff interrupt
            # -----------------------------

            want_ts = mem.get("_producer_wants_talk")

            if isinstance(want_ts, int) and (now_ts() - want_ts) <= 6:
                try:
                    if IS_WINDOWS:
                        await _control(mgr, "pause")
                    elif IS_MAC:
                        _control_mac("pause")
                except Exception:
                    pass

                if callable(log):
                    log("music", "producer requested talk → pausing music")

                mem.pop("_producer_wants_talk", None)

            # =====================================================
            # ✅ DYNAMIC RESUME (when talk queue is low)
            # =====================================================
            # =====================================================
            # ✅ EXPLICIT PRODUCER MUSIC INTENT (OPTION A)
            # =====================================================

            producer_wants_music = mem.get("_producer_wants_music")

            # Producer explicitly wants music running
            # But only actually resume if audio queue is clear (no TTS playing)
            if producer_wants_music is True and not st.get("playing"):
                # Get audio queue depth
                audio_q_size = 0
                try:
                    if isinstance(runtime, dict):
                        a = runtime.get("audio_queue_size", 0)
                        if callable(a):
                            audio_q_size = int(a())
                        else:
                            audio_q_size = int(a or 0)
                except Exception:
                    audio_q_size = 0
                
                # Get DB stats from runtime shared memory (to detect pending bridge segments)
                db_q = int(mem.get("_sys_db_queued", 0) or 0)
                db_c = int(mem.get("_sys_db_claimed", 0) or 0)
                db_busy = (db_q + db_c) > 0

                # Only resume if audio is truly clear OR if background music is permitted (ducking mode)
                allow_bg = bool(music_state.get("allow_background_music", False))
                # RELAXED: treat <= 8 as clear because runtime maintains a buffer of ~8.
                # BUT: if DB is busy (bridge pending), we treat it as NOT clear.
                is_clear = ((audio_q_size <= 8) and (not db_busy)) or allow_bg

                # STUCK QUEUE RECOVERY: If producer wants music but audio_q refuses to drain, force resume
                resume_wait_ts = mem.get("_resume_wait_ts")

                # Track queue movement to avoid false positives on long queues (reset timer on activity)
                current_load = db_q + db_c + audio_q_size
                last_load = mem.get("_stuck_monitor_load", -1)
                
                if not is_clear:
                    # If queue is draining (or changing), it's active -> reset timeout
                    if last_load != -1 and current_load != last_load:
                        resume_wait_ts = now
                        mem["_resume_wait_ts"] = now
                    
                    mem["_stuck_monitor_load"] = current_load

                    if not resume_wait_ts:
                        mem["_resume_wait_ts"] = now
                    elif (now - resume_wait_ts) > 45:
                        if callable(log):
                            log("music", f"Forcing music resume (audio_q={audio_q_size} db={db_q+db_c} stuck for {now - resume_wait_ts}s)")
                        is_clear = True
                
                if is_clear:
                    mem.pop("_resume_wait_ts", None)
                    try:
                        # Always skip to next track (don't resume the paused one mid-song)
                        if IS_WINDOWS:
                            await _control(mgr, "next")
                        elif IS_MAC:
                            _control_mac("next")

                        if callable(log):
                            log("music", f"Producer requested music ({'bg allowed' if allow_bg else 'queue clear'}) → skipping to next")

                    except Exception as e:
                        if callable(log):
                             log("music", f"Producer music resume failed: {e}")

                    # One-shot intent
                    mem.pop("_producer_wants_music", None)

                    # IMPORTANT: prevent stale talk intent from re-pausing
                    mem.pop("_producer_wants_talk", None)
                else:
                    # Audio still queued; keep the flag and try again next poll
                    if callable(log):
                        log_every(mem, "music_resume_waiting", 3, "music", f"Producer wants music but audio_q={audio_q_size} db={db_q}+{db_c} (waiting for speech)")

            # =====================================================
            # ✅ DYNAMIC RESUME (when talk queue is low)
            # =====================================================
            paused_for_talk_ts = mem.get("_music_paused_for_talk")

            # If we paused for talk and music is still not playing
            # (only resume if WE were the ones who paused it)
            if isinstance(paused_for_talk_ts, int) and not st.get("playing"):
                
                # Sanity check: don't try to resume if we've been running less than 30 seconds
                # (prevents resume on fresh startup when music was already paused)
                station_uptime = now - mem.get("_station_start_ts", now)
                if station_uptime < 30:
                    continue  # Skip resume logic during startup period
                
                # Get audio queue depth from runtime
                # Get audio queue depth from runtime (runtime provides a callable)
                audio_q_size = 0
                try:
                    if isinstance(runtime, dict):
                        a = runtime.get("audio_queue_size", 0)
                        if callable(a):
                            audio_q_size = int(a())
                        else:
                            audio_q_size = int(a or 0)
                except Exception:
                    audio_q_size = 0
                
                # How long since we paused?
                time_since_pause = now - paused_for_talk_ts
                
                # DO NOT auto-resume if audio is still queued - let producer decide
                # Producer decision logic (respects mix.weights) has full authority
                # Only clear the pause state when audio queue is truly empty, to stop
                # the dynamic resume from repeatedly trying to resume
                if audio_q_size == 0:
                    # Audio is done; let producer decide via normal decision loop
                    # Clear pause tracking so this doesn't keep running
                    mem.pop("_music_paused_for_talk", None)

            
            # ✅ Producer controls resume via decision logic, not scheduled resume

            if not st.get("playing"):
                # Gated check: Has the break duration elapsed?
                deadline = mem.get("_mb_break_deadline", 0)
                time_remaining = deadline - now
                
                # If we are inside the forced talk window, suppress resume
                # Only suppress the producer candidate flag from being set in runtime.py?
                # Actually, runtime.py logic will see "music not playing" and try to candidate it.
                # But here we can just LOG that we are waiting.
                # Actually, in runtime.py the candidate is set if music not playing.
                # The PRODUCER decides "YES/NO".
                # We can inject a "veto" by forcefully clearing the candidate if time remains?
                
                if time_remaining > 0:
                     # Suppress music candidate in memory so producer doesn't try to resume
                     c = mem.get("_producer_wants_music_candidate")
                     if c:
                         mem.pop("_producer_wants_music_candidate", None)
                         if isinstance(time_remaining, (int, float)) and time_remaining > 1:
                             log_every(mem, "break_wait", 5, "music", f"Waiting for break duration: {int(time_remaining)}s remaining")
                
                last_idle = state_mem.get("last_idle_kick", 0)

                if now - last_idle > 10:
                    state_mem["last_idle_kick"] = now

                    if producer_kick:
                        producer_kick.set()

                    if callable(log):
                        if time_remaining > 0:
                             log("music", "No music playing (break active) → letting host take over")
                        else:
                             log("music", "No music playing (break done) → ready for resume")
                
                # Signal resume event ONCE when deadline expires
                if time_remaining <= 0 and not mem.get("_mb_resume_signaled") and deadline > 0:
                    mem["_mb_resume_signaled"] = True
                    
                    if callable(log):
                        log("music", "Break duration expired → emitting resume suggestion")
                    
                    prune_music_candidates()
                        
                    mem.setdefault("feed_candidates", []).append({
                        "id": _sha1(f"music_breaks|resume|{now}"),
                        "source": "music_breaks",
                        "event_type": "resume_suggestion",
                        "title": "Return to Music",
                        "body": "The talk break is over. Introduce the next set of music.",
                        "heur": 85.0,  # High priority
                        "key_points": ["talk break over", "music starting now"],
                        "host_hint": "Wrap up the chat and throw to the music.",
                    })

            # Producer is in charge of resume decisions. Don't auto-return.

            # =====================================================
            # TRACK START EMIT
            # =====================================================

            changed  = bool(sig and sig != last_sig)
            can_emit = (now - last_emit_ts) >= min_emit_gap_sec
            playing = bool(st.get("playing"))

            should_emit = changed and can_emit

            if emit_only_when_playing:
                should_emit = should_emit and playing

            if should_emit:
                # Increment flow counter for new song
                inc_flow = mem.get("_mb_flow_count", 0) + 1
                mem["_mb_flow_count"] = inc_flow
                
                # Check target
                target = mem.get("_mb_flow_target")
                if not isinstance(target, int) or target <= 0:
                     # Initial startup - respect config
                     cfg_min = int(cfg.get("flow_songs_min", 1))
                     cfg_max = int(cfg.get("flow_songs_max", 3))
                     cfg_rnd = bool(cfg.get("flow_songs_random", True))
                     
                     if not cfg_rnd:
                        target = cfg_min
                     else:
                        target = random.randint(min(cfg_min, cfg_max), max(cfg_min, cfg_max))
                        
                     mem["_mb_flow_target"] = target
                
                if callable(log):
                    log("music", f"Music flow: song {inc_flow}/{target}")

                line = _format_track_line(st)

                payload = {
                    "title": "Track started",
                    "body": line,
                    "angle": angle,
                    "why": "Windows media session track changed.",
                    "key_points": ["music break", "resume when track ends"],
                    "host_hint": host_hint,
                    "track": {
                        "title": st.get("title") or "",
                        "artist": st.get("artist") or "",
                        "album": st.get("album") or "",
                        "source_app": st.get("source_app") or "",
                        "position_sec": st.get("position_sec"),
                        "duration_sec": st.get("duration_sec"),
                        "remaining_sec": rem,
                        "track_sig": sig,
                    },
                    "ts": now,
                }

                evt = StationEvent(
                    source="music_breaks",
                    type="track_start",
                    ts=now,
                    severity=0.0,
                    priority=float(pri_track),
                    payload=payload
                )

                event_q.put(evt)

                prune_music_candidates()

                mem.setdefault("feed_candidates", []).append({
                    "id": _sha1(f"music_breaks|track_start|{now}|{random.random()}"),
                    "post_id": _sha1(f"music_breaks|{sig}"),
                    "source": "music_breaks",
                    "event_type": "track_start",
                    "title": "Music break",
                    "body": _clamp_text(line, 800),
                    "comments": [],
                    "heur": float(pri_track),
                    "payload": payload,
                })

                last_emit_ts = now
                last_sig = sig

                state_mem["last_emit_ts"] = last_emit_ts
                state_mem["last_sig"] = last_sig

                if callable(log):
                    log("feed", f"music_breaks emit: {line}")

            # =====================================================
            # BOUNDARY DETECTION
            # =====================================================
            time_boundary = (
                isinstance(rem, (int, float)) and
                isinstance(last_rem, (int, float)) and
                last_rem > 5 and
                rem <= 5
            )

            # Check logic flow
            should_break = False
            if time_boundary:
                # Check if we hit song target
                curr_flow = mem.get("_mb_flow_count", 0)
                target_flow = mem.get("_mb_flow_target", 1)
                
                if curr_flow >= target_flow:
                    should_break = True
                    if callable(log):
                        log("music", f"Flow complete ({curr_flow}/{target_flow}) → triggering break")
                else:
                    if callable(log):
                        log("music", f"Flow continuing ({curr_flow}/{target_flow}) → skip break")

            boundary_hit = should_break

            state_mem["last_remaining"] = rem

            # =====================================================
            # FIRE BOUNDARY + SOFT DJ DECISION
            # =====================================================

            if boundary_hit and not state_mem.get("boundary_fired"):

                state_mem["boundary_fired"] = True
                
                # --- RESET FLOW, SETUP TALK BREAK ---
                cfg = mem.get("config", {}) or {}
                
                # New Flow Target
                f_min = int(cfg.get("flow_songs_min", 1))
                f_max = int(cfg.get("flow_songs_max", 3))
                f_rnd = bool(cfg.get("flow_songs_random", True))
                
                if not f_rnd:
                    next_target = f_min
                else:
                    next_target = random.randint(min(f_min, f_max), max(f_min, f_max))
                
                # Reset flow count for next time
                mem["_mb_flow_count"] = 0
                mem["_mb_flow_target"] = next_target
                
                # Talk Duration
                t_min = int(cfg.get("break_duration_min", 20))
                t_max = int(cfg.get("break_duration_max", 150))
                t_rnd = bool(cfg.get("break_duration_random", True))
                
                if not t_rnd:
                    talk_dur = t_min
                else:
                    talk_dur = random.randint(min(t_min, t_max), max(t_min, t_max))
                    
                mem["_mb_break_deadline"] = now + talk_dur
                mem["_mb_break_start_ts"] = now
                mem["_mb_resume_signaled"] = False
                
                if callable(log):
                    log("music", f"Scheduling break for {talk_dur}s (until {now+talk_dur}). Next flow target: {next_target} songs.")

                line = _format_track_line(st)

                payload = {
                    "title": "Track boundary",
                    "body": line,
                    "angle": "Throw it back to a song break.",
                    "why": "Track nearing completion.",
                    "host_hint": "Decide whether to continue music or pivot to live talk.",
                    "track": {
                        "title": st.get("title") or "",
                        "artist": st.get("artist") or "",
                        "album": st.get("album") or "",
                        "remaining_sec": rem,
                        "track_sig": sig,
                    },
                    "ts": now,
                }

                evt = StationEvent(
                    source="music_breaks",
                    type="track_boundary",
                    ts=now,
                    severity=0.0,
                    priority=85.0,
                    payload=payload
                )

                event_q.put(evt)

                prune_music_candidates()

                mem.setdefault("feed_candidates", []).append({
                    "id": _sha1(f"music_breaks|boundary|{now}|{random.random()}"),
                    "post_id": _sha1(f"music_breaks|boundary|{sig}"),
                    "source": "music_breaks",
                    "event_type": "track_boundary",
                    "title": "Music boundary",
                    "body": _clamp_text(line, 800),
                    "comments": [],
                    "heur": 85.0,
                    "payload": payload,
                })

                mem["_music_boundary_active"] = now

                if producer_kick:
                    producer_kick.set()



                if callable(log):
                    log("feed", f"music_breaks boundary fired → {line}")
            if st.get("playing") and not music_state.get("allow_background_music", False):
                await asyncio.sleep(max(poll_sec, 0.5))
                continue

            await asyncio.sleep(max(poll_sec, 0.5))


    # -----------------------------
    # Run loop
    # -----------------------------

    try:
        asyncio.run(_loop())
    except Exception as e:
        if callable(log):
            log("feed", f"music_breaks loop crashed: {e}")
        while not stop_event.is_set():
            time.sleep(2.0)


# =====================================================
# Widget: Now Playing + Controls + Background Toggle
# =====================================================
def register_widgets(registry, runtime):

    tk = runtime["tk"]
    ui_cmd_q = runtime.get("ui_cmd_q")
    music_state = runtime.get("MUSIC_STATE")   # 👈 UI bridge dict
    log = runtime.get("log")

    if music_state is None:
        if callable(log):
            log("music", "music_now_playing widget skipped: no MUSIC_STATE")
        return

    BG = "#0e0e0e"
    SURFACE = "#121212"
    CARD = "#161616"
    EDGE = "#2a2a2a"
    TXT = "#e8e8e8"
    MUTED = "#9a9a9a"
    ACCENT = "#4cc9f0"
    GOOD = "#2ee59d"

    class MusicNowPlayingWidget:

        def __init__(self, parent, runtime):
            self.tk = tk
            self.runtime = runtime

            self.root = tk.Frame(parent, bg=BG)

            # Scrollable wrapper
            canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0)
            vsb = tk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=vsb.set)
            
            vsb.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            
            scroll_host = tk.Frame(canvas, bg=BG)
            win_id = canvas.create_window((0, 0), window=scroll_host, anchor="nw")
            
            def _on_frame_configure(event):
                canvas.configure(scrollregion=canvas.bbox("all"))
            scroll_host.bind("<Configure>", _on_frame_configure)
            
            def _on_canvas_configure(event):
                canvas.itemconfig(win_id, width=event.width)
            canvas.bind("<Configure>", _on_canvas_configure)

            box = tk.Frame(
                scroll_host,
                bg=SURFACE,
                highlightbackground=EDGE,
                highlightthickness=1
            )
            box.pack(fill="both", expand=True, padx=10, pady=10)

            # ---------------- Header

            hdr = tk.Frame(box, bg=SURFACE)
            hdr.pack(fill="x", padx=10, pady=(10, 6))

            self.h1 = tk.Label(
                hdr,
                text="MUSIC",
                fg=ACCENT,
                bg=SURFACE,
                font=("Segoe UI", 10, "bold")
            )
            self.h1.pack(side="left")

            self.status = tk.Label(
                hdr,
                text="• idle",
                fg=MUTED,
                bg=SURFACE,
                font=("Segoe UI", 10)
            )
            self.status.pack(side="right")

            # ---------------- Track line

            self.track = tk.Label(
                box,
                text="(no track)",
                fg=TXT,
                bg=SURFACE,
                font=("Segoe UI", 12, "bold"),
                justify="left",
                anchor="w",
                wraplength=420
            )
            self.track.pack(fill="x", padx=10, pady=(0, 4))

            self.meta = tk.Label(
                box,
                text="",
                fg=MUTED,
                bg=SURFACE,
                font=("Segoe UI", 10),
                justify="left",
                anchor="w",
                wraplength=420
            )
            self.meta.pack(fill="x", padx=10, pady=(0, 8))

            # ---------------- Controls

            controls = tk.Frame(box, bg=SURFACE)
            controls.pack(fill="x", padx=10, pady=(0, 8))

            def btn(txt, cmd):
                b = tk.Button(
                    controls,
                    text=txt,
                    command=cmd,
                    bg=CARD,
                    fg=TXT,
                    relief="flat",
                    padx=10,
                    pady=6,
                    activebackground="#1f1f1f"
                )
                b.pack(side="left", padx=(0, 8))
                return b

            def send(cmd: str):
                try:
                    if ui_cmd_q:
                        ui_cmd_q.put(("music_cmd", {"cmd": cmd}))
                except Exception:
                    pass

            btn("⏮", lambda: send("prev"))
            btn("⏯", lambda: send("play_pause"))
            btn("⏭", lambda: send("next"))
            btn("⏹", lambda: send("stop"))

            # ---------------- Background options

            opts = tk.Frame(box, bg=SURFACE)
            opts.pack(fill="x", padx=10, pady=(0, 10))

            self.var_bg = tk.BooleanVar(
                value=bool(music_state.get("allow_background_music", False))
            )

            self.chk = tk.Checkbutton(
                opts,
                text="Allow background music (duck while host talks)",
                variable=self.var_bg,
                bg=SURFACE,
                fg=TXT,
                selectcolor=SURFACE,
                activebackground=SURFACE,
                activeforeground=TXT,
                command=self._on_toggle_bg
            )
            self.chk.pack(anchor="w", pady=(0, 6))

            # Duck slider

            row1 = tk.Frame(opts, bg=SURFACE)
            row1.pack(fill="x", pady=(0, 6))

            tk.Label(
                row1,
                text="Duck level",
                fg=MUTED,
                bg=SURFACE,
                font=("Segoe UI", 9)
            ).pack(side="left")

            self.duck = tk.DoubleVar(
                value=float(music_state.get("duck_level", 0.25) or 0.25)
            )

            tk.Scale(
                row1,
                from_=0.0,
                to=1.0,
                resolution=0.05,
                orient="horizontal",
                variable=self.duck,
                bg=SURFACE,
                fg=TXT,
                highlightthickness=0,
                command=self._on_duck_change,
                length=220
            ).pack(side="right")

            # Fade slider

            row2 = tk.Frame(opts, bg=SURFACE)
            row2.pack(fill="x")

            tk.Label(
                row2,
                text="Fade (sec)",
                fg=MUTED,
                bg=SURFACE,
                font=("Segoe UI", 9)
            ).pack(side="left")

            self.fade = tk.DoubleVar(
                value=float(music_state.get("fade_sec", 1.25) or 1.25)
            )

            tk.Scale(
                row2,
                from_=0.05,
                to=5.0,
                resolution=0.05,
                orient="horizontal",
                variable=self.fade,
                bg=SURFACE,
                fg=TXT,
                highlightthickness=0,
                command=self._on_fade_change,
                length=220
            ).pack(side="right")
            
            # ---------------- Break/Flow options
            
            pacing = tk.LabelFrame(box, text="Pacing", bg=SURFACE, fg=TXT, font=("Segoe UI", 8, "bold"), bd=1)
            pacing.pack(fill="x", padx=10, pady=10)
            
            # Talk Config (Min/Max/Random)
            
            def add_slider_row(parent, label, min_val, max_val, var, cmd=None):
                row = tk.Frame(parent, bg=SURFACE)
                row.pack(fill="x", pady=2)
                tk.Label(row, text=label, fg=MUTED, bg=SURFACE, width=15, anchor="w", font=("Segoe UI", 8)).pack(side="left")
                tk.Scale(
                    row, from_=min_val, to=max_val, orient="horizontal", variable=var,
                    bg=SURFACE, fg=TXT, highlightthickness=0, length=200, command=cmd
                ).pack(side="right")
                
            cfg = self.runtime.get("config", {}) or {}
            
            self.v_break_min = tk.IntVar(value=cfg.get("break_duration_min", 20))
            self.v_break_max = tk.IntVar(value=cfg.get("break_duration_max", 150))
            self.v_break_rnd = tk.BooleanVar(value=cfg.get("break_duration_random", True))
            
            tr = tk.Frame(pacing, bg=SURFACE)
            tr.pack(fill="x", pady=(2,6))
            tk.Checkbutton(tr, text="Random Talk Break", variable=self.v_break_rnd, bg=SURFACE, fg=TXT, selectcolor=SURFACE, activebackground=SURFACE, activeforeground=TXT, command=self._on_cfg_change).pack(side="left")
            
            add_slider_row(pacing, "Talk Min (s)", 5, 300, self.v_break_min, self._on_cfg_change)
            add_slider_row(pacing, "Talk Max (s)", 30, 600, self.v_break_max, self._on_cfg_change)
            
            # Flow Config
            
            self.v_flow_min = tk.IntVar(value=cfg.get("flow_songs_min", 1))
            self.v_flow_max = tk.IntVar(value=cfg.get("flow_songs_max", 3))
            self.v_flow_rnd = tk.BooleanVar(value=cfg.get("flow_songs_random", True))

            fr = tk.Frame(pacing, bg=SURFACE)
            fr.pack(fill="x", pady=(8,2))
            tk.Checkbutton(fr, text="Random Song Flow", variable=self.v_flow_rnd, bg=SURFACE, fg=TXT, selectcolor=SURFACE, activebackground=SURFACE, activeforeground=TXT, command=self._on_cfg_change).pack(side="left")

            add_slider_row(pacing, "Flow Min (songs)", 1, 10, self.v_flow_min, self._on_cfg_change)
            add_slider_row(pacing, "Flow Max (songs)", 1, 20, self.v_flow_max, self._on_cfg_change)


            self._tick()

        # =========================
        # UI → state
        # =========================

        def _on_cfg_change(self, _v=None):
            try:
                # Update local runtime copy just in case, but MAINLY send to real runtime over queue
                updates = {
                    "break_duration_min": self.v_break_min.get(),
                    "break_duration_max": self.v_break_max.get(),
                    "break_duration_random": self.v_break_rnd.get(),
                    "flow_songs_min": self.v_flow_min.get(),
                    "flow_songs_max": self.v_flow_max.get(),
                    "flow_songs_random": self.v_flow_rnd.get()
                }
                
                # Use ui_cmd_q to flush to station process
                self.send_cfg(updates)
                
            except Exception:
                pass
        
        def send_cfg(self, updates):
            try:
                if ui_cmd_q:
                    ui_cmd_q.put(("update_config", {"config": updates}))
            except Exception:
                pass

        def _on_toggle_bg(self):
            try:
                self.runtime["MUSIC_STATE"]["allow_background_music"] = bool(self.var_bg.get())
            except Exception:
                pass

        def _on_duck_change(self, _v=None):
            try:
                self.runtime["MUSIC_STATE"]["duck_level"] = float(self.duck.get())
            except Exception:
                pass

        def _on_fade_change(self, _v=None):
            try:
                self.runtime["MUSIC_STATE"]["fade_sec"] = float(self.fade.get())
            except Exception:
                pass

        # =========================
        # Live refresh
        # =========================

        def _tick(self):
            self._refresh()
            try:
                self.root.after(350, self._tick)
            except Exception:
                pass

        def _refresh(self):
            try:
                st = self.runtime.get("MUSIC_STATE") or {}

                playing = bool(st.get("playing", False))

                title  = (st.get("title") or "").strip()
                artist = (st.get("artist") or "").strip()
                album  = (st.get("album") or "").strip()
                app    = (st.get("source_app") or "").strip()

                pos = st.get("position_sec")
                dur = st.get("duration_sec")
                rem = st.get("remaining_sec")

                # ---- Track line

                if title and artist:
                    line = f"{artist} — {title}"
                elif title:
                    line = title
                elif artist:
                    line = artist
                else:
                    line = "(no track)"

                self.track.config(text=line)

                # ---- Meta

                meta = []

                if album:
                    meta.append(album)

                if app:
                    meta.append(app)

                if isinstance(pos, (int, float)) and isinstance(dur, (int, float)) and dur > 0:
                    meta.append(f"{pos:.0f}s / {dur:.0f}s")
                elif isinstance(rem, (int, float)):
                    meta.append(f"{rem:.0f}s remaining")

                self.meta.config(text=" • ".join(meta))

                # ---- Status

                self.status.config(
                    text="• playing" if playing else "• idle",
                    fg=GOOD if playing else MUTED
                )

            except Exception:
                pass


    def factory(parent, runtime):
        return MusicNowPlayingWidget(parent, runtime)

    registry.register(
        "music_now_playing",
        factory,
        title="Music • Now Playing",
        default_panel="left"
    )
