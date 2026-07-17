"""Tests for the GameView SPI plumbing: view registration and the default
`result` logic. Per-game conformance (observations serialize, metadata covers
every legal action, privacy) lives with each game's view tests."""

import random

import pytest
import torch

from meeple.framework import registry
from meeple.framework.game import Action, Game, State
from meeple.framework.spec import GameSpec
from meeple.framework.view import GameView


class _StubState(State):
    def __init__(self, returns: list[float]):
        self._returns = returns

    def legal_actions(self) -> list[Action]:
        return []

    def apply_action(self, action: Action) -> "State":
        raise NotImplementedError

    def is_terminal(self) -> bool:
        return True

    def returns(self) -> list[float]:
        return self._returns

    def current_player(self) -> int:
        return -2

    def chance_outcomes(self) -> list[tuple[Action, float]]:
        return []

    def information_state_key(self, player: int) -> str:
        return "terminal"

    def information_state_tensor(self, player: int) -> torch.Tensor:
        return torch.zeros(1)

    def resample_from_infostate(self, player: int, rng: random.Random) -> State:
        return self


class _StubGame(Game):
    def new_initial_state(self) -> State:
        return _StubState([0.0, 0.0])

    def spec(self) -> GameSpec:
        return GameSpec(
            num_players=2,
            perfect_information=True,
            has_chance=False,
            zero_sum=True,
            num_distinct_actions=1,
            action_names=("noop",),
        )


class _StubView(GameView):
    def observation(self, state: State, viewer: int) -> dict:
        return {}

    def action_metadata(self, action: Action) -> dict:
        return {"kind": "noop"}


def test_register_view_requires_registered_game():
    with pytest.raises(ValueError, match="unregistered game"):
        registry.register_view("no-such-game", _StubView)


def test_register_view_roundtrip_and_duplicate():
    registry.register("stub-view-game", _StubGame)
    try:
        registry.register_view("stub-view-game", _StubView)
        assert "stub-view-game" in registry.games_with_views()
        assert isinstance(registry.make_view("stub-view-game"), _StubView)
        with pytest.raises(ValueError, match="already registered"):
            registry.register_view("stub-view-game", _StubView)
    finally:
        del registry._REGISTRY["stub-view-game"]
        del registry._VIEW_REGISTRY["stub-view-game"]


def test_make_view_unknown_game_raises_key_error():
    with pytest.raises(KeyError, match="no view for game"):
        registry.make_view("does-not-exist")


@pytest.mark.parametrize(
    ("returns", "winner"),
    [([3.0, 1.0], 0), ([-1.0, 1.0], 1), ([2.0, 2.0], None)],
)
def test_default_result_declares_argmax_winner_or_draw(returns, winner):
    result = _StubView().result(_StubState(returns))
    assert result == {"scores": returns, "winner": winner}


def test_default_describe_action_and_game_meta():
    view = _StubView()
    state = _StubState([0.0, 0.0])
    assert view.describe_action(0, viewer=1, actor=0, state=state) == view.action_metadata(0)
    assert view.game_meta() == {}
