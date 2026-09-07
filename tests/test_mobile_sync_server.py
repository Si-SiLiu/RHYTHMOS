import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

from src.mobile_sync_server import create_app
from src.secure_token_store import EncryptedTokenStore


class _Runner:
    def run(self, **kwargs):
        assert kwargs == {"if_new_data": True, "trigger_type": "scheduled"}
        return {"success": True, "run_id": "safe-run-id", "records_imported": 4, "access_token": "never-return"}


class MobileSyncServerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.token_file = str(Path(self.directory.name) / "polar_tokens.enc")
        self.encryption_key = Fernet.generate_key().decode("utf-8")
        self.config = {
            "POLAR_CLIENT_ID": "client-id",
            "POLAR_CLIENT_SECRET": "client-secret",
            "POLAR_REDIRECT_URI": "https://sync.example.test/oauth2_callback",
            "POLAR_TOKEN_ENCRYPTION_KEY": self.encryption_key,
            "MOBILE_SYNC_API_TOKEN": "mobile-api-token",
            "POLAR_CONNECT_USERNAME": "owner",
            "POLAR_CONNECT_PASSWORD": "connect-password",
            "FLASK_SECRET_KEY": "flask-test-key",
            "POLAR_TOKEN_FILE": self.token_file,
        }
        self.snapshot = {
            "kind": "rhythmos.mobile_daily_snapshot",
            "version": 1,
            "date": "2026-09-07",
        }
        self.app = create_app(
            self.config,
            runner_factory=lambda: _Runner(),
            snapshot_builder=lambda **kwargs: self.snapshot,
        )
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.headers = {"Authorization": "Bearer mobile-api-token"}

    def tearDown(self):
        self.directory.cleanup()

    def test_health_is_public_but_mobile_data_requires_bearer_token(self):
        self.assertEqual(self.client.get("/healthz").get_json(), {"status": "ok"})
        response = self.client.get("/v1/mobile/daily-snapshot")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "UNAUTHORIZED"})

    def test_snapshot_is_read_only_and_not_cached(self):
        response = self.client.get("/v1/mobile/daily-snapshot?date=2026-09-07", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), self.snapshot)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_sync_returns_only_safe_summary(self):
        response = self.client.post("/v1/mobile/sync", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"success": True, "run_id": "safe-run-id", "records_imported": 4})

    def test_connect_requires_basic_auth_and_never_puts_secret_in_authorization_url(self):
        unauthorized = self.client.get("/connect/polar")
        self.assertEqual(unauthorized.status_code, 401)
        self.assertIn("Basic", unauthorized.headers["WWW-Authenticate"])

        response = self.client.get("/connect/polar", auth=("owner", "connect-password"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("client-secret", response.location)
        query = parse_qs(urlparse(response.location).query)
        self.assertEqual(query["client_id"], ["client-id"])
        self.assertEqual(query["redirect_uri"], ["https://sync.example.test/oauth2_callback"])
        self.assertTrue(query["state"])

    def test_callback_encrypts_tokens_and_returns_no_token_data(self):
        token_response = Mock(status_code=200)
        token_response.json.return_value = {
            "access_token": "sensitive-access-token",
            "refresh_token": "sensitive-refresh-token",
            "expires_in": 3600,
        }
        registration_response = Mock(status_code=201)
        http_post = Mock(side_effect=[token_response, registration_response])
        app = create_app(
            self.config,
            http_post=http_post,
        )
        app.config["TESTING"] = True
        client = app.test_client()
        connect = client.get("/connect/polar", auth=("owner", "connect-password"))
        state = parse_qs(urlparse(connect.location).query)["state"][0]

        response = client.get(f"/oauth2_callback?code=authorization-code&state={state}")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("sensitive-access-token", response.get_data(as_text=True))
        self.assertNotIn(b"sensitive-access-token", Path(self.token_file).read_bytes())
        saved = EncryptedTokenStore(self.token_file, self.encryption_key).load()
        self.assertEqual(saved["access_token"], "sensitive-access-token")
        self.assertEqual(http_post.call_count, 2)
        self.assertEqual(http_post.call_args_list[1].args[0], "https://www.polaraccesslink.com/v3/users")
        self.assertEqual(
            http_post.call_args_list[1].kwargs["headers"]["Authorization"],
            "Bearer sensitive-access-token",
        )

    def test_invalid_snapshot_date_is_rejected(self):
        response = self.client.get("/v1/mobile/daily-snapshot?date=not-a-date", headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "INVALID_DATE"})


if __name__ == "__main__":
    unittest.main()
