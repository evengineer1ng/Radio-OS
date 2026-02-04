import time
from typing import Any, Dict, List

PLUGIN_NAME = "notes"
IS_FEED = False

def register_widgets(registry, runtime):
    tk = runtime["tk"]

    def factory(parent, rt):
        return NotesWidget(parent, rt).root

    registry.register("notes", factory, title="Notes • High End", default_panel="right")


class NotesWidget:
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
        self.tk.Label(hdr, text="HIGH END NOTES", fg="#4cc9f0", bg="#121212",
                      font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        self.sub = self.tk.Label(hdr, text="station-local • persistent", fg="#9a9a9a", bg="#121212",
                                 font=("Segoe UI", 9))
        self.sub.pack(anchor="w", padx=10, pady=(0, 10))

        body = self.tk.Frame(self.root, bg="#0e0e0e")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        # buttons
        btns = self.tk.Frame(body, bg="#0e0e0e")
        btns.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.tk.Button(btns, text="ADD FROM NOW PLAYING", command=self._add_from_now,
                       bg="#2a2a2a", fg="#ffffff", relief="flat", padx=10, pady=8).pack(side="left")
        self.tk.Button(btns, text="DELETE SELECTED", command=self._delete_selected,
                       bg="#2a2a2a", fg="#ffffff", relief="flat", padx=10, pady=8).pack(side="left", padx=(10, 0))

        # list + viewer
        self.listbox = self.tk.Listbox(body, bg="#121212", fg="#e8e8e8", height=8,
                                       highlightthickness=1, highlightbackground="#2a2a2a",
                                       selectbackground="#2a2a2a")
        self.listbox.grid(row=1, column=0, sticky="ew")
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._render_selected())

        self.viewer = self.tk.Text(body, wrap="word", bg="#111111", fg="#e8e8e8",
                                   highlightthickness=1, highlightbackground="#2a2a2a",
                                   font=("Segoe UI", 10))
        self.viewer.grid(row=2, column=0, sticky="nsew", pady=(8, 0))

        self.notes: List[Dict[str, Any]] = []

    def _add_from_now(self):
        if self.ui_cmd_q is None:
            return
        try:
            from runtime import MEM  # if you exposed it; else ignore
        except Exception:
            MEM = None

        # best-effort: rely on runtime having mem["ui_last_seg"] and ui_event_worker storing notes
        try:
            from runtime import mem as _mem  # type: ignore
            seg = _mem.get("ui_last_seg") if isinstance(_mem, dict) else None
        except Exception:
            seg = None

        if not isinstance(seg, dict):
            # create a blank note shell
            payload = {"title": "Manual note", "body": f"@ {time.strftime('%H:%M:%S')}", "tags": ["manual"]}
        else:
            payload = {
                "title": (seg.get("title") or seg.get("source") or "Now Playing")[:240],
                "body": (seg.get("body") or "")[:4000],
                "tags": [str(seg.get("source") or "").lower()],
                "source": seg.get("source") or "",
                "seg_id": seg.get("id") or seg.get("post_id") or "",
            }

        try:
            self.ui_cmd_q.put(("notes_add", payload))
        except Exception:
            pass

    def _delete_selected(self):
        if self.ui_cmd_q is None:
            return
        idx = None
        try:
            sel = self.listbox.curselection()
            if sel:
                idx = int(sel[0])
        except Exception:
            idx = None
        if idx is None or idx < 0 or idx >= len(self.notes):
            return
        nid = self.notes[idx].get("id")
        if nid:
            try:
                self.ui_cmd_q.put(("notes_delete", str(nid)))
            except Exception:
                pass

    def _render_selected(self):
        idx = None
        try:
            sel = self.listbox.curselection()
            if sel:
                idx = int(sel[0])
        except Exception:
            idx = None
        if idx is None or idx < 0 or idx >= len(self.notes):
            return
        n = self.notes[idx]
        txt = f"{n.get('title','')}\n\n{n.get('body','')}\n\n(tags: {n.get('tags')})"
        self.viewer.delete("1.0", "end")
        self.viewer.insert("1.0", txt)

    def on_update(self, data: Any):
        if not isinstance(data, dict):
            return
        if "notes" in data and isinstance(data["notes"], list):
            self.notes = [x for x in data["notes"] if isinstance(x, dict)]
            self.listbox.delete(0, "end")
            for n in self.notes:
                ts = n.get("ts") or 0
                ts_s = time.strftime("%H:%M:%S", time.localtime(int(ts)))
                title = (n.get("title") or "note")[:60]
                self.listbox.insert("end", f"{ts_s} • {title}")
            if self.notes:
                self.listbox.selection_clear(0, "end")
                self.listbox.selection_set(0)
                self._render_selected()
