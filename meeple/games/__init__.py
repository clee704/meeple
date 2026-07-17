"""Registers every game with `meeple.framework.registry` on import."""

from meeple.framework import registry
from meeple.games.kahuna.engine import KahunaGame
from meeple.games.kahuna.heuristic import evaluate as kahuna_evaluate
from meeple.games.kahuna.view import KahunaView
from meeple.games.kuhn.engine import KuhnGame
from meeple.games.kuhn.view import KuhnView

registry.register("kuhn", KuhnGame)
registry.register("kahuna", KahunaGame)
registry.register_view("kuhn", KuhnView)
registry.register_view("kahuna", KahunaView)
registry.register_evaluator("kahuna", kahuna_evaluate)
