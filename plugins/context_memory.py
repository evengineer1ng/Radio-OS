import time
from typing import Any, Dict, List

PLUGIN_NAME = "context_memory"
IS_FEED = False

def register_widgets(registry, runtime):
    tk = runtime["tk"]

    def factory(parent, rt):
        return ContextMemoryWidget(parent, rt).root

    registry.register("context_memory", factory, title="Context • Memory", default_panel="left")


class ContextMemoryWidget:
    def __init__(self, parent, runtime):
        self.tk = runtime["tk"]
        self.runtime = runtime

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

        self.tk.Label(hdr, text="CONTEXT MEMORY", fg="#4cc9f0", bg="#121212",
                      font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        self.hint = self.tk.Label(hdr, text="live state + pins", fg="#9a9a9a", bg="#121212",
                                  font=("Segoe UI", 9))
        self.hint.pack(anchor="w", padx=10, pady=(0, 10))

        body = self.tk.Frame(self.root, bg="#0e0e0e")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        body.rowconfigure(2, weight=1)
        body.columnconfigure(0, weight=1)

        btns = self.tk.Frame(body, bg="#0e0e0e")
        btns.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.tk.Button(btns, text="PIN NOW PLAYING", command=self._pin_now,
                       bg="#2a2a2a", fg="#ffffff", relief="flat", padx=10, pady=8).pack(side="left")
        self.tk.Button(btns, text="UNPIN SELECTED", command=self._unpin_selected,
                       bg="#2a2a2a", fg="#ffffff", relief="flat", padx=10, pady=8).pack(side="left", padx=(10, 0))

        self.stats = self.tk.Text(body, height=8, wrap="word", bg="#111111", fg="#e8e8e8",
                                  highlightthickness=1, highlightbackground="#2a2a2a",
                                  font=("Segoe UI", 10))
        self.stats.grid(row=1, column=0, sticky="ew")

        self.listbox = self.tk.Listbox(body, bg="#121212", fg="#e8e8e8",
                                       highlightthickness=1, highlightbackground="#2a2a2a",
                                       selectbackground="#2a2a2a")
        self.listbox.grid(row=2, column=0, sticky="nsew", pady=(8, 0))

        self.pins: List[Dict[str, Any]] = []

        # periodic self-refresh via best-effort runtime mem (if accessible)
        self.root.after(700, self._tick)

    def _tick(self):
        # Best-effort runtime snapshot (no strict dependency)
        try:
            from runtime import mem as _mem  # type: ignore
            mem = _mem if isinstance(_mem, dict) else {}
        except Exception:
            mem = {}

        # render core stats
        try:
            candidates = len(mem.get("feed_candidates") or [])
            timeline = len(mem.get("timeline") or [])
            tags = mem.get("recent_riff_tags") or []
            vol = float(mem.get("audio_volume", 1.0) or 1.0)
            spd = float(mem.get("audio_speed", 1.0) or 1.0)

            txt = (
                f"audio_volume: {vol:.2f}\n"
                f"audio_speed:  {spd:.2f}\n"
                f"producer candidates: {candidates}\n"
                f"timeline depth: {timeline}\n"
                f"recent tags (tail): {list(tags)[-12:]}\n"
            )
            self.stats.delete("1.0", "end")
            self.stats.insert("1.0", txt)
        except Exception:
            pass

        self.root.after(700, self._tick)

    def _pin_now(self):
        if self.ui_cmd_q is None:
            return
        try:
            from runtime import mem as _mem  # type: ignore
            seg = _mem.get("ui_last_seg") if isinstance(_mem, dict) else None
        except Exception:
            seg = None

        if not isinstance(seg, dict):
            payload = {"title": "Pin", "body": f"Pinned @ {time.strftime('%H:%M:%S')}", "kind": "manual"}
        else:
            payload = {
                "title": (seg.get("title") or seg.get("source") or "Pinned")[:240],
                "body": (seg.get("body") or "")[:2500],
                "kind": str(seg.get("source") or "segment").lower(),
            }
        try:
            self.ui_cmd_q.put(("context_pin", payload))
        except Exception:
            pass

    def _unpin_selected(self):
        if self.ui_cmd_q is None:
            return
        idx = None
        try:
            sel = self.listbox.curselection()
            if sel:
                idx = int(sel[0])
        except Exception:
            idx = None
        if idx is None or idx < 0 or idx >= len(self.pins):
            return
        pid = self.pins[idx].get("id")
        if pid:
            try:
                self.ui_cmd_q.put(("context_unpin", str(pid)))
            except Exception:
                pass

    def on_update(self, data: Any):
        if not isinstance(data, dict):
            return
        if "pins" in data and isinstance(data["pins"], list):
            self.pins = [p for p in data["pins"] if isinstance(p, dict)]
            self.listbox.delete(0, "end")
            for p in self.pins:
                ts = p.get("ts") or 0
                ts_s = time.strftime("%H:%M:%S", time.localtime(int(ts)))
                title = (p.get("title") or "pin")[:60]
                kind = (p.get("kind") or "note")
                self.listbox.insert("end", f"{ts_s} • {kind} • {title}")
