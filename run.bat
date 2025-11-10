@echo off
REM === Change directory to your script folder ===
cd /d "C:\Users\netuser003\Documents\manop\Branch"

REM === Activate environment ===
call venv\Scripts\activate.bat

REM === Run the Python script ===
py main.py

REM === Pause to keep window open after finish ===
pause
