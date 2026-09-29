import { useApp, type PanelTab } from '../state'
import { SHORT_DISCLAIMER } from '../i18n/it'
import DetailPanel from './DetailPanel'
import Simulator from './Simulator'
import WeightsRanking from './WeightsRanking'
import { cx } from '../lib/ui'

const TABS: { key: PanelTab; label: string }[] = [
  { key: 'detail', label: 'Zona' },
  { key: 'weights', label: 'Pesi e classifica' },
]

export function PanelTabs({ className }: { className?: string }) {
  const { panelTab, setPanelTab, selection } = useApp()
  return (
    <div role="tablist" aria-label="Pannello" className={cx('flex gap-5 border-b border-line', className)}>
      {TABS.map((t) => (
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
