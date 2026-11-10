# Wiring reference

Tables below reflect the supplied source comments and pin definitions only. Confirm board pin labels and electrical compatibility for the exact hardware before powering it.

## Rover Uno sketch

| Uno pin | Connection | Source detail |
|---|---|---|
| D5 | Left BTS7960 RPWM | PWM |
| D6 | Left BTS7960 LPWM | PWM |
| D3 | Right BTS7960 RPWM | PWM |
| D11 | Right BTS7960 LPWM | PWM |
| D2, D4, D7, D8, D9, D10 | Servo channels 0–5 | Signal pins, in order |
| D12 | SoftwareSerial RX | ESP8266 TX (GPIO12) per sketch comments |
| D13 | SoftwareSerial TX | ESP8266 RX (GPIO14) through a level shifter; comment marks this optional |

Sketch comments say tie each BTS7960 R_EN and L_EN to 5 V. Motor power wiring, battery specification, and driver current ratings are TODO. Servo supply is separate; the pot-controller comments specify a 6 V buck, fuse, 1000 µF capacitor, and common ground. Do not power servos from Uno 5 V.

## ESP8266 bridge

| ESP8266 GPIO | Connection |
|---|---|
| GPIO14 (D5) | SoftwareSerial RX; Uno D13 TX through level shifting if used |
| GPIO12 (D6) | SoftwareSerial TX to Uno D12 RX |
| GND | Common ground with Uno |

The sketches use 9600 baud for the bridge serial connection. ESP8266 logic is 3.3 V; use appropriate level shifting on any signal entering the ESP8266. Confirm exact ESP8266 module pinout before wiring.

## Separate potentiometer arm controller

| Pot controller pin | Connection |
|---|---|
| A0–A5 | Pot wipers, channels 0–5 |
| Pot outer terminals | 5 V and GND |
| D12 | ENGAGE switch to GND; closed/LOW engages |
| D2, D4, D7, D8, D9, D10 | Servo signals, channels 0–5 |

The pot sketch describes USB power for the Arduino and a separately fused 6.0 V buck servo supply with 1000 µF capacitor; connect grounds together. Never use the Arduino 5 V pin to power the servos. Supply current, fuse rating, capacitor voltage rating, battery, and connector details: TODO.
