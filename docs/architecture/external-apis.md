# External APIs

## OpenRouter API
- **Purpose:** LLM actions for Browser‑Use when needed
- **Documentation:** https://openrouter.ai
- **Base URL(s):** https://openrouter.ai/api/v1
- **Authentication:** API key from `.env.local`
- **Rate Limits:** Subject to provider; keep low default concurrency

**Key Endpoints Used:**
- POST `/chat/completions` (or provider‑specific routes via OpenRouter)

**Integration Notes:**
- Redact PII in prompts/logging; retry/backoff; allow per‑profile model override.

If no external APIs are configured, the system operates with deterministic Playwright fallbacks only.

---
