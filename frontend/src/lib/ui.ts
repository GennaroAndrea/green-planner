import { ord } from './format'

export function cx(...c: (string | false | null | undefined)[]): string {
  return c.filter(Boolean).join(' ')
}

export function rankInterval(p5: number | null, p95: number | null): string | null {
  if (p5 === null || p95 === null) return null
  return p5 === p95 ? `sempre ${ord(p5)} posto` : `tra ${ord(p5)} e ${ord(p95)} posto`
}

/** SVG paths for the inline icons (24×24, stroke). */
export const ICONS = {
  layers: 'M12 3 2 8l10 5 10-5-10-5Zm-10 9 10 5 10-5M2 16l10 5 10-5',
  sun: 'M12 4V2m0 20v-2m8-8h2M2 12h2m13.66-5.66 1.41-1.41M4.93 19.07l1.41-1.41m0-11.32L4.93 4.93m14.14 14.14-1.41-1.41M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z',
  info: 'M12 16v-4m0-4h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
  close: 'M18 6 6 18M6 6l12 12',
  back: 'M15 18l-6-6 6-6',
  chevronDown: 'M6 9l6 6 6-6',
  chevronLeft: 'M15 18l-6-6 6-6',
  chevronRight: 'M9 18l6-6-6-6',
  check: 'M20 6 9 17l-5-5',
  download: 'M12 3v12m0 0-4-4m4 4 4-4M4 21h16',
  tree: 'M12 22v-6m0 0c-3.87 0-7-2.24-7-5 0-1.93 1.53-3.6 3.77-4.44A4.5 4.5 0 0 1 12 2a4.5 4.5 0 0 1 3.23 4.56C17.47 7.4 19 9.07 19 11c0 2.76-3.13 5-7 5Z',
  legend: 'M4 6h2m4 0h10M4 12h2m4 0h10M4 18h2m4 0h10',
  sliders: 'M4 21v-7m0-4V3m8 18v-9m0-4V3m8 18v-5m0-4V3M1 14h6m2-6h6m2 8h6',
}
