import cv2
import collections
import time
import os

# --- Settings ---
FPS = 60  # 60 for long-term recording.
WIDTH, HEIGHT = 1280, 720
BUFFER_SEC = 3  # Pre-event buffer (captures 3 seconds BEFORE the jump)
RECORD_AFTER_SEC = 3  # Post-event recording (captures 3 seconds AFTER the jump)
OUTPUT_DIR = "cat_jumps"

if not os.path.exists(OUTPUT_DIR): 
    os.makedirs(OUTPUT_DIR)

# Camera Configuration
cap = cv2.VideoCapture(0)
# Force MJPG format to achieve high frame rates on Jetson
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
cap.set(cv2.CAP_PROP_FPS, FPS)

# Circular buffer to store past frames
buffer = collections.deque(maxlen=BUFFER_SEC * FPS)

# Background Subtraction Logic (MOG2)
# history: Number of frames the model looks back to learn the background
# varThreshold: Mahalanobis distance threshold (lower is more sensitive)
fgbg = cv2.createBackgroundSubtractorMOG2(history=100, varThreshold=50, detectShadows=False)
recording = False

print("Watching... (Press Ctrl+C to stop)")

try:
    while True:
        ret, frame = cap.read()
        if not ret: break
        
        # Always store the current frame in the buffer
        buffer.append(frame)
        
        # Apply background subtraction to find moving pixels
        fgmask = fgbg.apply(frame)
        
        # Calculate motion score (count of white pixels in the mask)
        motion_score = cv2.countNonZero(fgmask)
        
        # Trigger Condition: Adjust the threshold (10000) based on your room/cat size
        if motion_score > 10000 and not recording:
            print(f"Jump Detected! Saving video... (Score: {motion_score})")
            recording = True
            start_time = time.time()
            
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            fname = os.path.join(OUTPUT_DIR, f"jump_{timestamp}.mp4")
            
            # Initialize VideoWriter (using mp4v codec for compatibility)
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(fname, fourcc, FPS, (WIDTH, HEIGHT))
            
            # Write 'past' frames from the buffer to include the wind-up of the jump
            for f in buffer: 
                out.write(f)
            
        if recording:
            out.write(frame)
            # Check if post-event recording duration has passed
            if time.time() - start_time > RECORD_AFTER_SEC:
                recording = False
                out.release()
                print(f"Recording Saved: {fname}")

except KeyboardInterrupt:
    print("\nStopping the detector...")
finally:
    cap.release()
    if 'out' in locals() and out.isOpened():
        out.release()