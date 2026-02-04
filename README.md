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

### Prerequisites

- Python 3.10+
- Piper TTS binary for your platform
- FFmpeg (for audio processing)
- Ollama (or compatible LLM endpoint)

### Installation

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
pip install -r dependencies.txt
```

4. Download Piper TTS binary:
   - **Windows**: Download from [Piper Releases](https://github.com/rhasspy/piper/releases), extract to `voices/piper_windows_amd64/`
   - **macOS**: Download macOS build, extract to `voices/piper_macos_amd64/`
   - **Linux**: Download Linux build, extract to `voices/piper_linux_amd64/`

5. Launch the shell:
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

## Platform-Specific Notes

### Windows
- Media control integration via Windows Media API (GSMTC)
- Piper auto-detected at `voices/piper_windows_amd64/piper/piper.exe`

### macOS
- Media control via AppleScript (Music.app, Spotify)
- Piper auto-detected at `voices/piper_macos_amd64/piper/piper` or `voices/piper_macos_arm64/piper/piper`

### Linux
- Media control not yet implemented
- Piper auto-detected at `voices/piper_linux_amd64/piper/piper`

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

## License

[Add your license here]

## Credits

- TTS: [Piper](https://github.com/rhasspy/piper)
- Audio: FFmpeg
- LLM: Ollama-compatible endpoints
