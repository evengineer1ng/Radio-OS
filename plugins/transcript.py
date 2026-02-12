"""
transcript.py — Live Transcript Plugin for RadioOS

Tracks spoken words from the host and all characters in real-time.
Provides a scrollable widget with "Save to Disk" functionality.
"""
from __future__ import annotations
import sys
import time
import threading
import tkinter as tk
from tkinter import filedialog, ttk

import your_runtime as rt

PLUGIN_NAME = "transcript"
PLUGIN_DESC = "Real-time transcript of all station speech"
IS_FEED = False

# =====================================================
# Global Transcript Storage
# =====================================================
# Stores: {timestamp: float, time_str: str, speaker: str, text: str}
TRANSCRIPT_HISTORY = []
MAX_HISTORY = 2000

# =====================================================
# Speech Hook
# =====================================================
_ORIGINAL_SPEAK = None
_HOOK_INSTALLED = False

def _transcript_speak_hook(text: str, voice_key: str = "host"):
    """
    Intercepts the runtime speak() function to log text to transcript.
    """
    try:
        if text and text.strip():
            ts = time.time()
            entry = {
                "timestamp": ts,
                "time_str": time.strftime("%H:%M:%S", time.localtime(ts)),
                "speaker": str(voice_key).upper(),
                "text": text.strip()
            }
            TRANSCRIPT_HISTORY.append(entry)
            
            # Trim history if needed
            if len(TRANSCRIPT_HISTORY) > MAX_HISTORY:
                TRANSCRIPT_HISTORY.pop(0)
                
    except Exception as e:
        print(f"[Transcript Plugin] Error in hook: {e}")

    # Pass through to the original function
    if _ORIGINAL_SPEAK:
        return _ORIGINAL_SPEAK(text, voice_key)
    return None

def install_hook():
    """Monkey-patch the runtime.speak function safely."""
    global _ORIGINAL_SPEAK, _HOOK_INSTALLED
    
    # Avoid double patching
    if getattr(rt, "_transcript_hook_installed", False):
        return

    if hasattr(rt, "speak"):
        _ORIGINAL_SPEAK = rt.speak
        rt.speak = _transcript_speak_hook
        rt._transcript_hook_installed = True
        _HOOK_INSTALLED = True
        print(f"[Transcript Plugin] Hook installed on runtime.speak")
    else:
        print(f"[Transcript Plugin] Warning: runtime.speak not found, cannot trace speech.")

# Install immediately upon import
install_hook()

# =====================================================
# Widget Registration
# =====================================================

def register_widgets(registry, runtime_stub):
    """
    Register the transcript widget.
    """
    
    # Try to import shell theme constants, else fallback
    try:
        from shell import UI, FONT_BODY, FONT_SMALL
    except ImportError:
        UI = {
            "bg": "#0e0e0e",
            "panel": "#121212", 
            "card": "#181818", 
            "text": "#e8e8e8",
            "accent": "#4cc9f0"
        }
        FONT_BODY = ("Segoe UI", 10)
        FONT_SMALL = ("Segoe UI", 8)

    def widget_factory(parent, runtime_ctx):
        """
        Builds the transcript UI panel.
        """
        # Main container
        frame = tk.Frame(parent, bg=UI["panel"])
        
        # 1. Header / Toolbar
        toolbar = tk.Frame(frame, bg=UI["panel"], pady=4, padx=4)
        toolbar.pack(side="top", fill="x")

        # Save Button
        def save_transcript():
            if not TRANSCRIPT_HISTORY:
                return
            
            # Generate default filename
            filename = f"transcript_{time.strftime('%Y%m%d_%H%M%S')}.txt"
            
            path = filedialog.asksaveasfilename(
                initialfile=filename,
                defaultextension=".txt",
                filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
                title="Save Transcript"
            )
            
            if path:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(f"RADIO OS TRANSCRIPT - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                        f.write("="*60 + "\n\n")
                        for entry in TRANSCRIPT_HISTORY:
                            f.write(f"[{entry['time_str']}] {entry['speaker']}: {entry['text']}\n")
                    print(f"Transcript saved to {path}")
                except Exception as e:
                    print(f"Error saving transcript: {e}")

        btn_save = tk.Button(
            toolbar,
            text="Save to Disk",
            command=save_transcript,
            bg=UI["card"],
            fg=UI["text"],
            bd=0,
            padx=10,
            font=FONT_SMALL,
            activebackground=UI["accent"],
            activeforeground="#000000"
        )
        btn_save.pack(side="left")
        
        # Status Label
        lbl_status = tk.Label(
            toolbar,
            text=f"Listening...", 
            bg=UI["panel"], 
            fg="#666", 
            font=FONT_SMALL
        )
        lbl_status.pack(side="right", padx=5)

        # 2. Text Area with Scrollbar
        text_frame = tk.Frame(frame, bg=UI["panel"])
        text_frame.pack(side="top", fill="both", expand=True, padx=2, pady=2)
        
        # Scrollbar
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")
        
        # Text Widget
        # Using a tag for speaker names to make them bold/colored
        import tkinter.font as tkfont
        base_font = tkfont.Font(font=FONT_BODY)
        bold_font = base_font.copy()
        bold_font.configure(weight="bold")

        txt = tk.Text(
            text_frame,
            bg=UI["card"],
            fg=UI["text"],
            bd=0,
            font=FONT_BODY,
            selectbackground=UI["accent"],
            selectforeground="#000000",
            wrap="word",
            yscrollcommand=scrollbar.set,
            padx=10,
            pady=10,
            state="disabled" 
        )
        txt.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=txt.yview)

        # Configure tags
        txt.tag_config("timestamp", foreground="#666666", font=FONT_SMALL)
        txt.tag_config("speaker", foreground=UI["accent"], font=bold_font, spacing1=5)
        txt.tag_config("content", foreground=UI["text"], spacing3=5)

        # State for polling
        last_rendered_idx = 0

        def update_view():
            nonlocal last_rendered_idx
            
            current_len = len(TRANSCRIPT_HISTORY)
            if current_len > last_rendered_idx:
                txt.config(state="normal")
                
                # Render new entries
                for i in range(last_rendered_idx, current_len):
                    entry = TRANSCRIPT_HISTORY[i]
                    
                    # Format: [HH:MM:SS] SPEAKER
                    #         Text content...
                    
                    txt.insert("end", f"[{entry['time_str']}]  ", "timestamp")
                    txt.insert("end", f"{entry['speaker']}\n", "speaker")
                    txt.insert("end", f"{entry['text']}\n", "content")
                
                # Auto-scroll if at bottom
                txt.see("end")
                txt.config(state="disabled")
                
                last_rendered_idx = current_len
                lbl_status.config(text=f"{last_rendered_idx} entries")
            
            # Schedule next update
            frame.after(1000, update_view)

        # Start loop
        update_view()

        return frame

    # Register the widget
    registry.register(
        "transcript",
        widget_factory,
        title="Transcript",
        default_panel="right" 
    )
