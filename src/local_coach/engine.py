"""Coordinator and CLI for Local Deterministic Coach v1.0."""

import argparse
import json
import sqlite3

from ..db import connect, get_current_db_path
from .config import load_rules, validate_output
from .explanation import build_rationale
from .hydration import generate_hydration_advice
from .nutrition import generate_nutrition_advice
from .recovery import generate_recovery_advice
from .safety import apply_safety_fallback
from .sleep import generate_sleep_advice
from .storage import ENGINE_VERSION, available_dates, latest_date, load_input, upsert_recommendation
from .training import build_training_summary, generate_training_advice


def generate_recommendation(data, rules=None, symptoms=None):
    rules = rules or load_rules()
    output = {
        "date": data.date, **generate_training_advice(data, rules),
        "sleep_advice": generate_sleep_advice(data, rules),
        "hydration_advice": generate_hydration_advice(data, rules),
        "nutrition_advice": generate_nutrition_advice(data, rules),
        "recovery_advice": generate_recovery_advice(data, rules),
        "data_limitations": (["睡眠证据缺失。"] if data.sleep_duration_hours is None and data.sleep_score is None else [])
                            + (["个人基线状态不可用。"] if not data.baseline_status else []),
        "safety_notices": [], "rationale": build_rationale(data), "engine_version": ENGINE_VERSION,
        "rule_config_version": rules["rule_config_version"], "generated_without_cloud_ai": True,
        "is_historical": data.is_historical, "freshness_days": data.freshness_days,
    }
    apply_safety_fallback(data, output, rules, symptoms=symptoms)
    output["training_summary"] = build_training_summary(
        data, rules, {
            "morning_training": output["morning_training"],
            "evening_training": output["evening_training"],
        },
    )
    return validate_output(output)


def run_local_coach(connection=None, coach_date=None, all_dates=False, dry_run=False,
                    today=None):
    owns_connection = connection is None
    if connection is None:
        if dry_run:
            db_path = get_current_db_path()
            connection = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
        else:
            connection = connect()
    try:
        dates = available_dates(connection) if all_dates else [coach_date or latest_date(connection)]
        dates = [value for value in dates if value]
        if not dates:
            raise ValueError("No recovery dates are available for Local Coach")
        rules, outputs = load_rules(), []
        for value in dates:
            output = generate_recommendation(
                load_input(
                    connection, value, today=today,
                    freshness_days=rules["freshness_days"],
                ),
                rules,
            )
            outputs.append(output)
            if not dry_run:
                upsert_recommendation(connection, output)
        if not dry_run:
            connection.commit()
        statuses = {}
        for output in outputs:
            status = output["morning_training"]["status"]
            statuses[status] = statuses.get(status, 0) + 1
        return {"local_coach_records_updated": 0 if dry_run else len(outputs), "records_validated": len(outputs),
                "historical_records": sum(item["is_historical"] for item in outputs),
                "morning_status_counts": statuses, "dry_run": dry_run}
    finally:
        if owns_connection:
            connection.close()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Generate local deterministic coaching advice.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--date", dest="coach_date")
    group.add_argument("--all", action="store_true", dest="all_dates")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    print(json.dumps(run_local_coach(coach_date=args.coach_date, all_dates=args.all_dates, dry_run=args.dry_run),
                     ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
