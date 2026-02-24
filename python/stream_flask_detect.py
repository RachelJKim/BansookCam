import os
import cv2
import threading
import time
from flask import Flask, Response, render_template_string
from ultralytics import YOLO 

# --- Settings ---
CAPTURE_FPS = 30 # Reduced slightly for better AI stability
DISPLAY_FPS = 20
JPEG_QUALITY = 70
WIDTH, HEIGHT = 1280, 720

frame_lock = threading.Lock()
latest_frame = None

# --- AI Setup ---
# 'yolov8n.pt' is the Nano model. It will auto-download on first run.
model = YOLO('yolov8n.pt') 

app = Flask(__name__)

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Streaming...</title>
    <link rel="icon" href="data:,">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; min-height: 100vh; }
        .stream-img { max-width: 100%; height: auto; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="row">
            <div class="col text-center mt-5 mb-4"><h1>Streaming...</h1></div>
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
        <div class="row">
            <div class="col text-center mt-3 mb-5">
                <a href="/quit" class="btn btn-danger btn-lg" role="button">Quit</a>
            </div>
        </div>
    </div>
</body>
</html>
""" 

def capture_frames():
    global latest_frame
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("CRITICAL ERROR: Camera failed to open.")
        return

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, CAPTURE_FPS)

    print("AI Camera initialized. Looking for cats...")

    try:
        while True:
            ret, frame = cap.read()
            if not ret: break

            # --- AI DETECTION STEP ---
            # persist=True helps track the same cat across frames
            # stream=True is more memory efficient
            results = model.predict(frame, conf=0.5, verbose=False, stream=True, device='cpu')

            for r in results:
                for box in r.boxes:
                    # Get class ID (Cat is usually index 15 in COCO)
                    class_id = int(box.cls[0])
                    label = model.names[class_id]

                    if label == 'cat':
                        # Get coordinates
                        b = box.xyxy[0].cpu().numpy() # [x1, y1, x2, y2]
                        conf = float(box.conf[0])

                        # Draw Bounding Box
                        cv2.rectangle(frame, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (0, 255, 0), 2)
                        
                        # Add Label Text
                        cv2.putText(frame, f"CAT {conf:.2f}", (int(b[0]), int(b[1] - 10)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            with frame_lock:
                latest_frame = frame
                
    finally:
        cap.release()


def generate_mjpeg():
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


@app.route('/quit')
def quit_app():
    os._exit(0)


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
    print("Starting Flask MJPEG server (AI cat detection)...")
    print("Open your browser to: http://localhost:8050")
    app.run(host='0.0.0.0', port=8050, threaded=True)