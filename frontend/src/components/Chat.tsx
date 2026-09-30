import { useEffect, useRef, useState, type FormEvent } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import 'katex/dist/katex.min.css'
import { ApiError, api, getJson } from '../api/client'
import type { ChatExchange, ChatStatus } from '../api/types'
import { CHAT } from '../i18n/it'
import { pct } from '../lib/format'
import { streamChat } from '../lib/sse'
import { ICONS, cx } from '../lib/ui'
import { Button, Caption, Icon, Spinner } from './ui'

interface Message {
  question: string
  answer: string
  status: string | null
  pending: boolean
  unverified: string[]
  error: string | null
}

/** "Chiedi" panel tab (FR-54, Q56): code entry, then the streamed chat. */
export default function Chat() {
  const [status, setStatus] = useState<ChatStatus | null>(null)
  const [failed, setFailed] = useState(false)
  const [expired, setExpired] = useState(false)

  const refresh = () =>
    getJson<ChatStatus>(api.chatStatus)
      .then((s) => {
        setStatus(s)
        setFailed(false)
      })
      .catch(() => setFailed(true))

  useEffect(() => {
    void refresh()
  }, [])

  if (failed) return <p className="text-sm text-warn">{CHAT.unavailable}</p>
  if (!status) return <Spinner />
  if (!status.available) return <p className="text-sm text-ink-2">{CHAT.unavailable}</p>
  if (!status.authenticated) return <CodeForm onDone={setStatus} notice={expired ? CHAT.expired : undefined} />
  return (
    <Conversation
      status={status}
      setStatus={setStatus}
      onExpired={() => {
        setExpired(true)
        void refresh()
      }}
    />
  )
}

function CodeForm({ onDone, notice }: { onDone: (s: ChatStatus) => void; notice?: string }) {
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(api.chatSession, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      })
      if (res.ok) onDone(await res.json())
      else setError(res.status === 503 ? CHAT.unavailable : CHAT.codeInvalid)
    } catch {
      setError(CHAT.error)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <h2 className="font-serif text-lg font-medium">{CHAT.title}</h2>
      <p className="text-sm text-ink-2">{CHAT.intro}</p>
      {notice && <p className="rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn">{notice}</p>}
      <label htmlFor="chat-code" className="block text-sm font-medium">
        {CHAT.codeLabel}
      </label>
      <div className="flex gap-2">
        <input
          id="chat-code"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={20}
          placeholder="XXXX-XXXX"
          className="min-h-11 min-w-0 flex-1 rounded-lg border border-line-strong bg-surface-1 px-3 font-mono text-base tracking-wider focus:border-accent focus:outline-none"
        />
        <Button type="submit" variant="primary" disabled={busy || normalise(code).length < 8}>
          {busy ? <Spinner className="border-surface-1 border-t-transparent" /> : CHAT.codeSubmit}
        </Button>
      </div>
      {error && <p className="text-sm text-warn">{error}</p>}
      <Caption>{CHAT.codeHint}</Caption>
    </form>
  )
}

const normalise = (code: string) => code.replace(/[^A-Za-z0-9]/g, '')

function Conversation({
  status,
  setStatus,
  onExpired,
}: {
  status: ChatStatus
  setStatus: (s: ChatStatus) => void
  onExpired: () => void
}) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const pending = messages.some((m) => m.pending)
  const spent = status.spent_usd ?? 0
  const budget = status.budget_usd ?? 0
  const overBudget = budget > 0 && spent >= budget

  useEffect(() => {
    getJson<ChatExchange[]>(api.chatHistory)
      .then((h) =>
        setMessages(h.map((x) => ({ question: x.question, answer: x.answer, status: null, pending: false, unverified: x.unverified, error: null }))),
      )
      .catch(() => {})
  }, [])

  // Follow the answer as it streams. Only the panel's own scroll area moves: scrollIntoView
  // would also shift the bottom sheet's overflow-hidden containers.
  useEffect(() => {
    const area = scrollParent(endRef.current)
    area?.scrollTo({ top: area.scrollHeight })
  }, [messages])

  const update = (fn: (m: Message) => Message) => setMessages((ms) => ms.map((m, i) => (i === ms.length - 1 ? fn(m) : m)))

  async function ask(question: string) {
    const q = question.trim()
    if (!q || pending || overBudget) return
    setInput('')
    setNotice(null)
    setMessages((ms) => [...ms, { question: q, answer: '', status: null, pending: true, unverified: [], error: null }])
    try {
      await streamChat(api.chat, q, (e) => {
        if (e.event === 'delta') update((m) => ({ ...m, answer: m.answer + e.data.text, status: null }))
        else if (e.event === 'status') update((m) => ({ ...m, status: e.data.text }))
        else if (e.event === 'error') update((m) => ({ ...m, error: e.data.message }))
        else if (e.event === 'done') {
          update((m) => ({ ...m, unverified: e.data.unverified }))
          if (e.data.spent_usd !== null) setStatus({ ...status, spent_usd: e.data.spent_usd })
        }
      })
    } catch (err) {
      const code = err instanceof ApiError ? err.status : 0
      if (code === 401) {
        onExpired()
        return
      }
      const msg = code === 402 ? CHAT.creditOver : code === 409 ? CHAT.busy : code === 503 ? CHAT.unavailable : CHAT.error
      update((m) => ({ ...m, error: msg }))
      if (code === 402) setStatus({ ...status, spent_usd: Math.max(spent, budget) })
    } finally {
      update((m) => ({ ...m, pending: false, status: null }))
    }
  }

  async function clear() {
    try {
      await fetch(api.chatHistory, { method: 'DELETE' })
      setMessages([])
    } catch {
      setNotice(CHAT.error)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <Caption>{CHAT.credit(pct(budget > 0 ? Math.min(1, spent / budget) : 0, 0))}</Caption>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2" aria-hidden>
            <div
              className={cx('h-full rounded-full', overBudget ? 'bg-warn' : 'bg-accent')}
              style={{ width: `${budget > 0 ? Math.min(100, (100 * spent) / budget) : 0}%` }}
            />
          </div>
        </div>
        <Button variant="ghost" onClick={clear} disabled={pending || messages.length === 0} className="min-h-9 px-2.5 text-xs">
          {CHAT.newChat}
        </Button>
      </div>

      {messages.length === 0 && (
        <div className="space-y-2">
          <p className="text-sm text-ink-2">{CHAT.intro}</p>
          <div className="flex flex-col gap-2">
            {CHAT.examples.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => ask(q)}
                disabled={overBudget}
                className="min-h-11 rounded-lg border border-line bg-surface-1 px-3 py-2 text-left text-sm text-ink hover:bg-surface-2 disabled:opacity-50"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      <ol className="space-y-4" aria-live="polite">
        {messages.map((m, i) => (
          <li key={i} className="space-y-2">
            <p className="ml-8 rounded-xl rounded-br-sm bg-surface-2 px-3 py-2 text-sm whitespace-pre-wrap">{m.question}</p>
            <div className="text-[14px] leading-relaxed">
              {m.answer ? <Markdown text={m.answer} /> : null}
              {m.pending && !m.answer && (
                <p className="flex items-center gap-2 text-sm text-ink-2">
                  <Spinner className="size-3" /> {m.status ?? CHAT.thinking}
                </p>
              )}
              {m.pending && m.answer && m.status && (
                <p className="mt-1 flex items-center gap-2 text-xs text-ink-2">
                  <Spinner className="size-3" /> {m.status}
                </p>
              )}
              {m.error && <p className="mt-1 text-sm text-warn">{m.error}</p>}
              {m.unverified.length > 0 && (
                <p className="mt-2 rounded-lg bg-warn-soft px-3 py-2 text-xs text-warn">{CHAT.unverified(m.unverified)}</p>
              )}
            </div>
          </li>
        ))}
      </ol>
      <div ref={endRef} />

      {notice && <p className="text-sm text-warn">{notice}</p>}
      {overBudget ? (
        <p className="rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn">{CHAT.creditOver}</p>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void ask(input)
          }}
          className="flex items-end gap-2"
        >
          <label htmlFor="chat-input" className="sr-only">
            {CHAT.placeholder}
          </label>
          <textarea
            id="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void ask(input)
              }
            }}
            rows={2}
            maxLength={1000}
            placeholder={CHAT.placeholder}
            className="min-h-11 min-w-0 flex-1 resize-none rounded-lg border border-line-strong bg-surface-1 px-3 py-2 text-base focus:border-accent focus:outline-none sm:text-sm"
          />
          <Button type="submit" variant="primary" disabled={pending || !input.trim()} aria-label={CHAT.send} className="px-3">
            {pending ? <Spinner className="border-surface-1 border-t-transparent" /> : <Icon d={ICONS.send} />}
          </Button>
        </form>
      )}
      <Caption>{CHAT.disclaimer}</Caption>
    </div>
  )
}

function scrollParent(el: HTMLElement | null): HTMLElement | null {
  for (let p = el?.parentElement; p; p = p.parentElement) {
    const { overflowY } = getComputedStyle(p)
    if (overflowY === 'auto' || overflowY === 'scroll') return p
  }
  return null
}

/**
 * The assistant's Markdown (react-markdown + GitHub tables), styled for the narrow panel. Raw
 * HTML in the text is not rendered (react-markdown's default), and links open in a new tab.
 * Headings are kept small: a chat answer shouldn't shout.
 */
const MD: Components = {
  p: ({ children }) => <p>{children}</p>,
  h1: ({ children }) => <p className="font-serif text-[16px] font-semibold">{children}</p>,
  h2: ({ children }) => <p className="font-serif text-[15px] font-semibold">{children}</p>,
  h3: ({ children }) => <p className="font-semibold">{children}</p>,
  h4: ({ children }) => <p className="font-semibold">{children}</p>,
  ul: ({ children }) => <ul className="list-disc space-y-1 pl-5 marker:text-ink-3">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5 marker:text-ink-3">{children}</ol>,
  li: ({ children }) => <li className="pl-0.5">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent underline underline-offset-2">
      {children}
    </a>
  ),
  code: ({ children, className }) =>
    className ? (
      <code className={className}>{children}</code>
    ) : (
      <code className="rounded bg-surface-2 px-1 py-0.5 font-mono text-[12.5px]">{children}</code>
    ),
  pre: ({ children }) => (
    <pre className="overflow-x-auto rounded-lg bg-surface-2 px-3 py-2 font-mono text-[12.5px] leading-snug">{children}</pre>
  ),
  blockquote: ({ children }) => <blockquote className="border-l-2 border-line-strong pl-3 text-ink-2">{children}</blockquote>,
  hr: () => <hr className="border-line" />,
  table: ({ children }) => (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[13px]">{children}</table>
    </div>
  ),
  // Numbers never break inside a cell: right-aligned (numeric) columns don't wrap at all
  th: ({ children, style }) => (
    <th style={style} className="border-b border-line-strong px-2 py-1 text-left font-semibold whitespace-nowrap">
      {children}
    </th>
  ),
  td: ({ children, style }) => (
    <td
      style={style}
      className={cx(
        'border-b border-line px-2 py-1 align-top [overflow-wrap:normal]',
        style?.textAlign === 'right' && 'whitespace-nowrap',
      )}
    >
      {children}
    </td>
  ),
}

/**
 * Italian decimal commas inside LaTeX: `0,333` would render as "0, 333" (a comma is punctuation
 * in math mode), so digit,digit becomes digit{,}digit within $…$ and $$…$$ (Q59).
 */
function fixMathCommas(text: string): string {
  return text.replace(/(\$\$[\s\S]*?\$\$|\$[^$\n]+?\$)/g, (math) => math.replace(/(\d),(?=\d)/g, '$1{,}'))
}

// Broken LaTeX shows as plain text in a muted colour instead of throwing
const KATEX = { throwOnError: false, strict: false, errorColor: 'var(--text-secondary)' }

function Markdown({ text }: { text: string }) {
  return (
    <div className="chat-md space-y-2.5 [overflow-wrap:anywhere]">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[[rehypeKatex, KATEX]]} components={MD}>
        {fixMathCommas(text)}
      </ReactMarkdown>
    </div>
  )
}
