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
import queue
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Plugin metadata
# ---------------------------------------------------------------------------
PLUGIN_NAME    = "iracing_sdk"
PLUGIN_DESC    = "Live iRacing telemetry feed — emits race events for the AI commentator."
IS_FEED        = True

# ---------------------------------------------------------------------------
# Module-level shared state — readable by iracing_director without needing
# the per-worker runtime dict (which is a different object from shared_runtime).
# ---------------------------------------------------------------------------
_live_state: Dict[str, Any] = {}          # updated in-place by feed_worker each tick
_cam_cmd_q: "queue.Queue[Dict[str,Any]]" = None  # created lazily (needs queue module)
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
    "announce_weather_changes": True,
    "announce_fuel_warning":    True,
    "announce_lap_delta":       True,
    "announce_laps_to_go":      True,
    "fuel_warning_pct":         0.20,      # warn player when fuel fraction drops below this
    "laps_to_go_marks":         [5, 3, 1], # fire countdown commentary at these laps-remaining values
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
    idx:          int
    name:         str
    car:          str
    car_num:      str
    irating:      int   = 0
    team_name:    str   = ""
    license:      str   = ""
    car_class:    str   = ""     # short class name e.g. "GT3", "LMP2"
    car_class_id: int   = 0
    abbrev_name:  str   = ""     # abbreviated name e.g. "A.Smith"
    is_ai:        bool  = False

@dataclass
class LiveDriver:
    idx:             int
    name:            str
    car_num:         str
    position:        int   = 0      # 1-based overall on-track position
    class_position:  int   = 0      # 1-based position within car class
    car_class_id:    int   = 0
    lap:             int   = 0
    lap_pct:         float = 0.0
    last_lap_time:   float = -1.0
    best_lap_time:   float = -1.0
    incidents:       int   = 0
    on_pit_road:     bool  = False
    is_player:       bool  = False
    dnf:             bool  = False
    gap_to_leader:   float = 0.0    # seconds behind leader (CarIdxF2Time)
    f2_time:         float = 0.0    # raw CarIdxF2Time value
    est_time:        float = 0.0    # estimated time to complete current lap
    gear:            int   = 0      # current gear (0=N, -1=R)
    track_surface:   int   = 3      # -1=NotInWorld 0=OffTrack 1=InPitStall 2=Approaching 3=OnTrack

@dataclass
class PlayerTelemetry:
    """Real-time telemetry for the player's car only."""
    speed_ms:            float = 0.0    # m/s
    speed_kph:           float = 0.0    # km/h
    rpm:                 float = 0.0
    gear:                int   = 0      # 0=N, -1=R
    throttle:            float = 0.0    # 0.0–1.0
    brake:               float = 0.0    # 0.0–1.0
    fuel_level:          float = 0.0    # litres remaining
    fuel_pct:            float = 0.0    # fraction of full tank (0.0–1.0)
    fuel_use_per_hr:     float = 0.0    # litres/hour burn rate
    oil_temp:            float = 0.0    # Celsius
    water_temp:          float = 0.0    # Celsius
    lap_current_time:    float = -1.0   # running lap time in seconds
    lap_delta_best:      float = 0.0    # delta vs personal best (+ = slower)
    lap_delta_session:   float = 0.0    # delta vs session fastest
    is_on_track:         bool  = False
    team_incident_count: int   = 0
    fast_repairs_used:   int   = 0

@dataclass
class WeatherData:
    """Live weather snapshot."""
    air_temp:      float = 22.0   # Celsius
    track_temp:    float = 30.0   # Celsius
    wind_vel:      float = 0.0    # m/s
    wind_dir:      float = 0.0    # radians clockwise from N
    humidity:      float = 0.5    # 0–1
    fog_level:     float = 0.0    # 0–1
    skies:         int   = 0      # 0=Clear 1=PartlyCloudy 2=MostlyCloudy 3=Overcast
    track_wetness: int   = 0      # 0=Dry … 5=VeryWet
    declared_wet:  bool  = False

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
                if d.get("IsSpectator", 0):
                    continue  # skip spectators / pace car
                result.append(DriverInfo(
                    idx=int(d.get("CarIdx", 0)),
                    name=str(d.get("UserName", "Unknown")),
                    car=str(d.get("CarPath", "")),
                    car_num=str(d.get("CarNumber", "?")),
                    irating=int(d.get("IRating", 0)),
                    team_name=str(d.get("TeamName", "")),
                    license=str(d.get("LicString", "")),
                    car_class=str(d.get("CarClassShortName", "")),
                    car_class_id=int(d.get("CarClassID", 0)),
                    abbrev_name=str(d.get("AbbrevName", "")),
                    is_ai=bool(d.get("IsMyAIDriver", 0)),
                ))
            return result
        except Exception:
            return []

    def live_drivers(self, driver_map: Dict[int, DriverInfo]) -> List[LiveDriver]:
        """Sample real-time per-car arrays and return LiveDriver list."""
        try:
            lap_dist_pct = list(self._ir["CarIdxLapDistPct"]    or [])
            lap_num      = list(self._ir["CarIdxLap"]           or [])
            last_lap     = list(self._ir["CarIdxLastLapTime"]   or [])
            best_lap     = list(self._ir["CarIdxBestLapTime"]   or [])
            incidents    = list(self._ir["CarIdxInc"]           or [])
            on_pit       = list(self._ir["CarIdxOnPitRoad"]     or [])
            f2_times     = list(self._ir["CarIdxF2Time"]        or [])  # seconds behind leader
            est_times    = list(self._ir["CarIdxEstTime"]       or [])  # est. lap completion time
            gears        = list(self._ir["CarIdxGear"]          or [])  # current gear
            surfaces     = list(self._ir["CarIdxTrackSurface"]  or [])  # surface enum
            class_pos    = list(self._ir["CarIdxClassPosition"] or [])  # within-class position
            car_classes  = list(self._ir["CarIdxClass"]         or [])  # class index
            player_car_idx = int(self._ir["PlayerCarIdx"] or 0)

            drivers = []
            for idx, info in driver_map.items():
                if idx >= len(lap_dist_pct):
                    continue
                pct = float(lap_dist_pct[idx] if idx < len(lap_dist_pct) else 0.0)
                lap = int(lap_num[idx] if idx < len(lap_num) else 0)
                f2  = float(f2_times[idx]) if idx < len(f2_times) else 0.0
                drivers.append(LiveDriver(
                    idx=idx,
                    name=info.name,
                    car_num=info.car_num,
                    car_class_id=int(car_classes[idx]) if idx < len(car_classes) else info.car_class_id,
                    lap=max(lap, 0),
                    lap_pct=max(pct, 0.0),
                    last_lap_time=float(last_lap[idx]) if idx < len(last_lap) else -1.0,
                    best_lap_time=float(best_lap[idx]) if idx < len(best_lap) else -1.0,
                    incidents=int(incidents[idx]) if idx < len(incidents) else 0,
                    on_pit_road=bool(on_pit[idx]) if idx < len(on_pit) else False,
                    is_player=(idx == player_car_idx),
                    f2_time=f2,
                    gap_to_leader=f2 if f2 > 0 else 0.0,
                    est_time=float(est_times[idx]) if idx < len(est_times) else 0.0,
                    gear=int(gears[idx]) if idx < len(gears) else 0,
                    track_surface=int(surfaces[idx]) if idx < len(surfaces) else 3,
                    class_position=int(class_pos[idx]) if idx < len(class_pos) else 0,
                ))

            # Derive overall positions: higher (lap + pct) = better
            drivers.sort(key=lambda d: (d.lap + d.lap_pct), reverse=True)
            for pos, d in enumerate(drivers, start=1):
                d.position = pos

            return drivers
        except Exception:
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

    def player_telemetry(self) -> "PlayerTelemetry":
        """Read live telemetry for the player's car."""
        try:
            speed_ms = float(self.var("Speed", 0.0))
            return PlayerTelemetry(
                speed_ms=speed_ms,
                speed_kph=speed_ms * 3.6,
                rpm=float(self.var("RPM", 0.0)),
                gear=int(self.var("Gear", 0)),
                throttle=float(self.var("Throttle", 0.0)),
                brake=float(self.var("Brake", 0.0)),
                fuel_level=float(self.var("FuelLevel", 0.0)),
                fuel_pct=float(self.var("FuelLevelPct", 0.0)),
                fuel_use_per_hr=float(self.var("FuelUsePerHour", 0.0)),
                oil_temp=float(self.var("OilTemp", 0.0)),
                water_temp=float(self.var("WaterTemp", 0.0)),
                lap_current_time=float(self.var("LapCurrentLapTime", -1.0)),
                lap_delta_best=float(self.var("LapDeltaToBestLap", 0.0)),
                lap_delta_session=float(self.var("LapDeltaToSessionBestLap", 0.0)),
                is_on_track=bool(self.var("IsOnTrack", False)),
                team_incident_count=int(self.var("PlayerCarTeamIncidentCount", 0)),
                fast_repairs_used=int(self.var("PlayerFastRepairsUsed", 0)),
            )
        except Exception:
            return PlayerTelemetry()

    def weather(self) -> "WeatherData":
        """Read current weather snapshot."""
        try:
            return WeatherData(
                air_temp=float(self.var("AirTemp", 22.0)),
                track_temp=float(self.var("TrackTemp", 30.0)),
                wind_vel=float(self.var("WindVel", 0.0)),
                wind_dir=float(self.var("WindDir", 0.0)),
                humidity=float(self.var("RelativeHumidity", 0.5)),
                fog_level=float(self.var("FogLevel", 0.0)),
                skies=int(self.var("Skies", 0)),
                track_wetness=int(self.var("TrackWetness", 0)),
                declared_wet=bool(self.var("WeatherDeclaredWet", False)),
            )
        except Exception:
            return WeatherData()

    def session_laps_remain(self) -> int:
        try:
            v = self._ir["SessionLapsRemainEx"]
            if v is None:
                v = self._ir["SessionLapsRemain"]
            val = int(v or 0)
            return val if val < 32767 else 0  # 32767 = unlimited/timed race
        except Exception:
            return 0

    def session_time_remain(self) -> float:
        try:
            return max(0.0, float(self.var("SessionTimeRemain", 0.0)))
        except Exception:
            return 0.0

    def track_type(self) -> str:
        """Returns 'road', 'oval', 'dirtOval', or 'dirtRoad'."""
        try:
            wi = self._ir["WeekendInfo"] or {}
            return str(wi.get("TrackType", "road")).lower()
        except Exception:
            return "road"

    def event_type(self) -> str:
        """Returns 'Practice', 'Qualify', 'Race', etc."""
        try:
            wi = self._ir["WeekendInfo"] or {}
            return str(wi.get("EventType", "Race"))
        except Exception:
            return "Race"

    def num_car_classes(self) -> int:
        try:
            wi = self._ir["WeekendInfo"] or {}
            return max(1, int(wi.get("NumCarClasses", 1)))
        except Exception:
            return 1

    def radio_transmit_car_idx(self) -> int:
        """Index of the car currently transmitting on team radio (-1 if none)."""
        try:
            v = self.var("RadioTransmitCarIdx", -1)
            return int(v) if v is not None else -1
        except Exception:
            return -1

    def cam_switch_car(self, car_num: int, group: int = 1, camera: int = 0) -> bool:
        """Direct iRacing to follow car_num in the given camera group/camera index."""
        if not self.connected:
            return False
        try:
            self._ir.cam_switch_num(car_num, group, camera)
            return True
        except Exception:
            return False

    def camera_groups(self) -> List[Dict[str, Any]]:
        """Return list of {num, name} dicts from iRacing CameraInfo."""
        try:
            ci = self._ir["CameraInfo"] or {}
            return [
                {"num": int(g.get("GroupNum", 0)), "name": str(g.get("GroupName", ""))}
                for g in (ci.get("Groups") or [])
            ]
        except Exception:
            return []


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

    def player_telemetry(self) -> "PlayerTelemetry":
        player = next((d for d in self._live if d.is_player), None)
        fuel_pct = max(0.0, 1.0 - (self._current_lap / max(self._total_laps, 1)))
        lap_t    = self._base_lap_time
        cur_pct  = player.lap_pct if player else 0.0
        return PlayerTelemetry(
            speed_ms=55.0,
            speed_kph=198.0,
            rpm=7200.0,
            gear=4,
            throttle=0.85,
            brake=0.0,
            fuel_level=round(fuel_pct * 50.0, 1),
            fuel_pct=round(fuel_pct, 3),
            fuel_use_per_hr=2.8,
            oil_temp=96.0,
            water_temp=87.0,
            lap_current_time=round(lap_t * cur_pct, 3) if cur_pct > 0 else -1.0,
            lap_delta_best=round(self._rng.gauss(0.0, 0.12), 3),
            lap_delta_session=round(self._rng.gauss(0.4, 0.2), 3),
            is_on_track=(self._session_state == "Racing"),
            team_incident_count=player.incidents if player else 0,
        )

    def weather(self) -> "WeatherData":
        return WeatherData(
            air_temp=22.0,
            track_temp=35.0,
            wind_vel=round(self._rng.uniform(0, 3), 1),
            wind_dir=round(self._rng.uniform(0, 6.28), 2),
            humidity=0.55,
            fog_level=0.0,
            skies=1,
            track_wetness=0,
            declared_wet=False,
        )

    def session_laps_remain(self) -> int:
        return max(0, self._total_laps - self._current_lap)

    def session_time_remain(self) -> float:
        return float(self.session_laps_remain() * self._base_lap_time)

    def track_type(self) -> str:
        t = self._track.lower()
        return "oval" if any(w in t for w in ("daytona", "oval", "speedway", "nascar")) else "road"

    def event_type(self) -> str:
        return "Race"

    def num_car_classes(self) -> int:
        return 1

    def radio_transmit_car_idx(self) -> int:
        # Simulate occasional radio chatter
        if self._rng.random() < 0.008:
            return self._rng.randint(0, max(0, len(self._live) - 1))
        return -1

    def cam_switch_car(self, car_num: int, group: int = 1, camera: int = 0) -> bool:
        return False  # simulation does not support camera control

    def camera_groups(self) -> List[Dict[str, Any]]:
        return []  # no camera info in simulation mode

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

        # Simulated gap to leader
        if active:
            leader_prog = active[0].lap + active[0].lap_pct
            for d in active:
                delta = leader_prog - (d.lap + d.lap_pct)
                d.gap_to_leader = delta * self._base_lap_time if d.position > 1 else 0.0
                d.f2_time = d.gap_to_leader

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
    prev_wetness:       int           = -1
    laps_to_go_announced: set         = set()
    last_fuel_warned:   bool          = False
    prev_radio_idx:     int           = -1
    last_delta_ts:      float         = 0.0
    tire_stints:        Dict[int,int]  = {}   # idx → laps on current tyre set
    gap_history:        Dict[str,list] = {}   # "idxA:idxB" → [(ts, gap_s), ...]
    battle_active:      Dict[str,float]= {}   # "idxA:idxB" → first_close_ts
    last_battle_emit:   Dict[str,float]= {}   # "idxA:idxB" → last emit ts

    def _emit(etype: str, data: Dict[str, Any]) -> None:
        """Push an event onto event_q."""
        try:
            ev = StationEvent(
                source="iracing_sdk",
                type=etype,
                ts=int(time.time()),
                payload=data,
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
                    "from":        prev_session_state,
                    "to":          sess_state,
                    "track":       backend.track_name(),
                    "series":      backend.series_name(),
                    "total_laps":  backend.total_laps(),
                    "air_temp":    backend.air_temp(),
                    "track_temp":  backend.track_temp(),
                    "track_type":  backend.track_type(),
                    "event_type":  backend.event_type(),
                    "num_classes": backend.num_car_classes(),
                })
                if sess_state == "Racing" and not session_started:
                    session_started = True
                    # Only emit race-start candidate for actual Race sessions,
                    # not for Practice or Qualifying (which also use "Racing" state)
                    _evt_type = backend.event_type()
                    if _evt_type == "Race":
                        _candidate(
                            f"Race LIVE: {backend.series_name()} at {backend.track_name()}",
                            f"The {backend.series_name()} race at {backend.track_name()} has gone green! "
                            f"{backend.total_laps()} laps of sim racing ahead.",
                            ["iracing", "race_start", "live"],
                            priority=95.0,
                        )
                prev_session_state = sess_state

            # ---- Flag changes -------------------------------------------
            flag = backend.flag_str()
            if flag != prev_flag and cfg.get("announce_flags", True):
                _emit("flag_change", {
                    "flag":         flag,
                    "lap":          backend.current_lap(),
                    "track":        backend.track_name(),
                    "laps_remain":  backend.session_laps_remain(),
                    "time_remain":  round(backend.session_time_remain(), 0),
                })
                prev_flag = flag

            # ---- Weather changes ----------------------------------------
            if cfg.get("announce_weather_changes", True):
                wx = backend.weather()
                if prev_wetness >= 0 and wx.track_wetness != prev_wetness:
                    _WETNESS = ["dry","slightly damp","damp","wet","very wet","extremely wet"]
                    _emit("weather_change", {
                        "wetness_level": wx.track_wetness,
                        "wetness_desc":  _WETNESS[min(wx.track_wetness, 5)],
                        "prev_wetness":  prev_wetness,
                        "air_temp":      round(wx.air_temp, 1),
                        "track_temp":    round(wx.track_temp, 1),
                        "wind_vel":      round(wx.wind_vel, 1),
                        "declared_wet":  wx.declared_wet,
                        "lap":           backend.current_lap(),
                    })
                prev_wetness = wx.track_wetness

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

            # Update module-level shared live state — readable by iracing_director
            # (the per-worker runtime dict is a different object from shared_runtime,
            # so we use module-level state as the cross-plugin communication channel)
            _live_state.clear()
            _live_state.update({
                "connected":   backend.connected,
                "session":     backend.event_type(),
                "track":       backend.track_name(),
                "lap":         backend.current_lap(),
                "total_laps":  backend.total_laps(),
                "cam_groups":  backend.camera_groups(),   # [{num, name}]
                "drivers": [
                    {
                        "car_num":      d.car_num,
                        "name":         d.name,
                        "position":     d.position,
                        "lap":          d.lap,
                        "last_lap":     d.last_lap_time,
                        "best_lap":     d.best_lap_time,
                        "gap":          d.gap_to_leader,
                        "on_pit":       d.on_pit_road,
                        "incidents":    d.incidents,
                        # -1=NotInWorld 0=OffTrack 1=InPitStall 2=Approaching 3=OnTrack
                        "track_surface":  d.track_surface,
                        "tire_stint":     tire_stints.get(d.idx, 0),
                    }
                    for d in live
                ],
                "battles": [],   # populated below after battle detection
            })

            for d in live:
                # Lap completion
                prev_lap = prev_laps.get(d.idx, -1)
                if prev_lap >= 0 and d.lap > prev_lap and cfg.get("announce_lap_completions", True):
                    tire_stints[d.idx] = tire_stints.get(d.idx, 0) + 1
                    _emit("lap_complete", {
                        "driver":         d.name,
                        "car_num":        d.car_num,
                        "position":       d.position,
                        "class_position": d.class_position,
                        "lap":            d.lap,
                        "lap_time":       d.last_lap_time,
                        "best_time":      d.best_lap_time,
                        "total_laps":     backend.total_laps(),
                        "laps_remain":    backend.session_laps_remain(),
                        "gap_to_leader":  d.gap_to_leader,
                        "f2_time":        d.f2_time,
                        "is_player":      d.is_player,
                        "on_pit_road":    d.on_pit_road,
                        "irating":        driver_map[d.idx].irating if d.idx in driver_map else 0,
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
                            "driver":         d.name,
                            "car_num":        d.car_num,
                            "from_pos":       prev_pos,
                            "to_pos":         d.position,
                            "lap":            d.lap,
                            "is_player":      d.is_player,
                            "is_lead_change": (d.position == 1),
                            "gap_to_leader":  d.gap_to_leader,
                            "laps_remain":    backend.session_laps_remain(),
                            "class_position": d.class_position,
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
                    _stint = tire_stints.get(d.idx, 0)
                    if not d.on_pit_road:
                        tire_stints[d.idx] = 0   # fresh rubber on exit
                    _emit("pit_entry" if d.on_pit_road else "pit_exit", {
                        "driver":          d.name,
                        "car_num":         d.car_num,
                        "position":        d.position,
                        "lap":             d.lap,
                        "laps_remain":     backend.session_laps_remain(),
                        "is_player":       d.is_player,
                        "tire_stint_laps": _stint,
                    })

                # Update snapshots
                prev_positions[d.idx]  = d.position
                prev_laps[d.idx]       = d.lap
                prev_incidents[d.idx]  = d.incidents
                prev_pit[d.idx]        = d.on_pit_road

            # ---- Player telemetry events --------------------------------
            player_car = next((d for d in live if d.is_player), None)
            if player_car and sess_state == "Racing":
                pt = backend.player_telemetry()
                fuel_warn_pct = float(cfg.get("fuel_warning_pct", FEED_DEFAULTS["fuel_warning_pct"]))

                # Fuel warning
                if (cfg.get("announce_fuel_warning", True)
                        and 0 < pt.fuel_pct <= fuel_warn_pct
                        and not last_fuel_warned):
                    _emit("fuel_warning", {
                        "driver":          player_car.name,
                        "car_num":         player_car.car_num,
                        "fuel_pct":        round(pt.fuel_pct, 3),
                        "fuel_level":      round(pt.fuel_level, 1),
                        "fuel_use_per_hr": round(pt.fuel_use_per_hr, 2),
                        "laps_remain":     backend.session_laps_remain(),
                        "position":        player_car.position,
                        "lap":             player_car.lap,
                        "is_player":       True,
                    })
                    last_fuel_warned = True
                elif pt.fuel_pct > fuel_warn_pct + 0.05:
                    last_fuel_warned = False  # reset after pit/refuel

                # Lap delta — fire when player is beating the session best
                if (cfg.get("announce_lap_delta", True)
                        and pt.lap_current_time > 10.0
                        and pt.lap_delta_session < -0.15
                        and (time.time() - last_delta_ts) > 20.0):
                    _emit("lap_delta", {
                        "driver":           player_car.name,
                        "car_num":          player_car.car_num,
                        "delta":            round(abs(pt.lap_delta_session), 3),
                        "delta_sign":       "-",
                        "position":         player_car.position,
                        "lap":              player_car.lap,
                        "is_player":        True,
                        "vs":               "session_best",
                        "current_lap_time": round(pt.lap_current_time, 3),
                    })
                    last_delta_ts = time.time()

            # ---- Laps to go countdown -----------------------------------
            if cfg.get("announce_laps_to_go", True) and sess_state == "Racing":
                laps_remain = backend.session_laps_remain()
                marks = list(cfg.get("laps_to_go_marks", FEED_DEFAULTS["laps_to_go_marks"]))
                if laps_remain in marks and laps_remain not in laps_to_go_announced:
                    leader = live[0] if live else None
                    _emit("laps_to_go", {
                        "laps_remain": laps_remain,
                        "leader":      leader.name if leader else "?",
                        "leader_num":  leader.car_num if leader else "?",
                        "gap_p2":      round(live[1].gap_to_leader, 2) if len(live) > 1 else 0.0,
                        "track":       backend.track_name(),
                        "series":      backend.series_name(),
                    })
                    laps_to_go_announced.add(laps_remain)

            # ---- Radio chatter ------------------------------------------
            radio_idx = backend.radio_transmit_car_idx()
            if (radio_idx >= 0 and radio_idx != prev_radio_idx
                    and radio_idx in driver_map):
                rd       = driver_map[radio_idx]
                car_live = next((d for d in live if d.idx == radio_idx), None)
                if car_live:
                    _emit("radio_chatter", {
                        "driver":    rd.name,
                        "car_num":   rd.car_num,
                        "position":  car_live.position,
                        "lap":       car_live.lap,
                        "is_player": car_live.is_player,
                    })
            prev_radio_idx = radio_idx

            # ---- Battle detection (gap history per adjacent pair) ------
            _BCLS = 1.5    # seconds: within = battle
            _BMIN = 8.0    # seconds close before emitting 'ongoing'
            _BTRN = 0.35   # gap must close by this much to be 'building'
            _BCD  = 20.0   # per-pair emit cooldown
            _BHST = 12.0   # gap history window (s)
            _now_b = time.time()
            _sb = sorted(
                [d for d in live
                 if d.track_surface in (2, 3)
                 and str(d.car_num) != "0"
                 and "pace" not in d.name.lower()],
                key=lambda d: d.position
            )
            _battle_list = []
            for _bi in range(len(_sb) - 1):
                _a, _b = _sb[_bi], _sb[_bi + 1]
                _gap = max(0.0, _b.gap_to_leader - _a.gap_to_leader)
                _bkey = f"{min(_a.idx,_b.idx)}:{max(_a.idx,_b.idx)}"
                _hist = gap_history.setdefault(_bkey, [])
                _hist.append((_now_b, _gap))
                _hist[:] = [(t, g) for t, g in _hist if _now_b - t <= _BHST]
                if _gap <= _BCLS and len(_hist) >= 3:
                    _battle_list.append({
                        "a_num": _a.car_num, "a_name": _a.name, "a_pos": _a.position,
                        "b_num": _b.car_num, "b_name": _b.name, "b_pos": _b.position,
                        "gap":   round(_gap, 3),
                    })
                    if _bkey not in battle_active:
                        battle_active[_bkey] = _now_b
                    _dur   = _now_b - battle_active[_bkey]
                    _trend = _hist[0][1] - _gap   # positive = gap closing
                    _le    = last_battle_emit.get(_bkey, 0.0)
                    if _now_b - _le >= _BCD:
                        if _dur < _BMIN and _trend > _BTRN:
                            _emit("battle_building", {
                                "chaser":     _b.name, "chaser_num": _b.car_num,
                                "chaser_pos": _b.position,
                                "leader":     _a.name, "leader_num": _a.car_num,
                                "leader_pos": _a.position,
                                "gap":        round(_gap, 3),
                                "gap_trend":  round(_trend, 3),
                                "lap":        _a.lap,
                            })
                            last_battle_emit[_bkey] = _now_b
                        elif _dur >= _BMIN:
                            _emit("battle_ongoing", {
                                "chaser":     _b.name, "chaser_num": _b.car_num,
                                "chaser_pos": _b.position,
                                "leader":     _a.name, "leader_num": _a.car_num,
                                "leader_pos": _a.position,
                                "gap":        round(_gap, 3),
                                "duration":   int(_dur),
                                "lap":        _a.lap,
                            })
                            last_battle_emit[_bkey] = _now_b
                else:
                    battle_active.pop(_bkey, None)
                    gap_history.pop(_bkey, None)
                    last_battle_emit.pop(_bkey, None)
            _live_state["battles"] = _battle_list

            # ---- Periodic standings telemetry event ---------------------
            if live and backend.current_lap() % 5 == 0 and live[0].lap_pct < 0.02:
                top_five = [
                    {"pos": d.position, "driver": d.name, "car_num": d.car_num,
                     "lap": d.lap, "gap": round(d.gap_to_leader, 2),
                     "is_player": d.is_player, "class_position": d.class_position}
                    for d in live[:5]
                ]
                wx = backend.weather()
                _emit("standings_update", {
                    "lap":           backend.current_lap(),
                    "total_laps":    backend.total_laps(),
                    "laps_remain":   backend.session_laps_remain(),
                    "time_remain":   round(backend.session_time_remain(), 0),
                    "top_five":      top_five,
                    "flag":          flag,
                    "track_temp":    round(wx.track_temp, 1),
                    "track_wetness": wx.track_wetness,
                    "wind_vel":      round(wx.wind_vel, 1),
                })

            # Race end
            if sess_state == "Checkered" and live:
                winner = next((d for d in live if d.position == 1), live[0])
                _emit("race_finish", {
                    "winner":             winner.name,
                    "winner_num":         winner.car_num,
                    "laps_run":           winner.lap,
                    "track":              backend.track_name(),
                    "series":             backend.series_name(),
                    "fastest_lap_time":   global_best_time,
                    "fastest_lap_driver": global_best_name,
                    "top_five": [
                        {"pos": d.position, "driver": d.name, "car_num": d.car_num,
                         "best_time": d.best_lap_time, "is_player": d.is_player}
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

        # Drain camera commands queued by the director plugin via module-level queue
        if _cam_cmd_q is not None:
            while True:
                try:
                    cmd = _cam_cmd_q.get_nowait()
                    backend.cam_switch_car(
                        int(cmd.get("car_num", 0)),
                        int(cmd.get("group", 1)),
                        int(cmd.get("camera", 0)),
                    )
                except Exception:
                    break

        time.sleep(dt)

    backend.disconnect()
    log("iracing_sdk", "Feed worker stopped.")
