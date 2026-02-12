# Radio OS

A desktop-first, content-agnostic AI radio runtime with a modular plugin architecture. Build custom AI radio stations that pull from feeds, generate commentary, and stream audio with natural TTS voices.

## Features

- **Modular Plugin System**: Extensible feed plugins (RSS, Reddit, Bluesky, Markets, etc.)
- **AI-Driven Production**: Producer and host agents curate and comment on content
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **Live Music Integration**: Detects and pauses for your local music player
- **Real-time UI**: Desktop shell with widgets for station control
- **Custom Voices**: Multiple TTS voices via Piper
- **SQLite Memory**: Persistent station memory and content tracking

## Architecture

```
shell.py          # Desktop UI and process manager
runtime.py        # Station engine (feeds, events, audio, routing)
launcher.py       # Station process launcher with environment setup
plugins/          # Feed plugins and UI widgets
stations/         # Per-station configs and entrypoints
voices/           # TTS voice models (ONNX)
```

## Quick Start

### System Requirements

- **Operating System**: Windows 10/11, macOS 11+, or Linux (Ubuntu 20.04+)
- **Python**: 3.10 or newer
- **RAM**: 4GB minimum, 8GB recommended (16GB for ML features)
- **Disk Space**: 15GB for full setup
  - Base dependencies: ~400MB
  - Ollama + AI models: ~8-12GB (optional)
  - Piper + voice models: ~200-400MB (optional)
  - PyTorch ML: ~2GB (optional)
- **GPU**: Recommended for Ollama (works on CPU but slower)

### One-Command Setup (Recommended)

Radio OS includes an automated first-time setup that handles everything:

**Windows:**
```bash
windows.bat
```

**macOS/Linux:**
```bash
chmod +x mac.sh
./mac.sh
```

The setup wizard will:
1. ✅ Install Python dependencies
2. 💬 Prompt to install Ollama + AI models (~8-12GB, 10-30 min)
3. 🗣️ Prompt to install Piper TTS + voices (~200-400MB, 5-10 min)
4. 🧠 Prompt to install PyTorch for ML (~2GB, 5-15 min)
5. 🚀 Launch Radio OS Shell

**First-time setup takes 15-45 minutes** depending on your internet speed.

On subsequent runs, `windows.bat` or `mac.sh` will launch directly without prompts.

### Stations Included

Radio OS ships with these ready-to-use stations:

- **BasketballFM** - Basketball news and commentary
- **HockeyFM** - Hockey coverage and analysis
- **popcultureFM** - Pop culture trends and entertainment
- **SimRacingFM** - Sim racing community and esports
- **VibezFM** - Music, culture, and lifestyle
- **FlowFM** - Hip-hop focus with DJ commentary
- **FromTheBackmarker** - Formula racing management sim with ML
- **WelcomeFM** - Intro station to get started

All stations work out-of-the-box after automated setup completes.

### Manual Installation

If you prefer manual setup or encounter issues:

1. Clone the repository:
```bash
git clone https://github.com/evengineer1ng/radio-os.git
cd radio-os
```

2. Create and activate virtual environment:
```bash
python -m venv radioenv
# Windows:
radioenv\Scripts\activate
# macOS/Linux:
source radioenv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install Ollama (optional but recommended):
   - Download from [ollama.ai/download](https://ollama.ai/download)
   - Pull models: `ollama pull qwen3:8b`, `ollama pull llama3.1:8b`, etc.

5. Download Piper TTS (optional but recommended):
```bash
python setup.py
```

6. Configure station manifests:
```bash
python tools/inject_manifest_paths.py --piper-bin /path/to/piper --voices-dir ./voices
```

7. Launch:
```bash
python shell_bookmark.py
```

## Creating a Station

Use the built-in wizard in the shell UI, or manually create a station directory:

```
stations/mystation/
  ├── manifest.yaml    # Station configuration
  └── mystation.py     # Optional custom entrypoint
```

See [templates/default_manifest.yaml](templates/default_manifest.yaml) for configuration options.

## Configuration

### Station Logos

Station logos are referenced in `manifest.yaml` via the `station.logo` field:

```yaml
station:
  name: MyStation
  logo: logos/mystation.png  # Relative to project root
```

Add your logo images to `logos/` directory. Supported formats: PNG, JPG, GIF.

### AI Model Configuration

Radio OS defaults to Ollama running locally. To use alternative AI providers:

**ChatGPT / OpenAI:**
```yaml
llm:
  endpoint: https://api.openai.com/v1/completions
  api_key: your-api-key-here
models:
  producer: gpt-4
  host: gpt-3.5-turbo
```

**Claude / Anthropic:**
```yaml
llm:
  endpoint: https://api.anthropic.com/v1/complete
  api_key: your-api-key-here
models:
  producer: claude-3-opus-20240229
  host: claude-3-sonnet-20240229
```

**Google Gemini:**
```yaml
llm:
  endpoint: https://generativelanguage.googleapis.com/v1/models
  api_key: your-api-key-here
models:
  producer: gemini-pro
  host: gemini-pro
```

### TTS Configuration

Radio OS defaults to Piper (free, local TTS). To use cloud TTS:

**ElevenLabs:**
```yaml
tts:
  provider: elevenlabs
  api_key: your-elevenlabs-key
voices:
  host: voice-id-from-elevenlabs
```

**OpenAI TTS:**
```yaml
tts:
  provider: openai
  api_key: your-openai-key
voices:
  host: alloy  # or: echo, fable, onyx, nova, shimmer
```

See station manifest.yaml files for full TTS configuration options.

## Optional Features

### PyTorch ML (From the Backmarker)

The "From the Backmarker" racing management station includes advanced ML features for AI-powered team decisions. This requires PyTorch (~2GB):

**Install PyTorch:**
```bash
pip install torch>=2.0.0
```

The station works without PyTorch using simpler heuristics. ML features include:
- Neural network policy for strategic decisions
- Reinforcement learning for season-long optimization
- Training data collection and model updates

See [documentation/FTB_ML_SYSTEM.md](documentation/FTB_ML_SYSTEM.md) for details.

### FFmpeg (Audio Processing)

Some plugins require FFmpeg for advanced audio processing:

**Windows:**
- Download from [ffmpeg.org/download.html](https://ffmpeg.org/download.html)
- Add to PATH

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt-get install ffmpeg  # Ubuntu/Debian
sudo dnf install ffmpeg      # Fedora
```

## Troubleshooting

### Setup Issues

**"Python not found in PATH"**
- Ensure Python 3.10+ is installed
- Reinstall Python with "Add to PATH" option checked (Windows)
- Verify: `python --version` or `python3 --version`

**"Failed to install dependencies"**
- Check internet connection
- Try manual install: `pip install -r requirements.txt`
- Linux: Install system packages first:
  ```bash
  sudo apt-get install python3-tk libsndfile1 portaudio19-dev
  ```

**"Ollama downloads are slow"**
- Model downloads are 8-12GB, expect 10-30 minutes on average broadband
- You can skip Ollama during setup and install manually later
- Check Ollama is running: `ollama list`

**"Piper voice downloads failing"**
- Try downloading voices manually from [HuggingFace Piper Voices](https://huggingface.co/rhasspy/piper-voices/)
- Place `.onnx` and `.onnx.json` files in `voices/` directory
- Re-run: `python tools/inject_manifest_paths.py --piper-bin /path/to/piper --voices-dir ./voices`

### Runtime Issues

**"No audio output"**
- Check Piper is installed: Look for `voices/piper_*/piper/piper` binary
- Verify voice models exist: `ls voices/*.onnx`
- Check audio device in shell UI settings
- Test TTS manually: `echo "Test" | piper --model voices/en_US-lessac-high.onnx --output_file test.wav`

**"Station won't start / crashes immediately"**
- Check `stations/<station_id>/runtime.log` for errors
- Verify Ollama is running: `ollama list`
- Check station manifest.yaml for syntax errors
- Validate dependencies: `pip check`

**"AI models not found"**
- Pull missing models: `ollama pull qwen3:8b`, etc.
- Check Ollama endpoint in manifest: `llm.endpoint`
- Verify Ollama service is running in background

**"Port already in use"**
- Another station may be running
- Kill Radio OS processes: Task Manager (Windows) or `pkill -f radio_os` (Unix)
- Change port in manifest if needed

**"Out of memory / GPU errors"**
- Reduce model sizes (use `qwen3:8b` instead of larger models)
- Lower `producer.max_tokens` and `host.max_tokens` in manifest
- Close other GPU-intensive applications
- Consider cloud AI APIs instead of local Ollama

### Performance Issues

**"High CPU/GPU usage"**
- Reduce `producer.tick_sec` and `host.idle_riff_sec` in manifest
- Lower queue depths: `producer.target_depth`, `pacing.queue_target_depth`
- Use smaller AI models (8B instead of 70B parameters)

**"Slow response times"**
- Check internet if using cloud AI APIs
- Reduce `max_tokens` to speed up generation
- Use faster models (qwen3:8b is very performant)

## Support & Community

- **Issues**: [GitHub Issues](https://github.com/evengineer1ng/radio-os/issues)
- **Discussions**: [GitHub Discussions](https://github.com/evengineer1ng/radio-os/discussions)
- **Documentation**: [/documentation](documentation/)

## Plugin Development

Feed plugins are simple Python modules in `plugins/`:

```python
PLUGIN_NAME = "my_feed"
IS_FEED = True

DEFAULT_CONFIG = {
    "poll_interval": 300,
}

def feed_worker(stop_event, mem, cfg, runtime=None):
    # Access runtime globals
    from your_runtime import event_q, StationEvent, log
    
    while not stop_event.is_set():
        # Fetch content, push events
        event_q.put(StationEvent(
            role="feed",
            source="my_feed",
            content_blocks=[{"text": "Hello from my feed!"}]
        ))
        time.sleep(cfg["poll_interval"])
```

UI widgets can also be registered:

```python
def register_widgets(registry, runtime_stub):
    def factory(parent, runtime):
        return MyWidget(parent, runtime)
    
    registry.register(
        "my_widget",
        factory,
        title="My Widget",
        default_panel="left"
    )
```

## License & Attribution

### Radio OS
- **License**: GPL-3.0 (GNU General Public License v3.0)
- **Copyright**: (c) 2026 Evan Pena
- **Summary**: Free, open source, and hackable forever. Any derivative work must remain open source under GPL-3.0.

See [LICENSE](LICENSE) for full details.

### Dependencies

#### Piper TTS
- **License**: MIT
- **Source**: [rhasspy/piper](https://github.com/rhasspy/piper)
- **Binaries**: Downloaded on-demand via `setup.py`

#### Voice Models
- **License**: Typically CC-BY-NC per model (see [Piper Voices](https://huggingface.co/rhasspy/piper-voices/))
- **Note**: Downloaded separately by users - verify licensing before commercial use

#### FFmpeg
- **License**: LGPL
- **Source**: [ffmpeg.org](https://ffmpeg.org/)

## Environment Variables

- `RADIO_OS_ROOT`: Project root directory
- `RADIO_OS_PLUGINS`: Global plugins directory
- `RADIO_OS_VOICES`: Global voices directory
- `STATION_DIR`: Active station directory
- `STATION_DB_PATH`: Station SQLite database
- `STATION_MEMORY_PATH`: Station memory JSON
- `CONTEXT_MODEL`: LLM model for producer
- `HOST_MODEL`: LLM model for host

## Contributing

Contributions welcome! This project is still evolving. Key areas:

- New feed plugins
- Linux media control integration
- Additional TTS engine support
- Performance optimizations
- Documentation

## Credits

- TTS: [Piper](https://github.com/rhasspy/piper) by Rhasspy
- Audio: [FFmpeg](https://ffmpeg.org/)
- LLM: Ollama-compatible endpoints
