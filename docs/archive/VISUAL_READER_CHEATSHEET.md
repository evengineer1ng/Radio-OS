# visual_reader — One-Page Cheat Sheet

## Install (Pick Your Setup)

### Option A: OpenAI (Recommended for Power)
```bash
pip install mss Pillow pyautogui opencv-python openai
export OPENAI_API_KEY="sk-..."
python shell.py
```

### Option B: Anthropic (Claude)
```bash
pip install mss Pillow pyautogui opencv-python anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
python shell.py
```

### Option C: Free Local Ollama
```bash
pip install mss Pillow pyautogui opencv-python
ollama pull llava:latest
ollama serve  # in Terminal 1
python shell.py  # in Terminal 2
```

---

## Setup (4 Steps)

### Step 1: Configure Vision Model
```
shell.py → Settings → Visual Models

LOCAL:
  ✓ Select "Local Model"
  → "http://localhost:11434"
  → Save

OR API:
  ✓ Select "API-based"
  → Provider: openai / anthropic / google
  → Model: gpt-4-vision / claude-3-5-sonnet / gemini-1.5-pro
  → API Key: [paste]
  → Save
```

### Step 2: Enable in Station
```
Station Editor → Visual Reader

✓ Enable Visual Reader
Source: screen (or window/video_file)
Capture Interval: 5 (seconds)
Talk Over Video: ☐ (leave unchecked for now)
Save
```

### Step 3: Launch
```
Click "Launch Station"
```

### Step 4: Monitor
```
tail -f stations/algotradingfm/runtime.log | grep VISUAL
# Should see: [VISUAL ...] Interpreted: A laptop showing...
```

---

## Source Types

| Source | Use When | Setup |
|--------|----------|-------|
| **screen** | Monitoring your screen | Just select "screen" |
| **window** | Windows only, specific window | Set "OBS Studio" or window title |
| **video_file** | Analyzing a video file | Set full path: `/media/video.mp4` |

---

## Common Configs

### Live Commentary
```yaml
source_type: screen
capture_interval: 3
talk_over_video: true
```
→ Every 3s, capture & generate live commentary

### Batch Video Analysis
```yaml
source_type: video_file
source_path: /path/to/video.mp4
capture_interval: 10
talk_over_video: false
```
→ Every 10s, extract frame for analysis

### OBS Monitoring (Windows)
```yaml
source_type: window
source_window: OBS Studio
capture_interval: 5
talk_over_video: true
```
→ Monitor OBS window, generate commentary

---

## Consume Events in Producer

```python
import your_runtime as rt

# In your producer feed_worker
for evt in event_q.get_all():
    if evt.role == "visual_reader":
        summary = evt.data["text"]        # Interpretation
        talk_now = evt.data["talk_over_video"]  # Live?
        
        if talk_now:
            # Generate live commentary
            comment = llm_generate(
                f"Comment on: {summary}",
                model=HOST_MODEL,
                num_predict=100,
            )
            # Send to TTS
```

---

## Quick Verify

```bash
# Check plugin loaded
python -c "from plugins import visual_reader; print(f'✓ {visual_reader.PLUGIN_NAME}')"

# Check config saved (Windows)
type %APPDATA%\RadioOS\config.json | python -m json.tool | grep visual

# Check logs running (Mac/Linux)
grep VISUAL ~/stations/*/runtime.log
```

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError: mss` | `pip install mss` |
| `"No vision model configured"` | Settings → Visual Models → Save |
| `"Connection refused"` | `ollama serve` not running (for Ollama) |
| `"Invalid API key"` | Copy fresh key into Settings → Visual Models |
| No `[VISUAL]` in logs | Station Editor: Enable Visual Reader checkbox |

---

## Monitor Performance

```bash
# Watch real-time events
tail -f stations/STATION_ID/runtime.log | grep VISUAL

# Expected output every 5 seconds:
# [VISUAL ...] Interpreted: A laptop showing code editor...

# If slower: Increase capture_interval (10s instead of 5s)
# If errors: Check API key or Ollama connection
```

---

## Data Stored

- **Memory:** `mem["visual_interpretations"]` — last 50 text summaries
- **Events:** `visual_interpretation` events emitted to producer
- **Images:** NEVER stored (discarded after interpretation)

---

## Cost Estimate (API)

| Provider | Cost/Image | 10 imgs/min |
|----------|-----------|------------|
| OpenAI | ~$0.01 | ~$6/hour |
| Anthropic | ~$0.003 | ~$1.80/hour |
| Google | ~$0.002 | ~$1.20/hour |
| Ollama (local) | $0 | FREE ✓ |

---

## Docs

- **[VISUAL_READER_HOWTO.md](VISUAL_READER_HOWTO.md)** ← Full guide with scenarios
- **[VISUAL_READER_QUICKSTART.md](VISUAL_READER_QUICKSTART.md)** ← Quick reference
- **[VISUAL_READER_IMPLEMENTATION.md](VISUAL_READER_IMPLEMENTATION.md)** ← Technical deep dive

---

## One-Liner Test

```bash
# Install minimal + test
pip install mss Pillow pyautogui opencv-python && python test_visual_reader.py
```

Should see: **7/7 tests passed ✨**

---

Done! You're ready to analyze visual content 🎬
