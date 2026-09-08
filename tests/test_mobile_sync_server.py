import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

from src.cloud_sync_store import CloudDocument
from src.mobile_sync_server import create_app
from src.secure_token_store import EncryptedTokenStore


class _Runner:
    def run(self, **kwargs):
        assert kwargs == {"if_new_data": True, "trigger_type": "scheduled"}
        return {"success": True, "run_id": "safe-run-id", "records_imported": 4, "access_token": "never-return"}


class _CloudStore:
    def __init__(self):
        self.documents = {}

    def load(self, account_id, document_type, document_key):
        return self.documents.get((account_id, document_type, document_key))

    def save(self, account_id, document_type, document_key, payload, source_device):
        key = (account_id, document_type, document_key)
        previous = self.documents.get(key)
        document = CloudDocument(
            account_id=account_id,
            document_type=document_type,
            document_key=document_key,
            revision=(previous.revision + 1) if previous else 1,
            payload=dict(payload),
            payload_sha256="a" * 64,
            source_device=source_device,
        )
        self.documents[key] = document
        return document


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
        self.nutrition_entry_saver = Mock(side_effect=lambda payload: {"date": payload["date"]})
        self.nutrition_label_parser = Mock(return_value={"basis": "per 100 g", "nutrients": {"protein": {"value": 3.2, "unit": "g"}}, "confidence": 0.9})
        self.nutrition_label_saver = Mock(return_value={"food_catalog_id": 7, "food_name": "测试食物"})
        self.nutrition_library_loader = Mock(return_value={"items": [{"id": 7, "food_name": "测试食物"}]})
        self.app = create_app(
            self.config,
            runner_factory=lambda: _Runner(),
            snapshot_builder=lambda **kwargs: self.snapshot,
            screenshot_importer=lambda payload: {"date": payload["date"]},
            morning_hrv_importer=lambda payload: {"date": payload["date"]},
            nutrition_entry_saver=self.nutrition_entry_saver,
            nutrition_label_parser=self.nutrition_label_parser,
            nutrition_label_saver=self.nutrition_label_saver,
            nutrition_library_loader=self.nutrition_library_loader,
            history_builder=lambda **kwargs: {
                "kind": "rhythmos.mobile_recovery_history",
                "version": 1,
                "days": [],
                "requested_days": kwargs["days"],
            },
            training_history_builder=lambda **kwargs: {
                "kind": "rhythmos.mobile_training_history",
                "version": 1,
                "days": [],
                "requested_days": kwargs["days"],
            },
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

    def test_manual_nutrition_entry_requires_auth_and_returns_refreshed_snapshot(self):
        payload = {"date": "2026-09-07", "food_name": "午餐", "calories_kcal": 620}
        self.assertEqual(self.client.post("/v1/mobile/nutrition-entry", json=payload).status_code, 401)

        response = self.client.post("/v1/mobile/nutrition-entry", headers=self.headers, json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), self.snapshot)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.nutrition_entry_saver.assert_called_once_with(payload)

    def test_food_label_parse_and_library_share_the_mobile_token_boundary(self):
        payload = {"raw_text": "每100g 蛋白质 3.2g"}
        self.assertEqual(self.client.post("/v1/mobile/nutrition-label/parse", json=payload).status_code, 401)
        parsed = self.client.post("/v1/mobile/nutrition-label/parse", headers=self.headers, json=payload)
        self.assertEqual(parsed.status_code, 200)
        self.assertEqual(parsed.get_json()["basis"], "per 100 g")
        self.assertEqual(parsed.headers["Cache-Control"], "no-store")
        self.nutrition_label_parser.assert_called_once_with(payload)

        library = self.client.get("/v1/mobile/nutrition-library/food", headers=self.headers)
        self.assertEqual(library.status_code, 200)
        self.assertEqual(library.get_json()["items"][0]["food_name"], "测试食物")

        saved = self.client.post("/v1/mobile/nutrition-library/food", headers=self.headers, json=payload)
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.get_json()["food_catalog_id"], 7)
        self.nutrition_label_saver.assert_called_once_with(payload)

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

    def test_history_is_token_protected_and_range_checked(self):
        response = self.client.get("/v1/mobile/recovery-history")
        self.assertEqual(response.status_code, 401)
        response = self.client.get("/v1/mobile/recovery-history?days=7", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["requested_days"], 7)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        response = self.client.get("/v1/mobile/recovery-history?days=bad", headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "INVALID_HISTORY_RANGE"})

    def test_training_history_is_token_protected_and_range_checked(self):
        response = self.client.get("/v1/mobile/training-history")
        self.assertEqual(response.status_code, 401)
        response = self.client.get("/v1/mobile/training-history?days=7", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["requested_days"], 7)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        response = self.client.get("/v1/mobile/training-history?days=bad", headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "INVALID_HISTORY_RANGE"})

    def test_cloud_document_push_and_pull_share_the_mobile_token_boundary(self):
        cloud = _CloudStore()
        app = create_app(self.config, cloud_store_factory=lambda settings: cloud)
        app.config["TESTING"] = True
        client = app.test_client()
        payload = {"payload": self.snapshot, "source_device": "macOS-test"}

        self.assertEqual(
            client.post("/v1/cloud/documents/daily_snapshot/2026-09-07", json=payload).status_code,
            401,
        )
        saved = client.post(
            "/v1/cloud/documents/daily_snapshot/2026-09-07", headers=self.headers, json=payload,
        )
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.get_json()["revision"], 1)
        pulled = client.get(
            "/v1/cloud/documents/daily_snapshot/2026-09-07", headers=self.headers,
        )
        self.assertEqual(pulled.status_code, 200)
        self.assertEqual(pulled.get_json()["payload"], self.snapshot)
        self.assertEqual(pulled.headers["Cache-Control"], "no-store")

    def test_reviewed_screenshot_values_are_imported_without_an_image_upload(self):
        payload = {
            "date": "2026-09-07", "rmssd": 42.5, "mean_hr": 57,
            "image_sha256": "a" * 64, "user_confirmed": True,
        }
        response = self.client.post("/v1/mobile/kubios-screenshot-import", headers=self.headers, json=payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), self.snapshot)

    def test_screenshot_endpoint_reports_a_safe_import_failure_or_non_json_input(self):
        response = self.client.post("/v1/mobile/kubios-screenshot-import", headers=self.headers, json={})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json(), {"error": "SCREENSHOT_IMPORT_FAILED"})
        response = self.client.post("/v1/mobile/kubios-screenshot-import", headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "INVALID_SCREENSHOT_PAYLOAD"})

    def test_reviewed_device_measurement_returns_a_fresh_snapshot(self):
        payload = {
            "date": "2026-09-07", "source_type": "ios_bluetooth_hrv",
            "measurement_sha256": "d" * 64, "user_confirmed": True,
        }
        response = self.client.post("/v1/mobile/morning-hrv-import", headers=self.headers, json=payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), self.snapshot)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_device_measurement_endpoint_rejects_non_json_input(self):
        response = self.client.post("/v1/mobile/morning-hrv-import", headers=self.headers)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "INVALID_DEVICE_MEASUREMENT_PAYLOAD"})


if __name__ == "__main__":
    unittest.main()
