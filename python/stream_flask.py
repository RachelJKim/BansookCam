import os
import cv2
import threading
import time
from flask import Flask, Response, render_template_string

# --- Settings ---
CAPTURE_FPS = 60
DISPLAY_FPS = 20
JPEG_QUALITY = 70
WIDTH, HEIGHT = 1280, 720

# Camera device indices: 0 = Arducam (video0), 2 = HD USB Camera (video2)
CAMERA_DEVICES = [0, 2]
CAMERA_NAMES = ['Arducam', 'HD USB Camera']

frame_locks = [threading.Lock(), threading.Lock()]
latest_frames = [None, None]

app = Flask(__name__)

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Streaming...</title>
    <link rel="icon" href="data:,">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css"
          rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; min-height: 100vh; }
        .stream-img {
            max-width: 100%;
            height: auto;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="row">
            <div class="col text-center mt-5 mb-4">
                <h1>Streaming...</h1>
            </div>
        </div>
        <div class="row justify-content-center g-3">
            <div class="col-md-6 text-center">
                <p class="text-muted small mb-1">Arducam</p>
                <img class="stream-img" src="/video_feed/0" alt="Camera 1">
            </div>
            <div class="col-md-6 text-center">
                <p class="text-muted small mb-1">HD USB Camera</p>
                <img class="stream-img" src="/video_feed/1" alt="Camera 2">
            </div>
        </div>
        <div class="row">
            <div class="col text-center text-muted mt-4">
                <p>Resolution: {{ width }}x{{ height }} | FPS: {{ fps }}</p>
            </div>
        </div>
        <div class="row">
            <div class="col text-center mt-3 mb-5">
                <a href="/quit" class="btn btn-danger btn-lg" role="button">Quit</a>
            </div>
        </div>
    </div>
</body>
</html>
"""


def capture_frames(cam_id):
    """Capture from one camera into latest_frames[cam_id]."""
    global latest_frames

    device = CAMERA_DEVICES[cam_id]
    name = CAMERA_NAMES[cam_id]
    print(f"Camera {cam_id} ({name}): opening device {device}...", flush=True)
    cap = cv2.VideoCapture(device)
    print(f"Camera {cam_id} ({name}): open finished.", flush=True)

    if not cap.isOpened():
        print(f"CRITICAL ERROR: Camera {cam_id} ({name}) failed to open.", flush=True)
        return

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, CAPTURE_FPS)

    print(f"Camera {cam_id} ({name}): streaming started.", flush=True)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print(f"Camera {cam_id}: failed to read frame. Exiting loop.", flush=True)
                break
            # HD USB Camera (cam_id 1) is mounted upside-down; flip 180°
            if cam_id == 1:
                frame = cv2.flip(frame, -1)
            with frame_locks[cam_id]:
                latest_frames[cam_id] = frame
    except Exception as e:
        print(f"Error in capture_frames({cam_id}): {e}", flush=True)
    finally:
        cap.release()


def generate_mjpeg(cam_id):
    """Yield JPEG frames as an MJPEG multipart stream for camera cam_id."""
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
    interval = 1.0 / DISPLAY_FPS

    while True:
        with frame_locks[cam_id]:
            if latest_frames[cam_id] is None:
                time.sleep(interval)
                continue
            frame = latest_frames[cam_id].copy()

        ret, buf = cv2.imencode('.jpg', frame, encode_params)
        if not ret:
            time.sleep(interval)
            continue

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n'
        )
        time.sleep(interval)


@app.route('/favicon.ico')
def favicon():
    return '', 204


@app.route('/quit')
def quit_app():
    """Terminate the process so camera and terminal are released."""
    os._exit(0)


@app.route('/')
def index():
    return render_template_string(HTML_PAGE, width=WIDTH, height=HEIGHT, fps=DISPLAY_FPS)


@app.route('/video_feed/<int:cam_id>')
def video_feed(cam_id):
    if cam_id < 0 or cam_id >= len(CAMERA_DEVICES):
        return 'Invalid camera', 404
    return Response(
        generate_mjpeg(cam_id),
        mimetype='multipart/x-mixed-replace; boundary=frame',
    )


if __name__ == '__main__':
    for i in range(len(CAMERA_DEVICES)):
        t = threading.Thread(target=capture_frames, args=(i,), daemon=True)
        t.start()

    time.sleep(3)

    print("Starting Flask MJPEG server (two cameras)...")
    print("Open your browser to: http://localhost:8050")

    app.run(host='0.0.0.0', port=8050, threaded=True)
