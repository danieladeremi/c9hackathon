# Guidelines for Junie: C9 Draft Planner

League of Legends draft-preparation tool for Cloud9 Kia (Cloud9 x JetBrains hackathon, Category 2).
Before a task, read `CLAUDE.md` (hackathon facts and data licence), `docs/design/2026-11-19-draft-planner.md` (design)
and `docs/design/2026-11-19-implementation-plan.md` (tracker). Tick tracker items you finish.

## Hard rules

- **Never commit GRID data or anything built from it**: no `.zst`, `.jsonl`, `.csv` extracts, `.duckdb`, `.parquet`, `.sqlite`, nothing under `data/`. The data lives in the sibling folder `../stl-hackathon-2026-grid-starter` (env `STL_DATA_DIR`) and is read in place. Derived files go in `data/` (gitignored).
- Do not commit or push. The developer reviews your diff first.
- **This runs on a laptop with little free RAM and disk.** Never start more than 2 worker processes, never decompress the corpus to disk, stream feeds line by line, and keep DuckDB connections at `threads=2` and a `memory_limit` of 1 GB or less. Try a small run (`--limit 20`) before a full one.
- Every statistic shown to a coach carries its sample size. When a sample is too small to mean anything, say so instead of showing a number.
- No Riot art, icons or sounds. Champion names as text are fine.

## Layout

| Path | What |
|---|---|
| `pipeline/` | Streams GRID feeds into `data/draft.duckdb`: `feed.py` (state merging), `extract.py`, `roles.py`, `resolve.py`, `derive.py`, `build.py`, `checks.py` |
| `planner/rules.py` | Draft order (keyed on first pick, not side) and hard Fearless rules |
| `planner/stats.py` | Read-only SQL: tendencies, pools, lane matchups, next-action prediction |
| `planner/api.py` | FastAPI app (`/api/...`) |
| `web/` | React + TypeScript (Vite) draft board; `src/api.ts` mirrors the API types |
| `tests/` | pytest; synthetic data only, never real GRID data |

DuckDB tables: `games`, `game_context` (adds event, patch, `game_date`), `draft_actions` (`seq` 1-20), `player_games` (with `role`), `team_minutes`, `player_minutes`, `lane_diffs`, `series`, `meta_*`. Cloud9 Kia's team ID is `47351`. IDs are strings.

## Commands

```bash
uv run pytest                                  # tests
uv run python -m pipeline.build --limit 20     # quick rebuild (full build: drop --limit, ~3 min)
uv run python -m pipeline.checks               # data-quality report
uv run uvicorn planner.api:app --port 8000     # API
cd web && npm run dev                          # UI on http://localhost:5173
cd web && npx tsc -b                           # type-check the UI
```

PyCharm run configurations for each of these are in `.idea/runConfigurations/`.

## Style

- Python 3.14, standard library first; DuckDB SQL for aggregation. Type hints, short docstrings that say *why*.
- Keep the API typed and mirror any response change in `web/src/api.ts`.
- Add or update tests with every change. Run `uv run pytest` and, for UI changes, `npx tsc -b` before finishing.
- Finish by listing what changed, how you verified it, and anything left undone.
