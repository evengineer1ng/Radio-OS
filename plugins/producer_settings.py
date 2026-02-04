import math
from typing import Dict, Any
from your_runtime import CFG  # type: ignore

PLUGIN_NAME = "producer_settings"
PLUGIN_DESC = "Live control of producer pacing, queue size, and generation parameters."
IS_FEED = False

def register_widgets(registry, runtime):
    tk = runtime["tk"]
    
    # ensure producer config dict exists
    if "producer" not in CFG:
        CFG["producer"] = {}
        
    def get_cfg_val(key, default):
        return CFG["producer"].get(key, default)
        
    def set_cfg_val(key, val):
        CFG["producer"][key] = val
        print(f"[Producer Settings] Set {key} = {val}")

    BG = "#0e0e0e"
    CARD = "#141414" 
    BORDER = "#2a2a2a"
    TEXT = "#e8e8e8"
    MUTED = "#9a9a9a"
    accent_color = "#4cc9f0" 

    def factory(parent, runtime):
        root = tk.Frame(parent, bg=BG)
        
        card = tk.Frame(
            root,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        card.pack(fill="both", expand=True, padx=12, pady=12)
        
        # Header
        header_frame = tk.Frame(card, bg=CARD)
        header_frame.pack(fill="x", padx=12, pady=(10, 5))
        
        lbl_title = tk.Label(
            header_frame, 
            text="Producer Settings",
            bg=CARD, 
            fg=TEXT,
            font=("Segoe UI", 12, "bold"),
            anchor="w"
        )
        lbl_title.pack(side="left")
        
        lbl_sub = tk.Label(
            card,
            text="Live adjustments for flow, pacing, and queue.",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
            anchor="w"
        )
        lbl_sub.pack(fill="x", padx=12, pady=(0, 10))
        
        # Settings Container
        settings_frame = tk.Frame(card, bg=CARD)
        settings_frame.pack(fill="both", expand=True, padx=12, pady=5)
        
        def add_slider(label_text, key, default, min_val, max_val, resolution=1.0):
            row = tk.Frame(settings_frame, bg=CARD)
            row.pack(fill="x", pady=4)
            
            top = tk.Frame(row, bg=CARD)
            top.pack(fill="x")
            
            tk.Label(top, text=label_text, bg=CARD, fg=TEXT, font=("Segoe UI", 9)).pack(side="left")
            val_label = tk.Label(top, text=str(get_cfg_val(key, default)), bg=CARD, fg=accent_color, font=("Segoe UI", 9, "bold"))
            val_label.pack(side="right")
            
            def on_change(val):
                v = float(val)
                if resolution == 1.0:
                    v = int(v)
                set_cfg_val(key, v)
                val_label.config(text=str(v))
            
            scale = tk.Scale(
                row,
                from_=min_val,
                to=max_val,
                resolution=resolution,
                orient="horizontal",
                showvalue=0,
                bg=CARD,
                fg=TEXT,
                troughcolor=BG,
                activebackground=accent_color,
                highlightthickness=0,
                bd=0,
                command=on_change
            )
            scale.set(get_cfg_val(key, default))
            scale.pack(fill="x", pady=(2, 0))

        # 1. Queue Target Depth
        add_slider("Target Queue Depth", "target_depth", 4, 1, 20, 1)
        
        # 2. Max Queue Depth
        add_slider("Max Queue Depth", "max_depth", 12, 5, 50, 1)

        # 3. Tick Seconds (Pacing)
        add_slider("Producer Tick (Secs)", "tick_sec", 35, 1, 120, 1)
        
        # 4. Max Enqueue Per Cycle
        add_slider("Max Enqueue / Cycle", "max_enqueue_per_cycle", 8, 1, 20, 1)
        
        # 5. Temperature
        add_slider("Temperature (Creativity)", "temperature", 0.6, 0.1, 1.5, 0.05)
        
        # 6. Max Tokens
        add_slider("Max Tokens", "max_tokens", 220, 50, 1000, 10)

        # 7. Audio Low Water (when to panic)
        add_slider("Audio Low Water Mark", "audio_low_water", 2, 1, 10, 1)

        # Save Button
        def do_save():
            if hasattr(runtime, "save_cfg_to_manifest"):
                runtime.save_cfg_to_manifest()
            elif "save_cfg_to_manifest" in CFG:
                # Hack access if injected
                pass
            else:
                # Try import from runtime
                try:
                    from runtime import save_cfg_to_manifest
                    save_cfg_to_manifest()
                except ImportError:
                    print("Cannot save: save_cfg_to_manifest not found")

        btn = tk.Button(
            card, text="Save to Manifest", 
            bg=accent_color, fg=BG, 
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            command=do_save
        )
        btn.pack(fill="x", padx=12, pady=(10, 10))
        
        return root

    registry.register(
        "producer_settings",
        factory,
        title="Producer Tuning",
        default_panel="right"
    )
