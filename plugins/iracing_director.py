"""
plugins/iracing_director.py
────────────────────────────────────────────────────────────────────────────
iRacing Broadcast Director — automatic camera control + web dashboard.

Exposes a FastAPI UI on http://localhost:7650 and writes camera switch
commands into `runtime["iracing_cam_cmd_q"]`, which `iracing_sdk.py`
drains each tick.

Scoring model (per car, every director tick):
  • Leader bonus:   25 pts if car is P1
  • Battle bonus:   up to 50 pts — max when gap < 0.3 s, decays linearly to 0 at 3 s
  • Incident decay: starts at 25 pts, halves every 30 s
  • Locked focus:   25 pts if user manually locked onto a car

Plugin contract:
  PLUGIN_NAME / PLUGIN_DESC are read by the shell.
  register_widgets(registry, runtime_stub) — called once at plugin load.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

# ── Plugin metadata ──────────────────────────────────────────────────────────
PLUGIN_NAME = "iRacing Director"
PLUGIN_DESC = "Automatic camera director with web dashboard (port 7650)."
IS_FEED     = False                      # meta/director plugin only

_PORT = 7650
_TICK = 3.0                              # seconds between camera switches
_BATTLE_THRESHOLD  = 3.0                 # gap (s) beyond which battle score = 0
_BATTLE_MAX_GAP    = 0.3                 # gap (s) that gives max battle score
_INCIDENT_DECAY_S  = 30.0                # half-life for incident score
_INCIDENT_INIT_PTS = 25.0


# ── HTML dashboard ────────────────────────────────────────────────────────────
_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="3">
<title>iRacing Director</title>
<style>
  :root { --bg:#0f1117; --card:#1a1d27; --hi:#00e5ff; --warn:#ffdd57; --danger:#ff4d4f; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:'Segoe UI',sans-serif; background:var(--bg); color:#ccc; padding:16px; }
  h1 { color:var(--hi); font-size:1.2rem; margin-bottom:12px; letter-spacing:.05em; }
  .row { display:flex; gap:12px; flex-wrap:wrap; }
  .card { background:var(--card); border-radius:8px; padding:12px; flex:1; min-width:260px; }
  .card h2 { font-size:.75rem; text-transform:uppercase; letter-spacing:.1em; color:#666; margin-bottom:8px; }
  table { width:100%; border-collapse:collapse; font-size:.8rem; }
  th { text-align:left; color:#555; font-weight:400; padding:2px 4px; }
  td { padding:3px 4px; }
  tr.focus td { color:var(--hi); font-weight:700; }
  tr.battle td { color:var(--warn); }
  tr:hover td { background:#252833; }
  .badge { display:inline-block; padding:1px 6px; border-radius:4px; font-size:.7rem; }
  .badge-auto { background:#1a3a1a; color:#4caf50; }
  .badge-lock { background:#3a1a1a; color:#ff4d4f; }
  form { display:inline; }
  button { background:#1e2435; border:1px solid #333; color:#aaa; padding:2px 10px;
           border-radius:4px; cursor:pointer; font-size:.75rem; }
  button:hover { background:#2d3451; color:var(--hi); }
  .status { font-size:.72rem; color:#555; margin-top:8px; }
</style>
</head>
<body>
<h1>&#127916; iRacing Director
  <span class="badge {mode_badge}">{mode_label}</span>
</h1>
<div class="row">

  <div class="card">
    <h2>Driver Scores</h2>
    <table>
      <tr><th>P</th><th>Car</th><th>Driver</th><th>Score</th><th>Gap</th><th></th></tr>
      {driver_rows}
    </table>
    <div class="status">Auto-refresh 3 s &bull; Click Focus to lock camera</div>
  </div>

  <div class="card" style="max-width:260px">
    <h2>Controls</h2>
    <form method="post" action="/mode/auto"><button>&#9654; Auto</button></form>
    &nbsp;
    <form method="post" action="/mode/lock"><button>&#128274; Hold</button></form>
    <br><br>
    <h2 style="margin-bottom:6px">Camera Group</h2>
    {group_buttons}
    <br><br>
    <h2 style="margin-bottom:6px">Battles</h2>
    <table>
      <tr><th>Car</th><th>vs</th><th>Gap</th></tr>
      {battle_rows}
    </table>
    <br>
    <h2 style="margin-bottom:6px">Recent Incidents</h2>
    <table>
      <tr><th>Car</th><th>Driver</th><th>Score</th></tr>
      {incident_rows}
    </table>
  </div>

</div>
</body>
</html>"""

# Preferred broadcast camera group names, in priority order
_PREFERRED_CAM_NAMES = ["TV Mixed", "TV2", "TV1", "Scenic", "TV"]


# ── BroadcastDirector ─────────────────────────────────────────────────────────

class BroadcastDirector:
    """Scores drivers each tick and issues camera switch commands."""

    def __init__(self, runtime: Dict[str, Any]) -> None:
        self._runtime = runtime
        self._mode: str = "auto"          # "auto" | "lock"
        self._locked_car: Optional[int] = None
        self._cam_group: int = 0          # 0 = auto-resolve each tick
        self._user_set_group: bool = False  # True once user picks manually
        self._incident_scores: Dict[int, Tuple[float, float]] = {}  # car_num → (pts, ts)
        self._current_cam_car: Optional[int] = None
        self._last_switch: float = 0.0
        self._battles: List[Tuple[int, int, float]] = []   # (car_a, car_b, gap)
        self._stop = threading.Event()

    # ── Public controls ────────────────────────────────────────────────────

    def set_mode(self, mode: str) -> None:
        self._mode = "lock" if mode == "lock" else "auto"
        if mode == "auto":
            self._user_set_group = False  # re-enable auto group resolution

    def set_camera_group(self, group: int) -> None:
        self._cam_group = max(1, int(group))
        self._user_set_group = True   # lock to this group until user clicks Auto

    def focus_car(self, car_num: int) -> None:
        self._locked_car = car_num
        self._mode = "lock"
        self._issue_cmd(car_num)

    def notify_incident(self, car_num: int, points: float) -> None:
        self._incident_scores[car_num] = (_INCIDENT_INIT_PTS, time.time())

    def stop(self) -> None:
        self._stop.set()

    # ── Director loop ──────────────────────────────────────────────────────

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                pass
            time.sleep(_TICK)

    def _tick(self) -> None:
        sdk = self._sdk()
        state: Dict[str, Any] = dict(getattr(sdk, "_live_state", {}) or {}) if sdk else {}
        drivers: List[Dict[str, Any]] = state.get("drivers", [])
        if not drivers:
            return

        # Auto-resolve preferred broadcast group unless user manually set one
        if not self._user_set_group:
            self._cam_group = self._resolve_cam_group(state.get("cam_groups", []))

        # Sort by position for battle detection
        sorted_d = sorted(drivers, key=lambda d: d.get("position", 999))

        # Detect battles (adjacent cars within threshold)
        self._battles = []
        for i in range(len(sorted_d) - 1):
            a, b = sorted_d[i], sorted_d[i + 1]
            gap = abs(float(a.get("gap", 99)) - float(b.get("gap", 99)))
            if gap < _BATTLE_THRESHOLD:
                self._battles.append((a["car_num"], b["car_num"], gap))

        if self._mode == "lock" and self._locked_car is not None:
            return  # user override — don't auto-switch

        # Score each car — exclude pace car, retired drivers, and cars idling in pits
        best_car = self._current_cam_car
        best_score = -1.0

        for d in drivers:
            cn = d.get("car_num")
            # Pace car
            if str(cn) == "0":
                continue
            if "pace" in str(d.get("name", "")).lower():
                continue
            # Retired / not in world (quit or towed to garage)
            if int(d.get("track_surface", 3)) == -1:
                continue
            # Parked in pit stall with no incident interest — skip
            if int(d.get("track_surface", 3)) == 1 and cn not in self._incident_scores:
                continue
            score = 0.0

            # Leader bonus
            if d.get("position", 99) == 1:
                score += 25.0

            # Battle bonus
            for a, b, gap in self._battles:
                if cn in (a, b):
                    norm = max(0.0, (_BATTLE_THRESHOLD - gap) / (_BATTLE_THRESHOLD - _BATTLE_MAX_GAP))
                    score += 50.0 * min(1.0, norm)
                    break

            # Incident decay
            if cn in self._incident_scores:
                pts, ts = self._incident_scores[cn]
                elapsed = time.time() - ts
                decayed = pts * (0.5 ** (elapsed / _INCIDENT_DECAY_S))
                if decayed < 0.5:
                    del self._incident_scores[cn]
                else:
                    self._incident_scores[cn] = (decayed, ts)
                    score += decayed

            if score > best_score:
                best_score = score
                best_car = cn

        if best_car is not None and best_car != self._current_cam_car:
            self._issue_cmd(best_car)

    def _resolve_cam_group(self, cam_groups: List[Dict]) -> int:
        """Pick TV Mixed, then TV2, then first available, then fallback to 1."""
        if not cam_groups:
            return self._cam_group or 1
        name_to_num = {g["name"].lower(): g["num"] for g in cam_groups if g.get("name")}
        for pref in _PREFERRED_CAM_NAMES:
            if pref.lower() in name_to_num:
                return name_to_num[pref.lower()]
        # Fallback: first group that isn't obviously an in-car/helmet cam
        cockpit_tokens = {"cockpit", "hood", "bumper", "nose", "helmet", "chase"}
        for g in cam_groups:
            if not any(t in g["name"].lower() for t in cockpit_tokens):
                return g["num"]
        return cam_groups[0]["num"] if cam_groups else 1

    @staticmethod
    def _sdk() -> Any:
        """Return the iracing_sdk module (loaded after us, so checked at call time)."""
        import sys as _sys
        return _sys.modules.get("iracing_sdk")

    def _issue_cmd(self, car_num: int) -> None:
        sdk = self._sdk()
        cam_q = getattr(sdk, "_cam_cmd_q", None) if sdk else None
        if cam_q is None:
            return
        try:
            cam_q.put_nowait({"car_num": car_num, "group": self._cam_group, "camera": 0})
            self._current_cam_car = car_num
            self._last_switch = time.time()
        except queue.Full:
            pass

    # ── Dashboard data ─────────────────────────────────────────────────────

    def render_html(self) -> str:
        sdk = self._sdk()
        state: Dict[str, Any] = dict(getattr(sdk, "_live_state", {}) or {}) if sdk else {}
        drivers = sorted(state.get("drivers", []), key=lambda d: d.get("position", 999))

        focus_cars = {self._current_cam_car} if self._current_cam_car else set()
        battle_cars = {cn for a, b, _ in self._battles for cn in (a, b)}

        # Driver rows
        rows = []
        inc_rows = []
        for d in drivers:
            cn    = d["car_num"]
            is_f  = cn in focus_cars
            is_b  = cn in battle_cars
            cls   = "focus" if is_f else ("battle" if is_b else "")
            score = self._compute_score(d)
            gap   = f"{d.get('gap', 0):.2f}s" if d.get("position", 1) > 1 else "—"
            focus_btn = (f'<form method="post" action="/focus/{cn}">'
                         f'<button>Focus</button></form>')
            rows.append(
                f'<tr class="{cls}"><td>{d.get("position","")}</td>'
                f'<td>{cn}</td><td>{d.get("name","")[:18]}</td>'
                f'<td>{score:.0f}</td><td>{gap}</td>'
                f'<td>{focus_btn}</td></tr>'
            )
            if cn in self._incident_scores:
                pts = self._incident_scores[cn][0]
                inc_rows.append(
                    f'<tr><td>{cn}</td><td>{d.get("name","")[:14]}</td>'
                    f'<td>{pts:.0f}</td></tr>'
                )

        battle_rows = [
            f'<tr><td>{a}</td><td>{b}</td>'
            f'<td>{g:.2f}s</td></tr>'
            for a, b, g in self._battles[:5]
        ] or ["<tr><td colspan=3>—</td></tr>"]

        group_btns_parts = []
        cam_groups = state.get("cam_groups", [])
        if cam_groups:
            # Show named buttons from live iRacing data
            for g in cam_groups:
                active = " style=\"color:#00e5ff;border-color:#00e5ff;\"" if g["num"] == self._cam_group else ""
                group_btns_parts.append(
                    f'<form method="post" action="/group/{g["num"]}" style="display:inline">'
                    f'<button{active}>{g["name"]}</button></form>'
                )
        else:
            # Fallback: generic numbered buttons
            group_btns_parts = [
                f'<form method="post" action="/group/{g}" style="display:inline">'
                f'<button>Grp {g}</button></form>'
                for g in range(1, 8)
            ]
        group_btns = " ".join(group_btns_parts)

        subs = {
            "{mode_label}":    "AUTO" if self._mode == "auto" else "LOCKED",
            "{mode_badge}":    "badge-auto" if self._mode == "auto" else "badge-lock",
            "{driver_rows}":   "\n".join(rows) or "<tr><td colspan=6>No data</td></tr>",
            "{battle_rows}":   "\n".join(battle_rows),
            "{incident_rows}": "\n".join(inc_rows) or "<tr><td colspan=3>—</td></tr>",
            "{group_buttons}": group_btns,
        }
        html = _HTML
        for placeholder, value in subs.items():
            html = html.replace(placeholder, value)
        return html

    def _compute_score(self, d: Dict[str, Any]) -> float:
        cn = d["car_num"]
        score = 0.0
        if d.get("position", 99) == 1:
            score += 25.0
        for a, b, gap in self._battles:
            if cn in (a, b):
                norm = max(0.0, (_BATTLE_THRESHOLD - gap) / (_BATTLE_THRESHOLD - _BATTLE_MAX_GAP))
                score += 50.0 * min(1.0, norm)
                break
        if cn in self._incident_scores:
            score += self._incident_scores[cn][0]
        if cn == self._locked_car and self._mode == "lock":
            score += 25.0
        return score


# ── Web server ─────────────────────────────────────────────────────────────────

def _start_web_server(director: BroadcastDirector) -> None:
    try:
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse, RedirectResponse
        import uvicorn
    except ImportError:
        print("[iracing_director] fastapi/uvicorn not installed — web UI disabled")
        return

    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(director.render_html())

    @app.post("/mode/{mode}")
    async def set_mode(mode: str):
        director.set_mode(mode)
        return RedirectResponse("/", status_code=303)

    @app.post("/focus/{car_num}")
    async def focus(car_num: int):
        director.focus_car(car_num)
        return RedirectResponse("/", status_code=303)

    @app.post("/group/{group}")
    async def set_group(group: int):
        director.set_camera_group(group)
        return RedirectResponse("/", status_code=303)

    config = uvicorn.Config(app, host="0.0.0.0", port=_PORT,
                            log_level="error", access_log=False)
    server = uvicorn.Server(config)
    server.run()


# ── Plugin entry point ──────────────────────────────────────────────────────

def register_widgets(registry: Any, runtime_stub: Any) -> None:
    """Called once by the shell/runtime when the plugin is loaded."""
    # Initialise the module-level camera command queue in iracing_sdk.
    # iracing_sdk may not be loaded yet (director loads first alphabetically),
    # so we set it after a short delay in a thread, or set it lazily via a
    # module-level sentinel.  Simpler: just import queue here and patch it
    # once iracing_sdk is available (done in director loop at first tick).
    director = BroadcastDirector({})

    def _patch_sdk_queue() -> None:
        """Wait until iracing_sdk is loaded, then attach the cam queue to it."""
        import sys as _sys
        for _ in range(60):  # wait up to 60 s
            sdk = _sys.modules.get("iracing_sdk")
            if sdk is not None:
                if getattr(sdk, "_cam_cmd_q", None) is None:
                    sdk._cam_cmd_q = queue.Queue(maxsize=8)
                break
            time.sleep(1.0)

    threading.Thread(target=_patch_sdk_queue, name="iracing-sdk-patch", daemon=True).start()

    # Director loop thread
    t_dir = threading.Thread(target=director.run, name="iracing-director", daemon=True)
    t_dir.start()

    # Web server thread
    t_web = threading.Thread(
        target=_start_web_server, args=(director,),
        name="iracing-director-web", daemon=True
    )
    t_web.start()

    try:
        registry.register_link("iRacing Director", f"http://localhost:{_PORT}")
    except Exception:
        pass  # registry may not support links in all shell versions

    print(f"[iracing_director] Director started — UI at http://localhost:{_PORT}")
