"""Exercises chance resolution against a minimal inline State (framework
tests never depend on a specific game's package)."""

import random

import torch

from meeple.framework.chance import resolve_chance, sample_chance
from meeple.framework.game import CHANCE, Action, State


class _TwoFlipState(State):
    """Two consecutive biased coin flips (90% heads), then player 0 acts."""

    def __init__(self, flips: tuple[int, ...] = ()):
        self._flips = flips

    def legal_actions(self) -> list[Action]:
        return [0] if len(self._flips) == 2 else []

    def apply_action(self, action: Action) -> "_TwoFlipState":
        return _TwoFlipState(self._flips + (action,))

    def is_terminal(self) -> bool:
        return len(self._flips) == 3

    def returns(self) -> list[float]:
        return [0.0]

    def current_player(self) -> int:
        return CHANCE if len(self._flips) < 2 else 0

    def chance_outcomes(self) -> list[tuple[Action, float]]:
        return [(1, 0.9), (0, 0.1)]

    def information_state_key(self, player: int) -> str:
        return str(self._flips)

    def information_state_tensor(self, player: int) -> torch.Tensor:
        return torch.zeros(1)


def test_sample_chance_follows_the_distribution():
    rng = random.Random(0)
    state = _TwoFlipState()
    heads = sum(sample_chance(state, rng) for _ in range(1000))
    assert 850 < heads < 950


def test_resolve_chance_stops_at_the_first_decision_node():
    state = resolve_chance(_TwoFlipState(), random.Random(0))
    assert state.current_player() == 0
    assert not state.is_terminal()
    assert state.legal_actions() == [0]


def test_resolve_chance_is_a_no_op_at_a_decision_node():
    state = _TwoFlipState((1, 1))
    assert resolve_chance(state, random.Random(0)) is state
