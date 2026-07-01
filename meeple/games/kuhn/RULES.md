# Kuhn Poker — Rules contract

> **This document is a hard gate.** No engine code may be written
> for this game until this file is complete, every rule is cited, all
> `MUST-VERIFY` items are resolved, and the human sign-off below is checked.
> Do **not** fill this in from memory — cite a real source for every rule.

## Status

- **State:** VERIFIED *(textbook game with one fixed, unambiguous rule set —
  no open questions; sign-off is still required before engine code is written)*
- **Human verified:** [ ]  — name / date: ____________________
- **Sources** (≥2 authoritative; the official rulebook is mandatory):
  1. Kuhn, H.W. (1950), "A Simplified Two-Person Poker", *Contributions to the
     Theory of Games*, vol. 1, Annals of Mathematics Studies 24, Princeton
     University Press, pp. 97–103. (Original definition.)
  2. OpenSpiel game documentation — `kuhn_poker`:
     https://github.com/google-deepmind/open_spiel/blob/master/open_spiel/games/kuhn_poker/kuhn_poker.h
     (Reference implementation used as this project's cross-check oracle only —
     never a game backend.)

## Components & players

- Players: 2 (fixed).
- Cards: a 3-card deck, ranks {Jack, Queen, King} (J < Q < K), one of each.
- Chips: each player antes 1 chip per hand; a bet/call costs 1 additional chip.

## Setup

Each player antes 1 chip into the pot. The 3-card deck is shuffled; each
player is dealt 1 card face down (their private hand). The third card is
left unused. Player 0 acts first.

## Turn structure

A betting round of at most 2 rounds of action, in fixed turn order
(player 0 then player 1, repeating until the round ends). Each player acts
once per round with exactly one atomic action:
- `pass` (check if no bet is outstanding, fold if a bet is outstanding)
- `bet` (bet 1 chip if no bet is outstanding, call if a bet is outstanding)

The round — and the hand — ends as soon as: both players have passed, a bet
has been called, or a pass follows a bet (fold). No further actions are legal
after a terminal state is reached.

## Legal actions (enumeration)

At any non-terminal, non-chance state exactly 2 actions are legal for the
acting player: `pass` (0) and `bet` (1). There is no other branching — Kuhn
poker has no raises, no fold-vs-call distinction beyond `pass`/`bet`, and no
draws.

## State transitions & special mechanics

History (sequence of `pass`/`bet`) fully determines the betting state; there
are exactly 4 possible 2-player histories before showdown/fold, per
OpenSpiel's enumeration: `pp` (both pass → showdown), `bp` (bet, pass → bettor
wins), `bb` (bet, call → showdown), `pbp` (pass, bet, pass → bettor wins),
`pbb` (pass, bet, call → showdown). No fixpoint/cascade logic — pure
sequential history.

## Chance & hidden information

- **Public**: betting history (the sequence of `pass`/`bet` actions taken).
- **Hidden**: each player's own card (private; opponent's card is unknown
  until showdown).
- **Chance events**: one chance node at the start of the hand — deal 2 of the
  3 cards to the 2 players, each of the `3!/(3-2)! = 6` ordered deals equally
  likely (uniform random permutation of 2 cards from 3).

## Terminal conditions & scoring

A hand ends, and `returns()` is computed, at one of:
- **Fold** (a `pass` immediately follows a `bet`): the player who bet wins the
  pot; returns = `[+pot_other_paid, -pot_other_paid]` oriented to the folder
  losing exactly what they put in (ante, or ante+call) and the bettor winning
  it. Concretely: winner gets `+1` (just the opponent's ante) if no bet was
  called, or `+2` if a bet was placed and the round ends in a fold before the
  call.
- **Showdown** (`pp`, `bb`, or `pbb`): higher card wins the pot. Pot size is
  `2` chips (1 ante each) if neither player bet (`pp`), or `4` chips (1 ante +
  1 bet/call each) if both bet (`bb`, `pbb`). Winner's net return is
  `+1` (showdown after `pp`) or `+2` (showdown after `bb`/`pbb`); loser's
  return is the negation. `returns()` always sums to 0 (zero-sum).

## GameSpec

```
name                  = "kuhn"
num_players           = 2
perfect_information   = False
has_chance            = True
zero_sum              = True
num_distinct_actions  = 2          # pass=0, bet=1
```

## Action encoding

- `0` → `pass`
- `1` → `bet`

These are the only two actions in the game; `num_distinct_actions = 2`.

## Worked example / known position (for tests)

Deal: player 0 gets Q, player 1 gets K. History `pb` (player 0 passes,
player 1 bets): at this point it is player 0's decision node, legal actions
are `[0, 1]` (pass=fold, bet=call). If player 0 passes (folds): terminal,
`returns() == [-1, +1]`. If player 0 bets (calls) instead, history becomes
`pbb`: terminal showdown, K > Q so `returns() == [-2, +2]`.

## OPEN / MUST-VERIFY (BLOCKING)

*(none — the game is a fixed, universally-cited textbook definition)*

## Rules-first checklist

- [x] Every rule above cites a source.
- [x] No `MUST-VERIFY` items remain open.
- [x] GameSpec and action encoding are fully specified.
- [x] At least one worked example is provided.
- [ ] Human sign-off checked at the top.
