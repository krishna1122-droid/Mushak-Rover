# Build process

The synopsis gives a broad staged development method. The steps here adapt only the parts supported by the supplied code; they are a replication outline, not a verified lab log.

1. **Mechanical platform — TODO details.** Assemble the tracked chassis, drive motors, and arm mounting. The exact chassis and mounting process is not recorded.
2. **Drive electronics.** Connect left/right BTS7960 PWM inputs to Uno D5/D6 and D3/D11. Configure enable pins as stated in the Uno sketch comments. Verify motor direction with the tracks lifted before floor testing.
3. **Serial link and bridge.** Wire the ESP8266 GPIO12/14 software-serial link to Uno D12/D13 as described in [wiring](wiring.md), using level shifting toward ESP8266 inputs. Configure Wi-Fi placeholders locally.
4. **Servo arm.** Connect six signal channels to Uno pins 2, 4, 7, 8, 9, and 10. Use an independently sized servo supply and common ground. Confirm safe angle limits before moving the arm; the rover sketch's initial limits are the full 0–180 range.
5. **Phone control.** Upload the bridge sketch, join the configured 2.4 GHz network, open the ESP8266's printed address, and check STOP and low-speed commands with the drive wheels raised.
6. **Laptop controls.** Install Python dependencies, supply local network and camera settings, install the absent `follow_me.py` dependency, then confirm the camera and manual controls before enabling drive. Keep `SEND` behavior in mind: it is currently true.
7. **Standalone arm controller (optional configuration).** Use a separate Uno/Nano and the arm-pot sketch. Match pot positions to the current arm pose before closing ENGAGE. The sketch does not share control with the ESP8266 rover firmware.
8. **Record the actual process.** Add dated photos and specific observed test outcomes. These were not included with the supplied files.

Firmware and software paths are listed in the repository README.
