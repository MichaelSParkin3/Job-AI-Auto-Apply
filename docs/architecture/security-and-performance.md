# Security and Performance

## Security Requirements
**Frontend Security**
- CSP: default-src 'self'; img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'
- XSS: sanitize any dynamic HTML views; no untrusted HTML rendering in MVP
- Secure Storage: Avoid localStorage for secrets; none needed for MVP

**Backend Security**
- Input Validation: pydantic models for all API routes
- Rate Limiting: Not required (local); guard against rapid repeat actions
- CORS: Same‑origin only
- AI Mode Opt-In: Auto review, AI auto fill, and auto submit require profile-level consent; CLI refuses to start AI modes unless `profiles/<id>.yaml` sets `automation.allow_auto=true`.
- Handoff Snapshot Redaction: Saved form state stores hashed values + widget metadata only; raw answers never persist outside Browser-Use memory.
- Prompt Redaction: Store AI prompts/responses encrypted-at-rest (local key) with hashes in logs; redact JD snippets beyond 500 characters.

### AI Answer Governance
- AnswerOrchestrator strips PII before drafting, enforces profile confidence thresholds, logs hashed value lengths only, and retries OpenRouter at most twice before falling back to deterministic answers.
- Reviewer approvals and profile saves record provenance metadata so contaminated answers can be rolled back.
- Telemetry dashboards monitor drafted/approved/rejected counts; alert when rejection rate exceeds policy thresholds.

**Authentication Security**
- OpenRouter: Key from `.env.local`; never persisted in artifacts
- Logs: PII redaction in `actions.log`; only `run.json` stores PII

## Performance Optimization
**Frontend**
- Bundle target ≤ 200KB gzipped for MVP
- Loading: single route, static assets; prefetch UI
- Caching: HTTP cache headers for static files

**Backend**
- Response Time Target: Preview API ≤ 50ms p50
- Database Optimization: N/A (file I/O); minimize sync blocking
- Caching: In‑process memo for small lookups
- Decision Engine SLA: AI decisions should complete within 8s p95; queue watchdog escalates items exceeding 30s without response. Auto fill attempts should either submit or emit a handoff within 15s of final field entry to avoid session expiry.
- Answer Draft SLA: Orchestrator requests should resolve within 6s p95 (including retries); fallback path must complete within 7s overall to keep Browser-Use flows responsive. Confidence calculations and artifact writes must add <150ms per field.

---
