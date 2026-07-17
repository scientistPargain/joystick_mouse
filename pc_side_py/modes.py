import time
import pyautogui

class BaseMode:
    def __init__(self, deadzone):
        self.deadzone = deadzone
    def handle_input(self, dx, dy, sniper_active, current_time):
        raise NotImplementedError
    def handle_click(self):
        raise NotImplementedError

class MouseMode(BaseMode):
    """Tight deadzone (180) for precision. Click = Left Click."""
    def __init__(self, base_speed=0.015, max_speed_mult=4.0, ramp_time=0.8, sniper_mult=0.2):
        super().__init__(deadzone=180)
        self.base_speed = base_speed
        self.max_speed_mult = max_speed_mult
        self.ramp_time = ramp_time
        self.sniper_mult = sniper_mult
        self.stick_held_start_time = 0
        self.is_stick_active = False

    def handle_input(self, dx, dy, sniper_active, current_time):
        currently_active = abs(dx) > self.deadzone or abs(dy) > self.deadzone
        
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

        move_x = dy * current_modifier if abs(dy) > self.deadzone else 0
        move_y = dx * current_modifier if abs(dx) > self.deadzone else 0

        if move_x != 0 or move_y != 0:
            pyautogui.moveRel(move_x, move_y)

    def handle_click(self):
        pyautogui.click()  # Standard Left Click

class ScrollMode(BaseMode):
    """Large deadzone (350). Click = Middle Click (Scroll wheel click)."""
    def __init__(self):
        super().__init__(deadzone=350)
        self.last_action_time = 0
        self.cooldown = 0.35  

    def handle_input(self, dx, dy, sniper_active, current_time):
        if abs(dx) > self.deadzone:
            scroll_amount = 4 if dx < 0 else -4
            pyautogui.scroll(scroll_amount)

        if current_time - self.last_action_time > self.cooldown:
            if dy > self.deadzone:
                pyautogui.hotkey('ctrl', 'tab')          
                self.last_action_time = current_time
            elif dy < -self.deadzone:
                pyautogui.hotkey('ctrl', 'shift', 'tab')   
                self.last_action_time = current_time

    def handle_click(self):
        # pyautogui.click(button='middle')  # Middle click to open links in new tabs
        return

class MediaMode(BaseMode):
    """Very large deadzone (450). Click = Play / Pause."""
    def __init__(self):
        super().__init__(deadzone=450)
        self.last_action_time = 0
        self.cooldown = 0.3 

    def handle_input(self, dx, dy, sniper_active, current_time):
        if current_time - self.last_action_time > self.cooldown:
            if dx > self.deadzone:
                pyautogui.press('volumedown')
                self.last_action_time = current_time
            elif dx < -self.deadzone:
                pyautogui.press('volumeup')
                self.last_action_time = current_time
            
            if dy > self.deadzone:
                pyautogui.press('nexttrack')
                self.last_action_time = current_time
            elif dy < -self.deadzone:
                pyautogui.press('prevtrack')
                self.last_action_time = current_time

    def handle_click(self):
        pyautogui.press('playpause')  # Plays or pauses background media

class ArrowKeysMode(BaseMode):
    """Moderate deadzone (250). Click = Enter Key."""
    def __init__(self):
        super().__init__(deadzone=250)
        self.last_action_time = 0
        self.cooldown = 0.15

    def handle_input(self, dx, dy, sniper_active, current_time):
        if current_time - self.last_action_time > self.cooldown:
            if dy > self.deadzone:
                pyautogui.press('right')
                self.last_action_time = current_time
            elif dy < -self.deadzone:
                pyautogui.press('left')
                self.last_action_time = current_time
            
            if dx > self.deadzone:
                pyautogui.press('down')
                self.last_action_time = current_time
            elif dx < -self.deadzone:
                pyautogui.press('up')
                self.last_action_time = current_time

    def handle_click(self):
        pyautogui.press('enter')  # Simulates pressing the Enter key