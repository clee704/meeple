"""In-memory match store: lifecycle (create → join → play → finish), per-seat
auth tokens, and the per-viewer state envelope the API serves. Matches are
lost on restart — fine for the local/LAN scope; persistence would swap in
behind the same `MatchStore` methods."""

import random
import secrets
import time
from dataclasses import dataclass, field

from meeple.framework import registry
from meeple.framework.chance import resolve_chance
from meeple.framework.game import Game, State
from meeple.framework.view import GameView

# Join codes avoid easily-confused characters (0/O, 1/I/L).
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 5


class MatchError(Exception):
    """Base for domain failures the API layer maps onto HTTP errors."""


class UnknownMatchError(MatchError):
    pass


class BadTokenError(MatchError):
    pass


class MatchFullError(MatchError):
    pass


class NotYourTurnError(MatchError):
    pass


class IllegalActionError(MatchError):
    pass


@dataclass
class Match:
    match_id: str
    join_code: str
    game_id: str
    game: Game
    view: GameView
    state: State
    rng: random.Random
    tokens: list[str | None]
    # One history per seat: entries are pre-masked by `describe_action` at
    # append time, so a viewer's log never holds what they may not see.
    histories: list[list[dict]]
    version: int = 1
    forfeited_by: int | None = None
    canceled: bool = False
    # Wall-clock/turn bookkeeping for the UI. A "turn" is a stretch of
    # actions by one player: it advances when `to_move` changes hands.
    turn_count: int = 1
    started_at: float | None = None  # monotonic; set when the last seat fills
    turn_started_at: float | None = None  # monotonic; reset when the turn passes
    finished_at: float | None = None

    @property
    def status(self) -> str:
        if self.canceled or self.forfeited_by is not None:
            return "finished"
        if None in self.tokens:
            return "waiting"
        return "finished" if self.state.is_terminal() else "in_progress"

    def seat_for_token(self, token: str) -> int:
        for seat, seat_token in enumerate(self.tokens):
            if seat_token is not None and secrets.compare_digest(seat_token, token):
                return seat
        raise BadTokenError("bad seat token")

    def leave(self, seat: int) -> None:
        """`seat` leaves the match. If no opponent ever joined there is no one
        to award a win to, so the match is simply canceled; otherwise `seat`
        forfeits and the remaining seat(s) win."""
        if self.status == "waiting":
            self.canceled = True
        elif self.status == "in_progress":
            self.forfeited_by = seat
        else:
            raise IllegalActionError(f"match is {self.status}, cannot be left")
        self.finished_at = time.monotonic()
        self.version += 1

    def apply(self, seat: int, action: int) -> None:
        if self.status != "in_progress":
            raise NotYourTurnError(f"match is {self.status}, not in progress")
        if self.state.current_player() != seat:
            raise NotYourTurnError(f"it is seat {self.state.current_player()}'s turn")
        # The server, not the client, is authoritative about legality.
        if action not in self.state.legal_actions():
            raise IllegalActionError(f"action {action} is not legal now")
        # Descriptions read the pre-action state (e.g. which face-up card a
        # draw is about to take), so build them before applying.
        entries = [
            {"actor": seat, "meta": self.view.describe_action(action, viewer, seat, self.state)}
            for viewer in range(len(self.tokens))
        ]
        self.state = self.state.apply_action(action)
        for viewer, entry in enumerate(entries):
            self.histories[viewer].append(entry)
        self.state = resolve_chance(self.state, self.rng)
        if self.state.is_terminal():
            self.finished_at = time.monotonic()
        elif self.state.current_player() != seat:
            self.turn_count += 1
            self.turn_started_at = time.monotonic()
        self.version += 1

    def envelope(self, seat: int, include_meta: bool) -> dict:
        spec = self.game.spec()
        in_progress = self.status == "in_progress"
        your_turn = in_progress and self.state.current_player() == seat
        env = {
            "version": self.version,
            "game_id": self.game_id,
            "seat": seat,
            "status": self.status,
            "to_move": self.state.current_player() if in_progress else None,
            "your_turn": your_turn,
            "observation": self.view.observation(self.state, seat),
            "legal_actions": [
                {"action": a, "name": spec.action_names[a], "meta": self.view.action_metadata(a)}
                for a in (self.state.legal_actions() if your_turn else [])
            ],
            "history": list(self.histories[seat]),
            "result": self._result(),
            "forfeited_by": self.forfeited_by,
            "turn_count": self.turn_count,
            "elapsed_seconds": self._elapsed_seconds(),
            "turn_elapsed_seconds": self._since(self.turn_started_at),
        }
        if include_meta:
            env["meta"] = self.view.game_meta()
        return env

    def _elapsed_seconds(self) -> float:
        return self._since(self.started_at)

    def _since(self, start: float | None) -> float:
        if start is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else time.monotonic()
        return end - start

    def _result(self) -> dict | None:
        if self.canceled:
            return None  # never started: no scores, no winner
        if self.forfeited_by is not None:
            # A forfeit isn't a game-engine outcome, so it's scored here
            # rather than via the view: the forfeiting seat loses outright,
            # and every remaining seat ties for the win. Same
            # highest-score-wins/tie-is-a-draw convention as GameView.result.
            num_players = len(self.tokens)
            scores = [-1.0 if p == self.forfeited_by else 1.0 for p in range(num_players)]
            best = max(scores)
            winners = [p for p, s in enumerate(scores) if s == best]
            winner = winners[0] if len(winners) == 1 else None
            return {"scores": scores, "winner": winner}
        return self.view.result(self.state) if self.state.is_terminal() else None


@dataclass
class MatchStore:
    _matches: dict[str, Match] = field(default_factory=dict)
    _by_code: dict[str, str] = field(default_factory=dict)

    def create(
        self, game_id: str, seed: int | None = None, creator_seat: int = 0
    ) -> tuple[Match, str]:
        view = registry.make_view(game_id)  # KeyError for games without a web view
        game = registry.make(game_id)
        rng = random.Random(secrets.randbits(64) if seed is None else seed)
        num_players = game.spec().num_players
        if not 0 <= creator_seat < num_players:
            raise ValueError(f"seat must be in 0..{num_players - 1}, got {creator_seat}")
        token = secrets.token_urlsafe(16)
        tokens: list[str | None] = [None] * num_players
        tokens[creator_seat] = token
        match = Match(
            match_id=secrets.token_urlsafe(9),
            join_code=self._new_join_code(),
            game_id=game_id,
            game=game,
            view=view,
            state=resolve_chance(game.new_initial_state(), rng),
            rng=rng,
            tokens=tokens,
            histories=[[] for _ in range(num_players)],
        )
        self._matches[match.match_id] = match
        self._by_code[match.join_code] = match.match_id
        return match, token

    def join(self, join_code: str) -> tuple[Match, int, str]:
        match_id = self._by_code.get(join_code.strip().upper())
        if match_id is None:
            raise UnknownMatchError(f"no match with join code {join_code!r}")
        match = self._matches[match_id]
        if match.canceled or match.forfeited_by is not None:
            raise UnknownMatchError(f"match with join code {join_code!r} is no longer available")
        if None not in match.tokens:
            raise MatchFullError("all seats are taken")
        seat = match.tokens.index(None)
        token = secrets.token_urlsafe(16)
        match.tokens[seat] = token
        if None not in match.tokens:
            match.started_at = time.monotonic()  # the clock runs on play, not waiting
            match.turn_started_at = match.started_at
        match.version += 1  # wakes the creator's poll: status flips to in_progress
        return match, seat, token

    def get(self, match_id: str) -> Match:
        try:
            return self._matches[match_id]
        except KeyError:
            raise UnknownMatchError(f"unknown match {match_id!r}") from None

    def _new_join_code(self) -> str:
        while True:
            code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
            if code not in self._by_code:
                return code
