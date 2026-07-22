from __future__ import annotations

from dotenv import load_dotenv
from redberry_webkit.env_resolver import resolve_env_path

_env_path = resolve_env_path()
load_dotenv(_env_path)

import argparse  # noqa: E402
import asyncio  # noqa: E402
import base64  # noqa: E402
import logging  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import secrets  # noqa: E402
import time  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from datetime import datetime  # noqa: E402
from logging.handlers import RotatingFileHandler  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Literal  # noqa: E402

import pandas as pd  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402
from nicegui import ui  # noqa: E402
from pydantic import BaseModel, Field, field_validator  # noqa: E402
from redberry_webkit.auth import client_ip, purge_loop  # noqa: E402
from redberry_webkit.logging_utils import CredentialFilter  # noqa: E402
from slowapi import Limiter, _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402
from slowapi.middleware import SlowAPIMiddleware  # noqa: E402
from starlette.middleware.base import RequestResponseEndpoint  # noqa: E402

from app import metrics  # noqa: E402
from app.config import config  # noqa: E402
from app.libs.indicators import add_indicators  # noqa: E402
from app.libs.plotting import get_plot_bytes  # noqa: E402
from app.metrics import RequestRecord  # noqa: E402
from app.ui.router import TRUSTED_PROXIES, auth  # noqa: E402
from app.ui.router import router as ui_router  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
DEV = os.getenv("DEV", "false").lower() in ("true", "1", "yes")
CONFIG_RELOAD_INTERVAL_S = 5

_stream_handler = logging.StreamHandler()
_file_handler = RotatingFileHandler(LOG_DIR / "app.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
_credential_filter = CredentialFilter()
_stream_handler.addFilter(_credential_filter)
_file_handler.addFilter(_credential_filter)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[_stream_handler, _file_handler],
)
logger = logging.getLogger(__name__)
logger.info("Using .env=%s", _env_path)


def _rate_limit_key(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return client_ip(request.headers, host, TRUSTED_PROXIES)


limiter = Limiter(key_func=_rate_limit_key)

_security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(_security)) -> str:
    """API auth is mandatory here (unlike the template's opt-in default): an
    unconfigured token set must fail closed, not open, for a chart-rendering API.
    Reads API_TOKENS from config (hot-reload) rather than a frozen os.getenv
    snapshot, so a token rotation via the Impostazioni page takes effect
    without a restart."""
    valid_tokens = {t.strip() for t in config.get("API_TOKENS", "").split(",") if t.strip()}
    if not valid_tokens:
        logger.warning("Authentication is enabled but NO API_TOKENS are configured.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    token = credentials.credentials
    if not any(secrets.compare_digest(token, valid) for valid in valid_tokens):
        logger.warning("Unauthorized access attempt with invalid token.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing token")

    return token


MAX_CONCURRENT_CHARTS = 4
CHART_TIMEOUT = 30
chart_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHARTS)


async def _config_reload_loop(interval_s: int) -> None:
    while True:
        await asyncio.sleep(interval_s)
        config.reload_if_stale()


def _crash_on_task_error(task: asyncio.Task[None]) -> None:
    # A background loop task (purge_loop, config reload) is only ever supposed to end
    # via .cancel() at shutdown. If it dies from an unhandled exception instead, asyncio
    # would otherwise just log "Task exception was never retrieved" and keep the process
    # alive with silently broken rate-limit purging / config hot-reload — worse than crashing.
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.critical("Background task %s died unexpectedly, exiting", task.get_name(), exc_info=exc)
        os._exit(1)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    await metrics.init_db()
    purge_task = asyncio.create_task(purge_loop(auth))
    purge_task.add_done_callback(_crash_on_task_error)
    config_task = asyncio.create_task(_config_reload_loop(CONFIG_RELOAD_INTERVAL_S))
    config_task.add_done_callback(_crash_on_task_error)
    yield
    purge_task.cancel()
    config_task.cancel()


app = FastAPI(
    title="Candle Graph",
    lifespan=_lifespan,
    docs_url="/docs" if DEV else None,
    redoc_url="/redoc" if DEV else None,
    openapi_url="/openapi.json" if DEV else None,
)
app.state.limiter = limiter
# slowapi lacks precise stubs for this handler signature, hence the ignore below.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)
app.include_router(ui_router)

_UI_PREFIX = "/ui"
_LOGIN_PATHS = {"/login", "/auth/login", "/auth/logout"}
_UI_BYPASS_PREFIXES = (f"{_UI_PREFIX}/_nicegui",)


@app.middleware("http")
async def _auth_gate(request: Request, call_next: RequestResponseEndpoint) -> Response:
    path = request.url.path
    if path in _LOGIN_PATHS or any(path.startswith(p) for p in _UI_BYPASS_PREFIXES):
        return await call_next(request)
    if path == _UI_PREFIX or path.startswith(_UI_PREFIX + "/"):
        token = request.cookies.get(auth.cookie_name, "")
        if auth.verify_token(token):
            return await call_next(request)
        return RedirectResponse(url="/login", status_code=302)
    return await call_next(request)


class OHLCVData(BaseModel):
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @field_validator("open", "high", "low", "close", "volume")
    @classmethod
    def must_be_finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("Value must be finite")
        return v


class ChartRequest(BaseModel):
    symbol: str = Field(..., max_length=50)
    data: list[OHLCVData] = Field(..., max_length=5000)
    bb_k: float = Field(2.0, gt=0, le=10)
    max_ohlcv_points: int = Field(180, ge=10, le=1000)
    response_format: Literal["png", "b64"] = Field("png")


@app.post("/api/v1/chart", response_model=None)
@limiter.limit(lambda: config.get("RATE_LIMIT", "20/minute"))
async def generate_chart(
    request: Request,
    body: ChartRequest,
    _token: str = Depends(verify_token),
) -> Response | dict[str, str]:
    start = time.time()
    status_label = "error"
    err_msg: str | None = None

    try:
        if not body.data:
            err_msg = "Data list is empty"
            raise HTTPException(status_code=400, detail=err_msg)

        async with chart_semaphore:
            df = pd.DataFrame([d.model_dump() for d in body.data])
            df = df.sort_values(by="date").reset_index(drop=True)
            df = df.tail(body.max_ohlcv_points).copy()

            df_with_indicators = await asyncio.wait_for(
                asyncio.to_thread(add_indicators, df, bb_k=body.bb_k),
                timeout=CHART_TIMEOUT,
            )

            if df_with_indicators.empty:
                raise ValueError("Insufficient data for indicators after calculation")

            img_bytes = await asyncio.wait_for(
                asyncio.to_thread(get_plot_bytes, df_with_indicators, body.symbol),
                timeout=CHART_TIMEOUT,
            )

            if not img_bytes:
                raise ValueError("Empty image bytes generated")

            status_label = "ok"

            if body.response_format == "b64":
                b64_str = base64.b64encode(img_bytes).decode("utf-8")
                return {"image_b64": b64_str}

            return Response(content=img_bytes, media_type="image/png")

    except asyncio.TimeoutError:
        status_label = "timeout"
        err_msg = "Request timed out"
        logger.error("Timeout generating chart for %s", body.symbol)
        raise HTTPException(status_code=503, detail="Request timed out")

    except ValueError as e:
        msg = str(e)
        logger.warning("Validation error for %s: %s", body.symbol, msg)
        safe_messages = {
            "Insufficient data for indicators after calculation",
            "Empty image bytes generated",
            "Data list is empty",
        }
        detail = msg if msg in safe_messages else "Invalid input data"
        err_msg = detail
        raise HTTPException(status_code=400, detail=detail)

    except HTTPException:
        raise

    except Exception as e:
        err_msg = "Internal server error"
        logger.error("Unexpected error for %s: %s", body.symbol, str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        await metrics.record(
            RequestRecord(
                symbol=body.symbol,
                status=status_label,
                duration=time.time() - start,
                error_msg=err_msg,
            )
        )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/ui/")


from app.ui import pages as _ui_pages  # noqa: E402,F401

ui.run_with(app, mount_path="/ui", storage_secret=auth.ui_storage_secret)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Candle Graph — FastAPI + NiceGUI web app")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--host", type=str, default=HOST)
    parser.add_argument("--dev", action=argparse.BooleanOptionalAction, default=DEV)
    parser.add_argument("--env-file", type=str, default=None)
    args = parser.parse_args()

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.dev,
        # Reload must not watch data/ (logs, sqlite, auth.json, NiceGUI storage) — the
        # app writes there continuously, and watching it makes every log line trigger
        # a reload that logs again, forever.
        reload_dirs=[str(PROJECT_ROOT / "app"), str(PROJECT_ROOT / "static")] if args.dev else None,
        loop="asyncio",
    )
