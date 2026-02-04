IS_FEED = False

def register_widgets(registry, runtime):

    tk = runtime["tk"]
    mem = runtime["mem"]

    BG = "#0e0e0e"
    CARD = "#161616"
    BORDER = "#2a2a2a"
    TXT = "#e8e8e8"
    MUTED = "#9a9a9a"
    ACCENT = "#4cc9f0"

    def explorer_factory(parent, runtime):

        root = tk.Frame(parent, bg=BG)

        # =========================
        # Controls
        # =========================

        ctrl = tk.Frame(root, bg=BG)
        ctrl.pack(fill="x", padx=10, pady=6)

        search_var = tk.StringVar()

        tk.Entry(
            ctrl,
            textvariable=search_var,
            bg=CARD,
            fg=TXT,
            insertbackground=TXT,
            relief="flat"
        ).pack(side="left", fill="x", expand=True, padx=(0,8))

        sort_var = tk.StringVar(value="Newest")

        tk.OptionMenu(
            ctrl,
            sort_var,
            "Newest", "Highest Priority"
        ).pack(side="left")

        # =========================
        # Scroll area
        # =========================

        canvas = tk.Canvas(root, bg=BG, highlightthickness=0)
        scroll = tk.Scrollbar(root, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)

        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=BG)
        win = canvas.create_window((0,0), window=inner, anchor="nw")

        cards = []

        def sync(_=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", sync)

        def clear_cards():
            for c in cards:
                c.destroy()
            cards.clear()

        # =========================
        # Render
        # =========================

        def render():

            clear_cards()

            q = search_var.get().lower().strip()
            items = list(mem.get("feed_candidates", []))

            # -------- filter search
            if q:
                items = [
                    c for c in items
                    if q in (c.get("title","")+c.get("body","")).lower()
                ]

            # -------- sorting
            if sort_var.get() == "Highest Priority":
                items.sort(key=lambda c: float(c.get("heur",0)), reverse=True)
            else:
                items.sort(key=lambda c: int(c.get("ts",0)), reverse=True)

            # -------- display
            for c in items[:200]:

                card = tk.Frame(inner, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
                card.pack(fill="x", padx=10, pady=6)

                hdr = tk.Frame(card, bg=CARD)
                hdr.pack(fill="x", padx=8, pady=(6,2))

                tk.Label(
                    hdr,
                    text=c.get("source","").upper(),
                    fg=ACCENT,
                    bg=CARD,
                    font=("Segoe UI", 9, "bold")
                ).pack(side="left")

                tk.Label(
                    hdr,
                    text=c.get("event_type",""),
                    fg=MUTED,
                    bg=CARD,
                    font=("Segoe UI", 9)
                ).pack(side="right")

                tk.Label(
                    card,
                    text=c.get("title",""),
                    fg=TXT,
                    bg=CARD,
                    font=("Segoe UI", 12, "bold"),
                    justify="left"
                ).pack(fill="x", padx=8)

                tk.Label(
                    card,
                    text=c.get("body","")[:400],
                    fg=MUTED,
                    bg=CARD,
                    font=("Segoe UI", 10),
                    justify="left"
                ).pack(fill="x", padx=8, pady=(2,8))

                cards.append(card)

        # =========================
        # Live refresh loop
        # =========================

        def tick():
            render()
            root.after(1500, tick)

        tick()

        root.pack(fill="both", expand=True)
        return root


    registry.register(
        "event_explorer",
        explorer_factory,
        title="Events • Explorer",
        default_panel="center"
    )
