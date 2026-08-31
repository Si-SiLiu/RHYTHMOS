import copy
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from src import ai_coach_provider
from tests.test_ai_coach_approval import approved_record
from tests.test_ai_coach_context import valid_source
from tests.test_ai_coach_contract import valid_output


NOW = datetime.fromisoformat("2030-06-01T00:00:00+00:00")
DIGEST_KEY = b"synthetic-provider-test-key-at-least-32-bytes"


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class AICoachProviderTests(unittest.TestCase):
    def test_blocked_approval_stops_before_network(self):
        post = mock.Mock()
        with self.assertRaises(ai_coach_provider.AIProviderError):
            ai_coach_provider.generate_coach_output(
                valid_source(), now=NOW, digest_key=DIGEST_KEY, post=post
            )
        post.assert_not_called()

    def test_approved_request_is_structured_and_validated(self):
        record = approved_record()
        output = valid_output()
        response = FakeResponse({
            "status": "completed",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(output)}],
            }],
        })
        post = mock.Mock(return_value=response)
        with tempfile.TemporaryDirectory() as directory:
            approval_path = Path(directory) / "approval.json"
            approval_path.write_text(json.dumps(record), encoding="utf-8")
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key-for-provider"}):
                result = ai_coach_provider.generate_coach_output(
                    valid_source(),
                    now=NOW,
                    digest_key=DIGEST_KEY,
                    approval_path=approval_path,
                    post=post,
                )

        self.assertEqual(result["audit"]["model_version"], record["model_snapshot"])
        self.assertEqual(len(result["audit"]["input_snapshot_digest"]), 64)
        post.assert_called_once()
        endpoint, = post.call_args.args
        self.assertEqual(endpoint, record["endpoint"])
        request = post.call_args.kwargs["json"]
        self.assertEqual(request["model"], record["model_snapshot"])
        self.assertFalse(request["store"])
        self.assertEqual(request["reasoning"], {"effort": "low"})
        self.assertEqual(request["text"]["format"]["type"], "json_schema")
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertNotIn("OPENAI_API_KEY", json.dumps(request))

    def test_invalid_model_output_fails_closed(self):
        record = approved_record()
        output = copy.deepcopy(valid_output())
        output["evidence"][0]["fact_id"] = "invented_metric"
        response = FakeResponse({"output_text": json.dumps(output)})
        with tempfile.TemporaryDirectory() as directory:
            approval_path = Path(directory) / "approval.json"
            approval_path.write_text(json.dumps(record), encoding="utf-8")
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key-for-provider"}):
                with self.assertRaises(ai_coach_provider.AIProviderError):
                    ai_coach_provider.generate_coach_output(
                        valid_source(),
                        now=NOW,
                        digest_key=DIGEST_KEY,
                        approval_path=approval_path,
                        post=mock.Mock(return_value=response),
                    )

    def test_missing_credentials_fail_without_network(self):
        record = approved_record()
        post = mock.Mock()
        with tempfile.TemporaryDirectory() as directory:
            approval_path = Path(directory) / "approval.json"
            approval_path.write_text(json.dumps(record), encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
                ai_coach_provider, "load_dotenv"
            ):
                with self.assertRaises(ai_coach_provider.AIProviderError):
                    ai_coach_provider.generate_coach_output(
                        valid_source(),
                        now=NOW,
                        digest_key=DIGEST_KEY,
                        approval_path=approval_path,
                        post=post,
                    )
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
