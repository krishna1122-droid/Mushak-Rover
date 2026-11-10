/*
  Mushak Arm - wired pot controller, ONE Arduino (Uno / Nano)

  6 pots -> this Arduino -> 6 servos. No Bluetooth, no ESP8266, no second board, no serial link.

  Wiring:
    Pots: outer pins to 5V and GND, wiper (middle pin) to A0..A5 (channel 0..5).
          ch0 base, ch1 shoulder, ch2 elbow, ch3 wrist roll, ch4 wrist, ch5 gripper.
    ENGAGE switch: one side to D12, other side to GND. Closed = servos follow the pots.
    Servo signals: ch0 D2, ch1 D4, ch2 D7, ch3 D8, ch4 D9, ch5 D10.
    Servo power: 6.0 V buck (fused, with a 1000 uF capacitor). Its GND joined to the Arduino GND.
                 Never power the servos from the Arduino 5V pin.
    Arduino: powered from USB.

  Behaviour:
    - Switch open: servos are not driven until the first time you close it.
    - Switch closed for the first time: each servo jumps to its pot's angle. Set the pots
      roughly to match the arm's pose BEFORE closing the switch.
    - Switch opened again: the servos keep holding their last angle (the arm does not drop).
    - Servos move 1 degree every 15 ms toward the pot angle, so motion is smooth and slow.
*/

#include <Servo.h>

const uint8_t POT_PINS[6] = {A0, A1, A2, A3, A4, A5};
const uint8_t SERVO_PINS[6] = {2, 4, 7, 8, 9, 10};
const uint8_t ENGAGE_PIN = 12;

// Safe angle range of each joint, with a 5 degree margin inside the measured ends.
// Measured ends: base 0-90, shoulder 0-180, elbow 0-90, wrist roll 0-180, wrist 0-90, gripper 0-90.
const int MIN_ANGLE[6] = {5, 5, 5, 5, 5, 5};
const int MAX_ANGLE[6] = {85, 175, 85, 175, 85, 85};

// Flip to true for a joint that moves the opposite way from its pot (instead of swapping wires).
const bool REVERSE[6] = {false, false, false, false, false, false};

const uint8_t SAMPLES = 16;           // average readings per pot (less noise)
const int DEADBAND = 3;               // ignore pot changes smaller than this many degrees
const unsigned long STEP_MS = 15;     // 1 degree every 15 ms
const unsigned long READ_MS = 20;     // read the pots 50 times a second

Servo servo[6];
bool attached[6] = {false, false, false, false, false, false};
int current[6] = {90, 90, 90, 90, 90, 90};   // where the servo is now
int target[6] = {90, 90, 90, 90, 90, 90};    // where the pot says it should be
int potAngle[6] = {90, 90, 90, 90, 90, 90};
bool started = false;                        // has ENGAGE been closed at least once
unsigned long lastStep = 0, lastRead = 0;

int readAngle(uint8_t ch) {
  long sum = 0;
  for (uint8_t i = 0; i < SAMPLES; i++) sum += analogRead(POT_PINS[ch]);
  int raw = sum / SAMPLES;
  if (REVERSE[ch]) raw = 1023 - raw;
  return map(raw, 0, 1023, MIN_ANGLE[ch], MAX_ANGLE[ch]);
}

void setup() {
  Serial.begin(115200);               // optional USB debug
  pinMode(ENGAGE_PIN, INPUT_PULLUP);
  for (uint8_t ch = 0; ch < 6; ch++) potAngle[ch] = readAngle(ch);
  Serial.println(F("Arm pot controller ready. Close ENGAGE to start."));
}

void loop() {
  bool engaged = (digitalRead(ENGAGE_PIN) == LOW);

  // Read pots, ignoring tiny wiggles
  if (millis() - lastRead >= READ_MS) {
    lastRead = millis();
    for (uint8_t ch = 0; ch < 6; ch++) {
      int a = readAngle(ch);
      if (abs(a - potAngle[ch]) >= DEADBAND) potAngle[ch] = a;
    }
  }

  if (engaged) {
    if (!started) {
      // First time ENGAGE is closed: attach every servo at its pot's angle
      started = true;
      for (uint8_t ch = 0; ch < 6; ch++) {
        current[ch] = potAngle[ch];
        target[ch] = potAngle[ch];
        servo[ch].attach(SERVO_PINS[ch]);
        servo[ch].write(current[ch]);
        attached[ch] = true;
      }
      Serial.println(F("Engaged"));
    }
    for (uint8_t ch = 0; ch < 6; ch++) target[ch] = potAngle[ch];
  }
  // When the switch is open the targets are left alone, so the arm holds its last pose.

  // Move every attached servo 1 degree toward its target at a fixed pace
  if (millis() - lastStep >= STEP_MS) {
    lastStep = millis();
    for (uint8_t ch = 0; ch < 6; ch++) {
      if (attached[ch] && current[ch] != target[ch]) {
        current[ch] += (target[ch] > current[ch]) ? 1 : -1;
        servo[ch].write(current[ch]);
      }
    }
  }
}
