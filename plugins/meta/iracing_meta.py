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
import queue
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
    # Notable
    "position_change":      Tier.NOTABLE,
    "incident":             Tier.NOTABLE,
    "pit_entry":            Tier.NOTABLE,
    "pit_exit":             Tier.NOTABLE,
    # Routine
    "lap_complete":         Tier.ROUTINE,
    "standings_update":     Tier.ROUTINE,
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

_SYSTEM_PBP = """You are {pbp_name}, the play-by-play commentator for {station_name}.
You call every moment like it MATTERS — exclamatory, immediate, vivid.
Keep each call to 1-2 punchy sentences. No bullet points. Spoken words only.
Track: {track}. Series: {series}. Lap {lap} of {total_laps}."""

_SYSTEM_COLOR = """You are {color_name}, the color commentator for {station_name}.
You add analysis, context, and insight to every call. Your partner is calling the action.
Your lines are 1-3 measured sentences. No bullet points. Spoken words only.
Track: {track}. Series: {series}."""

# Event-type → user prompt template
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
        "LAP: {driver} (#{car_num}) completes lap {lap} "
        "in P{position} with a time of {lap_time:.3f}s "
        "(best: {best_time:.3f}s, gap to leader: {gap_to_leader:.2f}s).\n"
        "Call this lap in the context of their race."
    ),

    "position_change": (
        "PASS: {driver} (#{car_num}) just moved from P{from_pos} to P{to_pos} on lap {lap}!\n"
        "{lead_flag}"
        "Make this call feel electric."
    ),

    "incident": (
        "INCIDENT: {driver} (#{car_num}) picked up {delta} incident point(s) "
        "(total: {total}) on lap {lap} in P{position}.\n"
        "React to this incident — was it avoidable? What does it mean for their race?"
    ),

    "pit_entry": (
        "PIT IN: {driver} (#{car_num}) dives into the pits from P{position} on lap {lap}.\n"
        "Call the pit stop — timing, strategy, implications."
    ),

    "pit_exit": (
        "PIT OUT: {driver} (#{car_num}) rejoins the race from pit lane on lap {lap}.\n"
        "React — where do they re-enter? What's the strategy here?"
    ),

    "fastest_lap": (
        "FASTEST LAP: {driver} (#{car_num}) just set the fastest lap of the race: {lap_time:.3f}s "
        "on lap {lap}!\n"
        "Make this moment feel significant."
    ),

    "standings_update": (
        "STANDINGS (lap {lap}/{total_laps}, {flag} flag):\n"
        "{standings_text}\n"
        "Give a concise state-of-race summary. One crisp PBP sentence, one color insight."
    ),

    "race_finish": (
        "RACE OVER! {winner} (#{winner_num}) wins the {series} at {track} after {laps_run} laps!\n"
        "Top 5: {top_five_text}\n"
        "Give the victory call. Make it memorable."
    ),
}


def _build_user_prompt(event_type: str, data: Dict[str, Any]) -> str:
    template = _EVENT_PROMPTS.get(event_type)
    if not template:
        return f"Event: {event_type}\nData: {json.dumps(data)}\nReact to this."
    try:
        # Pre-format derived fields
        extra = {}
        if event_type == "position_change":
            extra["lead_flag"] = "THIS IS A LEAD CHANGE! " if data.get("is_lead_change") else ""
        if event_type == "standings_update":
            top = data.get("top_five", [])
            extra["standings_text"] = "\n".join(
                f"  P{d['pos']}: {d['driver']} (#{d['car_num']}) — lap {d['lap']}"
                + (f" +{d['gap']:.2f}s" if d.get("gap", 0) > 0 else " LEADER")
                for d in top
            )
        if event_type == "race_finish":
            top = data.get("top_five", [])
            extra["top_five_text"] = ", ".join(
                f"P{d['pos']} {d['driver']}" for d in top
            )
        merged = {**data, **extra}
        return template.format_map({k: merged.get(k, "?") for k in _extract_keys(template)})
    except Exception:
        return f"Event: {event_type}\nData: {json.dumps(data, default=str)}"


def _extract_keys(s: str) -> List[str]:
    import string
    formatter = string.Formatter()
    return [fname for _, fname, _, _ in formatter.parse(s) if fname]


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

        # Cooldowns per event type (seconds)
        self._cooldowns: Dict[str, float] = {
            "lap_complete":      8.0,
            "standings_update": 25.0,
            "pit_entry":         6.0,
            "pit_exit":          6.0,
            "flag_change":       5.0,
        }
        self._last_event_ts:   Dict[str, float] = {}

        # Race context memory (persists across calls)
        self._race_ctx: Dict[str, Any] = {
            "track":        "Unknown",
            "series":       "iRacing",
            "total_laps":   0,
            "current_lap":  0,
            "flag":         "green",
            "session_state":"Unknown",
            "fastest_lap":  None,
            "fastest_name": None,
        }

        # Worker thread + queue
        self._q: queue.Queue = queue.Queue(maxsize=32)
        self._stop_evt = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

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
        self._pbp_name   = str((voices.get("pbp")   or {}).get("name", "Alex"))
        self._color_name = str((voices.get("color")  or {}).get("name", "Jordan"))

        self._station_name = str((cfg.get("station") or {}).get("name", "iRacingFM"))

        self._log("iracing_meta", f"iRacingMetaPlugin initialized — voices: "
                  f"pbp={self._pbp_name}, color={self._color_name}")

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
        """Pass-through: regular feed candidates are still curated normally."""
        return candidates

    def generate_script(self, segment: Dict[str, Any],
                        state: Any) -> Dict[str, Any]:
        """Generate a standard talk segment (non-live mode fallback)."""
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
        etype = getattr(event, "event_type", "")
        data  = getattr(event, "data", {}) or {}

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

        # Enqueue for worker
        try:
            self._q.put_nowait((tier, etype, data))
        except queue.Full:
            pass  # drop: queue full means we're already generating

    def _update_race_ctx(self, etype: str, data: Dict[str, Any]) -> None:
        rc = self._race_ctx
        if etype == "session_state_change":
            rc["track"]       = data.get("track", rc["track"])
            rc["series"]      = data.get("series", rc["series"])
            rc["total_laps"]  = data.get("total_laps", rc["total_laps"])
            rc["session_state"] = data.get("to", rc["session_state"])
        elif etype == "flag_change":
            rc["flag"]        = data.get("flag", rc["flag"])
            rc["current_lap"] = data.get("lap", rc["current_lap"])
        elif etype == "fastest_lap":
            rc["fastest_lap"]  = data.get("lap_time")
            rc["fastest_name"] = data.get("driver")
        elif etype in ("lap_complete", "standings_update"):
            rc["current_lap"] = data.get("lap", rc["current_lap"])

    # =========================================================================
    # Background commentary worker
    # =========================================================================

    def _commentary_worker(self) -> None:
        """
        Consumes (tier, etype, data) tuples and generates LLM commentary,
        then emits it back onto the runtime's ui_q / audio queue.
        """
        while not self._stop_evt.is_set():
            try:
                tier, etype, data = self._q.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                self._generate_and_emit(tier, etype, data)
            except Exception as exc:
                self._log("iracing_meta", f"commentary_worker error: {exc}")

    def _generate_and_emit(self, tier: Tier, etype: str, data: Dict[str, Any]) -> None:
        rc = self._race_ctx

        system_pbp = _SYSTEM_PBP.format(
            pbp_name     = self._pbp_name,
            station_name = self._station_name,
            track        = rc["track"],
            series       = rc["series"],
            lap          = rc["current_lap"],
            total_laps   = rc["total_laps"],
        )
        system_color = _SYSTEM_COLOR.format(
            color_name   = self._color_name,
            station_name = self._station_name,
            track        = rc["track"],
            series       = rc["series"],
        )

        user_prompt = _build_user_prompt(etype, data)

        # Model selection — use host model for critical calls, cheaper for routine
        host_model    = self._cfg_get("models.host", "gpt-4o-mini")
        fast_model    = self._cfg_get("models.fast", host_model)
        model = host_model if tier.value >= Tier.NOTABLE.value else fast_model
        max_tokens = 160 if tier.value >= Tier.CRITICAL.value else 80

        # PBP call
        pbp_text = self._llm(
            system=system_pbp,
            user=user_prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=0.85,
        )

        # Color commentary (slightly more considered)
        color_text = self._llm(
            system=system_color,
            user=f"{user_prompt}\n\n[PBP just said: {pbp_text}]\nNow add your color commentary.",
            model=model,
            max_tokens=max_tokens,
            temperature=0.75,
        )

        # Push audio segments via the runtime's emit mechanism
        self._emit_audio_segment(self._pbp_name, pbp_text, etype, tier)
        time.sleep(0.3)  # brief breath between voices
        self._emit_audio_segment(self._color_name, color_text, etype, tier)

        self._last_call_ts = time.time()
        self._log("iracing_meta", f"[{etype}] pbp: {pbp_text[:60]}…")

    def _emit_audio_segment(self, voice: str, text: str, etype: str, tier: Tier) -> None:
        """Push a commentary segment onto the runtime audio / event queue."""
        if not text or not text.strip():
            return

        # Use bookmark's standard segment format
        segment = {
            "source":     "iracing_meta",
            "event_type": etype,
            "voice":      voice,
            "text":       text.strip(),
            "priority":   90 + tier.value * 2,
            "tags":       ["iracing", "live", "commentary", etype],
            "ts":         int(time.time()),
        }

        try:
            # Prefer the dedicated ui_q path that bookmark uses for TTS
            ui_q = self._ctx.get("ui_q")
            if ui_q is not None:
                ui_q.put_nowait({"type": "tts", "voice": voice, "text": text.strip(),
                                 "priority": segment["priority"]})
                return
        except Exception:
            pass

        # Fallback: push as a StationEvent so the regular pipeline handles it
        try:
            StationEvent = self._ctx.get("StationEvent")
            event_q      = self._ctx.get("event_q")
            if StationEvent and event_q:
                ev = StationEvent(
                    source="iracing_meta",
                    event_type="commentary",
                    data=segment,
                    priority=segment["priority"],
                )
                event_q.put_nowait(ev)
        except Exception as exc:
            self._log("iracing_meta", f"emit_audio_segment fallback error: {exc}")

    # =========================================================================
    # Talk segment (non-live curated content)
    # =========================================================================

    def _generate_talk_segment(self, segment: Dict[str, Any]) -> Dict[str, Any]:
        """Standard radio segment generation for non-live content."""
        title  = segment.get("title", "")
        body   = segment.get("body", segment.get("angle", ""))
        model  = self._cfg_get("models.host", "gpt-4o-mini")
        rc     = self._race_ctx

        system = (
            f"You are {self._pbp_name}, host of {self._station_name} — "
            f"a sim racing radio station. You discuss iRacing, simracing news, "
            f"and racing strategy. Tone: knowledgeable, enthusiastic, concise. "
            f"Speak naturally for audio. No bullet points."
        )
        user = (
            f"Topic: {title}\n"
            f"Material: {body}\n\n"
            f"Current race context: {rc['track']}, {rc['series']}, "
            f"lap {rc['current_lap']} of {rc['total_laps']}.\n\n"
            f"Write a 2-4 sentence spoken segment on this topic."
        )

        text = self._llm(system=system, user=user, model=model,
                         max_tokens=200, temperature=0.7)

        return {
            "lead_line":       text,
            "followup_line":   "",
            "supporting_lines":[],
            "takeaway":        title,
        }

    # =========================================================================
    # Helpers
    # =========================================================================

    def _llm(self, system: str, user: str, model: str,
             max_tokens: int = 120, temperature: float = 0.75) -> str:
        try:
            fn = self._ctx.get("llm_generate")
            if callable(fn):
                return fn(system=system, user=user, model=model,
                          max_tokens=max_tokens, temperature=temperature) or ""
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
