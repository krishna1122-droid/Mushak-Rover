# Safety notes

- Test drive with tracks raised and keep people, loose wires, and tools clear of moving parts.
- `S` and the phone page STOP button command motor stop. The Uno also stops drive outputs after 500 ms without a received line. Test this failsafe safely; it is not a certified emergency stop and does not guarantee a disconnected power stage.
- Laptop `SEND` is set to `True` in the supplied application. Read and configure it before running; opening the interface can lead to transmitted drive commands. The application starts with drive disabled, but do not rely on that as the only safeguard.
- The ESP8266 phone page and UDP bridge have no authentication or encryption in the supplied code. Use only a controlled local network and do not expose them to the internet.
- Keep servo power separate from the Arduino supply. The pot-controller comments call for a fused 6 V buck, 1000 µF capacitor, and common ground. Verify voltage, current, fuse, polarity, and wiring for the actual servos.
- The pot sketch's ENGAGE switch is active low. On first engagement, each servo immediately attaches at its current pot-derived angle; set the pots near the arm's existing pose first. Opening the switch leaves attached servos holding their last target.
- The rover Uno sketch attaches a servo on its first angle command and writes that angle immediately. Start with conservative limits and clear space around the arm.
- Inspect the project at the competition venue and follow event rules. The rulebook disallows hazardous materials, open flames, or high voltages without prior approval.
