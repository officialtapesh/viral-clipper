"""Command line interface.

    python scripts/clip.py run    <url-or-file> [options]   # everything, one shot
    python scripts/clip.py prepare <url-or-file> -w work      # download + transcribe
    python scripts/clip.py find   -w work --mode llm|heuristic|agent
    python scripts/clip.py render -w work -o clips
"""

from __future__ import annotations

import argparse
import dataclasses
import html
import json
import shutil
import sys
from pathlib import Path

from . import highlights as hl
from .download import get_source
from .reframe import probe
from .render import RenderOptions, render_clip, slugify
from .transcribe import transcribe, load


def _source_path(work: Path) -> Path:
    meta = work / "source.json"
    if meta.exists():
        return Path(json.loads(meta.read_text())["path"])
    raise SystemExit(f"No prepared source in {work}. Run `prepare` first.")


def _is_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


def cmd_prepare(a) -> None:
    work = Path(a.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    if _is_url(a.source) and not a.full_download:
        return _prepare_url(a, work)
    print(f"→ Getting source: {a.source}")
    src = get_source(a.source, work)
    info = probe(src)
    (work / "source.json").write_text(json.dumps({"path": str(src), "width": info.width,
                                                  "height": info.height, "fps": info.fps,
                                                  "duration": info.duration}, indent=1))
    print(f"  {info.width}x{info.height} @ {info.fps:.2f}fps, {info.duration/60:.1f} min")
    print(f"→ Transcribing with whisper-{a.whisper}")
    segs = transcribe(src, work / "transcript.json", a.whisper, a.language)
    hl.export_for_agent(segs, work, a.n, a.min, a.max)
    print(f"✓ {len(segs)} segments → {work/'transcript.txt'}")


def _prepare_url(a, work: Path) -> None:
    """URL mode: never download the whole video. Captions (or audio only) now,
    and just the chosen clip sections at render time."""
    from .transcribe import save
    from .youtube import fetch_captions, fetch_info

    print(f"→ Reading video info: {a.source}")
    info = fetch_info(a.source, work)
    dur = info.get("duration") or 0
    print(f"  \"{info.get('title')}\" · {dur/60:.1f} min · {info.get('width')}x{info.get('height')}")
    segs = None
    if not a.use_whisper:
        print("→ Fetching captions (no video download)")
        segs = fetch_captions(a.source, info, work, a.language)
    if segs:
        save(segs, work / "transcript.json")
    else:
        print("→ No usable captions → downloading AUDIO only (≈10% of video size) for Whisper")
        audio = _download_audio(a.source, work)
        segs = transcribe(audio, work / "transcript.json", a.whisper, a.language)
    (work / "source.json").write_text(json.dumps({
        "mode": "sections", "url": a.source, "title": info.get("title"), "duration": dur,
        "width": info.get("width"), "height": info.get("height")}, ensure_ascii=False, indent=1))
    hl.export_for_agent(segs, work, a.n, a.min, a.max)
    print(f"✓ {len(segs)} segments → {work/'transcript.txt'}  (video not downloaded)")


def _download_audio(url: str, work: Path) -> Path:
    import subprocess
    from .tools import ytdlp_cmd

    for p in work.glob("audio.*"):
        return p
    subprocess.run(ytdlp_cmd() + ["--no-playlist", "-f", "ba[ext=m4a]/ba", "-o", str(work / "audio.%(ext)s"), url],
                   check=True)
    return next(work.glob("audio.*"))


def cmd_find(a) -> None:
    work = Path(a.work)
    segs = load(work / "transcript.json")
    if a.mode == "agent":
        hl.export_for_agent(segs, work, a.n, a.min, a.max)
        print(f"Agent mode: read {work/'PICK_CLIPS.md'} and write {work/'clips.json'}")
        return
    print(f"→ Finding moments ({a.mode})")
    if a.mode == "llm":
        clips = hl.find_with_llm(segs, a.n, a.min, a.max, a.context, a.model)
    else:
        clips = hl.find_heuristic(segs, a.n, a.min, a.max)
    clips = hl.snap(clips, segs, a.min, a.max)[: a.n]
    hl.save_clips(clips, work / "clips.json")
    for c in clips:
        print(f"  {c.score:3d}  {c.start:7.1f}-{c.end:7.1f}s  {c.title}")
    print(f"✓ {len(clips)} clips → {work/'clips.json'}")


def cmd_render(a) -> None:
    work, out = Path(a.work).resolve(), Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((work / "source.json").read_text()) if (work / "source.json").exists() else {}
    sections = meta.get("mode") == "sections"
    src = None if sections else _source_path(work)
    segs = load(work / "transcript.json")
    clips = list(enumerate(hl.snap(hl.load_clips(work / "clips.json"), segs, a.min, a.max), 1))
    if a.only:
        keep = {int(x) for x in a.only.split(",")}
        clips = [(i, c) for i, c in clips if i in keep]
    opt = RenderOptions(aspect=a.aspect, height=a.height, layout=a.layout,
                        caption_style=a.style, font=a.font, captions=not a.no_captions,
                        title=not a.no_title, fade_out=a.fade_out,
                        music=Path(a.music) if a.music else None, music_volume=a.music_volume)
    info = None if sections else probe(src)
    results = []
    for k, (i, c) in enumerate(clips, 1):
        name = f"{i:02d}_{c.score:02d}_{slugify(c.title or c.hook)}.mp4"
        print(f"→ [{k}/{len(clips)}] {name}  ({c.duration:.0f}s{', %d parts' % len(c.parts) if c.parts else ''})")
        if c.parts:
            res = _render_parts(c, segs, out / name, opt, work, meta if sections else None, src)
        elif sections:
            from .youtube import download_section
            print("  downloading just this section…")
            sec, off = download_section(meta["url"], c.start, c.end, work)
            local = dataclasses.replace(c, start=c.start - off, end=c.end - off)
            res = render_clip(sec, local, _shift(segs, off, c.start - 5, c.end + 5), out / name, opt)
            res.update(start=round(c.start, 2), end=round(c.end, 2))
        else:
            res = render_clip(src, c, segs, out / name, opt, info)
        print(f"  layout={res['layout']}")
        results.append(res)
        shutil.rmtree(out / f".{Path(name).stem}", ignore_errors=True)
    (out / "clips.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    _gallery(results, out)
    print(f"✓ {len(results)} clips in {out}/  (open {out/'index.html'} to preview)")


def _render_parts(c, segs, out_path: Path, opt, work: Path, meta: dict | None, src: Path | None) -> dict:
    """Non-linear edit: cut each part, join them, render the joined clip."""
    from .assemble import assemble

    getter = None
    if meta:
        from .youtube import download_section

        # parts close together share one download
        spans: list[list[float]] = []
        for a_, b_ in sorted(c.parts):
            if spans and a_ - spans[-1][1] < 45:
                spans[-1][1] = max(spans[-1][1], b_)
            else:
                spans.append([a_, b_])

        def getter(a_, b_):
            span = next(sp for sp in spans if sp[0] <= a_ and b_ <= sp[1])
            print(f"  downloading section {span[0]:.0f}-{span[1]:.0f}s…")
            return download_section(meta["url"], span[0], span[1], work)
    else:
        getter = lambda a_, b_: (src, 0.0)

    tmp = out_path.parent / f".{out_path.stem}"
    joined, jsegs, total = assemble(c.parts, getter, segs, tmp)
    local = dataclasses.replace(c, start=0.0, end=total, parts=[])
    res = render_clip(joined, local, jsegs, out_path, opt)
    res.update(start=round(c.start, 2), end=round(c.end, 2), parts=c.parts, duration=round(total, 2))
    return res


def _shift(segs, off: float, lo: float, hi: float):
    from .transcribe import Segment, Word

    return [Segment(s.start - off, s.end - off, s.text,
                    [Word(w.start - off, w.end - off, w.text) for w in s.words])
            for s in segs if s.end >= lo and s.start <= hi]


def cmd_run(a) -> None:
    cmd_prepare(a)
    if a.mode == "agent":
        a.mode = "llm" if _has_llm() else "heuristic"
    cmd_find(a)
    cmd_render(a)


def _has_llm() -> bool:
    import os
    return any(os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL"))


def _gallery(results: list[dict], out: Path) -> None:
    cards = "\n".join(f"""<div class=card><video src="{html.escape(r['file'])}" controls preload=metadata></video>
<div class=meta><b class=score>{r['score']}</b><h3>{html.escape(r['title'] or '')}</h3>
<p>{html.escape(r['reason'] or '')}</p><p class=cap>{html.escape(r['caption'] or '')} {html.escape(' '.join(r['hashtags'] or []))}</p>
<small>{r['start']}s → {r['end']}s · {r['duration']}s · {r['layout']}</small></div></div>""" for r in results)
    (out / "index.html").write_text(f"""<!doctype html><meta charset=utf-8><title>Clips</title>
<style>body{{font:15px system-ui;background:#0e0e10;color:#eee;margin:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:20px}}
.card{{background:#1a1a1e;border-radius:14px;overflow:hidden}}video{{width:100%;display:block;background:#000}}
.meta{{padding:12px 14px}}.score{{float:right;background:#ffe600;color:#000;border-radius:20px;padding:2px 10px}}
h3{{margin:0 0 6px;font-size:16px}}p{{color:#aaa;margin:4px 0}}.cap{{color:#7fd}}small{{color:#666}}</style>
<h1>Clips</h1><div class=grid>{cards}</div>""")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="clip", description="Turn long videos into viral short clips.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def shared(sp, source=False):
        if source:
            sp.add_argument("source", help="YouTube/URL or local video file")
        sp.add_argument("-w", "--work", default="work", help="working folder (default: work)")
        sp.add_argument("-n", type=int, default=8, help="max clips (default 8)")
        sp.add_argument("--min", type=float, default=20, help="min clip length s")
        sp.add_argument("--max", type=float, default=60, help="max clip length s")

    def find_opts(sp):
        sp.add_argument("--mode", choices=["llm", "heuristic", "agent"], default="agent",
                        help="how to pick moments (run: agent→llm if key set, else heuristic)")
        sp.add_argument("--context", default="", help="what the video is about / audience")
        sp.add_argument("--model", default=None)

    def render_opts(sp):
        sp.add_argument("-o", "--out", default="clips")
        sp.add_argument("--aspect", default="9:16", help="9:16, 1:1, 4:5, 16:9")
        sp.add_argument("--height", type=int, default=1920)
        sp.add_argument("--layout", choices=["auto", "stack", "track", "center", "fit"], default="auto")
        sp.add_argument("--style", choices=["pop", "karaoke", "boxed", "minimal"], default="pop")
        sp.add_argument("--font", default=None, help="caption font family")
        sp.add_argument("--no-captions", action="store_true")
        sp.add_argument("--no-title", action="store_true")
        sp.add_argument("--fade-out", type=float, default=0.6)
        sp.add_argument("--music", default=None, help="background music file (auto-ducked)")
        sp.add_argument("--music-volume", type=float, default=0.12)
        sp.add_argument("--only", default="", help="render only these clip numbers, e.g. 1,3")

    def prep_opts(sp):
        sp.add_argument("--whisper", default="small", help="tiny/base/small/medium/large-v3")
        sp.add_argument("--language", default=None, help="force language, e.g. hi, en")
        sp.add_argument("--use-whisper", action="store_true",
                        help="URL: ignore YouTube captions, transcribe audio with Whisper (more accurate timing)")
        sp.add_argument("--full-download", action="store_true",
                        help="URL: download the whole video instead of only the clip sections")

    sp = sub.add_parser("doctor", help="check this machine is ready")
    sp.set_defaults(fn=lambda a: sys.exit(__import__("clipper.doctor", fromlist=["run"]).run()))
    sp = sub.add_parser("prepare"); shared(sp, True); prep_opts(sp); sp.set_defaults(fn=cmd_prepare)
    sp = sub.add_parser("find"); shared(sp); find_opts(sp); sp.set_defaults(fn=cmd_find)
    sp = sub.add_parser("render"); shared(sp); render_opts(sp); sp.set_defaults(fn=cmd_render)
    sp = sub.add_parser("run"); shared(sp, True); prep_opts(sp); find_opts(sp); render_opts(sp)
    sp.set_defaults(fn=cmd_run)

    a = p.parse_args(argv)
    try:
        a.fn(a)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
