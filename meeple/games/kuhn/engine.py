"""Native Kuhn poker engine — exercises the `Game`/`State` interface with zero
OpenSpiel dependency. Rules: `meeple/games/kuhn/RULES.md`."""

import random
from itertools import permutations

import torch

from meeple.framework.game import CHANCE, Action, Game, State
from meeple.framework.spec import GameSpec

PASS: Action = 0
BET: Action = 1
NUM_CARDS = 3  # J, Q, K
_DEALS = list(permutations(range(NUM_CARDS), 2))  # 6 equally likely (p0_card, p1_card)


def _kuhn_spec() -> GameSpec:
    return GameSpec(
        num_players=2,
        perfect_information=False,
        has_chance=True,
        zero_sum=True,
        num_distinct_actions=2,
        action_names=("pass", "bet"),
    )


class KuhnState(State):
    def __init__(self, cards: tuple[int, int] | None = None, history: str = ""):
        self._cards = cards  # None until the chance node resolves the deal
        self._history = history

    def legal_actions(self) -> list[Action]:
        if self.is_terminal():
            return []
        if self._cards is None:
            raise RuntimeError("call apply_action with a chance outcome first")
        return [PASS, BET]

    def apply_action(self, action: Action) -> "KuhnState":
        if self._cards is None:
            return KuhnState(cards=_DEALS[action], history="")
        if action not in (PASS, BET):
            raise ValueError(f"illegal action {action!r}; legal: {self.legal_actions()}")
        symbol = "p" if action == PASS else "b"
        return KuhnState(cards=self._cards, history=self._history + symbol)

    def is_terminal(self) -> bool:
        h = self._history
        return h in ("pp", "bp", "bb", "pbp", "pbb")

    def returns(self) -> list[float]:
        if not self.is_terminal():
            raise RuntimeError("returns() called on a non-terminal state")
        h = self._history
        p0_card, p1_card = self._cards
        higher_is_p0 = p0_card > p1_card

        if h == "bp":  # player 0 bet, player 1 folded
            return [1.0, -1.0]
        if h == "pbp":  # player 1 bet, player 0 folded
            return [-1.0, 1.0]
        # Showdown: "pp" (1-chip pot each) or "bb"/"pbb" (2-chip pot each)
        win = 1.0 if h == "pp" else 2.0
        return [win, -win] if higher_is_p0 else [-win, win]

    def current_player(self) -> int:
        if self._cards is None:
            return CHANCE
        if self.is_terminal():
            raise RuntimeError("current_player() called on a terminal state")
        return len(self._history) % 2

    def chance_outcomes(self) -> list[tuple[Action, float]]:
        if self._cards is not None:
            return []
        p = 1.0 / len(_DEALS)
        return [(i, p) for i in range(len(_DEALS))]

    def information_state_key(self, player: int) -> str:
        card = self._cards[player]
        return f"{card}:{self._history}"

    def resample_from_infostate(self, player: int, rng: random.Random) -> "KuhnState":
        if self._cards is None:
            return self  # nothing dealt yet, so nothing is hidden from anyone
        # `player` knows their own card and the betting history; the only
        # hidden information is the opponent's card, uniform over the rest.
        own = self._cards[player]
        other = rng.choice([card for card in range(NUM_CARDS) if card != own])
        cards = (own, other) if player == 0 else (other, own)
        return KuhnState(cards=cards, history=self._history)

    def information_state_tensor(self, player: int) -> torch.Tensor:
        # one-hot card (3) + one-hot history (length up to 3, 2 symbols) -> length 9
        card = self._cards[player]
        card_oh = [1.0 if i == card else 0.0 for i in range(NUM_CARDS)]
        history_oh = [0.0] * 6
        for i, ch in enumerate(self._history):
            history_oh[2 * i + (0 if ch == "p" else 1)] = 1.0
        return torch.tensor(card_oh + history_oh, dtype=torch.float32)


class KuhnGame(Game):
    def new_initial_state(self) -> KuhnState:
        return KuhnState()

    def spec(self) -> GameSpec:
        return _kuhn_spec()
