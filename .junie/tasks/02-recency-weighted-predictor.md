# Task 02: Make the opponent predictor beat the baseline properly

## Why

Task 01 measured the opponent next-action predictor on the 2026 season (`docs/results/predictor-backtest.json`):
top-3 bans 15.8% against 13.0% for "league popularity", picks 14.1% against 13.5%. That edge is too small to show coaches
with a straight face. The likely cause: `stats.rank_candidates` weights every game since January 2025 equally, so last
season's meta and old rosters drown out what a team does now.

## What to build

Work only in `planner/stats.py`, `planner/backtest.py` and `tests/`. **Do not edit `planner/api.py` or anything in `web/`**:
another change is in progress there. Keep the live board and the backtest on one shared scoring function, as now.

1. **Recency weighting.** Each past draft action counts with weight `0.5 ** (age_days / half_life_days)`, where age is
   measured from the date being predicted. Apply it to both the team model and the league-popularity baseline (a fair comparison).
2. **Blend with the league prior.** Score = `w * team_share + (1 - w) * league_share`, where each share is the recency-weighted
   share within that team's (or the league's) history for the same action and phase. Keep the same-game-number bonus as an
   option and test whether it helps.
3. **Tune without touching the test set.** Choose `half_life_days`, `w` and whether to keep the game-number bonus on a
   **validation** window: holdout games from 2025-07-01 to 2025-12-31, with history before each game as usual. Only then
   run the 2026 test once with the chosen values. Record the grid, the validation scores and the chosen values in the JSON.
   Suggested grid: half-life 14, 30, 60, 120, 365 days; `w` 0, 0.25, 0.5, 0.75, 1.
4. **Report.** `docs/results/predictor-backtest.json` keeps its current shape (the board reads it) and gains a
   `tuning` section. Print validation and test tables. Keep the old unweighted predictor as a second baseline in the output,
   so the improvement is visible.
5. **Live predictions** in `predict_next` use the chosen parameters (read them from the JSON if present, else sensible
   defaults), with `before` still supported.
6. **Tests:** recency weights (a 1-day-old action outweighs a 1-year-old one), the blend at `w = 0` and `w = 1`, and that
   tuning never reads games on or after the test cutoff. Synthetic data only.

## Done when

- `uv run pytest` passes; `uv run python -m planner.backtest` runs in a few minutes or less.
- Report the 2026 top-3 hit rates for bans and picks: tuned model, league-popularity baseline (recency-weighted) and the old
  unweighted model. If the tuned model still does not clearly beat the baseline, say so plainly; that is a valid result.
- Update the tracker line for the predictor hit rate with the new numbers.
