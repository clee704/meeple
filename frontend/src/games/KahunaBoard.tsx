import { useMemo, useState } from 'react'
import type { HistoryEntry, LegalAction } from '../types'
import type { GameRendererProps } from './registry'

// Shape of meeple/games/kahuna/view.py's observation/meta payloads.
interface KahunaObservation {
  bridges: (number | null)[]
  control: Record<string, number | null>
  hand: string[]
  opponent_hand_count: number
  face_up: (string | null)[]
  pile_count: number
  discard: string[]
  my_hidden_discards: string[]
  opponent_hidden_discard_count: number
  scores: number[]
  scoring_count: number
  to_move: number | null
  final_turns_remaining: number | null
}

interface KahunaMeta {
  islands: string[]
  bridges: [string, string][]
  majority: Record<string, number>
}

// Island positions, hand-placed to match meeple/games/kahuna/board.svg;
// the topology itself always comes from the game's meta, never from here.
const POS: Record<string, [number, number]> = {
  ALOA: [240, 170],
  BARI: [385, 160],
  COCO: [550, 170],
  DUDA: [305, 225],
  ELAI: [380, 240],
  FAAA: [455, 215],
  GOLA: [510, 260],
  HUNA: [245, 305],
  IFFI: [360, 315],
  JOJO: [445, 290],
  KAHU: [550, 350],
  LALE: [380, 385],
}
const VIEWBOX = '174 94 442 357'
const SEAT_COLOR = ['var(--p0)', 'var(--p1)']

function countCards(cards: string[]): [string, number][] {
  const counts = new Map<string, number>()
  for (const c of cards) counts.set(c, (counts.get(c) ?? 0) + 1)
  return [...counts.entries()]
}

function variantLabel(la: LegalAction): string {
  const spend = la.meta.spend as string[]
  const verb = la.meta.kind === 'place' ? 'Build' : 'Remove'
  return `${verb}, paying ${spend.join(' + ')}`
}

function historyLine(h: HistoryEntry, seat: number): string {
  const who = h.actor === seat ? 'You' : 'Opponent'
  const m = h.meta
  switch (m.kind) {
    case 'place': {
      const [a, b] = m.islands as string[]
      return `${who} built ${a}–${b} (paid ${(m.spend as string[]).join('+')})`
    }
    case 'remove': {
      const [a, b] = m.islands as string[]
      return `${who} removed ${a}–${b} (paid ${(m.spend as string[]).join('+')})`
    }
    case 'draw_blind':
      return `${who} drew from the pile`
    case 'take_faceup':
      return `${who} took face-up card ${(m.slot as number) + 1}`
    case 'skip':
      return `${who} skipped`
    case 'discard':
      return m.island ? `${who} discarded ${m.island} face-down` : `${who} discarded face-down`
    default:
      return `${who} moved`
  }
}

export function KahunaBoard({
  observation,
  meta,
  seat,
  yourTurn,
  legalActions,
  history,
  submitAction,
}: GameRendererProps) {
  const obs = observation as unknown as KahunaObservation
  const { islands, bridges, majority } = meta as unknown as KahunaMeta
  const [chooser, setChooser] = useState<number | null>(null) // bridge pos

  const byBridge = useMemo(() => {
    const map = new Map<number, LegalAction[]>()
    for (const la of legalActions) {
      if (la.meta.kind === 'place' || la.meta.kind === 'remove') {
        const pos = la.meta.bridge as number
        map.set(pos, [...(map.get(pos) ?? []), la])
      }
    }
    return map
  }, [legalActions])

  const byKind = (kind: string) => legalActions.filter((la) => la.meta.kind === kind)

  const pick = (la: LegalAction) => {
    setChooser(null)
    submitAction(la.action)
  }

  const clickBridge = (pos: number) => {
    const variants = byBridge.get(pos)
    if (!variants) return
    if (variants.length === 1) pick(variants[0])
    else setChooser(chooser === pos ? null : pos)
  }

  return (
    <div className="kahuna">
      <div className="kahuna-status">
        <span>
          Scores: <b style={{ color: SEAT_COLOR[seat] }}>you {obs.scores[seat]}</b> ·{' '}
          <b style={{ color: SEAT_COLOR[1 - seat] }}>them {obs.scores[1 - seat]}</b>
        </span>
        <span>Scoring {obs.scoring_count}/3</span>
        <span>Pile {obs.pile_count}</span>
        <span>Opponent: {obs.opponent_hand_count} cards</span>
        {obs.opponent_hidden_discard_count > 0 && (
          <span>({obs.opponent_hidden_discard_count} face-down discards)</span>
        )}
        {obs.final_turns_remaining !== null && (
          <span className="dim">Final turns: {obs.final_turns_remaining}</span>
        )}
      </div>

      <svg viewBox={VIEWBOX} className="kahuna-svg">
        {bridges.map(([a, b], pos) => {
          const [x1, y1] = POS[a]
          const [x2, y2] = POS[b]
          const owner = obs.bridges[pos]
          const actionable = yourTurn && byBridge.has(pos)
          return (
            <line
              key={pos}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke={owner === null ? 'var(--line)' : SEAT_COLOR[owner]}
              strokeWidth={owner === null ? 2 : 5}
              strokeDasharray={owner === null ? '4 5' : undefined}
              className={actionable ? 'bridge actionable' : 'bridge'}
              onClick={() => clickBridge(pos)}
            />
          )
        })}
        {islands.map((island) => {
          const [x, y] = POS[island]
          const controller = obs.control[island]
          return (
            <g key={island}>
              <circle
                cx={x}
                cy={y}
                r={26}
                fill={controller === null ? 'var(--panel)' : SEAT_COLOR[controller]}
                stroke="var(--ink)"
                strokeWidth={1.5}
              />
              <text
                x={x}
                y={y + 4}
                textAnchor="middle"
                fontSize={13}
                fill={controller === null ? 'var(--ink)' : '#fff'}
              >
                {island}
              </text>
              <text x={x} y={y + 17} textAnchor="middle" fontSize={9} fill="var(--dim)">
                {majority[island]}
              </text>
            </g>
          )
        })}
      </svg>

      {chooser !== null && (
        <div className="kahuna-chooser">
          {(byBridge.get(chooser) ?? []).map((la) => (
            <button key={la.action} onClick={() => pick(la)}>
              {variantLabel(la)}
            </button>
          ))}
          <button onClick={() => setChooser(null)}>Cancel</button>
        </div>
      )}

      <div className="kahuna-panel">
        <div>
          <h3>Your hand</h3>
          <div className="action-row">
            {countCards(obs.hand).map(([card, n]) => (
              <span key={card} className="chip">
                {card}
                {n > 1 ? ` ×${n}` : ''}
              </span>
            ))}
            {obs.hand.length === 0 && <span className="dim">empty</span>}
          </div>
          {obs.my_hidden_discards.length > 0 && (
            <div className="dim">Your face-down discards: {obs.my_hidden_discards.join(', ')}</div>
          )}
        </div>

        <div>
          <h3>Draw</h3>
          <div className="action-row">
            {obs.face_up.map((card, slot) => {
              const la = byKind('take_faceup').find((x) => x.meta.slot === slot)
              return (
                <button
                  key={slot}
                  className="chip-btn"
                  disabled={!la}
                  onClick={() => la && pick(la)}
                >
                  {card ?? '—'}
                </button>
              )
            })}
            {byKind('draw_blind').map((la) => (
              <button key={la.action} onClick={() => pick(la)}>
                Draw blind ({obs.pile_count})
              </button>
            ))}
            {byKind('skip').map((la) => (
              <button key={la.action} onClick={() => pick(la)}>
                Skip turn
              </button>
            ))}
          </div>
        </div>

        {byKind('discard').length > 0 && (
          <div>
            <h3>Hand limit — discard face-down first</h3>
            <div className="action-row">
              {byKind('discard').map((la) => (
                <button key={la.action} onClick={() => pick(la)}>
                  {la.meta.island as string}
                </button>
              ))}
            </div>
          </div>
        )}

        <div>
          <h3>Log</h3>
          <ul className="kahuna-log">
            {history.slice(-8).map((h, i) => (
              <li key={history.length - 8 + i}>{historyLine(h, seat)}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
