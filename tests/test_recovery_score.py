import sqlite3
import unittest

from src import db, recovery_score


class RecoveryScoreTests(unittest.TestCase):
    def make_connection(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)
        return connection

    def test_activity_load_increases_with_steps_and_active_calories(self):
        low = recovery_score.calculate_activity_load_score(steps=2000, active_calories=200)
        medium = recovery_score.calculate_activity_load_score(steps=8000, active_calories=900)
        high = recovery_score.calculate_activity_load_score(steps=18000, active_calories=2200)

        self.assertLess(low, medium)
        self.assertLess(medium, high)
        self.assertEqual(high, 100)

    def test_training_load_increases_with_duration_and_calories(self):
        low = recovery_score.calculate_training_load_score("PT10M", 100)
        medium = recovery_score.calculate_training_load_score("PT60M", 500)
        high = recovery_score.calculate_training_load_score("PT3H", 1200)

        self.assertLess(low, medium)
        self.assertLess(medium, high)
        self.assertEqual(high, 100)

    def test_recommendation_ranges(self):
        self.assertEqual(recovery_score.recommendation_for_score(90), "正常训练")
        self.assertEqual(recovery_score.recommendation_for_score(70), "适度训练")
        self.assertEqual(recovery_score.recommendation_for_score(50), "减量训练")
        self.assertEqual(recovery_score.recommendation_for_score(30), "恢复优先")

    def test_load_without_recovery_evidence_is_not_scored(self):
        easy = recovery_score.calculate_recovery_score(
            {
                "date": "2026-07-10",
                "steps": 1000,
                "active_calories": 100,
                "training_duration": None,
                "training_calories": 0,
            }
        )
        hard = recovery_score.calculate_recovery_score(
            {
                "date": "2026-07-11",
                "steps": 20000,
                "active_calories": 2200,
                "training_duration": "PT2H",
                "training_calories": 1200,
            }
        )

        self.assertIsNone(easy["recovery_score"])
        self.assertIsNone(hard["recovery_score"])
        self.assertIsNone(easy["recommendation"])
        self.assertIsNone(hard["recommendation"])

    def test_rebuild_recovery_scores_upserts_rows(self):
        connection = self.make_connection()
        connection.execute(
            """
            INSERT INTO daily_recovery_metrics (
                date, steps, active_calories, training_count, training_duration, training_calories
            )
            VALUES ('2026-07-10', 1000, 100, 0, NULL, 0)
            """
        )
        connection.execute(
            """INSERT INTO recovery_scores
               (date,recovery_score,activity_load_score,training_load_score,score_version,recommendation)
               VALUES ('2026-07-10', 74, 20, 20, 'v1.0', '适度训练')"""
        )
        connection.commit()

        first_count = recovery_score.rebuild_recovery_scores(connection)
        connection.execute(
            """
            UPDATE daily_recovery_metrics
            SET steps = 20000, active_calories = 2200, training_duration = 'PT2H', training_calories = 1200
            WHERE date = '2026-07-10'
            """
        )
        connection.commit()
        second_count = recovery_score.rebuild_recovery_scores(connection)

        row_count = connection.execute("SELECT COUNT(*) FROM recovery_scores").fetchone()[0]
        row = connection.execute("SELECT * FROM recovery_scores").fetchone()

        self.assertEqual(first_count, 0)
        self.assertEqual(second_count, 0)
        self.assertEqual(row_count, 0)
        self.assertIsNone(row)
        connection.close()


if __name__ == "__main__":
    unittest.main()
