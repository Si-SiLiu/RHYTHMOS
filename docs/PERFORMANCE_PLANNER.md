# Performance Planner 1.0 MVP

Performance Planner｜表现计划 provides an **Adaptive Workday｜自适应工作日**
without introducing a cloud dependency. It is a local planning surface, not a
medical, diagnostic, or autonomous scheduling system.

## User flow

1. Create one dated plan and add ordered work, learning, meeting, exercise,
   recovery, routine, or other blocks.
2. Add an optional neural checkpoint before/after a block, at a fixed time, or
   manually.
3. Complete the existing Training Studio flow and explicitly link its `run_id`.
   The Planner never copies or rewrites cognitive sessions, task results, or
   trials.
4. Evaluate deterministic local rules. The generated recommendation stores the
   exact source snapshot and its data-sufficiency state.
5. Acknowledge a recommendation or explicitly confirm an applicable plan
   change. Generation and acknowledgment alone never modify the plan.

## Deterministic inputs and outputs

`src.performance_planner` reads the plan and block demand, completion and delay
state, continuous work minutes, recovery/readiness for the plan date, the latest
completed cognitive session summary, and checkpoint state. It returns one or
more allowlisted recommendation types:

- continue as planned
- shorten a delayed block
- add a recovery break
- postpone a high-demand block
- switch the related block to low cognitive demand
- take a neural check
- resume after a check

The rules do not call AI, a model, a provider SDK, or a network API. Missing
signals produce `insufficient`; one signal produces `partial`; two or more
available recovery/readiness/cognitive signals produce `sufficient`.

## Storage and isolation

Schema `0.27.0` keeps the four Planner tables from migration sequence 26 and
adds a recommendation fingerprint index in sequence 27. The Streamlit
page uses the existing database context, so `DRC_DEMO_MODE=1` automatically
routes all Planner CRUD into the current browser session's `demo.db`. Repeating
the same evaluation reuses its recommendation rows. Resetting
the sandbox removes that session only. Local mode continues using the unchanged
formal database path.

## Integration boundaries

- Training Studio remains the only cognitive-task execution surface.
- `cognitive_run_id` is a unique, nullable association validated against a
  completed cognitive session. Replaying the same association is idempotent.
- Progress Lab UI is unchanged. `get_progress_lab_rows()` is a stable read-only
  query surface for a future integration.
- Recovery, Baseline, Confidence, cognitive protocols, and cognitive frontend
  code are unchanged.

## Verification

Python tests are split across Planner behavior, schema migration, and Demo
sandbox isolation. The browser smoke starts an isolated Demo runtime, validates
health, CRUD, overlap rejection, checkpoint/run linking, recommendation
generation, refresh persistence, session isolation, and 320/375/390 px
horizontal overflow.
