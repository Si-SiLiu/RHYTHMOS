import re
import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


class AICoachDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = (BASE_DIR / "docs" / "AI_COACH.md").read_text(encoding="utf-8")
        cls.decisions = (BASE_DIR / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
        cls.roadmap = (BASE_DIR / "docs" / "ROADMAP.md").read_text(encoding="utf-8")

    def test_design_records_the_enabled_runtime(self):
        self.assertIn("runtime enabled with standard API retention", self.design)
        self.assertIn("model version: `gpt-5.4`", self.design.lower())
        self.assertIn("OpenAI's Responses API", self.design)

    def test_input_is_allowlisted_and_sensitive_sources_are_denied(self):
        self.assertIn("Minimum Necessary Input Allowlist", self.design)
        for term in ("token files", "raw JSON", "environment secrets", "OAuth credentials"):
            self.assertIn(term, self.design)
        self.assertIn("User text is untrusted data", self.design)

    def test_output_and_audit_contract_is_versioned(self):
        for field in (
            "summary", "evidence", "limitations", "suggested_actions",
            "questions_for_user", "safety_notice", "model_version",
            "prompt_version", "output_schema_version", "safety_policy_version",
            "input_snapshot_digest", "generated_at",
        ):
            self.assertIn(f"`{field}`", self.design)

    def test_confidence_and_medical_boundaries_are_defined(self):
        for level in ("`high`", "`medium`", "`low`", "`very_low`"):
            self.assertIn(level, self.design)
        self.assertRegex(self.design, r"must not diagnose")
        self.assertIn("seek immediate local emergency help", self.design)
        self.assertIn("deterministic fallback", self.design)

    def test_design_decisions_and_roadmap_status_are_consistent(self):
        for adr in ("ADR-020", "ADR-021", "ADR-022"):
            self.assertIn(adr, self.decisions)
        self.assertIn("Phase 12.0 — AI Coach Architecture & Safety Design — Completed", self.roadmap)
        self.assertIn("Phase 12.1 — AI Coach Implementation — Completed", self.roadmap)

    def test_design_contains_no_secret_like_assignment(self):
        self.assertIsNone(re.search(r"(?i)(access_token|refresh_token|client_secret)\s*[:=]\s*[^`\s]", self.design))


if __name__ == "__main__":
    unittest.main()
