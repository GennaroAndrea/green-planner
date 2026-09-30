import type { GridSize, IndicatorKey, Level, WeightsPp } from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** GET a JSON endpoint. The backend's `detail` (English, for developers) stays in the error message. */
export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, { signal })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      // not JSON: keep the status text
    }
    throw new ApiError(res.status, String(detail))
  }
  return res.json() as Promise<T>
}

/**
 * `weights=pollution:25,green_deficit:35,...` for custom weights, or null for the defaults
 * (the backend then serves the precomputed results).
 */
export function weightsParam(weights: WeightsPp, defaults: WeightsPp, active: IndicatorKey[]): string | null {
  const isDefault = active.every((k) => (weights[k] ?? 0) === (defaults[k] ?? 0))
  if (isDefault) return null
  return active.map((k) => `${k}:${weights[k] ?? 0}`).join(',')
}

function query(params: Record<string, string | number | null | undefined>): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined) q.set(k, String(v))
  const s = q.toString()
  return s ? `?${s}` : ''
}

export const api = {
  metadata: () => '/api/metadata',
  zones: (w: string | null) => `/api/zones${query({ weights: w })}`,
  cells: (grid: GridSize, w: string | null) => `/api/cells${query({ grid, weights: w })}`,
  detail: (level: Level, id: string, w: string | null) =>
    `/api/${level === 'zone' ? 'zones' : 'cells'}/${encodeURIComponent(id)}${query({ weights: w })}`,
  simulate: (level: Level, id: string, trees: number, w: string | null) =>
    `/api/${level === 'zone' ? 'zones' : 'cells'}/${encodeURIComponent(id)}/simulate${query({ trees, weights: w })}`,
  ranking: (level: Level, grid: GridSize, limit: number | null, w: string | null) =>
    `/api/ranking${query({ level, grid: level === 'cell' ? grid : null, limit, weights: w })}`,
  sensitivity: (level: Level, grid: GridSize, w: string | null) =>
    `/api/sensitivity${query({ level, grid: level === 'cell' ? grid : null, weights: w })}`,
  layer: (key: string) => `/api/layers/${key}`,
  chatStatus: '/api/chat/status',
  chatSession: '/api/chat/session',
  chat: '/api/chat',
  chatHistory: '/api/chat/history',
}
