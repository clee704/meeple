"""Cross-checks the native Kuhn engine against OpenSpiel's `kuhn_poker` (the
oracle, CLAUDE.md G6) over every deal and betting sequence: PLAN.md Phase 1's
done-when is "native and OpenSpiel agree on returns over many seeded games."

Both engines deal cards 0=J/1=Q/2=K; OpenSpiel resolves the deal as two
sequential chance nodes (one card per player), while the native engine uses
one combined chance node — so each deal is driven with the *equivalent*
explicit actions per engine rather than a shared RNG seed (the two chance
encodings consume randomness differently and would desync under one seed).
"""

from itertools import permutations, product

import pytest

from meeple.framework.openspiel_adapter import OpenSpielGame
from meeple.games.kuhn.engine import BET, PASS, KuhnGame

DEALS = list(permutations(range(3), 2))  # (p0_card, p1_card); same order as engine.py's _DEALS
BETTING_SEQUENCES = ["pp", "bp", "bb", "pbp", "pbb"]


def _play_native(p0_card: int, p1_card: int, betting: str):
    state = KuhnGame().new_initial_state()
    state = state.apply_action(DEALS.index((p0_card, p1_card)))
    for ch in betting:
        state = state.apply_action(PASS if ch == "p" else BET)
    return state


def _play_openspiel(p0_card: int, p1_card: int, betting: str):
    state = OpenSpielGame("kuhn_poker").new_initial_state()
    state = state.apply_action(p0_card)
    state = state.apply_action(p1_card)
    for ch in betting:
        state = state.apply_action(PASS if ch == "p" else BET)
    return state


@pytest.mark.parametrize(("deal", "betting"), list(product(DEALS, BETTING_SEQUENCES)))
def test_native_kuhn_matches_openspiel_returns(deal, betting):
    p0_card, p1_card = deal
    native = _play_native(p0_card, p1_card, betting)
    openspiel = _play_openspiel(p0_card, p1_card, betting)

    assert native.is_terminal() == openspiel.is_terminal()
    if native.is_terminal():
        assert native.returns() == list(openspiel.returns())
