"""
Facebook Plugin (API Access Required)
======================================

This plugin fetches Facebook posts by hashtag/keyword using Meta Graph API.

SETUP REQUIRED:
- Facebook Developer Account (developers.facebook.com)
- Facebook App with Pages Access
- Meta Graph API Access Token with appropriate permissions
- App Review & Approval from Meta

Configuration in manifest.yaml:
  facebook_feed:
    enabled: false  # Set to true after setup
    access_token: "YOUR_FACEBOOK_ACCESS_TOKEN_HERE"
    page_id: "YOUR_FACEBOOK_PAGE_ID"
    keywords: ["tech", "innovation", "startup"]
    poll_sec: 120
    limit: 15
    priority: 70

Note: Facebook's API requires app review for most permissions.
Learn more: developers.facebook.com/docs/graph-api
"""

import time
import requests
import hashlib
from typing import Any, Dict, List


# Plugin metadata
PLUGIN_NAME = "Facebook"
PLUGIN_DESC = "Fetch Facebook posts (requires Meta Graph API access & app approval)"
IS_FEED = True

FEED_DEFAULTS = {
    "enabled": False,
    "access_token": "",
    "page_id": "",
    "keywords": [],
    "poll_sec": 120,
    "limit": 15,
    "priority": 70.0
}


def now_ts() -> int:
    return int(time.time())


def sha1(x: Any) -> str:
    return hashlib.sha1(str(x).encode("utf-8", errors="ignore")).hexdigest()


def fetch_facebook_posts(access_token: str, page_id: str, keywords: List[str], limit: int = 15) -> List[Dict[str, Any]]:
    """Fetch Facebook posts using Meta Graph API"""
    
    if not access_token or not page_id:
        return []
    
    out: List[Dict[str, Any]] = []
    
    # Meta Graph API page posts endpoint
    url = f"https://graph.facebook.com/v18.0/{page_id}/posts"
    
    try:
        params = {
            "fields": "id,message,created_time,likes.summary(true),comments.summary(true)",
            "limit": limit,
            "access_token": access_token
        }
        
        r = requests.get(url, params=params, timeout=15)
        
        if r.status_code != 200:
            return []
        
        posts = r.json().get("data", [])
        
        for post in posts:
            pid = post.get("id")
            message = post.get("message", "")
            
            # Filter by keywords if specified
            if keywords:
                if not any(kw.lower() in message.lower() for kw in keywords):
                    continue
            
            out.append({
                "post_id": pid,
                "title": message[:120] if message else "Facebook Post",
                "body": message,
                "created_time": post.get("created_time", ""),
                "likes": post.get("likes", {}).get("summary", {}).get("total_count", 0),
            })
    
    except Exception:
        pass
    
    return out


def feed_worker(stop_event, mem, cfg):
    """
    Facebook feed plugin worker
    
    Requires valid Meta Graph API access token and page ID.
    See plugin header for setup instructions.
    """
    
    access_token = cfg.get("access_token", "").strip()
    page_id = cfg.get("page_id", "").strip()
    keywords = list(cfg.get("keywords", []))
    poll_sec = float(cfg.get("poll_sec", 120))
    limit = int(cfg.get("limit", 15))
    priority = float(cfg.get("priority", 70.0))
    burst_delay = float(cfg.get("burst_delay", 0.25))
    
    # Import runtime objects
    try:
        from runtime import StationEvent, event_q
    except ImportError:
        return
    
    seen_local = set()
    
    # Warn if not configured
    if not access_token or not page_id:
        print("⚠️  Facebook plugin enabled but missing access_token or page_id")
        print("   Get API access at: developers.facebook.com")
        time.sleep(5)
    
    while not stop_event.is_set():
        
        if not access_token or not page_id:
            time.sleep(2.0)
            continue
        
        posts = fetch_facebook_posts(access_token, page_id, keywords, limit=limit)
        
        for p in posts:
            pid = p["post_id"]
            
            if pid in seen_local:
                continue
            
            seen_local.add(pid)
            
            title = p.get("title", "")
            body = p.get("body", "")
            
            # Realtime event
            evt = StationEvent(
                source="facebook",
                type="post",
                ts=now_ts(),
                severity=0.0,
                priority=priority,
                payload={
                    "title": title,
                    "body": body,
                    "angle": "Comment on this Facebook discussion.",
                    "why": "Community conversation on Facebook.",
                    "key_points": ["facebook community", "social engagement"],
                    "host_hint": "Quick social insight."
                }
            )
            
            event_q.put(evt)
            
            # Producer candidate
            mem.setdefault("feed_candidates", []).append({
                "id": sha1(f"facebook|{pid}|{now_ts()}"),
                "post_id": pid,
                "source": "facebook",
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
    """Register Facebook feed widget"""
    import tkinter as tk
    
    BG = "#0e0e0e"
    CARD = "#1a1a1a"
    TXT = "#e8e8e8"
    MUTED = "#9a9a9a"
    ACCENT = "#4267B2"  # Facebook blue
    
    def facebook_widget_factory(parent, runtime):
        root = tk.Frame(parent, bg=BG)
        
        # Header
        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", pady=(2, 0))
        
        tk.Label(
            header,
            text="📘 Facebook Feed",
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
            
            fb_items = [c for c in candidates if c.get("source") == "facebook"]
            fb_items = sorted(fb_items, key=lambda x: x.get("id", ""), reverse=True)[:30]
            
            for item in fb_items:
                card = tk.Frame(inner, bg=CARD, relief="flat", bd=1)
                
                title_txt = item.get("title", "No title")
                body_txt = item.get("body", "")
                likes = item.get("likes", 0)
                
                title_frame = tk.Frame(card, bg=CARD)
                title_frame.pack(fill="x", padx=10, pady=(8, 4))
                
                tk.Label(
                    title_frame,
                    text=title_txt,
                    bg=CARD, fg=TXT,
                    font=("Segoe UI", 10, "bold"),
                    wraplength=320,
                    justify="left"
                ).pack(side="left", fill="x", expand=True)
                
                if likes:
                    tk.Label(
                        title_frame,
                        text=f"👍 {likes}",
                        bg=CARD, fg=ACCENT,
                        font=("Segoe UI", 8)
                    ).pack(side="right")
                
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
        "facebook_feed_widget",
        facebook_widget_factory,
        title="Facebook Feed",
        default_panel="right"
    )
