# 🎬 viral-clipper

**Free, open-source AI clipping.** Turns long videos (podcasts, interviews, talks, YouTube links) into short vertical clips ready for Reels, Shorts and TikTok. It's an open alternative to Opus Clip, Klap and Vizard that runs on your own machine.

```bash
python3 scripts/clip.py run "https://youtube.com/watch?v=..." -o clips
```

## What it does

| Feature | viral-clipper | How |
|---|---|---|
| **No full video download** | ✅ | reads YouTube captions, then downloads only the clip sections |
| Find viral moments | ✅ | AI or offline heuristic, scored 0-100 |
| Virality score + reason | ✅ | hook / standalone / payoff / emotion / pace rubric |
| Gaming / streamer layout | ✅ | auto-detects the face cam → gameplay on top, streamer below |
| Auto-reframe to 9:16 | ✅ | face tracking with a smooth "camera operator" (no jitter) |
| Cold-open hooks | ✅ | multi-part edits: punchline first, then the story |
| Shows the action | ✅ | pulls in the on-screen moment the speaker reacts to |
| Animated captions | ✅ | 4 styles: `pop`, `karaoke`, `boxed`, `minimal` |
| Keyword highlighting | ✅ | numbers and power words coloured |
| Hook title overlay | ✅ | first 3 seconds |
| Hindi / Hinglish / 90+ languages | ✅ | Whisper + bundled Devanagari font |
| Background music, auto-ducked | ✅ | `--music track.mp3` |
| Smooth endings (no hard cuts) | ✅ | audio + video fade |
| Aspect ratios | ✅ | 9:16, 1:1, 4:5, 16:9 |
| Post captions + hashtags | ✅ | in `clips.json` |
| Preview gallery | ✅ | `clips/index.html` |
| Approve, then auto-post | ✅ | YouTube, Instagram, Facebook, TikTok via Claude's browser (as a skill) |
| One-command setup | ✅ | `python3 scripts/setup.py` (ffmpeg + fonts included) |
| Cost | **₹0** | everything local; AI picking is optional |

## Quick start (for testers)

1. Unzip, and put the `viral-clipper` folder somewhere permanent (e.g. `Movies/`).
2. **macOS:** right-click `Install Helper.command` → **Open** → **Open** (the first time only,
   because macOS blocks double-clicking downloaded scripts).
   **Windows:** double-click `Install Helper (Windows).bat`.
   You only need Python 3 installed ([python.org](https://www.python.org/downloads/));
   setup gets everything else, including its own Python 3.12 if yours is older.
3. In the **Claude desktop app**: add the skill (`SKILL.md`, or upload this zip as a skill),
   then connect the `viral-clipper` folder (+ → Add folder).
4. Ask Claude: *"Make 3 shorts from https://youtube.com/watch?v=…"*

## Install

```bash
git clone https://github.com/<you>/viral-clipper && cd viral-clipper
python3 scripts/setup.py      # one command: installs everything, incl. ffmpeg + fonts
```
Only Python 3.9+ is needed ([python.org](https://www.python.org/downloads/)). The setup installs a private `.venv` with ffmpeg (captions included), the speech model loader and face tracking, then runs `python3 scripts/clip.py doctor` to confirm everything works. You don't need Homebrew, apt or any manual ffmpeg install.

## Use it from the Claude app (desktop or phone)

Claude's cloud sandbox can't reach YouTube, so a tiny **helper** runs the
download and render jobs on your own computer:

1. Double-click **`Install Helper.command`** (macOS) or **`Install Helper (Windows).bat`** once.
   It sets everything up and starts the helper at every login.
2. In the Claude app, connect this folder and add the skill.
3. Ask: *"Make 10 shorts from https://youtube.com/watch?v=…"*. Claude picks the
   moments, the helper renders them, and the clips come back in the chat.
   This works from your phone too, as long as your computer is on and the
   Claude desktop app is open.

The helper only accepts two job types (`prepare`, `render`) with validated
settings, so it never runs arbitrary commands. Remove it any time with
`python3 scripts/install_helper.py --uninstall`.

## No computer? Use it from an iPad / phone via Claude Code (cloud)

1. Open **Claude Code** (claude.ai/code, or Code in the Claude app) and connect this GitHub repo.
2. Edit the cloud environment: under **Network access**, keep *Allow package managers* and add
   these allowed domains: `youtube.com`, `googlevideo.com`, `ytimg.com`, `huggingface.co`, `hf.co`
   (or choose **Full**).
3. Ask: *"Read SKILL.md and make 5 shorts from <YouTube link>"*.

Everything runs in Claude's cloud. Note: YouTube sometimes blocks downloads from cloud servers
("confirm you're not a bot"). If that happens, use the helper on a home computer instead.

## Three ways to pick moments

1. **As a Claude skill (recommended, free).** Upload this folder as a skill, or use it in Claude Code. Claude reads the transcript and picks the clips like an editor would. No API key needed. See [`SKILL.md`](SKILL.md).
2. **LLM mode.** `--mode llm` with `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`. For **100% free**, run a local model with [Ollama](https://ollama.com):
   ```bash
   export OPENAI_BASE_URL=http://localhost:11434/v1 OPENAI_API_KEY=ollama CLIPPER_MODEL=llama3.1
   ```
3. **Heuristic mode.** `--mode heuristic` works fully offline and scores hooks, questions, numbers, emotion and pace.

## Step by step

```bash
python3 scripts/clip.py prepare video.mp4 -w work --language hi   # transcribe
python3 scripts/clip.py find    -w work --mode llm -n 10          # pick clips
#   …edit work/clips.json by hand if you like…
python3 scripts/clip.py render  -w work -o clips --style pop --music bgm.mp3
```

**Useful flags:** `--min/--max` sets clip length, `--whisper large-v3` gives better transcripts, `--layout fit|track|center` controls the reframe, `--font "Montserrat ExtraBold"` sets the caption font (or drop `.ttf` files into `fonts/`), and `--only 2,5` re-renders specific clips.

## How it works

```
URL ─► YouTube captions (few KB; else audio-only + Whisper)    file ─► faster-whisper
         ─► moment finder (Claude / LLM / heuristic) ─► snap to sentence edges
         ─► download ONLY the chosen sections ─► face tracking (OpenCV) ─► dead-zone camera smoothing ─► crop
         ─► ASS animated captions + hook title ─► ffmpeg (fades, music ducking) ─► MP4
```

## Tips

- For background music and SFX, use royalty-free tracks (e.g. Pixabay).
- Podcasts with two speakers: `track` follows whoever is largest in frame, and switches smoothly.
- Hindi (Devanagari) is detected automatically and uses the bundled Noto Sans Devanagari font.

## License

MIT. Use it, fork it, ship it.
