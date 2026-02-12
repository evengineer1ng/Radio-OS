"""
Instagram Plugin (API Access Required)
=======================================

This plugin fetches Instagram posts by hashtag using Meta Graph API.

SETUP REQUIRED:
- Facebook Developer Account (developers.facebook.com)
- Instagram Business Account linked to Facebook Page
- Meta Graph API Access Token
- App Review & Approval from Meta

Configuration in manifest.yaml:
  instagram_feed:
    enabled: false  # Set to true after setup
    access_token: "YOUR_INSTAGRAM_ACCESS_TOKEN_HERE"
    hashtags: ["fitness", "wellness", "gym"]
    poll_sec: 120
    limit: 15
    priority: 70

Note: Instagram's API is restricted. You need app approval and a business account.
Learn more: developers.facebook.com/docs/instagram-api
"""

import time
import requests
import hashlib
from typing import Any, Dict, List


# Plugin metadata
PLUGIN_NAME = "Instagram"
PLUGIN_DESC = "Fetch Instagram posts by hashtag (requires Meta Graph API approval)"
IS_FEED = True

FEED_DEFAULTS = {
    "enabled": False,
    "access_token": "",
    "hashtags": [],
    "poll_sec": 120,
    "limit": 15,
    "priority": 70.0
}


def now_ts() -> int:
    return int(time.time())


def sha1(x: Any) -> str:
    return hashlib.sha1(str(x).encode("utf-8", errors="ignore")).hexdigest()


def fetch_instagram_posts(access_token: str, hashtags: List[str], limit: int = 15) -> List[Dict[str, Any]]:
    """Fetch Instagram posts using Meta Graph API"""
    
    if not access_token or not hashtags:
        return []
    
    out: List[Dict[str, Any]] = []
    
    # Meta Graph API hashtag search
    base_url = "https://graph.facebook.com/v18.0/ig_hashtag_search"
    
    for tag in hashtags:
        try:
            # Step 1: Get hashtag ID
            params = {
                "user_id": "YOUR_INSTAGRAM_BUSINESS_ID",  # User needs to configure
                "q": tag,
                "access_token": access_token
            }
            
            r = requests.get(base_url, params=params, timeout=15)
            
            if r.status_code != 200:
                continue
            
            data = r.json().get("data", [])
            if not data:
                continue
            
            hashtag_id = data[0].get("id")
            
            # Step 2: Get recent posts for this hashtag
            posts_url = f"https://graph.facebook.com/v18.0/{hashtag_id}/recent_media"
            posts_params = {
                "user_id": "YOUR_INSTAGRAM_BUSINESS_ID",
                "fields": "id,caption,media_type,timestamp,like_count",
                "limit": limit,
                "access_token": access_token
            }
            
            r2 = requests.get(posts_url, params=posts_params, timeout=15)
            
            if r2.status_code != 200:
                continue
            
            posts = r2.json().get("data", [])
            
            for post in posts:
                pid = post.get("id")
                caption = post.get("caption", "")
                
                out.append({
                    "post_id": pid,
                    "title": caption[:120] if caption else "Instagram Post",
                    "body": caption,
                    "media_type": post.get("media_type", ""),
                })
        
        except Exception:
            pass
    
    return out


def feed_worker(stop_event, mem, cfg):
    """
    Instagram feed plugin worker
    
    Requires valid Meta Graph API access token and app approval.
    See plugin header for setup instructions.
    """
    
    access_token = cfg.get("access_token", "").strip()
    hashtags = list(cfg.get("hashtags", []))
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
    if not access_token:
        print("⚠️  Instagram plugin enabled but no access_token configured")
        print("   Get API access at: developers.facebook.com")
        time.sleep(5)
    
    while not stop_event.is_set():
        
        if not access_token or not hashtags:
            time.sleep(2.0)
            continue
        
        posts = fetch_instagram_posts(access_token, hashtags, limit=limit)
        
        for p in posts:
            pid = p["post_id"]
            
            if pid in seen_local:
                continue
            
            seen_local.add(pid)
            
            title = p.get("title", "")
            body = p.get("body", "")
            
            # Realtime event
            evt = StationEvent(
                source="instagram",
                type="post",
                ts=now_ts(),
                severity=0.0,
                priority=priority,
                payload={
                    "title": title,
                    "body": body,
                    "angle": "React to this Instagram moment.",
                    "why": "Visual trend on Instagram.",
                    "key_points": ["instagram culture", "visual content"],
                    "host_hint": "Quick social vibe check."
                }
            )
            
            event_q.put(evt)
            
            # Producer candidate
            mem.setdefault("feed_candidates", []).append({
                "id": sha1(f"instagram|{pid}|{now_ts()}"),
                "post_id": pid,
                "source": "instagram",
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
    """Register Instagram feed widget"""
    import tkinter as tk
    
    BG = "#0e0e0e"
    CARD = "#1a1a1a"
    TXT = "#e8e8e8"
    MUTED = "#9a9a9a"
    ACCENT = "#e1306c"  # Instagram pink
    
    def instagram_widget_factory(parent, runtime):
        root = tk.Frame(parent, bg=BG)
        
        # Header
        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", pady=(2, 0))
        
        tk.Label(
            header,
            text="📷 Instagram Feed",
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
            
            ig_items = [c for c in candidates if c.get("source") == "instagram"]
            ig_items = sorted(ig_items, key=lambda x: x.get("id", ""), reverse=True)[:30]
            
            for item in ig_items:
                card = tk.Frame(inner, bg=CARD, relief="flat", bd=1)
                
                title_txt = item.get("title", "No title")
                body_txt = item.get("body", "")
                media_type = item.get("media_type", "")
                
                tk.Label(
                    card,
                    text=f"{title_txt} {f'[{media_type}]' if media_type else ''}",
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
        "instagram_feed_widget",
        instagram_widget_factory,
        title="Instagram Feed",
        default_panel="right"
    )
