#pragma once

// ─── WiFi ────────────────────────────────────────────────────────────────────
#define WIFI_SSID     "blender"
#define WIFI_PASSWORD "strawberrybanana"

// ─── Radio OS server discovery ────────────────────────────────────────────────
// Puck resolves this mDNS name at boot — connects to whichever machine on the
// local network is currently running web_server.py (Mac, PC, or Pi).
#define RADIOOS_MDNS_HOST   "radioos.local"
// Fallback IP if mDNS fails (e.g. router doesn't forward mDNS)
#define RADIOOS_FALLBACK_HOST "10.0.0.70"
#define RADIO_OS_PORT       7800

// ─── Node identity ───────────────────────────────────────────────────────────
// NODE_ID is set per-environment in platformio.ini

// ─── Waveshare ESP32-S3-AUDIO-Board ──────────────────────────────────────────
// ES8311 DAC/amp + ES7210 mic ADC
// Both codecs share one I2S bus and are configured via I2C
#if defined(BOARD_S3_AUDIO)
  // I2C — controls ES8311 (DAC) and ES7210 (mic ADC) chip config
  #define PIN_I2C_SCL     10
  #define PIN_I2C_SDA     11
  // I2S — shared audio bus for both codecs
  #define PIN_I2S_MCLK    12
  #define PIN_I2S_BCLK    13
  #define PIN_I2S_LRCLK   14
  #define PIN_I2S_DIN     15   // data from ES7210 mic → ESP32
  #define PIN_I2S_DOUT    16   // data from ESP32 → ES8311 amp
  // RGB LED strip (WS2812, 7 LEDs)
  #define PIN_RGB_LED     38
  #define RGB_LED_COUNT    7
  // ES8311 I2C address
  #define ES8311_ADDR     0x18
  // ES7210 I2C address
  #define ES7210_ADDR     0x40

// ─── ESP32-C6 (Waveshare DEV-KIT-N8) ─────────────────────────────────────────
#elif defined(BOARD_C6)
  #define PIN_I2S_BCLK    4
  #define PIN_I2S_LRCLK   5
  #define PIN_I2S_DIN     2
  #define PIN_I2S_DOUT    10
  #define PIN_I2S_MCLK    -1
  #define AMP_ENABLE_PIN  -1

// ─── Classic ESP32 DevKit C ───────────────────────────────────────────────────
#elif defined(BOARD_ESP32)
  #define PIN_I2S_BCLK    26
  #define PIN_I2S_LRCLK   25
  #define PIN_I2S_DIN     35
  #define PIN_I2S_DOUT    22
  #define PIN_I2S_MCLK    -1
  #define AMP_ENABLE_PIN  -1
#endif

// ─── Audio config ─────────────────────────────────────────────────────────────
#define SAMPLE_RATE     16000
#define AUDIO_CHUNK_MS     20   // 20ms per WiFi packet = 320 samples @ 16kHz
