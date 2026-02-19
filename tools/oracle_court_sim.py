#!/usr/bin/env python3
"""
oracle_court_sim.py — Court Layer Test Harness

Runs oracle_kingdom (world) + oracle_court (court) together,
with an automated oracle that moves between rooms and issues
decrees every few ticks.  Reports the full court state evolution.

Usage:
    python tools/oracle_court_sim.py [--seed N] [--ticks N] [--stress]

    --seed N    : RNG seed (default 42)
    --ticks N   : simulation length (default 500)
    --stress    : start the kingdom in a stressed state (higher tensions)
"""

from __future__ import annotations

import argparse
import math
import sys
import os
import time

# ── Path setup ────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "plugins_disabled"))

import oracle_kingdom as ok
import oracle_court as oc


# ============================================================
# HELPERS
# ============================================================

def stress_kingdom(ks: ok.KingdomState):
    """
    Push kingdom into a stressed state so CTA templates fire.
    Simulates a kingdom that has been poorly managed.
    """
    ks.political.external_threat = 55.0
    ks.political.corruption = 50.0
    ks.political.enforcement_capacity = 35.0
    ks.social.class_tension = 60.0
    ks.social.cohesion = 35.0
    ks.social.fear_level = 40.0
    ks.social.literacy = 22.0
    ks.belief.public_faith = 30.0
    ks.belief.interpretation_divergence = 30.0
    ks.physical.trade_volume = 20.0
    ks.physical.treasury = 250.0


# ── Automated oracle behavior ──

MOVE_SCHEDULE = [
    # (tick_offset, location)  — oracle moves on this schedule
    (0,   oc.LocationId.THRONE_ROOM),
    (15,  oc.LocationId.WAR_CHAMBER),
    (30,  oc.LocationId.TEMPLE),
    (50,  oc.LocationId.COURTYARD),
    (65,  oc.LocationId.HARBOR),
    (80,  oc.LocationId.LIBRARY),
    (95,  oc.LocationId.OBSERVATORY),
    (105, oc.LocationId.TREASURY),
    (115, oc.LocationId.RAMPARTS),
    (130, oc.LocationId.THRONE_ROOM),
]

DECREE_INTERVAL = 8   # issue a decree every N ticks
SILENCE_CHANCE  = 0.2  # 20% chance of choosing silence


def pick_move(tick: int) -> oc.LocationId | None:
    """Return a location if the oracle should move this tick, else None."""
    cycle_len = MOVE_SCHEDULE[-1][0] + 20  # ~150 tick cycle
    t = tick % cycle_len
    for offset, loc in MOVE_SCHEDULE:
        if t == offset:
            return loc
    return None


def auto_decree(court: oc.CourtState, kingdom: ok.KingdomState,
                rng: ok.SeededRNG) -> oc.CourtDecreeOption | None:
    """
    Auto-choose a decree.  Picks the first non-silence option
    unless SILENCE_CHANCE triggers.
    """
    options = oc.CourtDecreeGenerator.generate(court, kingdom, rng)
    if not options:
        return None

    gen_rng = rng.fork(f"auto_decree_{kingdom.tick}")

    # Chance of silence
    if gen_rng.random() < SILENCE_CHANCE:
        return options[-1]  # silence is always last

    # Pick the option with highest agent trust (most supported)
    non_silence = [o for o in options if not o.is_silence]
    if not non_silence:
        return options[-1]

    # Weighted random by agent trust
    weights = [max(1.0, o.agent_trust) for o in non_silence]
    total = sum(weights)
    roll = gen_rng.random() * total
    cumulative = 0.0
    for i, w in enumerate(weights):
        cumulative += w
        if roll <= cumulative:
            return non_silence[i]
    return non_silence[0]


# ============================================================
# REPORTER
# ============================================================

class Reporter:
    """Accumulates and prints simulation statistics."""

    def __init__(self):
        self.decree_count = 0
        self.silence_count = 0
        self.move_count = 0
        self.cta_requests_total = 0
        self.cta_signals_total = 0
        self.thoughts_total = 0
        self.deaths = 0
        self.successions = 0
        self.snapshots: list[dict] = []

    def snapshot(self, tick: int, court: oc.CourtState, kingdom: ok.KingdomState):
        """Take a periodic snapshot."""
        self.snapshots.append({
            "tick": tick,
            "location": court.current_location.name,
            "composite": kingdom.health.composite,
            "active_reqs": len(court.active_requests),
            "active_sigs": len(court.active_signals),
            "req_history": len(court.request_history),
            "sig_history": len(court.signal_history),
            "thoughts": len(court.inner_state.thought_log),
            "archetype": court.oracle_identity.archetype.name,
            "silence_ticks": court.inner_state.total_silence_ticks,
            "agents": {
                aid: {
                    "name": kingdom.characters.get(a.character_id, ok.Character()).name,
                    "trust": a.trust,
                    "fear": a.fear,
                    "admiration": a.admiration,
                    "resentment": a.resentment,
                    "memories": len(a.memories),
                    "tone": a.narrative_tone,
                    "label": a.oracle_label,
                    "consistency": a.perceived_consistency,
                    "decisiveness": a.perceived_decisiveness,
                }
                for aid, a in court.agents.items()
            },
        })

    def print_report(self, court: oc.CourtState, kingdom: ok.KingdomState):
        """Print final report."""
        print("\n" + "=" * 70)
        print("  ORACLE COURT SIMULATION REPORT")
        print("=" * 70)
        print(f"  Ticks simulated: {kingdom.tick}")
        print(f"  Decrees issued:  {self.decree_count}")
        print(f"  Silences chosen: {self.silence_count}")
        print(f"  Oracle moves:    {self.move_count}")
        print(f"  CTA requests:    {self.cta_requests_total}")
        print(f"  CTA signals:     {self.cta_signals_total}")
        print(f"  Inner thoughts:  {self.thoughts_total}")
        print(f"  Agent deaths:    {self.deaths}")
        print()

        # ── Kingdom final state ──
        print("── Kingdom Health ─────────────────────────────────")
        print(f"  Composite:   {kingdom.health.composite:.1f}")
        print(f"  Legitimacy:  {kingdom.political.legitimacy:.1f}")
        print(f"  Ext. threat: {kingdom.political.external_threat:.1f}")
        print(f"  Corruption:  {kingdom.political.corruption:.1f}")
        print(f"  Class tens.: {kingdom.social.class_tension:.1f}")
        print(f"  Faith:       {kingdom.belief.public_faith:.1f}")
        print(f"  Trade vol:   {kingdom.physical.trade_volume:.1f}")
        print(f"  Treasury:    {kingdom.physical.treasury:.1f}")
        print()

        # ── Oracle identity ──
        print("── Oracle Identity ────────────────────────────────")
        oid = court.oracle_identity
        print(f"  Archetype:   {oid.archetype.name}")
        print(f"  Axis usage:  ", end="")
        sorted_axes = sorted(oid.axis_usage.items(), key=lambda x: -x[1])
        for ax, val in sorted_axes[:5]:
            if val > 0:
                print(f"{ax}={val:.1f} ", end="")
        print()
        print(f"  Silence ratio: {oid.silence_count}/{oid.decree_count} decrees")
        print()

        # ── Agent final state ──
        print("── Court Agents ───────────────────────────────────")
        for aid, agent in court.agents.items():
            char = kingdom.characters.get(agent.character_id)
            name = char.name if char else "?"
            faction = kingdom.factions.get(char.faction_id) if char else None
            arch = faction.archetype.name if faction else "?"
            print(f"  {name} ({arch})")
            print(f"    trust={agent.trust:.1f}  fear={agent.fear:.1f}  "
                  f"adm={agent.admiration:.1f}  res={agent.resentment:.1f}")
            print(f"    consistency={agent.perceived_consistency:.1f}  "
                  f"decisiveness={agent.perceived_decisiveness:.1f}")
            print(f"    memories={len(agent.memories)}  tone={agent.narrative_tone}  "
                  f"label=\"{agent.oracle_label}\"")
            print(f"    petitions_ignored={agent.petitions_ignored}  "
                  f"times_rewarded={agent.times_rewarded}")
            # Top memories
            if agent.memories:
                top = sorted(agent.memories, key=lambda m: abs(m.current_weight), reverse=True)[:3]
                for m in top:
                    print(f"      [{m.memory_type.name}] w={m.current_weight:.2f}: {m.description[:50]}")
        print()

        # ── Faction Memory ──
        print("── Faction Memories ───────────────────────────────")
        for fid, fm in court.faction_memories.items():
            faction = kingdom.factions.get(fid)
            fname = faction.name if faction else fid
            print(f"  {fname}: trust={fm.collective_trust:.1f}  "
                  f"resentment={fm.collective_resentment:.1f}  "
                  f"memories={len(fm.memories)}")
        print()

        # ── Inner Thoughts ──
        print("── Inner Narrator ─────────────────────────────────")
        inner = court.inner_state
        print(f"  Total silence ticks: {inner.total_silence_ticks}")
        print(f"  Existential pressure: {inner.existential_pressure:.2f}")
        print(f"  Legacy anxiety: {inner.legacy_anxiety:.2f}")
        print(f"  Suppressed thoughts: {inner.suppressed_thoughts:.2f}")
        print(f"  Locations visited: {len(inner.location_history)}")
        if inner.thought_log:
            print(f"  Thoughts generated: {len(inner.thought_log)}")
            for t in inner.thought_log[-5:]:
                print(f"    [tick {t.tick}] ({t.thought_type.name}) \"{t.text}\"")
                print(f"      trait={t.dominant_trait} tension={t.tension_level:.2f}")
        else:
            print("  No inner thoughts generated.")
        print()

        # ── Timeline ──
        print("── Timeline (snapshots every 50 ticks) ────────────")
        for snap in self.snapshots:
            agents_str = ""
            for aid, a in snap["agents"].items():
                agents_str += f" {a['name'][:8]}(t={a['trust']:.0f}/r={a['resentment']:.0f}/{a['tone']})"
            print(f"  tick={snap['tick']:>4} loc={snap['location']:<14} "
                  f"hp={snap['composite']:.0f} reqs={snap['active_reqs']} "
                  f"sigs={snap['active_sigs']} thoughts={snap['thoughts']} "
                  f"arch={snap['archetype']}")
            if agents_str:
                print(f"        {agents_str.strip()}")
        print()

        # ── Serialization check ──
        d = court.to_dict()
        court2 = oc.CourtState.from_dict(d)
        print(f"  Serialization round-trip: "
              f"agents={len(court2.agents)} "
              f"factions={len(court2.faction_memories)} OK")
        print()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Oracle Court Simulation")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ticks", type=int, default=500)
    parser.add_argument("--stress", action="store_true",
                        help="Start kingdom in stressed state")
    args = parser.parse_args()

    SEED = args.seed
    TICKS = args.ticks

    print(f"Oracle Court Sim — seed={SEED}, ticks={TICKS}, stress={args.stress}")
    print()

    # ── Build world ──
    rng = ok.SeededRNG(SEED)
    oracle = ok.OracleBuild.random_build(rng)
    ks = ok.WorldBuilder.build_kingdom("court_test", SEED, is_player=True, oracle=oracle)

    if args.stress:
        stress_kingdom(ks)

    # ── Build court ──
    court = oc.CourtBuilder.build(ks)

    reporter = Reporter()
    t0 = time.perf_counter()

    prev_agent_count = len(court.agents)
    prev_thought_count = 0

    for tick in range(1, TICKS + 1):
        tick_rng = ok.SeededRNG(SEED + tick)

        # ── World tick ──
        ok.SimulationEngine.advance_tick(ks, tick_rng, ok.TimeConfig())

        # ── Oracle movement ──
        move_target = pick_move(tick)
        if move_target is not None:
            oc.CourtEngine.move_oracle(court, ks, move_target)
            reporter.move_count += 1

        # ── Court tick ──
        prev_req = len(court.active_requests) + len(court.request_history)
        prev_sig = len(court.active_signals) + len(court.signal_history)
        oc.CourtEngine.tick(court, ks, tick_rng)
        new_reqs = (len(court.active_requests) + len(court.request_history)) - prev_req
        new_sigs = (len(court.active_signals) + len(court.signal_history)) - prev_sig
        if new_reqs > 0:
            reporter.cta_requests_total += new_reqs
        if new_sigs > 0:
            reporter.cta_signals_total += new_sigs

        # ── Inner thoughts ──
        current_thoughts = len(court.inner_state.thought_log)
        if current_thoughts > prev_thought_count:
            reporter.thoughts_total += (current_thoughts - prev_thought_count)
            prev_thought_count = current_thoughts

        # ── Auto-decree ──
        if tick % DECREE_INTERVAL == 0:
            option = auto_decree(court, ks, tick_rng)
            if option:
                events = oc.CourtPropagationBridge.propagate_court_decree(
                    court, ks, option, tick_rng
                )
                if option.is_silence:
                    reporter.silence_count += 1
                else:
                    reporter.decree_count += 1

        # ── Agent lifecycle tracking ──
        if len(court.agents) != prev_agent_count:
            diff = prev_agent_count - len(court.agents)
            if diff > 0:
                reporter.deaths += diff
            prev_agent_count = len(court.agents)

        # ── Periodic snapshot ──
        if tick % 50 == 0 or tick == 1:
            reporter.snapshot(tick, court, ks)

        # ── Verbose events ──
        if tick <= 5 or tick % 100 == 0:
            tension = oc.InnerNarratorEngine.compute_inner_tension(ks, court)
            print(f"  [tick {tick:>4}] loc={court.current_location.name:<14} "
                  f"hp={ks.health.composite:.0f} "
                  f"threat={ks.political.external_threat:.0f} "
                  f"tension_score={tension:.2f} "
                  f"reqs={len(court.active_requests)} "
                  f"sigs={len(court.active_signals)} "
                  f"thoughts={len(court.inner_state.thought_log)}")

    elapsed = time.perf_counter() - t0
    print(f"\n  Elapsed: {elapsed:.2f}s  ({TICKS / elapsed:.0f} ticks/sec)")

    reporter.print_report(court, ks)
