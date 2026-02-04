import time
import hashlib
import feedparser
import html
import re
import requests
import calendar
import webbrowser
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


PLUGIN_NAME = "rss"

# =====================================================
# Helpers
# =====================================================

def now_ts():
    return int(time.time())


def sha1(x: Any):
    return hashlib.sha1(str(x).encode()).hexdigest()


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_html(text: str):
    if not text:
        return ""

    text = html.unescape(text)
    text = _TAG_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def domain(url: str):
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


# =====================================================
# Optional deep fetch
# =====================================================

def fetch_article_text(url, timeout, max_chars):
    try:
        r = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "RadioOS/1.0"}
        )
        if r.status_code != 200:
            return ""

        text = clean_html(r.text)
        return text[:max_chars]

    except Exception:
        return ""


# =====================================================
# RSS FEED WORKER (modern Radio OS)
# =====================================================

def feed_worker(stop_event, mem, cfg, runtime):

    StationEvent = runtime["StationEvent"]
    event_q = runtime["event_q"]
    emit_candidate = runtime["emit_candidate"]

    urls = list(cfg.get("urls", []))
    poll_sec = float(cfg.get("poll_sec", 180))
    priority = float(cfg.get("priority", 72.0))

    deep_cfg = cfg.get("deep_fetch", {}) or {}
    deep_enabled = bool(deep_cfg.get("enabled", False))
    deep_timeout = float(deep_cfg.get("timeout_sec", 5))
    deep_max_chars = int(deep_cfg.get("max_chars", 1500))

    # seen = set() -> use persistent memory
    seen = set()
    if "rss_seen_ids" in mem and isinstance(mem["rss_seen_ids"], list):
        seen.update(mem["rss_seen_ids"])

    while not stop_event.is_set():

        for feed_url in urls:

            try:
                feed = feedparser.parse(feed_url)

                emit_limit = int(cfg.get("emit_limit", 2))
                emitted = 0

                for e in feed.entries:
                    if emitted >= emit_limit:
                        break


                    pid = e.get("id") or e.get("link")
                    if not pid or pid in seen:
                        continue

                    # Mark as seen and persist
                    seen.add(pid)
                    mem.setdefault("rss_seen_ids", [])
                    if isinstance(mem["rss_seen_ids"], list):
                        mem["rss_seen_ids"].append(pid)
                        # Keep history bounded but generous
                        if len(mem["rss_seen_ids"]) > 2500:
                            mem["rss_seen_ids"] = mem["rss_seen_ids"][-2000:]

                    title = clean_html(e.get("title", ""))
                    if not title:
                        continue

                    raw_summary = ""

                    if e.get("content"):
                        try:
                            raw_summary = e["content"][0].get("value", "")
                        except Exception:
                            pass

                    if not raw_summary:
                        raw_summary = (
                            e.get("summary") or
                            e.get("description") or
                            ""
                        )

                    summary = clean_html(raw_summary)

                    if deep_enabled and e.get("link"):
                        if not summary or len(summary) < 120:
                            deep = fetch_article_text(
                                e["link"],
                                deep_timeout,
                                deep_max_chars
                            )
                            if deep:
                                summary = deep

                    # Avoid duplicating title in summary if they are identical
                    if not summary:
                        # If we have no summary, leaving it empty is better than duplicating the title
                        # because the runtime/LLM often sees both title and body.
                        pass  
                    elif summary.strip() == title.strip():
                        # If the summary is just the title repeated, clear it to avoid double narration.
                        summary = ""

                    src_site = domain(e.get("link", ""))

                    # Try to find a date
                    pub_ts = now_ts()
                    try:
                        if e.get("published_parsed"):
                            pub_ts = calendar.timegm(e.published_parsed)
                        elif e.get("updated_parsed"):
                            pub_ts = calendar.timegm(e.updated_parsed)
                    except Exception:
                        pass

                    # -----------------------
                    # Live station event (for producer)
                    # -----------------------

                    evt = StationEvent(
                        source="rss",
                        type="alert",
                        ts=now_ts(),
                        priority=priority,
                        payload={
                            "title": title,
                            "body": summary,
                            "source_site": src_site,
                            "link": e.get("link"),
                            "ts": pub_ts,
                            "angle": "React naturally to this news update.",
                            "why": "A new headline just appeared.",
                            "key_points": ["breaking update"],
                            "host_hint": "News pulse."
                        }
                    )
                    
                    event_q.put(evt)

                    # -----------------------
                    # Widget Update (Live Feed)
                    # -----------------------
                    if isinstance(runtime, dict):
                        w_upd = runtime.get("ui_widget_update")
                        if w_upd:
                            w_upd("rss_now_playing", {
                                "title": title, 
                                "body": summary,
                                "source_site": src_site,
                                "link": e.get("link"),
                                "ts": pub_ts
                            })

                    # -----------------------
                    # Producer candidate
                    # -----------------------

                    emit_candidate({
                        "id": sha1(f"rss|{pid}|{now_ts()}"),
                        "post_id": pid,
                        "source": "rss",
                        "event_type": "item",
                        "title": title,
                        "body": summary,
                        "comments": [],
                        "heur": priority,
                        "source_site": src_site,
                    })
                    emitted += 1

            except Exception:
                pass

        time.sleep(poll_sec)


# =====================================================
# RSS WIDGET — SCROLLING CARD FEED (BOUNDED + TACTILE)
# =====================================================

def register_widgets(registry, runtime):

    tk = runtime["tk"]

    BG = "#0e0e0e"
    CARD = "#161616"
    BORDER = "#2a2a2a"

    TITLE = "#ffffff"
    BODY = "#d6d6d6"
    SOURCE = "#4cc9f0"
    MUTED = "#9a9a9a"

    def rss_widget_factory(parent, runtime):

        root = tk.Frame(parent, bg=BG)

        # -------------------------
        # Header / Sort
        # -------------------------
        
        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", pady=(2,0))

        sort_var = tk.StringVar(value="Newest")

        def toggle_sort():
            nv = "Oldest" if sort_var.get() == "Newest" else "Newest"
            sort_var.set(nv)
            btn_sort.config(text=f"Sort: {nv}")
            reorder()

        btn_sort = tk.Label(
            header,
            text="Sort: Newest",
            bg=BG, fg=MUTED,
            font=("Segoe UI", 8),
            cursor="hand2"
        )
        btn_sort.bind("<Button-1>", lambda e: toggle_sort())
        btn_sort.pack(side="right", padx=12)

        # -------------------------
        # Scroll container
        # -------------------------

        canvas = tk.Canvas(root, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(root, orient="vertical", command=canvas.yview)

        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=BG)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        cards = []

        def reorder():
            for c in cards:
                c.pack_forget()

            items = cards if sort_var.get() == "Newest" else reversed(cards)
            for c in items:
                c.pack(fill="x", padx=12, pady=8)

        # -------------------------
        # Keep bounded + responsive
        # -------------------------

        def _sync_width(event):
            canvas.itemconfigure(window_id, width=event.width)

            wrap = max(event.width - 48, 240)

            for c in cards:
                c._title.config(wraplength=wrap)
                c._body.config(wraplength=wrap)

        canvas.bind("<Configure>", _sync_width)

        def _on_inner_config(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", _on_inner_config)

        # -------------------------
        # Create RSS card
        # -------------------------

        def make_card(payload):

            card = tk.Frame(
                inner,
                bg=CARD,
                highlightbackground=BORDER,
                highlightthickness=1
            )
            
            link = payload.get("link")
            ts = payload.get("ts") or now_ts()
            dt = datetime.fromtimestamp(ts).strftime("%H:%M")

            def on_click(e):
                if link:
                    webbrowser.open(link)

            site = payload.get("source_site", "").upper()
            src = tk.Label(
                card,
                text=f"{site} • {dt}",
                fg=SOURCE,
                bg=CARD,
                font=("Segoe UI", 9, "bold")
            )
            src.pack(anchor="w", padx=12, pady=(10,2))

            title = tk.Label(
                card,
                text=payload.get("title", ""),
                fg=TITLE,
                bg=CARD,
                justify="left",
                anchor="w",
                font=("Segoe UI", 13, "bold")
            )
            title.pack(fill="x", padx=12, pady=(0,6))

            body = tk.Label(
                card,
                text=payload.get("body", "")[:520],
                fg=BODY,
                bg=CARD,
                justify="left",
                anchor="w",
                font=("Segoe UI", 11)
            )
            body.pack(fill="x", padx=12, pady=(0,12))

            # store for resize wrapping
            card._title = title
            card._body = body

            # tactile feel (ready for clicks later)
            card.configure(cursor="hand2")
            src.configure(cursor="hand2")
            title.configure(cursor="hand2")
            body.configure(cursor="hand2")
            
            card.bind("<Button-1>", on_click)
            src.bind("<Button-1>", on_click)
            title.bind("<Button-1>", on_click)
            body.bind("<Button-1>", on_click)

            return card

        # -------------------------
        # Runtime events
        # -------------------------

        def on_station_event(evt, seg):
            if evt == "now_playing_on" and seg.get("source") == "rss":
                p = seg.get("payload", seg)
                # optionally highlight top card
                pass

        def on_update(data):
            # Incoming feed item
            if isinstance(data, dict):
                card = make_card(data)
                cards.insert(0, card)
                
                if len(cards) > 20:
                    try:
                        old = cards.pop()
                        old.destroy()
                    except:
                        pass
                
                reorder()
                if sort_var.get() == "Newest":
                    canvas.yview_moveto(0)

        root.on_station_event = on_station_event
        root.on_update = on_update

        root.pack(fill="both", expand=True)
        return root


    registry.register(
        "rss_now_playing",
        rss_widget_factory,
        title="RSS • Live Feed",
        default_panel="center"
    )
