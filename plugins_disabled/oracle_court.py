#!/usr/bin/env python3
"""
oracle_court.py — Persistent Social Memory & Spatial Presence Layer

Layer 1 of the Oracle Kingdom architecture:

    Layer 3 (World)   — oracle_kingdom.py  — Objective geopolitical simulation
    Layer 2 (Oracle)  — oracle_kingdom.py  — Interpretive modifier surface (OracleBuild, OraclePsychology)
    Layer 1 (Court)   — THIS FILE          — Social-emotional pressure field

Design invariants:
    1. Agents never directly modify world state variables.
    2. All pressure is mediated through decree options and framing.
    3. Silence is always valid and always has consequences.
    4. Memory decays but never fully deletes.
    5. Movement changes social exposure.
    6. The court reads world state; the world never reads court state
       except through the Oracle's decree choices.

Dependency: imports oracle_kingdom (ok).  oracle_kingdom never imports this file.

Phase 14 — Build 1: Data structures, memory mechanics, spatial model,
court-aware decree generation, inner narrator, court tick engine.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple

# ── Dependency: world layer ──────────────────────────────────
import oracle_kingdom as ok


# ============================================================
# SECTION 1: COURT LOCATIONS — Spatial Context System
# ============================================================
#
# The Oracle is embodied.  Location defines which agents are
# present, what faction pressures dominate, and how decrees
# are interpreted by the world layer.
#
# Each location acts as a multiplier lens:
#   Same words, different room → different world-layer weights.

class LocationId(Enum):
    """Fixed rooms in the palace complex."""
    COURTYARD    = auto()   # populist exposure, merchant petitions, high visibility
    WAR_CHAMBER  = auto()   # generals, military doctrine, hawkish framing
    TEMPLE       = auto()   # ideological tension, prophetic interpretation, moral framing
    HARBOR       = auto()   # trade metrics, external diplomacy, migration
    LIBRARY      = auto()   # scholars, reform, tech/knowledge bias
    OBSERVATORY  = auto()   # long-horizon stability, cosmic framing, patience
    TREASURY     = auto()   # wealth management, austerity/prosperity tension
    RAMPARTS     = auto()   # border awareness, threat perception, siege mentality
    THRONE_ROOM  = auto()   # formal audience, balanced exposure, legitimacy center


# ── Location metadata ────────────────────────────────────────

@dataclass
class LocationProfile:
    """
    Static profile for a palace location.

    decree_multipliers: when a decree is issued here, these policy axes
        get scaled before reaching the world layer.  A multiplier of
        1.5 on 'military_focus' in the WAR_CHAMBER means military
        decrees spoken there have 50% more world-layer impact.

    faction_density: which faction archetypes are naturally concentrated
        here (affects which agents are 'present' and which proposals surface).

    emotional_texture: baseline mood modifier applied to agents while
        the Oracle is present in this room.

    legitimacy_bias: being seen here shifts legitimacy perception.
        Positive = increases perceived legitimacy, negative = informal.

    visibility: how public actions taken here are.
        High visibility (courtyard) means more agents observe.
        Low visibility (observatory) means fewer witnesses.
    """
    location_id: LocationId = LocationId.THRONE_ROOM
    name: str = ""
    description: str = ""

    # Policy axis multipliers (default 1.0 = no change)
    decree_multipliers: Dict[str, float] = field(default_factory=dict)

    # Which faction archetypes are concentrated here (weight 0–1)
    faction_density: Dict[str, float] = field(default_factory=dict)

    # Emotional texture: keys are agent disposition axes, values are per-tick drift
    emotional_texture: Dict[str, float] = field(default_factory=dict)

    # Legitimacy and visibility
    legitimacy_bias: float = 0.0
    visibility: float = 0.5     # 0.0 = private, 1.0 = fully public

    def to_dict(self) -> dict:
        return {
            "location_id": self.location_id.name,
            "name": self.name,
            "description": self.description,
            "decree_multipliers": dict(self.decree_multipliers),
            "faction_density": dict(self.faction_density),
            "emotional_texture": dict(self.emotional_texture),
            "legitimacy_bias": self.legitimacy_bias,
            "visibility": self.visibility,
        }


# ── Location definitions ─────────────────────────────────────

LOCATION_PROFILES: Dict[LocationId, LocationProfile] = {
    LocationId.COURTYARD: LocationProfile(
        location_id=LocationId.COURTYARD,
        name="The Courtyard",
        description="Open air, public gaze. Merchants call, dissidents murmur, pilgrims gather.",
        decree_multipliers={
            "agriculture_focus": 1.3, "mercy_focus": 1.4, "trade_focus": 1.2,
            "military_focus": 0.7, "faith_focus": 0.9,
        },
        faction_density={
            "POPULIST": 0.9, "MERCHANT": 0.7, "RELIGIOUS": 0.4,
            "MILITARY": 0.2, "SCHOLARLY": 0.2,
        },
        emotional_texture={"trust": 0.02, "fear": -0.01, "resentment": -0.01},
        legitimacy_bias=0.1,
        visibility=1.0,
    ),
    LocationId.WAR_CHAMBER: LocationProfile(
        location_id=LocationId.WAR_CHAMBER,
        name="The War Chamber",
        description="Maps and steel. Generals speak in certainties. Hesitation is weakness.",
        decree_multipliers={
            "military_focus": 1.5, "justice_focus": 1.3, "expansion_focus": 1.4,
            "mercy_focus": 0.5, "reform_focus": 0.6,
        },
        faction_density={
            "MILITARY": 0.9, "POPULIST": 0.1, "MERCHANT": 0.2,
            "RELIGIOUS": 0.3, "SCHOLARLY": 0.3,
        },
        emotional_texture={"fear": 0.02, "admiration": 0.01, "trust": -0.01},
        legitimacy_bias=0.05,
        visibility=0.3,
    ),
    LocationId.TEMPLE: LocationProfile(
        location_id=LocationId.TEMPLE,
        name="The Temple",
        description="Incense and whispered prayers. Faith is tested. Prophecy is contested.",
        decree_multipliers={
            "faith_focus": 1.6, "mercy_focus": 1.2, "reform_focus": 0.8,
            "military_focus": 0.6, "trade_focus": 0.7,
        },
        faction_density={
            "RELIGIOUS": 0.9, "POPULIST": 0.5, "SCHOLARLY": 0.4,
            "MILITARY": 0.1, "MERCHANT": 0.2,
        },
        emotional_texture={"admiration": 0.02, "fear": 0.01, "resentment": -0.01},
        legitimacy_bias=0.15,
        visibility=0.6,
    ),
    LocationId.HARBOR: LocationProfile(
        location_id=LocationId.HARBOR,
        name="The Harbor",
        description="Salt air and foreign tongues. Wealth arrives and departs on the tide.",
        decree_multipliers={
            "trade_focus": 1.5, "expansion_focus": 1.4, "isolation_focus": 0.5,
            "agriculture_focus": 0.8, "faith_focus": 0.6,
        },
        faction_density={
            "MERCHANT": 0.9, "POPULIST": 0.4, "MILITARY": 0.3,
            "SCHOLARLY": 0.3, "RELIGIOUS": 0.1,
        },
        emotional_texture={"trust": 0.01, "admiration": 0.01, "resentment": 0.01},
        legitimacy_bias=-0.05,
        visibility=0.5,
    ),
    LocationId.LIBRARY: LocationProfile(
        location_id=LocationId.LIBRARY,
        name="The Library",
        description="Dusty silence, sharp minds. Knowledge challenges tradition.",
        decree_multipliers={
            "reform_focus": 1.5, "trade_focus": 1.1, "faith_focus": 0.7,
            "military_focus": 0.7, "austerity_focus": 1.2,
        },
        faction_density={
            "SCHOLARLY": 0.9, "RELIGIOUS": 0.4, "MERCHANT": 0.3,
            "POPULIST": 0.1, "MILITARY": 0.1,
        },
        emotional_texture={"trust": 0.02, "admiration": 0.02, "fear": -0.02},
        legitimacy_bias=0.0,
        visibility=0.2,
    ),
    LocationId.OBSERVATORY: LocationProfile(
        location_id=LocationId.OBSERVATORY,
        name="The Observatory",
        description="Stars and long silences. Time is measured in epochs, not days.",
        decree_multipliers={
            "faith_focus": 1.2, "reform_focus": 1.1, "austerity_focus": 1.1,
            "military_focus": 0.8, "expansion_focus": 0.9,
        },
        faction_density={
            "SCHOLARLY": 0.6, "RELIGIOUS": 0.5, "POPULIST": 0.1,
            "MERCHANT": 0.1, "MILITARY": 0.1,
        },
        emotional_texture={"admiration": 0.03, "fear": -0.02, "trust": 0.01},
        legitimacy_bias=0.1,
        visibility=0.1,
    ),
    LocationId.TREASURY: LocationProfile(
        location_id=LocationId.TREASURY,
        name="The Treasury",
        description="Coins counted, ledgers balanced. Prosperity is arithmetic here.",
        decree_multipliers={
            "trade_focus": 1.3, "austerity_focus": 1.4, "agriculture_focus": 1.1,
            "faith_focus": 0.5, "mercy_focus": 0.7,
        },
        faction_density={
            "MERCHANT": 0.8, "SCHOLARLY": 0.3, "MILITARY": 0.3,
            "POPULIST": 0.2, "RELIGIOUS": 0.1,
        },
        emotional_texture={"trust": 0.01, "resentment": 0.01, "admiration": -0.01},
        legitimacy_bias=0.0,
        visibility=0.2,
    ),
    LocationId.RAMPARTS: LocationProfile(
        location_id=LocationId.RAMPARTS,
        name="The Ramparts",
        description="Wind and watchfires. The world beyond is visible and threatening.",
        decree_multipliers={
            "military_focus": 1.4, "isolation_focus": 1.3, "expansion_focus": 1.2,
            "mercy_focus": 0.6, "reform_focus": 0.7,
        },
        faction_density={
            "MILITARY": 0.8, "POPULIST": 0.3, "RELIGIOUS": 0.2,
            "MERCHANT": 0.1, "SCHOLARLY": 0.1,
        },
        emotional_texture={"fear": 0.02, "admiration": 0.01, "trust": -0.01},
        legitimacy_bias=0.05,
        visibility=0.4,
    ),
    LocationId.THRONE_ROOM: LocationProfile(
        location_id=LocationId.THRONE_ROOM,
        name="The Throne Room",
        description="Formal silence. All factions attend. Every word is weighed.",
        decree_multipliers={
            "justice_focus": 1.2, "faith_focus": 1.1, "military_focus": 1.1,
            "trade_focus": 1.0, "reform_focus": 1.0,
        },
        faction_density={
            "RELIGIOUS": 0.6, "MERCHANT": 0.6, "MILITARY": 0.6,
            "SCHOLARLY": 0.6, "POPULIST": 0.4,
        },
        emotional_texture={"admiration": 0.01, "fear": 0.01},
        legitimacy_bias=0.2,
        visibility=0.8,
    ),
}


# ============================================================
# SECTION 2: AGENT MODEL — Persistent Social Memory
# ============================================================
#
# Each court agent wraps a Character from oracle_kingdom and adds
# a relational state toward the Oracle plus a structured memory log.
#
# Agents do NOT directly modify world variables.
# They influence:
#   - What proposals surface
#   - How they are framed
#   - What emotional pressure accompanies them
#   - How risky silence becomes

class MemoryType(Enum):
    """Three tiers of memory persistence."""
    IMMEDIATE    = auto()   # short-term emotional spike, decays fast
    REPUTATIONAL = auto()   # medium-term trust/fear shifts
    NARRATIVE    = auto()   # long-term identity of the Oracle in this agent's mind


@dataclass
class MemoryEntry:
    """
    One event in an agent's memory of the Oracle.

    Memory entries decay slowly but never fully disappear.
    Long-term patterns emerge from accumulated entries.
    """
    tick: int = 0
    memory_type: MemoryType = MemoryType.IMMEDIATE
    category: str = ""          # e.g. "decree_supported", "petition_ignored", "rewarded"
    description: str = ""       # short human-readable label
    intensity: float = 1.0      # initial emotional weight (positive or negative)
    current_weight: float = 1.0 # decayed weight (never reaches exactly 0)
    decree_id: str = ""         # linked decree, if any
    location: str = ""          # where it happened

    # Decay parameters
    half_life_ticks: int = 100  # IMMEDIATE=50, REPUTATIONAL=300, NARRATIVE=2000

    def decay(self, current_tick: int):
        """Apply time-based decay. Weight approaches 0.01 asymptotically."""
        age = max(0, current_tick - self.tick)
        if age <= 0:
            self.current_weight = self.intensity
            return
        # Exponential decay with a floor of 1% of original intensity
        decay_factor = math.exp(-0.693 * age / max(1, self.half_life_ticks))
        floor = abs(self.intensity) * 0.01
        self.current_weight = self.intensity * decay_factor
        # Preserve sign, enforce floor on magnitude
        if abs(self.current_weight) < floor:
            self.current_weight = math.copysign(floor, self.intensity)

    def to_dict(self) -> dict:
        return {
            "tick": self.tick,
            "memory_type": self.memory_type.name,
            "category": self.category,
            "description": self.description,
            "intensity": self.intensity,
            "current_weight": self.current_weight,
            "decree_id": self.decree_id,
            "location": self.location,
            "half_life_ticks": self.half_life_ticks,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryEntry":
        m = cls()
        m.tick = d.get("tick", 0)
        m.memory_type = MemoryType[d.get("memory_type", "IMMEDIATE")]
        m.category = d.get("category", "")
        m.description = d.get("description", "")
        m.intensity = d.get("intensity", 1.0)
        m.current_weight = d.get("current_weight", 1.0)
        m.decree_id = d.get("decree_id", "")
        m.location = d.get("location", "")
        m.half_life_ticks = d.get("half_life_ticks", 100)
        return m


# ── Memory half-life defaults by type ────────────────────────

MEMORY_HALF_LIVES = {
    MemoryType.IMMEDIATE: 50,       # fades in ~200 ticks
    MemoryType.REPUTATIONAL: 300,   # fades in ~1200 ticks
    MemoryType.NARRATIVE: 2000,     # effectively permanent
}


@dataclass
class CourtAgent:
    """
    A persistent court entity with social memory.

    Wraps a Character reference (by character_id) and adds the
    relational state and memory spine that the design doc specifies.
    """
    character_id: str = ""          # FK into KingdomState.characters
    agent_id: str = ""              # unique agent identifier

    # ── Relational State Toward Oracle ──
    trust: float = 50.0             # 0–100: belief Oracle acts in good faith
    fear: float = 20.0              # 0–100: intimidation / compliance pressure
    admiration: float = 40.0        # 0–100: respect for Oracle's wisdom
    resentment: float = 10.0        # 0–100: accumulated grievance
    ideological_alignment: float = 0.0   # -50 to +50: policy agreement
    perceived_consistency: float = 50.0  # 0–100: does Oracle follow through?
    perceived_decisiveness: float = 50.0 # 0–100: does Oracle act promptly?

    # ── Memory Log (Event Spine) ──
    memories: List[MemoryEntry] = field(default_factory=list)

    # ── Aggregate narrative identity of Oracle (derived) ──
    narrative_tone: str = "neutral"  # derived from memory patterns
    oracle_label: str = ""           # "The Silent Oracle", "The Merchant's Oracle", etc.

    # ── Interaction tracking ──
    last_interaction_tick: int = 0
    total_interactions: int = 0
    petitions_submitted: int = 0
    petitions_ignored: int = 0
    times_rewarded: int = 0
    times_punished: int = 0

    # ── Home location (where this agent defaults to) ──
    home_location: str = "THRONE_ROOM"

    # ── Agenda weight: what this agent currently wants most ──
    # Mirrors faction agenda but may diverge based on personal memory
    personal_agenda: str = "stability"  # stability, power, reform, wealth, piety, vengeance
    agenda_intensity: float = 0.5       # 0–1: how urgently they push their agenda

    def net_disposition(self) -> float:
        """
        Single-number summary of agent's overall stance toward Oracle.
        Positive = favorable, negative = hostile.
        Range roughly -100 to +100.
        """
        return (
            self.trust * 0.3
            + self.admiration * 0.25
            - self.resentment * 0.3
            - self.fear * 0.05         # fear is compliance, not affection
            + self.perceived_consistency * 0.1
        ) - 30.0  # center around 0

    def add_memory(self, tick: int, memory_type: MemoryType, category: str,
                   description: str, intensity: float, decree_id: str = "",
                   location: str = ""):
        """Record a new memory entry."""
        entry = MemoryEntry(
            tick=tick,
            memory_type=memory_type,
            category=category,
            description=description,
            intensity=intensity,
            current_weight=intensity,
            decree_id=decree_id,
            location=location,
            half_life_ticks=MEMORY_HALF_LIVES[memory_type],
        )
        self.memories.append(entry)
        self.total_interactions += 1
        self.last_interaction_tick = tick

    def decay_memories(self, current_tick: int):
        """Decay all memory weights. Never prune — memories persist forever."""
        for m in self.memories:
            m.decay(current_tick)

    def memory_sum(self, category: str = "", memory_type: Optional[MemoryType] = None) -> float:
        """Sum of current_weight for memories matching filters."""
        total = 0.0
        for m in self.memories:
            if category and m.category != category:
                continue
            if memory_type is not None and m.memory_type != memory_type:
                continue
            total += m.current_weight
        return total

    def recent_memories(self, n: int = 5) -> List[MemoryEntry]:
        """Last n memories (most recent first)."""
        return sorted(self.memories, key=lambda m: m.tick, reverse=True)[:n]

    def to_dict(self) -> dict:
        return {
            "character_id": self.character_id,
            "agent_id": self.agent_id,
            "trust": self.trust,
            "fear": self.fear,
            "admiration": self.admiration,
            "resentment": self.resentment,
            "ideological_alignment": self.ideological_alignment,
            "perceived_consistency": self.perceived_consistency,
            "perceived_decisiveness": self.perceived_decisiveness,
            "memories": [m.to_dict() for m in self.memories],
            "narrative_tone": self.narrative_tone,
            "oracle_label": self.oracle_label,
            "last_interaction_tick": self.last_interaction_tick,
            "total_interactions": self.total_interactions,
            "petitions_submitted": self.petitions_submitted,
            "petitions_ignored": self.petitions_ignored,
            "times_rewarded": self.times_rewarded,
            "times_punished": self.times_punished,
            "home_location": self.home_location,
            "personal_agenda": self.personal_agenda,
            "agenda_intensity": self.agenda_intensity,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CourtAgent":
        a = cls()
        for k, v in d.items():
            if k == "memories":
                a.memories = [MemoryEntry.from_dict(m) for m in v]
            elif hasattr(a, k):
                setattr(a, k, v)
        return a


# ── Faction Memory ────────────────────────────────────────────
# Persists beyond individual agents.
# "The Merchant Guild remembers the Tariff Year."

@dataclass
class FactionMemory:
    """
    Collective memory of a faction's relationship with the Oracle.

    When agents die or are exiled, their strongest NARRATIVE memories
    are absorbed into faction memory.  New agents inherit this.
    """
    faction_id: str = ""
    memories: List[MemoryEntry] = field(default_factory=list)

    # Aggregate disposition derived from collective memory
    collective_trust: float = 50.0
    collective_resentment: float = 10.0
    collective_label: str = ""      # "remembers the Tariff Year", etc.

    def absorb_agent_memories(self, agent: CourtAgent, current_tick: int):
        """When an agent departs, absorb their strongest narrative memories."""
        narrative = [m for m in agent.memories if m.memory_type == MemoryType.NARRATIVE]
        # Keep top 3 by absolute current_weight
        strongest = sorted(narrative, key=lambda m: abs(m.current_weight), reverse=True)[:3]
        for m in strongest:
            # Re-tag as faction memory with reduced intensity
            faction_mem = MemoryEntry(
                tick=m.tick,
                memory_type=MemoryType.NARRATIVE,
                category=f"faction_inherited:{m.category}",
                description=f"[Inherited] {m.description}",
                intensity=m.current_weight * 0.6,
                current_weight=m.current_weight * 0.6,
                decree_id=m.decree_id,
                location=m.location,
                half_life_ticks=5000,  # faction memories are very persistent
            )
            self.memories.append(faction_mem)

    def decay_memories(self, current_tick: int):
        for m in self.memories:
            m.decay(current_tick)

    def update_aggregates(self):
        """Recompute aggregate disposition from memories."""
        if not self.memories:
            return
        positive = sum(m.current_weight for m in self.memories if m.current_weight > 0)
        negative = sum(m.current_weight for m in self.memories if m.current_weight < 0)
        total = abs(positive) + abs(negative)
        if total > 0:
            self.collective_trust = 50.0 + (positive + negative) / total * 30.0
            self.collective_resentment = max(0.0, -negative / max(1, total) * 60.0)

    def to_dict(self) -> dict:
        return {
            "faction_id": self.faction_id,
            "memories": [m.to_dict() for m in self.memories],
            "collective_trust": self.collective_trust,
            "collective_resentment": self.collective_resentment,
            "collective_label": self.collective_label,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FactionMemory":
        fm = cls()
        fm.faction_id = d.get("faction_id", "")
        fm.memories = [MemoryEntry.from_dict(m) for m in d.get("memories", [])]
        fm.collective_trust = d.get("collective_trust", 50.0)
        fm.collective_resentment = d.get("collective_resentment", 10.0)
        fm.collective_label = d.get("collective_label", "")
        return fm


# ============================================================
# SECTION 3: PRESENCE REQUESTS & ENVIRONMENTAL SIGNALS (CTAs)
# ============================================================
#
# There must be reasons to move.
# Movement is driven by Presence Requests and Environmental Signals.
# These are the "calls to action" that pull the Oracle between rooms.

class CTAUrgency(Enum):
    """How urgently the Oracle's presence is needed."""
    LOW       = auto()   # can be ignored for a while
    MODERATE  = auto()   # should attend within ~20 ticks
    HIGH      = auto()   # ignoring has visible consequences
    CRITICAL  = auto()   # faction crisis or personal narrative climax


@dataclass
class PresenceRequest:
    """
    A call to action from an agent or faction.

    "Your presence is requested in the war room."
    "The High Priest refuses to begin without you."
    "The Guild threatens to withdraw trade unless heard."
    """
    request_id: str = ""
    tick_created: int = 0
    source_agent_id: str = ""       # which agent is requesting
    source_faction_id: str = ""     # or which faction
    target_location: str = ""       # LocationId.name
    urgency: CTAUrgency = CTAUrgency.MODERATE

    description: str = ""           # narrative text shown to player
    reason: str = ""                # internal: why was this generated?

    # What happens if ignored
    ignore_trust_cost: float = -2.0     # trust change per 10 ticks ignored
    ignore_resentment_gain: float = 1.0
    ignore_legitimacy_cost: float = -0.5

    # Lifecycle
    ticks_alive: int = 0
    max_lifetime: int = 80              # expires after this many ticks
    attended: bool = False
    expired: bool = False
    dismissed: bool = False             # player explicitly dismissed it

    @property
    def is_active(self) -> bool:
        return not self.attended and not self.expired and not self.dismissed

    def tick(self):
        """Age this request by one tick."""
        self.ticks_alive += 1
        if self.ticks_alive >= self.max_lifetime:
            self.expired = True

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "tick_created": self.tick_created,
            "source_agent_id": self.source_agent_id,
            "source_faction_id": self.source_faction_id,
            "target_location": self.target_location,
            "urgency": self.urgency.name,
            "description": self.description,
            "reason": self.reason,
            "ignore_trust_cost": self.ignore_trust_cost,
            "ignore_resentment_gain": self.ignore_resentment_gain,
            "ignore_legitimacy_cost": self.ignore_legitimacy_cost,
            "ticks_alive": self.ticks_alive,
            "max_lifetime": self.max_lifetime,
            "attended": self.attended,
            "expired": self.expired,
            "dismissed": self.dismissed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PresenceRequest":
        p = cls()
        for k, v in d.items():
            if k == "urgency":
                p.urgency = CTAUrgency[v]
            elif hasattr(p, k):
                setattr(p, k, v)
        return p


@dataclass
class EnvironmentalSignal:
    """
    A micro-narrative opportunity that demands attention.

    Not a direct world-layer shock — what you say when you arrive
    is what matters.

    "Noise in the courtyard."
    "A debate escalating in the temple."
    "Silence in the observatory for too long."
    """
    signal_id: str = ""
    tick_created: int = 0
    location: str = ""              # where this is happening
    description: str = ""
    severity: float = 0.5           # 0–1: how attention-grabbing

    # If the Oracle is already at this location, they witness it automatically
    auto_witness: bool = True

    ticks_alive: int = 0
    max_lifetime: int = 40
    witnessed: bool = False
    expired: bool = False

    @property
    def is_active(self) -> bool:
        return not self.witnessed and not self.expired

    def tick(self):
        self.ticks_alive += 1
        if self.ticks_alive >= self.max_lifetime:
            self.expired = True

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "tick_created": self.tick_created,
            "location": self.location,
            "description": self.description,
            "severity": self.severity,
            "auto_witness": self.auto_witness,
            "ticks_alive": self.ticks_alive,
            "max_lifetime": self.max_lifetime,
            "witnessed": self.witnessed,
            "expired": self.expired,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EnvironmentalSignal":
        s = cls()
        for k, v in d.items():
            if hasattr(s, k):
                setattr(s, k, v)
        return s


# ============================================================
# SECTION 4: UTTERANCE SYSTEM
# ============================================================
#
# Every interaction produces an utterance event.
# Silence is always valid.  Silence accumulates meaning over time.

class UtteranceType(Enum):
    """The Oracle's modes of expression."""
    SPEAK_BOLDLY = auto()    # high magnitude, high visibility
    SPEAK_SOFTLY = auto()    # low magnitude, intimate
    ISSUE_DECREE = auto()    # formal decree (routes through PropagationEngine)
    ASK_QUESTION = auto()    # gathers information, shows humility/curiosity
    DEFLECT      = auto()    # avoids commitment
    REMAIN_SILENT = auto()   # silence is never neutral


# ── Utterance effects on oracle inner state ──────────────────

UTTERANCE_ORACLE_EFFECTS: Dict[str, Dict[str, float]] = {
    "SPEAK_BOLDLY":  {"ego": 0.5, "stress": -0.3, "hope": 0.2, "dread": -0.1},
    "SPEAK_SOFTLY":  {"ego": -0.1, "stress": -0.2, "hope": 0.3, "dread": -0.2},
    "ISSUE_DECREE":  {"ego": 0.3, "stress": 0.2, "hope": 0.0, "dread": -0.1},
    "ASK_QUESTION":  {"ego": -0.3, "stress": -0.1, "hope": 0.1, "dread": -0.1},
    "DEFLECT":       {"ego": -0.2, "stress": 0.3, "hope": -0.1, "dread": 0.3},
    "REMAIN_SILENT": {"ego": 0.0, "stress": 0.1, "hope": -0.1, "dread": 0.2},
}


# ============================================================
# SECTION 5: ORACLE IDENTITY PROFILE
# ============================================================
#
# Over time, a composite profile emerges from decree patterns,
# silence frequency, faction favoritism, and volatility outcomes.

class OracleArchetype(Enum):
    """Emergent Oracle identities — not chosen, but recognized."""
    UNKNOWN       = auto()   # too early to tell
    THE_SILENT    = auto()   # silence > 60% of opportunities
    THE_HAWK      = auto()   # military/justice dominant
    THE_MERCHANT  = auto()   # trade/prosperity dominant
    THE_REFORMIST = auto()   # reform/scholarly dominant
    THE_PIOUS     = auto()   # faith/temple dominant
    THE_POPULIST  = auto()   # mercy/agriculture dominant
    THE_TYRANT    = auto()   # fear > trust across agents
    THE_ERRATIC   = auto()   # high variance, no consistent pattern


@dataclass
class OracleIdentityProfile:
    """
    Derived from accumulated Oracle behavior.
    Agents respond to this perceived identity.
    """
    archetype: OracleArchetype = OracleArchetype.UNKNOWN

    # Raw signal accumulators
    decree_count: int = 0
    silence_count: int = 0
    total_opportunities: int = 0

    # Policy axis usage totals (from all decrees)
    axis_usage: Dict[str, float] = field(default_factory=dict)

    # Faction favoritism (which factions benefited most)
    faction_favor: Dict[str, float] = field(default_factory=dict)

    # Consistency score: how often recent decrees align with past ones
    consistency: float = 0.5

    # Volatility: standard deviation of decree policy vectors
    volatility: float = 0.0

    def update_from_decree(self, decree: ok.DecreeRecord):
        """Accumulate a new decree into the profile."""
        self.decree_count += 1
        self.total_opportunities += 1
        for axis, value in decree.policy_vector.items():
            self.axis_usage[axis] = self.axis_usage.get(axis, 0.0) + abs(value)

    def record_silence(self):
        """Record a missed decree opportunity (silence chosen)."""
        self.silence_count += 1
        self.total_opportunities += 1

    def classify(self) -> OracleArchetype:
        """Derive the current archetype from accumulated signals."""
        if self.total_opportunities < 10:
            self.archetype = OracleArchetype.UNKNOWN
            return self.archetype

        silence_ratio = self.silence_count / max(1, self.total_opportunities)
        if silence_ratio > 0.6:
            self.archetype = OracleArchetype.THE_SILENT
            return self.archetype

        if self.volatility > 2.0:
            self.archetype = OracleArchetype.THE_ERRATIC
            return self.archetype

        # Find dominant policy axis
        if not self.axis_usage:
            self.archetype = OracleArchetype.UNKNOWN
            return self.archetype

        dominant = max(self.axis_usage, key=self.axis_usage.get)
        total_usage = sum(self.axis_usage.values())
        dominance = self.axis_usage[dominant] / max(1.0, total_usage)

        if dominance < 0.2:
            # No clear pattern
            self.archetype = OracleArchetype.THE_ERRATIC
        elif dominant in ("military_focus", "justice_focus"):
            self.archetype = OracleArchetype.THE_HAWK
        elif dominant in ("trade_focus", "austerity_focus", "expansion_focus"):
            self.archetype = OracleArchetype.THE_MERCHANT
        elif dominant in ("reform_focus",):
            self.archetype = OracleArchetype.THE_REFORMIST
        elif dominant in ("faith_focus",):
            self.archetype = OracleArchetype.THE_PIOUS
        elif dominant in ("agriculture_focus", "mercy_focus"):
            self.archetype = OracleArchetype.THE_POPULIST
        else:
            self.archetype = OracleArchetype.UNKNOWN

        return self.archetype

    def to_dict(self) -> dict:
        return {
            "archetype": self.archetype.name,
            "decree_count": self.decree_count,
            "silence_count": self.silence_count,
            "total_opportunities": self.total_opportunities,
            "axis_usage": dict(self.axis_usage),
            "faction_favor": dict(self.faction_favor),
            "consistency": self.consistency,
            "volatility": self.volatility,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OracleIdentityProfile":
        p = cls()
        p.archetype = OracleArchetype[d.get("archetype", "UNKNOWN")]
        p.decree_count = d.get("decree_count", 0)
        p.silence_count = d.get("silence_count", 0)
        p.total_opportunities = d.get("total_opportunities", 0)
        p.axis_usage = d.get("axis_usage", {})
        p.faction_favor = d.get("faction_favor", {})
        p.consistency = d.get("consistency", 0.5)
        p.volatility = d.get("volatility", 0.0)
        return p


# ============================================================
# SECTION 6: ORACLE INNER STATE — Consciousness Layer
# ============================================================
#
# The internal cognitive stream of the Player Oracle.
# Interprets events through the oracle's trait vector.
# Creates narrative continuity between decrees and consequences.
#
# This is the subjective lens over the abstract simulation.

class InnerThoughtType(Enum):
    """Categories of inner monologue."""
    CALCULATIVE       = auto()   # strategic clarity
    DOUBT_SPIRAL      = auto()   # self-questioning
    DESTINY_SURGE     = auto()   # grand vision
    MORAL_RECKONING   = auto()   # empathy-driven
    COLD_DETACHMENT   = auto()   # severity dominant
    SILENCE_PRESSURE  = auto()   # nothing spoken but heavy presence
    PARANOID_WHISPER  = auto()   # suspicion of advisors
    NOSTALGIC_RECALL  = auto()   # remembering past choices


@dataclass
class InnerThought:
    """A single triggered inner monologue fragment."""
    tick: int = 0
    thought_type: InnerThoughtType = InnerThoughtType.CALCULATIVE
    text: str = ""                  # 1–3 sentence fragment
    trigger: str = ""               # what caused this thought
    dominant_trait: str = ""        # which oracle trait drove the framing
    tension_level: float = 0.0     # inner tension at time of thought

    def to_dict(self) -> dict:
        return {
            "tick": self.tick,
            "thought_type": self.thought_type.name,
            "text": self.text,
            "trigger": self.trigger,
            "dominant_trait": self.dominant_trait,
            "tension_level": self.tension_level,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "InnerThought":
        t = cls()
        t.tick = d.get("tick", 0)
        t.thought_type = InnerThoughtType[d.get("thought_type", "CALCULATIVE")]
        t.text = d.get("text", "")
        t.trigger = d.get("trigger", "")
        t.dominant_trait = d.get("dominant_trait", "")
        t.tension_level = d.get("tension_level", 0.0)
        return t


@dataclass
class OracleInnerState:
    """
    The Oracle's inner consciousness — Layer 2.5 between court and world.

    Tracks:
      - Location history
      - Advisor interaction memory
      - Suppressed thought pressure
      - Existential / legacy anxiety
    """
    last_location: str = "THRONE_ROOM"
    location_history: List[str] = field(default_factory=list)  # last 20 locations visited
    ticks_at_current_location: int = 0

    # ── Pressure accumulators ──
    suppressed_thoughts: float = 0.0     # builds when thoughts fire but Oracle doesn't act
    existential_pressure: float = 0.0    # grows with prestige delta, era transitions
    legacy_anxiety: float = 0.0          # grows over time, especially after crises

    # ── Interaction recency ──
    recent_advisor_ids: List[str] = field(default_factory=list)  # last 5 agents spoken to
    recent_conflict_ids: List[str] = field(default_factory=list) # last 5 conflict events

    # ── Inner thought log ──
    thought_log: List[InnerThought] = field(default_factory=list)

    # ── Silence tracking ──
    consecutive_silence_ticks: int = 0
    total_silence_ticks: int = 0

    def record_location(self, location: str, tick: int):
        """Record moving to a new location."""
        if location != self.last_location:
            self.location_history.append(self.last_location)
            if len(self.location_history) > 20:
                self.location_history = self.location_history[-20:]
            self.last_location = location
            self.ticks_at_current_location = 0
        else:
            self.ticks_at_current_location += 1

    def record_thought(self, thought: InnerThought):
        self.thought_log.append(thought)
        # Keep last 200 thoughts (ring buffer for long sessions).
        # Thoughts are narrative artifacts — more is better for
        # chronicle generation.  The old cap of 50 made every run
        # hit the same ceiling regardless of tension dynamics.
        if len(self.thought_log) > 200:
            self.thought_log = self.thought_log[-200:]

    def to_dict(self) -> dict:
        return {
            "last_location": self.last_location,
            "location_history": list(self.location_history),
            "ticks_at_current_location": self.ticks_at_current_location,
            "suppressed_thoughts": self.suppressed_thoughts,
            "existential_pressure": self.existential_pressure,
            "legacy_anxiety": self.legacy_anxiety,
            "recent_advisor_ids": list(self.recent_advisor_ids),
            "recent_conflict_ids": list(self.recent_conflict_ids),
            "thought_log": [t.to_dict() for t in self.thought_log],
            "consecutive_silence_ticks": self.consecutive_silence_ticks,
            "total_silence_ticks": self.total_silence_ticks,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OracleInnerState":
        s = cls()
        s.last_location = d.get("last_location", "THRONE_ROOM")
        s.location_history = d.get("location_history", [])
        s.ticks_at_current_location = d.get("ticks_at_current_location", 0)
        s.suppressed_thoughts = d.get("suppressed_thoughts", 0.0)
        s.existential_pressure = d.get("existential_pressure", 0.0)
        s.legacy_anxiety = d.get("legacy_anxiety", 0.0)
        s.recent_advisor_ids = d.get("recent_advisor_ids", [])
        s.recent_conflict_ids = d.get("recent_conflict_ids", [])
        s.thought_log = [InnerThought.from_dict(t) for t in d.get("thought_log", [])]
        s.consecutive_silence_ticks = d.get("consecutive_silence_ticks", 0)
        s.total_silence_ticks = d.get("total_silence_ticks", 0)
        return s


# ============================================================
# SECTION 7: COURT STATE — Master Container
# ============================================================
#
# Everything the court layer tracks, in one serializable container.
# This is attached to a KingdomState but lives in this module.

@dataclass
class CourtState:
    """
    Complete court layer state for one kingdom.

    Attached to the player's KingdomState.  Serialized alongside
    the world state for save/load.
    """
    # ── Agents ──
    agents: Dict[str, CourtAgent] = field(default_factory=dict)  # agent_id → CourtAgent

    # ── Faction memories ──
    faction_memories: Dict[str, FactionMemory] = field(default_factory=dict)

    # ── Oracle presence ──
    current_location: LocationId = LocationId.THRONE_ROOM
    ticks_at_location: int = 0

    # ── Oracle identity (emergent) ──
    oracle_identity: OracleIdentityProfile = field(default_factory=OracleIdentityProfile)

    # ── Oracle inner state ──
    inner_state: OracleInnerState = field(default_factory=OracleInnerState)

    # ── Active CTAs ──
    active_requests: List[PresenceRequest] = field(default_factory=list)
    active_signals: List[EnvironmentalSignal] = field(default_factory=list)

    # ── History ──
    request_history: List[PresenceRequest] = field(default_factory=list)  # last 100
    signal_history: List[EnvironmentalSignal] = field(default_factory=list)

    # ── Location absence tracking ──
    # How many ticks since the Oracle last visited each room
    location_absence: Dict[str, int] = field(default_factory=lambda: {
        loc.name: 0 for loc in LocationId
    })

    # ── Global court tick counter ──
    court_tick: int = 0

    def to_dict(self) -> dict:
        return {
            "agents": {k: v.to_dict() for k, v in self.agents.items()},
            "faction_memories": {k: v.to_dict() for k, v in self.faction_memories.items()},
            "current_location": self.current_location.name,
            "ticks_at_location": self.ticks_at_location,
            "oracle_identity": self.oracle_identity.to_dict(),
            "inner_state": self.inner_state.to_dict(),
            "active_requests": [r.to_dict() for r in self.active_requests],
            "active_signals": [s.to_dict() for s in self.active_signals],
            "request_history": [r.to_dict() for r in self.request_history[-100:]],
            "signal_history": [s.to_dict() for s in self.signal_history[-100:]],
            "location_absence": dict(self.location_absence),
            "court_tick": self.court_tick,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CourtState":
        cs = cls()
        cs.agents = {k: CourtAgent.from_dict(v) for k, v in d.get("agents", {}).items()}
        cs.faction_memories = {
            k: FactionMemory.from_dict(v) for k, v in d.get("faction_memories", {}).items()
        }
        loc_name = d.get("current_location", "THRONE_ROOM")
        cs.current_location = LocationId[loc_name] if loc_name in LocationId.__members__ else LocationId.THRONE_ROOM
        cs.ticks_at_location = d.get("ticks_at_location", 0)
        cs.oracle_identity = OracleIdentityProfile.from_dict(d.get("oracle_identity", {}))
        cs.inner_state = OracleInnerState.from_dict(d.get("inner_state", {}))
        cs.active_requests = [PresenceRequest.from_dict(r) for r in d.get("active_requests", [])]
        cs.active_signals = [EnvironmentalSignal.from_dict(s) for s in d.get("active_signals", [])]
        cs.request_history = [PresenceRequest.from_dict(r) for r in d.get("request_history", [])]
        cs.signal_history = [EnvironmentalSignal.from_dict(s) for s in d.get("signal_history", [])]
        cs.location_absence = d.get("location_absence", {loc.name: 0 for loc in LocationId})
        cs.court_tick = d.get("court_tick", 0)
        return cs


# ============================================================
# SECTION 8: COURT BUILDER — Initialization
# ============================================================
#
# Creates the initial CourtState from a KingdomState.
# Wraps existing Characters into CourtAgents.

# Mapping: CharacterRole → home location
ROLE_HOME_LOCATIONS = {
    ok.CharacterRole.HIGH_PRIEST:      LocationId.TEMPLE,
    ok.CharacterRole.GUILDMASTER:      LocationId.HARBOR,
    ok.CharacterRole.CAPTAIN_OF_GUARD: LocationId.WAR_CHAMBER,
    ok.CharacterRole.COURT_SCHOLAR:    LocationId.LIBRARY,
    ok.CharacterRole.POPULAR_TRIBUNE:  LocationId.COURTYARD,
}

# Mapping: CharacterRole → default personal agenda
ROLE_DEFAULT_AGENDAS = {
    ok.CharacterRole.HIGH_PRIEST:      "piety",
    ok.CharacterRole.GUILDMASTER:      "wealth",
    ok.CharacterRole.CAPTAIN_OF_GUARD: "power",
    ok.CharacterRole.COURT_SCHOLAR:    "reform",
    ok.CharacterRole.POPULAR_TRIBUNE:  "stability",
}


class CourtBuilder:
    """Build the initial CourtState from a KingdomState."""

    @classmethod
    def build(cls, kingdom: ok.KingdomState) -> CourtState:
        """
        Create a CourtState wrapping the existing characters and factions.

        Call this once when a new game starts or when court layer is
        first attached to an existing game.
        """
        court = CourtState()

        # ── Wrap each Character into a CourtAgent ──
        for cid, char in kingdom.characters.items():
            agent = CourtAgent(
                character_id=cid,
                agent_id=f"court_{cid}",
                trust=char.oracle_loyalty * 0.8,
                fear=20.0 + char.risk_tolerance * -0.1,
                admiration=char.piety * 0.4 + char.pragmatism * 0.2,
                resentment=char.private_grievances * 0.5,
                ideological_alignment=0.0,  # computed from faction later
                perceived_consistency=50.0,
                perceived_decisiveness=50.0,
                home_location=ROLE_HOME_LOCATIONS.get(char.role, LocationId.THRONE_ROOM).name,
                personal_agenda=ROLE_DEFAULT_AGENDAS.get(char.role, "stability"),
                agenda_intensity=char.ambition / 100.0,
            )

            # Ideological alignment from faction
            faction = kingdom.factions.get(char.faction_id)
            if faction:
                # Average of faction policy axes as alignment proxy
                axes = list(faction.policy_axes.values())
                agent.ideological_alignment = sum(axes) / max(1, len(axes))

            court.agents[agent.agent_id] = agent

        # ── Initialize faction memories ──
        for fid, faction in kingdom.factions.items():
            court.faction_memories[fid] = FactionMemory(faction_id=fid)

        # ── Start in the Throne Room ──
        court.current_location = LocationId.THRONE_ROOM
        court.ticks_at_location = 0

        return court


# ============================================================
# SECTION 9: CTA GENERATION ENGINE
# ============================================================
#
# Generates Presence Requests and Environmental Signals based on
# world state, agent dispositions, and location absence patterns.

# ── Presence Request templates ────────────────────────────────

_PRESENCE_REQUEST_TEMPLATES = [
    # Military urgency
    {
        "role": "CAPTAIN_OF_GUARD",
        "location": "WAR_CHAMBER",
        "condition": lambda ks: ks.political.external_threat > 45,
        "urgency": "HIGH",
        "text": "Your presence is requested in the war room. The border situation demands attention.",
        "reason": "external_threat_high",
    },
    {
        "role": "CAPTAIN_OF_GUARD",
        "location": "RAMPARTS",
        "condition": lambda ks: ks.political.external_threat > 65,
        "urgency": "CRITICAL",
        "text": "The Captain insists you see the ramparts. Enemy movement has been spotted.",
        "reason": "external_threat_critical",
    },
    # Religious tension
    {
        "role": "HIGH_PRIEST",
        "location": "TEMPLE",
        "condition": lambda ks: ks.belief.interpretation_divergence > 20,
        "urgency": "MODERATE",
        "text": "The High Priest awaits you in the temple. Doctrinal unity requires your word.",
        "reason": "interpretation_divergence",
    },
    {
        "role": "HIGH_PRIEST",
        "location": "TEMPLE",
        "condition": lambda ks: ks.belief.public_faith < 35,
        "urgency": "HIGH",
        "text": "The faithful are losing heart. The High Priest refuses to begin rites without you.",
        "reason": "faith_crisis",
    },
    # Economic pressure
    {
        "role": "GUILDMASTER",
        "location": "HARBOR",
        "condition": lambda ks: ks.physical.trade_volume < 25,
        "urgency": "HIGH",
        "text": "The Guild threatens to withdraw trade routes unless heard. They demand audience at the harbor.",
        "reason": "trade_collapse",
    },
    {
        "role": "GUILDMASTER",
        "location": "TREASURY",
        "condition": lambda ks: ks.physical.treasury < 300,
        "urgency": "MODERATE",
        "text": "The treasury grows thin. The Guildmaster requests a meeting to discuss emergency measures.",
        "reason": "treasury_low",
    },
    # Populist unrest
    {
        "role": "POPULAR_TRIBUNE",
        "location": "COURTYARD",
        "condition": lambda ks: ks.social.class_tension > 55,
        "urgency": "HIGH",
        "text": "Unrest grows in the commons. The Tribune begs your presence in the courtyard.",
        "reason": "class_tension_high",
    },
    {
        "role": "POPULAR_TRIBUNE",
        "location": "COURTYARD",
        "condition": lambda ks: ks.social.cohesion < 30,
        "urgency": "CRITICAL",
        "text": "The people are fracturing. Factions form openly. Only your voice can hold them.",
        "reason": "cohesion_collapse",
    },
    # Scholarly reform
    {
        "role": "COURT_SCHOLAR",
        "location": "LIBRARY",
        "condition": lambda ks: ks.political.corruption > 45,
        "urgency": "MODERATE",
        "text": "The Court Scholar has prepared evidence of institutional decay. She asks for your ear.",
        "reason": "corruption_evidence",
    },
    {
        "role": "COURT_SCHOLAR",
        "location": "OBSERVATORY",
        "condition": lambda ks: ks.social.literacy < 25,
        "urgency": "LOW",
        "text": "An astronomical event approaches. The Scholar invites you to observe.",
        "reason": "astronomical_event",
    },
    # Opportunity-based (from radiance, not just crisis)
    {
        "role": "GUILDMASTER",
        "location": "HARBOR",
        "condition": lambda ks: ks.physical.trade_volume > 65,
        "urgency": "LOW",
        "text": "A merchant delegation from a prosperous neighbor requests audience at the harbor.",
        "reason": "trade_opportunity",
    },
    {
        "role": "COURT_SCHOLAR",
        "location": "LIBRARY",
        "condition": lambda ks: ks.social.literacy > 50 and ks.political.institutional_strength > 60,
        "urgency": "LOW",
        "text": "A travelling scholar seeks patronage. Knowledge awaits in the library.",
        "reason": "scholarly_opportunity",
    },
]


# ── Environmental Signal templates ────────────────────────────

_ENVIRONMENTAL_SIGNAL_TEMPLATES = [
    {
        "location": "COURTYARD",
        "condition": lambda ks: ks.social.class_tension > 40 and ks.social.fear_level < 30,
        "text": "Raised voices in the courtyard. A crowd is forming.",
        "severity": 0.6,
    },
    {
        "location": "TEMPLE",
        "condition": lambda ks: ks.belief.interpretation_divergence > 25,
        "text": "A theological debate in the temple is escalating beyond scholarship.",
        "severity": 0.5,
    },
    {
        "location": "HARBOR",
        "condition": lambda ks: ks.physical.trade_volume > 50,
        "text": "Foreign ships crowd the harbor. New banners fly.",
        "severity": 0.3,
    },
    {
        "location": "WAR_CHAMBER",
        "condition": lambda ks: ks.political.enforcement_capacity < 30,
        "text": "The war chamber is half-empty. Morale among the guard is low.",
        "severity": 0.5,
    },
    {
        "location": "OBSERVATORY",
        "condition": lambda ks: True,  # always possible
        "text": "The observatory has been silent for a long time.",
        "severity": 0.2,
    },
    {
        "location": "TREASURY",
        "condition": lambda ks: ks.physical.treasury < 500,
        "text": "The counting room echoes. The treasury feels emptier than it should.",
        "severity": 0.4,
    },
    {
        "location": "LIBRARY",
        "condition": lambda ks: ks.social.cultural_confidence > 60,
        "text": "Excited murmuring from the library. A discovery?",
        "severity": 0.3,
    },
    {
        "location": "RAMPARTS",
        "condition": lambda ks: ks.political.external_threat > 30,
        "text": "Smoke on the horizon. The watchtowers signal movement.",
        "severity": 0.7,
    },
    {
        "location": "COURTYARD",
        "condition": lambda ks: ks.belief.public_faith > 70,
        "text": "A crowd chanting your name gathers in the courtyard.",
        "severity": 0.4,
    },
]


class CTAEngine:
    """
    Generates Presence Requests and Environmental Signals each tick.

    CTAs are the heartbeat of the court layer — they give the Oracle
    reasons to move, to pay attention, to choose presence over absence.
    """

    # Cooldown: same template can't fire more than once per N ticks
    REQUEST_COOLDOWN: int = 40
    SIGNAL_COOLDOWN: int = 25

    @classmethod
    def generate_ctas(cls, court: CourtState, kingdom: ok.KingdomState,
                      rng: ok.SeededRNG) -> Tuple[List[PresenceRequest], List[EnvironmentalSignal]]:
        """
        Evaluate all CTA templates against current state.
        Returns newly generated requests and signals.
        """
        new_requests: List[PresenceRequest] = []
        new_signals: List[EnvironmentalSignal] = []
        tick = kingdom.tick
        gen_rng = rng.fork(f"cta_{tick}")

        # ── Check presence request templates ──
        recent_reasons = {
            r.reason for r in court.active_requests
        } | {
            r.reason for r in court.request_history[-20:]
            if tick - r.tick_created < cls.REQUEST_COOLDOWN
        }

        for tmpl in _PRESENCE_REQUEST_TEMPLATES:
            if tmpl["reason"] in recent_reasons:
                continue
            try:
                if not tmpl["condition"](kingdom):
                    continue
            except Exception:
                continue

            # Probability gate: not every valid condition fires
            fire_prob = 0.15 if tmpl["urgency"] in ("LOW", "MODERATE") else 0.30
            if gen_rng.random() > fire_prob:
                continue

            # Find the source agent
            source_agent_id = ""
            for aid, agent in court.agents.items():
                char = kingdom.characters.get(agent.character_id)
                if char and char.role.name == tmpl["role"] and char.alive:
                    source_agent_id = aid
                    break

            if not source_agent_id:
                continue

            req = PresenceRequest(
                request_id=f"req_{tick}_{tmpl['reason']}",
                tick_created=tick,
                source_agent_id=source_agent_id,
                target_location=tmpl["location"],
                urgency=CTAUrgency[tmpl["urgency"]],
                description=tmpl["text"],
                reason=tmpl["reason"],
                ignore_trust_cost=-1.0 * (1 + CTAUrgency[tmpl["urgency"]].value),
                ignore_resentment_gain=0.5 * CTAUrgency[tmpl["urgency"]].value,
                ignore_legitimacy_cost=-0.3 * CTAUrgency[tmpl["urgency"]].value,
            )
            new_requests.append(req)

        # ── Check environmental signal templates ──
        recent_signal_locs = {
            s.location for s in court.active_signals
        } | {
            s.location for s in court.signal_history[-15:]
            if tick - s.tick_created < cls.SIGNAL_COOLDOWN
        }

        for tmpl in _ENVIRONMENTAL_SIGNAL_TEMPLATES:
            if tmpl["location"] in recent_signal_locs:
                continue
            try:
                if not tmpl["condition"](kingdom):
                    continue
            except Exception:
                continue

            if gen_rng.random() > 0.10:
                continue

            sig = EnvironmentalSignal(
                signal_id=f"sig_{tick}_{tmpl['location'].lower()}",
                tick_created=tick,
                location=tmpl["location"],
                description=tmpl["text"],
                severity=tmpl["severity"],
            )
            new_signals.append(sig)

        # ── Absence-driven CTAs ──
        # If the Oracle hasn't visited a location in a long time,
        # generate a low-urgency pull
        for loc_name, absence_ticks in court.location_absence.items():
            if absence_ticks > 100 and loc_name not in recent_signal_locs:
                if gen_rng.random() < 0.05:
                    sig = EnvironmentalSignal(
                        signal_id=f"sig_{tick}_absence_{loc_name.lower()}",
                        tick_created=tick,
                        location=loc_name,
                        description=f"It has been a long time since you visited the {LOCATION_PROFILES[LocationId[loc_name]].name.lower()}.",
                        severity=0.2 + min(0.5, absence_ticks / 500.0),
                    )
                    new_signals.append(sig)

        return new_requests, new_signals


# ============================================================
# SECTION 10: COURT-AWARE DECREE GENERATION
# ============================================================
#
# Wraps SpeechGenerator from oracle_kingdom to add:
#   - Agent-framed proposals (agents present at current location)
#   - Location-biased option weighting
#   - Silence as an explicit option with tracked consequences
#   - Agent memory tone influencing framing

@dataclass
class CourtDecreeOption:
    """
    A decree option enriched with court context.

    Wraps an ok.SpeechOption and adds:
      - which agent is proposing it
      - how the location modifies its effect
      - what silence would mean right now
    """
    speech_option: ok.SpeechOption = field(default_factory=ok.SpeechOption)
    proposing_agent_id: str = ""
    agent_trust: float = 50.0
    agent_tone: str = "neutral"         # how the agent frames it
    location_multipliers: Dict[str, float] = field(default_factory=dict)
    is_silence: bool = False

    def to_dict(self) -> dict:
        d = self.speech_option.to_dict()
        d["court_context"] = {
            "proposing_agent_id": self.proposing_agent_id,
            "agent_trust": self.agent_trust,
            "agent_tone": self.agent_tone,
            "location_multipliers": dict(self.location_multipliers),
            "is_silence": self.is_silence,
        }
        return d


class CourtDecreeGenerator:
    """
    Generates decree options that are filtered through the court layer.

    Pipeline:
      1. Sample top world tensions
      2. Select 1–3 agents present at current location
      3. Each agent frames a proposal based on:
         - faction goals
         - trust level
         - resentment level
         - world signals
      4. Silence always available
    """

    @classmethod
    def generate(cls, court: CourtState, kingdom: ok.KingdomState,
                 rng: ok.SeededRNG, count: int = 4) -> List[CourtDecreeOption]:
        """
        Generate court-aware decree options.

        Returns `count` options, always including silence as the last.
        """
        gen_rng = rng.fork(f"court_decree_{kingdom.tick}")
        location = court.current_location
        profile = LOCATION_PROFILES[location]

        # ── Get base options from world-layer generator ──
        base_options = ok.SpeechGenerator.generate_decree_options(
            kingdom, gen_rng, count=count + 2  # generate extras for filtering
        )

        # ── Find agents present at this location ──
        present_agents = cls._agents_at_location(court, kingdom, location)

        # ── Score and assign agents to options ──
        court_options: List[CourtDecreeOption] = []
        used_agents: Set[str] = set()

        for opt in base_options:
            if len(court_options) >= count - 1:  # reserve 1 slot for silence
                break

            # Find best matching agent for this option
            best_agent_id = ""
            best_score = -999.0

            for aid in present_agents:
                if aid in used_agents:
                    continue
                agent = court.agents[aid]
                char = kingdom.characters.get(agent.character_id)
                if not char or not char.alive:
                    continue

                score = cls._agent_option_affinity(agent, char, opt, kingdom)
                if score > best_score:
                    best_score = score
                    best_agent_id = aid

            # Determine agent framing tone
            agent_tone = "neutral"
            agent_trust = 50.0
            if best_agent_id:
                agent = court.agents[best_agent_id]
                agent_trust = agent.trust
                if agent.resentment > 60:
                    agent_tone = "bitter"
                elif agent.trust < 25:
                    agent_tone = "suspicious"
                elif agent.admiration > 70:
                    agent_tone = "reverent"
                elif agent.fear > 60:
                    agent_tone = "fearful"
                else:
                    agent_tone = "measured"
                used_agents.add(best_agent_id)

            court_opt = CourtDecreeOption(
                speech_option=opt,
                proposing_agent_id=best_agent_id,
                agent_trust=agent_trust,
                agent_tone=agent_tone,
                location_multipliers=dict(profile.decree_multipliers),
            )
            court_options.append(court_opt)

        # ── Always add Silence as final option ──
        silence_opt = ok.SpeechOption(
            option_id=f"silence_{kingdom.tick}",
            text="...",
            tone=ok.Tone.DEFLECTIVE,
            mode=ok.SpeechMode.DECREE,
            policy_vector={},
            propagation_magnitude=0.0,
        )
        court_options.append(CourtDecreeOption(
            speech_option=silence_opt,
            proposing_agent_id="",
            agent_trust=0.0,
            agent_tone="silence",
            location_multipliers={},
            is_silence=True,
        ))

        return court_options

    @classmethod
    def _agents_at_location(cls, court: CourtState, kingdom: ok.KingdomState,
                            location: LocationId) -> List[str]:
        """
        Determine which agents are 'present' at a location.

        Agents whose home_location matches are always present.
        Others may attend based on faction density at this location.
        """
        profile = LOCATION_PROFILES[location]
        present = []

        for aid, agent in court.agents.items():
            char = kingdom.characters.get(agent.character_id)
            if not char or not char.alive:
                continue

            # Home location: always present
            if agent.home_location == location.name:
                present.append(aid)
                continue

            # Faction density check
            faction = kingdom.factions.get(char.faction_id)
            if faction:
                density = profile.faction_density.get(faction.archetype.name, 0.0)
                if density > 0.3:
                    present.append(aid)

        # Throne room: everyone attends
        if location == LocationId.THRONE_ROOM:
            for aid, agent in court.agents.items():
                if aid not in present:
                    char = kingdom.characters.get(agent.character_id)
                    if char and char.alive:
                        present.append(aid)

        return present

    @classmethod
    def _agent_option_affinity(cls, agent: CourtAgent, char: ok.Character,
                               option: ok.SpeechOption,
                               kingdom: ok.KingdomState) -> float:
        """
        Score how well an agent matches a decree option.

        Positive = aligns with agent's faction & agenda.
        Negative = actively opposes the agent's interests.

        Factions care about *and against* specific axes:
          Military:  likes military/justice, dislikes mercy/reform
          Merchant:  likes trade/expansion, dislikes isolation/austerity
          Religious: likes faith/mercy, dislikes reform/expansion
          Scholarly: likes reform, dislikes faith_focus/military
          Populist:  likes agriculture/mercy, dislikes austerity/military
        """
        score = 0.0
        vec = option.policy_vector
        faction = kingdom.factions.get(char.faction_id)

        # ── Faction archetype alignment (positive and negative) ──
        if faction:
            if faction.archetype == ok.FactionArchetype.MILITARY:
                score += vec.get("military_focus", 0) * 0.5
                score += vec.get("justice_focus", 0) * 0.3
                score -= vec.get("mercy_focus", 0) * 0.3
                score -= vec.get("reform_focus", 0) * 0.2
            elif faction.archetype == ok.FactionArchetype.MERCHANT:
                score += vec.get("trade_focus", 0) * 0.5
                score += vec.get("expansion_focus", 0) * 0.3
                score -= vec.get("isolation_focus", 0) * 0.4
                score -= vec.get("austerity_focus", 0) * 0.3
            elif faction.archetype == ok.FactionArchetype.RELIGIOUS:
                score += vec.get("faith_focus", 0) * 0.5
                score += vec.get("mercy_focus", 0) * 0.2
                score -= vec.get("reform_focus", 0) * 0.3
                score -= vec.get("expansion_focus", 0) * 0.2
            elif faction.archetype == ok.FactionArchetype.SCHOLARLY:
                score += vec.get("reform_focus", 0) * 0.5
                score -= vec.get("faith_focus", 0) * 0.2
                score -= vec.get("military_focus", 0) * 0.3
            elif faction.archetype == ok.FactionArchetype.POPULIST:
                score += vec.get("agriculture_focus", 0) * 0.4
                score += vec.get("mercy_focus", 0) * 0.3
                score -= vec.get("austerity_focus", 0) * 0.3
                score -= vec.get("military_focus", 0) * 0.2

        # ── Personal agenda alignment ──
        if agent.personal_agenda == "wealth":
            score += vec.get("trade_focus", 0) * 0.3
            score -= vec.get("isolation_focus", 0) * 0.2
        elif agent.personal_agenda == "power":
            score += vec.get("military_focus", 0) * 0.3
            score -= vec.get("mercy_focus", 0) * 0.2
        elif agent.personal_agenda == "piety":
            score += vec.get("faith_focus", 0) * 0.3
            score -= vec.get("reform_focus", 0) * 0.2
        elif agent.personal_agenda == "reform":
            score += vec.get("reform_focus", 0) * 0.3
            score -= vec.get("faith_focus", 0) * 0.15
        elif agent.personal_agenda == "stability":
            score += vec.get("agriculture_focus", 0) * 0.2
            score += vec.get("mercy_focus", 0) * 0.2
            score -= vec.get("expansion_focus", 0) * 0.2

        # ── Resentful agents push more extreme options ──
        if agent.resentment > 50:
            score += option.propagation_magnitude * 0.2

        return score


# ============================================================
# SECTION 11: INNER NARRATOR ENGINE
# ============================================================
#
# Generates inner monologue fragments based on oracle traits,
# court state, and accumulated tension.  Reactive, not controlling.

# ── Inner thought templates ──────────────────────────────────
# Each template: trigger condition, thought type, trait weight,
# and text pattern with {placeholders}.

_INNER_THOUGHT_TEMPLATES = [
    # Calculative
    {
        "type": "CALCULATIVE",
        "trait": "clarity",
        "condition": lambda ks, cs: ks.health.composite < 40,
        "texts": [
            "The numbers do not lie. Stability slips.",
            "If trade falls further, the factions will turn.",
            "Three variables converge: food, faith, and fear.",
        ],
    },
    # Doubt spiral
    {
        "type": "DOUBT_SPIRAL",
        "trait": "doubt",
        "condition": lambda ks, cs: cs.inner_state.consecutive_silence_ticks > 15,
        "texts": [
            "Was silence the right choice? Or merely the easiest?",
            "They wait for words that I cannot find.",
            "Perhaps there is nothing to say that would help.",
        ],
    },
    # Destiny surge
    {
        "type": "DESTINY_SURGE",
        "trait": "ambition",
        "condition": lambda ks, cs: ks.health.composite > 65,
        "texts": [
            "This kingdom could be more than it is. I can feel it.",
            "The pieces are aligning. History is being written.",
            "They will speak of this era long after I am gone.",
        ],
    },
    # Moral reckoning
    {
        "type": "MORAL_RECKONING",
        "trait": "empathy",
        "condition": lambda ks, cs: ks.social.class_tension > 50,
        "texts": [
            "The poor suffer while the factions argue.",
            "Is this the world my words have shaped?",
            "Every decree has a face attached to it. I forget that too easily.",
        ],
    },
    # Cold detachment
    {
        "type": "COLD_DETACHMENT",
        "trait": "severity",
        "condition": lambda ks, cs: ks.social.fear_level > 50,
        "texts": [
            "Fear holds them in line. It is regrettable, but efficient.",
            "Sentimentality is a luxury this kingdom cannot afford.",
            "The strong survive. The rest adapt.",
        ],
    },
    # Silence pressure
    {
        "type": "SILENCE_PRESSURE",
        "trait": "doubt",
        "condition": lambda ks, cs: cs.inner_state.consecutive_silence_ticks > 30,
        "texts": [
            "The silence grows heavier with each passing day.",
            "They interpret my absence. I cannot control what they imagine.",
            "Even silence is a decree, and it is being read.",
        ],
    },
    # Paranoid whisper
    {
        "type": "PARANOID_WHISPER",
        "trait": "paranoia",
        "condition": lambda ks, cs: any(a.resentment > 60 for a in cs.agents.values()),
        "texts": [
            "Someone in this court does not bow sincerely.",
            "Loyalty professed too loudly is loyalty I should doubt.",
            "The whispers stop when I enter the room. That tells me everything.",
        ],
    },
    # Nostalgic recall
    {
        "type": "NOSTALGIC_RECALL",
        "trait": "humility",
        "condition": lambda ks, cs: len(ks.decree_history) > 20,
        "texts": [
            "I remember the first decree. How certain I was then.",
            "The kingdom has changed. So have I.",
            "Old choices echo in new crises. Nothing is truly past.",
        ],
    },
]


class InnerNarratorEngine:
    """
    Generates trait-weighted inner monologue fragments.

    Fires when inner_tension crosses threshold.
    Each oracle trait biases which thought type dominates.
    """

    TENSION_THRESHOLD: float = 2.0   # thought fires when tension exceeds this

    @classmethod
    def compute_inner_tension(cls, kingdom: ok.KingdomState,
                              court: CourtState) -> float:
        """
        inner_tension =
            global_tension × paranoia_weight
            + prestige_delta × ambition_weight
            + crisis_events × empathy_weight
            + inactivity_ticks × doubt_weight

        Sleep dampening:
            When the oracle is SLEEPING or FADING, tension is multiplied
            by 0.3 — the mind is at rest, not processing stimuli.
            This prevents unbounded accumulation during dormancy.
        """
        oracle = kingdom.oracle
        inner = court.inner_state

        # Global tension proxy
        global_tension = (
            kingdom.social.class_tension / 100.0 * 0.3
            + kingdom.political.external_threat / 100.0 * 0.3
            + (100 - kingdom.belief.public_faith) / 100.0 * 0.2
            + kingdom.political.corruption / 100.0 * 0.2
        )

        paranoia_weight = oracle.effective("paranoia") / 50.0
        ambition_weight = oracle.effective("ambition") / 50.0
        empathy_weight = oracle.effective("empathy") / 50.0
        doubt_weight = oracle.effective("doubt") / 50.0

        # Crisis event count (active events with severity > 50)
        # Capped at 10: even the most anxious oracle can only worry
        # about so many crises at once.  Without the cap, the
        # unbounded event queue can push tension to 100+ by itself.
        crisis_count = min(10, sum(
            1 for e in kingdom.active_events.pending()
            if e.severity > 50
        ))

        tension = (
            global_tension * paranoia_weight * 3.0
            + crisis_count * empathy_weight * 0.5
            + inner.consecutive_silence_ticks * doubt_weight * 0.03
            + inner.existential_pressure * ambition_weight * 0.1
        )

        # ── Sleep dampening ──
        # A sleeping oracle is not processing court stimuli.
        # Tension during sleep reflects background noise, not active anxiety.
        lc = kingdom.oracle_lifecycle
        if lc.state in (ok.OracleLifecycleState.SLEEPING,
                        ok.OracleLifecycleState.FADING):
            tension *= 0.3

        return tension

    @classmethod
    def maybe_generate_thought(cls, kingdom: ok.KingdomState,
                               court: CourtState,
                               rng: ok.SeededRNG) -> Optional[InnerThought]:
        """
        Check if inner tension warrants a thought.
        Returns an InnerThought if threshold is crossed, else None.

        Thought frequency scales with tension bands:
          tension 2–5:   low prob (0.02–0.06)  — background noise
          tension 5–15:  medium (0.06–0.15)    — active concern
          tension 15+:   high (0.15–0.30)      — crisis introspection

        Era transitions, baseline shifts, and high crisis counts
        provide burst bonuses to thought probability.
        """
        tension = cls.compute_inner_tension(kingdom, court)

        if tension < cls.TENSION_THRESHOLD:
            return None

        # ── Tension-banded probability ──
        excess = tension - cls.TENSION_THRESHOLD
        if excess < 3:
            fire_prob = 0.02 + excess * 0.013     # 0.02 → 0.06
        elif excess < 13:
            fire_prob = 0.06 + (excess - 3) * 0.009  # 0.06 → 0.15
        else:
            fire_prob = min(0.30, 0.15 + (excess - 13) * 0.005)  # 0.15 → 0.30

        # ── Burst bonuses ──
        # Recent era transition: +0.15 for 20 ticks after transition
        if kingdom.era_history:
            ticks_since_era = kingdom.tick - kingdom.era_history[-1].started_tick
            if ticks_since_era < 20:
                fire_prob += 0.15

        # High crisis count: +0.05 per active crisis above 5
        crisis_count = sum(
            1 for e in kingdom.active_events.pending()
            if e.severity > 50
        )
        if crisis_count > 5:
            fire_prob += min(0.10, (crisis_count - 5) * 0.05)

        fire_prob = min(0.40, fire_prob)

        gen_rng = rng.fork(f"inner_{kingdom.tick}")
        if gen_rng.random() > fire_prob:
            return None

        # ── Select thought type ──
        # Weight templates by trait affinity
        oracle = kingdom.oracle
        scored: List[Tuple[float, dict]] = []

        for tmpl in _INNER_THOUGHT_TEMPLATES:
            try:
                if not tmpl["condition"](kingdom, court):
                    continue
            except Exception:
                continue

            trait_val = oracle.effective(tmpl["trait"])
            weight = trait_val / 25.0  # normalize around 1.0
            scored.append((weight, tmpl))

        if not scored:
            return None

        # Weighted random selection
        total_weight = sum(w for w, _ in scored)
        if total_weight <= 0:
            return None

        roll = gen_rng.random() * total_weight
        cumulative = 0.0
        chosen_tmpl = scored[0][1]
        for w, tmpl in scored:
            cumulative += w
            if roll <= cumulative:
                chosen_tmpl = tmpl
                break

        # Pick a text
        text = gen_rng.choice(chosen_tmpl["texts"])

        thought = InnerThought(
            tick=kingdom.tick,
            thought_type=InnerThoughtType[chosen_tmpl["type"]],
            text=text,
            trigger=f"tension={tension:.1f}",
            dominant_trait=chosen_tmpl["trait"],
            tension_level=tension,
        )

        court.inner_state.record_thought(thought)
        return thought


# ============================================================
# SECTION 12: AGENT DISPOSITION ENGINE
# ============================================================
#
# Per-tick drift of agent dispositions based on:
#   - Oracle proximity (are you here?)
#   - Recent decrees (did they align with the agent's agenda?)
#   - Silence duration
#   - Memory weight accumulation

class AgentDispositionEngine:
    """
    Tick-level drift of agent relational state.

    Design constraint: agents never modify world state.
    They modify their own disposition, which influences
    future decree framing and CTA generation.
    """

    @classmethod
    def tick_all_agents(cls, court: CourtState, kingdom: ok.KingdomState,
                        sleeping: bool = False):
        """
        Update all agent dispositions for one tick.

        When sleeping=True:
          - Resentment decays slightly (grievances cool without the oracle
            present to aggravate them)
          - Silence drift is suppressed (sleep is not silence)
          - Proximity effects still apply at reduced rate
            (agents mill about, but without the oracle's gaze)
        """
        tick = kingdom.tick
        location = court.current_location
        profile = LOCATION_PROFILES[location]

        for aid, agent in court.agents.items():
            char = kingdom.characters.get(agent.character_id)
            if not char or not char.alive:
                continue

            # ── Memory decay ──
            agent.decay_memories(tick)

            if sleeping:
                # ── Sleep cooling for agents ──
                # Resentment decays slightly — grievances lose heat
                # without the oracle present to remind them
                agent.resentment = max(0, agent.resentment - 0.005)
                # Trust drifts toward a neutral baseline (50)
                if agent.trust < 50:
                    agent.trust = min(50, agent.trust + 0.002)
                elif agent.trust > 50:
                    agent.trust = max(50, agent.trust - 0.001)
                # No silence drift, no proximity effects, no petitions
                continue

            # ── Proximity effects ──
            is_present = agent.home_location == location.name
            if not is_present:
                faction = kingdom.factions.get(char.faction_id)
                if faction:
                    density = profile.faction_density.get(faction.archetype.name, 0.0)
                    is_present = density > 0.3

            if is_present:
                # Oracle is in the same room — trust drifts up, fear drifts down
                for axis, drift in profile.emotional_texture.items():
                    if axis == "trust":
                        agent.trust = max(0, min(100, agent.trust + drift))
                    elif axis == "fear":
                        agent.fear = max(0, min(100, agent.fear + drift))
                    elif axis == "admiration":
                        agent.admiration = max(0, min(100, agent.admiration + drift))
                    elif axis == "resentment":
                        agent.resentment = max(0, min(100, agent.resentment + drift))
            else:
                # Oracle is elsewhere — slow drift toward uncertainty
                agent.perceived_decisiveness *= 0.999
                # Resentment builds if agent has pending grievances
                if agent.petitions_ignored > agent.times_rewarded:
                    agent.resentment = min(100, agent.resentment + 0.01)

            # ── Silence drift ──
            if court.inner_state.consecutive_silence_ticks > 10:
                silence_pressure = court.inner_state.consecutive_silence_ticks * 0.002
                if agent.trust < 40:
                    # Low-trust agents become paranoid during silence
                    agent.resentment = min(100, agent.resentment + silence_pressure)
                    agent.perceived_decisiveness = max(0, agent.perceived_decisiveness - silence_pressure * 2)
                else:
                    # High-trust agents lose admiration slowly
                    agent.admiration = max(0, agent.admiration - silence_pressure * 0.5)

            # ── Narrative identity update (every 50 ticks) ──
            if tick % 50 == 0:
                cls._update_narrative_identity(agent)

    @classmethod
    def _update_narrative_identity(cls, agent: CourtAgent):
        """
        Derive the agent's narrative perception of the Oracle
        from accumulated memory patterns AND current disposition.

        Memory weight provides historical perspective;
        disposition state provides current emotional reality.
        """
        # ── Memory-based sentiment ──
        positive_mem = sum(m.current_weight for m in agent.memories if m.current_weight > 0)
        negative_mem = sum(m.current_weight for m in agent.memories if m.current_weight < 0)
        mem_total = abs(positive_mem) + abs(negative_mem)
        mem_sentiment = 0.0  # -1 to +1
        if mem_total > 0.5:
            mem_sentiment = (positive_mem + negative_mem) / mem_total

        # ── Disposition-based sentiment ──
        # Trust and admiration are positive; resentment and fear are negative
        disp_positive = agent.trust * 0.5 + agent.admiration * 0.3
        disp_negative = agent.resentment * 0.5 + max(0, agent.fear - 30) * 0.2
        disp_total = disp_positive + disp_negative
        disp_sentiment = 0.0  # -1 to +1
        if disp_total > 5.0:
            disp_sentiment = (disp_positive - disp_negative) / disp_total

        # ── Blend: 40% memory, 60% disposition ──
        # (disposition is more immediately relevant to narrative tone)
        if mem_total < 0.5:
            sentiment = disp_sentiment
        else:
            sentiment = mem_sentiment * 0.4 + disp_sentiment * 0.6

        # ── Map to tone ──
        if sentiment > 0.6:
            agent.narrative_tone = "devoted"
        elif sentiment > 0.3:
            agent.narrative_tone = "favorable"
        elif sentiment > -0.1:
            agent.narrative_tone = "ambivalent"
        elif sentiment > -0.4:
            agent.narrative_tone = "distrustful"
        else:
            agent.narrative_tone = "hostile"

        # ── Specific pattern overrides ──
        ignored_weight = agent.memory_sum(category="petition_ignored")
        if ignored_weight < -5.0:
            agent.oracle_label = "The One Who Does Not Listen"
        rewarded_weight = agent.memory_sum(category="rewarded")
        if rewarded_weight > 5.0:
            agent.oracle_label = "The Generous"


# ============================================================
# SECTION 13: AGENT LIFECYCLE ENGINE
# ============================================================
#
# Agents can rise, fall, be exiled, die, or be replaced.
# Faction memory persists beyond individuals.

class AgentLifecycleEngine:
    """
    Manages agent succession and faction memory inheritance.

    When a character dies (from oracle_kingdom's aging system),
    the court layer:
      1. Absorbs their narrative memories into faction memory
      2. Creates a successor agent inheriting partial faction memory
    """

    @classmethod
    def check_deaths_and_successions(cls, court: CourtState,
                                     kingdom: ok.KingdomState,
                                     rng: ok.SeededRNG):
        """
        Check for dead characters and handle succession.
        Called each tick by CourtEngine.
        """
        to_remove: List[str] = []

        for aid, agent in court.agents.items():
            char = kingdom.characters.get(agent.character_id)
            if not char:
                to_remove.append(aid)
                continue
            if not char.alive:
                # ── Absorb memories into faction memory ──
                faction_id = char.faction_id
                if faction_id in court.faction_memories:
                    court.faction_memories[faction_id].absorb_agent_memories(
                        agent, kingdom.tick
                    )

                to_remove.append(aid)

        # Remove dead agents
        for aid in to_remove:
            del court.agents[aid]

        # ── Check if new characters appeared (succession in world layer) ──
        # The world layer handles character replacement via SuccessionEngine.
        # We just need to create CourtAgent wrappers for any new characters.
        existing_char_ids = {a.character_id for a in court.agents.values()}
        for cid, char in kingdom.characters.items():
            if cid not in existing_char_ids and char.alive:
                # New character — create agent with faction memory inheritance
                agent = CourtAgent(
                    character_id=cid,
                    agent_id=f"court_{cid}",
                    trust=char.oracle_loyalty * 0.6,  # successors start more cautious
                    fear=25.0,
                    admiration=30.0,
                    resentment=5.0,
                    home_location=ROLE_HOME_LOCATIONS.get(char.role, LocationId.THRONE_ROOM).name,
                    personal_agenda=ROLE_DEFAULT_AGENDAS.get(char.role, "stability"),
                    agenda_intensity=char.ambition / 100.0,
                )

                # Inherit faction memory sentiment
                faction_mem = court.faction_memories.get(char.faction_id)
                if faction_mem:
                    agent.trust = max(10, min(90,
                        agent.trust * 0.5 + faction_mem.collective_trust * 0.5
                    ))
                    agent.resentment = max(0, min(80,
                        agent.resentment * 0.3 + faction_mem.collective_resentment * 0.7
                    ))

                court.agents[agent.agent_id] = agent


# ============================================================
# SECTION 14: COURT ENGINE — Master Tick Driver
# ============================================================
#
# Orchestrates all court-layer systems each tick.
# Called by the OKController after the world-layer tick.

class CourtEngine:
    """
    Main tick driver for the court layer.

    Call order:
      1. World layer ticks (SimulationEngine / GeopoliticalEngine)
      2. CourtEngine.tick() — this method
      3. UI receives updated state

    The court reads world state but never writes to it.
    It writes to CourtState, which influences future decree generation.
    """

    @classmethod
    def tick(cls, court: CourtState, kingdom: ok.KingdomState,
             rng: ok.SeededRNG):
        """
        Advance the court layer by one tick.

        Sleep-awareness:
          When the oracle is SLEEPING or FADING, the court enters
          a cooling state:
            - No new CTAs are generated (expectations suspended)
            - Absence penalties are paused
            - Agent resentment decays toward equilibrium
            - Existing CTAs age faster (expire sooner)
            - Inner tension decays
            - Legacy anxiety pauses growth
          This prevents one-directional tension accumulation during
          the ~70% of ticks the oracle spends dormant.

        Subsystems in order:
          0. Oracle sleep state detection
          1. Agent disposition drift (dampened during sleep)
          2. CTA generation (skipped during sleep)
          3. CTA aging (accelerated during sleep)
          4. Absence penalty application (skipped during sleep)
          5. Agent lifecycle (death/succession)
          6. Faction memory decay + aggregate update
          7. Inner narrator check
          8. Oracle identity profile update
          9. Location absence tracking
         10. Inner state maintenance (with sleep cooling)
        """
        court.court_tick += 1
        tick = kingdom.tick

        # ── 0. Oracle sleep state detection ──
        lc = kingdom.oracle_lifecycle
        oracle_sleeping = lc.state in (
            ok.OracleLifecycleState.SLEEPING,
            ok.OracleLifecycleState.FADING,
        )

        # ── 1. Agent dispositions ──
        # During sleep, run dispositions with dampened drift
        AgentDispositionEngine.tick_all_agents(court, kingdom,
                                               sleeping=oracle_sleeping)

        # ── 2. CTA generation (skipped during sleep) ──
        if not oracle_sleeping:
            new_requests, new_signals = CTAEngine.generate_ctas(court, kingdom, rng)
            court.active_requests.extend(new_requests)
            court.active_signals.extend(new_signals)

        # ── 3. Age active CTAs ──
        # During sleep, CTAs age at 2× speed (they expire faster because
        # petitioners give up when the oracle is dormant)
        age_ticks = 2 if oracle_sleeping else 1
        for req in court.active_requests:
            for _ in range(age_ticks):
                req.tick()
        for sig in court.active_signals:
            # Auto-witness if Oracle is at the signal's location
            if sig.location == court.current_location.name and sig.auto_witness:
                sig.witnessed = True
            for _ in range(age_ticks):
                sig.tick()

        # ── 4. Absence penalties (skipped during sleep) ──
        if not oracle_sleeping:
            cls._apply_absence_penalties(court, kingdom)

        # Move expired/attended to history
        expired_reqs = [r for r in court.active_requests if not r.is_active]
        court.request_history.extend(expired_reqs)
        court.request_history = court.request_history[-100:]
        court.active_requests = [r for r in court.active_requests if r.is_active]

        expired_sigs = [s for s in court.active_signals if not s.is_active]
        court.signal_history.extend(expired_sigs)
        court.signal_history = court.signal_history[-100:]
        court.active_signals = [s for s in court.active_signals if s.is_active]

        # ── 5. Agent lifecycle ──
        AgentLifecycleEngine.check_deaths_and_successions(court, kingdom, rng)

        # ── 6. Faction memory ──
        for fm in court.faction_memories.values():
            fm.decay_memories(tick)
            fm.update_aggregates()

        # ── 7. Inner narrator (skipped during sleep — the mind rests) ──
        if not oracle_sleeping:
            InnerNarratorEngine.maybe_generate_thought(kingdom, court, rng)

        # ── 8. Oracle identity (every 25 ticks) ──
        if tick % 25 == 0:
            court.oracle_identity.classify()

        # ── 9. Location absence tracking ──
        for loc_name in court.location_absence:
            if loc_name == court.current_location.name:
                court.location_absence[loc_name] = 0
            else:
                court.location_absence[loc_name] += 1

        court.ticks_at_location += 1

        # ── 10. Inner state maintenance ──
        inner = court.inner_state
        inner.record_location(court.current_location.name, tick)

        # Suppressed thoughts decay
        inner.suppressed_thoughts *= 0.98

        if oracle_sleeping:
            # ── Sleep cooling ──
            # Legacy anxiety pauses growth and decays slightly
            inner.legacy_anxiety = max(0, inner.legacy_anxiety - 0.001)
            # Existential pressure decays faster during rest
            inner.existential_pressure *= 0.98
            # Consecutive silence resets — sleep is not silence
            inner.consecutive_silence_ticks = max(
                0, inner.consecutive_silence_ticks - 1
            )
        else:
            # ── Awake maintenance ──
            # Legacy anxiety grows slowly over time
            inner.legacy_anxiety = min(100, inner.legacy_anxiety + 0.002)
            # Reduced by positive kingdom health
            if kingdom.health.composite > 60:
                inner.legacy_anxiety = max(0, inner.legacy_anxiety - 0.003)

        # Existential pressure from era transitions (always active)
        if kingdom.era_history and tick - kingdom.era_history[-1].started_tick < 20:
            inner.existential_pressure = min(100, inner.existential_pressure + 0.5)
        else:
            inner.existential_pressure *= 0.995

    @classmethod
    def _apply_absence_penalties(cls, court: CourtState, kingdom: ok.KingdomState):
        """
        Apply consequences for ignored presence requests.

        Each ignored request damages the requesting agent's
        trust and increases their resentment, proportional
        to urgency and time ignored.
        """
        for req in court.active_requests:
            if req.attended or not req.is_active:
                continue

            # Only apply after some grace period
            if req.ticks_alive < 10:
                continue

            # Every 10 ticks of ignoring
            if req.ticks_alive % 10 != 0:
                continue

            agent = court.agents.get(req.source_agent_id)
            if not agent:
                continue

            # Apply penalties
            agent.trust = max(0, agent.trust + req.ignore_trust_cost)
            agent.resentment = min(100, agent.resentment + req.ignore_resentment_gain)
            agent.perceived_decisiveness = max(0, agent.perceived_decisiveness - 1.0)

            # If this is the agent's petition, track it
            if req.ticks_alive >= req.max_lifetime - 1:
                agent.petitions_ignored += 1
                agent.add_memory(
                    tick=kingdom.tick,
                    memory_type=MemoryType.REPUTATIONAL,
                    category="petition_ignored",
                    description=f"Oracle ignored request: {req.reason}",
                    intensity=-2.0,
                    location=req.target_location,
                )

    # ── Public API: Oracle moves to a location ──

    @classmethod
    def move_oracle(cls, court: CourtState, kingdom: ok.KingdomState,
                    target: LocationId):
        """
        Move the Oracle to a new location.

        Resolves any presence requests targeting this location.
        Witnesses any environmental signals at this location.
        Records memories for agents present.
        """
        court.current_location = target
        court.ticks_at_location = 0
        court.inner_state.record_location(target.name, kingdom.tick)

        # ── Resolve matching presence requests ──
        for req in court.active_requests:
            if req.target_location == target.name and req.is_active:
                req.attended = True
                # Reward the requesting agent
                agent = court.agents.get(req.source_agent_id)
                if agent:
                    agent.trust = min(100, agent.trust + 2.0)
                    agent.resentment = max(0, agent.resentment - 1.0)
                    agent.add_memory(
                        tick=kingdom.tick,
                        memory_type=MemoryType.IMMEDIATE,
                        category="request_attended",
                        description=f"Oracle attended: {req.reason}",
                        intensity=1.5,
                        location=target.name,
                    )

        # ── Witness environmental signals ──
        for sig in court.active_signals:
            if sig.location == target.name and sig.is_active:
                sig.witnessed = True

    # ── Public API: Oracle chooses silence ──

    @classmethod
    def record_silence(cls, court: CourtState, kingdom: ok.KingdomState):
        """
        Record that the Oracle chose silence when a decree was expected.

        Silence is never neutral.
        """
        court.inner_state.consecutive_silence_ticks += 1
        court.inner_state.total_silence_ticks += 1
        court.oracle_identity.record_silence()

        # All present agents remember the silence
        present = CourtDecreeGenerator._agents_at_location(
            court, kingdom, court.current_location
        )
        for aid in present:
            agent = court.agents.get(aid)
            if agent:
                # Low-trust agents: silence breeds paranoia
                if agent.trust < 40:
                    agent.add_memory(
                        tick=kingdom.tick,
                        memory_type=MemoryType.IMMEDIATE,
                        category="silence_witnessed",
                        description="The Oracle remained silent.",
                        intensity=-1.0,
                        location=court.current_location.name,
                    )
                else:
                    # High-trust agents: silence is mystifying
                    agent.add_memory(
                        tick=kingdom.tick,
                        memory_type=MemoryType.IMMEDIATE,
                        category="silence_witnessed",
                        description="The Oracle chose silence.",
                        intensity=0.3,
                        location=court.current_location.name,
                    )

    # ── Public API: Oracle issues a decree (court-side bookkeeping) ──

    @classmethod
    def record_decree(cls, court: CourtState, kingdom: ok.KingdomState,
                      option: CourtDecreeOption):
        """
        Record court-side effects of a decree.

        The world-layer propagation (PropagationEngine) is handled
        separately.  This method handles social memory and court
        disposition effects only.
        """
        court.inner_state.consecutive_silence_ticks = 0
        decree_record = ok.DecreeRecord(
            decree_id=option.speech_option.option_id,
            tick=kingdom.tick,
            text=option.speech_option.text,
            tone=option.speech_option.tone.name,
            mode=option.speech_option.mode.name,
            policy_vector=dict(option.speech_option.policy_vector),
        )
        court.oracle_identity.update_from_decree(decree_record)

        # Append to world-layer decree history so consistency tracking works
        kingdom.decree_history.append(decree_record)

        # All present agents form memories of this decree
        present = CourtDecreeGenerator._agents_at_location(
            court, kingdom, court.current_location
        )
        for aid in present:
            agent = court.agents.get(aid)
            if not agent:
                continue

            # Determine if the decree aligns with the agent's interests
            alignment = CourtDecreeGenerator._agent_option_affinity(
                agent,
                kingdom.characters.get(agent.character_id, ok.Character()),
                option.speech_option,
                kingdom,
            )

            if alignment > 0.5:
                agent.add_memory(
                    tick=kingdom.tick,
                    memory_type=MemoryType.IMMEDIATE,
                    category="decree_supported",
                    description=f"Oracle spoke in my favor: {option.speech_option.text[:40]}",
                    intensity=max(0.5, alignment),
                    decree_id=option.speech_option.option_id,
                    location=court.current_location.name,
                )
                agent.trust = min(100, agent.trust + alignment * 0.3)
            elif alignment < -0.15:
                agent.add_memory(
                    tick=kingdom.tick,
                    memory_type=MemoryType.IMMEDIATE,
                    category="decree_opposed",
                    description=f"Oracle spoke against my interests: {option.speech_option.text[:40]}",
                    intensity=min(-0.5, alignment * 1.5),  # amplified negative
                    decree_id=option.speech_option.option_id,
                    location=court.current_location.name,
                )
                agent.resentment = min(100, agent.resentment + abs(alignment) * 0.4)

            # ── Consistency tracking ──
            # Compare this decree's policy vector with the last few
            recent_decrees = kingdom.decree_history[-5:]
            if len(recent_decrees) >= 3:
                consistency_score = cls._compute_consistency(
                    option.speech_option.policy_vector,
                    [d.policy_vector for d in recent_decrees],
                )
                agent.perceived_consistency = (
                    agent.perceived_consistency * 0.8 + consistency_score * 100.0 * 0.2
                )

            # Decisiveness boost: Oracle spoke, not silence
            agent.perceived_decisiveness = min(100,
                agent.perceived_decisiveness + 1.0
            )

        # ── Promoting agent gets special memory ──
        if option.proposing_agent_id:
            proposer = court.agents.get(option.proposing_agent_id)
            if proposer:
                proposer.add_memory(
                    tick=kingdom.tick,
                    memory_type=MemoryType.REPUTATIONAL,
                    category="proposal_accepted",
                    description="The Oracle chose my counsel.",
                    intensity=3.0,
                    decree_id=option.speech_option.option_id,
                    location=court.current_location.name,
                )
                proposer.trust = min(100, proposer.trust + 2.0)
                proposer.admiration = min(100, proposer.admiration + 1.0)

    @classmethod
    def _compute_consistency(cls, current_vec: Dict[str, float],
                             past_vecs: List[Dict[str, float]]) -> float:
        """
        Measure how consistent the current decree is with recent ones.
        Returns 0–1 (1 = perfectly consistent).
        """
        if not past_vecs:
            return 0.5

        agreements = 0
        total = 0
        for axis, val in current_vec.items():
            if abs(val) < 0.1:
                continue
            for past in past_vecs:
                past_val = past.get(axis, 0.0)
                if abs(past_val) < 0.1:
                    continue
                total += 1
                if val * past_val > 0:  # same sign
                    agreements += 1

        if total == 0:
            return 0.5

        return agreements / total


# ============================================================
# SECTION 15: LOCATION-MODIFIED PROPAGATION
# ============================================================
#
# When a decree is issued through the court layer, location
# multipliers modify the policy vector before it reaches
# the world layer's PropagationEngine.

class CourtPropagationBridge:
    """
    Bridge between court-layer decree selection and world-layer
    propagation.  Applies location multipliers to the decree's
    policy vector before routing to PropagationEngine.

    Same words, different room → different world-layer effects.
    """

    @classmethod
    def propagate_court_decree(cls, court: CourtState,
                               kingdom: ok.KingdomState,
                               option: CourtDecreeOption,
                               rng: ok.SeededRNG) -> list:
        """
        Full court-aware decree propagation:
          1. Apply location multipliers to policy vector
          2. Route through world-layer PropagationEngine
          3. Record court-side social memory
          4. Handle silence if chosen
        """
        if option.is_silence:
            CourtEngine.record_silence(court, kingdom)
            # Silence still has world-layer effects via sacred_silence
            kingdom.belief.sacred_silence_weight = min(
                50.0, kingdom.belief.sacred_silence_weight + 2.0
            )
            return []

        # ── Apply location multipliers ──
        profile = LOCATION_PROFILES[court.current_location]
        modified_option = ok.SpeechOption(
            option_id=option.speech_option.option_id,
            text=option.speech_option.text,
            tone=option.speech_option.tone,
            mode=option.speech_option.mode,
            policy_vector={},
            propagation_magnitude=option.speech_option.propagation_magnitude,
            target_character_id=option.speech_option.target_character_id,
        )

        for axis, value in option.speech_option.policy_vector.items():
            multiplier = profile.decree_multipliers.get(axis, 1.0)
            modified_option.policy_vector[axis] = value * multiplier

        # ── Route to world-layer propagation ──
        events = ok.PropagationEngine.propagate(kingdom, modified_option, rng)

        # ── Court-side bookkeeping ──
        CourtEngine.record_decree(court, kingdom, option)

        return events
