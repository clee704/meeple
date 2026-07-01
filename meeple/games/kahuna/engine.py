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
  you discard face-down card(s) first (`discard_facedown`), then draw as
  normal — drawing itself is never blocked.
- Token supply (10 per player) is a physical-component limit only; a
  digital version isn't bound by it, so it's not enforced here.
- Premature end is checked only once scoring_count >= 1 (round 2 or 3).
- Skip is allowed regardless of the no-double-skip rule whenever there's
  truly nothing to draw — this only ever arises in the final "one more
  turn each" phase, where the deck is permanently empty, so it can't be
  exploited to skip repeatedly during normal play.
"""

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


class KahunaState(State):
    def __init__(
        self,
        bridges: tuple[int | None, ...],
        hands: tuple[tuple[str, ...], tuple[str, ...]],
        face_up: tuple[str | None, ...],
        pile: tuple[str, ...],
        discard: tuple[str, ...],
        current_player: int,
        pending: tuple[str, ...],
        pending_reason: str,
        scores: tuple[float, float],
        scoring_count: int,
        previous_turn_was_skip: bool,
        final_turns_remaining: int | None,
        premature_winner: int | None,
        final_round_winner: int | None = None,
        discard_hidden: tuple[str, ...] = (),
        played_card_this_turn: bool = False,
    ):
        self._bridges = bridges
        self._hands = hands
        self._face_up = face_up
        self._pile = pile
        self._discard = discard
        # Cards discarded face-down for the hand limit (see RULES.md's Turn
        # structure): these get reshuffled into the pile just like `discard`,
        # but their identity must stay hidden from the opponent's
        # information state (see information_state_key/tensor below).
        self._discard_hidden = discard_hidden
        # RULES.md's information-state tensor lists this explicitly; it's
        # public (both players can see cards being played) and resets at
        # the start of each new turn.
        self._played_card_this_turn = played_card_this_turn
        self._current_player = current_player
        self._pending = pending
        self._pending_reason = pending_reason
        self._scores = scores
        self._scoring_count = scoring_count
        self._previous_turn_was_skip = previous_turn_was_skip
        self._final_turns_remaining = final_turns_remaining
        self._premature_winner = premature_winner
        self._final_round_winner = final_round_winner

    # --- derived board queries -------------------------------------------------

    def _bridge_count(self, player: int, island: str) -> int:
        return sum(1 for pos in ISLAND_BRIDGES[island] if self._bridges[pos] == player)

    def _controller(self, island: str) -> int | None:
        for player in (0, 1):
            if self._bridge_count(player, island) >= MAJORITY[island]:
                return player
        return None

    def _controlled_islands(self, player: int) -> int:
        return sum(1 for island in ISLANDS if self._controller(island) == player)

    def _total_bridges(self, player: int) -> int:
        return sum(1 for owner in self._bridges if owner == player)

    def _pile_and_faceup_empty(self) -> bool:
        return len(self._pile) == 0 and all(c is None for c in self._face_up)

    # --- State interface ---------------------------------------------------

    def legal_actions(self) -> list[Action]:
        if self.is_terminal():
            return []
        if self._pending:
            raise RuntimeError("call apply_action with a chance outcome first")

        player = self._current_player
        opponent = 1 - player
        hand = self._hands[player]
        actions: list[Action] = []

        if self._total_bridges(player) < BRIDGE_SUPPLY:
            for pos, (a, b) in enumerate(BRIDGES):
                if self._bridges[pos] is not None:
                    continue
                if a in hand:
                    actions.append(PLACE_A_BASE + pos)
                if b in hand:
                    actions.append(PLACE_B_BASE + pos)

        for pos, (a, b) in enumerate(BRIDGES):
            if self._bridges[pos] != opponent:
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
            for island in ISLANDS:
                if island in hand:
                    actions.append(DISCARD_BASE + ISLANDS.index(island))
        else:
            if self._pile:
                actions.append(DRAW_BLIND)
            for j, card in enumerate(self._face_up):
                if card is not None:
                    actions.append(FACEUP_BASE + j)

        nothing_to_draw = not self._pile and all(c is None for c in self._face_up)
        skip_allowed = (
            not self._previous_turn_was_skip
            or self._final_turns_remaining is not None
            or nothing_to_draw
        )
        if skip_allowed:
            actions.append(SKIP)

        return actions

    def apply_action(self, action: Action) -> "KahunaState":
        if self._pending:
            legal_chance = [outcome for outcome, _prob in self.chance_outcomes()]
            if action not in legal_chance:
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
            return self._replace(pending=(f"hand{self._current_player}",), pending_reason="turn")
        if FACEUP_BASE <= action < SKIP:
            return self._apply_take_faceup(action - FACEUP_BASE)
        if action == SKIP:
            return self._apply_skip()
        return self._apply_discard_facedown(ISLANDS[action - DISCARD_BASE])

    def is_terminal(self) -> bool:
        if self._premature_winner is not None:
            return True
        return self._scoring_count == 3 and self._final_turns_remaining == 0

    def returns(self) -> list[float]:
        if not self.is_terminal():
            raise RuntimeError("returns() called on a non-terminal state")
        if self._premature_winner is not None:
            return [1.0, -1.0] if self._premature_winner == 0 else [-1.0, 1.0]
        return [self._scores[0] - self._scores[1], self._scores[1] - self._scores[0]]

    def winner(self) -> int | None:
        """RULES.md's Winner tiebreak: total score, then who won the final
        scoring round specifically, then bridge count on the board, else no
        winner. Distinct from `returns()`, which is just the net score
        difference (the zero-sum reward signal) and can be 0 even when this
        resolves a winner via the tiebreak."""
        if not self.is_terminal():
            raise RuntimeError("winner() called on a non-terminal state")
        if self._premature_winner is not None:
            return self._premature_winner
        if self._scores[0] != self._scores[1]:
            return 0 if self._scores[0] > self._scores[1] else 1
        if self._final_round_winner is not None:
            return self._final_round_winner
        b0, b1 = self._total_bridges(0), self._total_bridges(1)
        if b0 != b1:
            return 0 if b0 > b1 else 1
        return None

    def current_player(self) -> int:
        if self._pending:
            return CHANCE
        if self.is_terminal():
            raise RuntimeError("current_player() called on a terminal state")
        return self._current_player

    def chance_outcomes(self) -> list[tuple[Action, float]]:
        if not self._pending:
            return []
        total = len(self._pile)
        counts: dict[str, int] = {}
        for card in self._pile:
            counts[card] = counts.get(card, 0) + 1
        return [(ISLANDS.index(island), count / total) for island, count in counts.items()]

    def information_state_key(self, player: int) -> str:
        return repr(
            (
                self._bridges,
                self._face_up,
                self._discard,
                len(self._discard_hidden),  # count is public; identities aren't
                len(self._pile),
                self._current_player,
                self._pending_reason if self._pending else None,
                self._scores,
                self._scoring_count,
                self._previous_turn_was_skip,
                self._final_turns_remaining,
                self._premature_winner,
                self._played_card_this_turn,
                tuple(sorted(self._hands[player])),
            )
        )

    def information_state_tensor(self, player: int) -> torch.Tensor:
        values: list[float] = []
        for owner in self._bridges:
            relative = 0 if owner is None else (1 if owner == player else 2)
            values.extend(1.0 if relative == k else 0.0 for k in range(3))
        for island in ISLANDS:
            controller = self._controller(island)
            relative = 0 if controller is None else (1 if controller == player else 2)
            values.extend(1.0 if relative == k else 0.0 for k in range(3))
        for island in ISLANDS:
            values.append(float(self._hands[player].count(island)))
        for island in ISLANDS:
            values.append(float(sum(1 for c in self._face_up if c == island)))
        for island in ISLANDS:
            values.append(float(self._discard.count(island)))
        values.append(float(len(self._discard_hidden)))  # count is public; identities aren't
        values.append(float(len(self._pile)))
        values.append(self._scores[player])
        values.append(self._scores[1 - player])
        values.append(float(self._scoring_count))
        values.append(1.0 if self._previous_turn_was_skip else 0.0)
        values.append(
            float(self._final_turns_remaining) if self._final_turns_remaining is not None else -1.0
        )
        values.append(1.0 if self._played_card_this_turn else 0.0)
        return torch.tensor(values, dtype=torch.float32)

    # --- mutation helpers ----------------------------------------------------

    def _replace(self, **overrides) -> "KahunaState":
        fields = dict(
            bridges=self._bridges,
            hands=self._hands,
            face_up=self._face_up,
            pile=self._pile,
            discard=self._discard,
            discard_hidden=self._discard_hidden,
            current_player=self._current_player,
            pending=self._pending,
            pending_reason=self._pending_reason,
            scores=self._scores,
            scoring_count=self._scoring_count,
            previous_turn_was_skip=self._previous_turn_was_skip,
            final_turns_remaining=self._final_turns_remaining,
            premature_winner=self._premature_winner,
            final_round_winner=self._final_round_winner,
            played_card_this_turn=self._played_card_this_turn,
        )
        fields.update(overrides)
        return KahunaState(**fields)

    def _apply_place(self, pos: int, endpoint: int) -> "KahunaState":
        player = self._current_player
        a, b = BRIDGES[pos]
        card = a if endpoint == 0 else b
        hands = list(self._hands)
        hands[player] = _remove_first(hands[player], card)
        bridges = list(self._bridges)
        bridges[pos] = player
        state = self._replace(
            bridges=tuple(bridges),
            hands=tuple(hands),
            discard=tuple(sorted(self._discard + (card,))),
            played_card_this_turn=True,
        )
        for island in (a, b):
            state = state._resolve_new_control(island, player)
        return state._check_premature_end()

    def _apply_remove(self, pos: int, cards: str) -> "KahunaState":
        player = self._current_player
        a, b = BRIDGES[pos]
        c1, c2 = {"aa": (a, a), "bb": (b, b), "ab": (a, b)}[cards]
        hands = list(self._hands)
        hand = _remove_first(hands[player], c1)
        hand = _remove_first(hand, c2)
        hands[player] = hand
        bridges = list(self._bridges)
        bridges[pos] = None
        # Losing majority on `a`/`b` here is purely passive — _controller()
        # derives it on demand from bridge counts, so nothing further to do.
        state = self._replace(
            bridges=tuple(bridges),
            hands=tuple(hands),
            discard=tuple(sorted(self._discard + (c1, c2))),
            played_card_this_turn=True,
        )
        return state._check_premature_end()

    def _resolve_new_control(self, island: str, player: int) -> "KahunaState":
        if self._bridge_count(player, island) < MAJORITY[island]:
            return self
        opponent = 1 - player
        state = self
        for pos in ISLAND_BRIDGES[island]:
            if state._bridges[pos] == opponent:
                bridges = list(state._bridges)
                bridges[pos] = None
                state = state._replace(bridges=tuple(bridges))
        return state

    def _check_premature_end(self) -> "KahunaState":
        if self._scoring_count < 1:
            return self
        # RULES.md: "if a player has zero bridges, the game ends and the
        # *other* player wins" -- implicitly asymmetric. If both players
        # have zero bridges (a genuinely empty board), there's no "other
        # player" for the rule to hand a win to, so this doesn't fire.
        zero_bridge_players = [p for p in (0, 1) if self._total_bridges(p) == 0]
        if len(zero_bridge_players) == 1:
            return self._replace(premature_winner=1 - zero_bridge_players[0])
        return self

    def _apply_take_faceup(self, slot: int) -> "KahunaState":
        player = self._current_player
        card = self._face_up[slot]
        hands = list(self._hands)
        hands[player] = self._hands[player] + (card,)
        face_up = list(self._face_up)
        face_up[slot] = None
        state = self._replace(hands=tuple(hands), face_up=tuple(face_up))
        if state._pile:
            return state._replace(pending=(f"faceup{slot}",), pending_reason="turn")
        return state._finish_turn(just_drew=True)

    def _apply_skip(self) -> "KahunaState":
        return self._finish_turn(was_skip=True)

    def _apply_discard_facedown(self, island: str) -> "KahunaState":
        player = self._current_player
        hands = list(self._hands)
        hands[player] = _remove_first(hands[player], island)
        return self._replace(
            hands=tuple(hands),
            discard_hidden=tuple(sorted(self._discard_hidden + (island,))),
        )

    def _finish_turn(self, was_skip: bool = False, just_drew: bool = False) -> "KahunaState":
        state = self._replace(previous_turn_was_skip=was_skip)
        just_entered_final_phase = False
        # Only check for a *new* depletion right after an action that itself
        # drew the last card (a resolved blind draw, or a face-up pick with
        # no pile left to refill from) — never on a skip, which touches
        # neither pile nor face-up. Without this, an already-empty pile
        # would re-trigger scoring on every subsequent turn-ending action,
        # even ones (like skip) that changed nothing.
        if just_drew and state._final_turns_remaining is None and state._pile_and_faceup_empty():
            state = state._trigger_scoring()
            just_entered_final_phase = state._final_turns_remaining is not None
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
        if state._final_turns_remaining is not None and not just_entered_final_phase:
            state = state._replace(final_turns_remaining=state._final_turns_remaining - 1)
            if state._final_turns_remaining == 0:
                return state._final_scoring()
        return state._replace(current_player=1 - state._current_player, played_card_this_turn=False)

    def _trigger_scoring(self) -> "KahunaState":
        scoring_count = self._scoring_count + 1
        if scoring_count == 3:
            return self._replace(scoring_count=scoring_count, final_turns_remaining=2)

        p0, p1 = self._controlled_islands(0), self._controlled_islands(1)
        points = 1.0 if scoring_count == 1 else 2.0
        scores = list(self._scores)
        if p0 > p1:
            scores[0] += points
        elif p1 > p0:
            scores[1] += points

        # Both the openly-discarded and face-down-discarded cards go back
        # into the pile — the face-down/hidden distinction only matters for
        # what's visible *before* a reshuffle, not for what gets reshuffled.
        new_pile = tuple(sorted(self._discard + self._discard_hidden))
        num_to_deal = min(NUM_FACEUP_SLOTS, len(new_pile))
        state = self._replace(
            scores=tuple(scores),
            scoring_count=scoring_count,
            pile=new_pile,
            discard=(),
            discard_hidden=(),
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
        scores = list(self._scores)
        final_round_winner = None
        if p0 > p1:
            scores[0] += p0 - p1
            final_round_winner = 0
        elif p1 > p0:
            scores[1] += p1 - p0
            final_round_winner = 1
        return self._replace(scores=tuple(scores), final_round_winner=final_round_winner)

    def _apply_chance(self, action: Action) -> "KahunaState":
        island = ISLANDS[action]
        destination, *rest = self._pending
        pile = list(self._pile)
        pile.remove(island)
        state = self._replace(pile=tuple(pile), pending=tuple(rest))

        if destination.startswith("hand"):
            player = int(destination[len("hand") :])
            hands = list(state._hands)
            hands[player] = hands[player] + (island,)
            state = state._replace(hands=tuple(hands))
        else:
            slot = int(destination[len("faceup") :])
            face_up = list(state._face_up)
            face_up[slot] = island
            state = state._replace(face_up=tuple(face_up))

        if state._pending:
            return state

        if state._pending_reason == "turn":
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
            current_player=0,  # player 0 moves first (see module docstring)
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
