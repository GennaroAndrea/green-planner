import { api } from '../api/client'
import type { Detail, IndicatorKey, Ranking } from '../api/types'
import { classLabel, detailTitle, DISCLAIMERS, driverSentence, ERRORS, INDICATOR_HINT, INDICATOR_LABEL, rawValueText } from '../i18n/it'
import { classColor, INDICATOR_COLORS, scoreColor } from '../lib/colors'
import { fmt, ord, pct } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { useApp } from '../state'
import { Button, Caption, Icon, RobustBadge, Spinner } from './ui'
import { cx, ICONS, rankInterval } from '../lib/ui'

export default function DetailPanel() {
  const { selection, wParam, setSimulating } = useApp()
  const url = selection ? api.detail(selection.level, selection.id, wParam) : null
  const { data, error, loading } = useFetch<Detail>(url)

  if (!selection) return <Intro />
  if (error && !data) return <p className="p-4 text-sm text-warn">{ERRORS.load}</p>
  if (!data) return <Loading />
  // Keep showing the previous item while the next one loads, dimmed.
  const stale = loading || data.id !== selection.id

  return (
    <article className={cx('space-y-5 transition-opacity', stale && 'opacity-50')} aria-busy={stale}>
      <Header d={data} />
      <Drivers d={data} />
      <Indicators d={data} />
      <TreesBox d={data} />
      <Stats d={data} />
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" onClick={() => setSimulating(true)} className="flex-1">
          <Icon d={ICONS.tree} className="size-4" /> Simula intervento
        </Button>
      </div>
      <Caption className="text-ink-3">Stima del modello. Dati ARPA soggetti a revisione. Priorità relativa rispetto al resto di Bari.</Caption>
    </article>
  )
}

function Loading() {
  return (
    <div className="flex items-center gap-2 p-2 text-sm text-ink-2">
      <Spinner /> Caricamento…
    </div>
  )
}

function Header({ d }: { d: Detail }) {
  const interval = rankInterval(d.sensitivity.rank_p5, d.sensitivity.rank_p95)
  const unit = d.level === 'zone' ? 'quartieri' : 'celle'
  return (
    <header>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-serif text-xl leading-tight font-medium">{detailTitle(d)}</h2>
          <Caption className="mt-1">
            Priorità {classLabel(d.ipf_class).toLowerCase()} · classe {d.ipf_class} di 4 · {ord(d.rank)} su {fmt(d.ranked_items)} {unit}
          </Caption>
        </div>
        <p className="shrink-0 text-right font-serif text-[40px] leading-none font-medium" style={{ color: classColor(d.ipf_class) }}>
          {fmt(d.ipf, 1)}
          <span className="font-mono text-xs text-ink-2"> /100</span>
        </p>
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1">
        <RobustBadge s={d.sensitivity} />
        {interval && d.sensitivity.applicable && (
          <span className="text-xs text-ink-2">
            {interval} variando i pesi di ±5 punti
          </span>
        )}
      </div>
      {!d.is_default && <Caption className="mt-1.5 text-accent">Scenario con pesi personalizzati</Caption>}
    </header>
  )
}

function Drivers({ d }: { d: Detail }) {
  const raw = Object.fromEntries(d.indicators.map((i) => [i.key, i.raw_value])) as Record<IndicatorKey, number | null>
  return (
    <section className="border-t-[1.5px] border-ink pt-3">
      <h3 className="font-serif text-base font-medium">Perché questa zona è prioritaria?</h3>
      <ol className="mt-2 space-y-2.5">
        {d.top_drivers.map((dr, i) => (
          <li key={dr.indicator} className="flex gap-2.5">
            <span className="mt-0.5 font-serif text-lg leading-none text-ink-3">{i + 1}</span>
            <div className="min-w-0 text-sm">
              <p>
                <span className="mr-1.5 inline-block size-2 rounded-sm align-middle" style={{ background: INDICATOR_COLORS[dr.indicator] }} />
                {driverSentence(dr.indicator, dr.score, dr.contribution)}
              </p>
              <p className="mt-0.5 text-xs text-ink-2">{rawValueText(dr.indicator, raw[dr.indicator], d.trees.target_green_share)}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}

function Indicators({ d }: { d: Detail }) {
  const ipf = d.ipf ?? 0
  return (
    <section>
      <Caption>Punteggi degli indicatori (0–100) e peso nell’indice</Caption>
      <ul className="mt-2 space-y-2">
        {d.indicators.map((ind) => (
          <li key={ind.key} className="flex items-center gap-2.5 text-[13px]" title={INDICATOR_HINT[ind.key]}>
            <span className="w-28 shrink-0 text-ink-2">{INDICATOR_LABEL[ind.key]}</span>
            <span className="relative h-2.5 flex-1">
              <span className="absolute inset-x-0 top-[4.5px] h-px bg-line-strong" />
              {ind.score !== null && (
                <span
                  className="absolute top-0 -ml-[5px] size-2.5 rounded-full"
                  style={{ left: `${ind.score}%`, background: scoreColor(ind.score) }}
                />
              )}
            </span>
            <span className="w-7 text-right font-mono text-xs">{fmt(ind.score)}</span>
            <span className="w-10 text-right font-mono text-[11px] text-ink-3">{fmt(ind.weight * 100)}%</span>
          </li>
        ))}
      </ul>
      <Caption className="mt-3">Da cosa deriva l’indice ({fmt(ipf, 1)} punti)</Caption>
      <div className="mt-1.5 flex h-3 overflow-hidden rounded-sm bg-surface-2" role="img" aria-label="Contributi degli indicatori all’indice">
        {d.indicators.map((ind) => (
          <span key={ind.key} style={{ width: `${ind.contribution ?? 0}%`, background: INDICATOR_COLORS[ind.key] }} />
        ))}
      </div>
      <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1">
        {d.indicators.map((ind) => (
          <li key={ind.key} className="flex items-center gap-1 text-[11px] text-ink-2">
            <span className="size-2 rounded-sm" style={{ background: INDICATOR_COLORS[ind.key] }} />
            {INDICATOR_LABEL[ind.key]} <span className="font-mono">{fmt(ind.contribution, 1)}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function TreesBox({ d }: { d: Detail }) {
  const t = d.trees
  const share = d.stats.veg_share
  const nonResidentialCell = d.level === 'cell' && d.stats.residential === false
  return (
    <>
    {nonResidentialCell && (
      <p className="rounded-lg bg-surface-2 px-3 py-2 text-[13px] text-ink-2">
        <b className="font-medium text-ink">Area non residenziale</b>: nessun residente in questa cella (zona industriale, porto,
        infrastrutture). I suoi alberi sono contati a parte nei totali del quartiere.
      </p>
    )}
    <section className="flex border-y border-line">
      <div className="flex-1 py-2.5 pr-3">
        {d.level === 'cell' ? (
          <>
            <Caption>Vegetazione attuale → obiettivo</Caption>
            <p className="mt-0.5 font-serif text-xl">
              {pct(share)} → {pct(t.target_green_share, 0)}
            </p>
          </>
        ) : (
          <>
            <Caption>Vegetazione media</Caption>
            <p className="mt-0.5 font-serif text-xl">{pct(share)}</p>
            <Caption className="mt-0.5">
              {fmt(t.cells_below_target)} celle abitate su {fmt(d.stats.cells_residential)} sotto il {pct(t.target_green_share, 0)}
            </Caption>
          </>
        )}
      </div>
      <div className="flex-1 border-l border-line py-2.5 pl-3">
        <Caption>Nuovi alberi (stima)</Caption>
        <p className="mt-0.5 font-serif text-xl">~{fmt(t.trees_new)}</p>
        <Caption className="mt-0.5">
          {fmt(t.trees_for_target)} {d.level === 'zone' ? 'per portare ogni cella abitata al' : 'per arrivare al'}{' '}
          {pct(t.target_green_share, 0)}
        </Caption>
        {d.level === 'zone' && (t.trees_new_nonres ?? 0) > 0 && (
          <Caption className="mt-1 text-ink-3">+ {fmt(t.trees_new_nonres)} in aree non residenziali</Caption>
        )}
      </div>
    </section>
    </>
  )
}

function Stats({ d }: { d: Detail }) {
  const s = d.stats
  const area = d.level === 'zone' ? s.analysed_area_m2 : s.area_m2
  return (
    <section>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[13px]">
        <Stat label="Residenti" value={fmt(s.residents)} />
        <Stat label="Di cui vulnerabili (<14, >67)" value={fmt(s.vulnerable)} />
        <Stat label="Densità" value={`${fmt(s.density_km2)} ab./km²`} />
        <Stat label={d.level === 'zone' ? 'Area analizzata' : 'Area della cella'} value={`${fmt((area ?? 0) / 1e6, 2)} km²`} />
        <Stat label="Verde pubblico mappato (Comune)" value={pct(s.green_share)} />
        {d.level === 'zone' && (
          <Stat label="Celle abitate / analizzate" value={`${fmt(s.cells_residential)} / ${fmt(s.cells_analysed)}`} />
        )}
      </dl>
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] text-ink-2">{label}</dt>
      <dd className="font-mono text-[13px]">{value}</dd>
    </div>
  )
}

/** Shown when nothing is selected: how to start, plus the current top 5. */
function Intro() {
  const { level, grid, wParam, selectAndFly } = useApp()
  const { data } = useFetch<Ranking>(api.ranking(level, grid, 5, wParam))
  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-serif text-xl font-medium">Dove piantare prima a Bari</h2>
        <p className="mt-1.5 text-sm text-ink-2">
          L’indice IPF (0–100) combina inquinamento, carenza di verde, traffico e popolazione. Tocca{' '}
          {level === 'zone' ? 'un quartiere' : 'una cella'} sulla mappa per vedere perché è{' '}
          {level === 'zone' ? 'prioritario' : 'prioritaria'} e quanti alberi servono.
        </p>
      </div>
      <section>
        <Caption>Le 5 {level === 'zone' ? 'zone' : 'celle'} più prioritarie</Caption>
        <ol className="mt-1.5">
          {data?.items.map((it) => (
            <li key={it.id}>
              <button
                type="button"
                onClick={() => {
                  selectAndFly({ level, id: it.id })
                }}
                className="flex min-h-11 w-full items-center gap-3 border-t border-line text-left text-sm hover:bg-surface-2"
              >
                <span className="w-5 font-serif text-lg text-ink-3">{it.rank}</span>
                <span className="size-3 rounded-sm" style={{ background: classColor(it.ipf_class) }} />
                <span className="flex-1 truncate">{level === 'zone' ? it.name : `Cella · ${it.name ?? ''}`}</span>
                <span className="font-mono text-xs">{fmt(it.ipf, 1)}</span>
              </button>
            </li>
          ))}
        </ol>
      </section>
      <p className="text-xs text-ink-3">{DISCLAIMERS.relative_priority}</p>
    </div>
  )
}
