import { memo, type ComponentType, type ReactNode } from 'react'
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
  // Optional: hand the shell a node to show in the match HUD (e.g. score /
  // round). Generic — the shell never inspects it; it just slots it into the
  // header on wide screens and the kebab menu on narrow ones. Pass null to
  // clear. A renderer that has nothing to add simply never calls it.
  reportHud?: (node: ReactNode) => void
}

// Memoized: MatchScreen re-renders every second for its clock tick, and a
// board (Kahuna's is ~800 lines) shouldn't re-execute its render body for a
// cosmetic tick that doesn't change any of its props.
export const renderers: Record<string, ComponentType<GameRendererProps>> = {
  kahuna: memo(KahunaBoard),
  kuhn: memo(KuhnBoard),
}

// Seat labels for games where the lobby offers a seat choice, indexed by
// seat. Seat 0 always moves first (an engine-level rule), so for Kahuna the
// house rule is: Black plays first. Games without labels get a single
// create button that takes seat 0.
export const seatNames: Record<string, string[]> = {
  kahuna: ['Black', 'White'],
}
