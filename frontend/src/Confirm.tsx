import { useState, type ReactNode } from 'react'
import { Overlay } from './Overlay'

interface Options {
  confirmLabel?: string
  danger?: boolean
  // An alert: a single dismiss button, no Cancel (for "you must pick a card
  // first"-style notices where there's nothing to decline).
  alert?: boolean
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
      setPending({
        message,
        confirmLabel: opts.confirmLabel ?? 'OK',
        danger: opts.danger ?? false,
        alert: opts.alert ?? false,
        resolve,
      })
    })

  const close = (ok: boolean) => {
    pending?.resolve(ok)
    setPending(null)
  }

  const dialog = pending && (
    <Overlay
      onClose={() => close(false)}
      contentClassName="modal"
      contentProps={{ role: 'alertdialog', 'aria-modal': true }}
    >
      <p>{pending.message}</p>
      <div className="action-row modal-actions">
        {!pending.alert && <button onClick={() => close(false)}>Cancel</button>}
        <button className={pending.danger ? 'danger' : 'primary'} autoFocus onClick={() => close(true)}>
          {pending.confirmLabel}
        </button>
      </div>
    </Overlay>
  )
  return [dialog, ask]
}
