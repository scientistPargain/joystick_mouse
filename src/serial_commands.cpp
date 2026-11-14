#include "serial_commands.h"
#include "buzzer.h"

#include <Arduino.h>

void pump_serial_commands() {
  if (Serial.available() <= 0) return;

  String command = Serial.readStringUntil('\n');
  command.trim();
  if (command.length() == 0) return;

  if (!command.startsWith("BEEP:")) return;
  long count = command.substring(5).toInt();
  if (count < 1) count = 1;
  if (count > 10) count = 10;
  buzzer_beep((uint8_t)count);
}
