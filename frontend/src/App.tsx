import { useCallback, useEffect, useRef, useState } from 'react'
import { clearSession, joinMatch, loadSession, saveSession } from './api'
import { Lobby } from './Lobby'
import { MatchScreen } from './MatchScreen'
import type { Session } from './types'

export default function App() {
  const [session, setSession] = useState<Session | null>(loadSession)
  const [toast, setToast] = useState<string | null>(null)
  // True only when the session was entered on this page-load (a create/join
  // action), not restored from storage: a fresh creator session is known to
  // have started out waiting, even if the opponent joins before the first
  // poll observes it (see MatchScreen and its join chime).
  const fresh = useRef(false)

  const showError = useCallback((msg: string) => {
    setToast(msg)
    window.setTimeout(() => setToast(null), 4000)
  }, [])

  const enter = useCallback((s: Session) => {
    saveSession(s)
    fresh.current = true
    setSession(s)
  }, [])

  const exit = useCallback(() => {
    clearSession()
    setSession(null)
  }, [])

  // Shareable LAN link: #/join/KJ4QZ joins that match (replacing any stored
  // session — an explicit link click wins over a stale game).
  useEffect(() => {
    const handle = async () => {
      const match = location.hash.match(/^#\/join\/([A-Za-z0-9]+)$/)
      if (!match) return
      history.replaceState(null, '', location.pathname)
      try {
        enter(await joinMatch(match[1]))
      } catch (e) {
        showError(String(e))
      }
    }
    handle()
    window.addEventListener('hashchange', handle)
    return () => window.removeEventListener('hashchange', handle)
  }, [enter, showError])

  return (
    <main>
      {session ? (
        <MatchScreen
          key={session.matchId}
          session={session}
          freshlyCreated={fresh.current && session.joinCode !== undefined}
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
