"""Speech-to-text with word-level timestamps (faster-whisper)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word]


def transcribe(
    video: Path,
    cache: Path,
    model_size: str = "small",
    language: str | None = None,
) -> list[Segment]:
    """Transcribe `video`; results are cached as JSON next to the work files."""
    if cache.exists():
        return load(cache)

    from faster_whisper import WhisperModel  # imported lazily: heavy

    try:
        model = WhisperModel(model_size, device="auto", compute_type="auto")
    except Exception as e:  # GPU libs missing/mismatched → CPU is always safe
        print(f"  (GPU not usable: {e}; using CPU)")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
    seg_iter, info = model.transcribe(
        load_audio(video),
        language=language,
        word_timestamps=True,
        vad_filter=True,
    )
    print(f"  detected language: {info.language} ({info.language_probability:.0%})")

    segments: list[Segment] = []
    for s in seg_iter:
        words = [Word(w.start, w.end, w.word.strip()) for w in (s.words or []) if w.word.strip()]
        segments.append(Segment(s.start, s.end, s.text.strip(), words))
        print(f"  [{s.start:7.1f}s] {s.text.strip()[:70]}")

    save(segments, cache)
    return segments


def load_audio(path: Path, sr: int = 16000):
    """Decode any audio/video to 16 kHz mono float32 with ffmpeg.

    Passing an array (not a path) to faster-whisper avoids PyAV, whose version
    differs between machines (e.g. Colab ships an old one that breaks it).
    """
    import subprocess

    import numpy as np

    from .tools import ffmpeg

    raw = subprocess.run([ffmpeg(), "-v", "error", "-nostdin", "-i", str(path), "-vn", "-ac", "1",
                          "-ar", str(sr), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def save(segments: list[Segment], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(s) for s in segments], ensure_ascii=False, indent=1))


def load(path: Path) -> list[Segment]:
    raw = json.loads(path.read_text())
    return [
        Segment(s["start"], s["end"], s["text"], [Word(**w) for w in s["words"]])
        for s in raw
    ]


def words_between(segments: list[Segment], start: float, end: float) -> list[Word]:
    return [w for s in segments for w in s.words if w.start >= start - 0.05 and w.end <= end + 0.05]
