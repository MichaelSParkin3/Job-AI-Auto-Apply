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

---
