import unittest

from src.cloud_sync_store import SupabaseCloudDocumentStore


class SupabaseCloudDocumentStoreTests(unittest.TestCase):
    def test_new_secret_key_uses_apikey_without_jwt_authorization(self):
        store = SupabaseCloudDocumentStore(
            "https://project.supabase.co", "sb_secret_example_for_test_only"
        )

        self.assertEqual(store._headers["apikey"], "sb_secret_example_for_test_only")
        self.assertNotIn("Authorization", store._headers)

    def test_legacy_service_role_key_keeps_bearer_authorization(self):
        store = SupabaseCloudDocumentStore(
            "https://project.supabase.co", "legacy-service-role-test-key"
        )

        self.assertEqual(store._headers["Authorization"], "Bearer legacy-service-role-test-key")

