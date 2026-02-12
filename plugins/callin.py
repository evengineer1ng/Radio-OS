import tkinter as tk
from tkinter import ttk
import sounddevice as sd
import queue
import time
from typing import Dict, Any, List

PLUGIN_NAME = "callin"
IS_FEED = False

def register_widgets(registry, runtime):
    # Pass 'runtime' which is the shim or actual runtime dict
    def factory(parent, rt):
        return CallInWidget(parent, rt).root

    registry.register("callin", factory, title="Live Call-In", default_panel="right")

class CallInWidget:
    def __init__(self, parent, runtime):
        self.tk = runtime["tk"]
        self.ui_cmd_q = runtime["ui_cmd_q"]
        self.event_q = runtime["event_q"]
        self.StationEvent = runtime["StationEvent"]
        
        self.root = self.tk.Frame(parent, bg="#0e0e0e")
        
        # Header
        hdr = self.tk.Frame(self.root, bg="#121212", highlightthickness=1, highlightbackground="#2a2a2a")
        hdr.pack(fill="x", padx=10, pady=(10, 8))
        self.tk.Label(hdr, text="LIVE CALLER", fg="#ff4d6d", bg="#121212", 
                      font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        self.tk.Label(hdr, text="disruptive • live audio", fg="#9a9a9a", bg="#121212", 
                                 font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=(0, 10))

        body = self.tk.Frame(self.root, bg="#0e0e0e")
        body.pack(fill="both", expand=True, padx=10, pady=0)

        # 1. Device Selection
        dev_frame = self.tk.Frame(body, bg="#0e0e0e")
        dev_frame.pack(fill="x", pady=(0, 10))
        
        self.tk.Label(dev_frame, text="Input Device:", bg="#0e0e0e", fg="#9a9a9a", font=("Segoe UI", 9)).pack(anchor="w")
        
        self.devices = []
        self.dev_names = []
        try:
            self.devices = sd.query_devices()
            # filter inputs
            self.inputs = [d for d in self.devices if d['max_input_channels'] > 0]
            self.dev_names = [d['name'] for d in self.inputs]
        except Exception:
            self.dev_names = ["Default"]
            
        self.dev_var = self.tk.StringVar()
        if self.dev_names:
            self.dev_var.set(self.dev_names[0])
            
        self.dev_menu = ttk.Combobox(dev_frame, textvariable=self.dev_var, values=self.dev_names, state="readonly")
        self.dev_menu.pack(fill="x", pady=(4,0))

        # 2. Controls & Waveform
        ctrl_frame = self.tk.Frame(body, bg="#0e0e0e")
        ctrl_frame.pack(fill="x", pady=5)
        
        self.btn_call = self.tk.Button(
            ctrl_frame, 
            text="CALL IN (PUSH TO TALK)",
            command=self._toggle_call,
            bg="#2a2a2a", fg="#ffffff",
            activebackground="#ff4d6d", activeforeground="#ffffff",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            pady=12
        )
        self.btn_call.pack(fill="x", pady=(0, 10))

        # Waveform Canvas
        self.canvas = self.tk.Canvas(ctrl_frame, height=60, bg="#000000", highlightthickness=1, highlightbackground="#333")
        self.canvas.pack(fill="x")
        
        # 3. Chat Window
        chat_frame = self.tk.Frame(body, bg="#0e0e0e")
        chat_frame.pack(fill="both", expand=True, pady=(15, 0))
        
        self.tk.Label(chat_frame, text="Caller Message (Text):", bg="#0e0e0e", fg="#9a9a9a", font=("Segoe UI", 9)).pack(anchor="w")
        
        self.txt_msg = self.tk.Text(chat_frame, height=4, bg="#1a1a1a", fg="white", 
                                    insertbackground="white", relief="flat", font=("Segoe UI", 10))
        self.txt_msg.pack(fill="x", pady=(4, 6))
        
        self.btn_send = self.tk.Button(
            chat_frame, 
            text="SEND TEXT INTERRUPT",
            command=self._send_text,
            bg="#2a2a2a", fg="#ffffff",
            relief="flat",
            padx=10, pady=6
        )
        self.btn_send.pack(fill="x")

        # State
        self.is_calling = False
        self.wave_data = [0.0] * 50
        
    def _toggle_call(self):
        if not self.is_calling:
            # Start Call
            self.is_calling = True
            self.btn_call.configure(text="🔴 ON AIR - CLICK TO END", bg="#ff4d6d", fg="#ffffff")
            
            # Resolve device ID
            idx = None
            try:
                name = self.dev_var.get()
                for i, d in enumerate(self.devices):
                    if d['name'] == name and d['max_input_channels'] > 0:
                        idx = i
                        break
            except Exception:
                pass
            
            # Trigger Runtime Interrupt & Recording
            self.ui_cmd_q.put(("callin_on", {"device": idx}))
            
        else:
            # End Call
            self.is_calling = False
            self.btn_call.configure(text="CALL IN (PUSH TO TALK)", bg="#2a2a2a", fg="#ffffff")
            
            # Determine if we should Transcribe
            # If text box has content, maybe we prefer that? 
            # But the user might have spoken too. We'll let runtime transcribe.
            # If the user wants to send text ONLY, they use the other button.
            # But if they use PTT, we assume voice.
            self.ui_cmd_q.put(("callin_off", {"transcribe": True}))

    def _send_text(self):
        txt = self.txt_msg.get("1.0", "end").strip()
        if not txt:
            return
            
        # Send generic event for interruption
        # We use 'callin' source so it matches the persona of "Caller"
        evt = self.StationEvent(
            source="callin",
            type="urgent_interrupt",  # High priority magic word or just set priority manually
            priority=100.0,           # Max priority
            payload={
                "title": "Caller Message",
                "body": txt,
                "host_hint": "Read this message from a caller immediately and react.",
                "why": "Urgent listener interaction."
            }
        )
        try:
            # We put it directly to event_q for speed, skipping some runtime/voice logic checks?
            # Actually event_q is the correct place.
            self.event_q.put(evt)
            # Also clear text
            self.txt_msg.delete("1.0", "end")
            
            # Optional: flash button
            orig = self.btn_send.cget("bg")
            self.btn_send.configure(bg="#2ee59d", text="SENT!")
            self.root.after(1000, lambda: self.btn_send.configure(bg=orig, text="SEND TEXT INTERRUPT"))
            
        except Exception:
            pass

    def on_update(self, data):
        """
        Received update from runtime (via shell)
        data = {"level": float}
        """
        if not isinstance(data, dict):
            return
            
        lvl = float(data.get("level", 0.0))
        
        # update waveform buffer
        self.wave_data.append(lvl)
        self.wave_data.pop(0)
        
        # redraw canvas
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10: return
        
        self.canvas.delete("all")
        
        # Draw bars
        n = len(self.wave_data)
        bar_w = w / n
        
        mid = h / 2
        
        for i, val in enumerate(self.wave_data):
            # Scale val (0..1 usually, but might be small)
            # Log scale might be better but linear is fine for simple viz
            amp = val * (h * 0.8) 
            if amp < 1: amp = 1
            
            x0 = i * bar_w
            x1 = x0 + bar_w - 1
            y0 = mid - (amp/2)
            y1 = mid + (amp/2)
            
            color = "#ff4d6d" if self.is_calling else "#444444"
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")

