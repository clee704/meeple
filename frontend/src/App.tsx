import { useCallback, useEffect, useRef, useState } from 'react'
import { clearSession, joinMatch, loadSession, saveSession } from './api'
import { Lobby } from './Lobby'
import { MatchScreen } from './MatchScreen'
import type { Session } from './types'

function joinCodeFromHash(): string | null {
  return location.hash.match(/^#\/join\/([A-Za-z0-9]+)$/)?.[1].toUpperCase() ?? null
}

function clearJoinHash(): void {
  history.replaceState(null, '', location.pathname + location.search)
}

function loadInitialSession(): Session | null {
  const code = joinCodeFromHash()
  if (!code) return loadSession()
  const tabSession = loadSession({ includeSharedFallback: false })
  return tabSession?.joinCode?.toUpperCase() === code ? tabSession : null
}

export default function App() {
  const [session, setSession] = useState<Session | null>(loadInitialSession)
  const [toast, setToast] = useState<string | null>(null)
  // True only when this page-load created the match. A fresh creator session
  // is known to have started out waiting, even if the opponent joins before
  // the first poll observes it (see MatchScreen and its join chime).
  const fresh = useRef(false)
  const hashJoin = useRef<ReturnType<typeof joinMatch> | null>(null)

  const showError = useCallback((msg: string) => {
    setToast(msg)
    window.setTimeout(() => setToast(null), 4000)
  }, [])

  const enter = useCallback((s: Session, created = false) => {
    saveSession(s)
    fresh.current = created
    setSession(s)
  }, [])

  const exit = useCallback(() => {
    clearSession()
    setSession(null)
  }, [])

  // Shareable LAN link: #/join/KJ4QZ joins that match. An explicit join link
  // wins over the shared fallback copy, but a tab already seated in that
  // match keeps its own tab-scoped session.
  useEffect(() => {
    const handle = async () => {
      const code = joinCodeFromHash()
      if (!code) return
      const tabSession = loadSession({ includeSharedFallback: false })
      const hasMatchingTabSession =
        tabSession?.joinCode?.toUpperCase() === code && tabSession.matchId === session?.matchId
      if (hasMatchingTabSession) {
        clearJoinHash()
        return
      }
      // Joining mutates the server as soon as the request succeeds, so only
      // one hash join may be in flight. A later hash is reconsidered if this
      // request fails; it cannot supersede a seat claim whose token we own.
      if (hashJoin.current) return
      const request = joinMatch(code)
      hashJoin.current = request
      try {
        const joined = await request
        clearJoinHash()
        enter(joined)
      } catch (e) {
        if (joinCodeFromHash() === code) showError(String(e))
      } finally {
        if (hashJoin.current === request) hashJoin.current = null
        const queuedCode = joinCodeFromHash()
        if (queuedCode && queuedCode !== code) void handle()
      }
    }
    handle()
    window.addEventListener('hashchange', handle)
    return () => window.removeEventListener('hashchange', handle)
  }, [enter, session?.matchId, showError])

  return (
    <main>
      {session ? (
        <MatchScreen
          key={session.matchId}
          session={session}
          freshlyCreated={fresh.current}
          onExit={exit}
          onError={showError}
        />
      ) : (
        <Lobby onEnter={enter} onError={showError} />
      )}
      {toast && <div className="toast">{toast}</div>}
    </main>
  )
}
