#pragma once

/* Input pipeline — pure decision logic, no Arduino Serial and no BLE inside.
 * Reads the two pot values and the button state each tick and produces one
 * HID report (buttons, dx, dy, wheel). Matches the behaviour the Python port
 * had, ported to C++.
 */

#include "config.h"

struct InputState {
  Profile profile;          // current profile
  float last_frame_time;    // seconds
  float stick_held_start;   // seconds, -1 when stick is released
  float subX, subY;         // sub-pixel accumulators
  bool button_down;         // physical button state
  unsigned long button_pressed_at; // millis()
  Profile profile_shift_pending;   // profile chosen by a hold, applied on release
};

struct MoveResult {
  int8_t dx;
  int8_t dy;
  int8_t wheel;
  uint8_t buttons;           // HID bitmask
  bool sniper_active;
  uint8_t mode_shift_beeps;  // beeps to emit on a hold-shift, else 0
};

void inputStateInit(InputState& s);
MoveResult inputStep(InputState& s, int rawX, int rawY, int swPressed, float now);
const char* profileName(Profile p);
