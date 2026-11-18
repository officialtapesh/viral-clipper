"""Fetch a source video from a URL (YouTube, Instagram, X, etc.) or accept a local path."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .tools import ytdlp_cmd

VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}


def get_source(src: str, workdir: Path) -> Path:
    """Return a local path to the source video, downloading it if `src` is a URL."""
    if os.path.exists(src):
        return Path(src).resolve()

    if not src.startswith(("http://", "https://")):
        raise FileNotFoundError(f"Not a file or URL: {src}")

    workdir.mkdir(parents=True, exist_ok=True)
    for p in workdir.glob("source.*"):  # already downloaded
        if p.suffix in VIDEO_EXT:
            return p.resolve()

    cmd = ytdlp_cmd() + [
        "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "-o", str(workdir / "source.%(ext)s"),
        src,
    ]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise RuntimeError(
            "Download failed. If you're inside a sandbox without internet access to the site, "
            "download the video yourself and pass the file path instead of the URL.")
    for p in workdir.glob("source.*"):
        if p.suffix in VIDEO_EXT:
            return p.resolve()
    raise RuntimeError("Download finished but no video file was found")
