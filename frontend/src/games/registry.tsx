import { memo, type ComponentType, type ReactNode } from 'react'
import type { Envelope, HistoryEntry, LegalAction } from '../types'
import { KahunaBoard } from './KahunaBoard'
import { KuhnBoard } from './KuhnBoard'

// The per-game plugin contract: everything a renderer gets is either
// game-defined SPI output (observation/meta, opaque to the shell) or the
// generic turn plumbing. A renderer's one output is submitAction(id); it
// resolves to the accepted envelope, or false if the server rejected it, so
// a renderer can chain several actions in one gesture and stop as soon as a
// move is rejected or finishes the match.
export interface GameRendererProps {
  observation: unknown
  meta: Record<string, unknown>
  seat: number
  yourTurn: boolean
  legalActions: LegalAction[]
  history: HistoryEntry[]
  result: Record<string, unknown> | null
  submitAction: (action: number) => Promise<Envelope | false>
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
