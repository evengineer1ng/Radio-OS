#!/usr/bin/env python3
"""
Diagnostic script to check race day state in a save file.

Usage:
    python3 check_race_state.py saves/yourfile.json
"""

import json
import sys
from pathlib import Path


def check_race_state(save_path: Path):
    """Check race day state and tracking in a save file"""
    print(f"Checking: {save_path}\n")
    
    with open(save_path, 'r') as f:
        data = json.load(f)
    
    # Basic info
    print("=" * 60)
    print("BASIC INFO")
    print("=" * 60)
    print(f"Save Version: {data.get('save_version', 'MISSING')}")
    print(f"Current Tick: {data.get('tick', 0)}")
    print(f"Season: {data.get('season_number', 1)}")
    print(f"Races Completed: {data.get('races_completed_this_season', 0)}")
    print(f"Phase: {data.get('phase', 'unknown')}")
    print()
    
    # Race day state
    print("=" * 60)
    print("RACE DAY STATE")
    print("=" * 60)
    print(f"Race Day Active: {data.get('race_day_active', False)}")
    
    completed = data.get('completed_race_ticks', [])
    prompted = data.get('prompted_race_ticks', [])
    
    print(f"Completed Race Ticks: {len(completed)}")
    if completed:
        print(f"  Sample: {completed[:5]}")
    
    print(f"Prompted Race Ticks: {len(prompted)}")
    if prompted:
        print(f"  Sample: {prompted[:5]}")
    
    race_day_state = data.get('race_day_state', None)
    if race_day_state:
        print("\nRace Day State Object:")
        print(f"  Phase: {race_day_state.get('phase', 'MISSING')}")
        print(f"  Race Tick: {race_day_state.get('race_tick', 'MISSING')}")
        print(f"  League ID: {race_day_state.get('league_id', 'MISSING')}")
    else:
        print("\n⚠️  No race_day_state object (OLD SAVE)")
    print()
    
    # Player info
    print("=" * 60)
    print("PLAYER INFO")
    print("=" * 60)
    player_team = data.get('player_team', {})
    if player_team:
        print(f"Team Name: {player_team.get('name', 'Unknown')}")
        print(f"League ID: {player_team.get('league_id', 'MISSING')}")
        print(f"Budget: ${player_team.get('budget', {}).get('cash', 0):,.2f}")
    else:
        print("No player team found")
    print()
    
    # League info
    print("=" * 60)
    print("LEAGUES")
    print("=" * 60)
    leagues = data.get('leagues', {})
    print(f"Total Leagues: {len(leagues)}")
    
    player_league = None
    if player_team:
        player_league_id = player_team.get('league_id')
        for league_id, league in leagues.items():
            if league_id == player_league_id:
                player_league = league
                break
    
    if player_league:
        print(f"\nPlayer's League:")
        print(f"  Name: {player_league.get('name', 'Unknown')}")
        print(f"  Tier: {player_league.get('tier', '?')}")
        print(f"  Races This Season: {player_league.get('races_this_season', 0)}")
        
        schedule = player_league.get('schedule', [])
        print(f"  Schedule Length: {len(schedule)}")
        
        if schedule:
            print(f"  Next 3 Races:")
            current_tick = data.get('tick', 0)
            count = 0
            for entry in schedule:
                if isinstance(entry, list) and len(entry) >= 1:
                    race_tick = entry[0]
                    track_id = entry[1] if len(entry) > 1 else None
                else:
                    race_tick = entry
                    track_id = None
                
                if race_tick >= current_tick and count < 3:
                    print(f"    Tick {race_tick}: track_id={track_id}")
                    count += 1
    print()
    
    # Diagnosis
    print("=" * 60)
    print("DIAGNOSIS")
    print("=" * 60)
    
    issues = []
    
    # Check for old save markers
    if not completed and not prompted:
        if data.get('races_completed_this_season', 0) > 0:
            issues.append("⚠️  OLD SAVE: Has completed races but no tracking sets")
            issues.append("   → Will be auto-fixed on load with reconstruction")
    
    if not race_day_state:
        issues.append("⚠️  OLD SAVE: Missing race_day_state object")
        issues.append("   → Will be auto-initialized on load")
    
    if data.get('race_day_active', False):
        issues.append("⚠️  STALE STATE: race_day_active=True in save file")
        issues.append("   → Will be auto-reset to False on load")
    
    if race_day_state and race_day_state.get('phase', 'idle') != 'idle':
        issues.append(f"⚠️  STALE STATE: race_day_state.phase={race_day_state.get('phase')}")
        issues.append("   → Will be auto-reset to IDLE on load")
    
    if not issues:
        print("✅ No issues detected - save looks good!")
    else:
        for issue in issues:
            print(issue)
    
    print("\n" + "=" * 60)
    print("RECOMMENDATION")
    print("=" * 60)
    
    if not issues:
        print("✅ Save is ready to load - should work fine")
    else:
        print("ℹ️  Save has some old/stale state, but the NEW FIXES will")
        print("   automatically handle these issues on load.")
        print("\n   Just load the save normally and races should work!")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 check_race_state.py <save_file.json>")
        print("\nExample:")
        print("  python3 check_race_state.py saves/patchedgreatstart.json")
        sys.exit(1)
    
    save_file = Path(sys.argv[1])
    
    if not save_file.exists():
        print(f"Error: File not found: {save_file}")
        sys.exit(1)
    
    try:
        check_race_state(save_file)
    except Exception as e:
        print(f"\n❌ Error reading save file: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
