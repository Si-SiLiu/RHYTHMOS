"""Install the five-minute private iOS-to-macOS sync LaunchAgent."""

from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
LABEL = "com.rhythmos.mobile-change-sync"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_DIR = Path.home() / "Library" / "Logs" / "RHYTHMOS"


def main() -> int:
    python = BASE_DIR / ".venv" / "bin" / "python"
    runner = BASE_DIR / "scripts" / "pull_mobile_changes.py"
    if not python.is_file() or not runner.is_file():
        raise RuntimeError("RHYTHMOS sync runtime is incomplete")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": [str(python), str(runner)],
        "StartInterval": 300,
        "RunAtLoad": True,
        "ProcessType": "Background",
        "StandardOutPath": str(LOG_DIR / "mobile-change-sync.stdout.log"),
        "StandardErrorPath": str(LOG_DIR / "mobile-change-sync.stderr.log"),
    }
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_bytes(plistlib.dumps(plist, fmt=plistlib.FMT_XML, sort_keys=False))
    os.chmod(PLIST_PATH, 0o600)
    domain = f"gui/{os.getuid()}"
    subprocess.run(["/bin/launchctl", "bootout", f"{domain}/{LABEL}"], check=False, capture_output=True)
    subprocess.run(["/bin/launchctl", "bootstrap", domain, str(PLIST_PATH)], check=True)
    print("installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
