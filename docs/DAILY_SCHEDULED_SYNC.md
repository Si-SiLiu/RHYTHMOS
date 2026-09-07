# Scheduled Polar Sync

RHYTHMOS｜律衡 uses the user-level macOS LaunchAgent
`com.daily-recovery-coach.sync` to start the existing One-Click Sync Pipeline at
two-hour intervals from 00:00 through 22:00 in the Mac's local time zone. The
scheduler contains no Fetch, Import, Recovery, or reporting business logic and
never invokes Cloud AI.

The periodic schedule is intentionally selective:

- Polar daily activity, training, sleep, recovery, and continuous heart-rate
  data refresh every two hours.
- The cadence includes the required 12:00 and 22:00 local-time refreshes.
- No periodic Polar refresh runs after the 22:00 slot.

## Configuration

`config/scheduler.toml` remains the authority for enabling the LaunchAgent and
catch-up policy. Its legacy `sync_time` value is retained for catch-up status
compatibility; the installed LaunchAgent uses the fixed cadence above. Invalid
or damaged configuration falls back in memory and does not overwrite the
damaged file.

The System Information page can validate and save a strict `HH:MM` time. Saving
regenerates and reloads the LaunchAgent. Page load only inspects state; it never
starts a sync automatically.

## Install and remove

```bash
.venv/bin/python scripts/install_daily_sync_launch_agent.py --dry-run
.venv/bin/python scripts/install_daily_sync_launch_agent.py
.venv/bin/python scripts/uninstall_daily_sync_launch_agent.py
```

The generated plist is stored at
`~/Library/LaunchAgents/com.daily-recovery-coach.sync.plist`. It uses the
project-local virtual environment and the actual project runner. The child
runner establishes the project directory before importing the Pipeline. This
avoids a macOS privacy restriction that prevents `launchd` itself from opening a
Desktop/Documents path as `WorkingDirectory` while preserving the same runtime
directory for Pipeline code. Standard streams go to
`~/Library/Logs/Daily Recovery Coach/` (legacy compatibility path); the Pipeline's structured safe log
continues to use the project's existing log system. The plist contains no token,
secret, or copied environment variable.

## Trigger provenance and locking

Every canonical `sync_history` row records one of `manual`, `scheduled`, or
`catch_up`. A kernel-backed file lock at `data/sync_pipeline.lock` prevents
overlapping triggers. Abnormal process exit releases the kernel lock; stale
metadata is diagnostic and cannot permanently block a later run.

Selective maintenance commands such as `--only resolution` are marked as
selective and do not count as the day's complete sync. Scheduled and catch-up
runs avoid a second full run after a successful full pipeline on the same day.
Idempotent Polar GET requests retry bounded transient TLS/network, rate-limit,
and server failures before the run is recorded as failed; an explicit catch-up
remains available when all attempts fail.

## Catch-up behavior

After the configured catch-up window, the System Information page displays a
prompt when no full successful sync exists for today. The user may run it now or
defer it. Streamlit reruns never execute catch-up on their own. A Mac that is
asleep, powered off, or logged out during a scheduled window can delay or miss
the LaunchAgent trigger; this is a platform constraint rather than a scheduler
guarantee.
