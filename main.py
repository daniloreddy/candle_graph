import os
import logging
import argparse
import asyncio
import uvicorn
import pandas as pd
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, HTTPException, Response, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import List, Set
from datetime import datetime
from dotenv import load_dotenv

from libs.indicators import add_indicators
from libs.plotting import get_plot_bytes

# --- Global Argument Parsing (Worker safe) ---
env_parser = argparse.ArgumentParser(add_help=False)
env_parser.add_argument("--env-file", type=str, default=None)
env_args, _ = env_parser.parse_known_args()

# Caricamento variabili d'ambiente
load_dotenv(env_args.env_file)

# Estrazione Token Abilitati
api_tokens_str = os.getenv("API_TOKENS", "")
VALID_TOKENS: Set[str] = set(filter(None, api_tokens_str.split(",")))

# --- Configurazione Logging ---
log_handler = RotatingFileHandler("app.log", maxBytes=1_000_000, backupCount=3)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[log_handler, logging.StreamHandler()],
)
logger = logging.getLogger("cangle_graph")

# --- Security Dependency ---
security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verifica la validità del token Bearer."""
    if not VALID_TOKENS:
        logger.warning(
            "Authentication is enabled but NO API_TOKENS are configured in environment."
        )
        raise HTTPException(status_code=401, detail="Unauthorized")

    if credentials.credentials not in VALID_TOKENS:
        logger.warning("Unauthorized access attempt with invalid token.")
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    return credentials.credentials


# --- App Config ---
MAX_CONCURRENT_CHARTS = 4
chart_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHARTS)

app = FastAPI(title="Cangle Graph API")


class OHLCVData(BaseModel):
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class ChartRequest(BaseModel):
    symbol: str = Field(..., max_length=50)
    data: List[OHLCVData] = Field(..., max_length=5000)
    bb_k: float = Field(2.0, gt=0)
    max_ohlcv_points: int = Field(180, ge=10, le=1000)


@app.post("/api/v1/chart")
async def generate_chart(
    request: ChartRequest,
    _token: str = Depends(verify_token),  # Protezione endpoint
):
    if not request.data:
        raise HTTPException(status_code=400, detail="Data list is empty")

    async with chart_semaphore:
        try:
            df = pd.DataFrame([d.model_dump() for d in request.data])
            df = df.sort_values(by="date").reset_index(drop=True)
            df = df.tail(request.max_ohlcv_points).copy()

            df_with_indicators = await asyncio.to_thread(
                add_indicators, df, bb_k=request.bb_k
            )

            if df_with_indicators.empty:
                raise ValueError("Insufficient data for indicators after calculation")

            img_bytes = await asyncio.to_thread(
                get_plot_bytes, df_with_indicators, request.symbol
            )

            if not img_bytes:
                raise ValueError("Empty image bytes generated")

            return Response(content=img_bytes, media_type="image/png")

        except ValueError as e:
            logger.warning("Validation error for %s: %s", request.symbol, str(e))
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(
                "Unexpected error for %s: %s", request.symbol, str(e), exc_info=True
            )
            raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "auth_enabled": len(VALID_TOKENS) > 0,
        "concurrency_limit": MAX_CONCURRENT_CHARTS,
    }


if __name__ == "__main__":
    # Leggiamo i default dall'ambiente (popolato da load_dotenv globale)
    default_port = int(os.getenv("PORT", "8000"))
    default_host = os.getenv("HOST", "0.0.0.0")
    default_dev = os.getenv("DEV", "false").lower() in ("true", "1", "yes")

    parser = argparse.ArgumentParser(description="Cangle Graph API")
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

    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.dev)
