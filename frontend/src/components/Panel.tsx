import { lazy, Suspense } from 'react'
import { useApp, type PanelTab } from '../state'
import { api } from '../api/client'
import type { ChatStatus } from '../api/types'
import { CHAT, SHORT_DISCLAIMER } from '../i18n/it'
import { useFetch } from '../lib/hooks'
import DetailPanel from './DetailPanel'
import { Spinner } from './ui'
import Simulator from './Simulator'
import WeightsRanking from './WeightsRanking'
import { cx } from '../lib/ui'

// Loaded on first use: the chat and its Markdown renderer aren't needed for the map (NFR-04)
const Chat = lazy(() => import('./Chat'))

const TABS: { key: PanelTab; label: string }[] = [
  { key: 'detail', label: 'Zona' },
  { key: 'weights', label: 'Pesi e classifica' },
  { key: 'chat', label: CHAT.tab },
]

export function PanelTabs({ className }: { className?: string }) {
  const { panelTab, setPanelTab, selection } = useApp()
  // The chat tab exists only where the chat is configured (the demo laptop only, Q54)
  const chat = useFetch<ChatStatus>(api.chatStatus)
  const tabs = TABS.filter((t) => t.key !== 'chat' || chat.data?.available)
  return (
    <div role="tablist" aria-label="Pannello" className={cx('flex gap-5 border-b border-line', className)}>
      {tabs.map((t) => (
        <button
          key={t.key}
          role="tab"
          type="button"
          aria-selected={panelTab === t.key}
          onClick={() => setPanelTab(t.key)}
          className={cx(
            '-mb-px min-h-11 border-b-[1.5px] text-[14px] transition-colors',
            panelTab === t.key ? 'border-accent font-medium text-ink' : 'border-transparent text-ink-2 hover:text-ink',
          )}
        >
          {t.key === 'detail' && selection ? 'Scheda' : t.label}
        </button>
      ))}
    </div>
  )
}

/** Body of the side panel / bottom sheet. */
export function PanelBody() {
  const { panelTab, simulating } = useApp()
  if (panelTab === 'weights') return <WeightsRanking />
  if (panelTab === 'chat')
    return (
      <Suspense fallback={<Spinner />}>
        <Chat />
      </Suspense>
    )
  return simulating ? <Simulator /> : <DetailPanel />
}

/** Always-visible disclaimer line (NFR-07), with a link to the full text. */
export function DisclaimerBar({ className }: { className?: string }) {
  const { setMethodologyOpen } = useApp()
  return (
    <p className={cx('font-mono text-[11px] leading-snug text-ink-3', className)}>
      {SHORT_DISCLAIMER} ·{' '}
      <button type="button" onClick={() => setMethodologyOpen(true)} className="underline underline-offset-2 hover:text-ink">
        avvertenze
      </button>
    </p>
  )
}
