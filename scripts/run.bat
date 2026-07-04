@echo off
:: Check venv and run app
cd /d "%~dp0.."

if not exist "venv" (
    echo Initializing venv...
    python -m venv venv
    call venv\Scripts\pip install -r requirements.txt
)

call venv\Scripts\activate
python -m app.main %*
