"""GameSpec — the static description the AI layer uses to pick a compatible
solver (CLAUDE.md's solver-compatibility matrix). Drives behavior; never
branches on a game's name (CLAUDE.md P5)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GameSpec:
    num_players: int
    perfect_information: bool
    has_chance: bool
    zero_sum: bool
    num_distinct_actions: int
    action_names: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.action_names) != self.num_distinct_actions:
            raise ValueError(
                f"action_names has {len(self.action_names)} entries, "
                f"expected num_distinct_actions={self.num_distinct_actions}"
            )
