# Phase 3 (frontend): review and handoff

- **Date**: 2026-09-29
- **Phase**: 3, frontend (plan §8, items 3.1–3.6; 3.0 was done at the end of Phase 2)
- **Status**: done. Q45–Q48 were raised and decided during this phase. After the review, the Phase 1 model issues (Q33) were closed with Q49–Q50 (A.6), which changed the results.
- **Next phase**: 4, demo readiness

---

## Part A: Review

### A.1 What was built

All code is in `frontend/src/`. The stack is the one decided in Q13: React 19 + TypeScript + Vite 8, MapLibre GL 6 via `react-map-gl`, Tailwind CSS v4 and Headless UI 2. All Italian text is in `i18n/it.ts`.

| Plan item | Result | Where |
|---|---|---|
| 3.1 Responsive layout, mobile-first | Header (placeholder name, Q41) above the map. Below 640 px: a draggable **bottom sheet** (peek / half / full). 640–1024 px: a **collapsible** side panel (360 px). Above 1024 px: a **fixed** side panel (420 px). Tapping a zone opens the sheet or panel. On phones the tapped zone is panned into view above the sheet. | `App.tsx`, `components/BottomSheet.tsx`, `components/Panel.tsx` |
| 3.2 Choropleth + legend + view toggle | **Quartieri / Celle 250 m / Celle 500 m** switch. Indicator tabs *Priorità, Aria, Traffico, Verde, Popolazione, Industria* (FR-52, Q45): *Priorità* shows the classes, the indicator tabs a 0–100 ramp. The legend shows class counts computed from the GeoJSON (FR-41), collapses to a button on phones, and flags custom-weight scenarios. Not-analysed areas are grey, and clicking one opens a popup saying why. | `components/MapView.tsx`, `components/MapOverlay.tsx`, `components/MapPopup.tsx` |
| 3.3 Detail panel | Title, IPF, class, "N° su M", robustness badge + rank interval (FR-51), "Perché questa zona è prioritaria?" (3 drivers in the methodology §11 sentence form, each with its raw value in plain words), indicator lollipops with weights, contribution bar, green/trees box (Q42: cells "x% → 15%", zones "mean % · N celle su M sotto il 15%"), residents/density/area, and the "Simula intervento" button. Without a selection it shows an intro and the current top 5. | `components/DetailPanel.tsx`, `i18n/it.ts` (`driverSentence`, `rawValueText`) |
| (FR-53) Simulator | Opens from the card (Q44). It has a trees slider with markers for the model estimate and the 15% target, quick buttons (0 / estimate / target), a before/after decorative sketch, green share, IPF (with delta), class and rank before/after, and the Q37 disclaimer. | `components/Simulator.tsx` |
| 3.4 Context layers | A popover with checkboxes: green areas (polygons), traffic controllers (sized by vehicles/day, hollow = no data), ARPA stations, E-PRTR facilities (filled = reported 2020–2024). Every layer has a popup. The *Industria* tab forces the facilities layer on and shows the no-causality text. | `components/MapView.tsx`, `components/MapOverlay.tsx`, `components/MapPopup.tsx` |
| 3.5 Weight sliders + "Verifica robustezza" | 4 sliders (0–100, step 5), each showing its effective share (Q36), plus "Ripristina". Changes are debounced 350 ms, then the map and ranking refetch with `weights=`. All-zero weights show a warning and keep the last valid scenario. The industry exclusion note is shown. "Verifica robustezza" fetches `/api/sensitivity` for the current level and weights and summarises it in plain Italian (or "non applicabile"). | `components/WeightsRanking.tsx`, `AppProvider.tsx` |
| 3.6 Ranking, methodology modal, disclaimers | Ranking for the current view (quartieri or cells), sortable by priority/trees/residents, with the prototype's split contribution bars, robustness badge and interval. Cells show 20 at a time ("Mostra altre"). **CSV export** (FR-49, Q48) uses `;`, decimal comma and a UTF-8 BOM, for Italian Excel. The **"Metodologia e fonti"** modal covers formula, weights, indicators, study area, classes, tree parameters (read-only, Q43), the robustness table (zones / 250 m / 500 m), sources with licences and download dates, limitations and all disclaimers. A disclaimer line is always visible (panel/sheet footer, or the legend when the tablet panel is collapsed). | `components/WeightsRanking.tsx`, `components/Methodology.tsx`, `components/Panel.tsx` |
| (FR-48) Comune/year selectors | Headless listboxes in the header. Only Bari / "Dati 2026" are enabled; Copertino, Lecce, 2025 and 2024 show "prossimamente" (Q48). | `components/Header.tsx` |
| (NFR-11) Themes | Light and dark tokens in `index.css`. The theme follows `prefers-color-scheme`, and the header toggle's choice is stored in `localStorage`. The basemap switches between CARTO Positron and Dark Matter. Sliders, listboxes, popovers, MapLibre controls and popups are all styled for both themes (no native `<select>`). | `index.css`, `lib/hooks.ts` (`useTheme`) |
| (docs) | Decisions Q45–Q48, Phase 3 status (plan §8), methodology §8 colours + change log (Italian), README frontend section | |

### A.2 Results and how they were verified

- **Build and lint**: `npm run build` (tsc + vite) and `npm run lint` (oxlint) are clean. `uv run pytest`: 68 passed (the backend is unchanged), and `ruff check` is clean.
- **Visual and flow checks** in headless Chrome (system Chrome driven by `playwright-core`, installed in a scratch folder, not in the project) at 360×740, 390×844, 820×1180, 1366×768 and 1440×900, in light and dark. **No horizontal scroll** at any width, and **no console errors**. Checked flows:
  - map → tap zone → card → simulator (phone and desktop);
  - weights → ranking;
  - cells view → cell card → simulator;
  - layers + popups, the Industria tab, the methodology modal.
- **Numbers match the API and the methodology**:
  - Libertà: 86,3, alta, 4° su 16, "tra 2° e 5° posto", 20,9% · 14 celle su 29, ~601 / 2.432 alberi;
  - simulator with 601 trees: 85,1, medio-alta, 5° (as in methodology §10.1);
  - top cell (Madonnella): 99,4, and its simulator with 208 trees reaches exactly 15,0%;
  - 250 m legend counts: 282 / 282 / 281 / 282 + 879 not analysed (= 2,006 cells).
- **Custom weights** (pollution 50, green 30, traffic 0, population 20): one debounced request each for `/api/zones` and `/api/ranking`. "Verifica robustezza" shows correlation 1,00 and 100% robust, matching `/api/sensitivity` (Spearman 0.9987, robust share 1.0). With all weights at 0, **no request is sent** and the warning is shown.
- **Production build served by the backend on :8000**: the map and legend are ready in **about 1.7 s** locally (1366×768, including the CARTO basemap from the internet).
  - Main JS: 423 KB gzipped (MapLibre included).
  - MapLibre worker: 144 KB gzipped.
  - CSS: 18 KB gzipped.
  - ngrok is not measured yet (Phase 4).

### A.3 Deviations from the plan and new decisions

- **Q45**: the industry tab is labelled "Industria", not "AIA" (the data is E-PRTR).
- **Q46**: class colours are the darkest 4 of the prototype palette. Methodology §8 was updated.
- **Q47**: fonts are bundled (`@fontsource`: Inter, Source Serif 4, IBM Plex Mono).
- **Q48**: FR-48 (disabled selectors) and FR-49 (CSV export) are included.
- **Recharts isn't installed** (it is in the Q13 stack). Every chart in the prototype is a simple bar or lollipop, drawn with plain elements. Add Recharts only if a real chart is needed.
- **No vitest tests** (optional in §7.1). The tested logic lives in the backend. The frontend was verified with the browser checks above.
- **Technical choices** (not method; they can be changed):
  - **MapLibre 6 worker**: MapLibre looks for `maplibre-gl-worker.mjs` next to its own module, which bundling breaks. The worker is therefore imported with `?worker&url` and passed to `setWorkerUrl`, with `worker.format: 'es'` in `vite.config.ts`.
  - **Choropleth layer order**: drawn above the basemap's roads and buildings, below the labels (the first symbol layer after the last non-symbol layer). The opacity is 0.72 for zones and 0.78 for cells.
  - **Choropleth source keyed by level**: `react-map-gl` doesn't update `promoteId` on an existing source. Without the key, hovering one cell highlighted a whole quartiere.
  - **Map interaction**: the choropleth is not keyboard-navigable. The ranking list gives keyboard access to every item, and `selectAndFly` zooms the map to it.
  - **Robustness wording**: the rank interval is shown as "tra X° e Y° posto variando i pesi di ±5 punti" (p5–p95).
  - **"Verifica robustezza" headline**: "stabile" when the mean Spearman is ≥ 0.9, "abbastanza stabile" when ≥ 0.75, otherwise "dipende molto dai pesi". These thresholds are wording only, not a model rule.
  - **Driver adjectives** ("elevato / medio / basso"): score ≥ 67 / ≥ 34 / below. Wording only, not a model rule.
  - **Source licences** in the modal come from the catalogues:
    - Comune di Bari datasets: CC BY; population: CC BY-SA;
    - SIT (Civilario Unico Comunale, the same files we download): CC BY;
    - Uso del Suolo 2011: IODL 2.0;
    - ARPA stations: CC BY 4.0;
    - E-PRTR: CC BY 4.0, © EEA (EEA SDI catalogue).

### A.4 Process notes

- 4 questions were asked before coding: the industry tab label, the class colours, fonts, and the Could items.
- **Bugs found and fixed through the browser checks**, not by reading the code:
  - MapLibre worker not loading (blank map);
  - basemap buildings painted over the choropleth;
  - a zoom expression MapLibre rejected;
  - hovering a cell highlighting a whole quartiere;
  - the icon-only methodology button with no accessible name on phones;
  - all-zero weights silently falling back to the defaults.
- Screenshot-driven checks were worth it: most of these bugs don't show in `tsc` or lint.

### A.5 Known issues and open points

1. ~~Licences of SIT and E-PRTR~~ **Solved**: SIT is CC BY (Comune di Bari portal, dataset "Civilario Unico Comunale"), E-PRTR is CC BY 4.0 (EEA catalogue). Both are now in the modal.
2. ~~Population reference date~~ **Solved**: "al 6 gennaio 2024" is confirmed by the Comune di Bari portal description. It is now in the modal and in methodology §3.
3. ~~Phase 1 model issues~~ **Solved by Q49–Q50** (A.6).
4. **Industria tab**: the Molfetta facility (Powerflor) is outside the initial view. The tab doesn't zoom out to show all 4 facilities; the legend explains the 10 km radius.
5. **Bundle size**: the main chunk is 1.49 MB raw / 423 KB gzipped, so Vite prints its > 500 kB warning. MapLibre could be split into its own chunk for caching, but the total download is the same. Measure over ngrok in Phase 4 before optimising.
6. **Not tested**:
   - real touch devices (sheet drag, pinch zoom) and landscape phones (NFR-10, Phase 4);
   - Firefox and Safari (the slider styling has Firefox rules; Safari is untested).
7. **Basemap tiles** come from CARTO (internet required, as planned).

### A.6 Addendum: satellite vegetation (Q49) and non-residential cells (Q50)

The user closed Q33 after the Phase 3 review. The questions were asked with data before implementation.

**What changed:**

| Area | Change | Where |
|---|---|---|
| Download | New source `sentinel2_ndvi`: STAC search (Planetary Computer, anonymous SAS token), tile 33TXF, Jun–Aug 2025, cloud < 1%, one scene per date (19). Per scene: NDVI from B04/B08, invalid SCL classes (no data, saturated, shadow, water, clouds, cirrus) masked; then the per-pixel median. Cached as an 8.3 MB int16 GeoTIFF with the scene ids and dates in the manifest. | `pipeline/satellite.py`, `pipeline/download.py`, `config/bari.yaml` (`sources.sentinel2_ndvi`, `vegetation`) |
| Build | `veg_m2` / `veg_share` / `veg_valid_share` per cell: vegetated pixels (NDVI ≥ 0.30) whose centre is in the cell. `veg_share` is the green-deficit raw column, and the tree estimate uses `veg_m2`. `residential` = rounded residents > 0. Zones: `veg_*`, `cells_residential`; `trees_new` / `green_deficit_m2` / `plantable_m2` over residential cells only, plus `trees_new_nonres`. Metadata: `vegetation`, `inputs.vegetation`; the disclaimer `public_green_only` became `satellite_vegetation`. | `pipeline/build.py`, `docs/artefacts.md` |
| Backend | Stats include `veg_*`, `residential` / `cells_residential`. `trees.trees_new_nonres` (zones). Ranking items carry `trees_new_nonres` (zones) and `residential` (cells). `cells_below_target` counts residential cells on `veg_share`. Simulator: vegetation fields (`veg_m2`, `veg_share`, `added_veg_m2`), zone trees spread over residential cells only. | `backend/store.py`, `backend/main.py`, `backend/schemas.py` |
| UI | "Vegetazione" wording in the card, simulator, driver sentences, map legend and modal. Zone card: "Vegetazione media x% · N celle abitate su M sotto il 15%" and "+ N in aree non residenziali". Cell card: "Area non residenziale" notice; public green shown as a descriptive stat. Ranking: "+N" non-residential trees (zones), "non residenziale" tag (cells). CSV gets the matching columns. Modal: Sentinel-2 source (Copernicus, free and open), new indicator text, non-residential paragraph, updated limits. Also: 4-digit numbers are now grouped ("1.678"). | `frontend/src/` |
| Docs | Q49, Q50, D11, Q33 marked resolved (plan). Methodology §1, §3, §4.4, §5.1, §6, §8–§10.1, §12–§16 rewritten with the new numbers (Italian). | |

**Verified results** (rebuilt artefacts, default weights):
- Cells with the maximum green deficit: **117 of 1,127 (10%)**, previously 552 (49%). Valid NDVI covers 99.97% of the analysed cells' pixels. Bounds: 0% → 100 deficit, ≥ 25.6% → 0.
- Why not the public green: the Comune's polygons are often not vegetated from above. Tree-lined-street polygons have median NDVI 0.11 (5% of pixels ≥ 0.30), cemeteries 0.16, sports fields 0.13. Spearman between public green share and vegetation share over analysed cells: 0.00.
- Zones: Madonnella 97,0, Murat 95,9, San Nicola 95,2, Libertà 91,5 (the four "alta"), then San Pasquale 86,2. Mean Spearman 1,00 (0.9972). 15 of 16 zones robust; the one "sensitive" zone is San Paolo, 10th, on the top-10 border. In the one-at-a-time test the zone top 10 changes by at most one zone.
- Cells 250 m: Spearman 0.99, 75% robust (90% of the top 10%). New class edges: 250 m 46,4 / 60,2 / 75,6; zones 70,3 / 79,3 / 87,5.
- Trees: **45,278** (was 54,855), of which **12,345 in 302 non-residential cells**. Zone totals: 32,933.
- Libertà:
  - 1,678 trees + 113 in non-residential areas; 25 of 27 residential cells below 15%;
  - simulator with 1,678 trees: 87,1, medio-alta, still 4th;
  - with 6,763 trees (the 15% target): 73,9, media, 11th.
- Tests: `uv run pytest` 70 passed. There's a new `vegetation_area` unit test on a synthetic raster. The API fixture now has non-residential cells and a zone without deficit. `ruff` is clean, and `npm run build` / `lint` are clean.
- Browser (production build on :8000): the zone card, a non-residential cell card, the cell ranking and the modal on a phone (all new texts present, no horizontal scroll) show no console errors.

**Notes and known issues:**
- `pipeline download` now needs `rasterio` (added to `pyproject.toml`) and internet access to Planetary Computer. The composite is cached, so `pipeline build` works offline.
- A cell's population score can be > 0 while its card says "Residenti 0". Residents spread by quartiere (Q23) can leave e.g. 0.4 residents in a cell. The build uses the fractional value for density (e.g. "8 ab./km²"), but the rounded one for `residential` and the displayed count.
- Sorting cells by "Alberi" gives many ties at 78 (full cells without vegetation).
- The 500 m grid has 30 non-residential cells. Its trees aren't used for zone totals (zones come from 250 m).

---

## Part B: Handoff for the next agent (Phase 4, demo readiness)

### B.1 Read first
1. This file, then `docs/requirements_and_plan.md` §8 Phase 4, NFR-04 and NFR-10, and §10.0 (up to Q48).
2. `CLAUDE.md` (rules: git, language, ask-don't-guess, handoffs).
3. `docs/methodology.md` §13 (results table) for the demo narrative, and §14 (limitations) for jury questions.

### B.2 Current state (how to run)
```bash
uv run python -m pipeline build                  # if data/processed/ is missing (about 30 s)
(cd frontend && npm install && npm run build)    # frontend/dist
uv run uvicorn backend.main:app                  # app + API on :8000
# demo (user's setup): the app on port 8080, exposed through ngrok
uv run uvicorn backend.main:app --port 8080
ngrok http 8080 --url https://green-planner.ngrok.io
# development: uvicorn --reload on :8000 + (cd frontend && npm run dev) on :5173
```

### B.3 Code map (frontend)
- `App.tsx`: loads the metadata, then the layout (header, map, overlays, panel/sheet, modal) and the insets used for map fitting.
- `state.ts` + `AppProvider.tsx`: global UI state:
  - view (`'zone' | 250 | 500`), map tab, layers, weights (live + debounced `wParam`);
  - selection, simulator flag, panel tab, methodology modal;
  - `selectAndFly` (zoom, or pan only on phones).
- `api/client.ts` + `api/types.ts`: URL builders and types mirroring `backend/schemas.py`.
- `lib/hooks.ts`: `useFetch` (keeps the previous data while loading), `useDebounced`, `useBreakpoint`, `useTheme`.
- `i18n/it.ts`: **all** Italian strings (labels, disclaimers, driver sentences).
- `lib/colors.ts`: class colours (Q46), the score ramp and the indicator colours (prototype).

### B.4 Implementation notes for Phase 4
- **4.1 `make demo` / script**: build the frontend, run uvicorn on **port 8080** (no `--reload`), then start ngrok with `ngrok http 8080 --url https://green-planner.ngrok.io` (the user's reserved URL). The dev setup stays on :8000 (Vite proxies `/api` there). The backend already serves `frontend/dist` at `/` and gzips responses of 1 kB or more.
- **4.2 checks**:
  - time the first load over ngrok (NFR-04: < 3 s);
  - check the sheet drag and pinch zoom on a real phone, in portrait and landscape;
  - check Safari (iOS) if anyone on the jury uses an iPhone.
- **Headless checks**: the screenshot approach in A.2 is quick to repeat. Install `playwright-core` in a scratch folder, launch `/usr/bin/google-chrome` with `--use-gl=swiftshader --enable-unsafe-swiftshader`, and use `isMobile`/`hasTouch` for phone widths.
- **4.3 demo narrative** (numbers verified in this phase):
  - Madonnella: 1st, 97,0, "sempre 1° posto", 1,9% vegetation;
  - Libertà: 4th, 91,5; drivers green deficit (94) / density / traffic; 3,0% vegetation although the Comune maps 20,9% public green (a good story for why satellite data); the simulator with its 1,678 estimated trees gives 87,1 and medio-alta;
  - a low zone for contrast: Loseto, 16th (55,5), or Carbonara, 15th (pollution score 4);
  - non-residential areas: Palese – Macchie has 1,776 trees in inhabited cells and 3,940 more in non-residential ones (e.g. the airport area);
  - re-check any weight-scenario numbers before the demo: they changed with Q49.

### B.5 Open questions to ask the user
1. The final product name (Q14) is still open. The UI uses "Urban Green Planner" (Q41).

### B.6 Pitfalls
- Never run git commands other than `git status` / `git diff`.
- After changing `vite.config.ts` or the dependencies, restart the dev server with `--force`. Otherwise Vite serves stale pre-bundled deps ("504 Outdated Optimize Dep").
- Don't remove the `?worker&url` import in `MapView.tsx`: without it the map stays blank.
- If you add a new source to the map, give it a `key` if any of its non-data props (e.g. `promoteId`) can change.
- Keep every new UI string in `i18n/it.ts`, in Italian.
- `pipeline download --force` rebuilds the satellite composite (19 scenes, a few minutes). The Planetary Computer SAS token is fetched anonymously on each run.
