import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { ApiError, getState, leaveMatch, postAction } from './api'
import { useConfirm } from './Confirm'
import { mergeEnvelope } from './envelope'
import { renderers } from './games/registry'
import { playSound } from './sound'
import { useEscapeToClose } from './useEscapeToClose'
import type { Envelope, MatchStatus, Session } from './types'

const POLL_MS = 1000

function formatClock(seconds: number): string {
  const t = Math.max(0, Math.floor(seconds))
  const h = Math.floor(t / 3600)
  const mm = String(Math.floor((t % 3600) / 60)).padStart(2, '0')
  const ss = String(t % 60).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // Fall through to the old selection-based path for non-secure LAN origins.
    }
  }
  const textArea = document.createElement('textarea')
  textArea.value = text
  textArea.style.position = 'fixed'
  textArea.style.left = '-9999px'
  document.body.append(textArea)
  textArea.focus()
  textArea.select()
  const copied = document.execCommand('copy')
  textArea.remove()
  return copied
}

// Kebab (⋮) dropdown anchored to the HUD's top-right corner, for actions
// that shouldn't sit as bare buttons in the chrome (e.g. quitting).
function Menu({
  items,
  extras,
}: {
  items: { label: string; danger?: boolean; onClick: () => void }[]
  extras?: ReactNode
}) {
  const [open, setOpen] = useState(false)
  useEscapeToClose(() => setOpen(false), open)
  return (
    <div className="menu">
      <button
        className="menu-btn"
        aria-label="Match menu"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        ⋮
      </button>
      {open && (
        <>
          <div className="menu-backdrop" onClick={() => setOpen(false)} />
          <div className="menu-pop" role="menu">
            {/* Shown only on narrow screens, where the HUD tucks its status
                (score / round) in here rather than wrapping the bar. */}
            {extras && <div className="menu-extras">{extras}</div>}
            {items.map(({ label, danger, onClick }) => (
              <button
                key={label}
                role="menuitem"
                className={danger ? 'danger' : undefined}
                onClick={() => {
                  setOpen(false)
                  onClick()
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function Hud({
  env,
  clock,
  turnClock,
  session,
  extras,
  onExit,
  onQuit,
}: {
  env: Envelope
  clock: string
  turnClock: string
  session: Session
  extras: ReactNode
  onExit: () => void
  onQuit: () => void
}) {
  const [copied, setCopied] = useState(false)
  const matchClock = (
    <span className="hud-clock">
      Turn {env.turn_count} · {clock}
    </span>
  )
  if (env.status === 'finished') {
    const verdict =
      env.result === null
        ? 'Match canceled.'
        : env.forfeited_by !== null
        ? env.forfeited_by === env.seat
          ? 'You quit.'
          : 'Opponent quit — you win!'
        : (() => {
            const winner = env.result?.winner as number | null
            return winner === null ? 'Draw.' : winner === env.seat ? 'You win!' : 'You lose.'
          })()
    return (
      <header className="hud">
        <strong className="hud-verdict">{verdict}</strong>
        <div className="hud-right">
          {extras && <span className="hud-extras">{extras}</span>}
          {matchClock}
          <button className="primary" onClick={onExit}>
            Back to lobby
          </button>
        </div>
      </header>
    )
  }
  if (env.status === 'waiting') {
    const link = `${location.origin}${location.pathname}#/join/${session.joinCode}`
    const copyLink = async () => {
      if (!(await copyText(link))) return
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    }
    return (
      <header className="hud">
        <div>
          <span className="hud-turn">Waiting for an opponent…</span>
          <div className="dim hud-join">
            join code <strong>{session.joinCode}</strong> · same network:{' '}
            <span className="hud-link">{link}</span>{' '}
            <button className="hud-copy" onClick={() => void copyLink()}>
              {copied ? 'Copied' : 'Copy link'}
            </button>
          </div>
        </div>
        <Menu items={[{ label: 'Quit match', danger: true, onClick: onQuit }]} />
      </header>
    )
  }
  // The turn pill wears the active player's seat color, so your own color is
  // the thing that lights up when it's your move (and the opponent's when
  // it's theirs) — seat 0 is --p0, seat 1 is --p1.
  const activeSeat = env.to_move ?? env.seat
  return (
    <header className="hud">
      <span
        className="hud-turn"
        style={{
          background: `var(--p${activeSeat})`,
          color: `var(--p${activeSeat}-ink)`,
          borderColor: 'var(--ink)',
        }}
      >
        {env.your_turn ? 'Your turn' : "Opponent's turn"} · {turnClock}
      </span>
      <div className="hud-right">
        {extras && <span className="hud-extras">{extras}</span>}
        {matchClock}
        <Menu items={[{ label: 'Quit match', danger: true, onClick: onQuit }]} extras={extras} />
      </div>
    </header>
  )
}

export function MatchScreen({
  session,
  freshlyCreated = false,
  onExit,
  onError,
}: {
  session: Session
  // The creator entered this match moments ago (vs restoring a stored
  // session on reload): it necessarily started out waiting.
  freshlyCreated?: boolean
  onExit: () => void
  onError: (msg: string) => void
}) {
  const [env, setEnv] = useState<Envelope | null>(null)
  const [meta, setMeta] = useState<Record<string, unknown>>({})
  const [hudExtras, setHudExtras] = useState<ReactNode>(null)
  const [confirmDialog, ask] = useConfirm()
  const envRef = useRef<Envelope | null>(null)
  const absorbedAtRef = useRef(Date.now())

  const absorb = useCallback((e: Envelope) => {
    const prev = envRef.current
    const merged = mergeEnvelope(prev, e)
    if (merged === prev) return
    envRef.current = merged
    absorbedAtRef.current = Date.now()
    setEnv(merged)
    if (e.meta) setMeta(e.meta)
  }, [])

  // Ding when the opponent joins — the creator is usually waiting in
  // another tab or across the room. Only on the observed transition, so a
  // reload of an in-progress match stays quiet. A freshly created match
  // observably started out waiting, so it may chime even if the opponent
  // joined before the first poll resolved.
  const prevStatus = useRef<MatchStatus | undefined>(freshlyCreated ? 'waiting' : undefined)
  useEffect(() => {
    const prev = prevStatus.current
    prevStatus.current = env?.status
    if (prev === 'waiting' && env?.status === 'in_progress') playSound('joined')
  }, [env?.status])

  // Ding when it becomes your turn — eyes drift away while the opponent
  // thinks. Only on an observed flip mid-game: joining or reloading into
  // your own turn stays quiet, and the match-start flip is already covered
  // by the join sound.
  const prevTurn = useRef({ status: env?.status, yours: env?.your_turn })
  useEffect(() => {
    const prev = prevTurn.current
    prevTurn.current = { status: env?.status, yours: env?.your_turn }
    if (prev.status === 'in_progress' && env?.status === 'in_progress' && !prev.yours && env.your_turn)
      playSound('your-turn')
  }, [env?.status, env?.your_turn])

  // The server's elapsed_seconds only refreshes when the state changes, so
  // tick locally once a second to keep the clock moving between polls.
  const [, setTick] = useState(0)
  const running = env?.status === 'in_progress'
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(id)
  }, [running])

  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    // Self-rescheduling rather than setInterval: the next poll is only fired
    // after the previous one settles, so a slow response (backgrounded tab,
    // laggy LAN) can never leave two requests in flight to resolve out of
    // order and let a stale envelope clobber a newer one.
    const tick = async (initial: boolean) => {
      try {
        const resp = await getState(session, initial ? undefined : envRef.current?.version)
        if (stopped) return
        // An unchanged poll (no envelope in the response) still reschedules.
        if ('observation' in resp) absorb(resp)
      } catch (err) {
        if (!stopped && err instanceof ApiError && (err.status === 404 || err.status === 403)) {
          onError('Match no longer exists on the server.')
          onExit()
          return
        }
        // transient network errors: keep polling silently
      }
      if (!stopped) timer = setTimeout(() => tick(false), POLL_MS)
    }
    tick(true)
    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
    }
  }, [session, absorb, onExit, onError])

  // Stable identity so a memoized Board doesn't re-render on every 1s clock
  // tick (which only touches the `tick` state below, not this callback).
  const submitAction = useCallback(
    async (action: number) => {
      try {
        const next = await postAction(session, action)
        absorb(next)
        return next
      } catch (err) {
        if (err instanceof ApiError) onError(err.message)
        else onError(String(err))
        return false
      }
    },
    [session, absorb, onError],
  )

  const quit = async () => {
    const prompt =
      env?.status === 'in_progress' ? 'Quit this match? Your opponent wins by forfeit.' : 'Quit this match?'
    if (!(await ask(prompt, { confirmLabel: 'Quit match', danger: true }))) return
    try {
      await leaveMatch(session)
    } catch (err) {
      // Leaving anyway is still the right outcome even if the request failed
      // (e.g. the match was already gone) -- don't strand the player here.
      if (err instanceof ApiError) onError(err.message)
      else onError(String(err))
    }
    onExit()
  }

  if (!env) return <p className="dim">Loading…</p>

  // Both clocks come from the server (so they survive reloads) and tick
  // locally between polls.
  const sinceAbsorb = running ? (Date.now() - absorbedAtRef.current) / 1000 : 0
  const elapsed = env.elapsed_seconds + sinceAbsorb
  const turnElapsed = env.turn_elapsed_seconds + sinceAbsorb
  const Board = renderers[env.game_id]
  return (
    <div className="match">
      <Hud
        env={env}
        clock={formatClock(elapsed)}
        turnClock={formatClock(turnElapsed)}
        session={session}
        extras={hudExtras}
        onExit={onExit}
        onQuit={quit}
      />
      {env.status === 'waiting' ? null : Board ? (
        <Board
          observation={env.observation}
          meta={meta}
          seat={env.seat}
          yourTurn={env.your_turn}
          legalActions={env.legal_actions}
          history={env.history}
          result={env.result}
          submitAction={submitAction}
          reportHud={setHudExtras}
        />
      ) : (
        <p>
          No renderer registered for <code>{env.game_id}</code>.
        </p>
      )}
      {confirmDialog}
    </div>
  )
}
