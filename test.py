import cv2
import time

def camera_loop(self):
    """Read frames from camera and send to model."""
    if not self.session_active or not self.io_handler:
        return

    # --- Camera health check ---
    # Camera health check + reconnection support (mockup UI hooks)
    try:
        cap = getattr(self.io_handler, "cap", None)
        cap_opened = callable(getattr(cap, "isOpened", None)) and cap.isOpened()
    except Exception:
        cap_opened = False

    if not cap_opened:
        print("Camera appears disconnected.")

        # Inform UI (mockup functions to be implemented in integrated UI)
        if hasattr(self.ui, "show_camera_disconnected"):
            try:
                self.ui.show_camera_disconnected()
            except Exception as e:
                print(f"UI show_camera_disconnected failed: {e}")

        # simple reconnect counter stored on the controller instance
        self._reconnect_attempts = getattr(self, "_reconnect_attempts", 0) + 1
        max_retries = 3

        if self._reconnect_attempts <= max_retries:
            print(f"Attempting camera reconnect (attempt {self._reconnect_attempts}/{max_retries})")
        try:
            if self.io_handler.open_camera(retry=True):
                print("Camera reconnect successful.")
                self._reconnect_attempts = 0
            if hasattr(self.ui, "hide_camera_disconnected"):
                try:
                    self.ui.hide_camera_disconnected()
                except Exception as e:
                    print(f"UI hide_camera_disconnected failed: {e}")
            else:
                # Give other event loop work a chance; return to retry on next tick
                return
        except Exception as e:
            print(f"Reconnect attempt failed: {e}")
            return
        else:
            print("Camera permanently disconnected after retries.")
        self._reconnect_attempts = 0
        if hasattr(self.ui, "show_camera_failed"):
            try:
                self.ui.show_camera_failed()
            except Exception:
                pass
        self.stop_task("CAMERA_DISCONNECTED")
        self.full_reset()
        return

    frame = self.io_handler.read_frame()
    if frame is None:
        return

    try:
        # frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        resized = cv2.resize(frame, (976, 725))
        self.model_handler.push_frame(resized)
        # --- Save Image every 3 seconds to "data" folder ---
        current_time = time.time()
        if current_time - self.last_image_save_time >= self.image_save_interval:
            try:
                # Use IOHandler's existing function (it auto-creates folder)
                self.io_handler.save_image_direct(
                    resized,
                    folder_prefix="data",
                    emp_id=getattr(self.ui, "current_emp_id", "Unknown"),
                )
                self.last_image_save_time = current_time
            except Exception as e:
                print(f"Interval image save failed: {e}")
                MockIOHandler.open_camera(self, retry=True)
                time.sleep(0.1)

    except Exception as e:
        print(f"Camera loop error: {e}")

# Mock classes for manual testing
class MockIOHandler:
    def __init__(self):
        self.cap = cv2.VideoCapture(0)

    def open_camera(self, retry=False):
        if not self.cap.isOpened():
            self.cap.open(0)
        return self.cap.isOpened()

    def read_frame(self):
        ret, frame = self.cap.read()
        return frame if ret else None

    def save_image_direct(self, image, folder_prefix, emp_id):
        filename = f"{folder_prefix}/{emp_id}_image.jpg"
        print(f"Image saved to {filename}")

class MockUI:
    def __init__(self):
        self.current_emp_id = "12345"

    def show_camera_disconnected(self):
        print("UI: Camera disconnected.")

    def hide_camera_disconnected(self):
        print("UI: Camera reconnected.")

class MockModelHandler:
    def push_frame(self, frame):
        print("Frame pushed to model handler.")

class MockSelf:
    def __init__(self):
        self.session_active = True
        self.io_handler = MockIOHandler()
        self.ui = MockUI()
        self.model_handler = MockModelHandler()
        self.last_image_save_time = 0
        self.image_save_interval = 3

if __name__ == "__main__":
    mock_self = MockSelf()
    try:
        while True:
            camera_loop(mock_self)
            time.sleep(0.1)  # Simulate a loop delay
    except KeyboardInterrupt:
        print("Exiting...")
        if mock_self.io_handler.cap.isOpened():
            mock_self.io_handler.cap.release()