#pragma once

// ─── WiFi ────────────────────────────────────────────────────────────────────
#define WIFI_SSID     "blender"
#define WIFI_PASSWORD "strawberrybanana"

// Radio OS Python backend — Raspberry Pi at 10.0.0.120
#define RADIO_OS_HOST "10.0.0.120"
#define RADIO_OS_PORT 7800          // WebSocket port (Radio OS web shell)

// ─── Node identity ───────────────────────────────────────────────────────────
// NODE_ID is set per-environment in platformio.ini (1-4)
// Nodes 1-2 = ESP32-C6,  Nodes 3-4 = Classic ESP32

// ─── I2S pins — ESP32-C6 ─────────────────────────────────────────────────────
#if defined(BOARD_C6)
  #define I2S_SCK       6    // Shared BCLK for mic + amp
  #define I2S_WS        7    // Shared LRCLK for mic + amp
  #define I2S_MIC_SD    2    // INMP441 data out  → ESP32 in
  #define I2S_AMP_SD   10    // MAX98357A data in ← ESP32 out

// ─── I2S pins — Classic ESP32 ────────────────────────────────────────────────
#elif defined(BOARD_ESP32)
  #define I2S_SCK      26
  #define I2S_WS       25
  #define I2S_MIC_SD   35    // input-only pin, good for mic
  #define I2S_AMP_SD   22
#endif

// ─── Audio config ────────────────────────────────────────────────────────────
#define SAMPLE_RATE     16000
#define DMA_BUF_COUNT       4
#define DMA_BUF_LEN       256
#define AUDIO_CHUNK_MS     20   // ms of audio per WiFi packet (~640 bytes @ 16kHz)
