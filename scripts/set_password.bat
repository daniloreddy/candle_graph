@echo off
:: Set Candle Graph dashboard password

if not exist "venv" (
    echo Initializing venv...
    python -m venv venv
    call venv\Scripts\pip install -r requirements.txt
)

call venv\Scripts\activate
python scripts\set_password.py
