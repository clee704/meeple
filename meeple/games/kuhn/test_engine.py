import random

import pytest

from meeple.framework.game import CHANCE, State
from meeple.games.kuhn.engine import BET, PASS, KuhnGame, KuhnState


def _deal(p0_card: int, p1_card: int, history: str = "") -> KuhnState:
    return KuhnState(cards=(p0_card, p1_card), history=history)


def _random_playthrough(state: State, rng: random.Random) -> State:
    """Drives `state` to terminal via uniform-random choices, without pulling
    in `meeple.ai` — a game's package should depend only on `meeple.framework`,
    never on the AI layer, and that includes its own tests."""
    while not state.is_terminal():
        if state.current_player() == CHANCE:
            outcomes, probs = zip(*state.chance_outcomes(), strict=True)
            action = rng.choices(outcomes, weights=probs, k=1)[0]
        else:
            action = rng.choice(state.legal_actions())
        state = state.apply_action(action)
    return state


def test_initial_state_is_a_chance_node():
    state = KuhnGame().new_initial_state()
    assert state.current_player() == CHANCE
    outcomes = state.chance_outcomes()
    assert len(outcomes) == 6
    assert sum(p for _, p in outcomes) == pytest.approx(1.0)


def test_legal_actions_after_deal():
    state = _deal(0, 1)
    assert state.legal_actions() == [PASS, BET]


def test_illegal_action_rejected():
    state = _deal(0, 1)
    with pytest.raises(ValueError):
        state.apply_action(2)


def test_legal_actions_on_terminal_state_is_empty():
    state = _deal(0, 1, history="pp")
    assert state.is_terminal()
    assert state.legal_actions() == []


@pytest.mark.parametrize(
    ("p0_card", "p1_card", "history", "expected_returns"),
    [
        (0, 1, "pp", [-1.0, 1.0]),  # showdown, no bets: Q beats J
        (2, 1, "pp", [1.0, -1.0]),  # showdown, no bets: K beats Q
        (0, 1, "bp", [1.0, -1.0]),  # player 0 bets, player 1 folds
        (0, 1, "pbp", [-1.0, 1.0]),  # player 1 bets, player 0 folds
        (1, 2, "bb", [-2.0, 2.0]),  # showdown after bet+call: K beats Q
        (1, 2, "pbb", [-2.0, 2.0]),  # showdown after pass/bet/call: K beats Q
        (2, 1, "pbb", [2.0, -2.0]),  # showdown after pass/bet/call: K beats Q
    ],
)
def test_returns_at_known_terminal_states(p0_card, p1_card, history, expected_returns):
    state = _deal(p0_card, p1_card, history=history)
    assert state.is_terminal()
    assert state.returns() == expected_returns
    assert sum(state.returns()) == 0.0  # zero-sum


def test_worked_example_from_rules_md():
    # RULES.md worked example: deal Q to p0, K to p1, history "pb".
    state = _deal(p0_card=1, p1_card=2, history="pb")
    assert state.legal_actions() == [PASS, BET]

    folded = state.apply_action(PASS)
    assert folded.is_terminal()
    assert folded.returns() == [-1.0, 1.0]

    called = state.apply_action(BET)
    assert called.is_terminal()
    assert called.returns() == [-2.0, 2.0]


def test_returns_before_terminal_raises():
    state = _deal(0, 1)
    with pytest.raises(RuntimeError):
        state.returns()


def test_full_playthrough_is_terminal_and_zero_sum():
    final = _random_playthrough(KuhnGame().new_initial_state(), random.Random(0))
    assert final.is_terminal()
    assert sum(final.returns()) == 0.0


def test_determinism_under_fixed_seed():
    def run(seed: int) -> list[float]:
        return _random_playthrough(KuhnGame().new_initial_state(), random.Random(seed)).returns()

    assert run(42) == run(42)


def test_information_state_key_hides_opponent_card():
    p0_view_a = _deal(0, 1, history="p").information_state_key(0)
    p0_view_b = _deal(0, 2, history="p").information_state_key(0)
    assert p0_view_a == p0_view_b  # player 0's view doesn't depend on p1's card


def test_information_state_tensor_shape():
    state = _deal(0, 1, history="pb")
    tensor = state.information_state_tensor(0)
    assert tensor.shape == (9,)


@pytest.mark.parametrize("viewer", [0, 1])
def test_resample_preserves_the_viewers_information_state(viewer):
    state = _deal(0, 1, history="pb")
    sample = state.resample_from_infostate(viewer, random.Random(0))
    assert sample.information_state_key(viewer) == state.information_state_key(viewer)


def test_resample_covers_both_unseen_opponent_cards():
    state = _deal(0, 1, history="b")
    sampled = {
        state.resample_from_infostate(0, random.Random(seed))._cards[1] for seed in range(40)
    }
    assert sampled == {1, 2}  # everything but player 0's own card


def test_resample_is_deterministic_under_a_fixed_seed():
    state = _deal(2, 0, history="p")
    cards = [state.resample_from_infostate(1, random.Random(5))._cards for _ in range(2)]
    assert cards[0] == cards[1]


def test_resample_before_the_deal_returns_self():
    state = KuhnGame().new_initial_state()
    assert state.resample_from_infostate(0, random.Random(0)) is state
