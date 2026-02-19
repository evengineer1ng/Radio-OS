#!/usr/bin/env python3
"""
oracle_geosim.py — Three-Layer Geopolitical Simulation

Runs the full world ontology:
  Layer C: 1 player kingdom (full sim, AI oracle)
  Layer B: up to 20 tracked kingdoms (full sim, AI oracle, narrated)
  Layer A: 200+ deep field civs (cheap macro vectors, shocks, promotions)

This exercises:
  - MacroEngine (per-tick minor civ evolution)
  - MacroShock rolls (the storms that make fringe civs matter)
  - ImportanceScorer (dynamic ranking)
  - CivPromoter (promotion/demotion lifecycle)
  - GeopoliticalEngine (three-layer tick driver)
  - Cross-layer coupling (trade index, ideology field)

Run:
    python tools/oracle_geosim.py
    python tools/oracle_geosim.py --seed 42 --ticks 3000 --deep-field 300
    python tools/oracle_geosim.py --seed 42 --ticks 5000 --deep-field 500 --verbose
"""

import argparse
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugins_disabled"))
os.environ["FTB_DEBUG"] = ""

import oracle_kingdom as ok

# ── ANSI ──────────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
RED = "\033[91m"
YEL = "\033[93m"
GRN = "\033[92m"
CYN = "\033[96m"
MAG = "\033[95m"
BLU = "\033[94m"
WHT = "\033[97m"

TIER_COLOURS = {
    1: CYN,   # Tier 1 (top 3)
    2: GRN,   # Tier 2 (4-10)
    3: YEL,   # Tier 3 (11-20)
}

def _tier_colour(rank: int) -> str:
    if rank <= 3:
        return TIER_COLOURS[1]
    elif rank <= 10:
        return TIER_COLOURS[2]
    else:
        return TIER_COLOURS[3]


def _bar(value: float, width: int = 15, lo: float = 0, hi: float = 100) -> str:
    frac = max(0.0, min(1.0, (value - lo) / max(1, hi - lo)))
    filled = int(frac * width)
    empty = width - filled
    if frac < 0.25:
        col = RED
    elif frac < 0.5:
        col = YEL
    elif frac < 0.75:
        col = GRN
    else:
        col = CYN
    return f"{col}{'█' * filled}{'░' * empty}{RESET}"


# ── AI Oracle for Tracked Kingdoms ────────────────────────────

def ai_decree_callback(kingdom: ok.KingdomState, rng: ok.SeededRNG):
    """Issue an AI-driven decree for a tracked kingdom."""
    gen_rng = rng.fork(f"ai_decree_{kingdom.tick}")
    options = ok.SpeechGenerator.generate_decree_options(kingdom, gen_rng, count=4)
    if not options:
        return

    # Simple scoring (same as oracle_sim.py)
    scored = []
    for opt in options:
        score = _score_option(opt, kingdom, gen_rng)
        scored.append((score, opt))
    scored.sort(key=lambda x: x[0], reverse=True)

    roll = gen_rng.random()
    if roll < 0.70 and len(scored) >= 1:
        chosen = scored[0][1]
    elif roll < 0.90 and len(scored) >= 2:
        chosen = scored[1][1]
    else:
        chosen = scored[gen_rng.randint(0, len(scored) - 1)][1]

    ok.PropagationEngine.propagate_decree(kingdom, chosen, gen_rng)
    kingdom.decree_history.append(ok.DecreeRecord(
        decree_id=chosen.option_id,
        tick=kingdom.tick,
        text=chosen.text,
        tone=chosen.tone.name,
        mode=chosen.mode.name,
        policy_vector=dict(chosen.policy_vector),
    ))
    ok.MythMemory.tick_memory(kingdom, gen_rng)


def _score_option(opt, kingdom, rng):
    score = 0.0
    oracle = kingdom.oracle
    p = kingdom.physical
    s = kingdom.social
    pol = kingdom.political
    b = kingdom.belief

    for trait_name in ok.ORACLE_TRAITS:
        val = oracle.effective(trait_name) / 50.0
        if trait_name == "conviction":
            score += val * opt.propagation_magnitude * 0.3
        if trait_name == "empathy" and "mercy_focus" in opt.policy_vector:
            score += val * opt.policy_vector["mercy_focus"] * 0.5
        if trait_name == "clarity" and opt.tone == ok.Tone.PRACTICAL:
            score += val * 0.3
        if trait_name == "self_belief" and opt.tone == ok.Tone.SEVERE:
            score += val * 0.2

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

    score += rng.gauss(0, 0.3)
    return score


# ── Display ───────────────────────────────────────────────────

def print_leaderboard(geo: ok.GeopoliticalState, tick: int):
    """Print the Top 20 importance leaderboard."""
    print(f"\n{'═' * 110}")
    print(f"{BOLD}  GLOBAL IMPORTANCE LEADERBOARD — Tick {tick}  "
          f"(Tracked: {len(geo.tracked_kingdoms)} | Deep Field: {len(geo.deep_field)}){RESET}")
    print(f"{'═' * 110}")

    # Combine tracked + deep field for unified ranking
    # Build display entries
    entries = []

    # Player kingdom (always rank 0 / special)
    pk = geo.player_kingdom
    pk_lc = pk.oracle_lifecycle
    pk_lc_state = pk_lc.state.name[:5]
    pk_lc_info = f"{pk_lc_state} int={pk_lc.intensity:.1f} next={pk_lc.ticks_until_transition}t"
    entries.append({
        "rank": 0,
        "name": pk.name,
        "layer": "C",
        "importance": 99.9,  # player is always important
        "wealth": pk.physical.trade_volume,
        "military": pk.political.enforcement_capacity,
        "stability": pk.social.cohesion,
        "volatility": pk.social.class_tension,
        "era": pk.current_era.name if hasattr(pk.current_era, "name") else "STABLE",
        "extra": f"decrees={len(pk.decree_history)} | {pk_lc_info}",
    })

    # Tracked kingdoms
    for kid, ks in geo.tracked_kingdoms.items():
        # Find matching minor civ for rank
        rank = 999
        importance = 0
        for civ in geo.deep_field:
            if civ.civ_id == kid:
                rank = civ.rank
                importance = civ.importance
                break
        lc = ks.oracle_lifecycle
        lc_state = lc.state.name[:5]
        lc_info = f"{lc_state} int={lc.intensity:.1f} next={lc.ticks_until_transition}t"
        entries.append({
            "rank": rank,
            "name": ks.name,
            "layer": "B",
            "importance": importance,
            "wealth": ks.physical.trade_volume,
            "military": ks.political.enforcement_capacity,
            "stability": ks.social.cohesion,
            "volatility": ks.social.class_tension,
            "era": ks.current_era.name if hasattr(ks.current_era, "name") else "STABLE",
            "extra": f"d={len(ks.decree_history)} e={len(ks.event_history)} | {lc_info}",
        })

    # Top deep field civs (not promoted)
    for civ in sorted(geo.deep_field, key=lambda c: c.importance, reverse=True)[:25]:
        if civ.is_promoted:
            continue
        ora = "☀" if civ.oracle_state.oracle_active else "☽"
        entries.append({
            "rank": civ.rank,
            "name": civ.name,
            "layer": "A",
            "importance": civ.importance,
            "wealth": civ.wealth_index,
            "military": civ.military_strength,
            "stability": civ.stability,
            "volatility": civ.volatility,
            "era": f"{civ.era_flag}/{civ.biome}" if civ.era_flag != "STABLE" else civ.biome,
            "extra": f"{ora} sp={civ.shock_potential:.1f} m={civ.momentum:+.2f}",
        })

    # Sort by importance descending (player always first)
    entries.sort(key=lambda e: (e["layer"] == "C", e["importance"]), reverse=True)

    # Header
    print(f"  {'#':>3} {'Layer':>5} {'Name':<16} {'Import':>7} "
          f"{'Wealth':>7} {'Military':>8} {'Stab':>5} {'Vol':>5} "
          f"{'Era/Biome':<14} {'Details'}")
    print(f"  {'─' * 105}")

    for i, e in enumerate(entries[:25]):
        layer = e["layer"]
        if layer == "C":
            col = MAG  # player = magenta
        elif layer == "B":
            col = _tier_colour(e["rank"])
        else:
            col = DIM

        rank_str = "★" if layer == "C" else str(e["rank"])
        print(f"  {rank_str:>3} {col}[{layer}]{RESET} "
              f"{col}{e['name']:<16}{RESET} "
              f"{e['importance']:>6.1f} "
              f"{_bar(e['wealth'], 8)} {e['wealth']:>5.1f} "
              f"{_bar(e['military'], 8)} {e['military']:>5.1f} "
              f"{e['stability']:>5.1f} {e['volatility']:>5.1f} "
              f"{e['era']:<14} "
              f"{DIM}{e['extra']}{RESET}")

    # Global indices
    print(f"\n  {BOLD}Global:{RESET}  "
          f"Trade={geo.global_trade_index:.1f}  "
          f"Ideology={geo.global_ideology_field:+.1f}  "
          f"Tension={geo.global_conflict_tension:.1f}  "
          f"Pop={geo.global_population:.0f}")

    # Recent promotions/demotions
    recent_promos = [p for p in geo.promotion_log if tick - p["tick"] < 200]
    recent_demos = [d for d in geo.demotion_log if tick - d["tick"] < 200]
    if recent_promos or recent_demos:
        print(f"\n  {BOLD}Recent Movements:{RESET}")
        for p in recent_promos[-3:]:
            print(f"    {GRN}↑ PROMOTED{RESET}: {p['name']} (tick {p['tick']}, importance {p['importance']:.1f})")
        for d in recent_demos[-3:]:
            print(f"    {RED}↓ DEMOTED{RESET}: {d['name']} (tick {d['tick']})")

    print()


def print_deep_field_weather(geo: ok.GeopoliticalState):
    """Print statistical summary of the Deep Field."""
    active = [c for c in geo.deep_field if not c.is_promoted]
    if not active:
        return

    # Aggregate stats
    avg_wealth = sum(c.wealth_index for c in active) / len(active)
    avg_stability = sum(c.stability for c in active) / len(active)
    avg_volatility = sum(c.volatility for c in active) / len(active)
    avg_momentum = sum(c.momentum for c in active) / len(active)
    max_shock = max(c.shock_potential for c in active)
    hottest = max(active, key=lambda c: c.shock_potential)

    # Count by biome
    biome_counts = {}
    for c in active:
        biome_counts[c.biome] = biome_counts.get(c.biome, 0) + 1

    # Oracle lifecycle counts (deep field)
    oracle_awake = sum(1 for c in active if c.oracle_state.oracle_active)
    oracle_sleeping = len(active) - oracle_awake

    # Count recent shocks (last 200 ticks)
    recent_shock_count = sum(
        1 for c in active for s in c.recent_shocks
        if geo.current_tick - s.tick < 200
    )

    print(f"  {BOLD}Deep Field Weather ({len(active)} civs):{RESET}")
    print(f"    Avg Wealth: {avg_wealth:.1f}  "
          f"Avg Stability: {avg_stability:.1f}  "
          f"Avg Volatility: {avg_volatility:.1f}  "
          f"Avg Momentum: {avg_momentum:+.3f}")
    print(f"    Oracles: {CYN}{oracle_awake} awake{RESET} / {DIM}{oracle_sleeping} sleeping{RESET}  "
          f"({oracle_awake * 100 // len(active)}% active)")
    print(f"    Hottest: {hottest.name} (shock_pot={max_shock:.1f}, "
          f"vol={hottest.volatility:.1f}, mom={hottest.momentum:+.2f})")
    print(f"    Recent shocks (last 200t): {recent_shock_count}")
    biome_str = " ".join(f"{b}:{n}" for b, n in sorted(biome_counts.items(), key=lambda x: -x[1])[:5])
    print(f"    Top biomes: {biome_str}")

    # Era distribution
    era_counts = {}
    for c in active:
        era_counts[c.era_flag] = era_counts.get(c.era_flag, 0) + 1
    non_stable = {k: v for k, v in era_counts.items() if k != "STABLE"}
    if non_stable:
        era_str = " ".join(f"{e}:{n}" for e, n in sorted(non_stable.items(), key=lambda x: -x[1]))
        stable_n = era_counts.get("STABLE", 0)
        print(f"    Eras: STABLE:{stable_n} {era_str}")

    # Positive influence radiation
    radiating_eras = {"GOLDEN_AGE", "TRADE_HEGEMONY", "REFORMATION_RISE"}
    beacons = [c for c in active if c.era_flag in radiating_eras]
    if beacons:
        regions_lit = len(set(c.geographic_region for c in beacons))
        avg_prest = sum(c.prestige for c in beacons) / len(beacons)
        print(f"    {GRN}Radiating beacons: {len(beacons)} across {regions_lit} regions"
              f"  (avg prestige ✧{avg_prest:.1f}){RESET}")
    print()


def print_shock_log(geo: ok.GeopoliticalState, since_tick: int):
    """Print recent macro shocks across the Deep Field."""
    shocks = []
    for civ in geo.deep_field:
        for s in civ.recent_shocks:
            if s.tick >= since_tick:
                shocks.append((s.tick, civ.name, s.shock_type, s.magnitude))

    if not shocks:
        return

    shocks.sort(key=lambda x: x[0], reverse=True)
    print(f"  {BOLD}Recent Macro Shocks:{RESET}")
    for tick, name, stype, mag in shocks[:8]:
        severity = "⚡" if mag > 20 else "◉" if mag > 10 else "·"
        print(f"    {DIM}t{tick:>5}{RESET} {severity} {name:<16} {stype:<28} mag={mag:.1f}")
    if len(shocks) > 8:
        print(f"    {DIM}... and {len(shocks) - 8} more{RESET}")
    print()


def print_final_report(geo: ok.GeopoliticalState):
    """End-of-simulation summary."""
    print(f"\n{'━' * 110}")
    print(f"{BOLD}  GEOPOLITICAL SIMULATION — FINAL REPORT{RESET}")
    print(f"{'━' * 110}\n")

    # Promotion/demotion summary
    print(f"  {BOLD}Lifecycle Events:{RESET}")
    print(f"    Total promotions:  {len(geo.promotion_log)}")
    print(f"    Total demotions:   {len(geo.demotion_log)}")

    if geo.promotion_log:
        print(f"\n  {BOLD}All Promotions:{RESET}")
        for p in geo.promotion_log:
            era_tag = f" [{p['era_flag']}]" if p.get("era_flag", "STABLE") != "STABLE" else ""
            displaced_tag = f" ⇢ displaced {p['displaced']}" if p.get("displaced") else ""
            print(f"    t{p['tick']:>5} {GRN}↑{RESET} {p['name']:<16} (importance {p['importance']:.1f}){YEL}{era_tag}{RESET}{DIM}{displaced_tag}{RESET}")

    if geo.demotion_log:
        print(f"\n  {BOLD}All Demotions:{RESET}")
        for d in geo.demotion_log:
            print(f"    t{d['tick']:>5} {RED}↓{RESET} {d['name']:<16}")

    # Currently tracked kingdoms
    print(f"\n  {BOLD}Currently Tracked ({len(geo.tracked_kingdoms)}):{RESET}")
    for kid, ks in geo.tracked_kingdoms.items():
        era = ks.current_era.name if hasattr(ks.current_era, "name") else "STABLE"
        print(f"    {CYN}{ks.name:<16}{RESET} era={era}, "
              f"health={ks.health.composite:.1f}, "
              f"decrees={len(ks.decree_history)}, "
              f"events={len(ks.event_history)}")

    # Deep field distribution
    active = [c for c in geo.deep_field if not c.is_promoted]
    if active:
        # Wealth distribution
        wealth_buckets = {"poor (<25)": 0, "lower (25-40)": 0, "middle (40-60)": 0,
                          "upper (60-75)": 0, "rich (>75)": 0}
        for c in active:
            if c.wealth_index < 25: wealth_buckets["poor (<25)"] += 1
            elif c.wealth_index < 40: wealth_buckets["lower (25-40)"] += 1
            elif c.wealth_index < 60: wealth_buckets["middle (40-60)"] += 1
            elif c.wealth_index < 75: wealth_buckets["upper (60-75)"] += 1
            else: wealth_buckets["rich (>75)"] += 1

        print(f"\n  {BOLD}Deep Field Wealth Distribution ({len(active)} civs):{RESET}")
        for label, count in wealth_buckets.items():
            pct = count / len(active) * 100
            bar_len = int(pct / 2)
            print(f"    {label:<15} {_bar(pct, 20, 0, 50)} {count:>4} ({pct:.0f}%)")

    # Macro shock totals
    all_shocks = []
    for c in geo.deep_field:
        all_shocks.extend(c.recent_shocks)
    if all_shocks:
        shock_types = {}
        for s in all_shocks:
            shock_types[s.shock_type] = shock_types.get(s.shock_type, 0) + 1
        print(f"\n  {BOLD}Total Shocks by Type:{RESET}")
        for stype, count in sorted(shock_types.items(), key=lambda x: -x[1]):
            print(f"    {stype:<30} {count}")

    # Deep field era distribution
    if active:
        era_counts = {}
        for c in active:
            era_counts[c.era_flag] = era_counts.get(c.era_flag, 0) + 1
        non_stable = {k: v for k, v in era_counts.items() if k != "STABLE"}
        if non_stable:
            print(f"\n  {BOLD}Deep Field Era Distribution ({len(active)} civs):{RESET}")
            stable_n = era_counts.get("STABLE", 0)
            print(f"    STABLE             {stable_n:>4} ({stable_n*100//len(active)}%)")
            for era_name, count in sorted(non_stable.items(), key=lambda x: -x[1]):
                pct = count * 100 // len(active)
                if era_name in ("CIVIL_CRISIS", "FAMINE", "DECLINE", "REFORMATION_FALL"):
                    col = RED
                elif era_name in ("MILITANT",):
                    col = YEL
                elif era_name in ("GOLDEN_AGE", "RENAISSANCE", "TRADE_HEGEMONY", "ASCENDANT", "REFORMATION_RISE"):
                    col = GRN
                else:
                    col = WHT
                print(f"    {col}{era_name:<18}{RESET} {count:>4} ({pct}%)")

        # Tail extremes
        very_poor = [c for c in active if c.wealth_index < 15]
        very_rich = [c for c in active if c.wealth_index > 80]
        if very_poor or very_rich:
            print(f"\n  {BOLD}Wealth Tail Extremes:{RESET}")
            if very_poor:
                print(f"    {RED}Very poor (<15):{RESET} {len(very_poor)} civs")
                for c in sorted(very_poor, key=lambda c: c.wealth_index)[:3]:
                    print(f"      {c.name}: wealth={c.wealth_index:.1f}, stab={c.stability:.1f}, era={c.era_flag}")
            if very_rich:
                print(f"    {GRN}Very rich (>80):{RESET} {len(very_rich)} civs")
                for c in sorted(very_rich, key=lambda c: -c.wealth_index)[:3]:
                    print(f"      {c.name}: wealth={c.wealth_index:.1f}, stab={c.stability:.1f}, era={c.era_flag}")

    # Player kingdom summary
    pk = geo.player_kingdom
    print(f"\n  {BOLD}Player Kingdom: {pk.name}{RESET}")
    era = pk.current_era.name if hasattr(pk.current_era, "name") else "STABLE"
    print(f"    Era: {era}")
    print(f"    Health: {pk.health.composite:.1f}")
    print(f"    Decrees: {len(pk.decree_history)}")
    print(f"    Events: {len(pk.event_history)}")

    # ── Bright Spots ──
    if active:
        print(f"\n  {BOLD}✦ Bright Spots:{RESET}")

        # Most Resilient: highest stability with lowest volatility
        resilient = sorted(active, key=lambda c: c.stability - c.volatility * 0.5, reverse=True)[:3]
        print(f"    {GRN}Most Resilient:{RESET}")
        for c in resilient:
            print(f"      {c.name}: stab={c.stability:.1f} vol={c.volatility:.1f} era={c.era_flag}")

        # Fastest Rising: highest sustained momentum
        rising = sorted(active, key=lambda c: c.momentum_sustained * 0.5 + c.momentum, reverse=True)[:3]
        print(f"    {CYN}Fastest Rising:{RESET}")
        for c in rising:
            print(f"      {c.name}: mom={c.momentum:+.2f} sustained={c.momentum_sustained}t era={c.era_flag}")

        # Prosperity Engine: highest wealth growth rate
        prosperous = sorted(active, key=lambda c: c.wealth_growth_rate, reverse=True)[:3]
        print(f"    {YEL}Prosperity Engines:{RESET}")
        for c in prosperous:
            print(f"      {c.name}: w_growth={c.wealth_growth_rate:+.3f} wealth={c.wealth_index:.1f} era={c.era_flag}")

        # Cultural Beacons: highest absolute alignment × influence
        beacons = sorted(active, key=lambda c: abs(c.cultural_alignment) * c.influence_score * 0.01, reverse=True)[:3]
        print(f"    {MAG}Cultural Beacons:{RESET}")
        for c in beacons:
            print(f"      {c.name}: align={c.cultural_alignment:+.1f} inf={c.influence_score:.1f} era={c.era_flag}")

        # Count positive era civs
        positive_eras = {"GOLDEN_AGE", "RENAISSANCE", "TRADE_HEGEMONY", "ASCENDANT", "REFORMATION_RISE"}
        positive_civs = [c for c in active if c.era_flag in positive_eras]
        if positive_civs:
            print(f"\n    {GRN}Civs in positive eras: {len(positive_civs)}{RESET}")
            for c in sorted(positive_civs, key=lambda c: c.importance, reverse=True)[:5]:
                duration = geo.current_tick - c.era_flag_since
                prest = f" ✧{c.prestige:.1f}" if c.prestige > 0.5 else ""
                print(f"      {c.name}: {c.era_flag} for {duration}t (wealth={c.wealth_index:.1f} stab={c.stability:.1f}{prest})")
        else:
            print(f"\n    {DIM}No civs currently in positive eras — the world is harsh.{RESET}")

        # Prestige leaders (may not be in positive era — prestige lingers)
        prestigious = sorted(active, key=lambda c: c.prestige, reverse=True)[:3]
        if prestigious and prestigious[0].prestige > 1.0:
            print(f"\n    {CYN}Prestige Leaders:{RESET}")
            for c in prestigious:
                if c.prestige > 0.5:
                    print(f"      {c.name}: ✧{c.prestige:.1f} era={c.era_flag} imp={c.importance:.1f}")

    # ── Oracle Lifecycle Summary ──
    print(f"\n  {BOLD}Oracle Lifecycle Summary:{RESET}")

    # Player
    pk_lc = pk.oracle_lifecycle
    total_lc = pk_lc.total_active_ticks + pk_lc.total_sleep_ticks
    active_pct = (pk_lc.total_active_ticks / max(1, total_lc)) * 100
    print(f"    Player ({pk.name}):  {pk_lc.state.name}  "
          f"wakes={pk_lc.wake_count}  active={pk_lc.total_active_ticks}t ({active_pct:.0f}%)  "
          f"sleep={pk_lc.total_sleep_ticks}t")

    # Tracked kingdoms
    for kid, ks in geo.tracked_kingdoms.items():
        lc = ks.oracle_lifecycle
        total_lc = lc.total_active_ticks + lc.total_sleep_ticks
        a_pct = (lc.total_active_ticks / max(1, total_lc)) * 100
        print(f"    {ks.name:<16} {lc.state.name:<8} "
              f"wakes={lc.wake_count:<3} active={lc.total_active_ticks}t ({a_pct:.0f}%)  "
              f"sleep={lc.total_sleep_ticks}t")

    # Deep field oracle aggregate
    if active:
        df_awake = sum(1 for c in active if c.oracle_state.oracle_active)
        avg_last_active = sum(c.oracle_state.last_active_tick for c in active) / len(active)
        print(f"    Deep Field:  {df_awake}/{len(active)} currently awake  "
              f"(avg last_active_tick={avg_last_active:.0f})")

    print()


# ── MAIN ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Three-Layer Geopolitical Simulation")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ticks", type=int, default=2000)
    parser.add_argument("--deep-field", type=int, default=200,
                        help="Number of Deep Field minor civs (Layer A)")
    parser.add_argument("--report-interval", type=int, default=250,
                        help="Ticks between dashboard prints")
    parser.add_argument("--verbose", action="store_true",
                        help="Print promotions/shocks as they happen")
    parser.add_argument("--no-decrees", action="store_true")
    args = parser.parse_args()

    master_rng = ok.SeededRNG(args.seed)

    print(f"\n{BOLD}╔══════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}║  ORACLE KINGDOM — Three-Layer Geopolitical Simulation       ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════════════════════════════╝{RESET}")
    print(f"  Seed: {args.seed}  |  Ticks: {args.ticks}  |  Deep Field: {args.deep_field}")
    print()

    # ── Build World ──────────────────────────────────────────
    # Player kingdom
    player_seed = master_rng.fork("player").seed
    player_oracle = ok.OracleBuild.random_build(master_rng.fork("player_oracle"))
    player_ks = ok.WorldBuilder.build_kingdom(
        kingdom_id="player_0",
        seed=player_seed,
        is_player=True,
        oracle=player_oracle,
    )

    print(f"  {BOLD}Player Kingdom:{RESET} {MAG}{player_ks.name}{RESET}")
    traits = {t: int(player_ks.oracle.effective(t)) for t in ok.ORACLE_TRAITS}
    traits_str = " ".join(f"{t[:4]}={v}" for t, v in traits.items())
    print(f"    Oracle: {traits_str}")

    # Deep Field
    player_alignment = (player_ks.belief.public_faith - 50) * 0.5
    deep_field = ok.DeepFieldBuilder.build_deep_field(
        master_seed=args.seed + 1000,
        count=args.deep_field,
        player_alignment=player_alignment,
    )

    print(f"  {BOLD}Deep Field:{RESET} {len(deep_field)} minor civilizations generated")

    # Biome distribution
    biome_counts = {}
    for c in deep_field:
        biome_counts[c.biome] = biome_counts.get(c.biome, 0) + 1
    biome_str = " ".join(f"{b}:{n}" for b, n in sorted(biome_counts.items(), key=lambda x: -x[1])[:5])
    print(f"    Biome distribution: {biome_str}")
    print()

    # ── Assemble GeopoliticalState ────────────────────────────
    geo = ok.GeopoliticalState(
        game_id=f"geosim_{args.seed}",
        master_seed=args.seed,
        player_kingdom=player_ks,
        tracked_kingdoms={},   # empty initially — promotions will fill this
        deep_field=deep_field,
    )

    # ── Simulation Loop ──────────────────────────────────────
    t0 = time.time()
    last_report_tick = 0

    decree_cb = None if args.no_decrees else ai_decree_callback

    # Also issue player decrees via AI
    def player_decree_if_due(tick):
        if args.no_decrees:
            return
        if tick % 15 == 0 and ok.OracleLifecycleEngine.is_decree_allowed(player_ks.oracle_lifecycle):
            prng = ok.SeededRNG(player_ks.seed + tick)
            ai_decree_callback(player_ks, prng)

    promo_count_before = len(geo.promotion_log)
    demo_count_before = len(geo.demotion_log)

    for tick in range(args.ticks):
        rng = ok.SeededRNG(args.seed + tick)

        ok.GeopoliticalEngine.tick(geo, rng, decree_callback=decree_cb)

        # Player decrees (AI-driven for sim)
        player_decree_if_due(tick)

        # Verbose logging for promotions/demotions
        if args.verbose:
            if len(geo.promotion_log) > promo_count_before:
                for p in geo.promotion_log[promo_count_before:]:
                    print(f"  {DIM}t{tick:>5}{RESET} {GRN}↑ PROMOTED{RESET}: {p['name']} (importance {p['importance']:.1f})")
                promo_count_before = len(geo.promotion_log)
            if len(geo.demotion_log) > demo_count_before:
                for d in geo.demotion_log[demo_count_before:]:
                    print(f"  {DIM}t{tick:>5}{RESET} {RED}↓ DEMOTED{RESET}: {d['name']}")
                demo_count_before = len(geo.demotion_log)

        # Periodic reports
        if tick > 0 and tick % args.report_interval == 0:
            print_leaderboard(geo, tick)
            print_deep_field_weather(geo)
            print_shock_log(geo, since_tick=tick - args.report_interval)
            last_report_tick = tick

    elapsed = time.time() - t0

    # ── Final Report ─────────────────────────────────────────
    print_leaderboard(geo, args.ticks)
    print_deep_field_weather(geo)
    print_final_report(geo)

    ticks_per_sec = args.ticks / max(0.01, elapsed)
    civs_per_tick = args.deep_field + len(geo.tracked_kingdoms) + 1
    print(f"  {DIM}Completed in {elapsed:.1f}s  "
          f"({ticks_per_sec:.0f} ticks/sec, "
          f"{civs_per_tick} civs/tick = {ticks_per_sec * civs_per_tick:.0f} civ-ticks/sec){RESET}\n")


if __name__ == "__main__":
    main()
