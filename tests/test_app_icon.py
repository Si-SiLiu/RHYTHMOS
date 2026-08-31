import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts import build_app_icon, build_macos_app
from src.branding import PAGE_ICON_PATH, brand_icon_path, load_page_icon


class AppIconTests(unittest.TestCase):
    def test_canonical_source_and_generated_assets_exist(self):
        self.assertTrue(build_app_icon.DEFAULT_SOURCE.is_file())
        for size in build_app_icon.OUTPUT_SIZES:
            self.assertTrue((build_app_icon.DEFAULT_OUTPUT_DIR / f"app_icon_{size}.png").is_file())
        self.assertTrue((build_app_icon.DEFAULT_OUTPUT_DIR / "app_icon.icns").is_file())

    def test_generated_png_dimensions_are_square_and_exact(self):
        for size in build_app_icon.OUTPUT_SIZES:
            with Image.open(build_app_icon.DEFAULT_OUTPUT_DIR / f"app_icon_{size}.png") as image:
                self.assertEqual(image.size, (size, size))
                self.assertIn(image.mode, {"RGB", "RGBA"})

    def test_source_is_not_overwritten_by_build(self):
        before = build_app_icon.DEFAULT_SOURCE.read_bytes()
        build_app_icon.build_icon_assets()
        self.assertEqual(build_app_icon.DEFAULT_SOURCE.read_bytes(), before)

    def test_build_is_idempotent(self):
        build_app_icon.build_icon_assets()
        first = (build_app_icon.DEFAULT_OUTPUT_DIR / "app_icon_64.png").read_bytes()
        build_app_icon.build_icon_assets()
        self.assertEqual((build_app_icon.DEFAULT_OUTPUT_DIR / "app_icon_64.png").read_bytes(), first)

    def test_build_uses_no_network_library(self):
        source = Path(build_app_icon.__file__).read_text(encoding="utf-8")
        for forbidden in ("requests", "urllib", "httpx", "openai"):
            self.assertNotIn(f"import {forbidden}", source)

    def test_streamlit_page_icon_loads_and_missing_falls_back(self):
        icon = load_page_icon()
        self.assertEqual(icon.size, (64, 64))
        self.assertEqual(load_page_icon(Path("/missing/icon.png")), "💚")
        self.assertEqual(PAGE_ICON_PATH, build_app_icon.BASE_DIR / "assets" / "app_icon_64.png")

    def test_brand_icon_path_is_project_relative_and_missing_safe(self):
        self.assertTrue(brand_icon_path().is_file())
        self.assertIsNone(brand_icon_path(Path("/missing/icon.png")))

    def test_dashboard_integrates_icon_without_touching_engines(self):
        dashboard = (build_app_icon.BASE_DIR / "src" / "dashboard.py").read_text(encoding="utf-8")
        self.assertIn("page_icon=load_page_icon()", dashboard)
        for engine in ("recovery_score.py", "baseline.py", "recovery_confidence.py"):
            self.assertNotIn("app_icon", (build_app_icon.BASE_DIR / "src" / engine).read_text(encoding="utf-8"))

    def test_macos_builder_copies_icns_and_sets_plist(self):
        with tempfile.TemporaryDirectory() as directory:
            app = build_macos_app.build_app_bundle(
                build_app_icon.BASE_DIR,
                Path(directory) / "Test.app",
                should_sign=False,
                should_compile=False,
            )
            import plistlib
            with (app / "Contents" / "Info.plist").open("rb") as stream:
                info = plistlib.load(stream)
            self.assertEqual(info["CFBundleIconFile"], "app_icon.icns")
            versions = json.loads(
                (build_app_icon.BASE_DIR / "config" / "versions.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                info["CFBundleShortVersionString"], versions["app_version"]
            )
            self.assertTrue((app / "Contents" / "Resources" / "app_icon.icns").is_file())


if __name__ == "__main__":
    unittest.main()
