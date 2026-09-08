import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src import db
from src.mobile_snapshot import (
    CONTRACT_KIND,
    CONTRACT_VERSION,
    MobileSnapshotContractError,
    build_mobile_daily_snapshot,
    validate_mobile_daily_snapshot,
    write_mobile_daily_snapshot,
)
from src.nutrition_logging import create_meal_record, food_catalog_by_name


class MobileDailySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "recovery.db"
        self.connection = db.connect(self.path)

    def tearDown(self):
        if self.connection is not None:
            self.connection.close()
        self.temp.cleanup()

    def test_snapshot_exports_only_mobile_safe_today_projection(self):
        self.connection.execute(
            """INSERT INTO daily_recovery_metrics(
                   date,sleep_duration,sleep_score,nightly_hrv_rmssd,
                   nightly_resting_hr,respiration_rate,morning_rmssd,morning_mean_hr
               ) VALUES('2026-09-07','PT7H30M',82,52,49,14,44,56)"""
        )
        self.connection.execute(
            """INSERT INTO recovery_scores(
                   date,recovery_score,activity_load_score,training_load_score,
                   score_version,recommendation
               ) VALUES('2026-09-07',84,20,16,'1.0.0','正常训练')"""
        )
        self.connection.execute(
            """INSERT INTO recovery_confidence(
                   date,data_completeness_score,baseline_maturity_score,
                   confidence_score,confidence_level,group_scores_json,
                   available_groups_json,missing_groups_json,confidence_version
               ) VALUES('2026-09-07',90,80,86,'high','{}','[]','[\"respiration\"]','1.0.0')"""
        )
        self.connection.execute(
            """INSERT INTO polar_sleep_raw(source,external_id,date,raw_json)
               VALUES('polar','sleep-1','2026-09-07',?)""",
            (json.dumps({
                "sleepResult": {
                    "hypnogram": {
                        "sleepStart": "2026-09-07T01:02:47+08:00",
                        "sleepEnd": "2026-09-07T08:32:47+08:00",
                    },
                },
                "sleepEvaluation": {
                    "sleepSpan": "27000s",
                    "asleepDuration": "25200s",
                    "phaseDurations": {"deep": "5400s", "rem": "4500s"},
                },
                "averageHeartRate": 55.93,
            }),),
        )
        self.connection.execute(
            """INSERT INTO polar_training_sessions_raw(
                   source,external_id,date,raw_json,sport,duration,calories
               ) VALUES('polar','session-1','2026-09-07','{}','running','PT45M',460)"""
        )
        self.connection.commit()

        snapshot = build_mobile_daily_snapshot(
            self.path,
            "2026-09-07",
            generated_at=datetime(2026, 9, 7, 5, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(snapshot["kind"], CONTRACT_KIND)
        self.assertEqual(snapshot["version"], CONTRACT_VERSION)
        self.assertEqual(snapshot["generated_at"], "2026-09-07T05:30:00Z")
        self.assertEqual(snapshot["date"], "2026-09-07")
        self.assertEqual(snapshot["recovery"]["status"], "ready")
        self.assertEqual(snapshot["recovery"]["recommendation_code"], "normal_training")
        self.assertEqual(snapshot["recovery"]["morning_hrv_rmssd_ms"]["value"], 44)
        self.assertEqual(snapshot["sleep"]["duration_minutes"]["value"], 450)
        self.assertEqual(snapshot["sleep"]["sleep_start_time"]["value"], "2026-09-07T01:02:47+08:00")
        self.assertEqual(snapshot["sleep"]["wake_time"]["value"], "2026-09-07T08:32:47+08:00")
        self.assertEqual(snapshot["sleep"]["actual_duration_minutes"]["value"], 420)
        self.assertEqual(snapshot["sleep"]["deep_duration_minutes"]["value"], 90)
        self.assertEqual(snapshot["sleep"]["rem_duration_minutes"]["value"], 75)
        self.assertEqual(snapshot["sleep"]["average_hr_bpm"]["value"], 55.93)
        self.assertIsNone(snapshot["sleep"]["regularity_score"]["value"])
        self.assertEqual(snapshot["sleep"]["regularity_score"]["provenance"]["source"], "missing")
        self.assertEqual(
            set(snapshot["recovery"]["details"]),
            {
                "pns_index", "sns_index", "physiological_age_years", "mean_rr_ms",
                "sdnn_ms", "poincare_sd1_ms", "poincare_sd2_ms", "stress_index",
                "respiration_rate_bpm", "measurement_quality",
            },
        )
        self.assertEqual(snapshot["training"], {
            "session_count": 1,
            "duration_minutes": 45.0,
            "calories_kcal": 460,
            "sports": ["running"],
        })
        self.assertNotIn("raw_json", json.dumps(snapshot))
        self.assertNotIn("session-1", json.dumps(snapshot))

    def test_explicit_empty_date_remains_explicitly_unavailable(self):
        snapshot = build_mobile_daily_snapshot(
            self.path,
            "2026-09-07",
            generated_at="2026-09-07T00:00:00Z",
        )

        self.assertEqual(snapshot["recovery"]["status"], "insufficient_data")
        self.assertIsNone(snapshot["recovery"]["score"])
        self.assertIsNone(snapshot["sleep"]["duration_minutes"]["value"])
        self.assertIsNone(snapshot["sleep"]["regularity_score"]["value"])
        self.assertEqual(snapshot["training"]["session_count"], 0)

    def test_sleep_regularity_score_is_exported_after_seven_valid_nights(self):
        history = []
        for day in range(1, 8):
            date_value = f"2026-09-{day:02d}"
            history.append({
                "date": date_value,
                "resolved_fields": {
                    "sleep_start_time": {"value": f"{date_value}T23:00:00+08:00"},
                    "wake_time": {"value": f"{date_value}T07:00:00+08:00"},
                    "actual_sleep_duration_minutes": {"value": 450},
                },
            })

        with patch("src.mobile_snapshot.get_sleep_history", return_value=history):
            snapshot = build_mobile_daily_snapshot(self.path, "2026-09-07")

        regularity = snapshot["sleep"]["regularity_score"]
        self.assertEqual(regularity["value"], 100.0)
        self.assertEqual(regularity["provenance"]["source"], "sleep_regularity")

    def test_training_uses_the_desktop_local_projection_for_manual_activity(self):
        self.connection.execute(
            """INSERT INTO manual_activity_sessions(
                   date,duration_minutes,calories_kcal,activity_type,activity_name
               ) VALUES('2026-09-07',55,320,'strength_training','上肢力量')"""
        )
        self.connection.commit()

        snapshot = build_mobile_daily_snapshot(
            self.path,
            "2026-09-07",
            generated_at="2026-09-07T00:00:00Z",
        )

        self.assertEqual(snapshot["training"], {
            "session_count": 1,
            "duration_minutes": 55.0,
            "calories_kcal": 320.0,
            "sports": ["strength_training"],
        })

    def test_nutrition_uses_the_same_daily_feedback_as_desktop(self):
        catalog = food_catalog_by_name(self.connection)
        create_meal_record(self.connection, {
            "date": "2026-09-07", "meal_type": "breakfast", "eaten_at": "08:00",
        }, [{"food_catalog_id": catalog["egg"]["id"], "quantity": 2, "unit": "piece"}])

        snapshot = build_mobile_daily_snapshot(self.path, "2026-09-07")
        nutrition = snapshot["nutrition"]

        self.assertEqual(nutrition["recorded_meals"], 1)
        self.assertEqual(nutrition["food_count"], 1)
        self.assertEqual(nutrition["identified_food_count"], 1)
        self.assertEqual(nutrition["meals"], [{
            "meal_type": "breakfast", "meal_slot": "meal_1", "eaten_at": "08:00",
            "items": [{
                "food_name": "鸡蛋", "item_type": "food", "quantity": 2.0, "unit": "piece",
                "identified": True,
                "nutrients": {
                    "calories_kcal": 143.0, "protein_g": 12.56, "carbohydrate_g": 0.72,
                    "fat_g": 9.51, "fiber_g": 0.0, "water_ml": 76.15,
                },
            }],
        }])
        self.assertEqual(
            [item["metric"] for item in nutrition["metrics"]],
            ["calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "fiber_g", "water_ml"],
        )
        protein = nutrition["metrics"][1]
        self.assertEqual(protein["current"], 12.56)
        self.assertEqual(protein["status"], "recorded")

    def test_nutrition_projects_the_active_desktop_cycle_plan(self):
        cursor = self.connection.execute(
            """INSERT INTO nutrition_plan_cycles(uuid,name,start_date,end_date,status)
               VALUES('cycle-1','每周饮食循环','2026-09-07','2026-10-04','active')"""
        )
        self.connection.execute(
            """INSERT INTO user_weekly_plans(
                   plan_id,week_start,title,timezone,nutrition_cycle_id
               ) VALUES('nutrition-week-1','2026-09-07','每周饮食循环','local',?)""",
            (cursor.lastrowid,),
        )
        self.connection.execute(
            """INSERT INTO user_weekly_plan_items(
                   item_id,plan_id,weekday,title,start_time,end_time,category,notes
               ) VALUES('breakfast-1','nutrition-week-1',0,'燕麦、酸奶','08:00','08:45','meal',
                         '__nutrition_manual_recipe__:breakfast|{}')"""
        )
        self.connection.commit()

        plan = build_mobile_daily_snapshot(self.path, "2026-09-07")["nutrition"]["plan"]

        self.assertEqual(plan["cycle_name"], "每周饮食循环")
        self.assertEqual(plan["week_start"], "2026-09-07")
        self.assertEqual((plan["week_index"], plan["week_count"]), (1, 4))
        self.assertEqual(plan["entries"], [{
            "weekday": 0, "meal_slot": "breakfast", "start_time": "08:00",
            "end_time": "08:45", "title": "燕麦、酸奶",
        }])

    def test_missing_database_has_no_implicit_snapshot(self):
        self.connection.close()
        self.path.unlink()
        self.connection = None

        self.assertIsNone(build_mobile_daily_snapshot(self.path))

    def test_writer_creates_json_only_for_a_factual_or_selected_day(self):
        output = Path(self.temp.name) / "exports" / "today.json"

        exported = write_mobile_daily_snapshot(
            output,
            self.path,
            "2026-09-07",
            generated_at="2026-09-07T00:00:00Z",
        )

        self.assertTrue(exported)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["date"], "2026-09-07")

    def test_contract_validator_accepts_exported_snapshot(self):
        snapshot = build_mobile_daily_snapshot(
            self.path,
            "2026-09-07",
            generated_at="2026-09-07T00:00:00Z",
        )

        self.assertIs(validate_mobile_daily_snapshot(snapshot), snapshot)

    def test_contract_validator_rejects_unknown_members(self):
        snapshot = build_mobile_daily_snapshot(
            self.path,
            "2026-09-07",
            generated_at="2026-09-07T00:00:00Z",
        )
        snapshot["training"]["debug_session_ids"] = []

        with self.assertRaisesRegex(MobileSnapshotContractError, "unexpected keys: debug_session_ids"):
            validate_mobile_daily_snapshot(snapshot)

    def test_contract_validator_rejects_inconsistent_or_unsafe_values(self):
        snapshot = build_mobile_daily_snapshot(
            self.path,
            "2026-09-07",
            generated_at="2026-09-07T00:00:00Z",
        )
        inconsistent = copy.deepcopy(snapshot)
        inconsistent["recovery"]["status"] = "ready"
        with self.assertRaisesRegex(MobileSnapshotContractError, "inconsistent"):
            validate_mobile_daily_snapshot(inconsistent)

        unsafe = copy.deepcopy(snapshot)
        unsafe["sleep"]["score"]["value"] = float("nan")
        with self.assertRaisesRegex(MobileSnapshotContractError, "JSON-safe"):
            validate_mobile_daily_snapshot(unsafe)


if __name__ == "__main__":
    unittest.main()
