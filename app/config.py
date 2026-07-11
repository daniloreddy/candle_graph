from __future__ import annotations

from redberry_webkit.config import ConfigManager

_DEFAULTS: dict[str, str] = {
    "REFRESH_ENABLED": "true",
    "REFRESH_INTERVAL": "30",
    "TZ": "UTC",
}

config = ConfigManager(defaults=_DEFAULTS, secret_keys=set())
