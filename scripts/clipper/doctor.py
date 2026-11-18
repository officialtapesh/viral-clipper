"""`clip.py doctor`: check that this machine can run the whole pipeline."""

from __future__ import annotations

import importlib
import sys
import urllib.request

from .tools import FONTS, _has_libass, ffmpeg

OK, BAD, WARN = "✅", "❌", "⚠️ "


def _reach(url: str) -> bool:
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=8)
        return True
    except urllib.error.HTTPError as e:  # any HTTP answer means the network path works
        return e.code < 500 and e.code != 403
    except Exception:
        return False


def run() -> int:
    problems = 0
    print(f"{OK} Python {sys.version.split()[0]}" if sys.version_info >= (3, 9)
          else f"{BAD} Python 3.9+ required")

    for mod, why in [("faster_whisper", "transcription"), ("cv2", "face tracking"),
                     ("numpy", "core"), ("yt_dlp", "downloading"), ("imageio_ffmpeg", "bundled ffmpeg")]:
        try:
            importlib.import_module(mod)
            print(f"{OK} {mod}")
        except Exception:
            print(f"{BAD} {mod} missing ({why}) → run: python3 scripts/setup.py")
            problems += 1

    try:
        import cv2
        if cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml").empty():
            print(f"{BAD} OpenCV face model missing → pip install 'opencv-python-headless<5'")
            problems += 1
    except Exception:
        pass

    try:
        ff = ffmpeg()
        if _has_libass(ff):
            print(f"{OK} ffmpeg with captions ({ff})")
        else:
            print(f"{BAD} ffmpeg has no libass (captions) → run: python3 scripts/setup.py")
            problems += 1
    except Exception as e:
        print(f"{BAD} {e}")
        problems += 1

    from .tools import YTDLP_BIN, deno
    try:
        import subprocess
        vcmd = [str(YTDLP_BIN)] if YTDLP_BIN.exists() else [sys.executable, "-m", "yt_dlp"]
        v = subprocess.run(vcmd + ["--version"], capture_output=True, text=True, timeout=60)
        ver = (v.stdout or "").strip().splitlines()[-1] if v.stdout.strip() else "?"
        print(f"{OK} yt-dlp {ver} ({'standalone app' if YTDLP_BIN.exists() else 'pip'})")
    except Exception as e:
        print(f"{WARN} yt-dlp check failed: {e}")
    print(f"{OK} deno (YouTube JS runtime)" if deno() else
          f"{WARN} deno missing → YouTube downloads may fail; run: python3 scripts/setup.py")
    if sys.version_info < (3, 10) and not YTDLP_BIN.exists():
        print(f"{WARN} Python {sys.version.split()[0]} only gets an old yt-dlp → re-run setup "
              "(it fetches the standalone app) or install Python 3.10+")

    fonts = sorted(p.name for p in FONTS.glob("*.tt*")) if FONTS.is_dir() else []
    print(f"{OK} {len(fonts)} caption fonts bundled" if fonts else f"{WARN} no bundled fonts (captions use system fonts)")

    print("\nNetwork:")
    for name, url, need in [("YouTube (download by URL)", "https://www.youtube.com", False),
                            ("Hugging Face (speech model, first run only)", "https://huggingface.co", True)]:
        if _reach(url):
            print(f"{OK} {name}")
        else:
            print(f"{WARN} {name} not reachable"
                  + (" → the speech model can't download; run where internet is open" if need
                     else " → download the video yourself and pass the file path"))

    print("\n" + ("Ready. Try: python3 scripts/clip.py run \"<youtube-url>\" -n 5" if not problems
                  else f"{problems} problem(s) above. Fix them, then run doctor again."))
    return 1 if problems else 0
