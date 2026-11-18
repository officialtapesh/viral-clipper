---
name: viral-clipper
description: Turn a long-form video (podcast, interview, talk, YouTube URL or local file) into short vertical viral clips with virality scores, face-tracked 9:16 reframing, animated word-by-word captions and hook titles. Use when asked to make reels, shorts, TikToks or highlight clips from a long video.
---

# Viral Clipper

A free, open-source Opus Clip / Klap / Vizard alternative. You (Claude) act as
the editor who picks moments; the scripts do transcription and rendering.

All commands run from this skill's folder. Scripts live in `scripts/`.

## 1. Setup (once per machine)

```bash
pip install -r requirements.txt     # faster-whisper, opencv<5, yt-dlp, numpy
ffmpeg -version                     # must exist, built with libass
```
If ffmpeg is missing: `brew install ffmpeg` / `sudo apt install ffmpeg` / `winget install ffmpeg`.

## 2. Prepare: download and transcribe

```bash
python scripts/clip.py prepare "<youtube-url-or-file>" -w work -n 8 --min 20 --max 60
```
- Add `--language hi` for Hindi or Hinglish (auto-detect works too).
- Use `--whisper medium` or `large-v3` for better accuracy; `base` is faster.
- Writes `work/transcript.txt` (`[start-end] text`) and `work/PICK_CLIPS.md`.

## 3. Pick the clips yourself (agent mode, no API key)

Read `work/PICK_CLIPS.md` and `work/transcript.txt`, then write
`work/clips.json`. Think like a top short-form editor:

- **Hook first.** Start on the line that stops the scroll, not on "so", "um"
  or setup. A bold claim, a question, a conflict, a surprising number.
- **Standalone.** A stranger must understand it with zero context.
- **Payoff.** End right after the punchline or insight lands. Never mid-thought.
- **Score honestly** 0-100 (hook 30, standalone 25, payoff 20, emotion 15, pace 10).
- **Title** is the on-screen hook: 7 words max, punchy, in the video's language.
- Give each clip a post `caption` and 3-5 `hashtags`. No overlapping clips.

For long transcripts, read in chunks and keep a running shortlist.

Without an agent, use `python scripts/clip.py find -w work --mode llm` (needs
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or a local Ollama via `OPENAI_BASE_URL`)
or `--mode heuristic`, which works fully offline.

## 4. Render

```bash
python scripts/clip.py render -w work -o clips --style pop
```
Options:
| flag | values |
|---|---|
| `--aspect` | `9:16` (default), `1:1`, `4:5`, `16:9` |
| `--layout` | `auto` (track faces, else blurred-fit), `track`, `fit`, `center` |
| `--style` | `pop` (Opus-style), `karaoke`, `boxed` (Hormozi), `minimal` |
| `--font` | any installed font, or drop `.ttf` files in `fonts/` |
| `--music file.mp3` | background music, auto-ducked under speech |
| `--only 1,3` | re-render specific clips |
| `--no-title`, `--no-captions`, `--fade-out 0.6` | |

Every clip ends with a smooth audio and video fade, never a hard cut.

Output: `clips/NN_SCORE_title.mp4`, `clips/clips.json` with metadata and
`clips/index.html`, a preview gallery.

## 5. Check before you hand over

Grab a frame from each clip
(`ffmpeg -ss 2 -i clip.mp4 -frames:v 1 f.png`) and look at it: is the face
in frame, are the captions readable and not covering the face? If the
reframe is wrong, re-render that clip with `--layout fit` or `center`.
Tell the user the top clips with their score and why each will work.

## One-shot (no agent)
```bash
python scripts/clip.py run "<url-or-file>" -o clips
```
