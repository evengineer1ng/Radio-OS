# Contributing to Radio OS

Thanks for your interest in contributing to Radio OS! This guide will help you get set up and productive quickly.

---

## Table of Contents

- [Development Setup](#development-setup)
- [Project Architecture](#project-architecture)
- [How to Contribute](#how-to-contribute)
- [Writing a Plugin](#writing-a-plugin)
- [Code Style](#code-style)
- [Submitting Changes](#submitting-changes)
- [Reporting Bugs](#reporting-bugs)
- [Community](#community)

---

## Development Setup

### Prerequisites

- **Python 3.10+** (3.12 recommended)
- **Git**
- **tkinter** — usually bundled with Python; on Linux: `sudo apt install python3-tk`

### Clone & Install

```bash
git clone https://github.com/evengineer1ng/Radio-OS.git
cd Radio-OS

# Create a virtual environment
python3 -m venv radioenv
source radioenv/bin/activate        # macOS/Linux
# radioenv\Scripts\Activate.ps1    # Windows PowerShell

# Install core dependencies
pip install -r requirements.txt
```

### Run Radio OS

```bash
# Interactive launcher (recommended)
./mac.sh              # macOS / Linux
windows.bat           # Windows

# Or launch the desktop shell directly
python shell_bookmark.py --desktop
```

### Run Tests

```bash
pip install pytest
pytest tests/ -v
```

---

## Project Architecture

```
shell_bookmark.py      ← Desktop UI & process manager (was shell.py)
bookmark.py            ← Station runtime engine (was runtime.py)
launcher.py            ← Station process launcher
your_runtime.py        ← Plugin compatibility shim

model_provider.py      ← LLM provider abstraction (Ollama, OpenAI, Anthropic, Google)
voice_provider.py      ← TTS provider abstraction (Piper, Kokoro, ElevenLabs)
context_engine.py      ← Per-character context lookup (API, DB, text/RAG)

plugins/               ← Feed plugins and UI widgets
  meta/                ← Meta plugins (radio_station, from_the_backmarker)
  rss.py, reddit.py …  ← Feed source plugins
  flows.py             ← Media playback awareness

stations/              ← Per-station configs and entrypoints
  <station_id>/
    manifest.yaml      ← Station configuration
    station.sqlite     ← Station database
    station_memory.json

voices/                ← TTS voice models (downloaded via setup.py)
web/                   ← Svelte web frontend + FastAPI backend
docs/                  ← Developer documentation
templates/             ← Manifest templates
```

### Key Concepts

- **Queues**: The runtime communicates via in-process queues: `event_q`, `ui_q`, `ui_cmd_q`, `dj_q`, `subtitle_q`. These are the primary pub/sub channels.
- **Manifest**: Each station has a `manifest.yaml` that configures models, pacing, feeds, and scheduling.
- **Meta plugins**: High-level plugins in `plugins/meta/` that control core AI behavior (radio station mode vs. game narrator mode).
- **Feed plugins**: Modules in `plugins/` that pull content from external sources and push `StationEvent` objects onto `event_q`.

---

## How to Contribute

### Good First Issues

Look for issues labeled [`good first issue`](https://github.com/evengineer1ng/Radio-OS/labels/good%20first%20issue) — these are scoped tasks with clear acceptance criteria.

### Areas We Need Help

| Area | Examples |
|------|----------|
| **Feed plugins** | New content sources (Mastodon, Hacker News, YouTube, Twitch, etc.) |
| **Platform support** | Linux media control (MPRIS2/D-Bus), Wayland, etc. |
| **TTS voices** | New voice model integrations, voice quality improvements |
| **Web UI** | Svelte components, mobile responsiveness, accessibility |
| **Documentation** | User guides, plugin tutorials, API docs, video walkthroughs |
| **Testing** | Unit tests, integration tests, cross-platform validation |
| **Bug fixes** | Check the issue tracker for reported bugs |

---

## Writing a Plugin

Feed plugins are the easiest way to contribute. Create a new file in `plugins/`:

```python
"""
plugins/hacker_news.py — Hacker News feed plugin
"""
import time
import requests

PLUGIN_NAME = "hacker_news"
PLUGIN_DESC = "Fetch top stories from Hacker News."
IS_FEED = True

FEED_DEFAULTS = {
    "enabled": False,
    "poll_sec": 300,
    "priority": 60,
    "story_count": 5,
}

def feed_worker(stop_event, mem, cfg, runtime=None):
    """Main feed loop — runs in its own thread."""
    from your_runtime import event_q, StationEvent, log

    seen = set()

    while not stop_event.is_set():
        try:
            resp = requests.get(
                "https://hacker-news.firebaseio.com/v0/topstories.json",
                timeout=10
            )
            story_ids = resp.json()[:cfg.get("story_count", 5)]

            for sid in story_ids:
                if sid in seen:
                    continue
                seen.add(sid)

                detail = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                    timeout=10
                ).json()

                event_q.put(StationEvent(
                    role="feed",
                    source="hacker_news",
                    content_blocks=[{
                        "text": f"{detail.get('title', 'Untitled')} — "
                                f"{detail.get('score', 0)} points on Hacker News",
                        "url": detail.get("url", ""),
                    }],
                    priority=cfg.get("priority", 60),
                ))

            log("HN", f"Fetched {len(story_ids)} stories")

        except Exception as e:
            log("HN", f"Error: {e}")

        stop_event.wait(cfg.get("poll_sec", 300))
```

### Plugin Checklist

- [ ] `PLUGIN_NAME`, `PLUGIN_DESC`, `IS_FEED` module constants
- [ ] `FEED_DEFAULTS` dict with `"enabled": False` as default
- [ ] `feed_worker(stop_event, mem, cfg, runtime=None)` function
- [ ] Import from `your_runtime` (not `bookmark` or `runtime` directly)
- [ ] Respect `stop_event` — check it in your loop, use `stop_event.wait()` instead of `time.sleep()`
- [ ] Handle errors gracefully — don't crash the thread
- [ ] Keep it single-file, single-responsibility

For **UI widgets**, implement `register_widgets(registry, runtime_stub)` instead.

---

## Code Style

- **Indentation**: 4 spaces (no tabs)
- **Line length**: 100 characters soft limit, 120 hard limit
- **Docstrings**: Required for all public functions, classes, and modules
- **Imports**: Standard library → third-party → local, separated by blank lines
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE` for constants
- **Type hints**: Encouraged but not required (especially for plugin contributions)
- **No blocking calls** on the main thread — use threads and push events onto queues

### Things to Avoid

- Don't rename or remove global queues (`event_q`, `ui_q`, etc.) — plugins depend on them
- Don't change `your_runtime.py` exports — it's a compatibility shim
- Don't change manifest key structure without updating `launcher.py` and `shell_bookmark.py`

---

## Submitting Changes

### Branch Naming

```
feature/my-new-plugin
fix/race-day-crash
docs/plugin-tutorial
```

### Pull Request Process

1. **Fork** the repo and create a feature branch from `main`
2. **Make your changes** with clear, focused commits
3. **Test** on your platform — note which OS you tested on in the PR
4. **Open a PR** with:
   - A clear title describing the change
   - What the change does and why
   - Screenshots/recordings for UI changes
   - Steps to test
5. **Respond to review feedback** — we aim to review within a few days

### Commit Messages

Use clear, descriptive commit messages:

```
feat(plugins): add Hacker News feed plugin
fix(ftb): prevent crash when race state is None
docs: add plugin development tutorial
chore: update dependencies for Python 3.13
```

---

## Reporting Bugs

Use the [bug report template](https://github.com/evengineer1ng/Radio-OS/issues/new?template=bug_report.md) and include:

- OS and Python version
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs (`stations/<id>/runtime.log`)
- Screenshots if applicable

---

## Community

- **Issues**: [GitHub Issues](https://github.com/evengineer1ng/Radio-OS/issues) for bugs and feature requests
- **Discussions**: [GitHub Discussions](https://github.com/evengineer1ng/Radio-OS/discussions) for questions and ideas

---

## License

By contributing, you agree that your contributions will be licensed under the [GPL-3.0 License](LICENSE).

Thank you for helping make Radio OS better! 🎙️
