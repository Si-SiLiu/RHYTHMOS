import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import polar_client, polar_fetch


class PolarFetchTests(unittest.TestCase):
    def test_fetch_and_save_writes_success_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "payload.json"

            with patch("src.polar_fetch.print"), patch(
                "src.polar_fetch.save_raw_json", return_value=output
            ) as save:
                data = polar_fetch.fetch_and_save("Thing", "payload.json", lambda: [{"id": 1}])

            self.assertEqual(data, [{"id": 1}])
            save.assert_called_once_with("payload.json", [{"id": 1}])

    def test_fetch_and_save_writes_api_error_payload(self):
        error = polar_client.PolarAPIError("/broken", 403, "Forbidden")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "error.json"

            with patch("src.polar_fetch.print"), patch(
                "src.polar_fetch.save_raw_json", return_value=output
            ) as save:
                data = polar_fetch.fetch_and_save(
                    "Broken",
                    "error.json",
                    lambda: (_ for _ in ()).throw(error),
                )

        self.assertIsNone(data)
        saved_payload = save.call_args.args[1]
        self.assertEqual(saved_payload["path"], "/broken")
        self.assertEqual(saved_payload["status_code"], 403)
        self.assertNotIn("access_token", saved_payload)
        self.assertNotIn("refresh_token", saved_payload)

    def test_structured_result_exposes_safe_http_status(self):
        error = polar_client.PolarAPIError("/unavailable", 404, "Not Found")
        with patch("src.polar_fetch.print"), patch(
            "src.polar_fetch.save_raw_json", return_value=Path("safe-error.json")
        ):
            result = polar_fetch.fetch_and_save_result(
                "Optional",
                "safe-error.json",
                lambda: (_ for _ in ()).throw(error),
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status_code"], 404)
        self.assertNotIn("response", result)

    def test_fetch_sleep_details_expands_v4_date_listing(self):
        class Client:
            def get_sleep(self, **kwargs):
                return {"nightSleeps": [{"sleepDate": "2026-07-10"}]}

            def get_sleep_for_date(self, date_value):
                return {
                    "nightSleeps": [
                        {
                            "sleepDate": date_value,
                            "sleepEvaluation": {"asleepDuration": "27000s"},
                        }
                    ]
                }

        payload = polar_fetch.fetch_sleep_details(
            Client(), from_date="2026-07-01", to_date="2026-07-10"
        )

        self.assertEqual(len(payload["nightSleeps"]), 1)
        self.assertEqual(
            payload["nightSleeps"][0]["sleepEvaluation"]["asleepDuration"],
            "27000s",
        )

    def test_fetch_sleep_details_checks_requested_current_date(self):
        calls = []

        class Client:
            def get_sleep(self, **kwargs):
                return {"nightSleeps": [{"sleepDate": "2026-07-09"}]}

            def get_sleep_for_date(self, date_value):
                calls.append(date_value)
                if date_value == "2026-07-10":
                    raise polar_client.PolarAPIError("/sleeps", 404, "Not found")
                return {"nightSleeps": [{"sleepDate": date_value}]}

        payload = polar_fetch.fetch_sleep_details(
            Client(), from_date="2026-07-01", to_date="2026-07-10",
            ensure_date="2026-07-10",
        )

        self.assertEqual(calls, ["2026-07-09", "2026-07-10"])
        self.assertEqual(len(payload["nightSleeps"]), 1)

    def test_sleep_history_is_split_into_supported_ranges(self):
        ranges = []

        class Client:
            def get_sleep(self, **kwargs):
                ranges.append((kwargs["from_date"], kwargs["to_date"]))
                return {"nightSleeps": []}

            def get_sleep_for_date(self, _date_value):
                raise AssertionError("no individual record should be requested")

        polar_fetch.fetch_sleep_details(
            Client(), from_date="2026-07-05", to_date="2026-09-02"
        )

        self.assertEqual(ranges, [
            ("2026-07-05", "2026-08-02"),
            ("2026-08-03", "2026-08-31"),
            ("2026-09-01", "2026-09-02"),
        ])

    def test_fetch_continuous_hr_uses_per_date_endpoint(self):
        class Client:
            def get_continuous_heart_rate(self, date_value=None, **kwargs):
                next_date = "2026-07-11"
                return {
                    "continuousSamples": {
                        "heartRateSamplesPerDay": [
                            {
                                "date": date_value,
                                "samples": [{"heartRate": 55, "offsetMillis": 1}],
                            },
                            {
                                "date": next_date,
                                "samples": ([{"heartRate": 56, "offsetMillis": 2}] * (2 if date_value == next_date else 1)),
                            },
                        ]
                    }
                }

        payload = polar_fetch.fetch_continuous_heart_rate_for_dates(
            Client(), ["2026-07-10", "2026-07-11"]
        )

        self.assertEqual(payload["heartRateSamplesPerDay"][0]["date"], "2026-07-10")
        self.assertEqual(len(payload["heartRateSamplesPerDay"]), 2)
        self.assertEqual(len(payload["heartRateSamplesPerDay"][1]["samples"]), 2)

    def test_nightly_recharge_samples_are_fetched_one_day_at_a_time(self):
        calls = []

        class Client:
            def get_nightly_recharge(self, **kwargs):
                calls.append(kwargs)
                if not kwargs.get("samples"):
                    return {"nightlyRechargeResults": [
                        {"sleepResultDate": "2026-07-09", "meanNightlyRecoveryRespirationInterval": 0},
                        {"sleepResultDate": "2026-07-10", "meanNightlyRecoveryRespirationInterval": 0},
                    ]}
                return {"nightlyRechargeResults": [{
                    "sleepResultDate": kwargs["from_date"],
                    "breathingRateSamples": [{"breathingRateValues": [14.0, 16.0]}],
                }]}

        payload = polar_fetch.fetch_nightly_recharge_with_samples(
            Client(), from_date="2026-07-01", to_date="2026-07-11",
        )

        self.assertEqual(len(calls), 3)
        for call in calls[1:]:
            self.assertTrue(call["samples"])
            start = polar_fetch.date.fromisoformat(call["from_date"])
            end = polar_fetch.date.fromisoformat(call["to_date"])
            self.assertEqual(end - start, polar_fetch.timedelta(days=1))
        self.assertEqual(
            payload["nightlyRechargeResults"][0]["breathingRateSamples"][0]["breathingRateValues"],
            [14.0, 16.0],
        )

    def test_nightly_recharge_history_is_split_before_sample_fetches(self):
        range_calls = []

        class Client:
            def get_nightly_recharge(self, **kwargs):
                if not kwargs["samples"]:
                    range_calls.append((kwargs["from_date"], kwargs["to_date"]))
                    return {"nightlyRechargeResults": []}
                raise AssertionError("no sample record should be requested")

        polar_fetch.fetch_nightly_recharge_with_samples(
            Client(), from_date="2026-07-05", to_date="2026-09-02"
        )

        self.assertEqual(range_calls, [
            ("2026-07-05", "2026-08-02"),
            ("2026-08-03", "2026-08-31"),
            ("2026-09-01", "2026-09-02"),
        ])


if __name__ == "__main__":
    unittest.main()
