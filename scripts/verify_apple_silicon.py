"""Read-only native runtime verification; never opens the health database."""

import argparse
import importlib
import platform
import subprocess
import sys
from pathlib import Path

try:
    from scripts.apple_silicon import require_arm64_binary, require_arm64_python
except ModuleNotFoundError:
    from apple_silicon import require_arm64_binary, require_arm64_python

BASE_DIR = Path(__file__).resolve().parents[1]


def verify(runtime_only=False):
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("Run this verifier with native macOS arm64 Python")
    require_arm64_python(Path(sys.executable))
    for module in ("ssl", "sqlite3", "numpy", "pandas", "pyarrow", "PIL.Image", "streamlit"):
        importlib.import_module(module)
    checked = set()
    for root in {Path(sys.prefix), Path(sys.base_prefix)}:
        for pattern in ("*.so", "*.dylib"):
            for path in root.rglob(pattern):
                path = path.resolve()
                if path not in checked:
                    require_arm64_binary(path)
                    checked.add(path)
    if not runtime_only:
        require_arm64_binary(BASE_DIR / "dist/RHYTHMOS.app/Contents/MacOS/rhythmos")
        require_arm64_binary(BASE_DIR / "bin/kubios-vision-ocr")
        subprocess.run([
            "/usr/bin/codesign", "--verify", "--deep", "--strict",
            str(BASE_DIR / "dist/RHYTHMOS.app"),
        ], check=True)
    print(f"PASS: native arm64 Python; {len(checked)} compatible native libraries; "
          + ("runtime only" if runtime_only else "arm64 app and OCR, valid app signature"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-only", action="store_true")
    verify(parser.parse_args().runtime_only)
