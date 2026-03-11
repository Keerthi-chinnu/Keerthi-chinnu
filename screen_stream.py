#!/usr/bin/env python3
"""
📡 WiFi Screen Streamer
View your laptop screen from any device on the same network.
Open your browser and go to: http://<YOUR_WIFI_IP>:5000

Requirements:
    pip install pillow flask mss

Usage:
    python screen_stream.py
"""

import io
import socket
import threading
import time

try:
    from flask import Flask, Response, render_template_string
    import mss
    import mss.tools
    from PIL import Image
except ImportError:
    print("Installing required packages...")
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask", "mss", "pillow"])
    from flask import Flask, Response, render_template_string
    import mss
    import mss.tools
    from PIL import Image

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
QUALITY   = 60    # JPEG quality (1-95). Lower = faster, smaller; Higher = sharper
FPS_CAP   = 15    # Max frames per second
MONITOR   = 1     # 0 = all monitors combined, 1 = primary, 2 = secondary, …
PORT      = 5000
# ──────────────────────────────────────────────────────────────────────────────

_frame_lock  = threading.Lock()
_latest_jpeg = b""
_fps_actual  = 0.0


def capture_loop():
    """Background thread: continuously grabs the screen and JPEG-encodes it."""
    global _latest_jpeg, _fps_actual
    interval = 1.0 / FPS_CAP
    with mss.mss() as sct:
        monitor = sct.monitors[MONITOR]
        frame_count = 0
        t0 = time.time()
        while True:
            t_start = time.time()

            img  = sct.grab(monitor)
            pil  = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")

            buf  = io.BytesIO()
            pil.save(buf, format="JPEG", quality=QUALITY, optimize=True)
            jpeg = buf.getvalue()

            with _frame_lock:
                _latest_jpeg = jpeg

            # FPS counter
            frame_count += 1
            elapsed = time.time() - t0
            if elapsed >= 1.0:
                _fps_actual  = frame_count / elapsed
                frame_count  = 0
                t0           = time.time()

            # throttle
            took = time.time() - t_start
            sleep = interval - took
            if sleep > 0:
                time.sleep(sleep)


def generate_mjpeg():
    """Yield an endless MJPEG stream from the latest captured frame."""
    boundary = b"--frame"
    while True:
        with _frame_lock:
            jpeg = _latest_jpeg
        if jpeg:
            yield (
                boundary + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n"
                b"\r\n" + jpeg + b"\r\n"
            )
        time.sleep(1.0 / FPS_CAP)


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📡 Live Screen</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:      #0a0c10;
    --panel:   #10141c;
    --border:  #1e2433;
    --accent:  #00e5ff;
    --dim:     #4a5568;
    --text:    #cdd6f4;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  header {
    width: 100%;
    padding: 14px 24px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 8px var(--accent);
    animation: pulse 1.6s ease-in-out infinite;
  }
  @keyframes pulse {
    0%,100% { opacity: 1; transform: scale(1); }
    50%      { opacity: .4; transform: scale(.75); }
  }

  header h1 { font-size: .85rem; letter-spacing: .12em; color: var(--accent); }

  #stats {
    margin-left: auto;
    font-size: .75rem;
    color: var(--dim);
    display: flex; gap: 20px;
  }
  #stats span { color: var(--text); }

  main {
    flex: 1;
    width: 100%;
    padding: 20px;
    display: flex;
    justify-content: center;
    align-items: flex-start;
  }

  .screen-wrap {
    position: relative;
    width: 100%;
    max-width: 1400px;
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
    box-shadow: 0 0 40px rgba(0,229,255,.07);
  }

  .screen-wrap img {
    display: block;
    width: 100%;
    height: auto;
    image-rendering: auto;
  }

  /* scan-line overlay */
  .screen-wrap::after {
    content: '';
    position: absolute; inset: 0;
    background: repeating-linear-gradient(
      to bottom,
      transparent 0px,
      transparent 3px,
      rgba(0,0,0,.12) 3px,
      rgba(0,0,0,.12) 4px
    );
    pointer-events: none;
  }

  footer {
    padding: 12px;
    font-size: .7rem;
    color: var(--dim);
    letter-spacing: .08em;
  }
</style>
</head>
<body>

<header>
  <div class="dot"></div>
  <h1>LIVE SCREEN STREAM</h1>
  <div id="stats">
    FPS&nbsp;<span id="fps">—</span>
    &nbsp;|&nbsp;
    LATENCY&nbsp;<span id="lat">—</span>&nbsp;ms
  </div>
</header>

<main>
  <div class="screen-wrap">
    <img id="feed" src="/stream" alt="live screen">
  </div>
</main>

<footer>MJPEG · monitor {{ monitor }} · quality {{ quality }} · port {{ port }}</footer>

<script>
  // Measure frame arrival rate client-side
  const img = document.getElementById('feed');
  const fpsEl = document.getElementById('fps');
  const latEl = document.getElementById('lat');
  let last = performance.now(), count = 0;

  img.addEventListener('load', () => {
    const now = performance.now();
    latEl.textContent = Math.round(now - last);
    last = now;
    count++;
  });

  setInterval(() => {
    fpsEl.textContent = count;
    count = 0;
  }, 1000);
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(
        HTML,
        monitor=MONITOR,
        quality=QUALITY,
        port=PORT,
    )


@app.route("/stream")
def stream():
    return Response(
        generate_mjpeg(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


def get_wifi_ip():
    """Return the machine's outbound LAN IP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    # Start capture thread
    t = threading.Thread(target=capture_loop, daemon=True)
    t.start()

    ip = get_wifi_ip()
    print("\n" + "═" * 52)
    print("  📡  Screen Streamer is LIVE")
    print("═" * 52)
    print(f"  Open on ANY device on your WiFi:")
    print(f"\n      http://{ip}:{PORT}\n")
    print(f"  Settings: monitor={MONITOR}  quality={QUALITY}  fps≤{FPS_CAP}")
    print("═" * 52)
    print("  Press Ctrl+C to stop.\n")

    app.run(host="0.0.0.0", port=PORT, threaded=True)