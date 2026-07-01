import random

import pytest

from meeple.framework.game import CHANCE, State
from meeple.games.kahuna.engine import (
    DISCARD_BASE,
    DRAW_BLIND,
    FACEUP_BASE,
    HAND_LIMIT,
    NUM_BRIDGES,
    PLACE_A_BASE,
    PLACE_B_BASE,
    REMOVE_AA_BASE,
    REMOVE_AB_BASE,
    REMOVE_BB_BASE,
    SKIP,
    KahunaGame,
    KahunaState,
)
from meeple.games.kahuna.graph import BRIDGES, ISLANDS


def _state(**overrides) -> KahunaState:
    fields = dict(
        bridges=(None,) * NUM_BRIDGES,
        hands=((), ()),
        face_up=(None, None, None),
        pile=(),
        discard=(),
        current_player=0,
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


def _random_playthrough(state: State, rng: random.Random) -> State:
    while not state.is_terminal():
        if state.current_player() == CHANCE:
            outcomes, probs = zip(*state.chance_outcomes(), strict=True)
            action = rng.choices(outcomes, weights=probs, k=1)[0]
        else:
            action = rng.choice(state.legal_actions())
        state = state.apply_action(action)
    return state


def _bridges_with(*owned: tuple[str, str, int]) -> tuple[int | None, ...]:
    bridges: list[int | None] = [None] * NUM_BRIDGES
    for a, b, owner in owned:
        bridges[BRIDGES.index((a, b))] = owner
    return tuple(bridges)


# --- setup / deal --------------------------------------------------------


def test_initial_deal_gives_each_player_3_cards_and_3_faceup_and_player0_starts():
    state = KahunaGame().new_initial_state()
    rng = random.Random(0)
    while state.current_player() == CHANCE:
        outcomes, probs = zip(*state.chance_outcomes(), strict=True)
        action = rng.choices(outcomes, weights=probs, k=1)[0]
        state = state.apply_action(action)
    assert len(state._hands[0]) == 3
    assert len(state._hands[1]) == 3
    assert all(c is not None for c in state._face_up)
    assert state.current_player() == 0


# --- legal actions / illegal action rejection ----------------------------


def test_place_legal_only_with_a_matching_card_and_free_line():
    pos = BRIDGES.index(("ALOA", "BARI"))
    state = _state(hands=(("ALOA",), ()))
    assert PLACE_A_BASE + pos in state.legal_actions()
    assert PLACE_B_BASE + pos not in state.legal_actions()  # no BARI card


def test_illegal_action_rejected():
    state = _state(hands=(("ALOA",), ()))
    illegal_pos = BRIDGES.index(("KAHU", "LALE"))
    with pytest.raises(ValueError):
        state.apply_action(PLACE_A_BASE + illegal_pos)  # no KAHU card


def test_remove_requires_opponent_bridge_and_correct_cards():
    pos = BRIDGES.index(("ELAI", "HUNA"))
    state = _state(
        bridges=_bridges_with(("ELAI", "HUNA", 1)),
        hands=(("ELAI", "ELAI"), ()),
    )
    legal = state.legal_actions()
    assert REMOVE_AA_BASE + pos in legal  # 2x ELAI (the 'a' endpoint)
    assert REMOVE_BB_BASE + pos not in legal  # no HUNA cards
    assert REMOVE_AB_BASE + pos not in legal  # no HUNA card for the mixed pay


# --- place/remove spend the specific card the action names (A2 fix) -----


def test_place_a_and_place_b_discard_different_cards():
    pos = BRIDGES.index(("ELAI", "HUNA"))
    state = _state(hands=(("ELAI", "HUNA"), ()))
    after_a = state.apply_action(PLACE_A_BASE + pos)
    after_b = state.apply_action(PLACE_B_BASE + pos)
    assert after_a._hands[0] == ("HUNA",)
    assert after_a._discard == ("ELAI",)
    assert after_b._hands[0] == ("ELAI",)
    assert after_b._discard == ("HUNA",)


def test_remove_variants_discard_different_card_combinations():
    pos = BRIDGES.index(("ELAI", "HUNA"))
    hand = ("ELAI", "ELAI", "HUNA")
    state = _state(bridges=_bridges_with(("ELAI", "HUNA", 1)), hands=(hand, ()))
    after_aa = state.apply_action(REMOVE_AA_BASE + pos)
    after_ab = state.apply_action(REMOVE_AB_BASE + pos)
    assert after_aa._hands[0] == ("HUNA",)
    assert after_aa._discard == ("ELAI", "ELAI")
    assert after_ab._hands[0] == ("ELAI",)
    assert after_ab._discard == ("ELAI", "HUNA")


# --- majority / control, including the even-degree case -----------------


def test_even_degree_island_needs_strictly_more_than_half():
    # COCO has degree 4 (BARI, FAAA, GOLA, KAHU); majority is 3, not 2.
    two_of_four = _bridges_with(("BARI", "COCO", 0), ("COCO", "FAAA", 0))
    state = _state(bridges=two_of_four, hands=(("GOLA",), ()))
    pos = BRIDGES.index(("COCO", "GOLA"))
    after = state.apply_action(PLACE_B_BASE + pos)  # player 0 now has 3 of 4 on COCO
    assert after._controller("COCO") == 0

    one_short = _state(bridges=two_of_four)
    assert one_short._controller("COCO") is None  # 2 of 4 is not a majority


def test_worked_example_regression_elai_huna_ripple():
    """Regression test for RULES.md's worked example: a placement that wins
    ELAI's majority strips player 1's only ELAI bridge, which also drops
    player 1 below majority on HUNA -- costing them that token too, without
    touching their other HUNA bridges."""
    bridges = _bridges_with(
        ("BARI", "ELAI", 0),
        ("DUDA", "ELAI", 0),
        ("ELAI", "FAAA", 0),
        ("ELAI", "HUNA", 1),
        ("ALOA", "HUNA", 1),
        ("HUNA", "IFFI", 1),
    )
    state = _state(bridges=bridges, hands=(("ELAI",), ()))
    assert state._controller("ELAI") is None
    assert state._controller("HUNA") == 1

    pos = BRIDGES.index(("ELAI", "IFFI"))
    after = state.apply_action(PLACE_A_BASE + pos)

    assert after._controller("ELAI") == 0
    assert after._controller("HUNA") is None  # dethroned, not captured
    # player 1's other HUNA bridges are untouched:
    assert after._bridges[BRIDGES.index(("ALOA", "HUNA"))] == 1
    assert after._bridges[BRIDGES.index(("HUNA", "IFFI"))] == 1
    # the stripped bridge returns to the supply (free), not owned by anyone:
    assert after._bridges[BRIDGES.index(("ELAI", "HUNA"))] is None


def test_dethroning_does_not_grant_first_claim_to_reclaim():
    # After the ripple above, either player can reclaim HUNA -- including
    # player 1 rebuilding their own majority there.
    bridges = _bridges_with(
        ("ELAI", "IFFI", 0),
        ("ALOA", "HUNA", 1),
        ("HUNA", "IFFI", 1),
    )
    state = _state(bridges=bridges, hands=((), ("DUDA",)), current_player=1)
    assert state._controller("HUNA") is None
    pos = BRIDGES.index(("DUDA", "HUNA"))
    after = state.apply_action(PLACE_A_BASE + pos)
    assert after._controller("HUNA") == 1


# --- bridge/token supply --------------------------------------------------


def test_bridge_supply_limits_placement():
    owned = [(a, b, 0) for a, b in BRIDGES[:25]]
    bridges = _bridges_with(*owned)
    free_pos = BRIDGES.index(BRIDGES[25])
    a, b = BRIDGES[25]
    state = _state(bridges=bridges, hands=((a, b), ()))
    assert PLACE_A_BASE + free_pos not in state.legal_actions()  # supply exhausted


# --- skip / draw legality -------------------------------------------------


def test_cannot_skip_twice_in_a_row_when_a_draw_is_available():
    state = _state(pile=("ALOA",), previous_turn_was_skip=True)
    assert SKIP not in state.legal_actions()


def test_skip_always_legal_when_nothing_to_draw():
    state = _state(pile=(), face_up=(None, None, None), previous_turn_was_skip=True)
    assert SKIP in state.legal_actions()


def test_take_faceup_is_a_deliberate_pick_not_chance():
    state = _state(face_up=("ALOA", None, None), pile=())
    after = state.apply_action(FACEUP_BASE + 0)
    assert after._hands[0] == ("ALOA",)
    assert after.current_player() != CHANCE  # no pile to refill from


# --- hand limit: discard face-down first, then draw as normal ------------


def test_hand_limit_blocks_drawing_until_discarded():
    full_hand = tuple(ISLANDS[:HAND_LIMIT])
    assert len(full_hand) == HAND_LIMIT
    state = _state(hands=(full_hand, ()), pile=("ALOA",), face_up=("BARI", None, None))
    legal = state.legal_actions()
    assert DRAW_BLIND not in legal
    assert FACEUP_BASE + 0 not in legal
    island_idx = ISLANDS.index(full_hand[0])
    assert DISCARD_BASE + island_idx in legal

    after = state.apply_action(DISCARD_BASE + island_idx)
    assert len(after._hands[0]) == HAND_LIMIT - 1
    assert full_hand[0] in after._discard_hidden  # discarded face-down, not to the open pile
    assert full_hand[0] not in after._discard
    assert DRAW_BLIND in after.legal_actions()  # can draw normally now


def test_facedown_discard_identity_is_hidden_but_count_is_not():
    # Same number of face-down discards, different specific cards: the
    # count is public (comparable to pile size), but which cards they are
    # must not leak into either player's information state.
    aloa = _state(discard_hidden=("ALOA",))
    bari = _state(discard_hidden=("BARI",))
    assert aloa.information_state_key(1) == bari.information_state_key(1)
    assert aloa.information_state_tensor(1).tolist() == bari.information_state_tensor(1).tolist()

    # A different *count* is a genuinely different, visible state.
    two_hidden = _state(discard_hidden=("ALOA", "BARI"))
    assert aloa.information_state_key(1) != two_hidden.information_state_key(1)


def test_facedown_and_open_discards_both_get_reshuffled_into_the_pile():
    state = _state(pile=("ALOA",), discard=("BARI",), discard_hidden=("COCO",))
    after = _deplete_pile_and_faceup(state)
    assert after._discard == ()
    assert after._discard_hidden == ()
    assert sorted(after._pile) + sorted(c for c in after._face_up if c) == sorted(["BARI", "COCO"])


def test_discard_facedown_requires_a_matching_card():
    state = _state(hands=(("ALOA",), ()))
    with pytest.raises(ValueError):
        state.apply_action(DISCARD_BASE + ISLANDS.index("BARI"))


# --- scoring: interim, final, tiebreak, premature end --------------------


def _deplete_pile_and_faceup(state: KahunaState) -> KahunaState:
    state = state.apply_action(DRAW_BLIND)
    while state.current_player() == CHANCE:
        (action, _prob) = state.chance_outcomes()[0]
        state = state.apply_action(action)
    return state


def test_interim_scoring_1_awards_one_point_to_the_leader():
    # Player 0 controls ALOA and LALE (2 islands); player 1 controls none.
    bridges = _bridges_with(
        ("ALOA", "BARI", 0), ("ALOA", "DUDA", 0), ("HUNA", "LALE", 0), ("IFFI", "LALE", 0)
    )
    state = _state(bridges=bridges, pile=("ALOA",), discard=("BARI",))
    after = _deplete_pile_and_faceup(state)
    assert after._scores == (1.0, 0.0)
    assert after._scoring_count == 1
    assert len(after._face_up) == 3  # reshuffled and redealt (once chance resolves)


def test_interim_scoring_2_awards_two_points():
    bridges = _bridges_with(("ALOA", "BARI", 1), ("ALOA", "DUDA", 1))
    state = _state(bridges=bridges, pile=("ALOA",), scoring_count=1, discard=("BARI",))
    after = _deplete_pile_and_faceup(state)
    assert after._scores == (0.0, 2.0)
    assert after._scoring_count == 2


def test_third_depletion_starts_final_turns_instead_of_scoring_immediately():
    state = _state(pile=("ALOA",), scoring_count=2)
    after = _deplete_pile_and_faceup(state)
    assert after._scoring_count == 3
    assert after._final_turns_remaining == 2
    assert after._scores == (0.0, 0.0)  # not scored yet -- one more turn each first
    assert not after.is_terminal()


def test_skip_does_not_retrigger_scoring_without_a_new_draw():
    # Regression: SKIP touches neither pile nor face-up, so it must never
    # re-fire scoring just because the depleted condition still holds.
    state = _state(pile=("ALOA",), discard=("BARI",))
    after = _deplete_pile_and_faceup(state)
    assert after._scoring_count == 1
    after_skip = after.apply_action(SKIP)
    assert after_skip._scoring_count == 1


def test_reshuffle_with_empty_discard_cascades_through_remaining_scorings():
    # Regression: if the discard pile is empty at reshuffle time, the new
    # pile is empty too, so there's no future draw event that could ever
    # detect "depleted again" -- the engine must advance scoring itself
    # instead of getting permanently stuck with nothing left to draw.
    bridges = _bridges_with(("ALOA", "BARI", 0), ("ALOA", "DUDA", 0))
    state = _state(bridges=bridges, pile=("ALOA",), discard=())
    after = _deplete_pile_and_faceup(state)
    assert after._scoring_count == 3
    assert after._final_turns_remaining == 2
    assert after._scores == (3.0, 0.0)  # +1 (round 1) and +2 (round 2), both to player 0
    assert after._pile == ()
    assert after._face_up == (None, None, None)


def test_final_scoring_awards_exact_island_difference():
    bridges = _bridges_with(
        ("ALOA", "BARI", 0),
        ("ALOA", "DUDA", 0),
        ("HUNA", "LALE", 0),
        ("IFFI", "LALE", 0),
        ("BARI", "COCO", 0),
        ("COCO", "FAAA", 0),
        ("COCO", "GOLA", 0),
    )
    state = _state(
        bridges=bridges,
        current_player=1,
        scoring_count=3,
        final_turns_remaining=1,
        previous_turn_was_skip=False,
    )
    after = state.apply_action(SKIP)
    assert after.is_terminal()
    # player 0 controls ALOA, LALE, COCO (3); player 1 controls 0 -> +3
    assert after.returns() == [3.0, -3.0]


def test_winner_is_the_higher_total_score():
    state = _state(scores=(3.0, 1.0), scoring_count=3, final_turns_remaining=0)
    assert state.winner() == 0


def test_tiebreak_falls_back_to_final_round_winner():
    # Equal totals overall; player 1 wins the final round specifically
    # (majority on ALOA: 2 of its 3 lines).
    state = _state(
        scores=(2.0, 1.0),
        scoring_count=3,
        final_turns_remaining=1,
        current_player=0,
        bridges=_bridges_with(("ALOA", "BARI", 1), ("ALOA", "DUDA", 1)),
    )
    after = state.apply_action(SKIP)
    assert after.is_terminal()
    assert after._scores == (2.0, 2.0)  # tied overall
    assert after.returns() == [0.0, 0.0]  # zero-sum payoff is genuinely tied
    assert after.winner() == 1  # but player 1 won the final round


def test_tiebreak_falls_back_to_bridge_count_when_final_round_is_also_tied():
    # Equal totals overall, and final round is also a tie (no islands
    # change hands) -- fall back to whoever has more bridges on the board.
    state = _state(
        scores=(1.0, 1.0),
        scoring_count=3,
        final_turns_remaining=1,
        current_player=0,
        bridges=_bridges_with(("ALOA", "BARI", 0)),
    )
    after = state.apply_action(SKIP)
    assert after.is_terminal()
    assert after._scores == (1.0, 1.0)
    assert after.winner() == 0  # only player 0 has a bridge on the board


def test_no_winner_when_everything_is_tied():
    state = _state(scores=(1.0, 1.0), scoring_count=3, final_turns_remaining=1, current_player=0)
    after = state.apply_action(SKIP)
    assert after.is_terminal()
    assert after.winner() is None


def test_winner_raises_before_terminal():
    state = KahunaGame().new_initial_state()
    with pytest.raises(RuntimeError):
        state.winner()


def test_premature_end_when_a_player_has_zero_bridges_in_round_2_or_later():
    pos = BRIDGES.index(("ELAI", "HUNA"))
    state = _state(
        # player 0 has an unrelated bridge elsewhere, so they don't already
        # have 0 bridges before player 1's only bridge gets removed below.
        bridges=_bridges_with(("ALOA", "BARI", 0), ("ELAI", "HUNA", 1)),
        hands=(("ELAI", "HUNA"), ()),
        scoring_count=1,
    )
    after = state.apply_action(REMOVE_AB_BASE + pos)
    assert after.is_terminal()
    assert after.returns() == [1.0, -1.0]
    assert after.winner() == 0


def test_final_scoring_tie_awards_no_points():
    state = _state(scoring_count=3, final_turns_remaining=1, current_player=0)
    after = state.apply_action(SKIP)
    assert after.is_terminal()
    assert after._scores == (0.0, 0.0)


# --- terminal-state guards ------------------------------------------------


def test_legal_actions_on_terminal_state_is_empty():
    state = _state(premature_winner=0)
    assert state.legal_actions() == []


def test_legal_actions_raises_during_a_pending_chance_node():
    state = _state(pile=("ALOA",), pending=("hand0",), pending_reason="turn")
    with pytest.raises(RuntimeError):
        state.legal_actions()


def test_current_player_raises_on_terminal_state():
    state = _state(premature_winner=0)
    with pytest.raises(RuntimeError):
        state.current_player()


def test_chance_outcomes_empty_when_not_pending():
    state = _state()
    assert state.chance_outcomes() == []


def test_premature_end_does_not_apply_in_round_1():
    pos = BRIDGES.index(("ELAI", "HUNA"))
    state = _state(
        bridges=_bridges_with(("ELAI", "HUNA", 1)),
        hands=(("ELAI", "HUNA"), ()),
        scoring_count=0,
    )
    after = state.apply_action(REMOVE_AB_BASE + pos)
    assert not after.is_terminal()


# --- determinism / full playthrough ---------------------------------------


def test_determinism_under_fixed_seed():
    def run(seed: int) -> list[float]:
        return _random_playthrough(KahunaGame().new_initial_state(), random.Random(seed)).returns()

    assert run(7) == run(7)


def test_full_playthrough_is_terminal_and_zero_sum():
    final = _random_playthrough(KahunaGame().new_initial_state(), random.Random(1))
    assert final.is_terminal()
    assert sum(final.returns()) == pytest.approx(0.0)


def test_returns_before_terminal_raises():
    state = KahunaGame().new_initial_state()
    with pytest.raises(RuntimeError):
        state.returns()


def test_spec_matches_rules_md():
    spec = KahunaGame().spec()
    assert spec.num_players == 2
    assert spec.perfect_information is False
    assert spec.has_chance is True
    assert spec.zero_sum is True
    assert spec.num_distinct_actions == 152


def test_information_state_key_hides_opponent_hand():
    a = _state(hands=(("ALOA",), ("BARI",)))
    b = _state(hands=(("ALOA",), ("COCO",)))
    assert a.information_state_key(0) == b.information_state_key(0)


def test_information_state_tensor_shape_is_stable():
    state = _state(hands=(("ALOA",), ()))
    assert state.information_state_tensor(0).shape == state.information_state_tensor(1).shape
