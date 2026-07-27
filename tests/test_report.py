import sqlite3
import tempfile
import unittest
from pathlib import Path

from src import db, report


class ReportTests(unittest.TestCase):
    def make_connection(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)
        return connection

    def insert_metric_and_score(
        self,
        connection,
        date,
        steps=1000,
        calories=2000,
        active_calories=500,
        activity_duration="PT1H",
        training_count=1,
        training_duration="PT30M",
        training_calories=300,
        recovery_score=80,
        recommendation="正常训练",
    ):
        connection.execute(
            """
            INSERT INTO daily_recovery_metrics (
                date, steps, calories, active_calories, activity_duration,
                training_count, training_duration, training_calories
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                date,
                steps,
                calories,
                active_calories,
                activity_duration,
                training_count,
                training_duration,
                training_calories,
            ),
        )
        connection.execute(
            """
            INSERT INTO recovery_scores (
                date, recovery_score, activity_load_score, training_load_score, recommendation
            )
            VALUES (?, ?, 10, 20, ?)
            """,
            (date, recovery_score, recommendation),
        )
        connection.commit()

    def test_get_latest_report_date(self):
        connection = self.make_connection()
        self.insert_metric_and_score(connection, "2026-07-09")
        self.insert_metric_and_score(connection, "2026-07-10")

        self.assertEqual(report.get_latest_report_date(connection), "2026-07-10")
        connection.close()

    def test_render_report_contains_required_fields(self):
        data = {
            "date": "2026-07-10",
            "recovery_score": 86,
            "recommendation": "正常训练",
            "steps": 1234,
            "calories": 2100,
            "active_calories": 600,
            "activity_duration": "PT1H",
            "training_count": 1,
            "training_duration": "PT30M",
            "training_calories": 300,
        }

        content = report.render_report(data)

        for expected in (
            "# RHYTHMOS｜律衡 每日状态报告 - 2026-07-10",
            "恢复分数：86",
            "训练建议：正常训练",
            "步数：1234",
            "总热量：2100",
            "活跃热量：600",
            "活动时长：PT1H",
            "训练次数：1",
            "训练时长：PT30M",
            "训练热量：300",
        ):
            self.assertIn(expected, content)

    def test_generate_daily_report_defaults_to_latest_day(self):
        connection = self.make_connection()
        self.insert_metric_and_score(connection, "2026-07-09", recovery_score=70)
        self.insert_metric_and_score(connection, "2026-07-10", recovery_score=90)

        with tempfile.TemporaryDirectory() as directory:
            path, content = report.generate_daily_report(
                connection=connection,
                reports_dir=Path(directory),
            )

            self.assertEqual(path.name, "daily_report_2026-07-10.md")
            self.assertTrue(path.exists())
            self.assertIn("恢复分数：90", content)
            self.assertEqual(path.read_text(encoding="utf-8"), content)
        connection.close()

    def test_generate_daily_report_accepts_specific_date(self):
        connection = self.make_connection()
        self.insert_metric_and_score(connection, "2026-07-09", recovery_score=70)
        self.insert_metric_and_score(connection, "2026-07-10", recovery_score=90)

        with tempfile.TemporaryDirectory() as directory:
            path, content = report.generate_daily_report(
                report_date="2026-07-09",
                connection=connection,
                reports_dir=Path(directory),
            )

            self.assertEqual(path.name, "daily_report_2026-07-09.md")
            self.assertIn("恢复分数：70", content)
        connection.close()

    def test_missing_date_raises_report_error(self):
        connection = self.make_connection()
        self.insert_metric_and_score(connection, "2026-07-10")

        with self.assertRaises(report.ReportError):
            report.load_report_data(connection, "2026-07-01")
        connection.close()

    def test_report_always_contains_local_safety_disclaimer(self):
        data = {"date": "2026-07-10", "recovery_score": 80, "score_version": "v1.0",
                "recommendation": "normal", "steps": 1, "calories": 1, "active_calories": 1,
                "activity_duration": None, "training_count": 0, "training_duration": None,
                "training_calories": 0, "local_coach": None}
        content = report.render_report(data)
        self.assertIn("今日教练建议", content)
        self.assertIn("不构成医疗诊断或治疗意见", content)

    def test_report_renders_prospective_progress_without_health_values(self):
        content = report.render_prospective_section({
            "status": "collecting", "eligible_unique_days": 0,
            "target_unique_days": 14, "remaining_unique_days": 14,
            "late_generation_count": 0,
        })
        self.assertIn("真实合格天数：0 / 14", content)
        self.assertIn("历史记录", content)


if __name__ == "__main__":
    unittest.main()
