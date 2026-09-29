import { useEffect, useState, useSyncExternalStore } from 'react'
import { getJson } from '../api/client'

export interface FetchState<T> {
  data: T | undefined
  error: Error | undefined
  loading: boolean
}

/**
 * Fetches `url` (null = don't fetch). Keeps the previous data while a new URL loads, so the map and
 * panels don't flash when the weights change.
 */
export function useFetch<T>(url: string | null): FetchState<T> {
  const [state, setState] = useState<FetchState<T> & { url: string | null }>({
    data: undefined,
    error: undefined,
    loading: url !== null,
    url,
  })
  // Reset "loading" synchronously when the URL changes (render-time state update).
  if (state.url !== url) setState({ ...state, url, loading: url !== null, error: undefined })

  useEffect(() => {
    if (url === null) return
    const ctrl = new AbortController()
    getJson<T>(url, ctrl.signal)
      .then((data) => setState((s) => (s.url === url ? { data, error: undefined, loading: false, url } : s)))
      .catch((error: Error) => {
        if (ctrl.signal.aborted) return
        setState((s) => (s.url === url ? { ...s, error, loading: false } : s))
      })
    return () => ctrl.abort()
  }, [url])

  return { data: state.data, error: state.error, loading: state.loading }
}

export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(query)
      m.addEventListener('change', cb)
      return () => m.removeEventListener('change', cb)
    },
    () => window.matchMedia(query).matches,
  )
}

/** Breakpoints of NFR-09: phone < 640 px, tablet 640–1024 px, desktop > 1024 px. */
export function useBreakpoint(): 'phone' | 'tablet' | 'desktop' {
  const sm = useMediaQuery('(min-width: 640px)')
  const lg = useMediaQuery('(min-width: 1024px)')
  return lg ? 'desktop' : sm ? 'tablet' : 'phone'
}

export type ThemePref = 'light' | 'dark' | null

/** Theme (Q39): follows the device setting until the user toggles it; the choice is remembered. */
export function useTheme(): [boolean, () => void] {
  const systemDark = useMediaQuery('(prefers-color-scheme: dark)')
  const [pref, setPref] = useState<ThemePref>(() => {
    try {
      const v = localStorage.getItem('theme')
      return v === 'light' || v === 'dark' ? v : null
    } catch {
      return null
    }
  })
  const dark = pref ? pref === 'dark' : systemDark
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])
  const toggle = () => {
    const next = dark ? 'light' : 'dark'
    setPref(next)
    try {
      localStorage.setItem('theme', next)
    } catch {
      // storage unavailable: the choice lasts for this session only
    }
  }
  return [dark, toggle]
}
