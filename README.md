# Joystick Multi-Tool (ESP32 → PC)

Turn a cheap analog 2-axis joystick module into a configurable PC input device.
The ESP32 reads the joystick and streams its position over USB serial; a Python
engine on the PC turns that stream into mouse movement, scrolling, media keys and
arrow keys — with a live web dashboard for tuning the feel without reflashing
anything.

## What it solves

- **A 2-axis joystick is a mouse, but a bad one.** A raw pot gives a jittery,
  unusable pointer. This project adds the layer a real mouse already has:
  a deadzone, acceleration ramp-up while the stick is held, and a precision
  ("sniper") modifier for slow, pixel-accurate movement.
- **One stick, several tools.** Instead of buying a mouse, a scroll wheel, a
  media remote and a D-pad, the same hardware switches between four input
  profiles by holding the joystick button.
- **Tuning without touching code.** Deadzones, speeds, cooldowns and audio
  feedback are live-editable sliders in a browser dashboard, so the feel can be
  dialled in while holding the device in your hand.
- **No driver, no pairing, no cloud.** Everything is a USB serial link plus a
  local Python process. It works offline and on any machine with Python.

## Features

| | |
|---|---|
| **Mouse mode** | Relative pointer movement, configurable deadzone, hold-to-accelerate ramp, sniper/precision multiplier |
| **Scroll mode** | Vertical scroll wheel + horizontal `Ctrl+Tab` / `Ctrl+Shift+Tab` tab switching |
| **Media mode** | Volume up/down, next/previous track, play/pause |
| **Arrow keys mode** | Arrow-key navigation, `Enter` to activate |
| **Button semantics** | Tap = click, mid-hold = precision mode, long hold = switch profile |
| **Audio feedback** | Active buzzer confirms profile switches and actions (per-category toggles) |
| **Calibration** | Capture the stick's rest position as centre, live from the dashboard |
| **Live dashboard** | Telemetry readout (raw X/Y, dX/dY, button state) + per-mode tuning sliders |
| **Safe tuning** | Slider changes apply instantly in memory; a single *Save* button commits them to disk |

## Quick start

### 1. Flash the firmware

```powershell
pio run -e esp32dev -t upload
```

The ESP32 must be in its normal (not bootloader) mode. Serial is **115200 baud**.

### 2. Wire the joystick

| Signal | ESP32 pin | Notes |
|---|---|---|
| Joystick X (pot wiper) | **GPIO34** | ADC1, input-only — OK for `analogRead` |
| Joystick Y (pot wiper) | **GPIO35** | ADC1, input-only — OK for `analogRead` |
| Switch (SW) | **GPIO32** | `INPUT_PULLUP`: connect the other leg to **GND** |
| Active buzzer | **GPIO25** | `HIGH` = sound; use an *active* buzzer module |
| Common ground | **GND** | Pot outer legs: 3V3 and GND |

### 3. Run the PC engine

```powershell
cd pc_side_py
.\venv\Scripts\python.exe app.py
```

Open **http://127.0.0.1:5000** for the dashboard. Close the terminal to stop.

> Run the command **from inside `pc_side_py/`** — the config file is opened by
> relative path. Also check the COM port: `SERIAL_PORT` is set to `COM5` in
> `app.py`, `pc_controller.py` and `pc_controller_v2.py`.

### 4. Tune it

Move a slider → the change applies immediately (in memory only). Hit
**Save Profile Settings** to write it to `pc_side_py/config.json`. Use
**Capture Rest Center Baseline** if the pointer drifts at rest.

## Using the joystick

| Gesture | Action |
|---|---|
| Move the stick | Mouse movement / scroll / media / arrows depending on the active profile |
| Short tap (< 0.25 s) | Click in the active profile (left click, middle click, play/pause, Enter) |
| Medium hold (0.25 s – 0.8 s) | Precision (sniper) mode — slower, finer movement |
| Long hold (> 0.8 s) | Switch to the next profile (beep confirms which one) |

## Project layout

```
src/main.cpp              ESP32 firmware: reads pots/button, streams over serial, drives the buzzer
pc_side_py/
  app.py                  Flask + Socket.IO server, telemetry feed, dashboard events
  controller.py           JoystickController: parsing, button state machine, config I/O
  modes.py                The four input profiles
  config.json             Live tuning values (deadzones, speeds, cooldowns, audio flags)
  templates/index.html    Dashboard (single file, inline CSS/JS)
  pc_controller.py        Legacy standalone v1 engine (superseded)
  pc_controller_v2.py     CLI-only front-end over the shared controller
```

## Documentation

- **[TECHNICAL.md](TECHNICAL.md)** — wiring, serial protocol, firmware internals,
  engine architecture, threading, config schema, dashboard internals, extension
  guide, troubleshooting.
- **[AGENTS.md](AGENTS.md)** — notes for AI agents working in this repo (commands,
  quirks, what not to break).
