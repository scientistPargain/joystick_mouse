# AGENTS.md

ESP32 joystick that acts as a multi-tool PC mouse (mouse / scroll / media / arrow modes) with a Flask-SocketIO tuning dashboard.

## Layout: two halves, one serial link

| Where | What | Entry |
|---|---|---|
| `src/main.cpp` | ESP32 firmware (PlatformIO, `env:esp32dev`, Arduino framework) | `pio run -e esp32dev` |
| `pc_side_py/` | PC-side engine + web dashboard | `pc_side_py/app.py` |
| `pc_side_py/modes.py` | The 4 input profiles (Mouse, Scroll, Media, Arrow) | |
| `pc_side_py/controller.py` | `JoystickController`: parsing, button state machine, config I/O | |
| `pc_side_py/config.json` | Live tuning values (deadzones, speeds, cooldowns, audio flags) | |
| `pc_side_py/templates/index.html` | Single-file dashboard (inline CSS/JS, socket.io from CDN) | |

`pc_side_py/pc_controller.py` and `pc_controller_v2.py` are the older CLI-only versions. `pc_controller.py` is a standalone v1 (own parsing/loop, does not use `controller.py`) — superseded; `pc_controller_v2.py` is the CLI front-end over the shared `JoystickController`. Don't wire new features into `pc_controller.py`.

## Commands

```powershell
pio run -e esp32dev            # build firmware
pio run -e esp32dev -t upload  # flash
pio run -e esp32dev -t monitor # serial monitor, 115200
cd pc_side_py; .\venv\Scripts\python.exe app.py   # dashboard at http://127.0.0.1:5000
cd pc_side_py; .\venv\Scripts\python.exe pc_controller_v2.py  # CLI, no web UI
.\pc_side_py\venv\Scripts\python.exe test\test_rx_framing.py  # serial framing regression test
```

`test/test_rx_framing.py` is the only test in the repo (plain asserts, no pytest). It pins the serial framing rules and the "a backlog must not replay as pointer movement" rule — run it after touching `controller.py`'s reader. Firmware has no test suite (the root `test/` folder also holds the PlatformIO placeholder for firmware unit tests).

## Serial protocol (115200, both directions)

- ESP32 → PC, every ~8 ms: `rawX,rawY,button\n` (ADC 12-bit, 0-4095; button `0`=pressed `1`=released).
- PC → ESP32: `BEEP:<count>\n` (firmware beeps `count` times on pin 25).

Firmware pins: X=34, Y=35 (ADC1), SW=32 (`INPUT_PULLUP`), buzzer=25.

Firmware and Python must agree on this format — change both sides together.

## Python side quirks that will bite you

- **Run from inside `pc_side_py/`.** `config.json` is opened by relative path in `controller.py`; launching from the repo root silently loads fallback defaults and writes the config to the wrong place.
- **`from gevent import monkey; monkey.patch_all()` must stay the first import in `app.py`** — before `flask`, `flask_socketio`, `pyserial`. Moving it down breaks the async mode.
- **`SERIAL_PORT` is hardcoded in three places** (`app.py`, `pc_controller.py`, `pc_controller_v2.py`). The Windows COM number changes with USB re-enumeration; update all three.
- **Never call `reset_input_buffer()` on the serial port.** A purge discards the head of the *next* frame; the tail then parses as a complete frame with a corrupted first field. The reader must accumulate bytes and split on newlines (`controller.py:update()`).
- **Only the newest frame may move the pointer.** If the engine is ever blocked, a backlog of frames piles up in the driver buffer; replaying all of them flings the cursor across the screen for seconds.
- **Windows timer granularity is ~15.6 ms**, which turns `gevent.sleep(0.001)` into a 15 ms sleep and drops the sensor loop from ~650 Hz to ~65 Hz. `app.py` calls `timeBeginPeriod(1)` for this reason — do not remove it.
- **Config is in-memory until explicitly saved.** The dashboard's `update_setting` event mutates only `controller.config`; `save_configuration` is the only path that writes `config.json`. A browser reconnect re-reads `config.json` from disk and **discards unsaved tuning changes**.
- **`pyautogui` drives the real mouse/keyboard.** There is no headless mode; don't run the engine unattended. `pyautogui.FAILSAFE` is only enabled in the legacy `pc_controller.py`, not in `controller.py`.
- Socket.io event names are shared between `app.py` (server) and `templates/index.html` (client): `telemetry_data`, `sync_config`, `save_confirmed`, `update_setting`, `save_configuration`, `trigger_recenter`, `trigger_test_beep`. Rename in one place only and the dashboard breaks silently.

## Behaviour model

- Modes cycle by **holding the joystick button ≥ 0.8 s**; the mode index lives in `JoystickController.current_mode_idx` and `mode_names` (order must match the `self.modes` list).
- A **tap ≤ 0.25 s** = click (`handle_click` of the active mode); a press between tap and hold thresholds = sniper/precision multiplier (mouse mode only).
- `dx/dy` are raw ADC minus `CENTER_X/CENTER_Y` (default 2048). `trigger_recenter` re-centres on the current reading.
- Deadzone/speed values are read from `self.controller.config` at every input event — change `config.json`, don't cache values in the mode classes.

## Gotchas

- `.vscode/c_cpp_properties.json` and `.vscode/launch.json` are PlatformIO-generated and contain absolute paths; never hand-edit them.
- `pc_side_py/venv/` is a local, gitignored venv (Python 3.11) that already has Flask/Flask-SocketIO/gevent/pyserial/pyautogui installed — use it instead of creating a new env.
- The dashboard pulls `socket.io.js` from a CDN, so it needs internet on first load.
