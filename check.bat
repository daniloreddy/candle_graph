@echo off
:: Code quality checks

if not exist "venv" (
    echo Error: venv not found.
    exit /b 1
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
