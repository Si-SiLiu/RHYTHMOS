import json
import unittest

from src.ai_coach_provider_adapters import (
    OpenAIResponsesAdapter,
    ProviderAdapterError,
    get_provider_adapter,
    register_provider_adapter,
)


class AICoachProviderAdapterTests(unittest.TestCase):
    def test_openai_adapter_is_explicitly_registered(self):
        adapter = get_provider_adapter("openai")
        self.assertIsInstance(adapter, OpenAIResponsesAdapter)
        self.assertEqual(adapter.credential_env, "OPENAI_API_KEY")

    def test_unknown_provider_does_not_fallback(self):
        with self.assertRaises(ProviderAdapterError):
            get_provider_adapter("unknown-provider")

    def test_openai_adapter_uses_strict_structured_output(self):
        adapter = get_provider_adapter("openai")
        request = adapter.build_request(
            {"safe": "context"},
            model="model-snapshot",
            system_prompt="system",
            output_schema={"type": "object"},
        )
        self.assertFalse(request["store"])
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertEqual(
            json.loads(request["input"][1]["content"][0]["text"]),
            {"safe": "context"},
        )

    def test_new_adapter_must_match_its_provider_id(self):
        class WrongIdAdapter:
            provider_id = "different"
            credential_env = "TEST_PROVIDER_KEY"

        with self.assertRaises(ProviderAdapterError):
            register_provider_adapter("registered", WrongIdAdapter())

    def test_registered_adapter_cannot_replace_existing_adapter(self):
        class DuplicateAdapter:
            provider_id = "openai"
            credential_env = "OTHER_KEY"

        with self.assertRaises(ProviderAdapterError):
            register_provider_adapter("openai", DuplicateAdapter())


if __name__ == "__main__":
    unittest.main()
