"""Web view for Kuhn poker — the deliberately tiny second implementation of
the `GameView` SPI (Kahuna being the real one), so the SPI always has two
consumers keeping it honest."""

from meeple.framework.game import Action, State
from meeple.framework.view import GameView
from meeple.games.kuhn.engine import PASS, KuhnState

CARD_NAMES = ("J", "Q", "K")
_ACTION_KINDS = {PASS: "pass", 1: "bet"}


class KuhnView(GameView):
    def observation(self, state: State, viewer: int) -> dict:
        assert isinstance(state, KuhnState)
        return {
            "card": CARD_NAMES[state._cards[viewer]],
            "history": [_ACTION_KINDS[0 if ch == "p" else 1] for ch in state._history],
            "to_move": None if state.is_terminal() else state.current_player(),
        }

    def action_metadata(self, action: Action) -> dict:
        return {"kind": _ACTION_KINDS[action]}

    def result(self, state: State) -> dict:
        assert isinstance(state, KuhnState)
        result = super().result(state)
        # Only a showdown reveals both cards; a fold keeps them mucked.
        showdown = state._history in ("pp", "bb", "pbb")
        result["cards"] = [CARD_NAMES[c] for c in state._cards] if showdown else None
        return result
