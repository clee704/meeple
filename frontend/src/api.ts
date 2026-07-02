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

export async function createMatch(gameId: string): Promise<Session> {
  const r = await post<{ match_id: string; game_id: string; seat: number; token: string; join_code: string }>(
    '/api/matches',
    { game_id: gameId },
  )
  return { matchId: r.match_id, gameId: r.game_id, seat: r.seat, token: r.token, joinCode: r.join_code }
}

export async function joinMatch(joinCode: string): Promise<Session> {
  const r = await post<{ match_id: string; game_id: string; seat: number; token: string }>(
    '/api/matches/join',
    { join_code: joinCode },
  )
  return { matchId: r.match_id, gameId: r.game_id, seat: r.seat, token: r.token }
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

// The session survives a refresh (and an accidental tab close) so a LAN
// match isn't orphaned by one, but only one match at a time per browser.
const SESSION_KEY = 'meeple.session'

export function loadSession(): Session | null {
  const raw = localStorage.getItem(SESSION_KEY)
  return raw ? (JSON.parse(raw) as Session) : null
}

export function saveSession(session: Session): void {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session))
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY)
}
