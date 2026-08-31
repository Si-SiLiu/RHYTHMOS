import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from src import ai_coach_context
from src.ai_coach_approval import AIApprovalError
from tests.test_ai_coach_approval import approved_record
from tests.test_ai_coach_contract import valid_input


BASE_DIR = Path(__file__).resolve().parents[1]
NOW = datetime.fromisoformat("2030-06-01T00:00:00+00:00")


def valid_source():
    source = valid_input()
    source.pop("contract_versions")
    return source


class AICoachContextTests(unittest.TestCase):
    def test_valid_source_builds_closed_context_and_versions(self):
        source = valid_source()
        result = ai_coach_context.build_context(source)
        self.assertEqual(result["contract_versions"], {
            "prompt_version": "1.3.0",
            "output_schema_version": "1.3.0",
            "safety_policy_version": "1.0.0",
        })
        self.assertEqual(
            set(result),
            ai_coach_context.REQUIRED_SOURCE_FIELDS | {"contract_versions"},
        )

    def test_builder_does_not_mutate_or_alias_source(self):
        source = valid_source()
        original = copy.deepcopy(source)
        result = ai_coach_context.build_context(source)
        result["recovery"]["score"] = 0
        self.assertEqual(source, original)
        self.assertNotEqual(source["recovery"]["score"], result["recovery"]["score"])

    def test_unknown_root_and_caller_versions_are_rejected(self):
        for key, value in (("raw_json", {}), ("contract_versions", {}), ("token", "forbidden")):
            source = valid_source()
            source[key] = value
            with self.assertRaises(ai_coach_context.AIContextError):
                ai_coach_context.build_context(source)

    def test_unknown_nested_and_exact_metrics_are_rejected(self):
        for key, value in (("exact_hrv", 55.2), ("sleep_duration_minutes", 480)):
            source = valid_source()
            source["daily_metrics"][key] = value
            with self.assertRaises(ai_coach_context.AIContextError):
                ai_coach_context.build_context(source)

    def test_missing_required_source_field_is_rejected(self):
        source = valid_source()
        source.pop("confidence")
        with self.assertRaises(ai_coach_context.AIContextError):
            ai_coach_context.build_context(source)

    def test_sensitive_question_is_rejected_not_redacted(self):
        for question in ("邮箱 test@example.com", "电话 138 0013 8000", "api_key: forbidden"):
            source = valid_source()
            source["user_question"] = question
            with self.assertRaises(ai_coach_context.AIContextError):
                ai_coach_context.build_context(source)

    def test_committed_blocked_approval_stops_before_context_build(self):
        with mock.patch("src.ai_coach_context.build_context") as builder:
            with self.assertRaises(AIApprovalError):
                ai_coach_context.build_approved_context(valid_source(), now=NOW)
            builder.assert_not_called()

    def test_synthetic_complete_approval_allows_context_build(self):
        record = approved_record()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "approval.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            result = ai_coach_context.build_approved_context(
                valid_source(), now=NOW, approval_path=path
            )
        self.assertEqual(result["analysis_date"], "2026-07-08")

    def test_error_does_not_echo_rejected_value(self):
        source = valid_source()
        source["user_question"] = "api_key: SUPER_SECRET_VALUE"
        try:
            ai_coach_context.build_context(source)
        except ai_coach_context.AIContextError as exc:
            self.assertEqual(str(exc), "AI context source is not allowed")
            self.assertNotIn("SUPER_SECRET_VALUE", str(exc))
        else:
            self.fail("Sensitive context was not rejected")

    def test_context_builder_has_no_network_database_or_engine_dependency(self):
        source = (BASE_DIR / "src" / "ai_coach_context.py").read_text(encoding="utf-8")
        for forbidden in ("requests", "sqlite3", "polar_client", "recovery_score", "streamlit"):
            self.assertNotIn(f"import {forbidden}", source)


if __name__ == "__main__":
    unittest.main()
