# Unified Project Structure

```text
job-ai-auto-apply/
├─ apps/
│  ├─ cli/                    # Typer CLI (Python)
│  ├─ preview/                # FastAPI BFF + static serving
│  └─ ui/                     # React + Vite + Tailwind + shadcn/ui
├─ packages/
│  └─ shared/                 # Shared TS types for UI
├─ sites/
│  └─ simplyhired/            # Playbooks, selectors, widgets
├─ runs/                      # Per-run artifact directories (created at runtime)
├─ history/
│  └─ history.jsonl           # Append-only run summaries
├─ config/                    # config.yaml (generated)
├─ data/
│  └─ profiles/               # per-profile YAML + resume PDFs
├─ .local/                    # browser sessions per profile
├─ docs/
│  ├─ prd.md
│  └─ architecture.md
├─ package.json               # pnpm workspaces for apps/ui + packages
├─ pnpm-workspace.yaml
├─ pyproject.toml             # Python project config
└─ .env.local                 # OpenRouter API key (local only)
```

---
