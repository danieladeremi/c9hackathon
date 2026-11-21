# C9 Draft Planner: implementation plan

What to build is in [2026-11-19-draft-planner.md](2026-11-19-draft-planner.md). Hackathon rules and the data licence are in [CLAUDE.md](../../CLAUDE.md). This file is the setup guide and the tracker: tick items as they finish.

**Deadline:** 12 Jan 2027, 11:00 am Pacific. Target submission: 11 Jan 2027, to leave a day of margin.

## 0. Machine setup (on the computer the entry is built on)

All work happens on a personal machine; the entry must be solely the entrant's.

- [ ] Register on cloud9.devpost.com ("Join Hackathon"); trial codes arrive by email within 5 business days.
- [ ] Install JetBrains Toolbox, then PyCharm and WebStorm. Activate the All Products Pack code, then the AI Ultimate code.
- [ ] Install JetBrains Air in the IDE (https://www.jetbrains.com/air/ides/) and connect an agent (Junie, Claude Agent or Codex). Turn off training/retention on inputs wherever an agent offers it (data licence requirement).
- [x] Install Python 3.14 (built-in zstd), uv, Node.js LTS and git.
- [ ] Clone both repos side by side:
  ```
  mkdir hackathon && cd hackathon
  git clone https://github.com/danieladeremi/c9hackathon.git
  git clone --filter=blob:none --sparse https://github.com/cloud9esports/stl-hackathon-2026-grid-starter.git
  cd stl-hackathon-2026-grid-starter && git sparse-checkout set lol meta && cd ..
  ```
- [ ] In `c9hackathon`, set a repo-local git identity with the GitHub no-reply address (Settings > Emails on GitHub shows it):
  ```
  git config user.name "<GitHub name>"
  git config user.email "<id>+<login>@users.noreply.github.com"
  ```
- [ ] Open `c9hackathon` in PyCharm. Start an `AI_SHOWCASE.md` log now and add to it at every milestone (bonus prize, and evidence for judging criterion 1).
- [ ] Choose the licence (MIT or Apache 2.0) and add `LICENSE` at the repo root.

**Done when:** both repos are cloned side by side, the IDE opens the project with an agent connected, and `LICENSE` is committed.

## 1. Data pipeline (target 30 Nov)

Python package under `pipeline/`, run with uv, reading from `STL_DATA_DIR` (default `../stl-hackathon-2026-grid-starter`) and writing a local DuckDB file under `data/` (gitignored).

- [x] Inspect one LoL feed: first and last envelopes, all event types, how draft actions, side and first-pick selection appear. Record findings in the design doc.
- [x] Load `meta/` tables (games, rosters, teams, players, characters, tournaments).
- [x] Extract per game: draft sequence in order (pick/ban, team, side, champion, phase), winner, patch, game number in series.
- [x] Extract per game per role: champion, player, gold and XP at 10/14/20 minutes; lane gold difference at 14.
  - Done: per-player minute snapshots (gold, XP, level, CS, K/D/A, position) and roles inferred from lane position plus player history. Lane gold/XP/CS differences at 10/14/20 are in `lane_diffs`. 17 team-games (~0.5%) still lack a full role set.
- [x] Extract team-state snapshots, one sampled per 5-minute window per game (features listed in the design doc).
- [x] Handle the starter repo's caveats: rolled-back games (`series-!started-game`), missing games, team renames (join on IDs).
- [x] Tests on a small synthetic feed (no real data in the repo).

**Done when:** one command rebuilds the DuckDB file from scratch, and C9 Kia's 2026 games and drafts can be queried from it.

**Status (20 Nov):** `uv run python -m pipeline.build` rebuilds `data/draft.duckdb` from all 745 series in ~3 minutes (2 workers, below-normal priority, peak ~230 MB). `uv run python -m pipeline.checks` reports data quality: 1,737 games match `meta/` exactly, 0 winner mismatches, 0 Fearless repeat picks. Snapshots are stored every minute; 5-minute sampling happens at model time.

## 2. Draft board and evidence layer (target 10 Dec)

- [x] Confirm current LCS 2026 rules: side vs first-pick selection, pick/ban order, Fearless rules per series length.
  - From the data: the first-pick team was on red side in 246 of 1,737 games, so side and first pick are separate choices; Fearless locks picks (not bans) for both teams across the series.
- [x] FastAPI service: draft state, legal actions, Fearless-excluded champions.
- [x] React + TypeScript UI (WebStorm): draft board for a Bo1/Bo3/Bo5 series.
- [ ] C9 Kia champion pools: seeded from pro games, editable by the coach.
  - Seeded from pro games and shown per player with Fearless strike-through; coach editing not built yet.
- [x] Opponent tendencies: pick/ban frequency overall and by game number in series, with sample sizes.
- [ ] Lane matchups: gold difference at 14 by matchup, with sample sizes.
  - API done (`/api/matchups`); not yet shown in the UI (planned for C9 pick slots once the enemy laner is known).

**Done when:** a coach can step through a full Fearless Bo5 against a chosen opponent and see that opponent's tendencies at each step.

**Status (20 Nov):** a full Fearless series can be stepped through end to end (checked in a headless browser: game 2 locks the 10 game-1 picks). The rules engine replays 739 of 740 real series; the one rejection is a feed anomaly. A baseline next-action predictor is shown for opponent slots; its hit rate is not measured yet.

## 3. Win-probability models and WPA (target 22 Dec)

- [x] Team strength rating per team per split.
- [x] Pre-game model (team strength, side).
- [x] In-game model: logistic regression baseline, then small MLP. Split by game; hold out the most recent split.
- [x] Report accuracy, ECE and reliability diagrams per time window; keep the better-calibrated model.
- [x] WPA table per draft slot: `ΔW̄` overall and per phase, `W̄`, win rate, sample size, bootstrap interval, "not enough data" threshold.
- [ ] Show the WPA table in the draft board for the current slot.
  - Next: API endpoint over `data/winprob.duckdb` and a panel for C9 pick slots (lane gold vs the revealed enemy laner, early WPA, total WPA shrunk, evidence labels). Waits for Junie task 01 to merge (same files).

**Done when:** for any slot in the draft, every eligible champion shows WPA with an interval or "not enough data", and the model's calibration report is in the repo.

**Status (21 Nov):** `uv run python -m winprob.train` trains both models in ~25 s and writes `docs/results/winprob-report.md`. Elo by team (not by split), logistic regression chosen over the MLP. WPA uses empirical-Bayes shrinkage and reliability-based evidence labels instead of bootstrap intervals and a fixed threshold, because per-champion total WPA turned out to be mostly noise (see the design doc, "Model results"). Reliability diagrams are tables in the report for now; a chart can go in the UI or the write-up.

## 4. Series planner (target 31 Dec)

- [ ] Show each team's remaining Fearless pool after each game.
- [ ] "If we take X in game N" view for later games, for both teams.

**Done when:** a coach can see what C9 and the opponent have left for games 3-5 after any games 1-2 drafts.

## 5. Pocket pick mode (target 5 Jan, cut if behind)

- [ ] Pick an original name for the mode.
- [ ] In counterpick slots, list low-presence champions ranked by matchup and composition fit, with evidence strength labelled.

**Done when:** in a counterpick slot the mode lists candidates and says how much evidence each has.

## 6. Polish and submission (6-11 Jan)

- [ ] Fresh-clone install test following only the README.
- [ ] Decide demo hosting: ask in the Cloud9 Discord whether a public site showing aggregate statistics is allowed; otherwise judges run it locally.
- [ ] Demo video under 3 minutes, public on YouTube: problem, who it's for, one full draft with WPA, one clear insight for C9. No copyrighted music.
- [ ] Text description and tooling explanation (which JetBrains tools did what).
- [ ] Methodology write-up (cite the thesis).
- [ ] Finish `AI_SHOWCASE.md` for the bonus prize.
- [ ] Commit `.idea/`, `.junie/` and `.air/` folders.
- [ ] Pre-push data check prints nothing (command in CLAUDE.md).
- [ ] Submit on Devpost, Category 2, with the bonus link.

**Done when:** the Devpost submission is in, by 11 Jan.

## Open decisions

- Licence: MIT or Apache 2.0.
- Demo hosting (see step 6).
- Exact LCS 2026 draft rules (see step 2).
