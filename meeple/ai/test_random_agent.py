"""Exercises random_agent against a minimal inline State rather than
`games.kuhn` — code under `meeple.ai` should depend only on `meeple.framework`,
never on a specific game's package, and that includes its own tests."""

import random

import torch

from meeple.ai.random_agent import play_to_terminal, select_action
from meeple.framework.game import CHANCE, Action, State


class _CoinFlipState(State):
    """Chance flips a coin (0 or 1); the acting player then picks 0 or 1 and
    wins iff it matches the flip."""

    def __init__(self, flip: int | None = None, choice: int | None = None):
        self._flip = flip
        self._choice = choice

    def legal_actions(self) -> list[Action]:
        return [] if self.is_terminal() else [0, 1]

    def apply_action(self, action: Action) -> "_CoinFlipState":
        if self._flip is None:
            return _CoinFlipState(flip=action)
        return _CoinFlipState(flip=self._flip, choice=action)

    def is_terminal(self) -> bool:
        return self._choice is not None

    def returns(self) -> list[float]:
        win = 1.0 if self._choice == self._flip else -1.0
        return [win]

    def current_player(self) -> int:
        return CHANCE if self._flip is None else 0

    def chance_outcomes(self) -> list[tuple[Action, float]]:
        return [] if self._flip is not None else [(0, 0.5), (1, 0.5)]

    def information_state_key(self, player: int) -> str:
        return "root"

    def information_state_tensor(self, player: int) -> torch.Tensor:
        return torch.zeros(1)


def test_select_action_picks_a_legal_action():
    state = _CoinFlipState(flip=0)
    rng = random.Random(0)
    assert select_action(state, rng) in state.legal_actions()


def test_play_to_terminal_resolves_chance_and_reaches_terminal():
    final = play_to_terminal(_CoinFlipState(), random.Random(0))
    assert final.is_terminal()
    assert final.returns()[0] in (1.0, -1.0)
