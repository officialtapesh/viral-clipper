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


# --------------------------------------------------------------------------- #
# Facecam detection (streamer overlay in a corner of gameplay / screen videos)
# --------------------------------------------------------------------------- #

@dataclass
class Box:
    x: int
    y: int
    w: int
    h: int
    face: tuple  # (cx, cy, size) of the face inside, source pixels


def _sample_gray(src: Path, start: float, dur: float, info: VideoInfo, n: int = 14) -> list:
    import cv2

    frames = []
    for t in np.linspace(start + 0.3, start + max(dur - 0.3, 0.4), n):
        raw = subprocess.run([ffmpeg(), "-v", "error", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
                              "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
        if len(raw) >= info.width * info.height:
            frames.append(np.frombuffer(raw[: info.width * info.height], np.uint8).reshape(info.height, info.width))
    return frames


def detect_facecam(src: Path, start: float, dur: float, info: VideoInfo, verbose: bool = False) -> Box | None:
    """Find a small, stationary face overlay (webcam box) and its rectangle.

    1. Faces smaller than 22% of frame width that sit in the same spot in
       at least 40% of sampled frames = the streamer's cam.
    2. The cam's border is a long straight edge that stays put while the
       gameplay moves, so it shows up in the *median* gradient image.
    """
    import cv2

    frames = _sample_gray(src, start, dur, info, n=20)
    log = (lambda m: print(f"    facecam: {m}")) if verbose else (lambda m: None)
    if len(frames) < 4:
        log(f"only {len(frames)} frames could be read")
        return None
    W, H = info.width, info.height
    casc, _ = _detectors()
    hits = []
    for g in frames:
        fs = casc.detectMultiScale(cv2.equalizeHist(g), 1.1, 4, minSize=(max(48, H // 18),) * 2)
        hits += [f for f in fs if f[2] < 0.22 * W]
    if not hits:
        log("no faces found")
        return None
    a = np.array(hits, dtype=float)
    cx = (a[:, 0] + a[:, 2] / 2) / W
    cy = (a[:, 1] + a[:, 3] / 2) / H
    best = max((((abs(cx - cx[i]) < 0.04) & (abs(cy - cy[i]) < 0.06)) for i in range(len(a))), key=np.sum)
    if best.sum() < 0.35 * len(frames):
        log(f"no stable face (best spot in {int(best.sum())}/{len(frames)} frames)")
        return None
    fx, fy, fw, fh = np.median(a[best], axis=0)
    fcx, fcy = fx + fw / 2, fy + fh / 2
    # a cam that sits near the centre is a talking-head video, not an overlay
    if 0.3 * W < fcx < 0.7 * W and 0.3 * H < fcy < 0.7 * H:
        return None

    st = np.stack(frames).astype(np.float32)
    gx = np.median(np.abs(np.stack([cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3) for f in st])), axis=0)
    gy = np.median(np.abs(np.stack([cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3) for f in st])), axis=0)

    def peak(profile, lo, hi, base):
        lo, hi = int(max(lo, 0)), int(min(hi, len(profile)))
        if hi - lo < 3:
            return None
        k = int(np.argmax(profile[lo:hi]))
        return lo + k if profile[lo + k] > 6 * base else None

    r0, r1 = int(max(fy - fh, 0)), int(min(fy + 2 * fh, H))
    colp = gx[r0:r1].mean(0)
    base = float(np.median(colp)) + 1e-3
    left = peak(colp, fx - 4 * fw, fx - 0.4 * fw, base)
    right = peak(colp, fx + 1.4 * fw, fx + 5 * fw, base)
    x0 = left if left is not None else int(max(fx - 1.5 * fw, 0))
    x1 = right if right is not None else (W if fcx > W / 2 else int(min(fx + 2.5 * fw, W)))
    rowp = gy[:, x0:x1].mean(1)
    base = float(np.median(rowp)) + 1e-3
    top = peak(rowp, fy - 3 * fh, fy - 0.4 * fh, base)
    bot = peak(rowp, fy + 1.4 * fh, fy + 4 * fh, base)
    y0 = top if top is not None else (0 if fcy < H / 2 else int(max(fy - 1.2 * fh, 0)))
    y1 = bot if bot is not None else (int(min(fy + 2.2 * fh, H)) if fcy < H / 2 else H)
    if (x1 - x0) < fw * 1.2 or (y1 - y0) < fh * 1.2:
        log("face found but no cam border")
        return None
    log(f"found at x={x0} y={y0} {x1 - x0}x{y1 - y0} (face in {int(best.sum())}/{len(frames)} frames)")
    return Box(int(x0), int(y0), int(x1 - x0), int(y1 - y0), (fcx, fcy, fw))


def save_check_image(src: Path, t: float, cam: Box | None, out: Path) -> None:
    """Frame with the detected cam box drawn, so a human or Claude can verify it."""
    import cv2

    raw = subprocess.run([ffmpeg(), "-v", "error", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
                          "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return
    if cam:
        cv2.rectangle(img, (cam.x, cam.y), (cam.x + cam.w, cam.y + cam.h), (0, 255, 255), 4)
    cv2.imwrite(str(out), cv2.resize(img, (img.shape[1] // 2, img.shape[0] // 2)))


def stack_crops(info: VideoInfo, cam: Box, out_w: int, out_h: int, top_h: int):
    """Crop rectangles for: gameplay (top, avoiding the cam) and cam (bottom)."""
    W, H = info.width, info.height
    # gameplay: full height, aspect out_w:top_h, steer away from the cam overlay
    gw = min(W, int(round(H * out_w / top_h / 2) * 2))
    gx = (W - gw) // 2
    if cam.x + cam.w / 2 > W / 2:          # cam on the right
        gx = max(0, min(gx, cam.x - gw - 4))
    else:                                   # cam on the left
        gx = min(W - gw, max(gx, cam.x + cam.w + 4))
    # cam: inset 4% to drop rounded borders, then largest rect of bottom aspect
    ix, iy = cam.x + cam.w * 0.04, cam.y + cam.h * 0.04
    iw, ih = cam.w * 0.92, cam.h * 0.92
    aspect = out_w / (out_h - top_h)
    cw, ch = (ih * aspect, ih) if iw / ih > aspect else (iw, iw / aspect)
    fcx, fcy, _ = cam.face
    cx = min(max(fcx - cw / 2, ix), ix + iw - cw)
    cy = min(max(fcy - ch / 2, iy), iy + ih - ch)
    ev = lambda v: int(v) // 2 * 2
    return (ev(gw), H - H % 2, ev(gx), 0), (ev(cw), ev(ch), ev(cx), ev(cy))
