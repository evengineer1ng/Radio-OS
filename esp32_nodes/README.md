# ESP32 Audio Nodes

Four ESP32 nodes — each with one INMP441 mic + one MAX98357A amp + 3W speaker — streaming audio to/from the Radio OS backend over WiFi WebSocket.

## Hardware

| Node | Board | Port (example) |
|------|-------|---------------|
| 1 | ESP32-C6 (Waveshare) | `/dev/cu.wchusbserial...` |
| 2 | ESP32-C6 (Waveshare) | `/dev/cu.wchusbserial...` |
| 3 | Classic ESP32 DevKit C | `/dev/cu.wchusbserial...` |
| 4 | Classic ESP32 DevKit C | `/dev/cu.wchusbserial...` |

## Wiring (per node)

### INMP441 Mic
| INMP441 | ESP32-C6 | Classic ESP32 |
|---------|----------|---------------|
| VDD | 3V3 | 3V3 |
| GND | GND | GND |
| L/R | GND | GND |
| SCK | GPIO6 | GPIO26 |
| WS  | GPIO7 | GPIO25 |
| SD  | GPIO2 | GPIO35 |

### MAX98357A Amp
| MAX98357A | ESP32-C6 | Classic ESP32 |
|-----------|----------|---------------|
| VIN | 5V | 5V |
| GND | GND | GND |
| BCLK | GPIO6 (shared) | GPIO26 (shared) |
| LRC  | GPIO7 (shared) | GPIO25 (shared) |
| DIN  | GPIO10 | GPIO22 |

## Setup

1. Edit `src/config.h` — set your WiFi SSID/password and Radio OS server IP
2. Edit `platformio.ini` — set correct `upload_port` for each board
3. Install PlatformIO IDE extension in VS Code
4. Select environment (`c6_node` or `esp32_node`) in the PlatformIO status bar
5. Click **Upload** (→ arrow in status bar)
6. Click **Monitor** (plug icon) to see serial output

## Protocol

Each node opens a WebSocket to `ws://RADIO_OS_HOST:8765/audio` and:
- **Sends**: raw 16-bit mono PCM at 16kHz (mic audio)
- **Receives**: raw 16-bit mono PCM at 16kHz (playback audio from server)
- **Identifies itself** with `HELLO:node<N>` text message on connect
