import '@fontsource-variable/inter'
import '@fontsource-variable/source-serif-4'
import '@fontsource/ibm-plex-mono/400.css'
import { useMemo, useState } from 'react'
import { api } from './api/client'
import type { MapCollection, Metadata } from './api/types'
import BottomSheet, { PEEK_PX, type SheetSnap } from './components/BottomSheet'
import Header from './components/Header'
import { LayersButton, Legend, MapTabs, ViewSwitch } from './components/MapOverlay'
import MapView from './components/MapView'
import Methodology from './components/Methodology'
import { DisclaimerBar, PanelBody, PanelTabs } from './components/Panel'
import { Icon, Spinner } from './components/ui'
import { cx, ICONS } from './lib/ui'
import { APP_NAME, ERRORS } from './i18n/it'
import { useBreakpoint, useFetch, useMediaQuery, useTheme } from './lib/hooks'
import { AppProvider } from './AppProvider'
import { useApp } from './state'

export default function App() {
  const [dark, toggleTheme] = useTheme()
  const meta = useFetch<Metadata>(api.metadata())

  if (!meta.data) {
    return (
      <main className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <p className="font-serif text-2xl">{APP_NAME}</p>
        {meta.error ? <p className="text-sm text-warn">{ERRORS.load}</p> : <Spinner />}
      </main>
    )
  }
  return (
    <AppProvider meta={meta.data}>
      <Layout dark={dark} toggleTheme={toggleTheme} />
    </AppProvider>
  )
}

function Layout({ dark, toggleTheme }: { dark: boolean; toggleTheme: () => void }) {
  const app = useApp()
  const bp = useBreakpoint()
  const phone = bp === 'phone'
  // Landscape phones get the tablet layout, but the open legend would cover most of the map
  const short = useMediaQuery('(max-height: 499px)')
  const [snap, setSnap] = useState<SheetSnap>('peek')
  const [collapsedPref, setCollapsed] = useState(false)
  const collapsed = bp === 'tablet' && collapsedPref // only the tablet panel collapses

  const insets = useMemo(
    () =>
      phone
        ? { top: 150, bottom: PEEK_PX, bottomOpen: Math.round(window.innerHeight * 0.52) }
        : { top: bp === 'tablet' ? 110 : 60, bottom: 0, bottomOpen: 0 },
    [phone, bp],
  )

  const url = app.view === 'zone' ? api.zones(app.wParam) : api.cells(app.view, app.wParam)
  const map = useFetch<MapCollection>(url)

  // A new selection (map tap, ranking click) or the weights tab opens the sheet/panel.
  // Adjusted during render (React's pattern for state derived from a change), not in an effect.
  const { selection, panelTab } = app
  const [seen, setSeen] = useState({ selection, panelTab })
  if (seen.selection !== selection || seen.panelTab !== panelTab) {
    setSeen({ selection, panelTab })
    if ((selection && seen.selection !== selection) || (panelTab === 'weights' && seen.panelTab !== panelTab)) {
      if (snap === 'peek') setSnap('half')
      if (selection) setCollapsed(false)
    }
  }

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <Header dark={dark} toggleTheme={toggleTheme} />
      <div className="relative flex min-h-0 flex-1">
        <main className="relative min-w-0 flex-1" aria-label="Mappa">
          <MapView dark={dark} data={map.data} insets={insets} />
          {map.error && !map.data && (
            <p className="absolute inset-x-4 top-28 rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn">{ERRORS.load}</p>
          )}

          {/* Overlay controls: tabs + view + layers on top, legend bottom-left. */}
          <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex flex-col gap-2 p-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="pointer-events-auto min-w-0">
              <MapTabs />
            </div>
            <div className="pointer-events-auto flex items-center gap-2">
              <ViewSwitch />
              <LayersButton />
            </div>
          </div>
          <div
            className="pointer-events-none absolute left-3 z-10"
            style={{ bottom: phone ? PEEK_PX + 12 : 12 }}
          >
            <div className="pointer-events-auto">
              <Legend
                key={phone || short ? 'p' : 'd'}
                data={map.data}
                loading={map.loading}
                collapsible={phone || short}
                footer={!phone && collapsed ? <DisclaimerBar /> : undefined}
              />
            </div>
          </div>
        </main>

        {phone ? (
          <BottomSheet snap={snap} onSnap={setSnap} head={<PanelTabs />} footer={<DisclaimerBar />}>
            <PanelBody />
          </BottomSheet>
        ) : (
          <aside
            className={cx(
              'relative flex shrink-0 flex-col border-l border-line bg-surface-1 transition-[width] duration-200',
              collapsed ? 'w-12' : bp === 'desktop' ? 'w-[420px]' : 'w-[360px]',
            )}
            aria-label="Pannello di dettaglio"
          >
            {bp === 'tablet' && (
              <button
                type="button"
                onClick={() => setCollapsed(!collapsed)}
                aria-label={collapsed ? 'Apri il pannello' : 'Chiudi il pannello'}
                className="absolute top-2 left-1 z-10 flex size-10 items-center justify-center rounded-lg text-ink-2 hover:bg-surface-2"
              >
                <Icon d={collapsed ? ICONS.chevronLeft : ICONS.chevronRight} />
              </button>
            )}
            {!collapsed && (
              <>
                <PanelTabs className={cx('shrink-0 px-5', bp === 'tablet' && 'pl-12')} />
                <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
                  <PanelBody />
                </div>
                <div className="shrink-0 border-t border-line px-5 py-2">
                  <DisclaimerBar />
                </div>
              </>
            )}
          </aside>
        )}
      </div>
      <Methodology />
    </div>
  )
}
