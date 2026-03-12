// Beep test — ES8311 official lib, MCLK_MULTIPLE_128 (matches ESP32-audioI2S default)
// Tries 4 data packing modes. Watch serial to see which mode is playing when you hear clean tone.

#include <Arduino.h>
#include <Wire.h>
#include <driver/i2s_std.h>
#include <math.h>
#include "es8311.h"

#define PIN_I2C_SDA   11
#define PIN_I2C_SCL   10
#define PIN_I2S_MCLK  12
#define PIN_I2S_BCLK  13
#define PIN_I2S_LRCLK 14
#define PIN_I2S_DIN   15
#define TCA9555_ADDR  0x20
#define SAMPLE_RATE   16000
// MCLK = 16000 * 128 = 2,048,000 Hz  (matches ESP32-audioI2S lib)
#define MCLK_HZ       (SAMPLE_RATE * 128)

i2s_chan_handle_t tx_handle = nullptr;

static void tca9555_pa_enable() {
    Wire.beginTransmission(TCA9555_ADDR);
    Wire.write(0x07); Wire.write(0xFE); Wire.endTransmission();
    Wire.beginTransmission(TCA9555_ADDR);
    Wire.write(0x03); Wire.write(0x01); Wire.endTransmission();
    delay(100);
}

static void codec_init() {
    es8311_handle_t h = es8311_create(I2C_NUM_0, ES8311_ADDRRES_0);
    const es8311_clock_config_t clk = {
        false, false, true,
        MCLK_HZ,       // mclk_frequency = 2,048,000
        SAMPLE_RATE    // sample_frequency = 16,000
    };
    esp_err_t r = es8311_init(h, &clk, ES8311_RESOLUTION_16, ES8311_RESOLUTION_16);
    int vol = 0;
    es8311_voice_volume_set(h, 90, &vol);
    es8311_microphone_config(h, false);
    es8311_voice_mute(h, false);
    Serial.printf("[CODEC] init=%d vol=%d mclk=%d\n", r, vol, MCLK_HZ);
}

static void i2s_start(i2s_data_bit_width_t bits) {
    if (tx_handle) {
        i2s_channel_disable(tx_handle);
        i2s_del_channel(tx_handle);
        tx_handle = nullptr;
    }
    i2s_chan_config_t ch = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    ch.auto_clear = true;
    i2s_new_channel(&ch, &tx_handle, nullptr);

    i2s_std_config_t cfg = {
        .clk_cfg  = {SAMPLE_RATE, I2S_CLK_SRC_DEFAULT, I2S_MCLK_MULTIPLE_128},
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(bits, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = (gpio_num_t)PIN_I2S_MCLK,
            .bclk = (gpio_num_t)PIN_I2S_BCLK,
            .ws   = (gpio_num_t)PIN_I2S_LRCLK,
            .dout = (gpio_num_t)PIN_I2S_DIN,
            .din  = I2S_GPIO_UNUSED,
            .invert_flags = {false, false, false},
        },
    };
    esp_err_t r1 = i2s_channel_init_std_mode(tx_handle, &cfg);
    esp_err_t r2 = i2s_channel_enable(tx_handle);
    Serial.printf("[I2S] bits=%d init=%d enable=%d\n", (int)bits, r1, r2);
}

static void play_tone(int mode) {
    const int N = SAMPLE_RATE * 2;  // 2 seconds
    const int CHUNK = 256;

    if (mode < 2) {
        static int16_t buf[CHUNK*2];
        for (int base = 0; base < N; base += CHUNK) {
            int n = (CHUNK < N-base) ? CHUNK : (N-base);
            for (int i = 0; i < n; i++) {
                int16_t s = (int16_t)(20000.0f * sinf(2.0f*M_PI*440.0f*(base+i)/SAMPLE_RATE));
                if (mode == 1) s = (int16_t)(((s & 0xFF) << 8) | ((s >> 8) & 0xFF));
                buf[i*2] = s; buf[i*2+1] = s;
            }
            size_t wr = 0;
            i2s_channel_write(tx_handle, buf, n*2*sizeof(int16_t), &wr, pdMS_TO_TICKS(500));
        }
    } else {
        static int32_t buf[CHUNK*2];
        for (int base = 0; base < N; base += CHUNK) {
            int n = (CHUNK < N-base) ? CHUNK : (N-base);
            for (int i = 0; i < n; i++) {
                int32_t s16 = (int32_t)(int16_t)(20000.0f * sinf(2.0f*M_PI*440.0f*(base+i)/SAMPLE_RATE));
                int32_t s = (mode == 2) ? s16 : (s16 << 16);
                buf[i*2] = s; buf[i*2+1] = s;
            }
            size_t wr = 0;
            i2s_channel_write(tx_handle, buf, n*2*sizeof(int32_t), &wr, pdMS_TO_TICKS(500));
        }
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("\n=== BEEP FORMAT SWEEP (MCLK x128) ===");
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 400000);
    codec_init();
    tca9555_pa_enable();
}

void loop() {
    Serial.println(">>> MODE 0: 16-bit slot, int16 native");
    i2s_start(I2S_DATA_BIT_WIDTH_16BIT);
    play_tone(0);
    delay(300);

    Serial.println(">>> MODE 1: 16-bit slot, int16 byte-swapped");
    i2s_start(I2S_DATA_BIT_WIDTH_16BIT);
    play_tone(1);
    delay(300);

    Serial.println(">>> MODE 2: 32-bit slot, sample in low 16 bits");
    i2s_start(I2S_DATA_BIT_WIDTH_32BIT);
    play_tone(2);
    delay(300);

    Serial.println(">>> MODE 3: 32-bit slot, sample <<16 (high bits)");
    i2s_start(I2S_DATA_BIT_WIDTH_32BIT);
    play_tone(3);
    delay(300);
}
