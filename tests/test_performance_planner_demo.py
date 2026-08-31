import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src import demo_sandbox
from src.db import DB_PATH, connect, get_current_db_path, set_current_db_path
from src.i18n import get_translator
from src.performance_planner import (
    add_block,
    create_checkpoint,
    create_plan,
    get_plan_for_date,
    list_checkpoints,
    list_plans,
)


class PerformancePlannerDemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sessions_root = Path(self.temp.name) / "sessions"
        self.root_patch = patch.object(
            demo_sandbox,
            "SESSIONS_ROOT",
            self.sessions_root,
        )
        self.root_patch.start()
        self.mode_patch = patch.dict(
            os.environ,
            {"DRC_DEMO_MODE": "1"},
            clear=False,
        )
        self.mode_patch.start()

    def tearDown(self):
        set_current_db_path(None)
        self.mode_patch.stop()
        self.root_patch.stop()
        self.temp.cleanup()

    def test_planner_tables_are_created_in_demo_database(self):
        path = demo_sandbox.configure_demo_runtime({})
        with connect(path) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        self.assertIn("performance_plans", tables)

    def test_planner_crud_uses_current_demo_context(self):
        state = {}
        path = demo_sandbox.configure_demo_runtime(state)
        plan = create_plan("2099-01-01", "Demo", "UTC")
        add_block(
            plan["plan_id"],
            "Demo block",
            "other",
            "2099-01-01T09:00:00",
            "2099-01-01T10:00:00",
        )
        self.assertEqual(get_current_db_path(), path)
        with connect(path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM performance_plan_blocks"
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_planner_sessions_are_isolated(self):
        state_a, state_b = {}, {}
        path_a = demo_sandbox.configure_demo_runtime(state_a)
        create_plan("2099-01-01", "Only A", "UTC")
        path_b = demo_sandbox.configure_demo_runtime(state_b)
        self.assertNotEqual(path_a, path_b)
        self.assertEqual(list_plans(), [])

    def test_reset_removes_only_current_planner_records(self):
        state_a, state_b = {}, {}
        path_a = demo_sandbox.configure_demo_runtime(state_a)
        create_plan("2099-01-01", "A", "UTC")
        path_b = demo_sandbox.configure_demo_runtime(state_b)
        create_plan("2099-01-02", "B", "UTC")
        old_a = path_a
        new_a = demo_sandbox.reset_demo_sandbox(state_a)
        self.assertNotEqual(old_a, new_a)
        self.assertEqual(list_plans(), [])
        with connect(path_b) as connection:
            title = connection.execute(
                "SELECT title FROM performance_plans"
            ).fetchone()[0]
        self.assertEqual(title, "B")

    def test_demo_planner_rerun_reuses_database(self):
        state = {}
        first = demo_sandbox.configure_demo_runtime(state)
        create_plan("2099-01-01", "Persistent", "UTC")
        second = demo_sandbox.configure_demo_runtime(state)
        self.assertEqual(first, second)
        self.assertEqual(list_plans()[0]["title"], "Persistent")

    def test_browser_refresh_restores_sandbox_from_query_parameter(self):
        class BrowserState:
            def __init__(self, query_params=None):
                self.session_state = {}
                self.query_params = query_params or {}

        first_browser_session = BrowserState()
        first_path = demo_sandbox.configure_demo_runtime(first_browser_session)
        create_plan("2099-01-01", "Persistent refresh", "UTC")
        refreshed_session = BrowserState(
            dict(first_browser_session.query_params)
        )
        second_path = demo_sandbox.configure_demo_runtime(refreshed_session)
        self.assertEqual(first_path, second_path)
        self.assertEqual(list_plans()[0]["title"], "Persistent refresh")

    def test_local_mode_keeps_formal_database_context(self):
        with patch.dict(os.environ, {}, clear=True):
            resolved = demo_sandbox.configure_demo_runtime({})
        self.assertEqual(resolved, DB_PATH)
        self.assertEqual(get_current_db_path(), DB_PATH)

    def test_page_imports_in_demo_mode_without_exception(self):
        page = (
            Path(__file__).parents[1]
            / "src"
            / "pages"
            / "8_Performance_Planner.py"
        )
        with patch(
            "src.i18n.ui.render_sidebar",
            return_value=("en", get_translator("en")),
        ):
            app = AppTest.from_file(str(page)).run(timeout=20)
        self.assertEqual(list(app.exception), [])
        self.assertTrue(app.title)

    def test_manual_planner_type_options_exclude_polar_exercise_type(self):
        page = (
            Path(__file__).parents[1]
            / "src"
            / "pages"
            / "8_Performance_Planner.py"
        )
        with patch(
            "src.i18n.ui.render_sidebar",
            return_value=("en", get_translator("en")),
        ), patch("streamlit.page_link", return_value=None):
            app = AppTest.from_file(str(page)).run(timeout=20)
            create_button = next(
                button for button in app.button
                if button.label == get_translator("en")("performance_planner.create")
            )
            create_button.click().run(timeout=20)
        add_type = next(
            widget for widget in app.selectbox if widget.key == "pp_add_block_type"
        )
        self.assertNotIn("exercise", add_type.options)

    def test_checkpoint_delete_requires_confirmation_and_is_scoped(self):
        page = (
            Path(__file__).parents[1]
            / "src"
            / "pages"
            / "8_Performance_Planner.py"
        )
        with patch(
            "src.i18n.ui.render_sidebar",
            return_value=("en", get_translator("en")),
        ), patch("streamlit.page_link", return_value=None):
            app = AppTest.from_file(str(page)).run(timeout=20)
            # The readiness CTA appears before the planner form; select the
            # actual create-plan submit button by its rendered label rather
            # than relying on widget order.
            create_button = next(
                button for button in app.button
                if button.label == get_translator("en")("performance_planner.create")
            )
            create_button.click().run(timeout=20)

            db_path = next(self.sessions_root.glob("*/demo.db"))
            plan = get_plan_for_date(date.today(), db_path=db_path)
            first = create_checkpoint(
                plan["plan_id"],
                "focus_check",
                f"{date.today().isoformat()}T12:00:00",
                "manual",
                db_path=db_path,
            )
            second = create_checkpoint(
                plan["plan_id"],
                "focus_check",
                f"{date.today().isoformat()}T13:00:00",
                "manual",
                db_path=db_path,
            )
            app.run(timeout=20)

            first_delete = next(
                button
                for button in app.button
                if button.key == f"pp_checkpoint_delete_{first['checkpoint_id']}"
            )
            first_delete.click().run(timeout=20)
            app.run(timeout=20)
            remaining_after_first_click = {
                item["checkpoint_id"]
                for item in list_checkpoints(plan["plan_id"], db_path=db_path)
            }
            self.assertEqual(
                remaining_after_first_click,
                {first["checkpoint_id"], second["checkpoint_id"]},
            )

            cancel = next(
                button
                for button in app.button
                if button.key == f"pp_checkpoint_delete_cancel_{first['checkpoint_id']}"
            )
            cancel.click().run(timeout=20)
            self.assertEqual(
                {
                    item["checkpoint_id"]
                    for item in list_checkpoints(plan["plan_id"], db_path=db_path)
                },
                {first["checkpoint_id"], second["checkpoint_id"]},
            )

            next(
                button
                for button in app.button
                if button.key == f"pp_checkpoint_delete_{first['checkpoint_id']}"
            ).click().run(timeout=20)
            next(
                button
                for button in app.button
                if button.key == f"pp_checkpoint_delete_confirm_{first['checkpoint_id']}"
            ).click().run(timeout=20)
            self.assertEqual(
                {
                    item["checkpoint_id"]
                    for item in list_checkpoints(plan["plan_id"], db_path=db_path)
                },
                {second["checkpoint_id"]},
            )


if __name__ == "__main__":
    unittest.main()
