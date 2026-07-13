"""Web view for Kahuna: per-viewer observation (own hand and own face-down
discards by identity, the opponent's only by count — mirroring
`information_state_key`), structured action metadata decoded from the
engine's action layout, and a history masking rule for the one action whose
id would leak hidden information (`discard_facedown` encodes the island)."""

from meeple.framework.game import Action, State
from meeple.framework.view import GameView
from meeple.games.kahuna.engine import (
    DISCARD_BASE,
    DRAW_BLIND,
    FACEUP_BASE,
    PLACE_A_BASE,
    PLACE_B_BASE,
    REMOVE_AA_BASE,
    REMOVE_AB_BASE,
    REMOVE_BB_BASE,
    SKIP,
    KahunaState,
)
from meeple.games.kahuna.graph import BRIDGES, ISLANDS, MAJORITY


class KahunaView(GameView):
    def observation(self, state: State, viewer: int) -> dict:
        assert isinstance(state, KahunaState)
        opponent = 1 - viewer
        return {
            "bridges": list(state.bridges),
            "control": {island: state._controller(island) for island in ISLANDS},
            "hand": sorted(state.hands[viewer]),
            "opponent_hand_count": len(state.hands[opponent]),
            "face_up": list(state.face_up),
            "pile_count": len(state.pile),
            "discard": sorted(state.discard),
            "my_hidden_discards": sorted(state.hidden_discards[viewer]),
            "opponent_hidden_discard_count": len(state.hidden_discards[opponent]),
            "scores": list(state.scores),
            "scoring_count": state.scoring_count,
            # Public scoring log — one (p0, p1) pair of points awarded per
            # completed scoring round; drives the end-of-game breakdown.
            "round_points": [list(points) for points in state.round_points],
            "to_move": None if state.is_terminal() else state.to_move,
            "previous_turn_was_skip": state.previous_turn_was_skip,
            "discarded_this_turn": state.discarded_this_turn,
            "final_turns_remaining": state.final_turns_remaining,
        }

    def action_metadata(self, action: Action) -> dict:
        if PLACE_A_BASE <= action < REMOVE_AA_BASE:
            endpoint = 0 if action < PLACE_B_BASE else 1
            pos = action - (PLACE_A_BASE if endpoint == 0 else PLACE_B_BASE)
            islands = BRIDGES[pos]
            return {
                "kind": "place",
                "bridge": pos,
                "islands": list(islands),
                "spend": [islands[endpoint]],
            }
        if REMOVE_AA_BASE <= action < DRAW_BLIND:
            pos = action % len(BRIDGES)
            a, b = BRIDGES[pos]
            spend = {REMOVE_AA_BASE: [a, a], REMOVE_BB_BASE: [b, b], REMOVE_AB_BASE: [a, b]}[
                action - pos
            ]
            return {"kind": "remove", "bridge": pos, "islands": [a, b], "spend": spend}
        if action == DRAW_BLIND:
            return {"kind": "draw_blind"}
        if FACEUP_BASE <= action < SKIP:
            return {"kind": "take_faceup", "slot": action - FACEUP_BASE}
        if action == SKIP:
            return {"kind": "skip"}
        return {"kind": "discard", "island": ISLANDS[action - DISCARD_BASE]}

    def describe_action(self, action: Action, viewer: int, actor: int, state: State) -> dict:
        meta = self.action_metadata(action)
        # A face-down discard's identity is the actor's private information.
        if meta["kind"] == "discard" and viewer != actor:
            meta["island"] = None
        # Which card a face-up take grabbed is public (the slot was visible
        # to everyone), so the history can name it outright.
        if meta["kind"] == "take_faceup":
            assert isinstance(state, KahunaState)
            meta["card"] = state.face_up[meta["slot"]]
        return meta

    def result(self, state: State) -> dict:
        assert isinstance(state, KahunaState)
        return {
            "scores": state.returns(),
            "winner": state.winner(),  # RULES.md tiebreak, not returns() argmax
            "points": list(state.scores),
            "premature": state.premature_winner is not None,
        }

    def game_meta(self) -> dict:
        return {
            "islands": list(ISLANDS),
            "bridges": [list(pair) for pair in BRIDGES],
            "majority": dict(MAJORITY),
        }

    def seat_names(self) -> list[str] | None:
        # House rule for the web lobby: Black is seat 0 and moves first.
        return ["Black", "White"]
