import os
import time
import hashlib
import random
from typing import Any, Dict, List

# Import runtime objects
from runtime import StationEvent, event_q


# --------------------
# Helpers
# --------------------

def now_ts() -> int:
    return int(time.time())

def sha1(x: Any) -> str:
    s = "" if x is None else str(x)
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()

def clamp_text(t: str, n: int = 1400) -> str:
    t = (t or "").strip()
    if len(t) <= n:
        return t
    return t[: n - 3].rstrip() + "..."

def file_read(path: str, max_chars: int) -> str:
    try:
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return (f.read() or "")[:max_chars]
    except Exception:
        return ""


# ======================================================
# Radio OS Plugin Entrypoint
# ======================================================

def feed_worker(stop_event, mem, cfg):
    """
    Document watcher plugin (spec compliant)

    feeds:
      document:
        enabled: true
        files:
          - name: strategy
            path: "./strategy_reference.txt"
            max_chars: 5000
            announce: true
            announce_priority: 86
            candidate: false

          - name: playbook
            path: "./coach_playbook.txt"
            max_chars: 7000
            announce: false
            candidate: true
            candidate_priority: 80

        poll_sec: 2.5
        announce_cooldown_sec: 600
    """

    files_cfg = cfg.get("files", [])
    if not isinstance(files_cfg, list):
        files_cfg = []

    poll_sec = float(cfg.get("poll_sec", 2.5))
    announce_cooldown_sec = float(cfg.get("announce_cooldown_sec", 600))

    mem.setdefault("docs", {})
    ann_last = mem.setdefault("_doc_announce_last", {})

    mtimes: Dict[str, float] = {}

    while not stop_event.is_set():

        try:
            for fc in files_cfg:

                if not isinstance(fc, dict):
                    continue

                name = str(fc.get("name", "")).strip() or "doc"
                path = str(fc.get("path", "")).strip()

                if not path:
                    continue

                max_chars = int(fc.get("max_chars", 5000))

                announce = bool(fc.get("announce", False))
                announce_priority = float(fc.get("announce_priority", 86.0))

                as_candidate = bool(fc.get("candidate", False))
                candidate_priority = float(fc.get("candidate_priority", 80.0))

                # --------------------
                # Change detection
                # --------------------

                try:
                    mtime = os.path.getmtime(path) if os.path.exists(path) else 0.0
                except Exception:
                    mtime = 0.0

                if mtimes.get(path) == mtime:
                    continue

                mtimes[path] = mtime

                text = file_read(path, max_chars)
                h = sha1(text)

                cur = mem["docs"].get(name, {})

                if isinstance(cur, dict) and cur.get("hash") == h:
                    continue

                # --------------------
                # Update soft memory
                # --------------------

                mem["docs"][name] = {
                    "text": text,
                    "hash": h,
                    "ts": now_ts(),
                    "path": path,
                    "max_chars": max_chars,
                }

                now = now_ts()
                last_ann = int(ann_last.get(name, 0))

                # --------------------
                # Realtime announcement event
                # --------------------

                if announce and (now - last_ann) >= announce_cooldown_sec:

                    ann_last[name] = now

                    evt = StationEvent(
                        source="document",
                        type="document_update",
                        ts=now,
                        severity=0.0,
                        priority=announce_priority,
                        payload={
                            "title": f"Document updated: {name}",
                            "body": clamp_text(
                                f"The {name} reference file was updated. The station will use it for framing.",
                                1200
                            ),
                            "angle": "Briefly acknowledge and continue the show.",
                            "why": "Background knowledge changed.",
                            "key_points": ["context update"],
                            "host_hint": "quick_note",
                        }
                    )

                    event_q.put(evt)

                # --------------------
                # Producer candidate (optional)
                # --------------------

                if as_candidate:

                    mem.setdefault("feed_candidates", []).append({
                        "id": sha1(f"cand|doc|{name}|{now}|{random.random()}"),
                        "post_id": sha1(f"candpost|doc|{name}|{now}"),
                        "source": "document",
                        "event_type": "document_context",
                        "title": f"Reference document: {name}",
                        "body": text[:1200],
                        "comments": [],
                        "heur": candidate_priority,
                    })

        except Exception:
            pass

        time.sleep(poll_sec)
