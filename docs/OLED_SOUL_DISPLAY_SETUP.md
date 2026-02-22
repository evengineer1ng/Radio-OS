# OLED Soul Display (SPI, Raspberry Pi 5)

This repo now includes a standalone daemon for the 128x64 transparent OLED "soul display":

- Daemon: `tools/oled_soul_daemon.py`
- Event sender utility: `tools/oled_event_send.py`

The daemon uses:
- UDP JSON events for control
- 20 FPS render loop
- Priority scheduler (`ERROR > LISTENING > THINKING > TRANSITION > AMBIENT`)
- Abstract geometry animations only (no text/icons)

## 1) Install dependencies on Pi

Core image drawing already uses Pillow (in this repo).

For SPI OLED hardware output, install Luma:

```bash
pip install luma.oled luma.core
```

If you need SPI userspace tools:

```bash
sudo apt-get update
sudo apt-get install -y python3-spidev
```

Enable SPI in `raspi-config` if not already enabled.

## 2) Run daemon (hardware mode)

```bash
python3 tools/oled_soul_daemon.py \
  --driver ssd1306 \
  --spi-port 0 \
  --spi-device 0 \
  --dc-pin 24 \
  --rst-pin 25 \
  --fps 20 \
  --width 128 \
  --height 64
```

Notes:
- `--driver` defaults to `ssd1306`. Change if your panel uses another luma-supported driver.
- `--rotate` accepts 0/90/180/270.

## 3) Run daemon (simulation mode)

Useful for local dev without OLED hardware:

```bash
python3 tools/oled_soul_daemon.py --simulate --preview-path /tmp/oled_preview.png
```

This writes periodic preview frames to `/tmp/oled_preview.png`.

## 4) Send test events

```bash
python3 tools/oled_event_send.py --type enter_station
python3 tools/oled_event_send.py --type audio_cli_on
python3 tools/oled_event_send.py --type thinking_start
python3 tools/oled_event_send.py --type thinking_end
python3 tools/oled_event_send.py --type error
python3 tools/oled_event_send.py --type clear_error
python3 tools/oled_event_send.py --type volume_delta --delta 1
python3 tools/oled_event_send.py --type station_nudge_left
python3 tools/oled_event_send.py --type confirm
```

Or raw JSON:

```bash
python3 tools/oled_event_send.py --json '{"type":"loading_start"}'
```

## 5) Event contract

Default UDP endpoint:
- Host: `127.0.0.1`
- Port: `5115`

Supported high-level event types:
- Lifecycle: `boot`, `wake`, `sleep`, `shutdown`
- Station: `enter_station`, `exit_station`, `station_start`, `station_stop`
- Transition: `loading_in`, `loading_out`, `loading_start`, `loading_switch`
- Audio CLI: `audio_cli_on`, `audio_cli_off`, `listening_start`, `listening_stop`
- Thinking: `thinking_start`, `thinking_end`, `llm_busy_start`, `llm_busy_end`
- Error: `error`, `clear_error`
- Tactile: `volume_delta` (`delta` int), `station_nudge_left`, `station_nudge_right`, `confirm`

## 6) Animation mapping

Implemented mappings follow your spec:
- Boot: `Ignition`
- Enter station: `Portal Open`
- Exit station: `Portal Close`
- Loading: `Scan & Lock`
- Audio CLI on: `Ripples` + listening sustain arc
- Audio CLI off: `Dampen`
- Thinking: three-body orbit sustain + resolve pulse on end
- Error: `Fracture` + error sustain
- Volume: `Tilt wave`
- Nudge: `Side wind`
- Confirm: `Ping`
- Ambient default: `Breathing Halo` (or `Orbit Calm` via `--ambient orbit_calm`)

## 7) Integrating from runtime code

If you want to emit events from Python runtime code:

```python
from tools.oled_event_client import send_oled_event

send_oled_event({"type": "audio_cli_on"})
send_oled_event({"type": "volume_delta", "delta": 1})
```

That keeps OLED logic isolated from station runtime logic.
