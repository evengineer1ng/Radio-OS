# Manual Test Instructions for Live Race Viewing

## Setup
1. Start Radio OS with FTB station
2. Load a save or start new game
3. Advance time until just before a race

## Test 1: Watch Race Live (YES)
1. Click "Advance Tick" (single tick, not batch)
2. Dialog should appear: "Would you like to watch the race unfold live?"
3. Click **YES**
4. Expected behavior:
   - ftb_pbp widget should activate
   - Race events appear one at a time every 2 seconds
   - Can watch positions change, overtakes, crashes in real-time
   - Entire race takes ~90-120 seconds to unfold
   - At end, tick completes and racing stats are updated

## Test 2: Skip Live View (NO)
1. Click "Advance Tick"
2. Dialog appears
3. Click **NO**
4. Expected behavior:
   - Race runs instantly (< 1 second)
   - All events appear at once
   - Racing stats update immediately
   - No live viewing, just like before

## Test 3: Batch Advance (No Dialog)
1. Click "Advance 7 Days" or any batch advance
2. Expected behavior:
   - NO dialog appears
   - All races run instantly
   - Normal batch behavior (no live viewing for batches)

## Test 4: Delegate Mode (No Dialog)
1. Enable delegate mode
2. Let auto-tick run through a race day
3. Expected behavior:
   - NO dialog appears
   - Race runs instantly in background
   - Delegate mode continues uninterrupted

## Verification Points

### Check ftb_pbp Widget
- Open ftb_pbp widget during live race
- Should see:
  - "🔴 Live Race" indicator
  - Positions updating lap by lap
  - Events appearing in timeline
  - Race statistics building up

### Check Racing Stats Tab
- After ANY race (live or instant):
  - Race should appear in history
  - Stats should be updated
  - Can view race results

### Check Console Logs
Look for these key messages:

```
[FTB DIALOG] 🏁 Showing watch race dialog for [Track Name]
[FTB DIALOG] User responded: YES (watch live)
[FTB] 🎥 Live race mode activated - will stream X events
[FTB] 📺 ftb_pbp live feed started
[FTB LIVE RACE] 📡 Streaming event 1/50: qualifying_result
[FTB LIVE RACE] 📡 Streaming event 2/50: overtake
...
[FTB LIVE RACE] 🏁 Finalizing live race mode
[FTB LIVE RACE] ✅ Live race finalized, returning to normal flow
```

## Debugging

### Dialog doesn't appear?
- Check: Are you in delegate mode? (should be "human")
- Check: Is this a single tick or batch? (only works for single)
- Check: Is this your player's league race? (won't trigger for AI-only races)
- Check console for: `[FTB CONTROLLER] 🏁 Dialog shown, user chose: ...`

### Race doesn't appear in stats?
- Check: Did the race actually complete?
- Check: Are you looking at the right league/tier?
- Look for: `[FTB] RACE_COMPLETE: [League Name] Round X - Y events generated`

### Live view not working?
- Check ftb_pbp console logs
- Look for: `[FTB] 📺 ftb_pbp live feed started`
- Check: `[FTB LIVE RACE] 📡 Streaming event X/Y: ...`
- Verify events are being streamed at 2-second intervals

### Race runs instantly even when clicking YES?
- Check the flag is being set: `_watch_current_race_live = True`
- Check streaming loop is active: `if self._stream_live_race_event()`
- Verify `_live_pbp_mode` flag is True during race

## Quick Debug Checklist
- [ ] Dialog appears when expected
- [ ] YES choice triggers live mode
- [ ] NO choice triggers instant mode
- [ ] Live events stream at correct intervals
- [ ] ftb_pbp widget updates during streaming
- [ ] Race appears in stats after completion
- [ ] Batch advances skip dialog
- [ ] Delegate mode skips dialog
