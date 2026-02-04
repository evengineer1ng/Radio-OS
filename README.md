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

### Easiest: Use the Launcher Script

**Windows:**
```bash
windows.bat
```

**macOS/Linux:**
```bash
chmod +x mac.sh
./mac.sh
```

These scripts handle everything:
- Create virtual environment (first time)
- Install dependencies
- Download Piper (if needed)
- Validate setup
- Launch Radio OS

### Manual Installation

If you prefer manual setup:

1. Clone the repository:
```bash
git clone https://github.com/yourusername/radio_os.git
cd radio_os
```

2. Create and activate virtual environment:
```bash
python -m venv radioenv
source radioenv/bin/activate  # On Windows: radioenv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Download Piper TTS and voice models:
```bash
python setup.py
```

5. Launch:
```bash
python shell.py
```

## Creating a Station

Use the built-in wizard in the shell UI, or manually create a station directory:

```
stations/mystation/
  ├── manifest.yaml    # Station configuration
  └── mystation.py     # Optional custom entrypoint
```

See [templates/default_manifest.yaml](templates/default_manifest.yaml) for configuration options.

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
