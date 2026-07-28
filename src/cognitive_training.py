"""Cognitive Training Studio service boundary.

Training records are intentionally independent from Neural Readiness and
Recovery tables.  Browser tasks submit one completed session in one batch.
"""
from __future__ import annotations

import json
import hashlib
import math
import statistics
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from .db import connect, get_current_db_path

PLANS = {
    "focus_alertness": ("focus_target", "focus_gonogo", "focus_visual_search"),
    "working_memory": ("memory_grid", "sequence_memory", "nback_lite"),
    "cognitive_control_speed": ("stroop_control", "task_switching", "symbol_match"),
}
PROTOCOLS = {
    "focus_target": "focus_target_v1", "focus_gonogo": "focus_gonogo_v2",
    "focus_visual_search": "focus_visual_search_v1", "memory_grid": "memory_grid_v1",
    "sequence_memory": "sequence_memory_v1", "nback_lite": "nback_lite_v1",
    "stroop_control": "stroop_control_v1", "task_switching": "task_switching_v1",
    "symbol_match": "symbol_match_v1",
}
ADAPTIVE_RULE_VERSION = "adaptive_training_v1"
CONTROL_SPEED_ADAPTIVE_RULE_VERSION = "adaptive_control_speed_v1"


def _finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _bounded_accuracy(value, correct, total):
    value = _finite(value)
    if value is None and total:
        value = correct / total
    return max(0.0, min(1.0, value)) if value is not None else None


def _rt_summary(trials):
    values = [_finite(item.get("response_time_ms")) for item in trials or []]
    values = [value for value in values if value is not None and value >= 0]
    if not values:
        return None, None, None
    mean = statistics.fmean(values)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    return statistics.median(values), mean, sd / mean if mean else None


def bounded_d_prime(hit_count, target_count, false_alarm_count, non_target_count):
    """Return finite d-prime with log-linear correction at 0/1 rates."""
    if target_count <= 0 or non_target_count <= 0:
        return None
    hit_rate = (hit_count + 0.5) / (target_count + 1)
    fa_rate = (false_alarm_count + 0.5) / (non_target_count + 1)
    return _inverse_normal(hit_rate) - _inverse_normal(fa_rate)


def _inverse_normal(p):
    return statistics.NormalDist().inv_cdf(max(1e-6, min(1 - 1e-6, float(p))))


def adapt_difficulty(current: int, accuracy: float | None, stable_rounds: int = 0, changes: int = 0) -> int:
    """Conservative round-level adaptation; never changes more than two levels."""
    if accuracy is None or changes >= 2:
        return current
    if accuracy >= 0.90 and stable_rounds >= 2:
        return min(10, current + 1)
    if accuracy < 0.75:
        return max(1, current - 1)
    return current


def _median(values):
    values = [value for value in values if value is not None]
    return statistics.median(values) if values else None


def _accuracy(trials):
    return sum(bool(item.get("correct")) for item in trials) / len(trials) if trials else None


def _rule_answer(rule, number):
    if number is None:
        return None
    if rule == "parity":
        return "left" if int(number) % 2 else "right"
    if rule == "magnitude":
        return "left" if int(number) < 5 else "right"
    return None


def _post_condition_change(trials, condition_key, condition_value):
    changed_indexes = [index for index, item in enumerate(trials[:-1]) if item.get(condition_key) == condition_value]
    after_changed = [trials[index + 1] for index in changed_indexes]
    baseline = [item for item in trials if item.get(condition_key) != condition_value]
    changed_rt = _median([_finite(item.get("response_time_ms")) for item in after_changed if item.get("correct")])
    baseline_rt = _median([_finite(item.get("response_time_ms")) for item in baseline if item.get("correct")])
    return changed_rt - baseline_rt if changed_rt is not None and baseline_rt is not None and len(after_changed) >= 2 else None


def control_speed_metrics(task_type: str, trials: list[dict[str, Any]], active_duration_seconds=None) -> dict[str, Any]:
    """Compute task metrics without substituting missing comparison data with zero."""
    valid = [item for item in trials if not item.get("practice")]
    responded = [item for item in valid if not item.get("omission")]
    rt = lambda items: _median([_finite(item.get("response_time_ms")) for item in items])
    cv_values = [_finite(item.get("response_time_ms")) for item in responded]
    mean = statistics.fmean(value for value in cv_values if value is not None) if any(value is not None for value in cv_values) else None
    cv = (statistics.stdev([value for value in cv_values if value is not None]) / mean
          if mean and sum(value is not None for value in cv_values) > 1 else None)
    base = {"total_trials": len(valid), "correct_count": sum(bool(x.get("correct")) for x in valid),
            "error_count": sum(x.get("correct") is False and not x.get("omission") for x in valid),
            "omission_count": sum(bool(x.get("omission")) for x in valid), "rt_coefficient_of_variation": cv}
    if task_type == "stroop_control":
        congruent = [x for x in valid if x.get("congruency") == "congruent"]
        incongruent = [x for x in valid if x.get("congruency") == "incongruent"]
        c_rt, i_rt = rt(congruent), rt(incongruent)
        c_acc, i_acc = _accuracy(congruent), _accuracy(incongruent)
        base.update(overall_accuracy=_accuracy(valid), congruent_trial_count=len(congruent), incongruent_trial_count=len(incongruent),
                    congruent_accuracy=c_acc, incongruent_accuracy=i_acc, median_rt_ms=rt(valid),
                    congruent_median_rt_ms=c_rt, incongruent_median_rt_ms=i_rt,
                    interference_cost_ms=i_rt-c_rt if len(congruent) >= 2 and len(incongruent) >= 2 and c_rt is not None and i_rt is not None else None,
                    interference_error_cost=c_acc-i_acc if len(congruent) >= 2 and len(incongruent) >= 2 else None,
                    post_error_slowing_ms=_post_condition_change(valid, "correct", False))
    elif task_type == "task_switching":
        repeat = [x for x in valid if x.get("switch_condition") == "repeat"]
        switched = [x for x in valid if x.get("switch_condition") == "switch"]
        r_rt, s_rt = rt(repeat), rt(switched)
        r_acc, s_acc = _accuracy(repeat), _accuracy(switched)
        perseverations = 0
        for item in valid:
            if item.get("previous_rule") is None and item.get("previous_rule_expected_response") is None:
                perseverations += int(bool(item.get("perseveration_error")))
                continue
            current_expected = item.get("expected_response") or _rule_answer(item.get("current_rule"), item.get("stimulus_number"))
            previous_expected = item.get("previous_rule_expected_response") or _rule_answer(item.get("previous_rule"), item.get("stimulus_number"))
            distinguishable = current_expected is not None and previous_expected is not None and current_expected != previous_expected
            if (item.get("switch_condition") == "switch" and item.get("correct") is False and not item.get("omission")
                    and distinguishable and item.get("actual_response") == previous_expected):
                perseverations += 1
        base.update(overall_accuracy=_accuracy(valid), initial_trial_count=sum(x.get("switch_condition") == "initial" for x in valid),
                    repeat_trial_count=len(repeat), switch_trial_count=len(switched), repeat_accuracy=r_acc, switch_accuracy=s_acc,
                    median_rt_ms=rt(valid), repeat_median_rt_ms=r_rt, switch_median_rt_ms=s_rt,
                    switch_cost_ms=s_rt-r_rt if len(repeat) >= 2 and len(switched) >= 2 and r_rt is not None and s_rt is not None else None,
                    switch_error_cost=r_acc-s_acc if len(repeat) >= 2 and len(switched) >= 2 else None,
                    rule_a_accuracy=_accuracy([x for x in valid if x.get("current_rule") == "parity"]),
                    rule_b_accuracy=_accuracy([x for x in valid if x.get("current_rule") == "magnitude"]),
                    post_switch_recovery_ms=_post_condition_change(valid, "switch_condition", "switch"),
                    perseveration_error_count=perseverations)
    elif task_type == "symbol_match":
        correct = [x for x in valid if x.get("correct")]
        seconds = _finite(active_duration_seconds)
        symbol_ids = sorted({str(item.get("symbol_id")) for item in valid if item.get("symbol_id") is not None})
        base.update(accuracy=_accuracy(valid), median_correct_rt_ms=rt(correct),
                    mean_correct_rt_ms=statistics.fmean([_finite(x.get("response_time_ms")) for x in correct if _finite(x.get("response_time_ms")) is not None]) if correct else None,
                    correct_per_minute=len(correct) / seconds * 60 if seconds else None,
                    attempted_per_minute=len(responded) / seconds * 60 if seconds else None,
                    symbol_specific_accuracy={symbol: _accuracy([x for x in valid if str(x.get("symbol_id")) == symbol]) for symbol in symbol_ids},
                    symbol_specific_median_rt={symbol: rt([x for x in correct if str(x.get("symbol_id")) == symbol]) for symbol in symbol_ids},
                    mapping_id=next((item.get("mapping_id") for item in valid if item.get("mapping_id")), None),
                    mapping_seed=next((item.get("mapping_seed") for item in valid if item.get("mapping_seed")), None))
    return base


def normalize_task_result(task: dict[str, Any], task_order: int) -> dict[str, Any]:
    task_type = str(task.get("task_type") or "")
    if task_type not in PROTOCOLS:
        raise ValueError(f"Unknown cognitive task: {task_type}")
    submitted_trials = task.get("trials") or []
    trials = [item for item in submitted_trials if not item.get("practice") and item.get("valid", True)
              and not item.get("duplicate_response") and not item.get("after_interruption")]
    correct = sum(bool(t.get("correct")) for t in trials)
    total = len(trials)
    omissions = sum(bool(t.get("omission")) for t in trials)
    errors = sum(t.get("correct") is False and not t.get("omission") for t in trials)
    median, mean, cv = _rt_summary(trials)
    accuracy = _bounded_accuracy(task.get("accuracy"), correct, total)
    score = _finite(task.get("score"))
    preview_metrics = dict(task.get("metrics") or {})
    metrics = {"preview_metrics": preview_metrics}
    if task_type == "nback_lite":
        target_count = sum(item.get("expected_response") == "same" for item in trials)
        non_target_count = sum(item.get("expected_response") == "different" for item in trials)
        hit_count = sum(item.get("expected_response") == "same" and item.get("actual_response") == "same" for item in trials)
        false_alarm_count = sum(item.get("expected_response") == "different" and item.get("actual_response") == "same" for item in trials)
        metrics.update(target_count=target_count, hit_count=hit_count, false_alarm_count=false_alarm_count,
                       miss_count=max(0, target_count - hit_count),
                       correct_rejection_count=max(0, non_target_count - false_alarm_count),
                       sensitivity_d_prime=bounded_d_prime(hit_count, target_count, false_alarm_count, non_target_count))
    elif task_type == "focus_gonogo":
        go = [item for item in trials if item.get("stimulus_type") == "go"]
        nogo = [item for item in trials if item.get("stimulus_type") == "nogo"]
        metrics.update(go_trial_count=len(go), nogo_trial_count=len(nogo),
                       correct_go_count=sum(bool(item.get("correct")) for item in go),
                       commission_error_count=sum(not bool(item.get("correct")) for item in nogo),
                       inhibition_accuracy=sum(bool(item.get("correct")) for item in nogo) / len(nogo) if nogo else None)
    if task_type in {"stroop_control", "task_switching", "symbol_match"}:
        metrics.update(control_speed_metrics(task_type, trials, task.get("active_duration_seconds")))
        metrics["adaptive_rule_version"] = CONTROL_SPEED_ADAPTIVE_RULE_VERSION
    else:
        metrics["adaptive_rule_version"] = ADAPTIVE_RULE_VERSION
    metrics.update({
        "completed": bool(task.get("completed", not task.get("partial"))),
        "interrupted": bool(task.get("interrupted")),
        "partial": bool(task.get("partial")),
        "configured_duration_seconds": _finite(task.get("configured_duration_seconds")),
        "active_duration_seconds": _finite(task.get("active_duration_seconds")),
        "actual_duration_seconds": _finite(task.get("actual_duration_seconds")),
        "difficulty_changes": task.get("difficulty_changes") or [],
        "difficulty_config": task.get("difficulty_config") or {},
    })
    return {
        "id": str(task.get("id") or uuid.uuid4().hex), "task_type": task_type,
        "task_order": task_order, "protocol_version": task.get("protocol_version") or PROTOCOLS[task_type],
        "difficulty_start": int(task.get("difficulty_start", task.get("difficulty", 1))),
        "difficulty_end": int(task.get("difficulty_end", task.get("difficulty", 1))),
        "total_trials": total, "correct_count": correct, "error_count": errors,
        "omission_count": omissions, "median_rt_ms": median, "mean_rt_ms": mean,
        "rt_cv": cv, "accuracy": accuracy, "score": score,
        "metrics": metrics, "trials": trials,
    }


def save_training_session(payload: dict[str, Any], db_path=None) -> dict[str, Any]:
    plan = payload.get("training_plan")
    mode = payload.get("session_mode")
    if plan not in PLANS or mode not in {"quick", "standard"}:
        raise ValueError("Invalid training plan or session mode")
    tasks = [normalize_task_result(task, i + 1) for i, task in enumerate(payload.get("tasks") or [])]
    submitted_types = [task["task_type"] for task in tasks]
    expected_types = list(PLANS[plan])
    interrupted = bool(payload.get("interrupted"))
    if interrupted:
        if not tasks or submitted_types != expected_types[:len(submitted_types)]:
            raise ValueError("An interrupted session must contain an ordered task prefix")
    elif submitted_types != expected_types:
        raise ValueError("A completed training session must contain its three plan tasks in order")
    session_id = str(payload.get("run_id") or payload.get("id") or uuid.uuid4().hex)
    completed = bool(payload.get("completed")) and not interrupted
    connection = connect(db_path or get_current_db_path())
    try:
        existing = connection.execute("SELECT id FROM cognitive_training_sessions WHERE id=?", (session_id,)).fetchone()
        if existing:
            return _load_saved_session(connection, session_id)
        connection.execute(
            """INSERT INTO cognitive_training_sessions
            (id,user_id,training_plan,session_mode,started_at,completed_at,timezone,total_duration_seconds,completed,interrupted,device_context,app_version,protocol_version)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET completed_at=excluded.completed_at,total_duration_seconds=excluded.total_duration_seconds,
            completed=excluded.completed,interrupted=excluded.interrupted,device_context=excluded.device_context""",
            (session_id, payload.get("user_id", "local_user"), plan, mode, payload["started_at"], payload.get("completed_at"), payload.get("timezone", "UTC"),
             _finite(payload.get("total_duration_seconds")), int(completed), int(interrupted), json.dumps(payload.get("device_context") or {}, ensure_ascii=False, sort_keys=True),
             payload.get("app_version"), payload.get("protocol_version", ADAPTIVE_RULE_VERSION)),
        )
        connection.execute("DELETE FROM cognitive_training_trials WHERE session_id=?", (session_id,))
        connection.execute("DELETE FROM cognitive_training_task_results WHERE session_id=?", (session_id,))
        for task in tasks:
            connection.execute(
                """INSERT INTO cognitive_training_task_results
                (id,session_id,task_type,task_order,protocol_version,difficulty_start,difficulty_end,total_trials,correct_count,error_count,omission_count,median_rt_ms,mean_rt_ms,rt_cv,accuracy,score,metrics_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (task["id"], session_id, task["task_type"], task["task_order"], task["protocol_version"], task["difficulty_start"], task["difficulty_end"], task["total_trials"], task["correct_count"], task["error_count"], task["omission_count"], task["median_rt_ms"], task["mean_rt_ms"], task["rt_cv"], task["accuracy"], task["score"], json.dumps(task["metrics"], ensure_ascii=False, sort_keys=True)),
            )
            connection.executemany(
                """INSERT INTO cognitive_training_trials(session_id,task_result_id,trial_index,stimulus_type,stimulus_payload,expected_response,actual_response,response_time_ms,correct,difficulty_level)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                [(session_id, task["id"], int(item.get("trial_index", i + 1)), str(item.get("stimulus_type", task["task_type"])), json.dumps(_trial_payload(item), ensure_ascii=False), item.get("expected_response"), item.get("actual_response"), _finite(item.get("response_time_ms")), None if item.get("correct") is None else int(bool(item.get("correct"))), item.get("difficulty_level", task["difficulty_end"])) for i, item in enumerate(task["trials"])],
            )
        _refresh_progress(connection, payload, tasks, plan)
        connection.commit()
        return {"session_id": session_id, "completed": completed, "interrupted": interrupted, "tasks": tasks}
    finally:
        connection.close()


def _load_saved_session(connection, session_id):
    session = connection.execute("SELECT completed,interrupted FROM cognitive_training_sessions WHERE id=?", (session_id,)).fetchone()
    rows = connection.execute("SELECT * FROM cognitive_training_task_results WHERE session_id=? ORDER BY task_order", (session_id,)).fetchall()
    tasks = []
    for row in rows:
        item = dict(row)
        item["metrics"] = json.loads(item.pop("metrics_json") or "{}")
        trial_rows = connection.execute(
            "SELECT * FROM cognitive_training_trials WHERE task_result_id=? ORDER BY trial_index", (item["id"],)
        ).fetchall()
        item["trials"] = []
        for trial_row in trial_rows:
            trial = dict(trial_row)
            trial["stimulus_payload"] = json.loads(trial["stimulus_payload"] or "{}")
            item["trials"].append(trial)
        tasks.append(item)
    return {"session_id": session_id, "completed": bool(session["completed"]), "interrupted": bool(session["interrupted"]), "tasks": tasks}


def _trial_payload(item):
    semantic = ("word_meaning", "font_color", "congruency", "input_method", "current_rule", "previous_rule",
                "switch_condition", "stimulus_number", "previous_rule_expected_response", "perseveration_error",
                "symbol_id", "expected_digit", "mapping_id", "schema_version")
    return {**(item.get("stimulus_payload") or {}), **{key: item.get(key) for key in semantic if key in item},
            "practice": False, "trial_type": item.get("trial_type")}


def _refresh_progress(connection, payload, tasks, plan):
    day = str(payload["started_at"])[:10]
    row = connection.execute(
        "SELECT COUNT(*),SUM(completed),SUM(CASE WHEN completed=1 THEN total_duration_seconds ELSE 0 END) "
        "FROM cognitive_training_sessions WHERE substr(started_at,1,10)=? AND training_plan=?", (day, plan)
    ).fetchone()
    comparable = connection.execute(
        """SELECT r.accuracy,r.median_rt_ms,r.difficulty_end
             FROM cognitive_training_task_results r
             JOIN cognitive_training_sessions s ON s.id=r.session_id
            WHERE substr(s.started_at,1,10)=? AND s.training_plan=? AND s.completed=1""",
        (day, plan),
    ).fetchall()
    accuracies = [item["accuracy"] for item in comparable if item["accuracy"] is not None]
    rts = [item["median_rt_ms"] for item in comparable if item["median_rt_ms"] is not None]
    difficulties = [item["difficulty_end"] for item in comparable if item["difficulty_end"] is not None]
    connection.execute(
        """INSERT INTO cognitive_training_progress(date,training_plan,session_count,completed_session_count,total_training_minutes,average_accuracy,median_rt_ms,highest_difficulty,adherence_rate)
        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(date,training_plan) DO UPDATE SET session_count=excluded.session_count,completed_session_count=excluded.completed_session_count,total_training_minutes=excluded.total_training_minutes,average_accuracy=excluded.average_accuracy,median_rt_ms=excluded.median_rt_ms,highest_difficulty=excluded.highest_difficulty,adherence_rate=excluded.adherence_rate,updated_at=CURRENT_TIMESTAMP""",
        (day, plan, row[0] or 0, row[1] or 0, (row[2] or 0) / 60, statistics.fmean(accuracies) if accuracies else None,
         statistics.median(rts) if rts else None, max(difficulties) if difficulties else None,
         (row[1] or 0) / row[0] if row[0] else None),
    )


def get_training_history(days=28, db_path=None):
    connection = connect(db_path or get_current_db_path(), migrate=False)
    try:
        rows = connection.execute("SELECT * FROM cognitive_training_progress WHERE date>=date('now',?) ORDER BY date DESC", (f"-{int(days)} day",)).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []
    finally:
        connection.close()


def get_control_speed_trends(days=28, db_path=None):
    """Read-only, protocol/mode-separated task history for Progress Lab."""
    connection = connect(db_path or get_current_db_path(), migrate=False)
    try:
        rows = connection.execute(
            """SELECT r.id AS task_result_id, s.started_at, s.session_mode, s.device_context, r.task_type, r.protocol_version,
                      r.difficulty_end, r.accuracy, r.median_rt_ms, r.metrics_json
                 FROM cognitive_training_sessions s JOIN cognitive_training_task_results r ON r.session_id=s.id
                WHERE s.training_plan='cognitive_control_speed' AND s.completed=1
                  AND s.started_at>=datetime('now', ?) ORDER BY s.started_at DESC""", (f"-{int(days)} days",)
        ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            metrics = json.loads(item.pop("metrics_json") or "{}")
            device = json.loads(item.get("device_context") or "{}")
            width = ((device.get("viewport") or {}).get("width"))
            device_class = "mobile" if width and width < 600 else "tablet" if width and width < 1024 else "desktop"
            config = metrics.get("difficulty_config") or {"difficulty_end": item.get("difficulty_end")}
            config_hash = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]
            methods = connection.execute(
                "SELECT stimulus_payload FROM cognitive_training_trials WHERE task_result_id=?", (item["task_result_id"],)
            ).fetchall()
            input_methods = sorted({
                json.loads(method["stimulus_payload"] or "{}").get("input_method")
                for method in methods
                if json.loads(method["stimulus_payload"] or "{}").get("input_method")
            })
            input_method = ",".join(input_methods) or "unknown"
            item.update(metrics=metrics, device_class=device_class, difficulty_config_hash=config_hash,
                        input_method=input_method,
                        comparable_group="|".join((item["task_type"], item["protocol_version"], item["session_mode"],
                                                   config_hash, device_class, input_method)))
            output.append(item)
        return output
    except Exception:
        return []
    finally:
        connection.close()


def recommendation(neural_result: dict[str, Any] | None, recent_history: list[dict[str, Any]]) -> dict[str, str]:
    if neural_result and neural_result.get("mental_fatigue", 0) >= 8:
        return {"kind": "rest", "plan": "", "reason": "主观脑力疲劳较高，今天可以跳过训练。"}
    if neural_result and neural_result.get("confidence_level") == "high" and neural_result.get("baseline_status") == "slower_than_baseline":
        return {"kind": "quick", "plan": "focus_alertness", "reason": "今日状态较低，建议选择轻量快速训练。"}
    plans = {item.get("training_plan") for item in recent_history}
    plan = "cognitive_control_speed" if "cognitive_control_speed" not in plans else ("working_memory" if "working_memory" not in plans else "focus_alertness")
    return {"kind": "standard", "plan": plan, "reason": "根据近期参与情况提供一套短时结构化训练。"}
