# Radio OS — Flutter Native App Design Specification

**Target**: Raspberry Pi 5 dedicated radio unit
**Platform**: Flutter (Dart) — Linux ARM64 primary, iOS/Android secondary
**Radio OS Version**: 1.06+
**Author**: Design spec generated from full codebase audit
**Status**: DRAFT v1.0

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Hardware & Platform Constraints](#3-hardware--platform-constraints)
4. [Network Layer — API Client](#4-network-layer--api-client)
5. [Audio Engine](#5-audio-engine)
6. [Voice Command System](#6-voice-command-system)
7. [Shell Layer — Station Browser](#7-shell-layer--station-browser)
8. [Station Runtime Dashboard](#8-station-runtime-dashboard)
9. [Per-Station UI Modules](#9-per-station-ui-modules)
10. [Settings & Configuration](#10-settings--configuration)
11. [State Management](#11-state-management)
12. [Navigation & Routing](#12-navigation--routing)
13. [Theming & Visual Design](#13-theming--visual-design)
14. [Offline & Edge Behavior](#14-offline--edge-behavior)
15. [File & Directory Structure](#15-file--directory-structure)
16. [Dependencies](#16-dependencies)
17. [Testing Strategy](#17-testing-strategy)
18. [Build & Deployment](#18-build--deployment)
19. [Appendices](#19-appendices)

---

## 1. Executive Summary

Radio OS is a desktop-first, content-agnostic AI "radio" runtime composed of three layers:

| Layer | Python Module | What it does |
|-------|---------------|-------------|
| **Shell** | `shell_bookmark.py` | Station browser, settings, process manager |
| **Station Engine** | `bookmark.py` | Per-station runtime: feeds → events → LLM → TTS → audio |
| **Plugins** | `plugins/*.py` | Feed workers, game simulations, audio engines, UI widgets |

The Flutter app replaces the existing tkinter desktop shell (`shell_bookmark.py`) and the Svelte web UI (`web/src/`) with a single native application optimized for a Raspberry Pi 5 powered radio unit with touchscreen. It communicates exclusively over HTTP REST and WebSocket to the two existing FastAPI servers:

| Server | Port | Scope |
|--------|------|-------|
| **Shell Server** (`web_server.py`) | 7800 | Station orchestration, settings, plugin management, audio streaming |
| **Plugin Server** (`ftb_web_server.py`) | 7555 | Game-specific state & commands (FTB, future per-plugin servers) |

The Python backend runs on the same Pi 5 — both servers and the station subprocess are local processes. The Flutter app is a local-first thick client, not a remote thin client.

---

## 2. System Architecture

### 2.1 High-Level Topology

```
┌──────────────────────────────────────────────────────────────┐
│                    RASPBERRY PI 5                             │
│                                                              │
│  ┌────────────────────┐    ┌────────────────────────────┐    │
│  │  Flutter App        │    │  Python Backend            │    │
│  │  (Linux ARM64)      │    │                            │    │
│  │                     │    │  shell_bookmark.py          │    │
│  │  ┌───────────────┐ │REST│  ┌──────────────────────┐  │    │
│  │  │ API Client    │◄├────┤► │ web_server.py :7800  │  │    │
│  │  └───────┬───────┘ │    │  └──────────┬───────────┘  │    │
│  │          │         │    │             │               │    │
│  │  ┌───────▼───────┐ │REST│  ┌──────────▼───────────┐  │    │
│  │  │ Game Client   │◄├────┤► │ ftb_web_server :7555 │  │    │
│  │  └───────┬───────┘ │    │  └──────────────────────┘  │    │
│  │          │         │    │                            │    │
│  │  ┌───────▼───────┐ │ WS │  ┌──────────────────────┐  │    │
│  │  │ Audio WS      │◄├────┤► │ AudioBridge          │  │    │
│  │  │ Event WS      │ │    │  │ (WAV pipe → stream)  │  │    │
│  │  └───────────────┘ │    │  └──────────────────────┘  │    │
│  │                     │    │                            │    │
│  │  ┌───────────────┐ │    │  ┌──────────────────────┐  │    │
│  │  │ Voice Input   │ │    │  │ bookmark.py          │  │    │
│  │  │ (Mic / STT)   │ │    │  │ (station runtime)    │  │    │
│  │  └───────────────┘ │    │  └──────────────────────┘  │    │
│  │                     │    │                            │    │
│  │  ┌───────────────┐ │    │  ┌──────────────────────┐  │    │
│  │  │ Audio Output  │ │    │  │ plugins/*.py         │  │    │
│  │  │ (Speaker/DAC) │ │    │  │ (feeds, games, etc.) │  │    │
│  │  └───────────────┘ │    │  └──────────────────────┘  │    │
│  └────────────────────┘    └────────────────────────────┘    │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Touchscreen  │  │ Speaker/DAC  │  │ Mic (USB/I2S)     │  │
│  │ (7" / 10")   │  │ (3.5mm/USB)  │  │ (wake word)       │  │
│  └──────────────┘  └──────────────┘  └───────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Process Model

1. **Python backend** starts first (systemd service or launcher script)
   - `web_server.py` launches on port 7800 (the Shell Server)
   - When a station starts, `StationManager` spawns `bookmark.py` as a subprocess with `RADIO_OS_HEADLESS=1`
   - The station's plugin server (e.g. `ftb_web_server.py`) starts on port 7555 inside the station process
2. **Flutter app** starts second (either auto-launched by the same systemd unit, or manually)
   - Connects to `http://127.0.0.1:7800` for orchestration
   - Connects to `ws://127.0.0.1:7800/ws/audio/{station_id}` for audio streaming
   - Connects to `ws://127.0.0.1:7800/ws/station/{station_id}` for proxied event stream
   - Connects to `http://127.0.0.1:7555` for direct game state (when FTB or similar is active)

### 2.3 Data Flow: Audio Pipeline

```
bookmark.py (TTS) → WAV files → .audio_pipe/ → AudioBridge.poll_new_segments()
    → ws/audio/{id} → Flutter WebSocket → PCM decode → AudioPlayer → Speaker
```

The audio payload format over WebSocket is binary:
```
[4 bytes: JSON metadata length (big-endian uint32)]
[N bytes: JSON metadata {"voice","speaker","text","duration","sr","ts"}]
[M bytes: WAV file data (16-bit PCM, variable sample rate)]
```

### 2.4 Data Flow: Game State

```
ftb_game.py (tick) → ftb_state_db (SQLite) → ftb_web_server.py (serialize)
    → GET /api/state → Flutter HTTP → Riverpod state → UI rebuild
```

Real-time events via WebSocket:
```
ftb_web_server.py → ws/live → web_server.py proxy → ws/station/{id}
    → Flutter WebSocket → event dispatcher → state update / notification / audio event
```

---

## 3. Hardware & Platform Constraints

### 3.1 Raspberry Pi 5 Specifications

| Spec | Value | Impact on Flutter |
|------|-------|-------------------|
| CPU | Cortex-A76 4-core @ 2.4 GHz | Comfortable for Flutter Linux; avoid jank on complex lists |
| RAM | 4 GB or 8 GB | Budget ~200 MB for Flutter app |
| GPU | VideoCore VII | Vulkan/OpenGL ES 3.1; Flutter Impeller backend should work |
| Display | 7" 800×480 or 10.1" 1280×800 | Design for **800×480 minimum** |
| Audio output | 3.5mm jack, HDMI, USB DAC, I2S HAT | Use ALSA/PulseAudio via `just_audio` |
| Mic input | USB mic or I2S MEMS | Access via platform channel → ALSA |
| Network | Ethernet + WiFi 5 | Localhost only for API; WiFi for LLM API calls |
| Storage | microSD or NVMe (via HAT) | Station DBs + voices + models live here |

### 3.2 Display Design Targets

| Screen | Resolution | DPI | Orientation |
|--------|-----------|-----|-------------|
| Primary | 800×480 (7" official) | ~133 | Landscape |
| Alt | 1280×800 (10.1") | ~149 | Landscape |
| Dev/Debug | 1920×1080 (HDMI monitor) | Variable | Landscape |

All layouts must be fluid and work at 800×480. Use `LayoutBuilder` and breakpoints, never fixed pixel widths. Touch targets minimum 48×48 dp.

### 3.3 Flutter Linux Prerequisites

- Flutter Linux ARM64 (flutter.dev Linux desktop target)
- Impeller rendering backend (preferred; fallback to Skia if Impeller has Pi 5 issues)
- GTK runner (default for Flutter Linux desktop)
- PulseAudio or PipeWire for audio output
- ALSA for low-level mic access (wake word detection)

---

## 4. Network Layer — API Client

### 4.1 Shell Server Client (Port 7800)

A Dart service class wrapping all REST endpoints from `web_server.py`. This is the **primary** API surface.

#### Station Management

| Method | Endpoint | Dart Method |
|--------|----------|-------------|
| GET | `/api/health` | `healthCheck()` |
| GET | `/api/stations` | `listStations()` |
| POST | `/api/stations/{id}/launch` | `launchStation(id)` |
| POST | `/api/stations/{id}/stop` | `stopStation(id)` |
| GET | `/api/stations/{id}/status` | `getStationStatus(id)` |
| GET | `/api/stations/{id}/log` | `getStationLog(id, lines)` |
| POST | `/api/stations/create` | `createStation(manifest)` |

#### Settings (6 sections mirroring shell_bookmark.py tabs)

| Method | Endpoint | Dart Method |
|--------|----------|-------------|
| GET | `/api/settings/general` | `getGeneralSettings()` |
| POST | `/api/settings/general` | `updateGeneralSettings(data)` |
| GET | `/api/settings/models` | `getModelSettings()` |
| POST | `/api/settings/models` | `updateModelSettings(data)` |
| GET | `/api/settings/voices` | `getVoiceSettings()` |
| POST | `/api/settings/voices` | `updateVoiceSettings(data)` |
| GET | `/api/settings/plugins` | `getPluginSettings()` |
| POST | `/api/settings/plugins` | `updatePluginSettings(data)` |
| GET | `/api/settings/visual` | `getVisualSettings()` |
| POST | `/api/settings/visual` | `updateVisualSettings(data)` |
| GET | `/api/settings/storage` | `getStorageSettings()` |
| POST | `/api/settings/storage` | `updateStorageSettings(data)` |

#### Plugin & Feed Control

| Method | Endpoint | Dart Method |
|--------|----------|-------------|
| GET | `/api/plugins` | `listPlugins()` |
| GET | `/api/meta_plugins` | `listMetaPlugins()` |
| GET | `/api/voices` | `listVoices()` |
| GET | `/api/stations/{id}/feeds` | `listFeeds(stationId)` |
| POST | `/api/stations/{id}/feeds/{feed}/toggle` | `toggleFeed(stationId, feed)` |
| POST | `/api/stations/{id}/feeds/{feed}/config` | `configureFeed(stationId, feed, cfg)` |
| POST | `/api/stations/{id}/plugin/{name}/command` | `pluginCommand(stationId, plugin, cmd)` |

#### Storage & Save Management

| Method | Endpoint | Dart Method |
|--------|----------|-------------|
| GET | `/api/storage/usage` | `getStorageUsage()` |
| POST | `/api/storage/cleanup` | `cleanupStorage()` |

### 4.2 Game Client (Port 7555)

A separate Dart service class wrapping the FTB plugin server endpoints. Only active when a game station is running.

#### Core State

| Method | Endpoint | Dart Method |
|--------|----------|-------------|
| GET | `/api/state` | `getGameState()` |
| GET | `/api/full_state` | `getFullGameState()` |
| GET | `/api/subtitle` | `getSubtitle()` |
| GET | `/api/audio_state` | `getAudioState()` |
| GET | `/api/ui_screen` | `getUIScreen()` |
| GET | `/api/snapshot` | `getSnapshot()` |

#### Game Commands

| Method | Endpoint | Dart Method |
|--------|----------|-------------|
| POST | `/api/command` | `sendCommand(cmd)` |
| POST | `/api/ui_command` | `sendUICommand(action, payload)` |
| POST | `/api/navigate` | `navigate(screen)` |
| POST | `/api/tick` | `tick(mode, count)` |

#### Game-Specific Operations

| Category | Endpoints | Dart Methods |
|----------|-----------|-------------|
| Race Day | `/api/race_day/*` (respond, start_live, pause, complete) | `raceDayRespond()`, `raceDayStartLive()`, etc. |
| Sponsors | `/api/sponsor/*` (accept, decline) | `acceptSponsor()`, `declineSponsor()` |
| Parts | `/api/parts/*` (buy, sell, equip) | `buyPart()`, `sellPart()`, `equipPart()` |
| Staff | `/api/staff/*` (hire, fire, contract) | `hireAgent()`, `fireStaff()`, etc. |
| R&D | `/api/rd/*` (start, cancel) | `startRD()`, `cancelRD()` |
| Infrastructure | `/api/infrastructure/*` (upgrade, sell) | `upgradeInfra()`, `sellInfra()` |
| Save/Load | `/api/new_game`, `/api/load_game`, `/api/save_game`, `/api/saves`, `/api/autosave` | Full CRUD |
| Data Queries | `/api/ftb_data/query_*` | `queryDrivers()`, `queryTeams()`, etc. |

### 4.3 WebSocket Connections

```dart
class RadioWebSocketManager {
  // Audio stream — binary WAV segments
  WebSocketChannel? _audioWs; // ws://127.0.0.1:7800/ws/audio/{stationId}

  // Event stream — JSON messages (proxied from station's ws/live)
  WebSocketChannel? _eventWs; // ws://127.0.0.1:7800/ws/station/{stationId}

  // Direct plugin WS (optional, for lower latency game events)
  WebSocketChannel? _pluginWs; // ws://127.0.0.1:7555/ws/live
}
```

**Event WS message types** (from existing Svelte `ws.ts` / `App.svelte`):

| `type` | Payload | Action |
|--------|---------|--------|
| `state_update` | Full or partial game state | Merge into game state provider |
| `subtitle` | `{text}` | Update subtitle overlay |
| `notification` | `{title, body, ...}` | Push to notification center |
| `audio_event` | `{audio_type, file_path, volume, ...}` | Trigger ambient/SFX playback |
| `widget_update` | `{widget_key, data}` | Route to per-widget provider |
| `navigate` | `{screen}` | Programmatic tab switch (from Audio CLI) |
| `switch_tab` | `{tab}` | Direct tab change |
| `now_playing` | `{source, title, ...}` | Update now-playing banner |
| `pong` | — | Keepalive response |

### 4.4 Client Architecture Patterns

```dart
// Base HTTP client with retry, timeout, connection pooling
class RadioHttpClient {
  final String baseUrl;
  final Duration timeout;
  final int maxRetries;
  // Uses dio or http package with interceptors
}

// Shell client wraps RadioHttpClient for port 7800
class ShellApiClient {
  final RadioHttpClient _http;
  ShellApiClient({String host = '127.0.0.1', int port = 7800});
}

// Game client wraps RadioHttpClient for port 7555
class GameApiClient {
  final RadioHttpClient _http;
  GameApiClient({String host = '127.0.0.1', int port = 7555});
}
```

**Connection resilience**: The app must handle the backend being unavailable at startup (Pi is still booting), station crashes (process dies), and server restarts. Implement exponential backoff reconnect on all WebSocket connections, and show a connection status banner (mirroring the Svelte `conn-banner`).

---

## 5. Audio Engine

### 5.1 Architecture

The Flutter app is the **sole audio output** for the radio unit. In headless mode, `bookmark.py` writes WAV files to `.audio_pipe/`; the Shell Server's `AudioBridge` reads them and streams binary payloads over the `/ws/audio/{station_id}` WebSocket.

```dart
class RadioAudioEngine {
  // Primary: TTS voice stream from station
  late final VoiceStreamPlayer _voicePlayer;

  // Secondary: Ambient/SFX from audio events (engine sounds, crowd, stingers)
  late final AmbientAudioManager _ambient;

  // Tertiary: Music channel (ducking-aware)
  late final MusicPlayer _music;

  // Master volume, per-channel volumes, ducking state
  late final AudioMixer _mixer;
}
```

### 5.2 Voice Stream Player

Receives binary WebSocket payloads from `/ws/audio/{station_id}`:

```dart
class VoiceStreamPlayer {
  void onBinaryMessage(Uint8List payload) {
    // 1. Parse: first 4 bytes = JSON metadata length (big-endian)
    final metaLen = ByteData.sublistView(payload, 0, 4).getUint32(0);
    final metaJson = utf8.decode(payload.sublist(4, 4 + metaLen));
    final meta = jsonDecode(metaJson); // {voice, speaker, text, duration, sr, ts}
    final wavBytes = payload.sublist(4 + metaLen);

    // 2. Queue for sequential playback (segments arrive faster than real-time)
    _playbackQueue.add(AudioSegment(meta: meta, wav: wavBytes));

    // 3. Start playback if idle
    if (!_isPlaying) _playNext();
  }
}
```

Audio must play sequentially (one segment after another) to preserve TTS pacing. Buffer 2–3 segments ahead for gapless playback.

### 5.3 Ambient Audio Manager

Mirrors `ftb_audio_engine.py` and `ok_audio_engine.py`:

| Channel | FTB Usage | OK Usage | Flutter Implementation |
|---------|-----------|----------|----------------------|
| Music | Drift variants (minor/neutral/major) | Room ambient beds | Looping audio player with crossfade |
| Engine/World | Engine sounds, crash SFX | Crowd murmurs, whispers | One-shot + looping players |
| UI | Tactile feedback | Stingers (decree chime) | One-shot player |
| Narrator duck | Volume ducking signal | Volume ducking signal | Mixer volume automation |

Audio event files are served from the station's audio directory via the plugin server's `/audio/` static mount. Flutter fetches and caches them locally.

### 5.4 Ducking & Mixing

```dart
class AudioMixer {
  double masterVolume = 0.8;
  double voiceVolume = 1.0;
  double musicVolume = 0.10;     // MUSIC_VOLUME from webAudio.ts
  double musicDuckVolume = 0.02;  // MUSIC_DUCK_VOLUME
  double ambientVolume = 0.08;
  double sfxVolume = 0.30;

  bool isDucking = false; // true while TTS is playing

  void startDucking() {
    // Fade music to musicDuckVolume over 500ms
    // Fade ambient to 50% over 300ms
  }

  void stopDucking() {
    // Fade music back to musicVolume over 2000ms
    // Fade ambient back to 100% over 1000ms
  }
}
```

### 5.5 Audio Package Selection

| Purpose | Recommended Package | Why |
|---------|-------------------|-----|
| WAV playback (voice) | `just_audio` + `just_audio_linux` | Mature, supports raw PCM, Linux ARM64 |
| Ambient loops | `just_audio` (multiple instances) | Can run multiple players simultaneously |
| Low-latency SFX | `audioplayers` (fallback) | Simple one-shot playback |
| Mixing control | Custom Dart mixer layer | No existing Flutter mixer with ducking |

If `just_audio_linux` has issues on ARM64, fall back to platform channels calling ALSA/GStreamer directly.

---

## 6. Voice Command System

### 6.1 Overview

The existing `audio_cli.py` already has a **Web Mode** (`WebIntrospector` + `WebCommandDispatcher`) that operates entirely over REST against port 7800. The simplest integration path:

**Option A — Run `audio_cli.py` as a sidecar process on the Pi**
- Flutter doesn't handle STT/wake-word directly
- `audio_cli.py --web http://127.0.0.1:7800` runs headlessly
- Voice commands arrive as WebSocket events (`navigate`, `switch_tab`) that Flutter already handles
- **Recommended for v1** — zero Flutter STT code needed

**Option B — Native Flutter STT with command dispatch**
- Flutter handles wake word ("hey radio") and STT via `speech_to_text` package
- Parsed commands sent to backend via REST
- Requires reimplementing `CommandParser` + `AudioCLISession` logic in Dart
- **Recommended for v2** — better latency, no Python STT dependency

### 6.2 Option A Detail: Audio CLI Sidecar

```
[Pi Mic] → audio_cli.py (Python, Web Mode) → REST commands → web_server.py
                                              ↓
                                         WebSocket events
                                              ↓
                                      Flutter event handler
                                              ↓
                                      Navigate / Tab Switch / Command
```

The Flutter app listens for these WS message types (already defined in `App.svelte`):
- `navigate` → `{screen: "wizard" | "landing" | "loading" | "game"}`
- `switch_tab` → `{tab: "dashboard" | "team" | "car" | ...}`

Audio CLI's NarrationEngine already handles TTS output through the station's audio pipeline, so voice responses come through the same WAV WebSocket stream.

### 6.3 Option B Detail: Native Flutter Voice

```dart
class VoiceCommandService {
  // Wake word detection — always-on, low-power
  late final WakeWordDetector _wakeWord; // "hey radio"

  // STT engine — activated on wake
  late final SpeechToText _stt;

  // Command parser — intent extraction
  late final CommandParser _parser;

  // Dispatchers — routes to correct backend
  late final RuntimeDispatcher _runtime;  // port 7800
  late final GameDispatcher _game;        // port 7555

  // Active context
  CommandContext _context = CommandContext.runtime;
}
```

Wake word detection on Pi 5: Use `porcupine_flutter` (Picovoice) for always-on keyword detection with minimal CPU usage, or `vosk` for offline STT.

### 6.4 Audio CLI Persona Integration

When a station with a paired `AudioPersona` starts, the voice system loads the persona's:
- System prompt overlay (shapes LLM responses)
- Custom greeting/farewell
- Voice override (TTS voice selection)
- Phrase hints (STT bias)
- Ambient narration hooks

In Option A, this is handled entirely by `audio_cli.py`. In Option B, the Flutter app would need to call a backend endpoint to get persona metadata and apply voice/STT hints locally.

---

## 7. Shell Layer — Station Browser

### 7.1 Station Carousel

Replaces `shell_bookmark.py`'s `RadioShell` class. The station browser is the app's home screen.

```
┌─────────────────────────────────────────────┐
│  RADIO OS                    ⚙️  🔊  📡     │
│─────────────────────────────────────────────│
│                                             │
│   ◄  [Station Card]  [Station Card]  ►     │
│       (active/glow)   (inactive)            │
│                                             │
│   From the Backmarker   Oracle Kingdom      │
│   🏎️ Racing Sim         👑 Social Sim       │
│   ● RUNNING              ○ Stopped          │
│                                             │
│─────────────────────────────────────────────│
│  [▶ Launch]  [⏹ Stop]  [📋 Log]  [✏️ Edit] │
│─────────────────────────────────────────────│
│                                             │
│  Now Playing: Kai — "Championship update..."│
│  ▁▂▃▅▆▇▅▃▂▁  (waveform visualization)     │
│                                             │
│  💬 "The gap to P3 is closing, and..."      │
│                                             │
└─────────────────────────────────────────────┘
```

**Data source**: `GET /api/stations` returns list of station manifests with status.

**Station Card Widget**:
```dart
class StationCard {
  final String id;
  final String name;
  final String category;
  final String logoPath;
  final String metaPlugin;  // "ftb_narrator_plugin", "ok_narrator_plugin", "radio_station"
  final StationStatus status; // stopped, starting, running, error
}
```

### 7.2 Station Types & Routing

The `meta_plugin` field in the station manifest determines which UI module loads when a station is active:

| `meta_plugin` | Station Type | UI Module |
|---------------|-------------|-----------|
| `ftb_narrator_plugin` | Racing Management (FTB) | `FTBGameModule` |
| `ok_narrator_plugin` | Oracle Kingdom | `OracleKingdomModule` |
| `radio_station` | General Radio (VibezFM, FlowFM, etc.) | `RadioStationModule` |
| (future) `neikos_narrator` | Neikos: Hundred Islands | `NeikosModule` |

### 7.3 Station Wizard

Mirrors `shell_bookmark.py`'s `StationWizard` for creating new stations:

1. **Name & Category** — text fields
2. **Meta Plugin** — dropdown (from `GET /api/meta_plugins`)
3. **Model Configuration** — provider + model dropdowns for producer/host/navigator
4. **Voice Configuration** — voice selection per role (from `GET /api/voices`)
5. **Feed Selection** — toggles for available feed plugins
6. **Review & Create** — sends manifest to `POST /api/stations/create`

---

## 8. Station Runtime Dashboard

### 8.1 Universal Runtime Bar

Present at the bottom of every station view (replaces Svelte's `tab-nav`):

```
┌─────────────────────────────────────────────┐
│  📡 From the Backmarker    ● Connected      │
│─────────────────────────────────────────────│
│                                             │
│          [ STATION-SPECIFIC CONTENT ]       │
│                                             │
│─────────────────────────────────────────────│
│  💬 "Lap 42 of 58 and the pressure..."     │  ← Subtitle overlay
│─────────────────────────────────────────────│
│  🏠  👥  🏎️  🔧  🏁  📡  💰  🤝  📊  ⚙️  │  ← Tab bar
└─────────────────────────────────────────────┘
```

### 8.2 Subtitle System

Mirrors `bookmark.py`'s `subtitle_q` → word-by-word subtitle pacing:

```dart
class SubtitleOverlay extends StatefulWidget {
  // Receives subtitle text updates from WebSocket
  // Displays with fade-in animation
  // Auto-hides after text stops updating for 3 seconds
  // Positioned as a floating bar above the tab navigation
  // Style: dark translucent background, white text, rounded corners
}
```

### 8.3 Now Playing Banner

Shows current TTS speaker + text preview + optional waveform visualization:

```dart
class NowPlayingBanner {
  final String speaker;    // "Kai", "Court Herald", etc.
  final String voiceId;    // "am_adam", "bf_emma"
  final String textPreview;
  final bool isPlaying;
  // Optional: simple waveform bars animation during playback
}
```

### 8.4 Notification Center

Mirrors `shell_bookmark.py`'s notification system and Svelte's `NotificationCenter.svelte`:

```dart
class NotificationItem {
  final String id;
  final String title;
  final String body;
  final String category; // "race_result", "sponsor_offer", "contract", "system"
  final DateTime timestamp;
  final bool read;
  final Map<String, dynamic>? actionPayload; // for actionable notifications
}
```

---

## 9. Per-Station UI Modules

### 9.1 FTB Game Module (From the Backmarker)

This is the most complex UI, mirroring the Svelte `web/src/` SPA entirely. It maps to the 18 tabs defined in `App.svelte`.

#### Tab Structure

| Tab ID | Icon | Name | Data Source |
|--------|------|------|-------------|
| `dashboard` | 🏠 | Home | `/api/state` — team overview, metrics, events |
| `team` | 👥 | Team | Drivers roster, engineer stats, staff contracts |
| `car` | 🏎️ | Car | Parts inventory, car setup, performance stats |
| `development` | 🔧 | Dev | R&D projects, technology tree |
| `raceops` | 🏁 | Race | Race day flow, qualifying, strategy |
| `pbp` | 📡 | PBP | Live play-by-play, lap standings, telemetry |
| `finance` | 💰 | Finance | Budget, income/expenses, prize money |
| `sponsors` | 🤝 | Sponsors | Sponsor offers, active deals |
| `promotion` | 📈 | Promotion | League standings, promotion/relegation |
| `stats` | 📊 | Stats | Racing statistics, driver comparisons |
| `analytics` | 📈 | Analytics | Performance analytics, trend charts |
| `career` | 🏆 | Career | Manager career progression |
| `calendar` | 📅 | Calendar | Season schedule, upcoming races |
| `ai` | 🤖 | AI | AI assistant chat interface |
| `penalties` | ⚠️ | Penalties | Penalty history, regulations |
| `history` | 📜 | History | Decision history, past results |
| `help` | ❓ | Help | Help documentation |
| `data` | 🗄️ | Data | FTB data explorer (raw queries) |

#### Dashboard Screen Detail

From `Dashboard.svelte` analysis:

```dart
class FTBDashboard extends StatelessWidget {
  // Top section: Phase indicator (Development / Race Weekend / etc.)
  // Metrics row: Cash, Morale, Team Health, Reputation, Runway
  // Events: Two-tab split (Personal / World) with formatted event cards
  // Driver results banner: Last race positions per driver
  // Next race countdown: Days until next race + track name
}
```

#### Race Day Flow

From `ftb_race_day.py` — the race day is an interactive modal experience:

```
IDLE → PRE_RACE_PROMPT → QUALI_READY → QUALI_RUNNING → QUALI_COMPLETE
    → RACE_READY → RACE_RUNNING → RACE_COMPLETE → POST_RACE_ADVANCE
```

Each phase requires specific UI:
- **PRE_RACE_PROMPT**: Yes/No dialog — attend race or simulate
- **QUALI_RUNNING**: Live qualifying positions updating
- **RACE_RUNNING**: Full PBP view with lap-by-lap standings, overtake events, gap intervals
- **RACE_COMPLETE**: Results popup with positions, points, prize money

#### Game State Model (Dart)

```dart
class FTBGameState {
  final String status;       // "no_game", "running"
  final int tick;
  final String dateStr;
  final String phase;        // "development", "race_weekend", "offseason"
  final String timeMode;     // "paused", "playing"
  final String controlMode;  // "human", "ai"
  final TeamState? playerTeam;
  final List<TeamState> aiTeams;
  final Map<String, LeagueState> leagues;
  final List<dynamic> freeAgents;
  final List<dynamic> jobBoard;
  final List<EventRecord> recentEvents;
  final List<DriverRecentResults> playerDriverRecentResults;
  final PlayByPlayState playByPlay;
  final RaceDayState? raceDay;
  // ... (complete from stores.ts gameState writable)
}
```

#### New Game / Load Game

Mirrors `SetupWizard.svelte` and the load screen in `App.svelte`:
- **New Game Wizard**: Team name, difficulty, league selection → `POST /api/new_game`
- **Load Game**: List saves from `GET /api/saves`, load via `POST /api/load_game`
- **Auto-save detection**: `GET /api/autosave` on startup

#### Race Result Popup

From `App.svelte`'s race result tracking logic — queue-based popup system:
```dart
class RaceResultPopup {
  final String key;
  final int tick, season, round;
  final String track, league, team;
  final List<RaceResultRow> rows;
  final int totalPoints, totalPrizeMoney;
}
```
Results are deduped by a composite key (`season|tick|league|round|track|team`) and queued for sequential display.

### 9.2 Oracle Kingdom Module

Driven by `ok_narrator_plugin.py` + `oracle_kingdom.py` + `oracle_court.py`.

#### Architecture Understanding

Oracle Kingdom is a **deterministic social simulation** centered on belief. The Oracle speaks through dialogue options, and effects cascade through a layered kingdom. The UI needs to present:

1. **Oracle Decree Interface** — The core interaction: choose what to say
2. **Kingdom State** — Factions, agents, belief propagation visualization
3. **Court View** — 9 palace rooms (LocationId enum), agent positions, social pressure
4. **Narrative Feed** — The narrator's output (5 responsibilities: Attention, Interaction, Narrative, Ritual, Audio Mix)
5. **Causal Ledger** — History of causes and effects

Since Oracle Kingdom uses `ok_narrator_plugin` as its meta plugin and has its own audio engine (`ok_audio_engine.py` with 9 spatial rooms and 16 pygame channels), the Flutter module needs:

```dart
class OracleKingdomModule {
  // Decree panel: show dialogue options, send choice to backend
  // Kingdom map: visual representation of factions and influence
  // Court presence: which agents are in current room
  // Event feed: narrative output with ritual markers
  // Audio: room-specific ambient beds, crowd murmurs, stingers
}
```

**API integration**: Oracle Kingdom's state is served through the station's event stream. The plugin command proxy (`/api/stations/{id}/plugin/{name}/command`) routes commands to the Oracle Kingdom controller.

### 9.3 Radio Station Module (General)

For stations using `radio_station` meta plugin (VibezFM, FlowFM, popcultureFM, etc.):

```dart
class RadioStationModule {
  // Now Playing: current segment source, speaker, text
  // Feed Status: which feeds are active, last event per feed
  // Event Log: scrolling list of StationEvents
  // Music Integration: flows plugin status, current track
  // Producer Queue: depth indicator, pending segments
  // Character Mix: active voices and roles
}
```

This is the simplest module — primarily a dashboard showing the radio "being a radio" with feeds flowing in and narration going out.

### 9.4 Neikos Module (Future)

Placeholder for `neikos.py` — deterministic island creature-ecology simulation:

```dart
class NeikosModule {
  // Island map: 100 sealed islands visualization
  // Species browser: 300 species, stats, breeding
  // League standings: competitive league results
  // Faction territories: territorial influence map
  // Event feed: ecology events, battles, genetic outcomes
}
```

---

## 10. Settings & Configuration

### 10.1 Settings Screen Structure

Mirrors `shell_bookmark.py`'s 8 settings tabs:

| Tab | API Endpoint | Key Fields |
|-----|-------------|------------|
| **General** | `/api/settings/general` | Station defaults, boot behavior, UI scaling |
| **Models** | `/api/settings/models` | LLM provider (Ollama/OpenAI/Anthropic/Google), model selection, API keys, endpoint URLs |
| **Voices** | `/api/settings/voices` | TTS provider (Piper/Kokoro/ElevenLabs/OpenAI/Azure/Google Cloud), voice-per-role mapping, speed, sample rate |
| **Plugins** | `/api/settings/plugins` | Per-plugin enable/disable, feed configuration |
| **Visual** | `/api/settings/visual` | Theme, accent color, background (for desktop; simplified on Pi) |
| **Storage** | `/api/settings/storage` | DB paths, memory paths, cleanup, archive |
| **Audio CLI** | (local config) | Wake phrase, exit phrase, STT engine, verbosity, audio mode |
| **Environment** | `/api/settings/general` | Env vars display, paths, versions |

### 10.2 Local Flutter Config

Stored in shared preferences or a local JSON file on the Pi:

```dart
class RadioAppConfig {
  String backendHost = '127.0.0.1';
  int shellPort = 7800;
  int gamePort = 7555;
  String theme = 'dark';        // dark, light, nord, dracula, monokai
  double uiScale = 1.0;
  bool showSubtitles = true;
  bool showWaveform = true;
  double masterVolume = 0.8;
  String audioOutput = 'default'; // ALSA device name
  bool wakeWordEnabled = true;
  String wakePhrase = 'hey radio';
  String exitPhrase = 'thanks radio';
  String verbosity = 'standard'; // minimal, concise, standard, broadcast, diagnostic
}
```

---

## 11. State Management

### 11.1 Provider Architecture (Riverpod)

```dart
// Connection state
final connectionStateProvider = StateProvider<ConnectionState>((ref) => ConnectionState.disconnected);

// Station list (from shell server)
final stationsProvider = FutureProvider<List<Station>>((ref) async {
  return ref.read(shellApiProvider).listStations();
});

// Active station
final activeStationProvider = StateProvider<Station?>((ref) => null);

// Game state (polled + WS updated) — only when FTB-type station is active
final gameStateProvider = StateNotifierProvider<GameStateNotifier, FTBGameState>((ref) {
  return GameStateNotifier(ref);
});

// Subtitle stream
final subtitleProvider = StateProvider<String>((ref) => '');

// Notification list
final notificationsProvider = StateNotifierProvider<NotificationNotifier, List<NotificationItem>>((ref) {
  return NotificationNotifier();
});

// Audio playback state
final audioStateProvider = StateNotifierProvider<AudioStateNotifier, AudioPlaybackState>((ref) {
  return AudioStateNotifier();
});

// Now playing metadata
final nowPlayingProvider = StateProvider<NowPlayingInfo?>((ref) => null);

// Active tab
final activeTabProvider = StateProvider<String>((ref) => 'dashboard');

// Widget updates (keyed per widget)
final widgetUpdatesProvider = StateProvider<Map<String, dynamic>>((ref) => {});

// Settings (per section, fetched on demand)
final generalSettingsProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  return ref.read(shellApiProvider).getGeneralSettings();
});
```

### 11.2 Polling Strategy

Mirrors the Svelte app's approach:

| Data | Method | Interval | Condition |
|------|--------|----------|-----------|
| Game state | REST poll | 3 seconds | Station running + game loaded |
| Audio state | REST poll | 5 seconds | Station running + audio active |
| Station status | REST poll | 10 seconds | Always (home screen) |
| Events | WebSocket push | Real-time | Station running |
| Audio segments | WebSocket push | Real-time | Station running |
| Subtitles | WebSocket push | Real-time | Station running |

### 11.3 Optimistic Updates

For game commands (tick, buy part, hire staff), apply the expected state change immediately in the provider, then reconcile with the next server state poll. If the server rejects the action, roll back and show a toast.

---

## 12. Navigation & Routing

### 12.1 Route Tree

```
/                           → StationBrowser (home)
/station/:id                → StationRuntime (active station wrapper)
  /station/:id/dashboard    → Per-station dashboard (default)
  /station/:id/team         → Team management (FTB)
  /station/:id/car          → Car setup (FTB)
  /station/:id/raceops      → Race operations (FTB)
  /station/:id/pbp          → Play-by-play (FTB)
  /station/:id/finance      → Finance (FTB)
  /station/:id/sponsors     → Sponsors (FTB)
  /station/:id/calendar     → Calendar (FTB)
  /station/:id/decree       → Decree interface (OK)
  /station/:id/kingdom      → Kingdom view (OK)
  /station/:id/court        → Court view (OK)
  /station/:id/feeds        → Feed status (Radio)
  /station/:id/events       → Event log (Radio)
  /station/:id/...          → (all other station-specific tabs)
/settings                   → Settings root
  /settings/general
  /settings/models
  /settings/voices
  /settings/plugins
  /settings/storage
/wizard                     → New station wizard
/wizard/game                → New game wizard (FTB)
```

### 12.2 Navigation Patterns

- **Bottom tab bar**: Scrollable tab bar matching the Svelte pattern. On 800×480, show 6 visible tabs with horizontal scroll for the rest.
- **Back navigation**: Physical back button (if present) or swipe-right gesture returns to previous tab or home.
- **Programmatic navigation**: Audio CLI commands (`navigate`, `switch_tab` via WebSocket) trigger navigation directly.
- **Deep linking**: Station launch from home screen opens directly to the station's dashboard.

### 12.3 Router Implementation

Use `go_router` for declarative routing with shell routes for the persistent bottom bar:

```dart
final router = GoRouter(
  routes: [
    GoRoute(path: '/', builder: (_, __) => StationBrowserScreen()),
    ShellRoute(
      builder: (_, state, child) => StationShell(child: child), // persistent nav bar + subtitle
      routes: [
        GoRoute(path: '/station/:id/:tab', builder: (_, state) {
          final id = state.pathParameters['id']!;
          final tab = state.pathParameters['tab'] ?? 'dashboard';
          return StationTabScreen(stationId: id, tab: tab);
        }),
      ],
    ),
    GoRoute(path: '/settings/:section', builder: (_, state) => SettingsScreen(section: state.pathParameters['section']!)),
    GoRoute(path: '/wizard', builder: (_, __) => StationWizardScreen()),
  ],
);
```

---

## 13. Theming & Visual Design

### 13.1 Design Language

The Radio OS aesthetic is **dark-first, information-dense, terminal-inspired** with accent colors. The Svelte app uses CSS custom properties; Flutter uses a `ThemeData` equivalent.

### 13.2 Color Themes

Ported from `shell_bookmark.py`'s 6 themes:

```dart
enum RadioTheme { dark, light, nord, dracula, monokai, solarized }

class RadioColors {
  // Dark theme (default)
  static const dark = RadioColors(
    bgPrimary: Color(0xFF0e0e0e),
    bgSecondary: Color(0xFF121212),
    bgCard: Color(0xFF1a1a1a),
    border: Color(0xFF2a2a2a),
    textPrimary: Color(0xFFe8e8e8),
    textSecondary: Color(0xFF9a9a9a),
    textMuted: Color(0xFF666666),
    accent: Color(0xFF4cc9f0),
    success: Color(0xFF34d399),
    warning: Color(0xFFfbbf24),
    danger: Color(0xFFf87171),
    info: Color(0xFF60a5fa),
  );
}
```

### 13.3 Typography

```dart
class RadioTypography {
  static const fontFamily = 'Inter'; // or system default on Pi
  static const fontMono = 'JetBrains Mono'; // for data, metrics, timestamps

  // Scale for 800×480 touch
  static const headlineLarge = TextStyle(fontSize: 20, fontWeight: FontWeight.w800);
  static const headlineMedium = TextStyle(fontSize: 16, fontWeight: FontWeight.w700);
  static const bodyLarge = TextStyle(fontSize: 14);
  static const bodyMedium = TextStyle(fontSize: 12);
  static const bodySmall = TextStyle(fontSize: 11);
  static const caption = TextStyle(fontSize: 9);
}
```

### 13.4 Component Library

Shared widgets mirroring the Svelte components:

| Svelte Component | Flutter Widget | Purpose |
|-----------------|---------------|---------|
| `MetricDisplay.svelte` | `MetricCard` | Key metric with label, value, trend indicator |
| `EntityCard.svelte` | `EntityCard` | Driver/engineer card with stats |
| `StatBar.svelte` | `StatBar` | Horizontal stat bar (0–100) with color gradient |
| `Modal.svelte` | `RadioModal` | Centered modal with backdrop |
| `Toast.svelte` | `RadioToast` | Auto-dismiss notification toast |
| `Toolbar.svelte` | `RadioToolbar` | Top app bar with station info |
| `NotificationCenter.svelte` | `NotificationDrawer` | Slide-out notification panel |
| `SetupWizard.svelte` | `SetupWizard` | Multi-step game creation wizard |

### 13.5 Touch Optimization

For the 7" touchscreen:
- All interactive elements ≥ 48×48 dp
- Generous padding between list items (12px minimum)
- Swipe gestures for tab switching
- Long-press for secondary actions (instead of right-click)
- Pull-to-refresh on data screens
- Bottom sheet dialogs instead of centered modals on small screens

---

## 14. Offline & Edge Behavior

### 14.1 Backend Unavailable

| Scenario | Behavior |
|----------|----------|
| Backend not started yet | Show "Connecting to Radio OS..." splash with retry animation |
| Backend crashes | Show connection banner, auto-reconnect every 2s, preserve last known state |
| Station process dies | Station status → "error", show log excerpt, offer relaunch |
| WiFi drops (LLM APIs) | Backend handles gracefully; Flutter shows "content paused" indicator |

### 14.2 Cache Strategy

```dart
class RadioCache {
  // Station list: cache in memory, refresh on pull-to-refresh
  // Game state: hold last known state in Riverpod, overlay with "stale" indicator
  // Audio segments: no caching (real-time stream)
  // Ambient audio files: download and cache in app-local storage
  // Logos/images: cache with standard Flutter image cache
  // Settings: cache per-session, invalidate on save
}
```

### 14.3 Startup Sequence

```
1. Flutter app launches (systemd or autostart)
2. Show splash screen with Radio OS logo
3. Attempt connection to http://127.0.0.1:7800/api/health
4. If OK → fetch station list, show Station Browser
5. If FAIL → retry every 2s with "Waiting for backend..." message
6. If a station was running (from previous session) → auto-reconnect to event/audio streams
7. Audio CLI sidecar starts independently (if configured)
```

---

## 15. File & Directory Structure

```
radio_os_flutter/
├── lib/
│   ├── main.dart                    # App entry point, provider scope, router
│   ├── app.dart                     # MaterialApp with theme, router config
│   │
│   ├── config/
│   │   ├── constants.dart           # API ports, timeouts, default values
│   │   ├── themes.dart              # RadioTheme definitions (6 themes)
│   │   └── typography.dart          # Font styles
│   │
│   ├── data/
│   │   ├── api/
│   │   │   ├── shell_api_client.dart    # Port 7800 REST client
│   │   │   ├── game_api_client.dart     # Port 7555 REST client
│   │   │   ├── http_client.dart         # Base HTTP with retry/timeout
│   │   │   └── ws_manager.dart          # WebSocket connection manager
│   │   ├── models/
│   │   │   ├── station.dart             # Station, StationStatus
│   │   │   ├── game_state.dart          # FTBGameState, TeamState, etc.
│   │   │   ├── event.dart               # StationEvent, NotificationItem
│   │   │   ├── audio.dart               # AudioSegment, AudioEvent
│   │   │   ├── settings.dart            # Settings section models
│   │   │   ├── race_day.dart            # RaceDayState, RaceDayPhase
│   │   │   ├── oracle_kingdom.dart      # OKState, DecreeOption, Faction
│   │   │   └── neikos.dart              # NeikosState, Island, Species
│   │   └── repositories/
│   │       ├── station_repository.dart  # Station CRUD operations
│   │       ├── game_repository.dart     # Game state polling + commands
│   │       ├── audio_repository.dart    # Audio stream management
│   │       └── settings_repository.dart # Settings load/save
│   │
│   ├── domain/
│   │   ├── providers/
│   │   │   ├── connection_provider.dart
│   │   │   ├── station_providers.dart
│   │   │   ├── game_state_provider.dart
│   │   │   ├── audio_provider.dart
│   │   │   ├── subtitle_provider.dart
│   │   │   ├── notification_provider.dart
│   │   │   ├── settings_provider.dart
│   │   │   └── navigation_provider.dart
│   │   └── services/
│   │       ├── audio_engine.dart        # RadioAudioEngine (voice + ambient + music)
│   │       ├── voice_command.dart       # VoiceCommandService (Option B)
│   │       └── event_dispatcher.dart    # Routes WS events to providers
│   │
│   ├── presentation/
│   │   ├── screens/
│   │   │   ├── station_browser/
│   │   │   │   ├── station_browser_screen.dart
│   │   │   │   ├── station_card.dart
│   │   │   │   └── station_wizard_screen.dart
│   │   │   ├── station_runtime/
│   │   │   │   ├── station_shell.dart       # Persistent wrapper (nav bar + subtitle)
│   │   │   │   └── station_tab_screen.dart  # Tab router
│   │   │   ├── ftb/
│   │   │   │   ├── dashboard_tab.dart
│   │   │   │   ├── team_tab.dart
│   │   │   │   ├── car_tab.dart
│   │   │   │   ├── development_tab.dart
│   │   │   │   ├── race_ops_tab.dart
│   │   │   │   ├── play_by_play_tab.dart
│   │   │   │   ├── finance_tab.dart
│   │   │   │   ├── sponsors_tab.dart
│   │   │   │   ├── promotion_tab.dart
│   │   │   │   ├── stats_tab.dart
│   │   │   │   ├── analytics_tab.dart
│   │   │   │   ├── career_tab.dart
│   │   │   │   ├── calendar_tab.dart
│   │   │   │   ├── ai_assistant_tab.dart
│   │   │   │   ├── penalties_tab.dart
│   │   │   │   ├── history_tab.dart
│   │   │   │   ├── help_tab.dart
│   │   │   │   ├── data_tab.dart
│   │   │   │   ├── setup_wizard.dart
│   │   │   │   └── race_result_popup.dart
│   │   │   ├── oracle_kingdom/
│   │   │   │   ├── decree_tab.dart
│   │   │   │   ├── kingdom_tab.dart
│   │   │   │   ├── court_tab.dart
│   │   │   │   ├── narrative_tab.dart
│   │   │   │   └── ledger_tab.dart
│   │   │   ├── radio_station/
│   │   │   │   ├── radio_dashboard_tab.dart
│   │   │   │   ├── feed_status_tab.dart
│   │   │   │   └── event_log_tab.dart
│   │   │   └── settings/
│   │   │       ├── settings_screen.dart
│   │   │       ├── general_settings.dart
│   │   │       ├── model_settings.dart
│   │   │       ├── voice_settings.dart
│   │   │       ├── plugin_settings.dart
│   │   │       └── storage_settings.dart
│   │   ├── widgets/
│   │   │   ├── metric_card.dart
│   │   │   ├── entity_card.dart
│   │   │   ├── stat_bar.dart
│   │   │   ├── radio_modal.dart
│   │   │   ├── radio_toast.dart
│   │   │   ├── radio_toolbar.dart
│   │   │   ├── subtitle_overlay.dart
│   │   │   ├── now_playing_banner.dart
│   │   │   ├── notification_drawer.dart
│   │   │   ├── connection_banner.dart
│   │   │   ├── waveform_visualizer.dart
│   │   │   └── loading_splash.dart
│   │   └── router.dart              # GoRouter configuration
│   │
│   └── utils/
│       ├── formatters.dart          # Currency, dates, sizes, durations
│       ├── event_format.dart        # Event summary formatting (from eventFormat.ts)
│       └── platform_utils.dart      # Pi-specific helpers
│
├── assets/
│   ├── fonts/
│   ├── images/
│   │   └── radioos.png
│   └── audio/
│       └── (cached ambient files)
│
├── linux/                           # Flutter Linux runner (GTK)
│   ├── CMakeLists.txt
│   └── my_application.cc
│
├── test/
│   ├── api/
│   ├── providers/
│   ├── screens/
│   └── widgets/
│
├── integration_test/
│   └── app_test.dart
│
├── pubspec.yaml
├── analysis_options.yaml
└── README.md
```

---

## 16. Dependencies

### 16.1 pubspec.yaml Core Dependencies

```yaml
dependencies:
  flutter:
    sdk: flutter

  # State Management
  flutter_riverpod: ^2.5.0
  riverpod_annotation: ^2.3.0

  # Routing
  go_router: ^14.0.0

  # HTTP & WebSocket
  dio: ^5.4.0                     # HTTP client with interceptors
  web_socket_channel: ^2.4.0      # WebSocket client
  connectivity_plus: ^6.0.0       # Network status monitoring

  # Audio
  just_audio: ^0.9.36             # Primary audio playback
  just_audio_linux: ^0.0.3        # Linux (ALSA/PulseAudio) backend
  audio_session: ^0.1.18          # Audio focus management

  # Voice (Option B — conditional)
  # speech_to_text: ^6.6.0        # STT
  # porcupine_flutter: ^3.0.0     # Wake word detection

  # UI
  fl_chart: ^0.68.0               # Charts for analytics
  shimmer: ^3.0.0                 # Loading placeholders
  cached_network_image: ^3.3.0    # Image caching
  flutter_svg: ^2.0.0             # SVG support

  # Utilities
  shared_preferences: ^2.2.0      # Local config persistence
  path_provider: ^2.1.0           # File system paths
  intl: ^0.19.0                   # Date/number formatting
  collection: ^1.18.0             # Data structure utilities
  freezed_annotation: ^2.4.0      # Immutable models
  json_annotation: ^4.8.0         # JSON serialization

dev_dependencies:
  flutter_test:
    sdk: flutter
  build_runner: ^2.4.0
  freezed: ^2.5.0
  json_serializable: ^6.7.0
  riverpod_generator: ^2.4.0
  mockito: ^5.4.0
  flutter_lints: ^4.0.0
```

### 16.2 System Dependencies (Pi 5)

```bash
# Flutter Linux desktop prerequisites
sudo apt install clang cmake ninja-build pkg-config libgtk-3-dev liblzma-dev

# Audio
sudo apt install libasound2-dev pulseaudio libpulse-dev
# or pipewire equivalents

# Mic access (for voice commands)
sudo apt install portaudio19-dev

# Python backend
# (existing requirements.txt + radioenv virtualenv)
```

---

## 17. Testing Strategy

### 17.1 Unit Tests

| Layer | Target | Tool |
|-------|--------|------|
| API clients | Mock HTTP responses, verify request format | `mockito`, `dio`'s mock adapter |
| State providers | State transitions, event handling | `riverpod_test` |
| Audio engine | Segment parsing, queue management | Standard `flutter_test` |
| Formatters | Currency, dates, event summaries | Standard `flutter_test` |

### 17.2 Widget Tests

| Screen | Focus |
|--------|-------|
| Station browser | Card rendering, launch/stop actions |
| FTB dashboard | Metric display with various state shapes |
| Race day flow | Phase transitions, modal lifecycle |
| Settings | Form validation, save/load cycle |

### 17.3 Integration Tests

| Scenario | Method |
|----------|--------|
| Full station launch flow | Mock backend, verify all API calls in sequence |
| Audio playback | Feed mock WAV segments, verify sequential playback |
| WebSocket reconnection | Simulate disconnect, verify auto-reconnect |
| Voice command flow | (Option A) Send mock WS navigate events, verify routing |

### 17.4 On-Device Testing

- Test on actual Pi 5 with 7" touchscreen
- Profile frame rates (target: 60fps, acceptable: 30fps for data-heavy screens)
- Measure memory usage under load (multiple hours of continuous audio)
- Test audio latency (WAV WebSocket → speaker)
- Test touch responsiveness with automotive-grade screen protector

---

## 18. Build & Deployment

### 18.1 Build for Pi 5

```bash
# Cross-compile on dev machine (if not building on Pi itself)
flutter build linux --release --target-platform linux-arm64

# Or build directly on Pi 5
flutter build linux --release
```

### 18.2 Systemd Service

```ini
# /etc/systemd/system/radio-os-flutter.service
[Unit]
Description=Radio OS Flutter UI
After=radio-os-backend.service
Requires=radio-os-backend.service

[Service]
Type=simple
User=pi
Environment=DISPLAY=:0
ExecStart=/home/pi/radio_os_flutter/build/linux/arm64/release/bundle/radio_os_flutter
Restart=always
RestartSec=5

[Install]
WantedBy=graphical.target
```

```ini
# /etc/systemd/system/radio-os-backend.service
[Unit]
Description=Radio OS Python Backend
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/Radio-OS
ExecStart=/home/pi/Radio-OS/radioenv/bin/python web_server.py
Environment=RADIO_OS_ROOT=/home/pi/Radio-OS
Environment=RADIO_OS_HEADLESS=1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 18.3 Kiosk Mode (Optional)

For a dedicated radio appliance:

```bash
# Auto-login to desktop
sudo raspi-config # → System Options → Boot / Auto Login → Desktop Autologin

# Launch Flutter app fullscreen on boot
# Add to /home/pi/.config/autostart/radio-os.desktop
[Desktop Entry]
Type=Application
Name=Radio OS
Exec=/home/pi/radio_os_flutter/build/linux/arm64/release/bundle/radio_os_flutter --fullscreen
```

### 18.4 Update Mechanism

- **Backend**: `git pull` + restart service (or rsync from release artifact)
- **Flutter app**: Replace build bundle + restart service
- **Combined**: Shell script that stops both services, updates both, restarts
- **Future**: OTA update system with version checking against a manifest URL

---

## 19. Appendices

### A. Complete WebSocket Event Type Reference

From `App.svelte` and `ftb_web_server.py`:

```dart
enum WsEventType {
  stateUpdate,      // Full or partial game state
  subtitle,         // Subtitle text update
  notification,     // In-game notification
  audioEvent,       // Ambient/SFX trigger
  widgetUpdate,     // Per-widget data push
  navigate,         // Programmatic screen change (from Audio CLI)
  switchTab,        // Direct tab change (from Audio CLI)
  nowPlaying,       // Current audio segment info
  raceResult,       // Race completion event
  batchSummary,     // Tick batch completion summary
  pong,             // Keepalive response
  error,            // Server error
}
```

### B. FTB Game State Schema (Key Fields)

From `stores.ts` and `ftb_web_server.py`:

```dart
// Top-level game state keys
{
  "status": "no_game" | "running",
  "tick": int,
  "date_str": "DD/MM",
  "phase": "development" | "race_weekend" | "offseason",
  "time_mode": "paused" | "playing",
  "control_mode": "human" | "ai",
  "season_number": int,
  "player_team": { /* TeamState */ },
  "ai_teams": [ /* TeamState[] */ ],
  "leagues": { /* leagueId: LeagueState */ },
  "free_agents": [ /* Agent[] */ ],
  "job_board": [ /* Job[] */ ],
  "recent_events": [ /* StationEvent[] */ ],
  "player_driver_recent_results": [ /* DriverResults[] */ ],
  "play_by_play": {
    "is_live": bool,
    "lap_info": { "current": int, "total": int },
    "standings": [ /* position entries */ ],
    "live_events": [ /* lap events */ ],
  },
  "race_day": {
    "phase": "idle" | "pre_race_prompt" | "quali_ready" | ... | "post_race_advance",
    /* phase-specific data */
  },
  "parts_marketplace": [ /* Part[] */ ],
  "manager_career": { /* career progression data */ },
  "tracks": { /* trackId: TrackInfo */ },
}
```

### C. Audio Payload Wire Format

```
Binary WebSocket message:
┌──────────────┬──────────────────────────┬──────────────────────┐
│ 4 bytes      │ N bytes                  │ M bytes              │
│ uint32 BE    │ UTF-8 JSON               │ WAV file             │
│ = N          │ metadata                 │ (PCM 16-bit)         │
│              │ {                        │                      │
│              │   "voice": "am_adam",    │ RIFF header +        │
│              │   "speaker": "Kai",      │ audio data           │
│              │   "text": "...",         │                      │
│              │   "duration": 3.2,       │                      │
│              │   "sr": 24000,           │                      │
│              │   "ts": 1234567890       │                      │
│              │ }                        │                      │
└──────────────┴──────────────────────────┴──────────────────────┘
```

### D. Station Manifest Structure (Key Fields)

From `manifest.yaml` files:

```yaml
station:
  id: string
  name: string
  host: string
  category: string
  logo: string (path)
meta_plugin: string  # "ftb_narrator_plugin", "ok_narrator_plugin", "radio_station"
llm:
  provider: string   # "openai", "ollama", "anthropic", "google"
models:
  producer: string
  host: string
  navigator: string
  narrator: string (optional)
audio:
  voices_provider: string  # "piper", "kokoro", "elevenlabs"
voices:
  host: string             # voice ID per role
  narrator: string
  # ... role-specific voices
characters:
  host:
    role: string
    traits: [string]
    focus: [string]
feeds:
  <feed_name>:
    enabled: bool
    plugin: string (optional, defaults to feed_name)
    # ... feed-specific config
pacing:
  idle_riff_sec: int
  between_segments_sec: int
  # ... timing params
```

### E. Oracle Kingdom Room IDs

From `oracle_court.py`'s `LocationId` enum (used for spatial audio):

```
COURTYARD, THRONE_ROOM, GRAND_HALL, ARCHIVE,
GARDEN, TOWER, DUNGEON, TEMPLE, MARKETPLACE
```

Each room has ambient audio beds, textures, and crowd sounds in `stations/OracleKingdom/audio/rooms/<location_id>/`.

### F. Broadcast Commentary Voice Tiers (FTB)

From `ftb_broadcast_commentary_llm.py`:

| Tier | Level | PBP Voice | Color Voice |
|------|-------|-----------|-------------|
| 1 | Grassroots | am_puck | bf_lily |
| 2 | Enthusiast | am_eric | af_river |
| 3 | Professional | am_adam | af_bella |
| 4 | Premium | bm_lewis | bf_emma |
| 5 | World Class | bm_george | bf_alice |

### G. Audio CLI Verbosity Levels

From `audio_cli.py`:

| Level | Description | Max Output |
|-------|-------------|------------|
| `minimal` | Shortest confirmation | ~80 chars, 1 sentence |
| `concise` | 1-2 short sentences | ~2 sentences |
| `standard` | Up to 3 sentences | ~4 sentences |
| `broadcast` | Full narration | ~600 chars |
| `diagnostic` | Structured debug data | Station + route + state |

---

*End of Design Specification*
