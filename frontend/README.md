# PypeDeid — Playground UI

**Admin / operator** SPA. Requires an **admin API key** when the backend has auth enabled. See [`frontend-production/`](../frontend-production/) for the inference-scoped consumer UI.

## Setup

```bash
npm install
npm run dev          # http://localhost:3000 (proxies /api → localhost:8000)
npm run build        # production build to dist/
npm run lint         # ESLint
```

Requires the API server running at `localhost:8000`:

```bash
pypedeid serve
```

Set `VITE_API_KEY` (admin key) and optionally `VITE_API_BASE_URL` in `.env.local`.

## Views

| Route | Component | Purpose |
|-------|-----------|---------|
| `/pipelines` | PipelinesCatalogView | Browse saved pipelines: composition, output label space |
| `/create` | PipelineBuilder | Visual drag-and-drop pipeline composer with config forms |
| `/inference` | InferenceView | Paste text, see spans + redacted output + pipe-step trace |
| `/production` | ProductionView | Dataset-centric assisted NER workspace |
| `/evaluate` | EvaluateView | Run evals, metrics/confusion matrix/comparison |
| `/datasets` | DatasetsView | Register, browse, compose, transform, generate datasets |
| `/dictionaries` | DictionaryManager | Upload/manage whitelist & blacklist term lists |
| `/deploy` | DeployView | Configure inference modes, pipeline allowlist |
| `/audit` | AuditView | Browse audit trail with stats, filters, detail panel |

## Tech stack

- React 19 + TypeScript
- Vite 8 (build + dev server)
- Tailwind CSS v4
- @xyflow/react (pipeline canvas)
- TanStack Query (data fetching)
- zustand (client state)
- @rjsf/core (JSON Schema config forms)
- recharts (eval charts)
- Lucide React (icons)

See [docs/ui.md](../docs/ui.md) for detailed documentation of each view.
