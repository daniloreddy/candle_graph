# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

FastAPI REST API that generates technical analysis PNG charts (candlestick + Bollinger Bands, RSI, MACD) for cryptocurrency OHLCV data. All rendering happens in RAM — no disk I/O. Includes a NiceGUI web dashboard for request monitoring, protected by cookie-based JWT auth.

## Commands

```bash
# Setup
python -m venv venv && venv\Scripts\activate   # Windows
pip install -r requirements.txt -r requirements.dev.txt

# Set dashboard password (first run — requires existing venv, no auto-init)
python scripts/set_password.py

# Run local (scripts/)
scripts\run.bat --port 8000 --env-file .env    # Windows
scripts/run.sh  --port 8000 --env-file .env    # macOS/Linux
scripts\run.bat --dev                          # auto-reload

# Docker
docker compose -f docker-compose-dev.yml up --build   # dev (local build)
docker compose up -d                                   # prod (GHCR image)
docker compose down

# Quality (all checks — scripts/)
scripts\checks.bat   # Windows: Ruff format, Ruff check, MyPy, pytest
scripts/checks.sh    # macOS/Linux: same

# Individual checks
venv\Scripts\ruff format .
venv\Scripts\ruff check . --fix
venv\Scripts\mypy .

# Tests
venv\Scripts\pytest tests\
venv\Scripts\pytest tests\test_api.py::test_name -v  # single test
scripts\test_api.bat "<token>" [port]                # integration (needs running server)
scripts/test_api.sh  "<token>" [port]                # macOS/Linux
```

## Architecture

```
app/
  main.py               FastAPI app, auth, routing, semaphore, NiceGUI mount, GET /health (unauthenticated)
  config.py             ConfigManager singleton — single source of truth (.env) for runtime-editable settings (REFRESH_ENABLED, REFRESH_INTERVAL, TZ), mtime-polled hot-reload every ~5s from the lifespan
  metrics.py            SQLite async metrics (RequestRecord, init_db, record, get_stats, get_history)
  libs/
    indicators.py       Bollinger(20), RSI(14), MACD(12/26/9) via ta library
    plotting.py         PNG rendering, 3-subplot dark theme chart
  ui/
    router.py           FastAPI routes: GET /login, POST /auth/login (form-based, redirect + ?error=<code> on
                        failure), GET /auth/logout + `auth` singleton (`AuthManager` from `redberry_webkit.auth`:
                        cookie-based JWT, scrypt, brute-force protection)
    pages.py            NiceGUI @ui.page("/") — dashboard with metric cards + request history table (timestamps rendered in the configured TZ)
                        NiceGUI @ui.page("/config") — settings page, "Interfaccia" card: auto-refresh enable/disable switch + interval (15/30/60/120s) + IANA timezone input, all backed by `app.config.config` (ConfigManager → .env)
static/
  login.html            Self-contained login page
data/
  metrics.db            SQLite: request log (ts, symbol, status, duration, error_msg)
  auth.json             Password hash + JWT secret (auto-created; gitignored)
  app.log               RotatingFileHandler output (non-Docker runs only — Docker's own log driver covers stdout)
```

**Request flow**: JSON (OHLCV + params) → Pydantic validation → Bearer token check → sort + slice data → `asyncio.to_thread` (indicators + plot) → PNG bytes response → metrics recorded in `finally`.

**Async/Thread hybrid**: FastAPI is async; Pandas/Matplotlib are synchronous. CPU-bound work runs in threads via `asyncio.to_thread()` to avoid blocking the event loop. `chart_semaphore` caps concurrent renders at 4 (default).

**Thread-safe Matplotlib**: Never use `matplotlib.pyplot` (global state). Every request creates its own `Figure` + `FigureCanvasAgg` instance in `libs/plotting.py`.

**Fail-fast on bad data**: `indicators.py` returns empty DataFrame if <26 points. `plotting.py` returns `b""` on error. Both checked in `main.py` — raise 400 rather than silently serving corrupt output.

**Metrics**: Every `POST /api/v1/chart` is recorded with `await metrics.record(...)` in a `finally` block — status "ok" / "error" / "timeout", duration in seconds, error_msg for non-ok. 429/401 (rate limit / auth failures) are NOT recorded (recorded only after entering the handler body).

**NiceGUI**: Mounted at `/ui` via `ui.run_with(app, mount_path="/ui", ...)`. `_auth_gate` middleware (`app/main.py`, constants `_UI_PREFIX`/`_LOGIN_PATHS`/`_UI_BYPASS_PREFIXES`) protects all `/ui/*` paths, redirecting to `/login`. NiceGUI's own websocket transport (`/ui/_nicegui`) bypasses the gate. Login: form POST `/auth/login` → 303 redirect to `/ui/` with cookie, or to `/login?error=<invalid|blocked|limited|nopassword>` — `login.html` reads the query param and shows the matching message. `verify_password()` (scrypt N=131072, ~150-250ms) runs via `asyncio.to_thread(...)`, never inline. `AUTH_SECURE_COOKIE` (env, default `0`) forces the cookie `Secure` flag when TLS terminates somewhere that doesn't set `X-Forwarded-Proto: https`. Dark mode persisted per user via `app.storage.user` (boot-time-per-user preference, out of ConfigManager's scope). Auto-refresh and timezone are app-wide (shared across all users) via `app.config.config` (`ConfigManager`, backed by `.env`) keys `REFRESH_ENABLED` (default on), `REFRESH_INTERVAL` (default 30s, options 15/30/60/120s) and `TZ` (default UTC), configurable at `/config`; when disabled no timer is created and the dashboard shows "auto-refresh disabilitato". `ConfigManager` hot-reloads from `.env` every ~5s (mtime-polled from the FastAPI lifespan), so edits — from the UI or a manual `.env` change — apply without a restart; dashboard timestamps and the auto-refresh timer pick up the new values on next Dashboard page load. Background tasks (`purge_task`, `config_task` in `_lifespan`) have `add_done_callback(_crash_on_task_error)` — an unhandled exception crashes the process (`os._exit(1)`) instead of dying silently.

## Configuration

`.env` file passed via `--env-file`. Two categories:

**Boot-time only** (plain `os.getenv`, read once at import/startup — restart required to change):
```
API_TOKENS=token1,token2   # comma-separated Bearer tokens for /api/v1/chart
PORT=8000
HOST=0.0.0.0
DEV=false
AUTH_SECURE_COOKIE=1       # set to 1 if behind HTTPS proxy (optional)
RATE_LIMIT=20/minute       # per-IP limit on /api/v1/chart (optional)
TRUSTED_PROXIES=127.0.0.1  # comma-separated IPs allowed to set CF-Connecting-IP/X-Real-IP/X-Forwarded-For (optional, default 127.0.0.1)
```

**Runtime-editable** (via `app.config.config` / the `/config` dashboard page, hot-reloaded):
```
TZ=UTC                 # IANA timezone for dashboard timestamps; invalid values fall back to UTC (logged)
REFRESH_ENABLED=true   # dashboard auto-refresh on/off
REFRESH_INTERVAL=30    # seconds: 15/30/60/120
```

UI password: set via `python scripts/set_password.py` → stored in `data/auth.json`. JWT secret auto-generated on first run and persisted there.

**Docker**: the compose files bind-mount the project directory at `/app/hostcfg` and set `ENV_FILE=/app/hostcfg/.env` so `ConfigManager` can read/write the real `.env` next to `docker-compose.yml` (see rules/uvicorn.md §7 and rules/docker.md §2 — `env_file:` alone freezes values as OS env at container boot and can't hot-reload). `NICEGUI_STORAGE_PATH=/app/data/.nicegui` keeps NiceGUI's own per-user storage (dark mode, etc.) on the bind-mounted `./data` volume so it survives container recreation.

## Key Constraints

- Minimum 26 OHLCV points required (MACD's longest window)
- `max_ohlcv_points` defaults to 180, range 10–1000
- Input array hard-capped at 5000 points by Pydantic
- Token auth uses `secrets.compare_digest` per-token (constant-time)
- `workers=1` mandatory — multiple workers would create multiple semaphore instances and metric DB connections
- `data/auth.json` and `data/metrics.db` must be in a persistent volume in Docker
