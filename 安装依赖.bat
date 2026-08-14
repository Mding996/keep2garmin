@echo off
cd /d "%~dp0"
echo ========================================
echo   Install Dependencies
echo ========================================
echo.
pip install -r requirements.txt
echo.
echo Done! Now double-click start.bat
pause
