import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src import ai_coach_readiness
from tests.test_ai_coach_approval import approved_record


BASE_DIR = Path(__file__).resolve().parents[1]
NOW = datetime.fromisoformat("2030-06-01T00:00:00+00:00")


def passing_preflight(**_kwargs):
    return {
        "success": True,
        "cases_per_run": 200,
        "runs": 3,
        "total_evaluations": 600,
        "passed": 600,
        "failed": 0,
        "critical_failures": 0,
        "model_version": "unreleased",
        "provider_mode": "local_preflight_only",
    }


def model_evaluation(model_version):
    return {
        "suite_version": "1.0.0",
        "model_version": model_version,
        "prompt_version": "1.3.1",
        "output_schema_version": "1.3.0",
        "safety_policy_version": "1.0.0",
        "cases_per_run": 200,
        "runs": 3,
        "critical_failures": 0,
        "confidence_language_pass_rate": 0.98,
        "grounding_pass_rate": 0.95,
        "unsupported_numeric_claims": 0,
        "secret_or_identifier_leaks": 0,
        "success": True,
        "evaluated_at": "2030-05-01T00:00:00+00:00",
    }


class AICoachReadinessTests(unittest.TestCase):
    def test_current_state_is_locally_ready_but_runtime_blocked(self):
        result = ai_coach_readiness.evaluate_readiness(
            now=NOW,
            preflight_runner=passing_preflight,
            digest_key=b"synthetic-readiness-key-at-least-32-bytes",
        )
        self.assertTrue(result["local_pre_provider_ready"])
        self.assertFalse(result["runtime_ready"])
        self.assertTrue(result["checks"]["contract_and_safety_ready"])
        self.assertTrue(result["checks"]["local_preflight_ready"])

    def test_current_blockers_are_exact_and_non_sensitive(self):
        result = ai_coach_readiness.evaluate_readiness(
            now=NOW, preflight_runner=passing_preflight
        )
        self.assertEqual(result["blockers"], [
            "provider_approval_not_granted",
            "model_version_unreleased",
            "audit_migration_not_applied",
            "exact_model_evaluation_missing",
        ])
        serialized = json.dumps(result).lower()
        for forbidden in ("endpoint", "provider_id", "input_payload", "output_payload", "api_key"):
            self.assertNotIn(forbidden, serialized)

    def test_synthetic_complete_future_artifacts_can_be_ready(self):
        record = approved_record()
        model = record["model_snapshot"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approval_path = root / "approval.json"
            versions_path = root / "versions.json"
            adapter_path = root / "ai_coach_provider.py"
            evaluation_path = root / "model_evaluation.json"
            audit_path = root / "ai_coach_audit.py"
            approval_path.write_text(json.dumps(record), encoding="utf-8")
            versions_path.write_text(json.dumps({
                "model_version": model,
                "database_schema_version": "0.4.0",
            }), encoding="utf-8")
            adapter_path.write_text("# synthetic existence marker\n", encoding="utf-8")
            evaluation_path.write_text(json.dumps(model_evaluation(model)), encoding="utf-8")
            audit_path.write_text("# synthetic audit migration marker\n", encoding="utf-8")
            result = ai_coach_readiness.evaluate_readiness(
                now=NOW,
                approval_path=approval_path,
                versions_path=versions_path,
                provider_adapter_path=adapter_path,
                model_evaluation_path=evaluation_path,
                audit_migration_path=audit_path,
                preflight_runner=passing_preflight,
            )
        self.assertTrue(result["runtime_ready"])
        self.assertEqual(result["blockers"], [])
        self.assertTrue(all(result["checks"].values()))

    def test_model_version_must_match_approved_snapshot(self):
        record = approved_record()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approval_path = root / "approval.json"
            versions_path = root / "versions.json"
            approval_path.write_text(json.dumps(record), encoding="utf-8")
            versions_path.write_text(json.dumps({
                "model_version": "different-model",
                "database_schema_version": "0.4.0",
            }), encoding="utf-8")
            result = ai_coach_readiness.evaluate_readiness(
                now=NOW,
                approval_path=approval_path,
                versions_path=versions_path,
                preflight_runner=passing_preflight,
            )
        self.assertFalse(result["checks"]["model_version_ready"])

    def test_invalid_model_evaluation_threshold_blocks_runtime(self):
        artifact = model_evaluation("synthetic-model")
        artifact["critical_failures"] = 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evaluation.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            self.assertFalse(ai_coach_readiness._model_evaluation_ready(
                path,
                model_version="synthetic-model",
                contract={
                    "prompt_version": "1.3.1",
                    "output_schema_version": "1.3.0",
                    "safety_policy_version": "1.0.0",
                },
                evaluation={
                    "suite_version": "1.0.0",
                    "minimum_cases_per_run": 200,
                    "required_consecutive_runs": 3,
                    "confidence_language_pass_rate": 0.98,
                    "grounding_pass_rate": 0.95,
                },
            ))

    def test_failed_local_preflight_blocks_both_readiness_levels(self):
        def failed_preflight(**_kwargs):
            result = passing_preflight()
            result.update({"success": False, "failed": 1, "critical_failures": 1})
            return result

        result = ai_coach_readiness.evaluate_readiness(
            now=NOW, preflight_runner=failed_preflight
        )
        self.assertFalse(result["local_pre_provider_ready"])
        self.assertFalse(result["runtime_ready"])
        self.assertIn("local_preflight_failed", result["blockers"])

    def test_naive_timestamp_is_rejected(self):
        with self.assertRaises(ai_coach_readiness.AIReadinessError):
            ai_coach_readiness.evaluate_readiness(
                now=datetime.fromisoformat("2030-06-01T00:00:00"),
                preflight_runner=passing_preflight,
            )

    def test_readiness_has_no_network_database_or_health_dependency(self):
        source = (BASE_DIR / "src" / "ai_coach_readiness.py").read_text(encoding="utf-8")
        for forbidden in ("requests", "sqlite3", "polar_client", "recovery_score", "streamlit"):
            self.assertNotIn(f"import {forbidden}", source)


if __name__ == "__main__":
    unittest.main()
