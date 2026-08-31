import json
import os
import re
import sqlite3
import subprocess
import sys
import unittest
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
STATE_PATH = Path(
    os.environ.get("PROJECT_STATE_PATH", BASE_DIR / "project_state.json")
)
CURRENT_STATE_PATH = Path(
    os.environ.get(
        "PROJECT_CURRENT_STATE_PATH",
        BASE_DIR / "docs" / "CURRENT_STATE.md",
    )
)
DB_PATH = BASE_DIR / "data" / "recovery.db"
VERSIONS_PATH = BASE_DIR / "config" / "versions.json"
KUBIOS_REAL_EVALUATION_PATH = BASE_DIR / "config" / "kubios_screenshot_real_evaluation.json"
RECOVERY_SOURCE_PATH = BASE_DIR / "src" / "recovery_score.py"
GENERATED_BY = "scripts/update_project_state.py"

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
MODEL_ID_RE = re.compile(r"^[a-z][a-z0-9._-]{0,127}$")
PRIORITIES = {"P0", "P1", "P2", "P3"}
ISSUE_STATUSES = {
    "open",
    "planned",
    "in_progress",
    "blocked",
    "monitoring",
    "awaiting_approval",
    "external_constraint",
}

DEFAULT_METADATA = {
    "current_phase": "Simplified Structured Training Entry UI",
    "phase_status": "completed",
    "prioritized_issues": [
        {
            "priority": "P1",
            "description": "No cloud provider currently satisfies both deployment-region support and verified Zero Data Retention requirements.",
            "status": "blocked",
            "owner": "Product Owner / Chief Architect",
            "target_phase": "Phase 12.1 AI Coach Implementation",
        },
        {
            "priority": "P2",
            "description": "Some recent Polar respiration and Kubios metrics are missing.",
            "status": "monitoring",
            "owner": "Product Owner",
            "target_phase": "Data Quality",
        },
        {
            "priority": "P2",
            "description": "Cardio Load remains unavailable in the latest sync and is surfaced as an optional endpoint warning.",
            "status": "monitoring",
            "owner": "Chief Architect",
            "target_phase": "Recovery Inputs Review",
        },
        {
            "priority": "P2",
            "description": "The next actual 06:00 LaunchAgent run is still pending observation.",
            "status": "monitoring",
            "owner": "Product Owner / Codex",
            "target_phase": "Daily Scheduling Operations",
        },
        {
            "priority": "P3",
            "description": "A Git release tag cannot be created because this workspace is not a Git repository.",
            "status": "external_constraint",
            "owner": "Codex",
            "target_phase": "Future Git repository setup",
        },
    ],
    "next_goal": "Observe real training-entry use and refine catalog metadata without changing training or recovery algorithms.",
}
METADATA_FIELDS = set(DEFAULT_METADATA)

REQUIRED_FIELDS = {
    "app_version",
    "current_phase",
    "phase_status",
    "recovery_engine_version",
    "database_schema_version",
    "dashboard_version",
    "baseline_engine_version",
    "confidence_engine_version",
    "local_coach_engine_version",
    "personal_logging_version",
    "nutrition_logging_engine_version",
    "food_catalog_version",
    "training_logging_version",
    "exercise_catalog_version",
    "training_entry_ui_version",
    "training_entry_default_mode",
    "conditional_training_fields_ready",
    "rpe_rir_preference_supported",
    "simplified_training_entry_ready",
    "structured_training_ready",
    "training_session_count",
    "training_exercise_count",
    "training_set_count",
    "latest_training_detail_date",
    "supplement_unit_system_version",
    "supplement_catalog_version",
    "supplement_product_enrichment_version",
    "brand_based_supplement_logging_ready",
    "supplement_product_count",
    "verified_supplement_product_count",
    "unverified_supplement_product_count",
    "supplement_ingredient_count",
    "latest_supplement_product_update",
    "supplement_enrichment_runtime_status",
    "supplement_dynamic_units_ready",
    "supplement_catalog_count",
    "simple_nutrition_input_ready",
    "food_catalog_count",
    "meal_record_count",
    "meal_item_count",
    "meal_template_count",
    "latest_meal_date",
    "manual_logging_engine_version",
    "data_resolution_version",
    "scheduler_version",
    "ai_context_export_version",
    "i18n_engine_version",
    "kubios_screenshot_import_version",
    "kubios_data_model_version",
    "model_version",
    "scheduled_sync_enabled",
    "scheduled_sync_time",
    "launch_agent_installed",
    "latest_scheduled_sync_at",
    "latest_scheduled_sync_success",
    "manual_activity_count",
    "manual_sleep_count",
    "manual_recovery_count",
    "resolved_field_count",
    "supplement_catalog_count",
    "manual_logging_ready",
    "data_resolution_ready",
    "supported_languages",
    "default_language",
    "current_language",
    "translation_key_count",
    "translation_coverage",
    "language_setting_ready",
    "kubios_screenshot_count",
    "kubios_screenshot_imported_count",
    "kubios_screenshot_review_pending_count",
    "latest_kubios_screenshot_import_date",
    "local_ocr_ready",
    "real_kubios_screenshot_verified",
    "kubios_raw_measurement_count",
    "kubios_normalized_count",
    "kubios_derived_count",
    "latest_kubios_measurement_date",
    "kubios_core_metrics_ready",
    "kubios_advanced_metrics_ready",
    "test_total",
    "test_passed",
    "test_failed",
    "test_success",
    "baseline_record_count",
    "scored_day_count",
    "recovery_v1_day_count",
    "daily_metric_day_count",
    "earliest_data_date",
    "latest_data_date",
    "table_record_counts",
    "schema_migration_count",
    "latest_schema_migration",
    "confidence_record_count",
    "local_coach_record_count",
    "latest_local_coach_date",
    "local_coach_ready",
    "cloud_ai_runtime_ready",
    "body_measurement_count",
    "nutrition_log_count",
    "workout_session_count",
    "exercise_set_count",
    "ai_context_export_count",
    "latest_body_measurement_date",
    "latest_nutrition_log_date",
    "latest_manual_workout_date",
    "manual_chatgpt_sync_ready",
    "automatic_cloud_sync_ready",
    "prospective_evaluation_eligible_days",
    "prospective_evaluation_target_days",
    "prospective_evaluation_remaining_days",
    "prospective_evaluation_status",
    "prospective_evaluation_ready",
    "daily_collection_status",
    "daily_collection_on_track",
    "today_collection_completed",
    "current_collection_streak_days",
    "overdue_collection_days",
    "latest_source_data_date",
    "source_data_lag_days",
    "database_aligned_with_source",
    "today_source_data_available",
    "prospective_collection_blocker",
    "known_issues",
    "prioritized_issues",
    "next_goal",
    "updated_at",
    "generated_by",
}

CURRENT_STATE_KEYS = {
    "App Version": "app_version",
    "Current Phase": "current_phase",
    "Phase Status": "phase_status",
    "Recovery Engine Version": "recovery_engine_version",
    "Baseline Engine Version": "baseline_engine_version",
    "Confidence Engine Version": "confidence_engine_version",
    "Local Coach Engine Version": "local_coach_engine_version",
    "Personal Logging Version": "personal_logging_version",
    "Nutrition Logging Engine Version": "nutrition_logging_engine_version",
    "Food Catalog Version": "food_catalog_version",
    "Training Logging Version": "training_logging_version",
    "Exercise Catalog Version": "exercise_catalog_version",
    "Training Entry UI Version": "training_entry_ui_version",
    "Training Entry Default Mode": "training_entry_default_mode",
    "Conditional Training Fields Ready": "conditional_training_fields_ready",
    "RPE RIR Preference Supported": "rpe_rir_preference_supported",
    "Simplified Training Entry Ready": "simplified_training_entry_ready",
    "Structured Training Ready": "structured_training_ready",
    "Training Session Count": "training_session_count",
    "Training Exercise Count": "training_exercise_count",
    "Training Set Count": "training_set_count",
    "Latest Training Detail Date": "latest_training_detail_date",
    "Supplement Unit System Version": "supplement_unit_system_version",
    "Supplement Catalog Version": "supplement_catalog_version",
    "Supplement Product Enrichment Version": "supplement_product_enrichment_version",
    "Brand Based Supplement Logging Ready": "brand_based_supplement_logging_ready",
    "Supplement Product Count": "supplement_product_count",
    "Verified Supplement Product Count": "verified_supplement_product_count",
    "Unverified Supplement Product Count": "unverified_supplement_product_count",
    "Supplement Ingredient Count": "supplement_ingredient_count",
    "Latest Supplement Product Update": "latest_supplement_product_update",
    "Supplement Enrichment Runtime Status": "supplement_enrichment_runtime_status",
    "Supplement Dynamic Units Ready": "supplement_dynamic_units_ready",
    "Supplement Catalog Count": "supplement_catalog_count",
    "Simple Nutrition Input Ready": "simple_nutrition_input_ready",
    "Food Catalog Count": "food_catalog_count",
    "Meal Record Count": "meal_record_count",
    "Meal Item Count": "meal_item_count",
    "Meal Template Count": "meal_template_count",
    "Latest Meal Date": "latest_meal_date",
    "Manual Logging Engine Version": "manual_logging_engine_version",
    "Data Resolution Version": "data_resolution_version",
    "Scheduler Version": "scheduler_version",
    "Scheduled Sync Enabled": "scheduled_sync_enabled",
    "Scheduled Sync Time": "scheduled_sync_time",
    "LaunchAgent Installed": "launch_agent_installed",
    "Latest Scheduled Sync At": "latest_scheduled_sync_at",
    "Latest Scheduled Sync Success": "latest_scheduled_sync_success",
    "Manual Activity Count": "manual_activity_count",
    "Manual Sleep Count": "manual_sleep_count",
    "Manual Recovery Count": "manual_recovery_count",
    "Resolved Field Count": "resolved_field_count",
    "Manual Logging Ready": "manual_logging_ready",
    "Data Resolution Ready": "data_resolution_ready",
    "AI Context Export Version": "ai_context_export_version",
    "i18n Engine Version": "i18n_engine_version",
    "Kubios Screenshot Import Version": "kubios_screenshot_import_version",
    "Kubios Data Model Version": "kubios_data_model_version",
    "Database Schema Version": "database_schema_version",
    "Schema Migration Count": "schema_migration_count",
    "Latest Schema Migration": "latest_schema_migration",
    "Dashboard Version": "dashboard_version",
    "Default Language": "default_language",
    "Current Language": "current_language",
    "Translation Key Count": "translation_key_count",
    "Translation Coverage": "translation_coverage",
    "Language Setting Ready": "language_setting_ready",
    "Kubios Screenshot Count": "kubios_screenshot_count",
    "Kubios Screenshot Imported Count": "kubios_screenshot_imported_count",
    "Kubios Screenshot Review Pending Count": "kubios_screenshot_review_pending_count",
    "Latest Kubios Screenshot Import Date": "latest_kubios_screenshot_import_date",
    "Local OCR Ready": "local_ocr_ready",
    "Real Kubios Screenshot Verified": "real_kubios_screenshot_verified",
    "Kubios Raw Measurement Count": "kubios_raw_measurement_count",
    "Kubios Normalized Count": "kubios_normalized_count",
    "Kubios Derived Count": "kubios_derived_count",
    "Latest Kubios Measurement Date": "latest_kubios_measurement_date",
    "Kubios Core Metrics Ready": "kubios_core_metrics_ready",
    "Kubios Advanced Metrics Ready": "kubios_advanced_metrics_ready",
    "Test Total": "test_total",
    "Test Passed": "test_passed",
    "Test Failed": "test_failed",
    "Test Success": "test_success",
    "Baseline Record Count": "baseline_record_count",
    "Scored Day Count": "scored_day_count",
    "Recovery v1 Day Count": "recovery_v1_day_count",
    "Confidence Record Count": "confidence_record_count",
    "Local Coach Record Count": "local_coach_record_count",
    "Latest Local Coach Date": "latest_local_coach_date",
    "Local Coach Ready": "local_coach_ready",
    "Cloud AI Runtime Ready": "cloud_ai_runtime_ready",
    "Body Measurement Count": "body_measurement_count",
    "Nutrition Log Count": "nutrition_log_count",
    "Workout Session Count": "workout_session_count",
    "Exercise Set Count": "exercise_set_count",
    "AI Context Export Count": "ai_context_export_count",
    "Latest Body Measurement Date": "latest_body_measurement_date",
    "Latest Nutrition Log Date": "latest_nutrition_log_date",
    "Latest Manual Workout Date": "latest_manual_workout_date",
    "Manual ChatGPT Sync Ready": "manual_chatgpt_sync_ready",
    "Automatic Cloud Sync Ready": "automatic_cloud_sync_ready",
    "Prospective Eligible Days": "prospective_evaluation_eligible_days",
    "Prospective Target Days": "prospective_evaluation_target_days",
    "Prospective Remaining Days": "prospective_evaluation_remaining_days",
    "Prospective Evaluation Status": "prospective_evaluation_status",
    "Prospective Evaluation Ready": "prospective_evaluation_ready",
    "Daily Collection Status": "daily_collection_status",
    "Daily Collection On Track": "daily_collection_on_track",
    "Today Collection Completed": "today_collection_completed",
    "Current Collection Streak Days": "current_collection_streak_days",
    "Overdue Collection Days": "overdue_collection_days",
    "Latest Source Data Date": "latest_source_data_date",
    "Source Data Lag Days": "source_data_lag_days",
    "Database Aligned With Source": "database_aligned_with_source",
    "Today Source Data Available": "today_source_data_available",
    "Prospective Collection Blocker": "prospective_collection_blocker",
    "Latest Data Date": "latest_data_date",
    "Next Goal": "next_goal",
    "Updated At": "updated_at",
}

INTEGER_STATE_FIELDS = {
    "test_total",
    "test_passed",
    "test_failed",
    "baseline_record_count",
    "scored_day_count",
    "recovery_v1_day_count",
    "schema_migration_count",
    "confidence_record_count",
    "local_coach_record_count",
    "prospective_evaluation_eligible_days",
    "prospective_evaluation_target_days",
    "prospective_evaluation_remaining_days",
    "current_collection_streak_days",
    "overdue_collection_days",
    "source_data_lag_days",
    "body_measurement_count",
    "nutrition_log_count",
    "workout_session_count",
    "exercise_set_count",
    "ai_context_export_count",
    "translation_key_count",
    "kubios_screenshot_count",
    "kubios_screenshot_imported_count",
    "kubios_screenshot_review_pending_count",
    "kubios_raw_measurement_count",
    "kubios_normalized_count",
    "kubios_derived_count",
    "manual_activity_count",
    "manual_sleep_count",
    "manual_recovery_count",
    "resolved_field_count",
    "supplement_catalog_count",
    "supplement_product_count",
    "verified_supplement_product_count",
    "unverified_supplement_product_count",
    "supplement_ingredient_count",
    "food_catalog_count",
    "meal_record_count",
    "meal_item_count",
    "meal_template_count",
    "training_session_count",
    "training_exercise_count",
    "training_set_count",
}

BOOLEAN_STATE_FIELDS = {"test_success", "local_coach_ready", "cloud_ai_runtime_ready", "manual_chatgpt_sync_ready", "automatic_cloud_sync_ready", "prospective_evaluation_ready", "daily_collection_on_track", "today_collection_completed", "database_aligned_with_source", "today_source_data_available", "language_setting_ready", "local_ocr_ready", "real_kubios_screenshot_verified", "kubios_core_metrics_ready", "kubios_advanced_metrics_ready", "scheduled_sync_enabled", "launch_agent_installed", "manual_logging_ready", "data_resolution_ready", "supplement_dynamic_units_ready", "simple_nutrition_input_ready", "structured_training_ready", "brand_based_supplement_logging_ready", "conditional_training_fields_ready", "rpe_rir_preference_supported", "simplified_training_entry_ready"}

COUNTED_TABLES = (
    "polar_daily_activity_raw",
    "polar_training_sessions_raw",
    "polar_sleep_raw",
    "polar_nightly_recharge_raw",
    "polar_cardio_load_raw",
    "polar_continuous_hr_raw",
    "kubios_morning_hrv_raw",
    "kubios_screenshot_imports",
    "kubios_measurement_groups",
    "kubios_hrv_measurements_raw",
    "kubios_hrv_normalized",
    "kubios_hrv_derived",
    "polar_flow_import_files",
    "daily_recovery_metrics",
    "baseline_metrics",
    "recovery_scores",
    "recovery_confidence",
    "local_coach_recommendations",
    "body_measurements",
    "personal_profile",
    "personal_goals",
    "nutrition_logs",
    "nutrition_templates",
    "meal_events",
    "meal_event_items",
    "supplement_catalog",
    "supplement_products",
    "supplement_product_ingredients",
    "supplement_intake_records",
    "supplement_product_favorites",
    "supplement_product_sources",
    "supplement_product_candidates",
    "food_catalog",
    "meal_records",
    "meal_items",
    "meal_templates",
    "training_sessions",
    "exercise_catalog",
    "training_exercises",
    "training_sets",
    "workout_sessions",
    "exercise_sets",
    "daily_nutrition_summary",
    "daily_training_summary",
    "polar_manual_session_links",
    "manual_activity_sessions",
    "manual_sleep_logs",
    "manual_recovery_logs",
    "resolved_daily_fields",
    "schema_migrations",
)

AUTO_STATE_START = "<!-- AUTO_STATE_START -->"
AUTO_STATE_END = "<!-- AUTO_STATE_END -->"


class ProjectStateError(RuntimeError):
    """Raised when project state cannot be derived, written, or verified."""


def parse_version(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.(\d+))?", str(value))
    if not match:
        raise ProjectStateError(f"Invalid engine version: {value}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def normalize_semver(value):
    major, minor, patch = parse_version(value)
    return f"{major}.{minor}.{patch}"


def load_versions(path=VERSIONS_PATH):
    path = Path(path)
    try:
        versions = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectStateError(f"Unable to read version source {path}: {exc}") from exc

    required = {
        "app_version",
        "recovery_engine_version",
        "baseline_engine_version",
        "confidence_engine_version",
        "database_schema_version",
        "dashboard_version",
        "model_version",
        "local_coach_engine_version",
        "personal_logging_version",
        "nutrition_logging_engine_version",
        "food_catalog_version",
        "training_logging_version",
        "training_entry_ui_version",
        "exercise_catalog_version",
        "manual_logging_engine_version",
        "data_resolution_version",
        "scheduler_version",
        "ai_context_export_version",
        "i18n_engine_version",
        "kubios_screenshot_import_version",
        "kubios_data_model_version",
    }
    missing = required - set(versions)
    if missing:
        raise ProjectStateError(f"Version source is missing: {sorted(missing)}")

    for key in required - {"model_version"}:
        value = versions[key]
        if not isinstance(value, str) or not SEMVER_RE.fullmatch(value):
            raise ProjectStateError(f"{key} must be SemVer: {value!r}")
    model_version = versions["model_version"]
    if model_version != "unreleased" and (
        not isinstance(model_version, str)
        or not (SEMVER_RE.fullmatch(model_version) or MODEL_ID_RE.fullmatch(model_version))
    ):
        raise ProjectStateError("model_version must be a model identifier, SemVer, or 'unreleased'")
    return versions


def load_real_kubios_verification(path=KUBIOS_REAL_EVALUATION_PATH):
    """Return only an aggregate verification flag; never load fixture values."""
    try:
        evaluation = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        evaluation.get("verified_on_real_screenshots") is True
        and int(evaluation.get("sample_count", 0)) > 0
        and evaluation.get("template_detection_accuracy") is not None
        and evaluation.get("numeric_field_accuracy") is not None
    )


def collect_i18n_state():
    """Derive translation readiness without network or health-data access."""
    from src.i18n import (
        DEFAULT_LANGUAGE,
        SUPPORTED_LANGUAGES,
        load_language_preference,
    )
    from src.i18n.translator import LOCALES_DIR
    from src.i18n.validation import validate_matching_keys
    from scripts.check_i18n_coverage import scan

    resources = {
        code: json.loads(
            (LOCALES_DIR / f"{code}.json").read_text(encoding="utf-8")
        )
        for code in SUPPORTED_LANGUAGES
    }
    keys = validate_matching_keys(resources)
    uncovered = sum(len(items) for items in scan().values())
    return {
        "supported_languages": list(SUPPORTED_LANGUAGES),
        "default_language": DEFAULT_LANGUAGE,
        "current_language": load_language_preference(),
        "translation_key_count": len(keys),
        "translation_coverage": (
            "100%"
            if not uncovered
            else f"{max(len(keys) - uncovered, 0) / len(keys):.1%}"
        ),
        "language_setting_ready": not uncovered,
    }


def extract_recovery_engine_version(source_path=RECOVERY_SOURCE_PATH):
    source = Path(source_path).read_text(encoding="utf-8")
    versions = set(
        re.findall(
            r'["\']score_version["\']\s*:\s*["\'](v?\d+\.\d+(?:\.\d+)?)["\']',
            source,
        )
    )
    if not versions:
        raise ProjectStateError(f"No score_version found in {source_path}")
    return normalize_semver(max(versions, key=parse_version))


def collect_database_state(db_path=DB_PATH):
    db_path = Path(db_path)
    if not db_path.exists():
        raise ProjectStateError(f"Database does not exist: {db_path}")

    uri = f"file:{db_path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        table_record_counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in COUNTED_TABLES
        }
        date_row = connection.execute(
            "SELECT MIN(date), MAX(date), COUNT(*) FROM daily_recovery_metrics"
        ).fetchone()
        recovery_v1_day_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM recovery_scores
            WHERE score_version IN ('v1.0', '1.0.0')
            """
        ).fetchone()[0]
        schema_row = connection.execute(
            """
            SELECT COUNT(*), (
                SELECT version FROM schema_migrations
                ORDER BY sequence DESC LIMIT 1
            )
            FROM schema_migrations
            """
        ).fetchone()
        latest_local_coach_date = connection.execute(
            "SELECT MAX(date) FROM local_coach_recommendations"
        ).fetchone()[0]
        latest_body_measurement_date = connection.execute("SELECT MAX(date) FROM body_measurements").fetchone()[0]
        latest_nutrition_log_date = connection.execute("SELECT MAX(date) FROM nutrition_logs").fetchone()[0]
        latest_meal_date = connection.execute(
            "SELECT MAX(date) FROM meal_records WHERE deleted_at IS NULL"
        ).fetchone()[0]
        latest_training_detail_date = connection.execute(
            """SELECT MAX(s.date) FROM training_sessions s
               WHERE s.deleted_at IS NULL AND EXISTS (
                   SELECT 1 FROM training_exercises e
                   WHERE e.training_session_id=s.id AND e.deleted_at IS NULL
               )"""
        ).fetchone()[0]
        latest_supplement_product_update = connection.execute(
            "SELECT MAX(updated_at) FROM supplement_products WHERE deleted_at IS NULL"
        ).fetchone()[0]
        verified_supplement_product_count = connection.execute(
            """SELECT COUNT(*) FROM supplement_products WHERE deleted_at IS NULL
               AND verification_status IN ('user_confirmed','label_verified','source_verified')"""
        ).fetchone()[0]
        unverified_supplement_product_count = connection.execute(
            """SELECT COUNT(*) FROM supplement_products WHERE deleted_at IS NULL
               AND verification_status NOT IN ('user_confirmed','label_verified','source_verified')"""
        ).fetchone()[0]
        latest_manual_workout_date = connection.execute("SELECT MAX(date) FROM workout_sessions").fetchone()[0]
        latest_kubios_measurement_date = connection.execute(
            "SELECT MAX(date) FROM kubios_hrv_normalized WHERE selected_as_primary=1"
        ).fetchone()[0]
        screenshot_row = connection.execute(
            """
            SELECT COUNT(*),
                   SUM(CASE WHEN import_status = 'imported' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN reviewed = 0 THEN 1 ELSE 0 END),
                   MAX(created_at)
            FROM kubios_screenshot_imports
            """
        ).fetchone()
        base_path = str(BASE_DIR)
        if base_path not in sys.path:
            sys.path.insert(0, base_path)
        from src.local_coach.prospective import evaluate_prospective
        prospective = evaluate_prospective(connection)
        from src.local_coach.collection import monitor_daily_collection
        daily_collection = monitor_daily_collection(connection)
        from src.data_freshness import collect_freshness
        freshness = collect_freshness(db_path=db_path)
    except sqlite3.Error as exc:
        raise ProjectStateError(f"Unable to read project database state: {exc}") from exc
    finally:
        connection.close()

    return {
        "baseline_record_count": table_record_counts["baseline_metrics"],
        "scored_day_count": table_record_counts["recovery_scores"],
        "recovery_v1_day_count": recovery_v1_day_count,
        "confidence_record_count": table_record_counts["recovery_confidence"],
        "local_coach_record_count": table_record_counts["local_coach_recommendations"],
        "latest_local_coach_date": latest_local_coach_date,
        "body_measurement_count": table_record_counts["body_measurements"],
        "nutrition_log_count": table_record_counts["nutrition_logs"],
        "workout_session_count": table_record_counts["workout_sessions"],
        "exercise_set_count": table_record_counts["exercise_sets"],
        "ai_context_export_count": len(list((BASE_DIR / "exports" / "ai_context").glob("ai_context_*.json"))),
        "latest_body_measurement_date": latest_body_measurement_date,
        "latest_nutrition_log_date": latest_nutrition_log_date,
        "latest_meal_date": latest_meal_date,
        "latest_training_detail_date": latest_training_detail_date,
        "latest_supplement_product_update": latest_supplement_product_update,
        "verified_supplement_product_count": verified_supplement_product_count,
        "unverified_supplement_product_count": unverified_supplement_product_count,
        "latest_manual_workout_date": latest_manual_workout_date,
        "manual_activity_count": table_record_counts["manual_activity_sessions"],
        "manual_sleep_count": table_record_counts["manual_sleep_logs"],
        "manual_recovery_count": table_record_counts["manual_recovery_logs"],
        "resolved_field_count": table_record_counts["resolved_daily_fields"],
        "kubios_screenshot_count": screenshot_row[0] or 0,
        "kubios_screenshot_imported_count": screenshot_row[1] or 0,
        "kubios_screenshot_review_pending_count": screenshot_row[2] or 0,
        "latest_kubios_screenshot_import_date": screenshot_row[3],
        "kubios_raw_measurement_count": table_record_counts["kubios_hrv_measurements_raw"],
        "kubios_normalized_count": table_record_counts["kubios_hrv_normalized"],
        "kubios_derived_count": table_record_counts["kubios_hrv_derived"],
        "latest_kubios_measurement_date": latest_kubios_measurement_date,
        "prospective_evaluation_eligible_days": prospective["eligible_unique_days"],
        "prospective_evaluation_target_days": prospective["target_unique_days"],
        "prospective_evaluation_remaining_days": prospective["remaining_unique_days"],
        "prospective_evaluation_status": prospective["status"],
        "prospective_evaluation_ready": prospective["success"],
        "daily_collection_status": daily_collection["status"],
        "daily_collection_on_track": daily_collection["on_track"],
        "today_collection_completed": daily_collection["today_collected"],
        "current_collection_streak_days": daily_collection["current_streak_days"],
        "overdue_collection_days": daily_collection["overdue_missing_days"],
        "latest_source_data_date": freshness["latest_source_data_date"],
        "source_data_lag_days": freshness["source_data_lag_days"],
        "database_aligned_with_source": freshness["database_aligned_with_source"],
        "today_source_data_available": freshness["today_source_data_available"],
        "prospective_collection_blocker": freshness["prospective_collection_blocker"],
        "daily_metric_day_count": date_row[2],
        "earliest_data_date": date_row[0],
        "latest_data_date": date_row[1],
        "table_record_counts": table_record_counts,
        "schema_migration_count": schema_row[0],
        "latest_schema_migration": schema_row[1],
    }


def collect_scheduler_state():
    """Collect aggregate local scheduler facts without exposing plist contents."""
    from src.scheduler.config import load_scheduler_config
    from src.scheduler.history import SchedulerHistory
    from src.scheduler.launch_agent import get_launch_agent_status

    loaded = load_scheduler_config()
    latest = SchedulerHistory().latest("scheduled")
    agent = get_launch_agent_status()
    return {
        "scheduled_sync_enabled": bool(loaded.config.enabled),
        "scheduled_sync_time": loaded.config.sync_time,
        "launch_agent_installed": bool(agent.installed),
        "latest_scheduled_sync_at": latest.get("finished_at") if latest else None,
        "latest_scheduled_sync_success": (
            latest.get("status") == "success" if latest else None
        ),
    }


def _summary_count(summary, name):
    match = re.search(rf"{re.escape(name)}=(\d+)", summary)
    return int(match.group(1)) if match else 0


def parse_unittest_result(output):
    match = re.search(r"Ran\s+(\d+)\s+tests?", output)
    if not match:
        raise ProjectStateError("Unable to find unittest total in test output")

    total = int(match.group(1))
    summary_match = re.search(r"^(OK|FAILED)(?:\s*\(([^)]*)\))?$", output, re.MULTILINE)
    if not summary_match:
        raise ProjectStateError("Unable to find unittest result summary")

    status, details = summary_match.groups()
    details = details or ""
    failed = (
        _summary_count(details, "failures")
        + _summary_count(details, "errors")
        + _summary_count(details, "unexpected successes")
    )
    passed = max(total - failed, 0)
    return {
        "test_total": total,
        "test_passed": passed,
        "test_failed": failed,
        "test_success": status == "OK" and failed == 0,
        "test_suite_ok": status == "OK",
    }


def discover_test_total(base_dir=BASE_DIR):
    base_dir = Path(base_dir).resolve()
    path_entry = str(base_dir)
    inserted = path_entry not in sys.path
    if inserted:
        sys.path.insert(0, path_entry)
    try:
        suite = unittest.defaultTestLoader.discover(str(base_dir / "tests"))
        return suite.countTestCases()
    finally:
        if inserted:
            sys.path.remove(path_entry)


def run_unittest_suite(
    base_dir=BASE_DIR,
    candidate_state_path=None,
    candidate_current_state_path=None,
):
    environment = os.environ.copy()
    if candidate_state_path is not None:
        environment["PROJECT_STATE_PATH"] = str(candidate_state_path)
    if candidate_current_state_path is not None:
        environment["PROJECT_CURRENT_STATE_PATH"] = str(
            candidate_current_state_path
        )

    process = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=base_dir,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    output = "\n".join(part for part in (process.stdout, process.stderr) if part)
    result = parse_unittest_result(output)
    if process.returncode != 0 or not result.pop("test_suite_ok"):
        raise ProjectStateError(
            "Full unittest suite failed: "
            f"total={result['test_total']} "
            f"passed={result['test_passed']} "
            f"failed={result['test_failed']}"
        )
    return result


def validate_prioritized_issues(issues):
    if not isinstance(issues, list) or not issues:
        raise ProjectStateError("prioritized_issues must be a non-empty list")

    required = {"priority", "description", "status", "owner", "target_phase"}
    for index, issue in enumerate(issues):
        if not isinstance(issue, dict):
            raise ProjectStateError(f"prioritized_issues[{index}] must be an object")
        missing = required - set(issue)
        if missing:
            raise ProjectStateError(
                f"prioritized_issues[{index}] is missing: {sorted(missing)}"
            )
        if issue["priority"] not in PRIORITIES:
            raise ProjectStateError(
                f"prioritized_issues[{index}] has invalid priority"
            )
        if issue["status"] not in ISSUE_STATUSES:
            raise ProjectStateError(
                f"prioritized_issues[{index}] has invalid status"
            )
        for key in required - {"priority", "status"}:
            if not isinstance(issue[key], str) or not issue[key].strip():
                raise ProjectStateError(
                    f"prioritized_issues[{index}].{key} must be non-empty"
                )
    return issues


def load_state_metadata(state_path=STATE_PATH):
    state_path = Path(state_path)
    if not state_path.exists():
        return json.loads(json.dumps(DEFAULT_METADATA))

    state = json.loads(state_path.read_text(encoding="utf-8"))
    metadata = {}
    for key in METADATA_FIELDS:
        metadata[key] = state.get(key, DEFAULT_METADATA[key])
    metadata["prioritized_issues"] = validate_prioritized_issues(
        metadata["prioritized_issues"]
    )
    if metadata["phase_status"] not in {
        "planned",
        "in_progress",
        "completed",
        "blocked",
    }:
        raise ProjectStateError("phase_status is invalid")
    return metadata


def build_project_state(test_result, db_path=DB_PATH, metadata=None):
    metadata = metadata or load_state_metadata()
    versions = load_versions()
    implemented_recovery_version = extract_recovery_engine_version()
    if implemented_recovery_version != versions["recovery_engine_version"]:
        raise ProjectStateError(
            "Recovery Engine version mismatch: "
            f"code={implemented_recovery_version} "
            f"versions.json={versions['recovery_engine_version']}"
        )

    database_state = collect_database_state(db_path)
    scheduler_state = collect_scheduler_state()
    i18n_state = collect_i18n_state()
    if database_state["latest_schema_migration"] != versions["database_schema_version"]:
        raise ProjectStateError(
            "Database schema version mismatch: "
            f"ledger={database_state['latest_schema_migration']} "
            f"versions.json={versions['database_schema_version']}"
        )

    issues = validate_prioritized_issues(metadata["prioritized_issues"])
    state = {
        "app_version": versions["app_version"],
        "current_phase": metadata["current_phase"],
        "phase_status": metadata["phase_status"],
        "recovery_engine_version": versions["recovery_engine_version"],
        "database_schema_version": versions["database_schema_version"],
        "dashboard_version": versions["dashboard_version"],
        "baseline_engine_version": versions["baseline_engine_version"],
        "confidence_engine_version": versions["confidence_engine_version"],
        "local_coach_engine_version": versions["local_coach_engine_version"],
        "personal_logging_version": versions["personal_logging_version"],
        "nutrition_logging_engine_version": versions["nutrition_logging_engine_version"],
        "food_catalog_version": versions["food_catalog_version"],
        "training_logging_version": versions["training_logging_version"],
        "exercise_catalog_version": versions["exercise_catalog_version"],
        "training_entry_ui_version": versions["training_entry_ui_version"],
        "training_entry_default_mode": "simple",
        "conditional_training_fields_ready": True,
        "rpe_rir_preference_supported": True,
        "simplified_training_entry_ready": True,
        "supplement_unit_system_version": versions["supplement_unit_system_version"],
        "supplement_catalog_version": versions["supplement_catalog_version"],
        "supplement_product_enrichment_version": versions["supplement_product_enrichment_version"],
        "manual_logging_engine_version": versions["manual_logging_engine_version"],
        "data_resolution_version": versions["data_resolution_version"],
        "scheduler_version": versions["scheduler_version"],
        "ai_context_export_version": versions["ai_context_export_version"],
        "i18n_engine_version": versions["i18n_engine_version"],
        "kubios_screenshot_import_version": versions["kubios_screenshot_import_version"],
        "kubios_data_model_version": versions["kubios_data_model_version"],
        "model_version": versions["model_version"],
        **test_result,
        **database_state,
        **scheduler_state,
        **i18n_state,
        "local_coach_ready": (
            database_state["local_coach_record_count"] > 0
            and versions["local_coach_engine_version"] == "1.0.0"
        ),
        "cloud_ai_runtime_ready": False,
        "supplement_dynamic_units_ready": (
            versions["supplement_unit_system_version"] == "1.0.0"
            and database_state["table_record_counts"].get("supplement_catalog", 0) >= 10
        ),
        "supplement_catalog_count": database_state["table_record_counts"].get("supplement_catalog", 0),
        "brand_based_supplement_logging_ready": (
            versions["supplement_catalog_version"] == "2.0.0"
            and versions["supplement_product_enrichment_version"] == "1.0.0"
            and database_state["latest_schema_migration"] == "0.15.0"
        ),
        "supplement_product_count": database_state["table_record_counts"].get("supplement_products", 0),
        "verified_supplement_product_count": database_state["verified_supplement_product_count"],
        "unverified_supplement_product_count": database_state["unverified_supplement_product_count"],
        "supplement_ingredient_count": database_state["table_record_counts"].get("supplement_product_ingredients", 0),
        "latest_supplement_product_update": database_state["latest_supplement_product_update"],
        "supplement_enrichment_runtime_status": "provider_blocked",
        "simple_nutrition_input_ready": (
            versions["nutrition_logging_engine_version"] == "5.0.0"
            and versions["food_catalog_version"] == "1.0.0"
            and database_state["table_record_counts"].get("food_catalog", 0) >= 9
        ),
        "food_catalog_count": database_state["table_record_counts"].get("food_catalog", 0),
        "meal_record_count": database_state["table_record_counts"].get("meal_records", 0),
        "meal_item_count": database_state["table_record_counts"].get("meal_items", 0),
        "meal_template_count": database_state["table_record_counts"].get("meal_templates", 0),
        "structured_training_ready": (
            versions["training_logging_version"] == "2.0.0"
            and versions["exercise_catalog_version"] == "1.0.0"
            and database_state["table_record_counts"].get("exercise_catalog", 0) >= 23
        ),
        "training_session_count": database_state["table_record_counts"].get("training_sessions", 0),
        "training_exercise_count": database_state["table_record_counts"].get("training_exercises", 0),
        "training_set_count": database_state["table_record_counts"].get("training_sets", 0),
        "local_ocr_ready": (
            sys.platform == "darwin"
            and (BASE_DIR / "bin" / "kubios-vision-ocr").is_file()
        ),
        "real_kubios_screenshot_verified": load_real_kubios_verification(),
        "kubios_core_metrics_ready": versions["kubios_data_model_version"] == "1.0.0",
        "kubios_advanced_metrics_ready": versions["kubios_data_model_version"] == "1.0.0",
        "manual_chatgpt_sync_ready": True,
        "automatic_cloud_sync_ready": False,
        "manual_logging_ready": (
            versions["manual_logging_engine_version"] == "1.1.0"
            and all(
                name in database_state["table_record_counts"]
                for name in (
                    "manual_activity_sessions", "manual_sleep_logs",
                    "manual_recovery_logs",
                )
            )
        ),
        "data_resolution_ready": (
            versions["data_resolution_version"] == "1.1.0"
            and "resolved_daily_fields" in database_state["table_record_counts"]
        ),
        "known_issues": [issue["description"] for issue in issues],
        "prioritized_issues": issues,
        "next_goal": metadata["next_goal"],
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generated_by": GENERATED_BY,
    }
    missing = REQUIRED_FIELDS - set(state)
    if missing:
        raise ProjectStateError(f"Project state is missing fields: {sorted(missing)}")
    return state


def write_project_state(state, state_path=STATE_PATH):
    state_path = Path(state_path)
    temporary_path = state_path.with_suffix(state_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(state_path)


def preserve_updated_at_when_unchanged(state, previous_state):
    """Keep generated output byte-stable when measured facts did not change."""
    if not isinstance(previous_state, dict):
        return state
    comparable_state = {key: value for key, value in state.items() if key != "updated_at"}
    comparable_previous = {
        key: value for key, value in previous_state.items() if key != "updated_at"
    }
    previous_updated_at = previous_state.get("updated_at")
    if comparable_state == comparable_previous and isinstance(previous_updated_at, str):
        state["updated_at"] = previous_updated_at
    return state


def render_current_state_auto(state):
    issue_rows = [
        "| Priority | Description | Status | Owner | Target Phase |",
        "| --- | --- | --- | --- | --- |",
    ]
    for issue in state["prioritized_issues"]:
        cells = [
            issue["priority"],
            issue["description"],
            issue["status"],
            issue["owner"],
            issue["target_phase"],
        ]
        issue_rows.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")

    lines = [
        AUTO_STATE_START,
        "## Automated Project State",
        "",
        f"- App Version: {state['app_version']}",
        f"- Current Phase: {state['current_phase']}",
        f"- Phase Status: {state['phase_status']}",
        f"- Recovery Engine Version: {state['recovery_engine_version']}",
        f"- Baseline Engine Version: {state['baseline_engine_version']}",
        f"- Confidence Engine Version: {state['confidence_engine_version']}",
        f"- Local Coach Engine Version: {state['local_coach_engine_version']}",
        f"- Personal Logging Version: {state['personal_logging_version']}",
        f"- Nutrition Logging Engine Version: {state['nutrition_logging_engine_version']}",
        f"- Food Catalog Version: {state['food_catalog_version']}",
        f"- Training Logging Version: {state['training_logging_version']}",
        f"- Exercise Catalog Version: {state['exercise_catalog_version']}",
        f"- Training Entry UI Version: {state['training_entry_ui_version']}",
        f"- Training Entry Default Mode: {state['training_entry_default_mode']}",
        f"- Conditional Training Fields Ready: {str(state['conditional_training_fields_ready']).lower()}",
        f"- RPE RIR Preference Supported: {str(state['rpe_rir_preference_supported']).lower()}",
        f"- Simplified Training Entry Ready: {str(state['simplified_training_entry_ready']).lower()}",
        f"- Structured Training Ready: {str(state['structured_training_ready']).lower()}",
        f"- Training Session Count: {state['training_session_count']}",
        f"- Training Exercise Count: {state['training_exercise_count']}",
        f"- Training Set Count: {state['training_set_count']}",
        f"- Latest Training Detail Date: {state['latest_training_detail_date'] or 'none'}",
        f"- Supplement Unit System Version: {state['supplement_unit_system_version']}",
        f"- Supplement Catalog Version: {state['supplement_catalog_version']}",
        f"- Supplement Product Enrichment Version: {state['supplement_product_enrichment_version']}",
        f"- Brand Based Supplement Logging Ready: {str(state['brand_based_supplement_logging_ready']).lower()}",
        f"- Supplement Product Count: {state['supplement_product_count']}",
        f"- Verified Supplement Product Count: {state['verified_supplement_product_count']}",
        f"- Unverified Supplement Product Count: {state['unverified_supplement_product_count']}",
        f"- Supplement Ingredient Count: {state['supplement_ingredient_count']}",
        f"- Latest Supplement Product Update: {state['latest_supplement_product_update'] or 'none'}",
        f"- Supplement Enrichment Runtime Status: {state['supplement_enrichment_runtime_status']}",
        f"- Supplement Dynamic Units Ready: {str(state['supplement_dynamic_units_ready']).lower()}",
        f"- Supplement Catalog Count: {state['supplement_catalog_count']}",
        f"- Simple Nutrition Input Ready: {str(state['simple_nutrition_input_ready']).lower()}",
        f"- Food Catalog Count: {state['food_catalog_count']}",
        f"- Meal Record Count: {state['meal_record_count']}",
        f"- Meal Item Count: {state['meal_item_count']}",
        f"- Meal Template Count: {state['meal_template_count']}",
        f"- Latest Meal Date: {state['latest_meal_date'] or 'none'}",
        f"- Manual Logging Engine Version: {state['manual_logging_engine_version']}",
        f"- Data Resolution Version: {state['data_resolution_version']}",
        f"- Scheduler Version: {state['scheduler_version']}",
        f"- Scheduled Sync Enabled: {str(state['scheduled_sync_enabled']).lower()}",
        f"- Scheduled Sync Time: {state['scheduled_sync_time']}",
        f"- LaunchAgent Installed: {str(state['launch_agent_installed']).lower()}",
        f"- Latest Scheduled Sync At: {state['latest_scheduled_sync_at'] or 'none'}",
        f"- Latest Scheduled Sync Success: {'none' if state['latest_scheduled_sync_success'] is None else str(state['latest_scheduled_sync_success']).lower()}",
        f"- Manual Activity Count: {state['manual_activity_count']}",
        f"- Manual Sleep Count: {state['manual_sleep_count']}",
        f"- Manual Recovery Count: {state['manual_recovery_count']}",
        f"- Resolved Field Count: {state['resolved_field_count']}",
        f"- Manual Logging Ready: {str(state['manual_logging_ready']).lower()}",
        f"- Data Resolution Ready: {str(state['data_resolution_ready']).lower()}",
        f"- AI Context Export Version: {state['ai_context_export_version']}",
        f"- i18n Engine Version: {state['i18n_engine_version']}",
        f"- Kubios Screenshot Import Version: {state['kubios_screenshot_import_version']}",
        f"- Kubios Data Model Version: {state['kubios_data_model_version']}",
        f"- Database Schema Version: {state['database_schema_version']}",
        f"- Schema Migration Count: {state['schema_migration_count']}",
        f"- Latest Schema Migration: {state['latest_schema_migration']}",
        f"- Dashboard Version: {state['dashboard_version']}",
        f"- Supported Languages: {', '.join(state['supported_languages'])}",
        f"- Default Language: {state['default_language']}",
        f"- Current Language: {state['current_language']}",
        f"- Translation Key Count: {state['translation_key_count']}",
        f"- Translation Coverage: {state['translation_coverage']}",
        f"- Language Setting Ready: {str(state['language_setting_ready']).lower()}",
        f"- Kubios Screenshot Count: {state['kubios_screenshot_count']}",
        f"- Kubios Screenshot Imported Count: {state['kubios_screenshot_imported_count']}",
        f"- Kubios Screenshot Review Pending Count: {state['kubios_screenshot_review_pending_count']}",
        f"- Latest Kubios Screenshot Import Date: {state['latest_kubios_screenshot_import_date'] or 'none'}",
        f"- Local OCR Ready: {str(state['local_ocr_ready']).lower()}",
        f"- Real Kubios Screenshot Verified: {str(state['real_kubios_screenshot_verified']).lower()}",
        f"- Kubios Raw Measurement Count: {state['kubios_raw_measurement_count']}",
        f"- Kubios Normalized Count: {state['kubios_normalized_count']}",
        f"- Kubios Derived Count: {state['kubios_derived_count']}",
        f"- Latest Kubios Measurement Date: {state['latest_kubios_measurement_date'] or 'none'}",
        f"- Kubios Core Metrics Ready: {str(state['kubios_core_metrics_ready']).lower()}",
        f"- Kubios Advanced Metrics Ready: {str(state['kubios_advanced_metrics_ready']).lower()}",
        f"- Test Total: {state['test_total']}",
        f"- Test Passed: {state['test_passed']}",
        f"- Test Failed: {state['test_failed']}",
        f"- Test Success: {str(state['test_success']).lower()}",
        f"- Baseline Record Count: {state['baseline_record_count']}",
        f"- Scored Day Count: {state['scored_day_count']}",
        f"- Recovery v1 Day Count: {state['recovery_v1_day_count']}",
        f"- Confidence Record Count: {state['confidence_record_count']}",
        f"- Local Coach Record Count: {state['local_coach_record_count']}",
        f"- Latest Local Coach Date: {state['latest_local_coach_date'] or 'none'}",
        f"- Local Coach Ready: {str(state['local_coach_ready']).lower()}",
        f"- Cloud AI Runtime Ready: {str(state['cloud_ai_runtime_ready']).lower()}",
        f"- Body Measurement Count: {state['body_measurement_count']}",
        f"- Nutrition Log Count: {state['nutrition_log_count']}",
        f"- Workout Session Count: {state['workout_session_count']}",
        f"- Exercise Set Count: {state['exercise_set_count']}",
        f"- AI Context Export Count: {state['ai_context_export_count']}",
        f"- Latest Body Measurement Date: {state['latest_body_measurement_date'] or 'none'}",
        f"- Latest Nutrition Log Date: {state['latest_nutrition_log_date'] or 'none'}",
        f"- Latest Manual Workout Date: {state['latest_manual_workout_date'] or 'none'}",
        f"- Manual ChatGPT Sync Ready: {str(state['manual_chatgpt_sync_ready']).lower()}",
        f"- Automatic Cloud Sync Ready: {str(state['automatic_cloud_sync_ready']).lower()}",
        f"- Prospective Eligible Days: {state['prospective_evaluation_eligible_days']}",
        f"- Prospective Target Days: {state['prospective_evaluation_target_days']}",
        f"- Prospective Remaining Days: {state['prospective_evaluation_remaining_days']}",
        f"- Prospective Evaluation Status: {state['prospective_evaluation_status']}",
        f"- Prospective Evaluation Ready: {str(state['prospective_evaluation_ready']).lower()}",
        f"- Daily Collection Status: {state['daily_collection_status']}",
        f"- Daily Collection On Track: {str(state['daily_collection_on_track']).lower()}",
        f"- Today Collection Completed: {str(state['today_collection_completed']).lower()}",
        f"- Current Collection Streak Days: {state['current_collection_streak_days']}",
        f"- Overdue Collection Days: {state['overdue_collection_days']}",
        f"- Latest Source Data Date: {state['latest_source_data_date'] or 'none'}",
        f"- Source Data Lag Days: {state['source_data_lag_days'] if state['source_data_lag_days'] is not None else 'none'}",
        f"- Database Aligned With Source: {str(state['database_aligned_with_source']).lower()}",
        f"- Today Source Data Available: {str(state['today_source_data_available']).lower()}",
        f"- Prospective Collection Blocker: {state['prospective_collection_blocker'] or 'none'}",
        f"- Latest Data Date: {state['latest_data_date'] or 'none'}",
        f"- Next Goal: {state['next_goal']}",
        f"- Updated At: {state['updated_at']}",
        "",
        "### Prioritized Issues",
        "",
        *issue_rows,
        AUTO_STATE_END,
    ]
    return "\n".join(lines)


def sync_current_state(
    state,
    document_path=CURRENT_STATE_PATH,
    output_path=None,
):
    document_path = Path(document_path)
    output_path = Path(output_path or document_path)
    document = document_path.read_text(encoding="utf-8")
    if (
        document.count(AUTO_STATE_START) != 1
        or document.count(AUTO_STATE_END) != 1
        or document.index(AUTO_STATE_START) > document.index(AUTO_STATE_END)
    ):
        raise ProjectStateError(
            "CURRENT_STATE.md must contain exactly one ordered AUTO_STATE marker pair"
        )

    before = document.split(AUTO_STATE_START, 1)[0]
    after = document.split(AUTO_STATE_END, 1)[1]
    updated = before + render_current_state_auto(state) + after
    output_path.write_text(updated, encoding="utf-8")
    return output_path


def parse_current_state(document_path=CURRENT_STATE_PATH):
    document = Path(document_path).read_text(encoding="utf-8")
    if AUTO_STATE_START not in document or AUTO_STATE_END not in document:
        raise ProjectStateError("CURRENT_STATE.md auto state markers are missing")
    block = document.split(AUTO_STATE_START, 1)[1].split(AUTO_STATE_END, 1)[0]

    values = {}
    for label, state_key in CURRENT_STATE_KEYS.items():
        match = re.search(
            rf"^- {re.escape(label)}:\s*(.+?)\s*$",
            block,
            re.MULTILINE,
        )
        if not match:
            raise ProjectStateError(f"CURRENT_STATE.md is missing key: {label}")
        raw_value = match.group(1).strip()
        if state_key in INTEGER_STATE_FIELDS:
            if raw_value == "none" and state_key == "source_data_lag_days":
                values[state_key] = None
                continue
            try:
                values[state_key] = int(raw_value)
            except ValueError as exc:
                raise ProjectStateError(
                    f"CURRENT_STATE.md value for {label} must be an integer"
                ) from exc
        elif state_key in BOOLEAN_STATE_FIELDS:
            if raw_value not in {"true", "false"}:
                raise ProjectStateError(
                    f"CURRENT_STATE.md value for {label} must be true or false"
                )
            values[state_key] = raw_value == "true"
        elif state_key == "latest_scheduled_sync_success":
            if raw_value == "none":
                values[state_key] = None
            elif raw_value in {"true", "false"}:
                values[state_key] = raw_value == "true"
            else:
                raise ProjectStateError(
                    "CURRENT_STATE.md value for Latest Scheduled Sync Success "
                    "must be true, false, or none"
                )
        elif state_key == "latest_scheduled_sync_at" and raw_value == "none":
            values[state_key] = None
        elif state_key in {"latest_data_date", "latest_local_coach_date", "latest_source_data_date", "latest_body_measurement_date", "latest_nutrition_log_date", "latest_manual_workout_date", "latest_kubios_screenshot_import_date", "latest_kubios_measurement_date", "latest_training_detail_date", "latest_supplement_product_update", "latest_meal_date"} and raw_value == "none":
            values[state_key] = None
        elif state_key == "prospective_collection_blocker" and raw_value == "none":
            values[state_key] = None
        else:
            values[state_key] = raw_value
    return values


def validate_current_state(state, document_path=CURRENT_STATE_PATH):
    document_state = parse_current_state(document_path)
    differences = {
        key: {"project_state": state.get(key), "current_state": value}
        for key, value in document_state.items()
        if state.get(key) != value
    }
    if differences:
        details = "; ".join(
            f"{key}: project_state={values['project_state']!r}, "
            f"CURRENT_STATE={values['current_state']!r}"
            for key, values in differences.items()
        )
        raise ProjectStateError(f"Project state documentation mismatch: {details}")


def _candidate_path(path, suffix):
    path = Path(path)
    return path.with_name(f".{path.name}.{suffix}")


def update_project_state():
    metadata = load_state_metadata()
    try:
        previous_state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        previous_state = None
    discovered_total = discover_test_total()
    candidate_result = {
        "test_total": discovered_total,
        "test_passed": discovered_total,
        "test_failed": 0,
        "test_success": True,
    }
    candidate_state = build_project_state(candidate_result, metadata=metadata)

    candidate_state_path = _candidate_path(STATE_PATH, "candidate")
    candidate_document_path = _candidate_path(CURRENT_STATE_PATH, "candidate")
    write_project_state(candidate_state, candidate_state_path)
    sync_current_state(
        candidate_state,
        document_path=CURRENT_STATE_PATH,
        output_path=candidate_document_path,
    )
    try:
        test_result = run_unittest_suite(
            candidate_state_path=candidate_state_path,
            candidate_current_state_path=candidate_document_path,
        )
    finally:
        candidate_state_path.unlink(missing_ok=True)
        candidate_document_path.unlink(missing_ok=True)

    if test_result["test_total"] != discovered_total:
        raise ProjectStateError(
            "Discovered test count changed while the suite was running: "
            f"before={discovered_total}, result={test_result['test_total']}"
        )

    state = build_project_state(test_result, metadata=metadata)
    preserve_updated_at_when_unchanged(state, previous_state)
    next_state_path = _candidate_path(STATE_PATH, "next")
    next_document_path = _candidate_path(CURRENT_STATE_PATH, "next")
    write_project_state(state, next_state_path)
    sync_current_state(
        state,
        document_path=CURRENT_STATE_PATH,
        output_path=next_document_path,
    )
    validate_current_state(state, next_document_path)
    next_state_path.replace(STATE_PATH)
    next_document_path.replace(CURRENT_STATE_PATH)
    return state


def main():
    try:
        state = update_project_state()
    except ProjectStateError as exc:
        raise SystemExit(f"Project state update failed: {exc}")

    print(f"Updated: {STATE_PATH}")
    print(
        "Tests: "
        f"total={state['test_total']} "
        f"passed={state['test_passed']} "
        f"failed={state['test_failed']}"
    )
    print(
        "Database: "
        f"baseline={state['baseline_record_count']} "
        f"scored_days={state['scored_day_count']} "
        f"recovery_v1_days={state['recovery_v1_day_count']} "
        f"latest={state['latest_data_date']}"
    )
    print("CURRENT_STATE.md: synchronized")


if __name__ == "__main__":
    main()
