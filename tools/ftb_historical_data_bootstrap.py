"""
FTB Historical Data Bootstrap Script

Initializes historical data tables for existing FTB saves by reprocessing
season summaries and race results archives.

Usage:
    python tools/ftb_historical_data_bootstrap.py [db_path]
"""

import sys
import os
import sqlite3
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from plugins import ftb_state_db
except ImportError:
    print("Error: Could not import ftb_state_db")
    sys.exit(1)


def bootstrap_historical_data(db_path: str, verbose: bool = True) -> None:
    """Bootstrap historical data from existing season summaries and race results.
    
    Args:
        db_path: Path to FTB state database
        verbose: Print progress information
    """
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return
    
    if verbose:
        print(f"Bootstrapping historical data for: {db_path}")
        print("=" * 70)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get current game state
    cursor.execute("SELECT tick FROM game_state_snapshot WHERE id = 1")
    row = cursor.fetchone()
    current_tick = row['tick'] if row else 0
    
    if verbose:
        print(f"Current game tick: {current_tick}")
        print()
    
    # 1. Bootstrap team career totals
    if verbose:
        print("1. Bootstrapping team career totals...")
    
    cursor.execute("SELECT DISTINCT team_name FROM season_summaries")
    teams = [row['team_name'] for row in cursor.fetchall()]
    
    if verbose:
        print(f"   Found {len(teams)} teams")
    
    for team in teams:
        try:
            ftb_state_db.update_team_career_totals(db_path, team, current_tick)
            if verbose:
                print(f"   ✓ {team}")
        except Exception as e:
            print(f"   ✗ Error updating {team}: {e}")
    
    if verbose:
        print()
    
    # 2. Bootstrap team peak/valley metrics
    if verbose:
        print("2. Bootstrapping team peak/valley metrics...")
    
    for team in teams:
        try:
            ftb_state_db.update_team_peak_valley(db_path, team, current_tick)
            if verbose:
                print(f"   ✓ {team}")
        except Exception as e:
            print(f"   ✗ Error updating {team}: {e}")
    
    if verbose:
        print()
    
    # 3. Bootstrap active streaks from recent races
    if verbose:
        print("3. Bootstrapping active streaks...")
    
    cursor.execute("""
        SELECT DISTINCT player_team_name FROM race_results_archive
    """)
    racing_teams = [row['player_team_name'] for row in cursor.fetchall()]
    
    for team in racing_teams:
        try:
            # Get most recent races for this team
            cursor.execute("""
                SELECT race_id, season, finish_positions_json, championship_position_after
                FROM race_results_archive
                WHERE player_team_name = ?
                ORDER BY season DESC, round_number DESC
                LIMIT 20
            """, (team,))
            
            races = cursor.fetchall()
            
            # Process races in reverse order (oldest to newest) to build streaks
            for race in reversed(races):
                try:
                    finishes = json.loads(race['finish_positions_json'])
                    # Find team's finish
                    team_finish = None
                    scored_points = False
                    was_dnf = False
                    
                    for result in finishes:
                        if result.get('team') == team or result.get('driver_team') == team:
                            team_finish = result.get('position', 99)
                            scored_points = team_finish <= 10
                            was_dnf = result.get('status') != 'finished'
                            break
                    
                    if team_finish:
                        ftb_state_db.update_active_streaks_after_race(
                            db_path, team, team_finish, race['race_id'],
                            race['season'], current_tick, scored_points, was_dnf
                        )
                except (json.JSONDecodeError, KeyError) as e:
                    continue
            
            if verbose:
                print(f"   ✓ {team}")
        except Exception as e:
            print(f"   ✗ Error updating streaks for {team}: {e}")
    
    if verbose:
        print()
    
    # 4. Bootstrap momentum metrics
    if verbose:
        print("4. Bootstrapping momentum metrics...")
    
    for team in racing_teams:
        try:
            ftb_state_db.update_momentum_metrics(db_path, team, current_tick)
            if verbose:
                print(f"   ✓ {team}")
        except Exception as e:
            print(f"   ✗ Error updating momentum for {team}: {e}")
    
    if verbose:
        print()
    
    # 5. Bootstrap driver career stats
    if verbose:
        print("5. Bootstrapping driver career stats...")
    
    cursor.execute("""
        SELECT DISTINCT name FROM entities WHERE entity_type = 'driver'
    """)
    drivers = [row['name'] for row in cursor.fetchall()]
    
    if verbose:
        print(f"   Found {len(drivers)} drivers")
    
    for driver in drivers:
        try:
            ftb_state_db.update_driver_career_stats(db_path, driver, current_tick)
            if verbose:
                print(f"   ✓ {driver}")
        except Exception as e:
            print(f"   ✗ Error updating driver {driver}: {e}")
    
    if verbose:
        print()
    
    # 6. Initialize team pulse metrics with baseline values
    if verbose:
        print("6. Initializing team pulse metrics...")
    
    for team in teams:
        try:
            # Get current team state
            cursor.execute("""
                SELECT championship_position, points, budget
                FROM teams
                WHERE team_name = ?
            """, (team,))
            team_row = cursor.fetchone()
            
            if team_row:
                # Calculate simple baseline percentile
                cursor.execute("SELECT COUNT(*) as total FROM teams")
                total_teams = cursor.fetchone()['total']
                
                position = team_row['championship_position'] or total_teams
                percentile = ((total_teams - position + 1) / total_teams) * 100
                
                # Baseline financial stability
                financial_stability = min(100, max(0, team_row['budget'] / 10000))
                
                ftb_state_db.update_team_pulse_metrics(
                    db_path, team, current_tick,
                    performance_trend=percentile,
                    financial_stability=financial_stability,
                    development_speed=50.0,  # Neutral baseline
                    league_percentile=percentile
                )
                
                if verbose:
                    print(f"   ✓ {team} (pulse: {percentile:.1f})")
        except Exception as e:
            print(f"   ✗ Error initializing pulse for {team}: {e}")
    
    if verbose:
        print()
    
    # 7. Initialize default prestige scores
    if verbose:
        print("7. Initializing prestige scores...")
    
    for team in teams:
        try:
            cursor.execute("""
                SELECT championships_won, wins_total, seasons_entered
                FROM team_career_totals
                WHERE team_name = ?
            """, (team,))
            career = cursor.fetchone()
            
            if career:
                # Simple prestige calculation
                championships = career['championships_won'] or 0
                wins = career['wins_total'] or 0
                seasons = career['seasons_entered'] or 1
                
                championship_prestige = min(40, championships * 10)
                wins_prestige = min(30, wins * 0.5)
                longevity_prestige = min(20, seasons * 2)
                
                total_prestige = 50 + championship_prestige + wins_prestige + longevity_prestige
                total_prestige = min(100, total_prestige)
                
                # Determine legacy tier
                if total_prestige >= 90:
                    legacy_tier = "legendary"
                elif total_prestige >= 75:
                    legacy_tier = "storied"
                elif total_prestige >= 60:
                    legacy_tier = "established"
                elif total_prestige >= 45:
                    legacy_tier = "emerging"
                else:
                    legacy_tier = "new"
                
                cursor.execute("""
                    INSERT OR REPLACE INTO team_prestige
                    (team_name, prestige_index, championship_prestige, wins_prestige,
                     longevity_prestige, legacy_tier, last_updated_tick)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (team, total_prestige, championship_prestige, wins_prestige,
                      longevity_prestige, legacy_tier, current_tick))
                
                if verbose:
                    print(f"   ✓ {team} ({legacy_tier}, {total_prestige:.1f})")
        except Exception as e:
            print(f"   ✗ Error initializing prestige for {team}: {e}")
    
    conn.commit()
    conn.close()
    
    if verbose:
        print()
        print("=" * 70)
        print("✓ Historical data bootstrap complete!")
        print()
        print("Summary:")
        print(f"  - {len(teams)} teams updated")
        print(f"  - {len(drivers)} drivers updated")
        print(f"  - Active streaks initialized")
        print(f"  - Momentum metrics calculated")
        print(f"  - Prestige scores initialized")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python ftb_historical_data_bootstrap.py <db_path>")
        print()
        print("Example:")
        print("  python tools/ftb_historical_data_bootstrap.py stations/FromTheBackmarker/ftb_state.db")
        sys.exit(1)
    
    db_path = sys.argv[1]
    
    # Expand relative paths
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.getcwd(), db_path)
    
    print("FTB Historical Data Bootstrap")
    print("=" * 70)
    print()
    
    # Initialize database schema (adds tables if missing)
    print("Ensuring database schema is up to date...")
    ftb_state_db.init_db(db_path)
    print("✓ Schema updated")
    print()
    
    # Run bootstrap
    bootstrap_historical_data(db_path, verbose=True)
    
    print()
    print("Bootstrap complete! Historical data is now available for narrator.")


if __name__ == "__main__":
    main()
