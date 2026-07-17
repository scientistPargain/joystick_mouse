import time
from modes import MouseMode, ScrollMode, MediaMode, ArrowKeysMode

class JoystickController:
    def __init__(self, serial_instance, tap_threshold=0.25, mode_hold_threshold=0.8):
        self.esp32 = serial_instance
        self.tap_threshold = tap_threshold
        self.mode_hold_threshold = mode_hold_threshold

        self.modes = [MouseMode(), ScrollMode(), MediaMode(), ArrowKeysMode()]
        self.mode_names = ["Mouse Mode", "Scroll Mode", "Media Mode", "Arrow Keys Mode"]
        self.current_mode_idx = 0

        self.CENTER_X = 2048
        self.CENTER_Y = 2048

        self.is_button_down = False
        self.button_pressed_time = 0
        self.mode_shifted_this_press = False

    def update(self):
        if self.esp32.in_waiting > 0:
            line = self.esp32.readline().decode('utf-8', errors='ignore').strip()
            self.esp32.reset_input_buffer()
            
            data = line.split(',')
            if len(data) != 3:
                return

            raw_x = int(data[0])
            raw_y = int(data[1])
            button = int(data[2]) 
            current_time = time.time()

            dx = raw_x - self.CENTER_X
            dy = raw_y - self.CENTER_Y

            sniper_active = False
            active_mode = self.modes[self.current_mode_idx]

            # --- CORRECTION: ACCURATE DUAL-PURPOSE STATE ENGINE ---
            if button == 0:  # Physical hold down
                if not self.is_button_down:
                    self.button_pressed_time = current_time
                    self.is_button_down = True
                    self.mode_shifted_this_press = False
                
                duration = current_time - self.button_pressed_time
                
                # Check for mode change
                if duration > self.mode_hold_threshold and not self.mode_shifted_this_press:
                    self.cycle_mode()
                    self.mode_shifted_this_press = True  # Locks cycle out until release
                
                # Activate Sniper mode ONLY if we are in mouse mode AND haven't triggered a mode switch
                elif duration > self.tap_threshold and not self.mode_shifted_this_press:
                    if self.current_mode_idx == 0:
                        sniper_active = True

            elif button == 1 and self.is_button_down:  # Released
                duration = current_time - self.button_pressed_time
                
                # Only execute standard tap clicks if we didn't just perform a mode shift or sniper drag
                if duration <= self.tap_threshold and not self.mode_shifted_this_press:
                    active_mode.handle_click()
                
                self.is_button_down = False

            # --- ROUTE DATA CHANNELS ---
            active_mode.handle_input(dx, dy, sniper_active, current_time)

    def cycle_mode(self):
        self.current_mode_idx = (self.current_mode_idx + 1) % len(self.modes)
        print(f"\n[MODE SHIFT] Switched Profile Context to: {self.mode_names[self.current_mode_idx]}")
        
        # Write beep payload string back across the USB serial pipe to hardware
        beep_count = self.current_mode_idx + 1
        payload = f"BEEP:{beep_count}\n"
        self.esp32.write(payload.encode('utf-8'))