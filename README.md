# Urban Green Planner (working title)

Decision-support tool for urban forestation in Bari. It combines Open Data Puglia datasets (green areas, traffic, air quality, population, industrial emissions) into a per-zone **Forestation Priority Index (IPF)**. It shows priorities on a map, explains every score, and estimates the number of new trees needed.

The final product name will be chosen with the team.

- Idea (Italian): [`urban_green_planner_hackathon.md`](urban_green_planner_hackathon.md)
- Requirements & implementation plan: [`docs/requirements_and_plan.md`](docs/requirements_and_plan.md)
- Methodology (Italian): [`docs/methodology.md`](docs/methodology.md)
- Pipeline output schema: [`docs/artefacts.md`](docs/artefacts.md)
- Phase reviews and handoffs: [`docs/handoff/`](docs/handoff/)
- Demo script (Italian): [`docs/demo_script.md`](docs/demo_script.md)

## Layout

```
config/     per-city configuration (sources + model parameters), extra CA certificates
data/       raw/ (downloaded, gitignored except manifest), manual/ (hand-made, committed), interim/, processed/
pipeline/   offline data pipeline (Python)
backend/    FastAPI app
frontend/   React + TypeScript + Vite app (UI in Italian)
tests/      pytest suite
scripts/    demo launcher
deploy/     committed data snapshot (Docker image, clean-start fallback, tests)
.github/    CI workflows: test, build and publish (GHCR)
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

Downloaded files, sizes and checksums are recorded in `data/raw/manifest.json`. The satellite vegetation input (`sentinel2_ndvi`) is not a plain file: the download step builds a median NDVI composite from the clear Sentinel-2 summer scenes (Microsoft Planetary Computer, no account needed) and caches it as one GeoTIFF; the scenes used are listed in the manifest.

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

## Frontend

```bash
(cd frontend && npm run dev)     # dev server on :5173, proxies /api to the backend on :8000
(cd frontend && npm run build)   # production build into frontend/dist/, then served by the backend at /
```

React + TypeScript + Vite, MapLibre GL (via `react-map-gl`) on CARTO basemaps, Tailwind CSS and Headless UI. The UI is in Italian, and all its texts live in `frontend/src/i18n/it.ts`. The layout is mobile-first: a bottom sheet on phones (< 640 px), a collapsible side panel on tablets, and a fixed side panel on desktop. The light and dark themes follow the device setting and can be toggled from the header. Fonts are bundled, so the only external requests are the basemap tiles.

## Demo

```bash
make demo          # data check → frontend build → backend on :8080 → ngrok (https://green-planner.ngrok.io)
make demo-local    # the same on http://localhost:8080, without ngrok
```

`scripts/demo.sh` uses `data/processed/` if it's built, otherwise it rebuilds it offline from `data/raw/`, and otherwise it falls back to the committed snapshot in `deploy/data/`. It rebuilds the frontend only when a source file is newer than `frontend/dist/`. Ctrl+C stops both ngrok and the backend (whose log goes to `data/interim/demo_uvicorn.log`). The ngrok URL and port can be changed with `DEMO_NGROK_URL` and `DEMO_PORT`.

### HTTPS (optional)

The backend can serve HTTPS with a self-signed certificate, e.g. when it is hosted on a private network (Q55):

```bash
make cert                          # tls/cert.pem + tls/key.pem (gitignored): localhost, this host, its LAN IP
make cert NAMES="192.168.1.50 demo.lan"   # + extra addresses / names (remembered for later runs)
make demo HTTPS=1                  # ngrok → https://127.0.0.1:8080 (ngrok accepts the self-signed certificate)
make demo-local HTTPS=1            # https://localhost:8080
DEMO_HOST=0.0.0.0 make demo-local HTTPS=1  # also reachable from other devices on the network
```

With `HTTPS=1`, both demo targets check the certificate at startup and replace it (new certificate and new key) when it is missing, expires within a day, or doesn't cover the laptop's current LAN address, so moving to another network needs no manual step. Plain HTTP stays the default. Browsers show a warning for a self-signed certificate until it is trusted (import `tls/cert.pem`). The launcher's health checks and the admin CLI verify the certificate against `tls/cert.pem` (no verification is ever disabled), and `./chat` finds the HTTPS server by itself.

### Docker image and CI

The same app also runs as one Docker image (`Dockerfile`: frontend build, then the backend serving it). Its data is the committed snapshot in `deploy/data/` (see [`deploy/README.md`](deploy/README.md)), because `data/processed/` is gitignored:

```bash
make snapshot      # after every `pipeline build`: copy the artefacts into deploy/data/, then commit
make docker-build && make docker-run    # build and run the image locally on http://localhost:8080
```

**CI** (GitHub Actions, Q60), two workflows in `.github/workflows/`:

| Workflow | Runs | Does |
|---|---|---|
| `test.yml` (**Test**) | on every push (any branch), or by hand | ruff check + format check, pytest, frontend lint + build |
| `build.yml` (**Build and publish**) | after a green Test on `main`, or by hand (any branch) | builds the image of the tested commit and pushes it to GHCR (private): `ghcr.io/gennaroandrea/green-planner:<commit SHA>`, plus `:latest` for `main` |

Nothing is deployed automatically. To run a published image elsewhere: `docker login ghcr.io` (a classic GitHub token with `read:packages`), then `docker run -p 8080:8080 ghcr.io/gennaroandrea/green-planner:latest`.

## AI chat ("Chiedi")

A third panel tab, **Chiedi**, answers questions about the project in Italian: the method and its formulas, the decisions, the data, the Bari results and how to use the app (FR-54, Q53, Q56). It uses Claude Haiku 4.5 through the Claude API, with thinking off and streamed answers (`backend/chat.py`). The model reads `docs/methodology.md` and gets the numbers from three read-only tools (ranking, quartiere card, simulator, all at default weights); it declines unrelated questions. After each answer, a check looks for numbers that are neither in the tool results, the methodology or the question, nor the correct result of an operation written in the answer; if it finds any, the answer gets a visible warning (`backend/chat_numbers.py`). The conversation memory (last 10 exchanges) lives in the server process. Answers are rendered as Markdown with `react-markdown` + `remark-gfm` (tables included; raw HTML is never rendered) and LaTeX with KaTeX (`$…$`, `$$…$$`; Italian decimal commas are fixed automatically, and the number check reads LaTeX too), and the chat code is loaded only when the tab is first opened, so the map's first load is unchanged.

The chat runs on the demo laptop only (Q54): copy `.env.example` to `.env` and set `GREEN_PLANNER_ADMIN_SECRET` and `ANTHROPIC_API_KEY`. `make demo` loads `.env`; without both, the tab is hidden.

**Test mode** (for trying the UI without API credit): with `GREEN_PLANNER_CHAT_TEST_MODE=1` in `.env`, questions that start with `/test` get canned answers (`backend/chat_test.py`: six answers that cycle, each after a real tool call, streamed at about the model's pace, number-checked and charged ~$0.006 on the session budget; the sixth has an invented number to show the warning). Other questions still go to the model. Keep it off for the demo.

If the Anthropic account runs out of credit (or the key is rejected), users see "La chat non è disponibile in questo momento", the server log says what to fix, and `./chat status` shows `model: ERROR, Anthropic credit exhausted`.

```bash
uv run --env-file .env python scripts/chat_eval.py   # 19 fixed test questions against the real API (~$0.02 each)
```

### Access codes

The chat is gated by single-use access codes (FR-55, Q54); the map stays public.

```bash
./chat status                                     # chat on/off, model errors, codes, sessions, spending
./chat codes 10 --label giuria                    # until today 23:59, $0.30 each
./chat codes 5 --budget 0.50 --expires "2026-10-01 23:59"
./chat sessions                                   # spending, budget and tokens per session
./chat revoke <session-id>
./chat revoke-all                                 # every session + unused codes (--yes: no prompt)
./chat disable                                    # switch the chat off (enable: back on)
```

`./chat` is a short form of `uv run python -m backend.admin`. It finds the server that `make demo` / `make demo-local` is running by itself (http or https, any port); `--url` (before the command) or `GREEN_PLANNER_URL` point to another one. Codes are shown once and stored only as keyed hashes (`data/interim/chat_auth.sqlite`). A visitor redeems a code once and gets a session cookie. Each session has an API spending budget in USD, set when the codes are created (`--budget`, default $0.30, at most $5): the chat's API usage is priced with the official per-model rates in `backend/chat_pricing.py`, and once a session's spending reaches its budget it can't ask more questions (the last question may overshoot by its own cost).

## Development

```bash
uv run pytest                    # Python tests
uv run ruff check .              # lint
(cd frontend && npm run dev)     # frontend dev server
```
