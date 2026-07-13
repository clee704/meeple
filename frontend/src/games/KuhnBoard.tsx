import { useState } from 'react'
import type { GameRendererProps } from './registry'

// Shape of meeple/games/kuhn/view.py's observation and result payloads.
interface KuhnObservation {
  card: string
  history: string[]
  to_move: number | null
}

export function KuhnBoard({ observation, yourTurn, legalActions, result, submitAction }: GameRendererProps) {
  const obs = observation as KuhnObservation
  const cards = result?.cards as string[] | null | undefined
  const [busy, setBusy] = useState(false)

  const act = async (action: number) => {
    if (busy) return
    setBusy(true)
    try {
      await submitAction(action)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="kuhn-board">
      <div className="kuhn-card" aria-label="your card">
        {obs.card}
      </div>
      <div className="kuhn-history">
        {obs.history.length === 0 ? 'No bets yet.' : obs.history.join(' → ')}
        {cards && <div>Showdown: {cards.join(' vs ')}</div>}
        {result && cards === null && <div>Folded — cards stay hidden.</div>}
      </div>
      {yourTurn && (
        <div className="action-row">
          {legalActions.map((la) => (
            <button key={la.action} disabled={busy} onClick={() => act(la.action)}>
              {la.name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
