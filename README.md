Problem Statement

ADHD comes with a predictable set of daily struggles: starting a task feels like pushing a boulder, staying on it is a constant battle against distraction, and time itself seems to blur and slip away. Under the surface, these are executive-function challenges — task paralysis, poor sustained attention, time blindness, emotional dysregulation, and a tendency to hyperfocus for so long that you forget to drink water or stand up. Over 200 million adults deal with this globally, and the tools meant to help are almost all app-based timers and focus assistants that live on the very screens most likely to pull your attention away in the first place. There are, however, real techniques that work — body doubling (having someone nearby so you feel accountable), task breakdown (splitting an overwhelming task into tiny steps), structured time-blocking, external cueing (physical reminders outside your own head), sensory grounding, and habit tracking with progressive goals. These are well-documented in clinical literature but almost never delivered through a single physical system. Curie is that system — a desk companion that combines all of these approaches into one device: it sits with you like a body double, breaks tasks down on voice command, runs scored focus sessions, gives you something tactile to touch when you need to reground, guides breathing exercises, tracks your habits with streak-based goals, and nudges you to move or hydrate when it senses you’ve been sitting too long.

How Your Project Works

Curie is a desk robot built on the Arduino UNO Q that addresses specific ADHD executive-function deficits through a set of interlinked, technique-driven features. Its camera uses on-device object detection to track your physical presence and phone pickups in real time, feeding those signals into a live focus score during work sessions — externalising time blindness and creating micro-rewards, both established accountability mechanisms. Those scores feed into a daily and weekly habit tracker with streak visualisation and progressive goal-setting, where each session’s target is the previous score plus a small increment, turning “do better” into a concrete number. When the camera detects sustained phone use, Curie responds with a gentle verbal nudge, countering distraction cycles through external cueing rather than willpower alone. For task paralysis, the conversational LLM decomposes overwhelming tasks into micro-steps on command. A capacitive touch sensor lets you pet Curie as a tactile grounding mechanism, and the robot guides timed box-breathing exercises with synchronised head movement for emotional regulation. A proactive agent monitors seated duration and issues movement and hydration nudges after 60 and 90 minutes, interrupting hyperfocus before it becomes harmful. Curie also acts as a passive body double — its animated face and physical presence create companionship and accountability without requiring active input. Conversational AI runs through cloud APIs (Groq LLM, Whisper STT, Cartesia TTS); vision and hardware control stay local.

Why Arduino UNO Q?

Curie’s architecture demands two things at once: real-time hardware control at millisecond granularity for servo animation, touch response, and OLED rendering — and a full Linux environment capable of running Python, driving a USB camera, and calling cloud APIs. The Arduino UNO Q is uniquely built for this. It houses a Qualcomm QRB2210 quad-core Cortex-A53 at 2 GHz running Debian Linux, paired with an STM32U585 Cortex-M33 MCU at 160 MHz running Zephyr RTOS, connected through an internal bridge. The Linux side runs the entire application layer — LLM integration, speech-to-text, text-to-speech, the web dashboard, and the SQLite memory database. The MCU side handles the latency-sensitive hardware loop: the RoboEyes animation state machine, servo kinematics with eased interpolation, touch polling, and the OLED frame buffer, all at consistent frame rates without being interrupted by the heavier AI workloads. The onboard dual ISP and GPU handle the camera-based person and phone detection entirely on-device, so no video frames leave the board — this was a privacy-first choice, since Curie is watching you at your desk all day. Conversational AI, on the other hand, goes to Groq’s cloud inference because the quality of dialogue, emotion-tagged responses, and task decomposition that an ADHD user benefits from requires a large language model far beyond what the QRB2210’s CPU/GPU can run at usable speed. We accepted this cloud dependency as a reasonable trade-off: the sensitive data (video) stays local, and the non-sensitive data (text queries) goes to the cloud for quality. Built-in Wi-Fi and Bluetooth mean no additional networking hardware, and the UNO form factor keeps the footprint small enough to sit on a desk without feeling like a development board 

<img width="441" height="328" alt="image" src="https://github.com/user-attachments/assets/689e49b6-e9f5-4f45-bdcc-da5daa19f517" />

<img width="433" height="321" alt="image" src="https://github.com/user-attachments/assets/6d9a9902-96fd-45f9-9ea0-83ba21f1e0af" />

<img width="412" height="307" alt="image" src="https://github.com/user-attachments/assets/cfb95e68-4168-4ba9-ac88-a94e3648266f" />

<img width="415" height="306" alt="image" src="https://github.com/user-attachments/assets/66f28f05-983f-4c97-8d08-43c047b9a778" />


2. Components Used (BOM)

   
Arduino UNO Q (ABX00087) 1
USB-A Webcam with Built-in Microphone 1
Wired Speaker 1
0.96” SSD1306 OLED Display (128×64, I2C) 1
MG90S Servo Motor 1
TTP223 Capacitive Touch Sensor Module 2
USB-C Hub (with PD passthrough) 1
USB-C Cable (PD power to hub) 1
USB-A Cable (stripped, 5V to servo from hub) 1
PLA Filament (3D-printed enclosure) 1
Jumper Wires

3. System Architecture & Circuit


Step-by-Step Workflow

Idle State (always running when no session is active): USB-A webcam continuously captures frames → UNO Q Linux side runs on-device object detection (person/phone classification) at ~1 Hz → Python tracks whether the user is at their desk and for how long. The MCU simultaneously runs the RoboEyes idle animation loop (periodic blinking, random eye wandering), polls both TTP223 touch sensors, and renders the SSD1306 OLED at ~30 fps. Meanwhile, background threads handle proactive behaviours: a sedentary monitor tracks how long the user has been seated and queues a movement nudge after 60 minutes or a hydration/stretch nudge after 90; a clock thread checks for late-night usage (past midnight) and sends a once-per-night sleep encouragement; a weekly summary thread fires on Sunday evenings, pulls 7-day stats from SQLite, sends them to the LLM for a coached recap, and delivers it as spoken audio. The LLM’s mood analysis of recent conversation can also trigger a breathing exercise suggestion — if the user’s last few messages indicate stress or overwhelm, Curie offers to guide a timed box-breathing session with synchronised head movement and OLED animation. On boot or morning reactivation, Curie can deliver a contextual debrief weaving together the day’s calendar events and weather.
Focus Session (started via voice or web dashboard): Python starts a Pomodoro timer and enters gamification mode → on each detection cycle, the vision pipeline checks for person presence and phone visibility → if the person is absent for 15+ seconds, Python sends a pause command to the MCU via Bridge RPC, the timer halts, and Curie’s eyes shift to a tired expression → when the person returns for 5+ seconds, the timer auto-resumes and eyes return to normal → if a phone is detected during a session, Python increments the pickup counter, the MCU eyes show a sweat-drop animation, and a verbal nudge is queued → a live focus score (100 − pickups×5 − AFK×2, floored at 20%) is computed each cycle and reflected in the OLED eye mood (happy ≥80%, neutral 50–79%, sweating <50%) → at session end, the score is logged to SQLite, a completion chime plays, the OLED displays the final percentage with a confetti particle animation, and the MCU reports the result back to Python for streak tracking and goal-setting.
Voice Conversation & Contextual Interventions: When the user holds the speak sensor, the MCU signals Python via Bridge → Python records from the USB microphone via arecord (16 kHz mono) → on release, audio is uploaded to Groq Whisper for transcription → the transcript is injected into the LLM conversation context (last 4 messages from SQLite + long-term user facts + system prompt + upcoming calendar events) and sent to Groq → the LLM returns mood-tagged text with action tags (e.g. [HAPPY] Great work! [BREAKDOWN: step1 | step2 | step3]) → Python parses these: emotion tags drive MCU facial expressions, action tags execute locally, and the spoken text is sent to Cartesia for TTS → the resulting PCM audio plays through the wired speaker via ALSA while the MCU keeps expressions synchronised to the current mood tag → tapping the speak sensor during playback interrupts speech immediately. Through this same pipeline, the LLM can recognise signs of task paralysis in the user’s language and proactively offer to decompose the task into three to five micro-steps, capture stray thoughts as persistent brain-dump notes in SQLite, set Google Calendar reminders via the [REMIND] tag, or recall what the user was last working on via [RECALL].

**Wiring: **

TTP223 Touch Sensor (Pet) D2
TTP223 Touch Sensor (Speak) D3
MG90S Pan Servo D5 (PWM)
SSD1306 OLED (128×64) SDA / SCL (I2C)
USB-A Webcam (with mic) USB A port
Wired Speaker USB A + aux (3.5mm) port

<img width="685" height="500" alt="image" src="https://github.com/user-attachments/assets/109e3746-3e93-47e1-84f5-204f606c8257" />

<img width="833" height="440" alt="image" src="https://github.com/user-attachments/assets/d16dcbb8-fee7-43f7-a20f-5e6387af1af1" />
