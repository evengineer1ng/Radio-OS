#!/usr/bin/env python3
# plugins/futuresight.py
#
# RadioOS plugin: "futuresight"
# - Timeline scheduler: at T+offset (relative to PLAY), ingest a video frame and interpret it via Vision LLM.
# - Replaces "video_timeline" logic with "visual_reader" interpretation logic.
#
# Config inputs (manifest):
# feeds:
#   futuresight:
#     enabled: true
#     poll_sec: 0.25
#     vision_provider: "ollama"  # or "openai", "anthropic"
#     vision_model: "llava:latest"
#     vision_endpoint: "http://localhost:11434"
#     vision_api_key: "..."
#

import base64
import dataclasses
import hashlib
import io
import json
import sys
import os
import re
import subprocess
import threading
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

PLUGIN_NAME = "futuresight"
PLUGIN_DESC = "FutureSight — Visual Interpretation Timeline"
IS_FEED = True

DEFAULT_CONFIG = {
    "enabled": False,
    "poll_sec": 0.25,
    "vision_provider": "ollama",
    "vision_model": "llava:latest",
    "vision_endpoint": "http://localhost:11434",
    "vision_api_key": "",
    "vision_prompt": (
        "Describe what is happening in this video frame as if you are a commentator watching a live feed. "
        "Focus on the action, the people, and the atmosphere. Keep it immediate and descriptive."
    ),
}

# =====================================================
# Platform detection
# =====================================================
IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

# =====================================================
# Imports: Cross-platform capture libraries
# =====================================================
try:
    import mss  # type: ignore
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    from PIL import Image  # type: ignore
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import cv2  # type: ignore
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

if IS_WINDOWS:
    try:
        import pyautogui  # type: ignore
        HAS_PYAUTOGUI = True
    except ImportError:
        HAS_PYAUTOGUI = False
    
    try:
        from win32gui import FindWindow, GetWindowRect  # type: ignore
        HAS_WINDOWS_API = True
    except ImportError:
        HAS_WINDOWS_API = False
else:
    HAS_PYAUTOGUI = False
    HAS_WINDOWS_API = False

# =====================================================
# Capture Helpers
# =====================================================

def capture_screen() -> Optional[bytes]:
    """Capture full screen."""
    if HAS_MSS:
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                screenshot = sct.grab(monitor)
                if HAS_PIL:
                    img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=85)
                    return buf.getvalue()
        except Exception:
            pass
    if HAS_PYAUTOGUI:
        try:
            img = pyautogui.screenshot()
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return buf.getvalue()
        except Exception:
            pass
    return None

def capture_window(window_title: str) -> Optional[bytes]:
    """Capture specific window (Windows)."""
    if not IS_WINDOWS or not HAS_WINDOWS_API or not HAS_PYAUTOGUI:
        return None
    try:
        hwnd = FindWindow(None, window_title)
        if hwnd:
            rect = GetWindowRect(hwnd)
            if rect:
                x, y, x2, y2 = rect
                w = x2 - x
                h = y2 - y
                if w > 0 and h > 0:
                    img = pyautogui.screenshot(region=(x, y, w, h))
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=85)
                    return buf.getvalue()
    except Exception:
        pass
    return None

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

def parse_hhmmss(s: str) -> Optional[float]:
    if s is None:
        return None
    s = str(s).strip().lower()
    if not s:
        return None
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
    if ":" in s:
        parts = s.split(":")
        try:
            parts = [float(p) for p in parts]
        except Exception:
            return None
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        return None
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
# Vision Logic (Adapted from visual_reader.py)
# =====================================================

class VisionClient:
    """Abstract base for vision model clients."""
    def interpret(self, image_bytes: bytes, prompt: str) -> Optional[str]:
        raise NotImplementedError

class OllamaVisionClient(VisionClient):
    def __init__(self, endpoint: str, model: str):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
    
    def interpret(self, image_bytes: bytes, prompt: str) -> Optional[str]:
        try:
            b64_image = base64.b64encode(image_bytes).decode("utf-8")
            payload = {
                "model": self.model,
                "prompt": prompt,
                "images": [b64_image],
                "stream": False,
            }
            url = f"{self.endpoint}/api/generate"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("response", "").strip()
        except Exception as e:
            print(f"[futuresight] Ollama error: {e}")
            return None

class APIVisionClient(VisionClient):
    def __init__(self, provider: str, model: str, api_key: str):
        self.provider = provider
        self.model = model
        self.api_key = api_key
    
    def interpret(self, image_bytes: bytes, prompt: str) -> Optional[str]:
        try:
            if self.provider == "openai":
                return self._interpret_openai(image_bytes, prompt)
            elif self.provider == "anthropic":
                return self._interpret_anthropic(image_bytes, prompt)
            elif self.provider == "google":
                return self._interpret_google(image_bytes, prompt)
            return None
        except Exception as e:
            print(f"[futuresight] API error: {e}")
            return None
    
    def _interpret_openai(self, image_bytes: bytes, prompt: str) -> Optional[str]:
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url", 
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}
                        },
                    ],
                }
            ],
            "max_tokens": 300,
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("choices"):
                return result["choices"][0]["message"]["content"].strip()
        return None

    def _interpret_anthropic(self, image_bytes: bytes, prompt: str) -> Optional[str]:
        # Minimal implementation without external SDK dependency if possible, 
        # but for robustness we mimic the visual_reader pattern which uses import.
        # If 'anthropic' is not installed, this will fail.
        try:
            import anthropic  # type: ignore
            client = anthropic.Anthropic(api_key=self.api_key)
            b64_image = base64.b64encode(image_bytes).decode("utf-8")
            message = client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64_image,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            if message.content:
                return message.content[0].text.strip()
        except ImportError:
            print("[futuresight] Anthropic SDK not installed.")
        except Exception as e:
            print(f"[futuresight] Anthropic error: {e}")
        return None

    def _interpret_google(self, image_bytes: bytes, prompt: str) -> Optional[str]:
        try:
            import google.generativeai as genai  # type: ignore
            from PIL import Image  # type: ignore
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model)
            img = Image.open(io.BytesIO(image_bytes))
            response = model.generate_content([prompt, img])
            return response.text.strip()
        except ImportError:
            print("[futuresight] google-generativeai SDK not installed.")
        except Exception as e:
            print(f"[futuresight] Google error: {e}")
        return None

def get_vision_client(cfg: Dict[str, Any]) -> VisionClient:
    provider = cfg.get("vision_provider", "ollama")
    model = cfg.get("vision_model", "llava:latest")
    
    if provider == "ollama":
        endpoint = cfg.get("vision_endpoint", "http://localhost:11434")
        return OllamaVisionClient(endpoint, model)
    else:
        api_key = cfg.get("vision_api_key", "")
        return APIVisionClient(provider, model, api_key)

# =====================================================
# Timeline Model & State
# =====================================================

@dataclass
class TimelineItem:
    id: str
    enabled: bool
    offset_sec: float
    label: str
    kind: str          # "video" (mapped to visual ingest), "text", "api"
    payload: Dict[str, Any]

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

_MEM_KEY_ITEMS = "_futuresight_items"
_MEM_KEY_STATE = "_futuresight_state"
_MEM_KEY_TAPE  = "_futuresight_tape"
_LOCK = threading.Lock()

def _default_state() -> Dict[str, Any]:
    return {
        "running": False,
        "paused": False,
        "started_ts": 0,
        "pause_started_ts": 0,
        "pause_accum_sec": 0.0,
        "fired_ids": {},
        "last_error": "",
    }

def _get_state(mem: Dict[str, Any]) -> Dict[str, Any]:
    st = mem.get(_MEM_KEY_STATE)
    if not isinstance(st, dict):
        st = _default_state()
        mem[_MEM_KEY_STATE] = st
    for k, v in _default_state().items():
        st.setdefault(k, v)
    return st

def _timeline_elapsed_sec(mem: Dict[str, Any]) -> float:
    st = _get_state(mem)
    if not st.get("running"):
        return 0.0
    started_ts = float(st.get("started_ts") or 0)
    if started_ts <= 0: return 0.0
    
    paused = bool(st.get("paused", False))
    pause_accum = float(st.get("pause_accum_sec") or 0.0)
    if paused and st.get("pause_started_ts"):
        return max(0.0, float(st["pause_started_ts"]) - started_ts - pause_accum)
    return max(0.0, time.time() - started_ts - pause_accum)

def _items_from_mem(mem: Dict[str, Any]) -> List[TimelineItem]:
    raw = mem.get(_MEM_KEY_ITEMS)
    if not isinstance(raw, list): return []
    out = []
    for it in raw:
        if isinstance(it, dict):
            try:
                out.append(TimelineItem.from_dict(it))
            except Exception: pass
    return out

def _save_items_to_mem(mem: Dict[str, Any], items: List[TimelineItem]) -> None:
    mem[_MEM_KEY_ITEMS] = [it.to_dict() for it in items]

TIMELINE_HANDLERS = {}
def register_timeline_handler(kind: str, fn):
    TIMELINE_HANDLERS[kind] = fn

# =====================================================
# Ingest Logic
# =====================================================

def ffmpeg_available() -> bool:
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=2)
        return r.returncode == 0
    except Exception:
        return False

def resolve_video_source(path: str) -> str:
    p = path.lower()
    if "youtube.com" in p or "youtu.be" in p:
        try:
            real = subprocess.check_output(
                ["yt-dlp", "-f", "best[ext=mp4]/best", "-g", path],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            if real: return real
        except Exception: pass
    return path

def extract_single_frame(input_path: str, ss: float) -> Optional[bytes]:
    """Capture a single frame at timestamp ss."""
    ss = max(0.0, float(ss))
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-ss", str(ss),
        "-i", input_path,
        "-vframes", "1",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "pipe:1",
    ]
    try:
        out = subprocess.check_output(cmd, timeout=10)
        return out if out else None
    except Exception:
        return None

def _ingest_visual_item(item: TimelineItem, mem: Dict[str, Any], cfg: Dict[str, Any], runtime: Optional[Dict[str, Any]]) -> None:
    runtime = runtime or {}
    StationEvent = runtime.get("StationEvent")
    event_q = runtime.get("event_q")
    ui_q = runtime.get("ui_q")
    log = runtime.get("log")

    pld = item.payload
    raw_source = _safe_str(pld.get("source"), "file") # file, url, screen, window
    raw_path = _safe_str(pld.get("path"), "")
    seek = float(pld.get("seek") or 0.0)

    jpg_bytes = None
    path_info = ""

    # 1. Screen Capture
    if raw_source == "screen":
        jpg_bytes = capture_screen()
        path_info = "Screen Capture"
    
    # 2. Window Capture
    elif raw_source == "window":
        jpg_bytes = capture_window(raw_path) # path is window title
        path_info = f"Window: {raw_path}"

    # 3. Video File / URL
    else:
        try:
            path = resolve_video_source(raw_path)
            if path and ffmpeg_available():
                jpg_bytes = extract_single_frame(path, seek)
                path_info = path
        except Exception as e:
            with _LOCK: _get_state(mem)["last_error"] = str(e)
            return

    if not jpg_bytes:
        if callable(log): log("futuresight", f"Failed to capture visual from {raw_source} ({path_info})")
        return

    # Interpret
    client = get_vision_client(cfg)
    prompt = cfg.get("vision_prompt") or DEFAULT_CONFIG["vision_prompt"]
    description = client.interpret(jpg_bytes, prompt)

    if not description:
        if callable(log): log("futuresight", "Vision client returned no description.")
        return

    # Emit Event
    title = pld.get("label") or "Visual Interpretation"
    body = description
    
    # Send to runtime
    if StationEvent and event_q:
        try:
            evt = StationEvent(
                source="futuresight",
                type="visual_interpretation",
                ts=now_ts(),
                priority=90,  # High priority info
                payload={
                    "title": title,
                    "body": body,
                    "timeline_item": item.label,
                    "offset_sec": item.offset_sec,
                    "source": raw_source,
                    "info": path_info,
                    "seek": seek,
                }
            )
            event_q.put(evt)
        except Exception: pass

    # Feed candidate
    if runtime.get("emit_candidate"):
        runtime["emit_candidate"]({
            "source": "futuresight",
            "event_type": "visual_interpretation",
            "title": f"FutureSight: {item.label}",
            "body": body,
            "heur": 85.0,
            "ts": now_ts(),
        })

    # Tape / Log
    with _LOCK:
        tape = mem.setdefault(_MEM_KEY_TAPE, [])
        tape.append({
            "ts": now_ts(),
            "item_id": item.id,
            "label": item.label,
            "title": title,
            "body": body[:100] + "..."
        })
        mem[_MEM_KEY_TAPE] = tape[-50:]

    if ui_q:
        ui_q.put(("widget_update", {
            "widget_key": "futuresight",
            "data": {
                "status": "event",
                "tape": mem.get(_MEM_KEY_TAPE, [])
            }
        }))

# Register the "video" kind to use our visual ingest
register_timeline_handler("video", _ingest_visual_item)


# =====================================================
# Main Feed Worker
# =====================================================

def feed_worker(stop_event, mem, cfg, runtime=None):
    poll_sec = float(cfg.get("poll_sec", 0.25))
    mem.setdefault(_MEM_KEY_ITEMS, [])
    mem.setdefault(_MEM_KEY_TAPE, [])
    
    while not stop_event.is_set():
        try:
            with _LOCK:
                st = _get_state(mem)
                running = bool(st.get("running"))
                paused = bool(st.get("paused"))
            
            if not running or paused:
                time.sleep(poll_sec)
                continue
                
            elapsed = _timeline_elapsed_sec(mem)
            items = _items_from_mem(mem)
            due = []
            
            with _LOCK:
                fired = st.setdefault("fired_ids", {})
                for it in items:
                    if not it.enabled: continue
                    if fired.get(it.id): continue
                    if elapsed >= float(it.offset_sec):
                        due.append(it)
                for it in due:
                    fired[it.id] = True
            
            for it in due:
                handler = TIMELINE_HANDLERS.get(it.kind)
                if handler:
                    try:
                        t = threading.Thread(target=handler, args=(it, mem, cfg, runtime), daemon=True)
                        t.start()
                    except Exception as e:
                        if runtime and getattr(runtime, 'log', None):
                            runtime['log']("futuresight", f"Handler dispatch error: {e}")

            time.sleep(poll_sec)
        except Exception:
            time.sleep(poll_sec)

# =====================================================
# Widget
# =====================================================

def register_widgets(registry, runtime):
    tk = runtime["tk"]
    
    # Colors
    C = {
        "BG": "#0e0e0e", "SURFACE": "#121212", "CARD": "#161616", "EDGE": "#2a2a2a",
        "TXT": "#e8e8e8", "MUTED": "#9a9a9a", "ACCENT": "#00b4d8", # FutureSight Blue
        "GOOD": "#2ee59d", "BAD": "#ff4d6d", "AMBER": "#ffb703"
    }

    def widget_factory(parent, runtime):
        return FutureSightWidget(parent, runtime, **C)

    registry.register(
        "futuresight",
        widget_factory,
        title="FutureSight • Visual Logic",
        default_panel="center"
    )

class FutureSightWidget:
    def __init__(self, parent, runtime, **C):
        self.tk = runtime["tk"]
        self.runtime = runtime
        self.mem = runtime.get("mem", {})
        self.cfg = runtime.get("cfg") or {}
        self.C = C
        self.root = self.tk.Frame(parent, bg=C["BG"])
        
        # Header Controls
        top = self.tk.Frame(self.root, bg=C["SURFACE"])
        top.pack(fill="x", padx=10, pady=10)
        
        self.status_lbl = self.tk.Label(top, text="FutureSight Idle", fg=C["MUTED"], bg=C["SURFACE"], font=("Segoe UI", 10, "bold"))
        self.status_lbl.pack(side="left", padx=10)
        
        btns = self.tk.Frame(top, bg=C["SURFACE"])
        btns.pack(side="right")
        self.tk.Button(btns, text="PLAY", command=self.play, bg=C["CARD"], fg=C["TXT"]).pack(side="left", padx=2)
        self.tk.Button(btns, text="PAUSE", command=self.pause, bg=C["CARD"], fg=C["TXT"]).pack(side="left", padx=2)
        self.tk.Button(btns, text="STOP", command=self.stop, bg=C["CARD"], fg=C["TXT"]).pack(side="left", padx=2)
        
        # Main Split
        main = self.tk.Frame(self.root, bg=C["BG"])
        main.pack(fill="both", expand=True, padx=10, pady=(0,10))
        
        left = self.tk.Frame(main, bg=C["BG"])  # Editor
        left.pack(side="left", fill="both", expand=True, padx=(0,5))
        
        # Editor Header
        ed_tools = self.tk.Frame(left, bg=C["CARD"])
        ed_tools.pack(fill="x")
        self.tk.Button(ed_tools, text="Add Item", command=self.add_item, bg=C["SURFACE"], fg=C["TXT"]).pack(side="left")
        self.tk.Button(ed_tools, text="Remove", command=self.remove_selected, bg=C["SURFACE"], fg=C["TXT"]).pack(side="left", padx=5)
        self.tk.Button(ed_tools, text="Save", command=self.save_json, bg=C["SURFACE"], fg=C["TXT"]).pack(side="left", padx=5)
        self.tk.Button(ed_tools, text="Load", command=self.load_json, bg=C["SURFACE"], fg=C["TXT"]).pack(side="left", padx=5)

        # Listbox
        self.listbox = self.tk.Listbox(left, bg=C["SURFACE"], fg=C["TXT"], relief="flat")
        self.listbox.pack(fill="both", expand=True, pady=5)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        
        # Form
        form = self.tk.Frame(left, bg=C["CARD"])
        form.pack(fill="x")
        
        self.var_off = self.tk.StringVar()
        self.var_lbl = self.tk.StringVar()
        self.var_source = self.tk.StringVar(value="file")
        self.var_path = self.tk.StringVar()
        self.var_seek = self.tk.StringVar()
        
        f1 = self.tk.Frame(form, bg=C["CARD"])
        f1.pack(fill="x", pady=2)
        self.tk.Label(f1, text="Offset:", fg=C["MUTED"], bg=C["CARD"]).pack(side="left")
        self.tk.Entry(f1, textvariable=self.var_off, width=10).pack(side="left", padx=5)
        self.tk.Label(f1, text="Label:", fg=C["MUTED"], bg=C["CARD"]).pack(side="left")
        self.tk.Entry(f1, textvariable=self.var_lbl).pack(side="left", fill="x", expand=True, padx=5)
        
        f2 = self.tk.Frame(form, bg=C["CARD"])
        f2.pack(fill="x", pady=2)
        
        self.tk.Label(f2, text="Source:", fg=C["MUTED"], bg=C["CARD"]).pack(side="left")
        
        # Source Dropdown
        opt = self.tk.OptionMenu(f2, self.var_source, "file", "url", "screen", "window")
        opt.config(bg=C["SURFACE"], fg=C["TXT"], highlightthickness=0, borderwidth=1)
        # Fix for OptionMenu colors on Windows sometimes being stubborn
        opt["menu"].config(bg=C["SURFACE"], fg=C["TXT"])
        opt.pack(side="left", padx=5)

        self.tk.Label(f2, text="Path/Title:", fg=C["MUTED"], bg=C["CARD"]).pack(side="left")
        self.tk.Entry(f2, textvariable=self.var_path).pack(side="left", fill="x", expand=True, padx=5)
        
        f3 = self.tk.Frame(form, bg=C["CARD"])
        f3.pack(fill="x", pady=2)
        self.tk.Label(f3, text="Seek (s):", fg=C["MUTED"], bg=C["CARD"]).pack(side="left")
        self.tk.Entry(f3, textvariable=self.var_seek, width=8).pack(side="left", padx=5)
        self.tk.Button(f3, text="Apply", command=self.apply, bg=C["ACCENT"], fg="#000").pack(side="right")
        
        self.refresh_list()

    def play(self):
        with _LOCK:
            st = _get_state(self.mem)
            if not st["running"]:
                st["running"] = True
                st["paused"] = False
                st["started_ts"] = time.time()
                st["fired_ids"] = {}
                st["pause_accum_sec"] = 0.0
        self.status_lbl.config(text="Running", fg=self.C["GOOD"])
        
    def pause(self):
        with _LOCK:
            st = _get_state(self.mem)
            if st["running"] and not st["paused"]:
                st["paused"] = True
                st["pause_started_ts"] = time.time()
        self.status_lbl.config(text="Paused", fg=self.C["AMBER"])
        
    def stop(self):
        with _LOCK:
            st = _get_state(self.mem)
            st.update(_default_state())
        self.status_lbl.config(text="Stopped", fg=self.C["MUTED"])
    
    def add_item(self):
        items = _items_from_mem(self.mem)
        items.append(TimelineItem(
            id=sha1(time.time()), enabled=True, offset_sec=0.0, label="New Vision Event",
            kind="video", payload={"source": "file", "path": "https://...", "seek": 0}
        ))
        _save_items_to_mem(self.mem, items)
        self.refresh_list()
        
    def remove_selected(self):
        sel = self.listbox.curselection()
        if not sel: return
        items = _items_from_mem(self.mem)
        if 0 <= sel[0] < len(items):
            items.pop(sel[0])
            _save_items_to_mem(self.mem, items)
            self.refresh_list()
            
    def save_json(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(filetypes=[("JSON", "*.json")], defaultextension=".json")
        if path:
            items = _items_from_mem(self.mem)
            with open(path, "w") as f: json.dump([it.to_dict() for it in items], f, indent=2)
            
    def load_json(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            try:
                with open(path) as f:
                     raw = json.load(f)
                items = [TimelineItem.from_dict(x) for x in raw]
                _save_items_to_mem(self.mem, items)
                self.refresh_list()
            except Exception: pass
            
    def refresh_list(self):
        self.listbox.delete(0, self.tk.END)
        items = _items_from_mem(self.mem)
        for it in items:
            t = fmt_hhmmss(it.offset_sec)
            self.listbox.insert(self.tk.END, f"[{t}] {it.label}")
            
    def on_select(self, _e):
        sel = self.listbox.curselection()
        if not sel: return
        it = _items_from_mem(self.mem)[sel[0]]
        self.var_off.set(fmt_hhmmss(it.offset_sec))
        self.var_lbl.set(it.label)
        self.var_source.set(it.payload.get("source", "file"))
        self.var_path.set(it.payload.get("path",""))
        self.var_seek.set(str(it.payload.get("seek", 0)))
        
    def apply(self):
        sel = self.listbox.curselection()
        if not sel: return
        idx = sel[0]
        items = _items_from_mem(self.mem)
        it = items[idx]
        
        off = parse_hhmmss(self.var_off.get())
        if off is not None: it.offset_sec = off
        it.label = self.var_lbl.get()
        it.payload["source"] = self.var_source.get()
        it.payload["path"] = self.var_path.get()
        try: it.payload["seek"] = float(self.var_seek.get())
        except: pass
        
        _save_items_to_mem(self.mem, items)
        self.refresh_list()

