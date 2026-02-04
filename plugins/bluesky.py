import time
import requests
import hashlib
from typing import Any, Dict, List

# Import runtime objects
from runtime import StationEvent, event_q


# Plugin metadata
PLUGIN_NAME = "Bluesky"
PLUGIN_DESC = "Fetch posts from Bluesky network."
IS_FEED = True

FEED_DEFAULTS = {
    "enabled": False,
    "identifier": "",
    "password": "",
    "hashtags": [],
    "poll_sec": 60,
    "limit": 20,
    "priority": 70.0,
    "burst_delay": 0.25
}

# --------------------
# Helpers
# --------------------

def now_ts() -> int:
    return int(time.time())

def sha1(x: Any) -> str:
    return hashlib.sha1(str(x).encode("utf-8", errors="ignore")).hexdigest()

# --------------------
# Auth Helper
# --------------------

_BSKY_SESSION = None
_BSKY_SESSION_TS = 0

def get_bsky_token(identifier: str, password: str) -> str:
    global _BSKY_SESSION, _BSKY_SESSION_TS
    
    now = time.time()
    if _BSKY_SESSION and (now - _BSKY_SESSION_TS < 3600):
        return _BSKY_SESSION

    if not identifier or not password:
        return ""

    try:
        r = requests.post(
            "https://bsky.social/xrpc/com.atproto.server.createSession",
            json={"identifier": identifier, "password": password},
            headers={"User-Agent": "RadioOS/1.0"},
            timeout=10
        )
        if r.status_code == 200:
            _BSKY_SESSION = r.json().get("accessJwt")
            _BSKY_SESSION_TS = now
            return _BSKY_SESSION
        else:
            print(f"[Bluesky] Auth failed: {r.status_code} {r.text}")
            
            # Retry with suffix if missing
            if "." not in identifier:
                print(f"[Bluesky] Retrying with .bsky.social suffix...")
                r2 = requests.post(
                    "https://bsky.social/xrpc/com.atproto.server.createSession",
                    json={"identifier": identifier + ".bsky.social", "password": password},
                    headers={"User-Agent": "RadioOS/1.0"},
                    timeout=10
                )
                if r2.status_code == 200:
                    _BSKY_SESSION = r2.json().get("accessJwt")
                    _BSKY_SESSION_TS = now
                    return _BSKY_SESSION
                else:
                    print(f"[Bluesky] Auth retry failed: {r2.status_code} {r2.text}")

    except Exception as e:
        print(f"[Bluesky] Auth exception: {e}")
        pass
    
    return ""


def fetch_bluesky_tags(tags: List[str], identifier: str = "", password: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    # Get token if credentials provided
    token = get_bsky_token(identifier, password)
    
    headers = {"User-Agent": "RadioOS/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        # Use main PDS if authenticated
        base_url = "https://bsky.social/xrpc/app.bsky.feed.searchPosts"
    else:
        # Fallback to public (likely broken/limited)
        base_url = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"

    for tag in tags:
        # Fetch both "Latest" (News) and "Top" (Existing/Trending)
        for sort_order in ["latest", "top"]:
            try:
                # Split limit to avoid double-dipping too hard
                eff_limit = max(5, int(limit / 2))
                
                r = requests.get(
                    base_url,
                    params={
                        "q": f"#{tag}",
                        "limit": eff_limit,
                        "sort": sort_order
                    },
                    headers=headers,
                    timeout=10
                )

                if r.status_code != 200:
                    print(f"[Bluesky] Error fetching #{tag} ({sort_order}): {r.status_code}")
                    continue

                posts = r.json().get("posts", [])
                print(f"[Bluesky] #{tag} ({sort_order}) found {len(posts)} items")

                for p in posts:

                    pid = p.get("uri")
                    if not pid:
                        continue

                    text = (p.get("record") or {}).get("text", "")
                    
                    # Bluesky "Top" posts might be old, so check date if needed
                    # But for "existing" content per user request, we allow older hits.

                    out.append({
                        "post_id": pid,
                        "title": text[:120],
                        "body": text,
                    })

            except Exception:
                pass

    return out


# ======================================================
# Radio OS Plugin Entrypoint
# ======================================================

def feed_worker(stop_event, mem, cfg, runtime=None):
    """
    Bluesky hashtag feed plugin (spec compliant)
    """
    
    # Runtime hooks (safe access)
    rt = runtime or {}
    emit_candidate = rt.get("emit_candidate")
    ui_update = rt.get("ui_widget_update")
    # If StationEvent/event_q not passed, fallback (though runtime usually passes them)
    _StationEvent = rt.get("StationEvent") or (lambda **k: k)
    _event_q = rt.get("event_q")

    tags = list(cfg.get("hashtags", []))
    poll_sec = float(cfg.get("poll_sec", 60))
    limit = int(cfg.get("limit", 20))
    priority = float(cfg.get("priority", 70.0))
    burst_delay = float(cfg.get("burst_delay", 0.25))
    
    identifier = cfg.get("identifier", "")
    password = cfg.get("password", "")
    
    if not identifier or not password:
        import os
        identifier = identifier or os.environ.get("BLUESKY_HANDLE", "")
        password = password or os.environ.get("BLUESKY_PASSWORD", "")

    if not identifier or not password:
        print("⚠️  Bluesky plugin: Missing credentials. Public search API is now restricted.")
        time.sleep(2)

    seen_local = set()

    while not stop_event.is_set():

        if not tags:
            time.sleep(2.0)
            continue

        posts = fetch_bluesky_tags(tags, identifier=identifier, password=password, limit=limit)

        for p in posts:
            pid = p["post_id"]

            if pid in seen_local:
                continue

            seen_local.add(pid)

            title = p.get("title", "")
            body = p.get("body", "")

            # --------------------
            # Widget Update
            # --------------------
            if ui_update:
                ui_update("bluesky_latest", {
                    "title": title,
                    "body": body,
                    "post_id": pid
                })

            # --------------------
            # Producer candidate (Normalized)
            # --------------------
            if emit_candidate:
                emit_candidate({
                    "id": sha1(f"bsky|{pid}|{now_ts()}"),
                    "post_id": pid,
                    "source": "bluesky",
                    "event_type": "item",
                    "title": title,
                    "body": body,
                    "comments": [],
                    "heur": priority,
                })
            else:
                # Fallback if runtime not provided (legacy)
                mem.setdefault("feed_candidates", []).append({
                    "id": sha1(f"bsky|{pid}|{now_ts()}"),
                    "post_id": pid,
                    "source": "bluesky",
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
# BLUESKY WIDGET
# ======================================================

def register_widgets(registry, runtime):
    
    tk = runtime["tk"]

    BG = "#0e0e0e"
    CARD = "#111b24"        # Slight blue tint
    BORDER = "#1e2933"
    ACCENT = "#0085ff"      # Bluesky Blue
    TEXT = "#e8e8e8"
    MUTED = "#8a9aa9"

    def widget_factory(parent, rt):
        
        root = tk.Frame(parent, bg=BG)

        # Header
        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", pady=(2, 6))
        
        lbl = tk.Label(
            header, 
            text="Bluesky Feed", 
            bg=BG, fg=ACCENT, 
            font=("Segoe UI", 9, "bold")
        )
        lbl.pack(side="left", padx=4)

        # Container
        container = tk.Frame(root, bg=BG)
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=BG)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=parent.winfo_width())
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Adjust width on resize
        def on_resize(event):
            canvas.itemconfig(canvas.find_withtag("all")[0], width=event.width)
        canvas.bind("<Configure>", on_resize)

        # State
        items = []

        def render_item(data):
            # Create card
            card = tk.Frame(
                scrollable_frame, 
                bg=CARD, 
                highlightbackground=BORDER, 
                highlightthickness=1,
                pady=8, padx=8
            )
            card.pack(fill="x", pady=4, padx=2, anchor="n")
            
            # Post Text
            msg = tk.Label(
                card, 
                text=data.get("body", ""), 
                bg=CARD, fg=TEXT, 
                font=("Segoe UI", 9), 
                wraplength=280, 
                justify="left",
                anchor="w"
            )
            msg.pack(fill="x", anchor="w")
            
            # Footer (ID)
            foot = tk.Label(
                card,
                text=str(data.get("post_id", ""))[-12:],
                bg=CARD, fg=MUTED,
                font=("Segoe UI", 7)
            )
            foot.pack(anchor="e", pady=(4,0))

            items.insert(0, card)
            if len(items) > 30:
                old = items.pop()
                old.destroy()

        # Hook listener
        def on_update(key, data):
            if key == "bluesky_latest":
                # Schedule GUI update on main thread
                if getattr(parent, "after", None):
                    parent.after(0, lambda: render_item(data))
        
        # Register listener
        if "ui_q" in rt:
            # We can't direct subscribe here easily without a complex event bus, 
            # BUT the runtime's UiLoop (shell.py) often routes these if we use a specific queue pattern.
            # However, simpler pattern: The runtime calls 'update()' on registered widgets? 
            # Actually, standard RadioOS widget pattern is usually polling or queue-driven.
            # But here we used a closure.
            
            # Let's attach the update method to the root widget so the UI loop can find it
            # (Requires shell support or a specific widget_key registry).
            root.update_widget = on_update

        return root

    registry.register(
        "bluesky",
        widget_factory,
        title="Bluesky Feed"
    )

