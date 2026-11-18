#!/usr/bin/env python3
"""Start the viral-clipper helper automatically at login.

    python3 scripts/install_helper.py              # install + start now
    python3 scripts/install_helper.py --uninstall  # remove

macOS: a LaunchAgent (~/Library/LaunchAgents). Windows: a Task Scheduler
logon task. Linux: a systemd --user service. Nothing needs admin rights.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "scripts" / "helper.py"
LABEL = "com.viralclipper.helper"


def venv_python() -> str:
    p = REPO / ".venv" / ("Scripts/pythonw.exe" if os.name == "nt" else "bin/python")
    if not p.exists():
        sys.exit("Run `python3 scripts/setup.py` first.")
    return str(p)


def mac(uninstall: bool) -> None:
    plist = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"], capture_output=True)
    if uninstall:
        plist.unlink(missing_ok=True)
        print("✓ helper removed")
        return
    log = REPO / "jobs" / "helper.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key><array>
    <string>{venv_python()}</string><string>{HELPER}</string>
  </array>
  <key>WorkingDirectory</key><string>{REPO}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Standard</string>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict></plist>
""")
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(plist)], capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(["launchctl", "load", "-w", str(plist)], check=True)
    print(f"✓ helper installed: starts at login ({plist})")


def windows(uninstall: bool) -> None:
    subprocess.run(["schtasks", "/Delete", "/TN", "ViralClipperHelper", "/F"], capture_output=True)
    if uninstall:
        print("✓ helper removed")
        return
    cmd = f'"{venv_python()}" "{HELPER}"'
    subprocess.run(["schtasks", "/Create", "/TN", "ViralClipperHelper", "/SC", "ONLOGON",
                    "/TR", cmd, "/RL", "LIMITED", "/F"], check=True)
    subprocess.run(["schtasks", "/Run", "/TN", "ViralClipperHelper"], check=True)
    print("✓ helper installed: starts at login (Task Scheduler: ViralClipperHelper)")


def linux(uninstall: bool) -> None:
    unit = Path.home() / ".config" / "systemd" / "user" / "viral-clipper-helper.service"
    if uninstall:
        subprocess.run(["systemctl", "--user", "disable", "--now", unit.name], capture_output=True)
        unit.unlink(missing_ok=True)
        print("✓ helper removed")
        return
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(f"""[Unit]
Description=viral-clipper helper

[Service]
ExecStart={venv_python()} {HELPER}
WorkingDirectory={REPO}
Restart=always
Nice=10

[Install]
WantedBy=default.target
""")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", unit.name], check=True)
    print("✓ helper installed: starts at login (systemd --user)")


if __name__ == "__main__":
    un = "--uninstall" in sys.argv
    {"darwin": mac, "win32": windows}.get(sys.platform, linux)(un)
