import { useEffect, useState } from 'react'
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

  useEffect(() => {
    listGames().then(setGames, (e) => onError(String(e)))
  }, [onError])

  const create = async (gameId: string, seat = 0) => {
    try {
      const session = await createMatch(gameId, seat)
      playSound('created')
      onEnter(session, true)
    } catch (e) {
      onError(String(e))
    }
  }

  const join = async () => {
    try {
      onEnter(await joinMatch(code))
    } catch (e) {
      onError(String(e))
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
              <button key={g.game_id} onClick={() => create(g.game_id)}>
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
                <button key={seat} onClick={() => create(g.game_id, seat)}>
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
        <button type="submit" disabled={code.length < 5}>
          Join
        </button>
      </form>
    </div>
  )
}
