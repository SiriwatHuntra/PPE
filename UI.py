# UI.py (Refactored)
from PyQt5 import QtCore, QtWidgets, QtGui, uic
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QGraphicsScene, QGraphicsPixmapItem

from Logic import LogicController
from LogHandler import init_logger
from chart import init_bar_chart, update_bar_chart
from LogHandler import read_log_summary, read_db_total_current_year, read_db_entry_date

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
                self.DateTim.setDateTime(now)
                year = now.date().year()
                if getattr(self, "_last_year", None) != year:
                    self._last_year = year
                    self.update_task_totals()
        except Exception:
            pass

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
            "TIMEOUT": "#808080",
            "EMERGENCY": "#8B0000"
        }
        image_map = {
            "PASS": "asset/Image/pass.png",
            "FAIL": "asset/Image/fail.png",
            "TIMEOUT": "asset/Image/timeout.png",
            "EMERGENCY": "asset/Image/Emergency.png"
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
        if not hasattr(self, "labelsummary"):
            return
        if text:
            self.labelsummary.setText(text)
            self.labelsummary.setStyleSheet(
                "background:#DAA520; border-radius:80px; color:white; padding-top:280px; font-size:50px;"
            )
            self.labelsummary.setVisible(True)
            reconnect_image_path = "asset/Image/connect.png"
            self.imgsummary.setPixmap(QtGui.QPixmap(reconnect_image_path))
            self.imgsummary.setScaledContents(True)
            self.imgsummary.setVisible(True)
        else:
            self.labelsummary.setVisible(False)
            self.imgsummary.setVisible(False)

    
    def show_emergency(self):
        """Show red EMERGENCY banner + emergency image on imgsummary."""
        self.show_summary("EMERGENCY")

        if hasattr(self, "labelIDCard"):
            self.labelIDCard.setVisible(False)
        if hasattr(self, "Dashboard"):
            self.Dashboard.setVisible(False)
        if hasattr(self, "PL_PPE"):
            self.PL_PPE.setVisible(False)
        if hasattr(self, "labelTotalEnt"):
            self.labelTotalEnt.setVisible(False)
        if hasattr(self, "totalEnt"):
            self.totalEnt.setVisible(False)
        if hasattr(self, "labelEoD"):
            self.labelEoD.setVisible(False)
        if hasattr(self, "GraphEoD"):
            self.GraphEoD.setVisible(False)
        if hasattr(self, "imglabel"):
            self.imglabel.setVisible(False)

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
            logger.error(f"update totalEnt (year) failed: {e}")
    
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
            logger.error(f"refresh_eod_chart failed: {e}")



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



