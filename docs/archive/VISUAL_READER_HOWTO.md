# How to Use visual_reader — Quick Guide

## TL;DR (2 Minutes)

### 1. Install Dependencies
```bash
# Core (required)
pip install mss Pillow pyautogui opencv-python

# Pick ONE vision provider:
pip install openai                # OpenAI GPT-4-Vision
# OR
pip install anthropic             # Anthropic Claude
# OR
pip install google-generativeai   # Google Gemini
```

### 2. Set Up Vision Model (Shell Settings)
```
1. Launch shell:  python shell.py
2. Click Settings (gear icon)
3. Click "Visual Models" tab
4. Choose model:
   - LOCAL: Select "Local Model", use "http://localhost:11434"
   - API: Select "API-based", choose provider (OpenAI/Anthropic/Google), paste API key
5. Click "Save Settings"
```

### 3. Enable in Station
```
1. Click station to edit
2. Find "Visual Reader" section
3. Toggle "Enable Visual Reader" ✓
4. Select source:
   - screen  (capture full screen)
   - window  (Windows only: specify window title)
   - video_file (specify /path/to/video.mp4)
5. Set "Capture Interval" (e.g., 5 seconds)
6. Toggle "Talk Over Video" if you want AI to speak live
7. Save
```

### 4. Launch & Watch
```
1. Click "Launch Station"
2. Watch logs for [VISUAL ...] messages:
   tail -f stations/algotradingfm/runtime.log | grep VISUAL
```

Done! 🎉

---

## Common Scenarios

### Scenario 1: Free Local Analysis (Ollama)
Doesn't need internet or API keys. Slower but free.

**Setup:**
```bash
# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Pull model
ollama pull llava:latest

# Terminal 3: Launch RadioOS
python shell.py
```

**In Settings → Visual Models:**
- Model Type: **Local**
- Local Model: **http://localhost:11434**
- Save

**In Station Editor:**
- Enable ✓
- Source: **screen**
- Interval: **5** (seconds)
- Save & Launch

**Result:** Every 5 seconds, captures screen and sends to local LLaVA for interpretation.

---

### Scenario 2: Live Commentary (OpenAI)
For real-time video analysis with live AI commentary.

**Setup:**
```bash
pip install mss Pillow pyautogui opencv-python openai
export OPENAI_API_KEY="sk-..."
python shell.py
```

**In Settings → Visual Models:**
- Model Type: **API**
- API Provider: **openai**
- Model: **gpt-4-vision** (or **gpt-4o**)
- API Key: *paste your key*
- Max Image Size: **1024** (max quality)
- Save

**In Station Editor:**
- Enable ✓
- Source: **screen**
- Interval: **3** (every 3 seconds)
- Talk Over Video: ✓ (YES - generate live commentary)
- Save & Launch

**Producer Integration:**
```python
# In your producer feed_worker
for evt in event_q.get_all():
    if evt.role == "visual_reader":
        visual_summary = evt.data["text"]
        talk_now = evt.data["talk_over_video"]
        
        if talk_now:
            # Generate live commentary
            comment = llm_generate(
                f"You just saw: {visual_summary}\n\nRespond with a 20-second radio segment.",
                model=HOST_MODEL,
                num_predict=100,
            )
            # Queue for TTS and broadcast
```

**Result:** Every 3 seconds, AI analyzes screen and generates live commentary segments.

---

### Scenario 3: Video Analysis (Anthropic Claude)
For post-analysis of recorded videos.

**Setup:**
```bash
pip install mss Pillow pyautogui opencv-python anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
python shell.py
```

**In Settings → Visual Models:**
- Model Type: **API**
- API Provider: **anthropic**
- Model: **claude-3-5-sonnet-20241022**
- API Key: *paste your key*
- Save

**In Station Editor:**
- Enable ✓
- Source: **video_file**
- Source Path: **/path/to/video.mp4**
- Interval: **10** (every 10 seconds)
- Talk Over Video: ✗ (NO - batch analysis)
- Save & Launch

**Result:** Extracts frames every 10 seconds, Claude analyzes them, summaries stored in memory.

---

## Checking It Works

### 1. Verify Plugin Loaded
```bash
python -c "from plugins import visual_reader; print(f'✓ {visual_reader.PLUGIN_NAME}')"
# Output: ✓ visual_reader
```

### 2. Check Global Config Saved
```bash
# Windows
cat %APPDATA%\RadioOS\config.json | python -m json.tool | grep visual_model

# Mac/Linux
cat ~/.radioOS/config.json | python -m json.tool | grep visual_model
```

### 3. Watch Runtime Logs
```bash
# Start station, then in another terminal:
tail -f stations/algotradingfm/runtime.log | grep VISUAL

# You should see:
# [VISUAL ...] Visual reader started: screen @ 5s
# [VISUAL ...] Interpreted: A laptop showing code editor with Python script...
```

### 4. Check Memory
```python
# In station memory viewer (or memory file)
# Look for:
mem["visual_interpretations"] = [
    {
        "timestamp": 1707000000,
        "source": "screen",
        "text": "A bright screen showing..."
    }
]
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| **"No vision model configured"** | Go to Settings → Visual Models, select model, Save |
| **"Connection refused" (Ollama)** | Make sure `ollama serve` is running: `ollama pull llava:latest && ollama serve` |
| **"Invalid API key"** | Double-check your key in Settings → Visual Models (it's masked but should save) |
| **No [VISUAL] messages in logs** | Enable plugin in station editor, make sure "Enable Visual Reader" is checked |
| **Out of memory** | Increase capture_interval (e.g., 10s instead of 5s) or reduce max_image_size in global settings |
| **Slow interpretation** | It's normal! Vision models take 2-5s (Ollama) or 5-10s (API). Increase interval or reduce image size. |

---

## Pro Tips

1. **Test with screen first** — easiest to debug
2. **Start with 10-second intervals** — faster testing cycles
3. **Use local Ollama for prototyping** — free, no API calls
4. **Integrate with producer early** — consume events from the start
5. **Monitor logs** — `[VISUAL ...]` messages tell you what's happening
6. **Tune image quality** — max_image_size=512, quality=70 = faster + cheaper

---

## What Gets Stored?

**✓ Text summaries** (memory, events)  
**✗ NO image files** (screenshots discarded after interpretation)

Interpretations stored in:
- `mem["visual_interpretations"]` — last 50 entries
- `event_q` — visual_interpretation events (consumed by producer)

---

## Integration with Producer Example

```python
# In producer's feed_worker
import your_runtime as rt

# Get visual interpretations from memory
visual_summaries = mem.get("visual_interpretations", [])
for entry in visual_summaries:
    if entry["timestamp"] > last_processed:
        print(f"New visual: {entry['text']}")
        
        # Generate commentary segment
        segment = llm_generate(
            f"Create a 30-second segment about: {entry['text']}",
            model=HOST_MODEL,
        )
        
        # Queue for TTS + broadcast
        event_fn(rt.StationEvent(
            role="producer",
            event_type="segment_ready",
            data={"text": segment, "type": "visual_commentary"}
        ))
```

---

## Next Steps

1. ✅ Install dependencies (see above)
2. ✅ Configure global vision model
3. ✅ Enable in station
4. ✅ Launch & watch logs
5. → Integrate with producer for live commentary
6. → Tune capture interval for your use case
7. → Add custom prompts if needed

---

**Questions?** See [VISUAL_READER_QUICKSTART.md](VISUAL_READER_QUICKSTART.md) or [VISUAL_READER_IMPLEMENTATION.md](VISUAL_READER_IMPLEMENTATION.md)

**Run validation:** `python test_visual_reader.py`
