# AI-powered workflow: how this entry was built

A running log of how AI agents and JetBrains tools built the C9 Draft Planner, kept as the work happened.
Each entry says which tool did what, how the result was checked, and what a human decided.

## Tools

| Tool | Role |
|---|---|
| **PyCharm** | Main IDE for the whole repo: Python pipeline and API, React/TypeScript front end, test runner, run configurations (`.idea/runConfigurations/`) |
| **Junie** (in PyCharm, JetBrains AI) | Coding agent for self-contained, testable tasks. Briefs live in `.junie/tasks/`; project rules in `.junie/guidelines.md` |
| **Claude (Claude Code)** | Design, data investigation, architecture, writing Junie's task briefs and reviewing its diffs. Ran in VS Code for the first two sessions, then in PyCharm |

The developer chose the idea and the category, approved each design change, and reviewed every commit.

## Log

### 19 Nov 2026: idea and design (Claude Code)
- Researched the hackathon rules and wrote the design: a Fearless draft planner with a win-probability-added model adapted from
  a published thesis method.

### 20 Nov 2026: data pipeline (Claude Code)
- Inspected the GRID LoL feed and found facts the docs did not state: `seriesState` is usually partial, not a full snapshot; roles
  are missing; Fearless locks picks but not bans. The pipeline was designed around these findings.
- **A bug found by watching the machine, not the tests:** the first full build froze the developer's laptop. Diagnosis: some feeds
  report a game clock of ~35,000,000 s, and the snapshot loop tried to "catch up" with hundreds of thousands of rows. Fixed with a
  clock guard; the build now runs in ~3 minutes at a 232 MB peak, with 2 workers at below-normal priority.
- Role inference reached 5 inconsistent players out of 252 after adding a second pass that uses each player's history.
- Verification: 1,737 games match the starter repo's index exactly; 0 winner mismatches; 0 repeated Fearless picks.

### 20 Nov 2026: rules engine, API and draft board (Claude Code)
- Derived the real draft order from the data: it is keyed on *first pick*, not side (the first-pick team was on red side in 246
  games). The rules engine replays 739 of 740 real series; the one rejection is a feed that records two slots swapped.
- Built the FastAPI service and the React draft board, then drove a full Fearless game in a headless browser to confirm the
  locks (game 2 correctly locked the 10 game-1 picks).

### 21 Nov 2026: moved into PyCharm; Junie joins
- Opened the project in PyCharm, added shared run configurations, and wrote `.junie/guidelines.md` so Junie starts every task
  with the data-licence rules and the laptop's memory limits.
- Junie task 01 (`.junie/tasks/01-predictor-backtest.md`): measure the opponent-prediction hit rate on held-out games against a
  league-popularity baseline. **Junie built** `planner/backtest.py` (a day-by-day replay so no prediction sees same-day or later
  games), a no-leakage `before` option, a shared ranking function so the live board and the backtest score identically, an API
  endpoint, the hit-rate line on the board, and synthetic-data tests. **Claude reviewed** the diff and re-ran the tests and the
  backtest independently (same numbers, 3 s). **Result:** top-3 hit rate on the 2026 season, bans 15.8% vs 13.0% for the
  league-popularity baseline, picks 14.1% vs 13.5%: only a small edge, now shown honestly on the board. Diagnosis: all games since
  January 2025 count equally, so last season's meta drowns out recent habits. That became Junie task 02.

### 21 Nov 2026: win-probability models (Claude Code, in PyCharm)
- Built Elo team strength, a pre-game model and an in-game model (logistic regression against an MLP), trained on 2025 and
  tested on the whole 2026 season. Logistic regression won on calibration, and the report says so.
- **The model caught two data bugs the pipeline checks had missed**: 2025 feeds never record a generic dragon event, so the
  dragon feature was zero for every training game; and Atakhan is recorded under a different name. Fixed and rebuilt.
- **A result that changed the design**: a split-half test showed per-champion total WPA (and raw win rate) barely repeats
  between random halves of the data, while lane gold at 14 minutes repeats strongly. Rather than ship a ranking of noise,
  every figure is now shrunk by its measured reliability and labelled strong, some or weak evidence.
- Kept away from the files Junie's task touches, so both could work at once.

### 22 Nov 2026: Fearless series value and the C9 pick panel (Claude Code, in PyCharm)
- Ran Junie and Claude in parallel: Junie got task 02 (recency-weighted predictor, `planner/stats.py` and `backtest.py` only) while
  Claude built the Fearless value in new files plus `api.py` and the UI. File boundaries were written into the brief to avoid clashes.
- Checked the idea against the data before building it: a team's recent picks do forecast which champions it uses later in a series.
  Two fixes came from looking at the calibration table, not the headline number: champions already locked in game 1 were wrongly
  counted as "not used", and champions a team had never picked got a forecast of exactly zero. After both, the forecast beats a flat
  rate by 18% and its probabilities hold up (24% predicted, 24% observed).
- Added a playable filter after the first ranking recommended taking Xayah to deny an opponent, when no C9 player plays Xayah.
- **Browser testing caught a crash no test had**: typing in the champion search froze the board, because 17 player-games with no
  recorded champion became a nameless champion. Fixed at the query and guarded in the UI.
- **Reviewing a screenshot caught a ranking bug**: once the enemy laner was known, champions with a thin head-to-head record sank
  below weaker ones, instead of falling back to their solid overall number. Fixed, with a regression test.

