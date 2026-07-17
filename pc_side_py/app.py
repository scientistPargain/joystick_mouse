# MUST BE AT THE ABSOLUTE TOP to patch libraries before imports
from gevent import monkey
monkey.patch_all()

import os
import json
import serial
from flask import Flask, render_template
from flask_socketio import SocketIO
import gevent
from controller import JoystickController

# Serial Port Settings
SERIAL_PORT = 'COM5'
BAUD_RATE = 115200

app = Flask(__name__)
app.config['SECRET_KEY'] = 'joystick_secret_xyz!'
socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins="*")

esp32_serial = None
joystick_controller = None

def load_config_data():
    if os.path.exists("config.json"):
        with open("config.json", "r") as f:
            return json.load(f)
    return {}

def background_joystick_loop():
    global joystick_controller
    print(f"[ENGINE] Web server successfully bound to joystick telemetry on port: {SERIAL_PORT}")
    
    while True:
        if joystick_controller:
            try:
                joystick_controller.update()
                telemetry = joystick_controller.latest_telemetry
                socketio.emit('telemetry_data', {
                    'raw_x': telemetry['raw_x'],
                    'raw_y': telemetry['raw_y'],
                    'button': telemetry['button'],
                    'dx': telemetry['dx'],
                    'dy': telemetry['dy'],
                    'current_mode': joystick_controller.mode_names[joystick_controller.current_mode_idx]
                })
            except Exception:
                pass
        gevent.sleep(0.001)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    global joystick_controller
    print("[DASHBOARD] Web Client Connected/Refreshed. Reverting memory to disk baseline...")
    
    if joystick_controller:
        # Re-read config.json from disk to wipe out any unsaved trial variations
        joystick_controller.load_config() 
        
    socketio.emit('sync_config', load_config_data())

@socketio.on('update_setting')
def handle_setting_update(data):
    """Updates runtime memory parameters instantly for trial testing, without writing to disk."""
    global joystick_controller
    if not joystick_controller:
        return
        
    section = data.get('section')
    key = data.get('key')
    value = data.get('value')
    
    try:
        if isinstance(joystick_controller.config[section][key], bool):
            value = bool(value)
        elif isinstance(joystick_controller.config[section][key], int):
            value = int(value)
        elif isinstance(joystick_controller.config[section][key], float):
            value = float(value)
            
        # Modify active memory framework only
        joystick_controller.config[section][key] = value
        
        # Broadcast configuration updates out to other open browser contexts
        socketio.emit('sync_config', joystick_controller.config)
    except Exception as e:
        print(f"[ERROR] Failed applying runtime setting update: {e}")

@socketio.on('save_configuration')
def handle_save_configuration():
    """Explicitly commits the current memory state structure directly to config.json."""
    global joystick_controller
    if joystick_controller:
        try:
            joystick_controller.save_config()
            print("[DATABASE] Successfully committed memory matrix parameters directly to config.json")
            socketio.emit('save_confirmed', {'status': 'success'})
        except Exception as e:
            print(f"[CRITICAL] Disk write failure: {e}")

@socketio.on('trigger_recenter')
def handle_recenter():
    global joystick_controller
    if joystick_controller:
        joystick_controller.update_offsets()

@socketio.on('trigger_test_beep')
def handle_test_beep(data):
    global joystick_controller
    if joystick_controller:
        count = int(data.get('count', 1))
        payload = f"BEEP:{count}\n"
        try:
            joystick_controller.esp32.write(payload.encode('utf-8'))
        except Exception:
            pass

if __name__ == '__main__':
    try:
        esp32_serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.001)
    except Exception as e:
        print(f"[CRITICAL] Serial interface initialization error: {e}")
        os._exit(1)

    joystick_controller = JoystickController(esp32_serial)
    gevent.spawn(background_joystick_loop)
    socketio.run(app, host='127.0.0.1', port=5000, debug=False)