"""Fearless series value: what taking a champion now does to the rest of the series.

In hard Fearless a pick is gone for *both* teams for the rest of the series. So beyond its value in
this game, each candidate has:

- **denial**: the chance the opponent would have used it later in the series. Taking it now removes it.
- **cost**: the chance C9 would have wanted it later. Taking it now spends it.

Both come from one forecast, P(team uses champion in the remaining games), built from the team's pick
rate over its last games and the expected number of games left, then calibrated on 2025 series. Its
accuracy on the 2026 season is in ``docs/results/series-use-calibration.json``:

    uv run python -m planner.series_value       # fit on 2025, evaluate on 2026, write the JSON

Bans do not carry over in Fearless, so a ban has no series effect.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date
from functools import lru_cache

import numpy as np

from pipeline.config import REPO_ROOT

from .rules import SERIES_GAMES, Series

HISTORY_GAMES = 80
MIN_HISTORY_GAMES = 10
PLAYABLE_GAMES = 3         # a current player needs this many pro games on a champion to count as able to play it
PRIOR_GAMES = 8            # the league's recent pick rate counts as this many games of team history
LEAGUE_WINDOW_DAYS = 60
CALIBRATION_PATH = REPO_ROOT / "docs" / "results" / "series-use-calibration.json"
FIT_START, FIT_END, TEST_START = date(2025, 1, 1), date(2026, 1, 1), date(2026, 1, 1)


def future_game_probabilities(fmt: str, wins_a: int, wins_b: int, p_a: float = 0.5) -> list[float]:
    """P(each later game is played), given the score *before* the game being drafted now.

    The current game counts as played. Each game is a coin flip at ``p_a`` (team strength is
    ignored here: the forecast is about the opponent's habits, not the result).
    """
    needed = SERIES_GAMES[fmt] // 2 + 1
    total = SERIES_GAMES[fmt]
    played_so_far = wins_a + wins_b
    states = {(wins_a, wins_b): 1.0}
    probs = []
    for game in range(played_so_far, total):
        next_states: dict[tuple[int, int], float] = defaultdict(float)
        live = 0.0
        for (a, b), p in states.items():
            if a >= needed or b >= needed:
                next_states[(a, b)] += p
                continue
            live += p
            next_states[(a + 1, b)] += p * p_a
            next_states[(a, b + 1)] += p * (1 - p_a)
        if game > played_so_far:
            probs.append(round(live, 4))
        states = next_states
    return probs


def smoothed_rate(team_picks: int, team_games: int, league_rate: float, prior_games: float = PRIOR_GAMES) -> float:
    """Team pick rate pulled toward the league's recent rate, so a champion the team has never
    picked still gets a small, realistic chance instead of exactly zero."""
    return (team_picks + prior_games * league_rate) / (team_games + prior_games)


def raw_use_probability(rate: float, expected_games: float) -> float:
    """P(at least one use) over ``expected_games`` games at a per-game pick rate."""
    return 1 - (1 - min(max(rate, 0.0), 1.0)) ** expected_games


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def calibrate(p: float, a: float, b: float) -> float:
    return 1 / (1 + math.exp(-(a + b * _logit(p))))


@lru_cache(maxsize=1)
def calibration() -> tuple[float, float]:
    try:
        data = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
        return float(data["calibration"]["a"]), float(data["calibration"]["b"])
    except (OSError, KeyError, ValueError):
        return 0.0, 1.0


def pick_history(con, team_id: str, before: date | None = None, last_games: int = HISTORY_GAMES) -> tuple[int, dict[str, int]]:
    """(games, champion -> picks) over the team's last games before ``before``."""
    params: list = [team_id]
    clause = ""
    if before is not None:
        clause = "AND g.game_date < ?"
        params.append(before)
    params.append(last_games)
    rows = con.execute(f"""
        WITH recent AS (
            SELECT DISTINCT g.game_id, g.started_at FROM draft_actions d JOIN game_context g USING (game_id)
            WHERE d.team_id = ? AND d.action = 'pick' {clause}
            ORDER BY g.started_at DESC LIMIT ?)
        SELECT d.champion_id, count(*) FROM draft_actions d JOIN recent r USING (game_id)
        WHERE d.team_id = ? AND d.action = 'pick' AND d.champion_id IS NOT NULL GROUP BY 1
    """, [*params, team_id]).fetchall()
    games = con.execute(f"""
        SELECT count(*) FROM (
            SELECT DISTINCT g.game_id, g.started_at FROM draft_actions d JOIN game_context g USING (game_id)
            WHERE d.team_id = ? AND d.action = 'pick' {clause} ORDER BY g.started_at DESC LIMIT ?)
    """, params).fetchone()[0]
    return games, dict(rows)


def league_rates(con, before: date | None = None, days: int = LEAGUE_WINDOW_DAYS) -> dict[str, float]:
    """Champion -> picks per team-game across all teams over the last ``days`` days of data."""
    params: list = []
    end = "(SELECT max(game_date) FROM game_context)"
    if before is not None:
        end = "?"
        params.append(before)
    rows = con.execute(f"""
        WITH recent_games AS (SELECT game_id FROM game_context
                        WHERE game_date < {end} + INTERVAL 1 DAY AND game_date >= {end} - INTERVAL {int(days)} DAY)
        SELECT d.champion_id, count(*) * 1.0 / (SELECT 2 * count(*) FROM recent_games)
        FROM draft_actions d JOIN recent_games USING (game_id)
        WHERE d.action = 'pick' AND d.champion_id IS NOT NULL GROUP BY 1
    """, params * 2).fetchall()
    return dict(rows)


def _players(con, team_id: str) -> dict[str, tuple[str, int]]:
    """Champion -> (current player most associated with it, their games on it)."""
    rows = con.execute("""
        WITH last AS (
            SELECT pg.game_id FROM player_games pg JOIN game_context g USING (game_id)
            WHERE pg.team_id = ? ORDER BY g.started_at DESC LIMIT 1),
        roster AS (SELECT player_id, player_name FROM player_games WHERE game_id = (SELECT game_id FROM last) AND team_id = ?)
        SELECT pg.champion_id, arg_max(r.player_name, n), max(n) FROM (
            SELECT player_id, champion_id, count(*) AS n FROM player_games GROUP BY 1, 2) pg
        JOIN roster r USING (player_id) GROUP BY 1
    """, [team_id, team_id]).fetchall()
    return {c: (name.strip(), int(n)) for c, name, n in rows}


def series_value(con, series: Series, game_index: int, us: str, champion_names: dict[str, str],
                 unavailable: set[str], top: int = 25) -> dict:
    """Rank the champions still available by net series value for ``us``."""
    them = series.team_b if us == series.team_a else series.team_a
    wins = series.wins()
    before_this_game = {series.team_a: 0, series.team_b: 0}
    for game in series.games[:game_index]:
        if game.winner in before_this_game:
            before_this_game[game.winner] += 1
    future = future_game_probabilities(series.format, before_this_game[us], before_this_game[them])
    expected_games = float(sum(future))
    a, b = calibration()

    our_games, our_counts = pick_history(con, us)
    their_games, their_counts = pick_history(con, them)
    our_players, their_players = _players(con, us), _players(con, them)

    league = league_rates(con)

    def use(counts: dict, games: int, champ: str) -> float | None:
        if expected_games == 0:
            return 0.0
        if games < MIN_HISTORY_GAMES:
            return None
        rate = smoothed_rate(counts.get(champ, 0), games, league.get(champ, 0.0))
        return calibrate(raw_use_probability(rate, expected_games), a, b)

    rows = []
    for champ in set(our_counts) | set(their_counts) | set(league):
        if champ in unavailable:
            continue
        denial, cost = use(their_counts, their_games, champ), use(our_counts, our_games, champ)
        if denial is None or cost is None:
            continue
        their_player, our_player = their_players.get(champ), our_players.get(champ)
        rows.append({
            "champion_id": champ,
            "name": champion_names.get(champ, champ),
            "denial": round(denial, 3),
            "cost": round(cost, 3),
            "net": round(denial - cost, 3),
            "their_picks": their_counts.get(champ, 0),
            "our_picks": our_counts.get(champ, 0),
            "their_player": their_player[0] if their_player else None,
            "their_player_games": their_player[1] if their_player else 0,
            "our_player": our_player[0] if our_player else None,
            "our_player_games": our_player[1] if our_player else 0,
            # Denying by picking only works if someone on the team can play it.
            "playable": bool(our_player and our_player[1] >= PLAYABLE_GAMES),
        })
    rows.sort(key=lambda r: (not r["playable"], -r["net"], -r["denial"], r["name"]))
    return {
        "us": us, "them": them, "wins": wins,
        "future_game_probabilities": future,
        "expected_future_games": round(expected_games, 2),
        "history_games": {"us": our_games, "them": their_games, "window": HISTORY_GAMES},
        "calibration": {"a": a, "b": b},
        "playable_min_games": PLAYABLE_GAMES,
        "champions": rows[:top],
        "note": "Bans do not carry over in Fearless: only picks have a series effect." if expected_games else
                "Last possible game of the series: no Fearless effect left.",
    }


# --- Offline fit and evaluation ---------------------------------------------------------------

def _series_rows(con, start: date, end: date) -> tuple[list[float], list[float]]:
    """(raw forecast, used?) for every team x series x champion in [start, end), leaving out champions
    already picked in game 1 (Fearless makes them unusable, which is not what the forecast is about).

    The forecast for a series uses only games before that series, and the actual number of
    games after the first one (the same horizon as when drafting game 1)."""
    picks = con.execute("""
        SELECT g.series_id, min(g.game_date) OVER (PARTITION BY g.series_id) AS series_date,
               count(DISTINCT g.game_id) OVER (PARTITION BY g.series_id) AS series_games,
               g.game_id, g.game_number, g.started_at, d.team_id, d.champion_id
        FROM draft_actions d JOIN game_context g USING (game_id)
        WHERE d.action = 'pick' AND d.champion_id IS NOT NULL
    """).fetchall()
    team_games: dict[str, list] = defaultdict(list)
    seen = set()
    for sid, sdate, n_games, gid, gnum, started, team, champ in picks:
        if (team, gid) not in seen:
            seen.add((team, gid))
            team_games[team].append([started, gid, set()])
    by_key = {(t, g[1]): g for t, gs in team_games.items() for g in gs}
    series: dict[str, dict] = {}
    for sid, sdate, n_games, gid, gnum, started, team, champ in picks:
        by_key[(team, gid)][2].add(champ)
        s = series.setdefault(sid, {"date": sdate, "games": n_games, "first_start": started,
                                    "teams": defaultdict(set), "game1": set()})
        s["first_start"] = min(s["first_start"], started)
        if gnum == 1:
            s["game1"].add(champ)        # Fearless-locked for the rest: not a fair question
        else:
            s["teams"][team].add(champ)  # used *after* game 1
    for gs in team_games.values():
        gs.sort(key=lambda g: g[0])
    universe = sorted({c for *_, c in picks})
    all_games = sorted((g[0], g[2]) for gs in team_games.values() for g in gs)
    starts = [g[0] for g in all_games]

    preds, ys = [], []
    for s in series.values():
        if not (start <= s["date"] < end) or s["games"] < 2:
            continue
        horizon = s["games"] - 1
        for team, used in s["teams"].items():
            history = [g for g in team_games[team] if g[0] < s["first_start"]][-HISTORY_GAMES:]
            if len(history) < MIN_HISTORY_GAMES:
                continue
            counts: dict[str, int] = defaultdict(int)
            for *_, champs in history:
                for c in champs:
                    counts[c] += 1
            league = s.setdefault("league", _league_window(all_games, starts, s["first_start"]))
            for c in universe:
                if c in s["game1"]:
                    continue
                rate = smoothed_rate(counts[c], len(history), league.get(c, 0.0))
                preds.append(raw_use_probability(rate, horizon))
                ys.append(1.0 if c in used else 0.0)
    return preds, ys


def _league_window(all_games: list, starts: list, before) -> dict[str, float]:
    """League pick rate per team-game over the LEAGUE_WINDOW_DAYS before ``before``."""
    from bisect import bisect_left
    from datetime import timedelta

    lo, hi = bisect_left(starts, before - timedelta(days=LEAGUE_WINDOW_DAYS)), bisect_left(starts, before)
    window = all_games[lo:hi]
    counts: dict[str, int] = defaultdict(int)
    for _, champs in window:
        for c in champs:
            counts[c] += 1
    return {c: n / len(window) for c, n in counts.items()} if window else {}


def fit_and_evaluate(con) -> dict:
    from sklearn.linear_model import LogisticRegression

    from winprob.metrics import summarize

    fit_p, fit_y = _series_rows(con, FIT_START, FIT_END)
    test_p, test_y = _series_rows(con, TEST_START, date(2100, 1, 1))
    x_fit = np.array([[_logit(p)] for p in fit_p])
    model = LogisticRegression(C=100.0).fit(x_fit, np.array(fit_y))
    a, b = float(model.intercept_[0]), float(model.coef_[0][0])
    raw = np.array(test_p)
    cal = np.array([calibrate(p, a, b) for p in test_p])
    y = np.array(test_y)
    constant = np.full(len(y), float(np.mean(fit_y)))
    return {
        "method": f"P(team uses champion after game 1) from its last {HISTORY_GAMES} games, smoothed toward the league's "
                  f"pick rate over the previous {LEAGUE_WINDOW_DAYS} days ({PRIOR_GAMES} games of weight); logistic calibration fitted on "
                  f"{FIT_START} to {FIT_END}, evaluated on series from {TEST_START}",
        "calibration": {"a": round(a, 4), "b": round(b, 4)},
        "fit_rows": len(fit_y),
        "test": {
            "calibrated": summarize(y, cal, bins=10),
            "uncalibrated": summarize(y, np.clip(raw, 1e-4, 1 - 1e-4), bins=10),
            "constant_rate": summarize(y, constant, bins=10),
        },
    }


def main() -> None:
    import duckdb

    from pipeline.config import DB_PATH

    con = duckdb.connect(str(DB_PATH), read_only=True, config={"threads": 2, "memory_limit": "1GB"})
    try:
        report = fit_and_evaluate(con)
    finally:
        con.close()
    CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATION_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    t = report["test"]
    print(f"Calibration a={report['calibration']['a']}, b={report['calibration']['b']} (fit on {report['fit_rows']:,} rows)")
    for name in ("calibrated", "uncalibrated", "constant_rate"):
        print(f"  {name:13s} log loss {t[name]['log_loss']:.4f}  ECE {t[name]['ece']:.4f}  n={t[name]['n']:,}")
    print("  reliability (calibrated):")
    for row in t["calibrated"]["reliability"]:
        print(f"    predicted {row['mean_predicted']:.2f}  observed {row['observed']:.2f}  n={row['count']:,}")
    print(f"Wrote {CALIBRATION_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
