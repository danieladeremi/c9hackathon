# C9 Draft Planner

A League of Legends draft-preparation tool for Cloud9 Kia, built for the Cloud9 x JetBrains "Sky's The Limit" hackathon (Category 2). Design: [docs/design/2026-11-19-draft-planner.md](docs/design/2026-11-19-draft-planner.md).

## Requirements

- [uv](https://docs.astral.sh/uv/) (installs Python 3.14 for you: `uv python install 3.14`)
- The hackathon's GRID data, cloned **beside** this repo (it is licensed and never committed here):

```
hackathon/
├── c9hackathon/                        ← this repo
└── stl-hackathon-2026-grid-starter/    ← GRID data
```

```bash
git clone --filter=blob:none --sparse https://github.com/cloud9esports/stl-hackathon-2026-grid-starter.git
cd stl-hackathon-2026-grid-starter && git sparse-checkout set lol meta
```

Set `STL_DATA_DIR` if the data lives elsewhere.

## Build the local database

```bash
uv sync
uv run python -m pipeline.build              # all 745 LoL series, about 3-5 minutes
uv run python -m pipeline.build --limit 20   # quick check
```

This writes `data/draft.duckdb` (gitignored). The build uses 2 worker processes at below-normal priority by default so the computer stays usable; change it with `--workers`.

Tables: `games`, `draft_actions`, `player_games` (with inferred role), `team_minutes`, `player_minutes`, plus `series` and `meta_*` copies of the starter repo's index tables.

## Run the draft board

Needs [Node.js](https://nodejs.org/) 20+ as well. In two terminals:

```bash
uv run uvicorn planner.api:app --port 8000     # API (reads data/draft.duckdb)
cd web && npm install && npm run dev           # UI on http://localhost:5173
```

Pick an opponent and a format, then click champions to fill each slot in draft order. For each slot the right-hand panel shows:

- **This slot**: the opponent's likely bans or picks when they are drafting; their most-picked champions still open when C9 bans; C9's comfort picks still open when C9 picks.
- **Opponent habits**: bans, picks and "banned against" for this game number of a series, or for all games, with sample sizes.
- **Fearless pools**: each current player's most-played champions, struck through once Fearless or this draft removes them.

Side and first pick are separate choices per game. Fearless locks every champion picked in earlier games for both teams; bans do not carry over. The series is saved in the browser, so a reload keeps it.

## Data quality report

```bash
uv run python -m pipeline.checks
```

## Tests

```bash
uv run pytest
```

Tests use a small synthetic feed; no GRID data is needed or stored.
