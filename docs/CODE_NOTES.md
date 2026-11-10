# Code notes and observed inconsistencies

These notes identify source-level issues without silently changing program behavior.

- `mushak_appAK.py` header says `SEND = False` by default, while the setting is `True`. The app can send real rover commands as supplied.
- `ARM_ENABLED = True` is paired with a comment saying to set it true after the buck converter is fitted and joints are mapped; the comment and value disagree.
- Uno firmware comments say the Servo library disables PWM on pins 9 and 10 and lists motor PWM pins 3, 5, 6, 11, which matches the defined motor pins. Validate actual board/driver mapping before use.
- ESP8266 sketch comment describes GPIO12 as D6 TX to Uno D12 and GPIO14 as D5 RX from Uno D13; the `SoftwareSerial uno(14, 12)` constructor uses RX then TX, which agrees. The Uno sketch comment labels pin 13 as TX and pin 12 as RX.
- `follow_me.py` is imported but absent. The app references `StreamReader`, `STALE_TIMEOUT`, `LOST_TIMEOUT`, `MODEL_PATH`, `CONF`, `IMGSZ`, `pick_person`, `SMOOTH`, `compute_drive`, and `YOLO` through that module. Do not substitute an invented implementation.
- Rover firmware command timer refreshes on any parsed line, including malformed lines, because `lastCmd` is updated before command validation. `S` stops motors but does not clear the timer or detach servos.
- The phone bridge forwards UDP payloads and appends newline if missing. Its UDP buffer is 64 bytes; no authentication is implemented.
- The standalone pot controller comment says opening ENGAGE keeps the arm holding its last angle; firmware keeps servo attachments and targets unchanged, so this is the intended behavior but consumes servo holding power.
- Source comments mention a 775 motor, six-degree arm, and measured angle ranges, but the repository lacks independent build evidence and part specifications. Treat those as comments, not verified measurements.
