import time
import json
import os
import pyautogui
from modes import MouseMode, ScrollMode, MediaMode, ArrowKeysMode

class JoystickController:
    def __init__(self, serial_instance, tap_threshold=0.25, mode_hold_threshold=0.8):
        self.esp32 = serial_instance
        self.tap_threshold = tap_threshold
        self.mode_hold_threshold = mode_hold_threshold
        self.config_path = "config.json"
        
        # Load the configuration database matrix
        self.load_config()

        # Initialize modular profile layout frameworks
        self.modes = [MouseMode(self), ScrollMode(self), MediaMode(self), ArrowKeysMode(self)]
        self.mode_names = ["Mouse Mode", "Scroll Mode", "Media Mode", "Arrow Keys Mode"]
        self.current_mode_idx = 0

        self.CENTER_X = 2048
        self.CENTER_Y = 2048

        self.is_button_down = False
        self.button_pressed_time = 0
        self.mode_shifted_this_press = False
        
        # Safe storage container cache for UI update triggers
        self.latest_telemetry = {"raw_x": 2048, "raw_y": 2048, "button": 1, "dx": 0, "dy": 0}

        # Incomplete trailing bytes of the serial stream, kept until its newline arrives
        self._rxbuf = b''

    def load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                self.config = json.load(f)
        else:
            # Fallback default parameter mapping blocks if array gets deleted
            # Keep in sync with config.json
            self.config = {
                "audio": {"master_mute": False, "profile_shift": True, "media_actions": True, "arrow_actions": True},
                "mouse": {"deadzone": 600, "base_speed": 0.015, "max_speed_mult": 4.0, "ramp_time": 2.9, "sniper_mult": 0.2},
                "scroll": {"deadzone": 1000, "scroll_amount": 4, "cooldown": 0.35},
                "media": {"deadzone": 2000, "cooldown": 0.4},
                "arrow": {"deadzone": 2000, "cooldown": 0.34}
            }

    def save_config(self):
        with open(self.config_path, "w") as f:
            json.dump(self.config, f, indent=2)

    def update_offsets(self):
        """Re-centers the analog offsets based on current positional physics readings."""
        self.CENTER_X = self.latest_telemetry["raw_x"]
        self.CENTER_Y = self.latest_telemetry["raw_y"]
        print(f"[CALIBRATION] Re-centered coordinate space layout to: X={self.CENTER_X}, Y={self.CENTER_Y}")

    def send_beep_command(self, count):
        """Writes structural sound pulses downward across the physical connection pipe line."""
        if self.config["audio"]["master_mute"]:
            return
        payload = f"BEEP:{count}\n"
        try:
            self.esp32.write(payload.encode('utf-8'))
        except Exception:
            pass

    def update(self):
        if self.esp32.in_waiting > 0:
            try:
                # Read every arrived byte and split on newlines. Never purge the port:
                # a purge can cut the next frame in half and its tail then parses as a
                # complete frame with a corrupted first field.
                self._rxbuf += self.esp32.read(self.esp32.in_waiting)
                if len(self._rxbuf) > 4096:
                    self._rxbuf = b''  # frame that never terminates, resync on the next one
                *frames, self._rxbuf = self._rxbuf.split(b'\n')
                # Only the newest frame may move the pointer: if the engine was
                # blocked, a backlog of frames piled up, and replaying all of them
                # would fling the cursor across the screen for seconds.
                for frame in frames[:-1]:
                    self._handle_frame(frame.decode('utf-8', errors='ignore').strip(),
                                       move=False)
                if frames:
                    self._handle_frame(frames[-1].decode('utf-8', errors='ignore').strip(),
                                       move=True)
            except Exception:
                pass

    def _handle_frame(self, line, move=True):
        data = line.split(',')
        if len(data) != 3:
            return

        raw_x = int(data[0])
        raw_y = int(data[1])
        button = int(data[2])
        current_time = time.time()

        dx = raw_x - self.CENTER_X
        dy = raw_y - self.CENTER_Y

        # Update high speed tracking telemetry cache container
        self.latest_telemetry = {
            "raw_x": raw_x, "raw_y": raw_y, "button": button, "dx": dx, "dy": dy
        }

        sniper_active = False
        active_mode = self.modes[self.current_mode_idx]

        # --- BUTTON EVENT PROCESSOR ---
        if button == 0:
            if not self.is_button_down:
                self.button_pressed_time = current_time
                self.is_button_down = True
                self.mode_shifted_this_press = False

            duration = current_time - self.button_pressed_time
            if duration > self.mode_hold_threshold and not self.mode_shifted_this_press:
                self.cycle_mode()
                self.mode_shifted_this_press = True

            elif duration > self.tap_threshold and not self.mode_shifted_this_press:
                if self.current_mode_idx == 0:
                    sniper_active = True

        elif button == 1 and self.is_button_down:
            duration = current_time - self.button_pressed_time
            if duration <= self.tap_threshold and not self.mode_shifted_this_press:
                active_mode.handle_click()
            self.is_button_down = False

        # --- INPUT ROUTING EXECUTION ---
        if move:
            active_mode.handle_input(dx, dy, sniper_active, current_time)

    def cycle_mode(self):
        self.current_mode_idx = (self.current_mode_idx + 1) % len(self.modes)
        print(f"\n[MODE SHIFT] Switched Profile Context to: {self.mode_names[self.current_mode_idx]}")
        
        # Verify if profile beeps are enabled before executing tone outputs
        if self.config["audio"]["profile_shift"]:
            self.send_beep_command(self.current_mode_idx + 1)