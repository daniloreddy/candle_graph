# ruff: noqa: E402 -- imports below intentionally follow the early load_dotenv() call.
import os
import argparse
from dotenv import load_dotenv

# Must run before importing any local app.* module: several of them
# (e.g. app.ui.router) read env vars at module import time, so .env has to
# already be loaded into the process environment by the time they execute.
# Same resolver as app/config.py — ENV_FILE (Docker) > --env-file (local) > auto-discovery.
from redberry_webkit.env_resolver import resolve_env_path

load_dotenv(resolve_env_path())

import math
import secrets
import logging
import base64
import asyncio
import time
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import uvicorn
import pandas as pd
from fastapi import FastAPI, HTTPException, Response, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from nicegui import ui
from pydantic import BaseModel, Field, field_validator
from typing import List, Set, Literal
from datetime import datetime
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from redberry_webkit.auth import client_ip, purge_loop

from app.config import config
from app.libs.indicators import add_indicators
from app.libs.plotting import get_plot_bytes
from app import metrics
from app.metrics import RequestRecord
from app.ui.router import TRUSTED_PROXIES, router as ui_router, auth as ui_auth

api_tokens_str = os.getenv("API_TOKENS", "")
VALID_TOKENS: Set[str] = set(filter(None, api_tokens_str.split(",")))

RATE_LIMIT: str = os.getenv("RATE_LIMIT", "20/minute")

_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_log_handlers: list[logging.Handler] = [logging.StreamHandler()]
if not Path("/.dockerenv").exists():
    # Docker's own log driver already collects stdout; outside Docker there is
    # no such collector, so rotate a file ourselves to avoid unbounded growth.
    _log_dir = Path("data")
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_handlers.append(
        RotatingFileHandler(_log_dir / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    )

logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT, handlers=_log_handlers)
logger = logging.getLogger("candle_graph")


def get_client_ip(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return client_ip(request.headers, host, TRUSTED_PROXIES)


limiter = Limiter(key_func=get_client_ip)

security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    if not VALID_TOKENS:
        logger.warning("Authentication is enabled but NO API_TOKENS are configured in environment.")
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = credentials.credentials
    if not any(secrets.compare_digest(token, valid) for valid in VALID_TOKENS):
        logger.warning("Unauthorized access attempt with invalid token.")
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    return token


MAX_CONCURRENT_CHARTS = 4
CHART_TIMEOUT = 30
chart_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHARTS)


async def _config_reload_loop() -> None:
    while True:
        await asyncio.sleep(5)
        try:
            config.reload_if_stale()
        except Exception:
            logger.warning("Config reload failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await metrics.init_db()
    purge_task = asyncio.create_task(purge_loop(ui_auth))
    reload_task = asyncio.create_task(_config_reload_loop())
    yield
    purge_task.cancel()
    reload_task.cancel()


app = FastAPI(
    title="Candle Graph API",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda req, exc: Response(
        content='{"detail":"Too many requests"}',
        status_code=429,
        media_type="application/json",
    ),
)
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def ui_auth_gate(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/ui"):
        return await call_next(request)
    if path.startswith("/ui/socket.io"):
        return await call_next(request)
    token = request.cookies.get(ui_auth.cookie_name, "")
    if ui_auth.verify_token(token):
        return await call_next(request)
    if "websocket" in request.headers.get("upgrade", "").lower():
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return RedirectResponse(url="/login", status_code=302)


app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(ui_router)


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
    data: List[OHLCVData] = Field(..., max_length=5000)
    bb_k: float = Field(2.0, gt=0, le=10)
    max_ohlcv_points: int = Field(180, ge=10, le=1000)
    response_format: Literal["png", "b64"] = Field("png")


@app.post("/api/v1/chart")
@limiter.limit(RATE_LIMIT)
async def generate_chart(
    request: Request,
    body: ChartRequest,
    _token: str = Depends(verify_token),
):
    start = time.time()
    status = "error"
    err_msg: Optional[str] = None

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

            status = "ok"

            if body.response_format == "b64":
                b64_str = base64.b64encode(img_bytes).decode("utf-8")
                return {"image_b64": b64_str}

            return Response(content=img_bytes, media_type="image/png")

    except asyncio.TimeoutError:
        status = "timeout"
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
                status=status,
                duration=time.time() - start,
                error_msg=err_msg,
            )
        )


@app.get("/health")
async def health():
    return {"status": "ok"}


# --- NiceGUI mount ---
from app.ui import pages as _ui_pages  # noqa: F401,E402 — late import registers @ui.page decorators

_fastapi_app = app
ui.run_with(_fastapi_app, mount_path="/ui", storage_secret=ui_auth.ui_storage_secret)


if __name__ == "__main__":
    default_port = int(os.getenv("PORT", "8000"))
    default_host = os.getenv("HOST", "127.0.0.1")
    default_dev = os.getenv("DEV", "false").lower() in ("true", "1", "yes")

    parser = argparse.ArgumentParser(description="Candle Graph API")
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument("--host", type=str, default=default_host)
    parser.add_argument("--dev", action="store_true", default=default_dev)
    parser.add_argument("--env-file", type=str, default=None)
    args = parser.parse_args()

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.dev)
