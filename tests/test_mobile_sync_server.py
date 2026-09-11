import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

from src.cloud_sync_store import CloudDocument
from src.mobile_sync_server import create_app
from src.cloud_sync_store import CloudSyncError
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
        self.nutrition_plan_entry_saver = Mock(side_effect=lambda payload: {"date": payload["week_start"]})
        self.nutrition_plan_cycle_saver = Mock(return_value={"date": "2026-09-07"})
        self.nutrition_history_builder = Mock(return_value={"kind": "rhythmos.mobile_nutrition_history", "version": 1, "days": []})
        self.nutrition_label_parser = Mock(return_value={"basis": "per 100 g", "nutrients": {"protein": {"value": 3.2, "unit": "g"}}, "confidence": 0.9})
        self.nutrition_label_saver = Mock(return_value={"food_catalog_id": 7, "food_name": "测试食物"})
        self.nutrition_library_loader = Mock(return_value={"items": [{"id": 7, "food_name": "测试食物"}]})
        self.personal_profile_saver = Mock(return_value={"date": "2026-09-07"})
        self.body_measurement_saver = Mock(return_value={"date": "2026-09-07"})
        self.app = create_app(
            self.config,
            runner_factory=lambda: _Runner(),
            snapshot_builder=lambda **kwargs: self.snapshot,
            screenshot_importer=lambda payload: {"date": payload["date"]},
            morning_hrv_importer=lambda payload: {"date": payload["date"]},
            nutrition_entry_saver=self.nutrition_entry_saver,
            nutrition_plan_cycle_saver=self.nutrition_plan_cycle_saver,
            nutrition_plan_entry_saver=self.nutrition_plan_entry_saver,
            nutrition_history_builder=self.nutrition_history_builder,
            nutrition_label_parser=self.nutrition_label_parser,
            nutrition_label_saver=self.nutrition_label_saver,
            nutrition_library_loader=self.nutrition_library_loader,
            personal_profile_saver=self.personal_profile_saver,
            body_measurement_saver=self.body_measurement_saver,
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
            personal_history_builder=lambda **kwargs: {
                "kind": "rhythmos.mobile_personal_history",
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
        self.assertEqual(
            self.client.get("/healthz").get_json(),
            {
                "status": "ok",
                "supabase_url_configured": False,
                "supabase_service_role_configured": False,
                "cloud_sync_configured": False,
                "mobile_sync_configured": True,
                "mobile_account_auth_configured": False,
                "rhythmos_account_registration_enabled": False,
                "apple_sign_in_configured": False,
            },
        )
        response = self.client.get("/v1/mobile/daily-snapshot")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "UNAUTHORIZED"})

    def test_snapshot_is_read_only_and_not_cached(self):
        response = self.client.get("/v1/mobile/daily-snapshot?date=2026-09-07", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), self.snapshot)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_verified_apple_identity_creates_a_rotating_account_session(self):
        store = _CloudStore()
        app = create_app(
            {
                **self.config,
                "SUPABASE_URL": "https://project.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-test-key",
                "RHYTHMOS_MOBILE_SESSION_SIGNING_KEY": "a" * 48,
                "RHYTHMOS_APPLE_AUDIENCE": "com.rhythmos.ios",
                "RHYTHMOS_OWNER_APPLE_SUB": "apple-owner-subject",
            },
            snapshot_builder=lambda **kwargs: self.snapshot,
            cloud_store_factory=lambda _settings: store,
            apple_identity_verifier=lambda token, nonce: (
                "apple-owner-subject" if token == "identity-token" and nonce == "n" * 32 else "other"
            ),
        )
        client = app.test_client()
        device_id = "ios-device-1234567890"
        response = client.post("/v1/mobile/auth/apple", json={
            "identity_token": "identity-token", "nonce": "n" * 32, "device_id": device_id,
        })
        self.assertEqual(response.status_code, 200)
        created = response.get_json()
        self.assertEqual(created["account_id"], self.config.get("POLAR_MEMBER_ID", "daily-recovery-coach-local"))
        self.assertNotIn("mobile-api-token", str(created))

        protected = client.get(
            "/v1/mobile/daily-snapshot?date=2026-09-07",
            headers={"Authorization": f"Bearer {created['access_token']}"},
        )
        self.assertEqual(protected.status_code, 200)

        refreshed = client.post("/v1/mobile/auth/refresh", json={
            "refresh_token": created["refresh_token"], "device_id": device_id,
        })
        self.assertEqual(refreshed.status_code, 200)
        self.assertNotEqual(refreshed.get_json()["refresh_token"], created["refresh_token"])

    def test_rhythmos_account_registration_and_login_share_one_private_account(self):
        store = _CloudStore()
        app = create_app(
            {
                **self.config,
                "SUPABASE_URL": "https://project.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-test-key",
                "RHYTHMOS_MOBILE_SESSION_SIGNING_KEY": "a" * 48,
                "RHYTHMOS_ACCOUNT_REGISTRATION_ENABLED": "true",
                "RHYTHMOS_ACCOUNT_REGISTRATION_CODE_SHA256": sha256(b"test-invitation").hexdigest(),
            },
            snapshot_builder=lambda **kwargs: self.snapshot,
            cloud_store_factory=lambda _settings: store,
        )
        client = app.test_client()
        payload = {
            "account_name": "rhythmos.tester", "password": "a-safe-test-password",
            "registration_code": "test-invitation",
            "device_id": "ios-device-1234567890",
        }
        created = client.post("/v1/mobile/auth/account/register", json=payload)
        self.assertEqual(created.status_code, 201)
        created_body = created.get_json()
        self.assertEqual(created_body["account_id"], self.config.get("POLAR_MEMBER_ID", "daily-recovery-coach-local"))
        self.assertNotIn(payload["password"], str(store.documents))

        logged_in = client.post("/v1/mobile/auth/account/login", json=payload)
        self.assertEqual(logged_in.status_code, 200)
        self.assertEqual(logged_in.get_json()["account_id"], created_body["account_id"])
        self.assertNotEqual(logged_in.get_json()["refresh_token"], created_body["refresh_token"])

        bad_password = client.post("/v1/mobile/auth/account/login", json={**payload, "password": "wrong-password-123"})
        unknown_account = client.post("/v1/mobile/auth/account/login", json={**payload, "account_name": "unknown.account"})
        self.assertEqual(bad_password.get_json(), {"error": "INVALID_ACCOUNT_CREDENTIALS"})
        self.assertEqual(unknown_account.get_json(), {"error": "INVALID_ACCOUNT_CREDENTIALS"})
        repeated_registration = client.post("/v1/mobile/auth/account/register", json={
            **payload, "account_name": "another.tester",
        })
        self.assertEqual(repeated_registration.status_code, 403)
        self.assertEqual(repeated_registration.get_json(), {"error": "ACCOUNT_REGISTRATION_DISABLED"})

    def test_first_verified_apple_login_returns_only_an_enrollment_fingerprint(self):
        store = _CloudStore()
        app = create_app(
            {
                **self.config,
                "SUPABASE_URL": "https://project.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-test-key",
                "RHYTHMOS_MOBILE_SESSION_SIGNING_KEY": "a" * 48,
                "RHYTHMOS_APPLE_AUDIENCE": "com.rhythmos.ios",
            },
            cloud_store_factory=lambda _settings: store,
            apple_identity_verifier=lambda _token, _nonce: "apple-owner-subject",
        )
        response = app.test_client().post("/v1/mobile/auth/apple", json={
            "identity_token": "identity-token", "nonce": "n" * 32,
            "device_id": "ios-device-1234567890",
        })
        body = response.get_json()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(body["error"], "ACCOUNT_ENROLLMENT_REQUIRED")
        self.assertEqual(len(body["owner_claim_sha256"]), 64)
        self.assertNotIn("apple-owner-subject", str(body))

    def test_sync_returns_only_safe_summary(self):
        response = self.client.post("/v1/mobile/sync", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"success": True, "run_id": "safe-run-id", "records_imported": 4})

    def test_sync_and_reviewed_screenshot_refresh_cloud_recovery_history(self):
        store = _CloudStore()
        history = {
            "kind": "rhythmos.mobile_recovery_history",
            "version": 1,
            "generated_at": "2026-09-08T00:00:00Z",
            "days": [{"date": "2026-09-07"}],
        }
        app = create_app(
            {**self.config, "POLAR_MEMBER_ID": "test-member"},
            runner_factory=lambda: _Runner(),
            snapshot_builder=lambda **kwargs: self.snapshot,
            screenshot_importer=lambda payload: {"date": payload["date"]},
            history_builder=lambda **kwargs: history,
            cloud_store_factory=lambda _settings: store,
        )
        client = app.test_client()

        self.assertEqual(client.post("/v1/mobile/sync", headers=self.headers).status_code, 200)
        self.assertEqual(
            store.documents[("test-member", "recovery_history", "days:28")].payload,
            history,
        )
        screenshot = {
            "date": "2026-09-07", "rmssd": 42.5, "mean_hr": 57,
            "image_sha256": "a" * 64, "user_confirmed": True,
        }
        self.assertEqual(
            client.post("/v1/mobile/kubios-screenshot-import", headers=self.headers, json=screenshot).status_code,
            201,
        )
        self.assertEqual(store.documents[("test-member", "recovery_history", "days:28")].revision, 2)

    def test_manual_nutrition_entry_requires_auth_and_returns_refreshed_snapshot(self):
        payload = {"date": "2026-09-07", "food_name": "午餐", "calories_kcal": 620}
        self.assertEqual(self.client.post("/v1/mobile/nutrition-entry", json=payload).status_code, 401)

        response = self.client.post("/v1/mobile/nutrition-entry", headers=self.headers, json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), self.snapshot)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.nutrition_entry_saver.assert_called_once_with(payload)

    def test_repeated_idempotent_mobile_write_replays_without_duplicate_local_save(self):
        store = _CloudStore()
        app = create_app(
            {**self.config, "POLAR_MEMBER_ID": "test-member"},
            snapshot_builder=lambda **kwargs: self.snapshot,
            nutrition_entry_saver=self.nutrition_entry_saver,
            cloud_store_factory=lambda _settings: store,
        )
        client = app.test_client()
        payload = {"date": "2026-09-07", "food_name": "午餐", "calories_kcal": 620}
        headers = {**self.headers, "Idempotency-Key": "ios-write-5f238171"}

        first = client.post("/v1/mobile/nutrition-entry", headers=headers, json=payload)
        repeated = client.post("/v1/mobile/nutrition-entry", headers=headers, json=payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.get_json(), self.snapshot)
        self.nutrition_entry_saver.assert_called_once_with(payload)
        self.assertIn(
            ("test-member", "mobile_request", "ios:nutrition_entry:ios-write-5f238171"),
            store.documents,
        )
        self.assertIn(
            ("test-member", "mobile_change", "ios:ios-write-5f238171"),
            store.documents,
        )

    def test_idempotency_key_cannot_be_reused_for_a_different_write_body(self):
        store = _CloudStore()
        app = create_app(
            {**self.config, "POLAR_MEMBER_ID": "test-member"},
            snapshot_builder=lambda **kwargs: self.snapshot,
            nutrition_entry_saver=self.nutrition_entry_saver,
            cloud_store_factory=lambda _settings: store,
        )
        client = app.test_client()
        headers = {**self.headers, "Idempotency-Key": "ios-write-5f238171"}
        client.post(
            "/v1/mobile/nutrition-entry", headers=headers,
            json={"date": "2026-09-07", "food_name": "午餐", "calories_kcal": 620},
        )
        conflict = client.post(
            "/v1/mobile/nutrition-entry", headers=headers,
            json={"date": "2026-09-07", "food_name": "午餐", "calories_kcal": 621},
        )

        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.get_json(), {"error": "IDEMPOTENCY_KEY_CONFLICT"})
        self.nutrition_entry_saver.assert_called_once()

    def test_nutrition_plan_cell_edit_requires_auth_and_returns_refreshed_snapshot(self):
        payload = {"week_start": "2026-09-07", "weekday": 0, "meal_slot": "breakfast"}
        self.assertEqual(self.client.post("/v1/mobile/nutrition-plan-entry", json=payload).status_code, 401)

        response = self.client.post("/v1/mobile/nutrition-plan-entry", headers=self.headers, json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), self.snapshot)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.nutrition_plan_entry_saver.assert_called_once_with(payload)

    def test_nutrition_plan_cycle_edit_requires_auth_and_returns_refreshed_snapshot(self):
        payload = {
            "original_start_date": "2026-08-03", "name": "2026 适应期",
            "start_date": "2026-08-03", "duration_weeks": 8,
        }
        self.assertEqual(self.client.post("/v1/mobile/nutrition-plan-cycle", json=payload).status_code, 401)

        response = self.client.post("/v1/mobile/nutrition-plan-cycle", headers=self.headers, json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), self.snapshot)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.nutrition_plan_cycle_saver.assert_called_once_with(payload)

    def test_nutrition_history_uses_the_authenticated_history_boundary(self):
        self.assertEqual(self.client.get("/v1/mobile/nutrition-history").status_code, 401)

        response = self.client.get("/v1/mobile/nutrition-history?days=28", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["kind"], "rhythmos.mobile_nutrition_history")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.nutrition_history_builder.assert_called_once_with(days=28)

    def test_personal_profile_and_body_edits_require_auth_and_return_a_fresh_snapshot(self):
        profile = {"name": "测试用户", "gender": "male", "birth_date": "1995-06-01", "height_cm": 175}
        body = {"date": "2026-09-07", "height_cm": 175, "weight_kg": 80.5}
        self.assertEqual(self.client.post("/v1/mobile/personal-profile", json=profile).status_code, 401)
        self.assertEqual(self.client.post("/v1/mobile/body-measurement", json=body).status_code, 401)

        profile_response = self.client.post("/v1/mobile/personal-profile", headers=self.headers, json=profile)
        body_response = self.client.post("/v1/mobile/body-measurement", headers=self.headers, json=body)

        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(body_response.status_code, 200)
        self.assertEqual(profile_response.get_json(), self.snapshot)
        self.assertEqual(body_response.get_json(), self.snapshot)
        self.personal_profile_saver.assert_called_once_with(profile)
        self.body_measurement_saver.assert_called_once_with(body)

    def test_personal_history_requires_auth_and_has_a_bounded_range(self):
        self.assertEqual(self.client.get("/v1/mobile/personal-history").status_code, 401)
        response = self.client.get("/v1/mobile/personal-history?days=28", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["kind"], "rhythmos.mobile_personal_history")
        self.assertEqual(self.client.get("/v1/mobile/personal-history?days=29", headers=self.headers).status_code, 400)

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
        response = self.client.get("/v1/mobile/recovery-history?days=29", headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "INVALID_HISTORY_RANGE"})
        response = self.client.get("/v1/mobile/recovery-history?days=bad", headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "INVALID_HISTORY_RANGE"})

    def test_recovery_history_rebuilds_a_cloud_document_missing_sleep_details(self):
        store = _CloudStore()
        legacy_history = {
            "kind": "rhythmos.mobile_recovery_history",
            "version": 1,
            "days": [{"date": "2026-09-07", "details": {}}],
        }
        complete_history = {
            "kind": "rhythmos.mobile_recovery_history",
            "version": 1,
            "days": [{
                "date": "2026-09-07",
                "details": {},
                "sleep_details": {
                    field: None for field in (
                        "duration_minutes", "score", "sleep_start_time", "wake_time",
                        "actual_duration_minutes", "deep_duration_minutes", "rem_duration_minutes",
                        "average_hr_bpm", "nightly_hrv_rmssd_ms", "resting_hr_bpm",
                        "respiration_rate_bpm", "regularity_score",
                    )
                },
            }],
        }
        store.save("test-member", "recovery_history", "days:28", legacy_history, "old-device")
        builder = Mock(return_value=complete_history)
        app = create_app(
            {**self.config, "POLAR_MEMBER_ID": "test-member"},
            history_builder=builder,
            cloud_store_factory=lambda _settings: store,
        )

        response = app.test_client().get("/v1/mobile/recovery-history?days=28", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), complete_history)
        builder.assert_called_once_with(days=28)
        self.assertEqual(store.documents[("test-member", "recovery_history", "days:28")].revision, 2)

    def test_training_history_is_token_protected_and_range_checked(self):
        response = self.client.get("/v1/mobile/training-history")
        self.assertEqual(response.status_code, 401)
        response = self.client.get("/v1/mobile/training-history", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["requested_days"], 28)
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

    def test_cloud_storage_failure_reports_a_safe_actionable_code(self):
        class CredentialsRejectedStore:
            def save(self, *args, **kwargs):
                raise CloudSyncError("upstream rejected credentials", failure_code="credentials")

            def load(self, *args, **kwargs):
                raise CloudSyncError("upstream rejected credentials", failure_code="credentials")

        app = create_app(self.config, cloud_store_factory=lambda settings: CredentialsRejectedStore())
        app.config["TESTING"] = True
        client = app.test_client()
        payload = {"payload": self.snapshot, "source_device": "macOS-test"}

        response = client.post(
            "/v1/cloud/documents/daily_snapshot/2026-09-07", headers=self.headers, json=payload,
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json(), {"error": "CLOUD_SYNC_CREDENTIALS"})

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
