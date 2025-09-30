# Epic 8 — Artifacts, History & Dedupe Hardening

## Expanded Goal
Make the system durable and auditable at scale by capturing comprehensive artifacts, writing a robust append-only history with atomicity on Windows, enforcing a 30-day dedupe policy, managing storage with retention and thresholds, and finalizing reliability measures (Playwright fallbacks, retries, session backups).

## Story 8.1 — Artifact Capture & Retention Controls
As an operator,
I want controllable artifact capture and retention,
so that I can balance auditability with disk usage.

Acceptance Criteria
1: Config/CLI `--artifacts` supports `screenshots|video|both` with `screenshots` default.
2: Every significant step produces a screenshot; file paths logged in `run.json`.
3: Retention policy: default keep 30 days; `config cleanup` removes expired run folders and empty parents.
4: Storage threshold warnings at configurable GB/% thresholds; logs `STORAGE_THRESHOLD` event.
5: Tests simulate retention and threshold warnings without deleting non-expired runs.

## Story 8.2 — History JSONL Append & Atomicity
As a developer,
I want a crash-safe, atomic append to `history/history.jsonl`,
so that history is consistent even on Windows.

Acceptance Criteria
1: Append uses temp-file + rename with file locks to avoid partial writes.
2: History entry schema includes all fields from the brief (ids, timestamps, URLs, fingerprint, status, artifacts, answers summary, JD text path, HTML snapshot path).
3: Failures roll back without corrupting the file; emits `HISTORY_APPEND_FAILED` with details.
4: Unit tests inject I/O failures to verify atomicity and rollback.
5: A small `history index` utility lists last N entries with filters.

## Story 8.3 — JD Capture & HTML Snapshot
As a user,
I want the full job description text and HTML snapshot saved per run,
so that I have a complete local audit trail.

Acceptance Criteria
1: Extracts JD text from the detail pane; writes to `runs/<id>/jd.txt`.
2: Saves a sanitized HTML snapshot to `runs/<id>/page.html`.
3: Paths recorded in `run.json` and history entry.
4: Privacy: PII redaction rules applied to logs; raw JD stored as-is.
5: Fixture-based tests verify extraction and file creation.

## Story 8.4 — Dedupe Policy Enforcement (30 Days)
As an applicant,
I want the system to avoid re-applying within 30 days for the same posting + JD content,
so that I don’t spam employers.

Acceptance Criteria
1: Fingerprint = `posting_url + sha256(job_description_full)`; matches within 30 days are marked `duplicate` and skipped.
2: `--reapply` flag bypasses dedupe only after 30 days or when explicitly allowed.
3: Skipped duplicates write an entry with `status=duplicate` and reason.
4: History lookup is O(1) or batched with an index to keep performance acceptable.
5: Tests cover duplicate detection, window expiry, and reapply behavior.

## Story 8.5 — Reliability Hardening & Fallbacks
As an operator,
I want improved reliability for brittle steps,
so that transient issues don’t derail runs.

Acceptance Criteria
1: Playwright fallback paths integrated for uploads and stubborn widgets; triggered by explicit failure codes.
2: Auto-retry once on upload/submit failures with exponential backoff; emits `RETRYING` events.
3: Session backup/restore from Epic 2 finalized with rotation and metrics.
4: Error taxonomy finalized and documented; mapped to user-facing toasts and log codes.
5: Integration tests simulate failure→retry→success and failure→retry→fail paths.

### Rationale (Epic 8)
- Locks in auditability and trust (artifacts/history), enforces respectful behavior (dedupe), and improves resilience (fallbacks/retries). Windows-focused atomic writes prevent corruption; storage controls keep local-first sustainable.

---
