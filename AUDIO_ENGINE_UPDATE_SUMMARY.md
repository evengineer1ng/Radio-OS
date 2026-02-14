# Audio Engine Update Summary

## Changes Made

### New Features Added

#### 1. **AmbientAudioManager Class**
- Manages 4 independent ambient sounds that loop and fade on their own schedules
- Each sound has its own fade-in/out timing, play duration, and silence periods
- Creates a layered, organic atmosphere that evolves naturally
- Sounds included:
  - `garage.ogg` - Mechanical garage ambiance
  - `toolbox.ogg` - Tool/wrench sounds
  - `distantchatter.ogg` - Crowd background
  - `distantpa.ogg` - Public address system

#### 2. **Enhanced Crash System**
- Updated to prioritize `.ogg` format (your new files)
- Fallback to `.wav` if OGG not found
- Randomly selects from multiple variants (`light.ogg`, `light_01.ogg`, etc.)
- More graceful mixing with engine fade-outs

#### 3. **Crowd Reaction System**
- New `play_crowd_reaction()` method
- Supports three types:
  - `'cheer'` - Major excitement (crowdcheer_oneshot.ogg)
  - `'chatter'` - General activity (crowdchatter_oneshot.ogg)
  - `'whoop'` - Quick reaction (crowdwhoop.ogg)
- Integrated into event system for race simulation triggers

#### 4. **Improved Channel Management**
- Increased from 8 to 16 audio channels
- Channels 10-13 reserved for ambient sounds
- Channel 4 added for crowd reactions
- Better isolation prevents audio conflicts

### Technical Improvements

1. **Delta Time Propagation**
   - `WorldAudioController.update()` now receives `dt` parameter
   - Enables smooth fade calculations in ambient manager

2. **OGG Format Priority**
   - All file lookups now check `.ogg` first
   - Maintains backward compatibility with `.wav`

3. **Independent Timing**
   - Each ambient sound has its own state machine
   - Staggered start times prevent synchronized fades
   - Random duration ranges create organic variation

4. **Event System Extension**
   - Added `crowd_reaction` action type
   - Maintains existing crash, engine, and performance events

## File Structure

```
stations/FromTheBackmarker/audio/
├── music/
│   ├── theme_neutral.ogg    ← Music theme (default mood)
│   ├── theme_minor.ogg      ← Music theme (struggle/drama)
│   └── theme_major.ogg      ← Music theme (triumph)
├── world/
│   ├── ambient/
│   │   ├── garage.ogg              ← Ambient loop (independent)
│   │   ├── toolbox.ogg             ← Ambient loop (independent)
│   │   ├── distantchatter.ogg      ← Ambient loop (independent)
│   │   ├── distantpa.ogg           ← Ambient loop (independent)
│   │   ├── crowdcheer_oneshot.ogg  ← Event-driven (race excitement)
│   │   ├── crowdchatter_oneshot.ogg← Event-driven (general activity)
│   │   └── crowdwhoop.ogg          ← Event-driven (quick reaction)
│   ├── crashes/
│   │   ├── light.ogg / light_01.ogg       ← Event-driven
│   │   ├── medium.ogg / medium_01.ogg     ← Event-driven
│   │   └── hard.ogg / hard_01.ogg         ← Event-driven
│   └── engines/
│       ├── formulaz/      ← High-tier racing
│       ├── midformula/    ← Mid-tier racing
│       └── grassroots/    ← Entry-level racing
└── ui/
    └── [UI feedback sounds]
```

## Audio Behavior

### Ambient Sounds (Automatic, Independent)
- **Start**: Fade in over 3-15 seconds (varies per sound)
- **Play**: Continue for 15-45 seconds at target volume
- **Fade Out**: Gradually reduce over 5-25 seconds
- **Silent**: Pause for 5-60 seconds before next cycle
- **Result**: Layered, organic atmosphere that never feels repetitive

### Event Sounds (Triggered by Simulation)
- **Crashes**: Play on incident, briefly silence engines
- **Crowd**: Play on exciting moments (overtakes, wins, incidents)
- **Engines**: Loop continuously during race, change with league tier

### Music (Mood-Based)
- Automatically crossfades between variants based on team performance
- Ducks (reduces volume) during narrator speech
- Always present as subtle background

## Integration Points

The race simulation and other plugins can trigger audio by emitting events:

```python
# Example: Trigger audio on race incident
event_q.put(StationEvent(
    source='ftb',
    type='audio',
    payload={
        'audio_type': 'world',
        'action': 'crash',
        'severity': 0.75
    }
))

# Example: Crowd reacts to exciting overtake
event_q.put(StationEvent(
    source='ftb',
    type='audio',
    payload={
        'audio_type': 'world',
        'action': 'crowd_reaction',
        'reaction_type': 'cheer'
    }
))
```

## Configuration

Default volumes in manifest.yaml:
- **music**: 0.08 (very subtle background)
- **world**: 0.5 (engines, crashes)
- **ambient**: 0.15 (garage, toolbox, crowds)
- **ui**: 0.15 (tactile feedback)

Ambient sounds are scaled further:
- garage: 30% of ambient channel
- toolbox: 25% of ambient channel
- distantchatter: 40% of ambient channel
- distantpa: 20% of ambient channel

## Next Steps

1. **Test the ambient fading** - Start the station and listen for garage/toolbox sounds fading in/out
2. **Trigger race events** - Simulate crashes and overtakes to hear dynamic audio responses
3. **Adjust timing** - If ambient sounds feel too frequent or sparse, tune the duration ranges in `AmbientAudioManager.__init__`
4. **Add more variants** - Drop more OGG files in the audio folders, engine will pick randomly

## Backward Compatibility

✅ Existing audio trigger code continues to work
✅ Falls back to WAV if OGG files missing
✅ Manifest settings use existing structure
✅ No breaking changes to event system
