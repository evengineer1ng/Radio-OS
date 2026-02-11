# UI Audio Assets

Tactile, mechanical, NON-MUSICAL feedback sounds.

## Required Sounds

### click.wav
- Generic button press
- Dry, short (50-80ms)
- Mechanical relay click or soft tap

### confirm.wav
- Action confirmation
- Slightly more pronounced than click
- Satisfying "lock-in" sound (80-120ms)

### error.wav
- Invalid action, denied
- Brief buzzer or negative beep
- Should feel corrective, not annoying (100-150ms)

### toggle.wav
- Switch flip, checkbox
- Distinct "on/off" character
- Could be higher pitch than click (60-90ms)

### alert.wav
- Important notification
- Two-tone chime or single bell
- Attention-grabbing but not alarming (150-250ms)

## Design Philosophy

**UI audio should feel:**
- Mechanical (garage equipment, telemetry systems)
- Tactile (physicality, like pressing real buttons)
- Dry (no reverb, very short)
- Low-frequency content minimal (avoid bassiness)

Think:
- Radio tuner clicks
- Toggle switches in cockpit
- Garage bay door latches
- Timing transponder beeps
- Pit radio squelch

**DO NOT:**
- Use musical tones
- Add reverb or delay
- Make sounds longer than 250ms
- Use aggressive EDM-style UI bleeps

## Technical Requirements

- **Format**: WAV (uncompressed, ultra-low latency)
- **Sample Rate**: 44.1 kHz
- **Duration**: 50-250ms maximum
- **Bit Depth**: 16-bit
- **Channels**: Mono
- **Peak Level**: -6dB (quiet, non-intrusive)

## Sources

- UI sound effect packs (Kenney.nl, freesound.org)
- Record actual mechanical switches
- Synthesize simple transients in Audacity
- Racing sim UI sounds (with permission)
- "Mechanical keyboard" sample packs
