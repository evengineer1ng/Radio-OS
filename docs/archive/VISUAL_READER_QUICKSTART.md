# visual_reader Quick Start

## 30-Second Setup

### 1. Install Dependencies
```bash
# Required (all platforms)
pip install mss Pillow pyautogui opencv-python

# Pick one:
pip install openai              # OpenAI
pip install anthropic           # Anthropic/Claude
pip install google-generativeai # Google Gemini
```

### 2. Configure Global Settings
- Launch shell: `python shell.py`
- Click **Settings → Visual Models**
- Choose your model (Local Ollama or API)
- Save

### 3. Enable in Station
- Open station editor
- Find **Visual Reader** section
- Toggle **Enable Visual Reader**
- Choose source (screen/window/video_file)
- Set capture interval (5-10 seconds recommended)
- Toggle **Talk Over Video** if desired
- Save

### 4. Run Station
- Click **Launch Station**
- Watch runtime.log for `[VISUAL ...]` messages
- Interpretations appear in station memory

## Test Setups

### Local Testing (Ollama + Screen Capture)
```bash
# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Pull model
ollama pull llava:latest

# Terminal 3: Launch RadioOS
cd ~/radio_os
python shell.py
```

Then in Settings → Visual Models:
- Model Type: **Local**
- Local Model: **http://localhost:11434** (or just `llava:latest`)

### Cloud Testing (OpenAI + Screen Capture)
```bash
export OPENAI_API_KEY="sk-..."
python shell.py
```

Then in Settings → Visual Models:
- Model Type: **API**
- API Provider: **openai**
- Model: **gpt-4-vision** (or **gpt-4o**)
- API Key: *paste from env*

## Common Configurations

### Live Stream Commentary
```yaml
source_type: screen
capture_interval: 3
talk_over_video: true
```
→ Every 3 seconds, capture screen and generate live commentary

### Video Analysis
```yaml
source_type: video_file
source_path: /path/to/video.mp4
capture_interval: 10
talk_over_video: false
```
→ Extract frames every 10 seconds for post-analysis

### Window Monitoring (Windows)
```yaml
source_type: window
source_window: OBS Studio
capture_interval: 5
talk_over_video: true
```
→ Monitor OBS output, generate commentary

## API Costs (Rough Estimate)

**OpenAI GPT-4-Vision:**
- ~$0.01 per image (1024px)
- 10 images/min = ~$6/hour

**Anthropic Claude 3.5 Sonnet:**
- ~$0.003 per image (1024px)
- 10 images/min = ~$1.80/hour

**Google Gemini 1.5:**
- ~$0.002 per image
- 10 images/min = ~$1.20/hour

**Ollama (Local):**
- $0 (runs on your machine)
- Slower but free

## Debugging

### Check if plugin loaded
```bash
# Look for visual_reader in plugin list
python -c "from shell import discover_plugins; print(discover_plugins())"
```

### Test vision client directly
```python
import your_runtime as rt
cfg = rt.get_visual_model_config()
print(cfg)
```

### Check environment variables
```bash
# Windows
echo %VISUAL_MODEL_TYPE%
echo %VISUAL_MODEL_LOCAL%

# Mac/Linux
echo $VISUAL_MODEL_TYPE
echo $VISUAL_MODEL_LOCAL
```

### Monitor in real-time
```bash
# Watch runtime logs
tail -f stations/algotradingfm/runtime.log | grep VISUAL
```

## Next Steps

1. **Set up global visual model** in shell settings
2. **Test with a simple station** (enable plugin, capture interval = 10s)
3. **Monitor logs** to see interpretations flowing
4. **Integrate with producer** to consume events
5. **Tune capture interval** and image quality for your use case

---

**Questions?** Check [VISUAL_READER_IMPLEMENTATION.md](VISUAL_READER_IMPLEMENTATION.md) for full details.
