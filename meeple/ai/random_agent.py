"""Baseline agent: picks uniformly among legal actions. Used to smoke-test new
`Game`/`State` implementations end-to-end, and as the eval harness's weakest
opponent — every other agent must beat this decisively."""

import random

from meeple.ai.base import Agent
from meeple.framework.chance import resolve_chance
from meeple.framework.game import Action, State


class RandomAgent(Agent):
    def select_action(self, state: State, rng: random.Random) -> Action:
        return rng.choice(state.legal_actions())


def play_to_terminal(state: State, rng: random.Random) -> State:
    """Drive `state` to a terminal node with uniformly random play, resolving
    chance nodes by sampling from `chance_outcomes()`'s distribution."""
    agent = RandomAgent()
    state = resolve_chance(state, rng)
    while not state.is_terminal():
        state = resolve_chance(state.apply_action(agent.select_action(state, rng)), rng)
    return state
