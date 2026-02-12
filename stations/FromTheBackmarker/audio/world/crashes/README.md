# Crash / Incident Audio

Use sparingly and with restraint.

## Severity Levels

### Hard Crash (`severity > 0.7`)
**Files:** `hard.wav`, `hard_01.wav`, `hard_02.wav`

- Full transient impact
- Long reverb tail (2-3 seconds)
- Possible tire screech leading in
- Carbon fiber crunch, gravel spray
- **Critical**: 2 seconds of SILENCE after crash before ambient resumes

### Medium Contact (`severity 0.3-0.7`)
**Files:** `medium.wav`, `medium_01.wav`, etc.

- Brief impact
- Shorter reverb (0.5-1 second)
- Wheel-to-wheel contact, minor barrier kiss
- Engine audio dips briefly (0.5s silence)

### Light Touch (`severity < 0.3`)
**Files:** `light.wav`, `light_01.wav`, etc.

- Dry, short, apologetic
- Tire squeal, light scrape
- Almost comically minor
- No silence after

## Technical Requirements

- **Format**: WAV (uncompressed, low latency)
- **Sample Rate**: 44.1 kHz
- **Duration**: 1-5 seconds
- **Bit Depth**: 16-bit minimum
- **Peak Level**: Normalized to -1dB (crashes should be LOUD)

## Design Philosophy

**Silence after major crash is powerful.**

Let the narrator fill the void. The absence of sound creates tension better than any SFX.

## Sources

- Racing game crashes
- Sound effect libraries (Big Room Sound, BOOM Library)
- YouTube crash compilations audio
- Freesound.org metal impacts
