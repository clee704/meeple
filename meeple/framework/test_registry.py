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
