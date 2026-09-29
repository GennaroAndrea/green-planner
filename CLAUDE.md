# CLAUDE.md

## Project

**Urban Green Planner**: a project for the Bari Hackathon (1 October 2026). It is a GIS decision-support dashboard. It combines Open Data Puglia datasets (green areas, traffic, air quality, population, industrial sites) into a per-cell **Forestation Priority Index (IPF, Indice di Priorità di Forestazione)**. It shows priority zones on a map, explains why each zone scored as it did, and estimates how many new trees each zone needs. Bari is the first case study.

Documentation (read the relevant ones before starting a task):
- `urban_green_planner_hackathon.md`: original idea and dataset notes (Italian).
- `docs/requirements_and_plan.md`: requirements, implementation plan (phases), decision log (§10.0).
- `docs/methodology.md`: **the model methodology (Italian)**, i.e. how the IPF is built and why each choice was made. The single source of truth for the model.
- `docs/artefacts.md`: schema of the pipeline outputs in `data/processed/` (what the backend loads).
- `docs/handoff/phase_<N>.md`: review + handoff written at the end of each phase. **Start from the latest one.**
- `data/manual/README.md`: sources of the hand-transcribed data.
- `docs/demo_script.md`: the demo script (Italian, Q52). `deploy/README.md`: the committed data snapshot for the Render deploy (Q51).

## Commands

uv is installed in `~/.local/bin`. If `uv` isn't found, prefix the command with `PATH=$HOME/.local/bin:$PATH`.

```bash
uv sync                                   # Python env (pipeline + backend)
uv run python -m pipeline download        # raw data into data/raw/ (+ manifest.json); --only <source>, --force
uv run python -m pipeline build           # data/raw/ → data/processed/ (schema: docs/artefacts.md)
uv run pytest                             # tests
uv run ruff check . && uv run ruff format .
uv run uvicorn backend.main:app --reload  # backend on :8000 (serves frontend/dist if built)
cd frontend && npm run dev                # frontend dev server (proxies /api to :8000)
cd frontend && npm run build && npm run lint
make demo                                 # demo: build + backend on :8080 + ngrok (make demo-local: no ngrok)
make snapshot                             # after `pipeline build`: refresh deploy/data/ (Render deploy)
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
- **Exception: `docs/methodology.md` is written and maintained in Italian.** Every update to it is in Italian too.

### Workflow
- The user is currently the **only developer**. The user will say when the team joins.
- **Never run git commands except `git status` and `git diff`** (no init, add, commit, branch, checkout, stash, push, etc.). The user manages the repository.
- When the team joins, the user will create **per-person git branches with clear ownership** (who does what), so people don't interfere with each other. See `docs/requirements_and_plan.md` §8.1.
- Design decisions are recorded in `docs/requirements_and_plan.md` §10.0 (decision log). Follow them, and don't reopen them without asking.
- The product name is **not chosen yet** (it will be decided with the team). Use a neutral placeholder in the UI until then.
- **Keep `docs/methodology.md` in sync with the model.** Any change to `pipeline/` logic or to model parameters in `config/bari.yaml` updates the methodology (in Italian) in the same piece of work, including its change log (§16).

### Phase review and handoff
At the end of each phase of the plan (`docs/requirements_and_plan.md` §8), and before starting the next one, write `docs/handoff/phase_<N>.md` (in English) with two parts:
- **Review**: what was built (per plan item, with file locations), results and how they were verified, deviations from the plan and new decisions (with their decision-log IDs), process issues and lessons learned, and known issues / open points.
- **Handoff for the next agent**: what to read first, current state (how to rebuild/run), what to reuse, implementation notes for the next phase, open questions to ask the user, pitfalls.

Also update the phase status in the plan. Only state numbers you have verified, not numbers from memory. Use `docs/handoff/phase_1.md` as the template.

### Ask, don't guess
- If you have a doubt about anything (requirements, data semantics, technical choices, scope, naming), **ask the user**. Don't guess.
- If an assumption can't be avoided, state it explicitly and get it confirmed.
- Ask **before** implementing a method or data choice, not afterwards. Explain each question in plain language (what it is, the options, the trade-offs). Back any claim about data quality with concrete values from the data.
