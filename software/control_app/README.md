# Laptop control app

## Install

Use Python 3.10 or newer (version not stated in source; confirm compatibility for the chosen Ultralytics release). Create a virtual environment, then install:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The source imports `cv2`, Flask, and `follow_me`; it also calls `fm.YOLO`, so the requirements list includes OpenCV and Ultralytics as stated in the source header. The required `follow_me.py` was not supplied. Its API and additional dependencies are listed in [../../docs/CODE_NOTES.md](../../docs/CODE_NOTES.md).

## Configure and run

Edit the settings near the top of `mushak_appAK.py` for the local rover IP, ESP32-CAM stream URL, and app username/password. Replace placeholders with private local values; do not commit them. `SEND` is currently `True`, so the app transmits commands. The code's opening comment incorrectly says it defaults to `False`; see code notes.

Run `python mushak_appAK.py`, then open `http://localhost:8000` on the laptop. To access it from a phone on the same network, use the laptop's local address and port 8000. The Flask development server is not intended for public internet exposure.

The browser requires HTTP Basic authentication using the configured username and password. The app's `follow_me.py` dependency, ESP32-CAM stream configuration, and matching network settings are needed for the camera/follow features.
