"""Viral Clipper web app: make shorts from any device, iPad included.

Upload a long video (or paste a link), choose how many clips, and get
vertical shorts with captions back. Same engine as the CLI / Claude skill.

Run locally:   python3 webapp/app.py   → http://localhost:7860
Hosted:        a Hugging Face Space (see webapp/space/), free CPU.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import gradio as gr

REPO = Path(__file__).resolve().parents[1]
CLIP = REPO / "scripts" / "clip.py"
JOBS = Path(os.environ.get("CLIPPER_JOBS", "/tmp/viral-clipper-jobs"))
KEEP_HOURS = 3

INTRO = """
# 🎬 Viral Clipper
**Long video in → viral vertical shorts out.** Free and open source
([GitHub](https://github.com/officialtapesh/viral-clipper)).

1. **Upload a video** (most reliable) *or* paste a YouTube link.
2. Choose how many clips and press **Make shorts**.
3. Preview, then download. Gaming videos with a face cam get gameplay on top and the creator below automatically.

⏱️ This free server is slow. Roughly: a YouTube link with captions takes a few minutes;
an uploaded 30-minute video takes 10-20 minutes (it has to be transcribed first).
"""


def _cleanup() -> None:
    JOBS.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - KEEP_HOURS * 3600
    for d in JOBS.iterdir():
        try:
            if d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def make_shorts(video, url, n, min_len, max_len, language, layout, style, accuracy,
                openai_key, anthropic_key, progress=gr.Progress()):
    _cleanup()
    source = None
    if video:
        source = video if isinstance(video, str) else getattr(video, "name", None)
    elif url and url.strip():
        source = url.strip()
    if not source:
        raise gr.Error("Upload a video or paste a link first.")
    if url and url.strip() and not source.startswith("http") and video is None:
        raise gr.Error("That link doesn't look right (it should start with https://).")

    job = JOBS / uuid.uuid4().hex[:12]
    work, out = job / "work", job / "clips"
    job.mkdir(parents=True)
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    mode = "heuristic"
    if openai_key and openai_key.strip():
        env["OPENAI_API_KEY"] = openai_key.strip()
        mode = "llm"
    if anthropic_key and anthropic_key.strip():
        env["ANTHROPIC_API_KEY"] = anthropic_key.strip()
        mode = "llm"

    cmd = [sys.executable, str(CLIP), "run", source, "-w", str(work), "-o", str(out),
           "-n", str(int(n)), "--min", str(min_len), "--max", str(max(max_len, min_len + 5)),
           "--mode", mode, "--layout", layout, "--style", style,
           "--whisper", "small" if accuracy.startswith("Better") else "base"]
    if language != "auto":
        cmd += ["--language", language]

    log_lines: list[str] = []
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            cwd=str(REPO), env=env, bufsize=1)
    steps = {"Reading video info": 0.05, "Fetching captions": 0.1, "Getting source": 0.05,
             "Transcribing": 0.15, "Finding moments": 0.5, "→ [": 0.6, "✓": 0.95}
    for line in proc.stdout:
        line = line.rstrip()
        if not line or "%" in line and "[download]" in line:
            continue
        log_lines.append(line)
        for key, frac in steps.items():
            if key in line:
                progress(frac, desc=line.strip()[:80])
        yield "\n".join(log_lines[-40:]), None, None, ""
    rc = proc.wait()

    if rc != 0:
        hint = ""
        joined = "\n".join(log_lines)
        if "Sign in to confirm" in joined or "403" in joined or "Couldn't read video info" in joined:
            hint = ("\n\n⚠️ YouTube blocked this server. Download the video and **upload the file** "
                    "instead; that always works.")
        yield "\n".join(log_lines[-60:]) + hint, None, None, "❌ Something went wrong. See the log above."
        return

    meta = json.loads((out / "clips.json").read_text(encoding="utf-8")) if (out / "clips.json").exists() else []
    videos = [str(out / m["file"]) for m in meta if (out / m["file"]).exists()]
    gallery = [(v, f"{m['score']} · {m['title']}") for v, m in zip(videos, meta)]
    notes = ["## Your shorts\n"]
    for i, m in enumerate(meta, 1):
        tags = " ".join(m.get("hashtags") or [])
        notes.append(f"**{i}. {m['title']}** — score {m['score']}, {m['duration']:.0f}s, layout `{m['layout']}`  \n"
                     f"{m.get('reason') or ''}  \n"
                     f"Caption: {m.get('caption') or ''} {tags}\n")
    if mode == "heuristic":
        notes.append("\n_Moments picked by the free built-in scorer. For smarter picks, add an OpenAI or "
                     "Claude API key, or use the Claude skill / Codex (see GitHub)._")
    yield "\n".join(log_lines[-20:]), gallery, videos, "\n".join(notes)


with gr.Blocks(title="Viral Clipper") as demo:
    gr.Markdown(INTRO)
    with gr.Row():
        with gr.Column(scale=1):
            video = gr.File(label="Upload video", file_types=["video"], type="filepath")
            url = gr.Textbox(label="…or paste a YouTube link", placeholder="https://www.youtube.com/watch?v=…")
            n = gr.Slider(1, 10, value=3, step=1, label="How many shorts")
            with gr.Row():
                min_len = gr.Slider(10, 60, value=20, step=5, label="Min length (s)")
                max_len = gr.Slider(20, 90, value=55, step=5, label="Max length (s)")
            with gr.Accordion("Style options", open=False):
                language = gr.Dropdown(["auto", "hi", "en"], value="auto", label="Language")
                layout = gr.Dropdown(["auto", "stack", "track", "center"], value="auto",
                                     label="Layout (auto: face cam → gameplay + face, speaker → follow face)")
                style = gr.Dropdown(["pop", "karaoke", "boxed", "minimal"], value="pop", label="Caption style")
                accuracy = gr.Radio(["Fast", "Better (slower)"], value="Fast", label="Transcription")
            with gr.Accordion("Smarter AI picks (optional, your own key)", open=False):
                gr.Markdown("Keys are used only for this request and are never stored.")
                openai_key = gr.Textbox(label="OpenAI API key", type="password")
                anthropic_key = gr.Textbox(label="Anthropic (Claude) API key", type="password")
            go = gr.Button("🎬 Make shorts", variant="primary", size="lg")
        with gr.Column(scale=1):
            gallery = gr.Gallery(label="Preview", columns=2, height="auto", object_fit="contain")
            files = gr.Files(label="Download")
            notes = gr.Markdown()
            log = gr.Textbox(label="Progress", lines=10, max_lines=20, autoscroll=True)

    go.click(make_shorts, [video, url, n, min_len, max_len, language, layout, style, accuracy,
                           openai_key, anthropic_key], [log, gallery, files, notes])

demo.queue(default_concurrency_limit=1, max_size=20)

if __name__ == "__main__":
    share = "--share" in sys.argv or bool(os.environ.get("COLAB_RELEASE_TAG"))
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)),
                max_file_size="2gb", share=share)
