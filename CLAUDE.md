# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

FastAPI REST API that generates technical analysis PNG charts (candlestick + Bollinger Bands, RSI, MACD) for cryptocurrency OHLCV data. All rendering happens in RAM — no disk I/O.

## Commands

```bash
# Setup
python -m venv venv && venv\Scripts\activate   # Windows
pip install -r requirements.txt -r requirements.dev.txt

# Run local (scripts/)
scripts\run.bat --port 8000 --env-file .env    # Windows
scripts/run.sh  --port 8000 --env-file .env    # macOS/Linux
scripts\run.bat --dev                          # auto-reload

# Docker
docker compose up --build       # build + start
docker compose up -d            # detached
docker compose down

# Quality (all checks — scripts/)
scripts\check.bat    # Windows: Ruff format, Ruff check, MyPy
scripts/check.sh     # macOS/Linux: + pytest

# Individual checks
venv\Scripts\ruff format .
venv\Scripts\ruff check . --fix
venv\Scripts\mypy .

# Tests
venv\Scripts\pytest tests\
venv\Scripts\pytest tests\test_api.py::test_name -v  # single test
venv\Scripts\python test_api_client.py               # integration (needs running server)
```

## Architecture

```
app/main.py           → FastAPI app, auth, routing, semaphore
app/libs/indicators.py → Bollinger(20), RSI(14), MACD(12/26/9) via ta library
app/libs/plotting.py  → PNG rendering, 3-subplot dark theme chart
```

**Request flow**: JSON (OHLCV + params) → Pydantic validation → Bearer token check → sort + slice data → `asyncio.to_thread` (indicators + plot) → PNG bytes response.

**Async/Thread hybrid**: FastAPI is async; Pandas/Matplotlib are synchronous. CPU-bound work runs in threads via `asyncio.to_thread()` to avoid blocking the event loop. `chart_semaphore` caps concurrent renders at 4 (default).

**Thread-safe Matplotlib**: Never use `matplotlib.pyplot` (global state). Every request creates its own `Figure` + `FigureCanvasAgg` instance in `libs/plotting.py`.

**Fail-fast on bad data**: `indicators.py` returns empty DataFrame if <26 points. `plotting.py` returns `b""` on error. Both checked in `main.py` — raise 400 rather than silently serving corrupt output.

## Configuration

`.env` file passed via `--env-file`:
```
API_TOKENS=token1,token2   # comma-separated Bearer tokens
PORT=8000
HOST=0.0.0.0
DEV=false
```

## Logging

`app.log` — `RotatingFileHandler` (1 MB max, 3 backups), also streams to console. Use `logging.getLogger(__name__)` in modules; never `print()`.

## Key Constraints

- Minimum 26 OHLCV points required (MACD's longest window)
- `max_ohlcv_points` defaults to 180, range 10–1000
- Input array hard-capped at 5000 points by Pydantic
- Token auth uses set lookup — timing-sensitive; `AUDIT.md` flags this
- Raw exception strings reach clients in error responses (see `AUDIT.md`)
