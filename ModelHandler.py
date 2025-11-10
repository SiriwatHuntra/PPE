# ModelHandler.py
import time
from queue import Queue
from PyQt5 import QtCore
from Model.Model_optimize import load_model, detect_objects, validate_counts

from LogHandler import init_logger

logger = init_logger("Model_Handler")

class ModelHandler(QtCore.QObject):
    """
    Handles ONNX inference and validation logic.
    Controlled entirely by one master timer.
    """
    result_ready = QtCore.pyqtSignal(dict, object)  # detections, annotated image
    validation_done = QtCore.pyqtSignal(str)        # "PASS", "TIMEOUT"

    def __init__(self, timeout_seconds=30, interval_ms=200, parent=None):
        super().__init__(parent)
        self.model_session = None
        self.timeout_seconds = timeout_seconds
        self.interval_ms = interval_ms

        # Thread-safe queue for incoming frames
        self.frame_queue = Queue(maxsize=1)
        self.running = False
        self.task_info = None
        self.expected_items = None
        self.start_time = None

        # One unified timer to manage validation loop + timeout
        self.timer = QtCore.QTimer()
        self.timer.setInterval(self.interval_ms)
        self.timer.timeout.connect(self._loop_step)

    # --------------------- Model Setup ---------------------
    def initialize_model(self):
        """Load ONNX model before UI starts."""
        self.model_session = load_model()
        logger.info("Model loaded successfully.")

    # --------------------- Validation Control ---------------------
    def start_validation(self, task_info: dict, expected_items: dict):
        """Begin new validation session."""
        if self.running:
            return
        self.running = True
        self.task_info = task_info
        self.expected_items = expected_items
        self.start_time = time.time()
        self.timer.start()
        logger.info("Validation started.")

    def stop_validation(self, reason="MANUAL"):
        """Stop validation and clean up."""
        if not self.running:
            return
        self.timer.stop()
        self.running = False
        self.validation_done.emit(reason)
        logger.info(f"Validation stopped ({reason}).")

    def push_frame(self, frame):
        """Receive frame from camera/UI thread."""
        if not self.running:
            return
        if not self.frame_queue.full():
            self.frame_queue.put(frame)

    # --------------------- Internal Loop ---------------------
    def _loop_step(self):
        """Main loop triggered by single timer."""
        if not self.running:
            return

        # Timeout check
        elapsed = time.time() - self.start_time
        if elapsed >= self.timeout_seconds:
            self.stop_validation(reason="TIMEOUT")
            return

        # Frame check
        if not self.frame_queue.empty():
            frame = self.frame_queue.get()
            try:
                detected_items, annotated = detect_objects(frame, self.expected_items)
                status, detected, expected = validate_counts(detected_items, self.expected_items)
                self.last_detected = detected
                self.last_expected = expected
                self.last_status = status

                self.result_ready.emit(detected_items, annotated)
                if status:
                    self.stop_validation(reason="PASS")
                # if not pass yet, just continue looping until timeout
            except Exception as e:
                logger.info(f"Detection error: {e}")

    # --------------------- Manual Reset ---------------------
    def reset(self):
        """Reset for next validation round."""
        self.stop_validation(reason="RESET")
        self.task_info = None
        self.expected_items = None
        self.start_time = None
        with self.frame_queue.mutex:
            self.frame_queue.queue.clear()
        logger.info("Reset complete.")
