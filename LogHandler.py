# LogHandler.py
import os, csv, threading, logging, datetime, pymssql
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from collections import Counter
import pandas as pd
from datetime import date, timedelta

"""
Archive file format
log/
 └── CSV/
     ├── Validate/
     │    ├── 2025/
     │    │    ├── 01/
     │    │    ├── 02/
     │    │    └── 11/
     │    │         └── Validate_2025-11-17.csv
     └── Emergency/
          └── 2025/
               └── 11/
                    └── Emergency_2025-11-17.csv
"""
LOG_DIR = "log/text"
os.makedirs(LOG_DIR, exist_ok=True)
_csv_lock = threading.Lock()

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

def call_datetime_now():
    """Return current datetime object."""
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    time = datetime.datetime.now().strftime("%H:%M:%S") 
    return date, time

class CSVFormatter(logging.Formatter):
    """Custom formatter for compact CSV-like output."""
    def format(self, record):
        date, time = call_datetime_now()
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

# ============================================================
# DATA ARCHIVE CRAWLER FUNCTIONS
# ============================================================

def _calculate_task_summary(df: pd.DataFrame) -> dict:
    """
    Helper function to calculate PASS counts for specific tasks from a DataFrame.
    This logic is extracted and reused by both read_log_summary and read_today_summary.
    """
    tasks = [
        "Solder Ability Test",
        "Chemical Analysis",
        "Thickness Measurement",
        "Group Lead",
        "Manager",
    ]
    
    result = {task: 0 for task in tasks}
    
    # Check required columns
    required = ["TASK", "Validation Status"]
    if not set(required).issubset(df.columns):
        logging.warning("Missing required columns for task summary.")
        return result

    # Count PASS records by task
    for task in tasks:
        count = ((df["TASK"] == task) & 
                 (df["Validation Status"] == "PASS")).sum()
        result[task] = int(count)
    
    return result

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
                
                # --- 1. Log-Type Specific Column Check ---
                required_cols = []
                if folder_name == "Validate":
                    required_cols = ["TASK", "Validation Status", "TimeStamp"]
                elif folder_name == "Emergency":
                    required_cols = ["TimeStamp", "Status"]
                
                if not set(required_cols).issubset(df.columns):
                    logging.warning(f"Skip {file_path}: missing columns {required_cols}")
                    continue

                # --- 2. Consolidated Timestamp Filtering Logic ---
                # This block was previously repeated for Validate and Emergency
                if "TimeStamp" in df.columns:
                    # Parse timestamp
                    df["TimeStamp"] = pd.to_datetime(df["TimeStamp"], errors="coerce")
                    # Remove invalid timestamps
                    df = df.dropna(subset=["TimeStamp"])  
                    # Filter rows from this specific day onwards
                    df = df[df["TimeStamp"].dt.date >= day]
                
                # --- 3. Append valid DataFrame ---
                if not df.empty:
                    frames.append(df)
                    logging.info(f"Loaded {len(df)} rows from {file_path}")
                        
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
            
        # *** REPLACED REPEATED LOGIC WITH HELPER FUNCTION CALL ***
        task_summary = _calculate_task_summary(val_df)
        result.update(task_summary) # Update the result dict with task counts

    # ---------------- Emergency logs ----------------
    emg_df = collect_frames("Emergency")
    if not emg_df.empty:
        hw_mask = emg_df["Status"].str.contains("BOARD|RFID|DEVICE", case=False, na=False)
        result["hardware_events"] = dict(Counter(emg_df[hw_mask]["Status"]))
        result["emergency_events"] = dict(Counter(emg_df[~hw_mask]["Status"]))

    return result

def read_today_summary(base="log/CSV"):
    """
    Read validation logs for TODAY ONLY and count PASS by task.
    Returns dict with counts per task for current day.
    """
    today = datetime.date.today() # Use datetime.date.today() from imported module
    base = Path(base)
    
    # Build path for today's file
    yy, mm, dd = today.strftime("%Y"), today.strftime("%m"), today.strftime("%d")
    file_path = base / "Validate" / yy / mm / f"Validate_{yy}-{mm}-{dd}.csv"
    
    if not file_path.exists():
        logging.info(f"No validation log for today: {file_path}")
        return _calculate_task_summary(pd.DataFrame()) # Return empty counts
    
    try:
        df = pd.read_csv(file_path)
        
        # Use the reusable helper function for calculation
        result = _calculate_task_summary(df)
        
        logging.info(f"Today's summary: {result}")
        return result
        
    except Exception as e:
        logging.error(f"Error reading today's log: {e}")
        return _calculate_task_summary(pd.DataFrame()) # Return empty counts

# --- NEW CORE DB UTILITY (Kept as is) ---
def _execute_db_query(server: str, 
                      user: str, 
                      password: str, 
                      database: str, 
                      sql: str, 
                      params: tuple = None, 
                      fetch_one=False, 
                      fetch_all=False, 
                      commit=False):
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
        
        # Determine fetch strategy
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
        
# ============================================================
# NEW BUNDLED READ FUNCTIONS
# ============================================================
def _get_db_params(server, user, password, database, table):
    """Helper to bundle DB connection parameters."""
    return {
        "server": server,
        "user": user,
        "password": password,
        "database": database,
        "table": table
    }






def _get_db_read_sql_and_params(time_frame: str):
    """
    Helper to get the WHERE clause and parameters for different timeframes.
    Replaces repetitive date calculation logic.
    """
    today = date.today()
    if time_frame == "today":
        # Check from 00:00:00 to 23:59:59 of today
        start = f"{today.year}-{today.month:02d}-{today.day:02d} 00:00:00"
        where_clause = " [record_at] >= %s AND [record_at] <= %s "
        end = f"{today.year}-{today.month:02d}-{today.day:02d} 23:59:59"
        params = (start, end)
    elif time_frame == "week":
        # Check from the start of the current calendar week (Monday 00:00:00)
        # today.weekday() returns 0 for Monday, 6 for Sunday
        days_to_subtract = today.weekday()
        start_of_week = today - timedelta(days=days_to_subtract)
        
        start = f"{start_of_week.year}-{start_of_week.month:02d}-{start_of_week.day:02d} 00:00:00"
        # The range goes until the start of next Monday (7 days from start_of_week)
        where_clause = " [record_at] >= %s AND [record_at] < DATEADD(DAY, 7, %s) "
        params = (start, start)
    elif time_frame == "month":
        # Check from the first day of the current month
        first_day = date(today.year, today.month, 1)
        start = f"{first_day.year}-{first_day.month:02d}-01 00:00:00"
        where_clause = " [record_at] >= %s AND [record_at] < DATEADD(MONTH, 1, %s) "
        params = (start, start)
    else:
        raise ValueError("Invalid time_frame")
    
    return where_clause, params

def _execute_db_read_count(
    server: str,
    user: str,
    password: str,
    database: str,
    table: str,
    time_frame: str, # "today" or "month"
    status_filter: str = "'PASS'", # SQL IN list or single value
    group_by_status: bool = False
):
    """
    Consolidated function to read simple counts/aggregations.
    Bundles read_db_total_today, read_db_total_month, and read_pass_timeout_from_db logic.
    """
    try:
        where_time, params = _get_db_read_sql_and_params(time_frame)
    except ValueError:
        return {"PASS": 0, "TIMEOUT": 0} if group_by_status else 0

    if group_by_status:
        # Used for read_pass_timeout_from_db
        select_clause = "[status], COUNT(*) AS cnt"
        group_clause = "GROUP BY [status]"
    else:
        # Used for read_db_total_today and read_db_total_month
        select_clause = "COUNT(*)"
        group_clause = ""
        
    sql = f"""
    SELECT {select_clause}
    FROM {table}
    WHERE {where_time}
      AND [status] IN ({status_filter})
    {group_clause}
    """
    
    rows = _execute_db_query(server, user, password, database, sql, params, fetch_all=True)
    
    if group_by_status:
        # Expected statuses: 'PASS', 'TIMEOUT'
        result = {"PASS": 0, "TIMEOUT": 0}
        for row in rows if rows else []:
            status, count = row[0], int(row[1])
            if status in result:
                result[status] = count
        return result
    else:
        # Single count (Total PASS today/month)
        count = int(rows[0][0]) if rows and rows[0] and rows[0][0] is not None else 0
        return count

# ============================================================
# REFACTORED PUBLIC API FUNCTIONS
# ============================================================

def read_last_7_days_by_task_from_db(
    server: str,
    user: str,
    password: str,
    database: str,
    table: str = "[DBx].[dbo].[PL_PPE]"
):
    """
    Reads last 7 days from database and group by date and task.
    (Updated to use _execute_db_query for internal consistency)
    """
    # Query logic is unique and complex, so it stays, but execution is delegated.
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
    rows = _execute_db_query(server, user, password, database, sql, fetch_all=True)
    
    # Rest of the date/dict initialization logic is the same...
    from datetime import datetime, timedelta
    today = datetime.now().date()
    dates = [(today - timedelta(days=6-i)).strftime("%d-%m") for i in range(7)]
    
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
    date_to_idx = {today - timedelta(days=6-i): i for i in range(7)}
    
    # ใส่ข้อมูลจาก database
    for row in rows if rows else []:
        date_obj = row[0]  # date object
        task = row[1]      # task name
        count = int(row[2])
        
        if date_obj in date_to_idx and task in result["tasks"]:
            idx = date_to_idx[date_obj]
            result["tasks"][task][idx] = count
    
    logging.info(f"[DB_READ] 7-day task summary loaded from database")
    return result

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
    (Updated to use _execute_db_query for internal consistency)
    """
    sql = f"""
    SELECT CONVERT(date, record_at) AS date, COUNT(*) AS cnt
    FROM {table}
    WHERE status = 'PASS'
      AND record_at >= DATEADD(DAY, -%s, GETDATE())
    GROUP BY CONVERT(date, record_at)
    ORDER BY date ASC
    """
    rows = _execute_db_query(server, user, password, database, sql, (days,), fetch_all=True)
    return [(r[0], int(r[1])) for r in rows if r]


def read_db_total_today(
    server: str,
    user: str,
    password: str,
    database: str,
    table: str = "[DBx].[dbo].[PL_PPE]"
) -> int:
    """
    Return total count of PASS records for TODAY only.
    (Now calls _execute_db_read_count)
    """
    return _execute_db_read_count(
        server=server,
        user=user,
        password=password,
        database=database,
        table=table,
        time_frame="today",
        status_filter="'PASS'",
        group_by_status=False)


def read_db_total_month(
    server: str,
    user: str,
    password: str,
    database: str,
    table: str = "[DBx].[dbo].[PL_PPE]"
) -> int:
    """
    Return total count of PASS records for CURRENT MONTH only (from day 1 to last day).
    (Now calls _execute_db_read_count)
    """
    return _execute_db_read_count(
        server=server,
        user=user,
        password=password,
        database=database,
        table=table,
        time_frame="month",
        status_filter="'PASS'",
        group_by_status=False)

def read_pass_timeout_from_db(
    server: str,
    user: str,
    password: str,
    database: str,
    table: str = "[DBx].[dbo].[PL_PPE]"
):
    """
    Read PASS and TIMEOUT counts for TODAY from database.
    (Now calls _execute_db_read_count)
    """
    return _execute_db_read_count(
        server, 
        user, 
        password, 
        database, 
        table, 
        time_frame="today", 
        status_filter="'PASS', 'TIMEOUT'", 
        group_by_status=True
    )
