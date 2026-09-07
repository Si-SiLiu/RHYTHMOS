"""Build the local macOS Vision OCR helper without downloading dependencies."""

import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    from scripts.apple_silicon import MACOS_TARGET, require_arm64_binary
except ModuleNotFoundError:
    from apple_silicon import MACOS_TARGET, require_arm64_binary


BASE_DIR = Path(__file__).resolve().parents[1]
SOURCE = BASE_DIR / "scripts" / "kubios_vision_ocr.swift"
OUTPUT = BASE_DIR / "bin" / "kubios-vision-ocr"


def build():
    if platform.system() != "Darwin":
        raise RuntimeError("macOS Vision OCR is available only on macOS.")
    compiler = shutil.which("swiftc") or shutil.which("xcrun")
    if not compiler:
        raise RuntimeError("Swift compiler is unavailable; install Apple Command Line Tools.")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ocr-build-", dir=OUTPUT.parent) as staging:
        executable = Path(staging) / OUTPUT.name
        command = [compiler]
        if Path(compiler).name == "xcrun":
            command.append("swiftc")
        command.extend(["-target", MACOS_TARGET, str(SOURCE), "-o", str(executable)])
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            raise RuntimeError(f"Local Vision OCR helper compilation failed: {result.stderr.strip()}")
        require_arm64_binary(executable)
        executable.chmod(0o755)
        executable.replace(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    print(build())
