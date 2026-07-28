(function () {
  "use strict";

  const CONTROL_TASKS = new Set(["stroop_control", "task_switching", "symbol_match"]);
  const COLORS = [
    {id: "red", label: "红", css: "#d95050", key: "1"},
    {id: "blue", label: "蓝", css: "#3779d8", key: "2"},
    {id: "green", label: "绿", css: "#2c9d66", key: "3"},
    {id: "yellow", label: "黄", css: "#c79714", key: "4"},
  ];
  const SYMBOLS = [
    ["circle", "○"], ["triangle", "△"], ["diamond", "◇"],
    ["star", "☆"], ["hexagon", "⬡"], ["cross", "＋"],
  ];
  const DURATIONS = {
    quick: {stroop_control: 55, task_switching: 55, symbol_match: 55},
    standard: {stroop_control: 100, task_switching: 100, symbol_match: 100},
  };
  const PRACTICE_PROTOCOLS = {
    stroop_control: "stroop_practice_v1",
    task_switching: "task_switching_practice_v1",
    symbol_match: "symbol_match_practice_v1",
  };
  const native = {
    timeout: window.setTimeout.bind(window),
    interval: window.setInterval.bind(window),
    clearTimeout: window.clearTimeout.bind(window),
    clearInterval: window.clearInterval.bind(window),
    raf: window.requestAnimationFrame.bind(window),
    cancelRaf: window.cancelAnimationFrame.bind(window),
  };
  const registry = {timeouts: new Set(), intervals: new Set(), frames: new Set()};

  window.setTimeout = function (callback, delay, ...args) {
    let id = native.timeout(() => {
      registry.timeouts.delete(id);
      callback(...args);
    }, delay);
    registry.timeouts.add(id);
    return id;
  };
  window.clearTimeout = function (id) {
    registry.timeouts.delete(id);
    native.clearTimeout(id);
  };
  window.setInterval = function (callback, delay, ...args) {
    const id = native.interval(callback, delay, ...args);
    registry.intervals.add(id);
    return id;
  };
  window.clearInterval = function (id) {
    registry.intervals.delete(id);
    native.clearInterval(id);
  };
  window.requestAnimationFrame = function (callback) {
    let id = native.raf((time) => {
      registry.frames.delete(id);
      callback(time);
    });
    registry.frames.add(id);
    return id;
  };
  window.cancelAnimationFrame = function (id) {
    registry.frames.delete(id);
    native.cancelRaf(id);
  };
  function clearAllTaskTimers() {
    registry.timeouts.forEach(native.clearTimeout);
    registry.intervals.forEach(native.clearInterval);
    registry.frames.forEach(native.cancelRaf);
    registry.timeouts.clear();
    registry.intervals.clear();
    registry.frames.clear();
    taskTimer = null;
  }
  window.__rhythmosTimerRegistry = registry;
  window.clearAllTaskTimers = clearAllTaskTimers;

  const legacy = {
    stats,
    startTask,
    abortPractice,
  };
  let generation = 0;
  let state = null;

  function token() {
    return generation;
  }
  function alive(value) {
    return value === generation && !done;
  }
  function nextGeneration() {
    generation += 1;
    clearAllTaskTimers();
    window.onkeydown = null;
    if (state) {
      state.responded = true;
      state.current = null;
    }
    return generation;
  }
  function schedule(callback, delay, currentToken = token()) {
    return window.setTimeout(() => {
      if (alive(currentToken)) callback();
    }, delay);
  }
  function mean(values) {
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  }
  function median(values) {
    const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
    if (!sorted.length) return null;
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  }
  function coefficientOfVariation(values) {
    const avg = mean(values);
    if (!avg || values.length < 2) return null;
    const variance = values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / (values.length - 1);
    return Math.sqrt(variance) / avg;
  }
  function shuffle(values) {
    const result = [...values];
    for (let index = result.length - 1; index > 0; index -= 1) {
      const other = Math.floor(Math.random() * (index + 1));
      [result[index], result[other]] = [result[other], result[index]];
    }
    return result;
  }
  function ruleAnswer(rule, number) {
    if (rule === "parity") return number % 2 === 1 ? "left" : "right";
    return number < 5 ? "left" : "right";
  }
  function difficultyConfig(taskName, taskLevel) {
    const levelIndex = Math.max(1, Math.min(5, taskLevel));
    if (taskName === "stroop_control") {
      return {
        response_window_ms: [2400, 2200, 1950, 1750, 1550][levelIndex - 1],
        condition_ratio: {congruent: 0.4, incongruent: 0.6},
        iti_ms: [220, 200, 180, 160, 150][levelIndex - 1],
        color_count: 4,
      };
    }
    if (taskName === "task_switching") {
      return {
        response_window_ms: [2600, 2350, 2100, 1900, 1700][levelIndex - 1],
        switch_ratio: 0.5,
        iti_ms: [240, 220, 200, 180, 160][levelIndex - 1],
        rule_count: 2,
      };
    }
    return {
      response_window_ms: [2700, 2450, 2200, 1950, 1750][levelIndex - 1],
      iti_ms: [220, 200, 180, 160, 150][levelIndex - 1],
      symbol_count: Math.min(6, levelIndex + 2),
      mapping_visible: true,
    };
  }

  function setup(seconds) {
    taskStart = now();
    clearInterval(taskTimer);
    resize();
    taskTimer = setInterval(() => {
      const elapsed = (now() - taskStart) / 1000;
      const left = Math.max(0, seconds - elapsed);
      timer.textContent = Math.ceil(left) + " 秒";
      bar.style.width = Math.min(100, elapsed / seconds * 100) + "%";
    }, 100);
  }
  window.setup = setup;

  function stroopBlock() {
    const conditions = shuffle([
      ...Array(8).fill("congruent"),
      ...Array(12).fill("incongruent"),
    ]);
    const colorOrder = shuffle([...Array(20)].map((_, index) => index % 4));
    return conditions.map((condition, index) => {
      const color = colorOrder[index];
      const alternatives = [0, 1, 2, 3].filter((value) => value !== color);
      return {
        word: condition === "congruent" ? color : alternatives[(index + color) % alternatives.length],
        color,
        congruency: condition,
      };
    });
  }
  function validSwitchBlock(block, previousRule, previousNumber) {
    const rules = block.map((item) => item.rule);
    const switches = block.filter((item, index) => {
      const previous = index ? block[index - 1].rule : previousRule;
      return previous && previous !== item.rule;
    }).length;
    const left = block.filter((item) => ruleAnswer(item.rule, item.number) === "left").length;
    if (Math.abs(rules.filter((item) => item === "parity").length - rules.filter((item) => item === "magnitude").length) > 2) return false;
    if (Math.abs(switches - block.length / 2) > 2 || Math.abs(left - block.length / 2) > 2) return false;
    if (previousNumber !== null && block[0].number === previousNumber) return false;
    for (let index = 1; index < block.length; index += 1) {
      if (block[index].number === block[index - 1].number) return false;
    }
    const joined = previousRule ? [previousRule, ...rules] : rules;
    for (let index = 3; index < joined.length; index += 1) {
      if (joined[index] === joined[index - 2] && joined[index - 1] === joined[index - 3] && joined[index] !== joined[index - 1]) return false;
    }
    let run = 1;
    for (let index = 1; index < joined.length; index += 1) {
      run = joined[index] === joined[index - 1] ? run + 1 : 1;
      if (run > 3) return false;
    }
    return true;
  }
  function taskSwitchBlock(previousRule = null, previousNumber = null) {
    const numbers = [1, 2, 3, 4, 6, 7, 8, 9];
    for (let attempt = 0; attempt < 600; attempt += 1) {
      const block = [];
      for (let index = 0; index < 24; index += 1) {
        const numberChoices = numbers.filter((value) => value !== (index ? block[index - 1].number : previousNumber));
        block.push({
          rule: Math.random() < 0.5 ? "parity" : "magnitude",
          number: numberChoices[Math.floor(Math.random() * numberChoices.length)],
        });
      }
      if (validSwitchBlock(block, previousRule, previousNumber)) return block;
    }
    const ruleBits = [..."010001101110011011011000"].map(Number);
    const fallbackNumbers = [6, 4, 6, 9, 4, 1, 2, 8, 2, 9, 2, 3, 9, 1, 3, 9, 6, 7, 3, 7, 9, 4, 8, 2];
    for (const invert of [0, 1]) {
      for (let offset = 0; offset < 24; offset += 1) {
        const candidate = [...Array(24)].map((_, index) => {
          const source = (index + offset) % 24;
          return {
            rule: (ruleBits[source] ^ invert) ? "magnitude" : "parity",
            number: fallbackNumbers[source],
          };
        });
        if (validSwitchBlock(candidate, previousRule, previousNumber)) return candidate;
      }
    }
    throw new Error("Unable to generate a valid Task Switching block");
  }
  function symbolBlock(symbolCount) {
    const values = [];
    for (let index = 0; index < 24; index += 1) values.push(index % symbolCount);
    for (let attempt = 0; attempt < 100; attempt += 1) {
      const candidate = shuffle(values);
      if (candidate.every((value, index) => !index || value !== candidate[index - 1])) {
        return candidate.map((symbol) => ({symbol, digit: state.mapping[symbol]}));
      }
    }
    return values.map((symbol) => ({symbol, digit: state.mapping[symbol]}));
  }
  function refillQueue() {
    if (!state || state.queue.length >= 6) return;
    let block;
    if (task === "stroop_control") block = stroopBlock();
    else if (task === "task_switching") {
      const tail = state.queue[state.queue.length - 1];
      block = taskSwitchBlock(tail ? tail.rule : state.previousRule, tail ? tail.number : state.previousNumber);
    }
    else block = symbolBlock(difficultyConfig(task, level).symbol_count);
    state.queue.push(...block);
  }

  function inputFromKeyboard(event) {
    if (task === "stroop_control") {
      const color = COLORS.find((item) => item.key === event.key);
      return color ? color.id : null;
    }
    if (task === "task_switching") {
      if (event.key === "ArrowLeft" || event.key.toLowerCase() === "a") return "left";
      if (event.key === "ArrowRight" || event.key.toLowerCase() === "d") return "right";
      return null;
    }
    return /^[1-6]$/.test(event.key) ? event.key : null;
  }
  function renderTrial(item, practice, respond) {
    stage.innerHTML = "";
    let expected;
    let options;
    if (task === "stroop_control") {
      expected = COLORS[item.color].id;
      stage.innerHTML = `<div class="control-stimulus" style="color:${COLORS[item.color].css}">${COLORS[item.word].label}</div><div class="small">1 红 · 2 蓝 · 3 绿 · 4 黄</div>`;
      options = COLORS.map((color) => ({label: color.label, value: color.id, css: color.css}));
    } else if (task === "task_switching") {
      expected = ruleAnswer(item.rule, item.number);
      const parity = item.rule === "parity";
      stage.innerHTML = `<div class="control-rule">当前规则：${parity ? "奇数 / 偶数" : "小于5 / 大于5"}</div><div class="control-stimulus">${item.number}</div><div class="small">← / A = 左　｜　→ / D = 右</div>`;
      options = [
        {label: parity ? "奇数" : "小于5", value: "left"},
        {label: parity ? "偶数" : "大于5", value: "right"},
      ];
    } else {
      expected = String(item.digit);
      const symbols = practice ? SYMBOLS.slice(0, 3) : SYMBOLS.slice(0, difficultyConfig(task, level).symbol_count);
      const mapping = symbols.map((symbol, index) => `${symbol[1]} = ${practice ? index + 1 : state.mapping[index]}`).join("　");
      stage.innerHTML = `<div class="symbol-map" aria-label="符号数字对应表">${mapping}</div><div class="control-stimulus" aria-label="目标符号">${SYMBOLS[item.symbol][1]}</div><div class="small">按键 1—6</div>`;
      options = [...Array(symbols.length)].map((_, index) => ({label: String(index + 1), value: String(index + 1)}));
    }
    const row = document.createElement("div");
    row.className = "control-choices " + (options.length > 4 ? "six" : "");
    options.forEach((option) => {
      const button = document.createElement("button");
      button.className = "choice color-choice";
      button.dataset.response = option.value;
      button.innerHTML = (option.css ? `<span class="swatch" style="background:${option.css}"></span>` : "") + option.label;
      button.addEventListener("pointerup", (event) => {
        const method = event.pointerType === "touch" ? "touch" : "mouse";
        respond(option.value, method, expected);
      }, {once: true});
      row.appendChild(button);
    });
    stage.appendChild(row);
    window.onkeydown = (event) => {
      const value = inputFromKeyboard(event);
      if (value !== null) {
        event.preventDefault();
        respond(value, "keyboard", expected);
      }
    };
    return expected;
  }

  function practiceIntro() {
    nextGeneration();
    state = {phase: "practice_intro", formal: false, practiceRepeats: 0, responded: false};
    const description = {
      stroop_control: "请选择字体的颜色，不要按照文字含义作答。",
      task_switching: "先确认顶部规则：奇数/偶数或小于5/大于5。",
      symbol_match: "查看上方符号—数字表，选择当前符号对应的数字。",
    }[task];
    timer.textContent = "练习准备";
    bar.style.width = "0%";
    stage.dataset.practiceProtocol = PRACTICE_PROTOCOLS[task];
    stage.innerHTML = `<div class="gonogo-instruction"><h3>5 秒练习</h3><p>${description}</p><p class="small">练习模式 · 不计入正式成绩</p><div class="gonogo-actions"><button class="primary" id="hotfixPractice">开始 5 秒练习</button><button class="primary" id="hotfixSkip">跳过练习</button></div></div>`;
    document.getElementById("hotfixPractice").onclick = practiceCountdown;
    document.getElementById("hotfixSkip").onclick = formalStart;
    resize();
  }
  function practiceCountdown() {
    const currentToken = nextGeneration();
    state = {...state, phase: "practice_countdown", responded: false};
    const began = now();
    stage.innerHTML = '<div class="gonogo-instruction"><h3>5 秒练习</h3><p id="hotfixCountdown">3</p></div>';
    setInterval(() => {
      if (!alive(currentToken)) return;
      const elapsed = now() - began;
      document.getElementById("hotfixCountdown").textContent = Math.max(0, 3 - Math.floor(elapsed / 1000)) || "开始";
      if (elapsed >= 3000) practiceRun();
    }, 50);
  }
  function practiceItems() {
    if (task === "stroop_control") return [{word: 0, color: 1}, {word: 1, color: 1}, {word: 2, color: 3}, {word: 3, color: 0}];
    if (task === "task_switching") return [{number: 7, rule: "parity"}, {number: 2, rule: "magnitude"}, {number: 8, rule: "parity"}, {number: 3, rule: "magnitude"}];
    return [{symbol: 0, digit: 1}, {symbol: 1, digit: 2}, {symbol: 2, digit: 3}];
  }
  function practiceRun() {
    const currentToken = nextGeneration();
    const began = now();
    const deadline = began + 5000;
    const items = practiceItems();
    let index = 0;
    state = {...state, phase: "practice_active", practiceDeadline: deadline, responded: false};
    setTimeout(() => practiceDone(false), 5000);
    function show() {
      if (!alive(currentToken) || state.phase !== "practice_active") return;
      if (now() >= deadline) return practiceDone(false);
      const item = items[index % items.length];
      index += 1;
      state.responded = false;
      renderTrial(item, true, (value, method, expected) => {
        if (state.responded || !alive(currentToken)) return;
        state.responded = true;
        hint.textContent = value === expected ? "正确" : task === "stroop_control" ? "请按字体颜色作答" : task === "task_switching" ? "注意顶部规则" : "请查看上方对应表";
        schedule(show, 260, currentToken);
      });
    }
    show();
  }
  function practiceDone(aborted) {
    if (!state || !state.phase.startsWith("practice")) return;
    nextGeneration();
    if (aborted) return practiceIntro();
    state = {...state, phase: "practice_summary", formal: false};
    timer.textContent = "练习完成";
    bar.style.width = "100%";
    stage.innerHTML = '<div class="gonogo-instruction"><h3>练习完成</h3><p class="small">完整5秒练习已结束，数据不进入正式成绩。</p><div class="gonogo-actions"><button class="primary" id="hotfixRetry">再练一次</button><button class="primary" id="hotfixFormal">开始正式训练</button></div></div>';
    document.getElementById("hotfixRetry").onclick = () => {
      state.practiceRepeats += 1;
      practiceCountdown();
    };
    document.getElementById("hotfixFormal").onclick = formalStart;
    resize();
  }

  function formalStart() {
    const repeats = state ? state.practiceRepeats : 0;
    nextGeneration();
    delete stage.dataset.practiceProtocol;
    trials = [];
    level = 2;
    const configured = DURATIONS[cfg.session_mode][task];
    state = {
      phase: "formal",
      formal: true,
      configured,
      startedAt: now(),
      actualStartedAt: now(),
      queue: [],
      current: null,
      responded: false,
      previousRule: null,
      previousNumber: null,
      blockTrials: [],
      highBlocks: 0,
      changes: [],
      initialLevel: level,
      practiceProtocolVersion: PRACTICE_PROTOCOLS[task],
      practiceRepeatedCount: repeats,
      mapping: shuffle([1, 2, 3, 4, 5, 6]),
      mappingId: null,
    };
    state.mappingId = `map_${state.mapping.join("")}_${cfg.run_id}`;
    hint.textContent = "保持准确与稳定；请勿切换页面。";
    setup(configured);
    formalNext();
  }
  function evaluateBlock() {
    if (state.blockTrials.length < 8) return;
    const block = state.blockTrials.splice(0, 8);
    const accuracy = block.filter((item) => item.correct).length / block.length;
    const rts = block.map((item) => item.response_time_ms).filter(Number.isFinite);
    const stable = coefficientOfVariation(rts);
    let nextLevel = level;
    let reason = "hold";
    if (accuracy >= 0.90 && stable !== null && stable <= 0.35) {
      state.highBlocks += 1;
      if (state.highBlocks >= 2 && state.changes.length < 2) {
        nextLevel = Math.min(5, level + 1);
        reason = "two_stable_high_accuracy_blocks";
        state.highBlocks = 0;
      }
    } else {
      state.highBlocks = 0;
      if (accuracy < 0.75 && state.changes.length < 2) {
        nextLevel = Math.max(1, level - 1);
        reason = "accuracy_below_75_percent";
      }
    }
    if (nextLevel !== level) {
      state.changes.push({
        previous_level: level,
        new_level: nextLevel,
        reason,
        triggering_block_metrics: {accuracy, rt_coefficient_of_variation: stable, trial_count: block.length},
        changed_at: new Date().toISOString(),
      });
      level = nextLevel;
    }
  }
  function formalNext() {
    const currentToken = token();
    if (!alive(currentToken) || !state || !state.formal) return;
    if ((now() - state.startedAt) / 1000 >= state.configured) return finishTask();
    refillQueue();
    const item = state.queue.shift();
    state.current = item;
    state.responded = false;
    const shownAt = now();
    const expected = renderTrial(item, false, (value, method, expectedResponse) => {
      formalRespond(item, value, method, expectedResponse, shownAt, false, currentToken);
    });
    setTimeout(() => formalRespond(item, "none", "none", expected, shownAt, true, currentToken), difficultyConfig(task, level).response_window_ms);
  }
  function formalRespond(item, value, inputMethod, expected, shownAt, omission, currentToken) {
    if (!alive(currentToken) || !state || state.current !== item || state.responded) return;
    state.responded = true;
    state.current = null;
    const correct = !omission && value === expected;
    const trial = {
      stimulus_type: task,
      expected_response: expected,
      actual_response: value,
      response_time_ms: omission ? null : now() - shownAt,
      correct,
      omission,
      valid: true,
      input_method: inputMethod,
      difficulty_level: level,
      difficulty_config: difficultyConfig(task, level),
      schema_version: "control_speed_trial_v1",
    };
    if (task === "stroop_control") {
      Object.assign(trial, {
        word_meaning: COLORS[item.word].id,
        font_color: COLORS[item.color].id,
        congruency: item.congruency,
        trial_type: item.congruency,
      });
    } else if (task === "task_switching") {
      const previousRule = state.previousRule;
      const previousExpected = previousRule ? ruleAnswer(previousRule, item.number) : null;
      const condition = previousRule === null ? "initial" : previousRule === item.rule ? "repeat" : "switch";
      const distinguishable = previousExpected !== null && previousExpected !== expected;
      Object.assign(trial, {
        current_rule: item.rule,
        previous_rule: previousRule,
        switch_condition: condition,
        trial_type: condition,
        stimulus_number: item.number,
        previous_rule_expected_response: previousExpected,
        perseveration_error: condition === "switch" && !correct && !omission && distinguishable && value === previousExpected,
      });
      state.previousRule = item.rule;
      state.previousNumber = item.number;
    } else {
      Object.assign(trial, {
        symbol_id: SYMBOLS[item.symbol][0],
        expected_digit: expected,
        mapping_id: state.mappingId,
        trial_type: "symbol_match",
      });
    }
    noteTrial(trial);
    state.blockTrials.push(trial);
    evaluateBlock();
    hint.textContent = correct ? "正确" : omission ? "请更快作答" : "再确认规则";
    schedule(formalNext, difficultyConfig(task, level).iti_ms, currentToken);
  }

  function previewStats() {
    const all = trials.filter((item) => !item.practice && item.valid !== false);
    const correct = all.filter((item) => item.correct);
    const result = {
      trial_count: all.length,
      accuracy: all.length ? correct.length / all.length : null,
      median_rt_ms: median(all.map((item) => item.response_time_ms)),
    };
    if (task === "symbol_match") {
      result.median_correct_rt_ms = median(correct.map((item) => item.response_time_ms));
    }
    return result;
  }
  stats = function () {
    if (!CONTROL_TASKS.has(task)) return legacy.stats();
    const active = state ? (now() - state.startedAt) / 1000 : 0;
    const valid = trials.filter((item) => !item.practice && item.valid !== false);
    return {
      task_type: task,
      protocol_version: `${task}_v1`,
      difficulty_start: state ? state.initialLevel : level,
      difficulty_end: level,
      total_trials: valid.length,
      correct_count: valid.filter((item) => item.correct).length,
      error_count: valid.filter((item) => item.correct === false && !item.omission).length,
      omission_count: valid.filter((item) => item.omission).length,
      accuracy: valid.length ? valid.filter((item) => item.correct).length / valid.length : null,
      metrics: previewStats(),
      trials: valid,
      configured_duration_seconds: state ? state.configured : null,
      active_duration_seconds: active,
      actual_duration_seconds: active,
      difficulty_changes: state ? state.changes : [],
      difficulty_config: difficultyConfig(task, level),
      practice_protocol_version: state ? state.practiceProtocolVersion : null,
      practice_repeated_count: state ? state.practiceRepeatedCount : 0,
      completed: true,
      interrupted: false,
      partial: false,
    };
  };

  startTask = function () {
    nextGeneration();
    task = cfg.task_types[taskIndex];
    trials = [];
    level = 1;
    taskStart = now();
    label.textContent = `${taskIndex + 1} / ${cfg.task_types.length} · ${names[task]}`;
    title.textContent = names[task];
    hint.textContent = "";
    stage.innerHTML = "";
    if (CONTROL_TASKS.has(task)) return practiceIntro();
    return legacy.startTask();
  };
  abortPractice = function () {
    if (CONTROL_TASKS.has(task) && state && state.phase.startsWith("practice")) {
      practiceDone(true);
      return true;
    }
    return legacy.abortPractice();
  };
  finishTask = function () {
    if (done) return;
    const taskResult = stats();
    clearAllTaskTimers();
    window.onkeydown = null;
    results.push(taskResult);
    taskIndex += 1;
    state = null;
    if (taskIndex >= cfg.task_types.length) return finish();
    startTask();
  };
  finish = function () {
    if (done) return;
    if (interrupted && CONTROL_TASKS.has(task) && state && state.formal) {
      const partial = stats();
      partial.completed = false;
      partial.interrupted = true;
      partial.partial = true;
      partial.difficulty_end = partial.difficulty_start;
      partial.difficulty_changes = [];
      partial.metrics = {...partial.metrics, completed: false, interrupted: true, partial: true};
      if (!results.length || results[results.length - 1].task_type !== partial.task_type) results.push(partial);
    }
    done = true;
    clearAllTaskTimers();
    window.onkeydown = null;
    const formalSeconds = results.reduce((sum, item) => sum + (Number(item.active_duration_seconds) || 0), 0);
    post("streamlit:setComponentValue", {value: {
      id: cfg.run_id,
      run_id: cfg.run_id,
      training_plan: cfg.training_plan,
      session_mode: cfg.session_mode,
      started_at: new Date(Date.now() - formalSeconds * 1000).toISOString(),
      completed_at: new Date().toISOString(),
      total_duration_seconds: formalSeconds,
      completed: !interrupted,
      interrupted: Boolean(interrupted),
      interruption_reason: interrupted,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
      device_context: {
        user_agent: navigator.userAgent,
        viewport: {width: innerWidth, height: innerHeight, device_pixel_ratio: devicePixelRatio},
        input_mode: "mouse,keyboard,touch",
        operating_system: navigator.userAgentData?.platform || navigator.platform,
        browser: navigator.userAgent,
      },
      protocol_version: "adaptive_control_speed_v1",
      tasks: results,
    }});
  };
  begin = function (args) {
    nextGeneration();
    practiceState = null;
    clearTargetPracticeTimers();
    targetPracticeState = null;
    cfg = args;
    started = now();
    taskIndex = 0;
    results = [];
    done = false;
    interrupted = null;
    state = null;
    startTask();
    resize();
  };
  window.addEventListener("pagehide", () => {
    if (!done && state && state.formal) {
      interrupted = "pagehide";
      finish();
    } else {
      clearAllTaskTimers();
    }
  });

  window.__rhythmosControlTest = {
    median,
    stroopBlock,
    taskSwitchBlock,
    validSwitchBlock,
    ruleAnswer,
    difficultyConfig,
    durations: DURATIONS,
    registry,
    getState: () => state,
    getTrials: () => trials,
    getResults: () => results,
    getTask: () => task,
    setLevel: (value) => { level = value; },
    getLevel: () => level,
    evaluateBlock,
    expectedResponse: () => {
      if (!state || !state.current) return null;
      if (task === "stroop_control") return COLORS[state.current.color].id;
      if (task === "task_switching") return ruleAnswer(state.current.rule, state.current.number);
      return String(state.current.digit);
    },
    wordResponse: () => state && state.current && task === "stroop_control" ? COLORS[state.current.word].id : null,
  };
})();
