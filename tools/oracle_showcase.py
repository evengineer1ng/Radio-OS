#!/usr/bin/env python3
"""
oracle_showcase.py — Comprehensive Oracle Kingdom Showcase

Runs the full simulation stack end-to-end and prints a narrative
report demonstrating every system:

  LAYER A  Deep Field (200+ minor civs, macro shocks, promotions)
  LAYER B  Tracked Kingdoms (full sim, AI decrees, oracle lifecycle)
  LAYER C  Player Kingdom (full sim, court layer, inner narrator)

  WORLD    PhysicalLayer · SocialLayer · PoliticalLayer · BeliefLayer
           Factions · Characters · Relationships · Events · Ripples
           EraClassifier · BaselineShifts · InstitutionalScars
           TerminalResolution · OracleLifecycle · OraclePsychology
           MythMemory · NeighbourInfluence · CausalLedger

  COURT    CourtAgents (trust/fear/admiration/resentment/memory)
           PresenceRequests · EnvironmentalSignals · LocationSystem
           CourtDecreeGenerator · InnerNarratorEngine
           OracleIdentityProfile · AgentLifecycle · FactionMemory
           CourtPropagationBridge (location-modified decrees)

  Run:
      python tools/oracle_showcase.py
      python tools/oracle_showcase.py --seed 77 --ticks 2000 --deep-field 300
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

# ── Path setup ────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "plugins_disabled"))
os.environ["FTB_DEBUG"] = ""

import oracle_kingdom as ok
import oracle_court as oc

# ── ANSI ──────────────────────────────────────────────────────
BOLD  = "\033[1m"
DIM   = "\033[2m"
RESET = "\033[0m"
RED   = "\033[91m"
YEL   = "\033[93m"
GRN   = "\033[92m"
CYN   = "\033[96m"
MAG   = "\033[95m"
BLU   = "\033[94m"
WHT   = "\033[97m"

def _bar(val: float, w: int = 12, lo: float = 0, hi: float = 100) -> str:
    frac = max(0.0, min(1.0, (val - lo) / max(1, hi - lo)))
    filled = int(frac * w)
    if frac < 0.25:   col = RED
    elif frac < 0.50:  col = YEL
    elif frac < 0.75:  col = GRN
    else:               col = CYN
    return f"{col}{'█' * filled}{'░' * (w - filled)}{RESET}"

def _sign(v: float) -> str:
    return f"+{v:.1f}" if v >= 0 else f"{v:.1f}"

def _pct(v: float) -> str:
    return f"{v:.0f}%"


# ============================================================
# AI ORACLE — Issues decrees for all kingdoms
# ============================================================

def ai_score_option(opt: ok.SpeechOption, ks: ok.KingdomState,
                    rng: ok.SeededRNG) -> float:
    """Score a decree option based on oracle personality & kingdom needs.
    
    Phase 15: personality-driven divergence ensures different oracle builds
    produce different archetypes and governance styles, not just need-based
    agriculture/mercy (which always converges to POPULIST).
    """
    score = 0.0
    oracle = ks.oracle
    p, s, pol, b = ks.physical, ks.social, ks.political, ks.belief
    vec = opt.policy_vector

    # ── Personality-driven axis affinity ──────────────────────
    # Each personality trait pulls toward specific policy axes.
    # This is the PRIMARY differentiator between oracle builds.
    severity = oracle.effective("severity") / 50.0
    empathy = oracle.effective("empathy") / 50.0
    conviction = oracle.effective("conviction") / 50.0
    ambition = oracle.effective("ambition") / 50.0
    paranoia = oracle.effective("paranoia") / 50.0
    doubt = oracle.effective("doubt") / 50.0
    charisma = oracle.effective("charisma") / 50.0
    humility = oracle.effective("humility") / 50.0

    # Severity → military/justice (HAWK)
    score += severity * (vec.get("military_focus", 0) + vec.get("justice_focus", 0)) * 0.8
    # Empathy → mercy/agriculture (POPULIST)
    score += empathy * (vec.get("mercy_focus", 0) + vec.get("agriculture_focus", 0)) * 0.6
    # Conviction → faith (PIOUS)
    score += conviction * vec.get("faith_focus", 0) * 0.7
    # Ambition → expansion/trade (MERCHANT)
    score += ambition * (vec.get("expansion_focus", 0) + vec.get("trade_focus", 0)) * 0.7
    # Paranoia → military/enforcement
    score += paranoia * vec.get("military_focus", 0) * 0.5
    # Doubt → reform (REFORMIST) — doubt drives introspection and change
    score += doubt * vec.get("reform_focus", 0) * 0.6
    # Charisma → propaganda magnitude bonus
    score += charisma * opt.propagation_magnitude * 0.2
    # Humility → mercy, anti-expansion
    score += humility * vec.get("mercy_focus", 0) * 0.3
    score -= humility * vec.get("expansion_focus", 0) * 0.2

    # Tone affinity
    if opt.tone == ok.Tone.PRACTICAL:
        score += oracle.effective("clarity") / 50.0 * 0.2
    elif opt.tone == ok.Tone.SEVERE:
        score += severity * 0.3
    elif opt.tone == ok.Tone.GENTLE:
        score += empathy * 0.2
    elif opt.tone == ok.Tone.MYSTICAL:
        score += conviction * 0.2

    # ── Need-based scoring (secondary, not primary) ──────────
    # Only activates in crisis, not as default driver
    if p.resource_pressure > 60:
        score += (p.resource_pressure / 100) * vec.get("agriculture_focus", 0) * 1.5
    if p.trade_volume < 20:
        score += (1 - p.trade_volume / 100) * vec.get("trade_focus", 0) * 1.0
    if pol.external_threat > 60:
        score += (pol.external_threat / 100) * vec.get("military_focus", 0) * 1.5
    if b.public_faith < 30:
        score += (1 - b.public_faith / 100) * vec.get("faith_focus", 0) * 1.0
    if pol.corruption > 60:
        score += (pol.corruption / 100) * vec.get("reform_focus", 0) * 1.0

    # Noise — important for diversity across seeds
    score += rng.gauss(0, 0.5)
    return score


def ai_decree_for_tracked(ks: ok.KingdomState, rng: ok.SeededRNG):
    """Issue an AI decree for a tracked (Layer B) kingdom."""
    gen_rng = rng.fork(f"ai_decree_{ks.kingdom_id}_{ks.tick}")
    options = ok.SpeechGenerator.generate_decree_options(ks, gen_rng, count=4)
    if not options:
        return
    scored = sorted(options, key=lambda o: ai_score_option(o, ks, gen_rng), reverse=True)
    roll = gen_rng.random()
    chosen = scored[0] if roll < 0.7 else scored[min(1, len(scored) - 1)]
    ok.PropagationEngine.propagate_decree(ks, chosen, gen_rng)
    ks.decree_history.append(ok.DecreeRecord(
        decree_id=chosen.option_id, tick=ks.tick,
        text=chosen.text, tone=chosen.tone.name,
        mode=chosen.mode.name,
        policy_vector=dict(chosen.policy_vector),
    ))
    ok.MythMemory.tick_memory(ks, gen_rng)


# ============================================================
# COURT-AWARE PLAYER ORACLE
# ============================================================

# Oracle movement: personality-driven room selection
def pick_court_move(court: oc.CourtState, ks: ok.KingdomState,
                    rng: ok.SeededRNG) -> Optional[oc.LocationId]:
    """
    Every ~15 ticks, move the oracle based on active CTAs, personality,
    and kingdom needs.  Not a fixed schedule — reactive.
    """
    tick = ks.tick
    if tick % 15 != 0:
        return None

    gen_rng = rng.fork(f"move_{tick}")

    # Priority 1: respond to highest-urgency CTA
    if court.active_requests:
        best_req = max(court.active_requests, key=lambda r: r.urgency.value)
        if best_req.urgency.value >= 3:  # HIGH or CRITICAL
            try:
                return oc.LocationId[best_req.target_location]
            except KeyError:
                pass

    # Priority 2: personality-driven pull
    oracle = ks.oracle
    candidates = []
    if oracle.effective("paranoia") > 35 and ks.political.external_threat > 25:
        candidates.append(oc.LocationId.RAMPARTS)
    if oracle.effective("empathy") > 40 and ks.social.class_tension > 40:
        candidates.append(oc.LocationId.COURTYARD)
    if oracle.effective("ambition") > 40 and ks.physical.trade_volume > 35:
        candidates.append(oc.LocationId.HARBOR)
    if oracle.effective("conviction") > 40 and ks.belief.public_faith < 50:
        candidates.append(oc.LocationId.TEMPLE)
    if oracle.effective("clarity") > 40:
        candidates.append(oc.LocationId.LIBRARY)

    # Priority 3: visit neglected locations
    if not candidates:
        neglected = sorted(court.location_absence.items(), key=lambda x: -x[1])
        for loc_name, absence in neglected[:3]:
            if absence > 60:
                try:
                    candidates.append(oc.LocationId[loc_name])
                except KeyError:
                    pass

    # Fallback: throne room every other cycle
    if not candidates:
        candidates = [oc.LocationId.THRONE_ROOM, oc.LocationId.OBSERVATORY]

    # Don't move to current location
    candidates = [c for c in candidates if c != court.current_location]
    if not candidates:
        return None

    return gen_rng.choice(candidates)


def court_decree(court: oc.CourtState, ks: ok.KingdomState,
                 rng: ok.SeededRNG) -> Optional[oc.CourtDecreeOption]:
    """
    AI-driven court decree: scores by oracle personality × agent trust × need.
    """
    options = oc.CourtDecreeGenerator.generate(court, ks, rng)
    if not options:
        return None

    gen_rng = rng.fork(f"court_decree_{ks.tick}")

    # Score each option
    scored = []
    for opt in options:
        if opt.is_silence:
            # Silence score based on doubt and consecutive silence
            silence_pull = ks.oracle.effective("doubt") * 0.02
            silence_push = court.inner_state.consecutive_silence_ticks * 0.1
            s = max(0, silence_pull - silence_push)
            scored.append((s, opt))
            continue
        # Base score from world need
        s = ai_score_option(opt.speech_option, ks, gen_rng)
        # Trust multiplier: trusted agents' proposals get a boost
        s += opt.agent_trust * 0.01
        # Location multiplier bonus
        for axis, mult in opt.location_multipliers.items():
            if axis in opt.speech_option.policy_vector:
                s += (mult - 1.0) * 0.3  # slight bonus for location-amplified axes
        scored.append((s, opt))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Weighted selection with noise
    roll = gen_rng.random()
    if roll < 0.60:
        return scored[0][1]
    elif roll < 0.85 and len(scored) > 1:
        return scored[1][1]
    elif len(scored) > 2:
        return scored[2][1]
    return scored[0][1]


# ============================================================
# EVENT LOG — Captures interesting moments for the narrative
# ============================================================

class EventLog:
    """Records notable events during the simulation for the final report."""
    def __init__(self):
        self.entries: List[Tuple[int, str, str]] = []  # (tick, category, text)
        self.decree_texts: List[Tuple[int, str, str]] = []  # (tick, location, text)
        self.thought_ticks: List[int] = []
        self.cta_log: List[Tuple[int, str, str]] = []   # (tick, type, desc)
        self.move_log: List[Tuple[int, str]] = []        # (tick, location)
        self.era_transitions: List[Tuple[int, str, str]] = []  # (tick, from, to)
        self.promotions: List[Tuple[int, str, float]] = []
        self.shocks: List[Tuple[int, str, str]] = []

    def add(self, tick: int, cat: str, text: str):
        self.entries.append((tick, cat, text))


# ============================================================
# MAIN SIMULATION
# ============================================================

def run_single_seed(SEED: int, TICKS: int, DF_COUNT: int,
                    verbose: bool = True) -> dict:
    """
    Run one full simulation and return a results dict.
    If verbose=True, prints the full narrative report.
    If verbose=False, prints a one-line progress then returns quietly.
    """

    # ══════════════════════════════════════════════════════════
    # TITLE
    # ══════════════════════════════════════════════════════════
    if verbose:
        print(f"""
{BOLD}╔════════════════════════════════════════════════════════════════════════╗
║                                                                        ║
║    ◆  O R A C L E   K I N G D O M  ◆                                  ║
║                                                                        ║
║    Comprehensive Simulation Showcase                                   ║
║    Three-Layer World  ·  Court Presence  ·  Inner Narrator             ║
║                                                                        ║
║    Seed: {SEED:<6}  Ticks: {TICKS:<6}  Deep Field: {DF_COUNT:<6}               ║
╚════════════════════════════════════════════════════════════════════════╝{RESET}
""")

    t0_build = time.perf_counter()

    # ── Build the world ──────────────────────────────────────
    master_rng = ok.SeededRNG(SEED)
    player_oracle = ok.OracleBuild.random_build(master_rng.fork("player_oracle"))
    player_ks = ok.WorldBuilder.build_kingdom(
        kingdom_id="player_0", seed=master_rng.fork("player").seed,
        is_player=True, oracle=player_oracle,
    )

    # Deep field
    player_alignment = (player_ks.belief.public_faith - 50) * 0.5
    deep_field = ok.DeepFieldBuilder.build_deep_field(
        master_seed=SEED + 1000, count=DF_COUNT,
        player_alignment=player_alignment,
    )

    geo = ok.GeopoliticalState(
        game_id=f"showcase_{SEED}", master_seed=SEED,
        player_kingdom=player_ks,
        tracked_kingdoms={}, deep_field=deep_field,
    )

    # ── Build court layer ────────────────────────────────────
    court = oc.CourtBuilder.build(player_ks)

    build_time = time.perf_counter() - t0_build

    # ── Print initial state ──────────────────────────────────
    if verbose:
        traits = {t: int(player_ks.oracle.effective(t)) for t in ok.ORACLE_TRAITS}
        print(f"  {BOLD}Player Kingdom:{RESET} {MAG}{player_ks.name}{RESET}")
        print(f"  {BOLD}Oracle Traits:{RESET}  ", end="")
        for t, v in traits.items():
            if v >= 35:
                print(f"{CYN}{t[:5]}={v}{RESET} ", end="")
            elif v <= 15:
                print(f"{RED}{t[:5]}={v}{RESET} ", end="")
            else:
                print(f"{DIM}{t[:5]}={v}{RESET} ", end="")
        print()

        print(f"  {BOLD}Court Agents:{RESET}")
        for aid, agent in court.agents.items():
            char = player_ks.characters.get(agent.character_id)
            faction = player_ks.factions.get(char.faction_id) if char else None
            print(f"    {char.name:<20} {DIM}{faction.archetype.name if faction else '?':<12}{RESET} "
                  f"home={agent.home_location:<14} agenda={agent.personal_agenda}")

        print(f"\n  {BOLD}Deep Field:{RESET} {len(deep_field)} civilizations")
        biome_counts = Counter(c.biome for c in deep_field)
        print(f"  {DIM}Biomes: {' '.join(f'{b}:{n}' for b, n in biome_counts.most_common(6))}{RESET}")

        print(f"\n  {DIM}World built in {build_time:.2f}s{RESET}")
        print()

    # ══════════════════════════════════════════════════════════
    # SIMULATION LOOP
    # ══════════════════════════════════════════════════════════

    log = EventLog()
    t0_sim = time.perf_counter()

    # Tracking
    decree_count = 0
    silence_count = 0
    move_count = 0
    prev_era = player_ks.current_era
    prev_agents = set(court.agents.keys())
    prev_promo_count = 0
    prev_shock_count = sum(len(c.recent_shocks) for c in deep_field)
    snapshot_interval = max(50, TICKS // 20)
    snapshots = []

    if verbose:
        print(f"  {BOLD}▸ Simulating {TICKS} ticks...{RESET}")
        print()

    for tick in range(1, TICKS + 1):
        tick_rng = ok.SeededRNG(SEED + tick)

        # ── 0. Sync archetype from court → kingdom ──
        # The kingdom engine reads oracle_archetype for mechanical
        # modifier effects; the classifier lives in the court layer.
        player_ks.oracle_archetype = court.oracle_identity.archetype.name

        # ── 1. Geopolitical tick (all three layers) ──
        ok.GeopoliticalEngine.tick(geo, tick_rng, decree_callback=ai_decree_for_tracked)

        # ── 2. Player decree (court-aware) ──
        if tick % 10 == 0 and ok.OracleLifecycleEngine.is_decree_allowed(player_ks.oracle_lifecycle):
            option = court_decree(court, player_ks, tick_rng)
            if option:
                events = oc.CourtPropagationBridge.propagate_court_decree(
                    court, player_ks, option, tick_rng
                )
                if option.is_silence:
                    silence_count += 1
                    log.decree_texts.append((tick, court.current_location.name, "[silence]"))
                else:
                    decree_count += 1
                    log.decree_texts.append((tick, court.current_location.name,
                                            option.speech_option.text[:60]))
                ok.MythMemory.tick_memory(player_ks, tick_rng)

        # ── 3. Oracle movement ──
        move_target = pick_court_move(court, player_ks, tick_rng)
        if move_target is not None and move_target != court.current_location:
            oc.CourtEngine.move_oracle(court, player_ks, move_target)
            move_count += 1
            log.move_log.append((tick, move_target.name))

        # ── 4. Court tick ──
        prev_req = len(court.active_requests) + len(court.request_history)
        prev_sig = len(court.active_signals) + len(court.signal_history)
        prev_thought = len(court.inner_state.thought_log)

        oc.CourtEngine.tick(court, player_ks, tick_rng)

        new_reqs = (len(court.active_requests) + len(court.request_history)) - prev_req
        new_sigs = (len(court.active_signals) + len(court.signal_history)) - prev_sig
        if new_reqs > 0:
            for r in court.active_requests[-new_reqs:]:
                log.cta_log.append((tick, "REQUEST", r.description[:60]))
        if new_sigs > 0:
            for s in court.active_signals[-new_sigs:]:
                log.cta_log.append((tick, "SIGNAL", s.description[:60]))

        # Inner thoughts
        if len(court.inner_state.thought_log) > prev_thought:
            log.thought_ticks.append(tick)

        # ── 5. Track notable events ──

        # Era transition
        if player_ks.current_era != prev_era:
            log.era_transitions.append((tick, prev_era.name, player_ks.current_era.name))
            log.add(tick, "ERA", f"{prev_era.name} → {player_ks.current_era.name}")
            prev_era = player_ks.current_era

        # Agent deaths/successions
        current_agents = set(court.agents.keys())
        departed = prev_agents - current_agents
        newcomers = current_agents - prev_agents
        if departed:
            for aid in departed:
                log.add(tick, "DEATH", f"Court agent departed: {aid}")
        if newcomers:
            for aid in newcomers:
                a = court.agents[aid]
                c = player_ks.characters.get(a.character_id)
                name = c.name if c else aid
                log.add(tick, "SUCCESSION", f"New court agent: {name}")
        prev_agents = current_agents

        # Promotions
        if len(geo.promotion_log) > prev_promo_count:
            for p in geo.promotion_log[prev_promo_count:]:
                log.promotions.append((p["tick"], p["name"], p["importance"]))
            prev_promo_count = len(geo.promotion_log)

        # Macro shocks (count new ones)
        current_shock_count = sum(len(c.recent_shocks) for c in deep_field)
        if current_shock_count > prev_shock_count:
            # Find the newest shock across all civs
            for c in deep_field:
                for s in c.recent_shocks:
                    if s.tick == tick:
                        log.shocks.append((tick, c.name, s.shock_type))
            prev_shock_count = current_shock_count

        # ── Periodic snapshot ──
        if tick % snapshot_interval == 0 or tick == 1:
            tension = oc.InnerNarratorEngine.compute_inner_tension(player_ks, court)
            snapshots.append({
                "tick": tick,
                "hp": player_ks.health.composite,
                "era": player_ks.current_era.name,
                "loc": court.current_location.name,
                "arch": court.oracle_identity.archetype.name,
                "tension": tension,
                "thoughts": len(court.inner_state.thought_log),
                "reqs": len(court.active_requests),
                "sigs": len(court.active_signals),
                "agents": {
                    aid: (a.trust, a.resentment, a.narrative_tone)
                    for aid, a in court.agents.items()
                },
                "tracked": len(geo.tracked_kingdoms),
                "global_trade": geo.global_trade_index,
                "global_tension": geo.global_conflict_tension,
            })

        # ── Progress indicator ──
        if verbose and tick % (TICKS // 10) == 0:
            pct = tick * 100 // TICKS
            tension = oc.InnerNarratorEngine.compute_inner_tension(player_ks, court)
            print(f"    {DIM}[{pct:>3}%]{RESET} tick={tick:>5}  "
                  f"hp={player_ks.health.composite:.0f}  "
                  f"era={player_ks.current_era.name:<16} "
                  f"loc={court.current_location.name:<14} "
                  f"arch={court.oracle_identity.archetype.name:<12} "
                  f"tension={tension:.1f}  "
                  f"tracked={len(geo.tracked_kingdoms)}")

    sim_time = time.perf_counter() - t0_sim
    tps = TICKS / max(0.01, sim_time)
    civs_per_tick = DF_COUNT + len(geo.tracked_kingdoms) + 1

    # ── Collect results dict (always) ────────────────────────
    ks = player_ks
    oid = court.oracle_identity
    inner = court.inner_state
    lc = ks.oracle_lifecycle
    total_lc = lc.total_active_ticks + lc.total_sleep_ticks
    active_pct = lc.total_active_ticks / max(1, total_lc) * 100
    total_reqs = len(court.request_history) + len(court.active_requests)
    total_sigs = len(court.signal_history) + len(court.active_signals)
    active_df = [c for c in deep_field if not c.is_promoted]

    # Court serialization check
    court_d = court.to_dict()
    court2 = oc.CourtState.from_dict(court_d)
    court_ok = (len(court2.agents) == len(court.agents)
                and len(court2.faction_memories) == len(court.faction_memories))
    ks_d = ks.to_dict()
    ks2 = ok.KingdomState.from_dict(ks_d)
    ks_ok = (ks2.tick == ks.tick and len(ks2.characters) == len(ks.characters))

    # Agent disposition summary
    tones = Counter(a.narrative_tone for a in court.agents.values())
    avg_trust = sum(a.trust for a in court.agents.values()) / max(1, len(court.agents))
    avg_resentment = sum(a.resentment for a in court.agents.values()) / max(1, len(court.agents))

    # Thought type breakdown
    thought_types = Counter(t.thought_type.name for t in inner.thought_log) if inner.thought_log else {}
    dominant_thought = thought_types.most_common(1)[0][0] if thought_types else "—"

    # Deep field summary
    df_in_crisis = sum(1 for c in active_df if c.era_flag in ("CIVIL_CRISIS", "FAMINE", "DECLINE"))
    df_golden = sum(1 for c in active_df if c.era_flag in ("GOLDEN_AGE", "RENAISSANCE", "TRADE_HEGEMONY", "ASCENDANT"))

    results = {
        "seed": SEED,
        "ticks": TICKS,
        "kingdom_name": ks.name,
        "final_hp": ks.health.composite,
        "final_era": ks.current_era.name,
        "era_transitions": len(log.era_transitions),
        "era_list": [e[2] for e in log.era_transitions],
        "archetype": oid.archetype.name,
        "decrees": decree_count,
        "silences": silence_count,
        "moves": move_count,
        "thoughts": len(inner.thought_log),
        "dominant_thought": dominant_thought,
        "thought_types": dict(thought_types),
        "total_reqs": total_reqs,
        "total_sigs": total_sigs,
        "tones": dict(tones),
        "avg_trust": avg_trust,
        "avg_resentment": avg_resentment,
        "agents": len(court.agents),
        "scars": len(ks.institutional_scars),
        "baseline_shifts": len(ks.baseline_shifts),
        "oracle_state": lc.state.name,
        "oracle_wakes": lc.wake_count,
        "oracle_active_pct": active_pct,
        "oracle_ego": ks.oracle.ego,
        "oracle_stress": ks.oracle.stress,
        "oracle_hope": ks.oracle.hope,
        "oracle_dread": ks.oracle.dread,
        "paranoia": ks.oracle.effective("paranoia"),
        "severity": ks.oracle.effective("severity"),
        "empathy": ks.oracle.effective("empathy"),
        "tracked": len(geo.tracked_kingdoms),
        "promotions": len(geo.promotion_log),
        "demotions": len(geo.demotion_log),
        "global_trade": geo.global_trade_index,
        "global_tension": geo.global_conflict_tension,
        "df_crisis": df_in_crisis,
        "df_golden": df_golden,
        "df_awake": sum(1 for c in active_df if c.oracle_state.oracle_active),
        "court_serial_ok": court_ok,
        "kingdom_serial_ok": ks_ok,
        "build_time": build_time,
        "sim_time": sim_time,
        "tps": tps,
        "civ_tps": tps * civs_per_tick,
        "final_thought": inner.thought_log[-1].text if inner.thought_log else "",
    }

    if not verbose:
        return results

    # ══════════════════════════════════════════════════════════
    # NARRATIVE REPORT
    # ══════════════════════════════════════════════════════════

    print(f"""

{'═' * 76}
{BOLD}  THE CHRONICLES OF {ks.name.upper()}{RESET}
{BOLD}  {TICKS} Ticks  ·  Seed {SEED}  ·  {DF_COUNT} Civilizations{RESET}
{'═' * 76}
""")

    # ── I. THE ORACLE ────────────────────────────────────────
    print(f"{BOLD}  I. THE ORACLE{RESET}")
    print(f"  {'─' * 60}")
    oid = court.oracle_identity
    print(f"  Archetype:        {CYN}{oid.archetype.name}{RESET}")
    sorted_axes = sorted(oid.axis_usage.items(), key=lambda x: -x[1])
    top_axes = [(a, v) for a, v in sorted_axes if v > 5]
    if top_axes:
        print(f"  Dominant Policies: ", end="")
        for ax, val in top_axes[:4]:
            print(f"{ax.replace('_focus','')}={val:.0f} ", end="")
        print()
    print(f"  Decrees Issued:   {decree_count}  ({silence_count} silences)")
    print(f"  Rooms Visited:    {move_count} moves across {len(set(m[1] for m in log.move_log))} locations")
    print(f"  Inner Thoughts:   {len(court.inner_state.thought_log)}")

    # Trait summary
    print(f"\n  {BOLD}Personality:{RESET}")
    for t in ok.ORACLE_TRAITS:
        v = ks.oracle.effective(t)
        bar = _bar(v, 10)
        label = f"  {v:.0f}" if v == int(v) else f"  {v:.1f}"
        marker = " ◆" if v >= 35 else (" ▪" if v <= 15 else "")
        print(f"    {t:<14} {bar}{label}{marker}")

    # Oracle lifecycle
    lc = ks.oracle_lifecycle
    total_lc = lc.total_active_ticks + lc.total_sleep_ticks
    active_pct = lc.total_active_ticks / max(1, total_lc) * 100
    print(f"\n  {BOLD}Oracle Lifecycle:{RESET}  {lc.state.name}  "
          f"(wakes: {lc.wake_count}, active: {_pct(active_pct)} of time)")

    # Oracle psychology snapshot
    print(f"  Ego: {ks.oracle.ego:.1f}  Stress: {ks.oracle.stress:.1f}  "
          f"Hope: {ks.oracle.hope:.1f}  Dread: {ks.oracle.dread:.1f}")

    # ── II. THE KINGDOM ──────────────────────────────────────
    print(f"\n{BOLD}  II. THE KINGDOM{RESET}")
    print(f"  {'─' * 60}")
    print(f"  Era:              {CYN}{ks.current_era.name}{RESET}")
    print(f"  Health:           {_bar(ks.health.composite, 20)} {ks.health.composite:.1f}")
    print(f"  Year/Day:         Year {ks.world_year}, Day {ks.world_day}")
    print()

    layers = [
        ("Food Prod.",    ks.physical.food_production),
        ("Food Stores",   ks.physical.food_stores),
        ("Infrastructure",ks.physical.infrastructure),
        ("Trade Volume",  ks.physical.trade_volume),
        ("Treasury",      ks.physical.treasury),
        ("─────────",     -1),
        ("Cohesion",      ks.social.cohesion),
        ("Class Tension", ks.social.class_tension),
        ("Fear Level",    ks.social.fear_level),
        ("Hope Level",    ks.social.hope_level),
        ("Literacy",      ks.social.literacy),
        ("Cultural Conf.",ks.social.cultural_confidence),
        ("─────────",     -1),
        ("Legitimacy",    ks.political.legitimacy),
        ("Corruption",    ks.political.corruption),
        ("Ext. Threat",   ks.political.external_threat),
        ("Enforcement",   ks.political.enforcement_capacity),
        ("Inst. Strength",ks.political.institutional_strength),
        ("─────────",     -1),
        ("Public Faith",  ks.belief.public_faith),
        ("Interp. Diverg.",ks.belief.interpretation_divergence),
        ("Sacred Silence", ks.belief.sacred_silence_weight),
    ]
    for name, val in layers:
        if val == -1:
            print(f"    {DIM}{'─' * 40}{RESET}")
            continue
        inv = name in ("Class Tension", "Fear Level", "Corruption",
                       "Ext. Threat", "Interp. Diverg.")
        bar_val = 100 - val if inv else val
        print(f"    {name:<18} {_bar(bar_val, 12)} {val:>6.1f}")

    # Eras
    if ks.era_history:
        print(f"\n  {BOLD}Era History:{RESET}")
        for e in ks.era_history[-6:]:
            dur = (e.ended_tick or ks.tick) - e.started_tick
            print(f"    {e.era:<20} ticks {e.started_tick}–{e.ended_tick or '...'} ({dur}t)")

    # Scars
    if ks.institutional_scars:
        print(f"\n  {BOLD}Institutional Scars:{RESET} {len(ks.institutional_scars)}")
        for scar in ks.institutional_scars[-4:]:
            print(f"    {RED}▪{RESET} {scar.source_event_kind} on {scar.variable} "
                  f"(delta={scar.delta:+.1f}, tick {scar.tick_formed})")
            if scar.description:
                print(f"      {DIM}\"{scar.description}\"{RESET}")

    # Baseline shifts
    if ks.baseline_shifts:
        print(f"\n  {BOLD}Baseline Shifts:{RESET} {len(ks.baseline_shifts)}")
        for s in ks.baseline_shifts[-4:]:
            print(f"    {CYN}▸{RESET} {s.target_variable} {_sign(s.delta)} "
                  f"(tick {s.tick_applied}, sustained {s.years_sustained}y)")
            if s.description:
                print(f"      {DIM}\"{s.description}\"{RESET}")

    # Events
    pending = ks.active_events.pending()
    if pending:
        print(f"\n  {BOLD}Active Events:{RESET} {len(pending)}")
        for e in sorted(pending, key=lambda x: -x.severity)[:5]:
            print(f"    [{e.kind.name}] sev={e.severity:.0f}: {e.description[:60]}")

    # ── III. THE COURT ───────────────────────────────────────
    print(f"\n{BOLD}  III. THE COURT{RESET}")
    print(f"  {'─' * 60}")
    print(f"  Oracle is in:     {CYN}{court.current_location.name}{RESET}")
    loc_profile = oc.LOCATION_PROFILES[court.current_location]
    print(f"                    {DIM}\"{loc_profile.description}\"{RESET}")
    print(f"  Ticks here:       {court.ticks_at_location}")
    print()

    # Agent detail
    print(f"  {BOLD}Court Agents:{RESET}")
    for aid, agent in court.agents.items():
        char = ks.characters.get(agent.character_id)
        faction = ks.factions.get(char.faction_id) if char else None
        name = char.name if char else "?"
        arch = faction.archetype.name if faction else "?"

        # Tone color
        tone_col = {
            "devoted": GRN, "favorable": CYN, "neutral": WHT,
            "ambivalent": YEL, "distrustful": RED, "hostile": RED,
        }.get(agent.narrative_tone, WHT)

        print(f"\n    {BOLD}{name}{RESET} ({arch}, {agent.home_location})")
        print(f"      Trust:       {_bar(agent.trust, 10)} {agent.trust:.1f}")
        print(f"      Fear:        {_bar(agent.fear, 10)} {agent.fear:.1f}")
        print(f"      Admiration:  {_bar(agent.admiration, 10)} {agent.admiration:.1f}")
        print(f"      Resentment:  {_bar(100 - agent.resentment, 10)} {agent.resentment:.1f}")
        print(f"      Consistency: {agent.perceived_consistency:.0f}  "
              f"Decisiveness: {agent.perceived_decisiveness:.0f}")
        print(f"      Tone: {tone_col}{agent.narrative_tone}{RESET}"
              f"  Memories: {len(agent.memories)}"
              + (f"  Label: \"{agent.oracle_label}\"" if agent.oracle_label else ""))

        # Top 2 memories
        if agent.memories:
            top = sorted(agent.memories, key=lambda m: abs(m.current_weight), reverse=True)[:2]
            for m in top:
                w_col = GRN if m.current_weight > 0 else RED
                print(f"        {w_col}[{m.memory_type.name}]{RESET} "
                      f"w={m.current_weight:+.2f}: {m.description[:45]}")

    # Faction memory
    print(f"\n  {BOLD}Faction Memory:{RESET}")
    for fid, fm in court.faction_memories.items():
        faction = ks.factions.get(fid)
        fname = faction.name if faction else fid
        trust_col = GRN if fm.collective_trust > 55 else (RED if fm.collective_trust < 45 else YEL)
        print(f"    {fname:<25} trust={trust_col}{fm.collective_trust:.0f}{RESET}  "
              f"resentment={fm.collective_resentment:.0f}  "
              f"memories={len(fm.memories)}")

    # CTA summary
    total_reqs = len(court.request_history) + len(court.active_requests)
    total_sigs = len(court.signal_history) + len(court.active_signals)
    print(f"\n  {BOLD}Calls to Action:{RESET}")
    print(f"    Presence Requests: {total_reqs} total, {len(court.active_requests)} active")
    print(f"    Env. Signals:      {total_sigs} total, {len(court.active_signals)} active")
    if log.cta_log:
        print(f"    Recent:")
        for tick, ctype, desc in log.cta_log[-4:]:
            icon = "📍" if ctype == "REQUEST" else "🌤"
            print(f"      {icon} t{tick}: {desc}")

    # ── IV. THE INNER VOICE ──────────────────────────────────
    print(f"\n{BOLD}  IV. THE INNER VOICE{RESET}")
    print(f"  {'─' * 60}")
    inner = court.inner_state
    print(f"  Total Silence:    {inner.total_silence_ticks} ticks")
    print(f"  Existential Pr.:  {inner.existential_pressure:.2f}")
    print(f"  Legacy Anxiety:   {inner.legacy_anxiety:.2f}")
    print(f"  Suppressed:       {inner.suppressed_thoughts:.2f}")
    print(f"  Locations Seen:   {len(inner.location_history)}")

    if inner.thought_log:
        print(f"\n  {BOLD}Inner Thoughts ({len(inner.thought_log)} total):{RESET}")
        # Type distribution
        type_counts = Counter(t.thought_type.name for t in inner.thought_log)
        for ttype, count in type_counts.most_common():
            print(f"    {ttype:<20} {count:>3}×")

        # Last several thoughts
        print(f"\n  {BOLD}Recent Thoughts:{RESET}")
        for t in inner.thought_log[-6:]:
            tcol = {
                "CALCULATIVE": CYN, "DOUBT_SPIRAL": YEL,
                "DESTINY_SURGE": GRN, "MORAL_RECKONING": MAG,
                "COLD_DETACHMENT": RED, "SILENCE_PRESSURE": YEL,
                "PARANOID_WHISPER": RED, "NOSTALGIC_RECALL": BLU,
            }.get(t.thought_type.name, WHT)
            print(f"    {DIM}t{t.tick:>5}{RESET} {tcol}[{t.thought_type.name}]{RESET}")
            print(f"           \"{t.text}\"")
            print(f"           {DIM}trait={t.dominant_trait} tension={t.tension_level:.1f}{RESET}")
    else:
        print(f"\n  {DIM}The oracle's mind is quiet. No inner thoughts generated.{RESET}")

    # ── V. THE WORLD ─────────────────────────────────────────
    print(f"\n{BOLD}  V. THE WORLD BEYOND{RESET}")
    print(f"  {'─' * 60}")
    print(f"  Global Trade:     {geo.global_trade_index:.1f}")
    print(f"  Global Ideology:  {geo.global_ideology_field:+.1f}")
    print(f"  Global Tension:   {geo.global_conflict_tension:.1f}")
    print(f"  Global Pop.:      {geo.global_population:.0f}")
    print(f"  Tracked Kingdoms: {len(geo.tracked_kingdoms)}")
    print(f"  Deep Field Civs:  {len(geo.deep_field)}")

    # Tracked kingdom summaries
    if geo.tracked_kingdoms:
        print(f"\n  {BOLD}Tracked Kingdoms (Layer B):{RESET}")
        for kid, tks in sorted(geo.tracked_kingdoms.items(),
                               key=lambda x: -x[1].health.composite)[:8]:
            lc = tks.oracle_lifecycle
            era = tks.current_era.name if hasattr(tks.current_era, "name") else "STABLE"
            print(f"    {tks.name:<20} hp={tks.health.composite:.0f}  era={era:<16} "
                  f"oracle={lc.state.name:<8} decrees={len(tks.decree_history)}")

    # Deep field weather
    active_df = [c for c in deep_field if not c.is_promoted]
    if active_df:
        avg_wealth = sum(c.wealth_index for c in active_df) / len(active_df)
        avg_stab = sum(c.stability for c in active_df) / len(active_df)
        max_shock = max(c.shock_potential for c in active_df)
        hottest = max(active_df, key=lambda c: c.shock_potential)

        era_counts = Counter(c.era_flag for c in active_df)
        positive_eras = {"GOLDEN_AGE", "RENAISSANCE", "TRADE_HEGEMONY", "ASCENDANT"}
        negative_eras = {"CIVIL_CRISIS", "FAMINE", "DECLINE"}
        n_positive = sum(era_counts.get(e, 0) for e in positive_eras)
        n_negative = sum(era_counts.get(e, 0) for e in negative_eras)
        n_stable = era_counts.get("STABLE", 0)

        print(f"\n  {BOLD}Deep Field Summary ({len(active_df)} civs):{RESET}")
        print(f"    Avg Wealth:   {avg_wealth:.1f}   Avg Stability: {avg_stab:.1f}")
        print(f"    Max Shock Potential: {max_shock:.1f} ({hottest.name})")
        print(f"    Eras: {GRN}▲{n_positive} positive{RESET}  "
              f"{WHT}●{n_stable} stable{RESET}  "
              f"{RED}▼{n_negative} in crisis{RESET}")

        # Oracle lifecycle in deep field
        df_awake = sum(1 for c in active_df if c.oracle_state.oracle_active)
        print(f"    Oracles: {df_awake}/{len(active_df)} currently awake")

    # Promotions
    if geo.promotion_log:
        print(f"\n  {BOLD}Promotions:{RESET} {len(geo.promotion_log)} total")
        for p in geo.promotion_log[-5:]:
            print(f"    {GRN}↑{RESET} t{p['tick']:>5}: {p['name']} "
                  f"(importance {p['importance']:.1f})")

    # Demotions
    if geo.demotion_log:
        print(f"  {BOLD}Demotions:{RESET} {len(geo.demotion_log)} total")
        for d in geo.demotion_log[-3:]:
            print(f"    {RED}↓{RESET} t{d['tick']:>5}: {d['name']}")

    # ── VI. DECREE SAMPLES ───────────────────────────────────
    print(f"\n{BOLD}  VI. DECREE SAMPLES{RESET}")
    print(f"  {'─' * 60}")
    # Show a spread of decrees across the timeline
    if log.decree_texts:
        step = max(1, len(log.decree_texts) // 10)
        samples = log.decree_texts[::step][:10]
        for tick, loc, text in samples:
            icon = "🤫" if text == "[silence]" else "📜"
            print(f"    {icon} t{tick:>5} [{loc}]")
            print(f"       {DIM}\"{text}\"{RESET}")

    # ── VII. TIMELINE ────────────────────────────────────────
    print(f"\n{BOLD}  VII. TIMELINE{RESET}")
    print(f"  {'─' * 60}")
    print(f"  {'tick':>5}  {'hp':>4}  {'era':<16} {'loc':<14} {'arch':<12} "
          f"{'tns':>4}  {'tht':>3}  {'trk':>3}  {'agents'}")
    print(f"  {'─' * 100}")
    for snap in snapshots:
        # Agent summary: just names and tones
        agent_str = ""
        for aid, (trust, res, tone) in snap["agents"].items():
            t_col = GRN if trust > 50 else (RED if trust < 20 else YEL)
            agent_str += f" {t_col}{tone[:4]}{RESET}"

        print(f"  {snap['tick']:>5}  {snap['hp']:>4.0f}  {snap['era']:<16} "
              f"{snap['loc']:<14} {snap['arch']:<12} "
              f"{snap['tension']:>4.1f}  {snap['thoughts']:>3}  "
              f"{snap['tracked']:>3}  {agent_str}")

    # ── VIII. ERA TRANSITIONS ────────────────────────────────
    if log.era_transitions:
        print(f"\n{BOLD}  VIII. ERA TRANSITIONS{RESET}")
        print(f"  {'─' * 60}")
        for tick, era_from, era_to in log.era_transitions:
            icon = "🌅" if era_to in ("GOLDEN_AGE", "RENAISSANCE", "ASCENDANT") else "🌑"
            print(f"    {icon} tick {tick:>5}: {era_from} → {CYN}{era_to}{RESET}")

    # ── IX. SERIALIZATION ────────────────────────────────────
    print(f"\n{BOLD}  IX. SYSTEM VALIDATION{RESET}")
    print(f"  {'─' * 60}")

    # Court serialization
    court_d = court.to_dict()
    court2 = oc.CourtState.from_dict(court_d)
    court_ok = (len(court2.agents) == len(court.agents)
                and len(court2.faction_memories) == len(court.faction_memories))
    print(f"  Court round-trip:    {'✅' if court_ok else '❌'} "
          f"({len(court2.agents)} agents, {len(court2.faction_memories)} factions)")

    # Kingdom serialization
    ks_d = ks.to_dict()
    ks2 = ok.KingdomState.from_dict(ks_d)
    ks_ok = (ks2.tick == ks.tick and len(ks2.characters) == len(ks.characters))
    print(f"  Kingdom round-trip:  {'✅' if ks_ok else '❌'} "
          f"(tick={ks2.tick}, {len(ks2.characters)} characters, "
          f"{len(ks2.decree_history)} decrees)")

    print(f"\n  {BOLD}Performance:{RESET}")
    print(f"    Build time:  {build_time:.2f}s")
    print(f"    Sim time:    {sim_time:.2f}s")
    print(f"    Throughput:  {tps:.0f} ticks/sec "
          f"({civs_per_tick} civs/tick = "
          f"{tps * civs_per_tick:.0f} civ-ticks/sec)")

    # ── CODA ─────────────────────────────────────────────────
    # Pick the most dramatic inner thought for a closing line
    if inner.thought_log:
        final = inner.thought_log[-1]
        print(f"\n  {DIM}{'─' * 60}{RESET}")
        print(f"  {DIM}The oracle thinks:{RESET}")
        print(f"  {BOLD}\"{final.text}\"{RESET}")
    else:
        print(f"\n  {DIM}The oracle's mind is quiet. For now.{RESET}")

    print(f"\n{'═' * 76}\n")

    return results


# ============================================================
# MULTI-SEED COMPARATIVE RUN
# ============================================================

def run_multi(seeds: List[int], ticks: int, df_count: int):
    """Run N seeds and print a comparative dashboard."""

    n = len(seeds)
    print(f"""
{BOLD}╔════════════════════════════════════════════════════════════════════════╗
║                                                                        ║
║    ◆  O R A C L E   K I N G D O M  —  MULTI-SEED STRESS TEST  ◆      ║
║                                                                        ║
║    {n} Seeds  ·  {ticks} Ticks Each  ·  {df_count} Deep Field Civs              ║
╚════════════════════════════════════════════════════════════════════════╝{RESET}
""")

    all_results = []
    t0 = time.perf_counter()

    for i, seed in enumerate(seeds):
        label = f"[{i+1:>2}/{n}]"
        print(f"  {DIM}{label}{RESET} seed={seed:<6}", end="", flush=True)
        t1 = time.perf_counter()
        r = run_single_seed(seed, ticks, df_count, verbose=False)
        elapsed = time.perf_counter() - t1

        # One-line summary
        arch_col = {
            "THE_HAWK": RED, "THE_PIOUS": MAG, "THE_MERCHANT": YEL,
            "THE_SCHOLAR": CYN, "THE_REFORMER": GRN, "THE_ERRATIC": RED,
            "THE_TYRANT": RED, "UNKNOWN": DIM,
        }.get(r["archetype"], WHT)
        hp_col = GRN if r["final_hp"] >= 55 else (YEL if r["final_hp"] >= 40 else RED)

        tone_str = ""
        for tone in ("devoted", "favorable", "ambivalent", "distrustful", "hostile"):
            cnt = r["tones"].get(tone, 0)
            if cnt:
                tc = {"devoted": GRN, "favorable": CYN, "ambivalent": YEL,
                      "distrustful": RED, "hostile": RED}.get(tone, WHT)
                tone_str += f"{tc}{tone[:4]}:{cnt}{RESET} "

        serial_icon = "✅" if (r["court_serial_ok"] and r["kingdom_serial_ok"]) else "❌"

        print(f"  {r['kingdom_name']:<16} "
              f"hp={hp_col}{r['final_hp']:>4.0f}{RESET}  "
              f"era={r['final_era']:<16} "
              f"arch={arch_col}{r['archetype']:<14}{RESET} "
              f"dec={r['decrees']:>3}+{r['silences']}"
              f"  th={r['thoughts']:>3}  "
              f"trk={r['tracked']:>2}  "
              f"{serial_icon}  "
              f"{elapsed:.1f}s")

        all_results.append(r)

    total_time = time.perf_counter() - t0

    # ══════════════════════════════════════════════════════════
    # COMPARATIVE DASHBOARD
    # ══════════════════════════════════════════════════════════
    print(f"""
{'═' * 90}
{BOLD}  COMPARATIVE DASHBOARD  —  {n} Seeds × {ticks} Ticks{RESET}
{'═' * 90}
""")

    # ── Health distribution ──
    hps = [r["final_hp"] for r in all_results]
    hp_min, hp_max, hp_avg = min(hps), max(hps), sum(hps) / n
    hp_std = (sum((h - hp_avg) ** 2 for h in hps) / n) ** 0.5
    print(f"  {BOLD}Kingdom Health:{RESET}")
    print(f"    Min: {RED}{hp_min:.0f}{RESET}  Max: {GRN}{hp_max:.0f}{RESET}  "
          f"Avg: {hp_avg:.1f}  StdDev: {hp_std:.1f}")

    # Health histogram
    buckets = {"0-20": 0, "20-35": 0, "35-50": 0, "50-65": 0, "65-80": 0, "80+": 0}
    for h in hps:
        if h < 20:   buckets["0-20"] += 1
        elif h < 35: buckets["20-35"] += 1
        elif h < 50: buckets["35-50"] += 1
        elif h < 65: buckets["50-65"] += 1
        elif h < 80: buckets["65-80"] += 1
        else:        buckets["80+"] += 1
    print(f"    Distribution: ", end="")
    for label, cnt in buckets.items():
        if cnt:
            bar = "█" * cnt
            print(f" {label}:{bar}({cnt})", end="")
    print()

    # ── Era distribution ──
    era_counts = Counter(r["final_era"] for r in all_results)
    print(f"\n  {BOLD}Final Eras:{RESET}")
    for era, cnt in era_counts.most_common():
        pct = cnt * 100 / n
        bar = "█" * cnt
        col = GRN if era in ("GOLDEN_AGE", "RENAISSANCE") else (RED if era in ("DECLINE", "CIVIL_CRISIS", "FAMINE") else WHT)
        print(f"    {era:<20} {col}{bar}{RESET} {cnt} ({pct:.0f}%)")

    # ── Archetype distribution ──
    arch_counts = Counter(r["archetype"] for r in all_results)
    print(f"\n  {BOLD}Oracle Archetypes:{RESET}")
    for arch, cnt in arch_counts.most_common():
        pct = cnt * 100 / n
        bar = "█" * cnt
        col = {
            "THE_HAWK": RED, "THE_PIOUS": MAG, "THE_MERCHANT": YEL,
            "THE_SCHOLAR": CYN, "THE_REFORMER": GRN, "THE_ERRATIC": RED,
            "THE_TYRANT": RED, "UNKNOWN": DIM,
        }.get(arch, WHT)
        print(f"    {arch:<20} {col}{bar}{RESET} {cnt} ({pct:.0f}%)")

    # ── Court disposition ──
    all_tones = Counter()
    for r in all_results:
        for tone, cnt in r["tones"].items():
            all_tones[tone] += cnt
    total_agents_across = sum(all_tones.values())
    print(f"\n  {BOLD}Agent Dispositions (across all {n} runs, {total_agents_across} total):{RESET}")
    for tone, cnt in all_tones.most_common():
        pct = cnt * 100 / max(1, total_agents_across)
        bar_len = max(1, int(pct / 3))
        col = {"devoted": GRN, "favorable": CYN, "ambivalent": YEL,
               "distrustful": RED, "hostile": RED, "neutral": WHT}.get(tone, WHT)
        print(f"    {tone:<14} {col}{'█' * bar_len}{RESET} {cnt} ({pct:.0f}%)")

    # ── Inner narrator ──
    thoughts = [r["thoughts"] for r in all_results]
    th_avg = sum(thoughts) / n
    th_min, th_max = min(thoughts), max(thoughts)
    all_thought_types = Counter()
    for r in all_results:
        for tt, cnt in r["thought_types"].items():
            all_thought_types[tt] += cnt
    print(f"\n  {BOLD}Inner Narrator:{RESET}")
    print(f"    Thoughts per run:  min={th_min}  max={th_max}  avg={th_avg:.1f}")
    print(f"    Thought types:")
    for tt, cnt in all_thought_types.most_common():
        print(f"      {tt:<22} {cnt:>4}×")

    # ── Decrees ──
    decs = [r["decrees"] for r in all_results]
    sils = [r["silences"] for r in all_results]
    print(f"\n  {BOLD}Decrees:{RESET}")
    print(f"    Per run:  min={min(decs)}  max={max(decs)}  avg={sum(decs)/n:.1f}")
    print(f"    Silences: min={min(sils)}  max={max(sils)}  avg={sum(sils)/n:.1f}")

    # ── Scars & shifts ──
    scars = [r["scars"] for r in all_results]
    shifts = [r["baseline_shifts"] for r in all_results]
    print(f"\n  {BOLD}Scars & Baseline Shifts:{RESET}")
    print(f"    Scars per run:   min={min(scars)}  max={max(scars)}  avg={sum(scars)/n:.1f}")
    print(f"    Shifts per run:  min={min(shifts)}  max={max(shifts)}  avg={sum(shifts)/n:.1f}")

    # ── Geopolitical ──
    promos = [r["promotions"] for r in all_results]
    demos = [r["demotions"] for r in all_results]
    tracked = [r["tracked"] for r in all_results]
    print(f"\n  {BOLD}Geopolitics:{RESET}")
    print(f"    Tracked kingdoms:  min={min(tracked)}  max={max(tracked)}  avg={sum(tracked)/n:.1f}")
    print(f"    Promotions:        min={min(promos)}  max={max(promos)}  avg={sum(promos)/n:.1f}")
    print(f"    Demotions:         min={min(demos)}  max={max(demos)}  avg={sum(demos)/n:.1f}")

    # ── Oracle psychology ──
    egos = [r["oracle_ego"] for r in all_results]
    stresses = [r["oracle_stress"] for r in all_results]
    hopes = [r["oracle_hope"] for r in all_results]
    dreads = [r["oracle_dread"] for r in all_results]
    print(f"\n  {BOLD}Oracle Psychology (end state):{RESET}")
    print(f"    Ego:     min={min(egos):.1f}  max={max(egos):.1f}  avg={sum(egos)/n:.1f}")
    print(f"    Stress:  min={min(stresses):.1f}  max={max(stresses):.1f}  avg={sum(stresses)/n:.1f}")
    print(f"    Hope:    min={min(hopes):.1f}  max={max(hopes):.1f}  avg={sum(hopes)/n:.1f}")
    print(f"    Dread:   min={min(dreads):.1f}  max={max(dreads):.1f}  avg={sum(dreads)/n:.1f}")

    # ── Serialization ──
    all_court_ok = all(r["court_serial_ok"] for r in all_results)
    all_ks_ok = all(r["kingdom_serial_ok"] for r in all_results)
    print(f"\n  {BOLD}Serialization:{RESET}")
    print(f"    Court round-trip:   {'✅ ALL PASS' if all_court_ok else '❌ FAILURES'}")
    print(f"    Kingdom round-trip: {'✅ ALL PASS' if all_ks_ok else '❌ FAILURES'}")
    if not all_court_ok or not all_ks_ok:
        for r in all_results:
            if not r["court_serial_ok"] or not r["kingdom_serial_ok"]:
                print(f"      ❌ seed={r['seed']}: court={'✅' if r['court_serial_ok'] else '❌'} "
                      f"kingdom={'✅' if r['kingdom_serial_ok'] else '❌'}")

    # ── Performance ──
    total_ticks = sum(r["ticks"] for r in all_results)
    total_civ_ticks = sum(r["civ_tps"] * r["sim_time"] for r in all_results)
    avg_tps = sum(r["tps"] for r in all_results) / n
    print(f"\n  {BOLD}Performance:{RESET}")
    print(f"    Total wall time:   {total_time:.1f}s")
    print(f"    Total sim ticks:   {total_ticks:,}")
    print(f"    Avg throughput:    {avg_tps:.0f} ticks/sec")
    print(f"    Total civ-ticks:   {total_civ_ticks:,.0f}")

    # ── Notable outliers ──
    print(f"\n  {BOLD}Notable Outliers:{RESET}")
    best_hp = max(all_results, key=lambda r: r["final_hp"])
    worst_hp = min(all_results, key=lambda r: r["final_hp"])
    most_thoughts = max(all_results, key=lambda r: r["thoughts"])
    most_scars = max(all_results, key=lambda r: r["scars"])

    print(f"    Healthiest:      seed={best_hp['seed']}  {best_hp['kingdom_name']}  "
          f"hp={GRN}{best_hp['final_hp']:.0f}{RESET}  arch={best_hp['archetype']}")
    print(f"    Most suffering:  seed={worst_hp['seed']}  {worst_hp['kingdom_name']}  "
          f"hp={RED}{worst_hp['final_hp']:.0f}{RESET}  arch={worst_hp['archetype']}")
    print(f"    Most introspective: seed={most_thoughts['seed']}  "
          f"{most_thoughts['thoughts']} thoughts  "
          f"dominant={most_thoughts['dominant_thought']}")
    print(f"    Most scarred:    seed={most_scars['seed']}  "
          f"{most_scars['scars']} scars  {most_scars['baseline_shifts']} shifts")

    # ── Closing quotes from each oracle ──
    print(f"\n  {BOLD}Final Thoughts from Each Oracle:{RESET}")
    for r in all_results:
        if r["final_thought"]:
            arch_col = {
                "THE_HAWK": RED, "THE_PIOUS": MAG, "THE_MERCHANT": YEL,
                "THE_SCHOLAR": CYN, "THE_REFORMER": GRN, "THE_ERRATIC": RED,
            }.get(r["archetype"], WHT)
            print(f"    {DIM}s{r['seed']:<5}{RESET} {arch_col}{r['archetype']:<14}{RESET} "
                  f"\"{r['final_thought']}\"")

    print(f"\n{'═' * 90}\n")


# ============================================================
# MAIN ENTRYPOINT
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Oracle Kingdom — Comprehensive Showcase")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ticks", type=int, default=1500)
    parser.add_argument("--deep-field", type=int, default=200,
                        help="Number of deep-field civs")
    parser.add_argument("--multi", type=int, default=0,
                        help="Run N seeds (e.g. --multi 20). Overrides --seed.")
    parser.add_argument("--seed-start", type=int, default=1,
                        help="Starting seed for multi mode (default: 1)")
    args = parser.parse_args()

    if args.multi > 0:
        seeds = list(range(args.seed_start, args.seed_start + args.multi))
        run_multi(seeds, args.ticks, args.deep_field)
    else:
        run_single_seed(args.seed, args.ticks, args.deep_field, verbose=True)


if __name__ == "__main__":
    main()
