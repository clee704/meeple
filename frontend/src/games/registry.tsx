import type { ComponentType } from 'react'
import type { HistoryEntry, LegalAction } from '../types'
import { KuhnBoard } from './KuhnBoard'

// The per-game plugin contract: everything a renderer gets is either
// game-defined SPI output (observation/meta, opaque to the shell) or the
// generic turn plumbing. A renderer's one output is submitAction(id).
export interface GameRendererProps {
  observation: unknown
  meta: Record<string, unknown>
  seat: number
  yourTurn: boolean
  legalActions: LegalAction[]
  history: HistoryEntry[]
  result: Record<string, unknown> | null
  submitAction: (action: number) => void
}

export const renderers: Record<string, ComponentType<GameRendererProps>> = {
  kuhn: KuhnBoard,
}
