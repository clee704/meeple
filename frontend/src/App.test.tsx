import { StrictMode } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Session } from './types'

const api = vi.hoisted(() => ({
  clearSession: vi.fn(),
  joinMatch: vi.fn(),
  loadSession: vi.fn(() => null),
  saveSession: vi.fn(),
}))

vi.mock('./api', () => api)
vi.mock('./Lobby', () => ({ Lobby: () => <div>Lobby</div> }))
vi.mock('./MatchScreen', () => ({
  MatchScreen: ({ session }: { session: Session }) => <div>Match {session.matchId}</div>,
}))

import App from './App'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

describe('hash joins', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    history.replaceState(null, '', '/')
  })

  it('keeps the credential from a successful join when the hash changes in flight', async () => {
    const pending = deferred<Session>()
    api.joinMatch.mockReturnValue(pending.promise)
    location.hash = '#/join/FIRST'

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    )
    await waitFor(() => expect(api.joinMatch).toHaveBeenCalledTimes(1))

    location.hash = '#/join/SECOND'
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    expect(api.joinMatch).toHaveBeenCalledTimes(1)

    const joined: Session = {
      matchId: 'claimed-match',
      gameId: 'kahuna',
      seat: 1,
      token: 'seat-token',
      joinCode: 'FIRST',
    }
    pending.resolve(joined)

    expect(await screen.findByText('Match claimed-match')).toBeTruthy()
    expect(api.saveSession).toHaveBeenCalledWith(joined)
    expect(location.hash).toBe('')
    expect(api.joinMatch).toHaveBeenCalledTimes(1)
  })
})
