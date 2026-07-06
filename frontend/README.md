# MeepleMind Frontend

React + Vite app for browser play. The built files in `dist/` are served by
the FastAPI backend when running the `meeple` CLI.

## Install

```sh
npm ci
```

## Development

Run the backend on port 8000 from the repo root:

```sh
uv run meeple
```

Then run Vite from this directory:

```sh
npm run dev
```

Vite proxies `/api` to `http://localhost:8000`, so the frontend can use the
same API paths in development and production.

## Checks

```sh
npm run build
npm run lint
```

These checks also run in CI. They are mirrored in pre-commit for local commits,
so run `npm ci` before `uv run pre-commit run -a`.

## Game Renderers

Per-game React renderers live in `src/games/` and are registered in
`src/games/registry.tsx`. The generic shell passes the `GameView` payloads
through unchanged; renderer code owns the game-specific observation, metadata,
history, and action UI.
