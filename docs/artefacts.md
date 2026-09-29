# Pipeline artefacts (schema v1)

`uv run python -m pipeline build` writes everything below into `data/processed/` from `data/raw/` (+ `data/manual/`). All spatial outputs are in **EPSG:4326**. Computation happens in EPSG:32633, so areas and distances are metric.

| File | Content |
|---|---|
| `cells_250.parquet` / `.geojson` | 250 m grid (default view) |
| `cells_500.parquet` / `.geojson` | 500 m grid |
| `zones.parquet` / `.geojson` | 17 quartieri (SIT), aggregated from the 250 m grid |
| `layer_green_areas.geojson` | public green areas (D1), simplified to 1 m |
| `layer_traffic_controllers.geojson` | traffic controllers with mean daily vehicles |
| `layer_air_stations.geojson` | the 5 ARPA stations in Bari with 2025 annual means |
| `layer_industry.geojson` | E-PRTR facilities within 10 km (context only, see `metadata.inputs.industry`) |
| `metadata.json` | parameters, weights, normalisation bounds, class edges, sensitivity summaries, input stats, sources |

The GeoParquet files are the ones the backend loads. The GeoJSON copies are for inspection and debugging.

## Indicators

Indicator keys (stable, also used as i18n keys): `pollution`, `green_deficit`, `traffic`, `population`, `industry`. The **active** ones are listed in `metadata.indicators.active`. With the current data, `industry` is dropped (only 2 recent facilities, Q18), and its weight is redistributed proportionally (`metadata.weights.effective`).

| Key | Raw column | Raw unit | Normalisation (p5–p95 over analysed cells) |
|---|---|---|---|
| `pollution` | `pollution_ratio` | mean of annual mean / EU 2030 limit over NO₂, PM10, PM2.5 (IDW, power 2) | linear |
| `green_deficit` | `green_share` | share of cell area covered by public green (0–1) | linear, then `100 − score` |
| `traffic` | `traffic_index` | Σ controller mean daily vehicles × Gaussian(d, σ = 300 m), weights < 1% set to 0 (≈ 910 m) | log1p |
| `population` | `density_km2` | residents per km² | log1p |

The bounds used for each indicator are in `metadata.grids.<size>.normalisation.<key>` (`lower`, `upper`, in raw units).

## Cells (`cells_<size>`)

One row per grid cell, clipped to the municipal boundary. Slivers below 10% of a full cell are dropped.

| Column | Type | Description |
|---|---|---|
| `cell_id` | str | `"<size>-<col>-<row>"`, stable across builds |
| `geometry` | Polygon | clipped cell |
| `area_m2`, `area_share` | float | clipped area, and its share of a full cell |
| `zone_id` | int | quartiere containing the cell centroid |
| `zone_covered` | bool | the quartiere is covered by the population data (false: Torre a Mare) |
| `green_m2`, `green_share` | float | public green area inside the cell |
| `artificial_share` | float | share of CORINE class 1 (Uso del Suolo 2011) |
| `residents`, `vulnerable` | float | total residents (under67 + over67), vulnerable (under14 + over67), rounded |
| `density_km2` | float | residents per km² |
| `traffic_index`, `pollution_ratio` | float | raw indicators (see above) |
| `analysed` | bool | in the study area: covered zone AND (density ≥ 800/km² OR artificial ≥ 30%) |
| `score_<key>` | float | 0–100 per active indicator. Null when not analysed. |
| `ipf` | float | Σ wᵢ·scoreᵢ with the default effective weights. Null when not analysed. |
| `contrib_<key>` | float | wᵢ·scoreᵢ in IPF points (sums to `ipf`) |
| `ipf_class` | int | 1..4 = bassa / media / medio-alta / alta (quartiles of analysed cells). 0 = not analysed. |
| `green_deficit_m2`, `plantable_m2`, `trees_new` | float/int | tree estimate (§6.5). Null when not analysed. |
| `rank` | int | 1 = highest IPF among analysed cells |
| `rank_p5`, `rank_p95` | int | 5th–95th percentile rank over the 1,000 weight perturbations |
| `top_n_freq` | float | share of runs in the top 10% of cells |
| `class_stability` | float | share of runs keeping `ipf_class` |
| `robust` | bool | top-N cell: `top_n_freq ≥ 0.8`. Others: `class_stability ≥ 0.8`. |

## Zones (`zones`)

One row per quartiere (17). Zone values are aggregates of the **analysed cells of the 250 m grid**. Scores are **population-weighted means** of the cell scores. So the zone IPF is the population-weighted mean of the cell IPFs, and it stays linear in the weights (the backend recomputes it as `Σ wᵢ·score_<key>`).

| Column | Description |
|---|---|
| `zone_id`, `name`, `rione` | id (1–17, Roman numeral of the quartiere), display name (Italian), population RIONE |
| `covered`, `analysed` | covered by the population data / has analysed cells (Torre a Mare: both false, all values null) |
| `cells_analysed`, `analysed_area_m2` | number and area of analysed cells |
| `residents`, `vulnerable`, `density_km2` | sums over analysed cells, and density over their area |
| `green_m2`, `green_share` | public green in analysed cells |
| `pollution_ratio`, `traffic_index` | population-weighted means of the raw values |
| `score_<key>`, `ipf`, `contrib_<key>` | as for cells |
| `ipf_class` | quartiles over the 16 analysed zones |
| `green_deficit_m2`, `plantable_m2`, `trees_new` | sums over analysed cells |
| `rank`, `rank_p5`, `rank_p95`, `top_n_freq`, `class_stability`, `robust` | as for cells, with top N = 10 zones |

## Layers

- `layer_traffic_controllers`: `device_db`, `device_type`, `device_id`, `code`, `name`, `n_detectors`, `vehicles_day` (null = no valid data), `detectors_with_data`, `has_data`, `suspicious_total`.
- `layer_air_stations`: `id_station`, `station`, `no2_ugm3`, `pm10_ugm3`, `pm25_ugm3`, `pollution_ratio`, `pollutants_measured`.
- `layer_industry`: `facility_id`, `name`, `city`, `last_reporting_year`, `nox_kg`, `pm10_kg` (kg/year, latest report), `recent` (counts under Q18).
- `layer_green_areas`: `green_id`, `nome_area`, `type_id`.

## `metadata.json`

| Key | Content |
|---|---|
| `schema_version`, `city`, `built_at` | |
| `indicators` | `all`, `active`, `dropped` (key → reason), `raw_column` |
| `weights` | `configured_pp` (config, percentage points), `effective` (active, sum 1) |
| `classes`, `trees`, `urban_mask`, `normalisation`, `grid` | parameters from the config |
| `grids.<size>` | `cells`, `cells_analysed`, `normalisation` bounds, `class_edges`, `sensitivity` summary |
| `zones` | `zones_analysed`, `class_edges`, `sensitivity` summary |
| `…sensitivity` summary | `n`, `top_n`, `spearman_mean`, `spearman_p5`, `top_n_overlap_mean`/`_min`, `robust_share`, `robust_share_top_n`, `one_at_a_time` (list: `indicator`, `delta_pp`, `weight`, `top_n_kept`, `spearman`) |
| `sensitivity` | run parameters + `dirichlet_alpha0` |
| `inputs` | `population` (address match stats), `traffic` (months used, controllers), `air`, `industry` |
| `sources` | per raw source: status, number of files, latest download time, URLs (from the manifest) |
| `disclaimers` | keys for the UI (texts live in the frontend): `relative_priority`, `model_estimate`, `arpa_validation`, `no_causality`, `public_green_only`, `population_coverage` |
