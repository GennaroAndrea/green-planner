import type { ButtonHTMLAttributes, ReactNode } from 'react'
import type { ItemSensitivity } from '../api/types'
import { cx } from '../lib/ui'

/** Small uppercase-free "mono" caption, as in the prototype. */
export function Caption({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cx('font-mono text-[11px] leading-snug text-ink-2', className)}>{children}</p>
}

export function Button({
  variant = 'secondary',
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' }) {
  return (
    <button
      type="button"
      {...props}
      className={cx(
        'inline-flex min-h-11 items-center justify-center gap-1.5 rounded-lg px-3.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        variant === 'primary' && 'bg-ink text-surface-1 hover:opacity-90',
        variant === 'secondary' && 'border border-line-strong bg-surface-1 text-ink hover:bg-surface-2',
        variant === 'ghost' && 'text-ink-2 hover:bg-surface-2 hover:text-ink',
        className,
      )}
    />
  )
}

/** Segmented control (radio group). Every option is a ≥ 44 px touch target on phones. */
export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  label,
  className,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
  label: string
  className?: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cx('flex rounded-lg bg-surface-2 p-0.5', className)}>
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={cx(
            'min-h-10 flex-1 rounded-md px-2.5 text-[13px] whitespace-nowrap transition-colors sm:min-h-8',
            o.value === value ? 'bg-surface-1 font-medium text-ink shadow-sm' : 'text-ink-2 hover:text-ink',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** Robustness badge + rank interval (FR-51). */
export function RobustBadge({ s, compact = false }: { s: Pick<ItemSensitivity, 'robust' | 'applicable'>; compact?: boolean }) {
  if (!s.applicable || s.robust === null) {
    return (
      <span className="inline-flex items-center rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-ink-2">
        {compact ? 'n/a' : 'Robustezza non applicabile'}
      </span>
    )
  }
  return s.robust ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-ok-soft px-2 py-0.5 text-[11px] font-medium text-ok">
      <Dot /> {compact ? 'Robusta' : 'Priorità robusta'}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full bg-warn-soft px-2 py-0.5 text-[11px] font-medium text-warn">
      <Dot /> {compact ? 'Sensibile' : 'Priorità sensibile ai pesi'}
    </span>
  )
}

function Dot() {
  return <span aria-hidden className="inline-block size-1.5 rounded-full bg-current" />
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cx('inline-block size-4 animate-spin rounded-full border-2 border-line-strong border-t-transparent', className)}
    />
  )
}

export function Icon({ d, className }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden className={cx('size-5', className)}>
      <path d={d} />
    </svg>
  )
}
