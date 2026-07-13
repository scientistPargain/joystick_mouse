import serial
import pyautogui
import time

# PyAutoGUI safety feature (move mouse to corner to halt script if needed)
pyautogui.FAILSAFE = False 

# !!! Make sure this matches your ESP32's assigned COM port !!!
SERIAL_PORT = 'COM5' 
BAUD_RATE = 115200

try:
    # Set a tiny timeout so the read loop never locks up
    esp32 = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.001)
    print(f"Successfully connected to ESP32 on {SERIAL_PORT}")
except Exception as e:
    print(f"Error opening serial port: {e}")
    exit()

# Calibration thresholds for 12-bit raw values
CENTER_X = 2048
CENTER_Y = 2048
DEADZONE = 180 
MOUSE_SPEED_MODIFIER = 0.015 

last_click_time = 0
DEBOUNCE_DELAY = 0.2  # 200ms cooldown window for clicks

while True:
    try:
        if esp32.in_waiting > 0:
            # Read the incoming string line
            line = esp32.readline().decode('utf-8', errors='ignore').strip()
            
            # CRITICAL: Drop accumulated backlog packets so movements stay real-time
            esp32.reset_input_buffer()
            
            data = line.split(',')
            if len(data) == 3:
                raw_x = int(data[0])
                raw_y = int(data[1])
                button = int(data[2])
                
                # Calculate deviations from physical rest center
                dx = raw_x - CENTER_X
                dy = raw_y - CENTER_Y
                
                move_x = 0
                move_y = 0
                
                # --- CORRECTED AXES & DIRECTION INVERSIONS ---
                if abs(dy) > DEADZONE:
                    move_x = dy * MOUSE_SPEED_MODIFIER
                if abs(dx) > DEADZONE:
                    move_y = dx * MOUSE_SPEED_MODIFIER 
                
                # Command cursor translation instantly
                if move_x != 0 or move_y != 0:
                    pyautogui.moveRel(move_x, move_y)
                
                # --- NON-BLOCKING BUTTON HOOK ---
                current_time = time.time()
                if button == 0 and (current_time - last_click_time > DEBOUNCE_DELAY):
                    pyautogui.click()
                    last_click_time = current_time
                    
    except KeyboardInterrupt:
        print("\nShutting down controller connection cleanly...")
        esp32.close()
        break
    except Exception:
        # Silently bypass erratic fragmented frames
        continue