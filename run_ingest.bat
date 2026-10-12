@echo off
chcp 65001 > nul
cd /d "%~dp0"
if not exist venv\Scripts\activate.bat (
  echo Run setup.bat first.
  pause
  exit /b 1
)
call venv\Scripts\activate.bat
rem Examples:  run_ingest.bat --limit 50     run_ingest.bat --delete-original
python ingest.py %*
pause
