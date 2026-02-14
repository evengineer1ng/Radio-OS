"""
FTB INTERACTIVE RACE DAY - IMPLEMENTATION GUIDE
================================================

This document outlines the complete implementation of the new interactive race day system.

## OVERVIEW

Transform race day from instant simulation to an interactive, player-controlled experience:
1. Pre-race prompt appears the day BEFORE race
2. Player chooses to watch live or skip
3. If watching: quali simulates → visible in event log → no tick advance yet
4. Player goes to ftb_pbp tab, clicks "Play Live Race"
5. Race plays out lap-by-lap with broadcast commentary
6. After race completes, tick advances and results appear

## COMPONENTS CREATED

1. **ftb_race_day.py** - State machine for race day phases
2. **ftb_broadcast_commentary.py** - Two-voice broadcast crew generator

## COMPONENTS TO MODIFY

### 1. ftb_game.py (SimState & FTBSimulation)

**Add to SimState __init__:**
```python
from plugins.ftb_race_day import RaceDayState, RaceDayPhase
self.race_day_state = RaceDayState()
```

**Modify tick_simulation() to check for upcoming races:**
```python
# BEFORE advancing tick, check if next tick has a race
race_info = should_show_pre_race_prompt(state, state.tick)
if race_info:
    # Set state to show prompt, DON'T advance tick yet
    race_tick, league, track_id = race_info
    state.race_day_state.phase = RaceDayPhase.PRE_RACE_PROMPT
    state.race_day_state.race_tick = race_tick
    state.race_day_state.league_id = league.league_id
    state.race_day_state.track_id = track_id
    
    # Emit event to show prompt in UI
    events.append(SimEvent(
        event_type="ui_action",
        category="show_pre_race_prompt",
        ts=state.tick,
        priority=100.0,
        data={
            'league_name': league.name,
            'track_name': track.name if track else "Unknown",
            'tier': league.tier
        }
    ))
    return events  # Don't continue with tick advance
```

**Add new command handlers:**
- `ftb_pre_race_response` - handles yes/no from prompt
- `ftb_start_live_race` - starts race playback from pbp widget
- `ftb_pause_live_race` - pause/resume race
- `ftb_complete_race_day` - advance tick after race completes

### 2. ftb_pbp.py (Play-by-Play Widget)

**Add to widget:**
- Race control panel (only visible when race is ready)
- "Play Live Race" button
- Speed slider (5s, 10s, 30s, 60s per lap)
- Pause/Resume button
- Live standings table that updates each lap
- Event feed that scrolls as events happen
- Progress bar showing race completion

**New methods:**
```python
def _render_race_control_panel(self):
    """Show play button and speed controls"""
    if not RACE_DAY_STATE or RACE_DAY_STATE.phase != RaceDayPhase.RACE_READY:
        return
    
    # Play button
    # Speed slider
    # Status display

def _update_live_race(self):
    """Called periodically to advance race if playing"""
    if not RACE_DAY_STATE or not RACE_DAY_STATE.live_race_active:
        return
    
    elapsed = time.time() - RACE_DAY_STATE.live_race_last_update
    if elapsed >= RACE_DAY_STATE.live_race_speed:
        # Advance one lap
        # Update standings
        # Show new events
        # Generate commentary
        RACE_DAY_STATE.race_lap_cursor += 1
```

### 3. ftb_audio_engine.py

**Add broadcast mode:**
```python
def start_broadcast_audio(self, tier: int):
    """Start broadcast crew audio with tier-appropriate filtering"""
    from plugins.ftb_race_day import get_broadcast_audio_params
    
    params = get_broadcast_audio_params(tier)
    
    # Duck music
    self.music_controller.duck_for_narrator()
    
    # Set up audio filtering for broadcast
    # - Apply radio filter for grassroots
    # - Clear audio for higher tiers
    
    self.broadcast_active = True

def play_commentary_line(self, text: str, speaker: str, tier: int):
    """Play a single commentary line with appropriate voice"""
    # speaker = 'pbp' or 'color'
    # Choose voice based on speaker
    # Apply tier-based audio filtering
    # Queue for TTS playback
    pass

def end_broadcast_audio(self):
    """End broadcast, restore music"""
    self.broadcast_active = False
    self.music_controller.unduck()
```

### 4. FTB Widget (Main Dashboard)

**Add pre-race prompt dialog:**
```python
def _show_pre_race_prompt(self, league_name: str, track_name: str, tier: int):
    """Show stylized yes/no dialog for race viewing"""
    
    # Create custom dialog (not system dialog)
    dialog = ctk.CTkToplevel(self)
    dialog.title("Race Day Tomorrow")
    dialog.geometry("500x300")
    
    # Styling based on tier
    if tier >= 4:
        bg_color = "#1a1a2e"
        accent = "#FFD700"
    else:
        bg_color = "#2a2a2a"
        accent = "#4CAF50"
    
    dialog.configure(fg_color=bg_color)
    
    # Title
    title = ctk.CTkLabel(
        dialog,
        text=f"🏁 {league_name}",
        font=("Segoe UI", 20, "bold"),
        text_color=accent
    )
    title.pack(pady=20)
    
    # Message
    msg = ctk.CTkLabel(
        dialog,
        text=f"Race tomorrow at {track_name}.\n\nWatch qualifying and live race coverage?",
        font=("Segoe UI", 14),
        text_color="#ffffff"
    )
    msg.pack(pady=10)
    
    # Buttons
    btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
    btn_frame.pack(pady=30)
    
    yes_btn = ctk.CTkButton(
        btn_frame,
        text="Yes - Watch Live",
        command=lambda: self._pre_race_response(True, dialog),
        fg_color=accent,
        hover_color="#555555",
        width=150,
        height=40,
        font=("Segoe UI", 13, "bold")
    )
    yes_btn.pack(side="left", padx=10)
    
    no_btn = ctk.CTkButton(
        btn_frame,
        text="No - Instant Results",
        command=lambda: self._pre_race_response(False, dialog),
        fg_color="#555555",
        hover_color="#666666",
        width=150,
        height=40,
        font=("Segoe UI", 13)
    )
    no_btn.pack(side="left", padx=10)
    
    dialog.transient(self)
    dialog.grab_set()

def _pre_race_response(self, watch_live: bool, dialog):
    """Send response to controller"""
    ftb_cmd_q = self.runtime.get("ftb_cmd_q")
    if ftb_cmd_q:
        ftb_cmd_q.put({
            "cmd": "ftb_pre_race_response",
            "watch_live": watch_live
        })
    dialog.destroy()
```

## FLOW DIAGRAM

```
[Normal Tick] → Check next tick for race
                ↓
                Has player race?
                ↓
        [Show Pre-Race Prompt]
                ↓
        Player chooses Yes/No
                ↓
    ┌───────────┴────────────┐
    │                        │
   YES                      NO
    │                        │
    ↓                        ↓
[Simulate Quali]    [Continue normal tick]
    │                        │
[Show in Event Log]          ↓
    │                   [Instant race sim]
[Don't advance tick]         │
    │                        ↓
    ↓                   [Show results]
[Player goes to PBP tab]
    │
    ↓
[Clicks "Play Live Race"]
    │
    ↓
[Race plays lap-by-lap]
    │
    ├─ Broadcast commentary
    │
    ├─ Live standings update
    │
    ├─ Events scroll by
    │
    └─ Music ducked → Broadcast audio
    │
    ↓
[Race completes]
    │
    ↓
[Tick advances automatically]
    │
    ↓
[Results appear in event log]
```

## AUDIO FLOW

```
[Normal Music Playing]
        ↓
[Pre-race prompt shown]
        ↓
[Player clicks Yes]
        ↓
[Quali simulates - no audio change]
        ↓
[Player clicks Play Live Race]
        ↓
[Music fades to 30% volume]
        ↓
[Broadcast audio starts]
    - Play-by-play voice
    - Color commentary voice
    - Tier-based filtering
        ↓
[Race plays with commentary]
        ↓
[Race ends]
        ↓
[Broadcast audio fades out]
        ↓
[Music fades back to 100%]
        ↓
[Tick advances, results appear]
```

## TESTING CHECKLIST

- [ ] Pre-race prompt appears one tick before race
- [ ] Clicking "No" allows normal tick advance
- [ ] Clicking "Yes" runs quali without tick advance
- [ ] Quali results appear in event log
- [ ] PBP tab shows "Play Live Race" button
- [ ] Speed slider adjusts race playback speed
- [ ] Live standings update each lap
- [ ] Events appear as they happen
- [ ] Broadcast commentary plays during race
- [ ] Audio quality varies by tier (fuzzy in grassroots, clear in Formula Z)
- [ ] Music ducks during broadcast
- [ ] Race can be paused/resumed
- [ ] After race completes, tick advances automatically
- [ ] Race results appear in event log post-tick
- [ ] System works in both manual and auto tick modes
- [ ] System handles AI team races (instant sim, no prompt)

## IMPLEMENTATION PHASES

### Phase 1: Core State Machine (DONE ✓)
- Created ftb_race_day.py
- Created ftb_broadcast_commentary.py

### Phase 2: Integration Points (NEXT)
- Modify tick_simulation() in ftb_game.py
- Add command handlers in FTB Controller
- Add pre-race prompt UI to FTB Widget

### Phase 3: PBP Widget Enhancement
- Add race control panel
- Add live standings display
- Add event feed
- Add speed slider

### Phase 4: Audio System
- Integrate broadcast commentary generator
- Add tier-based audio filtering
- Implement music ducking
- Add TTS for commentary

### Phase 5: Polish & Testing
- Smooth animations
- Progress indicators
- Error handling
- Edge case testing

## VOICE ASSIGNMENTS

**Broadcast Crew:**
- Play-by-play: High energy, lap-by-lap calls (suggest: male voice, energetic tone)
- Color commentary: Analysis, insights (suggest: different voice, calmer)

**Not used during race:**
- Narrator (bm_fable) - silent during broadcast, resumes after

## CONFIGURATION

Add to manifest or settings:
```yaml
race_day:
  default_watch_mode: "ask"  # "ask", "always", "never"
  default_playback_speed: 10  # seconds per lap
  commentary_frequency: "normal"  # "minimal", "normal", "verbose"
  auto_advance_after_race: true  # automatically advance tick after race
```

## NEXT STEPS

1. Implement Phase 2 (integration points)
2. Test pre-race prompt flow
3. Test quali simulation
4. Begin Phase 3 (PBP widget)
