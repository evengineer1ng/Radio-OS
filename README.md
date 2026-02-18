# Radio OS

[![CI](https://github.com/evengineer1ng/Radio-OS/actions/workflows/ci.yml/badge.svg)](https://github.com/evengineer1ng/Radio-OS/actions/workflows/ci.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

A desktop-first, content-agnostic AI radio runtime.  Build custom AI radio stations that pull from live feeds, generate commentary, and stream audio with natural TTS voices.

![Radio OS](radioos.png)

---

## Quick Start

> **Requirements:** Python 3.10+ · Windows 10/11, macOS 11+, or Linux

### 1. Launch the installer menu

**macOS / Linux:**
```bash
chmod +x mac.sh
./mac.sh
```

**Windows:**
```
windows.bat
```

### 2. Pick from the menu

```
========================================
        🎙️  Radio OS Launcher
========================================

  1)  Boot Radio OS
  2)  Install / update core dependencies
  -----------------------------------------
  3)  Install Ollama   (local AI models, optional)
  4)  Install Piper    (offline TTS, optional)
  5)  Install PyTorch  (ML features, optional)

  q)  Quit
```

**First time?**  Run **option 2** to install core dependencies, then **option 1** to boot.  That's it — you'll be inside the GUI in under five minutes.

Options 3–5 are entirely optional power-user add-ons you can install whenever you like:

| Option | What it does | Size | When you need it |
|--------|-------------|------|------------------|
| **Ollama** | Run AI models locally on your GPU | ~8–12 GB | If you want free, private AI (otherwise use OpenAI / Claude / Gemini API keys) |
| **Piper** | Fast offline text-to-speech | ~20–400 MB | If you want an alternative to the built-in Kokoro TTS |
| **PyTorch** | ML features for "From the Backmarker" | ~2 GB | Only for the racing management sim's advanced AI |

---

## What's Inside

```
mac.sh / windows.bat    ← Start here!
shell_bookmark.py       ← Desktop UI and process manager
bookmark.py             ← Station runtime engine (feeds, events, audio)
launcher.py             ← Station process launcher
model_provider.py       ← LLM provider abstraction
voice_provider.py       ← TTS provider abstraction
plugins/                ← Feed plugins and UI widgets
stations/               ← Per-station configs and entrypoints
voices/                 ← TTS voice models (ONNX)
web/                    ← Svelte web frontend
docs/                   ← Developer documentation & release notes
```

## Stations Included

| Station | Description |
|---------|-------------|
| **WelcomeFM** | Intro station — great place to start |
| **BasketballFM** | Basketball news and commentary |
| **HockeyFM** | Hockey coverage and analysis |
| **popcultureFM** | Pop culture trends and entertainment |
| **SimRacingFM** | Sim racing community and esports |
| **VibezFM** | Music, culture, and lifestyle |
| **FlowFM** | Hip-hop focus with DJ commentary |
| **FromTheBackmarker** | Formula racing management sim with ML |

All stations work out-of-the-box after installing core dependencies.

---

## AI Provider Setup

Radio OS works with **any** OpenAI-compatible LLM provider.  Configure your provider in each station's `manifest.yaml` or via the GUI settings panel.

<details>
<summary><b>OpenAI / ChatGPT</b></summary>

Set your API key as the environment variable `OPENAI_API_KEY`, or add it in the GUI under *Settings → Environment*.

```yaml
llm:
  provider: openai
  api_key_env: OPENAI_API_KEY
models:
  producer: gpt-4o
  host: gpt-4o
```
</details>

<details>
<summary><b>Ollama (free, local)</b></summary>

Install Ollama via **option 3** in the launcher, or manually from [ollama.ai](https://ollama.ai). Then pull a model:

```bash
ollama pull qwen3:8b
```

```yaml
llm:
  provider: ollama
models:
  producer: qwen3:8b
  host: llama3.1:8b
```
</details>

<details>
<summary><b>Anthropic Claude / Google Gemini</b></summary>

Set the relevant API key environment variable and update `manifest.yaml`:

```yaml
# Claude
llm:
  provider: anthropic
  api_key_env: ANTHROPIC_API_KEY

# Gemini
llm:
  provider: google
  api_key_env: GOOGLE_API_KEY
```
</details>

---

## TTS (Text-to-Speech)

Radio OS ships with **Kokoro** TTS built-in — no extra install needed.

Optional alternatives:
- **Piper** — free, offline (install via **option 4** in the launcher)
- **ElevenLabs** / **OpenAI TTS** — cloud-based, configure API keys in manifest

---

## Creating a Station

Use the built-in wizard in the GUI, or manually create:

```
stations/mystation/
  ├── manifest.yaml
  └── mystation.py     # optional custom entrypoint
```

See `templates/default_manifest.yaml` for all configuration options.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Python not found` | Install Python 3.10+ and make sure it's on your PATH |
| `Dependencies failed` | Check internet · Linux: `sudo apt install python3-tk libsndfile1 portaudio19-dev` |
| `No audio` | Verify Kokoro or Piper is configured · Check audio device in GUI settings |
| `Station won't start` | Check `stations/<id>/runtime.log` · Verify your LLM provider is reachable |
| `Out of memory` | Use smaller models (8B) · Lower `max_tokens` in manifest · Try cloud APIs |

For more details, see the `docs/` folder.

---

## Plugin Development

Feed plugins are simple Python modules in `plugins/`:

```python
PLUGIN_NAME = "my_feed"
IS_FEED = True
DEFAULT_CONFIG = {"poll_interval": 300}

def feed_worker(stop_event, mem, cfg, runtime=None):
    from your_runtime import event_q, StationEvent
    while not stop_event.is_set():
        event_q.put(StationEvent(
            role="feed", source="my_feed",
            content_blocks=[{"text": "Hello!"}]
        ))
        time.sleep(cfg["poll_interval"])
```

---

## Contributing

We welcome contributions! See **[CONTRIBUTING.md](CONTRIBUTING.md)** for:

- Development setup
- Plugin development guide with example code
- Code style and conventions
- Pull request process

---

## License

**GPL-3.0** — free, open source, and hackable forever.  
© 2026 Evan Pelletier. See [LICENSE](LICENSE).

### Dependencies
- [Piper TTS](https://github.com/rhasspy/piper) — MIT
- [FFmpeg](https://ffmpeg.org/) — LGPL
- Voice models — see [Piper Voices](https://huggingface.co/rhasspy/piper-voices/) for per-model licenses
