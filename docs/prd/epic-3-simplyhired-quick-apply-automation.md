# Epic 3 — SimplyHired Quick Apply Automation

## Expanded Goal
Detect and open the Quick Apply flow on a job detail, robustly map form fields (tolerant to common A/B variants), fill values from the active profile using a top-down, human-like strategy, deterministically upload the resume PDF, and compile a clear submission summary and pre-submit screenshot for the review UI. No actual submission in this epic.

## Story 3.1 — Quick Apply Discovery & Safe Open
As an applicant,
I want the agent to scan the left results list, find Quick Apply postings, safely open each Quick Apply, then return to the results to continue,
so that it can process many applications in one run without duplicates and with pagination when needed.

Acceptance Criteria
1: From a SimplyHired search page (left list + right detail), scans the left list top‑to‑bottom to identify cards with a Quick Apply marker; ignores off‑site "Apply" links.
2: For each candidate, opens the job detail (right pane) and safely opens the Quick Apply module (modal or in‑page) without submitting; emits events: `QA_CANDIDATE`, `QUICK_APPLY_OPENED` (or `QUICK_APPLY_MISSING`).
3: After safe open, closes the module (or navigates back) and returns focus to the search page, resuming scan at the next unvisited card. Maintains an in‑run visited set keyed by `posting_url`/card id to avoid re‑opening the same job. (Cross‑run dedupe is out‑of‑scope; see Epic 5.)
4: Honors `--limit N` (default 2): stops after processing N Quick Apply candidates or end‑of‑results, whichever comes first.
5: Pagination: when the current list is exhausted and the limit is not reached, detects and uses pagination controls (Next/numbered) to load the next results page and continues scanning; emits `PAGINATED_NEXT` and `END_OF_RESULTS` when appropriate.
6: Guardrails enforced throughout: single‑tab policy and allowed domains only; logs `BLOCKED_DOMAIN` on violations.
7: Fixture tests cover: (a) multiple Quick Apply markers on one page; (b) two‑page results with Next; (c) duplicate item across pages skipped by the visited set; (d) modal and in‑page variants.

## Story 3.2 — Form Structure Mapping & Selector Library
As a developer,
I want a small selector library and heuristics to map visible form labels/inputs to profile fields,
so that filling is resilient to minor label or layout changes.

Acceptance Criteria
1: JSON/YAML selector map defines label synonyms (e.g., "Full Name", "Your name").
2: Heuristics resolve label→input pairs, including radios, selects, checkboxes, and textareas.
3: Emits `FORM_MAPPED` with a structured plan of fields to fill; unknowns marked `UNMAPPED`.
4: Unit tests validate mapping for common fields and A/B label variants.
5: Unknowns fall back to a conservative skip with log entries; no crash.

## Story 3.3 — Profile-Driven Filling & Validation
As an applicant,
I want fields filled from my active profile with sensible defaults and safety checks,
so that answers are accurate and consistent.

Acceptance Criteria
1: Fills common identity, eligibility, and contact fields from profile YAML.
2: Applies constraints and transformations (e.g., strip PII from logs, normalize phone formats).
3: Radios/selects are chosen by synonym matching; textareas use concise, non-PII summaries if needed.
4: Emits `FIELD_FILLED`/`FIELD_SKIPPED` events with reasons; logs are redacted.
5: Dry-run never clicks submit; live mode stops before submit in this epic.

## Story 3.4 — Deterministic Resume Upload
As an applicant,
I want the resume PDF uploaded reliably,
so that the application includes my document every time.

Acceptance Criteria
1: Uses a deterministic Playwright file chooser to upload `data/resumes/<profile>/resume.pdf`.
2: Verifies upload success via filename/attachment indicator.
3: Retries once with backoff; on failure emits `UPLOAD_FAILED` with snapshot.
4: Respects Dry-Run by simulating upload without network/file mutation.
5: Tests mock the upload control and success indicator states.

## Story 3.5 — Submission Summary & Pre-Submit Screenshot
As a user,
I want a concise submission summary and a pre-submit screenshot,
so that I can review everything before approving.

Acceptance Criteria
1: Extracts key fields (job title, company, location, answers summary non‑PII) into a `summary` object.
2: Captures a pre-submit screenshot of the review/confirmation step if present; otherwise, composes a synthetic summary view.
3: Writes a draft `run.json` into the run folder with the `summary` but no `status=submitted`.
4: Emits `SUMMARY_READY` and stores the screenshot path in artifacts.
5: Integration tests verify `summary` contents and artifact creation in dry-run fixtures.

### Rationale (Epic 3)
- Builds the core automation that feeds the review gate without risking premature submission. Selector library + heuristics absorb UI drift; deterministic upload covers the most brittle step; the summary provides the UI everything it needs for clear user approval in the next epic.

---
