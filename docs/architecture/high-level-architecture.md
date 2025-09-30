# High Level Architecture

## Technical Summary
- Architecture: Local-first, privacy-preserving monolith with clear modular boundaries. Python (Typer CLI + FastAPI preview server) orchestrates the full flow; a small React + Vite UI runs as static assets served by FastAPI.
- Decision & Run Modes: The CLI now owns a pluggable decision engine that operates in explicit modes (`review`, `ai_autofill`, `auto_review`, `auto_submit`) so we can support human approval, AI-assisted form filling with assisted submit, and unattended submission without branching the core pipeline.
- Frontend: React 18 + Vite + Tailwind + shadcn/ui, focused on a single Preview window to Approve/Edit/Abort. UI is small, offline-first, and keyboard-centric.
- Backend: FastAPI app embedded alongside the CLI process provides Preview routes, serves static UI, and exposes a minimal REST API for the UI to control runs and edits.
- Browser automation: Headful Chrome via Browserâ€‘Use + Playwright with a stealth posture, single-tab, profile-specific persistent session, deterministic fallbacks for uploads/widgets, and now an LLM-guided auto-fill executor that can hand the form back to humans when CAPTCHA or MFA is detected.
- Storage: File-first artifacts (screenshots/video optional), `run.json`, HTML snapshots, and `history.jsonl`, now extended with decision audit trails (confidence, rationale) and queue snapshots so we can reconcile human and AI actions after the fact. Optional local SQLite index can be introduced later for search/analytics; not needed for MVP.
- Goals alignment: Meets PRD privacy (local-only PII), reliability (95% success, retry), performance (â‰¤120s median), dedupe, and the revised autonomy roadmap (LLM-driven auto fill proof, advisory AI, full auto, scheduler) without sacrificing auditability or user override controls.

## Platform and Infrastructure Choice
**Options considered**
- Local Desktop (Windows) only: No external hosting; dev CI via GitHub Actions.
- Vercel + Supabase: Great for web apps, conflicts with privacy constraints (PII cloud storage).
- AWS/GCP/Azure: Powerful but unnecessary for MVP; increases cost/scope; privacy trade-offs.

**Recommendation**
- Platform: Local Desktop (Windows 10/11). No cloud data storage. Optional GitHub Actions for CI (tests/build only, no PII). Future unattended runs rely on OS-native schedulers (Task Scheduler, cron) triggered via a lightweight adapter once full-auto mode is available.
- Key Services: Windows filesystem, Chrome Stable, Playwright (Chromium), Python 3.11 runtime, Node 22 for building UI only.
- Deployment Host and Regions: N/A (local-only).

## Repository Structure
- Structure: Monorepo with Python + Node subprojects; file-first storage.
- Monorepo Tool: pnpm workspaces for UI; Python managed by `uv` or `venv` (documented), no polyglot mega-tooling required.
- Package Organization: `apps/cli` (Typer + orchestration), `apps/preview` (FastAPI), `apps/ui` (React), `sites/simplyhired, sites/lever` (playbooks/locators), `packages/shared` (TS types used by UI; Python shares pydantic models locally).

## High Level Architecture Diagram
```mermaid
flowchart LR
    U[User] -->|CLI args
    | Typer | CLI((CLI Orchestrator))
    subgraph Local Machine (Windows)
      CLI --> PREV[FastAPI Preview Server]
      PREV <-->|HTTP JSON + Static UI| UI[React + Vite (shadcn/ui)]
      CLI --> DEC[Decision Engine\n(Human & AI modes)]
      DEC --> QUEUE[Review Queue\n(pending candidates)]
      CLI --> BR[Browserâ€‘Use (Playwright, Chrome headful)]
      BR --> G[Google SERP]
      BR --> L[Lever Apply]
      CLI --> ART[Artifacts Store (screenshots, run.json, logs)]
      CLI --> HIST[history.jsonl]
      CLI --> DEDUPE[Dedupe Fingerprint]
      SCHED[Scheduler Adapter\n(cron/Task Scheduler)] --> CLI
    end
G:::ext
  L:::ext
classDef ext fill:#fff,stroke:#999,stroke-dasharray: 5 5
```

## Architectural Patterns
- Jamstackâ€‘style UI: Static UI served by local FastAPI for simplicity and speed â€” Rationale: Zero external hosting, fast load, minimal surface.
- Modular Monolith: Python app segmented into domain modules (config, profiles, browser, preview, artifacts) â€” Rationale: Lower complexity than services, easy local ops.
- BFF (Backend for Frontend): Preview server mediates UI â†” CLI â€” Rationale: Stable API boundary, testable UI.
- Repository Pattern (Fileâ€‘based): Encapsulate read/write of artifacts/history â€” Rationale: Enables swap to SQLite later without UI/CLI churn.
- Circuit Breaker/Retry on Submission: Controlled single retry on failure â€” Rationale: Hit reliability target without infinite loops.
- Deterministic Fallbacks: Playwright scripted steps for uploads/widgets â€” Rationale: Resilience when LLM actions drift.

---

