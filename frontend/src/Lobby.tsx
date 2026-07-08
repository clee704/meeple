import { useEffect, useRef, useState } from 'react'
import { createMatch, joinMatch, listGames } from './api'
import { playSound } from './sound'
import type { GameInfo, Session } from './types'

export function Lobby({
  onEnter,
  onError,
}: {
  onEnter: (s: Session, created?: boolean) => void
  onError: (msg: string) => void
}) {
  const [games, setGames] = useState<GameInfo[]>([])
  const [code, setCode] = useState('')
  const [pending, setPending] = useState<'create' | 'join' | null>(null)
  const pendingRef = useRef(false)

  useEffect(() => {
    listGames().then(setGames, (e) => onError(String(e)))
  }, [onError])

  const beginSubmit = (kind: 'create' | 'join') => {
    if (pendingRef.current) return false
    pendingRef.current = true
    setPending(kind)
    return true
  }

  const endSubmit = () => {
    pendingRef.current = false
    setPending(null)
  }

  const create = async (gameId: string, seat = 0) => {
    if (!beginSubmit('create')) return
    try {
      const session = await createMatch(gameId, seat)
      playSound('created')
      onEnter(session, true)
    } catch (e) {
      onError(String(e))
    } finally {
      endSubmit()
    }
  }

  const join = async () => {
    if (code.length < 5 || !beginSubmit('join')) return
    try {
      onEnter(await joinMatch(code))
    } catch (e) {
      onError(String(e))
    } finally {
      endSubmit()
    }
  }

  return (
    <div className="lobby">
      <h1>MeepleMind</h1>
      <h2>Start a match</h2>
      <div className="game-list">
        {games.map((g) => {
          const names = g.seat_names
          if (!names) {
            return (
              <button key={g.game_id} disabled={pending !== null} onClick={() => create(g.game_id)}>
                {g.game_id} <span className="dim">({g.num_players}p)</span>
              </button>
            )
          }
          // Named seats: one button per seat, seat 0 (the first mover) first.
          return (
            <div key={g.game_id} className="game-entry">
              <span>
                {g.game_id} <span className="dim">({g.num_players}p)</span>
              </span>
              {names.map((name, seat) => (
                <button key={seat} disabled={pending !== null} onClick={() => create(g.game_id, seat)}>
                  <span className="seat-swatch" style={{ background: `var(--p${seat})` }} />
                  {name}
                  {seat === 0 && <span className="dim"> · moves first</span>}
                </button>
              ))}
            </div>
          )
        })}
      </div>
      <h2>Join a match</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          join()
        }}
      >
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="Join code, e.g. KJ4QZ"
          maxLength={5}
        />
        <button type="submit" disabled={code.length < 5 || pending !== null}>
          {pending === 'join' ? 'Joining...' : 'Join'}
        </button>
      </form>
    </div>
  )
}
