"""Build a project-local RHYTHMOS｜律衡 macOS dashboard bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile

try:
    from scripts.apple_silicon import MACOS_MIN_VERSION, MACOS_TARGET, require_arm64_binary, require_arm64_python
    from scripts.build_kubios_ocr_helper import build as build_ocr_helper
except ModuleNotFoundError:  # Direct script invocation.
    from apple_silicon import MACOS_MIN_VERSION, MACOS_TARGET, require_arm64_binary, require_arm64_python
    from build_kubios_ocr_helper import build as build_ocr_helper


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = BASE_DIR / "dist" / "RHYTHMOS.app"
SWIFT_TEMPLATE = BASE_DIR / "scripts" / "macos_dashboard_app.swift"
ICON_PATH = BASE_DIR / "assets" / "app_icon.icns"
STARTUP_SPLASH_PATH = BASE_DIR / "assets" / "startup_splash.png"
VERSIONS_PATH = BASE_DIR / "config" / "versions.json"


def render_swift_source(project_root: Path) -> str:
    """Render the native app source with a safely escaped project path."""
    template = SWIFT_TEMPLATE.read_text(encoding="utf-8")
    project_literal = json.dumps(str(project_root.resolve()), ensure_ascii=False)
    return template.replace('"__PROJECT_ROOT__"', project_literal)


def compile_native_app(source_path: Path, executable_path: Path) -> None:
    """Compile the AppKit/WebKit window used by the local app bundle."""
    try:
        subprocess.run(
            [
                "/usr/bin/xcrun",
                "swiftc",
                "-target",
                MACOS_TARGET,
                str(source_path),
                "-o",
                str(executable_path),
                "-framework",
                "Cocoa",
                "-framework",
                "WebKit",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else ""
        raise RuntimeError(f"DASHBOARD_APP_COMPILE_FAILED:{detail}") from exc
    require_arm64_binary(executable_path)


def sign_app_bundle(output_path: Path) -> None:
    """Apply an ad-hoc local signature so Finder can launch the bundle."""
    try:
        subprocess.run(
            ["/usr/bin/codesign", "--force", "--sign", "-", str(output_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(output_path)],
            check=True, capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("DASHBOARD_APP_SIGN_FAILED") from exc


def build_app_bundle(
    project_root: Path,
    output_path: Path,
    should_sign: bool = True,
    should_compile: bool = True,
) -> Path:
    """Create a self-contained app shell that points at this local project."""
    project_root = project_root.resolve()
    output_path = output_path.resolve()
    launcher_path = project_root / "src" / "dashboard_launcher.py"
    python_path = project_root / ".venv" / "bin" / "python"
    if not launcher_path.is_file():
        raise RuntimeError("DASHBOARD_LAUNCHER_NOT_FOUND")
    if not python_path.is_file():
        raise RuntimeError("DASHBOARD_PYTHON_NOT_FOUND")
    if should_compile:
        if output_path != DEFAULT_OUTPUT.resolve():
            raise RuntimeError("DASHBOARD_CANONICAL_OUTPUT_REQUIRED")
        require_arm64_python(python_path)
    if not ICON_PATH.is_file():
        raise RuntimeError("DASHBOARD_APP_ICON_NOT_FOUND")
    if not STARTUP_SPLASH_PATH.is_file():
        raise RuntimeError("DASHBOARD_STARTUP_SPLASH_NOT_FOUND")
    try:
        app_version = json.loads(VERSIONS_PATH.read_text(encoding="utf-8"))["app_version"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError("DASHBOARD_APP_VERSION_NOT_FOUND") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Build and sign before replacing the installed bundle. Temporary build
    # support stays beside the sole supported app output and is cleaned up.
    with tempfile.TemporaryDirectory(prefix=".rhythmos-build-", dir=output_path.parent) as staging:
        stage = Path(staging)
        bundle = stage / "bundle"
        _populate_bundle(project_root, bundle, app_version, should_compile)
        if should_sign:
            sign_app_bundle(bundle)
        previous = stage / "previous"
        if output_path.exists():
            output_path.rename(previous)
        try:
            bundle.rename(output_path)
        except OSError:
            if previous.exists():
                previous.rename(output_path)
            raise
    return output_path


def _populate_bundle(project_root: Path, output_path: Path, app_version: str, should_compile: bool) -> None:
    contents_dir = output_path / "Contents"
    macos_dir = contents_dir / "MacOS"
    resources_dir = contents_dir / "Resources"
    macos_dir.mkdir(parents=True)
    resources_dir.mkdir()

    executable_path = macos_dir / "rhythmos"
    source_path = resources_dir / "DashboardApp.swift"
    source_path.write_text(render_swift_source(project_root), encoding="utf-8")
    shutil.copy2(ICON_PATH, resources_dir / "app_icon.icns")
    shutil.copy2(STARTUP_SPLASH_PATH, resources_dir / "startup_splash.png")
    if should_compile:
        compile_native_app(source_path, executable_path)
    else:
        executable_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable_path.chmod(0o755)

    info = {
        "CFBundleDisplayName": "RHYTHMOS｜律衡",
        "CFBundleExecutable": "rhythmos",
        "CFBundleIdentifier": "local.rhythmos.dashboard",
        "CFBundleIconFile": "app_icon.icns",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "RHYTHMOS｜律衡",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": app_version,
        "CFBundleVersion": app_version,
        "LSMinimumSystemVersion": MACOS_MIN_VERSION,
        "LSArchitecturePriority": ["arm64"],
        "LSRequiresNativeExecution": True,
        "LSApplicationCategoryType": "public.app-category.healthcare-fitness",
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "打开 RHYTHMOS iOS",
                "CFBundleTypeRole": "Editor",
                "CFBundleTypeExtensions": ["rhythmos-ios"],
                "CFBundleTypeIconFile": "app_icon.icns",
                "LSHandlerRank": "Owner",
            }
        ],
    }
    with (contents_dir / "Info.plist").open("wb") as plist_file:
        plistlib.dump(info, plist_file, sort_keys=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建本地 macOS Dashboard 应用")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output.resolve() != DEFAULT_OUTPUT.resolve():
        raise RuntimeError("DASHBOARD_CANONICAL_OUTPUT_REQUIRED")
    require_arm64_python(BASE_DIR / ".venv/bin/python")
    build_ocr_helper()
    app_path = build_app_bundle(BASE_DIR, args.output)
    print(f"Built: {app_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
