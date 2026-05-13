# Documentation index

PypeDeid is a **deployable de-identification service** — a self-hosted FastAPI app, packaged via Docker, that operators run inside their own trust boundary. The deployment-track docs ([deployment.md](deployment.md), [docker-quickstart.md](docker-quickstart.md), [configuration.md](configuration.md)) cover production setup; the rest describe the feature surface that service exposes.

| Document | Contents |
|----------|----------|
| [../README.md](../README.md) | Repo quick start, **CLI profiles vs `data/pipelines` vs `modes.json`**, layout, API table |
| [configuration.md](configuration.md) | Environment variables, auth scopes, CORS, body limits, `.env` resolution |
| [api.md](api.md) | HTTP API reference (paths, auth notes) |
| [deployment.md](deployment.md) | Single-API production layout, Docker, volumes, security |
| [docker-quickstart.md](docker-quickstart.md) | Build, env vars, volume mounts, and pointing a frontend at the API |
| [pipes-and-pipelines.md](pipes-and-pipelines.md) | Pipe types, composition, registry |
| [models.md](models.md) | Filesystem model registry (`models/{framework}/{name}/`) |
| [evaluation.md](evaluation.md) | Metrics, matching modes, eval API |
| [data-ingestion.md](data-ingestion.md) | Dataset formats, registration, transforms |
| [ui.md](ui.md) | Both frontend apps: Playground UI (admin, `frontend/`) and Production UI (inference, `frontend-production/`) |
| [synthesis.md](synthesis.md) | LLM note synthesis |
| [neuroner-setup.md](neuroner-setup.md) | NeuroNER Docker sidecar |
| [transforms-and-composition.md](transforms-and-composition.md) | Dataset transforms |

**Project narrative:** [../PROJECT_OVERVIEW.md](../PROJECT_OVERVIEW.md) (architecture and pipe system).
