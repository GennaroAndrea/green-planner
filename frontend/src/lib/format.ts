// Italian number formatting (UI locale).

// `useGrouping: 'always'`: Italian CLDR data doesn't group 4-digit numbers ("1678"), which reads
// inconsistently next to "36.113".
const nf = (digits: number) =>
  new Intl.NumberFormat('it-IT', { minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: 'always' })

const nf0 = nf(0)
const nf1 = nf(1)
const nf2 = nf(2)

export function fmt(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '–'
  return (digits === 0 ? nf0 : digits === 1 ? nf1 : digits === 2 ? nf2 : nf(digits)).format(value)
}

/** 0.209 → "20,9%" */
export function pct(share: number | null | undefined, digits = 1): string {
  if (share === null || share === undefined) return '–'
  return `${fmt(share * 100, digits)}%`
}

/** 4 → "4°" */
export function ord(n: number | null | undefined): string {
  return n === null || n === undefined ? '–' : `${n}°`
}

export function date(iso: string | null | undefined): string {
  if (!iso) return '–'
  return new Date(iso).toLocaleDateString('it-IT', { day: 'numeric', month: 'long', year: 'numeric' })
}

/** "2025-09" → "set 2025" */
export function month(ym: string): string {
  const [y, m] = ym.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleDateString('it-IT', { month: 'short', year: 'numeric' })
}
