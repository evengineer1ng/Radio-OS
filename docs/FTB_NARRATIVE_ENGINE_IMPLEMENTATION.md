# FTB Narrative Engine Implementation Complete

## What Changed

Transformed FTB from **atomic event narration** (1 event = 1 spoken line) to **editorial storytelling** (many events → composed beats).

### Architecture

**Before:**
```
SimEvent → generate_narration() → {text, voice} → speak directly
```

**After:**
```
SimEvent → EventRouter → BeatBuilder → NarratorBeat/NewsBeat → DB segment → TTS pipeline
```

---

## Files Created

### 1. `plugins/meta/narrative_engine.py` (NEW)

**Core classes:**

- **EventRouter**: Classifies events into tiers
  - `US_CORE`: Direct player team events (race results, DNF, qualifying)
  - `US_CONTEXT`: Constraint changes (financial crisis, ultimatums)
  - `WORLD_SIGNAL`: Formula Z standings, tier changes
  - `NOISE`: AI team events (ignored or batched)

- **BeatBuilder**: Collapses events into narrative moments
  - `_collapse_race_weekend()`: Qualifying + race → 1-2 beats (not 40 events)
  - `_collapse_context()`: Financial updates → digest
  - `_check_formula_z_news()`: Periodic world beat (independent of events)

- **ArcMemory**: Persistent story state
  - Themes, open loops, Formula Z standings memory
  - Stored in `mem["ftb_narrative_state"]`

- **Beat types:**
  - `NarratorBeat`: Jarvis documentary voice (us-first perspective)
  - `NewsBeat`: Formula Z news anchor (world context)

---

## Files Modified

### 2. `plugins/ftb_game.py`

**Added `FTBNarrationHelpers` class:**
- `get_player_team_name(state)`: Returns player team identifier
- `get_team_league(state, team)`: Returns (league_name, tier)
- `get_narration_facts(state, events)`: Builds compact context bundle for LLM
- `_calculate_recent_trend(state)`: Derives "improving|flat|declining" from race history
- `_get_formula_z_standings(state)`: Returns tier 1 championship data

**Modified `FTBController._emit_events()`:**
- Now calls `ACTIVE_META_PLUGIN.ftb_emit_segments()` after emitting StationEvents
- Creates DB connection and passes state snapshot to meta plugin

---

### 3. `plugins/meta/from_the_backmarker.py`

**Added `ftb_emit_segments()` method:**
- Imports `narrative_engine` classes
- Gets narration facts via `FTBNarrationHelpers`
- Classifies events via `EventRouter`
- Builds beats via `BeatBuilder`
- Converts beats to DB segments
- Enqueues segments via `bookmark.db_enqueue_segment()`

**Deprecated `generate_narration()`:**
- Now returns empty list
- Added detailed docstring explaining new flow
- Old method left intact for backward compatibility (unused)

---

## Key Design Decisions

### 1. Event Collapsing Rules (Race Weekend)

**Input:** 40 SimEvents (20 teams × qualifying + race)

**Output:** 2-3 beats
- Our qualifying position
- Our race result (with intent: turning_point/relief/setback)
- Optional: winner announcement (if not us)

**DNF Override:** If player DNFs, suppress all other race beats and narrate the retirement.

### 2. Formula Z News (Persistent)

**Eligibility:**
- Time-based: every 50 ticks
- Event-based: leader change, points gap < 10

**Always runs** even when player is in tier 5 (gives world context).

### 3. Voice Resolution

- `NarratorBeat` → `voices.narrator` (from manifest)
- `NewsBeat` → `voices.formula_z_news` (from manifest)
- Fallback: `"host"` if voices not configured

### 4. Segment Integration

Beats flow through **existing DB pipeline**:
- Same queue as RSS, Reddit, Twitter
- Same rejection filters
- Same music-gating
- Same subtitle generation
- Same TTS rendering

This fixes "spoken JSON" — FTB is now just another content source.

---

## Configuration

### Required Manifest Entries

```yaml
voices:
  narrator: en_GB-alan-medium.onnx
  formula_z_news: en_US-lessac-high.onnx

models:
  narrator: qwen3:8b  # Used for beat generation
```

### Optional Tuning

```yaml
ftb:
  narrative:
    formula_z_news_interval: 50  # Ticks between Formula Z updates
    race_beat_priority: 70.0      # Priority for race beats
    news_beat_priority: 30.0      # Priority for Formula Z news
```

---

## Testing Checklist

### Manual Verification

1. **Start FromTheBackmarker station**
   ```powershell
   cd C:\Users\evana\Documents\radio_os
   radioenv\Scripts\Activate.ps1
   python shell.py
   ```

2. **Create new save** via FTB widget

3. **Tick through first race weekend** (manual step mode)
   - Watch `runtime.log` for:
     ```
     [meta] Processed 40 events → 2 beats
     [meta] Emitted ftb_narration beat: Driver qualified P12
     [meta] Emitted ftb_narration beat: Driver finished P10
     ```

4. **Check audio output:**
   - Should hear: "The team qualified in P12. This was a moment when..."
   - Should NOT hear: "Event race_result driver John position 10 grid 12 points 1"

5. **Advance 50+ ticks:**
   - Should hear periodic Formula Z news: "Formula Z Update: Team Alpha leads championship"

### Log Patterns to Verify

**Success indicators:**
```
[ftb] Narrative beat emission...
[meta] Processed 38 events → 3 beats
[meta] Emitted ftb_narration beat: ...
[tts] Claimed seg source=ftb title=...
[tts] PACKET lens intro=0 summary=145 panel=0 takeaway=0
[host] Playing bundle lines=1 src=ftb type=ftb_narration
```

**Failure indicators:**
```
[meta] Narrative engine not available  # Missing narrative_engine.py import
[meta] ftb_emit_segments error: ...    # Check traceback
[tts] render error: ...                # Packet structure issue
```

### Known Edge Cases

1. **No player team yet:** `ftb_emit_segments()` returns early if `player_team_name` is empty (expected during initial ticks)

2. **First qualifying/race:** May generate beats with incomplete trend data (acceptable — will improve after 2-3 races)

3. **Formula Z standings empty:** `_check_formula_z_news()` returns None (prevents crash)

4. **LLM timeout:** BeatBuilder catches exception and skips beat (won't block simulation)

---

## State Changes

### Arc Memory Structure

Stored in `mem["ftb_narrative_state"]`:
```python
{
  "themes": ["budget crisis", "reliability concerns"],  # Last 20
  "open_loops": ["Will the new engineer help?"],        # Last 10
  "last_formula_z_top3": ["Alpha", "Beta", "Gamma"],
  "last_formula_z_leader": "Alpha",
  "last_formula_z_news_tick": 127,
  "recent_pain_points": ["DNF at Silverstone"],         # Last 5
  "momentum": "improving"  # improving|flat|declining
}
```

### DB Changes

FTB segments now have:
- `source = "ftb"`
- `event_type = "ftb_narration" | "ftb_news"`
- Proper `title`, `body`, `angle`, `priority` fields
- Flow through standard `db_enqueue_segment()` path

---

## Future Enhancements (Not Implemented)

### 1. Multi-Voice Panels

Currently narrator is single-voice. Could add:
- Technical expert for development results
- Analyst for financial updates
- Multiple perspectives per beat

### 2. Arc-Based Intents

Currently intent is derived from event type. Could:
- Track story arcs (redemption, comeback, crisis)
- Choose intent based on arc position
- Generate callback lines referencing past beats

### 3. Player Identity Integration

Currently narrator voice is generic. Could:
- Inject player identity strings into system prompt
- Adjust tone based on identity (scrappy underdog vs. corporate climber)

### 4. Beat Prioritization

Currently priority = event priority. Could:
- Boost priority for milestone moments (first podium, promotion)
- Reduce priority for repetitive beats (10th P15 finish)

### 5. Batch Summary Beats

Currently batch ticks generate summary event. Could:
- Generate a narrative recap beat for 7-day batches
- "A week passed — two races, a development breakthrough, and a tightening budget"

---

## Rollback Plan

If issues arise, revert by:

1. **Restore old `generate_narration()`:**
   ```python
   def generate_narration(self, events, context):
       segments = []
       for event in events:
           narration = self._generate_event_narration(event, context)
           if narration:
               segments.append(narration)
       return segments
   ```

2. **Comment out new pipeline in `FTBController._emit_events()`:**
   ```python
   # ACTIVE_META_PLUGIN.ftb_emit_segments(...)  # DISABLED
   ```

3. **Delete `narrative_engine.py`** (optional)

Old pipeline will resume atomic event narration.

---

## Performance Notes

### Before (Atomic)
- 40 events → 40 LLM calls → 40 spoken lines → ~3 minutes of audio

### After (Beats)
- 40 events → 2-3 beats → 2-3 LLM calls → 3-5 sentences → ~20 seconds of audio

**Win:** 90% reduction in LLM calls and audio time.

---

## Questions Answered

### Q: How do we identify "us"?
**A:** `state.player_team.name` (always single team, no multi-driver support yet)

### Q: Do we have stable league lookup?
**A:** Added `FTBNarrationHelpers.get_team_league(state, team_name)`

### Q: Where are narrator prompts defined?
**A:** In `BeatBuilder._narrator_system_prompt()` — can be externalized to manifest later

### Q: What if LLM fails?
**A:** Beat generation fails gracefully (returns None), simulation continues, segment not emitted

---

## Summary

✅ **Event classification** (EventRouter)  
✅ **Event collapsing** (BeatBuilder race weekend logic)  
✅ **Persistent Formula Z news** (time + standings-based)  
✅ **Jarvis documentary narrator** (us-first, past tense)  
✅ **DB segment emission** (proper pipeline integration)  
✅ **Arc memory** (persistent story state)  
✅ **Helper methods** (FTBNarrationHelpers for facts extraction)  
✅ **Old path deprecated** (generate_narration returns empty)  

**Status:** Implementation complete. Ready for testing.

---

## Next Steps (For User)

1. **Test manually** using checklist above
2. **Review audio quality** — does it sound like documentary narration?
3. **Tune parameters:**
   - Formula Z news interval (currently 50 ticks)
   - Beat priority values
   - Narrator LLM temperature (currently 0.8)
4. **Expand beat types** (optional):
   - Development breakthrough beats
   - Contract negotiation beats
   - Staff morale beats
5. **Add manifest prompts** (optional):
   - Move system prompts from code to manifest YAML
   - Allow per-station narrator personality tuning

---

**Implementation Date:** February 7, 2026  
**Files Changed:** 3 (2 modified, 1 created)  
**Lines Added:** ~900  
**Breaking Changes:** None (old path deprecated but not removed)
