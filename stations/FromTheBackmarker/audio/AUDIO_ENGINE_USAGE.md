# FromTheBackmarker Audio Engine Usage

## Overview

The updated audio engine now supports your new OGG files with intelligent ambient layering and event-driven sounds.

## Audio Channels

### 1. **Music Channel** (Theme System)
- `music/theme_neutral.ogg` - Default mood
- `music/theme_minor.ogg` - Struggling/dramatic mood
- `music/theme_major.ogg` - Triumphant/winning mood
- **Behavior**: Automatically crossfades based on team performance
- **Volume**: Very low background (0.08), ducks to 0.02 during narration

### 2. **Ambient Sounds** (Independent Looping)
These sounds fade in/out on their own schedules, creating layered atmosphere:

- **`world/ambient/garage.ogg`**
  - Mechanical garage ambiance
  - Fades in: 3-8 seconds
  - Plays: 15-45 seconds
  - Fades out: 5-12 seconds
  - Silent: 10-30 seconds
  - Target volume: 30% of ambient channel

- **`world/ambient/toolbox.ogg`**
  - Toolbox/wrench sounds
  - Fades in: 4-10 seconds
  - Plays: 15-45 seconds
  - Fades out: 6-15 seconds
  - Silent: 15-45 seconds
  - Target volume: 25% of ambient channel

- **`world/ambient/distantchatter.ogg`**
  - Distant crowd chatter
  - Fades in: 5-12 seconds
  - Plays: 15-45 seconds
  - Fades out: 8-20 seconds
  - Silent: 5-20 seconds
  - Target volume: 40% of ambient channel

- **`world/ambient/distantpa.ogg`**
  - Distant PA system
  - Fades in: 6-15 seconds
  - Plays: 15-45 seconds
  - Fades out: 10-25 seconds
  - Silent: 20-60 seconds
  - Target volume: 20% of ambient channel

### 3. **Event-Driven World Sounds**

#### Crashes
- `world/crashes/light.ogg` / `light_01.ogg` - Minor incidents
- `world/crashes/medium.ogg` / `medium_01.ogg` - Moderate crashes
- `world/crashes/hard.ogg` / `hard_01.ogg` - Major crashes
- **Behavior**: Plays on crash events, briefly silences engine audio
- **Severity mapping**:
  - 0.0-0.3 → light (no engine pause)
  - 0.3-0.7 → medium (0.5s engine pause)
  - 0.7-1.0 → hard (2.0s engine pause)

#### Crowd Reactions
- `world/ambient/crowdcheer_oneshot.ogg` - Major excitement
- `world/ambient/crowdchatter_oneshot.ogg` - General activity
- `world/ambient/crowdwhoop.ogg` - Quick reaction
- **Trigger examples**: Overtakes, pole position, race wins, incidents

#### Engine Sounds
- `world/engines/formulaz/` - Top tier racing
- `world/engines/midformula/` - Mid-tier racing
- `world/engines/grassroots/` - Entry-level racing
- **Behavior**: Loops continuously during race, changes with league tier

## How to Trigger Audio Events

From any plugin or station code, emit events to the `event_q`:

```python
from your_runtime import event_q, StationEvent

# Play crash sound
event_q.put(StationEvent(
    source='ftb',
    type='audio',
    payload={
        'audio_type': 'world',
        'action': 'crash',
        'severity': 0.8  # 0.0-1.0
    }
))

# Play crowd reaction
event_q.put(StationEvent(
    source='ftb',
    type='audio',
    payload={
        'audio_type': 'world',
        'action': 'crowd_reaction',
        'reaction_type': 'cheer'  # 'cheer', 'chatter', 'whoop'
    }
))

# Start engine audio
event_q.put(StationEvent(
    source='ftb',
    type='audio',
    payload={
        'audio_type': 'world',
        'action': 'engine_start',
        'league_tier': 'midformula'  # 'grassroots', 'midformula', 'formulaz'
    }
))

# Stop engine audio (race ended)
event_q.put(StationEvent(
    source='ftb',
    type='audio',
    payload={
        'audio_type': 'world',
        'action': 'engine_stop'
    }
))

# Update performance scalar (affects music mood)
event_q.put(StationEvent(
    source='ftb',
    type='audio',
    payload={
        'audio_type': 'performance_update',
        'state_data': {
            'morale': 0.7,
            'reputation': 0.6,
            'legitimacy': 0.8,
            'position': 5,
            'max_position': 20,
            'budget': 1500000,
            'budget_baseline': 1000000
        }
    }
))
```

## Configuration

In `stations/FromTheBackmarker/manifest.yaml`, you can customize:

```yaml
audio:
  crossfade_duration: 6.0  # Music crossfade time
  channel_volumes:
    music: 0.08       # Theme music volume
    world: 0.5        # Crashes, engines
    ambient: 0.15     # Garage, toolbox, crowds
    ui: 0.15          # UI feedback
    narrator: 1.0     # Narrator voice
  performance_weights:
    morale: 0.25
    reputation: 0.20
    legitimacy: 0.15
    position: 0.25
    budget: 0.15
```

## Channel Assignment

- **Channel 0**: Main music theme
- **Channel 1**: Crossfade music theme
- **Channel 2**: Engine loops
- **Channel 3**: Crash sounds
- **Channel 4**: Crowd reactions
- **Channels 10-13**: Ambient sounds (garage, toolbox, distantchatter, distantpa)

## Tips

1. **Ambient sounds are automatic** - They start fading in/out as soon as the audio engine starts
2. **Crashes have natural falloff** - Hard crashes silence engines briefly for dramatic effect
3. **Crowd reactions are one-shots** - They don't loop, use them for specific events
4. **Music mood adapts** - The theme automatically shifts based on team performance metrics
5. **All sounds use OGG format** - Efficient and high quality

## Integration Example

```python
# In your race simulation plugin:
def on_incident(incident_type, severity):
    # Play crash sound
    runtime['event_q'].put(StationEvent(
        source='ftb',
        type='audio',
        payload={
            'audio_type': 'world',
            'action': 'crash',
            'severity': severity
        }
    ))
    
    # Maybe trigger crowd reaction too
    if severity > 0.6:
        runtime['event_q'].put(StationEvent(
            source='ftb',
            type='audio',
            payload={
                'audio_type': 'world',
                'action': 'crowd_reaction',
                'reaction_type': 'whoop'
            }
        ))
```
