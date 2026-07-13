"""The web-facing SPI a game implements so the generic backend and a
per-game frontend renderer can present it. Deliberately separate from
`State` (which serves solvers): a game without a view is still fully
playable by AI/eval code — it just doesn't appear in the web lobby.

Everything returned here must be JSON-serializable, and `observation`/
`describe_action` must contain ONLY what `viewer` is allowed to see —
the server sends their output verbatim to that player's browser."""

from abc import ABC, abstractmethod

from meeple.framework.game import Action, State


def winner_from_scores(scores: list[float]) -> int | None:
    """The default winner convention: highest score wins, a tie is a draw
    (`None`). Shared so every scores-only verdict (natural finishes without
    a game tiebreak, the web layer's forfeits) stays on one algorithm."""
    best = max(scores)
    winners = [p for p, s in enumerate(scores) if s == best]
    return winners[0] if len(winners) == 1 else None


class GameView(ABC):
    @abstractmethod
    def observation(self, state: State, viewer: int) -> dict:
        """What `viewer` sees of `state`: their own hand by identity, the
        opponent's hidden information only in aggregate (counts etc.)."""

    @abstractmethod
    def action_metadata(self, action: Action) -> dict:
        """Structured, static description of an action (kind, targets, cost
        ...) that a renderer maps clicks onto. Only ever sent to the player
        to move alongside `legal_actions`, so it needs no masking."""

    def describe_action(self, action: Action, viewer: int, actor: int, state: State) -> dict:
        """A move-history entry as seen by `viewer`. `state` is the state the
        action is about to be applied to, so a description can name what the
        action touched (e.g. which card a face-up draw took). Override when
        the raw action would leak `actor`'s hidden information (e.g. a
        face-down discard whose action id encodes the card)."""
        return self.action_metadata(action)

    def result(self, state: State) -> dict:
        """End-screen summary at a terminal state. The default declares the
        highest `returns()` entry the winner, or a draw (`None`) on a tie;
        override when the game has its own tiebreak."""
        scores = state.returns()
        return {"scores": scores, "winner": winner_from_scores(scores)}

    def game_meta(self) -> dict:
        """Static bootstrap data for the renderer (board topology etc.),
        sent once per match."""
        return {}

    def seat_names(self) -> list[str] | None:
        """Lobby seat labels indexed by seat (seat 0 moves first), or None
        when the game offers no meaningful seat choice at create time."""
        return None
