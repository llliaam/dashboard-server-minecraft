@echo off
cd /d "%~dp0"
echo ============================================
echo  MC Dashboard — First-Time Setup
echo ============================================
echo.
echo [1/2] Menginstall dependencies...
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo GAGAL: pip install error. Pastikan Python 3.10+ terinstall.
    pause
    exit /b 1
)
echo [2/2] Menjalankan dashboard (shortcut Desktop akan dibuat otomatis)...
echo.
echo Setelah ini, gunakan shortcut "MC Dashboard" di Desktop.
echo start.bat tidak perlu dijalankan lagi.
echo.
python main.py
pause
