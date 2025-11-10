# IOHandler.py (Cleaned)
import os, cv2, json, time, datetime, threading, serial, serial.tools.list_ports, pymssql
from pymodbus.client import ModbusTcpClient
from PyQt5 import QtCore
from LogHandler import write_csv_log, init_logger
import codecs
logger = init_logger("IO")
class IOHandler(QtCore.QObject):
    """Handles RFID, camera, door, and emergency monitoring."""

    # ---- Signals ----
    rfid_detected = QtCore.pyqtSignal(str)
    camera_error = QtCore.pyqtSignal(str)
    camera_restored = QtCore.pyqtSignal()
    emergency_triggered = QtCore.pyqtSignal()
    emergency_cleared = QtCore.pyqtSignal()
    summary_text = QtCore.pyqtSignal(str)
    # ---- ADAM-6050 CONFIG ----
    USE_ADAM = True
    ADAM_HOST = "10.0.0.1"   # <-- your module IP
    ADAM_PORT = 502
    ADAM_TIMEOUT = 2
    # ---- Door ------
    BASE_COIL_DO = 16    # DO0..DO5 at coils 16–21
    DO_DOOR = 0           # DO0 for the door

    BASE_DI = 0
    DI_EMERGENCY = 0      # DI0 = emergency input
    DI_BUTTON = 1         # DI1 = door-open button

    DO_ACTIVE_OPENS = True   # True → DO HIGH unlocks door

    MSSQL_HOST = "172.16.0.102"
    MSSQL_USER = "dbxuser"
    MSSQL_PASSWORD = ""
    MSSQL_DBNAME = "APCSProDB"

    # init
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cap = None
        self.ser = None          # RFID
        self.ser_door = None     # Door board
        self.serial_lock = threading.Lock()
        self.reading_active = False
        self.adam = None
        self.adam_ok = False
        self._emergency_mode = False
        self._door_connected = False       # current known state
        self._last_door_log = 0            # cooldown timer
        self._rfid_connected = False
        self._last_rfid_log = 0
        self._rfid_watch_running = False

    # ---------------- RFID ----------------
    # search by Vendor ID and Products ID
    # Return with connected port
    def _find_device(self, vid, pid):
        for port in serial.tools.list_ports.comports():
            if port.vid == vid and port.pid == pid:
                return port.device
        return None


    def _retry_serial_init(self, desc, vid, pid, baudrate, timeout):
        """Shared retry loop for serial devices (with emergency lock support)."""
        first_fail = True
        while True:
            try:
                port = self._find_device(vid, pid)

                # -------- Missing device --------
                if not port:
                    if first_fail and "Door" in desc:
                        logger.error(f"{desc} device lost — entering emergency lock.")
                        write_csv_log("Emergency", status="BOARD_DISCONNECTED")
                        self.emergency_triggered.emit()
                        first_fail = False

                    logger.warning(f"{desc} not found, retrying...")
                    time.sleep(3)
                    continue

                # -------- Device found --------
                ser = serial.Serial(port, baudrate=baudrate, timeout=timeout)
                logger.info(f"{desc} connected at {port}")

                if "Door" in desc:
                    logger.info("Emergency board restored — system unlocking.")
                    write_csv_log("Emergency", status="BOARD_RESTORED")
                    self.emergency_cleared.emit()

                return ser

            except Exception as e:
                logger.error(f"Failed to open {desc}: {e}")
                time.sleep(3)
            time.sleep(2)

    def init_serial(self, vid=4292, pid=60000, baudrate=19200, timeout=0.2):
        """Initialize RFID serial device and start watcher."""
        port = self._find_device(vid, pid)
        if not port:
            logger.warning("RFID not found — starting watcher.")
            self.ser = None
            self._rfid_connected = False
            if not self._rfid_watch_running:
                threading.Thread(
                    target=self._rfid_watch_loop,
                    args=(vid, pid, baudrate, timeout),
                    daemon=True,
                ).start()
            return None

        try:
            self.ser = serial.Serial(port, baudrate=baudrate, timeout=timeout)
            logger.info(f"RFID connected at {port}")
            self._rfid_connected = True
            if not self._rfid_watch_running:
                threading.Thread(
                    target=self._rfid_watch_loop,
                    args=(vid, pid, baudrate, timeout),
                    daemon=True,
                ).start()
            return self.ser
        except Exception as e:
            logger.error(f"Failed to open RFID: {e}")
            self._rfid_connected = False
            return None

    def _rfid_watch_loop(self, vid, pid, baudrate, timeout):
        """Monitor RFID connection state and reconnect when lost."""
        self._rfid_watch_running = True
        cooldown = 5

        while True:
            time.sleep(1)
            now = time.time()

            port = self._find_device(vid, pid)
            connected = bool(port)

            # ---------- Lost ----------
            if not connected and self._rfid_connected:
                if now - self._last_rfid_log > cooldown:
                    logger.warning("RFID disconnected.")
                    write_csv_log("Emergency", status="RFID_LOST")
                    self.summary_text.emit("RFID reconnecting...")
                    self._last_rfid_log = now
                self._rfid_connected = False
                # stop reading safely
                self.reading_active = False
                continue

            # ---------- Restored ----------
            if connected and not self._rfid_connected:
                try:
                    self.ser = serial.Serial(port, baudrate=baudrate, timeout=timeout)
                    logger.info(f"RFID reconnected at {port}")
                    write_csv_log("Emergency", status="RFID_RESTORED")
                    self.summary_text.emit("")
                    self._rfid_connected = True
                    # ready for new reads
                    self.start_rfid_thread()
                except Exception as e:
                    logger.debug(f"RFID reopen failed: {e}")


    def start_rfid_thread(self):
        """Start continuous RFID read loop."""
        if self.reading_active:
            return
        if not self.ser or not self.ser.is_open:
            self.init_serial()
        self.reading_active = True
        threading.Thread(target=self._rfid_loop, daemon=True).start()

    def stop_rfid(self):
        self.reading_active = False

    def _read_card(self):
        """Perform one RFID read command sequence."""
        if not self.ser or not self.ser.is_open:
            return None
        try:
            with self.serial_lock:
                self.ser.write((0xAA,0xBB,0x06,0x00,0x00,0x00,0x01,0x02,0x52,0x51))
                self.ser.read(20)
                self.ser.write((0xAA,0xBB,0x06,0x00,0x00,0x00,0x02,0x02,0x04,0x04))
                data = self.ser.read(20)
                y="".join(a.upper()+b.upper() for a,b in zip(str(codecs.encode(data,"hex")[::2]),str(codecs.encode(data,"hex")[1::2])))
            if len(data) == 14:
                self.ser.write(bytes([0xAA,0xBB,0x06,0x00,0x00,0x00,0x06,0x01,0x24,0x23]))
                emp_hex = y[22:30]
                swapper = emp_hex[6:8]+emp_hex[4:6]+emp_hex[2:4]+emp_hex[0:2]
                rfid_now = str(int(swapper,16))
                emp_no =  self.server_query(rfid_now)
                return emp_no
        except Exception as e:
            logger.debug(f"RFID read issue: {e}")
        return None

    def server_query(self, raw_emp_code: str):


        # Zero-pad to length 10, same behavior as your original code
        myid = raw_emp_code
        print(f"This is My ID: {myid}")
        # if len(myid) < 10:
        #     myid = myid.zfill(10)

        sql = """
        SELECT
        users.[id], users.[full_name], users.[name], users.[english_name],
        users.[emp_num], users.[extension], users.[lockout], users.[emp_code1],
        users.[emp_code2], users.[expired_on], users.[is_admin], sc.emp_code,
        CASE
            WHEN SUM(CASE WHEN _role.operation_name = 'ByPassProcessDoor' THEN 1 ELSE 0 END) > 0
            THEN 'Y' ELSE 'N'
        END AS IS_BY_PASS
        FROM APCSProDB.man.users
        LEFT JOIN (
            SELECT u.id, r.name AS role_name, p.name AS permission_name, o.name AS operation_name
            FROM APCSProDB.man.users u
            INNER JOIN APCSProDB.man.user_roles ur ON ur.user_id = u.id
            INNER JOIN APCSProDB.man.roles r ON r.id = ur.role_id
            INNER JOIN APCSProDB.man.role_permissions rp ON rp.role_id = r.id
            INNER JOIN APCSProDB.man.permissions p ON p.id = rp.permission_id
            INNER JOIN APCSProDB.man.permission_operations po ON po.permission_id = p.id
            INNER JOIN APCSProDB.man.operations o ON o.id = po.operation_id
        ) AS _role ON _role.id = users.id
        LEFT JOIN APCSProDB.man.user_skill_cards sc ON users.id = sc.user_id
        WHERE users.emp_code1 = %s OR users.emp_code2 = %s OR sc.emp_code = %s
        GROUP BY
        users.[id], users.[full_name], users.[name], users.[english_name],
        users.[emp_num], users.[extension], users.[lockout], users.[emp_code1],
        users.[emp_code2], users.[expired_on], users.[is_admin], sc.emp_code
        """

        try:
            with pymssql.connect(
                host=self.MSSQL_HOST,
                user=self.MSSQL_USER,
                password=self.MSSQL_PASSWORD,
                database=self.MSSQL_DBNAME,
            ) as conn:
                with conn.cursor() as cur:
                    # Parameterized to avoid SQL injection
                    cur.execute(sql, (myid, myid, myid))
                    row = cur.fetchone()
            if not row:
                # mirror your original behavior's message
                logger.info("No profile")
                return None

            logger.info("Data Employee Matched")

            # Build a readable dict (indexes follow SELECT order)
            result = {
                "id": row[0],
                "full_name": row[1],
                "name": row[2],
                "english_name": row[3],
                "emp_num": row[4],
                "extension": row[5],
                "lockout": row[6],
                "emp_code1": row[7],
                "emp_code2": row[8],
                "expired_on": row[9],
                "is_admin": row[10],
                "skill_emp_code": row[11],
                "is_by_pass": row[12],
            }
            
            # Optional: keep a handy field like your EmpNo
            self.last_empno = str(result["emp_num"]) if result["emp_num"] is not None else ""
            logger.info(f"EmpNo : {self.last_empno}")
            logger.info(self.last_empno)
            return self.last_empno

        except Exception as e:
            logger.error(f"MSSQL query error: {e}")
            return None

    def _rfid_loop(self):
        """Poll RFID continuously and self-heal connection."""
        while self.reading_active:
            try:
                # --- normal read ---
                card_id = self._read_card()
                if card_id:
                    self.rfid_detected.emit(card_id)
                    QtCore.QThread.msleep(2000)
                else:
                    QtCore.QThread.msleep(100)

            except Exception as e:
                logger.error(f"RFID loop error: {e}")
                self.init_serial()
                QtCore.QThread.sleep(2)

    # ---------------- CAMERA ----------------
    def open_camera(self, index=0):
        """Ensure camera is open."""
        if self.cap and self.cap.isOpened():
            return True
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.cap = None
            msg = f"Failed to open camera (index={index})"
            self.camera_error.emit(msg)
            logger.error(msg)
            return False
        logger.info(f"Camera opened (index={index})")
        return True

    def read_frame(self):
        if not self.cap or not self.cap.isOpened():
            return None
        ok, frame = self.cap.read()
        return frame if ok else None

    def release_camera(self):
        if self.cap:
            self.cap.release()
            self.cap = None
            logger.info("Camera released.")

    def start_validation_camera_monitor(self, logic_ref=None):
        logger.info("Cam observer begin")
        if getattr(self, "_cam_val_running", False):
            return
        self._cam_val_running = True
        self._logic_ref = logic_ref

    def stop_validation_camera_monitor(self):
        logger.info("Cam observer stop")
        self._cam_val_running = False

    # ---------------- IMAGE SAVE ----------------
    def save_image_direct(self, image_bgr, folder_prefix, emp_id="Unknown"):
        if image_bgr is None:
            logger.warning("No image to save.")
            return None
        folder = os.path.join("log", folder_prefix, datetime.datetime.now().strftime("%d_%m_%y"))
        os.makedirs(folder, exist_ok=True)
        filename = f"{folder_prefix}_{emp_id}_{datetime.datetime.now():%Y%m%d_%H%M%S}.jpg"
        path = os.path.join(folder, filename)
        try:
            cv2.imwrite(path, image_bgr)
            logger.info(f"Saved image: {path}")
            return path
        except Exception as e:
            logger.error(f"Save failed: {e}")
            return None

    # ---------------- JSON UTIL ----------------
    @staticmethod
    def load_json(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"JSON load error: {e}")
            return None

    # ---------------- ADAM HELPER ----------------
    def init_adam(self):
        try:
            self.adam = ModbusTcpClient(self.ADAM_HOST, port=self.ADAM_PORT, timeout=self.ADAM_TIMEOUT)
            self.adam_ok = self.adam.connect()
        except Exception as e:
            logger.error(f"ADAM connect failed:{e}")


    def adam_write_do(self, ch, state):
        if not self.adam_ok:
            self.init_adam()
        addr = self.BASE_COIL_DO + ch
        rr = self.adam.write_coil(address=addr, value=bool(state))
        if rr.isError():
            logger.error(f"ADAM write_coil failed @ {addr}: {rr}")

    def adam_read_di(self, start, count):
        if not self.adam_ok:
            self.init_adam()
        rr = self.adam.read_discrete_inputs(address=start, count=count)
        if rr.isError():
            logger.error("ADAM read_discrete_inputs failed")
            return []
        return rr.bits[:count]

    # ---------------- DOOR ----------------
    def open_door(self, auto_close=True):
        if self._emergency_mode:
            logger.warning("Open ignored: Emergency active.")
            return
        state = True if self.DO_ACTIVE_OPENS else False
        self.adam_write_do(self.DO_DOOR, state)
        logger.info("Door opened via ADAM")
        if auto_close:
            QtCore.QTimer.singleShot(5000, self.close_door)

    def close_door(self):
        state = False if self.DO_ACTIVE_OPENS else True
        self.adam_write_do(self.DO_DOOR, state)
        logger.info("Door closed via ADAM")

    # ---------------- EMERGENCY ----------------
    def start_emergency_monitor(self):
        if getattr(self, "_emg_running", False):
            return
        self._emg_running = True
        threading.Thread(target=self._emg_loop, daemon=True).start()

    def stop_emergency_monitor(self):
        self._emg_running = False

    def _emg_loop(self):
        while getattr(self, "_emg_running", False):
            try:
                bits = self.adam_read_di(self.BASE_DI, 12)
                val = bool(bits[self.DI_EMERGENCY])

                # If button wired to ISO GND (pressed=0V), invert:
                emg_active = not val

                if emg_active != getattr(self, "_emg_state", None):
                    self._emg_state = emg_active
                    if emg_active:
                        self.emergency_triggered.emit()
                        self.close_door()
                    else:
                        self.emergency_cleared.emit()

                QtCore.QThread.msleep(100)
            except Exception as e:
                self.init_adam()
                logger.error(f"Emergency loop error: {e}")
                QtCore.QThread.msleep(300)

    def _emg_open(self):
        print("Temporary function: Shutdown door electric current")
