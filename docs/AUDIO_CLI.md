# Audio CLI — Voice-Command Interface for Radio OS

> **Added in v2.1** · Shell-level module · `audio_cli.py`

Audio CLI is a voice-activated command interface for Radio OS that you can enable or disable at any time. When enabled, say **"Hey Radio"** to start a session, issue natural-language commands, and say **"Thanks Radio"** to end. It runs at the shell level (not as a plugin) and works in both **tkinter desktop** and **headless web** modes.

---

## Quick Start

### Web / Headless Mode (recommended)
```bash
python audio_cli.py --web http://127.0.0.1:7800
```

### Introspect UI State (debug)
```bash
python audio_cli.py --web http://127.0.0.1:7800 --introspect
```

### Test Microphone & STT
```bash
python audio_cli.py --test-mic
```

### Integrated (via shell_bookmark.py)
Audio CLI is started automatically by `shell_bookmark.py` when the shell launches. No separate process needed.

---

## How It Works

```
Microphone → Wake Detection → STT → LLM Command Parser → Dispatcher → UI / API
                                                              ↓
                                                     TTS Narration ← Voice Output
                                                     (with audio ducking)
```

1. **Wake listener** — When Audio CLI is enabled, a mic thread listens for the wake phrase ("Hey Radio").
2. **Command capture** — Once activated, records speech until silence is detected.
3. **Speech-to-Text** — Transcribes audio via whisper.cpp (preferred) or SpeechRecognition fallback.
4. **LLM command parser** — Sends transcript + current UI state to an LLM with a structured system prompt. The LLM returns a JSON response with actions and narration.
5. **Command dispatcher** — Executes actions against the shell (tkinter) or web API (REST).
6. **TTS narration** — Speaks the response via `voice_provider`, ducking station audio while speaking.

---

## Architecture

Audio CLI is composed of these internal classes:

| Class | Purpose |
|---|---|
| `AudioCLISession` | Top-level lifecycle manager — mic listening, session state, context routing |
| `MicStream` | Persistent 16 kHz mono mic input with ring buffer |
| `STTEngine` | Speech-to-text (whisper.cpp or SpeechRecognition) |
| `CommandParser` | Sends transcript + UI state to LLM, parses structured JSON response |
| `NarrationEngine` | TTS output via `voice_provider` with audio ducking and barge-in control |
| `UIIntrospector` | Reads tkinter widget tree for current UI state (desktop mode) |
| `WebIntrospector` | Reads UI state via REST API (web mode) |
| `CommandDispatcher` | Executes actions against the tkinter shell |
| `WebCommandDispatcher` | Executes actions via REST API (port 7800) |
| `GameCommandDispatcher` | Direct FTB game control channel (port 7555) |
| `BrowserController` | Opens/closes the system browser for the web UI |
| `LocalAudioPlayer` | Local station audio playback (web mode) |
| `CLIAction` / `CLIResponse` | Structured data types for parsed LLM output |

---

## Dual-Context Routing

Audio CLI has **two independent command channels**:

| Context | Port | Controls |
|---|---|---|
| **Runtime** | 7800 | Station management, settings, plugin toggling, feed config, browser, audio |
| **Game** | 7555 | FTB game actions — wizard, decisions, race day, tabs, hire/fire, R&D |

Switch between them by saying:
- *"Switch to the game"* / *"Game controls"* / *"FTB controls"*
- *"Switch to runtime"* / *"Back to the radio"* / *"Station controls"*

---

## Supported Actions

### Station Control
| Voice Command | Action |
|---|---|
| *"Start From the Backmarker"* | Launch a station by name |
| *"Stop the station"* | Stop the running station |
| *"Play Vibez FM"* | Start a station |

### Navigation & UI
| Voice Command | Action |
|---|---|
| *"Go to settings"* | Navigate shell views |
| *"Show me the team tab"* | Switch game tabs |
| *"Open the browser"* / *"Go headless"* | Show/hide web UI |

### Game Control (FTB)
| Voice Command | Action |
|---|---|
| *"Start a new game"* | Open the startup wizard |
| *"Advance the day"* | Progress one in-game day |
| *"Watch the race live"* | Start live race viewing |
| *"Save the game"* | Save current progress |
| *"Who are my drivers?"* | Query game state (answered from data, no navigation) |
| *"What's our budget?"* | Direct data answer |
| *"Hire John Smith"* | Hire a free agent |
| *"Show the standings"* | Query championship data |

### Plugin Management
| Voice Command | Action |
|---|---|
| *"List plugins"* | Show all plugins and status |
| *"Enable RSS"* / *"Turn off Twitter"* | Toggle feeds |
| *"Set the RSS URL to..."* | Configure feed parameters |

### Audio & Mode
| Voice Command | Action |
|---|---|
| *"Play audio"* / *"Mute"* / *"Stop audio"* | Control local playback |
| *"Switch to speaker mode"* | Disable barge-in (mic muted during TTS) |
| *"I'm wearing headphones"* | Enable barge-in (mic stays live during TTS) |
| *"Switch to web mode"* | Change interface mode |
| *"Restart Radio OS"* | Full application restart |

### Verbosity Levels
| Voice Command | Level | Behavior |
|---|---|---|
| *"Be brief"* / *"Minimal mode"* | `minimal` | 1–8 words max |
| *"Concise mode"* | `concise` | One short sentence (default) |
| *"Give me more detail"* | `standard` | 2–3 sentences |
| *"Broadcast mode"* | `broadcast` | Immersive, dramatic narration |
| *"Debug mode"* | `diagnostic` | Structured state dump |

### Audio Keyboard (Voice Dictation)
Say *"Type something"* or *"Audio keyboard"* to enter dictation mode for free-form text input (naming saves, entering URLs, etc.).

| Voice Command | Action |
|---|---|
| *"Enter"* / *"Submit"* / *"Done"* | Submit the current text |
| *"Clear text"* / *"Clear"* / *"Start over"* / *"Erase"* | Clear the buffer and dictate fresh |
| *"Cancel"* / *"Exit keyboard"* | Leave dictation mode without submitting |

### Command Chaining
Compound commands are split into ordered action sequences with automatic 2-second delays. Conditional execution (`if_success` / `if_fail`) is supported for multi-step workflows.

---

## Configuration

Audio CLI reads settings from `~/.radioOS/config.json` under the `audio_cli` key:

```json
{
  "audio_cli": {
    "wake_phrase": "hey radio",
    "exit_phrase": "thanks radio",
    "silence_duration_sec": 2.2,
    "min_utterance_sec": 0.6,
    "audio_output_mode": "speaker",
    "verbosity": "concise",
    "game_port": 7555
  }
}
```

| Key | Default | Description |
|---|---|---|
| `wake_phrase` | `"hey radio"` | Phrase to activate a session |
| `exit_phrase` | `"thanks radio"` | Phrase to end a session |
| `silence_duration_sec` | `2.2` | Seconds of silence to end a voice capture |
| `min_utterance_sec` | `0.6` | Minimum speech duration before silence can end capture |
| `audio_output_mode` | `"speaker"` | `"speaker"` (no barge-in) or `"headphone"` (barge-in enabled) |
| `verbosity` | `"concise"` | Default verbosity level |
| `game_port` | `7555` | Port for direct FTB game communication |

---

## Audio Ducking

When Audio CLI speaks, station audio is automatically ducked (lowered to 20% volume) so narration is clearly audible. A flag file (`.audio_cli_suppress`) signals the ducking state to the station runtime. Volume is restored immediately after narration finishes.

---

## Dependencies

- **Required**: `numpy`
- **Recommended**: `sounddevice`, `soundfile` (for mic capture and audio I/O)
- **STT**: whisper.cpp (preferred) or `SpeechRecognition` (fallback)
- **TTS**: `voice_provider.py` (Kokoro / system TTS)
- **LLM**: `model_provider.py` (for command parsing)

---

## Technical Notes

- Audio CLI is **not** a plugin — it runs at the shell level with direct access to UI state, station processes, and audio routing.
- The mic stream uses a 15-second ring buffer at 16 kHz mono.
- RMS silence threshold is `0.008` — speech below this is treated as silence.
- Command capture max duration is 10 seconds per utterance.
- The LLM always outputs structured JSON (never free-form text), enforced by the system prompt.
- In speaker mode, the mic is physically muted during TTS to prevent feedback loops.
- Game state queries (drivers, budget, car, etc.) are answered directly from the state snapshot without navigating tabs — keeping the UI undisturbed.
