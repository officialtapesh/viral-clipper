"""Locate external tools so users never have to install ffmpeg by hand.

ffmpeg: the system one if it exists, otherwise the static build shipped by the
`imageio-ffmpeg` pip package (Mac, Windows and Linux builds all include libass,
which the captions need). Video probing uses OpenCV, so ffprobe is not needed.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FONTS = REPO / "fonts"


def _has_libass(exe: str) -> bool:
    try:
        out = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20).stdout
        return " ass " in out
    except Exception:
        return False


@functools.lru_cache(maxsize=None)
def ffmpeg() -> str:
    sys_ff = shutil.which("ffmpeg")
    if sys_ff and _has_libass(sys_ff):
        return sys_ff
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    if sys_ff:
        return sys_ff
    raise RuntimeError("ffmpeg not found. Run: python3 scripts/setup.py")


VENV_BIN = REPO / ".venv" / ("Scripts" if os.name == "nt" else "bin")
YTDLP_BIN = VENV_BIN / ("yt-dlp.exe" if os.name == "nt" else "yt-dlp-standalone")


def deno() -> str | None:
    """JavaScript runtime YouTube now requires (installed from pip as `deno`)."""
    try:
        from deno import find_deno_bin

        return find_deno_bin()
    except Exception:
        return shutil.which("deno")


def ytdlp_cmd() -> list[str]:
    """Prefer the official standalone yt-dlp app: it bundles its own modern Python
    and the YouTube challenge solver, so it works even on old system Pythons."""
    if YTDLP_BIN.exists():
        cmd = [str(YTDLP_BIN)]
    else:
        cmd = [sys.executable, "-m", "yt_dlp"]
    cmd += ["--ffmpeg-location", ffmpeg()]
    d = deno()
    if d:
        cmd += ["--js-runtimes", f"deno:{d}"]
    return cmd
