"""Registry: game id -> `Game` factory (and optionally a `GameView` factory
for games playable in the web UI). The only place `ai`/`eval`/`web` look up a
game by name, so they never import a specific game's package directly."""

from collections.abc import Callable

from meeple.framework.game import Game
from meeple.framework.view import GameView

_REGISTRY: dict[str, Callable[[], Game]] = {}
_VIEW_REGISTRY: dict[str, Callable[[], GameView]] = {}


def register(game_id: str, factory: Callable[[], Game]) -> None:
    if game_id in _REGISTRY:
        raise ValueError(f"game {game_id!r} is already registered")
    _REGISTRY[game_id] = factory


def register_view(game_id: str, factory: Callable[[], GameView]) -> None:
    if game_id not in _REGISTRY:
        raise ValueError(f"cannot register a view for unregistered game {game_id!r}")
    if game_id in _VIEW_REGISTRY:
        raise ValueError(f"view for game {game_id!r} is already registered")
    _VIEW_REGISTRY[game_id] = factory


def make(game_id: str) -> Game:
    try:
        factory = _REGISTRY[game_id]
    except KeyError:
        raise KeyError(f"unknown game {game_id!r}; registered games: {sorted(_REGISTRY)}") from None
    return factory()


def make_view(game_id: str) -> GameView:
    try:
        factory = _VIEW_REGISTRY[game_id]
    except KeyError:
        raise KeyError(
            f"no view for game {game_id!r}; games with views: {sorted(_VIEW_REGISTRY)}"
        ) from None
    return factory()


def registered_games() -> list[str]:
    return sorted(_REGISTRY)


def games_with_views() -> list[str]:
    return sorted(_VIEW_REGISTRY)
