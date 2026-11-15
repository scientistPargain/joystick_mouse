#pragma once
#include <Arduino.h>

/* Active buzzer driver (pin 25). */

void buzzer_init();
void buzzer_beep(uint8_t count);
