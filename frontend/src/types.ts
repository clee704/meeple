// Mirrors the backend's state envelope (meeple/web/matches.py). The
// `observation` and `meta` payloads are game-defined: the shell passes them
// through untyped and only the game's renderer knows their shape.

export interface LegalAction {
  action: number
  name: string
  meta: Record<string, unknown>
}

export interface HistoryEntry {
  actor: number
  meta: Record<string, unknown>
}

export type MatchStatus = 'waiting' | 'in_progress' | 'finished'

export interface Envelope {
  version: number
  game_id: string
  seat: number
  status: MatchStatus
  to_move: number | null
  your_turn: boolean
  observation: unknown
  legal_actions: LegalAction[]
  history: HistoryEntry[]
  result: Record<string, unknown> | null
  forfeited_by: number | null
  turn_count: number
  elapsed_seconds: number
  meta?: Record<string, unknown>
}

export interface GameInfo {
  game_id: string
  num_players: number
}

// What a browser needs to keep acting as one seat of one match.
export interface Session {
  matchId: string
  gameId: string
  seat: number
  token: string
  joinCode?: string
}
