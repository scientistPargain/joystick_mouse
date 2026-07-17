# MUST BE AT THE ABSOLUTE TOP to patch libraries before imports
from gevent import monkey
monkey.patch_all()

import os
import json
import serial
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
import gevent
from controller import JoystickController

# Serial Port Settings
SERIAL_PORT = 'COM5'
BAUD_RATE = 115200

app = Flask(__name__)
app.config['SECRET_KEY'] = 'joystick_secret_xyz!'
socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins="*")

# Shared global controller references
esp32_serial = None
joystick_controller = None

def load_config_data():
    if os.path.exists("config.json"):
        with open("config.json", "r") as f:
            return json.load(f)
    return {}

def background_joystick_loop():
    """Cooperative gevent greenlet execution loop to keep telemetry streaming fluidly."""
    global joystick_controller
    print(f"[ENGINE] Web server successfully bound to joystick telemetry on port: {SERIAL_PORT}")
    
    while True:
        if joystick_controller:
            try:
                joystick_controller.update()
                
                # Emit live real-time position matrix packages straight to the browser UI
                telemetry = joystick_controller.latest_telemetry
                socketio.emit('telemetry_data', {
                    'raw_x': telemetry['raw_x'],
                    'raw_y': telemetry['raw_y'],
                    'button': telemetry['button'],
                    'dx': telemetry['dx'],
                    'dy': telemetry['dy'],
                    'current_mode': joystick_controller.mode_names[joystick_controller.current_mode_idx]
                })
            except Exception as e:
                pass
        # Voluntarily yield execution time to allow the web framework server to process socket routes
        gevent.sleep(0.001)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    print("[DASHBOARD] Web Client Connected. Synchronizing configuration matrix parameters...")
    # Send the current config parameters over to the page so inputs align with saved JSON numbers
    socketio.emit('sync_config', load_config_data())

@socketio.on('update_setting')
def handle_setting_update(data):
    """Listens to real-time UI value shifts, commits to matrix runtime, and updates JSON database."""
    global joystick_controller
    if not joystick_controller:
        return
        
    section = data.get('section')
    key = data.get('key')
    value = data.get('value')
    
    try:
        # Cast values properly depending on data-type profile signature
        if isinstance(joystick_controller.config[section][key], bool):
            value = bool(value)
        elif isinstance(joystick_controller.config[section][key], int):
            value = int(value)
        elif isinstance(joystick_controller.config[section][key], float):
            value = float(value)
            
        joystick_controller.config[section][key] = value
        joystick_controller.save_config()
        
        # Broadcast configuration updates out to any other open browser tabs
        socketio.emit('sync_config', joystick_controller.config)
    except Exception as e:
        print(f"[ERROR] Failed applying setting variation update: {e}")

@socketio.on('trigger_recenter')
def handle_recenter():
    """Manual recalibration offset request hook."""
    global joystick_controller
    if joystick_controller:
        joystick_controller.update_offsets()

@socketio.on('trigger_test_beep')
def handle_test_beep(data):
    """Direct manual buzzer injection circuit execution tester."""
    global joystick_controller
    if joystick_controller:
        count = int(data.get('count', 1))
        # Bypass master mute for hardware testing purposes specifically
        payload = f"BEEP:{count}\n"
        try:
            joystick_controller.esp32.write(payload.encode('utf-8'))
            print(f"[TEST] Dispatched diagnostics pulse array burst: {count} beeps")
        except Exception:
            pass

if __name__ == '__main__':
    try:
        esp32_serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.001)
    except Exception as e:
        print(f"[CRITICAL] Serial interface initialization error: {e}. Check device connection hooks!")
        os._exit(1)

    # Handover runtime configuration blocks
    joystick_controller = JoystickController(esp32_serial)
    
    # Spawn the background telemetry parser loop using native gevent execution greenlets
    gevent.spawn(background_joystick_loop)
    
    # Fire up the lightweight WSGI web runtime application server environment
    socketio.run(app, host='127.0.0.1', port=5000, debug=False)