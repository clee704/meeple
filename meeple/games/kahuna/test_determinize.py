"""Tests for `KahunaState.resample_from_infostate` (`determinize.py`).

States are always built by applying actions from the real initial state —
the determinizer replays the state's action log, which hand-assembled
states (as used in test_engine.py) don't carry.
"""

import random

import pytest

from meeple.framework.chance import resolve_chance
from meeple.framework.game import CHANCE
from meeple.games.kahuna.engine import (
    DECK,
    DISCARD_BASE,
    DRAW_BLIND,
    FACEUP_BASE,
    SKIP,
    KahunaGame,
    KahunaState,
)
from meeple.games.kahuna.graph import ISLANDS


def _deal(
    p0_cards: tuple[str, ...], p1_cards: tuple[str, ...], face_up: tuple[str, ...]
) -> KahunaState:
    state = KahunaGame().new_initial_state()
    for island in (*p0_cards, *p1_cards, *face_up):
        state = state.apply_action(ISLANDS.index(island))
    return state


_DEAL = (("ALOA", "BARI", "COCO"), ("DUDA", "ELAI", "FAAA"), ("GOLA", "HUNA", "IFFI"))


def _play_random(game_seed: int, plies: int) -> KahunaState:
    rng = random.Random(game_seed)
    state = resolve_chance(KahunaGame().new_initial_state(), rng)
    for _ in range(plies):
        if state.is_terminal():
            break
        state = resolve_chance(state.apply_action(rng.choice(state.legal_actions())), rng)
    return state


def _assert_consistent(sample: KahunaState, state: KahunaState, viewer: int) -> None:
    opponent = 1 - viewer
    # The defining property: the sampled world is indistinguishable to the
    # viewer, down to its own replayed log.
    assert sample.information_state_key(viewer) == state.information_state_key(viewer)
    # Everything the viewer sees is reproduced exactly...
    assert sample.hands[viewer] == state.hands[viewer]
    assert sample.hidden_discards[viewer] == state.hidden_discards[viewer]
    public = (
        "bridges face_up discard to_move pending pending_reason scores scoring_count "
        "previous_turn_was_skip final_turns_remaining premature_winner final_round_winner "
        "round_points faceup_takes played_card_this_turn discarded_this_turn"
    )
    for name in public.split():
        assert getattr(sample, name) == getattr(state, name), name
    # ...hidden zones keep their observed sizes, and no card is lost or
    # duplicated in the redistribution.
    assert len(sample.hands[opponent]) == len(state.hands[opponent])
    assert len(sample.hidden_discards[opponent]) == len(state.hidden_discards[opponent])
    assert len(sample.pile) == len(state.pile)
    cards = (
        sample.pile
        + sample.discard
        + sample.hands[0]
        + sample.hands[1]
        + sample.hidden_discards[0]
        + sample.hidden_discards[1]
        + tuple(card for card in sample.face_up if card is not None)
    )
    assert sorted(cards) == sorted(DECK)


@pytest.mark.parametrize("game_seed", range(3))
def test_resampled_worlds_match_the_viewers_information_state(game_seed):
    rng = random.Random(game_seed)
    state = resolve_chance(KahunaGame().new_initial_state(), rng)
    ply = 0
    while not state.is_terminal():
        if ply % 5 == 0:
            for viewer in (0, 1):
                _assert_consistent(
                    state.resample_from_infostate(viewer, random.Random(ply)), state, viewer
                )
        state = resolve_chance(state.apply_action(rng.choice(state.legal_actions())), rng)
        ply += 1
    for viewer in (0, 1):  # terminal states resample too
        _assert_consistent(state.resample_from_infostate(viewer, random.Random(0)), state, viewer)


def test_hidden_information_actually_varies_across_samples():
    # The opponent's whole hand is hidden from viewer 1 (initial deal +
    # blind draws); a determinizer that peeked at the true state or pinned
    # hidden draws to their true outcomes would sample one hand forever.
    state = _deal(*_DEAL)
    state = state.apply_action(DRAW_BLIND)
    state = state.apply_action(ISLANDS.index("JOJO"))  # p0's draw, masked for p1
    hands = {
        tuple(sorted(state.resample_from_infostate(1, random.Random(seed)).hands[0]))
        for seed in range(40)
    }
    assert len(hands) > 1
    assert all(len(hand) == 4 for hand in hands)


def test_witnessed_faceup_take_stays_in_the_opponents_hand():
    state = _deal(*_DEAL)
    state = state.apply_action(FACEUP_BASE + 0)  # p0 takes GOLA in full view of p1
    state = state.apply_action(ISLANDS.index("JOJO"))  # refill slot 0
    assert state.to_move == 1
    for seed in range(25):
        sample = state.resample_from_infostate(1, random.Random(seed))
        assert "GOLA" in sample.hands[0]


def test_facedown_discard_may_shed_a_witnessed_take():
    # p0 takes GOLA and HUNA in full view (reaching the hand limit), then
    # discards face-down. The viewer can't tell *what* was discarded, so
    # consistent worlds both keep and shed the witnessed GOLA: witnessed
    # takes are pinned by the card flow, not by a hard rule.
    state = _deal(*_DEAL)
    state = state.apply_action(FACEUP_BASE + 0)  # p0 takes GOLA
    state = state.apply_action(ISLANDS.index("JOJO"))
    state = state.apply_action(SKIP)  # p1
    state = state.apply_action(FACEUP_BASE + 1)  # p0 takes HUNA -> 5 cards
    state = state.apply_action(ISLANDS.index("KAHU"))
    state = state.apply_action(SKIP)  # p1
    state = state.apply_action(DISCARD_BASE + ISLANDS.index("GOLA"))  # hidden from p1
    state = state.apply_action(DRAW_BLIND)
    state = state.apply_action(ISLANDS.index("LALE"))
    with_gola = [
        "GOLA" in state.resample_from_infostate(1, random.Random(seed)).hands[0]
        for seed in range(60)
    ]
    assert any(with_gola) and not all(with_gola)


def test_resample_works_at_a_chance_node():
    state = _deal(*_DEAL).apply_action(DRAW_BLIND)
    assert state.current_player() == CHANCE
    sample = state.resample_from_infostate(1, random.Random(0))
    assert sample.current_player() == CHANCE
    assert sample.information_state_key(1) == state.information_state_key(1)


def test_resample_is_deterministic_under_a_fixed_seed():
    state = _play_random(game_seed=3, plies=30)
    samples = [state.resample_from_infostate(0, random.Random(42)) for _ in range(2)]
    assert samples[0].hands == samples[1].hands
    assert samples[0].pile == samples[1].pile
    assert samples[0].hidden_discards == samples[1].hidden_discards


def test_resampled_state_supports_a_full_playthrough():
    state = _play_random(game_seed=3, plies=40)
    sample = state.resample_from_infostate(0, random.Random(7))
    rng = random.Random(9)
    while not sample.is_terminal():
        sample = resolve_chance(sample.apply_action(rng.choice(sample.legal_actions())), rng)
    assert len(sample.returns()) == 2
