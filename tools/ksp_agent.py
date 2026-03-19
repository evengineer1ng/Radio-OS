"""
OpenClaw — KSP Autonomous AI Pilot
====================================
An LLM-driven autopilot for Kerbal Space Program via the kRPC mod.
The agent reads live telemetry, reasons about the next action using an LLM,
and executes maneuvers via kRPC.  It also pushes events into the Radio OS
ksp_sdk feed so the commentary engine can narrate every decision.

Architecture
------------
  KSP                kRPC server (localhost:50000)
   ↑                       ↓
ksp_agent.py   →   KSPConnection  →  reads telemetry
                           ↓
                   MissionPlanner  →  tracks phase/objectives
                           ↓
                     LLMPilot     →  decides next action via LLM
                           ↓
              execute action via kRPC + push event to ksp_sdk._agent_event_q
                           ↓
                     ksp_meta.py  →  generates spoken commentary

USAGE
  python tools/ksp_agent.py [--host localhost] [--port 50000]
                             [--model qwen3:8b]
                             [--mission "insert into 80km orbit"]
                             [--ollama-url http://localhost:11434]

REQUIREMENTS
  pip install krpc
  KSP with kRPC mod installed and server running.
"""

from __future__ import annotations

import argparse
import enum
import glob
import json
import math
import os
import queue
import re
import sys
import time
import threading
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Add project root to path so we can import ksp_sdk event bridge
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    import plugins.ksp_sdk as _ksp_sdk_mod
    _AGENT_EVENT_Q = _ksp_sdk_mod._agent_event_q
except ImportError:
    # Running standalone without Radio OS — create a local queue
    _AGENT_EVENT_Q: queue.Queue = queue.Queue()

# ---------------------------------------------------------------------------
# kRPC import
# ---------------------------------------------------------------------------
try:
    import krpc                # type: ignore
    _HAS_KRPC = True
except ImportError:
    _HAS_KRPC = False
    print("[openclaw] krpc package not installed. pip install krpc", file=sys.stderr)


# ---------------------------------------------------------------------------
# Telemetry snapshot (lean — only what the agent needs)
# ---------------------------------------------------------------------------

@dataclass
class AgentTelemetry:
    vessel_name:      str   = "Unknown"
    phase:            str   = "pre_launch"     # internal mission phase
    altitude_m:       float = 0.0
    apoapsis_m:       float = 0.0
    periapsis_m:      float = 0.0
    speed_ms:         float = 0.0
    vertical_speed:   float = 0.0
    surface_speed:    float = 0.0
    orbital_speed:    float = 0.0
    throttle:         float = 0.0
    sas_enabled:      bool  = False
    autopilot_mode:   str   = "StabilityAssist"
    gear_deployed:    bool  = False
    parachute_armed:  bool  = False
    fuel_pct:         float = 1.0          # main propellant fraction
    mono_pct:         float = 1.0
    electric_pct:     float = 1.0
    stage:            int   = 0
    in_atmosphere:    bool  = True
    landed:           bool  = False
    g_force:          float = 1.0
    has_maneuver:     bool  = False
    maneuver_dv:      float = 0.0          # delta-v remaining for next node
    maneuver_time:    float = 0.0          # seconds until next node execution
    target_dist_m:    float = -1.0
    ut:               float = 0.0
    body_name:        str   = "Kerbin"
    atm_depth_m:      float = 70_000.0     # atmosphere ceiling in metres


# ---------------------------------------------------------------------------
# Game-scene enum
# ---------------------------------------------------------------------------

class GameScene(enum.Enum):
    UNKNOWN      = "unknown"
    FLIGHT       = "flight"
    SPACE_CENTER = "space_center"
    EDITOR_VAB   = "editor_vab"
    EDITOR_SPH   = "editor_sph"
    LOADING      = "loading"


# ---------------------------------------------------------------------------
# Saved-craft descriptor
# ---------------------------------------------------------------------------

@dataclass
class CraftInfo:
    name:       str        # ship display name (from 'ship = ...' line)
    key:        str        # filename without .craft  (what kRPC needs)
    save:       str        # save-game folder name
    path:       str        # full .craft file path
    craft_type: str = "VAB"  # VAB or SPH


# ---------------------------------------------------------------------------
# kRPC connection wrapper
# ---------------------------------------------------------------------------

class KSPConnection:
    """
    Thin wrapper around a live kRPC connection.
    Provides read (telemetry) and write (control) methods.
    """

    def __init__(self, host: str = "localhost",
                 rpc_port: int = 50000, stream_port: int = 50001):
        self._host   = host
        self._rpc    = rpc_port
        self._stm    = stream_port
        self._conn   = None
        self._vessel = None
        self._sc     = None

    def connect(self) -> bool:
        """Establish the kRPC socket. Does NOT require a vessel to be in flight."""
        if not _HAS_KRPC:
            return False
        try:
            self._conn = krpc.connect(name="OpenClaw",
                                      address=self._host,
                                      rpc_port=self._rpc,
                                      stream_port=self._stm)
            self._sc   = self._conn.space_center
            # Don't touch active_vessel here — it may not exist yet
            return True
        except Exception as exc:
            print(f"[openclaw] socket connect failed: {exc}", file=sys.stderr)
            self._conn = None
            return False

    def has_active_vessel(self) -> bool:
        """Return True when KSP has a vessel loaded in a flight scene."""
        if not self._conn:
            return False
        try:
            _ = self._sc.active_vessel
            return True
        except Exception:
            return False

    @property
    def connected(self) -> bool:
        return self._conn is not None

    def disconnect(self) -> None:
        try:
            if self._conn:
                self._conn.close()
        except Exception:
            pass
        self._conn = None

    # ---- Telemetry ---------------------------------------------------------

    def read_telemetry(self) -> Optional[AgentTelemetry]:
        if not self._conn:
            return None
        try:
            vessel = self._sc.active_vessel
            self._vessel = vessel
            flight   = vessel.flight(vessel.orbit.body.reference_frame)
            orbit    = vessel.orbit
            control  = vessel.control
            ap       = vessel.auto_pilot

            situation = str(vessel.situation).split(".")[-1].upper()
            phase     = _situation_to_phase(situation)

            # Propellant
            fuel_pct  = _res_fraction(vessel, ["LiquidFuel","Oxidizer","SolidFuel","Xenon"])
            mono_pct  = _res_fraction(vessel, ["MonoPropellant"])
            elec_pct  = _res_fraction(vessel, ["ElectricCharge"])

            # Maneuver node
            nodes     = control.nodes
            has_node  = len(nodes) > 0
            dv_rem    = float(nodes[0].remaining_delta_v) if nodes else 0.0
            node_ut   = float(nodes[0].ut) if nodes else 0.0
            node_eta  = float(node_ut - self._sc.ut) if has_node else 0.0

            # Target
            target_dist = -1.0
            try:
                tgt = self._sc.target_vessel
                if tgt:
                    tv_pos = vessel.position(vessel.surface_reference_frame)
                    tg_pos = tgt.position(vessel.surface_reference_frame)
                    dd = tuple(a-b for a, b in zip(tv_pos, tg_pos))
                    target_dist = math.sqrt(sum(d*d for d in dd))
            except Exception:
                pass

            # Autopilot mode
            try:
                ap_mode = str(ap.sas_mode).split(".")[-1]
            except Exception:
                ap_mode = "StabilityAssist"

            t = AgentTelemetry(
                vessel_name     = vessel.name,
                phase           = phase,
                altitude_m      = float(flight.mean_altitude),
                apoapsis_m      = float(orbit.apoapsis_altitude),
                periapsis_m     = float(orbit.periapsis_altitude),
                speed_ms        = float(flight.speed),
                vertical_speed  = float(flight.vertical_speed),
                surface_speed   = float(flight.speed),
                orbital_speed   = float(orbit.speed),
                throttle        = float(control.throttle),
                sas_enabled     = bool(control.sas),
                autopilot_mode  = ap_mode,
                gear_deployed   = bool(control.gear),
                fuel_pct        = fuel_pct,
                mono_pct        = mono_pct,
                electric_pct    = elec_pct,
                stage           = int(control.current_stage),
                in_atmosphere   = float(flight.mean_altitude) < float(orbit.body.atmosphere_depth),
                landed          = situation in ("LANDED", "SPLASHED"),
                g_force         = float(flight.g_force),
                has_maneuver    = has_node,
                maneuver_dv     = dv_rem,
                maneuver_time   = node_eta,
                target_dist_m   = target_dist,
                ut              = float(self._sc.ut),
                body_name       = orbit.body.name,
                atm_depth_m     = float(orbit.body.atmosphere_depth),
            )
            return t
        except Exception as exc:
            print(f"[openclaw] telemetry read error: {exc}", file=sys.stderr)
            return None

    # ---- Control -----------------------------------------------------------

    def set_throttle(self, value: float) -> None:
        value = max(0.0, min(1.0, value))
        self._vessel.control.throttle = value

    def activate_next_stage(self) -> None:
        self._vessel.control.activate_next_stage()

    def toggle_sas(self, enabled: bool) -> None:
        self._vessel.control.sas = enabled

    def toggle_rcs(self, enabled: bool) -> None:
        self._vessel.control.rcs = enabled

    def toggle_gear(self, deployed: bool) -> None:
        self._vessel.control.gear = deployed

    def deploy_parachutes(self) -> None:
        for p in self._vessel.parts.parachutes:
            p.deploy()

    def set_sas_mode(self, mode: str) -> None:
        """mode: StabilityAssist, Prograde, Retrograde, Normal, Radial, etc."""
        try:
            ap = self._vessel.auto_pilot
            modes_map = {
                "stabilityassist": krpc.client.services.space_center.SASMode.stability_assist,
                "prograde":        krpc.client.services.space_center.SASMode.prograde,
                "retrograde":      krpc.client.services.space_center.SASMode.retrograde,
                "normal":          krpc.client.services.space_center.SASMode.normal,
                "antinormal":      krpc.client.services.space_center.SASMode.anti_normal,
                "radialin":        krpc.client.services.space_center.SASMode.radial,
                "radialout":       krpc.client.services.space_center.SASMode.anti_radial,
                "target":          krpc.client.services.space_center.SASMode.target,
                "maneuver":        krpc.client.services.space_center.SASMode.maneuver,
            }
            m = modes_map.get(mode.lower().replace(" ", ""))
            if m:
                ap.sas = True
                ap.sas_mode = m
        except Exception as exc:
            print(f"[openclaw] set_sas_mode error: {exc}", file=sys.stderr)

    def add_maneuver_node(self, prograde_dv: float, eta_seconds: float) -> None:
        """Add a simple prograde/retrograde maneuver node."""
        ut = self._sc.ut + eta_seconds
        self._vessel.control.add_node(ut, prograde=prograde_dv)

    def warp_to(self, ut: float) -> None:
        """Time-warp to a specific universal time."""
        try:
            self._sc.warp_to(ut)
        except Exception as exc:
            print(f"[openclaw] warp_to error: {exc}", file=sys.stderr)

    # ---- Scene / lifecycle -------------------------------------------------

    def get_scene(self) -> GameScene:
        """Return the current KSP game scene via conn.krpc.current_game_scene."""
        if not self._conn:
            return GameScene.UNKNOWN
        try:
            raw = str(self._conn.krpc.current_game_scene).split(".")[-1].lower()
            mapping = {
                "flight":       GameScene.FLIGHT,
                "space_center": GameScene.SPACE_CENTER,
                "editor_vab":   GameScene.EDITOR_VAB,
                "editor_sph":   GameScene.EDITOR_SPH,
            }
            return mapping.get(raw, GameScene.UNKNOWN)
        except Exception:
            return GameScene.UNKNOWN

    def launch_from_vab(self, craft_key: str,
                        launch_site: str = "LaunchPad") -> bool:
        """Launch a saved VAB vessel by its craft key (filename without .craft)."""
        try:
            self._sc.launch_vessel_from_vab(craft_key, launch_site)
            return True
        except Exception as exc:
            print(f"[openclaw] launch_from_vab failed: {exc}", file=sys.stderr)
            return False

    def launch_from_sph(self, craft_key: str,
                        launch_site: str = "Runway") -> bool:
        """Launch a saved SPH vessel by its craft key."""
        try:
            self._sc.launch_vessel_from_sph(craft_key, launch_site)
            return True
        except Exception as exc:
            print(f"[openclaw] launch_from_sph failed: {exc}", file=sys.stderr)
            return False


def _res_fraction(vessel, names: List[str]) -> float:
    total = 0.0; current = 0.0
    try:
        for r in vessel.resources.all:
            if r.resource.name in names and r.max > 0:
                total += r.max; current += r.amount
    except Exception:
        return 1.0
    return (current / total) if total > 0 else 1.0


def _situation_to_phase(situation: str) -> str:
    return {
        "PRE_LAUNCH": "pre_launch", "LAUNCHING": "ascent",
        "FLYING": "ascent",         "SUB_ORBITAL": "sub_orbital",
        "ORBITING": "orbit",         "ESCAPING": "escape",
        "DOCKED": "docked",          "LANDED": "landed",
        "SPLASHED": "splashed",
    }.get(situation, "unknown")


# ---------------------------------------------------------------------------
# Mission planner — tracks objectives and phase
# ---------------------------------------------------------------------------

@dataclass
class MissionObjective:
    description: str
    achieved:    bool = False
    notes:       str  = ""


class MissionPlanner:
    """
    Maintains a list of mission objectives and tracks progress.
    The LLM pilot uses this as context for decisions.
    """

    def __init__(self, mission_description: str):
        self.description   = mission_description
        self.objectives:   List[MissionObjective] = []
        self.phase_history: List[str] = []
        self._prev_phase   = ""

    def update(self, telemetry: AgentTelemetry) -> None:
        if telemetry.phase != self._prev_phase:
            self.phase_history.append(
                f"T+{int(telemetry.ut % 86400)}: entered {telemetry.phase}"
            )
            self._prev_phase = telemetry.phase
            if len(self.phase_history) > 20:
                self.phase_history = self.phase_history[-20:]

    def status_text(self) -> str:
        lines = [f"Mission: {self.description}"]
        if self.phase_history:
            lines.append("Phase history: " + ", ".join(self.phase_history[-5:]))
        pending = [o for o in self.objectives if not o.achieved]
        done    = [o for o in self.objectives if o.achieved]
        if done:
            lines.append("Completed: " + "; ".join(o.description for o in done))
        if pending:
            lines.append("Pending: " + "; ".join(o.description for o in pending))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM client (Ollama REST)
# ---------------------------------------------------------------------------

class OllamaClient:
    """Minimal Ollama REST client — no extra dependencies needed."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen3:8b"):
        self._url   = base_url.rstrip("/")
        self._model = model

    def chat(self, system: str, user: str,
             max_tokens: int = 256, temperature: float = 0.3) -> str:
        payload = json.dumps({
            "model":   self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            "stream": False,
        }).encode()

        req = urllib.request.Request(
            f"{self._url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read())
                raw  = body.get("message", {}).get("content", "")
                # Strip think blocks
                raw  = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
                return raw
        except urllib.error.URLError as exc:
            print(f"[openclaw] LLM request failed: {exc}", file=sys.stderr)
            return ""
        except Exception as exc:
            print(f"[openclaw] LLM error: {exc}", file=sys.stderr)
            return ""


# ---------------------------------------------------------------------------
# LLM Pilot — core decision engine
# ---------------------------------------------------------------------------

_SYSTEM_PILOT = """/no_think
You are OpenClaw, an autonomous AI pilot for Kerbal Space Program.
Your job is to fly the rocket efficiently and safely toward the mission goal.

You MUST respond with valid JSON only — no other text before or after it.

Response format:
{{
  "action": "<action_name>",
  "params": {{}},
  "reason": "<1 sentence explanation>",
  "next_objective": "<what we need to do after this>"
}}

Available actions and their params:
- "set_throttle"       → params: {{"value": 0.0–1.0}}
- "activate_stage"     → params: {{}}  (stage when needed)
- "set_sas_mode"       → params: {{"mode": "prograde|retrograde|normal|maneuver|stabilityassist"}}
- "toggle_sas"         → params: {{"enabled": true/false}}
- "toggle_rcs"         → params: {{"enabled": true/false}}
- "deploy_parachutes"  → params: {{}}  (only in atmosphere, below 5km)
- "toggle_gear"        → params: {{"deployed": true/false}}
- "add_maneuver_node"  → params: {{"prograde_dv": <m/s>, "eta_seconds": <seconds from now>}}
- "warp_to_maneuver"   → params: {{}}  (warp to existing maneuver node - 30s before)
- "wait"               → params: {{"seconds": <1–30>}}  (do nothing for N seconds)

Decision guidelines:
- During ascent: set prograde SAS, throttle 1.0, stage when fuel depleted
- At apoapsis ~70km: cut throttle, coast, then circularize
- In orbit: use prograde/retrograde burns to adjust orbit
- For reentry: point retrograde, throttle 0, deploy chutes below 3km
- NEVER leave throttle at 1.0 while coasting in orbit
- NEVER deploy parachutes above 10km altitude
- Stage only when rocket stage fuel is exhausted (fuel_pct < 0.05)
"""


@dataclass
class PilotAction:
    action:         str
    params:         Dict[str, Any]
    reason:         str
    next_objective: str


class LLMPilot:
    """
    Uses an LLM to decide the next autopilot action.
    Throttles decision rate and refuses unsafe commands.
    """

    def __init__(self, llm: OllamaClient, mission: MissionPlanner,
                 decision_interval_sec: float = 3.0):
        self._llm          = llm
        self._mission      = mission
        self._interval     = decision_interval_sec
        self._last_decided = 0.0
        self._decision_log: List[Dict[str, Any]] = []

    def should_decide(self) -> bool:
        return (time.time() - self._last_decided) >= self._interval

    def decide(self, telem: AgentTelemetry) -> Optional[PilotAction]:
        if not self.should_decide():
            return None
        self._last_decided = time.time()

        telem_text = _format_telemetry(telem)
        mission_text = self._mission.status_text()

        user_prompt = (
            f"Current telemetry:\n{telem_text}\n\n"
            f"{mission_text}\n\n"
            "What is the single best action to take RIGHT NOW? "
            "Respond ONLY with the JSON action and nothing else."
        )

        raw = self._llm.chat(
            system=_SYSTEM_PILOT,
            user=user_prompt,
            max_tokens=200,
            temperature=0.2,   # low temp for reliable JSON
        )

        action = _parse_action(raw)
        if action is None:
            return None

        # Safety gate — refuse dangerous commands in wrong context
        action = _safety_check(action, telem)
        if action is None:
            return None

        self._decision_log.append({
            "ts":     time.time(),
            "action": action.action,
            "reason": action.reason,
            "telem":  {"alt": telem.altitude_m, "phase": telem.phase},
        })
        if len(self._decision_log) > 100:
            self._decision_log = self._decision_log[-100:]

        return action


def _format_telemetry(t: AgentTelemetry) -> str:
    alt_km   = t.altitude_m / 1_000
    apo_km   = t.apoapsis_m / 1_000
    peri_km  = t.periapsis_m / 1_000
    atm_km   = t.atm_depth_m / 1_000
    in_space = not t.in_atmosphere
    return (
        f"Vessel: {t.vessel_name} | Phase: {t.phase} | Body: {t.body_name}\n"
        f"Altitude: {alt_km:.1f} km (atm ends {atm_km:.0f} km) | "
        f"In atmosphere: {t.in_atmosphere} | Landed: {t.landed}\n"
        f"Apoapsis: {apo_km:.1f} km | Periapsis: {peri_km:.1f} km\n"
        f"Speed: {t.speed_ms:.0f} m/s (surface) | {t.orbital_speed:.0f} m/s (orbital)\n"
        f"Vertical speed: {t.vertical_speed:.0f} m/s | G-force: {t.g_force:.2f}g\n"
        f"Throttle: {t.throttle:.2f} | SAS: {t.sas_enabled} ({t.autopilot_mode})\n"
        f"Stage: {t.stage} | Fuel: {t.fuel_pct*100:.1f}% | "
        f"Mono: {t.mono_pct*100:.1f}% | Electric: {t.electric_pct*100:.1f}%\n"
        f"Maneuver node: {t.has_maneuver} (dv={t.maneuver_dv:.1f} m/s, "
        f"eta={t.maneuver_time:.0f}s)\n"
        f"Target: {'none' if t.target_dist_m < 0 else f'{t.target_dist_m/1000:.2f} km'}"
    )


def _parse_action(raw: str) -> Optional[PilotAction]:
    """Extract and validate a JSON action from LLM output."""
    if not raw:
        return None
    try:
        # Find JSON block
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        obj = json.loads(m.group(0))
        return PilotAction(
            action         = str(obj.get("action", "wait")),
            params         = dict(obj.get("params", {})),
            reason         = str(obj.get("reason", "")),
            next_objective = str(obj.get("next_objective", "")),
        )
    except (json.JSONDecodeError, Exception):
        return None


_VALID_ACTIONS = {
    "set_throttle", "activate_stage", "set_sas_mode", "toggle_sas",
    "toggle_rcs", "deploy_parachutes", "toggle_gear", "add_maneuver_node",
    "warp_to_maneuver", "wait",
}


def _safety_check(action: PilotAction, telem: AgentTelemetry) -> Optional[PilotAction]:
    """Block unsafe actions; return None to skip, or adjusted action to proceed."""
    a = action.action

    if a not in _VALID_ACTIONS:
        print(f"[openclaw] blocked unknown action: {a}", file=sys.stderr)
        return None

    # Never deploy chutes high up
    if a == "deploy_parachutes" and telem.altitude_m > 15_000:
        print(f"[openclaw] blocked deploy_parachutes at {telem.altitude_m:.0f}m", file=sys.stderr)
        return PilotAction("wait", {"seconds": 5},
                           "too high for parachutes — waiting", "continue descent")

    # Never full throttle in orbit without a maneuver
    if a == "set_throttle":
        val = float(action.params.get("value", 0))
        if val > 0.5 and not telem.in_atmosphere and not telem.has_maneuver:
            print(f"[openclaw] throttled down — no maneuver node in orbit", file=sys.stderr)
            action.params["value"] = 0.0
            action.reason = "no maneuver node active — holding throttle at 0"

    # Staging when fuel isn't exhausted is suspicious
    if a == "activate_stage" and telem.fuel_pct > 0.10:
        print(f"[openclaw] blocked premature staging (fuel={telem.fuel_pct*100:.1f}%)",
              file=sys.stderr)
        return PilotAction("wait", {"seconds": 2},
                           "fuel not depleted — holding stage", "wait for stage to burn out")

    return action


# ---------------------------------------------------------------------------
# Action executor
# ---------------------------------------------------------------------------

def execute_action(conn: KSPConnection, action: PilotAction,
                   telem: AgentTelemetry) -> None:
    """Execute a PilotAction via kRPC and push an event to Radio OS."""
    a = action.action

    try:
        if a == "set_throttle":
            conn.set_throttle(float(action.params.get("value", 0)))

        elif a == "activate_stage":
            conn.activate_next_stage()
            push_event({
                "type":      "stage_separation",
                "vessel":    telem.vessel_name,
                "stage":     telem.stage,
                "altitude_m":telem.altitude_m,
                "speed_ms":  telem.speed_ms,
                "source":    "agent",
            })

        elif a == "set_sas_mode":
            conn.set_sas_mode(str(action.params.get("mode", "StabilityAssist")))

        elif a == "toggle_sas":
            conn.toggle_sas(bool(action.params.get("enabled", True)))

        elif a == "toggle_rcs":
            conn.toggle_rcs(bool(action.params.get("enabled", True)))

        elif a == "deploy_parachutes":
            conn.deploy_parachutes()

        elif a == "toggle_gear":
            conn.toggle_gear(bool(action.params.get("deployed", True)))

        elif a == "add_maneuver_node":
            dv  = float(action.params.get("prograde_dv", 0))
            eta = float(action.params.get("eta_seconds", 60))
            conn.add_maneuver_node(dv, eta)

        elif a == "warp_to_maneuver":
            if telem.has_maneuver and telem.maneuver_time > 35:
                conn.warp_to(telem.ut + telem.maneuver_time - 30)

        elif a == "wait":
            secs = float(action.params.get("seconds", 2))
            time.sleep(max(0.1, min(secs, 30)))
            return   # don't push a Radio OS event for wait

    except Exception as exc:
        print(f"[openclaw] execute_action error for '{a}': {exc}", file=sys.stderr)
        return

    # Push an agent_action event to Radio OS for commentary
    push_event({
        "type":    "agent_action",
        "action":  a,
        "params":  action.params,
        "reason":  action.reason,
        "vessel":  telem.vessel_name,
        "altitude_m": telem.altitude_m,
        "phase":   telem.phase,
    })


def push_event(data: Dict[str, Any]) -> None:
    """Push a telemetry event into the Radio OS ksp_sdk bridge queue."""
    try:
        _AGENT_EVENT_Q.put_nowait(data)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Craft manager — discovers + selects + launches saved vessels
# ---------------------------------------------------------------------------

def _read_craft_name(path: str) -> Optional[str]:
    """Extract the 'ship = ...' display name from a .craft file."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if line.lower().startswith("ship ="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


class CraftManager:
    """
    Scans KSP save directories for .craft files, asks the LLM to pick
    the best vessel for the current mission, and launches it via kRPC.
    """

    def __init__(self, ksp_dir: str, conn: KSPConnection, llm: OllamaClient):
        self._ksp_dir = ksp_dir
        self._conn    = conn
        self._llm     = llm

    def list_craft(self) -> List[CraftInfo]:
        """Return all .craft files found across every save game."""
        results: List[CraftInfo] = []
        saves_dir = os.path.join(self._ksp_dir, "saves")
        if not os.path.isdir(saves_dir):
            return results
        for save_name in sorted(os.listdir(saves_dir)):
            for craft_type in ("VAB", "SPH"):
                craft_dir = os.path.join(saves_dir, save_name, "Ships", craft_type)
                if not os.path.isdir(craft_dir):
                    continue
                for fname in sorted(os.listdir(craft_dir)):
                    if not fname.endswith(".craft"):
                        continue
                    path = os.path.join(craft_dir, fname)
                    key  = fname[:-6]          # strip .craft
                    name = _read_craft_name(path) or key
                    results.append(CraftInfo(
                        name=name, key=key,
                        save=save_name, path=path,
                        craft_type=craft_type,
                    ))
        return results

    def select_for_mission(self, mission: str,
                            craft: List[CraftInfo]) -> Optional[CraftInfo]:
        """Use the LLM to pick the most suitable craft for the mission."""
        if not craft:
            return None
        if len(craft) == 1:
            return craft[0]
        listing = "\n".join(
            f"{i+1}. [{c.craft_type}] {c.name}  (save: {c.save})"
            for i, c in enumerate(craft)
        )
        raw = self._llm.chat(
            system=(
                "You are a KSP mission planner. "
                "Pick the vessel that best fits the mission. "
                "Reply with ONLY the vessel number — no other text."
            ),
            user=(
                f"Mission: {mission}\n\n"
                f"Available vessels:\n{listing}\n\n"
                "Which vessel number should we fly?"
            ),
            max_tokens=8,
            temperature=0.1,
        )
        try:
            idx = int(re.search(r"\d+", raw).group(0)) - 1
            if 0 <= idx < len(craft):
                return craft[idx]
        except Exception:
            pass
        return craft[0]   # fallback: first available

    def launch(self, craft: CraftInfo) -> bool:
        print(f"[openclaw] Launching '{craft.name}' ({craft.craft_type}) "
              f"from save '{craft.save}'...")
        if craft.craft_type == "SPH":
            return self._conn.launch_from_sph(craft.key)
        return self._conn.launch_from_vab(craft.key)


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

class OpenClawAgent:
    """
    Top-level orchestrator.

    Outer game loop
        while running:
            _handle_space_center()  ← scan saves, pick best craft, launch it
            _flight_loop()          ← fly until vessel is gone
            if not --loop: stop
    """

    def __init__(self, args: argparse.Namespace):
        self._args       = args
        self._conn       = KSPConnection(args.host, args.port, args.stream_port)
        self._llm        = OllamaClient(base_url=args.ollama_url, model=args.model)
        self._craft_mgr  = CraftManager(args.ksp_dir, self._conn, self._llm)
        self._running    = False
        self._mission:   Optional[MissionPlanner] = None
        self._pilot:     Optional[LLMPilot]       = None

    def _new_mission(self) -> None:
        """Reset mission planner and pilot for a fresh flight."""
        self._mission = MissionPlanner(self._args.mission)
        self._pilot   = LLMPilot(self._llm, self._mission,
                                  decision_interval_sec=self._args.decision_interval)

    # ------------------------------------------------------------------ run --

    def run(self) -> None:
        # Step 1: connect kRPC socket (retry until KSP server is running)
        print(f"[openclaw] Waiting for kRPC at "
              f"{self._args.host}:{self._args.port}...")
        print("[openclaw] Open KSP → kRPC toolbar button → Start server")
        while True:
            if self._conn.connect():
                print("[openclaw] kRPC connected.")
                break
            print("[openclaw] Not available — retrying in 5s...", file=sys.stderr)
            time.sleep(5)

        print(f"[openclaw] LLM: {self._args.model}  Mission: {self._args.mission}")
        self._running = True

        try:
            self._game_loop()
        except KeyboardInterrupt:
            print("\n[openclaw] Interrupted.")
        finally:
            try:
                self._conn.set_throttle(0.0)
            except Exception:
                pass
            self._conn.disconnect()
            print("[openclaw] Disconnected.")

    # ------------------------------------------------------------- game loop --

    def _game_loop(self) -> None:
        """
        Outer loop: if no vessel in flight, auto-select and launch one;
        then run the flight loop.  Repeat if --loop is set.
        """
        while self._running:
            if not self._conn.has_active_vessel():
                self._handle_space_center()
                if not self._running:
                    return

            self._new_mission()
            push_event({
                "type":   "mission_start",
                "vessel": "OpenClaw",
                "phase":  "pre_launch",
                "manned": True,
            })
            print(f"\n[openclaw] Starting flight — {self._args.mission}")
            self._flight_loop()

            if not self._args.loop:
                print("[openclaw] Mission complete. "
                      "Pass --loop to keep playing indefinitely.")
                self._running = False
            else:
                print("[openclaw] Mission ended — returning to Space Center loop.")
                time.sleep(3)

    # ------------------------------------------------------- space-center phase

    def _handle_space_center(self) -> None:
        """
        Scan all save games for craft, let the LLM pick the best one,
        and launch it. Called whenever there is no active vessel.
        """
        # If vessel appeared while we were called, go straight to flying
        if self._conn.has_active_vessel():
            return

        print("\n[openclaw] No active vessel — scanning saves for craft...")
        craft_list = self._craft_mgr.list_craft()

        if not craft_list:
            print("[openclaw] No saved craft found in "
                  f"'{self._args.ksp_dir}/saves/*/Ships/'")
            print("[openclaw] Build a vessel in the VAB and save it, "
                  "then OpenClaw will auto-launch it.")
            print("[openclaw] Waiting for a vessel to appear in flight...")
            while not self._conn.has_active_vessel() and self._running:
                time.sleep(3)
            return

        print(f"[openclaw] Found {len(craft_list)} saved craft:")
        for i, c in enumerate(craft_list):
            print(f"  {i+1:2d}. [{c.craft_type}] {c.name:<40s}  (save: {c.save})")

        chosen = self._craft_mgr.select_for_mission(
            self._args.mission, craft_list
        )
        if chosen is None:
            print("[openclaw] Could not select a craft — "
                  "waiting for a vessel in flight.", file=sys.stderr)
            while not self._conn.has_active_vessel() and self._running:
                time.sleep(3)
            return

        ok = self._craft_mgr.launch(chosen)
        if not ok:
            print("[openclaw] Auto-launch failed — waiting for vessel "
                  "manually.", file=sys.stderr)

        # Wait for the flight scene to load (up to 60 s)
        print("[openclaw] Waiting for flight scene to load...")
        for _ in range(60):
            if self._conn.has_active_vessel():
                return
            time.sleep(1)
        print("[openclaw] Timed out waiting for flight scene.",
              file=sys.stderr)

    # ----------------------------------------------------------- flight loop --

    def _flight_loop(self) -> None:
        """Fly the active vessel until it disappears (recovered/destroyed)."""
        poll_interval = 0.5

        while self._running:
            t0 = time.time()

            if not self._conn.connected:
                print("\n[openclaw] kRPC socket lost — reconnecting...",
                      file=sys.stderr)
                while not self._conn.connect():
                    time.sleep(5)
                print("[openclaw] Reconnected.")

            telem = self._conn.read_telemetry()
            if telem is None:
                # Vessel gone — mission ended (recovered / destroyed)
                print("\n[openclaw] Vessel no longer in scene — "
                      "mission ended.")
                return

            self._mission.update(telem)

            if self._args.verbose:
                _print_telemetry(telem)

            action = self._pilot.decide(telem)
            if action:
                print(f"\n[openclaw] → {action.action}({action.params})"
                      f" | {action.reason}")
                execute_action(self._conn, action, telem)

            elapsed = time.time() - t0
            time.sleep(max(0.0, poll_interval - elapsed))


def _print_telemetry(t: AgentTelemetry) -> None:
    print(
        f"\r[openclaw] {t.phase:12s} | "
        f"alt={t.altitude_m/1000:7.1f}km | "
        f"apo={t.apoapsis_m/1000:7.1f}km | "
        f"fuel={t.fuel_pct*100:5.1f}% | "
        f"thr={t.throttle:.2f} | g={t.g_force:.1f}",
        end="", flush=True,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="OpenClaw — LLM-driven autonomous KSP pilot"
    )
    p.add_argument("--host",              default="localhost",
                   help="kRPC server host (default: localhost)")
    p.add_argument("--port",       type=int, default=50000,
                   help="kRPC RPC port (default: 50000)")
    p.add_argument("--stream-port",type=int, default=50001, dest="stream_port",
                   help="kRPC stream port (default: 50001)")
    p.add_argument("--model",             default="qwen3:8b",
                   help="Ollama model to use for piloting decisions")
    p.add_argument("--ollama-url",        default="http://localhost:11434",
                   dest="ollama_url",
                   help="Ollama API base URL")
    p.add_argument("--mission",           default="achieve a stable 80km orbit around Kerbin",
                   help="Natural language mission description")
    p.add_argument("--decision-interval", type=float, default=3.0,
                   dest="decision_interval",
                   help="Seconds between LLM decisions (default: 3.0)")
    p.add_argument("--ksp-dir",           default="D:/Games/Kerbal Space Program",
                   dest="ksp_dir",
                   help="Path to your KSP installation (default: D:/Games/Kerbal Space Program)")
    p.add_argument("--loop",              action="store_true",
                   help="After each mission ends, auto-select a new vessel and fly again")
    p.add_argument("--verbose", "-v",     action="store_true",
                   help="Print telemetry each tick")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    if not _HAS_KRPC:
        print("ERROR: krpc package not installed. Run: pip install krpc", file=sys.stderr)
        sys.exit(1)
    agent = OpenClawAgent(args)
    agent.run()
