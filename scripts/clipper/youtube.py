"""Work from a URL without downloading the whole video.

1. `fetch_info()` reads the video's metadata (title, length, captions list).
2. `fetch_captions()` downloads only the caption track (json3, word timings)
   and turns it into the same Segment/Word structure Whisper produces.
3. `download_section()` downloads only the seconds a clip needs.

So a 2-hour podcast → a few KB of captions + ~1 minute of video per clip.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from .tools import ytdlp_cmd
from .transcribe import Segment, Word


def _run(args: list[str], capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(ytdlp_cmd() + args, capture_output=capture, text=True)


def fetch_info(url: str, work: Path) -> dict:
    cache = work / "info.json"
    if cache.exists():
        return json.loads(cache.read_text())
    r = _run(["-J", "--skip-download", "--no-playlist", url])
    if r.returncode != 0:
        raise RuntimeError(f"Couldn't read video info:\n{r.stderr[-1500:]}")
    info = json.loads(r.stdout)
    keep = {k: info.get(k) for k in ("id", "title", "duration", "width", "height", "fps", "language",
                                      "uploader", "webpage_url")}
    keep["subtitles"] = sorted((info.get("subtitles") or {}).keys())
    keep["automatic_captions"] = sorted((info.get("automatic_captions") or {}).keys())
    work.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(keep, ensure_ascii=False, indent=1))
    return keep


def choose_track(info: dict, prefer: str | None = None) -> tuple[str, bool] | None:
    """Return (language key, is_auto). Human captions beat auto; original language beats translations."""
    lang = (prefer or info.get("language") or "").split("-")[0]
    subs = [s for s in info.get("subtitles", []) if s != "live_chat"]
    auto = info.get("automatic_captions", [])

    def pick(keys, *cands):
        for c in cands:
            if c and c in keys:
                return c
        return None

    if prefer:
        k = pick(subs, prefer) or pick(auto, f"{prefer}-orig", prefer)
        if k:
            return k, k not in subs
    k = pick(subs, lang, f"{lang}-IN", f"{lang}-US", f"{lang}-GB")
    if k:
        return k, False
    orig = [a for a in auto if a.endswith("-orig")]
    if orig:
        return orig[0], True
    k = pick(auto, lang)
    if k:
        return k, True
    if len(subs) == 1:
        return subs[0], False
    k = pick(subs, "en", "hi") or pick(auto, "en", "hi")
    return (k, k in auto) if k else None


def _parse_json3(data: dict) -> list[Word]:
    words: list[Word] = []
    events = [e for e in data.get("events", []) if e.get("segs")]
    for e in events:
        t0 = e.get("tStartMs", 0) / 1000
        dur = e.get("dDurationMs", 0) / 1000
        segs = [s for s in e["segs"] if s.get("utf8", "").strip()]
        if not segs:
            continue
        has_offsets = any("tOffsetMs" in s for s in segs[1:])
        if has_offsets:  # auto captions: one seg per word with its own start
            for s in segs:
                for tok in s["utf8"].split():
                    words.append(Word(t0 + s.get("tOffsetMs", 0) / 1000, 0, tok))
        else:  # human captions: a phrase per event; spread words across it
            toks = " ".join(s["utf8"] for s in segs).split()
            step = (dur or 0.4 * len(toks)) / max(len(toks), 1)
            for i, tok in enumerate(toks):
                words.append(Word(t0 + i * step, 0, tok))

    words.sort(key=lambda w: w.start)
    # drop duplicates from rolling captions, then set end = next start (capped)
    dedup: list[Word] = []
    for w in words:
        if dedup and abs(w.start - dedup[-1].start) < 0.01 and w.text == dedup[-1].text:
            continue
        dedup.append(w)
    for i, w in enumerate(dedup):
        nxt = dedup[i + 1].start if i + 1 < len(dedup) else w.start + 0.5
        w.end = round(min(nxt, w.start + 1.0), 3)
        w.start = round(w.start, 3)
    return [w for w in dedup if not re.fullmatch(r"\[.*\]", w.text)]  # drop [Music] etc.


def words_to_segments(words: list[Word], max_words: int = 18, gap: float = 0.7) -> list[Segment]:
    segs: list[Segment] = []
    cur: list[Word] = []
    for w in words:
        if cur and (w.start - cur[-1].end > gap or len(cur) >= max_words
                    or cur[-1].text.endswith((".", "?", "!", "।"))):
            segs.append(Segment(cur[0].start, cur[-1].end, " ".join(x.text for x in cur), cur))
            cur = []
        cur.append(w)
    if cur:
        segs.append(Segment(cur[0].start, cur[-1].end, " ".join(x.text for x in cur), cur))
    return segs


def fetch_captions(url: str, info: dict, work: Path, prefer: str | None = None) -> list[Segment] | None:
    track = choose_track(info, prefer)
    if not track:
        return None
    key, is_auto = track
    out = work / "captions"
    out.mkdir(parents=True, exist_ok=True)
    r = _run(["--skip-download", "--no-playlist", "--sub-format", "json3", "--sub-langs", key,
              "--write-auto-subs" if is_auto else "--write-subs", "-o", str(out / "cap"), url])
    files = list(out.glob("cap*.json3"))
    if r.returncode != 0 or not files:
        return None
    words = _parse_json3(json.loads(files[0].read_text(encoding="utf-8")))
    if len(words) < 20:
        return None
    print(f"  captions: {key} ({'auto' if is_auto else 'human'}), {len(words)} words")
    return words_to_segments(words)


def download_section(url: str, start: float, end: float, work: Path, pad: float = 1.0) -> tuple[Path, float]:
    """Download only [start-pad, end+pad]. Returns (file, offset_seconds)."""
    a = max(0.0, start - pad)
    b = end + pad
    tag = hashlib.md5(f"{url}|{a:.2f}|{b:.2f}".encode()).hexdigest()[:10]
    dest = (work / "sections" / f"sec_{int(a)}_{tag}.mp4").resolve()
    if dest.exists() and dest.stat().st_size > 10_000:
        return dest, a
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = _run(["--no-playlist",
              "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
              "--download-sections", f"*{a:.2f}-{b:.2f}", "--force-keyframes-at-cuts",
              "--merge-output-format", "mp4", "-o", str(dest), url], capture=False)
    if r.returncode != 0 or not dest.exists():
        raise RuntimeError(f"Couldn't download section {a:.0f}-{b:.0f}s")
    return dest, a
