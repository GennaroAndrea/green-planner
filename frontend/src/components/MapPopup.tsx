import type { Level } from '../api/types'
import { DISCLAIMERS } from '../i18n/it'
import { fmt, month, pct } from '../lib/format'
import { useApp } from '../state'

export interface PopupInfo {
  kind: 'not_analysed' | 'green' | 'traffic' | 'air' | 'industry'
  lng: number
  lat: number
  props: Record<string, unknown>
  level: Level
}

const num = (v: unknown): number | null => (v === null || v === undefined || v === '' ? null : Number(v))

function Title({ children }: { children: React.ReactNode }) {
  return <p className="font-serif text-[15px] leading-tight font-medium">{children}</p>
}
function Line({ children }: { children: React.ReactNode }) {
  return <p className="mt-1 text-xs text-ink-2">{children}</p>
}

/** Content of the map popups: context-layer features and non-analysed areas. */
export function PopupContent({ info }: { info: PopupInfo }) {
  const { meta } = useApp()
  const months = meta.inputs.traffic.months_used
  const p = info.props
  switch (info.kind) {
    case 'not_analysed':
      return (
        <div>
          <Title>{info.level === 'zone' ? String(p.name ?? 'Quartiere') : 'Cella'}: non analizzata</Title>
          <Line>
            {info.level === 'zone'
              ? DISCLAIMERS.population_coverage
              : 'Fuori dall’area di studio: poca popolazione e poca superficie urbanizzata (campagna, aree agricole), dove il dato del solo verde pubblico darebbe una priorità falsamente alta.'}
          </Line>
        </div>
      )
    case 'green':
      return (
        <div>
          <Title>{String(p.nome_area || 'Area verde pubblica')}</Title>
          <Line>Area verde pubblica (Comune di Bari)</Line>
        </div>
      )
    case 'traffic': {
      const v = num(p.vehicles_day)
      return (
        <div>
          <Title>{String(p.name ?? p.code)}</Title>
          <Line>Centralina {String(p.code)}</Line>
          <Line>
            {v === null
              ? 'Nessun dato valido nel periodo (solo letture a zero)'
              : `Media: ${fmt(v)} veicoli/giorno (somma dei sensori, ${month(months[0])} – ${month(months[months.length - 1])})`}
          </Line>
        </div>
      )
    }
    case 'air': {
      const pm25 = num(p.pm25_ugm3)
      return (
        <div>
          <Title>{String(p.station)}</Title>
          <Line>Medie annuali 2025 (ARPA Puglia)</Line>
          <Line>
            NO₂ {fmt(num(p.no2_ugm3))} · PM10 {fmt(num(p.pm10_ugm3))} · PM2.5{' '}
            {pm25 === null ? 'non misurato' : fmt(pm25)} µg/m³
          </Line>
          <Line>In media al {pct(num(p.pollution_ratio), 0)} dei limiti UE 2030</Line>
        </div>
      )
    }
    case 'industry': {
      const nox = num(p.nox_kg)
      const pm10 = num(p.pm10_kg)
      return (
        <div>
          <Title>{String(p.name)}</Title>
          <Line>
            {String(p.city)} · ultima dichiarazione E-PRTR {String(p.last_reporting_year)}
          </Line>
          <Line>
            {nox !== null && `NOₓ ${fmt(nox / 1000, 1)} t/anno`}
            {nox !== null && pm10 !== null && ' · '}
            {pm10 !== null && `PM10 ${fmt(pm10 / 1000, 1)} t/anno`}
          </Line>
          {!p.recent && <Line>Dichiarazione non recente: potrebbe non essere più attivo.</Line>}
          <p className="mt-1.5 text-[11px] text-ink-3">{DISCLAIMERS.no_causality}</p>
        </div>
      )
    }
  }
}
