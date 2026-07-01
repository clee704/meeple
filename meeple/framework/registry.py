"""Registry: game id -> `Game` factory. The only place `ai`/`eval`/`web` look
up a game by name, so they never import a specific game's package directly."""

from collections.abc import Callable

from meeple.framework.game import Game

_REGISTRY: dict[str, Callable[[], Game]] = {}


def register(game_id: str, factory: Callable[[], Game]) -> None:
    if game_id in _REGISTRY:
        raise ValueError(f"game {game_id!r} is already registered")
    _REGISTRY[game_id] = factory


def make(game_id: str) -> Game:
    try:
        factory = _REGISTRY[game_id]
    except KeyError:
        raise KeyError(f"unknown game {game_id!r}; registered games: {sorted(_REGISTRY)}") from None
    return factory()


def registered_games() -> list[str]:
    return sorted(_REGISTRY)
