import { useMemo, useState } from 'react'
import { api } from '../api/client'
import type { Detail, Simulation } from '../api/types'
import { classLabel, detailTitle, ERRORS } from '../i18n/it'
import { classColor } from '../lib/colors'
import { fmt, ord, pct } from '../lib/format'
import { useDebounced, useFetch } from '../lib/hooks'
import { useApp } from '../state'
import { Button, Caption, Icon, Spinner } from './ui'
import { cx, ICONS } from '../lib/ui'

/** A round slider step giving about 200 positions. */
function niceStep(max: number): number {
  const raw = max / 200
  const p = 10 ** Math.floor(Math.log10(Math.max(raw, 1)))
  for (const m of [1, 2, 5, 10]) if (m * p >= raw) return m * p
  return 10 * p
}

/** Tree simulator (FR-53, Q37, Q44), opened from the selected zone/cell card. */
export default function Simulator() {
  const { selection, wParam, setSimulating } = useApp()
  const detail = useFetch<Detail>(selection ? api.detail(selection.level, selection.id, wParam) : null)
  const d = detail.data

  if (!selection) return null
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button variant="ghost" onClick={() => setSimulating(false)} className="-ml-2 px-2" aria-label="Torna alla scheda">
          <Icon d={ICONS.back} className="size-4" /> Scheda
        </Button>
      </div>
      <header>
        <h2 className="font-serif text-xl font-medium">Simulatore</h2>
        {d && <Caption className="mt-0.5">{detailTitle(d)} · cosa succede se pianto nuovi alberi?</Caption>}
      </header>
      {d ? <SimulatorBody key={`${d.level}-${d.id}`} d={d} /> : detail.error ? <p className="text-sm text-warn">{ERRORS.load}</p> : <Spinner />}
    </div>
  )
}

function SimulatorBody({ d }: { d: Detail }) {
  const { wParam } = useApp()
  const estimate = d.trees.trees_new ?? 0
  const target = d.trees.trees_for_target ?? 0
  const { max, step } = useMemo(() => {
    const base = Math.max(target * 1.2, estimate * 2, 100)
    const st = niceStep(base)
    return { max: Math.ceil(base / st) * st, step: st }
  }, [estimate, target])
  const [trees, setTrees] = useState(estimate)
  const debounced = useDebounced(trees, 120)
  const [years, setYears] = useState<number | null>(null)
  const debouncedYears = useDebounced(years, 120)
  const sim = useFetch<Simulation>(api.simulate(d.level, d.id, debounced, wParam, debouncedYears))
  const s = sim.data
  const maxYears = (s?.maturity_years ?? 15) + 10

  const marker = (n: number) => `calc(10px + (100% - 20px) * ${Math.min(1, n / max)})`

  return (
    <>
      <TreeSketch share={s ? s.after.veg_share : null} before={s?.before.veg_share ?? null} trees={trees} max={max} />

      <div>
        <div className="flex items-center gap-3 pb-4">
          <label htmlFor="sim-trees" className="text-[13px] text-ink-2">
            Nuovi alberi
          </label>
          <div className="relative flex-1">
            <input
              id="sim-trees"
              type="range"
              className="range block w-full"
              min={0}
              max={max}
              step={step}
              value={trees}
              onChange={(e) => setTrees(Number(e.target.value))}
              style={{ '--fill': '#3B6D11' } as React.CSSProperties}
            />
            {/* Markers for the model estimate and the 15% target, aligned with the thumb centre (20 px thumb). */}
            {estimate > 0 && (
              <span className="absolute top-[36px] -translate-x-1/2 font-mono text-[10px] whitespace-nowrap text-ink-2" style={{ left: marker(estimate) }}>
                ▲ stima
              </span>
            )}
            {target > 0 && (
              <span className="absolute top-[36px] -translate-x-1/2 font-mono text-[10px] whitespace-nowrap text-ok" style={{ left: marker(target) }}>
                ▲ 15%
              </span>
            )}
          </div>
          <span className="min-w-14 text-right font-mono text-sm">{fmt(trees)}</span>
        </div>
        <div className="mt-1 flex flex-wrap gap-2">
          <Button onClick={() => setTrees(0)} className="min-h-10 px-2.5 text-xs">
            Nessuno
          </Button>
          <Button onClick={() => setTrees(estimate)} className="min-h-10 px-2.5 text-xs">
            Stima del modello · {fmt(estimate)}
          </Button>
          {target > 0 && (
            <Button onClick={() => setTrees(target)} className="min-h-10 px-2.5 text-xs">
              Obiettivo 15% · {fmt(target)}
            </Button>
          )}
        </div>
        <Caption className="mt-2">
          {target > 0
            ? `Con ${fmt(target)} alberi (${fmt(d.trees.target_green_share * 100)}% di vegetazione in ${d.level === 'zone' ? 'ogni cella abitata' : 'questa cella'}) si chiude tutto il deficit. La stima del modello (${fmt(estimate)}) considera piantabile solo il 25% del deficit.`
            : 'Questa zona ha già almeno il 15% di verde pubblico: nessun deficit da colmare.'}
        </Caption>
      </div>

      <div>
        <div className="flex items-center gap-3 pb-4">
          <label htmlFor="sim-years" className="text-[13px] text-ink-2">
            Anni dalla piantumazione
          </label>
          <div className="relative flex-1">
            <input
              id="sim-years"
              type="range"
              className="range block w-full"
              min={0}
              max={maxYears}
              step={1}
              value={years ?? maxYears}
              onChange={(e) => setYears(Number(e.target.value))}
              style={{ '--fill': '#888780' } as React.CSSProperties}
            />
            <span
              className="absolute top-[36px] -translate-x-1/2 font-mono text-[10px] whitespace-nowrap text-ink-2"
              style={{ left: `calc(10px + (100% - 20px) * ${Math.min(1, (s?.maturity_years ?? 15) / maxYears)})` }}
            >
              ▲ maturità
            </span>
          </div>
          <span className="min-w-14 text-right font-mono text-sm">
            {years == null ? 'maturi' : `${fmt(years)} ${years === 1 ? 'anno' : 'anni'}`}
          </span>
        </div>
        <Caption className="mt-1">
          {s && s.growth_share != null && s.growth_share < 1
            ? `Chioma al ${pct(s.growth_share)} della maturità: gli alberi crescono linearmente fino all'anno ${s.maturity_years} (stima del modello).`
            : `A maturità (anno ${s?.maturity_years ?? 15}) ogni albero contribuisce con la chioma piena.`}
        </Caption>
        {s && d.level === 'cell' && trees > 0 && (
          <Caption className="mt-2">
            {s.years_to_target != null
              ? s.years_to_target === 0
                ? 'La cella è già al di sopra dell\'obiettivo di vegetazione.'
                : `Con ${fmt(trees)} alberi la cella raggiunge il ${fmt(s.target_green_share * 100)}% di vegetazione nell'anno ${s.years_to_target}.`
              : `Con ${fmt(trees)} alberi il ${fmt(s.target_green_share * 100)}% di vegetazione non è raggiungibile in questa cella (servono ~${fmt(s.trees_for_target)} alberi).`}{' '}
            {s.years_to_class_change != null
              ? `La priorità scende di classe nell'anno ${s.years_to_class_change}.`
              : 'La classe di priorità resta invariata anche a maturità.'}
          </Caption>
        )}
        {d.level === 'zone' && <Caption className="mt-2">Il calcolo per anno è disponibile per le singole celle.</Caption>}
      </div>

      {s ? (
        <div className={cx('transition-opacity', sim.loading && 'opacity-60')}>
          <div className="flex border-t-[1.5px] border-ink">
            <div className="flex-1 py-3 pr-3">
              <Caption>Vegetazione</Caption>
              <p className="mt-0.5 font-serif text-[28px] leading-tight">{pct(s.after.veg_share)}</p>
              <Caption>era {pct(s.before.veg_share)}</Caption>
            </div>
            <div className="flex-1 border-l border-line py-3 pl-3">
              <Caption>Indice IPF</Caption>
              <p className="mt-0.5 font-serif text-[28px] leading-tight" style={{ color: classColor(s.after.ipf_class) }}>
                {fmt(s.after.ipf, 1)}
              </p>
              <Caption>
                {s.after.ipf < s.before.ipf - 0.05
                  ? `−${fmt(s.before.ipf - s.after.ipf, 1)} punti (era ${fmt(s.before.ipf, 1)})`
                  : `era ${fmt(s.before.ipf, 1)}`}
              </Caption>
            </div>
          </div>
          <div className="relative h-1.5 rounded-sm bg-surface-2">
            <div className="h-1.5 rounded-sm transition-all" style={{ width: `${s.after.ipf}%`, background: classColor(s.after.ipf_class) }} />
            <div className="absolute top-[-3px] h-3 w-0.5 bg-ink-3" style={{ left: `${s.before.ipf}%` }} title="Prima" />
          </div>
          <p className="mt-2 text-sm">
            Priorità {classLabel(s.after.ipf_class).toLowerCase()} · {ord(s.after.rank)} posto
            {s.after.rank !== s.before.rank && <span className="text-ink-2"> (era {ord(s.before.rank)}, {classLabel(s.before.ipf_class).toLowerCase()})</span>}
          </p>
          <Caption className="mt-0.5">
            Punteggio carenza verde {fmt(s.before.score_green_deficit)} → {fmt(s.after.score_green_deficit)}
          </Caption>
        </div>
      ) : sim.error ? (
        <p className="text-sm text-warn">{ERRORS.generic}</p>
      ) : (
        <Spinner />
      )}

      <p className="text-xs text-ink-3">
        Simulazione semplificata: ogni albero aggiunge {fmt(s?.crown_area_m2 ?? 30)} m² di chioma alla vegetazione e cambia solo l’indicatore del
        verde. Inquinamento, traffico e popolazione restano invariati; classe e posizione sono confrontate con il resto della città com’è
        oggi.{d.level === 'zone' &&
          ' Gli alberi sono distribuiti tra le celle abitate del quartiere in proporzione al loro deficit di vegetazione.'}
      </p>
    </>
  )
}

/** Fixed pseudo-random tree positions for the decorative sketch (as in the prototype), avoiding the two roads. */
const SKETCH_TREES: [number, number, number][] = (() => {
  let seed = 11
  const rnd = () => {
    seed = (seed * 9301 + 49297) % 233280
    return seed / 233280
  }
  const out: [number, number, number][] = []
  while (out.length < 70) {
    const x = 8 + rnd() * 144
    const y = 8 + rnd() * 104
    if ((y > 46 && y < 70) || (x > 64 && x < 88)) continue
    out.push([x, y, 3.5 + rnd() * 2.5])
  }
  return out
})()

function SketchCell({ count, label, value }: { count: number; label: string; value: number | null }) {
  return (
    <figure>
      <figcaption className="mb-1 flex justify-between font-mono text-[11px] text-ink-2">
        <span>{label}</span>
        <span>{pct(value)}</span>
      </figcaption>
      <svg viewBox="0 0 160 120" className="block w-full rounded bg-[#FAEEDA] dark:bg-[#3a2f24]" aria-hidden>
        <rect x="0" y="52" width="160" height="12" fill="#B4B2A9" opacity="0.6" />
        <rect x="70" y="0" width="12" height="120" fill="#B4B2A9" opacity="0.6" />
        {SKETCH_TREES.slice(0, count).map(([x, y, r], i) => (
          <circle key={i} cx={x} cy={y} r={r} fill="#3B6D11" fillOpacity={0.9} />
        ))}
      </svg>
    </figure>
  )
}

/** Decorative before/after sketch: more trees drawn as the slider grows (not to scale). */
function TreeSketch({ share, before, trees, max }: { share: number | null; before: number | null; trees: number; max: number }) {
  const n = Math.round((Math.min(trees, max) / max) * SKETCH_TREES.length)
  return (
    <div className="grid grid-cols-2 gap-2.5">
      <SketchCell count={0} label="Prima" value={before} />
      <SketchCell count={n} label="Dopo" value={share} />
    </div>
  )
}
