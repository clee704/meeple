# Kahuna — Rules

> This file has two jobs: it's the actual rulebook — something a person can
> read to learn how the game works — *and* it's a gate: no engine code gets
> written for this game until it's filled in, sourced, and checked off below.
>
> All rules below are verified against the sources cited, including the
> exact board graph — human sign-off is the last step before engine coding.

Kahuna is a 2-player board game about building bridges between islands to
take control of them. Taking one island can knock your opponent out of
control of a *neighboring* island too — not by flipping it to you outright,
but by leaving it uncontrolled and open for whoever moves in next. That
slow, multi-turn tug-of-war over newly-vulnerable islands is the interesting
part of the game.

## Status

- [ ] **Human verified** — check once you've compared everything below
  against a real source.
- **Sources:**
  1. Official manual (Thames & Kosmos) — http://www.thamesandkosmos.com/manuals/full/691806_kahuna_manual.pdf
  2. UltraBoardGames rules — https://ultraboardgames.com/kahuna/game-rules.php
  3. BoardGameGeek — https://boardgamegeek.com/boardgame/394/kahuna

## Components & players

- **2 players.**
- **12 islands** connected by **27 bridge lines**, traced from the physical
  board:

![Kahuna board graph](board.svg)

(Mermaid's auto-layout couldn't hold this structure without adding
crossings, so this is a hand-placed SVG instead, with coordinates tuned to
match the physical board layout — all 27 edges are straight lines, none
passing within a node's radius of any island it doesn't connect to.)

  Each island's degree (lines touching it, and its majority threshold — the
  number of bridges needed for strict majority):

  | Island | Degree | Majority |
  |---|---|---|
  | ALOA | 3 | 2 |
  | BARI | 5 | 3 |
  | COCO | 4 | 3 |
  | DUDA | 4 | 3 |
  | ELAI | 6 | 4 |
  | FAAA | 5 | 3 |
  | GOLA | 4 | 3 |
  | HUNA | 5 | 3 |
  | IFFI | 5 | 3 |
  | JOJO | 5 | 3 |
  | KAHU | 5 | 3 |
  | LALE | 3 | 2 |

- **25 bridges + 10 control tokens per player.**
- **24 island cards** — 2 per island.

## Setup

- Each player starts with a hand of 3 cards.
- 3 cards are dealt face-up beside the board (public, and drawable).
- The rest of the deck forms a face-down draw pile.

## Turn structure

On your turn you can play any number of island cards (including zero), then
you end your turn by drawing or skipping (see below). `place` and `remove`
are each one atomic action, even though `remove` costs 2 cards at once:

- **`place(bridge_pos)`** — discard 1 card naming an island at either end of
  an empty bridge line, and place your bridge there.
- **`remove(bridge_pos)`** — remove one of your opponent's bridges, by
  discarding 2 cards, in one of two ways:
  - **Same island, twice:** discard 2 cards naming the *same* island to
    remove any one opponent bridge touching that island (your choice of
    which one, if they own more than one there).
  - **Two different islands:** discard 2 cards naming two *different*
    islands to remove the specific opponent bridge that directly connects
    those two islands (only legal if that exact bridge line exists and your
    opponent owns it).
- **Ending your turn** — one of:
  - **Draw blind** from the face-down pile (a chance event: the pile's
    order is hidden).
  - **Take a specific face-up card** (you can see all 3, so this is a
    deliberate pick, not chance). Immediately refill that now-empty slot by
    flipping the top card of the face-down pile face up — a chance event,
    since the pile's order is hidden, but it happens right away, not on a
    later turn.
  - **Skip** — end your turn without drawing at all. Only legal if your
    opponent did **not** also skip on their immediately preceding turn — two
    skips can't happen back-to-back.

Hand limit is 5.

```mermaid
flowchart TD
    A([Your turn starts]) --> B{Play a card?}
    B -->|place| C[Place a bridge on a line]
    C --> D{New strict majority for you<br/>on either endpoint island?}
    D -->|yes| E[Take that island's token +<br/>remove ALL opponent bridges there]
    D -->|no| B
    B -->|remove| H[Remove one opponent bridge]
    E --> F{Did any opponent bridge just<br/>removed drop them below majority<br/>on its other endpoint island?}
    H --> F
    F -->|yes| G[Opponent loses that token too —<br/>their other bridges there stay put]
    F -->|no| B
    G --> B
    B -->|end turn| J{How do you end it?}
    J -->|draw blind| K[Draw from face-down pile — chance]
    J -->|take face-up card| L[Take a specific visible card,<br/>then refill the slot from the pile — chance]
    J -->|skip, if allowed| M[No draw this turn]
    K --> N([Opponent's turn])
    L --> N
    M --> N
```

## State transitions & special mechanics (the core of the game)

**The rules, stated directly:**

1. You **control** an island whenever you currently own a strict majority of
   its bridge lines — strictly more than half, not just half. (5-line
   island: 3 bridges. 4-line island: also 3, not 2 — an even split isn't a
   majority for either side.) This isn't a flag that gets set once and then
   sticks; it's just whatever the current bridge count says, checked fresh
   every time a bridge changes.
2. The moment a `place` is what pushes your count on an island past strict
   majority for the first time, you immediately take that island's control
   token, **and** every bridge your opponent owns touching that one island
   is removed at once.

That's the whole rule set for control. Everything below is a consequence of
those two rules, not an additional one.

**What follows from that:**

- Strict majority needs more than half of a *fixed* line count, so only one
  player can ever hold it on a given island. Control therefore never
  transfers directly between players in one step — an island is always
  controlled by exactly one player, or by nobody.
- Rule 2 only fires on a *new* majority, and per the point above that's only
  possible on an island nobody already controls (you can't out-place an
  opponent who still holds their majority-supporting bridges). So `place`
  only ever *creates* control — it can't take control away from an existing
  holder directly.
- `remove` — a direct action, or the side effect in rule 2 — only ever
  works the other way: it *destroys* control, by dropping someone's count
  below majority. It never hands control to anyone else in that same step.
- Rule 2's bridge removal can still ripple to a second island: each bridge
  it strips sits on a line with another endpoint elsewhere, so the
  opponent's count *there* drops by one too. If that drops them below
  majority, they lose that island's token as well — but nothing more: their
  other bridges there are untouched, and nothing else gets removed. Losing
  majority only ever costs the token, never bridges by itself.
- That leaves the far island uncontrolled, not captured. Reclaiming it is a
  separate, later action, open to *either* player — whoever gets there
  first with a new majority triggers rule 2 all over again on *that*
  island. This cuts both ways: dethroning your opponent doesn't give you
  first claim on what opens up — if they rebuild majority there first, it's
  your bridges that get stripped next. That repeatable, symmetric risk over
  whichever islands are currently vulnerable is what makes board position
  matter, not a single move triggering an instant chain reaction.
- Mechanically: `place` and `remove` each touch exactly one line, and a
  line has exactly two endpoint islands — so a single action can only ever
  directly change bridge counts on those two islands. No board-wide sweep
  is needed after a move, just a check of the (at most two) islands whose
  count just changed.

Bridges and tokens are also a limited, shared supply — 25 bridges and 10
tokens per player, in total. Running out limits what you can still play.

## Chance & hidden information

- **Public**: the whole board (every bridge and who owns it), both players'
  placed tokens, the scores, which round it is, remaining bridge/token
  supplies, the 3 face-up cards, and whether the previous turn ended in a
  skip (needed to know if skipping is currently legal).
- **Hidden**: what's in each player's hand, and the order of the face-down
  pile.
- **Random events**: drawing blind from the face-down pile — whether as
  your own draw, or as the automatic refill after someone takes a face-up
  card. Taking a specific face-up card is a visible, deliberate choice, not
  a random event.

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
num_distinct_actions  = 2 * 27 + 5 = 59   # place + remove per line (P=27),
                                          # + draw-blind + 3 face-up picks + skip
```

## Action encoding

`P = 27`. Stable integer scheme:
- `0 .. 26` → `place(bridge_pos = i)`
- `27 .. 53` → `remove(bridge_pos = i - 27)`
- `54` → end turn, draw blind from the face-down pile
- `55 .. 57` → end turn, take face-up slot `j` (`j` in 0..2)
- `58` → end turn, skip the draw

(Exactly how face-up slots are indexed as they get refilled is an
implementation detail to pin down when the engine is built, not a rules
question.)

`bridge_pos` is assigned by sorting all 27 lines alphabetically by their two
island names:

| pos | line | pos | line | pos | line |
|---|---|---|---|---|---|
| 0 | ALOA-BARI | 9 | COCO-KAHU | 18 | GOLA-JOJO |
| 1 | ALOA-DUDA | 10 | DUDA-ELAI | 19 | GOLA-KAHU |
| 2 | ALOA-HUNA | 11 | DUDA-HUNA | 20 | HUNA-IFFI |
| 3 | BARI-COCO | 12 | ELAI-FAAA | 21 | HUNA-LALE |
| 4 | BARI-DUDA | 13 | ELAI-HUNA | 22 | IFFI-JOJO |
| 5 | BARI-ELAI | 14 | ELAI-IFFI | 23 | IFFI-KAHU |
| 6 | BARI-FAAA | 15 | ELAI-JOJO | 24 | IFFI-LALE |
| 7 | COCO-FAAA | 16 | FAAA-GOLA | 25 | JOJO-KAHU |
| 8 | COCO-GOLA | 17 | FAAA-JOJO | 26 | KAHU-LALE |

`legal_actions()` filters these down by: the line is free and you hold a
card naming one of its endpoint islands (`place`); your opponent owns that
bridge and you hold either 2 cards naming one of its endpoint islands, or 1
card naming each endpoint island (`remove`); draw-blind and each currently-
filled face-up slot are always legal; skip is legal only if the opponent's
immediately preceding turn wasn't itself a skip.

## Information-state tensor (for Deep CFR)

Per-bridge owner (3 possibilities × P positions) · per-island control,
degree, and each player's bridge count there · your hand, counted per
island (12 numbers) · the 3 public face-up cards · cards seen/discarded so
far this round · bridges/tokens remaining · which round it is · scores ·
whether you've already played a card this turn · whether the opponent
skipped their last turn (so you know if skipping is legal for you).

## Worked example

Focus on two neighboring islands that share a bridge line: **ELAI** (degree
6, majority 4) and **HUNA** (degree 5, majority 3), connected by
`ELAI-HUNA` (`bridge_pos = 13`).

Board state before the move:
- **ELAI**'s 6 lines: `BARI-ELAI`(5) and `DUDA-ELAI`(10) and `ELAI-FAAA`(12)
  are player 0's; `ELAI-HUNA`(13) is player 1's; `ELAI-IFFI`(14) and
  `ELAI-JOJO`(15) are free. Nobody controls ELAI yet — player 0 has 3 of 6,
  one short of majority.
- **HUNA**'s 5 lines: `ALOA-HUNA`(2) and `ELAI-HUNA`(13) and `HUNA-IFFI`(20)
  are player 1's; `DUDA-HUNA`(11) and `HUNA-LALE`(21) are free. Player 1
  controls HUNA with exactly 3 of 5 (majority).
- Player 0 holds a card naming ELAI (or IFFI) in hand.

At this position, `place(bridge_pos=14)` (`ELAI-IFFI`) is legal for player 0
— the line is free and they hold a card naming one of its endpoints.

Playing it:
1. Player 0's count on ELAI goes from 3 to 4 — a new strict majority. Player
   0 takes ELAI's token.
2. Every player-1 bridge touching ELAI is removed at once — just
   `ELAI-HUNA`(13), player 1's only bridge there. It returns to the supply
   and the line is free again.
3. That removal drops player 1's count on HUNA from 3 to 2 — below HUNA's
   majority of 3. Player 1 loses HUNA's token. Their other two HUNA bridges
   (`ALOA-HUNA`, `HUNA-IFFI`) are untouched, and nothing else is removed.

After the move: ELAI is controlled by player 0 (4 of 6:
`BARI-ELAI`/`DUDA-ELAI`/`ELAI-FAAA`/`ELAI-IFFI`; `ELAI-HUNA` and
`ELAI-JOJO` free). HUNA is uncontrolled (player 1 holds 2 of 5:
`ALOA-HUNA`/`HUNA-IFFI`; `DUDA-HUNA`/`ELAI-HUNA`/`HUNA-LALE` free) — open
for either player to claim on a later turn, per the "reclaiming is
symmetric risk" point above.

## Open questions

*(none — the board graph was traced from the physical board and is listed
in Components & players above.)*

## Checklist

- [x] Every rule cites a source.
- [x] No open questions remain unresolved.
- [x] GameSpec and action encoding are fully specified.
- [x] A worked example is provided.
- [ ] Human verified, at the top.
