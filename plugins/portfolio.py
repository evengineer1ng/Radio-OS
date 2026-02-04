import time
import requests
import hashlib
import random
from typing import Any, Dict, Optional, Tuple, List

PLUGIN_NAME = "portfolio_event"

# =====================================================
# Helpers
# =====================================================

def now_ts() -> int:
    return int(time.time())


def sha1(x: Any) -> str:
    return hashlib.sha1(str(x).encode("utf-8", errors="ignore")).hexdigest()


def clamp_text(t: str, n: int = 1400) -> str:
    t = (t or "").strip()
    if len(t) <= n:
        return t
    return t[: n - 3].rstrip() + "..."


def _as_float(x: Any) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None


def _fmt_pct(x: float) -> str:
    return f"{x*100:.2f}%"


def _fmt_money(x: float) -> str:
    ax = abs(x)
    if ax >= 1_000_000:
        return f"{x/1_000_000:.2f}M"
    if ax >= 1_000:
        return f"{x/1_000:.2f}K"
    return f"{x:.2f}"


def _fmt_signed_money(x: float) -> str:
    s = _fmt_money(x)
    return f"+{s}" if x >= 0 else s


def _safe(x: Any, default: str = "") -> str:
    try:
        if x is None:
            return default
        return str(x)
    except Exception:
        return default


# =====================================================
# Hyperliquid API
# =====================================================

def hl_fetch_state(base_url: str, user: str, timeout: int = 12) -> Optional[Dict[str, Any]]:
    try:
        r = requests.post(
            base_url.rstrip("/") + "/info",
            json={"type": "clearinghouseState", "user": user},
            timeout=timeout,
        )
        r.raise_for_status()
        j = r.json()
        return j if isinstance(j, dict) else None
    except Exception:
        return None


def hl_extract_equity_and_positions(state: Dict[str, Any]) -> Tuple[Optional[float], List[Dict[str, Any]]]:
    equity = None
    positions: List[Dict[str, Any]] = []

    ms = state.get("marginSummary") if isinstance(state, dict) else None
    if isinstance(ms, dict):
        equity = _as_float(ms.get("accountValue"))

    aps = state.get("assetPositions")
    if isinstance(aps, list):
        for ap in aps:
            if not isinstance(ap, dict):
                continue

            pos = ap.get("position")
            if not isinstance(pos, dict):
                continue

            positions.append({
                "coin": str(pos.get("coin") or ap.get("coin") or ""),
                "szi": _as_float(pos.get("szi")),
                "entryPx": _as_float(pos.get("entryPx")),
                "unrealizedPnl": _as_float(pos.get("unrealizedPnl")),
                "leverage": _as_float(pos.get("leverage")),
            })
            
    # Enrich with notional value (approximate)
    for p in positions:
        szi = p.get("szi") or 0.0
        entry = p.get("entryPx") or 0.0
        pnl = p.get("unrealizedPnl") or 0.0
        
        # If we have size and entry, crude notional is size * entry (cost basis)
        # Better: size * current_price.
        # current_price ~ entry + (pnl / size)  [if long]
        # Notional value = size * current_price = size * entry + pnl
        # (This holds for both long and short if pnl is calculated correctly by engine)
        
        notional = abs((szi * entry) + pnl)
        p["notional"] = notional

    return equity, positions


def positions_signature(positions: List[Dict[str, Any]]) -> str:
    parts = []
    for p in sorted(positions, key=lambda x: (x.get("coin") or "")):
        coin = p.get("coin") or ""
        szi = p.get("szi")
        try:
            bucket = "na" if szi is None else f"{round(float(szi), 6)}"
        except Exception:
            bucket = "na"
        parts.append(f"{coin}:{bucket}")
    return sha1("|".join(parts))


def summarize_positions(positions: List[Dict[str, Any]], max_n: int = 6) -> str:
    if not positions:
        return "No open positions detected."

    # Sort by USD notional value (size * price), not raw unit size
    def key(p):
        try:
            return float(p.get("notional") or 0.0)
        except Exception:
            return 0.0

    top = sorted(positions, key=key, reverse=True)[:max_n]
    lines = []

    for p in top:
        bits = [p.get("coin") or "?"]

        if p.get("notional") is not None:
            bits.append(f"${_fmt_money(float(p['notional']))}")  # Show USD size
        
        # Keep raw size in parens if useful? No, user wants USD value focus.
        # Maybe " (2.5 ETH)"
        # if p.get("szi") is not None:
        #    bits.append(f"({p['szi']})")

        if p.get("unrealizedPnl") is not None:
            bits.append(f"uPnL={_fmt_money(float(p['unrealizedPnl']))}")

        lines.append(" ".join(bits))

    return " | ".join(lines)


# =====================================================
# Feed Worker
# =====================================================
# Back-compat: supports both signatures:
#   feed_worker(stop_event, mem, cfg)
#   feed_worker(stop_event, mem, cfg, runtime)
# =====================================================

def feed_worker(stop_event, mem, cfg, runtime=None):
    """
    Portfolio event plugin (Hyperliquid)

    feeds:
      portfolio_event:
        enabled: true
        mode: hyperliquid
        user_address: "0x7240BF39c2C195F55e5d39D2Af35bE9E65d0Fd8e"
        poll_sec: 6

        min_emit_gap_sec: 20
        min_equity_delta_frac: 0.003
        big_equity_delta_frac: 0.015

        positions_change_priority: 95
        equity_change_priority: 93
        big_move_priority: 98

        base_url: "https://api.hyperliquid.xyz"
    """

    # Runtime objects (preferred)
    StationEvent = None
    event_q = None
    ui_q = None
    log = None

    if isinstance(runtime, dict):
        StationEvent = runtime.get("StationEvent")
        event_q = runtime.get("event_q")
        ui_q = runtime.get("ui_q")
        log = runtime.get("log")

    # Back-compat (old style plugins importing runtime.py directly)
    if StationEvent is None or event_q is None:
        try:
            from runtime import StationEvent as _SE, event_q as _EQ  # type: ignore
            StationEvent = _SE
            event_q = _EQ
        except Exception:
            # No runtime available -> do nothing safely
            while not stop_event.is_set():
                time.sleep(2.0)
            return

    mode = str(cfg.get("mode", "hyperliquid")).lower().strip()
    user = str(cfg.get("user_address", "")).strip()
    
    # Auto-fix: if user address is a raw big integer (decimal), convert to hex (0x...)
    # This handles YAML parsers loading big ints or users pasting decimal addresses
    if user.isdigit() and len(user) > 20: 
        try:
            old_user = user
            user = hex(int(user))
            if log: log("feed", f"corrected hyperliquid address from {old_user[:6]}.. to {user}")
        except:
            pass
            
    poll_sec = float(cfg.get("poll_sec", 6.0))
    base_url = str(cfg.get("base_url", "https://api.hyperliquid.xyz")).strip()

    min_emit_gap_sec = float(cfg.get("min_emit_gap_sec", 20.0))
    min_equity_delta_frac = float(cfg.get("min_equity_delta_frac", 0.003))
    big_equity_delta_frac = float(cfg.get("big_equity_delta_frac", 0.015))

    pri_pos = float(cfg.get("positions_change_priority", 95.0))
    pri_eq = float(cfg.get("equity_change_priority", 93.0))
    pri_big = float(cfg.get("big_move_priority", 98.0))

    if mode == "hyperliquid" and not user:
        while not stop_event.is_set():
            time.sleep(2.0)
        return

    state_mem = mem.setdefault("_portfolio_event_state", {})

    last_emit_ts = int(state_mem.get("last_emit_ts", 0) or 0)
    prev_equity = state_mem.get("prev_equity")
    
    # Historical tracking
    # List of [ts, equity]
    history = state_mem.get("history") or [] 

    prev_sig = state_mem.get("prev_positions_sig", "")

    try:
        prev_equity = float(prev_equity) if prev_equity is not None else None
    except Exception:
        prev_equity = None

    while not stop_event.is_set():

        try:
            if mode != "hyperliquid":
                time.sleep(max(poll_sec, 1.0))
                continue

            state = hl_fetch_state(base_url, user)
            if not state:
                if log: log("feed", f"portfolio check failed for user {user[:8]}...")
                time.sleep(max(poll_sec, 1.0))
                continue

            equity, positions = hl_extract_equity_and_positions(state)
            
            # --------------------
            # History Maintenance
            # --------------------
            now = now_ts()
            if equity is not None:
                # Add sample if > 5 minutes since last sample, or empty
                should_append = False
                if not history:
                    should_append = True
                else:
                    last_hist_ts = history[-1][0]
                    if now - last_hist_ts > 300: # 5 mins
                        should_append = True
                
                if should_append:
                    history.append((now, float(equity)))
                    # Prune > 7 days (7 * 24 * 3600)
                    cutoff = now - 604800
                    history = [h for h in history if h[0] > cutoff]
                    state_mem["history"] = history
                    mem["_portfolio_event_state"] = state_mem # force save prompt

            # --------------------
            # Continuous HUD update
            # --------------------

            if isinstance(runtime, dict):
                widget_update_fn = runtime.get("ui_widget_update")
                ui_q_ref = runtime.get("ui_q")

                hud_data = {
                    "equity": equity,
                    "prev_equity": prev_equity,
                    "positions": positions,
                    "history": history, # Pass history to HUD
                    "mode": mode,
                    "user": user,
                    "base_url": base_url,
                    "ts": now_ts(),
                }
                
                if isinstance(equity, (int, float)):
                    if widget_update_fn:
                         widget_update_fn("portfolio_hud", hud_data)
                    elif ui_q_ref:
                        ui_q_ref.put((
                            "widget_update",
                            {
                                "widget_key": "portfolio_hud",
                                "data": hud_data
                            }
                        ))

            sig = positions_signature(positions)

            now = now_ts()
            can_emit = (now - last_emit_ts) >= min_emit_gap_sec

            positions_changed = bool(sig and sig != prev_sig)

            equity_changed = False
            big_move = False
            eq_frac = None

            if equity is not None and prev_equity is not None and prev_equity != 0:
                eq_frac = abs(equity - prev_equity) / max(abs(prev_equity), 1e-9)
                if eq_frac >= min_equity_delta_frac:
                    equity_changed = True
                if eq_frac >= big_equity_delta_frac:
                    big_move = True

            emit = False
            event_type = None
            priority = None
            title = None
            body = None
            key_points = []

            if positions_changed and (can_emit or big_move):

                emit = True
                event_type = "positions_change"
                priority = pri_big if big_move else pri_pos

                title = "Positions changed"
                body = summarize_positions(positions)

                key_points = [
                    "positions changed",
                    "exposure updated",
                    "check risk"
                ]

            elif equity_changed and (can_emit or big_move):

                emit = True
                event_type = "big_equity_move" if big_move else "equity_change"
                priority = pri_big if big_move else pri_eq

                if eq_frac is not None and equity is not None and prev_equity is not None:
                    delta = equity - prev_equity
                    title = "Equity moved"
                    body = f"Equity moved by {_fmt_money(delta)} ({_fmt_pct(eq_frac)})"
                    
                    # Add historical context
                    if history:
                        # 24h ago
                        lookback_24h = now - 86400
                        val_24h = None
                        # Find closest sample to 24h ago
                        closest_diff = 9999999
                        for hts, hval in history:
                            diff = abs(hts - lookback_24h)
                            if diff < closest_diff and diff < 3600*2: # within 2h window
                                closest_diff = diff
                                val_24h = hval
                        
                        if val_24h:
                            d24 = equity - val_24h
                            p24 = (d24 / abs(val_24h)) if val_24h != 0 else 0
                            body += f" | 24h change: {_fmt_signed_money(d24)} ({_fmt_pct(p24)})"
                            key_points.append(f"24h outcome: {_fmt_pct(p24)}")

                else:
                    title = "Equity moved"
                    body = "Equity changed."

                key_points.append("equity moved")
                key_points.append("risk state shifted")

            # Emit StationEvent (live)
            if emit and title and body and event_type:

                payload = {
                    "title": title,
                    "body": clamp_text(body, 1400),
                    "angle": "Treat as concrete portfolio state and react naturally.",
                    "why": "Live portfolio update.",
                    "key_points": key_points,
                    "host_hint": "Quick live portfolio check-in.",
                    # Extra HUD fields (for widget)
                    "equity": equity,
                    "prev_equity": prev_equity,
                    "positions": positions,
                    "mode": mode,
                    "user": user,
                    "base_url": base_url,
                    "ts": now,
                }

                evt = StationEvent(
                    source="portfolio",
                    type=event_type,
                    ts=now,
                    severity=0.0,
                    priority=float(priority or 94.0),
                    payload=payload
                )

                event_q.put(evt)

                last_emit_ts = now
                state_mem["last_emit_ts"] = last_emit_ts

                # Producer candidate (kept for your queue)
                mem.setdefault("feed_candidates", []).append({
                    "id": sha1(f"portfolio|{event_type}|{now}|{random.random()}"),
                    "post_id": sha1(f"portfolio|{event_type}|{now}"),
                    "source": "portfolio",
                    "event_type": event_type,
                    "title": title,
                    "body": clamp_text(body, 1400),
                    "comments": [],
                    "heur": float(priority or 50.0),
                    "payload": payload,  # <— keep full for widgets/now-playing sync
                })

                if callable(log):
                    try:
                        log("feed", f"portfolio emit: {event_type} pri={priority}")
                    except Exception:
                        pass

            # Update memory state
            if equity is not None:
                prev_equity = equity
                state_mem["prev_equity"] = equity

            if sig:
                prev_sig = sig
                state_mem["prev_positions_sig"] = sig

            mem["_portfolio_event_state"] = state_mem

        except Exception:
            pass

        time.sleep(max(poll_sec, 1.0))


# =====================================================
# Widget Registration
# =====================================================

def register_widgets(registry, runtime):
    """
    Registers a Portfolio HUD widget.
    Widget behavior:
      - EMPTY unless now_playing_on segment is source=portfolio
      - Shows a tactile HUD + positions cards
      - Auto-clears after hold window OR on now_playing_off
    """

    tk = runtime["tk"]

    # Theme (match your dark UI, but with energy)
    BG = "#0e0e0e"
    SURFACE = "#121212"
    CARD = "#161616"
    EDGE = "#2a2a2a"

    TXT = "#e8e8e8"
    MUTED = "#9a9a9a"

    CYAN = "#4cc9f0"
    GREEN = "#2ee59d"
    RED = "#ff4d6d"
    AMBER = "#ffb703"
    PURPLE = "#8b5cf6"

    def portfolio_hud_factory(parent, runtime):
        return PortfolioHUDWidget(parent, runtime,
                                  BG=BG, SURFACE=SURFACE, CARD=CARD, EDGE=EDGE,
                                  TXT=TXT, MUTED=MUTED,
                                  CYAN=CYAN, GREEN=GREEN, RED=RED, AMBER=AMBER, PURPLE=PURPLE)

    registry.register(
        "portfolio_hud",
        portfolio_hud_factory,
        title="Portfolio • HUD",
        default_panel="left"
    )


class PortfolioHUDWidget:
    """
    A bounded, scrollable, tactile portfolio HUD.
    Designed to be 'show only while talking' and later click-interactable.
    """

    def __init__(self, parent, runtime, **C):
        self.tk = runtime["tk"]
        self.runtime = runtime
        self.C = C

        self.root = self.tk.Frame(parent, bg=C["BG"])

        # visibility / sync
        self._active = False
        self._last_payload = None
        self._hold_ms = 0
        self._hide_job = None

        # -------------------------
        # Header HUD
        # -------------------------
        self.hdr = self.tk.Frame(self.root, bg=C["SURFACE"], highlightbackground=C["EDGE"], highlightthickness=1)
        self.hdr.pack(fill="x", padx=10, pady=(10, 8))

        self.hdr.columnconfigure(0, weight=1)
        self.hdr.columnconfigure(1, weight=0)

        # Left: Title + badges
        left = self.tk.Frame(self.hdr, bg=C["SURFACE"])
        left.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        self.title = self.tk.Label(left, text="PORTFOLIO", fg=C["CYAN"], bg=C["SURFACE"],
                                   font=("Segoe UI", 10, "bold"))
        self.title.pack(anchor="w")

        self.badges = self.tk.Frame(left, bg=C["SURFACE"])
        self.badges.pack(anchor="w", pady=(6, 0))

        self.badge_mode = self._pill(self.badges, "MODE", C["PURPLE"])
        self.badge_mode.pack(side="left", padx=(0, 8))

        self.badge_last = self._pill(self.badges, "LAST", C["AMBER"])
        self.badge_last.pack(side="left")

        # Right: Equity + Delta
        right = self.tk.Frame(self.hdr, bg=C["SURFACE"])
        right.grid(row=0, column=1, sticky="e", padx=10, pady=10)

        self.equity_lbl = self.tk.Label(right, text="—", fg=C["TXT"], bg=C["SURFACE"],
                                        font=("Segoe UI", 18, "bold"))
        self.equity_lbl.pack(anchor="e")

        self.delta_lbl = self.tk.Label(right, text="", fg=C["MUTED"], bg=C["SURFACE"],
                                       font=("Segoe UI", 10))
        self.delta_lbl.pack(anchor="e", pady=(2, 0))

        # -------------------------
        # Body: scrollable cards
        # -------------------------
        body = self.tk.Frame(self.root, bg=C["BG"])
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.canvas = self.tk.Canvas(body, bg=C["BG"], highlightthickness=0)
        self.scroll = self.tk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)

        self.scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = self.tk.Frame(self.canvas, bg=C["BG"])
        self._window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.cards: List[Any] = []  # list of tk.Frame

        def _on_inner_cfg(_e=None):
            try:
                self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            except Exception:
                pass

        self.inner.bind("<Configure>", _on_inner_cfg)

        def _on_canvas_cfg(e):
            # keep inner width locked to canvas width
            try:
                self.canvas.itemconfigure(self._window_id, width=e.width)
            except Exception:
                pass
            self._sync_wrap(e.width)

        self.canvas.bind("<Configure>", _on_canvas_cfg)

        # Empty state overlay
        self.empty = self.tk.Label(
            self.inner,
            text="(Portfolio HUD idle)\n\nWill light up only when the host is talking about a portfolio update.",
            fg=C["MUTED"],
            bg=C["BG"],
            justify="center",
            font=("Segoe UI", 11)
        )
        self.empty.pack(fill="both", expand=True, pady=40)

        # Start hidden (empty)
        self._render_empty()

        self.root.pack(fill="both", expand=True)

    # -------------------------
    # Pills / UI primitives
    # -------------------------

    def _pill(self, parent, text: str, color: str):
        f = self.tk.Frame(parent, bg=color)
        lbl = self.tk.Label(f, text=text, fg="#0b0b0b", bg=color, font=("Segoe UI", 9, "bold"))
        lbl.pack(padx=10, pady=4)
        f._lbl = lbl
        return f

    def _set_pill(self, pill_frame, text: str):
        try:
            pill_frame._lbl.config(text=text)
        except Exception:
            pass

    def _sync_wrap(self, width: int):
        wrap = max(int(width) - 80, 260)
        for c in self.cards:
            try:
                c._title.config(wraplength=wrap)
                c._sub.config(wraplength=wrap)
            except Exception:
                pass

    # -------------------------
    # Show/Hide logic
    # -------------------------

    def _cancel_hide(self):
        if self._hide_job is not None:
            try:
                self.root.after_cancel(self._hide_job)
            except Exception:
                pass
        self._hide_job = None

    def _schedule_hide(self):
        self._cancel_hide()
        self._hide_job = self.root.after(self._hold_ms, self._render_empty)

    def _render_empty(self):
        self._active = False
        self._last_payload = None
        self._cancel_hide()

        # clear HUD text
        self.equity_lbl.config(text="—")
        self.delta_lbl.config(text="")
        self._set_pill(self.badge_mode, "MODE")
        self._set_pill(self.badge_last, "LAST")

        # clear cards
        for c in list(self.cards):
            try:
                c.destroy()
            except Exception:
                pass
        self.cards.clear()

        # show empty message
        try:
            self.empty.pack(fill="both", expand=True, pady=40)
        except Exception:
            pass

        try:
            self.canvas.yview_moveto(0)
        except Exception:
            pass

    # -------------------------
    # Rendering
    # -------------------------

    def _render_payload(self, payload: Dict[str, Any]):
        C = self.C
        self._active = True
        self._last_payload = payload or {}

        # remove empty
        try:
            self.empty.pack_forget()
        except Exception:
            pass

        # HUD fields
        mode = _safe(payload.get("mode"), "hyperliquid").upper()
        ts = payload.get("ts") or now_ts()

        eq = payload.get("equity")
        prev_eq = payload.get("prev_equity")
        positions = payload.get("positions") or []

        # Equity display
        if isinstance(eq, (int, float)):
            self.equity_lbl.config(text=_fmt_money(float(eq)))
        else:
            self.equity_lbl.config(text="—")

        # Delta display
        if isinstance(eq, (int, float)) and isinstance(prev_eq, (int, float)):
            delta = float(eq) - float(prev_eq)
            sign = _fmt_signed_money(delta)
            frac = 0.0
            if float(prev_eq) != 0:
                frac = abs(delta) / max(abs(float(prev_eq)), 1e-9)
            pct = _fmt_pct(frac)

            col = C["GREEN"] if delta >= 0 else C["RED"]
            self.delta_lbl.config(text=f"Δ {sign}  ({pct})", fg=col)
        else:
            self.delta_lbl.config(text="", fg=C["MUTED"])

        # Badges
        self._set_pill(self.badge_mode, f"{mode}")
        self._set_pill(self.badge_last, time.strftime("%H:%M:%S", time.localtime(int(ts))))

        # Rebuild cards
        for c in list(self.cards):
            try:
                c.destroy()
            except Exception:
                pass
        self.cards.clear()

        # Sort by notional (USD value)
        def _sz(p):
            try:
                # Prefer 'notional', fallback to raw 'szi' logic if missing
                return float(p.get("notional") or abs(float(p.get("szi") or 0)))
            except Exception:
                return 0.0

        pos_sorted = sorted([p for p in positions if isinstance(p, dict)], key=_sz, reverse=True)

        # If no positions, show a single card
        if not pos_sorted:
            self._add_card(
                stripe=C["CYAN"],
                title="No open positions",
                sub="Exposure is flat. Waiting for the next entry / state change.",
                meta=[]
            )
        else:
            for p in pos_sorted[:14]:
                coin = _safe(p.get("coin"), "?")
                szi = p.get("szi")
                entry = p.get("entryPx")
                upnl = p.get("unrealizedPnl")
                lev = p.get("leverage")
                notional = p.get("notional")

                side = "LONG" if (isinstance(szi, (int, float)) and float(szi) > 0) else "SHORT"
                stripe = C["GREEN"] if side == "LONG" else C["RED"]

                meta = []
                # Only show notional USD size primarily
                if isinstance(notional, (int, float)):
                    meta.append(("SIZE", f"${_fmt_money(float(notional))}"))
                
                # Show raw units in small tooltip-like field (optional) or just skip to save space
                # if isinstance(szi, (int, float)):
                #    meta.append(("UNITS", f"{float(szi):.3f}"))

                if isinstance(entry, (int, float)):
                    meta.append(("ENTRY", f"{float(entry):.4f}"))
                if isinstance(lev, (int, float)):
                    meta.append(("LEV", f"{float(lev):.2f}x"))
                if isinstance(upnl, (int, float)):
                    meta.append(("uPnL", _fmt_signed_money(float(upnl))))

                sub = f"{side} • risk snapshot"
                self._add_card(
                    stripe=stripe,
                    title=f"{coin}",
                    sub=sub,
                    meta=meta,
                    upnl=upnl
                )

        try:
            self.canvas.yview_moveto(0)
        except Exception:
            pass


    def _add_card(self, stripe: str, title: str, sub: str, meta: List[Tuple[str, str]], upnl: Any = None):
        C = self.C

        card = self.tk.Frame(self.inner, bg=C["CARD"], highlightbackground=C["EDGE"], highlightthickness=1)
        card.pack(fill="x", padx=2, pady=8)

        # stripe
        bar = self.tk.Frame(card, bg=stripe, width=6)
        bar.pack(side="left", fill="y")

        body = self.tk.Frame(card, bg=C["CARD"])
        body.pack(side="left", fill="both", expand=True, padx=12, pady=10)

        # title
        t = self.tk.Label(body, text=title, fg=C["TXT"], bg=C["CARD"],
                          font=("Segoe UI", 13, "bold"), anchor="w", justify="left")
        t.pack(fill="x")

        # subtitle
        s = self.tk.Label(body, text=sub, fg=C["MUTED"], bg=C["CARD"],
                          font=("Segoe UI", 10), anchor="w", justify="left")
        s.pack(fill="x", pady=(2, 8))

        # meta row
        if meta:
            row = self.tk.Frame(body, bg=C["CARD"])
            row.pack(fill="x")

            for i, (k, v) in enumerate(meta):
                chip_bg = "#1f1f1f"
                fg = C["TXT"]

                # color uPnL value
                if k.lower() == "upnl":
                    try:
                        if isinstance(upnl, (int, float)):
                            fg = C["GREEN"] if float(upnl) >= 0 else C["RED"]
                    except Exception:
                        pass

                chip = self.tk.Frame(row, bg=chip_bg, highlightbackground=C["EDGE"], highlightthickness=1)
                chip.pack(side="left", padx=(0, 8), pady=0)

                lk = self.tk.Label(chip, text=k, fg=C["MUTED"], bg=chip_bg, font=("Segoe UI", 8, "bold"))
                lv = self.tk.Label(chip, text=v, fg=fg, bg=chip_bg, font=("Segoe UI", 9, "bold"))

                lk.pack(side="top", anchor="w", padx=8, pady=(6, 0))
                lv.pack(side="top", anchor="w", padx=8, pady=(0, 6))

        # store for wrap sync
        card._title = t
        card._sub = s

        # tactile feel: hover
        def _enter(_e=None):
            try:
                card.config(bg="#1a1a1a")
                body.config(bg="#1a1a1a")
                t.config(bg="#1a1a1a")
                s.config(bg="#1a1a1a")
            except Exception:
                pass

        def _leave(_e=None):
            try:
                card.config(bg=C["CARD"])
                body.config(bg=C["CARD"])
                t.config(bg=C["CARD"])
                s.config(bg=C["CARD"])
            except Exception:
                pass

        for w in (card, body, t, s):
            try:
                w.bind("<Enter>", _enter)
                w.bind("<Leave>", _leave)
                w.config(cursor="hand2")
            except Exception:
                pass

        self.cards.append(card)

    # =================================================
    # Hook points used by your StationUI dispatcher
    # =================================================

    def on_station_event(self, evt: str, seg: Dict[str, Any]):

        # Ignore end-of-segment events completely
        if evt == "now_playing_off":
            return

        # We only care when a portfolio update comes in
        if evt != "now_playing_on":
            return

        source = str(seg.get("source", "")).lower().strip()

        if source != "portfolio":
            return

        # Prefer wrapped payload
        if isinstance(seg.get("payload"), dict):
            payload = seg["payload"]
        else:
            payload = dict(seg or {})

        # Render immediately and persist
        self._render_payload(payload)

    def on_update(self, data: Any):
        """
        Optional: if you later choose to send ui_q ("widget_update", {...})
        we can render here too.
        """
        if isinstance(data, dict):
            self._render_payload(data)
