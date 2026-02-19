#!/usr/bin/env python3
"""
oracle_sim.py — Headless Oracle Kingdom Simulation

Spawns a seed world with N kingdoms, each governed by an AI Oracle
that autonomously picks decrees every DECREE_INTERVAL ticks.

Run:
    python tools/oracle_sim.py                          # defaults
    python tools/oracle_sim.py --seed 42 --kingdoms 6 --ticks 2000
    python tools/oracle_sim.py --seed 42 --ticks 1000 --verbose

The simulation prints a live dashboard every REPORT_INTERVAL ticks
showing each kingdom's trajectory side-by-side, then a final
divergence report.  Use this to observe the "pebble in a pond"
effect: identical starting conditions + one tiny decree difference
→ vastly different outcomes by tick 1000.
"""

import argparse
import math
import os
import sys
import time
import copy

# Add project root to path so we can import oracle_kingdom
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugins_disabled"))

# Suppress debug output during simulation
os.environ["FTB_DEBUG"] = ""

import oracle_kingdom as ok

# ────────────────────────────────────────────────────────────
# AI ORACLE — Simple heuristic decree selection
# ────────────────────────────────────────────────────────────

class AIOracle:
    """
    Autonomous Oracle decision engine.

    Uses the same SpeechGenerator as the player but selects options
    via a scored heuristic:
      - Highest affinity to Oracle build (personality)
      - Weighted toward current kingdom needs (responsive)
      - Small random noise (so two identical builds diverge slightly)
    """

    @staticmethod
    def choose_and_issue_decree(kingdom: ok.KingdomState, rng: ok.SeededRNG) -> dict:
        """
        Generate decree options, pick the best one, propagate it.
        Returns a summary dict for logging.
        """
        gen_rng = rng.fork(f"ai_decree_{kingdom.tick}")

        # Generate options
        options = ok.SpeechGenerator.generate_decree_options(kingdom, gen_rng, count=4)
        if not options:
            return {"action": "silence", "tick": kingdom.tick}

        # Score each option
        scored = []
        for opt in options:
            score = _score_option(opt, kingdom, gen_rng)
            scored.append((score, opt))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Pick: 70% chance of top option, 20% second, 10% random
        roll = gen_rng.random()
        if roll < 0.70 and len(scored) >= 1:
            chosen = scored[0][1]
        elif roll < 0.90 and len(scored) >= 2:
            chosen = scored[1][1]
        else:
            chosen = scored[gen_rng.randint(0, len(scored) - 1)][1]

        # Propagate the decree through the sim
        events = ok.PropagationEngine.propagate_decree(kingdom, chosen, gen_rng)

        # Record in decree history
        kingdom.decree_history.append(ok.DecreeRecord(
            decree_id=chosen.option_id,
            tick=kingdom.tick,
            text=chosen.text,
            tone=chosen.tone.name,
            mode=chosen.mode.name,
            policy_vector=dict(chosen.policy_vector),
        ))

        # Update myth memory
        ok.MythMemory.tick_memory(kingdom, gen_rng)

        return {
            "action": "decree",
            "tick": kingdom.tick,
            "text": chosen.text[:60],
            "tone": chosen.tone.name,
            "events": len(events),
        }


def _score_option(opt: ok.SpeechOption, kingdom: ok.KingdomState,
                  rng: ok.SeededRNG) -> float:
    """Score an option based on kingdom needs + Oracle personality."""
    score = 0.0
    oracle = kingdom.oracle
    p = kingdom.physical
    s = kingdom.social
    pol = kingdom.political
    b = kingdom.belief

    # Personality affinity (Oracle prefers its natural tendencies)
    for trait_name in ok.ORACLE_TRAITS:
        val = oracle.effective(trait_name) / 50.0  # 0→1
        # Conviction likes bold moves (high magnitude)
        if trait_name == "conviction":
            score += val * opt.propagation_magnitude * 0.3
        # Empathy likes mercy/hope options
        if trait_name == "empathy":
            if "mercy_focus" in opt.policy_vector:
                score += val * opt.policy_vector["mercy_focus"] * 0.5
        # Clarity prefers practical tone
        if trait_name == "clarity":
            if opt.tone == ok.Tone.PRACTICAL:
                score += val * 0.3
        # Self-belief likes bold tones
        if trait_name == "self_belief":
            if opt.tone == ok.Tone.SEVERE:
                score += val * 0.2

    # Kingdom needs (responsive governance)
    vec = opt.policy_vector
    if "agriculture_focus" in vec and p.resource_pressure > 40:
        score += (p.resource_pressure / 100.0) * vec["agriculture_focus"] * 2.0
    if "trade_focus" in vec and p.trade_volume < 30:
        score += (1.0 - p.trade_volume / 100.0) * vec.get("trade_focus", 0) * 1.5
    if "military_focus" in vec and pol.external_threat > 40:
        score += (pol.external_threat / 100.0) * vec.get("military_focus", 0) * 1.5
    if "faith_focus" in vec and b.public_faith < 40:
        score += (1.0 - b.public_faith / 100.0) * vec.get("faith_focus", 0) * 1.5
    if "reform_focus" in vec and pol.corruption > 40:
        score += (pol.corruption / 100.0) * vec.get("reform_focus", 0) * 1.2
    if "mercy_focus" in vec and s.fear_level > 50:
        score += (s.fear_level / 100.0) * vec.get("mercy_focus", 0) * 1.0
    if "justice_focus" in vec and s.class_tension > 50:
        score += (s.class_tension / 100.0) * vec.get("justice_focus", 0) * 1.0

    # Small noise to break symmetry
    score += rng.gauss(0, 0.3)

    return score


# ────────────────────────────────────────────────────────────
# WORLD RUNNER
# ────────────────────────────────────────────────────────────

def build_multi_kingdom_world(master_seed: int, num_kingdoms: int,
                              shared_start: bool = True) -> list:
    """
    Build N kingdoms.  If shared_start=True, all start from the
    SAME initial conditions (same layer values, same factions)
    but with different Oracle builds.  This isolates the Oracle's
    decree-driven divergence.

    If shared_start=False, each kingdom gets its own seeded
    initial conditions (natural variance).
    """
    master_rng = ok.SeededRNG(master_seed)
    kingdoms = []

    # Generate the first kingdom as the template
    template_seed = master_rng.fork("template").seed
    template = ok.WorldBuilder.build_kingdom(
        kingdom_id="k0",
        seed=template_seed,
        is_player=False,
    )

    for i in range(num_kingdoms):
        if shared_start and i > 0:
            # Clone template layers but give unique Oracle + id
            ks = copy.deepcopy(template)
            ks.kingdom_id = f"k{i}"
            ks.name = ok.WorldBuilder.generate_kingdom_name(master_rng.fork(f"name_{i}"))
            ks.oracle = ok.OracleBuild.random_build(master_rng.fork(f"oracle_{i}"))
            ks.seed = master_rng.fork(f"kseed_{i}").seed
        else:
            kseed = master_rng.fork(f"kingdom_{i}").seed
            ks = ok.WorldBuilder.build_kingdom(
                kingdom_id=f"k{i}",
                seed=kseed,
                is_player=False,
            )
        kingdoms.append(ks)

    return kingdoms


def snapshot_kingdom(k: ok.KingdomState) -> dict:
    """Extract key variables for dashboard display."""
    p = k.physical
    s = k.social
    pol = k.political
    b = k.belief
    h = k.health

    return {
        "name": k.name,
        "id": k.kingdom_id,
        "tick": k.tick,
        "health": round(getattr(h, "composite", 50.0), 1),
        "food": round(p.food_stores, 1),
        "rp": round(p.resource_pressure, 1),
        "infra": round(p.infrastructure, 1),
        "trade": round(p.trade_volume, 1),
        "treasury": round(p.treasury, 0),
        "tension": round(s.class_tension, 1),
        "cohesion": round(s.cohesion, 1),
        "hope": round(s.hope_level, 1),
        "fear": round(s.fear_level, 1),
        "faith": round(b.public_faith, 1),
        "divergence": round(b.interpretation_divergence, 1),
        "legitimacy": round(pol.legitimacy, 1),
        "corruption": round(pol.corruption, 1),
        "inst_strength": round(pol.institutional_strength, 1),
        "enforcement": round(pol.enforcement_capacity, 1),
        "era": k.current_era.name if hasattr(k.current_era, "name") else str(k.current_era),
        "decrees": len(k.decree_history),
        "events": len(k.event_history),
        "scars": len(k.institutional_scars) if hasattr(k, "institutional_scars") else 0,
    }


# ────────────────────────────────────────────────────────────
# DISPLAY
# ────────────────────────────────────────────────────────────

# ANSI colours for kingdom columns
COLOURS = [
    "\033[96m",   # cyan
    "\033[93m",   # yellow
    "\033[92m",   # green
    "\033[95m",   # magenta
    "\033[91m",   # red
    "\033[94m",   # blue
    "\033[97m",   # white
    "\033[33m",   # dark yellow
]
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def _bar(value: float, width: int = 20, lo: float = 0, hi: float = 100) -> str:
    """Render a value as a mini bar chart."""
    frac = max(0.0, min(1.0, (value - lo) / max(1, hi - lo)))
    filled = int(frac * width)
    empty = width - filled
    # Colour by zone
    if frac < 0.25:
        col = "\033[91m"  # red
    elif frac < 0.5:
        col = "\033[93m"  # yellow
    elif frac < 0.75:
        col = "\033[92m"  # green
    else:
        col = "\033[96m"  # cyan
    return f"{col}{'█' * filled}{'░' * empty}{RESET}"


def print_dashboard(kingdoms: list, tick: int, decree_logs: dict):
    """Print a side-by-side dashboard of all kingdoms."""
    snaps = [snapshot_kingdom(k) for k in kingdoms]

    print(f"\n{'═' * 100}")
    print(f"{BOLD}  ORACLE KINGDOM SIMULATION — Tick {tick}{RESET}")
    print(f"{'═' * 100}")

    # Header row
    header = f"{'Variable':<22}"
    for i, s in enumerate(snaps):
        col = COLOURS[i % len(COLOURS)]
        header += f"  {col}{s['name'][:14]:<14}{RESET}"
    print(header)
    print(f"{'─' * 100}")

    # Key variables
    rows = [
        ("Health (composite)", "health", 0, 100),
        ("Food Stores", "food", 0, 200),
        ("Resource Pressure", "rp", 0, 100),
        ("Infrastructure", "infra", 0, 100),
        ("Trade Volume", "trade", 0, 100),
        ("Class Tension", "tension", 0, 100),
        ("Social Cohesion", "cohesion", 0, 100),
        ("Hope", "hope", 0, 100),
        ("Fear", "fear", 0, 100),
        ("Public Faith", "faith", 0, 100),
        ("Interpretation Div", "divergence", 0, 100),
        ("Legitimacy", "legitimacy", 0, 100),
        ("Corruption", "corruption", 0, 100),
        ("Inst. Strength", "inst_strength", 0, 100),
        ("Enforcement", "enforcement", 0, 100),
    ]

    for label, key, lo, hi in rows:
        line = f"  {label:<20}"
        for i, s in enumerate(snaps):
            val = s[key]
            bar = _bar(val, width=10, lo=lo, hi=hi)
            line += f"  {bar} {val:>6}"
        print(line)

    # Meta row
    print(f"{'─' * 100}")
    meta_line = f"  {'Era':<20}"
    for i, s in enumerate(snaps):
        col = COLOURS[i % len(COLOURS)]
        meta_line += f"  {col}{s['era'][:18]:<18}{RESET}"
    print(meta_line)

    meta_line = f"  {'Decrees / Events':<20}"
    for i, s in enumerate(snaps):
        meta_line += f"  {s['decrees']:>3}d / {s['events']:>3}e       "
    print(meta_line)

    meta_line = f"  {'Scars':<20}"
    for i, s in enumerate(snaps):
        meta_line += f"  {s['scars']:>3} scars         "
    print(meta_line)

    # Last decree per kingdom
    print(f"{'─' * 100}")
    print(f"  {DIM}Last decrees:{RESET}")
    for i, k in enumerate(kingdoms):
        col = COLOURS[i % len(COLOURS)]
        if k.decree_history:
            last = k.decree_history[-1]
            print(f"    {col}{k.name[:14]}{RESET}: [{last.tone}] \"{last.text[:55]}...\"")
        else:
            print(f"    {col}{k.name[:14]}{RESET}: (silence)")

    print()


def print_final_report(kingdoms: list, initial_snapshots: list):
    """Print divergence analysis after simulation completes."""
    final_snaps = [snapshot_kingdom(k) for k in kingdoms]

    print(f"\n{'━' * 100}")
    print(f"{BOLD}  FINAL DIVERGENCE REPORT{RESET}")
    print(f"{'━' * 100}\n")

    # Compute ranges for each variable
    vars_to_check = [
        "health", "food", "rp", "infra", "trade",
        "tension", "cohesion", "hope", "fear",
        "faith", "divergence", "legitimacy", "corruption",
        "inst_strength", "enforcement",
    ]

    print(f"  {'Variable':<22} {'Min':>8} {'Max':>8} {'Range':>8} {'Spread':>8}")
    print(f"  {'─' * 56}")

    total_range = 0.0
    for var in vars_to_check:
        values = [s[var] for s in final_snaps]
        vmin, vmax = min(values), max(values)
        vrange = vmax - vmin
        total_range += vrange
        # Colour by spread
        if vrange > 40:
            col = "\033[92m"  # green — high divergence, good!
        elif vrange > 20:
            col = "\033[93m"  # yellow
        else:
            col = "\033[91m"  # red — low divergence
        print(f"  {var:<22} {vmin:>8.1f} {vmax:>8.1f} {col}{vrange:>8.1f}{RESET} {'██' * min(10, int(vrange / 5))}")

    avg_range = total_range / len(vars_to_check)
    print(f"\n  {BOLD}Average cross-variable range: {avg_range:.1f}{RESET}")

    if avg_range > 20:
        print(f"  {BOLD}\033[92m✓ STRONG DIVERGENCE — pebble → destiny is working.{RESET}")
    elif avg_range > 8:
        print(f"  {BOLD}\033[93m◐ MODERATE DIVERGENCE — Oracle personality drives meaningfully different outcomes.{RESET}")
    else:
        print(f"  {BOLD}\033[91m✗ WEAK DIVERGENCE — system is too symmetric, more coupling needed.{RESET}")

    # Era comparison
    print(f"\n  {BOLD}Era outcomes:{RESET}")
    for i, k in enumerate(kingdoms):
        col = COLOURS[i % len(COLOURS)]
        era_names = [e.era for e in k.era_history] if k.era_history else [k.current_era.name]
        print(f"    {col}{k.name[:14]}{RESET}: {' → '.join(era_names[-5:])}")

    # Decree count comparison
    print(f"\n  {BOLD}Oracle activity:{RESET}")
    for i, k in enumerate(kingdoms):
        col = COLOURS[i % len(COLOURS)]
        tones = {}
        for d in k.decree_history:
            tones[d.tone] = tones.get(d.tone, 0) + 1
        tone_str = ", ".join(f"{t}:{c}" for t, c in sorted(tones.items(), key=lambda x: -x[1])[:3])
        print(f"    {col}{k.name[:14]}{RESET}: {len(k.decree_history)} decrees, {len(k.event_history)} events — top tones: {tone_str}")

    print()


# ────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Headless Oracle Kingdom Simulation")
    parser.add_argument("--seed", type=int, default=42, help="Master RNG seed")
    parser.add_argument("--kingdoms", type=int, default=4, help="Number of kingdoms (2-8)")
    parser.add_argument("--ticks", type=int, default=1000, help="Simulation length in ticks")
    parser.add_argument("--decree-interval", type=int, default=15,
                        help="Ticks between AI decree decisions")
    parser.add_argument("--report-interval", type=int, default=200,
                        help="Ticks between dashboard prints")
    parser.add_argument("--shared-start", action="store_true", default=True,
                        help="All kingdoms start with identical conditions (isolates Oracle effect)")
    parser.add_argument("--unique-starts", action="store_true",
                        help="Each kingdom gets unique starting conditions")
    parser.add_argument("--verbose", action="store_true",
                        help="Print each decree as it happens")
    parser.add_argument("--no-decrees", action="store_true",
                        help="Run with no Oracle speech (baseline drift only)")
    args = parser.parse_args()

    num_kingdoms = max(2, min(8, args.kingdoms))
    shared = not args.unique_starts

    print(f"\n{BOLD}╔══════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}║    ORACLE KINGDOM — Seed World Simulation            ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════════════════════╝{RESET}")
    print(f"  Seed: {args.seed}  |  Kingdoms: {num_kingdoms}  |  Ticks: {args.ticks}")
    print(f"  Decree interval: every {args.decree_interval} ticks")
    print(f"  Shared start: {shared}")
    if args.no_decrees:
        print(f"  ⚠  NO DECREES MODE — Oracles are silent (baseline only)")
    print()

    # Build world
    kingdoms = build_multi_kingdom_world(args.seed, num_kingdoms, shared_start=shared)

    # Print Oracle builds
    print(f"  {BOLD}Oracle Builds:{RESET}")
    for i, k in enumerate(kingdoms):
        col = COLOURS[i % len(COLOURS)]
        traits = {t: int(k.oracle.effective(t)) for t in ok.ORACLE_TRAITS}
        traits_str = " ".join(f"{t[:4]}={v}" for t, v in traits.items())
        print(f"    {col}{k.name[:14]}{RESET}: {traits_str}")
    print()

    # Snapshot initial state
    initial_snaps = [snapshot_kingdom(k) for k in kingdoms]
    decree_logs = {k.kingdom_id: [] for k in kingdoms}

    # Time config
    time_config = ok.TimeConfig()

    # ── SIMULATION LOOP ──────────────────────────────────────
    t0 = time.time()

    for tick in range(1, args.ticks + 1):
        for k in kingdoms:
            # Create per-kingdom RNG
            rng = ok.SeededRNG(k.seed + tick)

            # Advance simulation engine one tick
            events = ok.SimulationEngine.advance_tick(k, rng, time_config)

            # AI Oracle decree decision
            if not args.no_decrees and tick % args.decree_interval == 0:
                decree_rng = rng.fork(f"decree_{k.kingdom_id}")
                result = AIOracle.choose_and_issue_decree(k, decree_rng)
                decree_logs[k.kingdom_id].append(result)

                if args.verbose and result["action"] == "decree":
                    col = COLOURS[kingdoms.index(k) % len(COLOURS)]
                    print(f"  {DIM}t{tick:>5}{RESET} {col}{k.name[:12]}{RESET} [{result['tone']}] \"{result['text']}\"")

            # Note: advance_tick already increments k.tick and k.world_day

        # Periodic dashboard
        if tick % args.report_interval == 0:
            print_dashboard(kingdoms, tick, decree_logs)

    elapsed = time.time() - t0

    # ── FINAL DASHBOARD ──────────────────────────────────────
    print_dashboard(kingdoms, args.ticks, decree_logs)
    print_final_report(kingdoms, initial_snaps)

    print(f"  {DIM}Simulation completed in {elapsed:.1f}s ({args.ticks / max(0.01, elapsed):.0f} ticks/sec){RESET}\n")


if __name__ == "__main__":
    main()
