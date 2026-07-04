// Synthesized UI sounds — short oscillator envelopes via the Web Audio API,
// so there are no audio assets to ship. Everything is deliberately quiet and
// brief; playback is best-effort (no sound is never an error).

export type SoundName =
  | 'select' // a card picked up for play/discard
  | 'deselect' // a selected card put back
  | 'play' // card(s) played on the board (one sound per batch)
  | 'discard' // card(s) discarded face-down
  | 'your-turn' // the opponent finished — it's your move
  | 'round' // an interim round (1/2) scored
  | 'game-over' // final scoring — the game is done
  | 'joined' // an opponent joined your match
  | 'created' // your match was created

let ctx: AudioContext | null = null

function context(): AudioContext {
  ctx ??= new AudioContext()
  // Browsers gate audio behind a user gesture. Sounds fired from a click
  // resume the context themselves; poll-driven ones (e.g. "opponent
  // joined") only work once some earlier gesture has unlocked it.
  if (ctx.state === 'suspended') void ctx.resume()
  return ctx
}

// Unlock on the first gesture anywhere, so poll-driven sounds can play even
// if no sound-producing click happened first.
window.addEventListener('pointerdown', () => void context(), { once: true })

function tone(at: number, freq: number, dur: number, peak: number, type: OscillatorType) {
  const ac = context()
  const t = ac.currentTime + at
  const osc = ac.createOscillator()
  const gain = ac.createGain()
  osc.type = type
  osc.frequency.value = freq
  gain.gain.setValueAtTime(0, t)
  gain.gain.linearRampToValueAtTime(peak, t + 0.01)
  gain.gain.exponentialRampToValueAtTime(0.0005, t + dur)
  osc.connect(gain).connect(ac.destination)
  osc.start(t)
  osc.stop(t + dur + 0.05)
}

const SOUNDS: Record<SoundName, () => void> = {
  select: () => tone(0, 880, 0.08, 0.05, 'sine'),
  deselect: () => tone(0, 620, 0.08, 0.04, 'sine'),
  play: () => {
    // A woody "thock": low triangle body with a faint octave sparkle.
    tone(0, 220, 0.12, 0.09, 'triangle')
    tone(0, 440, 0.1, 0.03, 'sine')
  },
  discard: () => tone(0, 150, 0.16, 0.08, 'triangle'),
  'your-turn': () => {
    tone(0, 660, 0.09, 0.05, 'sine')
    tone(0.08, 990, 0.22, 0.05, 'sine')
  },
  round: () => {
    tone(0, 523, 0.18, 0.06, 'sine') // C5
    tone(0.16, 784, 0.3, 0.06, 'sine') // G5
  },
  'game-over': () => {
    tone(0, 523, 0.18, 0.06, 'sine') // C5
    tone(0.16, 659, 0.18, 0.06, 'sine') // E5
    tone(0.32, 784, 0.2, 0.06, 'sine') // G5
    tone(0.48, 1047, 0.5, 0.06, 'sine') // C6
  },
  joined: () => {
    tone(0, 740, 0.12, 0.05, 'sine')
    tone(0.12, 988, 0.25, 0.05, 'sine')
  },
  created: () => {
    tone(0, 587, 0.12, 0.05, 'sine')
    tone(0.1, 880, 0.2, 0.05, 'sine')
  },
}

export function playSound(name: SoundName): void {
  try {
    SOUNDS[name]()
  } catch {
    // No AudioContext, or the autoplay policy blocked it — stay silent.
  }
}
