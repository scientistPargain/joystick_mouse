import time
import pyautogui

class BaseMode:
    """Base class that all operational modes inherit from."""
    def __init__(self):
        pass
    def handle_input(self, dx, dy, deadzone, sniper_active, current_time):
        raise NotImplementedError

class MouseMode(BaseMode):
    """Handles standard mouse translation, acceleration, and sniper dampening."""
    def __init__(self, base_speed=0.015, max_speed_mult=4.0, ramp_time=0.8, sniper_mult=0.2):
        super().__init__()
        self.base_speed = base_speed
        self.max_speed_mult = max_speed_mult
        self.ramp_time = ramp_time
        self.sniper_mult = sniper_mult
        self.stick_held_start_time = 0
        self.is_stick_active = False

    def handle_input(self, dx, dy, deadzone, sniper_active, current_time):
        currently_active = abs(dx) > deadzone or abs(dy) > deadzone
        
        if currently_active and not sniper_active:
            if not self.is_stick_active:
                self.stick_held_start_time = current_time
                self.is_stick_active = True
            
            duration_held = current_time - self.stick_held_start_time
            speed_factor = 1.0 + (self.max_speed_mult - 1.0) * min(duration_held / self.ramp_time, 1.0)
            current_modifier = self.base_speed * speed_factor
        elif sniper_active:
            self.is_stick_active = False
            current_modifier = self.base_speed * self.sniper_mult
        else:
            self.is_stick_active = False
            current_modifier = self.base_speed

        # Hardware mapping: dy -> X movement, dx -> Y movement
        move_x = dy * current_modifier if abs(dy) > deadzone else 0
        move_y = dx * current_modifier if abs(dx) > deadzone else 0

        if move_x != 0 or move_y != 0:
            pyautogui.moveRel(move_x, move_y)

class ScrollMode(BaseMode):
    """Joystick up/down scrolls pages. Left/right switches browser tabs."""
    def __init__(self):
        super().__init__()
        self.last_action_time = 0
        self.cooldown = 0.35  # Clean cooldown window for browser tabs

    def handle_input(self, dx, dy, deadzone, sniper_active, current_time):
        # Physical UP/DOWN movement maps to dx on your hardware
        if abs(dx) > deadzone:
            # Scroll up when pushed forward, scroll down when pulled back
            scroll_amount = 4 if dx < 0 else -4
            pyautogui.scroll(scroll_amount)

        # Physical LEFT/RIGHT movement maps to dy on your hardware
        if current_time - self.last_action_time > self.cooldown:
            if dy > deadzone:
                pyautogui.hotkey('ctrl', 'tab')          # Next Tab
                self.last_action_time = current_time
            elif dy < -deadzone:
                pyautogui.hotkey('ctrl', 'shift', 'tab')   # Previous Tab
                self.last_action_time = current_time

class MediaMode(BaseMode):
    """Joystick up/down controls master volume. Left/right skips tracks."""
    def __init__(self):
        super().__init__()
        self.last_action_time = 0
        self.cooldown = 0.3 

    def handle_input(self, dx, dy, deadzone, sniper_active, current_time):
        if current_time - self.last_action_time > self.cooldown:
            # Physical UP/DOWN movement maps to dx on your hardware
            if dx > deadzone:
                pyautogui.press('volumedown')
                self.last_action_time = current_time
            elif dx < -deadzone:
                pyautogui.press('volumeup')
                self.last_action_time = current_time
            
            # Physical LEFT/RIGHT movement maps to dy on your hardware
            if dy > deadzone:
                pyautogui.press('nexttrack')
                self.last_action_time = current_time
            elif dy < -deadzone:
                pyautogui.press('prevtrack')
                self.last_action_time = current_time

class ArrowKeysMode(BaseMode):
    """Maps joystick axes to directional keyboard arrow keys."""
    def __init__(self):
        super().__init__()
        self.last_action_time = 0
        self.cooldown = 0.15

    def handle_input(self, dx, dy, deadzone, sniper_active, current_time):
        if current_time - self.last_action_time > self.cooldown:
            # Physical LEFT/RIGHT maps to dy
            if dy > deadzone:
                pyautogui.press('right')
                self.last_action_time = current_time
            elif dy < -deadzone:
                pyautogui.press('left')
                self.last_action_time = current_time
            
            # Physical UP/DOWN maps to dx
            if dx > deadzone:
                pyautogui.press('down')
                self.last_action_time = current_time
            elif dx < -deadzone:
                pyautogui.press('up')
                self.last_action_time = current_time