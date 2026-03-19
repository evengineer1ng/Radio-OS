"""
KSP (Kerbal Space Program) Feed Plugin
=======================================
Connects to KSP via the kRPC mod and emits StationEvents for key mission
milestones — launch, staging, orbit insertion, maneuver execution, landing,
explosions, etc.

The plugin is intentionally passive — it only reads KSP data and pushes
events onto event_q.  All commentary decisions live in plugins/meta/ksp_meta.py.

Architecture
------------
  kRPC server (KSP mod)  ← listens on localhost:50000 by default
        │
  KSPReader              ← thin wrapper around the krpc client
        │
  EventDetector          ← compares current telemetry to previous tick
        │
  feed_worker            ← pushes StationEvents onto event_q
        │
  ksp_meta.py            ← receives events, runs LLM commentary

The agent (tools/ksp_agent.py) can also push events through _agent_event_q
so player-directed actions generate commentary too.

REQUIREMENTS
  pip install krpc

SETUP
  1. Install kRPC mod in KSP (via CKAN or manual)
  2. Enable kRPC server in KSP (Settings → kRPC, start server)
  3. Default connection: localhost:50000
"""

from __future__ import annotations

import os
import sys
import time
import math
import threading
import queue
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Plugin metadata
# ---------------------------------------------------------------------------
PLUGIN_NAME = "ksp_sdk"
PLUGIN_DESC = "Live KSP telemetry feed via kRPC — emits mission events for AI commentary."
IS_FEED     = True

FEED_DEFAULTS: Dict[str, Any] = {
    "enabled":           False,
    "host":              "localhost",
    "rpc_port":          50000,
    "stream_port":       50001,
    "poll_hz":           4,           # telemetry sample rate
    "sim_mode":          False,       # force simulation even when kRPC is available
    "vessel_name":       "",          # empty = track active vessel
    # Event enable flags
    "announce_launch":           True,
    "announce_staging":          True,
    "announce_orbit":            True,
    "announce_maneuvers":        True,
    "announce_altitude":         True,
    "announce_resources":        True,
    "announce_reentry":          True,
    "announce_landing":          True,
    "announce_explosions":       True,
    "announce_rendezvous":       True,
    "announce_eva":              True,
    # Thresholds
    "altitude_milestones_m":     [1_000, 10_000, 35_000, 70_000, 100_000,
                                   250_000, 500_000, 1_000_000],
    "resource_warning_pct":      0.15,  # warn below 15%
    "rendezvous_alert_m":        2_500,  # alert when target within 2.5 km
    "max_q_altitude_m":          30_000, # approximate MaxQ region upper bound
}

# ---------------------------------------------------------------------------
# Module-level shared state — readable by ksp_meta without needing runtime
# ---------------------------------------------------------------------------
_live_state: Dict[str, Any] = {}            # updated each tick by feed_worker
_agent_event_q: queue.Queue = queue.Queue() # ksp_agent.py pushes events here

# ---------------------------------------------------------------------------
# kRPC import — graceful fallback to sim mode
# ---------------------------------------------------------------------------
try:
    import krpc                 # type: ignore
    _HAS_KRPC = True
except ImportError:
    _HAS_KRPC = False


# ---------------------------------------------------------------------------
# Telemetry snapshot
# ---------------------------------------------------------------------------

@dataclass
class VesselSnapshot:
    name:           str   = "Unknown"
    situation:      str   = "PRE_LAUNCH"   # kRPC VesselSituation string
    flight_phase:   str   = "pre_launch"   # our internal phase label
    altitude_m:     float = 0.0            # altitude above sea level
    apoapsis_m:     float = 0.0
    periapsis_m:    float = 0.0
    speed_ms:       float = 0.0            # surface speed
    orbital_speed:  float = 0.0
    vertical_speed: float = 0.0
    throttle:       float = 0.0            # 0–1
    g_force:        float = 0.0
    dynamic_pressure: float = 0.0          # Pa
    stage_number:   int   = 0
    fuel_pct:       float = 1.0            # propellant fraction (LF+OX or solid)
    mono_pct:       float = 1.0            # monopropellant
    electric_pct:   float = 1.0
    meco:           bool  = False          # main engine cut off
    in_atmosphere:  bool  = True
    landed:         bool  = False
    splashed:       bool  = False
    target_dist_m:  float = -1.0           # -1 = no target
    crew_eva:       bool  = False
    ut:             float = 0.0            # universal time (seconds)
    manned:         bool  = True


# ---------------------------------------------------------------------------
# Live kRPC reader
# ---------------------------------------------------------------------------

class KSPReader:
    """Thin wrapper around a krpc connection."""

    def __init__(self, host: str = "localhost",
                 rpc_port: int = 50000, stream_port: int = 50001):
        self._host        = host
        self._rpc_port    = rpc_port
        self._stream_port = stream_port
        self._conn        = None
        self._vessel      = None

    def connect(self) -> bool:
        if not _HAS_KRPC:
            return False
        try:
            self._conn = krpc.connect(
                name="RadioOS",
                address=self._host,
                rpc_port=self._rpc_port,
                stream_port=self._stream_port,
            )
            return True
        except Exception:
            self._conn = None
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
        self._conn   = None
        self._vessel = None

    def _get_vessel(self):
        """Return active vessel (refreshes if needed)."""
        try:
            v = self._conn.space_center.active_vessel
            self._vessel = v
            return v
        except Exception:
            self._vessel = None
            return None

    def snapshot(self) -> Optional[VesselSnapshot]:
        """Read current telemetry and return a VesselSnapshot."""
        if not self._conn:
            return None
        vessel = self._get_vessel()
        if vessel is None:
            return None
        try:
            flight   = vessel.flight(vessel.orbit.body.reference_frame)
            orbit    = vessel.orbit
            control  = vessel.control
            sc       = self._conn.space_center

            # Situation
            situation_raw = str(vessel.situation).split(".")[-1].upper()

            # Propellant fractions
            fuel_pct  = _resource_fraction(vessel, ["LiquidFuel", "Oxidizer",
                                                      "SolidFuel", "Xenon"])
            mono_pct  = _resource_fraction(vessel, ["MonoPropellant"])
            elec_pct  = _resource_fraction(vessel, ["ElectricCharge"])

            # Target
            target_dist = -1.0
            try:
                target = sc.target_vessel or sc.target_body
                if target:
                    tv_pos = sc.active_vessel.position(sc.active_vessel.surface_reference_frame)
                    tg_pos = target.position(sc.active_vessel.surface_reference_frame) \
                             if hasattr(target, "position") else None
                    if tg_pos:
                        dx = tv_pos[0] - tg_pos[0]
                        dy = tv_pos[1] - tg_pos[1]
                        dz = tv_pos[2] - tg_pos[2]
                        target_dist = math.sqrt(dx*dx + dy*dy + dz*dz)
            except Exception:
                pass

            # EVA state — check if there are any Kerbals on EVA
            eva_active = False
            try:
                for v in sc.vessels:
                    if "EVA" in str(v.type):
                        eva_active = True
                        break
            except Exception:
                pass

            snap = VesselSnapshot(
                name            = vessel.name,
                situation       = situation_raw,
                flight_phase    = _situation_to_phase(situation_raw),
                altitude_m      = float(flight.mean_altitude),
                apoapsis_m      = float(orbit.apoapsis_altitude),
                periapsis_m     = float(orbit.periapsis_altitude),
                speed_ms        = float(flight.speed),
                orbital_speed   = float(orbit.speed),
                vertical_speed  = float(flight.vertical_speed),
                throttle        = float(control.throttle),
                g_force         = float(flight.g_force),
                dynamic_pressure= float(flight.dynamic_pressure),
                stage_number    = int(control.current_stage),
                fuel_pct        = fuel_pct,
                mono_pct        = mono_pct,
                electric_pct    = elec_pct,
                meco            = (float(control.throttle) < 0.01),
                in_atmosphere   = float(flight.mean_altitude) < float(orbit.body.atmosphere_depth),
                landed          = situation_raw in ("LANDED", "SPLASHED"),
                splashed        = situation_raw == "SPLASHED",
                target_dist_m   = target_dist,
                crew_eva        = eva_active,
                ut              = float(sc.ut),
                manned          = any(c.type.name == "Crew"
                                      for c in vessel.parts.list if hasattr(c, "crew")),
            )
            return snap
        except Exception:
            return None


def _resource_fraction(vessel, names: List[str]) -> float:
    """Return fraction of total capacity remaining across named resources."""
    total = 0.0
    current = 0.0
    try:
        for r in vessel.resources.all:
            if r.resource.name in names and r.max > 0:
                total   += r.max
                current += r.amount
    except Exception:
        return 1.0
    return (current / total) if total > 0 else 1.0


def _situation_to_phase(situation: str) -> str:
    _MAP = {
        "PRE_LAUNCH": "pre_launch",
        "LAUNCHING":  "ascent",
        "FLYING":     "ascent",
        "SUB_ORBITAL": "sub_orbital",
        "ORBITING":   "orbit",
        "ESCAPING":   "escape",
        "DOCKED":     "docked",
        "LANDED":     "landed",
        "SPLASHED":   "splashed",
    }
    return _MAP.get(situation, "unknown")


# ---------------------------------------------------------------------------
# Simulation mode
# ---------------------------------------------------------------------------

class SimMission:
    """Fake mission that walks through a scripted flight profile for testing."""

    _PHASES = [
        ("pre_launch",    10, {"altitude_m": 0, "speed_ms": 0, "fuel_pct": 1.0}),
        ("ascent",        40, {"altitude_m": 50_000, "speed_ms": 400, "fuel_pct": 0.7}),
        ("staging",        5, {"altitude_m": 60_000, "speed_ms": 800, "fuel_pct": 0.65,
                                "stage_number": 1}),
        ("ascent_2",      30, {"altitude_m": 100_000, "speed_ms": 900, "fuel_pct": 0.5}),
        ("orbit",         60, {"altitude_m": 120_000, "speed_ms": 2200, "fuel_pct": 0.45,
                                "apoapsis_m": 120_500, "periapsis_m": 119_800}),
        ("transfer",      20, {"altitude_m": 130_000, "speed_ms": 2400, "fuel_pct": 0.3}),
        ("reentry",       30, {"altitude_m": 50_000, "speed_ms": 600, "fuel_pct": 0.25}),
        ("descent",       20, {"altitude_m": 5_000, "speed_ms": 80, "fuel_pct": 0.23}),
        ("landing",       10, {"altitude_m": 0, "speed_ms": 3, "fuel_pct": 0.21}),
    ]

    def __init__(self, vessel_name: str = "Kerbonaut I"):
        self._phase_idx   = 0
        self._phase_start = time.time()
        self._vessel_name = vessel_name
        self._stage       = 0
        self._ut          = 0.0

    def snapshot(self) -> VesselSnapshot:
        now = time.time()
        name, duration, props = self._PHASES[self._phase_idx]
        elapsed = now - self._phase_start
        if elapsed >= duration:
            self._phase_idx = min(self._phase_idx + 1, len(self._PHASES) - 1)
            self._phase_start = now
        alt  = float(props.get("altitude_m", 0))
        apoa = float(props.get("apoapsis_m", alt + 500))
        peri = float(props.get("periapsis_m", max(0, alt - 500)))
        self._ut = now - (time.time() - now)  # monotonic UT proxy
        stage = int(props.get("stage_number", self._stage))
        if stage != self._stage:
            self._stage = stage
        return VesselSnapshot(
            name            = self._vessel_name,
            situation       = "FLYING" if alt > 0 else "PRE_LAUNCH",
            flight_phase    = name.replace("_2", ""),
            altitude_m      = alt,
            apoapsis_m      = apoa,
            periapsis_m     = peri,
            speed_ms        = float(props.get("speed_ms", 0)),
            orbital_speed   = float(props.get("speed_ms", 0)) if alt > 70_000 else 0.0,
            vertical_speed  = (alt - 0) / max(1.0, elapsed) if name in ("ascent", "ascent_2") else -(alt / 30),
            throttle        = 1.0 if name in ("ascent", "ascent_2", "transfer") else 0.0,
            g_force         = 2.5 if name in ("ascent", "reentry") else 1.0,
            dynamic_pressure= 20_000 if name == "ascent" else 0.0,
            stage_number    = self._stage,
            fuel_pct        = float(props.get("fuel_pct", 0.5)),
            mono_pct        = 0.95,
            electric_pct    = 1.0,
            meco            = name not in ("ascent", "ascent_2", "transfer"),
            in_atmosphere   = alt < 70_000,
            landed          = name == "landing" and elapsed > 5,
            splashed        = False,
            target_dist_m   = -1.0,
            crew_eva        = False,
            ut              = self._ut,
            manned          = True,
        )


# ---------------------------------------------------------------------------
# Event detector — diff between two snapshots
# ---------------------------------------------------------------------------

class EventDetector:
    """
    Compares successive VesselSnapshots and yields event dicts for
    anything noteworthy.
    """

    def __init__(self, cfg: Dict[str, Any]):
        self._cfg            = cfg
        self._prev:  Optional[VesselSnapshot] = None
        self._launch_fired   = False
        self._orbit_fired    = False
        self._max_q_fired    = False
        self._max_q_passed   = False    # set once we pass MaxQ altitude going up
        self._reentry_fired  = False
        self._landing_fired  = False
        self._eva_fired      = False
        self._passed_milestones: set = set()
        self._prev_stage     = -1
        self._announced_phases: set = set()
        self._fuel_warned    = False
        self._mono_warned    = False
        self._elec_warned    = False
        self._prev_periapsis = -1.0
        self._prev_apoapsis  = -1.0
        self._attitude_checks = 0
        self._mission_start_fired = False

    def tick(self, snap: VesselSnapshot) -> List[Dict[str, Any]]:
        """Return list of event dicts for this tick (may be empty)."""
        events: List[Dict[str, Any]] = []
        prev = self._prev
        cfg  = self._cfg

        # Always: mission start on first tick
        if not self._mission_start_fired:
            events.append({
                "type": "mission_start",
                "vessel": snap.name,
                "phase": snap.flight_phase,
                "altitude_m": snap.altitude_m,
                "manned": snap.manned,
            })
            self._mission_start_fired = True

        if prev is None:
            self._prev = snap
            return events

        # --- Launch detection ---
        if (cfg.get("announce_launch", True)
                and not self._launch_fired
                and prev.throttle < 0.5 and snap.throttle >= 0.5
                and snap.altitude_m < 2_000):
            events.append({
                "type":       "launch",
                "vessel":     snap.name,
                "ut":         snap.ut,
                "manned":     snap.manned,
                "g_force":    snap.g_force,
            })
            self._launch_fired = True

        # --- Stage separation ---
        if (cfg.get("announce_staging", True)
                and prev.stage_number != snap.stage_number
                and self._prev_stage != snap.stage_number):
            events.append({
                "type":       "stage_separation",
                "vessel":     snap.name,
                "stage":      snap.stage_number,
                "altitude_m": snap.altitude_m,
                "speed_ms":   snap.speed_ms,
            })
            self._prev_stage = snap.stage_number

        # --- Altitude milestones ---
        if cfg.get("announce_altitude", True):
            milestones = cfg.get("altitude_milestones_m",
                                  [1_000, 10_000, 35_000, 70_000, 100_000])
            for m in milestones:
                if m not in self._passed_milestones:
                    if prev.altitude_m < m <= snap.altitude_m:
                        label = _altitude_label(m)
                        events.append({
                            "type":       "altitude_milestone",
                            "vessel":     snap.name,
                            "altitude_m": m,
                            "label":      label,
                            "speed_ms":   snap.speed_ms,
                            "apoapsis_m": snap.apoapsis_m,
                        })
                        self._passed_milestones.add(m)
                        # Track Karman line separately as orbit_achieved candidate
                        if m == 70_000:
                            self._max_q_passed = True

        # --- MaxQ passthrough ---
        max_q_alt = float(cfg.get("max_q_altitude_m", 30_000))
        if (not self._max_q_fired
                and snap.in_atmosphere
                and snap.dynamic_pressure > 0
                and snap.altitude_m > 5_000):
            # Find local peak in dynamic pressure by comparing with next reading
            # Simple heuristic: announce when altitude crosses 25–35km on way up
            if prev.altitude_m < 25_000 <= snap.altitude_m:
                events.append({
                    "type":      "max_q",
                    "vessel":    snap.name,
                    "altitude_m": snap.altitude_m,
                    "dyn_pressure_pa": snap.dynamic_pressure,
                    "speed_ms":  snap.speed_ms,
                })
                self._max_q_fired = True

        # --- Orbit achieved ---
        atm_depth = 70_000   # Kerbin default; close enough for most bodies
        if (cfg.get("announce_orbit", True)
                and not self._orbit_fired
                and snap.periapsis_m > atm_depth
                and snap.apoapsis_m > atm_depth):
            events.append({
                "type":        "orbit_achieved",
                "vessel":      snap.name,
                "apoapsis_m":  snap.apoapsis_m,
                "periapsis_m": snap.periapsis_m,
                "orbital_speed": snap.orbital_speed,
            })
            self._orbit_fired = True

        # --- Maneuver node completion heuristic ---
        # Detect significant throttle down after active burn
        if (cfg.get("announce_maneuvers", True)
                and prev.throttle > 0.7 and snap.throttle < 0.1
                and snap.altitude_m > 70_000):
            events.append({
                "type":       "maneuver_executed",
                "vessel":     snap.name,
                "apoapsis_m": snap.apoapsis_m,
                "periapsis_m":snap.periapsis_m,
                "altitude_m": snap.altitude_m,
                "delta_apo_m": snap.apoapsis_m - self._prev_apoapsis
                               if self._prev_apoapsis > 0 else 0.0,
            })

        # --- Track apoapsis / periapsis for change reference ---
        if snap.apoapsis_m > 0:
            self._prev_apoapsis  = snap.apoapsis_m
        if snap.periapsis_m > 0:
            self._prev_periapsis = snap.periapsis_m

        # --- Resource warnings ---
        warn_pct = float(cfg.get("resource_warning_pct", 0.15))
        if (cfg.get("announce_resources", True)
                and not self._fuel_warned
                and 0 < snap.fuel_pct < warn_pct
                and snap.altitude_m > 500):
            events.append({
                "type":      "resource_warning",
                "resource":  "fuel",
                "pct":       round(snap.fuel_pct * 100, 1),
                "vessel":    snap.name,
                "altitude_m": snap.altitude_m,
            })
            self._fuel_warned = True

        if (cfg.get("announce_resources", True)
                and not self._elec_warned
                and 0 < snap.electric_pct < warn_pct
                and snap.altitude_m > 500):
            events.append({
                "type":      "resource_warning",
                "resource":  "electric",
                "pct":       round(snap.electric_pct * 100, 1),
                "vessel":    snap.name,
                "altitude_m": snap.altitude_m,
            })
            self._elec_warned = True

        # --- Engine flameout (MECO early) ---
        if (prev.throttle > 0.5 and snap.meco
                and snap.altitude_m < snap.apoapsis_m
                and snap.altitude_m > 1_000):
            events.append({
                "type":      "engine_cutoff",
                "vessel":    snap.name,
                "altitude_m": snap.altitude_m,
                "expected":  snap.altitude_m > 70_000,  # True = planned cutoff
                "apoapsis_m": snap.apoapsis_m,
            })

        # --- Reentry ---
        if (cfg.get("announce_reentry", True)
                and not self._reentry_fired
                and prev.altitude_m > 70_000 > snap.altitude_m
                and snap.vertical_speed < -50):
            events.append({
                "type":       "reentry_start",
                "vessel":     snap.name,
                "altitude_m": snap.altitude_m,
                "speed_ms":   snap.speed_ms,
                "g_force":    snap.g_force,
            })
            self._reentry_fired = True

        # --- G-force spike on reentry ---
        if (snap.g_force > 4.0 and prev.g_force < 3.0
                and snap.vertical_speed < -100):
            events.append({
                "type":    "gforce_spike",
                "vessel":  snap.name,
                "g_force": round(snap.g_force, 1),
                "altitude_m": snap.altitude_m,
                "speed_ms":   snap.speed_ms,
            })

        # --- Landing / splashdown ---
        if (cfg.get("announce_landing", True)
                and not self._landing_fired
                and snap.landed
                and not prev.landed):
            etype = "splashdown" if snap.splashed else "touchdown"
            events.append({
                "type":         etype,
                "vessel":       snap.name,
                "speed_ms":     snap.speed_ms,
                "altitude_m":   snap.altitude_m,
                "manned":       snap.manned,
                "mission_time": snap.ut,
            })
            self._landing_fired = True

        # --- Rendezvous proximity ---
        if (cfg.get("announce_rendezvous", True)
                and snap.target_dist_m > 0):
            threshold = float(cfg.get("rendezvous_alert_m", 2_500))
            if prev.target_dist_m > threshold > snap.target_dist_m:
                events.append({
                    "type":     "rendezvous_approach",
                    "vessel":   snap.name,
                    "distance_m": snap.target_dist_m,
                })

        # --- EVA ---
        if (cfg.get("announce_eva", True)
                and not prev.crew_eva and snap.crew_eva
                and not self._eva_fired):
            events.append({
                "type":   "eva_start",
                "vessel": snap.name,
                "altitude_m": snap.altitude_m,
            })
            self._eva_fired = True
        elif prev.crew_eva and not snap.crew_eva and self._eva_fired:
            events.append({
                "type":   "eva_end",
                "vessel": snap.name,
            })
            self._eva_fired = False

        self._prev = snap
        return events


def _altitude_label(m: float) -> str:
    labels = {
        1_000: "1 km",      10_000: "10 km",    35_000: "35 km",
        70_000: "the Karman line (70 km — space!)",
        100_000: "100 km",  250_000: "250 km",
        500_000: "500 km",  1_000_000: "1,000 km",
    }
    if m in labels:
        return labels[m]
    if m >= 1_000_000:
        return f"{m/1_000_000:.0f} Mm"
    if m >= 1_000:
        return f"{m/1_000:.0f} km"
    return f"{m:.0f} m"


# ---------------------------------------------------------------------------
# Feed worker — entry point called by runtime
# ---------------------------------------------------------------------------

def feed_worker(event_q, StationEvent, cfg: Dict[str, Any],
                runtime: Dict[str, Any]) -> None:
    """
    Main polling loop.  Connects to kRPC, polls telemetry, detects events,
    and pushes them onto event_q as StationEvents.

    runtime["log"] is used for diagnostic messages.
    """
    log       = runtime.get("log", print)
    poll_hz   = float(cfg.get("poll_hz", 4))
    poll_int  = 1.0 / max(poll_hz, 0.5)
    host      = str(cfg.get("host", "localhost"))
    rpc_port  = int(cfg.get("rpc_port", 50000))
    stm_port  = int(cfg.get("stream_port", 50001))
    sim_mode  = bool(cfg.get("sim_mode", False))

    if not bool(cfg.get("enabled", False)):
        log("ksp_sdk", "Plugin disabled — set enabled=true in station manifest to activate.")
        return

    # Try live kRPC connection
    reader:    Optional[KSPReader] = None
    sim:       Optional[SimMission] = None
    detector   = EventDetector(cfg)
    reconnect_at = 0.0

    if not sim_mode and _HAS_KRPC:
        reader = KSPReader(host, rpc_port, stm_port)
        if reader.connect():
            log("ksp_sdk", f"Connected to KSP kRPC at {host}:{rpc_port}")
        else:
            log("ksp_sdk", "kRPC not available — falling back to sim mode.")
            sim = SimMission(str(cfg.get("vessel_name", "Kerbonaut I")))
    else:
        if not _HAS_KRPC and not sim_mode:
            log("ksp_sdk", "krpc package not installed — running in sim mode. "
                           "pip install krpc to enable live KSP connection.")
        sim = SimMission(str(cfg.get("vessel_name", "Kerbonaut I")))

    stop_evt = runtime.get("stop_event")

    while True:
        if stop_evt and stop_evt.is_set():
            break

        tick_start = time.time()

        # Reconnect attempt if reader lost connection
        if reader and not reader.connected and time.time() > reconnect_at:
            if reader.connect():
                log("ksp_sdk", "Reconnected to kRPC.")
                detector = EventDetector(cfg)   # fresh detector after reconnect
            else:
                reconnect_at = time.time() + 5.0

        # Get snapshot
        snap: Optional[VesselSnapshot] = None
        if reader and reader.connected:
            snap = reader.snapshot()
        elif sim:
            snap = sim.snapshot()

        if snap is None:
            time.sleep(poll_int)
            continue

        # Update shared live state (read by ksp_meta heartbeat)
        _live_state.update({
            "vessel":       snap.name,
            "phase":        snap.flight_phase,
            "altitude_m":   snap.altitude_m,
            "apoapsis_m":   snap.apoapsis_m,
            "periapsis_m":  snap.periapsis_m,
            "speed_ms":     snap.speed_ms,
            "orbital_speed":snap.orbital_speed,
            "fuel_pct":     snap.fuel_pct,
            "g_force":      snap.g_force,
            "throttle":     snap.throttle,
            "stage":        snap.stage_number,
            "landed":       snap.landed,
            "manned":       snap.manned,
            "target_dist_m":snap.target_dist_m,
            "ut":           snap.ut,
        })

        # Detect and emit events from telemetry diff
        detected_events = detector.tick(snap)
        for ev_data in detected_events:
            _push_station_event(ev_data, event_q, StationEvent, log)

        # Drain agent-injected events (from ksp_agent.py)
        while not _agent_event_q.empty():
            try:
                ev_data = _agent_event_q.get_nowait()
                _push_station_event(ev_data, event_q, StationEvent, log)
            except queue.Empty:
                break

        # Periodic resource update (like standings_update in iRacing)
        _live_state.setdefault("_last_resource_ts", 0)
        if time.time() - _live_state["_last_resource_ts"] > 30:
            _push_station_event({
                "type":        "resource_update",
                "vessel":      snap.name,
                "fuel_pct":    round(snap.fuel_pct * 100, 1),
                "mono_pct":    round(snap.mono_pct * 100, 1),
                "electric_pct":round(snap.electric_pct * 100, 1),
                "altitude_m":  snap.altitude_m,
                "apoapsis_m":  snap.apoapsis_m,
            }, event_q, StationEvent, log)
            _live_state["_last_resource_ts"] = time.time()

        elapsed = time.time() - tick_start
        sleep_t = max(0.0, poll_int - elapsed)
        time.sleep(sleep_t)

    if reader:
        reader.disconnect()
    log("ksp_sdk", "Feed worker stopped.")


def _push_station_event(ev_data: Dict[str, Any],
                         event_q, StationEvent, log) -> None:
    etype = ev_data.get("type", "unknown")
    try:
        ev = StationEvent(
            source   = "ksp_sdk",
            type     = etype,
            ts       = int(time.time()),
            payload  = ev_data,
            priority = _EVENT_PRIORITIES.get(etype, 50),
        )
        event_q.put_nowait(ev)
    except Exception as exc:
        log("ksp_sdk", f"Failed to push event {etype}: {exc}")


_EVENT_PRIORITIES: Dict[str, int] = {
    "launch":            95,
    "mission_start":     85,
    "stage_separation":  88,
    "orbit_achieved":    95,
    "maneuver_executed": 82,
    "max_q":             80,
    "altitude_milestone":75,
    "reentry_start":     90,
    "gforce_spike":      85,
    "touchdown":         95,
    "splashdown":        95,
    "engine_cutoff":     80,
    "resource_warning":  88,
    "rendezvous_approach":85,
    "eva_start":         78,
    "eva_end":           70,
    "resource_update":   50,
    "agent_action":      72,
}
