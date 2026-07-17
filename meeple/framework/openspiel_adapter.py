"""Wraps an OpenSpiel game behind the `Game`/`State` interface.

Oracle-only: used to cross-check native engines (e.g. Kuhn) in tests, never
as a game backend for play/eval/web. `open-spiel` is an optional dependency —
import this module lazily, only where the cross-check happens.
"""

import random

import pyspiel
import torch

from meeple.framework.game import CHANCE, Action, Game, State
from meeple.framework.spec import GameSpec


class OpenSpielState(State):
    def __init__(self, state: pyspiel.State):
        self._state = state

    def legal_actions(self) -> list[Action]:
        return self._state.legal_actions()

    def apply_action(self, action: Action) -> "OpenSpielState":
        child = self._state.clone()
        child.apply_action(action)
        return OpenSpielState(child)

    def is_terminal(self) -> bool:
        return self._state.is_terminal()

    def returns(self) -> list[float]:
        return self._state.returns()

    def current_player(self) -> int:
        player = self._state.current_player()
        return CHANCE if player == pyspiel.PlayerId.CHANCE else player

    def chance_outcomes(self) -> list[tuple[Action, float]]:
        return self._state.chance_outcomes()

    def information_state_key(self, player: int) -> str:
        return self._state.information_state_string(player)

    def information_state_tensor(self, player: int) -> torch.Tensor:
        return torch.tensor(self._state.information_state_tensor(player), dtype=torch.float32)

    def resample_from_infostate(self, player: int, rng: random.Random) -> "OpenSpielState":
        # pyspiel wants a 0-arg uniform-[0,1) sampler instead of an rng.
        try:
            return OpenSpielState(self._state.resample_from_infostate(player, rng.random))
        except pyspiel.SpielError as error:
            raise NotImplementedError(
                f"the wrapped OpenSpiel game does not implement resample_from_infostate: {error}"
            ) from error


class OpenSpielGame(Game):
    """Adapts an OpenSpiel game registered under `openspiel_name` to `Game`."""

    def __init__(self, openspiel_name: str):
        self._game = pyspiel.load_game(openspiel_name)

    def new_initial_state(self) -> OpenSpielState:
        return OpenSpielState(self._game.new_initial_state())

    def spec(self) -> GameSpec:
        t = self._game.get_type()
        info = self._game.get_type().information
        return GameSpec(
            num_players=self._game.num_players(),
            perfect_information=info == pyspiel.GameType.Information.PERFECT_INFORMATION,
            has_chance=t.chance_mode != pyspiel.GameType.ChanceMode.DETERMINISTIC,
            zero_sum=t.utility == pyspiel.GameType.Utility.ZERO_SUM,
            num_distinct_actions=self._game.num_distinct_actions(),
            action_names=tuple(str(i) for i in range(self._game.num_distinct_actions())),
        )
