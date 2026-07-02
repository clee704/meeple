import { useEffect, useState } from 'react'
import { createMatch, joinMatch, listGames } from './api'
import type { GameInfo, Session } from './types'

export function Lobby({ onEnter, onError }: { onEnter: (s: Session) => void; onError: (msg: string) => void }) {
  const [games, setGames] = useState<GameInfo[]>([])
  const [code, setCode] = useState('')

  useEffect(() => {
    listGames().then(setGames, (e) => onError(String(e)))
  }, [onError])

  const create = async (gameId: string) => {
    try {
      onEnter(await createMatch(gameId))
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
        {games.map((g) => (
          <button key={g.game_id} onClick={() => create(g.game_id)}>
            {g.game_id} <span className="dim">({g.num_players}p)</span>
          </button>
        ))}
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
