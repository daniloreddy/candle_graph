@echo off
:: Check venv and run app

if not exist "venv" (
    echo Error: venv not found. Run setup first.
    exit /b 1
)

call venv\Scripts\activate
python -m app.main %*
