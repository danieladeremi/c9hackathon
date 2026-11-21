"""Does the draft predict the result beyond team strength? The test behind a live win-probability bar.

    uv run python -m winprob.draft_eval

Holdout as everywhere else: champion estimates learned from 2025 games only, evaluated on the 2026 season.
For fitting the combination weights on 2025, champion estimates are cross-fitted (5 folds by game), so no
game helps score itself.

Models (logistic regression on the blue side's result):
  M0  pre-game only             logit(p_pregame)                     the baseline: side + team strength
  M1  + projected lane gold     + sum over roles of blue's minus red's champion lane gold @14 (shrunk)
  M2  + champion WPA            + sum of shrunk champion total WPA (the route the reliability check called noisy)
  M3  draft only                projected lane gold alone (no team strength)

Pass mark for a moving bar: M1 must beat M0 on held-out log loss, with a 90% paired bootstrap interval that
excludes zero. Results: docs/results/draft-eval.json and .md.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date

import duckdb
import numpy as np
from sklearn.linear_model import LogisticRegression

from pipeline.config import DB_PATH, REPO_ROOT, WORK_DIR

from . import wpa as W
from .metrics import summarize

CUTOFF = date(2026, 1, 1)
FOLDS = 5
ROLES = ("top", "jungle", "mid", "bot", "support")
OUT_JSON = REPO_ROOT / "docs" / "results" / "draft-eval.json"
OUT_MD = REPO_ROOT / "docs" / "results" / "draft-eval.md"
BOOTSTRAP = 2000


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def _load(con):
    games = con.execute("""
        SELECT g.game_id, g.game_date, g.blue_team_id, g.red_team_id, (g.winner_team_id = g.blue_team_id)::INT AS blue_won,
               p.p_blue
        FROM game_context g JOIN wp.pregame p USING (game_id)
        WHERE g.winner_team_id IS NOT NULL ORDER BY g.started_at
    """).fetchall()
    picks = con.execute("""
        SELECT pg.game_id, pg.team_id, pg.role, pg.champion_id, l.gold_diff, w.wpa_total
        FROM player_games pg
        LEFT JOIN lane_diffs l ON l.game_id = pg.game_id AND l.player_id = pg.player_id AND l.minute = 14
        LEFT JOIN wp.team_game_wpa w ON w.game_id = pg.game_id AND w.team_id = pg.team_id
        WHERE pg.role IN ('top', 'jungle', 'mid', 'bot', 'support') AND pg.champion_id IS NOT NULL
    """).fetchall()
    gold14 = dict(con.execute("""
        SELECT g.game_id, sum(CASE WHEN t.team_id = g.blue_team_id THEN t.net_worth ELSE -t.net_worth END)
        FROM team_minutes t JOIN game_context g USING (game_id) WHERE t.minute = 14 GROUP BY 1 HAVING count(*) = 2
    """).fetchall())
    return games, picks, gold14


def _estimates(picks_by_game: dict, game_ids: set[str], metric: int) -> dict[tuple[str, str], float]:
    """Shrunk champion-role estimate of a per-pick metric (3 = lane gold @14, 4 = total WPA),
    learned only from ``game_ids``. Returned as the difference from the role's average."""
    groups: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for gid in game_ids:
        for team, role, champ, gold, wpa_total in picks_by_game.get(gid, ()):
            value = (None, None, None, gold, wpa_total)[metric]
            if value is not None:
                groups[role][(champ, role)].append(float(value))
    out = {}
    for role, by_key in groups.items():
        shrunk, summary = W.shrink(by_key)
        for key, est in shrunk.items():
            out[key] = est.estimate - summary["grand_mean"]
    return out


def _draft_score(picks_by_game: dict, game, estimates: dict) -> float:
    """Blue's champions minus red's, summed over roles; unknown champions count as role average (0)."""
    gid, _, blue, red = game[0], game[1], game[2], game[3]
    total = 0.0
    for team, role, champ, *_ in picks_by_game.get(gid, ()):
        value = estimates.get((champ, role), 0.0)
        total += value if team == blue else -value if team == red else 0.0
    return total


def _paired_bootstrap(y, p_new, p_base, rng) -> tuple[float, float, float]:
    """Mean per-game log-loss improvement (base - new) and its 90% interval. Positive = new is better."""
    def per_game(p):
        p = np.clip(p, 1e-6, 1 - 1e-6)
        return -(y * np.log(p) + (1 - y) * np.log(1 - p))
    diff = per_game(p_base) - per_game(p_new)
    idx = rng.integers(0, len(diff), size=(BOOTSTRAP, len(diff)))
    means = diff[idx].mean(axis=1)
    return float(diff.mean()), float(np.percentile(means, 5)), float(np.percentile(means, 95))


def run() -> dict:
    con = duckdb.connect(str(DB_PATH), read_only=True, config={"threads": 2, "memory_limit": "1GB"})
    con.execute(f"ATTACH '{(WORK_DIR / 'winprob.duckdb').as_posix()}' AS wp (READ_ONLY)")
    games, picks, gold14 = _load(con)
    con.close()

    picks_by_game: dict[str, list] = defaultdict(list)
    for gid, team, role, champ, gold, wpa_total in picks:
        picks_by_game[gid].append((team, role, champ, gold, wpa_total))
    # Only games with exactly one pick per role per team give a clean role-vs-role comparison.
    complete = {gid for gid, rows in picks_by_game.items()
                if sorted(r for _, r, *_ in rows) == sorted(ROLES * 2)}
    games = [g for g in games if g[0] in complete]
    train = [g for g in games if g[1] < CUTOFF]
    test = [g for g in games if g[1] >= CUTOFF]
    train_ids = {g[0] for g in train}

    # Cross-fitted draft scores for training games; full-2025 estimates for 2026 games.
    rng = np.random.default_rng(0)
    fold_of = {g[0]: int(f) for g, f in zip(train, rng.integers(0, FOLDS, size=len(train)))}
    scores = {}
    for metric, name in ((3, "lane"), (4, "wpa")):
        per_game = {}
        for fold in range(FOLDS):
            fit_ids = {gid for gid in train_ids if fold_of[gid] != fold}
            est = _estimates(picks_by_game, fit_ids, metric)
            for g in train:
                if fold_of[g[0]] == fold:
                    per_game[g[0]] = _draft_score(picks_by_game, g, est)
        est_full = _estimates(picks_by_game, train_ids, metric)
        for g in test:
            per_game[g[0]] = _draft_score(picks_by_game, g, est_full)
        scores[name] = per_game

    def matrix(rows, cols):
        return np.column_stack([[f(g) for g in rows] for f in cols])

    pre = lambda g: float(_logit(np.array([g[5]]))[0])  # noqa: E731
    lane = lambda g: scores["lane"][g[0]] / 1000         # noqa: E731
    wpa = lambda g: scores["wpa"][g[0]]                  # noqa: E731
    specs = {
        "M0 pre-game only": [pre],
        "M1 pre-game + projected lane gold": [pre, lane],
        "M2 pre-game + champion WPA": [pre, wpa],
        "M3 draft only (projected lane gold)": [lane],
    }
    y_train = np.array([g[4] for g in train], dtype=float)
    y_test = np.array([g[4] for g in test], dtype=float)
    results, preds, coefs = {}, {}, {}
    for name, cols in specs.items():
        model = LogisticRegression(C=1e6, max_iter=1000).fit(matrix(train, cols), y_train)
        p = model.predict_proba(matrix(test, cols))[:, 1]
        preds[name] = p
        results[name] = summarize(y_test, p, bins=10)
        results[name].pop("reliability")
        coefs[name] = [round(float(c), 4) for c in model.coef_[0]] + [round(float(model.intercept_[0]), 4)]

    base = preds["M0 pre-game only"]
    comparisons = {}
    for name in ("M1 pre-game + projected lane gold", "M2 pre-game + champion WPA"):
        mean, low, high = _paired_bootstrap(y_test, preds[name], base, np.random.default_rng(1))
        comparisons[name] = {"log_loss_improvement": round(mean, 5), "ci90": [round(low, 5), round(high, 5)],
                             "significant": bool(low > 0)}

    # Does the projected lane gold predict the real gold lead at 14 minutes in 2026?
    pairs = [(scores["lane"][g[0]], gold14[g[0]]) for g in test if g[0] in gold14]
    proj, real = np.array(pairs).T
    lane_check = {
        "games": len(pairs),
        "correlation": round(float(np.corrcoef(proj, real)[0, 1]), 3),
        "slope_real_per_projected": round(float(np.polyfit(proj, real, 1)[0]), 3),
        "projected_sd": round(float(proj.std()), 1),
        "real_sd": round(float(real.std()), 1),
    }

    # Size of the effect on the bar: how far would M1 move a 50% game for a typical draft?
    lane_coef = coefs["M1 pre-game + projected lane gold"][1]
    typical = float(np.std([scores["lane"][g[0]] for g in test])) / 1000
    swing = 1 / (1 + math.exp(-lane_coef * typical)) - 0.5

    # Power check: if a projected gold lead were worth what a real gold lead at 14 is worth (fitted on 2025),
    # how much should M1 have gained? Expected per-game log-loss gain for a logit effect b*sd is ~ (b*sd)^2 / 8.
    real = [(gold14[g[0]] / 1000, g[4]) for g in train if g[0] in gold14]
    gold_model = LogisticRegression().fit(np.array([[x] for x, _ in real]), np.array([w for _, w in real]))
    per_1k = float(gold_model.coef_[0][0])
    chained_gain = (per_1k * typical) ** 2 / 8
    chained_move = 1 / (1 + math.exp(-per_1k * typical)) - 0.5
    m1 = comparisons["M1 pre-game + projected lane gold"]
    power = {
        "win_logit_per_1k_real_gold_at_14": round(per_1k, 3),
        "chained_bar_move_points": round(100 * chained_move, 1),
        "chained_expected_log_loss_gain": round(chained_gain, 5),
        "chained_effect_ruled_out": bool(m1["ci90"][1] < chained_gain),
    }

    passed = comparisons["M1 pre-game + projected lane gold"]["significant"]
    report = {
        "cutoff": str(CUTOFF),
        "games": {"train": len(train), "test": len(test)},
        "models": results,
        "coefficients_with_intercept": coefs,
        "vs_pregame": comparisons,
        "projected_lane_gold_vs_real_gold_at_14": lane_check,
        "typical_bar_move_points": round(100 * swing, 1),
        "power_check": power,
        "passed": passed,
        "verdict": (
            "The draft adds a measurable, held-out improvement over team strength: a moving bar is justified, "
            "with its size shown honestly."
            if passed else
            "The draft does not add a measurable held-out improvement over team strength: no moving bar. "
            "Show the pre-game number and the projected lane table instead."
            + (" The test had the power to see the effect a projected gold lead would have if it converted like a real one, "
               "and rules it out: draft lane advantages show up at 14 minutes but do not turn into wins."
               if power["chained_effect_ruled_out"] else
               " The test could not rule out a small effect at this sample size.")
        ),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text(_markdown(report), encoding="utf-8")
    return report


def _markdown(r: dict) -> str:
    lines = [
        "# Does the draft predict the result? (live win-bar test)",
        "",
        f"Generated by `uv run python -m winprob.draft_eval`. Champion estimates from {r['games']['train']} games before "
        f"{r['cutoff']} (cross-fitted for the training rows); evaluated on {r['games']['test']} games of the 2026 season.",
        "",
        "| Model | Accuracy | Log loss | Brier | ECE |",
        "|---|---:|---:|---:|---:|",
        *[f"| {name} | {m['accuracy']:.3f} | {m['log_loss']:.4f} | {m['brier']:.4f} | {m['ece']:.3f} |" for name, m in r["models"].items()],
        "",
        "Paired bootstrap against the pre-game model (positive = better; per-game log loss):",
        "",
        "| Model | Improvement | 90% interval | Significant |",
        "|---|---:|---|---|",
        *[f"| {name} | {c['log_loss_improvement']:+.5f} | {c['ci90'][0]:+.5f} to {c['ci90'][1]:+.5f} | {'yes' if c['significant'] else 'no'} |"
          for name, c in r["vs_pregame"].items()],
        "",
        f"Projected lane gold vs the real team gold lead at 14 minutes (2026, {r['projected_lane_gold_vs_real_gold_at_14']['games']} games): "
        f"correlation {r['projected_lane_gold_vs_real_gold_at_14']['correlation']}, "
        f"slope {r['projected_lane_gold_vs_real_gold_at_14']['slope_real_per_projected']} real gold per projected gold.",
        "",
        f"A typical draft (one standard deviation of projected lane gold) moves a 50% game by about "
        f"{r['typical_bar_move_points']} points in M1.",
        "",
        f"**Power check.** A real gold lead at 14 minutes is worth {r['power_check']['win_logit_per_1k_real_gold_at_14']} logit per 1,000 gold "
        f"(2025). If a projected lead converted the same way, a typical draft would move the bar "
        f"{r['power_check']['chained_bar_move_points']} points and improve log loss by about "
        f"{r['power_check']['chained_expected_log_loss_gain']:.4f} per game. The observed interval "
        f"{'rules that out' if r['power_check']['chained_effect_ruled_out'] else 'does not rule that out'}.",
        "",
        f"**Verdict:** {r['verdict']}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    r = run()
    print(_markdown(r))


if __name__ == "__main__":
    main()
