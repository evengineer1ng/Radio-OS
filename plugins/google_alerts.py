import time
import feedparser
import os, sqlite3, json, hashlib, random
import html
import re


# =====================================================
# Helpers
# =====================================================

def now_ts():
    return int(time.time())


def sha1(x):
    return hashlib.sha1(str(x).encode()).hexdigest()


# -------------------------
# DB
# -------------------------

def db_connect():
    db_path = os.environ.get("STATION_DB_PATH", "station.sqlite")
    return sqlite3.connect(db_path, check_same_thread=False, timeout=30)


def db_enqueue(conn, seg):
    conn.execute("""
        INSERT OR IGNORE INTO segments (
            id, created_ts, priority, status,
            post_id, source, event_type,
            title, body,
            comments_json, angle, why, key_points_json, host_hint
        ) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        seg["id"],
        now_ts(),
        seg["priority"],
        seg["post_id"],
        seg["source"],
        seg["event_type"],
        seg["title"],
        seg["body"],
        json.dumps([]),
        seg["angle"],
        seg["why"],
        json.dumps(seg["key_points"]),
        seg["host_hint"],
    ))
    conn.commit()


# -------------------------
# Cleaning utils
# -------------------------

_TAG_RE = re.compile(r"<[^>]+>")

def clean_html(text):
    if not text:
        return ""

    text = html.unescape(text)
    text = _TAG_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def is_link_garbage(text):
    if not text:
        return True

    t = text.strip().lower()

    # pure URL
    if t.startswith("http"):
        return True

    # short teaser containing url
    if "http" in t and len(t) < 150:
        return True

    # common rss junk phrases
    junk = [
        "read more",
        "read full story",
        "continue reading",
        "click here",
        "view article"
    ]

    for j in junk:
        if j in t and "http" in t:
            return True

    return False


# =====================================================
# RSS Worker (ACTIVE ONE)
# =====================================================

def feed_worker(stop_event, mem, *args):

    cfg = args[0] if args and isinstance(args[0], dict) else {}

    urls = list(cfg.get("urls", []))
    poll = float(cfg.get("poll_sec", 180))

    seen = set()

    conn = db_connect()

    while not stop_event.is_set():

        for url in urls:

            try:
                feed = feedparser.parse(url)

                for e in feed.entries:

                    pid = e.get("id") or e.get("link")
                    if not pid or pid in seen:
                        continue

                    seen.add(pid)

                    # -------------------------
                    # TITLE
                    # -------------------------
                    raw_title = e.get("title", "")
                    title = clean_html(raw_title)

                    # -------------------------
                    # BODY (real summary)
                    # -------------------------

                    raw_body = ""

                    # prefer rich content if present
                    if e.get("content"):
                        try:
                            raw_body = e["content"][0].get("value", "")
                        except Exception:
                            pass

                    # fallback
                    if not raw_body:
                        raw_body = (
                            e.get("summary") or
                            e.get("description") or
                            ""
                        )

                    body = clean_html(raw_body)

                    # kill garbage link-only payloads
                    if is_link_garbage(body):
                        body = ""

                    # final fallback
                    if not body:
                        body = title

                    if not title and not body:
                        continue

                    seg = {
                        "id": sha1(f"rss|{pid}|{now_ts()}"),
                        "post_id": pid,

                        "source": "feed",
                        "event_type": "item",

                        "title": title,
                        "body": body,

                        "angle": "Paraphrase and react to this alert.",
                        "why": "New information surfaced from monitored topics.",
                        "key_points": ["new alert", "potential market relevance"],

                        "priority": 72.0,
                        "host_hint": "New alert just in."
                    }

                    # ---- enqueue for airtime
                    db_enqueue(conn, seg)

                    # ---- publish for producer
                    mem.setdefault("feed_candidates", []).append({
                        "post_id": seg["post_id"],
                        "id": seg["id"],
                        "source": "feed",
                        "event_type": "item",
                        "title": title,
                        "body": body,
                        "comments": [],
                        "heur": 72.0,
                    })

            except Exception:
                pass

        time.sleep(poll)
