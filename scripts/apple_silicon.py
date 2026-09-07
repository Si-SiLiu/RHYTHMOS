"""Shared checks for the supported Apple Silicon macOS runtime."""

import subprocess
from pathlib import Path


# The retained NumPy wheel requires macOS 14 or later.
MACOS_MIN_VERSION = "14.0"
MACOS_TARGET = f"arm64-apple-macosx{MACOS_MIN_VERSION}"


def require_arm64_binary(path: Path) -> None:
    result = subprocess.run(
        ["/usr/bin/file", "-b", str(path.resolve())],
        check=True, capture_output=True, text=True,
    )
    if "Mach-O" not in result.stdout or "arm64" not in result.stdout:
        raise RuntimeError(f"APPLE_SILICON_BINARY_REQUIRED:{path}")


def require_arm64_python(python_path: Path) -> None:
    # Executing the interpreter detects Rosetta wrappers as well as Intel-only
    # installations; inspecting the file alone cannot detect a forced arch.
    result = subprocess.run(
        [str(python_path), "-c", "import platform; print(platform.machine())"],
        check=True, capture_output=True, text=True, timeout=30,
    )
    if result.stdout.strip() != "arm64":
        raise RuntimeError("APPLE_SILICON_PYTHON_REQUIRED: recreate .venv using native arm64 Python")
