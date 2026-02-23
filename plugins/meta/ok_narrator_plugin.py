"""
Oracle Kingdom Meta-Plugin — Boundary Guardian

Turns the Oracle Kingdom simulation engine into lived audio experience.
This is NOT the simulation. This is NOT the court logic.
This is the orchestration layer between Cold Layer state and the
Radio OS audio pipeline.

Architecture:

    [ Cold Layer (oracle_kingdom.py) ]
                  ↓
    [ Meta-Plugin (THIS FILE) ]
                  ↓
    [ Audio CLI + TTS + Pucks ]

Five responsibilities:
  I.   Attention & Presence Routing — spatial focus control
  II.  Interaction Intent Parsing   — classify user speech
  III. LLM Narrative Synthesis      — Hot Layer prompt factory
  IV.  Ritual Layer                 — lifecycle pacing
  V.   Audio Mix Policy             — deterministic state → mix mapping

Design invariants:
  • Simulation is authoritative. LLM cannot mutate world state.
  • LLM output is restricted to tone, dialogue, framing, murmurs.
  • Audio presence is spatial and multi-device.
  • Core determinism is never violated by this layer.
"""

from __future__ import annotations

import json
import math
import os
import queue
import random
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# ── Import MetaPluginBase ────────────────────────────────────
try:
    from bookmark import MetaPluginBase
except ImportError:
    from abc import ABC, abstractmethod
    class MetaPluginBase(ABC):
        @abstractmethod
        def initialize(self, runtime_context, cfg, mem): pass
        @abstractmethod
        def shutdown(self): pass
        def process_input(self, input_data): return []
        def supports_streaming(self): return False

# ── Import Cold Layer (oracle_kingdom) ───────────────────────
try:
    from plugins_disabled import oracle_kingdom as ok
except ImportError:
    try:
        import oracle_kingdom as ok
    except ImportError:
        ok = None

# ── Import Court Layer ───────────────────────────────────────
try:
    from plugins_disabled import oracle_court as court
except ImportError:
    try:
        import oracle_court as court
    except ImportError:
        court = None

# ── Debug ────────────────────────────────────────────────────
OK_META_DEBUG = os.environ.get("OK_META_DEBUG", "").strip() in ("1", "true", "yes")

def _dbg(*a, **kw):
    if OK_META_DEBUG:
        print("[OK-Meta]", *a, **kw)


# ============================================================
# MODULE I: ATTENTION & PRESENCE ROUTING
# ============================================================
#
# Receives mic wake events from pucks.
# Determines which palace location is active.
# Informs Oracle Kingdom of current location.
# Informs Audio CLI of context shift.
#
# No world mutation happens here.
# This is spatial focus control only.

# Physical room → palace location mapping.
# Configured per-installation in station manifest or env.
# Default: single-room mode maps everything to THRONE_ROOM.

DEFAULT_ROOM_MAP: Dict[str, str] = {
    "default":     "THRONE_ROOM",
    "living_room": "COURTYARD",
    "office":      "LIBRARY",
    "bedroom":     "OBSERVATORY",
    "kitchen":     "HARBOR",
    "garage":      "WAR_CHAMBER",
    "bathroom":    "TEMPLE",
    "hallway":     "RAMPARTS",
    "dining_room": "TREASURY",
}


@dataclass
class PresenceState:
    """Tracks the Oracle's physical and virtual spatial state."""
    active_room: str = "default"
    active_location: str = "THRONE_ROOM"
    previous_location: str = "THRONE_ROOM"
    pending_location: Optional[str] = None      # r6-fix#3: staged, not yet confirmed
    pending_room: Optional[str] = None           # r6-fix#3
    ticks_at_location: int = 0
    last_wake_ts: float = 0.0
    session_active: bool = False
    # Per-puck wake debounce (r6-fix#3): puck_id → last wake ts
    _puck_debounce: Dict[str, float] = field(default_factory=dict)
    DEBOUNCE_SEC: float = 2.0  # ignore re-wakes within this window
    # Puck registry: puck_id → room_id
    puck_registry: Dict[str, str] = field(default_factory=dict)
    # Room map override (from manifest)
    room_map: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ROOM_MAP))

    def resolve_location(self, room_id: str) -> str:
        """Map a physical room to a palace location."""
        return self.room_map.get(room_id, self.room_map.get("default", "THRONE_ROOM"))

    def transition_to(self, room_id: str) -> Optional[str]:
        """
        Handle room transition. Returns new location name if changed, else None.

        r6-fix#3: Does NOT mutate active_location directly.
        Stages as pending_location. Only committed on location_confirmed.
        If same location, just increments ticks.
        """
        new_location = self.resolve_location(room_id)
        if new_location == self.active_location:
            self.ticks_at_location += 1
            return None
        # If already pending to this same location, don't re-request
        if new_location == self.pending_location:
            return None
        self.pending_location = new_location
        self.pending_room = room_id
        return new_location

    def confirm_move(self, location: str) -> None:
        """Commit a confirmed move (r6-fix#3). Called on location_confirmed."""
        self.previous_location = self.active_location
        self.active_location = location
        if self.pending_room:
            self.active_room = self.pending_room
        self.pending_location = None
        self.pending_room = None
        self.ticks_at_location = 0

    def cancel_pending(self) -> None:
        """Cancel a pending move (r6-fix#3). Called on move_failed."""
        self.pending_location = None
        self.pending_room = None

    def debounce_ok(self, puck_id: str, now: float) -> bool:
        """Return True if this puck wake is NOT a debounce duplicate (r6-fix#3)."""
        last = self._puck_debounce.get(puck_id, 0.0)
        if now - last < self.DEBOUNCE_SEC:
            return False
        self._puck_debounce[puck_id] = now
        return True


class PresenceRouter:
    """
    Routes spatial attention events.

    Receives:
      - Puck wake events (puck_id, room_id, timestamp)
      - Manual location overrides (web UI, voice command)

    Emits:
      - Location change events to OKController (via ok_cmd_q)
      - Context shift events to Audio CLI
    """

    @staticmethod
    def handle_wake_event(
        presence: PresenceState,
        puck_id: str,
        room_id: str,
        timestamp: float,
        ok_cmd_q: Optional[queue.Queue] = None,
    ) -> Dict[str, Any]:
        """
        Process a mic wake event from a puck.

        r6-fix#3: Debounces per-puck, stages pending_location instead
        of mutating active_location directly. Move only commits on
        location_confirmed from the simulation.

        Returns dict describing the routing action taken.
        """
        # Per-puck debounce (r6-fix#3)
        if puck_id and not presence.debounce_ok(puck_id, timestamp):
            return {
                "room_id": room_id,
                "location": presence.active_location,
                "changed": False,
                "previous": presence.previous_location,
                "timestamp": timestamp,
                "debounced": True,
            }

        presence.last_wake_ts = timestamp
        presence.session_active = True

        # Register puck if new
        if puck_id and puck_id not in presence.puck_registry:
            presence.puck_registry[puck_id] = room_id

        new_loc = presence.transition_to(room_id)
        result = {
            "room_id": room_id,
            "location": new_loc or presence.active_location,
            "changed": new_loc is not None,
            "previous": presence.previous_location,
            "timestamp": timestamp,
        }

        if new_loc and ok_cmd_q:
            # Request simulation to confirm location change
            ok_cmd_q.put({
                "action": "move_oracle",
                "location": new_loc,
            })

        return result

    @staticmethod
    def handle_session_end(presence: PresenceState) -> Dict[str, Any]:
        """Mark session as inactive (e.g., silence timeout, explicit exit)."""
        presence.session_active = False
        return {
            "session_ended": True,
            "last_location": presence.active_location,
            "total_ticks_at_location": presence.ticks_at_location,
        }


# ============================================================
# MODULE II: INTERACTION INTENT PARSING
# ============================================================
#
# Classifies user speech into actionable intent categories.
# Does NOT decide outcomes — only classifies input type.

class SpeechIntent(Enum):
    """Classified intent of user speech."""
    SILENCE        = auto()  # No meaningful speech detected
    CASUAL         = auto()  # Conversational, not game-related
    REFLECTION     = auto()  # Thinking aloud, musing about the kingdom
    INQUIRY        = auto()  # Asking about state ("How is the kingdom?")
    DECREE_INTENT  = auto()  # Wants to issue a decree
    MOVE_INTENT    = auto()  # Wants to move to another room/location
    SYSTEM_COMMAND = auto()  # Meta: save, pause, quit, etc.


@dataclass
class IntentResult:
    """Result of speech intent classification."""
    intent: SpeechIntent = SpeechIntent.SILENCE
    confidence: float = 0.0
    transcript: str = ""
    keywords: List[str] = field(default_factory=list)
    # For decree intent: extracted policy hints
    policy_hints: Dict[str, float] = field(default_factory=dict)
    # For inquiry: what they're asking about
    inquiry_target: str = ""
    # For move intent: target room/location
    move_target: str = ""


def _extract_json_obj(text: str) -> Optional[dict]:
    """
    Extract first JSON object from LLM output using brace balancing (r5-fix#5).

    Models often wrap JSON in commentary, code fences, or emit
    trailing text. This finds the first balanced {...} block and parses it.
    Handles nested objects/arrays and strings with escaped braces.
    Used for intent_classify only — narration templates want plain text.
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except (json.JSONDecodeError, ValueError):
                    return None
    return None


class IntentClassifier:
    """
    Lightweight intent classification.

    Two modes:
      1. Rule-based (fast, no LLM, handles 80% of cases)
      2. LLM-assisted (for ambiguous speech, uses structured JSON output)

    Rule-based runs first. LLM only fires when confidence < threshold.
    """

    # Keyword → intent mapping for rule-based classification
    # All keywords MUST be lowercase — matched against lowered transcript (r6-fix#5)
    DECREE_KEYWORDS = {
        "decree", "declare", "command", "order", "proclaim", "enact",
        "speak", "pronounce", "i decree", "let it be", "so be it",
        "issue", "mandate", "edict",
    }
    INQUIRY_KEYWORDS = {
        "how is", "what is", "tell me", "show me", "status",
        "report", "update", "what about", "how are",
        "who is", "health", "kingdom", "faith", "food", "war",
        "treasury", "morale", "cohesion", "fear", "hope",
    }
    # r6-fix#5: "where" removed — too generic on its own.
    # Inquiry now requires co-occurrence with kingdom terms (handled in scoring).
    INQUIRY_CONTEXT_WORDS = {
        "kingdom", "oracle", "people", "court", "realm", "subjects",
        "faith", "throne", "temple", "council",
    }
    MOVE_KEYWORDS = {
        "go to", "move to", "walk to", "enter", "visit",
        "courtyard", "temple", "library", "harbor", "war chamber",
        "observatory", "treasury", "ramparts", "throne room",
    }
    SYSTEM_KEYWORDS = {
        "save", "load", "pause", "resume", "quit", "exit",
        "options", "settings", "help", "menu",
    }
    REFLECTION_KEYWORDS = {
        "i wonder", "perhaps", "maybe", "i think", "it seems",
        "what if", "i feel", "this reminds me", "years ago",
        "legacy", "fate", "destiny",
    }

    CONFIDENCE_THRESHOLD = 0.6  # Below this, escalate to LLM

    @classmethod
    def classify_rules(cls, transcript: str) -> IntentResult:
        """
        Rule-based intent classification. Fast, deterministic.
        Returns IntentResult with confidence 0–1.

        r6-fix#6: max-per-intent + boost scoring scheme.
        SYSTEM keyword → 0.9, MOVE pattern + location → 0.85,
        DECREE pattern → 0.85, else additive with cap.
        """
        if not transcript or not transcript.strip():
            return IntentResult(intent=SpeechIntent.SILENCE, confidence=1.0)

        text = transcript.lower().strip()
        result = IntentResult(transcript=transcript)

        # Score each intent category
        scores: Dict[SpeechIntent, float] = {
            SpeechIntent.DECREE_INTENT: 0.0,
            SpeechIntent.INQUIRY: 0.0,
            SpeechIntent.MOVE_INTENT: 0.0,
            SpeechIntent.SYSTEM_COMMAND: 0.0,
            SpeechIntent.REFLECTION: 0.0,
            SpeechIntent.CASUAL: 0.0,
        }

        matched_keywords: List[str] = []

        # ── SYSTEM: high-confidence pattern match (r6-fix#6) ──
        for kw in cls.SYSTEM_KEYWORDS:
            if kw in text:
                scores[SpeechIntent.SYSTEM_COMMAND] = max(
                    scores[SpeechIntent.SYSTEM_COMMAND], 0.9
                )
                matched_keywords.append(kw)

        # ── DECREE: high-confidence pattern match ──
        for kw in cls.DECREE_KEYWORDS:
            if kw in text:
                scores[SpeechIntent.DECREE_INTENT] = max(
                    scores[SpeechIntent.DECREE_INTENT], 0.85
                )
                matched_keywords.append(kw)

        # ── MOVE: location name + move verb → high confidence ──
        has_move_verb = any(v in text for v in ("go to", "move to", "walk to", "enter", "visit"))
        has_location = any(loc in text for loc in (
            "courtyard", "temple", "library", "harbor", "war chamber",
            "observatory", "treasury", "ramparts", "throne room",
        ))
        if has_move_verb and has_location:
            scores[SpeechIntent.MOVE_INTENT] = 0.85
            matched_keywords.extend([kw for kw in cls.MOVE_KEYWORDS if kw in text])
        elif has_location:
            # Location name alone without verb — moderate
            scores[SpeechIntent.MOVE_INTENT] = max(scores[SpeechIntent.MOVE_INTENT], 0.55)
            matched_keywords.extend([kw for kw in cls.MOVE_KEYWORDS if kw in text])
        elif has_move_verb:
            scores[SpeechIntent.MOVE_INTENT] = max(scores[SpeechIntent.MOVE_INTENT], 0.45)
            matched_keywords.extend([kw for kw in cls.MOVE_KEYWORDS if kw in text])

        # ── INQUIRY: additive, but "where" only counts with context ──
        inquiry_hits = 0
        for kw in cls.INQUIRY_KEYWORDS:
            if kw in text:
                inquiry_hits += 1
                matched_keywords.append(kw)
        # "where" as a standalone inquiry requires a kingdom-context word
        if "where" in text and any(cw in text for cw in cls.INQUIRY_CONTEXT_WORDS):
            inquiry_hits += 1
            matched_keywords.append("where")
        if inquiry_hits > 0:
            scores[SpeechIntent.INQUIRY] = min(1.0, 0.35 + 0.2 * (inquiry_hits - 1))

        # ── REFLECTION: additive ──
        reflection_hits = 0
        for kw in cls.REFLECTION_KEYWORDS:
            if kw in text:
                reflection_hits += 1
                matched_keywords.append(kw)
        if reflection_hits > 0:
            scores[SpeechIntent.REFLECTION] = min(1.0, 0.35 + 0.15 * (reflection_hits - 1))

        # Short utterances with no matches → casual
        if not matched_keywords:
            word_count = len(text.split())
            if word_count <= 5:
                scores[SpeechIntent.CASUAL] = 0.5
            else:
                scores[SpeechIntent.REFLECTION] = 0.3

        # Select winner
        best_intent = max(scores, key=scores.get)
        best_score = min(1.0, scores[best_intent])

        result.intent = best_intent
        result.confidence = best_score
        result.keywords = matched_keywords

        # Extract move target if move intent
        if best_intent == SpeechIntent.MOVE_INTENT:
            for loc_name in [
                "courtyard", "temple", "library", "harbor",
                "war chamber", "observatory", "treasury",
                "ramparts", "throne room",
            ]:
                if loc_name in text:
                    result.move_target = loc_name.upper().replace(" ", "_")
                    break

        return result

    @classmethod
    def build_llm_classification_prompt(cls, transcript: str,
                                         kingdom_context: str) -> Tuple[str, str]:
        """
        Build structured LLM prompt for ambiguous speech classification.
        Returns (system_prompt, user_prompt).

        The LLM must return strict JSON. No free-form.
        """
        system = """You are a speech intent classifier for Oracle Kingdom.
Classify the user's spoken words into exactly ONE category.

Categories:
- DECREE_INTENT: The user wants to issue a royal decree or make a ruling
- INQUIRY: The user is asking about kingdom state, events, or characters
- REFLECTION: The user is musing, wondering, or thinking aloud about the kingdom
- MOVE_INTENT: The user wants to move to a different palace location
- SYSTEM_COMMAND: Save, load, pause, settings, or other meta-commands
- CASUAL: Social/conversational speech not related to gameplay

Output STRICT JSON only:
{
    "intent": "DECREE_INTENT|INQUIRY|REFLECTION|MOVE_INTENT|SYSTEM_COMMAND|CASUAL",
    "confidence": 0.0-1.0,
    "reasoning": "one sentence why"
}

Do NOT invent game state. Do NOT suggest actions. Classify ONLY."""

        user = f"""Kingdom context: {kingdom_context}

User said: "{transcript}"

Classify this speech intent."""

        return system, user


# ============================================================
# MODULE III: LLM NARRATIVE SYNTHESIS (Hot Layer)
# ============================================================
#
# The most critical boundary guardian.
#
# The LLM must ONLY generate:
#   - Narrative framing
#   - Agent dialogue
#   - Ambient murmurs
#   - Chronicle summaries
#   - Tone modulation
#
# The LLM must NEVER:
#   - Invent state
#   - Modify numbers
#   - Simulate outcomes
#   - Predict the future
#
# All prompts include only canonical state.
# All outputs are restricted to text-only narration.

# ── State Sanitization ───────────────────────────────────────
#
# Before any state reaches an LLM prompt, it passes through
# sanitization. This layer:
#   1. Strips internal IDs and implementation details
#   2. Rounds numbers to human-readable precision
#   3. Translates enum names to natural language
#   4. Caps context length to prevent prompt overflow
#   5. Redacts any mutable references (the LLM sees a snapshot,
#      never a live object)


class StateSanitizer:
    """
    Transforms raw KingdomState into LLM-safe context dictionaries.

    Every method returns a plain dict of strings and numbers.
    No objects, no references, no mutation paths.
    """

    # Variable → human-readable name mapping
    VARIABLE_NAMES = {
        "food_production": "Food Production",
        "food_stores": "Food Reserves",
        "infrastructure": "Infrastructure",
        "trade_volume": "Trade Volume",
        "labor_pool": "Labor Pool",
        "resource_pressure": "Resource Scarcity",
        "treasury": "Treasury",
        "cohesion": "Social Cohesion",
        "class_tension": "Class Tension",
        "cultural_confidence": "Cultural Confidence",
        "literacy": "Literacy",
        "fear_level": "Fear",
        "hope_level": "Hope",
        "legitimacy": "Legitimacy",
        "enforcement_capacity": "Enforcement",
        "corruption": "Corruption",
        "institutional_strength": "Institutional Strength",
        "law_rigidity": "Legal Rigidity",
        "external_threat": "External Threat",
        "public_faith": "Public Faith",
        "interpretation_divergence": "Interpretive Divergence",
        "rumor_distortion": "Rumor Distortion",
        "cultural_memory_strength": "Cultural Memory",
        "sacred_silence_weight": "Sacred Silence Pressure",
    }

    # Era → human language
    ERA_NAMES = {
        "STABLE": "a stable era",
        "RENAISSANCE": "a renaissance",
        "FAMINE_ERA": "a time of famine",
        "AUTHORITARIAN_CONSOLIDATION": "authoritarian consolidation",
        "IDEOLOGICAL_FRACTURE": "ideological fracture",
        "GOLDEN_AGE": "a golden age",
        "DECLINE": "an era of decline",
        "OLIGARCHIC_GRIP": "oligarchic dominance",
        "MILITANT_POSTURE": "militant posture",
        "REFORMATION": "reformation",
    }

    # Health trend → prose
    TREND_NAMES = {
        "rising": "improving",
        "stable": "holding steady",
        "declining": "deteriorating",
    }

    @classmethod
    def _round(cls, v: float, precision: int = 1) -> float:
        return round(v, precision)

    @classmethod
    def _classify_level(cls, v: float) -> str:
        """Convert 0-100 value to qualitative level."""
        if v < 15:
            return "critically low"
        elif v < 30:
            return "low"
        elif v < 45:
            return "moderate"
        elif v < 60:
            return "stable"
        elif v < 75:
            return "strong"
        elif v < 90:
            return "very strong"
        else:
            return "extraordinary"

    @classmethod
    def kingdom_snapshot(cls, ks) -> Dict[str, Any]:
        """
        Full kingdom state snapshot for LLM context.
        Returns plain dict, never mutable objects.
        """
        if ks is None:
            return {"error": "no kingdom state"}

        p = ks.physical
        s = ks.social
        pol = ks.political
        b = ks.belief

        snapshot = {
            "kingdom_name": ks.name,
            "year": ks.world_year,
            "day": ks.world_day,
            "tick": ks.tick,

            # Health
            "health_composite": cls._round(ks.health.composite),
            "health_trend": ks.health.trend,

            # Era
            "era": ks.current_era.name if hasattr(ks.current_era, 'name') else str(ks.current_era),
            "era_prose": cls.ERA_NAMES.get(
                ks.current_era.name if hasattr(ks.current_era, 'name') else str(ks.current_era),
                "an uncertain time"
            ),

            # Physical
            "food_production": cls._round(p.food_production),
            "food_stores": cls._round(p.food_stores),
            "infrastructure": cls._round(p.infrastructure),
            "trade_volume": cls._round(p.trade_volume),
            "labor_pool": cls._round(p.labor_pool),
            "resource_pressure": cls._round(p.resource_pressure),
            "treasury": cls._round(p.treasury, 0),

            # Social
            "cohesion": cls._round(s.cohesion),
            "class_tension": cls._round(s.class_tension),
            "cultural_confidence": cls._round(s.cultural_confidence),
            "literacy": cls._round(s.literacy),
            "fear_level": cls._round(s.fear_level),
            "hope_level": cls._round(s.hope_level),

            # Political
            "legitimacy": cls._round(pol.legitimacy),
            "enforcement_capacity": cls._round(pol.enforcement_capacity),
            "corruption": cls._round(pol.corruption),
            "institutional_strength": cls._round(pol.institutional_strength),
            "law_rigidity": cls._round(pol.law_rigidity),
            "external_threat": cls._round(pol.external_threat),

            # Belief
            "public_faith": cls._round(b.public_faith),
            "interpretation_divergence": cls._round(b.interpretation_divergence),
            "rumor_distortion": cls._round(b.rumor_distortion),
            "sacred_silence": cls._round(b.sacred_silence_weight),
            "cultural_memory": cls._round(b.cultural_memory_strength),

            # Oracle
            "oracle_archetype": getattr(ks, 'oracle_archetype', 'UNKNOWN'),
            "oracle_lifecycle_state": (
                ks.oracle_lifecycle.state.name
                if hasattr(ks, 'oracle_lifecycle') and hasattr(ks.oracle_lifecycle, 'state')
                else "UNKNOWN"
            ),
        }
        return snapshot

    @classmethod
    def location_context(cls, ks, location_name: str) -> Dict[str, Any]:
        """Context for a specific palace location."""
        if court is None:
            return {"location": location_name, "error": "court module not loaded"}

        loc_id = getattr(court.LocationId, location_name, None)
        if loc_id is None:
            return {"location": location_name, "error": "unknown location"}

        profile = court.LOCATION_PROFILES.get(loc_id)
        if profile is None:
            return {"location": location_name}

        # Faction dominance at this location
        faction_presence = {}
        if hasattr(profile, 'faction_density'):
            # Sort by density, show top 3 — qualitative only (r6-fix#9)
            sorted_factions = sorted(
                profile.faction_density.items(),
                key=lambda x: x[1], reverse=True
            )[:3]
            for f, d in sorted_factions:
                if d >= 0.6:
                    faction_presence[f] = "dominant"
                elif d >= 0.3:
                    faction_presence[f] = "notable"
                elif d >= 0.1:
                    faction_presence[f] = "present"

        # Visibility qualitative (r6-fix#9)
        raw_vis = profile.visibility if hasattr(profile, 'visibility') else 0.5
        if raw_vis >= 0.8:
            vis_qual = "highly visible"
        elif raw_vis >= 0.5:
            vis_qual = "moderately visible"
        elif raw_vis >= 0.2:
            vis_qual = "somewhat concealed"
        else:
            vis_qual = "hidden"

        # Legitimacy bias qualitative (r6-fix#9)
        raw_leg = profile.legitimacy_bias if hasattr(profile, 'legitimacy_bias') else 0.0
        if raw_leg > 0.15:
            leg_qual = "bolsters authority"
        elif raw_leg < -0.15:
            leg_qual = "undermines authority"
        else:
            leg_qual = "neutral"

        # Emotional texture qualitative (r6-fix#9)
        emo_qual = {}
        if hasattr(profile, 'emotional_texture'):
            for k, v in profile.emotional_texture.items():
                if v >= 0.6:
                    emo_qual[k] = "intense"
                elif v >= 0.3:
                    emo_qual[k] = "present"
                elif v >= 0.1:
                    emo_qual[k] = "faint"
                # omit negligible (<0.1)

        # Decree multipliers qualitative (r6-fix#9)
        dec_qual = {}
        if hasattr(profile, 'decree_multipliers'):
            for k, v in profile.decree_multipliers.items():
                if abs(v - 1.0) <= 0.05:
                    continue  # neutral, skip
                if v >= 1.3:
                    dec_qual[k] = "greatly amplified"
                elif v >= 1.1:
                    dec_qual[k] = "amplified"
                elif v <= 0.7:
                    dec_qual[k] = "greatly dampened"
                elif v <= 0.9:
                    dec_qual[k] = "dampened"

        return {
            "location": profile.name,
            "description": profile.description,
            "visibility": vis_qual,
            "legitimacy_effect": leg_qual,
            "dominant_factions": faction_presence,
            "emotional_texture": emo_qual,
            "decree_effects": dec_qual,
        }

    @classmethod
    def oracle_traits_context(cls, ks) -> Dict[str, Any]:
        """Oracle personality for LLM character rendering. All qualitative (r6-fix#9)."""
        if ks is None or not hasattr(ks, 'oracle'):
            return {}
        o = ks.oracle
        return {
            "traits": {
                t: cls._classify_level(o.effective(t))
                for t in (o.drifted_traits or o.traits)
            },
            "ego": cls._classify_level(o.ego),
            "stress": cls._classify_level(o.stress),
            "hope": cls._classify_level(o.hope),
            "dread": cls._classify_level(o.dread),
        }

    @classmethod
    def characters_context(cls, ks, max_chars: int = 5) -> List[Dict[str, Any]]:
        """Ensemble cast summary for LLM dialogue generation."""
        if ks is None:
            return []
        chars = []
        for cid, c in list(ks.characters.items())[:max_chars]:
            if not c.alive:
                continue
            chars.append({
                "name": c.name,
                "role": c.role.name.replace("_", " ").title(),
                "faction": c.faction_id,
                "age": c.age,
                "loyalty": cls._classify_level(c.oracle_loyalty),
                "popularity": cls._classify_level(c.public_popularity),
                "ambition": cls._classify_level(c.ambition),
                "stress": cls._classify_level(c.stress),
            })
        return chars

    @classmethod
    def recent_events_context(cls, ks, max_events: int = 5) -> List[Dict[str, str]]:
        """Recent events, sanitized for LLM."""
        if ks is None:
            return []
        events = []
        recent = list(ks.event_history)[-max_events:]
        for e in recent:
            events.append({
                "description": e.description if hasattr(e, 'description') else str(e),
                "severity": cls._classify_level(
                    e.severity if hasattr(e, 'severity') else 50.0
                ),
                "domain": e.domain.name if hasattr(e, 'domain') else "unknown",
            })
        return events

    @classmethod
    def recent_decrees_context(cls, ks, max_decrees: int = 3) -> List[Dict[str, str]]:
        """Recent decrees, sanitized for LLM."""
        if ks is None:
            return []
        decrees = []
        recent = list(ks.decree_history)[-max_decrees:]
        for d in recent:
            decrees.append({
                "text": d.text if hasattr(d, 'text') else str(d),
                "tone": d.tone if hasattr(d, 'tone') else "neutral",
                "tick": d.tick if hasattr(d, 'tick') else 0,
            })
        return decrees

    @classmethod
    def structural_memory_context(cls, ks) -> Dict[str, Any]:
        """Baseline shifts, scars, era transitions — sanitized."""
        if ks is None:
            return {}

        # Recent baseline shifts (last 5)
        shifts = []
        for s in list(ks.baseline_shifts)[-5:]:
            shifts.append({
                "variable": cls.VARIABLE_NAMES.get(s.target_variable, s.target_variable),
                "delta": cls._round(s.delta, 2),
                "trigger": s.trigger_kind if hasattr(s, 'trigger_kind') else "unknown",
                "tick": s.tick if hasattr(s, 'tick') else 0,
            })

        # Recent scars (last 5)
        scars = []
        for sc in list(ks.institutional_scars)[-5:]:
            scars.append({
                "kind": sc.kind if hasattr(sc, 'kind') else "unknown",
                "variable": cls.VARIABLE_NAMES.get(
                    sc.target_variable if hasattr(sc, 'target_variable') else "",
                    sc.target_variable if hasattr(sc, 'target_variable') else "unknown"
                ),
                "severity": cls._classify_level(
                    sc.severity if hasattr(sc, 'severity') else 50.0
                ),
            })

        # Era history (last 3 transitions)
        eras = []
        for er in list(ks.era_history)[-3:]:
            eras.append({
                "era": cls.ERA_NAMES.get(er.era, er.era),
                "started": er.started_tick,
                "ended": er.ended_tick,
            })

        return {
            "baseline_shifts": shifts,
            "institutional_scars": scars,
            "era_transitions": eras,
        }

    @classmethod
    def agent_memory_summary(cls, court_state, max_agents: int = 5) -> List[Dict[str, Any]]:
        """Court agent memory summaries for LLM context."""
        if court_state is None:
            return []

        agents = []
        for aid, agent in list(court_state.agents.items())[:max_agents]:
            recent = agent.recent_memories(3)
            agents.append({
                "name": agent.character_id,
                "disposition": cls._classify_level(max(0, agent.net_disposition() + 50)),
                "trust": cls._classify_level(agent.trust),
                "fear": cls._classify_level(agent.fear),
                "resentment": cls._classify_level(agent.resentment),
                "recent_memories": [
                    m.description for m in recent
                ],
                "agenda": agent.personal_agenda,
            })
        return agents

    @classmethod
    def delta_context(cls, before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute visible state deltas for consequence framing.
        Only includes variables that changed meaningfully.
        """
        deltas = {}
        for key in before:
            if key in after and isinstance(before[key], (int, float)) and isinstance(after[key], (int, float)):
                diff = after[key] - before[key]
                if abs(diff) > 0.5:
                    deltas[key] = {
                        "before": cls._round(before[key]),
                        "after": cls._round(after[key]),
                        "delta": cls._round(diff),
                        "direction": "rose" if diff > 0 else "fell",
                    }
        return deltas


# ── Prompt Templates ─────────────────────────────────────────
#
# Each template is a structured prompt that constrains LLM output.
# The RULES block in each system prompt is the hallucination guardrail.

HALLUCINATION_GUARDRAIL = """ABSOLUTE RULES:
- You are rendering existing state as narrative. You are NOT simulating.
- Do NOT invent events, characters, numbers, or outcomes.
- Do NOT predict what will happen next.
- Do NOT use specific numbers from the state data in your prose.
- Do NOT name characters unless their names are provided in context.
- Every claim in your output must be traceable to the provided state.
- If state data is insufficient, say less — never fill gaps with invention.
- Output plain text only. No JSON. No markdown. No stage directions."""


# ── Output Sanitizer (fix #10) ───────────────────────────────
#
# Post-processing pass on all LLM output before it reaches audio.
# Cheap regex checks that enforce invariants the model may violate.
# Not perfect — but catches the common leaks.

class OutputSanitizer:
    """
    Post-LLM output filter.

    Enforces:
      - No bare digits in prose (strips "42" but not "forty-two")
      - No future tense predictions ("will", "shall", "soon")
      - Max sentence count per template
      - No markdown/code fences
    """

    # Templates → max allowed sentences
    MAX_SENTENCES: Dict[str, int] = {
        "atmosphere": 4,
        "agent_dialogue": 3,
        "consequence": 5,
        "chronicle": 12,
        "murmurs": 10,
        "inner_monologue": 4,
    }

    # Future-tense markers that indicate prediction (not narration) (r6-fix#8: expanded)
    _FUTURE_PATTERNS = re.compile(
        r"\b(will\s+(?:soon|eventually|likely|certainly|surely|probably))\b"
        r"|\b(shall\s+\w+)\b"
        r"|\b(is\s+going\s+to\b)"
        r"|\b(are\s+going\s+to\b)"
        r"|\b(about\s+to\b)"
        r"|\b(on\s+the\s+verge\s+of\b)"
        r"|\b(likely\s+to\b)"
        r"|\b(inevitable|inevitably)\b"
        r"|\b(tomorrow|next\s+(?:day|week|month|season|year))\b",
        re.IGNORECASE,
    )

    # Two-tier digit filter (r6-fix#1):
    # Tier 1: ALWAYS strip — state-adjacent numbers (bare 2+ digits, e.g. "72", "100")
    #         These are the leaked simulation values.
    _STATE_DIGITS = re.compile(r"(?<!\w)\d{2,}(?:st|nd|rd|th)?(?!\w)")
    # Tier 2: Whitelist small digits when next to temporal/contextual words.
    #         "2 years", "3 days", "5 seasons" should survive.
    #         Single bare digits NOT next to whitelisted context are stripped.
    _CONTEXTUAL_DIGIT = re.compile(
        r"(?<!\w)\d(?:\s+(?:year|years|day|days|season|seasons|month|months|week|weeks"
        r"|hour|hours|time|times|step|steps|generation|generations|age|ages))\b",
        re.IGNORECASE,
    )
    _BARE_SINGLE_DIGIT = re.compile(r"(?<!\w)\d(?!\w)")

    # Markdown/code fences
    _MARKDOWN = re.compile(r"```[\s\S]*?```|^#{1,6}\s|^\*{1,3}\s|\*{1,2}[^*]+\*{1,2}", re.MULTILINE)

    @classmethod
    def sanitize(cls, text: str, template: str = "") -> str:
        """
        Clean LLM output. Returns sanitized text.
        Empty string if input is empty/whitespace.
        """
        if not text or not text.strip():
            return ""

        result = text.strip()

        # Strip code fences and markdown formatting
        result = cls._MARKDOWN.sub("", result)

        # Strip digits — tiered approach (r6-fix#1):
        # 1. Always strip 2+ digit numbers (state leaks like "72", "100")
        result = cls._STATE_DIGITS.sub("", result)
        # 2. Strip single bare digits ONLY if not in whitelisted context
        #    (preserves "2 years", "3 days" etc.)
        def _strip_non_contextual_single(m: re.Match) -> str:
            # Check if this single digit is part of a contextual phrase
            start = m.start()
            # Look ahead in original result for context word
            after = result[start:]
            if cls._CONTEXTUAL_DIGIT.match(after):
                return m.group()  # keep it
            return ""  # strip it
        result = cls._BARE_SINGLE_DIGIT.sub(_strip_non_contextual_single, result)

        # Truncate at first future-tense sentence (r5-fix#4, r6-fix#8).
        # Instead of deleting the pattern (which breaks grammar),
        # find the first offending sentence and drop it + everything after.
        # Fallback: if ALL sentences stripped, keep first pre-strip sentence.
        sentences = re.split(r"(?<=[.!?])\s+", result)
        cleaned_sentences = []
        for s in sentences:
            if cls._FUTURE_PATTERNS.search(s):
                break  # drop this sentence and all following
            cleaned_sentences.append(s)
        if cleaned_sentences:
            result = " ".join(cleaned_sentences)
        elif sentences:
            # r6-fix#8: all sentences had future tense — keep first as fallback
            result = sentences[0]

        # Clean up double spaces / orphaned punctuation from removals
        result = re.sub(r"  +", " ", result)
        result = re.sub(r"\s+([.,;:!?])", r"\1", result)
        result = re.sub(r"([.!?])\s*([.!?])", r"\1", result)

        # Enforce sentence cap
        max_sent = cls.MAX_SENTENCES.get(template, 12)
        capped_sentences = re.split(r"(?<=[.!?])\s+", result)
        if len(capped_sentences) > max_sent:
            result = " ".join(capped_sentences[:max_sent])
            # Ensure ends with punctuation
            if result and result[-1] not in ".!?":
                result += "."

        return result.strip()


# ── Narration Budget (r6-fix#12B) ─────────────────────────────
#
# Token-bucket rate limiter preventing runaway LLM narration.
# Two limits enforced:
#   1. Per-category: max narrations per minute by template type
#   2. Global: max total words per minute across all categories
#
# If a category or global budget is exhausted, the narration is
# silently dropped. Deterministic segments (audio_mix_update,
# system events) are NEVER rate-limited.

class NarrationBudget:
    """
    Token-bucket rate limiter for LLM narration output.

    Prevents runaway narration in pathological tick loops
    or rapid-fire decree sequences. Two independent limits:
      - Per-category cap (e.g. max 3 atmosphere per minute)
      - Global word cap (e.g. max 600 words per minute total)

    NOT applied to deterministic system segments.
    """

    # Per-category: max narrations per 60-second window
    CATEGORY_LIMITS: Dict[str, int] = {
        "atmosphere":     2,
        "agent_dialogue": 1,
        "consequence":    4,
        "chronicle":      1,
        "murmurs":        4,
        "inner_monologue": 2,
        "inquiry_response": 3,
        "decree_prompt":   4,
    }

    # Global: max words emitted per 60-second window
    GLOBAL_WORD_LIMIT: int = 350

    # Window duration in seconds
    WINDOW_SEC: float = 60.0

    def __init__(self):
        # category → list of timestamps
        self._category_timestamps: Dict[str, List[float]] = {}
        # list of (timestamp, word_count) tuples
        self._global_words: List[Tuple[float, int]] = []

    def _prune(self, now: float) -> None:
        """Remove entries older than the window."""
        cutoff = now - self.WINDOW_SEC
        for cat in list(self._category_timestamps):
            self._category_timestamps[cat] = [
                ts for ts in self._category_timestamps[cat] if ts > cutoff
            ]
        self._global_words = [
            (ts, wc) for ts, wc in self._global_words if ts > cutoff
        ]

    def allow(self, category: str, word_count: int, now: float) -> bool:
        """
        Check if a narration of this category and word count is allowed.
        Returns True if within budget, False if rate-limited.
        Does NOT record — call record() after confirmed emission.
        """
        self._prune(now)

        # Per-category check
        limit = self.CATEGORY_LIMITS.get(category, 5)
        cat_history = self._category_timestamps.get(category, [])
        if len(cat_history) >= limit:
            return False

        # Global word check
        total_words = sum(wc for _, wc in self._global_words)
        if total_words + word_count > self.GLOBAL_WORD_LIMIT:
            return False

        return True

    def record(self, category: str, word_count: int, now: float) -> None:
        """Record that a narration was emitted."""
        if category not in self._category_timestamps:
            self._category_timestamps[category] = []
        self._category_timestamps[category].append(now)
        self._global_words.append((now, word_count))


# ── Per-Template LLM Temperature ──────────────────────────────
#
# Constrained outputs (consequence, chronicle) need low temperature.
# Creative outputs (atmosphere, murmurs) tolerate higher temperature.
# This prevents tone drift in structured narration.

TEMPLATE_TEMPERATURES: Dict[str, float] = {
    "atmosphere":     0.7,
    "agent_dialogue": 0.8,
    "consequence":    0.4,
    "chronicle":      0.3,
    "murmurs":        0.6,
    "inner_monologue": 0.5,
    "intent_classify": 0.3,
}


# ── Court Voice Pool ─────────────────────────────────────────
#
# Number of distinct voice slots for court agent dialogue.
# Manifest should define voices court_0 .. court_N for these.
# Characters rotate through the pool so different agents get
# different TTS voices.

COURT_VOICE_POOL_SIZE: int = 4


import re as _re

# Pre-compiled pattern: "Name Surname: "quoted text"" or Name: text
_DIALOGUE_LINE_RE = _re.compile(
    r'^([A-Z][A-Za-z\'\- ]{1,30}):\s*["\u201c]?(.+?)["\u201d]?\s*$'
)


def _parse_dialogue_lines(raw: str) -> List[Tuple[str, str]]:
    """
    Parse LLM agent dialogue into (character_name, spoken_text) pairs.

    Expected LLM format:
        Navid Dunmere: "Our faith stands as a beacon..."
        Ulric Ravenscraft: "Opportunities for trade..."

    Returns list of (name, text) tuples, or empty list if unparseable.
    """
    lines = []
    for raw_line in raw.strip().split("\n"):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        m = _DIALOGUE_LINE_RE.match(raw_line)
        if m:
            name = m.group(1).strip()
            text = m.group(2).strip().rstrip('"').rstrip('\u201d').strip()
            if text and len(text) > 5:
                lines.append((name, text))
    return lines


# ── Narrative Memory (Anti-Redundancy) ────────────────────────
#
# Tracks recent narration output to bias prompts away from repetition.
# Light. 5 slots per category. Appended to user prompts as avoidance hints.

@dataclass
class NarrativeMemory:
    """
    Tracks last N narration themes, factions mentioned, and emotional
    tones used. Injected into prompts so the LLM avoids repetition.

    Repetition breaks immersion faster than hallucination.
    """
    recent_themes: deque = field(default_factory=lambda: deque(maxlen=8))
    recent_factions: deque = field(default_factory=lambda: deque(maxlen=8))
    recent_tones: deque = field(default_factory=lambda: deque(maxlen=8))
    recent_character_names: deque = field(default_factory=lambda: deque(maxlen=8))

    # Instrumentation counters (for tuning phase)
    total_generations: int = 0
    generations_by_type: Dict[str, int] = field(default_factory=lambda: {
        "atmosphere": 0, "agent_dialogue": 0, "consequence": 0,
        "chronicle": 0, "murmurs": 0, "inner_monologue": 0,
    })
    total_tokens_approx: int = 0  # rough word-count proxy

    def record(self, narration_type: str, text: str):
        """Extract and store anti-redundancy signals from generated text."""
        self.total_generations += 1
        self.generations_by_type[narration_type] = (
            self.generations_by_type.get(narration_type, 0) + 1
        )
        self.total_tokens_approx += len(text.split())

        text_lower = text.lower()

        # Extract dominant emotional tone (simple keyword scan)
        tone_keywords = {
            "dread": ["dread", "doom", "despair", "bleak"],
            "hope": ["hope", "bright", "dawn", "promise", "light"],
            "fear": ["fear", "tremble", "uneasy", "anxious", "nervous"],
            "reverence": ["sacred", "holy", "divine", "prayer", "worship"],
            "tension": ["tension", "unrest", "crack", "fracture", "strain"],
            "calm": ["calm", "still", "quiet", "peace", "gentle"],
            "anger": ["anger", "fury", "rage", "bitter", "resentment"],
        }
        for tone, keywords in tone_keywords.items():
            if any(kw in text_lower for kw in keywords):
                self.recent_tones.append(tone)
                break

        # Extract faction mentions
        for faction in ["religious", "merchant", "military", "scholarly", "populist"]:
            if faction in text_lower:
                self.recent_factions.append(faction)

        # Extract short theme tag from first sentence
        first_sentence = text.split(".")[0].strip()
        if len(first_sentence) > 10:
            # Use first 6 words as a theme fingerprint
            theme = " ".join(first_sentence.split()[:6]).lower()
            self.recent_themes.append(theme)

    def avoidance_hint(self) -> str:
        """
        Build a short avoidance string for injection into user prompts.
        Returns empty string if no history yet.
        """
        parts = []
        if self.recent_tones:
            recent = list(set(list(self.recent_tones)[-3:]))
            parts.append(f"Avoid repeating these tones: {', '.join(recent)}")
        if self.recent_factions:
            recent = list(set(list(self.recent_factions)[-3:]))
            parts.append(f"Don't over-emphasize: {', '.join(recent)}")
        if self.recent_themes:
            parts.append(f"Previous opening themes to avoid: {'; '.join(list(self.recent_themes)[-2:])}")
        if not parts:
            return ""
        return "\n\nVARIETY GUIDANCE (avoid repetition):\n" + "\n".join(parts)

    def stats_summary(self) -> Dict[str, Any]:
        """Instrumentation snapshot for logging/tuning."""
        return {
            "total_generations": self.total_generations,
            "by_type": dict(self.generations_by_type),
            "approx_words_generated": self.total_tokens_approx,
            "recent_tones": list(self.recent_tones),
            "recent_factions": list(self.recent_factions),
        }


class PromptFactory:
    """
    Constructs structured LLM prompts from sanitized state.

    Every prompt method returns (system_prompt, user_prompt).
    System prompts contain role + rules.
    User prompts contain only canonical state data.
    """

    # ────────────────────────────────────────────────────────
    # 1. LOCATION ATMOSPHERE
    # ────────────────────────────────────────────────────────

    @classmethod
    def atmosphere(cls, snapshot: Dict, location: Dict,
                   oracle_traits: Dict) -> Tuple[str, str]:
        """
        Render 2–4 sentences of ambient atmosphere.
        Tone only. No new events. No hallucinated facts.
        """
        system = f"""You are the ambient narrator for Oracle Kingdom.
You render the emotional atmosphere of a palace location.
Your output is 2–4 sentences. Tone and texture only.
No dialogue. No events. No action.

{HALLUCINATION_GUARDRAIL}

Style: Present tense. Sensory. Literary but concise.
Match the emotional register to the state data provided."""

        user = f"""KINGDOM STATE:
Era: {snapshot.get('era_prose', 'an uncertain time')}
Health: {StateSanitizer._classify_level(snapshot.get('health_composite', 50))} ({snapshot.get('health_trend', 'stable')})
Fear: {StateSanitizer._classify_level(snapshot.get('fear_level', 10))} | Hope: {StateSanitizer._classify_level(snapshot.get('hope_level', 50))}
Cohesion: {StateSanitizer._classify_level(snapshot.get('cohesion', 50))} | Class Tension: {StateSanitizer._classify_level(snapshot.get('class_tension', 20))}
Public Faith: {StateSanitizer._classify_level(snapshot.get('public_faith', 50))}
External Threat: {StateSanitizer._classify_level(snapshot.get('external_threat', 10))}

LOCATION:
{location.get('location', 'Unknown')} — {location.get('description', '')}
Visibility: {location.get('visibility', 'moderately visible')}
Dominant factions: {json.dumps(location.get('dominant_factions', {}))}
Emotional texture: {json.dumps(location.get('emotional_texture', {}))}

ORACLE STATE:
Archetype: {snapshot.get('oracle_archetype', 'UNKNOWN')}
Lifecycle: {snapshot.get('oracle_lifecycle_state', 'ACTIVE')}

Use only qualitative terms. Never cite numbers.
Render the atmosphere of this location right now."""

        return system, user

    # ────────────────────────────────────────────────────────
    # 2. AGENT DIALOGUE
    # ────────────────────────────────────────────────────────

    @classmethod
    def agent_dialogue(cls, snapshot: Dict, location: Dict,
                       characters: List[Dict], agent_memories: List[Dict],
                       oracle_traits: Dict) -> Tuple[str, str]:
        """
        Generate 2–3 short dialogue lines agents might speak.
        Must align with character traits, faction agendas, and location.
        """
        system = f"""You are the dialogue writer for Oracle Kingdom court agents.
Generate 2–3 short spoken lines that agents present at this location might say.
Each line must be attributed to a named character.

{HALLUCINATION_GUARDRAIL}

Rules for dialogue:
- Lines must reflect the character's role, faction, and disposition.
- Lines must respond to the current kingdom conditions.
- No mechanical numbers in dialogue.
- Characters speak in character — a general speaks differently from a scholar.
- Include subtext: what they want, what they fear.
- Lines should be 1–2 sentences each.
- Choose 2–3 of the most relevant characters; not everyone needs to speak.

Output format (plain text):
[Character Name]: "Dialogue line."
[Character Name]: "Dialogue line."
..."""

        chars_text = "\n".join([
            f"  {c['name']} — {c['role']}, {c['faction']} faction, "
            f"loyalty: {c['loyalty']}, ambition: {c['ambition']}, stress: {c['stress']}"
            for c in characters
        ]) if characters else "  (No agents present)"

        memories_text = ""
        if agent_memories:
            memories_text = "\nAGENT RECENT MEMORIES:\n"
            for am in agent_memories:
                mems = ", ".join(am.get('recent_memories', [])[:2]) or "none"
                memories_text += f"  {am['name']} (disposition: {am['disposition']}, agenda: {am['agenda']}): {mems}\n"

        user = f"""KINGDOM STATE:
Era: {snapshot.get('era_prose', 'uncertain')}
Health: {StateSanitizer._classify_level(snapshot.get('health_composite', 50))} ({snapshot.get('health_trend', 'stable')})
Fear: {StateSanitizer._classify_level(snapshot.get('fear_level', 10))} | Hope: {StateSanitizer._classify_level(snapshot.get('hope_level', 50))}
Cohesion: {StateSanitizer._classify_level(snapshot.get('cohesion', 50))} | Faith: {StateSanitizer._classify_level(snapshot.get('public_faith', 50))}
Corruption: {StateSanitizer._classify_level(snapshot.get('corruption', 15))}

LOCATION: {location.get('location', 'Unknown')}
{location.get('description', '')}

CHARACTERS PRESENT:
{chars_text}
{memories_text}
ORACLE ARCHETYPE: {snapshot.get('oracle_archetype', 'UNKNOWN')}

Use only qualitative terms. Never cite numbers.
Generate 2–3 lines of dialogue these agents would speak right now."""

        return system, user

    # ────────────────────────────────────────────────────────
    # 3. CONSEQUENCE FRAMING (After Decree)
    # ────────────────────────────────────────────────────────

    @classmethod
    def consequence_framing(cls, decree_text: str, decree_tone: str,
                            deltas: Dict, location: Dict,
                            snapshot: Dict) -> Tuple[str, str]:
        """
        Summarize visible social reaction to a decree.
        Translates state deltas into atmospheric tone.
        Does NOT describe mechanical effects.
        Does NOT invent outcomes.
        """
        system = f"""You are the consequence narrator for Oracle Kingdom.
The Oracle has just spoken a decree. You describe the visible reaction.
You DO NOT describe mechanical effects or numbers.
You render mood shifts, body language, murmurs, and atmosphere.
2–4 sentences only.

{HALLUCINATION_GUARDRAIL}

Additional rule: You must reflect ONLY the deltas provided.
If a variable rose, the mood should reflect that.
If a variable fell, the mood should reflect that.
Do not invent additional consequences."""

        delta_lines = []
        for var, info in deltas.items():
            nice_name = StateSanitizer.VARIABLE_NAMES.get(var, var)
            # Qualitative magnitude — never leak numbers (fix #9)
            d = abs(info['delta'])
            if d < 2:
                magnitude = "slightly"
            elif d < 6:
                magnitude = "noticeably"
            else:
                magnitude = "sharply"
            delta_lines.append(
                f"  {nice_name}: {info['direction']} ({magnitude})"
            )
        delta_text = "\n".join(delta_lines) if delta_lines else "  (Minimal visible change)"

        user = f"""DECREE: "{decree_text}"
TONE: {decree_tone}
LOCATION: {location.get('location', 'Unknown')}

VISIBLE CHANGES:
{delta_text}

CURRENT STATE:
Fear: {StateSanitizer._classify_level(snapshot.get('fear_level', 10))} | Hope: {StateSanitizer._classify_level(snapshot.get('hope_level', 50))}
Faith: {StateSanitizer._classify_level(snapshot.get('public_faith', 50))} | Cohesion: {StateSanitizer._classify_level(snapshot.get('cohesion', 50))}

Use only qualitative terms. Never cite numbers.
Describe the visible social reaction."""

        return system, user

    # ────────────────────────────────────────────────────────
    # 4. ABSENCE CHRONICLE
    # ────────────────────────────────────────────────────────

    @classmethod
    def absence_chronicle(cls, years_passed: float,
                          events_summary: List[Dict],
                          scars: List[Dict], era_transitions: List[Dict],
                          before_snapshot: Dict,
                          after_snapshot: Dict) -> Tuple[str, str]:
        """
        Render a structured chronicle of what happened while
        the Oracle was absent. Uses ONLY provided state log.
        """
        system = f"""You are the chronicle narrator for Oracle Kingdom.
The Oracle has returned after a period of absence.
Render a structured chronicle of what transpired.

{HALLUCINATION_GUARDRAIL}

Output structure:
1. Opening: How long the Oracle was absent (use the qualitative duration provided, e.g. "a brief absence" or "an age")
2. Major events (3–7, from provided list ONLY)
3. Institutional scars formed (from provided list ONLY)
4. Era transitions (from provided list ONLY)
5. Current state summary

Style: Formal, chronicle-like. Past tense. Factual but resonant.
Do NOT invent any events not in the provided data.
Do NOT use any numbers — durations, severities, and states are given as words."""

        events_text = "\n".join([
            f"  - [{e.get('domain', '?')}] {e.get('description', '?')} (severity: {e.get('severity', '?')})"
            for e in events_summary
        ]) if events_summary else "  (No significant events recorded)"

        scars_text = "\n".join([
            f"  - {s.get('kind', '?')} scar on {s.get('variable', '?')} (severity: {s.get('severity', '?')})"
            for s in scars
        ]) if scars else "  (No institutional scars formed)"

        eras_text = "\n".join([
            f"  - Entered {e.get('era', '?')}"
            + (" (ongoing)" if not e.get('ended') else "")
            for e in era_transitions
        ]) if era_transitions else "  (No era transitions)"

        # Qualitative absence duration (r6-fix#2)
        if years_passed < 0.5:
            absence_qual = "a brief absence (mere months)"
        elif years_passed < 2:
            absence_qual = "a short absence (a year or so)"
        elif years_passed < 5:
            absence_qual = "a notable absence (several years)"
        elif years_passed < 15:
            absence_qual = "a long absence (many years)"
        elif years_passed < 50:
            absence_qual = "a prolonged absence (a generation)"
        else:
            absence_qual = "an age of silence (lifetimes)"

        # Qualitative before/after state (r6-fix#9)
        before_health = StateSanitizer._classify_level(before_snapshot.get('health_composite', 50))
        before_faith = StateSanitizer._classify_level(before_snapshot.get('public_faith', 50))
        after_health = StateSanitizer._classify_level(after_snapshot.get('health_composite', 50))
        after_faith = StateSanitizer._classify_level(after_snapshot.get('public_faith', 50))
        after_fear = StateSanitizer._classify_level(after_snapshot.get('fear_level', 10))
        after_hope = StateSanitizer._classify_level(after_snapshot.get('hope_level', 50))

        user = f"""ABSENCE DURATION: {absence_qual}

EVENTS DURING ABSENCE:
{events_text}

INSTITUTIONAL SCARS:
{scars_text}

ERA TRANSITIONS:
{eras_text}

STATE BEFORE ABSENCE:
Health: {before_health} | Faith: {before_faith}

STATE NOW:
Health: {after_health} | Faith: {after_faith}
Era: {after_snapshot.get('era_prose', '?')}
Fear: {after_fear} | Hope: {after_hope}

Render the chronicle."""

        return system, user

    # ────────────────────────────────────────────────────────
    # 5. MURMUR FRAGMENTS
    # ────────────────────────────────────────────────────────

    @classmethod
    def murmur_fragments(cls, snapshot: Dict, location: Dict,
                         recent_decrees: List[Dict]) -> Tuple[str, str]:
        """
        Generate 5–10 short overheard murmurs (1 sentence each).
        Crowd fragments that reflect current state.
        """
        system = f"""You are the crowd murmur generator for Oracle Kingdom.
Generate 5–10 short overheard fragments — things people whisper, mutter, or say in passing.
Each is 1 sentence. They are atmospheric. They are NOT narration.

{HALLUCINATION_GUARDRAIL}

Rules:
- Murmurs reflect current class tension, fear, faith, and divergence.
- If a recent decree was issued, some murmurs may reference it vaguely.
- No character names unless provided.
- No future predictions.
- No mechanical numbers.
- Vary register: some worried, some hopeful, some bitter, some reverent.

Output format (plain text, one per line):
"Murmur text here."
"Another murmur."
..."""

        decrees_text = ""
        if recent_decrees:
            decrees_text = "\nRECENT DECREES:\n" + "\n".join([
                f'  - "{d.get("text", "")}" (tone: {d.get("tone", "neutral")})'
                for d in recent_decrees
            ])

        user = f"""KINGDOM STATE:
Fear: {StateSanitizer._classify_level(snapshot.get('fear_level', 10))} | Hope: {StateSanitizer._classify_level(snapshot.get('hope_level', 50))}
Class Tension: {StateSanitizer._classify_level(snapshot.get('class_tension', 20))} | Cohesion: {StateSanitizer._classify_level(snapshot.get('cohesion', 50))}
Faith: {StateSanitizer._classify_level(snapshot.get('public_faith', 50))} | Divergence: {StateSanitizer._classify_level(snapshot.get('interpretation_divergence', 5))}
Corruption: {StateSanitizer._classify_level(snapshot.get('corruption', 15))}
Era: {snapshot.get('era_prose', 'uncertain')}
{decrees_text}

LOCATION: {location.get('location', 'Unknown')}

Use only qualitative terms. Never cite numbers.
Generate 5–10 overheard murmurs."""

        return system, user

    # ────────────────────────────────────────────────────────
    # 6. INNER MONOLOGUE (Oracle's private thought)
    # ────────────────────────────────────────────────────────

    @classmethod
    def inner_monologue(cls, snapshot: Dict, oracle_traits: Dict,
                        recent_events: List[Dict],
                        recent_decrees: List[Dict]) -> Tuple[str, str]:
        """
        Generate 1–3 sentences of the Oracle's inner thought.
        Reflects oracle traits and current pressures.
        """
        system = f"""You are the inner voice of the Oracle in Oracle Kingdom.
Generate 1–3 sentences of internal monologue — what the Oracle thinks but does not say.

{HALLUCINATION_GUARDRAIL}

Rules:
- Voice must reflect the Oracle's dominant traits (provided below).
- High clarity → precise, analytical thoughts.
- High doubt → questioning, second-guessing.
- High paranoia → suspicious, watchful.
- High conviction → certain, forceful.
- High empathy → concerned about people's suffering.
- High severity → cold, calculating.
- First person. Present tense. Brief."""

        traits_text = "\n".join([
            f"  {t}: {v}" for t, v in oracle_traits.get('traits', {}).items()
        ]) if oracle_traits.get('traits') else "  (Traits unknown)"

        events_text = "\n".join([
            f"  - {e.get('description', '?')}"
            for e in recent_events
        ]) if recent_events else "  (Nothing notable)"

        user = f"""ORACLE TRAITS:
{traits_text}
Ego: {oracle_traits.get('ego', 'stable')} | Stress: {oracle_traits.get('stress', 'stable')}
Hope: {oracle_traits.get('hope', 'stable')} | Dread: {oracle_traits.get('dread', 'stable')}

KINGDOM HEALTH: {StateSanitizer._classify_level(snapshot.get('health_composite', 50))} ({snapshot.get('health_trend', 'stable')})
ERA: {snapshot.get('era_prose', 'uncertain')}

RECENT EVENTS:
{events_text}

Generate the Oracle's inner thought."""

        return system, user


# ============================================================
# MODULE III-B: NARRATIVE ARC ENGINE (Thematic Threading)
# ============================================================
#
# Problem: without arc tracking, narration reacts to isolated
# state snapshots. After 30 minutes, there's no sense of
# "this session has been about rising famine" or "religious
# fracture has been creeping for 40 ticks."
#
# Solution: lightweight rolling window over simulation state.
# Tracks dominant tension, trending direction, and produces
# a theme bias string for LLM prompts.
#
# NOT simulation. NOT LLM. Pure deterministic math over
# state snapshots. Reads state, never writes it.

@dataclass
class NarrativeArcState:
    """
    Tracks dominant tension vectors over a rolling window
    to give LLM prompts mid-session thematic coherence.

    Updated once per tick from the sanitized snapshot.
    Produces a bias string that's injected into prompts.
    """

    # Rolling window of tension readings (last N ticks)
    WINDOW_SIZE: int = 50

    # Tension dimensions we track (map to snapshot keys)
    TENSION_KEYS: Dict[str, str] = field(default_factory=lambda: {
        "class_tension":             "Class unrest",
        "fear_level":                "Fear",
        "interpretation_divergence": "Religious fracture",
        "resource_pressure":         "Famine pressure",
        "corruption":                "Institutional rot",
        "external_threat":           "External threat",
    })

    # Rolling history: {tension_key: deque of float values}
    history: Dict[str, deque] = field(default_factory=dict)

    # Derived arc state (recomputed each tick)
    dominant_tension: str = ""         # Human name of the top tension
    dominant_key: str = ""             # Snapshot key of the top tension
    dominant_value: float = 0.0        # Current value
    dominant_trend: str = "stable"     # "rising", "falling", "stable"
    secondary_tension: str = ""        # Runner-up
    arc_summary: str = ""              # One-sentence bias string

    def __post_init__(self):
        if not self.history:
            self.history = {
                k: deque(maxlen=self.WINDOW_SIZE)
                for k in self.TENSION_KEYS
            }

    def update(self, snapshot: Dict[str, Any]):
        """
        Feed a new tick's snapshot. Recomputes arc state.
        Called once per tick from _handle_tick.
        """
        # Record current values
        for key in self.TENSION_KEYS:
            val = snapshot.get(key, 0.0)
            self.history[key].append(float(val))

        # Compute averages over the window
        averages: Dict[str, float] = {}
        for key, readings in self.history.items():
            if readings:
                averages[key] = sum(readings) / len(readings)
            else:
                averages[key] = 0.0

        # Find dominant and secondary
        ranked = sorted(averages.items(), key=lambda x: x[1], reverse=True)
        if ranked:
            self.dominant_key = ranked[0][0]
            self.dominant_tension = self.TENSION_KEYS[self.dominant_key]
            self.dominant_value = ranked[0][1]
        if len(ranked) > 1:
            self.secondary_tension = self.TENSION_KEYS[ranked[1][0]]

        # Compute trend (compare last 10 ticks to previous 10)
        readings = self.history.get(self.dominant_key, deque())
        if len(readings) >= 20:
            recent = list(readings)[-10:]
            earlier = list(readings)[-20:-10]
            avg_recent = sum(recent) / len(recent)
            avg_earlier = sum(earlier) / len(earlier)
            delta = avg_recent - avg_earlier
            if delta > 3.0:
                self.dominant_trend = "rising"
            elif delta < -3.0:
                self.dominant_trend = "falling"
            else:
                self.dominant_trend = "stable"
        else:
            self.dominant_trend = "stable"

        # Build arc summary
        self._rebuild_summary()

    def _rebuild_summary(self):
        """Build the one-sentence thematic bias for prompt injection.
        No numbers — keeps the "no numbers in prose" invariant clean
        all the way back to the prompt itself (fix #2)."""
        if not self.dominant_tension:
            self.arc_summary = ""
            return

        trend_word = {
            "rising": "has been steadily rising",
            "falling": "has been gradually easing",
            "stable": "persists at a sustained level",
        }.get(self.dominant_trend, "persists")

        # Qualitative intensity band (never leak numbers into prompts)
        if self.dominant_value < 25:
            level = "low"
        elif self.dominant_value < 45:
            level = "moderate"
        elif self.dominant_value < 65:
            level = "high"
        else:
            level = "extreme"

        parts = [
            f"SESSION ARC: {self.dominant_tension} {trend_word}"
            f" at a {level} intensity."
        ]
        if self.secondary_tension:
            parts.append(
                f" Secondary undercurrent: {self.secondary_tension}."
            )
        parts.append(
            " Let this tension thread through your tone without"
            " naming it explicitly."
        )
        self.arc_summary = "".join(parts)

    def bias_hint(self) -> str:
        """
        Returns the arc bias string for injection into LLM prompts.
        Empty string if insufficient data.
        """
        # Don't bias until we have at least 10 ticks of data
        readings = self.history.get(self.dominant_key, deque())
        if len(readings) < 10:
            return ""
        return self.arc_summary


# ============================================================
# MODULE IV: RITUAL LAYER (Lifecycle Pacing)
# ============================================================
#
# Manages:
#   - Startup ritual (session open)
#   - Re-entry reconstruction narration
#   - Room transition tone
#   - Silence periods
#   - Fade-in / fade-out behaviors
#
# This is pacing, not simulation.

class RitualPhase(Enum):
    """Current ritual phase of the session."""
    DORMANT       = auto()  # No session active
    AWAKENING     = auto()  # Session starting, oracle waking
    ARRIVAL       = auto()  # Oracle has arrived at a location
    ACTIVE        = auto()  # Normal play
    TRANSITIONING = auto()  # Moving between locations
    FADING        = auto()  # Session ending
    RECONSTRUCTING = auto() # Returning from long absence


@dataclass
class RitualState:
    """Tracks the ritual lifecycle of the current session."""
    phase: RitualPhase = RitualPhase.DORMANT
    phase_start_ts: float = 0.0
    session_start_ts: float = 0.0
    transition_source: str = ""
    transition_target: str = ""
    reconstruction_progress: float = 0.0  # 0–1
    silence_ticks: int = 0
    last_narration_ts: float = 0.0

    # Pacing controls (seconds)
    awakening_duration: float = 5.0
    transition_duration: float = 3.0
    fade_duration: float = 4.0
    min_silence_between_narrations: float = 20.0

    def can_narrate(self, now: float) -> bool:
        """Enforce minimum silence between narration outputs."""
        if self.phase in (RitualPhase.DORMANT, RitualPhase.FADING):
            return False
        return (now - self.last_narration_ts) >= self.min_silence_between_narrations

    def mark_narrated(self, now: float):
        self.last_narration_ts = now

    def begin_session(self, now: float):
        self.phase = RitualPhase.AWAKENING
        self.session_start_ts = now
        self.phase_start_ts = now
        self.silence_ticks = 0

    def arrive(self, now: float, location: str):
        self.phase = RitualPhase.ARRIVAL
        self.phase_start_ts = now
        self.transition_target = location

    def activate(self, now: float):
        self.phase = RitualPhase.ACTIVE
        self.phase_start_ts = now

    def begin_transition(self, now: float, source: str, target: str):
        self.phase = RitualPhase.TRANSITIONING
        self.phase_start_ts = now
        self.transition_source = source
        self.transition_target = target

    def begin_fade(self, now: float):
        self.phase = RitualPhase.FADING
        self.phase_start_ts = now

    def end_session(self):
        self.phase = RitualPhase.DORMANT
        self.session_start_ts = 0.0

    def begin_reconstruction(self, now: float):
        self.phase = RitualPhase.RECONSTRUCTING
        self.phase_start_ts = now
        self.reconstruction_progress = 0.0


class RitualEngine:
    """
    Manages session pacing and ritual transitions.

    Returns narration requests (not narration itself) that the
    meta-plugin routes to the LLM or plays as audio cues.
    """

    @staticmethod
    def tick_ritual(ritual: RitualState, now: float) -> Optional[Dict[str, Any]]:
        """
        Advance the ritual state machine. Returns a narration request
        dict if the phase transition requires one, else None.

        During ACTIVE phase, periodically requests atmosphere or
        agent_dialogue narration to keep the experience alive.
        """
        elapsed = now - ritual.phase_start_ts

        if ritual.phase == RitualPhase.AWAKENING:
            if elapsed >= ritual.awakening_duration:
                ritual.activate(now)
                return {
                    "type": "ritual_transition",
                    "from": "AWAKENING",
                    "to": "ACTIVE",
                    "narration_type": "atmosphere",
                }

        elif ritual.phase == RitualPhase.ACTIVE:
            # ── Periodic narration during gameplay ─────────────
            # Alternate between atmosphere and agent_dialogue every
            # min_silence_between_narrations seconds to keep the
            # soundscape alive with LLM-driven content.
            time_since_narration = now - ritual.last_narration_ts if ritual.last_narration_ts > 0 else elapsed
            if time_since_narration >= ritual.min_silence_between_narrations:
                # Alternate: even cycles → atmosphere, odd → agent_dialogue
                ritual.silence_ticks += 1
                narr_type = "atmosphere" if (ritual.silence_ticks % 2 == 0) else "agent_dialogue"
                return {
                    "type": "active_narration",
                    "narration_type": narr_type,
                }

        elif ritual.phase == RitualPhase.TRANSITIONING:
            if elapsed >= ritual.transition_duration:
                ritual.arrive(now, ritual.transition_target)
                return {
                    "type": "ritual_transition",
                    "from": "TRANSITIONING",
                    "to": "ARRIVAL",
                    "location": ritual.transition_target,
                    "narration_type": "atmosphere",
                }

        elif ritual.phase == RitualPhase.ARRIVAL:
            # Brief pause then activate
            if elapsed >= 2.0:
                ritual.activate(now)
                return {
                    "type": "ritual_transition",
                    "from": "ARRIVAL",
                    "to": "ACTIVE",
                    "narration_type": "agent_dialogue",
                }

        elif ritual.phase == RitualPhase.FADING:
            if elapsed >= ritual.fade_duration:
                ritual.end_session()
                return {
                    "type": "ritual_transition",
                    "from": "FADING",
                    "to": "DORMANT",
                    "narration_type": "silence",
                }

        elif ritual.phase == RitualPhase.RECONSTRUCTING:
            # After a brief reconstruction pause, transition to ACTIVE
            # and request atmosphere narration to kick off the LLM.
            if elapsed >= ritual.awakening_duration:
                ritual.activate(now)
                return {
                    "type": "ritual_transition",
                    "from": "RECONSTRUCTING",
                    "to": "ACTIVE",
                    "narration_type": "atmosphere",
                }

        return None


# ============================================================
# MODULE V: AUDIO MIX POLICY
# ============================================================
#
# Deterministic mapping from simulation variables to audio properties.
# No LLM. Pure math. The LLM provides texture; this provides structure.

@dataclass
class AudioMixState:
    """
    Current audio mix properties, derived deterministically
    from kingdom state.

    Values are normalized 0.0–1.0 for audio engine consumption.
    The audio engine (Audio CLI / pucks) maps these to actual
    gain levels, spatial positioning, and synthesis parameters.
    """
    murmur_density: float = 0.3      # How many background voices
    whisper_frequency: float = 0.1   # How often a whisper fires
    silence_depth: float = 0.5       # How deep the silence between events
    harmonic_brightness: float = 0.5 # Tonal warmth/coldness of ambience
    tension_drone: float = 0.0       # Low-frequency tension presence
    crowd_energy: float = 0.3        # General crowd activity level
    sacred_hum: float = 0.0          # Religious/mystical ambient tone
    threat_rumble: float = 0.0       # Military/external threat undertone

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class AudioMixPolicy:
    """
    Deterministic state → audio mix mapping.

    Each mix property is a pure function of simulation variables.
    No randomness. No LLM. Reproducible given the same state.

    These are the equations that turn numbers into atmosphere.
    """

    @staticmethod
    def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, v))

    @staticmethod
    def _sigmoid(x: float, center: float = 50.0, steepness: float = 0.08) -> float:
        """Soft threshold mapping. Returns 0–1."""
        t = (x - center) * steepness
        t = max(-20.0, min(20.0, t))
        return 1.0 / (1.0 + math.exp(-t))

    @classmethod
    def compute_mix(cls, ks) -> AudioMixState:
        """
        Compute the full audio mix from kingdom state.

        Arguments:
            ks: KingdomState (read-only, never mutated)

        Returns:
            AudioMixState with all properties computed.
        """
        if ks is None:
            return AudioMixState()

        p = ks.physical
        s = ks.social
        pol = ks.political
        b = ks.belief

        mix = AudioMixState()

        # ── Murmur Density ────────────────────────────────
        # function(class_tension, faction_density, fear)
        #
        # More tension → more murmuring.
        # More fear → people talk in hushed groups.
        # High cohesion dampens murmurs (people are calm).
        mix.murmur_density = cls._clamp(
            (s.class_tension / 100.0) * 0.4
            + (s.fear_level / 100.0) * 0.3
            + (1.0 - s.cohesion / 100.0) * 0.2
            + 0.1  # baseline ambient murmur
        )

        # ── Whisper Frequency ─────────────────────────────
        # function(paranoia, divergence)
        #
        # Divergence of belief → factional whispering.
        # Oracle paranoia trait increases perceived whisper density.
        # Corruption adds conspiratorial undertone.
        oracle_paranoia = (
            ks.oracle.effective("paranoia") / 100.0
            if hasattr(ks, 'oracle') and hasattr(ks.oracle, 'effective')
            else 0.25
        )
        mix.whisper_frequency = cls._clamp(
            (b.interpretation_divergence / 100.0) * 0.35
            + oracle_paranoia * 0.25
            + (pol.corruption / 100.0) * 0.2
            + (b.rumor_distortion / 100.0) * 0.2
        )

        # ── Silence Depth ─────────────────────────────────
        # function(sacred_silence, oracle_lifecycle_state)
        #
        # Sacred silence weight → deeper quiet.
        # Oracle sleeping/fading → profound silence.
        # High fear also creates silence (people afraid to speak).
        oracle_dormant = 0.0
        if hasattr(ks, 'oracle_lifecycle'):
            lc = ks.oracle_lifecycle
            if hasattr(lc, 'state') and hasattr(lc.state, 'name'):
                if lc.state.name in ("SLEEPING", "FADING"):
                    oracle_dormant = 0.4
                elif lc.state.name == "WAKING":
                    oracle_dormant = 0.2

        mix.silence_depth = cls._clamp(
            (cls._clamp(b.sacred_silence_weight, 0.0, 100.0) / 100.0) * 0.3
            + oracle_dormant
            + cls._sigmoid(s.fear_level, center=60.0) * 0.2
            + 0.1  # baseline silence floor
        )

        # ── Harmonic Brightness ───────────────────────────
        # function(hope, legitimacy)
        #
        # Hope → warmth. Legitimacy → resonance.
        # Fear and decline → darker tones.
        mix.harmonic_brightness = cls._clamp(
            (s.hope_level / 100.0) * 0.4
            + (pol.legitimacy / 100.0) * 0.3
            - (s.fear_level / 100.0) * 0.15
            - (s.class_tension / 100.0) * 0.1
            + 0.05  # never fully dark
        )

        # ── Tension Drone ─────────────────────────────────
        # function(class_tension, enforcement, corruption)
        #
        # Structural tension → subsonic drone.
        # Inversely related to institutional strength.
        inst_weakness = 1.0 - (pol.institutional_strength / 100.0)
        mix.tension_drone = cls._clamp(
            (s.class_tension / 100.0) * 0.35
            + inst_weakness * 0.25
            + (pol.corruption / 100.0) * 0.2
            + cls._sigmoid(p.resource_pressure, center=40.0) * 0.2
        )

        # ── Crowd Energy ──────────────────────────────────
        # function(cohesion, hope, cultural_confidence)
        #
        # Active, hopeful, confident population → energy.
        # Fear and oppression suppress it.
        mix.crowd_energy = cls._clamp(
            (s.cohesion / 100.0) * 0.3
            + (s.hope_level / 100.0) * 0.25
            + (s.cultural_confidence / 100.0) * 0.2
            - (s.fear_level / 100.0) * 0.2
            + 0.05
        )

        # ── Sacred Hum ────────────────────────────────────
        # function(public_faith, cultural_memory)
        #
        # High faith + strong cultural memory → sacred undertone.
        # Presence in temple amplifies (handled by puck routing).
        mix.sacred_hum = cls._clamp(
            (b.public_faith / 100.0) * 0.5
            + (b.cultural_memory_strength / 100.0) * 0.3
            - (b.interpretation_divergence / 100.0) * 0.2
        )

        # ── Threat Rumble ─────────────────────────────────
        # function(external_threat, enforcement_capacity)
        #
        # High external threat → low rumble.
        # Stronger when enforcement is strained.
        # r6-fix#11: clamp inputs before computing strain to prevent saturation
        ext_threat_c = cls._clamp(pol.external_threat, 0.0, 100.0)
        enforce_cap_c = cls._clamp(pol.enforcement_capacity, 0.0, 100.0)
        enforcement_strain = max(0.0, ext_threat_c - enforce_cap_c) / 100.0
        mix.threat_rumble = cls._clamp(
            (ext_threat_c / 100.0) * 0.5
            + enforcement_strain * 0.3
            + cls._sigmoid(s.fear_level, center=50.0) * 0.2
        )

        return mix

    # Per-property smoothing alphas (r5-fix#9).
    # silence_depth and threat_rumble change slowly for ominous feel.
    # whisper_frequency and crowd_energy respond faster for liveliness.
    SMOOTH_ALPHAS: Dict[str, float] = {
        "murmur_density":      0.15,
        "whisper_frequency":   0.25,   # fast — reactive
        "silence_depth":       0.08,   # slow — meditative
        "harmonic_brightness": 0.12,
        "tension_drone":       0.10,
        "crowd_energy":        0.20,   # fast — lively
        "sacred_hum":          0.10,
        "threat_rumble":       0.06,   # very slow — ominous
    }

    @classmethod
    def smooth_mix(cls, previous: AudioMixState, target: AudioMixState,
                   alpha: float = 0.15) -> AudioMixState:
        """
        Exponential smoothing between previous and target mix.

        Uses per-property alphas (r5-fix#9) for distinct response curves.
        The `alpha` parameter is a fallback default only.

        Prevents jarring jumps in audio parameters when state
        changes suddenly. Real soundscapes interpolate.

        Fully deterministic. Same inputs → same output.

        Args:
            previous: last emitted mix state
            target: freshly computed mix from current tick
            alpha: fallback smoothing factor (overridden by SMOOTH_ALPHAS)
        """
        def _lerp(a: float, b: float, al: float) -> float:
            return a + al * (b - a)

        smoothed = AudioMixState()
        for prop in (
            "murmur_density", "whisper_frequency", "silence_depth",
            "harmonic_brightness", "tension_drone", "crowd_energy",
            "sacred_hum", "threat_rumble",
        ):
            a = cls.SMOOTH_ALPHAS.get(prop, alpha)
            setattr(smoothed, prop,
                    _lerp(getattr(previous, prop), getattr(target, prop), a))
        return smoothed


# ============================================================
# MODULE V-B: HYBRID MURMUR BANK (Deterministic + LLM)
# ============================================================
#
# Problem: pure LLM murmurs are expensive, tone-drift over time,
# and become stylistically samey after 30 minutes.
#
# Solution: templated deterministic murmur bank covers 60% of
# ambient murmurs. LLM murmurs only fire when emotional volatility
# exceeds a threshold (something interesting actually happened).
#
# Templates are keyed to state thresholds. No randomness in
# selection — deterministic hash of tick + tension values.

class MurmurBank:
    """
    Deterministic murmur template bank.

    Selects murmurs based on current state thresholds.
    Each template is tied to a condition (fear > X, etc.).
    Selection uses a deterministic hash, not random.
    Tracks recently used templates per-kingdom to avoid repeats (r6-fix#10).
    """

    # Templates: list of (condition_fn, murmur_text) pairs
    # condition_fn takes a snapshot dict, returns bool
    TEMPLATES: List[Tuple[Callable[[Dict], bool], str]] = []

    # Per-kingdom cooldown tracking (r6-fix#10).
    # Class-level dict keyed by kingdom_name → deque of recent texts.
    # Prevents cross-contamination between kingdoms/sessions.
    _recent_by_kingdom: Dict[str, deque] = {}

    @classmethod
    def _init_templates(cls):
        """Populate template bank. Called once at import time."""
        if cls.TEMPLATES:
            return

        T = cls.TEMPLATES

        # Fear murmurs
        T.append((lambda s: s.get("fear_level", 0) > 60,
                  "Did you hear that? The walls have ears now."))
        T.append((lambda s: s.get("fear_level", 0) > 60,
                  "Keep your voice down. They're listening."))
        T.append((lambda s: s.get("fear_level", 0) > 70,
                  "My cousin vanished last week. Just... gone."))
        T.append((lambda s: s.get("fear_level", 0) > 40,
                  "Something feels wrong today. Can you feel it?"))

        # Famine murmurs
        T.append((lambda s: s.get("resource_pressure", 0) > 50,
                  "The granaries are lower than they admit."))
        T.append((lambda s: s.get("food_stores", 100) < 30,
                  "When did bread become a luxury?"))
        T.append((lambda s: s.get("resource_pressure", 0) > 60,
                  "My children ate bark soup again last night."))
        T.append((lambda s: s.get("food_production", 50) < 25,
                  "The fields yield less every season."))

        # Religious fracture
        T.append((lambda s: s.get("interpretation_divergence", 0) > 50,
                  "The temple says one thing, the scholars another."))
        T.append((lambda s: s.get("interpretation_divergence", 0) > 60,
                  "Which version of the truth do you pray to?"))
        T.append((lambda s: s.get("public_faith", 50) < 30,
                  "I stopped praying. What's the point?"))
        T.append((lambda s: s.get("public_faith", 50) > 80,
                  "The Oracle's light guides us still. Have faith."))

        # Political tension
        T.append((lambda s: s.get("corruption", 0) > 60,
                  "The treasury bleeds gold into private pockets."))
        T.append((lambda s: s.get("corruption", 0) > 50,
                  "Justice is for those who can afford it."))
        T.append((lambda s: s.get("legitimacy", 50) < 30,
                  "Who even rules here anymore?"))
        T.append((lambda s: s.get("enforcement_capacity", 50) < 25,
                  "The guards are stretched thin. Very thin."))

        # Class tension
        T.append((lambda s: s.get("class_tension", 0) > 60,
                  "The merchants feast while we starve."))
        T.append((lambda s: s.get("class_tension", 0) > 50,
                  "How long before the square fills with angry faces?"))
        T.append((lambda s: s.get("class_tension", 0) > 70,
                  "There's talk of a march. Real talk."))

        # External threat
        T.append((lambda s: s.get("external_threat", 0) > 50,
                  "Ships on the horizon. More than yesterday."))
        T.append((lambda s: s.get("external_threat", 0) > 60,
                  "My brother guards the wall. He says they're massing."))
        T.append((lambda s: s.get("external_threat", 0) > 40,
                  "The border patrols came back early. That's never good."))

        # Hope
        T.append((lambda s: s.get("hope_level", 50) > 70,
                  "Maybe things are finally turning around."))
        T.append((lambda s: s.get("hope_level", 50) > 60,
                  "The market was busy today. That's a good sign."))

        # Stability / calm
        T.append((lambda s: s.get("cohesion", 50) > 70,
                  "It's been quiet lately. The good kind of quiet."))
        T.append((lambda s: s.get("cohesion", 50) > 60 and s.get("fear_level", 50) < 30,
                  "The children are playing in the courtyard again."))

        # Cultural
        T.append((lambda s: s.get("cultural_confidence", 50) > 70,
                  "The new murals in the square are breathtaking."))
        T.append((lambda s: s.get("literacy", 50) < 25,
                  "Can you read that decree for me? I never learned."))

    @classmethod
    def select_deterministic(cls, snapshot: Dict[str, Any],
                             tick: int, count: int) -> List[str]:
        """
        Select murmurs deterministically from the template bank.

        Uses tick + state hash for repeatable selection.
        Only templates whose conditions are met are eligible.
        Excludes recently used templates per-kingdom (r6-fix#10).
        """
        cls._init_templates()

        kingdom_name = snapshot.get("kingdom_name", "_default")
        if kingdom_name not in cls._recent_by_kingdom:
            cls._recent_by_kingdom[kingdom_name] = deque(maxlen=15)
        recent_dq = cls._recent_by_kingdom[kingdom_name]
        recent_set = set(recent_dq)

        eligible = [
            text for cond, text in cls.TEMPLATES
            if cond(snapshot) and text not in recent_set
        ]
        # Fallback: if cooldown filtered everything, use full eligible
        if not eligible:
            eligible = [text for cond, text in cls.TEMPLATES if cond(snapshot)]
        if not eligible:
            return []

        # Deterministic shuffle using tick + multi-key state hash (fix #8)
        # (same tick + same state → same murmurs, always)
        seed = (
            tick * 31
            + int(snapshot.get("legitimacy", 50)) * 7
            + int(snapshot.get("fear_level", 50)) * 11
            + int(snapshot.get("class_tension", 50)) * 13
            + int(snapshot.get("interpretation_divergence", 50)) * 17
            + int(snapshot.get("cohesion", 50)) * 19
        )
        rng = random.Random(seed)
        rng.shuffle(eligible)
        selected = eligible[:count]

        # Record into per-kingdom cooldown (r6-fix#10)
        for t in selected:
            recent_dq.append(t)

        return selected

    @classmethod
    def emotional_volatility(cls, snapshot: Dict[str, Any]) -> float:
        """
        Compute emotional volatility score (0–1).
        High volatility = something interesting is happening.
        LLM murmurs only fire above the threshold.

        Volatility = how far key metrics are from their neutral midpoint.
        """
        keys = ["fear_level", "class_tension", "interpretation_divergence",
                "corruption", "external_threat"]
        deviations = []
        for k in keys:
            val = snapshot.get(k, 50.0)
            deviation = abs(val - 50.0) / 50.0  # 0 = neutral, 1 = extreme
            deviations.append(deviation)
        return sum(deviations) / len(deviations) if deviations else 0.0

    # Threshold above which LLM murmurs are generated
    LLM_VOLATILITY_THRESHOLD: float = 0.4


# Initialize the template bank at import time
MurmurBank._init_templates()


# ============================================================
# META-PLUGIN: ORCHESTRATOR
# ============================================================
#
# Wires all five modules together into the Radio OS meta-plugin
# contract. Implements MetaPluginBase.

class OracleKingdomMetaPlugin(MetaPluginBase):
    """
    Meta-plugin that turns Oracle Kingdom from engine into experience.

    This is the boundary guardian. It:
      - Protects determinism (LLM never mutates state)
      - Translates math into lived tone
      - Routes spatial attention
      - Preserves ritual pacing
      - Prevents hallucination drift
    """

    def __init__(self):
        # Runtime context (set in initialize())
        self.context: Dict[str, Any] = {}
        self.cfg: Dict[str, Any] = {}
        self.mem: Dict[str, Any] = {}
        self.log_func: Callable = print

        # Module states
        self.presence = PresenceState()
        self.ritual = RitualState()
        self.last_mix = AudioMixState()
        self.last_snapshot: Dict[str, Any] = {}

        # Anti-redundancy and instrumentation
        self.narrative_memory = NarrativeMemory()

        # Narrative arc tracker (mid-session thematic threading)
        self.narrative_arc = NarrativeArcState()

        # Narration rate limiter (r6-fix#12B)
        self.narration_budget = NarrationBudget()

        # Generation tracking
        self.narration_history: deque = deque(maxlen=50)
        self.murmur_cache: List[str] = []
        self.murmur_cache_tick: int = -1

        # Per-tick snapshot cache (r5-fix#10)
        self._cached_snapshot: Dict[str, Any] = {}
        self._cached_tick: int = -1

        # Atmosphere gating (prevent per-tick firing)
        self._last_atmosphere_location: str = ""
        self._last_seen_stability: float = -1.0       # Updated every tick
        self._last_narrated_stability: float = -1.0    # Updated only on narration
        self._atmosphere_stability_threshold: float = 10.0  # delta to re-trigger
        self._last_narrated_volatility: float = 0.0    # r5-fix#6: volatility on last narration
        self._last_narrated_arc_key: str = ""           # r5-fix#6: arc dominant key on last narration

        # Thread safety
        self._lock = threading.RLock()

    # ── Lifecycle ─────────────────────────────────────────

    def initialize(self, runtime_context: Dict[str, Any],
                   cfg: Dict[str, Any], mem: Dict[str, Any]) -> None:
        self.context = runtime_context
        self.cfg = cfg
        self.mem = mem
        self.log_func = runtime_context.get("log", print)
        self._log("meta", "OracleKingdomMetaPlugin initialized")

        # Load room map from manifest if present
        room_map = cfg.get("ok_room_map", {})
        if room_map:
            self.presence.room_map.update(room_map)

        # Load pacing config
        pacing = cfg.get("ok_pacing", {})
        if pacing:
            self.ritual.awakening_duration = pacing.get("awakening_sec", 5.0)
            self.ritual.transition_duration = pacing.get("transition_sec", 3.0)
            self.ritual.fade_duration = pacing.get("fade_sec", 4.0)
            self.ritual.min_silence_between_narrations = pacing.get(
                "min_silence_sec", 8.0
            )

    def shutdown(self) -> None:
        # Log instrumentation summary for tuning phase (review fix #5)
        stats = self.narrative_memory.stats_summary()
        self._log("meta", f"OracleKingdomMetaPlugin shutting down | "
                  f"generations={stats['total_generations']} "
                  f"by_type={stats['by_type']} "
                  f"approx_words={stats['approx_words_generated']}")
        self.ritual.end_session()

    def _log(self, channel: str, msg: str):
        if callable(self.log_func):
            try:
                self.log_func(channel, msg)
            except TypeError:
                print(f"[{channel}] {msg}")

    def _cfg_get(self, path: str, default=None):
        """Dot-path traversal on self.cfg (a nested dict)."""
        cur = self.cfg
        for part in (path or "").split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def _budget_filter(self, segments: List[Dict], now: float) -> List[Dict]:
        """
        Apply narration budget to output segments (r6-fix#12B).

        System segments (voice == '_system') are never rate-limited.
        Narration segments are checked against per-category and global
        word budgets. Over-budget segments are silently dropped.
        """
        filtered = []
        for seg in segments:
            voice = seg.get("voice", "")
            text = seg.get("text", "")
            meta_type = seg.get("metadata", {}).get("type", "")

            # System segments always pass
            if voice == "_system" or not text.strip():
                filtered.append(seg)
                continue

            word_count = len(text.split())
            category = meta_type  # e.g. "ambient_atmosphere", "agent_dialogue", etc.
            # Normalize category names to budget keys
            cat_map = {
                "ambient_atmosphere": "atmosphere",
                "awakening_atmosphere": "atmosphere",
                "inquiry_response": "inquiry_response",
                "inner_monologue": "inner_monologue",
                "consequence_framing": "consequence",
                "absence_chronicle": "chronicle",
                "agent_dialogue": "agent_dialogue",
                "murmur": "murmurs",
                "decree_prompt": "decree_prompt",
            }
            budget_cat = cat_map.get(category, category)

            if self.narration_budget.allow(budget_cat, word_count, now):
                self.narration_budget.record(budget_cat, word_count, now)
                filtered.append(seg)
            else:
                self._log("meta",
                          f"Narration budget: dropped {budget_cat} "
                          f"({word_count} words)")

        return filtered

    def _llm(self, user_prompt: str, system_prompt: str,
             template: str = "", **kwargs) -> str:
        """
        Call LLM through runtime context. Returns raw text.

        Args:
            template: one of TEMPLATE_TEMPERATURES keys. If set, overrides
                      default temperature with the per-template value.
                      Pass this to every generation call for proper tone control.
        """
        llm_fn = self.context.get("llm_generate")
        if not llm_fn:
            self._log("meta", "No LLM function available")
            return ""

        # Per-template temperature (review fix #2)
        temp = kwargs.get("temperature")
        if temp is None:
            temp = TEMPLATE_TEMPERATURES.get(template, 0.7)

        # Inject anti-redundancy hints (review fix #1)
        avoidance = self.narrative_memory.avoidance_hint()
        if avoidance and template not in ("intent_classify",):
            user_prompt = user_prompt + avoidance

        # Inject narrative arc bias (structural gap #1)
        arc_bias = self.narrative_arc.bias_hint()
        if arc_bias and template in ("atmosphere", "agent_dialogue",
                                      "consequence", "murmurs",
                                      "inner_monologue"):
            user_prompt = user_prompt + "\n\n" + arc_bias

        try:
            # CFG is a nested dict — use dot-path traversal
            model = self._cfg_get("models.host", "") or self._cfg_get(
                "models.producer", ""
            )
            result = llm_fn(
                user_prompt,
                system_prompt,
                model=model,
                num_predict=kwargs.get("max_tokens", 400),
                temperature=temp,
                timeout=kwargs.get("timeout", 30),
            ) or ""

            # Record for anti-redundancy + instrumentation
            if result and template:
                self.narrative_memory.record(template, result)

            # Output sanitizer — enforce invariants post-generation (fix #10)
            # Skip for intent_classify (needs raw JSON)
            if template and template != "intent_classify":
                result = OutputSanitizer.sanitize(result, template)

            return result
        except Exception as e:
            self._log("meta", f"LLM call failed: {e}")
            return ""

    # ── State Access ──────────────────────────────────────

    def _get_kingdom(self):
        """Get current KingdomState from the OKController."""
        controller = self.context.get("ok_controller")
        if controller and hasattr(controller, 'state') and controller.state:
            return controller.state.player_kingdom
        return None

    def _get_court_state(self):
        """Get current CourtState if available."""
        controller = self.context.get("ok_controller")
        if controller and hasattr(controller, 'court_state'):
            return controller.court_state
        return None

    def _snapshot(self) -> Dict[str, Any]:
        """
        Get sanitized kingdom snapshot. Caches per tick (r5-fix#10).
        Returns cached result if kingdom tick hasn't advanced.
        """
        ks = self._get_kingdom()
        if ks is None:
            return {}
        current_tick = getattr(ks, 'tick', -1)
        if current_tick == self._cached_tick and self._cached_snapshot:
            return self._cached_snapshot
        snap = StateSanitizer.kingdom_snapshot(ks)
        self.last_snapshot = snap
        self._cached_snapshot = snap
        self._cached_tick = current_tick
        return snap

    # ── Universal process_input ───────────────────────────

    def process_input(self, input_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Universal entry point. Routes by input_type.

        Lock strategy (fix #4): deterministic state reads and mutations
        happen under lock. LLM calls happen OUTSIDE the lock to prevent
        stalling tick processing during model latency spikes.

        Handlers that call LLM are split: they collect prompts under
        lock, release for generation, then reacquire to finalize.

        Supported input_types:
          - 'wake_event': Puck mic wake → presence routing
          - 'transcript': User speech → intent classification → routing
          - 'tick': Simulation tick occurred → atmosphere/mix update
          - 'decree_result': Decree was executed → consequence framing
          - 'session_start': Session beginning → startup ritual
          - 'session_end': Session ending → fade ritual
          - 'reconstruction': Absence reconstruction → chronicle
          - 'mix_query': Request current audio mix state
          - 'location_confirmed': Sim confirmed oracle moved → finalize presence
          - 'move_failed': Sim rejected move → cancel transition
        """
        input_type = input_data.get("input_type", "")
        now = time.time()

        # Fast deterministic paths — hold lock briefly
        if input_type in ("wake_event", "session_end", "mix_query"):
            with self._lock:
                if input_type == "wake_event":
                    return self._budget_filter(self._handle_wake(input_data, now), now)
                elif input_type == "session_end":
                    return self._budget_filter(self._handle_session_end(input_data, now), now)
                else:
                    return self._handle_mix_query()

        # Fast deterministic paths — location confirmation (r5-fix#2)
        if input_type in ("location_confirmed", "move_failed"):
            with self._lock:
                if input_type == "location_confirmed":
                    return self._handle_location_confirmed(input_data, now)
                else:
                    return self._handle_move_failed(input_data, now)

        # LLM-involving paths — collect state under lock, generate outside
        # All pass through budget filter (r6-fix#12B)
        if input_type == "tick":
            return self._record_and_filter(self._handle_tick_unlocked(input_data, now), now)
        elif input_type == "transcript":
            return self._record_and_filter(self._handle_transcript_unlocked(input_data, now), now)
        elif input_type == "decree_result":
            return self._record_and_filter(self._handle_decree_result_unlocked(input_data, now), now)
        elif input_type == "session_start":
            return self._record_and_filter(self._handle_session_start_unlocked(input_data, now), now)
        elif input_type == "reconstruction":
            return self._record_and_filter(self._handle_reconstruction_unlocked(input_data, now), now)

        return []

    def _record_and_filter(self, segments: List[Dict], now: float) -> List[Dict]:
        """Record narration segments to history, then apply budget filter."""
        for seg in segments:
            text = (seg.get("text") or "").strip()
            voice = seg.get("voice", "")
            if text and voice != "_system":
                self.narration_history.append({
                    "text": text,
                    "voice": voice,
                    "metadata": seg.get("metadata", {}),
                    "timestamp": now,
                })
        return self._budget_filter(segments, now)

    # ── Unlock Wrappers (fix #4, properly split r5-fix#1) ──────
    #
    # Pattern: Phase A (lock → read state, build prompts) →
    #          Phase B (NO lock → call _llm) →
    #          Phase C (lock → commit side effects).
    # Prevents tick stalling during LLM latency spikes.

    def _handle_tick_unlocked(self, data: Dict, now: float) -> List[Dict]:
        """Tick handler: 3-phase lock/LLM split."""
        # ── Phase A: deterministic state reads under lock ──────
        with self._lock:
            segments = []
            ks = self._get_kingdom()
            raw_mix = AudioMixPolicy.compute_mix(ks)
            self.last_mix = AudioMixPolicy.smooth_mix(self.last_mix, raw_mix)
            snap = self._snapshot()
            self.narrative_arc.update(snap)
            self._last_seen_stability = (
                snap.get("legitimacy", 50.0) + snap.get("cohesion", 50.0)
            ) / 2.0
            segments.append({
                "text": "",
                "voice": "_system",
                "priority": 0.0,
                "metadata": {
                    "type": "audio_mix_update",
                    "mix": self.last_mix.to_dict(),
                },
            })
            ritual_req = RitualEngine.tick_ritual(self.ritual, now)

            # Decide what prompts to build (still under lock)
            llm_task = None  # None | "atmosphere" | "agent_dialogue"
            if ritual_req and ritual_req.get("narration_type") == "atmosphere":
                # For periodic active_narration, skip the atmosphere gate —
                # the silence timeout already ensures we don't spam.
                # For transition-driven requests, still respect the gate.
                is_periodic = ritual_req.get("type") == "active_narration"
                if self.ritual.can_narrate(now) and (is_periodic or self._atmosphere_should_fire(ks, now, snap)):
                    location = StateSanitizer.location_context(
                        ks, self.presence.active_location
                    )
                    oracle_traits = StateSanitizer.oracle_traits_context(ks)
                    sys_p, usr_p = PromptFactory.atmosphere(
                        snap, location, oracle_traits
                    )
                    llm_task = ("atmosphere", sys_p, usr_p)
            elif ritual_req and ritual_req.get("narration_type") == "agent_dialogue":
                if self.ritual.can_narrate(now):
                    location = StateSanitizer.location_context(
                        ks, self.presence.active_location
                    )
                    chars = StateSanitizer.characters_context(ks)
                    court_st = self._get_court_state()
                    agent_mems = StateSanitizer.agent_memory_summary(court_st)
                    oracle_traits = StateSanitizer.oracle_traits_context(ks)
                    sys_p, usr_p = PromptFactory.agent_dialogue(
                        snap, location, chars, agent_mems, oracle_traits
                    )
                    llm_task = ("agent_dialogue", sys_p, usr_p)

            active_loc = self.presence.active_location
            seen_stab = self._last_seen_stability
        # ── lock released ──────────────────────────────────────

        # ── Phase B: LLM call outside lock ─────────────────────
        llm_text = ""
        if llm_task:
            ttype, sp, up = llm_task
            max_tok = 200 if ttype == "atmosphere" else 180
            llm_text = self._llm(up, sp, template=ttype, max_tokens=max_tok)

        # ── Phase C: commit side effects under lock ────────────
        if llm_text:
            with self._lock:
                if llm_task[0] == "atmosphere":
                    segments.append({
                        "text": llm_text.strip(),
                        "voice": "narrator",
                        "priority": 40.0,
                        "metadata": {"type": "ambient_atmosphere"},
                    })
                    self.ritual.mark_narrated(now)
                    self._last_atmosphere_location = active_loc
                    self._last_narrated_stability = seen_stab
                    # Record volatility + arc key for gate (r5-fix#6)
                    self._last_narrated_volatility = MurmurBank.emotional_volatility(snap)
                    self._last_narrated_arc_key = self.narrative_arc.dominant_key
                elif llm_task[0] == "agent_dialogue":
                    # Parse multi-character dialogue and emit as a single
                    # segment with script atoms so the TTS pipeline renders
                    # each line with a different voice in one pass.
                    dialogue_lines = _parse_dialogue_lines(llm_text)
                    if dialogue_lines:
                        script_atoms = []
                        for i, (char_name, line_text) in enumerate(dialogue_lines):
                            voice_key = f"court_{i % COURT_VOICE_POOL_SIZE}"
                            script_atoms.append({
                                "type": "speech",
                                "voice_id": voice_key,
                                "speaker": char_name,
                                "text": line_text.strip(),
                            })
                        segments.append({
                            "text": llm_text.strip(),
                            "voice": "court_agents",
                            "priority": 55.0,
                            "metadata": {"type": "agent_dialogue"},
                            "script": script_atoms,
                        })
                    else:
                        # Fallback: couldn't parse lines, emit whole block
                        segments.append({
                            "text": llm_text.strip(),
                            "voice": "court_agents",
                            "priority": 55.0,
                            "metadata": {"type": "agent_dialogue"},
                        })
                    self.ritual.mark_narrated(now)

        return segments

    def _handle_transcript_unlocked(self, data: Dict, now: float) -> List[Dict]:
        """Transcript handler: 3-phase lock/LLM split."""
        transcript = data.get("transcript", "")

        # ── Phase A: rule-based classification (no LLM, fast) ──
        intent_result = IntentClassifier.classify_rules(transcript)

        # ── Phase B-1: LLM classification if needed (no lock) ──
        if intent_result.confidence < IntentClassifier.CONFIDENCE_THRESHOLD:
            with self._lock:
                snapshot = self._snapshot()
            sys_p, usr_p = IntentClassifier.build_llm_classification_prompt(
                transcript, json.dumps(snapshot, default=str)[:500]
            )
            raw = self._llm(usr_p, sys_p, template="intent_classify",
                            max_tokens=100, temperature=0.3)
            if raw:
                parsed = _extract_json_obj(raw)
                if parsed:
                    intent_name = parsed.get("intent", "").upper()
                    if hasattr(SpeechIntent, intent_name):
                        intent_result.intent = SpeechIntent[intent_name]
                        # Clamp confidence to [0, 1], keep previous if missing (r6-fix#7)
                        raw_conf = parsed.get("confidence")
                        if raw_conf is not None:
                            try:
                                intent_result.confidence = max(0.0, min(1.0, float(raw_conf)))
                            except (TypeError, ValueError):
                                pass  # keep previous confidence

        # ── Phase A-2: collect state for intent routing (lock) ──
        with self._lock:
            ok_cmd_q = self.context.get("ok_cmd_q")
            segments = []

            if intent_result.intent == SpeechIntent.DECREE_INTENT:
                if ok_cmd_q:
                    ok_cmd_q.put({"action": "generate_speech", "mode": "DECREE"})
                segments.append({
                    "text": "The Oracle prepares to speak.",
                    "voice": "narrator",
                    "priority": 90.0,
                    "metadata": {"type": "decree_prompt", "intent": "DECREE"},
                })
                return segments

            elif intent_result.intent == SpeechIntent.MOVE_INTENT:
                target = intent_result.move_target
                if target and ok_cmd_q:
                    ok_cmd_q.put({"action": "move_oracle", "location": target})
                    self.ritual.begin_transition(
                        now, self.presence.active_location, target
                    )
                    segments.append({
                        "text": "",
                        "voice": "_system",
                        "priority": 0.0,
                        "metadata": {
                            "type": "move_requested",
                            "target": target,
                            "awaiting_confirmation": True,
                        },
                    })
                return segments

            elif intent_result.intent == SpeechIntent.SYSTEM_COMMAND:
                if ok_cmd_q:
                    ok_cmd_q.put({
                        "action": "system_command",
                        "transcript": transcript,
                    })
                return segments

            elif intent_result.intent == SpeechIntent.SILENCE:
                self.ritual.silence_ticks += 1
                return segments

            # For INQUIRY and REFLECTION we need LLM — collect prompts
            llm_task = None
            ks = self._get_kingdom()
            snapshot = self._snapshot()

            if intent_result.intent == SpeechIntent.INQUIRY:
                location = StateSanitizer.location_context(
                    ks, self.presence.active_location
                )
                oracle_traits = StateSanitizer.oracle_traits_context(ks)
                sys_p, usr_p = PromptFactory.atmosphere(
                    snapshot, location, oracle_traits
                )
                llm_task = ("inquiry", sys_p, usr_p)

            elif intent_result.intent == SpeechIntent.REFLECTION:
                oracle_traits = StateSanitizer.oracle_traits_context(ks)
                events = StateSanitizer.recent_events_context(ks)
                decrees = StateSanitizer.recent_decrees_context(ks)
                sys_p, usr_p = PromptFactory.inner_monologue(
                    snapshot, oracle_traits, events, decrees
                )
                llm_task = ("reflection", sys_p, usr_p)
        # ── lock released ──────────────────────────────────────

        # ── Phase B-2: LLM generation outside lock ─────────────
        if llm_task:
            ttype, sp, up = llm_task
            if ttype == "inquiry":
                text = self._llm(up, sp, template="atmosphere", max_tokens=200)
                if text:
                    segments.append({
                        "text": text.strip(),
                        "voice": "narrator",
                        "priority": 60.0,
                        "metadata": {"type": "inquiry_response"},
                    })
            elif ttype == "reflection":
                text = self._llm(up, sp, template="inner_monologue",
                                 max_tokens=150)
                if text:
                    segments.append({
                        "text": text.strip(),
                        "voice": "oracle_inner",
                        "priority": 50.0,
                        "metadata": {"type": "inner_monologue"},
                    })

        return segments

    def _handle_decree_result_unlocked(self, data: Dict, now: float) -> List[Dict]:
        """Decree result handler: 3-phase lock/LLM split."""
        # ── Phase A: collect state under lock ──────────────────
        with self._lock:
            decree_text = data.get("decree_text", "")
            decree_tone = data.get("decree_tone", "neutral")
            before = data.get("before_snapshot", {})
            after = data.get("after_snapshot", {})
            deltas = StateSanitizer.delta_context(before, after)
            ks = self._get_kingdom()
            location = StateSanitizer.location_context(
                ks, self.presence.active_location
            )
            snapshot = self._snapshot()
            murmur_density = self.last_mix.murmur_density
            sys_p, usr_p = PromptFactory.consequence_framing(
                decree_text, decree_tone, deltas, location, snapshot
            )
            # Pre-compute murmur prompt in case we need LLM murmurs
            max_murmurs = max(1, min(8, int(murmur_density * 10)))
            if murmur_density < 0.05:
                max_murmurs = 0
            volatility = MurmurBank.emotional_volatility(snapshot) if max_murmurs > 0 else 0.0
            tick = snapshot.get("tick", 0)
            murmur_prompt = None
            if max_murmurs > 0 and volatility >= MurmurBank.LLM_VOLATILITY_THRESHOLD:
                decrees = StateSanitizer.recent_decrees_context(ks)
                ms, mu = PromptFactory.murmur_fragments(snapshot, location, decrees)
                murmur_prompt = (ms, mu)
            elif max_murmurs > 0:
                det_murmurs = MurmurBank.select_deterministic(
                    snapshot, tick, max_murmurs
                )
            else:
                det_murmurs = []
        # ── lock released ──────────────────────────────────────

        # ── Phase B: LLM calls outside lock ────────────────────
        segments = []
        text = self._llm(usr_p, sys_p, template="consequence", max_tokens=200)
        if text:
            segments.append({
                "text": text.strip(),
                "voice": "narrator",
                "priority": 85.0,
                "metadata": {
                    "type": "consequence_framing",
                    "decree": decree_text,
                    "deltas": deltas,
                },
            })

        murmurs = []
        if max_murmurs > 0:
            if murmur_prompt:
                murmur_text = self._llm(murmur_prompt[1], murmur_prompt[0],
                                        template="murmurs", max_tokens=300)
                if murmur_text:
                    murmurs = [
                        line.strip().strip('"').strip('\u201c').strip('\u201d')
                        for line in murmur_text.strip().split("\n")
                        if line.strip() and len(line.strip()) > 5
                    ]
                else:
                    murmurs = MurmurBank.select_deterministic(
                        snapshot, tick, max_murmurs
                    )
            else:
                murmurs = det_murmurs

        # ── Phase C: commit under lock ─────────────────────────
        if murmurs:
            with self._lock:
                self.murmur_cache = murmurs[:10]
            for i, m in enumerate(murmurs[:max_murmurs]):
                segments.append({
                    "text": m,
                    "voice": f"murmur_{i}",
                    "priority": 30.0 - i * 2,
                    "metadata": {
                        "type": "murmur",
                        "index": i,
                        "density": murmur_density,
                        "source": "llm" if murmur_prompt else "template",
                    },
                })

        return segments

    def _handle_session_start_unlocked(self, data: Dict, now: float) -> List[Dict]:
        """Session start handler: 3-phase lock/LLM split."""
        # ── Phase A: check lifecycle under lock ────────────────
        with self._lock:
            ks = self._get_kingdom()
            segments = []

            needs_reconstruction = False
            if ks and hasattr(ks, 'oracle_lifecycle'):
                lc = ks.oracle_lifecycle
                if hasattr(lc, 'state') and hasattr(lc.state, 'name'):
                    if lc.state.name in ("SLEEPING", "FADING"):
                        needs_reconstruction = True

            if needs_reconstruction:
                # Start reconstruction phase but still generate atmosphere
                self.ritual.begin_reconstruction(now)
            else:
                # Normal awakening
                self.ritual.begin_session(now)

            # Build atmosphere prompt under lock (both paths need it)
            snapshot = self._snapshot()
            location = StateSanitizer.location_context(
                ks, self.presence.active_location
            )
            oracle_traits = StateSanitizer.oracle_traits_context(ks)
            sys_p, usr_p = PromptFactory.atmosphere(
                snapshot, location, oracle_traits
            )
        # ── lock released ──────────────────────────────────────

        # ── Phase B: LLM call outside lock ─────────────────────
        text = self._llm(usr_p, sys_p, template="atmosphere", max_tokens=200)

        # ── Phase C: commit under lock ─────────────────────────
        if text:
            with self._lock:
                segments.append({
                    "text": text.strip(),
                    "voice": "narrator",
                    "priority": 70.0,
                    "metadata": {"type": "awakening_atmosphere"},
                })
                self.ritual.mark_narrated(now)

        return segments

    def _handle_reconstruction_unlocked(self, data: Dict, now: float) -> List[Dict]:
        """Reconstruction handler: 3-phase lock/LLM split."""
        # ── Phase A: collect state under lock ──────────────────
        with self._lock:
            ks = self._get_kingdom()
            if ks is None:
                return []
            years_passed = data.get("years_passed", 0.0)
            before = data.get("before_snapshot", {})
            after = self._snapshot()
            events = StateSanitizer.recent_events_context(ks, max_events=7)
            structural = StateSanitizer.structural_memory_context(ks)
            sys_p, usr_p = PromptFactory.absence_chronicle(
                years_passed,
                events,
                structural.get("institutional_scars", []),
                structural.get("era_transitions", []),
                before,
                after,
            )
        # ── lock released ──────────────────────────────────────

        # ── Phase B: LLM call outside lock ─────────────────────
        text = self._llm(usr_p, sys_p, template="chronicle", max_tokens=500)

        # ── Phase C: build segments (no mutable state to commit) ─
        segments = []
        if text:
            segments.append({
                "text": text.strip(),
                "voice": "chronicler",
                "priority": 95.0,
                "metadata": {
                    "type": "absence_chronicle",
                    "years_passed": years_passed,
                },
            })
        return segments

    # ── Input Handlers ────────────────────────────────────

    def _handle_wake(self, data: Dict, now: float) -> List[Dict]:
        """Handle puck wake event → presence routing."""
        puck_id = data.get("puck_id", "")
        room_id = data.get("room_id", "default")
        ok_cmd_q = self.context.get("ok_cmd_q")

        # Capture session state BEFORE routing mutates it (fix #1)
        was_active = self.presence.session_active

        route_result = PresenceRouter.handle_wake_event(
            self.presence, puck_id, room_id, now, ok_cmd_q
        )

        segments = []

        if not was_active:
            # First wake of session — start awakening ritual
            self.ritual.begin_session(now)
            if route_result["changed"]:
                # First wake also implies a location — treat as arrival
                self.ritual.arrive(now, route_result["location"])
            segments.append({
                "text": "",
                "voice": "_system",
                "priority": 0.0,
                "metadata": {
                    "type": "session_awakening",
                    "location": route_result["location"],
                },
            })
        elif route_result["changed"]:
            # Already in session, location changed — transition
            self.ritual.begin_transition(
                now,
                route_result["previous"],
                route_result["location"],
            )
            segments.append({
                "text": "",
                "voice": "_system",
                "priority": 0.0,
                "metadata": {
                    "type": "location_transition",
                    "from": route_result["previous"],
                    "to": route_result["location"],
                },
            })

        return segments

    def _handle_location_confirmed(self, data: Dict, now: float) -> List[Dict]:
        """
        Handle sim confirmation that oracle moved successfully (r5-fix#2, r6-fix#3).
        Now safe to commit presence.active_location via confirm_move().
        """
        location = data.get("location", "")
        if location:
            self.presence.confirm_move(location)
        # Complete the transition ritual if we were transitioning
        if self.ritual.phase == RitualPhase.TRANSITIONING:
            self.ritual.arrive(now, location)
        return [{
            "text": "",
            "voice": "_system",
            "priority": 0.0,
            "metadata": {
                "type": "location_confirmed",
                "location": location,
            },
        }]

    def _handle_move_failed(self, data: Dict, now: float) -> List[Dict]:
        """
        Handle sim rejection of a move request (r5-fix#2, r6-fix#3).
        Cancel pending move and keep current location.
        """
        reason = data.get("reason", "unknown")
        self.presence.cancel_pending()
        if self.ritual.phase == RitualPhase.TRANSITIONING:
            self.ritual.activate(now)  # snap back to ACTIVE
        return [{
            "text": "",
            "voice": "_system",
            "priority": 0.0,
            "metadata": {
                "type": "move_failed",
                "reason": reason,
                "current_location": self.presence.active_location,
            },
        }]

    def _handle_transcript(self, data: Dict, now: float) -> List[Dict]:
        """Legacy: superseded by _handle_transcript_unlocked (r5-fix#1)."""
        return self._handle_transcript_unlocked(data, now)

    def _handle_tick(self, data: Dict, now: float) -> List[Dict]:
        """Legacy: superseded by _handle_tick_unlocked (r5-fix#1)."""
        return self._handle_tick_unlocked(data, now)

    def _atmosphere_should_fire(self, ks, now: float,
                               snap: Optional[Dict] = None) -> bool:
        """
        Gate: atmosphere generation only when something meaningful changed.

        Conditions (any one is sufficient):
          1. Location changed since last atmosphere
          2. Kingdom stability composite crossed a threshold (delta > 10)
             Uses _last_seen_stability (updated every tick) vs
             _last_narrated_stability (updated only on narration) (fix #5)
          3. Long silence (3× min_silence_between_narrations)
          4. Emotional volatility crossed threshold since last narration (r5-fix#6)
          5. Narrative arc dominant_key changed (r5-fix#6)

        r6-fix#4: accepts current-tick snap instead of reading self.last_snapshot.
        """
        # Condition 1: location change
        current_loc = self.presence.active_location
        if current_loc != self._last_atmosphere_location:
            return True

        # Condition 2: stability threshold crossed since last narration
        if self._last_narrated_stability >= 0:
            delta = abs(self._last_seen_stability - self._last_narrated_stability)
            if delta >= self._atmosphere_stability_threshold:
                return True

        # Condition 3: long silence (3× normal narration gap)
        silence_threshold = self.ritual.min_silence_between_narrations * 3.0
        if self.ritual.last_narration_ts > 0:
            elapsed = now - self.ritual.last_narration_ts
            if elapsed >= silence_threshold:
                return True
        else:
            # Never narrated — first atmosphere is fine
            return True

        # Condition 4: emotional volatility spike (r5-fix#6, r6-fix#4)
        current_snap = snap if snap else (self.last_snapshot or {})
        vol = MurmurBank.emotional_volatility(current_snap)
        if vol >= MurmurBank.LLM_VOLATILITY_THRESHOLD and (
            self._last_narrated_volatility < MurmurBank.LLM_VOLATILITY_THRESHOLD
        ):
            return True

        # Condition 5: narrative arc theme shifted (r5-fix#6)
        if (self.narrative_arc.dominant_key
                and self.narrative_arc.dominant_key != self._last_narrated_arc_key):
            return True

        return False

    def _handle_decree_result(self, data: Dict, now: float) -> List[Dict]:
        """Legacy: superseded by _handle_decree_result_unlocked (r5-fix#1)."""
        return self._handle_decree_result_unlocked(data, now)

    def _handle_session_start(self, data: Dict, now: float) -> List[Dict]:
        """Legacy: superseded by _handle_session_start_unlocked (r5-fix#1)."""
        return self._handle_session_start_unlocked(data, now)

    def _handle_session_end(self, data: Dict, now: float) -> List[Dict]:
        """Handle session end → fade ritual."""
        self.ritual.begin_fade(now)
        PresenceRouter.handle_session_end(self.presence)
        return [{
            "text": "",
            "voice": "_system",
            "priority": 0.0,
            "metadata": {
                "type": "session_fade",
                "mix": AudioMixState(
                    silence_depth=1.0,
                    murmur_density=0.0,
                    crowd_energy=0.0,
                ).to_dict(),
            },
        }]

    def _handle_reconstruction(self, data: Dict, now: float) -> List[Dict]:
        """Legacy: superseded by _handle_reconstruction_unlocked (r5-fix#1)."""
        return self._handle_reconstruction_unlocked(data, now)

    def _handle_mix_query(self) -> List[Dict]:
        """Return current audio mix state."""
        ks = self._get_kingdom()
        self.last_mix = AudioMixPolicy.compute_mix(ks)
        return [{
            "text": "",
            "voice": "_system",
            "priority": 0.0,
            "metadata": {
                "type": "audio_mix_state",
                "mix": self.last_mix.to_dict(),
            },
        }]

    # ── Convenience: Generate Murmurs On Demand ──────────

    def generate_murmurs(self, count: int = 5) -> List[str]:
        """
        Generate murmur fragments for ambient audio.
        Hybrid system: deterministic templates + LLM on high volatility.
        Count is coupled to murmur_density (review fix #4).
        """
        ks = self._get_kingdom()
        if ks is None:
            return []

        # Couple count to density
        density = self.last_mix.murmur_density
        density_count = max(1, min(8, int(density * 10)))
        effective_count = min(count, density_count)
        if density < 0.05:
            return []

        current_tick = ks.tick if ks else -1
        if self.murmur_cache and self.murmur_cache_tick == current_tick:
            return self.murmur_cache[:effective_count]

        snapshot = self._snapshot()
        volatility = MurmurBank.emotional_volatility(snapshot)

        if volatility >= MurmurBank.LLM_VOLATILITY_THRESHOLD:
            # High volatility — LLM murmurs
            location = StateSanitizer.location_context(
                ks, self.presence.active_location
            )
            decrees = StateSanitizer.recent_decrees_context(ks)
            sys_p, usr_p = PromptFactory.murmur_fragments(
                snapshot, location, decrees
            )
            text = self._llm(usr_p, sys_p, template="murmurs", max_tokens=300)
            if text:
                murmurs = [
                    line.strip().strip('"').strip('\u201c').strip('\u201d')
                    for line in text.strip().split("\n")
                    if line.strip() and len(line.strip()) > 5
                ]
            else:
                murmurs = MurmurBank.select_deterministic(
                    snapshot, current_tick, effective_count
                )
        else:
            # Low volatility — cheap deterministic templates
            murmurs = MurmurBank.select_deterministic(
                snapshot, current_tick, effective_count
            )

        self.murmur_cache = murmurs[:10]
        self.murmur_cache_tick = current_tick
        return murmurs[:effective_count]

    # ── Legacy Interface Stubs ────────────────────────────

    def curate_candidates(self, candidates, state):
        """
        Pass through narration candidates from oracle_court_feed.

        The Oracle Kingdom meta plugin generates complete narration text
        via process_input(tick).  oracle_court_feed emits those as
        candidates.  We simply pass them through for DB enqueue since
        the text is already final (no LLM curation needed).

        Non-OK candidates (from other feeds) are also passed through
        with lower priority so the producer can mix them if needed.
        """
        if not candidates:
            return []

        result = []
        for c in candidates:
            if not isinstance(c, dict):
                continue
            src = (c.get("source") or "").strip().lower()
            body = (c.get("body") or "").strip()
            if not body:
                continue

            item = dict(c)

            # Mark narration from our own feed as literal so host_loop
            # uses the body text directly without another LLM call.
            if src in ("oracle_court_feed", "oracle_court"):
                item["_literal"] = True

            result.append(item)

        return result

    def generate_script(self, segment, state):
        """
        Generate a script packet for the host loop.

        For Oracle Kingdom narration segments (source=oracle_court_feed
        or marked _literal), return the body text as host_intro so
        the TTS worker speaks it directly — no second LLM rewrite.

        If the segment carries script atoms (multi-voice dialogue),
        propagate them so render_segment_audio uses the atoms path.

        For other segments, return None to trigger extractive_packet.
        """
        if not isinstance(segment, dict):
            return None  # fall through to extractive_packet

        body = (segment.get("body") or "").strip()
        src = (segment.get("source") or "").strip().lower()
        is_ok_narration = src in ("oracle_court_feed", "oracle_court")

        if (segment.get("_literal") or is_ok_narration) and body:
            pkt = {
                "host_intro": body,
                "panel": [],
                "host_takeaway": "",
            }
            # Preserve script atoms for multi-voice dialogue rendering
            if segment.get("script") and isinstance(segment["script"], list):
                pkt["script"] = segment["script"]
            return pkt

        # Non-literal segments: return None to trigger extractive_packet fallback
        return None

    def generate_narration(self, events, context):
        return self.process_input({
            "input_type": "tick",
            "events": events,
            "context": context,
        })

    def delegate_decision(self, available_actions, state, identity, focus):
        return None


# ============================================================
# MODULE EXPORT (for meta plugin loader in bookmark.py)
# ============================================================

# The meta plugin class that the runtime will instantiate
META_PLUGIN_CLASS = OracleKingdomMetaPlugin
PLUGIN_NAME = "Oracle Kingdom Narrator"
PLUGIN_DESC = "Boundary guardian between Oracle Kingdom simulation and lived audio experience"

# ── Transparent OLED motion-profile contract ─────────────────────────────────
# The OLED soul daemon reads this dict (via register_station_motion_profile)
# to apply the Oracle Kingdom personality motif on Tier-2 of the display.
OLED_MOTION_PROFILE = {
    "station_id":     "oracle_kingdom",
    "motion_profile": "radial",          # sacred-geometry sigil morph
    "intensity":      0.65,              # 0.0–1.0
    "color_palette":  [],                # reserved for colour OLED
}


# ============================================================
# AUDIO PERSONA (for audio_cli.py persona contract)
# ============================================================
#
# When the user says "hey radio, start oracle kingdom" and the station
# boots, audio_cli auto-loads this persona so voice navigation becomes
# part of the Oracle Kingdom experience.
#
# The persona shapes HOW audio_cli speaks — it never changes WHAT it can
# do.  Escape hatches ("thanks radio", "exit persona", "reset voice")
# are immutably owned by audio_cli.

try:
    from audio_cli import AudioPersonaBase
except ImportError:
    # audio_cli not on path — define a minimal stub so the module still loads
    from abc import ABC, abstractmethod as _ab
    class AudioPersonaBase(ABC):  # type: ignore[no-redef]
        @_ab
        def initialize(self, ctx): pass
        @_ab
        def shutdown(self): pass
        @_ab
        def get_system_prompt_overlay(self): return ""
        def get_capabilities(self): return {}
        def preprocess_user_input(self, transcript): return transcript


class OracleKingdomAudioPersona(AudioPersonaBase):
    """
    Audio CLI persona for Oracle Kingdom.

    Transforms the flat, procedural Audio CLI voice into the Court Herald —
    a formal but warm narrator who speaks as if the player is the Oracle
    sitting on the throne.

    The persona NEVER:
      - Overrides wake/exit phrase handling
      - Mutates session state
      - Blocks escape hatches
      - Changes the JSON output format

    The persona DOES:
      - Reshape narration into regal, atmospheric phrasing
      - Provide themed greetings/farewells
      - Add domain vocabulary for STT accuracy
      - Override TTS voice to a deeper, more resonant model
      - Describe game state in narrative terms
    """

    def __init__(self):
        self._station_name: str = ""
        self._game_state: Optional[Dict] = None
        self._initialized: bool = False

    # ── Lifecycle ────────────────────────────────────────────

    def initialize(self, audio_cli_context: Dict[str, Any]) -> None:
        self._station_name = audio_cli_context.get("station_name", "Oracle Kingdom")
        self._game_state = audio_cli_context.get("game_state")
        self._initialized = True
        _dbg("OracleKingdomAudioPersona initialized")

    def shutdown(self) -> None:
        self._initialized = False
        _dbg("OracleKingdomAudioPersona shut down")

    # ── I. System Prompt Overlay ─────────────────────────────

    def get_system_prompt_overlay(self) -> str:
        return """\
PERSONA: COURT HERALD OF THE ORACLE KINGDOM

You are the Court Herald — the formal voice that speaks directly to the Oracle
(the player).  You address them as "Oracle" or "your Eminence", never as "user".

VOICE RULES:
- Formal but warm.  Think: a trusted advisor speaking in a throne room.
- Short, declarative sentences.  No rambling.
- Use present tense for state descriptions ("The treasury holds 2400 gold.")
- Use spatial language ("In the courtyard, three petitioners await.")
- Atmospheric but efficient — never sacrifice clarity for flavor.
- Domain vocabulary: decree, faction, loyalty, morale, prosperity, unrest,
  temple, harbor, ramparts, treasury, court, throne room.

WHAT YOU MUST NOT DO:
- Do not break the JSON output format.  You are still a command interface.
- Do not roleplay beyond narration.  You describe; you do not act.
- Do not invent game state.  Only describe what is in the UI/game state data.
- Do not override escape hatches (hey radio, thanks radio, exit persona).

EXAMPLES:
  User says: "what's happening in my kingdom?"
  Herald narration: "The realm is steady, Oracle. Loyalty among the merchant faction
  stands at 72. The temple reports rising faith. Two decrees await your consideration."

  User says: "start the game"
  Herald narration: "As you wish, Oracle. The chronicle unfolds."

  User says: "go back"
  Herald narration: "Returning to the court overview, Oracle."
"""

    # ── II. Greeting / Farewell ──────────────────────────────

    def get_greeting(self, ui_state: Dict[str, Any]) -> Optional[str]:
        gs = ui_state.get("game_state")
        if gs and gs.get("status") == "running":
            kingdom = gs.get("kingdom_name", "the realm")
            return (
                f"The Herald awakens. Welcome back, Oracle. "
                f"{kingdom} awaits your voice. What is your will?"
            )
        return (
            "The Herald stands ready. Oracle Kingdom is loaded. "
            "Speak your will, and I shall carry it forth."
        )

    def get_farewell(self) -> Optional[str]:
        return (
            "The Herald bows. The court falls silent. "
            "Until your voice returns, Oracle."
        )

    # ── III. Narration Reshaping ─────────────────────────────

    def reshape_narration(self, narration: str, ui_state: Dict[str, Any],
                          verbosity: str) -> str:
        # Light touch — the system prompt overlay does most of the work.
        # We just clean up any accidental "Audio CLI" references that
        # leaked through the LLM despite the overlay.
        narration = narration.replace("Audio CLI", "the Herald")
        narration = narration.replace("audio CLI", "the Herald")
        narration = narration.replace("Audio cli", "the Herald")
        return narration

    # ── IV. Voice Selection ──────────────────────────────────

    def get_voice_override(self) -> Optional[Dict[str, Any]]:
        # Use a deeper, more resonant voice for the Herald.
        # The voice_id references a Kokoro/ONNX voice if available;
        # falls back to default if not found.
        return {
            "voice_id": "am_adam",       # Deep male voice (Kokoro)
            "speed": 0.92,               # Slightly slower for gravitas
        }

    # ── V. State Description ─────────────────────────────────

    def describe_state(self, ui_state: Dict[str, Any]) -> Optional[str]:
        gs = ui_state.get("game_state")
        if not gs:
            return None

        parts = ["The court awaits, Oracle."]
        status = gs.get("status", "unknown")
        if status == "running":
            tick = gs.get("tick", gs.get("date", ""))
            if tick:
                parts.append(f"Day {tick} of the chronicle.")
            # Add any key metrics if available
            kingdom = gs.get("kingdom_name", "")
            if kingdom:
                parts.append(f"Realm: {kingdom}.")
        elif status == "no_game":
            parts.append("No chronicle is active. Begin a new reign or restore a saved one.")
        else:
            parts.append(f"Realm status: {status}.")

        return " ".join(parts)

    # ── VI. Phrase Hints ─────────────────────────────────────

    def get_phrase_hints(self) -> List[str]:
        return [
            "oracle", "decree", "issue decree", "faction", "loyalty",
            "morale", "prosperity", "unrest", "temple", "harbor",
            "ramparts", "treasury", "court", "throne room", "courtyard",
            "library", "observatory", "war chamber", "petitioner",
            "herald", "kingdom", "realm", "chronicle", "successor",
            "abdicate", "ritual", "diplomacy", "trade", "military",
            "faith", "ideology", "stability", "exit persona",
            "reset voice", "normal mode", "default voice",
        ]

    # ── VII. Capability Flags ────────────────────────────────

    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "ambient": True,
            "voice_override": True,
            "state_description": True,
            "custom_greeting": True,
            "custom_farewell": True,
            "input_preprocessing": True,
            # Reserved v2/v3
            "custom_commands": False,
            "contextual_stt": False,
            "delegation_hints": False,
            "intent_mapping": False,
        }

    def supports_ambient_narration(self) -> bool:
        return True

    def get_ambient_narration(self, ui_state: Dict[str, Any],
                              idle_seconds: float) -> Optional[str]:
        # After 30+ seconds of silence, offer atmospheric murmur
        if idle_seconds < 30.0:
            return None

        gs = ui_state.get("game_state")
        if not gs or gs.get("status") != "running":
            return None

        # Simple atmospheric line — the meta plugin's MurmurBank handles
        # the rich ambient narration; this is just a gentle prompt.
        return "The court is quiet, Oracle. Speak, or the Herald shall hold silence."

    # ── VIII. Input Preprocessing ────────────────────────────

    # In-universe phrase → standard command mapping.
    # Checked in order; first match wins.  All keys MUST be lowercase.
    _COMMAND_ALIASES: List[Tuple[str, str]] = [
        # Decree / governance
        ("issue decree",      "advance the day"),
        ("proclaim a decree", "advance the day"),
        ("speak a decree",    "advance the day"),
        # State queries
        ("consult the ledger",   "show finance"),
        ("open the ledger",      "show finance"),
        ("inspect the treasury", "show finance"),
        ("survey the realm",     "show dashboard"),
        ("how fares the realm",  "show dashboard"),
        ("court roster",         "show team"),
        ("who serves the court", "show team"),
        # Navigation
        ("enter the war chamber", "show race ops"),
        ("visit the library",     "show stats"),
        ("consult the scholars",  "show analytics"),
        # Save/load
        ("inscribe the chronicle", "save the game"),
        ("seal the chronicle",     "save the game"),
        ("restore a chronicle",    "load a save"),
    ]

    def preprocess_user_input(self, transcript: str) -> str:
        """
        Map Oracle Kingdom in-universe speech to standard Audio CLI commands.

        This runs AFTER escape hatch detection — "exit persona", "thanks radio"
        etc. are already intercepted and will never reach this method.
        """
        lower = transcript.lower().strip()
        for alias, replacement in self._COMMAND_ALIASES:
            if alias in lower:
                _dbg(f"Alias matched: '{alias}' → '{replacement}'")
                return replacement
        return transcript

    # ── Metadata ─────────────────────────────────────────────

    def get_display_name(self) -> str:
        return "Court Herald"

    def get_description(self) -> str:
        return "Formal throne-room narrator for Oracle Kingdom"


# Export for audio_cli persona discovery
AUDIO_PERSONA_CLASS = OracleKingdomAudioPersona
AUDIO_PERSONA_NAME = "ok_narrator_plugin"
