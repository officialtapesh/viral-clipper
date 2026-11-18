"""Auto-reframe: follow the speaker's face when cropping 16:9 to 9:16 / 1:1 / 4:5.

The camera behaves like a human operator: it holds still while the subject
stays inside a dead-zone, then eases toward them. That avoids the jittery
"robot pan" that cheap auto-reframers produce. If no face is found for most
of the clip (slides, B-roll, screen recordings), we fall back to a "fit"
layout: the full frame centred over a blurred, zoomed copy of itself.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .tools import ffmpeg

ANALYSIS_FPS = 5
ANALYSIS_WIDTH = 640


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: float
    duration: float


def probe(path: Path) -> VideoInfo:
    """Read size/fps/duration with OpenCV (no ffprobe needed), ffmpeg as fallback."""
    import cv2

    cap = cv2.VideoCapture(str(path))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    cap.release()
    if w and h:
        fps = fps if 1 < fps < 241 else 30.0
        return VideoInfo(w, h, fps, frames / fps if frames > 0 else 0.0)

    # fallback: parse `ffmpeg -i` banner
    err = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", err)
    f = re.search(r"([\d.]+) fps", err)
    d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if not m:
        raise RuntimeError(f"Could not read video: {path}")
    dur = int(d[1]) * 3600 + int(d[2]) * 60 + float(d[3]) if d else 0.0
    return VideoInfo(int(m[1]), int(m[2]), float(f[1]) if f else 30.0, dur)


def parse_aspect(aspect: str) -> float:
    a, b = aspect.split(":")
    return float(a) / float(b)


def output_size(aspect: str, height: int = 1920) -> tuple[int, int]:
    w = int(round(height * parse_aspect(aspect) / 2) * 2)
    return w, height


# --------------------------------------------------------------------------- #
# Face analysis
# --------------------------------------------------------------------------- #

def _detectors():
    import cv2

    base = getattr(getattr(cv2, "data", None), "haarcascades", "")
    f = cv2.CascadeClassifier(base + "haarcascade_frontalface_default.xml")
    p = cv2.CascadeClassifier(base + "haarcascade_profileface.xml")
    if f.empty():
        raise RuntimeError("OpenCV face models missing: pip install 'opencv-python-headless<5'")
    return f, p


def analyze_faces(src: Path, start: float, dur: float, info: VideoInfo) -> list[float | None]:
    """Return the subject's centre-x (0..1) for each analysis frame, or None."""
    import cv2

    h = int(round(info.height * ANALYSIS_WIDTH / info.width / 2) * 2)
    cmd = [ffmpeg(), "-v", "error", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{dur:.3f}",
           "-vf", f"fps={ANALYSIS_FPS},scale={ANALYSIS_WIDTH}:{h}",
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    frame_bytes = ANALYSIS_WIDTH * h
    frontal, profile = _detectors()

    centres: list[float | None] = []
    prev: float | None = None
    for k in range(len(raw) // frame_bytes):
        g = np.frombuffer(raw, np.uint8, frame_bytes, k * frame_bytes).reshape(h, ANALYSIS_WIDTH)
        g = cv2.equalizeHist(g)
        min_face = max(24, h // 12)
        faces = list(frontal.detectMultiScale(g, 1.1, 5, minSize=(min_face, min_face)))
        if not faces:
            faces = list(profile.detectMultiScale(g, 1.1, 5, minSize=(min_face, min_face)))
            faces += [(ANALYSIS_WIDTH - x - w, y, w, hh) for x, y, w, hh in
                      profile.detectMultiScale(cv2.flip(g, 1), 1.1, 5, minSize=(min_face, min_face))]
        if not faces:
            centres.append(None)
            continue

        def weight(f):
            x, y, w, hh = f
            cx = (x + w / 2) / ANALYSIS_WIDTH
            stick = 1.0 if prev is None else 1.0 + 1.5 * (1 - min(abs(cx - prev) * 3, 1))
            return w * hh * stick  # bigger + closer to current subject wins

        x, y, w, hh = max(faces, key=weight)
        prev = (x + w / 2) / ANALYSIS_WIDTH
        centres.append(prev)
    return centres


def camera_path(centres: list[float | None], n_frames: int, crop_frac: float) -> np.ndarray:
    """Turn noisy per-sample face centres into a smooth per-frame camera x (0..1)."""
    if n_frames <= 0:
        return np.zeros(0)
    xs = np.array([np.nan if c is None else c for c in centres], dtype=float)
    if np.all(np.isnan(xs)):
        return np.full(n_frames, 0.5)

    # fill gaps with nearest known value
    idx = np.arange(len(xs))
    good = ~np.isnan(xs)
    xs = np.interp(idx, idx[good], xs[good])

    # median filter kills single-frame false positives
    k = 5
    pad = np.pad(xs, (k // 2, k // 2), mode="edge")
    xs = np.array([np.median(pad[i : i + k]) for i in range(len(xs))])

    # resample to output frame rate
    xs = np.interp(np.linspace(0, len(xs) - 1, n_frames), idx, xs)

    # operator-style camera: dead-zone + easing
    half = crop_frac / 2
    dead = crop_frac * 0.18
    cam = np.empty(n_frames)
    pos = xs[0]
    vel = 0.0
    for i, target in enumerate(xs):
        err = target - pos
        if abs(err) > dead:
            vel = 0.85 * vel + 0.15 * (err - np.sign(err) * dead) * 0.25
        else:
            vel *= 0.8
        pos += vel
        pos = min(max(pos, half), 1 - half)
        cam[i] = pos
    return cam


def face_coverage(centres: list[float | None]) -> float:
    return 0.0 if not centres else sum(c is not None for c in centres) / len(centres)


# --------------------------------------------------------------------------- #
# Frame pump: decode -> crop -> encode
# --------------------------------------------------------------------------- #

def tracked_frames(src: Path, start: float, dur: float, info: VideoInfo,
                   cam: np.ndarray, out_w: int, out_h: int, fps: float):
    """Yield cropped+scaled BGR frames (bytes) following the camera path."""
    import cv2

    crop_w = int(round(info.height * out_w / out_h / 2) * 2)
    crop_w = min(crop_w, info.width)
    cmd = [ffmpeg(), "-v", "error", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{dur:.3f}",
           "-vf", f"fps={fps}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    fb = info.width * info.height * 3
    i = 0
    try:
        while True:
            buf = proc.stdout.read(fb)
            if len(buf) < fb:
                break
            frame = np.frombuffer(buf, np.uint8).reshape(info.height, info.width, 3)
            cx = cam[min(i, len(cam) - 1)] * info.width
            x0 = int(round(min(max(cx - crop_w / 2, 0), info.width - crop_w)))
            crop = frame[:, x0 : x0 + crop_w]
            yield cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_AREA).tobytes()
            i += 1
    finally:
        proc.stdout.close()
        proc.wait()
