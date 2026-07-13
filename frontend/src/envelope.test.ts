import { describe, expect, it } from 'vitest'
import { mergeEnvelope } from './envelope'
import type { Envelope } from './types'

function envelope(version: number, overrides: Partial<Envelope> = {}): Envelope {
  return {
    version,
    game_id: 'kahuna',
    seat: 0,
    status: 'in_progress',
    to_move: 0,
    your_turn: true,
    observation: {},
    legal_actions: [],
    history: [],
    history_from: 0,
    result: null,
    forfeited_by: null,
    turn_count: version,
    elapsed_seconds: 0,
    turn_elapsed_seconds: 0,
    ...overrides,
  }
}

describe('mergeEnvelope', () => {
  it('preserves the POST envelope when a delayed poll returns the same version', () => {
    const postResponse = envelope(2)
    const delayedPollResponse = envelope(2)

    expect(mergeEnvelope(postResponse, delayedPollResponse)).toBe(postResponse)
  })

  it('splices a newer polling history delta onto the absorbed prefix', () => {
    const first = envelope(2, {
      history: [{ actor: 0, meta: { action: 'first' } }],
    })
    const delta = envelope(3, {
      history_from: 1,
      history: [{ actor: 1, meta: { action: 'second' } }],
    })

    expect(mergeEnvelope(first, delta).history).toEqual([
      { actor: 0, meta: { action: 'first' } },
      { actor: 1, meta: { action: 'second' } },
    ])
  })
})
