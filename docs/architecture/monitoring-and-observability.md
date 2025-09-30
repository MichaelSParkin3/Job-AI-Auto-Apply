# Monitoring and Observability

## Monitoring Stack
- Frontend Monitoring: Console warnings surfaced in UI dev; optional local log capture
- Backend Monitoring: Structured JSON logs with log level; timing for key steps
- Error Tracking: Local log files only; no cloud
- Performance Monitoring: Simple timings for navigation, fill, submit, preview render

## Key Metrics
**Frontend**
- Paint time of `/ui` route
- Action latency: button press → API response
- JS runtime errors count
- Queue panel refresh cadence and stale badge detection

**Backend**
- Request rate and latency per endpoint
- Success/error ratio for submit actions
- Average artifact write times
- Decision engine throughput (decisions/min), split by mode (human vs AI)
- Queue depth over time (`pending`, `escalated`, `auto_submitted`)
- Scheduler run heartbeat latency (when unattended runs enabled)

**Telemetry Events**
- `AUTO_DECISION` — AI returned approve/abort/edit with confidence; includes anonymized rationale hash
- `AUTO_OVERRIDE` — human overrode an AI decision
- `AUTO_FAILSAFE_TRIGGERED` — queue item forced back to manual review due to low confidence or repeated failure
- `AUTOFILL_PLAN_READY` — LLM planner produced an enriched plan with token/latency metrics
- `AUTOFILL_FIELD_FILLED` / `AUTOFILL_FIELD_SKIPPED` — granular fill telemetry with redacted length metadata
- `AUTOFILL_HANDOFF_READY` — submission attempt blocked; includes reason enum and snapshot path
- `HANDOFF_RESUME_LAUNCHED` — user requested assisted submit relaunch; ties to `lastLaunchedAt`
- `AUTOFILL_DEMO_COMPLETED` — at least one auto submit succeeded during the run (used for MVP reporting)

---
