#include "config.h"
#include "buzzer.h"
#include "hid.h"
#include "input.h"
#include "serial_commands.h"

/* Wiring for the two input paths:
 *
 *   USB cable -> telemetry (rawX,rawY,button\n) and BEEP commands
 *   Bluetooth -> BLE HID mouse reports
 *
 * main.cpp only ties those together; the input decision logic lives in
 * input.cpp and the HID service lives in hid.cpp.
 */

static InputState inputState;

void setup() {
  Serial.begin(115200);
  pinMode(SW_PIN, INPUT_PULLUP);
  buzzer_init();
  pinMode(BATTERY_PIN, INPUT);
  analogSetAttenuation(ADC_11db);

  inputStateInit(inputState);
  hid_init("JoystickMouse");
}

void loop() {
  int rawX = analogRead(X_PIN);
  int rawY = analogRead(Y_PIN);
  int swRaw = digitalRead(SW_PIN); // 0 = pressed, 1 = released

  // USB telemetry, unchanged: rawX,rawY,button\n
  Serial.print(rawX);
  Serial.print(",");
  Serial.print(rawY);
  Serial.print(",");
  Serial.println(swRaw);

  // Bluetooth HID report
  float now = millis() / 1000.0f;
  int swPressed = (swRaw == LOW) ? 1 : 0;
  MoveResult mv = inputStep(inputState, rawX, rawY, swPressed, now);
  hid_send_mouse_report(mv.buttons, mv.dx, mv.dy, mv.wheel);

  // Profile switch beeps
  if (mv.mode_shift_beeps) {
    buzzer_beep(mv.mode_shift_beeps);
  }

  pump_serial_commands();
  delay(8);
}
