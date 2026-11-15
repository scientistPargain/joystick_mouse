#include "hid.h"
#include "config.h"

#include <BLEDevice.h>
#include <BLEHIDDevice.h>
#include <BLEServer.h>
#include <BLE2902.h>
#include <BLESecurity.h>
#include <BLEUtils.h>

// Windows only consumes the HID input report after an encrypted bond, and the
// report characteristic itself is flagged encrypted. Accept "Just Works" bonding.
class SecurityCallbacks : public BLESecurityCallbacks {
public:
  bool onSecurityRequest() override { return true; }
  bool onConfirmPIN(uint32_t pin) override { return true; }
  uint32_t onPassKeyRequest() override { return 0; }
  void onPassKeyNotify(uint32_t pass_key) override { (void)pass_key; }
  void onAuthenticationComplete(esp_ble_auth_cmpl_t cmpl) override { (void)cmpl; }
};

static SecurityCallbacks securityCallbacks;

static const uint8_t reportMap[] = {
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
static BLEHIDDevice* hid = nullptr;
static BLECharacteristic* mouseInput = nullptr;

bool hid_is_connected() {
  return serverCallbacks.connected;
}

void hid_init(const char* deviceName) {
  BLEDevice::init(deviceName);
  BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT);
  BLEDevice::setSecurityCallbacks(&securityCallbacks);

  BLESecurity *security = new BLESecurity();
  security->setAuthenticationMode(ESP_LE_AUTH_REQ_SC_BOND);
  security->setKeySize(16);

  BLEServer* server = BLEDevice::createServer();
  server->setCallbacks(&serverCallbacks);

  hid = new BLEHIDDevice(server);
  hid->reportMap((uint8_t*)reportMap, sizeof(reportMap));
  hid->pnp(0x02, 0x046D, 0xC03E, 0x0100);
  hid->hidInfo(0x00, 0x02);               // country 0, flags: Normally Connectable

  // The bundled library's inputReport() creates the HID input report with
  // ESP_GATT_PERM_READ_ENCRYPTED | ESP_GATT_PERM_WRITE_ENCRYPTED. This board's
  // precompiled SDK does not persist bond keys in NVS, so on every reboot the
  // encrypted characteristic becomes unreadable and Windows pairs the mouse but
  // refuses to subscribe to the report -> no cursor. Create the same
  // characteristic ourselves with plain READ|NOTIFY (same UUID, same descriptors).
  BLEService* hidService = hid->hidService();
  mouseInput = hidService->createCharacteristic(
      (uint16_t)0x2a4d,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  // Same treatment the battery level gets: enable the CCCD by default, or
  // Windows "connects" but never receives HID reports after a device reboot.
  BLE2902* inputReportCcc = new BLE2902();
  inputReportCcc->setNotifications(true);
  mouseInput->addDescriptor(inputReportCcc);
  BLEDescriptor* reportRef = new BLEDescriptor(BLEUUID((uint16_t)0x2908));
  uint8_t reportRefVal[] = { REPORT_ID_MOUSE, 0x01 };
  reportRef->setValue(reportRefVal, sizeof(reportRefVal));
  mouseInput->addDescriptor(reportRef);                      // report reference descriptor

  hid->startServices();
  hid->setBatteryLevel(100);

  BLEAdvertising* advertising = server->getAdvertising();
  advertising->addServiceUUID(hid->hidService()->getUUID());
  advertising->setAppearance(0x03C2);      // General HID Device / Mouse
  advertising->setScanResponse(true);
  advertising->setMinPreferred(0x06);
  advertising->setMinPreferred(0x12);
  advertising->start();
}

void hid_set_battery_level(uint8_t percent) {
  if (hid) hid->setBatteryLevel(percent);
}

void hid_send_mouse_report(uint8_t buttons, int8_t dx, int8_t dy, int8_t wheel) {
  if (!serverCallbacks.connected) return;
  uint8_t report[4] = { (uint8_t)(buttons & 0x07), (uint8_t)dx, (uint8_t)dy, (uint8_t)wheel };
  mouseInput->setValue(report, sizeof(report));
  mouseInput->notify();
}
