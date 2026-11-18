# Test media

`sample_talk.mp4`: a synthetic 52-second test video (generated test pattern + espeak-ng voice reading `sample_talk.txt`). Free to use; handy for checking that transcription → picking → rendering works:

```bash
python3 scripts/clip.py run tests/sample_talk.mp4 -n 1 --min 10 --max 40 --mode heuristic
```
