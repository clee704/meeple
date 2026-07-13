"""Chance-node resolution shared by every consumer that walks a game tree
forward (agents, the web backend): sample an outcome from a chance node's
distribution, or fast-forward through consecutive chance nodes until a
player must act or the game ends."""

import random

from meeple.framework.game import CHANCE, Action, State


def sample_chance(state: State, rng: random.Random) -> Action:
    """Sample one outcome from `state.chance_outcomes()`'s distribution."""
    outcomes, probs = zip(*state.chance_outcomes(), strict=True)
    return rng.choices(outcomes, weights=probs, k=1)[0]


def resolve_chance(state: State, rng: random.Random) -> State:
    """Apply sampled chance outcomes until `state` is terminal or a player
    is to move (e.g. an opening deal that cascades through several draws)."""
    while not state.is_terminal() and state.current_player() == CHANCE:
        state = state.apply_action(sample_chance(state, rng))
    return state
