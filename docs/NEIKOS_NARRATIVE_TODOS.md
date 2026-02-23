# Neikos: Hundred Islands — Narrative Bible v2 Implementation TODOs

All items map to sections of the Deterministic Narrative Bible v2.
File: `plugins/neikos.py` (currently 3332 lines, 16 sections §1–§16).

Legend: ✅ Done | 🔄 In Progress | ⬜ Pending

---

## CHUNK A — Core Canon Layer (§17–§19 scaffolding) ✅ COMPLETE
> Adds the hidden narrative skeleton. Zero breaking changes to existing systems.

- ✅ **A1** `§17 PROJECT HUNDRED CANON` — `FounderRecord`, `FOUNDER_CANON`, `resolve_founder_framing(seed)`
- ✅ **A2** `§18 BEHAVIORAL AXIS` — `BehavioralAxis` enum, `compute_behavioral_axis(trajectory)`
- ✅ **A3** `§19 CONTAINMENT TIER SYSTEM` — `ContainmentTier`, `TierCharacteristics`, `TIER_CHARACTERISTICS`, `compute_containment_tier`, `_seed_to_base_tier`; `IslandState.base_tier/current_tier`; `_tick()` recomputation every 20 ticks
- ✅ **A4** `ANOMALY_ZONE` NodeType; `is_relay_node` MapNode flag; topology steps 10b+10c; `IslandTopology.relay_node_ids/anomaly_zone_ids`

---

## CHUNK B — Narrative Mountain System (§20 pools) ✅ COMPLETE
> The deterministic story skeleton. Pure data — no runtime cost.

- ✅ **B1** `§20 NARRATIVE ARCHITECTURE` — `GLOBAL_MOUNTAINS` (M1–M20 with tier escalations), `ISLAND_MYSTERY_POOL` (IM1–IM20), `CHARACTER_ARC_POOL` (CA1–CA8), `LEAGUE_CONFLICT_POOL` (LC1–LC6)
- ✅ **B2** `IslandNarrativeProfile` dataclass with all fields + helper methods
- ✅ **B3** `generate_island_narrative(seed, base_tier)` — tier-weighted, CA3 always forced
- ✅ **B4** `get_mystery_description(mystery_code, tier)` with tier escalation fallback
- ✅ Wire: `IslandState.narrative_profile`, generated in `init_island()`

---

## CHUNK C — The Hidden Knower (§21) ✅ COMPLETE
> One NPC per island who holds partial knowledge. Unlock-gated.

- ✅ **C1** `KnowerArchetype` enum: 5 archetypes
- ✅ **C2** `HiddenKnower` dataclass: `archetype, name, location_node_id, unlock_thresholds, dialogue_fragments`, `is_unlocked()`, `get_fragment()`
- ✅ **C3** `generate_hidden_knower(topology, narrative_profile, seed)` — archetype placement, name pool, 3 fragments each
- ✅ **C4** `_cmd_talk_to_knower(fragment_index)` — locked/unlocked response with template substitution; `_cmd_get_knower()` (location hidden until unlocked); `"talk_knower"` + `"get_knower"` in `_handle_cmd`
- ✅ Wire: `IslandState.hidden_knower`; generated + wired in `init_island()`

---

## CHUNK D — NGP+ Behavioral Profile Persistence (§22) ✅ COMPLETE
> The hidden escalation system. Stored in `saves/.nk_profile.json`.

- ✅ **D1** `BehavioralProfileSignature` dataclass — `behavioral_axis, anomaly_engagement_history, ecological_disruption_pattern, dominance_harmony_bias, completed_tier, echo_seeds, run_count`, `to_dict()`, `from_dict()`
- ✅ **D2** `save_behavioral_profile(profile, path)` — merges with existing, dot-prefixed JSON file; `load_behavioral_profile(path)` — safe load, returns None if missing
- ✅ **D3** `compute_behavioral_signature(trajectory, ledger, current_tier, seed)` — derives signature from end-of-expedition state
- ✅ **D4** `apply_profile_to_island(profile, state)` — additive nudges: ecology, anomaly pressure, trajectory bias, NGP+ tier floor raise at run ≥ 2
- ✅ **D5** `init_island(seed, ngp_profile=None)` — accepts optional profile, applies it post-init
- ✅ **D6** `_cmd_new_expedition(next_seed)` + `_cmd_reset_simulation(seed)` in `_handle_cmd`
- ✅ Wire: `IslandState.ngp_profile`

---

## CHUNK E — Outcome Role Expansion (§23) ✅ COMPLETE
> Canonical narrative role names ON TOP of existing archetype names. Additive.

- ✅ **E1** `NARRATIVE_OUTCOME_ROLES: Dict[Tuple[int,int], str]` — 100 role labels covering all (iq, pq) combinations
- ✅ **E2** `compute_narrative_role(band_id) -> str`
- ✅ **E3** `describe_outcome_band()` — extended with `"narrative_role"` key (existing keys unchanged)

---

## CHUNK F — Memory Echo System (§24) ✅ COMPLETE
> Statistical recurrence artifacts across seeds. Pure presentation layer.

- ✅ **F1** `EchoEvent` dataclass + `_ECHO_MOTIF_POOL` — 30 motifs across 4 types (acoustic, visual, statistical, dialogue)
- ✅ **F2** `generate_echo_events(profile, topology, seed)` — uses `profile.echo_seeds`, gated at `run_count >= 2`, count scales with run count (capped 8)
- ✅ **F3** `IslandState.echo_events: Dict[str, EchoEvent]` (keyed by node_id) — populated in `init_island()` when NGP+ profile present
- ✅ **F4** `_cmd_explore()` — surfaces and consumes echo if present at current node; fires once then removed

---

## CHUNK G — Fragment System (§25) ✅ COMPLETE
> The "experiment leaks" as discoverable fragments. Presentation-only cold layer.

- ✅ **G1** `FragmentType` enum: `REDACTED_LOG | STATISTICAL_SUMMARY | RESEARCH_NOTE | SPECIES_REGISTRY_GLITCH | AUDIO_ARTIFACT`
- ✅ **G2** `NarrativeFragment` dataclass with `render()` + `to_dict()`
- ✅ **G3** `FRAGMENT_POOL` — 40 fragments across M1–M20 mountain codes with `{founder}`, `{island_name}`, `{tier}`, `{species_name}` slots
- ✅ **G4** `generate_island_fragments(narrative_profile, topology, seed)` — filters by active mountains, capped at 20
- ✅ **G5** `IslandState.island_fragments` + `IslandState.discovered_fragments`
- ✅ **G6** Fragment discovery in `_cmd_explore()` — node-type gated, ANOMALY_ZONE → AUDIO_ARTIFACT only
- ✅ **G7** `"get_fragments"` → `_cmd_get_fragments()` with rendered bodies for discovered fragments

---

## CHUNK H — Web API + Standalone Verification ✅ COMPLETE

- ✅ **H1** FastAPI routes: `GET /api/narrative`, `/api/tier`, `/api/knower`, `/api/fragments`, `/api/profile`
- ✅ **H2** `§16` smoke test extended: §17–§25 all verified inline

---

## Execution Order
```
A ✅ → B ✅ → C ✅ → D ✅ → E ✅ → F ✅ → G ✅ → H ✅
```

**ALL CHUNKS COMPLETE.** Final file size: ~6000 lines (§1–§25 + §13 controller).
All additions. Zero removals.

---

## Invariants (never break these)
- `SeededRNG` interface unchanged
- `_PERSONAL_ARCHETYPE_NAMES` and `_ISLAND_QUADRANT_NAMES` unchanged (E3 adds, not replaces)
- `compute_outcome_band()` signature unchanged
- Queue names (`nk_cmd_q`, `nk_ui_q`) unchanged
- `register_widgets()` signature unchanged
- All existing `_cmd_*` commands still work identically
- CA3 must always appear in `active_character_arcs` of narrative profile
- Profile path always `saves/.nk_profile.json` (dot-prefixed)
- Framing dict format: `{"traitor": "voss", "martyr": "kincaid", "protector": "ilyanova"}` (role→name_key)


All items map to sections of the Deterministic Narrative Bible v2.
File: `plugins/neikos.py` (currently 3332 lines, 16 sections §1–§16).

Legend: ✅ Done | 🔄 In Progress | ⬜ Pending

---

## CHUNK A — Core Canon Layer (§12–§20 scaffolding)
> Adds the hidden narrative skeleton. Zero breaking changes to existing systems.

- ⬜ **A1** `§17 PROJECT HUNDRED CANON` — New section after §16.
  - Named constants: `PROJECT_HUNDRED`, `THE_CARTOGRAPHERS`
  - `FounderRecord` dataclass: `name, role, thesis, fate_variant`
  - Fixed founders: Dr. Elian Voss, Dr. Mara Ilyanova, Director Hale Kincaid
  - `FOUNDER_CANON` dict (base truth, never varies)
  - `FOUNDER_TRUTH_VARIANTS` list (per-seed interpretation layer — who is framed as traitor)
  - `resolve_founder_framing(seed) -> dict` — deterministically assigns framing per island

- ⬜ **A2** `§18 BEHAVIORAL AXIS` — Add `BehavioralAxis` enum + tracker to `PlayerTrajectory`
  - Enum: `DOMINANT | CURIOUS | STABILIZING | EXPLOITATIVE`
  - `dominant_behavioral_axis() -> BehavioralAxis` derived from existing trajectory scores
  - No new fields needed — computed property from existing 5 axes

- ⬜ **A3** `§19 CONTAINMENT TIER SYSTEM`
  - `ContainmentTier` enum: `TIER_I` through `TIER_V` with descriptors
  - `TIER_CHARACTERISTICS` dict: mutation_rate_bias, league_stability, anomaly_density, npc_awareness_level per tier
  - `compute_containment_tier(ledger, trajectory) -> ContainmentTier` — deterministic from scores
  - Add `base_tier: ContainmentTier` and `current_tier: ContainmentTier` to `IslandState`
  - `init_island()` sets `base_tier` from seed, `current_tier` starts equal to base
  - `_tick()` recomputes `current_tier` from live scores every 20 ticks

- ⬜ **A4** Add `RELAY_NODE` flag to `MapNode` — `is_relay_node: bool = False`
  - Add `ANOMALY_ZONE` to `NodeType` enum
  - In `generate_island_topology()`: place 1–3 relay nodes in `INTERIOR_DEPTH` / `DUNGEON` nodes (seed-determined)
  - Relay node accessibility gated by anomaly_exposure + tier

---

## CHUNK B — Narrative Mountain System (§20–§25 pools)
> The deterministic story skeleton. Pure data — no runtime cost.

- ⬜ **B1** `§20 NARRATIVE MOUNTAIN POOLS` — new section `§20 NARRATIVE ARCHITECTURE`
  - `NarrativeMountain` dataclass: `id, code, label, description, tier_escalations: Dict[int, str]`
  - `GLOBAL_MOUNTAINS` list (M1–M20): Founder Betrayal Fracture, League Corruption Drift, Ecological Collapse Pressure, Neiko Mutation Instability, Hidden Observer Within Island, Memory Archive Degradation, Containment Breach Attempt, Silent Cartographer Loyalist, Failed Rebellion Myth, False History Rewrite, League Protects the System, League Accidentally Destabilizes, Neiko Sentience Spike, Anomaly Zone Expanding, Relay Node (formerly Anchor), Player Profile Flagged as Outlier, Ecological Over-Optimization, Cultural Ritual Around Containment, Fragmented Founder Recording, Genetic Drift Beyond Parameters
  - `ISLAND_MYSTERY_POOL` list (IM1–IM20): Disappearing Wild Zone, League Record Inconsistency, Restricted Ruin Area, Mutated Neiko Cluster, Gym Leader Acting Unstable, Missing Researcher, Strange Weather Pattern, Neiko Refuses Command Near Zone, League Ranking Glitch, Abandoned Outpost, Repeating Dream Reports, Echoing Signal in Cave, Identical Architecture Across Regions, Historical Dates Don't Align, Forbidden Route, Champion Who Vanished, Incorrect Evolution Event, Cultural Ritual With Unknown Origin, League Directive Contradiction, Silent Zone
  - `CHARACTER_ARC_POOL` list (CA1–CA8): Loyalist League Leader, Doubting Gym Leader, Hidden Knower, Overzealous Researcher, Disillusioned Champion, Ecological Purist, Power-Obsessed Rival, Resigned Archivist
  - `LEAGUE_CONFLICT_POOL` list (LC1–LC6): League Protects Stability, League Suppresses Anomalies, League Exploits Mutation, League Denies Historical Records, League Split Into Factions, League Militarization of Neikos

- ⬜ **B2** `IslandNarrativeProfile` dataclass
  - `primary_global_boulders: List[str]` (8–12 mountain codes)
  - `secondary_global_boulders: List[str]` (4–6)
  - `primary_mysteries: List[str]` (3–5 IM codes)
  - `secondary_mysteries: List[str]` (2–3 IM codes)
  - `active_character_arcs: List[str]` (3 CA codes)
  - `minor_roles: List[str]` (2 CA codes)
  - `primary_league_conflict: str` (1 LC code)
  - `background_league_tension: str` (1 LC code)
  - `founder_framing: dict` (from resolve_founder_framing)
  - `resolved_mysteries: Set[str]` — populated at runtime as player progresses
  - `unresolved_mysteries: Set[str]` — mysteries that persist

- ⬜ **B3** `generate_island_narrative(seed, base_tier) -> IslandNarrativeProfile`
  - Deterministic selection from pools using seeded RNG
  - Higher base_tier → more instability-themed mountains selected
  - Attach `IslandNarrativeProfile` to `IslandState`

- ⬜ **B4** Tier escalation depth per mystery
  - `get_mystery_description(mystery_code, tier) -> str` — returns tier-appropriate text
  - IM6 (Missing Researcher) example: Tier I = injured/blames Neiko, Tier V = flagged as anomaly variable

---

## CHUNK C — The Hidden Knower (§20.4)
> One NPC per island who holds partial knowledge. Unlock-gated.

- ⬜ **C1** `KnowerArchetype` enum: `RETIRED_ARCHIVIST | REGIONAL_GYM_LEADER | ISOLATED_RESEARCHER | ELDERLY_HERMIT | ANONYMOUS_SIGNAL`
- ⬜ **C2** `HiddenKnower` dataclass: `archetype, name, location_node_id, unlock_threshold: dict, dialogue_fragments: List[str]`
- ⬜ **C3** `generate_hidden_knower(topology, narrative_profile, seed) -> HiddenKnower`
  - Archetype selected deterministically from seed
  - Placed at a node consistent with archetype (hermit → wild zone, archivist → facility, etc.)
  - Unlock thresholds tied to: league progression + anomaly engagement + behavioral profile
- ⬜ **C4** `_cmd_talk_to_knower()` in `NKController`
  - Checks unlock threshold
  - Returns tiered dialogue fragment (confirms suspicions, never full exposition)
  - Updates `narrative_profile.resolved_mysteries` if threshold crossed
  - Add `"talk_knower"` action to `_handle_cmd`

---

## CHUNK D — NGP+ Behavioral Profile Persistence (§24)
> The hidden escalation system. Stored in `.nk_profile.json` inside `saves/`.

- ⬜ **D1** `BehavioralProfileSignature` dataclass
  - `behavioral_axis: str` (dominant axis name)
  - `anomaly_engagement_history: float` (0–100)
  - `ecological_disruption_pattern: float` (0–100)
  - `dominance_harmony_bias: float` (-1.0 to 1.0, negative = harmony)
  - `completed_tier: int` (highest tier completed)
  - `echo_seeds: List[int]` (previous island seeds for memory echo)
  - `run_count: int`

- ⬜ **D2** Profile storage: `saves/.nk_profile.json`
  - `save_behavioral_profile(profile, path)` — writes JSON
  - `load_behavioral_profile(path) -> Optional[BehavioralProfileSignature]` — reads JSON, returns None if missing
  - Path resolved relative to `STATION_DIR` env var, fallback to `saves/`
  - File named `.nk_profile.json` (dot-prefixed = not blazingly obvious)

- ⬜ **D3** `compute_behavioral_signature(trajectory, ledger) -> BehavioralProfileSignature`
  - Called at end of island (when `get_outcome` is triggered with high league_rank)

- ⬜ **D4** `apply_profile_to_island(profile, state)` — modifies new island's starting conditions
  - Mutation baseline shift based on `completed_tier`
  - Early anomaly visibility boost from `anomaly_engagement_history`
  - NPC suspicion levels from `dominance_harmony_bias`
  - Relay Node accessibility timing from `anomaly_engagement_history`

- ⬜ **D5** `NKController.init_island()` — accept optional `profile` param, call `apply_profile_to_island`
- ⬜ **D6** `"new_expedition"` and `"reset_simulation"` commands in `_handle_cmd`
  - `new_expedition`: saves profile, computes next tier, re-inits island with new seed
  - `reset_simulation`: deletes profile, re-inits at Tier I

---

## CHUNK E — Outcome Role Expansion (§7 + §21 Bible roles, additive)
> Add the canonical bible role names ON TOP of existing archetype names.

- ⬜ **E1** `NARRATIVE_OUTCOME_ROLES` dict: maps (tier, behavioral_axis, outcome_band_range) → role label
  - Bible roles: "The Model Subject", "The Efficient Champion", "The Silent Variable", "The Adaptive Outlier", "The System Disruptor", "The Anomaly Seeker", "The Catalyst", "The Fracture Harbinger", "The Apex Variable", "The Containment Breaker", "The Recursive Subject", "The Data Ascendant", "The Archive Reset", etc.
  - Total: ~25 canonical roles mapped across tier × behavioral_axis space

- ⬜ **E2** `compute_narrative_role(band_id, tier, behavioral_axis) -> str`
  - Returns canonical role label from `NARRATIVE_OUTCOME_ROLES`
  - Fallback to existing personal archetype name if no match

- ⬜ **E3** `describe_outcome_band()` — extend to include `narrative_role` key (additive, no removal)

---

## CHUNK F — Memory Echo System (§24.3)
> Statistical recurrence artifacts across seeds. Pure presentation layer.

- ⬜ **F1** `ECHO_MOTIF_POOL` — list of ~30 subtle echo descriptors
  - Acoustic: recurring Neiko call pattern, biome ambience loop
  - Visual: architectural symmetry, repeated NPC name fragment
  - Statistical: League ranking déjà vu, species distribution echo
  - Dialogue: NPC uses a phrase that echoes a prior island's Knower

- ⬜ **F2** `generate_echo_events(profile, topology, seed) -> List[dict]`
  - Uses `profile.echo_seeds` to seed cross-island recurrence
  - Returns list of `{node_id, echo_type, description}` events
  - Only non-empty if `profile.run_count >= 2`

- ⬜ **F3** `IslandState.echo_events` field + populate in `init_island()` when profile present
- ⬜ **F4** `_cmd_explore()` — if current node has echo event, push it to UI alongside normal explore output

---

## CHUNK G — Resolution Tracking + Fragment System (§4 + §19 + §27)
> The "experiment leaks" as discoverable fragments. Presentation-only cold layer.

- ⬜ **G1** `FragmentType` enum: `REDACTED_LOG | STATISTICAL_SUMMARY | RESEARCH_NOTE | SPECIES_REGISTRY_GLITCH | AUDIO_ARTIFACT`
- ⬜ **G2** `NarrativeFragment` dataclass: `fragment_id, type, title, body_template, unlock_condition: dict, mountain_code: str`
- ⬜ **G3** `FRAGMENT_POOL` — ~40 fragments tied to specific mountain codes
  - Each fragment has a `body_template` with `{founder}`, `{island_name}`, `{tier}` slots filled at runtime
- ⬜ **G4** `generate_island_fragments(narrative_profile, topology, seed) -> List[NarrativeFragment]`
  - Selects fragments matching active mountain codes
  - Applies founder framing substitutions
- ⬜ **G5** `IslandState.discovered_fragments: List[str]` (fragment IDs)
- ⬜ **G6** Fragment discovery in `_cmd_explore()` — FACILITY/LANDMARK/RELAY_NODE nodes surface fragments
  - ANOMALY_ZONE nodes surface AUDIO_ARTIFACT fragments
  - Gated by: anomaly_exposure >= threshold from fragment unlock_condition
- ⬜ **G7** `"get_fragments"` command in `_handle_cmd`

---

## CHUNK H — Web API + Standalone Verification Expansion (§14 + §16)
> Expose new systems through existing FastAPI + update smoke test.

- ⬜ **H1** FastAPI routes for new systems:
  - `GET /api/narrative` — returns `IslandNarrativeProfile` summary
  - `GET /api/tier` — returns current/base tier
  - `GET /api/knower` — returns knower status (locked/unlocked, archetype)
  - `GET /api/fragments` — returns discovered fragments
  - `GET /api/profile` — returns behavioral profile signature (if exists)

- ⬜ **H2** Standalone `§16` verification — extend to smoke-test:
  - Narrative profile generation
  - Founder framing variation across 5 seeds
  - Tier computation from sample trajectories
  - Hidden Knower placement
  - Fragment pool coverage

---

## Execution Order
```
A1 → A2 → A3 → A4   (canon + tier scaffolding, ~+200 lines)
B1 → B2 → B3 → B4   (mountain pools + profile, ~+300 lines)
C1 → C2 → C3 → C4   (Knower NPC, ~+100 lines)
D1 → D2 → D3 → D4 → D5 → D6   (NGP+ persistence, ~+150 lines)
E1 → E2 → E3         (outcome roles, ~+80 lines)
F1 → F2 → F3 → F4   (memory echoes, ~+100 lines)
G1 → G2 → G3 → G4 → G5 → G6 → G7   (fragment system, ~+200 lines)
H1 → H2              (API + verification, ~+80 lines)
```

Estimated final file size: ~4500–4700 lines (from current 3332).
All additions. Zero removals.

---

## Invariants (never break these)
- `SeededRNG` interface unchanged
- `_PERSONAL_ARCHETYPE_NAMES` and `_ISLAND_QUADRANT_NAMES` unchanged (E3 adds, not replaces)
- `compute_outcome_band()` signature unchanged
- Queue names (`nk_cmd_q`, `nk_ui_q`) unchanged
- `register_widgets()` signature unchanged
- All existing `_cmd_*` commands still work identically
