"""Tests for the Kahuna evaluator (`heuristic.py`). Zone-level states are
assembled via test_engine's `_state` helper — the evaluator reads only zone
caches, so no action log is needed."""

from meeple.games.kahuna.engine import KahunaGame
from meeple.games.kahuna.heuristic import evaluate
from meeple.games.kahuna.test_engine import _bridges_with, _state


def test_antisymmetric_between_the_players():
    state = _state(
        bridges=_bridges_with(("ALOA", "BARI", 0), ("ALOA", "DUDA", 0), ("COCO", "FAAA", 1)),
        hands=(("ELAI", "GOLA"), ("HUNA",)),
        scores=(2.0, 1.0),
        pile=("IFFI",),
    )
    assert evaluate(state, 0) == -evaluate(state, 1)
    assert evaluate(state, 0) > 0  # ahead on every term


def test_banked_points_outweigh_positional_promise():
    behind_on_points = _state(
        bridges=_bridges_with(("ALOA", "BARI", 0), ("ALOA", "DUDA", 0), ("ALOA", "HUNA", 0)),
        scores=(0.0, 1.0),
        pile=("IFFI",),
    )
    ahead_on_points = _state(scores=(1.0, 0.0), pile=("IFFI",))
    assert evaluate(ahead_on_points, 0) > evaluate(behind_on_points, 0)


def test_controlling_an_island_beats_threatening_it():
    # ALOA has 3 bridge lines, so majority needs 2: two bridges control it,
    # one is a threat.
    control = _state(
        bridges=_bridges_with(("ALOA", "BARI", 0), ("ALOA", "DUDA", 0)), pile=("IFFI",)
    )
    threat = _state(bridges=_bridges_with(("ALOA", "BARI", 0)), pile=("IFFI",))
    empty = _state(pile=("IFFI",))
    assert evaluate(control, 0) > evaluate(threat, 0) > evaluate(empty, 0)


def test_terminal_outcome_dominates_any_position():
    won = _state(premature_winner=0, scoring_count=1, pile=("IFFI",))
    rich_position = _state(
        bridges=_bridges_with(*((a, b, 0) for a, b in [("ALOA", "BARI"), ("ALOA", "DUDA")])),
        hands=(("ELAI", "GOLA", "HUNA", "IFFI", "JOJO"), ()),
        scores=(3.0, 0.0),
        pile=("KAHU",),
    )
    assert evaluate(won, 0) > evaluate(rich_position, 0)
    assert evaluate(won, 1) < evaluate(rich_position, 1)


def test_accepts_a_chance_pending_state():
    state = KahunaGame().new_initial_state()  # setup deal still pending
    assert evaluate(state, 0) == 0.0  # symmetric position evaluates even
