
import time
import threading
import math
import random
from typing import Any, Dict, Optional

try:
    import numpy as np
    import sounddevice as sd
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False

PLUGIN_NAME = "radio_dial"
IS_FEED = False

def register_widgets(registry, runtime):
    tk = runtime["tk"]
    def factory(parent, rt):
        return RadioDialWidget(parent, rt).root
    registry.register("radio_dial", factory, title="Radio • Dial", default_panel="left")

class RadioDialWidget:
    def __init__(self, parent, runtime):
        self.tk = runtime["tk"]
        self.runtime = runtime
        self.ui_cmd_q = runtime.get("ui_cmd_q")
        if self.ui_cmd_q is None:
            try:
                from runtime import ui_cmd_q as _q
                self.ui_cmd_q = _q
            except Exception:
                self.ui_cmd_q = None

        self.root = self.tk.Frame(parent, bg="#0e0e0e")
        
        # Audio state
        self.static_playing = False
        self.static_thread = None
        self.stop_static_event = threading.Event()
        
        # Tuning state
        self.tune_timer = None

        # Styles
        self.bg = "#0e0e0e"
        self.fg = "#e8e8e8"
        self.accent = "#4cc9f0"
        
        self._setup_ui()
        self._scan_stations()
        
        # Set dial to current station
        self._set_current_station_index()

    def _setup_ui(self):
        # Header
        hdr = self.tk.Frame(self.root, bg="#121212", highlightthickness=1, highlightbackground="#2a2a2a")
        hdr.pack(fill="x", padx=10, pady=(10, 8))
        self.tk.Label(hdr, text="RADIO DIAL", fg=self.accent, bg="#121212", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        self.status_lbl = self.tk.Label(hdr, text="tuning...", fg="#9a9a9a", bg="#121212", font=("Segoe UI", 9))
        self.status_lbl.pack(anchor="w", padx=10, pady=(0, 8))

        # Main Body
        body = self.tk.Frame(self.root, bg=self.bg)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Tuner Area
        tuner_frame = self.tk.Frame(body, bg="#181818", highlightthickness=1, highlightbackground="#333")
        tuner_frame.pack(fill="x", pady=(10, 15))

        self.tk.Label(tuner_frame, text="FREQUENCY", fg="#888", bg="#181818", font=("Segoe UI", 8, "bold")).pack(anchor="n", pady=(8,0))
        
        self.station_name_lbl = self.tk.Label(tuner_frame, text="---", fg="#fff", bg="#181818", font=("Segoe UI", 14, "bold"))
        self.station_name_lbl.pack(anchor="n", pady=(2, 6))

        # The Dial
        self.dial_var = self.tk.DoubleVar()
        self.dial = self.tk.Scale(
            tuner_frame, 
            variable=self.dial_var,
            orient="horizontal",
            showvalue=False,
            from_=0, to=100, # Will update range
            command=self._on_dial_drag,
            bg="#181818", fg="#444", 
            activebackground="#4cc9f0",
            troughcolor="#111",
            highlightthickness=0,
            length=250,
            width=20
        )
        self.dial.pack(fill="x", padx=15, pady=(0, 15))
        
        # Bind events
        self.dial.bind("<ButtonPress-1>", self._on_dial_press)
        self.dial.bind("<ButtonRelease-1>", self._on_dial_release)

        # Volume/Speed Sliders (Preserved functionality)
        self._mk_slider(body, "VOLUME", 0.0, 1.5, 1.0, lambda v: self._send("set_volume", float(v)), "vol_var")
        self._mk_slider(body, "SPEED", 0.6, 1.6, 1.0, lambda v: self._send("set_speed", float(v)), "spd_var")

    def _mk_slider(self, parent, label, lo, hi, init, on_change, var_name):
        wrap = self.tk.Frame(parent, bg=self.bg)
        wrap.pack(fill="x", pady=4)
        
        row = self.tk.Frame(wrap, bg=self.bg)
        row.pack(fill="x")
        self.tk.Label(row, text=label, fg="#888", bg=self.bg, font=("Segoe UI", 9, "bold")).pack(side="left")
        
        var = self.tk.DoubleVar(value=float(init))
        setattr(self, var_name, var)
        
        val_lbl = self.tk.Label(row, text=f"{init:.2f}", fg="#ccc", bg=self.bg, font=("Segoe UI", 9))
        val_lbl.pack(side="right")
        
        def _cmd(v):
            val_lbl.config(text=f"{float(v):.2f}")
            on_change(v)

        s = self.tk.Scale(
            wrap, from_=lo, to=hi, resolution=0.01,
            orient="horizontal", variable=var,
            showvalue=False,
            bg=self.bg, fg="#e8e8e8", troughcolor="#1f1f1f",
            highlightthickness=0,
            command=_cmd
        )
        s.pack(fill="x", pady=(0, 6))

    def _scan_stations(self):
        self.stations = []
        try:
            import os
            # Use runtime's root if available, else try relative
            root = self.runtime.get("config", {}).get("RADIO_OS_ROOT") or os.getcwd()
            s_dir = os.path.join(root, "stations")
            if not os.path.exists(s_dir):
                # Try relative to this file? No, assume cwd is root or we can find 'stations'
                if os.path.exists("stations"):
                    s_dir = "stations"
            
            if os.path.exists(s_dir):
                candidates = [d for d in os.listdir(s_dir) if os.path.isdir(os.path.join(s_dir, d))]
                # Filter for manifest
                self.stations = sorted([d for d in candidates if os.path.exists(os.path.join(s_dir, d, "manifest.yaml"))])
        except Exception as e:
            print(f"Station scan error: {e}")
        
        if not self.stations:
            self.stations = ["No Stations Found"]
            
        # Update dial range
        self.dial.configure(to=len(self.stations) - 1)

    def _set_current_station_index(self):
        import os
        
        # 1. Try env var (most reliable source of truth)
        current_path = os.environ.get("STATION_DIR")
        
        # 2. Try config injection
        if not current_path:
            current_path = self.runtime.get("config", {}).get("STATION_DIR")

        # 3. Fallback to CWD only if it looks like a station (has manifest)
        if not current_path:
            if os.path.exists("manifest.yaml"):
                current_path = os.getcwd()

        current = ""
        if current_path:
            # Handle trailing slashes or normalize path
            current = os.path.basename(os.path.normpath(current_path))

        if current and current in self.stations:
            idx = self.stations.index(current)
            self.dial_var.set(idx)
            self.station_name_lbl.config(text=current)
            self.status_lbl.config(text=f"Broadcasting: {current}")
        else:
            self.dial_var.set(0)
            if self.stations:
                self.station_name_lbl.config(text=self.stations[0])

    # --- Interaction Logic ---

    def _on_dial_press(self, event):
        self._start_static()

    def _on_dial_release(self, event):
        self._stop_static()
        # Tune to the integer station
        try:
            raw_val = self.dial_var.get()
            idx = int(round(raw_val))
            self.dial_var.set(idx) # Snap to integer
            
            if 0 <= idx < len(self.stations):
                target_station = self.stations[idx]
                self.station_name_lbl.config(text=target_station)
                self._tune_to(target_station)
        except Exception:
            pass

    def _on_dial_drag(self, val):
        # Update label while dragging
        try:
            # If a timer is running, cancel it (user is interacting again)
            if self.tune_timer:
                self.root.after_cancel(self.tune_timer)
                self.tune_timer = None
                self.status_lbl.config(text="Scanning...")

            idx = int(round(float(val)))
            if 0 <= idx < len(self.stations):
                self.station_name_lbl.config(text=self.stations[idx])
        except:
            pass
        
        # Modulate static volume based on how far we are from integer?
        # For now just constant static is fine.

    def _tune_to(self, station_name):
        import os
        current_path = self.runtime.get("config", {}).get("STATION_DIR", os.getcwd())
        current = os.path.basename(current_path)
        
        if station_name == current:
            self.status_lbl.config(text="Broadcasting: " + current)
            return
            
        # Cancel any pending
        if self.tune_timer:
            self.root.after_cancel(self.tune_timer)
            self.tune_timer = None

        # Schedule switch
        delay_ms = 3500
        
        # Countdown feedback (simple version)
        self.status_lbl.config(text=f"Switching to {station_name} in 3.5s...")
        
        def _do_switch():
            self.status_lbl.config(text=f"Connecting to {station_name}...")
            self._send("tune_station", station_name)
            self.tune_timer = None

        self.tune_timer = self.root.after(delay_ms, _do_switch)

    # --- Audio Logic ---

    def _start_static(self):
        if not HAS_AUDIO: return
        if self.static_playing: return
        self.static_playing = True
        self.stop_static_event.clear()
        self.static_thread = threading.Thread(target=self._static_worker)
        self.static_thread.daemon = True
        self.static_thread.start()

    def _stop_static(self):
        if not HAS_AUDIO: return
        self.static_playing = False
        self.stop_static_event.set()

    def _static_worker(self):
        # Generate white noise chunks
        try:
            fs = 44100
            chunk_size = 4096
            stream = sd.OutputStream(samplerate=fs, channels=1, blocksize=chunk_size, dtype='float32')
            stream.start()
            
            vol = 0.15 # Default static volume
            
            while not self.stop_static_event.is_set():
                # Generate noise
                noise = np.random.uniform(-vol, vol, chunk_size).astype(np.float32)
                # Add some crackle (random spikes)
                # mask = np.random.random(chunk_size) > 0.99
                # noise[mask] += np.random.uniform(-0.5, 0.5, np.sum(mask))
                
                stream.write(noise)
            
            stream.stop()
            stream.close()
        except Exception as e:
            print(f"Static audio error: {e}")

    def _send(self, cmd, payload):
        if self.ui_cmd_q:
            self.ui_cmd_q.put((cmd, payload))

    def on_update(self, data: Any):
        # accept updates from runtime
        if not isinstance(data, dict):
            return
        if "volume" in data:
            if hasattr(self, "vol_var"):
                self.vol_var.set(float(data["volume"]))
        if "speed" in data:
            if hasattr(self, "spd_var"):
                self.spd_var.set(float(data["speed"]))
