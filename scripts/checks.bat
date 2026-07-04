@echo off
:: Code quality checks
cd /d "%~dp0.."

if not exist "venv" (
    echo Initializing venv...
    python -m venv venv
    call venv\Scripts\pip install -r requirements.txt -r requirements.dev.txt
)

call venv\Scripts\activate

echo --- Running Ruff Format ---
ruff format .

echo.
echo --- Running Ruff Check ---
ruff check . --fix

echo.
echo --- Running MyPy ---
mypy .

echo.
echo --- Running Tests ---
pytest tests\
