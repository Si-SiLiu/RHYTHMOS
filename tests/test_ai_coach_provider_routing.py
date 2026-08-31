import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from src import ai_coach_provider
from src.ai_coach_provider_routing import ProviderRoute, ProviderRouteTable, ProviderRoutingError
from tests.test_ai_coach_approval import approved_record
from tests.test_ai_coach_context import valid_source
from tests.test_ai_coach_provider import FakeResponse
from tests.test_ai_coach_contract import valid_output


NOW = datetime.fromisoformat("2030-06-01T00:00:00+00:00")
DIGEST_KEY = b"synthetic-provider-routing-key-at-least-32-bytes"


def route_for(path: Path, *, provider_id: str = "openai") -> ProviderRoute:
    return ProviderRoute(
        jurisdiction="supported-region",
        provider_id=provider_id,
        processing_region="supported-region",
        approval_path=path,
        credential_env="OPENAI_API_KEY",
    )


class AICoachProviderRoutingTests(unittest.TestCase):
    def test_routes_resolve_case_insensitively_but_without_wildcard(self):
        route = route_for(Path("/tmp/approval.json"))
        table = ProviderRouteTable([route])
        self.assertEqual(table.resolve(" Supported-Region "), route)
        with self.assertRaises(ProviderRoutingError):
            table.resolve("another-region")

    def test_wildcard_and_duplicate_routes_are_rejected(self):
        route = route_for(Path("/tmp/approval.json"))
        with self.assertRaises(ProviderRoutingError):
            ProviderRouteTable(
                [
                    ProviderRoute(
                        jurisdiction="*",
                        provider_id="openai",
                        processing_region="supported-region",
                        approval_path=Path("/tmp/a.json"),
                        credential_env="OPENAI_API_KEY",
                    )
                ]
            )
        with self.assertRaises(ProviderRoutingError):
            ProviderRouteTable([route, route])

    def test_mapping_requires_exact_route_fields(self):
        with self.assertRaises(ProviderRoutingError):
            ProviderRouteTable.from_mapping({"region": {"provider_id": "openai"}})

    def test_runtime_requires_explicit_jurisdiction_when_route_table_is_supplied(self):
        post = mock.Mock()
        table = ProviderRouteTable([route_for(Path("/tmp/approval.json"))])
        with self.assertRaises(ai_coach_provider.AIProviderError):
            ai_coach_provider.generate_coach_output(
                valid_source(),
                now=NOW,
                digest_key=DIGEST_KEY,
                route_table=table,
                post=post,
            )
        post.assert_not_called()

    def test_route_and_approval_provider_must_match_before_network(self):
        record = approved_record()
        with tempfile.TemporaryDirectory() as directory:
            approval_path = Path(directory) / "approval.json"
            approval_path.write_text(json.dumps(record), encoding="utf-8")
            table = ProviderRouteTable(
                [route_for(approval_path, provider_id="other-provider")]
            )
            post = mock.Mock()
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key-for-routing"}):
                with self.assertRaises(ai_coach_provider.AIProviderError):
                    ai_coach_provider.generate_coach_output(
                        valid_source(),
                        now=NOW,
                        digest_key=DIGEST_KEY,
                        jurisdiction="supported-region",
                        route_table=table,
                        post=post,
                    )
            post.assert_not_called()

    def test_explicit_route_can_select_an_approved_adapter(self):
        record = approved_record()
        response = FakeResponse({"output_text": json.dumps(valid_output())})
        with tempfile.TemporaryDirectory() as directory:
            approval_path = Path(directory) / "approval.json"
            approval_path.write_text(json.dumps(record), encoding="utf-8")
            table = ProviderRouteTable([route_for(approval_path)])
            post = mock.Mock(return_value=response)
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key-for-routing"}):
                result = ai_coach_provider.generate_coach_output(
                    valid_source(),
                    now=NOW,
                    digest_key=DIGEST_KEY,
                    jurisdiction="supported-region",
                    route_table=table,
                    post=post,
                )
        self.assertEqual(result["audit"]["model_version"], record["model_snapshot"])
        post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
