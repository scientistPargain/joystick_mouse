#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEHIDDevice.h>
#include <BLEServer.h>
#include <BLE2902.h>
#include <HIDTypes.h>

const int X_PIN = 34;
const int Y_PIN = 35;
const int SW_PIN = 32;
const int BUZZER_PIN = 25; // Connect active buzzer pin here
const int BATTERY_PIN = 36; // Voltage divider on Li-ion pack (GPIO36, ADC1)

// --- ADC choices (bluetooth active, so no ADC2 reads) ---
const int ADC_MAX = 4095;

// --- HID report id ---
const uint8_t REPORT_ID_MOUSE = 1;

class ServerCallbacks : public BLEServerCallbacks {
public:
  void onConnect(BLEServer* server) override { connected = true; }
  void onDisconnect(BLEServer* server) override {
    connected = false;
    server->getAdvertising()->start();
  }
  bool connected = false;
};

static ServerCallbacks serverCallbacks;

const uint8_t reportMap[] = {
    0x05, 0x01,   // USAGE_PAGE (Generic Desktop)
    0x09, 0x02,   // USAGE (Mouse)
    0xA1, 0x01,   // COLLECTION (Application)
    0x85, REPORT_ID_MOUSE,  // REPORT_ID (1)
    0x09, 0x01,   //   USAGE (Pointer)
    0xA1, 0x00,   //   COLLECTION (Physical)
    0x05, 0x09,   //     USAGE_PAGE (Button)
    0x19, 0x01,   //     USAGE_MINIMUM (Button 1)
    0x29, 0x03,   //     USAGE_MAXIMUM (Button 3)
    0x15, 0x00,   //     LOGICAL_MINIMUM (0)
    0x25, 0x01,   //     LOGICAL_MAXIMUM (1)
    0x95, 0x03,   //     REPORT_COUNT (3)
    0x75, 0x01,   //     REPORT_SIZE (1)
    0x81, 0x02,   //     INPUT (Data, Variable, Absolute)
    0x95, 0x01,   //     REPORT_COUNT (1)
    0x75, 0x05,   //     REPORT_SIZE (5)
    0x81, 0x03,   //     INPUT (Constant, Variable, Absolute) - padding
    0x05, 0x01,   //     USAGE_PAGE (Generic Desktop)
    0x09, 0x30,   //     USAGE (X)
    0x09, 0x31,   //     USAGE (Y)
    0x09, 0x38,   //     USAGE (Wheel)
    0x15, 0x81,   //     LOGICAL_MINIMUM (-127)
    0x25, 0x7F,   //     LOGICAL_MAXIMUM (127)
    0x75, 0x08,   //     REPORT_SIZE (8)
    0x95, 0x03,   //     REPORT_COUNT (3)
    0x81, 0x06,   //     INPUT (Data, Variable, Relative)
    0xC0,         //   END_COLLECTION
    0xC0          // END_COLLECTION
};

BLEHIDDevice *hid = nullptr;
BLECharacteristic *mouseInput = nullptr;

const int CENTER = 2048;
const int DEADZONE = 155;     // raw ADC; matches Python config mouse.deadzone
const int SPEED = 16;         // raw units per pixel of pointer travel
const int WHEEL_THRESHOLD = 500;

uint8_t axes(int raw, int center) {
  int push = raw - center;
  int limited = constrain(push / SPEED, -127, 127);
  return (uint8_t)limited;
}

void setup() {
  Serial.begin(115200);
  pinMode(SW_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW); // Start with buzzer silent

  pinMode(BATTERY_PIN, INPUT);

  analogSetAttenuation(ADC_11db);

  // --- BLE HID mouse ---
  BLEDevice::init("JoystickMouse");
  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(&serverCallbacks);

  hid = new BLEHIDDevice(server);
  hid->reportMap((uint8_t*)reportMap, sizeof(reportMap));
  hid->pnp(0x02, 0x046D, 0xC03E, 0x0100);  // Vendor 0x046D = Logitech (generic USB mice), PID, version
  hid->hidInfo(0x00, 0x02);               // country: 0, flags: 0x02 (Normally Connectable)
  hid->manufacturer("Espressif");
  mouseInput = hid->inputReport(REPORT_ID_MOUSE);
  hid->startServices();
  hid->setBatteryLevel(100);

  BLEAdvertising *advertising = server->getAdvertising();
  advertising->addServiceUUID(hid->hidService()->getUUID());
  advertising->setScanResponse(true);
  advertising->setMinPreferred(0x06);
  advertising->start();
}

void loop() {
  // --- READ SENSORS ---
  int rawX = analogRead(X_PIN);
  int rawY = analogRead(Y_PIN);
  int swValue = digitalRead(SW_PIN); // 0 = Pressed, 1 = Released

  // Send data to PC over USB, unchanged
  Serial.print(rawX);
  Serial.print(",");
  Serial.print(rawY);
  Serial.print(",");
  Serial.println(swValue);

  // --- BLE HID report ---
  static int lastButton = -1;
  int button = (swValue == LOW) ? 0x01 : 0x00; // left button

  // axes are swapped: pot's Y = pointer's X, pot's X = pointer's Y
  int dxRaw = (abs(rawY - CENTER) > DEADZONE) ? (rawY - CENTER) : 0;
  int dyRaw = (abs(rawX - CENTER) > DEADZONE) ? (rawX - CENTER) : 0;
  int8_t dx = (int8_t)constrain(dxRaw / SPEED, -127, 127);
  int8_t dy = (int8_t)constrain(dyRaw / SPEED, -127, 127);

  int8_t wheel = 0;
  if (abs(dxRaw) > WHEEL_THRESHOLD) wheel = (dxRaw > 0) ? 1 : -1;

  uint8_t report[4] = { (uint8_t)(button & 0x03), (uint8_t)dx, (uint8_t)dy, (uint8_t)wheel };
  if (serverCallbacks.connected) {
    mouseInput->setValue(report, sizeof(report));
    mouseInput->notify();
  }

  // --- LISTEN FOR PC COMMANDS (BUZZER AUDIO) ---
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();

    if (command.startsWith("BEEP:")) {
      int count = command.substring(5).toInt();
      for (int i = 0; i < count; i++) {
        digitalWrite(BUZZER_PIN, HIGH);
        delay(80); // Short, crisp beep
        digitalWrite(BUZZER_PIN, LOW);
        if (i < count - 1) delay(80); // Gap between multi-beeps
      }
    }
  }

  delay(8);
}
