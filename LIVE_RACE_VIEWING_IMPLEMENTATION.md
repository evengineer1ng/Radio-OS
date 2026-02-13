# Live Race Viewing Implementation

## Overview
Added a feature that prompts the player to watch races unfold live in the play-by-play widget, with events streaming lap-by-lap instead of all appearing instantly.

## Flow

### 1. Pre-Tick Check (Manual Ticks Only)
- When user clicks "Advance Tick" (single tick only, not batch)
- **Before** simulation runs, check if player has a race on this tick
- If yes and not in delegate mode → show dialog

### 2. Dialog Display
- **Blocking** tkinter messagebox appears:
  ```
  🏁 Race Day - Round X
  [League Name]
  [Track Name]
  
  Would you like to watch the race unfold live in play-by-play?
  [Yes] [No]
  ```
- User chooses YES or NO
- Choice stored in `state._watch_current_race_live` flag

### 3. Race Simulation
- Race simulates completely (all laps computed at once)
- If user chose **YES**:
  - Events stored in `state._live_pbp_events`
  - `state._live_pbp_mode = True`
  - Events NOT added to main events list yet
  - `ftb_pbp.start_live_feed()` called to initialize widget
- If user chose **NO**:
  - Events added immediately (instant race)
  - Normal behavior

### 4. Live Event Streaming (If YES)
- Controller's main loop detects `_live_pbp_mode` flag
- `_stream_live_race_event()` called repeatedly:
  - Checks if enough time has passed (2 seconds per event)
  - Streams one event at a time to narrator/DB
  - Updates cursor position
  - Returns True if more events remain
- `ftb_pbp` widget displays events as they arrive
- Position changes, overtakes, crashes unfold in real-time

### 5. Finalization
- When all events streamed (`cursor >= len(events)`):
  - `_finalize_live_race()` called
  - Clears `_live_pbp_mode` flag
  - Emits race_end audio event
  - Updates UI
  - Tick completes

## Key Files Modified

### `plugins/ftb_game.py`

1. **SimState** (line ~3332):
   - Added `_watch_current_race_live` flag

2. **tick_simulation()** (line ~7615):
   - Checks for `_watch_current_race_live` flag
   - Routes to live mode or instant mode based on flag

3. **FTBController** methods:
   - `_check_for_upcoming_player_race()` - detects player races on tick
   - `_show_watch_race_dialog()` - blocking dialog with yes/no
   - `_stream_live_race_event()` - streams one event per interval
   - `_finalize_live_race()` - cleanup after streaming complete

4. **ftb_tick_step command handler** (line ~27695):
   - Pre-tick check added before simulation
   - Shows dialog if player race detected

5. **Main loop** (line ~27540):
   - Checks for `_live_pbp_mode` flag
   - Calls streaming function when active

### `plugins/ftb_pbp.py`
- Already had `start_live_feed()` function
- Already had `_advance_live_feed()` function
- Widget already updates automatically
- No changes needed!

## Technical Details

### Timing
- Events stream at **2.0 second intervals** (configurable)
- For a 50-event race: ~100 seconds total (1.5 minutes)
- User can watch entire race unfold

### Thread Safety
- Dialog blocks the command handler thread (safe)
- Flag checked before simulation (no race condition)
- Events streamed from main loop (no conflicts)

### Edge Cases Handled
- ✅ Delegate mode: no prompt (races run instantly)
- ✅ Batch ticks: no prompt (races run instantly)
- ✅ Auto mode: no prompt (races run instantly)
- ✅ Only prompts for **player's league** races
- ✅ Dialog failure: defaults to instant race (safe fallback)
- ✅ Flag cleared after use (won't affect next race)

## Testing Checklist

- [ ] Single tick with player race → dialog appears
- [ ] Click YES → race unfolds in ftb_pbp over ~90 seconds
- [ ] Click NO → race runs instantly as before
- [ ] Batch tick (7 days) → no dialog, instant races
- [ ] Delegate mode → no dialog, instant races
- [ ] Race in racing stats after completion
- [ ] ftb_pbp shows live positions/events during stream
- [ ] Can watch multiple races in a row

## Future Enhancements

1. **Speed control**: Let user choose interval (1s, 2s, 5s)
2. **Skip button**: Allow interrupting live view mid-race
3. **Replay mode**: Re-watch previous races
4. **Camera focus**: Auto-scroll to player's car in pbp
5. **Audio commentary**: Trigger specific audio cues during live events
6. **Highlight mode**: Only show key moments (overtakes, crashes, podium)
