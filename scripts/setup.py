#!/usr/bin/env python3
"""One-command setup. Works on macOS, Windows and Linux.

    python3 scripts/setup.py

Creates a private virtual environment in .venv, installs everything (including
an ffmpeg build with caption support, so no Homebrew/apt needed), then runs
`doctor` to confirm the machine is ready. Safe to run again any time.
"""

import os
import subprocess
import sys
import venv
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VENV = REPO / ".venv"


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main() -> None:
    if sys.version_info < (3, 9):
        sys.exit(f"Python 3.9+ needed (you have {sys.version.split()[0]}). Get it from python.org.")

    if not venv_python().exists():
        print("→ Creating virtual environment (.venv)")
        venv.EnvBuilder(with_pip=True).create(VENV)

    py = str(venv_python())
    print("→ Installing dependencies (first run takes a few minutes)")
    subprocess.check_call([py, "-m", "pip", "install", "-q", "--upgrade", "pip"])
    subprocess.check_call([py, "-m", "pip", "install", "-q", "-r", str(REPO / "requirements.txt")])

    print("→ Checking setup")
    r = subprocess.call([py, str(REPO / "scripts" / "clip.py"), "doctor"])
    sys.exit(r)


if __name__ == "__main__":
    main()
