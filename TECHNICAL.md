# Technical Reference — Joystick Multi-Tool

Deep dive into the hardware, the firmware, the PC engine and the dashboard.
Everything here was read from the code in this repo; where the code and this
document disagree, the code wins.

---

## 1. System overview

```
┌──────────────────────────┐        USB serial (115200)        ┌────────────────────────────┐
│  ESP32 dev board         │                                   │  PC (Windows/Linux/macOS)  │
│                          │  → rawX,rawY,button\n   (≈125 Hz) │                            │
│  ADC pots  → GPIO34/35   │ ────────────────────────────────► │  pyserial → JoystickController
│  Switch     → GPIO32     │                                   │        → modes.py → pyautogui
│  Buzzer    ← GPIO25      │ ◄──────────────────── BEEP:n\n    │                            │
└──────────────────────────┘        (PC → device commands)     │  Flask + Socket.IO dashboard│
                                                               │  http://127.0.0.1:5000      │
                                                               └────────────────────────────┘
```

Two independent halves:

- **Firmware (`src/main.cpp`)** — dumb sensor node. Reads the analog inputs,
  prints one CSV line per loop, and reacts to a single text command
  (`BEEP:<n>`). No state, no protocol versioning, no filtering.
- **PC engine (`pc_side_py/`)** — all the intelligence: parsing, deadzones,
  acceleration, profile state machine, config, and the web dashboard.

The split means the feel of the device can be retuned by editing `config.json`
or moving dashboard sliders **without reflashing the ESP32**. Only the raw
sampling lives on the microcontroller.

---

## 2. Hardware & wiring

### 2.1 Pins (from `src/main.cpp`)

| Constant | GPIO | Direction | Arduino setup |
|---|---|---|---|
| `X_PIN` | 34 | in | `analogRead` (ADC1 channel 6) |
| `Y_PIN` | 35 | in | `analogRead` (ADC1 channel 7) |
| `SW_PIN` | 32 | in | `pinMode(INPUT_PULLUP)` |
| `BUZZER_PIN` | 25 | out | `pinMode(OUTPUT)`, idle `LOW` |

### 2.2 Wiring notes that actually matter

- **GPIO34 and GPIO35 are input-only** and have *no internal pull-ups and no
  pull-downs*. That is fine for potentiometer wipers (they are driven
  externally) but means they cannot be used for a switch.
- **GPIO32 has an internal pull-up**, so the switch only needs one wire: signal
  to GPIO32, other leg to GND. Closed switch = `LOW` = "pressed".
- **Potentiometer power**: outer legs to **3V3** and **GND**, wiper to the ADC
  pin. With `analogSetAttenuation(ADC_11db)` the usable range is roughly
  0–3.1 V mapped to 0–4095 (12-bit). The default `analogRead` range
  (0–1 V / 0–1023) is *not* used, so 0–4095 is the value range everywhere.
- **Common ground is mandatory** — the ADC measures voltage relative to the
  ESP32's ground. USB power alone is not enough if the joystick is powered from
  elsewhere.
- **Active buzzer, not passive.** The firmware just drives the pin `HIGH` for
  80 ms per beep. A passive buzzer would need `tone()` and would emit a click
  instead of a sound. If you swap in a passive buzzer, use `tone(BUZZER_PIN, f)`.
- ESP32 board is powered over USB; no separate supply needed for the joystick.

### 2.3 Centre calibration

Raw ADC readings of an idle joystick sit wherever the pot's mechanical centre is
— often 2000–2100, but not exactly 2048. The PC engine keeps `CENTER_X` /
`CENTER_Y` (default **2048**) and computes:

```
dx = raw_x - CENTER_X
dy = raw_y - CENTER_Y
```

The dashboard's **Capture Rest Center Baseline** button emits `trigger_recenter`,
which sets the centres to the *current* raw reading. With the stick physically
at rest, press the button and the whole deadzone re-centres around it.

---

## 3. Firmware (`src/main.cpp`)

### 3.1 Startup

```cpp
Serial.begin(115200);
pinMode(SW_PIN, INPUT_PULLUP);
pinMode(BUZZER_PIN, OUTPUT);
digitalWrite(BUZZER_PIN, LOW);   // silent at boot
analogSetAttenuation(ADC_11db);  // 12-bit range
```

### 3.2 The transmit frame

Every loop iteration the firmware prints exactly:

```
<rawX>,<rawY>,<button>\n
```

- `rawX`, `rawY` — integers 0–4095.
- `button` — `0` = pressed, `1` = released (active-low switch).
- `\n` terminates the line; the PC side parses on newline.

### 3.3 The receive command

```cpp
if (Serial.available() > 0) {
  String command = Serial.readStringUntil('\n');
  command.trim();
  if (command.startsWith("BEEP:")) { ... }
}
```

Only one command exists: `BEEP:<count>` → the buzzer is driven `HIGH` for
80 ms, then `LOW` for 80 ms, repeated `count` times.

**Known quirk:** `readStringUntil('\n')` blocks until a newline arrives, and the
firmware reads commands *after* it has printed its sensor frame. A command that
arrives without a trailing newline will stall the loop until one shows up. The
PC side always appends `\n` (`f"BEEP:{count}\n"`), so this is safe in practice —
but any new command type must follow the same newline-terminated convention.

### 3.4 Loop timing

`delay(8)` at the end of the loop → roughly **125 sensor frames per second**.
The PC engine reads whatever is buffered and discards the rest
(`reset_input_buffer()`), so the effective telemetry rate is bounded by the
PC-side loop, not by the firmware.

---

## 4. Serial protocol

| Direction | Payload | Rate | Notes |
|---|---|---|---|
| ESP32 → PC | `rawX,rawY,button\n` | ~125 Hz | ASCII CSV, one line per frame |
| PC → ESP32 | `BEEP:<count>\n` | on demand | ASCII, newline-terminated |

Both sides are plain ASCII — debug with any serial monitor
(`pio run -e esp32dev -t monitor`).

If you change the frame format, change `controller.py:update()` in the same
commit; nothing validates the protocol at runtime, a mismatch shows up as
silently ignored input.

---

## 5. PC engine architecture

```
app.py
 ├─ gevent monkey patch (must be first import)
 ├─ Flask + SocketIO(app, async_mode='gevent', cors_allowed_origins='*')
 ├─ __main__: open serial → build JoystickController → gevent.spawn(loop) → socketio.run(...)
 └─ background_joystick_loop()  ← greenlet
      ├─ joystick_controller.update()        (parse + dispatch input)
      └─ socketio.emit('telemetry_data', …) (push to dashboard)

controller.py  JoystickController
 ├─ load_config() / save_config()   ← config.json
 ├─ update()                        ← parse frame, button state machine, dispatch
 ├─ modes: [MouseMode, ScrollMode, MediaMode, ArrowKeysMode]
 ├─ cycle_mode(), update_offsets(), send_beep_command()
 └─ latest_telemetry (cached dict, read by the dashboard feed)

modes.py
 └─ BaseMode  → handle_input(dx, dy, sniper_active, t) / handle_click()
    ├─ MouseMode       relative movement, deadzone, ramp, sniper
    ├─ ScrollMode      vertical scroll + tab switching
    ├─ MediaMode       volume / track keys
    └─ ArrowKeysMode   arrow keys + Enter
```

### 5.1 Frame handling — `controller.py:update()`

```python
if self.esp32.in_waiting > 0:
    line = self.esp32.readline().decode('utf-8', errors='ignore').strip()
    self.esp32.reset_input_buffer()
    data = line.split(',')
    if len(data) != 3: return
```

- `timeout=0.001` on the serial object, so `readline()` never blocks long.
- `reset_input_buffer()` discards any partially-received or queued frames —
  the engine always works on the freshest sample and never builds a backlog.
- Malformed frames (wrong field count) are dropped silently; the whole body is
  wrapped in `try/except: pass`, so a bad frame can never kill the loop.
- `latest_telemetry` is refreshed with every accepted frame and is what the
  dashboard displays.

### 5.2 Button state machine

Two thresholds, both constructor arguments of `JoystickController`
(`tap_threshold=0.25`, `mode_hold_threshold=0.8`):

| Press duration | Behaviour | Flag |
|---|---|---|
| ≤ 0.25 s, then released | `active_mode.handle_click()` | — |
| > 0.25 s and ≤ 0.8 s | `sniper_active = True` (mouse mode only) | — |
| > 0.8 s | `cycle_mode()`, once per press (`mode_shifted_this_press`) | blocks further actions for that press |

The click is only fired on the **release** edge (`button == 1 and
is_button_down`), and only if the press was short — so a long hold never
produces a stray click.

Sniper mode is mouse-mode-specific: in the other profiles the mid-hold band is
simply a no-op.

### 5.3 Profile (mode) list

`self.modes` and `self.mode_names` are parallel lists and **must stay in the
same order** — the index is the profile identifier:

| Index | Class | Display name |
|---|---|---|
| 0 | `MouseMode` | Mouse Mode |
| 1 | `ScrollMode` | Scroll Mode |
| 2 | `MediaMode` | Media Mode |
| 3 | `ArrowKeysMode` | Arrow Keys Mode |

`cycle_mode()` wraps around (`(idx + 1) % len(modes)`) and, if
`audio.profile_shift` is on, beeps `current_mode_idx + 1` times — so the beep
count tells you which profile you landed on.

### 5.4 Input routing — `modes.py`

Every profile reads its thresholds live from `self.controller.config[...]`
through a `deadzone` property, so dashboard slider changes take effect on the
very next input frame without restarting anything.

**MouseMode**

```python
speed_factor = 1.0 + (max_speed_mult - 1.0) * min(duration_held / ramp_time, 1.0)
current_modifier = base_speed * speed_factor          # accelerating
current_modifier = base_speed * sniper_mult           # precision mode
current_modifier = base_speed                         # at rest / below deadzone
move_x = dy * current_modifier
move_y = dx * current_modifier
```

- The **X/Y axes are swapped** on purpose: `dy` drives the screen's X axis and
  `dx` drives the screen's Y axis. This compensates for the physical
  orientation of the joystick module. Swap them if your module is mounted
  differently.
- The ramp timer starts the moment the stick leaves the deadzone and resets
  when it returns to it.
- `pyautogui.moveRel()` takes floats, so partial pixels are supported.

**ScrollMode**

- `|dx| > deadzone` → `pyautogui.scroll(±scroll_amount)`, sign flipped
  (`dx < 0` → positive scroll).
- `dy > deadzone` → `Ctrl+Tab`; `dy < -deadzone` → `Ctrl+Shift+Tab`, gated by
  `cooldown` seconds.
- Click → **middle click**.

**MediaMode**

- `dx > deadzone` → `volumedown`, `dx < -deadzone` → `volumeup`.
- `dy > deadzone` → `nexttrack`, `dy < -deadzone` → `prevtrack`.
- All gated by `cooldown`; each triggered action also fires a beep if
  `audio.media_actions` is on.
- Click → `playpause`.

**ArrowKeysMode**

- `dy > deadzone` → `right`, `dy < -deadzone` → `left`.
- `dx > deadzone` → `down`, `dx < -deadzone` → `up`.
- Gated by `cooldown`; beeps if `audio.arrow_actions` is on.
- Click → `enter`.

---

## 6. Concurrency model

- Flask-SocketIO runs in **gevent** async mode; `monkey.patch_all()` at the
  top of `app.py` replaces the standard library's threading/socket behaviour
  with gevent's cooperative greenlets. It must be the *first* import.
- The sensor loop is a separate greenlet: `gevent.spawn(background_joystick_loop)`.
- Inside that loop: `joystick_controller.update()` then a `socketio.emit()`,
  then `gevent.sleep(0.001)`. Because the emit happens on every tick, the
  dashboard receives a telemetry event roughly **every millisecond**, even when
  the underlying serial frame has not changed. It is cheap on localhost but is
  the main CPU cost of the app.
- The dashboard runs on `127.0.0.1:5000` only (loopback). `cors_allowed_origins="*"`
  is set, but the socket is bound to localhost, so it is not reachable from
  other machines.

---

## 7. Configuration file

`pc_side_py/config.json` — opened by the **relative** path `"config.json"`,
which is why the engine must be launched with `pc_side_py/` as the working
directory.

### 7.1 Schema and live values

```jsonc
{
  "audio": {
    "master_mute":    false,  // global audio kill switch
    "profile_shift":  true,   // beep when switching profiles
    "media_actions":  true,   // beep on media actions
    "arrow_actions":  true    // beep on arrow actions
  },
  "mouse": {
    "deadzone":       600,    // raw ADC units ignored at rest
    "base_speed":     0.015,  // pixels per raw unit at rest
    "max_speed_mult": 4.0,    // speed multiplier at full ramp
    "ramp_time":      2.9,    // seconds to reach max_speed_mult
    "sniper_mult":    0.2     // precision-mode multiplier
  },
  "scroll": { "deadzone": 1000, "scroll_amount": 4, "cooldown": 0.35 },
  "media":  { "deadzone": 2000, "cooldown": 0.4 },
  "arrow":  { "deadzone": 2000, "cooldown": 0.34 }
}
```

Deadzones are in **raw ADC units (0–4095)**, not pixels. A deadzone of 2000
means you must push the stick more than half its travel before anything
happens.

### 7.2 Two sets of defaults

`controller.py:load_config()` has a hard-coded fallback dict used when
`config.json` is missing. Those values are *not* the same as the file's
(currently: mouse deadzone 180 vs 600, ramp 0.8 vs 2.9, media/arrow deadzones
450/250 vs 2000/2000). If the file goes missing, the feel changes noticeably.
Keep the two in sync when you change either.

### 7.3 Write semantics

- `update_setting` (dashboard slider) → **memory only**. Type coercion is done
  by inspecting the current value's type (`bool` / `int` / `float`).
- `save_configuration` (Save button) → writes the whole config to disk with
  `json.dump(..., indent=2)`.
- On every socket **connect**, the server re-reads `config.json` from disk into
  the controller (`joystick_controller.load_config()`), then broadcasts
  `sync_config`. **Unsaved slider changes are therefore lost on a browser
  refresh** — the page even warns about this via `beforeunload`.

---

## 8. Dashboard internals

`pc_side_py/templates/index.html` — one self-contained file: inline CSS
(CSS custom properties for the dark theme), inline JS, and `socket.io` loaded
from a CDN (so the first load needs internet access).

### 8.1 Event map

| Direction | Event | Payload / effect |
|---|---|---|
| server → client | `telemetry_data` | `{raw_x, raw_y, button, dx, dy, current_mode}` |
| server → client | `sync_config` | full config object |
| server → client | `save_confirmed` | `{status: 'success'}` |
| client → server | `update_setting` | `{section, key, value}` |
| client → server | `save_configuration` | — |
| client → server | `trigger_recenter` | — |
| client → server | `trigger_test_beep` | `{count}` |

The client hardcodes the server URL `io("http://127.0.0.1:5000")` — if you
change the port in `app.py`, change it here too.

### 8.2 DOM id convention

Sliders are addressed as **`{section}-{key}`** (e.g. `mouse-base_speed`), and
their numeric readout as **`{section}-{key}-txt`**. `sync_config` finds the
element by that id and skips unknown keys (`if (!el) continue;`), so a config
key without a matching control simply does not appear in the UI.

The `master_mute` toggle is inverted in the UI: the checkbox is *checked* when
audio is **enabled**, and the client sends `!this.checked`.

### 8.3 Panel structure

Four tabs (`mouse`, `scroll`, `media`, `arrow`) switch four `.mode-panel`
sections via `switchTab(mode)`. The left column holds the live telemetry panel
(with the "Capture Rest Center Baseline" button) and the audio matrix with the
buzzer diagnostics buttons (single / triple beep).

---

## 9. Extension guide

### Add a new input profile

1. In `modes.py`, subclass `BaseMode` and implement
   `handle_input(self, dx, dy, sniper_active, current_time)` and
   `handle_click(self)`.
2. In `controller.py`, append the class to `self.modes` **and** the display
   name to `self.mode_names`, at the same index.
3. Add a `config.json` section for its tuning values and a fallback entry in
   `load_config()`.
4. In `templates/index.html`, add a tab button `tab-<name>`, a
   `.mode-panel` with `id="panel-<name>"`, and controls named
   `<name>-<key>` (plus `<name>-<key>-txt` readouts).

### Add a new serial command

1. Firmware: parse it in the `Serial.available()` block, newline-terminated.
2. PC side: send it the same way `send_beep_command()` does —
   `f"CMD:{args}\n"` via `self.esp32.write(...)`.

---

## 10. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `Serial interface initialization error` at startup | Wrong COM port. Check Device Manager; update `SERIAL_PORT` in `app.py` (and the two legacy scripts). |
| Engine starts but the pointer never moves | Run from `pc_side_py/`; check `config.json` was found (a missing file silently loads weaker fallback defaults). |
| Pointer drifts when the stick is at rest | Centre is off — press **Capture Rest Center Baseline** while the stick rests, or raise `mouse.deadzone`. |
| Nothing happens until the stick is pushed far | Deadzone too high for your pot — lower `mouse.deadzone` (raw units, 0–4095). |
| Dashboard shows "Loading..." forever | Socket blocked by a firewall, or the client URL doesn't match the server port; also check the CDN is reachable for `socket.io.js`. |
| Dashboard shows stale settings after a refresh | Expected: a reconnect re-reads `config.json` and discards unsaved changes. |
| Buzzer silent | Wrong buzzer type (passive instead of active) or `audio.master_mute` is on. |
| Dashboard toggles inverted | The `master_mute` control is intentionally inverted in the client. |
| Mode switch beep has the wrong count | `mode_names` and `self.modes` are out of sync — keep the same order. |
| Serial monitor garbage | Baud mismatch — everything must be 115200. |
