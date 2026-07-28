import sqlite3
import tempfile
import unittest
import json
from pathlib import Path

from src import db
from src.cognitive_training import PLANS, bounded_d_prime, control_speed_metrics, save_training_session


def task(task_type, order):
    return {
        "task_type": task_type,
        "task_order": order,
        "difficulty_start": 1,
        "difficulty_end": 2,
        "total_trials": 4,
        "correct_count": 3,
        "accuracy": 0.75,
        "trials": [{"trial_index": 1, "stimulus_type": task_type, "response_time_ms": 240, "correct": True}],
    }


class CognitiveTrainingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "training.db"

    def tearDown(self):
        self.tmp.cleanup()

    def payload(self, session_id="s1", mode="standard", interrupted=False):
        plan = "focus_alertness"
        return {
            "id": session_id,
            "training_plan": plan,
            "session_mode": mode,
            "started_at": "2026-07-28T08:00:00+08:00",
            "completed_at": "2026-07-28T08:07:00+08:00",
            "timezone": "Asia/Shanghai",
            "total_duration_seconds": 420,
            "completed": not interrupted,
            "interrupted": interrupted,
            "device_context": {"viewport": {"width": 390}, "input_mode": "touch"},
            "tasks": [task(name, i + 1) for i, name in enumerate(PLANS[plan])],
        }

    def test_d_prime_is_finite_at_extreme_rates(self):
        self.assertTrue(abs(bounded_d_prime(10, 10, 0, 10)) < 10)
        self.assertIsNone(bounded_d_prime(1, 0, 0, 1))

    def test_idempotent_session_upsert_and_mode_is_stored(self):
        first = save_training_session(self.payload(), self.path)
        second = save_training_session(self.payload(), self.path)
        self.assertEqual(first["session_id"], second["session_id"])
        connection = sqlite3.connect(self.path)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM cognitive_training_sessions").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM cognitive_training_task_results").fetchone()[0], 3)
            self.assertEqual(connection.execute("SELECT session_mode FROM cognitive_training_sessions").fetchone()[0], "standard")
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM cognitive_training_progress").fetchone()[0], 1)
        finally:
            connection.close()

    def test_interrupted_session_is_saved_but_not_completed(self):
        result = save_training_session(self.payload("s2", interrupted=True), self.path)
        self.assertTrue(result["interrupted"])
        connection = sqlite3.connect(self.path)
        try:
            self.assertEqual(connection.execute("SELECT completed,interrupted FROM cognitive_training_sessions WHERE id='s2'").fetchone(), (0, 1))
        finally:
            connection.close()

    def test_invalid_plan_task_order_is_rejected(self):
        payload = self.payload()
        payload["tasks"] = list(reversed(payload["tasks"]))
        with self.assertRaises(ValueError):
            save_training_session(payload, self.path)

    def test_control_speed_plan_and_protocols_are_saved(self):
        payload = self.payload("control")
        payload["training_plan"] = "cognitive_control_speed"
        payload["tasks"] = [task(name, index + 1) for index, name in enumerate(PLANS["cognitive_control_speed"])]
        result = save_training_session(payload, self.path)
        self.assertEqual([item["task_type"] for item in result["tasks"]], list(PLANS["cognitive_control_speed"]))
        self.assertEqual(result["tasks"][0]["protocol_version"], "stroop_control_v1")
        self.assertEqual(result["tasks"][0]["metrics"]["adaptive_rule_version"], "adaptive_control_speed_v1")

    def test_control_costs_are_null_without_both_valid_conditions(self):
        metrics = control_speed_metrics("stroop_control", [{"congruency": "congruent", "correct": True, "response_time_ms": 200}], 10)
        self.assertIsNone(metrics["interference_cost_ms"])
        self.assertIsNone(metrics["interference_error_cost"])

    def test_switch_and_symbol_metrics(self):
        switching = control_speed_metrics("task_switching", [
            {"switch_condition": "repeat", "current_rule": "parity", "correct": True, "response_time_ms": 200},
            {"switch_condition": "repeat", "current_rule": "magnitude", "correct": True, "response_time_ms": 220},
            {"switch_condition": "switch", "current_rule": "parity", "correct": True, "response_time_ms": 300},
            {"switch_condition": "switch", "current_rule": "magnitude", "correct": False, "response_time_ms": 320, "perseveration_error": True},
        ])
        self.assertEqual(switching["switch_cost_ms"], 100)
        self.assertEqual(switching["perseveration_error_count"], 1)
        symbols = control_speed_metrics("symbol_match", [
            {"correct": True, "response_time_ms": 300}, {"correct": False, "response_time_ms": 200}, {"correct": True, "response_time_ms": 500},
        ], 30)
        self.assertEqual(symbols["correct_per_minute"], 4)
        self.assertEqual(symbols["median_correct_rt_ms"], 400)

    def test_control_component_contains_isolated_practice_and_protocols(self):
        source = (Path(__file__).parents[1] / "src" / "cognitive_component_frontend" / "index.html").read_text(encoding="utf-8")
        for marker in ("stroop_control", "task_switching", "symbol_match", "stroop_practice_v1", "task_switching_practice_v1", "symbol_match_practice_v1", "adaptive_control_speed_v1", "performance.now", "开始 5 秒练习", "练习数据不进入正式成绩", "window.onkeydown"):
            self.assertIn(marker, source)
        self.assertIn("number:[1,2,3,4,6,7,8,9]", source)

    def test_run_id_is_the_idempotency_key_and_replay_does_not_duplicate(self):
        payload = self.payload("legacy-id")
        payload["run_id"] = "stable-run"
        for _ in range(3):
            result = save_training_session(payload, self.path)
            self.assertEqual(result["session_id"], "stable-run")
        connection = sqlite3.connect(self.path)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM cognitive_training_sessions").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM cognitive_training_trials").fetchone()[0], 3)
        finally:
            connection.close()

    def test_different_run_ids_create_different_sessions(self):
        first = self.payload("legacy")
        first["run_id"] = "run-one"
        second = self.payload("legacy")
        second["run_id"] = "run-two"
        save_training_session(first, self.path)
        save_training_session(second, self.path)
        connection = sqlite3.connect(self.path)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM cognitive_training_sessions").fetchone()[0], 2)
        finally:
            connection.close()

    def test_interrupted_ordered_task_prefix_is_saved(self):
        for count in (1, 2, 3):
            payload = self.payload(f"interrupted-{count}", interrupted=True)
            payload["tasks"] = payload["tasks"][:count]
            payload["tasks"][-1].update(partial=True, interrupted=True, completed=False)
            result = save_training_session(payload, self.path)
            self.assertTrue(result["interrupted"])
            self.assertEqual(len(result["tasks"]), count)
            replay = save_training_session(payload, self.path)
            self.assertEqual(len(replay["tasks"]), count)
            self.assertEqual(len(replay["tasks"][-1]["trials"]), 1)

    def test_practice_and_invalid_trials_are_never_persisted(self):
        payload = self.payload("filtered")
        payload["tasks"][0]["trials"] = [
            {"trial_index": 1, "correct": True, "response_time_ms": 200, "practice": True},
            {"trial_index": 2, "correct": True, "response_time_ms": 220, "valid": False},
            {"trial_index": 3, "correct": True, "response_time_ms": 240},
        ]
        payload["tasks"][0]["metrics"] = {"accuracy": 0.0, "median_rt_ms": 9999}
        result = save_training_session(payload, self.path)
        self.assertEqual(result["tasks"][0]["total_trials"], 1)
        self.assertEqual(result["tasks"][0]["correct_count"], 1)
        self.assertEqual(result["tasks"][0]["median_rt_ms"], 240)
        connection = sqlite3.connect(self.path)
        try:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM cognitive_training_trials WHERE task_result_id=?", (result["tasks"][0]["id"],)
            ).fetchone()[0], 1)
        finally:
            connection.close()

    def test_client_metrics_cannot_override_authoritative_control_metrics(self):
        payload = self.payload("authoritative")
        payload["training_plan"] = "cognitive_control_speed"
        payload["tasks"] = [task(name, index + 1) for index, name in enumerate(PLANS["cognitive_control_speed"])]
        payload["tasks"][0]["trials"] = [
            {"congruency": "congruent", "correct": True, "response_time_ms": 200},
            {"congruency": "congruent", "correct": True, "response_time_ms": 220},
            {"congruency": "incongruent", "correct": True, "response_time_ms": 300},
            {"congruency": "incongruent", "correct": False, "response_time_ms": 340},
        ]
        payload["tasks"][0]["metrics"] = {"interference_cost_ms": -9999}
        result = save_training_session(payload, self.path)
        self.assertEqual(result["tasks"][0]["metrics"]["interference_cost_ms"], 110)
        self.assertEqual(result["tasks"][0]["metrics"]["preview_metrics"]["interference_cost_ms"], -9999)

    def test_perseveration_fields_are_versioned_in_trial_payload(self):
        payload = self.payload("semantic")
        payload["training_plan"] = "cognitive_control_speed"
        payload["tasks"] = [task(name, index + 1) for index, name in enumerate(PLANS["cognitive_control_speed"])]
        payload["tasks"][1]["trials"] = [{
            "current_rule": "magnitude", "previous_rule": "parity", "switch_condition": "switch",
            "stimulus_number": 7, "expected_response": "right", "previous_rule_expected_response": "left",
            "actual_response": "left", "correct": False, "perseveration_error": True,
            "schema_version": "control_speed_trial_v1", "response_time_ms": 300,
        }]
        result = save_training_session(payload, self.path)
        connection = sqlite3.connect(self.path)
        try:
            raw = connection.execute(
                "SELECT stimulus_payload FROM cognitive_training_trials WHERE task_result_id=?", (result["tasks"][1]["id"],)
            ).fetchone()[0]
            stored = json.loads(raw)
            self.assertTrue(stored["perseveration_error"])
            self.assertEqual(stored["previous_rule_expected_response"], "left")
            self.assertEqual(stored["schema_version"], "control_speed_trial_v1")
        finally:
            connection.close()

    def test_memory_grid_component_contains_multi_round_progression(self):
        source = (Path(__file__).parents[1] / "src" / "cognitive_component_frontend" / "index.html").read_text(encoding="utf-8")
        self.assertIn("function memory(sec)", source)
        self.assertIn("nextRound(true)", source)
        self.assertIn("Math.min(3+round,10)", source)

    def test_every_cognitive_task_has_a_five_second_practice_entry(self):
        source = (Path(__file__).parents[1] / "src" / "cognitive_component_frontend" / "index.html").read_text(encoding="utf-8")
        self.assertIn("else practiceTask(sec)", source)
        self.assertIn("function practiceTask(sec)", source)
        self.assertIn("<h3>5 秒练习</h3>", source)
        self.assertIn("练习模式 · 不计入正式成绩", source)
        self.assertIn("开始 5 秒练习", source)
        self.assertIn("开始正式训练", source)
        for task_name in ("focus_target", "focus_visual_search", "memory_grid", "sequence_memory", "nback_lite"):
            self.assertIn(task_name, source)

    def task_practice_source(self):
        source = (Path(__file__).parents[1] / "src" / "cognitive_component_frontend" / "index.html").read_text(encoding="utf-8")
        return source.split("function clearPracticeShell()", 1)[1].split("function clearTargetPracticeTimers()", 1)[0]

    def test_four_task_practice_shell_is_timed_and_isolated(self):
        source = self.task_practice_source()
        full_source = (Path(__file__).parents[1] / "src" / "cognitive_component_frontend" / "index.html").read_text(encoding="utf-8")
        for marker in ("visual_search_practice_v1", "memory_grid_practice_v1", "sequence_memory_practice_v1", "nback_lite_practice_v1"):
            self.assertIn(marker, full_source)
        for marker in ("开始 5 秒练习", "elapsed>=3000", "elapsed>=5000", "practiceLater(finishTaskPractice,5000)", "练习模式 · 不计入正式成绩", "再练一次", "开始正式训练", "function abortPractice()"):
            self.assertIn(marker, source)
        self.assertNotIn("noteTrial", source)
        self.assertIn("clearPracticeShell()", source)
        self.assertIn("trials=[]", source)
        self.assertIn("markPracticeCompleted(task)", source)
        self.assertIn('id="skipTaskPractice"', source)
        self.assertGreaterEqual(source.count("finishTaskPractice()"), 5)

    def test_visual_search_practice_requires_one_to_four_in_order(self):
        source = self.task_practice_source()
        for marker in ("function visualSearchPractice()", "[1,2,3,4,5,6,7,8,9]", "practiceBoard(3)", "value!==next", "next>4", "请按顺序点击", "顺序正确"):
            self.assertIn(marker, source)

    def test_memory_and_sequence_practices_use_their_entry_protocols(self):
        source = self.task_practice_source()
        for marker in ("function memoryGridPractice()", "practiceBoard(3)", "targets=[first", "c.disabled=true", "点击刚才亮起的位置", "不是这个位置", "位置正确", "function sequenceMemoryPractice()", "[1,2,3,4,5,6,7,8,9]", "sequence-number", "sequence-choice-row", "记住数字顺序", "注意数字出现顺序"):
            self.assertIn(marker, source)
        full_source = (Path(__file__).parents[1] / "src" / "cognitive_component_frontend" / "index.html").read_text(encoding="utf-8")
        for marker in ("sequence-display", "sequence-digit", "从左到右记住以下数字", "数字按从左到右的顺序呈现"):
            self.assertIn(marker, full_source)
        self.assertIn('#stage input[aria-label*="按顺序输入"]', full_source)
        self.assertIn("width:min(680px,90vw)", full_source)
        for marker in ("#sequenceReady{display:none}", "点击数字区域任意位置开始填写", "sequenceMemoryPractice=function()", "练习 · 从左到右记住数字后，点击数字区域任意位置进入填写", "e.target.isConnected"):
            self.assertIn(marker, full_source)
        for marker in (".sequence-display{display:flex;align-items:center;align-content:center;justify-content:center;overflow:hidden}", "flex:1 1 0", ":has(.sequence-digit:nth-child(7))", ":has(.sequence-digit:nth-child(10))"):
            self.assertIn(marker, full_source)
        self.assertIn(".gonogo-instruction:has(.sequence-display){display:grid;justify-items:center;width:min(680px,90vw)", full_source)
        self.assertIn("practiceTask=function(sec)", full_source)
        self.assertIn("sequence_memory:['记住数字出现的顺序，然后按照相同顺序填写。','2 → 7 → 4']", full_source)
        self.assertIn("window.__gonogoRepeatObserver?.disconnect()", full_source)
        self.assertIn("window.__gonogoLastColor===color", full_source)
        self.assertIn(".gonogo-stimulus.repeat{animation:gonogo-repeat", full_source)
        self.assertIn("runTaskPractice=function()", full_source)
        self.assertIn("!stage.querySelector('.sequence-digit')", full_source)
        self.assertIn(".gonogo-instruction:has(#startTargetPractice)>h3{display:none}", full_source)
        self.assertIn("startPracticeCountdown=function(){clearPracticeShell();practiceState='countdown';let began=now(),countdownMs=1200", full_source)
        self.assertIn("targetPracticeCountdown=function(){clearTargetPracticeTimers();targetPracticeState='countdown';let began=now(),countdownMs=1200", full_source)
        self.assertIn(".gonogo-instruction:has(#startPractice)>h3", full_source)
        self.assertIn(".gonogo-instruction:has(#practiceCountdown)>p.small", full_source)
        self.assertIn(".gonogo-instruction:has(#targetPracticeCountdown)>p.small", full_source)

    def test_nback_practice_has_valid_one_and_two_back_sequences(self):
        source = self.task_practice_source()
        for marker in ("function nbackPractice()", "cfg.session_mode==='quick'?1:2", "n===1?[shapes[0],shapes[2],shapes[2]", "[shapes[0],shapes[1],shapes[0]", "正确匹配", "这次不匹配", "刚才应点击匹配", "e.code==='Space'", "responded"):
            self.assertIn(marker, source)

    def target_focus_practice_source(self):
        source = (Path(__file__).parents[1] / "src" / "cognitive_component_frontend" / "index.html").read_text(encoding="utf-8")
        return source.split("function targetPractice(sec)", 1)[1].split("function target(sec)", 1)[0]

    def test_target_focus_has_a_separate_five_second_practice_protocol(self):
        source = self.target_focus_practice_source()
        full_source = (Path(__file__).parents[1] / "src" / "cognitive_component_frontend" / "index.html").read_text(encoding="utf-8")
        self.assertIn("target_focus_practice_v1", full_source)
        self.assertIn("开始 5 秒练习", source)
        self.assertIn("targetPracticeCountdown", source)
        self.assertIn("elapsed>=3000", source)
        self.assertIn("startedAt=now()", source)
        self.assertIn("elapsed>=5000", source)
        self.assertIn("setTimeout(completePractice,5000)", source)
        self.assertIn("practiceDifficulty=1", source)
        self.assertIn("['target','target','target','target','distractor']", source)
        self.assertIn("点击目标 · 忽略干扰", source)
        self.assertIn("skipTargetPractice", source)
        self.assertIn("markPracticeCompleted('focus_target')", source)
        self.assertIn("if(cursor>=sequence.length)return completePractice()", source)

    def test_target_focus_practice_events_are_never_formal_trials(self):
        source = self.target_focus_practice_source()
        self.assertNotIn("noteTrial", source)
        self.assertIn("trials=[]", source)
        self.assertIn("started=now()", source)
        self.assertIn("开始正式训练", source)
        self.assertIn("retryTargetPractice", source)

    def test_target_focus_practice_handles_feedback_and_interruption_locally(self):
        source = self.target_focus_practice_source()
        for marker in ("hint.textContent='正确'", "这是干扰物", "请点击发光目标", "注意目标", "function abortTargetPractice()", "clearTargetPracticeTimers()", "practice-error"):
            self.assertIn(marker, source)
        full_source = (Path(__file__).parents[1] / "src" / "cognitive_component_frontend" / "index.html").read_text(encoding="utf-8")
        self.assertIn("if(abortTargetPractice()||abortPractice())return", full_source)

    def test_gonogo_protocol_v2_and_semantic_trial_fields_are_preserved(self):
        payload = self.payload()
        payload["tasks"][1]["task_type"] = "focus_gonogo"
        payload["tasks"][1]["protocol_version"] = "focus_gonogo_v2"
        payload["tasks"][1]["trials"] = [
            {"trial_index": 1, "stimulus_type": "go", "trial_type": "correct_go", "response_time_ms": 240, "correct": True, "practice": False},
            {"trial_index": 2, "stimulus_type": "nogo", "trial_type": "commission_error", "response_time_ms": 180, "correct": False, "commission_error": True, "practice": False},
        ]
        result = save_training_session(payload, self.path)
        task = result["tasks"][1]
        self.assertEqual(task["protocol_version"], "focus_gonogo_v2")
        self.assertEqual(task["metrics"]["adaptive_rule_version"], "adaptive_training_v1")
        connection = sqlite3.connect(self.path)
        try:
            raw = connection.execute("SELECT stimulus_payload FROM cognitive_training_trials WHERE task_result_id=? ORDER BY trial_index", (task["id"],)).fetchall()
            self.assertIn('"practice": false', raw[0][0])
            self.assertIn('"trial_type": "commission_error"', raw[1][0])
        finally:
            connection.close()
        source = (Path(__file__).parents[1] / "src" / "cognitive_component_frontend" / "index.html").read_text(encoding="utf-8")
        for marker in ("开始 5 秒练习", "跳过练习", "skipPractice", "5 秒练习", "正确 · 这是一次正确的 GO 操作", "错误 · 这是一次 NO-GO 误触", "duration_seconds:5", "practiceCorrect&&practiceError", "false_start", "correct_inhibition", "commission_error", "focus_gonogo_v2", "performance.now"):
            self.assertIn(marker, source)
        self.assertIn("function nextFormalStimulus()", source)
        self.assertIn("Math.random()<.72", source)
        self.assertIn("formalGoRun>=3", source)
        self.assertIn("formalNoGoRun>=2", source)
        self.assertNotIn("go=Math.random()>.25", source)
        self.assertIn("gonogo=function(sec)", source)
        self.assertIn("let token=run", source)
        self.assertIn("if(token!==run||formal||task!=='focus_gonogo'", source)
        self.assertIn("run++;clearStimulus();clearInterval(practiceTimer);formal=true", source)
        self.assertIn("markPracticeCompleted('focus_gonogo')", source)
        self.assertIn('id="skipPractice"', source)
        self.assertIn("id=\"startFormal\">开始正式训练</button></div></div>';timer.textContent='练习完成'", source)
        self.assertIn("task!=='focus_target'", source)
        self.assertIn("task!=='focus_gonogo'", source)
        self.assertIn("首次点击后开始", source)
        self.assertIn("progress>=.75?3:progress>=.4?2:1", source)
        self.assertIn("seconds-elapsed/1000", source)
        for marker in ("正确 · GO", "错误 · NO-GO 不要点击", "错过 · GO 未及时点击", "正确 · 保持不动", "错误 · 请按顺序寻找数字"):
            self.assertIn(marker, source)
        for marker in ("请记住以下数字", "sequenceReady", "我记住了", "序列已隐藏，请按刚才的顺序输入数字", "let round=0,answered=false", "function nextRound()", "第 ${round} 关", "setTimeout(nextRound,480)"):
            self.assertIn(marker, source)
        for marker in ("若当前图形与前", "相同才点击", "错过 · 相同图形需要点击", "nbackTimer", "nback-stimulus", "nback-repeat", "consecutive", "responded"):
            self.assertIn(marker, source)
        for marker in ("nback=function(sec)", "function choose()", "Math.random()<.35", "shapes.filter(shape=>shape!==history[history.length-n])", "setTimeout(next,180)"):
            self.assertIn(marker, source)
        self.assertIn("Math.max(700,1450-level*180)", source)
        self.assertIn("function begin(args){clearInterval(taskTimer)", source)
        self.assertIn("seconds-elapsed/1000", source)


if __name__ == "__main__":
    unittest.main()
