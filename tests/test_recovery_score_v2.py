import sqlite3
import unittest

from src import db, recovery_score


class RecoveryScoreV2Tests(unittest.TestCase):
    def make_connection(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)
        return connection

    def test_hrv_score_increases_with_rmssd(self):
        low = recovery_score.calculate_hrv_score(20)
        medium = recovery_score.calculate_hrv_score(50)
        high = recovery_score.calculate_hrv_score(80)

        self.assertLess(low, medium)
        self.assertLess(medium, high)
        self.assertEqual(high, 100)

    def test_morning_hr_score_decreases_with_higher_hr(self):
        good = recovery_score.calculate_morning_hr_score(50)
        medium = recovery_score.calculate_morning_hr_score(65)
        poor = recovery_score.calculate_morning_hr_score(85)

        self.assertGreater(good, medium)
        self.assertGreater(medium, poor)
        self.assertEqual(good, 100)
        self.assertEqual(poor, 0)

    def test_readiness_score_accepts_labels_and_numbers(self):
        self.assertEqual(recovery_score.calculate_readiness_score("Excellent"), 95)
        self.assertEqual(recovery_score.calculate_readiness_score("Good"), 80)
        self.assertEqual(recovery_score.calculate_readiness_score("40"), 40)
        self.assertIsNone(recovery_score.calculate_readiness_score(""))

    def test_calculate_recovery_score_uses_v2_when_kubios_exists(self):
        score = recovery_score.calculate_recovery_score(
            {
                "date": "2026-07-10",
                "steps": 20000,
                "active_calories": 2200,
                "training_duration": "PT2H",
                "training_calories": 1200,
                "morning_rmssd": 80,
                "morning_mean_hr": 50,
                "kubios_readiness": "Excellent",
            }
        )

        self.assertEqual(score["score_version"], "v0.2")
        self.assertEqual(score["hrv_score"], 100)
        self.assertEqual(score["morning_hr_score"], 100)
        self.assertEqual(score["readiness_score"], 95)
        self.assertGreater(score["recovery_score"], 60)

    def test_calculate_recovery_score_is_unscored_without_recovery_evidence(self):
        score = recovery_score.calculate_recovery_score(
            {
                "date": "2026-07-10",
                "steps": 1000,
                "active_calories": 100,
                "training_duration": None,
                "training_calories": 0,
                "morning_rmssd": None,
                "morning_mean_hr": None,
                "kubios_readiness": None,
            }
        )

        self.assertEqual(score["score_version"], "unscored_insufficient_recovery_evidence")
        self.assertIsNone(score["recovery_score"])
        self.assertIsNone(score["recommendation"])
        self.assertIsNone(score["hrv_score"])
        self.assertIsNone(score["morning_hr_score"])
        self.assertIsNone(score["readiness_score"])

    def test_rebuild_recovery_scores_upserts_v2_columns(self):
        connection = self.make_connection()
        connection.execute(
            """
            INSERT INTO daily_recovery_metrics (
                date,
                steps,
                active_calories,
                training_count,
                training_duration,
                training_calories,
                morning_rmssd,
                morning_mean_hr,
                kubios_readiness
            )
            VALUES ('2026-07-10', 8000, 900, 0, NULL, 0, 50, 60, 'Good')
            """
        )
        connection.commit()

        count = recovery_score.rebuild_recovery_scores(connection)
        row = connection.execute("SELECT * FROM recovery_scores").fetchone()

        self.assertEqual(count, 1)
        self.assertEqual(row["score_version"], "v0.2")
        self.assertIsNotNone(row["hrv_score"])
        self.assertIsNotNone(row["morning_hr_score"])
        self.assertEqual(row["readiness_score"], 80)
        connection.close()


if __name__ == "__main__":
    unittest.main()
