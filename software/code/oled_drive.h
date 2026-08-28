#ifndef _ADAFRUIT_SSD1306_H_
#define _ADAFRUIT_SSD1306_H_

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>

#define SSD1306_SWITCHCAPVCC 0x02

extern int indicatorState;
extern int dotCount;
extern bool isAsleep;
extern int zzzFrame;

extern bool isPomodoro;
extern bool isPomodoroBreak;
extern String pomodoroTime;
const uint8_t OLED_TIMER_TEXT_SIZE = 2;
extern int pomodoroAnimState; // For the intro animation
extern unsigned long pomoAnimTimer;
extern bool pomodoroPaused;   // To show paused state

extern bool isBreathingExercise;
extern String breathingTimeStr;

extern bool isHibernatingMode;
extern int currentStreak;

// DISPLAY TRANSITION ANIMATIONS
extern bool bootAnimationActive;
extern unsigned long bootAnimationStart;
extern unsigned long BOOT_ANIMATION_DURATION;
extern int breathingAnimState;
extern unsigned long breathingAnimTimer;
extern bool scoreConfettiActive;
extern unsigned long scoreConfettiStart;

// EXTERNALS FOR NEW SCORE DISPLAY
extern bool isShowingScore;
extern int pomodoroFinalScore;

static const uint8_t init_cmds[] = {
  0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 
  0x8D, 0x14, 0x20, 0x00, 0xA1, 0xC8, 0xDA, 0x12, 
  0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6, 
  0x2E, 0xAF
};

class Adafruit_SSD1306 : public Adafruit_GFX {
private:
    uint8_t buffer[1024]; 
    uint8_t i2c_addr;
public:
    Adafruit_SSD1306(int16_t w, int16_t h, TwoWire *t = &Wire, int8_t r = -1) 
      : Adafruit_GFX(w, h) {
        i2c_addr = 0x3C;
        clearDisplay();
    }

    bool begin(uint8_t vccstate = SSD1306_SWITCHCAPVCC, uint8_t addr = 0x3C, bool reset = true, bool periphBegin = true) {
        i2c_addr = addr;
        Wire.begin();
        delay(50);
        for (uint8_t i = 0; i < sizeof(init_cmds); i++) {
            Wire.beginTransmission(i2c_addr);
            Wire.write(0x00); 
            Wire.write(init_cmds[i]);
            Wire.endTransmission();
        }
        return true;
    }

    void drawPixel(int16_t x, int16_t y, uint16_t color) override {
        if ((x < 0) || (x >= width()) || (y < 0) || (y >= height())) return;
        if (color) buffer[x + (y / 8) * 128] |= (1 << (y & 7));
        else       buffer[x + (y / 8) * 128] &= ~(1 << (y & 7));
    }

    void clearDisplay() {
        memset(buffer, 0, 1024);
    }

    void display() {
        // ------------------------------------------------------------
        // BOOT / WAKE ANIMATION
        // ------------------------------------------------------------
        if (bootAnimationActive) {
            memset(buffer, 0, 1024);

            unsigned long elapsed = millis() - bootAnimationStart;

            if (elapsed < 1700) {
                // Large expanding ring. It deliberately grows beyond the
                // screen so the circle disappears completely before text.
                float p = (float)elapsed / 1700.0f;
                float ease = p * p * (3.0f - 2.0f * p);
                int radius = 2 + (int)(98.0f * ease);
                drawCircle(64, 32, radius, 1);
                drawCircle(64, 32, radius - 1, 1);
            } else {
                // "CURIE" floats in one letter at a time after the ring
                // has already expanded off-screen.
                unsigned long textElapsed = elapsed - 1700;
                const char *name = "CURIE";
                const int charCount = 5;
                const int textWidth = 60;
                const int baseX = (128 - textWidth) / 2;

                for (int i = 0; i < charCount; i++) {
                    unsigned long local = textElapsed - (unsigned long)i * 120;
                    if ((long)local < 0) continue;

                    float p = (local >= 750) ? 1.0f : (float)local / 750.0f;
                    float ease = 1.0f - (1.0f - p) * (1.0f - p) * (1.0f - p);

                    int startY = 78;
                    int targetY = 24;
                    int y = startY + (int)((targetY - startY) * ease);

                    setTextSize(2);
                    setTextColor(1);
                    setCursor(baseX + i * 12, y);
                    char c[2] = { name[i], '\0' };
                    print(c);
                }
            }

            // A small final settle gives the logo a clean finish.
            if (elapsed >= BOOT_ANIMATION_DURATION) {
                bootAnimationActive = false;
                memset(buffer, 0, 1024);
            }

        // ------------------------------------------------------------
        // HIBERNATION
        // ------------------------------------------------------------
        } else if (isHibernatingMode) {
            memset(buffer, 0, 1024);

        // ------------------------------------------------------------
        // POMODORO SCORE + CONFETTI
        // ------------------------------------------------------------
        } else if (isShowingScore) {
            memset(buffer, 0, 1024);

            setTextSize(1);
            setTextColor(1);
            setCursor(16, 12);
            print("SESSION COMPLETE");

            setTextSize(3);
            if (pomodoroFinalScore == 100) {
                setCursor(30, 32);
            } else {
                setCursor(38, 32);
            }
            print(pomodoroFinalScore);
            print("%");

            // Confetti is intentionally kept away from the score text.
            if (scoreConfettiActive) {
                unsigned long confettiElapsed = millis() - scoreConfettiStart;
                if (confettiElapsed >= 2600) {
                    scoreConfettiActive = false;
                } else {
                    float t = confettiElapsed / 1000.0f;

                    for (int i = 0; i < 22; i++) {
                        uint16_t seed = (uint16_t)(i * 197 + 53);
                        int startX = (seed * 37) % 128;
                        float vx = ((int)(seed % 11) - 5) * 0.35f;
                        float vy = 9.0f + (seed % 8) * 0.9f;
                        float startY = -((seed * 13) % 28);

                        int px = startX + (int)(vx * t * 10.0f);
                        int py = (int)(startY + vy * t + 7.5f * t * t);

                        // Keep the center clear so the score remains readable.
                        bool inScoreArea = (px > 20 && px < 108 && py > 27 && py < 58);
                        if (px >= 0 && px < 128 && py >= 0 && py < 64 && !inScoreArea) {
                            drawPixel(px, py, 1);
                            if (i % 3 == 0 && px + 1 < 128) drawPixel(px + 1, py, 1);
                            if (i % 4 == 0 && py + 1 < 64) drawPixel(px, py + 1, 1);
                        }
                    }
                }
            }

        // ------------------------------------------------------------
        // POMODORO
        // ------------------------------------------------------------
        } else if (isPomodoro) {
            // Phases 1/2/3 are text-only (no eyes ever drawn during them)
            // and always clear the whole frame. The eye-reopen phase (4)
            // is hand-drawn by sketch.ino and the settled state (5) is
            // drawn by roboEyes.update() - both happen BEFORE this runs,
            // so here we only ever touch the bottom timer strip for those,
            // never the whole buffer, or we'd erase the eyes.
            if (pomodoroAnimState == 1 || pomodoroAnimState == 2 || pomodoroAnimState == 3) {
                memset(buffer, 0, 1024);
            } else {
                fillRect(0, 48, 128, 16, 0);
            }

            const int textWidth = 84; // "- FOCUS WORK -" at text size 1
            int textX = 22;

            // pomoAnimTimer is set ONCE when the intro starts and never
            // reset per-phase, so elapsed time within a given phase has to
            // be found by subtracting that phase's start offset.
            const unsigned long POMO_SLIDE_IN = 650;
            const unsigned long POMO_HOLD = 1400;
            unsigned long introElapsed = millis() - pomoAnimTimer;

            if (pomodoroAnimState == 1) {
                // Slide in from the left.
                unsigned long elapsed = introElapsed;
                float p = elapsed >= POMO_SLIDE_IN ? 1.0f : (float)elapsed / (float)POMO_SLIDE_IN;
                float ease = 1.0f - (1.0f - p) * (1.0f - p) * (1.0f - p);
                textX = -textWidth + (int)((64 + textWidth / 2) * ease);
                setTextSize(1);
                setTextColor(1);
                setCursor(textX, 28);
                print("- FOCUS WORK -");

            } else if (pomodoroAnimState == 2) {
                // Hold the centered title while the eyes remain closed.
                setTextSize(1);
                setTextColor(1);
                setCursor(22, 28);
                print("- FOCUS WORK -");

            } else if (pomodoroAnimState == 3) {
                // Slide out to the right.
                unsigned long phaseStart = POMO_SLIDE_IN + POMO_HOLD;
                unsigned long elapsed = (introElapsed > phaseStart) ? (introElapsed - phaseStart) : 0;
                float p = elapsed >= 650 ? 1.0f : (float)elapsed / 650.0f;
                float ease = p * p * (3.0f - 2.0f * p);
                textX = 22 + (int)(106.0f * ease);
                setTextSize(1);
                setTextColor(1);
                setTextWrap(false);
                setCursor(textX, 28);
                print("- FOCUS WORK -");

            } else {
                // Normal timer, sitting in its own bottom strip below the
                // eyes (state 4's reopening eyes or state 5's settled
                // RoboEyes frame).
                setTextSize(OLED_TIMER_TEXT_SIZE);
                setTextColor(1);
                int16_t timerWidth = pomodoroTime.length() * 6 * OLED_TIMER_TEXT_SIZE;
                int16_t timerX = (128 - timerWidth) / 2;
                setCursor(timerX, 48);
                print(pomodoroTime);
            }

        // ------------------------------------------------------------
        // NORMAL UI / BREATHING
        // ------------------------------------------------------------
        } else {
            if (isAsleep) {
                setTextSize(1);
                setTextColor(1);
                if (zzzFrame > 0) { drawChar(60, 15, 'Z', 1, 0, 1); }
                if (zzzFrame > 1) { drawChar(70, 8, 'z', 1, 0, 1); }
                if (zzzFrame > 2) { drawChar(80, 2, 'z', 1, 0, 1); }
            }

            if (indicatorState == 1) {
                drawPixel(110, 60, 1); drawPixel(111, 60, 1);
                drawPixel(110, 61, 1); drawPixel(111, 61, 1);
            } else if (indicatorState == 2) {
                if (dotCount > 0) {
                    drawPixel(110, 60, 1); drawPixel(111, 60, 1);
                    drawPixel(110, 61, 1); drawPixel(111, 61, 1);
                }
                if (dotCount > 1) {
                    drawPixel(114, 60, 1); drawPixel(115, 60, 1);
                    drawPixel(114, 61, 1); drawPixel(115, 61, 1);
                }
                if (dotCount > 2) {
                    drawPixel(118, 60, 1); drawPixel(119, 60, 1);
                    drawPixel(118, 61, 1); drawPixel(119, 61, 1);
                }
            } else if (indicatorState == 3) {
                fillRect(115, 48, 2, 8, 1);
                fillRect(115, 58, 2, 2, 1);
            }

            if (isBreathingExercise) {
                // Move timer to the bottom strip to match Pomodoro
                fillRect(0, 48, 128, 16, 0);
                setTextSize(OLED_TIMER_TEXT_SIZE);
                setTextColor(1);
                int16_t timerWidth = breathingTimeStr.length() * 6 * OLED_TIMER_TEXT_SIZE;
                int16_t timerX = (128 - timerWidth) / 2;
                setCursor(timerX, 48); // Set to Y: 48
                print(breathingTimeStr);

                if (breathingAnimState == 1 || breathingAnimState == 2 || breathingAnimState == 3) {
                    const int textWidth = 66; // "- BREATHE -" is 11 chars (11 * 6 = 66px)
                    int textX = 31; // Perfectly centered: (128 - 66) / 2
                    unsigned long elapsed = millis() - breathingAnimTimer;

                    if (breathingAnimState == 1) {
                        float p = elapsed >= 700 ? 1.0f : (float)elapsed / 700.0f;
                        float ease = 1.0f - (1.0f - p) * (1.0f - p) * (1.0f - p);
                        textX = -textWidth + (int)((64 + textWidth / 2) * ease);
                    } else if (breathingAnimState == 2) {
                        textX = 31; // Hold at center
                    } else {
                        unsigned long outElapsed = elapsed > 1800 ? elapsed - 1800 : 0;
                        float p = outElapsed >= 700 ? 1.0f : (float)outElapsed / 700.0f;
                        float ease = p * p * (3.0f - 2.0f * p);
                        textX = 31 + (int)(97.0f * ease); // Slide cleanly off the right edge
                    }

                    // FORCE SIZE 1 SO IT MATCHES POMODORO
                    setTextSize(1);
                    setTextColor(1);
                    setTextWrap(false);
                    setCursor(textX, 28);
                    print("- BREATHE -");
                }
            }
        }

        Wire.beginTransmission(i2c_addr);
        Wire.write(0x00); Wire.write(0x21); Wire.write(0); Wire.write(127);
        Wire.write(0x22); Wire.write(0); Wire.write(7);
        Wire.endTransmission();

        for (uint16_t i = 0; i < 1024; ) {
            Wire.beginTransmission(i2c_addr);
            Wire.write(0x40);
            for (uint8_t x = 0; x < 16; x++) {
                Wire.write(buffer[i++]);
            }
            Wire.endTransmission();
        }
    }
};
#endif
