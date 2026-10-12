@echo off
chcp 65001 > nul
cd /d "%~dp0"
if not exist venv\Scripts\activate.bat (
  echo Run setup.bat first.
  pause
  exit /b 1
)
call venv\Scripts\activate.bat
rem No arguments = interactive mode.  Examples:  run_ask.bat "question" --ideas
python ask.py %*
pause
