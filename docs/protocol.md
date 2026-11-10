# Command protocol

Commands are ASCII, one line per command, terminated by newline when sent over serial. The ESP8266 accepts phone commands via HTTP query parameter `c` and laptop datagrams on UDP port **4210**, then forwards command text to the Uno.

| Command | Meaning |
|---|---|
| `D,<left>,<right>` | Drive left/right sides, each constrained by the Uno to -255 through 255. Negative is reverse. |
| `A,<ch>,<angle>` | Set servo channel 0–5, angle clamped to that channel's configured min/max (currently 0–180 in rover sketch). |
| `S` | Stop both drive motors. |
| `H` | Heartbeat; no direct action, but refreshes the Uno command timer. |

Uno `SoftwareSerial` operates at 9600 baud. Its 500 ms timeout stops the drive motors when no command is received. It does not detach servos or necessarily remove servo holding torque. Laptop app uses a 10 Hz drive-send rate while moving; the bridge does not validate command fields beyond the initial command letter and length for phone requests.
