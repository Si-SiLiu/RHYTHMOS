import assert from "node:assert/strict";
import {after, before, beforeEach, test} from "node:test";
import {spawn} from "node:child_process";
import {createRequire} from "node:module";
import {existsSync} from "node:fs";

const require = createRequire(import.meta.url);
const {chromium} = require("playwright");
const port = 18765;
const url = `http://127.0.0.1:${port}/index.html`;
let server;
let browser;
let page;

before(async () => {
  server = spawn("python3", ["-m", "http.server", String(port), "--directory", "src/cognitive_component_frontend"], {
    stdio: "ignore",
  });
  await new Promise((resolve) => setTimeout(resolve, 500));
  const localChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  browser = await chromium.launch({
    headless: true,
    ...(existsSync(localChrome) ? {executablePath: localChrome} : {}),
  });
});

after(async () => {
  await browser?.close();
  server?.kill();
});

beforeEach(async () => {
  page = await browser.newPage({viewport: {width: 390, height: 844}, hasTouch: true});
  await page.goto(url);
  await page.evaluate(() => {
    window.__componentValues = [];
    window.addEventListener("message", (event) => {
      if (event.data?.type === "streamlit:setComponentValue") window.__componentValues.push(event.data.value);
    });
  });
});

async function render(taskTypes, runId = `run-${Date.now()}`, mode = "quick") {
  await page.evaluate(({taskTypes, runId, mode}) => {
    window.postMessage({
      type: "streamlit:render",
      args: {run_id: runId, training_plan: "cognitive_control_speed", session_mode: mode, task_types: taskTypes},
    }, "*");
  }, {taskTypes, runId, mode});
}

async function skipPractice() {
  await page.locator("#hotfixSkip").click();
  await page.waitForFunction(() => window.__rhythmosControlTest.getState()?.formal === true);
}

async function respondByPointer(pointerType = "mouse", response = null) {
  const expected = response || await page.evaluate(() => window.__rhythmosControlTest.expectedResponse());
  await page.locator(`[data-response="${expected}"]`).dispatchEvent("pointerup", {pointerType});
  await page.waitForFunction(() => window.__rhythmosControlTest.getTrials().length > 0);
  return page.evaluate(() => window.__rhythmosControlTest.getTrials().at(-1));
}

test("Stroop mouse, touch, and keyboard normalize to the same color IDs", async () => {
  await render(["stroop_control"]);
  await skipPractice();
  const mouse = await respondByPointer("mouse");
  assert.equal(mouse.correct, true);
  assert.equal(mouse.actual_response, mouse.expected_response);
  assert.equal(mouse.input_method, "mouse");

  await page.waitForFunction(() => window.__rhythmosControlTest.getState()?.current);
  const touch = await respondByPointer("touch");
  assert.equal(touch.correct, true);
  assert.equal(touch.actual_response, touch.expected_response);
  assert.equal(touch.input_method, "touch");

  await page.waitForFunction(() => window.__rhythmosControlTest.getState()?.current);
  const expected = await page.evaluate(() => window.__rhythmosControlTest.expectedResponse());
  const key = {red: "1", blue: "2", green: "3", yellow: "4"}[expected];
  await page.keyboard.press(key);
  await page.waitForFunction(() => window.__rhythmosControlTest.getTrials().length >= 3);
  const keyboard = await page.evaluate(() => window.__rhythmosControlTest.getTrials().at(-1));
  assert.equal(keyboard.correct, true);
  assert.equal(keyboard.actual_response, keyboard.expected_response);
  assert.equal(keyboard.input_method, "keyboard");
});

test("Stroop word-meaning response is wrong on an incongruent trial", async () => {
  await render(["stroop_control"]);
  await skipPractice();
  for (let attempt = 0; attempt < 10; attempt += 1) {
    await page.waitForFunction(() => window.__rhythmosControlTest.getState()?.current);
    const pair = await page.evaluate(() => ({
      expected: window.__rhythmosControlTest.expectedResponse(),
      word: window.__rhythmosControlTest.wordResponse(),
    }));
    if (pair.expected !== pair.word) {
      const trial = await respondByPointer("mouse", pair.word);
      assert.equal(trial.correct, false);
      return;
    }
    await respondByPointer("mouse", pair.expected);
  }
  assert.fail("No incongruent trial generated");
});

test("Task Switching pointer and Symbol Match keyboard paths execute", async () => {
  await render(["task_switching"]);
  await skipPractice();
  const switchTrial = await respondByPointer("mouse");
  assert.equal(switchTrial.correct, true);
  assert.ok(["initial", "repeat", "switch"].includes(switchTrial.switch_condition));

  await render(["symbol_match"], "symbol-run");
  await skipPractice();
  const digit = await page.evaluate(() => window.__rhythmosControlTest.expectedResponse());
  await page.keyboard.press(digit);
  await page.waitForFunction(() => window.__rhythmosControlTest.getTrials().length === 1);
  const symbolTrial = await page.evaluate(() => window.__rhythmosControlTest.getTrials()[0]);
  assert.equal(symbolTrial.correct, true);
  assert.equal(symbolTrial.input_method, "keyboard");
  await page.waitForFunction(() => window.__rhythmosControlTest.getState()?.current);
  const nextDigit = await page.evaluate(() => window.__rhythmosControlTest.expectedResponse());
  await page.keyboard.press(nextDigit);
  await page.waitForFunction(() => window.__rhythmosControlTest.getTrials().length === 2);
  const mappingIds = await page.evaluate(() => window.__rhythmosControlTest.getTrials().map((trial) => trial.mapping_id));
  assert.equal(new Set(mappingIds).size, 1);
});

test("practice remains active for the full five-second window and submits no trial", async () => {
  await render(["stroop_control"]);
  await page.locator("#hotfixPractice").click();
  await page.waitForTimeout(7200);
  assert.equal(await page.locator("text=练习完成").count(), 0);
  await page.waitForSelector("text=完整5秒练习已结束", {timeout: 2000});
  assert.equal(await page.evaluate(() => window.__rhythmosControlTest.getTrials().length), 0);
});

test("blur finalizes a partial task and stops later trials", async () => {
  await render(["stroop_control"]);
  await skipPractice();
  await respondByPointer("mouse");
  await page.evaluate(() => window.dispatchEvent(new Event("blur")));
  await page.waitForFunction(() => window.__componentValues.length === 1);
  const value = await page.evaluate(() => window.__componentValues[0]);
  assert.equal(value.interrupted, true);
  assert.equal(value.tasks.length, 1);
  assert.equal(value.tasks[0].partial, true);
  const count = value.tasks[0].trials.length;
  await page.waitForTimeout(500);
  assert.equal(await page.evaluate(() => window.__rhythmosControlTest.getTrials().length), count);
});

test("visibilitychange finalizes a partial task", async () => {
  await render(["task_switching"]);
  await skipPractice();
  await respondByPointer("mouse");
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", {configurable: true, value: true});
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await page.waitForFunction(() => window.__componentValues.length === 1);
  const value = await page.evaluate(() => window.__componentValues[0]);
  assert.equal(value.interrupted, true);
  assert.equal(value.tasks[0].partial, true);
});

test("configured duration, queue refill, and timer cleanup govern completion", async () => {
  await page.evaluate(() => {
    window.__rhythmosControlTest.durations.quick.stroop_control = 0.35;
  });
  await render(["stroop_control"]);
  await skipPractice();
  while (!await page.evaluate(() => window.__componentValues.length)) {
    const current = await page.evaluate(() => window.__rhythmosControlTest.getState()?.current);
    if (current) await respondByPointer("mouse");
    else await page.waitForTimeout(20);
  }
  const value = await page.evaluate(() => window.__componentValues[0]);
  assert.ok(value.tasks[0].active_duration_seconds >= 0.35);
  assert.ok(value.tasks[0].configured_duration_seconds === 0.35);
  assert.equal(await page.evaluate(() => window.__rhythmosTimerRegistry.timeouts.size + window.__rhythmosTimerRegistry.intervals.size), 0);
});

test("a callback from Stroop cannot enter the following Task Switching task", async () => {
  await page.evaluate(() => {
    window.__rhythmosControlTest.durations.quick.stroop_control = 0.25;
    window.__rhythmosControlTest.durations.quick.task_switching = 0.5;
  });
  await render(["stroop_control", "task_switching"], "transition-run");
  await skipPractice();
  while (!await page.locator("#hotfixSkip").count()) {
    const current = await page.evaluate(() => window.__rhythmosControlTest.getState()?.current);
    if (current) await respondByPointer("mouse");
    else await page.waitForTimeout(20);
  }
  const stroopCount = await page.evaluate(() => window.__rhythmosControlTest.getResults()[0].trials.length);
  await skipPractice();
  await page.waitForTimeout(300);
  const snapshot = await page.evaluate(() => ({
    stroopCount: window.__rhythmosControlTest.getResults()[0].trials.length,
    currentTypes: window.__rhythmosControlTest.getTrials().map((trial) => trial.stimulus_type),
  }));
  assert.equal(snapshot.stroopCount, stroopCount);
  assert.ok(snapshot.currentTypes.every((type) => type === "task_switching"));
});

test("standard duration uses its separate centralized configuration", async () => {
  await page.evaluate(() => {
    window.__rhythmosControlTest.durations.standard.symbol_match = 0.4;
  });
  await render(["symbol_match"], "standard-duration", "standard");
  await skipPractice();
  while (!await page.evaluate(() => window.__componentValues.length)) {
    const current = await page.evaluate(() => window.__rhythmosControlTest.getState()?.current);
    if (current) await respondByPointer("touch");
    else await page.waitForTimeout(20);
  }
  const taskResult = await page.evaluate(() => window.__componentValues[0].tasks[0]);
  assert.equal(taskResult.configured_duration_seconds, 0.4);
  assert.ok(taskResult.active_duration_seconds >= 0.4);
});

test("Task Switching generator validates many random blocks and boundaries", async () => {
  await render(["task_switching"]);
  const valid = await page.evaluate(() => {
    const api = window.__rhythmosControlTest;
    let previousRule = null;
    let previousNumber = null;
    for (let index = 0; index < 120; index += 1) {
      const block = api.taskSwitchBlock(previousRule, previousNumber);
      if (!api.validSwitchBlock(block, previousRule, previousNumber)) return false;
      if (block.some((item) => item.number === 5)) return false;
      previousRule = block.at(-1).rule;
      previousNumber = block.at(-1).number;
    }
    return true;
  });
  assert.equal(valid, true);
});

test("adaptive difficulty requires two stable blocks and lowers on poor accuracy", async () => {
  await render(["stroop_control"]);
  await skipPractice();
  const levels = await page.evaluate(() => {
    const api = window.__rhythmosControlTest;
    const state = api.getState();
    const strong = () => [...Array(8)].map((_, index) => ({correct: true, response_time_ms: 300 + index}));
    state.blockTrials = strong();
    api.evaluateBlock();
    const afterOne = api.getLevel();
    state.blockTrials = strong();
    api.evaluateBlock();
    const afterTwo = api.getLevel();
    state.blockTrials = [...Array(8)].map((_, index) => ({correct: index < 4, response_time_ms: 350 + index}));
    api.evaluateBlock();
    return {afterOne, afterTwo, afterPoor: api.getLevel(), changes: state.changes.length};
  });
  assert.equal(levels.afterOne, 2);
  assert.equal(levels.afterTwo, 3);
  assert.equal(levels.afterPoor, 2);
  assert.equal(levels.changes, 2);
});

test("320px Symbol Match layout does not overflow and uses two columns", async () => {
  await page.setViewportSize({width: 320, height: 700});
  await render(["symbol_match"]);
  await skipPractice();
  await page.evaluate(() => window.__rhythmosControlTest.setLevel(5));
  await respondByPointer("touch");
  await page.waitForSelector(".control-choices.six");
  const layout = await page.evaluate(() => {
    const grid = document.querySelector(".control-choices.six");
    return {
      overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      columns: getComputedStyle(grid).gridTemplateColumns.split(" ").length,
    };
  });
  assert.equal(layout.overflow, false);
  assert.equal(layout.columns, 2);
});

test("existing Focus and Working Memory practice entry paths still render", async () => {
  await render(["focus_visual_search"], "legacy-focus");
  await page.waitForSelector("#skipTaskPractice");
  await page.locator("#skipTaskPractice").click();
  await page.waitForSelector(".board");

  await render(["memory_grid"], "legacy-memory");
  await page.waitForSelector("#skipTaskPractice");
  await page.locator("#skipTaskPractice").click();
  await page.waitForSelector(".board");
});
