"""
Twitter / X Plugin (API Access Required)
=========================================

This plugin fetches tweets by hashtag using Twitter API v2.

SETUP REQUIRED:
- Twitter Developer Account (developer.twitter.com)
- Twitter API v2 Access (Basic tier ~$100/month)
- Bearer Token from Twitter Developer Portal

Configuration in manifest.yaml:
  twitter_feed:
    enabled: false  # Set to true after setup
    bearer_token: "YOUR_TWITTER_BEARER_TOKEN_HERE"
    hashtags: ["crypto", "bitcoin", "trading"]
    poll_sec: 90
    limit: 20
    priority: 75

Note: Twitter's free tier was discontinued. You'll need a paid plan.
"""

import time
import requests
import hashlib
from typing import Any, Dict, List


# Plugin metadata
PLUGIN_NAME = "Twitter (X)"
PLUGIN_DESC = "Fetch tweets by hashtag (requires Twitter API v2 access ~$100/mo)"
IS_FEED = True

FEED_DEFAULTS = {
    "enabled": False,
    "bearer_token": "",
    "hashtags": [],
    "poll_sec": 90,
    "limit": 20,
    "priority": 75.0
}


def now_ts() -> int:
    return int(time.time())


def sha1(x: Any) -> str:
    return hashlib.sha1(str(x).encode("utf-8", errors="ignore")).hexdigest()


def fetch_tweets(bearer_token: str, hashtags: List[str], limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch tweets using Twitter API v2"""
    
    if not bearer_token or not hashtags:
        return []
    
    out: List[Dict[str, Any]] = []
    
    # Twitter API v2 recent search endpoint
    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {bearer_token}"}
    
    for tag in hashtags:
        try:
            # Build query: hashtag, English tweets, no retweets
            query = f"#{tag} lang:en -is:retweet"
            
            params = {
                "query": query,
                "max_results": min(limit, 100),  # API max is 100
                "tweet.fields": "created_at,author_id,public_metrics"
            }
            
            r = requests.get(url, headers=headers, params=params, timeout=15)
            
            if r.status_code != 200:
                continue  # Token invalid or rate limited
            
            data = r.json().get("data", [])
            
            for tweet in data:
                tid = tweet.get("id")
                text = tweet.get("text", "")
                
                out.append({
                    "tweet_id": tid,
                    "title": text[:120],
                    "body": text,
                    "created_at": tweet.get("created_at", ""),
                })
        
        except Exception:
            pass
    
    return out


def feed_worker(stop_event, mem, cfg):
    """
    Twitter feed plugin worker
    
    Requires valid Twitter API v2 bearer token.
    See plugin header for setup instructions.
    """
    
    bearer_token = cfg.get("bearer_token", "").strip()
    hashtags = list(cfg.get("hashtags", []))
    poll_sec = float(cfg.get("poll_sec", 90))
    limit = int(cfg.get("limit", 20))
    priority = float(cfg.get("priority", 75.0))
    burst_delay = float(cfg.get("burst_delay", 0.25))
    
    # Import runtime objects
    try:
        from runtime import StationEvent, event_q
    except ImportError:
        return
    
    seen_local = set()
    
    # Warn if not configured
    if not bearer_token:
        print("⚠️  Twitter plugin enabled but no bearer_token configured")
        print("   Get API access at: developer.twitter.com")
        time.sleep(5)
    
    while not stop_event.is_set():
        
        if not bearer_token or not hashtags:
            time.sleep(2.0)
            continue
        
        tweets = fetch_tweets(bearer_token, hashtags, limit=limit)
        
        for t in tweets:
            tid = t["tweet_id"]
            
            if tid in seen_local:
                continue
            
            seen_local.add(tid)
            
            title = t.get("title", "")
            body = t.get("body", "")
            
            # Realtime event
            evt = StationEvent(
                source="twitter",
                type="tweet",
                ts=now_ts(),
                severity=0.0,
                priority=priority,
                payload={
                    "title": title,
                    "body": body,
                    "angle": "React to this tweet naturally.",
                    "why": "Trending on Twitter right now.",
                    "key_points": ["twitter discussion", "social pulse"],
                    "host_hint": "Quick social take."
                }
            )
            
            event_q.put(evt)
            
            # Producer candidate
            mem.setdefault("feed_candidates", []).append({
                "id": sha1(f"twitter|{tid}|{now_ts()}"),
                "tweet_id": tid,
                "source": "twitter",
                "event_type": "item",
                "title": title,
                "body": body,
                "comments": [],
                "heur": priority,
            })

            if burst_delay > 0:
                time.sleep(burst_delay)
        
        time.sleep(poll_sec)


# ======================================================
# Widget Registration
# ======================================================

def register_widgets(registry, runtime):
    """Register Twitter feed widget"""
    import tkinter as tk
    
    BG = "#0e0e0e"
    CARD = "#1a1a1a"
    TXT = "#e8e8e8"
    MUTED = "#9a9a9a"
    ACCENT = "#1da1f2"  # Twitter blue
    
    def twitter_widget_factory(parent, runtime):
        root = tk.Frame(parent, bg=BG)
        
        # Header
        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", pady=(2, 0))
        
        tk.Label(
            header,
            text="🐦 Twitter Feed",
            bg=BG, fg=ACCENT,
            font=("Segoe UI", 10, "bold")
        ).pack(side="left", padx=12)
        
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
        
        # Scroll container
        scrollbar = tk.Scrollbar(root, orient="vertical")
        canvas = tk.Canvas(root, bg=BG, highlightthickness=0, yscrollcommand=scrollbar.set)
        scrollbar.configure(command=canvas.yview)
        
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        
        inner = tk.Frame(canvas, bg=BG)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        
        cards = []
        
        def sync(e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            if e:
                canvas.itemconfigure(window_id, width=e.width)
        
        inner.bind("<Configure>", sync)
        canvas.bind("<Configure>", sync)
        
        def reorder():
            for c in cards:
                c.pack_forget()
            items = cards if sort_var.get() == "Newest" else reversed(cards)
            for c in items:
                c.pack(fill="x", padx=12, pady=8)
        
        def render():
            for c in cards:
                c.destroy()
            cards.clear()
            
            mem = runtime.get("mem", {})
            candidates = mem.get("feed_candidates", [])
            
            twitter_items = [c for c in candidates if c.get("source") == "twitter"]
            twitter_items = sorted(twitter_items, key=lambda x: x.get("id", ""), reverse=True)[:30]
            
            for item in twitter_items:
                card = tk.Frame(inner, bg=CARD, relief="flat", bd=1)
                
                title_txt = item.get("title", "No title")
                body_txt = item.get("body", "")
                
                tk.Label(
                    card,
                    text=title_txt,
                    bg=CARD, fg=TXT,
                    font=("Segoe UI", 10, "bold"),
                    wraplength=380,
                    justify="left"
                ).pack(anchor="w", padx=10, pady=(8, 4))
                
                if body_txt and body_txt != title_txt:
                    tk.Label(
                        card,
                        text=body_txt[:200] + ("..." if len(body_txt) > 200 else ""),
                        bg=CARD, fg=MUTED,
                        font=("Segoe UI", 9),
                        wraplength=380,
                        justify="left"
                    ).pack(anchor="w", padx=10, pady=(0, 8))
                
                cards.append(card)
            
            reorder()
        
        def tick():
            render()
            root.after(3000, tick)
        
        tick()
        root.pack(fill="both", expand=True)
        return root
    
    registry.register(
        "twitter_feed_widget",
        twitter_widget_factory,
        title="Twitter Feed",
        default_panel="right"
    )
