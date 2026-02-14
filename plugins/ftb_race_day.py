"""
FTB Race Day Management System

Handles the interactive race day experience:
1. Pre-race prompt (day before race)
2. Qualifying simulation with event log
3. Interactive live race play-by-play
4. Broadcast crew audio (tier-based quality)
5. Post-race tick advance and results

Decoupled from main tick system to allow player-controlled race viewing.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import time

# Centralised import — bookmark.StationEvent is the canonical class.
# your_runtime re-exports it but the re-export can silently be None.
try:
    from bookmark import StationEvent as _StationEvent
except ImportError:
    _StationEvent = None

def _make_event(source: str, type: str, payload: dict) -> Any:
    """Build a StationEvent with auto-ts, or None if unavailable."""
    if _StationEvent is None:
        return None
    return _StationEvent(source=source, type=type, ts=int(time.time()), payload=payload)


class RaceDayPhase(Enum):
    """Phases of race day experience"""
    IDLE = "idle"                           # No race imminent
    PRE_RACE_PROMPT = "pre_race_prompt"     # Showing yes/no prompt
    QUALI_READY = "quali_ready"             # Waiting for quali sim
    QUALI_RUNNING = "quali_running"         # Qualifying in progress
    QUALI_COMPLETE = "quali_complete"       # Quali done, waiting for race
    RACE_READY = "race_ready"               # Waiting for play button
    RACE_RUNNING = "race_running"           # Race in progress
    RACE_COMPLETE = "race_complete"         # Race done, ready for tick advance
    POST_RACE_ADVANCE = "post_race_advance" # Advancing tick to show results


@dataclass
class RaceDayState:
    """State machine for race day experience"""
    phase: RaceDayPhase = RaceDayPhase.IDLE
    
    # Race identification
    race_tick: Optional[int] = None
    league_id: Optional[str] = None
    track_id: Optional[str] = None
    
    # Qualifying results
    quali_grid: List[Tuple] = field(default_factory=list)  # (team, driver, quali_score)
    quali_events: List[Any] = field(default_factory=list)  # SimEvents from quali
    
    # Race data
    race_result: Optional[Any] = None  # RaceResult object
    race_lap_cursor: int = 0           # Current lap being shown
    race_event_cursor: int = 0         # Current event being shown
    
    # Live race control
    live_race_active: bool = False
    live_race_speed: float = 10.0      # Seconds per lap
    live_race_last_update: float = 0.0
    
    # Live race streaming data (updated progressively)
    live_standings: List[Dict] = field(default_factory=list)  # Current positions, gaps
    live_events: List[Dict] = field(default_factory=list)     # Events shown so far
    current_lap: int = 0               # Current lap number
    total_laps: int = 0                # Total race laps
    
    # Audio state
    broadcast_active: bool = False
    music_ducked: bool = False
    
    # User choice
    player_wants_live_race: bool = False
    

def should_show_pre_race_prompt(state: 'SimState', current_tick: int) -> Optional[Tuple[int, Any, str]]:
    """
    Check if we should show pre-race prompt.
    
    Called BEFORE tick advances. Since tick will advance from N to N+1, and races execute
    at state.tick AFTER the advance, we need to check if tick N+1 has a race scheduled.
    
    Flow:
    1. We're at tick N (before advance)
    2. This function checks if tick N+1 has a race
    3. If yes, show prompt and PAUSE (don't advance tick yet)
    4. Player responds
    5. Tick advances from N to N+1
    6. Race executes at the new state.tick (N+1)
    """
    if not state.player_team:
        return None
    
    # Find player's league
    player_league = None
    for league in state.leagues.values():
        if state.player_team in league.teams:
            player_league = league
            break
    
    if not player_league:
        return None
    
    # Check if tick AFTER the upcoming advance will have a race
    # Current tick is N, after advance it will be N+1
    # So check if any race is scheduled at N+1
    next_tick_after_advance = current_tick + 1
    
    print(f"[FTB RACE DAY CHECK] Current tick: {current_tick}, will advance to: {next_tick_after_advance}")
    print(f"[FTB RACE DAY CHECK] Player league: {player_league.name}, schedule: {player_league.schedule[:5] if len(player_league.schedule) > 5 else player_league.schedule}")
    
    for entry in player_league.schedule:
        # Handle both formats
        if isinstance(entry, (tuple, list)) and len(entry) == 2:
            race_tick, track_id = entry
        else:
            race_tick = entry
            track_id = None
        
        if race_tick == next_tick_after_advance:
            # Skip if this race was already completed or already prompted
            if hasattr(state, 'completed_race_ticks') and (player_league.league_id, race_tick) in state.completed_race_ticks:
                print(f"[FTB RACE DAY CHECK] ⏭️ Race at tick {race_tick} already completed, skipping prompt")
                return None
            if hasattr(state, 'prompted_race_ticks') and (player_league.league_id, race_tick) in state.prompted_race_ticks:
                print(f"[FTB RACE DAY CHECK] ⏭️ Race at tick {race_tick} already prompted, skipping re-prompt")
                return None
            print(f"[FTB RACE DAY CHECK] ✅ MATCH! Race scheduled at tick {race_tick}")
            return (race_tick, player_league, track_id)
    
    return None


def simulate_qualifying(state: 'SimState', league: Any, track: Any, rng: Any) -> Tuple[List[Tuple], List[Any]]:
    """
    Simulate qualifying session and generate events for event log.
    
    Returns:
        (qualifying_grid, quali_events)
        - qualifying_grid: List of (team, driver, quali_score) tuples
        - quali_events: List of SimEvents for event log
    """
    from plugins.ftb_game import FTBSimulation, SimEvent, QUALIFYING_WEIGHTS
    
    events = []
    
    # Run qualifying scoring (same as race weekend)
    qual_weights = QUALIFYING_WEIGHTS['default']
    qualifying_scores = []
    
    for team in league.teams:
        if not team.drivers:
            continue
        
        car = team.car
        
        # Qualify ALL drivers from the team (both driver slots)
        # Must match simulate_race_weekend which iterates all drivers
        for driver in team.drivers:
            if not driver:
                continue
            
            # Calculate quali performance
            d_score = FTBSimulation.score_entity(driver, qual_weights['driver'])
            c_score = FTBSimulation.score_entity(car, qual_weights['car'])
            
            combined_score = FTBSimulation.compose_phase_score(
                {'driver': d_score, 'car': c_score},
                qual_weights['phase_weights']
            )
            
            # Add some randomness
            variance = 5.0 * (1.0 - getattr(driver, 'consistency', 50.0) / 100.0)
            final_score = combined_score + rng.uniform(-variance, variance)
            
            qualifying_scores.append((team, driver, final_score))
    
    # Sort by score (highest = pole)
    qualifying_scores.sort(key=lambda x: x[2], reverse=True)
    
    # Generate quali events
    # Pole position
    if qualifying_scores:
        pole_team, pole_driver, pole_score = qualifying_scores[0]
        events.append(SimEvent(
            event_type="outcome",
            category="qualifying_pole",
            ts=state.tick,
            priority=75.0 if pole_team == state.player_team else 60.0,
            severity="info",
            data={
                'driver': pole_driver.name,
                'team': pole_team.name,
                'score': pole_score,
                'league': league.name,
                'track': track.name if track else "Unknown",
                'message': f'{pole_driver.name} takes pole position!'
            }
        ))
    
    # Notable performances (top 3 + player team if not in top 3)
    for i, (team, driver, score) in enumerate(qualifying_scores[:3], 1):
        if i > 1:  # Skip pole (already added)
            events.append(SimEvent(
                event_type="outcome",
                category="qualifying_result",
                ts=state.tick,
                priority=65.0 if team == state.player_team else 50.0,
                severity="info",
                data={
                    'driver': driver.name,
                    'team': team.name,
                    'position': i,
                    'score': score,
                    'league': league.name,
                    'track': track.name if track else "Unknown",
                    'message': f'P{i}: {driver.name} ({team.name})'
                }
            ))
    
    # Player team result if not in top 3
    if state.player_team:
        player_pos = next((i for i, (t, _, _) in enumerate(qualifying_scores, 1) 
                          if t == state.player_team), None)
        if player_pos and player_pos > 3:
            player_entry = qualifying_scores[player_pos - 1]
            events.append(SimEvent(
                event_type="outcome",
                category="qualifying_result",
                ts=state.tick,
                priority=70.0,
                severity="info",
                data={
                    'driver': player_entry[1].name,
                    'team': player_entry[0].name,
                    'position': player_pos,
                    'score': player_entry[2],
                    'league': league.name,
                    'track': track.name if track else "Unknown",
                    'message': f'P{player_pos}: {player_entry[1].name} ({player_entry[0].name})'
                }
            ))
    
    # Random quali incidents (crashes, mechanical issues)
    # Small chance for drama
    if rng.random() < 0.15:  # 15% chance of incident
        # Pick a random team that's not on pole
        if len(qualifying_scores) > 3:
            incident_idx = rng.randint(3, len(qualifying_scores) - 1)
            incident_team, incident_driver, _ = qualifying_scores[incident_idx]
            
            incident_types = ['crash', 'mechanical', 'track_limits']
            incident_type = rng.choice(incident_types)
            
            if incident_type == 'crash':
                desc = f'{incident_driver.name} crashes in qualifying, will start from back'
                # Trigger crash audio
                _trigger_quali_crash_audio(state, severity=0.6)
            elif incident_type == 'mechanical':
                desc = f'{incident_driver.name} suffers mechanical issue in qualifying'
            else:
                desc = f'{incident_driver.name} has lap deleted for track limits violation'
            
            events.append(SimEvent(
                event_type="outcome",
                category="qualifying_incident",
                ts=state.tick,
                priority=70.0 if incident_team == state.player_team else 55.0,
                severity="warning",
                data={
                    'driver': incident_driver.name,
                    'team': incident_team.name,
                    'incident_type': incident_type,
                    'message': desc
                }
            ))
    
    return qualifying_scores, events


def _trigger_quali_crash_audio(state, severity=0.6):
    """Trigger crash audio during qualifying"""
    try:
        runtime = getattr(state, '_runtime', None)
        if not runtime:
            return
        
        event_q = runtime.get('event_q')
        if not event_q:
            return
        
        from bookmark import StationEvent
        
        event_q.put(StationEvent(
            source='ftb',
            type='audio',
            ts=int(time.time()),
            payload={
                'audio_type': 'world',
                'action': 'crash',
                'severity': severity
            }
        ))
    except:
        pass


def get_broadcast_audio_params(tier: int) -> Dict[str, Any]:
    """
    Get audio parameters for broadcast crew based on league tier.
    
    Grassroots = fuzzy radio quality
    Higher tiers = progressively clearer
    """
    tier_audio_config = {
        1: {  # Grassroots
            'filter': 'radio_fuzzy',
            'gain': 0.4,
            'background_static': 0.3,
            'voice_clarity': 0.5,
            'commentary_style': 'local_radio'
        },
        2: {  # Formula V
            'filter': 'radio_medium',
            'gain': 0.6,
            'background_static': 0.15,
            'voice_clarity': 0.65,
            'commentary_style': 'regional_broadcast'
        },
        3: {  # Formula X
            'filter': 'radio_clear',
            'gain': 0.75,
            'background_static': 0.05,
            'voice_clarity': 0.8,
            'commentary_style': 'professional'
        },
        4: {  # Formula Y
            'filter': 'broadcast_hq',
            'gain': 0.9,
            'background_static': 0.0,
            'voice_clarity': 0.95,
            'commentary_style': 'premium'
        },
        5: {  # Formula Z
            'filter': 'broadcast_premium',
            'gain': 1.0,
            'background_static': 0.0,
            'voice_clarity': 1.0,
            'commentary_style': 'world_class'
        }
    }
    
    return tier_audio_config.get(tier, tier_audio_config[1])  # Default to tier 1 if invalid


def start_live_race_stream(state: 'SimState', race_result: Any) -> None:
    """
    Initialize live race streaming from a completed race simulation.
    Race has already been simulated - we're just streaming it progressively.
    
    Args:
        state: Game state with race_day_state
        race_result: Complete RaceResult object from simulation
    """
    if not state.race_day_state:
        return
    
    rds = state.race_day_state
    rds.race_result = race_result
    rds.current_lap = 0
    rds.total_laps = len(set(lap.lap_number for lap in race_result.laps)) if race_result.laps else 0
    rds.live_standings = []
    rds.live_events = []
    rds.race_lap_cursor = 0
    rds.race_event_cursor = 0
    rds.live_race_active = True
    
    # Start engine audio based on league tier
    _start_race_engine_audio(state, rds.league_id)
    
    # Notify commentary system race is starting
    _emit_race_start_event(state, rds.league_id, rds.track_id)
    
    print(f"[FTB RACE DAY] 🏁 Live race stream initialized: {rds.total_laps} laps")


def _start_race_engine_audio(state, league_id):
    """Start engine audio based on league tier"""
    try:
        runtime = getattr(state, '_runtime', None)
        if not runtime:
            return
        
        event_q = runtime.get('event_q')
        if not event_q:
            return
        
        from bookmark import StationEvent
        
        # Map league ID to tier
        league_tier = 'midformula'  # Default
        if league_id:
            if 'grassroots' in league_id.lower() or 'tier1' in league_id.lower():
                league_tier = 'grassroots'
            elif 'formulaz' in league_id.lower() or 'tier3' in league_id.lower():
                league_tier = 'formulaz'
        
        event_q.put(StationEvent(
            source='ftb',
            type='audio',
            ts=int(time.time()),
            payload={
                'audio_type': 'world',
                'action': 'engine_start',
                'league_tier': league_tier
            }
        ))
    except:
        pass


def _stop_race_engine_audio(state):
    """Stop engine audio when race ends"""
    try:
        runtime = getattr(state, '_runtime', None)
        if not runtime:
            return
        
        event_q = runtime.get('event_q')
        if not event_q:
            return
        
        from bookmark import StationEvent
        
        event_q.put(StationEvent(
            source='ftb',
            type='audio',
            ts=int(time.time()),
            payload={
                'audio_type': 'world',
                'action': 'engine_stop'
            }
        ))
    except:
        pass


def _emit_race_start_event(state, league_id, track_id):
    """Emit race start event for commentary system"""
    try:
        runtime = getattr(state, '_runtime', None)
        if not runtime:
            return
        
        event_q = runtime.get('event_q')
        if not event_q:
            return
        
        from bookmark import StationEvent
        
        player_team_name = state.player_team.name if state.player_team else ''
        
        event_q.put(StationEvent(
            source='ftb',
            type='race_streaming_started',
            ts=int(time.time()),
            payload={
                'league_id': league_id or '',
                'track_id': track_id or '',
                'player_team': player_team_name
            }
        ))
    except:
        pass


def _trigger_race_event_audio(state, event):
    """
    Trigger audio engine sounds based on race events.
    
    Args:
        state: Game state with runtime access
        event: RaceEvent object with event_type and description
    """
    try:
        runtime = getattr(state, '_runtime', None)
        if not runtime:
            return
        
        event_q = runtime.get('event_q')
        if not event_q:
            return
        
        from bookmark import StationEvent
        
        event_type = event.event_type.lower()
        
        # Map event types to audio triggers
        if 'crash' in event_type or 'accident' in event_type or 'collision' in event_type:
            # Determine severity from description
            severity = 0.5  # Default medium
            if 'massive' in event.description.lower() or 'huge' in event.description.lower():
                severity = 0.9
            elif 'heavy' in event.description.lower() or 'major' in event.description.lower():
                severity = 0.7
            elif 'minor' in event.description.lower() or 'light' in event.description.lower():
                severity = 0.3
            
            # Play crash sound
            event_q.put(StationEvent(
                source='ftb',
                type='audio',
                ts=int(time.time()),
                payload={
                    'audio_type': 'world',
                    'action': 'crash',
                    'severity': severity
                }
            ))
            
            # Emit for commentary system
            event_q.put(StationEvent(
                source='ftb',
                type='incident',
                ts=int(time.time()),
                payload={
                    'driver': getattr(event, 'driver_name', 'Unknown'),
                    'team': getattr(event, 'team_name', 'Unknown'),
                    'severity': severity,
                    'lap': getattr(event, 'lap_number', 0),
                    'is_player_team': getattr(event, 'is_player', False),
                    'description': event.description
                }
            ))
        
        elif 'overtake' in event_type or 'pass' in event_type:
            # Crowd reacts to overtakes
            event_q.put(StationEvent(
                source='ftb',
                type='audio',
                ts=int(time.time()),
                payload={
                    'audio_type': 'world',
                    'action': 'crowd_reaction',
                    'reaction_type': 'whoop'
                }
            ))
            
            # Emit for commentary system
            event_q.put(StationEvent(
                source='ftb',
                type='overtake',
                ts=int(time.time()),
                payload={
                    'driver': getattr(event, 'driver_name', 'Unknown'),
                    'team': getattr(event, 'team_name', 'Unknown'),
                    'old_position': getattr(event, 'old_position', 0),
                    'new_position': getattr(event, 'new_position', 0),
                    'lap': getattr(event, 'lap_number', 0),
                    'is_player_team': getattr(event, 'is_player', False)
                }
            ))
        
        elif event_type == 'race_start' or 'lights out' in event.description.lower():
            # Big crowd cheer at race start
            event_q.put(StationEvent(
                source='ftb',
                type='audio',
                ts=int(time.time()),
                payload={
                    'audio_type': 'world',
                    'action': 'crowd_reaction',
                    'reaction_type': 'cheer'
                }
            ))
        
        elif event_type == 'race_finish' or 'checkered flag' in event.description.lower():
            # Crowd cheer at finish
            event_q.put(StationEvent(
                source='ftb',
                type='audio',
                ts=int(time.time()),
                payload={
                    'audio_type': 'world',
                    'action': 'crowd_reaction',
                    'reaction_type': 'cheer'
                }
            ))
        
        elif 'mechanical' in event_type or 'dnf' in event_type:
            # Light crash sound for mechanical failures
            event_q.put(StationEvent(
                source='ftb',
                type='audio',
                ts=int(time.time()),
                payload={
                    'audio_type': 'world',
                    'action': 'crash',
                    'severity': 0.2
                }
            ))
    
    except Exception as e:
        # Silently fail - audio is not critical
        pass


def advance_race_stream_lap(state: 'SimState') -> bool:
    """
    Advance race stream by one lap. Updates live_standings and live_events.
    
    Returns:
        True if more laps remain, False if race complete
    """
    if not state.race_day_state or not state.race_day_state.race_result:
        return False
    
    rds = state.race_day_state
    race_result = rds.race_result
    
    if rds.current_lap >= rds.total_laps:
        return False  # Race complete
    
    # Advance to next lap
    rds.current_lap += 1
    lap_num = rds.current_lap
    
    # Get lap data for this lap
    lap_data_this_lap = [l for l in race_result.laps if l.lap_number == lap_num]
    
    # Sort by position to get standings
    lap_data_this_lap.sort(key=lambda l: l.position)
    
    # Update live standings
    rds.live_standings = []
    for lap_data in lap_data_this_lap:
        is_player = False
        if state.player_team and lap_data.team_name == state.player_team.name:
            is_player = True
        
        rds.live_standings.append({
            'position': lap_data.position,
            'driver': lap_data.driver_name,
            'team': lap_data.team_name,
            'gap': lap_data.gap_to_leader,
            'status': 'racing',
            'is_player': is_player
        })
    
    # Add events that occurred on this lap
    events_this_lap = [e for e in race_result.race_events if e.lap_number == lap_num]
    
    for event in events_this_lap:
        event_dict = {
            'lap': event.lap_number,
            'type': event.event_type,
            'text': event.description
        }
        rds.live_events.append(event_dict)
        
        # Trigger audio for race events
        _trigger_race_event_audio(state, event)
    
    print(f"[FTB RACE DAY] 🏁 Lap {lap_num}/{rds.total_laps}: {len(rds.live_standings)} drivers, {len(events_this_lap)} events")
    
    return rds.current_lap < rds.total_laps  # More laps remaining?


def complete_race_stream(state: 'SimState') -> None:
    """Mark race stream as complete and add DNF statuses to standings"""
    if not state.race_day_state or not state.race_day_state.race_result:
        return
    
    rds = state.race_day_state
    race_result = rds.race_result
    
    # Update standings with DNF drivers
    dnf_positions = [pos for pos in race_result.final_positions if pos[2] != 'finished']
    
    for driver_name, team_name, status in dnf_positions:
        # Check if already in standings
        existing = [s for s in rds.live_standings if s['driver'] == driver_name]
        if existing:
            existing[0]['status'] = status
        else:
            # Add DNF driver at end
            is_player = state.player_team and team_name == state.player_team.name
            rds.live_standings.append({
                'position': len(rds.live_standings) + 1,
                'driver': driver_name,
                'team': team_name,
                'gap': 0.0,
                'status': status,
                'is_player': is_player
            })
    
    rds.live_race_active = False
    rds.phase = RaceDayPhase.RACE_COMPLETE
    
    # Stop engine audio
    _stop_race_engine_audio(state)
    
    print(f"[FTB RACE DAY] 🏁 Race stream complete!")
