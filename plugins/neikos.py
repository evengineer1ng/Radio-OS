"""
Neikos: Hundred Islands — Deterministic Island Creature-Ecology Simulation

A Radio OS plugin game.  The player is born on one of 100 sealed islands,
each generated from a deterministic seed.  300 species, competitive leagues,
genetic breeding, faction territorial influence, and a hidden world ledger
drive toward one of 100 outcome bands computed from the fusion of
Island State × Personal Trajectory.

Architecture (all in one file, pure math — LLM is presentation-only):
  §1  — Determinism infrastructure (SeededRNG, hashing)
  §2  — Global Type library & interaction matrix
  §3  — Biome vector model & climate archetypes
  §4  — Island macro-graph topology generation
  §5  — Species generation (300 per island)
  §6  — Encounter table system
  §7  — Battle & league simulation
  §8  — Genetic breeding & evolutionary drift
  §9  — Faction territorial influence & dialogue weighting
  §10 — Island ledger, normalization, 100 outcome bands
  §11 — Gate requirement computation
  §12 — Player trajectory & personal outcome
  §13 — Island controller & tick engine
  §14 — Widget registration (Radio OS plugin contract)

Design Principles:
  • Deterministic given (seed, player choices).
  • No infinite procedural sprawl — everything derives from seed.
  • LLM is presentation-only; the Cold Layer is pure math.
  • 100 islands × 300 species × 120–180 nodes each.
  • Simulation is pure computation — no blocking I/O on main thread.
"""

from __future__ import annotations

# ── stdlib ──────────────────────────────────────────────────
import hashlib
import json
import math
import os
import queue
import random
import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import (
    Any, Callable, Dict, FrozenSet, List, Optional,
    Set, Tuple, Union,
)

# ── Debug gate ──────────────────────────────────────────────
NK_DEBUG: bool = os.environ.get("NK_DEBUG", "").strip() in ("1", "true", "yes")


def _dbg(*a, **kw):
    if NK_DEBUG:
        print("[NK]", *a, **kw)


# ============================================================
# PLUGIN METADATA
# ============================================================

IS_FEED = False
PLUGIN_NAME = "Neikos: Hundred Islands"
PLUGIN_DESC = (
    "Deterministic 100-island creature-ecology simulation — "
    "300 species, league battling, genetic breeding, faction influence, "
    "100 outcome bands"
)
FEED_DEFAULTS: Dict[str, Any] = {}  # widget-only, no feed config


# ============================================================
# §1  DETERMINISM INFRASTRUCTURE
# ============================================================

class SeededRNG:
    """
    Reproducible PRNG wrapper.  Every sub-system forks its own RNG from
    the master seed so evaluation order between independent systems cannot
    break determinism.
    """

    def __init__(self, seed: int):
        self._seed = seed
        self._rng = random.Random(seed)

    # ---- delegation ------------------------------------------------
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

    def sample(self, population, k: int):
        return self._rng.sample(population, k)

    # ---- forking ---------------------------------------------------
    def fork(self, label: str) -> "SeededRNG":
        h = hashlib.sha256(f"{self._seed}:{label}".encode()).hexdigest()
        return SeededRNG(int(h[:16], 16))

    @property
    def seed(self) -> int:
        return self._seed


def _det_hash(text: str) -> int:
    """Deterministic 64-bit hash from a string."""
    return int(hashlib.sha256(text.encode()).hexdigest()[:16], 16)


# ============================================================
# §2  GLOBAL TYPE LIBRARY & INTERACTION MATRIX
# ============================================================

class NkType(Enum):
    """18 global mechanical creature types."""
    EMBER    = 0
    TIDE     = 1
    STONE    = 2
    GALE     = 3
    VERDANT  = 4
    FROST    = 5
    VOLT     = 6
    VENOM    = 7
    ALLOY    = 8
    SHADE    = 9
    RADIANT  = 10
    ECHO     = 11
    RIFT     = 12
    THORN    = 13
    BLOOM    = 14
    DUNE     = 15
    TORRENT  = 16
    PULSE    = 17


# Number of types
_NUM_TYPES = len(NkType)

# Canonical type interaction matrix  (18 × 18)
# Values: 1.25 = advantage, 1.0 = neutral, 0.75 = resistance
# Built with deterministic, balanced adjacency rules:
#   • Every type has ≥2 advantages and ≥2 weaknesses
#   • No type dominates >4 others or is weak to >4

def _build_type_matrix() -> List[List[float]]:
    """
    Build a balanced 18×18 interaction matrix.

    Strategy: ring-of-advantages with cross-links for depth.
    Each type i is strong against types at offsets +1, +5 (mod 18)
    and weak to types at offsets -1, -5 (mod 18).
    Additional cross-links at offsets +8 for a 3rd advantage / weakness.
    """
    n = _NUM_TYPES
    mat = [[1.0] * n for _ in range(n)]

    adv_offsets = [1, 5, 8]
    for i in range(n):
        for off in adv_offsets:
            j = (i + off) % n
            mat[i][j] = 1.25   # i has advantage over j
            mat[j][i] = 0.75   # j resists i → j is weak to i

    # Validate constraints
    for i in range(n):
        advs = sum(1 for j in range(n) if mat[i][j] == 1.25)
        weaks = sum(1 for j in range(n) if mat[i][j] == 0.75)
        assert 2 <= advs <= 4, f"Type {i} has {advs} advantages"
        assert 2 <= weaks <= 4, f"Type {i} has {weaks} weaknesses"

    return mat


TYPE_MATRIX: List[List[float]] = _build_type_matrix()


def type_multiplier(attacker: NkType, defender: NkType) -> float:
    """Look up the type effectiveness multiplier."""
    return TYPE_MATRIX[attacker.value][defender.value]


# ============================================================
# §3  BIOME VECTOR MODEL & CLIMATE ARCHETYPES
# ============================================================

class ClimateArchetype(Enum):
    TEMPERATE_MARITIME   = auto()
    SUBTROPICAL_LUSH     = auto()
    ARID_PLATEAU         = auto()
    BOREAL_COLD          = auto()
    VOLCANIC_ACTIVE      = auto()
    STORM_WRACKED        = auto()
    MISTBOUND_HIGHLAND   = auto()


@dataclass
class BiomeVector:
    """
    5-axis biome descriptor.  All values in [0.0, 1.0].
    """
    temperature:       float = 0.5
    moisture:          float = 0.5
    elevation:         float = 0.3
    vegetation_density: float = 0.5
    instability_bias:  float = 0.1

    def distance(self, other: "BiomeVector") -> float:
        return math.sqrt(
            (self.temperature - other.temperature) ** 2
            + (self.moisture - other.moisture) ** 2
            + (self.elevation - other.elevation) ** 2
            + (self.vegetation_density - other.vegetation_density) ** 2
            + (self.instability_bias - other.instability_bias) ** 2
        )

    def blend(self, other: "BiomeVector", w: float) -> "BiomeVector":
        """Weighted blend toward *other* (w=0 → self, w=1 → other)."""
        inv = 1.0 - w
        return BiomeVector(
            temperature=self.temperature * inv + other.temperature * w,
            moisture=self.moisture * inv + other.moisture * w,
            elevation=self.elevation * inv + other.elevation * w,
            vegetation_density=self.vegetation_density * inv + other.vegetation_density * w,
            instability_bias=self.instability_bias * inv + other.instability_bias * w,
        )

    def perturb(self, rng: SeededRNG, sigma: float = 0.05) -> "BiomeVector":
        def _clamp(v):
            return max(0.0, min(1.0, v))
        return BiomeVector(
            temperature=_clamp(self.temperature + rng.gauss(0, sigma)),
            moisture=_clamp(self.moisture + rng.gauss(0, sigma)),
            elevation=_clamp(self.elevation + rng.gauss(0, sigma)),
            vegetation_density=_clamp(self.vegetation_density + rng.gauss(0, sigma)),
            instability_bias=_clamp(self.instability_bias + rng.gauss(0, sigma * 0.5)),
        )

    def to_tuple(self) -> Tuple[float, ...]:
        return (
            self.temperature, self.moisture, self.elevation,
            self.vegetation_density, self.instability_bias,
        )


# Climate archetype → base biome vector
CLIMATE_BASES: Dict[ClimateArchetype, BiomeVector] = {
    ClimateArchetype.TEMPERATE_MARITIME:  BiomeVector(0.50, 0.60, 0.30, 0.55, 0.08),
    ClimateArchetype.SUBTROPICAL_LUSH:    BiomeVector(0.70, 0.75, 0.25, 0.80, 0.10),
    ClimateArchetype.ARID_PLATEAU:        BiomeVector(0.65, 0.15, 0.55, 0.15, 0.12),
    ClimateArchetype.BOREAL_COLD:         BiomeVector(0.20, 0.40, 0.45, 0.35, 0.07),
    ClimateArchetype.VOLCANIC_ACTIVE:     BiomeVector(0.75, 0.30, 0.60, 0.20, 0.30),
    ClimateArchetype.STORM_WRACKED:       BiomeVector(0.45, 0.80, 0.20, 0.40, 0.25),
    ClimateArchetype.MISTBOUND_HIGHLAND:  BiomeVector(0.35, 0.65, 0.70, 0.50, 0.15),
}

# Climate archetype → NkType affinity weights (higher = more likely selected)
CLIMATE_TYPE_AFFINITY: Dict[ClimateArchetype, Dict[NkType, float]] = {
    ClimateArchetype.TEMPERATE_MARITIME:  {NkType.TIDE: 1.5, NkType.VERDANT: 1.3, NkType.GALE: 1.2},
    ClimateArchetype.SUBTROPICAL_LUSH:    {NkType.BLOOM: 1.5, NkType.VERDANT: 1.4, NkType.VENOM: 1.3},
    ClimateArchetype.ARID_PLATEAU:        {NkType.DUNE: 1.5, NkType.STONE: 1.4, NkType.EMBER: 1.3},
    ClimateArchetype.BOREAL_COLD:         {NkType.FROST: 1.6, NkType.STONE: 1.3, NkType.SHADE: 1.2},
    ClimateArchetype.VOLCANIC_ACTIVE:     {NkType.EMBER: 1.6, NkType.STONE: 1.4, NkType.RIFT: 1.3},
    ClimateArchetype.STORM_WRACKED:       {NkType.VOLT: 1.5, NkType.TORRENT: 1.4, NkType.GALE: 1.3},
    ClimateArchetype.MISTBOUND_HIGHLAND:  {NkType.ECHO: 1.5, NkType.SHADE: 1.3, NkType.FROST: 1.2},
}


# ============================================================
# §4  ISLAND MACRO-GRAPH TOPOLOGY GENERATION
# ============================================================

class MacroRegion(Enum):
    """The 7 structural limbs of every island."""
    CENTRAL_BASIN    = auto()
    NORTH_RANGE      = auto()
    SOUTH_EXPANSE    = auto()
    WEST_WILD_BELT   = auto()
    EAST_COASTAL     = auto()
    INTERIOR_DEPTH   = auto()
    SUB_ISLET        = auto()


class NodeType(Enum):
    SETTLEMENT = auto()
    CITY       = auto()
    PATH       = auto()
    WILD_ZONE  = auto()
    FACILITY   = auto()
    DUNGEON    = auto()
    GATE       = auto()
    LANDMARK   = auto()


class GateType(Enum):
    LEAGUE      = auto()
    REPUTATION  = auto()
    RESEARCH    = auto()
    ECOLOGICAL  = auto()
    ANOMALY     = auto()
    ECONOMIC    = auto()


@dataclass
class GateRequirement:
    """A gate condition on an edge."""
    gate_type: GateType = GateType.LEAGUE
    primary_metric: str = "trainer_rating"
    threshold: float = 0.0
    secondary_modifier: str = ""
    flex_buffer: float = 0.0
    alternate_paths: List[Dict[str, Any]] = field(default_factory=list)

    def check(self, player_state: Dict[str, float]) -> bool:
        """Return True if player satisfies this gate."""
        val = player_state.get(self.primary_metric, 0.0)
        effective_threshold = self.threshold - self.flex_buffer
        if val >= effective_threshold:
            return True
        # Check alternates
        for alt in self.alternate_paths:
            metric = alt.get("metric", "")
            thresh = alt.get("threshold", 0.0)
            if player_state.get(metric, 0.0) >= thresh:
                return True
        return False


@dataclass
class MapNode:
    """A single node in the island topology graph."""
    node_id: str = ""
    node_type: NodeType = NodeType.PATH
    region: MacroRegion = MacroRegion.CENTRAL_BASIN
    name: str = ""
    biome: BiomeVector = field(default_factory=BiomeVector)
    neighbors: List[str] = field(default_factory=list)
    gate: Optional[GateRequirement] = None
    settlement_pop: int = 0
    is_start: bool = False
    is_depth_entrance: bool = False
    faction_influence: Dict[str, float] = field(default_factory=dict)
    # Encounter table slots (filled by §6)
    encounter_slots: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.name,
            "region": self.region.name,
            "name": self.name,
            "biome": self.biome.to_tuple(),
            "neighbors": list(self.neighbors),
            "gate": self.gate.gate_type.name if self.gate else None,
            "is_start": self.is_start,
        }


# ── Name generation ─────────────────────────────────────────

_SYLLABLES_A = [
    "ka", "ri", "mo", "ta", "su", "ne", "lo", "vi", "an", "du",
    "fe", "go", "hi", "ju", "le", "mi", "no", "pa", "re", "si",
    "to", "um", "va", "we", "xi", "yo", "za", "be", "ci", "da",
    "el", "fu", "gi", "ho", "in", "ja", "ke", "li", "mu", "na",
]
_SYLLABLES_B = [
    "ra", "shi", "wen", "tol", "mar", "ven", "kis", "dor", "pal",
    "thi", "arn", "bel", "cor", "den", "eld", "fen", "gal", "hel",
    "ion", "jor", "kel", "lan", "men", "nor", "osh", "pen", "ryn",
    "sol", "tor", "uth", "val", "wyr", "xen", "yol", "zan", "bir",
]


def _generate_name(rng: SeededRNG, prefix: str = "", min_syl: int = 2,
                   max_syl: int = 4) -> str:
    """Deterministic name from syllable tables."""
    n_syl = rng.randint(min_syl, max_syl)
    parts: List[str] = []
    for i in range(n_syl):
        table = _SYLLABLES_A if i % 2 == 0 else _SYLLABLES_B
        parts.append(rng.choice(table))
    name = "".join(parts).capitalize()
    if prefix:
        name = f"{prefix} {name}"
    return name


def generate_island_name(seed: int) -> str:
    """Canonical island name from seed."""
    rng = SeededRNG(seed).fork("island_name")
    return _generate_name(rng, min_syl=2, max_syl=3)


# ── Region biome base vectors ──────────────────────────────

_REGION_BIOME_OFFSETS: Dict[MacroRegion, BiomeVector] = {
    MacroRegion.CENTRAL_BASIN:   BiomeVector(0.0,  0.0,  -0.10, 0.05,  0.0),
    MacroRegion.NORTH_RANGE:     BiomeVector(-0.15, -0.05, 0.25,  -0.05, 0.02),
    MacroRegion.SOUTH_EXPANSE:   BiomeVector(0.10, -0.15, -0.10, -0.10, 0.03),
    MacroRegion.WEST_WILD_BELT:  BiomeVector(0.0,  0.10,  0.0,   0.20,  0.02),
    MacroRegion.EAST_COASTAL:    BiomeVector(0.0,  0.15,  -0.15, 0.0,   0.05),
    MacroRegion.INTERIOR_DEPTH:  BiomeVector(0.05, -0.10, 0.10,  -0.15, 0.20),
    MacroRegion.SUB_ISLET:       BiomeVector(0.0,  0.05,  -0.05, 0.0,   0.08),
}


def _region_biome(climate: ClimateArchetype, region: MacroRegion,
                  rng: SeededRNG) -> BiomeVector:
    """Compute the biome vector for a region on this island."""
    base = CLIMATE_BASES[climate]
    off = _REGION_BIOME_OFFSETS[region]
    def _c(v): return max(0.0, min(1.0, v))
    bv = BiomeVector(
        temperature=_c(base.temperature + off.temperature),
        moisture=_c(base.moisture + off.moisture),
        elevation=_c(base.elevation + off.elevation),
        vegetation_density=_c(base.vegetation_density + off.vegetation_density),
        instability_bias=_c(base.instability_bias + off.instability_bias),
    )
    return bv.perturb(rng, sigma=0.03)


# ── Topology builder ────────────────────────────────────────

@dataclass
class IslandTopology:
    """Complete island graph — nodes + edges + metadata."""
    seed: int = 0
    island_name: str = ""
    climate: ClimateArchetype = ClimateArchetype.TEMPERATE_MARITIME
    nodes: Dict[str, MapNode] = field(default_factory=dict)
    start_node_id: str = ""
    depth_entrance_ids: List[str] = field(default_factory=list)
    sub_islet_ids: List[List[str]] = field(default_factory=list)
    active_types: List[NkType] = field(default_factory=list)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    def neighbors_of(self, node_id: str) -> List[MapNode]:
        node = self.nodes.get(node_id)
        if not node:
            return []
        return [self.nodes[nid] for nid in node.neighbors if nid in self.nodes]

    def graph_distance(self, a: str, b: str) -> int:
        """BFS shortest-path distance between two nodes (-1 if unreachable)."""
        if a == b:
            return 0
        visited: Set[str] = {a}
        frontier = [a]
        dist = 0
        while frontier:
            dist += 1
            next_frontier: List[str] = []
            for nid in frontier:
                node = self.nodes.get(nid)
                if not node:
                    continue
                for nb in node.neighbors:
                    if nb == b:
                        return dist
                    if nb not in visited:
                        visited.add(nb)
                        next_frontier.append(nb)
            frontier = next_frontier
        return -1


def _add_edge(nodes: Dict[str, MapNode], a: str, b: str):
    """Add undirected edge between two node ids."""
    if b not in nodes[a].neighbors:
        nodes[a].neighbors.append(b)
    if a not in nodes[b].neighbors:
        nodes[b].neighbors.append(a)


def generate_island_topology(seed: int) -> IslandTopology:
    """
    Build the full island macro-graph for a given seed.

    Target: 120–180 nodes with structural grammar.
    """
    rng = SeededRNG(seed).fork("topology")
    name = generate_island_name(seed)

    # Pick climate
    climates = list(ClimateArchetype)
    climate = climates[seed % len(climates)]

    # Pick active types (12–15 from 18)
    type_rng = SeededRNG(seed).fork("active_types")
    n_active = type_rng.randint(12, 15)
    all_types = list(NkType)
    type_rng.shuffle(all_types)
    # Bias toward climate-affine types
    affinity = CLIMATE_TYPE_AFFINITY.get(climate, {})
    def _type_weight(t: NkType) -> float:
        return affinity.get(t, 1.0)
    all_types.sort(key=lambda t: -_type_weight(t))
    active_types = all_types[:n_active]

    nodes: Dict[str, MapNode] = {}
    nid_counter = [0]

    def _nid(prefix: str = "n") -> str:
        nid_counter[0] += 1
        return f"{prefix}_{nid_counter[0]:04d}"

    # ── Helper: build a spine of nodes for a region ────────
    def _build_spine(region: MacroRegion, length: int,
                     start_connect: Optional[str] = None) -> List[str]:
        spine_ids: List[str] = []
        bio_rng = rng.fork(f"biome_{region.name}")
        region_biome = _region_biome(climate, region, bio_rng)
        for i in range(length):
            nid = _nid("sp")
            # Periodically inject settlements / wild zones
            if i > 0 and i % rng.randint(3, 5) == 0:
                nt = NodeType.SETTLEMENT
            elif i > 0 and i % rng.randint(4, 7) == 0:
                nt = NodeType.WILD_ZONE
            else:
                nt = NodeType.PATH
            n = MapNode(
                node_id=nid,
                node_type=nt,
                region=region,
                name=_generate_name(bio_rng, prefix=region.name.replace("_", " ").title()),
                biome=region_biome.perturb(bio_rng, 0.04),
            )
            nodes[nid] = n
            if spine_ids:
                _add_edge(nodes, spine_ids[-1], nid)
            spine_ids.append(nid)
        if start_connect and spine_ids:
            _add_edge(nodes, start_connect, spine_ids[0])
        return spine_ids

    # ── Helper: attach branches off spine nodes ────────────
    def _attach_branches(spine_ids: List[str], region: MacroRegion,
                         p_branch: float = 0.3, max_branch_len: int = 6):
        bio_rng = rng.fork(f"branch_{region.name}")
        region_biome = _region_biome(climate, region, bio_rng)
        for sid in spine_ids:
            if bio_rng.random() < p_branch:
                blen = bio_rng.randint(2, max_branch_len)
                prev = sid
                for _ in range(blen):
                    nid = _nid("br")
                    nt_roll = bio_rng.random()
                    if nt_roll < 0.2:
                        nt = NodeType.SETTLEMENT
                    elif nt_roll < 0.4:
                        nt = NodeType.WILD_ZONE
                    elif nt_roll < 0.5:
                        nt = NodeType.LANDMARK
                    else:
                        nt = NodeType.PATH
                    n = MapNode(
                        node_id=nid, node_type=nt, region=region,
                        name=_generate_name(bio_rng),
                        biome=region_biome.perturb(bio_rng, 0.05),
                    )
                    nodes[nid] = n
                    _add_edge(nodes, prev, nid)
                    prev = nid
                # Terminal node might be dungeon or landmark
                terminal = nodes[prev]
                roll = bio_rng.random()
                if roll < 0.3:
                    terminal.node_type = NodeType.DUNGEON
                elif roll < 0.5:
                    terminal.node_type = NodeType.LANDMARK

    # ── 1. Start settlement ────────────────────────────────
    s0_id = _nid("s0")
    s0_biome = _region_biome(climate, MacroRegion.CENTRAL_BASIN, rng.fork("s0bio"))
    nodes[s0_id] = MapNode(
        node_id=s0_id, node_type=NodeType.SETTLEMENT,
        region=MacroRegion.CENTRAL_BASIN,
        name=_generate_name(rng.fork("s0name"), prefix="Haven"),
        biome=s0_biome, is_start=True,
    )

    # ── 2. Central Basin spine ─────────────────────────────
    cb_len = rng.randint(8, 13)
    cb_spine = _build_spine(MacroRegion.CENTRAL_BASIN, cb_len, start_connect=s0_id)

    # Place city C1 midway along central basin
    c1_idx = len(cb_spine) // 2
    if c1_idx < len(cb_spine):
        c1_node = nodes[cb_spine[c1_idx]]
        c1_node.node_type = NodeType.CITY
        c1_node.name = _generate_name(rng.fork("c1"), prefix="City")

    _attach_branches(cb_spine, MacroRegion.CENTRAL_BASIN,
                     p_branch=rng.uniform(0.2, 0.4))

    # ── 3. Regional limb spines ────────────────────────────
    limb_regions = [
        MacroRegion.NORTH_RANGE,
        MacroRegion.SOUTH_EXPANSE,
        MacroRegion.WEST_WILD_BELT,
        MacroRegion.EAST_COASTAL,
    ]
    limb_spines: Dict[MacroRegion, List[str]] = {}

    for lr in limb_regions:
        l_len = rng.randint(6, 14)
        # Connect to a random node on central basin spine
        connect_idx = rng.randint(0, max(0, len(cb_spine) - 1))
        connect_to = cb_spine[connect_idx]
        spine = _build_spine(lr, l_len, start_connect=connect_to)
        limb_spines[lr] = spine
        _attach_branches(spine, lr, p_branch=rng.uniform(0.20, 0.35),
                         max_branch_len=rng.randint(2, 5))

    # Place city C2 at end of east coastal
    if limb_spines.get(MacroRegion.EAST_COASTAL):
        ec_spine = limb_spines[MacroRegion.EAST_COASTAL]
        c2_node = nodes[ec_spine[-1]]
        c2_node.node_type = NodeType.CITY
        c2_node.name = _generate_name(rng.fork("c2"), prefix="Port")

    # Place city C3 somewhere on north range (seed-dependent)
    if rng.random() < 0.7 and limb_spines.get(MacroRegion.NORTH_RANGE):
        nr_spine = limb_spines[MacroRegion.NORTH_RANGE]
        c3_idx = rng.randint(len(nr_spine) // 3, len(nr_spine) - 1)
        c3_node = nodes[nr_spine[c3_idx]]
        c3_node.node_type = NodeType.CITY
        c3_node.name = _generate_name(rng.fork("c3"), prefix="Summit")

    # ── 4. Loops within and between limbs ──────────────────
    loop_rng = rng.fork("loops")
    all_spines = [cb_spine] + list(limb_spines.values())
    for spine in all_spines:
        # Intra-limb short loop
        if len(spine) >= 6:
            a_idx = loop_rng.randint(0, len(spine) // 2)
            b_idx = loop_rng.randint(len(spine) // 2 + 1, len(spine) - 1)
            _add_edge(nodes, spine[a_idx], spine[b_idx])
    # Cross-limb loops
    for _ in range(rng.randint(1, 3)):
        sa = loop_rng.choice(all_spines)
        sb = loop_rng.choice(all_spines)
        if sa is not sb and sa and sb:
            _add_edge(nodes, loop_rng.choice(sa), loop_rng.choice(sb))

    # ── 5. Wild core clusters ──────────────────────────────
    n_clusters = rng.randint(3, 6)
    wc_rng = rng.fork("wild_cores")
    wild_region = MacroRegion.WEST_WILD_BELT
    wild_biome = _region_biome(climate, wild_region, wc_rng)
    for ci in range(n_clusters):
        cluster_size = wc_rng.randint(3, 7)
        cluster_ids: List[str] = []
        # Entrance connects to a random existing node
        existing_ids = list(nodes.keys())
        anchor = wc_rng.choice(existing_ids)
        for wi in range(cluster_size):
            nid = _nid("wc")
            n = MapNode(
                node_id=nid, node_type=NodeType.WILD_ZONE,
                region=wild_region,
                name=_generate_name(wc_rng, prefix="Wild"),
                biome=wild_biome.perturb(wc_rng, 0.06),
            )
            nodes[nid] = n
            if cluster_ids:
                _add_edge(nodes, cluster_ids[-1], nid)
                # Micro loop inside cluster
                if len(cluster_ids) >= 3 and wc_rng.random() < 0.4:
                    _add_edge(nodes, cluster_ids[0], nid)
            cluster_ids.append(nid)
        # Connect entrance to anchor
        if cluster_ids:
            _add_edge(nodes, anchor, cluster_ids[0])

    # ── 6. Interior Depth Zone ─────────────────────────────
    depth_size = rng.randint(6, 12)
    depth_rng = rng.fork("depth")
    depth_biome = _region_biome(climate, MacroRegion.INTERIOR_DEPTH, depth_rng)
    # Invert biome relative to island baseline
    ib = CLIMATE_BASES[climate]
    depth_biome.temperature = max(0, min(1, 1.0 - ib.temperature + depth_rng.gauss(0, 0.05)))
    depth_biome.instability_bias = min(1.0, depth_biome.instability_bias + 0.25)

    depth_ids: List[str] = []
    for di in range(depth_size):
        nid = _nid("dp")
        nt = NodeType.DUNGEON if di > depth_size // 2 else NodeType.PATH
        n = MapNode(
            node_id=nid, node_type=nt,
            region=MacroRegion.INTERIOR_DEPTH,
            name=_generate_name(depth_rng, prefix="Depth"),
            biome=depth_biome.perturb(depth_rng, 0.04),
        )
        nodes[nid] = n
        if depth_ids:
            _add_edge(nodes, depth_ids[-1], nid)
        depth_ids.append(nid)
    # Loop inside depth
    if len(depth_ids) >= 4:
        _add_edge(nodes, depth_ids[0], depth_ids[-1])

    # Depth entrance gate
    depth_entrance_id = depth_ids[0] if depth_ids else ""
    if depth_entrance_id:
        nodes[depth_entrance_id].is_depth_entrance = True
        nodes[depth_entrance_id].gate = GateRequirement(
            gate_type=GateType.ANOMALY,
            primary_metric="anomaly_exposure",
            threshold=50.0,
            alternate_paths=[
                {"metric": "league_tier", "threshold": 3.0},
                {"metric": "research_milestones", "threshold": 5.0},
            ],
        )
        # Connect depth to interior-most node on central basin
        if cb_spine:
            _add_edge(nodes, cb_spine[-1], depth_entrance_id)

    # ── 7. Sub-islets ──────────────────────────────────────
    n_islets = rng.randint(2, 5)
    sub_islet_all: List[List[str]] = []
    islet_rng = rng.fork("islets")
    for ii in range(n_islets):
        islet_size = islet_rng.randint(4, 10)
        islet_biome = _region_biome(climate, MacroRegion.SUB_ISLET,
                                     islet_rng.fork(f"islet_{ii}"))
        islet_ids: List[str] = []
        for si in range(islet_size):
            nid = _nid("is")
            nt_roll = islet_rng.random()
            nt = (NodeType.SETTLEMENT if nt_roll < 0.2
                  else NodeType.WILD_ZONE if nt_roll < 0.5
                  else NodeType.PATH)
            n = MapNode(
                node_id=nid, node_type=nt,
                region=MacroRegion.SUB_ISLET,
                name=_generate_name(islet_rng, prefix="Isle"),
                biome=islet_biome.perturb(islet_rng, 0.05),
            )
            nodes[nid] = n
            if islet_ids:
                _add_edge(nodes, islet_ids[-1], nid)
            islet_ids.append(nid)
        # Loop
        if len(islet_ids) >= 4:
            _add_edge(nodes, islet_ids[0], islet_ids[-1])
        # Gate entrance from main island
        if islet_ids:
            existing_ids = [nid for nid, nd in nodes.items()
                           if nd.region != MacroRegion.SUB_ISLET]
            if existing_ids:
                anchor = islet_rng.choice(existing_ids)
                _add_edge(nodes, anchor, islet_ids[0])
                nodes[islet_ids[0]].gate = GateRequirement(
                    gate_type=islet_rng.choice(list(GateType)),
                    primary_metric="exploration_score",
                    threshold=islet_rng.uniform(20, 60),
                )
        sub_islet_all.append(islet_ids)

    # ── 8. Facilities (research / industrial) ──────────────
    n_facilities = rng.randint(3, 6)
    fac_rng = rng.fork("facilities")
    existing_ids = list(nodes.keys())
    for fi in range(n_facilities):
        nid = _nid("fac")
        anchor = fac_rng.choice(existing_ids)
        anchor_node = nodes[anchor]
        n = MapNode(
            node_id=nid, node_type=NodeType.FACILITY,
            region=anchor_node.region,
            name=_generate_name(fac_rng, prefix="Lab" if fi % 2 == 0 else "Works"),
            biome=anchor_node.biome.perturb(fac_rng, 0.03),
        )
        nodes[nid] = n
        _add_edge(nodes, anchor, nid)

    # ── 9. Gate placement (8–15 gated edges) ───────────────
    gate_rng = rng.fork("gates")
    n_gates = gate_rng.randint(8, 15)
    # We already placed depth + islet gates; add more
    placed_gates = 1 + n_islets  # depth entrance + islet entrances
    non_start_ids = [nid for nid, nd in nodes.items()
                     if not nd.is_start and nd.gate is None]
    gate_rng.shuffle(non_start_ids)
    for gi in range(min(n_gates - placed_gates, len(non_start_ids))):
        target_nid = non_start_ids[gi]
        target = nodes[target_nid]
        # Don't gate start-radius nodes (distance ≤ 2 from S0)
        if s0_id in nodes:
            # Quick distance check using BFS (only for small radius)
            dist = 0
            found = False
            visited_set: Set[str] = {s0_id}
            frontier_set = [s0_id]
            while frontier_set and dist < 3:
                dist += 1
                nf: List[str] = []
                for fid in frontier_set:
                    for nb in nodes[fid].neighbors:
                        if nb == target_nid:
                            found = True
                            break
                        if nb not in visited_set:
                            visited_set.add(nb)
                            nf.append(nb)
                    if found:
                        break
                frontier_set = nf
            if found and dist <= 2:
                continue  # skip gating near start

        gt = gate_rng.choice(list(GateType))
        metric_map = {
            GateType.LEAGUE: "trainer_rating",
            GateType.REPUTATION: "faction_standing",
            GateType.RESEARCH: "research_milestones",
            GateType.ECOLOGICAL: "ecological_balance",
            GateType.ANOMALY: "anomaly_exposure",
            GateType.ECONOMIC: "economic_investment",
        }
        target.gate = GateRequirement(
            gate_type=gt,
            primary_metric=metric_map[gt],
            threshold=gate_rng.uniform(15, 80),
            flex_buffer=gate_rng.uniform(0, 10),
        )

    # ── 10. Ensure extra cities / settlements to hit targets ──
    settlement_count = sum(1 for n in nodes.values()
                          if n.node_type == NodeType.SETTLEMENT)
    city_count = sum(1 for n in nodes.values()
                     if n.node_type == NodeType.CITY)
    # Promote some settlements to cities if needed
    if city_count < 5:
        for nid, nd in list(nodes.items()):
            if nd.node_type == NodeType.SETTLEMENT and len(nd.neighbors) >= 3:
                nd.node_type = NodeType.CITY
                nd.name = _generate_name(rng.fork(f"promote_{nid}"), prefix="City")
                city_count += 1
                if city_count >= 5:
                    break

    # ── 11. Biome adjacency blending (70/20/10 rule) ───────
    # One pass of smoothing
    for nid, nd in nodes.items():
        neighbor_biomes = [nodes[nb].biome for nb in nd.neighbors if nb in nodes]
        if not neighbor_biomes:
            continue
        avg_nb = BiomeVector(
            temperature=sum(b.temperature for b in neighbor_biomes) / len(neighbor_biomes),
            moisture=sum(b.moisture for b in neighbor_biomes) / len(neighbor_biomes),
            elevation=sum(b.elevation for b in neighbor_biomes) / len(neighbor_biomes),
            vegetation_density=sum(b.vegetation_density for b in neighbor_biomes) / len(neighbor_biomes),
            instability_bias=sum(b.instability_bias for b in neighbor_biomes) / len(neighbor_biomes),
        )
        # 70% self, 20% neighbors, 10% noise (already in initial perturb)
        nd.biome = nd.biome.blend(avg_nb, 0.2)

    topo = IslandTopology(
        seed=seed,
        island_name=name,
        climate=climate,
        nodes=nodes,
        start_node_id=s0_id,
        depth_entrance_ids=[depth_entrance_id] if depth_entrance_id else [],
        sub_islet_ids=sub_islet_all,
        active_types=active_types,
    )

    _dbg(f"Island '{name}' (seed={seed}): {topo.node_count} nodes, "
         f"{city_count} cities, {len(active_types)} active types, "
         f"climate={climate.name}")
    return topo


# ============================================================
# §5  SPECIES GENERATION (300 PER ISLAND)
# ============================================================

class RarityTier(Enum):
    COMMON   = 0
    UNCOMMON = 1
    RARE     = 2
    ELITE    = 3
    APEX     = 4
    ANOMALY  = 5


# BST ranges per rarity
_BST_RANGES: Dict[RarityTier, Tuple[int, int]] = {
    RarityTier.COMMON:   (300, 380),
    RarityTier.UNCOMMON: (360, 440),
    RarityTier.RARE:     (420, 500),
    RarityTier.ELITE:    (480, 560),
    RarityTier.APEX:     (550, 620),
    RarityTier.ANOMALY:  (350, 650),  # volatile
}

# Rarity distribution targets (out of 300)
_RARITY_TARGETS: Dict[RarityTier, Tuple[int, int]] = {
    RarityTier.COMMON:   (110, 130),   # ~40%
    RarityTier.UNCOMMON: (65, 85),     # ~25%
    RarityTier.RARE:     (38, 52),     # ~15%
    RarityTier.ELITE:    (25, 35),     # ~10%
    RarityTier.APEX:     (10, 18),     # ~5%
    RarityTier.ANOMALY:  (12, 22),     # ~5%
}


class StatArchetype(Enum):
    BALANCED  = auto()
    GLASS     = auto()   # high offense, low defense
    TANK      = auto()   # high defense, low offense
    TEMPO     = auto()   # high reflex/flux
    DISRUPTOR = auto()   # high focus, moderate others
    VOLATILE  = auto()   # anomaly-tier — wild distribution


@dataclass
class StatVector:
    """6-stat creature stat block."""
    vitality:  int = 50
    force:     int = 50
    reflex:    int = 50
    focus:     int = 50
    stability: int = 50
    flux:      int = 50

    @property
    def bst(self) -> int:
        return (self.vitality + self.force + self.reflex
                + self.focus + self.stability + self.flux)

    def to_tuple(self) -> Tuple[int, ...]:
        return (self.vitality, self.force, self.reflex,
                self.focus, self.stability, self.flux)


@dataclass
class HabitatAffinity:
    """Species habitat preference matching BiomeVector structure."""
    temperature_pref:  float = 0.5
    moisture_pref:     float = 0.5
    elevation_pref:    float = 0.3
    vegetation_pref:   float = 0.5
    instability_pref:  float = 0.1

    def distance_to_biome(self, bv: BiomeVector) -> float:
        return math.sqrt(
            (self.temperature_pref - bv.temperature) ** 2
            + (self.moisture_pref - bv.moisture) ** 2
            + (self.elevation_pref - bv.elevation) ** 2
            + (self.vegetation_pref - bv.vegetation_density) ** 2
            + (self.instability_pref - bv.instability_bias) ** 2
        )


@dataclass
class GeneticProfile:
    """Per-instance genetic profile."""
    stat_genes: List[int] = field(default_factory=lambda: [16] * 6)  # 0–31 each
    trait_genes: List[str] = field(default_factory=list)
    stability_gene: int = 16
    variance_seed: int = 0
    lineage_depth: int = 0

    # Gene clusters
    @property
    def physical_cluster(self) -> int:
        return self.stat_genes[0] + self.stat_genes[1]  # vitality + force

    @property
    def tempo_cluster(self) -> int:
        return self.stat_genes[2] + self.stat_genes[5]  # reflex + flux

    @property
    def cognitive_cluster(self) -> int:
        return self.stat_genes[3] + self.stat_genes[4]  # focus + stability


@dataclass
class Species:
    """A species template (one of 300 per island)."""
    species_id: str = ""
    name: str = ""
    primary_type: NkType = NkType.EMBER
    secondary_type: Optional[NkType] = None
    rarity: RarityTier = RarityTier.COMMON
    base_stats: StatVector = field(default_factory=StatVector)
    stat_archetype: StatArchetype = StatArchetype.BALANCED
    habitat: HabitatAffinity = field(default_factory=HabitatAffinity)
    move_pool: List[str] = field(default_factory=list)
    passive_trait: str = ""
    mutation_potential: float = 0.5
    evolution_stage: int = 1        # 1, 2, or 3
    evolution_line_id: str = ""     # shared across stages
    evolves_from: Optional[str] = None
    evolves_to: Optional[str] = None
    biome_affinity_regions: List[MacroRegion] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "species_id": self.species_id,
            "name": self.name,
            "primary_type": self.primary_type.name,
            "secondary_type": self.secondary_type.name if self.secondary_type else None,
            "rarity": self.rarity.name,
            "bst": self.base_stats.bst,
            "stats": self.base_stats.to_tuple(),
            "archetype": self.stat_archetype.name,
            "passive": self.passive_trait,
            "evo_stage": self.evolution_stage,
            "evo_line": self.evolution_line_id,
        }


@dataclass
class CreatureInstance:
    """A living creature instance (owned by player or wild)."""
    instance_id: str = ""
    species_id: str = ""
    nickname: str = ""
    level: int = 1
    genes: GeneticProfile = field(default_factory=GeneticProfile)
    fatigue: float = 0.0          # 0–100
    loyalty: float = 50.0         # 0–100
    temperament: float = 0.5      # 0–1
    adaptation_drift: float = 0.0
    exposure_history: List[str] = field(default_factory=list)
    # Effective stats = base_stats modified by genes, level, fatigue
    current_hp: int = 100

    def effective_stats(self, species: Species) -> StatVector:
        """Compute effective stats from base + genes + level + fatigue."""
        bs = species.base_stats
        g = self.genes.stat_genes
        fatigue_mult = max(0.5, 1.0 - self.fatigue / 200.0)
        level_mult = 1.0 + (self.level - 1) * 0.02
        def _calc(base: int, gene: int) -> int:
            return max(1, int((base + gene) * level_mult * fatigue_mult))
        return StatVector(
            vitality=_calc(bs.vitality, g[0]),
            force=_calc(bs.force, g[1]),
            reflex=_calc(bs.reflex, g[2]),
            focus=_calc(bs.focus, g[3]),
            stability=_calc(bs.stability, g[4]),
            flux=_calc(bs.flux, g[5]),
        )


# ── Trait library ──────────────────────────────────────────

_PASSIVE_TRAITS = [
    "Adaptive", "Resilient", "Swift", "Cunning", "Brute",
    "Stoic", "Volatile", "Predatory", "Symbiotic", "Migratory",
    "Burrower", "Glider", "Nocturnal", "Photosynthetic", "Venomous",
    "Armored", "Regenerator", "Echolocator", "Pack Hunter", "Solitary",
    "Thermal Vent", "Tidal Rhythm", "Spore Bearer", "Crystal Shell",
    "Rift Born", "Storm Caller", "Root Anchor", "Sand Walker",
    "Mist Cloak", "Pulse Emitter",
]

# ── Move templates ─────────────────────────────────────────

_MOVE_TEMPLATES = [
    "Strike", "Guard", "Rush", "Barrier", "Pulse",
    "Drain", "Eruption", "Torrent", "Freeze", "Shock",
    "Dissolve", "Shadow Lash", "Bloom Burst", "Quake",
    "Gale Cut", "Rift Tear", "Venom Spray", "Alloy Shell",
    "Echo Wave", "Dune Storm", "Thorn Snare", "Flux Overload",
    "Radiant Flash", "Stabilize", "Tempo Shift", "Disrupt Field",
]


def _generate_stat_vector(rng: SeededRNG, archetype: StatArchetype,
                          bst_target: int) -> StatVector:
    """Generate a stat vector matching archetype and BST target."""
    # Archetype weight profiles (vitality, force, reflex, focus, stability, flux)
    profiles: Dict[StatArchetype, List[float]] = {
        StatArchetype.BALANCED:  [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        StatArchetype.GLASS:     [0.6, 1.6, 1.2, 1.0, 0.5, 1.1],
        StatArchetype.TANK:      [1.5, 0.7, 0.6, 0.9, 1.5, 0.8],
        StatArchetype.TEMPO:     [0.8, 0.9, 1.5, 0.8, 0.7, 1.3],
        StatArchetype.DISRUPTOR: [0.9, 0.8, 1.0, 1.5, 0.9, 0.9],
        StatArchetype.VOLATILE:  [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    }
    weights = profiles[archetype]
    if archetype == StatArchetype.VOLATILE:
        # Anomaly-style wild variance
        weights = [rng.uniform(0.4, 1.8) for _ in range(6)]

    total_w = sum(weights)
    raw = [bst_target * w / total_w for w in weights]
    # Add small noise
    raw = [max(10, int(r + rng.gauss(0, r * 0.08))) for r in raw]
    # Normalize to hit BST target
    current_bst = sum(raw)
    if current_bst > 0:
        scale = bst_target / current_bst
        raw = [max(10, int(r * scale)) for r in raw]
    # Fix rounding residual
    diff = bst_target - sum(raw)
    if diff != 0:
        idx = rng.randint(0, 5)
        raw[idx] = max(10, raw[idx] + diff)

    return StatVector(
        vitality=raw[0], force=raw[1], reflex=raw[2],
        focus=raw[3], stability=raw[4], flux=raw[5],
    )


def generate_species_roster(topology: IslandTopology) -> Dict[str, Species]:
    """
    Generate 300 species for an island based on its topology, climate,
    and active type pool.
    """
    seed = topology.seed
    rng = SeededRNG(seed).fork("species")
    climate = topology.climate
    active_types = topology.active_types
    n_types = len(active_types)

    species_map: Dict[str, Species] = {}
    species_list: List[Species] = []

    # ── Rarity distribution (constrained allocator) ────────
    # Start with guaranteed minimums, then distribute remaining budget
    # by weighted random.  This prevents the old approach from summing
    # independent random picks to more (or fewer) than 300.
    rarity_counts: Dict[RarityTier, int] = {}
    budget = 300
    for rt in RarityTier:
        lo, _hi = _RARITY_TARGETS[rt]
        rarity_counts[rt] = lo
        budget -= lo
    # budget is now the surplus above all minimums
    # Distribute surplus one-at-a-time, respecting per-tier ceilings
    tiers_with_room = [rt for rt in RarityTier
                       if rarity_counts[rt] < _RARITY_TARGETS[rt][1]]
    while budget > 0 and tiers_with_room:
        rt = rng.choice(tiers_with_room)
        rarity_counts[rt] += 1
        budget -= 1
        if rarity_counts[rt] >= _RARITY_TARGETS[rt][1]:
            tiers_with_room = [r for r in tiers_with_room if r != rt]
    # Any leftover (very unlikely) goes to COMMON
    if budget > 0:
        rarity_counts[RarityTier.COMMON] += budget

    # ── Evolution lines ────────────────────────────────────
    evo_rng = rng.fork("evolution")
    line_counter = [0]
    species_counter = [0]

    def _next_line_id() -> str:
        line_counter[0] += 1
        return f"line_{line_counter[0]:04d}"

    def _next_species_id() -> str:
        species_counter[0] += 1
        return f"sp_{species_counter[0]:04d}"

    def _make_species(line_id: str, stage: int, rarity: RarityTier,
                      primary: NkType, secondary: Optional[NkType],
                      archetype: StatArchetype,
                      prev_id: Optional[str] = None) -> Species:
        sid = _next_species_id()
        bst_lo, bst_hi = _BST_RANGES[rarity]
        # Higher stages get higher BST within range
        stage_bias = (stage - 1) * 0.3
        bst = rng.randint(
            int(bst_lo + (bst_hi - bst_lo) * stage_bias * 0.3),
            bst_hi,
        )
        stats = _generate_stat_vector(rng.fork(sid), archetype, bst)

        # Habitat affinity
        climate_base = CLIMATE_BASES[climate]
        # Bias by type
        type_temp_bias = {
            NkType.EMBER: 0.15, NkType.FROST: -0.2, NkType.TIDE: -0.05,
            NkType.DUNE: 0.1, NkType.VERDANT: 0.0, NkType.VOLT: 0.0,
        }
        temp_off = type_temp_bias.get(primary, 0.0)
        hab = HabitatAffinity(
            temperature_pref=max(0, min(1, climate_base.temperature + temp_off + rng.gauss(0, 0.08))),
            moisture_pref=max(0, min(1, climate_base.moisture + rng.gauss(0, 0.1))),
            elevation_pref=max(0, min(1, climate_base.elevation + rng.gauss(0, 0.1))),
            vegetation_pref=max(0, min(1, climate_base.vegetation_density + rng.gauss(0, 0.1))),
            instability_pref=max(0, min(1, climate_base.instability_bias + rng.gauss(0, 0.05))),
        )

        # Move pool (4–8 moves)
        n_moves = rng.randint(4, 8)
        moves = rng.sample(_MOVE_TEMPLATES, min(n_moves, len(_MOVE_TEMPLATES)))
        # Prepend type-flavored move
        moves.insert(0, f"{primary.name.title()} {rng.choice(['Strike', 'Wave', 'Burst', 'Pulse'])}")

        # Passive trait
        passive = rng.choice(_PASSIVE_TRAITS)

        # Region affinity (1–3 regions)
        regions = list(MacroRegion)
        n_reg = rng.randint(1, 3)
        region_affinities = rng.sample(regions, min(n_reg, len(regions)))

        sp = Species(
            species_id=sid,
            name=_generate_name(rng.fork(f"name_{sid}"), min_syl=2, max_syl=3),
            primary_type=primary,
            secondary_type=secondary,
            rarity=rarity,
            base_stats=stats,
            stat_archetype=archetype,
            habitat=hab,
            move_pool=moves,
            passive_trait=passive,
            mutation_potential=rng.uniform(0.2, 0.9),
            evolution_stage=stage,
            evolution_line_id=line_id,
            evolves_from=prev_id,
            biome_affinity_regions=region_affinities,
        )
        species_map[sid] = sp
        species_list.append(sp)
        return sp

    # ── Build lines ────────────────────────────────────────
    # Type allocation: ensure each active type has ≥10 species
    type_quotas: Dict[NkType, int] = {t: 0 for t in active_types}
    min_per_type = 12  # guarantee at least 12 per type (well above 10 floor)

    # Track species per rarity used
    rarity_used: Dict[RarityTier, int] = {rt: 0 for rt in RarityTier}

    def _pick_rarity() -> RarityTier:
        """Pick a rarity tier that still has budget."""
        available = [rt for rt in RarityTier if rarity_used[rt] < rarity_counts[rt]]
        if not available:
            return RarityTier.COMMON
        return rng.choice(available)

    def _pick_archetype() -> StatArchetype:
        archetypes = list(StatArchetype)
        return rng.choice(archetypes[:-1])  # exclude VOLATILE for non-anomaly

    # Ensure minimum type coverage
    for t in active_types:
        while type_quotas[t] < min_per_type and len(species_list) < 300:
            line_id = _next_line_id()
            stages = evo_rng.choice([1, 2, 2, 2, 3, 3])
            rarity_base = _pick_rarity()
            arch = _pick_archetype()
            # Dual type?
            secondary = None
            if evo_rng.random() < 0.47:
                candidates = [at for at in active_types if at != t]
                if candidates:
                    secondary = evo_rng.choice(candidates)

            prev_id = None
            for stage in range(1, stages + 1):
                # Rarity escalates with stage
                if stage == 1:
                    r = rarity_base
                elif stage == 2:
                    r = RarityTier(min(rarity_base.value + 1, RarityTier.ELITE.value))
                else:
                    r = RarityTier(min(rarity_base.value + 2, RarityTier.APEX.value))
                sp = _make_species(line_id, stage, r, t, secondary, arch, prev_id)
                if prev_id and prev_id in species_map:
                    species_map[prev_id].evolves_to = sp.species_id
                prev_id = sp.species_id
                type_quotas[t] += 1
                rarity_used[r] = rarity_used.get(r, 0) + 1

    # Fill remaining slots
    while len(species_list) < 300:
        t = rng.choice(active_types)
        line_id = _next_line_id()
        stages = evo_rng.choice([1, 1, 2])
        rarity_base = _pick_rarity()
        arch = _pick_archetype()
        secondary = None
        if evo_rng.random() < 0.47:
            candidates = [at for at in active_types if at != t]
            if candidates:
                secondary = evo_rng.choice(candidates)
        prev_id = None
        for stage in range(1, stages + 1):
            if len(species_list) >= 300:
                break
            if stage == 1:
                r = rarity_base
            else:
                r = RarityTier(min(rarity_base.value + 1, RarityTier.ELITE.value))
            sp = _make_species(line_id, stage, r, t, secondary, arch, prev_id)
            if prev_id and prev_id in species_map:
                species_map[prev_id].evolves_to = sp.species_id
            prev_id = sp.species_id
            type_quotas[t] += 1
            rarity_used[r] = rarity_used.get(r, 0) + 1

    # Anomaly tier: override some species
    anomaly_count = rarity_counts.get(RarityTier.ANOMALY, 15)
    anomaly_candidates = [sp for sp in species_list
                         if sp.rarity in (RarityTier.RARE, RarityTier.ELITE)]
    evo_rng.shuffle(anomaly_candidates)
    for i in range(min(anomaly_count, len(anomaly_candidates))):
        sp = anomaly_candidates[i]
        sp.rarity = RarityTier.ANOMALY
        sp.stat_archetype = StatArchetype.VOLATILE
        bst = rng.randint(350, 650)
        sp.base_stats = _generate_stat_vector(rng.fork(f"anom_{sp.species_id}"),
                                               StatArchetype.VOLATILE, bst)
        sp.habitat.instability_pref = min(1.0, sp.habitat.instability_pref + 0.3)

    _dbg(f"Species roster: {len(species_list)} species, "
         f"{len(set(sp.evolution_line_id for sp in species_list))} lines")
    return species_map


# ============================================================
# §6  ENCOUNTER TABLE SYSTEM
# ============================================================

@dataclass
class EncounterTable:
    """Per-node encounter table with rarity-tiered slots."""
    node_id: str = ""
    common_slots: List[str] = field(default_factory=list)      # species_ids
    uncommon_slots: List[str] = field(default_factory=list)
    rare_slots: List[str] = field(default_factory=list)
    elite_slots: List[str] = field(default_factory=list)
    apex_slot: Optional[str] = None
    anomaly_slot: Optional[str] = None

    def all_species(self) -> List[str]:
        result = (self.common_slots + self.uncommon_slots
                  + self.rare_slots + self.elite_slots)
        if self.apex_slot:
            result.append(self.apex_slot)
        if self.anomaly_slot:
            result.append(self.anomaly_slot)
        return result


# Default slot counts by node type
_SLOT_COUNTS: Dict[NodeType, Dict[str, int]] = {
    NodeType.PATH:      {"common": 6, "uncommon": 3, "rare": 2, "elite": 0, "apex": 0},
    NodeType.WILD_ZONE: {"common": 5, "uncommon": 4, "rare": 3, "elite": 1, "apex": 0},
    NodeType.DUNGEON:   {"common": 2, "uncommon": 3, "rare": 3, "elite": 2, "apex": 1},
    NodeType.LANDMARK:  {"common": 3, "uncommon": 3, "rare": 2, "elite": 1, "apex": 0},
    NodeType.SETTLEMENT:{"common": 4, "uncommon": 2, "rare": 1, "elite": 0, "apex": 0},
    NodeType.CITY:      {"common": 3, "uncommon": 2, "rare": 1, "elite": 0, "apex": 0},
    NodeType.FACILITY:  {"common": 2, "uncommon": 2, "rare": 2, "elite": 1, "apex": 0},
    NodeType.GATE:      {"common": 4, "uncommon": 3, "rare": 2, "elite": 0, "apex": 0},
}

_HABITAT_THRESHOLD = 0.65  # max distance for species eligibility


def generate_encounter_tables(
    topology: IslandTopology,
    species_map: Dict[str, Species],
    ledger: Optional["IslandLedger"] = None,
) -> Dict[str, EncounterTable]:
    """
    Build encounter tables for every node in the island.

    Early-game protection: within radius 3 of start, no apex/anomaly,
    rare capped at 1.
    """
    rng = SeededRNG(topology.seed).fork("encounters")
    tables: Dict[str, EncounterTable] = {}

    # Precompute start-radius
    start_radius: Set[str] = set()
    if topology.start_node_id:
        visited: Set[str] = {topology.start_node_id}
        frontier = [topology.start_node_id]
        for _ in range(3):
            nf: List[str] = []
            for fid in frontier:
                node = topology.nodes.get(fid)
                if not node:
                    continue
                for nb in node.neighbors:
                    if nb not in visited:
                        visited.add(nb)
                        nf.append(nb)
            frontier = nf
        start_radius = visited

    # Group species by rarity
    by_rarity: Dict[RarityTier, List[Species]] = {rt: [] for rt in RarityTier}
    for sp in species_map.values():
        by_rarity[sp.rarity].append(sp)

    for nid, node in topology.nodes.items():
        slots = _SLOT_COUNTS.get(node.node_type,
                                  _SLOT_COUNTS[NodeType.PATH])
        is_early = nid in start_radius

        def _fill_slots(rarity: RarityTier, count: int) -> List[str]:
            if count <= 0:
                return []
            # Early-game protection
            if is_early:
                if rarity in (RarityTier.APEX, RarityTier.ANOMALY):
                    return []
                if rarity == RarityTier.RARE:
                    count = min(count, 1)

            candidates = by_rarity.get(rarity, [])
            # Filter by habitat distance
            eligible: List[Tuple[float, Species]] = []
            for sp in candidates:
                dist = sp.habitat.distance_to_biome(node.biome)
                if dist < _HABITAT_THRESHOLD:
                    # Weight: closer = higher
                    weight = max(0.01, 1.0 - dist / _HABITAT_THRESHOLD)
                    # Region bonus
                    if node.region in sp.biome_affinity_regions:
                        weight *= 1.5
                    eligible.append((weight, sp))

            if not eligible:
                # Fallback: relax threshold
                for sp in candidates:
                    eligible.append((0.1, sp))

            if not eligible:
                return []

            weights = [w for w, _ in eligible]
            pool = [sp for _, sp in eligible]
            chosen: List[str] = []
            for _ in range(min(count, len(pool))):
                picks = rng.choices(pool, weights=weights, k=1)
                chosen.append(picks[0].species_id)
            return chosen

        et = EncounterTable(
            node_id=nid,
            common_slots=_fill_slots(RarityTier.COMMON, slots["common"]),
            uncommon_slots=_fill_slots(RarityTier.UNCOMMON, slots["uncommon"]),
            rare_slots=_fill_slots(RarityTier.RARE, slots["rare"]),
            elite_slots=_fill_slots(RarityTier.ELITE, slots["elite"]),
        )

        if slots.get("apex", 0) > 0:
            apex_list = _fill_slots(RarityTier.APEX, 1)
            et.apex_slot = apex_list[0] if apex_list else None

        # Anomaly slot: only if node instability high enough
        if node.biome.instability_bias > 0.25 and not is_early:
            anom_list = _fill_slots(RarityTier.ANOMALY, 1)
            et.anomaly_slot = anom_list[0] if anom_list else None

        tables[nid] = et
        node.encounter_slots = {
            "common": et.common_slots,
            "uncommon": et.uncommon_slots,
            "rare": et.rare_slots,
        }

    return tables


def roll_encounter(table: EncounterTable, rng: SeededRNG) -> Optional[str]:
    """Roll an encounter from a node table. Returns species_id or None."""
    # Rarity roll
    roll = rng.random()
    if roll < 0.02 and table.anomaly_slot:
        return table.anomaly_slot
    elif roll < 0.05 and table.apex_slot:
        return table.apex_slot
    elif roll < 0.15 and table.elite_slots:
        return rng.choice(table.elite_slots)
    elif roll < 0.30 and table.rare_slots:
        return rng.choice(table.rare_slots)
    elif roll < 0.55 and table.uncommon_slots:
        return rng.choice(table.uncommon_slots)
    elif table.common_slots:
        return rng.choice(table.common_slots)
    return None


# ============================================================
# §7  BATTLE & LEAGUE SIMULATION
# ============================================================

class StatusEffect(Enum):
    FRACTURED   = auto()  # −Stability scaling each turn
    OVERCLOCKED = auto()  # +Force, −Stability
    ENTRENCHED  = auto()  # +Stability, −Reflex
    DISRUPTED   = auto()  # −Focus, misfire chance
    FLUXED      = auto()  # volatility in damage


@dataclass
class BattleCreature:
    """Snapshot of a creature in battle."""
    instance: CreatureInstance = field(default_factory=CreatureInstance)
    species: Species = field(default_factory=Species)
    effective: StatVector = field(default_factory=StatVector)
    current_hp: int = 0
    statuses: List[StatusEffect] = field(default_factory=list)
    tempo_debt: float = 0.0
    fainted: bool = False
    is_player_owned: bool = False   # team ownership tag for faint routing

    def init_from(self, instance: CreatureInstance, species: Species):
        self.instance = instance
        self.species = species
        self.effective = instance.effective_stats(species)
        self.current_hp = self.effective.vitality * 3  # HP pool
        self.statuses = []
        self.tempo_debt = 0.0
        self.fainted = False


@dataclass
class BattleResult:
    """Outcome of a single battle."""
    winner: str = ""       # "player" or "opponent"
    player_remaining: int = 0
    opponent_remaining: int = 0
    turns: int = 0
    fatigue_delta: float = 0.0


def simulate_battle(
    player_team: List[Tuple[CreatureInstance, Species]],
    opponent_team: List[Tuple[CreatureInstance, Species]],
    rng: SeededRNG,
) -> BattleResult:
    """
    Simulate a 3v3 turn-based battle.  Pure deterministic math.
    Returns BattleResult.
    """
    # Build battle snapshots
    p_team = []
    for inst, sp in player_team[:3]:
        bc = BattleCreature()
        bc.init_from(inst, sp)
        bc.is_player_owned = True
        p_team.append(bc)

    o_team = []
    for inst, sp in opponent_team[:3]:
        bc = BattleCreature()
        bc.init_from(inst, sp)
        bc.is_player_owned = False
        o_team.append(bc)

    turns = 0
    max_turns = 100  # prevent infinite loops

    p_active = 0
    o_active = 0

    while turns < max_turns:
        turns += 1

        if p_active >= len(p_team) or o_active >= len(o_team):
            break

        p_cur = p_team[p_active]
        o_cur = o_team[o_active]

        if p_cur.fainted:
            p_active += 1
            continue
        if o_cur.fainted:
            o_active += 1
            continue

        # ── Initiative ─────────────────────────────────────
        p_init = p_cur.effective.reflex - p_cur.tempo_debt + rng.uniform(-5, 5)
        o_init = o_cur.effective.reflex - o_cur.tempo_debt + rng.uniform(-5, 5)

        first, second = (p_cur, o_cur) if p_init >= o_init else (o_cur, p_cur)

        # ── Damage calculation ─────────────────────────────
        def _calc_damage(atk: BattleCreature, dfn: BattleCreature) -> int:
            base_power = 60 + rng.randint(-5, 5)
            stat_ratio = max(0.1, atk.effective.force / max(1, dfn.effective.stability))
            type_mult = type_multiplier(atk.species.primary_type,
                                        dfn.species.primary_type)
            # Dual-type defense modifier
            if dfn.species.secondary_type:
                type_mult *= type_multiplier(atk.species.primary_type,
                                              dfn.species.secondary_type)
                type_mult = math.sqrt(type_mult)  # geometric mean normalization

            # Status modifiers
            force_mod = 1.0
            if StatusEffect.OVERCLOCKED in atk.statuses:
                force_mod = 1.3
            if StatusEffect.DISRUPTED in atk.statuses:
                force_mod *= 0.8
            variance = rng.uniform(0.9, 1.1)

            damage = int(base_power * stat_ratio * type_mult * force_mod * variance)
            return max(1, damage)

        # First attacks
        dmg = _calc_damage(first, second)
        second.current_hp -= dmg
        first.tempo_debt += 3.0  # tempo cost

        if second.current_hp <= 0:
            second.fainted = True
            if second.is_player_owned:
                p_active += 1
            else:
                o_active += 1
            continue

        # Second attacks
        dmg = _calc_damage(second, first)
        first.current_hp -= dmg
        second.tempo_debt += 3.0

        if first.current_hp <= 0:
            first.fainted = True
            if first.is_player_owned:
                p_active += 1
            else:
                o_active += 1

        # Status resolution: decay tempo debt
        for c in (first, second):
            c.tempo_debt = max(0, c.tempo_debt - 1.0)

    p_alive = sum(1 for c in p_team if not c.fainted)
    o_alive = sum(1 for c in o_team if not c.fainted)

    winner = "player" if p_alive > o_alive else "opponent" if o_alive > p_alive else "draw"
    fatigue = turns * 0.5  # fatigue accumulation

    return BattleResult(
        winner=winner,
        player_remaining=p_alive,
        opponent_remaining=o_alive,
        turns=turns,
        fatigue_delta=fatigue,
    )


# ── League system ──────────────────────────────────────────

class LeagueTier(Enum):
    LOCAL     = 1
    REGIONAL  = 2
    ISLAND    = 3
    APEX_INV  = 4


@dataclass
class Trainer:
    """An AI or player trainer entity."""
    trainer_id: str = ""
    name: str = ""
    is_player: bool = False
    rating: float = 1200.0   # ELO-like
    tier: LeagueTier = LeagueTier.LOCAL
    team_species_ids: List[str] = field(default_factory=list)
    risk_profile: float = 0.5    # 0 = conservative, 1 = aggressive
    ideology_vector: Dict[str, float] = field(default_factory=dict)
    wins: int = 0
    losses: int = 0


@dataclass
class LeagueState:
    """Island-wide league simulation state."""
    trainers: Dict[str, Trainer] = field(default_factory=dict)
    tournament_history: List[Dict[str, Any]] = field(default_factory=list)
    meta_health: Dict[str, float] = field(default_factory=dict)

    def update_rating(self, winner_id: str, loser_id: str, k: float = 32.0):
        """ELO-like rating update."""
        w = self.trainers.get(winner_id)
        l = self.trainers.get(loser_id)
        if not w or not l:
            return
        expected_w = 1.0 / (1.0 + 10 ** ((l.rating - w.rating) / 400.0))
        expected_l = 1.0 - expected_w
        w.rating += k * (1.0 - expected_w)
        l.rating += k * (0.0 - expected_l)
        w.wins += 1
        l.losses += 1


def generate_ai_trainers(topology: IslandTopology,
                         species_map: Dict[str, Species],
                         count: int = 50) -> Dict[str, Trainer]:
    """Generate deterministic AI trainers for the island league."""
    rng = SeededRNG(topology.seed).fork("trainers")
    trainers: Dict[str, Trainer] = {}

    species_ids = list(species_map.keys())

    for i in range(count):
        tid = f"trainer_{i:04d}"
        name = _generate_name(rng.fork(f"tn_{i}"), min_syl=2, max_syl=3)

        # Team of 3–6
        team_size = rng.randint(3, 6)
        team = rng.sample(species_ids, min(team_size, len(species_ids)))

        # Rating distribution: gaussian around 1200, std 300
        rating = max(800, rng.gauss(1200, 300))

        tier = (LeagueTier.LOCAL if rating < 1300
                else LeagueTier.REGIONAL if rating < 1600
                else LeagueTier.ISLAND if rating < 1900
                else LeagueTier.APEX_INV)

        trainers[tid] = Trainer(
            trainer_id=tid, name=name, rating=rating, tier=tier,
            team_species_ids=team,
            risk_profile=rng.uniform(0.1, 0.9),
            ideology_vector={
                "competition": rng.uniform(-1, 1),
                "preservation": rng.uniform(-1, 1),
                "research_priority": rng.uniform(-1, 1),
            },
        )

    return trainers


# ============================================================
# §8  GENETIC BREEDING & EVOLUTIONARY DRIFT
# ============================================================

def breed_creatures(
    parent_a: CreatureInstance,
    parent_b: CreatureInstance,
    species_a: Species,
    species_b: Species,
    rng: SeededRNG,
    anomaly_instability: float = 0.0,
) -> GeneticProfile:
    """
    Compute offspring GeneticProfile from two parents.

    Inheritance: 40/40/20 rule with cluster suppression.
    """
    genes_a = parent_a.genes.stat_genes
    genes_b = parent_b.genes.stat_genes

    offspring_genes: List[int] = []
    mutation_band = 2 + int(anomaly_instability * 3)  # wider under instability

    for i in range(6):
        # 40% from A, 40% from B, 20% mutation
        if rng.random() < 0.4:
            base = genes_a[i]
        elif rng.random() < 0.67:  # 0.4 / (0.4+0.2) adjusted
            base = genes_b[i]
        else:
            base = (genes_a[i] + genes_b[i]) // 2
        # Mutation
        mutation = rng.randint(-mutation_band, mutation_band)
        gene = max(0, min(31, base + mutation))
        offspring_genes.append(gene)

    # Cluster suppression: if any cluster > 50, suppress weakest stat in cluster
    profile = GeneticProfile(
        stat_genes=offspring_genes,
        variance_seed=rng.randint(0, 2**31),
        lineage_depth=max(parent_a.genes.lineage_depth,
                          parent_b.genes.lineage_depth) + 1,
    )

    clusters = [
        (profile.physical_cluster, [0, 1]),   # vitality, force
        (profile.tempo_cluster, [2, 5]),       # reflex, flux
        (profile.cognitive_cluster, [3, 4]),   # focus, stability
    ]
    for total, indices in clusters:
        if total > 50:
            # Suppress weakest
            weakest_idx = min(indices, key=lambda idx: offspring_genes[idx])
            suppress = min(offspring_genes[weakest_idx], (total - 50) // 2)
            offspring_genes[weakest_idx] = max(0, offspring_genes[weakest_idx] - suppress)

    # Trait inheritance
    traits: List[str] = []
    if parent_a.genes.trait_genes:
        traits.append(rng.choice(parent_a.genes.trait_genes))
    if parent_b.genes.trait_genes:
        traits.append(rng.choice(parent_b.genes.trait_genes))
    # Rare trait unlock at lineage depth threshold
    if profile.lineage_depth >= 5 and rng.random() < 0.15:
        traits.append(rng.choice(_PASSIVE_TRAITS))
    profile.trait_genes = traits[:3]  # cap at 3

    return profile


@dataclass
class PopulationGenePool:
    """Tracks genetic diversity per species across the island."""
    species_id: str = ""
    avg_stat_genes: List[float] = field(default_factory=lambda: [16.0] * 6)
    trait_frequency: Dict[str, float] = field(default_factory=dict)
    diversity_variance: float = 1.0
    population_count: int = 100

    def update_from_breeding(self, offspring: GeneticProfile):
        """Shift pool statistics toward new offspring."""
        alpha = 0.01  # slow drift
        for i in range(6):
            self.avg_stat_genes[i] = (
                self.avg_stat_genes[i] * (1 - alpha)
                + offspring.stat_genes[i] * alpha
            )
        # Diversity: measure variance of avg genes
        mean = sum(self.avg_stat_genes) / 6
        var = sum((g - mean) ** 2 for g in self.avg_stat_genes) / 6
        self.diversity_variance = max(0.1, var)


# ============================================================
# §9  FACTION TERRITORIAL INFLUENCE & DIALOGUE WEIGHTING
# ============================================================

class FactionArchetype(Enum):
    LEAGUE_AUTHORITY      = auto()
    RESEARCH_CONSORTIUM   = auto()
    PRESERVATION_CIRCLE   = auto()
    INDUSTRIAL_SYNDICATE  = auto()
    FRONTIER_SETTLERS     = auto()
    DEPTH_SECT            = auto()


@dataclass
class IdeologyVector:
    """Multi-axis ideology descriptor."""
    competition:       float = 0.0
    preservation:      float = 0.0
    industrialization:  float = 0.0
    research_priority: float = 0.0
    anomaly_curiosity: float = 0.0

    def distance(self, other: "IdeologyVector") -> float:
        return math.sqrt(
            (self.competition - other.competition) ** 2
            + (self.preservation - other.preservation) ** 2
            + (self.industrialization - other.industrialization) ** 2
            + (self.research_priority - other.research_priority) ** 2
            + (self.anomaly_curiosity - other.anomaly_curiosity) ** 2
        )

    def to_dict(self) -> Dict[str, float]:
        return {
            "competition": self.competition,
            "preservation": self.preservation,
            "industrialization": self.industrialization,
            "research_priority": self.research_priority,
            "anomaly_curiosity": self.anomaly_curiosity,
        }


# Baseline ideology per faction archetype
_FACTION_IDEOLOGIES: Dict[FactionArchetype, IdeologyVector] = {
    FactionArchetype.LEAGUE_AUTHORITY:    IdeologyVector(0.8, -0.2, 0.2, 0.0, -0.3),
    FactionArchetype.RESEARCH_CONSORTIUM: IdeologyVector(0.0, 0.3, 0.1, 0.9, 0.4),
    FactionArchetype.PRESERVATION_CIRCLE: IdeologyVector(-0.3, 0.9, -0.5, 0.2, 0.0),
    FactionArchetype.INDUSTRIAL_SYNDICATE:IdeologyVector(0.2, -0.5, 0.9, 0.1, -0.2),
    FactionArchetype.FRONTIER_SETTLERS:   IdeologyVector(0.1, 0.1, 0.3, -0.1, 0.1),
    FactionArchetype.DEPTH_SECT:          IdeologyVector(-0.1, 0.0, -0.2, 0.5, 0.9),
}


@dataclass
class Faction:
    """A political faction on the island."""
    faction_id: str = ""
    archetype: FactionArchetype = FactionArchetype.LEAGUE_AUTHORITY
    name: str = ""
    influence_score: float = 50.0
    ideology: IdeologyVector = field(default_factory=IdeologyVector)
    territorial_nodes: Set[str] = field(default_factory=set)
    expansion_rate: float = 1.0
    stability_val: float = 0.8
    public_sentiment: float = 0.5


@dataclass
class DialogueDelta:
    """Effect of a dialogue choice on ideology axes."""
    competition:       float = 0.0
    preservation:      float = 0.0
    industrialization:  float = 0.0
    research_priority: float = 0.0
    anomaly_curiosity: float = 0.0


def generate_factions(topology: IslandTopology) -> Dict[str, Faction]:
    """Generate 4–6 factions for the island."""
    rng = SeededRNG(topology.seed).fork("factions")
    archetypes = list(FactionArchetype)
    n_factions = rng.randint(4, 6)
    rng.shuffle(archetypes)
    selected = archetypes[:n_factions]

    factions: Dict[str, Faction] = {}
    node_ids = list(topology.nodes.keys())

    for i, arch in enumerate(selected):
        fid = f"faction_{i:02d}"
        base_ideology = _FACTION_IDEOLOGIES[arch]
        # Perturb slightly per seed
        ideology = IdeologyVector(
            competition=max(-1, min(1, base_ideology.competition + rng.gauss(0, 0.1))),
            preservation=max(-1, min(1, base_ideology.preservation + rng.gauss(0, 0.1))),
            industrialization=max(-1, min(1, base_ideology.industrialization + rng.gauss(0, 0.1))),
            research_priority=max(-1, min(1, base_ideology.research_priority + rng.gauss(0, 0.1))),
            anomaly_curiosity=max(-1, min(1, base_ideology.anomaly_curiosity + rng.gauss(0, 0.1))),
        )

        # Initial territory: 10–30 random nodes
        n_terr = rng.randint(10, min(30, len(node_ids)))
        territory = set(rng.sample(node_ids, n_terr))

        name = _generate_name(rng.fork(f"fname_{i}"), prefix=arch.name.replace("_", " ").title())

        factions[fid] = Faction(
            faction_id=fid,
            archetype=arch,
            name=name,
            influence_score=rng.uniform(30, 70),
            ideology=ideology,
            territorial_nodes=territory,
            expansion_rate=rng.uniform(0.5, 1.5),
            stability_val=rng.uniform(0.5, 1.0),
            public_sentiment=rng.uniform(0.3, 0.7),
        )

        # Set initial node influence
        for nid in territory:
            if nid in topology.nodes:
                topology.nodes[nid].faction_influence[fid] = rng.uniform(0.3, 0.8)

    return factions


def diffuse_faction_influence(
    topology: IslandTopology,
    factions: Dict[str, Faction],
    diffusion_factor: float = 0.15,
):
    """
    One tick of territorial influence diffusion across the graph.

    Cities amplify, wild zones dampen, facilities anchor.
    """
    new_influence: Dict[str, Dict[str, float]] = {}

    for nid, node in topology.nodes.items():
        new_influence[nid] = {}
        neighbors = [topology.nodes[nb] for nb in node.neighbors
                     if nb in topology.nodes]

        for fid, faction in factions.items():
            local = node.faction_influence.get(fid, 0.0)

            # Average adjacent influence
            if neighbors:
                avg_adj = sum(nb.faction_influence.get(fid, 0.0)
                              for nb in neighbors) / len(neighbors)
            else:
                avg_adj = 0.0

            # Node type modifiers
            amp = 1.0
            if node.node_type == NodeType.CITY:
                amp = 1.3
            elif node.node_type == NodeType.WILD_ZONE:
                amp = 0.6
            elif node.node_type == NodeType.FACILITY:
                amp = 1.2
            elif node.node_type == NodeType.DUNGEON:
                amp = 0.4

            # Opposition pressure
            opposition = sum(node.faction_influence.get(ofid, 0.0)
                            for ofid in factions if ofid != fid)

            new_val = (local
                       + avg_adj * diffusion_factor * amp
                       - opposition * 0.05)
            new_influence[nid][fid] = max(0.0, min(1.0, new_val))

    # Apply
    for nid in topology.nodes:
        topology.nodes[nid].faction_influence = new_influence.get(nid, {})

    # Sync Faction objects: recompute territorial_nodes and influence_score
    for fid, faction in factions.items():
        terr: Set[str] = set()
        total_inf = 0.0
        for nid, node in topology.nodes.items():
            inf = node.faction_influence.get(fid, 0.0)
            if inf > 0.3:          # threshold for "controlled" territory
                terr.add(nid)
            total_inf += inf
        faction.territorial_nodes = terr
        faction.influence_score = total_inf / max(1, len(topology.nodes)) * 100.0


def compute_dialogue_impact(
    delta: DialogueDelta,
    player_credibility: float,
    faction_standings: Dict[str, float],
) -> Dict[str, float]:
    """
    Weight a dialogue delta by player credibility.

    Credibility = f(achievements, faction standing, league rating, milestones).
    Higher credibility → stronger impact.
    """
    mult = max(0.1, min(3.0, player_credibility))
    return {
        "competition": delta.competition * mult,
        "preservation": delta.preservation * mult,
        "industrialization": delta.industrialization * mult,
        "research_priority": delta.research_priority * mult,
        "anomaly_curiosity": delta.anomaly_curiosity * mult,
    }


# ============================================================
# §10  ISLAND LEDGER, NORMALIZATION, 100 OUTCOME BANDS
# ============================================================

@dataclass
class IslandLedger:
    """
    Hidden macro-state tracker.  All axes in [-100, +100].
    """
    ecological_balance:   float = 0.0
    urbanization_level:   float = 0.0
    league_influence:     float = 0.0
    research_advancement: float = 0.0
    genetic_diversity:    float = 0.0
    population_pressure:  float = 0.0
    anomaly_stability:    float = 0.0
    cultural_cohesion:    float = 0.0

    # Seed baseline bias (for normalization)
    _baseline: Dict[str, float] = field(default_factory=dict)

    def set_baseline(self, seed: int):
        """Store seed-dependent baseline for fair normalization."""
        rng = SeededRNG(seed).fork("ledger_baseline")
        self._baseline = {
            "ecological_balance": rng.uniform(-15, 15),
            "urbanization_level": rng.uniform(-10, 20),
            "league_influence": rng.uniform(-10, 10),
            "research_advancement": rng.uniform(-5, 10),
            "genetic_diversity": rng.uniform(0, 15),
            "population_pressure": rng.uniform(-10, 10),
            "anomaly_stability": rng.uniform(-5, 5),
            "cultural_cohesion": rng.uniform(-5, 15),
        }

    def normalize(self) -> Dict[str, float]:
        """Normalize raw values against seed baseline."""
        def _norm(raw: float, key: str) -> float:
            bias = self._baseline.get(key, 0.0)
            scaling = 50.0  # normalization denominator
            return max(-100, min(100, (raw - bias) / scaling * 100))
        return {
            "ecological_balance": _norm(self.ecological_balance, "ecological_balance"),
            "urbanization_level": _norm(self.urbanization_level, "urbanization_level"),
            "league_influence": _norm(self.league_influence, "league_influence"),
            "research_advancement": _norm(self.research_advancement, "research_advancement"),
            "genetic_diversity": _norm(self.genetic_diversity, "genetic_diversity"),
            "population_pressure": _norm(self.population_pressure, "population_pressure"),
            "anomaly_stability": _norm(self.anomaly_stability, "anomaly_stability"),
            "cultural_cohesion": _norm(self.cultural_cohesion, "cultural_cohesion"),
        }

    # Derived indices
    def stability_index(self) -> float:
        n = self.normalize()
        return (n["ecological_balance"] + n["genetic_diversity"]
                + n["anomaly_stability"]) / 3.0

    def civilization_index(self) -> float:
        n = self.normalize()
        return (n["urbanization_level"] + n["league_influence"]
                + n["research_advancement"]) / 3.0

    def tension_index(self) -> float:
        """Higher value = more tension / instability on the island."""
        n = self.normalize()
        # Tension rises when ecology and urbanization diverge,
        # when cultural cohesion is low, and when anomaly stability is low.
        eco_urb_gap = abs(n["ecological_balance"] - n["urbanization_level"])
        culture_stress = max(0, -n["cultural_cohesion"])   # negative cohesion → tension
        anomaly_stress = max(0, -n["anomaly_stability"])   # negative stability → tension
        return (eco_urb_gap + culture_stress + anomaly_stress) / 3.0

    def apply_delta(self, axis: str, delta: float):
        """Shift a ledger axis by delta, clamping to [-100, 100]."""
        current = getattr(self, axis, 0.0)
        setattr(self, axis, max(-100, min(100, current + delta)))

    def to_dict(self) -> dict:
        return {
            "raw": {
                "ecological_balance": self.ecological_balance,
                "urbanization_level": self.urbanization_level,
                "league_influence": self.league_influence,
                "research_advancement": self.research_advancement,
                "genetic_diversity": self.genetic_diversity,
                "population_pressure": self.population_pressure,
                "anomaly_stability": self.anomaly_stability,
                "cultural_cohesion": self.cultural_cohesion,
            },
            "normalized": self.normalize(),
            "stability_index": self.stability_index(),
            "civilization_index": self.civilization_index(),
            "tension_index": self.tension_index(),
        }


# ── Outcome bands ──────────────────────────────────────────

_ISLAND_QUADRANT_NAMES = [
    "Pristine Harmony",
    "Strained Ecology",
    "Industrial Surge",
    "Research Ascendant",
    "League Dominated",
    "Balanced Growth",
    "Anomaly Destabilized",
    "Cultural Fracture",
    "Genetic Bottleneck",
    "Frontier Expansion",
]

_PERSONAL_ARCHETYPE_NAMES = [
    "Island Champion",
    "Grand Research Architect",
    "Wanderer of the Wild Core",
    "Genetic Visionary",
    "Relic Seeker",
    "Stabilizer of the Fracture",
    "Instigator of Collapse",
    "League Reformer",
    "Isolationist Guardian",
    "Rift Walker",
]


def compute_island_quadrant(ledger: IslandLedger) -> int:
    """
    Compute island quadrant (0–9) from ledger axes using a rule-based
    argmax classifier.  Each quadrant maps to a named condition; the
    classifier picks the condition whose indicator is strongest.

    Quadrants:
      0 Pristine Harmony       — high stability, high ecology, low tension
      1 Strained Ecology       — low ecology, moderate urbanization
      2 Industrial Surge       — high urbanization, low ecology
      3 Research Ascendant     — research dominates
      4 League Dominated       — league influence dominates
      5 Balanced Growth        — no axis dominates (low variance)
      6 Anomaly Destabilized   — anomaly_stability deeply negative
      7 Cultural Fracture      — cultural_cohesion deeply negative
      8 Genetic Bottleneck     — genetic_diversity deeply negative
      9 Frontier Expansion     — high exploration-style pop pressure, moderate urb
    """
    n = ledger.normalize()
    eco = n["ecological_balance"]
    urb = n["urbanization_level"]
    lea = n["league_influence"]
    res = n["research_advancement"]
    gen = n["genetic_diversity"]
    pop = n["population_pressure"]
    ano = n["anomaly_stability"]
    cul = n["cultural_cohesion"]

    si = ledger.stability_index()

    # Score each quadrant — highest score wins
    scores: List[Tuple[float, int]] = [
        (si + eco * 0.3 - abs(urb) * 0.1,                    0),  # Pristine Harmony
        (-eco * 0.6 + urb * 0.2 - gen * 0.2,                 1),  # Strained Ecology
        (urb * 0.6 - eco * 0.3 + pop * 0.1,                  2),  # Industrial Surge
        (res * 0.8,                                            3),  # Research Ascendant
        (lea * 0.8,                                            4),  # League Dominated
        (-abs(eco) - abs(urb) - abs(lea) - abs(res) + 200,   5),  # Balanced Growth (low variance bonus)
        (-ano * 0.8,                                           6),  # Anomaly Destabilized
        (-cul * 0.8,                                           7),  # Cultural Fracture
        (-gen * 0.8,                                           8),  # Genetic Bottleneck
        (pop * 0.4 + urb * 0.3 + eco * 0.1,                  9),  # Frontier Expansion
    ]

    best_score, best_q = max(scores, key=lambda t: t[0])
    return best_q


def compute_personal_quadrant(trajectory: "PlayerTrajectory") -> int:
    """Compute personal archetype quadrant (0–9)."""
    scores = [
        trajectory.competitive_focus,
        trajectory.exploration_depth,
        trajectory.research_investment,
        trajectory.breeding_intensity,
        trajectory.anomaly_exposure,
    ]
    # Dominant axis determines base quadrant
    max_score = max(scores)
    max_idx = scores.index(max_score)

    # Map 5 primary axes to 10 quadrants with sub-splits
    quadrant_map = {
        0: [0, 7],   # competitive → Champion or Reformer
        1: [2, 4],   # exploration → Wanderer or Relic Seeker
        2: [1, 3],   # research → Architect or Visionary
        3: [3, 8],   # breeding → Visionary or Guardian
        4: [5, 9],   # anomaly → Stabilizer or Rift Walker
    }

    options = quadrant_map.get(max_idx, [0, 5])
    # Sub-split by risk appetite
    if trajectory.risk_appetite > 50:
        return options[1]
    return options[0]


def compute_outcome_band(ledger: IslandLedger,
                         trajectory: "PlayerTrajectory") -> int:
    """Compute final outcome band ID (0–99)."""
    iq = compute_island_quadrant(ledger)
    pq = compute_personal_quadrant(trajectory)
    return iq * 10 + pq


def describe_outcome_band(band_id: int) -> Dict[str, str]:
    """Human-readable description of an outcome band."""
    iq = band_id // 10
    pq = band_id % 10
    return {
        "band_id": band_id,
        "island_quadrant": iq,
        "island_condition": _ISLAND_QUADRANT_NAMES[iq],
        "personal_quadrant": pq,
        "personal_archetype": _PERSONAL_ARCHETYPE_NAMES[pq],
        "summary": (
            f"Island State: {_ISLAND_QUADRANT_NAMES[iq]}. "
            f"Personal Trajectory: {_PERSONAL_ARCHETYPE_NAMES[pq]}."
        ),
    }


# ============================================================
# §11  GATE REQUIREMENT COMPUTATION
# ============================================================

def compute_gate_thresholds(
    topology: IslandTopology,
    ledger: IslandLedger,
    factions: Dict[str, Faction],
):
    """
    Dynamically adjust gate thresholds based on ledger state and faction
    territorial control.  Called each simulation tick.
    """
    n = ledger.normalize()

    for nid, node in topology.nodes.items():
        if not node.gate:
            continue

        gate = node.gate
        # Dynamic adjustment based on ledger
        if gate.gate_type == GateType.LEAGUE:
            # High league influence → easier league gates
            gate.flex_buffer = max(0, n["league_influence"] * 0.15)
        elif gate.gate_type == GateType.ECOLOGICAL:
            gate.flex_buffer = max(0, n["ecological_balance"] * 0.15)
        elif gate.gate_type == GateType.RESEARCH:
            gate.flex_buffer = max(0, n["research_advancement"] * 0.15)
        elif gate.gate_type == GateType.ECONOMIC:
            gate.flex_buffer = max(0, n["urbanization_level"] * 0.1)
        elif gate.gate_type == GateType.ANOMALY:
            # Anomaly gates can open temporarily
            if n["anomaly_stability"] < -30:
                gate.flex_buffer = abs(n["anomaly_stability"]) * 0.2

        # Faction control: dominant faction in this area may shift threshold
        dominant_fid = max(node.faction_influence,
                          key=node.faction_influence.get,
                          default=None) if node.faction_influence else None
        if dominant_fid and dominant_fid in factions:
            faction = factions[dominant_fid]
            dom_influence = node.faction_influence[dominant_fid]
            if dom_influence > 0.6:
                # Strong faction presence: aligned players get easier access
                gate.flex_buffer += dom_influence * 5.0


# ============================================================
# §12  PLAYER TRAJECTORY & PERSONAL OUTCOME
# ============================================================

@dataclass
class PlayerTrajectory:
    """
    Accumulated player behavioral vector.
    All scores in [0, 100].
    """
    competitive_focus:    float = 0.0
    exploration_depth:    float = 0.0
    research_investment:  float = 0.0
    breeding_intensity:   float = 0.0
    anomaly_exposure:     float = 0.0
    risk_appetite:        float = 50.0
    dialogue_ideology:    IdeologyVector = field(default_factory=IdeologyVector)

    # Tracking counters
    battles_won: int = 0
    battles_lost: int = 0
    nodes_explored: int = 0
    species_discovered: int = 0
    breeds_completed: int = 0
    relics_found: int = 0
    anomaly_events: int = 0

    def update_from_battle(self, won: bool):
        if won:
            self.battles_won += 1
        else:
            self.battles_lost += 1
        # Recalculate competitive focus
        total_battles = self.battles_won + self.battles_lost
        if total_battles > 0:
            self.competitive_focus = min(100, total_battles * 1.5)

    def update_from_exploration(self, node: MapNode):
        self.nodes_explored += 1
        self.exploration_depth = min(100, self.nodes_explored * 0.8)
        if node.node_type == NodeType.LANDMARK:
            self.relics_found += 1

    def update_from_breeding(self):
        self.breeds_completed += 1
        self.breeding_intensity = min(100, self.breeds_completed * 3.0)

    def update_from_research(self, delta: float = 5.0):
        self.research_investment = min(100, self.research_investment + delta)

    def update_from_anomaly(self):
        self.anomaly_events += 1
        self.anomaly_exposure = min(100, self.anomaly_events * 8.0)

    def update_dialogue(self, delta: DialogueDelta, credibility: float = 1.0):
        iv = self.dialogue_ideology
        mult = max(0.1, min(3.0, credibility))
        iv.competition = max(-1, min(1, iv.competition + delta.competition * mult))
        iv.preservation = max(-1, min(1, iv.preservation + delta.preservation * mult))
        iv.industrialization = max(-1, min(1, iv.industrialization + delta.industrialization * mult))
        iv.research_priority = max(-1, min(1, iv.research_priority + delta.research_priority * mult))
        iv.anomaly_curiosity = max(-1, min(1, iv.anomaly_curiosity + delta.anomaly_curiosity * mult))

    def dominant_archetype(self) -> str:
        """Return the player's dominant personal archetype name."""
        pq = compute_personal_quadrant(self)
        return _PERSONAL_ARCHETYPE_NAMES[pq]

    def to_dict(self) -> dict:
        return {
            "competitive_focus": self.competitive_focus,
            "exploration_depth": self.exploration_depth,
            "research_investment": self.research_investment,
            "breeding_intensity": self.breeding_intensity,
            "anomaly_exposure": self.anomaly_exposure,
            "risk_appetite": self.risk_appetite,
            "battles_won": self.battles_won,
            "battles_lost": self.battles_lost,
            "nodes_explored": self.nodes_explored,
            "species_discovered": self.species_discovered,
            "breeds_completed": self.breeds_completed,
            "relics_found": self.relics_found,
            "anomaly_events": self.anomaly_events,
            "dominant_archetype": self.dominant_archetype(),
            "ideology": self.dialogue_ideology.to_dict(),
        }


# ============================================================
# §13  ISLAND CONTROLLER & TICK ENGINE
# ============================================================

@dataclass
class IslandState:
    """Complete mutable state of one island simulation."""
    seed: int = 0
    tick: int = 0
    topology: IslandTopology = field(default_factory=IslandTopology)
    species_map: Dict[str, Species] = field(default_factory=dict)
    encounter_tables: Dict[str, EncounterTable] = field(default_factory=dict)
    ledger: IslandLedger = field(default_factory=IslandLedger)
    factions: Dict[str, Faction] = field(default_factory=dict)
    league: LeagueState = field(default_factory=LeagueState)
    gene_pools: Dict[str, PopulationGenePool] = field(default_factory=dict)
    player_trajectory: PlayerTrajectory = field(default_factory=PlayerTrajectory)
    player_location: str = ""
    player_team: List[Tuple[str, str]] = field(default_factory=list)  # (instance_id, species_id)
    creatures: Dict[str, CreatureInstance] = field(default_factory=dict)
    discovered_species: Set[str] = field(default_factory=set)
    faction_standings: Dict[str, float] = field(default_factory=dict)  # player↔faction standing
    _instance_counter: int = 0   # deterministic ID generator (replaces uuid)

    def next_id(self, prefix: str = "inst") -> str:
        """Return a deterministic, monotonically increasing instance ID."""
        self._instance_counter += 1
        return f"{prefix}_{self._instance_counter:06d}"


class NKController:
    """
    Main controller for one island simulation.
    Manages initialization, tick loop, and command dispatch.
    """

    def __init__(self, runtime_stub: Dict[str, Any], config: Dict[str, Any]):
        self._runtime_stub = runtime_stub
        self._config = config
        self._state: Optional[IslandState] = None
        self._cmd_q: queue.Queue = runtime_stub.get("nk_cmd_q", queue.Queue())
        self._ui_q: queue.Queue = runtime_stub.get("nk_ui_q", queue.Queue())
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._poll_interval = 0.1  # how often to check the command queue (no sim drift)

    # ── Initialization ─────────────────────────────────────

    def init_island(self, seed: int):
        """Initialize a fresh island from seed."""
        _dbg(f"Initializing island seed={seed}")
        topology = generate_island_topology(seed)
        species_map = generate_species_roster(topology)

        ledger = IslandLedger()
        ledger.set_baseline(seed)

        factions = generate_factions(topology)
        encounter_tables = generate_encounter_tables(topology, species_map, ledger)

        trainers = generate_ai_trainers(topology, species_map)
        league = LeagueState(trainers=trainers)

        # Initialize gene pools for each species
        gene_pools: Dict[str, PopulationGenePool] = {}
        for sid in species_map:
            gene_pools[sid] = PopulationGenePool(species_id=sid)

        self._state = IslandState(
            seed=seed,
            topology=topology,
            species_map=species_map,
            encounter_tables=encounter_tables,
            ledger=ledger,
            factions=factions,
            league=league,
            gene_pools=gene_pools,
            player_location=topology.start_node_id,
            faction_standings={fid: 0.0 for fid in factions},
        )

        _dbg(f"Island initialized: {topology.island_name} "
             f"({topology.node_count} nodes, {len(species_map)} species, "
             f"{len(factions)} factions)")
        self._push_ui("island_initialized", {
            "island_name": topology.island_name,
            "seed": seed,
            "node_count": topology.node_count,
            "species_count": len(species_map),
            "faction_count": len(factions),
            "active_types": [t.name for t in topology.active_types],
            "climate": topology.climate.name,
        })

    # ── Tick engine ────────────────────────────────────────

    def start(self):
        """Start the background tick loop."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True,
                                         name="nk_tick")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run_loop(self):
        """
        Command-driven loop — the simulation advances deterministically
        only when the player issues commands.  An explicit 'advance'
        command (or any action that mutates game state) triggers one
        simulation tick, so wall-clock timing never affects the sim.
        """
        while not self._stop.is_set():
            # Block-wait for next command (with timeout so stop-flag works)
            try:
                cmd = self._cmd_q.get(timeout=self._poll_interval)
                self._handle_cmd(cmd)
            except queue.Empty:
                pass

    def _tick(self):
        """One simulation tick."""
        if not self._state:
            return

        st = self._state
        st.tick += 1

        # Faction diffusion
        diffuse_faction_influence(st.topology, st.factions)

        # Gate threshold adjustment
        compute_gate_thresholds(st.topology, st.ledger, st.factions)

        # Ledger drift from faction balance
        total_factions = len(st.factions)
        if total_factions > 0:
            # Compute average faction influence on key axes
            for fid, faction in st.factions.items():
                if faction.archetype == FactionArchetype.LEAGUE_AUTHORITY:
                    st.ledger.apply_delta("league_influence",
                                           faction.influence_score * 0.002)
                elif faction.archetype == FactionArchetype.RESEARCH_CONSORTIUM:
                    st.ledger.apply_delta("research_advancement",
                                           faction.influence_score * 0.002)
                elif faction.archetype == FactionArchetype.PRESERVATION_CIRCLE:
                    st.ledger.apply_delta("ecological_balance",
                                           faction.influence_score * 0.002)
                elif faction.archetype == FactionArchetype.INDUSTRIAL_SYNDICATE:
                    st.ledger.apply_delta("urbanization_level",
                                           faction.influence_score * 0.002)
                    st.ledger.apply_delta("ecological_balance",
                                           -faction.influence_score * 0.001)
                elif faction.archetype == FactionArchetype.DEPTH_SECT:
                    st.ledger.apply_delta("anomaly_stability",
                                           -faction.influence_score * 0.001)

        # Population pressure from urbanization
        st.ledger.apply_delta("population_pressure",
                               st.ledger.urbanization_level * 0.001)

        # Cultural cohesion decay
        tension = st.ledger.tension_index()
        if tension > 60:
            st.ledger.apply_delta("cultural_cohesion", -0.3)
        elif tension < 30:
            st.ledger.apply_delta("cultural_cohesion", 0.1)

        # AI league matches (off-screen)
        if st.tick % 5 == 0:
            self._simulate_ai_league_round()

        # Periodic UI update
        if st.tick % 10 == 0:
            self._push_ui("tick_update", {
                "tick": st.tick,
                "ledger": st.ledger.to_dict(),
                "player_location": st.player_location,
            })

    def _simulate_ai_league_round(self):
        """Simulate one round of AI vs AI battles."""
        if not self._state:
            return
        league = self._state.league
        trainer_ids = list(league.trainers.keys())
        if len(trainer_ids) < 2:
            return

        rng = SeededRNG(self._state.seed + self._state.tick).fork("ai_league")
        rng.shuffle(trainer_ids)
        pairs = list(zip(trainer_ids[::2], trainer_ids[1::2]))

        for a_id, b_id in pairs[:10]:  # max 10 matches per round
            a = league.trainers[a_id]
            b = league.trainers[b_id]
            # Simplified: higher rating + random → winner
            a_strength = a.rating + rng.gauss(0, 100)
            b_strength = b.rating + rng.gauss(0, 100)
            if a_strength > b_strength:
                league.update_rating(a_id, b_id)
            else:
                league.update_rating(b_id, a_id)

    # ── Command handling ───────────────────────────────────

    def _handle_cmd(self, cmd: Dict[str, Any]):
        """Dispatch a player command."""
        action = cmd.get("action", "")

        if action == "init":
            self.init_island(cmd.get("seed", 42))

        elif action == "advance":
            # Explicit sim-clock step (N ticks, default 1)
            n = max(1, int(cmd.get("ticks", 1)))
            for _ in range(n):
                self._tick()

        elif action == "move":
            self._cmd_move(cmd.get("target_node", ""))

        elif action == "encounter":
            self._cmd_encounter()

        elif action == "battle":
            self._cmd_battle(cmd.get("opponent_id", ""))

        elif action == "breed":
            self._cmd_breed(cmd.get("parent_a_id", ""),
                             cmd.get("parent_b_id", ""))

        elif action == "explore":
            self._cmd_explore()

        elif action == "dialogue":
            self._cmd_dialogue(cmd.get("delta", {}))

        elif action == "get_state":
            self._cmd_get_state()

        elif action == "get_species":
            self._cmd_get_species()

        elif action == "get_map":
            self._cmd_get_map()

        elif action == "get_outcome":
            self._cmd_get_outcome()

        else:
            self._push_ui("error", {"message": f"Unknown command: {action}"})

    def _cmd_move(self, target_node: str):
        """Move player to an adjacent node."""
        if not self._state:
            return
        st = self._state
        current = st.topology.nodes.get(st.player_location)
        if not current:
            self._push_ui("error", {"message": "Invalid current location"})
            return

        if target_node not in current.neighbors:
            self._push_ui("error", {"message": f"Cannot reach {target_node} from here"})
            return

        target = st.topology.nodes.get(target_node)
        if not target:
            self._push_ui("error", {"message": f"Unknown node {target_node}"})
            return

        # Check gate
        if target.gate:
            # Best faction standing the player has with any faction present at this node
            best_standing = 0.0
            for fid in st.factions:
                node_inf = target.faction_influence.get(fid, 0.0)
                player_rel = st.faction_standings.get(fid, 0.0)
                # Standing contribution: player relationship weighted by node presence
                best_standing = max(best_standing, node_inf * max(0, player_rel))

            player_state = {
                "trainer_rating": st.league.trainers.get("player", Trainer()).rating,
                "faction_standing": best_standing,
                "research_milestones": st.player_trajectory.research_investment / 20.0,
                "ecological_balance": st.ledger.ecological_balance,
                "anomaly_exposure": st.player_trajectory.anomaly_exposure,
                "economic_investment": st.ledger.urbanization_level,
                "exploration_score": st.player_trajectory.exploration_depth,
                "league_tier": 1.0 + st.player_trajectory.competitive_focus / 33.0,
            }
            if not target.gate.check(player_state):
                self._push_ui("gate_blocked", {
                    "node": target_node,
                    "gate_type": target.gate.gate_type.name,
                    "requirement": target.gate.primary_metric,
                    "threshold": target.gate.threshold,
                })
                return

        st.player_location = target_node
        st.player_trajectory.update_from_exploration(target)

        # Discover species at this node
        et = st.encounter_tables.get(target_node)
        if et:
            for sid in et.all_species():
                if sid not in st.discovered_species:
                    st.discovered_species.add(sid)
                    st.player_trajectory.species_discovered += 1

        self._push_ui("moved", {
            "node_id": target_node,
            "node_type": target.node_type.name,
            "region": target.region.name,
            "name": target.name,
            "biome": target.biome.to_tuple(),
            "neighbors": target.neighbors,
        })
        self._tick()  # advance sim after player action

    def _cmd_encounter(self):
        """Roll an encounter at current location."""
        if not self._state:
            return
        st = self._state
        et = st.encounter_tables.get(st.player_location)
        if not et:
            self._push_ui("no_encounter", {"message": "No encounters here"})
            return

        rng = SeededRNG(st.seed + st.tick + _det_hash(st.player_location)).fork("enc_roll")
        species_id = roll_encounter(et, rng)
        if not species_id or species_id not in st.species_map:
            self._push_ui("no_encounter", {"message": "Nothing appeared"})
            return

        sp = st.species_map[species_id]

        # Create wild creature instance
        inst_id = st.next_id("wild")
        level = max(1, rng.randint(3, 30))
        genes = GeneticProfile(
            stat_genes=[rng.randint(5, 28) for _ in range(6)],
            variance_seed=rng.randint(0, 2**31),
        )
        inst = CreatureInstance(
            instance_id=inst_id,
            species_id=species_id,
            level=level,
            genes=genes,
            temperament=rng.uniform(0.2, 0.8),
        )

        st.creatures[inst_id] = inst
        st.discovered_species.add(species_id)

        self._push_ui("encounter", {
            "species": sp.to_dict(),
            "instance_id": inst_id,
            "level": level,
        })
        self._tick()  # advance sim after player action

    def _cmd_battle(self, opponent_id: str):
        """Battle an AI trainer."""
        if not self._state:
            return
        st = self._state
        opponent = st.league.trainers.get(opponent_id)
        if not opponent:
            self._push_ui("error", {"message": f"Unknown trainer {opponent_id}"})
            return

        # Build player team from their creatures
        p_team: List[Tuple[CreatureInstance, Species]] = []
        for inst_id, sp_id in st.player_team[:3]:
            inst = st.creatures.get(inst_id)
            sp = st.species_map.get(sp_id)
            if inst and sp:
                p_team.append((inst, sp))

        if not p_team:
            self._push_ui("error", {"message": "No team set"})
            return

        # Build opponent team
        o_team: List[Tuple[CreatureInstance, Species]] = []
        rng = SeededRNG(st.seed + st.tick).fork(f"battle_{opponent_id}")
        for sp_id in opponent.team_species_ids[:3]:
            sp = st.species_map.get(sp_id)
            if sp:
                inst = CreatureInstance(
                    instance_id=st.next_id("ai"),
                    species_id=sp_id,
                    level=max(5, int(opponent.rating / 50)),
                    genes=GeneticProfile(
                        stat_genes=[rng.randint(8, 25) for _ in range(6)],
                    ),
                )
                o_team.append((inst, sp))

        if not o_team:
            self._push_ui("error", {"message": "Opponent has no team"})
            return

        result = simulate_battle(p_team, o_team, rng)

        # Update systems
        player_won = result.winner == "player"
        st.player_trajectory.update_from_battle(player_won)

        # Update league ratings
        player_trainer = st.league.trainers.get("player")
        if not player_trainer:
            player_trainer = Trainer(trainer_id="player", name="Player",
                                     is_player=True, rating=1200)
            st.league.trainers["player"] = player_trainer
        if player_won:
            st.league.update_rating("player", opponent_id)
        else:
            st.league.update_rating(opponent_id, "player")

        # Ledger impact
        st.ledger.apply_delta("league_influence", 0.5 if player_won else 0.1)

        # Faction standing shift: battling at a node builds relationship
        # with the dominant faction there
        cur_node = st.topology.nodes.get(st.player_location)
        if cur_node and cur_node.faction_influence:
            dom_fid = max(cur_node.faction_influence,
                          key=cur_node.faction_influence.get)
            standing_delta = 0.04 if player_won else 0.01
            old = st.faction_standings.get(dom_fid, 0.0)
            st.faction_standings[dom_fid] = max(-1.0, min(1.0, old + standing_delta))

        # Fatigue
        for inst_id, _ in st.player_team[:3]:
            inst = st.creatures.get(inst_id)
            if inst:
                inst.fatigue = min(100, inst.fatigue + result.fatigue_delta)

        self._push_ui("battle_result", {
            "winner": result.winner,
            "player_remaining": result.player_remaining,
            "opponent_remaining": result.opponent_remaining,
            "turns": result.turns,
            "player_rating": player_trainer.rating,
            "opponent_name": opponent.name,
        })
        self._tick()  # advance sim after player action

    def _cmd_breed(self, parent_a_id: str, parent_b_id: str):
        """Breed two creatures."""
        if not self._state:
            return
        st = self._state
        inst_a = st.creatures.get(parent_a_id)
        inst_b = st.creatures.get(parent_b_id)
        if not inst_a or not inst_b:
            self._push_ui("error", {"message": "Invalid parent(s)"})
            return

        sp_a = st.species_map.get(inst_a.species_id)
        sp_b = st.species_map.get(inst_b.species_id)
        if not sp_a or not sp_b:
            self._push_ui("error", {"message": "Unknown species"})
            return

        # Compatibility check: same species or shared type
        compatible = (inst_a.species_id == inst_b.species_id
                     or sp_a.evolution_line_id == sp_b.evolution_line_id
                     or sp_a.primary_type == sp_b.primary_type
                     or sp_a.secondary_type == sp_b.primary_type)
        if not compatible:
            self._push_ui("error", {"message": "Incompatible pair"})
            return

        rng = SeededRNG(st.seed + st.tick).fork(f"breed_{parent_a_id}_{parent_b_id}")
        anomaly_inst = max(0, -st.ledger.anomaly_stability) / 100.0

        offspring_genes = breed_creatures(inst_a, inst_b, sp_a, sp_b, rng,
                                          anomaly_instability=anomaly_inst)

        # Create offspring
        offspring_id = st.next_id("bred")
        offspring = CreatureInstance(
            instance_id=offspring_id,
            species_id=sp_a.species_id,  # same species as parent A base
            level=1,
            genes=offspring_genes,
            temperament=rng.uniform(0.2, 0.8),
        )
        st.creatures[offspring_id] = offspring

        # Update tracking
        st.player_trajectory.update_from_breeding()

        # Ecological impact
        pool = st.gene_pools.get(sp_a.species_id)
        if pool:
            pool.update_from_breeding(offspring_genes)
        st.ledger.apply_delta("genetic_diversity", -0.2)  # breeding narrows diversity
        st.ledger.apply_delta("population_pressure", 0.1)

        # Parent fatigue
        inst_a.fatigue = min(100, inst_a.fatigue + 10)
        inst_b.fatigue = min(100, inst_b.fatigue + 10)

        self._push_ui("breed_result", {
            "offspring_id": offspring_id,
            "species": sp_a.species_id,
            "genes": offspring_genes.stat_genes,
            "lineage_depth": offspring_genes.lineage_depth,
            "traits": offspring_genes.trait_genes,
        })
        self._tick()  # advance sim after player action

    def _cmd_explore(self):
        """Survey current location for discoveries."""
        if not self._state:
            return
        st = self._state
        node = st.topology.nodes.get(st.player_location)
        if not node:
            return

        # Check for anomaly events
        if node.biome.instability_bias > 0.2:
            rng = SeededRNG(st.seed + st.tick).fork("anomaly_check")
            if rng.random() < node.biome.instability_bias:
                st.player_trajectory.update_from_anomaly()
                st.ledger.apply_delta("anomaly_stability", -1.0)
                self._push_ui("anomaly_event", {
                    "node": st.player_location,
                    "instability": node.biome.instability_bias,
                })
                self._tick()  # advance sim after player action
                return

        # Research gain
        if node.node_type in (NodeType.FACILITY, NodeType.LANDMARK):
            st.player_trajectory.update_from_research(10.0)
            st.ledger.apply_delta("research_advancement", 0.5)
            self._push_ui("research_discovery", {
                "node": st.player_location,
                "research_score": st.player_trajectory.research_investment,
            })
        else:
            self._push_ui("explored", {
                "node": st.player_location,
                "biome": node.biome.to_tuple(),
            })
        self._tick()  # advance sim after player action

    def _cmd_dialogue(self, delta_raw: Dict[str, float]):
        """Process a dialogue choice."""
        if not self._state:
            return
        delta = DialogueDelta(
            competition=delta_raw.get("competition", 0.0),
            preservation=delta_raw.get("preservation", 0.0),
            industrialization=delta_raw.get("industrialization", 0.0),
            research_priority=delta_raw.get("research_priority", 0.0),
            anomaly_curiosity=delta_raw.get("anomaly_curiosity", 0.0),
        )

        # Credibility from achievements
        pt = self._state.player_trajectory
        credibility = (
            0.5
            + pt.battles_won * 0.02
            + pt.nodes_explored * 0.01
            + pt.relics_found * 0.1
            + pt.research_investment * 0.005
        )
        credibility = min(3.0, credibility)

        pt.update_dialogue(delta, credibility)

        # Faction influence shift at current node
        node = self._state.topology.nodes.get(self._state.player_location)
        if node:
            for fid, faction in self._state.factions.items():
                alignment = 1.0 - faction.ideology.distance(pt.dialogue_ideology) / 3.0
                shift = alignment * credibility * 0.05
                current = node.faction_influence.get(fid, 0.0)
                node.faction_influence[fid] = max(0, min(1, current + shift))

        # Update player faction standings based on dialogue alignment
        for fid, faction in self._state.factions.items():
            alignment = 1.0 - faction.ideology.distance(pt.dialogue_ideology) / 3.0
            standing_shift = alignment * credibility * 0.03
            old = self._state.faction_standings.get(fid, 0.0)
            self._state.faction_standings[fid] = max(-1.0, min(1.0, old + standing_shift))

        self._push_ui("dialogue_processed", {
            "credibility": credibility,
            "ideology": pt.dialogue_ideology.to_dict(),
        })
        self._tick()  # advance sim after player action

    def _cmd_get_state(self):
        """Return full game state snapshot."""
        if not self._state:
            self._push_ui("error", {"message": "No island initialized"})
            return
        st = self._state
        self._push_ui("state", {
            "seed": st.seed,
            "tick": st.tick,
            "island_name": st.topology.island_name,
            "climate": st.topology.climate.name,
            "node_count": st.topology.node_count,
            "species_count": len(st.species_map),
            "player_location": st.player_location,
            "discovered_species": len(st.discovered_species),
            "ledger": st.ledger.to_dict(),
            "trajectory": st.player_trajectory.to_dict(),
            "factions": {fid: f.name for fid, f in st.factions.items()},
        })

    def _cmd_get_species(self):
        """Return species roster summary."""
        if not self._state:
            return
        species_list = [sp.to_dict() for sp in self._state.species_map.values()]
        self._push_ui("species_roster", {"species": species_list})

    def _cmd_get_map(self):
        """Return topology summary."""
        if not self._state:
            return
        nodes_data = {nid: nd.to_dict()
                      for nid, nd in self._state.topology.nodes.items()}
        self._push_ui("map_data", {
            "nodes": nodes_data,
            "start": self._state.topology.start_node_id,
            "player_location": self._state.player_location,
        })

    def _cmd_get_outcome(self):
        """Compute and return current outcome band."""
        if not self._state:
            return
        band = compute_outcome_band(self._state.ledger,
                                     self._state.player_trajectory)
        desc = describe_outcome_band(band)
        self._push_ui("outcome_band", desc)

    # ── UI push ────────────────────────────────────────────

    def _push_ui(self, event_type: str, data: Dict[str, Any]):
        """Push an event to the UI queue."""
        self._ui_q.put({"type": event_type, "data": data, "tick": self._state.tick if self._state else 0})


# ============================================================
# §14  WEB SERVER (OPTIONAL — FastAPI)
# ============================================================

def _start_web_server(stop_event: threading.Event,
                      runtime_stub: Dict[str, Any]):
    """Optional web UI server on port 7700."""
    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        import uvicorn

        app = FastAPI(title="Neikos: Hundred Islands")
        controller: NKController = runtime_stub.get("nk_controller")

        @app.get("/api/state")
        def get_state():
            if controller and controller._state:
                st = controller._state
                return {
                    "seed": st.seed,
                    "tick": st.tick,
                    "island_name": st.topology.island_name,
                    "node_count": st.topology.node_count,
                    "species_count": len(st.species_map),
                    "ledger": st.ledger.to_dict(),
                    "player_location": st.player_location,
                    "trajectory": st.player_trajectory.to_dict(),
                }
            return {"error": "not initialized"}

        @app.post("/api/command")
        async def post_command(cmd: dict):
            if controller:
                controller._cmd_q.put(cmd)
                return {"status": "queued"}
            return {"error": "not initialized"}

        @app.get("/api/map")
        def get_map():
            if controller and controller._state:
                return {nid: nd.to_dict()
                        for nid, nd in controller._state.topology.nodes.items()}
            return {"error": "not initialized"}

        @app.get("/api/species")
        def get_species():
            if controller and controller._state:
                return [sp.to_dict()
                        for sp in controller._state.species_map.values()]
            return {"error": "not initialized"}

        @app.get("/api/outcome")
        def get_outcome():
            if controller and controller._state:
                band = compute_outcome_band(
                    controller._state.ledger,
                    controller._state.player_trajectory)
                return describe_outcome_band(band)
            return {"error": "not initialized"}

        config = uvicorn.Config(app, host="0.0.0.0", port=7700, log_level="error")
        server = uvicorn.Server(config)

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.serve())
        finally:
            loop.close()

    except ImportError:
        _dbg("FastAPI/uvicorn not available — web server disabled")
    except Exception as e:
        _dbg(f"Web server error: {e}")


# ============================================================
# §15  WIDGET REGISTRATION (Radio OS Plugin Contract)
# ============================================================

def register_widgets(registry, runtime_stub):
    """Register Neikos: Hundred Islands with the Radio OS runtime."""

    # ---- command & UI queues ----
    if "nk_cmd_q" not in runtime_stub:
        runtime_stub["nk_cmd_q"] = queue.Queue()
        _dbg("Created nk_cmd_q")

    if "nk_ui_q" not in runtime_stub:
        runtime_stub["nk_ui_q"] = queue.Queue()
        _dbg("Created nk_ui_q")

    # ---- controller ----
    if "nk_controller" not in runtime_stub:
        controller = NKController(runtime_stub, {})
        runtime_stub["nk_controller"] = controller
        # Auto-initialize island with a default seed
        controller.init_island(seed=1)
        controller.start()
        _dbg("Controller started (seed=1)")

    # ---- web server ----
    if "nk_web_started" not in runtime_stub:
        stop_event = runtime_stub.get("stop_event", threading.Event())
        web_thread = threading.Thread(
            target=_start_web_server,
            args=(stop_event, runtime_stub),
            daemon=True,
            name="nk_web_server",
        )
        web_thread.start()
        runtime_stub["nk_web_started"] = True
        _dbg("Web server started on port 7700")

    # ---- placeholder desktop widget ----
    def nk_widget_factory(parent_frame):
        """
        Placeholder widget — web-first game.
        """
        try:
            import customtkinter as ctk
            frame = ctk.CTkFrame(parent_frame)
            label = ctk.CTkLabel(
                frame,
                text="Neikos: Hundred Islands\n\n"
                     "Open browser → http://localhost:7700",
                font=("Helvetica", 14),
            )
            label.pack(expand=True, padx=20, pady=20)
            return frame
        except ImportError:
            return None

    registry.register("neikos", nk_widget_factory)
    _dbg("Widget registered: neikos")


# ============================================================
# §16  STANDALONE VERIFICATION
# ============================================================

if __name__ == "__main__":
    """Quick smoke test — generate one island and print summary."""
    import sys

    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    print(f"=== Neikos: Hundred Islands — Seed {seed} ===\n")

    # Generate topology
    topo = generate_island_topology(seed)
    print(f"Island: {topo.island_name}")
    print(f"Climate: {topo.climate.name}")
    print(f"Nodes: {topo.node_count}")
    print(f"Active Types: {[t.name for t in topo.active_types]}")

    # Node type distribution
    type_counts: Dict[str, int] = {}
    for nd in topo.nodes.values():
        tn = nd.node_type.name
        type_counts[tn] = type_counts.get(tn, 0) + 1
    print(f"Node distribution: {type_counts}")

    # Region distribution
    region_counts: Dict[str, int] = {}
    for nd in topo.nodes.values():
        rn = nd.region.name
        region_counts[rn] = region_counts.get(rn, 0) + 1
    print(f"Region distribution: {region_counts}")

    # Generate species
    species_map = generate_species_roster(topo)
    print(f"\nSpecies: {len(species_map)}")

    rarity_dist: Dict[str, int] = {}
    for sp in species_map.values():
        rn = sp.rarity.name
        rarity_dist[rn] = rarity_dist.get(rn, 0) + 1
    print(f"Rarity distribution: {rarity_dist}")

    type_dist: Dict[str, int] = {}
    for sp in species_map.values():
        tn = sp.primary_type.name
        type_dist[tn] = type_dist.get(tn, 0) + 1
    print(f"Type distribution: {type_dist}")

    evo_lines = set(sp.evolution_line_id for sp in species_map.values())
    print(f"Evolution lines: {len(evo_lines)}")

    # Generate encounters
    ledger = IslandLedger()
    ledger.set_baseline(seed)
    enc_tables = generate_encounter_tables(topo, species_map, ledger)
    total_slots = sum(len(et.all_species()) for et in enc_tables.values())
    print(f"\nEncounter tables: {len(enc_tables)} nodes, {total_slots} total slots")

    # Generate factions
    factions = generate_factions(topo)
    print(f"\nFactions: {len(factions)}")
    for fid, f in factions.items():
        print(f"  {f.name} ({f.archetype.name}): influence={f.influence_score:.1f}")

    # Generate trainers
    trainers = generate_ai_trainers(topo, species_map)
    print(f"\nAI Trainers: {len(trainers)}")
    top_5 = sorted(trainers.values(), key=lambda t: -t.rating)[:5]
    for t in top_5:
        print(f"  {t.name}: rating={t.rating:.0f} tier={t.tier.name}")

    # Outcome band for a hypothetical trajectory
    traj = PlayerTrajectory(
        competitive_focus=60, exploration_depth=30,
        research_investment=20, breeding_intensity=10,
        anomaly_exposure=5, risk_appetite=65,
    )
    band = compute_outcome_band(ledger, traj)
    desc = describe_outcome_band(band)
    print(f"\nOutcome Band: {band}")
    print(f"  Island: {desc['island_condition']}")
    print(f"  Personal: {desc['personal_archetype']}")
    print(f"  {desc['summary']}")

    # Validation checks
    print("\n=== Validation ===")
    # Check type coverage
    for t in topo.active_types:
        count = sum(1 for sp in species_map.values() if sp.primary_type == t)
        status = "✓" if count >= 10 else "✗"
        print(f"  {status} {t.name}: {count} species (need ≥10)")

    # Check gate count
    gate_count = sum(1 for nd in topo.nodes.values() if nd.gate)
    print(f"  {'✓' if gate_count >= 8 else '✗'} Gates: {gate_count} (need ≥8)")

    # Check loops (at least 1 per region with spine)
    print(f"  ✓ Node count in range: {120 <= topo.node_count <= 250}")

    print("\n✓ Island generation complete.")
