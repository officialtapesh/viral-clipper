"""Animated word-by-word captions (ASS/libass), Opus/Klap/Vizard style.

Styles:
  pop       3 words at a time, UPPERCASE, active word pops + turns yellow
  karaoke   one line at a time, words light up as they are spoken
  boxed     active word sits on a coloured box (Hormozi-style)
  minimal   clean sentence-case subtitles, no animation
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .transcribe import Word


@dataclass
class CaptionStyle:
    name: str = "pop"
    font: str = "Montserrat ExtraBold"
    size: int = 0              # 0 = auto from frame height
    color: str = "FFFFFF"      # RGB hex
    highlight: str = "FFE600"  # active word
    keyword: str = "4CFF6A"    # numbers / power words
    outline: str = "000000"
    words_per_group: int = 3
    uppercase: bool = True
    position: float = 0.72     # vertical centre of captions, 0=top 1=bottom


PRESETS = {
    "pop": CaptionStyle(),
    "karaoke": CaptionStyle(name="karaoke", words_per_group=6, uppercase=False, highlight="00E5FF"),
    "boxed": CaptionStyle(name="boxed", words_per_group=3, highlight="FFFFFF"),
    "minimal": CaptionStyle(name="minimal", words_per_group=6, uppercase=False,
                            highlight="FFFFFF", keyword="FFFFFF"),
}

KEYWORD_RE = re.compile(r"^(\d[\d,.%₹$k]*|[A-Z]{2,}|.{9,})$")


def _ass_color(rgb: str, alpha: str = "00") -> str:
    rgb = rgb.lstrip("#")
    return f"&H{alpha}{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}".upper()


def _ts(t: float) -> str:
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _clean(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def _group(words: list[Word], n: int, max_gap: float = 0.6) -> list[list[Word]]:
    groups: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        brk = cur and (len(cur) >= n or w.start - cur[-1].end > max_gap
                       or cur[-1].text.endswith((".", "?", "!", "।")))
        if brk:
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def build_ass(words: list[Word], clip_start: float, clip_end: float, w: int, h: int,
              style: CaptionStyle, title: str = "", title_secs: float = 3.0,
              caption_y: float | None = None) -> str:
    size = style.size or int(h * (0.052 if style.name in ("pop", "boxed") else 0.042))
    y = caption_y if caption_y is not None else style.position
    margin_v = int(h * (1 - y)) - size // 2
    white, hi, kw = _ass_color(style.color), _ass_color(style.highlight), _ass_color(style.keyword)
    outline = _ass_color(style.outline)
    outline_w = max(2, size // 9)
    title_size = int(h * 0.040)

    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{style.font},{size},{white},{white},{outline},&H80000000,1,0,0,0,100,100,0,0,1,{outline_w},{max(1, outline_w // 2)},2,{int(w*0.08)},{int(w*0.08)},{margin_v},1
Style: Title,{style.font},{title_size},&H00111111,&H00111111,&H00FFFFFF,&H00FFFFFF,1,0,0,0,100,100,0,0,3,{int(title_size*0.45)},0,8,{int(w*0.1)},{int(w*0.1)},{int(h*0.13)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev: list[str] = []

    if title:
        t = _clean(title.upper() if style.uppercase else title)
        ev.append(f"Dialogue: 2,{_ts(0)},{_ts(min(title_secs, clip_end - clip_start))},Title,,0,0,0,,"
                  f"{{\\fad(150,300)}}{t}")

    def fmt(word: Word) -> str:
        t = _clean(word.text)
        return t.upper() if style.uppercase else t

    for g in _group(words, style.words_per_group):
        g_start = g[0].start - clip_start
        g_end = g[-1].end - clip_start
        if style.name == "minimal":
            ev.append(f"Dialogue: 1,{_ts(g_start)},{_ts(g_end)},Cap,,0,0,0,,{' '.join(fmt(x) for x in g)}")
            continue
        for i, word in enumerate(g):
            a = word.start - clip_start
            b = (g[i + 1].start - clip_start) if i + 1 < len(g) else g_end
            if b - a < 0.04:
                continue
            parts = []
            for j, other in enumerate(g):
                txt = fmt(other)
                is_kw = bool(KEYWORD_RE.match(other.text.strip(".,!?")))
                if style.name == "karaoke":
                    col = hi if j <= i else white
                    parts.append(f"{{\\c{col}}}{txt}")
                elif j == i and style.name == "boxed":
                    parts.append(f"{{\\3c&H00E64D1A&\\bord{int(size*0.28)}\\c{white}}}{txt}"
                                 f"{{\\3c{outline}\\bord{outline_w}}}")
                elif j == i:
                    pop = "\\fscx85\\fscy85\\t(0,90,\\fscx112\\fscy112)\\t(90,160,\\fscx106\\fscy106)"
                    parts.append(f"{{\\c{hi}{pop}}}{txt}{{\\fscx100\\fscy100}}")
                else:
                    parts.append(f"{{\\c{kw if is_kw else white}}}{txt}")
            ev.append(f"Dialogue: 1,{_ts(a)},{_ts(b)},Cap,,0,0,0,,{' '.join(parts)}")

    return head + "\n".join(ev) + "\n"
