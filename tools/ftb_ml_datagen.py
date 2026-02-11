"""
FromTheBackmarker ML Training Data Generator

Runs headless simulations to generate training data for team principal AI.
Generates 100+ teams across 10 seasons to capture diverse strategies and outcomes.

Usage:
    python tools/ftb_ml_datagen.py --station_dir stations/FromTheBackmarker --seasons 10 --teams 100
"""

import sys
import os
import argparse
import json
import time
import random
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import FTB simulation engine
from plugins.ftb_game import FTBSimulation, SimState, Team, League, AIPrincipal
from plugins.ftb_state_db import init_db, query_ai_decisions, query_team_outcomes


def generate_training_data(
    station_dir: str,
    num_seasons: int = 10,
    num_teams: int = 100,
    output_dir: str = "data/ml_training"
):
    """
    Run headless simulation to generate ML training data.
    
    Args:
        station_dir: Path to FromTheBackmarker station directory
        num_seasons: Number of seasons to simulate per run
        num_teams: Total number of teams to create across all tiers
        output_dir: Directory to save training data exports
    """
    print(f"[FTB ML DataGen] Starting training data generation")
    print(f"  Station: {station_dir}")
    print(f"  Seasons: {num_seasons}")
    print(f"  Teams: {num_teams}")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Initialize database for this run
    run_id = f"run_{int(time.time())}"
    db_path = os.path.join(output_dir, f"{run_id}.db")
    init_db(db_path)
    print(f"[FTB ML DataGen] Initialized database: {db_path}")
    
    # Create simulation state
    state = SimState()
    state.state_db_path = db_path
    state.tick = 0
    state.season_number = 1
    state.sim_year = 2025
    state.sim_day_of_year = 1
    state.phase = "development"
    state.in_offseason = False
    state.seed = f"ml_training_{run_id}"
    state.time_mode = "auto"
    state.control_mode = "ai_only"
    
    # Initialize RNG
    state._rngs = {}
    
    # Create leagues across all tiers
    print(f"[FTB ML DataGen] Creating {num_teams} teams across 5 tiers...")
    
    # Distribute teams across tiers (more in lower tiers)
    tier_distribution = {
        1: int(num_teams * 0.35),  # 35% in Grassroots
        2: int(num_teams * 0.25),  # 25% in Formula V
        3: int(num_teams * 0.20),  # 20% in Formula X
        4: int(num_teams * 0.12),  # 12% in Formula Y
        5: int(num_teams * 0.08)   # 8% in Formula Z
    }
    
    state.leagues = {}
    state.ai_teams = []
    
    for tier, team_count in tier_distribution.items():
        tier_names = {
            1: "Grassroots Championship",
            2: "Formula V World Series",
            3: "Formula X International",
            4: "Formula Y Grand Prix",
            5: "Formula Z World Championship"
        }
        
        league = League(
            league_id=f"tier_{tier}_ml",
            name=tier_names[tier],
            tier=tier
        )
        league.teams = []
        league.championship_table = {}
        league.races_this_season = 0
        league.schedule = _generate_simple_schedule(tier, state.tick)
        
        # Create teams for this tier
        for i in range(team_count):
            team = _create_ml_training_team(
                tier=tier,
                team_index=i,
                seed=state.seed + str(tier) + str(i)
            )
            team._season_start_budget = team.budget.cash
            league.teams.append(team)
            state.ai_teams.append(team)
        
        state.leagues[league.league_id] = league
        print(f"  Created {team_count} teams in Tier {tier} ({tier_names[tier]})")
    
    print(f"[FTB ML DataGen] Total teams created: {len(state.ai_teams)}")
    
    # Initialize other state components
    state.tracks = _create_basic_tracks()
    state.free_agent_pool = []
    state.parts_catalog = {}
    state.sponsorships = {team.name: [] for team in state.ai_teams}
    state.pending_sponsor_offers = {}
    state.contracts = {}
    state.pending_developments = []
    state.pending_decisions = []
    state.last_salary_payout_tick = 0
    state._teams_to_spawn = []
    
    # Run simulation
    print(f"[FTB ML DataGen] Starting {num_seasons}-season simulation...")
    start_time = time.time()
    
    ticks_per_season = 50  # Approximate
    total_ticks = num_seasons * ticks_per_season
    
    for tick in range(total_ticks):
        # Run one simulation tick
        try:
            events = FTBSimulation.tick_simulation(state)
            
            # Progress indicator every 100 ticks
            if tick % 100 == 0:
                elapsed = time.time() - start_time
                progress = (tick / total_ticks) * 100
                print(f"  Tick {tick}/{total_ticks} ({progress:.1f}%) - "
                      f"Season {state.season_number} - "
                      f"Elapsed: {elapsed:.1f}s - "
                      f"Teams alive: {len(state.ai_teams)}")
        
        except Exception as e:
            print(f"[FTB ML DataGen] Error at tick {tick}: {e}")
            import traceback
            traceback.print_exc()
            break
    
    elapsed_total = time.time() - start_time
    print(f"[FTB ML DataGen] Simulation complete in {elapsed_total:.1f}s")
    
    # Export training data
    print(f"[FTB ML DataGen] Exporting training data...")
    export_training_data(db_path, output_dir, run_id)
    
    print(f"[FTB ML DataGen] Data generation complete!")
    print(f"  Database: {db_path}")
    print(f"  Exports: {output_dir}/{run_id}_*.json")


def _generate_simple_schedule(tier: int, start_tick: int) -> list:
    """Generate a simple race schedule for a tier."""
    races_per_season = {1: 10, 2: 12, 3: 14, 4: 15, 5: 16}
    num_races = races_per_season.get(tier, 12)
    
    schedule = []
    ticks_between_races = 5  # ~1 week
    
    for race_num in range(num_races):
        race_tick = start_tick + race_num * ticks_between_races
        track_id = f"track_{tier}_{race_num}"
        schedule.append((race_tick, track_id))
    
    return schedule


def _create_basic_tracks() -> dict:
    """Create minimal track catalog for all tiers."""
    from plugins.ftb_game import Track
    
    tracks = {}
    
    for tier in range(1, 6):
        for i in range(20):  # 20 tracks per tier
            track_id = f"track_{tier}_{i}"
            
            # Create Track instance with required positional arguments
            track = Track(
                track_id=track_id,
                name=f"Tier {tier} Circuit {i+1}",
                prestige_rating=tier + 2,  # 3-7 range
                length_km=3.5 + (tier * 0.5) + (i * 0.1),
                corner_count=12 + i,
                lap_count=50 - (tier * 3),
                track_type="road",
                characteristics=["balanced"],
                aero_demand="medium",
                mechanical_grip_emphasis="medium",
                power_sensitivity="medium",
                tire_stress="medium",
                min_tier=tier,
                max_tier=tier,
                track_character=f"Standard circuit for Tier {tier}"
            )
            
            tracks[track_id] = track
    
    return tracks


def _create_ml_training_team(tier: int, team_index: int, seed: str) -> Team:
    """Create a team for ML training with randomized attributes."""
    rng = random.Random(seed)
    
    # Generate team name
    team_name = f"T{tier}_Team_{team_index:03d}"
    
    team = Team(name=team_name)
    team.team_id = f"ml_training_{seed}"
    team.tier = tier
    team.ownership_type = "private_owner"
    
    # Randomize starting budget based on tier
    base_budgets = {1: 150000, 2: 250000, 3: 500000, 4: 1000000, 5: 2500000}
    base = base_budgets.get(tier, 150000)
    team.budget.cash = rng.uniform(base * 0.7, base * 1.3)
    
    # Create AI principal with randomized archetype
    principal_name = f"Principal_{team_name}"
    principal = AIPrincipal(name=principal_name)
    principal.entity_id = rng.randint(100000, 999999)
    principal.display_name = principal_name
    principal.age = rng.randint(35, 65)
    
    # Define archetype stat modifiers
    archetypes = {
        "bean_counter": {"financial_discipline": 85, "risk_tolerance": 25, "patience": 70},
        "gambler": {"risk_tolerance": 90, "aggression": 80, "patience": 30},
        "builder": {"long_term_orientation": 85, "patience": 80, "succession_planning": 75},
        "politician": {"political_instinct": 85, "media_management": 80, "supplier_relationship_management": 75},
        "visionary": {"talent_evaluation_accuracy": 80, "crisis_management": 75, "organizational_cohesion": 70},
        "pragmatist": {"budget_forecasting_accuracy": 70, "capital_allocation_balance": 70, "cost_cap_management": 70}
    }
    
    # Apply random archetype modifications
    archetype_key = rng.choice(list(archetypes.keys()))
    for stat, value in archetypes[archetype_key].items():
        if stat in principal.current_ratings:
            principal.current_ratings[stat] = float(value + rng.randint(-5, 5))
    
    team.principal = principal
    team.principal_name = principal_name
    
    # Initialize standing metrics
    team.standing_metrics = {
        'championship_position': 99,
        'morale': 50.0,
        'reputation': 50.0
    }
    
    # Track lifetime
    team.seasons_active = 1
    
    return team


def export_training_data(db_path: str, output_dir: str, run_id: str):
    """Export logged data to JSON files for ML training."""
    
    # Export AI decisions
    print("  Exporting AI decisions...")
    decisions = query_ai_decisions(db_path, limit=100000)
    decisions_path = os.path.join(output_dir, f"{run_id}_decisions.json")
    with open(decisions_path, 'w') as f:
        json.dump(decisions, f, indent=2)
    print(f"    Exported {len(decisions)} decisions to {decisions_path}")
    
    # Export team outcomes
    print("  Exporting team outcomes...")
    outcomes = query_team_outcomes(db_path, limit=10000)
    outcomes_path = os.path.join(output_dir, f"{run_id}_outcomes.json")
    with open(outcomes_path, 'w') as f:
        json.dump(outcomes, f, indent=2)
    print(f"    Exported {len(outcomes)} outcomes to {outcomes_path}")
    
    # Export successful teams only (for imitation learning)
    print("  Filtering successful teams...")
    successful = query_team_outcomes(
        db_path,
        min_budget_health=50.0,  # Positive budget growth
        survived_only=True,
        limit=10000
    )
    successful_path = os.path.join(output_dir, f"{run_id}_successful.json")
    with open(successful_path, 'w') as f:
        json.dump(successful, f, indent=2)
    print(f"    Exported {len(successful)} successful team seasons")
    
    # Generate summary statistics
    print("  Generating summary statistics...")
    summary = {
        'run_id': run_id,
        'total_decisions': len(decisions),
        'total_outcomes': len(outcomes),
        'successful_teams': len(successful),
        'survival_rate': len([o for o in outcomes if o['survival_flag']]) / max(len(outcomes), 1),
        'avg_budget_health': sum(o['budget_health_score'] for o in outcomes) / max(len(outcomes), 1),
        'avg_roi': sum(o['roi_score'] for o in outcomes) / max(len(outcomes), 1),
        'generated_at': time.time()
    }
    
    summary_path = os.path.join(output_dir, f"{run_id}_summary.json")
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"  Summary statistics:")
    print(f"    Survival rate: {summary['survival_rate']*100:.1f}%")
    print(f"    Avg budget health: {summary['avg_budget_health']:.1f}")
    print(f"    Avg ROI: {summary['avg_roi']:.1f}")


def main():
    parser = argparse.ArgumentParser(description='Generate ML training data for FTB team principals')
    parser.add_argument('--station_dir', type=str, default='stations/FromTheBackmarker',
                       help='Path to FromTheBackmarker station directory')
    parser.add_argument('--seasons', type=int, default=10,
                       help='Number of seasons to simulate')
    parser.add_argument('--teams', type=int, default=100,
                       help='Total number of teams to create')
    parser.add_argument('--output_dir', type=str, default='data/ml_training',
                       help='Directory to save training data')
    
    args = parser.parse_args()
    
    generate_training_data(
        station_dir=args.station_dir,
        num_seasons=args.seasons,
        num_teams=args.teams,
        output_dir=args.output_dir
    )


if __name__ == "__main__":
    main()
