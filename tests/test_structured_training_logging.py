import json
import math
from pathlib import Path
import sqlite3
import tempfile
import unittest

from src import db
from src.training_logging import (
    LB_TO_KG, ai_training_summaries, copy_exercise, copy_set,
    create_manual_training_session, ensure_polar_session_index,
    get_training_session, list_exercise_catalog, list_training_sessions,
    save_training_details, soft_delete_training_session,
)


ROOT = Path(__file__).resolve().parents[1]


class StructuredTrainingLoggingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "training.db"
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        db.init_db(self.connection)

    def tearDown(self):
        self.connection.close()
        self.directory.cleanup()

    def _polar(self, external_id="polar-1", date="2026-07-17", start="2026-07-17T16:32:33"):
        raw = {
            "identifier": {"id": external_id}, "startTime": start,
            "stopTime": "2026-07-17T17:58:13", "durationMillis": 5136000,
            "hrAvg": 105, "hrMax": 144, "calories": 605,
            "distanceMeters": 10250, "sport": {"id": "15"},
        }
        self.connection.execute(
            """INSERT INTO polar_training_sessions_raw(
                   source,external_id,date,raw_json,sport,start_time,duration,calories
               ) VALUES('polar',?,?,?,?,?,?,?)""",
            (external_id, date, json.dumps(raw), "15", start, "PT1H25M36S", 605),
        )
        self.connection.commit()

    def _manual(self, sport="strength"):
        return create_manual_training_session(self.connection, {
            "date": "2026-07-18", "start_time": "08:00:00",
            "duration_seconds": 3600, "resolved_sport_type": sport,
            "status": "draft",
        })

    def _strength_exercise(self, unit="kg", load=80, reps=8, completed=True):
        squat = next(item for item in list_exercise_catalog(self.connection)
                     if item["canonical_name"] == "barbell_back_squat")
        return {
            "exercise_catalog_id": squat["id"],
            "sets": [{
                "set_type": "working", "load_value": load, "load_unit": unit,
                "reps": reps, "rpe": 8, "rir": 2, "rest_seconds": 120,
                "side": "bilateral", "completed": completed,
            }],
        }

    def test_schema_migration_catalog_integrity_and_idempotency(self):
        tables = {row[0] for row in self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        self.assertTrue({"training_sessions", "exercise_catalog", "training_exercises", "training_sets"} <= tables)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM exercise_catalog").fetchone()[0], 23)
        self.assertEqual(self.connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(self.connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        db.init_db(self.connection)
        latest = self.connection.execute(
            "SELECT sequence,version FROM schema_migrations ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(tuple(latest), (db.SCHEMA_MIGRATIONS[-1].sequence, db.SCHEMA_MIGRATIONS[-1].version))

    def test_polar_sessions_are_indexed_individually_on_same_day(self):
        self._polar("polar-1", start="2026-07-17T08:00:00")
        self._polar("polar-2", start="2026-07-17T18:00:00")
        self.assertEqual(ensure_polar_session_index(self.connection), 2)
        self.assertEqual(ensure_polar_session_index(self.connection), 0)
        sessions = list_training_sessions(self.connection)
        self.assertEqual(len(sessions), 2)
        self.assertEqual({item["polar_external_id"] for item in sessions}, {"polar-1", "polar-2"})
        self.assertNotEqual(sessions[0]["uuid"], sessions[1]["uuid"])

    def test_polar_objective_fields_remain_authoritative(self):
        self._polar(); ensure_polar_session_index(self.connection)
        session = list_training_sessions(self.connection)[0]
        with self.assertRaisesRegex(ValueError, "POLAR_OBJECTIVE_FIELDS_READ_ONLY"):
            save_training_details(self.connection, session["id"], {
                "average_hr": 50, "status": "completed",
            }, [])
        refreshed = get_training_session(self.connection, session["id"])
        self.assertEqual(refreshed["average_hr"], 105)
        self.assertEqual(refreshed["max_hr"], 144)
        self.assertEqual(refreshed["calories"], 605)
        self.assertEqual(refreshed["distance_meters"], 10250)

    def test_sport_override_preserves_original_polar_sport(self):
        self._polar(); ensure_polar_session_index(self.connection)
        session = list_training_sessions(self.connection)[0]
        save_training_details(self.connection, session["id"], {
            "resolved_sport_type": "舞蹈技术训练", "status": "completed",
        }, [])
        refreshed = get_training_session(self.connection, session["id"])
        self.assertEqual(refreshed["polar_sport_type"], "15")
        self.assertEqual(refreshed["resolved_sport_type"], "舞蹈技术训练")
        self.assertEqual(refreshed["resolved_sport_type_source"], "manual_override")

    def test_manual_session_uuid_and_polar_external_id_are_unique(self):
        first = self._manual(); second = self._manual()
        rows = self.connection.execute(
            "SELECT uuid FROM training_sessions WHERE id IN (?,?)", (first, second)
        ).fetchall()
        self.assertNotEqual(rows[0][0], rows[1][0])
        self._polar(); ensure_polar_session_index(self.connection)
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """INSERT INTO training_sessions(
                       uuid,date,resolved_sport_type,resolved_sport_type_source,
                       source,polar_external_id,status
                   ) VALUES('duplicate','2026-07-18','15','polar','polar','polar-1','completed')"""
            )

    def test_strength_details_crud_and_summary(self):
        session_id = self._manual()
        exercise = self._strength_exercise()
        exercise["sets"].insert(0, {
            "set_type": "warmup", "load_value": 40, "load_unit": "kg",
            "reps": 10, "completed": True,
        })
        save_training_details(self.connection, session_id, {
            "resolved_sport_type": "strength", "status": "completed",
        }, [exercise])
        record = get_training_session(self.connection, session_id)
        self.assertEqual(record["summary"]["exercise_count"], 1)
        self.assertEqual(record["summary"]["total_set_count"], 2)
        self.assertEqual(record["summary"]["working_set_count"], 1)
        self.assertEqual(record["summary"]["warmup_set_count"], 1)
        self.assertEqual(record["summary"]["total_reps"], 18)
        self.assertEqual(record["summary"]["strength_volume_load_kg"], 640)
        self.assertEqual(record["summary"]["muscle_group_set_counts"], {"lower_body": 1})

        save_training_details(self.connection, session_id, {
            "resolved_sport_type": "strength", "status": "completed",
        }, [])
        self.assertEqual(get_training_session(self.connection, session_id)["summary"]["exercise_count"], 0)
        self.assertGreater(self.connection.execute(
            "SELECT COUNT(*) FROM training_exercises WHERE deleted_at IS NOT NULL"
        ).fetchone()[0], 0)

    def test_lb_conversion_bodyweight_and_assistance_boundaries(self):
        session_id = self._manual()
        pound = self._strength_exercise("lb", 100, 10)
        bodyweight = {
            "custom_exercise_name": "自重动作", "exercise_category": "bodyweight",
            "measurement_mode": "bodyweight_reps", "primary_muscle_group": "core",
            "sets": [{"load_unit": "bodyweight", "reps": 10, "completed": True}],
        }
        assisted = {
            "custom_exercise_name": "辅助动作", "exercise_category": "bodyweight",
            "measurement_mode": "assisted_reps", "primary_muscle_group": "back",
            "sets": [{"load_unit": "assisted_kg", "load_value": 20, "reps": 10, "completed": True}],
        }
        save_training_details(self.connection, session_id, {"status": "completed"}, [pound, bodyweight, assisted])
        summary = get_training_session(self.connection, session_id)["summary"]
        self.assertAlmostEqual(summary["strength_volume_load_kg"], 100 * 10 * LB_TO_KG, places=2)
        self.assertEqual(summary["total_reps"], 30)

    def test_rpe_rir_load_and_nonfinite_validation(self):
        session_id = self._manual()
        invalids = [
            {"load_value": -1, "load_unit": "kg", "reps": 5},
            {"load_value": 10, "load_unit": "kg", "reps": 5, "rpe": 11},
            {"load_value": 10, "load_unit": "kg", "reps": 5, "rir": -1},
            {"load_value": math.nan, "load_unit": "kg", "reps": 5},
            {"load_value": math.inf, "load_unit": "kg", "reps": 5},
            {"load_value": 10, "load_unit": "kg", "reps": 1.5},
        ]
        for set_row in invalids:
            exercise = self._strength_exercise()
            exercise["sets"] = [{**set_row, "completed": True}]
            with self.assertRaises(ValueError):
                save_training_details(self.connection, session_id, {"status": "draft"}, [exercise])

    def test_time_dance_and_cardio_modes_do_not_force_weight_reps_or_sets(self):
        session_id = self._manual("mixed")
        plank = {
            "custom_exercise_name": "悬垂", "exercise_category": "bodyweight",
            "measurement_mode": "duration", "sets": [{"duration_seconds": 60, "completed": True}],
        }
        dance = {
            "custom_exercise_name": "完整表演", "exercise_category": "dance",
            "measurement_mode": "dance_practice", "sets": [{"reps": 3, "rpe": 8, "completed": True}],
        }
        cardio = {
            "custom_exercise_name": "跑步", "exercise_category": "cardio",
            "measurement_mode": "distance_duration", "sets": [],
        }
        save_training_details(self.connection, session_id, {"status": "completed"}, [plank, dance, cardio])
        record = get_training_session(self.connection, session_id)
        self.assertEqual(record["summary"]["exercise_count"], 3)
        self.assertEqual(record["summary"]["total_set_count"], 2)

    def test_blank_sets_are_not_inserted_and_empty_exercise_is_rejected(self):
        session_id = self._manual()
        exercise = self._strength_exercise(); exercise["sets"] = [{}]
        save_training_details(self.connection, session_id, {"status": "draft"}, [exercise])
        self.assertEqual(get_training_session(self.connection, session_id)["summary"]["total_set_count"], 0)
        with self.assertRaisesRegex(ValueError, "EXERCISE_NAME_REQUIRED"):
            save_training_details(self.connection, session_id, {"status": "draft"}, [{"sets": []}])

    def test_copy_set_and_exercise_use_new_uuids_and_reset_completion(self):
        source_set = {"uuid": "set-source", "load_value": 80, "load_unit": "kg", "reps": 8, "completed": True}
        copied_set = copy_set(source_set)
        self.assertNotEqual(copied_set["uuid"], source_set["uuid"])
        self.assertFalse(copied_set["completed"])
        source_exercise = {"uuid": "exercise-source", "custom_exercise_name": "动作", "sets": [source_set]}
        copied_exercise = copy_exercise(source_exercise, reset_completed=True)
        self.assertNotEqual(copied_exercise["uuid"], source_exercise["uuid"])
        self.assertFalse(copied_exercise["sets"][0]["completed"])

    def test_soft_delete_hides_session_without_deleting_children(self):
        session_id = self._manual()
        save_training_details(self.connection, session_id, {"status": "completed"}, [self._strength_exercise()])
        child_count = self.connection.execute("SELECT COUNT(*) FROM training_exercises").fetchone()[0]
        self.assertTrue(soft_delete_training_session(self.connection, session_id))
        self.assertIsNone(get_training_session(self.connection, session_id))
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM training_exercises").fetchone()[0], child_count)

    def test_ai_summary_excludes_notes_and_raw_set_details(self):
        session_id = self._manual()
        exercise = self._strength_exercise(); exercise["notes"] = "private exercise note"
        exercise["sets"][0]["notes"] = "private set note"
        save_training_details(self.connection, session_id, {
            "status": "completed", "notes": "private session note",
        }, [exercise])
        payload = ai_training_summaries(self.connection, "2026-07-18")
        serialized = json.dumps(payload)
        self.assertEqual(len(payload), 1)
        self.assertNotIn("notes", serialized)
        self.assertNotIn("sets", serialized)
        self.assertNotIn("private", serialized)

    def test_dashboard_uses_service_layer_and_required_actions(self):
        source = (ROOT / "src" / "dashboard.py").read_text(encoding="utf-8")
        self.assertNotIn("connection.execute(", source)
        self.assertNotIn("st.data_editor", source)
        for token in (
            "ensure_polar_session_index", "save_training_details", "copy_set",
            "copy_exercise", "training_logging.copy_previous_set",
            "training_logging.add_exercise", "training_logging.complete_log",
        ):
            self.assertIn(token, source)

    def test_localization_contract(self):
        zh = json.loads((ROOT / "locales" / "zh-CN.json").read_text(encoding="utf-8"))
        en = json.loads((ROOT / "locales" / "en.json").read_text(encoding="utf-8"))
        self.assertEqual(zh["training_logging"]["title"], "训练数据")
        self.assertEqual(en["training_logging"]["title"], "Training Details")
        self.assertEqual(set(zh["training_logging"]), set(en["training_logging"]))


class StructuredTrainingLegacyMigrationTests(unittest.TestCase):
    def test_legacy_workout_and_sets_are_preserved_and_migrated(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = sqlite3.connect(Path(directory) / "legacy.db")
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(db.SCHEMA)
            for table_name, columns in db.MIGRATIONS.items():
                if not connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,),
                ).fetchone():
                    continue
                existing = {
                    row["name"] for row in connection.execute(
                        f"PRAGMA table_info({table_name})"
                    )
                }
                for column_name, column_type in columns.items():
                    if column_name not in existing:
                        connection.execute(
                            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                        )
            db.ensure_migration_ledger(connection)
            # Stop before the structured-training migration so the fixture
            # exercises the legacy workout/sets conversion path.
            for migration in db.SCHEMA_MIGRATIONS:
                if migration.sequence >= 14:
                    break
                if migration.sql:
                    connection.executescript(migration.sql)
                db.record_schema_migration(connection, migration)
            workout_id = connection.execute(
                """INSERT INTO workout_sessions(date,session_type,duration_minutes,notes)
                   VALUES('2026-07-17','strength',60,'legacy session')"""
            ).lastrowid
            connection.execute(
                """INSERT INTO exercise_sets(
                       workout_session_id,exercise_name,exercise_category,set_number,
                       reps,weight_kg,rpe,rest_seconds,notes
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (workout_id, "杠铃深蹲", "strength", 1, 8, 80, 8, 120, "legacy set"),
            )
            connection.commit()
            db.apply_migrations(connection); connection.commit()
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM workout_sessions").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM exercise_sets").fetchone()[0], 1)
            session = connection.execute(
                "SELECT * FROM training_sessions WHERE legacy_workout_session_id=?", (workout_id,)
            ).fetchone()
            self.assertIsNotNone(session)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM training_exercises WHERE training_session_id=?", (session["id"],)
            ).fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM training_sets").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            connection.close()


if __name__ == "__main__":
    unittest.main()
