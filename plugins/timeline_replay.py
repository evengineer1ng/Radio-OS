import time
from typing import Any, Dict, List

PLUGIN_NAME = "timeline_replay"

def register_widgets(registry, runtime):
    tk = runtime["tk"]

    def factory(parent, rt):
        return TimelineReplayWidget(parent, rt).root

    registry.register("timeline_replay", factory, title="Timeline • Replay", default_panel="center")


class TimelineReplayWidget:
    def __init__(self, parent, runtime):
        self.tk = runtime["tk"]
        self.runtime = runtime

        # queues
        self.ui_cmd_q = runtime.get("ui_cmd_q")
        if self.ui_cmd_q is None:
            try:
                from runtime import ui_cmd_q as _q  # type: ignore
                self.ui_cmd_q = _q
            except Exception:
                self.ui_cmd_q = None

        self.root = self.tk.Frame(parent, bg="#0e0e0e")

        hdr = self.tk.Frame(self.root, bg="#121212", highlightthickness=1, highlightbackground="#2a2a2a")
        hdr.pack(fill="x", padx=10, pady=(10, 8))
        self.tk.Label(hdr, text="TIMELINE REPLAY", fg="#4cc9f0", bg="#121212",
                      font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=10)

        body = self.tk.Frame(self.root, bg="#0e0e0e")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.canvas = self.tk.Canvas(body, bg="#0e0e0e", highlightthickness=0)
        self.scroll = self.tk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)

        self.scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = self.tk.Frame(self.canvas, bg="#0e0e0e")
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.items: List[Dict[str, Any]] = []
        self.cards = []

        def _on_inner(_e=None):
            try:
                self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            except Exception:
                pass
        self.inner.bind("<Configure>", _on_inner)

        def _on_canvas(e):
            try:
                self.canvas.itemconfigure(self.win, width=e.width)
            except Exception:
                pass
        self.canvas.bind("<Configure>", _on_canvas)

        # empty
        self.empty = self.tk.Label(self.inner, text="(timeline idle)", fg="#9a9a9a", bg="#0e0e0e",
                                   font=("Segoe UI", 11))
        self.empty.pack(pady=40)

    def _add(self, seg: Dict[str, Any]):
        if not isinstance(seg, dict):
            return

        # keep light copy
        item = {
            "id": seg.get("id") or seg.get("post_id") or "",
            "ts": seg.get("ts") or int(time.time()),
            "source": seg.get("source") or "",
            "title": (seg.get("title") or "")[:140],
            "body": (seg.get("body") or "")[:220],
        }
        self.items.insert(0, item)
        self.items = self.items[:120]

        # rebuild UI (cheap enough at 120 max)
        self._rebuild()

    def _rebuild(self):
        try:
            self.empty.pack_forget()
        except Exception:
            pass

        for c in list(self.cards):
            try:
                c.destroy()
            except Exception:
                pass
        self.cards.clear()

        if not self.items:
            self.empty.pack(pady=40)
            return

        for it in self.items:
            card = self.tk.Frame(self.inner, bg="#121212", highlightthickness=1, highlightbackground="#2a2a2a")
            card.pack(fill="x", pady=6)

            top = self.tk.Frame(card, bg="#121212")
            top.pack(fill="x", padx=10, pady=(8, 0))

            ts = it.get("ts") or 0
            ts_s = time.strftime("%H:%M:%S", time.localtime(int(ts)))

            self.tk.Label(top, text=f"{ts_s} • {str(it.get('source') or '').upper()}",
                          fg="#9a9a9a", bg="#121212", font=("Segoe UI", 9, "bold")).pack(side="left")

            btn = self.tk.Button(top, text="REPLAY", command=lambda sid=it.get("id"): self._replay(sid),
                                 bg="#2a2a2a", fg="#ffffff", relief="flat", padx=10, pady=4)
            btn.pack(side="right")

            title = self.tk.Label(card, text=it.get("title") or "", fg="#e8e8e8", bg="#121212",
                                  font=("Segoe UI", 11, "bold"), justify="left", anchor="w", wraplength=520)
            title.pack(fill="x", padx=10, pady=(6, 0))

            body = self.tk.Label(card, text=it.get("body") or "", fg="#9a9a9a", bg="#121212",
                                 font=("Segoe UI", 10), justify="left", anchor="w", wraplength=520)
            body.pack(fill="x", padx=10, pady=(4, 10))

            self.cards.append(card)

    def _replay(self, seg_id: str):
        if not seg_id or self.ui_cmd_q is None:
            return
        try:
            self.ui_cmd_q.put(("timeline_replay", {"seg_id": seg_id}))
        except Exception:
            pass

    def on_update(self, data: Any):
        # expects {"push": seg} or {"items":[...]}
        if not isinstance(data, dict):
            return
        if "push" in data and isinstance(data["push"], dict):
            self._add(data["push"])
        elif "items" in data and isinstance(data["items"], list):
            self.items = [x for x in data["items"] if isinstance(x, dict)][:120]
            self._rebuild()
