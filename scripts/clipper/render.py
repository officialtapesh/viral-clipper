"""Render one clip: reframe -> captions -> hook title -> smooth fades -> music."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import reframe as rf
from .captions import PRESETS, CaptionStyle, build_ass
from .highlights import Clip
from .tools import FONTS, ffmpeg
from .transcribe import Segment, words_between


DEVANAGARI = re.compile(r"[\u0900-\u097F]")


@dataclass
class RenderOptions:
    aspect: str = "9:16"
    height: int = 1920
    layout: str = "auto"          # auto | track | fit | center
    caption_style: str = "pop"
    font: str | None = None
    captions: bool = True
    title: bool = True
    fade_in: float = 0.15
    fade_out: float = 0.6         # smooth ending, never a hard cut
    music: Path | None = None
    music_volume: float = 0.12
    crf: int = 20
    fps: float = 30.0
    min_face_coverage: float = 0.35


def slugify(text: str, n: int = 40) -> str:
    s = re.sub(r"[^\w\s-]", "", text, flags=re.U).strip().lower()
    return re.sub(r"[\s_-]+", "-", s)[:n].strip("-") or "clip"


def _audio_filter(dur: float, opt: RenderOptions, has_music: bool) -> tuple[str, str]:
    fo = min(opt.fade_out, dur / 3)
    voice = (f"[1:a]aresample=48000,afade=t=in:d={opt.fade_in},"
             f"afade=t=out:st={dur - fo:.3f}:d={fo:.3f}[voice]")
    if not has_music:
        return voice, "[voice]"
    # loop music, duck it under speech, fade both ends
    mus = (f"[2:a]aresample=48000,volume={opt.music_volume},atrim=0:{dur:.3f},"
           f"afade=t=in:d=0.8,afade=t=out:st={max(dur - 1.2, 0):.3f}:d=1.2[mus];"
           f"[voice]asplit=2[v1][vsc];"
           f"[mus][vsc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck];"
           f"[v1][duck]amix=inputs=2:duration=first:normalize=0[aout]")
    return voice + ";" + mus, "[aout]"


def render_clip(src: Path, clip: Clip, segments: list[Segment], out_path: Path,
                opt: RenderOptions, info: rf.VideoInfo | None = None) -> dict:
    info = info or rf.probe(src)
    out_w, out_h = rf.output_size(opt.aspect, opt.height)
    dur = clip.end - clip.start
    fps = opt.fps
    n_frames = int(round(dur * fps))
    work = out_path.parent / f".{out_path.stem}"
    work.mkdir(parents=True, exist_ok=True)

    # 1. decide layout
    src_aspect = info.width / info.height
    target_aspect = out_w / out_h
    layout = opt.layout
    centres: list = []
    if layout in ("auto", "track") and src_aspect > target_aspect + 0.01:
        centres = rf.analyze_faces(src, clip.start, dur, info)
        cov = rf.face_coverage(centres)
        if layout == "auto":
            layout = "track" if cov >= opt.min_face_coverage else "fit"
    elif layout == "auto":
        layout = "center"

    # 2. captions + title
    caption_y = None
    if layout == "fit":
        # video sits in the middle band; put captions just under it
        band = out_w / src_aspect / out_h
        caption_y = min(0.5 + band / 2 + 0.07, 0.86)
    ass_file = None
    if opt.captions or (opt.title and clip.title):
        style = CaptionStyle(**{**PRESETS[opt.caption_style].__dict__})
        words = words_between(segments, clip.start, clip.end) if opt.captions else []
        if opt.font:
            style.font = opt.font
        elif DEVANAGARI.search(clip.title + " ".join(w.text for w in words)):
            style.font = "Noto Sans Devanagari ExtraBold"
            style.uppercase = False
        ass = build_ass(words, clip.start, clip.end, out_w, out_h, style,
                        title=clip.title if opt.title else "", caption_y=caption_y)
        ass_file = work / "subs.ass"
        ass_file.write_text(ass, encoding="utf-8")

    fo = min(opt.fade_out, dur / 3)
    ass_f = ""
    if ass_file:
        ass_f = f",ass={ass_file.name}"
        if FONTS.is_dir():
            shutil.copytree(FONTS, work / "fonts", dirs_exist_ok=True)  # relative path: no escaping issues on Windows
            ass_f += ":fontsdir=fonts"
    finish = (f"fade=t=in:d={opt.fade_in},fade=t=out:st={dur - fo:.3f}:d={fo:.3f}"
              + ass_f + ",format=yuv420p")

    # 3. build ffmpeg graph
    music = opt.music if opt.music and Path(opt.music).exists() else None
    a_graph, a_out = _audio_filter(dur, opt, bool(music))
    common_out = ["-map", "[vout]", "-map", a_out,
                  "-c:v", "libx264", "-preset", "veryfast", "-crf", str(opt.crf),
                  "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                  "-t", f"{dur:.3f}", str(out_path.resolve())]
    music_in = ["-stream_loop", "-1", "-i", str(Path(music).resolve())] if music else []
    audio_in = ["-ss", f"{clip.start:.3f}", "-t", f"{dur:.3f}", "-i", str(src)]

    if layout == "track":
        cam = rf.camera_path(centres, n_frames, crop_frac=(info.height * target_aspect) / info.width)
        v_graph = f"[0:v]{finish}[vout]"
        cmd = ([ffmpeg(), "-y", "-v", "error",
                "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{out_w}x{out_h}", "-r", str(fps), "-i", "-"]
               + audio_in + music_in
               + ["-filter_complex", v_graph + ";" + a_graph] + common_out)
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, cwd=work)
        for frame in rf.tracked_frames(src, clip.start, dur, info, cam, out_w, out_h, fps):
            proc.stdin.write(frame)
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed rendering {out_path.name}")
    else:
        if layout == "fit":
            v_graph = (f"[0:v]fps={fps},split=2[bg][fg];"
                       f"[bg]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                       f"crop={out_w}:{out_h},boxblur=28:2,eq=brightness=-0.12[bgb];"
                       f"[fg]scale={out_w}:-2[fgs];"
                       f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,{finish}[vout]")
        else:  # center crop
            v_graph = (f"[0:v]fps={fps},scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                       f"crop={out_w}:{out_h},{finish}[vout]")
        cmd = ([ffmpeg(), "-y", "-v", "error", "-ss", f"{clip.start:.3f}", "-t", f"{dur:.3f}", "-i", str(src)]
               + audio_in + music_in
               + ["-filter_complex", v_graph + ";" + a_graph] + common_out)
        subprocess.run(cmd, check=True, cwd=work)

    return {"file": out_path.name, "layout": layout, "duration": round(dur, 2),
            "start": round(clip.start, 2), "end": round(clip.end, 2), "score": clip.score,
            "title": clip.title, "reason": clip.reason, "caption": clip.caption,
            "hashtags": clip.hashtags}
