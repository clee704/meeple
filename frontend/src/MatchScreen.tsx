import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, getState, leaveMatch, postAction } from './api'
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

function Banner({
  env,
  clock,
  session,
  onExit,
  onQuit,
}: {
  env: Envelope
  clock: string
  session: Session
  onExit: () => void
  onQuit: () => void
}) {
  const turnClock = (
    <span className="dim">
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
      <div className="banner">
        <strong>{verdict}</strong>
        {turnClock}
        <button onClick={onExit}>Back to lobby</button>
      </div>
    )
  }
  if (env.status === 'waiting') {
    const link = `${location.origin}${location.pathname}#/join/${session.joinCode}`
    return (
      <div className="banner">
        <div>
          Waiting for an opponent — join code <strong>{session.joinCode}</strong>
          <div className="dim">
            Same network: <a href={link}>{link}</a>
          </div>
        </div>
        <button onClick={onQuit}>Quit</button>
      </div>
    )
  }
  return (
    <div className="banner">
      {env.your_turn ? 'Your turn.' : "Opponent's turn…"}
      {turnClock}
      <button onClick={onQuit}>Quit</button>
    </div>
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
  const envRef = useRef<Envelope | null>(null)
  const absorbedAtRef = useRef(Date.now())

  const absorb = useCallback((e: Envelope) => {
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
    if (!confirm(prompt)) return
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

  if (!env) return <div className="banner">Loading…</div>

  const elapsed =
    env.elapsed_seconds + (running ? (Date.now() - absorbedAtRef.current) / 1000 : 0)
  const Board = renderers[env.game_id]
  return (
    <div className="match">
      <Banner env={env} clock={formatClock(elapsed)} session={session} onExit={onExit} onQuit={quit} />
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
    </div>
  )
}
