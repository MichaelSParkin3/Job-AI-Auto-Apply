# Epic 9 — Scheduler & Unattended Runs

## Expanded Goal
Close the autonomy roadmap by packaging auto-submit into repeatable scheduled jobs. Provide CLI helpers that generate OS-native schedules (Task Scheduler XML, cron snippets), expose run status dashboards, and ensure scheduled runs respect quiet hours and fail safely.

## Story 9.1 — Scheduler Planning Commands
As a power user,
I want CLI commands that generate schedule artifacts,
so that I can set up daily runs without hand-crafting scripts.

Acceptance Criteria
1. `python -m apps.cli scheduler plan --profile <id> --search <url> --mode auto_submit --time 14:00` outputs Task Scheduler XML (`.xml`) and cron snippet (`.cron`) files.
2. Planner validates profile allows auto submit; warns if confidence threshold < recommended baseline.
3. Generated artifacts include environment setup instructions (activate venv, ensure Chrome installed).
4. Tests cover Windows XML + cron text generation using golden fixtures.

## Story 9.2 — Scheduler Runner & Heartbeat
As an operator,
I want scheduled runs to report status back to the UI,
so that I can monitor progress while away from the terminal.

Acceptance Criteria
1. CLI accepts `scheduler run --plan <file>` which launches `apply` with correct flags and writes PID/metadata to `runs/<id>/scheduler.json`.
2. Scheduled runs ping `/api/queue/{runId}/heartbeat` every 30s; UI shows “Scheduled run active” banner with last heartbeat.
3. Heartbeat includes `nextRunAt` and `planName` metadata for dashboards.
4. Integration tests simulate heartbeat loss; UI marks run as “stale” and emits toast.

## Story 9.3 — Quiet Hours & Conflict Handling
As a user,
I want to control when auto runs happen,
so that the tool respects my schedule and avoids overlapping sessions.

Acceptance Criteria
1. Profiles support `automation.schedule` block with `quiet_hours` (e.g., `22:00-07:00`) and max concurrent runs.
2. Scheduler runner checks quiet hours before starting; if blocked, logs reason and exits with code `75`.
3. If another run is active, new schedule defers until queue clears; records deferral event in history.
4. Tests cover quiet hour enforcement and conflict detection.

## Story 9.4 — Dashboard & History Enhancements
As a reviewer,
I want a consolidated view of scheduled activity,
so that I can audit outcomes quickly.

Acceptance Criteria
1. Preview UI adds “Scheduled Runs” tab summarizing last N runs (mode, duration, auto-submitted count, overrides).
2. History CLI gains `history schedule --plan <name>` filter.
3. `history.jsonl` records `schedulePlan` metadata (name, cadence) per run.
4. Provide Markdown template `docs/templates/scheduler-runbook.md` explaining how to enable/disable schedules safely.
5. Tests verify UI tab renders with mocked API data.

## Story 9.5 — Failure Recovery & Notifications
As an operator,
I want robust failure handling for scheduled runs,
so that unattended jobs never fail silently.

Acceptance Criteria
1. Scheduler runner retries failed runs once (configurable) before escalating to manual review.
2. On repeated failure, CLI sends notification (Windows toast / console) linking to logs and queue state.
3. History entry flagged with `status=failed_scheduled` when both attempts fail; includes reason.
4. Provide optional email hook (local SMTP config) for users who want email alerts.
5. Regression tests cover failure escalation and notification toggles.

### Rationale (Epic 9)
With scheduling in place, the autonomy ladder is complete. Users can opt into daily unattended runs confident that guardrails from prior epics will intervene when needed, and that every scheduled execution is observable and reversible.
