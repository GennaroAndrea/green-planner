# CLAUDE.md

## Project

**Urban Green Planner**: a project for the Bari Hackathon (1 October 2026). It is a GIS decision-support dashboard. It combines Open Data Puglia datasets (green areas, traffic, air quality, population, industrial sites) into a per-cell **Forestation Priority Index (IPF, Indice di Priorità di Forestazione)**. It shows priority zones on a map, explains why each zone scored as it did, and estimates how many new trees each zone needs. Bari is the first case study.

- Original idea and dataset notes (Italian): `urban_green_planner_hackathon.md`
- Requirements analysis and implementation plan: `docs/requirements_and_plan.md`

## Commands

uv is installed in `~/.local/bin`. If `uv` isn't found, prefix the command with `PATH=$HOME/.local/bin:$PATH`.

```bash
uv sync                                   # Python env (pipeline + backend)
uv run python -m pipeline download        # raw data into data/raw/ (+ manifest.json); --only <source>, --force
uv run pytest                             # tests
uv run ruff check . && uv run ruff format .
uv run uvicorn backend.main:app --reload  # backend on :8000 (serves frontend/dist if built)
cd frontend && npm run dev                # frontend dev server (proxies /api to :8000)
cd frontend && npm run build && npm run lint
```

- City config (data sources + all model parameters): `config/bari.yaml`.
- `data/raw/` is gitignored (except `manifest.json`). `data/manual/` holds hand-transcribed data and is committed; document the source of each file in its README.
- Some PA hosts don't send their intermediate TLS certificate. Add it to `config/certs/intermediates.pem`. Never disable verification.

## General rules

### Language
- **We talk in English.** All conversation with the user is in English.
- **Only the UI is in Italian.** This covers user-facing text in the app: labels, buttons, tooltips, map legends, explanations shown to end users.
- **Everything else is in English.** This covers source code, identifiers, code comments, commit messages, documentation, config files, logs and error messages meant for developers.
- **Files already written in Italian stay in Italian** (e.g. `urban_green_planner_hackathon.md`). Don't translate them unless asked.

### Workflow
- The user is currently the **only developer**. The user will say when the team joins.
- **Never run git commands except `git status` and `git diff`** (no init, add, commit, branch, checkout, stash, push, etc.). The user manages the repository.
- When the team joins, the user will create **per-person git branches with clear ownership** (who does what), so people don't interfere with each other. See `docs/requirements_and_plan.md` §8.1.
- Design decisions are recorded in `docs/requirements_and_plan.md` §10.0 (decision log). Follow them, and don't reopen them without asking.
- The product name is **not chosen yet** (it will be decided with the team). Use a neutral placeholder in the UI until then.

### Ask, don't guess
- If you have a doubt about anything (requirements, data semantics, technical choices, scope, naming), **ask the user**. Don't guess.
- If an assumption can't be avoided, state it explicitly and get it confirmed.
