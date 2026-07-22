@echo off
cd /d "%~dp0"
echo MC Dashboard — mengecek dependencies...
python -m pip install -q -r requirements.txt
echo Starting...
python main.py
pause
