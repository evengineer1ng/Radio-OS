# Multi-Provider LLM & Voice Implementation Guide

## Files Created

### 1. `model_provider.py`
Provides abstraction layer for LLM providers:
- `OllamaProvider` - Local Ollama/vLLM endpoints  
- `AnthropicProvider` - Claude API
- `OpenAIProvider` - GPT API
- `GoogleProvider` - Gemini API
- `get_llm_provider(cfg)` - Factory function

### 2. `voice_provider.py`
Provides abstraction layer for voice/TTS providers:
- `PiperProvider` - Local Piper TTS
- `ElevenLabsProvider` - ElevenLabs API
- `GoogleCloudTTSProvider` - Google Cloud Speech
- `AzureSpeechProvider` - Azure Speech Services
- `get_voice_provider(cfg)` - Factory function

## Changes to Existing Files

### `runtime.py`
1. **llm_generate()** - Refactored to use `model_provider.get_llm_provider()`
   - Auto-detects provider from `CFG["llm"]["provider"]`
   - Falls back to Ollama if not specified (backward compatible)

2. **speak()** - Refactored TTS to use `voice_provider.get_voice_provider()`
   - Calls provider's `synthesize()` method
   - Supports both local and API-based voices

3. **voice_is_playable()** - Updated to check provider availability
   - For Piper: verifies file exists
   - For APIs: verifies API key exists

### `launcher.py`
- Enhanced environment setup to pass API credentials
- API keys flow from parent environment to station process
- Manifest's `api_key_env` fields point to environment variable names

### `shell.py` (StationWizard)
- Added `var_llm_provider` dropdown for provider selection (ollama/anthropic/openai/google)
- Added `_row_combo()` helper for dropdown creation
- Added `_on_llm_provider_changed()` to dynamically update UI
- Added `_update_llm_ui()` to show provider-specific fields
- Similar enhancements for voice tab with voice provider selection

## Manifest Extension

### New LLM Config Structure
```yaml
llm:
  provider: "ollama"  # or "anthropic", "openai", "google"
  endpoint: "http://127.0.0.1:11434/api/generate"  # local only
  api_key_env: "ANTHROPIC_API_KEY"  # env var name for API key
  model: "claude-3-5-sonnet-20241022"  # optional model override
```

### New Audio/Voice Config Structure
```yaml
audio:
  voices_provider: "piper"  # or "elevenlabs", "google", "azure"
  piper_bin: "/path/to/piper"  # local only
  api_key_env: "ELEVENLABS_API_KEY"  # env var name
  region: "eastus"  # Azure only
```

## Usage Examples

### Claude API
```bash
export ANTHROPIC_API_KEY=sk-ant-...
# Manifest:
# llm:
#   provider: anthropic
#   api_key_env: ANTHROPIC_API_KEY
```

### GPT API
```bash
export OPENAI_API_KEY=sk-...
# Manifest:
# llm:
#   provider: openai
#   api_key_env: OPENAI_API_KEY
```

### ElevenLabs Voice
```bash
export ELEVENLABS_API_KEY=sk_...
# Manifest:
# audio:
#   voices_provider: elevenlabs
#   api_key_env: ELEVENLABS_API_KEY
# voices:
#   host: 21m00Tcm4TlvDq8ikWAM  # ElevenLabs voice ID
```

## Backward Compatibility

✅ **Fully backward compatible**
- Existing Ollama-based configs work unchanged
- If `provider` not specified, defaults to "ollama"
- If `voices_provider` not specified, defaults to "piper"
- All existing manifest.yaml files will continue to work

## Environment Variables

**LLM Providers**
- `ANTHROPIC_API_KEY` → Claude
- `OPENAI_API_KEY` → GPT
- `GOOGLE_API_KEY` → Gemini

**Voice Providers**
- `ELEVENLABS_API_KEY` → ElevenLabs
- `GOOGLE_API_KEY` → Google Cloud TTS
- `AZURE_SPEECH_KEY` → Azure Speech

## Testing Checklist

- [ ] Ollama still works (default)
- [ ] Claude API works
- [ ] GPT API works
- [ ] Gemini API works
- [ ] Piper local voice still works
- [ ] Mixed providers work (e.g., Claude LLM + Piper voice)
- [ ] Shell wizard allows provider selection
- [ ] API keys via environment variables
- [ ] Launcher passes credentials correctly
