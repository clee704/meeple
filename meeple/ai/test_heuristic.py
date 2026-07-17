"""Exercises HeuristicAgent against a minimal inline State (code under
`meeple.ai` depends only on `meeple.framework`, never on a specific game's
package, and that includes its own tests)."""

import random

import torch

from meeple.ai.heuristic import HeuristicAgent
from meeple.framework.game import Action, State


class _PickState(State):
    """One decision by player 0: pick a number; the child remembers it."""

    def __init__(self, pick: int | None = None):
        self.pick = pick

    def legal_actions(self) -> list[Action]:
        return [] if self.is_terminal() else [0, 1, 2, 3]

    def apply_action(self, action: Action) -> "_PickState":
        return _PickState(pick=action)

    def is_terminal(self) -> bool:
        return self.pick is not None

    def returns(self) -> list[float]:
        return [0.0]

    def current_player(self) -> int:
        return 0

    def chance_outcomes(self) -> list[tuple[Action, float]]:
        return []

    def information_state_key(self, player: int) -> str:
        return str(self.pick)

    def information_state_tensor(self, player: int) -> torch.Tensor:
        return torch.zeros(1)

    def resample_from_infostate(self, player: int, rng: random.Random) -> State:
        return self


def test_picks_the_action_whose_child_evaluates_highest():
    calls: list[tuple[int, int]] = []

    def evaluator(state: _PickState, player: int) -> float:
        calls.append((state.pick, player))
        return {0: 1.0, 1: 5.0, 2: 3.0, 3: 0.0}[state.pick]

    action = HeuristicAgent(evaluator).select_action(_PickState(), random.Random(0))
    assert action == 1
    # The evaluator sees every child once, from the acting player's seat.
    assert calls == [(0, 0), (1, 0), (2, 0), (3, 0)]


def test_ties_break_by_rng_and_replay_under_a_fixed_seed():
    def evaluator(state: _PickState, player: int) -> float:
        return 1.0 if state.pick in (1, 2) else 0.0

    agent = HeuristicAgent(evaluator)
    picks = {agent.select_action(_PickState(), random.Random(seed)) for seed in range(20)}
    assert picks == {1, 2}  # only best-valued actions, both reachable
    assert [agent.select_action(_PickState(), random.Random(7)) for _ in range(3)] == [
        agent.select_action(_PickState(), random.Random(7))
    ] * 3
