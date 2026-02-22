"""
FTB Web Server — Embedded FastAPI server for phone/browser access.

Runs as a daemon thread inside bookmark.py. Serves:
  - REST API for game state & commands
  - WebSocket for live subtitle/event streaming
  - Static Svelte SPA from web/dist/

Usage: auto-started by bookmark.py main() on boot.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import threading
import time
from collections import deque, defaultdict
from typing import Any, Dict, List, Optional, Set

PLUGIN_NAME = "ftb_web_server"
PLUGIN_DESC = "Embedded web server for phone/browser FTB access"
IS_FEED = False

# ─── Lazy imports (deferred so we don't crash if not installed) ────────────
_fastapi = None
_uvicorn = None

def _ensure_imports():
    global _fastapi, _uvicorn
    if _fastapi is None:
        import fastapi
        _fastapi = fastapi
    if _uvicorn is None:
        import uvicorn
        _uvicorn = uvicorn


# ═══════════════════════════════════════════════════════════════════
# WebBridge — shared state mirror between tkinter UI and web clients
# ═══════════════════════════════════════════════════════════════════

class WebBridge:
    """Thread-safe bridge that bookmark.py writes to and the web server reads from."""

    # All valid in-game tab IDs (must match App.svelte tab list)
    VALID_TABS = {
        "dashboard", "team", "car", "development", "raceops", "pbp",
        "finance", "sponsors", "promotion", "stats", "analytics", "career",
        "calendar", "ai", "penalties", "history", "help", "data",
    }

    def __init__(self):
        self._lock = threading.Lock()
        self.last_subtitle: str = ""
        self.last_widget_update: Dict[str, Any] = {}
        self.event_log: deque = deque(maxlen=500)
        self.connected_clients: Set[Any] = set()  # WebSocket refs
        self._broadcast_queue: asyncio.Queue | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        # UI screen state for Audio CLI navigation
        # Possible values: "landing", "wizard", "loading", "game"
        self.ui_screen: str = "landing"
        self.wizard_step: int = 1
        self.wizard_fields: Dict[str, Any] = {}
        self.active_tab: str = "dashboard"

    # Called from bookmark.py _poll_queues thread (tkinter main thread)
    def update_subtitle(self, text: str):
        with self._lock:
            self.last_subtitle = text
        self._enqueue_broadcast("subtitle", {"text": text})

    def update_widget(self, widget_key: str, data: Any):
        with self._lock:
            self.last_widget_update[widget_key] = data
            self.event_log.append({
                "type": "widget_update",
                "widget_key": widget_key,
                "data": data,
                "ts": time.time()
            })
        self._enqueue_broadcast("widget_update", {
            "widget_key": widget_key,
            "data": data
        })

    def push_event(self, event_type: str, payload: Any):
        """Push any ui_q event (now_playing, batch_summary, etc.)."""
        with self._lock:
            self.event_log.append({
                "type": event_type,
                "data": payload,
                "ts": time.time()
            })
        self._enqueue_broadcast(event_type, payload)

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "subtitle": self.last_subtitle,
                "widget_updates": dict(self.last_widget_update),
                "recent_events": list(self.event_log)[-50:],
            }

    def navigate_to(self, screen: str, wizard_step: int = 1):
        """Change the UI screen and broadcast to all connected clients.
        Valid screens: 'landing', 'wizard', 'loading', 'game'."""
        with self._lock:
            self.ui_screen = screen
            self.wizard_step = wizard_step
        self._enqueue_broadcast("navigate", {
            "screen": screen,
            "wizard_step": wizard_step,
        })

    def set_wizard_step(self, step: int):
        """Update the wizard step and broadcast."""
        with self._lock:
            self.wizard_step = step
        self._enqueue_broadcast("navigate", {
            "screen": "wizard",
            "wizard_step": step,
        })

    def set_wizard_field(self, field: str, value: Any):
        """Set a wizard field value and broadcast to connected clients."""
        with self._lock:
            self.wizard_fields[field] = value
        self._enqueue_broadcast("wizard_field", {
            "field": field,
            "value": value,
        })

    def get_ui_screen(self) -> Dict[str, Any]:
        """Return the current UI screen state for Audio CLI introspection."""
        with self._lock:
            return {
                "screen": self.ui_screen,
                "wizard_step": self.wizard_step,
                "wizard_fields": dict(self.wizard_fields),
                "active_tab": self.active_tab,
            }

    def switch_tab(self, tab_id: str) -> bool:
        """Switch the active in-game tab and broadcast to all clients.
        Returns True if the tab was valid, False otherwise."""
        tab_id = tab_id.strip().lower()
        if tab_id not in self.VALID_TABS:
            return False
        with self._lock:
            self.active_tab = tab_id
        self._enqueue_broadcast("switch_tab", {"tab": tab_id})
        return True

    def _enqueue_broadcast(self, event_type: str, data: Any):
        """Push a message to all connected WebSocket clients."""
        if self._broadcast_queue and self._loop:
            msg = json.dumps({"type": event_type, "data": data}, default=str)
            try:
                self._loop.call_soon_threadsafe(self._broadcast_queue.put_nowait, msg)
            except Exception:
                pass  # Queue full or loop closed — non-fatal

    def set_async_context(self, loop: asyncio.AbstractEventLoop, bq: asyncio.Queue):
        """Called once by the server thread after the event loop starts."""
        self._loop = loop
        self._broadcast_queue = bq


# Singleton — created once, stored in shared_runtime["web_bridge"]
_bridge: Optional[WebBridge] = None

def get_bridge() -> WebBridge:
    global _bridge
    if _bridge is None:
        _bridge = WebBridge()
    return _bridge


# ═══════════════════════════════════════════════════════════════════
# State Serializer — extracts JSON-safe game state from FTBController
# ═══════════════════════════════════════════════════════════════════

def serialize_entity(entity, state=None) -> Dict[str, Any]:
    """Serialize a Driver/Engineer/Mechanic/Strategist/Principal to dict."""
    if entity is None:
        return None
    d: Dict[str, Any] = {
        "name": getattr(entity, "name", "Unknown"),
        "type": getattr(entity, "entity_type", type(entity).__name__),
        "age": getattr(entity, "age", 0),
        "overall": getattr(entity, "overall_rating", 0) if hasattr(entity, "overall_rating") else 0,
    }
    # Extra useful fields for detail view
    for attr in ("entity_id", "potential_ceiling", "potential_rating",
                 "form_momentum", "morale_baseline", "display_name"):
        val = getattr(entity, attr, None)
        if val is not None:
            d[attr] = round(float(val), 1) if isinstance(val, float) else val
    # Grab stat dict if available — entities use 'current_ratings', fallback to 'stats'
    ratings = getattr(entity, "current_ratings", None)
    if ratings and isinstance(ratings, dict):
        d["stats"] = {k: round(float(v), 1) for k, v in ratings.items() if isinstance(v, (int, float))}
    elif hasattr(entity, "stats") and isinstance(entity.stats, dict):
        d["stats"] = {k: round(float(v), 1) for k, v in entity.stats.items() if isinstance(v, (int, float))}
    elif hasattr(entity, "to_dict"):
        try:
            d.update(entity.to_dict())
        except Exception:
            pass
    # Contract info — try entity.contract first, then look up in state.contracts
    contract = getattr(entity, "contract", None)
    entity_id = getattr(entity, "entity_id", None)
    if not contract and state and entity_id is not None:
        contracts = getattr(state, "contracts", {})
        contract = contracts.get(entity_id)
    if contract:
        # seasons_remaining may be a method or a static value
        sr = getattr(contract, "seasons_remaining", 0)
        if callable(sr):
            try:
                current_day = getattr(state, "tick", 0) if state else 0
                sr = round(sr(current_day), 1)
            except Exception:
                sr = 0
        d["contract"] = {
            "salary": getattr(contract, "base_salary", 0),
            "seasons_remaining": sr,
            "buyout": getattr(contract, "buyout_clause_fixed", None) or getattr(contract, "buyout_clause", 0) or 0,
            "role": getattr(contract, "role", ""),
        }
    return d


def _part_cost(part) -> int:
    """Calculate part cost using the same formula as FTBSimulation.calculate_part_cost."""
    base_cost = {
        'engine': 100000, 'chassis': 150000, 'aero_package': 120000,
        'suspension': 80000, 'tires': 30000, 'brakes': 50000,
        'cooling': 60000, 'electronics': 90000, 'transmission': 85000,
    }
    cost = base_cost.get(getattr(part, "part_type", ""), 50000)
    cost *= (1.0 + (getattr(part, "generation", 1) - 1) * 0.25)
    perf = getattr(part, "performance_score", None)
    if perf is None:
        # fallback: average of current_ratings
        ratings = getattr(part, "current_ratings", None)
        if ratings and isinstance(ratings, dict):
            vals = [v for v in ratings.values() if isinstance(v, (int, float))]
            perf = (sum(vals) / len(vals)) if vals else 50.0
        else:
            perf = 50.0
    cost *= (perf / 50.0)
    tier_min = getattr(part, "tier_minimum", 1)
    cost *= (1.0 + (tier_min - 1) * 0.2)
    return int(cost)


def _part_is_tier_compatible(part, team_tier: Optional[int]) -> bool:
    """Return True when a part can be used by the given team tier."""
    if team_tier is None:
        return True
    try:
        tier = int(team_tier)
    except Exception:
        return True

    tier_min = getattr(part, "tier_minimum", None)
    tier_max = getattr(part, "tier_maximum", None)
    if tier_min is None and tier_max is None:
        return True
    if tier_min is None:
        tier_min = tier
    if tier_max is None:
        tier_max = tier

    try:
        return int(tier_min) <= tier <= int(tier_max)
    except Exception:
        return True


def serialize_part(part) -> Dict[str, Any]:
    """Serialize a Part entity to dict for the web frontend."""
    if part is None:
        return None
    # quality = overall_rating (avg of current_ratings)
    overall = 0
    ratings = getattr(part, "current_ratings", None)
    if ratings and isinstance(ratings, dict):
        vals = [v for v in ratings.values() if isinstance(v, (int, float))]
        overall = round(sum(vals) / len(vals), 1) if vals else 0
    elif hasattr(part, "overall_rating"):
        overall = round(getattr(part, "overall_rating", 0), 1)

    d: Dict[str, Any] = {
        "id": getattr(part, "part_id", ""),
        "name": getattr(part, "name", "") or getattr(part, "display_name", ""),
        "type": getattr(part, "part_type", ""),
        "age": int(getattr(part, "age", 0) or 0),
        "quality": overall,
        "cost": _part_cost(part),
        "generation": getattr(part, "generation", 1),
        "manufacturer_id": getattr(part, "manufacturer_id", ""),
        "effectiveness": round(getattr(part, "effectiveness_modifier", 1.0), 2),
    }
    # Include individual stats
    if ratings and isinstance(ratings, dict):
        d["stats"] = {k: round(float(v), 1) for k, v in ratings.items() if isinstance(v, (int, float))}
    return d


def _json_safe(value: Any) -> Any:
    """Best-effort conversion to JSON-safe primitives for event payloads."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "__dict__"):
        try:
            return {str(k): _json_safe(v) for k, v in vars(value).items()}
        except Exception:
            return str(value)
    return str(value)


def _build_player_driver_recent_results(state, per_driver: int = 6) -> List[Dict[str, Any]]:
    """Return recent race finishes for each player-team driver (newest first)."""
    team = getattr(state, "player_team", None)
    if not team:
        return []

    driver_names = [getattr(d, "name", "") for d in (getattr(team, "drivers", None) or []) if d]
    driver_names = [name for name in driver_names if name]
    if not driver_names:
        return []

    team_name = getattr(team, "name", "")
    results_by_driver: Dict[str, List[Dict[str, Any]]] = {name: [] for name in driver_names}
    seen_keys: Set[str] = set()

    def _is_full() -> bool:
        return all(len(rows) >= per_driver for rows in results_by_driver.values())

    def _append_result(driver: str, row: Dict[str, Any], uniq_key: str) -> None:
        if driver not in results_by_driver:
            return
        if len(results_by_driver[driver]) >= per_driver:
            return
        if uniq_key in seen_keys:
            return
        seen_keys.add(uniq_key)
        results_by_driver[driver].append(row)

    # 1) Primary source: full in-memory event history.
    for evt in reversed(getattr(state, "event_history", []) or []):
        category = getattr(evt, "category", "") or getattr(evt, "event_type", "")
        if category != "race_result":
            continue

        data = getattr(evt, "data", {}) or {}
        event_team = str(data.get("team") or data.get("team_name") or data.get("player_team_name") or "")
        driver = str(data.get("driver") or "")
        if event_team != team_name or driver not in results_by_driver:
            continue

        tick = int(getattr(evt, "ts", 0) or 0)
        round_number = int(data.get("round_number", 0) or 0)
        track_name = str(data.get("track_name") or "")
        position = int(data.get("position", 0) or 0)
        points = float(data.get("points", 0) or 0)
        status = str(data.get("status") or "finished")
        uniq = f"evt:{driver}:{tick}:{round_number}:{track_name}:{position}:{status}"

        _append_result(
            driver,
            {
                "tick": tick,
                "season": int(getattr(state, "season_number", 0) or 0),
                "round": round_number,
                "driver": driver,
                "position": position,
                "points": points,
                "status": status,
                "track_name": track_name,
                "league_id": str(data.get("league_id") or ""),
                "league_name": str(data.get("league_name") or ""),
            },
            uniq,
        )
        if _is_full():
            break

    # 2) Fallback: archived race results DB (helps older saves with trimmed event history).
    if not _is_full():
        db_path = getattr(state, "state_db_path", None)
        if db_path:
            try:
                from plugins import ftb_state_db

                archive_rows = ftb_state_db.query_race_results(
                    db_path=db_path,
                    limit=max(80, per_driver * 16)
                )
                for race in archive_rows:
                    if str(race.get("player_team_name", "")) != team_name:
                        continue
                    finish_positions = race.get("finish_positions", []) or []
                    for finish in finish_positions:
                        if str(finish.get("team", "")) != team_name:
                            continue
                        driver = str(finish.get("driver", ""))
                        if driver not in results_by_driver:
                            continue
                        if len(results_by_driver[driver]) >= per_driver:
                            continue
                        round_number = int(race.get("round_number", 0) or 0)
                        season = int(race.get("season", 0) or 0)
                        track_name = str(race.get("track_name") or "")
                        tick = int(race.get("tick", 0) or 0)
                        position = int(finish.get("position", 0) or 0)
                        status = str(finish.get("status") or "finished")
                        uniq = f"db:{race.get('race_id', '')}:{driver}:{position}:{status}"
                        _append_result(
                            driver,
                            {
                                "tick": tick,
                                "season": season,
                                "round": round_number,
                                "driver": driver,
                                "position": position,
                                "points": 0.0,
                                "status": status,
                                "track_name": track_name,
                                "league_id": str(race.get("league_id") or ""),
                                "league_name": "",
                            },
                            uniq,
                        )
                    if _is_full():
                        break
            except Exception:
                pass

    return [{"name": name, "results": results_by_driver.get(name, [])} for name in driver_names]


def _serialize_promotion_opportunities(state) -> List[Dict[str, Any]]:
    """Return player-team promotion opportunities in a stable JSON shape."""
    team = getattr(state, "player_team", None)
    if not team:
        return []
    team_name = getattr(team, "name", "")
    now_tick = int(getattr(state, "tick", 0) or 0)

    out: List[Dict[str, Any]] = []
    for opp in (getattr(state, "promotion_opportunities", None) or []):
        if not isinstance(opp, dict):
            continue
        if str(opp.get("team", "")) != team_name:
            continue
        row = _json_safe(opp)
        status = str(row.get("status", "open")).lower()
        expires_tick = int(row.get("expires_tick", 0) or 0)
        if status == "open" and expires_tick and now_tick > expires_tick:
            status = "expired"
        row["status"] = status
        out.append(row)

    out.sort(key=lambda r: int(r.get("created_tick", 0) or 0), reverse=True)
    return out


def _build_play_by_play_history(state, limit: int = 20) -> List[Dict[str, Any]]:
    """Return recent race history entries for Play-by-Play tab."""
    team = getattr(state, "player_team", None)
    if not team:
        return []
    team_name = getattr(team, "name", "")
    rows: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    def _append(row: Dict[str, Any], uniq: str) -> None:
        if uniq in seen:
            return
        seen.add(uniq)
        rows.append(row)

    # 1) Primary source: race archive DB (stable across long saves).
    db_path = getattr(state, "state_db_path", None)
    if db_path:
        try:
            from plugins import ftb_state_db

            archived = ftb_state_db.query_race_results(
                db_path=db_path,
                limit=max(40, limit * 4)
            )
            for race in archived:
                finish_positions = race.get("finish_positions", []) or []
                winner_row = next(
                    (p for p in finish_positions if int(p.get("position", 99) or 99) == 1),
                    None
                )
                player_rows = [p for p in finish_positions if str(p.get("team", "")) == team_name]
                race_player_team = str(race.get("player_team_name", ""))
                if not player_rows and race_player_team != team_name:
                    continue
                player_best = min(
                    player_rows,
                    key=lambda p: int(p.get("position", 999) or 999),
                    default=None,
                )

                winner_driver = str(winner_row.get("driver", "—")) if winner_row else "—"
                winner_team = str(winner_row.get("team", "—")) if winner_row else "—"
                race_id = str(race.get("race_id") or "")
                season = int(race.get("season", 0) or 0)
                round_no = int(race.get("round_number", 0) or 0)
                track_name = str(race.get("track_name") or "Unknown Circuit")

                _append(
                    {
                        "race_id": race_id,
                        "name": f"S{season} R{round_no} • {track_name}",
                        "season": season,
                        "round": round_no,
                        "track_name": track_name,
                        "league_id": str(race.get("league_id") or ""),
                        "tick": int(race.get("tick", 0) or 0),
                        "winner": f"{winner_driver} ({winner_team})" if winner_driver != "—" else "—",
                        "winner_driver": winner_driver,
                        "winner_team": winner_team,
                        "player_finish": int(player_best.get("position", 0) or 0) if player_best else None,
                        "player_driver": str(player_best.get("driver", "")) if player_best else "",
                        "player_status": str(player_best.get("status", "finished")) if player_best else "",
                    },
                    race_id or f"db:{season}:{round_no}:{track_name}:{race.get('tick', 0)}",
                )
                if len(rows) >= limit:
                    return rows[:limit]
        except Exception:
            pass

    # 2) Fallback: in-memory event history (group per race).
    grouped: Dict[str, Dict[str, Any]] = {}
    for evt in reversed(getattr(state, "event_history", []) or []):
        category = getattr(evt, "category", "") or getattr(evt, "event_type", "")
        if category != "race_result":
            continue
        data = getattr(evt, "data", {}) or {}
        tick = int(getattr(evt, "ts", 0) or 0)
        league_id = str(data.get("league_id") or "")
        season = int(getattr(state, "season_number", 0) or 0)
        round_no = int(data.get("round_number", 0) or 0)
        track_name = str(data.get("track_name") or "Unknown Circuit")
        key = f"mem:{tick}:{league_id}:{round_no}:{track_name}"
        slot = grouped.setdefault(
            key,
            {
                "race_id": "",
                "name": f"S{season} R{round_no} • {track_name}",
                "season": season,
                "round": round_no,
                "track_name": track_name,
                "league_id": league_id,
                "tick": tick,
                "entries": [],
            },
        )
        slot["entries"].append(
            {
                "driver": str(data.get("driver") or ""),
                "team": str(data.get("team") or ""),
                "position": int(data.get("position", 999) or 999),
                "status": str(data.get("status") or "finished"),
            }
        )

    for key in sorted(grouped.keys(), key=lambda k: grouped[k].get("tick", 0), reverse=True):
        slot = grouped[key]
        entries = slot.get("entries", []) or []
        if not entries:
            continue
        winner = min(entries, key=lambda e: int(e.get("position", 999) or 999), default=None)
        player_rows = [e for e in entries if str(e.get("team", "")) == team_name]
        if not player_rows:
            continue
        player_best = min(player_rows, key=lambda e: int(e.get("position", 999) or 999), default=None)

        _append(
            {
                "race_id": str(slot.get("race_id", "")),
                "name": str(slot.get("name", "Race")),
                "season": int(slot.get("season", 0) or 0),
                "round": int(slot.get("round", 0) or 0),
                "track_name": str(slot.get("track_name", "Unknown Circuit")),
                "league_id": str(slot.get("league_id", "")),
                "tick": int(slot.get("tick", 0) or 0),
                "winner": (
                    f"{winner.get('driver', '—')} ({winner.get('team', '—')})"
                    if winner else "—"
                ),
                "winner_driver": str(winner.get("driver", "—")) if winner else "—",
                "winner_team": str(winner.get("team", "—")) if winner else "—",
                "player_finish": int(player_best.get("position", 0) or 0) if player_best else None,
                "player_driver": str(player_best.get("driver", "")) if player_best else "",
                "player_status": str(player_best.get("status", "finished")) if player_best else "",
            },
            key,
        )
        if len(rows) >= limit:
            break

    return rows[:limit]


def _build_play_by_play_telemetry(state, rds, standings: List[Dict[str, Any]], live_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build flat telemetry fields for the Play-by-Play web tab."""
    telemetry: Dict[str, Any] = {}
    phase_obj = getattr(rds, "phase", None)
    phase_val = getattr(phase_obj, "value", phase_obj) if rds else "idle"
    telemetry["phase"] = str(phase_val or "idle")
    telemetry["is_live"] = bool(getattr(rds, "live_race_active", False)) if rds else False
    telemetry["current_lap"] = int(getattr(rds, "current_lap", 0) or 0) if rds else 0
    telemetry["total_laps"] = int(getattr(rds, "total_laps", 0) or 0) if rds else 0
    telemetry["events_logged"] = len(live_events or [])
    telemetry["cars_in_classification"] = len(standings or [])

    if rds and getattr(rds, "live_race_speed", None):
        telemetry["race_speed_sec_per_lap"] = round(float(getattr(rds, "live_race_speed", 0) or 0), 2)
    if rds and getattr(rds, "broadcast_active", None) is not None:
        telemetry["broadcast_active"] = bool(getattr(rds, "broadcast_active", False))

    leader = standings[0] if standings else None
    if isinstance(leader, dict):
        telemetry["leader_driver"] = str(leader.get("driver", ""))
        telemetry["leader_team"] = str(leader.get("team", ""))

    player_row = next((s for s in (standings or []) if isinstance(s, dict) and s.get("is_player")), None)
    if isinstance(player_row, dict):
        telemetry["player_position"] = int(player_row.get("position", 0) or 0)
        telemetry["player_gap"] = round(float(player_row.get("gap", 0) or 0), 3)
        telemetry["player_status"] = str(player_row.get("status", "racing"))

    # Pull lap telemetry for player drivers if available in current race result.
    race_result = getattr(rds, "race_result", None) if rds else None
    race_tel = getattr(race_result, "telemetry", {}) or {}
    if isinstance(race_tel, dict) and race_tel:
        player_drivers = [
            getattr(d, "name", "")
            for d in (getattr(getattr(state, "player_team", None), "drivers", None) or [])
            if d
        ]
        player_rows = [race_tel.get(name, {}) for name in player_drivers if isinstance(race_tel.get(name, {}), dict)]
        if player_rows:
            fastest = [float(r.get("fastest_lap", 0) or 0) for r in player_rows if r.get("fastest_lap")]
            avg_laps = [float(r.get("avg_lap_time", 0) or 0) for r in player_rows if r.get("avg_lap_time")]
            consistency = [float(r.get("consistency_rating", 0) or 0) for r in player_rows if r.get("consistency_rating")]
            if fastest:
                telemetry["player_fastest_lap"] = round(min(fastest), 3)
            if avg_laps:
                telemetry["player_avg_lap_time"] = round(sum(avg_laps) / len(avg_laps), 3)
            if consistency:
                telemetry["player_consistency"] = round(sum(consistency) / len(consistency), 1)

    return telemetry


def _build_history_payload(state, race_history: Optional[List[Dict[str, Any]]] = None, limit_each: int = 80) -> Dict[str, Any]:
    """Return structured history feed for the web History tab."""
    out: Dict[str, Any] = {
        "decisions": [],
        "results": [],
        "transactions": [],
    }

    db_path = getattr(state, "state_db_path", None)
    if db_path:
        try:
            from plugins import ftb_state_db

            decisions = ftb_state_db.query_decision_history(db_path=db_path, limit=limit_each)
            for d in decisions:
                cost_val = float(d.get("immediate_cost", 0) or 0)
                detail = str(d.get("chosen_option_label") or "")
                if cost_val > 0:
                    detail = f"{detail} • Cost ${cost_val:,.0f}" if detail else f"Cost ${cost_val:,.0f}"
                out["decisions"].append({
                    "id": d.get("decision_id"),
                    "tick": int(d.get("tick", 0) or 0),
                    "season": int(d.get("season", 0) or 0),
                    "game_day": int(d.get("game_day", 0) or 0),
                    "label": str(d.get("category") or "decision").replace("_", " "),
                    "description": str(d.get("decision_text") or ""),
                    "detail": detail,
                    "resolved_by": str(d.get("resolved_by") or ""),
                })

            txns = ftb_state_db.query_financial_transactions(db_path=db_path, limit=limit_each)
            for t in txns:
                amount = float(t.get("amount", 0) or 0)
                ttype = str(t.get("type") or "").lower()
                sign = "+" if ttype == "income" else "-"
                out["transactions"].append({
                    "id": t.get("transaction_id"),
                    "tick": int(t.get("tick", 0) or 0),
                    "season": int(t.get("season", 0) or 0),
                    "game_day": int(t.get("game_day", 0) or 0),
                    "label": f"{ttype or 'transaction'} • {str(t.get('category') or '').replace('_', ' ')}",
                    "description": str(t.get("description") or ""),
                    "detail": f"{sign}${abs(amount):,.0f} • Balance ${float(t.get('balance_after', 0) or 0):,.0f}",
                    "amount": amount,
                    "type": ttype,
                    "category": str(t.get("category") or ""),
                })
        except Exception:
            pass

    # Race history is available either from caller or fresh build.
    history_rows = race_history if isinstance(race_history, list) else _build_play_by_play_history(state, limit=limit_each)
    for r in history_rows[:limit_each]:
        pf = r.get("player_finish")
        pf_text = f"P{pf}" if isinstance(pf, int) and pf > 0 else "—"
        detail = f"Your finish: {pf_text}"
        if r.get("player_driver"):
            detail += f" ({r.get('player_driver')})"
        out["results"].append({
            "id": r.get("race_id") or f"{r.get('tick', 0)}:{r.get('track_name', '')}",
            "tick": int(r.get("tick", 0) or 0),
            "season": int(r.get("season", 0) or 0),
            "game_day": None,
            "label": r.get("name") or f"S{r.get('season', 0)} R{r.get('round', 0)}",
            "description": f"Winner: {r.get('winner', '—')}",
            "detail": detail,
            "player_finish": r.get("player_finish"),
        })

    # Event-history fallback for decisions/results if DB isn't available yet.
    if not out["decisions"] or not out["results"]:
        player_team = getattr(state, "player_team", None)
        player_team_name = str(getattr(player_team, "name", "") or "")
        for evt in reversed(getattr(state, "event_history", []) or []):
            tick = int(getattr(evt, "ts", 0) or 0)
            category = str(getattr(evt, "category", "") or "").lower()
            event_type = str(getattr(evt, "event_type", "") or "").lower()
            desc = str(getattr(evt, "description", "") or str(evt))
            data = getattr(evt, "data", {}) or {}
            key = f"{event_type}:{category}"

            if (not out["results"]) and (category == "race_result" or "race" in key):
                event_team = str(data.get("team") or data.get("team_name") or data.get("player_team_name") or "")
                if player_team_name and event_team != player_team_name:
                    continue
                out["results"].append({
                    "id": f"evt:{tick}:{category}",
                    "tick": tick,
                    "season": int(getattr(state, "season_number", 0) or 0),
                    "game_day": None,
                    "label": category or event_type or "race",
                    "description": desc,
                    "detail": "",
                })

            if not out["decisions"]:
                if any(tok in key for tok in ("decision", "hire", "fire", "contract", "focus", "budget")):
                    out["decisions"].append({
                        "id": f"evt:{tick}:{category}",
                        "tick": tick,
                        "season": int(getattr(state, "season_number", 0) or 0),
                        "game_day": None,
                        "label": category or event_type or "decision",
                        "description": desc,
                        "detail": "",
                    })
            if len(out["results"]) >= limit_each and len(out["decisions"]) >= limit_each:
                break

    return out


def serialize_team(team, state=None) -> Dict[str, Any]:
    """Serialize a Team to dict."""
    if team is None:
        return None
    d: Dict[str, Any] = {
        "name": getattr(team, "name", ""),
        "budget": {},
        "roster": {},
        "car": None,
        "infrastructure": {},
        "rd_projects": [],
    }
    # Budget
    budget = getattr(team, "budget", None)
    if budget:
        # Compute weekly expenses: burn_rate * 7 (per-tick → per-week) + staff salaries * 7
        burn_per_tick = getattr(budget, "burn_rate", 0) or 0
        staff_per_tick = sum((getattr(budget, "staff_salaries", {}) or {}).values())
        weekly_expenses = (burn_per_tick + staff_per_tick) * 7

        # Compute weekly income from income_streams
        weekly_income = 0.0
        for inc in (getattr(budget, "income_streams", None) or []):
            amt = getattr(inc, "amount", 0) or 0
            freq = getattr(inc, "frequency", "")
            if freq == "monthly":
                weekly_income += amt / 4.33
            elif freq == "season":
                weekly_income += amt / 52
            elif freq == "per_race":
                weekly_income += amt / 4  # rough: ~1 race per month
            else:
                weekly_income += amt

        d["budget"] = {
            "cash": getattr(budget, "cash", 0),
            "weekly_expenses": round(weekly_expenses, 2),
            "weekly_income": round(weekly_income, 2),
        }
    # Roster
    for role in ("drivers", "engineers", "mechanics", "strategist", "principal"):
        val = getattr(team, role, None)
        if val is None:
            continue
        if isinstance(val, list):
            d["roster"][role] = [serialize_entity(e, state) for e in val if e]
        else:
            d["roster"][role] = serialize_entity(val, state)
    # Car
    car = getattr(team, "car", None)
    if car:
        d["car"] = {
            "name": getattr(car, "name", ""),
            "overall": getattr(car, "overall_rating", 0) if hasattr(car, "overall_rating") else 0,
        }
        # Car stats: use current_ratings (same pattern as entities)
        car_ratings = getattr(car, "current_ratings", None)
        if car_ratings and isinstance(car_ratings, dict):
            d["car"]["stats"] = {k: round(float(v), 1) for k, v in car_ratings.items() if isinstance(v, (int, float))}
        elif hasattr(car, "stats") and isinstance(car.stats, dict):
            d["car"]["stats"] = {k: round(float(v), 1) for k, v in car.stats.items() if isinstance(v, (int, float))}

        def _resolve_part_ref(part_ref: Any):
            """Resolve a part object or legacy part-id string to a Part."""
            if part_ref is None:
                return None
            if isinstance(part_ref, str):
                catalog = getattr(state, "parts_catalog", None) if state else None
                if isinstance(catalog, dict):
                    return catalog.get(part_ref)
                return None
            if hasattr(part_ref, "part_id") or hasattr(part_ref, "part_type"):
                return part_ref
            return None

        def _serialize_part_refs(raw_parts: Any) -> List[Dict[str, Any]]:
            rows: List[Dict[str, Any]] = []
            for part_ref in (raw_parts or []):
                part_obj = _resolve_part_ref(part_ref)
                if not part_obj:
                    continue
                row = serialize_part(part_obj)
                if row:
                    rows.append(row)
            return rows

        # Equipped parts live on the team, not the car: team.equipped_parts is Dict[str, Part]
        equipped = getattr(team, "equipped_parts", None)
        if isinstance(equipped, dict):
            equipped_items = list(equipped.values())
        elif isinstance(equipped, (list, tuple, set)):
            equipped_items = list(equipped)
        else:
            equipped_items = []
        d["car"]["equipped_parts"] = _serialize_part_refs(equipped_items)

        # Parts inventory lives on the team but older saves can carry ID strings.
        inventory = getattr(team, "parts_inventory", None)
        if isinstance(inventory, (list, tuple, set)):
            inventory_items = list(inventory)
        elif isinstance(inventory, dict):
            inventory_items = list(inventory.values())
        else:
            inventory_items = []
        d["car"]["parts_inventory"] = _serialize_part_refs(inventory_items)
    # Infrastructure (filter out boolean unlock flags — only show numeric facility levels)
    infra = getattr(team, "infrastructure", None)
    if infra:
        if isinstance(infra, dict):
            d["infrastructure"] = {
                k: float(v) for k, v in infra.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool) and not k.endswith("_unlocked")
            }
        elif hasattr(infra, "__dict__"):
            d["infrastructure"] = {
                k: float(v) for k, v in vars(infra).items()
                if isinstance(v, (int, float)) and not isinstance(v, bool) and not k.endswith("_unlocked")
            }
    # Standing metrics (morale, reputation, legitimacy, etc.)
    sm = getattr(team, "standing_metrics", None)
    if isinstance(sm, dict):
        d["standing_metrics"] = {
            str(k): round(float(v), 1)
            for k, v in sm.items()
            if isinstance(v, (int, float))
        }
    # R&D projects
    rd = getattr(team, "rd_projects", None) or getattr(team, "active_rd_projects", None) or []
    for proj in rd:
        dur = getattr(proj, "duration_ticks", 1) or 1
        prog = getattr(proj, "progress_ticks", 0) or 0
        d["rd_projects"].append({
            "id": getattr(proj, "project_id", ""),
            "name": getattr(proj, "project_name", "") or getattr(proj, "subsystem", "Project"),
            "description": getattr(proj, "description", ""),
            "project_type": getattr(proj, "project_type", "car_upgrade"),
            "subsystem": getattr(proj, "target_stat", "") or getattr(proj, "subsystem", ""),
            "progress": round(prog / dur, 3) if dur > 0 else 0,
            "progress_ticks": prog,
            "duration_ticks": dur,
            "risk_level": getattr(proj, "risk_level", "medium"),
            "success_rate": round(getattr(proj, "current_success_rate", 0.7), 2),
            "budget": getattr(proj, "total_cost", 0) or getattr(proj, "budget", 0),
            "completed": getattr(proj, "completed", False),
            "cancelled": getattr(proj, "cancelled", False),
            "target_stat": getattr(proj, "target_stat", ""),
            "target_improvement": getattr(proj, "target_improvement", 0),
        })
    return d


def serialize_game_state(controller) -> Dict[str, Any]:
    """Full game state snapshot for the REST API. Lock is acquired by _serialize_with_lock()."""
    state = controller.state
    if state is None:
        return {"status": "no_game", "tick": 0}

    out: Dict[str, Any] = {
        "status": "running",
        "tick": state.tick,
        "date_str": state.current_date_str() if hasattr(state, "current_date_str") else "",
        "phase": state.phase,
        "sim_year": state.sim_year,
        "sim_day_of_year": state.sim_day_of_year,
        "season_number": state.season_number,
        "time_mode": state.time_mode,
        "control_mode": state.control_mode,
        "save_mode": state.save_mode,
        "seed": state.seed,
        "game_id": state.game_id,
        "player_identity": state.player_identity,
        "player_focus": state.player_focus,
        "player_age": state.player_age,
        "manager_first_name": getattr(state, "manager_first_name", ""),
        "manager_last_name": getattr(state, "manager_last_name", ""),
        "in_offseason": state.in_offseason,
        "race_day_active": state.race_day_active,
        "races_completed_this_season": state.races_completed_this_season,
        "state_db_path": getattr(state, "state_db_path", None) or getattr(controller, "state_db_path", None),
    }

    # Player team
    if state.player_team:
        out["player_team"] = serialize_team(state.player_team, state)
    else:
        out["player_team"] = None

    # AI teams (summary)
    out["ai_teams"] = []
    for t in (state.ai_teams or []):
        out["ai_teams"].append(serialize_team(t, state))

    # Leagues
    out["leagues"] = {}
    for lname, league in (state.leagues or {}).items():
        out["leagues"][lname] = {
            "name": getattr(league, "name", lname),
            "tier": getattr(league, "tier", ""),
            "tier_name": getattr(league, "tier_name", ""),
            "team_names": getattr(league, "team_names", []),
            "races_this_season": getattr(league, "races_this_season", 0),
        }
        # Championship table
        ct = getattr(league, "championship_table", None)
        if ct:
            if isinstance(ct, dict):
                out["leagues"][lname]["championship_table"] = {
                    k: v for k, v in ct.items()
                }
            elif isinstance(ct, list):
                out["leagues"][lname]["championship_table"] = ct

        # Driver championship
        dc = getattr(league, "driver_championship", None)
        if dc:
            if isinstance(dc, dict):
                out["leagues"][lname]["driver_championship"] = {
                    k: v for k, v in dc.items()
                }
            elif isinstance(dc, list):
                out["leagues"][lname]["driver_championship"] = dc

        # Schedule
        sched = getattr(league, "schedule", None)
        if sched and isinstance(sched, list):
            out["leagues"][lname]["schedule"] = []
            races_done = int(getattr(league, "races_this_season", 0) or 0)
            tracks_map = getattr(state, "tracks", {}) or {}
            for idx, race in enumerate(sched):
                completed_default = idx < races_done
                if isinstance(race, dict):
                    tick_val = race.get("tick", race.get("race_tick", 0))
                    track_id = str(race.get("track_id", ""))
                    track_name = str(race.get("track_name", ""))
                    if not track_name and track_id and track_id in tracks_map:
                        track_name = str(getattr(tracks_map[track_id], "name", track_id))
                    out["leagues"][lname]["schedule"].append({
                        "track_name": track_name,
                        "track_id": track_id,
                        "tick": int(tick_val or 0),
                        "completed": bool(race.get("completed", completed_default)),
                    })
                elif isinstance(race, (tuple, list)):
                    tick_val = int(race[0]) if len(race) > 0 and race[0] is not None else 0
                    track_id = str(race[1]) if len(race) > 1 and race[1] is not None else ""
                    track_name = ""
                    if track_id and track_id in tracks_map:
                        track_name = str(getattr(tracks_map[track_id], "name", track_id))
                    out["leagues"][lname]["schedule"].append({
                        "track_name": track_name,
                        "track_id": track_id,
                        "tick": tick_val,
                        "completed": completed_default,
                    })
                elif isinstance(race, (int, float)):
                    out["leagues"][lname]["schedule"].append({
                        "track_name": "",
                        "track_id": "",
                        "tick": int(race),
                        "completed": completed_default,
                    })
                elif hasattr(race, "__dict__"):
                    out["leagues"][lname]["schedule"].append({
                        "track_name": getattr(race, "track_name", ""),
                        "track_id": getattr(race, "track_id", ""),
                        "tick": getattr(race, "tick", 0),
                        "completed": getattr(race, "completed", completed_default),
                    })

    # Free agents (summary for job market)
    out["free_agents"] = []
    for fa in (state.free_agents or [])[:100]:
        entity = getattr(fa, "entity", fa)
        d = serialize_entity(entity, state)
        # Use entity_id for stable identification (id(fa) is a Python memory
        # address that can lose precision in JSON / JavaScript).
        d["id"] = getattr(entity, "entity_id", None) or id(fa)
        d["asking_salary"] = getattr(fa, "asking_salary", 0)
        out["free_agents"].append(d)

    # Job board
    jb = getattr(state, "job_board", None)
    if jb:
        listings = getattr(jb, "listings", None) or getattr(jb, "vacancies", [])
        out["job_board"] = []
        teams_by_name = {
            getattr(t, "name", ""): t
            for t in (([state.player_team] if state.player_team else []) + (state.ai_teams or []))
            if t
        }

        def _job_field(row: Any, key: str, default: Any = None) -> Any:
            if isinstance(row, dict):
                return row.get(key, default)
            return getattr(row, key, default)

        def _job_role_pool(team_obj: Any, role_text: str) -> List[Any]:
            if not team_obj:
                return []
            role_key = str(role_text or "").strip().lower().replace(" ", "_")
            if role_key in ("driver", "drivers"):
                return [d for d in (getattr(team_obj, "drivers", None) or []) if d]
            if role_key in ("engineer", "engineers"):
                return [e for e in (getattr(team_obj, "engineers", None) or []) if e]
            if role_key in ("mechanic", "mechanics"):
                return [m for m in (getattr(team_obj, "mechanics", None) or []) if m]
            if role_key in ("strategist",):
                s = getattr(team_obj, "strategist", None)
                return [s] if s else []
            if role_key in ("team_principal", "team principal", "principal", "ai_principal", "aiprincipal"):
                p = getattr(team_obj, "principal", None)
                return [p] if p else []
            return []

        for idx, listing in enumerate(listings or []):
            team_name = str(_job_field(listing, "team_name", "") or "")
            role = str(_job_field(listing, "role", "") or "")
            team_obj = teams_by_name.get(team_name)
            role_pool = _job_role_pool(team_obj, role)

            overall_values = [
                float(getattr(entity, "overall_rating", 0.0))
                for entity in role_pool
                if isinstance(getattr(entity, "overall_rating", None), (int, float))
            ]
            age_values = [
                float(getattr(entity, "age", 0.0))
                for entity in role_pool
                if isinstance(getattr(entity, "age", None), (int, float))
            ]

            listing_overall = round(sum(overall_values) / len(overall_values), 1) if overall_values else 0.0
            listing_age = round(sum(age_values) / len(age_values), 1) if age_values else 0.0

            salary = _job_field(listing, "salary", None)
            if salary is None:
                salary_range = _job_field(listing, "salary_range", [0, 0])
                if isinstance(salary_range, (list, tuple)) and len(salary_range) >= 2:
                    salary = (float(salary_range[0] or 0) + float(salary_range[1] or 0)) / 2.0
                elif isinstance(salary_range, (int, float)):
                    salary = float(salary_range)
                else:
                    salary = 0.0

            out["job_board"].append({
                "id": idx,
                "team_name": team_name,
                "role": role,
                "salary": int(float(salary or 0)),
                "overall": listing_overall,
                "age": listing_age,
                "created_tick": int(_job_field(listing, "created_tick", 0) or 0),
                "tier": str(_job_field(listing, "tier", "") or ""),
                "expectation_band": str(_job_field(listing, "expectation_band", "") or ""),
            })

    # Recent events
    out["recent_events"] = []
    for evt in (state.event_history or [])[-30:]:
        evt_data = getattr(evt, "data", {}) or {}
        out["recent_events"].append({
            "type": getattr(evt, "event_type", ""),
            "description": getattr(evt, "description", str(evt)),
            "tick": getattr(evt, "tick", getattr(evt, "ts", 0)),
            "category": getattr(evt, "category", ""),
            "severity": getattr(evt, "severity", "info"),
            "priority": getattr(evt, "priority", 0),
            "event_id": getattr(evt, "event_id", 0),
            "data": _json_safe(evt_data),
        })

    # Stable dashboard feeds (not limited to recent_events window).
    out["player_driver_recent_results"] = _build_player_driver_recent_results(state, per_driver=6)
    out["promotion_opportunities"] = _serialize_promotion_opportunities(state)

    # Pending decisions
    out["pending_decisions"] = []
    for idx, dec in enumerate(state.pending_decisions or []):
        out["pending_decisions"].append({
            "id": getattr(dec, "decision_id", None) or idx,
            "prompt": getattr(dec, "prompt", ""),
            "options": [
                {
                    "label": getattr(opt, "label", ""),
                    "cost": getattr(opt, "cost", 0),
                    "description": getattr(opt, "description", ""),
                }
                for opt in (getattr(dec, "options", []) or [])
            ],
            "deadline_tick": getattr(dec, "deadline_tick", None),
        })

    # Sponsorships
    out["sponsorships"] = {}
    for team_name, slist in (state.sponsorships or {}).items():
        out["sponsorships"][team_name] = []
        for sp in (slist or []):
            out["sponsorships"][team_name].append({
                "name": getattr(sp, "sponsor_name", getattr(sp, "name", "")),
                "value": getattr(sp, "base_payment_per_season", getattr(sp, "annual_value", 0)),
                "seasons_remaining": getattr(sp, "duration_seasons", getattr(sp, "seasons_remaining", 0)) - getattr(sp, "seasons_active", 0),
                "confidence": round(getattr(sp, "confidence", 100.0), 1),
            })

    # Penalties
    out["penalties"] = []
    for p in (state.penalties or [])[-20:]:
        out["penalties"].append({
            "type": getattr(p, "penalty_type", ""),
            "amount": getattr(p, "amount", 0),
            "reason": getattr(p, "reason", ""),
            "tick": getattr(p, "tick", 0),
        })

    # Parts marketplace – show only parts compatible with the player's tier.
    # Group by part_type, take top N per type sorted by performance, then flatten.
    _parts_by_type: Dict[str, list] = defaultdict(list)
    for pid, part in state.parts_catalog.items():
        pt = getattr(part, "part_type", "unknown")
        _parts_by_type[pt].append(part)
    out["parts_marketplace"] = []
    player_tier = getattr(getattr(state, "player_team", None), "tier", None)
    _per_type_limit = max(8, 60 // max(len(_parts_by_type), 1))
    for ptype in sorted(_parts_by_type.keys()):
        bucket = _parts_by_type[ptype]
        if player_tier is not None:
            bucket = [p for p in bucket if _part_is_tier_compatible(p, player_tier)]
        if not bucket:
            continue
        # Sort by performance_score descending so best parts show first
        bucket.sort(key=lambda p: getattr(p, "performance_score", 0), reverse=True)
        for part in bucket[:_per_type_limit]:
            out["parts_marketplace"].append(serialize_part(part))

    # Manager career stats
    mcs = getattr(state, "manager_career_stats", None)
    if mcs:
        out["manager_career"] = {}
        for attr in ("wins", "podiums", "championships", "total_races",
                      "best_finish", "teams_managed", "seasons_completed",
                      "total_earnings", "employment_history"):
            val = getattr(mcs, attr, None)
            if val is not None:
                if isinstance(val, list):
                    out["manager_career"][attr] = [
                        v if isinstance(v, (str, int, float, bool)) else str(v)
                        for v in val
                    ]
                else:
                    out["manager_career"][attr] = val

    # Delegation
    out["delegation_settings"] = getattr(state, "delegation_settings", {})
    df = getattr(state, "delegation_focus", None)
    if df:
        out["delegation_focus"] = {
            "text": getattr(df, "text", ""),
            "stat_modifiers": getattr(df, "stat_modifiers", {}),
        }
    else:
        out["delegation_focus"] = None

    # Current meta / economic state
    out["current_meta"] = getattr(state, "current_meta", {})
    out["economic_state"] = getattr(state, "economic_state", {})

    # Contracts summary (for team/finance views)
    out["contracts"] = {}
    for eid, contract in (getattr(state, "contracts", {}) or {}).items():
        sr = getattr(contract, "seasons_remaining", 0)
        if callable(sr):
            try:
                sr = round(sr(state.tick), 1)
            except Exception:
                sr = 0
        out["contracts"][str(eid)] = {
            "entity_name": getattr(contract, "entity_name", ""),
            "team_name": getattr(contract, "team_name", ""),
            "role": getattr(contract, "role", ""),
            "base_salary": getattr(contract, "base_salary", 0),
            "seasons_remaining": sr,
            "buyout": getattr(contract, "buyout_clause_fixed", None) or 0,
        }

    # ─── Calendar Projection ─────────────────────────────────────
    try:
        projection = state.get_calendar_projection(days_ahead=90)
        # Group by simulated day-of-year for the Calendar UI
        # The Calendar tab expects { days: [ { day, events: [ { name, category, detail } ] } ], current_day, month_label, year }
        day_events: Dict[int, list] = defaultdict(list)
        for entry in projection:
            eday = entry.get("entry_day", 0)
            day_events[eday].append({
                "name": entry.get("title", ""),
                "category": entry.get("category", "other"),
                "detail": entry.get("description", ""),
                "priority": entry.get("priority", 50),
                "entry_type": entry.get("entry_type", ""),
            })
        days_list = []
        for day_num in sorted(day_events.keys()):
            days_list.append({"day": day_num, "events": day_events[day_num]})
        # Build month label from current date string
        date_str = state.current_date_str() if hasattr(state, "current_date_str") else ""
        month_label = ""
        year_label = ""
        if date_str:
            parts = date_str.split()
            if len(parts) >= 3:
                month_label = parts[1]  # e.g. "15 March Year3" → "March"
                year_label = parts[2]
            elif len(parts) == 2:
                month_label = parts[0]
                year_label = parts[1]
        out["calendar"] = {
            "days": days_list,
            "current_day": state.sim_day_of_year,
            "month_label": month_label,
            "year": year_label,
        }
    except Exception as e:
        out["calendar"] = {"days": [], "current_day": 0, "month_label": "", "year": ""}

    # ─── Income Streams (for Finance tab) ─────────────────────────
    if state.player_team:
        pt_budget = getattr(state.player_team, "budget", None)
        if pt_budget:
            streams = getattr(pt_budget, "income_streams", None) or []
            out["income_streams"] = []
            for inc in streams:
                out["income_streams"].append({
                    "name": getattr(inc, "name", ""),
                    "amount": getattr(inc, "amount", 0),
                    "frequency": getattr(inc, "frequency", ""),
                })

    # ─── Race Day State ────────────────────────────────────────────
    rds = getattr(state, "race_day_state", None)
    if rds:
        phase_val = rds.phase.value if hasattr(rds.phase, "value") else str(rds.phase)
        out["race_day"] = {
            "phase": phase_val,
            "race_tick": getattr(rds, "race_tick", None),
            "league_id": getattr(rds, "league_id", None),
            "track_id": getattr(rds, "track_id", None),
            "player_wants_live_race": getattr(rds, "player_wants_live_race", False),
            "live_race_active": getattr(rds, "live_race_active", False),
            "current_lap": getattr(rds, "current_lap", 0),
            "total_laps": getattr(rds, "total_laps", 0),
            "broadcast_active": getattr(rds, "broadcast_active", False),
        }

        # Qualifying grid
        quali_grid = getattr(rds, "quali_grid", [])
        out["race_day"]["quali_grid"] = []
        for entry in (quali_grid or []):
            if isinstance(entry, (tuple, list)) and len(entry) >= 2:
                team_obj, driver_obj = entry[0], entry[1]
                score = entry[2] if len(entry) > 2 else 0
                out["race_day"]["quali_grid"].append({
                    "team": getattr(team_obj, "name", str(team_obj)),
                    "driver": getattr(driver_obj, "name", str(driver_obj)),
                    "score": round(float(score), 3) if score else 0,
                    "is_player": getattr(team_obj, "name", "") == (state.player_team.name if state.player_team else ""),
                })

        # Live standings
        live_standings = getattr(rds, "live_standings", [])
        out["race_day"]["standings"] = []
        for s in (live_standings or []):
            if isinstance(s, dict):
                out["race_day"]["standings"].append(s)
            else:
                out["race_day"]["standings"].append({
                    "driver": getattr(s, "driver_name", getattr(s, "name", str(s))),
                    "team": getattr(s, "team_name", ""),
                    "gap": getattr(s, "gap", 0),
                    "is_player": getattr(s, "is_player", False),
                })

        # Live events
        live_events = getattr(rds, "live_events", [])
        out["race_day"]["events"] = []
        for evt in (live_events or [])[-100:]:
            if isinstance(evt, dict):
                out["race_day"]["events"].append(evt)
            else:
                out["race_day"]["events"].append({
                    "text": str(evt),
                    "lap": getattr(evt, "lap", 0),
                })

        # Race result summary
        race_result = getattr(rds, "race_result", None)
        if race_result:
            out["race_day"]["result"] = {
                "winner_driver": getattr(race_result, "winner_driver", ""),
                "winner_team": getattr(race_result, "winner_team", ""),
                "final_standings": getattr(race_result, "final_standings", []),
                "player_finish": getattr(race_result, "player_finish", None),
            }
    else:
        out["race_day"] = {"phase": "idle"}

    # ─── Pending Sponsor Offers (richer data) ─────────────────────
    out["pending_sponsor_offers"] = {}
    for team_name, offers in (state.pending_sponsor_offers or {}).items():
        out["pending_sponsor_offers"][team_name] = []
        for idx, sp in enumerate(offers or []):
            out["pending_sponsor_offers"][team_name].append({
                "index": idx,
                "name": getattr(sp, "sponsor_name", getattr(sp, "name", "")),
                "value": getattr(sp, "base_payment_per_season", getattr(sp, "annual_value", 0)),
                "seasons_remaining": getattr(sp, "duration_seasons", getattr(sp, "seasons_remaining", 0)),
                "confidence": round(getattr(sp, "confidence", 100.0), 1),
                "sponsor_id": getattr(sp, "sponsor_id", ""),
            })

    # ─── Play-by-Play data (built from race_day_state) ────────────
    pbp_history = _build_play_by_play_history(state, limit=24)
    pbp_telemetry = _build_play_by_play_telemetry(
        state=state,
        rds=rds,
        standings=out.get("race_day", {}).get("standings", []),
        live_events=out.get("race_day", {}).get("events", []),
    )
    out["play_by_play"] = {
        "is_live": rds is not None and getattr(rds, "live_race_active", False),
        "lap_info": {
            "current": getattr(rds, "current_lap", 0) if rds else 0,
            "total": getattr(rds, "total_laps", 0) if rds else 0,
        },
        "standings": out.get("race_day", {}).get("standings", []),
        "live_events": out.get("race_day", {}).get("events", []),
        "telemetry": pbp_telemetry,
        "history": pbp_history,
    }

    # ─── History tab payload ───────────────────────────────────────
    out["history"] = _build_history_payload(state, race_history=pbp_history, limit_each=80)

    # ─── Tracks for marketplace reference ─────────────────────────
    out["tracks"] = {}
    for tid, track in (getattr(state, "tracks", {}) or {}).items():
        out["tracks"][tid] = {
            "name": getattr(track, "name", tid),
            "length_km": getattr(track, "length_km", 0),
            "laps": getattr(track, "laps", 0),
        }

    return out


# ═══════════════════════════════════════════════════════════════════
# FastAPI Application
# ═══════════════════════════════════════════════════════════════════

def _serialize_with_lock(controller) -> Dict[str, Any]:
    """Serialize game state. Uses a short lock timeout so we never block the
    web server indefinitely.  If the lock is contended we just return a
    lightweight 'busy' response instead of hanging."""
    try:
        acquired = controller.state_lock.acquire(timeout=0.5)
        if not acquired:
            # Lock is held by the game engine — return a non-fatal busy marker
            # so the frontend keeps its existing state and retries on next poll.
            return {"status": "busy", "tick": getattr(controller.state, "tick", 0) if controller.state else 0}
        try:
            data = serialize_game_state(controller)
            # Validate JSON-serializable before returning to FastAPI
            # (catches stale Team/Driver objects leaking through)
            json.dumps(data, default=str)
            return data
        finally:
            controller.state_lock.release()
    except Exception as e:
        return {"status": "no_game", "error": str(e)}

def _build_full_state_payload(state_data: Dict[str, Any]) -> Dict[str, Any]:
    """Expand /api/state payload with stable top-level aliases for global refresh."""
    if not isinstance(state_data, dict):
        return {"status": "no_game"}
    if state_data.get("status") != "running":
        return state_data

    full = dict(state_data)
    full["current_date"] = state_data.get("date_str", "")
    full["race_state"] = state_data.get("race_day", {"phase": "idle"})
    full["team_state"] = state_data.get("player_team")

    leagues = state_data.get("leagues", {})
    standings: Dict[str, Any] = {}
    if isinstance(leagues, dict):
        for lname, league in leagues.items():
            if not isinstance(league, dict):
                continue
            standings[lname] = {
                "championship_table": league.get("championship_table", {}),
                "driver_championship": league.get("driver_championship", {}),
                "races_this_season": league.get("races_this_season", 0),
            }
    full["standings"] = standings

    player_team = state_data.get("player_team", {})
    budget = player_team.get("budget", {}) if isinstance(player_team, dict) else {}
    full["finances"] = {
        "cash": budget.get("cash", 0),
        "weekly_expenses": budget.get("weekly_expenses", 0),
        "weekly_income": budget.get("weekly_income", 0),
        "income_streams": state_data.get("income_streams", []),
    }
    full["staff"] = {
        "roster": player_team.get("roster", {}) if isinstance(player_team, dict) else {},
        "contracts": state_data.get("contracts", {}),
        "job_board": state_data.get("job_board", []),
    }
    full.setdefault("active_decisions", [])
    return full

def create_app(shared_runtime: Dict[str, Any], bridge: WebBridge):
    """Build the FastAPI app with all routes."""
    _ensure_imports()
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import JSONResponse, HTMLResponse
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="FTB Web Server", version="1.0.0")

    # Allow cross-origin for dev (Vite dev server on different port)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    log_fn = shared_runtime.get("log", lambda *a, **k: None)

    # ─── Bridge → broadcaster pump (runs as background task) ───
    async def bridge_pump():
        """Drain bridge._broadcast_queue and fan out to all connected WS clients."""
        bq = bridge._broadcast_queue
        if not bq:
            return
        while True:
            try:
                msg = await bq.get()
                # Fan out to all connected clients
                dead = set()
                for ws in list(bridge.connected_clients):
                    try:
                        await ws.send_text(msg)
                    except Exception:
                        dead.add(ws)
                bridge.connected_clients -= dead
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.1)

    @app.on_event("startup")
    async def on_startup():
        loop = asyncio.get_event_loop()
        bq = asyncio.Queue(maxsize=1000)
        bridge.set_async_context(loop, bq)
        app.state.pump_task = asyncio.create_task(bridge_pump())
        log_fn("web", "Bridge pump started (async context initialized)")

    @app.on_event("shutdown")
    async def on_shutdown():
        task = getattr(app.state, "pump_task", None)
        if task:
            task.cancel()

    # ──── REST: Health ────
    @app.get("/api/health")
    async def health():
        return {"status": "ok", "ts": time.time()}

    # ──── REST: Full game state ────
    @app.get("/api/state")
    async def get_state():
        controller = shared_runtime.get("ftb_controller")
        if not controller:
            return JSONResponse({"status": "no_controller"}, 503)
        try:
            # Run lock acquisition in a thread so we don't block the async event loop
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: _serialize_with_lock(controller))
            return data
        except Exception as e:
            log_fn("web", f"serialize_game_state error: {e}")
            # Return no_game rather than a bare error so the frontend keeps polling
            return JSONResponse({"status": "no_game", "error": str(e)}, 200)

    @app.get("/api/full_state")
    async def get_full_state():
        controller = shared_runtime.get("ftb_controller")
        if not controller:
            return JSONResponse({"status": "no_controller"}, 503)
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: _serialize_with_lock(controller))
            return _build_full_state_payload(data)
        except Exception as e:
            log_fn("web", f"full_state error: {e}")
            return JSONResponse({"status": "no_game", "error": str(e)}, 200)

    # ──── REST: Current subtitle ────
    @app.get("/api/subtitle")
    async def get_subtitle():
        return {"text": bridge.last_subtitle}

    # ──── REST: Snapshot (subtitle + recent events) ────
    @app.get("/api/snapshot")
    async def get_snapshot():
        return bridge.get_snapshot()

    # ──── REST: UI Screen State (for Audio CLI introspection) ────
    @app.get("/api/ui_screen")
    async def get_ui_screen():
        """Return the current UI screen (landing, wizard, loading, game)
        and wizard step if applicable. Used by Audio CLI to know what
        buttons are available for dynamic clicking."""
        screen_info = bridge.get_ui_screen()
        # Also include whether a game exists
        controller = shared_runtime.get("ftb_controller")
        has_game = controller is not None and controller.state is not None
        screen_info["has_game"] = has_game
        # If game exists, override screen to "game"
        if has_game and screen_info["screen"] not in ("wizard",):
            screen_info["screen"] = "game"
        # Describe available buttons for the current screen
        screen = screen_info["screen"]
        if screen == "landing":
            screen_info["buttons"] = [
                {"id": "new_game", "label": "🆕 New Game", "action": "navigate_wizard"},
                {"id": "load_game", "label": "📂 Load Game", "action": "show_load_screen"},
            ]
        elif screen == "wizard":
            step = screen_info["wizard_step"]
            buttons = []
            if step > 1:
                buttons.append({"id": "wizard_back", "label": "← Back", "action": "wizard_prev"})
            if step < 4:
                buttons.append({"id": "wizard_next", "label": "Next →", "action": "wizard_next"})
            else:
                buttons.append({"id": "wizard_start", "label": "🏁 START NEW GAME", "action": "confirm_new_game"})
            screen_info["buttons"] = buttons
            # Describe what the current step configures
            step_descriptions = {
                1: "Save Mode & World Seed",
                2: "Starting Tier",
                3: "Origin Story & Manager Identity",
                4: "Team Setup & Confirmation",
            }
            screen_info["step_description"] = step_descriptions.get(step, "")
            screen_info["total_steps"] = 4
            # Include selectable options for the current step
            wf = screen_info.get("wizard_fields", {})
            if step == 1:
                screen_info["fields"] = [
                    {"field": "save_mode", "label": "Save Mode", "type": "choice",
                     "current": wf.get("save_mode", "replayable"),
                     "options": [
                         {"value": "replayable", "label": "Replayable",
                          "desc": "Deterministic seed, same world every time"},
                         {"value": "permanent", "label": "Permanent",
                          "desc": "Extra entropy, unique every playthrough"},
                     ]},
                    {"field": "seed", "label": "World Seed", "type": "text",
                     "current": wf.get("seed", "")},
                ]
            elif step == 2:
                screen_info["fields"] = [
                    {"field": "tier", "label": "Starting Tier", "type": "choice",
                     "current": wf.get("tier", "grassroots"),
                     "options": [
                         {"value": "grassroots", "label": "Grassroots",
                          "desc": "The very bottom. Tiny budgets, volunteer crews."},
                         {"value": "formula_v", "label": "Formula V",
                          "desc": "Regional racing. Proper teams, modest budgets."},
                         {"value": "formula_x", "label": "Formula X",
                          "desc": "National level. Professional teams, growing budgets."},
                         {"value": "formula_y", "label": "Formula Y",
                          "desc": "International. Large budgets, factory support."},
                         {"value": "formula_z", "label": "Formula Z",
                          "desc": "The pinnacle. Massive budgets, global stage."},
                     ]},
                ]
            elif step == 3:
                screen_info["fields"] = [
                    {"field": "origin", "label": "Origin Story", "type": "choice",
                     "current": wf.get("origin", "grassroots_hustler"),
                     "options": [
                         {"value": "game_show_winner", "label": "Game Show Winner",
                          "desc": "Won a reality TV competition. Cash-rich, reputation-poor."},
                         {"value": "grassroots_hustler", "label": "Grassroots Hustler",
                          "desc": "Built up from nothing. Street-smart, budget-savvy."},
                         {"value": "former_driver", "label": "Former Driver",
                          "desc": "Retired racer. Deep race knowledge, media connections."},
                         {"value": "corporate_spinout", "label": "Corporate Spinout",
                          "desc": "Left a big team. Well-funded, corporate contacts."},
                         {"value": "engineering_savant", "label": "Engineering Savant",
                          "desc": "Technical genius. R&D bonus, people skills lacking."},
                     ]},
                    {"field": "manager_first", "label": "First Name", "type": "text",
                     "current": wf.get("manager_first", "")},
                    {"field": "manager_last", "label": "Last Name", "type": "text",
                     "current": wf.get("manager_last", "")},
                    {"field": "manager_age", "label": "Age", "type": "number",
                     "current": wf.get("manager_age", 32), "min": 22, "max": 70},
                    {"field": "player_identity", "label": "Player Tags", "type": "text",
                     "current": wf.get("player_identity", "")},
                ]
            elif step == 4:
                screen_info["fields"] = [
                    {"field": "team_name", "label": "Team Name", "type": "text",
                     "current": wf.get("team_name", "")},
                    {"field": "ownership", "label": "Ownership", "type": "choice",
                     "current": wf.get("ownership", "self_owned"),
                     "options": [
                         {"value": "self_owned", "label": "Self-Owned",
                          "desc": "You own the team"},
                         {"value": "hired_manager", "label": "Hired Manager",
                          "desc": "Working for someone else"},
                     ]},
                ]
        elif screen == "game":
            screen_info["active_tab"] = bridge.active_tab
            screen_info["tabs"] = [
                {"id": "dashboard", "label": "🏠 Home"},
                {"id": "team", "label": "👥 Team"},
                {"id": "car", "label": "🏎️ Car"},
                {"id": "development", "label": "🔧 Dev"},
                {"id": "raceops", "label": "🏁 Race"},
                {"id": "pbp", "label": "📡 PBP"},
                {"id": "finance", "label": "💰 Finance"},
                {"id": "sponsors", "label": "🤝 Sponsors"},
                {"id": "stats", "label": "📊 Stats"},
                {"id": "analytics", "label": "📈 Analytics"},
                {"id": "career", "label": "🏆 Career"},
                {"id": "calendar", "label": "📅 Calendar"},
                {"id": "ai", "label": "🤖 AI"},
                {"id": "penalties", "label": "⚠️ Penalties"},
                {"id": "history", "label": "📜 History"},
                {"id": "help", "label": "❓ Help"},
                {"id": "data", "label": "🗄️ Data"},
            ]
            screen_info["buttons"] = [
                {"id": "tick_1", "label": "⏩ +1 Day", "action": "advance_day"},
                {"id": "tick_7", "label": "+7 Days", "action": "ftb_tick_batch", "n": 7},
                {"id": "tick_30", "label": "+30 Days", "action": "ftb_tick_batch", "n": 30},
                {"id": "save", "label": "💾 Save", "action": "save_game"},
                {"id": "load", "label": "📂 Load", "action": "show_load_screen"},
                {"id": "new", "label": "🆕 New Game", "action": "navigate_wizard"},
            ]
        elif screen == "loading":
            screen_info["buttons"] = [
                {"id": "cancel_loading", "label": "← Cancel", "action": "navigate_landing"},
            ]
        return screen_info

    # ──── REST: Navigate UI Screen ────
    @app.post("/api/navigate")
    async def navigate_screen(payload: Dict[str, Any]):
        """Navigate the web UI to a specific screen.
        Used by Audio CLI to dynamically click buttons instead of
        hard-coding each game action as its own function.

        Supported targets:
          - 'wizard': show the setup wizard (step 1)
          - 'landing': go back to the landing/start menu
          - 'wizard_next': advance wizard to next step
          - 'wizard_prev': go back one wizard step
          - 'load_screen': show the load game screen
        """
        target = payload.get("target", "").strip().lower()
        step = payload.get("step", None)

        if target in ("wizard", "new_game", "navigate_wizard"):
            bridge.navigate_to("wizard", 1)
            return {"status": "ok", "screen": "wizard", "wizard_step": 1}
        elif target in ("landing", "home", "start_menu", "navigate_landing"):
            bridge.navigate_to("landing")
            return {"status": "ok", "screen": "landing"}
        elif target in ("wizard_next", "next"):
            current_step = bridge.wizard_step
            new_step = min(current_step + 1, 4)
            bridge.set_wizard_step(new_step)
            return {"status": "ok", "screen": "wizard", "wizard_step": new_step}
        elif target in ("wizard_prev", "back", "wizard_back"):
            current_step = bridge.wizard_step
            new_step = max(current_step - 1, 1)
            bridge.set_wizard_step(new_step)
            return {"status": "ok", "screen": "wizard", "wizard_step": new_step}
        elif target in ("load_screen", "load_game", "show_load_screen"):
            bridge.navigate_to("loading")
            return {"status": "ok", "screen": "loading"}

        # ── Tab switching (in-game navigation) ──
        # Accept "tab:<id>" or just the tab name directly
        tab_target = target.replace("tab:", "").replace("tab_", "")
        # Also accept friendly names → tab IDs
        tab_aliases = {
            "home": "dashboard", "overview": "dashboard",
            "dev": "development", "r&d": "development", "rd": "development",
            "race": "raceops", "race_ops": "raceops", "racing": "raceops",
            "play_by_play": "pbp", "playbyplay": "pbp", "broadcast": "pbp",
            "money": "finance", "budget": "finance",
            "sponsor": "sponsors", "sponsorships": "sponsors",
            "promotion": "promotion", "promotions": "promotion",
            "statistics": "stats", "racing_stats": "stats",
            "manager": "career", "manager_career": "career",
            "schedule": "calendar", "dates": "calendar",
            "assistant": "ai", "ai_assistant": "ai", "chat": "ai",
            "penalty": "penalties", "infractions": "penalties",
            "logs": "history", "event_log": "history",
            "help": "help", "docs": "help", "manual": "help", "guide": "help",
            "explorer": "data", "ftb_data": "data", "database": "data",
        }
        resolved_tab = tab_aliases.get(tab_target, tab_target)
        if bridge.switch_tab(resolved_tab):
            return {"status": "ok", "screen": "game", "active_tab": resolved_tab}

        return JSONResponse({"error": f"Unknown navigate target: {target}"}, 400)

    # ──── REST: Set Wizard Field ────
    WIZARD_FIELD_OPTIONS = {
        "save_mode": ["replayable", "permanent"],
        "tier": ["grassroots", "formula_v", "formula_x", "formula_y", "formula_z"],
        "origin": ["game_show_winner", "grassroots_hustler", "former_driver",
                    "corporate_spinout", "engineering_savant"],
        "ownership": ["self_owned", "hired_manager"],
    }

    @app.post("/api/wizard_field")
    async def set_wizard_field(payload: Dict[str, Any]):
        """Set a wizard field value (tier, origin, save_mode, ownership, seed, etc.).
        Used by Audio CLI to select options during the setup wizard.

        Supported fields:
          - save_mode: 'replayable' or 'permanent'
          - seed: any integer or string
          - tier: 'grassroots', 'formula_v', 'formula_x', 'formula_y', 'formula_z'
          - origin: 'game_show_winner', 'grassroots_hustler', 'former_driver',
                    'corporate_spinout', 'engineering_savant'
          - ownership: 'self_owned' or 'hired_manager'
          - team_name: any string
          - manager_first: any string
          - manager_last: any string
          - manager_age: integer 22-70
          - player_identity: comma-separated string of tags
        """
        field = payload.get("field", "").strip()
        value = payload.get("value")

        if not field:
            return JSONResponse({"error": "No field specified"}, 400)

        # Validate constrained fields
        if field in WIZARD_FIELD_OPTIONS:
            allowed = WIZARD_FIELD_OPTIONS[field]
            if value not in allowed:
                return JSONResponse({
                    "error": f"Invalid value '{value}' for {field}. "
                             f"Allowed: {', '.join(allowed)}"
                }, 400)

        bridge.set_wizard_field(field, value)
        return {"status": "ok", "field": field, "value": value}

    # ──── REST: Generic input field (audio keyboard backend) ────
    @app.post("/api/input_field")
    async def input_field(payload: Dict[str, Any]):
        """Generic field input endpoint — receives any field name and text value
        from the audio keyboard (or any other text-entry mechanism).

        Currently routes through the wizard field pipeline, which broadcasts
        the value to connected WebSocket clients so the Svelte UI updates.
        Extensible: as new input contexts are added (e.g. in-game rename,
        search, chat), this endpoint can route to the appropriate handler.
        """
        field = payload.get("field", "").strip()
        value = payload.get("value")

        if not field:
            return JSONResponse({"error": "No field specified"}, 400)
        if value is None:
            return JSONResponse({"error": "No value specified"}, 400)

        # Validate constrained fields (same rules as wizard_field)
        if field in WIZARD_FIELD_OPTIONS:
            allowed = WIZARD_FIELD_OPTIONS[field]
            if value not in allowed:
                return JSONResponse({
                    "error": f"Invalid value '{value}' for {field}. "
                             f"Allowed: {', '.join(allowed)}"
                }, 400)

        # Route through the bridge — broadcasts via WebSocket to all clients
        bridge.set_wizard_field(field, value)
        return {"status": "ok", "field": field, "value": value}

    # ──── REST: Send command to FTB ────
    @app.post("/api/command")
    async def send_command(cmd: Dict[str, Any]):
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        try:
            ftb_cmd_q.put(cmd)
            return {"status": "queued", "cmd": cmd.get("cmd", "")}
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)

    # ──── REST: UI command (flush, config, etc.) ────
    @app.post("/api/ui_command")
    async def send_ui_command(cmd: Dict[str, Any]):
        ui_cmd_q = shared_runtime.get("ui_cmd_q")
        if not ui_cmd_q:
            return JSONResponse({"error": "ui_cmd_q not available"}, 503)
        try:
            action = cmd.get("action", "")
            payload = cmd.get("payload", {})
            ui_cmd_q.put((action, payload))
            return {"status": "queued", "action": action}
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)

    # ──── REST: Check for autosave ────
    @app.get("/api/check_autosave")
    async def check_autosave():
        """Check if an autosave file exists and return its path + metadata."""
        # Try multiple locations where autosave could live
        candidates = []
        # 1. Controller's own save path (most authoritative)
        controller = shared_runtime.get("ftb_controller")
        if controller:
            csp = getattr(controller, "current_save_path", None)
            if csp:
                candidates.append(csp)
            cap = getattr(controller, "_get_autosave_path", None)
            if cap:
                try:
                    candidates.append(cap())
                except Exception:
                    pass
        # 2. STATION_DIR / ftb_autosave.json
        station_dir = shared_runtime.get("STATION_DIR", "")
        if station_dir:
            candidates.append(os.path.join(station_dir, "ftb_autosave.json"))
        # 3. RADIO_OS_ROOT / ftb_autosave.json
        root = os.environ.get("RADIO_OS_ROOT", "")
        if root:
            candidates.append(os.path.join(root, "ftb_autosave.json"))
        # 4. Scan stations/ for any ftb_autosave.json
        root_dir = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        stations_dir = os.path.join(root_dir, "stations")
        if os.path.isdir(stations_dir):
            for sname in os.listdir(stations_dir):
                p = os.path.join(stations_dir, sname, "ftb_autosave.json")
                candidates.append(p)
        # 5. cwd fallback
        candidates.append(os.path.join(".", "ftb_autosave.json"))

        for path in candidates:
            path = os.path.normpath(path)
            if os.path.isfile(path):
                return {
                    "exists": True,
                    "path": path,
                    "size": os.path.getsize(path),
                    "mtime": os.path.getmtime(path),
                }
        return {"exists": False}

    # ──── REST: List save files ────
    @app.get("/api/saves")
    async def list_saves():
        saves_dir = os.path.join(
            shared_runtime.get("STATION_DIR", "."), "..", "..", "saves"
        )
        saves_dir = os.path.normpath(saves_dir)
        if not os.path.isdir(saves_dir):
            # Try workspace root
            root = os.environ.get("RADIO_OS_ROOT", "")
            saves_dir = os.path.join(root, "saves") if root else ""
        files = []
        if os.path.isdir(saves_dir):
            for f in os.listdir(saves_dir):
                if f.endswith(".json"):
                    fp = os.path.join(saves_dir, f)
                    files.append({
                        "name": f,
                        "path": fp,
                        "size": os.path.getsize(fp),
                        "mtime": os.path.getmtime(fp),
                    })
        return {"saves": sorted(files, key=lambda x: x["mtime"], reverse=True)}

    # ──── REST: Notification history ────
    @app.get("/api/notifications")
    async def get_notifications():
        try:
            from plugins import ftb_notifications
            if hasattr(ftb_notifications, "query_notifications"):
                notifs = ftb_notifications.query_notifications(limit=100)
                return {"notifications": notifs}
        except Exception:
            pass
        return {"notifications": []}

    # ──── REST: Race Day State (detailed) ────
    @app.get("/api/race_day")
    async def get_race_day():
        controller = shared_runtime.get("ftb_controller")
        if not controller or not controller.state:
            return JSONResponse({"phase": "idle"}, 200)
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: _serialize_with_lock(controller))
            return {"race_day": data.get("race_day", {"phase": "idle"}),
                    "play_by_play": data.get("play_by_play", {})}
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)

    # ──── REST: Race Day Actions ────
    @app.post("/api/race_day/respond")
    async def race_day_respond(payload: Dict[str, Any]):
        """Handle pre-race prompt (watch live vs instant sim)."""
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        watch_live = payload.get("watch_live", False)
        ftb_cmd_q.put({"cmd": "ftb_pre_race_response", "watch_live": watch_live})
        return {"status": "queued", "watch_live": watch_live}

    @app.post("/api/race_day/start_live")
    async def race_day_start_live(payload: Dict[str, Any]):
        """Start live race playback."""
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        speed = payload.get("speed", 10.0)
        ftb_cmd_q.put({"cmd": "ftb_start_live_race", "speed": speed})
        return {"status": "queued", "speed": speed}

    @app.post("/api/race_day/pause")
    async def race_day_pause(body: dict = {}):
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        paused = body.get("paused", True)
        ftb_cmd_q.put({"cmd": "ftb_pause_live_race", "paused": paused})
        return {"status": "queued"}

    @app.post("/api/race_day/complete")
    async def race_day_complete():
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        ftb_cmd_q.put({"cmd": "ftb_complete_race_day"})
        return {"status": "queued"}

    # ──── REST: Sponsor Actions ────
    @app.post("/api/sponsor/accept")
    async def accept_sponsor(payload: Dict[str, Any]):
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        idx = payload.get("offer_index", 0)
        ftb_cmd_q.put({"cmd": "ftb_action", "action": "accept_sponsor", "target": idx})
        return {"status": "queued", "offer_index": idx}

    @app.post("/api/sponsor/decline")
    async def decline_sponsor(payload: Dict[str, Any]):
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        idx = payload.get("offer_index", 0)
        ftb_cmd_q.put({"cmd": "ftb_action", "action": "reject_sponsor", "target": idx})
        return {"status": "queued", "offer_index": idx}

    # ──── REST: Promotion Actions ────
    @app.post("/api/promotion/apply")
    async def apply_promotion(payload: Dict[str, Any]):
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        opportunity_id = str(payload.get("opportunity_id", "") or "")
        ftb_cmd_q.put({"cmd": "ftb_apply_promotion", "opportunity_id": opportunity_id})
        return {"status": "queued", "opportunity_id": opportunity_id}

    @app.post("/api/promotion/decline")
    async def decline_promotion(payload: Dict[str, Any]):
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        opportunity_id = str(payload.get("opportunity_id", "") or "")
        ftb_cmd_q.put({"cmd": "ftb_decline_promotion", "opportunity_id": opportunity_id})
        return {"status": "queued", "opportunity_id": opportunity_id}

    # ──── REST: Parts Marketplace Actions ────
    @app.post("/api/parts/buy")
    async def buy_part(payload: Dict[str, Any]):
        controller = shared_runtime.get("ftb_controller")
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q or not controller or not controller.state:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)

        part_id = str(payload.get("part_id", "") or "").strip()
        if not part_id:
            return JSONResponse({"error": "part_id is required"}, 400)

        with controller.state_lock:
            state = controller.state
            team = state.player_team if state else None
            if not team:
                return JSONResponse({"error": "No player team loaded"}, 409)

            part = state.parts_catalog.get(part_id)
            if not part:
                return JSONResponse({"error": f"Part not found: {part_id}"}, 404)

            if not _part_is_tier_compatible(part, getattr(team, "tier", None)):
                return JSONResponse({"error": "Part is not compatible with your league tier"}, 400)

            # Use authoritative server-side pricing.
            cost = _part_cost(part)
            if team.budget.cash < cost:
                return JSONResponse({"error": "Insufficient funds"}, 400)

        ftb_cmd_q.put({"cmd": "ftb_purchase_part", "part_id": part_id, "cost": cost})
        return {"status": "queued", "part_id": part_id, "cost": cost}

    @app.post("/api/parts/sell")
    async def sell_part(payload: Dict[str, Any]):
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        ftb_cmd_q.put({"cmd": "ftb_sell_part", "part_id": payload.get("part_id", "")})
        return {"status": "queued"}

    @app.post("/api/parts/equip")
    async def equip_part(payload: Dict[str, Any]):
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        ftb_cmd_q.put({"cmd": "ftb_equip_part", "part_id": payload.get("part_id", "")})
        return {"status": "queued"}

    # ──── REST: R&D / Development Actions ────
    @app.get("/api/rd_catalog")
    async def get_rd_catalog():
        """Return the R&D project catalog so the frontend can display available projects."""
        try:
            from plugins.ftb_game import RD_PROJECT_CATALOG
            catalog = []
            for project_id, template in RD_PROJECT_CATALOG.items():
                catalog.append({
                    "id": project_id,
                    "name": template.get("name", project_id),
                    "type": template.get("type", "car_upgrade"),
                    "cost": template.get("cost", 0),
                    "duration_ticks": template.get("duration_ticks", 14),
                    "base_success_rate": round(template.get("base_success_rate", 0.7), 2),
                    "target_stat": template.get("target_stat", ""),
                    "target_improvement": template.get("target_improvement", 0),
                    "generates_part": template.get("generates_part", False),
                    "part_type": template.get("part_type", ""),
                    "description": template.get("description", ""),
                    "risk_level": template.get("risk_level", "medium"),
                    "min_tier": template.get("min_tier", 1),
                })
            return {"catalog": catalog}
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)

    @app.post("/api/rd/start")
    async def start_rd_project(payload: Dict[str, Any]):
        """Start a new R&D project."""
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        project_id = payload.get("project_id", "")
        if not project_id:
            return JSONResponse({"error": "project_id is required"}, 400)
        ftb_cmd_q.put({
            "cmd": "ftb_start_development",
            "config": {
                "subsystem": payload.get("subsystem", ""),
                "budget": payload.get("budget", 0),
                "risk_level": payload.get("risk_level", 0.5),
                "engineers": [],
                "priority": payload.get("priority", "normal"),
            },
            "project_id": project_id,
        })
        return {"status": "queued", "project_id": project_id}

    @app.post("/api/rd/cancel")
    async def cancel_rd_project(payload: Dict[str, Any]):
        """Cancel an active R&D project."""
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        project_id = payload.get("project_id", "")
        if not project_id:
            return JSONResponse({"error": "project_id is required"}, 400)
        ftb_cmd_q.put({"cmd": "ftb_cancel_rd_project", "project_id": project_id})
        return {"status": "queued", "project_id": project_id}

    @app.post("/api/infrastructure/upgrade")
    async def upgrade_infrastructure(payload: Dict[str, Any]):
        """Upgrade a facility."""
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        facility = payload.get("facility", "")
        amount = payload.get("amount", 10)
        if not facility:
            return JSONResponse({"error": "facility is required"}, 400)
        ftb_cmd_q.put({"cmd": "ftb_upgrade_infrastructure", "facility": facility, "amount": amount})
        return {"status": "queued", "facility": facility}

    @app.post("/api/infrastructure/sell")
    async def sell_infrastructure(payload: Dict[str, Any]):
        """Sell a facility."""
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        facility = payload.get("facility", "")
        if not facility:
            return JSONResponse({"error": "facility is required"}, 400)
        ftb_cmd_q.put({"cmd": "ftb_sell_infrastructure", "facility": facility})
        return {"status": "queued", "facility": facility}

    # ──── REST: Staff / Job Board Actions ────
    @app.post("/api/staff/hire")
    async def hire_free_agent(payload: Dict[str, Any]):
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        ftb_cmd_q.put({"cmd": "ftb_hire_free_agent", "entity_name": payload.get("entity_name", ""),
                       "free_agent_id": payload.get("free_agent_id", 0)})
        return {"status": "queued"}

    @app.post("/api/staff/fire")
    async def fire_entity(payload: Dict[str, Any]):
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        ftb_cmd_q.put({"cmd": "ftb_fire_entity", "entity_name": payload.get("entity_name", ""), "confirmed": True})
        return {"status": "queued"}

    @app.post("/api/staff/apply_job")
    async def apply_job(payload: Dict[str, Any]):
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        ftb_cmd_q.put({"cmd": "ftb_apply_job", "listing_id": payload.get("listing_id", 0)})
        return {"status": "queued"}

    def _is_entity_on_player_team(player_team: Any, entity: Any) -> bool:
        """Return True if the entity is currently on the player's roster."""
        if not player_team or not entity:
            return False

        contains = getattr(player_team, "_roster_contains", None)
        if callable(contains):
            try:
                return bool(contains(entity))
            except Exception:
                pass

        target_id = getattr(entity, "entity_id", None)
        if target_id is None:
            return False

        for role in ("drivers", "engineers", "mechanics", "strategist", "principal"):
            roster_value = getattr(player_team, role, None)
            if roster_value is None:
                continue
            if isinstance(roster_value, list):
                for member in roster_value:
                    if getattr(member, "entity_id", None) == target_id:
                        return True
            else:
                if getattr(roster_value, "entity_id", None) == target_id:
                    return True
        return False

    @app.post("/api/staff/contract/offer")
    async def submit_staff_contract_offer(payload: Dict[str, Any]):
        """Evaluate a contract offer for a member of the player's own team."""
        controller = shared_runtime.get("ftb_controller")
        if not controller or not getattr(controller, "state", None):
            return JSONResponse({"error": "Contract system unavailable"}, 503)

        try:
            entity_id = int(payload.get("entity_id"))
        except Exception:
            return JSONResponse({"error": "entity_id is required"}, 400)

        try:
            seasons = max(1, min(5, int(payload.get("seasons_duration", 2))))
        except Exception:
            seasons = 2

        try:
            salary_annual = max(0.0, float(payload.get("salary_annual", 0)))
        except Exception:
            return JSONResponse({"error": "salary_annual must be numeric"}, 400)

        try:
            signing_bonus_annual = max(0.0, float(payload.get("signing_bonus_annual", 0)))
        except Exception:
            return JSONResponse({"error": "signing_bonus_annual must be numeric"}, 400)

        performance_clauses = payload.get("performance_clauses", {})
        if not isinstance(performance_clauses, dict):
            performance_clauses = {}
        exit_clauses = payload.get("exit_clauses", {})
        if not isinstance(exit_clauses, dict):
            exit_clauses = {}

        try:
            negotiation_round = max(0, int(payload.get("negotiation_round", 0)))
        except Exception:
            negotiation_round = 0

        with controller.state_lock:
            state = controller.state
            player_team = getattr(state, "player_team", None)
            if not player_team:
                return JSONResponse({"error": "No player team loaded"}, 409)

            find_entity = getattr(state, "_find_entity_by_id", None)
            entity = find_entity(entity_id) if callable(find_entity) else None
            if not entity:
                return JSONResponse({"error": "Entity not found"}, 404)

            if not _is_entity_on_player_team(player_team, entity):
                return JSONResponse({"error": "Can only negotiate with your own team members"}, 403)

            existing_contract = (getattr(state, "contracts", {}) or {}).get(entity_id)
            existing_team_name = str(getattr(existing_contract, "team_name", "") or "")
            player_team_name = str(getattr(player_team, "name", "") or "")
            if existing_contract and existing_team_name and existing_team_name != player_team_name:
                return JSONResponse({"error": "Entity is not contracted to player team"}, 403)

            role = str(
                payload.get("role")
                or (getattr(existing_contract, "role", None) if existing_contract else None)
                or getattr(entity, "entity_type", type(entity).__name__)
            ).lower()

            offer_terms = {
                "entity_id": entity_id,
                "seasons_duration": seasons,
                # Match tkinter negotiation flow: UI edits annual values, sim stores per-tick.
                "base_salary": salary_annual / 365.0,
                "signing_bonus": signing_bonus_annual / 365.0,
                "performance_clauses": performance_clauses,
                "exit_clauses": exit_clauses,
                "role": role,
                "negotiation_round": negotiation_round,
            }

            rng = state.get_rng("contracts", entity_id)
            result = state.evaluate_contract_offer(entity_id, offer_terms, rng)

        counter_offer = result.get("counter_offer") if isinstance(result, dict) else None
        counter_offer_annual = None
        if isinstance(counter_offer, dict):
            counter_offer_annual = dict(counter_offer)
            try:
                counter_offer_annual["base_salary_annual"] = int(max(0, round(float(counter_offer.get("base_salary", 0)) * 365)))
            except Exception:
                counter_offer_annual["base_salary_annual"] = 0
            try:
                counter_offer_annual["signing_bonus_annual"] = int(max(0, round(float(counter_offer.get("signing_bonus", 0)) * 365)))
            except Exception:
                counter_offer_annual["signing_bonus_annual"] = 0

        return {
            "status": "ok",
            "entity_id": entity_id,
            "result": result,
            "counter_offer_annual": counter_offer_annual,
        }

    @app.post("/api/staff/contract/finalize")
    async def finalize_staff_contract(payload: Dict[str, Any]):
        """Finalize a contract for a member of the player's own team."""
        controller = shared_runtime.get("ftb_controller")
        if not controller or not getattr(controller, "state", None):
            return JSONResponse({"error": "Contract system unavailable"}, 503)

        try:
            entity_id = int(payload.get("entity_id"))
        except Exception:
            return JSONResponse({"error": "entity_id is required"}, 400)

        try:
            seasons = max(1, min(5, int(payload.get("seasons_duration", 2))))
        except Exception:
            seasons = 2

        try:
            salary_annual = max(0.0, float(payload.get("salary_annual", 0)))
        except Exception:
            return JSONResponse({"error": "salary_annual must be numeric"}, 400)

        try:
            signing_bonus_annual = max(0.0, float(payload.get("signing_bonus_annual", 0)))
        except Exception:
            return JSONResponse({"error": "signing_bonus_annual must be numeric"}, 400)

        performance_clauses = payload.get("performance_clauses", {})
        if not isinstance(performance_clauses, dict):
            performance_clauses = {}
        exit_clauses = payload.get("exit_clauses", {})
        if not isinstance(exit_clauses, dict):
            exit_clauses = {}

        with controller.state_lock:
            state = controller.state
            player_team = getattr(state, "player_team", None)
            if not player_team:
                return JSONResponse({"error": "No player team loaded"}, 409)

            find_entity = getattr(state, "_find_entity_by_id", None)
            entity = find_entity(entity_id) if callable(find_entity) else None
            if not entity:
                return JSONResponse({"error": "Entity not found"}, 404)

            if not _is_entity_on_player_team(player_team, entity):
                return JSONResponse({"error": "Can only negotiate with your own team members"}, 403)

            existing_contract = (getattr(state, "contracts", {}) or {}).get(entity_id)
            role = str(
                payload.get("role")
                or (getattr(existing_contract, "role", None) if existing_contract else None)
                or getattr(entity, "entity_type", type(entity).__name__)
            ).lower()

            contract_terms = {
                "entity_id": entity_id,
                "team_name": getattr(player_team, "name", ""),
                "role": role,
                "seasons_duration": seasons,
                # Match tkinter negotiation flow: UI edits annual values, sim stores per-tick.
                "base_salary": salary_annual / 365.0,
                "signing_bonus": signing_bonus_annual / 365.0,
                "performance_clauses": performance_clauses,
                "exit_clauses": exit_clauses,
            }

            success = bool(state.finalize_contract(entity_id, contract_terms))
            if success:
                try:
                    state.mark_dirty("all")
                except Exception:
                    pass

        if not success:
            return JSONResponse({"error": "Unable to finalize contract"}, 400)
        return {"status": "ok", "success": True, "entity_id": entity_id}

    # ──── REST: New Game (creates the save — called from wizard confirmation) ────
    @app.post("/api/new_game")
    async def new_game(payload: Dict[str, Any]):
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        ftb_cmd_q.put({
            "cmd": "ftb_new_save",
            "origin": payload.get("origin", "grassroots_hustler"),
            "identity": payload.get("identity", []),
            "save_mode": payload.get("save_mode", "replayable"),
            "tier": payload.get("tier", "grassroots"),
            "seed": payload.get("seed", 42),
            "team_name": payload.get("team_name", ""),
            "ownership": payload.get("ownership", "self_owned"),
            "manager_age": payload.get("manager_age", 32),
            "manager_first_name": payload.get("manager_first_name", "Manager"),
            "manager_last_name": payload.get("manager_last_name", "Unknown"),
        })
        # Update UI screen to loading while game is being created
        bridge.navigate_to("loading")
        return {"status": "queued"}

    # ──── REST: Load Game ────
    @app.post("/api/load_game")
    async def load_game(payload: Dict[str, Any]):
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        path = payload.get("path", "")
        if not path:
            return JSONResponse({"error": "path is required"}, 400)
        ftb_cmd_q.put({"cmd": "ftb_load_save", "path": path})
        return {"status": "queued", "path": path}

    # ──── REST: Save Game ────
    @app.post("/api/save_game")
    async def save_game(payload: Dict[str, Any]):
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        name = payload.get("name", "").strip()
        path = payload.get("path", "").strip()
        if name:
            # Resolve name → full path in saves/ directory
            if not name.endswith(".json"):
                name += ".json"
            # Sanitize: strip slashes and dangerous chars
            name = name.replace("/", "_").replace("\\", "_").replace("..", "_")
            saves_dir = os.path.join(
                shared_runtime.get("STATION_DIR", "."), "..", "..", "saves"
            )
            saves_dir = os.path.normpath(saves_dir)
            if not os.path.isdir(saves_dir):
                root = os.environ.get("RADIO_OS_ROOT", "")
                saves_dir = os.path.join(root, "saves") if root else "saves"
            os.makedirs(saves_dir, exist_ok=True)
            path = os.path.join(saves_dir, name)
        ftb_cmd_q.put({"cmd": "ftb_save", "path": path if path else None})
        return {"status": "queued", "path": path or "autosave"}

    # ──── REST: Delete Save ────
    @app.delete("/api/saves/{filename}")
    async def delete_save(filename: str):
        saves_dir = os.path.join(
            shared_runtime.get("STATION_DIR", "."), "..", "..", "saves"
        )
        saves_dir = os.path.normpath(saves_dir)
        if not os.path.isdir(saves_dir):
            root = os.environ.get("RADIO_OS_ROOT", "")
            saves_dir = os.path.join(root, "saves") if root else ""
        fp = os.path.join(saves_dir, filename)
        if not os.path.isfile(fp):
            return JSONResponse({"error": "File not found"}, 404)
        try:
            os.remove(fp)
            return {"status": "deleted", "file": filename}
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)

    # ──── REST: Tick Controls ────
    @app.post("/api/tick")
    async def tick_step(payload: Dict[str, Any]):
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        n = int(payload.get("n", 1))
        batch = payload.get("batch", False)
        cmd_name = "ftb_tick_batch" if batch else "ftb_tick_step"
        ftb_cmd_q.put({"cmd": cmd_name, "n": n})
        return {"status": "queued", "cmd": cmd_name, "n": n}

    # ──── REST: Audio state for web clients ────
    @app.get("/api/audio_state")
    async def get_audio_state():
        """Return current audio engine state so the browser can mirror it."""
        controller = shared_runtime.get("ftb_controller")
        state = controller.state if controller else None

        result: Dict[str, Any] = {
            "music_variant": "neutral",
            "music_ducking": False,
            "music_pbp_muted": False,
            "engine_league": None,
            "performance_scalar": 0.0,
        }

        # Try to read live values from the audio engine singleton
        try:
            from plugins.ftb_audio_engine import _audio_engine
            if _audio_engine:
                mc = _audio_engine.music_controller
                result["music_variant"] = mc.current_variant
                result["music_ducking"] = mc.is_ducking
                result["music_pbp_muted"] = mc.pbp_muted
                result["engine_league"] = _audio_engine.world_controller.current_engine_league
                result["performance_scalar"] = round(_audio_engine.current_scalar, 3)
        except Exception:
            pass

        # Also expose whether a live race is active (for engine sounds)
        if state:
            rds = getattr(state, "race_day_state", None)
            result["race_day_active"] = rds is not None and getattr(rds, "live_race_active", False)
        else:
            result["race_day_active"] = False

        return result

    # ──── Static: Audio files ────
    station_dir = shared_runtime.get("STATION_DIR", "") or os.environ.get("STATION_DIR", "")
    audio_dir_path = os.path.join(station_dir, "audio") if station_dir else ""
    if not audio_dir_path or not os.path.isdir(audio_dir_path):
        # Fallback: try to find audio under the station dir via RADIO_OS_ROOT
        radio_root = os.environ.get("RADIO_OS_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        for candidate in [
            os.path.join(radio_root, "stations", "FromTheBackmarker", "audio"),
            os.path.join(radio_root, "audio"),
        ]:
            if os.path.isdir(candidate):
                audio_dir_path = candidate
                break
    if audio_dir_path and os.path.isdir(audio_dir_path):
        app.mount("/audio", StaticFiles(directory=audio_dir_path), name="audio")
        log_fn("web", f"📢 Mounted /audio → {audio_dir_path}")

    # ──── WebSocket: Live stream ────
    @app.websocket("/ws/live")
    async def websocket_live(ws: WebSocket):
        await ws.accept()
        bridge.connected_clients.add(ws)
        log_fn("web", f"WebSocket client connected ({len(bridge.connected_clients)} total)")

        # Send initial state snapshot
        try:
            controller = shared_runtime.get("ftb_controller")
            if controller and hasattr(controller, "state_lock"):
                loop = asyncio.get_event_loop()
                state_data = await loop.run_in_executor(None, lambda: _serialize_with_lock(controller))
                await ws.send_json({"type": "initial_state", "data": state_data})

            # Send current subtitle
            await ws.send_json({"type": "subtitle", "data": {"text": bridge.last_subtitle}})
        except Exception:
            pass

        try:
            while True:
                # Listen for inbound commands from the client
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                    msg_type = msg.get("type", "")

                    if msg_type == "command":
                        cmd = msg.get("data", {})
                        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
                        if ftb_cmd_q and isinstance(cmd, dict):
                            ftb_cmd_q.put(cmd)
                            await ws.send_json({"type": "ack", "data": {"cmd": cmd.get("cmd", "")}})

                    elif msg_type == "ui_command":
                        action = msg.get("action", "")
                        payload = msg.get("payload", {})
                        ui_cmd_q = shared_runtime.get("ui_cmd_q")
                        if ui_cmd_q:
                            ui_cmd_q.put((action, payload))

                    elif msg_type == "ping":
                        await ws.send_json({"type": "pong", "data": {"ts": time.time()}})

                except json.JSONDecodeError:
                    pass

        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            bridge.connected_clients.discard(ws)
            log_fn("web", f"WebSocket client disconnected ({len(bridge.connected_clients)} total)")

    # ──── REST: FTB Data Explorer Endpoints ────
    @app.post("/api/ftb_data/query_season_summaries")
    async def query_season_summaries(payload: Dict[str, Any]):
        try:
            from plugins import ftb_data_explorer
            result = ftb_data_explorer.query_season_summaries(
                db_path=payload.get("db_path"),
                team_name=payload.get("team_name"),
                limit=payload.get("limit", 50)
            )
            return result
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)

    @app.post("/api/ftb_data/query_race_history")
    async def query_race_history(payload: Dict[str, Any]):
        try:
            from plugins import ftb_data_explorer
            result = ftb_data_explorer.query_race_history(
                db_path=payload.get("db_path"),
                team_name=payload.get("team_name"),
                season=payload.get("season"),
                limit=payload.get("limit", 50)
            )
            return result
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)

    @app.post("/api/ftb_data/query_financial_history")
    async def query_financial_history(payload: Dict[str, Any]):
        try:
            from plugins import ftb_data_explorer
            result = ftb_data_explorer.query_financial_history(
                db_path=payload.get("db_path"),
                team_name=payload.get("team_name"),
                season=payload.get("season"),
                limit=payload.get("limit", 50)
            )
            return result
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)

    @app.post("/api/ftb_data/query_career_stats")
    async def query_career_stats(payload: Dict[str, Any]):
        try:
            from plugins import ftb_data_explorer
            result = ftb_data_explorer.query_career_stats(
                db_path=payload.get("db_path"),
                entity_name=payload.get("entity_name"),
                role=payload.get("role"),
                limit=payload.get("limit", 50)
            )
            return result
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)

    @app.post("/api/ftb_data/query_team_outcomes")
    async def query_team_outcomes(payload: Dict[str, Any]):
        try:
            from plugins import ftb_data_explorer
            result = ftb_data_explorer.query_team_outcomes(
                db_path=payload.get("db_path"),
                team_name=payload.get("team_name"),
                season=payload.get("season"),
                limit=payload.get("limit", 50)
            )
            return result
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)

    @app.post("/api/ftb_data/query_championship_history")
    async def query_championship_history(payload: Dict[str, Any]):
        try:
            from plugins import ftb_data_explorer
            result = ftb_data_explorer.query_championship_history(
                db_path=payload.get("db_path"),
                limit=payload.get("limit", 50)
            )
            return result
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)

    @app.post("/api/ftb_data/query_all_tables")
    async def query_all_tables(payload: Dict[str, Any]):
        try:
            from plugins import ftb_data_explorer
            result = ftb_data_explorer.query_all_tables(
                db_path=payload.get("db_path")
            )
            return result
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)

    # ──── Mount static files (Svelte build) ────
    radio_root = os.environ.get("RADIO_OS_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dist_dir = os.path.join(radio_root, "web", "dist")
    if os.path.isdir(dist_dir):
        # Serve index.html for SPA routing — no-cache so phone always gets latest build
        @app.get("/")
        async def serve_index():
            index_path = os.path.join(dist_dir, "index.html")
            if os.path.exists(index_path):
                with open(index_path, "r", encoding="utf-8") as f:
                    html = f.read()
                return HTMLResponse(html, headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                })
            return HTMLResponse("<h1>FTB Web UI — build not found. Run: cd web && npm run build</h1>")

        app.mount("/assets", StaticFiles(directory=os.path.join(dist_dir, "assets")), name="assets")
    else:
        @app.get("/")
        async def no_frontend():
            return HTMLResponse(
                "<h1>FTB Web Server Running</h1>"
                "<p>Frontend not built yet. Run: <code>cd web && npm install && npm run build</code></p>"
                f"<p>API available at <a href='/api/health'>/api/health</a></p>"
                f"<p>Looked for dist at: {dist_dir}</p>"
            )

    return app


# ═══════════════════════════════════════════════════════════════════
# Server launcher — called from bookmark.py as a daemon thread target
# ═══════════════════════════════════════════════════════════════════

def _get_local_ip() -> str:
    """Get the LAN IP address for display purposes."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


WEB_SERVER_PORT = int(os.environ.get("FTB_WEB_PORT", "7555"))


def start_web_server(stop_event: threading.Event, shared_runtime: Dict[str, Any]):
    """
    Entry point — runs in a daemon thread.
    Creates bridge, builds FastAPI app, runs uvicorn until stop_event is set.
    """
    _ensure_imports()
    import uvicorn
    import signal
    import subprocess

    log_fn = shared_runtime.get("log", print)

    # ── Kill any stale process holding our port ──
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{WEB_SERVER_PORT}"],
            capture_output=True, text=True, timeout=5,
        )
        pids = result.stdout.strip().split()
        my_pid = str(os.getpid())
        for pid in pids:
            if pid and pid != my_pid:
                try:
                    os.kill(int(pid), signal.SIGKILL)
                    log_fn("web", f"Killed stale process {pid} on port {WEB_SERVER_PORT}")
                except (ProcessLookupError, PermissionError):
                    pass
        if pids:
            time.sleep(0.5)  # give OS time to release the socket
    except Exception as e:
        log_fn("web", f"Port cleanup skipped: {e}")

    bridge = get_bridge()
    shared_runtime["web_bridge"] = bridge

    app = create_app(shared_runtime, bridge)

    local_ip = _get_local_ip()
    log_fn("web", f"╔══════════════════════════════════════════════╗")
    log_fn("web", f"║  📡 FTB Web UI starting on port {WEB_SERVER_PORT}          ║")
    log_fn("web", f"║  Local:   http://127.0.0.1:{WEB_SERVER_PORT}              ║")
    log_fn("web", f"║  Network: http://{local_ip}:{WEB_SERVER_PORT}{''.ljust(16 - len(local_ip))}║")
    log_fn("web", f"╚══════════════════════════════════════════════╝")

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=WEB_SERVER_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    # Monitor stop_event in a background thread so we can shut uvicorn down
    def _watch_stop():
        stop_event.wait()
        server.should_exit = True

    watcher = threading.Thread(target=_watch_stop, daemon=True)
    watcher.start()

    # Run uvicorn (blocks until server.should_exit is set)
    server.run()
    log_fn("web", "Web server stopped")
