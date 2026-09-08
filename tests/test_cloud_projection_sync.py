import unittest
from unittest.mock import Mock

from src.cloud_projection_sync import (
    DEFAULT_SYNC_SERVICE_URL,
    CloudProjectionSyncError,
    load_desktop_sync_settings,
    publish_local_projections,
)


class _Response:
    status_code = 201


class CloudProjectionSyncTests(unittest.TestCase):
    def test_mac_keychain_token_uses_the_production_https_service_by_default(self):
        settings = load_desktop_sync_settings(
            environment={}, keychain_lookup=lambda: "stored-secret-not-printed"
        )
        self.assertEqual(settings["RHYTHMOS_SYNC_SERVICE_URL"], DEFAULT_SYNC_SERVICE_URL)
        self.assertEqual(settings["MOBILE_SYNC_API_TOKEN"], "stored-secret-not-printed")

    def test_without_both_settings_the_publisher_does_not_make_a_request(self):
        post = Mock()
        result = publish_local_projections(settings={}, http_post=post)
        self.assertIsNone(result)
        post.assert_not_called()

    def test_publishes_safe_snapshots_and_histories_only_through_render(self):
        post = Mock(return_value=_Response())
        recovery = {"kind": "rhythmos.mobile_recovery_history", "days": [{"date": "2026-09-08"}]}
        training = {"kind": "rhythmos.mobile_training_history", "days": []}
        snapshot = {"kind": "rhythmos.mobile_daily_snapshot", "date": "2026-09-08"}
        result = publish_local_projections(
            settings={
                "RHYTHMOS_SYNC_SERVICE_URL": "https://sync.example.test",
                "MOBILE_SYNC_API_TOKEN": "token-not-printed",
            },
            snapshot_builder=lambda **kwargs: snapshot,
            recovery_history_builder=lambda **kwargs: recovery,
            training_history_builder=lambda **kwargs: training,
            http_post=post,
        )
        self.assertEqual(result, {"success": True, "documents_published": 3, "history_days": 14})
        self.assertEqual(post.call_count, 3)
        self.assertTrue(post.call_args_list[0].args[0].endswith("/daily_snapshot/2026-09-08"))
        self.assertEqual(post.call_args_list[1].kwargs["json"]["source_device"], "macos-local")
        self.assertNotIn("token-not-printed", str(result))

    def test_partial_settings_fail_without_sending_data(self):
        post = Mock()
        with self.assertRaises(CloudProjectionSyncError):
            publish_local_projections(
                settings={"RHYTHMOS_SYNC_SERVICE_URL": "https://sync.example.test"}, http_post=post,
            )
        post.assert_not_called()
