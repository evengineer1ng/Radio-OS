"""
iRacing Meta Plugin
===================
Transforms raw iRacing SDK events into live, two-voice broadcast commentary
using the LLM pipeline wired into Radio OS.

Architecture
------------
  IRacingEventQueue  ← events pushed by iracing_sdk.py feed worker
        │
  EventClassifier    ← tier the event (CRITICAL / NOTABLE / ROUTINE / AMBIENT)
        │
  CommentaryDirector ← decides whether to script a call, a quick burst, or skip
        │
  LLM pipeline       ← uses runtime["llm_generate"] to write commentary
        │
  emit into event_q  ← bookmark.py picks it up for TTS / audio

Two voices
----------
  play_by_play (pbp)  — immediate, exclamatory lap calls
  color               — analytical, context-heavy reactions

Both voices are configured in the station manifest under characters / tts / voices.
"""

from __future__ import annotations

import json
import random
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
    CRITICAL = 4   # lead change, race start/finish, caution, fastest lap, player event
    NOTABLE  = 3   # any pass, pit stop, incident
    ROUTINE  = 2   # lap completion, standings update
    AMBIENT  = 1   # flags, warmup, cooldown


_TIER_MAP: Dict[str, Tier] = {
    # Critical
    "session_state_change": Tier.CRITICAL,
    "flag_change":          Tier.CRITICAL,
    "fastest_lap":          Tier.CRITICAL,
    "race_finish":          Tier.CRITICAL,
    "fuel_warning":         Tier.CRITICAL,
    # Notable
    "position_change":      Tier.NOTABLE,
    "incident":             Tier.NOTABLE,
    "pit_entry":            Tier.NOTABLE,
    "pit_exit":             Tier.NOTABLE,
    "weather_change":       Tier.NOTABLE,
    "lap_delta":            Tier.NOTABLE,
    "laps_to_go":           Tier.NOTABLE,
    "battle_building":      Tier.NOTABLE,
    # Routine
    "lap_complete":         Tier.ROUTINE,
    "standings_update":     Tier.ROUTINE,
    "battle_ongoing":       Tier.ROUTINE,
    # Ambient
    "radio_chatter":        Tier.AMBIENT,
    "lead_update":          Tier.AMBIENT,
}

def _classify(event_type: str, data: Dict[str, Any]) -> Tier:
    t = _TIER_MAP.get(event_type, Tier.AMBIENT)
    # Anything involving the player car bumps up one tier
    if data.get("is_player") or data.get("is_lead_change"):
        if t.value < Tier.CRITICAL.value:
            t = Tier(t.value + 1)
    return t


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

_SYSTEM_PBP = """/no_think
You are {pbp_name}, the play-by-play commentator for {station_name}.
You call every moment like it MATTERS — exclamatory, immediate, vivid.
Keep each call to 1-2 punchy sentences. No bullet points. Spoken words only.
Never say '#', 'hash', or 'pound' — always say 'car number X'.
Never repeat the same fact twice within your response — say each thing exactly once.
Lap times are M:SS.mmm — say them naturally (e.g. "one twenty-three four five six").
NEVER invent tire compound names (soft/medium/hard) — that data is not available.
You MAY say a car is on X-lap-old tyres if stint data is given.
Track: {track} ({track_type}). Series: {series}. Session: {session_type}. Lap {lap} of {total_laps} ({laps_remain} to go).
Conditions: {weather_ctx}.
{battles_ctx}{standings_ctx}{bible_ctx}"""

_SYSTEM_COLOR = """/no_think
You are {color_name}, the color commentator for {station_name}.
CRITICAL: {pbp_name} will call the action. You MUST add only NEW information — do NOT repeat or
rephrase what they say. Your value is: strategy implications, tyre age considerations, a prediction, or
what this means for the rest of the session. If nothing analytical to add, say something forward-looking.
1-2 measured sentences. No bullet points. No intro phrases. Spoken words only.
Never repeat the same fact twice within your response — say each thing exactly once.
Never say '#', 'hash', or 'pound' — always say 'car number X'.
Lap times are M:SS.mmm. NEVER invent tire compound names — reference tyre age in laps if available.
Track: {track} ({track_type}). Series: {series}. Session: {session_type}. Lap {lap} of {total_laps}.
Conditions: {weather_ctx}.
{battles_ctx}{standings_ctx}{bible_ctx}"""

_SYSTEM_ANALYST = """/no_think
You are {analyst_name}, the technical analyst for {station_name}.
CRITICAL: {pbp_name} and {color_name} already covered the action and context. Do NOT repeat any of it.
One sharp observation only: lap-time gap vs rival, tyre age concern, sector speed, or a number not yet said.
Lap times are M:SS.mmm. NEVER invent tire compound names; you may reference stint length in laps if given.
1 sentence maximum. No preamble. Direct technical insight spoken naturally.
Never repeat the same fact twice within your response — say each thing exactly once.
Never say '#', 'hash', or 'pound' — always say 'car number X'.
Track: {track} ({track_type}). Series: {series}. Session: {session_type}.
{standings_ctx}"""

# Event-type → user prompt template (Race session)
_EVENT_PROMPTS: Dict[str, str] = {

    "session_state_change": (
        "SESSION: race state just changed from '{from}' to '{to}'.\n"
        "Track: {track} | Series: {series} | Total laps: {total_laps}\n"
        "Air: {air_temp}°C | Track: {track_temp}°C\n"
        "Write your opening call. Capture the energy of the moment."
    ),

    "flag_change": (
        "FLAG: {flag} flag is out on lap {lap}.\n"
        "Write a sharp call reacting to this flag situation."
    ),

    "lap_complete": (
        "LAP: {driver} (car {car_num}) completes lap {lap} "
        "in P{position} with a time of {lap_time} "
        "(best: {best_time}{gap_str}).\n"
        "Call this lap in the context of their race."
    ),

    "position_change": (
        "PASS: {driver} (car {car_num}) just moved from P{from_pos} to P{to_pos} on lap {lap}!\n"
        "{lead_flag}"
        "Make this call feel electric."
    ),

    "incident": (
        "INCIDENT: {driver} (car {car_num}) picked up {delta} incident point(s) "
        "(total: {total}) on lap {lap} in P{position}.\n"
        "React to this incident — was it avoidable? What does it mean for their race?"
    ),

    "pit_entry": (
        "PIT IN: {driver} (car {car_num}) dives into the pits from P{position} on lap {lap}.\n"
        "Call the pit stop — timing, strategy, implications."
    ),

    "pit_exit": (
        "PIT OUT: {driver} (car {car_num}) rejoins the race from pit lane on lap {lap}.\n"
        "React — where do they re-enter? What's the strategy here?"
    ),

    "fastest_lap": (
        "FASTEST LAP: {driver} (car {car_num}) just set the fastest lap of the race: {lap_time} "
        "on lap {lap}!\n"
        "Make this moment feel significant."
    ),

    "standings_update": (
        "STANDINGS (lap {lap}/{total_laps}, {flag} flag):\n"
        "{standings_text}\n"
        "Give a concise state-of-race summary. One crisp PBP sentence, one color insight."
    ),

    "race_finish": (
        "RACE OVER! {winner} (car {winner_num}) wins the {series} at {track} after {laps_run} laps!\n"
        "{fastest_lap_line}"
        "Top 5: {top_five_text}\n"
        "{player_win_flag}"
        "Give the victory call. Make it memorable."
    ),

    # ---- Live battle events ----
    "battle_building": (
        "BATTLE BUILDING: {chaser} (car {chaser_num}, P{chaser_pos}) is rapidly closing on "
        "{leader} (car {leader_num}, P{leader_pos})! Current gap: {gap}s, closed {gap_trend}s in recent laps.\n"
        "Call the pursuit and mounting pressure. What does {chaser} need to do to get by?"
    ),

    "battle_ongoing": (
        "WHEEL-TO-WHEEL: {chaser} (car {chaser_num}, P{chaser_pos}) has shadowed "
        "{leader} (car {leader_num}, P{leader_pos}) for {duration} seconds \u2014 gap just {gap}s!\n"
        "How is {leader} defending? What move is {chaser} setting up?"
    ),

    "lead_update": (
        "CURRENT LEADER: {driver} (car {car_num}) leads lap {lap}. "
        "P2 is {gap_to_p2:.2f}s behind.\n"
        "Give a crisp current state-of-race call."
    ),
}

# Event-type → user prompt template (Qualify session) — pace-focused
_EVENT_PROMPTS_QUALI: Dict[str, str] = {

    "session_state_change": (
        "QUALIFYING SESSION: state changed from '{from}' to '{to}'.\n"
        "Track: {track} | Series: {series}\n"
        "This is qualifying — drivers are fighting for grid position. Capture the tension."
    ),

    "flag_change": (
        "FLAG: {flag} flag in qualifying on lap {lap}.\n"
        "What does this mean for drivers still out on track? Call it."
    ),

    "lap_complete": (
        "QUALI LAP: {driver} (car {car_num}) posts {lap_time}, sitting P{position}{gap_str}.\n"
        "Best in session: {best_time}.\n"
        "Is this lap good enough? What do they need to improve?"
    ),

    "position_change": (
        "GRID MOVE: {driver} (car {car_num}) jumps from P{from_pos} to P{to_pos} on their latest flyer!\n"
        "{lead_flag}"
        "React to this grid position change — what does it mean for the race start?"
    ),

    "incident": (
        "INCIDENT in qualifying: {driver} (car {car_num}) collects {delta} incident point(s) on lap {lap}.\n"
        "Could this ruin their qualifying lap? What's the impact?"
    ),

    "pit_entry": (
        "QUALI PIT: {driver} (car {car_num}) comes in from P{position} on lap {lap}.\n"
        "Tyre change? Final prep? Call the qualifying strategy."
    ),

    "pit_exit": (
        "OUT LAP: {driver} (car {car_num}) heads back out from the pits on lap {lap}.\n"
        "They need a hot lap — call the anticipation."
    ),

    "fastest_lap": (
        "POLE SHOT! {driver} (car {car_num}) goes to the top of the timesheet: {lap_time} on lap {lap}!\n"
        "That is the benchmark. Can anyone beat it?"
    ),

    "standings_update": (
        "QUALI STANDINGS after lap {lap}:\n"
        "{standings_text}\n"
        "Summarise the qualifying order. Who is on pole, who needs to find more pace, who is under threat?"
    ),

    "race_finish": (
        "QUALIFYING COMPLETE! {winner} (car {winner_num}) takes POLE for the {series} at {track}!\n"
        "Grid: {top_five_text}\n"
        "Give the pole celebration call. What does the grid look like heading to the race?"
    ),

    "battle_building": (
        "QUALI BATTLE: {chaser} (car {chaser_num}, P{chaser_pos}) is closing on "
        "{leader} (car {leader_num}, P{leader_pos}) \u2014 gap {gap}s, trend {gap_trend}s.\n"
        "What does this mean for grid positions?"
    ),

    "battle_ongoing": (
        "QUALI FIGHT: {chaser} (car {chaser_num}) has been within {gap}s of "
        "{leader} (car {leader_num}) for {duration} seconds.\n"
        "Will this change the grid order?"
    ),

    "lead_update": (
        "QUALI LEADER: {driver} (car {car_num}) sits P1 on lap {lap}. "
        "P2 just {gap_to_p2:.2f}s back.\n"
        "Who looks set for pole? Who needs another lap?"
    ),
}

# Event-type → user prompt template (Practice session) — analytical
_EVENT_PROMPTS_PRACTICE: Dict[str, str] = {

    "session_state_change": (
        "PRACTICE SESSION: state changed from '{from}' to '{to}'.\n"
        "Track: {track} | Series: {series}\n"
        "This is FREE PRACTICE — no race is starting. Drivers are finding rhythm and setup.\n"
        "Set the analytical scene. Do NOT use race-start language."
    ),

    "flag_change": (
        "PRACTICE FLAG: {flag} flag out on lap {lap}.\n"
        "React in a practice context — what does this mean for drivers on hot laps or long runs?"
    ),

    "fastest_lap": (
        "PRACTICE BENCHMARK: {driver} (car {car_num}) posts {lap_time} on lap {lap}.\n"
        "Is this representative? Long run or hot lap pace?"
    ),

    "lap_complete": (
        "PRACTICE LAP: {driver} (car {car_num}) does {lap_time} in P{position}.\n"
        "Best so far: {best_time}. What are they working on?"
    ),

    "position_change": (
        "PRACTICE ORDER: {driver} (car {car_num}) moves from P{from_pos} to P{to_pos} on lap {lap}.\n"
        "React briefly — setup improvement or tyre prep?"
    ),

    "incident": (
        "PRACTICE INCIDENT: {driver} (car {car_num}) collects {delta} incident point(s) on lap {lap}.\n"
        "Brief reaction — what happened and is there any concern for the car?"
    ),

    "pit_entry": (
        "PRACTICE PIT: {driver} (car {car_num}) comes in from P{position} on lap {lap}.\n"
        "Setup change, tyre data, or fuel check? React briefly."
    ),

    "pit_exit": (
        "PRACTICE OUT LAP: {driver} (car {car_num}) heads back out on lap {lap}.\n"
        "What are they looking to achieve on this run?"
    ),

    "weather_change": (
        "PRACTICE CONDITIONS CHANGE: {wetness_desc} surface now.\n"
        "How does this affect setup work and the rest of the session?"
    ),

    "standings_update": (
        "PRACTICE TIMES after lap {lap}:\n"
        "{standings_text}\n"
        "Read the practice leaderboard. Who looks quick? Any surprises?"
    ),

    "battle_building": (
        "PRACTICE BATTLE: {chaser} (car {chaser_num}) closing on "
        "{leader} (car {leader_num}) \u2014 gap {gap}s, closing {gap_trend}s.\n"
        "What does this tell us about relative car pace?"
    ),

    "battle_ongoing": (
        "PRACTICE FIGHT: {chaser} (car {chaser_num}) within {gap}s of "
        "{leader} (car {leader_num}) for {duration} seconds.\n"
        "Track position battle or genuine pace comparison?"
    ),

    "lead_update": (
        "PRACTICE LEADER: {driver} (car {car_num}) leads the timing sheet. "
        "Gap to P2: {gap_to_p2:.2f}s.\n"
        "Brief session snapshot \u2014 what is the pace story so far?"
    ),
}


def _build_user_prompt(event_type: str, data: Dict[str, Any],
                       session_type: str = "Race") -> str:
    # Select prompt table based on session type
    _stype = (session_type or "Race").strip().lower()
    if _stype in ("qualify", "qualifying"):
        table = _EVENT_PROMPTS_QUALI
    elif _stype == "practice":
        table = _EVENT_PROMPTS_PRACTICE
    else:
        table = _EVENT_PROMPTS
    # Fall back to race prompts for event types not in practice/quali tables
    template = table.get(event_type) or _EVENT_PROMPTS.get(event_type)
    if not template:
        return f"Event: {event_type}\nData: {json.dumps(data)}\nReact to this."
    try:
        # Pre-format lap times as M:SS.mmm so the LLM pronounces them correctly
        data = dict(data)
        for _ltf in ("lap_time", "best_time"):
            if _ltf in data and isinstance(data[_ltf], (int, float)) and data[_ltf] > 0:
                data[_ltf] = _fmt_laptime(float(data[_ltf]))
        # Pre-format derived fields
        extra = {}
        if event_type == "position_change":
            extra["lead_flag"] = "THIS IS A LEAD CHANGE! " if data.get("is_lead_change") else ""
        if event_type == "lap_complete":
            extra["player_note"] = "THIS IS YOUR OWN LAP. Make it personal! " if data.get("is_player") else ""
            _gtl = float(data.get("gap_to_leader", 0.0))
            if _gtl <= 0.0:
                extra["gap_str"] = (", ON POLE" if _stype in ("qualify", "qualifying") else ", LEADING")
            else:
                extra["gap_str"] = (f", {_gtl:.2f}s off pole" if _stype in ("qualify", "qualifying")
                                    else f", gap to leader: {_gtl:.2f}s")
        if event_type == "session_state_change":
            nc = int(data.get("num_classes", 1))
            extra["multiclass_note"] = f"{nc} car classes are competing tonight.\n" if nc > 1 else ""
        if event_type == "standings_update":
            top = data.get("top_five", [])
            extra["standings_text"] = "\n".join(
                f"  P{d['pos']}: {d['driver']} (#{d['car_num']}) — lap {d['lap']}"
                + (f" +{d['gap']:.2f}s" if d.get("gap", 0) > 0 else " LEADER")
                + (" [YOU]" if d.get("is_player") else "")
                for d in top
            )
            wn = int(data.get("track_wetness", 0))
            _WET = [""," (slightly damp)"," (damp tracksurf)"," (WET tracksurf)"," (VERY WET)"," (FLOODED)"]
            extra["wetness_note"] = _WET[min(wn, 5)]
        if event_type == "race_finish":
            top = data.get("top_five", [])
            extra["top_five_text"] = ", ".join(f"P{d['pos']} {d['driver']}" for d in top)
            player_won = any(d.get("is_player") and d.get("pos") == 1 for d in top)
            extra["player_win_flag"] = "THE PLAYER WON THIS RACE! Make it intensely personal! " if player_won else ""
            flt = data.get("fastest_lap_time", -1.0)
            fld = data.get("fastest_lap_driver", "")
            extra["fastest_lap_line"] = f"Fastest lap: {fld} — {_fmt_laptime(flt)}\n" if (flt and flt > 0 and fld) else ""
        if event_type == "laps_to_go":
            laps = int(data.get("laps_remain", 0))
            extra["plural"] = "" if laps == 1 else "S"
            gap_p2 = float(data.get("gap_p2", 0.0))
            extra["battle_context"] = (
                f"The gap from P1 to P2 is just {gap_p2:.2f}s — there\'s a battle brewing! "
                if 0 < gap_p2 < 1.5 else ""
            )
        if event_type == "lap_delta":
            extra["session_context"] = (
                f"Current running lap time: {_fmt_laptime(data.get('current_lap_time', 0))}. "
                if data.get("current_lap_time", 0) > 0 else ""
            )
        if event_type == "pit_entry" or event_type == "pit_exit":
            stint = int(data.get("tire_stint_laps", 0))
            extra["stint_note"] = (
                f"Tyres are {stint} laps old. " if stint > 0 else ""
            )
        if event_type in ("battle_building", "battle_ongoing", "lead_update"):
            pass  # all fields come directly from data
        merged = {**data, **extra}
        return template.format_map({k: merged.get(k, "?") for k in _extract_keys(template)})
    except Exception:
        return f"Event: {event_type}\nData: {json.dumps(data, default=str)}"


def _extract_keys(s: str) -> List[str]:
    import string
    formatter = string.Formatter()
    return [fname for _, fname, _, _ in formatter.parse(s) if fname]


def _fmt_laptime(secs: float) -> str:
    """Convert float seconds to broadcast M:SS.mmm (e.g. '1:23.456')."""
    if not secs or secs <= 0:
        return "—"
    m = int(secs // 60)
    s = secs - m * 60
    return f"{m}:{s:06.3f}"


# ---------------------------------------------------------------------------
# Main meta plugin
# ---------------------------------------------------------------------------

class iRacingMetaPlugin(MetaPluginBase):
    """
    Live iRacing broadcast commentary meta plugin.

    Consumes StationEvents from iracing_sdk and produces spoken two-voice
    commentary segments via the LLM pipeline.
    """

    def __init__(self):
        self._ctx:  Dict[str, Any] = {}
        self._cfg:  Dict[str, Any] = {}
        self._mem:  Dict[str, Any] = {}
        self._log   = print

        # Commentary pacing
        self._last_call_ts:    float = 0.0
        self._min_gap_sec:     float = 4.0    # minimum seconds between any two calls
        self._routine_gap_sec: float = 12.0   # min gap between routine calls
        self._last_routine_ts: float = 0.0
        self._heartbeat_gap_sec: float = 15.0  # quiet seconds before lead-lap heartbeat

        # Cooldowns per event type (seconds)
        self._cooldowns: Dict[str, float] = {
            "lap_complete":      8.0,
            "standings_update": 25.0,
            "pit_entry":         6.0,
            "pit_exit":          6.0,
            "flag_change":       5.0,
            "fuel_warning":     30.0,
            "weather_change":   20.0,
            "lap_delta":        20.0,
            "laps_to_go":        8.0,
            "radio_chatter":    15.0,
            "battle_building":  18.0,
            "battle_ongoing":   25.0,
            "lead_update":      30.0,
        }
        self._last_event_ts:   Dict[str, float] = {}

        # Race context memory (persists across calls)
        self._race_ctx: Dict[str, Any] = {
            "track":         "Unknown",
            "series":        "iRacing",
            "total_laps":    0,
            "current_lap":   0,
            "flag":          "green",
            "session_state": "Unknown",
            "fastest_lap":   None,
            "fastest_name":  None,
            "track_type":    "road",
            "event_type":    "Race",
            "laps_remain":   0,
            "time_remain":   0.0,
            "num_classes":   1,
            "weather": {
                "air_temp":      22.0,
                "track_temp":    30.0,
                "track_wetness": 0,
                "wind_vel":      0.0,
                "skies":         0,
            },
        }

        # Latest-event store: dict of etype -> (tier, etype, data, ts)
        # Only the most recent event per type is ever queued for LLM.
        # A threading.Event signals the worker that something is ready.
        self._pending: Dict[str, tuple] = {}        # etype -> (tier, etype, data, ts)
        self._pending_lock = threading.Lock()
        self._pending_evt  = threading.Event()
        self._stop_evt = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        # Race Bible — rolling timeline of meaningful events
        self._race_timeline: List[str] = []
        self._bible_max: int = 10
        self._current_standings_text: str = ""

        # Voice names (set fully in initialize())
        self._pbp_name:     str = "Alex"
        self._color_name:   str = "Jordan"
        self._analyst_name: str = ""   # empty = analyst disabled until initialize() runs

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def initialize(self, runtime_context: Dict[str, Any],
                   cfg: Dict[str, Any], mem: Dict[str, Any]) -> None:
        self._ctx = runtime_context
        self._cfg = cfg
        self._mem = mem
        self._log = runtime_context.get("log", print)

        # Pacing overrides from manifest
        pacing = cfg.get("pacing", {}) or {}
        self._min_gap_sec     = float(pacing.get("min_commentary_gap_sec",   self._min_gap_sec))
        self._routine_gap_sec = float(pacing.get("routine_commentary_gap_sec", self._routine_gap_sec))

        # Voice names for prompts
        voices = (cfg.get("characters") or {})
        self._pbp_name     = str((voices.get("pbp")     or {}).get("name", "Alex"))
        self._color_name   = str((voices.get("color")   or {}).get("name", "Jordan"))
        self._analyst_name = str((voices.get("analyst") or {}).get("name", ""))

        self._station_name = str((cfg.get("station") or {}).get("name", "iRacingFM"))

        self._log("iracing_meta", f"iRacingMetaPlugin initialized — voices: "
                  f"pbp={self._pbp_name}, color={self._color_name}, analyst={self._analyst_name or 'disabled'}")

        # Start background commentary worker
        self._stop_evt.clear()
        self._worker_thread = threading.Thread(
            target=self._commentary_worker,
            name="iracing_meta_worker",
            daemon=True,
        )
        self._worker_thread.start()

    def shutdown(self) -> None:
        self._stop_evt.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=3.0)
        self._log("iracing_meta", "iRacingMetaPlugin shut down.")

    # =========================================================================
    # Legacy interface — called by bookmark.py event loop
    # =========================================================================

    def curate_candidates(self, candidates: List[Dict[str, Any]],
                          state: Any) -> List[Dict[str, Any]]:
        """Only allow live iRacing telemetry events through — block all other sources."""
        return [c for c in candidates if c.get("source") == "iracing_sdk"]

    def generate_script(self, segment: Dict[str, Any],
                        state: Any) -> Dict[str, Any]:
        """Generate a standard talk segment (non-live mode fallback).

        If the segment already carries pre-built multi-voice script atoms
        (from _emit_commentary), skip the LLM entirely so render_segment_audio
        uses those atoms unchanged.
        """
        if segment.get("script") and isinstance(segment.get("script"), list):
            # Pre-built atoms present — pass through without extra LLM work
            return {}
        return self._generate_talk_segment(segment)

    def generate_narration(self, events: List[Any], context: Any) -> str:
        """Called by bookmark for live narration — route iRacing events."""
        for ev in (events or []):
            if hasattr(ev, "source") and ev.source == "iracing_sdk":
                self._handle_iracing_event(ev)
        return ""   # commentary is emitted directly onto the queue

    def delegate_decision(self, available_actions, state, identity, focus) -> None:
        return None

    # =========================================================================
    # Primary event handler
    # =========================================================================

    def handle_event(self, event: Any) -> None:
        """
        Called externally (e.g. from bookmark event dispatcher) with any
        StationEvent.  Routes iRacing events to the commentary queue.
        """
        if getattr(event, "source", "") == "iracing_sdk":
            self._handle_iracing_event(event)

    def _handle_iracing_event(self, event: Any) -> None:
        etype = getattr(event, "type", "") or getattr(event, "event_type", "")
        data  = getattr(event, "payload", {}) or getattr(event, "data", {}) or {}

        # Update race context cache
        self._update_race_ctx(etype, data)

        # Classify tier
        tier = _classify(etype, data)

        # Check cooldowns
        now = time.time()
        cooldown = self._cooldowns.get(etype, 0.0)
        last_ts  = self._last_event_ts.get(etype, 0.0)
        if cooldown > 0 and (now - last_ts) < cooldown:
            return  # too soon for this type

        # Global pacing
        since_last = now - self._last_call_ts
        if tier.value <= Tier.ROUTINE.value and since_last < self._routine_gap_sec:
            return
        if since_last < self._min_gap_sec:
            return

        self._last_event_ts[etype] = now

        # Always overwrite the pending slot for this event type with the
        # freshest copy.  The worker only ever sees the latest version.
        with self._pending_lock:
            self._pending[etype] = (tier, etype, data, now)
        self._pending_evt.set()

    def _update_race_ctx(self, etype: str, data: Dict[str, Any]) -> None:
        rc = self._race_ctx
        if etype == "session_state_change":
            rc["track"]         = data.get("track", rc["track"])
            rc["series"]        = data.get("series", rc["series"])
            rc["total_laps"]    = data.get("total_laps", rc["total_laps"])
            rc["session_state"] = data.get("to", rc["session_state"])
            rc["track_type"]    = data.get("track_type", rc.get("track_type", "road"))
            rc["event_type"]    = data.get("event_type", rc.get("event_type", "Race"))
            rc["num_classes"]   = data.get("num_classes", rc.get("num_classes", 1))
        elif etype == "flag_change":
            rc["flag"]        = data.get("flag", rc["flag"])
            rc["current_lap"] = data.get("lap", rc["current_lap"])
        elif etype == "fastest_lap":
            rc["fastest_lap"]  = data.get("lap_time")
            rc["fastest_name"] = data.get("driver")
        elif etype in ("lap_complete", "standings_update"):
            rc["current_lap"] = data.get("lap", rc["current_lap"])
            if etype == "standings_update":
                rc.get("weather", {}).update({
                    "track_temp": data.get("track_temp", rc.get("weather", {}).get("track_temp", 30.0)),
                    "track_wetness": data.get("track_wetness", 0),
                    "wind_vel":  data.get("wind_vel", 0.0),
                })
        elif etype == "weather_change":
            wx = rc.setdefault("weather", {})
            wx["track_wetness"] = data.get("wetness_level", 0)
            wx["air_temp"]      = data.get("air_temp",   wx.get("air_temp",   22.0))
            wx["track_temp"]    = data.get("track_temp", wx.get("track_temp", 30.0))
            wx["wind_vel"]      = data.get("wind_vel",   wx.get("wind_vel",   0.0))
        # Propagate laps_remain / time_remain from any event that carries them
        if "laps_remain" in data:
            rc["laps_remain"] = data["laps_remain"]
        if "time_remain" in data:
            rc["time_remain"] = data["time_remain"]

        # Update standings text cache
        if etype == "standings_update":
            top = data.get("top_five", [])
            if top:
                lines = []
                for d in top:
                    gap_str = f" +{d['gap']:.2f}s" if d.get("gap", 0) > 0 else " LEADER"
                    you = " [YOU]" if d.get("is_player") else ""
                    lines.append(f"  P{d['pos']}: {d['driver']} (car {d['car_num']}) L{d['lap']}{gap_str}{you}")
                self._current_standings_text = "\n".join(lines)

        # Add to race bible
        self._add_bible_entry(etype, data)

    def _add_bible_entry(self, etype: str, data: Dict[str, Any]) -> None:
        """Append a one-liner to the rolling race timeline."""
        entry: Optional[str] = None
        lap = data.get("lap", self._race_ctx.get("current_lap", 0))

        if etype == "session_state_change":
            to_state = data.get("to", "")
            if to_state == "Racing":
                # Fresh race start — reset the bible
                self._race_timeline = []
            entry = f"Session: {data.get('from','?')} → {to_state} ({data.get('track', self._race_ctx.get('track', '?'))})"

        elif etype == "flag_change":
            entry = f"L{lap}: {data.get('flag','?')} flag"

        elif etype == "position_change":
            if data.get("is_lead_change"):
                entry = f"L{lap}: LEAD CHANGE — {data.get('driver','?')} takes P1"
            else:
                entry = f"L{lap}: {data.get('driver','?')} → P{data.get('to_pos','?')}"

        elif etype == "incident":
            entry = f"L{lap}: {data.get('driver','?')} +{data.get('delta',0)}x incident (P{data.get('position','?')})"

        elif etype == "pit_entry":
            entry = f"L{lap}: {data.get('driver','?')} pits (P{data.get('position','?')})"

        elif etype == "pit_exit":
            entry = f"L{lap}: {data.get('driver','?')} leaves pits"

        elif etype == "fastest_lap":
            lt = data.get("lap_time", 0.0)
            entry = f"L{lap}: FASTEST — {data.get('driver','?')} {lt:.3f}s"

        elif etype == "weather_change":
            entry = f"L{lap}: Weather — {data.get('wetness_desc', 'changed')}"

        elif etype == "battle_building":
            entry = (f"L{lap}: BATTLE BUILDING — {data.get('chaser','?')} closing on "
                     f"{data.get('leader','?')} (P{data.get('leader_pos','?')}), gap {data.get('gap',0):.2f}s")

        elif etype == "battle_ongoing":
            entry = (f"L{lap}: WHEEL-TO-WHEEL — {data.get('chaser','?')} vs "
                     f"{data.get('leader','?')}, gap {data.get('gap',0):.2f}s")

        elif etype == "race_finish":
            entry = f"FINISH: {data.get('winner','?')} wins after {data.get('laps_run','?')} laps"

        elif etype == "laps_to_go":
            laps_r = data.get("laps_remain", 0)
            entry = f"L{lap}: {laps_r} lap{'s' if laps_r != 1 else ''} to go — leader {data.get('leader','?')}"

        if entry:
            self._race_timeline.append(entry)
            if len(self._race_timeline) > self._bible_max:
                self._race_timeline = self._race_timeline[-self._bible_max:]

    # =========================================================================
    # Background commentary worker
    # =========================================================================

    def _commentary_worker(self) -> None:
        """
        Waits for a signal that new events arrived, then atomically grabs
        all pending events, picks the highest-tier freshest one, and
        generates commentary.  Because we always overwrite pending slots,
        only the most recent event per type is ever processed — no backlog.
        """
        while not self._stop_evt.is_set():
            # Sleep until something is available (1 s timeout for heartbeat check)
            signalled = self._pending_evt.wait(timeout=1.0)
            if self._stop_evt.is_set():
                break
            if not signalled:
                # Timed out — heartbeat if we've been quiet long enough
                if time.time() - self._last_call_ts >= self._heartbeat_gap_sec:
                    self._maybe_heartbeat()
                continue

            # Atomically grab and clear all pending events
            with self._pending_lock:
                snapshot = dict(self._pending)
                self._pending.clear()
                self._pending_evt.clear()

            if not snapshot:
                continue

            # Pick the highest-tier, and among ties the most recent
            ordered = sorted(snapshot.values(),
                             key=lambda x: (x[0].value, x[3]), reverse=True)
            tier, etype, data, queued_at = ordered[0]

            try:
                self._generate_and_emit(tier, etype, data, queued_at)
            except Exception as exc:
                self._log("iracing_meta", f"commentary_worker error: {exc}")

    def _maybe_heartbeat(self) -> None:
        """
        Called when commentary has been quiet for _heartbeat_gap_sec.
        Synthesises a live-state event about the lead battle or current leader
        so the broadcast never goes silent for too long.
        Only queues something if fresh live state is available.
        """
        import sys as _sys
        _sdk = _sys.modules.get("iracing_sdk")
        if not _sdk:
            return
        state: Dict[str, Any] = dict(getattr(_sdk, "_live_state", {}) or {})
        drivers = state.get("drivers", [])
        if not drivers:
            return
        on_track = sorted(
            [d for d in drivers
             if d.get("track_surface", 3) in (2, 3)
             and str(d.get("car_num", "")) != "0"
             and "pace" not in str(d.get("name", "")).lower()],
            key=lambda d: d.get("position", 999)
        )
        if not on_track:
            return
        now = time.time()
        # Close battle at front? — use it
        if len(on_track) >= 2:
            a, b = on_track[0], on_track[1]
            gap = max(0.0, float(b.get("gap", 99)) - float(a.get("gap", 0)))
            if 0 < gap < 2.5:
                with self._pending_lock:
                    self._pending["battle_ongoing"] = (
                        Tier.NOTABLE, "battle_ongoing",
                        {
                            "chaser":     b.get("name", "?"),
                            "chaser_num": b.get("car_num", "?"),
                            "chaser_pos": b.get("position", 2),
                            "leader":     a.get("name", "?"),
                            "leader_num": a.get("car_num", "?"),
                            "leader_pos": a.get("position", 1),
                            "gap":        round(gap, 3),
                            "duration":   max(0, int(now - self._last_call_ts)),
                            "lap":        a.get("lap", 0),
                        },
                        now,
                    )
                self._pending_evt.set()
                return
        # Fall back to a plain leader update
        leader = on_track[0]
        p2_gap = max(0.0, float(on_track[1].get("gap", 0)) - float(leader.get("gap", 0))) \
            if len(on_track) > 1 else 0.0
        with self._pending_lock:
            self._pending["lead_update"] = (
                Tier.ROUTINE, "lead_update",
                {
                    "driver":    leader.get("name", "?"),
                    "car_num":   leader.get("car_num", "?"),
                    "position":  1,
                    "lap":       leader.get("lap", 0),
                    "gap_to_p2": round(p2_gap, 2),
                },
                now,
            )
        self._pending_evt.set()

    def _generate_and_emit(self, tier: Tier, etype: str, data: Dict[str, Any],
                            queued_at: float = 0.0) -> None:
        # Staleness guard — must still be recent when LLM starts generating
        stale_threshold = 4.0   # seconds
        if queued_at > 0 and (time.time() - queued_at) > stale_threshold:
            self._log("iracing_meta",
                      f"[{etype}] dropped — stale by {time.time()-queued_at:.1f}s")
            return

        rc = self._race_ctx

        # Always read session type fresh from the live state (more reliable than
        # waiting for a session_state_change event to arrive first)
        import sys as _sys
        _sdk = _sys.modules.get("iracing_sdk")
        _live_st: Dict[str, Any] = (getattr(_sdk, "_live_state", {}) or {}) if _sdk else {}
        session_type: str = _live_st.get("session") or rc.get("event_type", "Race")

        # Build weather context string for system prompts
        wx = rc.get("weather", {})
        _SKIES = ["clear", "partly cloudy", "mostly cloudy", "overcast"]
        _WET   = ["dry", "slightly damp", "damp", "wet", "very wet", "extremely wet"]
        weather_ctx = f"{wx.get('air_temp', 22):.0f}\u00b0C air / {wx.get('track_temp', 30):.0f}\u00b0C track"
        wtness = int(wx.get("track_wetness", 0))
        if wtness > 0:
            weather_ctx += f", {_WET[min(wtness, 5)]} surface"
        skies = int(wx.get("skies", 0))
        if skies > 0:
            weather_ctx += f", {_SKIES[min(skies, 3)]} skies"
        wvel = float(wx.get("wind_vel", 0))
        if wvel > 1.0:
            weather_ctx += f", {wvel:.1f} m/s wind"

        laps_remain = rc.get("laps_remain", 0)
        if not laps_remain and rc.get("total_laps", 0) > 0:
            laps_remain = max(0, rc["total_laps"] - rc.get("current_lap", 0))

        # session_type already resolved above from live state; don't overwrite

        # Standings block — always injected
        standings_ctx = (
            f"Current standings:\n{self._current_standings_text}\n"
            if self._current_standings_text else ""
        )

        # Race bible — injected for CRITICAL/NOTABLE, omitted for ROUTINE/AMBIENT
        if tier.value >= Tier.NOTABLE.value and self._race_timeline:
            bible_ctx = "Key moments so far:\n" + "\n".join(self._race_timeline) + "\n"
        else:
            bible_ctx = ""

        # Active on-track battles — always inject so LLM never invents positions
        _btl_list = _live_st.get("battles", [])
        if _btl_list:
            _blines = [
                f"  car {b['a_num']} (P{b['a_pos']}) vs car {b['b_num']} (P{b['b_pos']}) — {b['gap']:.2f}s gap"
                for b in _btl_list[:4]
            ]
            battles_ctx = "Live on-track battles:\n" + "\n".join(_blines) + "\n"
        else:
            battles_ctx = ""

        system_pbp = _SYSTEM_PBP.format(
            pbp_name     = self._pbp_name,
            station_name = self._station_name,
            track        = rc["track"],
            track_type   = rc.get("track_type", "road"),
            series       = rc["series"],
            session_type = session_type,
            lap          = rc["current_lap"],
            total_laps   = rc["total_laps"],
            laps_remain  = laps_remain,
            weather_ctx  = weather_ctx or "normal conditions",
            battles_ctx  = battles_ctx,
            standings_ctx = standings_ctx,
            bible_ctx    = bible_ctx,
        )
        system_color = _SYSTEM_COLOR.format(
            pbp_name     = self._pbp_name,
            color_name   = self._color_name,
            station_name = self._station_name,
            track        = rc["track"],
            track_type   = rc.get("track_type", "road"),
            series       = rc["series"],
            session_type = session_type,
            lap          = rc["current_lap"],
            total_laps   = rc["total_laps"],
            weather_ctx  = weather_ctx or "normal conditions",
            battles_ctx  = battles_ctx,
            standings_ctx = standings_ctx,
            bible_ctx    = bible_ctx,
        )

        system_analyst = _SYSTEM_ANALYST.format(
            analyst_name = self._analyst_name or "Analyst",
            pbp_name     = self._pbp_name,
            color_name   = self._color_name,
            station_name = self._station_name,
            track        = rc["track"],
            track_type   = rc.get("track_type", "road"),
            series       = rc["series"],
            session_type = session_type,
            standings_ctx = standings_ctx,
        )

        user_prompt = _build_user_prompt(etype, data, session_type)

        # Model selection — keep tokens short to reduce latency
        host_model = self._cfg_get("models.host", "qwen3:8b")
        fast_model = self._cfg_get("models.fast", host_model)
        model      = host_model if tier.value >= Tier.NOTABLE.value else fast_model
        max_tokens = 120   # tight cap — one punchy sentence per voice

        # Voice 1 — PBP (always)
        pbp_text = self._llm(
            system=system_pbp,
            user=user_prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=0.85,
        )

        # Voice 2 — Color (NOTABLE and above only)
        # Explicitly forbidden from repeating PBP — must add new analytical content
        color_text = ""
        if tier.value >= Tier.NOTABLE.value:
            color_text = self._llm(
                system=system_color,
                user=(
                    f"{user_prompt}\n\n"
                    f"[{self._pbp_name} just said: \"{pbp_text}\"]\n"
                    "Do NOT repeat this. Add different, analytical insight only."
                ),
                model=model,
                max_tokens=max_tokens,
                temperature=0.75,
            )

        # Voice 3 — Analyst (CRITICAL only, brief technical observation)
        analyst_text = ""
        if tier.value >= Tier.CRITICAL.value and self._analyst_name:
            analyst_text = self._llm(
                system=system_analyst,
                user=(
                    f"{user_prompt}\n\n"
                    f"[Already said: \"{pbp_text}\" / \"{color_text}\"]"
                    "\nOne technical observation only."
                ),
                model=fast_model,
                max_tokens=80,
                temperature=0.65,
            )

        # Emit all voices as a single multi-voice segment via the TTS pipeline
        self._emit_commentary(tier, etype, pbp_text, color_text, analyst_text)

        self._last_call_ts = time.time()
        self._log("iracing_meta",
                  f"[{etype}/{session_type}] pbp={len(pbp_text)}ch "
                  f"color={len(color_text)}ch analyst={len(analyst_text)}ch")

    def _emit_commentary(self, tier: Tier, etype: str,
                          pbp_text: str, color_text: str, analyst_text: str) -> None:
        """
        Assembles all generated voice lines into a single multi-voice segment
        and enqueues it via db_enqueue_segment so the TTS pipeline renders
        each voice with its correct ONNX model.

        Bundle format uses the script-atoms path in render_segment_audio:
          [{"type": "speech", "voice_id": <name>, "text": <text>, "speaker": <name>}]
        The voice_id must match a key in the manifest voices section.
        """
        script: List[Dict[str, Any]] = []
        if pbp_text.strip():
            script.append({"type": "speech", "voice_id": self._pbp_name,
                            "text": pbp_text.strip(), "speaker": self._pbp_name})
        if color_text.strip():
            script.append({"type": "speech", "voice_id": self._color_name,
                            "text": color_text.strip(), "speaker": self._color_name})
        if analyst_text.strip() and self._analyst_name:
            script.append({"type": "speech", "voice_id": self._analyst_name,
                            "text": analyst_text.strip(), "speaker": self._analyst_name})

        if not script:
            return

        sha1_fn = self._ctx.get("sha1")
        unique_key = f"iracing-{etype}-{pbp_text[:24]}-{int(time.time())}"
        seg_id  = sha1_fn(unique_key) if sha1_fn else str(int(time.time()))
        post_id = sha1_fn(f"iracing-{etype}-{round(time.time(), -1)}") if sha1_fn else seg_id

        seg = {
            "id":         seg_id,
            "post_id":    post_id,
            "source":     "iracing_meta",
            "event_type": etype,
            "title":      f"[{etype}] live commentary",
            "body":       pbp_text.strip(),
            "priority":   90 + tier.value * 2,
            "lead_voice": self._pbp_name,
            "script":     script,
        }

        db_enqueue_fn = self._ctx.get("db_enqueue_segment")
        db_connect_fn = self._ctx.get("db_connect")
        if db_enqueue_fn and db_connect_fn:
            try:
                conn = db_connect_fn()
                db_enqueue_fn(conn, seg)
            except Exception as exc:
                self._log("iracing_meta", f"db_enqueue error: {exc}")
            return

        # Fallback — push PBP line as a StationEvent if DB path unavailable
        try:
            StationEvent = self._ctx.get("StationEvent")
            event_q      = self._ctx.get("event_q")
            if StationEvent and event_q:
                ev = StationEvent(
                    source="iracing_meta", type="commentary",
                    ts=int(time.time()),
                    payload={"voice": self._pbp_name, "text": pbp_text.strip()},
                    priority=seg["priority"],
                )
                event_q.put_nowait(ev)
        except Exception as exc:
            self._log("iracing_meta", f"emit_commentary fallback error: {exc}")

    # kept for backward-compat but no longer used for live commentary
    def _emit_audio_segment(self, voice: str, text: str, etype: str, tier: Tier) -> None:
        pass

    # =========================================================================
    # Talk segment (non-live curated content)
    # =========================================================================

    def _generate_talk_segment(self, segment: Dict[str, Any]) -> Dict[str, Any]:
        """Standard radio segment generation for non-live content."""
        title  = segment.get("title", "")
        body   = segment.get("body", segment.get("angle", ""))
        model  = self._cfg_get("models.host", "qwen3:8b")
        rc     = self._race_ctx

        system = (
            f"/no_think\n"
            f"You are {self._pbp_name}, host of {self._station_name} — "
            f"a sim racing radio station covering live iRacing. "
            f"Tone: knowledgeable, enthusiastic, concise. "
            f"Speak naturally for audio. No bullet points. No preamble."
        )
        user = (
            f"Topic: {title}\n"
            f"Material: {body}\n\n"
            f"Current race context: {rc['track']}, {rc['series']}, "
            f"lap {rc['current_lap']} of {rc['total_laps']}.\n\n"
            f"Write a 2-3 sentence spoken intro for this topic. Reply with only the spoken words."
        )

        intro = self._llm(system=system, user=user, model=model,
                          max_tokens=120, temperature=0.7)

        user2 = (
            f"Topic: {title}\n"
            f"Material: {body[:400]}\n\n"
            f"Write a 1-2 sentence summary of the key point. Reply with only the spoken words."
        )
        summary = self._llm(system=system, user=user2, model=model,
                            max_tokens=100, temperature=0.6)

        # Return in bookmark's expected packet format
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
                # Strip qwen3 / deepseek thinking blocks
                import re
                raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
                return raw
        except Exception as exc:
            self._log("iracing_meta", f"LLM error: {exc}")
        return ""

    def _cfg_get(self, key: str, default: Any = None) -> Any:
        try:
            fn = self._ctx.get("cfg_get")
            if callable(fn):
                return fn(key, default)
        except Exception:
            pass
        # Manual dotted-key lookup fallback
        parts = key.split(".")
        obj   = self._cfg
        for p in parts:
            if isinstance(obj, dict):
                obj = obj.get(p)
            else:
                return default
        return obj if obj is not None else default
