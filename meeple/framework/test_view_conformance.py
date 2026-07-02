"""SPI conformance: every game that registers a `GameView` must produce
JSON-serializable, well-formed output at every node of a real playthrough.
Game-specific privacy tests (what must NOT appear in an observation) live
with each game's own view tests."""

import json
import random

import pytest

import meeple.games  # noqa: F401 — side-effect: registers games + views
from meeple.framework import registry
from meeple.framework.chance import resolve_chance
from meeple.framework.game import CHANCE


@pytest.mark.parametrize("game_id", registry.games_with_views())
def test_view_conformance_over_a_seeded_playthrough(game_id):
    game = registry.make(game_id)
    view = registry.make_view(game_id)
    spec = game.spec()
    rng = random.Random(20260702)

    state = resolve_chance(game.new_initial_state(), rng)
    steps = 0
    while not state.is_terminal():
        actor = state.current_player()
        assert actor != CHANCE  # resolve_chance must have consumed chance nodes
        for viewer in range(spec.num_players):
            obs = json.loads(json.dumps(view.observation(state, viewer)))
            assert isinstance(obs, dict) and obs
        legal = state.legal_actions()
        assert legal
        for action in legal:
            json.dumps(view.action_metadata(action))
            for viewer in range(spec.num_players):
                json.dumps(view.describe_action(action, viewer=viewer, actor=actor))
        state = resolve_chance(state.apply_action(rng.choice(legal)), rng)
        steps += 1
        assert steps < 10_000, "playthrough did not terminate"

    result = json.loads(json.dumps(view.result(state)))
    assert len(result["scores"]) == spec.num_players
    assert result["winner"] is None or result["winner"] in range(spec.num_players)


@pytest.mark.parametrize("game_id", registry.games_with_views())
def test_action_metadata_covers_the_whole_action_space(game_id):
    view = registry.make_view(game_id)
    spec = registry.make(game_id).spec()
    for action in range(spec.num_distinct_actions):
        meta = view.action_metadata(action)
        assert isinstance(meta, dict) and "kind" in meta
