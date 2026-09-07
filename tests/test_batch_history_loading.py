"""Batch history reads preserve single-record semantics without N+1 queries."""

import sqlite3
import unittest

from src import db
from src.nutrition_logging import simple_storage as meals
from src.training_logging import storage as training
from src.training_logging.catalog import list_exercise_catalog


class BatchHistoryLoadingTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        db.init_db(self.connection)
        self.addCleanup(self.connection.close)

    def test_meals_match_single_reads_with_supplements_and_legacy_names(self):
        c = self.connection
        for name in ('燕麦', 'unidentified food'):
            meals.create_meal_record(c, {
                'date': '2026-01-01', 'meal_type': 'breakfast', 'eaten_at': '08:00',
            }, [{'custom_food_name': name, 'quantity': 50, 'unit': 'g'}], [{
                'custom_product_name': 'Test supplement', 'quantity': 1, 'unit': 'capsule',
            }])
        c.execute("UPDATE meal_items SET deleted_at='deleted' WHERE id=(SELECT MAX(id) FROM meal_items)")
        c.execute("UPDATE supplement_intake_records SET deleted_at='deleted' WHERE id=(SELECT MAX(id) FROM supplement_intake_records)")
        # Force multiple bounded batches, with detailed records in the last one.
        c.executemany(
            "INSERT INTO meal_records(uuid,date,meal_type,eaten_at,status,source) "
            "VALUES(?,'2026-01-02','lunch','12:00','draft','manual')",
            [(f'empty-{i}',) for i in range(405)],
        )
        c.commit()
        queries = []
        c.set_trace_callback(queries.append)
        actual = meals.list_meal_records(c, limit=500)
        c.set_trace_callback(None)
        self.assertEqual(len(actual), 407)
        self.assertLessEqual(len(queries), 7)
        self.assertEqual(actual, [meals.get_meal_record(c, row['id']) for row in actual])
        self.assertEqual(meals.list_meal_records(c, limit=1), actual[:1])
        c.execute("UPDATE meal_records SET deleted_at='deleted' WHERE id=?", (actual[0]['id'],))
        self.assertNotIn(actual[0]['id'], [r['id'] for r in meals.list_meal_records(c, 500)])

    def test_training_matches_single_reads_and_sees_source_updates(self):
        c = self.connection
        session_id = training.create_manual_training_session(c, {
            'date': '2026-01-01', 'resolved_sport_type': 'strength',
        })
        squat = next(item for item in list_exercise_catalog(c) if item['canonical_name'] == 'barbell_back_squat')
        training.save_training_details(c, session_id, {}, [{
            'exercise_catalog_id': squat['id'],
            'sets': [{'load_value': 50, 'load_unit': 'kg', 'reps': 8},
                     {'load_value': 60, 'load_unit': 'kg', 'reps': 6}],
        }])
        c.execute("UPDATE training_sets SET deleted_at='deleted' WHERE id=(SELECT MAX(id) FROM training_sets)")
        c.execute("INSERT INTO polar_training_sessions_raw(source,external_id,date,raw_json,sport,calories) VALUES('polar','test','2026-01-02','{}','15',100)")
        training.ensure_polar_session_index(c)
        c.executemany(
            "INSERT INTO training_sessions(uuid,date,source,resolved_sport_type_source) "
            "VALUES(?,'2026-01-03','manual','manual')", [(f'empty-{i}',) for i in range(405)],
        )
        c.commit()
        queries = []
        c.set_trace_callback(queries.append)
        actual = training.list_training_sessions(c, 500)
        c.set_trace_callback(None)
        self.assertEqual(len(actual), 407)
        self.assertLessEqual(len(queries), 8)
        self.assertEqual(actual, [training.get_training_session(c, r['id']) for r in actual])
        c.execute("UPDATE polar_training_sessions_raw SET calories=222 WHERE external_id='test'")
        refreshed = training.list_training_sessions(c, 500)
        self.assertEqual(next(r for r in refreshed if r['polar_external_id'] == 'test')['calories'], 222)
        self.assertEqual(training.list_training_sessions(c, 1), refreshed[:1])

    def test_empty_lists_and_limits(self):
        self.assertEqual(meals.list_meal_records(self.connection), [])
        self.assertEqual(training.list_training_sessions(self.connection), [])
        with self.assertRaises(ValueError):
            meals.list_meal_records(self.connection, 0)
        self.assertEqual(training.list_training_sessions(self.connection, 0), [])


if __name__ == '__main__':
    unittest.main()
