#pragma once
#include <Arduino.h>

/* ---- Wiring -------------------------------------------------- */
const int X_PIN = 34;      // ADC1, input-only — stick axis X (vertical orientation)
const int Y_PIN = 35;      // ADC1, input-only — stick axis Y (horizontal orientation)
const int SW_PIN = 32;     // INPUT_PULLUP -> GND when pressed
const int BUZZER_PIN = 25; // active buzzer, HIGH drives it
const int BATTERY_PIN = 36; // ADC1, input-only; Li-ion through a divider

/* ---- ADC ---------------------------------------------------- */
const int CENTER = 2048;   // raw ADC midpoint (12-bit)

/* ---- Input tuning (defaults mirror pc_side_py/config.json) -- */
const int MOUSE_DEADZONE = 155;
const int SCROLL_DEADZONE = 1000;
const float BASE_SPEED = 1.65f;      // px/s per raw unit
const float RAMP_TIME = 2.9f;        // seconds to full speed
const float MAX_SPEED_MULT = 4.0f;
const float SNIPER_MULT = 0.2f;
const float TAP_THRESHOLD = 0.25f;         // s: tap = click
const float MODE_HOLD_THRESHOLD = 0.8f;    // s: hold = switch profile
const float SCROLL_COOLDOWN = 0.35f;       // s between scroll actions
const float MAX_FRAME_GAP = 0.05f;         // s: max dt a frame may claim

/* ---- Profiles ------------------------------------------------- */
enum class Profile : uint8_t { Mouse = 0, Scroll = 1, Media = 2, Arrow = 3 };
constexpr uint8_t PROFILE_COUNT = 4;

/* ---- HID ------------------------------------------------------ */
const uint8_t REPORT_ID_MOUSE = 1;
const uint8_t HID_LEFT = 0x01;
const uint8_t HID_MIDDLE = 0x04;
