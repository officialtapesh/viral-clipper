"""Join several time ranges into one clip (cold opens, showing the action first)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from .tools import ffmpeg
from .transcribe import Segment, Word


def assemble(parts: list, get_source: Callable[[float, float], tuple[Path, float]],
             segs: list[Segment], tmp: Path, fps: float = 30.0) -> tuple[Path, list[Segment], float]:
    """Cut every [start, end] part (in the given order) and join them.

    Returns the joined file, its words re-timed onto the new timeline, and the
    total length. Each cut gets a tiny audio fade so joins never click.
    """
    tmp.mkdir(parents=True, exist_ok=True)
    pieces: list[Path] = []
    words: list[Word] = []
    t = 0.0
    for k, (a, b) in enumerate(parts):
        src, off = get_source(a, b)
        d = b - a
        piece = (tmp / f"part{k}.mp4").resolve()
        subprocess.run([ffmpeg(), "-y", "-v", "error", "-ss", f"{a - off:.3f}", "-i", str(Path(src).resolve()),
                        "-t", f"{d:.3f}", "-vf", f"fps={fps},format=yuv420p",
                        "-af", f"aresample=48000,afade=t=in:d=0.03,afade=t=out:st={max(d - 0.05, 0):.3f}:d=0.05",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
                        "-c:a", "aac", "-b:a", "256k", "-ac", "2", str(piece)], check=True)
        pieces.append(piece)
        for s in segs:
            for w in s.words:
                if w.start >= a - 0.05 and w.end <= b + 0.05:
                    words.append(Word(w.start - a + t, min(w.end, b) - a + t, w.text))
        t += d
    lst = tmp / "parts.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in pieces))
    joined = (tmp / "joined.mp4").resolve()
    subprocess.run([ffmpeg(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(joined)], check=True)
    return joined, [Segment(0.0, t, "", words)], t
