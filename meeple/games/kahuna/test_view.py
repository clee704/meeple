"""Kahuna view tests: privacy (the observation and history must not leak the
opponent's hand, the pile order, or a face-down discard's identity), action
metadata decoding, and the result's RULES.md tiebreak. Generic SPI
conformance lives in `meeple/framework/test_view_conformance.py`."""

import pytest

from meeple.games.kahuna.engine import (
    DISCARD_BASE,
    DRAW_BLIND,
    FACEUP_BASE,
    NUM_BRIDGES,
    PLACE_B_BASE,
    REMOVE_AB_BASE,
    SKIP,
    KahunaState,
)
from meeple.games.kahuna.graph import BRIDGES, ISLANDS
from meeple.games.kahuna.view import KahunaView


@pytest.fixture
def view():
    return KahunaView()


def _state(**overrides) -> KahunaState:
    fields = dict(
        bridges=(None,) * NUM_BRIDGES,
        hands=((), ()),
        face_up=(None, None, None),
        pile=(),
        discard=(),
        to_move=0,
        pending=(),
        pending_reason="turn",
        scores=(0.0, 0.0),
        scoring_count=0,
        previous_turn_was_skip=False,
        final_turns_remaining=None,
        premature_winner=None,
    )
    fields.update(overrides)
    return KahunaState(**fields)


def test_observation_is_invariant_to_opponent_privates(view):
    base = dict(
        hands=(("ALOA", "BARI"), ("COCO", "COCO", "DUDA")),
        pile=("ELAI", "FAAA", "GOLA"),
        hidden_discards=((), ("HUNA",)),
    )
    shuffled = dict(
        hands=(("ALOA", "BARI"), ("KAHU", "LALE", "IFFI")),  # different opponent hand
        pile=("GOLA", "ELAI", "FAAA"),  # different pile order
        hidden_discards=((), ("JOJO",)),  # different opponent face-down discard
    )
    a = view.observation(_state(**base), viewer=0)
    b = view.observation(_state(**shuffled), viewer=0)
    assert a == b
    assert a["hand"] == ["ALOA", "BARI"]
    assert a["opponent_hand_count"] == 3
    assert a["pile_count"] == 3
    assert a["opponent_hidden_discard_count"] == 1


def test_observation_shows_own_privates_by_identity(view):
    state = _state(
        hands=(("ALOA",), ("BARI", "COCO")),
        hidden_discards=(("DUDA", "ALOA"), ("ELAI",)),
    )
    obs = view.observation(state, viewer=0)
    assert obs["my_hidden_discards"] == ["ALOA", "DUDA"]
    obs1 = view.observation(state, viewer=1)
    assert obs1["hand"] == ["BARI", "COCO"]
    assert obs1["my_hidden_discards"] == ["ELAI"]
    assert obs1["opponent_hidden_discard_count"] == 2


def test_observation_reports_island_control(view):
    # ALOA has bridges at positions 0,1,2 and majority 2.
    obs = view.observation(_state(bridges=(0, 0) + (None,) * (NUM_BRIDGES - 2)), viewer=1)
    assert obs["control"]["ALOA"] == 0
    assert obs["control"]["BARI"] is None


def test_action_metadata_decodes_the_engine_layout(view):
    pos = 7  # COCO-FAAA
    assert BRIDGES[pos] == ("COCO", "FAAA")
    assert view.action_metadata(PLACE_B_BASE + pos) == {
        "kind": "place",
        "bridge": pos,
        "islands": ["COCO", "FAAA"],
        "spend": ["FAAA"],
    }
    assert view.action_metadata(REMOVE_AB_BASE + pos) == {
        "kind": "remove",
        "bridge": pos,
        "islands": ["COCO", "FAAA"],
        "spend": ["COCO", "FAAA"],
    }
    assert view.action_metadata(DRAW_BLIND) == {"kind": "draw_blind"}
    assert view.action_metadata(SKIP) == {"kind": "skip"}
    assert view.action_metadata(DISCARD_BASE + ISLANDS.index("HUNA")) == {
        "kind": "discard",
        "island": "HUNA",
    }


def test_describe_action_hides_opponents_facedown_discard(view):
    action = DISCARD_BASE + ISLANDS.index("HUNA")
    state = _state()
    assert view.describe_action(action, viewer=0, actor=0, state=state)["island"] == "HUNA"
    assert view.describe_action(action, viewer=1, actor=0, state=state)["island"] is None
    # Non-discard actions are public and never masked.
    assert view.describe_action(SKIP, viewer=1, actor=0, state=state) == {"kind": "skip"}


def test_describe_action_names_the_faceup_card_taken(view):
    state = _state(face_up=("COCO", "HUNA", None))
    for viewer in (0, 1):  # public to both players
        meta = view.describe_action(FACEUP_BASE + 1, viewer=viewer, actor=0, state=state)
        assert meta == {"kind": "take_faceup", "slot": 1, "card": "HUNA"}


def test_result_uses_the_rules_tiebreak_not_returns_argmax(view):
    # Tied points, but player 1 won the final scoring round: returns() is
    # [0, 0] (a draw by reward) while the RULES.md tiebreak crowns player 1.
    tied = _state(
        scores=(4.0, 4.0),
        scoring_count=3,
        final_turns_remaining=0,
        final_round_winner=1,
    )
    assert view.result(tied) == {
        "scores": [0.0, 0.0],
        "winner": 1,
        "points": [4.0, 4.0],
        "premature": False,
    }


def test_result_flags_a_premature_win(view):
    premature = _state(premature_winner=0, scoring_count=1)
    assert view.result(premature) == {
        "scores": [1.0, -1.0],
        "winner": 0,
        "points": [0.0, 0.0],
        "premature": True,
    }
