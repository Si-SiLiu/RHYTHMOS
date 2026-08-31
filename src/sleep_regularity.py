"""Device-independent sleep regularity calculations.

The module deliberately contains no Streamlit dependencies.  It accepts the
resolved sleep projections already used by the dashboard and turns them into
validated canonical records before selecting SRI or the summary fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import math
import statistics
from typing import Any, Iterable, Mapping


SLEEP_REGULARITY_VERSION = "2.0.0"
CONFIG = {
    "minimum_score_nights": 7,
    "reliable_nights": 14,
    "stable_nights": 28,
    "window_nights": 14,
    "interval_min_minutes": 120,
    "interval_max_minutes": 960,
    "actual_max_minutes": 960,
    "weights": {"bedtime": 0.35, "wake_time": 0.45, "duration": 0.20},
    "thresholds_minutes": {"bedtime": 60.0, "wake_time": 45.0, "duration": 60.0},
    "sri_min_coverage": 0.60,
    "sri_min_pair_minutes": 120,
}
assert math.isclose(sum(CONFIG["weights"].values()), 1.0)


@dataclass(frozen=True)
class SleepSegment:
    start: datetime
    end: datetime
    state: str


@dataclass(frozen=True)
class CanonicalSleepRecord:
    sleep_date: date
    sleep_start: datetime
    sleep_end: datetime
    actual_sleep_duration: float
    source: str = "unknown"
    source_record_id: str | None = None
    timezone: str | None = None
    sleep_segments: tuple[SleepSegment, ...] = ()
    completeness: float = 1.0
    quality: str = "observed"


@dataclass
class SleepRegularityResult:
    algorithm_type: str
    score: float | None
    status: str
    maturity_status: str
    confidence: float
    valid_nights: int
    required_nights: int
    data_completeness: float
    component_scores: dict[str, float | None] = field(default_factory=dict)
    explanation: str = ""
    calculation_version: str = SLEEP_REGULARITY_VERSION
    calculated_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm_type": self.algorithm_type,
            "score": self.score,
            "status": self.status,
            "maturity_status": self.maturity_status,
            "confidence": self.confidence,
            "valid_nights": self.valid_nights,
            "required_nights": self.required_nights,
            "data_completeness": self.data_completeness,
            "component_scores": dict(self.component_scores),
            "explanation": self.explanation,
            "calculation_version": self.calculation_version,
            "calculated_at": self.calculated_at,
            **self.details,
        }


@dataclass(frozen=True)
class LastNightScheduleDeviation:
    typical_bedtime: float | None
    typical_wake_time: float | None
    typical_duration: float | None
    bedtime_deviation_minutes: float | None
    wake_time_deviation_minutes: float | None
    duration_deviation_minutes: float | None
    dominant_deviation: str | None
    confidence: float


def _number(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _field(record: Mapping[str, Any], name: str) -> Any:
    fields = record.get("resolved_fields") or {}
    if name in fields and isinstance(fields[name], Mapping):
        return fields[name].get("value")
    aliases = {
        "sleep_start_time": "bedtime", "wake_time": "wake_time",
        "actual_sleep_duration_minutes": "actual_sleep_duration",
        "total_sleep_duration_minutes": "total_sleep_duration",
    }
    return record.get(aliases.get(name, name))


def _parse_datetime(value: Any, day: date | None = None) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None
        for pattern in ("%H:%M:%S", "%H:%M"):
            try:
                parsed_time = datetime.strptime(text, pattern).time()
                parsed = datetime.combine(day or date.today(), parsed_time)
                break
            except ValueError:
                continue
        if parsed is None:
            return None
    return parsed


def _duration_minutes(value: Any) -> float | None:
    if value in (None, ""):
        return None
    number = _number(value)
    if number is not None:
        return number
    text = str(value).strip().upper()
    if text.endswith("S") and not text.startswith("P"):
        seconds = _number(text[:-1])
        return seconds / 60 if seconds is not None else None
    if text.startswith("PT"):
        import re
        match = re.fullmatch(r"PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?", text)
        if match:
            hours, minutes, seconds = (float(item or 0) for item in match.groups())
            return hours * 60 + minutes + seconds / 60
    return None


def signed_circular_difference_minutes(current: float, reference: float) -> float:
    """Return current-reference in the shortest signed 24-hour direction."""
    return ((float(current) - float(reference) + 720) % 1440) - 720


def circular_difference_minutes(current: float, reference: float) -> float:
    return abs(signed_circular_difference_minutes(current, reference))


def _clock_minutes(value: datetime) -> float:
    return value.hour * 60 + value.minute + value.second / 60


def calculate_circular_center(values: Iterable[float]) -> float | None:
    values = [float(value) % 1440 for value in values]
    if not values:
        return None
    # The observed value minimizing circular absolute distance is a robust
    # circular median and avoids a 23:xx/00:xx discontinuity.
    return min(values, key=lambda candidate: sum(circular_difference_minutes(candidate, value) for value in values))


def calculate_circular_mad(values: Iterable[float], center: float | None = None) -> float | None:
    values = [float(value) % 1440 for value in values]
    center = calculate_circular_center(values) if center is None else center
    if center is None:
        return None
    return statistics.median(circular_difference_minutes(value, center) for value in values)


def _normalise_state(value: Any) -> str:
    text = str(value or "").upper()
    if "WAKE" in text or "AWAKE" in text:
        return "awake"
    if "SLEEP" in text or "REM" in text or "NON_REM" in text:
        return "asleep"
    return "unknown"


def _segments(record: Mapping[str, Any], start: datetime, end: datetime) -> tuple[SleepSegment, ...]:
    changes = record.get("sleep_state_changes") or record.get("sleep_segments") or []
    if not isinstance(changes, list):
        return ()
    parsed = []
    for item in changes:
        if isinstance(item, SleepSegment):
            parsed.append(item)
            continue
        if not isinstance(item, Mapping):
            continue
        offset = _duration_minutes(item.get("offsetFromStart"))
        if offset is None:
            offset = _number(item.get("offset_seconds"))
            offset = offset / 60 if offset is not None else None
        if offset is not None and 0 <= offset < (end - start).total_seconds() / 60:
            parsed.append((offset, _normalise_state(item.get("newState", item.get("state")))))
    parsed.sort(key=lambda item: item[0] if isinstance(item, tuple) else item.start)
    result = []
    for index, item in enumerate(parsed):
        if isinstance(item, SleepSegment):
            result.append(item)
            continue
        offset, state = item
        next_offset = parsed[index + 1][0] if index + 1 < len(parsed) and isinstance(parsed[index + 1], tuple) else (parsed[index + 1].start - start).total_seconds() / 60 if index + 1 < len(parsed) else (end - start).total_seconds() / 60
        segment_end = min(end, start + timedelta(minutes=next_offset))
        if segment_end > start + timedelta(minutes=offset):
            result.append(SleepSegment(start + timedelta(minutes=offset), segment_end, state))
    return tuple(result)


def canonicalize_sleep_record(record: Mapping[str, Any], *, default_timezone: str | None = "system") -> CanonicalSleepRecord | None:
    try:
        day = date.fromisoformat(str(record.get("sleep_date") or record.get("date")))
    except (TypeError, ValueError):
        return None
    start = _parse_datetime(_field(record, "sleep_start_time"), day)
    end = _parse_datetime(_field(record, "wake_time"), day)
    if not start or not end:
        return None
    if start.tzinfo is None and end.tzinfo is not None:
        start = start.replace(tzinfo=end.tzinfo)
    if end.tzinfo is None and start.tzinfo is not None:
        end = end.replace(tzinfo=start.tzinfo)
    if end <= start:
        end += timedelta(days=1)
    actual = _duration_minutes(_field(record, "actual_sleep_duration_minutes"))
    if actual is None:
        return None
    timezone_name = record.get("timezone") or (str(start.tzinfo) if start.tzinfo else default_timezone)
    return CanonicalSleepRecord(
        sleep_date=day,
        sleep_start=start,
        sleep_end=end,
        actual_sleep_duration=actual,
        source=str(record.get("source") or "resolved_sleep"),
        source_record_id=str(record.get("source_record_id") or record.get("manual_record_id") or record.get("date")),
        timezone=timezone_name,
        sleep_segments=_segments(record, start, end),
        completeness=1.0 if actual is not None else 0.0,
        quality="observed",
    )


def validate_sleep_record(record: CanonicalSleepRecord | None) -> tuple[bool, str | None]:
    if record is None:
        return False, "incomplete_record"
    if not record.timezone:
        return False, "timezone_unknown"
    interval = (record.sleep_end - record.sleep_start).total_seconds() / 60
    if interval <= 0:
        return False, "invalid_interval"
    if not CONFIG["interval_min_minutes"] <= interval <= CONFIG["interval_max_minutes"]:
        return False, "implausible_duration"
    if not 0 < record.actual_sleep_duration <= min(interval, CONFIG["actual_max_minutes"]):
        return False, "implausible_duration"
    if record.quality in {"source_error", "parse_error"}:
        return False, "source_error"
    return True, None


def sleep_record_exclusion_reason(record: Mapping[str, Any]) -> str | None:
    """Return a stable exclusion code before a raw mapping is canonicalized."""
    try:
        day = date.fromisoformat(str(record.get("sleep_date") or record.get("date")))
    except (AttributeError, TypeError, ValueError):
        return "incomplete_record"
    if _parse_datetime(_field(record, "sleep_start_time"), day) is None:
        return "missing_bedtime"
    if _parse_datetime(_field(record, "wake_time"), day) is None:
        return "missing_wake_time"
    if _duration_minutes(_field(record, "actual_sleep_duration_minutes")) is None:
        return "incomplete_record"
    canonical = canonicalize_sleep_record(record)
    valid, reason = validate_sleep_record(canonical)
    return None if valid else reason


def is_valid_sleep_record(record: CanonicalSleepRecord | None) -> bool:
    return validate_sleep_record(record)[0]


def _dedupe(records: Iterable[CanonicalSleepRecord]) -> list[CanonicalSleepRecord]:
    selected: dict[date, CanonicalSleepRecord] = {}
    for record in records:
        if not is_valid_sleep_record(record):
            continue
        current = selected.get(record.sleep_date)
        if current is None or (len(record.sleep_segments), record.completeness) > (len(current.sleep_segments), current.completeness):
            selected[record.sleep_date] = record
    return sorted(selected.values(), key=lambda item: item.sleep_date)


def select_valid_sleep_records(records: Iterable[Mapping[str, Any] | CanonicalSleepRecord], *, window_nights: int | None = None) -> list[CanonicalSleepRecord]:
    canonical = []
    for record in records:
        if isinstance(record, CanonicalSleepRecord):
            canonical.append(record)
            continue
        try:
            canonical.append(canonicalize_sleep_record(record))
        except (AttributeError, TypeError, ValueError):
            canonical.append(None)
    valid = _dedupe(record for record in canonical if record is not None)
    return valid[-(window_nights or len(valid)):]


def determine_maturity(valid_nights: int) -> str:
    if valid_nights < CONFIG["minimum_score_nights"]:
        return "collecting"
    if valid_nights < CONFIG["reliable_nights"]:
        return "provisional"
    if valid_nights < CONFIG["stable_nights"]:
        return "reliable"
    return "stable"


def map_score_to_status(score: float | None, maturity_status: str = "reliable") -> str:
    if maturity_status == "collecting":
        return "collecting"
    if score is None:
        return "unavailable"
    if score >= 85:
        return "very_regular"
    if score >= 70:
        return "regular"
    if score >= 55:
        return "variable"
    if score >= 40:
        return "low_regularity"
    return "irregular"


def _confidence(maturity: str, completeness: float, *, sri: bool = False) -> float:
    base = {"collecting": 0.0, "provisional": 0.55, "reliable": 0.80, "stable": 0.95}[maturity]
    return round(min(1.0, base * max(0.0, min(1.0, completeness)) * (0.9 if sri else 1.0)), 3)


def _component_score(variability: float | None, threshold: float) -> float | None:
    if variability is None:
        return None
    return max(0.0, min(100.0, 100.0 * math.exp(-math.log(2) * (variability / threshold) ** 2)))


def calculate_summary_score(records: Iterable[CanonicalSleepRecord], *, maturity_status: str | None = None) -> SleepRegularityResult:
    records = list(records)
    count = len(records)
    maturity = maturity_status or determine_maturity(count)
    completeness = count / max(CONFIG["window_nights"], 1)
    if count < CONFIG["minimum_score_nights"]:
        return SleepRegularityResult("insufficient_data", None, "collecting", maturity, _confidence(maturity, completeness), count, CONFIG["minimum_score_nights"], completeness, explanation="基线建立中")
    bedtimes = [_clock_minutes(item.sleep_start) for item in records]
    wake_times = [_clock_minutes(item.sleep_end) for item in records]
    durations = [item.actual_sleep_duration for item in records]
    bedtime_center = calculate_circular_center(bedtimes)
    wake_center = calculate_circular_center(wake_times)
    duration_center = statistics.median(durations)
    bedtime_mad = calculate_circular_mad(bedtimes, bedtime_center)
    wake_mad = calculate_circular_mad(wake_times, wake_center)
    duration_mad = statistics.median(abs(value - duration_center) for value in durations)
    components = {
        "bedtime": _component_score(bedtime_mad, CONFIG["thresholds_minutes"]["bedtime"]),
        "wake_time": _component_score(wake_mad, CONFIG["thresholds_minutes"]["wake_time"]),
        "duration": _component_score(duration_mad, CONFIG["thresholds_minutes"]["duration"]),
    }
    score = sum(components[name] * weight for name, weight in CONFIG["weights"].items() if components[name] is not None)
    status = map_score_to_status(score, maturity)
    return SleepRegularityResult(
        "summary_composite", score, status, maturity, _confidence(maturity, completeness), count, CONFIG["minimum_score_nights"], completeness,
        components, "近14天作息稳定性", details={"bedtime_center": bedtime_center, "wake_time_center": wake_center, "duration_center": duration_center, "bedtime_variability_minutes": bedtime_mad, "wake_time_variability_minutes": wake_mad, "duration_variability_minutes": duration_mad},
    )


def _timeline_map(records: Iterable[CanonicalSleepRecord]) -> dict[tuple[date, int], str]:
    result: dict[tuple[date, int], str] = {}
    for record in records:
        cursor = record.sleep_start.replace(second=0, microsecond=0)
        end = record.sleep_end.replace(second=0, microsecond=0)
        while cursor < end:
            state = "unknown"
            for segment in record.sleep_segments:
                if segment.start <= cursor < segment.end:
                    state = segment.state
                    break
            if state != "unknown":
                result[(cursor.date(), cursor.hour * 60 + cursor.minute)] = state
            cursor += timedelta(minutes=1)
    return result


def calculate_sri(records: Iterable[CanonicalSleepRecord], *, maturity_status: str | None = None) -> SleepRegularityResult:
    records = list(records)
    maturity = maturity_status or determine_maturity(len(records))
    timeline_records = [record for record in records if len(record.sleep_segments) >= 2]
    if len(timeline_records) < CONFIG["minimum_score_nights"]:
        return calculate_summary_score(records, maturity_status=maturity)
    state_map = _timeline_map(timeline_records)
    dates = sorted({record.sleep_date for record in timeline_records})
    comparable = matching = pairs = 0
    possible = max(1, (len(dates) - 1) * 1440)
    for current in dates:
        next_day = current + timedelta(days=1)
        pair_minutes = 0
        for minute in range(1440):
            left = state_map.get((current, minute))
            right = state_map.get((next_day, minute))
            if left in {"asleep", "awake"} and right in {"asleep", "awake"}:
                comparable += 1
                pair_minutes += 1
                matching += int(left == right)
        if pair_minutes >= CONFIG["sri_min_pair_minutes"]:
            pairs += 1
    coverage = comparable / possible
    if comparable == 0 or coverage < CONFIG["sri_min_coverage"] or pairs < 2:
        return calculate_summary_score(records, maturity_status=maturity)
    score = matching / comparable * 100
    return SleepRegularityResult(
        "sri_timeline", score, map_score_to_status(score, maturity), maturity,
        _confidence(maturity, coverage, sri=True), len(records), CONFIG["minimum_score_nights"], coverage,
        {"sri": score}, "近14天睡眠/清醒时间线一致性",
        details={"comparable_minutes": comparable, "matching_minutes": matching, "missing_minutes": possible - comparable, "coverage_ratio": coverage, "valid_day_pairs": pairs},
    )


def calculate_rolling_regularity_scores(
    records: Iterable[Mapping[str, Any] | CanonicalSleepRecord],
    *,
    window_nights: int | None = None,
) -> dict[date, float | None]:
    """Calculate overlapping regularity windows without rebuilding each timeline.

    Baseline charts need one score for many adjacent dates. Their SRI windows
    overlap almost completely, so build each night's state timeline once and
    reuse the adjacent-day comparisons for every window.
    """
    window = window_nights or CONFIG["window_nights"]
    valid = select_valid_sleep_records(records)
    timeline_records = [record for record in valid if len(record.sleep_segments) >= 2]
    timeline_dates = {record.sleep_date for record in timeline_records}
    state_map = _timeline_map(timeline_records)
    pair_stats: dict[date, tuple[int, int, int]] = {}
    for current in sorted(timeline_dates):
        next_day = current + timedelta(days=1)
        if next_day not in timeline_dates:
            continue
        comparable = matching = 0
        for minute in range(1440):
            left = state_map.get((current, minute))
            right = state_map.get((next_day, minute))
            if left in {"asleep", "awake"} and right in {"asleep", "awake"}:
                comparable += 1
                matching += int(left == right)
        pair_stats[current] = (
            comparable,
            matching,
            int(comparable >= CONFIG["sri_min_pair_minutes"]),
        )

    scores: dict[date, float | None] = {}
    for end_index, record in enumerate(valid):
        rolling = valid[max(0, end_index - window + 1):end_index + 1]
        has_timeline = sum(len(item.sleep_segments) >= 2 for item in rolling) >= CONFIG["minimum_score_nights"]
        if not has_timeline:
            scores[record.sleep_date] = calculate_summary_score(rolling).score
            continue
        dates = sorted(item.sleep_date for item in rolling if item.sleep_date in timeline_dates)
        comparable = matching = pairs = 0
        date_set = set(dates)
        for current in dates:
            if current + timedelta(days=1) not in date_set:
                continue
            pair_comparable, pair_matching, pair_is_valid = pair_stats.get(current, (0, 0, 0))
            comparable += pair_comparable
            matching += pair_matching
            pairs += pair_is_valid
        possible = max(1, (len(dates) - 1) * 1440)
        coverage = comparable / possible
        scores[record.sleep_date] = (
            matching / comparable * 100
            if comparable and coverage >= CONFIG["sri_min_coverage"] and pairs >= 2
            else calculate_summary_score(rolling).score
        )
    return scores


def calculate_last_night_deviation(current: Mapping[str, Any] | CanonicalSleepRecord, records: Iterable[Mapping[str, Any] | CanonicalSleepRecord]) -> LastNightScheduleDeviation:
    target = current if isinstance(current, CanonicalSleepRecord) else canonicalize_sleep_record(current)
    if target is None:
        return LastNightScheduleDeviation(None, None, None, None, None, None, None, 0.0)
    prior = [item for item in select_valid_sleep_records(records) if item.sleep_date < target.sleep_date]
    prior = prior[-CONFIG["window_nights"]:]
    if not prior:
        return LastNightScheduleDeviation(None, None, None, None, None, None, None, 0.0)
    bedtime = calculate_circular_center(_clock_minutes(item.sleep_start) for item in prior)
    wake = calculate_circular_center(_clock_minutes(item.sleep_end) for item in prior)
    duration = statistics.median(item.actual_sleep_duration for item in prior)
    bedtime_delta = signed_circular_difference_minutes(_clock_minutes(target.sleep_start), bedtime)
    wake_delta = signed_circular_difference_minutes(_clock_minutes(target.sleep_end), wake)
    duration_delta = target.actual_sleep_duration - duration
    values = {"bedtime": abs(bedtime_delta), "wake_time": abs(wake_delta), "duration": abs(duration_delta)}
    dominant = max(values, key=values.get) if values else None
    return LastNightScheduleDeviation(bedtime, wake, duration, bedtime_delta, wake_delta, duration_delta, dominant, min(1.0, len(prior) / CONFIG["reliable_nights"]))


class SleepRegularityService:
    """Application service used by the dashboard and future data adapters."""

    @staticmethod
    def calculate_regularity(records: Iterable[Mapping[str, Any] | CanonicalSleepRecord], current: Mapping[str, Any] | CanonicalSleepRecord | None = None) -> SleepRegularityResult:
        try:
            source = list(records)
            if current is not None:
                source.append(current)
            valid = select_valid_sleep_records(source, window_nights=CONFIG["window_nights"])
            maturity = determine_maturity(len(valid))
            if len(valid) < CONFIG["minimum_score_nights"]:
                return calculate_summary_score(valid, maturity_status=maturity)
            has_timeline = sum(len(item.sleep_segments) >= 2 for item in valid) >= CONFIG["minimum_score_nights"]
            return calculate_sri(valid, maturity_status=maturity) if has_timeline else calculate_summary_score(valid, maturity_status=maturity)
        except Exception:
            return SleepRegularityResult("unavailable", None, "unavailable", "unavailable", 0.0, 0, CONFIG["minimum_score_nights"], 0.0, explanation="睡眠数据暂不完整")

    @staticmethod
    def calculate_sri(records):
        return calculate_sri(select_valid_sleep_records(records))

    @staticmethod
    def calculate_summary_score(records):
        return calculate_summary_score(select_valid_sleep_records(records))

    @staticmethod
    def calculate_last_night_deviation(current, records):
        return calculate_last_night_deviation(current, records)

    @staticmethod
    def select_valid_sleep_records(records):
        return select_valid_sleep_records(records)

    @staticmethod
    def determine_maturity(valid_nights):
        return determine_maturity(valid_nights)

    @staticmethod
    def map_score_to_status(score, maturity_status="reliable"):
        return map_score_to_status(score, maturity_status)


def calculate_regularity(records, current=None) -> SleepRegularityResult:
    """Functional entry point for callers that do not need the service class."""
    return SleepRegularityService.calculate_regularity(records, current=current)
