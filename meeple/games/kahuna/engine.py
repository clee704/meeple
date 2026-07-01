"""Native Kahuna engine. Rules: `meeple/games/kahuna/RULES.md`.

RULES.md's action encoding lists one `place`/`remove` action per bridge
line, but which specific card(s) a hand spends to pay for it is a real
strategic choice (a different hand and discard-pile composition come out
of it) — not an interchangeable implementation detail. So each `place` and
`remove` action is split by exactly which card(s) it spends: `place` by
which of the line's two endpoint islands the discarded card names;
`remove` by whether it spends 2 cards of one endpoint, 2 of the other, or
1 of each. This expands the action space beyond what RULES.md's Action
encoding section shows; see that section (updated to match) for the
current numbering.

A few engine-level details RULES.md doesn't cover were settled directly
with the human via issue #14, rather than guessed:

- Player 0 moves first (arbitrary/symmetric — but real first-move
  advantage exists and should be accounted for in eval, e.g. by
  alternating who starts across a match).
- Hand limit (5): if your hand is already full when you'd otherwise draw,
  you discard a card face-down first (`discard_facedown`), then draw as
  normal — drawing itself is never blocked. The discard is strictly the
  prelude to that draw: it's only legal while something is drawable, and
  once made, only draw actions are legal until the turn ends. (The
  manual's "one or more" also permits discarding extra cards; the engine
  offers only the single discard needed to get under the limit.)
- Token supply (10 per player) is a physical-component limit only; a
  digital version isn't bound by it, so it's not enforced here.
- Premature end is checked only once scoring_count >= 1 (round 2 or 3).
- Skip is allowed regardless of the no-double-skip rule whenever there's
  truly nothing to draw — this only ever arises in the final "one more
  turn each" phase, where the deck is permanently empty, so it can't be
  exploited to skip repeatedly during normal play.
"""

from dataclasses import dataclass, replace
from functools import cached_property

import torch

from meeple.framework.game import CHANCE, Action, Game, State
from meeple.framework.spec import GameSpec
from meeple.games.kahuna.graph import BRIDGES, ISLAND_BRIDGES, ISLANDS, MAJORITY, NUM_BRIDGES

NUM_ISLANDS = len(ISLANDS)
BRIDGE_SUPPLY = 25
NUM_FACEUP_SLOTS = 3
HAND_LIMIT = 5

# place/remove are split by exactly which card(s) they spend — see module
# docstring. `a`/`b` below always mean BRIDGES[pos][0]/BRIDGES[pos][1].
PLACE_A_BASE = 0
PLACE_B_BASE = NUM_BRIDGES
REMOVE_AA_BASE = 2 * NUM_BRIDGES
REMOVE_BB_BASE = 3 * NUM_BRIDGES
REMOVE_AB_BASE = 4 * NUM_BRIDGES
DRAW_BLIND = 5 * NUM_BRIDGES
FACEUP_BASE = DRAW_BLIND + 1
SKIP = FACEUP_BASE + NUM_FACEUP_SLOTS
DISCARD_BASE = SKIP + 1
NUM_ACTIONS = DISCARD_BASE + NUM_ISLANDS

DECK: tuple[str, ...] = tuple(sorted(ISLANDS * 2))  # 24 cards, 2 per island

_ACTION_NAMES = (
    tuple(f"place({a}-{b} using {a})" for a, b in BRIDGES)
    + tuple(f"place({a}-{b} using {b})" for a, b in BRIDGES)
    + tuple(f"remove({a}-{b} using 2x{a})" for a, b in BRIDGES)
    + tuple(f"remove({a}-{b} using 2x{b})" for a, b in BRIDGES)
    + tuple(f"remove({a}-{b} using {a}+{b})" for a, b in BRIDGES)
    + ("draw_blind",)
    + tuple(f"take_faceup_{j}" for j in range(NUM_FACEUP_SLOTS))
    + ("skip",)
    + tuple(f"discard_facedown({island})" for island in ISLANDS)
)


def _kahuna_spec() -> GameSpec:
    return GameSpec(
        num_players=2,
        perfect_information=False,
        has_chance=True,
        zero_sum=True,
        num_distinct_actions=NUM_ACTIONS,
        action_names=_ACTION_NAMES,
    )


def _remove_first(hand: tuple[str, ...], card: str) -> tuple[str, ...]:
    items = list(hand)
    items.remove(card)
    return tuple(items)


@dataclass(frozen=True)
class KahunaState(State):
    bridges: tuple[int | None, ...]
    hands: tuple[tuple[str, ...], tuple[str, ...]]
    face_up: tuple[str | None, ...]
    pile: tuple[str, ...]
    discard: tuple[str, ...]
    # The acting player. Named `to_move` (not `current_player`) only because
    # the `State` interface already claims that name as a method.
    to_move: int
    pending: tuple[str, ...]
    pending_reason: str
    scores: tuple[float, float]
    scoring_count: int
    previous_turn_was_skip: bool
    final_turns_remaining: int | None
    premature_winner: int | None
    final_round_winner: int | None = None
    # Per-player cards discarded face-down for the hand limit (see RULES.md's
    # Turn structure): these get reshuffled into the pile just like `discard`,
    # but each player sees only their own by identity — the opponent's only
    # by count (see information_state_key/tensor below).
    hidden_discards: tuple[tuple[str, ...], tuple[str, ...]] = ((), ())
    # RULES.md's information-state tensor lists this explicitly; it's
    # public (both players can see cards being played) and resets at
    # the start of each new turn.
    played_card_this_turn: bool = False
    # True between a hand-limit face-down discard and the draw it forces:
    # the discard exists only as the prelude to a draw, so while this is
    # set only draw actions are legal. Public (the discard action itself
    # is visible) and reset when the turn ends.
    discarded_this_turn: bool = False

    # --- derived board queries -------------------------------------------------

    def _bridge_count(self, player: int, island: str) -> int:
        return sum(1 for pos in ISLAND_BRIDGES[island] if self.bridges[pos] == player)

    def _controller(self, island: str) -> int | None:
        for player in (0, 1):
            if self._bridge_count(player, island) >= MAJORITY[island]:
                return player
        return None

    def _controlled_islands(self, player: int) -> int:
        return sum(1 for island in ISLANDS if self._controller(island) == player)

    def _total_bridges(self, player: int) -> int:
        return sum(1 for owner in self.bridges if owner == player)

    def _pile_and_faceup_empty(self) -> bool:
        return len(self.pile) == 0 and all(c is None for c in self.face_up)

    # --- State interface ---------------------------------------------------

    def legal_actions(self) -> list[Action]:
        if self.is_terminal():
            return []
        if self.pending:
            raise RuntimeError("call apply_action with a chance outcome first")
        return list(self._legal_actions)

    @cached_property
    def _legal_actions(self) -> tuple[Action, ...]:
        # Cached on the (immutable) instance: MCTS-style consumers call
        # legal_actions() to pick and apply_action() to validate on the same
        # node, and this generation pass is the engine's most expensive one.
        player = self.to_move
        opponent = 1 - player
        hand = self.hands[player]
        actions: list[Action] = []

        if self.discarded_this_turn:
            # The face-down discard is only ever the prelude to a draw (see
            # module docstring): once it's made, the turn must end with one
            # — no more card plays, no skip.
            if self.pile:
                actions.append(DRAW_BLIND)
            actions.extend(
                FACEUP_BASE + j for j, card in enumerate(self.face_up) if card is not None
            )
            return tuple(actions)

        if self._total_bridges(player) < BRIDGE_SUPPLY:
            for pos, (a, b) in enumerate(BRIDGES):
                if self.bridges[pos] is not None:
                    continue
                if a in hand:
                    actions.append(PLACE_A_BASE + pos)
                if b in hand:
                    actions.append(PLACE_B_BASE + pos)

        for pos, (a, b) in enumerate(BRIDGES):
            if self.bridges[pos] != opponent:
                continue
            if hand.count(a) >= 2:
                actions.append(REMOVE_AA_BASE + pos)
            if hand.count(b) >= 2:
                actions.append(REMOVE_BB_BASE + pos)
            if a in hand and b in hand:
                actions.append(REMOVE_AB_BASE + pos)

        if len(hand) >= HAND_LIMIT:
            # Hand limit: discard face-down first, then draw as normal --
            # drawing itself is never directly blocked (see module docstring).
            # No draw to enable means no discard either: it exists only as
            # the prelude to a draw, never as free hidden hand-thinning.
            if not self._pile_and_faceup_empty():
                for index, island in enumerate(ISLANDS):
                    if island in hand:
                        actions.append(DISCARD_BASE + index)
        else:
            if self.pile:
                actions.append(DRAW_BLIND)
            for j, card in enumerate(self.face_up):
                if card is not None:
                    actions.append(FACEUP_BASE + j)

        # No back-to-back skips — unless there's nothing left to draw, in
        # which case skip is always legal (see module docstring).
        if not self.previous_turn_was_skip or self._pile_and_faceup_empty():
            actions.append(SKIP)

        return tuple(actions)

    def apply_action(self, action: Action) -> "KahunaState":
        if self.pending:
            # Chance legality is just "a card of that island is still in the
            # pile" — checked directly so the hot path never rebuilds the
            # full chance_outcomes() list.
            if not (0 <= action < NUM_ISLANDS) or ISLANDS[action] not in self.pile:
                legal_chance = [outcome for outcome, _prob in self.chance_outcomes()]
                raise ValueError(f"illegal chance action {action!r}; legal: {legal_chance}")
            return self._apply_chance(action)

        legal = self.legal_actions()
        if action not in legal:
            raise ValueError(f"illegal action {action!r}; legal: {legal}")

        if PLACE_A_BASE <= action < PLACE_B_BASE:
            return self._apply_place(action - PLACE_A_BASE, endpoint=0)
        if PLACE_B_BASE <= action < REMOVE_AA_BASE:
            return self._apply_place(action - PLACE_B_BASE, endpoint=1)
        if REMOVE_AA_BASE <= action < REMOVE_BB_BASE:
            return self._apply_remove(action - REMOVE_AA_BASE, cards="aa")
        if REMOVE_BB_BASE <= action < REMOVE_AB_BASE:
            return self._apply_remove(action - REMOVE_BB_BASE, cards="bb")
        if REMOVE_AB_BASE <= action < DRAW_BLIND:
            return self._apply_remove(action - REMOVE_AB_BASE, cards="ab")
        if action == DRAW_BLIND:
            return replace(self, pending=(f"hand{self.to_move}",), pending_reason="turn")
        if FACEUP_BASE <= action < SKIP:
            return self._apply_take_faceup(action - FACEUP_BASE)
        if action == SKIP:
            return self._apply_skip()
        return self._apply_discard_facedown(ISLANDS[action - DISCARD_BASE])

    def is_terminal(self) -> bool:
        if self.premature_winner is not None:
            return True
        return self.scoring_count == 3 and self.final_turns_remaining == 0

    def returns(self) -> list[float]:
        if not self.is_terminal():
            raise RuntimeError("returns() called on a non-terminal state")
        if self.premature_winner is not None:
            return [1.0, -1.0] if self.premature_winner == 0 else [-1.0, 1.0]
        return [self.scores[0] - self.scores[1], self.scores[1] - self.scores[0]]

    def winner(self) -> int | None:
        """RULES.md's Winner tiebreak: total score, then who won the final
        scoring round specifically, then bridge count on the board, else no
        winner. Distinct from `returns()`, which is just the net score
        difference (the zero-sum reward signal) and can be 0 even when this
        resolves a winner via the tiebreak."""
        if not self.is_terminal():
            raise RuntimeError("winner() called on a non-terminal state")
        if self.premature_winner is not None:
            return self.premature_winner
        if self.scores[0] != self.scores[1]:
            return 0 if self.scores[0] > self.scores[1] else 1
        if self.final_round_winner is not None:
            return self.final_round_winner
        b0, b1 = self._total_bridges(0), self._total_bridges(1)
        if b0 != b1:
            return 0 if b0 > b1 else 1
        return None

    def current_player(self) -> int:
        if self.pending:
            return CHANCE
        if self.is_terminal():
            raise RuntimeError("current_player() called on a terminal state")
        return self.to_move

    def chance_outcomes(self) -> list[tuple[Action, float]]:
        if not self.pending:
            return []
        total = len(self.pile)
        counts: dict[str, int] = {}
        for card in self.pile:
            counts[card] = counts.get(card, 0) + 1
        return [(ISLANDS.index(island), count / total) for island, count in counts.items()]

    def information_state_key(self, player: int) -> str:
        return repr(
            (
                self.bridges,
                self.face_up,
                self.discard,
                self.hidden_discards[player],  # you know your own face-down discards...
                len(self.hidden_discards[1 - player]),  # ...but only the count of theirs
                len(self.pile),
                self.to_move,
                self.pending_reason if self.pending else None,
                self.scores,
                self.scoring_count,
                self.previous_turn_was_skip,
                self.final_turns_remaining,
                self.premature_winner,
                self.played_card_this_turn,
                self.discarded_this_turn,
                tuple(sorted(self.hands[player])),
            )
        )

    def information_state_tensor(self, player: int) -> torch.Tensor:
        values: list[float] = []
        for owner in self.bridges:
            relative = 0 if owner is None else (1 if owner == player else 2)
            values.extend(1.0 if relative == k else 0.0 for k in range(3))
        for island in ISLANDS:
            controller = self._controller(island)
            relative = 0 if controller is None else (1 if controller == player else 2)
            values.extend(1.0 if relative == k else 0.0 for k in range(3))
        for island in ISLANDS:
            values.append(float(self.hands[player].count(island)))
        for island in ISLANDS:
            values.append(float(sum(1 for c in self.face_up if c == island)))
        for island in ISLANDS:
            values.append(float(self.discard.count(island)))
        # You see your own face-down discards by identity, the opponent's
        # only by count.
        for island in ISLANDS:
            values.append(float(self.hidden_discards[player].count(island)))
        values.append(float(len(self.hidden_discards[1 - player])))
        values.append(float(len(self.pile)))
        values.append(self.scores[player])
        values.append(self.scores[1 - player])
        values.append(float(self.scoring_count))
        values.append(1.0 if self.previous_turn_was_skip else 0.0)
        values.append(
            float(self.final_turns_remaining) if self.final_turns_remaining is not None else -1.0
        )
        values.append(1.0 if self.played_card_this_turn else 0.0)
        values.append(1.0 if self.discarded_this_turn else 0.0)
        return torch.tensor(values, dtype=torch.float32)

    # --- mutation helpers ----------------------------------------------------

    def _apply_place(self, pos: int, endpoint: int) -> "KahunaState":
        player = self.to_move
        a, b = BRIDGES[pos]
        card = a if endpoint == 0 else b
        hands = list(self.hands)
        hands[player] = _remove_first(hands[player], card)
        bridges = list(self.bridges)
        bridges[pos] = player
        state = replace(
            self,
            bridges=tuple(bridges),
            hands=tuple(hands),
            discard=tuple(sorted(self.discard + (card,))),
            played_card_this_turn=True,
        )
        for island in (a, b):
            state = state._resolve_new_control(island, player)
        return state._check_premature_end()

    def _apply_remove(self, pos: int, cards: str) -> "KahunaState":
        player = self.to_move
        a, b = BRIDGES[pos]
        c1, c2 = {"aa": (a, a), "bb": (b, b), "ab": (a, b)}[cards]
        hands = list(self.hands)
        hand = _remove_first(hands[player], c1)
        hand = _remove_first(hand, c2)
        hands[player] = hand
        bridges = list(self.bridges)
        bridges[pos] = None
        # Losing majority on `a`/`b` here is purely passive — _controller()
        # derives it on demand from bridge counts, so nothing further to do.
        state = replace(
            self,
            bridges=tuple(bridges),
            hands=tuple(hands),
            discard=tuple(sorted(self.discard + (c1, c2))),
            played_card_this_turn=True,
        )
        return state._check_premature_end()

    def _resolve_new_control(self, island: str, player: int) -> "KahunaState":
        if self._bridge_count(player, island) < MAJORITY[island]:
            return self
        opponent = 1 - player
        state = self
        for pos in ISLAND_BRIDGES[island]:
            if state.bridges[pos] == opponent:
                bridges = list(state.bridges)
                bridges[pos] = None
                state = replace(state, bridges=tuple(bridges))
        return state

    def _check_premature_end(self) -> "KahunaState":
        if self.scoring_count < 1:
            return self
        # RULES.md: "if a player has zero bridges, the game ends and the
        # *other* player wins" -- implicitly asymmetric. If both players
        # have zero bridges (a genuinely empty board), there's no "other
        # player" for the rule to hand a win to, so this doesn't fire.
        zero_bridge_players = [p for p in (0, 1) if self._total_bridges(p) == 0]
        if len(zero_bridge_players) == 1:
            return replace(self, premature_winner=1 - zero_bridge_players[0])
        return self

    def _apply_take_faceup(self, slot: int) -> "KahunaState":
        player = self.to_move
        card = self.face_up[slot]
        hands = list(self.hands)
        hands[player] = self.hands[player] + (card,)
        face_up = list(self.face_up)
        face_up[slot] = None
        state = replace(self, hands=tuple(hands), face_up=tuple(face_up))
        if state.pile:
            return replace(state, pending=(f"faceup{slot}",), pending_reason="turn")
        return state._finish_turn(just_drew=True)

    def _apply_skip(self) -> "KahunaState":
        return self._finish_turn(was_skip=True)

    def _apply_discard_facedown(self, island: str) -> "KahunaState":
        player = self.to_move
        hands = list(self.hands)
        hands[player] = _remove_first(hands[player], island)
        hidden = list(self.hidden_discards)
        hidden[player] = tuple(sorted(hidden[player] + (island,)))
        return replace(
            self,
            hands=tuple(hands),
            hidden_discards=tuple(hidden),
            discarded_this_turn=True,
        )

    def _finish_turn(self, was_skip: bool = False, just_drew: bool = False) -> "KahunaState":
        state = replace(self, previous_turn_was_skip=was_skip)
        just_entered_final_phase = False
        # Only check for a *new* depletion right after an action that itself
        # drew the last card (a resolved blind draw, or a face-up pick with
        # no pile left to refill from) — never on a skip, which touches
        # neither pile nor face-up. Without this, an already-empty pile
        # would re-trigger scoring on every subsequent turn-ending action,
        # even ones (like skip) that changed nothing.
        if just_drew and state.final_turns_remaining is None and state._pile_and_faceup_empty():
            state = state._trigger_scoring()
            just_entered_final_phase = state.final_turns_remaining is not None
        # Re-check premature end on every turn-ending action (using
        # scoring_count as of *this* point, after any scoring cascade above)
        # not just right after a place/remove: a zero-bridge condition must
        # not sit undetected once round 2+ begins, even if the turn that
        # crosses that boundary is a plain draw or skip that never touches
        # the board itself.
        state = state._check_premature_end()
        if state.is_terminal():
            return state
        # The turn that triggers the final phase doesn't itself count as one
        # of the "one more turn each" — that countdown starts on the *next*
        # turn (RULES.md: each player takes one more turn *after* this one).
        if state.final_turns_remaining is not None and not just_entered_final_phase:
            state = replace(state, final_turns_remaining=state.final_turns_remaining - 1)
            if state.final_turns_remaining == 0:
                return state._final_scoring()
        return replace(
            state,
            to_move=1 - state.to_move,
            played_card_this_turn=False,
            discarded_this_turn=False,
        )

    def _trigger_scoring(self) -> "KahunaState":
        scoring_count = self.scoring_count + 1
        if scoring_count == 3:
            return replace(self, scoring_count=scoring_count, final_turns_remaining=2)

        p0, p1 = self._controlled_islands(0), self._controlled_islands(1)
        points = 1.0 if scoring_count == 1 else 2.0
        scores = list(self.scores)
        if p0 > p1:
            scores[0] += points
        elif p1 > p0:
            scores[1] += points

        # Both the openly-discarded and face-down-discarded cards go back
        # into the pile — the face-down/hidden distinction only matters for
        # what's visible *before* a reshuffle, not for what gets reshuffled.
        new_pile = tuple(sorted(self.discard + self.hidden_discards[0] + self.hidden_discards[1]))
        num_to_deal = min(NUM_FACEUP_SLOTS, len(new_pile))
        state = replace(
            self,
            scores=tuple(scores),
            scoring_count=scoring_count,
            pile=new_pile,
            discard=(),
            hidden_discards=((), ()),
            face_up=(None, None, None),
            pending=tuple(f"faceup{j}" for j in range(num_to_deal)),
            pending_reason="reshuffle",
        )
        if num_to_deal == 0:
            # Degenerate: nothing was discarded since the last scoring, so
            # the freshly-reshuffled pile is already empty too. There's no
            # future draw event left to detect this round's depletion, so
            # advance straight to the next scoring rather than stalling
            # forever with nothing left to draw.
            return state._trigger_scoring()
        return state

    def _final_scoring(self) -> "KahunaState":
        p0, p1 = self._controlled_islands(0), self._controlled_islands(1)
        scores = list(self.scores)
        final_round_winner = None
        if p0 > p1:
            scores[0] += p0 - p1
            final_round_winner = 0
        elif p1 > p0:
            scores[1] += p1 - p0
            final_round_winner = 1
        return replace(self, scores=tuple(scores), final_round_winner=final_round_winner)

    def _apply_chance(self, action: Action) -> "KahunaState":
        island = ISLANDS[action]
        destination, *rest = self.pending
        pile = list(self.pile)
        pile.remove(island)
        state = replace(self, pile=tuple(pile), pending=tuple(rest))

        if destination.startswith("hand"):
            player = int(destination[len("hand") :])
            hands = list(state.hands)
            hands[player] = hands[player] + (island,)
            state = replace(state, hands=tuple(hands))
        else:
            slot = int(destination[len("faceup") :])
            face_up = list(state.face_up)
            face_up[slot] = island
            state = replace(state, face_up=tuple(face_up))

        if state.pending:
            return state

        if state.pending_reason == "turn":
            return state._finish_turn(just_drew=True)
        return state


class KahunaGame(Game):
    def new_initial_state(self) -> KahunaState:
        deal_order = tuple(f"hand{p}" for p in (0, 0, 0, 1, 1, 1)) + (
            "faceup0",
            "faceup1",
            "faceup2",
        )
        return KahunaState(
            bridges=(None,) * NUM_BRIDGES,
            hands=((), ()),
            face_up=(None, None, None),
            pile=DECK,
            discard=(),
            to_move=0,  # player 0 moves first (see module docstring)
            pending=deal_order,
            pending_reason="setup",
            scores=(0.0, 0.0),
            scoring_count=0,
            previous_turn_was_skip=False,
            final_turns_remaining=None,
            premature_winner=None,
        )

    def spec(self) -> GameSpec:
        return _kahuna_spec()
