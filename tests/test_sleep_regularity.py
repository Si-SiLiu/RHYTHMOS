import unittest
from datetime import date, datetime, timedelta, timezone

from src.sleep_regularity import (
    CONFIG,
    CanonicalSleepRecord,
    SleepRegularityService,
    SleepSegment,
    calculate_circular_center,
    calculate_circular_mad,
    calculate_last_night_deviation,
    calculate_rolling_regularity_scores,
    calculate_summary_score,
    calculate_sri,
    determine_maturity,
    map_score_to_status,
    select_valid_sleep_records,
    signed_circular_difference_minutes,
    sleep_record_exclusion_reason,
)
from src.sleep_adapters import HealthKitSleepAdapter, polar_to_canonical


TZ = timezone(timedelta(hours=8))


def record(day, bedtime_hour=23, wake_hour=7, duration=450, segments=()):
    start = datetime.combine(day, datetime.min.time(), TZ).replace(hour=bedtime_hour)
    end = datetime.combine(day, datetime.min.time(), TZ).replace(hour=wake_hour)
    if end <= start:
        end += timedelta(days=1)
    return CanonicalSleepRecord(day, start, end, duration, "test", str(day), "UTC+08:00", tuple(segments))


class SleepRegularityTests(unittest.TestCase):
    def test_maturity_thresholds_and_no_zero_for_insufficient_data(self):
        self.assertEqual(determine_maturity(6), "collecting")
        self.assertEqual(determine_maturity(7), "provisional")
        self.assertEqual(determine_maturity(14), "reliable")
        self.assertEqual(determine_maturity(28), "stable")
        result = calculate_summary_score([record(date(2026, 7, 1) + timedelta(days=i)) for i in range(6)])
        self.assertIsNone(result.score)
        self.assertEqual(result.algorithm_type, "insufficient_data")

    def test_status_is_derived_from_same_score(self):
        self.assertEqual(map_score_to_status(0), "irregular")
        self.assertNotEqual(map_score_to_status(0), "variable")
        self.assertEqual(map_score_to_status(None, "collecting"), "collecting")

    def test_circular_difference_across_midnight(self):
        self.assertEqual(signed_circular_difference_minutes(10, 1430), 20)
        self.assertEqual(signed_circular_difference_minutes(1430, 10), -20)
        self.assertEqual(calculate_circular_center([1435, 5, 10]), 5)
        self.assertEqual(calculate_circular_mad([1435, 5, 10], 5), 5)

    def test_cross_midnight_interval_is_valid(self):
        item = record(date(2026, 7, 1), bedtime_hour=23, wake_hour=6, duration=400)
        self.assertEqual(select_valid_sleep_records([item]), [item])
        self.assertEqual(sleep_record_exclusion_reason({"date": "2026-07-01", "wake_time": "07:00", "actual_sleep_duration": 400}), "missing_bedtime")

    def test_summary_uses_three_robust_components_and_weights_sum_to_one(self):
        days = [date(2026, 7, 1) + timedelta(days=i) for i in range(14)]
        result = calculate_summary_score([record(day, 23, 7, 450) for day in days])
        self.assertEqual(result.algorithm_type, "summary_composite")
        self.assertGreaterEqual(result.score, 99)
        self.assertEqual(set(result.component_scores), {"bedtime", "wake_time", "duration"})
        self.assertAlmostEqual(sum(CONFIG["weights"].values()), 1.0)

    def test_single_outlier_does_not_destroy_robust_score(self):
        days = [date(2026, 7, 1) + timedelta(days=i) for i in range(14)]
        records = [record(day, 23, 7, 450) for day in days]
        records[-1] = record(days[-1], 5, 12, 200)
        result = calculate_summary_score(records)
        self.assertGreater(result.score, 70)

    def test_last_night_is_excluded_from_its_own_reference(self):
        prior_days = [date(2026, 7, 1) + timedelta(days=i) for i in range(14)]
        prior = [record(day, 23, 7, 450) for day in prior_days]
        current = record(date(2026, 7, 15), 1, 6, 400)
        deviation = calculate_last_night_deviation(current, prior + [current])
        self.assertAlmostEqual(deviation.bedtime_deviation_minutes, 120)
        self.assertAlmostEqual(deviation.wake_time_deviation_minutes, -60)
        self.assertEqual(deviation.dominant_deviation, "bedtime")

    def test_sri_ignores_unknown_and_reports_coverage(self):
        records = []
        for i in range(8):
            day = date(2026, 7, 1) + timedelta(days=i)
            start = datetime.combine(day, datetime.min.time(), TZ)
            segments = (
                SleepSegment(start, start + timedelta(hours=12), "awake"),
                SleepSegment(start + timedelta(hours=12), start + timedelta(hours=24), "asleep"),
            )
            records.append(CanonicalSleepRecord(day, start, start + timedelta(hours=24), 600, "test", str(day), "UTC+08:00", segments))
        result = calculate_sri(records)
        self.assertEqual(result.algorithm_type, "sri_timeline")
        self.assertEqual(result.score, 100)
        self.assertGreater(result.details["coverage_ratio"], 0.9)
        self.assertGreater(result.details["valid_day_pairs"], 1)

    def test_rolling_scores_match_individual_overlapping_windows(self):
        records = []
        for index in range(16):
            day = date(2026, 7, 1) + timedelta(days=index)
            start = datetime.combine(day, datetime.min.time(), TZ)
            segments = (
                SleepSegment(start, start + timedelta(hours=8), "awake"),
                SleepSegment(start + timedelta(hours=8), start + timedelta(hours=16), "asleep"),
            )
            records.append(CanonicalSleepRecord(
                day, start, start + timedelta(hours=16), 600,
                "test", str(day), "UTC+08:00", segments,
            ))
        rolling_scores = calculate_rolling_regularity_scores(records)
        for index, item in enumerate(records):
            expected = SleepRegularityService.calculate_regularity(records[:index + 1]).score
            self.assertEqual(rolling_scores[item.sleep_date], expected)

    def test_duplicate_dates_are_counted_once(self):
        day = date(2026, 7, 1)
        selected = select_valid_sleep_records([record(day, segments=()), record(day, segments=(SleepSegment(datetime.combine(day, datetime.min.time(), TZ), datetime.combine(day, datetime.min.time(), TZ) + timedelta(hours=1), "asleep"),))])
        self.assertEqual(len(selected), 1)
        self.assertEqual(len(selected[0].sleep_segments), 1)

    def test_source_adapters_share_canonical_model(self):
        source = {"date": "2026-07-01", "bedtime": "23:00", "wake_time": "07:00", "actual_sleep_duration": 420}
        polar = polar_to_canonical(source)
        healthkit = HealthKitSleepAdapter().to_canonical(source)
        self.assertEqual(polar.source, "polar")
        self.assertEqual(healthkit.source, "healthkit")
        self.assertEqual(polar.sleep_date, healthkit.sleep_date)


if __name__ == "__main__":
    unittest.main()
