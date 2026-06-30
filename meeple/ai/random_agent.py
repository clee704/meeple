"""Baseline agent: picks uniformly among legal actions. Used to smoke-test the
seam (Phase 1) and as the eval harness's weakest opponent (CLAUDE.md G5)."""

import random

from meeple.framework.game import Action, State


def select_action(state: State, rng: random.Random) -> Action:
    return rng.choice(state.legal_actions())


def play_to_terminal(state: State, rng: random.Random) -> State:
    """Drive `state` to a terminal node, resolving chance nodes uniformly at
    random by sampling from `chance_outcomes()`'s distribution."""
    while not state.is_terminal():
        if state.current_player() == -1:
            outcomes, probs = zip(*state.chance_outcomes(), strict=True)
            action = rng.choices(outcomes, weights=probs, k=1)[0]
        else:
            action = select_action(state, rng)
        state = state.apply_action(action)
    return state
