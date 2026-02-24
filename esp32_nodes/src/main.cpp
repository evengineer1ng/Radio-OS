#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <driver/i2s_std.h>
#include "config.h"

// ─── Globals ─────────────────────────────────────────────────────────────────
WebSocketsClient ws;
bool ws_connected = false;

// Audio buffer: AUDIO_CHUNK_MS worth of 16-bit mono samples (mic)
// Speaker buffer: stereo 32-bit frames = 4x the mono sample count
const int CHUNK_SAMPLES = (SAMPLE_RATE * AUDIO_CHUNK_MS) / 1000;
int16_t  mic_buf[CHUNK_SAMPLES];
int32_t  spk_buf[CHUNK_SAMPLES * 2];   // stereo 32-bit: L+R interleaved

// New IDF v5 channel handles
i2s_chan_handle_t rx_handle = nullptr;
i2s_chan_handle_t tx_handle = nullptr;

// ─── I2S setup (ESP-IDF v5 API) ──────────────────────────────────────────────
void i2s_init() {
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    chan_cfg.auto_clear = true;
    // Full-duplex: TX for speaker, RX for mic
    i2s_new_channel(&chan_cfg, &tx_handle, &rx_handle);

    i2s_std_config_t std_cfg = {
        .clk_cfg  = I2S_STD_CLK_DEFAULT_CONFIG(SAMPLE_RATE),
        .slot_cfg = I2S_STD_MSB_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = (gpio_num_t)I2S_SCK,
            .ws   = (gpio_num_t)I2S_WS,
            .dout = (gpio_num_t)I2S_AMP_SD,
            .din  = (gpio_num_t)I2S_MIC_SD,
            .invert_flags = { .mclk_inv = false, .bclk_inv = false, .ws_inv = false },
        },
    };

    i2s_channel_init_std_mode(rx_handle, &std_cfg);
    i2s_channel_init_std_mode(tx_handle, &std_cfg);
    i2s_channel_enable(rx_handle);
    i2s_channel_enable(tx_handle);

    Serial.println("[I2S] Full-duplex I2S0 initialised");
}

// ─── WebSocket events ────────────────────────────────────────────────────────
void ws_event(WStype_t type, uint8_t* payload, size_t length) {
    switch (type) {
        case WStype_CONNECTED:
            ws_connected = true;
            Serial.printf("[WS] Connected to Radio OS  node=%d\n", NODE_ID);
            // Send hello so the server knows which node this is
            {
                char hello[32];
                snprintf(hello, sizeof(hello), "HELLO:node%d", NODE_ID);
                ws.sendTXT(hello);
            }
            break;

        case WStype_DISCONNECTED:
            ws_connected = false;
            Serial.println("[WS] Disconnected, will retry...");
            break;

        case WStype_BIN:
            // Incoming audio from server → play on speaker
            if (length <= sizeof(spk_buf)) {
                memcpy(spk_buf, payload, length);
                size_t written = 0;
                esp_err_t err = i2s_channel_write(tx_handle, spk_buf, length, &written,
                                  pdMS_TO_TICKS(100));
                Serial.printf("[SPK] rx %d bytes  wrote %d  err=0x%x\n",
                              (int)length, (int)written, (int)err);
            } else {
                Serial.printf("[SPK] frame too big: %d > %d\n", (int)length, (int)sizeof(spk_buf));
            }
            break;

        case WStype_TEXT:
            Serial.printf("[WS] Text: %s\n", payload);
            break;

        default:
            break;
    }
}

// ─── WiFi connect ────────────────────────────────────────────────────────────
void wifi_connect() {
    Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.printf("\n[WiFi] Connected  IP=%s\n", WiFi.localIP().toString().c_str());
}

// ─── Setup ───────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.printf("\n=== Radio OS Node %d booting ===\n", NODE_ID);

    // Drive MAX98357A SD pin HIGH to enable the amp.
    // If AMP_ENABLE_PIN == -1 the SD line is tied to 3.3V on the board.
#if AMP_ENABLE_PIN >= 0
    pinMode(AMP_ENABLE_PIN, OUTPUT);
    digitalWrite(AMP_ENABLE_PIN, HIGH);
    Serial.printf("[AMP] Enable pin GPIO%d → HIGH\n", AMP_ENABLE_PIN);
#else
    Serial.println("[AMP] SD tied to 3V3 externally");
#endif

    i2s_init();
    wifi_connect();

    ws.begin(RADIO_OS_HOST, RADIO_OS_PORT, "/audio");
    ws.onEvent(ws_event);
    ws.setReconnectInterval(3000);
    ws.enableHeartbeat(15000, 3000, 2);  // ping every 15s, pong timeout 3s, 2 retries
    Serial.printf("[WS] Connecting to ws://%s:%d/audio\n", RADIO_OS_HOST, RADIO_OS_PORT);
}

// ─── Loop ────────────────────────────────────────────────────────────────────
void loop() {
    ws.loop();

    if (!ws_connected) return;

    // Read mic (32-bit frames from INMP441, upper 16 bits are the sample)
    int32_t raw[CHUNK_SAMPLES];
    size_t bytes_read = 0;
    esp_err_t err = i2s_channel_read(rx_handle, raw, sizeof(raw), &bytes_read,
                                     pdMS_TO_TICKS(25));
    if (err != ESP_OK || bytes_read == 0) return;

    int samples_read = bytes_read / sizeof(int32_t);
    for (int i = 0; i < samples_read; i++) {
        mic_buf[i] = (int16_t)(raw[i] >> 14);
    }

    // Send raw 16-bit PCM to server for recording/monitoring
    ws.sendBIN((uint8_t*)mic_buf, samples_read * sizeof(int16_t));
}
