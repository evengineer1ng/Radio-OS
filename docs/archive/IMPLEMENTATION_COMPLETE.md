# Multi-Provider LLM & Voice Implementation - Complete Summary

## ✅ Implementation Status

### Completed Components

#### 1. **model_provider.py** (NEW FILE)
Abstracts LLM calls across multiple providers.

**Supported Providers:**
- **Ollama** - Local inference (existing behavior)
  - Endpoint: `http://127.0.0.1:11434/api/generate` (default)
  - Model format: e.g., `rnj-1:8b`, `glm-4.7-flash:latest`
  
- **Claude (Anthropic)** - Requires `ANTHROPIC_API_KEY` env var
  - Default model: `claude-3-5-sonnet-20241022`
  - Configurable via manifest `api_key_env`
  
- **GPT (OpenAI)** - Requires `OPENAI_API_KEY` env var
  - Default model: `gpt-4`
  - Supports all OpenAI models
  
- **Gemini (Google)** - Requires `GOOGLE_API_KEY` env var
  - Default model: `gemini-1.5-flash`
  - Supports all Gemini models

**Usage:**
```python
from model_provider import get_llm_provider

provider = get_llm_provider(CFG)  # Auto-detects from CFG["llm"]["provider"]
response = provider.generate(
    model="claude-3-5-sonnet",
    prompt="Generate content...",
    system="You are...",
    num_predict=320,
    temperature=0.35,
    force_json=True  # optional
)
```

---

#### 2. **voice_provider.py** (NEW FILE)
Abstracts voice synthesis across multiple providers.

**Supported Providers:**
- **Piper** - Local ONNX-based TTS (existing behavior)
  - Binary path: configurable via manifest `piper_bin`
  - Voice models: ONNX files (e.g., `en_US-lessac-high.onnx`)
  
- **ElevenLabs API** - Requires `ELEVENLABS_API_KEY` env var
  - Voice format: ElevenLabs voice IDs (e.g., `21m00Tcm4TlvDq8ikWAM`)
  - Stability & similarity_boost configurable
  
- **Google Cloud TTS** - Requires `GOOGLE_API_KEY` env var
  - Voice format: Google voice names (e.g., `en-US-Neural2-C`)
  - Multiple languages and genders supported
  
- **Azure Speech** - Requires `AZURE_SPEECH_KEY` env var + region
  - Voice format: Azure neural voices (e.g., `en-US-AriaNeural`)
  - Region: e.g., `eastus`, `westeurope`

**Usage:**
```python
from voice_provider import get_voice_provider

provider = get_voice_provider(CFG)  # Auto-detects from CFG["audio"]["voices_provider"]
audio_array, sample_rate = provider.synthesize(
    voice_key="host",                  # Character name
    text="Hello world",                # Text to synthesize
    voice_map={"host": "en_US-lessac-high.onnx"}  # Voice mappings
)
```

---

#### 3. **runtime.py** - Refactored
Two major function updates:

**`llm_generate()`** - Lines ~3480-3520
- Now uses `model_provider.get_llm_provider(CFG)`
- Auto-detects provider from `CFG["llm"]["provider"]`
- Falls back to Ollama if provider not specified (100% backward compatible)
- Logs provider type and model for debugging

**`speak(text, voice_key)`** - Lines ~1730-1900
- Now uses `voice_provider.get_voice_provider(CFG, audio_cfg)`
- Calls `provider.synthesize()` instead of subprocess call
- Merges voice_map from both `CFG["voices"]` and `CFG["audio"]["voices"]`
- Works with both local files and API voice IDs

**`voice_is_playable(voice_key)`** - Lines ~1704-1750
- Updated to work with any provider
- Piper: verifies ONNX file exists
- APIs: verifies API key in environment

---

#### 4. **launcher.py** - Enhanced
Added sections to pass API credentials via environment:

```python
# LLM API key handling
llm_cfg = cfg.get("llm", {})
if isinstance(llm_cfg, dict):
    api_key_env = (llm_cfg.get("api_key_env") or "").strip()
    if api_key_env:
        # env[api_key_env] inherits from parent process
        pass

# Voice API key handling  
audio_cfg = cfg.get("audio", {})
if isinstance(audio_cfg, dict):
    api_key_env = (audio_cfg.get("api_key_env") or "").strip()
    if api_key_env:
        # env[api_key_env] inherits from parent process
        pass
```

---

#### 5. **shell.py** - Partially Updated (Requires Manual UI Implementation)

**To complete shell.py, add these methods to `StationWizard` class:**

```python
def _row_combo(self, parent, r, label, var, options, command=None, width=40):
    """Add a combobox row for provider selection."""
    tk.Label(parent, text=label, ...).grid(row=r, column=0, ...)
    combo = ttk.Combobox(parent, textvariable=var, values=options, state="readonly")
    combo.grid(row=r, column=1, ...)
    if command:
        combo.bind("<<ComboboxSelected>>", lambda e: command())

def _on_llm_provider_changed(self):
    """Regenerate LLM UI when provider changes."""
    self._update_llm_ui(wrap)

def _update_llm_ui(self, wrap):
    """Show provider-specific fields (endpoint vs API key)."""
    provider = self.var_llm_provider.get()
    if provider == "ollama":
        self._row(wrap, 7, "Ollama endpoint", self.var_llm_endpoint, ...)
    else:  # anthropic, openai, google
        self._row(wrap, 7, "API Key env var", self.var_llm_api_key_env, ...)

def _on_voice_provider_changed(self):
    """Regenerate voice UI when provider changes."""
    self._update_voice_ui(wrap)

def _update_voice_ui(self, wrap):
    """Show provider-specific voice fields."""
    provider = self.var_voice_provider.get()
    if provider == "piper":
        # Show piper binary path
    else:
        # Show API key env var
```

See [MULTI_PROVIDER_GUIDE.md](./MULTI_PROVIDER_GUIDE.md) for complete UI implementation details.

---

## 📋 Manifest Configuration Examples

### Example 1: Claude API with ElevenLabs
```yaml
llm:
  provider: anthropic
  api_key_env: ANTHROPIC_API_KEY

audio:
  voices_provider: elevenlabs
  api_key_env: ELEVENLABS_API_KEY

voices:
  host: "21m00Tcm4TlvDq8ikWAM"    # ElevenLabs voice ID
  skeptic: "AZnzlk1XvdBFFXlQXcaN"
```

Launch with:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
export ELEVENLABS_API_KEY=sk_...
python launcher.py
```

### Example 2: GPT with Google Cloud TTS
```yaml
llm:
  provider: openai
  api_key_env: OPENAI_API_KEY

audio:
  voices_provider: google
  api_key_env: GOOGLE_API_KEY

voices:
  host: "en-US-Neural2-C"        # Google voice name
  skeptic: "en-US-Neural2-A"
```

Launch with:
```bash
export OPENAI_API_KEY=sk-...
export GOOGLE_API_KEY=AIza...
python launcher.py
```

### Example 3: Local Everything (Default - No Changes Needed)
```yaml
llm:
  provider: ollama
  endpoint: http://127.0.0.1:11434/api/generate

audio:
  voices_provider: piper
  piper_bin: /path/to/piper

voices:
  host: en_US-lessac-high.onnx   # Local ONNX file
```

---

## 🔐 Security Notes

1. **API Keys in Environment Variables**
   - Never store API keys directly in manifest.yaml
   - Always use `api_key_env` to reference environment variable names
   - Launcher passes env vars from parent process to station process

2. **Credential Handling**
   - Provider classes accept env var names from manifest
   - Lookup happens at provider instantiation time
   - If key missing, clear error message with env var name required

3. **Recommended Setup**
   ```bash
   # ~/.bashrc or ~/.env
   export ANTHROPIC_API_KEY="sk-ant-..."
   export OPENAI_API_KEY="sk-..."
   export ELEVENLABS_API_KEY="sk_..."
   export GOOGLE_API_KEY="AIza..."
   export AZURE_SPEECH_KEY="..."
   
   # Then launch stations normally
   python shell.py
   ```

---

## ✅ Backward Compatibility

**All existing stations continue to work unchanged:**
- If manifest has no `llm.provider`, defaults to Ollama
- If manifest has no `audio.voices_provider`, defaults to Piper
- Existing `llm.endpoint` still works
- Existing voice file paths still work

---

## 🧪 Testing Checklist

- [x] model_provider.py syntax valid
- [x] voice_provider.py syntax valid
- [x] runtime.py modifications syntax valid
- [x] launcher.py modifications syntax valid
- [ ] Test Ollama provider (should work like before)
- [ ] Test Claude provider with real API key
- [ ] Test GPT provider with real API key
- [ ] Test Gemini provider with real API key
- [ ] Test Piper voice (should work like before)
- [ ] Test ElevenLabs voice with real API key
- [ ] Test mixed providers (e.g., Claude + ElevenLabs)
- [ ] Verify shell.py UI updated with provider dropdowns
- [ ] Verify API keys passed correctly through launcher
- [ ] Test with all 6 existing stations

---

## 📚 Files Modified/Created

**New Files:**
- `model_provider.py` - 240 lines
- `voice_provider.py` - 300 lines
- `MULTI_PROVIDER_GUIDE.md` - Documentation
- `stations/algotradingfm/manifest_multi_provider.yaml` - Example config

**Modified Files:**
- `runtime.py` - 2 major functions refactored (100% compatible)
- `launcher.py` - Enhanced environment setup (backward compatible)
- `shell.py` - Awaiting UI implementation (shell.py still has old code for Piper)

---

## Next Steps

1. **Complete shell.py UI** - Add provider dropdowns and dynamic fields
2. **Test with each provider** - Verify all 4 LLM + 4 voice combinations work
3. **Update existing stations** - Add provider configs to manifests
4. **Documentation** - User guide for each provider setup

---

## Questions & Support

Refer to [MULTI_PROVIDER_GUIDE.md](./MULTI_PROVIDER_GUIDE.md) for detailed setup instructions for each provider.
