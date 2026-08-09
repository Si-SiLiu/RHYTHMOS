import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.db import connect
from src.performance_planner import (
    PlannerConflictError,
    PlannerNotFoundError,
    PlannerValidationError,
    acknowledge_recommendation,
    add_block,
    apply_recommendation,
    build_source_snapshot,
    create_checkpoint,
    create_plan,
    delete_block,
    delete_checkpoint,
    delete_plan,
    generate_recommendations,
    get_plan,
    get_progress_lab_rows,
    get_block_defaults,
    get_timeline_summary,
    link_checkpoint_run,
    list_blocks,
    list_checkpoints,
    list_recommendations,
    reorder_blocks,
    transition_block,
    update_block,
    update_checkpoint_status,
    update_plan,
)


class PerformancePlannerTests(unittest.TestCase):
    DAY = "2026-07-29"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "planner.db"
        self.plan = create_plan(
            self.DAY,
            "Workday",
            "Asia/Shanghai",
            db_path=self.db_path,
        )

    def tearDown(self):
        self.temp.cleanup()

    def add_test_block(
        self,
        title="Focus",
        start="09:00",
        end="10:00",
        **kwargs,
    ):
        return add_block(
            self.plan["plan_id"],
            title,
            kwargs.pop("block_type", "deep_work"),
            f"{self.DAY}T{start}:00",
            f"{self.DAY}T{end}:00",
            db_path=self.db_path,
            **kwargs,
        )

    def insert_cognitive_run(self, run_id="run-1", accuracy=0.9, completed=1):
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO cognitive_training_sessions(
                    id, training_plan, session_mode, started_at, completed_at,
                    timezone, completed, interrupted, device_context,
                    protocol_version
                ) VALUES(?, 'focus_alertness', 'quick', ?, ?, 'Asia/Shanghai',
                         ?, 0, '{}', 'planner-test-v1')
                """,
                (
                    run_id,
                    f"{self.DAY}T08:00:00",
                    f"{self.DAY}T08:05:00",
                    completed,
                ),
            )
            connection.execute(
                """
                INSERT INTO cognitive_training_task_results(
                    id, session_id, task_type, task_order, protocol_version,
                    total_trials, correct_count, error_count, omission_count,
                    accuracy, median_rt_ms, metrics_json
                ) VALUES(?, ?, 'focus_gonogo', 1, 'planner-test-v1',
                         10, 9, 1, 0, ?, 420, '{}')
                """,
                (f"task-{run_id}", run_id, accuracy),
            )
            connection.commit()

    def test_plan_crud_round_trip(self):
        updated = update_plan(
            self.plan["plan_id"],
            title="Updated",
            status="completed",
            timezone="UTC",
            db_path=self.db_path,
        )
        self.assertEqual(updated["title"], "Updated")
        self.assertEqual(get_plan(self.plan["plan_id"], db_path=self.db_path)["status"], "completed")
        self.assertTrue(delete_plan(self.plan["plan_id"], db_path=self.db_path))
        self.assertIsNone(get_plan(self.plan["plan_id"], db_path=self.db_path))

    def test_plan_date_is_unique(self):
        with self.assertRaises(PlannerConflictError):
            create_plan(self.DAY, "Duplicate", "UTC", db_path=self.db_path)

    def test_plan_title_must_not_be_empty(self):
        with self.assertRaises(PlannerValidationError):
            create_plan("2026-07-30", " ", "UTC", db_path=self.db_path)

    def test_delete_plan_cascades_children(self):
        block = self.add_test_block()
        create_checkpoint(
            self.plan["plan_id"],
            "focus_check",
            f"{self.DAY}T08:50:00",
            "before_block",
            related_block_id=block["block_id"],
            db_path=self.db_path,
        )
        delete_plan(self.plan["plan_id"], db_path=self.db_path)
        with connect(self.db_path) as connection:
            counts = [
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "performance_plan_blocks",
                    "performance_checkpoints",
                )
            ]
        self.assertEqual(counts, [0, 0])

    def test_block_create_update_delete(self):
        block = self.add_test_block(context="Desk", notes="Quiet")
        updated = update_block(
            block["block_id"],
            title="Revised",
            cognitive_demand="low",
            db_path=self.db_path,
        )
        self.assertEqual(updated["title"], "Revised")
        self.assertEqual(updated["cognitive_demand"], "low")
        self.assertTrue(delete_block(block["block_id"], db_path=self.db_path))

    def test_block_end_must_follow_start(self):
        with self.assertRaises(PlannerValidationError):
            self.add_test_block(start="10:00", end="09:59")

    def test_block_must_match_plan_date(self):
        with self.assertRaises(PlannerValidationError):
            add_block(
                self.plan["plan_id"],
                "Wrong date",
                "other",
                "2026-07-30T09:00:00",
                "2026-07-30T10:00:00",
                db_path=self.db_path,
            )

    def test_checkpoint_must_match_plan_date(self):
        with self.assertRaises(PlannerValidationError):
            create_checkpoint(
                self.plan["plan_id"],
                "focus_check",
                "2026-07-30T09:00:00",
                "manual",
                db_path=self.db_path,
            )

    def test_overlap_is_rejected(self):
        self.add_test_block()
        with self.assertRaises(PlannerConflictError):
            self.add_test_block("Overlap", "09:30", "10:30")

    def test_touching_blocks_do_not_overlap(self):
        self.add_test_block()
        second = self.add_test_block("Next", "10:00", "11:00")
        self.assertEqual(len(list_blocks(self.plan["plan_id"], db_path=self.db_path)), 2)
        self.assertEqual(second["planned_start"], f"{self.DAY}T10:00:00")

    def test_update_overlap_is_rejected(self):
        self.add_test_block()
        second = self.add_test_block("Next", "10:00", "11:00")
        with self.assertRaises(PlannerConflictError):
            update_block(
                second["block_id"],
                planned_start=f"{self.DAY}T09:30:00",
                db_path=self.db_path,
            )

    def test_invalid_domain_values_are_rejected(self):
        with self.assertRaises(PlannerValidationError):
            self.add_test_block(block_type="unsupported")
        with self.assertRaises(PlannerValidationError):
            self.add_test_block(cognitive_demand="extreme")

    def test_existing_block_types_have_centralized_input_defaults(self):
        expected = {
            "deep_work": {"priority": "medium", "cognitive_demand": "high", "physical_demand": "low"},
            "learning": {"priority": "medium", "cognitive_demand": "high", "physical_demand": "low"},
            "meeting": {"priority": "medium", "cognitive_demand": "moderate", "physical_demand": "low"},
            "exercise": {"priority": "medium", "cognitive_demand": "low", "physical_demand": "high"},
            "recovery": {"priority": "medium", "cognitive_demand": "low", "physical_demand": "low"},
            "routine": {"priority": "medium", "cognitive_demand": "low", "physical_demand": "low"},
            "other": {"priority": "medium", "cognitive_demand": "moderate", "physical_demand": "low"},
        }
        for block_type, defaults in expected.items():
            self.assertEqual(get_block_defaults(block_type), defaults)
        self.assertIsNot(get_block_defaults("deep_work"), get_block_defaults("deep_work"))

    def test_planner_add_form_keeps_advanced_options_collapsed_and_preserves_all_fields(self):
        page = (Path(__file__).parents[1] / "src" / "pages" / "8_Performance_Planner.py").read_text(encoding="utf-8")
        self.assertIn('TR("performance_planner.more_options"), expanded=False', page)
        self.assertIn('"pp_add_advanced_touched"', page)
        for field in ("priority", "cognitive_demand", "physical_demand", "context", "notes"):
            self.assertIn(f'"performance_planner.{field}"', page)
        for field in ("priority", "cognitive_demand", "physical_demand", "context", "notes"):
            self.assertIn(f'{field}={field}', page)

    def test_reorder_requires_exact_unique_ids(self):
        first = self.add_test_block()
        second = self.add_test_block("Second", "10:00", "11:00")
        reordered = reorder_blocks(
            self.plan["plan_id"],
            [second["block_id"], first["block_id"]],
            db_path=self.db_path,
        )
        self.assertEqual(reordered[0]["block_id"], second["block_id"])
        with self.assertRaises(PlannerValidationError):
            reorder_blocks(
                self.plan["plan_id"],
                [first["block_id"], first["block_id"]],
                db_path=self.db_path,
            )

    def test_block_status_transitions(self):
        block = self.add_test_block()
        for status in ("in_progress", "completed", "skipped", "postponed"):
            updated = transition_block(block["block_id"], status, db_path=self.db_path)
            self.assertEqual(updated["status"], status)

    def test_checkpoint_crud(self):
        block = self.add_test_block()
        checkpoint = create_checkpoint(
            self.plan["plan_id"],
            "quick_neural_check",
            f"{self.DAY}T08:50:00",
            "before_block",
            related_block_id=block["block_id"],
            db_path=self.db_path,
        )
        self.assertEqual(len(list_checkpoints(self.plan["plan_id"], db_path=self.db_path)), 1)
        updated = update_checkpoint_status(
            checkpoint["checkpoint_id"],
            "skipped",
            db_path=self.db_path,
        )
        self.assertEqual(updated["status"], "skipped")
        self.assertTrue(delete_checkpoint(checkpoint["checkpoint_id"], db_path=self.db_path))

    def test_checkpoint_rejects_block_from_another_plan(self):
        other = create_plan("2026-07-30", "Other", "UTC", db_path=self.db_path)
        other_block = add_block(
            other["plan_id"],
            "Other block",
            "other",
            "2026-07-30T09:00:00",
            "2026-07-30T10:00:00",
            db_path=self.db_path,
        )
        with self.assertRaises(PlannerValidationError):
            create_checkpoint(
                self.plan["plan_id"],
                "focus_check",
                f"{self.DAY}T09:00:00",
                "manual",
                related_block_id=other_block["block_id"],
                db_path=self.db_path,
            )

    def test_link_run_is_idempotent_and_does_not_copy_trials(self):
        self.insert_cognitive_run()
        checkpoint = create_checkpoint(
            self.plan["plan_id"],
            "focus_check",
            f"{self.DAY}T08:50:00",
            "manual",
            db_path=self.db_path,
        )
        first = link_checkpoint_run(
            checkpoint["checkpoint_id"],
            "run-1",
            db_path=self.db_path,
        )
        second = link_checkpoint_run(
            checkpoint["checkpoint_id"],
            "run-1",
            db_path=self.db_path,
        )
        self.assertEqual(first["cognitive_run_id"], second["cognitive_run_id"])
        snapshot = json.loads(first["result_snapshot_json"])
        self.assertEqual(snapshot["run_id"], "run-1")
        self.assertEqual(snapshot["task_count"], 1)
        with connect(self.db_path) as connection:
            result_count = connection.execute(
                "SELECT COUNT(*) FROM cognitive_training_task_results WHERE session_id='run-1'"
            ).fetchone()[0]
            trial_count = connection.execute(
                "SELECT COUNT(*) FROM cognitive_training_trials WHERE session_id='run-1'"
            ).fetchone()[0]
        self.assertEqual((result_count, trial_count), (1, 0))

    def test_run_can_link_to_only_one_checkpoint(self):
        self.insert_cognitive_run()
        checkpoints = [
            create_checkpoint(
                self.plan["plan_id"],
                "focus_check",
                f"{self.DAY}T0{hour}:00:00",
                "manual",
                db_path=self.db_path,
            )
            for hour in (7, 8)
        ]
        link_checkpoint_run(checkpoints[0]["checkpoint_id"], "run-1", db_path=self.db_path)
        with self.assertRaises(PlannerConflictError):
            link_checkpoint_run(checkpoints[1]["checkpoint_id"], "run-1", db_path=self.db_path)

    def test_missing_or_incomplete_run_cannot_link(self):
        checkpoint = create_checkpoint(
            self.plan["plan_id"],
            "focus_check",
            f"{self.DAY}T08:00:00",
            "manual",
            db_path=self.db_path,
        )
        with self.assertRaises(PlannerNotFoundError):
            link_checkpoint_run(checkpoint["checkpoint_id"], "missing", db_path=self.db_path)
        self.insert_cognitive_run("incomplete", completed=0)
        with self.assertRaises(PlannerNotFoundError):
            link_checkpoint_run(checkpoint["checkpoint_id"], "incomplete", db_path=self.db_path)

    def test_snapshot_reports_insufficient_data(self):
        snapshot = build_source_snapshot(
            self.plan["plan_id"],
            now=f"{self.DAY}T08:00:00",
            db_path=self.db_path,
        )
        self.assertEqual(snapshot["data_sufficiency"], "insufficient")

    def test_snapshot_combines_recovery_cognitive_and_metrics(self):
        self.add_test_block(cognitive_demand="high")
        self.insert_cognitive_run()
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO recovery_scores(
                    date, recovery_score, activity_load_score,
                    training_load_score, readiness_score, recommendation
                ) VALUES(?, 80, 50, 50, 78, 'test')
                """,
                (self.DAY,),
            )
            connection.commit()
        snapshot = build_source_snapshot(
            self.plan["plan_id"],
            now=f"{self.DAY}T09:30:00",
            db_path=self.db_path,
        )
        self.assertEqual(snapshot["data_sufficiency"], "sufficient")
        self.assertEqual(snapshot["high_cognitive_minutes"], 60)
        self.assertEqual(snapshot["latest_cognitive"]["run_id"], "run-1")

    def test_snapshot_normalizes_aware_and_naive_now_to_plan_timezone(self):
        update_plan(self.plan["plan_id"], timezone="UTC", db_path=self.db_path)
        block = self.add_test_block(start="09:00", end="10:00")
        checkpoint = create_checkpoint(
            self.plan["plan_id"],
            "focus_check",
            f"{self.DAY}T09:15:00",
            "fixed_time",
            db_path=self.db_path,
        )

        aware_current = build_source_snapshot(
            self.plan["plan_id"],
            now=f"{self.DAY}T17:30:00+08:00",
            db_path=self.db_path,
        )
        naive_current = build_source_snapshot(
            self.plan["plan_id"],
            now=f"{self.DAY}T09:30:00",
            db_path=self.db_path,
        )
        delayed = build_source_snapshot(
            self.plan["plan_id"],
            now=f"{self.DAY}T18:30:00+08:00",
            db_path=self.db_path,
        )

        self.assertEqual(aware_current["current_block_id"], block["block_id"])
        self.assertEqual(naive_current["current_block_id"], block["block_id"])
        self.assertEqual(delayed["delayed_block_ids"], [block["block_id"]])
        self.assertEqual(delayed["overdue_checkpoint_ids"], [checkpoint["checkpoint_id"]])

    def test_snapshot_uses_asia_shanghai_for_same_absolute_instant(self):
        block = self.add_test_block(start="17:00", end="18:00")
        snapshot = build_source_snapshot(
            self.plan["plan_id"],
            now=f"{self.DAY}T17:30:00+08:00",
            db_path=self.db_path,
        )
        self.assertEqual(snapshot["current_block_id"], block["block_id"])

    def test_invalid_plan_timezone_is_rejected(self):
        with self.assertRaises(PlannerValidationError):
            update_plan(
                self.plan["plan_id"],
                timezone="Mars/Olympus_Mons",
                db_path=self.db_path,
            )
        with self.assertRaises(PlannerValidationError):
            create_plan(
                "2026-07-30",
                "Invalid timezone",
                "Mars/Olympus_Mons",
                db_path=self.db_path,
            )

    def test_generation_without_signals_requests_neural_check(self):
        recommendations = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T08:00:00",
            db_path=self.db_path,
        )
        self.assertEqual(recommendations[0]["recommendation_type"], "take_neural_check")
        self.assertEqual(recommendations[0]["data_sufficiency"], "insufficient")

    def test_generation_never_mutates_plan(self):
        block = self.add_test_block(cognitive_demand="high")
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO recovery_scores(
                    date, recovery_score, activity_load_score,
                    training_load_score, readiness_score, recommendation
                ) VALUES(?, 35, 50, 50, 40, 'test')
                """,
                (self.DAY,),
            )
            connection.commit()
        before = get_plan(self.plan["plan_id"], db_path=self.db_path)
        generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T08:30:00",
            db_path=self.db_path,
        )
        after = get_plan(self.plan["plan_id"], db_path=self.db_path)
        block_after = list_blocks(self.plan["plan_id"], db_path=self.db_path)[0]
        self.assertEqual(before, after)
        self.assertEqual(block_after["status"], block["status"])

    def test_rules_detect_low_recovery_and_delay(self):
        block = self.add_test_block(cognitive_demand="high")
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO recovery_scores(
                    date, recovery_score, activity_load_score,
                    training_load_score, readiness_score, recommendation
                ) VALUES(?, 30, 50, 50, 40, 'test')
                """,
                (self.DAY,),
            )
            connection.commit()
        recommendations = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T11:00:00",
            db_path=self.db_path,
        )
        kinds = {item["recommendation_type"] for item in recommendations}
        self.assertIn("shorten_block", kinds)
        self.assertEqual(block["status"], "planned")

    def test_rules_detect_low_recovery_for_current_high_demand_block(self):
        block = self.add_test_block(cognitive_demand="high")
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO recovery_scores(
                    date, recovery_score, activity_load_score,
                    training_load_score, readiness_score, recommendation
                ) VALUES(?, 30, 50, 50, 40, 'test')
                """,
                (self.DAY,),
            )
            connection.commit()
        recommendations = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T09:30:00",
            db_path=self.db_path,
        )
        kinds = {item["recommendation_type"] for item in recommendations}
        self.assertIn("move_high_demand_block", kinds)
        self.assertNotIn("continue_as_planned", kinds)
        self.assertEqual(
            next(
                item["related_block_id"]
                for item in recommendations
                if item["recommendation_type"] == "move_high_demand_block"
            ),
            block["block_id"],
        )

    def test_rules_detect_continuous_work_threshold(self):
        first = self.add_test_block(start="09:00", end="10:00")
        second = self.add_test_block("Second", "10:00", "11:00")
        transition_block(first["block_id"], "completed", db_path=self.db_path)
        transition_block(second["block_id"], "completed", db_path=self.db_path)
        recommendations = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T11:00:00",
            db_path=self.db_path,
        )
        self.assertIn(
            "add_recovery_break",
            {item["recommendation_type"] for item in recommendations},
        )

    def test_rules_detect_resume_after_high_accuracy(self):
        self.add_test_block()
        self.insert_cognitive_run(accuracy=0.85)
        recommendations = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T09:30:00",
            db_path=self.db_path,
        )
        self.assertIn(
            "resume_after_check",
            {item["recommendation_type"] for item in recommendations},
        )

    def test_partial_data_and_complete_data_fallback_rules(self):
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO recovery_scores(
                    date, recovery_score, activity_load_score,
                    training_load_score, readiness_score, recommendation
                ) VALUES(?, 80, 50, 50, NULL, 'test')
                """,
                (self.DAY,),
            )
            connection.commit()
        partial = build_source_snapshot(
            self.plan["plan_id"],
            now=f"{self.DAY}T08:00:00",
            db_path=self.db_path,
        )
        self.assertEqual(partial["data_sufficiency"], "partial")

        self.insert_cognitive_run(accuracy=0.8)
        recommendations = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T08:00:00",
            db_path=self.db_path,
        )
        self.assertEqual(
            [item["recommendation_type"] for item in recommendations],
            ["continue_as_planned"],
        )

    def test_rules_detect_cognitive_accuracy_and_due_checkpoint(self):
        self.add_test_block(start="09:00", end="10:00")
        self.insert_cognitive_run(accuracy=0.6)
        create_checkpoint(
            self.plan["plan_id"],
            "focus_check",
            f"{self.DAY}T08:15:00",
            "fixed_time",
            db_path=self.db_path,
        )
        recommendations = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T09:15:00",
            db_path=self.db_path,
        )
        kinds = {item["recommendation_type"] for item in recommendations}
        self.assertIn("switch_to_low_demand_task", kinds)
        self.assertIn("take_neural_check", kinds)

    def test_apply_requires_confirmation_and_is_idempotent(self):
        block = self.add_test_block()
        recommendations = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T11:00:00",
            db_path=self.db_path,
        )
        recommendation = next(
            item for item in recommendations
            if item["recommendation_type"] == "shorten_block"
        )
        with self.assertRaises(PlannerValidationError):
            apply_recommendation(
                recommendation["recommendation_id"],
                confirmed=False,
                db_path=self.db_path,
            )
        applied = apply_recommendation(
            recommendation["recommendation_id"],
            confirmed=True,
            db_path=self.db_path,
        )
        replayed = apply_recommendation(
            recommendation["recommendation_id"],
            confirmed=True,
            db_path=self.db_path,
        )
        changed = list_blocks(self.plan["plan_id"], db_path=self.db_path)[0]
        self.assertIsNotNone(applied["applied_at"])
        self.assertEqual(applied["applied_at"], replayed["applied_at"])
        self.assertLess(
            datetime.fromisoformat(changed["planned_end"]),
            datetime.fromisoformat(block["planned_end"]),
        )

    def test_shorten_short_block_never_extends_or_overlaps_neighbor(self):
        block = self.add_test_block(start="09:00", end="09:10")
        neighbor = self.add_test_block("Neighbor", "09:10", "10:00")
        recommendation = next(
            item
            for item in generate_recommendations(
                self.plan["plan_id"],
                now=f"{self.DAY}T11:00:00",
                db_path=self.db_path,
            )
            if item["recommendation_type"] == "shorten_block"
        )
        applied = apply_recommendation(
            recommendation["recommendation_id"],
            confirmed=True,
            db_path=self.db_path,
        )
        replayed = apply_recommendation(
            recommendation["recommendation_id"],
            confirmed=True,
            db_path=self.db_path,
        )
        changed = next(
            item
            for item in list_blocks(self.plan["plan_id"], db_path=self.db_path)
            if item["block_id"] == block["block_id"]
        )
        self.assertLess(
            datetime.fromisoformat(changed["planned_end"]),
            datetime.fromisoformat(block["planned_end"]),
        )
        self.assertLessEqual(changed["planned_end"], neighbor["planned_start"])
        self.assertEqual(applied["applied_at"], replayed["applied_at"])

    def test_extremely_short_block_does_not_receive_misleading_shorten(self):
        self.add_test_block(start="09:00", end="09:01")
        recommendations = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T11:00:00",
            db_path=self.db_path,
        )
        self.assertNotIn(
            "shorten_block",
            {item["recommendation_type"] for item in recommendations},
        )

    def test_recommendation_generation_reuses_identical_evaluation(self):
        first = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T08:00:00",
            db_path=self.db_path,
        )
        second = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T08:00:00",
            db_path=self.db_path,
        )
        self.assertEqual(
            [item["recommendation_id"] for item in second],
            [item["recommendation_id"] for item in first],
        )
        self.assertEqual(
            len(list_recommendations(self.plan["plan_id"], db_path=self.db_path)),
            len(first),
        )

    def test_recommendation_generation_changes_for_new_time_or_snapshot(self):
        first = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T08:00:00",
            db_path=self.db_path,
        )
        later = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T08:01:00",
            db_path=self.db_path,
        )
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO recovery_scores(
                    date, recovery_score, activity_load_score,
                    training_load_score, readiness_score, recommendation
                ) VALUES(?, 80, 50, 50, NULL, 'test')
                """,
                (self.DAY,),
            )
            connection.commit()
        changed_snapshot = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T08:01:00",
            db_path=self.db_path,
        )
        self.assertNotEqual(first[0]["recommendation_id"], later[0]["recommendation_id"])
        self.assertNotEqual(later[0]["recommendation_id"], changed_snapshot[0]["recommendation_id"])

    def test_recommendation_fingerprints_keep_types_and_blocks_distinct(self):
        first = self.add_test_block("First", "09:00", "10:00", cognitive_demand="high")
        second = self.add_test_block("Second", "10:00", "11:00", cognitive_demand="high")
        self.insert_cognitive_run(accuracy=0.6)
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO recovery_scores(
                    date, recovery_score, activity_load_score,
                    training_load_score, readiness_score, recommendation
                ) VALUES(?, 30, 50, 50, 40, 'test')
                """,
                (self.DAY,),
            )
            connection.commit()
        same_block = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T09:30:00",
            db_path=self.db_path,
        )
        later_block = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T10:30:00",
            db_path=self.db_path,
        )
        self.assertTrue(
            {"move_high_demand_block", "switch_to_low_demand_task"}
            <= {item["recommendation_type"] for item in same_block}
        )
        self.assertEqual(
            next(
                item["related_block_id"]
                for item in same_block
                if item["recommendation_type"] == "move_high_demand_block"
            ),
            first["block_id"],
        )
        self.assertEqual(
            next(
                item["related_block_id"]
                for item in later_block
                if item["recommendation_type"] == "move_high_demand_block"
            ),
            second["block_id"],
        )

    def test_acknowledge_does_not_apply(self):
        block = self.add_test_block()
        recommendation = generate_recommendations(
            self.plan["plan_id"],
            now=f"{self.DAY}T11:00:00",
            db_path=self.db_path,
        )[0]
        acknowledged = acknowledge_recommendation(
            recommendation["recommendation_id"],
            db_path=self.db_path,
        )
        current = list_blocks(self.plan["plan_id"], db_path=self.db_path)[0]
        self.assertIsNotNone(acknowledged["acknowledged_at"])
        self.assertIsNone(acknowledged["applied_at"])
        self.assertEqual(current["planned_end"], block["planned_end"])

    def test_timeline_and_progress_query_are_stable(self):
        first = self.add_test_block()
        self.add_test_block("Recovery", "10:00", "10:30", block_type="recovery")
        transition_block(first["block_id"], "completed", db_path=self.db_path)
        summary = get_timeline_summary(
            self.plan["plan_id"],
            now=f"{self.DAY}T10:15:00",
            db_path=self.db_path,
        )
        rows = get_progress_lab_rows(
            start_date=self.DAY,
            end_date=self.DAY,
            db_path=self.db_path,
        )
        self.assertEqual(summary["completion_percent"], 50.0)
        self.assertEqual(summary["recovery_minutes"], 30)
        self.assertEqual(rows[0]["completed_block_count"], 1)
        self.assertEqual(json.loads(json.dumps(rows))[0]["plan_id"], self.plan["plan_id"])


if __name__ == "__main__":
    unittest.main()
