import pytest

from meeple.framework.spec import GameSpec


def test_valid_spec_constructs():
    spec = GameSpec(
        num_players=2,
        perfect_information=False,
        has_chance=True,
        zero_sum=True,
        num_distinct_actions=2,
        action_names=("pass", "bet"),
    )
    assert spec.num_distinct_actions == len(spec.action_names)


def test_mismatched_action_names_raises():
    with pytest.raises(ValueError, match="action_names"):
        GameSpec(
            num_players=2,
            perfect_information=False,
            has_chance=True,
            zero_sum=True,
            num_distinct_actions=2,
            action_names=("pass",),
        )
