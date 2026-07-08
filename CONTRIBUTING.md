# Contributing

This is a solo/small-scale project, but commits and PRs follow fixed
conventions so history stays readable and `git bisect`/changelogs stay useful.
For the *process* rules that govern what gets built and how (gates, the
framework/games seam, rules-first game onboarding), see `AGENTS.md` first —
this file only covers commit/PR mechanics.

## Commit messages — Conventional Commits

Every commit message follows [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional scope>): <short summary, imperative mood>

<optional body — the "why", not the "what">
```

**Types:**

| Type       | Use for |
|------------|---------|
| `feat`     | a new capability (a new engine, AI algorithm, endpoint, CLI command) |
| `fix`      | a bug fix |
| `refactor` | behavior-preserving restructuring (tests green before *and* after — AGENTS.md H4) |
| `test`     | adding/fixing tests with no production-code behavior change |
| `docs`     | `RULES.md`, `PLAN.md`, `README.md`, comments-only changes |
| `chore`    | tooling, CI, dependency bumps, repo hygiene |
| `perf`     | a performance improvement with no behavior change |

**Scope** (optional) is the affected area: `kahuna`, `kuhn`, `framework`,
`ai`, `eval`, `web`, `cli`. Example: `feat(kuhn): add native engine + RULES.md`.

A commit should be one logical, green checkpoint (AGENTS.md G9) — don't
bundle a refactor with a feature (H4); split them into two commits instead.

## Branch naming

`<type>/<short-description>`, matching the commit type above, e.g.
`feat/kuhn-engine`, `fix/kahuna-cascade-bug`, `chore/ci-coverage-gate`.

## Pull requests

- **Title**: a Conventional Commits header, e.g. `feat(kahuna): implement
  engine + cascade logic`. If a PR is a single commit, the title *is* that
  commit's header.
- **Description**: what changed and why; for a new game, link the relevant
  `RULES.md` section. Note any gates touched (e.g. "resolves Kahuna
  MUST-VERIFY #2").
- Before opening: run `uv sync`, `npm --prefix frontend ci`,
  `uv run pre-commit run -a`, and `uv run pytest`. CI runs the same checks
  (ruff, vulture, deptry, import-linter, pytest + coverage gate, frontend
  build/lint) and will block merge otherwise (AGENTS.md G10).
- A phase's hard gates (RULES sign-off G1, seam G2, tests G3, eval G5) must be
  satisfied before its PR is considered done — see `AGENTS.md`.

## Local setup

```bash
uv sync                  # install deps into .venv
npm --prefix frontend ci # install frontend deps for build/lint hooks
uv run pre-commit install  # run hooks automatically on every commit
```
