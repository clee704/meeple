# Kahuna — Rules

> This file has two jobs: it's the actual rulebook — something a person can
> read to learn how the game works — *and* it's a gate: no engine code gets
> written for this game until it's filled in, sourced, and checked off below.
>
> Most of the rules below are already verified against the sources cited.
> **Three open questions remain and block engine coding** — resolve them
> against the physical rulebook before implementing `legal_actions` or
> scoring.

Kahuna is a 2-player board game about building bridges between islands to
take control of them — and sometimes triggering a chain reaction that flips
several islands from your opponent's control to yours in one move.

## Status

- [ ] **Human verified** — check once you've compared everything below
  against a real source. *(Blocked right now — see Open questions.)*
- **Sources:**
  1. Official manual (Thames & Kosmos) — http://www.thamesandkosmos.com/manuals/full/691806_kahuna_manual.pdf
  2. UltraBoardGames rules — https://ultraboardgames.com/kahuna/game-rules.php
  3. BoardGameGeek — https://boardgamegeek.com/boardgame/394/kahuna

## Components & players

- **2 players.**
- **12 islands** connected by a fixed layout of bridge lines; each island has
  3–6 lines coming off it (the number is printed under the island's name on
  its card). Total bridge lines is about 24, but the exact count and layout
  still need tracing from the physical board — see Open question #1.
- **25 bridges + 10 control tokens per player.**
- **24 island cards** — 2 per island.

## Setup

- Each player starts with a hand of 3 cards.
- 3 cards are dealt face-up beside the board (public, and drawable).
- The rest of the deck forms a face-down draw pile.

## Turn structure

On your turn you can play any number of island cards (including zero), then
you must draw exactly one card. Hand limit is 5. Each played card is one
individual action:

- **`place(bridge_pos)`** — discard 1 card naming an island at either end of
  an empty bridge line, and place your bridge there.
- **`remove(bridge_pos)`** — remove one of your opponent's bridges. Which
  cards this costs is still an open question — see Open question #2.
- **`end_turn`** — stop playing cards for this turn; this is what triggers
  the draw.

```mermaid
flowchart TD
    A([Your turn starts]) --> B{Play a card?}
    B -->|place| C[place bridge, check for new control]
    B -->|remove| D[remove opponent bridge, check for lost control]
    C --> E{Control changed?}
    D --> E
    E -->|yes| F[cascade: recompute control<br/>on every island until stable]
    E -->|no| B
    F --> B
    B -->|end turn| G[draw one card — a chance event]
    G --> H([Opponent's turn])
```

After `end_turn`, the draw is a chance event — one card comes from the
face-down pile or possibly one of the 3 face-up cards (exactly how that
works is Open question #3) — and then it's the opponent's turn.

## State transitions & special mechanics (the core of the game)

This is the part that makes Kahuna interesting, so it's worth walking
through slowly:

- You **control** an island once you own a strict majority of its bridge
  lines (more than half — so on a 5-line island, 3 bridges is enough).
- The moment a placement gives you a *new* strict majority on an island, two
  things happen at once: you place your control token there, **and** every
  bridge your opponent owns touching that island is immediately removed.
- Removing those opponent bridges can, in turn, drop your opponent below
  majority on a *neighboring* island — so they lose control (and their
  token) there too. That can ripple further outward. This is the
  **cascade**.
- The rule of thumb: after *any* bridge is placed or removed, anywhere,
  recheck every island's control and keep resolving fallout until nothing
  changes anymore (a fixpoint), not just the one island you touched.
- Bridges and tokens are limited — 25 bridges and 10 tokens per player, total.
  Running out limits what you can still play.

## Chance & hidden information

- **Public**: the whole board (every bridge and who owns it), both players'
  placed tokens, the scores, which round it is, remaining bridge/token
  supplies, and the 3 face-up cards.
- **Hidden**: what's in each player's hand, and the order of the face-down
  pile.
- **Random events**: the end-of-turn draw.

## Terminal conditions & scoring

- A **scoring round** happens once the face-down pile is empty *and* the
  last of the 3 face-up cards has been drawn.
- After the 1st and 2nd scoring rounds: shuffle the discards into a new draw
  pile, deal 3 new face-up cards, and keep playing — players keep their
  current hands. The game ends after the 3rd scoring round.
- Points:
  - **1st scoring:** whoever controls more islands (by token count) gets +1.
  - **2nd scoring:** whoever controls more islands gets +2.
  - **3rd (final) scoring:** the leader's margin is the actual
    island/token difference between the two players.
  - **Tiebreak:** whoever has more bridges on the board; if still tied,
    nobody wins.
- Each player's final payoff is their net score difference (so the two
  payoffs always sum to 0).

## GameSpec

```
name                  = "kahuna"
num_players           = 2
perfect_information   = False
has_chance            = True
zero_sum              = True
num_distinct_actions  = 2 * <#bridge_pos> + 1     # place + remove per line, + end_turn  (≈ 49)
```

## Action encoding

Once the board graph is pinned down (Open question #1), the plan is a stable
integer scheme:
- `0 .. P-1` → `place(bridge_pos = i)`
- `P .. 2P-1` → `remove(bridge_pos = i - P)`
- `2P` → `end_turn`

where `P` is the number of bridge positions. `legal_actions()` filters these
down by: the line is free and you hold the required card (`place`); your
opponent owns that bridge and you hold the required card(s) (`remove`);
`end_turn` is always legal.

## Information-state tensor (for Deep CFR)

Per-bridge owner (3 possibilities × P positions) · per-island control, degree,
and each player's bridge count there · your hand, counted per island (12
numbers) · the 3 public face-up cards · cards seen/discarded so far this
round · bridges/tokens remaining · which round it is · scores · whether
you've already played a card this turn.

## Worked example

*(To fill in once the board graph exists — Open question #1.)* Should walk
through a small mid-game position: the board so far, the exact legal moves
available, and one placement that triggers a cascade (you gain control of an
island → strip at least one opponent bridge → your opponent loses a
neighboring island too), so the cascade logic has a concrete regression test.

## Open questions

- [ ] **MUST-VERIFY #1 — Exact board graph.** The full island adjacency and
  the exact count of bridge lines (`P`). This defines the whole action space
  — needs tracing directly from the physical board.
- [ ] **MUST-VERIFY #2 — Removal cost.** Which cards do you have to discard
  to remove a bridge? Likely the two island cards at that bridge's endpoints,
  but this needs confirming.
- [ ] **MUST-VERIFY #3 — Draw mechanics.** Can you draw from the 3 face-up
  cards as well as the face-down pile, and if a face-up slot is taken, how
  does it get refilled?

## Checklist

- [x] Every rule cites a source.
- [ ] No open questions remain unresolved. **(3 open — blocking)**
- [ ] GameSpec and action encoding are fully specified. *(waiting on #1)*
- [ ] A worked example is provided. *(waiting on #1)*
- [ ] Human verified, at the top.
