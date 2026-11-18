# 🎬 viral-clipper

**Free, open-source AI clipping.** Turns long videos (podcasts, interviews, talks, YouTube links) into short vertical clips ready for Reels, Shorts and TikTok. It's an open alternative to Opus Clip, Klap and Vizard that runs on your own machine.

```bash
python scripts/clip.py run "https://youtube.com/watch?v=..." -o clips
```

## What it does

| Feature | viral-clipper | How |
|---|---|---|
| Find viral moments | ✅ | AI or offline heuristic, scored 0-100 |
| Virality score + reason | ✅ | hook / standalone / payoff / emotion / pace rubric |
| Auto-reframe to 9:16 | ✅ | face tracking with a smooth "camera operator" (no jitter) |
| No face? Smart fallback | ✅ | blurred-background fit layout |
| Animated captions | ✅ | 4 styles: `pop`, `karaoke`, `boxed`, `minimal` |
| Keyword highlighting | ✅ | numbers and power words coloured |
| Hook title overlay | ✅ | first 3 seconds |
| Hindi / Hinglish / 90+ languages | ✅ | Whisper |
| Background music, auto-ducked | ✅ | `--music track.mp3` |
| Smooth endings (no hard cuts) | ✅ | audio + video fade |
| Aspect ratios | ✅ | 9:16, 1:1, 4:5, 16:9 |
| Post captions + hashtags | ✅ | in `clips.json` |
| Preview gallery | ✅ | `clips/index.html` |
| Approve, then auto-post | ✅ | YouTube, Instagram, Facebook, TikTok via Claude's browser (as a skill) |
| Cost | **₹0** | everything local; AI picking is optional |

## Install

```bash
git clone https://github.com/<you>/viral-clipper && cd viral-clipper
pip install -r requirements.txt
# plus ffmpeg: brew install ffmpeg | sudo apt install ffmpeg | winget install ffmpeg
```

## Three ways to pick moments

1. **As a Claude skill (recommended, free).** Upload this folder as a skill, or use it in Claude Code. Claude reads the transcript and picks the clips like an editor would. No API key needed. See [`SKILL.md`](SKILL.md).
2. **LLM mode.** `--mode llm` with `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`. For **100% free**, run a local model with [Ollama](https://ollama.com):
   ```bash
   export OPENAI_BASE_URL=http://localhost:11434/v1 OPENAI_API_KEY=ollama CLIPPER_MODEL=llama3.1
   ```
3. **Heuristic mode.** `--mode heuristic` works fully offline and scores hooks, questions, numbers, emotion and pace.

## Step by step

```bash
python scripts/clip.py prepare video.mp4 -w work --language hi   # transcribe
python scripts/clip.py find    -w work --mode llm -n 10          # pick clips
#   …edit work/clips.json by hand if you like…
python scripts/clip.py render  -w work -o clips --style pop --music bgm.mp3
```

**Useful flags:** `--min/--max` sets clip length, `--whisper large-v3` gives better transcripts, `--layout fit|track|center` controls the reframe, `--font "Montserrat ExtraBold"` sets the caption font (or drop `.ttf` files into `fonts/`), and `--only 2,5` re-renders specific clips.

## How it works

```
URL/file ─► yt-dlp ─► faster-whisper (word timestamps)
         ─► moment finder (Claude / LLM / heuristic) ─► snap to sentence edges
         ─► face tracking (OpenCV) ─► dead-zone camera smoothing ─► crop
         ─► ASS animated captions + hook title ─► ffmpeg (fades, music ducking) ─► MP4
```

## Tips

- For background music and SFX, use royalty-free tracks (e.g. Pixabay).
- Podcasts with two speakers: `track` follows whoever is largest in frame, and switches smoothly.
- Captions in Hindi script need a Devanagari font: `--font "Noto Sans Devanagari"`.

## License

MIT. Use it, fork it, ship it.
