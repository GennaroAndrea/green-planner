# Urban Green Planner (working title)

Decision-support tool for urban forestation in Bari. It combines Open Data Puglia datasets (green areas, traffic, air quality, population, industrial emissions) into a per-zone **Forestation Priority Index (IPF)**. It shows priorities on a map, explains every score, and estimates the number of new trees needed.

The final product name will be chosen with the team.

- Idea (Italian): [`urban_green_planner_hackathon.md`](urban_green_planner_hackathon.md)
- Requirements & implementation plan: [`docs/requirements_and_plan.md`](docs/requirements_and_plan.md)
- Methodology (Italian): [`docs/methodology.md`](docs/methodology.md)
- Pipeline output schema: [`docs/artefacts.md`](docs/artefacts.md)
- Phase reviews and handoffs: [`docs/handoff/`](docs/handoff/)

## Layout

```
config/     per-city configuration (sources + model parameters), extra CA certificates
data/       raw/ (downloaded, gitignored except manifest), manual/ (hand-made, committed), interim/, processed/
pipeline/   offline data pipeline (Python)
backend/    FastAPI app
frontend/   React + TypeScript + Vite app (UI in Italian)
tests/      pytest suite
```

## Setup

Requirements: [uv](https://docs.astral.sh/uv/), Node.js ≥ 20 with npm.

```bash
uv sync                          # Python environment
(cd frontend && npm install)     # frontend dependencies
```

## Data

```bash
uv run python -m pipeline download              # all sources into data/raw/
uv run python -m pipeline download --only sit   # a single source
uv run python -m pipeline download --force      # re-download everything
```

Downloaded files, sizes and checksums are recorded in `data/raw/manifest.json`.

```bash
uv run python -m pipeline build                 # data/raw/ → data/processed/ (about 30 s)
```

The artefact schema (grid cells, zones, context layers, metadata) is documented in [`docs/artefacts.md`](docs/artefacts.md).

Some public-administration hosts (`sit.egov.ba.it`, `www.arpa.puglia.it`) don't send their intermediate TLS certificate. The needed intermediates are in `config/certs/intermediates.pem`, and certificate verification stays enabled.

## Backend

```bash
uv run uvicorn backend.main:app --reload         # API on :8000 (+ frontend/dist at / if built)
```

The backend loads `data/processed/` at startup (override with `GREEN_PLANNER_DATA_DIR`), so run `pipeline build` first. Interactive API docs are at `http://localhost:8000/docs`, and the endpoint list is in [`docs/requirements_and_plan.md`](docs/requirements_and_plan.md) §7.2. Custom weights are passed as `?weights=pollution:25,green_deficit:35,traffic:20,population:20` (one value per active indicator, each 0–100, normalised on their total).

## Development

```bash
uv run pytest                    # Python tests
uv run ruff check .              # lint
(cd frontend && npm run dev)     # frontend dev server
```
