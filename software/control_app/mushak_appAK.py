"""
Mushak Rover Control - one app for driving, live camera, follow-me and the arm.
(The BSS panel can be merged in later; the rover part is kept self-contained.)

Run:   python mushak_app.py      then open  http://localhost:8000
       (phone on the same hotspot: http://<laptop-ip>:8000)
Needs: pip install flask opencv-python ultralytics    and follow_me.py in the same folder
       (this app reuses its person-following logic and tuning values).

The app is the ONLY viewer of the ESP32-CAM: it reads the stream once, runs the
detector when needed, and re-serves the video (with the overlay) to the browser.
Close every other camera tab / script first.

SAFETY: SEND = False by default (nothing is sent). Drive starts DISABLED. STOP, Space,
leaving the page, a stalled camera or a stalled browser all stop the rover, and the
Uno stops by itself after 500 ms without commands.
"""
import csv
import json
import os
import socket
import threading
import time
from datetime import datetime

import cv2
from flask import Flask, Response, jsonify, request

import follow_me as fm

# ---------------- Settings ----------------
SEND = True                         # False = simulate, True = really send to the rover
ROVER_IP = "ROVER_IP"                  # IP printed by the rover ESP8266
ROVER_PORT = 4210                     # UDP port of the ESP8266 bridge
DRIVE_SEND_HZ = 10                    # commands per second WHILE DRIVING (idle = silent, which stops arm jitter)
CAM_URL = "http://CAMERA_IP:81/stream" # ESP32-CAM stream
WEB_PORT = 8000
USER, PASSWORD = "APP_USER", "APP_PASSWORD" # CHANGE the password before showing it to anyone
LOG_FILE = "rover_log.csv"            # events for your pitch evidence

ARM_ENABLED = True                 # set True after the new buck converter is fitted and joints are mapped
ARM_LIMITS = {0: (0, 180), 1: (0, 180), 2: (0, 180),   # channel: (min, max) - set safe values after
              3: (0, 180), 4: (0, 180), 5: (0, 180)}   # mapping with servo_test.ino
ARM_HOME = {0: 90, 1: 90, 2: 90, 3: 90, 4: 90, 5: 90}   # where the arm is ASSUMED to be at start-up:
                                      # put the arm in this position BEFORE powering the arm servos
GRIPPER_CH = 5                        # which channel is the gripper (set after mapping the joints)
ARM_FILE = "arm_poses.json"           # poses you teach in the app are saved here
POSE_NAMES = ("home", "ready", "grab", "lift", "open", "close")
# One-button actions: a list of (pose, seconds to move there). Poses are taught once in the app
# ("Teach poses"); an action refuses to run until all its poses are taught. Edit the steps freely.
ARM_ACTIONS = {
    "Pick & lift":   [("ready", 2.0), ("open", 0.8), ("grab", 2.0), ("close", 1.0), ("lift", 2.0)],
    "Release":       [("open", 1.0)],
    "Home":          [("home", 2.5)],
    "Open gripper":  [("open", 0.8)],
    "Close gripper": [("close", 0.8)],
}

# ---------------- State ----------------
S = {"enabled": False, "mode": "MANUAL", "follow_go": False, "speed": 35,
     "manual": (0, 0, 0.0), "follow": (0, 0, "-", 0.0), "frame_ts": 0.0,
     "cmd": "S", "fps": 0.0, "online": False, "jpg": None, "arm_busy": ""}
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
app = Flask(__name__)
ARM_NOW = dict(ARM_HOME)              # last angle sent per channel
ARM_ABORT = threading.Event()         # set = stop the running arm action


def log(event, detail=""):
    new = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "event", "detail"])
        w.writerow([datetime.now().isoformat(timespec="milliseconds"), event, detail])


def send(text):
    if SEND:
        sock.sendto((text + "\n").encode(), (ROVER_IP, ROVER_PORT))


def stop_all(reason):
    S["enabled"] = False
    S["follow_go"] = False
    S["manual"] = (0, 0, 0.0)
    ARM_ABORT.set()
    for _ in range(3):
        send("S")
    log("STOP", reason)


# ---------------- Arm actions ----------------
def load_poses():
    if not os.path.exists(ARM_FILE):
        return {}
    raw = json.load(open(ARM_FILE))
    return {k: {int(c): int(a) for c, a in v.items()} for k, v in raw.items()}


POSES = load_poses()


def save_pose(name):
    """Save the arm's current position as a pose (open/close store only the gripper)."""
    POSES[name] = {GRIPPER_CH: ARM_NOW[GRIPPER_CH]} if name in ("open", "close") else dict(ARM_NOW)
    json.dump({k: {str(c): a for c, a in v.items()} for k, v in POSES.items()}, open(ARM_FILE, "w"))
    log("ARM_POSE_SAVED", name)


def arm_move(target, secs):
    """Glide to the target pose in small steps (no sudden jerk). False if aborted."""
    start, steps = dict(ARM_NOW), max(1, int(secs / 0.1))
    for i in range(1, steps + 1):
        if ARM_ABORT.is_set():
            return False
        for ch, a in target.items():
            lo, hi = ARM_LIMITS[ch]
            goal = max(lo, min(hi, a))
            v = int(round(start[ch] + (goal - start[ch]) * i / steps))
            if v != ARM_NOW[ch]:
                ARM_NOW[ch] = v
                send(f"A,{ch},{v}")
        time.sleep(0.1)
    return True


def run_action(name):
    log("ARM_ACTION", name)
    try:
        for pose, secs in ARM_ACTIONS[name]:
            if not arm_move(POSES[pose], secs):
                log("ARM_ABORT", name)
                return
        log("ARM_DONE", name)
    finally:
        S["arm_busy"] = ""


# ---------------- Background threads ----------------
def drive_loop():
    """Sends drive commands only while driving (DRIVE_SEND_HZ per second, also the heartbeat).
    When idle it sends STOP three times and then stays SILENT, because constant serial traffic
    makes the Uno's servos jitter. The Uno stops the motors by itself after 500 ms without
    commands, so silence is safe. Anything doubtful -> STOP."""
    stops_left = 3
    while True:
        now, cmd = time.time(), "S"
        if S["enabled"]:
            if S["mode"] == "MANUAL":
                l, r, t = S["manual"]
                if now - t < 0.4 and (l or r):
                    cmd = f"D,{l},{r}"
            elif S["follow_go"] and now - S["frame_ts"] < fm.STALE_TIMEOUT:
                l, r, st, t = S["follow"]
                if now - t < fm.LOST_TIMEOUT and (l or r):
                    cmd = f"D,{l},{r}"
        S["cmd"] = cmd
        if cmd == "S":
            if stops_left > 0:
                send(cmd)
                stops_left -= 1
            time.sleep(0.05)
        else:
            stops_left = 3
            send(cmd)
            time.sleep(1.0 / DRIVE_SEND_HZ)


def online_loop():
    last_err = None
    while True:
        try:
            socket.create_connection((ROVER_IP, 80), 2.0).close()
            S["online"] = True
            last_err = None
        except OSError as e:
            S["online"] = False
            if str(e) != last_err:
                print("ONLINE CHECK FAILED for", ROVER_IP, "->", e)
                last_err = str(e)
        time.sleep(2)

def cam_loop():
    reader = fm.StreamReader(CAM_URL)
    model, so, sh = None, None, None
    seen, last_stamp, last_st, n, t0 = 0.0, 0.0, "", 0, time.time()
    while True:
        frame, stamp = reader.latest()
        if frame is None or stamp == last_stamp:
            time.sleep(0.01)
            continue
        last_stamp = stamp
        S["frame_ts"] = stamp
        frame = frame.copy()
        h, w = frame.shape[:2]
        now, text = time.time(), "MANUAL"

        if S["mode"] == "FOLLOW":
            if model is None:
                model = fm.YOLO(fm.MODEL_PATH)
            res = model(frame, classes=[0], conf=fm.CONF, imgsz=fm.IMGSZ, verbose=False)[0]
            box = None
            if len(res.boxes):
                off, hgt, box = fm.pick_person(res.boxes, w, h, so)
                seen = now
                if so is None:
                    so, sh = off, hgt
                else:
                    so = fm.SMOOTH * so + (1 - fm.SMOOTH) * off
                    sh = fm.SMOOTH * sh + (1 - fm.SMOOTH) * hgt
            if so is not None and now - seen < fm.LOST_TIMEOUT:
                l, r, st = fm.compute_drive(so, sh) if box else (0, 0, "HOLD")
            else:
                so = sh = None
                l, r, st = 0, 0, "LOST"
            if st != last_st:
                log("FOLLOW_STATE", st)
                last_st = st
            S["follow"] = (l, r, st, now)
            if box:
                cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
            text = f"FOLLOW {st}" + ("" if S["follow_go"] else " (paused)")
        else:
            so = sh = None
            last_st = ""
            S["follow"] = (0, 0, "-", now)

        n += 1
        if now - t0 >= 1:
            S["fps"], n, t0 = round(n / (now - t0), 1), 0, now
        cv2.putText(frame, text, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            S["jpg"] = buf.tobytes()


# ---------------- Web API ----------------
@app.before_request
def auth():
    a = request.authorization
    if not a or a.username != USER or a.password != PASSWORD:
        return Response("Login required", 401, {"WWW-Authenticate": 'Basic realm="Mushak"'})


def status(msg=""):
    return jsonify(enabled=S["enabled"], mode=S["mode"], go=S["follow_go"], speed=S["speed"],
                   state=S["follow"][2], cmd=S["cmd"], fps=S["fps"], online=S["online"], send=SEND,
                   cam=time.time() - S["frame_ts"] < 2, armbusy=S["arm_busy"],
                   taught=sorted(POSES), armnow=ARM_NOW, msg=msg)


@app.route("/api/status")
def api_status():
    return status()


@app.route("/api/drive")
def api_drive():
    x, y = float(request.args.get("x", 0)), float(request.args.get("y", 0))
    if (x * x + y * y) ** 0.5 < 0.1:
        x = y = 0
    v = S["speed"] * 2.55
    m = max(1.0, abs(y + x), abs(y - x))
    S["manual"] = (int((y + x) / m * v), int((y - x) / m * v), time.time())
    return status()


@app.route("/api/enable")
def api_enable():
    if request.args.get("on") == "1":
        S["enabled"] = True
        log("DRIVE_ENABLED")
    else:
        stop_all("drive disabled")
    return status()


@app.route("/api/mode")
def api_mode():
    m = request.args.get("m", "MANUAL")
    S["mode"] = "FOLLOW" if m == "FOLLOW" else "MANUAL"
    S["follow_go"] = False
    S["manual"] = (0, 0, 0.0)
    log("MODE", S["mode"])
    return status()


@app.route("/api/go")
def api_go():
    S["follow_go"] = request.args.get("on") == "1" and S["mode"] == "FOLLOW" and S["enabled"]
    log("FOLLOW_GO" if S["follow_go"] else "FOLLOW_PAUSE")
    return status()


@app.route("/api/stop")
def api_stop():
    stop_all("STOP button / key")
    return status()


@app.route("/api/speed")
def api_speed():
    S["speed"] = max(10, min(100, int(float(request.args.get("v", 35)))))
    return status()


@app.route("/api/arm")
def api_arm():                        # direct move, used only by the Teach poses sliders
    if ARM_ENABLED and not S["arm_busy"]:
        ch, a = int(request.args["ch"]), int(float(request.args["a"]))
        lo, hi = ARM_LIMITS.get(ch, (90, 90))
        ARM_NOW[ch] = max(lo, min(hi, a))
        send(f"A,{ch},{ARM_NOW[ch]}")
    return status()


@app.route("/api/arm_action")
def api_arm_action():
    name = request.args.get("name", "")
    if not ARM_ENABLED:
        return status("Arm is disabled (set ARM_ENABLED = True)")
    if name not in ARM_ACTIONS:
        return status("Unknown action")
    if S["arm_busy"]:
        return status("Arm is busy: " + S["arm_busy"])
    missing = sorted({p for p, _ in ARM_ACTIONS[name] if p not in POSES})
    if missing:
        return status("Teach these poses first: " + ", ".join(missing))
    ARM_ABORT.clear()
    S["arm_busy"] = name
    threading.Thread(target=run_action, args=(name,), daemon=True).start()
    return status("Running: " + name)


@app.route("/api/arm_stop")
def api_arm_stop():
    ARM_ABORT.set()
    log("ARM_STOP")
    return status("Arm stopped (holding its position)")


@app.route("/api/arm_save")
def api_arm_save():
    name = request.args.get("pose", "")
    if name not in POSE_NAMES or not ARM_ENABLED:
        return status("Cannot save (arm disabled or unknown pose)")
    save_pose(name)
    return status("Saved pose: " + name)


@app.route("/video")
def video():
    def gen():
        while True:
            if S["jpg"]:
                yield b"--f\r\nContent-Type: image/jpeg\r\n\r\n" + S["jpg"] + b"\r\n"
            time.sleep(0.06)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=f")


@app.route("/log.csv")
def log_csv():
    data = open(LOG_FILE).read() if os.path.exists(LOG_FILE) else "time,event,detail\n"
    return Response(data, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=rover_log.csv"})


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Mushak Rover</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{margin:0;font:14px system-ui,sans-serif;background:#111;color:#eee}
.wrap{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:12px;padding:12px}
@media(max-width:800px){.wrap{grid-template-columns:1fr}}
.card{background:#1b1b1b;border-radius:8px;padding:10px;margin-bottom:10px}
#cam{width:100%;aspect-ratio:4/3;object-fit:contain;background:#000;border-radius:8px}
button{background:#333;color:#eee;border:0;border-radius:6px;padding:10px 14px;margin:2px;font-size:14px}
button.on{background:#2e7d32}#stop{background:#c62828;color:#fff;font-size:22px;padding:16px;width:100%;margin:0}
#en{width:100%;margin:0 0 8px}
#pad{position:relative;width:220px;height:220px;margin:6px auto;border-radius:50%;background:#262626;touch-action:none}
#knob{position:absolute;width:56px;height:56px;border-radius:50%;background:#4caf50;left:50%;top:50%;
transform:translate(-50%,-50%);pointer-events:none}
input[type=range]{width:100%}small{color:#999}
</style></head><body><div class="wrap">
<div><div class="card" id="st">connecting...</div>
<img id="cam" src="/video" alt="Waiting for camera">
<div class="card">Mode:
<button id="mM" onclick="mode('MANUAL')">Manual</button>
<button id="mF" onclick="mode('FOLLOW')">Follow me</button>
&nbsp;<button id="go" onclick="go(1)">Go (g)</button><button onclick="go(0)">Pause</button><br>
<small>Follow uses the tuning values in follow_me.py. It stops when you are lost or the video stalls.</small></div></div>
<div><button id="en" onclick="enable()">Drive DISABLED</button>
<button id="stop" onclick="stopNow()">STOP (Space)</button>
<div class="card">Manual speed: <b id="sv"></b>%<input id="sp" type="range" min="10" max="100" value="35">
<div id="pad"><div id="knob"></div></div><small>Drag the pad, or use W A S D / arrow keys.</small></div>
<div class="card"><b>Arm actions</b> <small id="armnote"></small><br>
<button class="act" onclick="armDo('Pick & lift')">Pick &amp; lift</button>
<button class="act" onclick="armDo('Release')">Release</button>
<button class="act" onclick="armDo('Home')">Home</button><br>
<button class="act" onclick="armDo('Open gripper')">Open gripper</button>
<button class="act" onclick="armDo('Close gripper')">Close gripper</button>
<button style="background:#c62828" onclick="armDo('')" id="astop">STOP ARM</button>
<div id="armmsg"><small></small></div><small id="taught"></small>
<details open><summary>Manual sliders and teach poses</summary>
<small>The sliders move the arm live, so go slowly. To teach a pose, move the sliders there, then save it. Open/close save only the gripper.</small>
<div id="arm"></div>
<button class="act" onclick="armSave('home')">Save home</button><button class="act" onclick="armSave('ready')">Save ready</button>
<button class="act" onclick="armSave('grab')">Save grab</button><button class="act" onclick="armSave('lift')">Save lift</button>
<button class="act" onclick="armSave('open')">Save gripper OPEN</button><button class="act" onclick="armSave('close')">Save gripper CLOSED</button>
</details></div>
<div class="card"><a style="color:#8ab4f8" href="/log.csv">Download event log (CSV)</a></div></div></div>
<script>
const $=id=>document.getElementById(id), ARM=__ARM__, ARM_ON=__ARMON__, HOME=__HOME__;
const api=p=>fetch('/api/'+p).then(r=>r.json()).catch(()=>({}));
let px=0,py=0,kx=0,ky=0,moved=false,en=false;
const cam=$('cam');cam.onerror=()=>setTimeout(()=>{cam.src='/video?'+Date.now()},1500);  // retry if the stream fails to start
const pad=$('pad'),knob=$('knob');
function setPad(e){const r=pad.getBoundingClientRect();let x=(e.clientX-r.left)/r.width*2-1,y=-((e.clientY-r.top)/r.height*2-1);
const m=Math.hypot(x,y);if(m>1){x/=m;y/=m}px=x;py=y;knob.style.left=(50+x*40)+'%';knob.style.top=(50-y*40)+'%'}
function resetPad(){px=py=0;knob.style.left='50%';knob.style.top='50%'}
pad.onpointerdown=e=>{pad.setPointerCapture(e.pointerId);setPad(e)};
pad.onpointermove=e=>{if(e.buttons)setPad(e)};pad.onpointerup=pad.onpointercancel=resetPad;
const K={w:[0,1],ArrowUp:[0,1],s:[0,-1],ArrowDown:[0,-1],a:[-1,0],ArrowLeft:[-1,0],d:[1,0],ArrowRight:[1,0]},held=new Set();
function keys(){let x=0,y=0;held.forEach(k=>{x+=K[k][0];y+=K[k][1]});kx=Math.max(-1,Math.min(1,x));ky=Math.max(-1,Math.min(1,y))}
onkeydown=e=>{if(e.target.tagName==='INPUT'&&e.key!==' ')return;
if(e.key===' '){e.preventDefault();stopNow();return}if(e.key==='g')go(1);if(K[e.key]){e.preventDefault();held.add(e.key);keys()}};
onkeyup=e=>{held.delete(e.key);keys()};
onblur=()=>{held.clear();keys();resetPad();api('drive?x=0&y=0')};
setInterval(()=>{const x=px||kx,y=py||ky,mv=!!(x||y);if(mv||moved)api('drive?x='+x.toFixed(2)+'&y='+y.toFixed(2));moved=mv},100);
function enable(){api('enable?on='+(en?0:1)).then(draw)}
function stopNow(){held.clear();keys();resetPad();api('stop').then(draw)}
function mode(m){api('mode?m='+m).then(draw)}
function go(on){api('go?on='+on).then(draw)}
$('sp').oninput=e=>{$('sv').textContent=e.target.value;api('speed?v='+e.target.value)};$('sv').textContent=35;
let armBusy=false;
ARM.forEach((lim,i)=>{const d=document.createElement('div');
d.innerHTML='Ch'+i+' <b id="av'+i+'">'+HOME[i]+'</b>&deg; <small>('+lim[0]+'-'+lim[1]+')</small><input type="range" id="a'+i+'" min="'+lim[0]+'" max="'+lim[1]+'" value="'+HOME[i]+'"'+(ARM_ON?'':' disabled')+'>';
$('arm').appendChild(d);const sl=$('a'+i);
sl.oninput=e=>{$('av'+i).textContent=e.target.value;if(armBusy)return;armBusy=true;setTimeout(()=>armBusy=false,80);api('arm?ch='+i+'&a='+e.target.value)};
sl.onchange=e=>api('arm?ch='+i+'&a='+e.target.value)});
let drag=false;addEventListener('pointerdown',e=>{if(e.target.type==='range')drag=true});
addEventListener('pointerup',()=>drag=false);addEventListener('pointercancel',()=>drag=false);
function armDo(n){if(n==='')api('arm_stop').then(draw);else api('arm_action?name='+encodeURIComponent(n)).then(draw)}
function armSave(p){api('arm_save?pose='+p).then(draw)}
document.querySelectorAll('.act').forEach(b=>b.disabled=!ARM_ON);
function drawArm(s){const m=$('armmsg');
if(s.armnow&&!drag)ARM.forEach((l,i)=>{const v=s.armnow[i];if(v!==undefined){$('a'+i).value=v;$('av'+i).textContent=v}});
if(s.msg)m.textContent=s.msg;else if(s.armbusy)m.textContent='Running: '+s.armbusy;else if(m.textContent.startsWith('Running'))m.textContent='Done';
$('taught').textContent='Taught poses: '+((s.taught||[]).join(', ')||'none')}
$('armnote').textContent=ARM_ON?'':'(disabled: set ARM_ENABLED = True after mapping joints)';
function draw(s){if(!s||!s.mode)return;en=s.enabled;drawArm(s);
$('en').textContent=en?'Drive ENABLED (click to disable)':'Drive DISABLED (click to enable)';$('en').className=en?'on':'';
$('mM').className=s.mode==='MANUAL'?'on':'';$('mF').className=s.mode==='FOLLOW'?'on':'';$('go').className=s.go?'on':'';
$('st').innerHTML='Rover: <b>'+(s.online?'online':'offline')+'</b> &middot; '+(s.send?'SENDING to rover':'<b style="color:#ffb300">SIMULATION - nothing is sent</b>')+
' &middot; Camera: <b>'+(s.cam?s.fps+' fps':'no video')+'</b><br>Mode: <b>'+s.mode+'</b>'+(s.mode==='FOLLOW'?' ('+s.state+(s.go?'':', paused')+')':'')+' &middot; Command: <code>'+s.cmd+'</code>'}
setInterval(()=>api('status').then(draw),500);
</script></body></html>"""


@app.route("/")
def index():
    arm = [list(ARM_LIMITS[i]) for i in range(6)]
    home = [ARM_HOME[i] for i in range(6)]
    return (PAGE.replace("__ARM__", json.dumps(arm)).replace("__ARMON__", json.dumps(ARM_ENABLED))
            .replace("__HOME__", json.dumps(home)))


if __name__ == "__main__":
    for fn in (drive_loop, online_loop, cam_loop):
        threading.Thread(target=fn, daemon=True).start()
    log("APP_START", "SEND=" + str(SEND))
    print(f"Open http://localhost:{WEB_PORT}  (user {USER})   SEND = {SEND}")
    try:
        app.run(host="0.0.0.0", port=WEB_PORT, threaded=True)
    finally:
        for _ in range(3):
            send("S")
