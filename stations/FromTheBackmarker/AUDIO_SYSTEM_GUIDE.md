# FromTheBackmarker Audio System Setup Guide

**Status:** ✅ Implementation Complete

A comprehensive four-channel audio system implementing modal drift music, world audio (engines/crashes), narrator-music integration, and tactile UI feedback for the FromTheBackmarker motorsport simulation station.

---

## System Overview

### Four Audio Pillars

1. **World Audio** — Engines, crashes, ambient motorsport texture
2. **State Music** — Modal drift music system responding to team performance
3. **Narrator Audio** — Voice synthesis with automatic music ducking
4. **UI Audio** — Tactile feedback sounds (clicks, confirms, alerts)

### Key Features

- **Modal Drift Music:** Theme automatically shifts between minor/neutral/major variants based on team performance (morale, reputation, legitimacy, championship position, budget)
- **Performance Scalar:** Smooth interpolation (-1.0 to +1.0) with exponential moving average for "morale inertia"
- **Narrator Ducking:** Music automatically reduces to 30% volume during narration, restores after 1.5s delay
- **Race Audio:** Engine loops change by league tier (grassroots/midformula/formulaz), crash audio with post-impact silence
- **Separation of Concerns:** Engine audio reflects *where* you are (tier), not *how* you're doing (performance comes from music/narrator)

---

## Installation

### 1. Install Dependencies

```powershell
# Activate virtual environment
.\radioenv\Scripts\Activate.ps1

# Install pygame for multi-channel audio
pip install pygame>=2.5.0

# Verify installation
python -c "import pygame; print('pygame version:', pygame.version.ver)"
```

### 2. Audio Assets Structure

```
stations/FromTheBackmarkerTemplate/audio/
├── music/
│   ├── theme_minor.ogg       # Performance < -0.4 (struggling)
│   ├── theme_neutral.ogg     # Performance -0.4 to +0.4 (holding on)
│   └── theme_major.ogg       # Performance > +0.4 (outperforming)
├── world/
│   ├── engines/
│   │   ├── grassroots/       # Karting, club racing (raw, noisy)
│   │   ├── midformula/       # F4, Formula Regional (cleaner, higher RPM)
│   │   └── formulaz/         # Top tier (hyper-clean, aggressive)
│   └── crashes/
│       ├── hard.wav          # Severity > 0.7 (full impact, long reverb)
│       ├── medium.wav        # Severity 0.3-0.7 (brief contact)
│       └── light.wav         # Severity < 0.3 (minor scrape)
└── ui/
    ├── click.wav
    ├── confirm.wav
    ├── error.wav
    ├── toggle.wav
    └── alert.wav
```

### 3. Source Audio Assets

**See README files in each audio subdirectory for:**
- Technical requirements (format, sample rate, duration)
- Design philosophy and guidelines
- Recommended sources (libraries, recordings, synthesis)

**Quick Start Sources:**
- **Music:** Artlist, Epidemic Sound, AudioJungle (search "cinematic theme variations")
- **Engines:** YouTube onboard footage audio, Freesound.org, racing sim communities
- **Crashes:** BOOM Library, Big Room Sound, Freesound.org metal impacts
- **UI:** Kenney.nl, mechanical keyboard samples, synthesized clicks

---

## Configuration

### Manifest Settings

Audio configuration is in `stations/FromTheBackmarkerTemplate/manifest.yaml`:

```yaml
audio:
  piper_bin: voices/piper_windows_amd64/piper/piper.exe
  
  # Channel enable/disable
  music_enabled: true
  world_audio_enabled: true
  ui_audio_enabled: true
  
  # Volume levels (0.0-1.0)
  master_volume: 0.8
  channel_volumes:
    music: 0.6        # State music (modal drift)
    world: 0.5        # Engines, crashes
    ui: 0.15          # Tactile feedback (quiet!)
    narrator: 1.0     # Voice narration
  
  # State music (modal drift) settings
  state_music:
    update_interval: 5.0       # Seconds between performance recalc
    smoothing_alpha: 0.15      # EMA smoothing (lower = smoother)
    crossfade_duration: 6.0    # Seconds to fade between variants
  
  # Performance scalar weights (must sum to 1.0)
  performance_weights:
    morale: 0.25
    reputation: 0.20
    legitimacy: 0.15
    position: 0.25              # Championship standing
    budget: 0.15

feeds:
  ftb_audio_engine:
    enabled: true               # Enable the audio engine plugin
```

### Performance Scalar Formula

```python
scalar = (
    0.25 * normalized_morale +
    0.20 * normalized_reputation +
    0.15 * normalized_legitimacy +
    0.25 * normalized_championship_position +  # Lower position = better = positive
    0.15 * normalized_budget_ratio
)

# Smoothed with exponential moving average (α = 0.15)
smoothed_scalar = α * raw_scalar + (1 - α) * previous_smoothed_scalar

# Maps to music variant:
#   scalar < -0.4  → theme_minor.ogg
#   -0.4 to +0.4   → theme_neutral.ogg
#   scalar > +0.4  → theme_major.ogg
```

---

## Architecture

### Plugin: `plugins/ftb_audio_engine.py`

Main audio engine coordinating all four channels.

**Key Components:**

- `PerformanceScalarCalculator` — Calculates -1.0 to +1.0 scalar from game state
- `StateMusicController` — Modal drift system with crossfade
- `WorldAudioController` — Engine loops, crash audio, post-crash silence
- `UIAudioController` — Preloaded tactile feedback sounds
- `NarratorMusicBridge` — Ducking coordination
- `FTBAudioEngine` — Master coordinator, event router

**Event Subscription:**

Listens to `event_q` for:
- `type='audio'` — Direct audio commands (engine start/stop, crashes, UI sounds)
- `source='ftb', type='narrator_segment'` — Narrator started (duck music)
- `source='ftb', type='state_update'` — Performance state changed (update scalar)

### Integration Points

**Game Simulation (`plugins/ftb_game.py`):**

Emits audio events at key moments:
- **Race start** → `audio_type='world', action='engine_start', league_tier='midformula'`
- **Race end** → `audio_type='world', action='engine_stop'`
- **Crash** → `audio_type='world', action='crash', severity=0.8`
- **Tick end** → `audio_type='performance_update', state_data={morale, position, ...}`

**Runtime (`bookmark.py`):**

- `AudioItem` dataclass extended with file audio fields (`music_track`, `world_audio`, `sfx_files`, etc.)
- `play_file_audio(item)` function plays file-based audio alongside TTS
- pygame.mixer initialized on startup (16 channels, 44.1kHz)
- File audio played after voice TTS in `host_loop`

---

## Usage

### Starting the Station

```powershell
# From repo root with virtualenv activated
python stations\FromTheBackmarkerTemplate\ftb_entrypoint.py
```

**Expected Console Output:**

```
[audio] pygame.mixer initialized for file audio playback
[ftb_audio_engine] Audio engine started
[ftb_audio_engine] Feed worker started, listening for events
```

### During Operation

**Performance changes:**
- Watch morale/position in game UI
- Music will smoothly crossfade between variants over 6 seconds
- Lower position / higher morale → more major/hopeful music

**Race weekends:**
- Engine audio starts on race entry (league-appropriate tier)
- Crashes trigger impact sounds with appropriate severity
- Engine stops at race end

**Narration:**
- Music ducks to 30% volume when narrator speaks
- Restores smoothly 1.5s after narration ends

**UI interactions:**
- Button clicks produce tactile feedback
- Errors produce negative audio cues

### Debugging

**Enable Audio Debug Info:**

Check `stations/FromTheBackmarkerTemplate/runtime.log` for:
```
[ftb_audio_engine] Crossfade start: neutral → major
[ftb_audio_engine] Performance scalar: 0.42 (major)
[ftb_audio_engine] Engine audio: midformula
[ftb_audio_engine] Crash severity: 0.85 (hard)
```

**Common Issues:**

1. **No music playing:**
   - Check audio files exist in `audio/music/` folder
   - Verify files are OGG format, not corrupted
   - Check `music_enabled: true` in manifest

2. **Music not changing:**
   - Verify `ftb_audio_engine` plugin is enabled
   - Check performance metrics are changing (morale, position)
   - Increase `smoothing_alpha` for faster response (less inertia)

3. **Audio too loud/soft:**
   - Adjust `channel_volumes` in manifest
   - Master volume affects all channels equally
   - UI audio should stay quiet (0.10-0.20 range)

4. **Pygame errors:**
   - Reinstall: `pip install --upgrade --force-reinstall pygame`
   - Check audio drivers (Windows: ensure DirectSound available)
   - Try lower buffer size: `buffer=256` in manifest

---

## Audio Design Guidelines

### Music Composition

**Modal Drift Philosophy:**

All three variants should share the same melodic DNA:
- Same tempo, same key (transpose mode, not key)
- Same chord progression root movement
- Vary: scale degrees, third intervals, leading tones, pad brightness

**Example:**
```
Theme in D:
- Minor:   D Aeolian   (D-E-F-G-A-Bb-C)  — flat 3rd, flat 7th
- Neutral: D Dorian    (D-E-F-G-A-B-C)   — flat 3rd, natural 7th
- Major:   D Ionian    (D-E-F#-G-A-B-C#) — natural 3rd, natural 7th
```

### Engine Audio

**Tier Characteristics:**

| Tier | RPM Range | Character | Reference |
|------|-----------|-----------|-----------|
| Grassroots | 8,000-10,000 | Raw, noisy, clipping OK | Karting, Spec Miata |
| Mid-Formula | 10,000-12,000 | Cleaner, higher pitch | F4, Formula Regional |
| Formula Z | 13,000-18,000 | Surgical, hyper-stable | F1, IndyCar |

**Critical Rule:** Engine audio NEVER reflects success/failure. It reflects league tier only.

### Crash Audio

**Severity Mapping:**

- **Time loss < 5s** → Light contact (dry, short)
- **Time loss 5-15s** → Medium impact (reverb tail, 0.5s silence after)
- **Time loss > 15s** → Hard crash (full reverb, 2s silence after)

**Post-Crash Silence is Powerful:** Let the narrator fill the void. Creates tension better than any SFX.

### UI Audio

**Keep it mechanical, NOT musical:**
- Think: garage equipment, telemetry beeps, pit radio clicks
- Avoid: EDM bleeps, notification chimes, musical tones
- Duration: 50-250ms maximum
- Peak level: -6dB (quiet, non-intrusive)

---

## Extending the System

### Adding New Audio Events

**In `ftb_game.py` (or other plugins):**

```python
from your_runtime import event_q, StationEvent

# Emit audio event
event_q.put(StationEvent(
    source="ftb",
    type="audio",
    ts=now_ts(),
    priority=50.0,
    payload={
        'audio_type': 'world',          # 'world', 'music', 'ui', 'narrator_duck'
        'action': 'victory_stinger',    # Custom action
        'file_path': 'audio/victory.wav',  # Optional direct path
        'volume': 0.8,
        'metadata': {'team': 'player'}
    }
))
```

**Handle in `ftb_audio_engine.py`:**

```python
def _handle_audio_event(self, event: AudioEvent) -> None:
    if event.audio_type == 'world':
        action = event.metadata.get('action')
        
        if action == 'victory_stinger':
            # Play victory sound
            file_path = event.file_path or self.audio_dir / 'world' / 'victory.wav'
            if file_path.exists():
                sound = pygame.mixer.Sound(str(file_path))
                channel = pygame.mixer.Channel(4)  # Use dedicated channel
                channel.play(sound)
                channel.set_volume(event.volume)
```

### Adding Real-Time DSP

**For advanced modal drift (beyond crossfade):**

```python
# In StateMusicController._complete_crossfade():

# Real-time filter adjustment
import pygame.sndarray

arr = pygame.sndarray.array(sound)
# Apply filter based on performance_scalar
filtered = apply_lowpass_filter(arr, cutoff_hz=1000 + scalar * 2000)
new_sound = pygame.sndarray.make_sound(filtered)
```

### Custom Performance Weights

Edit `manifest.yaml` to emphasize different metrics:

```yaml
performance_weights:
  morale: 0.40          # Emphasize team spirit
  reputation: 0.30      # PR matters more
  legitimacy: 0.05      # De-emphasize career credibility
  position: 0.20        # Standings less important
  budget: 0.05          # Financial health minimal
```

---

## Technical Reference

### Audio Event Schema

```python
@dataclass
class AudioEvent:
    audio_type: str           # 'world', 'music', 'ui', 'narrator_duck', 'performance_update'
    file_path: Optional[str]  # Direct audio file path (optional)
    volume: float = 1.0       # 0.0-1.0
    fade_in: float = 0.0      # Seconds
    fade_out: float = 0.0     # Seconds
    loop: bool = False        # Loop indefinitely?
    priority: int = 50        # 0-100
    metadata: Dict[str, Any]  # Custom data
```

### Performance State Data

```python
state_data = {
    'morale': 0.65,           # 0.0-1.0
    'reputation': 0.72,       # 0.0-1.0
    'legitimacy': 0.58,       # 0.0-1.0
    'position': 3,            # Championship position (lower = better)
    'max_position': 20,       # Total teams in championship
    'budget': 1500000,        # Current budget
    'budget_baseline': 1000000  # Baseline for comparison
}
```

### Pygame Mixer Channels

Reserved channel assignments:

| Channel | Purpose | Behavior |
|---------|---------|----------|
| 0 | Music (current variant) | Looping, volume-ducked |
| 1 | Music (crossfade target) | Temporary during transition |
| 2 | Engine audio | Looping during races |
| 3 | Crash audio | One-shot, loud |
| 4-7 | SFX / UI audio | One-shot, find_channel() |
| 8-15 | Reserved | Future expansion |

---

## Performance Considerations

**CPU Usage:**
- pygame.mixer runs on separate audio thread (minimal Python overhead)
- Crossfade updates at 20Hz (every 50ms)
- Performance recalc every 5 seconds (configurable)

**Memory:**
- Audio files kept in memory once loaded (pygame.mixer.Sound)
- Preload all UI sounds on startup (~100KB total)
- Music variants loaded on-demand (~5-10MB per track)

**Latency:**
- Voice TTS: sounddevice (low-latency, ~10-20ms)
- File audio: pygame.mixer (higher latency, ~50-100ms acceptable for music/SFX)

**Optimization Tips:**
- Use OGG for music (smaller files)
- Use WAV for SFX/UI (instant decode)
- Keep engine loops < 60 seconds
- Sample rate 44.1kHz (standard, widely supported)

---

## Troubleshooting

### Pygame Won't Initialize

**Error:** `pygame.error: No available audio device`

**Solutions:**
1. Check Windows audio settings (ensure output device enabled)
2. Try different buffer size: `buffer=1024` or `buffer=2048`
3. Reinstall audio drivers
4. Test with: `python -c "import pygame; pygame.mixer.init(); print('OK')"`

### Audio Files Not Playing

**Check:**
1. File path is correct (absolute or relative to station dir)
2. File format supported (OGG, WAV, MP3)
3. File not corrupted (`ffmpeg -i file.ogg` to verify)
4. Pygame initialized successfully (check console for init message)

### Music Not Ducking for Narrator

**Verify:**
1. ftb_audio_engine plugin is enabled and running
2. Narrator events being emitted (check runtime.log)
3. NarratorMusicBridge receiving events
4. Music volume manually controllable (test with manifest change)

### Performance Scalar Not Changing

**Debug:**
1. Print scalar in audio engine worker loop
2. Check morale/position values in game state
3. Verify smoothing_alpha not too low (< 0.05)
4. Ensure state_update events emitted every tick

---

## Future Enhancements

**Potential additions (not currently implemented):**

1. **Ambient Layers:** Garage, paddock, crowd atmosphere
2. **Spatial Audio:** Pan engines left/right based on track position
3. **Dynamic Stems:** Separate music stems (drums, bass, harmony) controlled independently
4. **Voice Processing:** Real-time reverb on narrator for "radio" effect
5. **Adaptive Music:** Tempo changes with race intensity
6. **Music Beds:** Different themes per league tier
7. **Audio Visualization:** Real-time waveform/spectrum in UI

---

## Credits & Licensing

**Audio Engine:** Radio OS Team
**Implementation:** February 2026
**Architecture:** Modal drift music system, multi-channel mixer, performance-driven composition

**Audio Asset Sources:**
- See individual README files in audio/ subdirectories
- Ensure proper licensing for music libraries
- Racing audio may require permission from original sources

---

## Support

**Issues:**
- Check `stations/FromTheBackmarkerTemplate/runtime.log`
- Enable debug logging: set log level in manifest
- Post in Radio OS community / GitHub issues

**Documentation:**
- Main Radio OS guide: `documentation/USER_GUIDE.md`
- FTB narrative system: `FTB_NARRATIVE_ENGINE_IMPLEMENTATION.md`
- Plugin instructions: `.github/copilot-instructions.md`

---

**Implementation Status:** ✅ COMPLETE

All four audio pillars implemented and integrated. Ready for audio asset population.
