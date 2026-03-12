#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <ESPmDNS.h>
#include <WebSocketsClient.h>
#include <driver/i2s_std.h>
#include <math.h>
#include "config.h"

// ─── Globals ─────────────────────────────────────────────────────────────────
WebSocketsClient ws;
bool ws_connected = false;

const int CHUNK_SAMPLES = (SAMPLE_RATE * AUDIO_CHUNK_MS) / 1000;  // 320 @ 16kHz/20ms
int16_t mic_buf[CHUNK_SAMPLES];

i2s_chan_handle_t rx_handle = nullptr;
i2s_chan_handle_t tx_handle = nullptr;

String boot_log;
bool   boot_log_sent = false;

// Resolved Radio OS server IP (populated by wifi_connect via mDNS)
IPAddress radioos_ip;

// Debug: send text over websocket so we can see it on the Pi
void ws_log(const char* fmt, ...) {
    char buf[512];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);
    Serial.print(buf);
    if (!ws_connected) {
        // Only buffer/send before connection — after connect all WS sends
        // must go through _puck_sender to avoid concurrent-write crashes
        boot_log += buf;
    }
}

// ─── ES8311 codec (DAC/amp) — init via I2C ───────────────────────────────────
#if defined(BOARD_S3_AUDIO)

static void es8311_write(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(ES8311_ADDR);
    Wire.write(reg);
    Wire.write(val);
    Wire.endTransmission();
}

static uint8_t es8311_read(uint8_t reg) {
    Wire.beginTransmission(ES8311_ADDR);
    Wire.write(reg);
    Wire.endTransmission(false);
    Wire.requestFrom((uint8_t)ES8311_ADDR, (uint8_t)1);
    return Wire.available() ? Wire.read() : 0xFF;
}

static void es8311_init() {
    ws_log("[ES8311] Initialising DAC codec...\n");
    uint8_t id = es8311_read(0xFD);
    ws_log("[ES8311] chip_id=0x%02X (expect 0x83)\n", id);

    // Reset
    es8311_write(0x00, 0x1F); delay(10);
    es8311_write(0x00, 0x00); delay(10);

    // --- Clock config for MCLK=4.096MHz (256fs), rate=16kHz ---
    // Source: Espressif ESP-ADF coeff_div[] table, entry {4096000, 16000}
    // pre_div=1, pre_multi=1, adc_div=1, dac_div=1
    // fs_mode=0 (single speed), lrck_h=0x00, lrck_l=0xFF, bclk_div=4
    // adc_osr=0x10, dac_osr=0x20

    // REG01: MCLK from I2S MCLK pin, not inverted
    es8311_write(0x01, 0x30);
    // REG02: pre_div=1 (bits[7:5]=0b000), pre_multi=1 (bits[4:3]=0b00)
    es8311_write(0x02, 0x00);
    // REG03: fs_mode=0, adc_osr=0x10
    es8311_write(0x03, 0x10);
    // REG04: dac_osr=0x20
    es8311_write(0x04, 0x20);
    // REG05: adc_div=1 (bits[7:4]=0x0), dac_div=1 (bits[3:0]=0x0)
    es8311_write(0x05, 0x00);
    // REG06: BCLK divider = 4 → BCLK = MCLK/4 = 1.024MHz = 32*2*16kHz ✓
    es8311_write(0x06, 0x04);
    // REG07/08: LRCLK divider MSB=0x00, LSB=0xFF → div=256 from MCLK side
    // (BCLK/64 = 1.024MHz/64 = 16kHz ✓)
    es8311_write(0x07, 0x00);
    es8311_write(0x08, 0xFF);

    // I2S format: standard Philips I2S, 32-bit word length
    // REG09 = SDP In (ESP→codec): bits[4:2]=100 = 32-bit
    // REG0A = SDP Out (codec→ESP): bits[4:2]=100 = 32-bit
    es8311_write(0x09, 0x10);  // 32-bit in
    es8311_write(0x0A, 0x10);  // 32-bit out (was 0x0C = 24-bit mismatch)

    // Power management: normal operation
    es8311_write(0x0D, 0x01);
    // DAC power on
    es8311_write(0x12, 0x00);
    // DAC volume: 0xBF = ~75% (REG32: 0x00=min, 0xFF=0dB per ES8311 datasheet)
    es8311_write(0x32, 0xBF);
    // REG31: DAC mute OFF — bits[6:5] = 0b00 = unmuted (default may be muted)
    es8311_write(0x31, 0x00);
    // REG37: bypass DAC equalizer (bit3=1), fade normal — matches Waveshare library
    es8311_write(0x37, 0x08);
    // Output driver on
    es8311_write(0x44, 0x08);
    es8311_write(0x45, 0x00);
    // Speaker/headphone output enable (REG13: enable DAC to mixer)
    es8311_write(0x13, 0x10);

    ws_log("[ES8311] Init complete\n");
}

// ─── TCA9555 I/O expander — amp (PA) enable ──────────────────────────────────
// The on-board Class-D amplifier power-amp enable is routed through the TCA9555
// GPIO expander at I2C 0x20.  EXIO8 = Port-1 bit-0.
// Confirmed from Waveshare official demo: Audio_ES8311.cpp → Audio_PA_EN()
//   Set_EXIO(TCA9555_EXIO8, true)   (TCA9555_EXIO8 = 8)
//
// TCA9555 register map:
//   0x02 Output Port 0,  0x03 Output Port 1
//   0x06 Config Port 0,  0x07 Config Port 1  (0=output, 1=input)
#define TCA9555_ADDR  0x20

static void tca9555_pa_enable() {
    // EXIO8 = Port-1 bit-0.  No read-modify-write — just write both registers.
    // Config Port 1 (reg 0x07): bit0=0 → output, all others stay input (1)
    Wire.beginTransmission(TCA9555_ADDR);
    Wire.write(0x07);
    Wire.write(0xFE);  // 1111 1110 — pin 8 as output
    Wire.endTransmission();

    // Output Port 1 (reg 0x03): bit0=1 → HIGH → amp enabled
    Wire.beginTransmission(TCA9555_ADDR);
    Wire.write(0x03);
    Wire.write(0x01);  // pin 8 HIGH
    Wire.endTransmission();

    delay(50);
    ws_log("[TCA9555] PA (EXIO8) enabled\n");
}

static uint8_t tca9555_read(uint8_t reg) {
    Wire.beginTransmission(TCA9555_ADDR);
    Wire.write(reg);
    Wire.endTransmission(false);
    Wire.requestFrom((uint8_t)TCA9555_ADDR, (uint8_t)1);
    return Wire.available() ? Wire.read() : 0xFF;
}

static void tca9555_dump() {
    Serial.printf("[TCA9555] IN0=0x%02X IN1=0x%02X OUT0=0x%02X OUT1=0x%02X CFG0=0x%02X CFG1=0x%02X\n",
        tca9555_read(0x00), tca9555_read(0x01),
        tca9555_read(0x02), tca9555_read(0x03),
        tca9555_read(0x06), tca9555_read(0x07));
    // Also dump the ES8311 DAC registers that control mute and volume
    Serial.printf("[ES8311] REG31(mute)=0x%02X REG32(vol)=0x%02X REG37(eq)=0x%02X\n",
        es8311_read(0x31), es8311_read(0x32), es8311_read(0x37));
}

// ─── ES7210 codec (quad mic ADC) — init via I2C ──────────────────────────────
static void es7210_write(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(ES7210_ADDR);
    Wire.write(reg);
    Wire.write(val);
    Wire.endTransmission();
}

static void es7210_init() {
    ws_log("[ES7210] Initialising ADC codec...\n");

    // Full reset — hold then release
    es7210_write(0x00, 0xFF); delay(20);
    es7210_write(0x00, 0x32); delay(20);  // normal operation (not 0x71 which keeps some resets)

    // Clock: MCLK=256fs, 16kHz → MCLK=4.096MHz
    // MCLK_PRED divider register (0x02): MCLK = pin / (PRED+1)
    es7210_write(0x02, 0x00);  // MCLK predivider = /1
    // MCLK_POSTD (0x03): post-divider
    es7210_write(0x03, 0x00);  // postdivider = /1

    // LRCK divider = MCLK / (256) for 16kHz: 0x06=MSB 0x07=LSB of LRCK div
    es7210_write(0x06, 0x00);  // LRCK div high = 0
    es7210_write(0x07, 0xFF);  // LRCK div low = 255 → div=256

    // I2S serial port format: standard I2S, 32-bit word length
    // Reg 0x11: bits[2:0]=data_len, bits[5:4]=mode
    // mode=00 (I2S standard), data_len=11 (32-bit) → 0x03
    es7210_write(0x11, 0x03);  // I2S standard, 32-bit

    // Mic power and bias
    es7210_write(0x40, 0xC3);  // MIC1/MIC2 differential, bias on
    es7210_write(0x41, 0x70);  // MIC1 gain = +30dB
    es7210_write(0x42, 0x70);  // MIC2 gain = +30dB
    es7210_write(0x43, 0x1B);  // MIC1 analog gain
    es7210_write(0x44, 0x1B);  // MIC2 analog gain

    // ADC enable: channels 1+2
    es7210_write(0x04, 0x03);  // enable ADC1 + ADC2

    // Power on (clear sleep bits)
    es7210_write(0x01, 0x00);  delay(10);

    ws_log("[ES7210] Init complete\n");
}

// ─── I2S init with MCLK for codec board ──────────────────────────────────────
static void i2s_init() {
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    chan_cfg.auto_clear = true;

    esp_err_t err = i2s_new_channel(&chan_cfg, &tx_handle, &rx_handle);
    ws_log("[I2S] new_channel err=0x%x  tx=%p rx=%p\n", err, tx_handle, rx_handle);

    i2s_std_config_t std_cfg = {
        .clk_cfg = {
            .sample_rate_hz = SAMPLE_RATE,
            .clk_src        = I2S_CLK_SRC_DEFAULT,
            .mclk_multiple  = I2S_MCLK_MULTIPLE_256,
        },
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT,
                                                         I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = (gpio_num_t)PIN_I2S_MCLK,
            .bclk = (gpio_num_t)PIN_I2S_BCLK,
            .ws   = (gpio_num_t)PIN_I2S_LRCLK,
            .dout = (gpio_num_t)PIN_I2S_DIN,    // DIN = data in to codec (from ESP)
            .din  = (gpio_num_t)PIN_I2S_DOUT,   // DOUT = data out of codec (to ESP)
            .invert_flags = { .mclk_inv = false, .bclk_inv = false, .ws_inv = false },
        },
    };

    esp_err_t e1 = i2s_channel_init_std_mode(tx_handle, &std_cfg);
    esp_err_t e2 = i2s_channel_init_std_mode(rx_handle, &std_cfg);
    esp_err_t e3 = i2s_channel_enable(tx_handle);
    esp_err_t e4 = i2s_channel_enable(rx_handle);

    ws_log("[I2S] init_tx=0x%x init_rx=0x%x en_tx=0x%x en_rx=0x%x\n", e1, e2, e3, e4);
    ws_log("[I2S] MCLK=%d BCLK=%d LRCLK=%d DIN=%d DOUT=%d\n",
           PIN_I2S_MCLK, PIN_I2S_BCLK, PIN_I2S_LRCLK, PIN_I2S_DIN, PIN_I2S_DOUT);
    ws_log("[I2S] Rate=%d Philips 32-bit stereo\n", SAMPLE_RATE);

    if (e1 == ESP_OK && e2 == ESP_OK && e3 == ESP_OK && e4 == ESP_OK) {
        ws_log("[I2S] Full-duplex I2S0 OK\n");
    } else {
        ws_log("[I2S] *** INIT FAILED ***\n");
    }
}

// ─── Board init: I2C scan + codec init + I2S ─────────────────────────────────
static void board_init() {
    // I2C bus
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 400000);
    ws_log("[I2C] Bus started: SDA=%d SCL=%d\n", PIN_I2C_SDA, PIN_I2C_SCL);

    // Scan to verify codecs are present
    int found = 0;
    for (uint8_t addr = 0x08; addr < 0x78; addr++) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
            ws_log("[I2C] Found device at 0x%02X\n", addr);
            found++;
        }
    }
    ws_log("[I2C] Scan complete: %d device(s) found\n", found);

    // Init codecs
    es8311_init();
    es7210_init();

    // Enable the on-board power amplifier via TCA9555 GPIO expander (EXIO8)
    tca9555_pa_enable();

    // Init I2S (after codecs are configured)
    i2s_init();
}

#else  // ─── Non-codec board (C6 / bare ESP32) ──────────────────────────────

static void i2s_init() {
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    chan_cfg.auto_clear = true;

    esp_err_t err = i2s_new_channel(&chan_cfg, &tx_handle, &rx_handle);
    ws_log("[I2S] new_channel err=0x%x  tx=%p rx=%p\n", err, tx_handle, rx_handle);

    i2s_std_config_t std_cfg = {
        .clk_cfg  = I2S_STD_CLK_DEFAULT_CONFIG(SAMPLE_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT,
                                                         I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = (gpio_num_t)PIN_I2S_BCLK,
            .ws   = (gpio_num_t)PIN_I2S_LRCLK,
            .dout = (gpio_num_t)PIN_I2S_DIN,
            .din  = (gpio_num_t)PIN_I2S_DOUT,
            .invert_flags = { .mclk_inv = false, .bclk_inv = false, .ws_inv = false },
        },
    };

    esp_err_t e1 = i2s_channel_init_std_mode(tx_handle, &std_cfg);
    esp_err_t e2 = i2s_channel_init_std_mode(rx_handle, &std_cfg);
    esp_err_t e3 = i2s_channel_enable(tx_handle);
    esp_err_t e4 = i2s_channel_enable(rx_handle);

    ws_log("[I2S] init_tx=0x%x init_rx=0x%x en_tx=0x%x en_rx=0x%x\n", e1, e2, e3, e4);
    ws_log("[I2S] BCLK=%d LRCLK=%d DOUT=%d DIN=%d\n",
           PIN_I2S_BCLK, PIN_I2S_LRCLK, PIN_I2S_DIN, PIN_I2S_DOUT);
}

static void board_init() {
    i2s_init();
}

#endif  // BOARD_S3_AUDIO

// ─── Play stereo I2S32 bytes from Pi directly to I2S TX ──────────────────────
// Pi sends stereo 32-bit MSB-aligned PCM (already expanded by _pcm16_to_i2s32)
static void play_i2s32_chunk(const uint8_t* data, size_t len) {
    const size_t MAX_CHUNK = CHUNK_SAMPLES * 2 * sizeof(int32_t);
    size_t offset = 0;
    while (offset < len) {
        size_t batch = min(len - offset, MAX_CHUNK);
        size_t written = 0;
        i2s_channel_write(tx_handle, data + offset, batch, &written, pdMS_TO_TICKS(200));
        offset += batch;
    }
}

// ─── WebSocket events ────────────────────────────────────────────────────────
static bool mic_streaming = false;  // gated by CMD:MIC_START / CMD:MIC_STOP

void ws_event(WStype_t type, uint8_t* payload, size_t length) {
    switch (type) {
        case WStype_CONNECTED:
            ws_connected = true;
            mic_streaming = false;  // don't stream mic until server asks
            {
                char hello[32];
                snprintf(hello, sizeof(hello), "HELLO:node%d", NODE_ID);
                ws.sendTXT(hello);
                // HELLO is the ONLY direct send allowed — happens before
                // _puck_sender task starts so there's no concurrent writer yet.
            }
            // Boot log: already visible on Serial, don't send over WS
            // (would race with _puck_sender task that starts after ACK arrives)
            boot_log = "";
            boot_log_sent = true;
            break;

        case WStype_DISCONNECTED:
            ws_connected = false;
            mic_streaming = false;
            break;

        case WStype_BIN: {
            // Server sends stereo I2S32 (expanded by _pcm16_to_i2s32 server-side)
            static uint32_t bin_count = 0;
            static size_t bin_bytes = 0;
            bin_count++;
            bin_bytes += length;
            if (bin_count % 50 == 1) {  // log every 50 frames (~1s)
                Serial.printf("[BIN] frame=%u  total_bytes=%u  len=%u\n",
                              bin_count, (unsigned)bin_bytes, (unsigned)length);
            }
            play_i2s32_chunk(payload, length);
            break;
        }

        case WStype_TEXT: {
            const char* cmd = (const char*)payload;
            if (strcmp(cmd, "CMD:REBOOT") == 0) {
                ws_log("[CMD] Rebooting\n");
                delay(200);
                ESP.restart();
            } else if (strcmp(cmd, "CMD:TONE") == 0) {
                // Local test tone — run in a task so WS loop isn't blocked
                Serial.printf("[CMD] Tone requested\n");
                tca9555_dump();
                xTaskCreate([](void*) {
                    const int sr = 16000, dur_ms = 2000;
                    const int total = sr * dur_ms / 1000;
                    const int chunk = 320;
                    int32_t buf[chunk * 2];
                    for (int base = 0; base < total; base += chunk) {
                        int n = min(chunk, total - base);
                        for (int i = 0; i < n; i++) {
                            int32_t s = (int32_t)(16383 * sinf(2.0f * M_PI * 440.0f * (base + i) / sr)) << 16;
                            buf[i*2]   = s;
                            buf[i*2+1] = s;
                        }
                        size_t written = 0;
                        i2s_channel_write(tx_handle, buf, n * 2 * sizeof(int32_t), &written, pdMS_TO_TICKS(200));
                    }
                    Serial.printf("[CMD] Tone done\n");
                    vTaskDelete(NULL);
                }, "tone", 4096, nullptr, 5, nullptr);
            } else if (strcmp(cmd, "CMD:MIC_START") == 0) {
                mic_streaming = true;
            } else if (strcmp(cmd, "CMD:MIC_STOP") == 0) {
                mic_streaming = false;
            }
            break;
        }

        default:
            break;
    }
}

// ─── WiFi + mDNS server discovery ────────────────────────────────────────────
void wifi_connect() {
    Serial.printf("[WiFi] Connecting to %s\n", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    int tries = 0;
    while (WiFi.status() != WL_CONNECTED && tries < 40) {
        delay(500);
        tries++;
    }
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[WiFi] Failed — rebooting");
        delay(1000);
        ESP.restart();
    }
    Serial.printf("[WiFi] Connected  IP=%s\n", WiFi.localIP().toString().c_str());

    // Resolve radioos.local via mDNS — connects to whichever machine is running Radio OS
    if (!MDNS.begin("puck")) {
        ws_log("[mDNS] Failed to start\n");
    }
    ws_log("[mDNS] Resolving " RADIOOS_MDNS_HOST "...\n");
    radioos_ip = MDNS.queryHost(RADIOOS_MDNS_HOST, 3000);  // 3s timeout
    if (radioos_ip == INADDR_NONE || radioos_ip == IPAddress(0,0,0,0)) {
        ws_log("[mDNS] Not found — falling back to %s\n", RADIOOS_FALLBACK_HOST);
        radioos_ip.fromString(RADIOOS_FALLBACK_HOST);
    } else {
        ws_log("[mDNS] Resolved to %s\n", radioos_ip.toString().c_str());
    }
}

// ─── Setup ───────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(500);
    ws_log("[Boot] Node %d  board=S3-AUDIO\n", NODE_ID);

    board_init();  // I2C scan, ES8311, ES7210, I2S

    wifi_connect();  // sets radioos_ip

    ws.begin(radioos_ip.toString().c_str(), RADIO_OS_PORT, "/audio");
    ws.onEvent(ws_event);
    ws.setReconnectInterval(3000);
    // Do NOT use enableHeartbeat — Starlette doesn't respond to WS protocol pings
    // so the library would declare the connection dead every ~21s.
    // Text PING/PONG in the app protocol handles keepalive instead.
    ws_log("[WS] Connecting to %s:%d\n", radioos_ip.toString().c_str(), RADIO_OS_PORT);
}

// ─── Loop ────────────────────────────────────────────────────────────────────
void loop() {
    ws.loop();

    // Send text PING every 10s to keep server's 60s receive-timeout alive
    static uint32_t last_ping_ms = 0;
    if (ws_connected && (millis() - last_ping_ms) >= 10000) {
        ws.sendTXT("PING");
        last_ping_ms = millis();
    }

    // Always drain the I2S RX buffer to prevent overflow — ES7210 fills it regardless
    static int32_t raw[CHUNK_SAMPLES];
    size_t bytes_read = 0;
    esp_err_t err = i2s_channel_read(rx_handle, raw, sizeof(raw), &bytes_read,
                                     pdMS_TO_TICKS(25));
    if (err != ESP_OK || bytes_read == 0 || !ws_connected || !mic_streaming) return;

    // ES7210 stereo 32-bit → take left channel, shift down to 16-bit
    int frames = bytes_read / sizeof(int32_t);
    int mono_count = 0;
    for (int i = 0; i < frames; i += 2) {
        mic_buf[mono_count++] = (int16_t)(raw[i] >> 8);
    }

    if (mono_count > 0) {
        ws.sendBIN((uint8_t*)mic_buf, mono_count * sizeof(int16_t));
    }
}
