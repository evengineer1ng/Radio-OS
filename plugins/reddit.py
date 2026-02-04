import time
import hashlib
import requests
from datetime import datetime
from typing import List, Dict, Any


PLUGIN_NAME = "reddit"


# =====================================================
# Helpers
# =====================================================

def now_ts():
    return int(time.time())


def sha1(x):
    return hashlib.sha1(str(x).encode("utf-8", errors="ignore")).hexdigest()


# =====================================================
# Reddit fetch
# =====================================================

def fetch_reddit(subreddits, limit=10):
    out = []

    for sub in subreddits:
        try:
            r = requests.get(
                f"https://www.reddit.com/r/{sub}/new.json",
                headers={"User-Agent": "radio-os"},
                params={"limit": limit},
                timeout=10
            )
            j = r.json()

            for c in j.get("data", {}).get("children", []):
                d = c["data"]

                out.append({
                    "post_id": d.get("id"),
                    "subreddit": d.get("subreddit", sub),
                    "title": d.get("title", ""),
                    "body": d.get("selftext", ""),
                    "author": d.get("author", ""),
                    "score": d.get("score", 0),
                    "comments": d.get("num_comments", 0),
                    "created_utc": d.get("created_utc", float(now_ts())),
                })

        except Exception:
            continue

    return out


# =====================================================
# REDDIT WIDGET (CARD STYLE)
# =====================================================

def register_widgets(registry, runtime):

    tk = runtime["tk"]

    BG = "#0e0e0e"
    CARD = "#141414"
    BORDER = "#2a2a2a"
    TEXT = "#e8e8e8"
    MUTED = "#9a9a9a"
    SOFT = "#cfcfcf"
    ORANGE = "#ff4500"

    def factory(parent, runtime):

        root = tk.Frame(parent, bg=BG)

        card = tk.Frame(
            root,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1
        )

        # ---------------- Header

        header = tk.Frame(card, bg=CARD)
        header.pack(fill="x", padx=10, pady=(10, 6))

        pill = tk.Label(
            header,
            text="r/—",
            bg=ORANGE,
            fg="white",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=3
        )
        pill.pack(side="left")

        # Karma Filter
        karma_var = tk.IntVar(value=2)
        
        k_val = tk.Label(header, textvariable=karma_var, bg=CARD, fg=MUTED, font=("Segoe UI", 8, "bold"))
        k_val.pack(side="right", padx=(2, 0))

        k_lbl = tk.Label(header, text="Min Karma:", bg=CARD, fg=MUTED, font=("Segoe UI", 8))
        k_lbl.pack(side="right", padx=(5, 2))

        k_scale = tk.Scale(
            header,
            from_=2,
            to=2000,
            orient="horizontal",
            variable=karma_var,
            bg=CARD,
            fg=MUTED,
            troughcolor=BORDER,
            highlightthickness=0,
            bd=0,
            sliderlength=15,
            showvalue=0,
            length=80
        )
        k_scale.pack(side="right", padx=5)

        meta = tk.Label(
            header,
            text="",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9)
        )
        meta.pack(side="right", padx=10)

        # ---------------- Title

        title = tk.Label(
            card,
            text="",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 13, "bold"),
            wraplength=520,
            justify="left",
            anchor="w"
        )
        title.pack(fill="x", padx=10, pady=(0, 6))

        # ---------------- Body preview

        body = tk.Label(
            card,
            text="",
            bg=CARD,
            fg=SOFT,
            font=("Segoe UI", 11),
            wraplength=520,
            justify="left",
            anchor="w"
        )
        body.pack(fill="x", padx=10, pady=(0, 10))

        visible = False

        def hide():
            nonlocal visible
            if visible:
                card.pack_forget()
            visible = False

        def show():
            nonlocal visible
            if not visible:
                card.pack(fill="both", expand=True, padx=12, pady=12)
            visible = True

        def render(seg):

            payload = seg.get("payload", seg)

            sub = payload.get("subreddit", "")
            title_txt = payload.get("title", "")
            body_txt = payload.get("body", "")
            score = payload.get("score", 0)
            comments = payload.get("comments", 0)
            
            ts = payload.get("created_utc") or seg.get("ts") or now_ts()
            dt_str = datetime.fromtimestamp(ts).strftime("%H:%M %b %d")

            pill.config(text=f"r/{sub}")
            meta.config(text=f"{score} pts • {comments} cmts • {dt_str}")

            title.config(text=title_txt)

            preview = body_txt.strip()
            if len(preview) > 420:
                preview = preview[:420] + "…"

            body.config(text=preview)

        # ---------------- Runtime events

        def on_station_event(evt, payload):

            if evt == "now_playing_on":

                src = (payload.get("source") or "").lower()
                if src != "reddit":
                    return

                # Filter by karma
                p_data = payload.get("payload", payload)
                if p_data.get("score", 0) < karma_var.get():
                    return

                show()
                render(payload)

            elif evt == "now_playing_off":
                # Don't auto-hide anymore so we can see the last item
                pass
                
        def on_update(data):
            if isinstance(data, dict):
                score = data.get("score", 0)
                if score >= karma_var.get():
                    show()
                    render(data)

        root.on_station_event = on_station_event
        root.on_update = on_update

        # show() # Start empty until first fetch
        hide()
        return root


    registry.register(
        "reddit_now_playing",
        factory,
        title="Reddit • Now Playing",
        default_panel="left"
    )


# =====================================================
# FEED WORKER
# =====================================================

def feed_worker(stop_event, mem, cfg, runtime):

    StationEvent = runtime["StationEvent"]
    event_q = runtime["event_q"]
    emit_candidate = runtime["emit_candidate"]

    subs = list(cfg.get("subreddits", []))
    poll = float(cfg.get("poll_sec", 30))
    limit = int(cfg.get("limit", 15))
    priority = float(cfg.get("priority", 55))
    burst = float(cfg.get("burst_delay", 0.25))
    ttl = int(cfg.get("seen_ttl_sec", 3600))

    seen = {}

    while not stop_event.is_set():

        now = now_ts()

        for k, t in list(seen.items()):
            if now - t > ttl:
                seen.pop(k, None)

        posts = fetch_reddit(subs, limit)

        for p in posts:

            pid = p["post_id"]
            if pid in seen:
                continue

            seen[pid] = now

            evt = StationEvent(
                source="reddit",
                type="post",
                ts=now,
                priority=priority,
                payload=p
            )

            event_q.put(evt)

            emit_candidate({
                "id": sha1(f"reddit|{pid}|{now}"),
                "source": "reddit",
                "title": p["title"],
                "body": p["body"],
                "heur": priority,
                **p
            })
            
            # -----------------------
            # Live Feed Update
            # -----------------------
            if isinstance(runtime, dict):
                w_upd = runtime.get("ui_widget_update")
                if w_upd:
                    w_upd("reddit_now_playing", p)

            if burst:
                time.sleep(burst)

        time.sleep(poll)
