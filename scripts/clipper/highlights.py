"""Find viral-worthy moments in a transcript.

Three ways to pick clips, from best to most offline:

1. **Agent mode** (used by the Claude skill): `export_for_agent()` writes a
   timestamped transcript; Claude reads it and writes clips.json itself.
2. **LLM mode**: `find_with_llm()` asks Claude (Anthropic API) or any
   OpenAI-compatible endpoint for clips with a virality score.
3. **Heuristic mode**: `find_heuristic()` needs no network at all. It scores
   sentence-aligned windows on hooks, questions, numbers, emotion and pace.

All three produce the same `Clip` list, which is snapped to sentence
boundaries so clips never start or end mid-word.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .transcribe import Segment


@dataclass
class Clip:
    start: float
    end: float
    title: str = ""
    hook: str = ""
    score: int = 0
    reason: str = ""
    hashtags: list[str] = field(default_factory=list)
    caption: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


VIRALITY_RUBRIC = """\
Score each candidate 0-100 for short-form virality (Reels / Shorts / TikTok):
- HOOK (30): do the first 3 seconds stop the scroll? Bold claim, question,
  conflict, surprising fact, "nobody talks about this", a strong opinion.
- STANDALONE (25): does it make sense with zero context from the full video?
- PAYOFF (20): is there a clear punchline, insight, reveal or resolution?
- EMOTION (15): humour, anger, awe, controversy, vulnerability, relatability.
- PACE (10): dense, no rambling, no dead air.
Rules: start exactly where the hook begins (not on filler like "so", "um",
"and"); end right after the payoff lands; never cut mid-sentence; clips must
not overlap."""


# --------------------------------------------------------------------------- #
# Transcript formatting
# --------------------------------------------------------------------------- #

def transcript_lines(segments: list[Segment]) -> str:
    return "\n".join(f"[{s.start:.1f}-{s.end:.1f}] {s.text}" for s in segments)


def export_for_agent(segments: list[Segment], workdir: Path, n: int, min_len: float, max_len: float) -> Path:
    """Write transcript.txt + instructions so an agent (Claude) can pick clips."""
    path = workdir / "transcript.txt"
    path.write_text(transcript_lines(segments))
    brief = workdir / "PICK_CLIPS.md"
    brief.write_text(f"""# Pick clips

Read `transcript.txt` (format: `[start-end] text`, seconds).
Choose up to {n} clips, each {min_len:.0f}-{max_len:.0f}s long.

{VIRALITY_RUBRIC}

Write `clips.json` in this folder: a JSON array sorted by score (highest first):

```json
[{{"start": 12.4, "end": 51.0, "score": 92,
  "title": "Short punchy on-screen hook (max 7 words)",
  "hook": "the opening line, verbatim",
  "reason": "why this will perform",
  "caption": "post caption, 1-2 lines",
  "hashtags": ["#tag1", "#tag2", "#tag3"]}}]
```
Use timestamps from the transcript; they will be snapped to sentence edges.
""")
    return path


# --------------------------------------------------------------------------- #
# LLM mode
# --------------------------------------------------------------------------- #

def _llm_prompt(segments: list[Segment], n: int, min_len: float, max_len: float, context: str) -> str:
    return f"""You are a top short-form video editor (Opus Clip / Klap style).
{('Context about this video: ' + context) if context else ''}

Below is a timestamped transcript (seconds). Find the {n} best standalone
clips, each between {min_len:.0f} and {max_len:.0f} seconds.

{VIRALITY_RUBRIC}

Return ONLY a JSON array, highest score first, no prose:
[{{"start": float, "end": float, "score": int, "title": "max 7 words on-screen hook",
  "hook": "opening line verbatim", "reason": "one sentence",
  "caption": "post caption", "hashtags": ["#a", "#b", "#c"]}}]

TRANSCRIPT:
{transcript_lines(segments)}"""


def _call_llm(prompt: str, model: str | None) -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic

        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=model or os.environ.get("CLIPPER_MODEL", "claude-sonnet-5-5"),
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")

    if os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_BASE_URL"):
        # Any OpenAI-compatible server works here, including free local ones
        # (Ollama: OPENAI_BASE_URL=http://localhost:11434/v1, model=llama3.1).
        from openai import OpenAI

        client = OpenAI()
        resp = client.chat.completions.create(
            model=model or os.environ.get("CLIPPER_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""

    raise RuntimeError(
        "No LLM configured. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or "
        "OPENAI_BASE_URL (e.g. local Ollama), or use --mode heuristic."
    )


def parse_clips_json(text: str) -> list[Clip]:
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise ValueError("No JSON array found in model output")
    items = json.loads(m.group(0))
    keys = Clip.__dataclass_fields__.keys()
    return [Clip(**{k: v for k, v in it.items() if k in keys}) for it in items]


def find_with_llm(segments, n, min_len, max_len, context="", model=None) -> list[Clip]:
    raw = _call_llm(_llm_prompt(segments, n, min_len, max_len, context), model)
    return parse_clips_json(raw)


# --------------------------------------------------------------------------- #
# Heuristic mode (offline)
# --------------------------------------------------------------------------- #

HOOK_PATTERNS = [
    r"\b(secret|truth|mistake|never|nobody|everyone|stop|why|how|what if|the reason)\b",
    r"\b(crazy|insane|shocking|biggest|worst|best|only|actually|literally)\b",
    r"\b(i was wrong|here'?s the thing|let me tell you|the problem is|most people)\b",
    # Hindi / Hinglish hooks (romanised)
    r"\b(sach|galat|kabhi|koi nahi|sabse|asli|kyun|kaise|dekho|suno|yaar)\b",
    # Hindi hooks (Devanagari) — \b doesn't work with Devanagari, so plain alternation
    r"(सच|गलत|कभी नहीं|कोई नहीं|सबसे|असली|क्यों|कैसे|झटका|राज़|राज|सीक्रेट|पहली बार|यकीन|शॉक|हैरान)",
    r"(सबसे बड़ा|सबसे महंगा|सबसे खतरनाक|पागल|खतरनाक|गज़ब|गजब|कमाल|बवाल|धमाका|अचानक|लेकिन|पर असली)",
]
EMOTION = (r"\b(love|hate|fear|angry|afraid|cried|laugh|funny|shame|proud|war|death|money|power|god)\b"
           r"|(प्यार|नफरत|डर|गुस्सा|रो|हंस|मज़ा|मजा|मौत|मार|पैसा|पैसे|करोड़|लाख|मिलियन|बिलियन|धोखा|लड़ाई|पुलिस|भाग)")
FILLER = r"^(so|and|but|um|uh|like|okay|yeah|you know|right)\b[ ,]*"


def _score_text(text: str, dur: float) -> float:
    t = text.lower()
    first = " ".join(t.split()[:15])
    s = 0.0
    s += 12 * sum(bool(re.search(p, first)) for p in HOOK_PATTERNS)
    s += 4 * sum(len(re.findall(p, t)) for p in HOOK_PATTERNS)
    s += 10 if "?" in first else 0
    s += 3 * min(len(re.findall(r"\d", t)), 5)
    s += 3 * len(re.findall(EMOTION, t))
    s += 2 * t.count("!")
    wps = len(t.split()) / max(dur, 1)
    s += 10 * min(wps / 3.0, 1.0)  # brisk speech
    s -= 8 if re.match(FILLER, t) else 0
    return s


def find_heuristic(segments: list[Segment], n: int, min_len: float, max_len: float) -> list[Clip]:
    cands: list[tuple[float, int, int]] = []
    for i in range(len(segments)):
        for j in range(i, len(segments)):
            dur = segments[j].end - segments[i].start
            if dur > max_len:
                break
            if dur < min_len:
                continue
            text = " ".join(s.text for s in segments[i : j + 1])
            cands.append((_score_text(text, dur), i, j))

    cands.sort(reverse=True)
    chosen: list[Clip] = []
    top = cands[0][0] if cands else 1
    for score, i, j in cands:
        a, b = segments[i].start, segments[j].end
        if any(a < c.end and b > c.start for c in chosen):
            continue
        first_line = segments[i].text
        title = " ".join(re.sub(FILLER, "", first_line, flags=re.I).split()[:7])
        chosen.append(Clip(a, b, title=title, hook=first_line,
                           score=int(40 + 55 * score / max(top, 1)),
                           reason="heuristic: hook words, pace, emotion"))
        if len(chosen) >= n:
            break
    return chosen


# --------------------------------------------------------------------------- #
# Post-processing
# --------------------------------------------------------------------------- #

def snap(clips: list[Clip], segments: list[Segment], min_len: float, max_len: float) -> list[Clip]:
    """Snap clip edges to sentence/word boundaries and drop overlaps."""
    words = [w for s in segments for w in s.words]
    out: list[Clip] = []
    for c in sorted(clips, key=lambda c: -c.score):
        if words:
            starts = [w.start for w in words]
            ends = [w.end for w in words]
            c.start = min(starts, key=lambda x: abs(x - c.start))
            c.end = min(ends, key=lambda x: abs(x - c.end))
        # prefer ending on a segment end if one is close (sentence completes)
        seg_end = min((s.end for s in segments), key=lambda x: abs(x - c.end), default=c.end)
        if abs(seg_end - c.end) < 2.5:
            c.end = seg_end
        if c.end - c.start > max_len + 5:
            c.end = c.start + max_len
        if c.end - c.start < min(min_len, 8):
            continue
        if any(c.start < o.end and c.end > o.start for o in out):
            continue
        out.append(c)
    return out


def save_clips(clips: list[Clip], path: Path) -> None:
    path.write_text(json.dumps([asdict(c) for c in clips], ensure_ascii=False, indent=2))


def load_clips(path: Path) -> list[Clip]:
    return parse_clips_json(path.read_text())
