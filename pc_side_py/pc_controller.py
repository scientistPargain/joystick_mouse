import serial
import pyautogui
import time

# PyAutoGUI safety feature (move mouse to corner to halt script if needed)
pyautogui.FAILSAFE = True 

# !!! Make sure this matches your ESP32's assigned COM port !!!
SERIAL_PORT = 'COM5' 
BAUD_RATE = 115200

try:
    esp32 = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.001)
    print(f"Successfully connected to ESP32 on {SERIAL_PORT}")
except Exception as e:
    print(f"Error opening serial port: {e}")
    exit()

# Calibration thresholds for 12-bit raw values
CENTER_X = 2048
CENTER_Y = 2048
DEADZONE = 180 

# --- ACCELERATION CONFIGURATION ---
BASE_SPEED = 0.015       # Starting speed when you first push the stick
MAX_SPEED_MULT = 4.0      # Maximum speed multiplier (e.g., up to 4x faster)
RAMP_TIME = 0.8           # Time in seconds of holding the stick to reach MAX_SPEED_MULT

# State tracking variables
stick_held_start_time = 0
is_stick_active = False
last_click_time = 0
DEBOUNCE_DELAY = 0.2

while True:
    try:
        if esp32.in_waiting > 0:
            line = esp32.readline().decode('utf-8', errors='ignore').strip()
            esp32.reset_input_buffer()
            
            data = line.split(',')
            if len(data) == 3:
                raw_x = int(data[0])
                raw_y = int(data[1])
                button = int(data[2])
                
                # Calculate deviations from center
                dx = raw_x - CENTER_X
                dy = raw_y - CENTER_Y
                
                # Check if the stick is physically being pushed past the deadzone
                currently_active = abs(dx) > DEADZONE or abs(dy) > DEADZONE
                current_time = time.time()
                
                # --- VELOCITY RAMPING LOGIC ---
                if currently_active:
                    if not is_stick_active:
                        # Stick just entered the active zone; start the timer
                        stick_held_start_time = current_time
                        is_stick_active = True
                    
                    # Calculate how long the stick has been held down continuously
                    duration_held = current_time - stick_held_start_time
                    
                    # Calculate the speed factor linearly ramping up over time
                    # min() caps it so it doesn't accelerate infinitely past MAX_SPEED_MULT
                    speed_factor = 1.0 + (MAX_SPEED_MULT - 1.0) * min(duration_held / RAMP_TIME, 1.0)
                else:
                    # Stick returned to center; reset the acceleration multiplier immediately
                    is_stick_active = False
                    speed_factor = 1.0
                
                # Combine base modifier with dynamic ramping speed factor
                current_modifier = BASE_SPEED * speed_factor
                
                move_x = 0
                move_y = 0
                
                # Calculate final relative mouse movement values
                if abs(dy) > DEADZONE:
                    move_x = dy * current_modifier
                if abs(dx) > DEADZONE:
                    move_y = dx * current_modifier 
                
                # Move the cursor
                if move_x != 0 or move_y != 0:
                    pyautogui.moveRel(move_x, move_y)
                
                # --- BUTTON HOOK ---
                if button == 0 and (current_time - last_click_time > DEBOUNCE_DELAY):
                    pyautogui.click()
                    last_click_time = current_time
                    
    except KeyboardInterrupt:
        print("\nShutting down controller connection cleanly...")
        esp32.close()
        break
    except Exception:
        continue