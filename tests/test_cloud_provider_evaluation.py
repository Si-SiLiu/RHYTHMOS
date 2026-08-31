import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


class CloudProviderEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = (BASE_DIR / "docs" / "CLOUD_PROVIDER_EVALUATION.md").read_text(encoding="utf-8")

    def test_historical_zdr_selection_is_recorded_without_weakening_gates(self):
        self.assertIn("Historical ZDR evaluation", self.document)
        self.assertIn("Missing public evidence is a failed gate", self.document)
        self.assertIn("model version: `gpt-5.4`", self.document.lower())

    def test_candidates_have_explicit_results(self):
        for candidate in ("OpenAI API", "Alibaba Cloud Model Studio", "Baidu Qianfan", "Tencent Hunyuan/TokenHub"):
            self.assertIn(candidate, self.document)
        self.assertIn("Fails the approved ZDR gate", self.document)

    def test_conditional_configuration_is_replayable_and_stateless(self):
        self.assertIn("`gpt-5.4-mini-2026-03-17`", self.document)
        self.assertIn("`POST /v1/responses`", self.document)
        self.assertIn("`store=false`", self.document)
        self.assertIn("no background mode", self.document)
        self.assertIn("conditional, not approved", self.document)

    def test_unblocking_paths_and_prohibited_workarounds_are_explicit(self):
        for heading in ("Path A", "Path B", "Path C", "Prohibited Workarounds"):
            self.assertIn(heading, self.document)
        for term in ("VPN", "proxy", "borrowed account"):
            self.assertIn(term, self.document)

    def test_primary_source_links_are_recorded(self):
        for domain in ("help.openai.com", "developers.openai.com", "help.aliyun.com", "cloud.baidu.com", "cloud.tencent.com"):
            self.assertIn(domain, self.document)

    def test_no_runtime_secret_or_key_is_present(self):
        self.assertNotIn("sk-", self.document)
        self.assertNotIn("Bearer ", self.document)


if __name__ == "__main__":
    unittest.main()
