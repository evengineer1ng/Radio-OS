# Flows Plugin Integration with experiment.py - COMPLETE ✅

## Summary
The flows plugin now properly integrates with experiment.py's host system to gracefully interrupt speech when music resumes and allow hosts to throw to music before it starts playing.

## Changes Made

### 1. Event Payload Field Names Fixed
**Problem**: Flows was using `"hint"` in event payloads, but experiment.py expects `"host_hint"`

**Solution**: Updated all three event types to use correct field names:
- `flow_intro` events → Now includes `"host_hint": "Brief, smooth music transition. Keep it flowing."`
- `music_incoming` events → Now includes `"host_hint": "High energy throw to music. Brief transition, then let it play."`
- `flow_reaction` events → Now includes `"host_hint": "Optional. Only comment if you have something genuine to say about this track."`

### 2. Enhanced Event Metadata
Added proper `title`, `body`, `angle`, and `why` fields to all events so the producer can better understand context:

```python
# Music Incoming Event (before flow completes)
{
    "type": "music_incoming",
    "title": "Music Flow Resuming",
    "body": "Completed {flow_count} track talk break, music is about to resume.",
    "angle": "Throw back to the music with energy.",
    "why": "Talk break ending, time to return to the flow.",
    "host_hint": "High energy throw to music. Brief transition, then let it play."
}
```

### 3. SHOW_INTERRUPT Already Working
The flows plugin was already correctly using `SHOW_INTERRUPT`:
- Retrieved from `runtime.get("SHOW_INTERRUPT")` at plugin startup ✅
- Sets interrupt when music resumes: `SHOW_INTERRUPT.set()` → gracefully cuts host speech ✅
- Clears after brief delay: `SHOW_INTERRUPT.clear()` ✅

## How It Works

### Flow Sequence

1. **Music Playing** → Flows plugin counts tracks in current flow
   
2. **Flow Target Reached** (e.g., 3 songs completed)
   - Plugin sends `music_incoming` event with `host_hint: "throw to music"`
   - Producer receives event and generates short transition segment
   - Gives host 2.5 seconds to start speaking the throw
   
3. **Music Resumes** (user unpauses or system resumes)
   - Plugin detects: `playing and not last_playing`
   - Sets `SHOW_INTERRUPT.set()` 
   - Speech synthesis checks SHOW_INTERRUPT and gracefully stops
   - Music continues uninterrupted

4. **Flow Resets** → Cycle starts again

### Graceful Speech Interruption

The experiment.py `speak()` function has multiple SHOW_INTERRUPT checkpoints:
- **Pre-synthesis** (line 1882): Aborts before generating audio
- **Pre-playback** (line 1975): Aborts after synthesis but before playing
- **During playback** (line 2036): Stops streaming mid-sentence
- **Music detection** (lines 2044-2050): Also stops if music resumes

### Host Awareness

Hosts receive the `host_hint` field in their prompt (experiment.py line 5475):
```
opening_hint: {seg.get("host_hint","")}
```

So when music is about to resume, the host sees:
```
opening_hint: High energy throw to music. Brief transition, then let it play.
```

And generates appropriate transitions like:
- "Alright, let's get back to it!"
- "Here we go—"
- "Music time!"

## Testing Checklist

- [x] Event payloads use `host_hint` (not `hint`)
- [x] SHOW_INTERRUPT properly exposed in runtime dict
- [x] Flow plugin gets SHOW_INTERRUPT from runtime
- [x] Music resume detection sets SHOW_INTERRUPT
- [x] Speak() function checks SHOW_INTERRUPT at multiple points
- [x] "music_incoming" events sent before flow completes
- [x] Producer receives and processes host_hint correctly
- [x] Flow events include proper title/angle/why metadata

## Manual Testing

1. Start a station with flows plugin enabled
2. Let 3+ songs play (flow completes)
3. Observe: Host should throw to music ("Let's get back to the music!")
4. Unpause music while host is still speaking
5. Observe: Host speech should cut gracefully mid-sentence
6. Music continues playing without interruption

## Files Modified

- `plugins/flows.py` - Fixed event payload fields, added metadata

## Architecture Notes

- **No circular dependencies**: flows plugin → event_q → producer → TTS → SHOW_INTERRUPT → flows detects
- **Event-driven**: No direct music control from flows—just state detection and event emission
- **Fail-safe**: If music doesn't resume, host finishes speaking naturally (graceful degradation)
- **Producer-authoritative**: All music/talk decisions respect mix.weights and producer logic

## Status: COMPLETE ✅

The flows plugin now properly interacts with experiment.py:
1. ✅ Gracefully silences host speech when music resumes
2. ✅ Hosts know music is coming and can throw to it appropriately
