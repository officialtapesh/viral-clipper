---
name: viral-clipper
description: Turn a long-form video (YouTube URL or local file) into any number of short vertical viral clips with virality scores, face-tracked 9:16 reframing, animated captions and hook titles, then after approval post them to YouTube Shorts, Instagram, Facebook, TikTok via the browser. Use when asked to make reels, shorts or highlight clips from a long video, or to post them.
---

# Viral Clipper

A free, open-source Opus Clip / Klap / Vizard alternative. You (Claude) act as
the editor who picks moments; the scripts do transcription and rendering.

All commands run from this skill's folder. Scripts live in `scripts/`.

## The flow

1. User gives a YouTube link and how many clips (e.g. 20 or 30). If no
   number is given, ask for one; the default is 10.
2. Transcribe, then pick the viral moments.
3. Render vertical reels with captions.
4. User approves.
5. Post to the platforms the user chose via the browser.

Pass the number as `-n`. For 20+ clips, use `--min 15 --max 60`, so a
1-hour video has enough room.

## 1. Setup (once per machine)

```bash
python3 scripts/setup.py
```
This creates `.venv`, installs everything (ffmpeg with caption support comes
from pip, so no Homebrew or apt is needed) and runs `doctor`. It's safe to re-run.
`scripts/clip.py` uses `.venv` automatically.

If `doctor` says YouTube or Hugging Face is unreachable, you are in a
sandbox with limited internet. Don't fight it. Either ask the user for the
video file (and pass its path instead of the URL), or run the commands on the
user's own computer, where the internet is open.

## 2. Prepare: transcript only, no video download

```bash
python3 scripts/clip.py prepare "<youtube-url-or-file>" -w work -n 8 --min 20 --max 60
```
For a URL, the **whole video is never downloaded**:
- It reads the video's own captions (human or auto, any language), which takes seconds and only a few KB.
- If there are no captions, it downloads the **audio only** (about 10% of the size) and transcribes it with Whisper.
- At render time, only the seconds each clip needs are downloaded.

Options: `--language hi` picks the caption or transcription language.
`--use-whisper` ignores captions and transcribes the audio, for tighter word timing.
`--full-download` gets the whole video (rarely needed). For local files, Whisper
runs on the file (`--whisper medium` or `large-v3` for accuracy).
Writes `work/transcript.txt` (`[start-end] text`) and `work/PICK_CLIPS.md`.

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

For long transcripts, read in chunks and keep a running shortlist, or run
`python3 scripts/clip.py find -w work --mode heuristic -n 15` first for a
candidate list, then read those windows closely and decide yourself.

### Editing rules (every video)

1. **Hook first, always.** If the strongest line (the reveal, the shock,
   the punchline) comes later in the moment, build a **cold open** with
   `parts`: that line first (3-6s), then the story from its start.
   Example: `"parts": [[37.4, 42.1], [9.9, 33.5], [42.1, 49.0]]`.
2. **Show, don't just tell.** If the speaker refers to something that
   happened on screen (a crash, a goal, a fail, a reveal), find that moment
   in the transcript (the live reaction: "अबे", "oh no", "wait wait") and put
   it in the clip, usually first, before the explanation.
3. **Cut the filler.** Drop sentences that repeat or explain what was
   already shown; use extra `parts` to jump over them.
4. **End on a payoff or a cliffhanger** ("the reason I'll tell you…",
   the twist, the result). Never mid-thought. Endings fade out smoothly.
5. **Layout is automatic, never blurred backgrounds:**
   - streamer face cam in a corner → `stack`: two equal boxes, gameplay on
     top, the creator's face below, captions in the centre. The cam is found
     once per video and saved to `work/facecam.json`; **look at
     `work/facecam_check.jpg`** (yellow box = detected cam) before trusting it.
     If it's wrong, re-render with `--facecam x,y,w,h` (source pixels) or
     `--facecam none`.
   - talking head / podcast → `track`: the crop follows the speaker's face
   - no faces → `center`: zoom into the main shot
6. Keep each clip 25-60s; aim for ~35-50s.

Without an agent, use `python3 scripts/clip.py find -w work --mode llm` (needs
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or a local Ollama via `OPENAI_BASE_URL`)
or `--mode heuristic`, which works fully offline.

## 4. Render

```bash
python3 scripts/clip.py render -w work -o clips --style pop
```
Options:
| flag | values |
|---|---|
| `--aspect` | `9:16` (default), `1:1`, `4:5`, `16:9` |
| `--layout` | `auto` (face cam → `stack`, speaker → `track`, else `center`), `stack`, `track`, `center`, `fit` (blurred bg, only if asked) |
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

## 6. Approval

Never post anything without the user's approval. Send the clips (or
`clips/index.html`) with a short table: number, score, title, length.
Ask which ones to post and which to drop or redo (e.g. "re-render 4 with
boxed captions"). Apply the edits, then ask again. Only approved clips
move on to posting.

## 7. Post to social media

Ask which platforms to post to (YouTube Shorts, Instagram Reels, Facebook
Reels, TikTok, LinkedIn, X) and whether to post now or space the clips
out (recommended: 1-3 per platform per day; bulk uploads get throttled).

Use a browser: the built-in browser or Claude in Chrome, whichever the
user prefers. Load that browser's skill first. For each platform:

1. Open the platform's upload page in a new tab
   (studio.youtube.com, instagram.com, business.facebook.com,
   tiktok.com/upload). If it isn't logged in, ask the user to log in
   there themselves and say "done". Never type passwords or OTPs.
2. Upload the MP4, paste the caption and hashtags from
   `clips/clips.json`, and set the title (YouTube: title max 100 chars,
   add `#Shorts`).
3. Use the platform's own scheduler if the user wants the posts spaced out.
4. Before clicking the final Post/Publish button, show the user what's
   filled in and confirm. Once they say "post all", you can go
   ahead for the rest of that batch.
5. Copy the live post URL into `clips/posted.json`
   (`{"clip": 1, "platform": "youtube", "url": "...", "at": "..."}`).

If a platform blocks automation or asks for a captcha, stop and hand that
step to the user.

Only post videos the user owns or has the rights to clip.

## One-shot (no agent)
```bash
python3 scripts/clip.py run "<url-or-file>" -o clips
```
