import type { Envelope } from './types'

export function mergeEnvelope(prev: Envelope | null, next: Envelope): Envelope {
  // Once a version has been absorbed, another envelope at that version cannot
  // add state. Preserve object identity so delayed polls cannot reset renderer
  // interaction that began after a POST response arrived first.
  if (prev && next.version <= prev.version) return prev

  // Polls receive only the history entries newer than their since-version
  // (history_from > 0) — splice them onto the prefix already held.
  return next.history_from > 0 && prev
    ? { ...next, history: [...prev.history.slice(0, next.history_from), ...next.history] }
    : next
}
