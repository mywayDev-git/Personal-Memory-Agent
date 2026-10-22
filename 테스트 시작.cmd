@echo off
setlocal
cd /d "%~dp0"
set "PMA_TEST_PY="
if exist ".venv\Scripts\pythonw.exe" set "PMA_TEST_PY=%CD%\.venv\Scripts\pythonw.exe"
if not defined PMA_TEST_PY if exist "..\..\.venv\Scripts\pythonw.exe" set "PMA_TEST_PY=%CD%\..\..\.venv\Scripts\pythonw.exe"
if not defined PMA_TEST_PY (
  echo Project Python not found. Please check the project virtual environment.
  pause
  exit /b 1
)
start "" "%PMA_TEST_PY%" -m scripts.user_test_console
