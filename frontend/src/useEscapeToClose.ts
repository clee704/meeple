import { useEffect } from 'react'

// Escape-to-close, shared by every dismissible overlay (confirm dialog, move
// log, match menu) so there's one place that defines what "dismiss" means.
export function useEscapeToClose(onClose: () => void, active: boolean) {
  useEffect(() => {
    if (!active) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, active])
}
