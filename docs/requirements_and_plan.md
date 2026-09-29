# Urban Green Planner: Requirements Analysis & Implementation Plan

> Status: **v1.0** (2026-09-29). All design questions are decided (Section 10.0). Pending: the product name (to be chosen with the team) and two data-access actions, which belong to Phase 0. Coding starts once the user closes the planning session.
>
> Source idea: `urban_green_planner_hackathon.md` (Italian). That file is kept unchanged as the original record. Every change from it is listed with its reason in **Section 11**.

---

## 1. Purpose and scope

### 1.1 Goal
Build a decision-support web application. Using Open Data Puglia, it identifies **which areas of Bari have the highest priority for new urban trees and green infrastructure**. For each area it:

1. computes a **Forestation Priority Index (IPF, Indice di Priorità di Forestazione)** on a 0–100 scale;
2. shows the IPF on an interactive map, as grid cells and as a neighbourhood summary;
3. **explains** the score by showing each indicator's contribution (no black box);
4. gives a **model-based estimate** of the number of new trees needed to reach a target green coverage.

### 1.2 Framing constraints (from the source doc)
- The goal is **not** "restoring oxygen". The project is framed as mitigating air pollution and heat exposure, increasing urban green, and reducing population exposure.
- Industrial facilities express **proximity / pressure**, never **causality**.
- Tree counts are **model estimates**, not absolute scientific values.
- ARPA daily data is **subject to later validation/revision**. The UI must say so.

### 1.3 In scope (MVP)
- City: **Bari** only.
- Offline data pipeline → precomputed spatial artefacts.
- FastAPI backend serving the artefacts, with IPF recomputation using custom weights.
- React frontend: map, zone detail panel, explanation, tree estimate. **UI in Italian.**
- Demo: backend runs on a laptop and is exposed via an **ngrok** tunnel.

### 1.4 Out of scope (MVP), possible extensions
**Citizen view** (*vista cittadino*: neighbourhood summary for residents and a form to report a spot for a tree, prototype `ui_prototype/v1/ugp_atlante_vista_cittadino.html`): **ignored for now**, to be added only once the demo works end to end (Q40). Copernicus/Sentinel-2 NDVI, temperature/heat stress, ISPRA soil sealing, GTFS/AMTAB bus stops, road accidents, other municipalities (Copertino, Lecce), validation against Lecce planting data, multi-year comparison.

---

## 2. Stakeholders and users

| User | Need |
|---|---|
| Regione Puglia / Comune di Bari planners | Rank areas for planting investment and justify choices with data |
| Citizens / associations | Understand where and why green is lacking in their neighbourhood |
| Hackathon jury | Clear, credible, explainable demo built on open data |

---

## 3. Data audit (verified on 2026-09-29)

I downloaded and inspected the real files, not only the catalogue descriptions. **Several findings change the original plan.**

| # | Dataset | Real format / content | Geo reference | Status |
|---|---|---|---|---|
| D1 | **Aree verdi** (Comune di Bari) | SHP (ZIP), **593 polygons**, fields `id, id_tipo_ar, id_circ, id_mun, id_av, nome_area, origid`. The CSV (582 rows) has names + circoscrizione/municipio, **no geometry**. | **EPSG:32633 (WGS84 / UTM 33N)**. The catalogue says WGS84, but the geometry is UTM. | ✅ Usable (use the SHP) |
| D2 | **Traffic daily flows** | Monthly CSVs (Aug 2025 → Jun 2026, some months missing). 524 rows = detectors, keyed by `device_db, device_type, device_id, detector_id`, one column per day (`d/m/yyyy`). Trailing days are `0` (probably missing data, not zero traffic). | None (join with D3) | ✅ Usable, needs cleaning |
| D3 | **Traffic controllers positions** | Monthly JSON, `traffic_controllers_info[]`: **83 controllers, 524 detectors**, `properties.latitude/longitude`, detector codes/descriptions. **1 controller has coords (0,0).** | EPSG:4326 | ✅ Usable |
| D4 | **Air quality daily data** (ARPA) | API `cloud.arpa.puglia.it/QualitaAria` (CSV/GeoJSON, **previous day only**). | EPSG:4326 | ⚠️ **Still unreachable from this PC** (TCP timeout, 2026-09-29). Not needed: the 2025 annual means come from the ARPA annual report (`data/manual/`). |
| D5 | **Air quality stations** (ARPA) | GeoJSON, 68 stations in Puglia; **only 5 in Bari**: Caldarola, Cavour, Kennedy, Carbonara, CUS. | EPSG:4326 | ✅ Usable, but sparse |
| D6 | **Resident population** (Comune di Bari) | 4 CSVs (`under14`, `under18`, `under67`, `over67`): `NUM_RESIDENTI, VIA, CIVICO, RIONE, FRAZIONE, CAP`. **No coordinates.** 16 distinct `RIONE` values. The files are **cumulative** (verified: u14 ⊂ u18 ⊂ u67 per address), so the total is under67 + over67 = 261,399, **about 17% below** Bari's ~316k. Torre a Mare is absent. | Address + rione only | ⚠️ Needs geocoding or rione-level aggregation |
| D7 | **AIA facilities** (Regione Puglia) | CSV, 67 rows: **a list of permit procedures** (type, free-text description, date, status). **No coordinates, no facility ID**, mostly outside Bari. | None | ❌ **Not usable** as a spatial layer |
| D8 | **Civic numbers + quartieri + municipi + circoscrizioni** (SIT Comune di Bari, "civilario unico") | SHP via `sit.egov.ba.it` | EPSG:32633 | ✅ **Downloaded** (Phase 0). The server doesn't send its intermediate TLS certificate, which is why phones worked and scripts didn't. Fixed with `config/certs/intermediates.pem`, verification kept on. **17 quartieri** (16 match the population `RIONE` values + Torre a Mare), **58,495 civic points**. A simple address join places **91.8% of residents**. |
| D9 | **Circoscrizioni** (2013) | ZIP on opendata.comune.bari.it (direct link found) | n/a | 🔍 Not inspected yet (fallback boundaries) |
| D10 | **E-PRTR / EEA Industrial Emissions** | External, has coordinates + pollutant releases | EPSG:4326 | 🔍 Not inspected yet. Candidate replacement for D7. |
| D11 | **Sentinel-2 L2A** (Copernicus), via Microsoft Planetary Computer (no account) | Median NDVI of the 19 clear scenes of Jun–Aug 2025 (tile 33TXF), cached as one GeoTIFF by `pipeline download` | EPSG:32633, 10 m | ✅ **Used since Q49** for the green-deficit indicator and the tree estimate. D1 stays as a context layer. |

### 3.1 Consequences
1. **Industrial pressure**: AIA (D7) can't be placed on a map. Options: E-PRTR (D10), manual geocoding of the few Bari AIA sites, or dropping the indicator from the MVP → **question Q5**.
2. **Population**: needs the civic-number layer (D8) or a fallback. A fallback could spread rione totals over the residential cells of each rione → **question Q4**.
3. **Air quality**: 5 stations in Bari make any interpolation coarse. With a 30% weight, this layer would dominate the IPF with a smooth gradient that carries almost no information. We also need an averaging period (e.g. annual mean), not just yesterday → **question Q3**.
4. **Green-area mask**: D1 maps only **public urban green**. Agricultural and peri-urban land would score as "no green" and get falsely high priority. The analysis must be **limited to the urban fabric** (e.g. cells with residents, or CORINE class 1 "artificial surfaces" from *Uso del Suolo 2011*) → **question Q6**.
5. Some catalogue hosts (ARPA API, SIT) time out from here. We must **cache all raw data locally** and not depend on live APIs during the demo.

---

## 4. Functional requirements

Priority uses MoSCoW: **M** = must, **S** = should, **C** = could.

### 4.1 Data pipeline
| ID | Requirement | Pri |
|---|---|---|
| FR-01 | Download the raw datasets into `data/raw/` with a script (reproducible, idempotent). Record the source URL + download date. | M |
| FR-02 | Clean each dataset (encoding, separators, invalid coordinates such as (0,0), missing/zero days). | M |
| FR-03 | Reproject everything to a metric CRS (**EPSG:32633**) for computation. Export to **EPSG:4326** for the web. | M |
| FR-04 | Generate a regular square grid over Bari (cell size configurable: 250 m / 500 m), clipped to the municipal boundary and masked to the urban area. | M |
| FR-05 | Compute per-cell raw indicators: green coverage %, traffic pressure, air-pollution level, resident population, industrial pressure (if kept). | M |
| FR-06 | Normalise each indicator to 0–100, with a documented method per indicator (Section 6.3). | M |
| FR-07 | Compute the IPF as a weighted sum with default weights stored in config. | M |
| FR-08 | Classify cells into 4 priority classes: low / medium / medium-high / high (green / yellow / orange / red). | M |
| FR-09 | Aggregate cells into neighbourhoods (quartieri or municipi). Population-weighted mean IPF, total estimated trees, dominant drivers. | M |
| FR-10 | Estimate new trees per cell and per neighbourhood (Section 6.5). | M |
| FR-11 | Write the outputs as versioned artefacts (GeoParquet + GeoJSON) plus a `metadata.json` (data dates, parameters, weights). | M |
| FR-12 | **Weight sensitivity check** (Section 6.7): perturb the weights many times, recompute the IPF, and store per cell/neighbourhood the rank interval, how often it stays in the top-N, and a robustness flag. Also store a city-level stability summary. | M |

### 4.2 Backend API
| ID | Requirement | Pri |
|---|---|---|
| FR-20 | Serve the grid cells with indicators + IPF as GeoJSON. | M |
| FR-21 | Serve the neighbourhoods with aggregated values as GeoJSON. | M |
| FR-22 | Serve the detail of one cell/neighbourhood: indicator values, normalised scores, weighted contributions, tree estimate, text explanation keys. | M |
| FR-23 | Recompute the IPF with user-supplied weights (each 0–100, normalised on their total, Q36; inactive indicators must be 0, Q30). | S |
| FR-24 | Serve the metadata: data sources, reference dates, disclaimers (ARPA validation, model estimate, no causality). | M |
| FR-25 | Serve the context layers: existing green areas, traffic sensors, ARPA stations. | S |
| FR-26 | Serve the built frontend as static files, so one ngrok tunnel exposes the whole app. | M |
| FR-27 | Serve the sensitivity results: per-zone rank interval + robustness flag, and the city-level stability summary. | M |
| FR-28 | **Tree simulator**: for one cell or zone and N new trees, return green area/share, green-deficit score, IPF, class and rank before and after, plus the model's tree estimate and the trees needed to reach the target share (Q37). | S |

### 4.3 Frontend (UI in Italian)
| ID | Requirement | Pri |
|---|---|---|
| FR-40 | Interactive map of Bari with an IPF choropleth, switchable between **grid** and **neighbourhood** view. | M |
| FR-41 | Legend with the 4 priority classes and counts per class. | M |
| FR-42 | Click a cell/neighbourhood → side panel: IPF, class, per-indicator scores (bars), contribution breakdown, estimated trees, current green %. | M |
| FR-43 | **"Perché questa zona è prioritaria?"**: generated explanation listing the top drivers in plain Italian. | M |
| FR-44 | Toggleable context layers: existing green areas, traffic sensors, ARPA stations. | S |
| FR-45 | Weight sliders ("scenario"): change the weights and the map updates. | S |
| FR-46 | Ranking table of the top-N priority neighbourhoods/cells, sortable. Each row has a bar split into the indicators' contributions (prototype). | S |
| FR-47 | "Metodologia e fonti" page/modal: formula, weights, data sources + dates, limitations and disclaimers. | M |
| FR-48 | Comune/year selectors as in the mockup (only Bari / latest data enabled, others disabled "prossimamente"). | C |
| FR-49 | Export the current ranking as CSV. | C |
| FR-50 | **Responsive layout** that adapts to phone, tablet and desktop (see NFR-09). On a phone: full-screen map, zone details in a draggable bottom sheet, legend collapsed to a button, weight sliders and ranking in a drawer/tab. On tablet: map + collapsible side panel. On desktop: map + fixed side panel. | M |
| FR-51 | Show the **robustness** of each zone in the detail panel and ranking. Example: badge *"Priorità robusta"* / *"Priorità sensibile ai pesi"*, plus the rank interval *"tra 3° e 7° posto"*. The methodology page shows the city-level stability summary. | M |
| FR-52 | **Map indicator tabs** (prototype): *Priorità* (IPF classes) plus one tab per active indicator (*Aria*, *Traffico*, *Verde*, *Popolazione*) colouring the map by that indicator's 0–100 score. The prototype's *AIA* tab shows the industrial facilities context layer (Q35). | S |
| FR-53 | **Simulator** (prototype), opened from the selected cell/zone card (Q44): a slider adds new trees, before/after green share, IPF and class. Markers for the model's tree estimate and for the trees needed to reach 15%. Disclaimer: only the green indicator changes (FR-28, Q37). | S |

---

## 5. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-01 | **Language**: UI in Italian. Code, comments, docs and commits in English (see `CLAUDE.md`). |
| NFR-02 | **Explainability**: every displayed score must be traceable to its indicator values and weights. |
| NFR-03 | **Offline-safe demo**: the app must run with **no live calls** to external data sources. Everything is precomputed or cached. |
| NFR-04 | **Performance**: initial map load < 3 s on a laptop via ngrok. A 250 m grid over Bari is about 3–7k cells, fine as simplified GeoJSON. |
| NFR-05 | **Reproducibility**: one command rebuilds all artefacts from raw data. Parameters live in a single config file. |
| NFR-06 | **Transferability**: city-specific inputs are isolated behind a per-city config/adapters, so Copertino/Lecce can be added later. |
| NFR-07 | **Scientific honesty**: disclaimers are always visible (model estimate, ARPA revision, no causality). |
| NFR-08 | **Licensing**: respect and cite the dataset licences (mostly IODL/CC-BY) in the UI. |
| NFR-09 | **Responsive design**: the UI works correctly from 360 px phones to wide desktop screens, in portrait and landscape. Breakpoints: phone < 640 px, tablet 640–1024 px, desktop > 1024 px. There is no horizontal page scroll and touch targets are ≥ 44 px. The map supports touch gestures (pinch zoom, tap to select). Text stays readable without zooming. Every feature available on desktop is reachable on a phone. |
| NFR-10 | **Device testing**: before the demo, check the layout in browser dev-tools device emulation (e.g. iPhone SE, Pixel 7, iPad, 1366×768 laptop, 1920×1080) **and** on at least one real phone via the ngrok URL. |
| NFR-11 | **Themes** (Q39): light and dark theme, following the device setting (`prefers-color-scheme`) with a toggle in the header. **Every control is styled for both themes and matches the rest of the UI**, native form controls included: dropdowns (`<select>` and their option lists, which browsers draw in the light system style unless `color-scheme` is set; prefer a styled headless listbox), sliders, inputs, buttons. The prototype has this bug (its dropdown ignores the dark theme): don't copy it. |

---

## 6. Methodology

The methodology now lives in **`docs/methodology.md`** (in Italian, by exception to the language rule). That file is the single, up-to-date description of how the model works and why each choice was made. This section used to contain the pre-implementation version. It was replaced at the end of Phase 1 so there is no second copy that goes stale.

Where the old subsections went (other sections of this plan still cite them):

| Old section | Topic | `docs/methodology.md` |
|---|---|---|
| 6.1 | Spatial unit, study area | §4 |
| 6.2 | Indicators | §5 |
| 6.3 | Normalisation | §6 |
| 6.4 | IPF, weights, classes | §7, §8 |
| 6.5 | Tree estimate | §10 |
| 6.6 | Explanation generation | §11 |
| 6.7 | Weight sensitivity check | §12 |

---

## 7. Architecture

```
┌──────────────────────── offline ─────────────────────────┐
│ pipeline/ (Python, GeoPandas/Shapely/pyproj)             │
│  download → clean → reproject → grid → indicators →      │
│  normalise → IPF → classify → aggregate → trees → export │
│                    ↓                                     │
│      data/processed/*.parquet  *.geojson  metadata.json  │
└──────────────────────────────────────────────────────────┘
                     ↓ (loaded at startup)
┌──────────────── FastAPI backend (Python) ────────────────┐
│ /api/cells  /api/zones  /api/zones/{id}  /api/ipf        │
│ /api/layers/{name}  /api/metadata                        │
│ + serves frontend/dist as static files at "/"            │
└──────────────────────────────────────────────────────────┘
                     ↓ HTTP (same origin)
┌──────────────── React frontend (TypeScript, Vite) ───────┐
│ Map (choropleth, layers) · Side panel · Weights ·        │
│ Ranking · Methodology — all UI strings in Italian        │
└──────────────────────────────────────────────────────────┘
                     ↓
            laptop :8000  ←── ngrok tunnel ──→ jury
```

### 7.1 Stack (decided, Q13)
- **Python 3.12**, **uv** for dependency management.
- Pipeline: `geopandas`, `shapely`, `pyproj`, `pandas`, `numpy`, `scipy` (IDW/kernels), `pyogrio`.
- Backend: `fastapi`, `uvicorn`, `pydantic`. The IPF is recomputed in memory with numpy (a few thousand cells, so it's instant).
- Frontend: **React + TypeScript + Vite**, **npm**. Map: **MapLibre GL** via `react-map-gl`, basemap **CARTO Positron** (free, no API key). Styling: **Tailwind CSS** (+ headless components). Charts: Recharts.
- Tests: `pytest` for pipeline + API, `vitest` for critical frontend logic (optional).

### 7.2 API
As built in Phase 2 (`backend/main.py`, interactive docs at `/docs`). Custom weights are passed as `weights=pollution:25,green_deficit:35,traffic:20,population:20`: one value per active indicator, each 0–100, normalised on their total (Q36). Without `weights`, the defaults apply.

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Status + artefact build time |
| GET | `/api/metadata` | `metadata.json` (sources, dates, default weights, parameters, disclaimer keys) + `layers` |
| GET | `/api/cells?grid=250&weights=…` | Grid GeoJSON with map properties only (`cell_id`, `zone_id`, `analysed`, `ipf`, `ipf_class`, `rank`, `robust`, `score_<key>` per active indicator) |
| GET | `/api/zones?weights=…` | Neighbourhood GeoJSON (`zone_id`, `name`, `analysed`, `ipf`, `ipf_class`, `rank`, `robust`, `trees_new`, `score_<key>`) |
| GET | `/api/zones/{id}` / `/api/cells/{cell_id}` (`?weights=…`) | Detail: raw values, scores, weights, contributions, top drivers, trees (+ target share, trees for the target, zones: cells below the target), sensitivity, descriptive stats |
| GET | `/api/zones/{id}/simulate` / `/api/cells/{cell_id}/simulate` (`?trees=N&weights=…`) | Tree simulator (FR-28, Q37): before/after green, green-deficit score, IPF, class, rank |
| GET | `/api/layers/{green\|traffic\|air\|industry}` | Context layers (served as built) |
| GET | `/api/ranking?level=zone\|cell&grid=&limit=20&weights=…` | Analysed items sorted by rank, with rank interval, robustness and per-indicator contributions |
| GET | `/api/sensitivity?level=zone\|cell&grid=&weights=…` | Sensitivity parameters, city-level summary and per-item results: precomputed for the default weights, computed on request for custom weights |

### 7.3 Repository layout (starting point, can evolve)
```
green_planner/
├── CLAUDE.md
├── urban_green_planner_hackathon.md
├── docs/requirements_and_plan.md
├── config/bari.yaml            # grid size, weights, tree params, sources
├── data/{raw,interim,processed}/   # raw + interim gitignored; processed maybe committed for the demo
├── pipeline/                   # Python package: download, clean, grid, indicators, ipf, export
├── backend/                    # FastAPI app
├── frontend/                   # React + Vite app (Italian UI)
├── notebooks/                  # data exploration (optional)
└── tests/
```

---

## 8. Implementation plan

No timeline is set. Coding starts once this planning session is closed. The phases below are ordered by dependency. Each has a clear "done" criterion, so the work can be split and tracked. Phases 2–4 can run **in parallel** once the artefact schema (Phase 1.4) is agreed.

### Phase 0: Setup & data acquisition
0.1 `.gitignore`, `uv` project, Vite app skeleton. (The user manages git.)
0.2 `pipeline/download.py`: fetch D1, D2 (all months), D3, D5, D6, D9 and cache them in `data/raw/` with a manifest.
0.3 Get D8 (SIT: civici, quartieri, municipi, confine) and check D4 (ARPA API) access (Q3c, Q4c).
0.4 Download E-PRTR (D10) and count the facilities within 10 km of Bari (Q5). Download *Uso del Suolo 2011* for the urban mask (Q6).
0.5 Find the ARPA Puglia 2025 annual air-quality report and transcribe the annual means of NO₂/PM10/PM2.5 for the 5 Bari stations into `data/manual/arpa_annual_2025.csv`, with the source cited (Q3b).
**Done when**: all MVP raw files are cached locally and the manifest is committed.

**Status (2026-09-29): done.** The user handles all git operations (committing included). Q18 and Q19 were raised and decided during this phase.
- Repo initialised, uv project (`pyproject.toml`), Vite + React + TS + Tailwind skeleton, FastAPI skeleton (`/api/health`, serves `frontend/dist`), pytest + ruff passing.
- `uv run python -m pipeline download` fetched every required source (281 MB, `data/raw/manifest.json`). The only failure is the optional ARPA daily API.
- ARPA 2025 annual means transcribed into `data/manual/arpa_annual_2025.csv` (source: *Relazione annuale 2025*, Rev. 1, July 2026; see `data/manual/README.md`). PM2.5 isn't measured at Carbonara and CUS.
- E-PRTR: 4 facilities with NOₓ/PM10 releases within 10 km of the municipal boundary. Only Modugno CCGT reports in 2024 (O-I glass plant 2022, Powerflor 2017, Bari thermal plant 2008). Under Q18 only 2 facilities count, so the indicator is dropped (context layer only).

### Phase 1: Core pipeline
1.1 Loaders + cleaning per dataset (encoding, CRS, invalid coords, zero-day gaps).
1.2 Study area: municipal boundary + urban mask.
1.3 Grid generation (configurable size).
1.4 **Define the artefact schema** (columns of cells/zones GeoParquet + metadata.json). This unblocks backend + frontend with mock data.
1.5 Indicators: green coverage → traffic kernel → population → air IDW → industry.
1.6 Normalisation, IPF, classes, tree estimate, neighbourhood aggregation.
1.7 Weight sensitivity check (Section 6.7): Monte Carlo + one-at-a-time, with results exported.
1.8 Export + a sanity-check notebook/map (do the results make sense for Bari? e.g. Libertà/Murat vs Poggiofranco).
**Done when**: `python -m pipeline build` produces `data/processed/` from `data/raw/` in one command, and the sanity map looks plausible.

**Status (2026-09-29): done.** Q20–Q29 were raised and decided during this phase.
- `uv run python -m pipeline build` builds everything in about 30 s. The artefact schema is in `docs/artefacts.md`. Modules: `loaders`, `grid`, `indicators`, `model` (shared with the backend), `sensitivity`, `build`.
- Study area: 1,127 of 2,006 cells at 250 m, and 315 of 528 at 500 m. 16 of 17 quartieri are analysed (Torre a Mare is excluded).
- Population: 92.3% of residents matched to a civic point (exact or number-only). The rest are spread over their quartiere's civic points, so no resident is lost.
- Traffic: 66 of 83 controllers have valid data. 17 report only zeros in every month. BG022 has isolated one-day spikes (up to 327,675/day, between normal readings of 300–2,500), which the detector plausibility cap removes (Q25).
- Sanity check: the top zones are Madonnella, Murat, San Pasquale, Libertà and San Nicola (dense centre, little public green). The bottom zones are Carbonara and Ceglie (low pollution and traffic). The ASI industrial area is analysed through artificial surface, with a population score of about 0.
- Traffic cutoff (Q24): 351 of 1,127 analysed 250 m cells are beyond about 910 m from any sensor and get traffic 0. The zone top 10 didn't change.
- Sensitivity (default weights): zones have mean Spearman 0.98, a mean top-10 overlap of 9.98/10, and 14 of 16 are robust (Palese - Macchie and Loseto, ranks 12–13, are sensitive to weights). At 250 m, cells have mean Spearman 0.98, and 72% are robust (77% of the top 10%).

### Phase 2: Backend
2.1 FastAPI app loading the artefacts at startup.
2.2 Endpoints from Section 7.2, with Pydantic response models.
2.3 IPF recomputation with custom weights + validation. Sensitivity endpoint (precomputed + on request).
2.4 Static serving of `frontend/dist`. CORS for dev.
2.5 pytest: IPF math, weight validation, endpoint smoke tests.
**Done when**: all endpoints return real data and the tests pass.

**Status (2026-09-29): done.** Q30–Q33 were raised and decided during this phase. Review and handoff: `docs/handoff/phase_2.md`.
- `backend/store.py` loads the artefacts at startup (about 0.5 s), recomputes custom-weight scenarios with `pipeline.model` / `pipeline.sensitivity` and caches them. `backend/schemas.py` has the Pydantic models, and `backend/main.py` the routes (API table in §7.2).
- Recomputing with the default weights reproduces every precomputed column exactly (IPF, class, rank, sensitivity) at all three levels.
- Map payload: `/api/cells` is 1.2 MB raw, 190 KB gzipped, served in about 0.12 s locally. A custom-weight recompute of the 250 m grid (with its sensitivity check) takes about 0.2 s.
- 57 tests pass (27 before this phase). `tests/test_backend.py` has 26 API tests on a synthetic fixture plus a smoke test on the real artefacts, and `tests/test_sensitivity.py` covers the zero-weight rule.

### Phase 3: Frontend (Italian UI)
3.0 **Prototype gap analysis**: the user's UI prototype in `ui_prototype/` is the reference for layout and features (not for the stack: Q13 applies). List what it shows, compare it with the API (§7.2), and **add anything missing to the backend too** (asking first about any new method or data choice). See `docs/handoff/phase_2.md` B.0. **Done (2026-09-29)**: gap list and the backend additions (FR-28, map scores, ranking contributions, tree target) are in the handoff; Q34–Q44 decided. The citizen view is ignored for now (Q40).
3.1 **Responsive layout, built mobile-first** (FR-50, NFR-09): header (name → Q14), map, and a detail container that is a side panel on desktop/tablet and a bottom sheet on phones. Build this first, so every later component is made to fit it.
3.2 Choropleth + legend (collapsible on phones) + grid/neighbourhood toggle.
3.3 Detail panel: indicator bars, contribution breakdown, trees, "Perché questa zona è prioritaria?", robustness badge + rank interval (FR-51).
3.4 Context layers toggle.
3.5 Weight sliders → refetch/recolour, plus a "Verifica robustezza" button.
3.6 Ranking table (switches to a card list on phones), methodology & sources modal (includes the sensitivity summary), disclaimers.
**Done when**: the full flow *map → zone → IPF → reasons → robustness → suggested intervention* works end to end on real data, at phone, tablet and desktop widths.

**Status (2026-09-29): done.** Q45–Q48 were raised and decided during this phase. Review and handoff: `docs/handoff/phase_3.md`.
- The app is in `frontend/src/` (React + TS + Vite, MapLibre via react-map-gl, Tailwind v4, Headless UI). It covers the map with indicator tabs, the quartieri/250 m/500 m switch, context layers, the legend with class counts, the detail card with explanation and robustness, the simulator, the weights with "Verifica robustezza", the sortable ranking with CSV export, the methodology modal, and light and dark themes.
- Checked in headless Chrome at 360×740, 390×844, 820×1180, 1366×768 and 1440×900: no horizontal scroll and no console errors. The full flow works on real data, and the numbers match the API (at the end of Phase 3, before Q49: Libertà 86,3 → 85,1 with 601 trees).
- **Q49–Q50** (after the Phase 3 review, closing Q33): the green indicator and the trees use Sentinel-2 vegetation, and non-residential cells' trees are reported apart. See `docs/handoff/phase_3.md` A.6.
- The production build served by the backend on :8000 is ready (map + legend) in about 1.7 s locally. The ngrok and real-phone checks are Phase 4 (NFR-10).

### Phase 4: Demo readiness
4.1 Production build, single `make demo` / script (build frontend → run uvicorn on port 8080 → start ngrok with `ngrok http 8080 --url https://green-planner.ngrok.io`).
4.2 Test via ngrok from a phone/another network. Check the load time. Run the device checks of NFR-10 (dev-tools emulation + at least one real phone, portrait and landscape).
4.3 Demo script: 2–3 zones to show, with a compelling narrative (e.g. a high-priority zone with its top drivers vs a low one).
4.4 README (English) + slide material if needed.
**Done when**: the full demo runs from a clean start in under 2 minutes with no network dependency except ngrok + basemap tiles.

### Phase 5 (stretch, only if time allows)
Weight presets ("salute", "clima", "equità"), CSV export, ~~Sentinel-2 NDVI~~ (done in Q49), bus stops (GTFS), Copertino/Lecce proof of transferability.

### 8.1 Team split (for when the team joins; for now a single developer, see Q15)
- **Data/GIS**: Phases 0–1.
- **Backend**: Phase 2 (starts on mock artefacts after 1.4).
- **Frontend**: Phase 3 (starts on mock API after 1.4).
- **Pitch/UX**: Italian copy, methodology text, demo script, slides.

When the team joins, the user creates **one git branch per person**, named after the area they own (e.g. `data/<name>`, `backend/<name>`, `frontend/<name>`). Each branch comes with a clear written description of who does what, and merges go into `main`, so people don't interfere with each other.

---

## 9. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| ARPA API / SIT hosts unreachable or slow | No pollution/population layer | Cache early, try other networks, fallbacks (Q3, Q4) |
| Only 5 air stations in Bari | Pollution layer is almost uniform, and with a 30% weight it distorts the IPF | Lower its weight, or combine it with the traffic proxy (Q3, Q10) |
| Public-green dataset ignores private/agricultural green | False high priority at the city edges | Urban mask (Q6); later NDVI |
| Population geocoding | Coarse population layer | Civic-number layer from SIT or rione-level spreading |
| Weights look arbitrary to the jury | Credibility | Weight sensitivity check (robust zones shown explicitly) + weight sliders + methodology page + literature-based justification |
| Map-heavy UI breaks on small screens | Jury opens the ngrok link on phones and sees a broken page | Mobile-first layout (FR-50), device checks (NFR-10) |
| ngrok / venue Wi-Fi fails | Demo fails | Local fallback on the laptop screen, pre-recorded video |
| Basemap tiles need internet | Blank map offline | Accept (ngrok needs internet anyway), or bundle a simple boundary basemap |

---

## 10. Questions and decisions

### 10.0 Decision log (2026-09-29)
The user accepted **all recommendations** below. The detailed questions are kept after this table as the rationale for each decision.

| # | Decision |
|---|---|
| Q1, Q2 | Withdrawn: no timeline. Coding starts after planning is closed. |
| Q3a | Pollutants: **NO₂ + PM10 + PM2.5** (mean ratio to EU limits) |
| Q3b | **2025 annual means** per station, copied by hand from the ARPA annual report. Fallback: collected daily API values. |
| Q3c | ⏳ **Pending action**: check ARPA API access from the user's network (see Q4c) |
| Q4a | **Exclude** zones not covered by the population data (e.g. Torre a Mare) and state it in the UI |
| Q4b | **Civic-number join** (SIT), with rione spreading as fallback |
| Q4c | ⏳ **Pending action**: get the SIT files (VPN check or manual download) |
| Q5 | **E-PRTR within 10 km**. Drop the indicator if there are fewer than 3 facilities. |
| Q6 | Urban mask: **≥ 50 residents OR ≥ 30% artificial surface** |
| Q7 | **Both 250 m and 500 m** grids, 250 m by default |
| Q8 | **Sum** detectors · **exclude August 2025** · **0 = missing** · **σ = 300 m** |
| Q9 | **Robust min–max (p5–p95)**, log transform for traffic and population |
| Q10 | Weights **20 / 30 / 20 / 20 / 10** (pollution / green / traffic / population / industry). If industry is dropped, **proportional** redistribution. |
| Q11 | **4 classes**, **quartile** boundaries |
| Q12 | Target **15%**, plantable fraction **25%**, crown **30 m²** |
| Q13 | **uv**, **MapLibre GL** (`react-map-gl`), **Tailwind CSS**, **npm**, **CARTO Positron** |
| Q14 | ⏳ **Pending**: product name to be chosen with the team. Use a placeholder until then. |
| Q15 | **The user is the only developer for now.** When the team joins, work happens on **per-person git branches with clear ownership**, so people don't interfere with each other. |
| Q16 | **Quartieri** (SIT). Fallback: circoscrizioni 2013. |
| Q17 | **±5 pp** spread, **1,000** runs, **top 10** neighbourhoods / **top 10%** cells, **≥ 80%** = robust |
| Q18 | Only facilities that **reported in the last 5 years** count (the user had no preference, so the recommendation was adopted; it can be changed). With the current data that's 2 (Modugno CCGT 2024, O-I 2022), so the **industry indicator is dropped** and its 10 points are redistributed proportionally. The recent facilities are shown as a **context layer**. |
| Q19 | **EU Directive 2024/2881 (2030) limits**: NO₂ 20, PM10 20, PM2.5 10 µg/m³ |
| Q20 | Population indicator = **total residents** (under67 + over67). Vulnerable residents are shown in the detail only. (Phase 1) |
| Q21 | Population indicator as **density** (residents/km²), so clipped edge cells aren't penalised. (Phase 1) |
| Q22 | Urban-mask resident threshold applied as a **density**: 50 per 250 m cell = **800/km²** (so 200 per 500 m cell). (Phase 1) |
| Q23 | Unmatched residents are spread over the **civic-number points of their quartiere**, in equal shares. (Phase 1) |
| Q24 | Traffic kernel **cut off below 1% influence** (≈ 910 m with σ = 300 m): cells farther from every sensor get traffic 0 ("no measured traffic nearby"). Without the cutoff, the log transform (Q9) turned the Gaussian tail into mid-range scores (e.g. 51/100 at 900 m from a 20,000-vehicle intersection). (Phase 1) |
| Q25 | Traffic detector-days above **50,000 vehicles** are treated as missing. Evidence: BG022 has isolated one-day spikes (65,719, 131,674, 261,885 and 327,675) between normal readings of 300–2,500 on the same detector. One lane can't exceed about 48,000/day. 99.9% of all readings are below 21,000. Only 3 readings are removed in the months used, and the consistently busy sensor at 30–38k/day is untouched. (Phase 1) |
| Q26 | Air-pollution IDW **power 2**. (Phase 1) |
| Q27 | A cell belongs to the quartiere containing its **centre point**. Zone aggregates come from the **250 m** grid. (Phase 1) |
| Q28 | Clipped cell fragments **< 10%** of a full cell are dropped from the grid. (Phase 1) |
| Q29 | A controller's daily traffic = **sum of its detectors' averages** (each detector averaged over its valid days), so a missing day on one detector doesn't lower the total. (Phase 1) |
| Q30 | Custom weights with a **non-zero weight for an inactive indicator** (`industry`) are **rejected** (HTTP 400). A weight of 0 is accepted and ignored. (Phase 2) |
| Q31 | Custom weights may be **0 to 100** per indicator. A **0 weight stays 0** in every sensitivity run: only the non-zero weights are perturbed, and the ±5 pp spread is calibrated on them. If there is nothing to perturb (a single non-zero indicator, or weights too concentrated for ±5 pp), the ranking is still returned and sensitivity is marked **not applicable**. The default results are unchanged. (Phase 2) |
| Q32 | API tests run on a **synthetic fixture** (tiny artefacts written to a temp dir), plus a smoke test on the real `data/processed/` that is skipped when it isn't built. (Phase 2) |
| Q33 | The open model issues from Phase 1 (green-deficit saturation, artificial-only cells) are **discussed later, before the demo**, not before Phase 2. (Phase 2) **Resolved by Q49 and Q50.** |
| Q34 | The UI prototype shows **5 classes** (fixed thresholds 20/40/60/80). **Kept 4 quartile classes** (Q11): with fixed thresholds all 16 quartieri (IPF 63–95) would fall into the top two classes. The UI uses 4 shades of the prototype's palette. (Phase 3.0) |
| Q35 | **Industry in the UI: context layer only.** No industry slider or score bar (the prototype has both). The prototype's *AIA* tab shows the industrial facilities layer (proximity, never causality). (Phase 3.0) |
| Q36 | Custom weights are **normalised on their total** (as in the prototype, "il calcolo li normalizza sul totale"): each 0–100, total > 0. Replaces the sum-to-100 rule of FR-23. (Phase 3.0) |
| Q37 | **Tree simulator**: each new tree adds its **crown area (30 m²)** to the green area. Only the green-deficit score changes (same normalisation bounds), then the IPF with the current weights; class and rank are placed against the current city (the rest unchanged). Works on **cells and quartieri**: for a quartiere, trees are spread over its analysed 250 m cells **in proportion to their green deficit** (by area if none has a deficit), and the score is re-aggregated population-weighted. The UI shows the model estimate (`trees_new`, plantable share) and the trees needed for 15% (whole deficit / 30 m²). The prototype's "480 trees reach the target" is not kept: it contradicts the tree formula. (Phase 3.0) |
| Q38 | Default grid stays **250 m** (Q7); the prototype's "griglia 500 m" was illustrative. (Phase 3.0) |
| Q39 | **Light + dark theme**, following the device setting, with a toggle. All controls, dropdowns included, styled consistently for both themes (NFR-11). (Phase 3.0) |
| Q40 | The prototype's **citizen view** (*vista cittadino*) is **ignored for now**; to be added only once the demo works end to end (§1.4). (Phase 3.0) |
| Q41 | UI placeholder name: **"Urban Green Planner"** (the working title, as in the prototype) until the team picks the final name (Q14 still open). (Phase 3.0) |
| Q42 | **Zone card green target**: cells keep "verde attuale → 15%"; zones show the mean public green share and the **number of analysed cells below 15%** (since Q49–Q50: mean vegetation share and residential cells below 15%, e.g. Libertà 3.0%, 25 of 27) (e.g. Libertà 20.9%, 14 of 29 cells), because a zone's mean can exceed 15% while many of its cells are below it (the deficit is summed per cell). Served as `trees.cells_below_target` in the zone detail. (Phase 3.0) |
| Q43 | The **plantable fraction (25%) and crown area (30 m²) are not editable** in the app: shown read-only in the methodology modal; the tree simulator (Q37) covers the "what if" use. (Phase 3.0) |
| Q44 | The **simulator opens from the selected zone/cell card** ("Simula intervento"), pre-filled with that selection: a panel next to the map on desktop, a step of the bottom sheet on phones. No separate screen with its own zone picker. (Phase 3.0) |
| Q45 | The industry map tab is labelled **"Industria"**, not the prototype's "AIA": the layer is E-PRTR data, not AIA permits (methodology §5.5). Its legend says facilities within 10 km, context only, proximity not causality. (Phase 3) |
| Q46 | Class colours: the **darkest 4** shades of the prototype palette, `#FAC775 #F0997B #D85A30 #993C1D` (bassa → alta). The palest (`#FAEEDA`) nearly disappears on a light basemap; it is only the 0 end of the indicator-tab ramp. (Phase 3) |
| Q47 | Fonts are **bundled** with the app (npm `@fontsource`: Inter, Source Serif 4, IBM Plex Mono), so the UI needs no font CDN (Phase 4: no network dependency except ngrok and basemap tiles). (Phase 3) |
| Q48 | Both Could items are in Phase 3: **FR-48** Comune/year selectors (only Bari / latest data enabled, the others "prossimamente") and **FR-49** CSV export of the ranking. (Phase 3) |
| Q49 | **Green deficit from satellite vegetation** (closes Q33, issue 1: with the Comune's public green, 49% of analysed cells had deficit 100). Sentinel-2 L2A (D11), **median NDVI of the clear summer scenes (Jun–Aug 2025)**, a 10 m pixel is vegetated when **NDVI ≥ 0.30**. `veg_share` replaces `green_share` as the indicator, and the **tree estimate uses the same measure** (target 15%). The public green areas stay as a context layer and a descriptive value. Evidence: summer ≥ 0.30 leaves 117 cells (10%) without vegetation; ≥ 0.40 would leave 33%; the year's greenest value makes the farmland fringe look green. Public green and satellite vegetation are uncorrelated (Spearman 0.00): e.g. tree-lined-street polygons have NDVI 0.11. Trees: 45,278 (was 54,855). (Phase 3) |
| Q50 | **Non-residential cells** (closes Q33, issue 2): analysed cells with **0 residents** (rounded count; 302 at 250 m) keep their class and card ("area non residenziale"), but **zone and ranking tree totals count residential cells only**, with the rest shown apart ("+ N in aree non residenziali": 12,345 of 45,278 trees), and the **zone simulator spreads trees over residential cells only**. (Phase 3) |

### 10.1 Detailed questions (rationale)

~~Q1 Timeline~~ and ~~Q2 Pre-processed data~~ are **withdrawn**: there is no timeline, and coding starts after this planning session is closed.

---

### Q3: Air quality (3 sub-questions)
**Context.** Bari has 5 ARPA stations (Caldarola, Cavour, Kennedy, Carbonara, CUS). The ARPA API returns **only the previous day**, and it timed out from my machine. We haven't yet seen which pollutants each station measures.

**Q3a: Which pollutants make up the "pollution" indicator?**
| Option | Meaning | Consequence |
|---|---|---|
| A | NO₂ only | The pollutant most linked to traffic, and it varies most in space. Simplest to explain. |
| B | NO₂ + PM10 + PM2.5 (mean of each one's ratio to its limit value) | Broader health picture. PM is spatially smoother, so it adds little variation between areas. |
| C | B + O₃ | O₃ is usually *higher* in suburbs and parks than near traffic. It would push the index the opposite way to traffic, which is confusing to explain. |

**Recommendation: B.** A station missing one of the pollutants is averaged over the ones it has.

**Q3b: Over which period is the pollution averaged?**
| Option | Meaning | Consequence |
|---|---|---|
| A | Annual mean of the last full year (2025), per station | Scientifically sound (EU limits are annual means). Needs a historical source. The API can't provide it. |
| B | Mean of the daily API values we collect from when coding starts | Automatic, but only covers a few days or weeks and depends on the season. |
| C | A single day (yesterday) | Trivial, but not defensible: one day's weather dominates. |

**Recommendation: A.** ARPA Puglia publishes an annual air-quality report with annual means per station. I haven't verified the 2025 edition or its format yet. If it's a PDF, we transcribe 5 stations × 3 pollutants = 15 numbers by hand into a small CSV, with the source cited. **Do you accept manual transcription from the ARPA annual report?** If not, B.

**Q3c: Retry access to the ARPA API from your network.** Can you open `https://cloud.arpa.puglia.it/QualitaAria?format=GeoJSON` from your phone/browser? (Yes/No.) If only your phone reaches it, we need another route to download the data onto the PC.

---

### Q4: Population (2 sub-questions)
**Context (verified).** The 4 CSVs are **cumulative**: every under-14 address also appears in under-18 with a count ≤, and every under-18 address appears in under-67 with a count ≤. So:
- total residents = `under67` (0–66) + `over67` (67+) = **261,399**;
- vulnerable ages = `under14` + `over67`.

Bari's official population is about 316k, so **about 17% of residents are missing** from this dataset. Also, the `FRAZIONE` values are BARI, CARBONARA, CEGLIE, LOSETO, PALESE, S.SPIRITO: **Torre a Mare does not appear at all**. Every address has a `RIONE` (16 values).

**Q4a: How do we handle the missing ~17%?**
| Option | Meaning | Consequence |
|---|---|---|
| A | Use the data as-is and state the undercount in the methodology page | Simple. Areas absent from the data (e.g. Torre a Mare) get a population score of 0, which lowers their IPF unfairly. |
| B | As A, but **exclude from the study area** the zones not covered by the population data (e.g. Torre a Mare), and state this | Avoids unfair scores. Those zones aren't analysed at all. |
| C | Rescale each rione to official totals | We don't have official per-rione totals from another source, so this isn't possible without more data. |

**Recommendation: B.**

**Q4b: How do we place residents on the map?**
| Option | Meaning | Consequence |
|---|---|---|
| A | Join addresses to the **SIT civic-number layer** (point per house number), then count per cell | Accurate. Needs the SIT files (see Q4c) and address matching (street-name spelling may differ). |
| B | Spread each rione's total uniformly over its residential cells | No extra data needed, but coarse: every cell in a rione gets the same density. |

**Recommendation: A, with B as the fallback** for addresses that don't match.

**Q4c: Downloading the SIT files.** You can reach `sit.egov.ba.it` from your phone. From this PC, DNS resolves (SIT → `94.94.215.140`, ARPA → `109.117.8.6`), but the **connection times out over IPv4**, while other hosts (dati.puglia.it, opendata.comune.bari.it) work. Both are public-administration servers, so the likely cause is that they block the PC's public IP: a VPN or proxy exiting outside Italy, or a firewall. Could you:
1. tell me whether this PC is on a **VPN/proxy** (if so, try with it off and I'll retry), **or**
2. download these ZIPs from a device that works and put them in `data/raw/sit/`:
   - Civici: `https://sit.egov.ba.it/vector/api/shp/qdjango/384/vwm_db_grafo_civico20210224101146733/`
   - Quartieri: `https://sit.egov.ba.it/vector/api/shp/qdjango/384/quartieri20200616115305907/`
   - Municipi: `https://sit.egov.ba.it/vector/api/shp/qdjango/384/municipi20200616115312092/`
   - Confine comunale: `https://sit.egov.ba.it/vector/api/shp/qdjango/384/Confine_Comunale_Bari20200227151955299/`

---

### Q5: Industrial pressure
**Context.** The AIA CSV can't be used (no coordinates, only permit procedures). The indicator has a 10% weight in the original formula.

| Option | Meaning | Consequence |
|---|---|---|
| A | Use **E-PRTR** (EEA) facilities within **10 km** of Bari. Pressure = sum of reported NOₓ + PM10 releases, weighted by distance. | Real emission magnitudes. There may be very few facilities near Bari, possibly none, which I haven't checked yet. |
| B | Manually geocode the AIA procedures located in Bari | Only presence/absence, no magnitude. Few points. Manual work. |
| C | **Drop the indicator** from the MVP and redistribute its 10% (see Q10) | Simplest. Loses a dimension listed in the original idea. |

**Recommendation: A**, falling back to **C** if E-PRTR has fewer than 3 facilities within 10 km. **Do you agree with A→C, and with the 10 km radius?**

---

### Q6: Urban mask (which cells are analysed)
**Context.** The green-area data only covers public urban green, so rural cells would falsely look "green-deficient".

| Option | A cell is analysed if… | Consequence |
|---|---|---|
| A | it has **≥ 50 residents** | Depends on the population data (and on Q4). Excludes industrial zones without residents. |
| B | **≥ 30% of its area** is CORINE class 1 "artificial surfaces" in *Uso del Suolo 2011* | Includes industrial/commercial areas (relevant for heat and pollution). The land-use map dates from 2011. It's one more dataset to download. |
| C | A **or** B | Covers both residential and built-up non-residential areas. |

**Recommendation: C**, with the thresholds 50 residents / 30% artificial. **Approve C and the two thresholds, or give other values.**

---

### Q7: Grid cell size
**Context.** Bari's municipality is about 117 km². Without the mask that is about 1,900 cells at 250 m or about 470 at 500 m. Traffic and air values are interpolated anyway, so smaller cells add detail mainly to the green and population layers.

| Option | Consequence |
|---|---|
| A: 250 m only | Street-block detail, looks good on the map. Noisier per-cell values. |
| B: 500 m only | Smoother, more robust. Coarse on the map (a cell covers a whole block of quarters). |
| C: Both, computed by the pipeline and selectable in the UI | Best of both. Slightly more pipeline/UI work. |

**Recommendation: C**, with 250 m as the default view.

---

### Q8: Traffic (4 sub-questions)
**Context.** 83 controllers (intersections) with 524 detectors (induction loops, e.g. "Spira Via Napoli est"). Data runs from Aug 2025 to Jun 2026. Some months end with runs of `0`.

- **Q8a: Combining detectors per intersection.** A = **sum all detectors** (approximates total vehicles through the intersection; double counts if one intersection has both entry and exit loops); B = maximum detector (underestimates). **Recommendation: A**, plus a check that flags intersections with suspiciously high totals.
- **Q8b: Period.** A = all available months; B = all months except August 2025 (holiday traffic isn't typical); C = only the latest 3 months. **Recommendation: B.**
- **Q8c: Zeros.** Treat a detector's daily value of `0` as **missing data** (excluded from the mean) and not as "no traffic". **Recommendation: yes.** Approve?
- **Q8d: Spatial spread.** Traffic of an intersection spreads to nearby cells with a Gaussian decay, **σ = 300 m** (at 600 m the influence has dropped to about 14%). **Approve 300 m, or give another value?**

---

### Q9: Normalisation method (raw values → 0–100)
| Option | How it works | Consequence |
|---|---|---|
| A: Robust min–max | Values ≤ 5th percentile → 0, ≥ 95th → 100, linear in between | Keeps the real *distances* between areas. A few outliers don't compress everyone else. |
| B: Percentile rank | Score = % of cells with a lower value | Always spreads 0–100 evenly, even when real differences are tiny, which exaggerates small differences. |

**Recommendation: A**, with a log transform first for traffic and population (their values span orders of magnitude).

---

### Q10: Default weights
**Context.** The sliders let users change the weights, but the **default** is what the jury sees first, and what the sensitivity check is centred on.

| Option | Pollution | Green deficit | Traffic | Population | Industry |
|---|---|---|---|---|---|
| A: Original | 30 | 25 | 20 | 15 | 10 |
| B: Adjusted to data quality | 20 | 30 | 20 | 20 | 10 |
| C: Equal | 20 | 20 | 20 | 20 | 20 |

**Recommendation: B.** Green deficit is the most direct and most reliable layer. Pollution is the weakest, with only 5 stations. If industry is dropped (Q5 → C), its 10 goes to green deficit (→ 40) or is spread proportionally. **Tell me which of the two.**

---

### Q11: Priority classes
**Q11a: How many classes?** The original is inconsistent: 4 in §14, 3 in the §10 mockup. A = 4 (bassa / media / medio-alta / alta); B = 3 (bassa / media / alta). **Recommendation: A** (the MVP spec).

**Q11b: How are the class boundaries set?**
| Option | Meaning | Consequence |
|---|---|---|
| A: Fixed thresholds 25/50/75 | "Alta" means IPF ≥ 75 | Absolute meaning. The number of red cells could be very small, or zero. |
| B: Quartiles | "Alta" means the top 25% of the analysed cells in Bari | Always a readable map with balanced classes. "Alta" becomes relative to Bari. |

**Recommendation: B.** The tool's purpose is to *rank* where to intervene first. The UI will state "priorità relativa rispetto al resto della città".

---

### Q12: Tree estimate parameters
**Context.** There is no Bari data on plantable space or existing trees, so these are stated model assumptions, shown in the UI.

- **Q12a: Target green coverage per cell.** A = **15%** (the original doc's example); B = **30%**, from the "3-30-300" urban forestry guideline (Konijnendijk, 2021). Note that 3-30-300 refers to *tree canopy*, while our data measures *mapped green areas*, so the two aren't identical. **Recommendation: A**, with B mentioned in the methodology page.
- **Q12b: Plantable fraction of the deficit** (how much of the missing green area can realistically host trees, given buildings and roads): A = 10%, B = 25%, C = 50%. **Recommendation: B.** This is a pure assumption, so the value is shown and editable.
- **Q12c: Crown area per mature tree:** A = 20 m² (small tree, about 5 m crown), B = **30 m²** (medium tree, about 6 m crown), C = 50 m² (large tree, about 8 m crown). **Recommendation: B.**

---

### Q13: Stack details
| Topic | Options | Recommendation |
|---|---|---|
| Q13a Python dependency manager | uv / pip + venv / poetry | **uv** (fast, lockfile, single tool) |
| Q13b Map library | **MapLibre GL** (WebGL, smooth on phones, vector basemaps) / Leaflet (simpler, more tutorials, slower with many polygons) | **MapLibre GL** via `react-map-gl` |
| Q13c Styling / UI components | **Tailwind CSS** (+ headless components) / MUI / Mantine | **Tailwind CSS**: the easiest way to write a precise responsive layout (FR-50) |
| Q13d Node package manager | npm / pnpm | **npm** (no extra install) |
| Q13e Basemap tiles | CARTO Positron (free, no key) / OSM standard / MapTiler (needs a key) | **CARTO Positron**: a light, neutral basemap that keeps the choropleth readable |

---

### Q14: Product name in the UI
A = "Urban Green Planner"; B = "Green Puglia" (from the mockup); C = something else (tell me). The subtitle would be e.g. *"Priorità di forestazione urbana – Bari"*.

---

### Q15: Who writes code in this repo?
**Context.** This affects the git workflow (branches/PRs vs direct commits), how much setup documentation we need, and whether the phases in Section 8.1 are split between people.

A = only you (with me); B = a team (tell me how many people and who does what: data/GIS, backend, frontend, design/pitch).

---

### Q16: Neighbourhood level for the summary view
| Option | Units | Consequence |
|---|---|---|
| A: **Quartieri** (SIT) | Number unknown until downloaded | Readable names ("Libertà", "Carrassi"). Most likely to match the population `RIONE` values. Needs the SIT download (Q4c). |
| B: Municipi | 5 | Too coarse for prioritising. |
| C: Circoscrizioni (2013) | 9, the old units (replaced by municipi in 2014) | Available now without SIT, but outdated. |

**Recommendation: A**, with C as the fallback if SIT can't be downloaded.

---

### Q17: Sensitivity-check parameters (Section 6.7)
| Parameter | Proposed value | Alternatives |
|---|---|---|
| Q17a Weight spread | about **±5 percentage points** per weight (Dirichlet around the defaults) | ±2.5 (mild) / ±10 (aggressive) |
| Q17b Runs | **1,000** | 500 / 5,000 |
| Q17c "Top-N" | **top 10** neighbourhoods; **top 10%** of cells | top 5 / top 20 |
| Q17d Robust threshold | stays in the top-N in **≥ 80%** of runs | 70% / 90% |

**Recommendation: all the proposed values.** Approve, or change individual ones.

---

### Q18: Which E-PRTR facilities count? (raised in Phase 0)
**Context.** Within 10 km of the municipal boundary, 4 facilities reported NOₓ/PM10 releases at some point: Modugno CCGT (last report **2024**), O-I glass plant in Bari (**2022**), Powerflor Molfetta (2017), Bari thermal plant (2008). A facility stops appearing when it closes **or** when it falls below the E-PRTR reporting threshold, so an old last report doesn't prove the facility is gone.

| Option | Facilities counted | Consequence |
|---|---|---|
| A | Any year, using each facility's latest report | 4, so the indicator is **kept**. Includes a plant not reported since 2008. |
| B | Reported in the last 5 years (2020–2024) | 2, so the indicator is **dropped** (weight redistributed). The facilities can still be shown as a context layer. |
| C | Reported in 2024 only | 1, so the indicator is dropped. |

**Recommendation: B.** Stale reports would put "pressure" where there may be no plant any more. Showing the 2 recent facilities on the map keeps the information visible without scoring it.

### Q19: Limit values for the pollution ratio (raised in Phase 0)
**Context.** The pollution score averages each pollutant's `annual mean / limit`, so the choice of limit changes how much each pollutant counts. Bari 2025 values: NO₂ 15–26, PM10 19–22, PM2.5 11 µg/m³.

| Option | NO₂ | PM10 | PM2.5 | Consequence |
|---|---|---|---|---|
| A: D.Lgs. 155/2010 (in force, used in the ARPA report) | 40 | 40 | 25 | Legally current. Every station is well below 1, so the scores look "fine". |
| B: EU Directive 2024/2881 (limits from 2030) | 20 | 20 | 10 | The upcoming standard. Several Bari stations exceed 1. |
| C: WHO 2021 guidelines | 10 | 15 | 5 | Health-based, the strictest. |

**Recommendation: B.** The index is relative (normalised over the cells anyway), so the absolute level matters less than the balance between pollutants. B is the official EU direction and is closer to current health evidence than A, while staying an EU legal reference.

---

## 11. Changes from the original plan

This section lists where this plan differs from `urban_green_planner_hackathon.md` (the "original") and why. The original file is left unchanged. Section numbers in the "Original" column refer to the original file.

Each change has a reason type:
- **Data** means the real files differ from the catalogue description.
- **Decision** means the user chose it in this planning phase.
- **Method** means it's needed for correct or credible results.
- **Rule** means it comes from a project rule in `CLAUDE.md`.

### 11.1 Data-driven changes

| # | Original | This plan | Why | Type |
|---|---|---|---|---|
| C1 | AIA facilities are an MVP input for industrial pressure (§4.7, §8, §14). E-PRTR is an external source alongside it (§7.1). | AIA is **not usable** as a spatial layer. **Replaced by E-PRTR** facilities within 10 km (NOₓ + PM10 releases). The indicator is dropped if there are fewer than 3 facilities (Q5). | The real CSV is a list of 67 permit **procedures** (type, free text, date, status), with no coordinates and no facility ID, mostly outside Bari. The original itself warned to check this (§4.7). | Data |
| C2 | Population "per civico and age band", assumed ready to join to the grid (§4.6). | Population must be **placed first**: joined to the SIT civic-number points, with rione spreading as fallback. Total = `under67` + `over67`. Zones missing from the data (e.g. Torre a Mare) are excluded (Q4). | The CSVs contain street + number + `RIONE`, **no coordinates**. The SIT civic layer that could solve this timed out from our machine (the user can reach it from a phone). The files turned out to be cumulative age bands, and they cover only about 83% of Bari's residents (Torre a Mare is missing), so coverage gaps must be handled (Q4a). | Data |
| C3 | Air quality from the daily ARPA API, spread to the grid via station coordinates (§4.4–4.5). 30% weight in the example formula (§3). | Pollution = NO₂ + PM10 + PM2.5, using **2025 annual means** from the ARPA annual report (transcribed by hand). Its **weight is lowered from 30 to 20** (Q3, Q10). Caching is mandatory. | Only **5 ARPA stations** are in Bari, so any interpolation gives a smooth gradient with little detail. With 30% weight it would dominate the IPF. The API returns **previous day only** (no history) and **timed out** from our machine. | Data |
| C4 | Green areas "georeferenced in WGS84", CSV/ZIP (§4.1). | Use the **SHP**, which is in **EPSG:32633 (UTM 33N)**. | The CSV has no geometry. The SHP's `.prj` is UTM 33N, not WGS84 as the catalogue states. | Data |
| C5 | Traffic example fields `2026-02-01, …` (§4.2). No cleaning mentioned. | Parse day columns as `d/m/yyyy`, treat trailing `0`s as missing, drop the controller at (0,0), **sum** a controller's detectors (flagging outliers), exclude August 2025 (Q8). | These are real-file issues found during the audit. Summing all detectors of one intersection may count the same vehicles more than once. | Data |
| C6 | Neighbourhood names are used in examples ("Zona Libertà", §3, §11–12), but the spatial unit is a grid only (§3, §15.4). No boundary dataset is listed. | New datasets: **neighbourhood boundaries**, i.e. SIT **quartieri** (fallback: circoscrizioni 2013) (Q16). | The grid alone has no names. Showing "Zona Libertà" requires polygons. See also D3. | Data + Decision |
| C7 | Live data implied ("aggiornamento quotidiano", API, §4.4). | **All data is cached locally and precomputed.** The demo makes no live calls to data sources (NFR-03). | The ARPA API and the SIT host timed out during the audit. A hackathon demo can't depend on them. | Data |

### 11.2 Method changes

| # | Original | This plan | Why | Type |
|---|---|---|---|---|
| M1 | Common CRS "e.g. WGS84/EPSG:4326" (§15.3). | **Compute in EPSG:32633** (metric). Convert to EPSG:4326 only for web output. | Areas (m²), distances (m) and a regular 250/500 m grid need a metric CRS. Computing in degrees distorts them. | Method |
| M2 | No study-area limit. The grid covers "the city" (§3). | **Urban mask**: a cell is analysed if it has ≥ 50 residents or ≥ 30% artificial surface (Q6). | The green-areas dataset covers only **public urban green**. Farmland and peri-urban land would score as "no green" and get falsely high priority. | Method |
| M3 | Sensor data assigned to "the corresponding cell" (§4.3). | Traffic spread to cells with a **distance-decay kernel**. Pollution uses **IDW interpolation**. | There are about 82 traffic points and 5 air stations for thousands of cells. Assigning each point to one cell would leave almost every cell empty. | Method |
| M4 | "Normalise 0–100", method unspecified (§3, §14). | Robust min–max (p5–p95), with a log transform for traffic and population (Q9). | Plain min–max is dominated by outliers (e.g. one very busy intersection). The method must be explicit to be explainable. | Method |
| M5 | Tree estimate uses "superficie utile" and "alberi esistenti" (§11). | **Parametric formula**: target %, plantable fraction, crown area per tree, all in config and shown in the UI. Defaults: 15% / 25% / 30 m² (Q12). | There is **no Bari dataset** for plantable surface or existing trees. The census is only for Copertino. The parameters must therefore be stated assumptions, consistent with the original's own "model estimate" framing (§11, §13). | Method |
| M6 | Priority classes: 4 in §14 (green/yellow/orange/red), 3 in the dashboard mockup (§10: alta/media/bassa). | **4 classes** with **quartile** boundaries (relative priority within Bari) (Q11). | The original is inconsistent. §14 is the MVP spec, and the user confirmed it. Quartiles always give a readable map, and the tool's purpose is to rank. | Method |
| M7 | Explanation "Perché questa zona è prioritaria?" as a requirement (§10, §12). | Explanation built from the **ranked weighted contributions** (top 3 drivers). The backend returns keys + numbers, and the frontend holds the Italian text. | Makes the explanation exactly traceable to the formula (NFR-02) and keeps Italian only in the UI (see R1). | Method + Rule |

### 11.3 Decisions and additions

| # | Original | This plan | Why | Type |
|---|---|---|---|---|
| D1 | Generic "software/app/dashboard" (§1, §9). No stack. | **Python pipeline + FastAPI + React (TypeScript, Vite)**. | User decision. | Decision |
| D2 | Not specified. | Demo on a **laptop exposed via ngrok**. FastAPI also serves the built frontend, so one tunnel is enough. | User decision. Serving everything from one origin avoids a second tunnel and CORS setup. | Decision |
| D3 | Grid only (250 or 500 m, §3, §15.4). | **Grid + neighbourhood summary**. Both 250 m and 500 m grids, 250 m by default (Q7). | User decision (see C6). | Decision |
| D4 | Fixed weights, to be "defined/justified" (§3, §15.6). | Adds **weight sliders** (FR-23, FR-45) and a methodology page (FR-47). | The weights are placeholders. Letting users explore them turns a credibility weakness into a demo feature. | Addition |
| D5 | Mockup has Comune and Anno selectors (§10). | Present but **only Bari / latest data enabled** (FR-48, Could). | The MVP data is a single snapshot for one city (population 2024, green-area SHP 2024). | Scope |
| D6 | Not specified. | Team split, phase "done" criteria, risk table, demo readiness phase. | Needed to organise and track the work. | Addition |
| D7 | Not specified. The mockup is desktop-shaped (§10). | **Responsive, mobile-first UI** (FR-50, NFR-09, NFR-10): bottom sheet on phones, side panel on tablet/desktop. | User decision. The jury may open the ngrok link on phones. | Decision |
| D8 | Weights to be "justified" (§3, §15.6), no validation method. | **Weight sensitivity check** (FR-12, FR-27, FR-51, §6.7): Monte Carlo weight perturbation, rank intervals, robustness badge. | User decision. It shows which priorities hold under different weights and answers the "arbitrary weights" objection with data. | Decision |
| D9 | Timeline oriented around the hackathon day (§15). | No timeline. Coding starts after the planning session is closed. | User decision. | Decision |
| D10 | Not specified. | One developer for now. When the team joins, **per-person git branches with clear ownership** (Q15). | User decision. It stops people interfering with each other's work. | Decision |

### 11.4 Rule-driven changes

| # | Original | This plan | Why | Type |
|---|---|---|---|---|
| R1 | All in Italian. | UI in Italian. Code, docs and commits in English. The original stays in Italian. | Project rule in `CLAUDE.md`. | Rule |

### 11.5 Unchanged
The core concept is kept as-is: the problem framing (mitigation, not "oxygen"), the IPF concept and its example weights as defaults, the Bari MVP, the pipeline order (open data → GIS → normalisation → IPF → tree estimate → dashboard), the explainability goal, the rules against claiming causality and the disclaimers, and the list of future extensions.
