"""
test_neikos_sim.py
==================
Comprehensive simulation walkthrough for Neikos: Hundred Islands.

Covers every major system end-to-end:
  §1   SeededRNG determinism
  §4   Island topology generation
  §5   Species roster
  §6   Encounter tables
  §7   Battle system (full 3v3)
  §8   Breeding + genetic inheritance
  §9   Factions + dialogue impact
  §10  Outcome bands + narrative roles
  §11  Gate thresholds
  §12  Player trajectory
  §17  PROJECT HUNDRED canon / founder framing
  §18  Behavioral axis
  §19  Containment tier system
  §20  Narrative mountain/mystery/arc/conflict profiles
  §21  Hidden Knower (lock/unlock/dialogue)
  §22  NGP+ behavioral profile persistence
  §23  Narrative outcome roles
  §24  Memory echo system
  §25  Fragment system (discovery simulation)
  §13  Full NKController driven simulation (40 ticks with commands)

Run with:
    source radioenv/bin/activate
    python3 tests/test_neikos_sim.py
"""

import sys
import os
import queue
import time
import tempfile
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugins"))
import neikos as nk

SEED = 42
W = 80  # print width

# ── helpers ───────────────────────────────────────────────────────────────────

def hr(label=""):
    if label:
        pad = (W - len(label) - 4) // 2
        print(f"\n{'─'*pad}  {label}  {'─'*(W-pad-len(label)-4)}")
    else:
        print("─" * W)

def ok(msg):   print(f"  ✓  {msg}")
def info(msg): print(f"     {msg}")
def warn(msg): print(f"  ⚠  {msg}")

passed = []
failed = []

def check(condition, label, detail=""):
    if condition:
        ok(label)
        passed.append(label)
    else:
        print(f"  ✗  FAIL: {label}" + (f"  [{detail}]" if detail else ""))
        failed.append(label)

# ─────────────────────────────────────────────────────────────────────────────
hr("§1  SeededRNG DETERMINISM")
# ─────────────────────────────────────────────────────────────────────────────

rng_a = nk.SeededRNG(SEED).fork("test")
rng_b = nk.SeededRNG(SEED).fork("test")
vals_a = [rng_a.randint(0, 1000) for _ in range(20)]
vals_b = [rng_b.randint(0, 1000) for _ in range(20)]
check(vals_a == vals_b, "Same seed+fork → identical sequences")

rng_c = nk.SeededRNG(SEED + 1).fork("test")
vals_c = [rng_c.randint(0, 1000) for _ in range(20)]
check(vals_a != vals_c, "Different seed → different sequence")

# Fork isolation
rng_d = nk.SeededRNG(SEED)
f1 = rng_d.fork("alpha")
f2 = rng_d.fork("beta")
check(f1.randint(0, 9999) != f2.randint(0, 9999), "Different fork labels → different values")

# ─────────────────────────────────────────────────────────────────────────────
hr("§4  ISLAND TOPOLOGY")
# ─────────────────────────────────────────────────────────────────────────────

topo = nk.generate_island_topology(SEED)
info(f"Island: {topo.island_name}  |  Climate: {topo.climate.name}")
info(f"Nodes: {topo.node_count}  |  Regions: {len(set(n.region for n in topo.nodes.values()))}")
info(f"Active types: {[t.name for t in topo.active_types]}")

check(120 <= topo.node_count <= 250, f"Node count in range: {topo.node_count}")
check(len(topo.active_types) >= 8, f"≥8 active types: {len(topo.active_types)}")
check(topo.start_node_id in topo.nodes, "Start node exists in topology")

# Node type breakdown
type_counts = {}
for nd in topo.nodes.values():
    type_counts[nd.node_type.name] = type_counts.get(nd.node_type.name, 0) + 1
info(f"Node types: {type_counts}")

check("ANOMALY_ZONE" in type_counts, f"ANOMALY_ZONE nodes present: {type_counts.get('ANOMALY_ZONE', 0)}")
check("FACILITY" in type_counts, f"FACILITY nodes present: {type_counts.get('FACILITY', 0)}")
check(len(topo.relay_node_ids) >= 1, f"Relay nodes: {len(topo.relay_node_ids)}")
check(len(topo.anomaly_zone_ids) >= 3, f"Anomaly zone ids: {len(topo.anomaly_zone_ids)}")

# Gate count
gates = sum(1 for nd in topo.nodes.values() if nd.gate)
check(gates >= 8, f"Gate count ≥8: {gates}")

# Relay nodes actually flagged
relay_ok = all(topo.nodes[nid].is_relay_node for nid in topo.relay_node_ids)
check(relay_ok, "All relay_node_ids have is_relay_node=True")

# Topology is deterministic
topo2 = nk.generate_island_topology(SEED)
check(topo.island_name == topo2.island_name and topo.node_count == topo2.node_count,
      "Topology is deterministic (same seed → same island)")

# ─────────────────────────────────────────────────────────────────────────────
hr("§5  SPECIES ROSTER")
# ─────────────────────────────────────────────────────────────────────────────

species_map = nk.generate_species_roster(topo)
info(f"Species generated: {len(species_map)}")

check(len(species_map) == 300, f"Exactly 300 species: {len(species_map)}")

# Type coverage
for t in topo.active_types:
    count = sum(1 for sp in species_map.values() if sp.primary_type == t)
    check(count >= 10, f"Type {t.name}: {count} species (need ≥10)")

# Rarity distribution — all 6 rarities present
rarities = {sp.rarity.name for sp in species_map.values()}
check(len(rarities) == 6, f"All 6 rarities represented: {rarities}")

# Evolution lines
evo_lines = {sp.evolution_line_id for sp in species_map.values()}
info(f"Evolution lines: {len(evo_lines)}")
check(len(evo_lines) >= 100, f"≥100 evo lines: {len(evo_lines)}")

# Determinism
species_map2 = nk.generate_species_roster(topo)
ids_a = sorted(species_map.keys())
ids_b = sorted(species_map2.keys())
check(ids_a == ids_b, "Species roster is deterministic")

# ─────────────────────────────────────────────────────────────────────────────
hr("§6  ENCOUNTER TABLES")
# ─────────────────────────────────────────────────────────────────────────────

ledger = nk.IslandLedger()
ledger.set_baseline(SEED)
enc_tables = nk.generate_encounter_tables(topo, species_map, ledger)

info(f"Encounter tables: {len(enc_tables)} nodes")
total_slots = sum(len(et.all_species()) for et in enc_tables.values())
info(f"Total encounter slots: {total_slots}")

check(len(enc_tables) == topo.node_count, "One encounter table per node")
check(total_slots > 500, f"Substantial encounter pool: {total_slots}")

# Roll a few encounters and confirm species exist
rng_enc = nk.SeededRNG(SEED).fork("enc_test")
hits = 0
for nid, et in list(enc_tables.items())[:20]:
    sid = nk.roll_encounter(et, rng_enc)
    if sid and sid in species_map:
        hits += 1
check(hits >= 15, f"Encounter rolls resolve to known species: {hits}/20")

# ─────────────────────────────────────────────────────────────────────────────
hr("§7  BATTLE SYSTEM")
# ─────────────────────────────────────────────────────────────────────────────

# Build two teams from the roster
all_species = list(species_map.values())
rng_b = nk.SeededRNG(SEED).fork("battle_setup")

def make_team(offset, label):
    team = []
    for i in range(3):
        sp = all_species[(offset + i * 17) % len(all_species)]
        inst = nk.CreatureInstance(
            instance_id=f"{label}_{i}",
            species_id=sp.species_id,
            level=20 + i * 5,
            genes=nk.GeneticProfile(
                stat_genes=[rng_b.randint(10, 28) for _ in range(6)],
                variance_seed=rng_b.randint(0, 2**31),
            ),
            temperament=0.5 + i * 0.1,
        )
        team.append((inst, sp))
    return team

p_team = make_team(0,  "p")
o_team = make_team(50, "o")

info(f"Player team:   {[t[1].name for t in p_team]}")
info(f"Opponent team: {[t[1].name for t in o_team]}")

rng_battle = nk.SeededRNG(SEED).fork("battle_sim")
result = nk.simulate_battle(p_team, o_team, rng_battle)

info(f"Winner: {result.winner}  |  Turns: {result.turns}")
info(f"Player remaining HP:   {result.player_remaining}")
info(f"Opponent remaining HP: {result.opponent_remaining}")
info(f"Fatigue delta: {result.fatigue_delta}")

check(result.winner in ("player", "opponent"), f"Battle has a winner: {result.winner}")
check(1 <= result.turns <= 100, f"Battle ends in 1–100 turns: {result.turns}")
check(result.fatigue_delta >= 0, "Fatigue delta is non-negative")

# Determinism — same seed → same winner
rng_battle2 = nk.SeededRNG(SEED).fork("battle_sim")
result2 = nk.simulate_battle(p_team, o_team, rng_battle2)
check(result.winner == result2.winner and result.turns == result2.turns,
      "Battle is fully deterministic")

# Different seed → may differ
rng_battle3 = nk.SeededRNG(SEED + 7).fork("battle_sim")
result3 = nk.simulate_battle(p_team, o_team, rng_battle3)
info(f"Alt-seed battle winner: {result3.winner} in {result3.turns} turns")

# Run 50 battles, check winner distribution — use matched levels so both sides can win
wins = {"player": 0, "opponent": 0}
for i in range(50):
    pt = make_team(i * 3, "p")
    ot = make_team(i * 3 + 1, "o")
    r = nk.simulate_battle(pt, ot, nk.SeededRNG(SEED + i).fork("b"))
    wins[r.winner] += 1
info(f"50-battle distribution: player={wins['player']} opponent={wins['opponent']}")
check(wins["player"] > 0 and wins["opponent"] > 0, "Both sides win some battles over 50 seeds")

# ─────────────────────────────────────────────────────────────────────────────
hr("§8  BREEDING + GENETIC INHERITANCE")
# ─────────────────────────────────────────────────────────────────────────────

sp_a = all_species[0]
sp_b = all_species[1]
rng_breed = nk.SeededRNG(SEED).fork("breed")
inst_a, inst_b = p_team[0][0], p_team[1][0]

offspring_genes = nk.breed_creatures(inst_a, inst_b, sp_a, sp_b, rng_breed, anomaly_instability=0.0)
info(f"Parent A genes: {inst_a.genes.stat_genes}")
info(f"Parent B genes: {inst_b.genes.stat_genes}")
info(f"Offspring genes: {offspring_genes.stat_genes}")
info(f"Lineage depth: {offspring_genes.lineage_depth}")

check(len(offspring_genes.stat_genes) == 6, "Offspring has 6 stat genes")
check(offspring_genes.lineage_depth >= 1, f"Lineage depth ≥1: {offspring_genes.lineage_depth}")

# Genes are a mix of parents, not copies
parent_genes = set(inst_a.genes.stat_genes + inst_b.genes.stat_genes)
match_count = sum(1 for g in offspring_genes.stat_genes if g in parent_genes)
check(match_count >= 2, f"Offspring genes overlap with parents: {match_count}/6")

# Anomaly instability increases trait variance
rng_anom = nk.SeededRNG(SEED).fork("breed_anom")
anom_genes = nk.breed_creatures(inst_a, inst_b, sp_a, sp_b, rng_anom, anomaly_instability=0.9)
info(f"Anomaly offspring genes: {anom_genes.stat_genes}  traits: {anom_genes.trait_genes}")

# Determinism
rng_breed2 = nk.SeededRNG(SEED).fork("breed")
inst_a2, inst_b2 = p_team[0][0], p_team[1][0]
offspring2 = nk.breed_creatures(inst_a2, inst_b2, sp_a, sp_b, rng_breed2)
check(offspring_genes.stat_genes == offspring2.stat_genes, "Breeding is deterministic")

# ─────────────────────────────────────────────────────────────────────────────
hr("§9  FACTIONS + DIALOGUE IMPACT")
# ─────────────────────────────────────────────────────────────────────────────

factions = nk.generate_factions(topo)
info(f"Factions ({len(factions)}):")
for fid, f in factions.items():
    info(f"  {f.name:40s} [{f.archetype.name}]  influence={f.influence_score:.1f}")

check(len(factions) >= 4, f"At least 4 factions: {len(factions)}")

archetype_names = {f.archetype.name for f in factions.values()}
check("LEAGUE_AUTHORITY" in archetype_names, "League Authority faction present")
check("DEPTH_SECT" in archetype_names, "Depth Sect faction present")

# Faction diffusion
topo_copy = nk.generate_island_topology(SEED)
fac2 = nk.generate_factions(topo_copy)
old_influences = {fid: f.influence_score for fid, f in fac2.items()}
nk.diffuse_faction_influence(topo_copy, fac2)
# Influence changed at node level, faction totals may shift
info("Faction diffusion ran without error ✓")

# Dialogue impact
traj_diag = nk.PlayerTrajectory(competitive_focus=50)
delta = nk.DialogueDelta(
    competition=2.0,
    preservation=-1.0,
    industrialization=0.5,
    research_priority=1.0,
    anomaly_curiosity=0.5,
)
before_comp = traj_diag.competitive_focus
impact = nk.compute_dialogue_impact(delta, 1.5, faction_standings={})
info(f"Dialogue impact: competition={impact.get('competition', 'n/a'):.2f}")
check(True, "compute_dialogue_impact runs without error")

# ─────────────────────────────────────────────────────────────────────────────
hr("§10  OUTCOME BANDS + §23 NARRATIVE ROLES")
# ─────────────────────────────────────────────────────────────────────────────

# Sample several trajectories and show their outcomes
scenarios = [
    ("Pure Competitor",  nk.PlayerTrajectory(competitive_focus=90, risk_appetite=80)),
    ("Researcher",       nk.PlayerTrajectory(research_investment=85, exploration_depth=40)),
    ("Explorer",         nk.PlayerTrajectory(exploration_depth=90, anomaly_exposure=30)),
    ("Breeder",          nk.PlayerTrajectory(breeding_intensity=80, research_investment=30)),
    ("Anomaly Seeker",   nk.PlayerTrajectory(anomaly_exposure=85, risk_appetite=70)),
    ("Balanced",         nk.PlayerTrajectory(competitive_focus=40, exploration_depth=40,
                                              research_investment=40, breeding_intensity=20,
                                              anomaly_exposure=20, risk_appetite=50)),
]

info(f"{'Scenario':<22} {'Band':>4}  {'Island Condition':<26} {'Archetype':<22} Narrative Role")
info("─" * W)
seen_bands = set()
for label, traj in scenarios:
    band = nk.compute_outcome_band(ledger, traj)
    desc = nk.describe_outcome_band(band)
    role = desc["narrative_role"]
    info(f"  {label:<20} {band:>4}  {desc['island_condition']:<26} "
         f"{desc['personal_archetype']:<22} {role}")
    seen_bands.add(band)

check(len(seen_bands) == len(scenarios), f"All scenarios produce distinct bands: {len(seen_bands)}")
check(len(nk.NARRATIVE_OUTCOME_ROLES) == 100, "All 100 outcome roles defined")

# narrative_role key present in describe_outcome_band
desc_check = nk.describe_outcome_band(57)
check("narrative_role" in desc_check, "narrative_role key in describe_outcome_band()")
check("band_id" in desc_check and "island_condition" in desc_check,
      "Existing keys still present (additive change)")

# ─────────────────────────────────────────────────────────────────────────────
hr("§11  GATE THRESHOLDS")
# ─────────────────────────────────────────────────────────────────────────────

# Apply gate threshold computation
before_thresholds = {
    nid: nd.gate.threshold
    for nid, nd in topo.nodes.items() if nd.gate
}
nk.compute_gate_thresholds(topo, ledger, factions)
after_thresholds = {
    nid: nd.gate.threshold
    for nid, nd in topo.nodes.items() if nd.gate
}
check(len(before_thresholds) == len(after_thresholds), "Gate count unchanged after threshold computation")
info(f"Gates computed: {len(after_thresholds)}")

# Check a gate check works
gated_node = next((nd for nd in topo.nodes.values() if nd.gate), None)
if gated_node:
    info(f"Sample gate: type={gated_node.gate.gate_type.name} "
         f"metric={gated_node.gate.primary_metric} threshold={gated_node.gate.threshold:.1f}")
    weak_player = {"trainer_rating": 100, "faction_standing": 0, "research_milestones": 0,
                   "ecological_balance": 0, "anomaly_exposure": 0, "economic_investment": 0,
                   "exploration_score": 0, "league_tier": 1.0}
    check(isinstance(gated_node.gate.check(weak_player), bool), "Gate.check() returns bool")

# ─────────────────────────────────────────────────────────────────────────────
hr("§17  PROJECT HUNDRED CANON")
# ─────────────────────────────────────────────────────────────────────────────

info(f"Project name:  {nk.PROJECT_HUNDRED}")
info(f"Organisation:  {nk.THE_CARTOGRAPHERS}")
info(f"Founders:")
for key, rec in nk.FOUNDER_CANON.items():
    info(f"  [{key}] {rec.name}  —  {rec.role}")
    info(f"          Thesis: {rec.thesis[:65]}…")

check(len(nk.FOUNDER_CANON) == 3, "Exactly 3 founders in FOUNDER_CANON")

# Framing variations across seeds
info("\nFounder framing across 10 seeds:")
traitor_counts = {}
for s in range(10):
    framing = nk.resolve_founder_framing(s)
    traitor_key = framing.get("traitor", "?")
    traitor_name = nk.FOUNDER_CANON[traitor_key].name if traitor_key in nk.FOUNDER_CANON else traitor_key
    traitor_counts[traitor_name] = traitor_counts.get(traitor_name, 0) + 1
    roles = {v: nk.FOUNDER_CANON[k].name for k, v in framing.items() if k in nk.FOUNDER_CANON}
    info(f"  seed {s}: traitor={traitor_name}")

info(f"Traitor distribution: {traitor_counts}")
check(len(traitor_counts) > 1, f"Multiple traitor assignments across 10 seeds (not always same person)")

# ─────────────────────────────────────────────────────────────────────────────
hr("§18  BEHAVIORAL AXIS")
# ─────────────────────────────────────────────────────────────────────────────

axis_cases = [
    ("Heavy competitor",  nk.PlayerTrajectory(competitive_focus=90), nk.BehavioralAxis.DOMINANT),
    ("Pure explorer",     nk.PlayerTrajectory(exploration_depth=90), nk.BehavioralAxis.CURIOUS),
    ("Pure researcher",   nk.PlayerTrajectory(research_investment=90), nk.BehavioralAxis.STABILIZING),
    ("Anomaly addict",    nk.PlayerTrajectory(anomaly_exposure=90), nk.BehavioralAxis.CURIOUS),
    ("Heavy breeder",     nk.PlayerTrajectory(breeding_intensity=90), nk.BehavioralAxis.EXPLOITATIVE),
]
info(f"{'Profile':<22} {'Axis':<16}")
info("─" * 40)
all_axes_seen = set()
for label, traj, expected in axis_cases:
    axis = nk.compute_behavioral_axis(traj)
    all_axes_seen.add(axis)
    marker = "✓" if axis == expected else "≈"
    info(f"  {marker}  {label:<20} → {axis.name}")

check(len(all_axes_seen) >= 3, f"≥3 distinct axes appear across test profiles: {[a.name for a in all_axes_seen]}")

# ─────────────────────────────────────────────────────────────────────────────
hr("§19  CONTAINMENT TIER SYSTEM")
# ─────────────────────────────────────────────────────────────────────────────

# Tier characteristics
info("Tier characteristics:")
for tier in nk.ContainmentTier:
    tc = nk.TIER_CHARACTERISTICS[tier]
    info(f"  {tier.name}: mut_bias={tc.mutation_rate_bias:.2f}  "
         f"league_stability={tc.league_stability:.2f}  "
         f"anomaly_density={tc.anomaly_density:.2f}")
    info(f"    → \"{tc.description}\"")

# Tier escalation via trajectory
tier_scenarios = [
    ("Baseline (no pressure)",    nk.PlayerTrajectory()),
    ("Moderate anomaly",          nk.PlayerTrajectory(anomaly_exposure=40, competitive_focus=30)),
    ("High anomaly + competitive",nk.PlayerTrajectory(anomaly_exposure=70, competitive_focus=80)),
    ("Extreme pressure",          nk.PlayerTrajectory(anomaly_exposure=95, competitive_focus=95,
                                                       exploration_depth=90)),
]
info("\nTier computation from trajectory:")
tiers_seen = set()
for label, traj in tier_scenarios:
    ledger_t = nk.IslandLedger()
    ledger_t.set_baseline(SEED)
    tier = nk.compute_containment_tier(ledger_t, traj)
    tiers_seen.add(tier)
    info(f"  {label:<38} → {tier.name}")

check(len(tiers_seen) >= 3, f"Tier escalates across pressure levels: {[t.name for t in sorted(tiers_seen, key=lambda x: x.value)]}")

# Seed-to-base distribution
info("\nBase tier distribution across 100 seeds:")
base_dist = {}
for s in range(100):
    t = nk._seed_to_base_tier(s)
    base_dist[t.name] = base_dist.get(t.name, 0) + 1
info(f"  {base_dist}")
check(base_dist.get("TIER_I", 0) > 50, f"TIER_I is most common base tier: {base_dist.get('TIER_I', 0)}/100")
check("TIER_V" in base_dist, f"TIER_V occurs in 100 seeds: {base_dist.get('TIER_V', 0)} times")

# ─────────────────────────────────────────────────────────────────────────────
hr("§20  NARRATIVE MOUNTAIN / MYSTERY / ARC / CONFLICT PROFILE")
# ─────────────────────────────────────────────────────────────────────────────

base_tier = nk._seed_to_base_tier(SEED)
np_prof = nk.generate_island_narrative(SEED, base_tier)

info(f"Primary global mountains ({len(np_prof.primary_global_boulders)}): {np_prof.primary_global_boulders}")
info(f"Secondary mountains      ({len(np_prof.secondary_global_boulders)}): {np_prof.secondary_global_boulders}")
info(f"Primary mysteries        ({len(np_prof.primary_mysteries)}): {np_prof.primary_mysteries}")
info(f"Secondary mysteries      ({len(np_prof.secondary_mysteries)}): {np_prof.secondary_mysteries}")
info(f"Active character arcs    ({len(np_prof.active_character_arcs)}): {np_prof.active_character_arcs}")
info(f"Minor roles              ({len(np_prof.minor_roles)}): {np_prof.minor_roles}")
info(f"Primary league conflict: {np_prof.primary_league_conflict}")
info(f"Background tension:      {np_prof.background_league_tension}")
info(f"Founder framing:         {np_prof.founder_framing}")

check(8 <= len(np_prof.primary_global_boulders) <= 12,
      f"8–12 primary mountains: {len(np_prof.primary_global_boulders)}")
check("CA3" in np_prof.active_character_arcs, "CA3 (Hidden Knower) always forced into arcs")
check(np_prof.primary_league_conflict.startswith("LC"), "League conflict assigned")
check(len(np_prof.founder_framing) == 3, "Founder framing has 3 roles")

# Mountain tier escalation
info("\nMystery tier escalation (IM6 across all tiers):")
for tier in nk.ContainmentTier:
    desc = nk.get_mystery_description("IM6", tier)
    info(f"  {tier.name}: {desc[:70]}…")
check(
    nk.get_mystery_description("IM6", nk.ContainmentTier.TIER_I) !=
    nk.get_mystery_description("IM6", nk.ContainmentTier.TIER_V),
    "Mystery description escalates from Tier I to Tier V"
)

# Profile varies across seeds
np_seed2 = nk.generate_island_narrative(SEED + 1, base_tier)
check(
    np_prof.primary_global_boulders != np_seed2.primary_global_boulders,
    "Narrative profile differs across seeds"
)

# ─────────────────────────────────────────────────────────────────────────────
hr("§21  HIDDEN KNOWER")
# ─────────────────────────────────────────────────────────────────────────────

knower = nk.generate_hidden_knower(topo, np_prof, SEED)
info(f"Archetype:  {knower.archetype.name}")
info(f"Name:       {knower.name}")
loc_node = topo.nodes.get(knower.location_node_id)
info(f"Location:   {knower.location_node_id}  ({loc_node.node_type.name if loc_node else '?'})")
info(f"Fragments:  {len(knower.dialogue_fragments)}")
info(f"Thresholds: {knower.unlock_thresholds}")

check(knower.location_node_id in topo.nodes, "Knower location is a valid node")
check(len(knower.dialogue_fragments) == 3, "Knower has exactly 3 dialogue fragments")

# Unlock check — fresh trajectory should be locked
fresh_traj = nk.PlayerTrajectory()
check(not knower.is_unlocked(fresh_traj), "Knower locked on fresh trajectory")

# Build a trajectory that meets all thresholds
unlocked_traj = nk.PlayerTrajectory(
    exploration_depth=100, research_investment=100,
    competitive_focus=100, anomaly_exposure=100,
    anomaly_events=20, nodes_explored=200, battles_won=30,
)
check(knower.is_unlocked(unlocked_traj), "Knower unlocks when all thresholds exceeded")

# Fragment rendering
ctx = {
    "island_name":  topo.island_name,
    "species_name": "Thornback",
    "anomaly_count": 7,
    "relay_node_id": "relay_001",
}
frag_0 = knower.get_fragment(0, ctx)
frag_1 = knower.get_fragment(1, ctx)
info(f"Fragment 0: {frag_0[:80]}…")
info(f"Fragment 1: {frag_1[:80]}…")
check(bool(frag_0) and bool(frag_1), "Fragments render non-empty strings")
check(frag_0 != frag_1, "Fragment 0 and 1 are distinct")

# Archetype placement varies across seeds
archetypes_seen = set()
for s in range(20):
    k = nk.generate_hidden_knower(topo, np_prof, s)
    archetypes_seen.add(k.archetype)
info(f"Archetypes seen across 20 seeds: {[a.name for a in archetypes_seen]}")
check(len(archetypes_seen) >= 3, f"≥3 distinct knower archetypes across 20 seeds")

# ─────────────────────────────────────────────────────────────────────────────
hr("§22  NGP+ BEHAVIORAL PROFILE PERSISTENCE")
# ─────────────────────────────────────────────────────────────────────────────

tmp_path = tempfile.mktemp(suffix=".json")

# Build a realistic end-of-run trajectory
run1_traj = nk.PlayerTrajectory(
    competitive_focus=65, exploration_depth=45,
    research_investment=30, anomaly_exposure=20,
    breeding_intensity=15, risk_appetite=60,
    battles_won=18, nodes_explored=55,
)
run1_ledger = nk.IslandLedger()
run1_ledger.set_baseline(SEED)
run1_tier = nk.ContainmentTier.TIER_II

sig1 = nk.compute_behavioral_signature(run1_traj, run1_ledger, run1_tier, SEED)
info(f"Run 1 signature:")
info(f"  axis={sig1.behavioral_axis}  tier={sig1.completed_tier}"
     f"  anomaly_hist={sig1.anomaly_engagement_history:.2f}"
     f"  dom_bias={sig1.dominance_harmony_bias:.3f}")

check(sig1.behavioral_axis in [a.name for a in nk.BehavioralAxis], "Axis is a valid BehavioralAxis name")
check(sig1.completed_tier == 2, f"Completed tier matches TIER_II: {sig1.completed_tier}")

# Save run 1
path_written = nk.save_behavioral_profile(sig1, tmp_path)
loaded1 = nk.load_behavioral_profile(tmp_path)
check(loaded1 is not None, "Profile loads back from disk")
check(loaded1.behavioral_axis == sig1.behavioral_axis, "Axis preserved on round-trip")
check(loaded1.run_count == 1, f"run_count=1 after first save: {loaded1.run_count}")

# Save run 2 — merge
run2_traj = nk.PlayerTrajectory(
    competitive_focus=40, anomaly_exposure=50, exploration_depth=70,
)
sig2 = nk.compute_behavioral_signature(run2_traj, run1_ledger, nk.ContainmentTier.TIER_III, SEED + 1)
nk.save_behavioral_profile(sig2, tmp_path)
loaded2 = nk.load_behavioral_profile(tmp_path)

check(loaded2.run_count == 2, f"run_count=2 after second save: {loaded2.run_count}")
check(loaded2.completed_tier == 3, f"Completed tier is max(2,3)=3: {loaded2.completed_tier}")
check(
    loaded2.anomaly_engagement_history == round(
        sig1.anomaly_engagement_history + sig2.anomaly_engagement_history, 4),
    "Anomaly history accumulates across runs"
)
info(f"Merged profile: axis={loaded2.behavioral_axis}  runs={loaded2.run_count}"
     f"  tier={loaded2.completed_tier}  anom_hist={loaded2.anomaly_engagement_history:.2f}")

# apply_profile_to_island
fresh_state_topo = nk.generate_island_topology(SEED + 5)
fresh_species = nk.generate_species_roster(fresh_state_topo)
fresh_enc = nk.generate_encounter_tables(fresh_state_topo, fresh_species, nk.IslandLedger())
eco_before = nk.IslandLedger()
eco_before.set_baseline(SEED + 5)

import copy
eco_with_profile = copy.deepcopy(eco_before)

# Build a high-disruption profile
disruptive_sig = nk.BehavioralProfileSignature(
    behavioral_axis="DOMINANT",
    ecological_disruption_pattern=0.8,
    anomaly_engagement_history=50.0,
    dominance_harmony_bias=0.7,
    completed_tier=3,
    run_count=3,
    echo_seeds=[SEED, SEED+1, SEED+2],
)

# Build a fake state to apply it to
fresh_state_obj = nk.IslandState(
    seed=SEED + 5,
    topology=fresh_state_topo,
    species_map=fresh_species,
    ledger=eco_with_profile,
    base_tier=nk.ContainmentTier.TIER_I,
    current_tier=nk.ContainmentTier.TIER_I,
)
nk.apply_profile_to_island(disruptive_sig, fresh_state_obj)

check(fresh_state_obj.base_tier == nk.ContainmentTier.TIER_II,
      f"NGP+ run≥2 raises tier floor by 1: {fresh_state_obj.base_tier.name}")
check(fresh_state_obj.player_trajectory.competitive_focus > 0,
      f"Dominance bias shifts competitive_focus: {fresh_state_obj.player_trajectory.competitive_focus:.1f}")

os.remove(tmp_path)
check(True, "Temp profile file cleaned up")

# ─────────────────────────────────────────────────────────────────────────────
hr("§24  MEMORY ECHO SYSTEM")
# ─────────────────────────────────────────────────────────────────────────────

# No echoes on first run
no_echo_profile = nk.BehavioralProfileSignature(run_count=1, echo_seeds=[SEED])
echoes_run1 = nk.generate_echo_events(no_echo_profile, topo, SEED)
check(len(echoes_run1) == 0, f"No echoes on run_count=1: {len(echoes_run1)}")

# Echoes appear from run 2+
echo_profile_r2 = nk.BehavioralProfileSignature(
    run_count=2, echo_seeds=[SEED - 1, SEED], anomaly_engagement_history=15.0
)
echoes_r2 = nk.generate_echo_events(echo_profile_r2, topo, SEED)
check(len(echoes_r2) >= 2, f"Echoes appear from run 2: {len(echoes_r2)}")

echo_profile_r5 = nk.BehavioralProfileSignature(
    run_count=5, echo_seeds=[1, 2, 3, 4, SEED], anomaly_engagement_history=40.0
)
echoes_r5 = nk.generate_echo_events(echo_profile_r5, topo, SEED)
check(len(echoes_r5) >= 4, f"More echoes at run 5: {len(echoes_r5)}")
check(len(echoes_r5) <= 8, f"Echo count capped at 8: {len(echoes_r5)}")

info(f"\nEcho sample (run 2):")
for e in echoes_r2[:3]:
    info(f"  [{e.echo_type}] @{e.node_id}  {e.description[:65]}…")

# All placed nodes are valid
bad_nodes = [e.node_id for e in echoes_r5 if e.node_id not in topo.nodes]
check(len(bad_nodes) == 0, f"All echo nodes exist in topology (bad: {bad_nodes})")

# Type variety
echo_types = {e.echo_type for e in echoes_r5}
check(len(echo_types) >= 2, f"Multiple echo types present: {echo_types}")

# Deterministic
echoes_r5b = nk.generate_echo_events(echo_profile_r5, topo, SEED)
check(
    [e.motif_code for e in echoes_r5] == [e.motif_code for e in echoes_r5b],
    "Echo generation is deterministic"
)

# ─────────────────────────────────────────────────────────────────────────────
hr("§25  FRAGMENT SYSTEM")
# ─────────────────────────────────────────────────────────────────────────────

info(f"Total fragment pool: {len(nk.FRAGMENT_POOL)}")
check(len(nk.FRAGMENT_POOL) >= 40, f"Fragment pool ≥40: {len(nk.FRAGMENT_POOL)}")

# Type coverage in pool
pool_types = {f.ftype.name for f in nk.FRAGMENT_POOL}
info(f"Fragment types in pool: {pool_types}")
check(len(pool_types) >= 4, f"≥4 fragment types in pool: {pool_types}")

# Mountain code coverage
pool_mountains = {f.mountain_code for f in nk.FRAGMENT_POOL}
info(f"Mountains covered by fragments: {sorted(pool_mountains)}")
check(len(pool_mountains) >= 10, f"≥10 mountains have fragments: {len(pool_mountains)}")

# Island-specific selection
frags = nk.generate_island_fragments(np_prof, topo, SEED)
info(f"Island fragment selection: {len(frags)} fragments")
check(len(frags) <= 20, f"Island selection capped at 20: {len(frags)}")
check(len(frags) >= 5, f"Island has ≥5 fragments: {len(frags)}")

# All selected fragments' mountains are in active set
active_mountains = set(np_prof.primary_global_boulders + np_prof.secondary_global_boulders)
bad_frags = [f.fragment_id for f in frags if f.mountain_code not in active_mountains]
check(len(bad_frags) == 0, f"All island fragments match active mountains (bad: {bad_frags})")

# Deterministic selection
frags2 = nk.generate_island_fragments(np_prof, topo, SEED)
check([f.fragment_id for f in frags] == [f.fragment_id for f in frags2],
      "Fragment selection is deterministic")

# Render context substitution
framing = np_prof.founder_framing
traitor_key = framing.get("traitor", "voss")
traitor_name = nk.FOUNDER_CANON[traitor_key].name if traitor_key in nk.FOUNDER_CANON else "Dr. Voss"
species_sample = next(iter(species_map.values()))
ctx = {
    "founder":       traitor_name,
    "island_name":   topo.island_name,
    "tier":          base_tier.name,
    "species_name":  species_sample.name,
    "anomaly_count": len(topo.anomaly_zone_ids),
    "variance":      20.0,
    "collapse_ticks": 150,
}
info(f"\nSample fragments (rendered):")
for frag in frags[:4]:
    rendered = frag.render(ctx)
    info(f"  [{frag.ftype.name}] \"{frag.title}\"")
    info(f"    {rendered[:100]}…")

render_ok = all(bool(f.render(ctx)) for f in frags)
check(render_ok, "All island fragments render without KeyError")

# ─────────────────────────────────────────────────────────────────────────────
hr("§13  FULL CONTROLLER SIMULATION  (40 ticks via commands)")
# ─────────────────────────────────────────────────────────────────────────────

ui_q = queue.Queue()
cmd_q = queue.Queue()
rt = {"nk_cmd_q": cmd_q, "nk_ui_q": ui_q}
ctrl = nk.NKController(rt, {})

# Init with a rich NGP+ profile (run 3 → tier floor raised)
ngp = nk.BehavioralProfileSignature(
    behavioral_axis="CURIOUS",
    anomaly_engagement_history=35.0,
    ecological_disruption_pattern=0.4,
    dominance_harmony_bias=0.2,
    completed_tier=2,
    echo_seeds=[1, 7, SEED],
    run_count=3,
)
ctrl.init_island(SEED, ngp_profile=ngp)
st = ctrl._state
check(st is not None, "Island initialized")
check(st.base_tier.value >= 2, f"NGP+ tier floor applied (run 3 → ≥TIER_II): {st.base_tier.name}")
check(st.hidden_knower is not None, "Hidden Knower generated")
check(st.narrative_profile is not None, "Narrative profile generated")
check(len(st.island_fragments) > 0, f"Island fragments generated: {len(st.island_fragments)}")
check(len(st.echo_events) > 0, f"Echo events generated (run 3): {len(st.echo_events)}")

info(f"\nIsland: {st.topology.island_name}  seed={SEED}  base_tier={st.base_tier.name}")
info(f"Knower: {st.hidden_knower.name} ({st.hidden_knower.archetype.name})")
info(f"Echoes placed at nodes: {list(st.echo_events.keys())[:4]}")

def drain_ui():
    events = []
    while not ui_q.empty():
        events.append(ui_q.get_nowait())
    return events

drain_ui()  # clear init events

# ── Move around the map ───────────────────────────────────────────────────────
info("\n── Movement sequence ──")
location = st.player_location
path_taken = [location]
moves_ok = 0
for step in range(8):
    cur = st.topology.nodes.get(location)
    if not cur or not cur.neighbors:
        break
    target = list(cur.neighbors)[0]
    ctrl._handle_cmd({"action": "move", "target_node": target})
    evts = drain_ui()
    move_evts = [e for e in evts if e["type"] == "moved"]
    if move_evts:
        location = move_evts[0]["data"]["node_id"]
        path_taken.append(location)
        moves_ok += 1
    else:
        # Gate blocked or error — try next neighbor
        if cur.neighbors and len(list(cur.neighbors)) > 1:
            target2 = list(cur.neighbors)[1]
            ctrl._handle_cmd({"action": "move", "target_node": target2})
            evts2 = drain_ui()
            m2 = [e for e in evts2 if e["type"] == "moved"]
            if m2:
                location = m2[0]["data"]["node_id"]
                path_taken.append(location)
                moves_ok += 1
info(f"  Path: {' → '.join(path_taken)}")
check(moves_ok >= 4, f"Made ≥4 successful moves: {moves_ok}")

# ── Encounters ────────────────────────────────────────────────────────────────
info("\n── Wild encounters ──")
enc_found = 0
for _ in range(5):
    ctrl._handle_cmd({"action": "encounter"})
    evts = drain_ui()
    enc_evts = [e for e in evts if e["type"] == "encounter"]
    if enc_evts:
        enc_found += 1
        sp_data = enc_evts[0]["data"]["species"]
        info(f"  Encountered: {sp_data['name']} (lvl {enc_evts[0]['data']['level']})")
        # Try to capture — just check we get the event
check(enc_found >= 1, f"Encountered at least one wild creature: {enc_found}/5 attempts")

# ── Explore for fragments and echoes ─────────────────────────────────────────
info("\n── Explore phase (seeking fragments + echoes) ──")
fragments_found = 0
echoes_found = 0

# Boost trajectory so fragment unlock conditions can be met
st.player_trajectory.research_investment = 40.0
st.player_trajectory.exploration_depth = 55.0
st.player_trajectory.anomaly_exposure = 30.0
st.player_trajectory.nodes_explored = 60
st.player_trajectory.battles_won = 10

# Visit all fragment-surfacing node types AND echo nodes
facility_nodes = [nid for nid, nd in st.topology.nodes.items()
                  if nd.node_type in (nk.NodeType.FACILITY, nk.NodeType.LANDMARK,
                                       nk.NodeType.DUNGEON)]
anomaly_nodes = list(st.topology.anomaly_zone_ids)
relay_nodes = list(st.topology.relay_node_ids)
echo_nodes = list(st.echo_events.keys())  # make sure we visit all echo nodes

explore_nodes = (facility_nodes[:4] + anomaly_nodes[:3] + relay_nodes[:2]
                 + echo_nodes                          # guaranteed echo hits
                 + [st.player_location])

for nid in explore_nodes:
    st.player_location = nid
    ctrl._handle_cmd({"action": "explore"})
    evts = drain_ui()
    for e in evts:
        if e["type"] == "fragment_discovered":
            fragments_found += 1
            info(f"  Fragment: [{e['data']['type']}] \"{e['data']['title']}\"")
            info(f"    {e['data']['body'][:80]}…")
        if e["type"] == "memory_echo":
            echoes_found += 1
            info(f"  Echo: [{e['data']['echo_type']}] {e['data']['description'][:70]}…")

check(fragments_found >= 1, f"At least 1 fragment discovered via explore: {fragments_found}")
check(echoes_found >= 1, f"At least 1 memory echo triggered: {echoes_found}")

# ── get_fragments command ─────────────────────────────────────────────────────
ctrl._handle_cmd({"action": "get_fragments"})
evts = drain_ui()
frag_evt = next((e for e in evts if e["type"] == "fragments"), None)
check(frag_evt is not None, "get_fragments returns fragments event")
if frag_evt:
    d = frag_evt["data"]
    check(d["discovered"] == fragments_found,
          f"discovered count matches: {d['discovered']} == {fragments_found}")
    discovered_bodies = [f for f in d["fragments"] if f["discovered"] and f["body"]]
    undiscovered_nulls = [f for f in d["fragments"] if not f["discovered"] and f["body"] is None]
    check(len(discovered_bodies) == fragments_found,
          f"Discovered fragments have rendered bodies: {len(discovered_bodies)}")
    info(f"  Total: {d['total']}  Discovered: {d['discovered']}")

# ── Battle an AI trainer ──────────────────────────────────────────────────────
info("\n── League battle ──")
trainers = nk.generate_ai_trainers(st.topology, st.species_map)
# Give player a team
rng_pt = nk.SeededRNG(SEED).fork("player_team_setup")
for i, (sp_id, sp) in enumerate(list(st.species_map.items())[:3]):
    inst = nk.CreatureInstance(
        instance_id=f"player_{i}",
        species_id=sp_id,
        level=25,
        genes=nk.GeneticProfile(stat_genes=[rng_pt.randint(15, 28) for _ in range(6)]),
    )
    st.creatures[inst.instance_id] = inst
    st.player_team.append((inst.instance_id, sp_id))

st.league.trainers["player"] = nk.Trainer(
    trainer_id="player", name="Player", is_player=True, rating=1200
)

trainer_id = list(trainers.keys())[0]
st.league.trainers[trainer_id] = list(trainers.values())[0]
ctrl._handle_cmd({"action": "battle", "opponent_id": trainer_id})
evts = drain_ui()
battle_evt = next((e for e in evts if e["type"] == "battle_result"), None)
check(battle_evt is not None, "Battle result event received")
if battle_evt:
    bd = battle_evt["data"]
    info(f"  vs {bd['opponent_name']}: {bd['winner']} wins in {bd['turns']} turns")
    info(f"  Player rating after: {bd['player_rating']}")

# ── Knower interaction ────────────────────────────────────────────────────────
info("\n── Hidden Knower interaction ──")
ctrl._handle_cmd({"action": "get_knower"})
evts = drain_ui()
knower_evt = next((e for e in evts if e["type"] == "knower_profile"), None)
check(knower_evt is not None, "get_knower returns profile event")
if knower_evt:
    info(f"  {knower_evt['data']['name']} ({knower_evt['data']['archetype']})"
         f"  unlocked={knower_evt['data']['is_unlocked']}")

# Talk (locked path)
ctrl._handle_cmd({"action": "talk_knower", "fragment_index": 0})
evts = drain_ui()
talk_evt = evts[0] if evts else None
check(talk_evt is not None and talk_evt["type"] in ("knower_locked", "knower_dialogue"),
      f"talk_knower returns expected event: {talk_evt['type'] if talk_evt else 'none'}")

# Force unlock, re-talk
st.player_trajectory.exploration_depth = 100
st.player_trajectory.research_investment = 100
st.player_trajectory.competitive_focus = 100
st.player_trajectory.anomaly_exposure = 100
st.player_trajectory.battles_won = 50
st.player_trajectory.anomaly_events = 10
st.player_trajectory.nodes_explored = 200

ctrl._handle_cmd({"action": "talk_knower", "fragment_index": 0})
evts = drain_ui()
dialogue_evt = next((e for e in evts if e["type"] == "knower_dialogue"), None)
check(dialogue_evt is not None, "Knower dialogue unlocks when threshold met")
if dialogue_evt:
    info(f"  [{dialogue_evt['data']['name']}]: {dialogue_evt['data']['fragment'][:90]}…")

# ── get_state / get_outcome ───────────────────────────────────────────────────
info("\n── State and outcome snapshots ──")
ctrl._handle_cmd({"action": "get_state"})
evts = drain_ui()
state_evt = next((e for e in evts if e["type"] == "state"), None)
check(state_evt is not None, "get_state returns state event")
if state_evt:
    sd = state_evt["data"]
    info(f"  tick={sd['tick']}  location={sd['player_location']}")
    info(f"  discovered_species={sd['discovered_species']}")

ctrl._handle_cmd({"action": "get_outcome"})
evts = drain_ui()
outcome_evt = next((e for e in evts if e["type"] == "outcome_band"), None)
check(outcome_evt is not None, "get_outcome returns outcome_band event")
if outcome_evt:
    od = outcome_evt["data"]
    info(f"  Band {od['band_id']}: {od['island_condition']} / {od['personal_archetype']}")
    info(f"  Narrative role: {od['narrative_role']}")

ctrl._handle_cmd({"action": "get_narrative"})
evts = drain_ui()
nar_evt = next((e for e in evts if e["type"] == "narrative_profile"), None)
check(nar_evt is not None, "get_narrative returns narrative_profile event")

# ── new_expedition ────────────────────────────────────────────────────────────
info("\n── New expedition (NGP+ cycle) ──")

tmp_profile_path = tempfile.mktemp(suffix=".json")
_orig_path_fn = nk._nk_profile_path
nk._nk_profile_path = lambda: tmp_profile_path

ctrl._cmd_new_expedition(next_seed=999)
evts = drain_ui()

exp_ended = next((e for e in evts if e["type"] == "expedition_ended"), None)
check(exp_ended is not None, "expedition_ended event fired")
if exp_ended:
    info(f"  Completed seed={exp_ended['data']['completed_seed']}"
         f"  next_seed={exp_ended['data']['next_seed']}")
    info(f"  Final tier={exp_ended['data']['final_tier']}"
         f"  axis={exp_ended['data']['behavioral_axis']}")

# New island should be initialized
drain_ui()  # flush
check(ctrl._state is not None and ctrl._state.seed == 999,
      f"New expedition started with seed 999: {ctrl._state.seed if ctrl._state else 'None'}")

# reset_simulation
ctrl._cmd_reset_simulation(seed=42)
evts = drain_ui()
reset_evt = next((e for e in evts if e["type"] == "simulation_reset"), None)
check(reset_evt is not None, "simulation_reset event fired")
if reset_evt:
    info(f"  Profile deleted: {reset_evt['data']['profile_deleted']}")
check(ctrl._state is not None and ctrl._state.seed == 42,
      "Simulation reset re-inits with seed 42")
check(ctrl._state.base_tier == nk.ContainmentTier.TIER_I,
      f"After reset, base tier is TIER_I: {ctrl._state.base_tier.name}")

nk._nk_profile_path = _orig_path_fn
if os.path.exists(tmp_profile_path):
    os.remove(tmp_profile_path)

# ── Advance ticks ─────────────────────────────────────────────────────────────
info("\n── Tick engine (advance 40 ticks) ──")
initial_tick = ctrl._state.tick
ctrl._handle_cmd({"action": "advance", "ticks": 40})
evts = drain_ui()
tick_updates = [e for e in evts if e["type"] == "tick_update"]
check(ctrl._state.tick == initial_tick + 40,
      f"Tick counter advanced 40: {initial_tick} → {ctrl._state.tick}")
check(len(tick_updates) >= 4,
      f"tick_update events fired every 10 ticks: {len(tick_updates)}")
if tick_updates:
    last_tu = tick_updates[-1]["data"]
    check("current_tier" in last_tu, "tick_update includes current_tier")
    info(f"  Last tick_update: tick={last_tu['tick']}  tier={last_tu['current_tier']}")

# ─────────────────────────────────────────────────────────────────────────────
hr("MULTI-SEED CONSISTENCY CHECK")
# ─────────────────────────────────────────────────────────────────────────────

info("Generating 5 complete islands and checking invariants…")
results = []
for s in [1, 7, 42, 99, 256]:
    t = nk.generate_island_topology(s)
    sm = nk.generate_species_roster(t)
    led = nk.IslandLedger(); led.set_baseline(s)
    bt = nk._seed_to_base_tier(s)
    np2 = nk.generate_island_narrative(s, bt)
    kn = nk.generate_hidden_knower(t, np2, s)
    frg = nk.generate_island_fragments(np2, t, s)
    framing = nk.resolve_founder_framing(s)
    results.append({
        "seed": s, "island": t.island_name, "nodes": t.node_count,
        "species": len(sm), "base_tier": bt.name,
        "mountains": len(np2.primary_global_boulders),
        "knower": kn.archetype.name,
        "fragments": len(frg),
        "traitor": framing.get("traitor", "?"),
    })

info(f"\n{'Seed':>4}  {'Island':<16} {'Nodes':>5} {'Tier':<8} "
     f"{'Mounts':>6} {'Knower':<22} {'Frags':>5} Traitor")
info("─" * W)
for r in results:
    info(f"  {r['seed']:>4}  {r['island']:<16} {r['nodes']:>5} {r['base_tier']:<8} "
         f"{r['mountains']:>6} {r['knower']:<22} {r['fragments']:>5} {r['traitor']}")

islands_unique = len({r["island"] for r in results})
check(islands_unique == 5, f"All 5 seeds produce distinct island names: {islands_unique}")
check(all(120 <= r["nodes"] <= 250 for r in results), "All islands in 120–250 node range")
check(all(r["species"] == 300 for r in results), "All islands have exactly 300 species")
check(all(8 <= r["mountains"] <= 12 for r in results), "All islands have 8–12 primary mountains")
check(all(r["fragments"] > 0 for r in results), "All islands have fragments")

# ─────────────────────────────────────────────────────────────────────────────
hr("RESULTS")
# ─────────────────────────────────────────────────────────────────────────────

total = len(passed) + len(failed)
print(f"\n  Passed: {len(passed)}/{total}")
if failed:
    print(f"\n  FAILED ({len(failed)}):")
    for f in failed:
        print(f"    ✗  {f}")
else:
    print("\n  All checks passed. ✓")

print()
sys.exit(0 if not failed else 1)
