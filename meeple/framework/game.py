"""The game-agnostic interface every engine implements. AI, eval, and web code
should depend only on this module (plus `spec.py`/`registry.py`) to reach a
game — never on a specific game's package."""

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
        """Deep CFR input: what `player` observes, as a fixed-size tensor.
        The one place a lossy encoding is sanctioned — each game's RULES.md
        documents exactly what its encoding drops."""

    @abstractmethod
    def information_state_key(self, player: int) -> str:
        """Tabular CFR info-set key: `player`'s full observation history.
        The contract is perfect recall — the key encodes everything `player`
        has observed (all public actions, plus chance outcomes and hidden
        actions masked per viewer), never a lossy snapshot of current zones.
        For games whose state fields don't already spell out that history,
        the recommended construction is a per-viewer masked projection of an
        append-only action log carried by the state, so recall holds by
        construction rather than by field selection."""


class Game(ABC):
    """A factory for initial states plus the static `GameSpec` that drives
    which solver (heuristic, MCTS, ISMCTS, CFR, ...) is compatible with it."""

    @abstractmethod
    def new_initial_state(self) -> State: ...

    @abstractmethod
    def spec(self) -> GameSpec: ...
