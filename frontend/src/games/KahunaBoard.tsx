import { useEffect, useMemo, useState } from 'react'
import type { HistoryEntry, LegalAction } from '../types'
import type { GameRendererProps } from './registry'
import { matchSelection, payOptionsByBridge } from './kahunaSelect'

// Shape of meeple/games/kahuna/view.py's observation/meta payloads (the
// fields this renderer uses).
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
  final_turns_remaining: number | null
}

interface KahunaMeta {
  islands: string[]
  bridges: [string, string][]
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

// A pile of `count` cards (card 0 bottommost), top card anchored at the
// top-left so a shrinking pile pulls in toward it; depth fans lower cards
// right-down.
function cardStack(count: number, classFor: (i: number) => string) {
  if (count === 0) return <span className="card empty" />
  return Array.from({ length: count }, (_, i) => {
    const depth = count - 1 - i
    return (
      <span
        key={i}
        className={classFor(i)}
        style={{ translate: `${1.2 * depth}px ${0.8 * depth}px` }}
      />
    )
  })
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
  const { islands, bridges } = meta as unknown as KahunaMeta

  // Card-first selection, mirroring the physical game: pick the card(s) to
  // spend, then pick the line(s)/bridge(s) they pay for, then confirm.
  const [selCards, setSelCards] = useState<number[]>([]) // indices into obs.hand
  const [selBridges, setSelBridges] = useState<number[]>([]) // bridge positions
  const [busy, setBusy] = useState(false) // an action (or batch) is in flight

  useEffect(() => {
    setSelCards([])
    setSelBridges([])
  }, [observation])

  const optionsByPos = useMemo(() => payOptionsByBridge(legalActions), [legalActions])
  const byKind = (kind: string) => legalActions.filter((la) => la.meta.kind === kind)

  const selNames = selCards.map((i) => obs.hand[i])
  const selOptions = selBridges.map((pos) => optionsByPos.get(pos) ?? [])

  // A line/bridge is selectable iff adding it keeps every selected
  // line/bridge payable out of the selected cards — so with nothing
  // selected, nothing highlights.
  const canAdd = (pos: number): boolean => {
    const opts = optionsByPos.get(pos)
    if (!opts) return false
    return matchSelection([...selOptions, opts], selNames, false) !== null
  }

  const toggleCard = (i: number) => {
    if (!yourTurn) return
    if (selCards.includes(i)) {
      const next = selCards.filter((j) => j !== i)
      // Drop the board selection if the remaining cards can't pay for it.
      const names = next.map((j) => obs.hand[j])
      if (matchSelection(selOptions, names, false) === null) setSelBridges([])
      setSelCards(next)
    } else {
      setSelCards([...selCards, i])
    }
  }

  const toggleBridge = (pos: number) => {
    if (selBridges.includes(pos)) setSelBridges(selBridges.filter((p) => p !== pos))
    else if (canAdd(pos)) setSelBridges([...selBridges, pos])
  }

  // Removes go first: a place's majority cascade can strip an opponent
  // bridge that's also selected for removal, but a remove never invalidates
  // another selected play.
  const orderedSel = [...selBridges].sort(
    (a, b) => Number(obs.bridges[a] === null) - Number(obs.bridges[b] === null),
  )
  const plan =
    selBridges.length > 0
      ? matchSelection(
          orderedSel.map((pos) => optionsByPos.get(pos) ?? []),
          selNames,
          true,
        )
      : null

  const run = async (fn: () => Promise<unknown>) => {
    if (busy) return
    setBusy(true)
    try {
      await fn()
    } finally {
      setBusy(false)
    }
  }

  const commit = () =>
    run(async () => {
      for (const opt of plan ?? []) if (!(await submitAction(opt.action))) return
    })

  const discardActions = new Map(
    byKind('discard').map((la) => [la.meta.island as string, la.action]),
  )
  const canDiscard =
    selBridges.length === 0 && selNames.length > 0 && selNames.every((n) => discardActions.has(n))

  const discard = () => {
    const n = selNames.length
    const msg =
      `Discard ${n} card${n > 1 ? 's' : ''} (${selNames.join(', ')}) face-down? ` +
      `You can't play cards after discarding — you must end your turn by drawing.`
    if (!confirm(msg)) return
    const actions = selNames.map((name) => discardActions.get(name)!)
    return run(async () => {
      for (const a of actions) if (!(await submitAction(a))) return
    })
  }

  const endTurn = (la: LegalAction | undefined) => la && run(() => submitAction(la.action))

  const nPlace = selBridges.filter((p) => obs.bridges[p] === null).length
  const nRemove = selBridges.length - nPlace
  const parts = []
  if (nPlace) parts.push(`build ${nPlace}`)
  if (nRemove) parts.push(`remove ${nRemove}`)
  const commitLabel = parts.length ? `Confirm: ${parts.join(' + ')}` : 'Confirm'

  const drawBlind = byKind('draw_blind')[0]
  const skip = byKind('skip')[0]
  const round = Math.min(obs.scoring_count + 1, 3)
  const hiddenCount = obs.my_hidden_discards.length + obs.opponent_hidden_discard_count
  const discardCount = obs.discard.length + hiddenCount

  return (
    <div className="kahuna">
      <div className="kahuna-status">
        <span>
          Scores: <b style={{ color: SEAT_COLOR[seat] }}>you {obs.scores[seat]}</b> ·{' '}
          <b style={{ color: SEAT_COLOR[1 - seat] }}>them {obs.scores[1 - seat]}</b>
        </span>
        <span>Round {round}/3</span>
        {obs.final_turns_remaining !== null && (
          <span className="dim">Final turns: {obs.final_turns_remaining}</span>
        )}
      </div>

      <div>
        <h3>Opponent's hand</h3>
        <div className="kahuna-cards">
          {Array.from({ length: obs.opponent_hand_count }, (_, i) => (
            <span key={i} className="card facedown" />
          ))}
          {obs.opponent_hand_count === 0 && <span className="dim">empty</span>}
        </div>
      </div>

      <div className="kahuna-board-row">
        <svg viewBox={VIEWBOX} className="kahuna-svg">
          {bridges.map(([a, b], pos) => {
            const [x1, y1] = POS[a]
            const [x2, y2] = POS[b]
            const owner = obs.bridges[pos]
            const selected = selBridges.includes(pos)
            const active = selected || (yourTurn && canAdd(pos))
            const base =
              owner === null
                ? selected
                  ? // Ghost of the bridge you're about to build.
                    { stroke: SEAT_COLOR[seat], strokeWidth: 5, opacity: 0.55 }
                  : active
                    ? { stroke: 'var(--accent)', strokeWidth: 4, strokeDasharray: '4 5', opacity: 0.6 }
                    : { stroke: 'var(--line)', strokeWidth: 2, strokeDasharray: '4 5' }
                : { stroke: SEAT_COLOR[owner], strokeWidth: 5, opacity: selected ? 0.45 : 1 }
            return (
              <g
                key={pos}
                className={selected ? 'bridge active selected' : active ? 'bridge active' : 'bridge'}
                onClick={active ? () => toggleBridge(pos) : undefined}
              >
                <line x1={x1} y1={y1} x2={x2} y2={y2} {...base} />
                {owner !== null && active && (
                  // Marked (or markable) for demolition.
                  <line
                    x1={x1}
                    y1={y1}
                    x2={x2}
                    y2={y2}
                    stroke="var(--danger)"
                    strokeWidth={selected ? 5 : 10}
                    strokeDasharray={selected ? '6 4' : undefined}
                    opacity={selected ? 0.95 : 0.3}
                  />
                )}
                {active && <line x1={x1} y1={y1} x2={x2} y2={y2} className="bridge-hit" />}
              </g>
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
              </g>
            )
          })}
        </svg>

        <div className="kahuna-supply">
          <div>
            <h3>Face-up</h3>
            <div className="kahuna-cards">
              {obs.face_up.map((card, slot) => {
                const la = byKind('take_faceup').find((x) => x.meta.slot === slot)
                if (card === null) return <span key={slot} className="card empty" />
                return (
                  <button key={slot} className="card" disabled={!la} onClick={() => endTurn(la)}>
                    {card}
                  </button>
                )
              })}
            </div>
          </div>
          <div>
            <h3>Pile ({obs.pile_count})</h3>
            <div className="kahuna-pile-wrap">
              <button
                className="pile"
                disabled={!drawBlind}
                onClick={() => endTurn(drawBlind)}
                aria-label={`draw pile, ${obs.pile_count} cards`}
              >
                {cardStack(obs.pile_count, () => 'card facedown')}
              </button>
              {skip && (
                <button className="kahuna-skip" onClick={() => endTurn(skip)}>
                  Skip draw
                </button>
              )}
            </div>
          </div>
          <div>
            <h3>Discard ({discardCount})</h3>
            {/* One pile, like the table: face-down hand-limit discards
                slide under it, openly spent cards land face-up on top. */}
            <div className="pile">
              {cardStack(discardCount, (i) => (i < hiddenCount ? 'card facedown' : 'card'))}
            </div>
          </div>
        </div>
      </div>

      <div>
        <h3>Your hand</h3>
        <div className="kahuna-cards">
          {obs.hand.map((card, i) => (
            <button
              key={i}
              className={selCards.includes(i) ? 'card selected' : 'card'}
              aria-pressed={selCards.includes(i)}
              onClick={() => toggleCard(i)}
            >
              {card}
            </button>
          ))}
          {obs.hand.length === 0 && <span className="dim">empty</span>}
        </div>
        {yourTurn && selCards.length > 0 && (
          <div className="action-row kahuna-confirm">
            <button className="primary" disabled={!plan || busy} onClick={commit}>
              {commitLabel}
            </button>
            {canDiscard && <button onClick={discard}>Discard face-down…</button>}
            <button onClick={() => { setSelCards([]); setSelBridges([]) }}>Clear</button>
            {!plan && (
              <span className="dim">select lines/bridges that spend every selected card</span>
            )}
          </div>
        )}
      </div>

      <div>
        <h3>Log</h3>
        <ul className="kahuna-log">
          {history.slice(-8).map((h, i) => (
            <li key={history.length - 8 + i}>{historyLine(h, seat)}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}
