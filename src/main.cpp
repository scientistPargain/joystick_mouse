#include <Arduino.h>

const int X_PIN = 34;
const int Y_PIN = 35;
const int SW_PIN = 32;

void setup() {
  // Start serial communication at 115200 baud
  Serial.begin(115200);
  pinMode(SW_PIN, INPUT_PULLUP);
}

void loop() {
  int rawX = analogRead(X_PIN);
  int rawY = analogRead(Y_PIN);
  int swValue = digitalRead(SW_PIN); // 0 = Pressed, 1 = Released

  // Send data over serial in a clean format: "X_val,Y_val,Button_val"
  Serial.print(rawX);
  Serial.print(",");
  Serial.print(rawY);
  Serial.print(",");
  Serial.println(swValue);

  // 15ms delay gives a smooth ~60Hz update rate, perfect for mouse tracking
  delay(8); 
}