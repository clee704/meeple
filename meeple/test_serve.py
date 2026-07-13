"""End-to-end tests of the web backend over HTTP. This module sits at the
package top level (like `serve.py` itself) because it deliberately spans the
seam: it drives the generic `meeple.web` app with the real registered games."""

import random
import time

import pytest
import torch
from fastapi.testclient import TestClient

import meeple.games  # noqa: F401 — side effect: registers games + views
from meeple.framework import registry
from meeple.framework.game import Game, State
from meeple.framework.spec import GameSpec
from meeple.framework.view import GameView
from meeple.web.app import FrontendBuildMissingError, create_app
from meeple.web.matches import _EVICT_IDLE_SECONDS, MatchStore, UnknownMatchError


class _ThreeSeatState(State):
    def legal_actions(self) -> list[int]:
        return [0]

    def apply_action(self, action: int) -> State:
        return self

    def is_terminal(self) -> bool:
        return False

    def returns(self) -> list[float]:
        return [0.0, 0.0, 0.0]

    def current_player(self) -> int:
        return 0

    def chance_outcomes(self) -> list[tuple[int, float]]:
        return []

    def information_state_tensor(self, player: int) -> torch.Tensor:
        return torch.zeros(0)

    def information_state_key(self, player: int) -> str:
        return f"p{player}"


class _ThreeSeatGame(Game):
    def new_initial_state(self) -> State:
        return _ThreeSeatState()

    def spec(self) -> GameSpec:
        return GameSpec(
            num_players=3,
            perfect_information=True,
            has_chance=False,
            zero_sum=False,
            num_distinct_actions=1,
            action_names=("noop",),
        )


class _ThreeSeatView(GameView):
    def observation(self, state: State, viewer: int) -> dict:
        return {"viewer": viewer}

    def action_metadata(self, action: int) -> dict:
        return {"kind": "noop"}


@pytest.fixture
def store():
    return MatchStore()


@pytest.fixture
def client(store):
    return TestClient(create_app(store, frontend_dist=None))


def _create(client, game_id="kuhn", **body):
    resp = client.post("/api/matches", json={"game_id": game_id, **body})
    assert resp.status_code == 201
    return resp.json()


def _seed(store, game_id="kahuna", seed=1, seat=0):
    """Create a fixed-deal match directly on the store (the HTTP API accepts no
    client seed) and return the create-response shape the tests consume."""
    match, token = store.create(game_id, seed=seed, creator_seat=seat)
    return {"match_id": match.match_id, "join_code": match.join_code, "token": token, "seat": seat}


def _join(client, join_code):
    resp = client.post("/api/matches/join", json={"join_code": join_code})
    assert resp.status_code == 200
    return resp.json()


def _state(client, match_id, token, **params):
    resp = client.get(
        f"/api/matches/{match_id}/state", params=params, headers={"X-Seat-Token": token}
    )
    assert resp.status_code == 200
    return resp.json()


def _act(client, match_id, token, action):
    return client.post(
        f"/api/matches/{match_id}/actions",
        json={"action": action},
        headers={"X-Seat-Token": token},
    )


def _leave(client, match_id, token):
    return client.post(f"/api/matches/{match_id}/leave", headers={"X-Seat-Token": token})


def _play_to_finish(client, match_id, tokens, rng=None, max_steps=10_000):
    """Drive a 2-seat match to the end over HTTP; returns the final envelopes."""
    envs = [_state(client, match_id, t) for t in tokens]
    steps = 0
    while any(e["status"] == "in_progress" for e in envs):
        mover = next(s for s, e in enumerate(envs) if e["your_turn"])
        legal = [la["action"] for la in envs[mover]["legal_actions"]]
        choice = rng.choice(legal) if rng else legal[0]
        resp = _act(client, match_id, tokens[mover], choice)
        assert resp.status_code == 200
        envs = [_state(client, match_id, t) for t in tokens]
        steps += 1
        assert steps < max_steps, "match did not terminate"
    return envs


def test_lists_games_with_views(client):
    games = {g["game_id"]: g for g in client.get("/api/games").json()}
    assert set(games) == {"kuhn", "kahuna"}
    assert games["kahuna"]["num_players"] == 2
    # Seat labels ride along from the game meta (none for kuhn).
    assert games["kahuna"]["seat_names"] == ["Black", "White"]
    assert games["kuhn"]["seat_names"] is None


def test_create_then_waiting_state(client):
    created = _create(client)
    env = _state(client, created["match_id"], created["token"])
    assert env["status"] == "waiting"
    assert env["your_turn"] is False
    assert env["to_move"] is None
    assert env["observation"] == {}
    assert env["legal_actions"] == []
    assert "meta" in env  # initial fetch bootstraps the renderer
    assert env["turn_count"] == 1
    assert env["elapsed_seconds"] == 0.0  # the clock doesn't run while waiting
    assert env["turn_elapsed_seconds"] == 0.0


@pytest.mark.parametrize("game_id", ["kuhn", "kahuna"])
def test_waiting_state_hides_deal_dependent_observation(client, game_id):
    created = _create(client, game_id=game_id)
    waiting = _state(client, created["match_id"], created["token"])
    assert waiting["status"] == "waiting"
    assert waiting["observation"] == {}

    joined = _join(client, created["join_code"])
    started = _state(client, created["match_id"], joined["token"])
    assert started["status"] == "in_progress"
    assert started["observation"] != {}


def test_join_assigns_seat_1_then_match_is_full(client):
    created = _create(client)
    joined = _join(client, created["join_code"])
    assert joined["seat"] == 1
    assert joined["match_id"] == created["match_id"]
    assert (
        client.post("/api/matches/join", json={"join_code": created["join_code"]}).status_code
        == 409
    )
    assert client.post("/api/matches/join", json={"join_code": "XXXXX"}).status_code == 404


def test_join_response_keeps_invite_code_while_three_player_match_waits(client):
    game_id = "three-seat-web-stub"
    registry.register(game_id, _ThreeSeatGame)
    registry.register_view(game_id, _ThreeSeatView)
    try:
        created = _create(client, game_id=game_id)
        joined = _join(client, created["join_code"])
        assert joined["seat"] == 1
        assert joined["match_id"] == created["match_id"]
        assert joined["join_code"] == created["join_code"]

        waiting = _state(client, created["match_id"], joined["token"])
        assert waiting["status"] == "waiting"
        assert waiting["observation"] == {}
    finally:
        registry._VIEW_REGISTRY.pop(game_id, None)
        registry._REGISTRY.pop(game_id, None)


def test_unknown_request_fields_are_rejected(client):
    # Version-skew guard: a server that doesn't know a field must say so
    # (422), not silently drop it (e.g. an old server ignoring `seat`).
    resp = client.post("/api/matches", json={"game_id": "kahuna", "bogus": 1})
    assert resp.status_code == 422


def test_creator_can_pick_their_seat(client):
    created = _create(client, game_id="kahuna", seat=1)
    assert created["seat"] == 1
    assert _join(client, created["join_code"])["seat"] == 0
    resp = client.post("/api/matches", json={"game_id": "kahuna", "seat": 2})
    assert resp.status_code == 422


def test_history_names_the_faceup_card_taken(client):
    created = _create(client, game_id="kahuna")
    match_id, token0 = created["match_id"], created["token"]
    token1 = _join(client, created["join_code"])["token"]
    before = _state(client, match_id, token0)["observation"]["face_up"][0]
    env = _act(client, match_id, token0, 136).json()  # 136 = take face-up slot 0
    entry = env["history"][-1]["meta"]
    assert entry == {"kind": "take_faceup", "slot": 0, "card": before}
    # The opponent's log names it too — the slot was public to both players.
    assert _state(client, match_id, token1)["history"][-1]["meta"] == entry


def test_create_rejects_a_client_supplied_seed(client):
    # A chosen seed would let the creator reconstruct the opponent's hidden
    # hand, so the deal must not be client-controllable (unknown field → 422).
    resp = client.post("/api/matches", json={"game_id": "kahuna", "seed": 1})
    assert resp.status_code == 422


def test_auth_rejections(client):
    created = _create(client)
    match_id = created["match_id"]
    resp = client.get(f"/api/matches/{match_id}/state", headers={"X-Seat-Token": "forged"})
    assert resp.status_code == 403
    resp = client.get(f"/api/matches/{match_id}/state")  # missing header
    assert resp.status_code == 422
    resp = client.get("/api/matches/nope/state", headers={"X-Seat-Token": "t"})
    assert resp.status_code == 404


def test_out_of_turn_and_illegal_actions_are_409(client):
    created = _create(client)
    match_id, token0 = created["match_id"], created["token"]
    # Match still waiting: no action is accepted, even from the creator.
    assert _act(client, match_id, token0, 0).status_code == 409

    token1 = _join(client, created["join_code"])["token"]
    envs = [_state(client, match_id, t) for t in (token0, token1)]
    mover = next(s for s, e in enumerate(envs) if e["your_turn"])
    waiter = 1 - mover
    tokens = (token0, token1)
    assert _act(client, match_id, tokens[waiter], 0).status_code == 409
    resp = _act(client, match_id, tokens[mover], 999_999)
    assert resp.status_code == 409
    assert "not legal" in resp.json()["detail"]


def test_leave_forfeits_an_in_progress_match(client):
    created = _create(client)
    match_id, token0 = created["match_id"], created["token"]
    token1 = _join(client, created["join_code"])["token"]

    resp = _leave(client, match_id, token0)
    assert resp.status_code == 200
    quitter = resp.json()
    assert quitter["status"] == "finished"
    assert quitter["forfeited_by"] == 0
    assert quitter["result"] == {"scores": [-1.0, 1.0], "winner": 1}

    # The remaining player sees the same outcome on their next poll.
    opponent = _state(client, match_id, token1)
    assert opponent["status"] == "finished"
    assert opponent["forfeited_by"] == 0
    assert opponent["result"] == {"scores": [-1.0, 1.0], "winner": 1}

    # No further actions or a second leave are accepted once finished.
    assert _act(client, match_id, token1, 0).status_code == 409
    assert _leave(client, match_id, token1).status_code == 409


def test_leave_while_waiting_closes_the_match_to_new_joiners(client):
    created = _create(client)
    match_id, token0 = created["match_id"], created["token"]
    resp = _leave(client, match_id, token0)
    assert resp.status_code == 200
    env = resp.json()
    assert env["status"] == "finished"
    assert env["observation"] == {}
    # No opponent ever joined, so there's no one to name a winner over —
    # unlike an in-progress forfeit, this must carry no fabricated result.
    assert env["forfeited_by"] is None
    assert env["result"] is None
    resp = client.post("/api/matches/join", json={"join_code": created["join_code"]})
    assert resp.status_code == 404


def test_leave_partially_filled_lobby_frees_only_that_seat(client):
    game_id = "three-seat-web-stub"
    registry.register(game_id, _ThreeSeatGame)
    registry.register_view(game_id, _ThreeSeatView)
    try:
        created = _create(client, game_id=game_id)
        joined = _join(client, created["join_code"])

        left = _leave(client, created["match_id"], joined["token"])
        assert left.status_code == 200
        assert left.json()["status"] == "waiting"
        assert left.json()["observation"] == {}

        replacement = _join(client, created["join_code"])
        final_join = _join(client, created["join_code"])
        assert replacement["seat"] == joined["seat"]
        assert final_join["seat"] == 2
        assert _state(client, created["match_id"], created["token"])["status"] == "in_progress"
    finally:
        registry._VIEW_REGISTRY.pop(game_id, None)
        registry._REGISTRY.pop(game_id, None)


def test_leave_rejects_bad_token(client):
    created = _create(client)
    resp = _leave(client, created["match_id"], "forged")
    assert resp.status_code == 403


def test_turn_count_advances_when_the_turn_passes(client, store):
    # Seed 1: seat 0 moves first holding BARI, and BARI-FAAA (bridge_pos 6)
    # is open — action 6 is place(6, using card a=BARI); 135 is draw-blind.
    created = _seed(store, "kahuna", seed=1)
    match_id, token0 = created["match_id"], created["token"]
    token1 = _join(client, created["join_code"])["token"]

    env = _state(client, match_id, token0)
    assert env["turn_count"] == 1
    assert env["elapsed_seconds"] >= 0.0

    # Playing a card keeps the turn; drawing passes it.
    env = _act(client, match_id, token0, 6).json()
    assert env["turn_count"] == 1
    env = _act(client, match_id, token0, 135).json()
    assert env["turn_count"] == 2
    assert _state(client, match_id, token1)["turn_count"] == 2


def test_turn_clock_restarts_when_the_turn_passes():
    store = MatchStore()
    match, _token = store.create("kahuna", seed=1)
    store.join(match.join_code)
    # Backdate the running turn: a poll must report the elapsed time (this
    # is what survives a page refresh) …
    match.turn_started_at -= 100.0
    assert match.envelope(0, include_meta=False)["turn_elapsed_seconds"] >= 100.0
    assert match.envelope(0, include_meta=False)["elapsed_seconds"] < 100.0
    # … and passing the turn (135 = draw-blind, see above) restarts it.
    match.apply(0, 135)
    assert match.envelope(0, include_meta=False)["turn_elapsed_seconds"] < 100.0


def test_kuhn_playthrough_and_polling(client):
    created = _create(client)
    match_id, token0 = created["match_id"], created["token"]
    token1 = _join(client, created["join_code"])["token"]

    env = _state(client, match_id, token0)
    unchanged = _state(client, match_id, token0, since=env["version"])
    assert unchanged == {"changed": False, "version": env["version"]}

    final0, final1 = _play_to_finish(client, match_id, (token0, token1))
    # First-legal-action play is pass/pass: a showdown.
    assert final0["status"] == final1["status"] == "finished"
    assert final0["result"]["cards"] is not None
    assert final0["result"] == final1["result"]
    assert [h["meta"]["kind"] for h in final0["history"]] == ["pass", "pass"]
    assert final0["turn_count"] == 2  # one action per Kuhn turn; terminal doesn't add one
    # A poll with the old version now returns the full envelope again.
    assert _state(client, match_id, token0, since=env["version"])["status"] == "finished"


def test_kahuna_playthrough_hides_opponent_privates(client):
    created = _create(client, game_id="kahuna")
    match_id, token0 = created["match_id"], created["token"]
    token1 = _join(client, created["join_code"])["token"]

    env = _state(client, match_id, token0)
    assert set(env["meta"]) == {"islands", "bridges", "majority"}

    rng = random.Random(3)
    finals = _play_to_finish(client, match_id, (token0, token1), rng=rng)
    for env in finals:
        obs = env["observation"]
        assert isinstance(obs["opponent_hand_count"], int)
        assert "opponent_hand" not in obs  # the other hand is never serialized
        assert env["result"]["winner"] in (0, 1, None)
        assert len(env["result"]["points"]) == 2


def test_same_seed_and_actions_give_identical_envelopes(client, store):
    ids = [_seed(store, "kahuna", seed=42) for _ in range(2)]
    tokens = []
    for created in ids:
        tokens.append((created["token"], _join(client, created["join_code"])["token"]))

    for _ in range(30):
        envs = [
            [_state(client, c["match_id"], t) for t in toks]
            for c, toks in zip(ids, tokens, strict=True)
        ]
        for seat in (0, 1):
            for env in (envs[0][seat], envs[1][seat]):
                env.pop("elapsed_seconds")  # wall-clock, inherently run-specific
                env.pop("turn_elapsed_seconds")
            assert envs[0][seat] == envs[1][seat]
        if envs[0][0]["status"] != "in_progress":
            break
        mover = next(s for s, e in enumerate(envs[0]) if e["your_turn"])
        action = min(la["action"] for la in envs[0][mover]["legal_actions"])
        for c, toks in zip(ids, tokens, strict=True):
            assert _act(client, c["match_id"], toks[mover], action).status_code == 200


def test_serve_module_wires_the_registered_app(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>MeepleMind</h1>")

    import meeple.serve

    app = meeple.serve.make_app(frontend_dist=dist)
    client = TestClient(app)
    assert app.title == "MeepleMind"
    assert client.get("/").text == "<h1>MeepleMind</h1>"
    games = {g["game_id"] for g in client.get("/api/games").json()}
    assert games == {"kuhn", "kahuna"}


def test_browser_server_fails_loudly_without_frontend_build(tmp_path, store):
    missing = tmp_path / "dist"
    with pytest.raises(FrontendBuildMissingError, match="npm run build"):
        create_app(store, frontend_dist=missing)


def test_cli_reports_missing_frontend_build(monkeypatch):
    import meeple.serve

    def fail():
        raise FrontendBuildMissingError("missing frontend")

    monkeypatch.setattr(meeple.serve, "make_app", fail)
    with pytest.raises(SystemExit, match="missing frontend"):
        meeple.serve.main()


def test_idle_matches_are_evicted_on_the_next_create(store, monkeypatch):
    stale, _token = store.create("kuhn")
    now = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: now + _EVICT_IDLE_SECONDS + 1)
    fresh, _token2 = store.create("kuhn")
    with pytest.raises(UnknownMatchError):
        store.get(stale.match_id)
    # The just-created match is inside its TTL and survives the sweep.
    assert store.get(fresh.match_id) is fresh


def test_polling_sends_only_history_entries_newer_than_since(client, store):
    created = _seed(store)
    joined = _join(client, created["join_code"])
    match_id = created["match_id"]
    tokens = [created["token"], joined["token"]]
    env = _state(client, match_id, tokens[0])
    first = env["legal_actions"][0]["action"]
    assert _act(client, match_id, tokens[0], first).status_code == 200
    seen = _state(client, match_id, tokens[0])
    assert seen["history_from"] == 0  # a fresh fetch always gets everything
    mover = seen["to_move"]
    mover_env = _state(client, match_id, tokens[mover])
    second = mover_env["legal_actions"][0]["action"]
    assert _act(client, match_id, tokens[mover], second).status_code == 200
    delta = _state(client, match_id, tokens[0], since=seen["version"])
    full = _state(client, match_id, tokens[0])
    assert delta["history_from"] == len(seen["history"])
    assert len(delta["history"]) >= 1
    assert full["history_from"] == 0
    assert full["history"][delta["history_from"] :] == delta["history"]
