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

## Tests

```bash
uv run pytest
```

Tests use a small synthetic feed; no GRID data is needed or stored.
