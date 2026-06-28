#!/usr/bin/env python3
"""CLI to set the Candle Graph dashboard login password."""

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_VENV_DIR = _ROOT / ("venv" if sys.platform == "win32" else ".venv")
_VENV_PYTHON = _VENV_DIR / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def _bootstrap() -> None:
    if not _VENV_PYTHON.exists():
        print("Creating venv...")
        subprocess.run([sys.executable, "-m", "venv", str(_VENV_DIR)], check=True)
        subprocess.run(
            [str(_VENV_PYTHON), "-m", "pip", "install", "-r", str(_ROOT / "requirements.txt")],
            check=True,
        )
    if Path(sys.executable).resolve() != _VENV_PYTHON.resolve():
        sys.exit(subprocess.run([str(_VENV_PYTHON), *sys.argv]).returncode)


_bootstrap()

import getpass  # noqa: E402

sys.path.insert(0, str(_ROOT))

from app.ui.router import auth  # noqa: E402


def main() -> None:
    password = getpass.getpass("New password: ")
    confirm = getpass.getpass("Confirm password: ")
    if not password:
        print("Password cannot be empty.")
        sys.exit(1)
    if password != confirm:
        print("Passwords do not match.")
        sys.exit(1)
    auth.set_password(password)
    print("Password set successfully.")


if __name__ == "__main__":
    main()
