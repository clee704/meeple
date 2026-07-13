import type { Envelope, GameInfo, Session } from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, init)
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      detail = (await resp.json()).detail ?? detail
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(resp.status, detail)
  }
  return resp.json()
}

function post<T>(path: string, body: unknown, token?: string): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'X-Seat-Token': token } : {}),
    },
    body: JSON.stringify(body),
  })
}

export function listGames(): Promise<GameInfo[]> {
  return request('/api/games')
}

export async function createMatch(gameId: string, seat = 0): Promise<Session> {
  const r = await post<{ match_id: string; game_id: string; seat: number; token: string; join_code: string }>(
    '/api/matches',
    { game_id: gameId, seat },
  )
  // A server that predates the seat field ignores it and seats you at 0.
  // Refuse to enter the match in the wrong color — fail loudly instead.
  if (r.seat !== seat)
    throw new ApiError(0, `server seated you at seat ${r.seat}, not ${seat} — restart the server (it's running an older build) and try again`)
  return {
    matchId: r.match_id,
    gameId: r.game_id,
    seat: r.seat,
    token: r.token,
    joinCode: r.join_code,
  }
}

export async function joinMatch(joinCode: string): Promise<Session> {
  const r = await post<{
    match_id: string
    game_id: string
    seat: number
    token: string
    join_code: string
  }>('/api/matches/join', { join_code: joinCode })
  return {
    matchId: r.match_id,
    gameId: r.game_id,
    seat: r.seat,
    token: r.token,
    joinCode: r.join_code,
  }
}

export function getState(session: Session, since?: number): Promise<Envelope | { changed: false; version: number }> {
  const query = since === undefined ? '' : `?since=${since}`
  return request(`/api/matches/${session.matchId}/state${query}`, {
    headers: { 'X-Seat-Token': session.token },
  })
}

export function postAction(session: Session, action: number): Promise<Envelope> {
  return post(`/api/matches/${session.matchId}/actions`, { action }, session.token)
}

export function leaveMatch(session: Session): Promise<Envelope> {
  return post(`/api/matches/${session.matchId}/leave`, undefined, session.token)
}

// The active session is tab-scoped (sessionStorage, survives a refresh) so
// two tabs of one browser can hold two different seats — e.g. the creator's
// tab stays White when a join link is opened in another tab. localStorage
// keeps the latest copy as a fallback so a freshly opened tab can resume a
// match after an accidental tab close.
const SESSION_KEY = 'meeple.session'

function isStoredSession(value: unknown): value is Session {
  if (!value || typeof value !== 'object') return false
  const s = value as Record<string, unknown>
  return (
    typeof s.matchId === 'string' &&
    typeof s.gameId === 'string' &&
    Number.isInteger(s.seat) &&
    typeof s.token === 'string' &&
    (s.joinCode === undefined || typeof s.joinCode === 'string')
  )
}

function parseStoredSession(raw: string | null): Session | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    return isStoredSession(parsed) ? parsed : null
  } catch {
    return null
  }
}

export function loadSession({
  includeSharedFallback = true,
}: {
  includeSharedFallback?: boolean
} = {}): Session | null {
  const tabRaw = sessionStorage.getItem(SESSION_KEY)
  const tabSession = parseStoredSession(tabRaw)
  if (tabRaw !== null && !tabSession) sessionStorage.removeItem(SESSION_KEY)
  if (tabSession) return tabSession
  if (!includeSharedFallback) return null

  const sharedRaw = localStorage.getItem(SESSION_KEY)
  const sharedSession = parseStoredSession(sharedRaw)
  if (sharedRaw !== null && !sharedSession) localStorage.removeItem(SESSION_KEY)
  if (sharedSession && sharedRaw) sessionStorage.setItem(SESSION_KEY, sharedRaw)
  return sharedSession
}

export function saveSession(session: Session): void {
  const raw = JSON.stringify(session)
  sessionStorage.setItem(SESSION_KEY, raw)
  localStorage.setItem(SESSION_KEY, raw)
}

export function clearSession(): void {
  const own = sessionStorage.getItem(SESSION_KEY)
  sessionStorage.removeItem(SESSION_KEY)
  // Leave the shared fallback copy alone if another tab wrote it since.
  if (own === null || localStorage.getItem(SESSION_KEY) === own) localStorage.removeItem(SESSION_KEY)
}
