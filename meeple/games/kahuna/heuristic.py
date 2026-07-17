"""Kahuna position evaluator for `framework.registry`'s evaluator hook
(consumed by the 1-ply-greedy heuristic agent). Reads only the state's zone
caches, so it accepts chance-pending states as the contract requires."""

from meeple.games.kahuna.engine import KahunaState
from meeple.games.kahuna.graph import ISLANDS, MAJORITY

# Weights, largest to smallest: a decided game dwarfs everything; banked
# points dwarf positional promise; holding an island's majority outweighs
# being one bridge short of one; bridges on the board and cards in hand are
# light material/tempo terms.
_TERMINAL = 1000.0
_SCORE = 10.0
_CONTROL = 3.0
_THREAT = 1.0
_BRIDGE = 0.3
_CARD = 0.1


def evaluate(state: KahunaState, player: int) -> float:
    """Higher is better for `player`; antisymmetric between the players
    (every term is a player-minus-opponent difference)."""
    if state.is_terminal():
        return _TERMINAL * state.returns()[player]
    opponent = 1 - player
    value = _SCORE * (state.scores[player] - state.scores[opponent])
    for island in ISLANDS:
        majority = MAJORITY[island]
        for who, sign in ((player, 1.0), (opponent, -1.0)):
            count = state._bridge_count(who, island)
            if count >= majority:
                value += sign * _CONTROL
            elif count == majority - 1:
                value += sign * _THREAT
    value += _BRIDGE * (state._total_bridges(player) - state._total_bridges(opponent))
    value += _CARD * (len(state.hands[player]) - len(state.hands[opponent]))
    return value
