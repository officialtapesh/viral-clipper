"""Locate external tools so users never have to install ffmpeg by hand.

ffmpeg: the system one if it exists, otherwise the static build shipped by the
`imageio-ffmpeg` pip package (Mac, Windows and Linux builds all include libass,
which the captions need). Video probing uses OpenCV, so ffprobe is not needed.
"""

from __future__ import annotations

import functools
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


def ytdlp_cmd() -> list[str]:
    return [sys.executable, "-m", "yt_dlp", "--ffmpeg-location", ffmpeg()]
