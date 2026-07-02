"""Registers every game with `meeple.framework.registry` on import."""

from meeple.framework import registry
from meeple.games.kahuna.engine import KahunaGame
from meeple.games.kuhn.engine import KuhnGame

registry.register("kuhn", KuhnGame)
registry.register("kahuna", KahunaGame)
