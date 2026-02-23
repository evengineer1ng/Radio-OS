#!/usr/bin/env python3
"""
oracle_kingdom_tk.py — Desktop Tkinter Frontend for Oracle Kingdom

A standalone customtkinter interface for playing Oracle Kingdom.
Connects to the same OKController backend via shared queues (in-process)
or via the HTTP API (if running separately).

Design:
  - 3-column layout: Palace Map | Oracle Actions | Kingdom State
  - Atmospheric dark theme matching the web frontend
  - Full court layer integration
  - Voice / TTS: when running inside Radio OS (via register_widgets),
    bookmark.py's speak() handles TTS through sounddevice.  The
    ok_narrator_plugin meta-plugin drives narration automatically.
    A subtitle bar shows what's being spoken via subtitle_q.
    Standalone mode is text-only (no TTS without the full runtime).

Launch:
  1. As a Radio OS widget (register_widgets in oracle_kingdom.py)
  2. Standalone: python plugins/oracle_kingdom_tk.py
"""

from __future__ import annotations

import json
import math
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# ── Ensure plugins dir is importable ──────────────────────────
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
_root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)

try:
    import customtkinter as ctk
except ImportError:
    print("customtkinter not installed. Run: pip install customtkinter")
    sys.exit(1)

# ── Lazy game imports ─────────────────────────────────────────
_ok = None
_oc = None

def _import_game():
    global _ok, _oc
    if _ok is None:
        import oracle_kingdom as ok
        _ok = ok
    if _oc is None:
        import oracle_court as oc
        _oc = oc


# ═══════════════════════════════════════════════════════════════
# THEME CONSTANTS
# ═══════════════════════════════════════════════════════════════

COLORS = {
    "bg":           "#0d0d12",
    "bg_panel":     "#14141c",
    "bg_card":      "#1a1a26",
    "bg_hover":     "#22223a",
    "border":       "#2a2a40",
    "text":         "#d4d4e0",
    "text_muted":   "#7a7a9a",
    "accent":       "#c9a44c",
    "accent_dim":   "#8a7030",
    "danger":       "#cc4444",
    "success":      "#44aa88",
    "info":         "#55aaff",
    "warn":         "#ddaa55",
}

LOCATION_ICONS = {
    "COURTYARD":    "🏛",
    "WAR_CHAMBER":  "⚔",
    "TEMPLE":       "🕯",
    "HARBOR":       "⚓",
    "LIBRARY":      "📚",
    "OBSERVATORY":  "🔭",
    "TREASURY":     "💰",
    "RAMPARTS":     "🏰",
    "THRONE_ROOM":  "👑",
}

LOCATION_NAMES = {
    "COURTYARD":    "Courtyard",
    "WAR_CHAMBER":  "War Chamber",
    "TEMPLE":       "Temple",
    "HARBOR":       "Harbor",
    "LIBRARY":      "Library",
    "OBSERVATORY":  "Observatory",
    "TREASURY":     "Treasury",
    "RAMPARTS":     "Ramparts",
    "THRONE_ROOM":  "Throne Room",
}


# ═══════════════════════════════════════════════════════════════
# TRAIT SLIDER PANEL (Character Creation)
# ═══════════════════════════════════════════════════════════════

class TraitSliderPanel(ctk.CTkFrame):
    """Oracle trait allocation panel."""

    TRAITS = [
        "clarity", "conviction", "empathy", "severity", "ambition",
        "humility", "self_belief", "doubt", "paranoia", "charisma",
    ]
    POOL = 250
    TRAIT_MIN = 5
    TRAIT_MAX = 50

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=COLORS["bg_panel"], **kw)
        self.sliders: Dict[str, ctk.CTkSlider] = {}
        self.labels: Dict[str, ctk.CTkLabel] = {}
        self._build()

    def _build(self):
        ctk.CTkLabel(
            self, text="Shape Your Oracle",
            font=("Helvetica", 20, "bold"),
            text_color=COLORS["accent"],
        ).pack(pady=(10, 2))

        ctk.CTkLabel(
            self, text="Allocate 250 points across ten traits.",
            font=("Helvetica", 12),
            text_color=COLORS["text_muted"],
        ).pack(pady=(0, 10))

        for trait in self.TRAITS:
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=2)

            ctk.CTkLabel(
                row, text=trait.replace("_", " ").title(),
                font=("Helvetica", 12),
                text_color=COLORS["text_muted"],
                width=100, anchor="w",
            ).pack(side="left")

            slider = ctk.CTkSlider(
                row,
                from_=self.TRAIT_MIN, to=self.TRAIT_MAX,
                number_of_steps=self.TRAIT_MAX - self.TRAIT_MIN,
                width=200,
                progress_color=COLORS["accent_dim"],
                button_color=COLORS["accent"],
                command=lambda v, t=trait: self._on_slide(t, v),
            )
            slider.set(25)
            slider.pack(side="left", padx=8, expand=True, fill="x")
            self.sliders[trait] = slider

            lbl = ctk.CTkLabel(
                row, text="25", width=30,
                font=("Menlo", 12),
                text_color=COLORS["accent"],
            )
            lbl.pack(side="right")
            self.labels[trait] = lbl

        self.pool_label = ctk.CTkLabel(
            self, text="Points remaining: 0",
            font=("Helvetica", 13),
            text_color=COLORS["text_muted"],
        )
        self.pool_label.pack(pady=8)
        self._update_pool()

    def _on_slide(self, trait: str, val: float):
        int_val = int(round(val))
        self.labels[trait].configure(text=str(int_val))
        self._update_pool()

    def _update_pool(self):
        total = sum(int(round(s.get())) for s in self.sliders.values())
        remaining = self.POOL - total
        color = COLORS["accent"] if remaining == 0 else COLORS["danger"]
        self.pool_label.configure(
            text=f"Points remaining: {remaining}",
            text_color=color,
        )

    def get_allocation(self) -> Optional[Dict[str, int]]:
        alloc = {t: int(round(s.get())) for t, s in self.sliders.items()}
        if sum(alloc.values()) != self.POOL:
            return None
        return alloc

    def apply_preset(self, name: str):
        presets = {
            "balanced": {t: 25 for t in self.TRAITS},
            "tyrant": dict(clarity=15, conviction=40, empathy=8, severity=45,
                           ambition=40, humility=5, self_belief=35, doubt=10,
                           paranoia=35, charisma=17),
            "mystic": dict(clarity=35, conviction=20, empathy=30, severity=10,
                           ambition=15, humility=35, self_belief=30, doubt=35,
                           paranoia=10, charisma=30),
            "diplomat": dict(clarity=30, conviction=20, empathy=40, severity=10,
                             ambition=20, humility=30, self_belief=25, doubt=15,
                             paranoia=15, charisma=45),
        }
        p = presets.get(name)
        if not p:
            return
        for t, v in p.items():
            self.sliders[t].set(v)
            self.labels[t].configure(text=str(v))
        self._update_pool()


# ═══════════════════════════════════════════════════════════════
# LOCATION MAP PANEL
# ═══════════════════════════════════════════════════════════════

class LocationPanel(ctk.CTkFrame):
    """Palace location grid + current location info."""

    def __init__(self, master, on_move_callback, **kw):
        super().__init__(master, fg_color=COLORS["bg_panel"], **kw)
        self.on_move = on_move_callback
        self.buttons: Dict[str, ctk.CTkButton] = {}
        self.current_loc = "THRONE_ROOM"
        self._build()

    def _build(self):
        ctk.CTkLabel(
            self, text="PALACE",
            font=("Helvetica", 11, "bold"),
            text_color=COLORS["text_muted"],
        ).pack(pady=(8, 4))

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=6)

        locs = list(LOCATION_NAMES.keys())
        for i, loc_id in enumerate(locs):
            r, c = divmod(i, 2)
            btn = ctk.CTkButton(
                grid,
                text=f"{LOCATION_ICONS.get(loc_id, '•')}\n{LOCATION_NAMES[loc_id]}",
                font=("Helvetica", 10),
                width=90, height=50,
                fg_color=COLORS["bg_card"],
                hover_color=COLORS["bg_hover"],
                border_color=COLORS["border"],
                border_width=1,
                text_color=COLORS["text_muted"],
                command=lambda lid=loc_id: self.on_move(lid),
            )
            btn.grid(row=r, column=c, padx=2, pady=2, sticky="nsew")
            self.buttons[loc_id] = btn
            grid.columnconfigure(c, weight=1)

        # Current location info
        self.loc_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=6)
        self.loc_frame.pack(fill="x", padx=6, pady=(8, 4))

        self.loc_name_lbl = ctk.CTkLabel(
            self.loc_frame, text="Throne Room",
            font=("Helvetica", 13, "bold"),
            text_color=COLORS["accent"],
        )
        self.loc_name_lbl.pack(padx=8, pady=(6, 0), anchor="w")

        self.loc_desc_lbl = ctk.CTkLabel(
            self.loc_frame, text="Formal silence. All factions attend.",
            font=("Helvetica", 11),
            text_color=COLORS["text_muted"],
            wraplength=190,
        )
        self.loc_desc_lbl.pack(padx=8, pady=(0, 6), anchor="w")

        self.set_current("THRONE_ROOM")

    def set_current(self, loc_id: str):
        self.current_loc = loc_id
        for lid, btn in self.buttons.items():
            if lid == loc_id:
                btn.configure(
                    border_color=COLORS["accent"],
                    text_color=COLORS["accent"],
                    fg_color=COLORS["bg_hover"],
                )
            else:
                btn.configure(
                    border_color=COLORS["border"],
                    text_color=COLORS["text_muted"],
                    fg_color=COLORS["bg_card"],
                )
        self.loc_name_lbl.configure(text=LOCATION_NAMES.get(loc_id, loc_id))

        descs = {
            "COURTYARD": "Open air, public gaze. Merchants call, dissidents murmur.",
            "WAR_CHAMBER": "Maps and steel. Generals speak in certainties.",
            "TEMPLE": "Incense and whispered prayers. Faith is tested.",
            "HARBOR": "Salt air and foreign tongues. Wealth on the tide.",
            "LIBRARY": "Dusty silence, sharp minds. Knowledge challenges tradition.",
            "OBSERVATORY": "Stars and long silences. Time in epochs.",
            "TREASURY": "Coins counted, ledgers balanced. Prosperity is arithmetic.",
            "RAMPARTS": "Wind and watchfires. The world beyond is threatening.",
            "THRONE_ROOM": "Formal silence. All factions attend. Every word is weighed.",
        }
        self.loc_desc_lbl.configure(text=descs.get(loc_id, ""))


# ═══════════════════════════════════════════════════════════════
# BAR WIDGET
# ═══════════════════════════════════════════════════════════════

class StatBar(ctk.CTkFrame):
    """A labeled progress bar for kingdom metrics."""

    def __init__(self, master, label: str, value: float = 50,
                 invert: bool = False, **kw):
        super().__init__(master, fg_color="transparent", height=20, **kw)
        self.invert = invert

        self.lbl = ctk.CTkLabel(
            self, text=label, font=("Helvetica", 10),
            text_color=COLORS["text_muted"], width=70, anchor="w",
        )
        self.lbl.pack(side="left")

        self.bar = ctk.CTkProgressBar(
            self, width=100, height=6,
            progress_color=COLORS["success"],
            fg_color=COLORS["border"],
        )
        self.bar.pack(side="left", padx=4, expand=True, fill="x")

        self.val_lbl = ctk.CTkLabel(
            self, text=str(int(value)),
            font=("Menlo", 10),
            text_color=COLORS["text_muted"],
            width=28, anchor="e",
        )
        self.val_lbl.pack(side="right")

        self.set_value(value)

    def set_value(self, val: float):
        pct = max(0, min(1, val / 100.0))
        self.bar.set(pct)
        self.val_lbl.configure(text=str(int(val)))

        if self.invert:
            color = COLORS["danger"] if val > 60 else COLORS["warn"] if val > 30 else COLORS["success"]
        else:
            color = COLORS["success"] if val > 60 else COLORS["warn"] if val > 30 else COLORS["danger"]
        self.bar.configure(progress_color=color)


# ═══════════════════════════════════════════════════════════════
# DECREE PANEL
# ═══════════════════════════════════════════════════════════════

class DecreePanel(ctk.CTkFrame):
    """Displays decree options and lets the user choose."""

    def __init__(self, master, on_generate, on_select, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.on_generate = on_generate
        self.on_select = on_select
        self.option_buttons: List[ctk.CTkButton] = []
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x")
        ctk.CTkLabel(
            hdr, text="THE COURT AWAITS",
            font=("Helvetica", 11, "bold"),
            text_color=COLORS["text_muted"],
        ).pack(side="left")
        ctk.CTkButton(
            hdr, text="Generate Options",
            font=("Helvetica", 11),
            width=120, height=28,
            fg_color=COLORS["bg_card"],
            hover_color=COLORS["bg_hover"],
            border_color=COLORS["accent_dim"],
            border_width=1,
            text_color=COLORS["accent"],
            command=self.on_generate,
        ).pack(side="right")

        self.options_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.options_frame.pack(fill="both", expand=True, pady=(6, 0))

        self.placeholder = ctk.CTkLabel(
            self.options_frame,
            text="No decree options yet. Click 'Generate Options'.",
            font=("Helvetica", 12),
            text_color=COLORS["text_muted"],
        )
        self.placeholder.pack(pady=20)

    def show_options(self, options: list):
        for w in self.options_frame.winfo_children():
            w.destroy()
        self.option_buttons.clear()

        if not options:
            ctk.CTkLabel(
                self.options_frame, text="No options available.",
                text_color=COLORS["text_muted"],
            ).pack(pady=20)
            return

        for idx, opt in enumerate(options):
            ctx = opt.get("court_context", {})
            is_silence = ctx.get("is_silence", False)
            text = opt.get("text", "...")
            tone = opt.get("tone", "PRACTICAL")
            agent = ctx.get("proposing_agent_id", "")
            agent_tone = ctx.get("agent_tone", "")

            card = ctk.CTkFrame(
                self.options_frame,
                fg_color=COLORS["bg_card"],
                border_color=COLORS["border"],
                border_width=1,
                corner_radius=6,
            )
            card.pack(fill="x", pady=2)

            if is_silence:
                ctk.CTkLabel(
                    card, text="... (Remain Silent)",
                    font=("Helvetica", 13, "italic"),
                    text_color=COLORS["text_muted"],
                ).pack(padx=12, pady=8)
            else:
                if agent:
                    ctk.CTkLabel(
                        card,
                        text=f"{agent.replace('court_','')} speaks {agent_tone}ly:",
                        font=("Helvetica", 10, "italic"),
                        text_color=COLORS["text_muted"],
                    ).pack(padx=12, pady=(6, 0), anchor="w")

                ctk.CTkLabel(
                    card, text=text,
                    font=("Helvetica", 12),
                    text_color=COLORS["text"],
                    wraplength=400, anchor="w", justify="left",
                ).pack(padx=12, pady=(2, 2), anchor="w")

                ctk.CTkLabel(
                    card, text=f"[{tone}]",
                    font=("Helvetica", 9),
                    text_color=COLORS["text_muted"],
                ).pack(padx=12, pady=(0, 6), anchor="w")

            btn = ctk.CTkButton(
                card, text="Choose",
                font=("Helvetica", 10),
                width=60, height=24,
                fg_color=COLORS["accent_dim"],
                hover_color=COLORS["accent"],
                text_color="#111",
                command=lambda i=idx: self.on_select(i),
            )
            btn.pack(padx=12, pady=(0, 6), anchor="e")


# ═══════════════════════════════════════════════════════════════
# INSPECTION PANEL  (Causal Ledger viewer)
# ═══════════════════════════════════════════════════════════════

# Mapping from the display label in stat_bars to the internal variable name
STAT_BAR_VARIABLES = {
    "Food":           "food_stores",
    "Trade":          "trade_volume",
    "Infrastructure": "infrastructure",
    "Cohesion":       "cohesion",
    "Hope":           "hope_level",
    "Fear":           "fear_level",
    "Tension":        "class_tension",
    "Legitimacy":     "legitimacy",
    "Corruption":     "corruption",
    "Enforcement":    "enforcement_capacity",
    "Threat":         "external_threat",
    "Faith":          "public_faith",
    "Divergence":     "interpretation_divergence",
}


class InspectionPanel(ctk.CTkToplevel):
    """
    Floating causal-ledger inspection window.

    Click any variable button to see a timeline of every change to that
    variable — what caused each shift and when.  'Why did legitimacy
    collapse?' — this answers it.
    """

    def __init__(self, master, cmd_q: queue.Queue, **kw):
        super().__init__(master, **kw)
        self.cmd_q = cmd_q
        self.title("Kingdom Inspection")
        self.geometry("560x520")
        self.configure(fg_color=COLORS["bg"])
        self.resizable(True, True)

        # Allow the window to stay open while playing
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

        self._build()

    def _build(self):
        # ── Header ──
        hdr = ctk.CTkFrame(self, fg_color=COLORS["bg_panel"], height=36, corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(
            hdr, text="🔍 Causal Ledger — Why did this happen?",
            font=("Helvetica", 12, "bold"),
            text_color=COLORS["accent"],
        ).pack(side="left", padx=12, pady=6)

        # ── Variable picker ──
        picker = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=0)
        picker.pack(fill="x", padx=8, pady=(8, 0))

        ctk.CTkLabel(
            picker, text="Select a variable to trace:",
            font=("Helvetica", 10),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=8, pady=(6, 2))

        btn_grid = ctk.CTkFrame(picker, fg_color="transparent")
        btn_grid.pack(fill="x", padx=8, pady=(0, 6))

        self._var_buttons: Dict[str, ctk.CTkButton] = {}
        vars_ordered = list(STAT_BAR_VARIABLES.items())
        for i, (label, var) in enumerate(vars_ordered):
            r, c = divmod(i, 4)
            btn = ctk.CTkButton(
                btn_grid,
                text=label,
                font=("Helvetica", 9),
                width=90, height=22,
                fg_color=COLORS["bg_panel"],
                hover_color=COLORS["bg_hover"],
                border_color=COLORS["border"],
                border_width=1,
                text_color=COLORS["text_muted"],
                command=lambda v=var, lbl=label: self._request_trace(v, lbl),
            )
            btn.grid(row=r, column=c, padx=2, pady=2, sticky="ew")
            btn_grid.columnconfigure(c, weight=1)
            self._var_buttons[label] = btn

        # ── Current variable label ──
        self._active_var_lbl = ctk.CTkLabel(
            self, text="No variable selected.",
            font=("Helvetica", 11, "italic"),
            text_color=COLORS["text_muted"],
        )
        self._active_var_lbl.pack(anchor="w", padx=12, pady=(8, 0))

        # ── Causal history text ──
        self._trace_box = ctk.CTkTextbox(
            self,
            font=("Menlo", 10),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["text"],
            state="disabled",
        )
        self._trace_box.pack(fill="both", expand=True, padx=8, pady=8)

    def _request_trace(self, variable: str, label: str):
        """Ask the controller for causal history of this variable."""
        self._active_var_lbl.configure(
            text=f"Tracing: {label}  ({variable})",
            text_color=COLORS["accent"],
        )
        # Highlight active button
        for lbl, btn in self._var_buttons.items():
            if lbl == label:
                btn.configure(border_color=COLORS["accent"], text_color=COLORS["accent"])
            else:
                btn.configure(border_color=COLORS["border"], text_color=COLORS["text_muted"])

        self._set_text("Loading…")
        self.cmd_q.put({"action": "causal_trace", "variable": variable, "last_n": 60})
        self.cmd_q.put({"action": "causal_explain", "variable": variable})

    def show_trace(self, variable: str, history: list, total_edges: int):
        """Render a variable_history list into the text box."""
        if not history:
            self._set_text(f"No causal history recorded for '{variable}' yet.\n"
                           "Play a few ticks and then inspect again.")
            return

        lines = [
            f"Variable: {variable}",
            f"Ledger size: {total_edges} total edges | showing last {len(history)}",
            "",
            f"{'Tick':>6}  {'Delta':>8}  {'Source Type':14}  {'Source ID'}",
            "─" * 60,
        ]
        cumulative = 0.0
        for e in history:
            delta = e.get("delta", 0.0)
            cumulative += delta
            sign = "+" if delta >= 0 else ""
            source_type = e.get("source_type", "?")[:14]
            source_id = e.get("source_id", "?")[:30]
            tick = e.get("tick", 0)
            lines.append(f"{tick:>6}  {sign}{delta:>7.2f}  {source_type:<14}  {source_id}")

        lines += ["─" * 60, f"{'Net (shown):':>30}  {'+' if cumulative >= 0 else ''}{cumulative:.2f}"]
        self._set_text("\n".join(lines))

    def show_explanation(self, variable: str, explanation: str):
        """Append a human-readable explanation below the trace."""
        current = self._trace_box.get("1.0", "end").rstrip()
        if "EXPLANATION" not in current:
            full = current + "\n\n── EXPLANATION ──\n" + explanation
            self._set_text(full)

    def _set_text(self, text: str):
        self._trace_box.configure(state="normal")
        self._trace_box.delete("1.0", "end")
        self._trace_box.insert("end", text)
        self._trace_box.configure(state="disabled")


# ═══════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════

class OracleKingdomApp(ctk.CTk):
    """Standalone Oracle Kingdom desktop client."""

    def __init__(self):
        super().__init__()
        self.title("Oracle Kingdom")
        self.geometry("1100x700")
        self.configure(fg_color=COLORS["bg"])
        ctk.set_appearance_mode("dark")

        _import_game()

        # ── Game state ──
        self.controller = None
        self.court_state = None
        self.runtime_stub: Dict[str, Any] = {
            "ok_cmd_q": queue.Queue(),
            "ok_ui_q": queue.Queue(),
            "log": lambda tag, msg: print(f"[{tag}] {msg}"),
            "STATION_DIR": os.path.join(_root, "saves"),
        }
        self.decree_options: list = []

        # ── Screens ──
        self.current_screen = None
        self.screens: Dict[str, ctk.CTkFrame] = {}
        self._build_title_screen()
        self._build_game_screen()
        self._show_screen("title")

        # ── Inspection panel (lazy — created on first open) ──
        self._inspection_panel: Optional[InspectionPanel] = None

        # ── UI poll timer ──
        self._poll_ui()

    # ── Screen management ─────────────────────────────────────

    def _show_screen(self, name: str):
        if self.current_screen and self.current_screen in self.screens:
            self.screens[self.current_screen].pack_forget()
        self.current_screen = name
        self.screens[name].pack(fill="both", expand=True)

    # ── Title Screen ──────────────────────────────────────────

    def _build_title_screen(self):
        frame = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        self.screens["title"] = frame

        center = ctk.CTkFrame(frame, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            center, text="👁",
            font=("Helvetica", 64),
        ).pack(pady=(0, 8))

        ctk.CTkLabel(
            center, text="Oracle Kingdom",
            font=("Helvetica", 36, "bold"),
            text_color=COLORS["accent"],
        ).pack()

        ctk.CTkLabel(
            center, text="Your words shape a world you cannot fully see.",
            font=("Helvetica", 14, "italic"),
            text_color=COLORS["text_muted"],
        ).pack(pady=(4, 24))

        btn_row = ctk.CTkFrame(center, fg_color="transparent")
        btn_row.pack()

        ctk.CTkButton(
            btn_row, text="New Kingdom",
            font=("Helvetica", 14, "bold"),
            fg_color=COLORS["accent"],
            text_color="#111",
            hover_color="#d4b05c",
            width=140, height=40,
            command=lambda: self._show_screen("creation"),
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_row, text="Continue",
            font=("Helvetica", 14),
            fg_color=COLORS["bg_card"],
            border_color=COLORS["accent_dim"],
            border_width=1,
            text_color=COLORS["text"],
            width=140, height=40,
            command=self._load_game,
        ).pack(side="left", padx=8)

        ctk.CTkLabel(
            center, text="Radio OS · Desktop Edition",
            font=("Helvetica", 10),
            text_color=COLORS["text_muted"],
        ).pack(pady=(20, 0))

        # ── Creation sub-screen ──
        creation = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        self.screens["creation"] = creation

        self.trait_panel = TraitSliderPanel(creation)
        self.trait_panel.pack(fill="both", expand=True, padx=20, pady=10)

        preset_row = ctk.CTkFrame(creation, fg_color="transparent")
        preset_row.pack(pady=4)
        for p in ["balanced", "tyrant", "mystic", "diplomat"]:
            ctk.CTkButton(
                preset_row, text=p.title(),
                font=("Helvetica", 10),
                width=70, height=26,
                fg_color=COLORS["bg_card"],
                hover_color=COLORS["bg_hover"],
                text_color=COLORS["text_muted"],
                command=lambda n=p: self.trait_panel.apply_preset(n),
            ).pack(side="left", padx=4)

        action_row = ctk.CTkFrame(creation, fg_color="transparent")
        action_row.pack(pady=(8, 16))

        ctk.CTkButton(
            action_row, text="← Back",
            font=("Helvetica", 12),
            fg_color="transparent",
            text_color=COLORS["text_muted"],
            width=80,
            command=lambda: self._show_screen("title"),
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            action_row, text="Begin",
            font=("Helvetica", 14, "bold"),
            fg_color=COLORS["accent"],
            text_color="#111",
            width=120, height=36,
            command=self._create_game,
        ).pack(side="right", padx=8)

    # ── Game Screen ───────────────────────────────────────────

    def _build_game_screen(self):
        frame = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        self.screens["game"] = frame

        # ── Header ──
        hdr = ctk.CTkFrame(frame, fg_color=COLORS["bg_panel"], height=36, corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        self.hdr_name = ctk.CTkLabel(
            hdr, text="Kingdom", font=("Helvetica", 12, "bold"),
            text_color=COLORS["accent"],
        )
        self.hdr_name.pack(side="left", padx=12)

        self.hdr_info = ctk.CTkLabel(
            hdr, text="Year 1 · Tick 0 · ♥ 50",
            font=("Helvetica", 11),
            text_color=COLORS["text_muted"],
        )
        self.hdr_info.pack(side="left", padx=12)

        btn_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_frame.pack(side="right", padx=8)

        self.pause_btn = ctk.CTkButton(
            btn_frame, text="▶ Resume", width=80, height=26,
            font=("Helvetica", 10),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["text"],
            command=self._toggle_pause,
        )
        self.pause_btn.pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="⏭ Tick", width=60, height=26,
            font=("Helvetica", 10),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["text"],
            command=self._manual_tick,
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="💾 Save", width=60, height=26,
            font=("Helvetica", 10),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["text"],
            command=self._save_game,
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="🔍 Inspect", width=80, height=26,
            font=("Helvetica", 10),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["info"],
            command=self._open_inspection_panel,
        ).pack(side="left", padx=2)

        # ── Subtitle bar (shows TTS narration from bookmark.py) ──
        sub_bar = ctk.CTkFrame(frame, fg_color="#0a0a10", height=24, corner_radius=0)
        sub_bar.pack(fill="x")
        sub_bar.pack_propagate(False)

        self.subtitle_indicator = ctk.CTkLabel(
            sub_bar, text="○", font=("Helvetica", 10),
            text_color=COLORS["text_muted"], width=16,
        )
        self.subtitle_indicator.pack(side="left", padx=(12, 4))

        self.subtitle_lbl = ctk.CTkLabel(
            sub_bar, text="",
            font=("Georgia", 11, "italic"),
            text_color=COLORS["text"],
            anchor="w",
        )
        self.subtitle_lbl.pack(side="left", fill="x", expand=True)

        self._subtitle_clear_id = None

        # ── 3-Column Body ──
        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # Left: Location map
        self.loc_panel = LocationPanel(body, on_move_callback=self._move_oracle)
        self.loc_panel.grid(row=0, column=0, sticky="nsw", padx=(4, 0), pady=4)

        # Center: Decrees + Events
        center = ctk.CTkFrame(body, fg_color="transparent")
        center.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)

        self.decree_panel = DecreePanel(
            center,
            on_generate=self._generate_decrees,
            on_select=self._select_decree,
        )
        self.decree_panel.pack(fill="x")

        ctk.CTkLabel(
            center, text="INNER MONOLOGUE",
            font=("Helvetica", 10, "bold"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", pady=(12, 2))

        self.thought_text = ctk.CTkTextbox(
            center, height=80,
            font=("Georgia", 11),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["text_muted"],
            state="disabled",
        )
        self.thought_text.pack(fill="x")

        ctk.CTkLabel(
            center, text="EVENTS",
            font=("Helvetica", 10, "bold"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", pady=(8, 2))

        self.event_text = ctk.CTkTextbox(
            center, height=120,
            font=("Helvetica", 10),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["text_muted"],
            state="disabled",
        )
        self.event_text.pack(fill="both", expand=True)

        # Right: Kingdom state
        right = ctk.CTkScrollableFrame(
            body, fg_color=COLORS["bg_panel"], width=260,
        )
        right.grid(row=0, column=2, sticky="nse", padx=(0, 4), pady=4)

        ctk.CTkLabel(
            right, text="KINGDOM",
            font=("Helvetica", 10, "bold"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", pady=(4, 2))

        self.stat_bars: Dict[str, StatBar] = {}
        metrics = [
            ("Food", False), ("Trade", False), ("Infrastructure", False),
            ("Cohesion", False), ("Hope", False), ("Fear", True),
            ("Tension", True), ("Legitimacy", False), ("Corruption", True),
            ("Enforcement", False), ("Threat", True),
            ("Faith", False), ("Divergence", True),
        ]
        for name, inv in metrics:
            bar = StatBar(right, label=name, invert=inv)
            bar.pack(fill="x", padx=4, pady=1)
            self.stat_bars[name] = bar
            # Click the label to open inspection panel for that variable
            var = STAT_BAR_VARIABLES.get(name)
            if var:
                bar.lbl.configure(cursor="hand2")
                bar.lbl.bind("<Button-1>", lambda e, v=var, n=name: self._inspect_var(v, n))

        ctk.CTkLabel(
            right, text="ORACLE MIND",
            font=("Helvetica", 10, "bold"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", pady=(10, 2))

        self.psych_bars: Dict[str, StatBar] = {}
        for name in ["Ego", "Stress", "Hope", "Dread"]:
            bar = StatBar(right, label=name)
            bar.pack(fill="x", padx=4, pady=1)
            self.psych_bars[name] = bar

        self.archetype_lbl = ctk.CTkLabel(
            right, text="Unknown",
            font=("Helvetica", 13, "italic"),
            text_color=COLORS["accent"],
        )
        self.archetype_lbl.pack(pady=(10, 4))

    # ── Game Logic ────────────────────────────────────────────

    def _create_game(self):
        alloc = self.trait_panel.get_allocation()
        if not alloc:
            return

        # Start controller
        self.controller = _ok.OKController(self.runtime_stub, {})
        self.controller.start()

        # Create game
        self.runtime_stub["ok_cmd_q"].put({
            "action": "new_game",
            "oracle_allocation": alloc,
            "time_preset": "week_per_year",
        })
        self.after(500, self._init_court_and_show)

    def _init_court_and_show(self):
        if self.controller and self.controller.state:
            self.court_state = _oc.CourtBuilder.build(
                self.controller.state.player_kingdom
            )
            self._show_screen("game")
            self._refresh_display()

    def _load_game(self):
        self.controller = _ok.OKController(self.runtime_stub, {})
        self.controller.start()
        self.runtime_stub["ok_cmd_q"].put({"action": "load"})
        # Give the controller thread time to load and compute absence ticks,
        # then check if reconstruction is needed before entering the game.
        self.after(600, self._check_reconstruction_after_load)

    def _check_reconstruction_after_load(self):
        """After loading, fast-forward any absence ticks silently then enter game."""
        if not self.controller or not self.controller.state:
            self.after(200, self._check_reconstruction_after_load)
            return

        if self.controller._reconstruction_machine:
            # Run all phases instantly (no ritual blocking) and show a brief summary
            self._show_reconstruction_summary()
        else:
            self._try_load_court()

    def _show_reconstruction_summary(self):
        """
        Show a dismissible dialog summarising what happened during absence.
        Runs reconstruction in background; 'Enter Kingdom' or 'Skip' closes it.
        """
        if not self.controller or not self.controller._reconstruction_machine:
            self._try_load_court()
            return

        # ── Build the dialog ──
        dlg = ctk.CTkToplevel(self)
        dlg.title("The Oracle Returns")
        dlg.geometry("520x420")
        dlg.configure(fg_color=COLORS["bg"])
        dlg.grab_set()
        dlg.transient(self)

        ctk.CTkLabel(
            dlg, text="While You Were Gone…",
            font=("Helvetica", 20, "bold"),
            text_color=COLORS["accent"],
        ).pack(pady=(20, 4))

        years_lbl = ctk.CTkLabel(
            dlg, text="Calculating absence…",
            font=("Helvetica", 12, "italic"),
            text_color=COLORS["text_muted"],
        )
        years_lbl.pack()

        summary_box = ctk.CTkTextbox(
            dlg, height=220,
            font=("Helvetica", 11),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["text"],
            state="disabled",
        )
        summary_box.pack(fill="x", padx=20, pady=10)

        enter_btn = ctk.CTkButton(
            dlg, text="Enter Kingdom",
            font=("Helvetica", 13, "bold"),
            fg_color=COLORS["accent"],
            text_color="#111",
            width=160, height=36,
            state="disabled",
            command=lambda: self._finish_load(dlg),
        )
        enter_btn.pack(pady=4)

        ctk.CTkButton(
            dlg, text="Skip",
            font=("Helvetica", 11),
            fg_color="transparent",
            text_color=COLORS["text_muted"],
            command=lambda: self._finish_load(dlg),
        ).pack()

        # ── Run reconstruction in a background thread ──
        def _run():
            if not self.controller or not self.controller._reconstruction_machine:
                return
            machine = self.controller._reconstruction_machine
            results = machine.run_all_phases()
            # Finalize so last_session_ts is stamped and reconstruction won't re-fire
            _ok.AbsenceReconstructor.finalize_reconstruction(
                self.controller.state, machine
            )
            self.controller._reconstruction_machine = None
            self.controller._reconstruction_pending = 0

            summary = machine.summary()
            total_years = summary.get("total_years", 0)
            total_events = summary.get("total_events", 0)
            agg = summary.get("aggregate_changes", {})
            crossings = summary.get("threshold_crossings", [])

            lines: list = [
                f"The kingdom advanced {total_years:.1f} years in your absence.",
                f"{total_events} events unfolded without an Oracle.",
                "",
            ]

            if agg:
                notable = sorted(agg.items(), key=lambda x: abs(x[1]), reverse=True)[:6]
                lines.append("Notable changes:")
                for var, delta in notable:
                    sign = "+" if delta > 0 else ""
                    lines.append(f"  {var.replace('_', ' ').title():22s}  {sign}{delta:.1f}")
                lines.append("")

            if crossings:
                lines.append("Thresholds crossed:")
                for c in crossings[:4]:
                    lines.append(f"  • {c}")

            text = "\n".join(lines)
            # Update UI from main thread
            self.after(0, lambda: _update_ui(total_years, text))

        def _update_ui(total_years: float, text: str):
            years_lbl.configure(text=f"{total_years:.1f} in-game years elapsed since last session")
            summary_box.configure(state="normal")
            summary_box.delete("1.0", "end")
            summary_box.insert("end", text)
            summary_box.configure(state="disabled")
            enter_btn.configure(state="normal")

        threading.Thread(target=_run, daemon=True).start()

    def _finish_load(self, dlg: ctk.CTkToplevel):
        """Close the reconstruction dialog and enter the game."""
        try:
            dlg.grab_release()
            dlg.destroy()
        except Exception:
            pass
        self._try_load_court()

    def _try_load_court(self):
        if self.controller and self.controller.state:
            self.court_state = _oc.CourtBuilder.build(
                self.controller.state.player_kingdom
            )
            self._show_screen("game")
            self._refresh_display()

    def _save_game(self):
        if self.controller:
            self.runtime_stub["ok_cmd_q"].put({"action": "save"})

    def _toggle_pause(self):
        if not self.controller:
            return
        if self.controller.paused:
            self.runtime_stub["ok_cmd_q"].put({"action": "resume"})
            self.pause_btn.configure(text="⏸ Pause")
        else:
            self.runtime_stub["ok_cmd_q"].put({"action": "pause"})
            self.pause_btn.configure(text="▶ Resume")

    def _open_inspection_panel(self):
        """Open (or focus) the causal ledger inspection window."""
        if self._inspection_panel is None or not self._inspection_panel.winfo_exists():
            self._inspection_panel = InspectionPanel(
                self, cmd_q=self.runtime_stub["ok_cmd_q"]
            )
        else:
            self._inspection_panel.deiconify()
            self._inspection_panel.lift()

    def _inspect_var(self, variable: str, label: str):
        """Open inspection panel and immediately trace a specific variable."""
        self._open_inspection_panel()
        self._inspection_panel._request_trace(variable, label)

    def _manual_tick(self):
        if not self.controller:
            return
        self.runtime_stub["ok_cmd_q"].put({"action": "tick"})
        # Also tick the court
        if self.court_state and self.controller.state:
            with self.controller.state_lock:
                kingdom = self.controller.state.player_kingdom
                rng = _ok.SeededRNG(kingdom.seed).fork(f"court_tick_{kingdom.tick}")
                _oc.CourtEngine.tick(self.court_state, kingdom, rng)
                kingdom.oracle_archetype = self.court_state.oracle_identity.archetype.name
        self.after(200, self._refresh_display)

    def _move_oracle(self, loc_id: str):
        if not self.court_state or not self.controller or not self.controller.state:
            return
        try:
            loc = _oc.LocationId[loc_id]
        except KeyError:
            return
        with self.controller.state_lock:
            _oc.CourtEngine.move_oracle(
                self.court_state, self.controller.state.player_kingdom, loc
            )
        self.loc_panel.set_current(loc_id)
        self._refresh_display()

    def _generate_decrees(self):
        if not self.court_state or not self.controller or not self.controller.state:
            return
        with self.controller.state_lock:
            kingdom = self.controller.state.player_kingdom
            rng = _ok.SeededRNG(kingdom.seed).fork(f"court_decrees_{kingdom.tick}")
            options = _oc.CourtDecreeGenerator.generate(
                self.court_state, kingdom, rng, count=4
            )
            self.decree_options = options
        self.decree_panel.show_options([o.to_dict() for o in options])

    def _select_decree(self, idx: int):
        if idx < 0 or idx >= len(self.decree_options):
            return
        option = self.decree_options[idx]
        if not self.controller or not self.controller.state:
            return
        with self.controller.state_lock:
            kingdom = self.controller.state.player_kingdom
            rng = _ok.SeededRNG(kingdom.seed).fork(f"court_prop_{kingdom.tick}")
            _oc.CourtPropagationBridge.propagate_court_decree(
                self.court_state, kingdom, option, rng
            )
            tick_rng = _ok.SeededRNG(kingdom.seed).fork(f"court_tick_post_{kingdom.tick}")
            _oc.CourtEngine.tick(self.court_state, kingdom, tick_rng)
            kingdom.oracle_archetype = self.court_state.oracle_identity.archetype.name

        self.decree_options = []
        self.decree_panel.show_options([])
        self.after(200, self._refresh_display)

    # ── Display Refresh ───────────────────────────────────────

    def _refresh_display(self):
        if not self.controller or not self.controller.state:
            return

        with self.controller.state_lock:
            pk = self.controller.state.player_kingdom

            # Header
            self.hdr_name.configure(text=pk.name or "Kingdom")
            composite = pk.health.composite
            self.hdr_info.configure(
                text=f"Year {pk.world_year} · Tick {pk.tick} · ♥ {composite:.0f}"
            )

            # Layer bars
            if pk.physical:
                self.stat_bars["Food"].set_value(pk.physical.food_stores)
                self.stat_bars["Trade"].set_value(pk.physical.trade_volume)
                self.stat_bars["Infrastructure"].set_value(pk.physical.infrastructure)
            if pk.social:
                self.stat_bars["Cohesion"].set_value(pk.social.cohesion)
                self.stat_bars["Hope"].set_value(pk.social.hope_level)
                self.stat_bars["Fear"].set_value(pk.social.fear_level)
                self.stat_bars["Tension"].set_value(pk.social.class_tension)
            if pk.political:
                self.stat_bars["Legitimacy"].set_value(pk.political.legitimacy)
                self.stat_bars["Corruption"].set_value(pk.political.corruption)
                self.stat_bars["Enforcement"].set_value(pk.political.enforcement_capacity)
                self.stat_bars["Threat"].set_value(pk.political.external_threat)
            if pk.belief:
                self.stat_bars["Faith"].set_value(pk.belief.public_faith)
                self.stat_bars["Divergence"].set_value(pk.belief.interpretation_divergence)

            # Oracle psychology
            o = pk.oracle
            self.psych_bars["Ego"].set_value(max(0, min(100, o.ego + 50)))
            self.psych_bars["Stress"].set_value(max(0, min(100, o.stress)))
            self.psych_bars["Hope"].set_value(max(0, min(100, o.hope + 50)))
            self.psych_bars["Dread"].set_value(max(0, min(100, o.dread)))

        # Court state
        if self.court_state:
            self.loc_panel.set_current(self.court_state.current_location.name)
            self.archetype_lbl.configure(
                text=self.court_state.oracle_identity.archetype.name
            )

            # Inner thoughts
            thoughts = self.court_state.inner_state.thought_log[-6:]
            if thoughts:
                self.thought_text.configure(state="normal")
                self.thought_text.delete("1.0", "end")
                for t in reversed(thoughts):
                    self.thought_text.insert("end", f"[{t.thought_type.name}] {t.text}\n")
                self.thought_text.configure(state="disabled")

    # ── UI Queue Poll ─────────────────────────────────────────

    def _poll_ui(self):
        """Check for UI events from the controller and subtitle updates."""
        ui_q = self.runtime_stub.get("ok_ui_q")
        if ui_q:
            try:
                while True:
                    msg = ui_q.get_nowait()
                    self._handle_ui_msg(msg)
            except queue.Empty:
                pass

        # Poll subtitle_q from bookmark.py runtime (if available)
        sub_q = self.runtime_stub.get("subtitle_q")
        if sub_q:
            try:
                while True:
                    txt = sub_q.get_nowait()
                    self._show_subtitle(txt)
            except queue.Empty:
                pass

        # Periodic refresh when game is running
        if self.current_screen == "game" and self.controller and not self.controller.paused:
            self._refresh_display()

        self.after(1000, self._poll_ui)

    def _show_subtitle(self, text: str):
        """Display subtitle text from TTS narration."""
        if text:
            self.subtitle_lbl.configure(text=text)
            self.subtitle_indicator.configure(text="♫", text_color=COLORS["accent"])
            # Auto-clear after 6 seconds of no update
            if self._subtitle_clear_id:
                self.after_cancel(self._subtitle_clear_id)
            self._subtitle_clear_id = self.after(
                6000, self._clear_subtitle
            )
        else:
            self._clear_subtitle()

    def _clear_subtitle(self):
        self.subtitle_lbl.configure(text="")
        self.subtitle_indicator.configure(text="○", text_color=COLORS["text_muted"])
        self._subtitle_clear_id = None

    def _handle_ui_msg(self, msg: dict):
        msg_type = msg.get("type", "")
        if msg_type == "event":
            data = msg.get("data", {})
            desc = data.get("description", "Event")
            self.event_text.configure(state="normal")
            self.event_text.insert("1.0", f"• {desc}\n")
            # Keep only last 50 lines
            lines = int(self.event_text.index("end-1c").split(".")[0])
            if lines > 50:
                self.event_text.delete("50.0", "end")
            self.event_text.configure(state="disabled")
        elif msg_type == "state_update":
            self._refresh_display()
        elif msg_type == "causal_trace":
            if self._inspection_panel and self._inspection_panel.winfo_exists():
                self._inspection_panel.show_trace(
                    variable=msg.get("variable", ""),
                    history=msg.get("history", []),
                    total_edges=msg.get("total_edges", 0),
                )
        elif msg_type == "causal_explanation":
            if self._inspection_panel and self._inspection_panel.winfo_exists():
                self._inspection_panel.show_explanation(
                    variable=msg.get("variable", ""),
                    explanation=msg.get("explanation", ""),
                )
        elif msg_type in ("reconstruction_start", "reconstruction_phase",
                          "reconstruction_complete", "load_error",
                          "speech_options", "inner_monologue"):
            # These are handled elsewhere or silently consumed here to
            # prevent queue build-up.
            pass


# ═══════════════════════════════════════════════════════════════
# STANDALONE ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = OracleKingdomApp()
    app.mainloop()
