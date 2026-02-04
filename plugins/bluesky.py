import time
import requests
import hashlib
from typing import Any, Dict, List

# Import runtime objects
from runtime import StationEvent, event_q


# --------------------
# Helpers
# --------------------

def now_ts() -> int:
    return int(time.time())

def sha1(x: Any) -> str:
    return hashlib.sha1(str(x).encode("utf-8", errors="ignore")).hexdigest()


def fetch_bluesky_tags(tags: List[str], limit: int = 20) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for tag in tags:
        try:
            r = requests.get(
                "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
                params={
                    "q": f"#{tag}",
                    "limit": limit
                },
                timeout=15
            )

            posts = r.json().get("posts", [])

            for p in posts:

                pid = p.get("uri")
                if not pid:
                    continue

                text = (p.get("record") or {}).get("text", "")

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

def feed_worker(stop_event, mem, cfg):
    """
    Bluesky hashtag feed plugin (spec compliant)

    feeds:
      bluesky_feed:
        enabled: true
        hashtags: ["crypto", "bitcoin", "trading"]
        poll_sec: 60
        limit: 20
        priority: 70
    """

    tags = list(cfg.get("hashtags", []))
    poll_sec = float(cfg.get("poll_sec", 60))
    limit = int(cfg.get("limit", 20))
    priority = float(cfg.get("priority", 70.0))

    seen_local = set()

    while not stop_event.is_set():

        if not tags:
            time.sleep(2.0)
            continue

        posts = fetch_bluesky_tags(tags, limit=limit)

        for p in posts:
            pid = p["post_id"]

            if pid in seen_local:
                continue

            seen_local.add(pid)

            title = p.get("title", "")
            body = p.get("body", "")

            # --------------------
            # Realtime event path
            # --------------------

            evt = StationEvent(
                source="bluesky",
                type="post",
                ts=now_ts(),
                severity=0.0,
                priority=priority,
                payload={
                    "title": title,
                    "body": body,
                    "angle": "Paraphrase and react naturally to this post.",
                    "why": "Trending social discussion just appeared.",
                    "key_points": ["new post", "community sentiment"],
                    "host_hint": "Quick social pulse."
                }
            )

            event_q.put(evt)

            # --------------------
            # Producer candidate path
            # --------------------

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

        time.sleep(poll_sec)
