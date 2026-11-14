#include "input.h"
#include "config.h"   // profile names, constants

#include <math.h>

const char* profileName(Profile p) {
  switch (p) {
    case Profile::Mouse: return "Mouse Mode";
    case Profile::Scroll: return "Scroll Mode";
    case Profile::Media: return "Media Mode";
    case Profile::Arrow: return "Arrow Keys Mode";
  }
  return "Unknown";
}

void inputStateInit(InputState& s) {
  s.profile = Profile::Mouse;
  s.last_frame_time = -1.0f;      // -1 = first frame contributes nothing
  s.stick_held_start = -1.0f;
  s.subX = 0.0f;
  s.subY = 0.0f;
  s.button_down = false;
  s.button_pressed_at = 0;
  s.profile_shift_pending = Profile::Mouse;
}

static int8_t clampI8(float v) {
  if (v > 127) return 127;
  if (v < -127) return -127;
  return (int8_t)lroundf(v);
}

MoveResult inputStep(InputState& s, int rawX, int rawY, int swPressed, float now) {
  MoveResult out{};
  // Axes are swapped in this mounting: pot Y drives the pointer X axis.
  float pushX = (float)(rawY - CENTER);   // horizontal
  float pushY = (float)(rawX - CENTER);   // vertical

  bool buttonIsDown = swPressed != 0;   // 0 = released, any other = pressed

  // --- button state machine ---
  if (buttonIsDown && !s.button_down) {
    s.button_down = true;
    s.button_pressed_at = millis();
  } else if (!buttonIsDown && s.button_down) {
    s.button_down = false;
    s.button_pressed_at = 0;
    s.stick_held_start = -1.0f;
  }

  bool sniper = false;
  if (s.button_down) {
    float held = (millis() - s.button_pressed_at) / 1000.0f;
    if (held > MODE_HOLD_THRESHOLD) {
      // profile switch: pick next profile now, applied on release; HID may lag a frame
      if (s.profile_shift_pending == s.profile) {
        s.profile = (Profile)(((uint8_t)s.profile + 1) % PROFILE_COUNT);
        out.mode_shift_beeps = (uint8_t)((uint8_t)s.profile + 1);
        s.profile_shift_pending = (Profile)(((uint8_t)s.profile + 1) % PROFILE_COUNT);
      }
      sniper = (s.profile == Profile::Mouse);
    } else if (held > TAP_THRESHOLD) {
      sniper = (s.profile == Profile::Mouse);
    }
  }
  out.sniper_active = sniper;

  // --- move the pointer, only in Mouse Mode (Media/Arrow are USB-only) ---
  if (s.profile == Profile::Mouse) {
    bool stickActive = fabs(pushX) > MOUSE_DEADZONE || fabs(pushY) > MOUSE_DEADZONE;

    float modifier;
    if (stickActive && !sniper) {
      if (s.stick_held_start < 0.0f) {
        s.stick_held_start = now;
      }
      float held = now - s.stick_held_start;
      float factor = 1.0f + (MAX_SPEED_MULT - 1.0f) * fminf(held / RAMP_TIME, 1.0f);
      modifier = BASE_SPEED * factor;
    } else if (sniper) {
      s.stick_held_start = -1.0f;
      modifier = BASE_SPEED * SNIPER_MULT;
    } else {
      s.stick_held_start = -1.0f;
      modifier = BASE_SPEED;
    }

    float dt = (s.last_frame_time < 0.0f) ? 0.0f : (now - s.last_frame_time);
    s.last_frame_time = now;
    if (dt <= 0.0f || dt > MAX_FRAME_GAP) dt = MAX_FRAME_GAP;

    float mx = (fabs(pushX) > MOUSE_DEADZONE) ? (pushX * modifier * dt) : 0.0f;
    float my = (fabs(pushY) > MOUSE_DEADZONE) ? (pushY * modifier * dt) : 0.0f;

    s.subX += mx;
    s.subY += my;
    int wholeX = (int)s.subX;
    int wholeY = (int)s.subY;
    s.subX -= wholeX;
    s.subY -= wholeY;
    out.dx = clampI8(wholeX);
    out.dy = clampI8(wholeY);
  } else {
    // Keep the sub-pixel state tidy while not in Mouse Mode
    s.stick_held_start = -1.0f;
    s.subX = 0.0f;
    s.subY = 0.0f;
  }

  // --- wheel on Scroll Mode: horizontal axis drives the wheel ---
  if (s.profile == Profile::Scroll) {
    if (fabs(pushX) > SCROLL_DEADZONE) out.wheel = (pushX > 0) ? 1 : -1;
    if (buttonIsDown) out.buttons |= HID_MIDDLE;
  }

  // --- buttons pass through by profile ---
  if (buttonIsDown) {
    if (s.profile == Profile::Mouse) out.buttons |= HID_LEFT;
    else if (s.profile == Profile::Scroll) out.buttons |= HID_MIDDLE;
  }

  return out;
}
