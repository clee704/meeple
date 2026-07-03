import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, getState, leaveMatch, postAction } from './api'
import { useConfirm } from './Confirm'
import { renderers } from './games/registry'
import type { Envelope, Session } from './types'

const POLL_MS = 1000

function formatClock(seconds: number): string {
  const t = Math.max(0, Math.floor(seconds))
  const h = Math.floor(t / 3600)
  const mm = String(Math.floor((t % 3600) / 60)).padStart(2, '0')
  const ss = String(t % 60).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

// Kebab (⋮) dropdown anchored to the HUD's top-right corner, for actions
// that shouldn't sit as bare buttons in the chrome (e.g. quitting).
function Menu({ items }: { items: { label: string; danger?: boolean; onClick: () => void }[] }) {
  const [open, setOpen] = useState(false)
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
  onExit,
  onQuit,
}: {
  env: Envelope
  clock: string
  turnClock: string
  session: Session
  onExit: () => void
  onQuit: () => void
}) {
  const matchClock = (
    <span className="hud-clock">
      Turn {env.turn_count} · {clock}
    </span>
  )
  if (env.status === 'finished') {
    const verdict =
      env.forfeited_by !== null
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
    return (
      <header className="hud">
        <div>
          <span className="hud-turn">Waiting for an opponent…</span>
          <div className="dim hud-join">
            join code <strong>{session.joinCode}</strong> · same network:{' '}
            <a href={link}>{link}</a>
          </div>
        </div>
        <Menu items={[{ label: 'Quit match', danger: true, onClick: onQuit }]} />
      </header>
    )
  }
  return (
    <header className="hud">
      <span className={env.your_turn ? 'hud-turn you' : 'hud-turn'}>
        {env.your_turn ? 'Your turn' : "Opponent's turn"} · {turnClock}
      </span>
      <div className="hud-right">
        {matchClock}
        <Menu items={[{ label: 'Quit match', danger: true, onClick: onQuit }]} />
      </div>
    </header>
  )
}

export function MatchScreen({
  session,
  onExit,
  onError,
}: {
  session: Session
  onExit: () => void
  onError: (msg: string) => void
}) {
  const [env, setEnv] = useState<Envelope | null>(null)
  const [meta, setMeta] = useState<Record<string, unknown>>({})
  const [confirmDialog, ask] = useConfirm()
  const envRef = useRef<Envelope | null>(null)
  const absorbedAtRef = useRef(Date.now())
  // When the current turn began, as seen by this client — the server
  // doesn't report it, so a page (re)load starts the count from zero.
  const turnStartRef = useRef(Date.now())

  const absorb = useCallback((e: Envelope) => {
    if (envRef.current?.turn_count !== e.turn_count) turnStartRef.current = Date.now()
    envRef.current = e
    absorbedAtRef.current = Date.now()
    setEnv(e)
    if (e.meta) setMeta(e.meta)
  }, [])

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
    const tick = async (initial: boolean) => {
      try {
        const resp = await getState(session, initial ? undefined : envRef.current?.version)
        if (stopped || !('observation' in resp)) return // unchanged since last poll
        absorb(resp)
      } catch (err) {
        if (!stopped && err instanceof ApiError && (err.status === 404 || err.status === 403)) {
          onError('Match no longer exists on the server.')
          onExit()
        }
        // transient network errors: keep polling silently
      }
    }
    tick(true)
    const id = setInterval(() => tick(false), POLL_MS)
    return () => {
      stopped = true
      clearInterval(id)
    }
  }, [session, absorb, onExit, onError])

  const submitAction = async (action: number) => {
    try {
      absorb(await postAction(session, action))
      return true
    } catch (err) {
      if (err instanceof ApiError) onError(err.message)
      else onError(String(err))
      return false
    }
  }

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

  const elapsed =
    env.elapsed_seconds + (running ? (Date.now() - absorbedAtRef.current) / 1000 : 0)
  const turnElapsed = running ? (Date.now() - turnStartRef.current) / 1000 : 0
  const Board = renderers[env.game_id]
  return (
    <div className="match">
      <Hud
        env={env}
        clock={formatClock(elapsed)}
        turnClock={formatClock(turnElapsed)}
        session={session}
        onExit={onExit}
        onQuit={quit}
      />
      {Board ? (
        <Board
          observation={env.observation}
          meta={meta}
          seat={env.seat}
          yourTurn={env.your_turn}
          legalActions={env.legal_actions}
          history={env.history}
          result={env.result}
          submitAction={submitAction}
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
