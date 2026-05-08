# Candle Graph API - Agent Guide

REST API for OHLCV technical analysis charts.

## Commands
- **Run**: `./run.sh --port 8000` (MacOS/Linux) or `run.bat` (Windows).
- **Dev Mode**: `./run.sh --dev` (enables uvicorn reload).
- **Verify**: `./check.sh` (Runs Ruff format, Ruff check --fix, and MyPy).
- **Test**: `./venv/bin/python test_api_client.py` (requires running server).

## Architecture & Constraints
- **Concurrency**: CPU-bound tasks (`indicators`, `plotting`) use `asyncio.to_thread` and are throttled by `chart_semaphore` (default 4 concurrent).
- **RAM Only**: No disk I/O for charts. Uses `io.BytesIO` and `FigureCanvasAgg`.
- **Thread-Safety**: DO NOT use `matplotlib.pyplot` (`plt`). Use the Object-Oriented API (`Figure`, `FigureCanvasAgg`) to prevent global state corruption.
- **Data Prep**: Incoming OHLCV data is sorted by date and sliced to `max_ohlcv_points` (default 180) before processing.
- **Types**: Strict Pydantic validation for `datetime` and `symbol` length.

## Environment
- **Venv**: `./venv/`
- **Dependencies**: `requirements.txt` (core), `requirements.dev.txt` (lint/test/typing).
- **Logs**: `app.log` managed by `RotatingFileHandler`.
