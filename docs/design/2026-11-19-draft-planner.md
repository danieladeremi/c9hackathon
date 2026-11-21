# C9 Draft Planner: design

Hackathon Category 2 (LoL). Facts about the hackathon, the data and its licence are in [CLAUDE.md](../../CLAUDE.md).

## Problem

C9 Kia's coaches prepare drafts in spreadsheets. They need to know, at each moment of a draft and across a Fearless series, which picks help most, what the opponent is likely to do, and how strong the evidence is.

## Features (build order)

1. **Draft board.** Models the current rules: side selection and first-pick selection are separate choices, standard pick/ban phase order, Fearless restrictions across a Bo3/Bo5. Coach-editable C9 champion pools, seeded from each player's pro games.
2. **Evidence layer.** Opponent pick/ban tendencies, overall and by game number in a series. Lane-matchup results per role (gold and XP difference at 14 minutes) from LCK, LEC and LCS feeds. Every number shows its sample size.
3. **Win Percentage Added (WPA).** For the current draft slot, every eligible champion ranked by estimated WPA, with an uncertainty range and sample size. "Not enough data" where the range is too wide. See the model below.
4. **Series planner.** "Take X in game 1 and this is what remains for games 3-5", for both teams' Fearless pools.
5. **Pocket pick mode.** In counterpick slots (the enemy laner for that role is already revealed), surface low-presence champions that score well on matchup and composition fit, labelled with how thin the evidence is. Needs an original name; no real personalities' names in the product.

Features 1-3 are a complete entry on their own; 4 and 5 are added if time allows.

## What sets it apart (refinement, 2026-11-20)

Most Category 2 entries will have a tendency table and a Fearless draft board, because the blueprint asks for both. Three ideas make this entry different; they reuse the WPA tables, so they are mostly display and modelling on top of features 2-4.

1. **Fearless series value (the headline).** In Fearless, a pick is locked for *both* teams for the rest of the series, so every candidate is priced three ways:
   - *Now*: its WPA in this game (feature 3).
   - *Denial*: how much the opponent's expected WPA in later games drops because the champion is gone from their pool. Taking an opponent's comfort pick denies it to them for the whole series.
   - *Cost*: how much C9's own expected WPA in later games drops, measured as the gap to C9's next-best option in that role.

   **Series value = now + denial − cost.** It answers the judges' "how to win" question directly ("taking Rumble in Game 1 removes the opponent top laner's best Game 3 option"). Bans do not carry over in Fearless (confirmed in the GRID data: bans repeat across games, picks never do), so denial comes only from picks.
2. **Opponent next-action prediction with a measured hit rate.** For each draft slot, the opponent's likely bans and picks, from their history by game number and draft phase, minus champions already locked. The hit rate on held-out series is shown beside it ("our top-3 predicted bans were right X% of the time"), so a coach knows how far to trust it.
3. **Replay mode.** Step through a real past C9 series slot by slot and show what the tool recommended against what was actually picked, and how each game ended. It is the core of the demo video and an honest check of the tool. Recommendations come only from data before that series (no leakage).

## WPA model

Method follows xPetu, "Win probability estimation for strategic decision-making in esports" (Aalto University master's thesis, 2024, CC BY-NC-SA 4.0; method only, no text or figures reused). The thesis evaluates actions (item purchases) by the change in an in-game win-probability model over the action's effective window, averaged over similar game states. We apply the same method to picks.

**Notation (from the thesis):**
- `w(x)`: estimated win probability at game state `x`, from one team's perspective.
- For one game where a champion was picked: initial state `x`, end state `z` of the window being measured.
- `W = w(x)`: initial win probability. Its mean over all games with that pick (`W̄`) measures selection bias: above 50% means the champion is mostly picked by teams that were already favoured.
- `ΔW = w(z) - w(x)`: win probability added. Its mean over similar states (`ΔW̄`) is the pick's estimated impact.
- "Similar states" `X`: the draft context a coach selects (role, enemy laner or enemy laner's class, side, patch window). Narrower `X` is more specific but has fewer samples; this trade-off is shown, not hidden.

**Two models:**
1. **Pre-game model `w(x₀)`**: win probability from the state before play starts. Features: team strength (rating per team per split), side. This is the `W` baseline that absorbs "strong teams pick this", which raw win rate cannot.
2. **In-game model `w(x_t)`**: win probability at minute `t`. Features follow the thesis's Table 5 where the GRID feed has them: per-player gold, level, kills, deaths, assists, position; per-team towers, inhibitors, dragons, barons, void grubs; game time; plus the pre-game team-strength term. Items are excluded, as in the thesis.

**Pick WPA by game phase:** for a champion in context `X`, average `ΔW` over windows 0-15, 15-25 and 25+ minutes. This shows whether a pick wins early, scales, or neither, and is more informative per game than final win/loss. Total WPA = mean of `w(terminal) - w(x₀)`, which reduces to outcome minus pre-game expectation.

**Data and training:**
- ~1,739 pro games (LCK, LEC, LTA, LCS). The thesis used 350,000 ranked games, so expect wider uncertainty and keep models small.
- Sample one game state per 5-minute interval per game, as the thesis does, to avoid training on highly correlated consecutive states.
- Split by game, never by state; hold out the most recent split for testing.
- Candidates: logistic regression (baseline) and a small multilayer perceptron (deep-learning option). Keep whichever has the better calibration on the held-out split; if the MLP does not beat logistic regression, say so.

**Evaluation (from the thesis):** accuracy, expected calibration error (ECE, 10-20 bins) and reliability diagrams, overall and per time window. Calibration matters more than accuracy because WPA is a difference of probabilities.

**Display:** for the current draft slot, every eligible champion with `ΔW̄` (overall and per phase), `W̄`, raw win rate and sample size `K`, sorted by `ΔW̄`. Bootstrap intervals over games; "not enough data" when `K` is below a minimum or the interval is too wide (thresholds tuned on validation and shown in the UI). Showing `W̄` next to win rate lets a coach see when a high win rate is only selection bias.

**Scope limits:** ally synergy not modelled at first (too sparse). Pocket pick mode uses the same table filtered to low-presence champions, where "not enough data" will be common and is labelled as such.

## Model results and what changed (2026-11-21)

Full numbers: [docs/results/winprob-report.md](../results/winprob-report.md), regenerated by `uv run python -m winprob.train`.

- **Holdout:** train on 2025 (1,285 games), test on the whole 2026 season (452 games). The original "after June 2026" cutoff left only 79 test games.
- **Pre-game model** (side + Elo, K and break shrink chosen on 2025): 64% accuracy against 55% for "blue wins", but over-confident on 2026 (ECE 0.07): ratings carry over the off-season, when rosters change.
- **In-game model:** logistic regression 75% accuracy, ECE 0.04 on held-out states; the MLP did not beat it, so logistic regression is used (as the method requires, this is stated, not hidden). Slightly over-confident above 0.85.
- **Two data bugs found by the model, fixed in the pipeline:** 2025 feeds have no generic dragon event (drakes are only recorded by type), so the dragon feature was zero for all training games; Atakhan is recorded as `slayVoraciousAtakhan`.
- **The key finding: per-champion total WPA is mostly noise at pro sample sizes.** Random split-half reliability (does a champion's average in one random half of the games predict the other half?): lane gold at 14 min r = 0.73; early WPA (0-15 min) r = 0.31; total WPA 0.25; raw win rate 0.23; mid and late WPA ~0.1. Raw champion win rates, which most draft tools show, are just as noisy.
- **Consequences for the product:**
  - Every per-champion figure is shrunk toward its role average by empirical Bayes; its evidence label (strong / some / weak) comes from its reliability, replacing the fixed games threshold and bootstrap interval.
  - A metric that does not repeat overall (r < 0.3) is weak everywhere. Today that leaves **lane gold @14** and **early WPA** as the champion-level signals a coach can lean on; total WPA is shown shrunk (mostly near zero) with a weak label, never as a ranking.
  - Recommendations lean on what does repeat: opponent and player habits (to be confirmed by the predictor backtest, Junie task 01), lane matchups, early WPA and player comfort. The Fearless series value is built from these, not from total WPA.
  - The methodology write-up should say this plainly: it is a measured, non-obvious result and a reason to trust the tool.

## Architecture

| Part | Choice | IDE |
|---|---|---|
| Data pipeline | Python 3.14 (built-in zstd), uv; streams the starter repo from `STL_DATA_DIR` into a local DuckDB file (gitignored) | PyCharm |
| Models | scikit-learn logistic regression and a small scikit-learn MLP (PyTorch dropped: a 1-2 GB install on a nearly full laptop disk, for ~25k training rows); precomputed WPA tables | PyCharm |
| API | FastAPI serving draft state, WPA tables, tendencies | PyCharm |
| UI | React + TypeScript; draft board, WPA ranked list with interval bars, tendency charts | WebStorm |

Junie and JetBrains Air are used throughout; `.idea/`, `.junie/`, `.air/` are committed and `AI_SHOWCASE.md` is kept as work happens for the bonus prize.

## Data findings (feed inspection, 2026-11-20)

- `seriesState` is **not** always a full snapshot: about 1-2% of events have `includesFullState`; the rest carry only changed fields, nested by ID. The pipeline keeps a running state by deep-merging partial states and lists by `id`.
- Draft: 20 `draftActions` per game. The order depends on which team has **first pick**, not on side: first-pick team F, other team S: bans F S F S F S, picks F S S F F S, bans S F S F, picks S F F S. Holds for 1,720 of 1,721 complete drafts (one feed records slots 12/13 swapped). The first-pick team was on red side in 246 of 1,737 games. Draft events can be reversed (`team-!banned-character`); the final state holds the corrected sequence.
- Fearless: across a Bo5, all 40 picks are distinct while bans repeat. Hard Fearless on picks only.
- Roles: `players[].roles` is empty and roster order is not role order. Roles are inferred: jungler from jungle-item and neutral-minion farm at 10:00; the other four from lane positions between 1:30 and 14:00; support is the bot-laner with fewer lane minions. Checked by hand against a C9 vs TL Bo5 (20/20 correct).
- Clock glitches: some feeds briefly report a game clock of about 35,000,000 s. The pipeline ignores clock values above 100 minutes or jumps of more than 5 minutes.
- Per-team objective counts (dragons by type, grubs, herald, baron) are in `teams[].objectives`; towers and inhibitors (`fortifier`) in `games[].structures`. Player level = `increaseLevel` count + 1.

## Open questions

- Hosted demo: a public site would show aggregate statistics derived from the licensed data to anyone, not only judges. Confirm with the organizers (Discord) that this is allowed, or give judges a local run instead.
- Exact current rules for side vs first-pick selection and Fearless in LCS 2026, to encode in the draft board.
