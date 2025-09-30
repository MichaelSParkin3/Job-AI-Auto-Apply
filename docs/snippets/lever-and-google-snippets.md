# Lever Apply + Google SERP Snippets

Collected guidance and minimal HTML/selector snippets to guide discovery and automation for Lever-hosted application forms discovered via Google.

Last updated: 2025-09-29

## Google SERP — Discovery via `site:jobs.lever.co`

- Preferred query: `site:jobs.lever.co/apply <role terms> <location terms>`
  - Examples:
    - `site:jobs.lever.co/apply front end remote`
    - `site:jobs.lever.co/apply "software engineer" "united states"`
- Time filter (programmatic): add `tbs=qdr:<window>` to the search URL
  - `qdr:h` (past hour), `qdr:d` (past 24 hours), `qdr:w` (past week), `qdr:m` (past month), `qdr:y` (past year)
  - Example (past week):
    - `https://www.google.com/search?q=site:jobs.lever.co/apply+front+end&tbs=qdr:w`
- Pagination: increment the `start` parameter by 10 (`start=0,10,20,…`).
- Cleaner SERP (optional): add `udm=14` to reduce UI noise in some regions.

Minimal result targeting strategy:

```text
Within Google results, prefer anchors where href starts with
  https://jobs.lever.co/ and either ends with /apply or contains /apply?
Fallback: open the job page on jobs.lever.co and click the visible
  "Apply for this job" control to reach the /apply form.
```

Operational guardrails:
- Respect Google’s ToS and throttling. Use human-like pacing and small `--limit` values.
- Avoid clicking ads (`/aclk`, `googleadservices.com`) and rich result widgets.

### DOM Snippets & Selectors (Google)

- Search input (type query directly, avoid clicking Tools UI):
  - `textarea#APjFqb.gLFyf[name="q"]`

```html
<!-- Google search bar (trimmed) -->
<div class="RNNXgb">
  <div class="a4bIc">
    <textarea id="APjFqb" name="q" class="gLFyf" aria-label="Search">site:jobs.lever.co front end</textarea>
  </div>
  <button class="HZVG1b" aria-label="Search"></button>
</div>
```

- Organic result link (title + anchor):
  - Card: `div.tF2Cxc`
  - Anchor: `div.yuRUbf a.zReHs[href^="https://jobs.lever.co/"]`
  - Title: `h3.LC20lb`

```html
<!-- One SERP result (trimmed) -->
<div class="tF2Cxc">
  <div class="yuRUbf">
    <a class="zReHs" href="https://jobs.lever.co/xsolla/e6b20...">
      <h3 class="LC20lb">Xsolla - Front End Engineer</h3>
    </a>
  </div>
  <div class="VwiC3b">6 days ago — Ensure performance…</div>
</div>
```

- Pagination (prefer building URL with `start=10n`; for robustness you can also click):
  - Next: `a#pnnext`
  - Page: `a.fl[href*="start="]`

```html
<!-- Pagination (trimmed) -->
<div role="navigation">
  <a id="pnnext" class="LLNLxf" href="/search?...&start=10">Next</a>
</div>
```

- Programmatic URL example (week filter, page 3):
  - `https://www.google.com/search?q=site:jobs.lever.co+front+end&tbs=qdr:w&start=20`

## Lever Posting Page — Open the Apply Form

- Confirm job header + categories present:
  - Title: `.posting-headline h2`
  - Apply button: `a.postings-btn.template-btn-submit[href$="/apply"]`

```html
<div class="posting-page">
  <div class="posting-headline"><h2>Front End Engineer</h2></div>
  <a class="postings-btn template-btn-submit" href="https://jobs.lever.co/xsolla/.../apply">Apply for this job</a>
</div>
```

Heuristic:
- If SERP URL is already `/apply`, skip this step and land directly on the form.

## Lever Apply Form — Stable Detection Heuristics

Landing confirmation:
- Host: `jobs.lever.co`
- Visible header matches job title
- Presence of `form#application-form` and a visible "Submit application" control

Common labels observed across Lever tenants:
- Resume/CV (file upload) — `input#resume-upload-input.application-file-input`
- Full name — `input[data-qa="name-input"]`
- Email — `input[data-qa="email-input"]`
- Phone — `input[data-qa="phone-input"]`
- Current location — `input#location-input.location-input`
- Current company — `input[data-qa="org-input"]`
- Links (LinkedIn/Twitter/GitHub/Portfolio/Other) — inputs named `urls[<Name>]`
- Additional questions — containers under `div.application-question.custom-question`
- EEO/Demographics — `#eeoSurvey_*` section with `select[name^="eeo["]`

Selector strategy (robust across variants):
- Prefer label→control association using the `application-label` → `application-field` pattern.
- When available, use `data-qa` attributes for core identity fields (stable across many tenants).
- Custom questions use dynamic `cards[<id>][fieldN]` names; match by the visible label text within `.application-label .text`, then fill the closest control inside `.application-field`.

```html
<form id="application-form" enctype="multipart/form-data">
  <a class="postings-btn template-btn-utility visible-resume-upload">
    <input id="resume-upload-input" name="resume" type="file" data-qa="input-resume" />
  </a>

  <label><div class="application-label">Full name<span class="required"></span></div>
    <div class="application-field"><input data-qa="name-input" name="name" required></div>
  </label>

  <label><div class="application-label">Email<span class="required"></span></div>
    <div class="application-field"><input data-qa="email-input" name="email" type="email" required></div>
  </label>

  <div class="application-form last-section-apply">
    <button id="btn-submit" data-qa="btn-submit" type="button" class="postings-btn template-btn-submit">Submit application</button>
  </div>
</form>
```

Notes:
- The submit control is often a `button#btn-submit[type="button"]` (JavaScript-driven). In review mode, do NOT click; capture pre‑submit screenshot and exit.
- LinkedIn: an optional `Apply with LinkedIn` button and `IN-widget` iframe may appear; ignore programmatically.
- EEO fields are optional; choose safe defaults (e.g., "Decline to self-identify") or leave blank when allowed.

### hCaptcha Presence (Do not bypass)

- Container: `div#h-captcha.h-captcha` with hidden input `input[name="h-captcha-response"]`.
- Policy: do not attempt to solve/bypass captchas. Treat presence as a submission gate. In review mode, stop before triggering submission.
- Allowlist consideration: loading the widget may reference `newassets.hcaptcha.com`; we will not interact with it.

## Pre‑Submit Summary & Screenshot Cues

- Before submit, extract:
  - Job title and company from the header region
  - Filled values (redact PII in logs)
  - Resume filename/attachment indicator (look for `.resume-upload-success` state)
- Capture the screenshot once all required fields are valid (submit enabled/visible).

## Domain Allowlist (Profiles)

Add the following hosts to `browser.allowed_domains` for Lever runs:
- `jobs.lever.co`
- `*.jobs.lever.co` (company subpaths)
- Optional: `api.lever.co`
- Optional (widget load only, no interaction): `newassets.hcaptcha.com`

## Google SERP Time Filter — Quick Reference

- `qdr:h` = past hour
- `qdr:d` = past day
- `qdr:w` = past week
- `qdr:m` = past month
- `qdr:y` = past year

Example: past day results for React roles
```
https://www.google.com/search?q=site:jobs.lever.co/apply+react+developer&tbs=qdr:d
```

---

Caveats:
- Google markup and A/B experiments change frequently; prefer URL parameters over clicking the `Tools` UI.
- Not all Lever postings expose `/apply` directly in SERP. Be prepared to open the job page and click its in‑page Apply control.
- Some companies add custom required questions; treat unknowns conservatively and surface them in the summary for human review.

## Profile YAML example (defaults)
```yaml
search:
  source: lever-google        # discovery provider
  terms: ["front end"]       # comes from user profile
  location: "remote us"      # comes from user profile
  time_window: d              # h|d|w|m|y (default: d = past 24h)
mode: review                  # stay review-only through Epic 4
browser:
  allowed_domains:
    - jobs.lever.co
    - "*.jobs.lever.co"
    - api.lever.co            # optional
    - newassets.hcaptcha.com  # load-only for widget
```

### Lever Resume Upload — Success/Ready Indicator (paste real snippet)

When Lever finishes parsing the uploaded resume, many tenants expose a visual success indicator (e.g., file chip/attachment row or a status text) and may auto-populate core fields. We will wait for this indicator during ai_autofill before filling remaining fields.

- Placeholder selectors (to be tuned per tenant):
  - `input#resume-upload-input.application-file-input` (upload control)
  - [Paste actual success node selector here]
  - Fallback: small network-idle window + DOM stability check.

Paste the provided HTML snippet here for future tuning:

```html
<div class="application-field">
  <a href="#" class="postings-btn template-btn-utility visible-resume-upload has-file">
    <svg class=" icon icon-paperclip" width="16" height="16" viewBox="0 0 16 16"><path id="Vector" d="M4 3.375C4 1.5125 5.5125 0 7.375 0C9.2375 0 10.75 1.5125 10.75 3.375V10.75C10.75 11.9937 9.74375 13 8.5 13C7.25625 13 6.25 11.9937 6.25 10.75V4.75C6.25 4.33437 6.58437 4 7 4C7.41563 4 7.75 4.33437 7.75 4.75V10.75C7.75 11.1656 8.08437 11.5 8.5 11.5C8.91563 11.5 9.25 11.1656 9.25 10.75V3.375C9.25 2.34063 8.40937 1.5 7.375 1.5C6.34063 1.5 5.5 2.34063 5.5 3.375V11.5C5.5 13.1562 6.84375 14.5 8.5 14.5C10.1562 14.5 11.5 13.1562 11.5 11.5V4.75C11.5 4.33437 11.8344 4 12.25 4C12.6656 4 13 4.33437 13 4.75V11.5C13 13.9844 10.9844 16 8.5 16C6.01562 16 4 13.9844 4 11.5V3.375Z"></path></svg>
    <span class="filename">Michael_Parkin_Senior_Front_End_Developer_Resume_2025.pdf</span>
    <span class="default-label" style="display: none;">ATTACH RESUME/CV</span>
    <input class="application-file-input invisible-resume-upload" data-qa="input-resume" id="resume-upload-input" name="resume" tabindex="-1" type="file">
  </a>
  <span class="resume-upload-failure" style="display: none;"><div class="resume-upload-label">Couldn't auto-read resume.</div></span>
  <span class="resume-upload-working" style="display: none;"><div class="loading-indicator"></div><div class="resume-upload-label">Analyzing resume...</div></span>
  <span class="resume-upload-success" style="display: inline;"><div class="loading-indicator completed"><svg class=" icon icon-check" width="16" height="16" viewBox="0 0 16 16"><path d="M15.6652 3.32222C16.1116 3.75184 16.1116 4.44954 15.6652 4.87916L6.52338 13.6778C6.077 14.1074 5.35208 14.1074 4.9057 13.6778L0.334784 9.27847C-0.111595 8.84885 -0.111595 8.15115 0.334784 7.72153C0.781163 7.29191 1.50608 7.29191 1.95246 7.72153L5.71633 11.3407L14.0511 3.32222C14.4975 2.89259 15.2224 2.89259 15.6688 3.32222H15.6652Z"></path></svg></div><div class="resume-upload-label">Success!</div></span>
</div>
```

Config proposal (site-level defaults):

```yaml
resume:
  success_selectors:
    # Success states (prefer visible success chip/label or completed check icon)
    - "span.resume-upload-success .resume-upload-label"
    - "span.resume-upload-success .loading-indicator.completed"
    # Has-file indicator (secondary confirmation)
    - "a.visible-resume-upload.has-file .filename"
  working_selectors:
    - "span.resume-upload-working .resume-upload-label"
  failure_selectors:
    - "span.resume-upload-failure .resume-upload-label"
  max_wait_seconds: 15
  poll_interval_ms: 300
```
