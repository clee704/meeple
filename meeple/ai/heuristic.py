"""1-ply greedy agent over a per-game evaluation hook: apply each legal
action, score the resulting state with the game's `Evaluator` (registered
through `framework.registry`, same opt-in pattern as `GameView`), pick the
best. Per the solver matrix (AGENTS.md) this is the baseline every game
gets for free once it registers an evaluator — the first opponent a search
agent must beat, and the fallback where search is too expensive."""

import random

from meeple.ai.base import Agent
from meeple.framework.game import Action, State
from meeple.framework.registry import Evaluator


class HeuristicAgent(Agent):
    """Greedy over `evaluator`: no search and no chance expectation — a
    child that is a chance node is scored as the position stands (the
    `Evaluator` contract requires accepting pending states), keeping the
    agent at one evaluation per legal action. Ties break by `rng` among
    the best children, so play varies across matches but replays exactly
    under a fixed seed."""

    def __init__(self, evaluator: Evaluator):
        self._evaluator = evaluator

    def select_action(self, state: State, rng: random.Random) -> Action:
        player = state.current_player()
        best_value = float("-inf")
        best: list[Action] = []
        for action in state.legal_actions():
            value = self._evaluator(state.apply_action(action), player)
            if value > best_value:
                best_value, best = value, [action]
            elif value == best_value:
                best.append(action)
        return rng.choice(best)
