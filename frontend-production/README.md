# PypeDeid — Production UI

**Inference-scoped** SPA for reviewers and consumers. Uses an **inference API key** — cannot create pipelines, modify datasets, or write deploy config. The Playground UI (`frontend/`) is the admin counterpart.

## Setup

```bash
npm install
npm run dev          # http://localhost:3001
npm run build        # production build to dist/
npm run lint         # ESLint
```

Requires the API server running at `localhost:8000`:

```bash
pypedeid serve
```

Create `.env.local`:

```env
VITE_API_BASE_URL=http://localhost:8000   # omit when using npm run dev (dev server proxies)
VITE_API_KEY=your-inference-key-here      # omit when API auth is disabled
```

## What this UI can access (inference scope)

| Route | Access |
|-------|--------|
| `POST /process/*` | Run any pipeline allowed by the deploy allowlist |
| `GET /deploy/health` | Mode list + per-mode availability |
| `GET /audit/logs`, `/audit/logs/{id}`, `/audit/stats` | Read-only audit |

Everything else requires an admin key — use the Playground UI for pipeline authoring, evaluation, dataset management, and deploy configuration.

## Key features

- **Batch NER workspace** — load a corpus, detect spans using a **deploy mode** (from `data/modes.json`: seeded aliases `fast` → `clinical-fast` (default), `presidio`, `transformer`, `transformer_presidio`), then review and resolve per document
- **Virtualized file list** — `@tanstack/react-virtual` for smooth scrolling on large corpora (>200 files)
- **Keyboard shortcuts** (active when workbench is focused and no text input is selected):
  - `↑` / `↓` — previous / next file
  - `J` / `K` — next / previous unresolved file
  - `N` — next file with a detection error
  - `R` — toggle resolved on the current file
  - `?` — cheat-sheet modal
- **Surrogate preview** — `Preview: surrogate` mode shows fake-data substitutions before export

## Tech stack

- React 19 + TypeScript
- Vite (build + dev server)
- Tailwind CSS
- TanStack Query (data fetching)
- @tanstack/react-virtual (virtualized lists)
- Lucide React (icons)

See [docs/ui.md](../docs/ui.md) for the full two-app architecture overview.
