# Source Tree

```
job-ai-auto-apply/                     # Monorepo root for Python automation + TypeScript UI
├── apps/                              # Modular monolith entry points and services
│   ├── browser/                       # Shared browser automation control (Playwright orchestration)
│   ├── cli/                           # Typer CLI orchestrator for run modes & decision engine
│   │   ├── tests/                     # pytest specs for CLI domain modules
│   │   └── *.py                       # Config loader, queue manager, runtime state, redaction helpers
│   ├── preview/                       # FastAPI preview/BFF server serving UI + run control API
│   │   ├── tests/                     # pytest coverage for FastAPI routers and runners
│   │   └── main.py                    # ASGI entrypoint wired into CLI process
│   └── ui/                            # React 18 + Vite + Tailwind SPA for review/approval UX
│       ├── src/
│       │   ├── components/            # shadcn/ui-based widgets & pages (TypeScript + JSX)
│       │   ├── store/                 # Zustand slices for run state + previews
│       │   ├── lib/                   # Client-side utilities (API clients, formatters)
│       │   ├── __tests__/             # Vitest + Testing Library unit specs
│       │   └── setup-tests.ts         # Vitest/RTL configuration shared across specs
│       ├── tests/                     # Playwright end-to-end flows against preview server
│       ├── tailwind.config.ts         # Tailwind design system tokens
│       ├── vite.config.ts             # Vite build tooling for SPA bundling
│       └── tsconfig.json              # TypeScript project configuration for UI app
├── sites/                             # Site-specific automation adapters (Python modules)
│   ├── lever/                         # Lever playbooks: navigation, selectors, summary, tests
│   └── simplyhired/                   # SimplyHired automations: form mappers, selectors, uploads
├── data/                              # Local-only assets referenced at runtime
│   ├── profiles/                      # YAML/JSON persona configs loaded by CLI
│   └── resumes/                       # Resume documents used during submissions
├── config/                            # Global runtime configuration (privacy-preserving defaults)
├── docs/                              # Architecture, PRD, QA, and supporting documentation
├── core/tests/                        # Integration/regression harnesses spanning multiple modules
├── scripts/                           # Operational tooling (screenshot capture, preview serve helpers)
├── history/                           # Append-only execution history (JSONL) maintained by CLI
├── runs/                              # Run artifacts (screenshots, DOM snapshots, audit trails)
├── package.json                       # Root pnpm workspace for Node-based tooling/UI builds
├── pnpm-workspace.yaml                # Declares UI workspace boundaries in monorepo
├── pyproject.toml                     # Python project metadata (Typer CLI, FastAPI services)
├── tsconfig.json                      # Shared TypeScript settings for tooling outside UI app
└── vite.config.ts                     # Root Vite config for static preview assets when applicable
```

The structure keeps Python and TypeScript concerns co-located within a single monorepo while
maintaining clear module boundaries: CLI + preview services share Python packages under `apps/`,
site automations live under `sites/`, and the React SPA remains isolated with its own toolchain.
Shared assets (`data/`, `config/`) and operational artifacts (`history/`, `runs/`) sit at the root,
reinforcing the local-first workflow described in the architecture overview.
