# Phase 1 (core pipeline): review and handoff

- **Date**: 2026-09-29
- **Phase**: 1, core pipeline (plan §8, items 1.1–1.8)
- **Status**: done. All model decisions are closed (Q20–Q29 added during this phase).
- **Next phase**: 2, backend (FastAPI)

---

## Part A: Review

### A.1 What was built

| Plan item | Result | Where |
|---|---|---|
| 1.1 Loaders + cleaning | One loader per dataset. Traffic: zeros → missing, >50k/day → missing, August 2025 excluded. Addresses → civic points (92.3% matched). | `pipeline/loaders.py` |
| 1.2 Study area | Covered quartiere AND (≥ 800 res/km² OR ≥ 30% artificial surface). Torre a Mare excluded. | `pipeline/build.py` |
| 1.3 Grid | 250 m + 500 m, nested, clipped to the boundary, slivers < 10% dropped | `pipeline/grid.py` |
| 1.4 Artefact schema | Documented | `docs/artefacts.md` |
| 1.5 Indicators | Green coverage, traffic (Gaussian kernel with a 1% cutoff), air (IDW), population (density) | `pipeline/indicators.py` |
| 1.6 Normalisation, IPF, classes, trees, zones | Robust min–max (log for traffic/population), weighted sum, quartile classes, tree formula, population-weighted zone aggregation | `pipeline/model.py`, `pipeline/build.py` |
| 1.7 Sensitivity | Dirichlet Monte Carlo (1,000 runs, ±5 pp) + one-at-a-time ±10 pp | `pipeline/sensitivity.py` |
| 1.8 Export + sanity check | GeoParquet + GeoJSON + `metadata.json`. The sanity map was checked visually (not committed). | `data/processed/` (gitignored) |
| (extra) Methodology | Full methodology in Italian, replacing plan §6 | `docs/methodology.md` |

`uv run python -m pipeline build` runs everything in about 28 s. There are 27 tests (model maths, sensitivity, grid/indicators/address matching on synthetic data), and ruff is clean.

### A.2 Results (default weights)

- 1,127 of 2,006 cells analysed at 250 m, 315 of 528 at 500 m. 16 of 17 quartieri are analysed.
- Top zones: Madonnella, Murat, San Pasquale, Libertà, San Nicola. Bottom zones: San Paolo, Ceglie, Carbonara. This is plausible: a dense centre with little public green, versus outer frazioni with lower measured pollution and traffic.
- Robustness: zones have Spearman 0.98 and 14 of 16 are robust (the whole top 10). In the one-at-a-time test the zone top 10 never changes. Cells at 250 m: Spearman 0.98, 72% robust.
- About 54,900 new trees estimated in total.
- Full results and explanations: `docs/methodology.md` §12–§13.

### A.3 Deviations from the plan and new decisions

All of these are recorded in the decision log (plan §10.0):
- **Q20–Q23** (asked before implementation): the population indicator uses total residents, as a density; the mask threshold is applied as a density (800/km²); unmatched residents are spread over civic points.
- **Q24**: traffic kernel cutoff at 1% (≈ 910 m). This was added after the review showed that log + Gaussian tail gave mid-range scores to cells far from any sensor.
- **Q25–Q29**: sensor cap, IDW power, centroid zone assignment, sliver threshold, summing detector averages.
- The plan's §6 was replaced with a pointer to `docs/methodology.md`.
- `config/bari.yaml` gained `zones` (SIT name → id/display name/rione), `urban_mask.min_resident_density_km2` (replaces `min_residents`), `urban_mask.min_cell_area_share`, `traffic.max_detector_daily_vehicles`, `traffic.kernel_min_weight`, `traffic.outlier_iqr_factor`, `air.idw_power`, `population.indicator` and `sensitivity.seed`.

### A.4 Process issue (lesson learned)

Five method choices (now Q25–Q29) were first implemented and only then listed as "to confirm" in a summary. The user didn't recognise them as questions. They were asked again properly and all confirmed, so no rework was needed. **Rule for next agents**: ask explained questions *before* building on a choice (CLAUDE.md, "Ask, don't guess"). Back any "this data is bad" claim with concrete values.

### A.5 Known issues and open points (not blocking Phase 2)

These are data and method limits. They're documented in `docs/methodology.md` §14. Raise them with the user if they matter for a task. Don't change them silently.
1. **Green deficit saturates**: 49% of analysed cells have no mapped public green, so their deficit score is 100. The indicator acts almost like a yes/no for half the area.
2. **The mask is dominated by artificial surfaces**: 672 of 1,127 analysed cells pass only the 30% artificial rule (industry, port, infrastructure), and 45% of those have zero residents. They mostly end in the low classes, because population is 0 there. The user hasn't discussed this yet. It could be worth raising before the demo.
3. **Traffic cliff**: the score drops from about 50 to 0 at about 910 m from a sensor (a consequence of Q24). 31% of analysed cells have traffic 0 ("not measured").
4. **Industry path not implemented**: if the industry indicator ever becomes active (≥ 3 recent facilities), `build_cells` raises `NotImplementedError`, because the spatial method is undecided.
5. **Zone IPFs are compressed** (63–95), because they are population-weighted means of cell IPFs. Classes are quartiles, so the map stays readable, but absolute zone IPFs look high. The UI should talk about relative priority (as planned).
6. **No end-to-end test**: `pipeline build` needs `data/raw/` (gitignored, 281 MB), so the tests use synthetic data. The real build is only checked by running it.
7. **Cell GeoJSON size**: `cells_250.geojson` is about 2.7 MB with all columns. The backend should serve only the needed properties (see B.4).

---

## Part B: Handoff for the next agent (Phase 2, backend)

### B.1 Read first
1. `CLAUDE.md`: rules (language, git, ask-don't-guess, handoffs).
2. `docs/requirements_and_plan.md`: §4.2 (backend requirements FR-20…27), §7.2 (API sketch), §8 Phase 2, §10.0 (decisions).
3. `docs/artefacts.md`: exact columns of what the backend loads.
4. `docs/methodology.md` (Italian): the model, if you need to understand a number.

### B.2 Current state
- `data/processed/` is **gitignored**. Rebuild it with `uv run python -m pipeline download` (only if `data/raw/` is missing) and then `uv run python -m pipeline build`.
- `backend/main.py` only has `/api/health`, plus static serving of `frontend/dist` mounted at `/` (mounted last, so `/api` wins).
- The frontend is still the Vite skeleton.

### B.3 What to reuse (don't reimplement the maths)
- `pipeline.model`:
  - `effective_weights(weights, active)` validates and normalises (raises `ValueError` on bad input);
  - `score_matrix(df, active)`, `compute_ipf`;
  - `quantile_classes` (class 0 = not analysed);
  - `ranks_desc`, `contributions`;
  - `top_drivers(row, weights, n=3)` returns keys + numbers for the explanation;
  - `INDICATORS`, `CLASS_KEYS`.
- `pipeline.sensitivity`: `sample_weights(center, spread_pp, runs, seed)`, `run_sensitivity(scores, center, weights, top_n, robust_threshold)` and `one_at_a_time(...)`. On-request sensitivity for custom weights takes about 0.1 s for the 1,127 cells at 250 m (measured).
- Parameters: read `data/processed/metadata.json` (`indicators.active`, `weights.effective`, `sensitivity.*`, `classes`), not the YAML. It records what the artefacts were actually built with.

### B.4 Implementation notes
- **Load at startup**: `cells_250.parquet`, `cells_500.parquet`, `zones.parquet` (EPSG:4326) and `metadata.json`. The context layers are already GeoJSON (`layer_*.geojson`) and can be served as-is.
- **Recompute with custom weights** (FR-23):
  - `ipf = score_matrix(df[analysed], active) @ w`;
  - then re-derive the classes (quartiles) and ranks. Zones work the same way, because zone scores are already population-weighted, so the zone IPF is linear in the weights.
  - Rows that aren't analysed keep IPF null and class 0.
- **Weights input**: the user gives percentage points that must sum to 100 (FR-23). `industry` is inactive, so reject a non-zero industry weight, or ignore it. **This is a design choice: ask the user.**
- **JSON**: parquet has nulls (non-analysed cells, Torre a Mare) and nullable ints (`Int64`, `boolean`). Convert NaN/NA to `null`, because FastAPI/json fails on NaN.
- **Payload size** (NFR-04, < 3 s over ngrok): send the map GeoJSON with only `cell_id`, `zone_id`, `analysed`, `ipf`, `ipf_class`, and maybe `robust`. Serve the full row from the detail endpoint.
- **Tests**:
  - the API tests need artefacts, which are gitignored, so build a small fixture (e.g. a few synthetic cells written to a tmp dir) or skip when `data/processed` is missing (**ask the user which**);
  - `TestClient` emits a Starlette/httpx deprecation warning (harmless).
- The **sensitivity endpoint** for default weights reads the precomputed columns and the `metadata` summaries. For custom weights, compute on request (plan §6.7 → methodology §12).

### B.5 Open questions to ask the user before or while building Phase 2
1. Custom weights including `industry` (inactive): reject or ignore?
2. API tests: synthetic fixture or skip without artefacts?
3. Does the 500 m grid also need zone-level recomputation? (Currently zones are aggregated only from 250 m, Q27.)
4. Whether to discuss known issues A.5 #1–#2 (green saturation, artificial-only cells) before the demo.

### B.6 Pitfalls
- Never run git commands other than `git status` / `git diff`.
- Keep `docs/methodology.md` in sync, **in Italian**, whenever the model changes.
- Italian only in the UI. The backend returns keys + numbers, not sentences (methodology §11).
- The product name is undecided. Use the neutral placeholder.
