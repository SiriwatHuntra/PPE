# Main.py (Refactored startup)
import logging
import sys
import os
from LogHandler import init_logger

logger = init_logger("Application  ")

# ------------------ 1. Load ONNX first ------------------
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

try:
    # logging.basicConfig(level=logging.INFO)
    logging.info("Loading ONNX model before PyQt startup...")
    from Model.Model_optimize import load_model
    load_model()
    logging.info("ONNX model initialized successfully.")
except Exception as e:
    logging.error(f"Failed to load ONNX model: {e}")
    sys.exit(1)

# ------------------ 2. Then import PyQt and modules ------------------
from PyQt5 import QtWidgets
from UI import MainApp
from IO import IOHandler

# ------------------ 3. Start application ------------------
def main():
    app = QtWidgets.QApplication(sys.argv)

    # Initialize UI
    window = MainApp()
    logic = window.logic   # LogicController already created inside MainApp

    # Initialize IO handler
    io = IOHandler()
    io.init_serial()
    io.start_rfid_thread()
    io.init_adam()                
    io.start_emergency_monitor()  
    io.summary_text.connect(window.set_summary_text)
    # Connect signals
    io.rfid_detected.connect(logic.rfid_event)

    # Keep a reference for clean exit
    logic.io_handler = io

    logic.bind_io_signals()                 
    io.open_camera()
    
    window.showFullScreen()
    sys.exit(app.exec_())

# ------------------ 4. Helper ------------------
def closeEvent(self, event):
    logging.info("Application closing.")
    if hasattr(self.logic, "io_handler") and self.logic.io_handler:
        self.logic.io_handler.stop_rfid()
        self.logic.io_handler.release_camera()
    event.accept()

# ------------------ Entry ------------------
if __name__ == "__main__":
    main()
