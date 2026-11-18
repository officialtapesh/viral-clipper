#!/usr/bin/env python3
"""Entry point: python3 scripts/clip.py run <url-or-file>

Automatically uses the repo's .venv (created by scripts/setup.py) if present,
so users never have to activate anything.
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV_PY = HERE.parent / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

if VENV_PY.exists() and Path(sys.prefix).resolve() != VENV_PY.parent.parent.resolve():
    args = [str(VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]]
    if os.name == "nt":
        import subprocess
        sys.exit(subprocess.call(args))
    try:
        os.execv(args[0], args)
    except OSError:
        pass  # .venv was built on another OS (e.g. shared folder); fall back to this Python

sys.path.insert(0, str(HERE))

from clipper.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
