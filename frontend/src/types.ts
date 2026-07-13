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
  // Index into the full history that `history` starts at: a poll passing
  // `since` receives only newer entries and splices them on at this offset.
  history_from: number
  result: Record<string, unknown> | null
  forfeited_by: number | null
  turn_count: number
  elapsed_seconds: number
  turn_elapsed_seconds: number
  meta?: Record<string, unknown>
}

export interface GameInfo {
  game_id: string
  num_players: number
  // Lobby seat labels indexed by seat (from the game meta); null/absent when
  // the game offers no seat choice.
  seat_names?: string[] | null
}

// What a browser needs to keep acting as one seat of one match.
export interface Session {
  matchId: string
  gameId: string
  seat: number
  token: string
  joinCode?: string
}
