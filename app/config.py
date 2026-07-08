"""ConfigManager: single source of truth (.env) for runtime-editable settings.

Boot-time-only settings (PORT, HOST, DEV, API_TOKENS, ...) stay on the plain
os.getenv pattern in main.py. This manager is only for settings editable from
the /config dashboard page at runtime (see rules/uvicorn.md #7).
"""

import argparse
import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values, find_dotenv, set_key

logger = logging.getLogger(__name__)

_DEFAULTS: dict[str, str] = {
    "REFRESH_ENABLED": "true",
    "REFRESH_INTERVAL": "30",
    "TZ": "UTC",
}


def _resolve_env_path() -> Path:
    env_file_var = os.environ.get("ENV_FILE")
    if env_file_var:
        return Path(env_file_var)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--env-file", type=str, default=None)
    args, _ = parser.parse_known_args()
    if args.env_file:
        return Path(args.env_file)
    found = find_dotenv(usecwd=True)
    return Path(found) if found else Path(".env")


class ConfigManager:
    _instance: Optional["ConfigManager"] = None

    _env_path: Path
    _last_mtime: float
    _cache: dict[str, str]

    def __new__(cls) -> "ConfigManager":
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._env_path = _resolve_env_path()
            instance._last_mtime = 0.0
            instance._cache = dict(_DEFAULTS)
            cls._instance = instance
            logger.info("Config: using .env=%s", instance._env_path)
            instance._load()
        return cls._instance

    def _load(self) -> None:
        if not self._env_path.exists():
            logger.warning(
                "No .env at %s - falling back to hardcoded defaults only "
                "(check the bind-mount/ENV_FILE if this is Docker).",
                self._env_path,
            )
        merged = dict(_DEFAULTS)
        merged.update({k: v for k, v in dotenv_values(str(self._env_path)).items() if v is not None})
        self._cache = merged
        try:
            self._last_mtime = self._env_path.stat().st_mtime
        except OSError:
            self._last_mtime = 0.0

    def reload_if_stale(self) -> bool:
        """Call periodically (e.g. every ~5s from the FastAPI lifespan)."""
        try:
            mtime = self._env_path.stat().st_mtime
        except OSError:
            return False
        if mtime == self._last_mtime:
            return False
        self._load()
        return True

    def get(self, key: str, default: str = "") -> str:
        return self._cache.get(key, default)

    def get_bool(self, key: str) -> bool:
        return self._cache.get(key, "false").strip().lower() in ("true", "1", "yes")

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self._cache.get(key, str(default)))
        except ValueError:
            return default

    def update_many(self, updates: dict[str, str]) -> None:
        """Called by the web-UI save handler - writes straight to .env."""
        for key, value in updates.items():
            stripped = value.strip()
            if not stripped:
                continue
            set_key(str(self._env_path), key, stripped, quote_mode="never")
            self._cache[key] = stripped


config = ConfigManager()
