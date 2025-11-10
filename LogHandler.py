# LogHandler.py
import os, csv, threading, logging, datetime, pymssql
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from collections import Counter
import pandas as pd

# Archive file format

# log/
#  └── CSV/
#      ├── Validate/
#      │    ├── 2025/
#      │    │    ├── 01/
#      │    │    ├── 02/
#      │    │    └── 10/
#      │    │         └── Validate_2025-10-28.csv
#      └── Emergency/
#           └── 2025/
#                └── 10/
#                     └── Emergency_2025-10-28.csv


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
    """
    Insert 1 แถวลงตาราง PL_PPE:
      [record_at], [opno], [enties_of_task], [status], [image_record]
    Note: location, remark not set
    """
    image_bytes = None
    if image_path:
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
        except Exception as e:
            logging.error(f"[DB_LOG] open image failed: {e}")

    conn = None
    try:
        conn = pymssql.connect(host=server, user=user, password=password, database=database, login_timeout=3)
        cur = conn.cursor()

        # ใช้ parameterized query ปลอดภัยกว่า string concat
        sql = f"""
        INSERT INTO {table}
            ([record_at], [opno], [enties_of_task], [status], [location], [image_record])
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        cur.execute(sql, (record_at, opno, enties_of_task, status, "H1", image_bytes))
        conn.commit()
        logging.info(f"[DB_LOG] inserted ({opno}, {enties_of_task}, {status}) at {record_at}")
    except Exception as e:
        logging.error(f"[DB_LOG] insert failed: {e}")
    finally:
        try:
            if conn:
                conn.close()
        except:
            pass
        
        
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

"""
Data archive crawler
"""

def read_log_summary(days_back=1, base="log/CSV"):
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
                logging.debug(f"Skip, No file name: {file_path}")
                continue
            
            try:
                df = pd.read_csv(file_path)
                if not set(["TASK","Validation Status"]).issubset(df.columns):
                    logging.debug(f"Skip missing data frame header")
                    continue
                if "TimeStamp" not in df.columns:
                    continue
                df["TimeStamp"] = pd.to_datetime(df["TimeStamp"], errors="coerce")
                df = df[df["TimeStamp"].datetime.date >= day]
                if not df.empty:
                    frames.append(df)
            except Exception as e:
                logging.debug(f"Skip {file_path}: {e}")
                continue

        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    # ---------------- Validate logs ----------------
    val_df = collect_frames("Validate")
    if not val_df.empty:
        for task in [
            "Solder Ability Test",
            "Chemical Analysis",
            "Thickness Measurement",
            "Group Lead",
            "Manager",
        ]:
            result[task] = ((val_df["TASK"] == task) &
                            (val_df["Validation Status"] == "PASS")).sum()

    # ---------------- Emergency logs ----------------
    emg_df = collect_frames("Emergency")
    if not emg_df.empty:
        hw_mask = emg_df["Status"].str.contains("BOARD|RFID|DEVICE", case=False, na=False)
        result["hardware_events"] = dict(Counter(emg_df[hw_mask]["Status"]))
        result["emergency_events"] = dict(Counter(emg_df[~hw_mask]["Status"]))

    return result

# add
# read data in date from database
def read_db_entry_date(
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
        import pymssql
        from datetime import datetime, timedelta

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
        logging.error(f"[DB_READ] read_db_entry_date failed: {e}")
        return []
    finally:
        try:
            if conn: conn.close()
        except: pass

# read total data in year from database
def read_db_total_current_year(
    server: str,
    user: str,
    password: str,
    database: str,
    table: str = "[DBx].[dbo].[PL_PPE]"
) -> int:
    import pymssql
    from datetime import date

    conn = None
    try:
        today = date.today()
        start = f"{today.year}-01-01"
        end = f"{today.year + 1}-01-01"

        conn = pymssql.connect(host=server, user=user, password=password, database=database, login_timeout=3)
        cur = conn.cursor()
        sql = f"""
        SELECT COUNT(*) FROM {table}
        WHERE [status] = 'PASS'
          AND [record_at] >= %s AND [record_at] < %s
        """
        cur.execute(sql, (start, end))
        row = cur.fetchone()
        return int(row[0] if row and row[0] is not None else 0)
    except Exception as e:
        import logging
        logging.error(f"[DB_READ] read_db_total_current_year failed: {e}")
        return 0
    finally:
        try:
            if conn: conn.close()
        except: pass
