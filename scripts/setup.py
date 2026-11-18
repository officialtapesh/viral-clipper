#!/usr/bin/env python3
"""One-command setup. Works on macOS, Windows and Linux.

    python3 scripts/setup.py

Creates a private virtual environment in .venv, installs everything (including
an ffmpeg build with caption support, so no Homebrew/apt needed), then runs
`doctor` to confirm the machine is ready. Safe to run again any time.
"""

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VENV = REPO / ".venv"


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


YTDLP_ASSETS = {
    ("darwin", None): "yt-dlp_macos",
    ("win32", None): "yt-dlp.exe",
    ("linux", "aarch64"): "yt-dlp_linux_aarch64",
    ("linux", None): "yt-dlp_linux",
}


def fetch_ytdlp() -> None:
    """Download the official standalone yt-dlp (bundles its own Python + YouTube solver).
    YouTube changes often, so refresh it if it's more than 3 days old."""
    import platform
    import time
    import urllib.request

    arch = platform.machine().lower()
    plat = "linux" if sys.platform.startswith("linux") else sys.platform
    asset = YTDLP_ASSETS.get((plat, arch)) or YTDLP_ASSETS.get((plat, None))
    if not asset:
        print("  (no standalone yt-dlp for this platform; using the pip version)")
        return
    bindir = VENV / ("Scripts" if os.name == "nt" else "bin")
    dest = bindir / ("yt-dlp.exe" if os.name == "nt" else "yt-dlp-standalone")
    if dest.exists() and time.time() - dest.stat().st_mtime < 3 * 86400:
        return
    url = f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/{asset}"
    print(f"→ Downloading latest yt-dlp ({asset})")
    try:
        tmp = dest.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.chmod(0o755)
        tmp.replace(dest)
    except Exception as e:
        print(f"  ⚠️  couldn't download standalone yt-dlp ({e}); falling back to the pip version")


MIN_PY = (3, 10)


def _py_version(py: Path) -> tuple:
    try:
        out = subprocess.run([str(py), "-c", "import sys;print(sys.version_info[0], sys.version_info[1])"],
                             capture_output=True, text=True, timeout=30).stdout.split()
        return tuple(int(x) for x in out)
    except Exception:
        return (0, 0)


def ensure_modern_venv() -> None:
    """Make .venv on Python 3.10+. If the system Python is older (e.g. macOS's
    built-in 3.9), fetch `uv` and let it provide a private Python 3.12, with no
    Homebrew and no installer for the user to run."""
    if venv_python().exists():
        if _py_version(venv_python()) >= MIN_PY:
            return
        print("→ Existing .venv uses an old Python; rebuilding it")
        shutil.rmtree(VENV)

    if sys.version_info >= MIN_PY:
        print("→ Creating virtual environment (.venv)")
        venv.EnvBuilder(with_pip=True).create(VENV)
        return

    print(f"→ Your Python is {sys.version.split()[0]}; getting a private Python 3.12 via uv")
    boot = REPO / ".uv-bootstrap"
    boot_py = boot / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not boot_py.exists():
        venv.EnvBuilder(with_pip=True).create(boot)
    subprocess.check_call([str(boot_py), "-m", "pip", "install", "-q", "--upgrade", "uv"])
    uv = boot / ("Scripts/uv.exe" if os.name == "nt" else "bin/uv")
    subprocess.check_call([str(uv), "venv", str(VENV), "--python", "3.12", "--seed", "-q"])


def main() -> None:
    if sys.version_info < (3, 8):
        sys.exit(f"Python 3.8+ needed to start setup (you have {sys.version.split()[0]}). Get it from python.org.")

    ensure_modern_venv()

    py = str(venv_python())
    print("→ Installing dependencies (first run takes a few minutes)")
    subprocess.check_call([py, "-m", "pip", "install", "-q", "--upgrade", "pip"])
    subprocess.check_call([py, "-m", "pip", "install", "-q", "-r", str(REPO / "requirements.txt")])

    fetch_ytdlp()

    print("→ Checking setup")
    r = subprocess.call([py, str(REPO / "scripts" / "clip.py"), "doctor"])
    sys.exit(r)


if __name__ == "__main__":
    main()
