import serial
from controller import JoystickController

# !!! Update with your current connection string !!!
SERIAL_PORT = 'COM10'
BAUD_RATE = 115200

def main():
    try:
        esp32_serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.001)
        print(f"Connected to ESP32 on {SERIAL_PORT}")
    except Exception as e:
        print(f"Failed opening serial communication port: {e}")
        return

    # Initialize modular state machine controller
    controller = JoystickController(esp32_serial)
    print("Multi-Tool Joystick active. Current Profile Context: Mouse Mode")
    print("-> Hold down Joystick button (0.8s) to switch profile modes.")

    while True:
        try:
            controller.update()
        except KeyboardInterrupt:
            print("\nSafely breaking application pipeline loop execution hooks...")
            esp32_serial.close()
            break
        except Exception:
            continue

if __name__ == '__main__':
    main()