# Epic 1 — Foundation & Review UI

## Expanded Goal
Establish a working foundation that proves the review-first experience. Ship a CLI skeleton, configuration loader, and a FastAPI preview server that serves a minimal React + shadcn/ui interface. The UI must open in Chrome app-mode and render a placeholder screenshot with functional Approve/Edit/Abort and keyboard shortcuts, as a safe Dry-Run simulation.

## Story 1.1 — Project Scaffold & Config Loader
As a developer,
I want a structured repo with a Typer CLI and config loader,
so that I can run commands and manage defaults consistently.

Acceptance Criteria
1: Running `python app.py --help` lists `apply`, `profiles`, `config`, `history`.
2: `config init` creates `config/config.yaml` with documented defaults.
3: `.env.local` is read for OpenRouter keys without crashing if missing.
4: Required folders exist on first run: `config/`, `data/`, `.local/`, `runs/`, `history/`.
5: Precedence documented: CLI → profile → global.

## Story 1.2 — Preview Server Skeleton
As a user,
I want a preview window served on port 4950,
so that I can review a submission before it’s sent.

Acceptance Criteria
1: `python app.py preview --demo` starts FastAPI on 4950 and opens Chrome app-mode.
2: UI uses shadcn/ui with `Button`, `Dialog`, `Card`, and `Toast` primitives.
3: Keyboard shortcuts: `A`=Approve, `E`=Edit, `Esc`=Abort.
4: Placeholder screenshot rendered with alt text and text summary region.
5: Dry-Run mode visibly indicated; Approve/Abort only simulate actions.

## Story 1.3 — Profiles Schema & Commands
As a user,
I want to create and validate role profiles,
so that each application uses the correct identity and resume.

Acceptance Criteria
1: `profiles new <id>` writes `data/profiles/<id>.yaml` using a template.
2: Schema includes identity, Q&A, model overrides, `documents.resume_path`.
3: `profiles validate <id>` checks YAML and resume presence at `data/resumes/<id>/resume.pdf`.
4: `profiles list` shows available profiles and their status.
5: Profile switching persists for the current session.

## Story 1.4 — Run Store & Redacted Logging (Skeleton)
As an operator,
I want consistent run folders and redacted logs,
so that I can audit behavior without exposing PII.

Acceptance Criteria
1: `runs/<run_id>/` is created for each demo run with timestamps.
2: `actions.log` contains structured JSON lines with redacted PII tokens.
3: `history/history.jsonl` appends a minimal entry for demo runs.
4: Crash-safe append behavior verified on Windows.
5: Configurable retention placeholders present (no deletion yet).

## Story 1.5 — Dry-Run Demo Flow
As a cautious user,
I want a complete demo path with no external browsing,
so that I can test the UI/UX safely.

Acceptance Criteria
1: `apply --dry-run --limit 1 --demo` renders the preview UI with a canned placeholder.
2: Approve/Abort paths update a demo `run.json` and toasts status.
3: Edit opens a Dialog text box and simulates one retry.
4: A demo `run.json` is written to the run folder with summary fields.
5: No network calls to SimplyHired occur in demo mode.

### Rationale (Epic 1)
- Focuses on trust and local-first preview before any live automation. Stories are sequenced from scaffolding → UI → profiles → logging → demo end-to-end, each completable by a single agent session and testable locally.

---
