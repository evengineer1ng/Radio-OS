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
from collections import deque
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

    def __init__(self):
        self._lock = threading.Lock()
        self.last_subtitle: str = ""
        self.last_widget_update: Dict[str, Any] = {}
        self.event_log: deque = deque(maxlen=500)
        self.connected_clients: Set[Any] = set()  # WebSocket refs
        self._broadcast_queue: asyncio.Queue | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

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

def serialize_entity(entity) -> Dict[str, Any]:
    """Serialize a Driver/Engineer/Mechanic/Strategist/Principal to dict."""
    if entity is None:
        return None
    d: Dict[str, Any] = {
        "name": getattr(entity, "name", "Unknown"),
        "type": getattr(entity, "entity_type", type(entity).__name__),
        "age": getattr(entity, "age", 0),
        "overall": getattr(entity, "overall_rating", 0) if hasattr(entity, "overall_rating") else 0,
    }
    # Grab stat dict if available
    if hasattr(entity, "stats") and isinstance(entity.stats, dict):
        d["stats"] = {k: round(float(v), 1) for k, v in entity.stats.items() if isinstance(v, (int, float))}
    elif hasattr(entity, "to_dict"):
        try:
            d.update(entity.to_dict())
        except Exception:
            pass
    # Contract info
    if hasattr(entity, "contract"):
        c = entity.contract
        if c:
            d["contract"] = {
                "salary": getattr(c, "salary", 0),
                "seasons_remaining": getattr(c, "seasons_remaining", 0),
                "buyout": getattr(c, "buyout_clause", 0),
            }
    return d


def serialize_team(team) -> Dict[str, Any]:
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
        d["budget"] = {
            "cash": getattr(budget, "cash", 0),
            "weekly_expenses": getattr(budget, "weekly_expenses", 0),
            "weekly_income": getattr(budget, "weekly_income", 0),
        }
    # Roster
    for role in ("drivers", "engineers", "mechanics", "strategist", "principal"):
        val = getattr(team, role, None)
        if val is None:
            continue
        if isinstance(val, list):
            d["roster"][role] = [serialize_entity(e) for e in val if e]
        else:
            d["roster"][role] = serialize_entity(val)
    # Car
    car = getattr(team, "car", None)
    if car:
        d["car"] = {
            "name": getattr(car, "name", ""),
            "overall": getattr(car, "overall_rating", 0) if hasattr(car, "overall_rating") else 0,
        }
        if hasattr(car, "stats") and isinstance(car.stats, dict):
            d["car"]["stats"] = {k: round(float(v), 1) for k, v in car.stats.items() if isinstance(v, (int, float))}
        if hasattr(car, "equipped_parts"):
            d["car"]["equipped_parts"] = []
            for p in (car.equipped_parts or []):
                d["car"]["equipped_parts"].append({
                    "id": getattr(p, "part_id", ""),
                    "name": getattr(p, "name", ""),
                    "type": getattr(p, "part_type", ""),
                    "quality": getattr(p, "quality", 0),
                })
        if hasattr(car, "parts_inventory"):
            d["car"]["parts_inventory"] = []
            for p in (car.parts_inventory or []):
                d["car"]["parts_inventory"].append({
                    "id": getattr(p, "part_id", ""),
                    "name": getattr(p, "name", ""),
                    "type": getattr(p, "part_type", ""),
                    "quality": getattr(p, "quality", 0),
                    "cost": getattr(p, "cost", 0),
                })
    # Infrastructure
    infra = getattr(team, "infrastructure", None)
    if infra:
        if isinstance(infra, dict):
            d["infrastructure"] = {k: float(v) for k, v in infra.items() if isinstance(v, (int, float))}
        elif hasattr(infra, "__dict__"):
            d["infrastructure"] = {k: float(v) for k, v in vars(infra).items() if isinstance(v, (int, float))}
    # R&D projects
    rd = getattr(team, "rd_projects", None) or getattr(team, "active_rd_projects", None) or []
    for proj in rd:
        d["rd_projects"].append({
            "id": getattr(proj, "project_id", ""),
            "subsystem": getattr(proj, "subsystem", ""),
            "progress": getattr(proj, "progress", 0),
            "risk_level": getattr(proj, "risk_level", 0),
            "budget": getattr(proj, "budget", 0),
        })
    return d


def serialize_game_state(controller) -> Dict[str, Any]:
    """Full game state snapshot for the REST API. Call with state_lock held."""
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
    }

    # Player team
    if state.player_team:
        out["player_team"] = serialize_team(state.player_team)
    else:
        out["player_team"] = None

    # AI teams (summary)
    out["ai_teams"] = []
    for t in (state.ai_teams or []):
        out["ai_teams"].append(serialize_team(t))

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
            for race in sched:
                if isinstance(race, dict):
                    out["leagues"][lname]["schedule"].append(race)
                elif hasattr(race, "__dict__"):
                    out["leagues"][lname]["schedule"].append({
                        "track_name": getattr(race, "track_name", ""),
                        "tick": getattr(race, "tick", 0),
                        "completed": getattr(race, "completed", False),
                    })

    # Free agents (summary for job market)
    out["free_agents"] = []
    for fa in (state.free_agents or [])[:100]:
        entity = getattr(fa, "entity", fa)
        out["free_agents"].append(serialize_entity(entity))

    # Job board
    jb = getattr(state, "job_board", None)
    if jb:
        listings = getattr(jb, "listings", [])
        out["job_board"] = []
        for listing in (listings or []):
            out["job_board"].append({
                "id": id(listing),
                "team_name": getattr(listing, "team_name", ""),
                "role": getattr(listing, "role", ""),
                "salary_range": getattr(listing, "salary_range", [0, 0]),
                "requirements": getattr(listing, "requirements", ""),
            })

    # Recent events
    out["recent_events"] = []
    for evt in (state.event_history or [])[-30:]:
        out["recent_events"].append({
            "type": getattr(evt, "event_type", ""),
            "description": getattr(evt, "description", str(evt)),
            "tick": getattr(evt, "tick", 0),
            "category": getattr(evt, "category", ""),
        })

    # Pending decisions
    out["pending_decisions"] = []
    for dec in (state.pending_decisions or []):
        out["pending_decisions"].append({
            "id": id(dec),
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
                "value": getattr(sp, "annual_value", 0),
                "seasons_remaining": getattr(sp, "seasons_remaining", 0),
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

    # Parts marketplace (top 50 by quality)
    out["parts_marketplace"] = []
    for pid, part in list(state.parts_catalog.items())[:50]:
        out["parts_marketplace"].append({
            "id": pid,
            "name": getattr(part, "name", ""),
            "type": getattr(part, "part_type", ""),
            "quality": getattr(part, "quality", 0),
            "cost": getattr(part, "cost", 0),
        })

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
                "value": getattr(sp, "annual_value", 0),
                "seasons_remaining": getattr(sp, "seasons_remaining", 0),
                "confidence": getattr(sp, "confidence", 100),
                "sponsor_id": getattr(sp, "sponsor_id", ""),
            })

    # ─── Play-by-Play data (built from race_day_state) ────────────
    out["play_by_play"] = {
        "is_live": rds is not None and getattr(rds, "live_race_active", False),
        "lap_info": {
            "current": getattr(rds, "current_lap", 0) if rds else 0,
            "total": getattr(rds, "total_laps", 0) if rds else 0,
        },
        "standings": out.get("race_day", {}).get("standings", []),
        "live_events": out.get("race_day", {}).get("events", []),
    }

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
            with controller.state_lock:
                data = serialize_game_state(controller)
            return data
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)

    # ──── REST: Current subtitle ────
    @app.get("/api/subtitle")
    async def get_subtitle():
        return {"text": bridge.last_subtitle}

    # ──── REST: Snapshot (subtitle + recent events) ────
    @app.get("/api/snapshot")
    async def get_snapshot():
        return bridge.get_snapshot()

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
            with controller.state_lock:
                data = serialize_game_state(controller)
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
    async def race_day_pause():
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        ftb_cmd_q.put({"cmd": "ftb_pause_live_race"})
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

    # ──── REST: Parts Marketplace Actions ────
    @app.post("/api/parts/buy")
    async def buy_part(payload: Dict[str, Any]):
        ftb_cmd_q = shared_runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            return JSONResponse({"error": "ftb_cmd_q not available"}, 503)
        ftb_cmd_q.put({"cmd": "ftb_purchase_part", "part_id": payload.get("part_id", ""), "cost": payload.get("cost", 0)})
        return {"status": "queued"}

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

    # ──── REST: New Game ────
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
        path = payload.get("path", "")
        ftb_cmd_q.put({"cmd": "ftb_save", "path": path if path else None})
        return {"status": "queued"}

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
                with controller.state_lock:
                    state_data = serialize_game_state(controller)
                await ws.send_json({"type": "initial_state", "data": state_data})

            # Send current subtitle
            await ws.send_json({"type": "subtitle", "data": {"text": bridge.last_subtitle}})
        except Exception:
            pass

        # Spawn broadcast listener task
        broadcast_task = asyncio.create_task(_ws_broadcast_listener(ws, bridge))

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
            broadcast_task.cancel()
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
        # Serve index.html for SPA routing
        @app.get("/")
        async def serve_index():
            index_path = os.path.join(dist_dir, "index.html")
            if os.path.exists(index_path):
                with open(index_path, "r", encoding="utf-8") as f:
                    return HTMLResponse(f.read())
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


async def _ws_broadcast_listener(ws, bridge: WebBridge):
    """Coroutine that forwards broadcast messages from the bridge to a single client."""
    bq = bridge._broadcast_queue
    if not bq:
        return
    try:
        while True:
            msg = await bq.get()
            try:
                await ws.send_text(msg)
            except Exception:
                break
    except asyncio.CancelledError:
        pass


# ═══════════════════════════════════════════════════════════════════
# Per-client broadcast fan-out
# ═══════════════════════════════════════════════════════════════════
# The bridge puts messages on a single asyncio.Queue. We need to
# fan-out to each connected client. We do this with a broadcaster task
# + per-client queues.

class BroadcastManager:
    """Manages per-client message queues for WebSocket fan-out."""

    def __init__(self):
        self._clients: Dict[int, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    async def register(self, ws_id: int) -> asyncio.Queue:
        async with self._lock:
            q = asyncio.Queue(maxsize=200)
            self._clients[ws_id] = q
            return q

    async def unregister(self, ws_id: int):
        async with self._lock:
            self._clients.pop(ws_id, None)

    async def broadcast(self, msg: str):
        async with self._lock:
            dead = []
            for ws_id, q in self._clients.items():
                try:
                    q.put_nowait(msg)
                except asyncio.QueueFull:
                    dead.append(ws_id)
            for ws_id in dead:
                self._clients.pop(ws_id, None)


# ═══════════════════════════════════════════════════════════════════
# Revised FastAPI app with proper fan-out
# ═══════════════════════════════════════════════════════════════════

def create_full_app(shared_runtime: Dict[str, Any], bridge: WebBridge):
    """Build FastAPI app with proper per-client WebSocket broadcasting."""
    _ensure_imports()
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import JSONResponse, HTMLResponse
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="FTB Web Server", version="1.0.0")
    
    # CRITICAL: Test if this simple WebSocket works
    @app.websocket("/ws/simple")
    async def websocket_simple_test(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_text("Simple WebSocket connected!")
        try:
            while True:
                data = await websocket.receive_text()
                await websocket.send_text(f"Echo: {data}")
        except WebSocketDisconnect:
            pass

    broadcaster = BroadcastManager()

    # TEMPORARILY DISABLE CORS MIDDLEWARE TO TEST
    # app.add_middleware(
    #     CORSMiddleware,
    #     allow_origins=["*"],
    #     allow_methods=["*"],
    #     allow_headers=["*"],
    # )

    log_fn = shared_runtime.get("log", lambda *a, **k: None)

    # ─── Bridge → broadcaster pump (runs as background task) ───
    async def bridge_pump():
        """Drain bridge._broadcast_queue and fan out to all clients."""
        bq = bridge._broadcast_queue
        if not bq:
            return
        while True:
            try:
                msg = await bq.get()
                await broadcaster.broadcast(msg)
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
        log_fn("web", "Bridge pump started")

    @app.on_event("shutdown")
    async def on_shutdown():
        task = getattr(app.state, "pump_task", None)
        if task:
            task.cancel()

    # ──── REST endpoints (same as above) ────
    @app.get("/api/health")
    async def health():
        return {"status": "ok", "ts": time.time()}

    @app.get("/api/websocket-test")
    async def websocket_test():
        return {"message": "WebSocket handler should be available at /ws/live", "websocket_endpoint": "/ws/live"}

    @app.get("/api/state")
    async def get_state():
        controller = shared_runtime.get("ftb_controller")
        if not controller:
            return JSONResponse({"status": "no_controller"}, 503)
        try:
            with controller.state_lock:
                data = serialize_game_state(controller)
            return data
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)

    @app.get("/api/subtitle")
    async def get_subtitle():
        return {"text": bridge.last_subtitle}

    @app.get("/api/snapshot")
    async def get_snapshot():
        return bridge.get_snapshot()

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

    @app.get("/api/saves")
    async def list_saves():
        root = os.environ.get("RADIO_OS_ROOT", "")
        saves_dir = os.path.join(root, "saves") if root else os.path.join(
            shared_runtime.get("STATION_DIR", "."), "..", "..", "saves"
        )
        saves_dir = os.path.normpath(saves_dir)
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

    # ──── WebSocket with per-client queue ────
    @app.websocket("/ws/live")
    async def websocket_live(ws: WebSocket):
        log_fn("web", "🔌 WebSocket /ws/live attempt")
        try:
            await ws.accept()
            log_fn("web", "✅ WebSocket /ws/live accepted!")
            await ws.send_text("WebSocket /ws/live connected!")
            
            while True:
                data = await ws.receive_text()
                log_fn("web", f"📥 /ws/live received: {data}")
                await ws.send_text(f"Live echo: {data}")
        except WebSocketDisconnect:
            log_fn("web", "🔌 /ws/live disconnected")
        except Exception as e:
            log_fn("web", f"❌ /ws/live error: {e}")
            import traceback
            log_fn("web", f"Traceback: {traceback.format_exc()}")
            raise

    # ──── Static files ────
    radio_root = os.environ.get("RADIO_OS_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dist_dir = os.path.join(radio_root, "web", "dist")

    @app.get("/")
    async def serve_index():
        index_path = os.path.join(dist_dir, "index.html")
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())
        return HTMLResponse(
            "<!DOCTYPE html><html><body style='font-family:system-ui;background:#1a1a2e;color:#e0e0e0;padding:2rem'>"
            "<h1>📡 FTB Web Server Running</h1>"
            "<p>Frontend not built yet.</p>"
            "<pre>cd web\nnpm install\nnpm run build</pre>"
            f"<p>API: <a href='/api/health' style='color:#4cc9f0'>/api/health</a> · "
            f"<a href='/api/state' style='color:#4cc9f0'>/api/state</a></p>"
            "</body></html>"
        )

    assets_dir = os.path.join(dist_dir, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

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

    log_fn = shared_runtime.get("log", print)

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
