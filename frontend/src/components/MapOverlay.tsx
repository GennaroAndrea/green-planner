import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import { useMemo, useState } from 'react'
import type { LayerKey, MapCollection } from '../api/types'
import { CLASS_KEYS, CLASS_LABEL, DISCLAIMERS, LAYER_LABEL, MAP_TABS, SCORE_LEGEND } from '../i18n/it'
import { CLASS_COLORS, GREEN, INDICATOR_COLORS, SCORE_RAMP } from '../lib/colors'
import { fmt } from '../lib/format'
import { useApp, type View } from '../state'
import { Icon, Segmented, Spinner } from './ui'
import { cx, ICONS } from '../lib/ui'

const VIEW_OPTIONS: { value: View; label: string }[] = [
  { value: 'zone', label: 'Quartieri' },
  { value: 50, label: 'Celle 50 m' },
  { value: 250, label: 'Celle 250 m' },
  { value: 500, label: 'Celle 500 m' },
]

/** Indicator tabs (FR-52) along the top of the map. */
export function MapTabs() {
  const { tab, setTab } = useApp()
  return (
    <div role="tablist" aria-label="Cosa mostra la mappa" className="no-scrollbar flex gap-1 overflow-x-auto">
      {MAP_TABS.map((t) => (
        <button
          key={t.key}
          role="tab"
          type="button"
          aria-selected={tab === t.key}
          onClick={() => setTab(t.key)}
          className={cx(
            'min-h-11 shrink-0 rounded-full px-3.5 text-[13px] whitespace-nowrap shadow-sm transition-colors sm:min-h-9',
            tab === t.key
              ? 'bg-ink font-medium text-surface-1'
              : 'bg-surface-1/95 text-ink-2 ring-1 ring-line hover:text-ink',
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

export function ViewSwitch() {
  const { view, setView } = useApp()
  return (
    <Segmented
      label="Unità della mappa"
      options={VIEW_OPTIONS}
      value={view}
      onChange={setView}
      className="bg-surface-1/95 shadow-sm ring-1 ring-line"
    />
  )
}

const LAYER_ORDER: LayerKey[] = ['green', 'traffic', 'air', 'industry']

export function LayersButton() {
  const { layers, toggleLayer, tab } = useApp()
  return (
    <Popover className="relative">
      <PopoverButton
        aria-label="Livelli di contesto"
        className="flex size-11 items-center justify-center rounded-lg bg-surface-1/95 text-ink shadow-sm ring-1 ring-line hover:bg-surface-2 sm:size-10"
      >
        <Icon d={ICONS.layers} />
        {layers.size > 0 && (
          <span className="absolute -top-1 -right-1 flex size-4 items-center justify-center rounded-full bg-accent text-[10px] font-medium text-surface-1">
            {layers.size}
          </span>
        )}
      </PopoverButton>
      <PopoverPanel
        anchor={{ to: 'bottom end', gap: 6 }}
        className="z-40 w-72 rounded-xl border border-line bg-surface-1 p-2 text-ink shadow-lg"
      >
        <p className="px-2 pt-1 pb-2 font-mono text-[11px] text-ink-2">Livelli di contesto</p>
        {LAYER_ORDER.map((k) => {
          const on = layers.has(k) || (k === 'industry' && tab === 'industry')
          const forced = k === 'industry' && tab === 'industry'
          return (
            <button
              key={k}
              type="button"
              role="checkbox"
              aria-checked={on}
              disabled={forced}
              onClick={() => toggleLayer(k)}
              className="flex min-h-11 w-full items-center gap-3 rounded-lg px-2 text-left text-sm hover:bg-surface-2 disabled:opacity-70"
            >
              <span
                className={cx(
                  'flex size-5 shrink-0 items-center justify-center rounded border',
                  on ? 'border-ink bg-ink text-surface-1' : 'border-line-strong',
                )}
              >
                {on && <Icon d={ICONS.check} className="size-3.5" />}
              </span>
              <LayerSymbol k={k} />
              <span className="flex-1">{LAYER_LABEL[k]}</span>
            </button>
          )
        })}
        <p className="px-2 pt-2 pb-1 text-[11px] text-ink-3">{DISCLAIMERS.no_causality}</p>
      </PopoverPanel>
    </Popover>
  )
}

function LayerSymbol({ k }: { k: LayerKey }) {
  if (k === 'green') return <span className="size-3 shrink-0 rounded-sm" style={{ background: GREEN }} />
  if (k === 'traffic') return <span className="size-3 shrink-0 rounded-full" style={{ background: INDICATOR_COLORS.traffic }} />
  if (k === 'air')
    return <span className="size-3 shrink-0 rounded-full ring-2 ring-white" style={{ background: INDICATOR_COLORS.pollution }} />
  return <span className="size-3 shrink-0 rounded-full border-[2.5px] border-stone-600 bg-stone-600 dark:border-stone-200" />
}

/** Legend (FR-41): class counts for the priority view, a 0–100 ramp for the indicator tabs. */
export function Legend({
  data,
  loading,
  collapsible,
  footer,
}: {
  data: MapCollection | undefined
  loading: boolean
  collapsible: boolean
  /** Extra content at the bottom (the disclaimer when the tablet panel is collapsed). */
  footer?: React.ReactNode
}) {
  const { tab, level, layers, wParam } = useApp()
  const [open, setOpen] = useState(!collapsible)
  const counts = useMemo(() => {
    const c = [0, 0, 0, 0, 0]
    for (const f of data?.features ?? []) c[f.properties.ipf_class] += 1
    return c
  }, [data])
  const unit = level === 'zone' ? 'quartieri' : 'celle'

  if (collapsible && !open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex min-h-11 items-center gap-2 rounded-lg bg-surface-1/95 px-3 text-[13px] text-ink shadow-sm ring-1 ring-line"
      >
        <span className="flex h-2.5 w-10 overflow-hidden rounded-sm">
          {[1, 2, 3, 4].map((i) => (
            <i key={i} className="flex-1" style={{ background: CLASS_COLORS[i] }} />
          ))}
        </span>
        Legenda
        {loading && <Spinner className="size-3" />}
      </button>
    )
  }

  const shownLayers = LAYER_ORDER.filter((k) => layers.has(k) || (k === 'industry' && tab === 'industry'))

  return (
    <div className="w-64 max-w-[calc(100vw-2rem)] rounded-xl bg-surface-1/95 p-3 text-ink shadow-sm ring-1 ring-line backdrop-blur">
      <div className="mb-2 flex items-start justify-between gap-2">
        <p className="font-mono text-[11px] leading-snug text-ink-2">
          {tab === 'priority' || tab === 'industry'
            ? `Priorità relativa di forestazione (${unit})`
            : SCORE_LEGEND[tab]}
        </p>
        <div className="flex items-center gap-1">
          {loading && <Spinner className="size-3" />}
          {collapsible && (
            <button
              type="button"
              aria-label="Chiudi legenda"
              onClick={() => setOpen(false)}
              className="-m-2 flex size-9 items-center justify-center text-ink-2"
            >
              <Icon d={ICONS.close} className="size-4" />
            </button>
          )}
        </div>
      </div>
      {wParam !== null && (tab === 'priority' || tab === 'industry') && (
        <p className="mb-2 rounded bg-accent-soft px-2 py-1 text-[11px] text-accent">Scenario con pesi personalizzati</p>
      )}
      {tab === 'priority' || tab === 'industry' ? (
        <ul className="space-y-1">
          {[4, 3, 2, 1].map((c) => (
            <li key={c} className="flex items-center gap-2 text-[13px]">
              <span className="size-3.5 rounded-sm" style={{ background: CLASS_COLORS[c] }} />
              <span className="flex-1">{CLASS_LABEL[CLASS_KEYS[c - 1]]}</span>
              <span className="font-mono text-xs text-ink-2">{fmt(counts[c])}</span>
            </li>
          ))}
          <li className="flex items-center gap-2 text-[13px] text-ink-2">
            <span className="size-3.5 rounded-sm bg-[var(--no-data)] opacity-60" />
            <span className="flex-1">Non analizzata</span>
            <span className="font-mono text-xs">{fmt(counts[0])}</span>
          </li>
        </ul>
      ) : (
        <div>
          <div
            className="h-2.5 rounded-sm"
            style={{ background: `linear-gradient(to right, ${SCORE_RAMP.map(([x, c]) => `${c} ${x}%`).join(', ')})` }}
          />
          <div className="mt-1 flex justify-between font-mono text-[11px] text-ink-2">
            <span>0 · basso</span>
            <span>100 · alto</span>
          </div>
        </div>
      )}
      {shownLayers.length > 0 && (
        <ul className="mt-2 space-y-1 border-t border-line pt-2">
          {shownLayers.map((k) => (
            <li key={k} className="flex items-center gap-2 text-[12px] text-ink-2">
              <LayerSymbol k={k} />
              {LAYER_LABEL[k]}
            </li>
          ))}
        </ul>
      )}
      {tab === 'industry' && <p className="mt-2 text-[11px] leading-snug text-ink-3">Impianti E-PRTR entro 10 km dal confine. Pieni: dichiarazione recente (2020–2024). {DISCLAIMERS.no_causality}</p>}
      {tab === 'priority' && (
        <p className="mt-2 text-[11px] leading-snug text-ink-3">Classi a quartili: ogni classe contiene circa un quarto delle zone analizzate.</p>
      )}
      {footer && <div className="mt-2 border-t border-line pt-2">{footer}</div>}
    </div>
  )
}
