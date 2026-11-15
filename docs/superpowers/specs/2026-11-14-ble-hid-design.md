# Design: BLE HID Bluetooth Mouse for the Joystick

Date: 2026-11-14
Branch: `deepanshu/bleHidv1.0`
Status: draft for approval

## Intent and the why

The Bluetooth link to the ESP32 has been unreliable for weeks: the PC and phone keep
failing the SPP pairing, leaving "Unknown device" flickering in the Bluetooth device
list and the connection silently breaking. Classic SPP is simply not dependable on
this hardware/Windows combination.

The fix is to stop pretending to be a serial port and become what a Bluetooth mouse
actually is: a **BLE HID device** that Windows pairs as "Bluetooth mouse" with a
mouse icon and a battery reading. The ESP32 does the full input pipeline itself —
deadzone, ramp, sniper, profiles, beeps — so no Python process is required for
wireless use. The web dashboard remains for tuning and calibration, and it must keep
working — over both USB and Bluetooth.

Success looks like: pair `JoystickMouse` once in Windows, and Windows shows it as a
mouse with a battery percentage, input follows the stick instantly, and the same
dashboard that tunes the USB-connected device also works over Bluetooth.

## Goals

- Wireless input goes straight to Windows as a real **BLE HID mouse** (X/Y relative
  movement, left/right click, scroll wheel).
- Behaviour is identical to the current USB build: deadzone, acceleration ramp,
  sniper/precision mode, profile cycling (hold button ≥ 0.8 s), tap/hold click
  semantics, and beeps on actions.
- **Port the full input pipeline into the firmware** (C++), instead of
  double-dipping through a PC app.
- The same dashboard works for tuning **with and without the cable**: USB serial
  path for the wired experience, BLE GATT service for the wireless one. Both use the
  same telemetry format and the same control protocol.
- Battery level is reported via the **Battery Service (`0x180F`)**, read from an
  **ADC voltage-divider** on the Li-ion/LiPo pack, mapped 3.0–4.2 V → 0–100 %.
- The current USB-serial firmware path keeps working, unchanged wire format.

## Non-goals

- No WiFi in the firmware.
- No OTA updates, no bonding with PIN/passkey — BLE HID pairs with the standard
  "Just Works" pairing (auto-accept), the same behaviour SPP had.
- No BLE keyboard for Arrow Keys mode in this branch; Arrow/Media/Scroll profiles
  are USB-only for now (they need keyboard HID reports and a separate report id).
  The mouse report map is implemented to leave a slot for a keyboard report later.
- No Bluetooth LE Audio, no BLE5 extended features.

## Constraints

- Board: classic `esp32dev` (ESP32), PlatformIO `espressif32` (installed
  v7.0.0, Arduino-ESP32 3.x). The precompiled SDK has
  `CONFIG_BLUEDROID_ENABLED=y` and the bundled `BLE` library includes
  `BLEHIDDevice` (`BLEHIDDevice.h`) with mouse/keyboard HID services built in.
- `CONFIG_NIMBLE_ENABLED` is **not** set, so the BlueDroid path is what we use.
- Flash: current build is ~84 % of the 1.3 MB flash. BluetoothSerial (SPP) and
  Bluetooth libraries must be removed from the build to make room — the new
  firmware does not use classic BT at all. If the build does not fit, the plan is
  to disable SPP in `platformio.ini` (e.g. by not instantiating `BluetoothSerial`)
  and, only if still too large, partition scheme changes.
- RAM is fine — 12 % used today; BLE + HID tables add a few KB.
- USB ADC2 reads are impossible while Bluetooth is active; we already use ADC1
  pins (34/35) and would use another ADC1 pin (36/39/33/32) for the battery.
- Bluetooth Classic (SPP) is removed entirely. USB COM port keeps working.
- Windows 10/11 pairing: HID over BLE with "Just Works" — the device pairs on
  sight without a PIN; clicking pairs it as a mouse with no extra prompts.

## The parts of the how

### 1. BLE architecture

| Service | UUID | Purpose |
|---|---|---|
| HID | `0x1812` | Mouse: buttons + X/Y relative movement + wheel |
| Battery | `0x180f` | `0x2a19` battery level, ADC-measured |
| Device Information | `0x180a` | manufacturer = "Espressif" / "LJ" |
| Joystick Control (custom) | `0x2000` (custom 128-bit UUID) | USB-compatible telemetry + control |

**Advertising**: `JoystickMouse`, connectable, 128-bit HID service UUID in the
adv packet (or 16-bit). Auto-accept pairing (no security required by the service).

**HID report map**: Report ID 1 — mouse (3 buttons, X/Y relative 8-bit each,
wheel 8-bit). An empty Report ID 2 slot is reserved for keyboard in a later branch.

**Custom control service** — one notify characteristic carrying the identical
`rawX,rawY,button\n` wire format as USB serial, plus one write characteristic for
the `BEEP:` command. The PC app's transport layer treats both paths identically,
so the port selection logic (`transport.py` equivalent) gains a BLE branch instead
of a separate code path.

**Bonding**: none (auto-accept). The device is bonded by the OS after first
connection; re-pairing after unpair just works.

**Connection interval**: default (~15 ms) — good enough for a mouse at
~65 reports/s.

### 2. Firmware layout

- `src/main.cpp` — ADC reads, button state machine, deadzone/ramp/sniper, the
  four profiles, HID report packing, telemetry framing, command handling, BLE
  service setup. ~400 lines.
- The Python decision logic is ported line-by-line into C++: same deadzone model,
  same acceleration curve (defaults 155 / 0.015 → per-second 1.65 equivalent),
  same tap/hold/0.8 s mode-switch rules.
- The `app.py` protocol (`rawX,rawY,button\n`) is unchanged — works over USB and
  over BLE notifications.
- `BEEP` command arrives on the same write characteristic shape as USB serial.

### 3. PC-side app changes

- `transport.discover_link()` gains a third candidate kind: **BLE** — enumerated
  after USB (cable wins), detected when SPP COM ports are unusable. The dashboard
  gains no new buttons or fields; it just shows `BLE (JoystickMouse)` or
  `USB (COM10)` in the existing link status slot.
- The app uses **bleak** to talk to the custom control service over BLE — raw ADC
  frames for telemetry, plus `BEEP:n` writes for feedback. This is a single new
  module (`pc_side_py/ble_transport.py`); the framing is identical.
- The dashboard no longer cares how the device is linked — it emits telemetry and
  receives it the same way.

### 4. Battery service

- Hardware: Li-ion/LiPo → 100 kΩ → GPIO **36** (ADC1 channel 0, input-only, ideal
  — nothing else needs it) → 100 kΩ → GND. 4.2 V at the pack is 2.1 V at the pin,
  comfortably inside the 3.3 V ADC range with no saturation.
- Mapping: 4.2 V → 100 %, 3.3 V → 0 %, linear, clamped.
- Update the level every 5 s via `BLEHIDDevice::setBatteryLevel()`.

### 5. Config / tuning over both paths

No custom config service is needed this branch: raw ADC telemetry comes over both
transports and the app's config logic is transport-agnostic, so the same sliders
write to memory and `save_configuration` writes to `config.json` the same way.
The only transport-specific part is open/probe/connect, inside `transport.py`.

## Testing

- Build: `pio run -e esp32dev` → must fit Flash ≤ 90 % with headroom.
- Host-side tests stay in `test/`: `test_rx_framing.py` remains valid (the wire
  format is unchanged); a new `test_ble_config.py` covers the seek/clamp logic if
  any config logic gets ported into the app for BLE.
- Manual checklist (all require hardware) — pair, browse the custom service in a
  BLE scanner, confirm live telemetry over BLE, confirm the dashboard badge
  shows `BLE (JoystickMouse)`, and confirm USB still works.

## Manual verification checklist

1. Flash, plug in a power bank: `JoystickMouse` appears in Windows' Bluetooth
   device list, pairs on sight as a **mouse** (not a COM port).
2. Windows shows battery percentage after a few seconds.
3. Stick movement → Windows cursor moves; left click, scroll wheel work.
4. Hold ≥ 0.8 s → profile switch beeps; tap → click actions.
5. `pio run -e esp32dev -t monitor` while USB is connected: live `rawX,rawY…`
   frames, unchanged format.
6. Start `app.py` with USB unplugged: dashboard shows `BLE (JoystickMouse)` and
   live telemetry.
7. Plug in the cable: `USB (COM10)` takes over within ~2 s.
8. Flash a fresh build and unpair/re-pair: works without a PIN.

## Known risks / decisions to surface

1. **SPP libraries removed from the build.** `BluetoothSerial` and the classic BT
   stack are excluded. If any transitive dependency is missed, the build on
   `esp32dev` will fail with unresolved BT symbols; fix is to remove them and
   nothing else.
2. **BLE report rate vs responsiveness.** ~15 ms default interval is fine for
   mouse-like use; if the cursor ever feels sluggish, bump to 10 ms.
3. **Joystick-only-mouse limitation.** Arrow Keys and Media modes need keyboard
   HID reports (separate report map / report id) — explicitly out of scope.
4. **Battery divider consumes GPIO36.** If the user needs GPIO36 for something
   else, GPIO39 (also ADC1, input-only) is the alternative with zero code change
   — one `ADC1_CHANNEL` constant to swap.
5. **Bonding/security.**
   - Pairing is unencrypted auto-accept; acceptable for a desk device but it
     means any nearby Windows machine can enumerate it. Pinning security on is
     possible later (BLE Secure Connections) without changing the service set.
6. **Interfering apps.** No classic SPP means no scanned COM ports — the previous
   "power bank looks like a COM port" confusion goes away entirely.
