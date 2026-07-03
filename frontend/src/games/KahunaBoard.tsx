import { useEffect, useMemo, useRef, useState } from 'react'
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
// Tight crop: island centers span x 240–550, y 160–385, radius 26, plus a
// 12px margin — keeps the islands as large as the container allows.
const VIEWBOX = '202 122 386 301'
// One-shot per browser: set once the drawing-ends-your-turn reminder has
// been shown, so it never fires again.
const DRAW_NOTICE_KEY = 'meeple.kahuna.draw-notice'
const SEAT_COLOR = ['var(--p0)', 'var(--p1)']
const SEAT_LABEL = ['var(--p0-ink)', 'var(--p1-ink)']

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
      return `${who} drew from the draw pile`
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
  // Draw source picked to end the turn: a face-up slot, or 'blind' for the
  // draw pile. Confirmed with an explicit button so a stray tap can't end
  // the turn by accident.
  const [drawSel, setDrawSel] = useState<number | 'blind' | null>(null)
  const [busy, setBusy] = useState(false) // an action (or batch) is in flight

  useEffect(() => {
    setSelCards([])
    setSelBridges([])
    setDrawSel(null)
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
    setDrawSel(null)
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

  // Picking a draw source is picking how the turn ends — it supersedes any
  // half-built play, so clear that selection to keep the state readable.
  const toggleDrawSel = (which: number | 'blind') => {
    setSelCards([])
    setSelBridges([])
    setDrawSel(drawSel === which ? null : which)
  }

  // First draw ever in this browser gets a one-time heads-up; after that
  // the Draw button acts immediately.
  const draw = (la: LegalAction | undefined) => {
    if (!la) return
    if (!localStorage.getItem(DRAW_NOTICE_KEY)) {
      localStorage.setItem(DRAW_NOTICE_KEY, '1')
      if (!confirm('Heads-up: drawing a card ends your turn. Draw now?')) return
    }
    endTurn(la)
  }

  // Skipping the draw is rare enough that a mishit is likelier than the
  // real intent — always confirm.
  const skipDraw = (la: LegalAction | undefined) => {
    if (!la) return
    if (!confirm('Skip your draw? Your turn ends without taking a card.')) return
    endTurn(la)
  }

  const nPlace = selBridges.filter((p) => obs.bridges[p] === null).length
  const nRemove = selBridges.length - nPlace
  const parts = []
  if (nPlace) parts.push(`build ${nPlace}`)
  if (nRemove) parts.push(`remove ${nRemove}`)
  const commitLabel = parts.length ? `Confirm: ${parts.join(' + ')}` : 'Confirm'

  const drawBlind = byKind('draw_blind')[0]
  const skip = byKind('skip')[0]
  const drawAction =
    drawSel === 'blind'
      ? drawBlind
      : drawSel !== null
        ? byKind('take_faceup').find((x) => x.meta.slot === drawSel)
        : undefined
  const round = Math.min(obs.scoring_count + 1, 3)
  const discardCount =
    obs.discard.length + obs.my_hidden_discards.length + obs.opponent_hidden_discard_count

  // Briefly show the opponent's openly played cards face-up beside the
  // discard pile before they merge into it, so you can see what they spent.
  const [revealed, setRevealed] = useState<string[]>([])
  const seenHistory = useRef(history.length)
  useEffect(() => {
    const fresh = history.slice(seenHistory.current)
    seenHistory.current = history.length
    const cards = fresh
      .filter((h) => h.actor !== seat && (h.meta.kind === 'place' || h.meta.kind === 'remove'))
      .flatMap((h) => h.meta.spend as string[])
    if (cards.length === 0) return
    setRevealed((prev) => [...prev, ...cards])
    // Batches expire FIFO, so dropping from the front removes exactly this one.
    setTimeout(() => setRevealed((prev) => prev.slice(cards.length)), 3000)
  }, [history, seat])
  // Clamped: a reshuffle can empty the discard pile mid-reveal.
  const revealCount = Math.min(revealed.length, discardCount)

  // Flag cards that just entered your hand — a blind draw is easy to miss.
  // Your hand is sorted, so the newcomer is found by multiset diff.
  const [justDrawn, setJustDrawn] = useState<number[]>([])
  const prevHand = useRef(obs.hand)
  useEffect(() => {
    const prev = prevHand.current
    if (prev.join('|') === obs.hand.join('|')) return
    prevHand.current = obs.hand
    const rest = [...prev]
    const added: number[] = []
    obs.hand.forEach((card, i) => {
      const at = rest.indexOf(card)
      if (at >= 0) rest.splice(at, 1)
      else added.push(i)
    })
    setJustDrawn(added)
    if (added.length === 0) return
    const t = setTimeout(() => setJustDrawn([]), 2500)
    return () => clearTimeout(t)
  }, [obs.hand])

  return (
    <div className="kahuna">
      <div className="kahuna-status">
        <span>
          Scores:{' '}
          <b
            className="seat-pill"
            style={{ background: SEAT_COLOR[seat], color: SEAT_LABEL[seat] }}
          >
            you {obs.scores[seat]}
          </b>{' '}
          <b
            className="seat-pill"
            style={{ background: SEAT_COLOR[1 - seat], color: SEAT_LABEL[1 - seat] }}
          >
            them {obs.scores[1 - seat]}
          </b>
        </span>
        <span>Round {round}/3</span>
        {obs.final_turns_remaining !== null && (
          <span className="dim">Final turns: {obs.final_turns_remaining}</span>
        )}
      </div>

      <div>
        <h3>Opponent's hand</h3>
        <div className="kahuna-cards kahuna-opp">
          {Array.from({ length: obs.opponent_hand_count }, (_, i) => (
            <span key={i} className="card facedown" />
          ))}
          {obs.opponent_hand_count === 0 && <span className="card empty"></span>}
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
                    { stroke: SEAT_COLOR[seat], strokeWidth: 5, opacity: 0.75 }
                  : active
                    ? { stroke: 'var(--accent)', strokeWidth: 4, strokeDasharray: '4 5', opacity: 0.9 }
                    : { stroke: 'var(--route)', strokeWidth: 2, strokeDasharray: '4 5' }
                : { stroke: SEAT_COLOR[owner], strokeWidth: 5, opacity: selected ? 0.65 : 1 }
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
                  fill={controller === null ? 'var(--island)' : SEAT_COLOR[controller]}
                  stroke="var(--island-edge)"
                  strokeWidth={0}
                />
                <text
                  x={x}
                  y={y + 4}
                  textAnchor="middle"
                  fontSize={11}
                  fill={controller === null ? 'var(--island-ink)' : SEAT_LABEL[controller]}
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
                  <button
                    key={slot}
                    className={drawSel === slot ? 'card selected' : 'card'}
                    aria-pressed={drawSel === slot}
                    disabled={!la}
                    onClick={() => toggleDrawSel(slot)}
                  >
                    {card}
                  </button>
                )
              })}
            </div>
          </div>
          <div>
            <h3>Draw pile ({obs.pile_count})</h3>
            <button
              className={drawSel === 'blind' ? 'pile selected' : 'pile'}
              aria-pressed={drawSel === 'blind'}
              disabled={!drawBlind}
              onClick={() => toggleDrawSel('blind')}
              aria-label={`draw pile, ${obs.pile_count} cards`}
            >
              {cardStack(obs.pile_count, () => 'card facedown')}
            </button>
          </div>
          {/* Always rendered so nothing shifts; Draw arms only once a
              face-up card or the pile is selected. */}
          <div className="action-row kahuna-draw-actions">
            <button className="primary" disabled={!drawAction || busy} onClick={() => draw(drawAction)}>
              Draw
            </button>
            <button disabled={!skip || busy} onClick={() => skipDraw(skip)}>
              Skip draw
            </button>
          </div>
          <div>
            <h3>Discard pile ({discardCount})</h3>
            {/* While a reveal holds out the whole pile, the revealed cards
                stand in for it — no empty slot above them. */}
            {(revealCount === 0 || discardCount > revealCount) && (
              <div className="pile">
                {cardStack(discardCount - revealCount, () => 'card facedown')}
              </div>
            )}
            {revealCount > 0 && (
              <div className="kahuna-cards kahuna-reveal">
                {revealed.slice(revealed.length - revealCount).map((card, i) => (
                  <span key={i} className="card revealed">
                    {card}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div>
        <h3>Your hand</h3>
        <div className="kahuna-cards">
          {obs.hand.map((card, i) => (
            <button
              key={i}
              className={[
                'card',
                selCards.includes(i) && 'selected',
                justDrawn.includes(i) && 'drawn',
              ]
                .filter(Boolean)
                .join(' ')}
              aria-pressed={selCards.includes(i)}
              disabled={!yourTurn}
              onClick={() => toggleCard(i)}
            >
              {card}
            </button>
          ))}
          {obs.hand.length === 0 && <span className="card empty"></span>}
        </div>
        {yourTurn && selCards.length > 0 && (
          <div className="action-row kahuna-confirm">
            <button className="primary" disabled={!plan || busy} onClick={commit}>
              {commitLabel}
            </button>
            {canDiscard && <button onClick={discard}>Discard</button>}
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
          {history
            .slice(-8)
            .reverse()
            .map((h, i) => (
              <li key={history.length - i}>{historyLine(h, seat)}</li>
            ))}
        </ul>
      </div>
    </div>
  )
}
