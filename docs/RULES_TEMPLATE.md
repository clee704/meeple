# <GAME NAME> — Rules contract

> **This document is a hard gate.** No engine code may be written
> for this game until this file is complete, every rule is cited, all
> `MUST-VERIFY` items are resolved, and the human sign-off below is checked.
> Do **not** fill this in from memory — cite a real source for every rule.

## Status

- **State:** DRAFT  *(change to VERIFIED only when complete)*
- **Human verified:** [ ]  — name / date: ____________________
- **Sources** (≥2 authoritative; the official rulebook is mandatory):
  1. <title> — <url>
  2. <title> — <url>

## Components & players

- Players: <n> (or range)
- Pieces/cards/tokens: <list with exact counts>

## Setup

<exact starting state: hands, board, decks, face-up cards, who goes first>

## Turn structure

<precise sequence of a turn. Define it in terms of ATOMIC sub-actions so the
game tree is clean — e.g. "place one X", "end turn", "draw" — not "do several
things at once". Note any hand limits / forced draws.>

## Legal actions (enumeration)

<exactly which actions are legal at a decision node, and their preconditions.
This defines `legal_actions()`.>

## State transitions & special mechanics

<how each action changes state; cascades; control/ownership rules; anything that
must be recomputed to a fixpoint after a change.>

## Chance & hidden information

- **Public** (both/all players see): <...>
- **Hidden** (per-player): <...>
- **Chance events** (and their distributions): <...>

*(This section drives the information-state tensor and the solver choice.)*

## Terminal conditions & scoring

<exact end trigger(s) and the exact scoring/win formula. Include tiebreakers.
Be numeric — "+1 / +2 / difference", not "some points".>

## GameSpec

```
name                  = "<game>"
num_players           = <n>
perfect_information    = <bool>
has_chance            = <bool>
zero_sum              = <bool>
num_distinct_actions  = <int>          # action-space upper bound (network output dim)
```

## Action encoding

<the fixed integer index scheme for actions, and how it sums to
num_distinct_actions. This must be stable — tests and nets depend on it.>

## Worked example / known position (for tests)

<at least one concrete position with the expected legal actions and, if
terminal, the expected returns. This becomes a regression test.>

## OPEN / MUST-VERIFY (BLOCKING)

- [ ] <each uncertain rule — must be resolved & checked off before coding>

## Rules-first checklist

- [ ] Every rule above cites a source.
- [ ] No `MUST-VERIFY` items remain open.
- [ ] GameSpec and action encoding are fully specified.
- [ ] At least one worked example is provided.
- [ ] Human sign-off checked at the top.
