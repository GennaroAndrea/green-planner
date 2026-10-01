// Types mirroring backend/schemas.py and docs/artefacts.md.
import type { FeatureCollection, Geometry } from 'geojson'

export type IndicatorKey = 'pollution' | 'green_deficit' | 'traffic' | 'population' | 'industry'
export type Level = 'zone' | 'cell'
export type GridSize = 50 | 250 | 500
export type ClassKey = 'bassa' | 'media' | 'medio_alta' | 'alta'
export type LayerKey = 'green' | 'traffic' | 'air' | 'industry'

/** Weights in percentage points (0–100 each), keyed by active indicator. */
export type WeightsPp = Partial<Record<IndicatorKey, number>>

export interface SensitivitySummary {
  n: number
  top_n: number
  spearman_mean: number
  spearman_p5: number
  top_n_overlap_mean: number
  top_n_overlap_min: number
  robust_share: number
  robust_share_top_n: number
  one_at_a_time: {
    indicator: IndicatorKey
    delta_pp: number
    weight: number
    top_n_kept: number
    top_n: number
    spearman: number
  }[]
}

export interface SourceInfo {
  status: string
  files?: number
  downloaded_at?: string | null
  urls?: string[] | null
}

export interface Metadata {
  schema_version: number
  city: string
  built_at: string
  indicators: {
    all: IndicatorKey[]
    active: IndicatorKey[]
    dropped: Partial<Record<IndicatorKey, string>>
    raw_column: Partial<Record<IndicatorKey, string>>
  }
  weights: { configured_pp: Record<IndicatorKey, number>; effective: WeightsPp }
  classes: { count: number; keys: ClassKey[]; method: string }
  disclaimers: string[]
  layers: LayerKey[]
  trees: { target_green_share: number; plantable_fraction: number; crown_area_m2: number }
  urban_mask: { min_resident_density_km2: number; min_artificial_share: number; min_cell_area_share: number }
  normalisation: { method: string; lower_percentile: number; upper_percentile: number; log_transform: IndicatorKey[] }
  grid: { cell_sizes_m: GridSize[]; default_cell_size_m: GridSize }
  grids: Record<string, {
    cell_size_m: number
    cells: number
    cells_analysed: number
    residents_in_analysed_cells: number
    normalisation: Partial<Record<IndicatorKey, { lower: number; upper: number; log: boolean }>>
    class_edges: number[]
    sensitivity: SensitivitySummary
  }>
  zones: { zones: number; zones_analysed: number; class_edges: number[]; sensitivity: SensitivitySummary }
  sensitivity: { runs: number; spread_pp: number; top_n_zones: number; top_share_cells: number; robust_threshold: number; one_at_a_time_delta_pp: number }
  inputs: {
    population: { residents_total: number; match_rate: number; residents_spread_by_zone: number }
    traffic: { months_used: string[]; months_excluded: string[]; controllers_positioned: number; controllers_with_data: number; kernel_sigma_m: number }
    air: { reference_year: number; stations: number; limit_values_ugm3: Record<string, number>; idw_power: number }
    industry: { facilities_in_radius: number; facilities_recent: number; last_reporting_year: number; active: boolean }
    vegetation: {
      period: string
      scenes: string[]
      ndvi_threshold: number
      valid_pixel_share: number
      cells_without_vegetation: number
      nonresidential_cells: number
    }
  }
  sources: Record<string, SourceInfo>
}

/** Properties of a map feature (cells and zones share most of them). */
export interface MapProps {
  cell_id?: string
  zone_id: number | null
  name?: string
  analysed: boolean
  ipf: number | null
  ipf_class: number
  rank: number | null
  robust: boolean | null
  trees_new?: number | null
  [score: `score_${string}`]: number | null
}

export type MapCollection = FeatureCollection<Geometry, MapProps>

export interface Weights {
  weights: WeightsPp
  is_default: boolean
}

export interface IndicatorDetail {
  key: IndicatorKey
  raw_column: string
  raw_value: number | null
  score: number | null
  weight: number
  contribution: number | null
}

export interface Driver {
  indicator: IndicatorKey
  score: number
  weight: number
  contribution: number
}

export interface Trees {
  green_deficit_m2: number | null
  plantable_m2: number | null
  trees_new: number | null
  /** Zones only: trees estimated in non-residential cells, not in `trees_new` (Q50). */
  trees_new_nonres: number | null
  target_green_share: number
  trees_for_target: number | null
  cells_below_target: number | null
}

export interface ItemSensitivity {
  applicable: boolean
  top_n: number
  rank_p5: number | null
  rank_p95: number | null
  top_n_freq: number | null
  class_stability: number | null
  robust: boolean | null
}

export interface Detail extends Weights {
  level: Level
  id: string
  grid: GridSize | null
  analysed: boolean
  ipf: number | null
  ipf_class: number
  class_key: ClassKey | null
  rank: number | null
  ranked_items: number
  indicators: IndicatorDetail[]
  top_drivers: Driver[]
  trees: Trees
  sensitivity: ItemSensitivity
  stats: {
    residents?: number
    vulnerable?: number
    density_km2?: number
    green_m2?: number
    green_share?: number
    veg_m2?: number
    veg_share?: number
    residential?: boolean
    area_m2?: number
    cells_analysed?: number
    cells_residential?: number
    analysed_area_m2?: number
    [key: string]: unknown
  }
  zone: { zone_id: number | null; name: string | null } | null
}

export interface RankingItem {
  id: string
  name: string | null
  zone_id: number | null
  ipf: number
  ipf_class: number
  rank: number
  rank_p5: number | null
  rank_p95: number | null
  top_n_freq: number | null
  robust: boolean | null
  trees_new: number | null
  trees_new_nonres: number | null
  residential: boolean | null
  residents: number | null
  contributions: WeightsPp
}

export interface Ranking extends Weights {
  level: Level
  grid: GridSize | null
  total: number
  items: RankingItem[]
}

export interface Sensitivity extends Weights {
  level: Level
  grid: GridSize | null
  applicable: boolean
  parameters: Record<string, unknown>
  summary: SensitivitySummary | null
}

export interface SimulationState {
  veg_m2: number
  veg_share: number
  score_green_deficit: number
  ipf: number
  ipf_class: number
  class_key: ClassKey
  rank: number
}

export interface Simulation extends Weights {
  level: Level
  id: string
  grid: GridSize | null
  trees: number
  years: number | null
  growth_share: number | null
  maturity_years: number | null
  years_to_target: number | null
  years_to_class_change: number | null
  added_veg_m2: number
  crown_area_m2: number
  target_green_share: number
  trees_estimate: number | null
  trees_for_target: number
  before: SimulationState
  after: SimulationState
}

/** GET /api/chat/status (backend/chat_auth.py ChatStatus). */
export interface ChatStatus {
  available: boolean
  authenticated: boolean
  expires_at: string | null
  budget_usd: number | null
  spent_usd: number | null
}

/** GET /api/chat/history item. */
export interface ChatExchange {
  question: string
  answer: string
  unverified: string[]
}
