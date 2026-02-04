#!/usr/bin/env python3
# plugins/video_timeline.py
#
# RadioOS plugin: "video_timeline"
# - Timeline scheduler: at T+offset (relative to when you press PLAY), ingest a video (file path or URL)
# - Ingestion: ffmpeg frame sampling -> simple scene/motion detectors -> StationEvent + emit_candidate
# - Widget: Timeline Editor (add/remove/reorder), save/load JSON, Play/Pause/Stop, live status + event tape
#
# NOTE:
# - Requires ffmpeg on PATH for best results.
# - URLs work if ffmpeg can open them directly (e.g., direct mp4 links). (YouTube needs yt-dlp; not included.)
#
# Manifest example (minimal):
# feeds:
#   video_timeline:
#     enabled: true
#     poll_sec: 0.25
#     default_capture_sec: 15
#     default_fps: 1.5
#     scene_threshold: 18        # 0..255-ish (higher = less sensitive)
#     motion_threshold: 10       # 0..255-ish
#     emit_limit_per_item: 4
#     priority:
#       scene_change: 86
#       motion_spike: 84
#       summary: 82



import base64
import dataclasses
import hashlib
import io
import json
import math
import os
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

PLUGIN_NAME = "video_timeline"


# =====================================================
# Helpers
# =====================================================


def now_ts() -> int:
    return int(time.time())

def sha1(x: Any) -> str:
    return hashlib.sha1(str(x).encode("utf-8", errors="ignore")).hexdigest()

def clamp_text(t: str, n: int = 1400) -> str:
    t = (t or "").strip()
    if len(t) <= n:
        return t
    return t[: n - 3].rstrip() + "..."

def _safe_str(x: Any, default: str = "") -> str:
    try:
        return default if x is None else str(x)
    except Exception:
        return default

def _as_float(x: Any) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None

def _as_int(x: Any) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None

def parse_hhmmss(s: str) -> Optional[float]:
    """
    Accepts:
      - "SS"
      - "MM:SS"
      - "HH:MM:SS"
      - "1h 2m 3s" (loose)
    Returns seconds (float).
    """
    if s is None:
        return None
    s = str(s).strip().lower()
    if not s:
        return None

    # Loose tokens: "1h 2m 3s"
    m = re.findall(r"(\d+(?:\.\d+)?)\s*([hms])", s)
    if m:
        total = 0.0
        for num, unit in m:
            v = float(num)
            if unit == "h":
                total += v * 3600
            elif unit == "m":
                total += v * 60
            else:
                total += v
        return total

    # Colon formats
    if ":" in s:
        parts = s.split(":")
        try:
            parts = [float(p) for p in parts]
        except Exception:
            return None
        if len(parts) == 2:
            mm, ss = parts
            return mm * 60 + ss
        if len(parts) == 3:
            hh, mm, ss = parts
            return hh * 3600 + mm * 60 + ss
        return None

    # plain seconds
    try:
        return float(s)
    except Exception:
        return None

def fmt_hhmmss(sec: float) -> str:
    sec = max(0.0, float(sec))
    s = int(sec)
    hh = s // 3600
    mm = (s % 3600) // 60
    ss = s % 60
    if hh > 0:
        return f"{hh:02d}:{mm:02d}:{ss:02d}"
    return f"{mm:02d}:{ss:02d}"


# =====================================================
# Timeline model
# =====================================================


@dataclass
class TimelineItem:
    id: str
    enabled: bool
    offset_sec: float
    label: str

    kind: str          # "video", "text", "api", "custom"
    payload: Dict[str, Any]   # handler-specific data

    def to_dict(self):
        return dataclasses.asdict(self)

    @staticmethod
    def from_dict(d):
        return TimelineItem(
            id=_safe_str(d.get("id") or sha1(json.dumps(d, sort_keys=True)), ""),
            enabled=bool(d.get("enabled", True)),
            offset_sec=float(d.get("offset_sec", 0)),
            label=_safe_str(d.get("label","")),
            kind=_safe_str(d.get("kind","video")),
            payload=d.get("payload",{}) if isinstance(d.get("payload"),dict) else {}
        )
def timeline_inject(mem: Dict[str, Any], item: "TimelineItem") -> None:
    items = _items_from_mem(mem)
    items.append(item)
    items.sort(key=lambda x: float(x.offset_sec))
    _save_items_to_mem(mem, items)

TIMELINE_HANDLERS = {}
def register_timeline_handler(kind: str, fn):
    TIMELINE_HANDLERS[kind] = fn

# =====================================================
# Frame sampling via ffmpeg
# =====================================================

def ffmpeg_available() -> bool:
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=2)
        return r.returncode == 0
    except Exception:
        return False

def iter_jpegs_from_ffmpeg(input_path: str, ss: float, dur: float, fps: float, timeout_sec: float = 60.0):
    """
    Yields raw JPEG bytes extracted by ffmpeg (image2pipe/mjpeg).
    """
    fps = max(0.2, float(fps))
    dur = max(0.5, float(dur))
    ss = max(0.0, float(ss))

    # -nostdin: avoid blocking
    # -loglevel error: quiet
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel", "error",
        "-ss", str(ss),
        "-i", input_path,
        "-t", str(dur),
        "-vf", f"fps={fps},scale=480:-1:flags=fast_bilinear",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "pipe:1",
    ]

    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    start = time.time()

    # Parse MJPEG stream by JPEG SOI/EOI markers
    buf = b""
    SOI = b"\xff\xd8"
    EOI = b"\xff\xd9"

    try:
        while True:
            if (time.time() - start) > timeout_sec:
                break

            chunk = p.stdout.read(4096) if p.stdout else b""
            if not chunk:
                break
            buf += chunk

            # Extract as many complete JPEGs as possible
            while True:
                a = buf.find(SOI)
                if a < 0:
                    # drop noise
                    if len(buf) > 1_000_000:
                        buf = buf[-100_000:]
                    break
                b = buf.find(EOI, a + 2)
                if b < 0:
                    # need more data
                    if a > 0:
                        buf = buf[a:]
                    break
                jpg = buf[a:b + 2]
                buf = buf[b + 2:]
                yield jpg

    finally:
        try:
            p.kill()
        except Exception:
            pass


# =====================================================
# Lightweight vision: scene + motion
# =====================================================

def _img_to_gray_small(jpg_bytes: bytes):
    """
    Returns small grayscale list[int] of length w*h.
    Pillow is used if available; otherwise return None.
    """
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return None

    try:
        im = Image.open(io.BytesIO(jpg_bytes))
        im = im.convert("L")
        im = im.resize((64, 36))
        return list(im.getdata())
    except Exception:
        return None

def _mean_abs_diff(a: List[int], b: List[int]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    # Average absolute pixel difference
    s = 0
    for i in range(len(a)):
        s += abs(int(a[i]) - int(b[i]))
    return s / max(len(a), 1)

def detect_events_from_frames(
    frames_jpg: List[bytes],
    scene_threshold: float,
    motion_threshold: float,
    emit_limit: int
) -> List[Dict[str, Any]]:
    """
    Produces a list of event dicts:
      {event_type, score, title, body, meta}
    """
    out: List[Dict[str, Any]] = []
    prev_gray = None
    prev_diff = None

    for idx, jpg in enumerate(frames_jpg):
        if len(out) >= emit_limit:
            break

        g = _img_to_gray_small(jpg)
        if g is None:
            continue

        if prev_gray is None:
            prev_gray = g
            continue

        d = _mean_abs_diff(prev_gray, g)
        prev_gray = g

        # motion spike: diff larger than threshold + relative jump
        if prev_diff is not None:
            if d >= motion_threshold and (d - prev_diff) >= (motion_threshold * 0.25):
                out.append({
                    "event_type": "motion_spike",
                    "score": float(d),
                    "title": "Motion spike detected",
                    "body": f"Frame-to-frame movement jumped (diff={d:.1f}).",
                    "meta": {"diff": round(d, 2), "frame_index": idx}
                })
                if len(out) >= emit_limit:
                    break

        # scene change: diff exceeds higher threshold
        if d >= scene_threshold:
            out.append({
                "event_type": "scene_change",
                "score": float(d),
                "title": "Scene change detected",
                "body": f"Visual scene changed materially (diff={d:.1f}).",
                "meta": {"diff": round(d, 2), "frame_index": idx}
            })

        prev_diff = d

    # Always include a summary if nothing triggered
    if not out:
        out.append({
            "event_type": "summary",
            "score": 0.0,
            "title": "Video check complete",
            "body": "No major scene/motion events detected in this sampling window.",
            "meta": {}
        })

    return out[:emit_limit]


# =====================================================
# Runtime integration shims
# =====================================================

def _get_priority(cfg: Dict[str, Any], event_type: str, fallback: float) -> float:
    p = (cfg.get("priority") or {})
    try:
        return float(p.get(event_type, fallback))
    except Exception:
        return fallback

def _safe_emit_candidate(runtime: Optional[Dict[str, Any]], mem: Dict[str, Any], cand: Dict[str, Any]) -> None:
    """
    Uses runtime['emit_candidate'] if present, else appends into mem['feed_candidates'].
    Does NOT require rewriting other plugins.
    """
    if isinstance(runtime, dict) and callable(runtime.get("emit_candidate")):
        try:
            runtime["emit_candidate"](cand)
            return
        except Exception:
            pass

    # fallback: append into feed_candidates (soft schema)
    cand = dict(cand or {})
    cand.setdefault("source", "video")
    cand.setdefault("event_type", "item")
    cand.setdefault("title", "")
    cand.setdefault("body", "")
    cand.setdefault("comments", [])
    cand.setdefault("heur", 50.0)
    cand.setdefault("ts", now_ts())
    if not cand.get("post_id"):
        base = (cand.get("title", "") + "|" + (cand.get("body", "") or "")[:200]).strip()
        cand["post_id"] = sha1(base)

    mem.setdefault("feed_candidates", [])
    mem["feed_candidates"].append(cand)
    mem["feed_candidates"] = mem["feed_candidates"][-800:]


# =====================================================
# Timeline engine state in mem
# =====================================================

_MEM_KEY_ITEMS = "_video_timeline_items"
_MEM_KEY_STATE = "_video_timeline_state"   # dict {running, started_ts, paused, pause_accum, pause_started_ts}
_MEM_KEY_TAPE  = "_video_timeline_tape"    # list of last events for widget

_LOCK = threading.Lock()


def _default_state() -> Dict[str, Any]:
    return {
        "running": False,
        "paused": False,
        "started_ts": 0,
        "pause_started_ts": 0,
        "pause_accum_sec": 0.0,
        "fired_ids": {},      # item_id -> true
        "active_item": None,  # item_id currently ingesting
        "active_until_ts": 0,
        "last_error": "",
    }

def _get_state(mem: Dict[str, Any]) -> Dict[str, Any]:
    st = mem.get(_MEM_KEY_STATE)
    if not isinstance(st, dict):
        st = _default_state()
        mem[_MEM_KEY_STATE] = st
    # ensure keys exist
    for k, v in _default_state().items():
        st.setdefault(k, v)
    return st

def _timeline_elapsed_sec(mem: Dict[str, Any]) -> float:
    st = _get_state(mem)
    if not st.get("running"):
        return 0.0
    started_ts = float(st.get("started_ts") or 0)
    if started_ts <= 0:
        return 0.0

    paused = bool(st.get("paused", False))
    pause_accum = float(st.get("pause_accum_sec") or 0.0)
    if paused and st.get("pause_started_ts"):
        # elapsed until pause start
        return max(0.0, float(st["pause_started_ts"]) - started_ts - pause_accum)
    return max(0.0, time.time() - started_ts - pause_accum)

def _items_from_mem(mem: Dict[str, Any]) -> List[TimelineItem]:
    raw = mem.get(_MEM_KEY_ITEMS)
    if not isinstance(raw, list):
        return []
    out: List[TimelineItem] = []
    for it in raw:
        if isinstance(it, dict):
            try:
                out.append(TimelineItem.from_dict(it))
            except Exception:
                pass
    return out

def _save_items_to_mem(mem: Dict[str, Any], items: List[TimelineItem]) -> None:
    mem[_MEM_KEY_ITEMS] = [it.to_dict() for it in items]


# =====================================================
# Ingestion worker for a single timeline item
# =====================================================
def resolve_video_source(path: str) -> str:
    """
    If path is a YouTube URL, use yt-dlp to resolve to a direct media stream.
    Otherwise return path as-is.
    """
    p = path.lower()

    if "youtube.com" in p or "youtu.be" in p:
        try:
            # yt-dlp returns a direct playable URL with -g
            real = subprocess.check_output(
                ["yt-dlp", "-f", "best[ext=mp4]/best", "-g", path],
                stderr=subprocess.DEVNULL
            ).decode().strip()

            if real:
                return real
        except Exception as e:
            raise RuntimeError(f"yt-dlp failed to resolve YouTube URL: {e}")

    return path

def _ingest_video_item(
    item: TimelineItem,
    mem: Dict[str, Any],
    cfg: Dict[str, Any],
    runtime: Optional[Dict[str, Any]],
) -> None:
    """
    Video handler for timeline items.
    Expects item.payload:
      {
        "source": "file" | "url",
        "path": str,
        "seek": float,
        "capture_sec": float,
        "fps": float
      }
    """
    runtime = runtime if isinstance(runtime, dict) else {}
    StationEvent = runtime.get("StationEvent")
    event_q = runtime.get("event_q")
    ui_q = runtime.get("ui_q")
    log = runtime.get("log")

    pld = item.payload if isinstance(item.payload, dict) else {}
    raw_path = _safe_str(pld.get("path"), "")

    try:
        path = resolve_video_source(raw_path)
    except Exception as e:
        with _LOCK:
            st = _get_state(mem)
            st["last_error"] = str(e)
    return
    seek = float(pld.get("seek") or 0.0)
    capture_sec = float(pld.get("capture_sec") or cfg.get("default_capture_sec", 15))
    fps = float(pld.get("fps") or cfg.get("default_fps", 1.5))
    source = _safe_str(pld.get("source"), "file")

    # mark active
    with _LOCK:
        st = _get_state(mem)
        st["active_item"] = item.id
        st["active_until_ts"] = now_ts() + int(max(2.0, capture_sec) + 2)

    if not path:
        with _LOCK:
            st = _get_state(mem)
            st["last_error"] = "video item missing payload.path"
        return

    if not ffmpeg_available():
        with _LOCK:
            st = _get_state(mem)
            st["last_error"] = "ffmpeg not found on PATH; cannot ingest video."
        return

    scene_threshold = float(cfg.get("scene_threshold", 18))
    motion_threshold = float(cfg.get("motion_threshold", 10))
    emit_limit = int(cfg.get("emit_limit_per_item", 4))

    frames: List[bytes] = []
    try:
        for jpg in iter_jpegs_from_ffmpeg(
            path,
            ss=seek,
            dur=capture_sec,
            fps=fps,
            timeout_sec=max(15.0, capture_sec * 5.0),
        ):
            frames.append(jpg)
            if len(frames) >= int(max(4, capture_sec * fps * 2)):
                break
    except Exception as e:
        with _LOCK:
            st = _get_state(mem)
            st["last_error"] = f"ffmpeg ingest error: {e}"
        return

    events = detect_events_from_frames(
        frames_jpg=frames,
        scene_threshold=scene_threshold,
        motion_threshold=motion_threshold,
        emit_limit=emit_limit,
    )

    for ev in events:
        et = ev.get("event_type", "summary")
        title = ev.get("title", "Video event")
        body = ev.get("body", "")
        score = float(ev.get("score", 0.0))
        meta = ev.get("meta", {}) if isinstance(ev.get("meta"), dict) else {}

        pri = _get_priority(cfg, et, fallback=82.0)

        payload = {
            "title": title,
            "body": clamp_text(body, 1400),
            "angle": "React to what the video just showed.",
            "why": "Scheduled timeline item fired (video).",
            "key_points": ["timeline", "video", et],
            "host_hint": "Timeline video pulse.",

            "timeline_item_id": item.id,
            "timeline_label": item.label,
            "offset_sec": item.offset_sec,

            "video_source": source,
            "video_path": path,
            "seek": seek,
            "capture_sec": capture_sec,
            "fps": fps,

            "score": score,
            "meta": meta,
            "ts": now_ts(),
        }

        if StationEvent is not None and event_q is not None:
            try:
                evt = StationEvent(
                    source="timeline",
                    type=et,
                    ts=now_ts(),
                    priority=float(pri),
                    payload=payload
                )
                event_q.put(evt)
            except Exception:
                pass

        _safe_emit_candidate(runtime, mem, {
            "source": "timeline",
            "event_type": et,
            "title": f"{item.label or 'Timeline'} • {title}",
            "body": payload["body"],
            "heur": float(pri),
            "ts": now_ts(),
            "timeline_item_id": item.id,
            "kind": item.kind,
            "meta": meta,
            "score": score,
        })

        with _LOCK:
            tape = mem.setdefault(_MEM_KEY_TAPE, [])
            tape.append({
                "ts": now_ts(),
                "item_id": item.id,
                "label": item.label,
                "kind": item.kind,
                "event_type": et,
                "title": title,
                "score": score,
                "path": path,
            })
            mem[_MEM_KEY_TAPE] = tape[-80:]

        if ui_q is not None:
            try:
                ui_q.put((
                    "widget_update",
                    {
                        "widget_key": "video_timeline",
                        "data": {
                            "status": "event",
                            "event": mem.get(_MEM_KEY_TAPE, [])[-1] if mem.get(_MEM_KEY_TAPE) else {},
                            "tape": mem.get(_MEM_KEY_TAPE, []),
                        }
                    }
                ))
            except Exception:
                pass

        if callable(log):
            try:
                log("feed", f"timeline(video) emit {et} item={item.label or item.id} pri={pri} score={score:.1f}")
            except Exception:
                pass

    with _LOCK:
        st = _get_state(mem)
        st["active_item"] = None
        st["active_until_ts"] = 0
register_timeline_handler("video", _ingest_video_item)

# =====================================================
# Feed worker (scheduler)
# =====================================================
def feed_worker(stop_event, mem, cfg, runtime=None):
    """
    General timeline scheduler.

    Fires TimelineItems when:
        elapsed_time >= item.offset_sec

    Dispatches each item to its registered handler by item.kind.

    Timeline state is controlled via:
        mem[_MEM_KEY_STATE]
    """

    poll_sec = float(cfg.get("poll_sec", 0.25))

    # Ensure storage
    mem.setdefault(_MEM_KEY_ITEMS, [])
    mem.setdefault(_MEM_KEY_TAPE, [])
    _get_state(mem)

    runtime = runtime if isinstance(runtime, dict) else {}

    while not stop_event.is_set():
        try:
            # -----------------------------
            # Check timeline state
            # -----------------------------
            with _LOCK:
                st = _get_state(mem)
                running = bool(st.get("running", False))
                paused = bool(st.get("paused", False))

            if not running or paused:
                time.sleep(max(0.15, poll_sec))
                continue

            # -----------------------------
            # Compute elapsed time
            # -----------------------------
            elapsed = _timeline_elapsed_sec(mem)

            # -----------------------------
            # Load items
            # -----------------------------
            items = _items_from_mem(mem)

            due: List[TimelineItem] = []

            # -----------------------------
            # Determine which items fire
            # -----------------------------
            with _LOCK:
                fired = st.get("fired_ids")
                if not isinstance(fired, dict):
                    fired = {}
                    st["fired_ids"] = fired

                for it in items:
                    if not it.enabled:
                        continue

                    if fired.get(it.id):
                        continue

                    if elapsed >= float(it.offset_sec):
                        due.append(it)

                # Mark as fired immediately (prevents double fire)
                for it in due:
                    fired[it.id] = True

            # -----------------------------
            # Dispatch due items
            # -----------------------------
            for it in due:
                handler = TIMELINE_HANDLERS.get(it.kind)

                if not handler:
                    # Unknown type — skip silently
                    continue

                t = threading.Thread(
                    target=handler,
                    args=(it, mem, cfg, runtime),
                    daemon=True
                )
                t.start()

            time.sleep(max(0.15, poll_sec))

        except Exception:
            # Never crash the timeline engine
            time.sleep(max(0.15, poll_sec))


# =====================================================
# Widget: Timeline Editor + Status + Tape
# =====================================================

def register_widgets(registry, runtime):
    tk = runtime["tk"]
    mem = runtime.get("mem", {})


    BG = "#0e0e0e"
    SURFACE = "#121212"
    CARD = "#161616"
    EDGE = "#2a2a2a"

    TXT = "#e8e8e8"
    MUTED = "#9a9a9a"
    ACCENT = "#4cc9f0"
    GOOD = "#2ee59d"
    BAD = "#ff4d6d"
    AMBER = "#ffb703"

    def widget_factory(parent, runtime):
        return VideoTimelineWidget(
            parent, runtime,
            BG=BG, SURFACE=SURFACE, CARD=CARD, EDGE=EDGE,
            TXT=TXT, MUTED=MUTED, ACCENT=ACCENT, GOOD=GOOD, BAD=BAD, AMBER=AMBER
        )

    registry.register(
        "video_timeline",
        widget_factory,
        title="Video • Timeline",
        default_panel="center"
    )


class VideoTimelineWidget:
    def __init__(self, parent, runtime, **C):
        self.tk = runtime["tk"]
        self.runtime = runtime
        self.mem = runtime.get("mem", {})
        self.cfg = (runtime.get("cfg") or runtime.get("manifest") or {})
        self.C = C

        self.root = self.tk.Frame(parent, bg=C["BG"])

        # Ensure storage
        self.mem.setdefault(_MEM_KEY_ITEMS, [])
        self.mem.setdefault(_MEM_KEY_TAPE, [])
        _get_state(self.mem)

        # -------------------------
        # Top controls
        # -------------------------
        top = self.tk.Frame(self.root, bg=C["SURFACE"], highlightbackground=C["EDGE"], highlightthickness=1)
        top.pack(fill="x", padx=10, pady=(10, 8))

        self.status_lbl = self.tk.Label(
            top, text="Timeline idle",
            fg=C["MUTED"], bg=C["SURFACE"],
            font=("Segoe UI", 10, "bold"),
            anchor="w"
        )
        self.status_lbl.pack(side="left", padx=10, pady=10)

        btns = self.tk.Frame(top, bg=C["SURFACE"])
        btns.pack(side="right", padx=10, pady=8)

        self.btn_play = self.tk.Button(btns, text="PLAY", command=self.play, relief="flat", bg=C["CARD"], fg=C["TXT"])
        self.btn_pause = self.tk.Button(btns, text="PAUSE", command=self.pause, relief="flat", bg=C["CARD"], fg=C["TXT"])
        self.btn_stop = self.tk.Button(btns, text="STOP", command=self.stop, relief="flat", bg=C["CARD"], fg=C["TXT"])

        self.btn_play.pack(side="left", padx=4)
        self.btn_pause.pack(side="left", padx=4)
        self.btn_stop.pack(side="left", padx=4)

        # -------------------------
        # Main split
        # -------------------------
        main = self.tk.Frame(self.root, bg=C["BG"])
        main.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        left = self.tk.Frame(main, bg=C["BG"])
        right = self.tk.Frame(main, bg=C["BG"])
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right.pack(side="right", fill="both", expand=True)

        # -------------------------
        # Timeline editor (left)
        # -------------------------
        editor = self.tk.Frame(left, bg=C["CARD"], highlightbackground=C["EDGE"], highlightthickness=1)
        editor.pack(fill="both", expand=True)

        ed_hdr = self.tk.Frame(editor, bg=C["CARD"])
        ed_hdr.pack(fill="x", padx=10, pady=(10, 6))

        self.tk.Label(ed_hdr, text="TIMELINE", fg=C["ACCENT"], bg=C["CARD"], font=("Segoe UI", 10, "bold")).pack(side="left")

        tools = self.tk.Frame(ed_hdr, bg=C["CARD"])
        tools.pack(side="right")

        self.tk.Button(tools, text="Add", command=self.add_item, relief="flat", bg=C["SURFACE"], fg=C["TXT"]).pack(side="left", padx=4)
        self.tk.Button(tools, text="Remove", command=self.remove_selected, relief="flat", bg=C["SURFACE"], fg=C["TXT"]).pack(side="left", padx=4)
        self.tk.Button(tools, text="Up", command=lambda: self.move_selected(-1), relief="flat", bg=C["SURFACE"], fg=C["TXT"]).pack(side="left", padx=4)
        self.tk.Button(tools, text="Down", command=lambda: self.move_selected(1), relief="flat", bg=C["SURFACE"], fg=C["TXT"]).pack(side="left", padx=4)
        self.tk.Button(tools, text="Save JSON", command=self.save_json_dialog, relief="flat", bg=C["SURFACE"], fg=C["TXT"]).pack(side="left", padx=4)
        self.tk.Button(tools, text="Load JSON", command=self.load_json_dialog, relief="flat", bg=C["SURFACE"], fg=C["TXT"]).pack(side="left", padx=4)

        # listbox
        self.listbox = self.tk.Listbox(
            editor,
            bg=C["SURFACE"],
            fg=C["TXT"],
            selectbackground=C["ACCENT"],
            highlightthickness=0,
            relief="flat"
        )
        self.listbox.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(0, 10))

        lb_scroll = self.tk.Scrollbar(editor, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=lb_scroll.set)
        lb_scroll.pack(side="right", fill="y", pady=(0, 10), padx=(0, 10))

        self.listbox.bind("<<ListboxSelect>>", lambda _e: self.load_selected_into_form())

        # form under list (simple inline)
        form = self.tk.Frame(left, bg=C["CARD"], highlightbackground=C["EDGE"], highlightthickness=1)
        form.pack(fill="x", pady=(8, 0))

        self.var_enabled = self.tk.IntVar(value=1)
        self.var_offset = self.tk.StringVar(value="00:00")
        self.var_label = self.tk.StringVar(value="Video")
        self.var_source = self.tk.StringVar(value="file")
        self.var_path = self.tk.StringVar(value="")
        self.var_seek = self.tk.StringVar(value="0")
        self.var_cap = self.tk.StringVar(value=str(self._default_capture_sec()))
        self.var_fps = self.tk.StringVar(value=str(self._default_fps()))

        row1 = self.tk.Frame(form, bg=C["CARD"])
        row1.pack(fill="x", padx=10, pady=(10, 6))
        self.tk.Checkbutton(row1, text="Enabled", variable=self.var_enabled, bg=C["CARD"], fg=C["TXT"], selectcolor=C["SURFACE"]).pack(side="left")
        self.tk.Label(row1, text="Offset", fg=C["MUTED"], bg=C["CARD"]).pack(side="left", padx=(10,4))
        row2 = self.tk.Frame(form, bg=C["CARD"])
        row2.pack(fill="x", padx=10, pady=4)

        self.tk.Label(row2, text="Path", fg=C["MUTED"], bg=C["CARD"]).pack(side="left")
        self.tk.Entry(row2, textvariable=self.var_path, width=50).pack(side="left", padx=6)


        row3 = self.tk.Frame(form, bg=C["CARD"])
        row3.pack(fill="x", padx=10, pady=4)

        self.tk.Label(row3, text="Seek", fg=C["MUTED"], bg=C["CARD"]).pack(side="left")
        self.tk.Entry(row3, textvariable=self.var_seek, width=8).pack(side="left", padx=4)

        self.tk.Label(row3, text="Capture", fg=C["MUTED"], bg=C["CARD"]).pack(side="left", padx=8)
        self.tk.Entry(row3, textvariable=self.var_cap, width=6).pack(side="left")

        self.tk.Label(row3, text="FPS", fg=C["MUTED"], bg=C["CARD"]).pack(side="left", padx=8)
        self.tk.Entry(row3, textvariable=self.var_fps, width=6).pack(side="left")


        row4 = self.tk.Frame(form, bg=C["CARD"])
        row4.pack(fill="x", padx=10, pady=(6,10))

        self.tk.Button(
            row4,
            text="Apply Changes",
            command=self.apply_form,
            bg=C["SURFACE"],
            fg=C["TXT"],
            relief="flat"
        ).pack(side="right")

    def add_item(self):
        it = TimelineItem(
            id=sha1(time.time()),
            enabled=True,
            offset_sec=0.0,
            label="Video",
            kind="video",
            payload={
                "source": "file",
                "path": "",
                "seek": 0.0,
                "capture_sec": float(self._default_capture_sec()),
                "fps": float(self._default_fps()),
            },
        )

        items = _items_from_mem(self.mem)
        items.append(it)
        _save_items_to_mem(self.mem, items)
        self.refresh_list()
    def _default_capture_sec(self) -> float:
        try:
            return float(self.cfg.get("default_capture_sec", 15))
        except Exception:
            return 15.0


    def _default_fps(self) -> float:
        try:
            return float(self.cfg.get("default_fps", 1.5))
        except Exception:
            return 1.5

    def remove_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return

        items = _items_from_mem(self.mem)
        items.pop(sel[0])
        _save_items_to_mem(self.mem, items)
        self.refresh_list()
    def move_selected(self, direction: int):
        sel = self.listbox.curselection()
        if not sel:
            return

        idx = sel[0]
        items = _items_from_mem(self.mem)
        new_idx = idx + direction

        if new_idx < 0 or new_idx >= len(items):
            return

        items[idx], items[new_idx] = items[new_idx], items[idx]
        _save_items_to_mem(self.mem, items)

        self.refresh_list()
        self.listbox.selection_set(new_idx)
    def save_json_dialog(self):
        from tkinter import filedialog

        items = _items_from_mem(self.mem)
        data = [it.to_dict() for it in items]

        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")]
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    def load_json_dialog(self):
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json")]
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return

        items: List[TimelineItem] = []
        for d in raw:
            if isinstance(d, dict):
                try:
                    items.append(TimelineItem.from_dict(d))
                except Exception:
                    pass

        _save_items_to_mem(self.mem, items)
        self.refresh_list()
    def refresh_list(self):
        self.listbox.delete(0, self.tk.END)

        items = _items_from_mem(self.mem)
        for it in items:
            status = "✓" if it.enabled else "✗"
            t = fmt_hhmmss(it.offset_sec)
            label = it.label or it.kind
            self.listbox.insert(self.tk.END, f"{status} {t} — {label}")

    def play(self):
        st = _get_state(self.mem)
        if not st["running"]:
            st["running"] = True
            st["paused"] = False
            st["started_ts"] = time.time()
            st["pause_accum_sec"] = 0.0
            st["fired_ids"] = {}
        elif st["paused"]:
            st["paused"] = False
            if st["pause_started_ts"]:
                st["pause_accum_sec"] += time.time() - st["pause_started_ts"]
                st["pause_started_ts"] = 0

        self.status_lbl.config(text="Timeline running", fg=self.C["GOOD"])


    def pause(self):
        st = _get_state(self.mem)
        if st["running"] and not st["paused"]:
            st["paused"] = True
            st["pause_started_ts"] = time.time()
            self.status_lbl.config(text="Timeline paused", fg=self.C["AMBER"])


    def stop(self):
        st = _get_state(self.mem)
        st.update(_default_state())
        self.status_lbl.config(text="Timeline stopped", fg=self.C["MUTED"])

    def load_selected_into_form(self):
        sel = self.listbox.curselection()
        if not sel:
            return

        it = _items_from_mem(self.mem)[sel[0]]
        pld = it.payload if isinstance(it.payload, dict) else {}

        self.var_enabled.set(1 if it.enabled else 0)
        self.var_offset.set(fmt_hhmmss(it.offset_sec))
        self.var_label.set(it.label)

        self.var_source.set(_safe_str(pld.get("source"), "file"))
        self.var_path.set(_safe_str(pld.get("path"), ""))
        self.var_seek.set(str(pld.get("seek", 0.0)))
        self.var_cap.set(str(pld.get("capture_sec", self._default_capture_sec())))
        self.var_fps.set(str(pld.get("fps", self._default_fps())))
    def apply_form(self):
        sel = self.listbox.curselection()
        if not sel:
            return

        items = _items_from_mem(self.mem)
        it = items[sel[0]]

        off = parse_hhmmss(self.var_offset.get())
        if off is None:
            return

        it.enabled = bool(self.var_enabled.get())
        it.offset_sec = float(off)
        it.label = self.var_label.get().strip()

        it.kind = "video"
        it.payload = {
            "source": self.var_source.get(),
            "path": self.var_path.get(),
            "seek": float(self.var_seek.get() or 0.0),
            "capture_sec": float(self.var_cap.get() or self._default_capture_sec()),
            "fps": float(self.var_fps.get() or self._default_fps()),
        }

        _save_items_to_mem(self.mem, items)
        self.refresh_list()
