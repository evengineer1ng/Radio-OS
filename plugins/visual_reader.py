"""
visual_reader.py — Visual Content Analysis Plugin for RadioOS

Captures screenshots from video/window/screen sources and sends them to a vision LLM
for interpretation. Emits text-only summaries and events (no long-term image storage).

Plugin contract:
  - feed_worker: Main feed loop (runs in thread)
  - register_widgets: UI panel registration
  - PLUGIN_NAME, PLUGIN_DESC: Metadata
  - DEFAULT_CONFIG: Per-station defaults
"""

from __future__ import annotations

import sys
import os
import time
import threading
import json
import io
from typing import Any, Dict, Optional, Tuple, List
from dataclasses import dataclass

PLUGIN_NAME = "visual_reader"
PLUGIN_DESC = "Capture and interpret visual content via vision LLM"
IS_FEED = True

DEFAULT_CONFIG = {
    "enabled": False,
    "source_type": "screen",  # "video_file", "window", "screen"
    "source_path": "",  # For video files: full path
    "source_window": "",  # For window capture: window title
    "capture_interval": 5,  # seconds
    "talk_over_video": False,  # AI speaks while video plays
    "reaction_frequency": 30,  # seconds (if talk_over_video is True)
    "max_interpretation_length": 500,  # chars
    "interpretation_temperature": 0.7,
}

DEFAULT_VISION_PROMPT = (
    "Describe what is happening in this video frame as if you are a commentator watching a live feed. "
    "Focus on the action, the people, and the atmosphere. Do not mention 'the image' or 'the frame'. "
    "Keep it immediate and descriptive."
)

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
except ImportError as e:
    HAS_MSS = False
    # We can't log here easily as runtime isn't imported yet, but we can print to stderr
    print(f"[visual_reader] Warning: 'mss' not found ({e}). Screen capture may be limited.", file=sys.stderr)

try:
    from PIL import Image
    HAS_PIL = True
except ImportError as e:
    HAS_PIL = False
    print(f"[visual_reader] Warning: 'Pillow' (PIL) not found ({e}). Image processing Disabled.", file=sys.stderr)

try:
    import cv2  # type: ignore
    HAS_CV2 = True
except ImportError as e:
    HAS_CV2 = False
    print(f"[visual_reader] Warning: 'opencv-python' (cv2) not found ({e}). Video file capture Disabled.", file=sys.stderr)

# Windows-specific
if IS_WINDOWS:
    try:
        import pyautogui  # type: ignore
        HAS_PYAUTOGUI = True
    except ImportError as e:
        HAS_PYAUTOGUI = False
        print(f"[visual_reader] Warning: 'pyautogui' not found ({e}). Fallback capture Disabled.", file=sys.stderr)
    
    try:
        from win32gui import FindWindow, GetWindowRect  # type: ignore
        HAS_WINDOWS_API = True
    except ImportError:
        HAS_WINDOWS_API = False
    
    try:
        import pygetwindow  # type: ignore
        HAS_PYGETWINDOW = True
    except ImportError:
        HAS_PYGETWINDOW = False

# Mac-specific
if IS_MAC:
    try:
        import Quartz  # type: ignore
        HAS_QUARTZ = True
    except ImportError:
        HAS_QUARTZ = False

# =====================================================
# Vision model client factory
# =====================================================

class VisionClient:
    """Abstract base for vision model clients."""
    def interpret(self, image_bytes: bytes) -> Optional[str]:
        raise NotImplementedError


class OllamaVisionClient(VisionClient):
    """Local Ollama/LLaVA client."""
    def __init__(self, endpoint: str, model: str = "llava:latest"):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
    
    def interpret(self, image_bytes: bytes) -> Optional[str]:
        """Send image to Ollama vision model."""
        try:
            import base64
            import urllib.request
            import urllib.error
            
            b64_image = base64.b64encode(image_bytes).decode("utf-8")
            prompt = DEFAULT_VISION_PROMPT
            
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
            
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                response_text = result.get("response", "").strip()
                if not response_text:
                    import your_runtime as rt
                    rt.log("visual", f"Ollama returned empty response. Raw result keys: {list(result.keys())}")
                return response_text
        except urllib.error.URLError as e:
            import your_runtime as rt
            if hasattr(e, 'reason') and "refused" in str(e.reason):
                 rt.log("visual", f"Ollama connection refused. Is Ollama running? (Error: {e})")
            else:
                 rt.log("visual", f"Ollama URL error: {e}")
            return None
        except Exception as e:
            import your_runtime as rt
            rt.log("visual", f"Ollama error: {e}")
            return None


class APIVisionClient(VisionClient):
    """API-based vision client (OpenAI, Anthropic, etc.)."""
    def __init__(self, provider: str, model: str, api_key: str, endpoint: Optional[str] = None):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.endpoint = endpoint
    
    def interpret(self, image_bytes: bytes) -> Optional[str]:
        """Send image to API vision model."""
        try:
            if self.provider == "openai":
                return self._interpret_openai(image_bytes)
            elif self.provider == "anthropic":
                return self._interpret_anthropic(image_bytes)
            elif self.provider == "google":
                return self._interpret_google(image_bytes)
            else:
                return self._interpret_custom(image_bytes)
        except Exception as e:
            import your_runtime as rt
            rt.log("visual", f"API error ({self.provider}): {e}")
            return None
    
    def _interpret_openai(self, image_bytes: bytes) -> Optional[str]:
        """OpenAI GPT-4-Vision."""
        import base64
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        
        import urllib.request
        import urllib.error
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": DEFAULT_VISION_PROMPT,
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 200,
        }
        
        url = "https://api.openai.com/v1/chat/completions"
        req = urllib.request.Request(
            url,
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
    
    def _interpret_anthropic(self, image_bytes: bytes) -> Optional[str]:
        """Claude/Anthropic."""
        try:
            import anthropic  # type: ignore
            client = anthropic.Anthropic(api_key=self.api_key)
            
            import base64
            b64_image = base64.b64encode(image_bytes).decode("utf-8")
            
            message = client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=[
                    {
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
                            {
                                "type": "text",
                                "text": DEFAULT_VISION_PROMPT,
                            },
                        ],
                    }
                ],
            )
            
            if message.content:
                return message.content[0].text.strip()
        except Exception:
            pass
        return None
    
    def _interpret_google(self, image_bytes: bytes) -> Optional[str]:
        """Google Vision / Gemini."""
        try:
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=self.api_key)
            
            model = genai.GenerativeModel(self.model)
            
            # Convert bytes to PIL Image
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            
            response = model.generate_content(
                [
                    DEFAULT_VISION_PROMPT,
                    img,
                ]
            )
            
            return response.text.strip()
        except Exception:
            pass
        return None
    
    def _interpret_custom(self, image_bytes: bytes) -> Optional[str]:
        """Custom endpoint."""
        import base64
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        
        import urllib.request
        
        payload = {
            "image": b64_image,
            "prompt": DEFAULT_VISION_PROMPT,
        }
        
        url = self.endpoint or "http://localhost:8000/vision"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("interpretation", "").strip()


def create_vision_client(cfg: Dict[str, Any]) -> Optional[VisionClient]:
    """Factory to create appropriate vision client from config."""
    model_type = cfg.get("model_type") or "local"
    
    if model_type == "local":
        local_model = cfg.get("local_model") or "llava:latest"
        endpoint = local_model
        # If it looks like a URL, use as endpoint; else use as model name with default endpoint
        if not local_model.startswith("http"):
            endpoint = "http://localhost:11434"
        return OllamaVisionClient(endpoint, local_model)
    else:
        return APIVisionClient(
            provider=cfg.get("api_provider") or "openai",
            model=cfg.get("api_model") or "gpt-4-vision-preview",
            api_key=cfg.get("api_key") or "",
            endpoint=cfg.get("api_endpoint") or "",
        )


# =====================================================
# Screenshot capture
# =====================================================

class ScreenCapture:
    """Cross-platform screenshot capture."""
    
    @staticmethod
    def capture_screen() -> Optional[bytes]:
        """Capture full screen."""
        if HAS_MSS:
            try:
                with mss.mss() as sct:
                    # Try monitor 1 (primary) first, fall back to 0 (all) or others
                    monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                    screenshot = sct.grab(monitor)
                    if HAS_PIL:
                        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
                        buf = io.BytesIO()
                        img.save(buf, format="JPEG", quality=85)
                        return buf.getvalue()
                    else:
                         import your_runtime as rt
                         rt.log("visual", "MSS capture blocked: PIL not available to process image.")
            except Exception as e:
                import your_runtime as rt
                rt.log("visual", f"MSS capture failed: {e}")
        
        # Fallback: pyautogui
        if HAS_PYAUTOGUI:
            try:
                img = pyautogui.screenshot()
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                return buf.getvalue()
            except Exception as e:
                import your_runtime as rt
                rt.log("visual", f"PyAutoGUI capture failed: {e}")
        else:
             if not HAS_MSS:
                 import your_runtime as rt
                 rt.log("visual", "No screen capture libraries available (missing mss AND pyautogui). Please pip install mss pyautogui pillow.")
        
        return None
    
    @staticmethod
    def capture_window(window_title: str) -> Optional[bytes]:
        """Capture specific window (Windows)."""
        if not IS_WINDOWS or not HAS_WINDOWS_API:
            return None
        
        if not HAS_PYAUTOGUI:
            import your_runtime as rt
            rt.log("visual", "Window capture blocked: PyAutoGUI not installed.")
            return None

        try:
            hwnd = FindWindow(None, window_title)
            if hwnd:
                rect = GetWindowRect(hwnd)
                if rect:
                    x, y, x2, y2 = rect
                    w = x2 - x
                    h = y2 - y
                    if w > 0 and h > 0 and HAS_PIL:
                        img = pyautogui.screenshot(region=(x, y, w, h))
                        buf = io.BytesIO()
                        img.save(buf, format="JPEG", quality=85)
                        return buf.getvalue()
            else:
                 import your_runtime as rt
                 rt.log("visual", f"Window not found: '{window_title}'")
        except Exception as e:
            import your_runtime as rt
            rt.log("visual", f"Window capture failed: {e}")
        
        return None
    
    @staticmethod
    def capture_video_frame(video_path: str, frame_num: int = -1) -> Optional[bytes]:
        """Capture frame from video file."""
        if not HAS_CV2:
            import your_runtime as rt
            rt.log("visual", "OpenCV (cv2) not installed/available for video capture.")
            return None
        
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                import your_runtime as rt
                rt.log("visual", f"Failed to open video file: {video_path}")
                return None
            
            # Read frame (latest if frame_num < 0, else specific frame)
            if frame_num < 0:
                # Get total frames and read last
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total_frames - 1))
            else:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            
            ret, frame = cap.read()
            cap.release()
            
            if ret and frame is not None:
                # Resize if needed
                h, w = frame.shape[:2]
                max_w = 1024
                if w > max_w:
                    scale = max_w / w
                    frame = cv2.resize(frame, (max_w, int(h * scale)))
                
                # Convert BGR to RGB and encode
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                ret, buf = cv2.imencode(".jpg", frame_rgb, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ret:
                    return buf.tobytes()
        except Exception:
            pass
        
        return None


# =====================================================
# Main feed worker
# =====================================================

class VisualReaderState:
    """Shared state for visual reader."""
    def __init__(self):
        self.enabled = False  # Show in UI, allow activation
        self.active = False   # Actually running/capturing
        self.source_type = "screen"
        self.source_path = ""
        self.source_window = ""
        self.capture_interval = 5
        self.talk_over_video = False
        self.reaction_frequency = 30
        self.last_capture_time = 0
        self.last_reaction_time = 0  # For throttling live commentary
        self.vision_client: Optional[VisionClient] = None
        self.stop_requested = False
        self._pending_reactions = []  # For summarization mode
        self._last_reacted_ts = 0
        self._last_capture_fail_log = 0.0
        self.video_frame_index = 0  # Track video playback position


_state = VisualReaderState()


def feed_worker(*args, **kwargs) -> None:
    """
    Main feed worker loop.
    Runs in thread, periodically captures screenshots and sends to vision LLM.
    """
    import your_runtime as rt
    import threading

    # Support both legacy signature:
    #   feed_worker(mem, config, event_fn, log_fn)
    # and new runtime signature:
    #   feed_worker(stop_event, mem, payload, runtime_ctx)
    stop_event = None
    mem: Dict[str, Any] = {}
    config: Dict[str, Any] = {}
    event_fn = None
    log_fn = None

    if len(args) >= 4 and isinstance(args[0], threading.Event):
        stop_event = args[0]
        mem = args[1] if isinstance(args[1], dict) else {}
        config = args[2] if isinstance(args[2], dict) else {}
        runtime_ctx = args[3] if isinstance(args[3], dict) else {}
        event_fn = runtime_ctx.get("emit_event") or runtime_ctx.get("event_q")
        if hasattr(event_fn, "put"):
            event_fn = event_fn.put
        log_fn = runtime_ctx.get("log")
    else:
        mem = args[0] if len(args) > 0 and isinstance(args[0], dict) else {}
        config = args[1] if len(args) > 1 and isinstance(args[1], dict) else {}
        event_fn = args[2] if len(args) > 2 else None
        log_fn = args[3] if len(args) > 3 else None

    if event_fn is None:
        event_fn = getattr(rt, "event_q", None)
        if hasattr(event_fn, "put"):
            event_fn = event_fn.put
    if log_fn is None:
        log_fn = getattr(rt, "log", None)
    
    # Load global visual model config
    global_cfg = rt.get_visual_model_config()
    _state.vision_client = create_vision_client(global_cfg)
    
    if not _state.vision_client:
        rt.log("visual", "No vision model configured; disabling visual_reader")
        return
    
    # Always start the worker. If config has no enabled/active flags,
    # treat it as available but inactive until explicitly activated.
    has_enabled_flag = isinstance(config, dict) and ("enabled" in config)
    has_active_flag = isinstance(config, dict) and ("active" in config)
    default_enabled = True if (not has_enabled_flag and not has_active_flag) else False
    _state.enabled = bool(config.get("enabled", default_enabled))
    _state.active = bool(config.get("active", False))
    # Treat visual_reader as session-gated: never auto-activate on boot.
    if isinstance(config, dict) and config.get("active"):
        config["active"] = False
        _state.active = False
        try:
            rt.log("visual", "visual_reader active reset to False on startup (manual activation required)")
        except Exception:
            pass
    # Log config dict id for debugging live reload
    rt.log("visual", f"[DEBUG] visual_reader config dict id: {id(config)}")
    _state.source_type = config.get("source_type", "screen")
    _state.source_path = config.get("source_path", "")
    _state.source_window = config.get("source_window", "")
    _state.capture_interval = config.get("capture_interval", 5)
    _state.talk_over_video = config.get("talk_over_video", False)
    _state.reaction_frequency = config.get("reaction_frequency", 30)
    rt.log("visual", f"Visual reader feed_worker running (enabled={_state.enabled}, active={_state.active}): source={_state.source_type} interval={_state.capture_interval}s talk_over_video={_state.talk_over_video}")
    
    # Track if we've already made the generic comment
    made_generic_comment = False
    was_active = False
    silent_mode = not _state.talk_over_video
    import threading
    # Use runtime shim for interrupt/queue control. 
    # 'rt' is 'your_runtime' which maps to the actual running runtime module, 
    # ensuring we access the *same* signal objects (SHOW_INTERRUPT) as the host.
    runtime = rt
    import os
    # Determine output file path (station dir)
    station_dir = os.environ.get("STATION_DIR", os.getcwd())
    output_file = os.path.join(station_dir, "visual_reader_output.txt")

    last_enabled = _state.enabled
    last_active = _state.active
    while not _state.stop_requested and (stop_event is None or not stop_event.is_set()):
        # Debug: print config dict id and enabled/active value every loop
        try:
            import your_runtime as rt
            rt.log("visual", f"[DEBUG] visual_reader loop config id: {id(config)} enabled={config.get('enabled')} active={_state.active} contents={config}")
        except Exception:
            pass
        try:
            # Always read enabled live from config dict (for live reload)
            if hasattr(config, 'get'):
                if 'enabled' in config:
                    new_enabled = bool(config.get('enabled', _state.enabled))
                    if new_enabled != _state.enabled:
                        rt.log("visual", f"[DEBUG] visual_reader enabled changed via config: {_state.enabled} -> {new_enabled}")
                    _state.enabled = new_enabled
                if 'active' in config:
                    _state.active = bool(config.get('active', _state.active))
            # Activation/deactivation logic: only run if _state.active is True
            if _state.active:
                if not was_active:
                    rt.log("visual", f"visual_reader ACTIVATED: source={_state.source_type} interval={_state.capture_interval}s talk_over_video={_state.talk_over_video}")
                    try:
                        mem["_visual_reader_active"] = True
                    except Exception:
                        pass
                    # Flush output file on activation
                    try:
                        with open(output_file, "w", encoding="utf-8") as _f:
                            _f.write("")
                        rt.log("visual", f"visual_reader output file flushed/created: {output_file}")
                    except Exception as e:
                        rt.log("visual", f"visual_reader output file flush error: {e}")
                    # Cross-platform: set interrupt flags and flush audio queue
                    if runtime is not None:
                        try:
                            # Set interrupt flags if present
                            if hasattr(runtime, 'SHOW_INTERRUPT'):
                                runtime.SHOW_INTERRUPT.set()
                                rt.log("visual", "SHOW_INTERRUPT set by visual_reader")
                            if hasattr(runtime, 'TTS_INTERRUPT'):
                                runtime.TTS_INTERRUPT.set()
                                rt.log("visual", "TTS_INTERRUPT set by visual_reader")
                            # Aggressively clear audio_queue (if present)
                            if hasattr(runtime, 'audio_queue'):
                                cleared = 0
                                while True:
                                    try:
                                        if runtime.audio_queue.empty():
                                            break
                                        runtime.audio_queue.get_nowait()
                                        cleared += 1
                                    except Exception:
                                        break
                                rt.log("visual", f"audio_queue forcibly cleared by visual_reader (removed {cleared} items)")
                            # Flush DB queue if present
                            if hasattr(runtime, 'db_flush_queue'):
                                runtime.db_flush_queue()
                                rt.log("visual", "db_flush_queue called by visual_reader")
                        except Exception as e:
                            rt.log("visual", f"Interrupt/flush failed: {e}")
                    # Inject a high-priority visual_start event
                    if callable(event_fn):
                        comment = "I'll comment as we go." if _state.talk_over_video else "[The host goes silent to observe.]"
                        evt = rt.StationEvent(
                            source="visual_reader",
                            type="visual_start",
                            ts=rt.now_ts(),
                            priority=100,
                            payload={
                                "text": rt.get_prompt(mem, "visual_throwaway_comment", comment=comment, talk_over_video=_state.talk_over_video),
                                "host_hint": "Generic throwaway comment about watching a video or going to video.",
                                "talk_over_video": _state.talk_over_video,
                            },
                        )
                        event_fn(evt)
                    made_generic_comment = True
                    # Reset pending reactions
                    _state._pending_reactions = []
                    _state._last_reacted_ts = 0
                    _state.video_frame_index = 0  # Reset video position on activation
                was_active = True
            else:
                if was_active:
                    rt.log("visual", "visual_reader DEACTIVATED")
                    try:
                        mem["_visual_reader_active"] = False
                    except Exception:
                        pass
                    # On disable, if summarization mode, react to all new lines in output file since last reaction
                    if not _state.talk_over_video:
                        try:
                            # Read all new lines from output file
                            with open(output_file, "r", encoding="utf-8") as f:
                                for line in f:
                                    if line.strip():
                                        ts_end = line.find("]")
                                        if line.startswith("[") and ts_end > 1:
                                            ts = int(line[1:ts_end])
                                            text = line[ts_end+1:].strip()
                                        else:
                                            ts = int(time.time())
                                            text = line.strip()
                                        if ts > _state._last_reacted_ts:
                                            _state._pending_reactions.append((ts, text))
                            # Summarize all reactions into one host event
                            if _state._pending_reactions:
                                summary = "\n".join([t for _, t in _state._pending_reactions])
                                if callable(event_fn):
                                    evt = rt.StationEvent(
                                        source="visual_reader",
                                        type="visual_react_summary",
                                        ts=rt.now_ts(),
                                        priority=100,
                                        payload={
                                            "text": rt.get_prompt(mem, "visual_summarize_reaction", material=summary),
                                            "host_hint": "React to the video after it ends.",
                                        },
                                    )
                                    event_fn(evt)
                                _state._last_reacted_ts = _state._pending_reactions[-1][0]
                                _state._pending_reactions = []
                        except Exception as e:
                            rt.log("visual", f"Failed to summarize reactions: {e}")
                    # Clear interrupt flags so host resumes
                    if runtime is not None:
                        try:
                            if hasattr(runtime, 'SHOW_INTERRUPT'):
                                runtime.SHOW_INTERRUPT.clear()
                                rt.log("visual", "SHOW_INTERRUPT cleared by visual_reader")
                            if hasattr(runtime, 'TTS_INTERRUPT'):
                                runtime.TTS_INTERRUPT.clear()
                                rt.log("visual", "TTS_INTERRUPT cleared by visual_reader")
                        except Exception as e:
                            rt.log("visual", f"Interrupt clear failed: {e}")
                    # Inject a visual_end event to signal host resume
                    if callable(event_fn):
                        evt = rt.StationEvent(
                            source="visual_reader",
                            type="visual_end",
                            ts=rt.now_ts(),
                            priority=100,
                            payload={
                                "text": "[Visual segment ended. Host resumes.]",
                                "host_hint": "Visual segment ended. Host resumes.",
                            },
                        )
                        event_fn(evt)
                    made_generic_comment = False
                was_active = False
                time.sleep(1)
                continue

            now = time.time()
            if now - _state.last_capture_time < _state.capture_interval:
                time.sleep(0.5)
                continue

            # Capture screenshot
            screenshot = None
            if _state.source_type == "screen":
                screenshot = ScreenCapture.capture_screen()
            elif _state.source_type == "window":
                screenshot = ScreenCapture.capture_window(_state.source_window)
            elif _state.source_type == "video_file":
                # Capture specific frame
                screenshot = ScreenCapture.capture_video_frame(_state.source_path, _state.video_frame_index)
                if screenshot:
                    # Advance frame index (approx 30fps * seconds)
                    _state.video_frame_index += int(_state.capture_interval * 30)
                else:
                    # If capture failed, we might be at end of video. Loop back?
                    if _state.video_frame_index > 0:
                        rt.log("visual", "Video ended or read failed; looping back to start.")
                        _state.video_frame_index = 0
                        screenshot = ScreenCapture.capture_video_frame(_state.source_path, 0)
            
            if not screenshot:
                # Throttle capture-failure logs to avoid spam
                now_fail = time.time()
                if now_fail - _state._last_capture_fail_log > 5:
                    rt.log("visual", f"visual_reader capture failed (source={_state.source_type}, window={_state.source_window or '-'}, path={_state.source_path or '-'})")
                    _state._last_capture_fail_log = now_fail
                time.sleep(1)
                continue

            _state.last_capture_time = now

            # Send to vision model
            rt.log("visual", f"Sending capture ({len(screenshot)} bytes) to vision model...")
            
            start_ts = time.time()
            interpretation = _state.vision_client.interpret(screenshot)
            duration = time.time() - start_ts

            if interpretation:
                rt.log("visual", f"Interpreted ({duration:.2f}s): {interpretation[:80]}...")

                # Write interpretation to dedicated output file (append)
                try:
                    with open(output_file, "a", encoding="utf-8") as f:
                        f.write(f"[{int(now)}] {interpretation}\n")
                except Exception as e:
                    rt.log("visual", f"Failed to write to output file: {e}")

                # Store in memory
                if "visual_interpretations" not in mem:
                    mem["visual_interpretations"] = []

                entry = {
                    "timestamp": int(now),
                    "source": _state.source_type,
                    "text": interpretation,
                }
                mem["visual_interpretations"].append(entry)

                # Keep only last 50
                if len(mem["visual_interpretations"]) > 50:
                    mem["visual_interpretations"] = mem["visual_interpretations"][-50:]

                if _state.talk_over_video and callable(event_fn):
                     if now - _state.last_reaction_time >= _state.reaction_frequency:
                        evt = rt.StationEvent(
                            source="visual_reader",
                            type="visual_live_commentary",
                            ts=rt.now_ts(),
                            payload={
                                "text": rt.get_prompt(mem, "visual_realtime_reaction", material=interpretation),
                                "host_hint": "React in real time to what you see in the video.",
                            },
                        )
                        event_fn(evt)
                        _state.last_reaction_time = now
                     else:
                        remaining = int(_state.reaction_frequency - (now - _state.last_reaction_time))
                        rt.log("visual", f"Reaction throttled (next in {remaining}s)")
            else:
                rt.log("visual", f"Vision model returned no interpretation ({duration:.2f}s). Check model availability/logs.")
                # Throttle no-interpretation logs
                now_no = time.time()
                if now_no - _state._last_capture_fail_log > 5:
                    rt.log("visual", "visual_reader: no interpretation returned by vision model")
                    _state._last_capture_fail_log = now_no

            time.sleep(0.5)

        except Exception as e:
            rt.log("visual", f"Error in feed loop: {e}")
            time.sleep(2)


# =====================================================
# Widget registration
# =====================================================

def register_widgets(registry, runtime_stub) -> None:
    """Register UI widgets for visual_reader config."""
    import tkinter as tk
    from tkinter import ttk, filedialog
    
    try:
        # Attempt import of UI constants
        from shell import UI, FONT_BODY, FONT_SMALL
    except ImportError:
        UI = {
            "bg": "#0e0e0e",
            "panel": "#121212",
            "card": "#181818",
            "text": "#e8e8e8",
            "muted": "#9a9a9a",
            "accent": "#4cc9f0",
        }
        FONT_BODY = ("Segoe UI", 11)
        FONT_SMALL = ("Segoe UI", 10)
    
    def make_widget_frame(parent_frame, config_dict):
        """Build visual_reader config widget."""
        frame = tk.LabelFrame(
            parent_frame,
            text="Visual Reader",
            fg=UI.get("text", "#e8e8e8"),
            bg=UI.get("panel", "#121212"),
            font=FONT_BODY,
            padx=12,
            pady=8,
        )
        
        # Enabled toggle (availability only; does not interrupt audio)
        enabled_var = tk.BooleanVar(value=_state.enabled)
        def _on_enabled_change(*_):
            _state.enabled = bool(enabled_var.get())
            if isinstance(config_dict, dict):
                config_dict["enabled"] = _state.enabled
            if not _state.enabled:
                _state.active = False
            try:
                import your_runtime as rt
                rt.log("visual", f"visual_reader enabled set to {_state.enabled}")
            except Exception:
                pass
        enabled_var.trace_add("write", _on_enabled_change)
        tk.Checkbutton(
            frame,
            text="Enable Visual Reader",
            variable=enabled_var,
            fg=UI.get("text", "#e8e8e8"),
            bg=UI.get("panel", "#121212"),
            selectcolor="#ff9500",  # Orange for visibility
        ).pack(anchor="w", pady=(0, 6))

        # Active toggle (controls interrupt/queue silence)
        active_var = tk.BooleanVar(value=_state.active)
        def _on_active_change(*_):
            _state.active = bool(active_var.get())
            if isinstance(config_dict, dict):
                config_dict["active"] = _state.active
            if _state.active:
                _state.enabled = True
                enabled_var.set(True)
            try:
                import your_runtime as rt
                rt.log("visual", f"visual_reader active set to {_state.active}")
            except Exception:
                pass
        active_var.trace_add("write", _on_active_change)
        tk.Checkbutton(
            frame,
            text="Activate (silence TTS/queue while on)",
            variable=active_var,
            fg=UI.get("text", "#e8e8e8"),
            bg=UI.get("panel", "#121212"),
            selectcolor="#ff9500",  # Orange for visibility
        ).pack(anchor="w", pady=(0, 8))
        
        # Source type
        tk.Label(
            frame,
            text="Source:",
            fg=UI.get("text", "#e8e8e8"),
            bg=UI.get("panel", "#121212"),
            font=FONT_SMALL,
        ).pack(anchor="w")
        
        source_var = tk.StringVar(value=config_dict.get("source_type", "screen"))
        for opt in ["screen", "window", "video_file"]:
            tk.Radiobutton(
                frame,
                text=opt,
                variable=source_var,
                value=opt,
                fg=UI.get("text", "#e8e8e8"),
                bg=UI.get("panel", "#121212"),
                selectcolor="#ff9500",  # Orange for visibility
            ).pack(anchor="w", padx=20)
        
        # Helper: get available windows cross-platform
        def get_available_windows():
            """Return list of available window titles (Windows)."""
            windows = []
            
            if IS_WINDOWS:
                # Strategy 1: Try pygetwindow first (most reliable)
                if HAS_PYGETWINDOW:
                    try:
                        import pygetwindow  # type: ignore
                        all_windows = pygetwindow.getAllWindows()
                        windows = [w.title for w in all_windows if w.title and len(w.title) > 1]
                        if windows:
                            return sorted(list(set(windows)))
                    except Exception:
                        pass
                
                # Strategy 2: GetTopWindow traversal
                if HAS_WINDOWS_API:
                    try:
                        import win32gui  # type: ignore
                        import win32con  # type: ignore
                        
                        hwnd = win32gui.GetTopWindow(0)  # type: ignore
                        while hwnd:
                            try:
                                title = win32gui.GetWindowText(hwnd)  # type: ignore
                                if title and len(title) > 1:
                                    windows.append(title)
                            except Exception:
                                pass
                            hwnd = win32gui.GetNextWindow(hwnd, win32con.GW_HWNDNEXT)  # type: ignore
                        
                        if windows:
                            return sorted(list(set(windows)))
                    except Exception:
                        pass
                
                # Strategy 3: EnumWindows
                if HAS_WINDOWS_API:
                    try:
                        import win32gui  # type: ignore
                        
                        def enum_callback(hwnd, results):
                            try:
                                title = win32gui.GetWindowText(hwnd)  # type: ignore
                                if title and len(title) > 1:
                                    windows.append(title)
                            except Exception:
                                pass
                            return True
                        
                        win32gui.EnumWindows(enum_callback, None)  # type: ignore
                        
                        if windows:
                            return sorted(list(set(windows)))
                    except Exception:
                        pass
            
            elif IS_MAC and HAS_QUARTZ:
                try:
                    import Quartz  # type: ignore
                    window_list = Quartz.CGWindowListCopyWindowInfo(  # type: ignore
                        Quartz.kCGWindowListOptionOnScreenOnly,  # type: ignore
                        Quartz.kCGNullWindowID  # type: ignore
                    )
                    if window_list:
                        for w in window_list:
                            title = w.get("kCGWindowName", "")
                            if title:
                                windows.append(title)
                except Exception as e:
                    import your_runtime as rt
                    if callable(rt.log):
                        rt.log("ui", f"visual_reader: Failed to get Quartz windows: {e}")
            
            # Fallback for Mac: AppleScript
            if not windows and IS_MAC:
                try:
                    import subprocess
                    result = subprocess.run(
                        ["osascript", "-e",
                         "tell application \"System Events\" to get name of every window of every process"],
                        capture_output=True,
                        text=True,
                        timeout=3
                    )
                    if result.stdout:
                        windows = [w.strip() for w in result.stdout.split(',') if w.strip()]
                except Exception as e:
                    import your_runtime as rt
                    if callable(rt.log):
                        rt.log("ui", f"visual_reader: AppleScript window enum failed: {e}")
            
            # Linux: try wmctrl if available
            if not windows and IS_LINUX:
                try:
                    import subprocess
                    result = subprocess.run(
                        ["wmctrl", "-l"],
                        capture_output=True,
                        text=True,
                        timeout=3
                    )
                    if result.stdout:
                        # wmctrl output: workspace ID window_id host title
                        windows = [line.split(None, 3)[-1] for line in result.stdout.split('\n') if line.strip()]
                except Exception as e:
                    import your_runtime as rt
                    if callable(rt.log):
                        rt.log("ui", f"visual_reader: wmctrl window enum failed: {e}")
            
            # If still empty, add a placeholder message
            if not windows:
                windows = ["(No windows found - try refreshing)"]
            
            return sorted(list(set(windows)))  # Deduplicate and sort
        
        # Window/Video path selection frame (hidden by default)
        path_frame = tk.Frame(frame, bg=UI.get("panel", "#121212"))
        
        # Window selection
        window_label = tk.Label(
            path_frame,
            text="Window:",
            fg=UI.get("text", "#e8e8e8"),
            bg=UI.get("panel", "#121212"),
            font=FONT_SMALL,
        )
        
        window_var = tk.StringVar(value=config_dict.get("source_window", ""))
        
        # Use ttk.Combobox for dropdown + text entry (populated on demand)
        window_combo = ttk.Combobox(
            path_frame,
            textvariable=window_var,
            values=["(Click refresh to load windows)"],
            state="normal",  # Allow typing
            width=35,
        )
        window_combo.configure(style="TCombobox")
        
        # Style the combobox to match theme
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            "TCombobox",
            fieldbackground=UI.get("card", "#181818"),
            background=UI.get("card", "#181818"),
            foreground=UI.get("text", "#e8e8e8"),
        )
        window_entry = tk.Entry(
            path_frame,
            textvariable=window_var,
            bg=UI.get("card", "#181818"),
            fg=UI.get("text", "#e8e8e8"),
            width=30,
        )
        
        # Refresh button to reload windows list
        def refresh_windows():
            """Refresh the list of available windows."""
            new_windows = get_available_windows()
            window_combo['values'] = new_windows
        
        refresh_btn = tk.Button(
            path_frame,
            text="↻",
            command=refresh_windows,
            bg=UI.get("card", "#181818"),
            fg=UI.get("text", "#e8e8e8"),
            width=3,
        )
        
        # Video file selection
        video_label = tk.Label(
            path_frame,
            text="Video:",
            fg=UI.get("text", "#e8e8e8"),
            bg=UI.get("panel", "#121212"),
            font=FONT_SMALL,
        )
        
        path_var = tk.StringVar(value=config_dict.get("source_path", ""))
        path_entry = tk.Entry(
            path_frame,
            textvariable=path_var,
            bg=UI.get("card", "#181818"),
            fg=UI.get("text", "#e8e8e8"),
            width=35,
        )
        
        def browse_video():
            """Open file dialog for video selection."""
            filename = filedialog.askopenfilename(
                title="Select Video File",
                filetypes=[("Video files", "*.mp4 *.avi *.mkv *.mov *.flv"), ("All files", "*.*")]
            )
            if filename:
                path_var.set(filename)
        
        browse_button = tk.Button(
            path_frame,
            text="Browse",
            command=browse_video,
            bg=UI.get("card", "#181818"),
            fg=UI.get("text", "#e8e8e8"),
            width=8,
        )
        
        def update_path_visibility(*args):
            """Show/hide window or video path based on source type."""
            current_source = source_var.get()
            
            # Clear all widgets in path_frame
            for w in path_frame.winfo_children():
                w.pack_forget()
            
            if current_source == "window":
                window_label.pack(anchor="w", pady=(4, 0))
                win_input_frame = tk.Frame(path_frame, bg=UI.get("panel", "#121212"))
                win_input_frame.pack(anchor="w", fill="x", padx=4, pady=4)
                window_combo.pack(side="left", fill="x", expand=True, padx=(0, 4))
                refresh_btn.pack(side="left", padx=(0, 4))
            elif current_source == "video_file":
                video_label.pack(anchor="w", pady=(4, 0))
                vid_input_frame = tk.Frame(path_frame, bg=UI.get("panel", "#121212"))
                vid_input_frame.pack(anchor="w", fill="x", padx=4, pady=4)
                path_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
                browse_button.pack(side="left")
        
        source_var.trace("w", update_path_visibility)
        path_frame.pack(anchor="w", fill="x", pady=4)
        
        # Initial visibility update
        update_path_visibility()
        
        # Capture interval
        tk.Label(
            frame,
            text="Capture Interval (seconds):",
            fg=UI.get("text", "#e8e8e8"),
            bg=UI.get("panel", "#121212"),
            font=FONT_SMALL,
        ).pack(anchor="w", pady=(8, 0))
        
        interval_var = tk.DoubleVar(value=config_dict.get("capture_interval", 5))
        tk.Scale(
            frame,
            from_=1,
            to=60,
            variable=interval_var,
            orient="horizontal",
            bg=UI.get("card", "#181818"),
            fg=UI.get("text", "#e8e8e8"),
            troughcolor=UI.get("panel", "#121212"),
        ).pack(fill="x", padx=4)
        
        # Talk over video toggle
        talk_var = tk.BooleanVar(value=config_dict.get("talk_over_video", False))
        def _on_talk_change(*_):
            _state.talk_over_video = bool(talk_var.get())
            if isinstance(config_dict, dict):
                config_dict["talk_over_video"] = _state.talk_over_video
        talk_var.trace_add("write", _on_talk_change)

        tk.Checkbutton(
            frame,
            text="Talk Over Video (AI speaks while playing)",
            variable=talk_var,
            fg=UI.get("text", "#e8e8e8"),
            bg=UI.get("panel", "#121212"),
            selectcolor="#ff9500",  # Orange for visibility
        ).pack(anchor="w", pady=8)

        # Reaction frequency slider (only relevant if talk_over_video is on)
        tk.Label(
            frame,
            text="Reaction Frequency (seconds):",
            fg=UI.get("text", "#e8e8e8"),
            bg=UI.get("panel", "#121212"),
            font=FONT_SMALL,
        ).pack(anchor="w")
        
        freq_var = tk.DoubleVar(value=config_dict.get("reaction_frequency", 30))
        def _on_freq_change(*_):
            _state.reaction_frequency = float(freq_var.get())
            if isinstance(config_dict, dict):
                config_dict["reaction_frequency"] = _state.reaction_frequency
        freq_var.trace_add("write", _on_freq_change)

        tk.Scale(
            frame,
            from_=5,
            to=120,
            variable=freq_var,
            orient="horizontal",
            bg=UI.get("card", "#181818"),
            fg=UI.get("text", "#e8e8e8"),
            troughcolor=UI.get("panel", "#121212"),
        ).pack(fill="x", padx=4, pady=(0, 8))
        
        return frame
    
    # Register with the registry (WidgetRegistry instance)
    registry.register(
        "visual_reader",
        make_widget_frame,
        title="Visual Reader",
        default_panel="right"
    )


# =====================================================
# State management
# =====================================================

def update_config(new_config: Dict[str, Any]) -> None:
    """Update runtime config (called by editor)."""
    prev_enabled = getattr(_state, "enabled", False)
    _state.enabled = new_config.get("enabled", False)
    _state.source_type = new_config.get("source_type", "screen")
    _state.source_path = new_config.get("source_path", "")
    _state.source_window = new_config.get("source_window", "")
    _state.capture_interval = new_config.get("capture_interval", 5)
    _state.talk_over_video = new_config.get("talk_over_video", False)
    try:
        import your_runtime as rt
        if _state.enabled and not prev_enabled:
            rt.log("visual", f"visual_reader ENABLED: source={_state.source_type} interval={_state.capture_interval}s talk_over_video={_state.talk_over_video}")
        elif not _state.enabled and prev_enabled:
            rt.log("visual", "visual_reader DISABLED")
    except Exception:
        pass


def stop() -> None:
    """Stop the feed worker."""
    _state.stop_requested = True
