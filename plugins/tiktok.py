"""
TikTok Plugin (API Access Required)
====================================

This plugin fetches TikTok videos by hashtag using TikTok Research API.

SETUP REQUIRED:
- TikTok Developer Account (developers.tiktok.com)
- TikTok Research API Access (requires academic/research qualification)
- API Key and Secret from TikTok Developer Portal
- Alternative: TikTok Display API (limited to user's own content)

Configuration in manifest.yaml:
  tiktok_feed:
    enabled: false  # Set to true after setup
    api_key: "YOUR_TIKTOK_API_KEY_HERE"
    api_secret: "YOUR_TIKTOK_API_SECRET_HERE"
    hashtags: ["dance", "comedy", "trending"]
    poll_sec: 180
    limit: 10
    priority: 72

Note: TikTok's Research API has strict eligibility requirements (academic/research only).
Public API access is very limited.
Learn more: developers.tiktok.com/products/research-api
"""

import time
import requests
import hashlib
from typing import Any, Dict, List


# Plugin metadata
PLUGIN_NAME = "TikTok"
PLUGIN_DESC = "Fetch TikTok videos by hashtag (requires Research API access - academic only)"
IS_FEED = True

FEED_DEFAULTS = {
    "enabled": False,
    "api_key": "",
    "api_secret": "",
    "hashtags": [],
    "poll_sec": 180,
    "limit": 10,
    "priority": 72.0
}


def now_ts() -> int:
    return int(time.time())


def sha1(x: Any) -> str:
    return hashlib.sha1(str(x).encode("utf-8", errors="ignore")).hexdigest()


def fetch_tiktok_videos(api_key: str, api_secret: str, hashtags: List[str], limit: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch TikTok videos using TikTok Research API
    
    Note: This is a placeholder. Actual implementation requires:
    - OAuth 2.0 authentication flow
    - Research API credentials
    - Academic/research qualification
    """
    
    if not api_key or not api_secret or not hashtags:
        return []
    
    out: List[Dict[str, Any]] = []
    
    # TikTok Research API endpoint (placeholder - actual endpoint varies)
    # Real endpoint: https://open.tiktokapis.com/v2/research/video/query/
    
    for tag in hashtags:
        try:
            # This is a simplified placeholder
            # Real implementation needs OAuth 2.0 client credentials flow
            
            headers = {
                "Authorization": f"Bearer {api_key}",  # Simplified - needs proper OAuth
                "Content-Type": "application/json"
            }
            
            # Research API query format
            payload = {
                "query": {
                    "and": [
                        {"field_name": "hashtag_name", "operation": "EQ", "field_values": [tag]}
                    ]
                },
                "max_count": limit,
                "start_date": "20240101",  # Last 30 days
                "end_date": "20240131"
            }
            
            # Note: This will fail without proper credentials and approval
            # Kept as reference for users with Research API access
            
            # r = requests.post(
            #     "https://open.tiktokapis.com/v2/research/video/query/",
            #     headers=headers,
            #     json=payload,
            #     timeout=15
            # )
            
            # Placeholder response handling
            # if r.status_code == 200:
            #     data = r.json().get("data", {}).get("videos", [])
            #     for video in data:
            #         vid = video.get("id")
            #         desc = video.get("video_description", "")
            #         out.append({
            #             "video_id": vid,
            #             "title": desc[:120],
            #             "body": desc,
            #         })
            
            pass  # Remove when implementing with real credentials
        
        except Exception:
            pass
    
    return out


def feed_worker(stop_event, mem, cfg):
    """
    TikTok feed plugin worker
    
    Requires TikTok Research API credentials (academic/research only).
    See plugin header for setup instructions.
    """
    
    api_key = cfg.get("api_key", "").strip()
    api_secret = cfg.get("api_secret", "").strip()
    hashtags = list(cfg.get("hashtags", []))
    poll_sec = float(cfg.get("poll_sec", 180))
    limit = int(cfg.get("limit", 10))
    priority = float(cfg.get("priority", 72.0))
    burst_delay = float(cfg.get("burst_delay", 0.25))
    
    # Import runtime objects
    try:
        from runtime import StationEvent, event_q
    except ImportError:
        return
    
    seen_local = set()
    
    # Warn if not configured
    if not api_key or not api_secret:
        print("⚠️  TikTok plugin enabled but missing API credentials")
        print("   TikTok Research API requires academic qualification")
        print("   Learn more: developers.tiktok.com/products/research-api")
        time.sleep(5)
    
    while not stop_event.is_set():
        
        if not api_key or not api_secret or not hashtags:
            time.sleep(2.0)
            continue
        
        videos = fetch_tiktok_videos(api_key, api_secret, hashtags, limit=limit)
        
        for v in videos:
            vid = v["video_id"]
            
            if vid in seen_local:
                continue
            
            seen_local.add(vid)
            
            title = v.get("title", "")
            body = v.get("body", "")
            
            # Realtime event
            evt = StationEvent(
                source="tiktok",
                type="video",
                ts=now_ts(),
                severity=0.0,
                priority=priority,
                payload={
                    "title": title,
                    "body": body,
                    "angle": "React to this TikTok trend.",
                    "why": "Viral on TikTok right now.",
                    "key_points": ["tiktok trend", "viral content"],
                    "host_hint": "Quick viral take."
                }
            )
            
            event_q.put(evt)
            
            # Producer candidate
            mem.setdefault("feed_candidates", []).append({
                "id": sha1(f"tiktok|{vid}|{now_ts()}"),
                "video_id": vid,
                "source": "tiktok",
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
    """Register TikTok feed widget"""
    import tkinter as tk
    
    BG = "#0e0e0e"
    CARD = "#1a1a1a"
    TXT = "#e8e8e8"
    MUTED = "#9a9a9a"
    ACCENT = "#fe2c55"  # TikTok pink
    
    def tiktok_widget_factory(parent, runtime):
        root = tk.Frame(parent, bg=BG)
        
        # Header
        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", pady=(2, 0))
        
        tk.Label(
            header,
            text="🎵 TikTok Feed",
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
            
            tiktok_items = [c for c in candidates if c.get("source") == "tiktok"]
            tiktok_items = sorted(tiktok_items, key=lambda x: x.get("id", ""), reverse=True)[:30]
            
            for item in tiktok_items:
                card = tk.Frame(inner, bg=CARD, relief="flat", bd=1)
                
                title_txt = item.get("title", "No title")
                body_txt = item.get("body", "")
                
                tk.Label(
                    card,
                    text=f"🎬 {title_txt}",
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
        "tiktok_feed_widget",
        tiktok_widget_factory,
        title="TikTok Feed",
        default_panel="right"
    )
