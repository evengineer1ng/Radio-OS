"""
FTB Remote — Pure HTTP remote control for Tailscale / LAN access.

NO WebSocket. NO FastAPI. NO uvicorn. Just Python stdlib http.server.
Serves self-contained HTML pages you can refresh from your phone abroad.

Start: auto-started by bookmark.py if enabled, or run standalone:
    python plugins/ftb_remote.py

Designed for Tailscale: run the sim at home, control from anywhere via
your Tailscale IP (e.g. http://100.x.y.z:7580).
"""

from __future__ import annotations

import html
import json
import os
import queue
import socket
import threading
import time
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

PLUGIN_NAME = "ftb_remote"
PLUGIN_DESC = "HTTP-only remote control — works over Tailscale, no WebSocket"
IS_FEED = False

# ═══════════════════════════════════════════════════════════════════
# Port & config
# ═══════════════════════════════════════════════════════════════════
REMOTE_PORT = int(os.environ.get("FTB_REMOTE_PORT", "7580"))

# Global ref to shared_runtime (set by start_remote_server)
_shared_runtime: Dict[str, Any] = {}


# ═══════════════════════════════════════════════════════════════════
# State helpers — read from the FTBController
# ═══════════════════════════════════════════════════════════════════

def _get_controller():
    return _shared_runtime.get("ftb_controller")


def _safe_state_snapshot() -> Dict[str, Any]:
    """Build a JSON-safe snapshot of game state, or a stub if unavailable."""
    ctrl = _get_controller()
    if not ctrl or not ctrl.state:
        return {"status": "no_game"}

    state = ctrl.state
    try:
        with ctrl.state_lock:
            snap: Dict[str, Any] = {
                "status": "running",
                "tick": state.tick,
                "date": state.current_date_str() if hasattr(state, "current_date_str") else f"Tick {state.tick}",
                "phase": getattr(state, "phase", ""),
                "sim_year": getattr(state, "sim_year", 0),
                "season": getattr(state, "season_number", 0),
                "time_mode": getattr(state, "time_mode", "paused"),
                "control_mode": getattr(state, "control_mode", "human"),
                "race_day_active": getattr(state, "race_day_active", False),
                "races_completed": getattr(state, "races_completed_this_season", 0),
                "in_offseason": getattr(state, "in_offseason", False),
                "player_identity": getattr(state, "player_identity", ""),
                "manager_name": f"{getattr(state, 'manager_first_name', '')} {getattr(state, 'manager_last_name', '')}".strip(),
            }

            # Player team
            pt = state.player_team
            if pt:
                budget = getattr(pt, "budget", None)
                snap["team"] = {
                    "name": getattr(pt, "name", ""),
                    "cash": getattr(budget, "cash", 0) if budget else 0,
                    "weekly_income": getattr(budget, "weekly_income", 0) if budget else 0,
                    "weekly_expenses": getattr(budget, "weekly_expenses", 0) if budget else 0,
                }

                # Roster
                roster = []
                for role_attr in ("drivers", "engineers", "mechanics"):
                    for e in (getattr(pt, role_attr, None) or []):
                        roster.append({
                            "name": getattr(e, "name", "?"),
                            "role": role_attr.rstrip("s").title(),
                            "age": getattr(e, "age", 0),
                            "overall": getattr(e, "overall_rating", 0) if hasattr(e, "overall_rating") else 0,
                        })
                strat = getattr(pt, "strategist", None)
                if strat:
                    roster.append({
                        "name": getattr(strat, "name", "?"),
                        "role": "Strategist",
                        "age": getattr(strat, "age", 0),
                        "overall": getattr(strat, "overall_rating", 0) if hasattr(strat, "overall_rating") else 0,
                    })
                princ = getattr(pt, "principal", None)
                if princ:
                    roster.append({
                        "name": getattr(princ, "name", "?"),
                        "role": "Principal",
                        "age": getattr(princ, "age", 0),
                        "overall": getattr(princ, "overall_rating", 0) if hasattr(princ, "overall_rating") else 0,
                    })
                snap["roster"] = roster

                # Car
                car = getattr(pt, "car", None)
                if car:
                    snap["car"] = {
                        "name": getattr(car, "name", ""),
                        "overall": getattr(car, "overall_rating", 0) if hasattr(car, "overall_rating") else 0,
                    }
                    if hasattr(car, "stats") and isinstance(car.stats, dict):
                        snap["car"]["stats"] = {k: round(float(v), 1) for k, v in car.stats.items() if isinstance(v, (int, float))}

            # Leagues summary
            snap["leagues"] = {}
            for lname, league in (state.leagues or {}).items():
                ldata: Dict[str, Any] = {
                    "tier": getattr(league, "tier_name", getattr(league, "tier", "")),
                    "teams": getattr(league, "team_names", []),
                    "races_this_season": getattr(league, "races_this_season", 0),
                }
                # Championship table
                ct = getattr(league, "championship_table", None)
                if ct:
                    if isinstance(ct, dict):
                        ldata["standings"] = ct
                    elif isinstance(ct, list):
                        ldata["standings"] = ct
                # Driver championship
                dc = getattr(league, "driver_championship", None)
                if dc:
                    if isinstance(dc, dict):
                        ldata["driver_standings"] = dc
                    elif isinstance(dc, list):
                        ldata["driver_standings"] = dc
                snap["leagues"][lname] = ldata

            # Recent events (last 20)
            snap["recent_events"] = []
            for evt in (state.event_history or [])[-20:]:
                snap["recent_events"].append({
                    "type": getattr(evt, "event_type", ""),
                    "category": getattr(evt, "category", ""),
                    "desc": getattr(evt, "description", str(evt)),
                    "tick": getattr(evt, "tick", getattr(evt, "ts", 0)),
                })

            # Pending decisions
            snap["decisions"] = []
            for dec in (state.pending_decisions or []):
                snap["decisions"].append({
                    "id": id(dec),
                    "prompt": getattr(dec, "prompt", ""),
                    "options": [
                        {"label": getattr(o, "label", ""), "desc": getattr(o, "description", "")}
                        for o in (getattr(dec, "options", []) or [])
                    ],
                })

        return snap
    except Exception as e:
        return {"status": "error", "error": str(e), "trace": traceback.format_exc()}


def _send_cmd(cmd_dict: Dict[str, Any]) -> str:
    """Push a command onto ftb_cmd_q. Returns status string."""
    ftb_cmd_q = _shared_runtime.get("ftb_cmd_q")
    if not ftb_cmd_q:
        return "ERROR: ftb_cmd_q not available"
    try:
        ftb_cmd_q.put(cmd_dict)
        return f"OK: {cmd_dict.get('cmd', '?')} queued"
    except Exception as e:
        return f"ERROR: {e}"


# ═══════════════════════════════════════════════════════════════════
# HTML Templates — self-contained, mobile-friendly, no JS frameworks
# ═══════════════════════════════════════════════════════════════════

_CSS = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: #0d1117; color: #c9d1d9;
    padding: 12px; max-width: 800px; margin: 0 auto;
    -webkit-text-size-adjust: 100%;
  }
  h1 { color: #58a6ff; font-size: 1.4em; margin-bottom: 8px; }
  h2 { color: #8b949e; font-size: 1.1em; margin: 16px 0 6px 0; border-bottom: 1px solid #21262d; padding-bottom: 4px; }
  h3 { color: #c9d1d9; font-size: 1em; margin: 10px 0 4px 0; }
  a { color: #58a6ff; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .card {
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    padding: 12px; margin-bottom: 12px;
  }
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 12px;
    font-size: 0.8em; font-weight: 600;
  }
  .badge-green { background: #238636; color: #fff; }
  .badge-yellow { background: #9e6a03; color: #fff; }
  .badge-red { background: #da3633; color: #fff; }
  .badge-blue { background: #1f6feb; color: #fff; }
  .badge-gray { background: #30363d; color: #8b949e; }
  table { width: 100%; border-collapse: collapse; margin: 6px 0; font-size: 0.9em; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #21262d; }
  th { color: #8b949e; font-weight: 600; font-size: 0.85em; }
  .money { color: #3fb950; font-weight: 600; }
  .money-neg { color: #f85149; font-weight: 600; }
  .btn {
    display: inline-block; padding: 8px 16px; margin: 4px;
    background: #21262d; border: 1px solid #30363d; border-radius: 6px;
    color: #c9d1d9; font-size: 0.95em; cursor: pointer;
    text-decoration: none; text-align: center;
  }
  .btn:hover { background: #30363d; border-color: #58a6ff; text-decoration: none; }
  .btn-primary { background: #238636; border-color: #2ea043; color: #fff; }
  .btn-primary:hover { background: #2ea043; }
  .btn-danger { background: #da3633; border-color: #f85149; color: #fff; }
  .btn-danger:hover { background: #f85149; }
  .btn-blue { background: #1f6feb; border-color: #388bfd; color: #fff; }
  .btn-blue:hover { background: #388bfd; }
  .actions { margin: 12px 0; display: flex; flex-wrap: wrap; gap: 4px; }
  .event-log { max-height: 300px; overflow-y: auto; font-size: 0.85em; }
  .event-row { padding: 4px 0; border-bottom: 1px solid #161b22; }
  .event-cat { color: #8b949e; font-size: 0.8em; }
  .topbar {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 8px; flex-wrap: wrap; gap: 8px;
  }
  .topbar-right { font-size: 0.85em; color: #8b949e; }
  .meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  @media (max-width: 480px) { .meta-grid { grid-template-columns: 1fr; } }
  .flash {
    background: #1f6feb22; border: 1px solid #1f6feb; border-radius: 6px;
    padding: 8px 12px; margin-bottom: 12px; font-size: 0.9em;
  }
  .nav { margin-bottom: 12px; display: flex; gap: 6px; flex-wrap: wrap; }
  .nav a { padding: 6px 12px; background: #21262d; border-radius: 6px; font-size: 0.85em; }
  .nav a.active { background: #1f6feb; color: #fff; }
  .auto-refresh { font-size: 0.8em; color: #8b949e; text-align: right; margin-top: 8px; }
</style>
"""

_NAV = """
<div class="nav">
  <a href="/" {act_dash}>Dashboard</a>
  <a href="/team" {act_team}>Team</a>
  <a href="/standings" {act_stand}>Standings</a>
  <a href="/events" {act_events}>Events</a>
  <a href="/controls" {act_ctrl}>Controls</a>
  <a href="/api/state.json">Raw JSON</a>
</div>
"""

_AUTO_REFRESH = """
<div class="auto-refresh">
  Auto-refresh:
  <a href="{path}?r=5">5s</a> ·
  <a href="{path}?r=10">10s</a> ·
  <a href="{path}?r=30">30s</a> ·
  <a href="{path}">off</a>
</div>
"""

def _nav(active: str) -> str:
    acts = {"dash": "", "team": "", "stand": "", "events": "", "ctrl": ""}
    if active in acts:
        acts[active] = 'class="active"'
    return _NAV.format(
        act_dash=acts["dash"], act_team=acts["team"],
        act_stand=acts["stand"], act_events=acts["events"],
        act_ctrl=acts["ctrl"],
    )

def _head(title: str, refresh_sec: int = 0, path: str = "/") -> str:
    meta_refresh = f'<meta http-equiv="refresh" content="{refresh_sec}">' if refresh_sec > 0 else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{meta_refresh}
<title>{title} — FTB Remote</title>
{_CSS}
</head><body>
"""

def _footer(path: str = "/") -> str:
    return _AUTO_REFRESH.format(path=path) + "</body></html>"

def _money(val) -> str:
    try:
        v = float(val)
        cls = "money" if v >= 0 else "money-neg"
        return f'<span class="{cls}">${v:,.0f}</span>'
    except (ValueError, TypeError):
        return str(val)

def _time_mode_badge(mode: str) -> str:
    if mode == "auto":
        return '<span class="badge badge-green">AUTO</span>'
    elif mode == "paused":
        return '<span class="badge badge-red">PAUSED</span>'
    else:
        return f'<span class="badge badge-yellow">{html.escape(mode.upper())}</span>'


# ── Page renderers ──

def render_dashboard(snap: Dict, flash: str = "", refresh: int = 0) -> str:
    if snap.get("status") == "no_game":
        return (_head("No Game", refresh, "/") + _nav("dash") +
                '<div class="card"><h2>No game loaded</h2><p>Start or load a game from the desktop app, then refresh this page.</p></div>' +
                _footer("/"))

    if snap.get("status") == "error":
        return (_head("Error", refresh, "/") + _nav("dash") +
                f'<div class="card"><h2>Error reading state</h2><pre>{html.escape(snap.get("error", ""))}</pre></div>' +
                _footer("/"))

    team = snap.get("team", {})
    p = _head("Dashboard", refresh, "/") + _nav("dash")
    if flash:
        p += f'<div class="flash">{html.escape(flash)}</div>'

    p += '<div class="topbar">'
    p += f'<h1>🏎️ {html.escape(team.get("name", "Unknown"))}</h1>'
    p += f'<div class="topbar-right">{html.escape(snap.get("date", ""))}</div>'
    p += '</div>'

    # Status bar
    p += '<div class="card"><div class="meta-grid">'
    p += f'<div>Tick: <strong>{snap.get("tick", 0)}</strong></div>'
    p += f'<div>Mode: {_time_mode_badge(snap.get("time_mode", "paused"))}</div>'
    p += f'<div>Season: <strong>{snap.get("season", 0)}</strong> · Year {snap.get("sim_year", 0)}</div>'
    p += f'<div>Races: <strong>{snap.get("races_completed", 0)}</strong></div>'
    p += f'<div>Cash: {_money(team.get("cash", 0))}</div>'
    p += f'<div>Weekly: {_money(team.get("weekly_income", 0))} in / {_money(-abs(team.get("weekly_expenses", 0)))} out</div>'
    if snap.get("race_day_active"):
        p += '<div><span class="badge badge-red">🏁 RACE DAY ACTIVE</span></div>'
    if snap.get("in_offseason"):
        p += '<div><span class="badge badge-yellow">OFF-SEASON</span></div>'
    p += '</div></div>'

    # Quick controls
    p += '<div class="card"><h2>Quick Controls</h2><div class="actions">'
    p += '<a class="btn btn-primary" href="/cmd?c=ftb_tick_step&n=1">▶ Advance 1 Day</a>'
    p += '<a class="btn btn-primary" href="/cmd?c=ftb_tick_step&n=7">⏩ Advance 7 Days</a>'
    p += '<a class="btn btn-primary" href="/cmd?c=ftb_tick_step&n=30">⏭ Advance 30 Days</a>'
    p += '<a class="btn" href="/cmd?c=ftb_save">💾 Save Game</a>'
    p += '<a class="btn btn-blue" href="/cmd?c=ftb_delegate">🤖 Delegate</a>'
    p += '<a class="btn" href="/cmd?c=ftb_regain_control">✋ Regain Control</a>'
    p += '</div></div>'

    # Pending decisions
    decisions = snap.get("decisions", [])
    if decisions:
        p += '<div class="card"><h2>⚠️ Pending Decisions</h2>'
        for dec in decisions:
            p += f'<div style="margin:8px 0"><strong>{html.escape(dec.get("prompt", ""))}</strong><br>'
            for i, opt in enumerate(dec.get("options", [])):
                p += f'<a class="btn" href="/decide?dec_id={dec["id"]}&opt={i}">{html.escape(opt.get("label", f"Option {i}"))}</a> '
                if opt.get("desc"):
                    p += f'<span style="font-size:0.8em;color:#8b949e">{html.escape(opt["desc"])}</span>'
                p += '<br>'
            p += '</div>'
        p += '</div>'

    # Recent events (last 5)
    events = snap.get("recent_events", [])[-5:]
    if events:
        p += '<div class="card"><h2>Recent Events</h2>'
        for evt in reversed(events):
            p += f'<div class="event-row"><span class="event-cat">[{html.escape(evt.get("category", ""))}]</span> '
            p += f'{html.escape(evt.get("desc", ""))} <span style="color:#484f58">t{evt.get("tick", 0)}</span></div>'
        p += f'<p style="margin-top:6px"><a href="/events">View all events →</a></p>'
        p += '</div>'

    p += _footer("/")
    return p


def render_team(snap: Dict, refresh: int = 0) -> str:
    if snap.get("status") != "running":
        return render_dashboard(snap, refresh=refresh)

    team = snap.get("team", {})
    p = _head("Team", refresh, "/team") + _nav("team")
    p += f'<h1>🏎️ {html.escape(team.get("name", ""))}</h1>'

    # Finances
    p += '<div class="card"><h2>💰 Finances</h2>'
    p += f'<p>Cash: {_money(team.get("cash", 0))}</p>'
    p += f'<p>Weekly income: {_money(team.get("weekly_income", 0))} · Expenses: {_money(-abs(team.get("weekly_expenses", 0)))}</p>'
    p += '</div>'

    # Roster
    roster = snap.get("roster", [])
    if roster:
        p += '<div class="card"><h2>👥 Roster</h2>'
        p += '<table><tr><th>Name</th><th>Role</th><th>Age</th><th>OVR</th></tr>'
        for r in roster:
            p += f'<tr><td>{html.escape(r.get("name", ""))}</td>'
            p += f'<td>{html.escape(r.get("role", ""))}</td>'
            p += f'<td>{r.get("age", 0)}</td>'
            p += f'<td><strong>{r.get("overall", 0):.0f}</strong></td></tr>'
        p += '</table></div>'

    # Car
    car = snap.get("car")
    if car:
        p += '<div class="card"><h2>🏎 Car</h2>'
        p += f'<p><strong>{html.escape(car.get("name", ""))}</strong> — Overall: {car.get("overall", 0):.0f}</p>'
        stats = car.get("stats", {})
        if stats:
            p += '<table><tr><th>Stat</th><th>Value</th></tr>'
            for k, v in sorted(stats.items()):
                p += f'<tr><td>{html.escape(k)}</td><td>{v:.1f}</td></tr>'
            p += '</table>'
        p += '</div>'

    p += _footer("/team")
    return p


def render_standings(snap: Dict, refresh: int = 0) -> str:
    if snap.get("status") != "running":
        return render_dashboard(snap, refresh=refresh)

    p = _head("Standings", refresh, "/standings") + _nav("stand")
    p += '<h1>🏆 Championship Standings</h1>'

    leagues = snap.get("leagues", {})
    if not leagues:
        p += '<div class="card"><p>No league data available yet.</p></div>'
    else:
        for lname, ldata in leagues.items():
            p += f'<div class="card"><h2>{html.escape(lname)}</h2>'
            p += f'<p>Tier: {html.escape(str(ldata.get("tier", "")))} · Races: {ldata.get("races_this_season", 0)}</p>'

            # Constructor standings
            standings = ldata.get("standings")
            if standings:
                p += '<h3>Constructor Championship</h3>'
                if isinstance(standings, dict):
                    sorted_s = sorted(standings.items(), key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0, reverse=True)
                    p += '<table><tr><th>#</th><th>Team</th><th>Points</th></tr>'
                    for i, (team_name, pts) in enumerate(sorted_s, 1):
                        p += f'<tr><td>{i}</td><td>{html.escape(str(team_name))}</td><td><strong>{pts}</strong></td></tr>'
                    p += '</table>'
                elif isinstance(standings, list):
                    p += '<table><tr><th>#</th><th>Team</th><th>Points</th></tr>'
                    for i, entry in enumerate(standings, 1):
                        if isinstance(entry, dict):
                            p += f'<tr><td>{i}</td><td>{html.escape(str(entry.get("team", entry.get("name", ""))))}</td><td><strong>{entry.get("points", 0)}</strong></td></tr>'
                        else:
                            p += f'<tr><td>{i}</td><td>{html.escape(str(entry))}</td><td>—</td></tr>'
                    p += '</table>'

            # Driver standings
            driver_s = ldata.get("driver_standings")
            if driver_s:
                p += '<h3>Driver Championship</h3>'
                if isinstance(driver_s, dict):
                    sorted_d = sorted(driver_s.items(), key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0, reverse=True)
                    p += '<table><tr><th>#</th><th>Driver</th><th>Points</th></tr>'
                    for i, (name, pts) in enumerate(sorted_d, 1):
                        p += f'<tr><td>{i}</td><td>{html.escape(str(name))}</td><td><strong>{pts}</strong></td></tr>'
                    p += '</table>'
                elif isinstance(driver_s, list):
                    p += '<table><tr><th>#</th><th>Driver</th><th>Points</th></tr>'
                    for i, entry in enumerate(driver_s, 1):
                        if isinstance(entry, dict):
                            p += f'<tr><td>{i}</td><td>{html.escape(str(entry.get("driver", entry.get("name", ""))))}</td><td><strong>{entry.get("points", 0)}</strong></td></tr>'
                        else:
                            p += f'<tr><td>{i}</td><td>{html.escape(str(entry))}</td><td>—</td></tr>'
                    p += '</table>'

            p += '</div>'

    p += _footer("/standings")
    return p


def render_events(snap: Dict, refresh: int = 0) -> str:
    if snap.get("status") != "running":
        return render_dashboard(snap, refresh=refresh)

    p = _head("Events", refresh, "/events") + _nav("events")
    p += '<h1>📋 Event Log</h1>'

    events = snap.get("recent_events", [])
    if not events:
        p += '<div class="card"><p>No events recorded yet.</p></div>'
    else:
        p += '<div class="card event-log">'
        for evt in reversed(events):
            p += f'<div class="event-row">'
            p += f'<span class="badge badge-gray">{html.escape(evt.get("category", ""))}</span> '
            p += f'{html.escape(evt.get("desc", ""))} '
            p += f'<span style="color:#484f58">tick {evt.get("tick", 0)}</span>'
            p += '</div>'
        p += '</div>'

    p += _footer("/events")
    return p


def render_controls(snap: Dict, flash: str = "", refresh: int = 0) -> str:
    p = _head("Controls", refresh, "/controls") + _nav("ctrl")
    p += '<h1>🎮 Controls</h1>'

    if flash:
        p += f'<div class="flash">{html.escape(flash)}</div>'

    status = snap.get("status", "no_game")
    p += f'<div class="card"><h2>Status: {html.escape(status)}</h2>'
    if status == "running":
        p += f'<p>Tick: {snap.get("tick", 0)} · Mode: {_time_mode_badge(snap.get("time_mode", ""))}</p>'
    p += '</div>'

    # Time controls
    p += '<div class="card"><h2>⏱ Time</h2><div class="actions">'
    p += '<a class="btn btn-primary" href="/cmd?c=ftb_tick_step&n=1">▶ +1 Day</a>'
    p += '<a class="btn btn-primary" href="/cmd?c=ftb_tick_step&n=7">⏩ +7 Days</a>'
    p += '<a class="btn btn-primary" href="/cmd?c=ftb_tick_step&n=14">⏩ +14 Days</a>'
    p += '<a class="btn btn-primary" href="/cmd?c=ftb_tick_step&n=30">⏭ +30 Days</a>'
    p += '<a class="btn btn-danger" href="/cmd?c=ftb_stop_tick">⛔ Stop Batch</a>'
    p += '</div></div>'

    # Time mode
    p += '<div class="card"><h2>⚙️ Time Mode</h2><div class="actions">'
    p += '<a class="btn" href="/cmd?c=ftb_set_time_mode&mode=manual">Manual</a>'
    p += '<a class="btn" href="/cmd?c=ftb_set_time_mode&mode=auto_slow">Auto Slow (2s)</a>'
    p += '<a class="btn" href="/cmd?c=ftb_set_time_mode&mode=auto_fast">Auto Fast (0.5s)</a>'
    p += '</div></div>'

    # Delegation
    p += '<div class="card"><h2>🤖 Delegation</h2><div class="actions">'
    p += '<a class="btn btn-blue" href="/cmd?c=ftb_delegate">Enable Delegation</a>'
    p += '<a class="btn" href="/cmd?c=ftb_regain_control">Regain Control</a>'
    p += '</div></div>'

    # Save/Load
    p += '<div class="card"><h2>💾 Save / Load</h2><div class="actions">'
    p += '<a class="btn btn-primary" href="/cmd?c=ftb_save">Save Game</a>'
    p += '</div>'
    # List saves
    root = os.environ.get("RADIO_OS_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    saves_dir = os.path.join(root, "saves")
    if os.path.isdir(saves_dir):
        saves = sorted(
            [f for f in os.listdir(saves_dir) if f.endswith(".json")],
            key=lambda f: os.path.getmtime(os.path.join(saves_dir, f)),
            reverse=True,
        )
        if saves:
            p += '<h3 style="margin-top:10px">Available Saves</h3><table><tr><th>File</th><th>Modified</th><th></th></tr>'
            for f in saves[:15]:
                fp = os.path.join(saves_dir, f)
                mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(fp)))
                size_kb = os.path.getsize(fp) / 1024
                p += f'<tr><td>{html.escape(f)} <span style="color:#484f58">({size_kb:.0f}KB)</span></td>'
                p += f'<td>{mtime}</td>'
                p += f'<td><a class="btn" href="/cmd?c=ftb_load_save&path={html.escape(fp)}">Load</a></td></tr>'
            p += '</table>'
    p += '</div>'

    # Race
    if snap.get("race_day_active") or snap.get("status") == "running":
        p += '<div class="card"><h2>🏁 Race Day</h2><div class="actions">'
        p += '<a class="btn btn-primary" href="/cmd?c=ftb_start_race_day">Start Race Day</a>'
        p += '</div></div>'

    # Reset (dangerous)
    p += '<div class="card"><h2>⚠️ Danger Zone</h2><div class="actions">'
    p += '<a class="btn btn-danger" href="/cmd?c=ftb_reset" onclick="return confirm(\'Really reset? This clears the current game.\')">🗑 Reset Game</a>'
    p += '</div></div>'

    p += _footer("/controls")
    return p


# ═══════════════════════════════════════════════════════════════════
# HTTP Request Handler
# ═══════════════════════════════════════════════════════════════════

class FTBRemoteHandler(BaseHTTPRequestHandler):
    """Serves static HTML pages from game state, handles commands via GET query params."""

    def log_message(self, format, *args):
        """Suppress default stderr logging."""
        pass

    def _parse_refresh(self) -> int:
        """Parse ?r=<seconds> for auto-refresh."""
        qs = parse_qs(urlparse(self.path).query)
        try:
            return max(2, min(120, int(qs.get("r", [0])[0])))
        except (ValueError, IndexError):
            return 0

    def _send_html(self, content: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _send_json(self, data: Any, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str, indent=2).encode("utf-8"))

    def _redirect(self, url: str):
        self.send_response(303)
        self.send_header("Location", url)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)
        refresh = self._parse_refresh()

        try:
            # ── JSON API ──
            if path == "/api/state.json":
                snap = _safe_state_snapshot()
                self._send_json(snap)
                return

            if path == "/api/health":
                self._send_json({"status": "ok", "ts": time.time(), "mode": "http-only"})
                return

            # ── Command execution via GET (simple! just links!) ──
            if path == "/cmd":
                cmd = qs.get("c", [""])[0]
                if not cmd:
                    self._redirect("/controls")
                    return

                cmd_dict: Dict[str, Any] = {"cmd": cmd}

                # Gather extra params
                for key in ("n", "mode", "path", "sec"):
                    vals = qs.get(key)
                    if vals:
                        cmd_dict[key] = vals[0]

                # Convert numeric params
                if "n" in cmd_dict:
                    try:
                        cmd_dict["n"] = int(cmd_dict["n"])
                    except ValueError:
                        pass
                if "sec" in cmd_dict:
                    try:
                        cmd_dict["sec"] = float(cmd_dict["sec"])
                    except ValueError:
                        pass

                result = _send_cmd(cmd_dict)

                # For tick commands, add a small delay so state updates
                if "tick" in cmd:
                    time.sleep(0.3)

                # Redirect back to referrer or dashboard
                referer = self.headers.get("Referer", "/")
                # Strip existing flash params
                ref_parsed = urlparse(referer)
                ref_path = ref_parsed.path or "/"
                self._redirect(ref_path)
                return

            # ── HTML pages ──
            snap = _safe_state_snapshot()

            if path == "/":
                self._send_html(render_dashboard(snap, refresh=refresh))
            elif path == "/team":
                self._send_html(render_team(snap, refresh=refresh))
            elif path == "/standings":
                self._send_html(render_standings(snap, refresh=refresh))
            elif path == "/events":
                self._send_html(render_events(snap, refresh=refresh))
            elif path == "/controls":
                self._send_html(render_controls(snap, refresh=refresh))
            else:
                self._send_html(
                    _head("404") + f'<h1>404</h1><p>Page not found: {html.escape(path)}</p>'
                    f'<p><a href="/">← Dashboard</a></p>' + _footer(),
                    status=404,
                )

        except Exception as e:
            self._send_html(
                _head("Error") + f'<h1>Server Error</h1><pre>{html.escape(traceback.format_exc())}</pre>' + _footer(),
                status=500,
            )


# ═══════════════════════════════════════════════════════════════════
# Server launcher
# ═══════════════════════════════════════════════════════════════════

def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _get_tailscale_ip() -> str:
    """Try to detect Tailscale IP (100.x.x.x)."""
    try:
        import subprocess
        result = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    # Fallback: scan interfaces for 100.x.x.x
    try:
        import subprocess
        result = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=3)
        for line in result.stdout.split("\n"):
            line = line.strip()
            if "inet " in line:
                parts = line.split()
                idx = parts.index("inet") + 1 if "inet" in parts else -1
                if idx > 0 and idx < len(parts):
                    ip = parts[idx]
                    if ip.startswith("100."):
                        return ip
    except Exception:
        pass
    return ""


def start_remote_server(stop_event: threading.Event, shared_runtime: Dict[str, Any]):
    """
    Entry point — runs in a daemon thread started by bookmark.py.
    Pure HTTP, no dependencies beyond stdlib.
    """
    global _shared_runtime
    _shared_runtime = shared_runtime

    log_fn = shared_runtime.get("log", print)

    local_ip = _get_local_ip()
    ts_ip = _get_tailscale_ip()

    server = HTTPServer(("0.0.0.0", REMOTE_PORT), FTBRemoteHandler)
    server.timeout = 1.0  # So we can check stop_event

    log_fn("remote", f"╔══════════════════════════════════════════════════╗")
    log_fn("remote", f"║  📡 FTB Remote (HTTP-only) on port {REMOTE_PORT}           ║")
    log_fn("remote", f"║  Local:     http://127.0.0.1:{REMOTE_PORT}                ║")
    log_fn("remote", f"║  LAN:       http://{local_ip}:{REMOTE_PORT}{''.ljust(20 - len(local_ip))}║")
    if ts_ip:
        log_fn("remote", f"║  Tailscale: http://{ts_ip}:{REMOTE_PORT}{''.ljust(20 - len(ts_ip))}║")
    else:
        log_fn("remote", f"║  Tailscale: (not detected — install & login)     ║")
    log_fn("remote", f"║                                                  ║")
    log_fn("remote", f"║  No WebSocket needed! Just refresh the page.     ║")
    log_fn("remote", f"╚══════════════════════════════════════════════════╝")

    while not stop_event.is_set():
        server.handle_request()

    server.server_close()
    log_fn("remote", "Remote server stopped")


# ═══════════════════════════════════════════════════════════════════
# Standalone mode — for testing without bookmark.py
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"FTB Remote — standalone test mode on port {REMOTE_PORT}")
    print(f"No game controller attached — pages will show 'no game' state.")
    print(f"Open http://127.0.0.1:{REMOTE_PORT}")

    ts_ip = _get_tailscale_ip()
    if ts_ip:
        print(f"Tailscale: http://{ts_ip}:{REMOTE_PORT}")

    stop = threading.Event()
    try:
        start_remote_server(stop, {"log": lambda tag, msg: print(f"[{tag}] {msg}")})
    except KeyboardInterrupt:
        stop.set()
        print("\nStopped.")
