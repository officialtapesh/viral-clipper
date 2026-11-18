@echo off
REM Windows: double-click once. Sets up viral-clipper and starts the helper at every login.
cd /d "%~dp0"
python scripts\setup.py && python scripts\install_helper.py
pause
