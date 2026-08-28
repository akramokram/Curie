# Curie

### A social-assistance robot for focus, task initiation, and executive function

Curie is a physical desk companion designed to help people who struggle with task initiation, distraction, and maintaining focus — particularly people with ADHD or executive dysfunction.

Instead of putting another productivity app on a screen, Curie brings the interaction into the physical world.

It can talk, listen, move, react, remember, guide tasks, run focus sessions, and respond to what is happening around the user.

> **Curie is not a medical device and is not intended to diagnose, treat, or cure ADHD.**
> It is an experimental assistive technology project designed to reduce friction around everyday tasks and focus.

<img width="8192" height="6144" alt="IMG_20260823_224452321" src="https://github.com/user-attachments/assets/54ac7508-e85a-4e76-ae1b-8c09528d0868" />


---

## ✨ What is Curie?

Curie is built around a simple idea:

**When starting a task is difficult, the solution shouldn't always be another notification, app, or productivity dashboard.**

Curie sits on the user's desk and acts as a persistent physical companion.

Rather than demanding attention, it is designed to provide small, low-friction interventions:

* Help break an overwhelming task into tiny first steps
* Start and manage focus sessions
* Provide gentle reminders
* Detect when the user has moved away from their workspace
* Detect potential phone/distraction activity
* Respond to voice commands
* Remember useful user information
* Provide a physical, expressive presence through its OLED face
* React through head movement, expressions, sound, and speech
* Provide breathing exercises
* Track focus-session performance and streaks

The goal is not to make the user "more productive" at all costs.

The goal is to **make starting and returning to a task easier.**

---

## 🧠 Designed around ADHD / Executive Dysfunction

Curie's interaction model is intentionally different from conventional productivity software.

Instead of:

> "You haven't completed your task."

Curie tries to reduce the barrier to starting:

> "Let's figure out the first tiny thing you need to do."

Its task-breakdown system is designed to turn an overwhelming task into **3–5 small, concrete first steps**.

Curie's AI personality is also deliberately designed not to shame the user for losing focus. The system prompt explicitly describes Curie as a calm support companion rather than a mascot or hype bot.

---

# 🤖 Features

## Voice Interaction

Curie can listen to the user through a microphone and respond using speech.

The software uses Groq's API for speech transcription and language-model interaction. The current implementation uses Whisper for audio transcription and Groq's OpenAI-compatible chat API for the AI layer.

API credentials are supplied by the user rather than hard-coded into the project.

---

## 📝 Task Breakdown

When the user is struggling to start something, Curie can turn the task into several extremely small actions.

For example:

**User:**

> "I need to finish my physics assignment."

**Curie:**

1. Open the assignment
2. Find the first unanswered question
3. Write down what the question is asking
4. Solve only that question

This is intended to reduce the activation energy required to begin.

---

## 🧠 Memory

Curie maintains a local SQLite database for:

* Recent conversation history
* User facts
* Daily focus statistics
* Brain-dump items

The database uses SQLite with WAL mode and locking to handle concurrent access.

Curie also includes a dedicated mechanism for clearing long-term user facts while preserving other information such as habits, streaks, trends, notes, and chat history.

---

## 📌 Brain Dump

Users can tell Curie about something they need to remember without creating a formal reminder.

Curie can store the item as a brain-dump note and retrieve the list later.

This is intended for the small thoughts that frequently interrupt a task:

> "I need to email my professor later."

Instead of switching apps and breaking focus, the user can simply tell Curie.

---

## ⏱️ Pomodoro / Focus Sessions

Curie includes an integrated focus timer with:

* Work sessions
* Break sessions
* Pause / resume
* Focus scoring
* Session statistics
* Streak tracking
* OLED timer animations
* Session-completion feedback

The physical OLED can display the focus state and final session score, including a small confetti animation after completion.

---

## 🌬️ Breathing Exercise

Curie can guide the user through a timed breathing exercise.

The physical OLED transitions into a dedicated breathing interface and displays the remaining time.

---

## 👁️ Computer Vision

Curie uses the Arduino UNO Q's vision capabilities to detect objects in its environment.

The current software uses the Arduino `VideoObjectDetection` brick and processes detections for things such as:

* People
* Phones
* Mobile devices
* Other detected objects

The vision system maintains presence and phone-detection state, which can then be used by Curie's focus logic.

---

## 📱 Distraction Awareness

During a focus session, Curie can use vision information to track potential phone activity and whether the user is present.

This allows Curie to provide feedback without requiring the user to manually report that they became distracted.

The intention is not surveillance or punishment — the system is designed around gentle intervention and returning to the task.

---

## 👀 Expressive OLED Face

Curie's physical face is a 128×64 OLED display.

The Arduino firmware uses expressive eyes and multiple animation states to communicate Curie's state.

The OLED supports states including:

* Normal expressions
* Sleep
* Wake/startle
* Listening
* Processing
* Pomodoro
* Breathing
* Notifications
* Session scores
* Confetti
* Boot animation

The boot animation itself expands a ring and then spells out **CURIE** across the display.

---

## 🦾 Physical Movement

Curie's head currently uses a single pan axis.

The Arduino firmware controls the servo with interpolated movement rather than simply jumping between positions. The current implementation constrains the pan movement to approximately 45°–135°.
Curie can:

* Look left/right/up/down through coordinated eye and head behavior
* React to sound
* Look toward the user
* Move during conversations
* React to interactions
* Dance
* Startle/wake
* Perform idle movements

---

## 🫳 Physical Interaction

Curie includes touch inputs for physical interaction.

The current firmware defines separate touch inputs for:

* Petting
* Speaking / interaction

These inputs can trigger different behavioral responses from Curie.

---

# 🖥️ Web Interface

<img width="1600" height="1200" alt="WhatsApp Image 2026-08-23 at 11 25 05 PM (2)" src="https://github.com/user-attachments/assets/a1304bb8-2518-46bd-9a6e-63e95e5ea32b" />


Curie also has a browser-based interface for controlling and monitoring the robot.

The interface includes a digital representation of Curie's face and controls for its different activities.

The interface currently includes functionality for:

* Chat
* Focus sessions
* Pomodoro controls
* Breathing exercises
* Habits
* Weekly trends
* Memory
* Settings
* Curie actions
* Camera status
* Hibernation
* Digital twin

The web interface also provides habit statistics such as Pomodoro score, phone pickups, and AFK events.

---

# 🔧 Hardware

<img width="1354" height="1037" alt="curie breadboard schematic" src="https://github.com/user-attachments/assets/c607cc34-1da2-49ce-82e8-fe965468ceed" />


Curie is built around the **Arduino UNO Q** platform.

### Main hardware

| Component          | Purpose                       |
| ------------------ | ----------------------------- |
| Arduino UNO Q      | Main computing platform       |
| 128×64 I²C OLED    | Physical face                 |
| Servo motor        | Head pan movement             |
| Microphone         | Voice input                   |
| Speaker            | Voice/audio output            |
| Camera             | Presence and object detection |
| Touch sensors      | Physical interaction          |
| 3D-printed body    | Mechanical enclosure          |
| Custom electronics | Power and signal distribution |

See [`hardware/`](hardware/) for the CAD files, schematic, and hardware documentation.

---

# 🔌 System Architecture

At a high level, Curie is split into two cooperating systems:

```text
                    ┌─────────────────────┐
                    │      CURIE USER     │
                    └──────────┬──────────┘
                               │
                 Voice / Touch / Presence
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Arduino UNO Q    │
                    │                     │
                    │   Curie AI / App    │
                    │                     │
                    │  ┌───────────────┐  │
                    │  │ Voice + LLM   │  │
                    │  │ Memory        │  │
                    │  │ Vision        │  │
                    │  │ Focus System  │  │
                    │  └───────────────┘  │
                    └───────┬─────┬───────┘
                            │     │
                 RouterBridge     │
                            │     │
              ┌─────────────┘     └──────────────┐
              ▼                                  ▼
       ┌─────────────┐                    ┌─────────────┐
       │ Arduino MCU │                    │ Web UI      │
       │             │                    │             │
       │ OLED        │                    │ Digital     │
       │ Servo       │                    │ Twin        │
       │ Touch       │                    │ Controls    │
       └─────────────┘                    └─────────────┘
```

The Arduino-side firmware communicates with the application layer through Arduino RouterBridge.

---

# 📁 Repository Structure

```text
Curie/
│
├── README.md
├── LICENSE
├── .gitignore
│
├── docs/
│   ├── schematic.png
│   ├── architecture.png
│   └── images/
│
├── hardware/
│   ├── CAD/
│   │   ├── STEP/
│   │   ├── STL/
│   │   └── source/
│   └── BOM.md
│
├── software/
│   ├── curie-app/
│   │   ├── main.py
│   │   ├── index.html
│   │   └── ...
│   │
│   └── arduino/
│       ├── sketch.ino
│       ├── oled_driver.h
│       └── ...
│
├── media/
│   ├── demo.gif
│   └── screenshots/
│
└── releases/
    └── curie-app.zip
```

---

# 🚀 Getting Started

## Hardware

1. Assemble the Curie body using the provided CAD files.
2. Wire the electronics according to the schematic in [`docs/schematic.png`](docs/schematic.png).
3. Connect the OLED, servo, touch sensors, microphone, speaker, and camera.
4. Install the required Arduino libraries.
5. Upload the Arduino firmware.

## Software

The Curie application runs on the Arduino UNO Q environment.

The application requires API credentials for external AI services used by the current implementation.

At minimum, configure:

```text
Groq API Key
Cartesia API Key
Cartesia Voice ID
```

Additional configuration includes:

```text
Location
Timezone
Language
Calendar configuration
```

**Do not commit API keys to GitHub.**

Use environment variables, a local configuration file excluded by `.gitignore`, or the application's settings mechanism.

---

# ⚠️ Current Status

Curie is an **active experimental project**.

The hardware, firmware, software, and interaction model are still being developed.

Some features may require specific Arduino UNO Q software versions, libraries, peripherals, or API services.

Expect things to change.

---

# 🛠️ Development

Curie consists of three major layers:

### Application Layer

Python application responsible for:

* AI interaction
* Voice
* Memory
* Vision
* Focus logic
* Statistics
* Web UI communication
* User context

### Interface Layer

HTML/CSS/JavaScript web interface providing:

* Digital twin
* Controls
* Statistics
* Settings
* Focus tools

### Hardware Layer

Arduino firmware responsible for:

* OLED rendering
* Eye animations
* Servo movement
* Touch interaction
* Physical reactions
* Hardware state

---

# 🤝 Contributing

Curie is intended to be an open hardware/software project.

Ideas, improvements, hardware modifications, interaction designs, and accessibility improvements are welcome.

If you build your own Curie or modify the design, I'd love to see it.

---

# 📜 License

This project is currently released under the terms of the license included in this repository.

See [`LICENSE`](LICENSE) for details.

---

# ❤️ Why Curie?

Productivity software usually asks the user to manage the tool.

Curie tries to do the opposite.

It sits beside you.

It notices.

It remembers.

It helps you start.

And when you get distracted, it doesn't tell you that you failed.

It just helps you come back.

**Curie is a physical interface between a person and the task they are trying to do.**
