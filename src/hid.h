#pragma once

/* BLE HID mouse service: creates the BLE device, the mouse report map and the
 * services, and exposes a thin API the input pipeline uses to send results.
 */

#include <Arduino.h>

void hid_init(const char* deviceName);

void hid_send_mouse_report(uint8_t buttons, int8_t dx, int8_t dy, int8_t wheel);
void hid_set_battery_level(uint8_t percent);

bool hid_is_connected();
