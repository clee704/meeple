import random

import pytest

from meeple.framework.game import CHANCE
from meeple.framework.openspiel_adapter import OpenSpielGame, OpenSpielState


def test_spec_matches_kuhn_poker():
    spec = OpenSpielGame("kuhn_poker").spec()
    assert spec.num_players == 2
    assert spec.perfect_information is False
    assert spec.has_chance is True
    assert spec.zero_sum is True
    assert spec.num_distinct_actions == 2


def test_initial_state_is_chance_node_with_three_outcomes():
    state = OpenSpielGame("kuhn_poker").new_initial_state()
    assert state.current_player() == CHANCE
    assert state.legal_actions() == [0, 1, 2]
    assert state.chance_outcomes() == [(0, 1 / 3), (1, 1 / 3), (2, 1 / 3)]


def test_information_state_key_and_tensor_after_deal():
    state = OpenSpielGame("kuhn_poker").new_initial_state()
    state = state.apply_action(0).apply_action(1)
    assert state.current_player() == 0
    assert "0" in state.information_state_key(0)
    assert state.information_state_tensor(0).numel() > 0


def test_resample_from_infostate_delegates_to_the_wrapped_game():
    state = OpenSpielGame("kuhn_poker").new_initial_state()
    state = state.apply_action(0).apply_action(1)
    sample = state.resample_from_infostate(0, random.Random(0))
    assert isinstance(sample, OpenSpielState)
    assert sample.information_state_key(0) == state.information_state_key(0)


def test_resample_from_infostate_raises_clearly_when_unsupported():
    state = OpenSpielGame("phantom_ttt").new_initial_state()
    with pytest.raises(NotImplementedError, match="resample_from_infostate"):
        state.resample_from_infostate(0, random.Random(0))
