"""
iRacing SDK Feed Plugin
=======================
Connects to the iRacing shared-memory API via pyirsdk and emits StationEvents
for every noteworthy change: session state transitions, lap completions,
position changes, pit activity, incidents, fastest laps, yellow flags, and
the live telemetry tick.

The plugin is intentionally passive — it only reads iRacing data and pushes
events onto event_q.  All commentary decisions live in plugins/meta/iracing_meta.py.

REQUIREMENTS
  pip install pyirsdk

IMPORTANT: iRacing only exposes shared memory on Windows.
On macOS / Linux the plugin starts in SIMULATION MODE — it synthesises a
fake race session so development and testing work without iRacing running.
"""

from __future__ import annotations

import os
import sys
import time
import random
import threading
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Plugin metadata
# ---------------------------------------------------------------------------
PLUGIN_NAME    = "iracing_sdk"
PLUGIN_DESC    = "Live iRacing telemetry feed — emits race events for the AI commentator."
IS_FEED        = True
FEED_DEFAULTS: Dict[str, Any] = {
    "enabled":              False,
    "poll_hz":              4,          # telemetry sample rate (4 Hz is plenty for commentary)
    "incident_threshold":   1,          # incident points delta to trigger an event
    "position_threshold":   1,          # position delta that counts as a pass
    "sim_mode":             False,      # force simulation mode even on Windows
    "sim_drivers":          12,
    "sim_laps":             30,
    "sim_track":            "Daytona",
    "sim_series":           "iRacing Demo League",
    "announce_session_changes": True,
    "announce_lap_completions": True,
    "announce_passes":          True,
    "announce_incidents":       True,
    "announce_fastest_lap":     True,
    "announce_flags":           True,
    "announce_pit":             True,
}

# ---------------------------------------------------------------------------
# SDK import — graceful fallback to sim mode
# ---------------------------------------------------------------------------
try:
    import irsdk  # pyirsdk
    _HAS_IRSDK = True
except ImportError:
    _HAS_IRSDK = False

_IS_WINDOWS = sys.platform == "win32"

# ---------------------------------------------------------------------------
# Shared data classes
# ---------------------------------------------------------------------------

@dataclass
class DriverInfo:
    idx:        int
    name:       str
    car:        str
    car_num:    str
    irating:    int  = 0
    team_name:  str  = ""
    license:    str  = ""

@dataclass
class LiveDriver:
    idx:            int
    name:           str
    car_num:        str
    position:       int  = 0        # 1-based on-track position
    lap:            int  = 0
    lap_pct:        float = 0.0
    last_lap_time:  float = -1.0
    best_lap_time:  float = -1.0
    incidents:      int  = 0
    on_pit_road:    bool = False
    is_player:      bool = False
    dnf:            bool = False
    gap_to_leader:  float = 0.0     # seconds behind leader

# ---------------------------------------------------------------------------
# Shared-memory reader (real iRacing)
# ---------------------------------------------------------------------------

class IRacingReader:
    """Thin wrapper around pyirsdk."""

    def __init__(self):
        self._ir   = irsdk.IRSDK()
        self._ok   = False

    def connect(self) -> bool:
        if not self._ok:
            self._ok = self._ir.startup()
        return self._ok

    def disconnect(self) -> None:
        try:
            self._ir.shutdown()
        except Exception:
            pass
        self._ok = False

    @property
    def connected(self) -> bool:
        return self._ok and self._ir.is_connected

    def var(self, key: str, default: Any = None) -> Any:
        try:
            v = self._ir[key]
            return v if v is not None else default
        except Exception:
            return default

    # ---- convenience accessors ----------------------------------------

    def session_state(self) -> str:
        """Returns one of: Invalid, GetInCar, Warmup, ParadeLaps, Racing, Checkered,
        CoolDown — mapped from the SessionState integer."""
        states = ["Invalid","GetInCar","Warmup","ParadeLaps","Racing","Checkered","CoolDown"]
        idx = int(self.var("SessionState", 0))
        return states[idx] if 0 <= idx < len(states) else "Unknown"

    def flag_str(self) -> str:
        """Map SessionFlags bitmask to a human string."""
        flags = int(self.var("SessionFlags", 0))
        # iRacing flag bits (partial, most important)
        FLAG_NAMES = {
            0x00000001: "checkered",
            0x00000002: "white",
            0x00000004: "green",
            0x00000008: "yellow",
            0x00000010: "red",
            0x00000020: "blue",
            0x00000080: "black",
            0x00000100: "yellow_waving",
            0x10000000: "caution",
            0x20000000: "caution_waving",
            0x40000000: "black_and_white",
            0x80000000: "meatball",
        }
        names = [n for bit, n in sorted(FLAG_NAMES.items()) if flags & bit]
        return names[0] if names else "green"

    def driver_info(self) -> List[DriverInfo]:
        try:
            di = self._ir["DriverInfo"] or {}
            drivers = di.get("Drivers", [])
            result = []
            for d in drivers:
                result.append(DriverInfo(
                    idx=int(d.get("CarIdx", 0)),
                    name=str(d.get("UserName", "Unknown")),
                    car=str(d.get("CarPath", "")),
                    car_num=str(d.get("CarNumber", "?")),
                    irating=int(d.get("IRating", 0)),
                    team_name=str(d.get("TeamName", "")),
                    license=str(d.get("LicString", "")),
                ))
            return result
        except Exception:
            return []

    def live_drivers(self, driver_map: Dict[int, DriverInfo]) -> List[LiveDriver]:
        """Sample real-time per-car arrays and return LiveDriver list."""
        try:
            lap_dist_pct   = list(self._ir["CarIdxLapDistPct"]   or [])
            lap_num        = list(self._ir["CarIdxLap"]          or [])
            last_lap       = list(self._ir["CarIdxLastLapTime"]  or [])
            best_lap       = list(self._ir["CarIdxBestLapTime"]  or [])
            incidents      = list(self._ir["CarIdxInc"]          or [])
            on_pit         = list(self._ir["CarIdxOnPitRoad"]    or [])
            # Position is not a direct iRacing array; we'll derive it from lap_dist_pct
            # combined with completed laps
            player_car_idx = int(self._ir["PlayerCarIdx"] or 0)

            drivers = []
            for idx, info in driver_map.items():
                if idx >= len(lap_dist_pct):
                    continue
                pct = float(lap_dist_pct[idx] if idx < len(lap_dist_pct) else 0.0)
                lap = int(lap_num[idx] if idx < len(lap_num) else 0)
                drivers.append(LiveDriver(
                    idx=idx,
                    name=info.name,
                    car_num=info.car_num,
                    lap=max(lap, 0),
                    lap_pct=max(pct, 0.0),
                    last_lap_time=float(last_lap[idx]) if idx < len(last_lap) else -1.0,
                    best_lap_time=float(best_lap[idx]) if idx < len(best_lap) else -1.0,
                    incidents=int(incidents[idx]) if idx < len(incidents) else 0,
                    on_pit_road=bool(on_pit[idx]) if idx < len(on_pit) else False,
                    is_player=(idx == player_car_idx),
                ))

            # Derive positions: higher (lap + pct) = better
            drivers.sort(key=lambda d: (d.lap + d.lap_pct), reverse=True)
            for pos, d in enumerate(drivers, start=1):
                d.position = pos

            # Gap to leader
            if drivers:
                leader_progress = drivers[0].lap + drivers[0].lap_pct
                track_length_m  = float(self.var("TrackLength", 3000.0) or 3000.0)
                avg_lap_sec = 90.0  # fallback if no times available
                for d in drivers:
                    delta_progress = leader_progress - (d.lap + d.lap_pct)
                    d.gap_to_leader = delta_progress * avg_lap_sec if d.position > 1 else 0.0

            return drivers
        except Exception as exc:
            return []

    def track_name(self) -> str:
        try:
            wi = self._ir["WeekendInfo"] or {}
            return str(wi.get("TrackDisplayName", "Unknown Track"))
        except Exception:
            return "Unknown Track"

    def series_name(self) -> str:
        try:
            wi = self._ir["WeekendInfo"] or {}
            return str(wi.get("SeriesName", "iRacing"))
        except Exception:
            return "iRacing"

    def total_laps(self) -> int:
        try:
            si = self._ir["SessionInfo"] or {}
            for s in (si.get("Sessions") or []):
                if s.get("SessionType") == "Race":
                    raw = str(s.get("SessionLaps", "0"))
                    return int(raw) if raw.isdigit() else 0
        except Exception:
            pass
        return 0

    def current_lap(self) -> int:
        try:
            return max(0, int(self._ir["RaceLaps"] or 0))
        except Exception:
            return 0

    def air_temp(self) -> float:
        return float(self.var("AirTemp", 22.0))

    def track_temp(self) -> float:
        return float(self.var("TrackTemp", 30.0))


# ---------------------------------------------------------------------------
# Simulator (dev / macOS mode)
# ---------------------------------------------------------------------------

class IRacingSimulator:
    """Fake iRacing session for development without Windows/iRacing."""

    _FIRST_NAMES = ["Alex","Jordan","Kai","Morgan","Sam","Taylor","Riley","Casey",
                    "Devon","Avery","Quinn","Blake","Drew","Jamie","Parker"]
    _LAST_NAMES  = ["Smith","Rossi","Müller","Honda","Dubois","Garcia","Kowalski",
                    "Lindqvist","Nakamura","Okafor","Ferreira","Santos","Kim","Novak"]
    _CARS        = ["Dallara IR18","Radical SR8","Porsche 911 GT3 Cup","NASCAR Cup",
                    "Mazda MX-5 Cup","LMP2 Oreca","GTE Ferrari 488"]

    def __init__(self, num_drivers: int, total_laps: int, track: str, series: str):
        self._num_drivers = num_drivers
        self._total_laps  = total_laps
        self._track       = track
        self._series      = series
        self._connected   = False

        self._session_state = "GetInCar"
        self._flag          = "green"
        self._current_lap   = 0
        self._tick          = 0
        self._caution_ticks = 0

        rng = random.Random(42)
        names = []
        while len(names) < num_drivers:
            n = f"{rng.choice(self._FIRST_NAMES)} {rng.choice(self._LAST_NAMES)}"
            if n not in names:
                names.append(n)

        car   = rng.choice(self._CARS)
        self._drivers: List[DriverInfo] = [
            DriverInfo(
                idx=i,
                name=names[i],
                car=car,
                car_num=str(rng.randint(1,99)),
                irating=rng.randint(1000, 4000),
                license=rng.choice(["D","C","B","A","P"]),
            )
            for i in range(num_drivers)
        ]

        # Live state per driver
        base_lap_time = 90.0 + rng.uniform(-5, 5)
        self._live: List[LiveDriver] = []
        for i, d in enumerate(self._drivers):
            self._live.append(LiveDriver(
                idx=i,
                name=d.name,
                car_num=d.car_num,
                position=i+1,
                lap=0,
                lap_pct=rng.uniform(0, 0.1) * (1.0 - i * 0.005),
                last_lap_time=-1.0,
                best_lap_time=-1.0,
                is_player=(i == 0),
            ))

        self._base_speed: List[float] = [
            (1.0 - i * 0.012 + rng.uniform(-0.005, 0.005))
            for i in range(num_drivers)
        ]
        self._base_lap_time = base_lap_time
        self._rng = rng

    # ---- public interface (mirrors IRacingReader) -------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def session_state(self) -> str:
        return self._session_state

    def flag_str(self) -> str:
        return self._flag

    def driver_info(self) -> List[DriverInfo]:
        return self._drivers

    def live_drivers(self, _driver_map) -> List[LiveDriver]:
        return self._live

    def track_name(self) -> str:
        return self._track

    def series_name(self) -> str:
        return self._series

    def total_laps(self) -> int:
        return self._total_laps

    def current_lap(self) -> int:
        return self._current_lap

    def air_temp(self) -> float:
        return 22.0

    def track_temp(self) -> float:
        return 35.0

    # ---- internal sim tick -----------------------------------------------

    def advance(self, dt: float) -> None:
        """Advance simulation by dt seconds."""
        self._tick += 1

        # Session progression
        if self._session_state == "GetInCar" and self._tick > 3:
            self._session_state = "Warmup"
        elif self._session_state == "Warmup" and self._tick > 6:
            self._session_state = "ParadeLaps"
        elif self._session_state == "ParadeLaps" and self._tick > 9:
            self._session_state = "Racing"

        if self._session_state != "Racing":
            return

        # Caution periods
        if self._caution_ticks > 0:
            self._caution_ticks -= 1
            self._flag = "yellow" if self._caution_ticks > 0 else "green"
        elif self._rng.random() < 0.003:
            self._caution_ticks = self._rng.randint(20, 60)
            self._flag = "yellow"
            # Give someone an incident
            victim = self._rng.choice(self._live)
            victim.incidents += self._rng.randint(2, 4)

        # Advance each driver
        for i, d in enumerate(self._live):
            if d.dnf:
                continue
            # Vary speed slightly each tick
            speed = self._base_speed[i] * (1.0 + self._rng.gauss(0, 0.002))
            if self._flag == "yellow":
                speed *= 0.6
            if d.on_pit_road:
                speed *= 0.3

            # Pit logic: random pit stops
            if (not d.on_pit_road and d.lap > 0 and d.lap % (self._total_laps // 3 + 1) == 0
                    and d.lap_pct > 0.3 and self._rng.random() < 0.05):
                d.on_pit_road = True
            elif d.on_pit_road and self._rng.random() < 0.1:
                d.on_pit_road = False

            lap_time = self._base_lap_time / speed
            pct_per_sec = dt / lap_time
            d.lap_pct += pct_per_sec

            if d.lap_pct >= 1.0:
                d.lap_pct -= 1.0
                d.lap += 1
                lap_t = lap_time * (1.0 + self._rng.gauss(0, 0.01))
                d.last_lap_time = lap_t
                if d.best_lap_time < 0 or lap_t < d.best_lap_time:
                    d.best_lap_time = lap_t

        # Re-derive positions
        active = [d for d in self._live if not d.dnf]
        active.sort(key=lambda d: (d.lap + d.lap_pct), reverse=True)
        for pos, d in enumerate(active, start=1):
            d.position = pos

        # Leader lap counter
        if active:
            self._current_lap = active[0].lap

        # Random DNF
        if self._rng.random() < 0.001:
            victim = self._rng.choice([d for d in self._live if not d.dnf])
            victim.dnf = True

        # Race end
        if self._current_lap >= self._total_laps:
            self._session_state = "Checkered"
            self._flag = "checkered"


# ---------------------------------------------------------------------------
# Feed worker
# ---------------------------------------------------------------------------

def feed_worker(stop_event: threading.Event, mem: Dict[str, Any],
                cfg: Dict[str, Any], runtime: Dict[str, Any]) -> None:
    """
    Main feed loop — samples iRacing (real or simulated) and pushes
    StationEvent objects onto event_q for the meta plugin to handle.
    """
    StationEvent  = runtime["StationEvent"]
    event_q       = runtime["event_q"]
    emit_candidate = runtime["emit_candidate"]
    log           = runtime.get("log", print)

    poll_hz = float(cfg.get("poll_hz", FEED_DEFAULTS["poll_hz"]))
    dt      = 1.0 / max(poll_hz, 0.1)

    incident_thresh  = int(cfg.get("incident_threshold", FEED_DEFAULTS["incident_threshold"]))
    position_thresh  = int(cfg.get("position_threshold", FEED_DEFAULTS["position_threshold"]))
    sim_mode         = bool(cfg.get("sim_mode", FEED_DEFAULTS["sim_mode"]))

    # Decide backend
    use_sim = sim_mode or not _IS_WINDOWS or not _HAS_IRSDK
    if use_sim:
        backend = IRacingSimulator(
            num_drivers=int(cfg.get("sim_drivers", FEED_DEFAULTS["sim_drivers"])),
            total_laps=int(cfg.get("sim_laps", FEED_DEFAULTS["sim_laps"])),
            track=str(cfg.get("sim_track", FEED_DEFAULTS["sim_track"])),
            series=str(cfg.get("sim_series", FEED_DEFAULTS["sim_series"])),
        )
        log("iracing_sdk", "⚠  iRacing SDK not available or sim_mode=true — running in SIMULATION MODE")
    else:
        backend = IRacingReader()
        log("iracing_sdk", "Connecting to iRacing shared memory …")

    # State snapshots for diffing
    prev_session_state: str           = ""
    prev_flag:          str           = ""
    prev_positions:     Dict[int,int] = {}
    prev_laps:          Dict[int,int] = {}
    prev_incidents:     Dict[int,int] = {}
    prev_pit:           Dict[int,bool]= {}
    global_best_time:   float         = -1.0
    global_best_name:   str           = ""
    driver_map:         Dict[int,DriverInfo] = {}
    session_started                   = False

    def _emit(etype: str, data: Dict[str, Any]) -> None:
        """Push an event onto event_q."""
        try:
            ev = StationEvent(
                source="iracing_sdk",
                event_type=etype,
                data=data,
                priority=80,
            )
            event_q.put_nowait(ev)
        except Exception as exc:
            log("iracing_sdk", f"emit error: {exc}")

    def _candidate(title: str, body: str, tags: List[str], priority: float = 80.0) -> None:
        """Emit a feed candidate so the regular LLM pipeline can also pick it up."""
        try:
            emit_candidate({
                "post_id":  f"ir_{title[:20]}_{int(time.time())}",
                "title":    title,
                "body":     body,
                "source":   "iracing_sdk",
                "tags":     tags,
                "priority": priority,
            })
        except Exception:
            pass

    while not stop_event.is_set():
        try:
            # Connection management
            if not backend.connected:
                if not backend.connect():
                    log("iracing_sdk", "Waiting for iRacing …")
                    time.sleep(5.0)
                    continue
                log("iracing_sdk", "Connected to iRacing ✓")

            # Advance simulator if in sim mode
            if use_sim:
                backend.advance(dt)

            # ---- Session state ------------------------------------------
            sess_state = backend.session_state()
            if sess_state != prev_session_state and cfg.get("announce_session_changes", True):
                _emit("session_state_change", {
                    "from":    prev_session_state,
                    "to":      sess_state,
                    "track":   backend.track_name(),
                    "series":  backend.series_name(),
                    "total_laps": backend.total_laps(),
                    "air_temp":   backend.air_temp(),
                    "track_temp": backend.track_temp(),
                })
                if sess_state == "Racing" and not session_started:
                    session_started = True
                    _candidate(
                        f"Race LIVE: {backend.series_name()} at {backend.track_name()}",
                        f"The {backend.series_name()} race at {backend.track_name()} has gone green! "
                        f"{backend.total_laps()} laps of sim racing ahead.",
                        ["iracing","race_start","live"],
                        priority=95.0,
                    )
                prev_session_state = sess_state

            # ---- Flag changes -------------------------------------------
            flag = backend.flag_str()
            if flag != prev_flag and cfg.get("announce_flags", True):
                _emit("flag_change", {
                    "flag":  flag,
                    "lap":   backend.current_lap(),
                    "track": backend.track_name(),
                })
                prev_flag = flag

            # Only process detailed events during / after racing
            if sess_state not in ("Racing","Checkered","CoolDown"):
                time.sleep(dt)
                continue

            # ---- Driver info refresh (infrequent) -----------------------
            if not driver_map:
                for di in backend.driver_info():
                    driver_map[di.idx] = di

            # ---- Live driver data ---------------------------------------
            live = backend.live_drivers(driver_map)

            for d in live:
                # Lap completion
                prev_lap = prev_laps.get(d.idx, -1)
                if prev_lap >= 0 and d.lap > prev_lap and cfg.get("announce_lap_completions", True):
                    _emit("lap_complete", {
                        "driver":        d.name,
                        "car_num":       d.car_num,
                        "position":      d.position,
                        "lap":           d.lap,
                        "lap_time":      d.last_lap_time,
                        "best_time":     d.best_lap_time,
                        "total_laps":    backend.total_laps(),
                        "gap_to_leader": d.gap_to_leader,
                        "is_player":     d.is_player,
                    })

                    # Fastest lap check
                    if (d.last_lap_time > 0 and cfg.get("announce_fastest_lap", True)
                            and (global_best_time < 0 or d.last_lap_time < global_best_time)):
                        global_best_time = d.last_lap_time
                        global_best_name = d.name
                        _emit("fastest_lap", {
                            "driver":    d.name,
                            "car_num":   d.car_num,
                            "lap_time":  d.last_lap_time,
                            "lap":       d.lap,
                            "is_player": d.is_player,
                        })

                # Position change (pass)
                prev_pos = prev_positions.get(d.idx, d.position)
                if prev_pos != d.position and abs(prev_pos - d.position) >= position_thresh:
                    if cfg.get("announce_passes", True) and d.position < prev_pos:
                        _emit("position_change", {
                            "driver":      d.name,
                            "car_num":     d.car_num,
                            "from_pos":    prev_pos,
                            "to_pos":      d.position,
                            "lap":         d.lap,
                            "is_player":   d.is_player,
                            "is_lead_change": (d.position == 1),
                        })

                # Incident points
                prev_inc = prev_incidents.get(d.idx, d.incidents)
                delta_inc = d.incidents - prev_inc
                if delta_inc >= incident_thresh and cfg.get("announce_incidents", True):
                    _emit("incident", {
                        "driver":    d.name,
                        "car_num":   d.car_num,
                        "delta":     delta_inc,
                        "total":     d.incidents,
                        "position":  d.position,
                        "lap":       d.lap,
                        "is_player": d.is_player,
                    })

                # Pit road
                prev_p = prev_pit.get(d.idx, d.on_pit_road)
                if prev_p != d.on_pit_road and cfg.get("announce_pit", True):
                    _emit("pit_entry" if d.on_pit_road else "pit_exit", {
                        "driver":    d.name,
                        "car_num":   d.car_num,
                        "position":  d.position,
                        "lap":       d.lap,
                        "is_player": d.is_player,
                    })

                # Update snapshots
                prev_positions[d.idx]  = d.position
                prev_laps[d.idx]       = d.lap
                prev_incidents[d.idx]  = d.incidents
                prev_pit[d.idx]        = d.on_pit_road

            # ---- Periodic standings telemetry event ---------------------
            if live and backend.current_lap() % 5 == 0 and live[0].lap_pct < 0.02:
                top_five = [
                    {"pos": d.position, "driver": d.name, "car_num": d.car_num,
                     "lap": d.lap, "gap": round(d.gap_to_leader, 2)}
                    for d in live[:5]
                ]
                _emit("standings_update", {
                    "lap":       backend.current_lap(),
                    "total_laps":backend.total_laps(),
                    "top_five":  top_five,
                    "flag":      flag,
                })

            # Race end
            if sess_state == "Checkered" and live:
                winner = next((d for d in live if d.position == 1), live[0])
                _emit("race_finish", {
                    "winner":     winner.name,
                    "winner_num": winner.car_num,
                    "laps_run":   winner.lap,
                    "track":      backend.track_name(),
                    "series":     backend.series_name(),
                    "top_five": [
                        {"pos": d.position, "driver": d.name, "best_time": d.best_lap_time}
                        for d in live[:5]
                    ],
                })
                _candidate(
                    f"Race Result: {backend.series_name()} — {winner.name} wins!",
                    f"{winner.name} (#{winner.car_num}) takes the victory at "
                    f"{backend.track_name()} in the {backend.series_name()}.",
                    ["iracing","race_result","winner"],
                    priority=92.0,
                )
                # After checkered don't spam; wait a while
                time.sleep(30.0)

        except Exception as exc:
            log("iracing_sdk", f"feed_worker error: {exc}")
            time.sleep(2.0)

        time.sleep(dt)

    backend.disconnect()
    log("iracing_sdk", "Feed worker stopped.")
