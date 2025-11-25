# LogHandler.py
import os, csv, threading, logging, datetime, pymssql
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from collections import Counter
import pandas as pd
from datetime import date

# Archive file format
# log/
#  └── CSV/
#      ├── Validate/
#      │    ├── 2025/
#      │    │    ├── 01/
#      │    │    ├── 02/
#      │    │    └── 11/
#      │    │         └── Validate_2025-11-17.csv
#      └── Emergency/
#           └── 2025/
#                └── 11/
#                     └── Emergency_2025-11-17.csv

LOG_DIR = "log/text"
os.makedirs(LOG_DIR, exist_ok=True)
_csv_lock = threading.Lock()

class CSVFormatter(logging.Formatter):
    """Custom formatter for compact CSV-like output."""
    def format(self, record):
        date = datetime.datetime.now().strftime("%d/%m/%y")
        time = datetime.datetime.now().strftime("%H:%M:%S")
        return f"{date}|{time} | {record.levelname} | {record.name} | {record.funcName} | {record.getMessage()}"

def write_csv_log(log_type: str, **kwargs):
    """
    log_type: "Validate" or "Emergency"
    Write date log into year/month subfolder.
    """
    now = datetime.datetime.now()
    year = now.strftime("%Y")
    month = now.strftime("%m")

    # Create year/month path
    base_dir = Path(f"log/CSV/{log_type}/{year}/{month}/") 
    base_dir.mkdir(parents=True, exist_ok=True)

    date_tag = now.strftime("%Y-%m-%d")
    csv_path = base_dir / f"{log_type}_{date_tag}.csv"

    with _csv_lock:
        file_exists = csv_path.exists()
        with csv_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # header only once per day file
            if not file_exists:
                if log_type == "Validate":
                    writer.writerow(["ID", "TASK", "TimeStamp", "Validation Status", "Items Missing"])
                elif log_type == "Emergency":
                    writer.writerow(["TimeStamp", "Status"])

            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
            if log_type == "Validate":
                writer.writerow([
                    kwargs.get("id", "Unknown"),
                    kwargs.get("task", "Unknown"),
                    timestamp,
                    kwargs.get("status", "UNKNOWN"),
                    kwargs.get("missing", "NONE")
                ])
            elif log_type == "Emergency":
                writer.writerow([timestamp, kwargs.get("status", "UNKNOWN")])

    logging.info(f"[CSV_LOG] {log_type} log saved → {csv_path}")
    return {"timestamp": timestamp, "csv_path": str(csv_path)}

# --- NEW CORE DB UTILITY ---
def _execute_db_query(server: str, user: str, password: str, database: str, sql: str, params: tuple = None, fetch_one=False, fetch_all=False, commit=False):
    """Internal function to handle DB connection, query execution, and cleanup."""
    conn = None
    try:
        conn = pymssql.connect(
            host=server, 
            user=user, 
            password=password, 
            database=database, 
            login_timeout=3
        )
        cur = conn.cursor()
        
        if params is None:
            cur.execute(sql)
        else:
            cur.execute(sql, params)

        if commit:
            conn.commit()
            return None
        
        if fetch_one:
            return cur.fetchone()
        
        if fetch_all:
            return cur.fetchall()
            
        return None

    except Exception as e:
        logging.error(f"[DB_EXEC] Query failed: {e}\nSQL: {sql[:100]}...")
        return None
    finally:
        try:
            if conn: 
                conn.close()
        except: 
            pass

# The existing write_db_log is kept, but internally it would now call _execute_db_query with commit=True.
# We'll refactor write_db_log to use this new utility:
def write_db_log(
    server: str,
    user: str,
    password: str,
    database: str,
    table: str = "[DBx].[dbo].[PL_PPE]",
    *,
    record_at: str,
    opno: str,
    enties_of_task: str,
    status: str,
    image_path: str = None
):
    """Insert 1 row into PL_PPE table, now using the core utility."""
    image_bytes = None
    if image_path:
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
        except Exception as e:
            logging.error(f"[DB_LOG] open image failed: {e}")

    sql = f"""
    INSERT INTO {table}
        ([record_at], [opno], [enties_of_task], [status], [image_record])
    VALUES (%s, %s, %s, %s, %s)
    """
    params = (record_at, opno, enties_of_task, status, image_bytes)
    
    result = _execute_db_query(server, user, password, database, sql, params, commit=True)
    if result is None:
        logging.info(f"[DB_LOG] inserted ({opno}, {enties_of_task}, {status}) at {record_at}")
    else:
        logging.error(f"[DB_LOG] insert failed for ({opno}, {enties_of_task}, {status}) at {record_at}")
        
        
def init_logger(name: str = "main") -> logging.Logger:
    """
    Create a date rotating logger that writes to file and terminal.
    Format:
        10:03:45 | INFO | IO | open_camera | Camera opened (index=0).
    """
    date_tag = datetime.datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(LOG_DIR, f"{date_tag}.log")

    # --- format for both file and console ---
    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(funcName)s | %(message)s"
    formatter = logging.Formatter(fmt, datefmt="%H:%M:%S")

    # --- rotating file handler ---
    file_handler = TimedRotatingFileHandler(
        log_path, when="midnight", backupCount=7, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # --- console (terminal) handler ---
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    # --- logger setup ---
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.info(f"Logger initialized for '{name}' → {log_path}")
    return logger


# ============================================================
# DATA ARCHIVE CRAWLER FUNCTIONS
# ============================================================

def read_today_summary(base="log/CSV"):
    """
    Read validation logs for TODAY ONLY and count PASS by task.
    Returns dict with counts per task for current day.
    """
    today = datetime.date.today()
    base = Path(base)
    
    result = {
        "Solder Ability Test": 0,
        "Chemical Analysis": 0,
        "Thickness Measurement": 0,
        "Group Lead": 0,
        "Manager": 0,
    }
    
    # Build path for today's file
    yy, mm, dd = today.strftime("%Y"), today.strftime("%m"), today.strftime("%d")
    file_path = base / "Validate" / yy / mm / f"Validate_{yy}-{mm}-{dd}.csv"
    
    if not file_path.exists():
        logging.info(f"No validation log for today: {file_path}")
        return result
    
    try:
        df = pd.read_csv(file_path)
        
        # Check required columns
        required = ["TASK", "Validation Status"]
        if not set(required).issubset(df.columns):
            logging.warning(f"Missing columns in {file_path}")
            return result
        
        # Count PASS records by task
        logging.info(f"Processing today's log: {len(df)} total records")
        for task in result.keys():
            count = ((df["TASK"] == task) & 
                    (df["Validation Status"] == "PASS")).sum()
            result[task] = int(count)
            # if count > 0:
            #     logging.info(f"Today - Task '{task}': {count} PASS")
        
    except Exception as e:
        logging.error(f"Error reading today's log: {e}")
    
    logging.info(f"Today's summary: {result}")
    return result

def read_last_7_days_by_task_from_db(
    server: str,
    user: str,
    password: str,
    database: str,
    table: str = "[DBx].[dbo].[PL_PPE]"
):
    """
    Read last 7 days from database and group by date and task.
    Returns: dict with structure:
    {
        "dates": ["24-11", "25-11", ...],
        "tasks": {
            "Chemical Analysis": [5, 3, 7, ...],
            "Solder Ability Test": [2, 4, 1, ...],
            ...
        }
    }
    """
    conn = None
    try:
        conn = pymssql.connect(host=server, user=user, password=password, database=database)
        cur = conn.cursor()
        
        # Query ดึงข้อมูล 7 วันล่าสุด แยกตาม task
        sql = f"""
        SELECT 
            CONVERT(date, record_at) AS date,
            enties_of_task,
            COUNT(*) AS cnt
        FROM {table}
        WHERE status = 'PASS'
          AND record_at >= DATEADD(DAY, -7, GETDATE())
        GROUP BY CONVERT(date, record_at), enties_of_task
        ORDER BY date ASC, enties_of_task
        """
        cur.execute(sql)
        rows = cur.fetchall()
        
        # สร้าง structure สำหรับ 7 วัน
        from datetime import datetime, timedelta
        today = datetime.now().date()
        dates = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            dates.append(day.strftime("%d-%m"))
        
        # Initialize result
        result = {
            "dates": dates,
            "tasks": {
                "Chemical Analysis": [0] * 7,
                "Solder Ability Test": [0] * 7,
                "Thickness Measurement": [0] * 7,
                "Group Lead": [0] * 7,
                "Manager": [0] * 7,
            }
        }
        
        # Map วันที่กับ index
        date_to_idx = {}
        for i in range(7):
            day = today - timedelta(days=6-i)
            date_to_idx[day] = i
        
        # ใส่ข้อมูลจาก database
        for row in rows:
            date_obj = row[0]  # date object
            task = row[1]      # task name
            count = int(row[2])
            
            if date_obj in date_to_idx and task in result["tasks"]:
                idx = date_to_idx[date_obj]
                result["tasks"][task][idx] = count
        
        logging.info(f"[DB_READ] 7-day task summary loaded from database")
        return result
        
    except Exception as e:
        logging.error(f"[DB_READ] read_last_7_days_by_task_from_db failed: {e}")
        # Return empty structure
        return {
            "dates": [(datetime.now().date() - timedelta(days=6-i)).strftime("%d-%m") for i in range(7)],
            "tasks": {
                "Chemical Analysis": [0] * 7,
                "Solder Ability Test": [0] * 7,
                "Thickness Measurement": [0] * 7,
                "Group Lead": [0] * 7,
                "Manager": [0] * 7,
            }
        }
    finally:
        try:
            if conn:
                conn.close()
        except:
            pass

def read_log_summary(days_back=7, base="log/CSV"):
    """
    Read validation logs from last N days and count PASS by task.
    Returns dict with counts per task.
    """
    today = datetime.date.today()
    base = Path(base)

    result = {
        "Solder Ability Test": 0,
        "Chemical Analysis": 0,
        "Thickness Measurement": 0,
        "Group Lead": 0,
        "Manager": 0,
        "emergency_events": {},
        "hardware_events": {},
    }

    # ---------------- Helper ----------------
    def collect_frames(folder_name):
        frames = []
        for i in range(days_back):
            day = today - datetime.timedelta(days=i)
            yy, mm, dd = day.strftime("%Y"), day.strftime("%m"), day.strftime("%d")
            file_path = base / folder_name / yy / mm / f"{folder_name}_{yy}-{mm}-{dd}.csv"
            
            if not file_path.exists():
                logging.debug(f"Skip, No file: {file_path}")
                continue
            
            try:
                df = pd.read_csv(file_path)
                
                # Check required columns exist
                if folder_name == "Validate":
                    required = ["TASK", "Validation Status", "TimeStamp"]
                    if not set(required).issubset(df.columns):
                        logging.warning(f"Skip {file_path}: missing columns {required}")
                        continue
                    
                    # Parse timestamp and filter by date
                    df["TimeStamp"] = pd.to_datetime(df["TimeStamp"], errors="coerce")
                    df = df.dropna(subset=["TimeStamp"])  # Remove invalid timestamps
                    
                    # Filter rows from this specific day onwards
                    df = df[df["TimeStamp"].dt.date >= day]
                    
                    if not df.empty:
                        frames.append(df)
                        logging.info(f"Loaded {len(df)} rows from {file_path}")
                        
                elif folder_name == "Emergency":
                    if "TimeStamp" not in df.columns or "Status" not in df.columns:
                        continue
                    df["TimeStamp"] = pd.to_datetime(df["TimeStamp"], errors="coerce")
                    df = df.dropna(subset=["TimeStamp"])
                    df = df[df["TimeStamp"].dt.date >= day]
                    if not df.empty:
                        frames.append(df)
                        
            except Exception as e:
                logging.error(f"Error reading {file_path}: {e}")
                continue

        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if not combined.empty:
            logging.info(f"Total {len(combined)} rows collected for {folder_name}")
        return combined

    # ---------------- Validate logs ----------------
    val_df = collect_frames("Validate")
    if not val_df.empty:
        logging.info(f"Processing {len(val_df)} validation records")
        for task in [
            "Solder Ability Test",
            "Chemical Analysis",
            "Thickness Measurement",
            "Group Lead",
            "Manager",
        ]:
            count = ((val_df["TASK"] == task) &
                    (val_df["Validation Status"] == "PASS")).sum()
            result[task] = int(count)
            # if count > 0:
            #     logging.info(f"Task '{task}': {count} PASS records")

    # ---------------- Emergency logs ----------------
    emg_df = collect_frames("Emergency")
    if not emg_df.empty:
        hw_mask = emg_df["Status"].str.contains("BOARD|RFID|DEVICE", case=False, na=False)
        result["hardware_events"] = dict(Counter(emg_df[hw_mask]["Status"]))
        result["emergency_events"] = dict(Counter(emg_df[~hw_mask]["Status"]))

    # logging.info(f"Summary result: {result}")
    return result


# ============================================================
# DATABASE READ FUNCTIONS
# ============================================================

# --- MERGED DB READ FUNCTION ---
def read_db_summary(
    server: str,
    user: str,
    password: str,
    database: str,
    table: str = "[DBx].[dbo].[PL_PPE]",
    days: int = 7
):
    """
    Return list of (date, count) for last `days` days with status='PASS'
    """
    conn = None
    try:
        conn = pymssql.connect(host=server, user=user, password=password, database=database)
        cur = conn.cursor()
        sql = f"""
        SELECT CONVERT(date, record_at) AS date, COUNT(*) AS cnt
        FROM {table}
        WHERE status = 'PASS'
          AND record_at >= DATEADD(DAY, -%s, GETDATE())
        GROUP BY CONVERT(date, record_at)
        ORDER BY date ASC
        """
        cur.execute(sql, (days,))
        rows = cur.fetchall()
        return [(r[0], int(r[1])) for r in rows]
    except Exception as e:
        # logging.error(f"[DB_READ] read_db_entry_date failed: {e}")
        return []
    finally:
        try:
            if conn: 
                conn.close()
        except: 
            pass


def read_db_total_today(
    server: str,
    user: str,
    password: str,
    database: str,
    table: str = "[DBx].[dbo].[PL_PPE]"
) -> int:
    """
    Return total count of PASS records for TODAY only.
    """
    conn = None
    try:
        today = date.today()
        start = f"{today.year}-{today.month:02d}-{today.day:02d} 00:00:00"
        end = f"{today.year}-{today.month:02d}-{today.day:02d} 23:59:59"

        conn = pymssql.connect(host=server, user=user, password=password, database=database, login_timeout=3)
        cur = conn.cursor()
        sql = f"""
        SELECT COUNT(*) FROM {table}
        WHERE [status] = 'PASS'
          AND [record_at] >= %s AND [record_at] <= %s
        """
        cur.execute(sql, (start, end))
        row = cur.fetchone()
        count = int(row[0] if row and row[0] is not None else 0)
        # logging.info(f"[DB_READ] Total PASS today ({today}): {count}")
        return count
    except Exception as e:
        # logging.error(f"[DB_READ] read_db_total_today failed: {e}")
        return 0
    finally:
        try:
            if conn: 
                conn.close()
        except: 
            pass

def read_db_total_month(
    server: str,
    user: str,
    password: str,
    database: str,
    table: str = "[DBx].[dbo].[PL_PPE]"
) -> int:
    """
    Return total count of PASS records for CURRENT MONTH only (from day 1 to last day).
    """
    conn = None
    try:
        today = date.today()
        first_day = date(today.year, today.month, 1)
        start = f"{first_day.year}-{first_day.month:02d}-01 00:00:00"

        conn = pymssql.connect(
            host=server, 
            user=user, 
            password=password, 
            database=database, 
            login_timeout=3
        )
        cur = conn.cursor()

        sql = f"""
        SELECT COUNT(*) FROM {table}
        WHERE [status] = 'PASS'
          AND [record_at] >= %s 
          AND [record_at] < DATEADD(MONTH, 1, %s)
        """
        cur.execute(sql, (start, start))
        row = cur.fetchone()
        count = int(row[0] if row and row[0] is not None else 0)
        
        logging.info(f"[DB_READ] Total PASS this month ({first_day.strftime('%Y-%m')}): {count}")
        return count
        
    except Exception as e:
        logging.error(f"[DB_READ] read_db_total_month failed: {e}")
        return 0
    finally:
        try:
            if conn: 
                conn.close()
        except: 
            pass

def read_pass_timeout_from_db(
    server: str,
    user: str,
    password: str,
    database: str,
    table: str = "[DBx].[dbo].[PL_PPE]"
):
    """
    Read PASS and TIMEOUT counts for TODAY from database.
    Returns: {"PASS": count, "TIMEOUT": count}
    """
    conn = None
    try:
        today = date.today()
        start = f"{today.year}-{today.month:02d}-{today.day:02d} 00:00:00"
        end = f"{today.year}-{today.month:02d}-{today.day:02d} 23:59:59"

        conn = pymssql.connect(
            host=server, 
            user=user, 
            password=password, 
            database=database, 
            login_timeout=3
        )
        cur = conn.cursor()
        
        sql = f"""
        SELECT 
            [status],
            COUNT(*) AS cnt
        FROM {table}
        WHERE [record_at] >= %s 
          AND [record_at] <= %s
          AND [status] IN ('PASS', 'TIMEOUT')
        GROUP BY [status]
        """
        cur.execute(sql, (start, end))
        rows = cur.fetchall()
        
        # Initialize result
        result = {
            "PASS": 0,
            "TIMEOUT": 0
        }
        
        # Fill in counts from database
        for row in rows:
            status = row[0]
            count = int(row[1])
            if status in result:
                result[status] = count
        
        # logging.info(f"[DB_READ] Today's PASS/TIMEOUT: PASS={result['PASS']}, TIMEOUT={result['TIMEOUT']}")
        return result
        
    except Exception as e:
        # logging.error(f"[DB_READ] read_pass_timeout_from_db failed: {e}")
        return {"PASS": 0, "TIMEOUT": 0}
    finally:
        try:
            if conn: 
                conn.close()
        except: 
            pass