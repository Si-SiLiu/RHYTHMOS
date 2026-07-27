"""Build local PNG and macOS ICNS assets from the canonical source icon."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageChops


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = BASE_DIR / "assets" / "app_icon.png"
DEFAULT_OUTPUT_DIR = BASE_DIR / "assets"
OUTPUT_SIZES = (1024, 512, 256, 128, 64, 32, 16)
ICONSET_FILES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


class AppIconBuildError(RuntimeError):
    """Raised when a local icon build cannot produce required assets."""


def content_square(image: Image.Image, tolerance: int = 12) -> tuple[int, int, int, int]:
    """Return a conservative square crop around non-background icon content."""
    rgb = image.convert("RGB")
    background = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    difference = ImageChops.difference(rgb, background).convert("L")
    mask = difference.point(lambda value: 255 if value > tolerance else 0)
    bounds = mask.getbbox()
    if not bounds:
        return (0, 0, min(rgb.size), min(rgb.size))
    left, top, right, bottom = bounds
    content_size = max(right - left, bottom - top)
    padding = max(round(content_size * 0.06), 16)
    side = min(max(content_size + padding * 2, 1), min(rgb.size))
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    crop_left = max(0, min(round(center_x - side / 2), rgb.width - side))
    crop_top = max(0, min(round(center_y - side / 2), rgb.height - side))
    return (crop_left, crop_top, crop_left + side, crop_top + side)


def prepare_icon(source_path: Path) -> Image.Image:
    """Load and safely crop the source without modifying the original file."""
    try:
        with Image.open(source_path) as source:
            image = source.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise AppIconBuildError("APP_ICON_SOURCE_INVALID") from exc
    if image.width != image.height:
        raise AppIconBuildError("APP_ICON_SOURCE_NOT_SQUARE")
    return image.crop(content_square(image))


def save_png_assets(image: Image.Image, output_dir: Path) -> dict[int, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for size in OUTPUT_SIZES:
        path = output_dir / f"app_icon_{size}.png"
        resized = image.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(path, format="PNG", optimize=True)
        outputs[size] = path
    return outputs


def build_icns(png_assets: dict[int, Path], output_dir: Path) -> Path:
    iconset_dir = output_dir / ".app_icon_build.iconset"
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir)
    iconset_dir.mkdir()
    try:
        for filename, size in ICONSET_FILES.items():
            shutil.copy2(png_assets[size], iconset_dir / filename)
        output_path = output_dir / "app_icon.icns"
        process = subprocess.run(
            ["/usr/bin/iconutil", "-c", "icns", str(iconset_dir), "-o", str(output_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0 or not output_path.is_file():
            raise AppIconBuildError("APP_ICON_ICNS_BUILD_FAILED")
        return output_path
    finally:
        shutil.rmtree(iconset_dir, ignore_errors=True)


def build_icon_assets(source_path: Path = DEFAULT_SOURCE, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, object]:
    source_path = Path(source_path).resolve()
    output_dir = Path(output_dir).resolve()
    if not source_path.is_file():
        raise AppIconBuildError("APP_ICON_SOURCE_NOT_FOUND")
    image = prepare_icon(source_path)
    png_assets = save_png_assets(image, output_dir)
    icns_path = build_icns(png_assets, output_dir)
    return {"source": source_path, "crop_size": image.size, "png": png_assets, "icns": icns_path}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build RHYTHMOS｜律衡 icon assets locally")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    try:
        result = build_icon_assets(args.source, args.output_dir)
    except AppIconBuildError as exc:
        print(str(exc))
        return 1
    print(f"Source preserved: {result['source']}")
    print(f"Generated PNG sizes: {', '.join(map(str, OUTPUT_SIZES))}")
    print(f"Generated ICNS: {result['icns']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
