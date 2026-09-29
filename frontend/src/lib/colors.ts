import type { IndicatorKey } from '../api/types'

/**
 * Priority classes 1..4 (bassa → alta): the darkest 4 shades of the prototype's palette (Q34, Q46).
 * Index 0 = not analysed (drawn with the theme's no-data grey).
 */
export const CLASS_COLORS = ['', '#FAC775', '#F0997B', '#D85A30', '#993C1D'] as const

/** Sequential ramp for the indicator tabs (score 0–100), from the same palette. */
export const SCORE_RAMP: [number, string][] = [
  [0, '#FAEEDA'],
  [25, '#FAC775'],
  [50, '#F0997B'],
  [75, '#D85A30'],
  [100, '#993C1D'],
]

/** Indicator colours from the prototype (contribution bars, weight sliders). */
export const INDICATOR_COLORS: Record<IndicatorKey, string> = {
  pollution: '#0F6E56',
  green_deficit: '#7F77DD',
  traffic: '#D85A30',
  population: '#BA7517',
  industry: '#888780',
}

/** Green used for green areas / parks on the map (prototype). */
export const GREEN = '#639922'

export function classColor(cls: number): string {
  return CLASS_COLORS[cls] || 'var(--no-data)'
}

/** Colour of a 0–100 score on the sequential ramp (piecewise linear). */
export function scoreColor(score: number): string {
  const s = Math.max(0, Math.min(100, score))
  for (let i = 1; i < SCORE_RAMP.length; i++) {
    const [x1, c1] = SCORE_RAMP[i]
    const [x0, c0] = SCORE_RAMP[i - 1]
    if (s <= x1) return mix(c0, c1, (s - x0) / (x1 - x0))
  }
  return SCORE_RAMP[SCORE_RAMP.length - 1][1]
}

function mix(a: string, b: string, t: number): string {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16))
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16))
  return `#${pa.map((v, i) => Math.round(v + (pb[i] - v) * t).toString(16).padStart(2, '0')).join('')}`
}
