"""Generate bilingual Markdown reports from persisted deterministic results."""

import argparse
from datetime import date
import json
from pathlib import Path

from src.i18n import get_translator, load_language_preference, normalize_language

try:
    from .db import BASE_DIR, DB_PATH, connect
except ImportError:
    from db import BASE_DIR, DB_PATH, connect


REPORTS_DIR = BASE_DIR / "reports"


class ReportError(RuntimeError):
    pass


def display_value(value, default="无"):
    return default if value is None or value == "" else value


def display_number(value):
    return 0 if value is None else value


def _recommendation(value, tr):
    aliases = {"normal_training": "normal_training", "正常训练": "normal_training", "normal": "normal_training",
               "moderate_training": "moderate_training", "适度训练": "moderate_training",
               "reduced_training": "reduced_training", "减量训练": "reduced_training",
               "recovery_priority": "recovery_priority", "恢复优先": "recovery_priority"}
    code = aliases.get(value)
    return tr(f"recovery.{code}") if code else (value or tr("recovery.no_recommendation"))


def _confidence(value, tr):
    code = str(value or "insufficient").lower().replace("_confidence", "")
    return tr(f"confidence.{code}") if code in {"high", "moderate", "low", "insufficient"} else value


def get_latest_report_date(connection):
    row = connection.execute("SELECT m.date FROM daily_recovery_metrics m JOIN recovery_scores s ON s.date=m.date ORDER BY m.date DESC LIMIT 1").fetchone()
    if not row:
        raise ReportError(get_translator(load_language_preference())("reports.missing_data"))
    return row["date"]


def load_report_data(connection, report_date=None):
    report_date = report_date or get_latest_report_date(connection)
    row = connection.execute(
        """SELECT m.date,m.steps,m.calories,m.active_calories,m.activity_duration,
                  m.training_count,m.training_duration,m.training_calories,m.sleep_duration,m.sleep_score,
                  s.recovery_score,s.score_version,s.recommendation,
                  c.confidence_score,c.confidence_level,c.data_completeness_score,c.baseline_maturity_score
           FROM daily_recovery_metrics m JOIN recovery_scores s ON s.date=m.date
           LEFT JOIN recovery_confidence c ON c.date=m.date WHERE m.date=?""",
        (report_date,),
    ).fetchone()
    if not row:
        raise ReportError(get_translator(load_language_preference())("reports.date_missing", date=report_date))
    data = dict(row)
    try:
        coach = connection.execute("SELECT * FROM local_coach_recommendations WHERE date=? ORDER BY updated_at DESC LIMIT 1", (report_date,)).fetchone()
    except Exception:
        coach = None
    if coach:
        coach = dict(coach)
        for key in ("morning_training", "evening_training", "sleep_advice", "hydration_advice", "nutrition_advice", "recovery_advice", "data_limitations", "safety_notices"):
            try: coach[key] = json.loads(coach[f"{key}_json"])
            except (KeyError, TypeError, json.JSONDecodeError): coach = None; break
    data["local_coach"] = coach
    try:
        resolved_rows = connection.execute(
            """SELECT domain,field_name,resolved_value_json,value_source,
                      source_record_id,is_fallback,is_manual_override,
                      resolution_reason,resolution_version
               FROM resolved_daily_fields WHERE date=?
               ORDER BY domain,field_name,updated_at DESC""",
            (report_date,),
        ).fetchall()
        resolved = {}
        for resolved_row in resolved_rows:
            if resolved_row["field_name"] == "notes":
                continue
            domain = resolved.setdefault(resolved_row["domain"], {})
            if resolved_row["field_name"] in domain:
                continue
            try:
                value = json.loads(resolved_row["resolved_value_json"])
            except (TypeError, json.JSONDecodeError):
                value = None
            domain[resolved_row["field_name"]] = {
                "value": value,
                "value_source": resolved_row["value_source"],
                "source_record_id": resolved_row["source_record_id"],
                "is_fallback": bool(resolved_row["is_fallback"]),
                "is_manual_override": bool(resolved_row["is_manual_override"]),
                "resolution_reason": resolved_row["resolution_reason"],
                "resolution_version": resolved_row["resolution_version"],
                "data_date": report_date,
            }
        data["resolved_fields"] = resolved
    except Exception:
        data["resolved_fields"] = {}
    try:
        from .personal_logging.summaries import build_body_summary
        data["body_summary"] = build_body_summary(connection, report_date)
        data["nutrition_summary"] = dict(connection.execute("SELECT * FROM daily_nutrition_summary WHERE date=?", (report_date,)).fetchone() or {})
        data["manual_training_summary"] = dict(connection.execute("SELECT * FROM daily_training_summary WHERE date=?", (report_date,)).fetchone() or {})
        data["ai_context_generated"] = any((BASE_DIR / "exports" / "ai_context").glob(f"ai_context_{report_date}.*"))
    except Exception:
        data.update(body_summary={}, nutrition_summary={}, manual_training_summary={}, ai_context_generated=False)
    try:
        from .local_coach.prospective import evaluate_prospective
        data["prospective_evaluation"] = evaluate_prospective(connection)
    except (ImportError, OSError, RuntimeError, ValueError):
        data["prospective_evaluation"] = None
    try:
        kubios = connection.execute(
            """SELECT n.date,n.source_type,n.rmssd_ms,n.mean_hr_bpm,n.readiness_percent,
                      n.pns_index,n.sns_index,n.measurement_quality,
                      d.rmssd_vs_baseline_percent,d.mean_hr_vs_baseline_percent,
                      d.readiness_vs_baseline_percent
               FROM kubios_hrv_normalized n LEFT JOIN kubios_hrv_derived d ON d.date=n.date
               WHERE n.date<=? AND n.selected_as_primary=1 ORDER BY n.date DESC,n.measurement_time DESC LIMIT 1""",
            (report_date,),
        ).fetchone()
        data["kubios_summary"] = dict(kubios) if kubios else {}
        if kubios:
            age = max((date.fromisoformat(report_date) - date.fromisoformat(kubios["date"])).days, 0)
            data["kubios_summary"].update(freshness_days=age, is_historical=age > 3)
    except Exception:
        data["kubios_summary"] = {}
    return data


def _coach_advice(section, entry, tr):
    if section == "nutrition": return tr("local_coach.nutrition_advice")
    status = entry.get("status", "insufficient_data")
    return tr(f"local_coach.{section}_advice.{status}")


def render_coach_section(coach, language="zh-CN"):
    tr = get_translator(language)
    if not coach:
        return f"## {tr('reports.local_coach')}\n\n{tr('local_coach.missing')}\n\n{tr('local_coach.disclaimer')}\n"
    return f"""## {tr('reports.local_coach')}

- {tr('local_coach.morning_strength')}: {_coach_advice('training', coach['morning_training'], tr)}
- {tr('local_coach.evening_hiphop')}: {_coach_advice('training', coach['evening_training'], tr)}
- {tr('local_coach.sleep')}: {_coach_advice('sleep', coach['sleep_advice'], tr)}
- {tr('local_coach.recovery')}: {_coach_advice('recovery', coach['recovery_advice'], tr)}
- {tr('local_coach.hydration')}: {_coach_advice('hydration', coach['hydration_advice'], tr)}
- {tr('local_coach.nutrition')}: {_coach_advice('nutrition', coach['nutrition_advice'], tr)}

{tr('local_coach.disclaimer')}
"""


def render_prospective_section(progress, language="zh-CN"):
    if not progress: return ""
    tr = get_translator(language)
    separator = "：" if normalize_language(language) != "en" else ": "
    return f"""## {tr('local_coach.progress')}

- {tr('common.status')}{separator}{progress['status']}
- {tr('reports.eligible_days')}{separator}{progress['eligible_unique_days']} / {progress['target_unique_days']}
- {tr('reports.remaining_days')}{separator}{progress['remaining_unique_days']}
- {tr('reports.late_backfill')}{separator}{progress['late_generation_count']}

{tr('reports.prospective_note')}
"""


def render_report(data, language="zh-CN"):
    language = normalize_language(language); tr = get_translator(language)
    body = data.get("body_summary") or {}; nutrition = data.get("nutrition_summary") or {}; manual = data.get("manual_training_summary") or {}
    coach_section = render_coach_section(data.get("local_coach"), language)
    prospective_section = render_prospective_section(data.get("prospective_evaluation"), language)
    kubios = data.get("kubios_summary") or {}
    no_data = tr("common.no_data")
    separator = "：" if language != "en" else ": "
    resolved = data.get("resolved_fields") or {}
    activity_resolved = resolved.get("activity") or {}
    sleep_resolved = resolved.get("sleep") or {}
    recovery_resolved = resolved.get("recovery") or {}

    def resolved_value(domain, field_name, fallback=None):
        field = domain.get(field_name) or {}
        return field.get("value") if field.get("value") not in (None, "") else fallback

    def source_suffix(domain, field_name):
        field = domain.get(field_name)
        if not field:
            return ""
        source_key = "manual_override" if field.get("is_manual_override") else field.get("value_source", "missing")
        return f" ({tr('source_labels.source')}: {tr(f'source_labels.{source_key}')})"

    activity_type = resolved_value(activity_resolved, "activity_type", no_data)
    if isinstance(activity_type, list):
        activity_type = ", ".join(str(item) for item in activity_type)
    subjective_lines = []
    for label_key, field_name in (
        ("manual_logging.sleep.quality", "subjective_sleep_quality"),
        ("manual_logging.sleep.awakenings", "awakenings"),
    ):
        value = resolved_value(sleep_resolved, field_name)
        if value is not None:
            subjective_lines.append(
                f"- {tr(label_key)}{separator}{value}{source_suffix(sleep_resolved, field_name)}"
            )
    for label_key, field_name in (
        ("manual_logging.recovery.subjective", "subjective_recovery"),
        ("manual_logging.recovery.fatigue", "fatigue"),
        ("manual_logging.recovery.soreness", "muscle_soreness"),
        ("manual_logging.recovery.energy", "mental_energy"),
        ("manual_logging.recovery.motivation", "training_motivation"),
        ("manual_logging.recovery.stress", "stress_level"),
    ):
        value = resolved_value(recovery_resolved, field_name)
        if value is not None:
            subjective_lines.append(
                f"- {tr(label_key)}{separator}{value}{source_suffix(recovery_resolved, field_name)}"
            )
    subjective_section = "\n".join(subjective_lines) or no_data
    return f"""# {tr('reports.title', date=data['date'])}

## {tr('reports.overview')}

- {tr('reports.date')}{separator}{data['date']}
- {tr('metrics.recovery_score')}{separator}{display_value(data.get('recovery_score'), no_data)}
- {tr('metrics.score_version')}{separator}{display_value(data.get('score_version'), no_data)}
- {tr('metrics.recommendation')}{separator}{_recommendation(data.get('recommendation'), tr)}

## {tr('reports.confidence')}

- {tr('confidence.score')}{separator}{display_value(data.get('confidence_score'), no_data)}
- {tr('confidence.level')}{separator}{_confidence(data.get('confidence_level'), tr)}
- {tr('confidence.completeness')}{separator}{display_value(data.get('data_completeness_score'), no_data)}

{tr('recovery.score_confidence_notice')}

## {tr('reports.activity')}

- {tr('metrics.steps')}{separator}{display_number(data.get('steps'))}
- {tr('reports.total_calories')}{separator}{display_number(data.get('calories'))}
- {tr('reports.active_calories')}{separator}{display_number(data.get('active_calories'))}
- {tr('reports.activity_duration')}{separator}{display_value(data.get('activity_duration'), no_data)}

## {tr('reports.training')}

- {tr('domain.exercise.sport')}{separator}{activity_type}{source_suffix(activity_resolved, 'activity_type')}
- {tr('reports.training_count')}{separator}{display_number(data.get('training_count'))}
- {tr('reports.training_duration')}{separator}{display_value(resolved_value(activity_resolved, 'duration_minutes', data.get('training_duration')), no_data)}{source_suffix(activity_resolved, 'duration_minutes')}
- {tr('reports.training_calories')}{separator}{display_number(resolved_value(activity_resolved, 'calories_kcal', data.get('training_calories')))}{source_suffix(activity_resolved, 'calories_kcal')}

## {tr('reports.sleep')}

- {tr('metrics.sleep_score')}{separator}{display_value(data.get('sleep_score'), no_data)}
- {tr('metrics.sleep_duration')}{separator}{display_value(resolved_value(sleep_resolved, 'actual_sleep_duration_minutes', data.get('sleep_duration')), no_data)}{source_suffix(sleep_resolved, 'actual_sleep_duration_minutes')}

## {tr('manual_logging.recovery.title')}

- {tr('domain.recovery.morning_rmssd')}{separator}{display_value(resolved_value(recovery_resolved, 'morning_rmssd'), no_data)}{source_suffix(recovery_resolved, 'morning_rmssd')}
- {tr('domain.recovery.morning_resting_hr')}{separator}{display_value(resolved_value(recovery_resolved, 'morning_mean_hr'), no_data)}{source_suffix(recovery_resolved, 'morning_mean_hr')}
{subjective_section}

## {tr('reports.kubios_core')}

- {tr('kubios_metrics.readiness.name')}{separator}{display_value(kubios.get('readiness_percent'), no_data)}
- {tr('kubios_metrics.rmssd.name')}{separator}{display_value(kubios.get('rmssd_ms'), no_data)} ms
- {tr('kubios_metrics.mean_hr.name')}{separator}{display_value(kubios.get('mean_hr_bpm'), no_data)} bpm
- {tr('kubios_metrics.pns.name')}{separator}{display_value(kubios.get('pns_index'), no_data)}
- {tr('kubios_metrics.sns.name')}{separator}{display_value(kubios.get('sns_index'), no_data)}
- {tr('kubios_metrics.quality.name')}{separator}{display_value(kubios.get('measurement_quality'), no_data)}
- {tr('reports.kubios_date')}{separator}{display_value(kubios.get('date'), no_data)}
- {tr('reports.kubios_source')}{separator}{display_value(kubios.get('source_type'), no_data)}
- {tr('reports.kubios_baseline')}{separator}RMSSD {display_value(kubios.get('rmssd_vs_baseline_percent'), no_data)}% / Mean HR {display_value(kubios.get('mean_hr_vs_baseline_percent'), no_data)}% / Readiness {display_value(kubios.get('readiness_vs_baseline_percent'), no_data)}%

{tr('reports.kubios_historical', days=kubios.get('freshness_days', 0)) if kubios.get('is_historical') else ''}

{tr('reports.kubios_advanced_link')}

{coach_section}

{prospective_section}

## {tr('reports.personal')}

- {tr('reports.weight')}{separator}{display_value(body.get('latest_weight_kg'), no_data)} kg
- {tr('reports.waist')}{separator}{display_value(body.get('waist_cm'), no_data)} cm
- {tr('reports.nutrition_calories')}{separator}{display_value(nutrition.get('calories'), no_data)} kcal
- {tr('reports.nutrition_completeness')}{separator}{display_value(nutrition.get('data_completeness'), no_data)}%
- {tr('reports.manual_sessions')}{separator}{display_value(manual.get('session_count'), 0)}
- {tr('reports.manual_volume')}{separator}{display_value(manual.get('total_volume_kg'), no_data)} kg
- AI Context{separator}{tr('reports.generated') if data.get('ai_context_generated') else tr('reports.not_generated')}

{tr('reports.parallel_notice')}

## {tr('reports.limitations')}

{tr('reports.missing_nutrition')}

{tr('reports.method')}

## {tr('reports.safety')}

{tr('safety.medical')}
"""


def save_report(content, report_date, reports_dir=REPORTS_DIR, language="zh-CN"):
    target = Path(reports_dir) / normalize_language(language)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"daily_report_{report_date}.md"
    path.write_text(content, encoding="utf-8")
    return path


def generate_daily_report(report_date=None, connection=None, reports_dir=REPORTS_DIR, language="zh-CN"):
    language = normalize_language(language)
    owns_connection = connection is None; connection = connection or connect()
    try:
        data = load_report_data(connection, report_date)
        content = render_report(data, language)
        return save_report(content, data["date"], reports_dir, language), content
    finally:
        if owns_connection: connection.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Generate a localized daily recovery report.")
    parser.add_argument("--date", dest="report_date")
    parser.add_argument("--language", choices=("zh-CN", "zh-TW", "en"))
    return parser.parse_args()


def main():
    args = parse_args(); language = args.language or load_language_preference()
    path, _ = generate_daily_report(args.report_date, language=language)
    tr = get_translator(language)
    print(tr("reports.saved", path=path))


if __name__ == "__main__":
    try: main()
    except ReportError as exc: raise SystemExit(str(exc))
