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

## Architecture

| Part | Choice | IDE |
|---|---|---|
| Data pipeline | Python 3.14 (built-in zstd), uv; streams the starter repo from `STL_DATA_DIR` into a local DuckDB file (gitignored) | PyCharm |
| Models | scikit-learn logistic regression and a small PyTorch MLP; precomputed WPA tables | PyCharm |
| API | FastAPI serving draft state, WPA tables, tendencies | PyCharm |
| UI | React + TypeScript; draft board, WPA ranked list with interval bars, tendency charts | WebStorm |

Junie and JetBrains Air are used throughout; `.idea/`, `.junie/`, `.air/` are committed and `AI_SHOWCASE.md` is kept as work happens for the bonus prize.

## Open questions

- Hosted demo: a public site would show aggregate statistics derived from the licensed data to anyone, not only judges. Confirm with the organizers (Discord) that this is allowed, or give judges a local run instead.
- Exact current rules for side vs first-pick selection and Fearless in LCS 2026, to encode in the draft board.
