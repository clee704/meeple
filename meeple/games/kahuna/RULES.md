# Kahuna — Rules contract

> **This document is a hard gate.** Most rules below are verified against the
> sources cited. **Three items remain `MUST-VERIFY` and BLOCK engine coding** —
> resolve them against the physical rulebook before implementing
> `legal_actions` / scoring.

## Status

- **State:** DRAFT (3 open MUST-VERIFY items)
- **Human verified:** [ ] — name / date: ____________________
- **Sources:**
  1. Official manual (Thames & Kosmos) — http://www.thamesandkosmos.com/manuals/full/691806_kahuna_manual.pdf
  2. UltraBoardGames rules — https://ultraboardgames.com/kahuna/game-rules.php
  3. BoardGameGeek — https://boardgamegeek.com/boardgame/394/kahuna

## Components & players

- **2 players.**
- **12 islands** connected by a fixed planar graph of bridge lines; each island
  has degree **3–6** (the number of lines is printed under the island's name on
  its card). **Total bridge lines ≈ 24** — *exact value is MUST-VERIFY #1.*
- **25 bridges + 10 control tokens per player.**
- **24 island cards** — **2 per island.**

## Setup

- Each player starts with a **hand of 3** cards.
- **3 cards face-up** beside the board (public, drawable).
- Remaining cards form the **face-down draw pile**.

## Turn structure

On your turn you may **play any number of island cards** (including none) — each
played card is one atomic action — and **then draw exactly one card**. **Hand
limit = 5.** Model as atomic sub-actions:

- **`place(bridge_pos)`** — discard **1** card naming one endpoint island of a
  *free* line; place your bridge there.
- **`remove(bridge_pos)`** — remove an opponent's bridge. *Cost is MUST-VERIFY
  #2* (likely the two endpoint-island cards of that bridge).
- **`end_turn`** — stop playing cards; triggers the draw (a chance node).

After `end_turn`: a chance node draws one card — from the face-down pile **or**
one of the 3 public face-up cards (*draw/refill mechanics = MUST-VERIFY #3*) —
then control passes to the opponent.

## State transitions & special mechanics (the core of the game)

- **Control = strict majority** of an island's lines (`> degree/2`).
- When a placement gives you a new strict majority on an island: **place your
  token there AND immediately remove ALL opponent bridges connected to that
  island.**
- That removal can drop the opponent below majority on **neighboring** islands →
  they lose those tokens → **cascade.**
- Therefore: after **any** board change (place or remove), **recompute control
  for all islands to a fixpoint**, placing/removing tokens accordingly.
- Bridges and tokens are finite supplies (25 / 10 each).

## Chance & hidden information

- **Public:** the board (all bridges + owners), both token sets, scores, round,
  supplies, and the **3 face-up cards.**
- **Hidden:** each player's hand contents, and the face-down pile order.
- **Chance:** the end-of-turn draw.

## Terminal conditions & scoring

- A **scoring** triggers when the **face-down pile is empty AND the last of the 3
  face-up cards has been drawn.**
- After the **1st and 2nd** scorings: reshuffle the discard into a new draw pile,
  deal 3 new face-up cards; **players keep their hands.** After the **3rd**
  scoring the game ends.
- Points:
  - **1st scoring:** token-majority leader **+1**
  - **2nd scoring:** token-majority leader **+2**
  - **3rd (final) scoring:** leader gets the **island/token difference**
  - **Tiebreak:** most bridges on the board; still tied → no winner.
- `returns()` = the two players' net score difference at game end (zero-sum).

## GameSpec

```
name                  = "kahuna"
num_players           = 2
perfect_information    = False
has_chance            = True
zero_sum              = True
num_distinct_actions  = 2 * <#bridge_pos> + 1     # place + remove per line, + end_turn  (≈ 49)
```

## Action encoding

Stable integer scheme (fix once the board graph is encoded):
- `0 .. P-1`        → `place(bridge_pos = i)`
- `P .. 2P-1`       → `remove(bridge_pos = i-P)`
- `2P`              → `end_turn`

where `P = #bridge_pos`. `legal_actions` filters by: line free + you hold a
required card (place); opponent owns that bridge + you hold required card(s)
(remove); `end_turn` always legal.

## Information-state tensor (for Deep CFR)

per-bridge owner (3×P) · per-island control + degree + my/opp bridge counts ·
my hand counts per island (12) · **public face-up cards** (12) · cards
seen/discarded this round (12) · bridges/tokens remaining · round one-hot ·
scores · cards-played-this-turn flag.

## Worked example / known position (for tests)

*(Fill once the board graph exists.)* Provide: a small mid-game position, the
exact set of legal actions, and a placement that triggers a cascade (gain
control of an island → strip ≥1 opponent bridge → opponent loses a neighbor) so
the cascade logic has a regression test.

## OPEN / MUST-VERIFY (BLOCKING — resolve before coding the engine)

- [ ] **#1 — Exact board graph:** the full island adjacency and the exact count
  of bridge lines (`P`). This defines the action space. Trace it from the board.
- [ ] **#2 — Removal cost:** which cards must be discarded to remove a bridge —
  the two endpoint-island cards (likely) vs two cards of the same island?
- [ ] **#3 — Draw mechanics:** may you draw from the 3 face-up cards as well as
  the face-down pile, and how is a taken face-up slot refilled?

## Rules-first checklist

- [ ] Every rule cites a source. *(done above)*
- [ ] No MUST-VERIFY items remain open. **(3 open — blocking)**
- [ ] GameSpec & action encoding fully specified. *(pending P from #1)*
- [ ] Worked example provided. *(pending #1)*
- [ ] Human sign-off checked at top.
