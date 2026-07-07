import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useConfirm } from '../Confirm'
import { Overlay } from '../Overlay'
import { playSound } from '../sound'
import type { HistoryEntry, LegalAction } from '../types'
import type { GameRendererProps } from './registry'
import { matchSelection, payOptionsByBridge } from './kahunaSelect'
import './kahuna.css'

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
  round_points: number[][]
  final_turns_remaining: number | null
}

interface KahunaMeta {
  islands: string[]
  bridges: [string, string][]
}

// What the board drawing needs — held back while a reveal overlay is up.
interface BoardSnap {
  bridges: (number | null)[]
  control: Record<string, number | null>
}

// Island positions, hand-placed to match meeple/games/kahuna/board.svg;
// the topology itself always comes from the game's meta, never from here.
const POS: Record<string, [number, number]> = {
  ALOA: [240, 175],
  BARI: [385, 155],
  COCO: [550, 175],
  DUDA: [303, 225],
  ELAI: [380, 240],
  FAAA: [455, 215],
  GOLA: [512, 260],
  HUNA: [250, 310],
  IFFI: [365, 315],
  JOJO: [445, 290],
  KAHU: [550, 350],
  LALE: [385, 385],
}
// Tight crop: island centers span x 240–550, y 160–385, radius 26, plus a
// 12px margin — keeps the islands as large as the container allows.
const VIEWBOX = '202 117 386 306'
// One-shot per browser: set once the drawing-ends-your-turn reminder has
// been shown, so it never fires again.
const DRAW_NOTICE_KEY = 'meeple.kahuna.draw-notice'
const BRIDGE_SUPPLY = 25
const SEAT_COLOR = ['var(--p0)', 'var(--p1)']
const SEAT_LABEL = ['var(--p0-ink)', 'var(--p1-ink)']
// Island labels hold this on-screen size however far the board is scaled
// down — counter-scaled by the SVG's live screen matrix — so they stay
// readable on a narrow phone instead of shrinking with the board. Roughly
// matches the hand cards' text at phone width.
const ISLAND_LABEL_PX = 14

// A pile of `count` cards (card 0 bottommost), top card anchored at the
// top-left so a shrinking pile pulls in toward it; depth fans lower cards
// right-down.
function cardStack(count: number, classFor: (i: number) => string) {
  if (count === 0) return <span className="card empty" />
  count = Math.min(count, 5)
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

function withoutSpent(cards: string[], spent: string[]): string[] {
  const next = [...cards]
  for (const card of spent) {
    const at = next.indexOf(card)
    if (at >= 0) next.splice(at, 1)
  }
  return next
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
      // The card is public — everyone saw the slot before it was taken.
      return typeof m.card === 'string'
        ? `${who} took ${m.card} from the face-up row`
        : `${who} took face-up card ${(m.slot as number) + 1}`
    case 'skip':
      return `${who} skipped`
    case 'discard':
      return m.island ? `${who} discarded ${m.island} face-down` : `${who} discarded face-down`
    default:
      return `${who} moved`
  }
}

// The previous turn plus the current (in-progress) turn — the last two
// maximal runs of consecutive same-actor entries. The log shows only these,
// never the whole game history.
function recentTurns(history: HistoryEntry[]): HistoryEntry[] {
  let changes = 0
  for (let i = history.length - 1; i > 0; i--) {
    if (history[i].actor !== history[i - 1].actor && ++changes === 2) return history.slice(i)
  }
  return history.slice()
}

// Score-sheet row labels: rounds 1 and 2, then the final scoring.
const roundLabel = (i: number) => (i === 2 ? 'Final round' : 'Round ' + (i + 1))

export function KahunaBoard({
  observation,
  meta,
  seat,
  yourTurn,
  legalActions,
  history,
  result,
  submitAction,
  reportHud,
}: GameRendererProps) {
  const obs = observation as unknown as KahunaObservation
  const { islands, bridges } = meta as unknown as KahunaMeta

  // Card-first selection, mirroring the physical game: pick the card(s) to
  // spend, then pick the line(s)/bridge(s) they pay for, then confirm. A
  // draw selection is mutually exclusive with a card/bridge selection, so
  // it's one state instead of three independently-cleared ones — nothing
  // can set one half without clearing the other.
  type Selection =
    | { mode: 'idle' }
    | { mode: 'play'; cards: number[]; bridges: number[] } // indices into obs.hand; bridge positions
    | { mode: 'draw'; which: number | 'blind' } // a face-up slot, or 'blind' for the draw pile
  const [sel, setSel] = useState<Selection>({ mode: 'idle' })
  const selCards = sel.mode === 'play' ? sel.cards : []
  const selBridges = sel.mode === 'play' ? sel.bridges : []
  const drawSel = sel.mode === 'draw' ? sel.which : null
  const [busy, setBusy] = useState(false) // an action (or batch) is in flight
  const [logOpen, setLogOpen] = useState(false) // full-history overlay
  const [confirmDialog, ask] = useConfirm()

  useEffect(() => {
    setSel({ mode: 'idle' })
  }, [observation])

  const optionsByPos = useMemo(() => payOptionsByBridge(legalActions), [legalActions])
  const byKind = (kind: string) => legalActions.filter((la) => la.meta.kind === kind)

  const selNames = selCards.map((i) => obs.hand[i])
  const selOptions = selBridges.map((pos) => optionsByPos.get(pos) ?? [])
  const remainingBridgeSupply = BRIDGE_SUPPLY - obs.bridges.filter((owner) => owner === seat).length
  const selectedPlacementCount = selBridges.filter((pos) => obs.bridges[pos] === null).length

  // A line/bridge is selectable iff adding it keeps every selected
  // line/bridge payable out of the selected cards — so with nothing
  // selected, nothing highlights. Computed as one memoized set: the
  // backtracking search must not rerun per bridge on every animation-timer
  // re-render.
  const addable = useMemo(() => {
    const ok = new Set<number>()
    if (!yourTurn) return ok
    for (const [pos, opts] of optionsByPos) {
      if (obs.bridges[pos] === null && selectedPlacementCount >= remainingBridgeSupply) continue
      if (matchSelection([...selOptions, opts], selNames, false) !== null) ok.add(pos)
    }
    return ok
    // selOptions/selNames derive from sel, obs.hand and optionsByPos.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [yourTurn, optionsByPos, sel, obs.hand, remainingBridgeSupply, selectedPlacementCount])
  const canAdd = (pos: number) => addable.has(pos)

  const toggleCard = (i: number) => {
    if (selCards.includes(i)) {
      playSound('deselect')
      const next = selCards.filter((j) => j !== i)
      // Drop the board selection if the remaining cards can't pay for it.
      const names = next.map((j) => obs.hand[j])
      const bridges = matchSelection(selOptions, names, false) === null ? [] : selBridges
      setSel(next.length > 0 || bridges.length > 0 ? { mode: 'play', cards: next, bridges } : { mode: 'idle' })
    } else {
      playSound('select')
      setSel({ mode: 'play', cards: [...selCards, i], bridges: selBridges })
    }
  }

  const toggleBridge = (pos: number) => {
    if (selBridges.includes(pos))
      setSel({ mode: 'play', cards: selCards, bridges: selBridges.filter((p) => p !== pos) })
    else if (canAdd(pos)) setSel({ mode: 'play', cards: selCards, bridges: [...selBridges, pos] })
  }

  // Removes go first: a place's majority cascade can strip an opponent
  // bridge that's also selected for removal, but a remove never invalidates
  // another selected play.
  const orderedSel = [...selBridges].sort(
    (a, b) => Number(obs.bridges[a] === null) - Number(obs.bridges[b] === null),
  )
  const plan =
    selBridges.length > 0 && selectedPlacementCount <= remainingBridgeSupply
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
      let accepted = false
      let actions = legalActions
      let remainingBridges = [...orderedSel]
      let remainingCards = [...selNames]
      while (remainingBridges.length > 0) {
        const available = payOptionsByBridge(actions)
        const nextPlan = matchSelection(
          remainingBridges.map((pos) => available.get(pos) ?? []),
          remainingCards,
          true,
        )
        const opt = nextPlan?.[0]
        if (!opt) break
        const env = await submitAction(opt.action)
        if (!env) return
        accepted = true
        remainingCards = withoutSpent(remainingCards, opt.cost)
        remainingBridges = remainingBridges.slice(1)
        if (env.status === 'finished') break
        actions = env.legal_actions
      }
      if (accepted) playSound('play') // once for the whole batch (see the sounds effect)
    })

  const discardActions = new Map(
    byKind('discard').map((la) => [la.meta.island as string, la.action]),
  )
  const canDiscard =
    selBridges.length === 0 && selNames.length > 0 && selNames.every((n) => discardActions.has(n))

  const discard = async () => {
    const n = selNames.length
    const msg =
      `Discard ${n} card${n > 1 ? 's' : ''} (${selNames.join(', ')}) face-down? ` +
      `You can't play cards after discarding — you must end your turn by drawing.`
    if (!(await ask(msg, { confirmLabel: 'Discard' }))) return
    const actions = selNames.map((name) => discardActions.get(name)!)
    return run(async () => {
      for (const a of actions) if (!(await submitAction(a))) return
      playSound('discard') // once for the whole batch (see the sounds effect)
    })
  }

  const endTurn = (la: LegalAction | undefined) => la && run(() => submitAction(la.action))

  // Picking a draw source is picking how the turn ends — it supersedes any
  // half-built play, so clear that selection to keep the state readable.
  const toggleDrawSel = (which: number | 'blind') => {
    playSound(drawSel === which ? 'deselect' : 'select')
    setSel(drawSel === which ? { mode: 'idle' } : { mode: 'draw', which })
  }

  // First draw ever in this browser gets a one-time heads-up; after that
  // the Draw button acts immediately.
  const draw = async (la: LegalAction | undefined) => {
    if (!la) return
    if (!localStorage.getItem(DRAW_NOTICE_KEY)) {
      if (!(await ask('Heads-up: drawing a card ends your turn. Draw now?', { confirmLabel: 'Draw' })))
        return
      localStorage.setItem(DRAW_NOTICE_KEY, '1')
    }
    endTurn(la)
  }

  // Skipping the draw is rare enough that a mishit is likelier than the
  // real intent — confirm, except when skip is the only legal move left
  // (nothing to play, nothing to draw; happens in the final turns).
  const skipDraw = async (la: LegalAction | undefined) => {
    if (!la) return
    const forced = legalActions.length === 1
    if (
      !forced &&
      !(await ask('Skip your draw? Your turn ends without taking a card.', { confirmLabel: 'Skip' }))
    )
      return
    endTurn(la)
  }

  const drawBlind = byKind('draw_blind')[0]
  const skip = byKind('skip')[0]
  const drawAction =
    drawSel === 'blind'
      ? drawBlind
      : drawSel !== null
        ? byKind('take_faceup').find((x) => x.meta.slot === drawSel)
        : undefined

  // Structurally impossible actions gray out: no legal place/remove at all,
  // no legal draw source, no legal skip. (A merely incomplete selection
  // keeps its button live and explains what is missing on tap.)
  const canPlay = optionsByPos.size > 0
  const canDraw = Boolean(drawBlind) || byKind('take_faceup').length > 0
  const round = Math.min(obs.scoring_count + 1, 3)
  const discardCount =
    obs.discard.length + obs.my_hidden_discards.length + obs.opponent_hidden_discard_count

  // A real game end — a forfeit carries no points and the HUD verdict
  // already covers it — shows the persistent score sheet below the hand.
  const gameOver = result !== null && 'points' in result

  // The Play / Draw / Skip buttons on your turn; see the gray-out rules
  // above for when each is disabled outright.
  const play = () => {
    if (selCards.length === 0)
      return void ask('Pick a card from your hand first, then the lines or bridges it pays for.', { alert: true })
    if (!plan) return void ask('Pick the lines or bridges these cards pay for.', { alert: true })
    commit()
  }
  const drawOrPrompt = () => {
    if (!drawAction) return void ask('Pick a face-up card or the draw pile first.', { alert: true })
    draw(drawAction)
  }

  // Opponent plays go through one serialized queue, one entry per update
  // (poll). A play is the whole set of cards committed together, so every
  // place/remove card seen in a single update is ONE entry — not one per
  // card or per bridge. Each entry carries those cards and the board as it
  // looked BEFORE them. Only the head entry's overlay shows, for a full 3s
  // from the moment it reaches the head, so successive plays are announced
  // strictly one at a time in order (a later play can't bleed into an
  // earlier one's overlay). The board holds the head's pre-play state and
  // animates that whole play's board changes as one step when it clears.
  interface Reveal {
    cards: string[]
    before: BoardSnap
    shownAt: number // when this entry reached the head of the queue
  }
  const [queue, setQueue] = useState<Reveal[]>([])
  // Enqueued during render (the "adjust state when props change" pattern),
  // so no frame ever paints the post-play board before the hold applies.
  const [tracked, setTracked] = useState({
    len: history.length,
    board: { bridges: obs.bridges, control: obs.control } as BoardSnap,
  })
  if (tracked.len !== history.length) {
    const added = history.slice(tracked.len)
    // A poll/action response can batch an opponent's move together with your
    // own subsequent one (e.g. you act right after their move lands). Only
    // the entries up to your own are opponent moves worth revealing —
    // entries from your own action don't invalidate an opponent reveal that
    // arrived earlier in the very same batch, only a queue left over from
    // before it (which would freeze the board on a now-stale snapshot).
    const ownIdx = added.findIndex((h) => h.actor === seat)
    const opponentPart = ownIdx === -1 ? added : added.slice(0, ownIdx)
    if (ownIdx !== -1 && queue.length > 0) setQueue([])
    const cards = opponentPart
      .filter((h) => h.meta.kind === 'place' || h.meta.kind === 'remove')
      .flatMap((h) => h.meta.spend as string[])
    if (cards.length > 0) {
      setQueue((q) => [...q, { cards, before: tracked.board, shownAt: Date.now() }])
    }
    setTracked({ len: history.length, board: { bridges: obs.bridges, control: obs.control } })
  }
  useEffect(() => {
    if (queue.length === 0) return
    const t = setTimeout(
      () =>
        setQueue((q) => {
          const rest = q.slice(1)
          // The next play's clock starts only now that it's visible.
          return rest.length ? [{ ...rest[0], shownAt: Date.now() }, ...rest.slice(1)] : rest
        }),
      Math.max(0, queue[0].shownAt + 3000 - Date.now()),
    )
    return () => clearTimeout(t)
  }, [queue])
  const revealed = queue[0]?.cards ?? []
  const revealActive = queue.length > 0
  useEffect(() => {
    if (revealActive) setSel({ mode: 'idle' })
  }, [revealActive])
  // Interaction is locked during a reveal; only the drawing is held back.
  const shownBoard = queue[0]?.before ?? { bridges: obs.bridges, control: obs.control }

  // New history entries also drive sounds (both players' plays/discards)
  // and the opponent-draw cue: a ghost of the taken card rising off its
  // face-up slot (or a face-down ghost off the pile), plus the new card
  // sliding into the opponent's hand — a draw is otherwise easy to miss.
  const [oppDraw, setOppDraw] = useState<
    { kind: 'blind'; at: number } | { kind: 'faceup'; slot: number; card: string; at: number } | null
  >(null)
  const heardLen = useRef(history.length)
  useEffect(() => {
    const added = history.slice(heardLen.current)
    heardLen.current = history.length
    if (added.length === 0) return
    // Opponent moves only: your own place/remove/discard arrives one action
    // per poll, so the cue is fired once per batch from commit()/discard()
    // instead (otherwise a multi-action turn would sound once per action).
    if (added.some((h) => h.actor !== seat && (h.meta.kind === 'place' || h.meta.kind === 'remove')))
      playSound('play')
    if (added.some((h) => h.actor !== seat && h.meta.kind === 'discard')) playSound('discard')
    // A draw sounds for both players (a draw is a single action per turn,
    // so there is no per-batch dedup to worry about); the floating-card
    // visual cue below stays opponent-only.
    if (added.some((h) => h.meta.kind === 'draw_blind' || h.meta.kind === 'take_faceup'))
      playSound('draw')
    const draw = added.find(
      (h) => h.actor !== seat && (h.meta.kind === 'draw_blind' || h.meta.kind === 'take_faceup'),
    )
    if (!draw) return
    const at = Date.now()
    const cue =
      draw.meta.kind === 'draw_blind'
        ? { kind: 'blind' as const, at }
        : typeof draw.meta.card === 'string'
          ? { kind: 'faceup' as const, slot: draw.meta.slot as number, card: draw.meta.card, at }
          : null
    if (!cue) return
    setOppDraw(cue)
    setTimeout(() => setOppDraw((cur) => (cur?.at === at ? null : cur)), 2000)
  }, [history, seat])

  // Animate what just changed on the drawn board, so a play (or your own
  // move's cascade) is trackable: new bridges grow in, removed ones fade
  // out as ghosts. Island recolors are a plain CSS transition. Merged, not
  // replaced: a batch landing must not cut short the previous animation.
  const [bridgeAnim, setBridgeAnim] = useState<{
    added: number[]
    removed: { pos: number; owner: number }[]
  }>({ added: [], removed: [] })
  const shownSig = shownBoard.bridges.map((b) => (b === null ? '.' : b)).join('')
  const prevShown = useRef(shownBoard)
  useLayoutEffect(() => {
    const prev = prevShown.current
    prevShown.current = shownBoard
    const added: number[] = []
    const removed: { pos: number; owner: number }[] = []
    shownBoard.bridges.forEach((b, pos) => {
      const before = prev.bridges[pos]
      if (before === null && b !== null) added.push(pos)
      else if (before !== null && b === null) removed.push({ pos, owner: before })
    })
    if (added.length === 0 && removed.length === 0) return
    setBridgeAnim((prev) => ({
      added: [...prev.added, ...added],
      removed: [...prev.removed.filter((r) => !added.includes(r.pos)), ...removed],
    }))
    const t = setTimeout(() => setBridgeAnim({ added: [], removed: [] }), 700)
    return () => clearTimeout(t)
    // The signature captures exactly the changes this effect reacts to.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shownSig])

  // A scoring pause: when a round scores, float the round's points and the
  // running total over the board for a while. Rounds 1/2 score the moment
  // the deck runs out (scoring_count flips), but round 3's flip merely
  // starts the two final turns — its scoring only lands when the game
  // ends, so the final overlay keys off `result` instead.
  const [roundScore, setRoundScore] = useState<{
    round: number
    delta: number[]
    total: number[]
  } | null>(null)
  const prevScore = useRef({ count: obs.scoring_count, scores: obs.scores })
  const finalShown = useRef(result !== null) // reloading a finished game stays quiet
  useEffect(() => {
    const prev = prevScore.current
    prevScore.current = { count: obs.scoring_count, scores: obs.scores }
    let scored: { round: number; delta: number[]; total: number[] } | null = null
    if (result !== null && 'points' in result) {
      // A real game end (a forfeit carries no points). Announce it once; a
      // premature end (zero bridges) has no scoring to show — the HUD
      // verdict covers it.
      if (finalShown.current) return
      finalShown.current = true
      playSound('game-over')
      if (result.premature) return
      scored = { round: 3, delta: obs.scores.map((s, i) => s - prev.scores[i]), total: obs.scores }
    } else if (obs.scoring_count !== prev.count && obs.scoring_count < 3) {
      playSound('round')
      scored = {
        round: obs.scoring_count,
        delta: obs.scores.map((s, i) => s - prev.scores[i]),
        total: obs.scores,
      }
    }
    if (!scored) return
    setRoundScore(scored)
    setTimeout(() => setRoundScore(null), 6000)
  }, [obs.scoring_count, obs.scores, result])

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

  // Island-label size in SVG user units, recomputed from the live screen
  // matrix so the rendered pixel size stays ISLAND_LABEL_PX at any board
  // width. ResizeObserver fires once on mount and on every resize.
  const svgRef = useRef<SVGSVGElement>(null)
  const [labelSize, setLabelSize] = useState(11)
  useLayoutEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const measure = () => {
      const ctm = svg.getScreenCTM()
      if (ctm && ctm.a > 0) setLabelSize(ISLAND_LABEL_PX / ctm.a)
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(svg)
    return () => ro.disconnect()
  }, [])

  // Contribute score / round to the shell's HUD (item 1); on phones the shell
  // tucks these into the kebab menu rather than wrapping the bar.
  const black = obs.scores[0]
  const white = obs.scores[1]
  const finalTurns = obs.final_turns_remaining
  useEffect(() => {
    reportHud?.(
      <>
        {/* Plain text, Black (seat 0) always first, no emphasis. En-dash
            (not ":") so it doesn't read like the clock. Which side is you is
            read from the turn pill's color. */}
        <span className="score-line">
          Score {black}–{white}
        </span>
        <span>Round {round}</span>
        {finalTurns !== null && <span className="dim">Final turns: {finalTurns}</span>}
      </>,
    )
    return () => reportHud?.(null)
  }, [reportHud, round, black, white, finalTurns])

  return (
    <div className="kahuna">
      <div className="kahuna-opp-row">
        <h3>Opponent's hand</h3>
        <div className="kahuna-cards kahuna-opp">
          {Array.from({ length: obs.opponent_hand_count }, (_, i) =>
            oppDraw && i === obs.opponent_hand_count - 1 ? (
              // The card the opponent just drew slides into their hand.
              <span key={`drawn-${oppDraw.at}`} className="card facedown drawn-in" />
            ) : (
              <span key={i} className="card facedown" />
            ),
          )}
          {obs.opponent_hand_count === 0 && <span className="card empty"></span>}
        </div>
      </div>

      <div className="kahuna-board-row">
        <div className="kahuna-board-wrap">
          <svg ref={svgRef} viewBox={VIEWBOX} className="kahuna-svg">
            {bridges.map(([a, b], pos) => {
              const [x1, y1] = POS[a]
              const [x2, y2] = POS[b]
              const owner = shownBoard.bridges[pos]
              const selected = selBridges.includes(pos)
              const active = !revealActive && (selected || canAdd(pos))
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
                  className={
                    selected
                      ? `bridge${active ? ' active' : ''} selected`
                      : active
                        ? 'bridge active'
                        : 'bridge'
                  }
                  onClick={active ? () => toggleBridge(pos) : undefined}
                >
                  <line
                    x1={x1}
                    y1={y1}
                    x2={x2}
                    y2={y2}
                    className={bridgeAnim.added.includes(pos) ? 'bridge-in' : undefined}
                    {...base}
                  />
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
            {bridgeAnim.removed.map(({ pos, owner }) => {
              const [a, b] = bridges[pos]
              const [x1, y1] = POS[a]
              const [x2, y2] = POS[b]
              return (
                // A just-removed bridge fades out over the dashed route.
                <line
                  key={`out-${pos}`}
                  className="bridge-out"
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={SEAT_COLOR[owner]}
                  strokeWidth={5}
                />
              )
            })}
            {islands.map((island) => {
              const [x, y] = POS[island]
              const controller = shownBoard.control[island]
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
                    y={y}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={labelSize}
                    fill={controller === null ? 'var(--island-ink)' : SEAT_LABEL[controller]}
                  >
                    {island}
                  </text>
                </g>
              )
            })}
          </svg>
          {(revealed.length > 0 || roundScore) && (
            <div className="kahuna-overlay">
              {roundScore && (
                <div className="kahuna-overlay-panel">
                  <span className="kahuna-overlay-label">
                    {roundScore.round === 3 ? 'Final scoring' : `Round ${roundScore.round} scored`}
                  </span>
                  <div className="kahuna-round-lines">
                    <span>
                      You +{roundScore.delta[seat]} · Opponent +{roundScore.delta[1 - seat]}
                    </span>
                    <span className="total">
                      Total {roundScore.total[seat]} : {roundScore.total[1 - seat]}
                    </span>
                  </div>
                </div>
              )}
              {revealed.length > 0 && (
                <div className="kahuna-overlay-panel">
                  <span className="kahuna-overlay-label">Opponent played</span>
                  <div className="kahuna-reveal-cards">
                    {revealed.map((card, i) => (
                      <span key={i} className="card revealed">
                        {card}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="kahuna-supply">
          <div>
            <h3>Face-up</h3>
            <div className="kahuna-cards">
              {obs.face_up.map((card, slot) => {
                const la = byKind('take_faceup').find((x) => x.meta.slot === slot)
                const ghost = oppDraw?.kind === 'faceup' && oppDraw.slot === slot ? oppDraw : null
                // Hold the refill back while the taken card is still floating
                // off this slot, so the new card only appears once that
                // animation is done (rather than sitting under the ghost).
                const shown = ghost ? null : card
                return (
                  <span key={slot} className="slot">
                    {shown === null ? (
                      <span className="card empty" />
                    ) : (
                      <button
                        className={drawSel === slot ? 'card selected' : 'card'}
                        aria-pressed={drawSel === slot}
                        disabled={revealActive || !la}
                        onClick={() => toggleDrawSel(slot)}
                      >
                        {shown}
                      </button>
                    )}
                    {ghost && (
                      // The card the opponent just took floats up off its
                      // (now empty) slot and fades.
                      <span key={ghost.at} className="card ghost-taken">
                        {ghost.card}
                      </span>
                    )}
                  </span>
                )
              })}
            </div>
          </div>
          <div>
            <h3>Draw ({obs.pile_count})</h3>
            <button
              className={drawSel === 'blind' ? 'pile selected' : 'pile'}
              aria-pressed={drawSel === 'blind'}
              disabled={revealActive || !drawBlind}
              onClick={() => toggleDrawSel('blind')}
              aria-label={`draw pile, ${obs.pile_count} cards`}
            >
              {oppDraw?.kind === 'blind' && (
                // The opponent's blind draw floats off the pile, face down.
                <span key={oppDraw.at} className="card facedown ghost-taken" />
              )}
              {cardStack(obs.pile_count, () => 'card facedown')}
            </button>
          </div>
          <div>
            <h3>Discard ({discardCount})</h3>
            <div className="kahuna-discard">
              {discardCount === 0 && <span className="dim">empty</span>}
              {obs.discard.length > 0 && (
                <div className="kahuna-discard-group">
                  <span className="kahuna-discard-label">Public</span>
                  <div className="kahuna-discard-chips">
                    {obs.discard.map((card, i) => (
                      <span key={`public-${i}`} className="kahuna-discard-chip">
                        {card}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {obs.my_hidden_discards.length > 0 && (
                <div className="kahuna-discard-group">
                  <span className="kahuna-discard-label">Your hidden</span>
                  <div className="kahuna-discard-chips">
                    {obs.my_hidden_discards.map((card, i) => (
                      <span key={`mine-${i}`} className="kahuna-discard-chip own-hidden">
                        {card}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {obs.opponent_hidden_discard_count > 0 && (
                <div className="kahuna-discard-group">
                  <span className="kahuna-discard-label">Opponent hidden</span>
                  <div className="kahuna-discard-chips">
                    <span className="kahuna-discard-chip facedown">
                      ? x{obs.opponent_hidden_discard_count}
                    </span>
                  </div>
                </div>
              )}
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
              className={[
                'card',
                selCards.includes(i) && 'selected',
                justDrawn.includes(i) && 'drawn',
              ]
                .filter(Boolean)
                .join(' ')}
              aria-pressed={selCards.includes(i)}
              disabled={!yourTurn || revealActive}
              onClick={() => toggleCard(i)}
            >
              {card}
            </button>
          ))}
          {obs.hand.length === 0 && <span className="card empty"></span>}
        </div>
        {yourTurn && (
          <div className="action-row kahuna-actions">
            <button disabled={busy || revealActive || !canPlay} onClick={play}>
              Play
            </button>
            <button disabled={busy || revealActive || !canDraw} onClick={drawOrPrompt}>
              Draw
            </button>
            <button disabled={busy || revealActive || !skip} onClick={() => skipDraw(skip)}>
              Skip
            </button>
            {canDiscard && (
              <button disabled={busy || revealActive} onClick={discard}>
                Discard
              </button>
            )}
          </div>
        )}
      </div>

      {/* Persistent end-of-game score sheet: the transient round overlays
          vanish after a few seconds, so once the game is over the totals
          and the per-round breakdown stay reviewable here. */}
      {gameOver && (
        <div>
          <h3>Final score</h3>
          <table className="kahuna-score-table">
            <thead>
              <tr>
                <th />
                <th>You</th>
                <th>Opponent</th>
              </tr>
            </thead>
            <tbody>
              {obs.round_points.map((pts, i) => (
                <tr key={i}>
                  <th>{roundLabel(i)}</th>
                  <td>+{pts[seat]}</td>
                  <td>+{pts[1 - seat]}</td>
                </tr>
              ))}
              <tr className="kahuna-score-total">
                <th>Total</th>
                <td>{obs.scores[seat]}</td>
                <td>{obs.scores[1 - seat]}</td>
              </tr>
            </tbody>
          </table>
          {result?.premature === true && (
            <p className="dim">Won early by knockout: the loser had no bridges on the board.</p>
          )}
        </div>
      )}

      <div className="kahuna-log-bar">
        <h3>Log</h3>
        <button
          className="kahuna-log-line"
          disabled={history.length === 0}
          onClick={() => setLogOpen(true)}
        >
          {history.length > 0 ? historyLine(history[history.length - 1], seat) : 'No moves yet'}
        </button>
      </div>

      {logOpen && (
        <Overlay
          onClose={() => setLogOpen(false)}
          contentClassName="modal kahuna-log-modal"
          contentProps={{ role: 'dialog', 'aria-modal': true, 'aria-label': 'Move log' }}
        >
          <h3>Log</h3>
          <ul className="kahuna-log-list">
            {[...recentTurns(history)].reverse().map((h, i) => (
              <li key={history.length - 1 - i}>{historyLine(h, seat)}</li>
            ))}
          </ul>
          <div className="action-row modal-actions">
            <button className="primary" onClick={() => setLogOpen(false)}>
              Close
            </button>
          </div>
        </Overlay>
      )}
      {confirmDialog}
    </div>
  )
}
