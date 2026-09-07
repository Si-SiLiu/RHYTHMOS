import argparse
from datetime import date, timedelta

try:
    from .polar_client import (
        PolarAPIError,
        PolarClient,
        PolarClientError,
        RAW_DIR,
        safe_error_payload,
        save_raw_json,
    )
except ImportError:
    from polar_client import (
        PolarAPIError,
        PolarClient,
        PolarClientError,
        RAW_DIR,
        safe_error_payload,
        save_raw_json,
    )


def parse_args():
    default_to = date.today()
    default_from = default_to - timedelta(days=27)

    parser = argparse.ArgumentParser(description="Fetch raw Polar AccessLink data.")
    parser.add_argument("--from", dest="from_date", default=default_from.isoformat())
    parser.add_argument("--to", dest="to_date", default=default_to.isoformat())
    parser.add_argument("--exercise-samples", action="store_true")
    parser.add_argument("--exercise-zones", action="store_true")
    parser.add_argument("--exercise-route", action="store_true")
    parser.add_argument("--activity-steps", action="store_true")
    parser.add_argument("--activity-zones", action="store_true")
    parser.add_argument("--inactivity-stamps", action="store_true")
    return parser.parse_args()


def fetch_and_save_result(label, filename, fetcher, *, preserve_existing_on_error=False):
    try:
        data = fetcher()
    except PolarAPIError as exc:
        existing = RAW_DIR / filename
        path = (
            existing
            if preserve_existing_on_error and existing.is_file()
            else save_raw_json(filename, safe_error_payload(exc))
        )
        print(f"{label}: HTTP {exc.status_code}, saved {path}")
        return {
            "ok": False,
            "data": None,
            "status_code": exc.status_code,
            "path": str(path),
        }

    path = save_raw_json(filename, data)
    count = len(data) if isinstance(data, list) else 1 if data else 0
    print(f"{label}: {count} item(s), saved {path}")
    return {
        "ok": True,
        "data": data,
        "status_code": None,
        "path": str(path),
    }


def fetch_and_save(label, filename, fetcher):
    """Backward-compatible raw data return for existing callers."""
    return fetch_and_save_result(label, filename, fetcher)["data"]


def _container_items(payload, *container_keys):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in container_keys:
        value = payload
        for part in key.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
    return []


def sleep_dates(payload):
    dates = []
    for item in _container_items(payload, "nightSleeps", "nights", "sleeps", "sleep"):
        if not isinstance(item, dict):
            continue
        value = item.get("sleepDate") or item.get("date")
        if value and str(value) not in dates:
            dates.append(str(value))
    return dates


def _bounded_date_ranges(from_date=None, to_date=None, *, max_span_days):
    """Split an inclusive Polar date range into API-supported spans.

    Polar validates the difference between the two date arguments rather than
    the number of calendar dates.  A 28-day maximum therefore permits both
    endpoints to receive ``start`` through ``start + 28 days`` inclusively.
    """
    if not from_date or not to_date:
        return [(from_date, to_date)]
    start = date.fromisoformat(str(from_date)[:10])
    end = date.fromisoformat(str(to_date)[:10])
    if start > end:
        return [(from_date, to_date)]

    ranges = []
    while start <= end:
        chunk_end = min(start + timedelta(days=max_span_days), end)
        ranges.append((start.isoformat(), chunk_end.isoformat()))
        start = chunk_end + timedelta(days=1)
    return ranges


def fetch_sleep_details(client, from_date=None, to_date=None, ensure_date=None):
    """Expand the v4 sleep date listing into complete per-night records."""
    dates = []
    # The v4 sleeps endpoint accepts at most a 30-day range. Keep one day of
    # headroom so this and Nightly Recharge use the same safe range policy.
    for chunk_from, chunk_to in _bounded_date_ranges(
        from_date, to_date, max_span_days=28,
    ):
        listing = client.get_sleep(from_date=chunk_from, to_date=chunk_to)
        for date_value in sleep_dates(listing):
            if date_value not in dates:
                dates.append(date_value)
    if ensure_date and str(ensure_date) not in dates:
        dates.append(str(ensure_date))
    if not dates:
        return listing

    nights = []
    for date_value in dates:
        try:
            detail = client.get_sleep_for_date(date_value)
        except PolarAPIError as exc:
            if exc.status_code == 404:
                continue
            raise
        items = _container_items(detail, "nightSleeps", "nightSleep", "nights", "sleep")
        if not items and isinstance(detail, dict) and (
            detail.get("sleepDate") or detail.get("date")
        ):
            items = [detail]
        nights.extend(item for item in items if isinstance(item, dict))
    return {"nightSleeps": nights}


def _nightly_recharge_items(payload):
    items = _container_items(
        payload,
        "nightlyRechargeResults.nightlyRechargeResults",
        "nightlyRechargeResults",
        "recharges",
        "nightly_recharge_results",
    )
    if not items and isinstance(payload, dict) and (
        payload.get("sleepResultDate") or payload.get("date")
    ):
        items = [payload]
    return [item for item in items if isinstance(item, dict)]


def _nightly_recharge_date(item):
    value = item.get("sleepResultDate") or item.get("date")
    return str(value) if value else None


def fetch_nightly_recharge_with_samples(
    client, from_date=None, to_date=None, sample_dates=None,
):
    """Fetch range summaries, then merge samples fetched one exclusive day at a time."""
    grouped = {}
    # Polar's Nightly Recharge range endpoint permits a maximum 28-day
    # difference between from/to, so history has to be fetched in segments.
    for chunk_from, chunk_to in _bounded_date_ranges(
        from_date, to_date, max_span_days=28,
    ):
        listing = client.get_nightly_recharge(
            from_date=chunk_from, to_date=chunk_to, samples=False,
        )
        for item in _nightly_recharge_items(listing):
            item_date = _nightly_recharge_date(item)
            if item_date:
                grouped[item_date] = dict(item)

    dates = set(grouped)
    dates.update(str(value) for value in (sample_dates or []) if value)
    for date_value in sorted(dates):
        try:
            next_date = (
                date.fromisoformat(date_value[:10]) + timedelta(days=1)
            ).isoformat()
        except ValueError:
            continue
        try:
            detail = client.get_nightly_recharge(
                from_date=date_value[:10], to_date=next_date, samples=True,
            )
        except PolarAPIError as exc:
            if exc.status_code in (400, 404):
                continue
            raise
        for item in _nightly_recharge_items(detail):
            item_date = _nightly_recharge_date(item) or date_value[:10]
            grouped[item_date] = {**grouped.get(item_date, {}), **item}

    return {
        "nightlyRechargeResults": [
            grouped[key] for key in sorted(grouped)
        ]
    }


def fetch_continuous_heart_rate_for_dates(client, dates):
    """Fetch per-day continuous HR because the v4 range endpoint may be unavailable."""
    grouped = {}
    for date_value in dates:
        try:
            payload = client.get_continuous_heart_rate(date_value=date_value)
        except PolarAPIError as exc:
            if exc.status_code == 404:
                continue
            raise
        items = _container_items(
            payload,
            "continuousSamples.heartRateSamplesPerDay",
            "heartRateSamplesPerDay",
            "days",
        )
        if not items and isinstance(payload, dict) and payload.get("date"):
            items = [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            item_date = str(item.get("date") or date_value)
            current = grouped.get(item_date)
            if current is None or len(item.get("samples") or []) > len(current.get("samples") or []):
                grouped[item_date] = item
    return {
        "heartRateSamplesPerDay": [
            grouped[key] for key in sorted(grouped)
        ]
    }


def main():
    args = parse_args()
    client = PolarClient()

    print("Token: refresh will be attempted" if client.is_token_expired() else "Token: valid")

    fetch_and_save(
        "User account",
        "polar_user_account.json",
        client.get_user_account_info,
    )
    fetch_and_save(
        "Sports",
        "polar_sports.json",
        client.get_sports,
    )
    fetch_and_save(
        "Training sessions",
        "polar_training_sessions.json",
        lambda: client.get_training_sessions(
            from_date=args.from_date,
            to_date=args.to_date,
        ),
    )
    fetch_and_save(
        "Daily activity",
        "polar_daily_activity.json",
        lambda: client.get_daily_activity_v3(
            from_date=args.from_date,
            to_date=args.to_date,
            steps=args.activity_steps,
            activity_zones=args.activity_zones,
            inactivity_stamps=args.inactivity_stamps,
        ),
    )
    sleep_payload = fetch_and_save(
        "Sleep",
        "polar_sleep.json",
        lambda: fetch_sleep_details(
            client, from_date=args.from_date, to_date=args.to_date,
            ensure_date=args.to_date,
        ),
    )
    fetch_and_save(
        "Available sleep",
        "polar_sleep_available.json",
        client.get_available_sleep,
    )
    fetch_and_save(
        "Nightly Recharge",
        "polar_nightly_recharge.json",
        lambda: fetch_nightly_recharge_with_samples(
            client, from_date=args.from_date, to_date=args.to_date,
            sample_dates=sleep_dates(sleep_payload),
        ),
    )
    fetch_and_save(
        "Cardio load",
        "polar_cardio_load.json",
        client.get_cardio_load,
    )
    fetch_and_save(
        "Continuous heart rate",
        "polar_continuous_heart_rate.json",
        lambda: fetch_continuous_heart_rate_for_dates(client, sleep_dates(sleep_payload)),
    )


if __name__ == "__main__":
    try:
        main()
    except PolarClientError as exc:
        raise SystemExit(str(exc))
