#!/bin/bash
# Code quality checks

if [ ! -d "venv" ]; then
    echo "Error: venv not found."
    exit 1
fi

source venv/bin/activate

echo "--- Running Ruff Format ---"
ruff format .

echo -e "\n--- Running Ruff Check ---"
ruff check . --fix

echo -e "\n--- Running MyPy ---"
mypy .

echo -e "\n--- Running Tests ---"
pytest tests/
