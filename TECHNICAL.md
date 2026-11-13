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

`delay(8)` at the end of the loop → roughly **125 sensor frames per second**
(~110 fps measured over the wire). The PC engine reads every arrived byte and
keeps the incomplete tail until its newline arrives (see §5.1), so no frame is
lost.

> Opening the serial port toggles DTR/RTS, which **reboots the ESP32** — the
> boot log (`ets Jul 29 2019 …`) is printed into the same stream and is ignored
> by the parser. This is normal, not a fault.

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
    self._rxbuf += self.esp32.read(self.esp32.in_waiting)
    if len(self._rxbuf) > 4096:
        self._rxbuf = b''          # frame that never terminates -> resync
    *frames, self._rxbuf = self._rxbuf.split(b'\n')
    for frame in frames[:-1]:
        self._handle_frame(frame.decode('utf-8', errors='ignore').strip(), move=False)
    if frames:
        self._handle_frame(frames[-1].decode('utf-8', errors='ignore').strip(), move=True)
```

- Every arrived byte is read and split on newlines; the incomplete tail stays
  in `_rxbuf` until its newline arrives, so a frame that arrives in pieces is
  **reassembled** instead of being mangled.
- **Never call `reset_input_buffer()` here.** A purge discards whatever has
  already arrived; the rest of that frame arrives afterwards, and the tail then
  parses as a complete frame with a corrupted first field (observed as
  `raw_x` collapsing to `0` or `94`, which produced pointer jitter no deadzone
  could filter out).
- **Only the newest frame moves the pointer** (`move=True`). If the engine is
  blocked for any reason, the driver buffer accumulates a backlog; replaying
  every frame of that backlog flings the cursor across the screen for seconds.
  The older frames are still parsed (so button taps are not lost) but only
  update state.
- `timeout=0.001` on the serial object, so reads never block long.
- Malformed frames (wrong field count, non-numeric fields, ESP32 boot chatter)
  are dropped silently; the whole body is wrapped in `try/except: pass`, so a
  bad frame can never kill the loop.
- `latest_telemetry` is refreshed with every accepted frame and is what the
  dashboard displays.
- Regression test: `test/test_rx_framing.py`.

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
  (`dx < 0` → positive scroll). Rate limited to `SCROLL_INTERVAL` (0.04 s,
  25 events/s) — the device streams ~110 frames/s and an unthrottled scroll
  event per frame scrolls the page away instantly.
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
- Inside that loop: `joystick_controller.update()` then (throttled)
  `socketio.emit()`, then `gevent.sleep(0.001)`.
- **Windows' default timer granularity is ~15.6 ms**, so `gevent.sleep(0.001)`
  actually sleeps ~15 ms and the loop drops from ~650 Hz to ~65 Hz — the
  pointer then only reacts every other frame. `app.py` calls
  `ctypes.windll.winmm.timeBeginPeriod(1)` to get a 1 ms timer period. Without
  it the device feels sluggish no matter how the config is tuned.
- The telemetry emit is throttled to `TELEMETRY_INTERVAL` (0.02 s → 50 Hz).
  Emitting on every loop tick floods the browser with hundreds of messages per
  second and makes the whole machine feel sluggish; 50 Hz is already faster
  than the eye can read the dashboard.
- The pointer path is **not** affected by that throttle: `update()` still runs
  on every tick and applies the newest frame of every device frame (~110 fps).
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
    "deadzone":       150,    // raw ADC units ignored at rest
    "base_speed":     0.015,  // pixels per raw unit PER FRAME (see note)
    "max_speed_mult": 3.0,    // speed multiplier at full ramp
    "ramp_time":      0.6,    // seconds to reach max_speed_mult
    "sniper_mult":    0.15    // precision-mode multiplier
  },
  "scroll": { "deadzone": 400, "scroll_amount": 4, "cooldown": 0.35 },
  "media":  { "deadzone": 800, "cooldown": 0.4 },
  "arrow":  { "deadzone": 600, "cooldown": 0.34 }
}
```

Deadzones are in **raw ADC units (0–4095)**, not pixels. With the stick resting
near raw 2000 and `CENTER` at 2048, a deadzone of 150 means the cursor starts
moving after roughly 200 units of push (~5 % of travel). A deadzone of 2000
means the stick has to be shoved almost to its end before anything happens.

**`base_speed` is per frame, not per second.** The pointer moves
`dx × base_speed` pixels *for every frame the device sends* (~110/s measured),
so the on-screen speed is `dx × base_speed × 110` px/s and it scales with the
frame rate. Reference values with the defaults above:

| deflection (raw units) | px/s at ramp start | px/s after the 0.6 s ramp |
|---|---|---|
| 150 | ~250 | ~670 |
| 450 | ~750 | ~2000 |
| 950 | ~1570 | ~4200 |
| 2000 | ~3300 | ~8800 |

### 7.2 Fallback defaults

`controller.py:load_config()` has a hard-coded fallback dict used when
`config.json` is missing. It is kept **identical** to the file's values — if the
two ever drift, a deleted config file silently changes the feel of the device.

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

### 8.4 Axis convention on the dashboard

The stick module is mounted rotated: the **pot's Y axis drives the pointer's
horizontal axis** (`modes.py` maps `move_x = dy`, `move_y = dx`, and the
scroll/media/arrow profiles follow the same convention). The dashboard therefore
reports the *pointer's* axes, not the raw pots: `app.py` swaps `raw_x`/`raw_y`
and `dx`/`dy` when it emits `telemetry_data`, and the panel labels the rows
"Position X (horizontal)" / "Position Y (vertical)". The controller's internals
(`CENTER_X/CENTER_Y`, the recenter button) stay in raw pot space.

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

## 10. Known design constraints

Deliberate or hardware-specific behaviours that look like bugs but are not
"fixed" by accident:

- **The pointer speed is frame-rate dependent.** `base_speed` is applied per
  frame, so the px/s scales with how many frames the device sends (~110/s).
  Before the framing fix in §5.1 roughly half the frames were being dropped by
  the port purge, which silently halved the pointer speed; the fix restored it
  to the real frame rate. Any future change to the frame rate changes the feel.
- **The axes are swapped**: `move_x = dy`, `move_y = dx` (`modes.py`). This
  compensates for the physical orientation of the joystick module. If the
  module is mounted differently, swap the two.
- **`CENTER_X/CENTER_Y` default to 2048/2048** (the ADC midpoint), but this
  joystick actually rests near raw 2000/1968 — a constant offset of
  (-48, -80). Harmless while the deadzone is above ~100, but press **Capture
  Rest Center Baseline** once to make the travel symmetric.
- **The firmware's command read is blocking.** `Serial.readStringUntil('\n')`
  waits for a newline with no timeout, so a command that arrives without one
  freezes the firmware (and with it the telemetry). The PC always appends
  `\n`; a future command type must do the same.
- **The dashboard's slider broadcast** re-syncs every open browser on each
  `update_setting`, i.e. on every `oninput` tick while a slider is dragged.

## 11. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Pointer teleports/jitters at rest, deadzone ignored | A frame was corrupted in the reader (historically `reset_input_buffer()` cutting the next frame). Check the raw values in the dashboard telemetry: they must stay inside a narrow band (~1950–2050). Run `pc_side_py/test_rx_framing.py`. |
| Cursor keeps flying after the stick is released | A backlog of frames was replayed as movement. The reader must only apply the newest frame (§5.1). |
| Everything feels sluggish / laggy | The sensor loop is running at ~65 Hz instead of ~650 Hz: `timeBeginPeriod(1)` is missing (§6), or the device frame rate dropped. |
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
