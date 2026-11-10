/*
  Mushak Rover - ESP8266 firmware with manual control page

  Does two jobs:
    1. Serves a control page (joystick + 6 arm sliders) at http://<rover-ip>/
       Open it on your phone, connected to the same 2.4 GHz Wi-Fi.
    2. Still accepts UDP command lines from the laptop (autonomous mode).
  Everything is forwarded unchanged to the Arduino Uno over serial.

  This replaces mushak_esp8266.ino (it contains everything that file did).

  Wiring (same as before):
    ESP8266 GPIO12 (D6, TX) -> Uno pin 12 (RX)
    Uno pin 13 (TX) -> level shifter -> ESP8266 GPIO14 (D5, RX)   optional for now
    GND <-> GND
*/

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <WiFiUdp.h>
#include <SoftwareSerial.h>

const char *WIFI_SSID = "YOUR_WIFI_SSID";
const char *WIFI_PASS = "YOUR_WIFI_PASSWORD";
const uint16_t UDP_PORT = 4210;

SoftwareSerial uno(14, 12);   // (RX = GPIO14, TX = GPIO12)
ESP8266WebServer server(80);
WiFiUDP udp;
char packet[64];

// ---------- The control page (runs in the phone's browser) ----------
static const char PAGE[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>Mushak Rover</title>
<style>
  body{font-family:system-ui,sans-serif;margin:0;padding:12px;background:#111;color:#eee}
  h1{font-size:18px;margin:0 0 8px}
  #status{font-size:13px;color:#7c7;margin-left:8px}
  .card{background:#1c1c1c;border-radius:12px;padding:12px;margin:10px 0}
  #pad{width:220px;height:220px;border-radius:50%;background:#262626;margin:12px auto;position:relative;touch-action:none}
  #knob{width:80px;height:80px;border-radius:50%;background:#3b82f6;position:absolute;left:70px;top:70px}
  .row{display:flex;align-items:center;gap:8px;margin:8px 0}
  .row label{width:70px;font-size:14px}
  input[type=range]{flex:1}
  .val{width:32px;text-align:right;font-size:13px}
  button{padding:14px;border:0;border-radius:10px;font-size:16px;background:#dc2626;color:#fff;width:100%}
</style></head><body>
<h1>Mushak Rover<span id="status">ready</span></h1>

<div class="card">
  <div class="row"><label>Speed</label>
    <input id="spd" type="range" min="20" max="100" value="60"><span class="val" id="spdv">60</span></div>
  <div id="pad"><div id="knob"></div></div>
  <button id="stop">STOP</button>
</div>

<div class="card" id="arm"></div>

<script>
const st = document.getElementById('status');

function send(c) {
  fetch('/cmd?c=' + encodeURIComponent(c), {cache: 'no-store'})
    .then(() => { st.textContent = 'connected'; st.style.color = '#7c7'; })
    .catch(() => { st.textContent = 'no connection'; st.style.color = '#f66'; });
}

// ----- Speed limit -----
const spd = document.getElementById('spd'), spdv = document.getElementById('spdv');
spd.oninput = () => { spdv.textContent = spd.value; };

// ----- Joystick -----
const pad = document.getElementById('pad'), knob = document.getElementById('knob');
const R = 70;                       // max knob travel in pixels
let active = false, jx = 0, jy = 0;

function move(e) {
  const r = pad.getBoundingClientRect();
  let dx = e.clientX - (r.left + r.width / 2);
  let dy = e.clientY - (r.top + r.height / 2);
  const d = Math.hypot(dx, dy);
  if (d > R) { dx *= R / d; dy *= R / d; }
  knob.style.left = (70 + dx) + 'px';
  knob.style.top = (70 + dy) + 'px';
  jx = dx / R;                      // -1 left .. +1 right
  jy = -dy / R;                     // -1 back .. +1 forward
}
function release() {
  active = false; jx = 0; jy = 0;
  knob.style.left = '70px'; knob.style.top = '70px';
  send('D,0,0');
}
pad.addEventListener('pointerdown', e => { active = true; pad.setPointerCapture(e.pointerId); move(e); });
pad.addEventListener('pointermove', e => { if (active) move(e); });
pad.addEventListener('pointerup', release);
pad.addEventListener('pointercancel', release);

// While the stick is held, send a drive command 10 times a second.
// (The Uno stops the motors on its own if these stop arriving.)
setInterval(() => {
  if (!active) return;
  const l = jy + jx, r = jy - jx;
  const m = Math.max(1, Math.abs(l), Math.abs(r));
  const k = 255 * spd.value / 100 / m;
  send('D,' + Math.round(l * k) + ',' + Math.round(r * k));
}, 100);

document.getElementById('stop').onclick = () => send('S');

// ----- Arm sliders -----
const armDiv = document.getElementById('arm');
const lastSent = [0, 0, 0, 0, 0, 0];
for (let i = 0; i < 6; i++) {
  const row = document.createElement('div');
  row.className = 'row';
  row.innerHTML = '<label>Servo ' + i + '</label>' +
    '<input type="range" min="0" max="180" value="90"><span class="val">90</span>';
  const s = row.querySelector('input'), v = row.querySelector('span');
  s.addEventListener('input', () => {
    v.textContent = s.value;
    const t = Date.now();
    if (t - lastSent[i] > 80) { lastSent[i] = t; send('A,' + i + ',' + s.value); }
  });
  s.addEventListener('change', () => send('A,' + i + ',' + s.value));  // always send the final value
  armDiv.appendChild(row);
}
</script>
</body></html>
)rawliteral";

// ---------- Web handlers ----------
void handleRoot() {
  server.send_P(200, "text/html", PAGE);
}

void handleCmd() {
  if (server.hasArg("c")) {
    String c = server.arg("c");
    c.trim();
    char first = c.length() > 0 ? c[0] : 0;
    // Only pass on known commands: D (drive), A (arm), S (stop), H (heartbeat)
    if (c.length() < 40 && (first == 'D' || first == 'A' || first == 'S' || first == 'H')) {
      uno.print(c);
      uno.print('\n');
      Serial.println(c);
    }
  }
  server.send(200, "text/plain", "ok");
}

// ---------- Arduino ----------
void setup() {
  Serial.begin(115200);
  uno.begin(9600);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("Connected. Rover IP address: ");
  Serial.println(WiFi.localIP());
  Serial.print("Open this on your phone: http://");
  Serial.println(WiFi.localIP());

  server.on("/", handleRoot);
  server.on("/cmd", handleCmd);
  server.begin();
  udp.begin(UDP_PORT);
}

void loop() {
  server.handleClient();

  // UDP commands from the laptop (autonomous mode)
  if (udp.parsePacket() > 0) {
    int n = udp.read(packet, sizeof(packet) - 1);
    if (n > 0) {
      packet[n] = 0;
      uno.print(packet);
      if (packet[n - 1] != '\n') uno.print('\n');
      Serial.print(packet);
    }
  }
}
