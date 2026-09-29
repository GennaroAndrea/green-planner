# Phase 2 (backend): review and handoff

- **Date**: 2026-09-29
- **Phase**: 2, backend (plan §8, items 2.1–2.5)
- **Status**: done. Q30–Q33 were added during this phase.
- **Next phase**: 3, frontend (Italian UI)

---

## Part A: Review

### A.1 What was built

| Plan item | Result | Where |
|---|---|---|
| 2.1 Load artefacts at startup | `Store` loads `cells_250/500.parquet`, `zones.parquet`, `metadata.json` and the 4 layer GeoJSONs in the FastAPI lifespan. It checks the required columns and gives a clear error if `pipeline build` hasn't run. Data dir: `data/processed/`, override with `GREEN_PLANNER_DATA_DIR`. | `backend/store.py` |
| 2.2 Endpoints + Pydantic models | health, metadata, cells/zones GeoJSON, cell/zone detail, layers, ranking, sensitivity (table in plan §7.2) | `backend/main.py`, `backend/schemas.py` |
| 2.3 Custom weights + sensitivity | `?weights=key:pp,...` parsing and validation (Q30). Scenarios are recomputed with `pipeline.model` / `pipeline.sensitivity` and cached (LRU, 32). The default weights read the precomputed columns. On-request sensitivity handles zero weights (Q31). | `backend/store.py`, `pipeline/sensitivity.py` (`sample_weights`) |
| 2.4 Static serving + CORS | `frontend/dist` is mounted at `/` after the API. CORS allows the Vite dev origin (GET only). GZip is on for responses ≥ 1 kB. | `backend/main.py` |
| 2.5 Tests | 26 API tests on a synthetic fixture (Q32), 1 smoke test on the real artefacts (skipped if they aren't built), 4 new sensitivity tests for the zero-weight rule | `tests/test_backend.py`, `tests/test_sensitivity.py` |
| (docs) | API table (plan §7.2), decisions Q30–Q33, methodology §7/§12/§15/§16 (in Italian), README backend section | |

### A.2 Results (verified on the real artefacts)

- **Exactness**: recomputing each level with the default weights through the custom-weight path reproduces every precomputed column exactly: IPF (within 1e-4), class, rank, `rank_p5`, `rank_p95`, `top_n_freq`, `class_stability`, `robust`, and the city-level summaries (e.g. zones Spearman 0.9822, robust share 0.875). This is also a fixture test.
- **Timings** (this laptop):
  - startup about 0.5 s;
  - `/api/cells` over HTTP (uvicorn, gzip) is 190 KB (1.2 MB uncompressed) in 0.12 s;
  - a custom-weight 250 m grid, including its 1,000-run sensitivity check, takes 0.22 s over HTTP;
  - zone detail/ranking take a few ms.
  - ngrok isn't measured yet (Phase 4).
- **Example**: with equal weights (25/25/25/25), the zone top 5 is Madonnella, Murat, San Nicola, San Pasquale, Libertà, and Palese – Macchie and Loseto stay the only "sensitive" zones.
- `uv run pytest`: 57 passed (27 before this phase). `ruff check` and `ruff format --check` are clean.

### A.3 Deviations from the plan and new decisions

- **Q30**: a non-zero weight for an inactive indicator (`industry`) is rejected with 400. `industry:0` is accepted.
- **Q31**: weights go from 0 to 100. A 0 weight stays fixed at 0 in the Monte Carlo, and only the non-zero weights are perturbed, with the spread calibrated on them. If there's nothing to perturb, sensitivity is "not applicable" (`applicable: false`, per-item sensitivity fields null) but the ranking is still returned. This changed `pipeline.sensitivity.sample_weights`. With all weights non-zero (the defaults), it draws exactly the same samples as before (tested).
- **Q32**: synthetic fixture for the API tests, plus a real-artefact smoke test.
- **Q33**: the Phase 1 model issues (handoff 1, A.5 #1–#2) are deferred to before the demo.
- **Technical choices** (not method; stated here so they can be changed):
  - The weight sum tolerance is ±0.1 pp, then rescaled to 1.
  - Weights within 1e-4 of the defaults count as "default" and use the artefacts.
  - Map GeoJSON coordinates are rounded to 6 decimals and properties to 3.
  - Validation errors are 400. Unknown grid, cell, zone or layer is 404.
- **API vs the §7.2 sketch**:
  - Layers are `green`, `traffic`, `air`, `industry` (the sketch had no `industry`).
  - The architecture diagram's `/api/ipf` (values only) was **not** built: `/api/cells?weights=` returns the whole GeoJSON (190 KB gzipped). Add a values-only endpoint only if refetching turns out to be slow over ngrok.
  - Every detail/ranking/sensitivity response carries `weights` (effective, sum 1) and `is_default`.

### A.4 Process notes

- All four open questions from handoff 1 (B.5) were asked before any code was written. The zero-weight edge case was found by testing `sample_weights` with extreme weights (`[1,0,0,0]` → `ValueError: alpha < 0`; `[0.5,0.5,0,0]` → sd 7 pp instead of 5) and asked as a question too.
- A small self-inflicted indentation bug and two dtype mismatches (`Float64` vs `float64` for sensitivity columns) were caught by ruff and the fixture test.

### A.5 Known issues and open points

1. **Default weights aren't whole numbers in pp**: 22.2 / 33.3 / 22.2 / 22.2. Integer sliders can't show them exactly, and they sum to 99 when rounded. The frontend should omit `weights` for the default scenario, and send its own values once the user moves a slider. **Ask the user**: slider step (1 pp or 0.1 pp?) and how to display the defaults.
2. **Tree parameters**: methodology §10 says the plantable fraction is "mostrata e modificabile nell'app", but no FR or endpoint covers changing tree parameters. Only weights are recomputable. **Ask the user** whether this is wanted (it would be a new query parameter on the detail/ranking/zones endpoints).
3. **Phase 1 model issues** (green-deficit saturation, artificial-only cells; handoff 1 A.5 #1–#2) are still open (Q33): raise them before the demo.
4. The first request for a new custom scenario computes it. Identical concurrent requests may compute it twice (harmless). The cache holds 32 scenarios per store (worst case about 64 MB).
5. `TestClient` emits a Starlette/httpx deprecation warning (harmless).

---

## Part B: Handoff for the next agent (Phase 3, frontend)

### B.0 The UI prototype (start here)
The user made a UI prototype in **`ui_prototype/`**. It is the reference for **layout, screens and features** of the real UI. It is **not** the reference for the stack: build with the decided stack (Q13: React + TS + Vite, MapLibre via react-map-gl, Tailwind, Recharts, npm) and follow the project rules (CLAUDE.md: Italian UI only, English code; NFR-07 disclaimers; FR-50 / NFR-09 mobile-first).

**Rule from the user: anything the prototype shows that the backend doesn't serve must be added to the backend too.** So the first step of Phase 3 is a gap analysis:
1. Go through every screen and element of the prototype (map, legend, panels, sliders, ranking, modals, filters, exports, …) and list the data each one needs.
2. Check each item against the API as built (plan §7.2, `/docs`, B.3 below). Mark it as served, derivable client-side (e.g. legend counts), or **missing**.
3. Show the gap list to the user. For each missing item that is **display or plumbing only** (data already in the artefacts), add it to the backend. For each item that needs a **new method, data or model choice** (e.g. editable tree parameters, presets, new indicators), ask the user first with the options explained (CLAUDE.md, "Ask, don't guess"), and keep `docs/methodology.md` in sync if the model changes.
4. Add backend tests for every new endpoint or field (synthetic fixture in `tests/test_backend.py`), and update plan §7.2 and `docs/artefacts.md` if the artefacts change.
5. Where the prototype conflicts with a decision in the decision log (§10.0) or a requirement, point it out to the user. Don't silently follow either side.

The open questions in B.5 may already be answered by the prototype: check it before asking.

### B.1 Read first
1. `ui_prototype/` (see B.0).
2. `CLAUDE.md`: rules (Italian UI only, git, ask-don't-guess, handoffs).
3. `docs/requirements_and_plan.md`: §4.3 (FR-40…51), §5 (NFR-04, NFR-07, NFR-09), §7.2 (**the API as built**), §8 Phase 3, §10.0.
4. `docs/methodology.md` (Italian): source text for the "Metodologia e fonti" modal and the explanations (§11).
5. The live API docs: `uv run uvicorn backend.main:app --reload`, then `http://localhost:8000/docs`.

### B.2 Current state
- The backend is complete. Run `uv run python -m pipeline build` once if `data/processed/` is missing, then `uv run uvicorn backend.main:app --reload`. `cd frontend && npm run dev` proxies `/api` to :8000.
- The frontend is still the Vite + React + TS + Tailwind skeleton. MapLibre, react-map-gl and Recharts aren't installed yet (stack Q13).

### B.3 What the API gives the UI (keys + numbers only; all Italian text lives in the frontend)
- **Map**: `/api/cells?grid=250|500` (`cell_id`, `zone_id`, `analysed`, `ipf`, `ipf_class` 0–4, `rank`, `robust`) and `/api/zones` (`zone_id`, `name`, `analysed`, `ipf`, `ipf_class`, `rank`, `robust`, `trees_new`). Class 0 / `analysed: false` means not analysed (grey). Torre a Mare is `analysed: false` (disclaimer `population_coverage`).
- **Detail panel** (FR-42/43/51): `/api/zones/{id}` and `/api/cells/{cell_id}` return:
  - `indicators[]` (raw value, score 0–100, weight, contribution);
  - `top_drivers[]` (3, sorted);
  - `trees`;
  - `sensitivity` (`rank_p5`, `rank_p95`, `robust`, `applicable`);
  - `stats`;
  - `class_key` (`bassa`/`media`/`medio_alta`/`alta`);
  - `ranked_items` (for "3° su 16").
- **Weights** (FR-45): `?weights=pollution:25,green_deficit:35,traffic:20,population:20` on every endpoint except layers/metadata. A 400 carries `detail` (an English message for developers: map it to an Italian UI message, don't show it).
- **Ranking** (FR-46): `/api/ranking?level=zone|cell&limit=`. **Sensitivity** (FR-27/51, "Verifica robustezza" button, methodology modal): `/api/sensitivity?level=…` (`summary.spearman_mean`, `top_n_overlap_mean`, `robust_share`, `one_at_a_time[]`).
- **Metadata** (FR-24/47): `weights.effective` (defaults), `classes.keys`, `disclaimers` (keys), `sources`, `inputs`, `grids.*.class_edges`, `layers`.
- **Layers** (FR-44): `/api/layers/green|traffic|air|industry`. Their properties are in `docs/artefacts.md`. `industry` is context only: its wording must express proximity, never causality (disclaimer `no_causality`).

### B.4 Implementation notes
- Use `promoteId: "cell_id"` / `"zone_id"` in MapLibre sources: features have no top-level `id`.
- Refetching `/api/cells?weights=` on slider release (debounced), not on every tick, keeps it at about 0.2 s per change locally.
- Legend counts per class (FR-41) can be computed client-side from the GeoJSON.
- `robust: null` with `sensitivity.applicable: false` means "not applicable" (e.g. only one non-zero weight). Show a neutral state, not "sensibile".

### B.5 Open questions to ask the user before or while building Phase 3
Check `ui_prototype/` first: it may already answer some of these. #3 is not UI-only (it needs a backend parameter and a methodology update).
1. Product name (Q14): still a placeholder?
2. Weight sliders: step 1 pp or 0.1 pp, and how to show the 22.2/33.3 defaults (A.5 #1).
3. Should tree parameters (plantable fraction) be editable in the UI, as methodology §10 says (A.5 #2)?
4. Is the default map view the zones or the 250 m grid?

### B.6 Pitfalls
- Never run git commands other than `git status` / `git diff`.
- Italian only in the UI. Code, comments and commits in English.
- Disclaimers always visible (NFR-07). Talk about **relative** priority (classes are quartiles).
- Mobile first (FR-50, NFR-09): build the layout shell before the components.
- If the model changes, keep `docs/methodology.md` in sync, in Italian.
