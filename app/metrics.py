"""MetricsDB: async SQLite for chart request tracking."""

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/metrics.db")
_lock = asyncio.Lock()


@dataclass
class RequestRecord:
    symbol: str
    status: str  # "ok" | "error" | "timeout"
    duration: float  # seconds
    error_msg: Optional[str] = None


async def init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        REAL    NOT NULL,
                symbol    TEXT    NOT NULL,
                status    TEXT    NOT NULL,
                duration  REAL,
                error_msg TEXT
            )
        """)
        await db.commit()
    logger.info("MetricsDB ready at %s", _DB_PATH)


async def record(rec: RequestRecord) -> None:
    async with _lock:
        try:
            async with aiosqlite.connect(_DB_PATH) as db:
                await db.execute(
                    "INSERT INTO requests (ts, symbol, status, duration, error_msg) VALUES (?, ?, ?, ?, ?)",
                    (time.time(), rec.symbol, rec.status, rec.duration, rec.error_msg),
                )
                await db.commit()
        except Exception as e:
            logger.warning("MetricsDB record failed: %s", e)


async def get_stats(hours: int = 24) -> dict:
    since = time.time() - hours * 3600
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT status, duration FROM requests WHERE ts >= ?", (since,)) as cur:
            rows = list(await cur.fetchall())

    total = len(rows)
    ok = sum(1 for r in rows if r["status"] == "ok")
    errors = sum(1 for r in rows if r["status"] == "error")
    timeouts = sum(1 for r in rows if r["status"] == "timeout")
    durations = [r["duration"] for r in rows if r["duration"] is not None]
    avg_dur = sum(durations) / len(durations) if durations else 0.0

    return {
        "total": total,
        "ok": ok,
        "errors": errors,
        "timeouts": timeouts,
        "avg_duration_s": round(avg_dur, 2),
    }


async def get_history(limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM requests ORDER BY ts DESC LIMIT ?", (limit,)) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]
