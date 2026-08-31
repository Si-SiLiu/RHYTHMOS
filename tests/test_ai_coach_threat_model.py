import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


class AICoachThreatModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = (BASE_DIR / "docs" / "AI_COACH_THREAT_MODEL.md").read_text(encoding="utf-8")

    def test_all_threat_ids_are_present(self):
        for number in range(1, 19):
            self.assertIn(f"`TM-{number:02d}`", self.document)

    def test_trust_boundaries_cover_full_path(self):
        for number in range(1, 8):
            self.assertIn(f"`TB-{number}`", self.document)
        self.assertIn("untrusted-output boundary", self.document)

    def test_critical_controls_fail_closed(self):
        for phrase in ("redirects disabled", "exact HTTPS origin allowlist", "kill switch default off", "exception-to-fallback", "additionalProperties=false"):
            self.assertIn(phrase, self.document)
        self.assertIn("No Critical or High residual", self.document)

    def test_privacy_and_retention_properties_are_explicit(self):
        for property_name in ("Data minimization", "Purpose limitation", "Unlinkability", "Transparency", "Intervenability", "Retention limitation", "Integrity"):
            self.assertIn(f"**{property_name}:**", self.document)
        self.assertIn("standard API retention is disclosed", self.document)
        self.assertIn("stored per day", self.document)

    def test_incident_response_preserves_deterministic_service(self):
        self.assertIn("rotate provider credential", self.document)
        self.assertIn("deterministic features remain available", self.document)
        self.assertIn("hash-identical", self.document)

    def test_design_records_the_approved_runtime_boundary(self):
        self.assertIn("standard-retention runtime enabled", self.document)
        self.assertIn("`gpt-5.4`", self.document)
        self.assertIn("minimum-necessary", self.document)


if __name__ == "__main__":
    unittest.main()
