import { createContext, useContext } from 'react'
import type { GridSize, IndicatorKey, LayerKey, Level, Metadata, WeightsPp } from './api/types'
import type { MapTab } from './i18n/it'

export interface Selection {
  level: Level
  id: string
}

export type PanelTab = 'detail' | 'weights'

/** What the map shows: neighbourhoods, or one of the two grids. */
export type View = 'zone' | GridSize

export interface AppState {
  meta: Metadata
  active: IndicatorKey[]
  defaults: WeightsPp
  view: View
  setView: (v: View) => void
  grid: GridSize
  level: Level
  tab: MapTab
  setTab: (t: MapTab) => void
  layers: Set<LayerKey>
  toggleLayer: (l: LayerKey) => void
  /** Slider values (live). */
  weights: WeightsPp
  setWeights: (w: WeightsPp) => void
  resetWeights: () => void
  /** `weights` query value after debouncing (null = defaults, or invalid weights). */
  wParam: string | null
  weightsValid: boolean
  selection: Selection | null
  select: (s: Selection | null) => void
  simulating: boolean
  setSimulating: (b: boolean) => void
  panelTab: PanelTab
  setPanelTab: (t: PanelTab) => void
  methodologyOpen: boolean
  setMethodologyOpen: (b: boolean) => void
  /** Last request to zoom the map to an item (ranking/list clicks); `n` makes each request unique. */
  flyRequest: (Selection & { n: number; zoom: boolean }) | null
  /** Select an item and move the map to it (zooming in, or only panning with `zoom: false`). */
  selectAndFly: (s: Selection, zoom?: boolean) => void
}

export const AppContext = createContext<AppState | null>(null)

export function useApp(): AppState {
  const v = useContext(AppContext)
  if (!v) throw new Error('useApp outside AppProvider')
  return v
}
