# UI.py (Refactored)
from PyQt5 import QtCore, QtWidgets, QtGui, uic
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QGraphicsScene, QGraphicsPixmapItem

from Logic import LogicController
from chart import init_bar_chart, update_bar_chart
from LogHandler import init_logger, read_log_summary, read_db_total_current_year, read_db_entry_date

logger = init_logger("Interface    ")

class MainApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi("asset/Scandisplay_without_label_IDC.ui", self)
        self.setWindowTitle("Scandisplay")

        # Scene setup for live camera display
        self.scene = QGraphicsScene()
        self.cameraview.setScene(self.scene)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        # UI state
        self.cap = None
        self.current_emp_id = None
        self.first_image_saved = False

        # Controller setup
        self.logic = LogicController(self)
        self.menu_window = Menu()
        self.connect_signals()
        
        # UI default view
        self.labelsummary.setVisible(False)
        self.imgsummary.setVisible(False)
        self.MessageTime.setVisible(False)
        self.labelIDCard.setAlignment(Qt.AlignCenter)

        # Add UI Dashboard
        init_bar_chart(self.GraphEoD, y_max=40)
        self.refresh_eod_chart(days=7, y_max=40)

        # in MainApp.__init__ after UI is set up
        self._clock_timer = QtCore.QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._update_datetime)
        self._clock_timer.start()
        self._update_datetime()  # prime once
        self.update_task_totals()  # update count of Entry        
        logger.info("UI initialized and ready.")

        if hasattr(self, "closebutton"):
            self.closebutton.clicked.connect(self.trigger_close)
            self.closebutton.setVisible(True)
            
        if hasattr(self.logic, "io") and hasattr(self.logic.io, "summary_text"):
            self.logic.io.summary_text.connect(self.set_summary_text)

    # ---------------- SIGNAL CONNECTIONS ----------------
    def connect_signals(self):
        """Connect menu and controller signals."""
        self.menu_window.choice_made.connect(self.handle_menu_choice)

    def handle_menu_choice(self, choice: str):
        if choice == "CANCEL":
            logger.info("Task selection CANCELled — returning to idle.")
            self.logic.full_reset()
            return

        """User selected a task from menu."""
        
        # Load expected task configuration
        from Model.Model_optimize import task_select
        expected_items = task_select(self.logic.task_tag.get(choice))
        if expected_items:
            self.logic.start_task(choice, expected_items)
        else:
            logger.error(f"No expected items found for {choice}")

    # ---------------- APP EVENTS ----------------
    def closeEvent(self, event):
        logger.info("Application closed by user.")
        if self.cap:
            self.cap.release()
        event.accept()
    
    # adjust
    def _update_datetime(self):
        try:
            if hasattr(self, "DateTim"):
                now = QtCore.QDateTime.currentDateTime()
                year = now.date().year()
                if hasattr(self, "DateTim") and isinstance(self.DateTim, QtWidgets.QDateTimeEdit):
                    self.DateTim.setDateTime(now)
                if not hasattr(self, "_last_year") or self._last_year != year:
                    self._last_year = year
                    self.update_task_totals()
        except Exception as e:
            logger.error(f"_update_datetime failed: {e}", exc_info=True)

    # --- UI helpers to react to logic events ---
    # adjust
    def show_scan_overlay(self):
        """Show 'Please Scan Card' screen."""
        self.labelIDCard.setText("Please Scan ID Card")
        self.labelIDCard.setVisible(True)
        self.imglabel.setVisible(True)
        self.Dashboard.setVisible(True)
        self.PL_PPE.setVisible(True)
        self.labelTotalEnt.setVisible(True)
        self.totalEnt.setVisible(True)
        self.labelEoD.setVisible(True)
        self.GraphEoD.setVisible(True)
        self.labelsummary.setVisible(False)
        self.imgsummary.setVisible(False)
        self.MessageTime.setVisible(False)
        if hasattr(self, "labelEmergency"):
            self.labelEmergency.setVisible(False)
        if hasattr(self, "imgEmergency"):
            self.imgEmergency.setVisible(False)
        if hasattr(self, "labelRFID"):
            self.labelRFID.setVisible(False)
        if hasattr(self, "imgRFID"):
            self.imgRFID.setVisible(False)
        if hasattr(self, "labelADAM"):
            self.labelADAM.setVisible(False)
        if hasattr(self, "imgADAM"):
            self.imgADAM.setVisible(False)


    # addjust
    def hide_scan_overlay(self):
        """Hide 'Please Scan Card' overlay when RFID detected."""
        self.labelIDCard.setVisible(False)
        self.imglabel.setVisible(False)
        self.Dashboard.setVisible(False)
        self.PL_PPE.setVisible(False)
        self.labelTotalEnt.setVisible(False)
        self.totalEnt.setVisible(False)
        self.labelEoD.setVisible(False)
        self.GraphEoD.setVisible(False)

    def show_summary(self, status: str):
        """Display PASS/FAIL/TIMEOUT summary."""
        color_map = {
            "PASS": "#228B22",
            "FAIL": "#800000",
            "TIMEOUT": "#808080"
        }
        image_map = {
            "PASS": "asset/Image/pass.png",
            "FAIL": "asset/Image/fail.png",
            "TIMEOUT": "asset/Image/timeout.png"
        }

        color = color_map.get(status, "#808080")
        image_path = image_map.get(status)
        self.labelsummary.setText(status)
        self.labelsummary.setStyleSheet(
            f"background:{color}; border-radius: 80px; color:white; padding-top: 280px;"
        )
        self.labelsummary.setVisible(True)
        pixmap = QtGui.QPixmap(image_path).scaled(250, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.imgsummary.setPixmap(pixmap)
        self.imgsummary.setVisible(True)

    @QtCore.pyqtSlot(str)
    def set_summary_text(self, text: str):
        """Show/Hide summary banner text from IO events."""
        if not hasattr(self, "labelRFID"):
            return
        if text == "RFID_disconnect":
            if hasattr(self, "labelRFID"):
                self.labelRFID.setText("RFID Not Found . . . .\nโปรดตรวจสอบอุปกรณ์ RFID \nเชื่อมต่อกับคอมพิวเตอร์")
                self.labelRFID.setAlignment(Qt.AlignCenter)
                self.labelRFID.setVisible(True)
                self.labelRFID.setStyleSheet("background:#DAA520; color:white; padding-top:460px;")
            if hasattr(self, "imgRFID"):
                connect_image_path = "asset/Image/connect.png"
                self.imgRFID.setPixmap(QtGui.QPixmap(connect_image_path))
                self.imgRFID.setScaledContents(True)
                self.imgRFID.setVisible(True)
        elif text == "RFID_reconnect":
            if hasattr(self, "labelRFID"):
                self.labelRFID.setText("RFID Connected")
                self.labelRFID.setAlignment(Qt.AlignCenter)
                self.labelRFID.setStyleSheet("background:#228B22; color:white; padding-top:460px;")
                self.labelRFID.setVisible(True)
                QtCore.QTimer.singleShot(2000, lambda: self.labelRFID.setVisible(False))
            if hasattr(self, "imgRFID"):
                icon_path = "asset/Image/checked.png" 
                self.imgRFID.setPixmap(QtGui.QPixmap(icon_path))
                self.imgRFID.setScaledContents(True)
                self.imgRFID.setVisible(True)
                QtCore.QTimer.singleShot(2000, lambda: self.imgRFID.setVisible(False))       
        elif text == "ADAM_disconnect":
            if hasattr(self, "labelADAM"):
                self.labelADAM.setText("ADAM Not Found . . . .\nโปรดตรวจสอบอุปกรณ์ ADAM \nเชื่อมต่อคอมพิวเตอร์")
                self.labelADAM.setAlignment(Qt.AlignCenter)
                self.labelADAM.setStyleSheet("background:#DAA520; color:white; padding-top:580px;")
                self.labelADAM.setVisible(True)
            if hasattr(self, "imgADAM"):
                icon_path = "asset/Image/connect.png"  
                self.imgADAM.setPixmap(QtGui.QPixmap(icon_path))
                self.imgADAM.setScaledContents(True)
                self.imgADAM.setVisible(True)
        elif text == "ADAM_reconnect":
            if hasattr(self, "labelADAM"):
                self.labelADAM.setText("ADAM Connected")
                self.labelADAM.setAlignment(Qt.AlignCenter)
                self.labelADAM.setStyleSheet("background:#228B22; color:white; padding-top:580px;")
                self.labelADAM.setVisible(True)
                QtCore.QTimer.singleShot(2000, lambda: self.labelADAM.setVisible(False))
            if hasattr(self, "imgADAM"):
                icon_path = "asset/Image/checked.png" 
                self.imgADAM.setPixmap(QtGui.QPixmap(icon_path))
                self.imgADAM.setScaledContents(True)
                self.imgADAM.setVisible(True)
                QtCore.QTimer.singleShot(2000, lambda: self.imgADAM.setVisible(False))

    def emergency(self):
        image_path = "asset/Image/Emergency.png"
        self.labelEmergency.setText("!!! EMERGENCY !!!")
        self.labelEmergency.setStyleSheet(
            "background: #8B0000; color:white; padding-top: 380px;"
        )
        self.labelEmergency.setVisible(True)
        pixmap = QtGui.QPixmap(image_path).scaled(571, 481, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.imgEmergency.setPixmap(pixmap)
        self.imgEmergency.setVisible(True)
   
    def hide_emergency(self):
        if hasattr(self, "labelEmergency"):
            self.labelEmergency.setVisible(False)
        if hasattr(self, "imgEmergency"):
            self.imgEmergency.setVisible(False)
        if hasattr(self, "labelRFID"): 
            self.labelRFID.setVisible(False)
        if hasattr(self, "imgRFID"):   
            self.imgRFID.setVisible(False)
        if hasattr(self, "labelADAM"): 
            self.labelADAM.setVisible(False)
        if hasattr(self, "imgADAM"):   
            self.imgADAM.setVisible(False)

    def blink_emergency(self):
        if hasattr(self, "emergency_timer") and self.emergency_timer.isActive():
            return

        self.blink_state = True
        self.emergency_timer = QTimer()
        self.emergency_timer.setInterval(500)  
        self.emergency_timer.timeout.connect(self.toggle_emergency_blink)
        self.emergency_timer.start()

    def toggle_emergency_blink(self):
        if hasattr(self, "labelEmergency") and self.labelEmergency.isVisible():
            self.blink_state = not self.blink_state
            self.labelEmergency.setVisible(self.blink_state)
            if hasattr(self, "imgEmergency"):
                self.imgEmergency.setVisible(self.blink_state)
        else:
            if hasattr(self, "emergency_timer"):
                self.emergency_timer.stop()

    def show_emergency(self):
        """Show red EMERGENCY banner + emergency image on imgsummary."""
        self.emergency()
        if hasattr(self, "labelEmergency"): 
            self.labelEmergency.raise_()
        if hasattr(self, "imgEmergency"):   
            self.imgEmergency.raise_()
        if hasattr(self, "hide_scan_overlay"): 
            self.hide_scan_overlay()
        for n in ("labelRFID","imgRFID","labelADAM","imgADAM"):
            w = getattr(self, n, None)
            if w: w.setVisible(False)

    def trigger_close(self):
        """Handle manual close button click."""
        self.close()
    
    def show_camera_error(self, msg):
        from PyQt5.QtWidgets import QMessageBox
        self._cam_popup = QMessageBox(QMessageBox.Warning, "Camera Error", msg, parent=self)
        self._cam_popup.setStandardButtons(QMessageBox.NoButton)
        self._cam_popup.show()

    def hide_camera_error(self):
        if hasattr(self, "_cam_popup") and self._cam_popup:
            self._cam_popup.close()
            self._cam_popup = None

    # --- inside class MainApp (UI.py) ---
    def get_totals_from_summary(self, days_back=365):
        result = read_log_summary(days_back=days_back)
        return {
            "Chemical Analysis": result.get("Chemical Analysis", 0),
            "Solder Ability Test": result.get("Solder Ability Test", 0),
            "Thickness Measurement": result.get("Thickness Measurement", 0),
        }
        
    # add
    # update task total in current year
    def update_task_totals(self):
        totals = self.get_totals_from_summary(days_back=365)
        self.Total_chemical.setText("Chemical Analysis : " + str(totals["Chemical Analysis"]))
        self.Total_solder.setText("Solder Ability Test: " + str(totals["Solder Ability Test"]))
        self.Total_thickness.setText("Thickness Measuerment : " + str(totals["Thickness Measurement"]))

        try:
            total_pass_year = read_db_total_current_year(
                server="172.16.0.102",
                user="system",
                password="p@$$w0rd",
                database="APCSProDB",
                table="[DBx].[dbo].[PL_PPE]"
            )
            if hasattr(self, "totalEnt"):
                self.totalEnt.setText(str(total_pass_year))
            self.refresh_eod_chart(days=7, y_max=40)
        except Exception as e:
            logger.error(f"update totalEnt (year) failed: {e}", exc_info=True)
    
    # add
    # refresh dashboard
    def refresh_eod_chart(self, days=7, y_max=40):
        try:
            rows = read_db_entry_date(
                server="172.16.0.102",
                user="system",
                password="p@$$w0rd",
                database="APCSProDB",
                table="[DBx].[dbo].[PL_PPE]",
                days=days
            )

            dates = [r[0].strftime("%d-%m") for r in rows] if rows else []
            counts = [r[1] for r in rows] if rows else []

            update_bar_chart(self.GraphEoD, dates, counts, y_max=y_max)

        except Exception as e:
            logger.error(f"refresh_eod_chart failed: {e}", exc_info=True)



class Menu(QtWidgets.QMainWindow):
    choice_made = QtCore.pyqtSignal(str)
    close_requested = QtCore.pyqtSignal()
    
    def __init__(self):
        
        super().__init__()
        uic.loadUi("asset/SelectMenu.ui", self)
        self.setWindowTitle("Select Menu")
        
        #set before take choice
        
        self.btnCA.clicked.connect(lambda: self.emit_choice("Chemical Analysis"))
        self.btnSAT.clicked.connect(lambda: self.emit_choice("Solder Ability Test"))
        self.btnTM.clicked.connect(lambda: self.emit_choice("Thickness Measurement"))
        self.btnGL.clicked.connect(lambda: self.emit_choice("Group Lead"))
        self.btnMGR.clicked.connect(lambda: self.emit_choice("Manager"))


        if hasattr(self, "closebtnSelect"):
            self.closebtnSelect.clicked.connect(self.trigger_closeMenu)
            self.closebtnSelect.setVisible(True)
        
    # add
    def apply_role(self, role: str):
        """Enable only buttons allowed by position."""
        role = role.upper().strip()
        btns = {
            "Chemical Analysis": self.btnCA,
            "Solder Ability Test": self.btnSAT,
            "Thickness Measurement": self.btnTM,
            "Group Lead": self.btnGL,
            "Manager": self.btnMGR,
        }

        # Enable first
        for b in btns.values():
            b.setEnabled(False)

        # Enable for position
        if role == "M":
            btns["Manager"].setEnabled(True)
        elif role == "GL":
            btns["Group Lead"].setEnabled(True)
        elif role == "O":
            btns["Chemical Analysis"].setEnabled(True)
            btns["Thickness Measurement"].setEnabled(True)
            btns["Solder Ability Test"].setEnabled(True)

    def emit_choice(self, choice: str):
        self.choice_made.emit(choice)
        self.close()

    def closeEvent(self, event):
        """If closed manually, treat as CANCEL."""
        event.accept()

    def trigger_closeMenu(self):
        """Handle manual close button click."""
        self.close()
        self.emit_choice("CANCEL")



