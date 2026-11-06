@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --name Shijuan --add-data "web:web" --add-data "sources.json:." --collect-submodules uvicorn launcher.py
exit /b %errorlevel%
