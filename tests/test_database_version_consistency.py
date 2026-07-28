import json
import unittest
from pathlib import Path

from src.db import SCHEMA_MIGRATIONS


class DatabaseVersionConsistencyTests(unittest.TestCase):
    def test_versions_json_matches_latest_schema_migration(self):
        root = Path(__file__).parents[1]
        versions = json.loads((root / "config" / "versions.json").read_text(encoding="utf-8"))
        self.assertEqual(versions["database_schema_version"], SCHEMA_MIGRATIONS[-1].version)


if __name__ == "__main__":
    unittest.main()
