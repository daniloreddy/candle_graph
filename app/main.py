import os
import math
import secrets
import logging
import argparse
import base64
import asyncio
import uvicorn
import pandas as pd
from fastapi import FastAPI, HTTPException, Response, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from typing import List, Set, Literal
from datetime import datetime
from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.libs.indicators import add_indicators
from app.libs.plotting import get_plot_bytes

# --- Global Argument Parsing (Worker safe) ---
env_parser = argparse.ArgumentParser(add_help=False)
env_parser.add_argument("--env-file", type=str, default=None)
env_args, _ = env_parser.parse_known_args()

# Caricamento variabili d'ambiente
load_dotenv(env_args.env_file)

# Estrazione Token Abilitati
api_tokens_str = os.getenv("API_TOKENS", "")
VALID_TOKENS: Set[str] = set(filter(None, api_tokens_str.split(",")))

RATE_LIMIT: str = os.getenv("RATE_LIMIT", "20/minute")

# --- Configurazione Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("candle_graph")

# --- Rate Limiting ---
def get_client_ip(request: Request) -> str:
    """Estrae l'IP reale del client testando gli header in sequenza."""
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

limiter = Limiter(key_func=get_client_ip)

# --- Security Dependency ---
security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verifica la validità del token Bearer."""
    if not VALID_TOKENS:
        logger.warning(
            "Authentication is enabled but NO API_TOKENS are configured in environment."
        )
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = credentials.credentials
    if not any(secrets.compare_digest(token, valid) for valid in VALID_TOKENS):
        logger.warning("Unauthorized access attempt with invalid token.")
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    return token


# --- App Config ---
MAX_CONCURRENT_CHARTS = 4
CHART_TIMEOUT = 30  # seconds per request
chart_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHARTS)

app = FastAPI(title="Candle Graph API", docs_url=None, redoc_url=None, openapi_url=None)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda req, exc: Response(
    content='{"detail":"Too many requests"}',
    status_code=429,
    media_type="application/json",
))
app.add_middleware(SlowAPIMiddleware)


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
    if not body.data:
        raise HTTPException(status_code=400, detail="Data list is empty")

    async with chart_semaphore:
        try:
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

            if body.response_format == "b64":
                b64_str = base64.b64encode(img_bytes).decode("utf-8")
                return {"image_b64": b64_str}

            return Response(content=img_bytes, media_type="image/png")

        except asyncio.TimeoutError:
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
            raise HTTPException(status_code=400, detail=detail)
        except Exception as e:
            logger.error(
                "Unexpected error for %s: %s", body.symbol, str(e), exc_info=True
            )
            raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    # Leggiamo i default dall'ambiente (popolato da load_dotenv globale)
    default_port = int(os.getenv("PORT", "8000"))
    default_host = os.getenv("HOST", "0.0.0.0")
    default_dev = os.getenv("DEV", "false").lower() in ("true", "1", "yes")

    parser = argparse.ArgumentParser(description="Candle Graph API")
    parser.add_argument(
        "--port", type=int, default=default_port, help="Porta di ascolto"
    )
    parser.add_argument(
        "--host", type=str, default=default_host, help="Host di ascolto"
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        default=default_dev,
        help="Attiva reload per sviluppo",
    )
    parser.add_argument("--env-file", type=str, default=None, help="Path al file .env")
    args = parser.parse_args()

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.dev)
