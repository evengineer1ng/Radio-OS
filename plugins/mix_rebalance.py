import math
from typing import Dict, Any

# Pull the live, loaded station manifest from the runtime engine.
# This works because runtime.py does: sys.modules.setdefault("your_runtime", sys.modules[__name__])
from your_runtime import CFG  # type: ignore

PLUGIN_NAME = "mix_rebalance"

IS_FEED = False

# =====================================================
# Mix Rebalance Widget
# =====================================================

def register_widgets(registry, runtime):

    tk = runtime["tk"]

    def get_cfg() -> Dict[str, Any]:
        # The UI runtime dict does NOT include manifest/cfg/station by design.
        # The canonical config lives in your_runtime.CFG.
        return CFG or {}

    BG = "#0e0e0e"
    CARD = "#141414"
    BORDER = "#2a2a2a"
    TEXT = "#e8e8e8"
    MUTED = "#9a9a9a"

    COLORS = [
        "#4cc9f0",
        "#ff6b6b",
        "#ffd166",
        "#2ee59d",
        "#9b5de5",
        "#f15bb5",
        "#00bbf9",
        "#f72585",
    ]

    def factory(parent, runtime):

        root = tk.Frame(parent, bg=BG)

        card = tk.Frame(
            root,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        card.pack(fill="both", expand=True, padx=12, pady=12)

        header = tk.Label(
            card,
            text="Feed Mix Rebalance",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 13, "bold"),
            anchor="w"
        )
        header.pack(fill="x", padx=12, pady=(10, 6))

        subtitle = tk.Label(
            card,
            text="Time is a pie — adjust how much airtime each feed gets",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 10),
            anchor="w"
        )
        subtitle.pack(fill="x", padx=12, pady=(0, 10))

        body = tk.Frame(card, bg=CARD)
        body.pack(fill="both", expand=True, padx=12, pady=8)

        canvas = tk.Canvas(
            body,
            width=220,
            height=220,
            bg=CARD,
            highlightthickness=0
        )
        canvas.pack(side="left", padx=(0, 14))

        # -----------------------------
        # Scrollable controls area
        # -----------------------------

        controls_outer = tk.Frame(body, bg=CARD)
        controls_outer.pack(side="left", fill="both", expand=True)

        ctrl_canvas = tk.Canvas(
            controls_outer,
            bg=CARD,
            highlightthickness=0
        )

        v_scroll = tk.Scrollbar(
            controls_outer,
            orient="vertical",
            command=ctrl_canvas.yview
        )

        h_scroll = tk.Scrollbar(
            controls_outer,
            orient="horizontal",
            command=ctrl_canvas.xview
        )

        ctrl_canvas.configure(
            yscrollcommand=v_scroll.set,
            xscrollcommand=h_scroll.set
        )

        v_scroll.pack(side="right", fill="y")
        h_scroll.pack(side="bottom", fill="x")
        ctrl_canvas.pack(side="left", fill="both", expand=True)

        # This is where sliders will live now
        controls = tk.Frame(ctrl_canvas, bg=CARD)

        ctrl_canvas.create_window(
            (0, 0),
            window=controls,
            anchor="nw"
        )

        def _update_scrollregion(event=None):
            ctrl_canvas.configure(
                scrollregion=ctrl_canvas.bbox("all")
            )

        controls.bind("<Configure>", _update_scrollregion)

        sliders: Dict[str, Any] = {}
        pct_labels: Dict[str, Any] = {}
        updating = False

        # =====================================================
        # Data helpers
        # =====================================================

        def get_feeds() -> list[str]:
            cfg = get_cfg()

            raw: list[str] = []

            feeds = cfg.get("feeds")
            if isinstance(feeds, dict):
                raw = [
                    str(k) for k, v in feeds.items()
                    if isinstance(v, dict) and v.get("enabled", False)
                ]

            elif isinstance(feeds, list):
                raw = [str(x) for x in feeds]

            else:
                quotas = (cfg.get("scheduler") or {}).get("source_quotas")
                if isinstance(quotas, dict) and quotas:
                    raw = [str(k) for k in quotas.keys()]
                else:
                    raw = list(get_weights().keys())

            return [x for x in raw if x != "music_breaks"]

        def get_weights() -> Dict[str, float]:
            cfg = get_cfg()

            w = (cfg.get("mix") or {}).get("weights")
            if isinstance(w, dict) and w:
                out: Dict[str, float] = {}
                for k, v in w.items():
                    if str(k) == "music_breaks":
                        continue
                    try:
                        out[str(k)] = float(v)
                    except Exception:
                        continue
                return out

            quotas = (cfg.get("scheduler") or {}).get("source_quotas")
            if isinstance(quotas, dict) and quotas:
                out2: Dict[str, float] = {}
                for k, v in quotas.items():
                    if str(k) == "music_breaks":
                        continue
                    try:
                        out2[str(k)] = float(v)
                    except Exception:
                        continue
                return out2

            return {}

        def normalize(weights: Dict[str, float]) -> Dict[str, float]:
            s = sum(max(v, 0.0) for v in weights.values())
            if s <= 0:
                n = len(weights)
                return {k: 1.0 / n for k in weights} if n else {}
            return {k: max(v, 0.0) / s for k, v in weights.items()}

        def save(weights01: Dict[str, float]) -> None:
            cfg = get_cfg()

            norm = normalize(weights01)

            # Store mix (for UI + persistence later)
            cfg.setdefault("mix", {})["weights"] = norm

            # ============================
            # LIVE SCHEDULER WIRING
            # ============================

            scheduler = cfg.setdefault("scheduler", {})
            quotas = scheduler.setdefault("source_quotas", {})

            TOTAL_SLOTS = 20   # feel free to tune (15–30 works great)

            # Convert fractions -> integer airtime slots
            raw = {src: norm[src] * TOTAL_SLOTS for src in norm}

            # Floor first
            ints = {src: int(v) for src, v in raw.items()}

            # Distribute leftover slots (largest remainder method)
            used = sum(ints.values())
            remainder = TOTAL_SLOTS - used

            if remainder > 0:
                # sort by fractional leftover
                order = sorted(
                    raw.items(),
                    key=lambda kv: kv[1] - int(kv[1]),
                    reverse=True
                )

                for src, _ in order:
                    if remainder <= 0:
                        break
                    ints[src] += 1
                    remainder -= 1

            # Never allow zero slots for enabled feeds
            for src in ints:
                if ints[src] <= 0:
                    ints[src] = 1

            # Push live into scheduler
            for src, slots in ints.items():
                quotas[src] = slots


        # =====================================================
        # Pie rendering
        # =====================================================

        def draw_pie(weights_any: Dict[str, float]) -> None:
            canvas.delete("all")

            w01 = normalize(weights_any or {})

            cx, cy = 110, 110
            r = 100

            if not w01:
                canvas.create_oval(
                    cx - r, cy - r, cx + r, cy + r,
                    outline=BORDER, width=2
                )
                canvas.create_text(
                    cx, cy,
                    text="NO DATA",
                    fill=MUTED,
                    font=("Segoe UI", 11, "bold")
                )
                return

            start = 0.0
            i = 0

            # Largest first for stable, readable pies.
            for src, frac in sorted(w01.items(), key=lambda x: x[1], reverse=True):
                if frac <= 0:
                    continue

                extent = float(frac) * 360.0
                color = COLORS[i % len(COLORS)]

                canvas.create_arc(
                    cx - r, cy - r, cx + r, cy + r,
                    start=start,
                    extent=extent,
                    fill=color,
                    outline=BORDER,
                    width=1,
                    style="pieslice"
                )

                start += extent
                i += 1

            canvas.create_text(
                cx, cy,
                text="100%",
                fill=TEXT,
                font=("Segoe UI", 12, "bold")
            )

        # =====================================================
        # UI rebuild
        # =====================================================

        def rebuild_controls() -> None:
            nonlocal updating

            for w in controls.winfo_children():
                w.destroy()

            sliders.clear()
            pct_labels.clear()

            feeds = get_feeds()
            weights = get_weights()

            # If we have feeds but no explicit weights yet, seed evenly.
            if feeds and not weights:
                weights = {f: 1.0 for f in feeds}

            # Ensure every enabled feed has a weight key.
            for f in feeds:
                weights.setdefault(f, 1.0)

            w01 = normalize(weights)

            # Debug line (keep until you're satisfied; then delete)
            dbg = tk.Label(
                controls,
                text=f"feeds={len(feeds)}  weights={len(w01)}",
                bg=CARD,
                fg=MUTED,
                anchor="w",
                font=("Segoe UI", 9)
            )
            dbg.pack(fill="x", pady=(0, 6))

            def sync_all(norm01: Dict[str, float]) -> None:
                nonlocal updating
                updating = True
                try:
                    for k, sld in sliders.items():
                        sld.set(norm01.get(k, 0.0) * 100.0)
                        if k in pct_labels:
                            pct_labels[k].config(
                                text=f"{int(round(norm01.get(k, 0.0) * 100.0))}%"
                            )
                finally:
                    updating = False

            for src in feeds:
                row = tk.Frame(controls, bg=CARD)
                row.pack(fill="x", pady=6)

                lbl = tk.Label(
                    row,
                    text=src,
                    bg=CARD,
                    fg=TEXT,
                    width=14,
                    anchor="w",
                    font=("Segoe UI", 10, "bold")
                )
                lbl.pack(side="left")

                var = tk.DoubleVar(value=w01.get(src, 0.0) * 100.0)

                def on_change(*_args, src=src, var=var):
                    nonlocal updating
                    if updating:
                        return

                    # Read current slider positions (0..100), convert to (0..1)
                    cur = {k: float(sliders[k].get()) for k in sliders}
                    cur[src] = float(var.get())

                    scaled01 = {k: v / 100.0 for k, v in cur.items()}
                    norm01 = normalize(scaled01)

                    sync_all(norm01)
                    save(norm01)
                    draw_pie(norm01)

                sld = tk.Scale(
                    row,
                    from_=0,
                    to=100,
                    orient="horizontal",
                    variable=var,
                    showvalue=False,
                    length=180,
                    bg=CARD,
                    fg=TEXT,
                    troughcolor="#2a2a2a",
                    highlightthickness=0
                )
                sld.pack(side="left", padx=6)

                pct = tk.Label(
                    row,
                    text=f"{int(round(w01.get(src, 0.0) * 100.0))}%",
                    bg=CARD,
                    fg=MUTED,
                    width=5
                )
                pct.pack(side="left")

                var.trace_add("write", on_change)

                sliders[src] = sld
                pct_labels[src] = pct

            draw_pie(w01)

        # =====================================================
        # Runtime hooks
        # =====================================================

        def on_station_event(evt, payload):
            if evt in ("station_loaded", "config_updated"):
                rebuild_controls()

        root.on_station_event = on_station_event

        # First paint after UI is up
        root.after(200, rebuild_controls)

        return root

    registry.register(
        "mix_rebalance",
        factory,
        title="Feed Mix Rebalance",
        default_panel="right"
    )
