import type { ComponentType } from 'react'
import type { HistoryEntry, LegalAction } from '../types'
import { KahunaBoard } from './KahunaBoard'
import { KuhnBoard } from './KuhnBoard'

// The per-game plugin contract: everything a renderer gets is either
// game-defined SPI output (observation/meta, opaque to the shell) or the
// generic turn plumbing. A renderer's one output is submitAction(id); it
// resolves true iff the server accepted the action, so a renderer can chain
// several actions in one gesture and stop as soon as one is rejected.
export interface GameRendererProps {
  observation: unknown
  meta: Record<string, unknown>
  seat: number
  yourTurn: boolean
  legalActions: LegalAction[]
  history: HistoryEntry[]
  result: Record<string, unknown> | null
  submitAction: (action: number) => Promise<boolean>
}

export const renderers: Record<string, ComponentType<GameRendererProps>> = {
  kahuna: KahunaBoard,
  kuhn: KuhnBoard,
}

// Seat labels for games where the lobby offers a seat choice, indexed by
// seat. Seat 0 always moves first (an engine-level rule), so for Kahuna the
// house rule is: Black plays first. Games without labels get a single
// create button that takes seat 0.
export const seatNames: Record<string, string[]> = {
  kahuna: ['Black', 'White'],
}
