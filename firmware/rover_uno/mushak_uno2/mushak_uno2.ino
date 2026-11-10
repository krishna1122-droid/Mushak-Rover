/*
  Mushak Rover - Arduino Uno firmware
  Controls: 2x BTS7960 (left/right 775 motors) + 6-servo arm.
  Commands arrive from the ESP8266 (SoftwareSerial) or from the USB Serial Monitor.

  Protocol (ASCII, one command per line, ends with newline):
    D,<left>,<right>   drive, each value -255..255 (negative = reverse)
    A,<ch>,<angle>     arm servo channel 0..5 to angle 0..180
    S                  stop motors
    H                  heartbeat (does nothing, keeps failsafe alive)

  Failsafe: if no command arrives for 500 ms, the motors stop.

  Wiring notes:
    - Tie R_EN and L_EN of each BTS7960 to 5V (always enabled).
    - Motor PWM pins 3, 5, 6, 11 (Servo library disables PWM on 9 and 10).
    - Uno TX (pin 13) -> level shifter -> ESP8266 RX.
    - ESP8266 TX -> Uno RX (pin 12) directly.
    - Servos powered from their own 6V supply, common ground with everything.
*/

#include <Servo.h>
#include <SoftwareSerial.h>

// ---------- Pins ----------
const uint8_t L_RPWM = 5,  L_LPWM = 6;    // left BTS7960
const uint8_t R_RPWM = 3,  R_LPWM = 11;   // right BTS7960
const uint8_t SERVO_PINS[6] = {2, 4, 7, 8, 9, 10};
const uint8_t LINK_RX = 12, LINK_TX = 13; // to/from ESP8266

// ---------- Settings ----------
const unsigned long FAILSAFE_MS = 500;
const unsigned long ARM_STEP_MS = 15;     // 1 degree per step -> smooth arm motion
const bool DEBUG = true;                  // true = echo every received command to USB Serial

SoftwareSerial link(LINK_RX, LINK_TX);
Servo arm[6];
int current[6] = {90, 90, 90, 90, 90, 90};
int target[6]  = {90, 90, 90, 90, 90, 90};
bool attached[6] = {false, false, false, false, false, false};

// Safe angle limits per servo. Start wide; tighten them after the servo_test.ino session.
int MIN_ANGLE[6] = {0, 0, 0, 0, 0, 0};
int MAX_ANGLE[6] = {180, 180, 180, 180, 180, 180};
unsigned long lastCmd = 0, lastStep = 0;

// ---------- Line reader (one per input so they never mix) ----------
struct LineReader {
  char buf[32];
  uint8_t len = 0;
  void poll(Stream &s, void (*onLine)(char *)) {
    while (s.available()) {
      char c = s.read();
      if (c == '\n' || c == '\r') {
        if (len > 0) {
          buf[len] = 0;
          onLine(buf);
          len = 0;
        }
      } else if (len < sizeof(buf) - 1) {
        buf[len++] = c;
      } else {
        len = 0;  // too long, discard
      }
    }
  }
};
LineReader usbReader, linkReader;

// ---------- Motors ----------
void setMotor(uint8_t rpwm, uint8_t lpwm, int speed) {
  speed = constrain(speed, -255, 255);
  if (speed >= 0) {
    analogWrite(rpwm, speed);
    analogWrite(lpwm, 0);
  } else {
    analogWrite(rpwm, 0);
    analogWrite(lpwm, -speed);
  }
}

void drive(int left, int right) {
  setMotor(L_RPWM, L_LPWM, left);
  setMotor(R_RPWM, R_LPWM, right);
}

// ---------- Command handling ----------
void handle(char *line) {
  lastCmd = millis();
  if (DEBUG) {
    Serial.print(F("RX: "));
    Serial.println(line);
  }
  switch (line[0]) {
    case 'D': {
      int l, r;
      if (sscanf(line + 1, ",%d,%d", &l, &r) == 2) drive(l, r);
      break;
    }
    case 'A': {
      int ch, ang;
      if (sscanf(line + 1, ",%d,%d", &ch, &ang) == 2 && ch >= 0 && ch < 6) {
        int a = constrain(ang, MIN_ANGLE[ch], MAX_ANGLE[ch]);
        if (!attached[ch]) {
          // First command for this servo: attach it now, so nothing moves at power-up
          // and only the servo you touch moves.
          current[ch] = a;
          arm[ch].attach(SERVO_PINS[ch]);
          arm[ch].write(a);
          attached[ch] = true;
        }
        target[ch] = a;
      }
      break;
    }
    case 'S':
      drive(0, 0);
      break;
    case 'H':
      break;
  }
}

// ---------- Arduino ----------
void setup() {
  Serial.begin(115200);
  link.begin(9600);

  uint8_t motorPins[4] = {L_RPWM, L_LPWM, R_RPWM, R_LPWM};
  for (uint8_t i = 0; i < 4; i++) pinMode(motorPins[i], OUTPUT);
  drive(0, 0);
  // Servos are attached later, one at a time, when each gets its first A command.
  lastCmd = millis();
}

void loop() {
  usbReader.poll(Serial, handle);
  linkReader.poll(link, handle);

  // Failsafe: stop if the controller went quiet
  if (millis() - lastCmd > FAILSAFE_MS) drive(0, 0);

  // Move arm servos gradually toward their targets
  if (millis() - lastStep >= ARM_STEP_MS) {
    lastStep = millis();
    for (uint8_t i = 0; i < 6; i++) {
      if (attached[i] && current[i] != target[i]) {
        current[i] += (target[i] > current[i]) ? 1 : -1;
        arm[i].write(current[i]);
      }
    }
  }
}
