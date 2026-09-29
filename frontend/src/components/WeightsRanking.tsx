import { useMemo, useState } from 'react'
import { api } from '../api/client'
import type { IndicatorKey, Ranking, RankingItem, Sensitivity } from '../api/types'
import { classLabel, DROPPED_REASON, ERRORS, INDICATOR_HINT, INDICATOR_LABEL } from '../i18n/it'
import { INDICATOR_COLORS } from '../lib/colors'
import { fmt, pct } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { useApp } from '../state'
import { Button, Caption, Icon, RobustBadge, Segmented, Spinner } from './ui'
import { cx, ICONS, rankInterval } from '../lib/ui'

export default function WeightsRanking() {
  const { level, grid } = useApp()
  return (
    <div className="space-y-6">
      <Weights />
      <RankingList key={`${level}-${grid}`} />
    </div>
  )
}

/** Weight sliders (FR-45): free 0–100 values, normalised on their total (Q36). */
function Weights() {
  const { meta, active, weights, setWeights, resetWeights, defaults, weightsValid } = useApp()
  const total = active.reduce((a, k) => a + (weights[k] ?? 0), 0)
  const isDefault = active.every((k) => weights[k] === defaults[k])
  const dropped = Object.entries(meta.indicators.dropped) as [IndicatorKey, string][]

  return (
    <section>
      <div className="flex items-center justify-between">
        <h2 className="font-serif text-lg font-medium">Pesi dell’indice</h2>
        <Button onClick={resetWeights} disabled={isDefault} className="min-h-9 px-3 text-xs">
          Ripristina
        </Button>
      </div>
      <ul className="mt-1">
        {active.map((k) => {
          const v = weights[k] ?? 0
          return (
            <li key={k} className="flex items-center gap-2 text-[13px]">
              <label htmlFor={`w-${k}`} className="flex w-28 shrink-0 items-center gap-1.5 text-ink-2" title={INDICATOR_HINT[k]}>
                <span className="size-2 rounded-sm" style={{ background: INDICATOR_COLORS[k] }} />
                {INDICATOR_LABEL[k]}
              </label>
              <input
                id={`w-${k}`}
                type="range"
                className="range min-w-0 flex-1"
                min={0}
                max={100}
                step={5}
                value={v}
                onChange={(e) => setWeights({ ...weights, [k]: Number(e.target.value) })}
                style={{ '--fill': INDICATOR_COLORS[k] } as React.CSSProperties}
              />
              <span className="w-7 text-right font-mono text-xs">{v}</span>
              <span className="w-9 text-right font-mono text-[11px] text-ink-3">{total > 0 ? pct(v / total, 0) : '–'}</span>
            </li>
          )
        })}
      </ul>
      <Caption className="mt-1">Somma dei pesi: {total}. Il calcolo li normalizza sul totale (ultima colonna: peso effettivo).</Caption>
      {dropped.map(([k, reason]) => (
        <Caption key={k} className="mt-1 text-ink-3">
          {INDICATOR_LABEL[k]}: {DROPPED_REASON[reason] ?? reason}.
        </Caption>
      ))}
      {!weightsValid && <p className="mt-2 rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn">{ERRORS.weights}</p>}
      <RobustnessCheck />
    </section>
  )
}

/** "Verifica robustezza" (plan 3.5): the city-level stability summary for the current weights. */
function RobustnessCheck() {
  const { level, grid, wParam } = useApp()
  const [requested, setRequested] = useState<string | null>(null)
  const key = `${level}|${grid}|${wParam}`
  const { data, loading, error } = useFetch<Sensitivity>(requested === key ? api.sensitivity(level, grid, wParam) : null)
  const s = data?.summary

  return (
    <div className="mt-3">
      {requested !== key ? (
        <Button onClick={() => setRequested(key)} className="w-full">
          Verifica robustezza
        </Button>
      ) : loading ? (
        <div className="flex min-h-11 items-center gap-2 text-sm text-ink-2">
          <Spinner /> Calcolo di 1.000 scenari di pesi…
        </div>
      ) : error ? (
        <p className="text-sm text-warn">{ERRORS.generic}</p>
      ) : data && !data.applicable ? (
        <p className="rounded-lg bg-surface-2 px-3 py-2 text-sm text-ink-2">
          Robustezza non applicabile: con un solo indicatore (o pesi troppo concentrati) non ci sono pesi da far variare.
        </p>
      ) : s ? (
        <div className="rounded-lg bg-surface-2 px-3 py-2.5 text-sm">
          <p className="font-medium">
            {s.spearman_mean >= 0.9 ? 'La classifica è stabile' : s.spearman_mean >= 0.75 ? 'La classifica è abbastanza stabile' : 'La classifica dipende molto dai pesi'}
          </p>
          <p className="mt-1 text-ink-2">
            Variando ogni peso di circa ±5 punti (1.000 scenari), {level === 'zone' ? `il top ${s.top_n}` : `il top 10% (${fmt(s.top_n)} celle)`} resta in
            media per il {pct(s.top_n_overlap_mean / s.top_n, 0)}; correlazione media con la classifica attuale {fmt(s.spearman_mean, 2)}.{' '}
            {pct(s.robust_share, 0)} delle {level === 'zone' ? 'zone' : 'celle'} ha una priorità robusta.
          </p>
        </div>
      ) : null}
    </div>
  )
}

type SortKey = 'rank' | 'trees_new' | 'residents'
const PAGE = 20

/** Ranking (FR-46): bars split by indicator contributions, sortable, CSV export (FR-49). */
function RankingList() {
  const { level, grid, wParam, active, selectAndFly, selection } = useApp()
  const { data, loading, error } = useFetch<Ranking>(api.ranking(level, grid, 10000, wParam))
  const [sort, setSort] = useState<SortKey>('rank')
  const [shown, setShown] = useState(PAGE)

  const items = useMemo(() => {
    const list = [...(data?.items ?? [])]
    if (sort !== 'rank') list.sort((a, b) => (b[sort] ?? 0) - (a[sort] ?? 0) || a.rank - b.rank)
    return list
  }, [data, sort])

  return (
    <section className="border-t-[1.5px] border-ink pt-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="font-serif text-lg font-medium">{level === 'zone' ? 'Quartieri da servire per primi' : `Celle ${grid} m da servire per prime`}</h2>
          <Caption>La barra mostra da cosa deriva il punteggio</Caption>
        </div>
        {loading && <Spinner className="mt-1.5" />}
      </div>
      <div className="mt-2 flex items-center gap-2">
        <Segmented
          label="Ordina per"
          value={sort}
          onChange={setSort}
          options={[
            { value: 'rank', label: 'Priorità' },
            { value: 'trees_new', label: 'Alberi' },
            { value: 'residents', label: 'Residenti' },
          ]}
          className="flex-1"
        />
        <Button
          variant="secondary"
          className="min-h-10 px-2.5 text-xs sm:min-h-9"
          disabled={!data}
          onClick={() => data && downloadCsv(data, active)}
          aria-label="Scarica la classifica in CSV"
          title="Scarica la classifica in CSV"
        >
          <Icon d={ICONS.download} className="size-4" /> CSV
        </Button>
      </div>
      {error && !data && <p className="mt-2 text-sm text-warn">{ERRORS.load}</p>}
      <ol className={cx('mt-1 transition-opacity', loading && 'opacity-60')}>
        {items.slice(0, shown).map((it) => (
          <li key={it.id}>
            <RankingRow
              it={it}
              level={level}
              active={active}
              selected={selection?.level === level && selection.id === it.id}
              onClick={() => {
                selectAndFly({ level, id: it.id })
              }}
            />
          </li>
        ))}
      </ol>
      {items.length > shown && (
        <Button variant="ghost" className="mt-1 w-full" onClick={() => setShown(shown + PAGE)}>
          Mostra altre {Math.min(PAGE, items.length - shown)} (di {fmt(items.length)})
        </Button>
      )}
    </section>
  )
}

function RankingRow({
  it,
  level,
  active,
  selected,
  onClick,
}: {
  it: RankingItem
  level: 'zone' | 'cell'
  active: IndicatorKey[]
  selected: boolean
  onClick: () => void
}) {
  const interval = rankInterval(it.rank_p5, it.rank_p95)
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx(
        'flex w-full items-center gap-2.5 border-t border-line py-2.5 text-left hover:bg-surface-2',
        selected && 'bg-surface-2',
      )}
    >
      <span className="w-7 shrink-0 text-center font-serif text-lg text-ink-3">{it.rank}</span>
      <div className="min-w-0 flex-1">
        <div className="mb-1.5 flex items-baseline justify-between gap-2 text-sm">
          <span className="truncate font-medium">{level === 'zone' ? it.name : `Cella · ${it.name ?? ''}`}</span>
          <span className="shrink-0 font-mono text-[11px] text-ink-2">
            ~{fmt(it.trees_new)} alberi
            {level === 'zone' && (it.trees_new_nonres ?? 0) > 0 && (
              <span className="text-ink-3" title="Alberi stimati in aree non residenziali, contati a parte">
                {' '}
                +{fmt(it.trees_new_nonres)}
              </span>
            )}
          </span>
        </div>
        <div className="h-2 overflow-hidden rounded-sm bg-surface-2">
          <div className="flex h-2" style={{ width: `${it.ipf}%` }}>
            {active.map((k) => (
              <i key={k} className="block h-2" style={{ width: `${((it.contributions[k] ?? 0) / it.ipf) * 100}%`, background: INDICATOR_COLORS[k] }} />
            ))}
          </div>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <RobustBadge s={{ robust: it.robust, applicable: it.robust !== null }} compact />
          {interval && <span className="text-[11px] text-ink-3">{interval}</span>}
          {it.residential === false && (
            <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-ink-2">non residenziale</span>
          )}
        </div>
      </div>
      <div className="w-16 shrink-0 text-right">
        <p className="font-serif text-xl leading-none">{fmt(it.ipf, 1)}</p>
        <p className="mt-0.5 font-mono text-[10px] text-ink-2">{classLabel(it.ipf_class)}</p>
      </div>
    </button>
  )
}

/** CSV for Italian spreadsheets: `;` separator, decimal comma, UTF-8 BOM. */
function downloadCsv(r: Ranking, active: IndicatorKey[]) {
  const num = (v: number | null, d = 1) => (v === null ? '' : v.toFixed(d).replace('.', ','))
  const esc = (s: string) => (/[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s)
  const head = [
    'posizione',
    r.level === 'zone' ? 'quartiere' : 'cella',
    ...(r.level === 'cell' ? ['quartiere'] : []),
    'ipf',
    'classe',
    'posizione_min_p5',
    'posizione_max_p95',
    'robusta',
    r.level === 'zone' ? 'nuovi_alberi_stima_aree_abitate' : 'nuovi_alberi_stima',
    ...(r.level === 'zone' ? ['nuovi_alberi_stima_aree_non_residenziali'] : ['residenziale']),
    'residenti',
    ...active.map((k) => `contributo_${k}`),
  ]
  const rows = r.items.map((it) => [
    String(it.rank),
    esc(r.level === 'zone' ? (it.name ?? '') : it.id),
    ...(r.level === 'cell' ? [esc(it.name ?? '')] : []),
    num(it.ipf),
    classLabel(it.ipf_class),
    it.rank_p5 === null ? '' : String(it.rank_p5),
    it.rank_p95 === null ? '' : String(it.rank_p95),
    it.robust === null ? '' : it.robust ? 'sì' : 'no',
    it.trees_new === null ? '' : String(it.trees_new),
    r.level === 'zone' ? (it.trees_new_nonres === null ? '' : String(it.trees_new_nonres)) : it.residential ? 'sì' : 'no',
    num(it.residents, 0),
    ...active.map((k) => num(it.contributions[k] ?? null, 2)),
  ])
  const lines = [head.join(';'), ...rows.map((x) => x.join(';'))]
  const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `classifica_ipf_${r.level === 'zone' ? 'quartieri' : `celle_${r.grid}m`}${r.is_default ? '' : '_pesi_personalizzati'}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}
