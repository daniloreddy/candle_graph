"""Single .env path resolver, shared by main.py and config.py.

Precedence: ENV_FILE (Docker — see rules/docker.md #2) > --env-file CLI flag
(local dev) > nearest .env found from cwd.
"""

import argparse
import os
from pathlib import Path

from dotenv import find_dotenv


def resolve_env_path() -> Path:
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
