import unittest
import tempfile
from pathlib import Path
from datetime import date, datetime, timezone
from unittest.mock import patch

from src.pipeline import fetch
from src.pipeline.errors import PipelineStepError


class FakeClient:
    def get_sports(self):
        return None

    def get_user_account_info(self):
        return None

    def get_daily_activity_v3(self, **kwargs):
        return None

    def get_training_sessions(self, **kwargs):
        return None

    def get_sleep(self, **kwargs):
        return None

    def get_nightly_recharge(self, **kwargs):
        return None

    def get_continuous_heart_rate(self, **kwargs):
        return None

    def get_cardio_load(self):
        return None


def success_result(items=None):
    return {"ok": True, "data": items or [], "status_code": None, "path": "safe.json"}


def failure_result(status_code):
    return {"ok": False, "data": None, "status_code": status_code, "path": "safe.json"}


class PipelineFetchTests(unittest.TestCase):
    def test_scheduled_dataset_cadence(self):
        utc = timezone.utc
        self.assertEqual(
            fetch.scheduled_dataset_names(datetime(2026, 7, 22, 10, 0, tzinfo=utc)),
            (),
        )
        self.assertEqual(
            fetch.scheduled_dataset_names(datetime(2026, 7, 22, 12, 0, tzinfo=utc)),
            fetch.SCHEDULED_DATASETS,
        )
        self.assertEqual(
            fetch.scheduled_dataset_names(datetime(2026, 7, 22, 22, 0, tzinfo=utc)),
            (),
        )
        self.assertEqual(
            fetch.scheduled_dataset_names(datetime(2026, 7, 22, 23, 0, tzinfo=utc)),
            fetch.SCHEDULED_DATASETS,
        )

    def test_scheduled_refresh_filters_to_allowed_polar_datasets(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "src.pipeline.fetch.scheduled_dataset_names",
                return_value=("daily_activity",),
            ), patch(
                "src.pipeline.fetch.fetch_and_save_result",
                return_value=success_result([{"date": "2026-07-22"}]),
            ) as fetch_result:
                summary = fetch.run(
                    {"polar_client": FakeClient(), "trigger_type": "scheduled"},
                    today=date(2026, 7, 22),
                    raw_dir=Path(directory),
                )
        self.assertEqual(summary["datasets_checked"], 1)
        self.assertEqual(summary["endpoint_results"][0]["endpoint"], "daily_activity")
        self.assertEqual(fetch_result.call_count, 1)

    def test_scheduled_refresh_is_noop_after_cutoff(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "src.pipeline.fetch.scheduled_dataset_names",
                return_value=(),
            ), patch("src.pipeline.fetch.fetch_and_save_result") as fetch_result:
                summary = fetch.run(
                    {"polar_client": FakeClient(), "trigger_type": "scheduled"},
                    today=date(2026, 7, 22),
                    raw_dir=Path(directory),
                )
        self.assertTrue(summary["scheduled_noop"])
        fetch_result.assert_not_called()

    def test_source_snapshot_changes_only_with_tracked_source_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIsNone(fetch.source_snapshot(root))
            tracked = root / "polar_daily_activity.json"
            tracked.write_text("[]", encoding="utf-8")
            first = fetch.source_snapshot(root)
            (root / "unrelated.txt").write_text("changed", encoding="utf-8")
            self.assertEqual(fetch.source_snapshot(root), first)
            tracked.write_text('[{"date":"2026-07-12"}]', encoding="utf-8")
            self.assertNotEqual(fetch.source_snapshot(root), first)

    def test_optional_endpoint_failures_become_warnings(self):
        results = [success_result([{"ok": True}]) for _ in range(6)] + [
            failure_result(404),
            failure_result(404),
        ]
        with patch("src.pipeline.fetch.fetch_and_save_result", side_effect=results):
            summary = fetch.run(
                {"polar_client": FakeClient()},
                today=date(2026, 7, 10),
            )
        self.assertEqual(summary["warning_count"], 1)
        self.assertEqual(summary["items_fetched"], 6)
        self.assertEqual(summary["endpoint_results"][-2]["status"], "warning")
        self.assertEqual(summary["endpoint_results"][-1]["status"], "unavailable")

    def test_cardio_load_404_is_non_blocking_capability_unavailable(self):
        results = [success_result([{"ok": True}]) for _ in range(7)] + [
            failure_result(404),
        ]
        with patch("src.pipeline.fetch.fetch_and_save_result", side_effect=results):
            summary = fetch.run(
                {"polar_client": FakeClient()},
                today=date(2026, 7, 10),
            )
        cardio = summary["endpoint_results"][-1]
        self.assertEqual(cardio["endpoint"], "cardio_load")
        self.assertEqual(cardio["status"], "unavailable")
        self.assertEqual(summary["warning_count"], 0)

    def test_required_endpoint_failure_raises_safe_code(self):
        results = [failure_result(503)] + [success_result() for _ in range(7)]
        with patch("src.pipeline.fetch.fetch_and_save_result", side_effect=results):
            with self.assertRaises(PipelineStepError) as raised:
                fetch.run(
                    {"polar_client": FakeClient()},
                    today=date(2026, 7, 10),
                )
        self.assertEqual(raised.exception.code, "FETCH_REQUIRED_ENDPOINT_FAILED")
        self.assertNotIn("payload", raised.exception.safe_message.lower())

    def test_sleep_sync_requests_sixty_days_of_polar_sleep_and_nightly_data(self):
        def execute_fetcher(_label, _filename, fetcher, **_kwargs):
            return success_result(fetcher())

        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "src.pipeline.fetch.fetch_and_save_result", side_effect=execute_fetcher,
            ), patch(
                "src.pipeline.fetch.fetch_sleep_details",
                return_value={"nightSleeps": [{"sleepDate": "2026-07-22"}]},
            ) as sleep_details, patch(
                "src.pipeline.fetch.fetch_nightly_recharge_with_samples",
                return_value={"nightlyRechargeResults": []},
            ) as nightly_recharge, patch(
                "src.pipeline.fetch.fetch_continuous_heart_rate_for_dates",
                return_value={"heartRateSamplesPerDay": []},
            ):
                fetch.run(
                    {"polar_client": FakeClient()},
                    today=date(2026, 7, 22),
                    raw_dir=Path(directory),
                )

        expected_from = "2026-05-24"
        self.assertEqual(sleep_details.call_args.kwargs["from_date"], expected_from)
        self.assertEqual(nightly_recharge.call_args.kwargs["from_date"], expected_from)

    def test_routine_sync_requests_only_recent_sleep_and_nightly_data(self):
        def execute_fetcher(_label, _filename, fetcher, **_kwargs):
            return success_result(fetcher())

        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "src.pipeline.fetch.fetch_and_save_result", side_effect=execute_fetcher,
            ), patch(
                "src.pipeline.fetch.fetch_sleep_details",
                return_value={"nightSleeps": [{"sleepDate": "2026-07-22"}]},
            ) as sleep_details, patch(
                "src.pipeline.fetch.fetch_nightly_recharge_with_samples",
                return_value={"nightlyRechargeResults": []},
            ) as nightly_recharge, patch(
                "src.pipeline.fetch.fetch_continuous_heart_rate_for_dates",
                return_value={"heartRateSamplesPerDay": []},
            ):
                fetch.run(
                    {"polar_client": FakeClient(), "trigger_type": "catch_up"},
                    today=date(2026, 7, 22),
                    raw_dir=Path(directory),
                )

        expected_from = "2026-07-15"
        self.assertEqual(sleep_details.call_args.kwargs["from_date"], expected_from)
        self.assertEqual(nightly_recharge.call_args.kwargs["from_date"], expected_from)


if __name__ == "__main__":
    unittest.main()
