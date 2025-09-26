# Deployment Architecture

## Deployment Strategy
- Frontend Deployment:
  - Platform: Local static assets served by FastAPI
  - Build Command: `pnpm --filter @app/ui build`
  - Output Directory: `apps/ui/dist`
  - CDN/Edge: N/A (local)

- Backend Deployment:
  - Platform: Local Python runtime (pipx/venv) or packaged executable
  - Build Command: `pip install -e .` (dev) / PyInstaller for single‑exe (optional)
  - Deployment Method: Zip distribution or installer; no network services created

## CI/CD Pipeline (GitHub Actions excerpt)
```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -e .[dev]
      - run: pytest -q
      - uses: actions/setup-node@v4
        with: { node-version: '22' }
      - run: cd apps/ui && pnpm install && pnpm build && pnpm test
```

## Environments
| Environment | Frontend URL | Backend URL | Purpose |
|---|---|---|---|
| Development | http://localhost:4950/ui | http://localhost:4950 | Local development |
| Staging | N/A | N/A | Not applicable (local-only) |
| Production | N/A | N/A | Distributed locally |

---
