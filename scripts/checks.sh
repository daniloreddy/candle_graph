#!/bin/bash
# Code quality checks
cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
    echo "Initializing venv..."
    python -m venv .venv
    .venv/bin/pip install -r requirements.txt -r requirements.dev.txt
fi

source .venv/bin/activate

echo "--- Running Ruff Format ---"
ruff format .

echo -e "\n--- Running Ruff Check ---"
ruff check . --fix

echo -e "\n--- Running MyPy ---"
mypy .

echo -e "\n--- Running Tests ---"
pytest tests/
