import copy
import json
import unittest
from pathlib import Path

from src import ai_coach_contract


BASE_DIR = Path(__file__).resolve().parents[1]


def valid_input():
    return {
        "analysis_date": "2026-07-08",
        "recovery": {
            "score": 72,
            "recommendation": "保持适度活动并关注睡眠。",
            "score_version": "1.0.0",
            "factors": [
                {
                    "metric_name": "sleep",
                    "direction": "supportive",
                    "status": "above",
                    "deviation_band": "small",
                }
            ],
        },
        "confidence": {
            "score": 84,
            "level": "high",
            "confidence_version": "1.0.0",
            "available_groups": ["sleep", "hrv"],
            "missing_groups": [],
        },
        "daily_metrics": {
            "sleep_duration_band": "typical",
            "hrv_band": "high",
            "training_count_band": "single",
        },
        "nutrition": {"recording_band": "complete", "coverage_band": "adequate"},
        "baseline_context": [
            {
                "metric_name": "sleep",
                "comparison_status": "above",
                "maturity_band": "mature",
                "deviation_band": "small",
            }
        ],
        "presentation": {"locale": "zh-CN", "unit_system": "metric"},
        "contract_versions": {
            "prompt_version": "1.3.1",
            "output_schema_version": "1.3.0",
            "safety_policy_version": "1.0.0",
        },
    }


def valid_output():
    return {
        "summary": "恢复状态稳定，证据完整度较高。",
        "domain_feedback": [
            {"domain": "sleep", "status": "positive", "commentary": "睡眠信号稳定。", "suggestion": "保持规律作息。"},
            {"domain": "recovery", "status": "positive", "commentary": "恢复信号稳定。", "suggestion": "按当前节奏安排。"},
            {"domain": "training", "status": "neutral", "commentary": "训练负荷适中。", "suggestion": "根据体感调整。"},
            {"domain": "nutrition", "status": "neutral", "commentary": "营养记录完整。", "suggestion": "保持记录。"},
        ],
        "evidence": [{"fact_id": "sleep_status", "statement": "睡眠处于个人典型范围以上。"}],
        "limitations": [],
        "suggested_actions": [
            {
                "title": "保持适度活动",
                "rationale": "当前确定性结果支持正常恢复安排。",
                "reversibility": "easy",
            }
        ],
        "questions_for_user": [],
        "safety_notice": "这不是医疗诊断。",
        "audit": {
            "model_version": "provider-model-snapshot",
            "prompt_version": "1.3.1",
            "output_schema_version": "1.3.0",
            "safety_policy_version": "1.0.0",
            "input_snapshot_digest": "a" * 64,
            "generated_at": "2026-07-11T10:00:00+08:00",
            "provider_mode": "cloud_standard_retention",
        },
    }


class AICoachContractTests(unittest.TestCase):
    def test_contract_versions_and_schema_files_are_valid(self):
        contract = ai_coach_contract.load_contract()
        self.assertEqual(contract["prompt_version"], "1.3.1")
        self.assertEqual(contract["output_schema_version"], "1.3.0")
        self.assertEqual(contract["safety_policy_version"], "1.0.0")
        for key in ("input_schema", "output_schema"):
            schema = json.loads((BASE_DIR / "config" / contract[key]).read_text(encoding="utf-8"))
            self.assertFalse(schema["additionalProperties"])

    def test_valid_input_is_accepted_and_copied(self):
        payload = valid_input()
        result = ai_coach_contract.validate_input(payload)
        self.assertEqual(result, payload)
        self.assertIsNot(result, payload)

    def test_input_rejects_unknown_nested_and_out_of_range_fields(self):
        for mutate in (
            lambda value: value.update({"raw_json": {}}),
            lambda value: value["recovery"].update({"score": 101}),
            lambda value: value["daily_metrics"].update({"exact_hrv": 58.2}),
        ):
            payload = valid_input()
            mutate(payload)
            with self.assertRaises(ai_coach_contract.AIContractError):
                ai_coach_contract.validate_input(payload)

    def test_input_rejects_sensitive_user_question(self):
        for question in ("联系我 test@example.com", "电话 138 0013 8000", "api_key: forbidden"):
            payload = valid_input()
            payload["user_question"] = question
            with self.assertRaises(ai_coach_contract.AIContractError):
                ai_coach_contract.validate_input(payload)

    def test_input_rejects_contract_version_drift(self):
        payload = valid_input()
        payload["contract_versions"]["prompt_version"] = "1.0.1"
        with self.assertRaises(ai_coach_contract.AIContractError):
            ai_coach_contract.validate_input(payload)

    def test_valid_output_is_accepted_and_copied(self):
        payload = valid_output()
        result = ai_coach_contract.validate_output(payload)
        self.assertEqual(result, payload)
        self.assertIsNot(result, payload)

    def test_output_rejects_unknown_fields_html_and_urls(self):
        payload = valid_output()
        payload["debug"] = "hidden"
        with self.assertRaises(ai_coach_contract.AIContractError):
            ai_coach_contract.validate_output(payload)

        for unsafe in ("<script>alert(1)</script>", "访问 https://example.com"):
            payload = valid_output()
            payload["summary"] = unsafe
            with self.assertRaises(ai_coach_contract.AIContractError):
                ai_coach_contract.validate_output(payload)

    def test_output_rejects_bad_digest_timestamp_and_version(self):
        for key, value in (
            ("input_snapshot_digest", "short"),
            ("generated_at", "2026-07-11"),
            ("safety_policy_version", "2.0.0"),
        ):
            payload = valid_output()
            payload["audit"][key] = value
            with self.assertRaises(ai_coach_contract.AIContractError):
                ai_coach_contract.validate_output(payload)

    def test_validation_errors_do_not_include_payload_values(self):
        payload = valid_input()
        payload["user_question"] = "api_key: SUPER_SECRET_VALUE"
        try:
            ai_coach_contract.validate_input(payload)
        except ai_coach_contract.AIContractError as exc:
            self.assertNotIn("SUPER_SECRET_VALUE", str(exc))
        else:
            self.fail("Sensitive value was not rejected")

    def test_validator_has_no_network_or_database_dependency(self):
        source = (BASE_DIR / "src" / "ai_coach_contract.py").read_text(encoding="utf-8")
        for forbidden in ("requests", "sqlite3", "polar_client", "recovery_score", "streamlit"):
            self.assertNotIn(f"import {forbidden}", source)


if __name__ == "__main__":
    unittest.main()
