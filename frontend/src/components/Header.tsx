import { Listbox, ListboxButton, ListboxOption, ListboxOptions } from '@headlessui/react'
import { APP_NAME } from '../i18n/it'
import { useApp } from '../state'
import { Icon } from './ui'
import { cx, ICONS } from '../lib/ui'

/** Comune/year selectors (FR-48): only Bari and the latest data are enabled. */
const COMUNI = [
  { value: 'bari', label: 'Bari', disabled: false },
  { value: 'copertino', label: 'Copertino', disabled: true },
  { value: 'lecce', label: 'Lecce', disabled: true },
]
const YEARS = [
  { value: 'latest', label: 'Dati 2026', disabled: false },
  { value: '2025', label: 'Dati 2025', disabled: true },
  { value: '2024', label: 'Dati 2024', disabled: true },
]

function Picker({ label, options }: { label: string; options: typeof COMUNI }) {
  const current = options.find((o) => !o.disabled)!
  return (
    <Listbox value={current.value} onChange={() => {}}>
      <ListboxButton
        aria-label={label}
        className="-mx-1 inline-flex min-h-8 items-center gap-0.5 rounded px-1 font-mono text-[11px] text-ink-2 hover:bg-surface-2 hover:text-ink"
      >
        {current.label}
        <Icon d={ICONS.chevronDown} className="size-3" />
      </ListboxButton>
      <ListboxOptions
        anchor={{ to: 'bottom start', gap: 4 }}
        className="z-50 w-48 rounded-xl border border-line bg-surface-1 p-1 text-sm text-ink shadow-lg focus:outline-none"
      >
        {options.map((o) => (
          <ListboxOption
            key={o.value}
            value={o.value}
            disabled={o.disabled}
            className="flex min-h-11 cursor-pointer items-center justify-between rounded-lg px-2.5 data-disabled:cursor-not-allowed data-focus:bg-surface-2 data-disabled:text-ink-3"
          >
            {o.label}
            {o.disabled ? <span className="text-[11px]">prossimamente</span> : <Icon d={ICONS.check} className="size-4" />}
          </ListboxOption>
        ))}
      </ListboxOptions>
    </Listbox>
  )
}

export default function Header({ dark, toggleTheme }: { dark: boolean; toggleTheme: () => void }) {
  const { setMethodologyOpen } = useApp()
  return (
    <header className="z-20 flex shrink-0 items-center justify-between gap-3 border-b border-line bg-surface-1 px-4 py-1.5 sm:px-5">
      <div className="flex min-w-0 items-center gap-2.5">
        <Logo />
        <div className="min-w-0">
          <h1 className="truncate font-serif text-[17px] leading-tight font-medium sm:text-[19px]">{APP_NAME}</h1>
          <div className="flex items-center gap-1 font-mono text-[11px] text-ink-2">
            <Picker label="Comune" options={COMUNI} />
            <span aria-hidden>·</span>
            <Picker label="Anno dei dati" options={YEARS} />
            <span aria-hidden className="hidden md:inline">
              · Indice di Priorità di Forestazione
            </span>
          </div>
        </div>
      </div>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => setMethodologyOpen(true)}
          aria-label="Metodologia e fonti"
          className={cx('flex min-h-11 items-center gap-1.5 rounded-lg px-2.5 text-sm text-ink-2 hover:bg-surface-2 hover:text-ink')}
        >
          <Icon d={ICONS.info} />
          <span className="hidden md:inline">Metodologia e fonti</span>
        </button>
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={dark ? 'Tema chiaro' : 'Tema scuro'}
          title={dark ? 'Tema chiaro' : 'Tema scuro'}
          className="flex size-11 items-center justify-center rounded-lg text-ink-2 hover:bg-surface-2 hover:text-ink"
        >
          <Icon d={dark ? ICONS.sun : ICONS.moon} />
        </button>
      </div>
    </header>
  )
}

function Logo() {
  return (
    <svg viewBox="0 0 32 32" className="size-8 shrink-0" aria-hidden>
      <rect width="32" height="32" rx="7" fill="#993C1D" />
      <rect x="6" y="6" width="9" height="9" fill="#FAC775" />
      <rect x="17" y="6" width="9" height="9" fill="#D85A30" />
      <rect x="6" y="17" width="9" height="9" fill="#F0997B" />
      <circle cx="21.5" cy="21.5" r="4.5" fill="#639922" />
    </svg>
  )
}
