"""
Oracle Kingdom — Deterministic Social Simulation Centered on Belief

A Radio OS plugin game. The player is the Oracle: an entity whose symbolic
speech cascades through a layered kingdom simulation.  No free-form text —
the Oracle selects from system-generated, trait-sculpted dialogue options.
Effects are opaque at the interface but fully traceable in a causal ledger.

Architecture:
  Phase 1 — Seed & determinism, core types, simulation layer skeletons,
            ensemble cast, relationship graph, controller + plugin contract.
  Phase 2 — Propagation engine, event system, Oracle psychology.
  Phase 3 — Multi-kingdom, persistence (Cold/Hot layers), web UI.
  Phase 4 — Closure systems: Causal Ledger, Inter-Kingdom Influence,
            Ritualized Absence Reconstruction.
  Phase 5 — Structural Memory: Baseline Shifts, Institutional Scar Tissue,
            Era Identity Classification, Power Gradient Recalibration,
            Intergenerational Value Drift.
  Phase 6 — State Coherence: Cross-domain feasibility constraints,
            dampening curves, material collapse consequences,
            recovery pathways.

Design Principles:
  • Deterministic given (seed, Oracle build, player choices, real-time gaps).
  • Lazy evaluation — neighbouring realms and historical ticks are computed
    on demand from the seed, never eagerly.
  • LLM is presentation-only (Hot Layer narrative extraction, inner monologue
    prose).  The Cold Layer is pure math.
  • Structural robustness with dynamic sensitivity — collapse is possible,
    not guaranteed.
  • Causal traceability — every outcome can be inspected back to its cause
    via the formal CausalLedger.
"""

from __future__ import annotations

# ── stdlib ──────────────────────────────────────────────────
import hashlib
import json
import math
import os
import queue
import random
import sqlite3
import threading
import time
import uuid
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import (
    Any, Callable, Dict, FrozenSet, List, Optional,
    Set, Tuple, Union,
)

# ── Debug gate ──────────────────────────────────────────────
OK_DEBUG: bool = os.environ.get("OK_DEBUG", "").strip() in ("1", "true", "yes")

def _dbg(*a, **kw):
    if OK_DEBUG:
        print("[OK]", *a, **kw)

# ============================================================
# PLUGIN METADATA
# ============================================================

IS_FEED = False
PLUGIN_NAME = "Oracle Kingdom"
PLUGIN_DESC = "Deterministic socio-political belief simulator"

FEED_DEFAULTS: Dict[str, Any] = {}  # no feed config — widget-only


# ============================================================
# SECTION 1: DETERMINISM INFRASTRUCTURE
# ============================================================

class SeededRNG:
    """
    Wrapper around random.Random that enforces determinism.

    Every sub-system derives its own SeededRNG from the master seed so that
    evaluation order between independent systems cannot break reproducibility.

    Usage:
        master = SeededRNG(42)
        physical_rng  = master.fork("physical_layer")
        social_rng    = master.fork("social_layer")

    Fork keys are hashed together with the parent state so results are
    independent and reproducible regardless of call order between forks.
    """

    def __init__(self, seed: int):
        self._seed = seed
        self._rng = random.Random(seed)

    # ---- delegation to stdlib Random ----------------------------
    def random(self) -> float:
        return self._rng.random()

    def randint(self, a: int, b: int) -> int:
        return self._rng.randint(a, b)

    def uniform(self, a: float, b: float) -> float:
        return self._rng.uniform(a, b)

    def gauss(self, mu: float, sigma: float) -> float:
        return self._rng.gauss(mu, sigma)

    def choice(self, seq):
        return self._rng.choice(seq)

    def choices(self, population, weights=None, k=1):
        return self._rng.choices(population, weights=weights, k=k)

    def shuffle(self, seq):
        self._rng.shuffle(seq)

    def sample(self, population, k):
        return self._rng.sample(population, k)

    # ---- deterministic forking ----------------------------------
    def fork(self, namespace: str) -> "SeededRNG":
        """Create a child RNG whose stream is independent of this one."""
        h = hashlib.sha256(f"{self._seed}:{namespace}".encode()).digest()
        child_seed = int.from_bytes(h[:8], "big")
        return SeededRNG(child_seed)

    @property
    def seed(self) -> int:
        return self._seed

    def get_state(self):
        return self._rng.getstate()

    def set_state(self, state):
        self._rng.setstate(state)


# ============================================================
# SECTION 2: TIME SYSTEM
# ============================================================

@dataclass
class TimeConfig:
    """
    Player-configurable real-time → world-time conversion.

    Spec §27-30:  The time scale is a foundational structural parameter.
    It determines character aging speed, generational turnover pace,
    institutional evolution speed, cultural drift velocity, and
    structural decay / growth tempo.
    """
    # How many in-game days pass per real-world second of absence.
    # At creation the player picks a preset; we store the resulting ratio.
    #
    # Preset examples (stored as world_days_per_real_second):
    #   "1 real day  = 1 game day"   → 1/86400   ≈ 0.0000116
    #   "1 real week = 1 game year"  → 365/604800 ≈ 0.000604
    #   "1 real month= 1 game year"  → 365/2592000≈ 0.000141
    #   "1 real year = 1 game year"  → 365/31536000≈0.0000116
    #
    world_days_per_real_second: float = 365.0 / 604800.0  # default: 1 week = 1 year

    # Tick granularity when the player IS present and the sim advances live.
    # One tick = one in-game day.
    days_per_tick: int = 1

    days_per_year: int = 365

    def real_seconds_to_world_days(self, seconds: float) -> float:
        """Convert a real-time gap into in-game days elapsed."""
        return seconds * self.world_days_per_real_second

    def world_days_to_years(self, days: float) -> float:
        return days / self.days_per_year

    # convenience
    def world_days_to_ticks(self, days: float) -> int:
        return max(1, int(days / self.days_per_tick))

    def to_dict(self) -> dict:
        return {
            "world_days_per_real_second": self.world_days_per_real_second,
            "days_per_tick": self.days_per_tick,
            "days_per_year": self.days_per_year,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TimeConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ============================================================
# SECTION 3: ORACLE BUILD (Character Creation)
# ============================================================

# Spec §39: Core trait axes — player allocates a finite point pool.
ORACLE_TRAITS = [
    "clarity",        # reduces interpretation distortion
    "conviction",     # increases propagation magnitude
    "empathy",        # modifies social-layer sensitivity
    "severity",       # amplifies enforcement / punishment vectors
    "ambition",       # influences growth-seeking policy bias
    "humility",       # dampens ego drift
    "self_belief",    # stabilises inner monologue under pressure
    "doubt",          # amplifies internal distortion
    "paranoia",       # biases threat perception
    "charisma",       # widens propagation reach
]

ORACLE_TRAIT_POINT_POOL = 250  # spread across 10 traits (avg 25 each, range 5-50)
ORACLE_TRAIT_MIN = 5
ORACLE_TRAIT_MAX = 50


@dataclass
class OracleBuild:
    """
    The Oracle's immutable origin build + mutable psychological state.

    Origin traits are set at character creation and never change.
    Drifted traits evolve each tick based on outcomes and absence.
    """
    # ---- immutable origin (set at creation) --------------------
    traits: Dict[str, float] = field(default_factory=dict)

    # ---- mutable psychological state ---------------------------
    drifted_traits: Dict[str, float] = field(default_factory=dict)

    # Inner-monologue emotional accumulators (spec §38, §40)
    ego: float = 0.0
    stress: float = 0.0
    hope: float = 0.0
    dread: float = 0.0

    # Trajectory bias accumulator (spec §43)
    # Maps tone_id → cumulative usage weight.  Higher = more available.
    trajectory: Dict[str, float] = field(default_factory=dict)

    # ---- creation helpers --------------------------------------
    @classmethod
    def from_allocation(cls, allocation: Dict[str, int]) -> "OracleBuild":
        """Validate and build from a player's point allocation."""
        total = sum(allocation.values())
        if total != ORACLE_TRAIT_POINT_POOL:
            raise ValueError(
                f"Trait points must sum to {ORACLE_TRAIT_POINT_POOL}, got {total}"
            )
        for name, val in allocation.items():
            if name not in ORACLE_TRAITS:
                raise ValueError(f"Unknown trait: {name}")
            if not (ORACLE_TRAIT_MIN <= val <= ORACLE_TRAIT_MAX):
                raise ValueError(
                    f"Trait '{name}' value {val} outside [{ORACLE_TRAIT_MIN}, {ORACLE_TRAIT_MAX}]"
                )
        traits = {t: float(allocation.get(t, 25)) for t in ORACLE_TRAITS}
        return cls(traits=traits, drifted_traits=dict(traits))

    @classmethod
    def random_build(cls, rng: SeededRNG) -> "OracleBuild":
        """Generate a procedural Oracle build (used for AI Oracles in neighbours)."""
        alloc: Dict[str, int] = {}
        remaining = ORACLE_TRAIT_POINT_POOL
        traits_left = list(ORACLE_TRAITS)
        rng_inner = rng.fork("oracle_build")
        for i, t in enumerate(traits_left):
            if i == len(traits_left) - 1:
                val = remaining
            else:
                avg_remaining = remaining / (len(traits_left) - i)
                val = int(rng_inner.gauss(avg_remaining, 6))
            val = max(ORACLE_TRAIT_MIN, min(ORACLE_TRAIT_MAX, val))
            val = min(val, remaining - ORACLE_TRAIT_MIN * (len(traits_left) - i - 1))
            val = max(val, remaining - ORACLE_TRAIT_MAX * (len(traits_left) - i - 1))
            alloc[t] = val
            remaining -= val
        return cls.from_allocation(alloc)

    # ---- drift mechanics (spec §40) ----------------------------
    def apply_drift(self, outcome_vector: Dict[str, float], absence_days: float = 0.0):
        """
        Shift drifted_traits based on recent outcomes and absence.

        outcome_vector maps trait names → signed pressure.
        Absence interacts with the build: e.g. high doubt + long silence
        increases doubt drift; high self_belief dampens it.
        """
        absence_factor = 1.0 + math.log1p(absence_days) * 0.05

        for trait in ORACLE_TRAITS:
            base = self.traits[trait]
            current = self.drifted_traits.get(trait, base)
            pressure = outcome_vector.get(trait, 0.0)

            # Traits closer to their origin resist drift (rubber-band)
            delta_from_origin = current - base
            rubber_band = -delta_from_origin * 0.02

            shift = (pressure + rubber_band) * absence_factor
            new_val = max(1.0, min(99.0, current + shift))
            self.drifted_traits[trait] = new_val

    def effective(self, trait: str) -> float:
        """Current effective value of a trait (drifted)."""
        return self.drifted_traits.get(trait, self.traits.get(trait, 25.0))

    # ---- serialisation -----------------------------------------
    def to_dict(self) -> dict:
        return {
            "traits": dict(self.traits),
            "drifted_traits": dict(self.drifted_traits),
            "ego": self.ego,
            "stress": self.stress,
            "hope": self.hope,
            "dread": self.dread,
            "trajectory": dict(self.trajectory),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OracleBuild":
        ob = cls()
        ob.traits = d.get("traits", {})
        ob.drifted_traits = d.get("drifted_traits", dict(ob.traits))
        ob.ego = d.get("ego", 0.0)
        ob.stress = d.get("stress", 0.0)
        ob.hope = d.get("hope", 0.0)
        ob.dread = d.get("dread", 0.0)
        ob.trajectory = d.get("trajectory", {})
        return ob


# ============================================================
# SECTION 4: SIMULATION LAYERS — Variable Containers
# ============================================================
#
# Each layer is a plain data container holding the continuous variables
# that the simulation engine ticks forward.  Cross-layer coupling is
# handled by the engine, not inside the containers.
#
# Spec §2: Four interlocking layers.
#   D influences B,C.  B,C influence A.  A feeds back into B.

@dataclass
class PhysicalLayer:
    """
    Layer A — the material world.

    All values normalised to 0–100 unless noted.
    """
    food_production: float = 50.0       # agricultural output
    food_stores: float = 60.0           # buffer (absolute, in "days of supply")
    infrastructure: float = 50.0        # roads, buildings, aqueducts
    trade_volume: float = 40.0          # external commerce throughput
    trade_balance: float = 0.0          # signed: positive = surplus
    labor_pool: float = 50.0            # available workforce
    labor_allocation: Dict[str, float] = field(default_factory=lambda: {
        "agriculture": 0.40,
        "craft":       0.20,
        "military":    0.15,
        "religion":    0.10,
        "governance":  0.10,
        "idle":        0.05,
    })
    resource_pressure: float = 0.0      # scarcity signal (0 = abundance, 100 = famine)
    treasury: float = 1000.0            # kingdom currency (absolute)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "PhysicalLayer":
        obj = cls()
        for k, v in d.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj


@dataclass
class SocialLayer:
    """
    Layer B — the human fabric.
    """
    cohesion: float = 60.0              # social unity
    class_tension: float = 20.0         # inequality strain
    cultural_confidence: float = 50.0   # collective identity strength
    literacy: float = 30.0              # communication efficiency
    fear_level: float = 10.0            # populace anxiety
    hope_level: float = 50.0            # collective optimism
    rumor_strength: float = 5.0         # competing-narrative noise floor
    # Faction influence shares (must sum to ~1.0, keyed by faction_id)
    faction_influence: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "SocialLayer":
        obj = cls()
        for k, v in d.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj


@dataclass
class PoliticalLayer:
    """
    Layer C — power and governance.
    """
    power_concentration: float = 50.0   # 0=distributed, 100=absolute
    legitimacy: float = 65.0            # perceived right to rule
    enforcement_capacity: float = 50.0  # ability to impose law
    law_rigidity: float = 40.0          # resistance to legal change
    corruption: float = 15.0
    institutional_strength: float = 50.0  # durability of offices/roles
    external_threat: float = 10.0       # perceived danger from neighbours

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "PoliticalLayer":
        obj = cls()
        for k, v in d.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj


@dataclass
class BeliefLayer:
    """
    Layer D — the Oracle's domain.

    The Oracle primarily interacts here.  D influences B and C.
    """
    public_faith: float = 65.0          # trust in the Oracle
    myth_accumulation: float = 0.0      # cultural weight of past decrees
    interpretation_divergence: float = 5.0  # how much factions disagree on meaning
    rumor_distortion: float = 5.0       # noise between Oracle → population
    sacred_silence_weight: float = 0.0  # accumulated pressure from Oracle absence
    cultural_memory_strength: float = 50.0  # how strongly old decrees persist

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "BeliefLayer":
        obj = cls()
        for k, v in d.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj


# ============================================================
# SECTION 5: FACTIONS
# ============================================================

class FactionArchetype(Enum):
    """Base archetypes — every kingdom spawns one of each."""
    RELIGIOUS = auto()     # temple / priesthood
    MERCHANT = auto()      # guilds / traders
    MILITARY = auto()      # guard / army
    SCHOLARLY = auto()     # scribes / scholars
    POPULIST = auto()      # commoners / farmers

FACTION_ARCHETYPE_NAMES = {
    FactionArchetype.RELIGIOUS: "Temple",
    FactionArchetype.MERCHANT:  "Guild",
    FactionArchetype.MILITARY:  "Guard",
    FactionArchetype.SCHOLARLY: "Academy",
    FactionArchetype.POPULIST:  "Commons",
}


@dataclass
class Faction:
    """
    A persistent power bloc.  Factions are structurally fixed (one per
    archetype) but their internal state is fully dynamic.
    """
    faction_id: str = ""
    name: str = ""
    archetype: FactionArchetype = FactionArchetype.POPULIST

    # Power & influence
    influence: float = 20.0           # share of societal influence (0–100)
    internal_unity: float = 70.0      # cohesion within the faction
    resources: float = 50.0           # material backing

    # Relationship to Oracle
    oracle_loyalty: float = 50.0      # faith in the Oracle specifically
    interpretation_bias: float = 0.0  # how much they skew Oracle speech (-50 to +50)

    # Policy leanings (each -50 to +50 axis)
    policy_axes: Dict[str, float] = field(default_factory=lambda: {
        "expansion_vs_isolation":  0.0,
        "tradition_vs_reform":     0.0,
        "mercy_vs_justice":        0.0,
        "austerity_vs_prosperity": 0.0,
        "faith_vs_reason":         0.0,
    })

    # Agenda priority — what the faction currently wants most
    agenda_priority: str = "stability"  # one of: stability, power, reform, wealth, piety

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, FactionArchetype):
                d[k] = v.name
            else:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Faction":
        obj = cls()
        for k, v in d.items():
            if k == "archetype":
                obj.archetype = FactionArchetype[v]
            elif hasattr(obj, k):
                setattr(obj, k, v)
        return obj


# ============================================================
# SECTION 6: ENSEMBLE CAST (Key Characters)
# ============================================================
#
# Spec §18-22: Archetypal roles with variable instantiation.
# Roles persist across runs; personalities are seed-driven.

class CharacterRole(Enum):
    """Fixed roles that exist in every kingdom."""
    HIGH_PRIEST = auto()       # spiritual authority
    GUILDMASTER = auto()       # economic power
    CAPTAIN_OF_GUARD = auto()  # enforcement arm
    COURT_SCHOLAR = auto()     # interpreter of prophecy
    POPULAR_TRIBUNE = auto()   # voice of the people

ROLE_FACTION_AFFINITY = {
    CharacterRole.HIGH_PRIEST:      FactionArchetype.RELIGIOUS,
    CharacterRole.GUILDMASTER:      FactionArchetype.MERCHANT,
    CharacterRole.CAPTAIN_OF_GUARD: FactionArchetype.MILITARY,
    CharacterRole.COURT_SCHOLAR:    FactionArchetype.SCHOLARLY,
    CharacterRole.POPULAR_TRIBUNE:  FactionArchetype.POPULIST,
}


@dataclass
class Character:
    """
    A key figure in the kingdom's ensemble cast.

    Spec §19: Each character has loyalty, ambition, risk tolerance,
    popularity, and private grievances.  Relationships between characters
    form a graph with trust/rivalry/debt/alignment edges.
    """
    character_id: str = ""
    name: str = ""
    role: CharacterRole = CharacterRole.POPULAR_TRIBUNE
    faction_id: str = ""             # primary faction alignment
    age: int = 35
    alive: bool = True

    # ---- personality (seed-generated, stable across a lifetime) ----
    ambition: float = 50.0           # drive for personal power
    risk_tolerance: float = 50.0     # willingness to gamble
    piety: float = 50.0             # reverence for Oracle / faith
    pragmatism: float = 50.0         # practicality vs idealism
    cruelty: float = 20.0            # willingness to harm
    charisma: float = 50.0           # public persuasion ability

    # ---- dynamic state (changes each tick) -------------------------
    oracle_loyalty: float = 60.0     # personal faith in the Oracle
    public_popularity: float = 50.0
    private_grievances: float = 0.0  # accumulated resentment
    stress: float = 10.0
    health: float = 90.0             # decays with age

    # ---- peak age & aging ----
    peak_age_start: int = 30
    peak_age_end: int = 55

    def is_past_peak(self) -> bool:
        return self.age > self.peak_age_end

    def age_one_year(self, rng: SeededRNG):
        """Apply one year of aging effects."""
        self.age += 1
        if self.age > self.peak_age_end:
            years_past = self.age - self.peak_age_end
            # Accelerating decay: gentle at first, steep after 10+ years past peak
            # year 1 past peak: ~0.5-1.5 health lost
            # year 5 past peak: ~2.5-5.0 health lost
            # year 10 past peak: ~5-10 health lost
            # year 15 past peak: ~8-15 health lost → character likely dead by age ~72
            decay = rng.uniform(0.5, 1.5) * (years_past ** 1.4 / 5.0)
            self.health = max(0.0, self.health - decay)
        if self.health <= 0:
            self.alive = False

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, CharacterRole):
                d[k] = v.name
            else:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Character":
        obj = cls()
        for k, v in d.items():
            if k == "role":
                obj.role = CharacterRole[v]
            elif hasattr(obj, k):
                setattr(obj, k, v)
        return obj


# ---- Relationship Graph ----

class RelationshipType(Enum):
    TRUST = auto()
    RIVALRY = auto()
    DEBT = auto()
    IDEOLOGICAL_ALIGNMENT = auto()


@dataclass
class RelationshipEdge:
    """Directed edge between two characters."""
    from_id: str = ""
    to_id: str = ""
    rel_type: RelationshipType = RelationshipType.TRUST
    weight: float = 0.0   # magnitude (-100 to 100; meaning depends on type)

    def to_dict(self) -> dict:
        return {
            "from_id": self.from_id,
            "to_id": self.to_id,
            "rel_type": self.rel_type.name,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RelationshipEdge":
        return cls(
            from_id=d["from_id"],
            to_id=d["to_id"],
            rel_type=RelationshipType[d["rel_type"]],
            weight=d.get("weight", 0.0),
        )


class RelationshipGraph:
    """
    Spec §19: Edges carry trust, rivalry, debt, ideological alignment.
    Events propagate along this graph.
    """

    def __init__(self):
        self._edges: List[RelationshipEdge] = []

    def add(self, edge: RelationshipEdge):
        self._edges.append(edge)

    def get_edges_from(self, character_id: str) -> List[RelationshipEdge]:
        return [e for e in self._edges if e.from_id == character_id]

    def get_edges_to(self, character_id: str) -> List[RelationshipEdge]:
        return [e for e in self._edges if e.to_id == character_id]

    def get_edge(self, from_id: str, to_id: str, rel_type: RelationshipType) -> Optional[RelationshipEdge]:
        for e in self._edges:
            if e.from_id == from_id and e.to_id == to_id and e.rel_type == rel_type:
                return e
        return None

    def set_weight(self, from_id: str, to_id: str, rel_type: RelationshipType, weight: float):
        edge = self.get_edge(from_id, to_id, rel_type)
        if edge:
            edge.weight = max(-100.0, min(100.0, weight))
        else:
            self.add(RelationshipEdge(from_id, to_id, rel_type, max(-100.0, min(100.0, weight))))

    def to_list(self) -> List[dict]:
        return [e.to_dict() for e in self._edges]

    @classmethod
    def from_list(cls, data: List[dict]) -> "RelationshipGraph":
        g = cls()
        for d in data:
            g.add(RelationshipEdge.from_dict(d))
        return g


# ============================================================
# SECTION 7: EVENT SYSTEM
# ============================================================
#
# Spec §20, §44-49: Non-scripted, threshold-triggered, severity-weighted.

class EventDomain(Enum):
    SOCIAL = auto()
    POLITICAL = auto()
    ECONOMIC = auto()
    RELIGIOUS = auto()
    MILITARY = auto()
    CULTURAL = auto()
    ENVIRONMENTAL = auto()
    DIPLOMATIC = auto()


class EventKind(Enum):
    """Spec §20: event archetypes."""
    PETITION = auto()
    ACCUSATION = auto()
    SCANDAL = auto()
    SHORTAGE = auto()
    DISCOVERY = auto()
    SCHISM = auto()
    MILITARY_DEFIANCE = auto()
    SUCCESSION = auto()
    TRADE_DISRUPTION = auto()
    CULTURAL_SHIFT = auto()
    NATURAL_DISASTER = auto()
    REFORM_MOVEMENT = auto()
    RENAISSANCE = auto()
    DIPLOMATIC_INCIDENT = auto()
    COMPOUND = auto()          # merged from multiple events
    TERMINAL = auto()          # Phase 7: terminal resolution transformation


@dataclass
class SimEvent:
    """
    Atomic event record.

    Spec §44: severity + urgency scoring.
    Spec §8: caused_by chain for causal traceability.
    """
    event_id: str = ""
    kind: EventKind = EventKind.PETITION
    domain: EventDomain = EventDomain.SOCIAL
    tick: int = 0
    severity: float = 0.0        # 0-100 structural impact
    urgency: float = 0.0         # 0-100 time sensitivity
    description: str = ""
    involved_actors: List[str] = field(default_factory=list)  # character_ids
    involved_factions: List[str] = field(default_factory=list)
    policy_vector: Dict[str, float] = field(default_factory=dict)
    caused_by: Optional[str] = None  # parent event_id
    resolved: bool = False
    resolution_tick: Optional[int] = None
    player_saw: bool = False         # has the Oracle inspected this?

    # ---- compound event source tracking ----
    source_events: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, (EventKind, EventDomain)):
                d[k] = v.name
            else:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SimEvent":
        obj = cls()
        for k, v in d.items():
            if k == "kind":
                obj.kind = EventKind[v]
            elif k == "domain":
                obj.domain = EventDomain[v]
            elif hasattr(obj, k):
                setattr(obj, k, v)
        return obj


class EventQueue:
    """
    Priority queue for active (unresolved) events.

    Spec §45: on awakening, events are presented in descending priority
    (severity × urgency).
    """

    def __init__(self):
        self._events: List[SimEvent] = []

    def push(self, event: SimEvent):
        self._events.append(event)
        self._events.sort(key=lambda e: e.severity * e.urgency, reverse=True)

    def pop(self) -> Optional[SimEvent]:
        return self._events.pop(0) if self._events else None

    def peek(self) -> Optional[SimEvent]:
        return self._events[0] if self._events else None

    def pending(self) -> List[SimEvent]:
        """All unresolved events, highest priority first."""
        return list(self._events)

    def __len__(self) -> int:
        return len(self._events)


# ============================================================
# SECTION 7.5: CAUSAL LEDGER (Closure System 1)
# ============================================================
#
# The spine of Oracle Kingdom.  Every variable mutation is recorded
# as a directed edge: source → target with variable name, delta, tick.
#
# This answers "Why did legitimacy collapse?" with a complete trace.
# Powers: Hot-layer reconstruction narration, timeline inspection UI,
#         deterministic replay debugging, root-cause analysis.

class CausalEdgeType(Enum):
    """What produced this mutation."""
    DECREE = auto()          # Oracle speech act
    EVENT = auto()           # threshold-triggered event
    RIPPLE = auto()          # propagating wave
    THRESHOLD = auto()       # threshold crossing that spawned an event
    COMPOUND = auto()        # compound event synthesis
    COUPLING = auto()        # cross-layer coupling (D→B, B→A, etc.)
    ABSENCE = auto()         # drift during Oracle absence
    SUCCESSION = auto()      # character death / replacement
    FACTION = auto()         # faction dynamics shift
    NEIGHBOUR = auto()       # inter-kingdom influence


@dataclass
class CausalEdge:
    """
    One directed edge in the causal graph.

    source_type + source_id = what caused the change.
    target_type + target_id = what was changed.
    variable = which specific variable was mutated.
    delta = signed magnitude of the change.
    tick = when it happened.
    """
    source_type: str          # "decree" | "event" | "ripple" | "threshold" | "coupling" | etc.
    source_id: str            # id of the decree, event, ripple, etc.
    target_type: str          # "kingdom" | "character" | "faction" | "layer"
    target_id: str            # kingdom_id, character_id, faction_id, or layer name
    variable: str             # e.g. "food_production", "oracle_loyalty", "legitimacy"
    delta: float              # signed change
    tick: int                 # world tick when this edge was created
    metadata: Dict[str, Any] = field(default_factory=dict)  # optional context

    def to_dict(self) -> dict:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "variable": self.variable,
            "delta": self.delta,
            "tick": self.tick,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CausalEdge":
        return cls(
            source_type=d["source_type"],
            source_id=d["source_id"],
            target_type=d["target_type"],
            target_id=d["target_id"],
            variable=d["variable"],
            delta=d["delta"],
            tick=d["tick"],
            metadata=d.get("metadata", {}),
        )


class CausalLedger:
    """
    Append-only causal edge graph.

    Every mutation to a kingdom variable, character state, or faction
    field is recorded here.  The ledger is the single source of truth
    for "why did X happen?"

    Query patterns:
      - trace_variable(var, tick_range) → all edges that touched `var`
      - trace_source(source_id) → all effects of a decree/event/ripple
      - trace_target(target_id) → all causes that affected a target
      - causal_chain(event_id) → walk backward to root causes
    """

    def __init__(self):
        self._edges: List[CausalEdge] = []
        # Index for fast lookup
        self._by_variable: Dict[str, List[int]] = {}    # variable → edge indices
        self._by_source: Dict[str, List[int]] = {}      # source_id → edge indices
        self._by_target: Dict[str, List[int]] = {}      # target_id → edge indices
        self._by_tick: Dict[int, List[int]] = {}         # tick → edge indices

    def record(self, edge: CausalEdge):
        """Append a causal edge and update indices."""
        idx = len(self._edges)
        self._edges.append(edge)

        self._by_variable.setdefault(edge.variable, []).append(idx)
        self._by_source.setdefault(edge.source_id, []).append(idx)
        self._by_target.setdefault(edge.target_id, []).append(idx)
        self._by_tick.setdefault(edge.tick, []).append(idx)

    def record_delta(self, source_type: str, source_id: str,
                     target_type: str, target_id: str,
                     variable: str, delta: float, tick: int,
                     metadata: Optional[Dict[str, Any]] = None):
        """Convenience: record an edge from components."""
        if abs(delta) < 1e-9:
            return  # skip zero-deltas to keep ledger lean
        self.record(CausalEdge(
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            variable=variable,
            delta=delta,
            tick=tick,
            metadata=metadata or {},
        ))

    # ---- query API ----

    def trace_variable(self, variable: str,
                       tick_start: Optional[int] = None,
                       tick_end: Optional[int] = None) -> List[CausalEdge]:
        """All edges that mutated `variable`, optionally within a tick range."""
        indices = self._by_variable.get(variable, [])
        edges = [self._edges[i] for i in indices]
        if tick_start is not None:
            edges = [e for e in edges if e.tick >= tick_start]
        if tick_end is not None:
            edges = [e for e in edges if e.tick <= tick_end]
        return edges

    def trace_source(self, source_id: str) -> List[CausalEdge]:
        """All effects caused by `source_id`."""
        indices = self._by_source.get(source_id, [])
        return [self._edges[i] for i in indices]

    def trace_target(self, target_id: str) -> List[CausalEdge]:
        """All causes that affected `target_id`."""
        indices = self._by_target.get(target_id, [])
        return [self._edges[i] for i in indices]

    def edges_at_tick(self, tick: int) -> List[CausalEdge]:
        """All edges recorded at a specific tick."""
        indices = self._by_tick.get(tick, [])
        return [self._edges[i] for i in indices]

    def causal_chain(self, source_id: str, max_depth: int = 10) -> List[CausalEdge]:
        """
        Walk backward from a source_id through the causal graph.

        Follows: source_id → its effects → those effects' sources → ...
        Returns all edges encountered (BFS, capped at max_depth).
        """
        visited: Set[str] = set()
        chain: List[CausalEdge] = []
        frontier = [source_id]

        for _ in range(max_depth):
            next_frontier: List[str] = []
            for sid in frontier:
                if sid in visited:
                    continue
                visited.add(sid)
                effects = self.trace_source(sid)
                chain.extend(effects)
                # Each effect's target might be the source of further edges
                for e in effects:
                    next_frontier.append(e.target_id)
            frontier = next_frontier
            if not frontier:
                break

        return chain

    def variable_history(self, variable: str, last_n: int = 50) -> List[Dict[str, Any]]:
        """
        Produce a timeline-friendly summary of a variable's mutations.

        Returns: [{tick, delta, source_type, source_id}, ...]
        """
        edges = self.trace_variable(variable)
        edges.sort(key=lambda e: e.tick)
        return [
            {
                "tick": e.tick,
                "delta": e.delta,
                "source_type": e.source_type,
                "source_id": e.source_id,
                "metadata": e.metadata,
            }
            for e in edges[-last_n:]
        ]

    def explain(self, variable: str, tick: Optional[int] = None) -> str:
        """
        Human-readable explanation of why a variable has its current value.

        Aggregates recent causal edges and produces a summary string.
        (Cold Layer data — the Hot Layer LLM can turn this into prose.)
        """
        edges = self.trace_variable(variable)
        if tick is not None:
            edges = [e for e in edges if e.tick <= tick]
        if not edges:
            return f"No causal history for '{variable}'."

        edges.sort(key=lambda e: e.tick, reverse=True)
        recent = edges[:10]

        lines = [f"Causal trace for '{variable}' (last {len(recent)} mutations):"]
        for e in recent:
            sign = "+" if e.delta > 0 else ""
            lines.append(
                f"  tick {e.tick}: {sign}{e.delta:.3f} ← {e.source_type}:{e.source_id}"
            )

        net = sum(e.delta for e in recent)
        lines.append(f"  Net recent change: {'+' if net > 0 else ''}{net:.3f}")
        return "\n".join(lines)

    # ---- serialisation ----

    def to_list(self, last_n: int = 5000) -> List[dict]:
        """Serialise most recent edges (cap to prevent save bloat)."""
        return [e.to_dict() for e in self._edges[-last_n:]]

    @classmethod
    def from_list(cls, data: List[dict]) -> "CausalLedger":
        ledger = cls()
        for d in data:
            ledger.record(CausalEdge.from_dict(d))
        return ledger

    def __len__(self) -> int:
        return len(self._edges)


# ============================================================
# SECTION 7.6: INTER-KINGDOM INFLUENCE ENGINE (Closure System 2)
# ============================================================
#
# Neighbours are NOT simulated tick-by-tick.
# They exert lazy influence via drift vectors.
# Full state materialises ONLY on inspection.

@dataclass
class InterKingdomVector:
    """
    Aggregate influence pressure from a neighbour kingdom.

    Updated lazily — recomputed when the player inspects or
    at wide intervals.  Applied as a lump sum each tick.
    """
    kingdom_id: str = ""
    trade_pressure: float = 0.0       # positive = wants trade, negative = embargo
    cultural_pressure: float = 0.0    # positive = cultural export, negative = cultural resistance
    military_pressure: float = 0.0    # positive = threatening, negative = allied
    myth_pressure: float = 0.0        # positive = competing faith narrative, negative = faith reinforcement
    diplomatic_stance: float = 0.0    # -1 hostile, 0 neutral, +1 friendly

    def to_dict(self) -> dict:
        return {
            "kingdom_id": self.kingdom_id,
            "trade_pressure": self.trade_pressure,
            "cultural_pressure": self.cultural_pressure,
            "military_pressure": self.military_pressure,
            "myth_pressure": self.myth_pressure,
            "diplomatic_stance": self.diplomatic_stance,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "InterKingdomVector":
        obj = cls()
        for k, v in d.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj


class NeighbourInfluenceEngine:
    """
    Lazy inter-kingdom influence system.

    Design:
      1. Each neighbour stores an InterKingdomVector (cheap).
      2. Vectors are recomputed from neighbour seed + elapsed time
         at wide intervals (not every tick).
      3. Every tick, aggregate neighbour vectors are applied to the
         player kingdom as small variable deltas.
      4. Full neighbour state is materialised ONLY when the player
         inspects a neighbour (prevents 5× RAM explosion).

    Influence is bidirectional but asymmetric:
      - Player kingdom's state affects vector drift
      - Neighbour's seed-derived personality determines baseline stance
    """

    # How often (in ticks) to recompute neighbour vectors
    RECOMPUTE_INTERVAL: int = 30

    @classmethod
    def compute_neighbour_vector(cls, neighbour_seed: int,
                                  player_state: KingdomState,
                                  elapsed_ticks: int,
                                  rng: SeededRNG) -> InterKingdomVector:
        """
        Derive influence vector from neighbour seed + player state.

        This is LAZY — we don't simulate the neighbour, we derive
        their stance from their seed personality and the player's
        observable state.
        """
        nrng = rng.fork(f"neighbour_vec_{neighbour_seed}")

        # Seed-derived baseline personality (stable per neighbour)
        baseline_aggression = nrng.uniform(-0.5, 0.8)
        baseline_trade_interest = nrng.uniform(-0.3, 0.7)
        baseline_cultural_export = nrng.uniform(-0.2, 0.5)
        baseline_faith_competition = nrng.uniform(-0.3, 0.6)

        # Player state modulates neighbour behaviour
        # Weak player → neighbours become more aggressive
        player_strength = player_state.health.composite / 100.0
        player_military = player_state.political.enforcement_capacity / 100.0
        player_trade = player_state.physical.trade_volume / 100.0
        player_faith = player_state.belief.public_faith / 100.0

        # Time drift: neighbours evolve slowly (deterministic from seed + tick)
        tick_drift_rng = SeededRNG(neighbour_seed + elapsed_ticks // 100)
        drift = tick_drift_rng.uniform(-0.1, 0.1)

        # Military pressure: high when player is weak, low when strong
        military_pressure = (
            baseline_aggression * 30.0
            + (1.0 - player_strength) * 20.0
            - player_military * 15.0
            + drift * 5.0
        )

        # Trade pressure: mutual benefit when both trade, embargo when isolated
        trade_pressure = (
            baseline_trade_interest * 20.0
            + player_trade * 10.0
            - (1.0 - player_strength) * 5.0
            + drift * 3.0
        )

        # Cultural pressure: strong neighbour culture vs player confidence
        cultural_pressure = (
            baseline_cultural_export * 15.0
            - player_state.social.cultural_confidence * 0.1
            + drift * 4.0
        )

        # Myth pressure: competing faith narratives
        myth_pressure = (
            baseline_faith_competition * 20.0
            - player_faith * 10.0
            + player_state.belief.interpretation_divergence * 0.2
            + drift * 3.0
        )

        # Diplomatic stance: aggregate summary
        diplomatic_stance = max(-1.0, min(1.0,
            -baseline_aggression * 0.5
            + baseline_trade_interest * 0.3
            + player_strength * 0.3
            - 0.1
            + drift
        ))

        return InterKingdomVector(
            kingdom_id=f"neighbour_{neighbour_seed}",
            trade_pressure=trade_pressure,
            cultural_pressure=cultural_pressure,
            military_pressure=military_pressure,
            myth_pressure=myth_pressure,
            diplomatic_stance=diplomatic_stance,
        )

    @classmethod
    def apply_influence(cls, state: KingdomState,
                        vectors: List[InterKingdomVector],
                        ledger: Optional["CausalLedger"] = None,
                        tick: int = 0):
        """
        Apply aggregate neighbour influence to the player kingdom.

        Called every tick.  The vectors themselves are recomputed less
        frequently (every RECOMPUTE_INTERVAL ticks).
        """
        if not vectors:
            return

        # Aggregate all neighbour pressures
        total_military = sum(v.military_pressure for v in vectors)
        total_trade = sum(v.trade_pressure for v in vectors)
        total_cultural = sum(v.cultural_pressure for v in vectors)
        total_myth = sum(v.myth_pressure for v in vectors)

        # Scale by number of neighbours (diminishing returns)
        n = len(vectors)
        scale = 1.0 / (1.0 + math.log(n)) if n > 1 else 1.0

        # Apply to kingdom variables (small per-tick nudges)
        _c = lambda v, lo=0.0, hi=100.0: max(lo, min(hi, v))

        # Military pressure → external_threat + enforcement spending
        # Gate: neighbours don't waste armies threatening a depopulated ruin.
        # Scale military pressure by population significance.
        pop_mil_gate = max(0.0, min(1.0, (state.physical.labor_pool - 10.0) / 30.0))
        mil_delta = total_military * scale * 0.02 * pop_mil_gate
        state.political.external_threat = _c(state.political.external_threat + mil_delta)
        if ledger and abs(mil_delta) > 0.001:
            ledger.record_delta("neighbour", "aggregate_neighbours", "layer", "political",
                                "external_threat", mil_delta, tick)

        # Trade pressure → trade_volume + treasury
        # Gate: trade requires infrastructure to flow through.
        # A kingdom with infra=3 cannot receive trade caravans.
        # Scale neighbour trade influence by infrastructure health.
        infra_gate = max(0.0, min(1.0, (state.physical.infrastructure - 15.0) / 35.0))
        trade_delta = total_trade * scale * 0.015 * infra_gate
        state.physical.trade_volume = _c(state.physical.trade_volume + trade_delta)
        trade_treasury = total_trade * scale * 0.1 * infra_gate
        state.physical.treasury = max(0, state.physical.treasury + trade_treasury)
        if ledger and abs(trade_delta) > 0.001:
            ledger.record_delta("neighbour", "aggregate_neighbours", "layer", "physical",
                                "trade_volume", trade_delta, tick)

        # Cultural pressure → cultural_confidence (inverse)
        cultural_delta = -total_cultural * scale * 0.01
        state.social.cultural_confidence = _c(state.social.cultural_confidence + cultural_delta)
        if ledger and abs(cultural_delta) > 0.001:
            ledger.record_delta("neighbour", "aggregate_neighbours", "layer", "social",
                                "cultural_confidence", cultural_delta, tick)

        # Myth pressure → interpretation_divergence + public_faith erosion
        # Gate: myth pressure requires enough population to sustain
        # competing doctrines.  A hamlet of 10 people has one priest,
        # not a theological battlefield.
        pop_myth_gate = max(0.0, min(1.0, (state.physical.labor_pool - 10.0) / 30.0))
        myth_div_delta = total_myth * scale * 0.008 * pop_myth_gate
        state.belief.interpretation_divergence = _c(state.belief.interpretation_divergence + myth_div_delta)
        myth_faith_delta = -total_myth * scale * 0.005 * pop_myth_gate
        state.belief.public_faith = _c(state.belief.public_faith + myth_faith_delta)
        if ledger and abs(myth_div_delta) > 0.001:
            ledger.record_delta("neighbour", "aggregate_neighbours", "layer", "belief",
                                "interpretation_divergence", myth_div_delta, tick)

    @classmethod
    def should_recompute(cls, tick: int) -> bool:
        """Whether it's time to recompute neighbour vectors."""
        return tick % cls.RECOMPUTE_INTERVAL == 0

    @classmethod
    def recompute_all_vectors(cls, world_state: "WorldState",
                               rng: SeededRNG) -> List[InterKingdomVector]:
        """Recompute influence vectors for all neighbours."""
        vectors: List[InterKingdomVector] = []
        player = world_state.player_kingdom

        for nid, nseed in world_state.neighbour_seeds.items():
            vec = cls.compute_neighbour_vector(
                nseed, player, player.tick, rng.fork(f"nvec_{nid}")
            )
            vec.kingdom_id = nid
            vectors.append(vec)

        return vectors


# ============================================================
# SECTION 7.7: RITUALIZED ABSENCE RECONSTRUCTION (Closure System 3)
# ============================================================
#
# When the Oracle returns after real-time absence, the reconstruction
# is NOT "4,382 ticks processed."
#
# It is a phased ritual:
#   silence → ripples → thresholds → succession → compound → myth → present
#
# Each phase batches ticks, emits summary deltas, and creates
# the "five years passed" experience.

@dataclass
class ReconstructionPhaseResult:
    """Summary of what happened during one reconstruction phase."""
    phase_name: str
    phase_description: str
    ticks_processed: int
    new_events_count: int
    events_summary: List[str]         # short descriptions of notable events
    variable_crossings: List[str]     # thresholds crossed during this phase
    health_before: float
    health_after: float
    health_trend: str                 # "rising", "stable", "declining"
    years_elapsed: float
    key_changes: Dict[str, float]     # variable_name → net delta this phase

    def to_dict(self) -> dict:
        return {
            "phase_name": self.phase_name,
            "phase_description": self.phase_description,
            "ticks_processed": self.ticks_processed,
            "new_events_count": self.new_events_count,
            "events_summary": self.events_summary,
            "variable_crossings": self.variable_crossings,
            "health_before": self.health_before,
            "health_after": self.health_after,
            "health_trend": self.health_trend,
            "years_elapsed": self.years_elapsed,
            "key_changes": self.key_changes,
        }


# Phase definitions — order matters.
# Each phase has a narrative label, a description, and a fraction
# of total reconstruction ticks it processes.

RECONSTRUCTION_PHASES = [
    {
        "name": "silence",
        "description": "Silence weighs upon the kingdom...",
        "fraction": 0.05,   # first 5% — just the immediate aftermath
    },
    {
        "name": "ripples",
        "description": "Ripples from past decrees begin to surface...",
        "fraction": 0.15,   # next 15% — existing ripples play out
    },
    {
        "name": "thresholds",
        "description": "Thresholds are crossed. Events cascade...",
        "fraction": 0.25,   # the bulk of event generation
    },
    {
        "name": "succession",
        "description": "Generations turn. The old make way for the new...",
        "fraction": 0.20,   # character aging, deaths, replacements
    },
    {
        "name": "compound",
        "description": "Compound crises form from converging pressures...",
        "fraction": 0.15,   # compound event synthesis
    },
    {
        "name": "myth",
        "description": "Myths harden. Memory crystallises...",
        "fraction": 0.10,   # decree memory evolution
    },
    {
        "name": "present",
        "description": "The present state stabilises. The Oracle awakens.",
        "fraction": 0.10,   # final settling
    },
]


class ReconstructionStateMachine:
    """
    Phases absence reconstruction into a ritualized experience.

    Instead of "processing N ticks" in a single batch, this breaks
    the reconstruction into narrative phases.  Each phase:
      1. Processes a fraction of total ticks
      2. Snapshots state before and after
      3. Detects threshold crossings
      4. Produces a summary suitable for narrative display

    The controller calls `next_phase()` repeatedly, pushing each
    phase result to the UI.  The player experiences time passing
    as a structured revelation.
    """

    # Threshold definitions for crossing detection
    VARIABLE_THRESHOLDS = {
        "food_stores": [10, 20, 40, 60, 80],
        "resource_pressure": [25, 50, 75],
        "public_faith": [20, 40, 60, 80],
        "legitimacy": [25, 50, 75],
        "class_tension": [30, 50, 70],
        "cohesion": [25, 50, 75],
        "enforcement_capacity": [25, 50, 75],
        "corruption": [25, 50, 75],
        "external_threat": [25, 50, 75],
        "interpretation_divergence": [15, 30, 50],
        "cultural_confidence": [25, 50, 75],
    }

    def __init__(self, world_state: "WorldState", total_ticks: int):
        self.world_state = world_state
        self.total_ticks = total_ticks
        self.ticks_consumed: int = 0
        self.phase_index: int = 0
        self.phase_results: List[ReconstructionPhaseResult] = []
        self.complete: bool = False

    @property
    def current_phase(self) -> Optional[dict]:
        if self.phase_index < len(RECONSTRUCTION_PHASES):
            return RECONSTRUCTION_PHASES[self.phase_index]
        return None

    @property
    def progress(self) -> float:
        """0.0 to 1.0"""
        return self.ticks_consumed / max(self.total_ticks, 1)

    def next_phase(self) -> Optional[ReconstructionPhaseResult]:
        """
        Process the next reconstruction phase.

        Returns the phase result, or None if reconstruction is complete.
        """
        phase_def = self.current_phase
        if phase_def is None or self.complete:
            self.complete = True
            return None

        # How many ticks this phase covers
        phase_ticks = max(1, int(self.total_ticks * phase_def["fraction"]))
        # Don't overshoot
        remaining = self.total_ticks - self.ticks_consumed
        phase_ticks = min(phase_ticks, remaining)

        if phase_ticks <= 0:
            self.phase_index += 1
            if self.phase_index >= len(RECONSTRUCTION_PHASES):
                self.complete = True
            return self.next_phase()

        # Snapshot state before
        kingdom = self.world_state.player_kingdom
        health_before = kingdom.health.composite
        vars_before = self._snapshot_key_variables(kingdom)

        # Run ticks
        rng = SeededRNG(kingdom.seed)
        all_events: List[SimEvent] = []
        for _ in range(phase_ticks):
            events = SimulationEngine.advance_tick(
                kingdom, rng, self.world_state.time_config
            )
            all_events.extend(events)

        # Snapshot state after
        health_after = kingdom.health.composite
        vars_after = self._snapshot_key_variables(kingdom)

        # Detect threshold crossings
        crossings = self._detect_crossings(vars_before, vars_after)

        # Compute key variable deltas
        key_changes: Dict[str, float] = {}
        for var in vars_before:
            delta = vars_after[var] - vars_before[var]
            if abs(delta) > 0.5:  # only report meaningful changes
                key_changes[var] = round(delta, 2)

        # Event summaries (top by severity)
        all_events.sort(key=lambda e: e.severity, reverse=True)
        event_summaries = [e.description[:100] for e in all_events[:5]]

        # Health trend
        if health_after - health_before > 2.0:
            trend = "rising"
        elif health_after - health_before < -2.0:
            trend = "declining"
        else:
            trend = "stable"

        # Years elapsed in this phase
        days_this_phase = phase_ticks * self.world_state.time_config.days_per_tick
        years_elapsed = days_this_phase / self.world_state.time_config.days_per_year

        result = ReconstructionPhaseResult(
            phase_name=phase_def["name"],
            phase_description=phase_def["description"],
            ticks_processed=phase_ticks,
            new_events_count=len(all_events),
            events_summary=event_summaries,
            variable_crossings=crossings,
            health_before=round(health_before, 1),
            health_after=round(health_after, 1),
            health_trend=trend,
            years_elapsed=round(years_elapsed, 2),
            key_changes=key_changes,
        )

        self.ticks_consumed += phase_ticks
        self.phase_results.append(result)
        self.phase_index += 1

        if self.phase_index >= len(RECONSTRUCTION_PHASES) or self.ticks_consumed >= self.total_ticks:
            self.complete = True

        return result

    def run_all_phases(self) -> List[ReconstructionPhaseResult]:
        """Run all phases sequentially. Returns all phase results."""
        results: List[ReconstructionPhaseResult] = []
        while not self.complete:
            result = self.next_phase()
            if result:
                results.append(result)
        return results

    def summary(self) -> Dict[str, Any]:
        """Produce an aggregate summary of the entire reconstruction."""
        if not self.phase_results:
            return {"status": "no_reconstruction"}

        total_events = sum(r.new_events_count for r in self.phase_results)
        total_years = sum(r.years_elapsed for r in self.phase_results)

        # Aggregate key changes across all phases
        aggregate_changes: Dict[str, float] = {}
        for r in self.phase_results:
            for var, delta in r.key_changes.items():
                aggregate_changes[var] = aggregate_changes.get(var, 0.0) + delta

        # Collect all threshold crossings
        all_crossings: List[str] = []
        for r in self.phase_results:
            all_crossings.extend(r.variable_crossings)

        return {
            "status": "complete",
            "total_ticks": self.ticks_consumed,
            "total_years": round(total_years, 1),
            "total_events": total_events,
            "phases": [r.to_dict() for r in self.phase_results],
            "aggregate_changes": {k: round(v, 2) for k, v in aggregate_changes.items()},
            "threshold_crossings": all_crossings,
            "health_start": self.phase_results[0].health_before,
            "health_end": self.phase_results[-1].health_after,
        }

    # ---- internal helpers ----

    def _snapshot_key_variables(self, kingdom: KingdomState) -> Dict[str, float]:
        """Snapshot all threshold-tracked variables."""
        return {
            "food_stores": kingdom.physical.food_stores,
            "resource_pressure": kingdom.physical.resource_pressure,
            "public_faith": kingdom.belief.public_faith,
            "legitimacy": kingdom.political.legitimacy,
            "class_tension": kingdom.social.class_tension,
            "cohesion": kingdom.social.cohesion,
            "enforcement_capacity": kingdom.political.enforcement_capacity,
            "corruption": kingdom.political.corruption,
            "external_threat": kingdom.political.external_threat,
            "interpretation_divergence": kingdom.belief.interpretation_divergence,
            "cultural_confidence": kingdom.social.cultural_confidence,
        }

    def _detect_crossings(self, before: Dict[str, float],
                          after: Dict[str, float]) -> List[str]:
        """Detect which thresholds were crossed between before and after snapshots."""
        crossings: List[str] = []
        for var, thresholds in self.VARIABLE_THRESHOLDS.items():
            v_before = before.get(var, 50.0)
            v_after = after.get(var, 50.0)
            for thresh in thresholds:
                # Crossed upward
                if v_before < thresh <= v_after:
                    crossings.append(f"{var} rose above {thresh}")
                # Crossed downward
                elif v_before >= thresh > v_after:
                    crossings.append(f"{var} fell below {thresh}")
        return crossings


# ============================================================
# SECTION 7.8: STRUCTURAL MEMORY — THE HISTORY-SHAPING LAYER
#              (Phase 5: What makes a kingdom *become* something)
# ============================================================
#
# Five systems that transform Oracle Kingdom from a reversible
# oscillator into a historically-shaped generational engine:
#
#   1. Baseline Shifts  — irreversible equilibrium mutations.
#   2. Institutional Scars — residual cost/benefit from resolved crises.
#   3. Era Identity — structural self-classification with mechanical modifiers.
#   4. Power Gradient — long-term regional hierarchy recalibration.
#   5. Intergenerational Value Drift — biased personality inheritance.
#
# None of these are cosmetic.  Each mechanically alters how the
# simulation behaves.  Together they create "the kingdom became
# something" — not just "the kingdom changed."


# ── 1. Baseline Shifts ────────────────────────────────────────
#
# When a variable holds above/below a threshold for N consecutive
# years, the *resting equilibrium* of related variables shifts
# permanently.  Even if the cause reverses, the kingdom never
# returns to its original state.  This is structural memory.

@dataclass
class BaselineShift:
    """
    A permanent, irreversible modification to a variable's equilibrium.

    Once recorded, a baseline shift modifies the effective value of
    a target variable forever.  Shifts accumulate — a kingdom that
    endured three famines has a different economic floor than one
    that never suffered.
    """
    shift_id: str
    trigger_variable: str        # what was sustained (e.g. "class_tension")
    trigger_threshold: float     # the threshold that was sustained
    trigger_direction: str       # "above" or "below"
    years_sustained: int         # how long the condition held
    tick_applied: int            # when the shift crystallised
    target_variable: str         # what gets permanently altered
    delta: float                 # signed permanent modifier
    description: str             # human-readable record
    era_tag: str = ""            # which era identity was active when this formed

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "BaselineShift":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# Trigger table: (variable, direction, threshold, years_required) → [(target, delta, description)]
BASELINE_SHIFT_TRIGGERS: List[Dict[str, Any]] = [
    # Merchant power sustained → wealth concentration rises permanently
    {
        "variable": "faction_influence_merchant", "direction": "above",
        "threshold": 35.0, "years": 3,
        "effects": [
            {"target": "class_tension", "delta": 3.0,
             "desc": "Merchant dominance entrenched wealth inequality."},
            {"target": "trade_volume", "delta": 2.0,
             "desc": "Trade infrastructure permanently expanded."},
        ],
    },
    # Prolonged famine → administrative fragility
    {
        "variable": "food_stores", "direction": "below",
        "threshold": 15.0, "years": 2,
        "effects": [
            {"target": "institutional_strength", "delta": -3.0,
             "desc": "Prolonged famine eroded administrative capacity."},
            {"target": "hope_level", "delta": -2.0,
             "desc": "The memory of hunger diminished collective optimism."},
        ],
    },
    # Sustained high enforcement → law rigidity increases permanently
    {
        "variable": "enforcement_capacity", "direction": "above",
        "threshold": 75.0, "years": 3,
        "effects": [
            {"target": "law_rigidity", "delta": 4.0,
             "desc": "Years of heavy enforcement calcified legal structures."},
            {"target": "fear_level", "delta": 2.0,
             "desc": "The populace learned caution under sustained authority."},
        ],
    },
    # Sustained corruption → permanent institutional decay
    {
        "variable": "corruption", "direction": "above",
        "threshold": 60.0, "years": 3,
        "effects": [
            {"target": "institutional_strength", "delta": -4.0,
             "desc": "Chronic corruption hollowed out institutions."},
            {"target": "legitimacy", "delta": -3.0,
             "desc": "Public trust never fully recovered from endemic corruption."},
        ],
    },
    # High cultural confidence sustained → permanent cultural resilience
    {
        "variable": "cultural_confidence", "direction": "above",
        "threshold": 75.0, "years": 4,
        "effects": [
            {"target": "cohesion", "delta": 3.0,
             "desc": "A golden era of culture forged lasting social bonds."},
            {"target": "interpretation_divergence", "delta": -2.0,
             "desc": "Cultural confidence unified interpretation of the Oracle's words."},
        ],
    },
    # Sustained external threat → permanent military posture
    {
        "variable": "external_threat", "direction": "above",
        "threshold": 60.0, "years": 3,
        "effects": [
            {"target": "enforcement_capacity", "delta": 3.0,
             "desc": "Years of external danger forged a standing military tradition."},
            {"target": "trade_volume", "delta": -2.0,
             "desc": "Chronic insecurity choked trade routes."},
        ],
    },
    # Sustained high faith → myth crystallisation
    {
        "variable": "public_faith", "direction": "above",
        "threshold": 80.0, "years": 3,
        "effects": [
            {"target": "myth_accumulation", "delta": 5.0,
             "desc": "Unwavering faith crystallised the Oracle's words into scripture."},
            {"target": "law_rigidity", "delta": 2.0,
             "desc": "Faith-based governance hardened the legal code."},
        ],
    },
    # Sustained low faith → secular drift
    {
        "variable": "public_faith", "direction": "below",
        "threshold": 30.0, "years": 3,
        "effects": [
            {"target": "interpretation_divergence", "delta": 5.0,
             "desc": "Loss of faith splintered the Oracle's authority permanently."},
            {"target": "corruption", "delta": 3.0,
             "desc": "Without faith-based restraint, corruption found fertile ground."},
        ],
    },
    # Sustained high class tension → permanent structural inequality
    {
        "variable": "class_tension", "direction": "above",
        "threshold": 65.0, "years": 3,
        "effects": [
            {"target": "cohesion", "delta": -4.0,
             "desc": "Prolonged inequality fractured the social fabric irreparably."},
            {"target": "fear_level", "delta": 2.0,
             "desc": "Class resentment bred lasting fear on both sides."},
        ],
    },
    # Sustained literacy → permanent knowledge infrastructure
    {
        "variable": "literacy", "direction": "above",
        "threshold": 65.0, "years": 5,
        "effects": [
            {"target": "institutional_strength", "delta": 3.0,
             "desc": "A literate populace built durable bureaucratic systems."},
            {"target": "corruption", "delta": -2.0,
             "desc": "Widespread literacy enabled accountability and oversight."},
        ],
    },

    # ── Phase 7B: SURPLUS COMPOUNDING ENGINE ───────────────────
    # These are the UPWARD counterforces.  The sim has many decay
    # channels but nothing that compounds prosperity.  Without
    # these, every recovery eventually collapses back to famine.
    #
    # Design: when the kingdom sustains good conditions, permanent
    # baseline shifts accumulate that increase collapse resistance.

    # Sustained food surplus → agricultural infrastructure compounds
    {
        "variable": "food_production", "direction": "above",
        "threshold": 55.0, "years": 3,
        "effects": [
            {"target": "food_production", "delta": 2.0,
             "desc": "Years of surplus funded irrigation and crop rotation."},
            {"target": "infrastructure", "delta": 1.5,
             "desc": "Agricultural wealth built granaries and roads."},
        ],
    },
    # Sustained good infrastructure → trade compounds
    {
        "variable": "infrastructure", "direction": "above",
        "threshold": 55.0, "years": 3,
        "effects": [
            {"target": "trade_volume", "delta": 2.0,
             "desc": "Maintained roads and ports attracted merchants permanently."},
            {"target": "treasury", "delta": 50.0,
             "desc": "Infrastructure investment yielded lasting fiscal returns."},
        ],
    },
    # Sustained low tension → institutional strength compounds
    {
        "variable": "class_tension", "direction": "below",
        "threshold": 25.0, "years": 4,
        "effects": [
            {"target": "institutional_strength", "delta": 3.0,
             "desc": "Social peace allowed institutions to mature and strengthen."},
            {"target": "cohesion", "delta": 2.0,
             "desc": "Years without strife deepened the social fabric."},
        ],
    },
    # Sustained low corruption → legitimacy compounds
    {
        "variable": "corruption", "direction": "below",
        "threshold": 20.0, "years": 3,
        "effects": [
            {"target": "legitimacy", "delta": 3.0,
             "desc": "Clean governance earned lasting trust in the crown."},
            {"target": "hope_level", "delta": 2.0,
             "desc": "Honest rule fostered durable optimism."},
        ],
    },
    # Sustained hope → cultural confidence compounds
    {
        "variable": "hope_level", "direction": "above",
        "threshold": 55.0, "years": 3,
        "effects": [
            {"target": "cultural_confidence", "delta": 2.0,
             "desc": "Collective optimism crystallised into cultural pride."},
            {"target": "food_production", "delta": 1.0,
             "desc": "Hopeful people invested more in their farms and workshops."},
        ],
    },
    # Sustained institutional strength → corruption resistance
    {
        "variable": "institutional_strength", "direction": "above",
        "threshold": 50.0, "years": 4,
        "effects": [
            {"target": "corruption", "delta": -3.0,
             "desc": "Strong institutions entrenched anti-corruption norms."},
            {"target": "legitimacy", "delta": 2.0,
             "desc": "Functioning governance became its own legitimation."},
        ],
    },
]


class BaselineShiftEngine:
    """
    Tracks sustained variable conditions and crystallises permanent
    baseline shifts when thresholds are held long enough.

    Called once per year boundary (not every tick).
    """

    @classmethod
    def check_and_apply(cls, state: "KingdomState",
                        sustained_tracker: Dict[str, int],
                        shifts: List[BaselineShift],
                        current_era: str = "") -> List[BaselineShift]:
        """
        Check all trigger conditions.  For each sustained condition,
        increment the tracker.  When years_required is met, crystallise
        a BaselineShift and apply it.

        sustained_tracker: {trigger_key → years_sustained} (mutable, stored on KingdomState)
        shifts: existing list of shifts (mutable, stored on KingdomState)

        Returns newly crystallised shifts this call.
        """
        new_shifts: List[BaselineShift] = []

        for trigger in BASELINE_SHIFT_TRIGGERS:
            var_name = trigger["variable"]
            direction = trigger["direction"]
            threshold = trigger["threshold"]
            years_required = trigger["years"]

            # Resolve variable value
            value = cls._resolve_variable(state, var_name)
            if value is None:
                continue

            # Check condition
            condition_met = (
                (direction == "above" and value >= threshold) or
                (direction == "below" and value <= threshold)
            )

            key = f"{var_name}_{direction}_{threshold}"

            if condition_met:
                sustained_tracker[key] = sustained_tracker.get(key, 0) + 1
            else:
                # Reset counter — condition broken
                sustained_tracker[key] = 0

            # Check if crystallisation is due
            if sustained_tracker.get(key, 0) >= years_required:
                # Prevent re-triggering the same shift
                already_applied = any(
                    s.trigger_variable == var_name and
                    s.trigger_threshold == threshold and
                    s.trigger_direction == direction and
                    abs(state.tick - s.tick_applied) < 365  # cooldown: 1 year
                    for s in shifts
                )
                if already_applied:
                    continue

                # Crystallise shifts
                for effect in trigger["effects"]:
                    shift = BaselineShift(
                        shift_id=f"bshift_{state.tick}_{var_name}_{effect['target']}",
                        trigger_variable=var_name,
                        trigger_threshold=threshold,
                        trigger_direction=direction,
                        years_sustained=sustained_tracker[key],
                        tick_applied=state.tick,
                        target_variable=effect["target"],
                        delta=effect["delta"],
                        description=effect["desc"],
                        era_tag=current_era,
                    )
                    shifts.append(shift)
                    new_shifts.append(shift)

                    # Apply the shift permanently
                    cls._apply_shift(state, effect["target"], effect["delta"])

                    # Record in causal ledger
                    state.causal_ledger.record_delta(
                        source_type="baseline_shift",
                        source_id=shift.shift_id,
                        target_type="layer",
                        target_id=state.kingdom_id,
                        variable=effect["target"],
                        delta=effect["delta"],
                        tick=state.tick,
                        metadata={
                            "trigger": var_name,
                            "direction": direction,
                            "threshold": threshold,
                            "years_sustained": sustained_tracker[key],
                            "description": effect["desc"],
                        },
                    )

                # Reset tracker after crystallisation
                sustained_tracker[key] = 0

        return new_shifts

    @classmethod
    def _resolve_variable(cls, state: "KingdomState", var_name: str) -> Optional[float]:
        """Resolve a variable name to its current value."""
        # Handle special compound variables
        if var_name == "faction_influence_merchant":
            for f in state.factions.values():
                if f.archetype == FactionArchetype.MERCHANT:
                    return f.influence
            return None

        # Try each layer
        for layer in (state.physical, state.social, state.political, state.belief):
            if hasattr(layer, var_name):
                return getattr(layer, var_name)
        return None

    @classmethod
    def _apply_shift(cls, state: "KingdomState", target: str, delta: float):
        """
        Apply a permanent delta to a target variable's EQUILIBRIUM BASELINE.

        Phase 8: shifts now modify the resting equilibrium, not the
        instantaneous value.  The mean-reversion pull in the tick loop
        will gradually drag the current value toward the new baseline.
        This makes baseline shifts structural (they change where the
        system wants to rest) rather than transient (a one-time bump
        that gets erased by decay channels).

        A small immediate nudge (30% of delta) is also applied to the
        current value so the shift isn't invisible on the tick it fires.
        """
        _c = lambda v, lo=0.0, hi=100.0: max(lo, min(hi, v))

        # 1. Modify the equilibrium baseline (the structural change)
        if hasattr(state, "equilibrium_baselines"):
            old_eq = state.equilibrium_baselines.get(target, 50.0)
            if target == "treasury":
                state.equilibrium_baselines[target] = max(0.0, old_eq + delta)
            else:
                state.equilibrium_baselines[target] = max(0.0, min(100.0, old_eq + delta))

        # 2. Small immediate nudge to current value (30% of delta)
        #    so the effect is perceptible immediately, not invisible.
        immediate = delta * 0.3
        for layer in (state.physical, state.social, state.political, state.belief):
            if hasattr(layer, target):
                old_val = getattr(layer, target)
                if target == "treasury":
                    setattr(layer, target, max(0.0, old_val + immediate))
                else:
                    setattr(layer, target, _c(old_val + immediate))
                return

    @classmethod
    def net_baseline_modifier(cls, shifts: List[BaselineShift],
                               variable: str) -> float:
        """Sum of all permanent baseline modifiers for a variable."""
        return sum(s.delta for s in shifts if s.target_variable == variable)


# ── 2. Institutional Scar Tissue ──────────────────────────────
#
# When a crisis event resolves (or expires), it leaves a permanent
# residual mark on the kingdom.  The crisis passes, but something
# remains altered.  This prevents symmetric oscillation.

@dataclass
class InstitutionalScar:
    """
    A permanent residual effect left by a resolved crisis.

    Not every event leaves a scar — only events above a severity
    threshold and of certain kinds.
    """
    scar_id: str
    source_event_id: str
    source_event_kind: str       # EventKind name
    source_event_description: str
    tick_formed: int
    variable: str                # what was permanently altered
    delta: float                 # signed permanent modifier
    description: str

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "InstitutionalScar":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# Scar table: EventKind → [(variable, delta_range, description_template)]
# delta_range is (min, max) — actual value is scaled by event severity.
SCAR_TABLE: Dict[str, List[Dict[str, Any]]] = {
    "SHORTAGE": [
        {"variable": "institutional_strength", "base_delta": -3.0,
         "desc": "Famine scars: administrative systems never fully recovered."},
        {"variable": "hope_level", "base_delta": -2.0,
         "desc": "The memory of empty granaries lingers in collective consciousness."},
    ],
    "SCHISM": [
        {"variable": "interpretation_divergence", "base_delta": 3.0,
         "desc": "The schism left permanent fractures in Oracle interpretation."},
        {"variable": "cohesion", "base_delta": -2.0,
         "desc": "Old schism lines persist as invisible social boundaries."},
    ],
    "MILITARY_DEFIANCE": [
        {"variable": "law_rigidity", "base_delta": 3.0,
         "desc": "After military defiance, laws were rewritten harder."},
        {"variable": "enforcement_capacity", "base_delta": -2.0,
         "desc": "Trust in the military arm was permanently diminished."},
    ],
    "NATURAL_DISASTER": [
        {"variable": "infrastructure", "base_delta": -4.0,
         "desc": "The disaster left scars in the landscape and the roads."},
        {"variable": "fear_level", "base_delta": 2.0,
         "desc": "A collective anxiety about catastrophe persists."},
    ],
    "COMPOUND": [
        {"variable": "institutional_strength", "base_delta": -5.0,
         "desc": "The convergence of crises overwhelmed institutional capacity."},
        {"variable": "legitimacy", "base_delta": -3.0,
         "desc": "The compound crisis shattered public confidence in governance."},
    ],
    "ACCUSATION": [
        {"variable": "corruption", "base_delta": 1.0,
         "desc": "The accusation, even resolved, left suspicion in its wake."},
    ],
    "REFORM_MOVEMENT": [
        {"variable": "law_rigidity", "base_delta": -2.0,
         "desc": "Reform loosened legal structures permanently."},
        {"variable": "institutional_strength", "base_delta": 2.0,
         "desc": "Reform strengthened institutions through renewal."},
    ],
    "CULTURAL_SHIFT": [
        {"variable": "cultural_confidence", "base_delta": 3.0,
         "desc": "The cultural shift left a permanent mark on identity."},
    ],
    "DIPLOMATIC_INCIDENT": [
        {"variable": "external_threat", "base_delta": 2.0,
         "desc": "The diplomatic incident left lasting mistrust between realms."},
        {"variable": "trade_volume", "base_delta": -1.5,
         "desc": "Trade routes never fully recovered from the diplomatic fallout."},
    ],
}

# Minimum severity to leave a scar
SCAR_SEVERITY_THRESHOLD: float = 35.0

# ── Phase 9: Scar gating constants ────────────────────────────
SCAR_COOLDOWN_TICKS: int = 180            # min ticks between scars of same (kind, variable)
MAX_SCARS_PER_VARIABLE: int = 12          # cap total active scars touching one variable
MAX_SCARS_PER_KIND: int = 10              # cap total active scars from one event kind
MAX_SCARS_PER_1000_TICKS: int = 6         # rate limiter: max scars in any 1000-tick window


def _sigmoid(x: float) -> float:
    """Standard sigmoid clamped to avoid overflow."""
    x = max(-20.0, min(20.0, x))
    return 1.0 / (1.0 + math.exp(-x))


# ── Adaptive (positive) scar definitions ──────────────────────
# Rare positive outcomes from crisis resolution.
ADAPTIVE_SCAR_TABLE: Dict[str, List[Dict[str, Any]]] = {
    "SHORTAGE": [
        {"variable": "food_production", "base_delta": 1.5,
         "prob": 0.15,
         "desc": "Famine survivors built granaries and improved irrigation."},
        {"variable": "infrastructure", "base_delta": 1.0,
         "prob": 0.10,
         "desc": "Crisis-era emergency roads became permanent improvements."},
    ],
    "SCHISM": [
        {"variable": "interpretation_divergence", "base_delta": -1.5,
         "prob": 0.12,
         "desc": "Post-schism reconciliation produced a unified canon."},
        {"variable": "institutional_strength", "base_delta": 1.5,
         "prob": 0.10,
         "desc": "The schism forced institutional reform and clarity."},
    ],
    "REFORM_MOVEMENT": [
        {"variable": "corruption", "base_delta": -1.0,
         "prob": 0.15,
         "desc": "Reform entrenched anti-corruption mechanisms."},
    ],
    "NATURAL_DISASTER": [
        {"variable": "infrastructure", "base_delta": 1.0,
         "prob": 0.10,
         "desc": "Rebuilding created more resilient structures."},
    ],
}


class InstitutionalScarEngine:
    """
    Phase 9: Gated institutional scar tissue engine.

    When events fire, this engine determines whether they leave
    permanent scar tissue on the kingdom.  Multiple gates prevent
    the bimodal outcome (scars=0 or scars=60+):

    1. Severity threshold gate
    2. Per-kind cap (MAX_SCARS_PER_KIND)
    3. Per-variable cap (MAX_SCARS_PER_VARIABLE)
    4. Per-(kind,variable) cooldown (SCAR_COOLDOWN_TICKS)
    5. Rate limiter (MAX_SCARS_PER_1000_TICKS)
    6. Probabilistic sigmoid gate with resilience modulation
    7. Diminishing returns on delta magnitude

    Also generates adaptive (positive) scars for certain event kinds.
    """

    @classmethod
    def _compute_resilience(cls, state: "KingdomState") -> float:
        """
        Kingdom resilience: 0.0 (fragile) to 1.0 (very resilient).

        Resilient kingdoms resist scarring — their institutions absorb
        crisis without permanent damage.
        """
        inst = getattr(state.political, "institutional_strength", 50.0)
        coh = getattr(state.social, "cohesion", 50.0)
        lit = getattr(state.social, "literacy", 30.0)
        treas = getattr(state.physical, "treasury", 0.0)

        resilience = (
            0.35 * (inst / 100.0)
            + 0.25 * (coh / 100.0)
            + 0.20 * (lit / 100.0)
            + 0.20 * min(1.0, treas / 5000.0)
        )
        return max(0.0, min(1.0, resilience))

    @classmethod
    def _scar_count_for_variable(cls, scars: List[InstitutionalScar],
                                  variable: str) -> int:
        return sum(1 for s in scars if s.variable == variable)

    @classmethod
    def _scar_count_for_kind(cls, scars: List[InstitutionalScar],
                              kind_name: str) -> int:
        return sum(1 for s in scars if s.source_event_kind == kind_name)

    @classmethod
    def _recent_scar_count(cls, scars: List[InstitutionalScar],
                            tick: int, window: int = 1000) -> int:
        cutoff = tick - window
        return sum(1 for s in scars if s.tick_formed > cutoff)

    @classmethod
    def _check_cooldown(cls, state: "KingdomState",
                         kind_name: str, variable: str) -> bool:
        """True if this (kind, variable) pair is on cooldown."""
        cooldowns = getattr(state, "scar_cooldowns", {})
        key = f"{kind_name}:{variable}"
        last_tick = cooldowns.get(key, -99999)
        return (state.tick - last_tick) < SCAR_COOLDOWN_TICKS

    @classmethod
    def _record_cooldown(cls, state: "KingdomState",
                          kind_name: str, variable: str):
        """Record that a scar was just applied for this (kind, variable)."""
        if not hasattr(state, "scar_cooldowns"):
            state.scar_cooldowns = {}
        key = f"{kind_name}:{variable}"
        state.scar_cooldowns[key] = state.tick

    @classmethod
    def form_scars(cls, event: SimEvent, state: "KingdomState",
                   scars: List[InstitutionalScar],
                   rng: SeededRNG) -> List[InstitutionalScar]:
        """
        Called when an event is created.  Determines and applies scars.

        Returns newly formed scars.  Updates state.scar_counters for
        instrumentation.
        """
        # Ensure instrumentation counters exist
        if not hasattr(state, "scar_counters"):
            state.scar_counters = {
                "applied": 0, "blocked_severity": 0,
                "blocked_cooldown": 0, "blocked_cap": 0,
                "blocked_probability": 0, "blocked_rate": 0,
                "adaptive_applied": 0,
            }

        # Gate 1: severity threshold
        if event.severity < SCAR_SEVERITY_THRESHOLD:
            state.scar_counters["blocked_severity"] += 1
            return []

        kind_name = event.kind.name
        scar_defs = SCAR_TABLE.get(kind_name, [])
        if not scar_defs:
            return []

        # Gate 5 (early check): rate limiter — global scar rate
        recent_count = cls._recent_scar_count(scars, state.tick, 1000)
        if recent_count >= MAX_SCARS_PER_1000_TICKS:
            state.scar_counters["blocked_rate"] += 1
            return []

        # Gate 2: per-kind cap
        kind_count = cls._scar_count_for_kind(scars, kind_name)
        if kind_count >= MAX_SCARS_PER_KIND:
            state.scar_counters["blocked_cap"] += 1
            return []

        # Compute resilience once for this event
        resilience = cls._compute_resilience(state)

        new_scars: List[InstitutionalScar] = []
        # Fork RNG deterministically from (seed, event_id)
        scar_rng = rng.fork(f"scar_{event.event_id}")

        severity_scale = event.severity / 100.0

        for scar_def in scar_defs:
            variable = scar_def["variable"]

            # Gate 3: per-variable cap
            var_count = cls._scar_count_for_variable(scars, variable)
            if var_count >= MAX_SCARS_PER_VARIABLE:
                state.scar_counters["blocked_cap"] += 1
                continue

            # Gate 4: per-(kind, variable) cooldown
            if cls._check_cooldown(state, kind_name, variable):
                state.scar_counters["blocked_cooldown"] += 1
                continue

            # Gate 6: probabilistic sigmoid with resilience modulation
            # p = sigmoid((severity - threshold)/10) * (1 - resilience)
            raw_p = _sigmoid((event.severity - SCAR_SEVERITY_THRESHOLD) / 10.0)
            p = raw_p * (1.0 - resilience)
            # Fork per-variable for determinism
            var_rng = scar_rng.fork(f"{variable}")
            roll = var_rng.random()
            if roll > p:
                state.scar_counters["blocked_probability"] += 1
                continue

            # Gate 7: diminishing returns on delta
            dim_factor = 1.0 / (1.0 + 0.35 * var_count)
            delta = scar_def["base_delta"] * severity_scale * dim_factor
            # Small random variance
            delta *= var_rng.uniform(0.7, 1.3)

            scar = InstitutionalScar(
                scar_id=f"scar_{state.tick}_{event.event_id[:12]}_{variable}",
                source_event_id=event.event_id,
                source_event_kind=kind_name,
                source_event_description=event.description[:100],
                tick_formed=state.tick,
                variable=variable,
                delta=round(delta, 3),
                description=scar_def["desc"],
            )
            scars.append(scar)
            new_scars.append(scar)

            # Record cooldown
            cls._record_cooldown(state, kind_name, variable)

            # Apply the scar to equilibrium baseline
            BaselineShiftEngine._apply_shift(state, scar.variable, scar.delta)

            # Record in causal ledger with full gating metadata
            state.causal_ledger.record_delta(
                source_type="institutional_scar",
                source_id=scar.scar_id,
                target_type="layer",
                target_id=state.kingdom_id,
                variable=scar.variable,
                delta=scar.delta,
                tick=state.tick,
                metadata={
                    "source_event": event.event_id,
                    "event_kind": kind_name,
                    "event_severity": event.severity,
                    "description": scar.description,
                    "p_sigmoid": round(raw_p, 4),
                    "p_final": round(p, 4),
                    "resilience": round(resilience, 4),
                    "dim_factor": round(dim_factor, 4),
                    "var_count": var_count,
                    "kind_count": kind_count,
                    "roll": round(roll, 4),
                },
            )

            state.scar_counters["applied"] += 1

            # Re-check rate limiter after each scar
            recent_count += 1
            if recent_count >= MAX_SCARS_PER_1000_TICKS:
                break

        # ── Adaptive (positive) scars ──────────────────────────
        # Small chance that crisis resolution produces resilience
        adaptive_defs = ADAPTIVE_SCAR_TABLE.get(kind_name, [])
        if adaptive_defs and event.severity >= SCAR_SEVERITY_THRESHOLD:
            adapt_rng = rng.fork(f"adaptive_{event.event_id}")
            for adef in adaptive_defs:
                variable = adef["variable"]
                # Use fixed probability from definition, modulated by resilience
                # High resilience = better at learning from crises
                adapt_p = adef["prob"] * (0.5 + resilience * 0.5)
                if adapt_rng.fork(variable).random() > adapt_p:
                    continue
                # Cooldown applies to adaptive scars too
                if cls._check_cooldown(state, kind_name + "_ADAPT", variable):
                    continue
                # Per-variable cap applies
                if cls._scar_count_for_variable(scars, variable) >= MAX_SCARS_PER_VARIABLE:
                    continue

                delta = adef["base_delta"] * severity_scale
                delta *= adapt_rng.fork(f"{variable}_v").uniform(0.6, 1.2)

                scar = InstitutionalScar(
                    scar_id=f"scar_adapt_{state.tick}_{event.event_id[:12]}_{variable}",
                    source_event_id=event.event_id,
                    source_event_kind=kind_name + "_ADAPTIVE",
                    source_event_description=f"Adaptive: {adef['desc'][:80]}",
                    tick_formed=state.tick,
                    variable=variable,
                    delta=round(delta, 3),
                    description=adef["desc"],
                )
                scars.append(scar)
                new_scars.append(scar)
                cls._record_cooldown(state, kind_name + "_ADAPT", variable)
                BaselineShiftEngine._apply_shift(state, scar.variable, scar.delta)

                state.causal_ledger.record_delta(
                    source_type="adaptive_scar",
                    source_id=scar.scar_id,
                    target_type="layer",
                    target_id=state.kingdom_id,
                    variable=scar.variable,
                    delta=scar.delta,
                    tick=state.tick,
                    metadata={
                        "source_event": event.event_id,
                        "event_kind": kind_name,
                        "adaptive": True,
                        "description": scar.description,
                        "p": round(adapt_p, 4),
                        "resilience": round(resilience, 4),
                    },
                )
                state.scar_counters["adaptive_applied"] += 1

        return new_scars


# ── 3. Era Identity Classification ────────────────────────────
#
# The kingdom's structural state is classified into an "era" —
# not a label, but a mechanical modifier that changes how the
# simulation behaves.  A kingdom in RENAISSANCE propagates
# reform ripples faster.  A kingdom in FAMINE_ERA generates
# more shortage events.  Identity shapes destiny.

class EraIdentity(Enum):
    """
    Structural identity states.

    Each era modifies simulation parameters mechanically.
    A kingdom can only be in ONE era at a time.
    Era transitions are logged, permanent in history, and
    announced to the player.
    """
    STABLE = auto()              # default — no special modifiers
    RENAISSANCE = auto()         # knowledge + culture flourishing
    FAMINE_ERA = auto()          # prolonged resource crisis
    AUTHORITARIAN_CONSOLIDATION = auto()  # enforcement + rigidity dominant
    IDEOLOGICAL_FRACTURE = auto()  # faith collapse + divergence
    GOLDEN_AGE = auto()          # everything high — rare and fragile
    DECLINE = auto()             # broad systemic decay
    OLIGARCHIC_GRIP = auto()     # one faction dominates resources
    MILITANT_POSTURE = auto()    # external threat drives policy
    REFORMATION = auto()         # structural renewal in progress


@dataclass
class EraRecord:
    """Historical record of an era transition."""
    era: str                     # EraIdentity name
    started_tick: int
    ended_tick: Optional[int] = None
    health_at_start: float = 50.0
    trigger_conditions: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "EraRecord":
        obj = cls(era=d["era"], started_tick=d["started_tick"])
        obj.ended_tick = d.get("ended_tick")
        obj.health_at_start = d.get("health_at_start", 50.0)
        obj.trigger_conditions = d.get("trigger_conditions", {})
        return obj


# Era detection rules: each era has conditions that must ALL be true.
# Checked in priority order — first match wins.

ERA_DETECTION_RULES: List[Dict[str, Any]] = [
    {
        "era": EraIdentity.GOLDEN_AGE,
        "conditions": {
            "health_composite_min": 75.0,
            "cultural_confidence_min": 70.0,
            "cohesion_min": 65.0,
            "legitimacy_min": 70.0,
            "food_stores_min": 50.0,
        },
    },
    {
        "era": EraIdentity.RENAISSANCE,
        "conditions": {
            "cultural_confidence_min": 65.0,
            "literacy_min": 55.0,
            "cohesion_min": 50.0,
            "interpretation_divergence_max": 25.0,
        },
    },
    {
        "era": EraIdentity.FAMINE_ERA,
        "conditions": {
            "food_stores_max": 20.0,
            "resource_pressure_min": 50.0,
        },
    },
    {
        "era": EraIdentity.AUTHORITARIAN_CONSOLIDATION,
        "conditions": {
            "enforcement_capacity_min": 70.0,
            "law_rigidity_min": 60.0,
            "fear_level_min": 40.0,
        },
    },
    {
        "era": EraIdentity.IDEOLOGICAL_FRACTURE,
        "conditions": {
            "interpretation_divergence_min": 35.0,
            "public_faith_max": 40.0,
        },
    },
    {
        "era": EraIdentity.OLIGARCHIC_GRIP,
        "conditions": {
            "max_faction_share_min": 40.0,  # one faction > 40% influence
            "class_tension_min": 45.0,
        },
    },
    {
        "era": EraIdentity.MILITANT_POSTURE,
        "conditions": {
            "external_threat_min": 55.0,
            "enforcement_capacity_min": 55.0,
        },
    },
    {
        "era": EraIdentity.REFORMATION,
        "conditions": {
            "law_rigidity_max": 30.0,
            "institutional_strength_min": 45.0,
            "corruption_max": 30.0,
        },
    },
    {
        "era": EraIdentity.DECLINE,
        "conditions": {
            "health_composite_max": 35.0,
        },
    },
    # STABLE is the fallback — no explicit conditions.
]

# Mechanical modifiers per era.
# These are multipliers/additions applied to simulation parameters.

ERA_MODIFIERS: Dict[str, Dict[str, float]] = {
    "STABLE": {},  # no modifiers
    "RENAISSANCE": {
        "reform_ripple_multiplier": 1.5,       # reform ripples propagate faster
        "cultural_confidence_drift": 0.1,       # slow cultural growth
        "event_prob_discovery": 2.0,            # discoveries more likely
        "diplomatic_stance_bonus": 0.1,         # neighbours view more favourably
        # Stability reinforcement: knowledge society resists decay
        "institutional_drift": 0.05,            # learning builds institutions
        "corruption_drift": -0.05,              # literacy enables oversight
        "hope_drift": 0.05,                     # cultural flowering inspires
        "infrastructure_drift": 0.03,           # knowledge builds better
        "trade_drift": 0.03,                    # cultural exports
    },
    "FAMINE_ERA": {
        "food_consumption_multiplier": 1.3,     # hoarding/waste increases consumption
        "event_prob_shortage": 2.0,             # shortages more likely
        "hope_drift": -0.2,                     # hope decays faster
        "cohesion_drift": -0.1,                 # social bonds fray
    },
    "AUTHORITARIAN_CONSOLIDATION": {
        "enforcement_drift": 0.1,               # enforcement self-reinforces
        "fear_drift": 0.1,                      # fear stays elevated
        "reform_ripple_multiplier": 0.5,        # reform suppressed
        "corruption_drift": 0.03,               # power corrupts (reduced — regime has controls)
        # Phase 7C: Regime Lock — authoritarian states mechanically
        # suppress tension and maintain infrastructure.  They don't
        # collapse into famine; they lock into low-freedom/high-order.
        "class_tension_drift": -0.15,           # enforced order suppresses dissent
        "infrastructure_drift": 0.03,           # regime invests in state infrastructure
        "food_production_drift": 0.02,          # state-managed agriculture (below surplus, but sustaining)
        "hope_drift": -0.05,                    # stagnation, not despair
        "legitimacy_drift": -0.02,              # slow erosion, not collapse
    },
    "IDEOLOGICAL_FRACTURE": {
        "divergence_drift": 0.15,               # divergence accelerates
        "rumor_drift": 0.1,                     # rumours proliferate
        "event_prob_schism": 2.0,               # schisms more likely
        "faith_drift": -0.1,                    # faith continues eroding
    },
    "GOLDEN_AGE": {
        "trade_drift": 0.1,                     # prosperity momentum
        "infrastructure_drift": 0.05,           # building projects
        "diplomatic_stance_bonus": 0.2,         # neighbours admire
        "event_prob_discovery": 3.0,            # peak discovery rate
        # Stability reinforcement: golden ages actively resist collapse
        "corruption_drift": -0.08,              # prosperity funds anti-corruption
        "hope_drift": 0.1,                      # golden feedback loop
        "cohesion_drift": 0.05,                 # shared prosperity bonds people
        "class_tension_drift": -0.08,           # wealth diffusion reduces strain
        "food_production_drift": 0.03,          # agricultural golden age
        "institutional_drift": 0.05,            # mature institutions
        "legitimacy_drift": 0.05,               # earned through prosperity
    },
    "DECLINE": {
        "infrastructure_drift": -0.05,           # decay (reduced from -0.1)
        "corruption_drift": 0.06,                # systems break down (reduced from 0.1)
        "hope_drift": -0.1,                      # collective despair (reduced from -0.15)
        "legitimacy_drift": -0.06,               # authority erodes (reduced from -0.1)
    },
    "OLIGARCHIC_GRIP": {
        "class_tension_drift": 0.1,             # inequality worsens
        "trade_drift": 0.05,                    # oligarchs trade well
        "reform_ripple_multiplier": 0.3,        # reform nearly impossible
        "corruption_drift": 0.08,               # rent-seeking
    },
    "MILITANT_POSTURE": {
        "enforcement_drift": 0.15,              # military buildup
        "trade_drift": -0.05,                   # commerce suffers
        "treasury_drain": 2.0,                  # military spending
        "fear_drift": 0.05,                     # society on edge
    },
    "REFORMATION": {
        "reform_ripple_multiplier": 2.0,        # reform in full swing
        "corruption_drift": -0.1,               # cleanup underway
        "institutional_drift": 0.1,             # rebuilding institutions
        "class_tension_drift": 0.05,            # reform creates friction
        # Stability reinforcement: reformation actively builds
        "hope_drift": 0.08,                     # renewal inspires
        "food_production_drift": 0.02,          # agricultural reform
        "infrastructure_drift": 0.03,           # rebuilding
        "legitimacy_drift": 0.05,               # earned through reform
    },
}


class EraClassifier:
    """
    Structurally classifies the kingdom into an era identity.

    Not cosmetic — era modifiers change simulation behaviour.
    Era transitions are logged and announced.
    """

    @classmethod
    def classify(cls, state: "KingdomState") -> EraIdentity:
        """
        Determine which era the kingdom is currently in.

        Checks rules in priority order.  First match wins.
        """
        for rule in ERA_DETECTION_RULES:
            if cls._check_conditions(state, rule["conditions"]):
                return rule["era"]
        return EraIdentity.STABLE

    @classmethod
    def _check_conditions(cls, state: "KingdomState",
                          conditions: Dict[str, float]) -> bool:
        """Check whether all conditions for an era are met."""
        for key, threshold in conditions.items():
            value = cls._resolve_condition_value(state, key)
            if value is None:
                return False

            if key.endswith("_min"):
                if value < threshold:
                    return False
            elif key.endswith("_max"):
                if value > threshold:
                    return False

        return True

    @classmethod
    def _resolve_condition_value(cls, state: "KingdomState",
                                  key: str) -> Optional[float]:
        """Resolve a condition key to a value."""
        # Strip _min/_max suffix to get variable name
        var_name = key
        for suffix in ("_min", "_max"):
            if var_name.endswith(suffix):
                var_name = var_name[:-len(suffix)]
                break

        # Special compound variables
        if var_name == "health_composite":
            return state.health.composite
        if var_name == "max_faction_share":
            if not state.factions:
                return 0.0
            return max(f.influence for f in state.factions.values())

        # Standard layer variables
        for layer in (state.physical, state.social, state.political, state.belief):
            if hasattr(layer, var_name):
                return getattr(layer, var_name)
        return None

    @classmethod
    def get_modifiers(cls, era: EraIdentity) -> Dict[str, float]:
        """Get the mechanical modifiers for an era."""
        return ERA_MODIFIERS.get(era.name, {})

    @classmethod
    def apply_era_drift(cls, state: "KingdomState", era: EraIdentity):
        """
        Apply per-tick era drift modifiers.

        These are the small, persistent pushes that make an era
        mechanically different from STABLE.
        """
        mods = cls.get_modifiers(era)
        _c = lambda v, lo=0.0, hi=100.0: max(lo, min(hi, v))
        ledger = state.causal_ledger

        # Apply drift modifiers
        drift_map = {
            "cultural_confidence_drift": ("social", "cultural_confidence"),
            "hope_drift": ("social", "hope_level"),
            "cohesion_drift": ("social", "cohesion"),
            "fear_drift": ("social", "fear_level"),
            "class_tension_drift": ("social", "class_tension"),
            "enforcement_drift": ("political", "enforcement_capacity"),
            "corruption_drift": ("political", "corruption"),
            "legitimacy_drift": ("political", "legitimacy"),
            "institutional_drift": ("political", "institutional_strength"),
            "trade_drift": ("physical", "trade_volume"),
            "infrastructure_drift": ("physical", "infrastructure"),
            "food_production_drift": ("physical", "food_production"),
            "divergence_drift": ("belief", "interpretation_divergence"),
            "rumor_drift": ("belief", "rumor_distortion"),
            "faith_drift": ("belief", "public_faith"),
        }

        for mod_key, (layer_name, var_name) in drift_map.items():
            drift_val = mods.get(mod_key, 0.0)
            if abs(drift_val) < 1e-6:
                continue

            layer = getattr(state, layer_name, None)
            if layer and hasattr(layer, var_name):
                old = getattr(layer, var_name)
                if var_name == "treasury":
                    setattr(layer, var_name, max(0.0, old + drift_val))
                else:
                    setattr(layer, var_name, _c(old + drift_val))

                ledger.record_delta(
                    source_type="era_modifier",
                    source_id=f"era_{era.name}",
                    target_type="layer",
                    target_id=state.kingdom_id,
                    variable=var_name,
                    delta=drift_val,
                    tick=state.tick,
                    metadata={"era": era.name},
                )


# ============================================================
# SECTION 7.9: STATE COHERENCE ENGINE
# ============================================================
#
# The simulation can drift into semantically impossible states:
#   food=0, hope=0, infrastructure=0 … but cohesion=100, faith=100.
#
# That is structural incoherence.
#
# This engine enforces cross-domain feasibility constraints.
# It does NOT replace the coupling logic.  It acts as a validator
# and corrector that runs every tick AFTER all couplings.
#
# Design: Mythic survivability.
#   A starving kingdom CAN hold together through faith + enforcement.
#   But only temporarily.  And the cost accumulates.
#   Without active player intervention, incoherence resolves into
#   collapse, not equilibrium.
#
# Three mechanisms:
#   1. Material State Classification
#   2. Cross-Domain Feasibility Constraints (tension equations)
#   3. Dampening Curves (prevent pinning at 0/100)


class MaterialState(Enum):
    """Macro classification of the material layer."""
    THRIVING = auto()    # food > 60, infrastructure > 50, trade > 40
    FUNCTIONAL = auto()  # food > 30, infrastructure > 25
    STRAINED = auto()    # food > 10, or infrastructure > 10
    COLLAPSED = auto()   # food <= 10 AND infrastructure <= 10


class StateCoherenceEngine:
    """
    Cross-domain feasibility validator.

    Runs every tick.  Does not generate events.
    Applies corrective forces when variables are structurally
    incompatible with each other.

    This is constraint logic, not simulation.
    """

    # ── Material State Classification ──────────────────────────

    @classmethod
    def classify_material(cls, state: "KingdomState") -> MaterialState:
        """Determine the macro material state."""
        p = state.physical
        if p.food_stores > 60 and p.infrastructure > 50 and p.trade_volume > 40:
            return MaterialState.THRIVING
        if p.food_stores > 30 and p.infrastructure > 25:
            return MaterialState.FUNCTIONAL
        if p.food_stores > 10 or p.infrastructure > 10:
            return MaterialState.STRAINED
        return MaterialState.COLLAPSED

    # ── Core Coherence Pass ────────────────────────────────────

    @classmethod
    def enforce_coherence(cls, state: "KingdomState"):
        """
        Main entry point.  Called every tick after coupling logic.

        Applies cross-domain constraints and dampening.
        Does not use RNG (deterministic correction).
        """
        _c = lambda v, lo=0.0, hi=100.0: max(lo, min(hi, v))
        mat = cls.classify_material(state)
        ledger = state.causal_ledger
        tick = state.tick

        # Phase 7: Post-transformation grace period.
        # During grace, treat material state as STRAINED (not COLLAPSED)
        # so the transformation's injected values have time to stabilize.
        in_grace = (hasattr(state, "terminal_grace_until") and
                    tick < state.terminal_grace_until)
        if in_grace and mat == MaterialState.COLLAPSED:
            mat = MaterialState.STRAINED

        def _correct(layer_name: str, var_name: str, delta: float, reason: str):
            """Apply a coherence correction and log it."""
            layer = getattr(state, layer_name, None)
            if layer is None or not hasattr(layer, var_name):
                return
            old = getattr(layer, var_name)
            if var_name == "treasury":
                new = max(0.0, old + delta)
            else:
                new = _c(old + delta)
            if abs(new - old) < 1e-6:
                return  # already at bound, skip
            setattr(layer, var_name, new)
            ledger.record_delta(
                source_type="coherence",
                source_id=reason,
                target_type="layer",
                target_id=state.kingdom_id,
                variable=var_name,
                delta=new - old,
                tick=tick,
                metadata={"material_state": mat.name, "reason": reason},
            )

        # ────────────────────────────────────────────────────────
        # 1. MATERIAL COLLAPSE → SOCIAL CONSEQUENCES
        # ────────────────────────────────────────────────────────
        #
        # If material layer is COLLAPSED, social variables cannot
        # remain high unless actively sustained by enforcement,
        # faith, or external threat (siege mentality).
        #
        # "Justification score": how much of the cohesion is
        # explainable by non-material forces.

        if mat == MaterialState.COLLAPSED:
            s = state.social
            pol = state.political
            b = state.belief

            # What justifies high cohesion despite starvation?
            # enforcement: fear-based unity
            # faith: belief-based unity
            # external_threat: siege mentality
            justification = (
                min(pol.enforcement_capacity, 80.0) / 80.0 * 0.35
                + min(b.public_faith, 90.0) / 90.0 * 0.35
                + min(pol.external_threat, 80.0) / 80.0 * 0.30
            )
            # justification is 0.0 to 1.0
            # At justification=1.0, cohesion ceiling is 80
            # At justification=0.0, cohesion ceiling is 20
            cohesion_ceiling = 20.0 + justification * 60.0

            if s.cohesion > cohesion_ceiling:
                decay = min((s.cohesion - cohesion_ceiling) * 0.08, 2.0)
                _correct("social", "cohesion", -decay,
                         "material_collapse_cohesion_drain")

            # Hope cannot persist without material basis
            hope_ceiling = 10.0 + justification * 25.0
            if s.hope_level > hope_ceiling:
                decay = min((s.hope_level - hope_ceiling) * 0.1, 1.5)
                _correct("social", "hope_level", -decay,
                         "material_collapse_hope_drain")

            # Cultural confidence erodes without material backing
            cc_ceiling = 30.0 + justification * 40.0
            if s.cultural_confidence > cc_ceiling:
                decay = min((s.cultural_confidence - cc_ceiling) * 0.05, 1.0)
                _correct("social", "cultural_confidence", -decay,
                         "material_collapse_cultural_drain")

            # ── Trade cannot flourish without infrastructure ───
            # A collapsed kingdom has ruined roads, no ports, no
            # warehouses.  Trade volume decays toward zero.
            p = state.physical
            if p.trade_volume > 10.0:
                trade_drain = min((p.trade_volume - 10.0) * 0.05, 2.0)
                _correct("physical", "trade_volume", -trade_drain,
                         "material_collapse_trade_drain")

            # ── Treasury bleeds during collapse ────────────────
            # Looters, fleeing merchants, debased currency.  Treasury
            # can't accumulate when there's no functioning economy.
            if p.treasury > 100.0:
                treasury_drain = min(p.treasury * 0.01, 50.0)
                # Use direct subtraction since _correct may not handle treasury sign
                p.treasury = max(0.0, p.treasury - treasury_drain)
                ledger.record_delta(
                    source_type="coherence",
                    source_id="material_collapse_treasury_bleed",
                    target_type="layer",
                    target_id=state.kingdom_id,
                    variable="treasury",
                    delta=-treasury_drain,
                    tick=tick,
                    metadata={"material_state": mat.name},
                )

        elif mat == MaterialState.STRAINED:
            s = state.social
            # Softer version: cohesion slowly erodes if material is strained
            if s.cohesion > 75.0 and state.physical.food_stores < 15:
                _correct("social", "cohesion", -0.3,
                         "material_strain_cohesion_pressure")

        # ────────────────────────────────────────────────────────
        # 2. CORRUPTION / LEGITIMACY TENSION
        # ────────────────────────────────────────────────────────
        #
        # corruption=100 + legitimacy=100 requires:
        #   fear OR faith OR enforcement to justify it.
        # Without justification, legitimacy decays.

        pol = state.political
        if pol.corruption > 60:
            corruption_excess = (pol.corruption - 60.0) / 40.0  # 0→1

            # What sustains legitimacy despite corruption?
            fear_cover = min(state.social.fear_level, 70.0) / 70.0
            faith_cover = min(state.belief.public_faith, 80.0) / 80.0
            enforce_cover = min(pol.enforcement_capacity, 80.0) / 80.0

            cover = max(fear_cover, faith_cover, enforce_cover)
            # How much corruption is "covered"?
            uncovered = max(0.0, corruption_excess - cover)

            if uncovered > 0.05 and pol.legitimacy > 30.0:
                legit_drain = uncovered * 0.6
                _correct("political", "legitimacy", -legit_drain,
                         "corruption_legitimacy_tension")

            # Corruption also drains institutional strength
            if pol.corruption > 70 and pol.institutional_strength > 20:
                inst_drain = (pol.corruption - 70.0) / 30.0 * 0.3
                _correct("political", "institutional_strength", -inst_drain,
                         "corruption_institutional_decay")

        # ────────────────────────────────────────────────────────
        # 3. FAITH WITHOUT MATERIAL BASIS
        # ────────────────────────────────────────────────────────
        #
        # Mythic exception: faith CAN persist during starvation.
        # But not indefinitely.  "Theodicy pressure" — if the Oracle's
        # domain is belief but reality contradicts belief, eventually
        # faith erodes.  Slowly in mythic mode.

        if mat == MaterialState.COLLAPSED:
            b = state.belief
            # Theodicy pressure: prolonged suffering → faith erosion
            # Rate depends on how long material has been collapsed.
            # We approximate via resource_pressure (higher = longer crisis feel)
            theodicy_intensity = state.physical.resource_pressure / 100.0
            # At rp=100, faith loses ~0.15/tick (slow but inevitable)
            # At rp=60, faith loses ~0.09/tick
            if b.public_faith > 20.0:
                faith_drain = theodicy_intensity * 0.15
                _correct("belief", "public_faith", -faith_drain,
                         "theodicy_pressure")
            # Interpretation divergence rises as people seek meaning
            if b.interpretation_divergence < 80.0:
                div_rise = theodicy_intensity * 0.08
                _correct("belief", "interpretation_divergence", div_rise,
                         "theodicy_divergence")

        elif mat == MaterialState.STRAINED:
            b = state.belief
            if b.public_faith > 70.0 and state.physical.resource_pressure > 60:
                _correct("belief", "public_faith", -0.05,
                         "material_strain_faith_pressure")

        # ────────────────────────────────────────────────────────
        # 4. ENFORCEMENT WITHOUT RESOURCES
        # ────────────────────────────────────────────────────────
        #
        # You can't maintain 75% enforcement with 0 treasury and
        # 0 food.  Soldiers need to eat.

        if mat == MaterialState.COLLAPSED:
            # Enforcement ceiling: depends on treasury and food
            # With both at 0, max sustainable enforcement is ~15 (personal loyalty)
            # With some treasury, ceiling is higher
            enforce_ceiling = 15.0 + min(state.physical.treasury, 500.0) / 500.0 * 25.0
            if pol.enforcement_capacity > enforce_ceiling:
                overshoot = pol.enforcement_capacity - enforce_ceiling
                enforce_drain = min(overshoot * 0.08, 1.0)
                _correct("political", "enforcement_capacity", -enforce_drain,
                         "enforcement_without_resources")

        elif mat == MaterialState.STRAINED:
            if pol.enforcement_capacity > 65.0 and state.physical.treasury < 200:
                _correct("political", "enforcement_capacity", -0.1,
                         "enforcement_resource_strain")

        # ────────────────────────────────────────────────────────
        # 5. DAMPENING CURVES — PREVENT PERMANENT SATURATION
        # ────────────────────────────────────────────────────────
        #
        # Values near 0 or 100 experience mean-reversion pressure.
        # This prevents variables from pinning permanently.
        # Strength: weak enough that strong forces can still push
        # to extremes, but prevents "dead" variables.

        cls._dampen_extremes(state, ledger, tick)

        # ────────────────────────────────────────────────────────
        # 6. POPULATION PRESSURE (implicit)
        # ────────────────────────────────────────────────────────
        #
        # Prolonged famine reduces labor_pool, which eventually
        # reduces resource_pressure (fewer mouths to feed).
        # This is the recovery pathway.

        if mat == MaterialState.COLLAPSED:
            p = state.physical
            if p.labor_pool > 10.0:
                # Population decline from starvation
                # Scales with resource pressure: higher rp = faster decline
                # Phase 7E: Increased from 0.05+0.15 to 0.1+0.25 so population
                # actually bottoms out within reasonable collapse duration
                pop_loss = 0.1 + (p.resource_pressure / 100.0) * 0.25
                _correct("physical", "labor_pool", -pop_loss,
                         "famine_population_decline")
            # Fewer people → less food needed → food_production more effective
            if p.labor_pool < 35.0:
                pop_fraction = (35.0 - p.labor_pool) / 35.0  # 0→1 as pop drops
                prod_boost = pop_fraction * 0.15
                _correct("physical", "food_production", prod_boost,
                         "population_decline_production_rebalance")

            # ── Deep Population Collapse Reset ─────────────────
            # When population crashes hard, the social fabric
            # simplifies.  Fewer elites competing → less corruption.
            # Fewer factions → less ideological fragmentation.
            # Fewer mouths → less tension over scarce resources.
            # This is the demographic reset that makes rebirth possible.
            if p.labor_pool < 25.0:
                pop_frac = (25.0 - p.labor_pool) / 25.0  # 0→1

                # Tension drops: fewer people = fewer competing interests
                if s.class_tension > 20.0:
                    tension_reset = pop_frac * 0.3
                    _correct("social", "class_tension", -tension_reset,
                             "population_collapse_tension_reset")

                # Corruption drops: fewer elites, less to steal
                if pol.corruption > 15.0:
                    corrupt_reset = pop_frac * 0.2
                    _correct("political", "corruption", -corrupt_reset,
                             "population_collapse_corruption_reset")

                # Divergence drops: smaller community, simpler doctrine
                if b.interpretation_divergence > 20.0:
                    div_reset = pop_frac * 0.15
                    _correct("belief", "interpretation_divergence", -div_reset,
                             "population_collapse_divergence_reset")

                # Fear drops: nothing left to fear when there's nothing left
                if s.fear_level > 15.0:
                    fear_reset = pop_frac * 0.2
                    _correct("social", "fear_level", -fear_reset,
                             "population_collapse_fear_reset")

        # ────────────────────────────────────────────────────────
        # 7. EXTERNAL THREAT COHERENCE
        # ────────────────────────────────────────────────────────
        #
        # external_threat=100 without military capacity is conquest.
        # If enforcement is low and external_threat is high,
        # the kingdom is losing sovereignty.

        if pol.external_threat > 70 and pol.enforcement_capacity < 30:
            # Sovereignty erosion: legitimacy + institutional_strength decay
            sovereignty_pressure = (pol.external_threat - 70.0) / 30.0
            weakness = (30.0 - pol.enforcement_capacity) / 30.0
            drain = sovereignty_pressure * weakness * 0.3
            _correct("political", "legitimacy", -drain,
                     "sovereignty_erosion_legitimacy")
            _correct("political", "institutional_strength", -drain * 0.5,
                     "sovereignty_erosion_institutions")

        # ── 7b. Tiny kingdom = low strategic value ─────────────
        # Neighbours don't threaten a depopulated ruin.  External
        # threat should decay when there's nothing worth conquering.
        # labor<20 = basically a hamlet; ext_threat decays toward 25.
        p = state.physical
        if p.labor_pool < 20.0 and pol.external_threat > 25.0:
            irrelevance = (20.0 - p.labor_pool) / 20.0  # 0→1
            threat_decay = irrelevance * 0.4
            _correct("political", "external_threat", -threat_decay,
                     "depopulation_reduces_strategic_value")

    @classmethod
    def _dampen_extremes(cls, state: "KingdomState",
                          ledger: "CausalLedger", tick: int):
        """
        Soft mean-reversion for variables pinned at extremes.

        Variables at 0 get a tiny upward push.
        Variables at 100 get a tiny downward push.

        Strength is 0.05/tick — easily overwhelmed by real forces,
        but prevents permanent death of any variable.

        Exception: During material COLLAPSE, upward dampening is
        suppressed for variables that should legitimately be low
        (cohesion, hope, legitimacy, faith).  Dampening should not
        fight collapse corrections.

        Exceptions: food_stores (can genuinely be 0), treasury,
        resource_pressure (derived, not dampened).
        """
        _c = lambda v, lo=0.0, hi=100.0: max(lo, min(hi, v))
        mat = cls.classify_material(state)

        # Variables that should NOT be dampened at all
        NO_DAMPEN = {"food_stores", "treasury", "resource_pressure",
                     "myth_accumulation", "sacred_silence_weight",
                     "labor_allocation"}

        # Variables where upward dampening is suppressed during collapse
        # (they should be allowed to stay low when material is gone)
        COLLAPSE_SUPPRESS_UP = {"cohesion", "hope_level", "legitimacy",
                                "public_faith", "institutional_strength"}

        DAMPEN_STRENGTH = 0.05
        DAMPEN_ZONE = 5.0  # only active within 5 points of 0 or 100

        suppress_up = (mat == MaterialState.COLLAPSED)

        for layer_name in ("social", "political", "belief"):
            layer = getattr(state, layer_name, None)
            if layer is None:
                continue
            for var_name in vars(layer):
                if var_name.startswith("_") or var_name in NO_DAMPEN:
                    continue
                val = getattr(layer, var_name)
                if not isinstance(val, (int, float)):
                    continue

                delta = 0.0
                if val < DAMPEN_ZONE:
                    # Suppress upward dampening during collapse for key vars
                    if suppress_up and var_name in COLLAPSE_SUPPRESS_UP:
                        continue
                    delta = (DAMPEN_ZONE - val) / DAMPEN_ZONE * DAMPEN_STRENGTH
                elif val > (100.0 - DAMPEN_ZONE):
                    delta = -((val - (100.0 - DAMPEN_ZONE)) / DAMPEN_ZONE * DAMPEN_STRENGTH)

                if abs(delta) > 1e-6:
                    old = val
                    new = _c(val + delta)
                    if abs(new - old) > 1e-6:
                        setattr(layer, var_name, new)
                        ledger.record_delta(
                            source_type="coherence",
                            source_id="dampening",
                            target_type="layer",
                            target_id=state.kingdom_id,
                            variable=var_name,
                            delta=new - old,
                            tick=tick,
                            metadata={"zone": "low" if val < DAMPEN_ZONE else "high"},
                        )

        # Physical layer: only dampen select variables
        phys_dampen = {"food_production", "infrastructure", "trade_volume",
                       "labor_pool"}
        p = state.physical
        for var_name in phys_dampen:
            val = getattr(p, var_name, None)
            if val is None or not isinstance(val, (int, float)):
                continue
            delta = 0.0
            if val < DAMPEN_ZONE:
                # During collapse, don't dampen labor_pool upward
                # (population should be allowed to decline)
                if suppress_up and var_name == "labor_pool":
                    continue
                delta = (DAMPEN_ZONE - val) / DAMPEN_ZONE * DAMPEN_STRENGTH
            elif val > (100.0 - DAMPEN_ZONE):
                delta = -((val - (100.0 - DAMPEN_ZONE)) / DAMPEN_ZONE * DAMPEN_STRENGTH)
            if abs(delta) > 1e-6:
                old = val
                new = _c(val + delta)
                if abs(new - old) > 1e-6:
                    setattr(p, var_name, new)
                    ledger.record_delta(
                        source_type="coherence",
                        source_id="dampening",
                        target_type="layer",
                        target_id=state.kingdom_id,
                        variable=var_name,
                        delta=new - old,
                        tick=tick,
                        metadata={"zone": "low" if val < DAMPEN_ZONE else "high"},
                    )


# ── 4. Power Gradient Recalibration ───────────────────────────
#
# Long-term neighbour ranking.  If a neighbour maintains stability
# and power for many ticks, their influence radius increases
# permanently.  They become regional anchors.  Diplomatic baselines
# shift.  The world evolves hierarchically.

@dataclass
class NeighbourPowerRank:
    """
    Long-term power accumulation for a neighbour kingdom.

    This is NOT the per-tick InterKingdomVector — it's the permanent
    power gradient that determines structural relationships.
    """
    kingdom_id: str
    stability_score: float = 50.0       # accumulated stability (0-100)
    influence_radius: float = 1.0       # multiplier on influence vectors
    is_regional_anchor: bool = False    # becomes anchor at high stability
    diplomatic_baseline: float = 0.0    # permanent diplomatic bias (-1 to 1)
    myth_resonance: float = 0.0         # how much their faith narrative matters
    ticks_tracked: int = 0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "NeighbourPowerRank":
        obj = cls(kingdom_id=d.get("kingdom_id", ""))
        for k, v in d.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj


class PowerGradientEngine:
    """
    Recalibrates neighbour power rankings over long periods.

    Called at yearly boundaries.  Neighbour stability is derived
    deterministically from their seed + elapsed time (lazy evaluation).
    """

    # How many years to become a regional anchor
    ANCHOR_THRESHOLD_YEARS: int = 10
    ANCHOR_STABILITY_THRESHOLD: float = 70.0

    @classmethod
    def recalibrate(cls, world_state: "WorldState",
                    power_ranks: Dict[str, NeighbourPowerRank],
                    rng: SeededRNG) -> Dict[str, NeighbourPowerRank]:
        """
        Update power rankings for all neighbours.

        Called at year boundary.  Derives neighbour stability from
        seed + time (lazy — no full simulation).
        """
        player = world_state.player_kingdom

        for nid, nseed in world_state.neighbour_seeds.items():
            if nid not in power_ranks:
                power_ranks[nid] = NeighbourPowerRank(kingdom_id=nid)

            rank = power_ranks[nid]
            rank.ticks_tracked = player.tick

            # Derive neighbour stability from seed + time
            nrng = SeededRNG(nseed + player.tick // 365)
            base_stability = nrng.uniform(30, 80)

            # Neighbour stability is inversely correlated with
            # player's instability (weak player attracts strong neighbours)
            player_health = player.health.composite
            stability_boost = (100.0 - player_health) * 0.1
            derived_stability = min(100.0, base_stability + stability_boost)

            # Smooth update: stability drifts slowly
            rank.stability_score += (derived_stability - rank.stability_score) * 0.1
            rank.stability_score = max(0.0, min(100.0, rank.stability_score))

            # Influence radius grows with sustained stability
            if rank.stability_score > 60:
                rank.influence_radius = min(3.0, rank.influence_radius + 0.02)
            elif rank.stability_score < 40:
                rank.influence_radius = max(0.5, rank.influence_radius - 0.01)

            # Regional anchor status
            years_tracked = rank.ticks_tracked // 365
            if (rank.stability_score >= cls.ANCHOR_STABILITY_THRESHOLD and
                    years_tracked >= cls.ANCHOR_THRESHOLD_YEARS):
                if not rank.is_regional_anchor:
                    rank.is_regional_anchor = True
                    # Becoming an anchor permanently shifts diplomatic baseline
                    rank.diplomatic_baseline -= 0.1  # they become more demanding

            # Myth resonance: stable neighbours build competing faith narratives
            rank.myth_resonance += rank.stability_score * 0.001
            rank.myth_resonance = min(10.0, rank.myth_resonance)

            # Diplomatic baseline drifts based on relative power
            power_diff = (rank.stability_score - player_health) / 100.0
            rank.diplomatic_baseline += power_diff * 0.02
            rank.diplomatic_baseline = max(-1.0, min(1.0, rank.diplomatic_baseline))

        return power_ranks

    @classmethod
    def modify_influence_vectors(cls, vectors: List[InterKingdomVector],
                                  power_ranks: Dict[str, NeighbourPowerRank]):
        """
        Scale influence vectors by power gradient rankings.

        Regional anchors exert stronger influence.
        High-stability neighbours have amplified vectors.
        """
        for vec in vectors:
            rank = power_ranks.get(vec.kingdom_id)
            if not rank:
                continue

            # Apply influence radius multiplier
            vec.military_pressure *= rank.influence_radius
            vec.trade_pressure *= rank.influence_radius
            vec.cultural_pressure *= rank.influence_radius
            vec.myth_pressure *= rank.influence_radius

            # Diplomatic stance shifted by permanent baseline
            vec.diplomatic_stance = max(-1.0, min(1.0,
                vec.diplomatic_stance + rank.diplomatic_baseline
            ))

            # Regional anchors apply extra myth pressure
            if rank.is_regional_anchor:
                vec.myth_pressure += rank.myth_resonance * 0.5


# ── 5. Intergenerational Value Drift ──────────────────────────
#
# When characters die and successors arise, the successor's
# personality is NOT random.  It is biased by the era they
# grew up in.  A successor born during AUTHORITARIAN_CONSOLIDATION
# has higher base authoritarianism.  This creates ideological
# evolution across generations.

# Era → personality bias: maps era identity to personality trait
# modifiers applied to successors born during that era.

ERA_PERSONALITY_BIAS: Dict[str, Dict[str, float]] = {
    "STABLE": {},
    "RENAISSANCE": {
        "piety": -3.0,         # more secular
        "pragmatism": 5.0,     # more practical
        "ambition": 3.0,       # inspired by progress
        "cruelty": -2.0,       # softer governance
    },
    "FAMINE_ERA": {
        "risk_tolerance": -5.0,  # survival makes you cautious
        "pragmatism": 5.0,       # necessity breeds practicality
        "cruelty": 3.0,          # scarcity hardens
        "ambition": -2.0,        # survival over glory
    },
    "AUTHORITARIAN_CONSOLIDATION": {
        "risk_tolerance": -5.0,    # obedience is safety
        "piety": 3.0,             # authority and faith align
        "cruelty": 5.0,           # enforcement normalised
        "ambition": 5.0,          # power is the path
        "charisma": -3.0,         # competence > charm
    },
    "IDEOLOGICAL_FRACTURE": {
        "piety": -5.0,            # faith collapsed around them
        "risk_tolerance": 5.0,    # nothing to lose
        "pragmatism": -3.0,       # ideology over practice
        "ambition": 3.0,          # faction leaders rise
    },
    "GOLDEN_AGE": {
        "charisma": 5.0,          # social skills valued
        "ambition": 3.0,          # raised in opportunity
        "cruelty": -5.0,          # prosperity softens
        "risk_tolerance": 3.0,    # confidence breeds boldness
    },
    "DECLINE": {
        "pragmatism": 5.0,        # survival mode
        "ambition": -5.0,         # cynicism prevails
        "cruelty": 3.0,           # desperation hardens
        "risk_tolerance": -3.0,   # fear of further collapse
    },
    "OLIGARCHIC_GRIP": {
        "ambition": 5.0,          # power-seeking normalised
        "cruelty": 3.0,           # exploitation accepted
        "piety": -3.0,            # wealth > faith
        "charisma": 3.0,          # networking essential
    },
    "MILITANT_POSTURE": {
        "risk_tolerance": 5.0,    # military courage
        "cruelty": 3.0,           # war normalises violence
        "piety": 3.0,             # soldiers pray
        "pragmatism": 3.0,        # tactical thinking
        "ambition": -2.0,         # duty over personal gain
    },
    "REFORMATION": {
        "pragmatism": 5.0,        # reform requires practicality
        "ambition": 3.0,          # change-makers
        "piety": -3.0,            # questioning tradition
        "risk_tolerance": 5.0,    # reformers take risks
        "cruelty": -3.0,          # reform is compassionate
    },
}


class IntergenerationalDrift:
    """
    Biases successor personality based on the era they were born in.

    Called by the SuccessionEngine when generating replacements.
    The predecessor's traits provide the base; the era biases the
    direction of variance.
    """

    @classmethod
    def bias_successor(cls, successor: Character, era: EraIdentity,
                       rng: SeededRNG):
        """
        Apply era-based personality bias to a newly created successor.

        This should be called AFTER the SuccessionEngine generates the
        base successor (which inherits variance from predecessor).
        """
        biases = ERA_PERSONALITY_BIAS.get(era.name, {})
        if not biases:
            return

        bias_rng = rng.fork(f"era_bias_{successor.character_id}")

        for trait, bias in biases.items():
            if not hasattr(successor, trait):
                continue
            current = getattr(successor, trait)
            # Apply bias with some randomness (not deterministic shift)
            actual_bias = bias * bias_rng.uniform(0.5, 1.5)
            new_val = max(5.0, min(95.0, current + actual_bias))
            setattr(successor, trait, new_val)

    @classmethod
    def bias_faction_loyalty(cls, successor: Character, era: EraIdentity,
                              faction: Optional["Faction"],
                              state: "KingdomState", rng: SeededRNG):
        """
        Additionally bias oracle_loyalty based on how the Oracle fared
        during this era.

        If the kingdom is declining under the Oracle's watch,
        the new generation has lower loyalty.  If thriving, higher.
        """
        health = state.health.composite
        trend = state.health.trend

        loyalty_bias = 0.0

        # Health-based bias
        if health > 70:
            loyalty_bias += 5.0   # "Oracle brought prosperity"
        elif health < 35:
            loyalty_bias -= 8.0   # "Oracle failed us"

        # Trend-based bias
        if trend == "rising":
            loyalty_bias += 3.0
        elif trend == "declining":
            loyalty_bias -= 5.0

        # Era-specific bias
        if era == EraIdentity.GOLDEN_AGE:
            loyalty_bias += 5.0
        elif era in (EraIdentity.DECLINE, EraIdentity.FAMINE_ERA):
            loyalty_bias -= 5.0
        elif era == EraIdentity.IDEOLOGICAL_FRACTURE:
            loyalty_bias -= 8.0

        bias_rng = rng.fork(f"loyalty_bias_{successor.character_id}")
        loyalty_bias *= bias_rng.uniform(0.6, 1.4)

        successor.oracle_loyalty = max(5.0, min(95.0,
            successor.oracle_loyalty + loyalty_bias
        ))


# ============================================================
# SECTION 7.10: TERMINAL RESOLUTION ENGINE
# ============================================================
#
# Phase 7: Collapse is not an equilibrium.  If the kingdom stays
# in material COLLAPSED with health < 10 for long enough, it
# undergoes structural transformation — not more of the same.
#
# Three terminal outcomes:
#   SOVEREIGNTY_LOST — a neighbour conquers the kingdom, external
#       control imposed.  Kingdom becomes a vassal state.
#   KINGDOM_FRAGMENTED — internal factions rip the polity apart.
#       Territory and population split; what remains is smaller
#       but potentially viable.
#   REBIRTH_NASCENT — after enough depopulation, survivors build
#       something new.  Baselines reset, scars remain, identity
#       changes.  A founding moment.
#
# Each outcome mechanically transforms the KingdomState:
# new era, new baselines, layer resets, power-rank changes,
# and a massive causal-ledger entry.
#
# Terminal states are TRANSFORMATIVE, not game-ending.
# After resolution, simulation continues in a structurally
# different configuration.

class TerminalOutcome(Enum):
    """Post-collapse structural transformations."""
    NONE = auto()                # no terminal resolution pending
    SOVEREIGNTY_LOST = auto()    # conquered / vassalised by external power
    KINGDOM_FRAGMENTED = auto()  # internal faction schism splits the polity
    REBIRTH_NASCENT = auto()     # survivors found a new order from the ashes


@dataclass
class TerminalResolutionRecord:
    """
    Permanent historical record of a terminal transformation.

    Stored on KingdomState — this is the kingdom's deepest scar:
    the record that it died and was reborn as something else.
    """
    outcome: str                      # TerminalOutcome name
    triggered_tick: int
    collapse_duration_ticks: int      # how long health < threshold
    health_at_trigger: float
    conditions_snapshot: Dict[str, float] = field(default_factory=dict)
    description: str = ""
    new_era: str = ""                 # era the kingdom transitioned to
    layer_resets: Dict[str, float] = field(default_factory=dict)  # what was reset and to what

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "TerminalResolutionRecord":
        obj = cls(
            outcome=d.get("outcome", "NONE"),
            triggered_tick=d.get("triggered_tick", 0),
            collapse_duration_ticks=d.get("collapse_duration_ticks", 0),
            health_at_trigger=d.get("health_at_trigger", 0.0),
        )
        obj.conditions_snapshot = d.get("conditions_snapshot", {})
        obj.description = d.get("description", "")
        obj.new_era = d.get("new_era", "")
        obj.layer_resets = d.get("layer_resets", {})
        return obj


# ── Terminal Resolution Condition Tables ──────────────────────

# Minimum ticks of continuous collapse (health < threshold) before
# terminal resolution can fire.  Prevents premature transformation
# from brief crises.
TERMINAL_COLLAPSE_HEALTH_THRESHOLD = 12.0
TERMINAL_COLLAPSE_DURATION_MIN = 200  # ~200 ticks at 7 days/tick ≈ 3.8 years

# Conditions for each outcome.  Checked in priority order.
# First match wins (can only undergo one terminal transformation
# per collapse cycle).
#
# Phase 7A: REBIRTH is checked FIRST but gated behind
# min_prior_resolutions=2, so it auto-skips for the first two
# resolutions.  Once the kingdom has tried conquest/fragmentation
# and failed, rebirth becomes the preferred path.

TERMINAL_CONDITIONS: List[Dict[str, Any]] = [
    # ── REBIRTH_NASCENT (checked first, gated) ────────────────
    # Population has bottomed out; survivors forge something new.
    # Requires: low population + at least 2 prior resolutions
    #           (the kingdom must have already tried conquest/fragmentation
    #            and failed — rebirth is the last resort, not the first).
    # This is the "phoenix" path — the least destructive transformation.
    {
        "outcome": TerminalOutcome.REBIRTH_NASCENT,
        "conditions": {
            "labor_pool_max": 35.0,
        },
        # Shorter incubation than base — by this point the kingdom has
        # already spent 1000+ ticks collapsing through prior resolutions.
        "collapse_duration_min": TERMINAL_COLLAPSE_DURATION_MIN,
        # Gate: only available after 2+ prior resolutions
        "min_prior_resolutions": 2,
    },
    # ── SOVEREIGNTY_LOST ──────────────────────────────────────
    # External power conquers the weakened kingdom.
    # Requires: high external threat + very low enforcement + low institutions
    {
        "outcome": TerminalOutcome.SOVEREIGNTY_LOST,
        "conditions": {
            "external_threat_min": 65.0,
            "enforcement_capacity_max": 20.0,
            "institutional_strength_max": 15.0,
        },
        "collapse_duration_min": TERMINAL_COLLAPSE_DURATION_MIN,
    },
    # ── KINGDOM_FRAGMENTED ────────────────────────────────────
    # Internal factions rip the kingdom apart.
    # Requires: high faction divergence + low cohesion + low legitimacy
    {
        "outcome": TerminalOutcome.KINGDOM_FRAGMENTED,
        "conditions": {
            "cohesion_max": 15.0,
            "legitimacy_max": 15.0,
            "class_tension_min": 50.0,
        },
        "collapse_duration_min": TERMINAL_COLLAPSE_DURATION_MIN,
    },
]


class TerminalResolutionEngine:
    """
    Detects and executes post-collapse structural transformations.

    Called every tick after StateCoherenceEngine.  Tracks how long
    the kingdom has been in continuous collapse.  When duration +
    co-conditions are met, triggers an irreversible transformation
    that restructures the kingdom mechanically.

    After transformation, the collapse counter resets and the
    kingdom enters a new structural phase.  Simulation continues.
    """

    # ── Collapse Duration Tracking ─────────────────────────────

    # Minimum ticks between consecutive terminal resolutions.
    # After a transformation the kingdom gets time to stabilize.
    RESOLUTION_COOLDOWN = 500  # ~500 ticks ≈ 9.6 years

    # Each successive resolution requires this many ADDITIONAL ticks
    # of collapse.  First resolution: base.  Second: base + escalation.
    # Third: base + 2×escalation.  Prevents infinite cycling.
    DURATION_ESCALATION_PER_RESOLUTION = 150

    # Maximum number of terminal resolutions before the engine stops
    # trying.  The kingdom that has fragmented, been conquered, and
    # reborn multiple times eventually stabilizes in whatever form remains.
    MAX_RESOLUTIONS = 5

    @classmethod
    def track_collapse(cls, state: "KingdomState") -> int:
        """
        Increment or reset the collapse duration counter.

        Returns the current collapse duration in ticks.
        """
        if state.health.composite < TERMINAL_COLLAPSE_HEALTH_THRESHOLD:
            state.collapse_duration += 1
        else:
            # Recovery — reset collapse counter
            if state.collapse_duration > 0:
                _dbg(f"Collapse recovery at tick {state.tick} after "
                     f"{state.collapse_duration} ticks of collapse")
            state.collapse_duration = 0
        return state.collapse_duration

    # ── Terminal Condition Evaluation ──────────────────────────

    @classmethod
    def evaluate(cls, state: "KingdomState",
                 world_state: Optional["WorldState"] = None
                 ) -> Optional[TerminalOutcome]:
        """
        Check if any terminal resolution condition is met.

        Returns the first matching TerminalOutcome, or None.

        Guards:
        - Cooldown: must be at least RESOLUTION_COOLDOWN ticks since
          the last terminal resolution.
        - Escalation: each successive resolution requires longer
          collapse duration.
        - Cap: after MAX_RESOLUTIONS, no more transformations fire.
        """
        n_previous = len(state.terminal_resolutions)

        # ── Max cap ────────────────────────────────────────────
        if n_previous >= cls.MAX_RESOLUTIONS:
            return None

        # ── Cooldown check ─────────────────────────────────────
        if n_previous > 0:
            last_tick = state.terminal_resolutions[-1].triggered_tick
            if (state.tick - last_tick) < cls.RESOLUTION_COOLDOWN:
                return None

        # ── Escalated duration requirement ─────────────────────
        duration = state.collapse_duration
        escalation = n_previous * cls.DURATION_ESCALATION_PER_RESOLUTION

        for rule in TERMINAL_CONDITIONS:
            min_duration = rule.get("collapse_duration_min",
                                    TERMINAL_COLLAPSE_DURATION_MIN)
            # Apply escalation: each prior resolution raises the bar
            effective_min = min_duration + escalation
            if duration < effective_min:
                continue

            # ── Phase 7A: Prior-resolution gate ────────────────
            # Some outcomes (e.g. REBIRTH) require N prior resolutions.
            min_prior = rule.get("min_prior_resolutions", 0)
            if n_previous < min_prior:
                continue

            # Check co-conditions
            conditions = rule["conditions"]
            all_met = True
            for cond_key, cond_val in conditions.items():
                actual = cls._resolve_condition(state, cond_key)
                if actual is None:
                    all_met = False
                    break
                if cond_key.endswith("_min") and actual < cond_val:
                    all_met = False
                    break
                if cond_key.endswith("_max") and actual > cond_val:
                    all_met = False
                    break

            if all_met:
                return rule["outcome"]

        return None

    @classmethod
    def _resolve_condition(cls, state: "KingdomState",
                           cond_key: str) -> Optional[float]:
        """Resolve a condition key like 'external_threat_min' to a value."""
        # Strip _min/_max suffix to get variable name
        var_name = cond_key
        for suffix in ("_min", "_max"):
            if var_name.endswith(suffix):
                var_name = var_name[:-len(suffix)]
                break

        # Search layers
        for layer_name in ("physical", "social", "political", "belief"):
            layer = getattr(state, layer_name, None)
            if layer and hasattr(layer, var_name):
                return float(getattr(layer, var_name))

        # Health composite
        if var_name == "health_composite":
            return state.health.composite

        return None

    # ── Terminal Resolution Execution ──────────────────────────

    @classmethod
    def execute(cls, outcome: TerminalOutcome,
                state: "KingdomState",
                world_state: Optional["WorldState"] = None):
        """
        Execute a terminal transformation.

        This is a one-time structural reset.  It:
        1. Logs a TerminalResolutionRecord
        2. Resets layer values to post-transformation state
        3. Creates massive baseline shifts
        4. Forces era transition
        5. Records in causal ledger
        6. Resets collapse counter
        7. Fires SimEvents for the event history
        """
        _dbg(f"╔══ TERMINAL RESOLUTION: {outcome.name} at tick {state.tick} ══╗")

        snapshot = cls._snapshot_conditions(state)
        record = TerminalResolutionRecord(
            outcome=outcome.name,
            triggered_tick=state.tick,
            collapse_duration_ticks=state.collapse_duration,
            health_at_trigger=state.health.composite,
            conditions_snapshot=snapshot,
        )

        if outcome == TerminalOutcome.SOVEREIGNTY_LOST:
            cls._execute_sovereignty_lost(state, record, world_state)
        elif outcome == TerminalOutcome.KINGDOM_FRAGMENTED:
            cls._execute_fragmentation(state, record, world_state)
        elif outcome == TerminalOutcome.REBIRTH_NASCENT:
            cls._execute_rebirth(state, record, world_state)

        # ── Common post-transformation bookkeeping ─────────────
        state.terminal_resolutions.append(record)

        # Reset collapse counter — new chapter begins
        state.collapse_duration = 0

        # Grace period: suppress coherence engine's collapse-state
        # drains for a while so the transformation has time to take hold.
        # 300 ticks ≈ ~6 years of stabilization.
        GRACE_PERIOD = 300
        state.terminal_grace_until = state.tick + GRACE_PERIOD

        # Force era transition to the new era
        if record.new_era:
            new_era = EraIdentity[record.new_era]
            if state.era_history:
                state.era_history[-1].ended_tick = state.tick
            era_rec = EraRecord(
                era=new_era.name,
                started_tick=state.tick,
                health_at_start=state.health.composite,
                trigger_conditions=snapshot,
            )
            state.era_history.append(era_rec)
            state.current_era = new_era

        # Record the transformation in causal ledger
        state.causal_ledger.record_delta(
            source_type="terminal_resolution",
            source_id=f"terminal_{outcome.name}_{state.tick}",
            target_type="kingdom",
            target_id=state.kingdom_id,
            variable="structural_identity",
            delta=1.0,
            tick=state.tick,
            metadata={
                "outcome": outcome.name,
                "collapse_duration": record.collapse_duration_ticks,
                "health_at_trigger": record.health_at_trigger,
                "new_era": record.new_era,
                "description": record.description,
            },
        )

        # Fire a SimEvent so it appears in history and narrative
        terminal_event = SimEvent(
            event_id=f"terminal_{outcome.name}_{state.tick}",
            kind=EventKind.TERMINAL,
            domain=EventDomain.POLITICAL,
            severity=100.0,
            urgency=100.0,
            tick=state.tick,
            description=record.description,
            policy_vector={
                "structural_transformation": 1.0,
            },
        )
        state.active_events.push(terminal_event)
        state.event_history.append(terminal_event)

        _dbg(f"╚══ {outcome.name}: {record.description} ══╝")

    # ── Outcome Implementations ────────────────────────────────

    @classmethod
    def _execute_sovereignty_lost(cls, state: "KingdomState",
                                   record: TerminalResolutionRecord,
                                   world_state: Optional["WorldState"]):
        """
        SOVEREIGNTY_LOST: External power imposes control.

        Mechanical effects:
        - External threat drops (the conqueror is now *in charge*)
        - Enforcement becomes externally imposed (rises to moderate)
        - Legitimacy collapses further (imposed rule is illegitimate)
        - Institutional strength gets partially rebuilt (conqueror's)
        - Treasury gets a tribute injection (conqueror invests)
        - Cohesion gets a small rally-against-occupier boost
        - Trade volume recovers partially (conqueror's trade network)
        - Food gets partial relief (administered supply)
        - Cultural confidence drops (subjugation)
        - Public faith may rally (suffering = martyrdom narrative)
        """
        _c = lambda v, lo=0.0, hi=100.0: max(lo, min(hi, v))
        p = state.physical
        s = state.social
        pol = state.political
        b = state.belief

        resets: Dict[str, float] = {}

        # External threat drops — the threat has arrived and won
        old_et = pol.external_threat
        pol.external_threat = _c(25.0)
        resets["external_threat"] = pol.external_threat

        # Enforcement imposed by occupier
        old_enf = pol.enforcement_capacity
        pol.enforcement_capacity = _c(45.0)
        resets["enforcement_capacity"] = pol.enforcement_capacity

        # Legitimacy destroyed — imposed rule
        pol.legitimacy = _c(8.0)
        resets["legitimacy"] = pol.legitimacy

        # Institutional strength: conqueror rebuilds administrative control
        pol.institutional_strength = _c(30.0)
        resets["institutional_strength"] = pol.institutional_strength

        # Law rigidity rises — conqueror's law
        pol.law_rigidity = _c(55.0)
        resets["law_rigidity"] = pol.law_rigidity

        # Treasury injection — tribute economy
        p.treasury = max(p.treasury, 500.0)
        resets["treasury"] = p.treasury

        # Food relief — administered supply (enough to escape COLLAPSED)
        p.food_stores = _c(max(p.food_stores, 35.0))
        resets["food_stores"] = p.food_stores

        # Food production: occupier organizes farming (must be >50 for surplus)
        p.food_production = _c(max(p.food_production, 55.0))
        resets["food_production"] = p.food_production

        # Infrastructure rebuilt (occupier needs functional roads and trade routes)
        p.infrastructure = _c(max(p.infrastructure, 50.0))
        resets["infrastructure"] = p.infrastructure

        # Trade through conqueror's network (needs infra ≥ 50 to be neutral)
        p.trade_volume = _c(max(p.trade_volume, 40.0))
        resets["trade_volume"] = p.trade_volume

        # Resource pressure eases significantly — occupier brings supply chains
        p.resource_pressure = _c(min(p.resource_pressure, 40.0))
        resets["resource_pressure"] = p.resource_pressure

        # Labor pool: occupier brings settlers/garrison
        p.labor_pool = _c(max(p.labor_pool, 30.0))
        resets["labor_pool"] = p.labor_pool

        # Cohesion: rally effect against occupier
        s.cohesion = _c(max(s.cohesion, 20.0))
        resets["cohesion"] = s.cohesion

        # Hope: small rise — occupation is at least not chaos
        s.hope_level = _c(max(s.hope_level, 15.0))
        resets["hope_level"] = s.hope_level

        # Cultural confidence: subjugation is humiliating
        s.cultural_confidence = _c(min(s.cultural_confidence, 15.0))
        resets["cultural_confidence"] = s.cultural_confidence

        # Fear rises — occupier control
        s.fear_level = _c(max(s.fear_level, 50.0))
        resets["fear_level"] = s.fear_level

        # Class tension suppressed — occupier imposes order with force
        s.class_tension = _c(min(s.class_tension, 20.0))
        resets["class_tension"] = s.class_tension

        # Faith: martyrdom narrative — can rally
        b.public_faith = _c(max(b.public_faith, 25.0))
        resets["public_faith"] = b.public_faith

        # Interpretation divergence: occupier imposes doctrinal unity
        b.interpretation_divergence = _c(min(b.interpretation_divergence, 20.0))
        resets["interpretation_divergence"] = b.interpretation_divergence

        # Rumor distortion: foreign rule clarifies who the enemy is
        b.rumor_distortion = _c(min(b.rumor_distortion, 15.0))
        resets["rumor_distortion"] = b.rumor_distortion

        # Corruption: new administration is initially disciplined
        # (extractive later, but starts clean)
        pol.corruption = _c(min(pol.corruption, 20.0))
        resets["corruption"] = pol.corruption

        # ── Permanent baseline shifts from conquest ────────────
        conquest_baselines = [
            BaselineShift(
                shift_id=f"terminal_conquest_{state.tick}_legit",
                trigger_variable="terminal_resolution",
                trigger_threshold=0.0,
                trigger_direction="conquest",
                years_sustained=0,
                tick_applied=state.tick,
                target_variable="legitimacy",
                delta=-15.0,
                description="The foreign conquest shattered all claims to native sovereignty.",
                era_tag="SOVEREIGNTY_LOST",
            ),
            BaselineShift(
                shift_id=f"terminal_conquest_{state.tick}_cultural",
                trigger_variable="terminal_resolution",
                trigger_threshold=0.0,
                trigger_direction="conquest",
                years_sustained=0,
                tick_applied=state.tick,
                target_variable="cultural_confidence",
                delta=-10.0,
                description="Generations will remember the humiliation of foreign rule.",
                era_tag="SOVEREIGNTY_LOST",
            ),
            BaselineShift(
                shift_id=f"terminal_conquest_{state.tick}_enforce",
                trigger_variable="terminal_resolution",
                trigger_threshold=0.0,
                trigger_direction="conquest",
                years_sustained=0,
                tick_applied=state.tick,
                target_variable="enforcement_capacity",
                delta=8.0,
                description="The occupier's garrison became a permanent feature.",
                era_tag="SOVEREIGNTY_LOST",
            ),
        ]
        state.baseline_shifts.extend(conquest_baselines)

        # ── Institutional scars ────────────────────────────────
        conquest_scar = InstitutionalScar(
            scar_id=f"scar_conquest_{state.tick}",
            source_event_id=f"terminal_SOVEREIGNTY_LOST_{state.tick}",
            source_event_kind="TERMINAL_SOVEREIGNTY_LOST",
            source_event_description="The kingdom fell to foreign conquest.",
            tick_formed=state.tick,
            variable="legitimacy",
            delta=-10.0,
            description="The kingdom fell to foreign conquest. The memory is indelible.",
        )
        state.institutional_scars.append(conquest_scar)

        # ── Neighbour power recalibration ──────────────────────
        if world_state and world_state.neighbour_power_ranks:
            # The conquering power gains massively
            strongest_id = max(
                world_state.neighbour_power_ranks,
                key=lambda k: world_state.neighbour_power_ranks[k].stability_score,
                default=None,
            )
            if strongest_id:
                rank = world_state.neighbour_power_ranks[strongest_id]
                rank.stability_score = min(100.0, rank.stability_score + 20.0)
                rank.influence_radius = min(3.0, rank.influence_radius + 0.5)
                rank.is_regional_anchor = True
                rank.diplomatic_baseline = min(1.0, rank.diplomatic_baseline + 0.3)

        record.description = (
            f"The kingdom fell to foreign conquest after {record.collapse_duration_ticks} "
            f"ticks of collapse.  Sovereignty is lost.  An occupier now governs, "
            f"imposing order from without."
        )
        record.new_era = "AUTHORITARIAN_CONSOLIDATION"
        record.layer_resets = resets

    @classmethod
    def _execute_fragmentation(cls, state: "KingdomState",
                                record: TerminalResolutionRecord,
                                world_state: Optional["WorldState"]):
        """
        KINGDOM_FRAGMENTED: Factions tear the kingdom apart.

        Mechanical effects:
        - Labor pool hard halved (territory split)
        - Trade volume collapses then slowly recovers
        - Food gets a relative boost (fewer mouths)
        - Resource pressure drops sharply (fewer people)
        - Cohesion paradoxically rises (smaller, more homogeneous group)
        - Enforcement drops (half the army went with the other faction)
        - Legitimacy resets to moderate (new claimant)
        - Institutional strength drops (split bureaucracy)
        - Class tension drops (the malcontents left)
        - External threat rises (former countrymen are now a rival)
        """
        _c = lambda v, lo=0.0, hi=100.0: max(lo, min(hi, v))
        p = state.physical
        s = state.social
        pol = state.political
        b = state.belief

        resets: Dict[str, float] = {}

        # Population halved — the other half left
        # Floor at 15: a viable remnant population
        p.labor_pool = _c(max(p.labor_pool * 0.5, 15.0))
        resets["labor_pool"] = p.labor_pool

        # Resource pressure drops massively — fewer mouths
        p.resource_pressure = _c(min(p.resource_pressure * 0.3, 30.0))
        resets["resource_pressure"] = p.resource_pressure

        # Food stores: fewer mouths = relative abundance
        p.food_stores = _c(max(p.food_stores + 20.0, 35.0))
        resets["food_stores"] = p.food_stores

        # Food production: lost farmland but far fewer mouths (>50 = surplus)
        p.food_production = _c(max(p.food_production * 0.7, 52.0))
        resets["food_production"] = p.food_production

        # Infrastructure: core territory remains intact (floor at 45 for viable trade)
        p.infrastructure = _c(max(p.infrastructure * 0.6, 45.0))
        resets["infrastructure"] = p.infrastructure

        # Trade disrupted but internal trade resumes
        p.trade_volume = _c(max(p.trade_volume * 0.3, 15.0))
        resets["trade_volume"] = p.trade_volume

        # Treasury split
        p.treasury = max(p.treasury * 0.4, 50.0)
        resets["treasury"] = p.treasury

        # Cohesion rises — smaller but more homogeneous group
        s.cohesion = _c(max(s.cohesion, 35.0))
        resets["cohesion"] = s.cohesion

        # Class tension drops — the agitators split off
        s.class_tension = _c(min(s.class_tension, 25.0))
        resets["class_tension"] = s.class_tension

        # Hope rises — new beginning, smaller but viable
        s.hope_level = _c(max(s.hope_level, 25.0))
        resets["hope_level"] = s.hope_level

        # Fear drops — the oppressors may have left with the other half
        s.fear_level = _c(min(s.fear_level, 20.0))
        resets["fear_level"] = s.fear_level

        # Cultural confidence: damaged but not destroyed
        s.cultural_confidence = _c(max(s.cultural_confidence, 20.0))
        resets["cultural_confidence"] = s.cultural_confidence

        # Enforcement halved
        pol.enforcement_capacity = _c(pol.enforcement_capacity * 0.5)
        resets["enforcement_capacity"] = pol.enforcement_capacity

        # Legitimacy: reset — new claimant, contested but possible
        pol.legitimacy = _c(30.0)
        resets["legitimacy"] = pol.legitimacy

        # Institutional strength gutted
        pol.institutional_strength = _c(max(pol.institutional_strength * 0.4, 10.0))
        resets["institutional_strength"] = pol.institutional_strength

        # Law rigidity drops — need new laws for new entity
        pol.law_rigidity = _c(min(pol.law_rigidity, 25.0))
        resets["law_rigidity"] = pol.law_rigidity

        # External threat RISES — the breakaway is now a hostile neighbour
        pol.external_threat = _c(max(pol.external_threat, 50.0))
        resets["external_threat"] = pol.external_threat

        # Corruption drops — smaller polity, fresh start
        pol.corruption = _c(min(pol.corruption, 25.0))
        resets["corruption"] = pol.corruption

        # Faith: moderate — the schism may have been partly religious
        b.public_faith = _c(max(b.public_faith, 20.0))
        resets["public_faith"] = b.public_faith

        # Interpretation divergence drops — more homogeneous remnant
        b.interpretation_divergence = _c(min(b.interpretation_divergence, 20.0))
        resets["interpretation_divergence"] = b.interpretation_divergence

        # ── Remove some factions (they left with the breakaway) ──
        if len(state.factions) > 2:
            # Remove the weakest faction (they went with the splitters)
            weakest_id = min(
                state.factions,
                key=lambda fid: state.factions[fid].influence,
                default=None,
            )
            if weakest_id:
                removed = state.factions.pop(weakest_id)
                _dbg(f"Faction {removed.name} departed with the breakaway")

        # ── Baseline shifts from fragmentation ─────────────────
        frag_baselines = [
            BaselineShift(
                shift_id=f"terminal_frag_{state.tick}_cohesion",
                trigger_variable="terminal_resolution",
                trigger_threshold=0.0,
                trigger_direction="fragmentation",
                years_sustained=0,
                tick_applied=state.tick,
                target_variable="cohesion",
                delta=5.0,
                description="The smaller, homogeneous remnant found unity in shared loss.",
                era_tag="KINGDOM_FRAGMENTED",
            ),
            BaselineShift(
                shift_id=f"terminal_frag_{state.tick}_ext_threat",
                trigger_variable="terminal_resolution",
                trigger_threshold=0.0,
                trigger_direction="fragmentation",
                years_sustained=0,
                tick_applied=state.tick,
                target_variable="external_threat",
                delta=10.0,
                description="The breakaway state became a permanent rival on the border.",
                era_tag="KINGDOM_FRAGMENTED",
            ),
            BaselineShift(
                shift_id=f"terminal_frag_{state.tick}_trade",
                trigger_variable="terminal_resolution",
                trigger_threshold=0.0,
                trigger_direction="fragmentation",
                years_sustained=0,
                tick_applied=state.tick,
                target_variable="trade_volume",
                delta=-8.0,
                description="The fracture severed ancient trade routes permanently.",
                era_tag="KINGDOM_FRAGMENTED",
            ),
        ]
        state.baseline_shifts.extend(frag_baselines)

        # ── Scar ───────────────────────────────────────────────
        frag_scar = InstitutionalScar(
            scar_id=f"scar_fragmentation_{state.tick}",
            source_event_id=f"terminal_KINGDOM_FRAGMENTED_{state.tick}",
            source_event_kind="TERMINAL_KINGDOM_FRAGMENTED",
            source_event_description="Internal factions tore the kingdom apart.",
            tick_formed=state.tick,
            variable="institutional_strength",
            delta=-8.0,
            description="The kingdom shattered. Institutions were split in half.",
        )
        state.institutional_scars.append(frag_scar)

        # ── Create breakaway as new neighbour ──────────────────
        if world_state:
            breakaway_id = f"breakaway_{state.kingdom_id}_{state.tick}"
            breakaway_seed = state.seed ^ state.tick
            world_state.neighbour_seeds[breakaway_id] = breakaway_seed
            world_state.neighbour_power_ranks[breakaway_id] = NeighbourPowerRank(
                kingdom_id=breakaway_id,
                stability_score=35.0,
                influence_radius=1.2,
                is_regional_anchor=False,
                diplomatic_baseline=-0.4,  # hostile — they split from you
                myth_resonance=0.3,
            )

        record.description = (
            f"After {record.collapse_duration_ticks} ticks of collapse, internal "
            f"factions tore the kingdom apart.  A breakaway state formed.  "
            f"What remains is smaller, humbler, and possibly viable."
        )
        record.new_era = "DECLINE"  # fragmented kingdoms start in decline but can recover
        record.layer_resets = resets

    @classmethod
    def _execute_rebirth(cls, state: "KingdomState",
                          record: TerminalResolutionRecord,
                          world_state: Optional["WorldState"]):
        """
        REBIRTH_NASCENT: Survivors found a new order from the ashes.

        This is the phoenix path.  Population bottomed out, the old
        structures are gone, and what emerges is genuinely new.

        Mechanical effects:
        - Many variables reset to moderate "founding" values
        - Scars PERSIST (history is not erased)
        - Baseline shifts are massive — new starting conditions
        - Era becomes REFORMATION (rebuilding)
        - Cultural confidence gets a seed boost (founding myth)
        - Hope rises significantly (new beginning)
        - Corruption resets low (nothing to corrupt yet)
        - Institutions are rebuilt from scratch (low but growing)
        """
        _c = lambda v, lo=0.0, hi=100.0: max(lo, min(hi, v))
        p = state.physical
        s = state.social
        pol = state.political
        b = state.belief

        resets: Dict[str, float] = {}

        # Physical layer: modest but sustainable (food_production MUST be >50 for surplus)
        p.food_stores = _c(30.0)
        resets["food_stores"] = 30.0
        p.food_production = _c(52.0)
        resets["food_production"] = 52.0
        p.resource_pressure = _c(25.0)
        resets["resource_pressure"] = 25.0
        # Labor pool stays where it is (already low — that's the trigger)
        resets["labor_pool"] = p.labor_pool
        p.infrastructure = _c(40.0)
        resets["infrastructure"] = 40.0
        p.trade_volume = _c(15.0)
        resets["trade_volume"] = 15.0
        p.treasury = max(p.treasury, 300.0)
        resets["treasury"] = p.treasury

        # Social layer: hope and cohesion from shared survival
        s.cohesion = _c(45.0)
        resets["cohesion"] = 45.0
        s.class_tension = _c(15.0)
        resets["class_tension"] = 15.0
        s.hope_level = _c(50.0)
        resets["hope_level"] = 50.0
        s.fear_level = _c(10.0)
        resets["fear_level"] = 10.0
        s.cultural_confidence = _c(35.0)
        resets["cultural_confidence"] = 35.0
        s.literacy = _c(max(s.literacy, 20.0))  # knowledge partially preserved
        resets["literacy"] = s.literacy

        # Political layer: clean slate with minimal institutions
        pol.legitimacy = _c(40.0)
        resets["legitimacy"] = 40.0
        pol.enforcement_capacity = _c(20.0)
        resets["enforcement_capacity"] = 20.0
        pol.corruption = _c(5.0)
        resets["corruption"] = 5.0
        pol.institutional_strength = _c(15.0)
        resets["institutional_strength"] = 15.0
        pol.law_rigidity = _c(15.0)
        resets["law_rigidity"] = 15.0
        # External threat: low (nobody cares about a tiny remnant)
        pol.external_threat = _c(min(pol.external_threat, 25.0))
        resets["external_threat"] = pol.external_threat

        # Belief layer: the survival story becomes founding myth
        b.public_faith = _c(max(b.public_faith, 40.0))
        resets["public_faith"] = b.public_faith
        b.myth_accumulation = _c(min(b.myth_accumulation + 15.0, 100.0))
        resets["myth_accumulation"] = b.myth_accumulation
        b.interpretation_divergence = _c(15.0)
        resets["interpretation_divergence"] = 15.0
        b.cultural_memory_strength = _c(min(b.cultural_memory_strength + 10.0, 100.0))
        resets["cultural_memory_strength"] = b.cultural_memory_strength

        # ── Baseline shifts from rebirth ───────────────────────
        rebirth_baselines = [
            BaselineShift(
                shift_id=f"terminal_rebirth_{state.tick}_hope",
                trigger_variable="terminal_resolution",
                trigger_threshold=0.0,
                trigger_direction="rebirth",
                years_sustained=0,
                tick_applied=state.tick,
                target_variable="hope_level",
                delta=10.0,
                description="The founding generation carried unshakeable hope.",
                era_tag="REBIRTH_NASCENT",
            ),
            BaselineShift(
                shift_id=f"terminal_rebirth_{state.tick}_faith",
                trigger_variable="terminal_resolution",
                trigger_threshold=0.0,
                trigger_direction="rebirth",
                years_sustained=0,
                tick_applied=state.tick,
                target_variable="public_faith",
                delta=8.0,
                description="Survival was proof of the Oracle's blessing.",
                era_tag="REBIRTH_NASCENT",
            ),
            BaselineShift(
                shift_id=f"terminal_rebirth_{state.tick}_cultural",
                trigger_variable="terminal_resolution",
                trigger_threshold=0.0,
                trigger_direction="rebirth",
                years_sustained=0,
                tick_applied=state.tick,
                target_variable="cultural_confidence",
                delta=8.0,
                description="The survival story became the new cultural bedrock.",
                era_tag="REBIRTH_NASCENT",
            ),
            BaselineShift(
                shift_id=f"terminal_rebirth_{state.tick}_corrupt",
                trigger_variable="terminal_resolution",
                trigger_threshold=0.0,
                trigger_direction="rebirth",
                years_sustained=0,
                tick_applied=state.tick,
                target_variable="corruption",
                delta=-5.0,
                description="The refounded kingdom had nothing left to steal.",
                era_tag="REBIRTH_NASCENT",
            ),
        ]
        state.baseline_shifts.extend(rebirth_baselines)

        # ── Scar: the collapse itself ──────────────────────────
        rebirth_scar = InstitutionalScar(
            scar_id=f"scar_rebirth_{state.tick}",
            source_event_id=f"terminal_REBIRTH_NASCENT_{state.tick}",
            source_event_kind="TERMINAL_REBIRTH_NASCENT",
            source_event_description="Survivors founded a new order from the ashes.",
            tick_formed=state.tick,
            variable="infrastructure",
            delta=-5.0,
            description="The old kingdom died.  Its ruins are a permanent reminder.",
        )
        state.institutional_scars.append(rebirth_scar)

        record.description = (
            f"After {record.collapse_duration_ticks} ticks of collapse and "
            f"depopulation, the survivors founded a new order from the ashes.  "
            f"The scars remain, but hope is real."
        )
        record.new_era = "REFORMATION"
        record.layer_resets = resets

    # ── Helpers ─────────────────────────────────────────────────

    @classmethod
    def _snapshot_conditions(cls, state: "KingdomState") -> Dict[str, float]:
        """Capture key variables at terminal resolution."""
        return {
            "health_composite": state.health.composite,
            "food_stores": state.physical.food_stores,
            "labor_pool": state.physical.labor_pool,
            "resource_pressure": state.physical.resource_pressure,
            "infrastructure": state.physical.infrastructure,
            "trade_volume": state.physical.trade_volume,
            "treasury": state.physical.treasury,
            "cohesion": state.social.cohesion,
            "hope_level": state.social.hope_level,
            "class_tension": state.social.class_tension,
            "fear_level": state.social.fear_level,
            "cultural_confidence": state.social.cultural_confidence,
            "legitimacy": state.political.legitimacy,
            "enforcement_capacity": state.political.enforcement_capacity,
            "institutional_strength": state.political.institutional_strength,
            "external_threat": state.political.external_threat,
            "corruption": state.political.corruption,
            "public_faith": state.belief.public_faith,
            "collapse_duration": state.collapse_duration,
        }


# ============================================================
# SECTION 8: ORACLE SPEECH SYSTEM
# ============================================================
#
# Spec §31-36: Structured options, no free-form input.

class SpeechMode(Enum):
    DECREE = auto()    # broadcast — wide variable shift
    AUDIENCE = auto()  # personal — relationship edge shift


class Tone(Enum):
    GENTLE = auto()
    SEVERE = auto()
    MYSTICAL = auto()
    PRACTICAL = auto()
    DEFLECTIVE = auto()


@dataclass
class SpeechOption:
    """
    One selectable Oracle utterance.

    The player sees only `text` and `tone`.
    Beneath the surface: `policy_vector` and `propagation_magnitude`.
    """
    option_id: str = ""
    text: str = ""
    tone: Tone = Tone.PRACTICAL
    mode: SpeechMode = SpeechMode.DECREE

    # ---- hidden mechanics (spec §34: outcome opacity) ----
    policy_vector: Dict[str, float] = field(default_factory=dict)
    propagation_magnitude: float = 1.0
    target_character_id: Optional[str] = None  # only for AUDIENCE mode

    def to_dict(self) -> dict:
        return {
            "option_id": self.option_id,
            "text": self.text,
            "tone": self.tone.name,
            "mode": self.mode.name,
            "policy_vector": dict(self.policy_vector),
            "propagation_magnitude": self.propagation_magnitude,
            "target_character_id": self.target_character_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SpeechOption":
        return cls(
            option_id=d.get("option_id", ""),
            text=d.get("text", ""),
            tone=Tone[d.get("tone", "PRACTICAL")],
            mode=SpeechMode[d.get("mode", "DECREE")],
            policy_vector=d.get("policy_vector", {}),
            propagation_magnitude=d.get("propagation_magnitude", 1.0),
            target_character_id=d.get("target_character_id"),
        )


@dataclass
class DecreeRecord:
    """
    Cold Layer entry for a player (or AI Oracle) speech act.

    Spec §13: Myth memory — recency weight, amplification over time.
    """
    decree_id: str = ""
    tick: int = 0
    text: str = ""
    tone: str = ""
    mode: str = ""
    policy_vector: Dict[str, float] = field(default_factory=dict)
    myth_weight: float = 1.0       # grows over time if uncontradicted
    recency_weight: float = 1.0    # decays over time

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "DecreeRecord":
        obj = cls()
        for k, v in d.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj


# ============================================================
# SECTION 9: KINGDOM HEALTH INDEX
# ============================================================
#
# Spec §23: Composite, multi-dimensional, smoothed.

@dataclass
class KingdomHealthIndex:
    """
    Not a single HP bar.  A composite derived from all layers.
    Exposes trend direction (rising / declining).
    """
    resource_stability: float = 50.0
    social_cohesion: float = 50.0
    political_legitimacy: float = 50.0
    cultural_confidence: float = 50.0
    institutional_strength: float = 50.0
    external_threat_pressure: float = 10.0

    # Smoothed composite
    _history: List[float] = field(default_factory=list)

    @property
    def composite(self) -> float:
        """Weighted average of all sub-indices."""
        raw = (
            self.resource_stability * 0.20
            + self.social_cohesion * 0.20
            + self.political_legitimacy * 0.20
            + self.cultural_confidence * 0.15
            + self.institutional_strength * 0.15
            + (100.0 - self.external_threat_pressure) * 0.10
        )
        return max(0.0, min(100.0, raw))

    @property
    def trend(self) -> str:
        """Rising, stable, or declining over recent history."""
        if len(self._history) < 3:
            return "stable"
        recent = self._history[-5:]
        delta = recent[-1] - recent[0]
        if delta > 2.0:
            return "rising"
        elif delta < -2.0:
            return "declining"
        return "stable"

    def snapshot(self):
        """Record current composite for trend tracking."""
        self._history.append(self.composite)
        # Keep last 100 snapshots
        if len(self._history) > 100:
            self._history = self._history[-100:]

    def to_dict(self) -> dict:
        return {
            "resource_stability": self.resource_stability,
            "social_cohesion": self.social_cohesion,
            "political_legitimacy": self.political_legitimacy,
            "cultural_confidence": self.cultural_confidence,
            "institutional_strength": self.institutional_strength,
            "external_threat_pressure": self.external_threat_pressure,
            "_history": list(self._history[-100:]),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KingdomHealthIndex":
        obj = cls()
        for k, v in d.items():
            if k == "_history":
                obj._history = list(v)
            elif hasattr(obj, k):
                setattr(obj, k, v)
        return obj


# ============================================================
# SECTION 10: KINGDOM STATE CONTAINER
# ============================================================
#
# Top-level state object for a single kingdom.  Each neighbouring
# realm also has one of these (lazily instantiated from seed).

@dataclass
class KingdomState:
    """
    Complete state of one kingdom at a point in time.

    For the player's kingdom this is always materialised.
    For neighbour kingdoms it is lazily computed from seed + checkpoints.
    """
    kingdom_id: str = ""
    name: str = ""
    seed: int = 0
    is_player: bool = False

    # ---- core layers ----
    physical: PhysicalLayer = field(default_factory=PhysicalLayer)
    social: SocialLayer = field(default_factory=SocialLayer)
    political: PoliticalLayer = field(default_factory=PoliticalLayer)
    belief: BeliefLayer = field(default_factory=BeliefLayer)

    # ---- Oracle ----
    oracle: OracleBuild = field(default_factory=OracleBuild)

    # ---- ensemble cast ----
    characters: Dict[str, Character] = field(default_factory=dict)  # character_id → Character
    relationships: RelationshipGraph = field(default_factory=RelationshipGraph)

    # ---- factions ----
    factions: Dict[str, Faction] = field(default_factory=dict)  # faction_id → Faction

    # ---- time ----
    tick: int = 0
    world_day: int = 1
    world_year: int = 1

    # ---- event ledger ----
    active_events: EventQueue = field(default_factory=EventQueue)
    decree_history: List[DecreeRecord] = field(default_factory=list)

    # ---- health index ----
    health: KingdomHealthIndex = field(default_factory=KingdomHealthIndex)

    # ---- ripple field (Phase 2: active ripples propagating through the system) ----
    ripples: List["Ripple"] = field(default_factory=list)

    # ---- full event history (Cold Layer — causal ledger) ----
    event_history: List[SimEvent] = field(default_factory=list)

    # ---- causal edge graph (Closure System 1) ----
    causal_ledger: CausalLedger = field(default_factory=CausalLedger)

    # ---- neighbour influence vectors (Closure System 2) ----
    neighbour_influence: Dict[str, float] = field(default_factory=dict)
    neighbour_vectors: List[InterKingdomVector] = field(default_factory=list)

    # ---- Phase 5: Structural Memory ----
    baseline_shifts: List[BaselineShift] = field(default_factory=list)
    baseline_sustained_tracker: Dict[str, int] = field(default_factory=dict)
    institutional_scars: List[InstitutionalScar] = field(default_factory=list)
    current_era: EraIdentity = EraIdentity.STABLE
    era_history: List[EraRecord] = field(default_factory=list)

    # ---- Phase 8: Equilibrium Baselines ----
    # Each variable has a resting equilibrium that it's pulled toward.
    # Baseline shifts modify THIS dict, not the current value directly.
    # Tick dynamics: value += (baseline - value) * PULL_RATE + shocks
    # Initial baselines mirror starting layer values.
    equilibrium_baselines: Dict[str, float] = field(default_factory=lambda: {
        # Baselines tuned so an oracle-less kingdom converges to
        # health ≈ 50 ("knife-edge").  The Oracle's speech acts are
        # the lever that tips the kingdom toward prosperity or ruin.
        "food_production": 50.0,
        "food_stores": 60.0,
        "infrastructure": 50.0,
        "trade_volume": 40.0,
        "labor_pool": 50.0,
        "resource_pressure": 0.0,
        "cohesion": 45.0,             # was 60 — social layer too optimistic
        "class_tension": 30.0,        # was 20 — structural tension exists
        "cultural_confidence": 45.0,  # was 50 — uncertainty without oracle
        "hope_level": 50.0,
        "fear_level": 15.0,           # was 10 — background anxiety
        "literacy": 30.0,
        "legitimacy": 47.0,           # was 65 — authority unproven
        "enforcement_capacity": 50.0,
        "corruption": 27.0,           # was 15 — human nature baseline
        "institutional_strength": 50.0,
        "law_rigidity": 40.0,
        "external_threat": 15.0,      # was 10 — world is mildly hostile
        "public_faith": 55.0,         # was 65 — faith earned, not given
        "interpretation_divergence": 10.0,  # was 5 — natural disagreement
        "rumor_distortion": 10.0,     # was 5 — rumor is default
        "cultural_memory_strength": 50.0,
    })

    # ---- Phase 7: Terminal Resolution ----
    collapse_duration: int = 0     # ticks of continuous health < threshold
    terminal_resolutions: List[TerminalResolutionRecord] = field(default_factory=list)
    terminal_grace_until: int = 0  # tick until which post-transformation grace period applies

    # ---- Phase 8: Scar Gating State ----
    scar_cooldowns: Dict[str, int] = field(default_factory=dict)  # "(kind):(variable)" → tick of last scar
    scar_counters: Dict[str, int] = field(default_factory=lambda: {
        "applied": 0,
        "adaptive_applied": 0,
        "blocked_severity": 0,
        "blocked_rate": 0,
        "blocked_cap": 0,
        "blocked_cooldown": 0,
        "blocked_probability": 0,
    })

    def to_dict(self) -> dict:
        return {
            "kingdom_id": self.kingdom_id,
            "name": self.name,
            "seed": self.seed,
            "is_player": self.is_player,
            "physical": self.physical.to_dict(),
            "social": self.social.to_dict(),
            "political": self.political.to_dict(),
            "belief": self.belief.to_dict(),
            "oracle": self.oracle.to_dict(),
            "characters": {k: v.to_dict() for k, v in self.characters.items()},
            "relationships": self.relationships.to_list(),
            "factions": {k: v.to_dict() for k, v in self.factions.items()},
            "tick": self.tick,
            "world_day": self.world_day,
            "world_year": self.world_year,
            "decree_history": [d.to_dict() for d in self.decree_history],
            "ripples": [r.to_dict() for r in self.ripples],
            "event_history": [e.to_dict() for e in self.event_history[-500:]],
            "health": self.health.to_dict(),
            "causal_ledger": self.causal_ledger.to_list(),
            "neighbour_influence": dict(self.neighbour_influence),
            "neighbour_vectors": [v.to_dict() for v in self.neighbour_vectors],
            "baseline_shifts": [s.to_dict() for s in self.baseline_shifts],
            "baseline_sustained_tracker": dict(self.baseline_sustained_tracker),
            "institutional_scars": [s.to_dict() for s in self.institutional_scars],
            "equilibrium_baselines": dict(self.equilibrium_baselines),
            "current_era": self.current_era.name,
            "era_history": [e.to_dict() for e in self.era_history],
            "collapse_duration": self.collapse_duration,
            "terminal_resolutions": [r.to_dict() for r in self.terminal_resolutions],
            "terminal_grace_until": self.terminal_grace_until,
            "scar_cooldowns": dict(self.scar_cooldowns),
            "scar_counters": dict(self.scar_counters),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KingdomState":
        ks = cls()
        ks.kingdom_id = d.get("kingdom_id", "")
        ks.name = d.get("name", "")
        ks.seed = d.get("seed", 0)
        ks.is_player = d.get("is_player", False)
        ks.physical = PhysicalLayer.from_dict(d.get("physical", {}))
        ks.social = SocialLayer.from_dict(d.get("social", {}))
        ks.political = PoliticalLayer.from_dict(d.get("political", {}))
        ks.belief = BeliefLayer.from_dict(d.get("belief", {}))
        ks.oracle = OracleBuild.from_dict(d.get("oracle", {}))
        ks.characters = {
            k: Character.from_dict(v) for k, v in d.get("characters", {}).items()
        }
        ks.relationships = RelationshipGraph.from_list(d.get("relationships", []))
        ks.factions = {
            k: Faction.from_dict(v) for k, v in d.get("factions", {}).items()
        }
        ks.tick = d.get("tick", 0)
        ks.world_day = d.get("world_day", 1)
        ks.world_year = d.get("world_year", 1)
        ks.decree_history = [DecreeRecord.from_dict(x) for x in d.get("decree_history", [])]
        ks.ripples = [Ripple.from_dict(r) for r in d.get("ripples", [])]
        ks.event_history = [SimEvent.from_dict(e) for e in d.get("event_history", [])]
        ks.health = KingdomHealthIndex.from_dict(d.get("health", {}))
        ks.causal_ledger = CausalLedger.from_list(d.get("causal_ledger", []))
        ks.neighbour_influence = d.get("neighbour_influence", {})
        ks.neighbour_vectors = [InterKingdomVector.from_dict(v) for v in d.get("neighbour_vectors", [])]
        ks.baseline_shifts = [BaselineShift.from_dict(s) for s in d.get("baseline_shifts", [])]
        ks.baseline_sustained_tracker = d.get("baseline_sustained_tracker", {})
        ks.institutional_scars = [InstitutionalScar.from_dict(s) for s in d.get("institutional_scars", [])]
        if "equilibrium_baselines" in d:
            ks.equilibrium_baselines.update(d["equilibrium_baselines"])
        era_name = d.get("current_era", "STABLE")
        ks.current_era = EraIdentity[era_name] if era_name in EraIdentity.__members__ else EraIdentity.STABLE
        ks.era_history = [EraRecord.from_dict(e) for e in d.get("era_history", [])]
        ks.collapse_duration = d.get("collapse_duration", 0)
        ks.terminal_resolutions = [
            TerminalResolutionRecord.from_dict(r)
            for r in d.get("terminal_resolutions", [])
        ]
        ks.terminal_grace_until = d.get("terminal_grace_until", 0)
        ks.scar_cooldowns = d.get("scar_cooldowns", {})
        saved_counters = d.get("scar_counters", {})
        for k in ks.scar_counters:
            if k in saved_counters:
                ks.scar_counters[k] = saved_counters[k]
        return ks


# ============================================================
# SECTION 11: WORLD STATE (Multi-Kingdom Container)
# ============================================================

@dataclass
class WorldState:
    """
    Top-level save container.

    The player's kingdom is always materialised.
    Neighbour kingdoms store only their seed + last checkpoint
    and are lazily reconstructed when inspected.
    """
    game_id: str = ""
    master_seed: int = 0
    time_config: TimeConfig = field(default_factory=TimeConfig)

    # The player's fully-materialised kingdom
    player_kingdom: KingdomState = field(default_factory=KingdomState)

    # Neighbour kingdoms — only seeds + minimal checkpoint data
    # Full KingdomState is computed on demand via WorldBuilder.
    neighbour_seeds: Dict[str, int] = field(default_factory=dict)  # kingdom_id → seed
    neighbour_checkpoints: Dict[str, dict] = field(default_factory=dict)  # kingdom_id → last serialised snapshot

    # ---- long-term power gradient (Phase 5) ----
    neighbour_power_ranks: Dict[str, NeighbourPowerRank] = field(default_factory=dict)

    # ---- real-time tracking ----
    last_session_ts: float = 0.0   # unix timestamp of last player interaction
    created_ts: float = 0.0

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "master_seed": self.master_seed,
            "time_config": self.time_config.to_dict(),
            "player_kingdom": self.player_kingdom.to_dict(),
            "neighbour_seeds": dict(self.neighbour_seeds),
            "neighbour_checkpoints": dict(self.neighbour_checkpoints),
            "neighbour_power_ranks": {k: v.to_dict() for k, v in self.neighbour_power_ranks.items()},
            "last_session_ts": self.last_session_ts,
            "created_ts": self.created_ts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WorldState":
        ws = cls()
        ws.game_id = d.get("game_id", "")
        ws.master_seed = d.get("master_seed", 0)
        ws.time_config = TimeConfig.from_dict(d.get("time_config", {}))
        ws.player_kingdom = KingdomState.from_dict(d.get("player_kingdom", {}))
        ws.neighbour_seeds = d.get("neighbour_seeds", {})
        ws.neighbour_checkpoints = d.get("neighbour_checkpoints", {})
        ws.neighbour_power_ranks = {
            k: NeighbourPowerRank.from_dict(v)
            for k, v in d.get("neighbour_power_ranks", {}).items()
        }
        ws.last_session_ts = d.get("last_session_ts", 0.0)
        ws.created_ts = d.get("created_ts", 0.0)
        return ws


# ============================================================
# SECTION 12: WORLD BUILDER (Deterministic Generation)
# ============================================================

class WorldBuilder:
    """
    Deterministic procedural generation of kingdoms, factions,
    ensemble cast, relationships, and initial layer values.

    All generation is seed-driven.  The same seed always produces
    the same world.
    """

    # Name pools (placeholder — will be expanded or use ftb_names patterns)
    KINGDOM_NAME_PARTS_A = [
        "Iron", "Golden", "Silver", "Crimson", "Jade", "Obsidian", "Azure",
        "Amber", "Ivory", "Shadow", "Dawn", "Dusk", "Storm", "Frost",
        "Ember", "Coral", "Onyx", "Marble", "Cedar", "Silk",
    ]
    KINGDOM_NAME_PARTS_B = [
        "Haven", "Reach", "Vale", "Spire", "Hold", "March", "Crest",
        "Gate", "Hollow", "Watch", "Keep", "Throne", "Crown", "Peak",
        "Shore", "Dell", "Mire", "Bridge", "Glade", "Citadel",
    ]

    CHARACTER_FIRST_NAMES = [
        "Aldric", "Belen", "Caius", "Dara", "Edrin", "Farah", "Goran",
        "Hessa", "Ilya", "Jorin", "Kael", "Liora", "Maren", "Navid",
        "Orin", "Petra", "Quill", "Renna", "Soren", "Thea",
        "Ulric", "Vanya", "Wynn", "Xara", "Yael", "Zara",
    ]
    CHARACTER_SURNAMES = [
        "Ashworth", "Blackthorn", "Carvell", "Dunmere", "Elderwood",
        "Fairchild", "Greystone", "Halloway", "Ironside", "Jasper",
        "Kingsley", "Lark", "Montrose", "Northwind", "Oakhart",
        "Pennworth", "Ravenscraft", "Stonewall", "Thistledown", "Voss",
        "Whitmore", "Yarrow", "Caskwell", "Dorne", "Elmswood",
    ]

    FACTION_NAME_TEMPLATES = {
        FactionArchetype.RELIGIOUS: ["Temple of the {adj} {noun}", "Order of {noun}", "The {adj} Covenant"],
        FactionArchetype.MERCHANT:  ["Guild of {noun}", "The {adj} Exchange", "{noun} Trading Company"],
        FactionArchetype.MILITARY:  ["{adj} Guard", "The {noun} Legion", "Knights of the {adj} {noun}"],
        FactionArchetype.SCHOLARLY: ["Academy of {noun}", "The {adj} Archive", "College of {adj} {noun}"],
        FactionArchetype.POPULIST:  ["The {adj} Commons", "People's {noun}", "Assembly of {noun}"],
    }

    FACTION_ADJ = [
        "Sacred", "High", "True", "Eternal", "Ancient", "Grand",
        "First", "Steadfast", "Radiant", "Humble", "Noble", "Free",
    ]
    FACTION_NOUN = [
        "Light", "Flame", "Stone", "Wind", "Truth", "Dawn",
        "Justice", "Wisdom", "Coin", "Iron", "Harvest", "Stars",
    ]

    @classmethod
    def generate_kingdom_name(cls, rng: SeededRNG) -> str:
        a = rng.choice(cls.KINGDOM_NAME_PARTS_A)
        b = rng.choice(cls.KINGDOM_NAME_PARTS_B)
        return f"{a}{b}"

    @classmethod
    def generate_character_name(cls, rng: SeededRNG) -> str:
        first = rng.choice(cls.CHARACTER_FIRST_NAMES)
        last = rng.choice(cls.CHARACTER_SURNAMES)
        return f"{first} {last}"

    @classmethod
    def generate_faction_name(cls, archetype: FactionArchetype, rng: SeededRNG) -> str:
        templates = cls.FACTION_NAME_TEMPLATES[archetype]
        template = rng.choice(templates)
        adj = rng.choice(cls.FACTION_ADJ)
        noun = rng.choice(cls.FACTION_NOUN)
        return template.format(adj=adj, noun=noun)

    @classmethod
    def build_factions(cls, kingdom_id: str, rng: SeededRNG) -> Dict[str, Faction]:
        """Generate one faction per archetype."""
        factions: Dict[str, Faction] = {}
        faction_rng = rng.fork("factions")
        for archetype in FactionArchetype:
            fid = f"{kingdom_id}_faction_{archetype.name.lower()}"
            f = Faction(
                faction_id=fid,
                name=cls.generate_faction_name(archetype, faction_rng),
                archetype=archetype,
                influence=faction_rng.uniform(10, 30),
                internal_unity=faction_rng.uniform(40, 90),
                resources=faction_rng.uniform(30, 70),
                oracle_loyalty=faction_rng.uniform(30, 80),
                interpretation_bias=faction_rng.uniform(-20, 20),
            )
            # Randomise policy axes
            for axis in f.policy_axes:
                f.policy_axes[axis] = faction_rng.uniform(-30, 30)
            factions[fid] = f

        # Normalise influence shares to sum to 100
        total_influence = sum(f.influence for f in factions.values())
        if total_influence > 0:
            for f in factions.values():
                f.influence = (f.influence / total_influence) * 100.0

        return factions

    @classmethod
    def build_ensemble_cast(
        cls, kingdom_id: str, factions: Dict[str, Faction], rng: SeededRNG
    ) -> Tuple[Dict[str, Character], RelationshipGraph]:
        """Generate key characters and their relationship graph."""
        chars: Dict[str, Character] = {}
        char_rng = rng.fork("characters")

        for role in CharacterRole:
            cid = f"{kingdom_id}_char_{role.name.lower()}"
            affinity_archetype = ROLE_FACTION_AFFINITY[role]
            faction_id = ""
            for fid, f in factions.items():
                if f.archetype == affinity_archetype:
                    faction_id = fid
                    break

            c = Character(
                character_id=cid,
                name=cls.generate_character_name(char_rng),
                role=role,
                faction_id=faction_id,
                age=char_rng.randint(28, 58),
                ambition=char_rng.uniform(15, 85),
                risk_tolerance=char_rng.uniform(15, 85),
                piety=char_rng.uniform(15, 85),
                pragmatism=char_rng.uniform(15, 85),
                cruelty=char_rng.uniform(5, 50),
                charisma=char_rng.uniform(20, 80),
                oracle_loyalty=char_rng.uniform(30, 80),
                public_popularity=char_rng.uniform(20, 70),
            )
            chars[cid] = c

        # Build relationship graph
        graph = RelationshipGraph()
        rel_rng = rng.fork("relationships")
        char_ids = list(chars.keys())
        for i, a_id in enumerate(char_ids):
            for b_id in char_ids[i + 1:]:
                # trust edge (bidirectional)
                trust_ab = rel_rng.uniform(-30, 60)
                graph.set_weight(a_id, b_id, RelationshipType.TRUST, trust_ab)
                graph.set_weight(b_id, a_id, RelationshipType.TRUST, trust_ab + rel_rng.uniform(-15, 15))

                # ideological alignment (based on faction proximity)
                a_faction = chars[a_id].faction_id
                b_faction = chars[b_id].faction_id
                if a_faction and b_faction and a_faction == b_faction:
                    alignment = rel_rng.uniform(20, 60)
                else:
                    alignment = rel_rng.uniform(-40, 40)
                graph.set_weight(a_id, b_id, RelationshipType.IDEOLOGICAL_ALIGNMENT, alignment)
                graph.set_weight(b_id, a_id, RelationshipType.IDEOLOGICAL_ALIGNMENT, alignment)

                # rivalry (sparse — only ~30% of pairs)
                if rel_rng.random() < 0.30:
                    rivalry = rel_rng.uniform(10, 60)
                    graph.set_weight(a_id, b_id, RelationshipType.RIVALRY, rivalry)
                    graph.set_weight(b_id, a_id, RelationshipType.RIVALRY, rivalry * rel_rng.uniform(0.5, 1.5))

        return chars, graph

    @classmethod
    def build_kingdom(cls, kingdom_id: str, seed: int, is_player: bool = False,
                      oracle: Optional[OracleBuild] = None) -> KingdomState:
        """
        Fully deterministic kingdom generation from seed.

        For the player kingdom, `oracle` is supplied from character creation.
        For AI kingdoms, oracle is procedurally generated.
        """
        rng = SeededRNG(seed)
        layer_rng = rng.fork("layers")

        ks = KingdomState(
            kingdom_id=kingdom_id,
            name=cls.generate_kingdom_name(rng.fork("name")),
            seed=seed,
            is_player=is_player,
        )

        # ---- Oracle ----
        if oracle:
            ks.oracle = oracle
        else:
            ks.oracle = OracleBuild.random_build(rng)

        # ---- Physical layer (vary starting conditions) ----
        ks.physical.food_production = layer_rng.uniform(35, 65)
        ks.physical.food_stores = layer_rng.uniform(40, 80)
        ks.physical.infrastructure = layer_rng.uniform(30, 60)
        ks.physical.trade_volume = layer_rng.uniform(20, 60)
        ks.physical.labor_pool = layer_rng.uniform(35, 65)
        ks.physical.treasury = layer_rng.uniform(500, 2000)

        # ---- Social layer ----
        ks.social.cohesion = layer_rng.uniform(40, 75)
        ks.social.class_tension = layer_rng.uniform(10, 40)
        ks.social.cultural_confidence = layer_rng.uniform(35, 65)
        ks.social.literacy = layer_rng.uniform(15, 50)
        ks.social.fear_level = layer_rng.uniform(5, 25)
        ks.social.hope_level = layer_rng.uniform(35, 65)

        # ---- Political layer ----
        ks.political.power_concentration = layer_rng.uniform(30, 70)
        ks.political.legitimacy = layer_rng.uniform(45, 80)
        ks.political.enforcement_capacity = layer_rng.uniform(30, 65)
        ks.political.law_rigidity = layer_rng.uniform(20, 60)
        ks.political.corruption = layer_rng.uniform(5, 35)
        ks.political.institutional_strength = layer_rng.uniform(35, 65)

        # ---- Belief layer ----
        ks.belief.public_faith = layer_rng.uniform(50, 80)
        ks.belief.myth_accumulation = 0.0
        ks.belief.interpretation_divergence = layer_rng.uniform(2, 15)
        ks.belief.cultural_memory_strength = layer_rng.uniform(30, 60)

        # ---- Factions ----
        ks.factions = cls.build_factions(kingdom_id, rng)
        # Mirror faction influence into social layer
        ks.social.faction_influence = {
            fid: f.influence for fid, f in ks.factions.items()
        }

        # ---- Ensemble cast ----
        ks.characters, ks.relationships = cls.build_ensemble_cast(kingdom_id, ks.factions, rng)

        return ks

    @classmethod
    def build_world(cls, master_seed: int, oracle: OracleBuild,
                    time_config: TimeConfig, num_neighbours: int = 4) -> WorldState:
        """
        Generate a complete world: player kingdom + N neighbours.

        Neighbour kingdoms are seeded but NOT fully materialised here.
        They store only their seed.  Full state is lazily computed.
        """
        master_rng = SeededRNG(master_seed)

        ws = WorldState(
            game_id=str(uuid.uuid4())[:8],
            master_seed=master_seed,
            time_config=time_config,
            created_ts=time.time(),
            last_session_ts=time.time(),
        )

        # Player kingdom
        player_seed = master_rng.fork("player").seed
        ws.player_kingdom = cls.build_kingdom(
            kingdom_id="player",
            seed=player_seed,
            is_player=True,
            oracle=oracle,
        )

        # Neighbour seeds (lazy — NOT materialised)
        for i in range(num_neighbours):
            nid = f"neighbour_{i}"
            nseed = master_rng.fork(f"neighbour_{i}").seed
            ws.neighbour_seeds[nid] = nseed

        return ws

    @classmethod
    def materialise_neighbour(cls, kingdom_id: str, seed: int,
                              checkpoint: Optional[dict] = None) -> KingdomState:
        """
        Lazily materialise a neighbour kingdom.

        If a checkpoint exists, restore from it.
        Otherwise generate fresh from seed.
        """
        if checkpoint:
            return KingdomState.from_dict(checkpoint)
        return cls.build_kingdom(kingdom_id, seed, is_player=False)


# ============================================================
# SECTION 12.5: PHASE 2 — RIPPLE, PROPAGATION, SPEECH GEN,
#               INTERPRETATION, SUCCESSION, ORACLE PSYCHOLOGY
# ============================================================

# ---- Tone propagation modifiers (spec §33) ----
# Each tone modifies propagation magnitude and interpretation distortion.

TONE_MODIFIERS: Dict[str, Dict[str, float]] = {
    "GENTLE":     {"magnitude": 0.7,  "distortion": -0.1, "faith_shift": 0.02,  "fear_shift": -0.03},
    "SEVERE":     {"magnitude": 1.4,  "distortion": 0.05, "faith_shift": -0.01, "fear_shift": 0.05},
    "MYSTICAL":   {"magnitude": 1.1,  "distortion": 0.15, "faith_shift": 0.03,  "fear_shift": 0.01},
    "PRACTICAL":  {"magnitude": 0.9,  "distortion": -0.05,"faith_shift": 0.0,   "fear_shift": -0.01},
    "DEFLECTIVE": {"magnitude": 0.5,  "distortion": 0.10, "faith_shift": -0.02, "fear_shift": 0.0},
}


# ---- Ripple system (spec §48) ----

@dataclass
class Ripple:
    """
    A propagating wave of systemic change.

    Ripples start when the Oracle speaks or when events fire.
    Each tick they apply their policy_vector to kingdom variables,
    attenuated by resistance and amplified by belief.
    They dissipate over time or merge with other ripples.
    """
    ripple_id: str = ""
    origin_tick: int = 0
    source_decree_id: str = ""     # which decree spawned this (if any)
    source_event_id: str = ""      # which event spawned this (if any)

    # The directional push this ripple carries
    policy_vector: Dict[str, float] = field(default_factory=dict)

    # Dynamics
    magnitude: float = 1.0          # current strength (decays each tick)
    initial_magnitude: float = 1.0
    dissipation_rate: float = 0.05  # fraction lost per tick
    momentum: float = 1.0           # accumulated inertia (spec §14)

    # Which layers this ripple affects
    affected_layers: List[str] = field(default_factory=lambda: ["belief", "social", "political", "physical"])

    # Tracking
    ticks_alive: int = 0
    absorbed: bool = False          # merged into another ripple

    def tick_decay(self):
        """Apply per-tick dissipation."""
        self.ticks_alive += 1
        self.magnitude *= (1.0 - self.dissipation_rate)
        # Momentum decays slower
        self.momentum *= 0.98

    @property
    def is_spent(self) -> bool:
        return self.magnitude < 0.01 or self.absorbed

    def to_dict(self) -> dict:
        return {
            "ripple_id": self.ripple_id,
            "origin_tick": self.origin_tick,
            "source_decree_id": self.source_decree_id,
            "source_event_id": self.source_event_id,
            "policy_vector": dict(self.policy_vector),
            "magnitude": self.magnitude,
            "initial_magnitude": self.initial_magnitude,
            "dissipation_rate": self.dissipation_rate,
            "momentum": self.momentum,
            "affected_layers": list(self.affected_layers),
            "ticks_alive": self.ticks_alive,
            "absorbed": self.absorbed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Ripple":
        obj = cls()
        for k, v in d.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj


# ---- Policy vector keys ----
# These are the axes that speech/events push on.  Each maps to
# specific variable adjustments in the simulation layers.

POLICY_AXES = [
    "agriculture_focus",       # → food_production, labor reallocation
    "trade_focus",             # → trade_volume, treasury
    "military_focus",          # → enforcement_capacity, external_threat
    "faith_focus",             # → public_faith, myth_accumulation
    "reform_focus",            # → law_rigidity (decrease), institutional_strength
    "austerity_focus",         # → treasury (save), infrastructure (cut)
    "mercy_focus",             # → fear_level (decrease), cohesion (increase)
    "justice_focus",           # → enforcement (increase), fear (increase), corruption (decrease)
    "expansion_focus",         # → trade, external_threat
    "isolation_focus",         # → trade (decrease), cohesion (increase)
]


# ---- Faction Interpretation Engine (spec §4, §12) ----

class FactionInterpreter:
    """
    Each faction filters Oracle speech through its own bias.

    Spec §12: Between Oracle → Faction → Population, interpretation
    noise accumulates.  Distortion variables: faction agenda bias,
    cultural rigidity, literacy, fear level, competing rumor strength.
    """

    @classmethod
    def interpret(cls, faction: Faction, policy_vector: Dict[str, float],
                  tone_mods: Dict[str, float], state: KingdomState,
                  rng: SeededRNG) -> Dict[str, float]:
        """
        Produce a faction-specific interpretation of a policy vector.

        Returns a modified policy vector representing what this faction
        *does* with the Oracle's speech.
        """
        interpreted = {}

        # Oracle clarity reduces distortion
        clarity = state.oracle.effective("clarity") / 50.0  # 0-2 scale
        distortion_base = tone_mods.get("distortion", 0.0)

        # Faction-specific distortion factors
        literacy_factor = state.social.literacy / 100.0          # higher = less noise
        fear_factor = state.social.fear_level / 100.0            # higher = more noise
        rumor_factor = state.social.rumor_strength / 100.0       # higher = more noise
        rigidity = state.political.law_rigidity / 100.0          # higher = resist change

        total_distortion = (
            distortion_base
            + faction.interpretation_bias / 100.0
            - clarity * 0.3
            - literacy_factor * 0.2
            + fear_factor * 0.15
            + rumor_factor * 0.1
        )

        for axis, value in policy_vector.items():
            # Apply faction agenda bias
            agenda_boost = 0.0
            if axis == "faith_focus" and faction.archetype == FactionArchetype.RELIGIOUS:
                agenda_boost = 0.3
            elif axis == "trade_focus" and faction.archetype == FactionArchetype.MERCHANT:
                agenda_boost = 0.3
            elif axis == "military_focus" and faction.archetype == FactionArchetype.MILITARY:
                agenda_boost = 0.3
            elif axis == "reform_focus" and faction.archetype == FactionArchetype.SCHOLARLY:
                agenda_boost = 0.2
            elif axis == "agriculture_focus" and faction.archetype == FactionArchetype.POPULIST:
                agenda_boost = 0.3

            # Interpretation = original + bias + noise
            noise = rng.gauss(0, abs(total_distortion) * 0.3)
            interpreted[axis] = value * (1.0 + agenda_boost) + noise

            # Rigidity dampens reform
            if axis == "reform_focus":
                interpreted[axis] *= (1.0 - rigidity * 0.5)

        return interpreted

    @classmethod
    def compute_faction_response(cls, faction: Faction,
                                 interpreted_vector: Dict[str, float],
                                 state: KingdomState) -> Dict[str, float]:
        """
        Translate an interpreted policy vector into concrete variable deltas.

        This is where abstract policy direction becomes material change.
        The faction's resources and influence determine execution strength.

        Phase 9 — State-dependent execution:
        Each delta is now scaled by a context multiplier derived from
        the current kingdom state.  Agriculture decrees are more
        effective when infrastructure is good (roads → distribution).
        Military decrees cost more when the treasury is low.
        This means the SAME decree, issued at different moments in
        the kingdom's history, produces different material effects.
        Small timing differences from earlier perturbations thus
        compound through the execution pathway.
        """
        execution_strength = (faction.influence / 100.0) * (faction.internal_unity / 100.0)
        deltas: Dict[str, float] = {}

        # Phase 9: pre-compute context multipliers
        infra_mod = 0.7 + 0.6 * (state.physical.infrastructure / 100.0)  # 0.7→1.3
        treasury_mod = 0.6 + 0.8 * min(1.0, state.physical.treasury / 500.0)  # 0.6→1.4
        cohesion_mod = 0.8 + 0.4 * (state.social.cohesion / 100.0)  # 0.8→1.2
        fear_mod = 1.0 + 0.3 * (state.social.fear_level / 100.0)  # 1.0→1.3 (fear amplifies enforcement)

        for axis, strength in interpreted_vector.items():
            # Phase 9: Increased from 0.1 to 0.4.
            # At 0.1 the per-decree delta was ~0.03 per faction,
            # completely dominated by mean reversion (0.09/tick × 15 ticks).
            # At 0.4 the decree → observable shift in ~1-2 units,
            # which compounds with equilibrium baseline shifting to
            # produce visible structural divergence over 100+ ticks.
            effect = strength * execution_strength * 0.4

            if axis == "agriculture_focus":
                deltas["food_production"] = deltas.get("food_production", 0) + effect * 2.0 * infra_mod
                deltas["trade_volume"] = deltas.get("trade_volume", 0) - effect * 0.3
            elif axis == "trade_focus":
                deltas["trade_volume"] = deltas.get("trade_volume", 0) + effect * 2.0 * infra_mod
                deltas["treasury"] = deltas.get("treasury", 0) + effect * 5.0
            elif axis == "military_focus":
                deltas["enforcement_capacity"] = deltas.get("enforcement_capacity", 0) + effect * 1.5 * fear_mod
                deltas["treasury"] = deltas.get("treasury", 0) - effect * 3.0 / max(0.5, treasury_mod)
            elif axis == "faith_focus":
                deltas["public_faith"] = deltas.get("public_faith", 0) + effect * 1.5 * cohesion_mod
                deltas["myth_accumulation"] = deltas.get("myth_accumulation", 0) + effect * 0.5
            elif axis == "reform_focus":
                deltas["law_rigidity"] = deltas.get("law_rigidity", 0) - effect * 1.0
                deltas["institutional_strength"] = deltas.get("institutional_strength", 0) + effect * 0.5 * cohesion_mod
                deltas["class_tension"] = deltas.get("class_tension", 0) + effect * 0.3
            elif axis == "austerity_focus":
                deltas["treasury"] = deltas.get("treasury", 0) + effect * 8.0
                deltas["infrastructure"] = deltas.get("infrastructure", 0) - effect * 0.5
                deltas["hope_level"] = deltas.get("hope_level", 0) - effect * 0.5
            elif axis == "mercy_focus":
                deltas["fear_level"] = deltas.get("fear_level", 0) - effect * 2.0
                deltas["cohesion"] = deltas.get("cohesion", 0) + effect * 1.0 * cohesion_mod
                deltas["corruption"] = deltas.get("corruption", 0) + effect * 0.3
            elif axis == "justice_focus":
                deltas["enforcement_capacity"] = deltas.get("enforcement_capacity", 0) + effect * 1.0 * fear_mod
                deltas["fear_level"] = deltas.get("fear_level", 0) + effect * 1.0
                deltas["corruption"] = deltas.get("corruption", 0) - effect * 1.5
            elif axis == "expansion_focus":
                deltas["trade_volume"] = deltas.get("trade_volume", 0) + effect * 1.0 * infra_mod
                deltas["external_threat"] = deltas.get("external_threat", 0) + effect * 0.5
            elif axis == "isolation_focus":
                deltas["trade_volume"] = deltas.get("trade_volume", 0) - effect * 1.5
                deltas["cohesion"] = deltas.get("cohesion", 0) + effect * 0.8 * cohesion_mod

        return deltas


# ---- Propagation Engine (spec §4, §24-25, §48) ----

class PropagationEngine:
    """
    When the Oracle speaks, consequences cascade through the system.

    Pipeline: Speech → Tone classification → Policy vectors →
    Faction interpretation → Variable deltas → Ripple creation →
    Character relationship effects → Oracle psychology update.
    """

    @classmethod
    def propagate_decree(cls, state: KingdomState, option: SpeechOption,
                         rng: SeededRNG) -> List[SimEvent]:
        """
        Process a Decree (broadcast) speech act.
        Returns any immediately-generated events.
        """
        events: List[SimEvent] = []
        tone_mods = TONE_MODIFIERS.get(option.tone.name, TONE_MODIFIERS["PRACTICAL"])

        # ---- Belief layer direct effects ----
        conviction = state.oracle.effective("conviction") / 50.0
        charisma = state.oracle.effective("charisma") / 50.0
        faith = state.belief.public_faith / 100.0

        # Magnitude = base × tone × conviction × charisma × faith (spec §17)
        effective_magnitude = (
            option.propagation_magnitude
            * tone_mods["magnitude"]
            * (0.5 + conviction * 0.5)
            * (0.5 + charisma * 0.5)
            * (0.5 + faith * 0.5)
        )

        # Faith shift from tone
        state.belief.public_faith += tone_mods["faith_shift"] * effective_magnitude * 10
        state.belief.public_faith = max(0, min(100, state.belief.public_faith))

        # Fear shift from tone
        state.social.fear_level += tone_mods["fear_shift"] * effective_magnitude * 10
        state.social.fear_level = max(0, min(100, state.social.fear_level))

        # Speaking reduces sacred silence
        state.belief.sacred_silence_weight = max(0, state.belief.sacred_silence_weight - 5.0)

        # ---- Faction interpretation ----
        aggregate_deltas: Dict[str, float] = {}
        prop_rng = rng.fork(f"prop_{state.tick}")

        for fid, faction in state.factions.items():
            interpreted = FactionInterpreter.interpret(
                faction, option.policy_vector, tone_mods, state, prop_rng
            )
            deltas = FactionInterpreter.compute_faction_response(
                faction, interpreted, state
            )
            for key, val in deltas.items():
                aggregate_deltas[key] = aggregate_deltas.get(key, 0) + val

        # ---- Apply aggregate deltas to state ----
        cls._apply_deltas(state, aggregate_deltas,
                          source_type="decree", source_id=option.option_id)

        # ---- Create ripple ----
        ripple = Ripple(
            ripple_id=f"ripple_{state.tick}_{option.option_id[:8]}",
            origin_tick=state.tick,
            source_decree_id=option.option_id,
            policy_vector=dict(option.policy_vector),
            magnitude=effective_magnitude,
            initial_magnitude=effective_magnitude,
            dissipation_rate=0.03 + (1.0 - faith) * 0.02,  # low faith = faster dissipation
        )
        state.ripples.append(ripple)

        # ---- Trajectory bias update (spec §43) ----
        tone_key = option.tone.name
        state.oracle.trajectory[tone_key] = state.oracle.trajectory.get(tone_key, 0.0) + 1.0

        # ---- Oracle psychology update ----
        OraclePsychology.update_after_speech(state, option, effective_magnitude)

        # ---- Check for unintended consequences (spec §25) ----
        if effective_magnitude > 2.0 and prop_rng.random() < 0.3:
            events.append(SimEvent(
                event_id=f"ev_{state.tick}_overreach",
                kind=EventKind.CULTURAL_SHIFT,
                domain=EventDomain.SOCIAL,
                tick=state.tick,
                severity=effective_magnitude * 15,
                urgency=30.0,
                description="The Oracle's words carry further than intended. Some interpret them too literally.",
                caused_by=option.option_id,
            ))

        return events

    @classmethod
    def propagate_audience(cls, state: KingdomState, option: SpeechOption,
                           rng: SeededRNG) -> List[SimEvent]:
        """
        Process an Audience (personal) speech act.
        Modifies relationship edges with the target character.
        """
        events: List[SimEvent] = []
        target_id = option.target_character_id
        if not target_id or target_id not in state.characters:
            return events

        char = state.characters[target_id]
        tone_mods = TONE_MODIFIERS.get(option.tone.name, TONE_MODIFIERS["PRACTICAL"])

        empathy = state.oracle.effective("empathy") / 50.0
        severity = state.oracle.effective("severity") / 50.0

        # Direct loyalty effect
        loyalty_shift = option.propagation_magnitude * 3.0
        if option.tone == Tone.GENTLE:
            loyalty_shift *= (0.5 + empathy * 0.5)
        elif option.tone == Tone.SEVERE:
            loyalty_shift *= -(0.5 + severity * 0.5)
            char.stress += 5.0
        elif option.tone == Tone.MYSTICAL:
            loyalty_shift *= (0.3 + char.piety / 100.0)
        elif option.tone == Tone.DEFLECTIVE:
            loyalty_shift *= -0.3
            char.private_grievances += 2.0

        char.oracle_loyalty = max(0, min(100, char.oracle_loyalty + loyalty_shift))

        # Grievance reduction if addressed
        if option.tone != Tone.DEFLECTIVE:
            char.private_grievances = max(0, char.private_grievances - 5.0)

        # Faction ripple from audience (smaller than decree)
        faction = state.factions.get(char.faction_id)
        if faction:
            faction.oracle_loyalty += loyalty_shift * 0.1
            faction.oracle_loyalty = max(0, min(100, faction.oracle_loyalty))

        # Small ripple
        ripple = Ripple(
            ripple_id=f"ripple_{state.tick}_aud_{target_id[:8]}",
            origin_tick=state.tick,
            source_decree_id=option.option_id,
            policy_vector=dict(option.policy_vector),
            magnitude=option.propagation_magnitude * 0.3,
            initial_magnitude=option.propagation_magnitude * 0.3,
            dissipation_rate=0.08,
            affected_layers=["social", "political"],
        )
        state.ripples.append(ripple)

        OraclePsychology.update_after_speech(state, option, option.propagation_magnitude * 0.3)

        return events

    @classmethod
    def propagate(cls, state: KingdomState, option: SpeechOption,
                  rng: SeededRNG) -> List[SimEvent]:
        """Route to decree or audience propagation."""
        if option.mode == SpeechMode.DECREE:
            return cls.propagate_decree(state, option, rng)
        else:
            return cls.propagate_audience(state, option, rng)

    # Phase 9: Fraction of decree-driven deltas that also shifts
    # the equilibrium baseline.  This is the core mechanism that
    # converts transient shocks into structural change.  Without
    # this, mean reversion erases all decree effects within ~50 ticks.
    # With it, each decree permanently nudges where the system
    # *wants* to rest — the pebble moves the whole pond.
    EQUILIBRIUM_SHIFT_FRACTION: float = 0.35

    @classmethod
    def _apply_deltas(cls, state: KingdomState, deltas: Dict[str, float],
                      source_type: str = "aggregate", source_id: str = "",
                      record_causal: bool = True):
        """Apply computed variable deltas to the appropriate layer.
        
        If record_causal is True, each delta is recorded in the
        kingdom's CausalLedger for deterministic accountability.

        Phase 9: decree-sourced deltas also shift equilibrium baselines
        by EQUILIBRIUM_SHIFT_FRACTION, so the system's resting point
        moves structurally with Oracle decisions.
        """
        _c = lambda v, lo=0.0, hi=100.0: max(lo, min(hi, v))
        p, s, pol, b = state.physical, state.social, state.political, state.belief
        ledger = state.causal_ledger if record_causal else None

        for key, delta in deltas.items():
            if abs(delta) < 1e-9:
                continue
            if key == "food_production":
                p.food_production = _c(p.food_production + delta)
            elif key == "trade_volume":
                p.trade_volume = _c(p.trade_volume + delta)
            elif key == "treasury":
                p.treasury = max(0, p.treasury + delta)
            elif key == "infrastructure":
                p.infrastructure = _c(p.infrastructure + delta)
            elif key == "enforcement_capacity":
                pol.enforcement_capacity = _c(pol.enforcement_capacity + delta)
            elif key == "public_faith":
                b.public_faith = _c(b.public_faith + delta)
            elif key == "myth_accumulation":
                b.myth_accumulation = max(0, b.myth_accumulation + delta)
            elif key == "law_rigidity":
                pol.law_rigidity = _c(pol.law_rigidity + delta)
            elif key == "institutional_strength":
                pol.institutional_strength = _c(pol.institutional_strength + delta)
            elif key == "class_tension":
                s.class_tension = _c(s.class_tension + delta)
            elif key == "hope_level":
                s.hope_level = _c(s.hope_level + delta)
            elif key == "fear_level":
                s.fear_level = _c(s.fear_level + delta)
            elif key == "cohesion":
                s.cohesion = _c(s.cohesion + delta)
            elif key == "corruption":
                pol.corruption = _c(pol.corruption + delta)
            elif key == "external_threat":
                pol.external_threat = _c(pol.external_threat + delta)
            else:
                continue

            # Record causal edge
            if ledger:
                ledger.record_delta(
                    source_type=source_type,
                    source_id=source_id,
                    target_type="layer",
                    target_id=state.kingdom_id,
                    variable=key,
                    delta=delta,
                    tick=state.tick,
                )

        # Phase 9: Shift equilibrium baselines for decree-sourced deltas.
        # This converts transient Oracle decisions into permanent structural
        # change — the mean reversion target itself drifts with governance.
        # Only applies to decree/aggregate sources (not organic recovery).
        if source_type in ("decree", "aggregate") and hasattr(state, "equilibrium_baselines"):
            # Variables that have equilibrium baselines and can be shifted
            SKIP_EQ = {"treasury", "food_stores", "resource_pressure", "myth_accumulation"}
            for key, delta in deltas.items():
                if key in SKIP_EQ or abs(delta) < 1e-9:
                    continue
                if key in state.equilibrium_baselines:
                    old_eq = state.equilibrium_baselines[key]
                    eq_shift = delta * cls.EQUILIBRIUM_SHIFT_FRACTION
                    state.equilibrium_baselines[key] = max(0.0, min(100.0, old_eq + eq_shift))

    @classmethod
    def tick_ripples(cls, state: KingdomState, rng: SeededRNG):
        """
        Advance all active ripples by one tick.

        Each ripple applies attenuated policy pressure to the kingdom.
        Spent ripples are removed.  Overlapping ripples may merge.
        """
        faith_amp = state.belief.public_faith / 50.0  # >1 = amplifies

        # Phase 5: Era modifiers for ripple propagation
        era_mods = EraClassifier.get_modifiers(state.current_era)
        reform_multiplier = era_mods.get("reform_ripple_multiplier", 1.0)

        for ripple in state.ripples:
            if ripple.is_spent:
                continue

            # Apply residual pressure
            for axis, strength in ripple.policy_vector.items():
                effect = strength * ripple.magnitude * ripple.momentum * 0.02 * faith_amp

                # Phase 5: Era-specific ripple scaling
                if axis == "reform_focus":
                    effect *= reform_multiplier

                # Map policy axes to small variable deltas
                deltas = {}
                if axis == "agriculture_focus":
                    deltas["food_production"] = effect * 0.5
                elif axis == "trade_focus":
                    deltas["trade_volume"] = effect * 0.5
                elif axis == "military_focus":
                    deltas["enforcement_capacity"] = effect * 0.3
                elif axis == "faith_focus":
                    deltas["public_faith"] = effect * 0.3
                elif axis == "reform_focus":
                    deltas["law_rigidity"] = -effect * 0.2
                elif axis == "mercy_focus":
                    deltas["fear_level"] = -effect * 0.3
                elif axis == "justice_focus":
                    deltas["corruption"] = -effect * 0.3
                cls._apply_deltas(state, deltas,
                                  source_type="ripple", source_id=ripple.ripple_id)

            ripple.tick_decay()

        # Merge overlapping ripples (spec §48: ripples can merge)
        cls._merge_ripples(state)

        # Prune spent ripples
        state.ripples = [r for r in state.ripples if not r.is_spent]

    @classmethod
    def _merge_ripples(cls, state: KingdomState):
        """
        If two ripples share similar policy vectors and are both strong,
        merge them into one with combined magnitude.
        """
        active = [r for r in state.ripples if not r.is_spent]
        if len(active) < 2:
            return

        merged_ids: Set[str] = set()
        for i, a in enumerate(active):
            if a.ripple_id in merged_ids:
                continue
            for b in active[i + 1:]:
                if b.ripple_id in merged_ids:
                    continue
                # Check policy vector similarity
                shared_axes = set(a.policy_vector.keys()) & set(b.policy_vector.keys())
                if len(shared_axes) < 2:
                    continue
                # Check sign agreement
                agreements = sum(
                    1 for ax in shared_axes
                    if a.policy_vector[ax] * b.policy_vector[ax] > 0
                )
                if agreements >= len(shared_axes) * 0.7:
                    # Merge b into a
                    a.magnitude += b.magnitude * 0.5
                    a.momentum = max(a.momentum, b.momentum)
                    for ax in b.policy_vector:
                        a.policy_vector[ax] = a.policy_vector.get(ax, 0) + b.policy_vector[ax] * 0.5
                    b.absorbed = True
                    merged_ids.add(b.ripple_id)


# ---- Speech Option Generator (spec §31-36, §42) ----

# Template bank for procedural speech generation.
# Each template has: text pattern, tone, policy vector, and trait affinity
# (how well it matches an Oracle build — higher affinity = more likely to appear).

_DECREE_TEMPLATES = [
    # Agriculture / populist
    {"text": "Honor the farmers above all else.", "tone": "PRACTICAL", "vector": {"agriculture_focus": 3.0, "trade_focus": -0.5}, "affinity": {"empathy": 1.0, "humility": 0.5}},
    {"text": "The land will provide — remain faithful.", "tone": "MYSTICAL", "vector": {"agriculture_focus": 1.5, "faith_focus": 2.0}, "affinity": {"self_belief": 1.0, "clarity": -0.5}},
    {"text": "Ration and preserve stability.", "tone": "PRACTICAL", "vector": {"austerity_focus": 2.0, "agriculture_focus": 1.0}, "affinity": {"pragmatism": 1.0}},
    {"text": "Sacrifice today for future abundance.", "tone": "SEVERE", "vector": {"austerity_focus": 3.0, "agriculture_focus": 1.5}, "affinity": {"conviction": 1.0, "severity": 0.5}},
    # Trade / economy
    {"text": "Open the roads. Let commerce flow.", "tone": "PRACTICAL", "vector": {"trade_focus": 3.0, "expansion_focus": 1.0}, "affinity": {"ambition": 0.8}},
    {"text": "Our wealth lies in what we share with neighbors.", "tone": "GENTLE", "vector": {"trade_focus": 2.0, "expansion_focus": 1.5}, "affinity": {"empathy": 0.5, "charisma": 0.5}},
    {"text": "Guard our markets from foreign influence.", "tone": "SEVERE", "vector": {"isolation_focus": 2.5, "trade_focus": -1.0}, "affinity": {"paranoia": 0.8, "severity": 0.5}},
    # Military / enforcement
    {"text": "Strengthen the walls. Discipline the watch.", "tone": "SEVERE", "vector": {"military_focus": 3.0, "justice_focus": 1.0}, "affinity": {"severity": 1.0, "conviction": 0.5}},
    {"text": "Peace is kept by those who prepare for war.", "tone": "PRACTICAL", "vector": {"military_focus": 2.5, "austerity_focus": 0.5}, "affinity": {"pragmatism": 0.8}},
    {"text": "Our guards serve the people, not the throne.", "tone": "GENTLE", "vector": {"military_focus": 1.0, "mercy_focus": 2.0}, "affinity": {"empathy": 1.0, "humility": 0.8}},
    # Faith / belief
    {"text": "The signs are clear to those who listen.", "tone": "MYSTICAL", "vector": {"faith_focus": 3.0}, "affinity": {"self_belief": 1.0, "clarity": 0.5}},
    {"text": "Doubt is the enemy of progress.", "tone": "SEVERE", "vector": {"faith_focus": 2.5, "justice_focus": 1.0}, "affinity": {"conviction": 1.0, "doubt": -1.0}},
    {"text": "Even I must question what I see.", "tone": "GENTLE", "vector": {"faith_focus": -0.5, "reform_focus": 1.5}, "affinity": {"doubt": 1.0, "humility": 1.0}},
    {"text": "Let faith be a lantern, not a cage.", "tone": "MYSTICAL", "vector": {"faith_focus": 1.5, "reform_focus": 1.0}, "affinity": {"empathy": 0.8, "clarity": 0.5}},
    # Reform / scholarly
    {"text": "The old ways have served us. But the world changes.", "tone": "PRACTICAL", "vector": {"reform_focus": 2.5, "trade_focus": 1.0}, "affinity": {"ambition": 0.5, "pragmatism": 0.5}},
    {"text": "Tear down what is rotten. Build anew.", "tone": "SEVERE", "vector": {"reform_focus": 4.0, "justice_focus": 1.0}, "affinity": {"conviction": 1.0, "severity": 1.0}},
    {"text": "Learn from the scholars. Invest in knowledge.", "tone": "GENTLE", "vector": {"reform_focus": 1.5, "agriculture_focus": -0.5}, "affinity": {"humility": 0.5, "empathy": 0.5}},
    # Justice / mercy
    {"text": "No crime shall go unanswered.", "tone": "SEVERE", "vector": {"justice_focus": 3.5, "mercy_focus": -1.0}, "affinity": {"severity": 1.5, "conviction": 0.5}},
    {"text": "Mercy reveals our strength, not our weakness.", "tone": "GENTLE", "vector": {"mercy_focus": 3.0, "justice_focus": -0.5}, "affinity": {"empathy": 1.5, "humility": 0.5}},
    {"text": "Balance punishment with understanding.", "tone": "PRACTICAL", "vector": {"justice_focus": 1.5, "mercy_focus": 1.5}, "affinity": {"pragmatism": 1.0}},
    # Expansion / isolation
    {"text": "Our destiny lies beyond these borders.", "tone": "MYSTICAL", "vector": {"expansion_focus": 3.0, "military_focus": 1.0}, "affinity": {"ambition": 1.5, "charisma": 0.5}},
    {"text": "We are sufficient unto ourselves.", "tone": "PRACTICAL", "vector": {"isolation_focus": 3.0, "agriculture_focus": 1.0}, "affinity": {"humility": 0.8, "paranoia": 0.5}},
    # Mixed / nuanced
    {"text": "Trust in the process. The harvest will come.", "tone": "GENTLE", "vector": {"agriculture_focus": 1.0, "faith_focus": 1.0, "mercy_focus": 0.5}, "affinity": {"self_belief": 0.5, "empathy": 0.5}},
    {"text": "I have seen what is coming. Prepare yourselves.", "tone": "MYSTICAL", "vector": {"military_focus": 1.5, "austerity_focus": 1.5, "faith_focus": 1.0}, "affinity": {"paranoia": 0.8, "conviction": 0.8}},
    {"text": "The kingdom's heart beats in its people.", "tone": "GENTLE", "vector": {"mercy_focus": 1.5, "agriculture_focus": 1.0, "reform_focus": 0.5}, "affinity": {"empathy": 1.0, "charisma": 0.5}},
    {"text": "I speak not for myself, but for what must be done.", "tone": "PRACTICAL", "vector": {"justice_focus": 1.0, "reform_focus": 1.0, "austerity_focus": 1.0}, "affinity": {"humility": 1.0, "conviction": 0.5}},
    {"text": "Silence was my counsel. Now I return with clarity.", "tone": "MYSTICAL", "vector": {"faith_focus": 2.0, "reform_focus": 1.0}, "affinity": {"clarity": 1.5, "self_belief": 0.5}},
    {"text": "Let those who hoard be reminded of their duty.", "tone": "SEVERE", "vector": {"justice_focus": 2.0, "trade_focus": 1.0, "mercy_focus": -0.5}, "affinity": {"severity": 0.8, "empathy": -0.3}},
    {"text": "Prosperity is not given. It is grown.", "tone": "PRACTICAL", "vector": {"agriculture_focus": 2.0, "trade_focus": 1.0, "reform_focus": 0.5}, "affinity": {"pragmatism": 1.0, "ambition": 0.3}},
    {"text": "I do not pretend to have all the answers.", "tone": "DEFLECTIVE", "vector": {"faith_focus": -1.0, "reform_focus": 0.5}, "affinity": {"doubt": 1.5, "humility": 1.0}},
    {"text": "The matter is not yet clear to me.", "tone": "DEFLECTIVE", "vector": {}, "affinity": {"doubt": 1.0, "humility": 0.5}},
]

# Audience templates — responses to characters
_AUDIENCE_TEMPLATES = [
    {"text": "I see your concern. It shall be addressed.", "tone": "GENTLE", "vector": {"mercy_focus": 1.0}, "affinity": {"empathy": 1.0}},
    {"text": "You have my trust. Act as you see fit.", "tone": "PRACTICAL", "vector": {"reform_focus": 0.5}, "affinity": {"humility": 0.5, "self_belief": 0.5}},
    {"text": "Do not test my patience on this matter.", "tone": "SEVERE", "vector": {"justice_focus": 1.5}, "affinity": {"severity": 1.0, "conviction": 0.5}},
    {"text": "Bring me proof before making such claims.", "tone": "PRACTICAL", "vector": {"justice_focus": 0.5, "reform_focus": 0.5}, "affinity": {"pragmatism": 1.0, "doubt": 0.3}},
    {"text": "The visions speak of your path differently.", "tone": "MYSTICAL", "vector": {"faith_focus": 1.5}, "affinity": {"clarity": 0.5, "self_belief": 1.0}},
    {"text": "Your loyalty does not go unnoticed.", "tone": "GENTLE", "vector": {"mercy_focus": 0.5, "faith_focus": 0.5}, "affinity": {"empathy": 0.8, "charisma": 0.5}},
    {"text": "You overstep. Remember your station.", "tone": "SEVERE", "vector": {"justice_focus": 1.0, "military_focus": 0.5}, "affinity": {"severity": 1.5, "paranoia": 0.5}},
    {"text": "I will consider your words in silence.", "tone": "DEFLECTIVE", "vector": {}, "affinity": {"doubt": 0.8, "humility": 0.5}},
    {"text": "You and I want the same thing. Let us find common ground.", "tone": "GENTLE", "vector": {"mercy_focus": 1.0, "reform_focus": 0.5}, "affinity": {"empathy": 1.0, "charisma": 1.0}},
    {"text": "If what you say is true, heads will roll.", "tone": "SEVERE", "vector": {"justice_focus": 2.5}, "affinity": {"severity": 1.0, "conviction": 1.0}},
]


class SpeechGenerator:
    """
    Generate context-sensitive, trait-sculpted speech options.

    Spec §31-36, §42: Options are not static.  They are generated from
    current state, Oracle personality, faction tensions, and trajectory.

    The player sees words.  The engine processes vectors.
    """

    @classmethod
    def generate_decree_options(cls, state: KingdomState, rng: SeededRNG,
                                count: int = 4) -> List[SpeechOption]:
        """Generate decree options sculpted by Oracle build and kingdom state."""
        gen_rng = rng.fork(f"speech_gen_{state.tick}")
        oracle = state.oracle

        # Score every template by affinity to Oracle's current drifted traits
        scored: List[Tuple[float, dict]] = []
        for tmpl in _DECREE_TEMPLATES:
            score = cls._score_template(tmpl, oracle, state)
            scored.append((score, tmpl))

        # Weighted random selection (higher affinity = more likely)
        scored.sort(key=lambda x: x[0], reverse=True)

        # Always include at least one high-affinity and one contrasting option
        selected = []

        # Top affinity picks
        top_pool = scored[:max(8, len(scored) // 2)]
        while len(selected) < count - 1 and top_pool:
            idx = gen_rng.randint(0, min(len(top_pool) - 1, 5))
            selected.append(top_pool.pop(idx))

        # One contrasting/deviation option (spec §42: deviation is possible)
        bottom_pool = scored[len(scored) // 2:]
        if bottom_pool:
            idx = gen_rng.randint(0, min(len(bottom_pool) - 1, 5))
            selected.append(bottom_pool[idx])
        elif scored:
            selected.append(scored[-1])

        # Build SpeechOption objects
        options = []
        for i, (score, tmpl) in enumerate(selected[:count]):
            options.append(SpeechOption(
                option_id=f"decree_{state.tick}_{i}",
                text=tmpl["text"],
                tone=Tone[tmpl["tone"]],
                mode=SpeechMode.DECREE,
                policy_vector=dict(tmpl["vector"]),
                propagation_magnitude=1.0 + score * 0.1,
            ))

        return options

    @classmethod
    def generate_audience_options(cls, state: KingdomState,
                                  character_id: str, rng: SeededRNG,
                                  count: int = 3) -> List[SpeechOption]:
        """Generate audience response options for a specific character."""
        gen_rng = rng.fork(f"audience_{state.tick}_{character_id}")
        oracle = state.oracle

        scored: List[Tuple[float, dict]] = []
        for tmpl in _AUDIENCE_TEMPLATES:
            score = cls._score_template(tmpl, oracle, state)
            scored.append((score, tmpl))

        scored.sort(key=lambda x: x[0], reverse=True)
        selected = []
        pool = scored[:max(5, len(scored))]
        while len(selected) < count and pool:
            idx = gen_rng.randint(0, min(len(pool) - 1, 3))
            selected.append(pool.pop(idx))

        options = []
        for i, (score, tmpl) in enumerate(selected[:count]):
            options.append(SpeechOption(
                option_id=f"audience_{state.tick}_{character_id[:8]}_{i}",
                text=tmpl["text"],
                tone=Tone[tmpl["tone"]],
                mode=SpeechMode.AUDIENCE,
                policy_vector=dict(tmpl["vector"]),
                propagation_magnitude=0.8 + score * 0.05,
                target_character_id=character_id,
            ))

        return options

    @classmethod
    def _score_template(cls, tmpl: dict, oracle: OracleBuild,
                        state: KingdomState) -> float:
        """
        Score how well a template matches the Oracle's current build.

        Higher score = more likely to be offered as an option.
        Trajectory bias (spec §43): repeated tone usage boosts similar templates.
        """
        affinity = tmpl.get("affinity", {})
        score = 0.0

        for trait, weight in affinity.items():
            if trait == "pragmatism":
                # Not a direct trait — derive from clarity + conviction average
                effective = (oracle.effective("clarity") + oracle.effective("conviction")) / 2.0
            else:
                effective = oracle.effective(trait)
            # Normalise to -1..1 scale (25 is neutral)
            normalised = (effective - 25.0) / 25.0
            score += normalised * weight

        # Trajectory bias: if this tone has been used a lot, boost slightly
        tone_name = tmpl.get("tone", "PRACTICAL")
        trajectory_boost = oracle.trajectory.get(tone_name, 0.0) * 0.05
        score += min(trajectory_boost, 1.0)

        # Context sensitivity: boost templates relevant to current crises
        vector = tmpl.get("vector", {})
        if "agriculture_focus" in vector and state.physical.resource_pressure > 50:
            score += 0.5
        if "military_focus" in vector and state.political.external_threat > 50:
            score += 0.5
        if "reform_focus" in vector and state.political.corruption > 50:
            score += 0.3
        if "faith_focus" in vector and state.belief.public_faith < 40:
            score += 0.4
        if "trade_focus" in vector and state.physical.trade_volume < 25:
            score += 0.3
        if "mercy_focus" in vector and state.social.fear_level > 60:
            score += 0.4
        if "justice_focus" in vector and state.social.class_tension > 60:
            score += 0.3

        return score


# ---- Compound Event Synthesis (spec §47) ----

class CompoundEventSynthesizer:
    """
    When multiple active events share affected variables, factions,
    or domain, they may merge into compound events.
    """

    @classmethod
    def check_compounds(cls, state: KingdomState, rng: SeededRNG) -> List[SimEvent]:
        """Scan active events for merge candidates."""
        pending = state.active_events.pending()
        if len(pending) < 2:
            return []

        new_compounds: List[SimEvent] = []
        merged_ids: Set[str] = set()

        for i, a in enumerate(pending):
            if a.event_id in merged_ids or a.kind == EventKind.COMPOUND:
                continue
            for b in pending[i + 1:]:
                if b.event_id in merged_ids or b.kind == EventKind.COMPOUND:
                    continue

                # Check overlap conditions
                same_domain = a.domain == b.domain
                shared_factions = set(a.involved_factions) & set(b.involved_factions)
                shared_actors = set(a.involved_actors) & set(b.involved_actors)
                severity_sum = a.severity + b.severity

                overlap_score = 0
                if same_domain:
                    overlap_score += 2
                overlap_score += len(shared_factions)
                overlap_score += len(shared_actors)

                # Need significant overlap to merge
                if overlap_score >= 2 and severity_sum > 60 and rng.random() < 0.4:
                    compound = SimEvent(
                        event_id=f"ev_{state.tick}_compound_{a.event_id[:8]}_{b.event_id[:8]}",
                        kind=EventKind.COMPOUND,
                        domain=a.domain,
                        tick=state.tick,
                        severity=min(100, severity_sum * 0.8),
                        urgency=max(a.urgency, b.urgency) * 1.2,
                        description=f"Converging crises: {a.description[:50]}... AND {b.description[:50]}...",
                        involved_actors=list(set(a.involved_actors + b.involved_actors)),
                        involved_factions=list(set(a.involved_factions + b.involved_factions)),
                        caused_by=a.event_id,
                        source_events=[a.event_id, b.event_id],
                    )
                    new_compounds.append(compound)
                    merged_ids.add(a.event_id)
                    merged_ids.add(b.event_id)

                    # Record causal edges: source events → compound
                    state.causal_ledger.record_delta(
                        source_type="event", source_id=a.event_id,
                        target_type="event", target_id=compound.event_id,
                        variable="compound_synthesis", delta=a.severity,
                        tick=state.tick,
                        metadata={"merged_with": b.event_id},
                    )
                    state.causal_ledger.record_delta(
                        source_type="event", source_id=b.event_id,
                        target_type="event", target_id=compound.event_id,
                        variable="compound_synthesis", delta=b.severity,
                        tick=state.tick,
                        metadata={"merged_with": a.event_id},
                    )
                    break

        # Remove merged source events from queue and mark resolved
        if merged_ids:
            remaining = [e for e in pending if e.event_id not in merged_ids]
            state.active_events._events = remaining
            state.active_events._events.sort(key=lambda e: e.severity * e.urgency, reverse=True)

        return new_compounds


# ---- Succession System (spec §29) ----

class SuccessionEngine:
    """
    When key characters die, generate procedural replacements.

    Successors inherit faction alignment and partial relationships
    but introduce new personality variance.
    """

    @classmethod
    def generate_successor(cls, dead_char: Character, state: KingdomState,
                           rng: SeededRNG) -> Character:
        """Create a replacement for a dead character.
        
        Phase 5: Successor personality is biased by the current era.
        A character who rises during AUTHORITARIAN_CONSOLIDATION will
        trend authoritarian.  This is intergenerational value drift.
        """
        succ_rng = rng.fork(f"succession_{dead_char.character_id}_{state.tick}")

        new_id = f"{dead_char.character_id}_succ_{state.world_year}"
        new_name = WorldBuilder.generate_character_name(succ_rng)

        successor = Character(
            character_id=new_id,
            name=new_name,
            role=dead_char.role,
            faction_id=dead_char.faction_id,
            age=succ_rng.randint(25, 40),
            # New personality — variance from predecessor
            ambition=max(10, min(90, dead_char.ambition + succ_rng.gauss(0, 15))),
            risk_tolerance=max(10, min(90, dead_char.risk_tolerance + succ_rng.gauss(0, 15))),
            piety=max(10, min(90, dead_char.piety + succ_rng.gauss(0, 15))),
            pragmatism=max(10, min(90, dead_char.pragmatism + succ_rng.gauss(0, 15))),
            cruelty=max(5, min(60, dead_char.cruelty + succ_rng.gauss(0, 10))),
            charisma=max(15, min(85, dead_char.charisma + succ_rng.gauss(0, 15))),
            # Fresh dynamic state
            oracle_loyalty=max(20, min(80, succ_rng.uniform(30, 70))),
            public_popularity=succ_rng.uniform(20, 50),
            private_grievances=0.0,
            stress=succ_rng.uniform(5, 25),
            health=succ_rng.uniform(80, 100),
        )

        # ── Phase 5: Intergenerational value drift ──
        # Bias personality by current era (not random — shaped by history)
        IntergenerationalDrift.bias_successor(successor, state.current_era, succ_rng)
        # Bias oracle loyalty by kingdom health trajectory
        faction = state.factions.get(dead_char.faction_id)
        IntergenerationalDrift.bias_faction_loyalty(
            successor, state.current_era, faction, state, succ_rng
        )

        return successor

    @classmethod
    def process_deaths(cls, state: KingdomState, rng: SeededRNG) -> List[SimEvent]:
        """
        Find dead characters, generate successors, update relationships,
        and emit succession events.
        """
        events: List[SimEvent] = []
        dead_ids = [cid for cid, c in state.characters.items() if not c.alive]

        for dead_id in dead_ids:
            dead_char = state.characters[dead_id]
            successor = cls.generate_successor(dead_char, state, rng)

            # Transfer some relationships (weakened)
            old_edges = state.relationships.get_edges_from(dead_id) + state.relationships.get_edges_to(dead_id)
            for edge in old_edges:
                new_weight = edge.weight * 0.3  # successor inherits 30% of relationships
                if edge.from_id == dead_id:
                    state.relationships.set_weight(successor.character_id, edge.to_id, edge.rel_type, new_weight)
                else:
                    state.relationships.set_weight(edge.from_id, successor.character_id, edge.rel_type, new_weight)

            # Replace in character dict
            del state.characters[dead_id]
            state.characters[successor.character_id] = successor

            events.append(SimEvent(
                event_id=f"ev_{state.tick}_succession_{dead_id}",
                kind=EventKind.SUCCESSION,
                domain=EventDomain.POLITICAL,
                tick=state.tick,
                severity=45.0,
                urgency=30.0,
                description=f"{dead_char.name} has passed. {successor.name} rises to the role of {dead_char.role.name.replace('_', ' ').title()}.",
                involved_actors=[successor.character_id],
                involved_factions=[dead_char.faction_id] if dead_char.faction_id else [],
                caused_by=None,
            ))

            # Record causal edge: character death → succession event
            state.causal_ledger.record_delta(
                source_type="succession",
                source_id=dead_id,
                target_type="character",
                target_id=successor.character_id,
                variable="role_transfer",
                delta=1.0,
                tick=state.tick,
                metadata={
                    "deceased": dead_char.name,
                    "successor": successor.name,
                    "role": dead_char.role.name,
                },
            )

        return events


# ---- Oracle Psychology Engine (spec §38, §40-41) ----

class OraclePsychology:
    """
    Manages the Oracle's inner psychological state.

    Spec §38: Inner monologue — subjective layer that may overestimate
    danger, minimize threats, catastrophize instability.

    Spec §40: Drift emerges from base traits × recent outcomes × absence.
    """

    @classmethod
    def update_after_speech(cls, state: KingdomState, option: SpeechOption,
                            effective_magnitude: float):
        """Update Oracle psychology after making a speech."""
        oracle = state.oracle

        # Speaking boosts self_belief slightly (you took action)
        oracle.ego += 0.5 * effective_magnitude
        oracle.stress = max(0, oracle.stress - 1.0)

        # Tone-specific effects
        if option.tone == Tone.SEVERE:
            oracle.ego += 0.3
            oracle.stress += 0.5
        elif option.tone == Tone.GENTLE:
            oracle.hope += 0.3
            oracle.stress -= 0.3
        elif option.tone == Tone.MYSTICAL:
            oracle.ego += 0.5
        elif option.tone == Tone.DEFLECTIVE:
            oracle.dread += 0.5
            oracle.ego -= 0.5

    @classmethod
    def tick_psychology(cls, state: KingdomState, rng: SeededRNG):
        """
        Per-tick psychological drift.

        Inner state changes emerge from base traits × recent outcomes × absence.
        """
        oracle = state.oracle
        b = state.belief
        s = state.social
        pol = state.political

        # ---- Ego drift ----
        # High faith + high self_belief → ego inflation
        faith_factor = b.public_faith / 100.0
        self_belief_factor = oracle.effective("self_belief") / 50.0
        humility_factor = oracle.effective("humility") / 50.0
        oracle.ego += (faith_factor * self_belief_factor - humility_factor) * 0.1
        oracle.ego *= 0.98  # natural decay toward 0

        # ---- Stress drift ----
        # Kingdom instability increases stress
        instability = (
            s.class_tension / 100.0 * 0.3
            + pol.corruption / 100.0 * 0.2
            + state.physical.resource_pressure / 100.0 * 0.3
            + (100 - b.public_faith) / 100.0 * 0.2
        )
        empathy_factor = oracle.effective("empathy") / 50.0
        oracle.stress += instability * empathy_factor * 0.5 - 0.1
        oracle.stress = max(-10, min(50, oracle.stress))

        # ---- Hope drift ----
        health_composite = state.health.composite / 100.0
        oracle.hope += (health_composite - 0.5) * 0.3
        oracle.hope *= 0.97

        # ---- Dread drift ----
        # High paranoia + threats → dread
        paranoia_factor = oracle.effective("paranoia") / 50.0
        doubt_factor = oracle.effective("doubt") / 50.0
        threat = pol.external_threat / 100.0
        oracle.dread += (threat * paranoia_factor + doubt_factor * 0.1 - 0.05) * 0.5
        oracle.dread = max(-5, min(50, oracle.dread))

        # ---- Trait drift based on accumulated psychology ----
        outcome_vector: Dict[str, float] = {}
        if oracle.ego > 5:
            outcome_vector["self_belief"] = 0.3
            outcome_vector["humility"] = -0.2
        if oracle.stress > 10:
            outcome_vector["doubt"] = 0.2
            outcome_vector["paranoia"] = 0.1
        if oracle.hope > 5:
            outcome_vector["empathy"] = 0.1
            outcome_vector["ambition"] = 0.1
        if oracle.dread > 5:
            outcome_vector["paranoia"] = 0.3
            outcome_vector["severity"] = 0.1

        if outcome_vector:
            oracle.apply_drift(outcome_vector, absence_days=b.sacred_silence_weight * 10)

    @classmethod
    def generate_inner_monologue_data(cls, state: KingdomState) -> Dict[str, Any]:
        """
        Produce the Cold Layer data that a Hot Layer LLM would use
        to compose inner monologue prose.

        Returns structured data, NOT prose.  The LLM step is separate.
        """
        oracle = state.oracle
        dominant = cls._dominant_emotion(oracle)
        # Self-perception label
        if oracle.ego > 5:
            self_perception = "inflated"
        elif oracle.ego < -3:
            self_perception = "diminished"
        elif oracle.stress > 10:
            self_perception = "burdened"
        elif oracle.hope > 5:
            self_perception = "hopeful"
        elif oracle.dread > 5:
            self_perception = "fearful"
        else:
            self_perception = "balanced"

        return {
            "ego": oracle.ego,
            "stress": oracle.stress,
            "hope": oracle.hope,
            "dread": oracle.dread,
            "doubt_level": oracle.effective("doubt"),
            "paranoia_level": oracle.effective("paranoia"),
            "self_perception": self_perception,
            "dominant_emotion": dominant,
            "trait_snapshot": {t: oracle.effective(t) for t in ORACLE_TRAITS},
            "public_faith": state.belief.public_faith,
            "health_composite": state.health.composite,
            "health_trend": state.health.trend,
            "active_events_count": len(state.active_events),
            "top_event": state.active_events.peek().description if state.active_events.peek() else None,
            "sacred_silence": state.belief.sacred_silence_weight,
        }

    @classmethod
    def _dominant_emotion(cls, oracle: OracleBuild) -> str:
        """Determine the dominant emotional state."""
        emotions = {
            "hubris": oracle.ego,
            "anxiety": oracle.stress,
            "optimism": oracle.hope,
            "dread": oracle.dread,
        }
        dominant = max(emotions, key=emotions.get)
        if emotions[dominant] < 2.0:
            return "calm"
        return dominant


# ---- Myth Memory Ticker (spec §13) ----

class MythMemory:
    """
    Manages decree myth weight and recency decay.

    Spec §13: Every decree enters a historical ledger.
    Memory has recency weight (decays), myth amplification (grows
    if uncontradicted), selective forgetting, retroactive reinterpretation.
    """

    @classmethod
    def tick_memory(cls, state: KingdomState, rng: SeededRNG):
        """Update decree memory weights each tick."""
        current_tick = state.tick

        for decree in state.decree_history:
            age_ticks = current_tick - decree.tick

            # Recency decays logarithmically
            decree.recency_weight = 1.0 / (1.0 + math.log1p(age_ticks) * 0.1)

            # Myth weight grows if the decree is old and uncontradicted
            # (contradiction detection: a newer decree with opposing policy vector)
            contradicted = cls._is_contradicted(decree, state.decree_history)
            if not contradicted and age_ticks > 30:
                # Silence amplifies myth (spec §13: silence makes past words more sacred)
                silence_boost = state.belief.sacred_silence_weight * 0.001
                decree.myth_weight = min(10.0, decree.myth_weight + 0.005 + silence_boost)
            elif contradicted:
                decree.myth_weight *= 0.995  # slow decay if contradicted

        # Myth accumulation into belief layer
        total_myth = sum(d.myth_weight * d.recency_weight for d in state.decree_history)
        state.belief.myth_accumulation = min(100, total_myth * 0.5)

        # Cultural memory strength
        if len(state.decree_history) > 0:
            avg_myth = total_myth / len(state.decree_history)
            state.belief.cultural_memory_strength = min(100, avg_myth * 20)

    @classmethod
    def _is_contradicted(cls, decree: DecreeRecord, history: List[DecreeRecord]) -> bool:
        """
        Check if a later decree contradicts this one.

        Contradiction = a newer decree with an opposing sign on the same policy axis.
        """
        for later in history:
            if later.tick <= decree.tick:
                continue
            for axis, value in decree.policy_vector.items():
                later_value = later.policy_vector.get(axis, 0)
                if value != 0 and later_value != 0 and (value * later_value < 0):
                    return True
        return False


# ============================================================
# SECTION 13: SIMULATION ENGINE (Pure Computation, NO LLM)
# ============================================================
#
# Spec: Simulation is pure math.  Every tick advances all four
# layers, applies cross-layer coupling, ages characters, checks
# event thresholds, and updates the health index.
#
# This is a SKELETON — the actual formulas will be tuned in Phase 2.
# The structure is here so the tick loop, save/load, and controller
# can be tested end-to-end.

class SimulationEngine:
    """
    Deterministic tick-based simulation.

    Each tick:
      0. Equilibrium mean-reversion pull (Phase 8)
      1. Advance physical layer (production, trade, resources)
      2. Apply belief → social/political coupling
      3. Apply social/political → physical coupling
      4. Decay/amplify ripples
      5. Check event thresholds
      6. Age characters (yearly boundary)
      7. Update health index

    Phase 9 — Sensitive Propagation:
    The Oracle is a pebble, not a steering wheel.  Small decree
    deltas (±1, ±2) should produce divergent timelines 500 ticks
    later through nonlinear cross-coupling, sigmoid thresholds,
    state-dependent mean-reversion, and timing jitter.  The system
    sits at the edge of chaos: tight convergence at rest, but a
    +1 at tick 50 alters which faction dominates at tick 120,
    which threshold is crossed at tick 250, which character dies
    at tick 300, and which baseline shift crystallises at tick 600.
    """

    # Mean-reversion pull rate per tick.
    # At 0.008, a variable 50 points from equilibrium gains ~0.4/tick
    # plus a nonlinear boost at large displacement.  Strong enough
    # to overpower cross-layer coupling drains that create deadlocked
    # attractor states, while still allowing shocks to dominate
    # short-term dynamics.
    EQUILIBRIUM_PULL_RATE: float = 0.008

    @staticmethod
    def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
        return max(lo, min(hi, val))

    @staticmethod
    def _sigmoid(x: float, center: float = 0.0, steepness: float = 1.0) -> float:
        """Logistic sigmoid: returns 0→1.  Use instead of hard thresholds.

        At x=center returns 0.5.  steepness controls sharpness of
        the transition.  A +1 shift at x≈center changes the output
        meaningfully; the same +1 far from center is negligible.
        This makes small nudges near the tipping point matter.
        """
        t = (x - center) * steepness
        t = max(-500.0, min(500.0, t))  # prevent overflow
        return 1.0 / (1.0 + math.exp(-t))

    @classmethod
    def tick_equilibrium_pull(cls, state: KingdomState, rng: SeededRNG):
        """
        Phase 8: Equilibrium mean-reversion.

        Each variable is gently pulled toward its equilibrium baseline.
        The pull is:  delta = (baseline - current) * PULL_RATE

        This is the mechanism that makes baseline shifts structural:
        shifting the equilibrium changes where the system WANTS to rest,
        not just where it IS right now.

        Variables with no equilibrium entry are skipped.
        treasury is excluded (absolute units, not normalized).
        food_stores is excluded (buffer stock, not an equilibrium concept).
        resource_pressure is derived, not pulled directly.
        """
        if not hasattr(state, "equilibrium_baselines"):
            return

        baselines = state.equilibrium_baselines
        ledger = state.causal_ledger
        k = cls.EQUILIBRIUM_PULL_RATE

        # ── Phase 9: Institutional-strength-modulated reversion ──
        #
        # Weak institutions → weak reversion → more volatility.
        # Strong institutions → strong reversion → stability.
        #
        # inst_factor ranges from 0.3 (collapsed institutions) to 1.2
        # (very strong institutions).  This means early decree-driven
        # institutional weakening increases future sensitivity to ALL
        # perturbations — the pebble-in-pond effect.
        inst_strength = getattr(state.political, "institutional_strength", 50.0)
        cohesion = getattr(state.social, "cohesion", 50.0)
        # Blend: 70% institutional strength, 30% social cohesion
        structural_health = inst_strength * 0.7 + cohesion * 0.3
        # Map 0→100 structural_health onto 0.3→1.2 reversion multiplier
        inst_factor = 0.3 + 0.9 * (structural_health / 100.0)

        # Variables to skip (derived, absolute, or buffer-stock)
        # Phase 10: interpretation_divergence is excluded — it now has
        # its own dynamic coupling in tick_interpretation_divergence()
        # rather than reverting to a static baseline.
        SKIP = {"treasury", "food_stores", "resource_pressure", "interpretation_divergence"}

        # Layer name → layer object mapping
        layer_map = {
            "physical": state.physical,
            "social": state.social,
            "political": state.political,
            "belief": state.belief,
        }

        for var_name, baseline in baselines.items():
            if var_name in SKIP:
                continue

            # Find which layer owns this variable
            for layer_name, layer in layer_map.items():
                if hasattr(layer, var_name):
                    current = getattr(layer, var_name)
                    if not isinstance(current, (int, float)):
                        break
                    gap = baseline - current
                    # Nonlinear pull: stronger when far from baseline.
                    # At gap=10 → 1.33× base rate, gap=20 → 2.33×, gap=30 → 4×.
                    # The quadratic term ensures the pull can always
                    # overpower constant per-tick drains at large displacement.
                    distance_factor = 1.0 + (gap * gap) / 300.0
                    # Phase 9: scale by institutional health.
                    # Weak institutions = softer reversion = more drift.
                    delta = gap * k * distance_factor * inst_factor

                    # Phase 10: Hope is volatile — reduced mean reversion.
                    # Hope reversion is cut by 40%, then further scaled by
                    # institutional strength: weak institutions can't sustain
                    # hope through inertia alone, so hope becomes path-
                    # dependent on Oracle governance rather than self-correcting.
                    if var_name == "hope_level":
                        hope_inst_scale = min(1.0, inst_strength / 60.0)  # 0→1.0
                        delta *= 0.6 * hope_inst_scale  # 40% base cut × inst weakness

                    if abs(delta) < 1e-6:
                        break
                    new_val = cls._clamp(current + delta)
                    setattr(layer, var_name, new_val)
                    ledger.record_delta(
                        "equilibrium_pull", f"eq_{var_name}",
                        "layer", state.kingdom_id,
                        var_name, new_val - current, state.tick,
                        {"baseline": baseline, "current_before": current,
                         "distance_factor": round(distance_factor, 3),
                         "inst_factor": round(inst_factor, 3)},
                    )
                    break

    @classmethod
    def tick_physical(cls, state: KingdomState, rng: SeededRNG):
        """
        Layer A tick: food, infrastructure, trade, labour.

        Inertia principle (spec §14): values change slowly.
        """
        p = state.physical
        ledger = state.causal_ledger

        # Phase 5: Era modifiers for physical layer
        era_mods = EraClassifier.get_modifiers(state.current_era)
        food_consumption_mult = era_mods.get("food_consumption_multiplier", 1.0)

        # ── FOOD PRODUCTION → FOOD STORES ──────────────────────
        #
        # Structural model: consumption is NOT fixed at 1.0.
        # People ration when stores are low (demand destruction).
        # This replaces the knife-edge at prod=50 that created a
        # binary surplus/deficit attractor.
        #
        # Rationing curve: consumption = base * ration_factor
        #   ration_factor = 1.0       when food_stores >= 60
        #   ration_factor = 0.4       when food_stores = 0  (starvation)
        #   ration_factor ~ 0.7       when food_stores = 20 (tight)
        # This means even prod=35 can sustain a starving kingdom at
        # low consumption, creating a "struggling" steady state rather
        # than guaranteed famine.
        pop_consumption_scale = max(0.1, p.labor_pool / 50.0)
        ration_factor = 0.4 + 0.6 * min(1.0, p.food_stores / 60.0)
        daily_consumption = 1.0 * food_consumption_mult * pop_consumption_scale * ration_factor
        daily_production = p.food_production / 50.0
        food_delta = (daily_production - daily_consumption) * 0.5
        p.food_stores += food_delta
        p.food_stores = cls._clamp(p.food_stores, 0, 200)
        ledger.record_delta("coupling", "physical_tick", "layer", state.kingdom_id,
                            "food_stores", food_delta, state.tick,
                            {"ration_factor": round(ration_factor, 3),
                             "daily_prod": round(daily_production, 3),
                             "daily_cons": round(daily_consumption, 3)})

        # ── Phase 8C: FOOD MID-BAND GRAVITY ───────────────────
        #
        # Problem: food_stores has two absorbing basins — once it
        # reaches 200 it stays there (no spoilage penalty), and
        # once it reaches 0 it stays there (no emergency relief).
        # This produces bimodal outcomes instead of a spectrum.
        #
        # Solution: two opposing gentle forces that push food_stores
        # toward the 40–120 mid-band.
        #
        # 1) SPOILAGE — accelerates above 80, significant above 140.
        #    spoilage = BASE + (food_stores/200)^3 * SCALE
        #    This prevents permanent 200 lock.
        #
        # 2) EMERGENCY SUBSISTENCE — when food_stores < 15 and the
        #    kingdom isn't completely collapsed, people forage,
        #    hunt, and barter at a subsistence level.  This creates
        #    a floor around 5–15 that slows the final slide to 0.

        # Spoilage: base 0.01/tick + cubic ramp above 80
        if p.food_stores > 40.0:
            spoil_base = 0.01
            spoil_ratio = p.food_stores / 200.0  # 0→1
            spoil_ramp = (spoil_ratio ** 3) * 0.6  # cubic: negligible at 80, ~0.08 at 140, ~0.6 at 200
            spoilage = spoil_base + spoil_ramp
            p.food_stores -= spoilage
            p.food_stores = max(0.0, p.food_stores)
            ledger.record_delta(
                "spoilage", "food_spoilage", "layer", state.kingdom_id,
                "food_stores", -spoilage, state.tick,
            )

        # Emergency subsistence: people forage when starving
        # Gated by labor_pool (need living people to forage) and
        # NOT active during terminal collapse (health < 5).
        if p.food_stores < 15.0 and p.labor_pool > 5.0:
            health_viable = state.health.composite > 5.0 if hasattr(state.health, "composite") else True
            if health_viable:
                desperation = (15.0 - p.food_stores) / 15.0  # 1.0 at 0, 0.0 at 15
                forage_ability = min(1.0, p.labor_pool / 30.0)
                subsistence = desperation * forage_ability * 0.35  # max ~0.35/tick
                p.food_stores += subsistence
                p.food_stores = cls._clamp(p.food_stores, 0, 200)
                ledger.record_delta(
                    "subsistence", "emergency_forage", "layer", state.kingdom_id,
                    "food_stores", subsistence, state.tick,
                )

        # ── RESOURCE PRESSURE (continuous) ────────────────────
        #
        # RP tracks the gap between what people need and what's stored.
        # Continuous formula: RP drifts toward a target based on
        # food_stores, rather than step-function jumps.
        #
        # Target curve (food_stores → RP target):
        #   food=0   → RP target=95  (severe)
        #   food=20  → RP target=70  (crisis)
        #   food=40  → RP target=40  (stressed)
        #   food=60  → RP target=15  (comfortable)
        #   food=100 → RP target=0   (abundant)
        #
        # RP moves toward target at 0.3/tick — fast enough to respond
        # to real crises, slow enough to not whipsaw.
        rp_before = p.resource_pressure
        rp_target = cls._clamp(95.0 - (p.food_stores / 100.0) * 95.0)
        rp_gap = rp_target - p.resource_pressure
        rp_speed = 0.3
        p.resource_pressure = cls._clamp(p.resource_pressure + rp_gap * 0.05 + math.copysign(min(rp_speed, abs(rp_gap)), rp_gap))

        # ── Phase 7E: Population Reset Pressure ────────────────
        # Fewer mouths = less food needed regardless of food stores.
        # Without this, RP stays at 99+ for 15k ticks during collapse
        # because the food-based formula only decreases RP when food>60
        # (impossible during famine).  Low population IS reduced demand.
        # Scale: labor_pool=10 → RP relief 2.0/tick, labor_pool=30 → 1.0/tick
        if p.labor_pool < 40.0:
            pop_relief = (40.0 - p.labor_pool) / 40.0 * 2.5
            p.resource_pressure = cls._clamp(p.resource_pressure - pop_relief)

        rp_delta = p.resource_pressure - rp_before
        ledger.record_delta("coupling", "physical_tick", "layer", state.kingdom_id,
                            "resource_pressure", rp_delta, state.tick)

        # Infrastructure slow decay (needs maintenance)
        # During grace period, decay is halved (new administration invests)
        in_grace = (hasattr(state, "terminal_grace_until") and
                    state.tick < state.terminal_grace_until)
        infra_delta = -0.005 if in_grace else -0.01
        p.infrastructure = cls._clamp(p.infrastructure + infra_delta)
        ledger.record_delta("coupling", "physical_tick", "layer", state.kingdom_id,
                            "infrastructure", infra_delta, state.tick)

        # Trade volume influenced by infrastructure
        trade_delta = (p.infrastructure - 50.0) * 0.005
        p.trade_volume = cls._clamp(p.trade_volume + trade_delta)
        ledger.record_delta("coupling", "physical_tick", "layer", state.kingdom_id,
                            "trade_volume", trade_delta, state.tick)

        # Treasury from trade
        treasury_delta = p.trade_volume * 0.1 - 5.0
        p.treasury += treasury_delta
        p.treasury = max(0.0, p.treasury)
        ledger.record_delta("coupling", "physical_tick", "layer", state.kingdom_id,
                            "treasury", treasury_delta, state.tick)

        # ── Phase 8A: TRADE IMPORT → FOOD CONVERSION ──────────
        #
        # The missing conversion pathway.  If trade_volume and treasury
        # are high but food_stores is low, the kingdom imports food.
        # Gated by infrastructure (needs roads/ports to receive goods).
        #
        # This prevents "rich but starving forever" — the kingdom's
        # wealth actually buys food resilience.
        #
        # Import capacity: trade * infra_gate * treasury_gate
        # Cost: each unit of food imported costs treasury.
        # Cap: imports can fill food_stores up to 50 (not abundance,
        #      just survival — domestic production needed for surplus).
        if p.food_stores < 50.0 and p.trade_volume > 15.0 and p.treasury > 100.0:
            infra_gate = cls._clamp(
                (p.infrastructure - 10.0) / 40.0, 0.0, 1.0
            )
            trade_capacity = (p.trade_volume - 15.0) / 85.0  # 0→1
            treasury_willingness = min(1.0, (p.treasury - 100.0) / 500.0)
            shortfall = (50.0 - p.food_stores) / 50.0  # 0→1 urgency

            import_amount = (
                shortfall * trade_capacity * infra_gate * treasury_willingness
                * 0.8  # max ~0.8/tick import rate
            )
            if import_amount > 0.01:
                import_cost = import_amount * 15.0  # food is expensive
                p.food_stores = cls._clamp(p.food_stores + import_amount, 0, 200)
                p.treasury = max(0.0, p.treasury - import_cost)
                ledger.record_delta(
                    "trade_import", "food_import", "layer", state.kingdom_id,
                    "food_stores", import_amount, state.tick,
                    {"cost": import_cost, "trade_capacity": trade_capacity,
                     "infra_gate": infra_gate},
                )
                ledger.record_delta(
                    "trade_import", "food_import_cost", "layer", state.kingdom_id,
                    "treasury", -import_cost, state.tick,
                )

        # ── Phase 8B: TREASURY → INFRASTRUCTURE REPAIR ────────
        #
        # Wealthy kingdoms invest in infrastructure maintenance.
        # This counters the constant -0.01/tick infrastructure decay
        # and creates a "wealth → roads → trade → wealth" flywheel.
        #
        # Gate: requires treasury > 300 (some wealth to spare).
        # Rate: small per-tick investment, not instant rebuild.
        # Cap: treasury investment can maintain infra up to 60;
        #      higher infrastructure requires prosperity compounding.
        if p.infrastructure < 60.0 and p.treasury > 300.0:
            invest_willingness = min(1.0, (p.treasury - 300.0) / 1000.0)
            infra_gap = (60.0 - p.infrastructure) / 60.0  # 0→1 urgency
            infra_invest = infra_gap * invest_willingness * 0.04  # max ~0.04/tick
            invest_cost = infra_invest * 20.0

            if infra_invest > 0.001:
                p.infrastructure = cls._clamp(p.infrastructure + infra_invest)
                p.treasury = max(0.0, p.treasury - invest_cost)
                ledger.record_delta(
                    "treasury_invest", "infra_repair", "layer", state.kingdom_id,
                    "infrastructure", infra_invest, state.tick,
                    {"cost": invest_cost},
                )
                ledger.record_delta(
                    "treasury_invest", "infra_repair_cost", "layer",
                    state.kingdom_id, "treasury", -invest_cost, state.tick,
                )

    @classmethod
    def tick_belief_coupling(cls, state: KingdomState, rng: SeededRNG):
        """
        Layer D → B,C coupling.

        Spec §17: Belief as force multiplier.
        High faith → faster policy adoption, stronger cascade.
        Low faith → fragmented response, competing authority.

        Phase 9 — Multiplicative cross-layer coupling:
        Coupling strengths are no longer flat constants.  They scale
        by the current state of OTHER variables, so the same decree
        at tension=20 produces a different ripple than at tension=70.
        This is the "telephone" effect: small differences in context
        amplify small differences in input.
        """
        b = state.belief
        s = state.social
        pol = state.political
        p = state.physical
        ledger = state.causal_ledger

        faith_factor = (b.public_faith - 50.0) / 50.0  # -1 to +1

        # ── Phase 9: Faith → Cohesion (multiplicative) ─────────
        # Old: cohesion_delta = faith_factor * 0.3  (constant)
        # New: scales by inverse class_tension.  When tension is high,
        # faith has LESS power to build cohesion (people are too angry
        # to be moved by shared belief).  When tension is low, faith
        # compounds community bonds.
        #
        # tension_mod: 1.5 at tension=0, 1.0 at tension=50, 0.5 at tension=100
        tension_mod = 1.5 - (s.class_tension / 100.0)
        cohesion_delta = faith_factor * 0.3 * tension_mod
        s.cohesion = cls._clamp(s.cohesion + cohesion_delta)
        ledger.record_delta("coupling", "belief_to_social", "layer", state.kingdom_id,
                            "cohesion", cohesion_delta, state.tick,
                            {"driver": "public_faith", "faith_factor": faith_factor,
                             "tension_mod": round(tension_mod, 3)})

        # ── Phase 9: Divergence → Tension (multiplicative) ────
        # Old: tension_delta = divergence * flat_coeff
        # New: scales by (1 + fear/100).  When people are afraid,
        # competing interpretations feel MORE dangerous — divergence
        # inflames tension faster.  When fear is low, divergence is
        # merely academic disagreement.
        #
        # Also scales by resource_pressure: material stress makes
        # ideological fractures more volatile (people fight harder
        # over beliefs when they're already fighting over food).
        in_grace = (hasattr(state, "terminal_grace_until") and
                    state.tick < state.terminal_grace_until)
        div_coeff = 0.01 if in_grace else 0.02
        fear_amp = 1.0 + s.fear_level / 100.0              # 1.0 → 2.0
        rp_amp = 1.0 + p.resource_pressure / 200.0         # 1.0 → 1.5
        tension_delta = b.interpretation_divergence * div_coeff * fear_amp * rp_amp
        s.class_tension = cls._clamp(s.class_tension + tension_delta)
        ledger.record_delta("coupling", "belief_to_social", "layer", state.kingdom_id,
                            "class_tension", tension_delta, state.tick,
                            {"driver": "interpretation_divergence", "grace": in_grace,
                             "fear_amp": round(fear_amp, 3),
                             "rp_amp": round(rp_amp, 3)})

        # ── Phase 9: Faith → Legitimacy (multiplicative) ──────
        # Old: legit_delta = faith_factor * 0.2  (flat)
        # New: scales by inverse corruption.  Clean government +
        # faith = strong legitimacy.  Corrupt government + faith
        # = less benefit (people see through it).
        corruption_discount = 1.0 - (pol.corruption / 150.0)  # 1.0→0.33
        legit_delta = faith_factor * 0.2 * corruption_discount
        pol.legitimacy = cls._clamp(pol.legitimacy + legit_delta)
        ledger.record_delta("coupling", "belief_to_political", "layer", state.kingdom_id,
                            "legitimacy", legit_delta, state.tick,
                            {"driver": "public_faith",
                             "corruption_discount": round(corruption_discount, 3)})

        # Sacred silence (absence) gradually increases divergence
        if b.sacred_silence_weight > 0:
            div_delta = b.sacred_silence_weight * 0.01
            b.interpretation_divergence = cls._clamp(
                b.interpretation_divergence + div_delta
            )
            ledger.record_delta("absence", "sacred_silence", "layer", state.kingdom_id,
                                "interpretation_divergence", div_delta, state.tick)

            rumor_delta = b.sacred_silence_weight * 0.005
            b.rumor_distortion = cls._clamp(
                b.rumor_distortion + rumor_delta
            )
            ledger.record_delta("absence", "sacred_silence", "layer", state.kingdom_id,
                                "rumor_distortion", rumor_delta, state.tick)

            # Myth grows during silence (spec §13)
            myth_delta = b.sacred_silence_weight * 0.02
            b.myth_accumulation += myth_delta
            ledger.record_delta("absence", "sacred_silence", "layer", state.kingdom_id,
                                "myth_accumulation", myth_delta, state.tick)

        # ── Phase 7D: Faith Reintegration Mechanism ────────────
        # When divergence=100 and faith=0, there's no recovery path.
        # But in reality, exhaustion from schism eventually produces
        # reintegration: people tire of competing doctrines and settle
        # on a simplified consensus.
        #
        # Three structural forces:
        #
        # D1: Divergence fatigue — very high divergence creates internal
        #     pressure toward simplification.  At divergence=100 this
        #     pushes -0.3/tick, enough to slowly pull back over 200 ticks.
        if b.interpretation_divergence > 70.0:
            fatigue = (b.interpretation_divergence - 70.0) / 30.0  # 0→1
            div_reduction = fatigue * 0.3
            b.interpretation_divergence = cls._clamp(
                b.interpretation_divergence - div_reduction
            )
            ledger.record_delta("coupling", "divergence_fatigue", "layer",
                                state.kingdom_id,
                                "interpretation_divergence", -div_reduction,
                                state.tick,
                                {"mechanism": "faith_reintegration_D1"})

        # D2: Myth-driven reintegration — high myth_accumulation means
        #     the Oracle's story is deeply embedded.  Even without active
        #     faith, the shared mythology pulls divergence down.
        if b.myth_accumulation > 40.0 and b.interpretation_divergence > 40.0:
            myth_pull = (b.myth_accumulation - 40.0) / 60.0 * 0.15
            b.interpretation_divergence = cls._clamp(
                b.interpretation_divergence - myth_pull
            )
            # Myth also slowly restores faith (shared story = shared belief)
            faith_restore = myth_pull * 0.5
            b.public_faith = cls._clamp(b.public_faith + faith_restore)
            ledger.record_delta("coupling", "myth_reintegration", "layer",
                                state.kingdom_id,
                                "interpretation_divergence", -myth_pull,
                                state.tick,
                                {"mechanism": "faith_reintegration_D2",
                                 "myth_accumulation": b.myth_accumulation})
            ledger.record_delta("coupling", "myth_reintegration", "layer",
                                state.kingdom_id,
                                "public_faith", faith_restore,
                                state.tick,
                                {"mechanism": "faith_reintegration_D2"})

        # D3: Cohesion-faith feedback — when social cohesion is moderate+,
        #     shared community life naturally reinforces faith.
        #     (Currently faith→cohesion exists but not cohesion→faith.)
        if s.cohesion > 30.0 and b.public_faith < 50.0:
            cohesion_faith = (s.cohesion - 30.0) / 70.0 * 0.1
            b.public_faith = cls._clamp(b.public_faith + cohesion_faith)
            ledger.record_delta("coupling", "cohesion_to_faith", "layer",
                                state.kingdom_id,
                                "public_faith", cohesion_faith,
                                state.tick,
                                {"mechanism": "faith_reintegration_D3"})

    @classmethod
    def tick_social_political_coupling(cls, state: KingdomState, rng: SeededRNG):
        """
        Layers B,C → A coupling.

        Social unrest hurts production.
        Political enforcement can suppress unrest but at cost.
        """
        s = state.social
        pol = state.political
        p = state.physical
        ledger = state.causal_ledger

        # ── CLASS TENSION → FOOD PRODUCTION ────────────────────
        #
        # Structural change: tension applies a MULTIPLICATIVE efficiency
        # penalty that pulls production toward a reduced target, NOT a
        # flat per-tick subtraction.
        #
        # The equilibrium pull already moved production toward its
        # baseline.  Tension THEN pulls it further DOWN toward a
        # penalized level:
        #   effective_target = baseline * (1 - penalty)
        #   penalty = 0.30 * (class_tension/100)
        #
        #   At tension=0:   target = baseline (no effect)
        #   At tension=50:  target = baseline * 0.85
        #   At tension=100: target = baseline * 0.70
        #
        # This can never push production below 70% of baseline, and
        # the pull toward the target is proportional to the gap,
        # so it's gentle near the target and strong far from it.
        in_grace = (hasattr(state, "terminal_grace_until") and
                    state.tick < state.terminal_grace_until)
        tension_penalty = (s.class_tension / 100.0) * (0.15 if in_grace else 0.30)

        prod_baseline = state.equilibrium_baselines.get("food_production", 50.0)
        effective_target = prod_baseline * (1.0 - tension_penalty)

        # Only drag DOWN — if production is already below the effective
        # target, tension doesn't push it further down (the equilibrium
        # pull handles upward recovery).
        if p.food_production > effective_target:
            overshoot = p.food_production - effective_target
            pop_scale = max(0.15, min(1.0, p.labor_pool / 50.0))
            # Pull 1.5% of overshoot per tick — gentle but persistent
            tension_drag = overshoot * 0.015 * pop_scale
            p.food_production = cls._clamp(p.food_production - tension_drag)
            ledger.record_delta("coupling", "social_to_physical", "layer", state.kingdom_id,
                                "food_production", -tension_drag, state.tick,
                                {"driver": "class_tension_efficiency", "grace": in_grace,
                                 "tension_penalty": round(tension_penalty, 3),
                                 "effective_target": round(effective_target, 1)})

        # ── Phase 9: Enforcement suppresses tension (multiplicative) ─
        # Old: flat suppression above threshold=60.
        # New: uses sigmoid around 50 for enforcement effectiveness,
        # AND scales by legitimacy.  Legitimate enforcement calms
        # people; illegitimate enforcement breeds resentment faster.
        # Same enforcement level, different political context → different
        # trajectory.
        if pol.enforcement_capacity > 40:
            # Sigmoid: smooth onset around enforcement_capacity=50
            enforce_curve = cls._sigmoid(pol.enforcement_capacity, center=50.0, steepness=0.1)
            legit_mod = 0.5 + 0.5 * (pol.legitimacy / 100.0)  # 0.5 → 1.0
            suppression = enforce_curve * 0.4 * legit_mod  # max ~0.4 at enforce=100, legit=100
            s.class_tension = cls._clamp(s.class_tension - suppression)
            ledger.record_delta("coupling", "political_to_social", "layer", state.kingdom_id,
                                "class_tension", -suppression, state.tick,
                                {"driver": "enforcement_capacity",
                                 "legit_mod": round(legit_mod, 3),
                                 "enforce_curve": round(enforce_curve, 3)})

            # Resentment: fear generated by enforcement scales INVERSELY
            # with legitimacy.  Legitimate police = less fear.
            # Illegitimate police = pure terror.
            fear_mod = 1.5 - (pol.legitimacy / 100.0)  # 1.5 at legit=0, 0.5 at legit=100
            fear_add = suppression * 0.5 * fear_mod
            s.fear_level = cls._clamp(s.fear_level + fear_add)
            ledger.record_delta("coupling", "political_to_social", "layer", state.kingdom_id,
                                "fear_level", fear_add, state.tick,
                                {"driver": "enforcement_capacity",
                                 "fear_mod": round(fear_mod, 3)})

        # Corruption drains treasury
        # During grace period, drain is halved (new administration has controls)
        corruption_mult = 0.05 if in_grace else 0.1
        corruption_drain = -pol.corruption * corruption_mult
        p.treasury -= pol.corruption * corruption_mult
        ledger.record_delta("coupling", "political_to_physical", "layer", state.kingdom_id,
                            "treasury", corruption_drain, state.tick,
                            {"driver": "corruption", "grace": in_grace})

        # ── Phase 9: Physical → Social feedback (sigmoid) ──────
        #
        # Old: hard if/else at resource_pressure == 50.
        # New: sigmoid curve centered at RP=50 with steepness 0.1.
        # At RP=49 → sigmoid ≈ 0.475 (slight stress)
        # At RP=51 → sigmoid ≈ 0.525 (slightly more stress)
        # At RP=70 → sigmoid ≈ 0.88 (severe stress)
        #
        # This means a +1 decree-induced shift at RP≈50 changes
        # the tension/hope dynamics meaningfully.  The SAME +1 at
        # RP=20 or RP=80 is negligible.  Timing of when the
        # perturbation arrives relative to the system's state
        # determines its impact — the telephone effect.
        #
        # Also: hope recovery below RP<15 now uses sigmoid too, so
        # there's no discontinuous switch between "crisis" and "relief".
        rp_stress = cls._sigmoid(p.resource_pressure, center=50.0, steepness=0.1)
        # Tension saturation: diminishing returns at high tension
        tension_headroom = max(0.0, (100.0 - s.class_tension) / 60.0)
        # Cohesion dampens RP→tension (united people weather shortages)
        cohesion_shield = 1.0 - 0.3 * (s.cohesion / 100.0)  # 1.0→0.7

        tension_add = 0.16 * rp_stress * tension_headroom * cohesion_shield
        hope_change = -0.5 * rp_stress + 0.1 * (1.0 - rp_stress)  # net: stress→decay, abundance→recovery

        s.class_tension = cls._clamp(s.class_tension + tension_add)
        s.hope_level = cls._clamp(s.hope_level + hope_change)

        if abs(tension_add) > 0.001:
            ledger.record_delta("coupling", "physical_to_social", "layer", state.kingdom_id,
                                "class_tension", tension_add, state.tick,
                                {"driver": "resource_pressure_sigmoid",
                                 "rp_stress": round(rp_stress, 4),
                                 "cohesion_shield": round(cohesion_shield, 3)})
        if abs(hope_change) > 0.001:
            ledger.record_delta("coupling", "physical_to_social", "layer", state.kingdom_id,
                                "hope_level", hope_change, state.tick,
                                {"driver": "resource_pressure_sigmoid",
                                 "rp_stress": round(rp_stress, 4)})

    # ── ORGANIC RECOVERY ENGINE ────────────────────────────────
    #
    # After MAX_RESOLUTIONS are exhausted (~tick 9000), the kingdom
    # has zero recovery mechanisms.  11000 ticks with no circuit
    # breaker means guaranteed FAMINE_ERA.
    #
    # Historical reality: even after total civilizational collapse,
    # survivors rebuild.  Rome fell, but villages still farmed.
    # The Dark Ages were not permanent — they evolved into something
    # new WITHOUT needing a transformative resolution event.
    #
    # This engine provides slow, autonomous recovery that doesn't
    # require resolutions.  It's weaker than resolution resets but
    # prevents permanent death spirals.  Conditions:
    #   - Population is low (survivors are few but resilient)
    #   - Resource pressure has eased (fewer mouths)
    #   - Kingdom has been in decline long enough for rubble to clear
    #
    # Key: this does NOT trigger during active collapse or grace
    # period — only in the quiet aftermath when things have stabilized
    # at a low level.

    @classmethod
    def tick_organic_recovery(cls, state: KingdomState, rng: SeededRNG):
        """
        Slow autonomous recovery for post-collapse kingdoms.

        Represents survivors rebuilding without external intervention.
        Much weaker than resolution resets but prevents eternal death.
        Only fires when conditions suggest the crisis has PASSED
        (low population, low pressure, no active grace/resolution).
        """
        p = state.physical
        s = state.social
        pol = state.political
        b = state.belief
        ledger = state.causal_ledger

        # ── Gate conditions ────────────────────────────────────
        # Don't fire during active grace period
        in_grace = (hasattr(state, "terminal_grace_until") and
                    state.tick < state.terminal_grace_until)
        if in_grace:
            return

        # Only fire when population is low (post-collapse demographic).
        # Low population IS the signal that collapse has happened and
        # the kingdom is in the quiet aftermath.
        if p.labor_pool > 25.0:
            return  # population hasn't bottomed — not yet post-collapse

        # Must have been through at least one resolution
        # (prevents firing at game start)
        n_resolutions = len(getattr(state, "terminal_resolutions", []))
        if n_resolutions == 0:
            return

        # ── Recovery intensity scales with how settled things are ──
        # Lower population = more concentrated survivors, better
        # land-per-person ratio.  Also scales with how many
        # resolutions have been processed (more collapse = more
        # cleared rubble for rebuilding).
        pop_factor = (25.0 - p.labor_pool) / 25.0      # 0→1 as pop drops
        resolution_factor = min(n_resolutions / 3.0, 1.0)  # scales with experience
        intensity = pop_factor * (0.5 + 0.5 * resolution_factor)  # 0→1

        # ── A: Subsistence farming rebuilds ────────────────────
        # Few survivors farm the best land.  Food production drifts
        # toward subsistence (45) — not surplus, but not starvation.
        if p.food_production < 45.0:
            food_recovery = intensity * 0.08  # max ~0.08/tick
            p.food_production = cls._clamp(p.food_production + food_recovery)
            ledger.record_delta("organic_recovery", "subsistence_farming",
                                "layer", state.kingdom_id,
                                "food_production", food_recovery, state.tick)

        # ── B: Basic infrastructure maintained ─────────────────
        # Survivors repair roads, clear wells, maintain shelters.
        # Drifts toward 20 — enough for a village, not a kingdom.
        if p.infrastructure < 20.0:
            infra_recovery = intensity * 0.04  # max ~0.04/tick
            p.infrastructure = cls._clamp(p.infrastructure + infra_recovery)
            ledger.record_delta("organic_recovery", "village_maintenance",
                                "layer", state.kingdom_id,
                                "infrastructure", infra_recovery, state.tick)

        # ── C: Small community cohesion ────────────────────────
        # Survivors who stayed bond together.  Cohesion drifts up
        # when population is tiny and tension is low.
        if s.cohesion < 30.0 and s.class_tension < 40.0:
            cohesion_recovery = intensity * 0.06
            s.cohesion = cls._clamp(s.cohesion + cohesion_recovery)
            ledger.record_delta("organic_recovery", "survivor_bonds",
                                "layer", state.kingdom_id,
                                "cohesion", cohesion_recovery, state.tick)

        # ── D: Hope from stability ─────────────────────────────
        # When things stop getting worse, hope slowly returns.
        if s.hope_level < 20.0 and p.food_stores > 5.0:
            hope_recovery = intensity * 0.05
            s.hope_level = cls._clamp(s.hope_level + hope_recovery)
            ledger.record_delta("organic_recovery", "stability_hope",
                                "layer", state.kingdom_id,
                                "hope_level", hope_recovery, state.tick)

        # ── E: Population slowly recovers ──────────────────────
        # If food is adequate, people have children.  Very slow.
        # food_production>40 means slight surplus → pop growth.
        if p.food_production > 40.0 and p.labor_pool < 20.0:
            pop_recovery = intensity * 0.02  # very slow
            p.labor_pool = cls._clamp(p.labor_pool + pop_recovery)
            ledger.record_delta("organic_recovery", "demographic_recovery",
                                "layer", state.kingdom_id,
                                "labor_pool", pop_recovery, state.tick)

        # ── F: Oral tradition preserves faith ──────────────────
        # Small communities with strong bonds maintain faith through
        # oral tradition, even without formal institutions.
        if b.public_faith < 25.0 and s.cohesion > 15.0:
            faith_recovery = intensity * 0.03
            b.public_faith = cls._clamp(b.public_faith + faith_recovery)
            ledger.record_delta("organic_recovery", "oral_tradition",
                                "layer", state.kingdom_id,
                                "public_faith", faith_recovery, state.tick)

    # ── PROSPERITY COMPOUNDING ENGINE ──────────────────────────
    #
    # The sim has many decay channels: tension_drag, corruption_drain,
    # infra_decay, RP escalation, divergence→tension pump.
    #
    # But nothing compounds *upward*.  Recovery is temporary because
    # prosperity never builds structural resistance.
    #
    # This engine creates a per-tick flywheel:
    #   high infrastructure → trade bonus
    #   high trade → treasury surplus
    #   treasury surplus → institutional investment
    #   institutional strength → corruption dampening
    #   low corruption → legitimacy stability
    #   high legitimacy → cohesion buffer
    #   high cohesion → famine resistance (food production bonus)
    #
    # Each link is individually weak (0.01-0.05/tick) but the chain
    # compounds when ALL links are active simultaneously.  Breaking
    # any link breaks the flywheel.
    #
    # This is structurally identical to how the decay channels work,
    # just in the opposite direction.

    @classmethod
    def tick_prosperity_compounding(cls, state: KingdomState, rng: SeededRNG):
        """
        Per-tick prosperity flywheel.  Each coupling is individually
        weak but compounds when all links are active.

        Only fires when variables are above prosperity thresholds —
        this is NOT free growth, it's reward for sustaining good state.
        """
        p = state.physical
        s = state.social
        pol = state.political
        b = state.belief
        ledger = state.causal_ledger

        # Gate: prosperity compounding requires at least STRAINED-or-better
        # material state.  Full collapse blocks all compounding, but
        # STRAINED kingdoms get a reduced flywheel (village-scale trade,
        # basic institutional growth).
        mat = StateCoherenceEngine.classify_material(state)
        if mat == MaterialState.COLLAPSED:
            return

        # Intensity factor: THRIVING=1.0, FUNCTIONAL=0.8, STRAINED=0.4
        intensity = {
            MaterialState.THRIVING: 1.0,
            MaterialState.FUNCTIONAL: 0.8,
            MaterialState.STRAINED: 0.4,
        }.get(mat, 0.0)

        # ── Link 1: Infrastructure → Trade bonus ──────────────
        # Above 55 infrastructure, trade gets a small per-tick push.
        # This is the inverse of the (infra-50)*0.005 decay channel
        # in tick_physical — that formula goes negative below 50.
        # This adds an EXTRA bonus above 55, making high-infra states
        # self-reinforcing.
        if p.infrastructure > 55.0:
            trade_bonus = (p.infrastructure - 55.0) / 45.0 * 0.08 * intensity
            p.trade_volume = cls._clamp(p.trade_volume + trade_bonus)
            ledger.record_delta("prosperity", "infra_to_trade", "layer",
                                state.kingdom_id, "trade_volume", trade_bonus,
                                state.tick)

        # ── Link 2: Trade → Treasury surplus ──────────────────
        # High trade generates investment capital beyond the base
        # treasury formula.  This surplus enables institutional growth.
        if p.trade_volume > 50.0:
            treasury_bonus = (p.trade_volume - 50.0) / 50.0 * 2.0 * intensity
            p.treasury += treasury_bonus
            ledger.record_delta("prosperity", "trade_to_treasury", "layer",
                                state.kingdom_id, "treasury", treasury_bonus,
                                state.tick)

        # ── Link 3: Treasury → Institutional investment ───────
        # Wealthy kingdoms can afford bureaucracy, courts, archives.
        # But only if corruption isn't eating the surplus.
        if p.treasury > 500.0 and pol.corruption < 40.0:
            invest = min((p.treasury - 500.0) / 2000.0 * 0.05, 0.05) * intensity
            pol.institutional_strength = cls._clamp(
                pol.institutional_strength + invest
            )
            ledger.record_delta("prosperity", "treasury_to_institutions", "layer",
                                state.kingdom_id, "institutional_strength",
                                invest, state.tick)

        # ── Link 4: Institutional strength → Corruption dampening ─
        # Strong institutions make corruption harder to sustain.
        if pol.institutional_strength > 40.0 and pol.corruption > 10.0:
            anti_corrupt = (pol.institutional_strength - 40.0) / 60.0 * 0.04 * intensity
            pol.corruption = cls._clamp(pol.corruption - anti_corrupt)
            ledger.record_delta("prosperity", "institutions_to_corruption", "layer",
                                state.kingdom_id, "corruption", -anti_corrupt,
                                state.tick)

        # ── Link 5: Low corruption → Legitimacy stability ─────
        # Clean governance earns trust.
        if pol.corruption < 30.0:
            legit_bonus = (30.0 - pol.corruption) / 30.0 * 0.03 * intensity
            pol.legitimacy = cls._clamp(pol.legitimacy + legit_bonus)
            ledger.record_delta("prosperity", "clean_gov_to_legitimacy", "layer",
                                state.kingdom_id, "legitimacy", legit_bonus,
                                state.tick)

        # ── Link 6: Legitimacy → Cohesion buffer ─────────────
        # Legitimate authority holds society together.
        if pol.legitimacy > 50.0:
            cohesion_bonus = (pol.legitimacy - 50.0) / 50.0 * 0.04 * intensity
            s.cohesion = cls._clamp(s.cohesion + cohesion_bonus)
            ledger.record_delta("prosperity", "legitimacy_to_cohesion", "layer",
                                state.kingdom_id, "cohesion", cohesion_bonus,
                                state.tick)

        # ── Link 7: Cohesion → Famine resistance ─────────────
        # United people share food, coordinate farming, resist hoarding.
        if s.cohesion > 50.0 and p.food_production < 60.0:
            food_bonus = (s.cohesion - 50.0) / 50.0 * 0.06 * intensity
            p.food_production = cls._clamp(p.food_production + food_bonus)
            ledger.record_delta("prosperity", "cohesion_to_food", "layer",
                                state.kingdom_id, "food_production", food_bonus,
                                state.tick)

        # ── Link 8: Hope → Investment multiplier ──────────────
        # Hopeful populations invest, innovate, take risks.
        if s.hope_level > 40.0:
            hope_invest = (s.hope_level - 40.0) / 60.0 * 0.03 * intensity
            p.infrastructure = cls._clamp(p.infrastructure + hope_invest)
            ledger.record_delta("prosperity", "hope_to_infrastructure", "layer",
                                state.kingdom_id, "infrastructure", hope_invest,
                                state.tick)

        # ── Link 9: Faith coherence → Social stability ────────
        # When faith is high and divergence is low, the Oracle's
        # authority provides a stability anchor.
        if b.public_faith > 50.0 and b.interpretation_divergence < 30.0:
            stability = (b.public_faith - 50.0) / 50.0 * 0.03 * intensity
            s.class_tension = cls._clamp(s.class_tension - stability)
            ledger.record_delta("prosperity", "faith_to_stability", "layer",
                                state.kingdom_id, "class_tension", -stability,
                                state.tick)

    @classmethod
    def tick_faction_dynamics(cls, state: KingdomState, rng: SeededRNG):
        """
        Faction influence shifts based on layer conditions.

        Phase 9 — Condition-sensitive faction dynamics:
        Faction influence drift now depends on whether the current
        state of the kingdom FAVOURS that faction's archetype.
        Militarists gain influence during external threat.
        Merchants gain during trade booms.  Populists gain during
        food crises.  Religious factions gain when faith is high.
        Scholars gain when literacy is high.

        This means a small early decree that nudges external_threat
        up by +2 slightly favours the military faction, which shifts
        policy pressure, which shifts enforcement, which shifts fear…
        The telephone effect through faction dynamics.
        """
        p = state.physical
        s = state.social
        pol = state.political
        b = state.belief

        for fid, faction in state.factions.items():
            # Base inertial pull toward equal share
            pull = (20.0 - faction.influence) * 0.005

            # ── Phase 9: Condition-sensitive influence bonus ────
            # Each archetype gets a small per-tick boost when
            # conditions favour it.  Magnitude is tiny (0.01-0.05)
            # but compounds over hundreds of ticks.
            condition_boost = 0.0
            arch = getattr(faction, "archetype", None)
            if arch is not None:
                arch_name = arch.name if hasattr(arch, "name") else str(arch)
                if arch_name == "MILITARY" and pol.external_threat > 40:
                    condition_boost = (pol.external_threat - 40) / 60.0 * 0.04
                elif arch_name == "MERCHANT" and p.trade_volume > 50:
                    condition_boost = (p.trade_volume - 50) / 50.0 * 0.04
                elif arch_name == "POPULIST" and p.resource_pressure > 40:
                    condition_boost = (p.resource_pressure - 40) / 60.0 * 0.04
                elif arch_name == "RELIGIOUS" and b.public_faith > 50:
                    condition_boost = (b.public_faith - 50) / 50.0 * 0.03
                elif arch_name == "SCHOLARLY" and s.literacy > 50:
                    condition_boost = (s.literacy - 50) / 50.0 * 0.03

            faction.influence = cls._clamp(faction.influence + pull + condition_boost)

            # Oracle loyalty drifts toward public faith
            # Phase 9: rate scales by faction's interpretation_bias.
            # Factions with strong bias resist loyalty drift (stubborn
            # ideologues change slowly; moderates track faith more).
            bias_resistance = 1.0 - abs(getattr(faction, "interpretation_bias", 0.0)) / 100.0
            faith_pull = (b.public_faith - faction.oracle_loyalty) * 0.01 * max(0.3, bias_resistance)
            faction.oracle_loyalty = cls._clamp(faction.oracle_loyalty + faith_pull)

        # Re-normalise influence shares
        total = sum(f.influence for f in state.factions.values())
        if total > 0:
            for f in state.factions.values():
                f.influence = (f.influence / total) * 100.0

    @classmethod
    def tick_characters(cls, state: KingdomState, rng: SeededRNG):
        """
        Character stress, loyalty drift, and yearly aging.

        Phase 9: Character stress now uses multiplicative weighting
        so the SAME kingdom instability feels different to different
        characters based on their faction and role.  A military
        captain cares more about external threat; a scholar cares
        more about literacy decline.  This makes character death
        timing sensitive to which variables shifted — another
        propagation channel for small decree effects.
        """
        for cid, char in state.characters.items():
            if not char.alive:
                continue

            # Phase 9: Role-weighted instability (multiplicative)
            # Base instability from kingdom state
            base_tension = state.social.class_tension / 100.0
            base_corruption = state.political.corruption / 100.0
            base_faithloss = (100 - state.belief.public_faith) / 100.0
            base_rp = state.physical.resource_pressure / 100.0

            # Role-specific amplifiers (default: balanced)
            role_name = char.role.name if hasattr(char.role, "name") else ""
            if role_name in ("CAPTAIN_OF_GUARD", "GENERAL"):
                # Military: external threat and tension matter more
                ext_threat = state.political.external_threat / 100.0
                instability = (base_tension * 0.2 + base_corruption * 0.1
                               + base_faithloss * 0.1 + base_rp * 0.2 + ext_threat * 0.4)
            elif role_name in ("HIGH_PRIEST", "ORACLE_INTERPRETER"):
                # Religious: faith loss and divergence matter more
                div = state.belief.interpretation_divergence / 100.0
                instability = (base_tension * 0.1 + base_corruption * 0.1
                               + base_faithloss * 0.4 + base_rp * 0.1 + div * 0.3)
            elif role_name in ("CHANCELLOR", "STEWARD"):
                # Administrative: corruption and RP matter more
                instability = (base_tension * 0.15 + base_corruption * 0.35
                               + base_faithloss * 0.1 + base_rp * 0.4)
            else:
                # Default weighting
                instability = (base_tension * 0.3 + base_corruption * 0.2
                               + base_faithloss * 0.2 + base_rp * 0.3)

            # Faction loyalty modulates stress resilience
            faction = state.factions.get(char.faction_id)
            faction_buffer = 0.0
            if faction:
                # High faction unity provides stress buffer
                faction_buffer = (faction.internal_unity / 100.0) * 0.05 if hasattr(faction, "internal_unity") else 0.0

            char.stress = cls._clamp(char.stress + instability * 0.5 - 0.2 - faction_buffer)

            # Loyalty drift toward faction's oracle_loyalty
            if faction:
                pull = (faction.oracle_loyalty - char.oracle_loyalty) * 0.02
                char.oracle_loyalty = cls._clamp(char.oracle_loyalty + pull)

            # Grievance accumulation from high stress
            if char.stress > 60:
                char.private_grievances = cls._clamp(
                    char.private_grievances + (char.stress - 60) * 0.05
                )

    @classmethod
    def tick_interpretation_divergence(cls, state: KingdomState, rng: SeededRNG):
        """
        Phase 10: Dynamic interpretation_divergence coupling.

        interpretation_divergence grows when factions are ideologically
        spread, the Oracle doubts themselves, and rumor distortion is
        high.  It shrinks when literacy and cultural confidence are
        strong — an educated, confident population resists the
        telephone effect.

        This variable then feeds into event severity amplification
        (check_event_thresholds), creating a self-reinforcing loop:
        decree tone → faction polarisation → interpretation fog →
        worse crises → more fear → more divergent interpretation.
        """
        b = state.belief
        s = state.social

        # 1. Compute average faction ideological spread.
        # "Spread" = std dev of interpretation_bias across factions.
        # Typical range: 0 (all agree) to ~30 (highly polarised).
        biases = [f.interpretation_bias for f in state.factions.values()]
        if len(biases) >= 2:
            mean_bias = sum(biases) / len(biases)
            variance = sum((x - mean_bias) ** 2 for x in biases) / len(biases)
            ideological_spread = variance ** 0.5  # 0–30 typical
        else:
            ideological_spread = 0.0

        # 2. Oracle doubt (0–50 trait → normalise to 0–1)
        oracle_doubt = state.oracle.effective("doubt") / 50.0

        # 3. Rumor distortion (0–100 → use as-is, scaled)
        rumor = b.rumor_distortion

        # 4. Stabilisers: literacy and cultural confidence (0–100)
        literacy = s.literacy
        cultural_conf = s.cultural_confidence

        # 5. Compute delta — mild per-tick so it takes ~200 ticks
        #    to move interpretation_divergence by ~20 points.
        #
        #    Stabilisers use *excess above baseline* so that average
        #    literacy/confidence (~30/~45) gives near-zero braking.
        #    Only kingdoms that INVEST in education and culture can
        #    resist the telephone effect.  This means the Oracle's
        #    decisions about education policy actually matter.
        #
        #    Drivers at baseline (spread~10, doubt~0.5, rumor~10):
        #      10*0.02 + 0.5*0.01 + 10*0.01 = 0.305
        #    Brakes at baseline (literacy=30, cultural_conf=45):
        #      max(0, 30-25)*0.012 + max(0, 45-40)*0.010 = 0.06 + 0.05 = 0.11
        #    Net at baseline: +0.195 → slow growth from 10 → stabilises
        #    when brakes catch up (high literacy kingdoms) or drivers
        #    grow (polarised kingdoms).
        literacy_excess = max(0.0, literacy - 25.0)  # baseline ~30, so ~5 excess
        cultural_excess = max(0.0, cultural_conf - 40.0)  # baseline ~45, so ~5 excess
        delta = (
            ideological_spread * 0.02       # polarised factions → fog
            + oracle_doubt * 0.01           # self-doubt → inconsistency
            + rumor * 0.01                  # rumor mill → distortion
            - literacy_excess * 0.012       # education → clarity
            - cultural_excess * 0.010       # identity → resistance
        )

        old_val = b.interpretation_divergence
        b.interpretation_divergence = cls._clamp(old_val + delta)

        if abs(delta) > 1e-6:
            state.causal_ledger.record_delta(
                source_type="coupling",
                source_id="interp_divergence_dynamic",
                target_type="layer",
                target_id=state.kingdom_id,
                variable="interpretation_divergence",
                delta=b.interpretation_divergence - old_val,
                tick=state.tick,
                metadata={
                    "ideological_spread": round(ideological_spread, 2),
                    "oracle_doubt": round(oracle_doubt, 3),
                    "rumor": round(rumor, 1),
                    "literacy": round(literacy, 1),
                    "cultural_conf": round(cultural_conf, 1),
                },
            )

    @classmethod
    def check_yearly_boundary(cls, state: KingdomState, rng: SeededRNG,
                              days_per_year: int = 365,
                              world_state: Optional["WorldState"] = None):
        """
        If world_day crosses a year boundary, trigger aging, succession,
        baseline shift checks, era classification, and power gradient
        recalibration.
        """
        new_year = state.world_day // days_per_year + 1
        if new_year > state.world_year:
            years_passed = new_year - state.world_year
            state.world_year = new_year

            char_rng = rng.fork(f"aging_y{state.world_year}")
            for cid, char in list(state.characters.items()):
                if not char.alive:
                    continue
                for _ in range(years_passed):
                    char.age_one_year(char_rng)
                if not char.alive:
                    _dbg(f"Character died: {char.name} (age {char.age})")

            # Succession: replace dead characters
            succession_events = SuccessionEngine.process_deaths(state, char_rng)
            for sev in succession_events:
                state.active_events.push(sev)
                state.event_history.append(sev)

            # ── Phase 5: Baseline Shift check (once per year) ──
            new_shifts = BaselineShiftEngine.check_and_apply(
                state,
                state.baseline_sustained_tracker,
                state.baseline_shifts,
                current_era=state.current_era.name,
            )
            if new_shifts:
                _dbg(f"Baseline shifts crystallised: {[s.description for s in new_shifts]}")

            # ── SCAR DECAY / CULTURAL HEALING ──────────────────
            # Scars accumulate relentlessly (mean ~2700 in 20k ticks).
            # Without decay, entropy always wins.
            #
            # Three mechanisms:
            #   1. Half-life: scar effect decays over time.  Old scars
            #      lose their mechanical bite.  The memory remains but
            #      the institutional damage heals.
            #   2. Institutional memory conversion: high institutional
            #      strength converts scars into wisdom (positive shifts).
            #   3. Pruning: fully decayed scars are removed to prevent
            #      unbounded list growth.
            #
            # Half-life: ~20 years (≈ 1040 ticks at 52 ticks/year).
            # Each year, scars lose ~3.4% of their delta.
            # After 20 years, a scar retains ~50% of its original effect.
            # After 60 years, ~12%.
            SCAR_ANNUAL_DECAY = 0.034  # ≈ half-life of 20 years
            SCAR_PRUNE_THRESHOLD = 0.1  # remove scars weaker than this
            SCAR_HEALING_INST_THRESHOLD = 45.0  # need strong institutions

            scars_pruned = 0
            scars_healed = 0
            for scar in state.institutional_scars[:]:
                age_ticks = state.tick - scar.tick_formed
                age_years = age_ticks / 52.0  # approximate

                if age_years < 2.0:
                    continue  # fresh scars don't decay yet

                # 1. Time decay: reduce scar magnitude
                decay_amount = abs(scar.delta) * SCAR_ANNUAL_DECAY
                if scar.delta < 0:
                    scar.delta += decay_amount  # negative scars → toward 0
                    # Reverse the damage: apply tiny positive correction
                    BaselineShiftEngine._apply_shift(
                        state, scar.variable, decay_amount
                    )
                else:
                    scar.delta -= decay_amount  # positive scars → toward 0
                    BaselineShiftEngine._apply_shift(
                        state, scar.variable, -decay_amount
                    )

                # 2. Institutional memory: strong institutions heal faster
                if state.political.institutional_strength > SCAR_HEALING_INST_THRESHOLD:
                    inst_heal = (state.political.institutional_strength - SCAR_HEALING_INST_THRESHOLD) / 55.0
                    extra_decay = abs(scar.delta) * SCAR_ANNUAL_DECAY * inst_heal
                    if scar.delta < 0:
                        scar.delta += extra_decay
                        BaselineShiftEngine._apply_shift(
                            state, scar.variable, extra_decay
                        )
                    else:
                        scar.delta -= extra_decay
                        BaselineShiftEngine._apply_shift(
                            state, scar.variable, -extra_decay
                        )
                    scars_healed += 1

                # 3. Pruning: remove fully decayed scars
                if abs(scar.delta) < SCAR_PRUNE_THRESHOLD:
                    state.institutional_scars.remove(scar)
                    scars_pruned += 1

            if scars_pruned > 0:
                _dbg(f"Scars pruned: {scars_pruned}, healed: {scars_healed}, remaining: {len(state.institutional_scars)}")

            # ── Phase 5: Power Gradient recalibration ──
            if world_state:
                PowerGradientEngine.recalibrate(
                    world_state, world_state.neighbour_power_ranks, rng
                )

    # ────────────────────────────────────────────────────────────
    # Phase 11: Competing Attractors — Relief & Decay Feedbacks
    # ────────────────────────────────────────────────────────────
    #
    # Four structural counter-feedbacks that create branching
    # long-term trajectories.  No randomness added — only
    # deterministic condition-gated deltas.
    #
    # 1. Prosperity relief: abundance + hope → tension drops
    # 2. Corruption creep: over-enforcement + divided society → rot
    # 3. Hope reinforcement: hope + cohesion → cultural confidence
    # 4. Fear cascade: high divergence + low legitimacy → fear grows
    #
    # Together these create competing attractors: some kingdoms
    # spiral upward (1→3→1 loop), others rot internally (2),
    # others fracture under fear (4→collapse).

    @classmethod
    def tick_competing_attractors(cls, state: KingdomState, rng: SeededRNG):
        """
        Phase 11: Competing Attractors — Relief & Decay Feedbacks.

        Four structural counter-feedbacks that create branching
        long-term trajectories.  Pure condition-gated deltas,
        no randomness, no baseline changes.
        """
        p = state.physical
        s = state.social
        pol = state.political
        b = state.belief

        # ── 1. Tension relief via prosperity ──────────────────
        # A well-fed, hopeful population tolerates inequality.
        # Prosperity alone isn't enough — people need hope too.
        # This creates the "bread and circuses" stabiliser.
        if p.food_stores > 60.0 and s.hope_level > 50.0:
            relief = (p.food_stores - 60.0) * 0.01
            s.class_tension = cls._clamp(s.class_tension - relief)
            if relief > 0.01:
                state.causal_ledger.record_delta(
                    source_type="attractor", source_id="prosperity_relief",
                    target_type="layer", target_id=state.kingdom_id,
                    variable="class_tension", delta=-relief,
                    tick=state.tick,
                    metadata={"food": round(p.food_stores, 1),
                              "hope": round(s.hope_level, 1)},
                )

        # ── 2. Corruption creep under high enforcement ────────
        # A powerful state apparatus in a divided society breeds
        # quiet graft.  Officials who can't be questioned exploit
        # their position.  The more divergent interpretation is,
        # the easier it is to hide corruption behind ideology.
        if pol.enforcement_capacity > 75.0 and b.interpretation_divergence > 70.0:
            creep = (pol.enforcement_capacity - 75.0) * 0.02
            pol.corruption = cls._clamp(pol.corruption + creep)
            if creep > 0.01:
                state.causal_ledger.record_delta(
                    source_type="attractor", source_id="enforcement_corruption",
                    target_type="layer", target_id=state.kingdom_id,
                    variable="corruption", delta=creep,
                    tick=state.tick,
                    metadata={"enforcement": round(pol.enforcement_capacity, 1),
                              "interp_div": round(b.interpretation_divergence, 1)},
                )

        # ── 3. Hope reinforcement loop ────────────────────────
        # A hopeful, cohesive society builds cultural confidence.
        # This indirectly reduces interpretation_divergence (via
        # the stabiliser in tick_interpretation_divergence) and
        # fear (via existing coupling), creating a flourishing
        # attractor.  The "virtuous cycle" path.
        if s.hope_level > 55.0 and s.cohesion > 55.0:
            boost = 0.05
            s.cultural_confidence = cls._clamp(s.cultural_confidence + boost)
            state.causal_ledger.record_delta(
                source_type="attractor", source_id="hope_cohesion_culture",
                target_type="layer", target_id=state.kingdom_id,
                variable="cultural_confidence", delta=boost,
                tick=state.tick,
                metadata={"hope": round(s.hope_level, 1),
                          "cohesion": round(s.cohesion, 1)},
            )

        # ── 4. Fear cascade under divergence ──────────────────
        # When the population can't agree on what the Oracle
        # means AND the government's legitimacy is shaky, fear
        # grows.  This is the "nobody's in charge" panic.
        # Persistent, small, and unlocks collapse branches when
        # other conditions (low food, high tension) compound.
        if b.interpretation_divergence > 80.0 and pol.legitimacy < 55.0:
            fear_delta = 0.1
            s.fear_level = cls._clamp(s.fear_level + fear_delta)
            state.causal_ledger.record_delta(
                source_type="attractor", source_id="divergence_fear_cascade",
                target_type="layer", target_id=state.kingdom_id,
                variable="fear_level", delta=fear_delta,
                tick=state.tick,
                metadata={"interp_div": round(b.interpretation_divergence, 1),
                          "legitimacy": round(pol.legitimacy, 1)},
            )

    @classmethod
    def check_event_thresholds(cls, state: KingdomState, rng: SeededRNG) -> List[SimEvent]:
        """
        Scan layer variables for threshold crossings that spawn events.

        Spec §20: Events are generated when variables cross thresholds,
        relationships strain, resources destabilise, belief amplifies.

        Returns newly generated events.
        Each event also records a causal edge from the triggering
        variable to the event.

        Phase 5: Per-kind cooldowns prevent the same event type from
        firing every tick.  Without cooldowns, famines generate hundreds
        of duplicate events and scar tissue floods the system.
        """
        events: List[SimEvent] = []
        ev_rng = rng.fork(f"events_t{state.tick}")
        ledger = state.causal_ledger

        # Phase 5: Era-based event probability modifiers
        era_mods = EraClassifier.get_modifiers(state.current_era)
        prob_discovery = era_mods.get("event_prob_discovery", 1.0)
        prob_shortage = era_mods.get("event_prob_shortage", 1.0)
        prob_schism = era_mods.get("event_prob_schism", 1.0)

        # Event cooldown: check recent event history to avoid repetition
        # key → most recent tick this event kind fired
        _recent: Dict[str, int] = {}
        for ev in state.event_history[-100:]:
            _recent[ev.kind.name] = max(_recent.get(ev.kind.name, 0), ev.tick)

        def _on_cooldown(kind_name: str, cooldown_ticks: int = 30) -> bool:
            """True if this event kind fired within the last cooldown_ticks."""
            last_tick = _recent.get(kind_name, -9999)
            return (state.tick - last_tick) < cooldown_ticks

        def _record_threshold(event: SimEvent, variable: str, value: float):
            """Helper: record threshold → event causal edge and update cooldown tracker."""
            _recent[event.kind.name] = state.tick  # prevent same-kind duplicates within this tick
            ledger.record_delta(
                source_type="threshold",
                source_id=variable,
                target_type="event",
                target_id=event.event_id,
                variable=variable,
                delta=value,
                tick=state.tick,
                metadata={"severity": event.severity, "kind": event.kind.name},
            )

        # ── Phase 9: Structural-health severity multiplier ─────
        # Event severity now depends on how fragile the kingdom is,
        # not just the raw variable that triggered it.  A famine in
        # a kingdom with strong institutions is a crisis; the same
        # famine in a collapsed kingdom is existential.
        inst_strength = state.political.institutional_strength
        health_composite = getattr(state.health, "composite", 50.0)
        # fragility: 0.7 when healthy (inst=80, health=80), 1.5 when broken (inst=10, health=10)
        fragility = 1.5 - 0.8 * (min(inst_strength, health_composite) / 100.0)

        # ── Phase 9: Sigmoid-based event probability ───────────
        #
        # Old: hard threshold checks (food_stores < 10, tension > 70).
        # New: sigmoid curves centered on the threshold.  A +1 shift
        # NEAR the threshold meaningfully alters event probability.
        # Far from the threshold, the same +1 is negligible.
        #
        # prob = sigmoid((variable - center) / steepness) * base_rate
        # Then RNG roll against prob.  This makes event timing
        # stochastically sensitive to small state differences.

        # ---- Famine threshold (sigmoid) ----
        if not _on_cooldown("SHORTAGE", 60):
            # Low food_stores → higher famine probability
            famine_prob = (
                cls._sigmoid(state.physical.food_stores, center=15.0, steepness=-0.3)
                * cls._sigmoid(state.physical.resource_pressure, center=60.0, steepness=0.15)
                * prob_shortage
            )
            if ev_rng.random() < famine_prob:
                sev = min(95.0, state.physical.resource_pressure * fragility)
                ev = SimEvent(
                    event_id=f"ev_{state.tick}_famine",
                    kind=EventKind.SHORTAGE,
                    domain=EventDomain.ECONOMIC,
                    tick=state.tick,
                    severity=sev,
                    urgency=80.0,
                    description="Food stores critically low. Famine threatens the kingdom.",
                )
                events.append(ev)
                _record_threshold(ev, "food_stores", state.physical.food_stores)
                _record_threshold(ev, "resource_pressure", state.physical.resource_pressure)

        # ---- Legitimacy crisis (sigmoid) ----
        if not _on_cooldown("PETITION", 45):
            legit_crisis_prob = cls._sigmoid(state.political.legitimacy, center=30.0, steepness=-0.15)
            if ev_rng.random() < legit_crisis_prob * 0.5:
                sev = (100.0 - state.political.legitimacy) * 0.7 * fragility
                ev = SimEvent(
                    event_id=f"ev_{state.tick}_legitimacy",
                    kind=EventKind.PETITION,
                    domain=EventDomain.POLITICAL,
                    tick=state.tick,
                    severity=min(95.0, sev),
                    urgency=60.0,
                    description="Public trust in governance has eroded severely.",
                )
                events.append(ev)
                _record_threshold(ev, "legitimacy", state.political.legitimacy)

        # ---- High class tension → unrest (sigmoid) ----
        if not _on_cooldown("PETITION", 45):
            unrest_prob = cls._sigmoid(state.social.class_tension, center=65.0, steepness=0.12)
            if ev_rng.random() < unrest_prob * 0.4:
                sev = state.social.class_tension * 0.8 * fragility
                ev = SimEvent(
                    event_id=f"ev_{state.tick}_unrest",
                    kind=EventKind.PETITION,
                    domain=EventDomain.SOCIAL,
                    tick=state.tick,
                    severity=min(95.0, sev),
                    urgency=50.0,
                    description="Class tensions have reached dangerous levels.",
                )
                events.append(ev)
                _record_threshold(ev, "class_tension", state.social.class_tension)

        # ---- Schism threshold (sigmoid) ----
        if not _on_cooldown("SCHISM", 50):
            schism_prob = (
                cls._sigmoid(state.belief.interpretation_divergence, center=40.0, steepness=0.12)
                * prob_schism
            )
            if ev_rng.random() < schism_prob * 0.35:
                sev = min(95.0, state.belief.interpretation_divergence * 1.5 * fragility)
                ev = SimEvent(
                    event_id=f"ev_{state.tick}_schism",
                    kind=EventKind.SCHISM,
                    domain=EventDomain.RELIGIOUS,
                    tick=state.tick,
                    severity=sev,
                    urgency=40.0,
                    description="Competing interpretations of Oracle speech threaten unity.",
                )
                events.append(ev)
                _record_threshold(ev, "interpretation_divergence", state.belief.interpretation_divergence)

        # ---- Character grievance → accusation ----
        # Per-character cooldown: scan recent history for this character's grievance events
        _char_grievance_last: Dict[str, int] = {}
        for ev_hist in state.event_history[-200:]:
            if ev_hist.kind == EventKind.ACCUSATION and ev_hist.involved_actors:
                for actor in ev_hist.involved_actors:
                    _char_grievance_last[actor] = max(
                        _char_grievance_last.get(actor, 0), ev_hist.tick
                    )
        for cid, char in state.characters.items():
            if (char.alive and char.private_grievances > 60
                    and (state.tick - _char_grievance_last.get(cid, -9999)) >= 30
                    and ev_rng.random() < 0.08):
                ev = SimEvent(
                    event_id=f"ev_{state.tick}_grievance_{cid}",
                    kind=EventKind.ACCUSATION,
                    domain=EventDomain.POLITICAL,
                    tick=state.tick,
                    severity=char.private_grievances * 0.7,
                    urgency=35.0,
                    description=f"{char.name} harbours deep grievances against the throne.",
                    involved_actors=[cid],
                    involved_factions=[char.faction_id] if char.faction_id else [],
                )
                events.append(ev)
                _record_threshold(ev, "private_grievances", char.private_grievances)

        # ---- Discovery / Renaissance ----
        if state.social.literacy > 70 and state.belief.cultural_memory_strength > 60:
            if not _on_cooldown("DISCOVERY", 90) and ev_rng.random() < 0.05 * prob_discovery:
                ev = SimEvent(
                    event_id=f"ev_{state.tick}_renaissance",
                    kind=EventKind.DISCOVERY,
                    domain=EventDomain.SOCIAL,
                    tick=state.tick,
                    severity=30.0,
                    urgency=20.0,
                    description="A renaissance of learning sweeps the kingdom — scholars unearth forgotten texts.",
                )
                events.append(ev)
                _record_threshold(ev, "literacy", state.social.literacy)
                _record_threshold(ev, "cultural_memory_strength", state.belief.cultural_memory_strength)

        # ---- Trade disruption ----
        if (not _on_cooldown("SHORTAGE", 60)
                and state.physical.trade_volume < 20
                and state.political.external_threat > 50):
            ev = SimEvent(
                event_id=f"ev_{state.tick}_trade_disruption",
                kind=EventKind.SHORTAGE,
                domain=EventDomain.ECONOMIC,
                tick=state.tick,
                severity=55.0,
                urgency=45.0,
                description="External threats and failing trade routes strangle the kingdom's commerce.",
            )
            events.append(ev)
            _record_threshold(ev, "trade_volume", state.physical.trade_volume)
            _record_threshold(ev, "external_threat", state.political.external_threat)

        # ---- Military defiance ----
        captain = None
        for c in state.characters.values():
            if c.alive and c.role == CharacterRole.CAPTAIN_OF_GUARD:
                captain = c
                break
        if captain and captain.oracle_loyalty < 30 and captain.private_grievances > 50:
            if not _on_cooldown("ACCUSATION", 40) and ev_rng.random() < 0.2:
                ev = SimEvent(
                    event_id=f"ev_{state.tick}_military_defiance",
                    kind=EventKind.ACCUSATION,
                    domain=EventDomain.MILITARY,
                    tick=state.tick,
                    severity=75.0,
                    urgency=70.0,
                    description=f"{captain.name} openly questions the Oracle's authority before the garrison.",
                    involved_actors=[captain.character_id],
                    involved_factions=[captain.faction_id] if captain.faction_id else [],
                )
                events.append(ev)
                _record_threshold(ev, "oracle_loyalty", captain.oracle_loyalty)
                _record_threshold(ev, "private_grievances", captain.private_grievances)

        # ---- Corruption scandal (sigmoid) ----
        if not _on_cooldown("ACCUSATION", 40):
            scandal_prob = cls._sigmoid(state.political.corruption, center=60.0, steepness=0.1)
            if ev_rng.random() < scandal_prob * 0.15:
                sev = min(90.0, state.political.corruption * 0.9 * fragility)
                ev = SimEvent(
                    event_id=f"ev_{state.tick}_scandal",
                    kind=EventKind.ACCUSATION,
                    domain=EventDomain.POLITICAL,
                    tick=state.tick,
                    severity=sev,
                    urgency=50.0,
                    description="Rumours of widespread corruption reach the Oracle's ears.",
                )
                events.append(ev)
                _record_threshold(ev, "corruption", state.political.corruption)

        # ---- Natural disaster (sigmoid-scaled probability) ----
        # Old: flat 1% per tick regardless of state.
        # New: base 1% + sigmoid ramp from resource pressure and
        # infrastructure weakness.  Weak infrastructure = more
        # vulnerable to floods/drought.  Same random event, different
        # impact and timing based on structural preparation.
        disaster_vuln = (
            0.01
            + 0.03 * cls._sigmoid(state.physical.resource_pressure, center=50.0, steepness=0.08)
            + 0.02 * cls._sigmoid(state.physical.infrastructure, center=30.0, steepness=-0.1)
        )
        if ev_rng.random() < disaster_vuln:
            # Severity scales with fragility
            disaster_severity = (40.0 + state.physical.resource_pressure * 0.5) * fragility
            ev = SimEvent(
                event_id=f"ev_{state.tick}_disaster",
                kind=EventKind.NATURAL_DISASTER,
                domain=EventDomain.ECONOMIC,
                tick=state.tick,
                severity=min(95.0, disaster_severity),
                urgency=90.0,
                description="A natural disaster strikes — floods, drought, or pestilence ravage the land.",
            )
            events.append(ev)
            _record_threshold(ev, "resource_pressure", state.physical.resource_pressure)

        # ---- Cultural shift (high faction influence churn) ----
        total_influence = sum(f.influence for f in state.factions.values())
        max_influence = max((f.influence for f in state.factions.values()), default=0)
        if total_influence > 0 and max_influence / total_influence > 0.45:
            dominant = max(state.factions.values(), key=lambda f: f.influence)
            if not _on_cooldown("CULTURAL_SHIFT", 60) and ev_rng.random() < 0.08:
                ev = SimEvent(
                    event_id=f"ev_{state.tick}_cultural_shift",
                    kind=EventKind.CULTURAL_SHIFT,
                    domain=EventDomain.SOCIAL,
                    tick=state.tick,
                    severity=45.0,
                    urgency=25.0,
                    description=f"The {dominant.archetype.name.lower()} faction's dominance reshapes cultural norms.",
                    involved_factions=[dominant.faction_id],
                )
                events.append(ev)
                _record_threshold(ev, "faction_influence", dominant.influence)

        # ---- Diplomatic incident (external threat spike) ----
        if state.political.external_threat > 70:
            if not _on_cooldown("DIPLOMATIC_INCIDENT", 50) and ev_rng.random() < 0.12:
                ev = SimEvent(
                    event_id=f"ev_{state.tick}_diplomacy",
                    kind=EventKind.DIPLOMATIC_INCIDENT,
                    domain=EventDomain.POLITICAL,
                    tick=state.tick,
                    severity=65.0,
                    urgency=60.0,
                    description="A neighbouring power makes threatening demands — the kingdom must respond.",
                )
                events.append(ev)
                _record_threshold(ev, "external_threat", state.political.external_threat)

        # ── Phase 10: Interpretation fog amplifies event severity ──
        # High interpretation_divergence → the population reads crises
        # through fractured lenses → events feel worse than they are.
        # High fear → urgency spikes (panicked people overreact).
        # Multipliers capped at 1.5× to stay knife-edge, not chaotic.
        interp_div = state.belief.interpretation_divergence
        fear = state.social.fear_level
        severity_amp = min(1.5, 1.0 + interp_div / 200.0)   # 1.0→1.5
        urgency_amp = min(1.5, 1.0 + fear / 200.0)           # 1.0→1.5
        for ev in events:
            ev.severity = min(95.0, ev.severity * severity_amp)
            ev.urgency = min(95.0, ev.urgency * urgency_amp)

        return events

    @classmethod
    def update_health_index(cls, state: KingdomState):
        """Recompute kingdom health from current layer values."""
        h = state.health
        p = state.physical
        s = state.social
        pol = state.political
        b = state.belief

        h.resource_stability = cls._clamp(
            (p.food_stores / 2.0) * 0.4 + (100 - p.resource_pressure) * 0.3 + p.infrastructure * 0.3
        )
        h.social_cohesion = cls._clamp(
            s.cohesion * 0.5 + (100 - s.class_tension) * 0.3 + s.hope_level * 0.2
        )
        h.political_legitimacy = cls._clamp(
            pol.legitimacy * 0.5 + pol.institutional_strength * 0.3 + (100 - pol.corruption) * 0.2
        )
        h.cultural_confidence = cls._clamp(
            s.cultural_confidence * 0.4 + b.cultural_memory_strength * 0.3 + b.public_faith * 0.3
        )
        h.institutional_strength = cls._clamp(
            pol.institutional_strength * 0.5 + pol.enforcement_capacity * 0.3 + s.literacy * 0.2
        )
        h.external_threat_pressure = pol.external_threat
        h.snapshot()

    @classmethod
    def advance_tick(cls, state: KingdomState, rng: SeededRNG,
                     time_config: TimeConfig,
                     world_state: Optional["WorldState"] = None) -> List[SimEvent]:
        """
        Advance the kingdom by one tick.  Returns new events.

        If world_state is provided, inter-kingdom influence is applied.
        """
        tick_rng = rng.fork(f"tick_{state.tick}")

        # Phase 8: equilibrium mean-reversion (runs first so shocks override)
        cls.tick_equilibrium_pull(state, tick_rng)

        cls.tick_physical(state, tick_rng)
        cls.tick_belief_coupling(state, tick_rng)
        cls.tick_social_political_coupling(state, tick_rng)
        cls.tick_organic_recovery(state, tick_rng)
        cls.tick_prosperity_compounding(state, tick_rng)
        cls.tick_faction_dynamics(state, tick_rng)
        cls.tick_characters(state, tick_rng)
        cls.check_yearly_boundary(state, tick_rng, time_config.days_per_year,
                                  world_state=world_state)

        # ── Phase 10: Dynamic interpretation_divergence ──────
        # The "telephone effect": factions with wildly different
        # policy leanings + a doubtful Oracle + active rumor mill
        # cause the kingdom's interpretive coherence to erode.
        # Literacy and cultural confidence push back — educated
        # populations are harder to mislead.
        #
        # This variable then amplifies event severity (below),
        # creating a path-dependent feedback loop: decree tone →
        # faction polarisation → interpretation fog → worse crises
        # → more fear → more divergent interpretation.
        cls.tick_interpretation_divergence(state, tick_rng)

        # ── Phase 11: Competing Attractors ───────────────────
        # Relief & decay feedbacks that create branching paths:
        # prosperity→relief, enforcement→corruption, hope→culture,
        # divergence→fear.  No randomness — pure structural forces.
        cls.tick_competing_attractors(state, tick_rng)

        # ---- Phase 2: ripple propagation, psychology, myth memory ----
        PropagationEngine.tick_ripples(state, tick_rng)
        OraclePsychology.tick_psychology(state, tick_rng)
        MythMemory.tick_memory(state, tick_rng)

        # ---- Phase 5: Era classification and drift ----
        new_era = EraClassifier.classify(state)
        if new_era != state.current_era:
            # Close old era record
            if state.era_history:
                state.era_history[-1].ended_tick = state.tick
            # Open new era record
            era_record = EraRecord(
                era=new_era.name,
                started_tick=state.tick,
                health_at_start=state.health.composite,
                trigger_conditions=cls._snapshot_era_conditions(state),
            )
            state.era_history.append(era_record)
            # Record era transition in causal ledger
            state.causal_ledger.record_delta(
                source_type="era_transition",
                source_id=f"era_{new_era.name}",
                target_type="kingdom",
                target_id=state.kingdom_id,
                variable="era_identity",
                delta=1.0,
                tick=state.tick,
                metadata={
                    "from_era": state.current_era.name,
                    "to_era": new_era.name,
                    "health": state.health.composite,
                },
            )
            _dbg(f"Era transition: {state.current_era.name} → {new_era.name}")
            state.current_era = new_era
        # Apply era drift modifiers every tick
        EraClassifier.apply_era_drift(state, state.current_era)

        # ---- Closure System 2: inter-kingdom influence ----
        if world_state and state.is_player:
            # Recompute neighbour vectors at intervals
            if NeighbourInfluenceEngine.should_recompute(state.tick):
                state.neighbour_vectors = NeighbourInfluenceEngine.recompute_all_vectors(
                    world_state, tick_rng
                )
                # Phase 5: Apply power gradient scaling to vectors
                if world_state.neighbour_power_ranks:
                    PowerGradientEngine.modify_influence_vectors(
                        state.neighbour_vectors, world_state.neighbour_power_ranks
                    )
            # Apply every tick (vectors are cheap)
            if state.neighbour_vectors:
                NeighbourInfluenceEngine.apply_influence(
                    state, state.neighbour_vectors,
                    ledger=state.causal_ledger, tick=state.tick
                )

        # Compound event synthesis
        compound_events = CompoundEventSynthesizer.check_compounds(state, tick_rng)
        for cev in compound_events:
            state.active_events.push(cev)
            state.event_history.append(cev)

        new_events = cls.check_event_thresholds(state, tick_rng)
        for ev in new_events:
            state.active_events.push(ev)
            state.event_history.append(ev)

        # ---- Phase 5: Institutional Scar Tissue ----
        # Events above severity threshold leave permanent scars.
        # We scar at event creation (threshold crossing = crisis happening).
        for ev in new_events:
            InstitutionalScarEngine.form_scars(
                ev, state, state.institutional_scars, tick_rng
            )

        # ---- Phase 6: State Coherence ----
        # Cross-domain feasibility constraints.  Prevents impossible
        # equilibria (e.g. cohesion=100 with food=0).
        StateCoherenceEngine.enforce_coherence(state)

        # ---- Phase 7: Terminal Resolution ----
        # Track collapse duration and check for structural transformation.
        # Collapse that persists long enough produces a new structural
        # identity — not more of the same suffering.
        TerminalResolutionEngine.track_collapse(state)
        terminal_outcome = TerminalResolutionEngine.evaluate(
            state, world_state=world_state
        )
        if terminal_outcome and terminal_outcome != TerminalOutcome.NONE:
            TerminalResolutionEngine.execute(
                terminal_outcome, state, world_state=world_state
            )

        cls.update_health_index(state)

        state.world_day += time_config.days_per_tick
        state.tick += 1

        return new_events

    @classmethod
    def _snapshot_era_conditions(cls, state: KingdomState) -> Dict[str, float]:
        """Snapshot key variables for era transition records."""
        return {
            "health_composite": state.health.composite,
            "food_stores": state.physical.food_stores,
            "resource_pressure": state.physical.resource_pressure,
            "cohesion": state.social.cohesion,
            "class_tension": state.social.class_tension,
            "cultural_confidence": state.social.cultural_confidence,
            "literacy": state.social.literacy,
            "legitimacy": state.political.legitimacy,
            "enforcement_capacity": state.political.enforcement_capacity,
            "law_rigidity": state.political.law_rigidity,
            "corruption": state.political.corruption,
            "external_threat": state.political.external_threat,
            "public_faith": state.belief.public_faith,
            "interpretation_divergence": state.belief.interpretation_divergence,
        }


# ============================================================
# SECTION 14: ABSENCE & RECONSTRUCTION
# ============================================================
#
# Spec §6, §28, §62: When the Oracle returns after real-time absence,
# compute elapsed world-time and advance the simulation.
#
# This section now uses the ReconstructionStateMachine (Closure System 3)
# for ritualized phased reconstruction.

class AbsenceReconstructor:
    """
    Handles the passage of time while the Oracle was away.

    Lazy evaluation principle: for the player's kingdom we fast-forward
    tick-by-tick (deterministic).  For neighbours we only update
    aggregate drift vectors unless the player inspects them.

    Reconstruction is now PHASED via ReconstructionStateMachine:
      silence → ripples → thresholds → succession → compound → myth → present
    """

    @classmethod
    def compute_absence(cls, world_state: WorldState) -> Tuple[float, int]:
        """
        Returns (real_seconds_elapsed, world_ticks_to_simulate).
        """
        now = time.time()
        real_gap = max(0.0, now - world_state.last_session_ts)
        world_days = world_state.time_config.real_seconds_to_world_days(real_gap)
        ticks = world_state.time_config.world_days_to_ticks(world_days)
        return real_gap, ticks

    @classmethod
    def begin_reconstruction(cls, world_state: WorldState) -> Optional[ReconstructionStateMachine]:
        """
        Create a ReconstructionStateMachine for the current absence.

        Returns None if no reconstruction is needed.
        The controller calls machine.next_phase() repeatedly,
        pushing each phase result to the UI for the ritual experience.
        """
        real_gap, total_ticks = cls.compute_absence(world_state)
        if total_ticks <= 0:
            return None

        # Set sacred silence weight before reconstruction
        world_days_elapsed = world_state.time_config.real_seconds_to_world_days(real_gap)
        world_state.player_kingdom.belief.sacred_silence_weight = math.log1p(world_days_elapsed) * 2.0

        return ReconstructionStateMachine(world_state, total_ticks)

    @classmethod
    def finalize_reconstruction(cls, world_state: WorldState,
                                machine: ReconstructionStateMachine):
        """
        Called after all reconstruction phases complete.

        Updates session timestamp and reduces sacred silence.
        """
        # Update session timestamp to now
        world_state.last_session_ts = time.time()

        # After reconstruction, reduce sacred silence
        world_state.player_kingdom.belief.sacred_silence_weight *= 0.5

    @classmethod
    def reconstruct_player_kingdom(
        cls, world_state: WorldState, max_ticks_per_batch: int = 500
    ) -> List[SimEvent]:
        """
        Legacy fast-forward method (still available for non-UI contexts).

        For the full ritual experience, use begin_reconstruction() +
        next_phase() loop instead.
        """
        real_gap, total_ticks = cls.compute_absence(world_state)

        if total_ticks <= 0:
            return []

        # Cap to prevent runaway
        ticks_to_run = min(total_ticks, max_ticks_per_batch)

        rng = SeededRNG(world_state.player_kingdom.seed)
        all_events: List[SimEvent] = []

        # Increase sacred silence weight proportionally
        world_days_elapsed = world_state.time_config.real_seconds_to_world_days(real_gap)
        world_state.player_kingdom.belief.sacred_silence_weight = math.log1p(world_days_elapsed) * 2.0

        for _ in range(ticks_to_run):
            events = SimulationEngine.advance_tick(
                world_state.player_kingdom, rng, world_state.time_config,
                world_state=world_state
            )
            all_events.extend(events)

        # Update session timestamp proportionally to ticks consumed
        fraction = ticks_to_run / max(total_ticks, 1)
        world_state.last_session_ts += real_gap * fraction

        # After reconstruction, reduce sacred silence
        world_state.player_kingdom.belief.sacred_silence_weight *= 0.5

        return all_events

    @classmethod
    def remaining_ticks(cls, world_state: WorldState) -> int:
        """How many ticks are still owed from absence."""
        _, ticks = cls.compute_absence(world_state)
        return ticks


# ============================================================
# SECTION 15: CONTROLLER (Runtime Boundary)
# ============================================================
#
# Borrowed pattern from FTBController: threaded tick loop,
# command queue, state lock, save/load, widget refresh.

class OKController:
    """
    Boundary between Oracle Kingdom simulation and Radio OS runtime.

    Responsibilities:
      - Process UI commands from ok_cmd_q
      - Run tick loop when unpaused
      - Handle absence reconstruction on session start
      - Save / load via JSON + SQLite
      - Route events to web UI via ok_ui_q
    """

    def __init__(self, runtime: Dict[str, Any], mem: Dict[str, Any]):
        self.runtime = runtime
        self.mem = mem
        self.log = runtime.get("log", print)
        self.state: Optional[WorldState] = None
        self.tick_rate: float = 2.0        # seconds per tick (live play)
        self.paused: bool = True           # start paused until game is created/loaded
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.state_lock = threading.RLock()
        self.current_save_path: Optional[str] = None
        self._reconstruction_pending: int = 0
        self._reconstruction_machine: Optional[ReconstructionStateMachine] = None

    # ---- lifecycle ----

    def start(self):
        """Start the controller thread."""
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="ok_controller")
        self.thread.start()
        _dbg("Controller thread started")

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5.0)
            self.thread = None
        _dbg("Controller thread stopped")

    # ---- main loop ----

    def _run_loop(self):
        cmd_q: queue.Queue = self.runtime.get("ok_cmd_q", queue.Queue())

        while not self.stop_event.is_set():
            # Process commands
            try:
                while True:
                    cmd = cmd_q.get_nowait()
                    self._handle_command(cmd)
            except queue.Empty:
                pass

            # Tick if unpaused and state exists
            if not self.paused and self.state:
                with self.state_lock:
                    rng = SeededRNG(self.state.player_kingdom.seed)
                    events = SimulationEngine.advance_tick(
                        self.state.player_kingdom, rng, self.state.time_config,
                        world_state=self.state
                    )
                    self.state.last_session_ts = time.time()

                    if events:
                        self._push_events_to_ui(events)

                    # Autosave periodically
                    if self.state.player_kingdom.tick % 50 == 0:
                        self._autosave()

            self.stop_event.wait(timeout=self.tick_rate)

    # ---- command handling ----

    def _handle_command(self, cmd: Dict[str, Any]):
        action = cmd.get("action", "")
        self.log("ok", f"Command: {action}")

        if action == "new_game":
            self._new_game(cmd)
        elif action == "save":
            self._save(cmd.get("path"))
        elif action == "load":
            self._load(cmd.get("path"))
        elif action == "pause":
            self.paused = True
        elif action == "resume":
            self.paused = False
        elif action == "tick":
            self._manual_tick()
        elif action == "select_speech":
            self._handle_speech_selection(cmd)
        elif action == "generate_speech":
            self._handle_generate_speech(cmd)
        elif action == "inner_monologue":
            self._handle_inner_monologue()
        elif action == "get_state":
            self._push_full_state()
        elif action == "reconstruct_next_phase":
            self._handle_reconstruction_phase()
        elif action == "reconstruct_all":
            self._handle_reconstruct_all()
        elif action == "causal_trace":
            self._handle_causal_trace(cmd)
        elif action == "causal_explain":
            self._handle_causal_explain(cmd)
        elif action == "inspect_neighbour":
            self._handle_inspect_neighbour(cmd)
        elif action == "get_neighbour_vectors":
            self._handle_get_neighbour_vectors()
        elif action == "get_era":
            self._handle_get_era()
        elif action == "get_structural_memory":
            self._handle_get_structural_memory()
        elif action == "get_power_gradient":
            self._handle_get_power_gradient()
        elif action == "get_coherence":
            self._handle_get_coherence()
        elif action == "get_terminal_resolution":
            self._handle_get_terminal_resolution()
        else:
            self.log("ok", f"Unknown command: {action}")

    def _new_game(self, cmd: Dict[str, Any]):
        seed = cmd.get("seed", random.randint(0, 2**32))
        oracle_allocation = cmd.get("oracle_allocation", {})
        time_preset = cmd.get("time_preset", "week_per_year")
        num_neighbours = cmd.get("num_neighbours", 4)

        # Build oracle
        if oracle_allocation:
            oracle = OracleBuild.from_allocation(oracle_allocation)
        else:
            oracle = OracleBuild.random_build(SeededRNG(seed))

        # Time config from preset
        tc = self._time_preset_to_config(time_preset)

        with self.state_lock:
            self.state = WorldBuilder.build_world(seed, oracle, tc, num_neighbours)
            self.paused = True  # start paused so player can inspect
            self.log("ok", f"New game created: {self.state.game_id} (seed={seed})")

        self._push_full_state()

    def _time_preset_to_config(self, preset: str) -> TimeConfig:
        presets = {
            "day_per_day":    TimeConfig(world_days_per_real_second=1.0 / 86400.0),
            "week_per_year":  TimeConfig(world_days_per_real_second=365.0 / 604800.0),
            "month_per_year": TimeConfig(world_days_per_real_second=365.0 / 2592000.0),
            "year_per_year":  TimeConfig(world_days_per_real_second=365.0 / 31536000.0),
        }
        return presets.get(preset, presets["week_per_year"])

    def _manual_tick(self):
        if not self.state:
            return
        with self.state_lock:
            rng = SeededRNG(self.state.player_kingdom.seed)
            events = SimulationEngine.advance_tick(
                self.state.player_kingdom, rng, self.state.time_config,
                world_state=self.state
            )
            self.state.last_session_ts = time.time()
            if events:
                self._push_events_to_ui(events)
            self._push_full_state()

    def _handle_speech_selection(self, cmd: Dict[str, Any]):
        """
        Player selected a speech option.

        Phase 2: propagation engine — interpret the speech,
        apply policy vectors through factions, trigger cascades.
        """
        option_data = cmd.get("option", {})
        if not self.state or not option_data:
            return

        option = SpeechOption.from_dict(option_data)
        with self.state_lock:
            kingdom = self.state.player_kingdom

            # Record decree in history
            decree = DecreeRecord(
                decree_id=option.option_id,
                tick=kingdom.tick,
                text=option.text,
                tone=option.tone.name,
                mode=option.mode.name,
                policy_vector=dict(option.policy_vector),
            )
            kingdom.decree_history.append(decree)

            # ---- Phase 2: propagation cascade ----
            prop_rng = SeededRNG(kingdom.seed).fork(f"propagate_{kingdom.tick}")
            ripples = PropagationEngine.propagate(kingdom, option, prop_rng)

            # Push each ripple as a UI event for narrative display
            ripple_events: List[SimEvent] = []
            for ripple in ripples:
                rev = SimEvent(
                    event_id=f"ev_{kingdom.tick}_ripple_{ripple.source_faction}",
                    kind=EventKind.DECREE,
                    domain=EventDomain.RELIGIOUS,
                    tick=kingdom.tick,
                    severity=abs(ripple.magnitude) * 50.0,
                    urgency=30.0,
                    description=(
                        f"Faction '{ripple.source_faction}' interprets the Oracle's "
                        f"decree on '{ripple.axis}' — {ripple.interpretation}"
                    ),
                    involved_factions=[ripple.source_faction],
                )
                ripple_events.append(rev)

            for rev in ripple_events:
                kingdom.active_events.push(rev)
                kingdom.event_history.append(rev)

            if ripple_events:
                self._push_events_to_ui(ripple_events)

            self.log("ok", f"Decree propagated with {len(ripples)} ripple(s): {option.text[:60]}...")

    def _handle_generate_speech(self, cmd: Dict[str, Any]):
        """Generate speech options for the player to choose from."""
        if not self.state:
            return
        mode_str = cmd.get("mode", "decree").upper()
        mode = SpeechMode[mode_str] if mode_str in SpeechMode.__members__ else SpeechMode.DECREE
        count = cmd.get("count", 3)

        with self.state_lock:
            kingdom = self.state.player_kingdom
            gen_rng = SeededRNG(kingdom.seed).fork(f"speech_gen_{kingdom.tick}")

            if mode == SpeechMode.DECREE:
                options = SpeechGenerator.generate_decree_options(
                    kingdom, gen_rng, count=count
                )
            else:
                # AUDIENCE mode — pick a petitioner from alive characters
                petitioners = [c for c in kingdom.characters.values() if c.alive]
                if not petitioners:
                    self.log("ok", "No living characters for audience")
                    return
                petitioner = petitioners[gen_rng.randint(0, len(petitioners) - 1)]
                options = SpeechGenerator.generate_audience_options(
                    kingdom, petitioner.character_id, gen_rng, count=count
                )

            # Push options to UI
            ui_q: Optional[queue.Queue] = self.runtime.get("ok_ui_q")
            if ui_q:
                ui_q.put({
                    "type": "speech_options",
                    "mode": mode.name,
                    "options": [opt.to_dict() for opt in options],
                })
            self.log("ok", f"Generated {len(options)} {mode.name} speech options")

    def _handle_inner_monologue(self):
        """Push oracle inner-monologue data to UI."""
        if not self.state:
            return
        with self.state_lock:
            kingdom = self.state.player_kingdom
            mono = OraclePsychology.generate_inner_monologue_data(kingdom)
            ui_q: Optional[queue.Queue] = self.runtime.get("ok_ui_q")
            if ui_q:
                ui_q.put({
                    "type": "inner_monologue",
                    "data": mono,
                })

    # ---- Closure System 1: Causal Ledger commands ----

    def _handle_causal_trace(self, cmd: Dict[str, Any]):
        """
        Trace causal history of a variable.

        cmd keys: variable (str), tick_start (optional int), tick_end (optional int)
        """
        if not self.state:
            return
        variable = cmd.get("variable", "")
        if not variable:
            return
        with self.state_lock:
            ledger = self.state.player_kingdom.causal_ledger
            history = ledger.variable_history(
                variable,
                last_n=cmd.get("last_n", 50)
            )
            ui_q: Optional[queue.Queue] = self.runtime.get("ok_ui_q")
            if ui_q:
                ui_q.put({
                    "type": "causal_trace",
                    "variable": variable,
                    "history": history,
                    "total_edges": len(ledger),
                })
            self.log("ok", f"Causal trace: {variable} → {len(history)} edges")

    def _handle_causal_explain(self, cmd: Dict[str, Any]):
        """
        Produce a human-readable explanation of why a variable
        has its current value.

        cmd keys: variable (str), tick (optional int)
        """
        if not self.state:
            return
        variable = cmd.get("variable", "")
        if not variable:
            return
        with self.state_lock:
            ledger = self.state.player_kingdom.causal_ledger
            explanation = ledger.explain(variable, tick=cmd.get("tick"))
            ui_q: Optional[queue.Queue] = self.runtime.get("ok_ui_q")
            if ui_q:
                ui_q.put({
                    "type": "causal_explanation",
                    "variable": variable,
                    "explanation": explanation,
                })

    # ---- Closure System 2: Neighbour Influence commands ----

    def _handle_inspect_neighbour(self, cmd: Dict[str, Any]):
        """
        Materialise a neighbour kingdom for inspection.

        cmd keys: kingdom_id (str)
        This is the ONLY time a neighbour is fully computed.
        """
        if not self.state:
            return
        kingdom_id = cmd.get("kingdom_id", "")
        if kingdom_id not in self.state.neighbour_seeds:
            self.log("ok", f"Unknown neighbour: {kingdom_id}")
            return

        with self.state_lock:
            seed = self.state.neighbour_seeds[kingdom_id]
            checkpoint = self.state.neighbour_checkpoints.get(kingdom_id)
            neighbour = WorldBuilder.materialise_neighbour(kingdom_id, seed, checkpoint)

            # Store checkpoint for next time
            self.state.neighbour_checkpoints[kingdom_id] = neighbour.to_dict()

            ui_q: Optional[queue.Queue] = self.runtime.get("ok_ui_q")
            if ui_q:
                ui_q.put({
                    "type": "neighbour_state",
                    "kingdom_id": kingdom_id,
                    "data": neighbour.to_dict(),
                })
            self.log("ok", f"Materialised neighbour: {kingdom_id} ({neighbour.name})")

    def _handle_get_neighbour_vectors(self):
        """Push current neighbour influence vectors to UI."""
        if not self.state:
            return
        with self.state_lock:
            vectors = self.state.player_kingdom.neighbour_vectors
            ui_q: Optional[queue.Queue] = self.runtime.get("ok_ui_q")
            if ui_q:
                ui_q.put({
                    "type": "neighbour_vectors",
                    "vectors": [v.to_dict() for v in vectors],
                })

    # ---- Phase 5: Structural Memory commands ----

    def _handle_get_era(self):
        """Push current era identity and history to UI."""
        if not self.state:
            return
        with self.state_lock:
            kingdom = self.state.player_kingdom
            era_mods = EraClassifier.get_modifiers(kingdom.current_era)
            ui_q: Optional[queue.Queue] = self.runtime.get("ok_ui_q")
            if ui_q:
                ui_q.put({
                    "type": "era_identity",
                    "current_era": kingdom.current_era.name,
                    "modifiers": era_mods,
                    "era_history": [e.to_dict() for e in kingdom.era_history],
                    "total_baseline_shifts": len(kingdom.baseline_shifts),
                    "total_scars": len(kingdom.institutional_scars),
                })

    def _handle_get_structural_memory(self):
        """Push full structural memory (shifts + scars + era history) to UI."""
        if not self.state:
            return
        with self.state_lock:
            kingdom = self.state.player_kingdom
            ui_q: Optional[queue.Queue] = self.runtime.get("ok_ui_q")
            if ui_q:
                ui_q.put({
                    "type": "structural_memory",
                    "baseline_shifts": [s.to_dict() for s in kingdom.baseline_shifts],
                    "institutional_scars": [s.to_dict() for s in kingdom.institutional_scars],
                    "era_history": [e.to_dict() for e in kingdom.era_history],
                    "current_era": kingdom.current_era.name,
                    "sustained_tracker": dict(kingdom.baseline_sustained_tracker),
                })

    def _handle_get_power_gradient(self):
        """Push neighbour power rankings to UI."""
        if not self.state:
            return
        with self.state_lock:
            ranks = self.state.neighbour_power_ranks
            ui_q: Optional[queue.Queue] = self.runtime.get("ok_ui_q")
            if ui_q:
                ui_q.put({
                    "type": "power_gradient",
                    "ranks": {k: v.to_dict() for k, v in ranks.items()},
                    "anchors": [k for k, v in ranks.items() if v.is_regional_anchor],
                })

    def _handle_get_coherence(self):
        """Push state coherence diagnostic to UI."""
        if not self.state:
            return
        with self.state_lock:
            ks = self.state.player_kingdom
            mat = StateCoherenceEngine.classify_material(ks)
            p = ks.physical
            s = ks.social
            pol = ks.political
            b = ks.belief

            # Compute justification score (same logic as engine)
            justification = (
                min(pol.enforcement_capacity, 80.0) / 80.0 * 0.35
                + min(b.public_faith, 90.0) / 90.0 * 0.35
                + min(pol.external_threat, 80.0) / 80.0 * 0.30
            )

            ui_q: Optional[queue.Queue] = self.runtime.get("ok_ui_q")
            if ui_q:
                ui_q.put({
                    "type": "coherence",
                    "material_state": mat.name,
                    "justification_score": round(justification, 3),
                    "tensions": {
                        "corruption_vs_legitimacy": round(pol.corruption - pol.legitimacy, 1),
                        "material_vs_cohesion": round(
                            s.cohesion - (p.food_stores + p.infrastructure) / 2.0, 1),
                        "faith_vs_reality": round(
                            b.public_faith - (p.food_stores + s.hope_level) / 2.0, 1),
                        "enforcement_vs_resources": round(
                            pol.enforcement_capacity - p.labor_pool, 1),
                    },
                    "health_composite": round(ks.health.composite, 1),
                })

    def _handle_get_terminal_resolution(self):
        """Push terminal resolution state and history to UI."""
        if not self.state:
            return
        with self.state_lock:
            ks = self.state.player_kingdom
            mat = StateCoherenceEngine.classify_material(ks)

            ui_q: Optional[queue.Queue] = self.runtime.get("ok_ui_q")
            if ui_q:
                ui_q.put({
                    "type": "terminal_resolution",
                    "collapse_duration": ks.collapse_duration,
                    "collapse_threshold": TERMINAL_COLLAPSE_HEALTH_THRESHOLD,
                    "duration_min": TERMINAL_COLLAPSE_DURATION_MIN,
                    "material_state": mat.name,
                    "health_composite": round(ks.health.composite, 1),
                    "total_resolutions": len(ks.terminal_resolutions),
                    "resolutions": [r.to_dict() for r in ks.terminal_resolutions],
                    "is_in_collapse": ks.health.composite < TERMINAL_COLLAPSE_HEALTH_THRESHOLD,
                    "ticks_until_eligible": max(
                        0, TERMINAL_COLLAPSE_DURATION_MIN - ks.collapse_duration
                    ),
                })

    # ---- Closure System 3: Ritualized Reconstruction commands ----

    def _handle_reconstruction_phase(self):
        """
        Process the next reconstruction phase and push results to UI.

        The frontend calls this repeatedly, receiving one phase at a time.
        This creates the "five years passed" ritual experience.
        """
        if not self._reconstruction_machine:
            self.log("ok", "No reconstruction in progress")
            return

        with self.state_lock:
            result = self._reconstruction_machine.next_phase()
            ui_q: Optional[queue.Queue] = self.runtime.get("ok_ui_q")

            if result:
                if ui_q:
                    ui_q.put({
                        "type": "reconstruction_phase",
                        "phase": result.to_dict(),
                        "progress": self._reconstruction_machine.progress,
                        "complete": self._reconstruction_machine.complete,
                    })
                self.log("ok", f"Reconstruction phase: {result.phase_name} "
                         f"({result.ticks_processed} ticks, {result.new_events_count} events)")

            if self._reconstruction_machine.complete:
                # Finalize
                AbsenceReconstructor.finalize_reconstruction(
                    self.state, self._reconstruction_machine
                )
                summary = self._reconstruction_machine.summary()
                if ui_q:
                    ui_q.put({
                        "type": "reconstruction_complete",
                        "summary": summary,
                    })
                self.log("ok", f"Reconstruction complete: {summary.get('total_years', 0)} years, "
                         f"{summary.get('total_events', 0)} events")
                self._reconstruction_machine = None
                self._reconstruction_pending = 0
                self._push_full_state()

    def _handle_reconstruct_all(self):
        """
        Run all reconstruction phases at once (for non-interactive contexts).
        Still produces per-phase results pushed to UI.
        """
        if not self._reconstruction_machine:
            self.log("ok", "No reconstruction in progress")
            return

        with self.state_lock:
            results = self._reconstruction_machine.run_all_phases()
            ui_q: Optional[queue.Queue] = self.runtime.get("ok_ui_q")

            for result in results:
                if ui_q:
                    ui_q.put({
                        "type": "reconstruction_phase",
                        "phase": result.to_dict(),
                        "progress": self._reconstruction_machine.progress,
                        "complete": self._reconstruction_machine.complete,
                    })

            # Finalize
            AbsenceReconstructor.finalize_reconstruction(
                self.state, self._reconstruction_machine
            )
            summary = self._reconstruction_machine.summary()
            if ui_q:
                ui_q.put({
                    "type": "reconstruction_complete",
                    "summary": summary,
                })

            self.log("ok", f"Full reconstruction: {summary.get('total_years', 0)} years, "
                     f"{summary.get('total_events', 0)} events")
            self._reconstruction_machine = None
            self._reconstruction_pending = 0
            self._push_full_state()

    # ---- save / load ----

    def _get_autosave_path(self) -> str:
        station_dir = self.runtime.get("STATION_DIR", ".")
        return os.path.join(station_dir, "ok_autosave.json")

    def _autosave(self):
        self._save(self._get_autosave_path())

    def _save(self, path: Optional[str] = None):
        if not self.state:
            return
        path = path or self._get_autosave_path()
        try:
            with self.state_lock:
                data = self.state.to_dict()
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            self.current_save_path = path
            self.log("ok", f"Saved to {path}")
        except Exception as e:
            self.log("ok", f"Save failed: {e}")

    def _load(self, path: Optional[str] = None):
        path = path or self._get_autosave_path()
        if not os.path.exists(path):
            self.log("ok", f"No save file at {path}")
            return
        try:
            with open(path, "r") as f:
                data = json.load(f)
            with self.state_lock:
                self.state = WorldState.from_dict(data)
                self.paused = True
            self.current_save_path = path
            self.log("ok", f"Loaded from {path}")

            # Check for absence reconstruction
            remaining = AbsenceReconstructor.remaining_ticks(self.state)
            if remaining > 0:
                self._reconstruction_pending = remaining
                self._reconstruction_machine = AbsenceReconstructor.begin_reconstruction(self.state)
                self.log("ok", f"Absence detected: {remaining} ticks to reconstruct")

                # Push reconstruction start to UI
                ui_q: Optional[queue.Queue] = self.runtime.get("ok_ui_q")
                if ui_q and self._reconstruction_machine:
                    ui_q.put({
                        "type": "reconstruction_start",
                        "total_ticks": remaining,
                        "phases": [p["name"] for p in RECONSTRUCTION_PHASES],
                        "phase_descriptions": [p["description"] for p in RECONSTRUCTION_PHASES],
                    })

            self._push_full_state()
        except Exception as e:
            self.log("ok", f"Load failed: {e}")

    # ---- UI push ----

    def _push_events_to_ui(self, events: List[SimEvent]):
        ui_q: Optional[queue.Queue] = self.runtime.get("ok_ui_q")
        if ui_q:
            for ev in events:
                ui_q.put({"type": "event", "data": ev.to_dict()})

    def _push_full_state(self):
        if not self.state:
            return
        ui_q: Optional[queue.Queue] = self.runtime.get("ok_ui_q")
        if ui_q:
            with self.state_lock:
                ui_q.put({
                    "type": "state_update",
                    "data": self.state.to_dict(),
                })

    # ---- public API for web server ----

    def get_state_snapshot(self) -> Optional[dict]:
        if not self.state:
            return None
        with self.state_lock:
            return self.state.to_dict()

    def get_pending_events(self) -> List[dict]:
        if not self.state:
            return []
        with self.state_lock:
            return [e.to_dict() for e in self.state.player_kingdom.active_events.pending()]


# ============================================================
# SECTION 16: WEB SERVER (Stub — Phase 3)
# ============================================================
#
# Oracle Kingdom will have its own FastAPI web server, similar to
# ftb_web_server.py.  For now, just a placeholder that starts
# and serves a health endpoint.

def _start_web_server(stop_event: threading.Event, runtime: Dict[str, Any]):
    """
    Start the Oracle Kingdom web server.

    Closure system endpoints:
      - GET  /ok/timeline/{variable}  → causal trace for a variable
      - GET  /ok/explain/{variable}   → human-readable causal explanation
      - GET  /ok/neighbours           → current neighbour influence vectors
      - GET  /ok/neighbour/{id}       → materialise and inspect a neighbour
      - POST /ok/reconstruct/next     → advance one reconstruction phase
      - POST /ok/reconstruct/all      → run all reconstruction phases
      - GET  /ok/reconstruct/status   → reconstruction progress
    """
    try:
        import fastapi
        import uvicorn

        app = fastapi.FastAPI(title="Oracle Kingdom", version="0.2.0")
        controller: Optional[OKController] = runtime.get("ok_controller")

        @app.get("/ok/health")
        def health():
            return {"status": "ok", "game_id": controller.state.game_id if controller and controller.state else None}

        @app.get("/ok/state")
        def get_state():
            if not controller:
                return {"error": "no controller"}
            snap = controller.get_state_snapshot()
            return snap or {"error": "no game loaded"}

        @app.get("/ok/events")
        def get_events():
            if not controller:
                return []
            return controller.get_pending_events()

        @app.post("/ok/command")
        def post_command(cmd: dict):
            cmd_q: Optional[queue.Queue] = runtime.get("ok_cmd_q")
            if cmd_q:
                cmd_q.put(cmd)
                return {"status": "queued"}
            return {"error": "no command queue"}

        # ---- Closure System 1: Causal Ledger endpoints ----

        @app.get("/ok/timeline/{variable}")
        def get_timeline(variable: str, last_n: int = 50):
            """Causal trace for a specific variable."""
            if not controller or not controller.state:
                return {"error": "no game loaded"}
            with controller.state_lock:
                ledger = controller.state.player_kingdom.causal_ledger
                return {
                    "variable": variable,
                    "history": ledger.variable_history(variable, last_n=last_n),
                    "total_edges": len(ledger),
                }

        @app.get("/ok/explain/{variable}")
        def get_explanation(variable: str):
            """Human-readable causal explanation for a variable."""
            if not controller or not controller.state:
                return {"error": "no game loaded"}
            with controller.state_lock:
                ledger = controller.state.player_kingdom.causal_ledger
                return {
                    "variable": variable,
                    "explanation": ledger.explain(variable),
                }

        @app.get("/ok/causal/chain/{source_id}")
        def get_causal_chain(source_id: str, max_depth: int = 10):
            """Walk the causal chain from a source event/decree."""
            if not controller or not controller.state:
                return {"error": "no game loaded"}
            with controller.state_lock:
                ledger = controller.state.player_kingdom.causal_ledger
                chain = ledger.causal_chain(source_id, max_depth=max_depth)
                return {
                    "source_id": source_id,
                    "chain": [e.to_dict() for e in chain],
                }

        # ---- Closure System 2: Neighbour Influence endpoints ----

        @app.get("/ok/neighbours")
        def get_neighbours():
            """Current neighbour influence vectors."""
            if not controller or not controller.state:
                return {"error": "no game loaded"}
            with controller.state_lock:
                vectors = controller.state.player_kingdom.neighbour_vectors
                return {
                    "vectors": [v.to_dict() for v in vectors],
                    "neighbour_ids": list(controller.state.neighbour_seeds.keys()),
                }

        @app.get("/ok/neighbour/{kingdom_id}")
        def get_neighbour(kingdom_id: str):
            """Materialise and inspect a neighbour kingdom."""
            if not controller or not controller.state:
                return {"error": "no game loaded"}
            if kingdom_id not in controller.state.neighbour_seeds:
                return {"error": f"unknown neighbour: {kingdom_id}"}
            with controller.state_lock:
                seed = controller.state.neighbour_seeds[kingdom_id]
                checkpoint = controller.state.neighbour_checkpoints.get(kingdom_id)
                neighbour = WorldBuilder.materialise_neighbour(kingdom_id, seed, checkpoint)
                controller.state.neighbour_checkpoints[kingdom_id] = neighbour.to_dict()
                return neighbour.to_dict()

        # ---- Closure System 3: Reconstruction endpoints ----

        @app.get("/ok/reconstruct/status")
        def get_reconstruction_status():
            """Current reconstruction progress."""
            if not controller:
                return {"error": "no controller"}
            machine = controller._reconstruction_machine
            if not machine:
                return {"status": "idle", "pending": False}
            return {
                "status": "in_progress",
                "pending": True,
                "progress": machine.progress,
                "phase_index": machine.phase_index,
                "total_phases": len(RECONSTRUCTION_PHASES),
                "ticks_consumed": machine.ticks_consumed,
                "total_ticks": machine.total_ticks,
                "complete": machine.complete,
                "phases_completed": [r.to_dict() for r in machine.phase_results],
            }

        @app.post("/ok/reconstruct/next")
        def reconstruct_next():
            """Advance one reconstruction phase."""
            cmd_q: Optional[queue.Queue] = runtime.get("ok_cmd_q")
            if cmd_q:
                cmd_q.put({"action": "reconstruct_next_phase"})
                return {"status": "queued"}
            return {"error": "no command queue"}

        @app.post("/ok/reconstruct/all")
        def reconstruct_all():
            """Run all remaining reconstruction phases."""
            cmd_q: Optional[queue.Queue] = runtime.get("ok_cmd_q")
            if cmd_q:
                cmd_q.put({"action": "reconstruct_all"})
                return {"status": "queued"}
            return {"error": "no command queue"}

        # ---- Phase 5: Structural Memory endpoints ----

        @app.get("/ok/era")
        def get_era():
            """Current era identity with mechanical modifiers."""
            if not controller or not controller.state:
                return {"error": "no game loaded"}
            with controller.state_lock:
                kingdom = controller.state.player_kingdom
                return {
                    "current_era": kingdom.current_era.name,
                    "modifiers": EraClassifier.get_modifiers(kingdom.current_era),
                    "era_history": [e.to_dict() for e in kingdom.era_history],
                }

        @app.get("/ok/structural_memory")
        def get_structural_memory():
            """Full structural memory: baseline shifts, scars, eras."""
            if not controller or not controller.state:
                return {"error": "no game loaded"}
            with controller.state_lock:
                kingdom = controller.state.player_kingdom
                return {
                    "baseline_shifts": [s.to_dict() for s in kingdom.baseline_shifts],
                    "institutional_scars": [s.to_dict() for s in kingdom.institutional_scars],
                    "era_history": [e.to_dict() for e in kingdom.era_history],
                    "current_era": kingdom.current_era.name,
                    "net_baselines": {
                        var: BaselineShiftEngine.net_baseline_modifier(kingdom.baseline_shifts, var)
                        for var in set(s.target_variable for s in kingdom.baseline_shifts)
                    } if kingdom.baseline_shifts else {},
                }

        @app.get("/ok/power_gradient")
        def get_power_gradient():
            """Neighbour power rankings and regional anchors."""
            if not controller or not controller.state:
                return {"error": "no game loaded"}
            with controller.state_lock:
                ranks = controller.state.neighbour_power_ranks
                return {
                    "ranks": {k: v.to_dict() for k, v in ranks.items()},
                    "anchors": [k for k, v in ranks.items() if v.is_regional_anchor],
                }

        @app.get("/ok/coherence")
        def get_coherence():
            """State coherence diagnostic: material classification, tensions."""
            if not controller or not controller.state:
                return {"error": "no game loaded"}
            with controller.state_lock:
                ks = controller.state.player_kingdom
                mat = StateCoherenceEngine.classify_material(ks)
                p = ks.physical
                s = ks.social
                pol = ks.political
                b = ks.belief
                justification = (
                    min(pol.enforcement_capacity, 80.0) / 80.0 * 0.35
                    + min(b.public_faith, 90.0) / 90.0 * 0.35
                    + min(pol.external_threat, 80.0) / 80.0 * 0.30
                )
                return {
                    "material_state": mat.name,
                    "justification_score": round(justification, 3),
                    "tensions": {
                        "corruption_vs_legitimacy": round(
                            pol.corruption - pol.legitimacy, 1),
                        "material_vs_cohesion": round(
                            s.cohesion - (p.food_stores + p.infrastructure) / 2.0, 1),
                        "faith_vs_reality": round(
                            b.public_faith - (p.food_stores + s.hope_level) / 2.0, 1),
                        "enforcement_vs_resources": round(
                            pol.enforcement_capacity - p.labor_pool, 1),
                    },
                    "health_composite": round(ks.health.composite, 1),
                }

        @app.get("/ok/terminal_resolution")
        def get_terminal_resolution():
            """Terminal resolution state: collapse tracking and transformation history."""
            if not controller or not controller.state:
                return {"error": "no game loaded"}
            with controller.state_lock:
                ks = controller.state.player_kingdom
                mat = StateCoherenceEngine.classify_material(ks)
                return {
                    "collapse_duration": ks.collapse_duration,
                    "collapse_threshold": TERMINAL_COLLAPSE_HEALTH_THRESHOLD,
                    "duration_min": TERMINAL_COLLAPSE_DURATION_MIN,
                    "material_state": mat.name,
                    "health_composite": round(ks.health.composite, 1),
                    "total_resolutions": len(ks.terminal_resolutions),
                    "resolutions": [r.to_dict() for r in ks.terminal_resolutions],
                    "is_in_collapse": ks.health.composite < TERMINAL_COLLAPSE_HEALTH_THRESHOLD,
                    "ticks_until_eligible": max(
                        0, TERMINAL_COLLAPSE_DURATION_MIN - ks.collapse_duration
                    ),
                }

        # Run on a different port than FTB
        config = uvicorn.Config(app, host="0.0.0.0", port=7600, log_level="warning")
        server = uvicorn.Server(config)

        # Run until stop_event is set
        loop = None
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(server.serve())
        finally:
            if loop:
                loop.close()

    except ImportError:
        _dbg("FastAPI/uvicorn not available — web server disabled")
    except Exception as e:
        _dbg(f"Web server error: {e}")


# ============================================================
# SECTION 17: WIDGET REGISTRATION (Radio OS Plugin Contract)
# ============================================================

def register_widgets(registry, runtime_stub):
    """Register Oracle Kingdom with the Radio OS runtime."""

    # ---- command & UI queues ----
    if "ok_cmd_q" not in runtime_stub:
        runtime_stub["ok_cmd_q"] = queue.Queue()
        _dbg("Created ok_cmd_q")

    if "ok_ui_q" not in runtime_stub:
        runtime_stub["ok_ui_q"] = queue.Queue()
        _dbg("Created ok_ui_q")

    # ---- controller ----
    if "ok_controller" not in runtime_stub:
        controller = OKController(runtime_stub, {})
        runtime_stub["ok_controller"] = controller
        controller.start()
        _dbg("Controller started")

    # ---- web server ----
    if "ok_web_started" not in runtime_stub:
        stop_event = runtime_stub.get("stop_event", threading.Event())
        web_thread = threading.Thread(
            target=_start_web_server,
            args=(stop_event, runtime_stub),
            daemon=True,
            name="ok_web_server",
        )
        web_thread.start()
        runtime_stub["ok_web_started"] = True
        _dbg("Web server started on port 7600")

    # ---- placeholder desktop widget (Phase 3+) ----
    def ok_widget_factory(parent_frame):
        """
        Placeholder — will be replaced with a real customtkinter widget later.
        For now the game is web-first.
        """
        try:
            import customtkinter as ctk
            frame = ctk.CTkFrame(parent_frame)
            label = ctk.CTkLabel(
                frame,
                text="Oracle Kingdom\n\nOpen browser → http://localhost:7600",
                font=("Helvetica", 14),
            )
            label.pack(expand=True, padx=20, pady=20)
            return frame
        except ImportError:
            return None

    registry.register("oracle_kingdom", ok_widget_factory)
    _dbg("Widget registered: oracle_kingdom")
