"""
realtime_speed_test.py
Realtime benchmark for ModelHandler + detect_objects pipeline.
Focus: frame processing speed (FPS) and stability.
"""
try:
    # logging.basicConfig(level=logging.INFO)
    from Model.Model_optimize import load_model
    load_model()
except Exception as e:
    print("Fail load model")

import cv2
import time
import threading
from collections import deque
from ModelHandler import ModelHandler
from Model.Model_optimize import task_select

# ---------- CONFIG ----------
CAM_INDEX = 0                # use camera 0
TASK_ID = 3                  # choose PPE task (1–5)
SHOW_WINDOW = True           # toggle to show output
WARMUP_FRAMES = 10
MAX_FPS_SAMPLES = 160

# ---------- GLOBAL ----------
fps_queue = deque(maxlen=MAX_FPS_SAMPLES)
running = True

# ---------- FRAME PRODUCER ----------
def camera_loop(handler: ModelHandler):
    global running
    cap = cv2.VideoCapture(CAM_INDEX)
    if not cap.isOpened():
        print("[ERROR] Cannot open camera.")
        return

    frame_count = 0
    t_last = time.time()

    while running:
        ret, frame = cap.read()
        if not ret:
            continue

        frame_count += 1
        handler.push_frame(frame)

        # Optional display
        if SHOW_WINDOW:
            annotated = getattr(handler, "last_annotated", frame)
            fps_text = f"FPS: {get_fps():.2f}"
            cv2.putText(annotated, fps_text, (10, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
            cv2.imshow("Realtime Inference", annotated)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        # FPS calc
        now = time.time()
        fps = 1.0 / (now - t_last)
        t_last = now
        fps_queue.append(fps)

    cap.release()
    cv2.destroyAllWindows()
    print("[INFO] Camera loop stopped.")

# ---------- FPS UTIL ----------
def get_fps():
    if len(fps_queue) == 0:
        return 0.0
    return sum(fps_queue) / len(fps_queue)

# ---------- CALLBACKS ----------
def on_result(detected, annotated):
    handler.last_detected = detected
    handler.last_annotated = annotated

def on_done(reason):
    print(f"[INFO] Validation ended with reason: {reason}")

# ---------- MAIN ----------
if __name__ == "__main__":
    expected = task_select(TASK_ID)
    handler = ModelHandler(timeout_seconds=9999, interval_ms=1)
    handler.initialize_model()

    # Connect signals manually (non-Qt runtime)
    handler.result_ready.connect(on_result)
    handler.validation_done.connect(on_done)

    handler.start_validation({"task": TASK_ID}, expected)

    # Start camera thread
    cam_thread = threading.Thread(target=camera_loop, args=(handler,), daemon=True)
    cam_thread.start()

    try:
        while cam_thread.is_alive():
            time.sleep(1)
            print(f"Current FPS: {get_fps():.2f}")
    except KeyboardInterrupt:
        running = False
        handler.stop_validation(reason="INTERRUPT")

    running = False
    handler.stop_validation(reason="STOP")
    print(f"[FINAL] Average FPS: {get_fps():.2f}")
