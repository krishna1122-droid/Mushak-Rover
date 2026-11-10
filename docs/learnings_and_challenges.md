# Learnings and challenges faced

The supplied files do not include a first-person account of the team's development experience, so this section separates code-visible design points from the team's missing reflection.

## Visible in the implementation

- Separate firmware roles allow the Uno to handle motors/servos while the ESP8266 handles phone HTTP requests and laptop UDP traffic.
- The Uno stops motors after 500 ms without commands and moves commanded arm servos one degree per 15 ms step.
- The standalone pot sketch averages 16 readings and ignores changes smaller than three degrees before updating its target.
- Servo power and common-ground requirements are called out in the pot-controller comments.
- The laptop app's external `follow_me.py` dependency and a camera stream configuration are required for its follow-me/video path.

## Team reflection — TODO

Add the actual challenges, debugging steps, design changes, what worked, what did not, and what Krishna and Digvij learned. Do not present code-derived observations above as personal experience.
