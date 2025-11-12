# Logic.py (Final Refactored Version)
import os, time, cv2
from PyQt5 import QtCore
from PyQt5.QtGui import QPixmap, QImage
from ModelHandler import ModelHandler
from LogHandler import write_csv_log, init_logger, write_db_log
# from pyMail import mail2all

logger = init_logger("Processor    ")

class LogicController(QtCore.QObject):
    """
    Central coordinator:
    - Manages ModelHandler (validation + timing)
    - Interfaces with IOHandler (camera, RFID)
    - Updates UI via signals
    """

    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        self.io_handler = None  # injected from Main.py
        self.session_active = False
        self.emergency_active = False

        # ----------------- Model handler -----------------
        self.model_handler = ModelHandler(timeout_seconds=30, interval_ms=200)
        self.model_handler.initialize_model()

        self.model_handler.result_ready.connect(self.handle_result_ready)
        self.model_handler.validation_done.connect(self.handle_validation_done)

        # ----------------- Camera & timers -----------------
        self.camera_timer = QtCore.QTimer()
        self.camera_timer.setInterval(100)
        self.camera_timer.timeout.connect(self.camera_loop)

        self.countdown_timer = QtCore.QTimer()
        self.countdown_timer.setInterval(1000)
        self.countdown_timer.timeout.connect(self._tick_countdown)    

        self.last_image_save_time = 0
        self.image_save_interval = 3
        # ----------------- State -----------------
        self.task_tag = {
            "Chemical Analysis": 1,
            "Solder Ability Test": 2,
            "Thickness Measurement": 3,
            "Group Lead": 4,
            "Manager": 5
        }
        self.current_task = None
        self.expected_items = None
        self._last_annotated = None
        
    def if_not_emergency(func):
        def wrapper(self, *a, **kw):
            if self.emergency_active:
                logger.debug(f"Skipped {func.__name__} during emergency.")
                return
            return func(self, *a, **kw)
        return wrapper
    
    def _stop_timer(self):
        self.camera_timer.stop()
        self.countdown_timer.stop()
        
    # RFID EVENT
    @if_not_emergency
    def rfid_event(self, card_id: str):
        """Triggered by IOHandler when RFID detected."""
        
        logger.info(f"RFID detected: {card_id}")
        self.ui.current_emp_id = card_id
        if hasattr(self.ui, "lblIDcard"):
            self.ui.lblIDcard.setText(f"Emp: {card_id}")

        # Run permission check
        if not self.check_permission(card_id):
            return

    # adjust
    def check_permission(self, card_id: str):
        """Check if scanned RFID card has access permission."""
        from IO import IOHandler  # use your existing IO class
        data = IOHandler.load_json("JsonAsset/TestOperator.json")
        if data is None:
            logger.error("Permission data not found.")
            self.handle_no_permission()
            return False

        match = next((item for item in data if item.get("EmpNo") == card_id), None)
        if match:
            role = (match.get("Position") or "").upper().strip()
            logger.info(f"Access granted for card: {card_id} (role={role})")
            setattr(self.ui, "current_role", role)
            self.handle_operator_access(role)
            return True
        else:
            logger.warning(f"Access denied for card: {card_id}")
            self.handle_no_permission()
            return False

    # TASK MANAGEMENT
    def start_task(self, task_name: str, expected_items: dict):
        """Triggered when user selects a task from menu."""
        all_items = [
            "Cap", "Face_Shield", "Carbon_Mask", "Gas_Mask", "OSL",
            "Clothes", "Glove", "Long_Glove", "Safety_Shoe", "ID_Card", "Yellow_Jacket"
        ]

        logger.info(f"Starting validation for task: {task_name}")
        self.current_task = task_name
        self.expected_items = expected_items

        if not expected_items:
            logger.error(f"No expected PPE items found for task {task_name}")
            return

        # --- Hide overlay first ---
        if hasattr(self.ui, "hide_scan_overlay"):
            self.ui.hide_scan_overlay()

        # --- Hide all PPE items ---
        for name in all_items:
            w = getattr(self.ui, name, None)
            iw = getattr(self.ui, f"img{name}", None)
            if w:
                w.setVisible(False)
            if iw:
                iw.setVisible(False)

        # --- Show and reset only expected PPE items ---
        expected_visible = list(expected_items.keys())
        for name in expected_visible:
            w = getattr(self.ui, name, None)
            iw = getattr(self.ui, f"img{name}", None)
            if w:
                w.setVisible(True)
                w.setStyleSheet(
                    "background:#A9A9A9; border:2px solid black; border-radius:30px;"
                )
            if iw:
                iw.setVisible(True)
        logger.info(f"Visible PPE for {task_name}: {expected_visible}")

        # --- Update category label ---
        if hasattr(self.ui, "lblcategory"):
            self.ui.lblcategory.setText(task_name)

        # --- Show reference image ---
        ref_map = {
            "Chemical Analysis": "asset/Reference/Chemical_Analysis.png",
            "Solder Ability Test": "asset/Reference/Solder_Ability_Test.png",
            "Thickness Measurement": "asset/Reference/Thickness_Measurement.png",
            "Group Lead": "asset/Reference/Group_Lead.png",
            "Manager": "asset/Reference/ManagerM.png",
        }
        ref_path = ref_map.get(task_name)
        try:
                if ref_path and os.path.exists(ref_path):
                    pix = QPixmap(ref_path)
                    self.ui.Reflabel.setPixmap(pix)
                    self.ui.Reflabel.setVisible(True)
        except Exception as e:
            logger.debug(f"Reference load failed: {e}")

        # --- Open camera and start validation ---
        if not self.io_handler or not self.io_handler.open_camera():
            logger.error("Failed to open camera for validation.")
            return
        self.io_handler.start_validation_camera_monitor(self)  # <--- start monitor
        self.model_handler.start_validation(
            task_info={"task": task_name}, expected_items=expected_items
        )

        self.camera_timer.start()
        self.countdown_timer.start()
        self.session_active = True

    # adjust
    def handle_operator_access(self, role: str):
        """When operator has permission — show menu with limited buttons."""
        if hasattr(self.ui, "hide_scan_overlay"):
            self.ui.hide_scan_overlay()
        if self.io_handler:
            self.io_handler.stop_rfid()
        if hasattr(self.ui, "menu_window") and hasattr(self.ui.menu_window, "apply_role"):
            self.ui.menu_window.apply_role(role)
        self.ui.menu_window.show()

    def handle_no_permission(self):
        """When operator has no permission — show warning."""
        if hasattr(self.ui, "labelIDCard"):
            self.ui.labelIDCard.setText("Access Denied")
        logger.info("Unauthorized card scanned — denied access.")
        QtCore.QTimer.singleShot(4000, self.ui.show_scan_overlay)

    @if_not_emergency
    def stop_task(self, reason: str):
        """Stop current validation session."""
        if not self.session_active:
            return
        logger.info(f"Stopping task — reason: {reason}")
        self.session_active = False
        self._stop_timer()
        self.model_handler.stop_validation(reason)
        if self.io_handler:
            self.io_handler.release_camera()
            self.io_handler.stop_validation_camera_monitor()


    # ----------------------------------------------------
    # CAMERA LOOP (FRAME PROVIDER)
    # ----------------------------------------------------
    def camera_loop(self):
        """Read frames from camera and send to model."""
        if not self.session_active or not self.io_handler:
            return

        # --- Camera health check ---
        if not (self.io_handler.cap and self.io_handler.cap.isOpened()):
            if not self.io_handler.open_camera(retry=True):
                logger.error("Camera lost...")
                self.stop_task("CAMERA_DISCONNECTED")
                self.full_reset()
                return

        frame = self.io_handler.read_frame()
        if frame is None:
            return

        try:
            #frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            resized = cv2.resize(frame, (976, 725))
            self.model_handler.push_frame(resized)
            # --- Save Image every 3 seconds to "dara" folder ---
            current_time = time.time()
            if current_time - self.last_image_save_time >= self.image_save_interval:
                try:
                    # Use IOHandler"z existing function (it auto-creates folder)
                    self.io_handler.save_image_direct(resized,folder_prefix ="data",emp_id=getattr(self.ui, "current_emp_id", "Unknown"))
                    self.last_image_save_time = current_time
                except Exception as e:
                    logger.error(f"Interval image save failed: {e}")
        except Exception as e:
            logger.error(f"Camera loop error: {e}")

    # ----------------------------------------------------
    # SIGNAL HANDLERS FROM MODELHANDLER
    # ----------------------------------------------------
    def handle_result_ready(self, detected_items: dict, annotated_img):
        """Update live camera preview and PPE visuals."""
        self._last_annotated = annotated_img

        # --- Update preview ---
        try:
            rgb = cv2.cvtColor(annotated_img, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            qt_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_img)
            self.ui.pixmap_item.setPixmap(pixmap)
        except Exception as e:
            logger.error(f"Display update failed: {e}")

        # --- Update PPE visuals (colors + counts) ---
        self.update_ppe_visuals(detected_items)

    @if_not_emergency
    def handle_validation_done(self, status: str):
        """Handle PASS / TIMEOUT event from ModelHandler."""
        logger.info(f"Validation complete — status: {status}")
        self._stop_timer()
        self.session_active = False
        detected = getattr(self.model_handler, "last_detected", {}) or {}
        expected = getattr(self.model_handler, "last_expected", {}) or {}
        if self.io_handler:
            self.io_handler.stop_validation_camera_monitor()

        # Show summary
        if hasattr(self.ui, "show_summary"):
            self.ui.show_summary(status)
            # If pass door will open
            if status == "PASS":                
                self.io_handler.open_door()
                QtCore.QTimer.singleShot(4000, self.full_reset)    

            else:
                QtCore.QTimer.singleShot(4000, self.full_reset)

        # Save image
        if self.io_handler:
            if self._last_annotated is not None:
                self.io_handler.save_image_direct(self._last_annotated,
                                                  folder_prefix=status.lower(),
                                                  emp_id=self.ui.current_emp_id)
            else:
                self.io_handler.save_image_direct(folder_prefix=status.lower(),
                                           emp_id=self.ui.current_emp_id)
        
        if status == "TIMEOUT" and self.expected_items:
            self.ui.MessageTime.setVisible(True)            # add
            missing_items = {
                k: v - detected.get(k, 0)
                for k, v in expected.items()
                if detected.get(k, 0) < v
            }
            missing_str = "; ".join(f"{k}:{v}" for k, v in missing_items.items()) if missing_items else "NONE"
        else:
            missing_str = "NONE"
        write_csv_log(
            "Validate",
            id=self.ui.current_emp_id,
            task=self.current_task or "Unknown",
            status=status,
            missing=missing_str
        )
        csv_info = write_csv_log(
            "Validate",
            id=self.ui.current_emp_id,
            task=self.current_task or "Unknown",
            status=status,
            missing=missing_str
        )
        ts = csv_info["timestamp"]

        image_path = None
        if hasattr(self.io_handler, "last_saved_path"):
            image_path = self.io_handler.last_saved_path
        elif hasattr(self, "_last_annotated") and self._last_annotated is not None:
            tmp_path = f"log/temp_{self.ui.current_emp_id}_{status}.jpg"
            cv2.imwrite(tmp_path, self._last_annotated)
            image_path = tmp_path
        write_db_log(
            server="172.16.0.102",
            user="system",
            password="p@$$w0rd",
            database="APCSProDB",
            table="[DBx].[dbo].[PL_PPE]",
            record_at=ts,
            opno=self.ui.current_emp_id,
            enties_of_task=(self.current_task or "Unknown"),
            status=status,
            image_path=image_path
        )
        if hasattr(self.ui, "update_task_totals"):
            self.ui.update_task_totals()
        

    # UI HELPERS
    # ----------------------------------------------------
    def update_ppe_visuals(self, detected):
        expected = self.expected_items or {}
        good = ng = 0
        for name, _ in expected.items():
            tw, iw = getattr(self.ui, name, None), getattr(self.ui, f"img{name}", None)
            if not tw or not iw: continue
            found = name in detected
            tw.setStyleSheet(f"background-color:{'lightgreen' if found else 'lightcoral'};"
                            f"border:2px solid {'green' if found else 'red'};border-radius:30px;")
            iw.setVisible(True)
            good += found
            ng += not found
        for lbl, val in (("lblGood", good), ("lblNG", ng), ("lblTotal", good+ng)):
            if hasattr(self.ui, lbl): getattr(self.ui, lbl).setText(f"{lbl[3:]} : {val}")

    def _tick_countdown(self):
        """Mirror ModelHandler's timer to UI display."""
        if not self.model_handler.start_time:
            return
        remain = max(0, int(self.model_handler.timeout_seconds -
                            (time.time() - self.model_handler.start_time)))
        if hasattr(self.ui, "Countnum"):
            self.ui.Countnum.display(remain)
    
    def full_reset(self, delay=1000):
        """Reset model, camera, and UI after validation or manual stop."""
        if self.emergency_active:
            logger.debug("Skip full_reset during emergency.")
            return

        self.model_handler.reset()
        if self.io_handler:
            self.io_handler.release_camera()
        
        QtCore.QTimer.singleShot(delay, self._post_reset)


    def _post_reset(self):
        """Handle UI cleanup and restart RFID after reset delay."""
        # --- Clear visuals ---
        for n in ("labelsummary", "imgsummary", "MessageTime", "labelEmergency", "imgEmergency"):
            w = getattr(self.ui, n, None)
            if w:
                w.setVisible(False)

        # --- Reset PPE counters and text ---
        for lbl in ("lblGood", "lblNG", "lblTotal"):
            if hasattr(self.ui, lbl):
                getattr(self.ui, lbl).setText(f"{lbl[3:]} : 0")
        if hasattr(self.ui, "lblcategory"):
            self.ui.lblcategory.setText("Section")
        if hasattr(self.ui, "Reflabel"):
            self.ui.Reflabel.clear()
        if hasattr(self.ui, "Countnum"):
            self.ui.Countnum.display(30)

        # --- Show idle overlay ---
        if hasattr(self.ui, "show_scan_overlay"):
            self.ui.show_scan_overlay()
        if hasattr(self.ui, "lblIDcard"):
            self.ui.lblIDcard.setText("ID Card")

        # --- Restart RFID ---
        if self.io_handler:
            QtCore.QTimer.singleShot(1000, self.io_handler.start_rfid_thread)

        logger.info("System fully reset and ready for next scan.")


    # ----------------------------------------------------
    # EMERGENCY HELPER
    # ----------------------------------------------------
    def bind_io_signals(self):
        if not self.io_handler:
            return
        self.io_handler.emergency_triggered.connect(self.handle_emergency_trigger)
        self.io_handler.emergency_cleared.connect(self.handle_emergency_clear)

    @QtCore.pyqtSlot()
    def handle_emergency_trigger(self):
        logger.warning("EMERGENCY triggered — performing full reset")
        self.emergency_active = True

        # --- Close Task Select window if it's open ---
        try:
            if hasattr(self.ui, "menu_window") and self.ui.menu_window.isVisible():
                self.ui.menu_window.close()
                logger.info("Task select window closed due to emergency.")
        except Exception as e:
            logger.error(f"Failed to close menu window: {e}")

        # --- Stop all active loops ---
        try:
            self._stop_timer()
        except Exception:
            pass

        # --- Stop model validation completely ---
        try:
            self.model_handler.stop_validation("EMERGENCY")
            self.model_handler.reset()
        except Exception:
            pass

        # --- Stop IO devices ---
        if self.io_handler:
            try:
                self.io_handler._emergency_mode = True
                self.io_handler.stop_rfid()
                self.io_handler.release_camera()
                self.io_handler._emg_open()
            except Exception:
                pass

        # --- Reset UI immediately ---
        if hasattr(self.ui, "show_emergency"):
            self.ui.show_emergency()
        # add
        if hasattr(self.ui, "blink_emergency"):
            self.ui.blink_emergency()

        try: 
            # mail2all("Emergency", "PPE detection", "Emergency button pushed")
            print("mock up mail send")
        except:
            logger.info("Fail to active email sender")

    @QtCore.pyqtSlot()
    def handle_emergency_clear(self):
        if not self.emergency_active: 
            logger.debug("Ignore redundant emergency_clear signal.")
            return
        logger.info("Emergency cleared — restarting system")
        self.emergency_active = False

        if self.io_handler:
            try:
                self.io_handler._emergency_mode = False
                #self.io_handler.close_door()
                self.io_handler.start_rfid_thread()
            except Exception:
                pass

        # Bring UI back to idle (same as startup)
        # if self.session_active or getattr(self.ui, "labelsummary", None):
        #     self.full_reset()
        if hasattr(self.ui, "emergency_timer"):
            self.ui.emergency_timer.stop()
        if hasattr(self.ui, "hide_emergency"):
            self.ui.hide_emergency()
        QtCore.QTimer.singleShot(200, self.ui.show_scan_overlay)
