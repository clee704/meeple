import { type HTMLAttributes, type ReactNode } from 'react'
import { useEscapeToClose } from './useEscapeToClose'

// A full-viewport backdrop that closes on outside click or Escape; the
// content stops propagation so a click inside doesn't dismiss it. The
// centered-dialog idiom behind the confirm dialog and the move-log overlay
// (the match menu is an anchored dropdown, not a centered dialog, so it only
// shares `useEscapeToClose`).
export function Overlay({
  onClose,
  backdropClassName = 'modal-backdrop',
  contentClassName,
  contentProps,
  children,
}: {
  onClose: () => void
  backdropClassName?: string
  contentClassName?: string
  contentProps?: HTMLAttributes<HTMLDivElement>
  children: ReactNode
}) {
  useEscapeToClose(onClose, true)
  return (
    <div className={backdropClassName} onClick={onClose}>
      <div className={contentClassName} onClick={(e) => e.stopPropagation()} {...contentProps}>
        {children}
      </div>
    </div>
  )
}
