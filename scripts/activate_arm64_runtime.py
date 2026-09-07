"""Activate the prepared native environment, retaining the Intel environment."""

from pathlib import Path
import subprocess

try:
    from scripts.apple_silicon import require_arm64_python
except ModuleNotFoundError:
    from apple_silicon import require_arm64_python

BASE_DIR = Path(__file__).resolve().parents[1]


def activate():
    candidate = BASE_DIR / ".venv-arm64"
    python = candidate / "bin/python3.12"
    require_arm64_python(python)
    subprocess.run([str(python), str(BASE_DIR / "scripts/verify_apple_silicon.py"), "--runtime-only"], check=True)
    # Keep the current environment active until the compiler is available.
    subprocess.run(["/usr/bin/xcrun", "--find", "swiftc"], check=True, capture_output=True, text=True)
    current = BASE_DIR / ".venv"
    backup = BASE_DIR / ".venv-intel-backup"
    if current.is_symlink() and current.resolve() == candidate:
        print("Native runtime already active")
        return
    if backup.exists():
        raise RuntimeError("Intel backup already exists; inspect before changing runtime")
    if current.is_symlink():
        raise RuntimeError("Unexpected .venv symlink; inspect before changing runtime")
    current.rename(backup)
    try:
        current.symlink_to(candidate.name, target_is_directory=True)
    except OSError:
        backup.rename(current)
        raise
    print("Activated .venv -> .venv-arm64; previous environment retained in .venv-intel-backup")


if __name__ == "__main__":
    activate()
