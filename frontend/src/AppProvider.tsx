import { useMemo, useState, type ReactNode } from 'react'
import { weightsParam } from './api/client'
import type { LayerKey, Metadata, WeightsPp } from './api/types'
import type { MapTab } from './i18n/it'
import { useDebounced } from './lib/hooks'
import { AppContext, type AppState, type PanelTab, type Selection, type View } from './state'

export function AppProvider({ meta, children }: { meta: Metadata; children: ReactNode }) {
  const active = meta.indicators.active
  const defaults = useMemo(
    () => Object.fromEntries(active.map((k) => [k, meta.weights.configured_pp[k]])) as WeightsPp,
    [meta, active],
  )
  const [view, setViewState] = useState<View>('zone')
  const [tab, setTab] = useState<MapTab>('priority')
  const [layers, setLayers] = useState<Set<LayerKey>>(new Set())
  const [weights, setWeights] = useState<WeightsPp>(defaults)
  const [selection, setSelection] = useState<Selection | null>(null)
  const [simulating, setSimulating] = useState(false)
  const [panelTab, setPanelTab] = useState<PanelTab>('detail')
  const [methodologyOpen, setMethodologyOpen] = useState(false)
  const [flyRequest, setFlyRequest] = useState<AppState['flyRequest']>(null)

  const debounced = useDebounced(weights, 350)
  const weightsValid = active.some((k) => (weights[k] ?? 0) > 0)
  const debouncedValid = active.some((k) => (debounced[k] ?? 0) > 0)
  // Invalid weights (all 0) keep the last valid scenario on screen, next to the warning.
  const [wParam, setWParam] = useState<string | null>(null)
  const nextParam = debouncedValid ? weightsParam(debounced, defaults, active) : wParam
  if (nextParam !== wParam) setWParam(nextParam)

  const select = (s: Selection | null) => {
    setSelection(s)
    setSimulating(false)
    if (s) setPanelTab('detail')
  }

  const value: AppState = {
    meta,
    active,
    defaults,
    view,
    setView: (v) => {
      setViewState(v)
      setSelection(null)
      setSimulating(false)
    },
    grid: view === 'zone' ? meta.grid.default_cell_size_m : view,
    level: view === 'zone' ? 'zone' : 'cell',
    tab,
    setTab,
    layers,
    toggleLayer: (l) =>
      setLayers((prev) => {
        const next = new Set(prev)
        if (next.has(l)) next.delete(l)
        else next.add(l)
        return next
      }),
    weights,
    setWeights,
    resetWeights: () => setWeights(defaults),
    wParam,
    weightsValid,
    selection,
    select,
    simulating,
    setSimulating,
    panelTab,
    setPanelTab,
    methodologyOpen,
    setMethodologyOpen,
    flyRequest,
    selectAndFly: (s, zoom = true) => {
      select(s)
      setFlyRequest((prev) => ({ ...s, zoom, n: (prev?.n ?? 0) + 1 }))
    },
  }
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}
