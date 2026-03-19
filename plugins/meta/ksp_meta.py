"""
KSP Meta Plugin
===============
Transforms raw KSP telemetry events (from ksp_sdk.py) into live, two-voice
broadcast commentary using the LLM pipeline wired into Radio OS.

Architecture
------------
  ksp_sdk event_q  ← events pushed by ksp_sdk.py feed worker
        │
  EventClassifier  ← tier the event (CRITICAL / NOTABLE / ROUTINE / AMBIENT)
        │
  CommentaryWorker ← background thread picks highest-tier pending event
        │
  LLM pipeline     ← uses runtime["llm_generate"] to write commentary
        │
  emit into db     ← bookmark.py picks it up for TTS / audio

Two voices
----------
  launch_control (pbp)   — immediate, technical, exclamatory flight calls
  flight_director (color) — strategic, analytical, what-comes-next commentary

Both voices should be configured in the station manifest under characters.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# MetaPluginBase import
# ---------------------------------------------------------------------------
try:
    from bookmark import MetaPluginBase
except ImportError:
    from abc import ABC, abstractmethod
    class MetaPluginBase(ABC):  # type: ignore
        @abstractmethod
        def initialize(self, runtime_context, cfg, mem): pass
        @abstractmethod
        def shutdown(self): pass
        def curate_candidates(self, candidates, state): return []
        def generate_script(self, segment, state): return {"lines": []}
        def generate_narration(self, events, context): return ""
        def delegate_decision(self, available_actions, state, identity, focus): return None


# ---------------------------------------------------------------------------
# Event tier
# ---------------------------------------------------------------------------

class Tier(Enum):
    CRITICAL = 4   # launch, explosion, orbit, landing, mission success/fail
    NOTABLE  = 3   # stage separation, max-Q, maneuver, reentry, resource warn
    ROUTINE  = 2   # altitude check, resource update
    AMBIENT  = 1   # background telemetry


_TIER_MAP: Dict[str, Tier] = {
    # Critical
    "launch":              Tier.CRITICAL,
    "orbit_achieved":      Tier.CRITICAL,
    "touchdown":           Tier.CRITICAL,
    "splashdown":          Tier.CRITICAL,
    "mission_start":       Tier.CRITICAL,
    # Notable
    "stage_separation":    Tier.NOTABLE,
    "max_q":               Tier.NOTABLE,
    "maneuver_executed":   Tier.NOTABLE,
    "engine_cutoff":       Tier.NOTABLE,
    "reentry_start":       Tier.NOTABLE,
    "gforce_spike":        Tier.NOTABLE,
    "resource_warning":    Tier.NOTABLE,
    "rendezvous_approach": Tier.NOTABLE,
    "eva_start":           Tier.NOTABLE,
    "eva_end":             Tier.NOTABLE,
    "altitude_milestone":  Tier.NOTABLE,
    "docking_complete":    Tier.NOTABLE,
    # Routine
    "resource_update":     Tier.ROUTINE,
    "heading_check":       Tier.ROUTINE,
    # Ambient
    "agent_action":        Tier.AMBIENT,
}


def _classify(event_type: str, data: Dict[str, Any]) -> Tier:
    t = _TIER_MAP.get(event_type, Tier.AMBIENT)
    # Karman line crossing is as big as orbit
    if event_type == "altitude_milestone" and data.get("altitude_m", 0) >= 70_000:
        t = Tier.CRITICAL
    return t


# ---------------------------------------------------------------------------
# System prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_LC = """/no_think
You are {lc_name}, the launch commentator for {station_name}.
You call every moment of this Kerbal Space Program mission as it HAPPENS — vivid, technical, immediate.
Keep each call to 1-2 punchy sentences. No bullet points. Spoken words only.
Use KSP/aerospace terminology naturally: apoapsis, periapsis, delta-v, staging, TWR, Isp.
Say altitudes naturally: "seventy thousand metres", "one hundred kilometres". Never say raw numbers without units.
Never invent data you weren't given. If a value is unknown say "we don't have that data".
Current mission: {vessel} — phase: {phase}.
Body: {body}. Atmosphere ceiling: ~{atm_depth_km} km.
Apoapsis: {apoapsis_km} km | Periapsis: {periapsis_km} km | Fuel: {fuel_pct}%.
Mission timeline so far:
{mission_bible}"""

_SYSTEM_FD = """/no_think
You are {fd_name}, the flight director for {station_name}.
CRITICAL: {lc_name} will call the action live. You MUST add only NEW information.
Your value: what this event means for the mission profile, what to expect next, risk assessment,
what the AI pilot should do next, or delta-v budget implications.
1-2 measured analytical sentences. No bullet points. No preamble. Spoken words only.
Never repeat anything {lc_name} already said. Never invent data.
Current mission: {vessel} — phase: {phase}.
Body: {body}. Apoapsis: {apoapsis_km} km | Periapsis: {periapsis_km} km | Fuel: {fuel_pct}%.
Mission timeline:
{mission_bible}"""


# ---------------------------------------------------------------------------
# Event prompt templates
# ---------------------------------------------------------------------------

_EVENT_PROMPTS: Dict[str, str] = {

    "mission_start": (
        "MISSION START: vessel '{vessel}' is on the pad and ready to fly.\n"
        "Manned: {manned}. Current phase: {phase}.\n"
        "Set the scene for the mission. What are we aiming for today?"
    ),

    "launch": (
        "LAUNCH! '{vessel}' ignites and lifts off!\n"
        "G-force at liftoff: {g_force:.1f}g. Vessel is manned: {manned}.\n"
        "Call the launch with energy. The mission clock has started."
    ),

    "stage_separation": (
        "STAGE SEPARATION: '{vessel}' just jettisoned stage {stage}!\n"
        "Altitude: {altitude_km} km | Speed: {speed_ms:.0f} m/s.\n"
        "Call the staging event. What does this mean for the ascent profile?"
    ),

    "max_q": (
        "MAX-Q: '{vessel}' is passing through maximum dynamic pressure!\n"
        "Altitude: {altitude_km} km | Speed: {speed_ms:.0f} m/s | Dyn pressure: {dyn_pressure_kpa:.1f} kPa.\n"
        "This is the highest aerodynamic stress point of the ascent. Call it."
    ),

    "altitude_milestone": (
        "ALTITUDE: '{vessel}' just passed {label}!\n"
        "Speed: {speed_ms:.0f} m/s | Apoapsis: {apoapsis_km} km.\n"
        "Mark this milestone. What does this altitude mean for the mission?"
    ),

    "orbit_achieved": (
        "ORBIT ACHIEVED! '{vessel}' has reached a stable orbit!\n"
        "Apoapsis: {apoapsis_km} km | Periapsis: {periapsis_km} km | "
        "Orbital speed: {orbital_speed_ms:.0f} m/s.\n"
        "This is a major milestone. Give the orbit insertion call."
    ),

    "maneuver_executed": (
        "MANEUVER COMPLETE: '{vessel}' has finished a burn.\n"
        "New apoapsis: {apoapsis_km} km | New periapsis: {periapsis_km} km.\n"
        "Apo change during burn: {delta_apo_km:.1f} km.\n"
        "What did this burn achieve? What is the mission status now?"
    ),

    "engine_cutoff": (
        "ENGINE CUTOFF: '{vessel}' engines have shut down.\n"
        "Altitude: {altitude_km} km | Apoapsis: {apoapsis_km} km.\n"
        "Was this planned? {expected_text} Call the cutoff."
    ),

    "resource_warning": (
        "WARNING: '{vessel}' is running critically low on {resource}!\n"
        "Current level: {pct:.1f}% remaining | Altitude: {altitude_km} km.\n"
        "This is a problem. React to the resource situation."
    ),

    "reentry_start": (
        "REENTRY: '{vessel}' is entering the atmosphere!\n"
        "Altitude: {altitude_km} km | Speed: {speed_ms:.0f} m/s | G-force: {g_force:.1f}g.\n"
        "Call the reentry. How is the vehicle holding up?"
    ),

    "gforce_spike": (
        "G-FORCE SPIKE: '{vessel}' is pulling {g_force:.1f} g's!\n"
        "Altitude: {altitude_km} km | Speed: {speed_ms:.0f} m/s.\n"
        "React to the stress. Is the crew/craft handling it?"
    ),

    "touchdown": (
        "TOUCHDOWN! '{vessel}' has landed safely!\n"
        "Touchdown speed: {speed_ms:.1f} m/s. Mission time: {mission_time_str}. Manned: {manned}.\n"
        "Give the landing call. Mission success or failure?"
    ),

    "splashdown": (
        "SPLASHDOWN! '{vessel}' has splashed down safely!\n"
        "Speed at splashdown: {speed_ms:.1f} m/s. Manned: {manned}.\n"
        "Call the splashdown. Are the crew safe?"
    ),

    "rendezvous_approach": (
        "RENDEZVOUS: '{vessel}' is closing on target — {distance_km:.2f} km away now!\n"
        "Call the approach. What procedures need to happen for docking?"
    ),

    "docking_complete": (
        "DOCKED! '{vessel}' has successfully docked!\n"
        "Call the docking achievement."
    ),

    "eva_start": (
        "EVA: A Kerbal from '{vessel}' is now on EVA at {altitude_km} km!\n"
        "React to the spacewalk. What are they out there to do?"
    ),

    "eva_end": (
        "EVA COMPLETE: The Kerbal from '{vessel}' has returned safely.\n"
        "Confirm the EVA is done. What was accomplished?"
    ),

    "resource_update": (
        "STATUS UPDATE — '{vessel}':\n"
        "Fuel: {fuel_pct:.1f}% | Monoprop: {mono_pct:.1f}% | Electric: {electric_pct:.1f}%\n"
        "Altitude: {altitude_km} km | Apoapsis: {apoapsis_km} km.\n"
        "Give a brief mission status call."
    ),

    "agent_action": (
        "AUTOPILOT ACTION: The AI pilot just executed '{action}'.\n"
        "Reason given: {reason}.\n"
        "React briefly — does this make sense? What will it achieve?"
    ),
}


def _build_user_prompt(event_type: str, data: Dict[str, Any]) -> str:
    template = _EVENT_PROMPTS.get(event_type)
    if not template:
        return f"Event: {event_type}\nData: {json.dumps(data, default=str)}\nReact to this mission event."

    # Pre-compute derived fields
    extra: Dict[str, Any] = {}

    alt_m = float(data.get("altitude_m", 0))
    extra["altitude_km"] = f"{alt_m / 1_000:.1f}"

    apo_m = float(data.get("apoapsis_m", 0))
    extra["apoapsis_km"] = f"{apo_m / 1_000:.1f}"

    peri_m = float(data.get("periapsis_m", 0))
    extra["periapsis_km"] = f"{peri_m / 1_000:.1f}"

    orb_ms = float(data.get("orbital_speed_ms", data.get("orbital_speed", 0)))
    extra["orbital_speed_ms"] = orb_ms

    delta_apo_m = float(data.get("delta_apo_m", 0))
    extra["delta_apo_km"] = delta_apo_m / 1_000

    dyn = float(data.get("dyn_pressure_pa", data.get("dynamic_pressure", 0)))
    extra["dyn_pressure_kpa"] = dyn / 1_000

    dist_m = float(data.get("distance_m", 0))
    extra["distance_km"] = dist_m / 1_000

    expected = bool(data.get("expected", True))
    extra["expected_text"] = ("This was a planned cutoff." if expected
                               else "This may be an unplanned shutdown!")

    mt = float(data.get("mission_time", 0))
    if mt > 0:
        h = int(mt // 3600)
        m = int((mt % 3600) // 60)
        s = int(mt % 60)
        extra["mission_time_str"] = f"T+{h:02d}:{m:02d}:{s:02d}"
    else:
        extra["mission_time_str"] = "unknown"

    extra["manned"] = "yes" if data.get("manned", True) else "no (unmanned)"

    merged = {**data, **extra}
    try:
        keys = _extract_keys(template)
        return template.format_map({k: merged.get(k, "?") for k in keys})
    except Exception:
        return f"Event: {event_type}\nData: {json.dumps(data, default=str)}"


def _extract_keys(s: str) -> List[str]:
    import string
    formatter = string.Formatter()
    return [fname for _, fname, _, _ in formatter.parse(s) if fname]


def _fmt_alt(m: float) -> str:
    if m >= 1_000_000:
        return f"{m/1_000_000:.1f} Mm"
    if m >= 1_000:
        return f"{m/1_000:.0f} km"
    return f"{m:.0f} m"


# ---------------------------------------------------------------------------
# Main meta plugin class
# ---------------------------------------------------------------------------

class KSPMetaPlugin(MetaPluginBase):
    """
    Live KSP broadcast commentary meta plugin.

    Consumes StationEvents from ksp_sdk and produces spoken two-voice
    commentary via the LLM pipeline.
    """

    def __init__(self):
        self._ctx: Dict[str, Any] = {}
        self._cfg: Dict[str, Any] = {}
        self._mem: Dict[str, Any] = {}
        self._log = print

        # Pacing
        self._last_call_ts:      float = 0.0
        self._min_gap_sec:       float = 5.0
        self._routine_gap_sec:   float = 30.0
        self._heartbeat_gap_sec: float = 20.0

        # Per-event-type cooldowns (seconds)
        self._cooldowns: Dict[str, float] = {
            "mission_start":       0.0,
            "launch":              0.0,
            "stage_separation":    5.0,
            "max_q":              10.0,
            "altitude_milestone": 15.0,
            "orbit_achieved":      0.0,
            "maneuver_executed":   8.0,
            "engine_cutoff":       8.0,
            "resource_warning":   60.0,
            "reentry_start":       0.0,
            "gforce_spike":       12.0,
            "touchdown":           0.0,
            "splashdown":          0.0,
            "rendezvous_approach": 20.0,
            "eva_start":          10.0,
            "eva_end":            10.0,
            "resource_update":    60.0,
            "agent_action":       15.0,
        }
        self._last_event_ts: Dict[str, float] = {}

        # Mission context
        self._mission_ctx: Dict[str, Any] = {
            "vessel":       "Unknown",
            "body":         "Kerbin",
            "atm_depth_km": 70,
            "phase":        "pre_launch",
            "apoapsis_m":   0.0,
            "periapsis_m":  0.0,
            "altitude_m":   0.0,
            "fuel_pct":     100.0,
            "stage":        0,
        }

        # Pending event queue for background worker
        self._pending:      Dict[str, tuple] = {}
        self._pending_lock  = threading.Lock()
        self._pending_evt   = threading.Event()
        self._stop_evt      = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        # Mission bible — rolling log of key events
        self._mission_timeline: List[str] = []
        self._bible_max: int = 12

        # Voice identities
        self._lc_name:      str = "Callum"       # launch control / PBP
        self._fd_name:      str = "Valentina"    # flight director / color
        self._station_name: str = "KSP Radio"

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def initialize(self, runtime_context: Dict[str, Any],
                   cfg: Dict[str, Any], mem: Dict[str, Any]) -> None:
        self._ctx = runtime_context
        self._cfg = cfg
        self._mem = mem
        self._log = runtime_context.get("log", print)

        pacing = cfg.get("pacing", {}) or {}
        self._min_gap_sec     = float(pacing.get("min_commentary_gap_sec",   self._min_gap_sec))
        self._routine_gap_sec = float(pacing.get("routine_commentary_gap_sec", self._routine_gap_sec))

        voices = cfg.get("characters") or {}
        self._lc_name  = str((voices.get("pbp")    or {}).get("name", "Callum"))
        self._fd_name  = str((voices.get("color")  or {}).get("name", "Valentina"))
        self._station_name = str((cfg.get("station") or {}).get("name", "KSP Radio"))

        self._log("ksp_meta", f"KSPMetaPlugin initialized — voices: "
                  f"lc={self._lc_name}, fd={self._fd_name}")

        self._stop_evt.clear()
        self._worker_thread = threading.Thread(
            target=self._commentary_worker,
            name="ksp_meta_worker",
            daemon=True,
        )
        self._worker_thread.start()

    def shutdown(self) -> None:
        self._stop_evt.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=3.0)
        self._log("ksp_meta", "KSPMetaPlugin shut down.")

    # =========================================================================
    # MetaPluginBase interface
    # =========================================================================

    def curate_candidates(self, candidates: List[Dict[str, Any]],
                           state: Any) -> List[Dict[str, Any]]:
        return [c for c in candidates if c.get("source") == "ksp_sdk"]

    def generate_script(self, segment: Dict[str, Any],
                         state: Any) -> Dict[str, Any]:
        if segment.get("script") and isinstance(segment.get("script"), list):
            return {}
        return self._generate_talk_segment(segment)

    def generate_narration(self, events: List[Any], context: Any) -> str:
        for ev in (events or []):
            if hasattr(ev, "source") and ev.source == "ksp_sdk":
                self._handle_ksp_event(ev)
        return ""

    def delegate_decision(self, available_actions, state, identity, focus) -> None:
        return None

    def handle_event(self, event: Any) -> None:
        if getattr(event, "source", "") == "ksp_sdk":
            self._handle_ksp_event(event)

    # =========================================================================
    # Event routing
    # =========================================================================

    def _handle_ksp_event(self, event: Any) -> None:
        etype = getattr(event, "type", "") or getattr(event, "event_type", "")
        data  = getattr(event, "payload", {}) or getattr(event, "data", {}) or {}

        self._update_mission_ctx(etype, data)

        tier     = _classify(etype, data)
        now      = time.time()
        cooldown = self._cooldowns.get(etype, 0.0)
        last_ts  = self._last_event_ts.get(etype, 0.0)

        if cooldown > 0 and (now - last_ts) < cooldown:
            return

        since_last = now - self._last_call_ts
        if tier.value <= Tier.ROUTINE.value and since_last < self._routine_gap_sec:
            return
        if since_last < self._min_gap_sec:
            return

        self._last_event_ts[etype] = now

        with self._pending_lock:
            self._pending[etype] = (tier, etype, data, now)
        self._pending_evt.set()

    def _update_mission_ctx(self, etype: str, data: Dict[str, Any]) -> None:
        mc = self._mission_ctx

        if "vessel" in data:
            mc["vessel"] = data["vessel"]
        if "altitude_m" in data:
            mc["altitude_m"] = data["altitude_m"]
        if "apoapsis_m" in data:
            mc["apoapsis_m"] = data["apoapsis_m"]
        if "periapsis_m" in data:
            mc["periapsis_m"] = data["periapsis_m"]
        if "fuel_pct" in data:
            mc["fuel_pct"] = data["fuel_pct"]
        if "stage" in data:
            mc["stage"] = data["stage"]

        # Phase updates
        if etype in ("launch",):
            mc["phase"] = "ascent"
        elif etype == "orbit_achieved":
            mc["phase"] = "orbit"
        elif etype == "maneuver_executed":
            mc["phase"] = "coast"
        elif etype == "reentry_start":
            mc["phase"] = "reentry"
        elif etype in ("touchdown", "splashdown"):
            mc["phase"] = "landed"
        elif etype == "mission_start":
            mc["phase"] = data.get("phase", "pre_launch")

        self._add_bible_entry(etype, data)

    def _add_bible_entry(self, etype: str, data: Dict[str, Any]) -> None:
        """Append a one-liner to the rolling mission timeline."""
        entry: Optional[str] = None
        alt_km = data.get("altitude_m", 0) / 1_000

        if etype == "mission_start":
            self._mission_timeline = []   # reset on new mission
            entry = f"Mission start: {data.get('vessel','?')} — {data.get('phase','?')}"
        elif etype == "launch":
            entry = f"T+0: LAUNCH — {data.get('vessel','?')}"
        elif etype == "stage_separation":
            entry = f"Stage {data.get('stage','?')} sep at {alt_km:.0f} km"
        elif etype == "max_q":
            entry = f"MaxQ at {alt_km:.0f} km"
        elif etype == "altitude_milestone":
            entry = f"Passed {data.get('label','?')} alt milestone"
        elif etype == "orbit_achieved":
            apo = data.get("apoapsis_m", 0) / 1_000
            peri = data.get("periapsis_m", 0) / 1_000
            entry = f"ORBIT: {apo:.0f} × {peri:.0f} km"
        elif etype == "maneuver_executed":
            apo = data.get("apoapsis_m", 0) / 1_000
            peri = data.get("periapsis_m", 0) / 1_000
            entry = f"Burn complete → {apo:.0f} × {peri:.0f} km"
        elif etype == "resource_warning":
            entry = f"LOW {data.get('resource','?').upper()}: {data.get('pct','?')}%"
        elif etype == "reentry_start":
            entry = f"Reentry begins at {alt_km:.0f} km"
        elif etype in ("touchdown", "splashdown"):
            spd = data.get("speed_ms", 0)
            entry = f"Landing at {spd:.1f} m/s"
        elif etype == "rendezvous_approach":
            dist = data.get("distance_m", 0) / 1_000
            entry = f"Rendezvous: {dist:.2f} km to target"
        elif etype == "eva_start":
            entry = f"EVA at {alt_km:.0f} km"
        elif etype == "agent_action":
            entry = f"AI Pilot: {data.get('action','?')} — {data.get('reason','')[:60]}"

        if entry:
            self._mission_timeline.append(entry)
            if len(self._mission_timeline) > self._bible_max:
                self._mission_timeline = self._mission_timeline[-self._bible_max:]

    # =========================================================================
    # Background commentary worker
    # =========================================================================

    def _commentary_worker(self) -> None:
        while not self._stop_evt.is_set():
            signalled = self._pending_evt.wait(timeout=1.0)
            if self._stop_evt.is_set():
                break
            if not signalled:
                if time.time() - self._last_call_ts >= self._heartbeat_gap_sec:
                    self._maybe_heartbeat()
                continue

            with self._pending_lock:
                snapshot = dict(self._pending)
                self._pending.clear()
                self._pending_evt.clear()

            if not snapshot:
                continue

            # Highest tier wins; ties go to most recent
            ordered = sorted(snapshot.values(),
                             key=lambda x: (x[0].value, x[3]), reverse=True)
            tier, etype, data, queued_at = ordered[0]

            try:
                self._generate_and_emit(tier, etype, data, queued_at)
            except Exception as exc:
                self._log("ksp_meta", f"commentary_worker error: {exc}")

    def _maybe_heartbeat(self) -> None:
        """Generate a quiet status call when commentary has been silent too long."""
        import sys as _sys
        _sdk = _sys.modules.get("ksp_sdk")
        if not _sdk:
            return
        state: Dict[str, Any] = dict(getattr(_sdk, "_live_state", {}) or {})
        if not state or not state.get("vessel"):
            return

        now  = time.time()
        mc   = self._mission_ctx
        data = {
            "vessel":       state.get("vessel", mc["vessel"]),
            "fuel_pct":     round(float(state.get("fuel_pct", 1.0)) * 100, 1),
            "mono_pct":     100.0,
            "electric_pct": 100.0,
            "altitude_m":   state.get("altitude_m", 0),
            "apoapsis_m":   state.get("apoapsis_m", 0),
            "periapsis_m":  state.get("periapsis_m", 0),
        }
        with self._pending_lock:
            self._pending["resource_update"] = (
                Tier.ROUTINE, "resource_update", data, now
            )
        self._pending_evt.set()

    def _generate_and_emit(self, tier: Tier, etype: str, data: Dict[str, Any],
                            queued_at: float = 0.0) -> None:
        # Staleness guard
        stale_threshold = 8.0
        if queued_at > 0 and (time.time() - queued_at) > stale_threshold:
            self._log("ksp_meta", f"[{etype}] dropped — stale by {time.time()-queued_at:.1f}s")
            return

        mc = self._mission_ctx

        # Mission bible text
        bible_text = ("\n".join(self._mission_timeline)
                      if self._mission_timeline else "No events yet.")

        # Shared prompt vars
        shared_vars = dict(
            vessel        = mc.get("vessel", "Unknown"),
            body          = mc.get("body", "Kerbin"),
            atm_depth_km  = mc.get("atm_depth_km", 70),
            phase         = mc.get("phase", "unknown"),
            apoapsis_km   = f"{mc.get('apoapsis_m', 0)/1_000:.1f}",
            periapsis_km  = f"{mc.get('periapsis_m', 0)/1_000:.1f}",
            fuel_pct      = f"{mc.get('fuel_pct', 100):.1f}",
            mission_bible = bible_text,
            lc_name       = self._lc_name,
            fd_name       = self._fd_name,
            station_name  = self._station_name,
        )

        system_lc = _SYSTEM_LC.format(**shared_vars)
        system_fd = _SYSTEM_FD.format(**shared_vars)
        user_prompt = _build_user_prompt(etype, data)

        host_model = self._cfg_get("models.host", "qwen3:8b")
        fast_model = self._cfg_get("models.fast", host_model)
        model      = host_model if tier.value >= Tier.NOTABLE.value else fast_model
        max_tokens = 120

        # Voice 1 — launch control (always)
        lc_text = self._llm(
            system=system_lc, user=user_prompt,
            model=model, max_tokens=max_tokens, temperature=0.85,
        )

        # Voice 2 — flight director (NOTABLE and above)
        fd_text = ""
        if tier.value >= Tier.NOTABLE.value:
            fd_text = self._llm(
                system=system_fd,
                user=(
                    f"{user_prompt}\n\n"
                    f"[{self._lc_name} just said: \"{lc_text}\"]\n"
                    "Do NOT repeat this. Add new mission-critical insight only."
                ),
                model=model, max_tokens=max_tokens, temperature=0.75,
            )

        self._emit_commentary(tier, etype, lc_text, fd_text)
        self._last_call_ts = time.time()
        self._log("ksp_meta",
                  f"[{etype}/{mc['phase']}] lc={len(lc_text)}ch fd={len(fd_text)}ch")

    def _emit_commentary(self, tier: Tier, etype: str,
                          lc_text: str, fd_text: str) -> None:
        script: List[Dict[str, Any]] = []
        if lc_text.strip():
            script.append({"type": "speech", "voice_id": self._lc_name,
                            "text": lc_text.strip(), "speaker": self._lc_name})
        if fd_text.strip():
            script.append({"type": "speech", "voice_id": self._fd_name,
                            "text": fd_text.strip(), "speaker": self._fd_name})

        if not script:
            return

        sha1_fn = self._ctx.get("sha1")
        unique_key = f"ksp-{etype}-{lc_text[:24]}-{int(time.time())}"
        seg_id  = sha1_fn(unique_key) if sha1_fn else str(int(time.time()))
        post_id = sha1_fn(f"ksp-{etype}-{round(time.time(), -1)}") if sha1_fn else seg_id

        seg = {
            "id":         seg_id,
            "post_id":    post_id,
            "source":     "ksp_meta",
            "event_type": etype,
            "title":      f"[KSP {etype}] live commentary",
            "body":       lc_text.strip(),
            "priority":   90 + tier.value * 2,
            "lead_voice": self._lc_name,
            "script":     script,
        }

        db_enqueue_fn = self._ctx.get("db_enqueue_segment")
        db_connect_fn = self._ctx.get("db_connect")
        if db_enqueue_fn and db_connect_fn:
            try:
                conn = db_connect_fn()
                db_enqueue_fn(conn, seg)
            except Exception as exc:
                self._log("ksp_meta", f"db_enqueue error: {exc}")
            return

        # Fallback
        try:
            StationEvent = self._ctx.get("StationEvent")
            event_q      = self._ctx.get("event_q")
            if StationEvent and event_q:
                ev = StationEvent(
                    source="ksp_meta", type="commentary",
                    ts=int(time.time()),
                    payload={"voice": self._lc_name, "text": lc_text.strip()},
                    priority=seg["priority"],
                )
                event_q.put_nowait(ev)
        except Exception as exc:
            self._log("ksp_meta", f"emit_commentary fallback error: {exc}")

    # =========================================================================
    # Non-live talk segment
    # =========================================================================

    def _generate_talk_segment(self, segment: Dict[str, Any]) -> Dict[str, Any]:
        title = segment.get("title", "")
        body  = segment.get("body", segment.get("angle", ""))
        model = self._cfg_get("models.host", "qwen3:8b")
        mc    = self._mission_ctx

        system = (
            f"/no_think\n"
            f"You are {self._lc_name}, host of {self._station_name} — "
            f"a Kerbal Space Program mission radio station with live AI commentary. "
            f"Tone: knowledgeable, enthusiastic, like a real space agency broadcaster. "
            f"Speak naturally for audio. No bullet points. No preamble."
        )
        user = (
            f"Topic: {title}\n"
            f"Material: {body}\n\n"
            f"Current mission context: vessel '{mc['vessel']}', phase '{mc['phase']}', "
            f"altitude {mc['altitude_m']/1000:.1f} km.\n\n"
            f"Write a 2-3 sentence spoken intro. Reply with only the spoken words."
        )

        intro   = self._llm(system=system, user=user, model=model,
                             max_tokens=120, temperature=0.7)
        user2   = (f"Topic: {title}\n"
                   f"Material: {body[:400]}\n\n"
                   f"Write a 1-2 sentence summary. Reply with only the spoken words.")
        summary = self._llm(system=system, user=user2, model=model,
                             max_tokens=100, temperature=0.6)
        return {
            "host_intro":    intro,
            "summary":       summary,
            "panel":         [],
            "host_takeaway": "",
        }

    # =========================================================================
    # Helpers
    # =========================================================================

    def _llm(self, system: str, user: str, model: str,
             max_tokens: int = 120, temperature: float = 0.75) -> str:
        try:
            fn = self._ctx.get("llm_generate")
            if callable(fn):
                raw = fn(user, system, model, max_tokens, temperature, 60) or ""
                raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
                return raw
        except Exception as exc:
            self._log("ksp_meta", f"LLM error: {exc}")
        return ""

    def _cfg_get(self, key: str, default: Any = None) -> Any:
        try:
            fn = self._ctx.get("cfg_get")
            if callable(fn):
                return fn(key, default)
        except Exception:
            pass
        parts = key.split(".")
        obj   = self._cfg
        for p in parts:
            if isinstance(obj, dict):
                obj = obj.get(p)
            else:
                return default
        return obj if obj is not None else default
