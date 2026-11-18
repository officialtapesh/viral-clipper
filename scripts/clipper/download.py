"""Fetch a source video from a URL (YouTube, etc.) or accept a local path."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def get_source(src: str, workdir: Path) -> Path:
    """Return a local path to the source video, downloading it if `src` is a URL."""
    if os.path.exists(src):
        return Path(src).resolve()

    if not src.startswith(("http://", "https://")):
        raise FileNotFoundError(f"Not a file or URL: {src}")

    workdir.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(workdir / "source.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
        "--merge-output-format", "mp4",
        "-o", out_tmpl,
        src,
    ]
    subprocess.run(cmd, check=True)
    for p in workdir.glob("source.*"):
        if p.suffix in {".mp4", ".mkv", ".webm", ".mov"}:
            return p.resolve()
    raise RuntimeError("yt-dlp finished but no video file was found")
