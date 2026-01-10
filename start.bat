@echo off
echo Starting Drone Monitor...

:: Create venv if not exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

:: Activate venv
call venv\Scripts\activate

:: Install requirements
echo Installing dependencies...
pip install -r requirements.txt
playwright install chromium

:: Run Server
echo Starting Server...
echo Opening http://localhost:8000
start http://localhost:8000
python run.py

pause
