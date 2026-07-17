import pytest

from meeple.framework import registry
from meeple.framework.game import Game
from meeple.framework.spec import GameSpec


class _DummyGame(Game):
    def new_initial_state(self):
        raise NotImplementedError

    def spec(self) -> GameSpec:
        return GameSpec(
            num_players=2,
            perfect_information=True,
            has_chance=False,
            zero_sum=True,
            num_distinct_actions=1,
            action_names=("noop",),
        )


def test_register_and_make_roundtrip():
    registry.register("dummy-roundtrip", _DummyGame)
    try:
        assert "dummy-roundtrip" in registry.registered_games()
        assert isinstance(registry.make("dummy-roundtrip"), _DummyGame)
    finally:
        del registry._REGISTRY["dummy-roundtrip"]


def test_register_duplicate_raises():
    registry.register("dummy-dup", _DummyGame)
    try:
        with pytest.raises(ValueError, match="already registered"):
            registry.register("dummy-dup", _DummyGame)
    finally:
        del registry._REGISTRY["dummy-dup"]


def test_make_unknown_game_raises_key_error():
    with pytest.raises(KeyError, match="unknown game"):
        registry.make("does-not-exist")


def test_kuhn_is_registered_via_games_package_import():
    import meeple.games  # noqa: F401

    assert "kuhn" in registry.registered_games()


def _zero_evaluator(state, player: int) -> float:
    return 0.0


def test_register_and_make_evaluator_roundtrip():
    registry.register("dummy-eval", _DummyGame)
    registry.register_evaluator("dummy-eval", _zero_evaluator)
    try:
        assert registry.make_evaluator("dummy-eval") is _zero_evaluator
    finally:
        del registry._REGISTRY["dummy-eval"]
        del registry._EVALUATOR_REGISTRY["dummy-eval"]


def test_register_evaluator_requires_a_registered_game():
    with pytest.raises(ValueError, match="unregistered game"):
        registry.register_evaluator("no-such-game", _zero_evaluator)


def test_register_duplicate_evaluator_raises():
    registry.register("dummy-eval-dup", _DummyGame)
    registry.register_evaluator("dummy-eval-dup", _zero_evaluator)
    try:
        with pytest.raises(ValueError, match="already registered"):
            registry.register_evaluator("dummy-eval-dup", _zero_evaluator)
    finally:
        del registry._REGISTRY["dummy-eval-dup"]
        del registry._EVALUATOR_REGISTRY["dummy-eval-dup"]


def test_make_evaluator_for_game_without_one_raises_key_error():
    with pytest.raises(KeyError, match="no evaluator"):
        registry.make_evaluator("does-not-exist")
