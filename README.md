# MeepleMind

A **game-agnostic board-game AI platform**: one engine interface, one set of
AI algorithms (heuristic → ISMCTS/MCTS → CFR/Deep CFR), one eval harness, and
one web backend, reused across many games.

[**Kahuna**](meeple/games/kahuna/RULES.md) is game #1 (planned next: Quarto,
Splendor, Patchwork).

## Architecture

```
   AI layer (game-agnostic)            Web backend (game-agnostic)
   heuristic · MCTS · ISMCTS ·         FastAPI · queue · store · Turnstile
   tabular CFR · Deep CFR · coach          │  uses framework/registry +
        │  imports ONLY framework/         │  a per-game renderer
        └───────────────┬─────────────────┘
                        ▼
            framework/  Game · State · GameSpec · registry      ← the seam
                        ▲
        ┌───────────────┼───────────────┬──────────────┐
   games/kahuna     games/quarto     games/kuhn     OpenSpielAdapter
   (game #1)        (Phase 10)    (seam smoke-test)   (oracle only)
```

`ai/`, `eval/`, and `web/` import only `framework/`; a game is reached only
through the `Game`/`State` interface, described by a `GameSpec`, and
discovered via a registry. See [`AGENTS.md`](AGENTS.md) for the full set of
operating rules and hard gates, and [`PLAN.md`](PLAN.md) for the phased
roadmap.

## Quickstart

```bash
uv sync                  # install deps into .venv
npm --prefix frontend ci # install frontend deps
uv run pytest            # run tests (with coverage gate)
uv run pre-commit run -a # lint + hygiene checks
```

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for commit/PR conventions, and
[`AGENTS.md`](AGENTS.md) for the project's hard gates (rules-first game
onboarding, the framework/games seam, test requirements).
