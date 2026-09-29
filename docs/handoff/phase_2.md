# Phase 2 (backend): review and handoff

- **Date**: 2026-09-29
- **Phase**: 2, backend (plan §8, items 2.1–2.5)
- **Status**: done. Q30–Q33 were added during this phase. Then the prototype gap analysis (plan 3.0) was done with its backend additions, and Q34–Q44 were decided (A.6).
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

1. ~~Default weights aren't whole numbers in pp~~ **Solved by Q36**: weights are now normalised on their total, so the sliders can start from `metadata.weights.configured_pp` of the active indicators (20/30/20/20). Sending those counts as the default scenario (`is_default: true`).
2. ~~Tree parameters editable?~~ **Decided (Q43)**: not editable, shown read-only in the methodology modal; methodology §10 fixed.
3. **Phase 1 model issues** (green-deficit saturation, artificial-only cells; handoff 1 A.5 #1–#2) are still open (Q33): raise them before the demo.
4. The first request for a new custom scenario computes it. Identical concurrent requests may compute it twice (harmless). The cache holds 32 scenarios per store (worst case about 64 MB).
5. `TestClient` emits a Starlette/httpx deprecation warning (harmless).

### A.6 Addendum: prototype gap analysis (plan 3.0)

The user added a UI prototype in `ui_prototype/v1/` (4 static HTML screens). The user asked that anything the prototype shows be served by the backend too. The citizen view (`ugp_atlante_vista_cittadino.html`) is **ignored for now** (Q40).

**Gap list** (the 3 in-scope screens: `schermata_mappa`, `pesi_e_classifica`, `simulatore_prima_dopo`):

| Prototype element | Before | Action |
|---|---|---|
| Zone card: IPF, class, indicator scores, trees, disclaimer | served | none |
| "Verde attuale → target 15%" | target only in metadata | added `trees.target_green_share` and `trees.trees_for_target` to the detail |
| Map tabs Aria / Traffico / Verde (colour by one indicator) | missing | added `score_<key>` to `/api/cells` and `/api/zones` |
| Ranking bars split by indicator contribution | missing | added `contributions` to `/api/ranking` items |
| Free weight sliders, "il calcolo li normalizza sul totale" | sum had to be 100 | weights now normalised on their total (Q36) |
| Simulator: N trees → green %, IPF, class before/after | missing (needed a method) | new `/api/{cells,zones}/{id}/simulate?trees=N` (FR-28, Q37); pure maths in `pipeline/model.py` (`green_deficit_score`, `spread_trees`) |
| 5 classes, fixed thresholds | conflict with Q11 | kept 4 quartiles (Q34) |
| Industry slider, score bar, *AIA* tab | conflict with Q18 | no slider or bar; the *AIA* tab shows the facilities layer (Q35) |
| "griglia 500 m" | conflict with Q7 | default stays 250 m (Q38) |
| Park dots, legend, "Ripristina" | derivable | client-side (green layer centroids, metadata defaults) |
| Zone "verde → target" line (A.6 finding) | contradictory for 3 zones | zones show the mean share + cells below 15% (Q42): added `trees.cells_below_target` to the zone detail |
| Dropdown not following the dark theme (only `<select>` is in the ignored citizen view) | prototype bug | UI rule NFR-11: light + dark themes, every control styled for both (Q39) |

**Verified**:
- `uv run pytest`: 68 passed. The fixture was rebuilt so that green scores come from green shares and zones are aggregated from their cells, like the pipeline does.
- Simulator tests:
  - 0 trees reproduces the detail values;
  - the cell formula, the zone spreading by deficit, and the area fallback are all checked;
  - planting `trees_for_target` reaches 15%.
- Real data, Libertà (default weights): IPF 86.3, alta, 4th. With the 601 estimated trees: 85.1, medio-alta, 5th. With the 2,432 trees for the target: 81.6, 6th. About 3 ms per simulation.
- `/api/cells` is now 1.41 MB uncompressed and 210 KB gzipped over HTTP, served in 0.12 s (it was 1.2 MB and 190 KB before the score columns).
- **Finding** (documented in methodology §10.1): zone deficits are sums of cell deficits. So Murat (16.3%), Libertà (20.9%) and San Paolo (23.2%) have an average green share above the 15% target and still a deficit. The zone card must not show "20,9% → 15%" as if the target were met (see B.5).

---

## Part B: Handoff for the next agent (Phase 3, frontend)

### B.0 The UI prototype (start here)
The user's prototype is in **`ui_prototype/v1/`**. It is the reference for **layout, screens, visual style and features** of the real UI. It is **not** the reference for the stack: build with the decided stack (Q13: React + TS + Vite, MapLibre via react-map-gl, Tailwind, Recharts, npm) and follow the project rules (CLAUDE.md: Italian UI only, English code; NFR-07 disclaimers; FR-50 / NFR-09 mobile-first).

- **Ignore `ugp_atlante_vista_cittadino.html` (citizen view) for now** (Q40, plan §1.4). It will be added only once the demo works end to end.
- **The gap analysis is done** (A.6). The backend now serves everything the three in-scope screens need. The prototype's conflicts with earlier decisions were resolved as Q34–Q39: **follow the decisions, not the prototype**, on these points:
  - 4 quartile classes, not 5 (Q34);
  - no industry slider or score bar, and the *AIA* tab shows the facilities layer (Q35);
  - 250 m default grid (Q38);
  - the simulator's target text (Q37).
- **Rule from the user**: anything the prototype shows that the backend doesn't serve must be added to the backend too. If you find something A.6 missed, add it (with tests and plan §7.2). Ask first if it needs a new method or data choice.
- **Prototype bug to fix, not copy**: dropdowns render in a different style and ignore the dark theme. In the real UI every control (dropdowns and their option lists, sliders, inputs, buttons) must match the rest of the UI in both light and dark theme (NFR-11, Q39). Native `<select>` option lists follow the OS style unless `color-scheme` is set, so prefer a styled headless listbox.
- The prototype's HTML depends on CSS variables from the page that hosted it (`--surface-1`, `--text-secondary`, `--font-voice`, `--font-mono`, …), and they aren't defined in the files. Define your own theme tokens (light + dark) with the same roles, plus the prototype's colours:
  - priority scale `#FAEEDA #FAC775 #F0997B #D85A30 #993C1D` (use 4 of them, Q34);
  - green `#639922`;
  - indicator colours `#0F6E56` (inquinamento), `#7F77DD` (verde), `#D85A30` (traffico), `#BA7517` (popolazione).

### B.1 Read first
1. `ui_prototype/v1/` (see B.0) and A.6 above.
2. `CLAUDE.md`: rules (Italian UI only, git, ask-don't-guess, handoffs).
3. `docs/requirements_and_plan.md`: §1.4 (citizen view deferred), §4.3 (FR-40…53), §5 (NFR-04, NFR-07, NFR-09, NFR-11), §7.2 (**the API as built**), §8 Phase 3, §10.0 (up to Q44).
4. `docs/methodology.md` (Italian): source text for the "Metodologia e fonti" modal, the explanations (§11) and the simulator (§10.1).
5. The live API docs: `uv run uvicorn backend.main:app --reload`, then `http://localhost:8000/docs`.

### B.2 Current state
- The backend is complete, including the prototype additions. Run `uv run python -m pipeline build` once if `data/processed/` is missing, then `uv run uvicorn backend.main:app --reload`. `cd frontend && npm run dev` proxies `/api` to :8000.
- The frontend is still the Vite + React + TS + Tailwind skeleton. MapLibre, react-map-gl and Recharts aren't installed yet (stack Q13).

### B.3 What the API gives the UI (keys + numbers only; all Italian text lives in the frontend)
- **Map** (FR-40, FR-52):
  - `/api/cells?grid=250|500`: `cell_id`, `zone_id`, `analysed`, `ipf`, `ipf_class` 0–4, `rank`, `robust`, `score_<key>`;
  - `/api/zones`: `zone_id`, `name`, `analysed`, `ipf`, `ipf_class`, `rank`, `robust`, `trees_new`, `score_<key>`;
  - the *Priorità* tab colours by `ipf_class`; the *Aria* / *Traffico* / *Verde* / *Popolazione* tabs colour by `score_pollution` / `score_traffic` / `score_green_deficit` / `score_population` (0–100);
  - class 0 / `analysed: false` means not analysed (grey). Torre a Mare is `analysed: false` (disclaimer `population_coverage`).
- **Zone card / detail panel** (FR-42/43/51): `/api/zones/{id}` and `/api/cells/{cell_id}` return:
  - `indicators[]` (raw value, score 0–100, weight, contribution);
  - `top_drivers[]` (3, sorted);
  - `trees` (`trees_new`, `target_green_share`, `trees_for_target`, deficit, and for zones `cells_below_target`: compare with `stats.cells_analysed`);
  - `sensitivity` (`rank_p5`, `rank_p95`, `robust`, `applicable`);
  - `stats` (`green_share`, residents, …);
  - `class_key` (`bassa`/`media`/`medio_alta`/`alta`);
  - `ranked_items` (for "3° su 16").
- **Weights** (FR-45): `?weights=pollution:25,green_deficit:35,traffic:20,population:20` on every endpoint except layers/metadata. Each value is 0–100, and they're normalised on their total (Q36), like the prototype's free sliders (step 5). Initial and "Ripristina" values: `metadata.weights.configured_pp` of the active indicators. A 400 carries `detail`, an English message for developers: map it to an Italian UI message, don't show it.
- **Ranking** (FR-46): `/api/ranking?level=zone|cell&limit=`. Each item has `contributions` (per indicator, summing to `ipf`) for the split bars, plus `trees_new`, `ipf_class`, `rank_p5`/`rank_p95`, `robust`.
- **Simulator** (FR-53): `/api/zones/{id}/simulate?trees=N` and `/api/cells/{cell_id}/simulate?trees=N` (+ `weights`) return:
  - `before` / `after`: `green_m2`, `green_share`, `score_green_deficit`, `ipf`, `ipf_class`, `class_key`, `rank`;
  - `trees_estimate` (model) and `trees_for_target` (15%): use them for the slider range and markers;
  - 400 if the item isn't analysed.
- **Sensitivity** (FR-27/51, "Verifica robustezza" button, methodology modal): `/api/sensitivity?level=…` (`summary.spearman_mean`, `top_n_overlap_mean`, `robust_share`, `one_at_a_time[]`).
- **Metadata** (FR-24/47): `weights`, `classes.keys`, `trees`, `disclaimers` (keys), `sources`, `inputs`, `grids.*.class_edges`, `layers`.
- **Layers** (FR-44, *AIA* tab): `/api/layers/green|traffic|air|industry`. Their properties are in `docs/artefacts.md`. `industry` is context only: its wording must express proximity, never causality (disclaimer `no_causality`).

### B.4 Implementation notes
- Use `promoteId: "cell_id"` / `"zone_id"` in MapLibre sources: features have no top-level `id`.
- Weight changes:
  - ranking and zones are a few ms, so they can update live, as in the prototype;
  - refetch `/api/cells?weights=` on slider release (debounced), which takes about 0.2 s locally.
- Simulator slider: call `simulate` debounced (about 3 ms server-side). The prototype's before/after tree drawing is decorative (client-side).
- Legend counts per class (FR-41) can be computed client-side from the GeoJSON.
- `robust: null` with `sensitivity.applicable: false` means "not applicable" (e.g. only one non-zero weight). Show a neutral state, not "sensibile".
- Prototype labels map to our keys:
  - *Inquinamento* = `pollution`, *Carenza verde* = `green_deficit`, *Traffico* = `traffic`, *Popolazione* = `population`;
  - class labels *Bassa / Media / Medio-alta / Alta* = `bassa / media / medio_alta / alta`.

### B.5 Open questions to ask the user before or while building Phase 3
1. ~~Product name~~ **Decided (Q41)**: use "Urban Green Planner" as the placeholder until the team picks the final name.
2. ~~Zone card green target~~ **Decided (Q42)**: cell card "8,2% → 15%"; zone card "Verde pubblico medio 20,9% · 14 celle su 29 sotto il 15%" (`trees.cells_below_target` / `stats.cells_analysed`).
3. ~~Tree parameters~~ **Decided (Q43)**: not editable, read-only in the methodology modal.
4. ~~Simulator entry point~~ **Decided (Q44)**: a "Simula intervento" button on the selected zone/cell card opens the simulator pre-filled (panel next to the map on desktop, step of the bottom sheet on phones). No separate screen or zone picker.

No open questions left for the start of Phase 3. Ask about anything new you find (CLAUDE.md, "Ask, don't guess").

### B.6 Pitfalls
- Never run git commands other than `git status` / `git diff`.
- Italian only in the UI. Code, comments and commits in English.
- Disclaimers always visible (NFR-07). Talk about **relative** priority (classes are quartiles).
- Don't build the citizen view yet (Q40). Don't copy the prototype's dropdown styling (NFR-11).
- Mobile first (FR-50, NFR-09): build the layout shell before the components.
- If the model changes, keep `docs/methodology.md` in sync, in Italian.
