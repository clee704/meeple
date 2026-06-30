"""The game-agnostic interface every engine implements (CLAUDE.md G2 — the seam)."""

from abc import ABC, abstractmethod

import torch

from meeple.framework.spec import GameSpec

Action = int
CHANCE = -1


class State(ABC):
    """A node in a game tree. `apply_action` returns a new `State` and must be
    cheap to produce — CFR and MCTS recurse over it heavily."""

    @abstractmethod
    def legal_actions(self) -> list[Action]: ...

    @abstractmethod
    def apply_action(self, action: Action) -> "State": ...

    @abstractmethod
    def is_terminal(self) -> bool: ...

    @abstractmethod
    def returns(self) -> list[float]:
        """Per-player payoff at a terminal state."""

    @abstractmethod
    def current_player(self) -> int:
        """`CHANCE` (-1) at a chance node, else the acting player's index."""

    @abstractmethod
    def chance_outcomes(self) -> list[tuple[Action, float]]: ...

    @abstractmethod
    def information_state_tensor(self, player: int) -> torch.Tensor:
        """Deep CFR input: everything `player` can observe, encoded as a tensor."""

    @abstractmethod
    def information_state_key(self, player: int) -> str:
        """Tabular CFR info-set key: a hashable summary of what `player` observes."""


class Game(ABC):
    """A factory for initial states plus the static `GameSpec` that drives
    solver selection (CLAUDE.md's solver-compatibility matrix)."""

    @abstractmethod
    def new_initial_state(self) -> State: ...

    @abstractmethod
    def spec(self) -> GameSpec: ...
