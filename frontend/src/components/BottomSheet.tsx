import { useEffect, useRef, useState, type ReactNode } from 'react'
import { cx } from '../lib/ui'

export type SheetSnap = 'peek' | 'half' | 'full'

export const PEEK_PX = 150

function snapHeight(snap: SheetSnap, available: number): number {
  if (snap === 'peek') return PEEK_PX
  if (snap === 'half') return Math.round(available * 0.52)
  return available - 8
}

/**
 * Draggable bottom sheet for phones (FR-50): peek / half / full. Only the grip area (handle + `head`)
 * drags, so the body scrolls normally.
 */
export default function BottomSheet({
  snap,
  onSnap,
  head,
  children,
  footer,
}: {
  snap: SheetSnap
  onSnap: (s: SheetSnap) => void
  head: ReactNode
  children: ReactNode
  footer: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [available, setAvailable] = useState(600)
  const [drag, setDrag] = useState<{ startY: number; startH: number; h: number } | null>(null)

  useEffect(() => {
    const parent = ref.current?.parentElement
    if (!parent) return
    const ro = new ResizeObserver(() => setAvailable(parent.clientHeight))
    ro.observe(parent)
    return () => ro.disconnect()
  }, [])

  const height = drag ? drag.h : snapHeight(snap, available)

  const onPointerDown = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest('button:not([data-grip])')) return
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    setDrag({ startY: e.clientY, startH: height, h: height })
  }
  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag) return
    const h = Math.max(PEEK_PX - 40, Math.min(available - 8, drag.startH + drag.startY - e.clientY))
    setDrag({ ...drag, h })
  }
  const onPointerUp = (e: React.PointerEvent) => {
    if (!drag) return
    const moved = Math.abs(e.clientY - drag.startY)
    setDrag(null)
    if (moved < 6) {
      // A tap on the grip cycles peek → half → full → peek.
      onSnap(snap === 'peek' ? 'half' : snap === 'half' ? 'full' : 'peek')
      return
    }
    const snaps: SheetSnap[] = ['peek', 'half', 'full']
    const velocityHint = e.clientY < drag.startY ? 30 : -30 // favour the drag direction
    const target = drag.h + velocityHint
    const best = snaps.reduce((a, b) =>
      Math.abs(snapHeight(b, available) - target) < Math.abs(snapHeight(a, available) - target) ? b : a,
    )
    onSnap(best)
  }

  return (
    <div
      ref={ref}
      className={cx(
        'absolute inset-x-0 bottom-0 z-30 flex flex-col rounded-t-2xl border-t border-line bg-surface-1 shadow-[0_-4px_20px_rgb(0_0_0/0.12)]',
        !drag && 'transition-[height] duration-200 ease-out',
      )}
      style={{ height }}
    >
      <div
        className="shrink-0 touch-none px-4 select-none"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => setDrag(null)}
      >
        <button
          type="button"
          data-grip
          aria-label={snap === 'full' ? 'Riduci il pannello' : 'Espandi il pannello'}
          className="flex h-5 w-full items-center justify-center"
        >
          <span className="h-1 w-10 rounded-full bg-line-strong" />
        </button>
        {head}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pt-3 pb-4">{children}</div>
      <div className="shrink-0 border-t border-line px-4 py-1.5 pb-[max(0.375rem,env(safe-area-inset-bottom))]">{footer}</div>
    </div>
  )
}
