#include <Arduino.h>
#include <Wire.h>
#include <Servo.h>
#include "Adafruit_SSD1306.h"
#include <FluxGarage_RoboEyes.h>
#include <Arduino_RouterBridge.h>

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1

int indicatorState = 0; 
int dotCount = 0;
bool isAsleep = false;
int zzzFrame = 0;

bool isPomodoro = false;
bool isPomodoroBreak = false;
String pomodoroTime = "00:00";

int pomodoroAnimState = 0;
unsigned long pomoAnimTimer = 0;
bool pomodoroPaused = false;

bool isBreathingExercise = false;
String breathingTimeStr = "00:00";

bool isHibernatingMode = false;
bool isNotificationActive = false;
unsigned long notificationStartTime = 0;
bool reducedMotionMode = false;

// SCORE DISPLAY VARIABLES
bool isShowingScore = false;
int pomodoroFinalScore = 0;
unsigned long scoreDisplayTimer = 0;

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);
RoboEyes<Adafruit_SSD1306> roboEyes(display);

#define PIN_TOUCH_PET 2
#define PIN_TOUCH_SPEAK 3
#define PIN_SERVO_PAN 5
Servo panServo;

// KINEMATICS — single remaining pan axis
float currentPan = 90.0;
float startPan = 90.0;
float targetPan = 90.0;
unsigned long moveStartTime = 0;
float moveDuration = 1000.0;
int moveCurve = 0; 

unsigned long lastServoCalcTime = 0;
unsigned long lastServoActiveTime = 0;

// PETTING STATE TIMERS
unsigned long petStartTime = 0;
int petStage = 0; 
bool isReleasingPet = false;
unsigned long petReleaseTime = 0;
float petBasePan = 90.0f;

bool isListening = false;
bool isProcessing = false;

// STARTLE TIMERS
bool startleActive = false;
int startleStep = 0;
unsigned long startleTimer = 0;

int lookingDir = -1;
unsigned long lookDirTimer = 0;

unsigned long lastInteractionTime = 0;

// DANCE PARTY STATE VARIABLES
bool isDancing = false;
unsigned long lastDanceStepTime = 0; 
int danceState = 0; 
float dancePanRange = 0.0;
float maxDancePanRange = 25.0;
bool sweepRight = true;
int currentDanceType = 0;
unsigned long danceStartTime = 0;

// HUMOR
int humorLevel = 5;

// STREAK
int currentStreak = 0;

// POMODORO LIVE FOCUS LEVEL
int currentFocusLevel = -1;
unsigned long sweatUntil = 0;

// BREATHING STATE VARIABLES
unsigned long breathingStartTime = 0;
unsigned long breathingDuration = 120000;
bool breathingPaused = false;
unsigned long breathingPauseStart = 0;
unsigned long breathingPausedAccum = 0; 
unsigned long lastBreathingCycleTime = 0;
int breathingCycleState = 0; 
float breathEyeSize = 30.0;

unsigned long lastZzzTime = 0;
unsigned long lastDotTime = 0;

int minIdleSec = 4;
int maxIdleSec = 8;
unsigned long lastServoIdleMove = 0;
unsigned long nextServoIdleInterval = 4000;
unsigned long startupSuppressUntil = 0;
unsigned long lastSoundMovementTime = 0;

// DISPLAY TRANSITION ANIMATIONS
bool bootAnimationActive = false;
bool linuxReady = false;
unsigned long bootAnimationStart = 0;
unsigned long BOOT_ANIMATION_DURATION = 3400;

int breathingAnimState = 0;
unsigned long breathingAnimTimer = 0;

bool scoreConfettiActive = false;
unsigned long scoreConfettiStart = 0;

bool noddingActive = false;
unsigned long lastNodStepTime = 0;
int nodStep = 0;

bool headShakeActive = false;
unsigned long lastShakeStepTime = 0;
int shakeStep = 0;

unsigned long petActiveTime = 0;
unsigned long speakActiveTime = 0;
bool pomoPetHandled = false;
bool pomoSpeakHandled = false;

// IDLE MICRO-JITTER
float jitterOffsetPan = 0;
float jitterTargetPan = 0;
unsigned long lastJitterPick = 0;
unsigned long nextJitterInterval = 400;

// CONFETTI
bool confettiActive = false;
unsigned long confettiStartTime = 0;
int confettiTier = 0;
struct ConfettiParticle { float x, y, vx, vy; };
const int CONFETTI_COUNT = 14;
ConfettiParticle confetti[CONFETTI_COUNT];

// STREAK FLAME ICON
const unsigned char PROGMEM flameIcon8x8[] = {
  0x18, 0x3C, 0x7E, 0x7E, 0xFC, 0x7E, 0x3C, 0x18
};

void moveTo(float pPan, float duration, int curve) {
    if (reducedMotionMode) return;
    startPan = currentPan;
    targetPan = constrain(pPan, 45.0f, 135.0f);
    moveDuration = max(80.0f, duration);
    moveCurve = curve;
    moveStartTime = millis();
}

void set_indicator(int state) { 
    if (startleActive || isHibernatingMode || isNotificationActive) return; 
    indicatorState = state; 
}

void set_processing_state(int state) {
    if (isHibernatingMode) return;
    if (state == 1) {
        isProcessing = true;
        roboEyes.setPosition(N); 
        moveTo(constrain(currentPan + 15.0f, 45.0f, 135.0f), 800, 0); 
    } else {
        isProcessing = false;
        roboEyes.setPosition(DEFAULT);
        moveTo(currentPan, 500, 0); 
    }
}

void look_direction(int dir) {
    if (isAsleep || isPomodoro || isBreathingExercise || isHibernatingMode) return; 
    lookingDir = dir;
    lookDirTimer = millis();
    roboEyes.setHeight(30, 30);
    
    if(dir == 0) { moveTo(50, 800, 0); roboEyes.setPosition(W); }  
    if(dir == 1) { moveTo(130, 800, 0); roboEyes.setPosition(E); } 
    if(dir == 2) { moveTo(75, 800, 0); roboEyes.setPosition(N); }   
    if(dir == 3) { moveTo(105, 800, 0); roboEyes.setPosition(S); }  
}

void set_behavior_toggles(int s_en) { }

void set_curie_mood(int mood) {
    if (startleActive || isHibernatingMode || isDancing) return; 
    roboEyes.setHeight(30, 30); 
    if (mood == 1) { roboEyes.setMood(HAPPY); } 
    else if (mood == 2) { roboEyes.setMood(TIRED); } 
    else if (mood == 3) { roboEyes.setMood(ANGRY); } 
    else if (mood == 4) { roboEyes.setMood(DEFAULT); roboEyes.anim_confused(); } 
    else if (mood == 5) { roboEyes.setMood(HAPPY); roboEyes.anim_laugh(); } 
    else { roboEyes.setMood(DEFAULT); }
}

void done_speaking() {
    if (startleActive || isHibernatingMode || isDancing) return; 
    roboEyes.setHeight(30, 30);
    roboEyes.setMood(DEFAULT);
    moveTo(constrain(currentPan - 15.0f, 45.0f, 135.0f), 600, 0); 
}

void startBootAnimation() {
    linuxReady = true;
    bootAnimationActive = true;
    bootAnimationStart = millis();
    startupSuppressUntil = bootAnimationStart + BOOT_ANIMATION_DURATION;
    roboEyes.setIdleMode(OFF, 0, 0);
    roboEyes.setHeight(0, 0);
    roboEyes.setWidth(0, 0);
}

void update_pomodoro(int mins, int secs, int isBreak, int isPaused) {
    if (!isPomodoro) {
        isPomodoro = true;
        pomodoroAnimState = 1;
        pomoAnimTimer = millis();
        roboEyes.setIdleMode(OFF, 0, 0);
        roboEyes.setHeight(0, 0);
        roboEyes.setWidth(0, 0);
    }
    isPomodoroBreak = (isBreak == 1);
    pomodoroPaused = (isPaused == 1);
    char buf[10];
    sprintf(buf, "%02d:%02d", mins, secs);
    pomodoroTime = String(buf);
}

void stop_pomodoro() {
    isPomodoro = false;
    pomodoroAnimState = 0;
    roboEyes.setMood(DEFAULT);
    roboEyes.setHeight(30, 30);
    roboEyes.setWidth(30, 30);
    roboEyes.setSweat(false);
    roboEyes.setIdleMode(ON, 2, 2);
    currentFocusLevel = -1;
}

void start_breathing_exercise(int durationSec) {
    if (isHibernatingMode) return;
    if (isBreathingExercise) {
        breathingStartTime = millis();
        breathingDuration = (unsigned long)durationSec * 1000;
        breathingPaused = false;
        breathingPauseStart = 0;
        breathingPausedAccum = 0;
        return;
    }
    isBreathingExercise = true;
    breathingStartTime = millis();
    breathingDuration = (unsigned long)durationSec * 1000;
    breathingPaused = false;
    breathingPauseStart = 0;
    breathingPausedAccum = 0;
    lastBreathingCycleTime = millis();
    breathingCycleState = 0;
    breathEyeSize = 30.0;

    breathingAnimState = 1;
    breathingAnimTimer = millis();

    roboEyes.setMood(DEFAULT);
    roboEyes.setPosition(DEFAULT);
    roboEyes.setIdleMode(OFF, 0, 0);
    roboEyes.setHeight(0, 0);
    roboEyes.setWidth(0, 0);
}

void stop_breathing_exercise() {
    isBreathingExercise = false;
    breathingPaused = false;
    breathingPauseStart = 0;
    breathingPausedAccum = 0;
    breathingAnimState = 0;
    roboEyes.setHeight(30, 30);
    roboEyes.setWidth(30, 30);
    roboEyes.setPosition(DEFAULT);
    roboEyes.setAutoblinker(ON, 3, 2);
    roboEyes.setIdleMode(ON, 2, 2);
    Bridge.notify("breathing_finished");
}


void set_dance_state(int state) {
    if (isBreathingExercise || isHibernatingMode) return; 
    isDancing = (state == 1);
    if (isDancing) {
        roboEyes.setMood(HAPPY);
        roboEyes.setAutoblinker(OFF); 
        lastDanceStepTime = millis();
        danceState = 0;
        dancePanRange = 0.0;
        sweepRight = true;
        currentDanceType = random(0, 3);
        danceStartTime = millis();
    } else {
        roboEyes.setMood(DEFAULT);
        roboEyes.setAutoblinker(ON, 3, 2); 
        moveTo(90, 1000, 0);
    }
}

void trigger_startle() {
    if (isHibernatingMode) return;
    if (millis() - lastServoActiveTime < 1500) return; 
    
    isAsleep = false;
    startleActive = true;
    startleStep = 0;
    
    roboEyes.setMood(TIRED); 
    roboEyes.setHeight(30, 15);
    roboEyes.setIdleMode(ON, 2, 2);
    
    moveTo(90, 150, 2); 
    
    headShakeActive = true;
    shakeStep = 0;
    lastShakeStepTime = millis();
    
    startleTimer = millis();
    Bridge.notify("woke_up"); 
}

void trigger_sound_movement() {
    if (isHibernatingMode || isAsleep || isPomodoro || isBreathingExercise || reducedMotionMode) return;
    if (millis() - lastSoundMovementTime < 5000) return;
    if (millis() - lastServoActiveTime < 700) return;
    lastSoundMovementTime = millis();
    float basePan = constrain(currentPan + 10.0, 55.0, 125.0);
    moveTo(basePan, 250, 0);
}

void set_idle_config(int minSec, int maxSec) {
    minIdleSec = minSec; maxIdleSec = maxSec;
    nextServoIdleInterval = random(minIdleSec * 1000, maxIdleSec * 1000);
}

void startConfetti(int tier) {
    if (isHibernatingMode) return;
    confettiActive = true;
    confettiTier = tier;
    confettiStartTime = millis();
    for (int i = 0; i < CONFETTI_COUNT; i++) {
        float angle = random(0, 360) * PI / 180.0;
        float speed = random(20, tier == 1 ? 55 : 40) / 10.0;
        confetti[i].x = 64; confetti[i].y = 32;
        confetti[i].vx = cos(angle) * speed;
        confetti[i].vy = sin(angle) * speed;
    }
}

void reactToPhone(int tier) {
    if (isHibernatingMode || startleActive || isBreathingExercise) return;
    if (tier == 1) {
        moveTo(currentPan + (currentPan < 90 ? -10 : 10), 300, 0);
    } else if (tier == 2) {
        roboEyes.setMood(DEFAULT);
        moveTo(constrain(currentPan + 15.0f, 45.0f, 135.0f), 400, 0);
    } else {
        roboEyes.setSweat(true);
        sweatUntil = millis() + 6000;
        moveTo(constrain(currentPan - 10.0f, 45.0f, 135.0f), 250, 0);
    }
}

void setup() {
    Bridge.begin();
    Bridge.provide("start_boot_animation", [](int state) {
        if (state) startBootAnimation();
    });
    Bridge.provide("set_idle_config", set_idle_config);
    Bridge.provide("set_curie_mood", set_curie_mood); 
    Bridge.provide("set_indicator", set_indicator); 
    Bridge.provide("set_behavior_toggles", set_behavior_toggles);
    Bridge.provide("look_direction", look_direction); 
    Bridge.provide("set_processing_state", set_processing_state); 
    Bridge.provide("done_speaking", done_speaking); 
    Bridge.provide("trigger_startle", trigger_startle);
    Bridge.provide("trigger_sound_movement", trigger_sound_movement); 
    Bridge.provide("set_dance_state", set_dance_state); 
    Bridge.provide("update_pomodoro", update_pomodoro); 
    Bridge.provide("stop_pomodoro", stop_pomodoro); 
    Bridge.provide("start_breathing_exercise", start_breathing_exercise);
    Bridge.provide("stop_breathing_exercise", stop_breathing_exercise);
    Bridge.provide("pause_breathing_exercise", [](int state) {
        if (state == 1) {
            if (!breathingPaused) { breathingPaused = true; breathingPauseStart = millis(); }
        } else {
            if (breathingPaused) {
                if (breathingPauseStart > 0) breathingPausedAccum += millis() - breathingPauseStart;
                breathingPauseStart = 0;
                breathingPaused = false;
                lastBreathingCycleTime = millis();
            }
        }
    });

    Bridge.provide("update_streak", [](int streak) { currentStreak = streak; });
    Bridge.provide("set_humor_level", [](int h) { humorLevel = h; });
    Bridge.provide("set_focus_level", [](int tier) { currentFocusLevel = tier; });
    Bridge.provide("react_phone", reactToPhone);
    Bridge.provide("set_reduced_motion", [](int state){ reducedMotionMode = (state == 1); });
    Bridge.provide("celebrate", [](int tier) {
        startConfetti(tier);
        roboEyes.setMood(HAPPY);
        moveTo(constrain(currentPan - 10.0f, 45.0f, 135.0f), 250, 0);
    });

    Bridge.provide("set_hibernate_mode", [](int state) {
        isHibernatingMode = (state == 1);
        if (isHibernatingMode) {
            moveTo(constrain(currentPan + 15.0f, 45.0f, 135.0f), 1000, 0); 
            roboEyes.setIdleMode(OFF, 0, 0);  
        } else {
            moveTo(90, 1000, 0);
            startBootAnimation();
            lastInteractionTime = millis();
        }
    });

    Bridge.provide("set_sleep_state", [](int state) {
        isAsleep = (state == 1);
        if (isAsleep) {
            moveTo(constrain(currentPan + 15.0f, 45.0f, 135.0f), 3000, 0);
            roboEyes.setHeight(2, 2);
            roboEyes.setWidth(30, 30);
            roboEyes.setAutoblinker(OFF, 0, 0);
            roboEyes.setIdleMode(OFF, 0, 0);
        } else {
            roboEyes.setHeight(30, 30);
            roboEyes.setWidth(30, 30);
            roboEyes.setPosition(DEFAULT);
            roboEyes.setAutoblinker(ON, 3, 2);
            roboEyes.setIdleMode(ON, 2, 2);
            roboEyes.setMood(DEFAULT);
            moveTo(90, 500, 0);
        }
    });

    Bridge.provide("trigger_notification", [](int state) {
        isNotificationActive = true;
        notificationStartTime = millis();
        indicatorState = 3; 
    });

    Bridge.provide("show_pomodoro_score", [](int score) {
        isShowingScore = true;
        pomodoroFinalScore = score;
        scoreDisplayTimer = millis();
        scoreConfettiActive = true;
        scoreConfettiStart = millis();
        confettiActive = false;
    });

    pinMode(PIN_TOUCH_PET, INPUT);
    pinMode(PIN_TOUCH_SPEAK, INPUT);
    
    delay(1000); 
    Wire.begin();
    delay(100); 
    
    display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
    display.clearDisplay();
    display.display();
    
    roboEyes.begin(SCREEN_WIDTH, SCREEN_HEIGHT, 100); 
    roboEyes.setPosition(DEFAULT);
    roboEyes.setAutoblinker(ON, 3, 2);
    roboEyes.setIdleMode(ON, 2, 2);
    roboEyes.setCuriosity(true);

    linuxReady = false;
    display.clearDisplay();
    display.display();

    lastInteractionTime = millis();
    currentPan = 90.0;
    targetPan = 90.0;
    startPan = 90.0;
    startupSuppressUntil = bootAnimationStart + BOOT_ANIMATION_DURATION;
}

void loop() {
    if (millis() - lastServoCalcTime > 20) {
        lastServoCalcTime = millis();
        bool moved = false;

        float t = 1.0f;
        if (moveDuration > 0) t = (float)(millis() - moveStartTime) / moveDuration;
        t = constrain(t, 0.0f, 1.0f);

        // Quintic smoothstep: zero velocity and acceleration at both ends.
        // This removes the hard starts/stops and eliminates servo jerks.
        float ease = t * t * t * (t * (t * 6.0f - 15.0f) + 10.0f);
        float newPan = startPan + (targetPan - startPan) * ease;

        jitterOffsetPan = 0.0;

        if (abs(newPan - currentPan) > 0.35f || t >= 1.0f) {
            currentPan = newPan;
            if (!panServo.attached()) panServo.attach(PIN_SERVO_PAN);
            panServo.write((int)round(currentPan));
            moved = true;
        }

        if (moved) lastServoActiveTime = millis();
        else if (millis() - lastServoActiveTime > 1000) {
            if (panServo.attached()) panServo.detach();
        }
    }

    if (!linuxReady) {
        display.clearDisplay();
        display.display();
        return;
    }

    if (bootAnimationActive) {
        display.display();

        if (!bootAnimationActive) {
            roboEyes.setHeight(30, 30);
            roboEyes.setWidth(30, 30);
            roboEyes.setPosition(DEFAULT);
            roboEyes.setAutoblinker(ON, 3, 2);
            roboEyes.setIdleMode(ON, 2, 2);
            roboEyes.setHeight(30, 30);
            roboEyes.setWidth(30, 30);
            moveTo(90, 700, 0);
            lastInteractionTime = millis();
        }
        return;
    }

    if (isShowingScore) {
        if (millis() - scoreDisplayTimer > 5000) {
            isShowingScore = false;
            scoreConfettiActive = false;
        } else {
            display.display();
            return;
        }
    }

    if (isHibernatingMode) {
        display.clearDisplay(); 
        display.display();
        return; 
    }

    if (isNotificationActive) {
        if (millis() - notificationStartTime > 30000) {
            isNotificationActive = false; 
            indicatorState = 0; 
        }
    }

    if (startleActive) {
        if (startleStep == 0) {
            if (millis() - startleTimer > 750) { 
                moveTo(120, 50, 2); 
                startleTimer = millis();
                startleStep = 1;
            }
        }
        else if (startleStep == 1) {
            if (millis() - startleTimer > 300) { 
                moveTo(60, 50, 2); 
                startleTimer = millis();
                startleStep = 2;
            }
        }
        else if (startleStep == 2) {
            if (millis() - startleTimer > 600) { 
                roboEyes.setMood(DEFAULT);
                roboEyes.setHeight(30, 30);
                moveTo(90, 1500, 0); 
                startleActive = false; 
            }
        }
    }

    bool rawPet = (digitalRead(PIN_TOUCH_PET) == HIGH);
    bool rawSpeak = (digitalRead(PIN_TOUCH_SPEAK) == HIGH);
    bool petStable = false;
    bool speakStable = false;

    if (rawPet) {
        if (petActiveTime == 0) petActiveTime = millis();
        if (millis() - petActiveTime > 100) petStable = true;
    } else { petActiveTime = 0; }

    if (rawSpeak) {
        if (speakActiveTime == 0) speakActiveTime = millis();
        if (millis() - speakActiveTime > 100) speakStable = true;
    } else { speakActiveTime = 0; }

    if (rawSpeak && indicatorState == 2) {
        Bridge.notify("interrupt_speech");
        delay(500); 
        return;
    }

    if (petStable || speakStable || indicatorState == 2 || isProcessing || startleActive || isPomodoro || isBreathingExercise) {
        lastInteractionTime = millis();
    }

    if (indicatorState == 1 || indicatorState == 2 || isAsleep) {
        if (millis() - lastDotTime > 300) {
            lastDotTime = millis();
            dotCount = (dotCount + 1) % 4;
            zzzFrame = (zzzFrame + 1) % 4;
        }
    }

    if (lookingDir != -1 && millis() - lookDirTimer > 2000) {
        lookingDir = -1;
        moveTo(90, 800, 0);
        roboEyes.setHeight(30, 30);
        roboEyes.setPosition(DEFAULT);
    }

    if (isBreathingExercise) {
        unsigned long elapsed = millis() - breathingStartTime;
        unsigned long effectiveElapsed = (elapsed > breathingPausedAccum) ? (elapsed - breathingPausedAccum) : 0;
        if (breathingPaused && breathingPauseStart > 0) {
            effectiveElapsed = (breathingPauseStart - breathingStartTime > breathingPausedAccum) ? (breathingPauseStart - breathingStartTime - breathingPausedAccum) : 0;
        }
        if (effectiveElapsed >= breathingDuration) { stop_breathing_exercise(); return; }

        int secsLeft = (breathingDuration - effectiveElapsed) / 1000;
        int mins = secsLeft / 60;
        int secs = secsLeft % 60;
        char buf[10];
        sprintf(buf, "%02d:%02d", mins, secs);
        breathingTimeStr = String(buf);

        // Intro timing: slide in, hold, slide out
        const unsigned long BREATH_SLIDE_IN = 700;
        const unsigned long BREATH_HOLD = 1100;
        const unsigned long BREATH_SLIDE_OUT = 700;
        const unsigned long BREATH_INTRO_TOTAL = BREATH_SLIDE_IN + BREATH_HOLD + BREATH_SLIDE_OUT;

        unsigned long animElapsed = millis() - breathingAnimTimer;

        if (breathingAnimState != 5) {
            if (animElapsed < BREATH_SLIDE_IN) {
                breathingAnimState = 1;
            } else if (animElapsed < BREATH_SLIDE_IN + BREATH_HOLD) {
                breathingAnimState = 2;
            } else if (animElapsed < BREATH_INTRO_TOTAL) {
                breathingAnimState = 3;
            } else {
                breathingAnimState = 5;
                lastBreathingCycleTime = millis();
            }
        }

        if (breathingAnimState == 1 || breathingAnimState == 2 || breathingAnimState == 3) {
            display.clearDisplay();
            display.display();
            return;
        }

        // Normal breathing cycle once the intro is completely finished.
        unsigned long cycleElapsed = (millis() - lastBreathingCycleTime) % 16000;
        float breathHeight = 30.0;
        float progress = 0.0;
        float ease = 0.0;

        if (cycleElapsed < 4000) {
            progress = (float)cycleElapsed / 4000.0;
            ease = progress * progress * (3.0 - 2.0 * progress);
            breathHeight = 2.0 + (28.0 * ease);
        }
        else if (cycleElapsed < 8000) {
            breathHeight = 30.0;
        }
        else if (cycleElapsed < 12000) {
            progress = (float)(cycleElapsed - 8000) / 4000.0;
            ease = progress * progress * (3.0 - 2.0 * progress);
            breathHeight = 30.0 - (28.0 * ease);
        }
        else {
            breathHeight = 2.0;
        }

        display.clearDisplay();
        int s = (int)breathHeight;
        int radius = s / 5;
        if (radius < 1) radius = 1;
        display.fillRoundRect(40 - 15, 32 - (s / 2), 30, s, radius, 1);
        display.fillRoundRect(88 - 15, 32 - (s / 2), 30, s, radius, 1);
        display.display();
        return;
    }

    if (isPomodoro) {
        if (pomodoroAnimState > 0 && pomodoroAnimState < 5) {
            const unsigned long POMO_SLIDE_IN   = 650;
            const unsigned long POMO_HOLD       = 1400;
            const unsigned long POMO_SLIDE_OUT  = 650;
            const unsigned long POMO_INTRO_TOTAL = POMO_SLIDE_IN + POMO_HOLD + POMO_SLIDE_OUT;

            unsigned long introElapsed = millis() - pomoAnimTimer;

            if (introElapsed < POMO_SLIDE_IN) {
                pomodoroAnimState = 1;
            } else if (introElapsed < POMO_SLIDE_IN + POMO_HOLD) {
                pomodoroAnimState = 2;
            } else if (introElapsed < POMO_INTRO_TOTAL) {
                pomodoroAnimState = 3;
            } else {
                pomodoroAnimState = 5;
                roboEyes.setHeight(30, 30);
                roboEyes.setWidth(30, 30);
                roboEyes.setPosition(DEFAULT);
                roboEyes.setIdleMode(ON, 1, 2);
            }

            if (pomodoroAnimState == 1 || pomodoroAnimState == 2 || pomodoroAnimState == 3) {
                display.clearDisplay();
                display.display();
                return;
            }
        }

        if (!isPomodoroBreak) {
            if (currentFocusLevel == 2) {
                roboEyes.setMood(DEFAULT);
                roboEyes.setSweat(true);
            } else {
                roboEyes.setSweat(false);
                roboEyes.setMood(currentFocusLevel == 0 ? HAPPY : DEFAULT);
            }
        } else {
            roboEyes.setSweat(false);
            roboEyes.setMood(TIRED); 
        }
        
        if (petStable && !pomoPetHandled) {
            pomoPetHandled = true;
            Bridge.notify("pet_event");
        }
        if (!rawPet) pomoPetHandled = false;

        if (speakStable && !pomoSpeakHandled && !isListening) {
            pomoSpeakHandled = true;
            isListening = true;
            roboEyes.setIdleMode(OFF, 0, 0);
            roboEyes.setPosition(E);
            Bridge.notify("listening_state", true);
        }
        if (!rawSpeak) {
            pomoSpeakHandled = false;
            if (isListening) {
                isListening = false;
                roboEyes.setIdleMode(ON, 1, 2);
                roboEyes.setPosition(DEFAULT);
                Bridge.notify("listening_state", false);
            }
        }

        roboEyes.update();
        display.display();
        return;
    }

    if (isAsleep) {
        if (rawPet) {
            isAsleep = false;
            Bridge.notify("woke_up"); 
            moveTo(90, 200, 2); 
            roboEyes.setHeight(30, 30);
            roboEyes.setWidth(30, 30);
            roboEyes.setPosition(DEFAULT);
            roboEyes.setAutoblinker(ON, 3, 2);
            roboEyes.setIdleMode(ON, 2, 2);
            roboEyes.setMood(DEFAULT);
            lastInteractionTime = millis();
            return; 
        } else {
            display.clearDisplay();
            display.fillRect(30, 42, 24, 2, 1); 
            display.fillRect(74, 42, 24, 2, 1); 
            display.setTextSize(1); display.setTextColor(1);
            if(zzzFrame > 0) { display.setCursor(60, 15); display.print("Z"); }
            if(zzzFrame > 1) { display.setCursor(70, 8); display.print("z"); }
            if(zzzFrame > 2) { display.setCursor(80, 2); display.print("z"); }
            display.display();
            return; 
        }
    } else {
        roboEyes.update();
    }

    if (confettiActive) {
        unsigned long confettiDuration = confettiTier == 1 ? 1800 : 1100;
        if (millis() - confettiStartTime > confettiDuration) {
            confettiActive = false;
        } else {
            float ct = (millis() - confettiStartTime) / 1000.0;
            for (int i = 0; i < CONFETTI_COUNT; i++) {
                int px = confetti[i].x + confetti[i].vx * ct * 10;
                int py = confetti[i].y + confetti[i].vy * ct * 10 + (ct * ct * 40);
                if (px >= 0 && px < SCREEN_WIDTH && py >= 0 && py < SCREEN_HEIGHT) {
                    display.drawPixel(px, py, 1);
                    if (px + 1 < SCREEN_WIDTH) display.drawPixel(px + 1, py, 1);
                }
            }
            display.display();
        }
    }

    if (sweatUntil > 0 && millis() > sweatUntil) {
        roboEyes.setSweat(false);
        sweatUntil = 0;
    }

    if (isDancing && !noddingActive && !headShakeActive && !startleActive) {
        int stepInterval = map(humorLevel, 1, 10, 600, 280);

        if (currentDanceType == 0) {
            if (millis() - lastDanceStepTime > stepInterval) {
                lastDanceStepTime = millis();
                danceState = 1 - danceState;
                dancePanRange += 2.0;
                if (dancePanRange > maxDancePanRange) dancePanRange = maxDancePanRange;
                float nextPan = sweepRight ? (90.0 + dancePanRange) : (90.0 - dancePanRange);
                if (danceState == 0) sweepRight = !sweepRight;
                moveTo(nextPan, 400, 0); 
            }
        } else if (currentDanceType == 1) {
            if (millis() - lastDanceStepTime > 100) {
                lastDanceStepTime = millis();
                float elapsed = (millis() - danceStartTime) / 1000.0;
                float speedFactor = map(humorLevel, 1, 10, 60, 140) / 100.0;
                float panWave = sin(elapsed * 2.2 * speedFactor) * maxDancePanRange;
                moveTo(90.0 + panWave, 120, 0);
            }
        } else {
            unsigned long holdTime = (danceState == 0) ? stepInterval : stepInterval * 2;
            if (millis() - lastDanceStepTime > holdTime) {
                lastDanceStepTime = millis();
                if (danceState == 0) {
                    float posePan = 90.0 + random(-25, 26);
                    moveTo(posePan, 350, 0);
                    danceState = 1;
                } else {
                    danceState = 0;
                }
            }
        }
    }

    if (rawPet && !isProcessing && indicatorState != 2 && !startleActive && !isBreathingExercise) {
        if (petStartTime == 0) {
            petStartTime = millis();
            petStage = 0;
            petBasePan = currentPan;
            roboEyes.setWidth(30, 30);
            roboEyes.setHeight(30, 30);
            roboEyes.setMood(HAPPY);
            roboEyes.anim_laugh();
            if (!isPomodoro) {
                noddingActive = true;
                nodStep = 0;
                lastNodStepTime = millis();
            }
        }
        
        unsigned long heldTime = millis() - petStartTime;
        if (heldTime > 2000 && petStage == 0) {
            petStage = 1;
            Bridge.notify("pet_event");
        }
        else if (heldTime > 5000 && petStage == 1 && !isPomodoro) {
            petStage = 2;
            roboEyes.setMood(TIRED);
            roboEyes.setHeight(15, 15);
            Bridge.notify("fidget_cycle_event");
            noddingActive = false;
        }
        else if (heldTime > 8000 && petStage == 2 && !isPomodoro) {
            petStage = 3;
            roboEyes.setMood(DEFAULT);
            roboEyes.setHeight(30, 30);
            moveTo(random(70, 110), 600, 0);
        }
        petReleaseTime = millis(); 
        isReleasingPet = false;
    } else {
        if (petStartTime > 0) {
            if (!isReleasingPet) {
                isReleasingPet = true;
                petReleaseTime = millis();
            }
            
            if (millis() - petReleaseTime > 2500) {
                petStartTime = 0;
                petStage = 0;
                isReleasingPet = false;
                if (!isPomodoro) {
                    roboEyes.setMood(DEFAULT);
                    roboEyes.setHeight(30, 30);
                    moveTo(90, 800, 0); 
                }
            }
        }
    }

    if (speakStable && indicatorState != 2 && !startleActive) { 
        if (isNotificationActive) {
            isNotificationActive = false;
            indicatorState = 0;
            Bridge.notify("notification_accepted");
            delay(500); 
        } else if (!isListening) {
            isListening = true;
            roboEyes.setIdleMode(OFF, 0, 0); 
            roboEyes.setPosition(E); 
            Bridge.notify("listening_state", true); 
        }
    } else {
        if (isListening) {
            isListening = false;
            roboEyes.setIdleMode(ON, 2, 2);  
            roboEyes.setPosition(DEFAULT);
            Bridge.notify("listening_state", false); 
        }
    }

    if (noddingActive) {
        if (millis() - lastNodStepTime > 300) {
            lastNodStepTime = millis();
            nodStep++;
            switch (nodStep) {
                case 1: moveTo(constrain(petBasePan + 5.0f, 45.0f, 135.0f), 300, 0); break;
                case 2: moveTo(constrain(petBasePan - 5.0f, 45.0f, 135.0f), 300, 0); break;
                case 3: moveTo(constrain(petBasePan + 5.0f, 45.0f, 135.0f), 300, 0); break;
                case 4: moveTo(constrain(petBasePan - 5.0f, 45.0f, 135.0f), 300, 0); break;
                case 5: moveTo(petBasePan, 300, 0); noddingActive = false; break;
            }
        }
    }
    if (headShakeActive && !noddingActive) { 
        if (millis() - lastShakeStepTime > 150) { 
            lastShakeStepTime = millis();
            shakeStep++;
            switch (shakeStep) {
                case 1: moveTo(70, 300, 0); break; 
                case 2: moveTo(110, 300, 0); break; 
                case 3: moveTo(70, 300, 0); break; 
                case 4: moveTo(110, 300, 0); break; 
                case 5: moveTo(90, 300, 0); headShakeActive = false; break;
            }
        }
    }

    if (millis() >= startupSuppressUntil && millis() - lastServoIdleMove > nextServoIdleInterval && indicatorState == 0 && !isProcessing && !noddingActive && !headShakeActive && !isAsleep && lookingDir == -1 && petStartTime == 0 && !startleActive && !isDancing && !isPomodoro && !isBreathingExercise && !reducedMotionMode) {
        lastServoIdleMove = millis();
        nextServoIdleInterval = random(minIdleSec * 1000, maxIdleSec * 1000); 
        moveTo(random(70, 110), 1200, 0); 
        roboEyes.setHeight(30, 30);
        roboEyes.setPosition(DEFAULT);
        roboEyes.blink(); 
    }
}
