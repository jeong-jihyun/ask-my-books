@echo off
chcp 65001 > nul
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python was not found.
  echo Install Python 3.11 or 3.12 and check "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist venv\Scripts\activate.bat (
  echo Creating virtual environment...
  python -m venv venv
)
call venv\Scripts\activate.bat

echo Installing packages...
pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Package install failed. See TUTORIAL.md, section 11.
  pause
  exit /b 1
)

where ollama >nul 2>&1
if errorlevel 1 (
  echo [WARNING] Ollama was not found. Install it from https://ollama.com
) else (
  echo Downloading embedding model bge-m3...
  ollama pull bge-m3
)

echo.
echo Setup finished. Next: edit config.py, then run run_ingest.bat
pause
