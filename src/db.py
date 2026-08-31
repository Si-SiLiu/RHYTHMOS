import sqlite3
import hashlib
import re
from contextvars import ContextVar
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "recovery.db"
_CURRENT_DB_PATH: ContextVar[Path | None] = ContextVar(
    "drc_current_db_path", default=None,
)


def set_current_db_path(db_path: Path | str | None) -> None:
    """Set the database path for the current Streamlit/script context."""
    _CURRENT_DB_PATH.set(Path(db_path) if db_path is not None else None)


def get_current_db_path() -> Path:
    """Return the current session database or the unchanged local default."""
    return _CURRENT_DB_PATH.get() or DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS polar_daily_activity_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    date TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    steps INTEGER,
    calories INTEGER,
    active_calories INTEGER,
    duration TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source, external_id, date)
);

CREATE TABLE IF NOT EXISTS polar_training_sessions_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    date TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    sport TEXT,
    start_time TEXT,
    duration TEXT,
    calories INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source, external_id, date)
);

CREATE TABLE IF NOT EXISTS daily_recovery_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    steps INTEGER,
    calories INTEGER,
    active_calories INTEGER,
    activity_duration TEXT,
    training_count INTEGER NOT NULL DEFAULT 0,
    training_duration TEXT,
    training_calories INTEGER NOT NULL DEFAULT 0,
    sleep_duration TEXT,
    sleep_score INTEGER,
    nightly_hrv_rmssd REAL,
    nightly_resting_hr REAL,
    respiration_rate REAL,
    morning_rmssd REAL,
    morning_mean_hr REAL,
    kubios_readiness TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recovery_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    recovery_score INTEGER NOT NULL,
    activity_load_score INTEGER NOT NULL,
    training_load_score INTEGER NOT NULL,
    hrv_score INTEGER,
    morning_hr_score INTEGER,
    readiness_score INTEGER,
    score_version TEXT NOT NULL DEFAULT 'v0.1',
    recommendation TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS baseline_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    window_days INTEGER NOT NULL,
    valid_days INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    mean_value REAL,
    median_value REAL,
    std_value REAL,
    mad_value REAL,
    min_value REAL,
    max_value REAL,
    latest_value REAL,
    percent_change REAL,
    z_score REAL,
    robust_z_score REAL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (date, metric_name, window_days)
);

CREATE TABLE IF NOT EXISTS polar_sleep_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    date TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    sleep_duration TEXT,
    sleep_score INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source, external_id, date)
);

CREATE TABLE IF NOT EXISTS polar_nightly_recharge_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    date TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    ans_status TEXT,
    hrv_rmssd REAL,
    resting_hr REAL,
    respiration_rate REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source, external_id, date)
);

CREATE TABLE IF NOT EXISTS polar_cardio_load_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    date TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    cardio_load REAL,
    strain REAL,
    tolerance REAL,
    status TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source, external_id, date)
);

CREATE TABLE IF NOT EXISTS polar_continuous_hr_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    date TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source, external_id, date)
);

CREATE TABLE IF NOT EXISTS kubios_morning_hrv_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    date TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    rmssd REAL,
    mean_hr REAL,
    readiness TEXT,
    measurement_time TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source, external_id, date)
);

CREATE TABLE IF NOT EXISTS polar_flow_import_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'collected',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


MIGRATIONS = {
    "daily_recovery_metrics": {
        "sleep_duration": "TEXT",
        "sleep_score": "INTEGER",
        "nightly_hrv_rmssd": "REAL",
        "nightly_resting_hr": "REAL",
        "respiration_rate": "REAL",
        "morning_rmssd": "REAL",
        "morning_mean_hr": "REAL",
        "kubios_readiness": "TEXT",
    },
    "recovery_scores": {
        "hrv_score": "INTEGER",
        "morning_hr_score": "INTEGER",
        "readiness_score": "INTEGER",
        "score_version": "TEXT NOT NULL DEFAULT 'v0.1'",
    },
    "kubios_morning_hrv_raw": {
        "source_type": "TEXT NOT NULL DEFAULT 'csv'",
        "source_file_sha256": "TEXT",
        "ocr_confidence": "REAL",
        "reviewed": "INTEGER NOT NULL DEFAULT 1",
        "reviewed_at": "TEXT",
        "import_method": "TEXT NOT NULL DEFAULT 'csv'",
        "is_daily_preferred": "INTEGER NOT NULL DEFAULT 0",
    },
    "meal_records": {
        "planned_meal_time": "TEXT",
        "actual_meal_time": "TEXT",
    },
    "meal_templates": {
        "template_type": "TEXT NOT NULL DEFAULT 'meal'",
    },
}

MIGRATION_LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    sequence INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


@dataclass(frozen=True)
class SchemaMigration:
    sequence: int
    version: str
    name: str
    fingerprint: str
    sql: str = ""

    @property
    def checksum(self):
        return hashlib.sha256(self.fingerprint.encode("utf-8")).hexdigest()


SCHEMA_MIGRATIONS = (
    SchemaMigration(1, "0.1.0", "legacy_schema_baseline", "daily-recovery-schema-baseline-v1"),
    SchemaMigration(2, "0.2.0", "schema_migration_ledger", "schema-migrations-ledger-v1"),
    SchemaMigration(
        3,
        "0.3.0",
        "recovery_confidence",
        "recovery-confidence-table-v1",
        """
        CREATE TABLE IF NOT EXISTS recovery_confidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            data_completeness_score INTEGER NOT NULL,
            baseline_maturity_score INTEGER NOT NULL,
            confidence_score INTEGER NOT NULL,
            confidence_level TEXT NOT NULL,
            group_scores_json TEXT NOT NULL,
            available_groups_json TEXT NOT NULL,
            missing_groups_json TEXT NOT NULL,
            confidence_version TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    SchemaMigration(
        4,
        "0.4.0",
        "local_coach_recommendations",
        "local-coach-recommendations-table-v1",
        """
        CREATE TABLE IF NOT EXISTS local_coach_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            morning_training_json TEXT NOT NULL,
            evening_training_json TEXT NOT NULL,
            sleep_advice_json TEXT NOT NULL,
            hydration_advice_json TEXT NOT NULL,
            nutrition_advice_json TEXT NOT NULL,
            recovery_advice_json TEXT NOT NULL,
            rationale_json TEXT NOT NULL,
            data_limitations_json TEXT NOT NULL,
            safety_notices_json TEXT NOT NULL,
            engine_version TEXT NOT NULL,
            rule_config_version TEXT NOT NULL,
            generated_without_cloud_ai INTEGER NOT NULL DEFAULT 1
                CHECK (generated_without_cloud_ai = 1),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (date, engine_version)
        );
        """,
    ),
    SchemaMigration(
        5,
        "0.5.0",
        "personal_logging_and_ai_context_export",
        "personal-logging-schema-v1-body-nutrition-workout-summary-link-template",
        """
        CREATE TABLE IF NOT EXISTS body_measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            measurement_time TEXT,
            height_cm REAL NOT NULL CHECK (height_cm > 0),
            weight_kg REAL NOT NULL CHECK (weight_kg > 0),
            waist_cm REAL CHECK (waist_cm IS NULL OR waist_cm > 0),
            body_fat_percent REAL CHECK (
                body_fat_percent IS NULL OR
                (body_fat_percent >= 0 AND body_fat_percent <= 100)
            ),
            is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_body_primary_per_date
            ON body_measurements(date) WHERE is_primary = 1;

        CREATE TABLE IF NOT EXISTS nutrition_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            meal_type TEXT NOT NULL CHECK (meal_type IN (
                'breakfast','lunch','dinner','snack','pre_workout',
                'post_workout','other'
            )),
            meal_time TEXT,
            food_name TEXT NOT NULL,
            amount REAL,
            unit TEXT,
            calories REAL,
            protein_g REAL,
            carbohydrate_g REAL,
            fat_g REAL,
            fiber_g REAL,
            water_ml REAL,
            sodium_mg REAL,
            notes TEXT,
            data_source TEXT NOT NULL DEFAULT 'manual'
                CHECK (data_source IN ('manual','template','import')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS nutrition_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            items_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS workout_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            session_type TEXT NOT NULL CHECK (session_type IN (
                'strength','hiphop','cardio','mobility','juggling','other'
            )),
            start_time TEXT,
            end_time TEXT,
            duration_minutes REAL CHECK (
                duration_minutes IS NULL OR duration_minutes >= 0
            ),
            session_rpe REAL CHECK (
                session_rpe IS NULL OR (session_rpe >= 0 AND session_rpe <= 10)
            ),
            energy_before INTEGER CHECK (
                energy_before IS NULL OR (energy_before >= 0 AND energy_before <= 10)
            ),
            energy_after INTEGER CHECK (
                energy_after IS NULL OR (energy_after >= 0 AND energy_after <= 10)
            ),
            soreness INTEGER CHECK (
                soreness IS NULL OR (soreness >= 0 AND soreness <= 10)
            ),
            metadata_json TEXT NOT NULL DEFAULT '{}',
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS exercise_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workout_session_id INTEGER NOT NULL,
            exercise_name TEXT NOT NULL,
            exercise_category TEXT,
            set_number INTEGER NOT NULL CHECK (set_number > 0),
            reps INTEGER CHECK (reps IS NULL OR reps >= 0),
            weight_kg REAL CHECK (weight_kg IS NULL OR weight_kg >= 0),
            duration_seconds REAL CHECK (
                duration_seconds IS NULL OR duration_seconds >= 0
            ),
            distance_m REAL CHECK (distance_m IS NULL OR distance_m >= 0),
            rpe REAL CHECK (rpe IS NULL OR (rpe >= 0 AND rpe <= 10)),
            rir REAL CHECK (rir IS NULL OR rir >= 0),
            tempo TEXT,
            rest_seconds REAL CHECK (rest_seconds IS NULL OR rest_seconds >= 0),
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workout_session_id) REFERENCES workout_sessions(id)
                ON DELETE CASCADE,
            UNIQUE (workout_session_id, exercise_name, set_number)
        );

        CREATE TABLE IF NOT EXISTS daily_nutrition_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            logged_meals INTEGER NOT NULL,
            calories REAL,
            protein_g REAL,
            carbohydrate_g REAL,
            fat_g REAL,
            fiber_g REAL,
            water_ml REAL,
            sodium_mg REAL,
            data_completeness INTEGER NOT NULL CHECK (
                data_completeness >= 0 AND data_completeness <= 100
            ),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS daily_training_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            session_count INTEGER NOT NULL,
            strength_session_count INTEGER NOT NULL,
            hiphop_session_count INTEGER NOT NULL,
            total_duration_minutes REAL,
            total_sets INTEGER NOT NULL,
            total_reps INTEGER NOT NULL,
            total_volume_kg REAL,
            average_session_rpe REAL,
            session_rpe_load REAL,
            strength_duration_minutes REAL,
            hiphop_duration_minutes REAL,
            juggling_duration_minutes REAL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS polar_manual_session_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            polar_session_external_id TEXT NOT NULL,
            workout_session_id INTEGER NOT NULL,
            match_method TEXT NOT NULL CHECK (
                match_method IN ('manual','date_time','date_type')
            ),
            confidence REAL CHECK (
                confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
            ),
            confirmed_by_user INTEGER NOT NULL DEFAULT 0
                CHECK (confirmed_by_user IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workout_session_id) REFERENCES workout_sessions(id)
                ON DELETE CASCADE,
            UNIQUE (polar_session_external_id, workout_session_id)
        );
        """,
    ),
    SchemaMigration(
        6,
        "0.6.0",
        "kubios_screenshot_import",
        "kubios-screenshot-import-v1-audit-reviewed-source-priority-local-ocr",
        """
        CREATE TABLE IF NOT EXISTS kubios_screenshot_imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_sha256 TEXT NOT NULL UNIQUE,
            original_relative_path TEXT NOT NULL,
            processed_relative_path TEXT,
            import_status TEXT NOT NULL,
            ocr_engine TEXT NOT NULL,
            ocr_engine_version TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            detected_date TEXT,
            detected_measurement_time TEXT,
            ocr_text_summary TEXT NOT NULL DEFAULT '',
            overall_ocr_confidence REAL,
            required_fields_found INTEGER NOT NULL DEFAULT 0,
            review_required INTEGER NOT NULL DEFAULT 1,
            reviewed INTEGER NOT NULL DEFAULT 0,
            reviewed_at TEXT,
            imported_record_id INTEGER,
            downstream_updated INTEGER NOT NULL DEFAULT 0,
            error_code TEXT,
            safe_error_message TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_kubios_screenshot_status
            ON kubios_screenshot_imports(import_status, created_at);
        CREATE INDEX IF NOT EXISTS idx_kubios_screenshot_detected_date
            ON kubios_screenshot_imports(detected_date);
        CREATE INDEX IF NOT EXISTS idx_kubios_source_file_sha
            ON kubios_morning_hrv_raw(source_file_sha256);
        """,
    ),
    SchemaMigration(
        7,
        "0.7.0",
        "kubios_hrv_data_model",
        "kubios-hrv-data-model-v1-raw-normalized-derived-groups-source-selection",
        """
        ALTER TABLE kubios_screenshot_imports ADD COLUMN measurement_group_id TEXT;
        CREATE TABLE IF NOT EXISTS kubios_measurement_groups (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            measurement_time_start TEXT,
            measurement_time_end TEXT,
            confirmed_by_user INTEGER NOT NULL DEFAULT 0 CHECK (confirmed_by_user IN (0,1)),
            confirmation_reason TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS kubios_hrv_measurements_raw (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            measurement_time TEXT,
            measurement_group_id TEXT,
            mean_rr_ms REAL,
            mean_hr_bpm REAL,
            rmssd_ms REAL,
            sdnn_ms REAL,
            poincare_sd1_ms REAL,
            poincare_sd2_ms REAL,
            stress_index REAL,
            respiratory_rate_bpm REAL,
            lf_power_ms2 REAL,
            hf_power_ms2 REAL,
            lf_power_nu REAL,
            hf_power_nu REAL,
            lf_hf_ratio REAL,
            readiness_percent REAL,
            pns_index REAL,
            sns_index REAL,
            physiological_age REAL,
            measurement_quality TEXT,
            mood_code TEXT,
            recovery_status TEXT,
            artefact_correction_percent REAL,
            measurement_duration_seconds REAL,
            source_type TEXT NOT NULL,
            source_file_sha256 TEXT,
            import_method TEXT NOT NULL,
            parser_version TEXT,
            reviewed INTEGER NOT NULL DEFAULT 0 CHECK (reviewed IN (0,1)),
            ocr_confidence REAL,
            selected_as_primary INTEGER NOT NULL DEFAULT 0 CHECK (selected_as_primary IN (0,1)),
            selection_reason TEXT,
            source_priority INTEGER NOT NULL,
            raw_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (measurement_group_id) REFERENCES kubios_measurement_groups(id),
            UNIQUE (date, measurement_time, source_type, source_file_sha256, import_method)
        );
        CREATE INDEX IF NOT EXISTS idx_kubios_hrv_raw_date
            ON kubios_hrv_measurements_raw(date, measurement_time);
        CREATE INDEX IF NOT EXISTS idx_kubios_hrv_raw_group
            ON kubios_hrv_measurements_raw(measurement_group_id);

        CREATE TABLE IF NOT EXISTS kubios_hrv_normalized (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            measurement_time TEXT,
            measurement_group_id TEXT,
            source_raw_table TEXT NOT NULL,
            source_raw_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            selected_as_primary INTEGER NOT NULL DEFAULT 1 CHECK (selected_as_primary IN (0,1)),
            selection_reason TEXT NOT NULL,
            source_priority INTEGER NOT NULL,
            rmssd_ms REAL,
            mean_hr_bpm REAL,
            readiness_percent REAL,
            pns_index REAL,
            sns_index REAL,
            sdnn_ms REAL,
            respiratory_rate_bpm REAL,
            stress_index REAL,
            physiological_age REAL,
            measurement_quality TEXT,
            core_data_completeness REAL NOT NULL CHECK (core_data_completeness BETWEEN 0 AND 100),
            normalization_version TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (date, measurement_time, source_type, normalization_version)
        );
        CREATE INDEX IF NOT EXISTS idx_kubios_normalized_primary
            ON kubios_hrv_normalized(date, selected_as_primary);

        CREATE TABLE IF NOT EXISTS kubios_hrv_derived (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            rmssd_vs_baseline_percent REAL,
            mean_hr_vs_baseline_percent REAL,
            sdnn_vs_baseline_percent REAL,
            readiness_vs_baseline_percent REAL,
            pns_vs_baseline_delta REAL,
            sns_vs_baseline_delta REAL,
            respiratory_rate_vs_baseline_percent REAL,
            stress_index_vs_baseline_percent REAL,
            rmssd_7d_trend REAL,
            mean_hr_7d_trend REAL,
            readiness_7d_trend REAL,
            pns_7d_trend REAL,
            sns_7d_trend REAL,
            consecutive_rmssd_below_baseline_days INTEGER NOT NULL DEFAULT 0,
            consecutive_mean_hr_above_baseline_days INTEGER NOT NULL DEFAULT 0,
            consecutive_readiness_decline_days INTEGER NOT NULL DEFAULT 0,
            data_quality_status TEXT NOT NULL,
            source_reliability_status TEXT NOT NULL,
            derivation_version TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (date, derivation_version)
        );
        """,
    ),
    SchemaMigration(
        8,
        "0.8.0",
        "manual_health_logging_and_field_resolution",
        "manual-health-logging-v1-activity-sleep-recovery-source-links-xor-resolved-fields",
        """
        CREATE TABLE IF NOT EXISTS manual_activity_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            duration_minutes REAL CHECK (duration_minutes IS NULL OR duration_minutes >= 0),
            activity_type TEXT,
            activity_name TEXT,
            average_hr_bpm REAL CHECK (average_hr_bpm IS NULL OR average_hr_bpm > 0),
            max_hr_bpm REAL CHECK (max_hr_bpm IS NULL OR max_hr_bpm > 0),
            calories_kcal REAL CHECK (calories_kcal IS NULL OR calories_kcal >= 0),
            fat_burn_percentage REAL CHECK (fat_burn_percentage IS NULL OR fat_burn_percentage BETWEEN 0 AND 100),
            distance_m REAL CHECK (distance_m IS NULL OR distance_m >= 0),
            session_rpe REAL CHECK (session_rpe IS NULL OR session_rpe BETWEEN 0 AND 10),
            notes TEXT,
            linked_polar_session_id TEXT,
            confirmed_by_user INTEGER NOT NULL DEFAULT 0 CHECK (confirmed_by_user IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_manual_activity_date
            ON manual_activity_sessions(date, start_time);

        CREATE TABLE IF NOT EXISTS manual_sleep_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sleep_date TEXT NOT NULL,
            bed_time TEXT,
            sleep_start_time TEXT,
            wake_time TEXT,
            get_up_time TEXT,
            sleep_duration_minutes REAL CHECK (sleep_duration_minutes IS NULL OR sleep_duration_minutes >= 0),
            nap_duration_minutes REAL CHECK (nap_duration_minutes IS NULL OR nap_duration_minutes >= 0),
            subjective_sleep_quality INTEGER CHECK (subjective_sleep_quality IS NULL OR subjective_sleep_quality BETWEEN 1 AND 10),
            awakenings INTEGER CHECK (awakenings IS NULL OR awakenings >= 0),
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_manual_sleep_date
            ON manual_sleep_logs(sleep_date);

        CREATE TABLE IF NOT EXISTS manual_recovery_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            measurement_time TEXT,
            subjective_recovery INTEGER CHECK (subjective_recovery IS NULL OR subjective_recovery BETWEEN 1 AND 10),
            fatigue INTEGER CHECK (fatigue IS NULL OR fatigue BETWEEN 1 AND 10),
            muscle_soreness INTEGER CHECK (muscle_soreness IS NULL OR muscle_soreness BETWEEN 1 AND 10),
            mental_energy INTEGER CHECK (mental_energy IS NULL OR mental_energy BETWEEN 1 AND 10),
            training_motivation INTEGER CHECK (training_motivation IS NULL OR training_motivation BETWEEN 1 AND 10),
            stress_level INTEGER CHECK (stress_level IS NULL OR stress_level BETWEEN 1 AND 10),
            pain_present INTEGER NOT NULL DEFAULT 0 CHECK (pain_present IN (0,1)),
            pain_location TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_manual_recovery_date
            ON manual_recovery_logs(date, measurement_time);

        ALTER TABLE polar_manual_session_links RENAME TO polar_manual_session_links_legacy;
        CREATE TABLE polar_manual_session_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            polar_session_external_id TEXT NOT NULL,
            workout_session_id INTEGER,
            manual_activity_session_id INTEGER,
            match_method TEXT NOT NULL CHECK (
                match_method IN ('manual','date_time','date_type','date_duration')
            ),
            confidence REAL CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
            match_confidence REAL CHECK (match_confidence IS NULL OR match_confidence BETWEEN 0 AND 1),
            confirmed_by_user INTEGER NOT NULL DEFAULT 0 CHECK (confirmed_by_user IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workout_session_id) REFERENCES workout_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (manual_activity_session_id) REFERENCES manual_activity_sessions(id) ON DELETE CASCADE,
            CHECK (
                (workout_session_id IS NOT NULL AND manual_activity_session_id IS NULL)
                OR
                (workout_session_id IS NULL AND manual_activity_session_id IS NOT NULL)
            )
        );
        INSERT INTO polar_manual_session_links (
            id, polar_session_external_id, workout_session_id, match_method,
            confidence, match_confidence, confirmed_by_user, created_at, updated_at
        )
        SELECT id, polar_session_external_id, workout_session_id, match_method,
               confidence, confidence, confirmed_by_user, created_at, created_at
        FROM polar_manual_session_links_legacy;
        DROP TABLE polar_manual_session_links_legacy;
        CREATE UNIQUE INDEX idx_polar_workout_link
            ON polar_manual_session_links(polar_session_external_id, workout_session_id)
            WHERE workout_session_id IS NOT NULL;
        CREATE UNIQUE INDEX idx_polar_manual_activity_link
            ON polar_manual_session_links(polar_session_external_id, manual_activity_session_id)
            WHERE manual_activity_session_id IS NOT NULL;

        CREATE TABLE IF NOT EXISTS resolved_daily_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            domain TEXT NOT NULL CHECK (domain IN ('activity','sleep','recovery','nutrition')),
            field_name TEXT NOT NULL,
            resolved_value_json TEXT,
            value_source TEXT NOT NULL CHECK (value_source IN ('polar','kubios','manual','estimated','missing')),
            source_record_id TEXT,
            is_fallback INTEGER NOT NULL DEFAULT 0 CHECK (is_fallback IN (0,1)),
            is_manual_override INTEGER NOT NULL DEFAULT 0 CHECK (is_manual_override IN (0,1)),
            resolution_reason TEXT NOT NULL,
            resolution_version TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (date, domain, field_name, resolution_version)
        );
        CREATE INDEX IF NOT EXISTS idx_resolved_fields_date_domain
            ON resolved_daily_fields(date, domain);
        """,
    ),
    SchemaMigration(
        9,
        "0.9.0",
        "editable_health_and_meal_events",
        "editable-health-v1-sleep-recovery-meal-events-items-max-five",
        """
        ALTER TABLE manual_sleep_logs ADD COLUMN total_sleep_duration_minutes REAL
            CHECK (total_sleep_duration_minutes IS NULL OR total_sleep_duration_minutes >= 0);
        ALTER TABLE manual_sleep_logs ADD COLUMN actual_sleep_duration_minutes REAL
            CHECK (actual_sleep_duration_minutes IS NULL OR actual_sleep_duration_minutes >= 0);
        ALTER TABLE manual_sleep_logs ADD COLUMN deep_sleep_duration_minutes REAL
            CHECK (deep_sleep_duration_minutes IS NULL OR deep_sleep_duration_minutes >= 0);
        ALTER TABLE manual_sleep_logs ADD COLUMN rem_sleep_duration_minutes REAL
            CHECK (rem_sleep_duration_minutes IS NULL OR rem_sleep_duration_minutes >= 0);
        ALTER TABLE manual_sleep_logs ADD COLUMN average_sleep_hr_bpm REAL
            CHECK (average_sleep_hr_bpm IS NULL OR average_sleep_hr_bpm > 0);
        ALTER TABLE manual_sleep_logs ADD COLUMN minimum_sleep_hr_bpm REAL
            CHECK (minimum_sleep_hr_bpm IS NULL OR minimum_sleep_hr_bpm > 0);
        ALTER TABLE manual_sleep_logs ADD COLUMN nightly_hrv_rmssd REAL
            CHECK (nightly_hrv_rmssd IS NULL OR nightly_hrv_rmssd > 0);
        ALTER TABLE manual_sleep_logs ADD COLUMN respiration_rate REAL
            CHECK (respiration_rate IS NULL OR respiration_rate > 0);

        ALTER TABLE manual_recovery_logs ADD COLUMN morning_rmssd_ms REAL
            CHECK (morning_rmssd_ms IS NULL OR morning_rmssd_ms > 0);
        ALTER TABLE manual_recovery_logs ADD COLUMN morning_resting_hr_bpm REAL
            CHECK (morning_resting_hr_bpm IS NULL OR morning_resting_hr_bpm > 0);

        CREATE TABLE IF NOT EXISTS meal_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            meal_type TEXT NOT NULL CHECK (meal_type IN (
                'breakfast','morning_snack','lunch','afternoon_snack','dinner',
                'training_fuel','bedtime_fuel','free_snack'
            )),
            actual_meal_time TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_meal_events_date_time
            ON meal_events(date, actual_meal_time, id);

        CREATE TABLE IF NOT EXISTS meal_event_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_event_id INTEGER NOT NULL,
            category TEXT NOT NULL CHECK (category IN (
                'carbohydrate','protein','fat','vegetable','fruit','dairy',
                'nuts','supplement','hydration','caffeine','alcohol'
            )),
            position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 5),
            item_name TEXT,
            quantity REAL NOT NULL CHECK (quantity >= 0),
            unit TEXT NOT NULL CHECK (unit IN ('g','ml')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (meal_event_id) REFERENCES meal_events(id) ON DELETE CASCADE,
            UNIQUE (meal_event_id, category, position)
        );
        CREATE INDEX IF NOT EXISTS idx_meal_event_items_event
            ON meal_event_items(meal_event_id, category, position);
        """,
    ),
    SchemaMigration(
        10,
        "0.10.0",
        "personal_profile_and_goals",
        "personal-profile-goals-v1-singleton-local-only",
        """
        CREATE TABLE IF NOT EXISTS personal_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            name TEXT NOT NULL,
            gender TEXT NOT NULL CHECK (gender IN (
                'male','female','non_binary','prefer_not_to_say'
            )),
            birth_date TEXT NOT NULL,
            height_cm REAL NOT NULL CHECK (height_cm > 0 AND height_cm <= 300),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS personal_goals (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            target_weight_kg REAL CHECK (
                target_weight_kg IS NULL OR
                (target_weight_kg > 0 AND target_weight_kg <= 500)
            ),
            target_body_fat_percent REAL CHECK (
                target_body_fat_percent IS NULL OR
                (target_body_fat_percent > 0 AND target_body_fat_percent <= 100)
            ),
            target_waist_cm REAL CHECK (
                target_waist_cm IS NULL OR
                (target_waist_cm > 0 AND target_waist_cm <= 300)
            ),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    SchemaMigration(
        11,
        "0.11.0",
        "kubios_morning_autonomic_inputs",
        "kubios-morning-autonomic-inputs-v1-stress-respiration-quality",
        """
        ALTER TABLE kubios_morning_hrv_raw ADD COLUMN stress_index REAL
            CHECK (stress_index IS NULL OR stress_index >= 0);
        ALTER TABLE kubios_morning_hrv_raw ADD COLUMN respiratory_rate REAL
            CHECK (respiratory_rate IS NULL OR respiratory_rate > 0);
        ALTER TABLE kubios_morning_hrv_raw ADD COLUMN measurement_quality TEXT
            CHECK (
                measurement_quality IS NULL OR
                measurement_quality IN ('GOOD','ACCEPTABLE','POOR','INVALID')
            );
        """,
    ),
    SchemaMigration(
        12,
        "0.12.0",
        "supplement_dynamic_units",
        "supplement-dynamic-units-v1-catalog-dual-dose-legacy-grams",
        """
        ALTER TABLE meal_event_items RENAME TO meal_event_items_legacy_011;

        CREATE TABLE meal_event_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_event_id INTEGER NOT NULL,
            category TEXT NOT NULL CHECK (category IN (
                'carbohydrate','protein','fat','vegetable','fruit','dairy',
                'nuts','supplement','hydration','caffeine','alcohol'
            )),
            position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 5),
            item_name TEXT,
            quantity REAL NOT NULL CHECK (
                quantity >= 0 AND (category != 'supplement' OR quantity > 0)
            ),
            unit TEXT NOT NULL CHECK (unit IN (
                'g','mg','mcg','ml','capsule','tablet','sachet','scoop','drop','iu'
            )),
            active_amount REAL CHECK (active_amount IS NULL OR active_amount > 0),
            active_unit TEXT CHECK (active_unit IS NULL OR active_unit IN (
                'g','mg','mcg','ml','capsule','tablet','sachet','scoop','drop','iu'
            )),
            timing TEXT,
            item_notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (meal_event_id) REFERENCES meal_events(id) ON DELETE CASCADE,
            UNIQUE (meal_event_id, category, position),
            CHECK (
                (active_amount IS NULL AND active_unit IS NULL) OR
                (active_amount IS NOT NULL AND active_unit IS NOT NULL)
            )
        );
        INSERT INTO meal_event_items (
            id,meal_event_id,category,position,item_name,quantity,unit,
            created_at,updated_at
        )
        SELECT id,meal_event_id,category,position,item_name,quantity,
               CASE WHEN unit='ml' THEN 'ml' ELSE 'g' END,
               created_at,updated_at
        FROM meal_event_items_legacy_011;
        DROP TABLE meal_event_items_legacy_011;
        CREATE INDEX idx_meal_event_items_event
            ON meal_event_items(meal_event_id, category, position);

        CREATE TABLE supplement_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT NOT NULL UNIQUE,
            display_name_zh TEXT NOT NULL,
            display_name_en TEXT NOT NULL,
            category TEXT NOT NULL,
            default_unit TEXT NOT NULL CHECK (default_unit IN (
                'g','mg','mcg','ml','capsule','tablet','sachet','scoop','drop','iu'
            )),
            allowed_units_json TEXT NOT NULL,
            default_active_unit TEXT CHECK (default_active_unit IS NULL OR default_active_unit IN (
                'g','mg','mcg','ml','capsule','tablet','sachet','scoop','drop','iu'
            )),
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO supplement_catalog(
            canonical_name,display_name_zh,display_name_en,category,
            default_unit,allowed_units_json,default_active_unit
        ) VALUES
          ('creatine_monohydrate','一水肌酸','Creatine Monohydrate','performance','g','["g","mg","scoop"]','g'),
          ('protein_powder','蛋白粉','Protein Powder','protein','g','["g","scoop"]','g'),
          ('fish_oil','鱼油','Fish Oil','fatty_acid','capsule','["capsule","mg"]','mg'),
          ('lutein','叶黄素','Lutein','micronutrient','capsule','["capsule","mg"]','mg'),
          ('vitamin_d3','维生素 D3','Vitamin D3','vitamin','capsule','["capsule","tablet","iu","mcg"]','iu'),
          ('vitamin_d3k2','维生素 D3K2','Vitamin D3K2','vitamin','capsule','["capsule","tablet","iu","mcg"]','iu'),
          ('magnesium','镁','Magnesium','mineral','tablet','["tablet","capsule","mg"]','mg'),
          ('electrolyte_powder','电解质粉','Electrolyte Powder','hydration','g','["g","sachet","scoop"]','mg'),
          ('caffeine_tablet','咖啡因片','Caffeine Tablet','stimulant','tablet','["tablet","mg"]','mg'),
          ('collagen','胶原蛋白','Collagen','protein','g','["g","scoop"]','g');
        """,
    ),
    SchemaMigration(
        13,
        "0.13.0",
        "simplified_structured_nutrition_logging",
        "simple-nutrition-v1-food-catalog-multitag-meals-templates-legacy-preserved",
        """
        ALTER TABLE meal_event_items ADD COLUMN active_component_name TEXT;

        CREATE TABLE food_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT NOT NULL UNIQUE,
            display_name_zh TEXT NOT NULL,
            display_name_en TEXT NOT NULL,
            aliases_json TEXT NOT NULL DEFAULT '[]',
            default_unit TEXT NOT NULL CHECK (default_unit IN (
                'g','kg','ml','l','piece','slice','serving','bowl','cup',
                'spoon','bottle','pack'
            )),
            allowed_units_json TEXT NOT NULL,
            category_tags_json TEXT NOT NULL DEFAULT '[]',
            serving_unit TEXT CHECK (serving_unit IS NULL OR serving_unit IN (
                'piece','slice','serving','bowl','cup','spoon','bottle','pack'
            )),
            serving_weight_g REAL CHECK (serving_weight_g IS NULL OR serving_weight_g > 0),
            serving_volume_ml REAL CHECK (serving_volume_ml IS NULL OR serving_volume_ml > 0),
            calories_per_100g REAL CHECK (calories_per_100g IS NULL OR calories_per_100g >= 0),
            protein_per_100g REAL CHECK (protein_per_100g IS NULL OR protein_per_100g >= 0),
            carbohydrate_per_100g REAL CHECK (carbohydrate_per_100g IS NULL OR carbohydrate_per_100g >= 0),
            fat_per_100g REAL CHECK (fat_per_100g IS NULL OR fat_per_100g >= 0),
            fiber_per_100g REAL CHECK (fiber_per_100g IS NULL OR fiber_per_100g >= 0),
            water_per_100g REAL CHECK (water_per_100g IS NULL OR water_per_100g >= 0),
            caffeine_per_100g REAL CHECK (caffeine_per_100g IS NULL OR caffeine_per_100g >= 0),
            alcohol_per_100g REAL CHECK (alcohol_per_100g IS NULL OR alcohol_per_100g >= 0),
            nutrition_source TEXT,
            data_quality TEXT NOT NULL CHECK (data_quality IN ('reference','verified','limited')),
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        INSERT INTO food_catalog(
            canonical_name,display_name_zh,display_name_en,aliases_json,
            default_unit,allowed_units_json,category_tags_json,serving_unit,
            serving_weight_g,serving_volume_ml,calories_per_100g,
            protein_per_100g,carbohydrate_per_100g,fat_per_100g,
            fiber_per_100g,water_per_100g,caffeine_per_100g,alcohol_per_100g,
            nutrition_source,data_quality
        ) VALUES
          ('oats','燕麦','Oats','["oatmeal","燕麦片"]','g','["g","kg","serving"]','["carbohydrate_source","fiber_source","whole_grain","protein_source"]','serving',40,NULL,379,13.15,67.70,6.52,10.10,10.84,0,0,'builtin_reference_v1','reference'),
          ('greek_yogurt','希腊酸奶','Greek Yogurt','["yogurt","酸奶"]','g','["g","kg","serving"]','["protein_source","dairy"]','serving',150,NULL,59,10.19,3.60,0.39,0,85.10,0,0,'builtin_reference_v1','reference'),
          ('orange','橙子','Orange','["橙","甜橙"]','piece','["piece","g","kg"]','["fruit","carbohydrate_source","fiber_source"]','piece',131,NULL,47,0.94,11.75,0.12,2.40,86.75,0,0,'builtin_reference_v1','reference'),
          ('egg','鸡蛋','Egg','["鸡子","全蛋"]','piece','["piece","g","kg"]','["protein_source","fat_source","animal_food"]','piece',50,NULL,143,12.56,0.72,9.51,0,76.15,0,0,'builtin_reference_v1','reference'),
          ('water','水','Water','["饮用水","drinking water"]','ml','["ml","l","cup"]','["beverage","hydration"]','cup',240,240,0,0,0,0,0,100,0,0,'builtin_reference_v1','verified'),
          ('coffee','咖啡','Coffee','["黑咖啡","brewed coffee"]','cup','["cup","ml","l"]','["beverage","caffeine_source"]','cup',240,240,1,0.12,0,0.02,0,99.39,40,0,'builtin_reference_v1','reference'),
          ('milk','牛奶','Milk','["whole milk","全脂牛奶"]','ml','["ml","l","cup","g"]','["dairy","protein_source","fat_source","carbohydrate_source","beverage"]','cup',247,240,61,3.15,4.80,3.25,0,88.13,0,0,'builtin_reference_v1','reference'),
          ('broccoli','西兰花','Broccoli','["青花菜"]','g','["g","kg","serving"]','["vegetable","fiber_source"]','serving',100,NULL,34,2.82,6.64,0.37,2.60,89.30,0,0,'builtin_reference_v1','reference'),
          ('avocado','牛油果','Avocado','["鳄梨"]','g','["g","kg","piece"]','["fruit","fat_source","fiber_source"]','piece',150,NULL,160,2,8.53,14.66,6.70,73.23,0,0,'builtin_reference_v1','reference');

        CREATE TABLE meal_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            date TEXT NOT NULL,
            meal_type TEXT NOT NULL CHECK (meal_type IN (
                'breakfast','morning_snack','lunch','afternoon_snack','dinner',
                'training_fuel','bedtime_fuel','free_snack'
            )),
            eaten_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('draft','completed')),
            source TEXT NOT NULL CHECK (source IN (
                'manual','copied','template','imported','photo_reviewed'
            )),
            notes TEXT,
            legacy_meal_event_id INTEGER UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            FOREIGN KEY (legacy_meal_event_id) REFERENCES meal_events(id)
        );
        CREATE INDEX idx_meal_records_date_time
            ON meal_records(date, eaten_at, id);

        CREATE TABLE meal_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            meal_record_id INTEGER NOT NULL,
            food_catalog_id INTEGER,
            custom_food_name TEXT,
            item_type TEXT NOT NULL CHECK (item_type IN ('food','beverage')),
            quantity REAL NOT NULL CHECK (quantity > 0),
            unit TEXT NOT NULL CHECK (unit IN (
                'g','kg','ml','l','piece','slice','serving','bowl','cup',
                'spoon','bottle','pack'
            )),
            normalized_weight_g REAL CHECK (normalized_weight_g IS NULL OR normalized_weight_g > 0),
            normalized_volume_ml REAL CHECK (normalized_volume_ml IS NULL OR normalized_volume_ml > 0),
            category_tags_json TEXT NOT NULL DEFAULT '[]',
            calories_kcal REAL CHECK (calories_kcal IS NULL OR calories_kcal >= 0),
            protein_g REAL CHECK (protein_g IS NULL OR protein_g >= 0),
            carbohydrate_g REAL CHECK (carbohydrate_g IS NULL OR carbohydrate_g >= 0),
            fat_g REAL CHECK (fat_g IS NULL OR fat_g >= 0),
            fiber_g REAL CHECK (fiber_g IS NULL OR fiber_g >= 0),
            water_ml REAL CHECK (water_ml IS NULL OR water_ml >= 0),
            caffeine_mg REAL CHECK (caffeine_mg IS NULL OR caffeine_mg >= 0),
            alcohol_g REAL CHECK (alcohol_g IS NULL OR alcohol_g >= 0),
            nutrition_source TEXT,
            classification_source TEXT NOT NULL CHECK (classification_source IN (
                'catalog','legacy_category','unclassified','user'
            )),
            user_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (user_confirmed IN (0,1)),
            brand TEXT,
            cooking_method TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            FOREIGN KEY (meal_record_id) REFERENCES meal_records(id) ON DELETE CASCADE,
            FOREIGN KEY (food_catalog_id) REFERENCES food_catalog(id) ON DELETE SET NULL,
            CHECK (food_catalog_id IS NOT NULL OR length(trim(custom_food_name)) > 0)
        );
        CREATE INDEX idx_meal_items_record ON meal_items(meal_record_id, id);
        CREATE INDEX idx_meal_items_catalog ON meal_items(food_catalog_id, created_at);

        CREATE TABLE food_favorites (
            food_catalog_id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (food_catalog_id) REFERENCES food_catalog(id) ON DELETE CASCADE
        );

        CREATE TABLE meal_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            meal_type TEXT NOT NULL CHECK (meal_type IN (
                'breakfast','morning_snack','lunch','afternoon_snack','dinner',
                'training_fuel','bedtime_fuel','free_snack'
            )),
            items_json TEXT NOT NULL,
            supplements_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );

        INSERT INTO meal_records(
            uuid,date,meal_type,eaten_at,status,source,notes,
            legacy_meal_event_id,created_at,updated_at
        )
        SELECT lower(hex(randomblob(16))),date,meal_type,actual_meal_time,
               'completed','manual',notes,id,created_at,updated_at
        FROM meal_events;

        INSERT INTO meal_items(
            uuid,meal_record_id,food_catalog_id,custom_food_name,item_type,
            quantity,unit,normalized_weight_g,normalized_volume_ml,
            category_tags_json,nutrition_source,classification_source,
            user_confirmed,created_at,updated_at
        )
        SELECT lower(hex(randomblob(16))),r.id,
               CASE
                 WHEN i.category='hydration' THEN (SELECT id FROM food_catalog WHERE canonical_name='water')
                 ELSE (SELECT id FROM food_catalog f
                       WHERE lower(f.canonical_name)=lower(trim(i.item_name))
                          OR lower(f.display_name_en)=lower(trim(i.item_name))
                          OR f.display_name_zh=trim(i.item_name)
                       LIMIT 1)
               END,
               CASE
                 WHEN i.category='hydration' THEN NULL
                 WHEN i.item_name IS NOT NULL AND length(trim(i.item_name)) > 0
                      AND NOT EXISTS (
                        SELECT 1 FROM food_catalog f
                        WHERE lower(f.canonical_name)=lower(trim(i.item_name))
                           OR lower(f.display_name_en)=lower(trim(i.item_name))
                           OR f.display_name_zh=trim(i.item_name)
                      ) THEN trim(i.item_name)
                 WHEN i.item_name IS NULL OR length(trim(i.item_name))=0 THEN i.category
                 ELSE NULL
               END,
               CASE WHEN i.category IN ('hydration','caffeine','alcohol')
                    THEN 'beverage' ELSE 'food' END,
               i.quantity,i.unit,
               CASE WHEN i.unit='g' AND i.quantity > 0 THEN i.quantity ELSE NULL END,
               CASE WHEN i.unit='ml' AND i.quantity > 0 THEN i.quantity ELSE NULL END,
               '["' || i.category || '"]',NULL,'legacy_category',1,
               i.created_at,i.updated_at
        FROM meal_event_items i
        JOIN meal_records r ON r.legacy_meal_event_id=i.meal_event_id
        WHERE i.category!='supplement' AND i.quantity > 0;
        """,
    ),
    SchemaMigration(
        14,
        "0.14.0",
        "structured_training_details",
        "structured-training-v1-polar-authority-session-exercise-set-catalog-audit",
        """
        CREATE TABLE training_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            duration_seconds REAL CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
            polar_sport_type TEXT,
            resolved_sport_type TEXT,
            resolved_sport_type_source TEXT NOT NULL CHECK (
                resolved_sport_type_source IN (
                    'polar','manual','manual_override','healthkit','imported'
                )
            ),
            source TEXT NOT NULL CHECK (
                source IN ('polar','manual','healthkit','imported','merged')
            ),
            polar_external_id TEXT,
            average_hr REAL CHECK (average_hr IS NULL OR average_hr > 0),
            max_hr REAL CHECK (max_hr IS NULL OR max_hr > 0),
            calories REAL CHECK (calories IS NULL OR calories >= 0),
            distance_meters REAL CHECK (distance_meters IS NULL OR distance_meters >= 0),
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','completed')),
            notes TEXT,
            legacy_workout_session_id INTEGER UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            FOREIGN KEY (legacy_workout_session_id) REFERENCES workout_sessions(id)
        );
        CREATE UNIQUE INDEX idx_training_sessions_polar_external
            ON training_sessions(polar_external_id)
            WHERE polar_external_id IS NOT NULL;
        CREATE INDEX idx_training_sessions_date_start
            ON training_sessions(date,start_time,id);

        CREATE TABLE exercise_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT NOT NULL UNIQUE,
            display_name_zh TEXT NOT NULL,
            display_name_en TEXT NOT NULL,
            exercise_category TEXT NOT NULL CHECK (exercise_category IN (
                'strength','bodyweight','cardio','mobility','dance','technique',
                'rehabilitation','other'
            )),
            movement_pattern TEXT NOT NULL CHECK (movement_pattern IN (
                'squat','hinge','push','pull','carry','rotation','locomotion',
                'isolation','skill'
            )),
            primary_muscle_group TEXT,
            secondary_muscle_groups_json TEXT NOT NULL DEFAULT '[]',
            equipment TEXT,
            measurement_mode TEXT NOT NULL CHECK (measurement_mode IN (
                'weight_reps','bodyweight_reps','assisted_reps','duration',
                'distance_duration','dance_practice','freeform'
            )),
            is_unilateral INTEGER NOT NULL DEFAULT 0 CHECK (is_unilateral IN (0,1)),
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE training_exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            training_session_id INTEGER NOT NULL,
            exercise_catalog_id INTEGER,
            custom_exercise_name TEXT,
            sequence_order INTEGER NOT NULL CHECK (sequence_order > 0),
            exercise_category TEXT NOT NULL CHECK (exercise_category IN (
                'strength','bodyweight','cardio','mobility','dance','technique',
                'rehabilitation','other'
            )),
            measurement_mode TEXT NOT NULL CHECK (measurement_mode IN (
                'weight_reps','bodyweight_reps','assisted_reps','duration',
                'distance_duration','dance_practice','freeform'
            )),
            primary_muscle_group TEXT,
            equipment TEXT,
            is_unilateral INTEGER NOT NULL DEFAULT 0 CHECK (is_unilateral IN (0,1)),
            skill_proficiency REAL CHECK (
                skill_proficiency IS NULL OR skill_proficiency BETWEEN 1 AND 10
            ),
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            FOREIGN KEY (training_session_id) REFERENCES training_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (exercise_catalog_id) REFERENCES exercise_catalog(id) ON DELETE SET NULL,
            CHECK (
                exercise_catalog_id IS NOT NULL OR
                (custom_exercise_name IS NOT NULL AND length(trim(custom_exercise_name)) > 0)
            )
        );
        CREATE UNIQUE INDEX idx_training_exercise_sequence
            ON training_exercises(training_session_id,sequence_order)
            WHERE deleted_at IS NULL;
        CREATE INDEX idx_training_exercises_session
            ON training_exercises(training_session_id,id);

        CREATE TABLE training_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            training_exercise_id INTEGER NOT NULL,
            set_number INTEGER NOT NULL CHECK (set_number > 0),
            set_type TEXT NOT NULL CHECK (set_type IN (
                'warmup','working','backoff','drop','failure','technique','test','other'
            )),
            load_value REAL CHECK (load_value IS NULL OR load_value >= 0),
            load_unit TEXT NOT NULL CHECK (load_unit IN (
                'kg','lb','bodyweight','assisted_kg','none'
            )),
            reps INTEGER CHECK (reps IS NULL OR reps >= 0),
            duration_seconds REAL CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
            distance_meters REAL CHECK (distance_meters IS NULL OR distance_meters >= 0),
            resistance_level REAL CHECK (resistance_level IS NULL OR resistance_level >= 0),
            incline_percent REAL CHECK (incline_percent IS NULL OR incline_percent >= 0),
            rpe REAL CHECK (rpe IS NULL OR rpe BETWEEN 1 AND 10),
            rir REAL CHECK (rir IS NULL OR rir BETWEEN 0 AND 10),
            rest_seconds REAL CHECK (rest_seconds IS NULL OR rest_seconds >= 0),
            side TEXT NOT NULL DEFAULT 'not_applicable' CHECK (side IN (
                'bilateral','left','right','alternating','not_applicable'
            )),
            completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0,1)),
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            FOREIGN KEY (training_exercise_id) REFERENCES training_exercises(id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX idx_training_set_number
            ON training_sets(training_exercise_id,set_number)
            WHERE deleted_at IS NULL;
        CREATE INDEX idx_training_sets_exercise
            ON training_sets(training_exercise_id,id);

        INSERT INTO exercise_catalog(
            canonical_name,display_name_zh,display_name_en,exercise_category,
            movement_pattern,primary_muscle_group,secondary_muscle_groups_json,
            equipment,measurement_mode,is_unilateral
        ) VALUES
          ('barbell_back_squat','杠铃深蹲','Barbell Back Squat','strength','squat','lower_body','["glutes","core"]','barbell','weight_reps',0),
          ('deadlift','硬拉','Deadlift','strength','hinge','posterior_chain','["back","core"]','barbell','weight_reps',0),
          ('bench_press','卧推','Bench Press','strength','push','chest','["triceps","shoulders"]','barbell','weight_reps',0),
          ('overhead_press','肩上推举','Overhead Press','strength','push','shoulders','["triceps","core"]','barbell','weight_reps',0),
          ('barbell_row','杠铃划船','Barbell Row','strength','pull','back','["biceps"]','barbell','weight_reps',0),
          ('lat_pulldown','高位下拉','Lat Pulldown','strength','pull','back','["biceps"]','cable','weight_reps',0),
          ('pull_up','引体向上','Pull-up','bodyweight','pull','back','["biceps","core"]','pullup_bar','bodyweight_reps',0),
          ('leg_press','腿举','Leg Press','strength','squat','lower_body','["glutes"]','machine','weight_reps',0),
          ('lunge','弓步蹲','Lunge','strength','squat','lower_body','["glutes","core"]','free_weight','weight_reps',1),
          ('biceps_curl','二头弯举','Biceps Curl','strength','isolation','biceps','[]','free_weight','weight_reps',0),
          ('triceps_pushdown','三头下压','Triceps Pushdown','strength','isolation','triceps','[]','cable','weight_reps',0),
          ('lateral_raise','侧平举','Lateral Raise','strength','isolation','shoulders','[]','free_weight','weight_reps',0),
          ('push_up','俯卧撑','Push-up','bodyweight','push','chest','["triceps","core"]','bodyweight','bodyweight_reps',0),
          ('plank','平板支撑','Plank','bodyweight','skill','core','[]','bodyweight','duration',0),
          ('bodyweight_squat','自重深蹲','Bodyweight Squat','bodyweight','squat','lower_body','["glutes"]','bodyweight','bodyweight_reps',0),
          ('running','跑步','Running','cardio','locomotion','full_body','[]','none','distance_duration',0),
          ('cycling','骑行','Cycling','cardio','locomotion','lower_body','[]','bicycle','distance_duration',0),
          ('rowing_machine','划船机','Rowing Machine','cardio','pull','full_body','["back","lower_body"]','rowing_machine','distance_duration',0),
          ('elliptical','椭圆机','Elliptical','cardio','locomotion','full_body','[]','elliptical','distance_duration',0),
          ('hiphop_basics','Hip-Hop 基础训练','Hip-Hop Basics','dance','skill','full_body','[]','none','dance_practice',0),
          ('technique_practice','技术练习','Technique Practice','technique','skill','full_body','[]','none','dance_practice',0),
          ('combination_rehearsal','组合排练','Combination Rehearsal','dance','skill','full_body','[]','none','dance_practice',0),
          ('full_performance','完整表演','Full Performance','dance','skill','full_body','[]','none','dance_practice',0);

        INSERT INTO training_sessions(
            uuid,date,start_time,duration_seconds,polar_sport_type,
            resolved_sport_type,resolved_sport_type_source,source,
            polar_external_id,calories,status,created_at,updated_at
        )
        SELECT lower(hex(randomblob(16))),date,start_time,NULL,sport,sport,
               'polar','polar',external_id,calories,'completed',created_at,updated_at
        FROM polar_training_sessions_raw;

        INSERT INTO training_sessions(
            uuid,date,start_time,end_time,duration_seconds,resolved_sport_type,
            resolved_sport_type_source,source,status,notes,
            legacy_workout_session_id,created_at,updated_at
        )
        SELECT lower(hex(randomblob(16))),w.date,w.start_time,w.end_time,
               CASE WHEN w.duration_minutes IS NULL THEN NULL ELSE w.duration_minutes*60 END,
               w.session_type,'manual','manual','completed',w.notes,w.id,
               w.created_at,w.updated_at
        FROM workout_sessions w
        WHERE NOT EXISTS (
            SELECT 1 FROM polar_manual_session_links l
            WHERE l.workout_session_id=w.id AND l.confirmed_by_user=1
        );

        UPDATE training_sessions
        SET legacy_workout_session_id=(
                SELECT l.workout_session_id FROM polar_manual_session_links l
                WHERE l.polar_session_external_id=training_sessions.polar_external_id
                  AND l.workout_session_id IS NOT NULL AND l.confirmed_by_user=1
                LIMIT 1
            ),
            source='merged'
        WHERE polar_external_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM polar_manual_session_links l
            WHERE l.polar_session_external_id=training_sessions.polar_external_id
              AND l.workout_session_id IS NOT NULL AND l.confirmed_by_user=1
        );

        INSERT INTO training_exercises(
            uuid,training_session_id,custom_exercise_name,sequence_order,
            exercise_category,measurement_mode,primary_muscle_group,
            equipment,is_unilateral,created_at,updated_at
        )
        SELECT lower(hex(randomblob(16))),grouped.training_session_id,
               grouped.exercise_name,grouped.sequence_order,
               COALESCE(grouped.exercise_category,'other'),
               CASE
                 WHEN grouped.has_distance=1 THEN 'distance_duration'
                 WHEN grouped.has_duration=1 AND grouped.has_reps=0 THEN 'duration'
                 WHEN grouped.has_weight=1 THEN 'weight_reps'
                 ELSE 'freeform'
               END,
               NULL,NULL,0,grouped.created_at,grouped.updated_at
        FROM (
            SELECT ts.id AS training_session_id,e.exercise_name,
                   ROW_NUMBER() OVER (
                       PARTITION BY ts.id ORDER BY MIN(e.id)
                   ) AS sequence_order,
                   MAX(e.exercise_category) AS exercise_category,
                   MAX(CASE WHEN e.distance_m IS NOT NULL THEN 1 ELSE 0 END) AS has_distance,
                   MAX(CASE WHEN e.duration_seconds IS NOT NULL THEN 1 ELSE 0 END) AS has_duration,
                   MAX(CASE WHEN e.reps IS NOT NULL THEN 1 ELSE 0 END) AS has_reps,
                   MAX(CASE WHEN e.weight_kg IS NOT NULL THEN 1 ELSE 0 END) AS has_weight,
                   MIN(e.created_at) AS created_at,MAX(e.updated_at) AS updated_at
            FROM exercise_sets e
            JOIN training_sessions ts ON ts.legacy_workout_session_id=e.workout_session_id
            GROUP BY ts.id,e.exercise_name
        ) grouped;

        INSERT INTO training_sets(
            uuid,training_exercise_id,set_number,set_type,load_value,load_unit,
            reps,duration_seconds,distance_meters,rpe,rir,rest_seconds,side,
            completed,notes,created_at,updated_at
        )
        SELECT lower(hex(randomblob(16))),te.id,e.set_number,'working',e.weight_kg,
               CASE WHEN e.weight_kg IS NULL THEN 'none' ELSE 'kg' END,
               e.reps,e.duration_seconds,e.distance_m,e.rpe,e.rir,e.rest_seconds,
               'not_applicable',1,e.notes,e.created_at,e.updated_at
        FROM exercise_sets e
        JOIN training_sessions ts ON ts.legacy_workout_session_id=e.workout_session_id
        JOIN training_exercises te
          ON te.training_session_id=ts.id AND te.custom_exercise_name=e.exercise_name;
        """,
    ),
    SchemaMigration(
        15,
        "0.15.0",
        "brand_based_supplement_products",
        "brand-supplement-products-v1-versioned-catalog-ingredients-intakes-candidates-provider-gate",
        """
        CREATE TABLE supplement_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            brand_name TEXT,
            product_name TEXT NOT NULL CHECK (length(trim(product_name)) > 0),
            product_variant TEXT,
            display_name_zh TEXT,
            display_name_en TEXT,
            barcode TEXT,
            country_or_region TEXT,
            dosage_form TEXT NOT NULL CHECK (dosage_form IN (
                'powder','capsule','softgel','tablet','liquid','sachet','drop','other'
            )),
            product_kind TEXT NOT NULL DEFAULT 'supplement' CHECK (product_kind IN (
                'supplement','medication','medical_food','other'
            )),
            default_intake_unit TEXT NOT NULL CHECK (default_intake_unit IN (
                'g','mg','mcg','ml','capsule','tablet','sachet','scoop','drop','iu'
            )),
            serving_quantity REAL NOT NULL CHECK (serving_quantity > 0),
            serving_unit TEXT NOT NULL CHECK (serving_unit IN (
                'g','mg','mcg','ml','capsule','tablet','sachet','scoop','drop','iu'
            )),
            package_size TEXT,
            formula_version TEXT,
            label_version_date TEXT,
            front_label_image_path TEXT,
            facts_label_image_path TEXT,
            product_url TEXT,
            data_source TEXT NOT NULL CHECK (data_source IN (
                'manual_minimal','barcode_database','official_product_page',
                'manufacturer_label','label_ocr','trusted_database',
                'ai_assisted_search','imported'
            )),
            primary_source_reference TEXT,
            primary_source_type TEXT,
            verification_status TEXT NOT NULL DEFAULT 'unverified' CHECK (
                verification_status IN (
                    'unverified','candidate','user_confirmed','label_verified',
                    'source_verified','stale','rejected'
                )
            ),
            user_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (user_confirmed IN (0,1)),
            verified_at TEXT,
            valid_from TEXT,
            valid_to TEXT,
            supersedes_product_id INTEGER,
            formula_hash TEXT,
            label_hash TEXT,
            legacy_identity_key TEXT UNIQUE,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            FOREIGN KEY (supersedes_product_id) REFERENCES supplement_products(id),
            CHECK (verification_status != 'source_verified' OR
                   length(trim(COALESCE(primary_source_reference,''))) > 0),
            CHECK (user_confirmed = 0 OR verified_at IS NOT NULL)
        );
        CREATE INDEX idx_supplement_products_brand_name
            ON supplement_products(brand_name,product_name,is_active);
        CREATE INDEX idx_supplement_products_barcode
            ON supplement_products(barcode) WHERE barcode IS NOT NULL;

        CREATE TABLE supplement_product_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            supplement_product_id INTEGER NOT NULL,
            canonical_ingredient_name TEXT NOT NULL CHECK (
                length(trim(canonical_ingredient_name)) > 0
            ),
            display_name_zh TEXT,
            display_name_en TEXT,
            amount_per_serving REAL NOT NULL CHECK (amount_per_serving > 0),
            amount_unit TEXT NOT NULL CHECK (amount_unit IN (
                'g','mg','mcg','ml','iu'
            )),
            serving_quantity REAL NOT NULL CHECK (serving_quantity > 0),
            serving_unit TEXT NOT NULL CHECK (serving_unit IN (
                'g','mg','mcg','ml','capsule','tablet','sachet','scoop','drop','iu'
            )),
            ingredient_role TEXT NOT NULL CHECK (ingredient_role IN (
                'active','nutrient','carrier','excipient','other'
            )),
            source_reference TEXT,
            source_type TEXT NOT NULL CHECK (source_type IN (
                'user_label','official_product_page','manufacturer_label',
                'trusted_database','barcode_database','retailer_page',
                'ai_assisted_search','manual_minimal','imported'
            )),
            confidence_level TEXT NOT NULL CHECK (confidence_level IN (
                'unknown','low','medium','high','verified'
            )),
            user_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (user_confirmed IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            FOREIGN KEY (supplement_product_id) REFERENCES supplement_products(id) ON DELETE CASCADE
        );
        CREATE INDEX idx_supplement_ingredients_product
            ON supplement_product_ingredients(supplement_product_id,id);

        CREATE TABLE supplement_intake_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            meal_record_id INTEGER NOT NULL,
            supplement_product_id INTEGER,
            custom_brand_name TEXT,
            custom_product_name TEXT,
            quantity REAL NOT NULL CHECK (quantity > 0),
            unit TEXT NOT NULL CHECK (unit IN (
                'g','mg','mcg','ml','capsule','tablet','sachet','scoop','drop','iu'
            )),
            taken_at TEXT NOT NULL,
            source TEXT NOT NULL CHECK (source IN (
                'manual','copied','template','imported','legacy_migration'
            )),
            notes TEXT,
            legacy_meal_event_item_id INTEGER UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            FOREIGN KEY (meal_record_id) REFERENCES meal_records(id) ON DELETE CASCADE,
            FOREIGN KEY (supplement_product_id) REFERENCES supplement_products(id) ON DELETE SET NULL,
            FOREIGN KEY (legacy_meal_event_item_id) REFERENCES meal_event_items(id),
            CHECK (
                supplement_product_id IS NOT NULL OR
                (custom_product_name IS NOT NULL AND length(trim(custom_product_name)) > 0)
            )
        );
        CREATE INDEX idx_supplement_intakes_meal
            ON supplement_intake_records(meal_record_id,id);
        CREATE INDEX idx_supplement_intakes_product
            ON supplement_intake_records(supplement_product_id,taken_at);

        CREATE TABLE supplement_product_favorites (
            supplement_product_id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplement_product_id) REFERENCES supplement_products(id) ON DELETE CASCADE
        );

        CREATE TABLE supplement_product_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            supplement_product_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_reference TEXT NOT NULL,
            retrieved_at TEXT NOT NULL,
            payload_hash TEXT,
            conflict_status TEXT NOT NULL DEFAULT 'none' CHECK (
                conflict_status IN ('none','review_required','resolved','rejected')
            ),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplement_product_id) REFERENCES supplement_products(id) ON DELETE CASCADE
        );

        CREATE TABLE supplement_product_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            candidate_key TEXT NOT NULL UNIQUE,
            brand_name TEXT,
            product_name TEXT NOT NULL,
            product_variant TEXT,
            barcode TEXT,
            dosage_form TEXT,
            serving_quantity REAL,
            serving_unit TEXT,
            ingredient_summary_json TEXT NOT NULL DEFAULT '[]',
            source_name TEXT NOT NULL,
            source_reference TEXT NOT NULL,
            source_type TEXT NOT NULL,
            confidence REAL CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
            retrieved_at TEXT NOT NULL,
            candidate_status TEXT NOT NULL DEFAULT 'pending' CHECK (
                candidate_status IN ('pending','confirmed','rejected','deferred')
            ),
            confirmed_product_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (confirmed_product_id) REFERENCES supplement_products(id)
        );

        INSERT INTO supplement_products(
            uuid,product_name,dosage_form,product_kind,default_intake_unit,
            serving_quantity,serving_unit,data_source,verification_status,
            legacy_identity_key,created_at,updated_at
        )
        SELECT lower(hex(randomblob(16))),grouped.item_name,'other',
               CASE WHEN lower(grouped.item_name) LIKE '%finasteride%'
                          OR grouped.item_name LIKE '%非那雄胺%'
                    THEN 'medication' ELSE 'supplement' END,
               grouped.unit,1,grouped.unit,'imported','unverified',
               grouped.identity_key,grouped.created_at,grouped.updated_at
        FROM (
            SELECT trim(item_name) AS item_name,unit,
                   lower(trim(item_name)) || '|' || unit || '|' ||
                   COALESCE(lower(trim(active_component_name)),'') || '|' ||
                   COALESCE(CAST(active_amount AS TEXT),'') || '|' ||
                   COALESCE(active_unit,'') AS identity_key,
                   MIN(created_at) AS created_at,MAX(updated_at) AS updated_at
            FROM meal_event_items
            WHERE category='supplement' AND item_name IS NOT NULL
                  AND length(trim(item_name)) > 0
            GROUP BY identity_key,item_name,unit
        ) grouped;

        INSERT INTO supplement_product_ingredients(
            uuid,supplement_product_id,canonical_ingredient_name,
            amount_per_serving,amount_unit,serving_quantity,serving_unit,
            ingredient_role,source_type,confidence_level,user_confirmed,
            created_at,updated_at
        )
        SELECT lower(hex(randomblob(16))),p.id,trim(i.active_component_name),
               i.active_amount,i.active_unit,1,i.unit,'active','imported',
               'unknown',0,MIN(i.created_at),MAX(i.updated_at)
        FROM meal_event_items i
        JOIN supplement_products p ON p.legacy_identity_key=
             lower(trim(i.item_name)) || '|' || i.unit || '|' ||
             COALESCE(lower(trim(i.active_component_name)),'') || '|' ||
             COALESCE(CAST(i.active_amount AS TEXT),'') || '|' ||
             COALESCE(i.active_unit,'')
        WHERE i.category='supplement' AND i.active_component_name IS NOT NULL
              AND length(trim(i.active_component_name)) > 0
              AND i.active_amount IS NOT NULL AND i.active_unit IS NOT NULL
        GROUP BY p.id,i.active_component_name,i.active_amount,i.active_unit,i.unit;

        INSERT INTO supplement_intake_records(
            uuid,meal_record_id,supplement_product_id,quantity,unit,taken_at,
            source,notes,legacy_meal_event_item_id,created_at,updated_at
        )
        SELECT lower(hex(randomblob(16))),r.id,p.id,i.quantity,i.unit,r.eaten_at,
               'legacy_migration',i.item_notes,i.id,i.created_at,i.updated_at
        FROM meal_event_items i
        JOIN meal_records r ON r.legacy_meal_event_id=i.meal_event_id
        JOIN supplement_products p ON p.legacy_identity_key=
             lower(trim(i.item_name)) || '|' || i.unit || '|' ||
             COALESCE(lower(trim(i.active_component_name)),'') || '|' ||
             COALESCE(CAST(i.active_amount AS TEXT),'') || '|' ||
             COALESCE(i.active_unit,'')
        WHERE i.category='supplement';
        """,
    ),
    SchemaMigration(
        16,
        "0.16.0",
        "meal_planned_and_actual_times",
        "meal-time-v1-planned-actual-recommendation-history",
        "",
    ),
    SchemaMigration(
        17,
        "0.17.0",
        "expanded_common_food_catalog",
        "food-catalog-v1.1-common-foods-and-tea",
        """
        INSERT OR IGNORE INTO food_catalog(
            canonical_name,display_name_zh,display_name_en,aliases_json,
            default_unit,allowed_units_json,category_tags_json,serving_unit,
            serving_weight_g,serving_volume_ml,calories_per_100g,
            protein_per_100g,carbohydrate_per_100g,fat_per_100g,
            fiber_per_100g,water_per_100g,caffeine_per_100g,alcohol_per_100g,
            nutrition_source,data_quality
        ) VALUES
          ('whole_wheat_mantou','全麦馒头','Whole Wheat Mantou','["全麦蒸馒头","whole wheat steamed bun"]','piece','["piece","g","kg","serving"]','["carbohydrate_source","fiber_source","whole_grain"]','piece',100,NULL,223,7.8,44.3,1.2,4.3,43.0,0,0,'builtin_reference_v1.1','reference'),
          ('whole_wheat_toast','全麦吐司','Whole Wheat Toast','["全麦面包","whole wheat bread"]','slice','["slice","g","kg","serving"]','["carbohydrate_source","fiber_source","whole_grain"]','slice',30,NULL,247,13.0,41.0,4.2,6.8,37.0,0,0,'builtin_reference_v1.1','reference'),
          ('lettuce','生菜','Lettuce','["莴苣叶","leaf lettuce"]','g','["g","kg","serving"]','["vegetable","fiber_source"]','serving',100,NULL,15,1.36,2.87,0.15,1.3,95.15,0,0,'builtin_reference_v1.1','reference'),
          ('carrot','胡萝卜','Carrot','["红萝卜"]','g','["g","kg","piece","serving"]','["vegetable","fiber_source"]','piece',61,NULL,41,0.93,9.58,0.24,2.8,88.29,0,0,'builtin_reference_v1.1','reference'),
          ('tomato','番茄','Tomato','["西红柿"]','g','["g","kg","piece","serving"]','["vegetable","fiber_source"]','piece',123,NULL,18,0.88,3.89,0.2,1.2,94.52,0,0,'builtin_reference_v1.1','reference'),
          ('ham_slice','火腿片','Ham Slice','["切片火腿","sliced ham"]','slice','["slice","g","kg","serving"]','["protein_source","animal_food"]','slice',25,NULL,145,21.0,1.5,7.0,0,70.0,0,0,'builtin_reference_v1.1','limited'),
          ('pumpkin_seeds','南瓜籽','Pumpkin Seeds','["南瓜子","pepitas"]','g','["g","kg","serving","spoon"]','["protein_source","fat_source","fiber_source","nuts_and_seeds"]','serving',28,NULL,559,30.2,10.7,49.1,6.0,5.2,0,0,'builtin_reference_v1.1','reference'),
          ('apple','苹果','Apple','["鲜苹果"]','piece','["piece","g","kg"]','["fruit","carbohydrate_source","fiber_source"]','piece',182,NULL,52,0.26,13.81,0.17,2.4,85.56,0,0,'builtin_reference_v1.1','reference'),
          ('tea','茶','Tea','["茶水","泡茶","brewed tea"]','cup','["cup","ml","l"]','["beverage","hydration","caffeine_source"]','cup',240,240,1,0,0.3,0,0,99.7,11,0,'builtin_reference_v1.1','reference');
        """,
    ),
    SchemaMigration(
        18,
        "0.18.0",
        "common_supplement_product_options",
        "supplement-products-v1-common-options",
        """
        INSERT OR IGNORE INTO supplement_products(
            uuid,brand_name,product_name,product_variant,display_name_zh,display_name_en,
            dosage_form,product_kind,default_intake_unit,serving_quantity,serving_unit,
            data_source,verification_status,legacy_identity_key
        ) VALUES
          (lower(hex(randomblob(16))),NULL,'鱼油',NULL,'鱼油','Fish Oil','softgel','supplement','capsule',1,'capsule','imported','unverified','builtin:fish_oil'),
          (lower(hex(randomblob(16))),NULL,'复合维生素',NULL,'复合维生素','Multivitamin','tablet','supplement','tablet',1,'tablet','imported','unverified','builtin:multivitamin'),
          (lower(hex(randomblob(16))),NULL,'叶黄素',NULL,'叶黄素','Lutein','capsule','supplement','capsule',1,'capsule','imported','unverified','builtin:lutein'),
          (lower(hex(randomblob(16))),NULL,'D3K2',NULL,'D3K2','Vitamin D3K2','capsule','supplement','capsule',1,'capsule','imported','unverified','builtin:vitamin_d3k2'),
          (lower(hex(randomblob(16))),NULL,'镁',NULL,'镁','Magnesium','tablet','supplement','tablet',1,'tablet','imported','unverified','builtin:magnesium'),
          (lower(hex(randomblob(16))),NULL,'一水肌酸',NULL,'一水肌酸','Creatine Monohydrate','powder','supplement','g',5,'g','imported','unverified','builtin:creatine_monohydrate'),
          (lower(hex(randomblob(16))),NULL,'谷氨酰胺',NULL,'谷氨酰胺','Glutamine','powder','supplement','g',5,'g','imported','unverified','builtin:glutamine'),
          (lower(hex(randomblob(16))),NULL,'瓜氨酸',NULL,'瓜氨酸','Citrulline','powder','supplement','g',5,'g','imported','unverified','builtin:citrulline'),
          (lower(hex(randomblob(16))),NULL,'精氨酸',NULL,'精氨酸','Arginine','powder','supplement','g',5,'g','imported','unverified','builtin:arginine'),
          (lower(hex(randomblob(16))),NULL,'牛磺酸',NULL,'牛磺酸','Taurine','capsule','supplement','mg',500,'mg','imported','unverified','builtin:taurine'),
          (lower(hex(randomblob(16))),NULL,'辅酶Q10',NULL,'辅酶Q10','Coenzyme Q10','softgel','supplement','mg',100,'mg','imported','unverified','builtin:coq10'),
          (lower(hex(randomblob(16))),NULL,'维生素D',NULL,'维生素D','Vitamin D','capsule','supplement','iu',1000,'iu','imported','unverified','builtin:vitamin_d');
        """,
    ),
    SchemaMigration(
        19,
        "0.19.0",
        "combined_d3k2_magnesium_option",
        "supplement-product-d3k2-magnesium-combination",
        """
        INSERT OR IGNORE INTO supplement_products(
            uuid,brand_name,product_name,product_variant,display_name_zh,display_name_en,
            dosage_form,product_kind,default_intake_unit,serving_quantity,serving_unit,
            data_source,verification_status,legacy_identity_key
        ) VALUES(
            lower(hex(randomblob(16))),NULL,'D3K2镁',NULL,'D3K2镁','Vitamin D3K2 Magnesium',
            'capsule','supplement','capsule',1,'capsule','imported','unverified',
            'builtin:vitamin_d3k2_magnesium'
        );
        """,
    ),
    SchemaMigration(
        20,
        "0.20.0",
        "common_protein_powder_options",
        "supplement-products-v1-protein-powder-options",
        """
        INSERT OR IGNORE INTO supplement_products(
            uuid,brand_name,product_name,product_variant,display_name_zh,display_name_en,
            dosage_form,product_kind,default_intake_unit,serving_quantity,serving_unit,
            data_source,verification_status,legacy_identity_key
        ) VALUES
          (lower(hex(randomblob(16))),NULL,'分离乳清蛋白粉',NULL,'分离乳清蛋白粉','Whey Protein Isolate','powder','supplement','g',30,'g','imported','unverified','builtin:whey_isolate'),
          (lower(hex(randomblob(16))),NULL,'浓缩乳清蛋白粉',NULL,'浓缩乳清蛋白粉','Whey Protein Concentrate','powder','supplement','g',30,'g','imported','unverified','builtin:whey_concentrate'),
          (lower(hex(randomblob(16))),NULL,'水解乳清蛋白粉',NULL,'水解乳清蛋白粉','Hydrolyzed Whey Protein','powder','supplement','g',30,'g','imported','unverified','builtin:whey_hydrolyzed'),
          (lower(hex(randomblob(16))),NULL,'酪蛋白',NULL,'酪蛋白','Casein','powder','supplement','g',30,'g','imported','unverified','builtin:casein'),
          (lower(hex(randomblob(16))),NULL,'植物蛋白粉',NULL,'植物蛋白粉','Plant Protein Powder','powder','supplement','g',30,'g','imported','unverified','builtin:plant_protein');
        """,
    ),
    SchemaMigration(
        21,
        "0.21.0",
        "common_medication_options",
        "supplement-products-v1-common-medication-options",
        """
        INSERT OR IGNORE INTO supplement_products(
            uuid,brand_name,product_name,product_variant,display_name_zh,display_name_en,
            dosage_form,product_kind,default_intake_unit,serving_quantity,serving_unit,
            data_source,verification_status,legacy_identity_key
        ) VALUES
          (lower(hex(randomblob(16))),'默沙东','保法止',NULL,'保法止','Propecia','tablet','medication','tablet',1,'tablet','imported','unverified','builtin:propecia'),
          (lower(hex(randomblob(16))),NULL,'非那雄胺片',NULL,'非那雄胺片','Finasteride Tablet','tablet','medication','tablet',1,'tablet','imported','unverified','builtin:finasteride_tablet');
        """,
    ),
    SchemaMigration(
        22,
        "0.22.0",
        "separate_medication_brands",
        "medication-brand-options-separated-from-supplements",
        """
        UPDATE supplement_products
           SET brand_name='保法止', updated_at=CURRENT_TIMESTAMP
         WHERE legacy_identity_key='builtin:propecia' AND product_kind='medication';
        """,
    ),
    SchemaMigration(
        23,
        "0.23.0",
        "remove_propecia_medication_option",
        "medication-product-options-remove-propecia",
        """
        UPDATE supplement_products
           SET is_active=0, deleted_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
         WHERE legacy_identity_key='builtin:propecia' AND product_kind='medication';
        """,
    ),
    SchemaMigration(
        24,
        "0.24.0",
        "daily_nutrition_completion",
        "nutrition-day-completion-v1",
        """
        CREATE TABLE IF NOT EXISTS daily_nutrition_completion (
            date TEXT PRIMARY KEY,
            confirmed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    SchemaMigration(
        25,
        "0.25.0",
        "training_program_and_prescription_layer",
        "training-program-prescription-v1-nullable-links",
        """
        CREATE TABLE IF NOT EXISTS training_programs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('draft','active','archived')),
            start_date TEXT,
            end_date TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_training_programs_status
            ON training_programs(status,start_date,id);

        CREATE TABLE IF NOT EXISTS training_day_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            training_program_id INTEGER NOT NULL,
            day_key TEXT NOT NULL,
            day_label TEXT NOT NULL,
            sequence_order INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            FOREIGN KEY (training_program_id) REFERENCES training_programs(id) ON DELETE CASCADE,
            UNIQUE(training_program_id,day_key)
        );
        CREATE INDEX IF NOT EXISTS idx_training_day_templates_program
            ON training_day_templates(training_program_id,sequence_order,id);

        CREATE TABLE IF NOT EXISTS training_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            training_day_template_id INTEGER NOT NULL,
            module_key TEXT NOT NULL,
            module_label TEXT NOT NULL,
            sequence_order INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            FOREIGN KEY (training_day_template_id) REFERENCES training_day_templates(id) ON DELETE CASCADE,
            UNIQUE(training_day_template_id,module_key)
        );
        CREATE INDEX IF NOT EXISTS idx_training_blocks_day
            ON training_blocks(training_day_template_id,sequence_order,id);

        CREATE TABLE IF NOT EXISTS training_prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            training_block_id INTEGER NOT NULL,
            exercise_catalog_id INTEGER,
            custom_exercise_name TEXT,
            sequence_order INTEGER NOT NULL DEFAULT 1,
            prescription_name TEXT,
            planned_sets_json TEXT NOT NULL DEFAULT '[]',
            target_notes TEXT,
            hprs_snapshot_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            FOREIGN KEY (training_block_id) REFERENCES training_blocks(id) ON DELETE CASCADE,
            FOREIGN KEY (exercise_catalog_id) REFERENCES exercise_catalog(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_training_prescriptions_block
            ON training_prescriptions(training_block_id,sequence_order,id);

        ALTER TABLE training_sessions ADD COLUMN training_program_id INTEGER;
        ALTER TABLE training_sessions ADD COLUMN training_day_template_id INTEGER;
        ALTER TABLE training_sessions ADD COLUMN prescription_snapshot_json TEXT;
        ALTER TABLE training_sessions ADD COLUMN hprs_adjustment_json TEXT;
        ALTER TABLE training_exercises ADD COLUMN training_prescription_id INTEGER;
        ALTER TABLE training_exercises ADD COLUMN module_key TEXT;
        ALTER TABLE training_exercises ADD COLUMN planned_sets_json TEXT;
        ALTER TABLE training_exercises ADD COLUMN completion_status TEXT;
        CREATE INDEX IF NOT EXISTS idx_training_sessions_plan
            ON training_sessions(training_program_id,training_day_template_id,date);
        CREATE INDEX IF NOT EXISTS idx_training_exercises_prescription
            ON training_exercises(training_prescription_id);
        """,
    ),
    SchemaMigration(
        26,
        "0.26.0",
        "weekly_plan_sport_type",
        "weekly-plan-sport-type-v1",
        """
        ALTER TABLE training_day_templates
            ADD COLUMN sport_type TEXT NOT NULL DEFAULT 'indoor_strength';
        CREATE INDEX IF NOT EXISTS idx_training_day_templates_sport
            ON training_day_templates(training_program_id,sport_type,day_key);
        """,
    ),
    SchemaMigration(
        27,
        "0.27.0",
        "neural_readiness_mvp",
        "neural-readiness-v1-assessments-pvt-trials-daily-features",
        """
        CREATE TABLE IF NOT EXISTS neural_assessments (
            id TEXT PRIMARY KEY,
            assessment_date TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            timezone TEXT NOT NULL,
            protocol_version TEXT NOT NULL,
            mental_fatigue INTEGER NOT NULL CHECK (mental_fatigue BETWEEN 0 AND 10),
            mental_clarity INTEGER NOT NULL CHECK (mental_clarity BETWEEN 0 AND 10),
            task_motivation INTEGER NOT NULL CHECK (task_motivation BETWEEN 0 AND 10),
            physical_heaviness INTEGER NOT NULL CHECK (physical_heaviness BETWEEN 0 AND 10),
            caffeine_last_2h INTEGER NOT NULL DEFAULT 0 CHECK (caffeine_last_2h IN (0, 1)),
            exercise_last_2h INTEGER NOT NULL DEFAULT 0 CHECK (exercise_last_2h IN (0, 1)),
            illness_or_discomfort INTEGER NOT NULL DEFAULT 0 CHECK (illness_or_discomfort IN (0, 1)),
            interrupted INTEGER NOT NULL DEFAULT 0 CHECK (interrupted IN (0, 1)),
            valid_for_baseline INTEGER NOT NULL DEFAULT 0 CHECK (valid_for_baseline IN (0, 1)),
            device_context TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_neural_assessments_date
            ON neural_assessments(assessment_date, valid_for_baseline);

        CREATE TABLE IF NOT EXISTS pvt_trials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assessment_id TEXT NOT NULL,
            trial_index INTEGER NOT NULL,
            stimulus_time_ms REAL,
            response_time_ms REAL,
            reaction_time_ms REAL,
            is_valid INTEGER NOT NULL CHECK (is_valid IN (0, 1)),
            is_false_start INTEGER NOT NULL CHECK (is_false_start IN (0, 1)),
            is_lapse_355 INTEGER NOT NULL CHECK (is_lapse_355 IN (0, 1)),
            is_lapse_500 INTEGER NOT NULL CHECK (is_lapse_500 IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (assessment_id) REFERENCES neural_assessments(id) ON DELETE CASCADE,
            UNIQUE(assessment_id, trial_index)
        );
        CREATE INDEX IF NOT EXISTS idx_pvt_trials_assessment
            ON pvt_trials(assessment_id, trial_index);

        CREATE TABLE IF NOT EXISTS daily_neural_features (
            date TEXT PRIMARY KEY,
            assessment_id TEXT NOT NULL UNIQUE,
            trial_count INTEGER NOT NULL,
            valid_trial_count INTEGER NOT NULL,
            median_rt_ms REAL,
            mean_rt_ms REAL,
            mean_response_speed REAL,
            fastest_10pct_rt_ms REAL,
            slowest_10pct_rt_ms REAL,
            rt_standard_deviation REAL,
            rt_coefficient_of_variation REAL,
            lapse_355_count INTEGER NOT NULL,
            lapse_500_count INTEGER NOT NULL,
            false_start_count INTEGER NOT NULL,
            first_half_median_rt_ms REAL,
            second_half_median_rt_ms REAL,
            time_on_task_change_ms REAL,
            mental_fatigue INTEGER NOT NULL,
            mental_clarity INTEGER NOT NULL,
            task_motivation INTEGER NOT NULL,
            physical_heaviness INTEGER NOT NULL,
            sleep_score REAL,
            nightly_hrv_rmssd REAL,
            morning_rmssd REAL,
            baseline_status TEXT NOT NULL,
            baseline_sample_count INTEGER NOT NULL DEFAULT 0,
            baseline_deviations_json TEXT NOT NULL DEFAULT '{}',
            confidence_level TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (assessment_id) REFERENCES neural_assessments(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_daily_neural_features_baseline
            ON daily_neural_features(date, baseline_status);
        """,
    ),
    SchemaMigration(
        28,
        "0.28.0",
        "cognitive_training_studio_mvp",
        "cognitive-training-studio-v1-sessions-tasks-trials-progress-preferences",
        """
        CREATE TABLE IF NOT EXISTS cognitive_training_sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'local_user',
            training_plan TEXT NOT NULL CHECK(training_plan IN ('focus_alertness','working_memory')),
            session_mode TEXT NOT NULL CHECK(session_mode IN ('quick','standard')),
            started_at TEXT NOT NULL,
            completed_at TEXT,
            timezone TEXT NOT NULL,
            total_duration_seconds REAL,
            completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0,1)),
            interrupted INTEGER NOT NULL DEFAULT 0 CHECK(interrupted IN (0,1)),
            device_context TEXT NOT NULL DEFAULT '{}',
            app_version TEXT,
            protocol_version TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_cognitive_sessions_date
            ON cognitive_training_sessions(started_at,training_plan,session_mode);

        CREATE TABLE IF NOT EXISTS cognitive_training_task_results (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            task_type TEXT NOT NULL,
            task_order INTEGER NOT NULL,
            protocol_version TEXT NOT NULL,
            difficulty_start INTEGER,
            difficulty_end INTEGER,
            total_trials INTEGER NOT NULL DEFAULT 0,
            correct_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            omission_count INTEGER NOT NULL DEFAULT 0,
            median_rt_ms REAL,
            mean_rt_ms REAL,
            rt_cv REAL,
            accuracy REAL,
            score REAL,
            metrics_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES cognitive_training_sessions(id) ON DELETE CASCADE,
            UNIQUE(session_id,task_order)
        );

        CREATE TABLE IF NOT EXISTS cognitive_training_trials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            task_result_id TEXT NOT NULL,
            trial_index INTEGER NOT NULL,
            stimulus_type TEXT NOT NULL,
            stimulus_payload TEXT NOT NULL DEFAULT '{}',
            expected_response TEXT,
            actual_response TEXT,
            response_time_ms REAL,
            correct INTEGER,
            difficulty_level INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES cognitive_training_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(task_result_id) REFERENCES cognitive_training_task_results(id) ON DELETE CASCADE,
            UNIQUE(task_result_id,trial_index)
        );

        CREATE TABLE IF NOT EXISTS cognitive_training_progress (
            date TEXT NOT NULL,
            training_plan TEXT NOT NULL,
            session_count INTEGER NOT NULL DEFAULT 0,
            completed_session_count INTEGER NOT NULL DEFAULT 0,
            total_training_minutes REAL NOT NULL DEFAULT 0,
            average_accuracy REAL,
            median_rt_ms REAL,
            highest_difficulty INTEGER,
            adherence_rate REAL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(date,training_plan)
        );

        CREATE TABLE IF NOT EXISTS cognitive_training_preferences (
            id INTEGER PRIMARY KEY CHECK(id=1),
            preferred_session_mode TEXT NOT NULL DEFAULT 'standard',
            preferred_training_plan TEXT NOT NULL DEFAULT 'focus_alertness',
            weekly_goal_sessions INTEGER NOT NULL DEFAULT 3,
            sound_enabled INTEGER NOT NULL DEFAULT 0,
            haptics_enabled INTEGER NOT NULL DEFAULT 1,
            reduced_motion INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT OR IGNORE INTO cognitive_training_preferences(id) VALUES(1);
        """,
    ),
    SchemaMigration(
        29,
        "0.29.0",
        "alertness_probe_protocols",
        "alertness-probe-v1-short-and-calibration-baselines",
        """
        ALTER TABLE neural_assessments ADD COLUMN test_mode TEXT;
        ALTER TABLE neural_assessments ADD COLUMN duration_seconds REAL;
        ALTER TABLE neural_assessments ADD COLUMN baseline_group TEXT;
        ALTER TABLE neural_assessments ADD COLUMN calibration_trigger TEXT;
        ALTER TABLE neural_assessments ADD COLUMN calibration_reason TEXT;
        ALTER TABLE neural_assessments ADD COLUMN metrics_json TEXT;
        ALTER TABLE daily_neural_features ADD COLUMN test_mode TEXT;
        ALTER TABLE daily_neural_features ADD COLUMN duration_seconds REAL;
        ALTER TABLE daily_neural_features ADD COLUMN protocol_version TEXT;
        ALTER TABLE daily_neural_features ADD COLUMN baseline_group TEXT;
        ALTER TABLE daily_neural_features ADD COLUMN fastest_20pct_rt_ms REAL;
        ALTER TABLE daily_neural_features ADD COLUMN slowest_20pct_rt_ms REAL;
        UPDATE neural_assessments
           SET test_mode='legacy_3min', baseline_group='legacy_3min'
         WHERE protocol_version='pvt_b_v1' AND test_mode IS NULL;
        CREATE INDEX IF NOT EXISTS idx_neural_assessments_baseline_group
            ON neural_assessments(test_mode, protocol_version, baseline_group, assessment_date);
        """,
    ),
    SchemaMigration(
        30,
        "0.30.0",
        "neural_assessment_preferences",
        "neural-assessment-v1-remember-condition-preferences",
        """
        CREATE TABLE IF NOT EXISTS neural_assessment_preferences (
            id INTEGER PRIMARY KEY CHECK(id=1),
            condition_preferences_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT OR IGNORE INTO neural_assessment_preferences(id) VALUES(1);
        """,
    ),
    SchemaMigration(
        31,
        "0.31.1",
        "cognitive_control_speed_training",
        "cognitive-control-speed-v1-plan-constraint",
        """
        PRAGMA foreign_keys=OFF;
        ALTER TABLE cognitive_training_trials RENAME TO cognitive_training_trials_legacy;
        ALTER TABLE cognitive_training_task_results RENAME TO cognitive_training_task_results_legacy;
        ALTER TABLE cognitive_training_sessions RENAME TO cognitive_training_sessions_legacy;
        CREATE TABLE cognitive_training_sessions (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'local_user',
            training_plan TEXT NOT NULL CHECK(training_plan IN ('focus_alertness','working_memory','cognitive_control_speed')),
            session_mode TEXT NOT NULL CHECK(session_mode IN ('quick','standard')), started_at TEXT NOT NULL, completed_at TEXT,
            timezone TEXT NOT NULL, total_duration_seconds REAL, completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0,1)),
            interrupted INTEGER NOT NULL DEFAULT 0 CHECK(interrupted IN (0,1)), device_context TEXT NOT NULL DEFAULT '{}',
            app_version TEXT, protocol_version TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO cognitive_training_sessions SELECT * FROM cognitive_training_sessions_legacy;
        CREATE TABLE cognitive_training_task_results (
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL, task_type TEXT NOT NULL, task_order INTEGER NOT NULL,
            protocol_version TEXT NOT NULL, difficulty_start INTEGER, difficulty_end INTEGER, total_trials INTEGER NOT NULL DEFAULT 0,
            correct_count INTEGER NOT NULL DEFAULT 0, error_count INTEGER NOT NULL DEFAULT 0, omission_count INTEGER NOT NULL DEFAULT 0,
            median_rt_ms REAL, mean_rt_ms REAL, rt_cv REAL, accuracy REAL, score REAL, metrics_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(session_id) REFERENCES cognitive_training_sessions(id) ON DELETE CASCADE,
            UNIQUE(session_id,task_order)
        );
        INSERT INTO cognitive_training_task_results SELECT * FROM cognitive_training_task_results_legacy;
        CREATE TABLE cognitive_training_trials (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, task_result_id TEXT NOT NULL, trial_index INTEGER NOT NULL,
            stimulus_type TEXT NOT NULL, stimulus_payload TEXT NOT NULL DEFAULT '{}', expected_response TEXT, actual_response TEXT,
            response_time_ms REAL, correct INTEGER, difficulty_level INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES cognitive_training_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(task_result_id) REFERENCES cognitive_training_task_results(id) ON DELETE CASCADE, UNIQUE(task_result_id,trial_index)
        );
        INSERT INTO cognitive_training_trials SELECT * FROM cognitive_training_trials_legacy;
        DROP TABLE cognitive_training_trials_legacy;
        DROP TABLE cognitive_training_task_results_legacy;
        DROP TABLE cognitive_training_sessions_legacy;
        CREATE INDEX IF NOT EXISTS idx_cognitive_sessions_date ON cognitive_training_sessions(started_at,training_plan,session_mode);
        PRAGMA foreign_keys=ON;
        """,
    ),
    SchemaMigration(
        32,
        "0.32.0",
        "nutrition_targets",
        "nutrition-targets-v1-metric-range",
        """
        CREATE TABLE IF NOT EXISTS nutrition_targets (
            metric TEXT PRIMARY KEY,
            minimum_value REAL NOT NULL CHECK(minimum_value >= 0),
            maximum_value REAL CHECK(maximum_value IS NULL OR maximum_value >= minimum_value),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    SchemaMigration(
        33,
        "0.33.0",
        "nutrition_target_snapshots",
        "nutrition-targets-v1-daily-snapshots",
        """
        CREATE TABLE IF NOT EXISTS nutrition_target_snapshots (
            date TEXT NOT NULL,
            metric TEXT NOT NULL,
            minimum_value REAL NOT NULL CHECK(minimum_value >= 0),
            maximum_value REAL CHECK(maximum_value IS NULL OR maximum_value >= minimum_value),
            PRIMARY KEY(date,metric)
        );
        """,
    ),
    SchemaMigration(
        34,
        "0.34.0",
        "personal_training_goal",
        "personal-training-goal-v1-muscle-gain-fat-loss-maintenance",
        """
        ALTER TABLE personal_goals ADD COLUMN training_goal TEXT
            NOT NULL DEFAULT 'maintenance'
            CHECK (training_goal IN ('muscle_gain','fat_loss','maintenance'));
        """,
    ),
    SchemaMigration(
        35,
        "0.35.0",
        "food_ocr_nutrition_profiles",
        "nutrition-label-ocr-v1-confirmed-food-priority",
        """
        CREATE TABLE IF NOT EXISTS food_ocr_nutrition_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_catalog_id INTEGER NOT NULL UNIQUE,
            brand TEXT,
            basis_quantity REAL NOT NULL CHECK(basis_quantity > 0),
            basis_unit TEXT NOT NULL CHECK(basis_unit IN ('g','ml','serving')),
            calories_kcal REAL CHECK(calories_kcal IS NULL OR calories_kcal >= 0),
            protein_g REAL CHECK(protein_g IS NULL OR protein_g >= 0),
            carbohydrate_g REAL CHECK(carbohydrate_g IS NULL OR carbohydrate_g >= 0),
            fat_g REAL CHECK(fat_g IS NULL OR fat_g >= 0),
            fiber_g REAL CHECK(fiber_g IS NULL OR fiber_g >= 0),
            sodium_mg REAL CHECK(sodium_mg IS NULL OR sodium_mg >= 0),
            ocr_confidence REAL CHECK(ocr_confidence IS NULL OR (ocr_confidence BETWEEN 0 AND 1)),
            source_file_sha256 TEXT,
            ocr_text TEXT,
            user_confirmed INTEGER NOT NULL DEFAULT 1 CHECK(user_confirmed IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(food_catalog_id) REFERENCES food_catalog(id) ON DELETE CASCADE
        );
        ALTER TABLE meal_items ADD COLUMN sodium_mg REAL
            CHECK(sodium_mg IS NULL OR sodium_mg >= 0);
        """,
    ),
    SchemaMigration(
        36,
        "0.36.0",
        "custom_food_nutrition_library",
        "nutrition-label-library-v1-image-history-custom-foods",
        """
        CREATE TABLE IF NOT EXISTS custom_food_nutrition_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_catalog_id INTEGER NOT NULL,
            food_name TEXT NOT NULL,
            brand TEXT,
            source_file_name TEXT,
            source_mime_type TEXT,
            source_file_sha256 TEXT NOT NULL,
            source_image_blob BLOB NOT NULL,
            basis_quantity REAL NOT NULL CHECK(basis_quantity > 0),
            basis_unit TEXT NOT NULL CHECK(basis_unit IN ('g','ml','serving')),
            nutrients_json TEXT NOT NULL,
            ocr_text TEXT,
            ocr_confidence REAL CHECK(ocr_confidence IS NULL OR (ocr_confidence BETWEEN 0 AND 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(food_catalog_id) REFERENCES food_catalog(id) ON DELETE CASCADE,
            UNIQUE(food_catalog_id,source_file_sha256)
        );
        CREATE INDEX IF NOT EXISTS idx_custom_food_nutrition_library_food
            ON custom_food_nutrition_library(food_catalog_id,created_at DESC);
        """,
    ),
    SchemaMigration(
        37,
        '0.37.0',
        'performance_planner_v1_root',
        'performance-planner-v1-plans-blocks-checkpoints-recommendations-snapshots-root-sequence-37',
        "\n        CREATE TABLE IF NOT EXISTS performance_plans (\n            plan_id TEXT PRIMARY KEY,\n            plan_date TEXT NOT NULL UNIQUE,\n            title TEXT NOT NULL CHECK(length(trim(title)) > 0),\n            status TEXT NOT NULL DEFAULT 'active'\n                CHECK(status IN ('draft','active','completed','archived')),\n            timezone TEXT NOT NULL,\n            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,\n            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP\n        );\n        CREATE INDEX IF NOT EXISTS idx_performance_plans_plan_date\n            ON performance_plans(plan_date);\n\n        CREATE TABLE IF NOT EXISTS performance_plan_blocks (\n            block_id TEXT PRIMARY KEY,\n            plan_id TEXT NOT NULL,\n            title TEXT NOT NULL CHECK(length(trim(title)) > 0),\n            block_type TEXT NOT NULL CHECK(block_type IN (\n                'deep_work','learning','meeting','exercise',\n                'recovery','routine','other'\n            )),\n            planned_start TEXT NOT NULL,\n            planned_end TEXT NOT NULL,\n            priority TEXT NOT NULL DEFAULT 'medium'\n                CHECK(priority IN ('low','medium','high')),\n            cognitive_demand TEXT NOT NULL DEFAULT 'moderate'\n                CHECK(cognitive_demand IN ('low','moderate','high')),\n            physical_demand TEXT NOT NULL DEFAULT 'moderate'\n                CHECK(physical_demand IN ('low','moderate','high')),\n            context TEXT,\n            notes TEXT,\n            sort_order INTEGER NOT NULL DEFAULT 0,\n            status TEXT NOT NULL DEFAULT 'planned'\n                CHECK(status IN (\n                    'planned','in_progress','completed','skipped','postponed'\n                )),\n            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,\n            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,\n            FOREIGN KEY(plan_id) REFERENCES performance_plans(plan_id)\n                ON DELETE CASCADE,\n            CHECK(planned_end > planned_start)\n        );\n        CREATE INDEX IF NOT EXISTS idx_performance_blocks_plan_id\n            ON performance_plan_blocks(plan_id, sort_order, planned_start);\n\n        CREATE TABLE IF NOT EXISTS performance_checkpoints (\n            checkpoint_id TEXT PRIMARY KEY,\n            plan_id TEXT NOT NULL,\n            related_block_id TEXT,\n            checkpoint_type TEXT NOT NULL CHECK(checkpoint_type IN (\n                'quick_neural_check','control_speed_check',\n                'focus_check','working_memory_check'\n            )),\n            scheduled_at TEXT NOT NULL,\n            trigger_type TEXT NOT NULL CHECK(trigger_type IN (\n                'before_block','after_block','fixed_time','manual'\n            )),\n            status TEXT NOT NULL DEFAULT 'pending'\n                CHECK(status IN ('pending','completed','skipped')),\n            cognitive_run_id TEXT,\n            result_snapshot_json TEXT,\n            completed_at TEXT,\n            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,\n            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,\n            FOREIGN KEY(plan_id) REFERENCES performance_plans(plan_id)\n                ON DELETE CASCADE,\n            FOREIGN KEY(related_block_id)\n                REFERENCES performance_plan_blocks(block_id) ON DELETE SET NULL\n        );\n        CREATE INDEX IF NOT EXISTS idx_performance_checkpoints_plan_id\n            ON performance_checkpoints(plan_id);\n        CREATE INDEX IF NOT EXISTS idx_performance_checkpoints_scheduled_at\n            ON performance_checkpoints(scheduled_at);\n        CREATE INDEX IF NOT EXISTS idx_performance_checkpoints_related_block\n            ON performance_checkpoints(related_block_id);\n        CREATE UNIQUE INDEX IF NOT EXISTS idx_performance_checkpoints_run_id\n            ON performance_checkpoints(cognitive_run_id)\n            WHERE cognitive_run_id IS NOT NULL;\n\n        CREATE TABLE IF NOT EXISTS performance_recommendations (\n            recommendation_id TEXT PRIMARY KEY,\n            plan_id TEXT NOT NULL,\n            related_block_id TEXT,\n            recommendation_type TEXT NOT NULL CHECK(recommendation_type IN (\n                'continue_as_planned','shorten_block','add_recovery_break',\n                'move_high_demand_block','switch_to_low_demand_task',\n                'take_neural_check','resume_after_check'\n            )),\n            severity TEXT NOT NULL CHECK(severity IN ('info','warning','high')),\n            title_key TEXT NOT NULL,\n            message_key TEXT NOT NULL,\n            rationale TEXT NOT NULL,\n            source_snapshot_json TEXT NOT NULL,\n            data_sufficiency TEXT NOT NULL\n                CHECK(data_sufficiency IN ('sufficient','partial','insufficient')),\n            generated_at TEXT NOT NULL,\n            acknowledged_at TEXT,\n            applied_at TEXT,\n            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,\n            FOREIGN KEY(plan_id) REFERENCES performance_plans(plan_id)\n                ON DELETE CASCADE,\n            FOREIGN KEY(related_block_id)\n                REFERENCES performance_plan_blocks(block_id) ON DELETE SET NULL\n        );\n        CREATE INDEX IF NOT EXISTS idx_performance_recommendations_plan_id\n            ON performance_recommendations(plan_id, generated_at);\n        CREATE INDEX IF NOT EXISTS idx_performance_recommendations_related_block\n            ON performance_recommendations(related_block_id);\n        ",
    ),
    SchemaMigration(
        38,
        '0.38.0',
        'performance_planner_recommendation_fingerprints_v1_root',
        'performance-planner-v1-recommendation-fingerprint-idempotency-root-sequence-38',
        '\n        ALTER TABLE performance_recommendations\n            ADD COLUMN recommendation_fingerprint TEXT;\n        CREATE UNIQUE INDEX IF NOT EXISTS idx_performance_recommendations_fingerprint\n            ON performance_recommendations(recommendation_fingerprint)\n            WHERE recommendation_fingerprint IS NOT NULL;\n        ',
    ),
    SchemaMigration(
        39,
        "0.39.0",
        "custom_supplement_nutrition_library",
        "nutrition-label-library-v2-supplement-ocr-history",
        """
        CREATE TABLE IF NOT EXISTS custom_supplement_nutrition_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplement_product_id INTEGER,
            product_name TEXT NOT NULL,
            brand TEXT,
            source_file_name TEXT,
            source_mime_type TEXT,
            source_file_sha256 TEXT NOT NULL UNIQUE,
            source_image_blob BLOB NOT NULL,
            serving_quantity REAL,
            serving_unit TEXT,
            ingredients_json TEXT NOT NULL,
            ocr_text TEXT,
            ocr_confidence REAL CHECK(ocr_confidence IS NULL OR (ocr_confidence BETWEEN 0 AND 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(supplement_product_id) REFERENCES supplement_products(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_custom_supplement_nutrition_library_product
            ON custom_supplement_nutrition_library(supplement_product_id,created_at DESC);
        """,
    ),
    SchemaMigration(
        40,
        "0.40.0",
        "common_supplement_inorganic_salts_glucose",
        "supplement-products-v1-inorganic-salts-glucose-options",
        """
        INSERT OR IGNORE INTO supplement_products(
            uuid,brand_name,product_name,product_variant,display_name_zh,display_name_en,
            dosage_form,product_kind,default_intake_unit,serving_quantity,serving_unit,
            data_source,verification_status,legacy_identity_key
        ) VALUES
          (lower(hex(randomblob(16))),NULL,'无机盐',NULL,'无机盐','Inorganic Salts',
           'powder','supplement','g',1,'g','imported','unverified','builtin:inorganic_salts'),
          (lower(hex(randomblob(16))),NULL,'葡萄糖',NULL,'葡萄糖','Glucose',
           'powder','supplement','g',1,'g','imported','unverified','builtin:glucose');
        """,
    ),
    SchemaMigration(
        41,
        "0.41.0",
        "repair_cognitive_training_foreign_keys",
        "cognitive-training-v1-repair-session-foreign-key-targets",
        """
        PRAGMA foreign_keys=OFF;
        BEGIN IMMEDIATE;
        DROP TABLE IF EXISTS cognitive_training_trials_fk_repair;
        DROP TABLE IF EXISTS cognitive_training_task_results_fk_repair;

        CREATE TABLE cognitive_training_task_results_fk_repair (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            task_type TEXT NOT NULL,
            task_order INTEGER NOT NULL,
            protocol_version TEXT NOT NULL,
            difficulty_start INTEGER,
            difficulty_end INTEGER,
            total_trials INTEGER NOT NULL DEFAULT 0,
            correct_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            omission_count INTEGER NOT NULL DEFAULT 0,
            median_rt_ms REAL,
            mean_rt_ms REAL,
            rt_cv REAL,
            accuracy REAL,
            score REAL,
            metrics_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES cognitive_training_sessions(id) ON DELETE CASCADE,
            UNIQUE(session_id,task_order)
        );
        INSERT INTO cognitive_training_task_results_fk_repair
            SELECT * FROM cognitive_training_task_results;

        CREATE TABLE cognitive_training_trials_fk_repair (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            task_result_id TEXT NOT NULL,
            trial_index INTEGER NOT NULL,
            stimulus_type TEXT NOT NULL,
            stimulus_payload TEXT NOT NULL DEFAULT '{}',
            expected_response TEXT,
            actual_response TEXT,
            response_time_ms REAL,
            correct INTEGER,
            difficulty_level INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES cognitive_training_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(task_result_id) REFERENCES cognitive_training_task_results_fk_repair(id) ON DELETE CASCADE,
            UNIQUE(task_result_id,trial_index)
        );
        INSERT INTO cognitive_training_trials_fk_repair
            SELECT * FROM cognitive_training_trials;

        DROP TABLE cognitive_training_trials;
        DROP TABLE cognitive_training_task_results;
        ALTER TABLE cognitive_training_task_results_fk_repair
            RENAME TO cognitive_training_task_results;
        ALTER TABLE cognitive_training_trials_fk_repair
            RENAME TO cognitive_training_trials;
        COMMIT;
        PRAGMA foreign_keys=ON;
        """,
    ),
    SchemaMigration(
        42,
        "0.42.0",
        "rename_custom_food_bell_pepper_to_sweet_pepper",
        "nutrition-food-label-rename-cai-jiao-to-tian-jiao-v1",
        """
        UPDATE meal_items SET custom_food_name='甜椒'
            WHERE custom_food_name='彩椒';
        UPDATE meal_event_items SET item_name='甜椒'
            WHERE item_name='彩椒';
        UPDATE nutrition_logs SET food_name='甜椒'
            WHERE food_name='彩椒';
        UPDATE custom_food_nutrition_library SET food_name='甜椒'
            WHERE food_name='彩椒';
        UPDATE food_catalog SET display_name_zh='甜椒'
            WHERE display_name_zh='彩椒';
        """,
    ),
    SchemaMigration(
        43,
        "0.43.0",
        "add_sweet_pepper_food_catalog_option",
        "food-catalog-v1.2-sweet-pepper-with-cai-jiao-compatibility-alias",
        """
        INSERT OR IGNORE INTO food_catalog(
            canonical_name,display_name_zh,display_name_en,aliases_json,
            default_unit,allowed_units_json,category_tags_json,serving_unit,
            serving_weight_g,serving_volume_ml,calories_per_100g,
            protein_per_100g,carbohydrate_per_100g,fat_per_100g,
            fiber_per_100g,water_per_100g,caffeine_per_100g,alcohol_per_100g,
            nutrition_source,data_quality
        ) VALUES(
            'sweet_pepper','甜椒','Sweet Pepper','["彩椒","灯笼椒","bell pepper"]',
            'g','["g","kg","piece","serving"]','["vegetable","fiber_source"]',
            'piece',150,NULL,26,0.99,6.03,0.30,2.10,92.21,0,0,
            'builtin_reference_v1.2','reference'
        );
        """,
    ),
    SchemaMigration(
        44,
        "0.44.0",
        "personal_goal_daily_calorie_adjustment",
        "personal-goals-v2-goal-specific-daily-calorie-deficit-surplus",
        """
        ALTER TABLE personal_goals ADD COLUMN daily_calorie_adjustment_kcal REAL
            CHECK(daily_calorie_adjustment_kcal IS NULL OR
                  (daily_calorie_adjustment_kcal > 0 AND daily_calorie_adjustment_kcal <= 2000));
        """,
    ),
    SchemaMigration(
        45,
        "0.45.0",
        "local_coach_combined_training_summary",
        "local-coach-combined-training-summary-v1",
        """
        ALTER TABLE local_coach_recommendations
            ADD COLUMN training_summary_json TEXT NOT NULL DEFAULT '{}';
        """,
    ),
    SchemaMigration(
        46,
        "0.46.0",
        "local_user_input_habits",
        "local-user-input-habits-v1-aggregate-only",
        """
        CREATE TABLE IF NOT EXISTS user_input_habits (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
            event_count INTEGER NOT NULL DEFAULT 0 CHECK (event_count >= 0),
            habits_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT OR IGNORE INTO user_input_habits(id) VALUES (1);
        """,
    ),
    SchemaMigration(
        47,
        "0.47.0",
        "training_plan_manual_dates",
        "training-plan-v2-manual-date-per-day",
        """
        ALTER TABLE training_day_templates
            ADD COLUMN planned_date TEXT;
        """,
    ),
    SchemaMigration(
        48,
        "0.48.0",
        "independent_user_weekly_plan",
        "user-weekly-plan-v1-intent-layer-with-execution-comparison",
        """
        CREATE TABLE IF NOT EXISTS user_weekly_plans (
            plan_id TEXT PRIMARY KEY,
            week_start TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL CHECK(length(trim(title)) > 0),
            timezone TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_user_weekly_plans_week
            ON user_weekly_plans(week_start);

        CREATE TABLE IF NOT EXISTS user_weekly_plan_items (
            item_id TEXT PRIMARY KEY,
            plan_id TEXT NOT NULL,
            weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 6),
            title TEXT NOT NULL CHECK(length(trim(title)) > 0),
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN (
                'work','study','training','meal','recovery','personal','other'
            )),
            notes TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            FOREIGN KEY(plan_id) REFERENCES user_weekly_plans(plan_id)
                ON DELETE CASCADE,
            CHECK(end_time > start_time)
        );
        CREATE INDEX IF NOT EXISTS idx_user_weekly_plan_items_plan
            ON user_weekly_plan_items(plan_id,weekday,start_time,sort_order);
        """,
    ),
    SchemaMigration(
        49,
        "0.49.0",
        "training_plan_actual_matrix",
        "training-plan-actual-v1-cycles-matrix-links-comparisons",
        """
        CREATE TABLE IF NOT EXISTS training_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL CHECK(end_date >= start_date),
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'planned'
                CHECK(status IN ('planned','active','completed','archived')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_training_cycles_dates
            ON training_cycles(start_date,end_date,status);

        CREATE TABLE IF NOT EXISTS planned_training_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            training_cycle_id INTEGER,
            planned_date TEXT NOT NULL,
            session_name TEXT NOT NULL,
            training_type TEXT NOT NULL,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'planned'
                CHECK(status IN ('planned','active','completed','archived')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(training_cycle_id) REFERENCES training_cycles(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_planned_training_sessions_date
            ON planned_training_sessions(planned_date,status,id);
        CREATE INDEX IF NOT EXISTS idx_planned_training_sessions_cycle
            ON planned_training_sessions(training_cycle_id,planned_date,id);

        CREATE TABLE IF NOT EXISTS planned_training_exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            planned_session_id INTEGER NOT NULL,
            exercise_catalog_id INTEGER,
            exercise_canonical_name TEXT,
            exercise_display_name TEXT,
            order_index INTEGER NOT NULL CHECK(order_index > 0),
            target_sets INTEGER CHECK(target_sets IS NULL OR target_sets >= 0),
            target_reps INTEGER CHECK(target_reps IS NULL OR target_reps >= 0),
            target_weight REAL CHECK(target_weight IS NULL OR target_weight >= 0),
            target_load_unit TEXT NOT NULL DEFAULT 'kg',
            target_duration_seconds REAL CHECK(target_duration_seconds IS NULL OR target_duration_seconds >= 0),
            target_distance_meters REAL CHECK(target_distance_meters IS NULL OR target_distance_meters >= 0),
            target_rpe REAL CHECK(target_rpe IS NULL OR target_rpe BETWEEN 1 AND 10),
            notes TEXT,
            substitution_allowed INTEGER NOT NULL DEFAULT 0 CHECK(substitution_allowed IN (0,1)),
            module_key TEXT NOT NULL DEFAULT 'main_strength',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(planned_session_id) REFERENCES planned_training_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(exercise_catalog_id) REFERENCES exercise_catalog(id) ON DELETE SET NULL,
            CHECK(exercise_catalog_id IS NOT NULL OR exercise_canonical_name IS NOT NULL OR exercise_display_name IS NOT NULL),
            UNIQUE(planned_session_id,order_index)
        );
        CREATE INDEX IF NOT EXISTS idx_planned_training_exercises_session
            ON planned_training_exercises(planned_session_id,order_index,id);
        CREATE INDEX IF NOT EXISTS idx_planned_training_exercises_module
            ON planned_training_exercises(planned_session_id,module_key,order_index,id);

        CREATE TABLE IF NOT EXISTS planned_session_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            planned_session_id INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(planned_session_id) REFERENCES planned_training_sessions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS plan_actual_session_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            planned_session_id INTEGER NOT NULL,
            actual_training_session_id INTEGER NOT NULL UNIQUE,
            match_source TEXT NOT NULL CHECK(match_source IN ('automatic','manual')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(planned_session_id) REFERENCES planned_training_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(actual_training_session_id) REFERENCES training_sessions(id) ON DELETE CASCADE,
            UNIQUE(planned_session_id,actual_training_session_id)
        );
        CREATE INDEX IF NOT EXISTS idx_plan_actual_session_links_plan
            ON plan_actual_session_links(planned_session_id,id);

        CREATE TABLE IF NOT EXISTS plan_actual_exercise_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            planned_exercise_id INTEGER NOT NULL UNIQUE,
            actual_training_exercise_id INTEGER NOT NULL UNIQUE,
            relationship TEXT NOT NULL CHECK(relationship IN ('matched','substituted')),
            match_source TEXT NOT NULL CHECK(match_source IN ('automatic','manual')),
            reason TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(planned_exercise_id) REFERENCES planned_training_exercises(id) ON DELETE CASCADE,
            FOREIGN KEY(actual_training_exercise_id) REFERENCES training_exercises(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS plan_actual_comparisons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            planned_session_id INTEGER NOT NULL,
            actual_training_session_id INTEGER,
            planned_exercise_id INTEGER,
            actual_training_exercise_id INTEGER,
            relationship TEXT NOT NULL CHECK(relationship IN ('matched','substituted','unplanned','unmatched')),
            status TEXT NOT NULL CHECK(status IN ('completed','partially_completed','not_completed','substituted','unplanned','unmatched')),
            planned_sets REAL,
            actual_sets REAL,
            planned_reps REAL,
            actual_reps REAL,
            planned_volume REAL,
            actual_volume REAL,
            sets_completion REAL,
            reps_completion REAL,
            load_completion REAL,
            volume_completion REAL,
            overall_completion REAL,
            calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(planned_session_id) REFERENCES planned_training_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(actual_training_session_id) REFERENCES training_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(planned_exercise_id) REFERENCES planned_training_exercises(id) ON DELETE CASCADE,
            FOREIGN KEY(actual_training_exercise_id) REFERENCES training_exercises(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_plan_actual_comparisons_session
            ON plan_actual_comparisons(planned_session_id,id);
        """,
    ),
    SchemaMigration(
        50,
        "0.50.0",
        "training_cycle_domains",
        "training-plan-v1-cycle-domain-separation",
        """
        ALTER TABLE training_cycles ADD COLUMN training_domain TEXT NOT NULL DEFAULT 'indoor_strength';
        CREATE INDEX IF NOT EXISTS idx_training_cycles_domain_dates
            ON training_cycles(training_domain,start_date,end_date,status);
        """,
    ),
    SchemaMigration(
        51,
        "0.51.0",
        "custom_nutrition_library_product_kinds",
        "nutrition-label-library-v3-supplement-medication-separation",
        """
        ALTER TABLE custom_supplement_nutrition_library
            ADD COLUMN product_kind TEXT NOT NULL DEFAULT 'supplement'
            CHECK(product_kind IN ('supplement','medication'));
        UPDATE custom_supplement_nutrition_library
           SET product_kind='medication'
         WHERE supplement_product_id IN (
             SELECT id FROM supplement_products WHERE product_kind='medication'
         );
        CREATE INDEX IF NOT EXISTS idx_custom_supplement_nutrition_library_kind
            ON custom_supplement_nutrition_library(product_kind,created_at DESC);
        """,
    ),
    SchemaMigration(
        52,
        "0.52.0",
        "nutrition_recurring_plan_cycle",
        "nutrition-recurring-plan-cycle-v1-editable-cycle-settings",
        """
        CREATE TABLE IF NOT EXISTS nutrition_plan_cycle_settings (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            start_date TEXT NOT NULL,
            duration_weeks INTEGER NOT NULL DEFAULT 1 CHECK(duration_weeks >= 1),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    SchemaMigration(
        53,
        "0.53.0",
        "nutrition_plan_cycles",
        "nutrition-recurring-plan-v2-cycle-management",
        """
        CREATE TABLE IF NOT EXISTS nutrition_plan_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL CHECK(length(trim(name)) > 0),
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL CHECK(end_date >= start_date),
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'planned'
                CHECK(status IN ('planned','active','completed','archived')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_nutrition_plan_cycles_dates
            ON nutrition_plan_cycles(start_date,end_date,status);

        INSERT INTO nutrition_plan_cycles(uuid,name,start_date,end_date,status)
        SELECT lower(hex(randomblob(16))), '每周饮食循环', start_date,
               date(start_date, '+' || CAST(duration_weeks * 7 - 1 AS TEXT) || ' days'),
               'active'
          FROM nutrition_plan_cycle_settings
         WHERE id=1
           AND NOT EXISTS (SELECT 1 FROM nutrition_plan_cycles);

        ALTER TABLE user_weekly_plans
            ADD COLUMN nutrition_cycle_id INTEGER;
        CREATE INDEX IF NOT EXISTS idx_user_weekly_plans_nutrition_cycle
            ON user_weekly_plans(nutrition_cycle_id,week_start);

        UPDATE user_weekly_plans
           SET nutrition_cycle_id=(SELECT id FROM nutrition_plan_cycles
                                     ORDER BY id DESC LIMIT 1)
         WHERE nutrition_cycle_id IS NULL
           AND title IN ('周期性饮食计划','Recurring Nutrition Plan');
        """,
    ),
    SchemaMigration(
        54,
        "0.54.0",
        "ai_feedback_outputs",
        "codex-feedback-output-v1-minimum-necessary-audit",
        """
        CREATE TABLE IF NOT EXISTS ai_feedback_outputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            provider_id TEXT NOT NULL,
            model_version TEXT NOT NULL,
            data_retention_mode TEXT NOT NULL
                CHECK(data_retention_mode IN ('zero_data_retention','standard_api_retention')),
            input_snapshot_digest TEXT NOT NULL,
            output_json TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_ai_feedback_outputs_generated
            ON ai_feedback_outputs(date DESC, generated_at DESC);
        """,
    ),
)


class DatabaseMigrationError(RuntimeError):
    """Raised when persisted schema migration history is inconsistent."""


def _pending_schema_migrations(connection):
    try:
        rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
        applied = {row[0] for row in rows}
    except sqlite3.OperationalError:
        applied = set()
    return [migration for migration in SCHEMA_MIGRATIONS if migration.version not in applied]


def backup_before_migration(db_path, connection):
    """Create a point-in-time backup before applying pending migrations."""
    path = Path(db_path)
    pending = _pending_schema_migrations(connection)
    if not path.exists() or not pending or path.stat().st_size == 0:
        return None
    target_version = pending[-1].version
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{path.stem}_before_schema_{target_version}_{timestamp}{path.suffix}"
    if backup_path.exists():
        return backup_path
    backup_connection = sqlite3.connect(backup_path)
    try:
        connection.backup(backup_connection)
    finally:
        backup_connection.close()
    return backup_path


def connect(db_path=None, migrate=True):
    db_path = get_current_db_path() if db_path is None else Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if migrate:
        backup_before_migration(db_path, connection)
        init_db(connection)
    return connection


def integrity_check(connection):
    return connection.execute("PRAGMA integrity_check").fetchone()[0]


def init_db(connection):
    connection.executescript(SCHEMA)
    apply_migrations(connection)
    connection.commit()
    return connection


def apply_migrations(connection):
    apply_column_migrations(connection)
    ensure_migration_ledger(connection)
    for migration in SCHEMA_MIGRATIONS:
        existing = connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (migration.version,),
        ).fetchone()
        if not existing and migration.sql:
            connection.executescript(migration.sql)
        record_schema_migration(connection, migration)
    apply_column_migrations(connection)
    meal_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(meal_records)")
    }
    if {"eaten_at", "actual_meal_time"}.issubset(meal_columns):
        connection.execute(
            "UPDATE meal_records SET actual_meal_time=eaten_at WHERE actual_meal_time IS NULL"
        )


def apply_column_migrations(connection):
    tables = {
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    for table_name, columns in MIGRATIONS.items():
        if table_name not in tables:
            continue
        existing_columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})")
        }
        for column_name, column_type in columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                )


def ensure_migration_ledger(connection):
    connection.executescript(MIGRATION_LEDGER_SCHEMA)


def record_schema_migration(connection, migration):
    if not SEMVER_RE.fullmatch(migration.version):
        raise DatabaseMigrationError(
            f"Schema migration version is not SemVer: {migration.version}"
        )
    existing = connection.execute(
        """
        SELECT sequence, name, checksum
        FROM schema_migrations
        WHERE version = ?
        """,
        (migration.version,),
    ).fetchone()
    if existing:
        expected = (migration.sequence, migration.name, migration.checksum)
        actual = (existing[0], existing[1], existing[2])
        if actual != expected:
            raise DatabaseMigrationError(
                f"Schema migration history mismatch for {migration.version}"
            )
        return False

    sequence_conflict = connection.execute(
        "SELECT version FROM schema_migrations WHERE sequence = ?",
        (migration.sequence,),
    ).fetchone()
    if sequence_conflict:
        raise DatabaseMigrationError(
            f"Schema migration sequence {migration.sequence} is already used"
        )
    connection.execute(
        """
        INSERT INTO schema_migrations (version, sequence, name, checksum)
        VALUES (?, ?, ?, ?)
        """,
        (
            migration.version,
            migration.sequence,
            migration.name,
            migration.checksum,
        ),
    )
    return True


def current_schema_version(connection):
    row = connection.execute(
        "SELECT version FROM schema_migrations ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None
