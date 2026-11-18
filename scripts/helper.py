#!/usr/bin/env python3
"""viral-clipper helper: runs clip jobs on this computer, where the internet is open.

Claude (in the desktop or mobile app) can reach a folder on your computer but
its own sandbox can't reach YouTube. This helper bridges that gap safely:

  jobs/<job-id>/request.json   ← Claude writes a job here
  jobs/<job-id>/status.json    → helper reports progress / result
  jobs/<job-id>/log.txt        → full output
  jobs/helper.json             → heartbeat, so Claude knows the helper is running

It only runs two actions, `prepare` and `render`, with strictly validated
settings. It never runs shell commands or anything else a file asks for.

    python3 scripts/helper.py            # run in the foreground
    python3 scripts/install_helper.py    # start automatically at login
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLIP = REPO / "scripts" / "clip.py"
VERSION = 1

URL_RE = re.compile(r"^https?://[^\s'\"<>]+$")
LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{1,8})?$")
FACECAM_RE = re.compile(r"^(auto|none|\d{1,5},\d{1,5},\d{1,5},\d{1,5})$")
ONLY_RE = re.compile(r"^\d{1,3}(,\d{1,3})*$")
LAYOUTS = {"auto", "stack", "track", "center", "fit"}
STYLES = {"pop", "karaoke", "boxed", "minimal"}
ASPECTS = {"9:16", "1:1", "4:5", "16:9"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _num(v, lo, hi, cast=float):
    v = cast(v)
    if not lo <= v <= hi:
        raise ValueError(f"{v} not in [{lo}, {hi}]")
    return v


def build_command(req: dict, job: Path) -> list[str]:
    """Turn a request into an argv list. Anything unexpected is rejected."""
    action = req.get("action")
    work = str(job / "work")
    common = ["--min", str(_num(req.get("min", 20), 5, 600)), "--max", str(_num(req.get("max", 60), 5, 600))]
    if action == "prepare":
        url = str(req.get("url", ""))
        if not URL_RE.match(url):
            raise ValueError("url must be a plain http(s) link")
        cmd = [sys.executable, str(CLIP), "prepare", url, "-w", work,
               "-n", str(_num(req.get("n", 10), 1, 100, int))] + common
        if req.get("language"):
            if not LANG_RE.match(str(req["language"])):
                raise ValueError("bad language code")
            cmd += ["--language", str(req["language"])]
        if req.get("use_whisper"):
            cmd += ["--use-whisper"]
        return cmd
    if action == "render":
        cmd = [sys.executable, str(CLIP), "render", "-w", work, "-o", str(job / "clips")] + common
        for key, allowed in (("layout", LAYOUTS), ("style", STYLES), ("aspect", ASPECTS)):
            if key in req:
                if req[key] not in allowed:
                    raise ValueError(f"bad {key}")
                cmd += [f"--{key}", req[key]]
        if "facecam" in req:
            if not FACECAM_RE.match(str(req["facecam"])):
                raise ValueError("bad facecam")
            cmd += ["--facecam", str(req["facecam"])]
        if "split" in req:
            cmd += ["--split", str(_num(req["split"], 0.3, 0.7))]
        if req.get("only"):
            if not ONLY_RE.match(str(req["only"])):
                raise ValueError("bad only")
            cmd += ["--only", str(req["only"])]
        if req.get("no_title"):
            cmd += ["--no-title"]
        return cmd
    raise ValueError(f"unknown action {action!r} (allowed: prepare, render)")


def write_status(job: Path, **kw) -> None:
    tmp = job / "status.json.tmp"
    tmp.write_text(json.dumps({**kw, "updated": now()}, ensure_ascii=False, indent=1))
    tmp.replace(job / "status.json")


def run_job(job: Path) -> None:
    req_file = job / "request.json"
    claimed = job / "request.running.json"
    try:
        req_file.replace(claimed)          # atomic claim: one helper, one run
    except OSError:
        return
    try:
        req = json.loads(claimed.read_text(encoding="utf-8"))
        cmd = build_command(req, job)
    except Exception as e:
        write_status(job, action=None, state="rejected", error=str(e))
        claimed.replace(job / "request.rejected.json")
        return

    action = req["action"]
    write_status(job, action=action, state="running", started=now())
    with open(job / "log.txt", "a", encoding="utf-8") as log:
        log.write(f"\n=== {now()} {action}: {' '.join(cmd[1:])}\n")
        log.flush()
        try:
            rc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(REPO),
                                timeout=4 * 3600).returncode
        except subprocess.TimeoutExpired:
            rc = -9
    out = {}
    if action == "render" and (job / "clips" / "clips.json").exists():
        out["clips"] = json.loads((job / "clips" / "clips.json").read_text(encoding="utf-8"))
    tail = (job / "log.txt").read_text(encoding="utf-8", errors="replace")[-1500:]
    write_status(job, action=action, state="done" if rc == 0 else "failed", returncode=rc,
                 finished=now(), log_tail=tail if rc else "", **out)
    claimed.replace(job / f"request.{action}.done.json")


def main() -> None:
    inbox = Path(sys.argv[sys.argv.index("--inbox") + 1]) if "--inbox" in sys.argv else REPO / "jobs"
    once = "--once" in sys.argv
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "README.txt").write_text(
        "viral-clipper jobs. Claude writes <job>/request.json; the helper runs it.\n"
        "Only 'prepare' and 'render' actions are accepted.\n")
    print(f"viral-clipper helper v{VERSION} watching {inbox}", flush=True)

    def beat():
        (inbox / "helper.json").write_text(json.dumps(
            {"alive": now(), "epoch": time.time(), "version": VERSION, "pid": os.getpid(),
             "platform": sys.platform}))

    def beat_forever():  # keeps the heartbeat fresh even while a long job runs
        while True:
            try:
                beat()
            except Exception:
                pass
            time.sleep(10)

    beat()
    if not once:
        threading.Thread(target=beat_forever, daemon=True).start()
    while True:
        for req in sorted(inbox.glob("*/request.json")):
            try:
                run_job(req.parent)
            except Exception:
                traceback.print_exc()
        if once:
            break
        time.sleep(2)


if __name__ == "__main__":
    main()
