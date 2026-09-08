import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.build_macos_app import (
    build_app_bundle,
    render_ios_launcher_swift_source,
    render_swift_source,
)
from src import dashboard_launcher


class DashboardLauncherTests(unittest.TestCase):
    def test_streamlit_command_is_loopback_only(self):
        command = dashboard_launcher.streamlit_command(
            Path("/tmp/python"),
            Path("/tmp/dashboard.py"),
            "127.0.0.1",
            8502,
        )
        self.assertIn("--server.address=127.0.0.1", command)
        self.assertIn("--server.fileWatcherType=none", command)
        self.assertIn("--server.port=8502", command)
        self.assertIn("--server.headless=true", command)

    @mock.patch("src.dashboard_launcher.is_port_open")
    def test_find_available_port_skips_occupied_port(self, mock_port):
        mock_port.side_effect = [True, False]
        self.assertEqual(dashboard_launcher.find_available_port(search_limit=2), 8502)

    @mock.patch("src.dashboard_launcher.is_port_open", return_value=True)
    @mock.patch("src.dashboard_launcher.is_process_running", return_value=True)
    def test_active_dashboard_url_requires_owned_live_process(self, _process, _port):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            state_path.write_text('{"pid": 42, "port": 8501}', encoding="utf-8")
            self.assertEqual(
                dashboard_launcher.active_dashboard_url(state_path),
                "http://127.0.0.1:8501",
            )
            self.assertIsNone(
                dashboard_launcher.active_dashboard_url(
                    state_path,
                    expected_fingerprint="new-runtime",
                )
            )
            state_path.write_text(
                '{"pid": 42, "port": 8501, "runtime_fingerprint": "new-runtime"}',
                encoding="utf-8",
            )
            self.assertEqual(
                dashboard_launcher.active_dashboard_url(
                    state_path,
                    expected_fingerprint="new-runtime",
                ),
                "http://127.0.0.1:8501",
            )

    def test_runtime_fingerprint_includes_cognitive_component_assets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / "src" / "cognitive_component_frontend").mkdir(parents=True)
            (root / "locales").mkdir()
            (root / "config" / "versions.json").write_text('{"app_version":"1"}', encoding="utf-8")
            component = root / "src" / "cognitive_component_frontend" / "index.html"
            component.write_text("first", encoding="utf-8")
            original = dashboard_launcher.runtime_fingerprint(root)
            component.write_text("second", encoding="utf-8")
            self.assertNotEqual(original, dashboard_launcher.runtime_fingerprint(root))

    def test_render_swift_source_embeds_project_path(self):
        source = render_swift_source(dashboard_launcher.BASE_DIR)
        self.assertIn(str(dashboard_launcher.BASE_DIR), source)
        self.assertNotIn("__PROJECT_ROOT__", source)
        self.assertIn("WKWebView", source)

    def test_render_swift_source_exposes_standard_edit_actions(self):
        source = render_swift_source(dashboard_launcher.BASE_DIR)
        for title, selector, key in (("复制", "NSText.copy", "\"c\""), ("粘贴", "NSText.paste", "\"v\"")):
            self.assertIn(title, source)
            self.assertIn(selector, source)
            self.assertIn(key, source)

    def test_render_swift_source_connects_native_file_picker(self):
        source = render_swift_source(dashboard_launcher.BASE_DIR)
        self.assertIn("WKUIDelegate", source)
        self.assertIn("webView.uiDelegate = self", source)
        self.assertIn("runOpenPanelWith parameters: WKOpenPanelParameters", source)
        self.assertIn("NSOpenPanel()", source)

    def test_render_swift_source_launches_dashboard_without_terminal(self):
        source = render_swift_source(dashboard_launcher.BASE_DIR)
        self.assertIn('appendingPathComponent(".venv/bin/python")', source)
        self.assertIn('appendingPathComponent("src/dashboard_launcher.py")', source)
        self.assertIn('process.arguments = ["-arm64", pythonURL.path, launcherURL.path, "--no-browser"]', source)
        self.assertIn('process.arguments = ["-arm64", pythonURL.path, runnerURL.path, "--trigger-type", "catch_up"]', source)
        self.assertNotIn('"-a", "Terminal"', source)
        self.assertNotIn("daily-recovery-coach-launch", source)

    def test_build_app_bundle_creates_valid_macos_structure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "Recovery.app"
            built_path = build_app_bundle(
                dashboard_launcher.BASE_DIR,
                output_path,
                should_sign=False,
                should_compile=False,
            )
            executable = built_path / "Contents" / "MacOS" / "rhythmos"
            info_path = built_path / "Contents" / "Info.plist"
            self.assertTrue(executable.is_file())
            self.assertTrue(executable.stat().st_mode & 0o111)
            with info_path.open("rb") as plist_file:
                info = plistlib.load(plist_file)
            self.assertEqual(info["CFBundlePackageType"], "APPL")
            self.assertEqual(info["CFBundleExecutable"], executable.name)
            self.assertEqual(info["NSPrincipalClass"], "NSApplication")
            self.assertEqual(info["LSArchitecturePriority"], ["arm64"])
            self.assertTrue(info["LSRequiresNativeExecution"])
            self.assertEqual(info["LSMinimumSystemVersion"], "14.0")
            launcher = built_path / "Contents" / "Helpers" / "打开 RHYTHMOS iOS.app"
            self.assertTrue((launcher / "Contents" / "MacOS" / "rhythmos-ios-launcher").is_file())
            with (launcher / "Contents" / "Info.plist").open("rb") as launcher_plist:
                launcher_info = plistlib.load(launcher_plist)
            self.assertTrue(launcher_info["LSUIElement"])

    def test_ios_launcher_source_runs_without_terminal(self):
        source = render_ios_launcher_swift_source(dashboard_launcher.BASE_DIR)
        self.assertIn('appendingPathComponent("scripts/open_ios_simulator.command")', source)
        self.assertIn('process.executableURL = URL(fileURLWithPath: "/usr/bin/nohup")', source)
        self.assertIn('process.arguments = [launcher.path, "--background"]', source)
        self.assertNotIn('"-a", "Terminal"', source)

    @mock.patch("src.dashboard_launcher.subprocess.run")
    def test_open_dashboard_url_uses_native_macos_open(self, mock_run):
        dashboard_launcher.open_dashboard_url("http://127.0.0.1:8501")
        mock_run.assert_called_once()
        self.assertEqual(
            mock_run.call_args.args[0],
            ["/usr/bin/open", "http://127.0.0.1:8501"],
        )


if __name__ == "__main__":
    unittest.main()
