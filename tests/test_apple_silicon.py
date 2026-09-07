import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import apple_silicon, build_macos_app
from src import dashboard_launcher


class AppleSiliconTests(unittest.TestCase):
    @mock.patch("scripts.apple_silicon.subprocess.run")
    def test_rejects_python_wrapper_forcing_rosetta(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "x86_64\n", "")
        with self.assertRaisesRegex(RuntimeError, "APPLE_SILICON_PYTHON_REQUIRED"):
            apple_silicon.require_arm64_python(Path("/tmp/python"))

    @mock.patch("scripts.apple_silicon.subprocess.run")
    def test_binary_must_contain_arm64(self, run):
        for description, accepted in (("Mach-O 64-bit executable x86_64", False),
                                      ("POSIX shell script text executable", False),
                                      ("Mach-O 64-bit executable arm64", True),
                                      ("Mach-O universal binary [x86_64] [arm64]", True)):
            with self.subTest(description=description):
                run.return_value = subprocess.CompletedProcess([], 0, description, "")
                if accepted:
                    apple_silicon.require_arm64_binary(Path("/tmp/binary"))
                else:
                    with self.assertRaises(RuntimeError):
                        apple_silicon.require_arm64_binary(Path("/tmp/binary"))

    @mock.patch("scripts.build_macos_app.require_arm64_binary")
    @mock.patch("scripts.build_macos_app.subprocess.run")
    def test_compiler_explicitly_targets_apple_silicon(self, run, verify):
        output = Path("/tmp/rhythmos")
        build_macos_app.compile_native_app(Path("/tmp/source.swift"), output)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-target") + 1], "arm64-apple-macosx14.0")
        verify.assert_called_once_with(output)

    def test_sign_failure_preserves_installed_app(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "test.app"
            output.mkdir()
            marker = output / "existing"
            marker.write_text("working app")
            with mock.patch.object(build_macos_app, "sign_app_bundle", side_effect=RuntimeError("sign failed")):
                with self.assertRaisesRegex(RuntimeError, "sign failed"):
                    build_macos_app.build_app_bundle(build_macos_app.BASE_DIR, output, should_compile=False)
            self.assertEqual(marker.read_text(), "working app")
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_architecture_change_invalidates_dashboard_reuse(self):
        with mock.patch.object(dashboard_launcher.platform, "machine", return_value="x86_64"):
            previous = dashboard_launcher.runtime_fingerprint()
        with mock.patch.object(dashboard_launcher.platform, "machine", return_value="arm64"):
            self.assertNotEqual(previous, dashboard_launcher.runtime_fingerprint())
