import time
import hashlib
import random
import math
import requests
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

PLUGIN_NAME = "markets"

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

def _pct(a: float, b: float) -> float:
    # percent change from a -> b
    if a == 0:
        return 0.0
    return (b - a) / a * 100.0

def _safe_str(x: Any, default: str = "") -> str:
    try:
        return default if x is None else str(x)
    except Exception:
        return default

def _mean(xs: List[float]) -> float:
    return sum(xs) / max(len(xs), 1)

def _stdev(xs: List[float]) -> float:
    # population stdev (stable for small windows)
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    v = sum((x - m) ** 2 for x in xs) / len(xs)
    return math.sqrt(max(v, 0.0))

def _sign(x: float) -> int:
    return 1 if x > 0 else (-1 if x < 0 else 0)

def _tagify(*parts: str) -> List[str]:
    out = []
    for p in parts:
        p = (p or "").strip().lower()
        if p and p not in out:
            out.append(p)
    return out


# =====================================================
# Data fetching (Binance public)
# =====================================================
def stock_price(symbol: str, timeout: int = 8) -> Optional[float]:
    """
    Free Yahoo Finance quote endpoint (no API key).
    Works for stocks, ETFs, indexes.
    """
    try:
        url = "https://query1.finance.yahoo.com/v7/finance/quote"
        r = requests.get(
            url,
            params={"symbols": symbol},
            timeout=timeout,
            headers={"User-Agent": "RadioOS/1.0"}
        )
        j = r.json()

        res = j.get("quoteResponse", {}).get("result", [])
        if not res:
            return None

        px = res[0].get("regularMarketPrice")
        if px is None:
            return None

        return float(px)

    except Exception:
        return None

def bn_price(symbol: str, timeout: int = 8) -> Optional[float]:
    """
    Lightweight spot price endpoint.
    """
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": symbol},
            timeout=timeout
        )
        j = r.json()
        return float(j["price"])
    except Exception:
        return None


# =====================================================
# Signal Engine
# =====================================================

class SymbolState:
    def __init__(self, window_points: int, vol_points: int, ret_points: int):
        self.prices = deque(maxlen=window_points)  # rolling prices
        self.returns = deque(maxlen=ret_points)    # per-tick returns (fraction)
        self.vol_hist = deque(maxlen=vol_points)   # rolling vol estimates
        self.last_emit_minute: Dict[str, int] = {} # event cooldown by type
        self.last_price: Optional[float] = None

    def push(self, px: float) -> None:
        if self.last_price and self.last_price > 0:
            self.returns.append((px - self.last_price) / self.last_price)
        self.last_price = px
        self.prices.append(px)

    def vol(self) -> float:
        return _stdev(list(self.returns))

    def vol_baseline(self) -> float:
        if not self.vol_hist:
            return 0.0
        return _mean(list(self.vol_hist))


def _cooldown_ok(st: SymbolState, event_type: str, cooldown_min: int) -> bool:
    """
    Cooldown bucketed by minutes, per symbol per event_type.
    """
    now_min = int(now_ts() / 60)
    last_min = int(st.last_emit_minute.get(event_type, -10_000))
    if (now_min - last_min) < max(cooldown_min, 0):
        return False
    st.last_emit_minute[event_type] = now_min
    return True


# =====================================================
# Feed Worker (modern Radio OS)
# =====================================================

def feed_worker(stop_event, mem, cfg, runtime=None):
    """
    Catch-all markets plugin (Binance spot price)
    - Multiple event types
    - Manifest-driven thresholds, enabled_events, emit_limit
    - Emits BOTH StationEvent (live) and feed_candidates via emit_candidate (producer pool)
    - Sends widget_update to market_hud (continuous) and market_tape (event tape)

    feeds:
      markets:
        enabled: true
        symbols: [BTCUSDT, ETHUSDT]
        poll_sec: 10

        # feed weight normalization
        emit_limit: 2

        # event gating
        enabled_events:
          momentum_burst: true
          volatility_spike: true
          trend_reversal: true
          range_break: true
          level_cross: false

        # thresholds
        window_points: 18          # rolling window length (in polls)
        momentum_pct: 0.60         # abs % over window to trigger momentum_burst
        reversal_pct: 0.70         # abs % move from mid->end to suggest reversal
        vol_spike_mult: 2.5        # current vol >= baseline * mult triggers spike
        range_break_pct: 0.90      # abs % break beyond recent hi/lo triggers range_break

        # cooldowns (minutes)
        cooldown_min:
          momentum_burst: 1
          volatility_spike: 2
          trend_reversal: 2
          range_break: 2
          level_cross: 5

        # priorities
        priority:
          momentum_burst: 92
          volatility_spike: 90
          trend_reversal: 88
          range_break: 91
          level_cross: 86

        # optional levels for level_cross
        levels:
          BTCUSDT: [80000, 75000, 90000]
    """

    # Runtime objects (preferred)
    StationEvent = None
    event_q = None
    ui_q = None
    log = None
    emit_candidate = None
    providers = cfg.get("providers", {}) or {}

    if isinstance(runtime, dict):
        StationEvent = runtime.get("StationEvent")
        event_q = runtime.get("event_q")
        ui_q = runtime.get("ui_q")
        log = runtime.get("log")
        emit_candidate = runtime.get("emit_candidate")

    # Back-compat import fallback
    if StationEvent is None or event_q is None or emit_candidate is None:
        try:
            from runtime import StationEvent as _SE, event_q as _EQ, emit_candidate as _EC  # type: ignore
            StationEvent = _SE
            event_q = _EQ
            emit_candidate = _EC
        except Exception:
            while not stop_event.is_set():
                time.sleep(2.0)
            return

    symbols = list(cfg.get("symbols", [])) or []
    poll_sec = float(cfg.get("poll_sec", 10.0))
    emit_limit = int(cfg.get("emit_limit", 2))

    enabled_events = cfg.get("enabled_events", {}) or {}
    thresholds = cfg  # keep simple; thresholds live at top-level keys per docstring

    window_points = int(thresholds.get("window_points", 18))
    momentum_pct = float(thresholds.get("momentum_pct", 0.60))
    reversal_pct = float(thresholds.get("reversal_pct", 0.70))
    vol_spike_mult = float(thresholds.get("vol_spike_mult", 2.5))
    range_break_pct = float(thresholds.get("range_break_pct", 0.90))

    cooldowns = cfg.get("cooldown_min", {}) or {}
    priorities = cfg.get("priority", {}) or {}
    levels_cfg = cfg.get("levels", {}) or {}

    # internal state
    state: Dict[str, SymbolState] = {}
    for s in symbols:
        state[s] = SymbolState(
            window_points=max(window_points, 6),
            vol_points=24,
            ret_points=max(window_points, 6),
        )

    # small helper
    def is_enabled(evt: str) -> bool:
        v = enabled_events.get(evt, True)
        return bool(v)

    def pri(evt: str, fallback: float) -> float:
        try:
            return float(priorities.get(evt, fallback))
        except Exception:
            return fallback

    def cd(evt: str, fallback: int) -> int:
        try:
            return int(cooldowns.get(evt, fallback))
        except Exception:
            return fallback

    # track “tape” for widget
    mem.setdefault("_markets_tape", [])  # list of last N emitted events (compact)

    while not stop_event.is_set():

        emitted = 0

        for sym in symbols:
            if emitted >= emit_limit:
                break

            st = state.get(sym)
            if st is None:
                st = SymbolState(window_points=max(window_points, 6), vol_points=24, ret_points=max(window_points, 6))
                state[sym] = st

            try:
                px = fetch_price(sym, providers)
                if px is None or px <= 0:
                    continue

                st.push(px)

                # ---------------------------
                # Continuous HUD update
                # ---------------------------
                if ui_q is not None:
                    try:
                        ui_q.put((
                            "widget_update",
                            {
                                "widget_key": "market_hud",
                                "data": {
                                    "symbol": sym,
                                    "price": px,
                                    "ts": now_ts(),
                                    "window_points": len(st.prices),
                                    "ret_window_pct": _pct(st.prices[0], st.prices[-1]) if len(st.prices) >= 2 else 0.0,
                                    "vol": st.vol(),
                                    "vol_base": st.vol_baseline(),
                                    "prices": list(st.prices),   # 👈 ADD THIS LINE

                                }
                            }
                        ))
                    except Exception:
                        pass

                # need sufficient history for signals
                if len(st.prices) < max(6, int(window_points * 0.66)):
                    continue

                # update vol baseline
                cur_vol = st.vol()
                if cur_vol > 0:
                    st.vol_hist.append(cur_vol)
                base_vol = st.vol_baseline()

                # computed features
                p0 = st.prices[0]
                pN = st.prices[-1]
                win_ret = _pct(p0, pN)

                mid = st.prices[len(st.prices)//2]
                snap = _pct(mid, pN)

                hi = max(st.prices)
                lo = min(st.prices)

                # range break distance from extrema
                break_up = _pct(hi, pN)  # will be <=0 if above hi
                break_dn = _pct(lo, pN)  # will be >=0 if above lo

                # ---------------------------
                # Candidate builder (common)
                # ---------------------------
                def emit_event(event_type: str, title: str, body: str, tags: List[str], metrics: Dict[str, Any], priority_fallback: float):
                    nonlocal emitted

                    # live StationEvent
                    payload = {
                        "title": title,
                        "body": clamp_text(body, 1400),
                        "angle": metrics.get("angle", ""),  # allow per-event angle in metrics
                        "why": metrics.get("why", "Live market signal detected."),
                        "key_points": metrics.get("key_points", []),
                        "host_hint": metrics.get("host_hint", "Market pulse."),
                        # extras for widgets / filtering
                        "symbol": sym,
                        "price": px,
                        "tags": tags,
                        "metrics": metrics,
                        "ts": now_ts(),
                    }

                    evt = StationEvent(
                        source="markets",
                        type=event_type,
                        ts=now_ts(),
                        severity=0.0,
                        priority=float(pri(event_type, priority_fallback)),
                        payload=payload
                    )
                    event_q.put(evt)

                    # candidate for producer pool (soft-extended)
                    emit_candidate({
                        "source": "markets",
                        "event_type": event_type,
                        "title": title,
                        "body": clamp_text(body, 1400),
                        "heur": float(pri(event_type, priority_fallback)),
                        "ts": now_ts(),
                        "symbol": sym,
                        "tags": tags,
                        "metrics": metrics,
                    })

                    # tape
                    tape = mem.setdefault("_markets_tape", [])
                    tape.append({
                        "ts": now_ts(),
                        "symbol": sym,
                        "event_type": event_type,
                        "title": title,
                        "price": px,
                        "metrics": metrics,
                        "tags": tags
                    })
                    mem["_markets_tape"] = tape[-60:]

                    # optional: widget_update for tape widget
                    if ui_q is not None:
                        try:
                            ui_q.put((
                                "widget_update",
                                {
                                    "widget_key": "market_tape",
                                    "data": {"items": mem.get("_markets_tape", [])}
                                }
                            ))
                        except Exception:
                            pass

                    emitted += 1

                    if callable(log):
                        try:
                            log("feed", f"markets emit {event_type} {sym} pri={pri(event_type, priority_fallback)}")
                        except Exception:
                            pass

                # ---------------------------
                # Event: momentum_burst
                # ---------------------------
                if emitted < emit_limit and is_enabled("momentum_burst"):
                    if abs(win_ret) >= momentum_pct and _cooldown_ok(st, "momentum_burst", cd("momentum_burst", 1)):
                        direction = "up" if win_ret > 0 else "down"
                        title = f"{sym} momentum {direction}"
                        body = f"{sym} moved {win_ret:.2f}% over the last {len(st.prices)} ticks (price={px:g})."
                        emit_event(
                            "momentum_burst",
                            title,
                            body,
                            tags=_tagify("momentum", "acceleration", direction),
                            metrics={
                                "pct_move": round(win_ret, 4),
                                "window_points": len(st.prices),
                                "vol": cur_vol,
                                "vol_base": base_vol,
                                "angle": "Treat as live momentum: what does it imply for continuation vs mean reversion?",
                                "why": "Short-window return exceeded threshold.",
                                "key_points": ["momentum burst", "continuation vs mean reversion"],
                                "host_hint": "Market momentum pulse."
                            },
                            priority_fallback=92.0
                        )
                        continue

                # ---------------------------
                # Event: volatility_spike
                # ---------------------------
                if emitted < emit_limit and is_enabled("volatility_spike"):
                    if base_vol > 0 and cur_vol >= base_vol * vol_spike_mult and _cooldown_ok(st, "volatility_spike", cd("volatility_spike", 2)):
                        title = f"{sym} volatility spike"
                        body = f"{sym} volatility expanded (vol={cur_vol:.5f}, baseline={base_vol:.5f})."
                        emit_event(
                            "volatility_spike",
                            title,
                            body,
                            tags=_tagify("volatility", "risk", "expansion"),
                            metrics={
                                "vol": cur_vol,
                                "vol_base": base_vol,
                                "vol_mult": round(cur_vol / max(base_vol, 1e-12), 3),
                                "window_points": len(st.prices),
                                "angle": "Frame as a risk-regime shift: widen ranges, execution risk up, position sizing matters.",
                                "why": "Volatility exceeded baseline multiple.",
                                "key_points": ["volatility expansion", "risk regime shift"],
                                "host_hint": "Risk update."
                            },
                            priority_fallback=90.0
                        )
                        continue

                # ---------------------------
                # Event: trend_reversal (snap move in latter half)
                # ---------------------------
                if emitted < emit_limit and is_enabled("trend_reversal"):
                    if abs(snap) >= reversal_pct and _cooldown_ok(st, "trend_reversal", cd("trend_reversal", 2)):
                        direction = "up" if snap > 0 else "down"
                        title = f"{sym} trend snap {direction}"
                        body = f"{sym} snapped {snap:.2f}% in the latter half of the window (price={px:g})."
                        emit_event(
                            "trend_reversal",
                            title,
                            body,
                            tags=_tagify("reversal", "trend", direction),
                            metrics={
                                "snap_pct": round(snap, 4),
                                "window_points": len(st.prices),
                                "pct_move": round(win_ret, 4),
                                "angle": "Treat as a possible trend shift; discuss confirmation signals and failure modes.",
                                "why": "Second-half move exceeded snap threshold.",
                                "key_points": ["trend snap", "confirmation vs fakeout"],
                                "host_hint": "Possible reversal."
                            },
                            priority_fallback=88.0
                        )
                        continue

                # ---------------------------
                # Event: range_break (push beyond recent extrema)
                # ---------------------------
                if emitted < emit_limit and is_enabled("range_break"):
                    # If pN is meaningfully beyond hi/lo, break_up will be negative large.
                    # We trigger when abs(distance beyond extrema) exceeds threshold.
                    beyond_hi = (pN - hi) / max(hi, 1e-9) * 100.0
                    beyond_lo = (lo - pN) / max(lo, 1e-9) * 100.0

                    if (beyond_hi >= range_break_pct or beyond_lo >= range_break_pct) and _cooldown_ok(st, "range_break", cd("range_break", 2)):
                        if beyond_hi >= range_break_pct:
                            title = f"{sym} range break up"
                            body = f"{sym} pushed {beyond_hi:.2f}% above the recent high (price={px:g})."
                            direction = "up"
                        else:
                            title = f"{sym} range break down"
                            body = f"{sym} dropped {beyond_lo:.2f}% below the recent low (price={px:g})."
                            direction = "down"

                        emit_event(
                            "range_break",
                            title,
                            body,
                            tags=_tagify("range", "breakout", direction),
                            metrics={
                                "beyond_hi_pct": round(beyond_hi, 4),
                                "beyond_lo_pct": round(beyond_lo, 4),
                                "hi": hi,
                                "lo": lo,
                                "window_points": len(st.prices),
                                "angle": "Treat as a range breakout: talk levels, liquidity pockets, and risk of a trap.",
                                "why": "Price moved beyond recent extrema.",
                                "key_points": ["range break", "trap risk", "levels"],
                                "host_hint": "Breakout / breakdown."
                            },
                            priority_fallback=91.0
                        )
                        continue

                # ---------------------------
                # Event: level_cross (optional)
                # ---------------------------
                if emitted < emit_limit and is_enabled("level_cross"):
                    levels = levels_cfg.get(sym)
                    if isinstance(levels, list) and levels:
                        last = st.prices[-2] if len(st.prices) >= 2 else None
                        if isinstance(last, (int, float)):
                            for lvl in levels:
                                lv = _as_float(lvl)
                                if lv is None:
                                    continue
                                crossed = (last < lv <= pN) or (last > lv >= pN)
                                if crossed and _cooldown_ok(st, f"level_{lv}", cd("level_cross", 5)):
                                    direction = "up" if pN >= lv else "down"
                                    title = f"{sym} crossed {lv:g}"
                                    body = f"{sym} crossed level {lv:g} ({direction}) (price={px:g})."
                                    emit_event(
                                        "level_cross",
                                        title,
                                        body,
                                        tags=_tagify("level", "cross", direction),
                                        metrics={
                                            "level": lv,
                                            "direction": direction,
                                            "window_points": len(st.prices),
                                            "angle": "Treat as a psychological/technical level cross; discuss whether it will hold.",
                                            "why": "Price crossed a configured level.",
                                            "key_points": ["level cross", "hold vs reject"],
                                            "host_hint": "Level check."
                                        },
                                        priority_fallback=86.0
                                    )
                                    break

            except Exception:
                pass

        time.sleep(max(poll_sec, 1.0))


# =====================================================
# Widgets
# =====================================================
def fetch_price(sym: str, providers: Dict[str, str]) -> Optional[float]:
    """
    Routes symbol to correct provider.
    """

    # crypto heuristic (you can improve later)
    if sym.endswith("USDT") or sym.endswith("USD"):
        prov = providers.get("crypto", "binance")
        if prov == "binance":
            return bn_price(sym)

    # otherwise treat as stock/ETF
    prov = providers.get("stocks", "yahoo")
    if prov == "yahoo":
        return stock_price(sym)

    return None

def yahoo_search(query: str, timeout: int = 8):
    try:
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        r = requests.get(
            url,
            params={"q": query, "quotesCount": 8, "newsCount": 0},
            timeout=timeout,
            headers={"User-Agent": "RadioOS/1.0"}
        )
        j = r.json()

        out = []
        for q in j.get("quotes", []):
            sym = q.get("symbol")
            name = q.get("shortname") or q.get("longname") or ""
            if sym:
                out.append({
                    "symbol": sym,
                    "name": name,
                    "provider": "yahoo"
                })
        return out
    except Exception:
        return []
def binance_search(query: str, timeout: int = 8):
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/exchangeInfo",
            timeout=timeout
        )
        j = r.json()

        q = query.upper()
        out = []

        for s in j.get("symbols", []):
            sym = s.get("symbol")
            if sym and q in sym:
                out.append({
                    "symbol": sym,
                    "name": f"{s.get('baseAsset')}/{s.get('quoteAsset')}",
                    "provider": "binance"
                })
                if len(out) >= 8:
                    break
        return out
    except Exception:
        return []

def register_widgets(registry, runtime):
    """
    Two widgets:
      - market_hud: continuous per-symbol snapshot (auto-updated via widget_update)
      - market_tape: scrolling tape of recent market events (auto-updated via widget_update)
    """
    tk = runtime["tk"]

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

    def market_hud_factory(parent, runtime):
        return MarketHUDWidget(
            parent, runtime,
            BG=BG, SURFACE=SURFACE, CARD=CARD, EDGE=EDGE,
            TXT=TXT, MUTED=MUTED,
            CYAN=CYAN, GREEN=GREEN, RED=RED, AMBER=AMBER, PURPLE=PURPLE
        )

    def market_tape_factory(parent, runtime):
        return MarketTapeWidget(
            parent, runtime,
            BG=BG, CARD=CARD, EDGE=EDGE,
            TXT=TXT, MUTED=MUTED,
            CYAN=CYAN, GREEN=GREEN, RED=RED, AMBER=AMBER
        )

    registry.register("market_hud", market_hud_factory, title="Markets • HUD", default_panel="left")
    registry.register("market_tape", market_tape_factory, title="Markets • Tape", default_panel="center")


class MarketHUDWidget:
    """
    Compact, tactile HUD. Shows latest snapshots per symbol.
    Updated via ui_q ("widget_update", {"widget_key":"market_hud","data":{...}})
    """
    def __init__(self, parent, runtime, **C):
        self.tk = runtime["tk"]
        self.C = C
        self.root = self.tk.Frame(parent, bg=C["BG"])

        self.rows: Dict[str, Any] = {}  # sym -> row widgets

        hdr = self.tk.Frame(self.root, bg=C["SURFACE"], highlightbackground=C["EDGE"], highlightthickness=1)
        hdr.pack(fill="x", padx=10, pady=(10, 8))

        self.tk.Label(hdr, text="MARKETS", fg=C["CYAN"], bg=C["SURFACE"], font=("Segoe UI", 10, "bold")).pack(
            anchor="w", padx=10, pady=10
        )

        self.body = self.tk.Frame(self.root, bg=C["BG"])
        self.body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.empty = self.tk.Label(
            self.body,
            text="(Markets HUD idle)\nWaiting for price snapshots…",
            fg=C["MUTED"], bg=C["BG"],
            justify="center",
            font=("Segoe UI", 11)
        )
        self.empty.pack(fill="both", expand=True, pady=30)

        self.root.pack(fill="both", expand=True)
    def add_symbol(sym):

        syms = mem.setdefault("_active_market_symbols", [])

        if sym not in syms:
            syms.append(sym)

        # also update engine cfg list if present
        cfg_syms = runtime["cfg"]["feeds"]["markets"].setdefault("symbols", [])
        if sym not in cfg_syms:
            cfg_syms.append(sym)

        save_memory_throttled(mem, 1.0)
    def draw_sparkline(self, canvas, values, pad=4):

        canvas.update_idletasks()
        canvas.delete("all")

        if not values or len(values) < 2:
            return

        width = canvas.winfo_width()
        height = canvas.winfo_height()

        if width < 10 or height < 10:
            return

        vmin = min(values)
        vmax = max(values)

        if vmax == vmin:
            vmax += 1e-9

        n = len(values)

        xs = []
        ys = []

        for i, v in enumerate(values):
            x = pad + i * (width - 2 * pad) / (n - 1)
            y = height - pad - (v - vmin) / (vmax - vmin) * (height - 2 * pad)
            xs.append(x)
            ys.append(y)

        for i in range(len(xs) - 1):
            canvas.create_line(
                xs[i], ys[i],
                xs[i+1], ys[i+1],
                width=2,
                fill=self.C["CYAN"],
                smooth=True
            )

    def on_search():

        q = search_var.get().strip()
        if not q:
            return

        results = []
        results += yahoo_search(q)
        results += binance_search(q)

        render_results(results)

    def _ensure_row(self, sym: str):
        C = self.C
        if sym in self.rows:
            return self.rows[sym]

        # remove empty once first row arrives
        try:
            self.empty.pack_forget()
        except Exception:
            pass

        card = self.tk.Frame(self.body, bg=C["CARD"], highlightbackground=C["EDGE"], highlightthickness=1)
        card.pack(fill="x", pady=8)

        top = self.tk.Frame(card, bg=C["CARD"])
        top.pack(fill="x", padx=10, pady=(10, 2))

        lbl_sym = self.tk.Label(top, text=sym, fg=C["TXT"], bg=C["CARD"], font=("Segoe UI", 12, "bold"))
        lbl_sym.pack(side="left")

        lbl_px = self.tk.Label(top, text="—", fg=C["TXT"], bg=C["CARD"], font=("Segoe UI", 12, "bold"))
        lbl_px.pack(side="right")

        sub = self.tk.Frame(card, bg=C["CARD"])
        sub.pack(fill="x", padx=10, pady=(0, 10))

        lbl_ret = self.tk.Label(sub, text="ret: —", fg=C["MUTED"], bg=C["CARD"], font=("Segoe UI", 10))
        lbl_ret.pack(side="left")

        lbl_vol = self.tk.Label(sub, text="vol: —", fg=C["MUTED"], bg=C["CARD"], font=("Segoe UI", 10))
        lbl_vol.pack(side="right")
        spark = self.tk.Canvas(
            card,
            width=120,
            height=40,
            bg=self.C["CARD"],
            highlightthickness=0
        )
        spark.pack(padx=10, pady=(4,6))

        row = {
            "card": card,
            "px": lbl_px,
            "ret": lbl_ret,
            "vol": lbl_vol,
            "spark": spark
        }


        self.rows[sym] = row
        return row

    def on_update(self, data: Any):
        if not isinstance(data, dict):
            return

        sym = _safe_str(data.get("symbol"), "")
        if not sym:
            return

        row = self._ensure_row(sym)

        px = data.get("price")
        ret = data.get("ret_window_pct")
        vol = data.get("vol")
        vb  = data.get("vol_base")
        prices = data.get("prices")

        if isinstance(prices, list):
            self.draw_sparkline(row["spark"], prices)

        try:
            if isinstance(px, (int, float)):
                row["px"].config(text=f"{float(px):g}")
        except Exception:
            pass

        try:
            if isinstance(ret, (int, float)):
                col = self.C["GREEN"] if float(ret) >= 0 else self.C["RED"]
                row["ret"].config(text=f"ret: {float(ret):+.2f}%", fg=col)
        except Exception:
            pass

        try:
            if isinstance(vol, (int, float)) and isinstance(vb, (int, float)) and float(vb) > 0:
                mult = float(vol) / max(float(vb), 1e-12)
                col = self.C["AMBER"] if mult >= 2.0 else self.C["MUTED"]
                row["vol"].config(text=f"vol×: {mult:.2f}", fg=col)
            elif isinstance(vol, (int, float)):
                row["vol"].config(text=f"vol: {float(vol):.5f}", fg=self.C["MUTED"])
        except Exception:
            pass

    # Optional station event hook (not required)
    def on_station_event(self, evt: str, seg: Dict[str, Any]):
        return


class MarketTapeWidget:
    """
    Recent event tape. Updates via widget_update with {"items":[...]}.
    """
    def __init__(self, parent, runtime, **C):
        self.tk = runtime["tk"]
        self.C = C
        self.root = self.tk.Frame(parent, bg=C["BG"])

        self.canvas = self.tk.Canvas(self.root, bg=C["BG"], highlightthickness=0)
        self.scroll = self.tk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)

        self.scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = self.tk.Frame(self.canvas, bg=C["BG"])
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.cards: List[Any] = []

        def _on_inner(_e=None):
            try:
                self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            except Exception:
                pass

        def _on_canvas(e):
            try:
                self.canvas.itemconfigure(self._win, width=e.width)
            except Exception:
                pass

        self.inner.bind("<Configure>", _on_inner)
        self.canvas.bind("<Configure>", _on_canvas)

        self.empty = self.tk.Label(
            self.inner,
            text="(Market tape idle)\nWaiting for market events…",
            fg=C["MUTED"], bg=C["BG"],
            justify="center",
            font=("Segoe UI", 11)
        )
        self.empty.pack(fill="both", expand=True, pady=30)

        self.root.pack(fill="both", expand=True)

    def _clear(self):
        for c in list(self.cards):
            try:
                c.destroy()
            except Exception:
                pass
        self.cards.clear()

    def on_update(self, data: Any):
        if not isinstance(data, dict):
            return
        items = data.get("items")
        if not isinstance(items, list):
            return

        # hide empty
        try:
            self.empty.pack_forget()
        except Exception:
            pass

        self._clear()

        C = self.C
        for it in reversed(items[-30:]):
            sym = _safe_str(it.get("symbol"), "?")
            et  = _safe_str(it.get("event_type"), "event")
            title = _safe_str(it.get("title"), "")
            ts = it.get("ts")

            stripe = C["CYAN"]
            if "down" in title.lower():
                stripe = C["RED"]
            elif "up" in title.lower():
                stripe = C["GREEN"]

            card = self.tk.Frame(self.inner, bg=C["CARD"], highlightbackground=C["EDGE"], highlightthickness=1)
            card.pack(fill="x", padx=10, pady=6)

            bar = self.tk.Frame(card, bg=stripe, width=6)
            bar.pack(side="left", fill="y")

            body = self.tk.Frame(card, bg=C["CARD"])
            body.pack(side="left", fill="both", expand=True, padx=10, pady=8)

            top = self.tk.Frame(body, bg=C["CARD"])
            top.pack(fill="x")

            self.tk.Label(top, text=sym, fg=C["TXT"], bg=C["CARD"], font=("Segoe UI", 10, "bold")).pack(side="left")
            self.tk.Label(top, text=et, fg=C["MUTED"], bg=C["CARD"], font=("Segoe UI", 9)).pack(side="right")

            self.tk.Label(body, text=title, fg=C["TXT"], bg=C["CARD"], font=("Segoe UI", 11, "bold"), anchor="w", justify="left").pack(fill="x", pady=(4,0))

            if isinstance(ts, (int, float)):
                self.tk.Label(body, text=time.strftime("%H:%M:%S", time.localtime(int(ts))), fg=C["MUTED"], bg=C["CARD"], font=("Segoe UI", 9)).pack(anchor="w", pady=(2,0))

            self.cards.append(card)

        try:
            self.canvas.yview_moveto(0)
        except Exception:
            pass

    def on_station_event(self, evt: str, seg: Dict[str, Any]):
        return
