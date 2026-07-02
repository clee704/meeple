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
            <button key={la.action} onClick={() => submitAction(la.action)}>
              {la.name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
