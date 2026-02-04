# Development Guide

## Project Structure

```
radio_os/
├── runtime.py           # Core station engine
├── shell.py            # Desktop UI shell
├── kernel.py           # Shared utilities
├── launcher.py         # Station process launcher
├── your_runtime.py     # Plugin compatibility shim
├── plugins/            # Feed plugins and UI widgets
├── stations/           # Station configurations and data
├── voices/             # TTS voice models
├── templates/          # Configuration templates
└── README.md
```

## Key Concepts

### Runtime Engine (runtime.py)

The central loop that:
1. Fetches content from feed plugins
2. Routes events through the priority queue
3. Generates AI commentary (producer + host)
4. Converts text to speech via Piper
5. Manages audio playback and music pausing
6. Updates the UI

**Core queues:**
- `event_q`: Feed plugins push content here
- `ui_q`: Runtime sends UI updates
- `ui_cmd_q`: UI sends commands back
- `dj_q`: DJ-style annotations
- `subtitle_q`: Subtitle display

### Plugin Architecture

Plugins are Python modules that export:

```python
PLUGIN_NAME = "my_plugin"
IS_FEED = True  # or False for widgets only
DEFAULT_CONFIG = {...}

def feed_worker(stop_event, mem, cfg, runtime=None):
    # Long-running feed poll loop
    pass

def register_widgets(registry, runtime_stub):
    # Optional: register UI widgets
    pass
```

Plugins import from `your_runtime` to access:
- `event_q`, `ui_q`, `ui_cmd_q`
- `StationEvent` class
- `log` function
- `now_ts()` timestamp helper

### Station Configuration

Each station has a `manifest.yaml` containing:
- Station metadata
- LLM endpoints and models
- Feed plugin list and settings
- Voice assignments
- Pacing/timing parameters

### Music Integration

`music_breaks` plugin handles:
- Detecting now-playing tracks
- Pausing during talk segments
- Resuming when audio queue clears
- Producer-initiated playback control

**Platform support:**
- Windows: GSMTC (Global System Media Transport Controls)
- macOS: AppleScript (Music.app, Spotify)
- Linux: Not yet implemented

### Text-to-Speech

Uses Piper (offline ONNX models):
1. Runtime detects platform
2. Auto-finds Piper binary via `_auto_detect_piper_bin()`
3. Subprocess call: `piper -m voice.onnx -f output.wav`
4. Audio fed to playback queue

## Adding a New Feed Plugin

1. Create `plugins/myplugin.py`:

```python
import time
import your_runtime as rt

PLUGIN_NAME = "myplugin"
IS_FEED = True
DEFAULT_CONFIG = {
    "poll_interval": 300,
    "max_items": 5,
}

def feed_worker(stop_event, mem, cfg, runtime=None):
    if runtime is None:
        return
    
    event_q = runtime.get("event_q")
    log = runtime.get("log")
    StationEvent = runtime.get("StationEvent")
    
    while not stop_event.is_set():
        try:
            # Fetch from your source
            items = fetch_items()
            
            for item in items[:cfg.get("max_items", 5)]:
                # Push to event queue
                event_q.put(StationEvent(
                    role="feed",
                    source="myplugin",
                    content_blocks=[
                        {"text": item["title"]},
                        {"text": item["body"], "type": "summary"},
                    ],
                    metadata={"url": item["url"]}
                ))
                
                # Avoid spam
                time.sleep(1)
        
        except Exception as e:
            if callable(log):
                log("feed", f"myplugin error: {e}")
        
        # Poll interval
        time.sleep(cfg.get("poll_interval", 300))
```

2. Add to station manifest:
```yaml
feeds:
  myplugin:
    enabled: true
    poll_interval: 300
    max_items: 5
```

## Platform Compatibility Checklist

When adding features, test/support:

- [ ] Windows
- [ ] macOS
- [ ] Linux

Common pitfalls:
- Hardcoded paths: Use `os.path.join()`
- Platform-specific APIs: Check `sys.platform`
- Binary paths: Use auto-detection via environment variables
- Subprocess calls: Quote paths, handle missing binaries gracefully

## Debugging

Enable verbose logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Station runtime logs to:
- `stations/<id>/runtime.log` (when launched via shell)
- stdout (when run directly)

## Testing

1. Test locally:
```bash
python shell.py
```

2. Create a test station via the wizard
3. Monitor `runtime.log` for errors
4. Check event flow with the Event Explorer widget

## Common Issues

### "Piper not found"
- Ensure Piper binary is in `voices/piper_*/piper/`
- Or set `RADIO_OS_VOICES` environment variable
- Or specify `piper_bin` in manifest

### "LLM endpoint unreachable"
- Check `CONTEXT_MODEL` / `HOST_MODEL` env vars
- Ensure Ollama is running on correct host:port
- See manifest for endpoint configuration

### Plugin not loading
- Check plugin name is in manifest
- Ensure `feed_worker` function exists
- Look for import errors in `runtime.log`

### Audio quality issues
- Test individual voice: `piper -m voices/model.onnx -f test.wav`
- Verify audio device in shell settings
- Check system volume

## Performance Tips

- Minimize feed poll intervals (balance freshness vs. load)
- Use `mem` dict for state persistence across polls
- Batch LLM requests when possible
- Profile hot paths with `cProfile`

## Questions?

See README.md, existing plugins, or open an issue.
