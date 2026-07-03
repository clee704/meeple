import { useEffect, useState, type ReactNode } from 'react'

interface Options {
  confirmLabel?: string
  danger?: boolean
}

interface Pending extends Required<Options> {
  message: string
  resolve: (ok: boolean) => void
}

// In-page replacement for window.confirm(): full-viewport backdrop (native
// dialogs leave the browser chrome undimmed on iOS and lead with a
// "localhost says…" header), styled buttons, Escape to cancel.
export function useConfirm(): [
  ReactNode,
  (message: string, opts?: Options) => Promise<boolean>,
] {
  const [pending, setPending] = useState<Pending | null>(null)

  const ask = (message: string, opts: Options = {}) =>
    new Promise<boolean>((resolve) => {
      setPending({ message, confirmLabel: opts.confirmLabel ?? 'OK', danger: opts.danger ?? false, resolve })
    })

  const close = (ok: boolean) => {
    pending?.resolve(ok)
    setPending(null)
  }

  useEffect(() => {
    if (!pending) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        pending.resolve(false)
        setPending(null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [pending])

  const dialog = pending && (
    <div className="modal-backdrop" onClick={() => close(false)}>
      <div className="modal" role="alertdialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <p>{pending.message}</p>
        <div className="action-row modal-actions">
          <button onClick={() => close(false)}>Cancel</button>
          <button
            className={pending.danger ? 'danger' : 'primary'}
            autoFocus
            onClick={() => close(true)}
          >
            {pending.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
  return [dialog, ask]
}
