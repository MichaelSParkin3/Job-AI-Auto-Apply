# User Interface Design Goals

## Overall UX Vision
A minimal, distraction-free review experience that keeps the user firmly in control: show the final review page screenshot, summarize key extracted fields (job, company, location, answers, salary if any), and provide three clear actions (Approve, Edit, Abort). Default to Review mode for trust; allow Dry-Run to exercise the flow safely. Layer in AI suggestions with clear confidence badges, give power users a queue view to batch decisions, and surface auto-run dashboards without overwhelming the core review screen.

## Key Interaction Paradigms
- Single window (Chrome app-mode) anchored to port 4950 with optional queue drawer
- Approve/Edit/Abort primary actions with keyboard shortcuts: `A`, `E`, `Esc`
- Queue navigation shortcuts: `J/K` (next/prev), `Shift+A` (approve), `Shift+X` (send to human review)
- Edit: lightweight text box for small corrections (e.g., “set salary to 125k”); one retry then back to review
- Deterministic states: Loading → Review → Submitting → Confirmation/Error → Back to Review (if needed) plus AI-specific states (`AI deciding`, `Awaiting human override`)
- Human-like pacing hints and status to explain pauses (builds trust)
- Clear redaction markers in any text preview to avoid exposing PII in logs
- Confidence badges highlight AI recommendations; tooltips explain rationale summaries

## Primary User Journey (MVP)
1. Start: user runs CLI with a SimplyHired search URL and selects an active profile; app launches headful Chrome and prepares preview server (port 4950).
2. Discover: agent scans the left results list, opens a candidate with Quick Apply, and fills the form deterministically (no submit yet).
3. Fill: agent maps fields from profile, uploads the resume PDF, and compiles a submission summary with a pre‑submit screenshot.
4. Review: preview window shows the screenshot and summary; user chooses Approve, Edit, or Abort.
5. Edit (optional): user enters a short correction; agent attempts a single targeted retry and refreshes the summary/screenshot.
6. Approve and Submit: on approval, agent submits once; on failure, auto‑retries once, otherwise returns to Review with reasons.
7. Finalize and History: artifacts and `run.json` are written; a JSONL history entry is appended; dedupe fingerprint prevents re‑apply within 30 days.

## Extended Journeys
- **AI Assist Mode:** Queue populates with multiple candidates; AI scores each and surfaces suggested outcomes. User reviews AI rationales, approves with a single keystroke, or bounces items back for manual editing.
- **Full Auto Mode:** UI displays read-only auto-run dashboard with progress, confidence histogram, and override controls. Users can jump in mid-run to pause, abort, or reclaim specific candidates into manual review.
- **Scheduled Runs:** When launched unattended, the UI highlights that the session is scheduler-triggered, shows next run time, and provides quick links to history entries for previous auto batches.

## Component Library: shadcn/ui
- Use `shadcn/ui` (Tailwind CSS component library) for accessible, consistent, and fast-to-assemble UI components.
- Core MVP components: `Button`, `Dialog` (Edit overlay), `Card`, `Toast/Toaster` (status), `Skeleton` (loading), `Separator`, and `Spinner`.
- Implementation: Minimal React + Vite UI served as static assets by FastAPI under `/ui` and opened in Chrome app-mode; keep footprint small.
- Rationale: High-quality, accessible components reduce bespoke CSS/JS, speed up delivery, and align with desktop-only Windows target.

## Core Screens and Views
- Preview Window (MVP)
- Queue Drawer (AI Assist) with filters and decision history
- Auto-Run Dashboard (Full Auto) summarizing progress, confidence, and overrides
- Edit Overlay (MVP)
- Submission Confirmation / Error State (MVP)
- History View (Post-MVP) — open run folder or show a simple list with links

## Accessibility: WCAG AA
- Color contrast ≥ 4.5:1 and scalable type
- Full keyboard navigation and visible focus rings
- Descriptive labels/ARIA for buttons and status
- Alt text for screenshots plus text summary of detected fields

## Branding
- Minimal, neutral styling with a single accent color
- System fonts; prioritize clarity and speed over heavy branding

## Target Device and Platforms: Desktop Only (Windows)
- Local FastAPI server with static `/ui` (React + Vite + Tailwind + shadcn/ui)
- Fixed window size consistent with stable viewport for stealth

### Assumptions and Rationale (UI Goals)
- Prioritizes speed, clarity, and trust over rich UI; screenshot-first aligns with “review-by-default.” Keyboard shortcuts reduce friction. shadcn/ui provides accessible, consistent components with minimal setup using Tailwind. Desktop-only (Windows) matches platform constraints in the brief and stabilizes viewport for stealth.

---
