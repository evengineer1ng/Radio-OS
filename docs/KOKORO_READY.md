🎉 **Kokoro TTS is now integrated and working!** 

## Quick Start

### 📋 Prerequisites
1. **Download Kokoro models** (not included in repo due to size):
   - Download `kokoro-v1.0.fp16.onnx` (169MB) and `voices-v1.0.bin` (18MB) 
   - From: https://github.com/thewh1teagle/kokoro-onnx/releases/tag/v1.0
   - Place in: `voices/kokoro/` directory

### ✅ What's Already Done
- KokoroProvider implemented in `voice_provider.py`
- Runtime integration complete
- UI support already existed

### 🚀 How to Use

1. **In Station Manifest** (e.g., `manifest.yaml`):
```yaml
audio:
  voices_provider: kokoro
  voices:
    host: af_sarah       # Warm American female
    announcer: am_adam   # Clear American male
    news: af_bella       # Professional female
    weather: am_liam     # Friendly male
```

2. **Available Voices** (60+ voices total):

**English US Female**: af_alloy, af_aoede, af_bella, af_heart, af_jessica, af_kore, af_nicole, af_nova, af_river, af_sarah, af_sky

**English US Male**: am_adam, am_echo, am_eric, am_fenrir, am_liam, am_michael, am_onyx, am_puck, am_santa

**English UK**: bf_alice, bf_emma, bf_isabella, bf_lily, bm_daniel, bm_fable, bm_george, bm_lewis

**Other Languages**: French (ef_/em_), Italian (if_/im_), Japanese (jf_/jm_), Chinese (zf_/zm_), Portuguese (pf_/pm_), Hindi (hf_/hm_)

3. **Test It**:
```bash
cd /Users/even/Documents/Radio-OS-1.03
source radioenv/bin/activate
python test_kokoro.py  # Verify setup
```

### 🎯 Recommended Voices
- **af_sarah**: Perfect main host voice (warm, friendly)  
- **am_adam**: Great announcer voice (clear, authoritative)
- **af_bella**: Excellent for news (professional, smooth)
- **bf_alice**: Beautiful narrator voice (British, elegant)
- **am_echo**: Distinctive character voice

### 💡 Tips
- Kokoro runs locally (no API keys needed)
- High quality 24kHz output
- Fast inference on Apple Silicon
- Multilingual support
- Voice names are case-sensitive (e.g., "af_sarah" not "AF_SARAH")

### 📚 Documentation
- Full setup guide: `documentation/KOKORO_SETUP.md`
- Example manifest: `examples/kokoro_demo_manifest.yaml`

You're all set to use Kokoro TTS in any Radio OS station! 🎙️