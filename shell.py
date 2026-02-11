#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import os
import json
import time
import yaml
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
try:
    from PIL import Image, ImageTk, ImageOps, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

BASE = os.path.dirname(__file__)
STATIONS_DIR = os.path.join(BASE, "stations")
RUNTIME_PATH = os.path.join(BASE, "runtime.py")
PLUGINS_DIR = os.path.join(BASE, "plugins")

# -----------------------------
# Config Helpers (Moved Up)
# -----------------------------
def get_global_config_path() -> str:
    """Return path to global RadioOS settings file."""
    if os.name == "nt":
        # Windows: %APPDATA%\RadioOS\config.json
        appdata = os.getenv("APPDATA", os.path.expanduser("~"))
        cfg_dir = os.path.join(appdata, "RadioOS")
    else:
        # Mac/Linux: ~/.radioOS/config.json
        cfg_dir = os.path.expanduser("~/.radioOS")
    
    os.makedirs(cfg_dir, exist_ok=True)
    return os.path.join(cfg_dir, "config.json")

def get_global_config() -> Dict[str, Any]:
    """Load global settings (creates empty dict if not exists)."""
    path = get_global_config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_global_config(cfg: Dict[str, Any]) -> None:
    """Save global settings."""
    path = get_global_config_path()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        print(f"Failed to save global config: {e}")

# -----------------------------
# Init Config & Scale
# -----------------------------
_G_CFG = get_global_config()
_G_GEN = _G_CFG.get("general", {})

UI_SCALE = float(_G_GEN.get("ui_scale", 1.0))
# Attempt high-dpi awareness on Windows if scale > 1.0 or user requests
# (Often better to just do it if possible, but let's stick to safe defaults)
if os.name == "nt":
    try:
        from ctypes import windll
        # If scale is default 1.0, user might rely on OS scaling.
        # But if they set custom scale, they likely want us to handle it.
        # For now, we enforce DPI awareness aggressively to avoid "squished" buttons.
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


# -----------------------------
# UI Theme
# -----------------------------
UI = {
    "bg": "#0e0e0e",
    "panel": "#121212",
    "card": "#181818",
    "card_hover": "#222222",
    "surface": "#0a0a0a",
    "text": "#e8e8e8",
    "muted": "#9a9a9a",
    "accent": "#4cc9f0",
    "danger": "#ff4d6d",
    "good": "#2ee59d",
}

# Color theme presets
COLOR_THEMES = {
    "dark": {
        "bg": "#0e0e0e",
        "panel": "#121212",
        "card": "#181818",
        "card_hover": "#222222",
        "surface": "#0a0a0a",
        "text": "#e8e8e8",
        "muted": "#9a9a9a",
        "accent": "#4cc9f0",
        "danger": "#ff4d6d",
        "good": "#2ee59d",
    },
    "light": {
        "bg": "#ffffff",
        "panel": "#f5f5f5",
        "card": "#fafafa",
        "card_hover": "#e8e8e8",
        "surface": "#f0f0f0",
        "text": "#1a1a1a",
        "muted": "#666666",
        "accent": "#0891b2",
        "danger": "#dc2626",
        "good": "#16a34a",
    },
    "nord": {
        "bg": "#2e3440",
        "panel": "#3b4252",
        "card": "#434c5e",
        "card_hover": "#4c566a",
        "surface": "#2e3440",
        "text": "#eceff4",
        "muted": "#d8dee9",
        "accent": "#88c0d0",
        "danger": "#bf616a",
        "good": "#a3be8c",
    },
    "dracula": {
        "bg": "#282a36",
        "panel": "#343746",
        "card": "#44475a",
        "card_hover": "#6272a4",
        "surface": "#21222c",
        "text": "#f8f8f2",
        "muted": "#6272a4",
        "accent": "#bd93f9",
        "danger": "#ff5555",
        "good": "#50fa7b",
    },
    "monokai": {
        "bg": "#272822",
        "panel": "#2d2e27",
        "card": "#3e3d32",
        "card_hover": "#49483e",
        "surface": "#1e1f1c",
        "text": "#f8f8f2",
        "muted": "#75715e",
        "accent": "#66d9ef",
        "danger": "#f92672",
        "good": "#a6e22e",
    },
}

# Apply theme from config if present
_theme_name = _G_GEN.get("theme", "dark")
if _theme_name in COLOR_THEMES:
    UI.update(COLOR_THEMES[_theme_name])

# -----------------------------
# Fonts (Scaled)
# -----------------------------
def _scale_font(size: int) -> int:
    return int(size * UI_SCALE)

FONT_H1 = ("Segoe UI", _scale_font(20), "bold")
FONT_H2 = ("Segoe UI", _scale_font(16), "bold")
FONT_BODY = ("Segoe UI", _scale_font(11))
FONT_SMALL = ("Segoe UI", _scale_font(10))

# -----------------------------
# Helpers
# -----------------------------
def scaled_geometry(w: int, h: int) -> str:
    return f"{int(w * UI_SCALE)}x{int(h * UI_SCALE)}"



def discover_plugins() -> Dict[str, Dict[str, Any]]:
    plugins: Dict[str, Dict[str, Any]] = {}
    if not os.path.exists(PLUGINS_DIR):
        return plugins

    for fn in sorted(os.listdir(PLUGINS_DIR)):
        if not fn.endswith(".py"):
            continue

        name = os.path.splitext(fn)[0]
        path = os.path.join(PLUGINS_DIR, fn)

        info: Dict[str, Any] = {
            "name": name,
            "display": name,
            "desc": "",
            "path": path,
            "is_feed": True,      # default
            "defaults": None,     # optional dict
        }

        try:
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(mod)

            info["display"] = getattr(mod, "PLUGIN_NAME", name)
            info["desc"]    = getattr(mod, "PLUGIN_DESC", "")
            info["is_feed"] = bool(getattr(mod, "IS_FEED", True))

            # Plugin-provided defaults (any of these names are acceptable)
            # Keep it flexible so plugin authors have options.
            d = (
                getattr(mod, "FEED_DEFAULTS", None)
                or getattr(mod, "DEFAULT_FEED_CFG", None)
                or getattr(mod, "DEFAULT_CONFIG", None)
            )
            if isinstance(d, dict):
                info["defaults"] = d

        except Exception:
            # tolerate import failure; keep minimal info
            pass

        plugins[name] = info

    return plugins


def safe_read_yaml(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

def safe_write_yaml(path: str, obj: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True)
    os.replace(tmp, path)

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def now_ts() -> int:
    return int(time.time())

def station_manifest_path(station_dir: str) -> str:
    return os.path.join(station_dir, "manifest.yaml")

def station_status_path(station_dir: str) -> str:
    return os.path.join(station_dir, "status.json")

def station_db_path(station_dir: str) -> str:
    return os.path.join(station_dir, "station.sqlite")

def station_memory_path(station_dir: str) -> str:
    return os.path.join(station_dir, "station_memory.json")

def parse_list_field(s: str) -> List[Any]:
    """
    Accepts:
      - JSON list: ["a","b"]
      - YAML-ish list: [a, b]
      - comma list: a,b
      - empty
    Returns list.
    """
    s = (s or "").strip()
    if not s:
        return []
    # Try JSON first
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return v
    except Exception:
        pass
    # Try YAML list
    try:
        v = yaml.safe_load(s)
        if isinstance(v, list):
            return v
    except Exception:
        pass
    # Comma fallback
    return [x.strip() for x in s.split(",") if x.strip()]

def parse_scalar_field(s: str) -> Any:
    """
    Parses an entry field into bool/int/float/list/str as appropriate.
    - If it looks like JSON/YAML list -> list
    - If it is 'true/false' -> bool
    - If numeric -> int/float
    - Else string
    """
    raw = (s or "").strip()
    if raw == "":
        return ""

    low = raw.lower()
    if low in ("true", "false"):
        return low == "true"

    # list-ish
    if (raw.startswith("[") and raw.endswith("]")) or "," in raw:
        # but don't blindly convert every comma string into list for keys that are clearly scalars
        # (we'll only use this in dynamic editor where list values started as list)
        pass

    # number
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except Exception:
        return raw

def resolve_cfg_path(station_dir: str, p: str) -> str:
    """
    Resolve relative paths against:
      1) station_dir
      2) RADIO_OS_ROOT (BASE)
    """
    p = (p or "").strip()
    if not p:
        return ""
    if os.path.isabs(p):
        return p

    # Try station dir first
    cand = os.path.join(station_dir, p)
    if os.path.exists(cand):
        return cand

    # Try BASE
    cand = os.path.join(BASE, p)
    if os.path.exists(cand):
        return cand

    # Fall back to station relative join even if not exists
    return os.path.join(station_dir, p)


# -----------------------------
# Station discovery
# -----------------------------
@dataclass
class StationInfo:
    station_id: str
    path: str
    manifest: Dict[str, Any]

def load_stations() -> List[StationInfo]:
    out: List[StationInfo] = []
    if not os.path.exists(STATIONS_DIR):
        return out

    for name in sorted(os.listdir(STATIONS_DIR)):
        path = os.path.join(STATIONS_DIR, name)
        if not os.path.isdir(path):
            continue
        mp = station_manifest_path(path)
        if not os.path.exists(mp):
            continue
        cfg = safe_read_yaml(mp)
        out.append(StationInfo(station_id=name, path=path, manifest=cfg))
    return out

# -----------------------------
# Runtime process management
# -----------------------------
class StationProcess:
    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None
        self.station: Optional[StationInfo] = None
        self._log_file = None  # keep handle alive on Windows

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def launch(self, station: StationInfo) -> None:
        self.stop()

        env = os.environ.copy()
        env["STATION_DIR"] = station.path
        env["STATION_DB_PATH"] = station_db_path(station.path)
        env["STATION_MEMORY_PATH"] = station_memory_path(station.path)

        env.setdefault("RADIO_OS_ROOT", BASE)
        env.setdefault("RADIO_OS_PLUGINS", os.path.join(BASE, "plugins"))
        env.setdefault("RADIO_OS_VOICES", os.path.join(BASE, "voices"))
        
        # Inject Visual Model configuration from manifest > global config
        # 1. Start with global config
        global_cfg = get_global_config()
        visual_cfg = global_cfg.get("visual_models", {})
        
        # 2. Override with station manifest
        manifest = station.manifest or {}
        if "visual_models" in manifest:
            visual_cfg.update(manifest["visual_models"])
            
        if visual_cfg:
            env["VISUAL_MODEL_TYPE"] = str(visual_cfg.get("model_type", "local"))
            env["VISUAL_MODEL_LOCAL"] = str(visual_cfg.get("local_model", "llava:latest"))
            env["VISUAL_MODEL_API_PROVIDER"] = str(visual_cfg.get("api_provider", ""))
            env["VISUAL_MODEL_API_MODEL"] = str(visual_cfg.get("api_model", ""))
            env["VISUAL_MODEL_API_KEY"] = str(visual_cfg.get("api_key", ""))
            env["VISUAL_MODEL_API_ENDPOINT"] = str(visual_cfg.get("api_endpoint", ""))
            env["VISUAL_MODEL_MAX_IMAGE_SIZE"] = str(visual_cfg.get("max_image_size", "1024"))
            env["VISUAL_MODEL_IMAGE_QUALITY"] = str(visual_cfg.get("image_quality", "85"))

        # Ensure unbuffered UTF-8 output so logs are captured correctly
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"

        log_path = os.path.join(station.path, "runtime.log")
        lf = None
        try:
            lf = open(log_path, "a", encoding="utf-8", errors="ignore")
            lf.write("\n\n===== LAUNCH {} =====\n".format(time.strftime("%Y-%m-%d %H:%M:%S")))
            lf.flush()
        except Exception:
            lf = None

        cmd = [sys.executable, "-u", RUNTIME_PATH]

        kwargs = {"cwd": BASE, "env": env, "stdout": lf if lf else None, "stderr": lf if lf else None}
        if sys.platform == "win32":
            # hide console window for runtime (Windows only)
            # NOTE: CREATE_NO_WINDOW can prevent win32gui.EnumWindows() from working correctly.
            # Set RADIO_OS_SHOW_CONSOLE=1 to disable this for window enumeration/debugging.
            if not os.environ.get("RADIO_OS_SHOW_CONSOLE"):
                try:
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                except Exception:
                    pass

        self._log_file = lf
        self.proc = subprocess.Popen(cmd, **kwargs)
        self.station = station

    def stop(self) -> None:
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.proc = None
        self.station = None
        try:
            if self._log_file:
                self._log_file.flush()
                self._log_file.close()
        except Exception:
            pass
        self._log_file = None

# -----------------------------
# Shell UI
# -----------------------------
class RadioShell:
    def __init__(self):
        # Load theme before creating UI
        cfg = get_global_config()
        theme_name = cfg.get("general", {}).get("theme", "dark")
        if theme_name in COLOR_THEMES:
            UI.update(COLOR_THEMES[theme_name])
        
        self.root = tk.Tk()
        self.root.title("Radio OS")
        self.root.geometry(scaled_geometry(1440, 860))
        self.root.configure(bg=UI["bg"])

        self.proc = StationProcess()
        self.stations: List[StationInfo] = load_stations()
        self.selected_idx = 0

        self._view = "home"  # or "runtime"
        self._transitioning = False

        self._build_styles()
        self._build_top_bar()
        self._build_home_view()
        self._build_runtime_view()

        self._status_poll_ms = 450
        self._tick()

        self.show_home(instant=True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _refresh_ui_colors(self):
        """Refresh all UI elements with current theme colors."""
        # Update window background
        self.root.configure(bg=UI["bg"])
        
        # Update all frames and widgets recursively
        def update_widget_colors(widget):
            try:
                # Try common color options
                if hasattr(widget, 'configure'):
                    try:
                        widget.configure(bg=UI["bg"])
                    except:
                        pass
                    try:
                        widget.configure(fg=UI["text"])
                    except:
                        pass
            except:
                pass
            
            # Recurse on children
            for child in widget.winfo_children():
                update_widget_colors(child)
        
        # Update theme styles
        self._build_styles()
        
        # Update main widget tree
        update_widget_colors(self.root)
        
        # Force redraw
        self.root.update()

    def _restart_app(self):
        """Restart the application by closing and reopening."""
        import subprocess
        import sys
        
        # Save the current script path
        script_path = sys.argv[0]
        
        # Close the current app
        self.root.quit()
        self.root.destroy()
        
        # Restart the app in a new process
        subprocess.Popen([sys.executable, script_path])
        
        # Exit cleanly
        sys.exit(0)

    def _build_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TNotebook", background=UI["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", background=UI["panel"], foreground=UI["text"], padding=(12, 8))
        style.map("TNotebook.Tab", background=[("selected", UI["card_hover"])])
        style.configure("TSeparator", background=UI["panel"])
    def delete_station(self, station_id: str):
        # Find station object
        st = None
        for s in self.stations:
            if s.station_id == station_id:
                st = s
                break

        if not st:
            return

        # Confirm
        if not messagebox.askyesno(
            "Delete Station",
            f"Delete station '{st.station_id}'?\n\nThis cannot be undone."
        ):
            return

        # If it's currently running → stop it cleanly
        if self.proc.station and self.proc.station.station_id == station_id:
            self.proc.stop()

        # Delete folder
        try:
            shutil.rmtree(st.path)
        except Exception as e:
            messagebox.showerror("Delete failed", str(e))
            return

        # Refresh UI list
        self.refresh_stations()


    def on_station_right_click(self, event, station_id):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(
            label="Delete Station",
            command=lambda: self.delete_station(station_id)
        )
        menu.tk_popup(event.x_root, event.y_root)

    def _build_plugin_manager(self, parent):

        plugins = discover_plugins()

        tk.Label(
            parent,
            text="Installed Plugins",
            font=FONT_H2,
            fg=UI["text"],
            bg=UI["bg"]
        ).pack(anchor="w", padx=14, pady=(14, 10))

        if not plugins:
            tk.Label(
                parent,
                text="No plugins found in /plugins folder.",
                font=FONT_BODY,
                fg=UI["muted"],
                bg=UI["bg"]
            ).pack(anchor="w", padx=14)
            return

        # ============================
        # Scroll container
        # ============================

        scrollbar = tk.Scrollbar(parent, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        canvas = tk.Canvas(parent, bg=UI["bg"], highlightthickness=0, yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)

        scrollbar.configure(command=canvas.yview)

        frame = tk.Frame(canvas, bg=UI["bg"])
        canvas.create_window((0, 0), window=frame, anchor="nw")

        frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # ============================
        # Current station feeds
        # ============================

        st = self.proc.station or (self.stations[self.selected_idx] if self.stations else None)

        feeds = {}
        if st:
            feeds = st.manifest.get("feeds", {})
            if not isinstance(feeds, dict):
                feeds = {}

        # ============================
        # Build rows
        # ============================

        for name, info in plugins.items():

            # 👉 Skip widget-only plugins
            if not info.get("is_feed", True):
                continue

            row = tk.Frame(frame, bg=UI["panel"])
            row.pack(fill="x", padx=14, pady=6)

            left = tk.Frame(row, bg=UI["panel"])
            left.pack(side="left", fill="x", expand=True)

            tk.Label(
                left,
                text=info["display"],
                font=("Segoe UI", 12, "bold"),
                fg=UI["text"],
                bg=UI["panel"]
            ).pack(anchor="w", padx=10, pady=(6, 0))

            if info.get("desc"):
                tk.Label(
                    left,
                    text=info["desc"],
                    font=FONT_SMALL,
                    fg=UI["muted"],
                    bg=UI["panel"]
                ).pack(anchor="w", padx=10, pady=(0, 6))

            # ----------------------------
            # Enabled toggle
            # ----------------------------

            enabled = bool(feeds.get(name, {}).get("enabled", False))
            v_en = tk.BooleanVar(value=enabled)

            def toggle(n=name, var=v_en):

                st2 = self.proc.station or (
                    self.stations[self.selected_idx] if self.stations else None
                )

                if not st2:
                    return

                mp = station_manifest_path(st2.path)
                cfg = safe_read_yaml(mp)

                cfg.setdefault("feeds", {})

                if n not in cfg["feeds"] or not isinstance(cfg["feeds"].get(n), dict):
                    cfg["feeds"][n] = {}

                cfg["feeds"][n]["enabled"] = bool(var.get())

                safe_write_yaml(mp, cfg)

                # Update in-memory station
                st2.manifest = cfg

                # Refresh UI
                self.refresh_stations(select_id=st2.station_id)

            chk = tk.Checkbutton(
                row,
                variable=v_en,
                command=toggle,
                bg=UI["panel"],
                fg=UI["text"],
                selectcolor=UI["panel"],
                activebackground=UI["panel"]
            )

            chk.pack(side="right", padx=14)
    # -----------------------------
    # Top bar
    # -----------------------------
    def _build_top_bar(self):
        bar = tk.Frame(self.root, bg=UI["bg"], height=56)
        bar.pack(fill="x", side="top")

        # Try to load custom icon
        icon_label = None
        icon_path = os.path.join(BASE, "radioos.png")
        if os.path.exists(icon_path):
            try:
                from PIL import Image, ImageTk
                img = Image.open(icon_path)
                # Resize to fit in title bar (height ~52px, account for padding)
                img.thumbnail((52, 52), Image.Resampling.LANCZOS)
                self.icon_photo = ImageTk.PhotoImage(img)
                icon_label = tk.Label(bar, image=self.icon_photo, bg=UI["bg"])
                icon_label.pack(side="left", padx=(16, 12))
            except Exception as e:
                print(f"Failed to load icon: {e}")

        self.title_lbl = tk.Label(bar, text="Radio OS", font=FONT_H1, fg=UI["text"], bg=UI["bg"])
        self.title_lbl.pack(side="left", padx=(0 if icon_label else 16, 0))

        self.mode_lbl = tk.Label(bar, text="Station Browser", font=FONT_SMALL, fg=UI["muted"], bg=UI["bg"])
        self.mode_lbl.pack(side="left", padx=10)

        right = tk.Frame(bar, bg=UI["bg"])
        right.pack(side="right", padx=12)

        self.btn_new = tk.Button(
            right, text="＋ New Station", font=FONT_BODY,
            bg=UI["panel"], fg=UI["text"], relief="flat",
            command=self.create_station_wizard
        )
        self.btn_new.pack(side="left", padx=6)

        self.btn_settings = tk.Button(
            right, text="⚙ Settings", font=FONT_BODY,
            bg=UI["panel"], fg=UI["text"], relief="flat",
            command=self.open_settings
        )
        self.btn_settings.pack(side="left", padx=6)

    # -----------------------------
    # Home view
    # -----------------------------
    def _build_home_view(self):
        self.home = tk.Frame(self.root, bg=UI["bg"])

        header = tk.Frame(self.home, bg=UI["bg"])
        header.pack(fill="x", padx=18, pady=(14, 6))

        self.home_hint = tk.Label(
            header,
            text="Scroll / drag / arrows. Hover cards for previews. Enter to play.",
            font=FONT_BODY, fg=UI["muted"], bg=UI["bg"]
        )
        self.home_hint.pack(side="left")

        self.canvas = tk.Canvas(self.home, bg=UI["bg"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(0, 12))

        self.carousel = tk.Frame(self.canvas, bg=UI["bg"])
        self.carousel_window = self.canvas.create_window((0, 0), window=self.carousel, anchor="nw")

        self.canvas.configure(xscrollincrement=1)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.carousel.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self._drag_last = None
        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)

        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.root.bind("<Left>", lambda e: self._nav(-1))
        self.root.bind("<Right>", lambda e: self._nav(1))
        self.root.bind("<Return>", lambda e: self._play_selected())

        self.cards: List[Dict[str, Any]] = []
        self._render_cards()
        self.root.after(120, lambda: self._snap_to_index(self.selected_idx, animate=False))

    def _render_cards(self):
        for w in self.carousel.winfo_children():
            w.destroy()
        self.cards.clear()

        if not self.stations:
            tk.Label(self.carousel, text="No stations found. Create one.", font=FONT_H2, fg=UI["muted"], bg=UI["bg"]).pack(
                pady=140
            )
            return

        for i, st in enumerate(self.stations):
            card = self._create_station_card(self.carousel, st, i)
            card.pack(side="left", padx=int(18 * UI_SCALE), pady=int(140 * UI_SCALE))
            self.cards.append({"frame": card, "station": st})

        self._highlight_selected()


    def _add_rounded_corners(self, parent_frame: tk.Frame, radius: int, bg_color: str, card_color: str):
        if not HAS_PIL:
            return

        # Cache key
        k = f"{radius}_{bg_color}_{card_color}"
        if not hasattr(self, "_corner_cache"):
            self._corner_cache = {}
        
        if k not in self._corner_cache:
            def make_corner(anchor):
                # high-res for better antialiasing then downscale?
                # For now simple drawing.
                # anchor: nw, ne, sw, se
                size = radius
                img = Image.new("RGBA", (size, size), bg_color)
                draw = ImageDraw.Draw(img)
                
                # Draw the card-colored arc (masking the bg color)
                # Effectively we are drawing the "card" onto the "bg" base.
                if anchor == "nw":
                    # Draw a circle sector filled with card_color
                    # Center at (radius, radius)
                    # Bbox (0, 0, 2*r, 2*r)
                    draw.pieslice([(0, 0), (radius*2, radius*2)], 180, 270, fill=card_color)
                elif anchor == "ne":
                    draw.pieslice([(-radius, 0), (radius, radius*2)], 270, 360, fill=card_color)
                elif anchor == "sw":
                    draw.pieslice([(0, -radius), (radius*2, radius)], 90, 180, fill=card_color)
                elif anchor == "se":
                    draw.pieslice([(-radius, -radius), (radius, radius)], 0, 90, fill=card_color)
                
                return ImageTk.PhotoImage(img)

            self._corner_cache[k] = {
                "nw": make_corner("nw"),
                "ne": make_corner("ne"),
                "sw": make_corner("sw"),
                "se": make_corner("se"),
            }

        corners = self._corner_cache[k]

        # Place labels at corners
        tk.Label(parent_frame, image=corners["nw"], bg=card_color, borderwidth=0).place(x=0, y=0, anchor="nw")
        tk.Label(parent_frame, image=corners["ne"], bg=card_color, borderwidth=0).place(relx=1.0, y=0, anchor="ne")
        tk.Label(parent_frame, image=corners["sw"], bg=card_color, borderwidth=0).place(x=0, rely=1.0, anchor="sw")
        tk.Label(parent_frame, image=corners["se"], bg=card_color, borderwidth=0).place(relx=1.0, rely=1.0, anchor="se")

    def _create_station_card(self, parent, station: StationInfo, idx: int) -> tk.Frame:
        cfg = station.manifest or {}
        st_meta = cfg.get("station", {}) if isinstance(cfg.get("station", {}), dict) else {}
        name = st_meta.get("name", station.station_id)
        cat = st_meta.get("category", "Custom")
        logo_path = st_meta.get("logo", "")

        # Square-ish dimensions
        CARD_W = int(320 * UI_SCALE)
        CARD_H = int(400 * UI_SCALE)
        
        card = tk.Frame(parent, bg=UI["card"], width=CARD_W, height=CARD_H)
        card.pack_propagate(False)

        # ----------------------------
        # Art / Logo
        # ----------------------------
        art_height = 0
        if logo_path and HAS_PIL:
            p = resolve_cfg_path(station.path, logo_path)
            if os.path.exists(p):
                try:
                    # Load and resize
                    pil_img = Image.open(p).convert("RGBA")
                    
                    # Target size for the art area
                    target_w = CARD_W - int(24 * UI_SCALE)
                    target_h = int(180 * UI_SCALE)
                    
                    # Crop/Resize to fill
                    pil_img = ImageOps.fit(pil_img, (target_w, target_h), method=Image.Resampling.LANCZOS)

                    # Round corners of the image
                    mask = Image.new("L", (target_w, target_h), 0)
                    draw = ImageDraw.Draw(mask)
                    radius = int(16 * UI_SCALE)
                    draw.rounded_rectangle((0, 0, target_w, target_h), radius=radius, fill=255)
                    
                    # Apply mask
                    pil_img.putalpha(mask)

                    # Convert to PhotoImage (must keep reference)
                    tk_img = ImageTk.PhotoImage(pil_img)
                    
                    lbl_art = tk.Label(card, image=tk_img, bg=UI["card"])
                    lbl_art.image = tk_img  # keep ref
                    lbl_art.pack(pady=(int(12 * UI_SCALE), 0))
                    art_height = target_h
                except Exception as e:
                    print(f"Failed to load logo {logo_path}: {e}")

        # If no art, add spacer or generic header
        if art_height == 0:
            tk.Frame(card, bg=UI["card"], height=int(20 * UI_SCALE)).pack()

        title = tk.Label(card, text=name, font=("Segoe UI", _scale_font(18), "bold"), fg=UI["text"], bg=UI["card"], wraplength=int(280 * UI_SCALE), justify="center")
        title.pack(pady=(int(12 * UI_SCALE), int(4 * UI_SCALE)))

        tag = tk.Label(card, text=str(cat).upper(), font=FONT_SMALL, fg=UI["accent"], bg=UI["card"])
        tag.pack()

        # Divider only if we have space
        ttk.Separator(card, orient="horizontal").pack(fill="x", padx=14, pady=10)

        # Feeds/info area - dynamic spacer
        feeds_frame = tk.Frame(card, bg=UI["card"])
        feeds_frame.pack(fill="x", padx=14, expand=True) # Expand to push buttons down

        chars = cfg.get("characters", {}) if isinstance(cfg.get("characters", {}), dict) else {}
        char_count = len(chars)
        
        # Simple summary line instead of list to save space
        f_list = [k for k, v in (cfg.get("feeds", {}) or {}).items() if v.get("enabled")]
        f_text = f"{len(f_list)} feeds active" if f_list else "No feeds"
        
        info_row = tk.Frame(feeds_frame, bg=UI["card"])
        info_row.pack(fill="x")
        
        tk.Label(info_row, text=f_text, font=FONT_BODY, fg=UI["muted"], bg=UI["card"]).pack(side="left")
        if char_count > 0:
            tk.Label(info_row, text=f" • {char_count} voices", font=FONT_BODY, fg=UI["muted"], bg=UI["card"]).pack(side="left")

        # Buttons area
        actions = tk.Frame(card, bg=UI["card"])
        actions.pack(fill="x", padx=int(14 * UI_SCALE), pady=(0, int(16 * UI_SCALE)), side="bottom")

        # Play Button (Primary)
        # Using a slightly taller/bolder look
        btn_play = tk.Button(
            actions, text="▶ PLAY", font=("Segoe UI", _scale_font(11), "bold"),
            bg=UI["accent"], fg="#000", relief="flat",
            activebackground=UI["good"], activeforeground="#000",
            cursor="hand2",
            command=lambda s=station: self.launch_station(s)
        )
        btn_play.pack(side="left", fill="x", expand=True, padx=(0, int(6 * UI_SCALE)), ipady=int(8 * UI_SCALE))

        # Edit Button (Secondary)
        btn_edit = tk.Button(
            actions, text="EDIT", font=("Segoe UI", _scale_font(11), "bold"),
            bg=UI["panel"], fg=UI["text"], relief="flat",
             activebackground=UI["card_hover"], activeforeground=UI["text"],
             cursor="hand2",
            command=lambda s=station: self.edit_station(s)
        )
        btn_edit.pack(side="left", fill="x", expand=True, padx=(int(6 * UI_SCALE), 0), ipady=int(8 * UI_SCALE))

        def hover_in(_):
            self._set_card_bg(card, UI["card_hover"])
        def hover_out(_):
            sel = (idx == self.selected_idx)
            base = UI["card_hover"] if sel else UI["card"]
            self._set_card_bg(card, base)

        card.bind("<Enter>", hover_in)
        card.bind("<Leave>", hover_out)

        card.bind("<Button-1>", lambda e: self._select_index(idx))
        for w in card.winfo_children():
            w.bind("<Button-1>", lambda e: self._select_index(idx))
        # Right click delete menu
        card.bind(
            "<Button-3>",
            lambda e, sid=station.station_id: self.on_station_right_click(e, sid)
        )

        for w in card.winfo_children():
            w.bind(
                "<Button-3>",
                lambda e, sid=station.station_id: self.on_station_right_click(e, sid)
            )

        # Apply rounded corners mask to the card frame itself
        self._add_rounded_corners(card, int(16 * UI_SCALE), UI["bg"], UI["card"])

        return card

    def _set_card_bg(self, card: tk.Frame, bg: str):
        try:
            card.configure(bg=bg)
            for w in card.winfo_children():
                if isinstance(w, (tk.Label, tk.Frame)):
                    try:
                        w.configure(bg=bg)
                    except Exception:
                        pass
        except Exception:
            pass

    def _select_index(self, idx: int):
        if not self.stations:
            return
        self.selected_idx = int(clamp(idx, 0, len(self.stations) - 1))
        self._highlight_selected()
        self._snap_to_index(self.selected_idx, animate=True)

    def _highlight_selected(self):
        for i, c in enumerate(self.cards):
            frame: tk.Frame = c["frame"]
            bg = UI["card_hover"] if (i == self.selected_idx) else UI["card"]
            self._set_card_bg(frame, bg)

    def _nav(self, step: int):
        if self._view != "home" or not self.stations:
            return
        self._select_index(self.selected_idx + step)

    def _play_selected(self):
        if self._view != "home" or not self.stations:
            return
        self.launch_station(self.stations[self.selected_idx])

    def _on_mousewheel(self, e):
        if self._view != "home":
            return
        delta = int(-1 * (e.delta / 120))
        self.canvas.xview_scroll(delta * 8, "units")

    def _drag_start(self, e):
        self._drag_last = (e.x, self.canvas.canvasx(0))

    def _drag_move(self, e):
        if not self._drag_last:
            return
        x0, cx0 = self._drag_last
        dx = e.x - x0
        bbox = self.canvas.bbox("all")
        total_w = max(bbox[2], 1) if bbox else 1
        self.canvas.xview_moveto(max(0.0, (cx0 - dx) / total_w))

    def _drag_end(self, e):
        self._drag_last = None
        self._snap_to_nearest()

    def _on_canvas_resize(self, e):
        self.canvas.itemconfigure(self.carousel_window, height=e.height)

    def _snap_to_nearest(self):
        if not self.cards:
            return

        vx0 = self.canvas.canvasx(0)
        vw = self.canvas.winfo_width()
        vcenter = vx0 + vw / 2

        best_i, best_d = 0, 1e18
        for i, c in enumerate(self.cards):
            f: tk.Frame = c["frame"]
            fx = f.winfo_x()
            fw = max(f.winfo_width(), 1)
            center = fx + fw / 2
            d = abs(center - vcenter)
            if d < best_d:
                best_d, best_i = d, i

        self._select_index(best_i)
        self._snap_to_index(best_i, animate=True)

    def _snap_to_index(self, idx: int, animate: bool):
        if not self.cards:
            return

        idx = int(clamp(idx, 0, len(self.cards) - 1))
        f: tk.Frame = self.cards[idx]["frame"]

        self.root.update_idletasks()
        bbox = self.canvas.bbox("all")
        if not bbox:
            return
        total_w = max(bbox[2], 1)
        vw = max(self.canvas.winfo_width(), 1)

        fx = f.winfo_x()
        fw = max(f.winfo_width(), 1)
        target_center = fx + fw / 2
        target_left = clamp(target_center - vw / 2, 0, max(total_w - vw, 1))

        if not animate:
            self.canvas.xview_moveto(target_left / total_w)
            return

        # lightweight animation
        start_left = self.canvas.canvasx(0)
        t0 = time.time()
        dur = 0.22

        def step():
            t = (time.time() - t0) / dur
            if t >= 1.0:
                self.canvas.xview_moveto(target_left / total_w)
                return
            k = 1 - (1 - clamp(t, 0.0, 1.0)) ** 3
            cur = start_left + (target_left - start_left) * k
            self.canvas.xview_moveto(cur / total_w)
            self.root.after(16, step)

        step()

    # -----------------------------
    # Runtime view
    # -----------------------------
    def _build_runtime_view(self):
        self.runtime = tk.Frame(self.root, bg=UI["bg"])

        left = tk.Frame(self.runtime, bg=UI["panel"], width=int(320 * UI_SCALE))
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        top_left = tk.Frame(left, bg=UI["panel"])
        top_left.pack(fill="x", padx=14, pady=14)

        self.btn_back = tk.Button(
            top_left, text="← Back", font=FONT_BODY,
            bg=UI["panel"], fg=UI["text"], relief="flat",
            command=self.stop_station
        )
        self.btn_back.pack(side="left")

        self.btn_stop = tk.Button(
            top_left, text="⏹ Stop", font=FONT_BODY,
            bg=UI["panel"], fg=UI["danger"], relief="flat",
            command=self.stop_station
        )
        self.btn_stop.pack(side="right")

        status_box = tk.Frame(left, bg=UI["panel"])
        status_box.pack(fill="x", padx=14, pady=(0, 10))

        tk.Label(status_box, text="Runtime Status", font=("Segoe UI", 12, "bold"), fg=UI["text"], bg=UI["panel"]).pack(anchor="w")

        self.status_lines = tk.Text(
            status_box, height=12, wrap="word",
            bg=UI["surface"], fg=UI["text"], font=("Consolas", 10),
            relief="flat", bd=0
        )
        self.status_lines.pack(fill="x", pady=(8, 0))
        self.status_lines.config(state="disabled")

        tk.Label(left, text="(Feed activity coming next)", font=FONT_BODY, fg=UI["muted"], bg=UI["panel"]).pack(
            anchor="w", padx=14, pady=(6, 0)
        )

        center = tk.Frame(self.runtime, bg=UI["surface"])
        center.pack(side="left", fill="both", expand=True)

        self.runtime_title = tk.Label(center, text="Visual Surface", font=FONT_H2, fg=UI["muted"], bg=UI["surface"])
        self.runtime_title.pack(expand=True)

        bottom = tk.Frame(self.runtime, bg="#000000", height=84)
        bottom.pack(side="bottom", fill="x")
        bottom.pack_propagate(False)

        self.now_playing = tk.Label(bottom, text="", font=("Segoe UI", 18, "bold"), fg=UI["text"], bg="#000000")
        self.now_playing.pack(anchor="w", padx=20, pady=(12, 0))

        self.now_sub = tk.Label(bottom, text="", font=("Segoe UI", 12), fg=UI["muted"], bg="#000000")
        self.now_sub.pack(anchor="w", padx=20, pady=(2, 0))

    # -----------------------------
    # View transitions
    # -----------------------------
    def show_home(self, instant: bool = False):
        if self._transitioning:
            return
        self._view = "home"
        self.mode_lbl.config(text="Station Browser")
        self.runtime.pack_forget()
        self.home.pack(fill="both", expand=True)
        self._transitioning = False if instant else True
        if not instant:
            self.root.after(180, lambda: setattr(self, "_transitioning", False))

    def show_runtime(self, instant: bool = False):
        if self._transitioning:
            return
        self._view = "runtime"
        self.mode_lbl.config(text="Station Runtime")
        self.home.pack_forget()
        self.runtime.pack(fill="both", expand=True)
        self._transitioning = False if instant else True
        if not instant:
            self.root.after(180, lambda: setattr(self, "_transitioning", False))

    # -----------------------------
    # Station actions
    # -----------------------------
    def launch_station(self, station: StationInfo):
        self.proc.launch(station)
        name = (station.manifest.get("station", {}) or {}).get("name", station.station_id)
        self.now_playing.config(text=f"Now Playing — {name}")
        self.now_sub.config(text="Launching runtime…")
        self.show_runtime()

    def stop_station(self):
        self.proc.stop()
        self.now_playing.config(text="")
        self.now_sub.config(text="")
        self.show_home()

    # -----------------------------
    # Settings
    # -----------------------------
    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Settings")
        win.geometry(scaled_geometry(900, 600))
        win.configure(bg=UI["bg"])

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=12, pady=12)

        gen = tk.Frame(nb, bg=UI["bg"])
        nb.add(gen, text="General")
        self._build_general_settings(gen)

        mdl = tk.Frame(nb, bg=UI["bg"])
        nb.add(mdl, text="Models")
        self._build_model_settings(mdl)

        voc = tk.Frame(nb, bg=UI["bg"])
        nb.add(voc, text="Voices")
        self._build_voice_settings(voc)

        plug = tk.Frame(nb, bg=UI["bg"])
        nb.add(plug, text="Plugins")
        self._build_plugin_manager(plug)

        vis = tk.Frame(nb, bg=UI["bg"])
        nb.add(vis, text="Visual Models")
        self._build_visual_models_panel(vis)

        st = tk.Frame(nb, bg=UI["bg"])
        nb.add(st, text="Storage")
        self._build_storage_tools(st)

    def _build_general_settings(self, parent: tk.Frame) -> None:
        """Build the General settings panel."""
        
        # Make scrollable
        scrollbar = tk.Scrollbar(parent, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        
        canvas = tk.Canvas(parent, bg=UI["bg"], highlightthickness=0, yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        
        scrollbar.configure(command=canvas.yview)
        
        scroll_frame = tk.Frame(canvas, bg=UI["bg"])
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        
        tk.Label(scroll_frame, text="General Settings", font=FONT_H2, fg=UI["text"], bg=UI["bg"]).pack(
            anchor="w", padx=14, pady=(14, 8)
        )
        
        wrap = tk.Frame(scroll_frame, bg=UI["bg"])
        wrap.pack(fill="both", expand=True, padx=14, pady=8)
        
        cfg = get_global_config()
        general = cfg.get("general", {})
        
        # Auto-start last station
        auto_start_var = tk.BooleanVar(value=general.get("auto_start_last_station", False))
        auto_frame = tk.Frame(wrap, bg=UI["panel"], padx=12, pady=10)
        auto_frame.pack(fill="x", pady=8)
        tk.Checkbutton(
            auto_frame, 
            text="Auto-start last active station on launch",
            variable=auto_start_var,
            bg=UI["panel"], fg=UI["text"], selectcolor=UI["bg"],
            font=FONT_BODY
        ).pack(anchor="w")
        
        # Status poll interval
        poll_frame = tk.LabelFrame(wrap, text="Status Update Interval", fg=UI["text"], 
                                    bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        poll_frame.pack(fill="x", pady=8)
        
        tk.Label(poll_frame, text="Update runtime status every (ms):", fg=UI["text"], 
                bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        poll_var = tk.StringVar(value=str(general.get("status_poll_ms", 1000)))
        tk.Entry(poll_frame, textvariable=poll_var, bg=UI["card"], fg=UI["text"], 
                insertbackground=UI["text"], width=10).pack(anchor="w", pady=(2, 4))
        tk.Label(poll_frame, text="(Lower = more responsive, higher = less CPU usage)", 
                fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        
        # Theme
        theme_frame = tk.LabelFrame(wrap, text="UI Theme", fg=UI["text"], 
                                     bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        theme_frame.pack(fill="x", pady=8)
        
        tk.Label(theme_frame, text="Choose a color theme:", fg=UI["text"], 
                bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        
        theme_var = tk.StringVar(value=general.get("theme", "dark"))
        
        # Theme selection with preview swatches
        theme_select_frame = tk.Frame(theme_frame, bg=UI["panel"])
        theme_select_frame.pack(fill="x", pady=(2, 4))
        
        tk.Label(theme_select_frame, text="Theme:", fg=UI["text"], 
                bg=UI["panel"], font=FONT_SMALL).pack(side="left", padx=(0, 8))
        
        theme_combo = ttk.Combobox(theme_select_frame, textvariable=theme_var, 
                                   values=list(COLOR_THEMES.keys()), state="readonly", width=15)
        theme_combo.pack(side="left", padx=(0, 12))
        
        # Preview swatches
        swatch_frame = tk.Frame(theme_select_frame, bg=UI["panel"])
        swatch_frame.pack(side="left")
        
        preview_swatches = []
        
        def update_preview(*args):
            theme_name = theme_var.get()
            if theme_name in COLOR_THEMES:
                colors = COLOR_THEMES[theme_name]
                swatch_colors = [colors["bg"], colors["panel"], colors["accent"], colors["text"]]
                for i, swatch in enumerate(preview_swatches):
                    if i < len(swatch_colors):
                        swatch.config(bg=swatch_colors[i])
        
        # Create 4 color swatches
        for i in range(4):
            swatch = tk.Label(swatch_frame, text="  ", bg=UI["bg"], width=3, height=1, relief="solid", borderwidth=1)
            swatch.pack(side="left", padx=1)
            preview_swatches.append(swatch)
        
        theme_combo.bind("<<ComboboxSelected>>", update_preview)
        update_preview()  # Initial preview
        
        tk.Label(theme_frame, text="(Requires restart to apply)", 
                fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w", pady=(4, 0))

        # UI Scale
        scale_frame = tk.LabelFrame(wrap, text="UI Scale (DPI Zoom)", fg=UI["text"], 
                                     bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        scale_frame.pack(fill="x", pady=8)

        tk.Label(scale_frame, text="Zoom Level (0.8 - 2.5):", fg=UI["text"], 
                bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")

        # Use global UI_SCALE as default
        # Note: we re-read config here to be safe, though UI_SCALE global exists
        _cur_gen = get_global_config().get("general", {})
        scale_var = tk.DoubleVar(value=_cur_gen.get("ui_scale", 1.0))
        
        scale_slider = tk.Scale(scale_frame, from_=0.8, to=2.5, resolution=0.1, orient="horizontal",
                                variable=scale_var, bg=UI["panel"], fg=UI["text"], highlightthickness=0, length=300)
        scale_slider.pack(anchor="w", pady=(2, 4))
        
        tk.Label(scale_frame, text="(Requires restart to apply)", 
                fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        
        # Save button
        def save_general():
            cfg = get_global_config()
            new_theme = theme_var.get()
            new_scale = scale_var.get()
            
            old_gen = cfg.get("general", {})
            old_theme = old_gen.get("theme", "dark")
            old_scale = float(old_gen.get("ui_scale", 1.0))
            
            cfg["general"] = {
                "auto_start_last_station": auto_start_var.get(),
                "status_poll_ms": int(poll_var.get() or 1000),
                "theme": new_theme,
                "ui_scale": new_scale,
            }
            save_global_config(cfg)
            
            # If theme or scale changed, restart the app
            if new_theme != old_theme or abs(new_scale - old_scale) > 0.001:
                if messagebox.askyesno("Display Settings Changed", 
                    "Display settings will be applied after restart.\n\nClose and reopen the application?"):
                    self._restart_app()
                    return
            
            messagebox.showinfo("Success", "General settings saved!")
        
        tk.Button(wrap, text="Save Settings", font=FONT_BODY, bg=UI["accent"], 
                 fg="#000", relief="flat", command=save_general).pack(anchor="w", pady=16)

    def _build_model_settings(self, parent: tk.Frame) -> None:
        """Build the Model Provider settings panel (defaults for new stations)."""
        
        # Make scrollable
        scrollbar = tk.Scrollbar(parent, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        
        canvas = tk.Canvas(parent, bg=UI["bg"], highlightthickness=0, yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        
        scrollbar.configure(command=canvas.yview)
        
        scroll_frame = tk.Frame(canvas, bg=UI["bg"])
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        
        tk.Label(scroll_frame, text="Default Model Settings", font=FONT_H2, fg=UI["text"], bg=UI["bg"]).pack(
            anchor="w", padx=14, pady=(14, 4)
        )
        tk.Label(scroll_frame, text="Set default LLM providers, endpoints, and models for new stations", 
                font=FONT_SMALL, fg=UI["muted"], bg=UI["bg"]).pack(anchor="w", padx=14, pady=(0, 8))
        
        wrap = tk.Frame(scroll_frame, bg=UI["bg"])
        wrap.pack(fill="both", expand=True, padx=14, pady=8)
        
        cfg = get_global_config()
        models = cfg.get("default_models", {})
        
        # LLM Provider Selection
        provider_frame = tk.LabelFrame(wrap, text="LLM Provider", fg=UI["text"], 
                                       bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        provider_frame.pack(fill="x", pady=8)
        
        tk.Label(provider_frame, text="Primary Provider:", fg=UI["text"], 
                bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        provider_var = tk.StringVar(value=models.get("provider", "ollama"))
        provider_options = ["ollama", "anthropic", "openai", "google"]
        provider_combo = ttk.Combobox(provider_frame, textvariable=provider_var, 
                                     values=provider_options, state="readonly", width=30)
        provider_combo.pack(anchor="w", pady=(2, 8))
        
        tk.Label(provider_frame, text="• ollama: Local models or OpenAI-compatible API\n"
                                     "• anthropic: Claude API (requires API key)\n"
                                     "• openai: GPT models (requires API key)\n"
                                     "• google: Gemini API (requires API key)", 
                fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL, justify="left").pack(anchor="w")
        
        # Ollama/Local Endpoint
        ollama_frame = tk.LabelFrame(wrap, text="Ollama / Local LLM Endpoint", fg=UI["text"], 
                                     bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        ollama_frame.pack(fill="x", pady=8)
        
        tk.Label(ollama_frame, text="Endpoint URL:", fg=UI["text"], 
                bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        tk.Label(ollama_frame, text="(e.g., http://localhost:11434 or any OpenAI-compatible endpoint)", 
                fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        
        ollama_var = tk.StringVar(value=models.get("llm_endpoint", "http://127.0.0.1:11434/api/generate"))
        tk.Entry(ollama_frame, textvariable=ollama_var, bg=UI["card"], fg=UI["text"], 
                insertbackground=UI["text"]).pack(fill="x", pady=(2, 8))
        
        # API Keys for Cloud Providers
        api_frame = tk.LabelFrame(wrap, text="Cloud Provider API Keys", fg=UI["text"], 
                                  bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        api_frame.pack(fill="x", pady=8)
        
        # Anthropic API Key
        tk.Label(api_frame, text="Anthropic API Key (Claude):", fg=UI["text"], 
                bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        anthropic_var = tk.StringVar(value=models.get("anthropic_api_key", ""))
        tk.Entry(api_frame, textvariable=anthropic_var, bg=UI["card"], fg=UI["text"], 
                insertbackground=UI["text"], show="•").pack(fill="x", pady=(2, 8))
        
        # OpenAI API Key
        tk.Label(api_frame, text="OpenAI API Key (GPT):", fg=UI["text"], 
                bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        openai_var = tk.StringVar(value=models.get("openai_api_key", ""))
        tk.Entry(api_frame, textvariable=openai_var, bg=UI["card"], fg=UI["text"], 
                insertbackground=UI["text"], show="•").pack(fill="x", pady=(2, 8))
        
        # Google/Gemini API Key
        tk.Label(api_frame, text="Google API Key (Gemini):", fg=UI["text"], 
                bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        google_var = tk.StringVar(value=models.get("google_api_key", ""))
        tk.Entry(api_frame, textvariable=google_var, bg=UI["card"], fg=UI["text"], 
                insertbackground=UI["text"], show="•").pack(fill="x", pady=(2, 8))
        
        # Producer Model
        producer_frame = tk.LabelFrame(wrap, text="Default Producer Model", fg=UI["text"], 
                                       bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        producer_frame.pack(fill="x", pady=8)
        
        tk.Label(producer_frame, text="Model Name:", fg=UI["text"], 
                bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        tk.Label(producer_frame, text="(e.g., llama3.1:70b, claude-3-opus-20240229, gpt-4o, gemini-1.5-pro)", 
                fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        
        producer_var = tk.StringVar(value=models.get("producer_model", "rnj-1:8b"))
        tk.Entry(producer_frame, textvariable=producer_var, bg=UI["card"], fg=UI["text"], 
                insertbackground=UI["text"]).pack(fill="x", pady=(2, 8))
        tk.Label(producer_frame, text="(Context-building, slower, higher quality)", 
                fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        
        # Host Model
        host_frame = tk.LabelFrame(wrap, text="Default Host Model", fg=UI["text"], 
                                   bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        host_frame.pack(fill="x", pady=8)
        
        tk.Label(host_frame, text="Model Name:", fg=UI["text"], 
                bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        tk.Label(host_frame, text="(e.g., llama3.1:70b, claude-3-opus-20240229, gpt-4o, gemini-1.5-pro)", 
                fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        
        host_var = tk.StringVar(value=models.get("host_model", "rnj-1:8b"))
        tk.Entry(host_frame, textvariable=host_var, bg=UI["card"], fg=UI["text"], 
                insertbackground=UI["text"]).pack(fill="x", pady=(2, 8))
        tk.Label(host_frame, text="(Live hosting, faster responses)", 
                fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        
        # Save button
        def save_models():
            cfg = get_global_config()
            cfg["default_models"] = {
                "provider": provider_var.get(),
                "llm_endpoint": ollama_var.get(),
                "anthropic_api_key": anthropic_var.get(),
                "openai_api_key": openai_var.get(),
                "google_api_key": google_var.get(),
                "producer_model": producer_var.get(),
                "host_model": host_var.get(),
            }
            save_global_config(cfg)
            messagebox.showinfo("Success", "Model settings saved!")
        
        tk.Button(wrap, text="Save Settings", font=FONT_BODY, bg=UI["accent"], 
                 fg="#000", relief="flat", command=save_models).pack(anchor="w", pady=16)

    def _build_voice_settings(self, parent: tk.Frame) -> None:
        """Build the Voice settings panel (defaults for new stations)."""
        
        # Make scrollable
        scrollbar = tk.Scrollbar(parent, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        
        canvas = tk.Canvas(parent, bg=UI["bg"], highlightthickness=0, yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        
        scrollbar.configure(command=canvas.yview)
        
        scroll_frame = tk.Frame(canvas, bg=UI["bg"])
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        
        tk.Label(scroll_frame, text="Default Voice Settings", font=FONT_H2, fg=UI["text"], bg=UI["bg"]).pack(
            anchor="w", padx=14, pady=(14, 4)
        )
        tk.Label(scroll_frame, text="Set global voice paths used as defaults for new stations", 
                font=FONT_SMALL, fg=UI["muted"], bg=UI["bg"]).pack(anchor="w", padx=14, pady=(0, 8))
        
        wrap = tk.Frame(scroll_frame, bg=UI["bg"])
        wrap.pack(fill="both", expand=True, padx=14, pady=8)
        
        cfg = get_global_config()
        voices = cfg.get("default_voices", {})
        
        # Voice Provider Selection
        provider_frame = tk.LabelFrame(wrap, text="Voice Provider", fg=UI["text"], 
                                       bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        provider_frame.pack(fill="x", pady=8)
        
        tk.Label(provider_frame, text="TTS Provider:", fg=UI["text"], 
                bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        provider_var = tk.StringVar(value=voices.get("provider", "piper"))
        provider_options = ["piper", "elevenlabs", "google_cloud_tts", "azure_speech"]
        provider_combo = ttk.Combobox(provider_frame, textvariable=provider_var, 
                                     values=provider_options, state="readonly", width=30)
        provider_combo.pack(anchor="w", pady=(2, 8))
        
        tk.Label(provider_frame, text="• piper: Local offline TTS (requires binary + ONNX models)\n"
                                     "• elevenlabs: ElevenLabs API (requires API key)\n"
                                     "• google_cloud_tts: Google Cloud TTS (requires credentials)\n"
                                     "• azure_speech: Azure Speech Services (requires API key)", 
                fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL, justify="left").pack(anchor="w")
        
        # Piper Binary (for local)
        piper_frame = tk.LabelFrame(wrap, text="Piper TTS Binary (Local Only)", fg=UI["text"], 
                                    bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        piper_frame.pack(fill="x", pady=8)
        
        tk.Label(piper_frame, text="Piper Binary Path:", fg=UI["text"], 
                bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        
        piper_row = tk.Frame(piper_frame, bg=UI["panel"])
        piper_row.pack(fill="x", pady=(2, 4))
        
        piper_var = tk.StringVar(value=voices.get("piper_bin", ""))
        tk.Entry(piper_row, textvariable=piper_var, bg=UI["card"], fg=UI["text"], 
                insertbackground=UI["text"]).pack(side="left", fill="x", expand=True, padx=(0, 8))
        
        def browse_piper():
            path = filedialog.askopenfilename(parent=parent.winfo_toplevel(),
                                              title="Select Piper Binary")
            if path:
                piper_var.set(path)
        
        tk.Button(piper_row, text="Browse", bg=UI["card"], fg=UI["text"], relief="flat",
                 command=browse_piper).pack(side="left")
        
        # API Configuration (for cloud providers)
        api_frame = tk.LabelFrame(wrap, text="API Provider Configuration", fg=UI["text"], 
                                  bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        api_frame.pack(fill="x", pady=8)
        
        tk.Label(api_frame, text="API Key (ElevenLabs/Azure):", fg=UI["text"], 
                bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        api_key_var = tk.StringVar(value=voices.get("api_key", ""))
        tk.Entry(api_frame, textvariable=api_key_var, bg=UI["card"], fg=UI["text"], 
                insertbackground=UI["text"], show="•").pack(fill="x", pady=(2, 8))
        
        tk.Label(api_frame, text="Google Cloud Credentials Path (JSON):", fg=UI["text"], 
                bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        
        gcloud_row = tk.Frame(api_frame, bg=UI["panel"])
        gcloud_row.pack(fill="x", pady=(2, 4))
        
        gcloud_var = tk.StringVar(value=voices.get("google_credentials", ""))
        tk.Entry(gcloud_row, textvariable=gcloud_var, bg=UI["card"], fg=UI["text"], 
                insertbackground=UI["text"]).pack(side="left", fill="x", expand=True, padx=(0, 8))
        
        def browse_gcloud():
            path = filedialog.askopenfilename(parent=parent.winfo_toplevel(),
                                              title="Select Google Credentials JSON",
                                              filetypes=[("JSON", "*.json"), ("All", "*.*")])
            if path:
                gcloud_var.set(path)
        
        tk.Button(gcloud_row, text="Browse", bg=UI["card"], fg=UI["text"], relief="flat",
                 command=browse_gcloud).pack(side="left")
        
        # Global Voices Directory
        voices_dir_frame = tk.LabelFrame(wrap, text="Global Voices Directory (Local Models)", fg=UI["text"], 
                                         bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        voices_dir_frame.pack(fill="x", pady=8)
        
        tk.Label(voices_dir_frame, text="Voice Models Directory:", fg=UI["text"], 
                bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        tk.Label(voices_dir_frame, text="(Stations can reference voices relative to this path)", 
                fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        
        voices_dir_row = tk.Frame(voices_dir_frame, bg=UI["panel"])
        voices_dir_row.pack(fill="x", pady=(2, 4))
        
        voices_dir_var = tk.StringVar(value=voices.get("voices_directory", ""))
        tk.Entry(voices_dir_row, textvariable=voices_dir_var, bg=UI["card"], fg=UI["text"], 
                insertbackground=UI["text"]).pack(side="left", fill="x", expand=True, padx=(0, 8))
        
        def browse_voices_dir():
            path = filedialog.askdirectory(parent=parent.winfo_toplevel(),
                                          title="Select Voices Directory")
            if path:
                voices_dir_var.set(path)
        
        tk.Button(voices_dir_row, text="Browse", bg=UI["card"], fg=UI["text"], relief="flat",
                 command=browse_voices_dir).pack(side="left")
        
        # Default Voice Presets (for Piper local models or API voice IDs)
        presets_frame = tk.LabelFrame(wrap, text="Default Character Voices", fg=UI["text"], 
                                      bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        presets_frame.pack(fill="x", pady=8)
        
        tk.Label(presets_frame, text="For Piper: .onnx file paths | For APIs: voice IDs (e.g., 'EXAVITQu4vr4xnSDxMaL')", 
                fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w", pady=(0, 8))
        
        voice_chars = ["host", "expert", "skeptic", "optimist", "coach"]
        voice_vars = {}
        
        for char in voice_chars:
            char_row = tk.Frame(presets_frame, bg=UI["panel"])
            char_row.pack(fill="x", pady=2)
            
            tk.Label(char_row, text=f"{char.title()}:", fg=UI["text"], bg=UI["panel"], 
                    font=FONT_SMALL, width=10, anchor="w").pack(side="left")
            
            var = tk.StringVar(value=voices.get(f"voice_{char}", ""))
            voice_vars[char] = var
            
            tk.Entry(char_row, textvariable=var, bg=UI["card"], fg=UI["text"], 
                    insertbackground=UI["text"]).pack(side="left", fill="x", expand=True, padx=(0, 4))
            
            tk.Button(char_row, text="...", bg=UI["card"], fg=UI["text"], relief="flat", width=3,
                     command=lambda v=var: self._browse_voice_file(v, parent)).pack(side="left")
        
        # Save button
        def save_voices():
            cfg = get_global_config()
            voice_cfg = {
                "provider": provider_var.get(),
                "piper_bin": piper_var.get(),
                "api_key": api_key_var.get(),
                "google_credentials": gcloud_var.get(),
                "voices_directory": voices_dir_var.get(),
            }
            for char, var in voice_vars.items():
                voice_cfg[f"voice_{char}"] = var.get()
            
            cfg["default_voices"] = voice_cfg
            save_global_config(cfg)
            messagebox.showinfo("Success", "Voice settings saved!")
        
        tk.Button(wrap, text="Save Settings", font=FONT_BODY, bg=UI["accent"], 
                 fg="#000", relief="flat", command=save_voices).pack(anchor="w", pady=16)

    def _browse_voice_file(self, var: tk.StringVar, parent: tk.Widget) -> None:
        """Browse for a voice file (.onnx)."""
        path = filedialog.askopenfilename(
            parent=parent.winfo_toplevel(),
            title="Select Voice Model",
            filetypes=[("ONNX Models", "*.onnx"), ("All Files", "*.*")]
        )
        if path:
            var.set(path)

    def _build_storage_tools(self, parent: tk.Frame) -> None:
        """Build the Storage tools panel."""
        
        # Make scrollable
        scrollbar = tk.Scrollbar(parent, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        
        canvas = tk.Canvas(parent, bg=UI["bg"], highlightthickness=0, yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        
        scrollbar.configure(command=canvas.yview)
        
        scroll_frame = tk.Frame(canvas, bg=UI["bg"])
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        
        tk.Label(scroll_frame, text="Storage & Maintenance", font=FONT_H2, fg=UI["text"], bg=UI["bg"]).pack(
            anchor="w", padx=14, pady=(14, 8)
        )
        
        wrap = tk.Frame(scroll_frame, bg=UI["bg"])
        wrap.pack(fill="both", expand=True, padx=14, pady=8)
        
        # Log Management
        log_frame = tk.LabelFrame(wrap, text="Log Management", fg=UI["text"], 
                                  bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        log_frame.pack(fill="x", pady=8)
        
        tk.Label(log_frame, text="Clean up old runtime logs to free disk space", 
                fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w", pady=(0, 8))
        
        def clear_all_logs():
            if not messagebox.askyesno("Clear Logs", 
                                      "Delete all runtime.log files from all stations?\n\nThis cannot be undone."):
                return
            
            count = 0
            for station in self.stations:
                log_path = os.path.join(station.path, "runtime.log")
                if os.path.exists(log_path):
                    try:
                        os.remove(log_path)
                        count += 1
                    except Exception as e:
                        print(f"Failed to delete {log_path}: {e}")
            
            messagebox.showinfo("Logs Cleared", f"Deleted {count} log file(s)")
        
        tk.Button(log_frame, text="Clear All Station Logs", bg=UI["card"], fg=UI["text"], 
                 relief="flat", command=clear_all_logs, font=FONT_BODY).pack(anchor="w", pady=4)
        
        # Database Management
        db_frame = tk.LabelFrame(wrap, text="Database Management", fg=UI["text"], 
                                 bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        db_frame.pack(fill="x", pady=8)
        
        tk.Label(db_frame, text="Manage station databases and queue state", 
                fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w", pady=(0, 8))
        
        def vacuum_databases():
            if not messagebox.askyesno("Vacuum Databases", 
                                      "Optimize all station databases?\n\nThis may take a moment."):
                return
            
            import sqlite3
            count = 0
            for station in self.stations:
                db_path = os.path.join(station.path, "station.sqlite")
                if os.path.exists(db_path):
                    try:
                        conn = sqlite3.connect(db_path)
                        conn.execute("VACUUM")
                        conn.close()
                        count += 1
                    except Exception as e:
                        print(f"Failed to vacuum {db_path}: {e}")
            
            messagebox.showinfo("Databases Optimized", f"Vacuumed {count} database(s)")
        
        tk.Button(db_frame, text="Vacuum All Databases", bg=UI["card"], fg=UI["text"], 
                 relief="flat", command=vacuum_databases, font=FONT_BODY).pack(anchor="w", pady=4)
        
        # Export/Backup
        export_frame = tk.LabelFrame(wrap, text="Backup & Export", fg=UI["text"], 
                                     bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        export_frame.pack(fill="x", pady=8)
        
        tk.Label(export_frame, text="Export station configurations for backup or sharing", 
                fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w", pady=(0, 8))
        
        def export_station():
            if not self.stations:
                messagebox.showwarning("No Stations", "No stations to export")
                return
            
            # Let user pick which station
            station_names = [s.station_id for s in self.stations]
            # Simple: just use the selected one
            if self.selected_idx >= 0 and self.selected_idx < len(self.stations):
                station = self.stations[self.selected_idx]
                
                dest = filedialog.asksaveasfilename(
                    parent=parent.winfo_toplevel(),
                    title=f"Export {station.station_id}",
                    defaultextension=".yaml",
                    initialfile=f"{station.station_id}_manifest.yaml",
                    filetypes=[("YAML Files", "*.yaml"), ("All Files", "*.*")]
                )
                
                if dest:
                    import shutil
                    src = os.path.join(station.path, "manifest.yaml")
                    try:
                        shutil.copy2(src, dest)
                        messagebox.showinfo("Success", f"Exported manifest to:\n{dest}")
                    except Exception as e:
                        messagebox.showerror("Export Failed", str(e))
        
        tk.Button(export_frame, text="Export Selected Station Manifest", bg=UI["card"], 
                 fg=UI["text"], relief="flat", command=export_station, font=FONT_BODY).pack(anchor="w", pady=4)
        
        # Global config path info
        info_frame = tk.LabelFrame(wrap, text="Configuration Location", fg=UI["text"], 
                                   bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        info_frame.pack(fill="x", pady=8)
        
        config_path = get_global_config_path()
        tk.Label(info_frame, text=f"Global config: {config_path}", 
                fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL, wraplength=800).pack(anchor="w")
        
        def open_config_dir():
            import subprocess
            import platform
            config_dir = os.path.dirname(config_path)
            
            if platform.system() == "Windows":
                os.startfile(config_dir)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", config_dir])
            else:
                subprocess.Popen(["xdg-open", config_dir])
        
        tk.Button(info_frame, text="Open Config Directory", bg=UI["card"], fg=UI["text"], 
                 relief="flat", command=open_config_dir, font=FONT_BODY).pack(anchor="w", pady=(8, 0))

    def _build_visual_models_panel(self, parent: tk.Frame) -> None:
        """Build the Visual Models settings panel."""
        # Title
        tk.Label(parent, text="Vision Model Configuration", font=FONT_H2, fg=UI["text"], bg=UI["bg"]).pack(
            anchor="w", padx=14, pady=(14, 8)
        )
        
        # Scrollable container
        scrollbar = ttk.Scrollbar(parent, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        
        canvas = tk.Canvas(parent, bg=UI["bg"], highlightthickness=0, yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=14, pady=8)
        
        scrollbar.configure(command=canvas.yview)
        
        scroll_frame = tk.Frame(canvas, bg=UI["bg"])
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        
        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        
        # Load current config
        cfg = get_global_config()
        visual_cfg = cfg.get("visual_models", {})
        
        # Model Type Selection (Local or API)
        model_type_var = tk.StringVar(value=visual_cfg.get("model_type", "local"))
        
        type_frame = tk.LabelFrame(scroll_frame, text="Model Type", fg=UI["text"], bg=UI["panel"], 
                                    font=FONT_BODY, padx=12, pady=8)
        type_frame.pack(fill="x", pady=8)
        
        tk.Radiobutton(type_frame, text="Local Model (e.g., Ollama/LLaVA)", variable=model_type_var, 
                       value="local", fg=UI["text"], bg=UI["panel"], selectcolor=UI["accent"]).pack(anchor="w")
        tk.Radiobutton(type_frame, text="API-based Model", variable=model_type_var, 
                       value="api", fg=UI["text"], bg=UI["panel"], selectcolor=UI["accent"]).pack(anchor="w")
        
        # Local Model Config
        local_frame = tk.LabelFrame(scroll_frame, text="Local Model Settings", fg=UI["text"], 
                                     bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        local_frame.pack(fill="x", pady=8)
        
        tk.Label(local_frame, text="Model Name / Endpoint:", fg=UI["text"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        local_model_var = tk.StringVar(value=visual_cfg.get("local_model", ""))
        local_model_entry = tk.Entry(local_frame, textvariable=local_model_var, bg=UI["card"], fg=UI["text"], 
                                      insertbackground=UI["text"])
        local_model_entry.pack(fill="x", pady=(2, 8))
        tk.Label(local_frame, text="(e.g., llava:latest, or http://localhost:11434)", 
                 fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        
        # API Model Config
        api_frame = tk.LabelFrame(scroll_frame, text="API Model Settings", fg=UI["text"], 
                                   bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        api_frame.pack(fill="x", pady=8)
        
        tk.Label(api_frame, text="API Provider:", fg=UI["text"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        api_provider_var = tk.StringVar(value=visual_cfg.get("api_provider", "openai"))
        provider_options = ["openai", "anthropic", "google", "custom"]
        provider_menu = ttk.Combobox(api_frame, textvariable=api_provider_var, values=provider_options, 
                                     state="readonly", width=30)
        provider_menu.pack(fill="x", pady=(2, 8))
        
        tk.Label(api_frame, text="Model Name:", fg=UI["text"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        api_model_var = tk.StringVar(value=visual_cfg.get("api_model", "gpt-4-vision"))
        api_model_entry = tk.Entry(api_frame, textvariable=api_model_var, bg=UI["card"], fg=UI["text"], 
                                    insertbackground=UI["text"])
        api_model_entry.pack(fill="x", pady=(2, 8))
        
        tk.Label(api_frame, text="API Key:", fg=UI["text"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        api_key_var = tk.StringVar(value=visual_cfg.get("api_key", ""))
        api_key_entry = tk.Entry(api_frame, textvariable=api_key_var, bg=UI["card"], fg=UI["text"], 
                                  insertbackground=UI["text"], show="•")
        api_key_entry.pack(fill="x", pady=(2, 8))
        
        tk.Label(api_frame, text="API Endpoint (optional):", fg=UI["text"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        api_endpoint_var = tk.StringVar(value=visual_cfg.get("api_endpoint", ""))
        api_endpoint_entry = tk.Entry(api_frame, textvariable=api_endpoint_var, bg=UI["card"], fg=UI["text"], 
                                       insertbackground=UI["text"])
        api_endpoint_entry.pack(fill="x", pady=(2, 8))
        
        # Vision-specific options
        opts_frame = tk.LabelFrame(scroll_frame, text="Vision Processing Options", fg=UI["text"], 
                                    bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        opts_frame.pack(fill="x", pady=8)
        
        tk.Label(opts_frame, text="Max Image Size (width):", fg=UI["text"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        max_size_var = tk.StringVar(value=visual_cfg.get("max_image_size", "1024"))
        max_size_entry = tk.Entry(opts_frame, textvariable=max_size_var, bg=UI["card"], fg=UI["text"], 
                                   insertbackground=UI["text"], width=10)
        max_size_entry.pack(anchor="w", pady=(2, 8))
        
        tk.Label(opts_frame, text="Image Quality (1-100):", fg=UI["text"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        quality_var = tk.StringVar(value=visual_cfg.get("image_quality", "85"))
        quality_entry = tk.Entry(opts_frame, textvariable=quality_var, bg=UI["card"], fg=UI["text"], 
                                  insertbackground=UI["text"], width=10)
        quality_entry.pack(anchor="w", pady=(2, 8))
        
        # Save button
        def save_visual_config():
            cfg = get_global_config()
            cfg["visual_models"] = {
                "model_type": model_type_var.get(),
                "local_model": local_model_var.get(),
                "api_provider": api_provider_var.get(),
                "api_model": api_model_var.get(),
                "api_key": api_key_var.get(),
                "api_endpoint": api_endpoint_var.get(),
                "max_image_size": max_size_var.get(),
                "image_quality": quality_var.get(),
            }
            save_global_config(cfg)
            messagebox.showinfo("Success", "Visual model settings saved!")

        quick_frame = tk.Frame(scroll_frame, bg=UI["bg"])
        quick_frame.pack(fill="x", pady=(0, 8), before=type_frame)
        tk.Button(
            quick_frame,
            text="Save Settings",
            font=FONT_BODY,
            bg=UI["accent"],
            fg="#000",
            relief="flat",
            command=save_visual_config,
        ).pack(side="right")
        
        btn_frame = tk.Frame(scroll_frame, bg=UI["bg"])
        btn_frame.pack(fill="x", pady=(16, 0))
        
        tk.Button(btn_frame, text="Save Settings", font=FONT_BODY, bg=UI["accent"], 
                  fg="#000", relief="flat", command=save_visual_config).pack(side="left", padx=4)

    # -----------------------------
    # Station editor / builder
    # -----------------------------
    def create_station_wizard(self):
        wiz = StationWizard(self)
        result = wiz.run_and_get_result()
        if not result:
            return

        manifest = result.get("manifest")
        if not manifest:
            return

        # Derive station_id from manifest
        station_block = manifest.get("station", {})
        station_id = station_block.get("id")

        if not station_id:
            name = station_block.get("name", "")
            station_id = name.lower().replace(" ", "_")

        if not station_id:
            messagebox.showerror("Error", "Station has no id or name.")
            return

        self.refresh_stations(select_id=station_id)
        self.edit_station(self._find_station(station_id))

    def edit_station(self, station: Optional[StationInfo]):
        if not station:
            return
        
        # Use the wizard but pre-populate with existing station data
        wiz = StationWizard(self, edit_mode=True, station=station)
        result = wiz.run_and_get_result()
        
        if result:
            # Manifest already saved by wizard, just refresh
            self.refresh_stations(select_id=station.station_id)

    def _find_station(self, station_id: str) -> Optional[StationInfo]:
        for s in self.stations:
            if s.station_id == station_id:
                return s
        return None

    def refresh_stations(self, select_id: Optional[str] = None):
        self.stations = load_stations()
        if select_id:
            for i, s in enumerate(self.stations):
                if s.station_id == select_id:
                    self.selected_idx = i
                    break
        self._render_cards()
        self.root.after(60, lambda: self._snap_to_index(self.selected_idx, animate=False))

    def _prompt_text(self, title: str, prompt: str) -> Optional[str]:
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry(scaled_geometry(520, 200))
        win.configure(bg=UI["bg"])

        tk.Label(win, text=prompt, font=FONT_BODY, fg=UI["text"], bg=UI["bg"], wraplength=480, justify="left").pack(
            padx=16, pady=(16, 8), anchor="w"
        )
        entry = tk.Entry(win, font=FONT_BODY, bg=UI["panel"], fg=UI["text"], insertbackground=UI["text"])
        entry.pack(fill="x", padx=16, pady=(0, 12))
        entry.focus_set()

        out = {"val": None}

        def ok():
            out["val"] = entry.get()
            win.destroy()

        def cancel():
            win.destroy()

        btns = tk.Frame(win, bg=UI["bg"])
        btns.pack(fill="x", padx=16, pady=10)
        tk.Button(btns, text="Cancel", font=FONT_BODY, bg=UI["panel"], fg=UI["text"], relief="flat", command=cancel).pack(
            side="right", padx=6
        )
        tk.Button(btns, text="OK", font=FONT_BODY, bg=UI["accent"], fg="#000", relief="flat", command=ok).pack(
            side="right", padx=6
        )

        win.bind("<Return>", lambda e: ok())
        win.bind("<Escape>", lambda e: cancel())

        self.root.wait_window(win)
        return out["val"]

    # -----------------------------
    # Live runtime status polling
    # -----------------------------
    def _tick(self):
        self._check_station_switch()
        self._update_status_panel()
        self.root.after(self._status_poll_ms, self._tick)

    def _check_station_switch(self):
        # Check if process exited with magic code 20
        if not self.proc or not self.proc.proc:
            return

        ret = self.proc.proc.poll()
        if ret == 20: 
            # It's a switch request
            try:
                rq_path = os.path.join(BASE, ".switch_request")
                if os.path.exists(rq_path):
                    with open(rq_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    # Consume file
                    try:
                        os.remove(rq_path)
                    except:
                        pass
                        
                    target_id = data.get("station_id")
                    if target_id:
                        print(f"[Shell] Switching to station: {target_id}")
                        self.proc.stop() # Ensure closed
                        
                        # Find station info
                        st = self._find_station(target_id)
                        if st:
                            self.launch_station(st)
                        else:
                            print(f"[Shell] Station {target_id} not found.")
            except Exception as e:
                print(f"[Shell] Switch failed: {e}")

    def _update_status_panel(self):
        if self._view != "runtime":
            return

        st = self.proc.station
        alive = self.proc.is_alive()
        lines: List[str] = []

        if self.proc.proc is not None:
            try:
                lines.append(f"returncode: {self.proc.proc.poll()}")
            except Exception:
                pass

        if st:
            lp = os.path.join(st.path, "runtime.log")
            if os.path.exists(lp):
                try:
                    with open(lp, "r", encoding="utf-8", errors="ignore") as f:
                        tail = f.read()[-4000:]
                    if tail.strip():
                        lines.append("")
                        lines.append("---- runtime.log tail ----")
                        lines.extend(tail.strip().splitlines()[-25:])
                except Exception:
                    pass

        lines.append(f"proc_alive: {alive}")

        if not st:
            lines.append("station: (none)")
            self._set_status_text("\n".join(lines))
            return

        name = (st.manifest.get("station", {}) or {}).get("name", st.station_id)
        lines.append(f"station: {name} ({st.station_id})")

        sp = station_status_path(st.path)
        status = None
        if os.path.exists(sp):
            try:
                with open(sp, "r", encoding="utf-8") as f:
                    status = json.load(f)
            except Exception:
                status = None

        if status:
            hb = int(status.get("ts", 0) or 0)
            age = now_ts() - hb if hb else -1
            lines.append(f"heartbeat_age_sec: {age}")
            for k in ["db_queued", "db_claimed", "audio_q", "last_event", "last_title", "last_source"]:
                if k in status:
                    lines.append(f"{k}: {status.get(k)}")
        else:
            lines.append("status.json: (missing)")

        dbp = station_db_path(st.path)
        if os.path.exists(dbp):
            try:
                lines.append(f"db_size_mb: {os.path.getsize(dbp)/1024/1024:.2f}")
            except Exception:
                pass

        self._set_status_text("\n".join(lines))
        self.now_sub.config(text="Live" if alive else "Not running")

    def _set_status_text(self, text: str):
        self.status_lines.config(state="normal")
        self.status_lines.delete("1.0", "end")
        self.status_lines.insert("1.0", text)
        self.status_lines.config(state="disabled")

    def _on_close(self):
        try:
            self.proc.stop()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()
CHARACTER_PRESETS = {

    "Universal FM": {
        "host": {
            "role": "moderator",
            "traits": ["calm", "smart"],
            "focus": ["flow", "continuity"]
        },
        "expert": {
            "role": "technical_voice",
            "traits": ["precise", "knowledgeable"],
            "focus": ["details", "accuracy"]
        },
        "skeptic": {
            "role": "critical_voice",
            "traits": ["cautious", "blunt"],
            "focus": ["risk", "downsides"]
        },
        "optimist": {
            "role": "positive_voice",
            "traits": ["energetic", "hopeful"],
            "focus": ["opportunity", "strengths"]
        },
        "storyteller": {
            "role": "narrative_voice",
            "traits": ["creative", "engaging"],
            "focus": ["examples", "analogies"]
        },
    },

    "Hockey FM": {
        "host": {
            "role": "play_by_play_host",
            "traits": ["smooth", "engaging"],
            "focus": ["flow", "pacing"]
        },
        "analyst": {
            "role": "tactical_breakdown",
            "traits": ["smart", "precise"],
            "focus": ["systems", "matchups"]
        },
        "stats_guru": {
            "role": "analytics_voice",
            "traits": ["data_driven", "calm"],
            "focus": ["metrics", "trends"]
        },
        "hype": {
            "role": "energy_driver",
            "traits": ["excited", "passionate"],
            "focus": ["big_plays", "emotion"]
        },
        "coach": {
            "role": "leadership_voice",
            "traits": ["motivational", "firm"],
            "focus": ["habits", "discipline"]
        }
    }
}
# ============================================================
# Onboarding Wizard (Gold Standard Manifest Generator)
# ============================================================

PRESET_ROLES = [
    "host", "engineer", "skeptic", "macro", "optimist", "coach",
    "analyst", "stats_guru", "hype", "moderator", "narrator",
    "risk_manager", "execution_specialist", "news_anchor"
]

PRESET_TRAITS = [
    "calm", "smart", "technical", "precise", "critical", "grounded",
    "contextual", "broad", "energetic", "constructive", "motivational",
    "long_term", "blunt", "curious", "skeptical", "disciplined",
    "measured", "creative", "engaging", "data_driven"
]

PRESET_FOCUS = [
    "flow", "continuity", "systems", "signals", "risk", "failure_modes",
    "regimes", "liquidity", "opportunity", "growth", "discipline", "milestones",
    "positioning", "execution", "orderflow", "volatility", "macro", "narrative",
    "pacing", "big_plays", "metrics", "trends", "strategy", "news"
]

# Known feed templates matching your gold manifest keys.
# If a plugin exists but isn't listed here, we still allow it (enabled + empty config),
# but these templates give a friendly default schema in the wizard.
FEED_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "reddit": {
        "enabled": True,
        "subreddits": [],
        "poll_sec": 30,
        "limit": 20,
        "priority": 60,
        "burst_delay": 0.2,
        "seen_ttl_sec": 3600,
    },
    "markets": {
        "enabled": True,
        "symbols": [],
        "poll_sec": 15,
        "breakout_pct": 0.2,
        "priority": 90,
    },
    "portfolio_event": {
        "enabled": True,
        "mode": "hyperliquid",
        "user_address": "",
        "poll_sec": 6,
        "min_emit_gap_sec": 20,
        "min_equity_delta_frac": 0.003,
        "big_equity_delta_frac": 0.015,
        "positions_change_priority": 95,
        "equity_change_priority": 93,
        "big_move_priority": 98,
        "base_url": "https://api.hyperliquid.xyz",
    },
    "rss": {
        "enabled": True,
        "urls": [],
        "poll_sec": 180,
        "priority": 72,
    },
    "bluesky": {
        "enabled": True,
        "hashtags": [],
        "poll_sec": 60,
        "limit": 20,
        "priority": 70,
    },
    "document": {
        "enabled": True,
        "files": [
            {
                "name": "strategy",
                "path": "./strategy_reference.txt",
                "max_chars": 5000,
                "announce": True,
                "announce_priority": 86,
                "candidate": False,
            },
            {
                "name": "playbook",
                "path": "./coach_playbook.txt",
                "max_chars": 7000,
                "announce": False,
                "candidate": True,
                "candidate_priority": 80,
            },
        ],
        "poll_sec": 2.5,
        "announce_cooldown_sec": 600,
    },
}

def _build_default_quotas() -> Dict[str, int]:
    # Baseline defaults
    base = {
        "reddit": 6,
        "markets": 4,
        "portfolio_event": 6,
        "bluesky": 2,
        "document": 4,
        "rss": 1,
    }
    # Dynamically correct based on installed plugins
    try:
        for name, info in discover_plugins().items():
            if info.get("is_feed", True):
                if name not in base:
                    base[name] = 3
    except Exception:
        pass
    return base

DEFAULT_SCHED_QUOTAS = _build_default_quotas()

def _build_default_weights() -> Dict[str, float]:
    # Baseline defaults
    base = {
        "reddit": 0.50,
        "bluesky": 0.25,
        "markets": 0.10,
        "portfolio_event": 0.10,
        "rss": 0.03,
        "document": 0.02,
    }
    # Dynamically correct based on installed plugins
    try:
        for name, info in discover_plugins().items():
            if info.get("is_feed", True):
                if name not in base:
                    base[name] = 0.05
    except Exception:
        pass
    return base

DEFAULT_MIX_WEIGHTS = _build_default_weights()

DEFAULT_CHARSET = {
    "host":   {"role": "host",   "traits": ["calm", "smart"],              "focus": ["flow", "continuity"]},
    "engineer": {"role": "engineer", "traits": ["technical", "precise"],     "focus": ["systems", "signals"]},
    "skeptic":  {"role": "skeptic",  "traits": ["critical", "grounded"],     "focus": ["risk", "failure_modes"]},
    "macro":    {"role": "macro",    "traits": ["contextual", "broad"],      "focus": ["regimes", "liquidity"]},
    "optimist": {"role": "optimist", "traits": ["energetic", "constructive"],"focus": ["opportunity", "growth"]},
    "coach":    {"role": "coach",    "traits": ["motivational", "long_term"],"focus": ["discipline", "milestones"]},
}


def _deepcopy_jsonable(x: Any) -> Any:
    return json.loads(json.dumps(x))

def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    # Remove negatives, normalize to sum=1.0, keep stable keys.
    w2 = {k: max(0.0, float(v)) for k, v in (weights or {}).items()}
    s = sum(w2.values())
    if s <= 0:
        # fallback equal
        keys = list(w2.keys()) or []
        if not keys:
            return {}
        eq = 1.0 / len(keys)
        return {k: eq for k in keys}
    return {k: (v / s) for k, v in w2.items()}

def _pie_segments(weights: Dict[str, float]) -> List[tuple]:
    # Returns list of (key, start_angle, extent_angle)
    w = _normalize_weights(weights)
    out = []
    a = 0.0
    for k, frac in w.items():
        ext = 360.0 * frac
        out.append((k, a, ext))
        a += ext
    return out

def _try_play_wav(path: str) -> None:
    # Best-effort audio playback for voice sampling.
    try:
        if os.name == "nt":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            return
    except Exception:
        pass

    # Optional fallback if installed
    try:
        import soundfile as sf
        import sounddevice as sd
        data, sr = sf.read(path, dtype="float32")
        sd.play(data, sr)
        return
    except Exception:
        pass

    # Last resort: open file (user can play it)
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


class StationWizard:
    """
    Friendly wizard that produces the gold-standard manifest.yaml.
    Can create new stations or edit existing ones.
    """
    def __init__(self, shell: "RadioShell", edit_mode: bool = False, station: Optional["StationInfo"] = None):
        self.shell = shell
        self.root = shell.root
        self.edit_mode = edit_mode
        self.station = station

        self.plugins = discover_plugins()  # available plugin modules

        # Result payload
        self._result: Optional[Dict[str, Any]] = None

        # Load global config for defaults
        global_cfg = get_global_config()
        default_models = global_cfg.get("default_models", {})
        default_voices = global_cfg.get("default_voices", {})

        # State - defaults for new station (use global config or fallback)
        self.station_id = ""
        self.station_name = "My Radio Station"
        self.station_host = "Host"
        self.station_category = "Custom"
        self.station_logo = ""

        self.llm_endpoint = default_models.get("llm_endpoint", "http://127.0.0.1:11434/api/generate")
        self.model_producer = default_models.get("producer_model", "rnj-1:8b")
        self.model_host = default_models.get("host_model", "rnj-1:8b")

        self.piper_bin = default_voices.get("piper_bin", "")
        # voices assigned per character (dynamic) - use global defaults
        self.voices: Dict[str, str] = {
            "host": default_voices.get("voice_host", ""),
            "expert": default_voices.get("voice_expert", ""),
            "skeptic": default_voices.get("voice_skeptic", ""),
            "optimist": default_voices.get("voice_optimist", ""),
            "coach": default_voices.get("voice_coach", ""),
        }

        # Feeds chosen/configured
        self.feed_cfg: Dict[str, Dict[str, Any]] = {}
        # Characters chosen/configured (2-10, must include host)
        self.characters = {
            "host": {
                "role": "moderator",
                "traits": ["calm", "smart"],
                "focus": ["flow", "continuity"]
            }
        }

        # Mix weights (ready for runtime later)
        self.mix_weights: Dict[str, float] = _deepcopy_jsonable(DEFAULT_MIX_WEIGHTS)

        # Scheduler quotas
        self.scheduler_quotas: Dict[str, int] = _deepcopy_jsonable(DEFAULT_SCHED_QUOTAS)

        # Preserve original manifest to avoid data loss on save
        self.existing_manifest: Optional[Dict[str, Any]] = None

        # If editing, load existing station data
        if edit_mode and station:
            self._load_existing_station(station)

        # Wizard window
        self.win = tk.Toplevel(self.root)
        self.win.title("Edit Station" if edit_mode else "New Station Wizard")
        self.win.geometry(scaled_geometry(1100, 760))
        self.win.configure(bg=UI["bg"])
        self.win.grab_set()

        self._build()

    # -------------
    # Public API
    # -------------
    def run_and_get_result(self) -> Optional[Dict[str, Any]]:
        self.root.wait_window(self.win)
        return self._result
    
    def _load_existing_station(self, station: "StationInfo"):
        """Load existing station manifest data into wizard state."""
        manifest_path = station_manifest_path(station.path)
        cfg = safe_read_yaml(manifest_path)
        
        if not cfg:
            return

        # Keep a copy of the full manifest to preserve extra fields (pacing, riff, etc)
        self.existing_manifest = _deepcopy_jsonable(cfg)
        
        # Load station basics
        st_block = cfg.get("station", {})
        self.station_id = station.station_id
        self.station_name = st_block.get("name", station.station_id)
        self.station_host = st_block.get("host", "Kai")
        self.station_category = st_block.get("category", "Custom")
        self.station_logo = st_block.get("logo", "")
        
        # Load models
        llm_block = cfg.get("llm", {})
        self.llm_endpoint = llm_block.get("endpoint", "http://127.0.0.1:11434/api/generate")
        
        models_block = cfg.get("models", {})
        self.model_producer = models_block.get("producer", "rnj-1:8b")
        self.model_host = models_block.get("host", "rnj-1:8b")
        
        # Load audio
        audio_block = cfg.get("audio", {})
        self.piper_bin = audio_block.get("piper_bin", "")
        
        # Load voices
        voices_block = cfg.get("voices", {})
        if isinstance(voices_block, dict):
            self.voices = dict(voices_block)
        
        # Load feeds
        feeds_block = cfg.get("feeds", {})
        if isinstance(feeds_block, dict):
            self.feed_cfg = _deepcopy_jsonable(feeds_block)
        
        # Load characters
        chars_block = cfg.get("characters", {})
        if isinstance(chars_block, dict) and chars_block:
            self.characters = _deepcopy_jsonable(chars_block)
        
        # Load mix weights
        mix_block = cfg.get("mix", {})
        if isinstance(mix_block, dict):
            weights = mix_block.get("weights", {})
            if isinstance(weights, dict):
                self.mix_weights = dict(weights)
        
        # Load scheduler quotas
        sched_block = cfg.get("scheduler", {})
        if isinstance(sched_block, dict):
            quotas = sched_block.get("source_quotas", {})
            if isinstance(quotas, dict):
                self.scheduler_quotas = dict(quotas)
    
    def _refresh_voices_tab(self):
        # Capture any current UI edits before we destroy the widgets
        try:
            if hasattr(self, "var_piper_bin"):
                self.piper_bin = (self.var_piper_bin.get() or "").strip()

            if hasattr(self, "voice_vars") and isinstance(self.voice_vars, dict):
                for k, var in self.voice_vars.items():
                    try:
                        self.voices[k] = (var.get() or "").strip()
                    except Exception:
                        pass
        except Exception:
            pass

        for w in self.tab_voices.winfo_children():
            w.destroy()

        self._build_voices()
    def _discover_feed_names(self) -> List[str]:
        # Prefer live plugin discovery; fall back to FEED_TEMPLATES keys.
        names = sorted(k for k, meta in (self.plugins or {}).items() if meta.get("is_feed", True))
        if names:
            return names
        return sorted(FEED_TEMPLATES.keys())

    def _make_scrollable_frame(self, parent: tk.Widget, bg: str):
        """
        Returns: (outer_frame, inner_frame, canvas)
        - outer_frame contains canvas + scrollbar
        - inner_frame is where you pack your rows
        - mousewheel is bound only when cursor is over the canvas
        """
        outer = tk.Frame(parent, bg=bg)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=bg, highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)

        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        vsb.pack(side="right", fill="y")

        canvas.configure(yscrollcommand=vsb.set)

        inner = tk.Frame(canvas, bg=bg)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_configure(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(e):
            # keep inner width matched to visible canvas width
            canvas.itemconfigure(win_id, width=e.width)

        inner.bind("<Configure>", _on_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Wheel scrolling (Windows/macOS)
        def _wheel(e):
            # delta is platform dependent; normalize a bit
            delta = 0
            try:
                if sys.platform == "darwin":
                    # macOS: delta usually matches scroll units directly
                    delta = int(-1 * e.delta)
                else:
                    # Windows: 120 increments
                    delta = int(-1 * (e.delta / 120))
            except Exception:
                delta = 0
            if delta != 0:
                canvas.yview_scroll(delta, "units")

        # Linux wheel
        def _wheel_up(_e):
            canvas.yview_scroll(-1, "units")

        def _wheel_down(_e):
            canvas.yview_scroll(1, "units")

        def _bind_wheel(_e=None):
            canvas.bind_all("<MouseWheel>", _wheel)
            canvas.bind_all("<Button-4>", _wheel_up)
            canvas.bind_all("<Button-5>", _wheel_down)

        def _unbind_wheel(_e=None):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)

        return outer, inner, canvas
    def _render_mix_ui(self):

        # Clear old UI
        for w in self.mix_wrap.winfo_children():
            w.destroy()

        tk.Label(
            self.mix_wrap,
            text="Feed mix (future-ready)",
            font=FONT_H2,
            fg=UI["text"],
            bg=UI["bg"]
        ).pack(anchor="w")

        tk.Label(
            self.mix_wrap,
            text="Adjust how often each enabled feed appears.",
            font=FONT_BODY,
            fg=UI["muted"],
            bg=UI["bg"]
        ).pack(anchor="w", pady=(4, 10))

        body = tk.Frame(self.mix_wrap, bg=UI["bg"])
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=UI["panel"], width=int(360 * UI_SCALE))
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        right = tk.Frame(body, bg=UI["bg"])
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))

        # 🔥 LIVE enabled feeds
        enabled = [
            k for k, v in self.feed_cfg.items()
            if isinstance(v, dict) and v.get("enabled", False)
        ]

        if not enabled:
            enabled = list(DEFAULT_MIX_WEIGHTS.keys())

        self.weight_sliders = {}

        tk.Label(
            left,
            text="Weights",
            font=("Segoe UI", 12, "bold"),
            fg=UI["text"],
            bg=UI["panel"]
        ).pack(anchor="w", padx=12, pady=(12, 8))

        for k in enabled:
            if k not in self.mix_weights:
                self.mix_weights[k] = 0.0

            row = tk.Frame(left, bg=UI["panel"])
            row.pack(fill="x", padx=12, pady=6)

            tk.Label(row, text=k, fg=UI["muted"], bg=UI["panel"], width=14, anchor="w").pack(side="left")

            v = tk.DoubleVar(value=float(self.mix_weights.get(k, 0.0)))
            self.weight_sliders[k] = v

            tk.Scale(
                row,
                from_=0.0, to=1.0, resolution=0.01,
                orient="horizontal",
                variable=v,
                length=200,
                bg=UI["panel"], fg=UI["text"],
                highlightthickness=0,
                command=lambda _=None: self._mix_redraw()
            ).pack(side="left", fill="x", expand=True)

        tk.Button(
            left,
            text="Normalize (sum=1)",
            bg=UI["panel"],
            fg=UI["accent"],
            relief="flat",
            command=self._mix_normalize_clicked
        ).pack(anchor="w", padx=12, pady=(8, 12))

        tk.Label(
            right,
            text="Preview pie",
            font=("Segoe UI", 12, "bold"),
            fg=UI["text"],
            bg=UI["bg"]
        ).pack(anchor="w")

        self.pie = tk.Canvas(
            right,
            bg=UI["surface"],
            highlightthickness=0,
            width=int(520 * UI_SCALE),
            height=int(520 * UI_SCALE)
        )
        self.pie.pack(pady=12)
        
        # Draw initial pie chart
        self._mix_redraw()

    # -------------
    # UI Build
    # -------------
    def _build(self):
        top = tk.Frame(self.win, bg=UI["bg"])
        top.pack(fill="x", padx=16, pady=(14, 8))

        tk.Label(top, text="Create a new station", font=FONT_H1, fg=UI["text"], bg=UI["bg"]).pack(anchor="w")
        tk.Label(
            top,
            text="We’ll configure: station → feeds → characters → voices → mix → done.",
            font=FONT_BODY, fg=UI["muted"], bg=UI["bg"]
        ).pack(anchor="w", pady=(4, 0))

        self.nb = ttk.Notebook(self.win)
        self.nb.pack(fill="both", expand=True, padx=12, pady=12)

        self.tab_basics = tk.Frame(self.nb, bg=UI["bg"])
        self.tab_feeds = tk.Frame(self.nb, bg=UI["bg"])
        self.tab_chars = tk.Frame(self.nb, bg=UI["bg"])
        self.tab_voices = tk.Frame(self.nb, bg=UI["bg"])
        self.tab_visual = tk.Frame(self.nb, bg=UI["bg"])
        self.tab_mix = tk.Frame(self.nb, bg=UI["bg"])
        self.tab_review = tk.Frame(self.nb, bg=UI["bg"])

        self.nb.add(self.tab_basics, text="1) Station")
        self.nb.add(self.tab_feeds, text="2) Feeds")
        self.nb.add(self.tab_chars, text="3) Characters")
        self.nb.add(self.tab_voices, text="4) Voices")
        self.nb.add(self.tab_visual, text="5) Visual Models")
        self.nb.add(self.tab_mix, text="6) Mix")
        self.nb.add(self.tab_review, text="7) Review")

        self._build_basics()
        self._build_feeds()
        self._build_characters()
        self._build_voices()
        self._build_visual_models()
        self._build_mix()
        self._build_review()

        # Footer nav
        footer = tk.Frame(self.win, bg=UI["bg"])
        footer.pack(fill="x", padx=12, pady=(0, 12))

        self.btn_back = tk.Button(
            footer, text="← Back", font=FONT_BODY,
            bg=UI["panel"], fg=UI["text"], relief="flat",
            command=self._go_back
        )
        self.btn_back.pack(side="left")

        self.btn_next = tk.Button(
            footer, text="Next →", font=FONT_BODY,
            bg=UI["accent"], fg="#000", relief="flat",
            command=self._go_next
        )
        self.btn_next.pack(side="right")

        self.btn_cancel = tk.Button(
            footer, text="Cancel", font=FONT_BODY,
            bg=UI["panel"], fg=UI["muted"], relief="flat",
            command=self._cancel
        )
        self.btn_cancel.pack(side="right", padx=8)

        def on_tab_change(e):
            self._sync_nav_buttons()

            idx = self.nb.index("current")

            # Mix tab index = 4
            if idx == 4:
                self._render_mix_ui()

            # Voices tab refresh you already had
            if idx == 3:
                self._refresh_voices_tab()


        self.nb.bind("<<NotebookTabChanged>>", on_tab_change)

        self._sync_nav_buttons()
    def _build_voices(self):
        wrap = tk.Frame(self.tab_voices, bg=UI["bg"])
        wrap.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(
            wrap,
            text="Voices & TTS",
            font=FONT_H2,
            fg=UI["text"],
            bg=UI["bg"]
        ).grid(row=0, column=0, sticky="w", pady=(0, 12), columnspan=3)

        # Piper binary
        self.var_piper_bin = tk.StringVar(value=self.piper_bin)

        tk.Label(
            wrap, text="Piper binary",
            font=FONT_BODY, fg=UI["muted"], bg=UI["bg"]
        ).grid(row=1, column=0, sticky="w", pady=6)

        tk.Entry(
            wrap,
            textvariable=self.var_piper_bin,
            bg=UI["surface"],
            fg=UI["text"],
            insertbackground=UI["text"]
        ).grid(row=1, column=1, sticky="ew", pady=6)

        tk.Button(
            wrap, text="Browse",
            bg=UI["panel"], fg=UI["text"], relief="flat",
            command=lambda: self._browse_file_into(self.var_piper_bin)
        ).grid(row=1, column=2, padx=8)

        ttk.Separator(wrap, orient="horizontal").grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=14
        )

        tk.Label(
            wrap,
            text="Assign voices to characters",
            font=("Segoe UI", 12, "bold"),
            fg=UI["text"],
            bg=UI["bg"]
        ).grid(row=3, column=0, sticky="w", columnspan=3)

        char_keys = sorted(self.characters.keys())

        self.voice_vars = {}

        r = 4
        for k in char_keys:
            self.voice_vars[k] = tk.StringVar(value=self.voices.get(k, ""))

            tk.Label(
                wrap,
                text=f"{k}",
                font=FONT_BODY,
                fg=UI["muted"],
                bg=UI["bg"]
            ).grid(row=r, column=0, sticky="w", pady=6)

            tk.Entry(
                wrap,
                textvariable=self.voice_vars[k],
                bg=UI["surface"],
                fg=UI["text"],
                insertbackground=UI["text"]
            ).grid(row=r, column=1, sticky="ew", pady=6)

            btnrow = tk.Frame(wrap, bg=UI["bg"])
            btnrow.grid(row=r, column=2, sticky="e")

            tk.Button(
                btnrow,
                text="Browse",
                bg=UI["panel"], fg=UI["text"], relief="flat",
                command=lambda vv=self.voice_vars[k]: self._browse_file_into(vv)
            ).pack(side="left", padx=4)

            tk.Button(
                btnrow,
                text="Sample",
                bg=UI["panel"], fg=UI["accent"], relief="flat",
                command=lambda key=k: self._sample_voice(key)
            ).pack(side="left", padx=4)

            r += 1

        wrap.grid_columnconfigure(1, weight=1)

        ttk.Separator(wrap, orient="horizontal").grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=14
        )

        self.var_sample_text = tk.StringVar(
            value="Checking in—let’s talk markets, risk, and what matters next."
        )

        tk.Label(
            wrap, text="Sample text",
            font=FONT_BODY, fg=UI["muted"], bg=UI["bg"]
        ).grid(row=r+1, column=0, sticky="w")

        tk.Entry(
            wrap,
            textvariable=self.var_sample_text,
            bg=UI["surface"],
            fg=UI["text"],
            insertbackground=UI["text"]
        ).grid(row=r+1, column=1, columnspan=2, sticky="ew")

    def _build_visual_models(self):
        """Build visual models configuration tab (prefilled with global settings)."""
        wrap = tk.Frame(self.tab_visual, bg=UI["bg"])
        wrap.pack(fill="both", expand=True, padx=14, pady=14)

        # Title
        tk.Label(
            wrap,
            text="Vision Model (Optional)",
            font=FONT_H2,
            fg=UI["text"],
            bg=UI["bg"]
        ).pack(anchor="w", pady=(0, 12))

        # Scrollable container
        scrollbar = ttk.Scrollbar(wrap, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        canvas = tk.Canvas(wrap, bg=UI["bg"], highlightthickness=0, yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, pady=8)

        scrollbar.configure(command=canvas.yview)

        scroll_frame = tk.Frame(canvas, bg=UI["bg"])
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # Model Type Selection
        type_frame = tk.LabelFrame(scroll_frame, text="Model Type", fg=UI["text"], bg=UI["panel"],
                                    font=FONT_BODY, padx=12, pady=8)
        type_frame.pack(fill="x", pady=8, padx=8)

        tk.Radiobutton(type_frame, text="Local Model (e.g., Ollama/LLaVA)", 
                       variable=self.var_visual_model_type, value="local",
                       fg=UI["text"], bg=UI["panel"], selectcolor=UI["accent"]).pack(anchor="w", pady=4)
        tk.Radiobutton(type_frame, text="API-based Model", 
                       variable=self.var_visual_model_type, value="api",
                       fg=UI["text"], bg=UI["panel"], selectcolor=UI["accent"]).pack(anchor="w", pady=4)

        # Local Model Config
        local_frame = tk.LabelFrame(scroll_frame, text="Local Model Settings", fg=UI["text"],
                                     bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        local_frame.pack(fill="x", pady=8, padx=8)

        tk.Label(local_frame, text="Model Name / Endpoint:", fg=UI["text"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        tk.Entry(local_frame, textvariable=self.var_visual_model_local, bg=UI["card"], fg=UI["text"],
                insertbackground=UI["text"]).pack(fill="x", pady=(2, 8))
        tk.Label(local_frame, text="(e.g., llava:latest or http://localhost:11434)",
                 fg=UI["muted"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")

        # API Model Config
        api_frame = tk.LabelFrame(scroll_frame, text="API Model Settings", fg=UI["text"],
                                   bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        api_frame.pack(fill="x", pady=8, padx=8)

        tk.Label(api_frame, text="API Provider:", fg=UI["text"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        provider_menu = ttk.Combobox(api_frame, textvariable=self.var_visual_model_api_provider,
                                     values=["openai", "anthropic", "google", "custom"],
                                     state="readonly", width=30)
        provider_menu.pack(fill="x", pady=(2, 8))

        tk.Label(api_frame, text="Model Name:", fg=UI["text"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        tk.Entry(api_frame, textvariable=self.var_visual_model_api_model, bg=UI["card"], fg=UI["text"],
                insertbackground=UI["text"]).pack(fill="x", pady=(2, 8))

        # Max image size
        opts_frame = tk.LabelFrame(scroll_frame, text="Processing Options", fg=UI["text"],
                                    bg=UI["panel"], font=FONT_BODY, padx=12, pady=8)
        opts_frame.pack(fill="x", pady=8, padx=8)

        tk.Label(opts_frame, text="Max Image Size (width):", fg=UI["text"], bg=UI["panel"], font=FONT_SMALL).pack(anchor="w")
        tk.Entry(opts_frame, textvariable=self.var_visual_model_max_size, bg=UI["card"], fg=UI["text"],
                insertbackground=UI["text"], width=10).pack(anchor="w", pady=(2, 8))

        btn_row = tk.Frame(scroll_frame, bg=UI["bg"])
        btn_row.pack(fill="x", pady=(12, 0), padx=8)
        tk.Button(
            btn_row,
            text="Save Visual Models",
            bg=UI["accent"],
            fg="#000",
            relief="flat",
            command=self._save_visual_models_tab,
            font=FONT_BODY,
        ).pack(side="right")

    def _save_visual_models_tab(self):
        """Save visual model settings from the wizard tab."""
        # Persist immediately for edit mode; otherwise just keep staged values.
        if self.edit_mode and self.station:
            manifest_path = station_manifest_path(self.station.path)
            cfg = safe_read_yaml(manifest_path)
            if not isinstance(cfg, dict):
                cfg = {}

            cfg.setdefault("visual_models", {})
            cfg["visual_models"]["model_type"] = self.var_visual_model_type.get().strip()
            cfg["visual_models"]["local_model"] = self.var_visual_model_local.get().strip()
            cfg["visual_models"]["api_provider"] = self.var_visual_model_api_provider.get().strip()
            cfg["visual_models"]["api_model"] = self.var_visual_model_api_model.get().strip()
            cfg["visual_models"]["api_key"] = self.var_visual_model_api_key.get().strip()
            cfg["visual_models"]["max_image_size"] = self.var_visual_model_max_size.get().strip()

            safe_write_yaml(manifest_path, cfg)
            messagebox.showinfo("Success", "Visual model settings saved!")
        else:
            # For new stations, values are staged in the wizard and will be written on Create.
            self._refresh_preview()
            messagebox.showinfo("Saved", "Visual model settings staged for this station.")

    # -------------
    # Step 1: basics
    # -------------
    def _build_basics(self):
        wrap = tk.Frame(self.tab_basics, bg=UI["bg"])
        wrap.pack(fill="both", expand=True, padx=18, pady=18)

        tk.Label(wrap, text="Station settings", font=FONT_H2, fg=UI["text"], bg=UI["bg"]).grid(
            row=0, column=0, sticky="w", pady=(0, 12), columnspan=3
        )

        self.var_station_id = tk.StringVar(value=self.station_id if self.edit_mode else "")
        self.var_station_name = tk.StringVar(value=self.station_name)
        self.var_station_host = tk.StringVar(value=self.station_host)
        self.var_station_cat = tk.StringVar(value=self.station_category)
        self.var_station_logo = tk.StringVar(value=self.station_logo)

        self.var_llm_endpoint = tk.StringVar(value=self.llm_endpoint)
        self.var_model_producer = tk.StringVar(value=self.model_producer)
        self.var_model_host = tk.StringVar(value=self.model_host)
        self.var_llm_provider = tk.StringVar(value="ollama")  # Default to ollama
        
        # Visual model variables
        global_cfg = get_global_config()
        visual_cfg = global_cfg.get("visual_models", {})
        self.var_visual_model_type = tk.StringVar(value=visual_cfg.get("model_type", "local"))
        self.var_visual_model_local = tk.StringVar(value=visual_cfg.get("local_model", ""))
        self.var_visual_model_api_provider = tk.StringVar(value=visual_cfg.get("api_provider", "openai"))
        self.var_visual_model_api_model = tk.StringVar(value=visual_cfg.get("api_model", "gpt-4-vision"))
        self.var_visual_model_api_key = tk.StringVar(value=visual_cfg.get("api_key", ""))
        self.var_visual_model_max_size = tk.StringVar(value=visual_cfg.get("max_image_size", "1024"))

        # Station ID row - read-only in edit mode
        if self.edit_mode:
            tk.Label(wrap, text="Station ID (folder name)", font=FONT_BODY, fg=UI["muted"], bg=UI["bg"]).grid(
                row=1, column=0, sticky="w", padx=(0, 10), pady=6
            )
            tk.Label(wrap, text=self.station_id, font=FONT_BODY, fg=UI["accent"], bg=UI["bg"]).grid(
                row=1, column=1, sticky="w", pady=6
            )
        else:
            self._row(wrap, 1, "Station ID (folder name)", self.var_station_id, hint="e.g. algotradingfm2")
        
        self._row(wrap, 2, "Station name", self.var_station_name)
        self._row(wrap, 3, "Host name", self.var_station_host)
        self._row(wrap, 4, "Category", self.var_station_cat)
        self._row_with_browse(wrap, 5, "Logo", self.var_station_logo, kind="file")

        ttk.Separator(wrap, orient="horizontal").grid(row=6, column=0, columnspan=3, sticky="ew", pady=14)

        tk.Label(wrap, text="Models & LLM", font=FONT_H2, fg=UI["text"], bg=UI["bg"]).grid(
            row=7, column=0, sticky="w", pady=(0, 10), columnspan=3
        )
        
        # Provider selector
        tk.Label(wrap, text="LLM Provider", font=FONT_BODY, fg=UI["muted"], bg=UI["bg"]).grid(
            row=8, column=0, sticky="w", padx=(0, 10), pady=6
        )
        provider_combo = ttk.Combobox(
            wrap, textvariable=self.var_llm_provider,
            values=["ollama", "anthropic", "openai", "google"],
            state="readonly", width=30
        )
        provider_combo.grid(row=8, column=1, sticky="ew", pady=6)
        provider_combo.bind("<<ComboboxSelected>>", lambda e: self._update_llm_labels())
        
        # Endpoint label - changes based on provider
        self.endpoint_label = tk.Label(wrap, text="Endpoint", font=FONT_BODY, fg=UI["muted"], bg=UI["bg"])
        self.endpoint_label.grid(row=9, column=0, sticky="w", padx=(0, 10), pady=6)
        
        endpoint_ent = tk.Entry(wrap, textvariable=self.var_llm_endpoint, font=FONT_BODY, 
                               bg=UI["surface"], fg=UI["text"], insertbackground=UI["text"], width=64)
        endpoint_ent.grid(row=9, column=1, sticky="ew", pady=6)
        
        self.endpoint_hint = tk.Label(wrap, text="", font=FONT_SMALL, fg=UI["muted"], bg=UI["bg"])
        self.endpoint_hint.grid(row=9, column=2, sticky="w", padx=(10, 0))
        
        self._row(wrap, 10, "Producer model", self.var_model_producer, width=64)
        self._row(wrap, 11, "Host model", self.var_model_host, width=64)
        
        # Character Manager model
        self.var_model_char_manager = tk.StringVar(value="")
        self._row(wrap, 12, "Character Manager model", self.var_model_char_manager, width=64, 
                 hint="(Optional) LLM for routing context queries")

        wrap.grid_columnconfigure(1, weight=1)
    
    def _update_llm_labels(self):
        """Update labels based on selected LLM provider."""
        provider = self.var_llm_provider.get()
        
        hints = {
            "ollama": "http://127.0.0.1:11434/api/generate",
            "anthropic": "Set ANTHROPIC_API_KEY env var, model name e.g. claude-3-opus",
            "openai": "Set OPENAI_API_KEY env var, model name e.g. gpt-4",
            "google": "Set GOOGLE_API_KEY env var, model name e.g. gemini-pro",
        }
        
        self.endpoint_hint.config(text=hints.get(provider, ""))

    def _row(self, parent, r, label, var, width=40, hint=""):
        tk.Label(parent, text=label, font=FONT_BODY, fg=UI["muted"], bg=UI["bg"]).grid(
            row=r, column=0, sticky="w", padx=(0, 10), pady=6
        )
        ent = tk.Entry(parent, textvariable=var, font=FONT_BODY, bg=UI["surface"], fg=UI["text"],
                       insertbackground=UI["text"], width=width)
        ent.grid(row=r, column=1, sticky="ew", pady=6)
        if hint:
            tk.Label(parent, text=hint, font=FONT_SMALL, fg=UI["muted"], bg=UI["bg"]).grid(
                row=r, column=2, sticky="w", padx=(10, 0)
            )
    
    def _row_with_browse(self, parent, r, label, var, width=40, kind="file"):
        """Row with browse button for files/folders."""
        tk.Label(parent, text=label, font=FONT_BODY, fg=UI["muted"], bg=UI["bg"]).grid(
            row=r, column=0, sticky="w", padx=(0, 10), pady=6
        )
        ent = tk.Entry(parent, textvariable=var, font=FONT_BODY, bg=UI["surface"], fg=UI["text"],
                       insertbackground=UI["text"], width=width)
        ent.grid(row=r, column=1, sticky="ew", pady=6)
        
        tk.Button(
            parent, text="Browse",
            bg=UI["panel"], fg=UI["text"], relief="flat",
            command=lambda: self._browse_file_into(var, kind=kind)
        ).grid(row=r, column=2, padx=8)

    # -------------
    # Step 2: feeds (HIGH-LEVEL TOGGLES + editor)
    # -------------
    def _build_feeds(self):
        wrap = tk.Frame(self.tab_feeds, bg=UI["bg"])
        wrap.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(
            wrap,
            text="Choose feeds (plugins) and configure them",
            font=FONT_H2, fg=UI["text"], bg=UI["bg"]
        ).pack(anchor="w", pady=(0, 6))

        tk.Label(
            wrap,
            text="Toggle feeds from the high-level list. Click a feed to edit its config on the right.",
            font=FONT_BODY, fg=UI["muted"], bg=UI["bg"]
        ).pack(anchor="w", pady=(0, 12))

        body = tk.Frame(wrap, bg=UI["bg"])
        body.pack(fill="both", expand=True)

        # LEFT SIDE: High-level toggles + feed list
        left = tk.Frame(body, bg=UI["panel"], width=int(360 * UI_SCALE))
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        # RIGHT SIDE: editor
        right = tk.Frame(body, bg=UI["bg"])
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))

        names = self._discover_feed_names()

        # Ensure cfg exists so toggles reflect something real
        for n in names:
            self._ensure_feed_cfg(n)

        if not names:
            names = sorted(FEED_TEMPLATES.keys())

        # Ensure cfg exists so toggles reflect something real
        for n in names:
            self._ensure_feed_cfg(n)

        # ---- Bulk action buttons ----
        topbar = tk.Frame(left, bg=UI["panel"])
        topbar.pack(fill="x", padx=12, pady=(12, 8))

        tk.Label(
            topbar,
            text="Feed Toggles",
            font=("Segoe UI", 12, "bold"),
            fg=UI["text"], bg=UI["panel"]
        ).pack(anchor="w", pady=(0, 8))

        btnrow = tk.Frame(topbar, bg=UI["panel"])
        btnrow.pack(fill="x")

        tk.Button(
            btnrow, text="Enable All",
            bg=UI["panel"], fg=UI["accent"], relief="flat",
            command=lambda: self._bulk_set_feeds(names, True)
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            btnrow, text="Disable All",
            bg=UI["panel"], fg=UI["danger"], relief="flat",
            command=lambda: self._bulk_set_feeds(names, False)
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            btnrow, text="Enable Defaults",
            bg=UI["panel"], fg=UI["text"], relief="flat",
            command=self._enable_default_feeds
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            btnrow, text="Invert",
            bg=UI["panel"], fg=UI["text"], relief="flat",
            command=lambda: self._invert_feeds(names)
        ).pack(side="right")

        ttk.Separator(left, orient="horizontal").pack(fill="x", padx=12, pady=(8, 10))

        # ---- Scrollable checkbox list ----
        self.feed_enabled_vars: Dict[str, tk.BooleanVar] = {}

        scroll = tk.Frame(left, bg=UI["panel"])
        scroll.pack(fill="both", expand=False, padx=12)

        canvas = tk.Canvas(scroll, bg=UI["panel"], highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)

        vsb = ttk.Scrollbar(scroll, orient="vertical", command=canvas.yview)
        vsb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=vsb.set)

        chk_frame = tk.Frame(canvas, bg=UI["panel"])
        canvas.create_window((0, 0), window=chk_frame, anchor="nw")
        def _on_canvas_resize(e):
            canvas.itemconfigure(1, width=e.width)
        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)


        canvas.bind("<Configure>", _on_canvas_resize)

        def _on_chk_frame_configure(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        chk_frame.bind("<Configure>", _on_chk_frame_configure)

        # Create checkboxes
        for n in names:
            cfg = self._ensure_feed_cfg(n)
            v = tk.BooleanVar(value=bool(cfg.get("enabled", False)))
            self.feed_enabled_vars[n] = v

            row = tk.Frame(chk_frame, bg=UI["panel"])
            row.pack(fill="x", pady=3)

            cb = tk.Checkbutton(
                row,
                text=n,
                variable=v,
                command=lambda nn=n: self._toggle_feed_from_var(nn),
                bg=UI["panel"], fg=UI["text"],
                selectcolor=UI["panel"],
                activebackground=UI["panel"],
                anchor="w"
            )
            cb.pack(fill="x")

        ttk.Separator(left, orient="horizontal").pack(fill="x", padx=12, pady=(10, 10))

        tk.Label(
            left,
            text="Click to edit config",
            font=("Segoe UI", 11, "bold"),
            fg=UI["text"], bg=UI["panel"]
        ).pack(anchor="w", padx=12)

        self.feed_list = tk.Listbox(
            left,
            bg=UI["surface"], fg=UI["text"], font=FONT_BODY,
            relief="flat", exportselection=False
        )
        self.feed_list.pack(fill="both", expand=True, padx=12, pady=(8, 12))

        for n in names:
            self.feed_list.insert("end", n)

        self.feed_list.bind("<<ListboxSelect>>", lambda e: self._feed_load_selected())

        # ---- Right side editor ----
        self.feed_editor_title = tk.Label(
            right,
            text="Select a feed on the left",
            font=FONT_H2, fg=UI["muted"], bg=UI["bg"]
        )
        self.feed_editor_title.pack(anchor="w", pady=(0, 10))

        self.feed_editor = tk.Frame(right, bg=UI["bg"])
        self.feed_editor.pack(fill="both", expand=True)

        # Preselect first feed so editor isn't blank
        if self.feed_list.size() > 0:
            self.feed_list.selection_set(0)
            self._feed_load_selected()

    # ---- helpers for high-level toggles ----
    def _toggle_feed_from_var(self, feed_name: str):
        cfg = self._ensure_feed_cfg(feed_name)
        v = self.feed_enabled_vars.get(feed_name)
        if v is None:
            return
        cfg["enabled"] = bool(v.get())
        self.feed_cfg[feed_name] = cfg
        # keep editor pill accurate if currently open
        self._feed_load_selected()

    def _set_feed_enabled(self, feed_name: str, enabled: bool):
        cfg = self._ensure_feed_cfg(feed_name)
        cfg["enabled"] = bool(enabled)
        self.feed_cfg[feed_name] = cfg
        if hasattr(self, "feed_enabled_vars") and feed_name in self.feed_enabled_vars:
            self.feed_enabled_vars[feed_name].set(bool(enabled))

    def _bulk_set_feeds(self, feed_names: List[str], enabled: bool):
        for n in feed_names:
            self._set_feed_enabled(n, enabled)
        self._feed_load_selected()

    def _invert_feeds(self, feed_names: List[str]):
        for n in feed_names:
            cfg = self._ensure_feed_cfg(n)
            cur = bool(cfg.get("enabled", False))
            self._set_feed_enabled(n, not cur)
        self._feed_load_selected()

    def _enable_default_feeds(self):
        # DEFAULT_SCHED_QUOTAS keys are your “recommended” gold set
        defaults = set(DEFAULT_SCHED_QUOTAS.keys())
        all_names = list(self.feed_cfg.keys()) if self.feed_cfg else []
        if not all_names and hasattr(self, "feed_enabled_vars"):
            all_names = list(self.feed_enabled_vars.keys())

        # If we still don't know, fall back to templates
        if not all_names:
            all_names = list(FEED_TEMPLATES.keys())

        for n in all_names:
            self._set_feed_enabled(n, n in defaults)

        self._feed_load_selected()


    def _feed_selected(self) -> Optional[str]:
        sel = self.feed_list.curselection()
        if not sel:
            return None
        return self.feed_list.get(sel[0])

    def _ensure_feed_cfg(self, feed_name: str) -> Dict[str, Any]:
        if feed_name not in self.feed_cfg:
            # Priority: plugin defaults -> FEED_TEMPLATES -> minimal stub
            meta = (self.plugins or {}).get(feed_name, {}) if isinstance(self.plugins, dict) else {}
            base = meta.get("defaults")
            if not isinstance(base, dict):
                base = FEED_TEMPLATES.get(feed_name)
            if not isinstance(base, dict):
                base = {"enabled": False}

            cfg = _deepcopy_jsonable(base)
            cfg.setdefault("enabled", False)  # IMPORTANT: default to off
            self.feed_cfg[feed_name] = cfg

        return self.feed_cfg[feed_name]


    def _feed_enable_selected(self):
        n = self._feed_selected()
        if not n:
            return
        cfg = self._ensure_feed_cfg(n)
        cfg["enabled"] = True
        self._feed_load_selected()

    def _feed_disable_selected(self):
        n = self._feed_selected()
        if not n:
            return
        cfg = self._ensure_feed_cfg(n)
        cfg["enabled"] = False
        self._feed_load_selected()

    def _feed_reset_selected(self):
        n = self._feed_selected()
        if not n:
            return
        base = FEED_TEMPLATES.get(n, {"enabled": True})
        self.feed_cfg[n] = _deepcopy_jsonable(base)
        self._feed_load_selected()

    def _clear(self, parent: tk.Widget):
        for w in parent.winfo_children():
            w.destroy()

    def _feed_load_selected(self):
        n = self._feed_selected()
        if not n:
            return

        cfg = self._ensure_feed_cfg(n)

        # Merge defaults so new keys (like auth) appear
        meta = (self.plugins or {}).get(n, {})
        if isinstance(meta, dict):
            defs = meta.get("defaults")
            if isinstance(defs, dict):
                for k, v in defs.items():
                    if k not in cfg:
                        # Copy default value if missing
                        cfg[k] = v

        self._clear(self.feed_editor)
        self.feed_editor_title.config(text=f"{n} feed")

        # enabled summary
        enabled = bool(cfg.get("enabled", False))
        pill = tk.Label(
            self.feed_editor,
            text=("ENABLED" if enabled else "DISABLED"),
            font=("Segoe UI", 10, "bold"),
            fg=("#000" if enabled else UI["text"]),
            bg=(UI["good"] if enabled else UI["panel"]),
            padx=10, pady=4
        )
        pill.pack(anchor="w", pady=(0, 10))

        # Live search "ready" panels (stubs now, wired later)
        if n == "reddit":
            self._render_reddit_live_search_stub(self.feed_editor, cfg)
        elif n == "bluesky":
            self._render_bluesky_live_search_stub(self.feed_editor, cfg)

        # generic config editor for feed fields
        form = tk.Frame(self.feed_editor, bg=UI["bg"])
        form.pack(fill="both", expand=True, pady=(10, 0))

        rows: List[tuple] = []
        for k in sorted(cfg.keys()):
            if k == "enabled":
                continue
            rows.append((k, cfg[k]))

        self._feed_vars: Dict[str, tk.Variable] = {}
        for i, (k, v) in enumerate(rows):
            row = tk.Frame(form, bg=UI["bg"])
            row.pack(fill="x", pady=6)

            tk.Label(row, text=k, font=FONT_BODY, fg=UI["muted"], bg=UI["bg"], width=22, anchor="w").pack(side="left")

            if isinstance(v, bool):
                vv = tk.BooleanVar(value=bool(v))
                tk.Checkbutton(row, variable=vv, bg=UI["bg"], fg=UI["text"], selectcolor=UI["bg"]).pack(side="left")
                self._feed_vars[k] = vv
            else:
                if isinstance(v, list):
                    sv = tk.StringVar(value=json.dumps(v, ensure_ascii=False))
                else:
                    sv = tk.StringVar(value=str(v))
                ent = tk.Entry(row, textvariable=sv, bg=UI["surface"], fg=UI["text"], insertbackground=UI["text"])
                ent.pack(fill="x", expand=True)
                self._feed_vars[k] = sv

        # Save feed config changes button
        def apply():
            for k, var in self._feed_vars.items():
                if isinstance(var, tk.BooleanVar):
                    cfg[k] = bool(var.get())
                else:
                    raw = str(var.get() or "").strip()
                    try:
                        cfg[k] = yaml.safe_load(raw)
                    except Exception:
                        cfg[k] = raw
            self.feed_cfg[n] = cfg

        tk.Button(
            self.feed_editor,
            text="Apply feed changes",
            bg=UI["accent"], fg="#000", relief="flat",
            command=apply
        ).pack(anchor="w", pady=12)

    def _render_reddit_live_search_stub(self, parent: tk.Widget, cfg: Dict[str, Any]):
        box = tk.Frame(parent, bg=UI["panel"])
        box.pack(fill="x", pady=(0, 10))
        tk.Label(box, text="Reddit: live subreddit search (ready for integration)", font=("Segoe UI", 11, "bold"),
                 fg=UI["text"], bg=UI["panel"]).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(box, text="For now, add subreddits below as a list. Later we’ll wire real search + click-to-add.",
                 font=FONT_SMALL, fg=UI["muted"], bg=UI["panel"]).pack(anchor="w", padx=12, pady=(0, 10))

        row = tk.Frame(box, bg=UI["panel"])
        row.pack(fill="x", padx=12, pady=(0, 12))
        q = tk.StringVar()
        tk.Entry(row, textvariable=q, bg=UI["surface"], fg=UI["text"], insertbackground=UI["text"]).pack(
            side="left", fill="x", expand=True
        )

        def add_sub():
            s = (q.get() or "").strip()
            if not s:
                return
            subs = cfg.get("subreddits", [])
            if not isinstance(subs, list):
                subs = []
            if s not in subs:
                subs.append(s)
            cfg["subreddits"] = subs
            q.set("")
            # reflect immediately in config editor if it exists
            self._feed_load_selected()

        tk.Button(row, text="Add", bg=UI["panel"], fg=UI["accent"], relief="flat", command=add_sub).pack(side="left", padx=8)

    def _render_bluesky_live_search_stub(self, parent: tk.Widget, cfg: Dict[str, Any]):
        box = tk.Frame(parent, bg=UI["panel"])
        box.pack(fill="x", pady=(0, 10))
        tk.Label(box, text="Bluesky: live hashtag suggestions (ready for integration)", font=("Segoe UI", 11, "bold"),
                 fg=UI["text"], bg=UI["panel"]).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(box, text="For now, add hashtags below. Later we’ll fetch real suggestions and show a clickable list.",
                 font=FONT_SMALL, fg=UI["muted"], bg=UI["panel"]).pack(anchor="w", padx=12, pady=(0, 10))

        row = tk.Frame(box, bg=UI["panel"])
        row.pack(fill="x", padx=12, pady=(0, 12))
        q = tk.StringVar()
        tk.Entry(row, textvariable=q, bg=UI["surface"], fg=UI["text"], insertbackground=UI["text"]).pack(
            side="left", fill="x", expand=True
        )

        def add_tag():
            s = (q.get() or "").strip().lstrip("#")
            if not s:
                return
            tags = cfg.get("hashtags", [])
            if not isinstance(tags, list):
                tags = []
            if s not in tags:
                tags.append(s)
            cfg["hashtags"] = tags
            q.set("")
            self._feed_load_selected()

        tk.Button(row, text="Add", bg=UI["panel"], fg=UI["accent"], relief="flat", command=add_tag).pack(side="left", padx=8)
    def _characters_changed(self):
        """
        Single source of truth sync between characters + voices + UI.
        Fixes duplicates, stale entries, and missed refreshes.
        """

        # --- 1) Capture current voice UI edits if present
        try:
            if hasattr(self, "voice_vars") and isinstance(self.voice_vars, dict):
                for k, var in self.voice_vars.items():
                    try:
                        self.voices[k] = (var.get() or "").strip()
                    except Exception:
                        pass
        except Exception:
            pass

        # --- 2) Ensure every character has a voice entry
        for k in self.characters.keys():
            if k not in self.voices:
                self.voices[k] = ""

        # --- 3) Remove voices for deleted characters
        for k in list(self.voices.keys()):
            if k not in self.characters:
                self.voices.pop(k, None)

        # --- 4) Refresh voices UI if tab exists (safe always)
        try:
            if hasattr(self, "tab_voices"):
                self._refresh_voices_tab()
        except Exception:
            pass


    # -------------
    # Step 3: characters
    # -------------


    def _append_to_json_list(self, var: tk.StringVar, value: str):
        v = (value or "").strip()
        if not v:
            return
        try:
            arr = parse_list_field(var.get())
            if not isinstance(arr, list):
                arr = []
        except Exception:
            arr = []
        if v not in arr:
            arr.append(v)
        var.set(json.dumps(arr, ensure_ascii=False))

    def _refresh_char_list(self):
        self.char_list.delete(0, "end")
        for k in sorted(self.characters.keys()):
            self.char_list.insert("end", k)

    def _char_selected_key(self) -> Optional[str]:
        sel = self.char_list.curselection()
        if not sel:
            return None
        return self.char_list.get(sel[0])

    def _char_load_selected(self):
        k = self._char_selected_key()
        if not k:
            return
        c = self.characters.get(k, {})
        if not isinstance(c, dict):
            return
        self.var_char_key.set(k)
        self.var_char_role.set(str(c.get("role", "")))
        self.var_char_traits.set(json.dumps(c.get("traits", []), ensure_ascii=False))
        self.var_char_focus.set(json.dumps(c.get("focus", []), ensure_ascii=False))
        
        # Load context engine config
        if hasattr(self, "context_engine_frame"):
            context_cfg = c.get("context_engine", {})
            self.context_engine_frame.load_config(context_cfg)
            if hasattr(self, "_char_context_engines"):
                self._char_context_engines[k] = context_cfg
    def _char_apply(self):
        old = self._char_selected_key()
        if not old:
            return

        new_key = (self.var_char_key.get() or "").strip().lower()
        if not new_key:
            messagebox.showerror("Character", "Character key cannot be empty.")
            return

        role = (self.var_char_role.get() or "").strip()
        traits = parse_list_field(self.var_char_traits.get())
        focus = parse_list_field(self.var_char_focus.get())

        if not isinstance(traits, list):
            traits = []
        if not isinstance(focus, list):
            focus = []

        if old == "host" and new_key != "host":
            messagebox.showerror("Character", "Host key must remain 'host'.")
            return

        # rename if needed
        if new_key != old:
            if new_key in self.characters:
                messagebox.showerror("Character", f"'{new_key}' already exists.")
                return
            self.characters[new_key] = self.characters.pop(old)
            
            # Rename context engine config if exists
            if hasattr(self, "_char_context_engines") and old in self._char_context_engines:
                self._char_context_engines[new_key] = self._char_context_engines.pop(old)

        # Get context engine config
        context_engine = {}
        if hasattr(self, "context_engine_frame"):
            context_engine = self.context_engine_frame.get_config()
            if hasattr(self, "_char_context_engines"):
                self._char_context_engines[new_key] = context_engine

        self.characters[new_key] = {
            "role": role,
            "traits": traits,
            "focus": focus
        }
        
        # Add context_engine if enabled
        if context_engine.get("enabled"):
            self.characters[new_key]["context_engine"] = context_engine

        self._refresh_char_list()
        self._characters_changed()   # 🔥 SYNC VOICES

        # Reselect
        for i in range(self.char_list.size()):
            if self.char_list.get(i) == new_key:
                self.char_list.selection_clear(0, "end")
                self.char_list.selection_set(i)
                self.char_list.see(i)
                break

        messagebox.showinfo("Character saved", f"{new_key} updated.")

    def _char_add(self):

        win = tk.Toplevel(self.win)
        win.title("Add Character")
        win.geometry(scaled_geometry(520, 300))
        win.configure(bg=UI["bg"])
        win.grab_set()

        tk.Label(
            win, text="Add a character",
            font=FONT_H2, fg=UI["text"], bg=UI["bg"]
        ).pack(anchor="w", padx=14, pady=(14, 8))

        tk.Label(
            win, text="Pick a suggested role, then choose a key name.",
            font=FONT_BODY, fg=UI["muted"], bg=UI["bg"]
        ).pack(anchor="w", padx=14)

        key_var = tk.StringVar()
        role_var = tk.StringVar()

        row1 = tk.Frame(win, bg=UI["bg"])
        row1.pack(fill="x", padx=14, pady=(14, 6))

        tk.Label(row1, text="Key", fg=UI["muted"], bg=UI["bg"], width=10, anchor="w").pack(side="left")
        tk.Entry(
            row1, textvariable=key_var,
            bg=UI["surface"], fg=UI["text"], insertbackground=UI["text"]
        ).pack(side="left", fill="x", expand=True)

        row2 = tk.Frame(win, bg=UI["bg"])
        row2.pack(fill="x", padx=14, pady=6)

        tk.Label(row2, text="Role", fg=UI["muted"], bg=UI["bg"], width=10, anchor="w").pack(side="left")
        cb = ttk.Combobox(row2, values=PRESET_ROLES, state="readonly")
        cb.pack(side="left", fill="x", expand=True)
        cb.bind("<<ComboboxSelected>>", lambda e: role_var.set(cb.get()))

        def ok():
            k = (key_var.get() or "").strip().lower()
            if not k:
                return
            if k == "host":
                messagebox.showerror("Character", "host already exists.")
                return
            if k in self.characters:
                messagebox.showerror("Character", "That key already exists.")
                return

            role = (role_var.get() or "").strip() or k

            traits = []
            focus = []

            if "engineer" in role:
                traits = ["technical", "precise"]
                focus = ["systems", "signals"]
            elif "skeptic" in role or "risk" in role:
                traits = ["critical", "grounded"]
                focus = ["risk", "failure_modes"]
            elif "macro" in role:
                traits = ["contextual", "broad"]
                focus = ["regimes", "liquidity"]
            elif "optimist" in role or "hype" in role:
                traits = ["energetic", "constructive"]
                focus = ["opportunity", "growth"]

            self.characters[k] = {
                "role": role,
                "traits": traits,
                "focus": focus
            }

            self._refresh_char_list()
            self._characters_changed()   # 🔥 SYNC VOICES

            win.destroy()

        btn = tk.Frame(win, bg=UI["bg"])
        btn.pack(fill="x", padx=14, pady=14)

        tk.Button(btn, text="Cancel", bg=UI["panel"], fg=UI["text"], relief="flat", command=win.destroy).pack(side="right", padx=6)
        tk.Button(btn, text="Add", bg=UI["accent"], fg="#000", relief="flat", command=ok).pack(side="right", padx=6)

    def _char_remove(self):
        k = self._char_selected_key()
        if not k:
            return

        if k == "host":
            messagebox.showerror("Characters", "Host cannot be removed.")
            return

        if len(self.characters) <= 2:
            messagebox.showerror("Characters", "Need at least 2 characters.")
            return

        if not messagebox.askyesno("Remove", f"Remove '{k}'?"):
            return

        self.characters.pop(k, None)

        self._refresh_char_list()
        self._characters_changed()   # 🔥 SYNC VOICES

        if self.char_list.size() > 0:
            self.char_list.selection_set(0)
            self._char_load_selected()


    def _char_load_preset_set(self):
        mem_presets = globals().get("CHARACTER_PRESETS", {})
        if not isinstance(mem_presets, dict):
            mem_presets = {}

        disk_presets = self._load_disk_character_presets()
        if not isinstance(disk_presets, dict):
            disk_presets = {}

        # Merge (disk overrides same-name in-memory)
        presets: Dict[str, Any] = {}
        presets.update(mem_presets)
        presets.update(disk_presets)

        if not presets:
            messagebox.showerror("Presets", "No character presets found.")
            return

        win = tk.Toplevel(self.win)
        win.title("Load Character Preset Set")
        win.geometry(scaled_geometry(520, 520))
        win.configure(bg=UI["bg"])
        win.grab_set()

        tk.Label(win, text="Choose a preset set", font=FONT_H2, fg=UI["text"], bg=UI["bg"]).pack(anchor="w", padx=14, pady=(14, 8))

        hint = "Includes built-in presets + anything you saved to disk."
        tk.Label(win, text=hint, font=FONT_SMALL, fg=UI["muted"], bg=UI["bg"]).pack(anchor="w", padx=14, pady=(0, 10))

        lb = tk.Listbox(win, bg=UI["surface"], fg=UI["text"], font=FONT_BODY, relief="flat")
        lb.pack(fill="both", expand=True, padx=14, pady=12)

        names = sorted(presets.keys())
        for name in names:
            lb.insert("end", name)

        def load():
            sel = lb.curselection()
            if not sel:
                return

            name = lb.get(sel[0])
            chosen = presets.get(name, {})
            if not isinstance(chosen, dict):
                return

            if "host" not in chosen:
                messagebox.showerror("Presets", "Preset must include 'host'.")
                return

            if not messagebox.askyesno("Replace characters", f"Load '{name}'?\nThis replaces your current characters."):
                return

            self.characters = _deepcopy_jsonable(chosen)

            keys = sorted(self.characters.keys())
            if len(keys) > 10:
                others = [k for k in keys if k != "host"]
                keep = ["host"] + others[:9]
                self.characters = {k: self.characters[k] for k in keep}

            self._refresh_char_list()
            self._characters_changed()   # 🔥 SYNC VOICES

            if self.char_list.size() > 0:
                self.char_list.selection_set(0)
                self._char_load_selected()

            win.destroy()


        btn = tk.Frame(win, bg=UI["bg"])
        btn.pack(fill="x", padx=14, pady=(0, 14))
        tk.Button(btn, text="Cancel", bg=UI["panel"], fg=UI["text"], relief="flat", command=win.destroy).pack(side="right", padx=6)
        tk.Button(btn, text="Load", bg=UI["accent"], fg="#000", relief="flat", command=load).pack(side="right", padx=6)

        # -------------
        # Step 4: voices
        # -------------
    def _build_characters(self):
        wrap = tk.Frame(self.tab_chars, bg=UI["bg"])
        wrap.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(
            wrap,
            text="Choose your characters",
            font=FONT_H2,
            fg=UI["text"],
            bg=UI["bg"]
        ).pack(anchor="w")

        tk.Label(
            wrap,
            text="Host is required (minimum). Add others from presets, then customize role/traits/focus.",
            font=FONT_BODY,
            fg=UI["muted"],
            bg=UI["bg"]
        ).pack(anchor="w", pady=(4, 10))

        body = tk.Frame(wrap, bg=UI["bg"])
        body.pack(fill="both", expand=True)

        # =========================
        # LEFT PANEL (LIST + BUTTONS)
        # =========================

        left = tk.Frame(body, bg=UI["panel"], width=int(260 * UI_SCALE))
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        self.char_list = tk.Listbox(
            left,
            bg=UI["surface"],
            fg=UI["text"],
            font=FONT_BODY,
            relief="flat",
            exportselection=False
        )
        self.char_list.pack(fill="both", expand=True, padx=10, pady=10)

        # -------------------------
        # BUTTON AREA (2 ROWS)
        # -------------------------

        btns = tk.Frame(left, bg=UI["panel"])
        btns.pack(fill="x", padx=10, pady=(0, 10))

        # Row 1 — Add / Remove
        row1 = tk.Frame(btns, bg=UI["panel"])
        row1.pack(fill="x")

        tk.Button(
            row1,
            text="Add…",
            bg=UI["panel"],
            fg=UI["accent"],
            relief="flat",
            command=self._char_add
        ).pack(side="left", padx=4)

        tk.Button(
            row1,
            text="Remove",
            bg=UI["panel"],
            fg=UI["danger"],
            relief="flat",
            command=self._char_remove
        ).pack(side="left", padx=4)

        # Row 2 — Presets
        row2 = tk.Frame(btns, bg=UI["panel"])
        row2.pack(fill="x", pady=(6, 0))

        tk.Button(
            row2,
            text="Save preset set…",
            bg=UI["panel"],
            fg=UI["text"],
            relief="flat",
            command=self._char_save_preset_set
        ).pack(side="left", padx=4)

        tk.Button(
            row2,
            text="Load preset set…",
            bg=UI["panel"],
            fg=UI["text"],
            relief="flat",
            command=self._char_load_preset_set
        ).pack(side="left", padx=4)

        # Populate list
        self._refresh_char_list()

        # =========================
        # RIGHT PANEL (EDITOR)
        # =========================

        right = tk.Frame(body, bg=UI["bg"])
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))

        self.var_char_key = tk.StringVar(value="")
        self.var_char_role = tk.StringVar(value="")
        self.var_char_traits = tk.StringVar(value="[]")
        self.var_char_focus = tk.StringVar(value="[]")

        # ---- Key ----

        tk.Label(
            right,
            text="Character key",
            font=FONT_BODY,
            fg=UI["muted"],
            bg=UI["bg"]
        ).pack(anchor="w")

        tk.Entry(
            right,
            textvariable=self.var_char_key,
            bg=UI["surface"],
            fg=UI["text"],
            insertbackground=UI["text"]
        ).pack(fill="x", pady=(0, 10))

        # ---- Role ----

        tk.Label(
            right,
            text="Role (choose from presets or type)",
            font=FONT_BODY,
            fg=UI["muted"],
            bg=UI["bg"]
        ).pack(anchor="w")

        row_role = tk.Frame(right, bg=UI["bg"])
        row_role.pack(fill="x", pady=(0, 10))

        tk.Entry(
            row_role,
            textvariable=self.var_char_role,
            bg=UI["surface"],
            fg=UI["text"],
            insertbackground=UI["text"]
        ).pack(side="left", fill="x", expand=True)

        role_pick = ttk.Combobox(
            row_role,
            values=PRESET_ROLES,
            state="readonly",
            width=20
        )
        role_pick.pack(side="left", padx=8)
        role_pick.bind(
            "<<ComboboxSelected>>",
            lambda e: self.var_char_role.set(role_pick.get())
        )

        # ---- Traits ----

        tk.Label(
            right,
            text="Traits (JSON list) — or use picker",
            font=FONT_BODY,
            fg=UI["muted"],
            bg=UI["bg"]
        ).pack(anchor="w")

        row_traits = tk.Frame(right, bg=UI["bg"])
        row_traits.pack(fill="x", pady=(0, 10))

        tk.Entry(
            row_traits,
            textvariable=self.var_char_traits,
            bg=UI["surface"],
            fg=UI["text"],
            insertbackground=UI["text"]
        ).pack(side="left", fill="x", expand=True)

        traits_pick = ttk.Combobox(
            row_traits,
            values=PRESET_TRAITS,
            state="readonly",
            width=20
        )
        traits_pick.pack(side="left", padx=8)

        tk.Button(
            row_traits,
            text="＋",
            bg=UI["panel"],
            fg=UI["accent"],
            relief="flat",
            command=lambda: self._append_to_json_list(
                self.var_char_traits,
                traits_pick.get()
            )
        ).pack(side="left")

        # ---- Focus ----

        tk.Label(
            right,
            text="Focus (JSON list) — or use picker",
            font=FONT_BODY,
            fg=UI["muted"],
            bg=UI["bg"]
        ).pack(anchor="w")

        row_focus = tk.Frame(right, bg=UI["bg"])
        row_focus.pack(fill="x", pady=(0, 10))

        tk.Entry(
            row_focus,
            textvariable=self.var_char_focus,
            bg=UI["surface"],
            fg=UI["text"],
            insertbackground=UI["text"]
        ).pack(side="left", fill="x", expand=True)

        focus_pick = ttk.Combobox(
            row_focus,
            values=PRESET_FOCUS,
            state="readonly",
            width=20
        )
        focus_pick.pack(side="left", padx=8)

        tk.Button(
            row_focus,
            text="＋",
            bg=UI["panel"],
            fg=UI["accent"],
            relief="flat",
            command=lambda: self._append_to_json_list(
                self.var_char_focus,
                focus_pick.get()
            )
        ).pack(side="left")

        # ---- Context Engine ----
        
        from context_engine_ui import build_context_engine_ui
        
        # Store context engine config per character
        if not hasattr(self, "_char_context_engines"):
            self._char_context_engines = {}
        
        def get_context_cfg():
            char_key = self.var_char_key.get().strip()
            return self._char_context_engines.get(char_key, {})
        
        def set_context_cfg(cfg):
            char_key = self.var_char_key.get().strip()
            self._char_context_engines[char_key] = cfg
        
        self.context_engine_frame = build_context_engine_ui(
            parent=right,
            bg=UI["panel"],
            surface=UI["surface"],
            text_color=UI["text"],
            muted=UI["muted"],
            accent=UI["accent"],
            get_context_cfg_func=get_context_cfg,
            set_context_cfg_func=set_context_cfg,
            station_dir=""  # Will use station_dir when available
        )
        self.context_engine_frame.pack(fill="x", pady=10)

        # ---- Apply ----

        tk.Button(
            right,
            text="Apply character changes",
            bg=UI["accent"],
            fg="#000",
            relief="flat",
            command=self._char_apply
        ).pack(anchor="w", pady=12)

        # -------------------------
        # Selection wiring
        # -------------------------

        self.char_list.bind(
            "<<ListboxSelect>>",
            lambda e: self._char_load_selected()
        )

        if self.char_list.size() > 0:
            self.char_list.selection_set(0)
            self._char_load_selected()

    def _browse_file_into(self, var: tk.StringVar, kind: str = "file"):
        if kind == "file":
            p = filedialog.askopenfilename(parent=self.win)
        else:
            p = filedialog.askdirectory(parent=self.win)

        if p:
            var.set(p)

    def _sample_voice(self, voice_key: str):
        piper = (self.var_piper_bin.get() or "").strip()
        model = (self.voice_vars.get(voice_key).get() or "").strip() if voice_key in self.voice_vars else ""
        text = (self.var_sample_text.get() or "").strip()

        if not piper or not os.path.exists(piper):
            messagebox.showerror("Sample voice", "Set a valid Piper binary path first.")
            return
        if not model or not os.path.exists(model):
            messagebox.showerror("Sample voice", f"Set a valid voice model path for '{voice_key}'.")
            return
        if not text:
            messagebox.showerror("Sample voice", "Sample text is empty.")
            return

        try:
            import tempfile
            out_wav = os.path.join(tempfile.gettempdir(), f"radioos_sample_{voice_key}.wav")
            # Piper usage differs by build; this is a common pattern:
            # echo "text" | piper -m model.onnx -f out.wav
            cmd = [piper, "-m", model, "-f", out_wav]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            proc.communicate(text + "\n", timeout=20)
            if os.path.exists(out_wav):
                _try_play_wav(out_wav)
            else:
                messagebox.showerror("Sample voice", "Failed to produce wav output.")
        except Exception as e:
            messagebox.showerror("Sample voice", f"Voice sample failed.\n\n{e}")
    def _character_presets_path(self) -> str:
        # Stored in repo root alongside shell.py; change if you want per-user
        return os.path.join(BASE, "character_presets.yaml")

    def _load_disk_character_presets(self) -> Dict[str, Any]:
        p = self._character_presets_path()
        if not os.path.exists(p):
            return {}
        try:
            with open(p, "r", encoding="utf-8") as f:
                obj = yaml.safe_load(f) or {}
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    def _save_disk_character_presets(self, presets: Dict[str, Any]) -> None:
        p = self._character_presets_path()
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.safe_dump(presets, f, sort_keys=False, allow_unicode=True)
        os.replace(tmp, p)

    def _char_save_preset_set(self):
        # Validate current set
        if "host" not in self.characters:
            messagebox.showerror("Presets", "Cannot save: missing 'host'.")
            return
        if len(self.characters) < 2:
            messagebox.showerror("Presets", "Need at least 2 characters to save a preset.")
            return

        name = self.shell._prompt_text("Save Character Preset Set", "Preset name (e.g. 'AlgoTrading FM v2'):")
        if not name:
            return
        name = name.strip()
        if not name:
            return

        disk = self._load_disk_character_presets()

        # If exists, confirm overwrite
        if name in disk:
            if not messagebox.askyesno("Overwrite preset", f"Preset '{name}' exists.\nOverwrite?"):
                return

        disk[name] = _deepcopy_jsonable(self.characters)
        self._save_disk_character_presets(disk)
        messagebox.showinfo("Preset saved", f"Saved '{name}' to {self._character_presets_path()}")

    # -------------
    # Step 5: mix weights pie + sliders
    # -------------
    def _build_mix(self):
        # Create wrapper frame - actual rendering happens in _render_mix_ui when tab is shown
        self.weight_sliders = {}
        self.mix_wrap = tk.Frame(self.tab_mix, bg=UI["bg"])
        self.mix_wrap.pack(fill="both", expand=True, padx=14, pady=14)
        
        # Initialize pie canvas placeholder
        self.pie = None


    def _mix_collect(self) -> Dict[str, float]:
        w = {}
        for k, var in self.weight_sliders.items():
            try:
                w[k] = float(var.get())
            except Exception:
                w[k] = 0.0
        return w

    def _mix_normalize_clicked(self):
        w = _normalize_weights(self._mix_collect())
        for k, frac in w.items():
            if k in self.weight_sliders:
                self.weight_sliders[k].set(frac)
        self._mix_redraw()

    def _mix_redraw(self):
        w = self._mix_collect()
        w = _normalize_weights(w)
        # update state
        self.mix_weights.update(w)
        
        # Safety check - pie canvas may not exist yet
        if not self.pie:
            return

        self.pie.delete("all")
        cx, cy = 260, 260
        r = 200
        x0, y0, x1, y1 = cx - r, cy - r, cx + r, cy + r

        segs = _pie_segments(w)

        # Use a rotating palette that relies on system colors lightly (no hardcoding too many),
        # but tkinter requires explicit fill colors; keep a small stable palette.
        palette = ["#4cc9f0", "#2ee59d", "#ff4d6d", "#f7b801", "#b084f5", "#2a9d8f", "#e76f51", "#8ecae6"]
        for i, (k, start, ext) in enumerate(segs):
            fill = palette[i % len(palette)]
            self.pie.create_arc(x0, y0, x1, y1, start=start, extent=ext, fill=fill, outline=UI["bg"])

        # Legend
        y = 20
        for i, (k, _, _) in enumerate(segs):
            frac = w.get(k, 0.0)
            fill = palette[i % len(palette)]
            self.pie.create_rectangle(20, y, 36, y + 16, fill=fill, outline="")
            self.pie.create_text(44, y + 8, text=f"{k}: {frac:.2f}", anchor="w", fill=UI["text"], font=("Segoe UI", 10))
            y += 22

    # -------------
    # Step 6: review
    # -------------
    def _build_review(self):
        wrap = tk.Frame(self.tab_review, bg=UI["bg"])
        wrap.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(wrap, text="Review & Create", font=FONT_H2, fg=UI["text"], bg=UI["bg"]).pack(anchor="w", pady=(0, 10))
        tk.Label(
            wrap,
            text="This is the exact manifest.yaml that will be written into stations/<station_id>/manifest.yaml.",
            font=FONT_BODY, fg=UI["muted"], bg=UI["bg"]
        ).pack(anchor="w", pady=(0, 10))

        self.review_text = tk.Text(wrap, bg=UI["surface"], fg=UI["text"], font=("Consolas", 10),
                                   relief="flat", bd=0, wrap="none", height=28)
        self.review_text.pack(fill="both", expand=True)

        btnrow = tk.Frame(wrap, bg=UI["bg"])
        btnrow.pack(fill="x", pady=10)

        tk.Button(btnrow, text="Refresh preview", bg=UI["panel"], fg=UI["text"], relief="flat", command=self._refresh_preview).pack(
            side="left", padx=6
        )
        button_text = "Save Changes" if self.edit_mode else "Create station"
        tk.Button(btnrow, text=button_text, bg=UI["accent"], fg="#000", relief="flat", command=self._finish).pack(
            side="right", padx=6
        )

        self._refresh_preview()

    def _load_default_manifest(self) -> Dict[str, Any]:
        path = os.path.join(BASE, "templates", "default_manifest.yaml")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                raise ValueError("Template is not a dict")
            return data
        except Exception as e:
            raise RuntimeError(f"Failed loading default manifest: {e}")

    def _merge_manifests(self, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        """Recursive merge of override into base."""
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._merge_manifests(base[k], v)
            else:
                base[k] = _deepcopy_jsonable(v)

    def _build_manifest(self) -> Dict[str, Any]:

        manifest = self._load_default_manifest()

        # If editing an existing station, overlay its configuration first.
        # This ensures that fields NOT managed by the wizard (pacing, riff, producer settings)
        # are preserved, rather than being reset to default template values.
        if self.existing_manifest:
            self._merge_manifests(manifest, self.existing_manifest)

        # -------- Station --------

        manifest["station"]["name"] = self.var_station_name.get().strip()
        manifest["station"]["host"] = self.var_station_host.get().strip()
        manifest["station"]["category"] = self.var_station_cat.get().strip()
        manifest["station"]["logo"] = self.var_station_logo.get().strip()

        # -------- Models --------

        manifest["llm"]["endpoint"] = self.var_llm_endpoint.get().strip()
        manifest["llm"]["provider"] = self.var_llm_provider.get().strip()

        manifest["models"]["producer"] = self.var_model_producer.get().strip()
        manifest["models"]["host"] = self.var_model_host.get().strip()
        manifest["models"]["character_manager"] = self.var_model_char_manager.get().strip()
        
        # -------- Visual Models --------
        manifest.setdefault("visual_models", {})
        manifest["visual_models"]["model_type"] = self.var_visual_model_type.get().strip()
        manifest["visual_models"]["local_model"] = self.var_visual_model_local.get().strip()
        manifest["visual_models"]["api_provider"] = self.var_visual_model_api_provider.get().strip()
        manifest["visual_models"]["api_model"] = self.var_visual_model_api_model.get().strip()
        manifest["visual_models"]["api_key"] = self.var_visual_model_api_key.get().strip()
        manifest["visual_models"]["max_image_size"] = self.var_visual_model_max_size.get().strip()

        # -------- Audio --------

        manifest["audio"]["piper_bin"] = self.var_piper_bin.get().strip()

        # Sync voice vars from UI before saving
        if hasattr(self, "voice_vars") and isinstance(self.voice_vars, dict):
            for k, var in self.voice_vars.items():
                try:
                    self.voices[k] = var.get().strip()
                except Exception:
                    pass

        manifest["voices"] = _deepcopy_jsonable(self.voices)

        # -------- Characters --------

        manifest["characters"] = _deepcopy_jsonable(self.characters)

        # -------- Feeds --------

        # -------- Feeds --------

        feeds_out: Dict[str, Any] = {}

        # Include ALL discovered feeds (enabled or not) so future toggles don’t need wizard edits.
        all_names = self._discover_feed_names()

        for name in all_names:
            cfg = self._ensure_feed_cfg(name)
            if not isinstance(cfg, dict):
                cfg = {"enabled": False}

            out = _deepcopy_jsonable(cfg)
            out.setdefault("enabled", False)
            feeds_out[name] = out

        manifest["feeds"] = feeds_out
        # -------- Scheduler quotas --------
        manifest.setdefault("scheduler", {})
        manifest["scheduler"].setdefault("source_quotas", {})

        sq = manifest["scheduler"]["source_quotas"]
        if not isinstance(sq, dict):
            sq = {}
            manifest["scheduler"]["source_quotas"] = sq

        for name, fcfg in feeds_out.items():
            # Don’t force quotas for disabled feeds unless you want it.
            # But having them present is nice for later enabling.
            sq.setdefault(name, int(self.scheduler_quotas.get(name, DEFAULT_SCHED_QUOTAS.get(name, 1))))
        manifest.setdefault("mix", {})
        manifest["mix"].setdefault("weights", {})

        mw = manifest["mix"]["weights"]
        if not isinstance(mw, dict):
            mw = {}
            manifest["mix"]["weights"] = mw

        for name, fcfg in feeds_out.items():
            enabled = bool(fcfg.get("enabled", False))
            if enabled:
                mw.setdefault(name, float(self.mix_weights.get(name, DEFAULT_MIX_WEIGHTS.get(name, 0.0))))
            else:
                mw.setdefault(name, 0.0)



        # -------- Scheduler quotas (optional but nice) --------

        if "scheduler" in manifest:
            manifest["scheduler"]["source_quotas"] = _deepcopy_jsonable(self.scheduler_quotas)

        # -------- Mix --------

        manifest["mix"]["weights"] = _deepcopy_jsonable(self.mix_weights)

        return manifest


    def _finish(self):
        try:
            manifest = self._build_manifest()
        except Exception as e:
            messagebox.showerror("Save station" if self.edit_mode else "Create station", f"Failed to build manifest:\n\n{e}")
            return

        # In edit mode, use existing station_id and path
        if self.edit_mode and self.station:
            station_id = self.station.station_id
            station_dir = self.station.path
        else:
            station_id = (self.var_station_id.get() or "").strip()
            if not station_id:
                messagebox.showerror("Create station", "Station ID is required.")
                return
            station_dir = os.path.join(STATIONS_DIR, station_id)
        
        os.makedirs(station_dir, exist_ok=True)

        out_path = os.path.join(station_dir, "manifest.yaml")

        try:
            with open(out_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(
                    manifest,
                    f,
                    sort_keys=False,
                    allow_unicode=True
                )
        except Exception as e:
            messagebox.showerror("Save station" if self.edit_mode else "Create station", f"Failed to write manifest:\n\n{e}")
            return

        self._result = {"manifest": manifest}
        self.win.destroy()

    def _refresh_preview(self):
        try:
            m = self._build_manifest()
            s = yaml.safe_dump(m, sort_keys=False, allow_unicode=True)
        except Exception as e:
            s = f"Error building manifest:\n{e}"
        self.review_text.config(state="normal")
        self.review_text.delete("1.0", "end")
        self.review_text.insert("1.0", s)
        self.review_text.config(state="disabled")

    # -------------
    # Navigation + validation
    # -------------
    def _sync_nav_buttons(self):
        idx = self.nb.index("current")
        self.btn_back.config(state=("disabled" if idx == 0 else "normal"))
        self.btn_next.config(state=("disabled" if idx == self.nb.index("end") - 1 else "normal"))

        # Keep preview fresh on review tab
        if idx == (self.nb.index("end") - 1):
            self._refresh_preview()

    def _go_back(self):
        idx = self.nb.index("current")
        if idx > 0:
            self.nb.select(idx - 1)

    def _go_next(self):
        idx = self.nb.index("current")
        if not self._validate_step(idx):
            return
        end = self.nb.index("end") - 1
        if idx < end:
            self.nb.select(idx + 1)

    def _cancel(self):
        self._result = None
        self.win.destroy()

    def _validate_step(self, idx: int) -> bool:
        # 0 basics
        if idx == 0:
            sid = (self.var_station_id.get() or "").strip()
            if not sid:
                messagebox.showerror("Station", "Station ID is required.")
                return False
            # folder safe-ish
            bad = any(c in sid for c in r'\/:*?"<>|')
            if bad:
                messagebox.showerror("Station", "Station ID contains invalid filename characters.")
                return False

            self.station_id = sid
            self.station_name = (self.var_station_name.get() or sid).strip()
            self.station_host = (self.var_station_host.get() or "Kai").strip()
            self.station_category = (self.var_station_cat.get() or "Custom").strip()
            self.station_logo = (self.var_station_logo.get() or "").strip()

            self.llm_endpoint = (self.var_llm_endpoint.get() or "").strip()
            self.model_producer = (self.var_model_producer.get() or "").strip()
            self.model_host = (self.var_model_host.get() or "").strip()
            return True

        # Characters step: ensure host exists (no hard max)
        if idx == 2:
            if "host" not in self.characters:
                messagebox.showerror("Characters", "Host character is required.")
                return False
            return True

        # 3 voices: store piper + voices
        if idx == 3:
            # capture piper bin
            self.piper_bin = (self.var_piper_bin.get() or "").strip()

            # capture per-character voices (ALL of them)
            if hasattr(self, "voice_vars") and isinstance(self.voice_vars, dict):
                for k, var in self.voice_vars.items():
                    try:
                        self.voices[k] = (var.get() or "").strip()
                    except Exception:
                        self.voices[k] = ""

            # optional: if characters changed since voices tab was built, keep map stable
            # remove stale keys (characters removed)
            for k in list(self.voices.keys()):
                if k not in self.characters:
                    self.voices.pop(k, None)

            return True

        return True

    # -------------
    # Utility
    # -------------
    def _build_manifest_preview_only(self) -> str:
        m = self._build_manifest()
        return yaml.safe_dump(m, sort_keys=False, allow_unicode=True)

# -----------------------------
# Station Editor Window
# -----------------------------
class EditorWindow:
    def __init__(self, shell: RadioShell, station: StationInfo):
        self.shell = shell
        self.station = station
        self.path = station.path
        self.mp = station_manifest_path(self.path)

        self.cfg = safe_read_yaml(self.mp)

        self.win = tk.Toplevel(shell.root)
        self.win.title(f"Edit Station — {station.station_id}")
        self.win.geometry(scaled_geometry(980, 720))
        self.win.configure(bg=UI["bg"])
        self.win.grab_set()

        self.nb = ttk.Notebook(self.win)
        self.nb.pack(fill="both", expand=True, padx=12, pady=12)

        self.tab_station   = tk.Frame(self.nb, bg=UI["bg"])
        self.tab_models    = tk.Frame(self.nb, bg=UI["bg"])
        self.tab_scheduler = tk.Frame(self.nb, bg=UI["bg"])
        self.tab_riff      = tk.Frame(self.nb, bg=UI["bg"])
        self.tab_pacing    = tk.Frame(self.nb, bg=UI["bg"])
        self.tab_producer  = tk.Frame(self.nb, bg=UI["bg"])
        self.tab_host      = tk.Frame(self.nb, bg=UI["bg"])
        self.tab_tts       = tk.Frame(self.nb, bg=UI["bg"])
        self.tab_feeds     = tk.Frame(self.nb, bg=UI["bg"])
        self.tab_chars     = tk.Frame(self.nb, bg=UI["bg"])

        self.nb.add(self.tab_station, text="Station")
        self.nb.add(self.tab_models, text="Models & Audio")
        self.nb.add(self.tab_scheduler, text="Scheduler")
        self.nb.add(self.tab_riff, text="Riff Engine")
        self.nb.add(self.tab_pacing, text="Pacing")
        self.nb.add(self.tab_producer, text="Producer")
        self.nb.add(self.tab_host, text="Host")
        self.nb.add(self.tab_tts, text="TTS")
        self.nb.add(self.tab_feeds, text="Feeds")
        self.nb.add(self.tab_chars, text="Characters")

        # dynamic var store (path_key -> {field->Var})
        self._dynamic_vars: Dict[str, Dict[str, tk.Variable]] = {}

        self._build_station_tab()
        self._build_models_tab()
        self._build_dynamic_section(self.tab_scheduler, ["scheduler"], "Scheduler")
        self._build_dynamic_section(self.tab_riff, ["riff"], "Riff Engine")
        self._build_dynamic_section(self.tab_pacing, ["pacing"], "Pacing")
        self._build_dynamic_section(self.tab_producer, ["producer"], "Producer")
        self._build_dynamic_section(self.tab_host, ["host"], "Host")
        self._build_dynamic_section(self.tab_tts, ["tts"], "TTS Anti-spam")
        self._build_feeds_tab()
        self._build_chars_tab()
        self._build_footer()

    def _cfg_get(self, path: List[str], default=None):
        cur: Any = self.cfg
        for p in path:
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
        return cur

    def _cfg_set(self, path: List[str], value):
        cur = self.cfg
        for p in path[:-1]:
            if p not in cur or not isinstance(cur[p], dict):
                cur[p] = {}
            cur = cur[p]
        cur[path[-1]] = value

    def _build_dynamic_section(self, parent, section_path: List[str], title: str):
        wrap = tk.Frame(parent, bg=UI["bg"])
        wrap.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(wrap, text=title, font=FONT_H2, fg=UI["text"], bg=UI["bg"]).pack(anchor="w", pady=(0, 12))

        section = self._cfg_get(section_path, {})
        if not isinstance(section, dict):
            section = {}

        keybase = ".".join(section_path)
        self._dynamic_vars[keybase] = {}

        # keep stable order
        for key in sorted(section.keys()):
            val = section[key]
            row = tk.Frame(wrap, bg=UI["bg"])
            row.pack(fill="x", pady=6)

            tk.Label(row, text=key, fg=UI["muted"], bg=UI["bg"], width=24, anchor="w").pack(side="left")

            # bool
            if isinstance(val, bool):
                v = tk.BooleanVar(value=val)
                tk.Checkbutton(row, variable=v, bg=UI["bg"], fg=UI["text"], selectcolor=UI["bg"]).pack(side="left")
                self._dynamic_vars[keybase][key] = v
                continue

            # list
            if isinstance(val, list):
                v = tk.StringVar(value=json.dumps(val, ensure_ascii=False))
                ent = tk.Entry(row, textvariable=v, bg=UI["surface"], fg=UI["text"], insertbackground=UI["text"])
                ent.pack(fill="x", expand=True)
                self._dynamic_vars[keybase][key] = v
                continue

            # scalar
            v = tk.StringVar(value=str(val))
            ent = tk.Entry(row, textvariable=v, bg=UI["surface"], fg=UI["text"], insertbackground=UI["text"])
            ent.pack(fill="x", expand=True)
            self._dynamic_vars[keybase][key] = v

    def _row_entry(self, parent, row: int, label: str, var: tk.StringVar, width: int = 32,
                   browse: bool = False, browse_kind: str = "file"):
        tk.Label(parent, text=label, font=FONT_BODY, fg=UI["muted"], bg=UI["bg"]).grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=4
        )

        ent = tk.Entry(parent, textvariable=var, font=FONT_BODY,
                       bg=UI["surface"], fg=UI["text"], insertbackground=UI["text"], width=width)
        ent.grid(row=row, column=1, sticky="ew", pady=4)

        if browse:
            def do_browse():
                p = filedialog.askopenfilename() if browse_kind == "file" else filedialog.askdirectory()
                if p:
                    var.set(p)
            tk.Button(parent, text="Browse", font=FONT_BODY, bg=UI["panel"], fg=UI["text"], relief="flat", command=do_browse).grid(
                row=row, column=2, padx=6
            )

    # -----------------------------
    # Tabs
    # -----------------------------
    def _build_station_tab(self):
        wrap = tk.Frame(self.tab_station, bg=UI["bg"])
        wrap.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(wrap, text="Station Metadata", font=FONT_H2, fg=UI["text"], bg=UI["bg"]).grid(
            row=0, column=0, sticky="w", pady=(0, 10), columnspan=2
        )

        self.var_name = tk.StringVar(value=str(self._cfg_get(["station", "name"], self.station.station_id)))
        self.var_host = tk.StringVar(value=str(self._cfg_get(["station", "host"], "Kai")))
        self.var_cat  = tk.StringVar(value=str(self._cfg_get(["station", "category"], "Custom")))
        self.var_logo = tk.StringVar(value=str(self._cfg_get(["station", "logo"], "")))

        self._row_entry(wrap, 1, "Name", self.var_name)
        self._row_entry(wrap, 2, "Host", self.var_host)
        self._row_entry(wrap, 3, "Category", self.var_cat)
        self._row_entry(wrap, 4, "Logo Art", self.var_logo, browse=True, browse_kind="file")

        wrap.grid_columnconfigure(1, weight=1)

        # Add Save button for station settings
        btn_row = tk.Frame(wrap, bg=UI["bg"])
        btn_row.grid(row=5, column=0, columnspan=2, sticky="e", pady=(16, 0))
        tk.Button(
            btn_row,
            text="Save Settings",
            font=FONT_BODY,
            bg=UI["accent"],
            fg="#000",
            relief="flat",
            command=self._quick_save_station_settings
        ).pack(side="right", padx=6)
    def _quick_save_station_settings(self):
        """Save only station metadata (name, host, category, logo) without touching other config."""
        self._cfg_set(["station", "name"], self.var_name.get())
        self._cfg_set(["station", "host"], self.var_host.get())
        self._cfg_set(["station", "category"], self.var_cat.get())
        self._cfg_set(["station", "logo"], self.var_logo.get())
        self._write_manifest()
        messagebox.showinfo("Success", "Station settings saved!")

    def _build_models_tab(self):
        wrap = tk.Frame(self.tab_models, bg=UI["bg"])
        wrap.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(wrap, text="LLM / Models", font=FONT_H2, fg=UI["text"], bg=UI["bg"]).grid(
            row=0, column=0, sticky="w", pady=(0, 10), columnspan=3
        )

        self.var_endpoint   = tk.StringVar(value=str(self._cfg_get(["llm", "endpoint"], "")))
        self.var_model_host = tk.StringVar(value=str(self._cfg_get(["models", "host"], "")))
        self.var_model_prod = tk.StringVar(value=str(self._cfg_get(["models", "producer"], "")))
        self.var_model_char_mgr = tk.StringVar(value=str(self._cfg_get(["models", "character_manager"], "")))
        
        # Detect provider from existing config
        endpoint = self._cfg_get(["llm", "endpoint"], "")
        provider = "ollama"
        if "anthropic" in str(endpoint).lower() or "claude" in str(self._cfg_get(["models", "host"], "")).lower():
            provider = "anthropic"
        elif "openai" in str(endpoint).lower() or "gpt" in str(self._cfg_get(["models", "host"], "")).lower():
            provider = "openai"
        elif "google" in str(endpoint).lower() or "gemini" in str(self._cfg_get(["models", "host"], "")).lower():
            provider = "google"
        
        self.var_provider = tk.StringVar(value=provider)

        # Provider selector
        tk.Label(wrap, text="LLM Provider", font=FONT_BODY, fg=UI["muted"], bg=UI["bg"]).grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=4
        )
        provider_combo = ttk.Combobox(
            wrap, textvariable=self.var_provider,
            values=["ollama", "anthropic", "openai", "google"],
            state="readonly", width=30
        )
        provider_combo.grid(row=1, column=1, sticky="ew", pady=4)
        
        # Endpoint row
        endpoint_label = tk.Label(wrap, text="Endpoint / API", font=FONT_BODY, fg=UI["muted"], bg=UI["bg"])
        endpoint_label.grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        
        tk.Entry(wrap, textvariable=self.var_endpoint, bg=UI["surface"], fg=UI["text"],
                insertbackground=UI["text"], width=60).grid(row=2, column=1, sticky="ew", pady=4)
        
        hint_text = "Ollama: http://localhost:11434  |  Others: Set env var"
        tk.Label(wrap, text=hint_text, font=FONT_SMALL, fg=UI["muted"], bg=UI["bg"]).grid(
            row=2, column=2, sticky="w", padx=(10, 0)
        )
        
        self._row_entry(wrap, 3, "Host model", self.var_model_host, width=60)
        self._row_entry(wrap, 4, "Producer model", self.var_model_prod, width=60)
        self._row_entry(wrap, 5, "Character Manager model", self.var_model_char_mgr, width=60)

        ttk.Separator(wrap, orient="horizontal").grid(row=6, column=0, columnspan=3, sticky="ew", pady=12)

        # Visual Models section
        tk.Label(wrap, text="Vision Model (Optional)", font=FONT_H2, fg=UI["text"], bg=UI["bg"]).grid(
            row=7, column=0, sticky="w", pady=(0, 10), columnspan=3
        )

        # Load visual model config from manifest or global settings
        vis_cfg = self._cfg_get(["visual_models"], {})
        if not isinstance(vis_cfg, dict) or not vis_cfg:
            global_cfg = get_global_config()
            vis_cfg = global_cfg.get("visual_models", {})

        self.var_vis_model_type = tk.StringVar(value=vis_cfg.get("model_type", "local"))
        self.var_vis_model_local = tk.StringVar(value=vis_cfg.get("local_model", ""))
        self.var_vis_model_api_provider = tk.StringVar(value=vis_cfg.get("api_provider", "openai"))
        self.var_vis_model_api_model = tk.StringVar(value=vis_cfg.get("api_model", "gpt-4-vision"))
        self.var_vis_model_max_size = tk.StringVar(value=vis_cfg.get("max_image_size", "1024"))

        # Model type selection
        tk.Label(wrap, text="Model Type", font=FONT_BODY, fg=UI["muted"], bg=UI["bg"]).grid(
            row=8, column=0, sticky="w", padx=(0, 10), pady=4
        )
        type_frame = tk.Frame(wrap, bg=UI["bg"])
        type_frame.grid(row=8, column=1, sticky="w", pady=4, columnspan=2)

        tk.Radiobutton(type_frame, text="Local", variable=self.var_vis_model_type, value="local",
                       fg=UI["text"], bg=UI["bg"], selectcolor=UI["accent"]).pack(side="left", padx=8)
        tk.Radiobutton(type_frame, text="API", variable=self.var_vis_model_type, value="api",
                       fg=UI["text"], bg=UI["bg"], selectcolor=UI["accent"]).pack(side="left", padx=8)

        self._row_entry(wrap, 9, "Local model", self.var_vis_model_local, width=60)
        self._row_entry(wrap, 10, "API provider", self.var_vis_model_api_provider, width=60)
        self._row_entry(wrap, 11, "API model", self.var_vis_model_api_model, width=60)
        self._row_entry(wrap, 12, "Max image width", self.var_vis_model_max_size, width=60)
        
        # Quick save button for visual models
        vis_btn_row = tk.Frame(wrap, bg=UI["bg"])
        vis_btn_row.grid(row=12, column=2, sticky="e", pady=(8, 4))
        tk.Button(vis_btn_row, text="Save", bg=UI["accent"], fg="#000", relief="flat",
                 command=self._quick_save_visual_models, font=FONT_SMALL).pack()

        ttk.Separator(wrap, orient="horizontal").grid(row=13, column=0, columnspan=3, sticky="ew", pady=12)

        tk.Label(wrap, text="Audio / Voices", font=FONT_H2, fg=UI["text"], bg=UI["bg"]).grid(
            row=14, column=0, sticky="w", pady=(0, 10), columnspan=3
        )

        self.var_piper = tk.StringVar(value=str(self._cfg_get(["audio", "piper_bin"], "")))
        self._row_entry(wrap, 15, "Piper binary", self.var_piper, width=60, browse=True, browse_kind="file")

        voices = self._cfg_get(["voices"], {})
        if not isinstance(voices, dict):
            voices = {}

        # explicit keys matching your manifest
        chars = self._cfg_get(["characters"], {})
        if not isinstance(chars, dict):
            chars = {}

        voice_keys = sorted(chars.keys())

        self.voice_vars: Dict[str, tk.StringVar] = {}
        r = 16
        for k in voice_keys:
            v = tk.StringVar(value=str(voices.get(k, "")))
            self.voice_vars[k] = v
            self._row_entry(wrap, r, f"Voice: {k}", v, width=60, browse=True, browse_kind="file")
            r += 1

        wrap.grid_columnconfigure(1, weight=1)

    def _build_feeds_tab(self):
        wrap = tk.Frame(self.tab_feeds, bg=UI["bg"])
        wrap.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(
            wrap, text="Feeds",
            font=FONT_H2, fg=UI["text"], bg=UI["bg"]
        ).pack(anchor="w", pady=(0, 10))

        feeds = self._cfg_get(["feeds"], {})
        if not isinstance(feeds, dict):
            feeds = {}

        nb = ttk.Notebook(wrap)
        nb.pack(fill="both", expand=True)

        for fname in sorted(feeds.keys()):
            feed_cfg = feeds[fname]
            if not isinstance(feed_cfg, dict):
                feed_cfg = {}

            tab = tk.Frame(nb, bg=UI["bg"])
            nb.add(tab, text=fname)

            body = tk.Frame(tab, bg=UI["bg"])
            body.pack(fill="both", expand=True, padx=14, pady=14)

            # ==========================
            # ENABLED TOGGLE
            # ==========================

            enabled = bool(feed_cfg.get("enabled", False))
            v_en = tk.BooleanVar(value=enabled)

            row = tk.Frame(body, bg=UI["bg"])
            row.pack(anchor="w", pady=6)

            tk.Checkbutton(
                row,
                text="Enabled",
                variable=v_en,
                bg=UI["bg"], fg=UI["text"],
                selectcolor=UI["bg"]
            ).pack(side="left")

            # dynamic storage for this feed
            keybase = f"feeds.{fname}"
            self._dynamic_vars[keybase] = {"enabled": v_en}

            # ==========================
            # EXISTING FIELDS
            # ==========================

            for k, v in feed_cfg.items():
                if k == "enabled":
                    continue

                line = tk.Frame(body, bg=UI["bg"])
                line.pack(fill="x", pady=6)

                tk.Label(
                    line, text=k,
                    fg=UI["muted"], bg=UI["bg"],
                    width=22, anchor="w"
                ).pack(side="left")

                if isinstance(v, list):
                    sv = tk.StringVar(value=json.dumps(v, ensure_ascii=False))
                else:
                    sv = tk.StringVar(value=str(v))

                ent = tk.Entry(
                    line,
                    textvariable=sv,
                    bg=UI["surface"], fg=UI["text"],
                    insertbackground=UI["text"]
                )
                ent.pack(fill="x", expand=True)

                self._dynamic_vars[keybase][k] = sv

            # ==========================
            # ADD NEW FIELD UI
            # ==========================

            ttk.Separator(body, orient="horizontal").pack(fill="x", pady=14)

            add_row = tk.Frame(body, bg=UI["bg"])
            add_row.pack(fill="x", pady=(6, 4))

            new_key = tk.StringVar()
            new_val = tk.StringVar()

            tk.Entry(
                add_row,
                textvariable=new_key,
                bg=UI["surface"], fg=UI["text"],
                insertbackground=UI["text"],
                width=22
            ).pack(side="left", padx=(0, 6))

            tk.Entry(
                add_row,
                textvariable=new_val,
                bg=UI["surface"], fg=UI["text"],
                insertbackground=UI["text"]
            ).pack(side="left", fill="x", expand=True, padx=(0, 6))

            def add_field(fname=fname, k_var=new_key, v_var=new_val, body_ref=body):
                k = (k_var.get() or "").strip()
                raw = (v_var.get() or "").strip()

                if not k:
                    return

                keybase = f"feeds.{fname}"

                # Smart parse YAML/JSON
                try:
                    parsed = yaml.safe_load(raw)
                except Exception:
                    parsed = raw

                if isinstance(parsed, list):
                    sv = tk.StringVar(value=json.dumps(parsed, ensure_ascii=False))
                else:
                    sv = tk.StringVar(value=str(parsed))

                # New visual row
                line = tk.Frame(body_ref, bg=UI["bg"])
                line.pack(fill="x", pady=6)

                tk.Label(
                    line, text=k,
                    fg=UI["muted"], bg=UI["bg"],
                    width=22, anchor="w"
                ).pack(side="left")

                ent = tk.Entry(
                    line,
                    textvariable=sv,
                    bg=UI["surface"], fg=UI["text"],
                    insertbackground=UI["text"]
                )
                ent.pack(fill="x", expand=True)

                self._dynamic_vars[keybase][k] = sv

                k_var.set("")
                v_var.set("")

            tk.Button(
                add_row,
                text="Add Field",
                bg=UI["panel"], fg=UI["accent"],
                relief="flat",
                command=add_field
            ).pack(side="left")


    def _build_chars_tab(self):
        wrap = tk.Frame(self.tab_chars, bg=UI["bg"])
        wrap.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(
            wrap, text="Characters",
            font=FONT_H2, fg=UI["text"], bg=UI["bg"]
        ).pack(anchor="w", pady=(0, 10))

        body = tk.Frame(wrap, bg=UI["bg"])
        body.pack(fill="both", expand=True)

        # ============================
        # LEFT PANEL (LIST + BUTTONS)
        # ============================

        left = tk.Frame(body, bg=UI["panel"], width=int(240 * UI_SCALE))
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        self.char_list = tk.Listbox(
            left,
            bg=UI["surface"],
            fg=UI["text"],
            font=FONT_BODY,
            relief="flat",
            exportselection=False
        )
        self.char_list.pack(fill="both", expand=True, padx=10, pady=10)

        btns = tk.Frame(left, bg=UI["panel"])
        btns.pack(fill="x", padx=10, pady=(0, 10))

        tk.Button(
            btns, text="Add",
            bg=UI["panel"], fg=UI["text"], relief="flat",
            command=self._char_add_safe
        ).pack(side="left", padx=4)

        tk.Button(
            btns, text="Remove",
            bg=UI["panel"], fg=UI["danger"], relief="flat",
            command=self._char_remove_safe
        ).pack(side="left", padx=4)

        tk.Button(
            btns, text="Load Preset",
            bg=UI["panel"], fg=UI["accent"], relief="flat",
            command=self._load_character_preset
        ).pack(side="left", padx=4)

        # ============================
        # LOAD EXISTING CHARACTERS
        # ============================

        chars = self._cfg_get(["characters"], {})
        if not isinstance(chars, dict):
            chars = {}

        self._chars = chars

        self.char_list.delete(0, "end")
        for k in sorted(self._chars.keys()):
            self.char_list.insert("end", k)

        self.char_list.bind("<<ListboxSelect>>", self._char_load_selected_safe)

        # ============================
        # RIGHT PANEL (EDITOR)
        # ============================

        right = tk.Frame(body, bg=UI["bg"])
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))

        self.var_char_role   = tk.StringVar()
        self.var_char_traits = tk.StringVar()
        self.var_char_focus  = tk.StringVar()

        tk.Label(right, text="Role", fg=UI["muted"], bg=UI["bg"]).pack(anchor="w")
        tk.Entry(
            right, textvariable=self.var_char_role,
            bg=UI["surface"], fg=UI["text"],
            insertbackground=UI["text"]
        ).pack(fill="x", pady=(0, 10))

        tk.Label(right, text="Traits (list)", fg=UI["muted"], bg=UI["bg"]).pack(anchor="w")
        tk.Entry(
            right, textvariable=self.var_char_traits,
            bg=UI["surface"], fg=UI["text"],
            insertbackground=UI["text"]
        ).pack(fill="x", pady=(0, 10))

        tk.Label(right, text="Focus (list)", fg=UI["muted"], bg=UI["bg"]).pack(anchor="w")
        tk.Entry(
            right, textvariable=self.var_char_focus,
            bg=UI["surface"], fg=UI["text"],
            insertbackground=UI["text"]
        ).pack(fill="x", pady=(0, 10))
        
        # ---- Context Engine UI ----
        
        from context_engine_ui import build_context_engine_ui
        
        # Store context engine config per character
        if not hasattr(self, "_char_context_engines"):
            self._char_context_engines = {}
        
        def get_context_cfg():
            sel = self.char_list.curselection()
            if not sel:
                return {}
            key = self.char_list.get(sel[0])
            return self._char_context_engines.get(key, {})
        
        def set_context_cfg(cfg):
            sel = self.char_list.curselection()
            if sel:
                key = self.char_list.get(sel[0])
                self._char_context_engines[key] = cfg
        
        self.context_engine_frame = build_context_engine_ui(
            parent=right,
            bg=UI["bg"],
            surface=UI["surface"],
            text_color=UI["text"],
            muted=UI["muted"],
            accent=UI["accent"],
            get_context_cfg_func=get_context_cfg,
            set_context_cfg_func=set_context_cfg,
            station_dir=self.station_dir
        )
        self.context_engine_frame.pack(fill="x", pady=10)

        tk.Button(
            right,
            text="Apply Changes",
            bg=UI["accent"], fg="#000", relief="flat",
            command=self._char_apply_safe
        ).pack(anchor="w", pady=10)

        # ============================
        # AUTO SELECT FIRST
        # ============================

        if self.char_list.size() > 0:
            self.char_list.selection_set(0)
            self._char_load_selected_safe()

    # -----------------------------
    # Character ops
    # -----------------------------
    def _load_character_preset(self):
        win = tk.Toplevel(self.win)
        win.title("Load Character Preset")
        win.geometry(scaled_geometry(320, 340))
        win.configure(bg=UI["bg"])
        win.grab_set()

        tk.Label(
            win, text="Choose preset",
            fg=UI["text"], bg=UI["bg"],
            font=FONT_BODY
        ).pack(pady=10)

        lb = tk.Listbox(
            win,
            bg=UI["surface"],
            fg=UI["text"],
            font=FONT_BODY,
            relief="flat"
        )
        lb.pack(fill="both", expand=True, padx=12, pady=6)

        for name in CHARACTER_PRESETS.keys():
            lb.insert("end", name)

        def load():
            sel = lb.curselection()
            if not sel:
                return

            preset_name = lb.get(sel[0])
            preset = CHARACTER_PRESETS[preset_name]

            if not messagebox.askyesno(
                "Overwrite Characters",
                f"Load '{preset_name}' preset?\n\nThis will replace current characters."
            ):
                return

            # Inject
            self._chars.clear()
            self._chars.update(json.loads(json.dumps(preset)))  # deep copy

            # Refresh list UI
            self.char_list.delete(0, "end")
            for k in sorted(self._chars.keys()):
                self.char_list.insert("end", k)

            if self.char_list.size() > 0:
                self.char_list.selection_set(0)
                self._char_load_selected_safe()

            win.destroy()

        tk.Button(
            win, text="Load",
            bg=UI["accent"], fg="#000", relief="flat",
            command=load
        ).pack(pady=10)

    def _char_selected_key(self):
        sel = self.char_list.curselection()
        if not sel:
            return None
        return self.char_list.get(sel[0])


    def _char_load_selected_safe(self, evt=None):
        key = self._char_selected_key()
        if not key:
            return

        c = self._chars.get(key, {})
        if not isinstance(c, dict):
            return

        self.var_char_role.set(str(c.get("role", "")))
        self.var_char_traits.set(json.dumps(c.get("traits", []), ensure_ascii=False))
        self.var_char_focus.set(json.dumps(c.get("focus", []), ensure_ascii=False))
        
        # Load context engine config
        if hasattr(self, "context_engine_frame"):
            context_cfg = c.get("context_engine", {})
            self.context_engine_frame.load_config(context_cfg)
            if hasattr(self, "_char_context_engines"):
                self._char_context_engines[key] = context_cfg


    def _char_add_safe(self):
        name = self.shell._prompt_text("Add character", "Character key (e.g. analyst):")
        if not name:
            return

        name = name.strip().lower()

        if not name or name in self._chars:
            return

        self._chars[name] = {
            "role": name,
            "traits": [],
            "focus": []
        }

        self.char_list.insert("end", name)
        self.char_list.selection_clear(0, "end")
        self.char_list.selection_set("end")
        self._char_load_selected_safe()


    def _char_remove_safe(self):
        key = self._char_selected_key()
        if not key:
            return

        if key == "host":
            messagebox.showerror("Not allowed", "Host cannot be removed.")
            return

        if not messagebox.askyesno("Remove", f"Remove '{key}'?"):
            return

        idx = self.char_list.curselection()[0]

        self._chars.pop(key, None)
        self.char_list.delete(idx)

        if self.char_list.size() > 0:
            self.char_list.selection_set(0)
            self._char_load_selected_safe()


    def _char_apply_safe(self):
        key = self._char_selected_key()
        if not key:
            return

        try:
            role = self.var_char_role.get().strip()

            traits = parse_list_field(self.var_char_traits.get())
            focus  = parse_list_field(self.var_char_focus.get())

            # HARD GUARANTEE list type
            if not isinstance(traits, list):
                traits = []

            if not isinstance(focus, list):
                focus = []

            # Get context engine config
            context_engine = {}
            if hasattr(self, "context_engine_frame"):
                context_engine = self.context_engine_frame.get_config()
                if hasattr(self, "_char_context_engines"):
                    self._char_context_engines[key] = context_engine

            self._chars[key] = {
                "role": role,
                "traits": traits,
                "focus": focus
            }
            
            # Add context_engine if enabled
            if context_engine.get("enabled"):
                self._chars[key]["context_engine"] = context_engine


        except Exception as e:
            messagebox.showerror(
                "Character Error",
                f"Invalid traits/focus format.\n\n{e}\n\nUse JSON list like:\n[\"calm\", \"smart\"]"
            )

    def _select_list_item(self, key: str):
        for i in range(self.char_list.size()):
            if self.char_list.get(i) == key:
                self.char_list.selection_clear(0, "end")
                self.char_list.selection_set(i)
                self.char_list.see(i)
                self._char_load_selected_safe()  # FIX: correct method
                return


    def _char_apply(self):
        key = self._char_selected_key()
        if not key:
            return

        role = (self.var_char_role.get() or "").strip()
        traits = parse_list_field(self.var_char_traits.get())
        focus = parse_list_field(self.var_char_focus.get())

        self._chars[key] = {"role": role, "traits": traits, "focus": focus}
        messagebox.showinfo("Saved", f"{key} updated.")

    # -----------------------------
    # Footer
    # -----------------------------
    def _build_footer(self):
        footer = tk.Frame(self.win, bg=UI["bg"])
        footer.pack(fill="x", padx=12, pady=(0, 12))

        tk.Button(footer, text="Save", font=FONT_BODY, bg=UI["accent"], fg="#000", relief="flat", command=self.save).pack(
            side="right", padx=6
        )
        tk.Button(footer, text="Close", font=FONT_BODY, bg=UI["panel"], fg=UI["text"], relief="flat", command=self.win.destroy).pack(
            side="right", padx=6
        )
        tk.Button(footer, text="Duplicate Station…", font=FONT_BODY, bg=UI["panel"], fg=UI["text"], relief="flat", command=self.duplicate_station).pack(
            side="left", padx=6
        )
        tk.Button(footer, text="Open Folder…", font=FONT_BODY, bg=UI["panel"], fg=UI["text"], relief="flat", command=self.open_folder).pack(
            side="left", padx=6
        )

    def open_folder(self):
        try:
            if sys.platform == "win32":
                os.startfile(self.path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.path])
            else:
                subprocess.Popen(["xdg-open", self.path])
        except Exception:
            pass

    def _quick_save_visual_models(self):
        """Save only visual model settings without touching other config."""
        self._cfg_set(["visual_models", "model_type"], self.var_vis_model_type.get())
        self._cfg_set(["visual_models", "local_model"], self.var_vis_model_local.get())
        self._cfg_set(["visual_models", "api_provider"], self.var_vis_model_api_provider.get())
        self._cfg_set(["visual_models", "api_model"], self.var_vis_model_api_model.get())
        self._cfg_set(["visual_models", "max_image_size"], self.var_vis_model_max_size.get())
        
        self._write_manifest()
        messagebox.showinfo("Success", "Visual model settings saved!")
    
    def _write_manifest(self):
        """Write the manifest to disk."""
        try:
            with open(self.mp, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.cfg, f, sort_keys=False, allow_unicode=True)
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to write manifest: {e}")

    def duplicate_station(self):
        new_id = self.shell._prompt_text("Duplicate Station", "New station id:")
        if not new_id:
            return
        new_id = new_id.strip()
        if not new_id:
            return

        dst = os.path.join(STATIONS_DIR, new_id)
        if os.path.exists(dst):
            messagebox.showerror("Exists", "That station id already exists.")
            return

        shutil.copytree(self.path, dst)
        self.shell.refresh_stations(select_id=new_id)

    # -----------------------------
    # Save manifest (FULL FIX: do not wipe feeds/pacing, no missing vars)
    # -----------------------------
    def save(self):
        # Station metadata
        self._cfg_set(["station", "name"], self.var_name.get())
        self._cfg_set(["station", "host"], self.var_host.get())
        self._cfg_set(["station", "category"], self.var_cat.get())
        self._cfg_set(["station", "logo"], self.var_logo.get())

        # LLM / models
        self._cfg_set(["llm", "endpoint"], self.var_endpoint.get())
        self._cfg_set(["llm", "provider"], self.var_provider.get())
        self._cfg_set(["models", "host"], self.var_model_host.get())
        self._cfg_set(["models", "producer"], self.var_model_prod.get())
        self._cfg_set(["models", "character_manager"], self.var_model_char_mgr.get())

        # Visual Models
        self._cfg_set(["visual_models", "model_type"], self.var_vis_model_type.get())
        self._cfg_set(["visual_models", "local_model"], self.var_vis_model_local.get())
        self._cfg_set(["visual_models", "api_provider"], self.var_vis_model_api_provider.get())
        self._cfg_set(["visual_models", "api_model"], self.var_vis_model_api_model.get())
        self._cfg_set(["visual_models", "max_image_size"], self.var_vis_model_max_size.get())

        # Audio / voices
        self._cfg_set(["audio", "piper_bin"], self.var_piper.get())
        self.cfg.setdefault("voices", {})
        if not isinstance(self.cfg.get("voices"), dict):
            self.cfg["voices"] = {}
        for k, v in self.voice_vars.items():
            self.cfg["voices"][k] = v.get()

        # Characters edited in-place
        self.cfg["characters"] = self._chars

        # Dynamic sections merge (scheduler/riff/pacing/producer/host/tts/feeds.*)
        for keybase, fields in self._dynamic_vars.items():
            path = keybase.split(".")
            current = self._cfg_get(path, {})
            if not isinstance(current, dict):
                current = {}

            for k, var in fields.items():
                # booleans
                if isinstance(var, tk.BooleanVar):
                    current[k] = bool(var.get())
                    continue

                raw = str(var.get() or "").strip()

                # Detect original type if present
                try:
                    orig = self._cfg_get(path + [k], None)
                except Exception:
                    orig = None

                # If it USED to be a list, force list parse
                if isinstance(orig, list):
                    current[k] = parse_list_field(raw)
                    continue

                # If user typed a list-looking thing for a NEW field, parse as list too
                # - starts with [ ... ]  (JSON/YAML list)
                # - or contains commas and no obvious dict/brace structure
                looks_like_list = (
                    (raw.startswith("[") and raw.endswith("]")) or
                    ("," in raw and not any(ch in raw for ch in "{}:"))
                )
                if looks_like_list:
                    current[k] = parse_list_field(raw)
                    continue

                # Otherwise YAML/JSON scalar parse
                if raw == "":
                    current[k] = ""
                    continue

                try:
                    v = yaml.safe_load(raw)
                    current[k] = v
                except Exception:
                    current[k] = parse_scalar_field(raw)

            self._cfg_set(path, current)

        # Write manifest
        safe_write_yaml(self.mp, self.cfg)

        # Refresh shell UI
        self.shell.refresh_stations(select_id=self.station.station_id)


# -----------------------------
# Entrypoint
# -----------------------------
if __name__ == "__main__":
    RadioShell().run()
