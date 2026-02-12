# Kokoro TTS Setup for Radio OS

## What is Kokoro?

Kokoro is a high-quality, multilingual text-to-speech (TTS) system that runs locally using ONNX models. It supports:

- **English** (US & UK accents)
- **French**
- **Italian** 
- **Japanese**
- **Chinese** (Mandarin)
- **Multiple voice types** (male/female, different personalities)

## Available Voices

The Kokoro model includes 60+ voices across different languages and genders:

### English (US)
- **af_** prefix: Female voices (alloy, aoede, bella, heart, jessica, kore, nicole, nova, river, sarah, sky)
- **am_** prefix: Male voices (adam, echo, eric, fenrir, liam, michael, onyx, puck, santa)

### English (UK) 
- **bf_** prefix: Female voices (alice, emma, isabella, lily)
- **bm_** prefix: Male voices (daniel, fable, george, lewis)

### Other Languages
- **ef_/em_**: French voices
- **if_/im_**: Italian voices  
- **jf_/jm_**: Japanese voices
- **zf_/zm_**: Chinese voices
- **pf_/pm_**: Portuguese voices
- **hf_/hm_**: Hindi voices

## Configuration

### Station Manifest (manifest.yaml)
```yaml
audio:
  voices_provider: kokoro
  voices:
    host: af_sarah          # American female, warm voice
    announcer: am_adam      # American male, clear voice  
    narrator: bf_alice      # British female, elegant
    guest: am_echo         # American male, distinctive
```

### Environment Setup
The models are automatically detected from:
- Model: `voices/kokoro/kokoro-v1.0.fp16.onnx`
- Voices: `voices/kokoro/voices-v1.0.bin`

### Manual Paths (optional)
```yaml
audio:
  voices_provider: kokoro
  kokoro_model: /path/to/kokoro-model.onnx
  kokoro_voices: /path/to/voices.bin
```

## Popular Voice Recommendations

- **af_sarah**: Warm, friendly American female - great for hosts
- **af_bella**: Smooth, professional American female - good for news
- **am_adam**: Clear, authoritative American male - perfect for announcers  
- **bf_alice**: Elegant British female - excellent for narratives
- **am_echo**: Distinctive American male - good for character voices

## Model Files

The setup script automatically downloads:
- `kokoro-v1.0.fp16.onnx` (169MB) - FP16 model for Apple Silicon
- `voices-v1.0.bin` (27MB) - Voice embeddings

## Performance

- **Sample Rate**: 24kHz
- **Quality**: High-quality neural synthesis
- **Speed**: Fast inference on Apple Silicon with MPS acceleration
- **Memory**: ~200MB model loading
- **Languages**: Multilingual with excellent accent support

## Testing

Test your setup:
```bash
python test_kokoro.py
```

This will verify model loading and generate sample audio with different voices.