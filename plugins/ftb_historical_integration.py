"""
FTB Historical Data Integration Example

This module shows how to integrate historical data updates into the FTB game
simulation flow.

Add these hooks to ftb_game.py at key points in the game loop.
"""

from plugins import ftb_state_db


# ============================================================================
# RACE COMPLETION HOOK
# ============================================================================

def on_race_completed(game_state, race_results):
    """
    Call this after race simulation completes.
    
    Args:
        game_state: Current game state object
        race_results: Race results with finish positions, DNFs, etc.
    """
    db_path = game_state.db_path
    current_tick = game_state.tick
    current_season = game_state.season
    race_id = f"s{current_season}_r{race_results['round_number']}_{race_results['track']}"
    
    # Update streaks for all teams
    for team_name, result in race_results['team_results'].items():
        finish_position = result['best_position']
        scored_points = finish_position <= 10
        had_dnf = result.get('dnf_count', 0) > 0
        
        ftb_state_db.update_active_streaks_after_race(
            db_path=db_path,
            team_name=team_name,
            finish_position=finish_position,
            race_id=race_id,
            season=current_season,
            tick=current_tick,
            scored_points=scored_points,
            was_dnf=had_dnf
        )
    
    # Update momentum metrics for player team
    player_team = game_state.player_team_name
    ftb_state_db.update_momentum_metrics(db_path, player_team, current_tick)
    
    # Update team pulse after race
    # Calculate components from game state
    performance_trend = calculate_performance_trend(game_state, player_team)
    financial_stability = calculate_financial_stability(game_state, player_team)
    development_speed = calculate_development_speed(game_state, player_team)
    league_percentile = calculate_league_percentile(game_state, player_team)
    
    ftb_state_db.update_team_pulse_metrics(
        db_path=db_path,
        team_name=player_team,
        tick=current_tick,
        performance_trend=performance_trend,
        financial_stability=financial_stability,
        development_speed=development_speed,
        league_percentile=league_percentile
    )
    
    print(f"[FTB Historical] Updated streaks and momentum after {race_id}")


# ============================================================================
# SEASON END HOOK
# ============================================================================

def on_season_completed(game_state):
    """
    Call this at end of season after final standings are determined.
    
    Args:
        game_state: Current game state object
    """
    db_path = game_state.db_path
    current_tick = game_state.tick
    
    print(f"[FTB Historical] Running end-of-season updates for Season {game_state.season}...")
    
    # Bulk update all teams' historical data
    ftb_state_db.bulk_update_historical_data(db_path, current_tick)
    
    # Update championship history
    write_championship_history(game_state)
    
    # Update team tier history
    for team in game_state.all_teams:
        update_team_tier_history(db_path, team, game_state.season, current_tick)
    
    print(f"[FTB Historical] Season {game_state.season} historical data complete")


def write_championship_history(game_state):
    """Write championship history record for completed season."""
    db_path = game_state.db_path
    season = game_state.season
    
    # Get final standings (assuming sorted by points)
    standings = sorted(game_state.league.teams, key=lambda t: t.points, reverse=True)
    
    if len(standings) < 3:
        return
    
    champion = standings[0]
    runner_up = standings[1]
    third_place = standings[2]
    
    title_margin = champion.points - runner_up.points
    
    # Calculate parity index (std dev of team CPI)
    import statistics
    cpis = [team.car_performance_index for team in standings]
    parity_index = statistics.stdev(cpis) if len(cpis) > 1 else 0.0
    
    # Determine when title was decided
    # (This would need logic based on when mathematical certainty occurred)
    title_decided_round = None  # TODO: implement
    
    with ftb_state_db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO championship_history
            (season, league_id, tier, champion_team, champion_points,
             runner_up_team, runner_up_points, third_place_team, third_place_points,
             title_margin, title_decided_round, parity_index, last_updated_tick)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            season,
            game_state.league.id,
            game_state.league.tier,
            champion.name,
            champion.points,
            runner_up.name,
            runner_up.points,
            third_place.name,
            third_place.points,
            title_margin,
            title_decided_round,
            parity_index,
            game_state.tick
        ))


def update_team_tier_history(db_path: str, team, season: int, tick: int):
    """Update team's tier history record for this season."""
    # Calculate performance tier based on percentile
    # This would use league standings to determine where team finished
    
    # For now, simple mapping based on championship position
    position = team.championship_position
    total_teams = team.league.team_count
    
    percentile = ((total_teams - position + 1) / total_teams) * 100
    
    if percentile >= 95:
        perf_tier = "dominant"
    elif percentile >= 80:
        perf_tier = "contender"
    elif percentile >= 60:
        perf_tier = "upper_midfield"
    elif percentile >= 40:
        perf_tier = "midfield"
    elif percentile >= 20:
        perf_tier = "lower_midfield"
    elif percentile >= 5:
        perf_tier = "backmarker"
    else:
        perf_tier = "crisis"
    
    with ftb_state_db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO team_tier_history
            (team_name, season, tier, performance_tier, tier_percentile,
             last_updated_tick)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (team.name, season, team.tier, perf_tier, percentile, tick))


# ============================================================================
# HELPER FUNCTIONS FOR PULSE CALCULATION
# ============================================================================

def calculate_performance_trend(game_state, team_name: str) -> float:
    """Calculate performance trend component (0-100)."""
    # Get team's recent championship positions
    # Compare to historical average
    # Return 0-100 score where 100 = significantly improving
    
    # Simplified: use current percentile
    team = game_state.get_team(team_name)
    position = team.championship_position or 20
    total_teams = len(game_state.league.teams)
    
    percentile = ((total_teams - position + 1) / total_teams) * 100
    return percentile


def calculate_financial_stability(game_state, team_name: str) -> float:
    """Calculate financial stability component (0-100)."""
    team = game_state.get_team(team_name)
    
    # Calculate runway in weeks
    weekly_burn = team.weekly_expenses if hasattr(team, 'weekly_expenses') else 5000
    runway_weeks = team.budget / weekly_burn if weekly_burn > 0 else 52
    
    # Map runway to 0-100 scale
    if runway_weeks >= 20:
        return 100.0
    elif runway_weeks >= 10:
        return 70.0 + (runway_weeks - 10) * 3.0
    elif runway_weeks >= 5:
        return 40.0 + (runway_weeks - 5) * 6.0
    else:
        return runway_weeks * 8.0


def calculate_development_speed(game_state, team_name: str) -> float:
    """Calculate development speed component (0-100)."""
    team = game_state.get_team(team_name)
    
    # Compare team's recent upgrades to league average
    # This would need tracking of upgrade frequency
    
    # Simplified: use engineering staff rating as proxy
    if hasattr(team, 'engineering_rating'):
        return min(100, team.engineering_rating * 1.2)
    
    return 50.0  # Neutral


def calculate_league_percentile(game_state, team_name: str) -> float:
    """Calculate league percentile (0-100)."""
    team = game_state.get_team(team_name)
    position = team.championship_position or 20
    total_teams = len(game_state.league.teams)
    
    return ((total_teams - position + 1) / total_teams) * 100


# ============================================================================
# NARRATOR QUERY EXAMPLES
# ============================================================================

def get_narrator_context_packet(db_path: str, team_name: str) -> dict:
    """
    Get comprehensive historical context for narrator.
    
    This is what the narrator plugin would call to get rich context.
    """
    from plugins.ftb_db_explorer import HistoricalDataQuery
    
    query = HistoricalDataQuery(db_path)
    summary = query.get_team_summary(team_name)
    
    if not summary:
        return {}
    
    # Build rich context packet
    context = {
        "team_name": team_name,
        
        # Current state
        "team_pulse": summary.team_pulse,
        "competitive_tier": summary.competitive_tier,
        "narrative_temperature": summary.narrative_temperature,
        "prestige_index": summary.prestige_index,
        
        # Career totals
        "career": {
            "seasons": summary.seasons_entered,
            "races": summary.races_entered,
            "wins": summary.wins_total,
            "podiums": summary.podiums_total,
            "championships": summary.championships_won,
            "win_rate": f"{summary.win_rate:.1f}%"
        },
        
        # Active streaks
        "streaks": {
            "current_points": summary.current_points_streak,
            "current_wins": summary.current_win_streak,
            "record_points": summary.longest_points_streak_ever,
            "approaching_record": summary.current_points_streak >= summary.longest_points_streak_ever * 0.8
        },
        
        # Peak performance
        "peak": {
            "best_finish": summary.best_season_finish,
            "best_finish_year": summary.best_season_finish_year,
            "golden_era": f"Season {summary.golden_era_start}-{summary.golden_era_end}" if summary.golden_era_start else None
        },
        
        # Narrative hooks
        "hooks": []
    }
    
    # Add narrative hooks based on data
    if summary.current_points_streak >= summary.longest_points_streak_ever * 0.8:
        context["hooks"].append({
            "type": "streak_alert",
            "message": f"Just {summary.longest_points_streak_ever - summary.current_points_streak} races from all-time record",
            "priority": "high"
        })
    
    if summary.team_pulse >= 80:
        context["hooks"].append({
            "type": "surge",
            "message": f"Team pulse at {summary.team_pulse:.1f}—highest this season",
            "priority": "medium"
        })
    
    if summary.best_season_finish and summary.best_season_finish <= 3:
        context["hooks"].append({
            "type": "legacy",
            "message": f"Former championship contender (P{summary.best_season_finish}, Season {summary.best_season_finish_year})",
            "priority": "low"
        })
    
    return context


def check_milestone_alerts(db_path: str, team_name: str) -> list:
    """
    Check if team has hit any milestones worth announcing.
    
    Returns list of milestone alerts for narrator.
    """
    from plugins.ftb_db_explorer import HistoricalDataQuery
    
    query = HistoricalDataQuery(db_path)
    summary = query.get_team_summary(team_name)
    
    alerts = []
    
    # Career milestones
    if summary.wins_total in [1, 10, 25, 50, 100]:
        alerts.append({
            "type": "career_milestone",
            "message": f"Career win #{summary.wins_total}!",
            "priority": "high"
        })
    
    if summary.races_entered in [50, 100, 200, 500]:
        alerts.append({
            "type": "career_milestone",
            "message": f"{summary.races_entered}th career start",
            "priority": "medium"
        })
    
    # Streak milestones
    if summary.current_points_streak in [5, 10, 15, 20]:
        alerts.append({
            "type": "streak_milestone",
            "message": f"{summary.current_points_streak} consecutive points finishes",
            "priority": "high"
        })
    
    # Record breaking
    if summary.current_points_streak > summary.longest_points_streak_ever:
        alerts.append({
            "type": "record_broken",
            "message": f"NEW ALL-TIME POINTS STREAK RECORD: {summary.current_points_streak} races!",
            "priority": "critical"
        })
    
    return alerts


# ============================================================================
# USAGE IN FTB_GAME.PY
# ============================================================================

"""
To integrate, add these calls in ftb_game.py:

1. After race simulation:
   
   from plugins import ftb_historical_integration
   ftb_historical_integration.on_race_completed(game_state, race_results)

2. At end of season:
   
   ftb_historical_integration.on_season_completed(game_state)

3. In narrator plugin:
   
   context = ftb_historical_integration.get_narrator_context_packet(
       db_path, player_team_name
   )
   
   # Use context in prompt:
   prompt = f'''
   Team: {context["team_name"]}
   Team Pulse: {context["team_pulse"]}/100 ({context["narrative_temperature"]})
   Career: {context["career"]["wins"]} wins in {context["career"]["races"]} races
   Current Streak: {context["streaks"]["current_points"]} points finishes
   
   Generate commentary considering this context...
   '''
   
4. For milestone announcements:
   
   alerts = ftb_historical_integration.check_milestone_alerts(
       db_path, player_team_name
   )
   
   for alert in alerts:
       if alert["priority"] in ["critical", "high"]:
           # Queue announcement segment
           queue_narrator_segment(alert["message"])
"""
