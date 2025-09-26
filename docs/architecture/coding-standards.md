# Coding Standards

## Critical Fullstack Rules
- Type Sharing: TS types in `packages/shared`; Python pydantic models in backend — keep contracts aligned.
- API Calls: UI must call only Preview BFF endpoints; no direct filesystem access.
- Env Vars: Access via config objects; never use `process.env` directly in components; backend reads `.env.local` once.
- Error Handling: Use standard `ApiError` shape across stack; no throw strings.
- State Updates: Use Zustand immutable updates; no direct mutation.
- Guardrails: Browser automation restricted to `*.simplyhired.com`; one tab; headful only.

## Naming Conventions
| Element | Frontend | Backend | Example |
|---|---|---|---|
| Components | PascalCase | - | `PreviewCard.tsx` |
| Hooks | camelCase with `use` | - | `usePreview.ts` |
| API Routes | - | kebab-case | `/api/run-preview` (or RESTful `/api/run/preview`) |
| Files/Modules | kebab-case | snake_case | `artifact-store.ts`, `file_store.py` |

---
