import time
import pyautogui

class BaseMode:
    def __init__(self, mode_name, controller_ref):
        self.mode_name = mode_name
        self.controller = controller_ref
        # REMOVED: self.deadzone = 200 to prevent property setter conflicts

    def handle_input(self, dx, dy, sniper_active, current_time):
        raise NotImplementedError
        
    def handle_click(self):
        raise NotImplementedError
        
    def trigger_action_beep(self, action_type):
        """Helper tool to execute real-time audio feedback telemetry signals."""
        config = self.controller.config["audio"]
        if config["master_mute"]:
            return
            
        if action_type == "media" and config["media_actions"]:
            self.controller.send_beep_command(1)
        elif action_type == "arrow" and config["arrow_actions"]:
            self.controller.send_beep_command(1)
class MouseMode(BaseMode):
    def __init__(self, controller_ref):
        super().__init__("mouse", controller_ref)
        self.stick_held_start_time = 0
        self.is_stick_active = False

    @property
    def deadzone(self):
        return self.controller.config["mouse"]["deadzone"]

    def handle_input(self, dx, dy, sniper_active, current_time):
        cfg = self.controller.config["mouse"]
        currently_active = abs(dx) > self.deadzone or abs(dy) > self.deadzone
        
        if currently_active and not sniper_active:
            if not self.is_stick_active:
                self.stick_held_start_time = current_time
                self.is_stick_active = True
            
            duration_held = current_time - self.stick_held_start_time
            speed_factor = 1.0 + (cfg["max_speed_mult"] - 1.0) * min(duration_held / cfg["ramp_time"], 1.0)
            current_modifier = cfg["base_speed"] * speed_factor
        elif sniper_active:
            self.is_stick_active = False
            current_modifier = cfg["base_speed"] * cfg["sniper_mult"]
        else:
            self.is_stick_active = False
            current_modifier = cfg["base_speed"]

        move_x = dy * current_modifier if abs(dy) > self.deadzone else 0
        move_y = dx * current_modifier if abs(dx) > self.deadzone else 0

        if move_x != 0 or move_y != 0:
            pyautogui.moveRel(move_x, move_y)

    def handle_click(self):
        pyautogui.click()

class ScrollMode(BaseMode):
    def __init__(self, controller_ref):
        super().__init__("scroll", controller_ref)
        self.last_action_time = 0

    @property
    def deadzone(self):
        return self.controller.config["scroll"]["deadzone"]

    def handle_input(self, dx, dy, sniper_active, current_time):
        cfg = self.controller.config["scroll"]
        if abs(dx) > self.deadzone:
            scroll_amount = cfg["scroll_amount"] if dx < 0 else -cfg["scroll_amount"]
            pyautogui.scroll(scroll_amount)

        if current_time - self.last_action_time > cfg["cooldown"]:
            if dy > self.deadzone:
                pyautogui.hotkey('ctrl', 'tab')          
                self.last_action_time = current_time
            elif dy < -self.deadzone:
                pyautogui.hotkey('ctrl', 'shift', 'tab')   
                self.last_action_time = current_time

    def handle_click(self):
        pyautogui.click(button='middle')

class MediaMode(BaseMode):
    def __init__(self, controller_ref):
        super().__init__("media", controller_ref)
        self.last_action_time = 0

    @property
    def deadzone(self):
        return self.controller.config["media"]["deadzone"]

    def handle_input(self, dx, dy, sniper_active, current_time):
        cfg = self.controller.config["media"]
        if current_time - self.last_action_time > cfg["cooldown"]:
            triggered = False
            if dx > self.deadzone:
                pyautogui.press('volumedown')
                triggered = True
            elif dx < -self.deadzone:
                pyautogui.press('volumeup')
                triggered = True
            
            if dy > self.deadzone:
                pyautogui.press('nexttrack')
                triggered = True
            elif dy < -self.deadzone:
                pyautogui.press('prevtrack')
                triggered = True
                
            if triggered:
                self.last_action_time = current_time
                self.trigger_action_beep("media")

    def handle_click(self):
        pyautogui.press('playpause')
        self.trigger_action_beep("media")

class ArrowKeysMode(BaseMode):
    def __init__(self, controller_ref):
        super().__init__("arrow", controller_ref)
        self.last_action_time = 0

    @property
    def deadzone(self):
        return self.controller.config["arrow"]["deadzone"]

    def handle_input(self, dx, dy, sniper_active, current_time):
        cfg = self.controller.config["arrow"]
        if current_time - self.last_action_time > cfg["cooldown"]:
            triggered = False
            if dy > self.deadzone:
                pyautogui.press('right')
                triggered = True
            elif dy < -self.deadzone:
                pyautogui.press('left')
                triggered = True
            
            if dx > self.deadzone:
                pyautogui.press('down')
                triggered = True
            elif dx < -self.deadzone:
                pyautogui.press('up')
                triggered = True
                
            if triggered:
                self.last_action_time = current_time
                self.trigger_action_beep("arrow")

    def handle_click(self):
        pyautogui.press('enter')
        self.trigger_action_beep("arrow")