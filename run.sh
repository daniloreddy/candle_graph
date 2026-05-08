#!/bin/bash
# Check venv and run app

if [ ! -d "venv" ]; then
    echo "Error: venv not found. Run setup first."
    exit 1
fi

source venv/bin/activate
python main.py "$@"
