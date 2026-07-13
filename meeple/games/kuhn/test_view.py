"""Privacy tests for the Kuhn view: what a player sees must be independent
of the opponent's hidden card. SPI conformance (serialization, coverage) is
handled generically in `meeple/framework/test_view_conformance.py`."""

import pytest

from meeple.games.kuhn.engine import KuhnState
from meeple.games.kuhn.view import KuhnView


@pytest.fixture
def view():
    return KuhnView()


def test_observation_is_invariant_to_the_opponents_card(view):
    a = view.observation(KuhnState(cards=(2, 0), history="pb"), viewer=0)
    b = view.observation(KuhnState(cards=(2, 1), history="pb"), viewer=0)
    assert a == b == {"card": "K", "history": ["pass", "bet"], "to_move": 0}


def test_result_reveals_cards_only_at_showdown(view):
    showdown = view.result(KuhnState(cards=(2, 0), history="bb"))
    assert showdown == {"scores": [2.0, -2.0], "winner": 0, "cards": ["K", "J"]}

    fold = view.result(KuhnState(cards=(0, 2), history="bp"))
    assert fold == {"scores": [1.0, -1.0], "winner": 0, "cards": None}
