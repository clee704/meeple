"""The game-agnostic contract every agent implements. Agents reach a game
only through `meeple.framework` (the seam) — never a specific game's package."""

import random
from abc import ABC, abstractmethod

from meeple.framework.game import Action, State


class Agent(ABC):
    """An action-selection policy: given a state where a player is to move,
    pick one of its legal actions.

    Agents are stateless across calls — everything they know comes from the
    `state` (whose information-state methods already encode perfect recall)
    and the caller-owned `rng`, so one instance can serve any number of
    concurrent matches and replaying a seeded match reproduces it exactly.
    Configuration that is fixed for an agent's lifetime (e.g. a simulation
    budget as the difficulty knob) belongs in the constructor, not in
    mutable per-match fields.
    """

    @abstractmethod
    def select_action(self, state: State, rng: random.Random) -> Action: ...
