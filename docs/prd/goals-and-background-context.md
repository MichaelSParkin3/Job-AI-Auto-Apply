# Goals and Background Context

## Goals
- Automate SimplyHired “Quick Apply” submissions with a review gate by default
- Support multiple role-specific profiles, each with its own resume, links, and Q&A
- Operate with a stealth-first, human-like automation posture using headful Chrome
- Keep all user data and artifacts strictly local; never store PII in the cloud
- Provide a minimal preview UI (port 4950) to Approve/Edit/Abort before submit
- Persist a complete audit trail per run with screenshots and a redacted step log
- Capture and store full job description text and HTML snapshots for every run
- Avoid duplicate applications within a 30-day window via content fingerprinting
- Achieve ≥ 95% successful submits in Review mode; median submit time ≤ 120s
- Enable quick profile switching (≤ 2s) and ≤ 1 manual correction per application
- Offer a safe Dry-Run mode that never submits but exercises the full flow

## Background Context
Many job seekers repeatedly re-enter the same information across postings while juggling multiple role personas (e.g., Frontend Developer and Music Producer) that require distinct resumes and narratives. UI drift and anti-bot measures on SimplyHired can break brittle scripts, while privacy concerns make cloud-based tools unattractive. This project delivers a local-first Windows app using Browser-Use (Playwright-based, LLM-driven) to automate SimplyHired “Quick Apply” with a stealth posture and a review-first workflow. It emphasizes privacy (local storage only), reliability (artifacted audit trail and dedupe), and user control (approve/edit/abort) to increase throughput without sacrificing accuracy or trust.

## Change Log
| Date       | Version | Description                     | Author |
|------------|---------|---------------------------------|--------|
| 2025-09-25 | v0.1    | Initial PRD draft from brief    | PM John |

---
