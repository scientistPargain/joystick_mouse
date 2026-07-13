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

# --- ACCELERATION & SNIPER CONFIGURATION ---
BASE_SPEED = 0.015       
MAX_SPEED_MULT = 4.0      
RAMP_TIME = 0.8           
SNIPER_SPEED_MULT = 0.2   # Reduces speed to 20% when button is held down

# State tracking variables
stick_held_start_time = 0
is_stick_active = False

# Button tracking variables
button_pressed_time = 0
is_button_down = False
TAP_THRESHOLD = 0.25      # If released under 250ms, it's a normal click

while True:
    try:
        if esp32.in_waiting > 0:
            line = esp32.readline().decode('utf-8', errors='ignore').strip()
            esp32.reset_input_buffer()
            
            data = line.split(',')
            if len(data) == 3:
                raw_x = int(data[0])
                raw_y = int(data[1])
                button = int(data[2])  # 0 = Pressed, 1 = Released
                
                current_time = time.time()
                
                # --- SNIPER / CLICK BUTTON LOGIC ---
                sniper_active = False
                
                if button == 0:  # Button is physically held DOWN
                    if not is_button_down:
                        button_pressed_time = current_time
                        is_button_down = True
                    
                    # If held longer than the tap threshold, activate sniper mode
                    if (current_time - button_pressed_time) > TAP_THRESHOLD:
                        sniper_active = True
                
                elif button == 1 and is_button_down:  # Button was just RELEASED
                    # If it was a short press, register a standard mouse click
                    if (current_time - button_pressed_time) <= TAP_THRESHOLD:
                        pyautogui.click()
                    is_button_down = False
                
                # --- COORDINATE CALCULATION ---
                # Fixed: Calculating dx and dy safely before evaluating activity status
                dx = raw_x - CENTER_X
                dy = raw_y - CENTER_Y
                
                # Check if the stick is physically being pushed past the deadzone
                currently_active = abs(dx) > DEADZONE or abs(dy) > DEADZONE
                
                # --- VELOCITY RAMPING LOGIC ---
                if currently_active and not sniper_active:
                    if not is_stick_active:
                        stick_held_start_time = current_time
                        is_stick_active = True
                    
                    duration_held = current_time - stick_held_start_time
                    speed_factor = 1.0 + (MAX_SPEED_MULT - 1.0) * min(duration_held / RAMP_TIME, 1.0)
                    current_modifier = BASE_SPEED * speed_factor
                
                elif sniper_active:
                    # Sniper mode overrides acceleration entirely and dampens movement
                    is_stick_active = False
                    current_modifier = BASE_SPEED * SNIPER_SPEED_MULT
                
                else:
                    is_stick_active = False
                    current_modifier = BASE_SPEED
                
                # --- CALCULATE MOVEMENT ---
                move_x = 0
                move_y = 0
                
                if abs(dy) > DEADZONE:
                    move_x = dy * current_modifier
                if abs(dx) > DEADZONE:
                    move_y = dx * current_modifier 
                
                if move_x != 0 or move_y != 0:
                    pyautogui.moveRel(move_x, move_y)
                    
    except KeyboardInterrupt:
        print("\nShutting down controller connection cleanly...")
        esp32.close()
        break
    except Exception:
        continue