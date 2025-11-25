# UI.py (Refactored)
from PyQt5 import QtCore, QtWidgets, QtGui, uic
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QGraphicsScene, QGraphicsPixmapItem, QMessageBox

from Logic import LogicController
from LogHandler import init_logger, read_last_7_days_by_task_from_db, read_db_total_today, read_today_summary, read_db_total_month, read_pass_timeout_from_db
from chart import init_bar_chart, update_bar_chart_by_task, init_pie_chart, update_pie_chart
from Model.Model_optimize import task_select
from IO import IOHandler

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
        self.closebutton.setEnabled(True)
        
        # UI default view
        self.labelTimeout.setVisible(False)
        self.imgTimeout.setVisible(False)
        self.labelPass.setVisible(False)
        self.imgPass.setVisible(False)
        self.MessageTime.setVisible(False)
        self.Camera_Message.setVisible(False)
        self.labelIDCard.setAlignment(Qt.AlignCenter)

        # UI Dashboard
        init_bar_chart(self.GraphEoD, y_max=40)
        self.refresh_eod_chart(days=7, y_max=40)
        init_pie_chart(self.GraphPie)
        self.refresh_pie_chart()

        # Clock timer
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
            logger.info("Task selection CANCELled – returning to idle.")
            self.logic.full_reset()
            return

        """User selected a task from menu."""
        
        # Load expected task configuration
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
    def show_scan_overlay(self):
        """Show 'Please Scan Card' screen."""
        self.labelIDCard.setText("Please Scan ID Card")
        self.labelIDCard.setVisible(True)
        self.imglabel.setVisible(True)
        self.Dashboard.setVisible(True)
        self.PL_PPE.setVisible(True)
        self.labelTotalEnt.setVisible(True)
        self.totalEnt.setVisible(True)
        self.labelMonth.setVisible(True)
        self.totalMonth.setVisible(True)
        self.labelEoD.setVisible(True)
        self.GraphEoD.setVisible(True)
        self.GraphPie.setVisible(True)
        self.labelTimeout.setVisible(False)
        self.imgTimeout.setVisible(False)
        self.labelPass.setVisible(False)
        self.imgPass.setVisible(False)
        self.MessageTime.setVisible(False)
        self.labelEmergency.setVisible(False)
        self.imgEmergency.setVisible(False)
        self.labelADAM.setVisible(False)
        self.imgADAM.setVisible(False)
        self.labelRFID.setVisible(False)
        self.imgRFID.setVisible(False)

    def hide_scan_overlay(self):
        """Hide 'Please Scan Card' overlay when RFID detected."""
        self.labelIDCard.setVisible(False)
        self.imglabel.setVisible(False)
        self.Dashboard.setVisible(False)
        self.PL_PPE.setVisible(False)
        self.labelTotalEnt.setVisible(False)
        self.totalEnt.setVisible(False)
        self.labelMonth.setVisible(False)
        self.totalMonth.setVisible(False)
        self.labelEoD.setVisible(False)
        self.GraphEoD.setVisible(False)
        self.GraphPie.setVisible(False)

    def show_summary(self, status: str):
        """Display PASS/TIMEOUT summary."""
        color_map = {
            "PASS": "#228B22",
            "TIMEOUT": "#808080"
        }
        image_map = {
            "PASS": "asset/Image/pass.png",
            "TIMEOUT": "asset/Image/timeout.png"
        }

        color = color_map.get(status, "#808080")
        image_path = image_map.get(status)
        if status == "PASS":
            self.labelPass.setText("PASS \n\n Door Open")
            self.labelPass.setStyleSheet(
                f"background:{color}; color:white;"
            )
            self.labelPass.setVisible(True)
            pixmap = QtGui.QPixmap(image_path).scaled(95, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.imgPass.setPixmap(pixmap)
            self.imgPass.setVisible(True)
        
        elif status == "TIMEOUT":
            self.labelTimeout.setText(status)
            self.labelTimeout.setStyleSheet(
                f"background:{color}; border-radius: 80px; color:white; padding-top: 280px;"
            )
            self.labelTimeout.setVisible(True)
            pixmap = QtGui.QPixmap(image_path).scaled(250, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.imgTimeout.setPixmap(pixmap)
            self.imgTimeout.setVisible(True)

    @QtCore.pyqtSlot(str)
    def set_summary_text(self, text: str):
        """Show/Hide summary banner text from IO events."""
        # print("get summary text",text)
        if text == "RFID_disconnect":
            if hasattr(self, "labelRFID"):
                self.labelRFID.setText("RFID Not Found . . . .\nโปรดตรวจสอบอุปกรณ์ RFID เชื่อมต่อกับคอมพิวเตอร์")
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
                self.labelADAM.setText("ADAM Not Found . . . .\nโปรดตรวจสอบอุปกรณ์ ADAM เชื่อมต่อกับคอมพิวเตอร์")
                self.labelADAM.setAlignment(Qt.AlignCenter)
                self.labelADAM.setStyleSheet("background:#DAA520; color:white; padding-top:460px;")
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
                self.labelADAM.setStyleSheet("background:#228B22; color:white; padding-top:460px;")
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
        self._cam_popup = QMessageBox(QMessageBox.Warning, "Camera Error", msg, parent=self)
        self._cam_popup.setStandardButtons(QMessageBox.NoButton)
        self._cam_popup.show()

    def hide_camera_error(self):
        if hasattr(self, "_cam_popup") and self._cam_popup:
            self._cam_popup.close()
            self._cam_popup = None

    def show_Camera_Mes(self, text: str):
        print(text)
        if text == "Camera_disconnect":
            self.Camera_Message.setVisible(True)
        elif text == "Camera_reconnect" :
            self.Camera_Message.setVisible(False)


    # --- inside class MainApp (UI.py) ---
    def get_today_totals(self):
        """Get totals for TODAY ONLY."""
        result = read_today_summary()
        
        if result is None:
            logger.warning("read_today_summary returned None!")
            return {
                "Chemical Analysis": 0,
                "Solder Ability Test": 0,
                "Thickness Measurement": 0,
                "Group Lead": 0,
                "Manager": 0,
            }
        
        return {
            "Chemical Analysis": result.get("Chemical Analysis", 0),
            "Solder Ability Test": result.get("Solder Ability Test", 0),
            "Thickness Measurement": result.get("Thickness Measurement", 0),
            "Group Lead": result.get("Group Lead", 0),
            "Manager": result.get("Manager", 0),
        }
        
    # update task total
    def update_task_totals(self):
        # Get TODAY's totals only
        try:
            db_config = IOHandler.load_json("JsonAsset/db.json") or {}
            total_pass_today = read_db_total_today(**db_config)
            total_pass_Month = read_db_total_month(**db_config)

            if hasattr(self, "totalEnt"):
                self.totalEnt.setText(str(total_pass_today))
            if hasattr(self, "totalMonth"):
                self.totalMonth.setText(str(total_pass_Month))
            
            self.refresh_eod_chart(days=7, y_max=40)
            self.refresh_pie_chart()

        except Exception as e:
            logger.error(f"update totalEnt  failed: {e}")

    # refresh dashboard
    def refresh_eod_chart(self, days=7, y_max=40):
        try:
            db_config = IOHandler.load_json("JsonAsset/db.json") or {}
            data = read_last_7_days_by_task_from_db(**db_config)
            update_bar_chart_by_task(self.GraphEoD, data, y_max=y_max)
        except Exception as e:
            logger.error(f"refresh_eod_chart failed: {e}")

    def refresh_pie_chart(self):
        """Refresh pie chart with today's PASS vs TIMEOUT distribution from database"""
        try:
            # read PASS/TIMEOUT from database
            db_config = IOHandler.load_json("JsonAsset/db.json") or {}
            pie_data = read_pass_timeout_from_db(**db_config)
            
            # filter data more than zero
            filtered_data = {
                status: count
                for status, count in pie_data.items()
                if count > 0
            }
            
            # If no data it will show " NO DATA "
            if not filtered_data:
                filtered_data = {}  
            
            update_pie_chart(self.GraphPie, filtered_data)
            
        except Exception as e:
            logger.error(f"refresh_pie_chart failed: {e}")

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

    def apply_role(self, role: str):
        """Enable only buttons allowed by position."""
        role = role.upper().strip()

        # Button references
        btns = {
            "Chemical Analysis": self.btnCA,
            "Solder Ability Test": self.btnSAT,
            "Thickness Measurement": self.btnTM,
            "Group Lead": self.btnGL,
            "Manager": self.btnMGR,
        }

        # Role-to-button mapping
        role_map = {
            "M": ["Manager"],
            "GL": ["Group Lead"],
            "O": ["Chemical Analysis", "Solder Ability Test", "Thickness Measurement"],
            "DEV": ["Chemical Analysis", "Solder Ability Test", "Thickness Measurement", "Group Lead", "Manager"],
        }

        # Apply styling once
        style = """
        QPushButton {
            color: #C9DFEE;
            background-color: #0A84FF;
            border-radius: 12px;
            text-align: left;
            padding-left: 170px;
        }
        QPushButton:disabled {
            background-color: #2A2A2A;
            color: #808080;
            border: 2px solid #444;
        }
        """
        for btn in btns.values():
            btn.setStyleSheet(style)
            btn.setEnabled(False)
            btn.setVisible(True)

        # Enable buttons based on role
        for key in role_map.get(role, []):
            if key in btns:
                btns[key].setEnabled(True)      
                
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