# AGENTS.md: instructions for AI coding agents

This file is for **OpenAI Codex / ChatGPT**, and any agent that reads `AGENTS.md`
(Cursor, Gemini CLI, Aider, etc.). Claude reads the same workflow from `SKILL.md`.

You are the editor. The user gives a video link (or file) and a number of
clips. You return finished vertical shorts. The scripts do the heavy work;
you decide what to show.

## Workflow

```bash
python3 scripts/setup.py                                      # once; safe to re-run
python3 scripts/clip.py prepare "<link-or-file>" -w work -n <N> --min 20 --max 60
# read work/transcript.txt + work/PICK_CLIPS.md, then write work/clips.json
python3 scripts/clip.py render -w work -o clips
```

- `prepare` with a URL **never downloads the whole video**: it reads the
  captions (or audio only) and only the chosen sections are downloaded at render time.
- If `doctor` / `prepare` says YouTube is unreachable, you're in a sandbox
  without internet. Ask the user to run this on their own computer, or for the video file.
- `python3 scripts/clip.py doctor` diagnoses setup problems.

## clips.json

```json
[{"parts": [[37.4, 42.1], [9.9, 33.5], [72.7, 76.6]], "score": 91,
  "title": "max 7 words, in the video's language", "hook": "opening line",
  "reason": "why it will perform", "caption": "post caption",
  "hashtags": ["#a", "#b", "#c"]}]
```
Use `start`/`end` for one range, or `parts` (played in order) for an edit.

## Editing rules (every video)

1. **Hook first.** If the reveal or punchline comes later, make a cold open with
   `parts`: that line first (3-6s), then the story from its start.
2. **Show, don't tell.** If the speaker reacts to something on screen (a crash,
   a goal, a fail), include that moment, usually first. Look for live reactions
   in the transcript ("अबे", "wait wait", "oh no").
3. **Cut the filler.** Use extra parts to skip repeats.
4. **End on a payoff or a cliffhanger**, never mid-thought. Endings fade out smoothly.
5. Aim for 35-50s per clip, with no overlaps. Score 0-100: hook 30, standalone 25,
   payoff 20, emotion 15, pace 10.

## Layout (automatic, never blurred backgrounds)

- Streamer face cam in a corner → `stack`: two equal boxes, gameplay on top,
  the creator's face below, captions centred. Check `work/facecam_check.jpg`;
  fix with `--facecam x,y,w,h` or `--facecam none`.
- Talking head → `track` (follows the speaker). No faces → `center`.

## Before handing over

Grab a frame from each clip (`ffmpeg -ss 2 -i clip.mp4 -frames:v 1 f.png`) and look
at it: is the action visible, are the captions readable? Re-render one clip with
`--only N`. Then give the user each clip's title, score, reason, caption and hashtags.

## Posting

Never post without the user's explicit approval. If you have a browser tool,
upload through the platform's own site with the user logged in (never type
passwords or OTPs), and confirm before clicking Publish. Only post videos the user
owns or has the rights to clip.

## Picking moments without an agent

`python3 scripts/clip.py run "<link>" -n 5 --mode llm` uses `OPENAI_API_KEY` (set
`CLIPPER_MODEL` to choose the model), `ANTHROPIC_API_KEY`, or any OpenAI-compatible
server (`OPENAI_BASE_URL`, e.g. local Ollama). `--mode heuristic` needs no AI.
