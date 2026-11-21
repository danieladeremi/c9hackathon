# Task 01: Measure the opponent-prediction hit rate

## Why

The draft board shows an opponent's likely next ban or pick (`planner/stats.py: predict_next`). Coaches, and the judges,
need to know how far to trust it. The design promises a measured hit rate shown next to the predictions
("our top-3 predicted bans were right X% of the time"). Right now it is unmeasured.

## What to build

1. **No-leakage option in `predict_next`.** Add an optional `before: date | None` parameter. When set, only games with
   `game_context.game_date < before` count, both for the champion counts and for the `games` sample size.
   Existing callers keep working unchanged.

2. **`planner/backtest.py`**, runnable as `uv run python -m planner.backtest`.
   - Test set: every complete draft (`draft_action_count = 20`) with `game_date >= 2026-01-01` (the whole 2026 season, the same holdout as the win-probability models). Make the cutoff a CLI option.
   - For each test game and each of its 20 slots: the acting team and action come from the real draft. Compute
     `predict_next(..., before=<that game's date>)`, where `unavailable` holds the champions already banned or picked earlier
     in that game plus the Fearless locks (champions picked in earlier games of the same series; use `planner.rules`).
     Skip the slot when the acting team has fewer than 10 prior games in that phase, and count how many were skipped.
     Treat a skipped ban (`champion_id` NULL) as unpredictable and leave it out.
   - Metrics: top-1, top-3 and top-5 hit rate, split by action (ban/pick) and by phase (ban1, pick1, ban2, pick2), with the
     number of slots behind each figure.
   - **Baseline**, to prove the team-specific model adds something: the same metrics for a "league popularity" predictor that
     ranks champions by how often *any* team chose them in that phase before the game date, with the same unavailability rules.
   - Output: print a readable table, and write aggregate results (no per-game rows, no champion-level data) to
     `docs/results/predictor-backtest.json`. Aggregate numbers are fine to commit.
   - Performance: 1 DuckDB connection with `threads=2`, `memory_limit='1GB'`, read-only. It should finish in a few minutes.
     If it is slow, load the test drafts once and batch the queries; do not add worker processes.

3. **Show it in the product.**
   - API: `GET /api/predictor/accuracy` returns the JSON (404 with a clear message if the backtest has not been run).
   - UI: under the "Likely {opponent} bans/picks now" list in `web/src/components/Insights.tsx`, add one line of evidence for the
     current action and phase, e.g. "Top-3 hit rate on 2026 games: 41% of 1,203 ban slots (league-popularity baseline: 29%)".
     Hide the line if no results exist. Mirror the type in `web/src/api.ts`.

4. **Tests** (`tests/test_backtest.py`): build a tiny DuckDB in `tmp_path` with hand-made `game_context` and `draft_actions`
   rows, and check that (a) `before` excludes same-day and later games, and (b) top-k hit counting and the skip rule are correct.
   Synthetic data only.

## Done when

- `uv run pytest` passes and `cd web && npx tsc -b` is clean.
- `uv run python -m planner.backtest` runs on the real data and writes `docs/results/predictor-backtest.json`.
- The board shows the hit-rate line for opponent slots.
- Tick "opponent next-action prediction hit rate" in the tracker (add the item under section 2 if it is missing),
  and report the headline numbers: team model against baseline, top-3, bans and picks.
