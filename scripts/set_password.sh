#!/bin/bash
# Set Candle Graph dashboard password

if [ ! -d ".venv" ]; then
    echo "Initializing venv..."
    python -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

source .venv/bin/activate
python scripts/set_password.py
