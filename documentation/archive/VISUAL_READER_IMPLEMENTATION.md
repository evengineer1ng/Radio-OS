# visual_reader Plugin — Complete Implementation Guide

**visual_reader** is a complete, production-ready plugin for capturing and interpreting visual content from video, window, or screen sources using a vision-capable LLM.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     SHELL (Global Settings)                  │
│              Visual Models Tab (OpenAI/Ollama/etc)            │
└──────────────────────┬──────────────────────────────────────┘
                       │ (stores config in ~/.radioOS/config.json)
                       │
┌──────────────────────┴──────────────────────────────────────┐
│                    LAUNCHER                                   │
│        (reads global config, injects env vars)                │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────┐
│                 STATION RUNTIME                              │
│ ┌────────────────────────────────────────────────────────┐  │
│ │  visual_reader Plugin (feed_worker thread)             │  │
│ │  ┌──────────────────────────────────────────────────┐  │  │
│ │  │ 1. ScreenCapture (mss/cv2/pyautogui)             │  │  │
│ │  │    - screen capture                              │  │  │
│ │  │    - window capture                              │  │  │
│ │  │    - video frame extraction                       │  │  │
│ │  └──────────────────────────────────────────────────┘  │  │
│ │  ┌──────────────────────────────────────────────────┐  │  │
│ │  │ 2. Vision Client (Factory Pattern)               │  │  │
│ │  │    - OllamaVisionClient (local)                   │  │  │
│ │  │    - APIVisionClient (OpenAI/Anthropic/Google)   │  │  │
│ │  └──────────────────────────────────────────────────┘  │  │
│ │  ┌──────────────────────────────────────────────────┐  │  │
│ │  │ 3. Memory/Event Flow                             │  │  │
│ │  │    - Store text summaries only                    │  │  │
│ │  │    - Emit StationEvent for producer flow         │  │  │
│ │  └──────────────────────────────────────────────────┘  │  │
│ │  ┌──────────────────────────────────────────────────┐  │  │
│ │  │ 4. Widget UI (station editor)                    │  │  │
│ │  │    - Enable/disable toggle                       │  │  │
│ │  │    - Source selection                            │  │  │
│ │  │    - Capture interval slider                     │  │  │
│ │  │    - Talk over video toggle                      │  │  │
│ │  └──────────────────────────────────────────────────┘  │  │
│ └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. ScreenCapture (Cross-Platform)

Captures screenshots from three sources:

```python
ScreenCapture.capture_screen()        # Full screen (mss/pyautogui)
ScreenCapture.capture_window(title)   # Window capture (Windows only, win32gui)
ScreenCapture.capture_video_frame()   # Video file frame (OpenCV)
```

**Platform Support:**
- **Windows**: mss, pyautogui, win32gui (window capture)
- **Mac**: mss, pyautogui
- All images are JPEG-encoded at 85% quality and resized to max 1024px width

**Dependencies:**
- `mss` — ultra-fast screen capture
- `Pillow` — image manipulation
- `opencv-python` — video frame extraction
- `pyautogui` — fallback screen capture
- `pywin32` — Windows window capture (optional, Windows only)

### 2. Vision Clients (Factory Pattern)

Create the appropriate vision client based on global config:

```python
# Local model (Ollama/LLaVA)
client = OllamaVisionClient(
    endpoint="http://localhost:11434",
    model="llava:latest"
)

# API-based (OpenAI)
client = APIVisionClient(
    provider="openai",
    model="gpt-4-vision",
    api_key="sk-...",
)

# Unified factory
client = create_vision_client(global_visual_cfg)
```

**Supported Providers:**
- **Ollama** (local) — free, runs locally, no API key
- **OpenAI** — GPT-4-Vision, GPT-4o (API-based)
- **Anthropic** — Claude 3.5 Sonnet (API-based)
- **Google** — Gemini 1.5 Pro (API-based)
- **Custom** — any HTTP endpoint

### 3. Feed Worker Loop

Runs in a background thread:

```python
feed_worker(mem, config, event_fn, log_fn)
```

**Loop Logic:**
1. Load global vision model config
2. Initialize vision client
3. Every `capture_interval` seconds:
   - Capture screenshot from configured source
   - Send to vision LLM
   - Parse interpretation text
   - Store in `mem["visual_interpretations"]` (last 50 entries)
   - Emit `visual_interpretation` event to producer
   - Event includes `talk_over_video` flag

**Memory Structure:**
```python
mem["visual_interpretations"] = [
    {
        "timestamp": 1707000000,
        "source": "screen",  # or "window" / "video_file"
        "text": "A laptop screen showing code editor with Python script open."
    },
    ...
]
```

**Emitted Events:**
```python
evt = StationEvent(
    role="visual_reader",
    event_type="visual_interpretation",
    data={
        "source": "screen",
        "text": "...",
        "timestamp": 1707000000,
        "talk_over_video": False,  # Producer uses this to decide timing
    }
)
```

### 4. Widget UI

Registers a config panel in the station editor:

**Controls:**
- **Enable Visual Reader** (checkbox)
- **Source** (radio buttons: screen / window / video_file)
- **Capture Interval** (slider, 1-60 seconds)
- **Talk Over Video** (checkbox) — AI speaks while source is active

Configuration is persisted to station manifest under `plugins.visual_reader`.

## Configuration

### Global Config (shell settings)

Set in **Settings → Visual Models tab**:
- Model Type: Local vs API
- Local Model: endpoint / model name
- API Credentials: provider, model, key, endpoint
- Image Processing: max size, quality

These are stored in `~/.radioOS/config.json` and passed to all stations.

### Per-Station Config (manifest)

Add to `stations/<id>/manifest.yaml`:

```yaml
plugins:
  visual_reader:
    enabled: false
    source_type: screen  # "screen" / "window" / "video_file"
    source_path: ""  # For video files: /path/to/video.mp4
    source_window: ""  # For windows: "OBS Studio"
    capture_interval: 5  # seconds
    talk_over_video: false
    max_interpretation_length: 500
    interpretation_temperature: 0.7
```

Or edit in the station editor UI.

## Usage Examples

### 1. Screen Capture + Ollama

**Global Config:**
- Model Type: Local
- Local Model: `http://localhost:11434`

**Station Config:**
- Source: `screen`
- Capture Interval: `5`
- Talk Over Video: `false`

**Setup:**
```bash
# Start Ollama with LLaVA
ollama pull llava:latest
ollama serve
```

**Result:** Every 5 seconds, the plugin captures the full screen, sends to LLaVA, and stores interpretation.

### 2. Window Capture + OpenAI (Windows)

**Global Config:**
- Model Type: API
- API Provider: `openai`
- Model: `gpt-4-vision`
- API Key: `sk-...`

**Station Config:**
- Source: `window`
- Source Window: `OBS Studio`
- Capture Interval: `3`
- Talk Over Video: `true`

**Result:** Every 3 seconds, captures OBS window, sends to GPT-4-Vision, producer receives event with `talk_over_video=true` so it can compose live commentary.

### 3. Video Analysis + Anthropic

**Global Config:**
- Model Type: API
- API Provider: `anthropic`
- Model: `claude-3-5-sonnet-20241022`
- API Key: `sk-ant-...`

**Station Config:**
- Source: `video_file`
- Source Path: `/media/interview.mp4`
- Capture Interval: `10`
- Talk Over Video: `false`

**Result:** Every 10 seconds, extracts a frame from the video, analyzes with Claude, and summarizes.

## Producer Integration

The producer can consume `visual_interpretation` events:

```python
# In producer logic
for evt in event_q.get_all():
    if evt.role == "visual_reader" and evt.event_type == "visual_interpretation":
        visual_text = evt.data["text"]
        talk_now = evt.data["talk_over_video"]
        
        if talk_now:
            # Interrupt current segment, generate commentary immediately
            commentary = llm_generate(
                f"Create a 20-second radio commentary about this:\n{visual_text}",
                model=HOST_MODEL
            )
            # Queue for TTS and broadcast
        else:
            # Queue for next break/segment
            # Or prepend to memory for next segment intro
```

## Environment Variables (Injected by launcher)

```bash
VISUAL_MODEL_TYPE=local|api
VISUAL_MODEL_LOCAL=model_or_endpoint
VISUAL_MODEL_API_PROVIDER=openai|anthropic|google|custom
VISUAL_MODEL_API_MODEL=model_name
VISUAL_MODEL_API_KEY=secret_key
VISUAL_MODEL_API_ENDPOINT=custom_url
VISUAL_MODEL_MAX_IMAGE_SIZE=1024  # px
VISUAL_MODEL_IMAGE_QUALITY=85     # 1-100
```

Access via:
```python
import your_runtime as rt
config = rt.get_visual_model_config()
```

## Dependencies

Install optional libraries as needed:

```bash
# Screen capture (required for any source)
pip install mss Pillow pyautogui

# Video frame extraction
pip install opencv-python

# Windows window capture
pip install pywin32

# API clients (optional, only for your chosen provider)
pip install openai               # For OpenAI
pip install anthropic            # For Anthropic
pip install google-generativeai  # For Google Gemini
```

## Troubleshooting

### Vision model not connecting

1. Check global config: **Settings → Visual Models**
2. Verify model type and credentials
3. For local: ensure Ollama/service is running on correct port
4. For API: verify API key is valid and not expired
5. Check plugin logs: look for `[VISUAL ...]` messages in `stations/<id>/runtime.log`

### No screenshots captured

1. Enable the plugin: check station config `enabled: true`
2. Check source is correct (screen/window/video_file)
3. For window capture (Windows): ensure window title matches exactly
4. For video file: ensure file path exists and is readable
5. Check libraries installed: `python -c "import mss; import cv2; import PIL"`

### Performance issues

1. Increase `capture_interval` (e.g., 10+ seconds)
2. Reduce `max_image_size` in global config (e.g., 512)
3. Reduce `image_quality` (e.g., 70)
4. Use local model instead of API for lower latency
5. Monitor CPU/memory: vision inference is heavy

### Memory growing unbounded

The plugin caps `mem["visual_interpretations"]` at 50 entries. If memory still grows:
- Check event_q isn't backed up (producer should consume events)
- Verify `event_fn()` is callable in feed_worker

## Future Enhancements

- [ ] Real-time frame batch processing (send multiple frames at once)
- [ ] Configurable interpretation prompt templates
- [ ] Caching of identical/similar screenshots (skip redundant API calls)
- [ ] Audio transcription integration (speech → text from captured video)
- [ ] Scene change detection (only capture on significant change)
- [ ] Multi-source orchestration (simultaneous screen + window + video)
- [ ] Integration with OBS Native plugin for frame buffer access

