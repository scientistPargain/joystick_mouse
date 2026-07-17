#include <Arduino.h>

const int X_PIN = 34;
const int Y_PIN = 35;
const int SW_PIN = 32;
const int BUZZER_PIN = 25; // Connect active buzzer pin here

void setup() {
  Serial.begin(115200);
  pinMode(SW_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW); // Start with buzzer silent
  
  analogSetAttenuation(ADC_11db); 
}

void loop() {
  // --- READ SENSORS ---
  int rawX = analogRead(X_PIN);
  int rawY = analogRead(Y_PIN);
  int swValue = digitalRead(SW_PIN); // 0 = Pressed, 1 = Released

  // Send data to PC
  Serial.print(rawX);
  Serial.print(",");
  Serial.print(rawY);
  Serial.print(",");
  Serial.println(swValue);

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