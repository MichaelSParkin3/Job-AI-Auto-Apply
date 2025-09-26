# Tech Stack

## Technology Stack Table
| Category | Technology | Version | Purpose | Rationale |
|---|---|---|---|---|
| Frontend Language | TypeScript | 5.6 | UI type safety | Mature ecosystem; integrates with Vite and shadcn/ui |
| Frontend Framework | React | 18.2 | Preview UI | Stable, well-documented, minimal runtime needs |
| UI Component Library | shadcn/ui + Tailwind CSS | shadcn (template) + 3.4 | Accessible, consistent UI | Fast to assemble, accessible components |
| State Management | Zustand | 4.x | Lightweight UI state | Simple store, minimal boilerplate |
| Backend Language | Python | 3.11 | CLI + server | Matches PRD; great ecosystem |
| Backend Framework | FastAPI | 0.115.x | Preview server REST + static | Async, type hints, easy testing |
| API Style | REST (JSON) | n/a | UI ↔ Preview control | Simple, predictable, debuggable |
| Database | None (file-first) | n/a | Artifacts/history storage | Meets privacy constraints; SQLite optional later |
| Cache | In‑process | n/a | Small ephemeral caches | Avoids external services |
| File Storage | Windows FS | n/a | Artifacts, logs | Local‑only privacy |
| Authentication | API key (.env.local) | n/a | OpenRouter access | No user auth needed locally |
| Frontend Testing | Vitest + RTL + axe | latest | Unit/a11y tests | Fast local CI, a11y coverage |
| Backend Testing | pytest | 8.x | Unit/integration | Mature, fixtures, Windows friendly |
| E2E Testing | Playwright | 1.46+ | UI/E2E (optional) | Same engine as automation; visual baseline optional |
| Build Tool | Vite | 5.x | Frontend dev/build | Fast dev server, simple static output |
| Bundler | esbuild (via Vite) | 0.21+ | Fast builds | Defaults suffice |
| IaC Tool | None | n/a | Local‑only | No infra to codify |
| CI/CD | GitHub Actions | hosted | Test/build only | No PII; gates quality |
| Monitoring | Local logs + metrics | n/a | Observability | No external telemetry |
| Logging | JSON logs | n/a | Debug + audit | PII redaction rules |
| CSS Framework | Tailwind CSS | 3.4 | Utility CSS | Pairs with shadcn/ui |

---
