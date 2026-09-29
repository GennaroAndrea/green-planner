// All user-facing Italian text lives here (the backend returns keys and numbers only).
import type { ClassKey, Detail, IndicatorKey, LayerKey } from '../api/types'
import { fmt, pct } from '../lib/format'

export const APP_NAME = 'Urban Green Planner' // placeholder until the team picks a name (Q14, Q41)

export const INDICATOR_LABEL: Record<IndicatorKey, string> = {
  pollution: 'Inquinamento',
  green_deficit: 'Carenza verde',
  traffic: 'Traffico',
  population: 'Popolazione',
  industry: 'Industria',
}

export const INDICATOR_HINT: Record<IndicatorKey, string> = {
  pollution: 'NO₂, PM10 e PM2.5 rispetto ai limiti UE 2030 (5 stazioni ARPA)',
  green_deficit: 'Quanta poca vegetazione c’è nella zona (satellite Sentinel-2, estate 2025)',
  traffic: 'Veicoli giornalieri misurati agli incroci vicini',
  population: 'Residenti per km² (persone esposte)',
  industry: 'Impianti E-PRTR entro 10 km: solo contesto',
}

export type MapTab = 'priority' | 'pollution' | 'traffic' | 'green_deficit' | 'population' | 'industry'

export const MAP_TABS: { key: MapTab; label: string }[] = [
  { key: 'priority', label: 'Priorità' },
  { key: 'pollution', label: 'Aria' },
  { key: 'traffic', label: 'Traffico' },
  { key: 'green_deficit', label: 'Verde' },
  { key: 'population', label: 'Popolazione' },
  { key: 'industry', label: 'Industria' },
]

export const SCORE_LEGEND: Record<Exclude<MapTab, 'priority' | 'industry'>, string> = {
  pollution: 'Inquinamento dell’aria (punteggio 0–100)',
  traffic: 'Traffico (punteggio 0–100)',
  green_deficit: 'Carenza di vegetazione, da satellite (punteggio 0–100)',
  population: 'Densità di popolazione (punteggio 0–100)',
}

export const CLASS_LABEL: Record<ClassKey, string> = {
  bassa: 'Bassa',
  media: 'Media',
  medio_alta: 'Medio-alta',
  alta: 'Alta',
}
export const CLASS_KEYS: ClassKey[] = ['bassa', 'media', 'medio_alta', 'alta']
export const classLabel = (cls: number) => (cls >= 1 && cls <= 4 ? CLASS_LABEL[CLASS_KEYS[cls - 1]] : 'Non analizzata')

export const LAYER_LABEL: Record<LayerKey, string> = {
  green: 'Aree verdi pubbliche (Comune)',
  traffic: 'Centraline di traffico',
  air: 'Stazioni ARPA qualità dell’aria',
  industry: 'Impianti industriali (E-PRTR)',
}

/** Disclaimer texts (keys from metadata.disclaimers, NFR-07). */
export const DISCLAIMERS: Record<string, string> = {
  relative_priority:
    'La priorità è relativa: confronta le zone di Bari tra loro (le classi sono quartili), non indica una soglia assoluta.',
  model_estimate:
    'Il numero di alberi è una stima di modello basata su parametri dichiarati, non un valore scientifico assoluto.',
  arpa_validation: 'I dati ARPA sulla qualità dell’aria sono soggetti a revisione da parte dell’ente.',
  no_causality: 'Gli impianti industriali indicano una pressione nelle vicinanze, mai la causa di un problema.',
  satellite_vegetation:
    'Il verde è misurato da satellite (Sentinel-2, estate 2025, pixel di 10 m): include verde pubblico e privato, ma alberi isolati e aiuole più piccoli di un pixel possono sfuggire.',
  population_coverage:
    'Torre a Mare non è analizzata: non compare nei dati di popolazione, quindi il suo punteggio sarebbe falsamente basso.',
}

export const SHORT_DISCLAIMER = 'Priorità relativa · stime di modello · dati ARPA soggetti a revisione'

function level(score: number): 'high' | 'mid' | 'low' {
  return score >= 67 ? 'high' : score >= 34 ? 'mid' : 'low'
}

const DRIVER_TITLE: Record<IndicatorKey, Record<'high' | 'mid' | 'low', string>> = {
  pollution: { high: 'Inquinamento dell’aria elevato', mid: 'Inquinamento dell’aria medio', low: 'Inquinamento dell’aria basso' },
  green_deficit: { high: 'Forte carenza di vegetazione', mid: 'Carenza di vegetazione media', low: 'Poca carenza di vegetazione' },
  traffic: { high: 'Traffico elevato', mid: 'Traffico medio', low: 'Traffico basso' },
  population: { high: 'Densità abitativa elevata', mid: 'Densità abitativa media', low: 'Densità abitativa bassa' },
  industry: { high: 'Pressione industriale', mid: 'Pressione industriale', low: 'Pressione industriale' },
}

/** "Traffico elevato (83/100): contribuisce per 18 punti all’indice." (methodology §11) */
export function driverSentence(key: IndicatorKey, score: number, contribution: number): string {
  return `${DRIVER_TITLE[key][level(score)]} (${fmt(score)}/100): contribuisce per ${fmt(contribution)} punti all’indice.`
}

/** Plain-language reading of an indicator's raw value. */
export function rawValueText(key: IndicatorKey, raw: number | null, targetShare: number): string {
  if (raw === null) return ''
  switch (key) {
    case 'pollution':
      return `In media al ${fmt(raw * 100)}% dei limiti UE 2030 (NO₂, PM10, PM2.5)`
    case 'green_deficit':
      return `Vegetazione (satellite, estate): ${pct(raw)} della superficie (obiettivo ${pct(targetShare, 0)})`
    case 'traffic':
      return raw <= 0
        ? 'Nessuna centralina entro ~900 m: traffico non misurato, non necessariamente assente'
        : `Circa ${fmt(Math.round(raw / 100) * 100)} veicoli/giorno agli incroci vicini (indice pesato per distanza)`
    case 'population':
      return `${fmt(raw)} abitanti/km²`
    default:
      return ''
  }
}

export const DROPPED_REASON: Record<string, string> = {
  too_few_facilities: 'escluso: troppo pochi impianti con dati recenti (solo contesto)',
}

export const ERRORS = {
  load: 'Impossibile caricare i dati. Verifica che il server sia attivo e riprova.',
  weights: 'Pesi non validi: almeno un indicatore deve avere un peso maggiore di 0.',
  generic: 'Si è verificato un errore. Riprova.',
}

export function detailTitle(d: Pick<Detail, 'level' | 'grid' | 'zone'>): string {
  if (d.level === 'zone') return d.zone?.name ?? 'Quartiere'
  return `Cella ${d.grid} m${d.zone?.name ? ` · ${d.zone.name}` : ''}`
}
