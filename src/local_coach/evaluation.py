"""Read-only longitudinal evaluation for Local Deterministic Coach outputs."""

import argparse
import json
import sqlite3
from datetime import date
from pathlib import Path

from ..db import get_current_db_path
from .config import LocalCoachConfigError, load_rules, validate_output
from .engine import generate_recommendation
from .safety import DISCLAIMER
from .storage import load_input, load_recommendation


BASE_DIR = Path(__file__).resolve().parents[2]
EVALUATION_PATH = BASE_DIR / "config" / "local_coach_evaluation.json"
PERSISTED_OUTPUT_KEYS = (
    "date", "morning_training", "evening_training", "training_summary", "sleep_advice",
    "hydration_advice", "nutrition_advice", "recovery_advice", "rationale",
    "data_limitations", "safety_notices", "engine_version",
    "rule_config_version", "generated_without_cloud_ai",
)


def load_evaluation_config(path=EVALUATION_PATH):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalCoachConfigError("Unable to load Local Coach evaluation config") from exc
    required = {
        "evaluation_version", "minimum_records", "required_schema_pass_rate",
        "required_deterministic_match_rate", "required_no_cloud_marker_rate",
        "required_safety_notice_rate", "maximum_duplicate_keys",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise LocalCoachConfigError("Local Coach evaluation fields do not match authority")
    if value["evaluation_version"] != "1.0.0":
        raise LocalCoachConfigError("Unsupported Local Coach evaluation version")
    if not isinstance(value["minimum_records"], int) or value["minimum_records"] < 1:
        raise LocalCoachConfigError("minimum_records must be positive")
    for key in required:
        if key.startswith("required_") and not 0 <= value[key] <= 1:
            raise LocalCoachConfigError(f"Invalid evaluation rate: {key}")
    if not isinstance(value["maximum_duplicate_keys"], int) or value["maximum_duplicate_keys"] < 0:
        raise LocalCoachConfigError("maximum_duplicate_keys must be non-negative")
    return value


def _rate(count, total):
    return round(count / total, 4) if total else 0.0


def _selected_dates(connection, date_from=None, date_to=None):
    clauses, parameters = [], []
    if date_from:
        date.fromisoformat(date_from)
        clauses.append("date >= ?")
        parameters.append(date_from)
    if date_to:
        date.fromisoformat(date_to)
        clauses.append("date <= ?")
        parameters.append(date_to)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return [row[0] for row in connection.execute(
        "SELECT DISTINCT date FROM local_coach_recommendations" + where + " ORDER BY date",
        parameters,
    )]


def evaluate_longitudinal(connection=None, *, date_from=None, date_to=None,
                          today=None, evaluation_config=None):
    """Evaluate stored advice without writes or raw-health output."""
    owns_connection = connection is None
    if connection is None:
        db_path = get_current_db_path()
        connection = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
    config = evaluation_config or load_evaluation_config()
    rules = load_rules()
    current_day = today or date.today()
    try:
        try:
            dates = _selected_dates(connection, date_from, date_to)
            duplicate_keys = connection.execute(
                """SELECT COUNT(*) FROM (
                    SELECT date, engine_version FROM local_coach_recommendations
                    GROUP BY date, engine_version HAVING COUNT(*) > 1
                )"""
            ).fetchone()[0]
        except sqlite3.OperationalError:
            dates, duplicate_keys = [], 0

        schema_pass = deterministic_matches = no_cloud = safety_notice = 0
        invalid_records = []
        morning_status_counts, transitions = {}, {}
        previous_status = None
        historical = 0
        for coach_date in dates:
            try:
                stored = load_recommendation(connection, coach_date)
                if not stored:
                    raise ValueError("missing stored recommendation")
                freshness = max((current_day - date.fromisoformat(coach_date)).days, 0)
                candidate = {key: stored[key] for key in PERSISTED_OUTPUT_KEYS}
                candidate.update(is_historical=freshness > rules["freshness_days"], freshness_days=freshness)
                validate_output(candidate)
                schema_pass += 1
                historical += int(candidate["is_historical"])
                no_cloud += int(candidate["generated_without_cloud_ai"] is True)
                safety_notice += int(DISCLAIMER in candidate["safety_notices"])
                regenerated = generate_recommendation(
                    load_input(connection, coach_date, today=current_day,
                               freshness_days=rules["freshness_days"]), rules
                )
                if all(candidate[key] == regenerated[key] for key in PERSISTED_OUTPUT_KEYS):
                    deterministic_matches += 1
                status = candidate["morning_training"]["status"]
                morning_status_counts[status] = morning_status_counts.get(status, 0) + 1
                if previous_status is not None:
                    transition = f"{previous_status}->{status}"
                    transitions[transition] = transitions.get(transition, 0) + 1
                previous_status = status
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, LocalCoachConfigError):
                invalid_records.append(coach_date)

        total = len(dates)
        rates = {
            "schema_pass_rate": _rate(schema_pass, total),
            "deterministic_match_rate": _rate(deterministic_matches, total),
            "no_cloud_marker_rate": _rate(no_cloud, total),
            "safety_notice_rate": _rate(safety_notice, total),
        }
        checks = {
            "minimum_records": total >= config["minimum_records"],
            "schema_valid": rates["schema_pass_rate"] >= config["required_schema_pass_rate"],
            "deterministic_match": rates["deterministic_match_rate"] >= config["required_deterministic_match_rate"],
            "no_cloud_markers": rates["no_cloud_marker_rate"] >= config["required_no_cloud_marker_rate"],
            "safety_notices": rates["safety_notice_rate"] >= config["required_safety_notice_rate"],
            "duplicate_keys": duplicate_keys <= config["maximum_duplicate_keys"],
        }
        return {
            "evaluation_version": config["evaluation_version"],
            "success": all(checks.values()), "record_count": total,
            "earliest_date": dates[0] if dates else None, "latest_date": dates[-1] if dates else None,
            "historical_record_count": historical, "invalid_record_count": len(invalid_records),
            "duplicate_key_count": duplicate_keys, **rates, "checks": checks,
            "blockers": [name for name, passed in checks.items() if not passed],
            "morning_status_counts": morning_status_counts,
            "morning_status_transitions": transitions,
            "generated_without_cloud_ai": True,
        }
    finally:
        if owns_connection:
            connection.close()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate Local Coach longitudinal consistency read-only.")
    parser.add_argument("--from", dest="date_from")
    parser.add_argument("--to", dest="date_to")
    parser.add_argument("--require-pass", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    result = evaluate_longitudinal(date_from=args.date_from, date_to=args.date_to)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.require_pass and not result["success"]:
        raise SystemExit(1)
    return result


if __name__ == "__main__":
    main()
