import assert from "node:assert/strict";
import {after, before, test} from "node:test";
import {spawn, spawnSync} from "node:child_process";
import {mkdtemp, readdir, rm} from "node:fs/promises";
import {existsSync} from "node:fs";
import {tmpdir} from "node:os";
import {dirname, join, resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {createRequire} from "node:module";

const require = createRequire(import.meta.url);
const {chromium} = require("playwright");
const repository = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const python = process.env.RHYTHMOS_PYTHON || "python3";
const port = 8768;
const origin = `http://127.0.0.1:${port}`;
let runtimeRoot;
let server;
let browser;
let context;
let page;
let serverOutput = "";
let serverOutputBeforeContextClose;

function extractPythonTracebacks(output) {
  const marker = "Traceback (most recent call last):";
  const starts = [];
  let offset = output.indexOf(marker);
  while (offset !== -1) {
    starts.push(offset);
    offset = output.indexOf(marker, offset + marker.length);
  }

  const tracebacks = [];
  for (let index = 0; index < starts.length; index += 1) {
    let end = starts[index + 1] ?? output.length;
    while (
      end < output.length
      && output.slice(starts[index], end).includes("During handling of the above exception")
    ) {
      index += 1;
      end = starts[index + 1] ?? output.length;
    }
    tracebacks.push(output.slice(starts[index], end).trim());
  }
  return tracebacks;
}

function isBenignTornadoWebSocketClose(traceback) {
  const frameFiles = Array.from(
    traceback.matchAll(/^\s*File "([^"]+)"/gm),
    ([, file]) => file,
  );
  const allowedFrame = /(?:site-packages\/(?:streamlit|tornado)\/|\/lib\/python\d+(?:\.\d+)?\/)/;
  const projectFrame = /\/(?:RHYTHMOS|RHYTHMOS-Worktrees)\/[^\n]*\/src\/|src\/dashboard\.py|src\/pages\/|performance_planner\.py/;
  const unexpectedException = /^(?:ValueError|TypeError|RuntimeError|sqlite3\.|AssertionError|KeyError|AttributeError|ModuleNotFoundError|SyntaxError)\b/m;
  const terminalLines = traceback.split("\n").filter((line) => /^[\w.]+(?:Error|Exception)$/.test(line));

  return (
    traceback.includes("tornado.websocket.WebSocketClosedError")
    && traceback.includes("tornado/websocket.py")
    && !projectFrame.test(traceback)
    && !unexpectedException.test(traceback)
    && frameFiles.length > 0
    && frameFiles.every((file) => allowedFrame.test(file))
    && terminalLines.at(-1) === "tornado.websocket.WebSocketClosedError"
  );
}

function assertNoUnexpectedServerTracebacks(output, allowBenignTornadoClose) {
  const tracebacks = extractPythonTracebacks(output);
  if (!allowBenignTornadoClose) {
    assert.equal(tracebacks.length, 0, output);
    return;
  }
  for (const traceback of tracebacks) {
    assert.equal(isBenignTornadoWebSocketClose(traceback), true, traceback);
  }
}

async function health() {
  const response = await fetch(`${origin}/_stcore/health`);
  return {ok: response.ok, body: await response.text()};
}

async function waitForHealth(timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (server?.exitCode !== null) {
      throw new Error(`Streamlit exited early (${server.exitCode}).\n${serverOutput}`);
    }
    try {
      const status = await health();
      if (status.ok && status.body.trim() === "ok") return;
    } catch {
      // The socket is expected to refuse connections during startup.
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 150));
  }
  throw new Error(`Streamlit health did not become ready.\n${serverOutput}`);
}

async function waitForPlanner(targetPage = page) {
  await targetPage.getByRole("heading", {name: /Performance Planner|表现计划/}).waitFor();
}

async function checkpointTabPanel() {
  const candidates = page.getByRole("tab", {name: /^(Checkpoints|检查点)$/});
  await page.waitForFunction(() => {
    const labels = /^(Checkpoints|检查点)$/;
    const tabs = Array.from(document.querySelectorAll('[role="tab"]'))
      .filter((element) => labels.test(element.textContent?.trim() ?? ""))
      .filter((element) => {
        const rectangle = element.getBoundingClientRect();
        return rectangle.width > 0 && rectangle.height > 0;
      });
    return tabs.length === 1;
  });
  const liveIds = await candidates.evaluateAll((elements) => elements
    .filter((element) => {
      const rectangle = element.getBoundingClientRect();
      return rectangle.width > 0 && rectangle.height > 0;
    })
    .map((element) => element.id));
  assert.equal(liveIds.length, 1);
  const tab = page.locator(`[id="${liveIds[0]}"]`);
  const panelId = await tab.getAttribute("aria-controls");
  assert.ok(panelId);
  if (await tab.getAttribute("aria-selected") !== "true") {
    await tab.click();
  }
  assert.equal(await tab.getAttribute("aria-selected"), "true");
  const panel = page.locator(`[id="${panelId}"]`);
  await panel.waitFor({state: "visible"});
  return panel;
}

async function waitForCheckpointConfirmation(expected) {
  await page.waitForFunction((shouldExist) => {
    const notice = /Delete this checkpoint|删除此检查点/;
    const exists = Array.from(document.querySelectorAll('[role="tabpanel"]'))
      .some((element) => notice.test(element.textContent ?? ""));
    return exists === shouldExist;
  }, expected);
}

async function checkpointCreateForm() {
  await checkpointTabPanel();
  const expander = page.locator('[data-testid="stExpander"]').filter({
    hasText: /Add neural checkpoint|添加神经检查点/,
  });
  assert.equal(await expander.count(), 1);
  const type = expander.locator('[data-testid="stSelectbox"]').filter({
    hasText: /Checkpoint type|检查点类型/,
  });
  assert.equal(await type.count(), 1);
  if (!await type.isVisible()) await expander.locator("summary").click();
  await type.waitFor({state: "visible"});
  assert.match(await type.textContent(), /Checkpoint type|检查点类型/);
  const form = expander.locator('[data-testid="stForm"]');
  assert.equal(await form.count(), 1);
  assert.equal(await form.getByRole("button", {name: /^(Add|添加)$/}).isEnabled(), true);
  return form;
}

async function findDemoDatabase() {
  const sessions = join(runtimeRoot, "daily-recovery-coach-demo", "sessions");
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    try {
      const entries = await readdir(sessions);
      if (entries.length) return join(sessions, entries[0], "demo.db");
    } catch {
      // Session directory is created after the first Streamlit connection.
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 100));
  }
  throw new Error("Demo database was not created");
}

function checkpointCount(databasePath) {
  const result = spawnSync(
    python,
    [
      "-c",
      "import sqlite3, sys; "
        + "print(sqlite3.connect(sys.argv[1]).execute("
        + "'SELECT COUNT(*) FROM performance_checkpoints').fetchone()[0])",
      databasePath,
    ],
    {encoding: "utf8"},
  );
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  return Number(result.stdout.trim());
}

before(async () => {
  runtimeRoot = await mkdtemp(join(tmpdir(), "rhythmos-planner-runtime-"));
  server = spawn(
    python,
    [
      "-m", "streamlit", "run", "src/dashboard.py",
      "--server.address=127.0.0.1",
      `--server.port=${port}`,
      "--server.headless=true",
      "--browser.gatherUsageStats=false",
    ],
    {
      cwd: repository,
      env: {
        ...process.env,
        DRC_DEMO_MODE: "1",
        PYTHONPATH: repository,
        TMPDIR: runtimeRoot,
      },
    },
  );
  server.stdout.on("data", (chunk) => { serverOutput += chunk.toString(); });
  server.stderr.on("data", (chunk) => { serverOutput += chunk.toString(); });
  await waitForHealth();

  const localChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  browser = await chromium.launch({
    headless: true,
    ...(existsSync(localChrome) ? {executablePath: localChrome} : {}),
  });
  context = await browser.newContext({viewport: {width: 390, height: 844}});
  page = await context.newPage();
});

after(async () => {
  await browser?.close();
  if (server && server.exitCode === null) {
    server.kill("SIGTERM");
    await new Promise((resolveWait) => {
      server.once("exit", resolveWait);
      setTimeout(resolveWait, 3000);
    });
  }
  const outputBeforeClose = serverOutputBeforeContextClose ?? serverOutput;
  const outputAfterClose = serverOutput.slice(outputBeforeClose.length);
  assertNoUnexpectedServerTracebacks(outputBeforeClose, false);
  assertNoUnexpectedServerTracebacks(outputAfterClose, true);
  if (runtimeRoot) await rm(runtimeRoot, {recursive: true, force: true});
});

test("Planner CRUD, overlap, checkpoint link, and recommendation survive refresh", async () => {
  await page.goto(`${origin}/Performance_Planner`, {waitUntil: "domcontentloaded"});
  await waitForPlanner();
  assert.equal((await health()).body.trim(), "ok");

  const createForm = page.locator('[data-testid="stForm"]').first();
  await createForm.getByRole("textbox", {name: /Plan title|计划标题/}).fill("Browser workday");
  await createForm.getByRole("button", {name: /Create plan|创建计划/}).click();
  await page.getByRole("tab", {name: /Schedule|日程/}).waitFor();

  const blockForm = page.locator('[data-testid="stForm"]').first();
  await blockForm.getByRole("textbox", {name: /Block title|时间块标题/}).fill("Browser focus");
  await blockForm.getByRole("button", {name: /^Add$|^添加$/}).click();
  await page.getByText("Browser focus", {exact: true}).waitFor();

  await page.getByText(/Add plan block|添加计划时间块/).click();
  const overlapForm = page.locator('[data-testid="stForm"]').first();
  await overlapForm.getByRole("textbox", {name: /Block title|时间块标题/}).fill("Overlap");
  await overlapForm.getByRole("button", {name: /^Add$|^添加$/}).click();
  await page.getByText(/overlaps another block|与其他时间块重叠/).waitFor();

  const checkpointForm = await checkpointCreateForm();
  await checkpointForm.getByRole("button", {name: /^Add$|^添加$/}).click();
  await page.getByText(/Quick Neural Check|快速神经检查/).waitFor();

  const demoDatabase = await findDemoDatabase();
  const seed = String.raw`
from src.db import connect
import sys
with connect(sys.argv[1]) as c:
    c.execute("""INSERT INTO cognitive_training_sessions(
        id, training_plan, session_mode, started_at, completed_at, timezone,
        completed, interrupted, device_context, protocol_version
    ) VALUES(
        'planner-browser-run', 'focus_alertness', 'quick',
        '2026-07-29T08:00:00', '2026-07-29T08:05:00', 'Asia/Shanghai',
        1, 0, '{}', 'planner-browser-v1'
    )""")
    c.commit()
`;
  const seeded = spawnSync(python, ["-c", seed, demoDatabase], {
    cwd: repository,
    env: {...process.env, PYTHONPATH: repository},
    encoding: "utf8",
  });
  assert.equal(seeded.status, 0, `${seeded.stdout}\n${seeded.stderr}`);

  const checkpointPanel = await checkpointTabPanel();
  const linkForm = checkpointPanel.locator('[data-testid="stForm"]').filter({
    hasText: /Training run ID|训练 run ID/,
  });
  assert.equal(await linkForm.count(), 1);
  await linkForm.getByRole("textbox", {name: /Training run ID|训练 run ID/})
    .fill("planner-browser-run");
  await linkForm.getByRole("button", {name: /Link completed run|关联已完成训练/}).click();
  await page.getByText(/Run linked|run 已关联/).waitFor();

  const secondCheckpointForm = await checkpointCreateForm();
  await secondCheckpointForm.getByRole("button", {name: /^Add$|^添加$/}).click();
  await page.getByText(/Quick Neural Check|快速神经检查/).last().waitFor();
  assert.equal(checkpointCount(demoDatabase), 2);

  let activeCheckpointPanel = await checkpointTabPanel();
  let deleteButtons = activeCheckpointPanel.getByRole("button", {name: /^Delete$|^删除$/});
  await deleteButtons.last().click();
  await waitForCheckpointConfirmation(true);
  activeCheckpointPanel = await checkpointTabPanel();
  await activeCheckpointPanel.getByText(/Delete this checkpoint|删除此检查点/).waitFor();
  assert.equal(checkpointCount(demoDatabase), 2);

  await activeCheckpointPanel.getByRole("button", {name: /^Cancel$|^取消$/}).click();
  await waitForCheckpointConfirmation(false);
  assert.equal(checkpointCount(demoDatabase), 2);

  activeCheckpointPanel = await checkpointTabPanel();
  deleteButtons = activeCheckpointPanel.getByRole("button", {name: /^Delete$|^删除$/});
  await deleteButtons.last().click();
  await waitForCheckpointConfirmation(true);
  activeCheckpointPanel = await checkpointTabPanel();
  await activeCheckpointPanel.getByRole(
    "button",
    {name: /Confirm deletion|确认删除/},
  ).click();
  await page.getByText(/Checkpoint deleted|检查点已删除/).waitFor();
  assert.equal(checkpointCount(demoDatabase), 1);

  await page.getByRole("tab", {name: /Adaptations|自适应建议/}).click();
  await page.getByRole("button", {name: /Evaluate plan now|立即评估计划/}).click();
  await page.getByText(/The plan remains unchanged|只有在你明确确认/).waitFor();

  await page.reload({waitUntil: "domcontentloaded"});
  await waitForPlanner();
  await page.getByRole("tab", {name: /Schedule|日程/}).click();
  await page.getByText("Browser focus", {exact: true}).waitFor();
  assert.equal((await health()).body.trim(), "ok");
  assert.equal(server.exitCode, null);
});

test("Planner has no horizontal overflow at 320, 375, and 390 px and isolates sessions", async () => {
  for (const width of [320, 375, 390]) {
    await page.setViewportSize({width, height: 844});
    await page.goto(`${origin}/Performance_Planner`, {waitUntil: "domcontentloaded"});
    await waitForPlanner();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    assert.ok(overflow <= 1, `horizontal overflow at ${width}px: ${overflow}px`);
  }

  const isolatedContext = await browser.newContext({viewport: {width: 390, height: 844}});
  const isolatedPage = await isolatedContext.newPage();
  await isolatedPage.goto(`${origin}/Performance_Planner`, {waitUntil: "domcontentloaded"});
  await waitForPlanner(isolatedPage);
  await isolatedPage.getByText(/No plan exists for this date yet|该日期尚无计划/).waitFor();
  serverOutputBeforeContextClose = serverOutput;
  await isolatedContext.close();

  assert.equal(page.isClosed(), false);
  const status = await health();
  assert.equal(status.ok, true);
  assert.equal(status.body.trim(), "ok");
  assert.equal(server.exitCode, null);
});
