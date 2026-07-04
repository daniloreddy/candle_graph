#!/bin/bash
# Check venv and run app
cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
    echo "Initializing venv..."
    python -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

source .venv/bin/activate
python -m app.main "$@"
