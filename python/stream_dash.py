import cv2
import threading
import time
from flask import Flask, Response, render_template_string

# --- Settings ---
CAPTURE_FPS = 60
DISPLAY_FPS = 20
JPEG_QUALITY = 70
WIDTH, HEIGHT = 1280, 720

frame_lock = threading.Lock()
latest_frame = None

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
        <div class="row justify-content-center">
            <div class="col-md-10 text-center">
                <img class="stream-img" src="/video_feed" alt="Camera Stream">
            </div>
        </div>
        <div class="row">
            <div class="col text-center text-muted mt-4">
                <p>Resolution: {{ width }}x{{ height }} | FPS: {{ fps }}</p>
            </div>
        </div>
    </div>
</body>
</html>
"""


def capture_frames():
    global latest_frame

    print("Background thread started. Attempting to open camera...", flush=True)
    cap = cv2.VideoCapture(0)
    print("Camera open command finished.", flush=True)

    if not cap.isOpened():
        print("CRITICAL ERROR: Camera failed to open.", flush=True)
        return

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, CAPTURE_FPS)

    print("Camera initialized. Streaming started...", flush=True)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Failed to read frame from camera. Exiting loop.", flush=True)
                break
            with frame_lock:
                latest_frame = frame
    except Exception as e:
        print(f"Error in capture_frames: {e}", flush=True)
    finally:
        cap.release()


def generate_mjpeg():
    """Yield JPEG frames as an MJPEG multipart stream."""
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
    interval = 1.0 / DISPLAY_FPS

    while True:
        with frame_lock:
            if latest_frame is None:
                time.sleep(interval)
                continue
            frame = latest_frame.copy()

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


@app.route('/')
def index():
    return render_template_string(HTML_PAGE, width=WIDTH, height=HEIGHT, fps=DISPLAY_FPS)


@app.route('/video_feed')
def video_feed():
    return Response(
        generate_mjpeg(),
        mimetype='multipart/x-mixed-replace; boundary=frame',
    )


if __name__ == '__main__':
    camera_thread = threading.Thread(target=capture_frames, daemon=True)
    camera_thread.start()

    time.sleep(3)

    print("Starting Flask MJPEG server...")
    print("Open your browser to: http://localhost:8050")

    app.run(host='0.0.0.0', port=8050, threaded=True)
