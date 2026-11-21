"""Train the win-probability models, evaluate them, and build the WPA tables.

    uv run python -m winprob.train                  # hold out the 2026 season
    uv run python -m winprob.train --cutoff 2026-04-01

Reads data/draft.duckdb (read-only). Writes:
  data/winprob.duckdb                  model outputs and WPA tables (gitignored)
  docs/results/winprob-report.json     aggregate evaluation metrics (safe to commit)
  docs/results/winprob-report.md       the same, readable

Runs single-process with BLAS limited to 2 threads; it takes well under a minute.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from pipeline.config import DB_PATH, REPO_ROOT, WORK_DIR

from . import wpa as W
from .elo import expected, run_elo
from .features import INGAME_FEATURES, ingame_matrix, load_games, load_states
from .metrics import log_loss, summarize

OUT_DB = WORK_DIR / "winprob.duckdb"
REPORT_DIR = REPO_ROOT / "docs" / "results"
ELO_K_GRID = (16, 24, 32, 40, 48, 64)
ELO_SHRINK_GRID = (0.0, 0.25, 0.5, 0.75)
METRICS = ("early", "mid", "late", "total", "win", "lane_gold14")
MIN_METRIC_RELIABILITY = 0.3  # random split-half r a metric needs before any figure can be "some"/"strong"
WINDOWS = {"0-15 min": (0, 15), "15-25 min": (16, 25), "25+ min": (26, 999)}


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def make_models() -> dict:
    return {
        "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000)),
        "mlp": make_pipeline(
            StandardScaler(),
            MLPClassifier(hidden_layer_sizes=(32, 16), alpha=1e-3, early_stopping=True,
                          validation_fraction=0.15, max_iter=500, random_state=0),
        ),
    }


def train(cutoff: date) -> dict:
    con = duckdb.connect(str(DB_PATH), read_only=True, config={"threads": 2, "memory_limit": "1GB"})
    games = load_games(con)
    is_train = np.array([g.game_date < cutoff for g in games.rows])
    y_game = np.array([1.0 if g.blue_won else 0.0 for g in games.rows])
    print(f"{len(games.rows)} games: {is_train.sum()} train (before {cutoff}), {(~is_train).sum()} held out")

    # --- Team strength (Elo): K and break shrink chosen on training games only ------------
    best, best_loss, elo = (None, None), math.inf, {}
    for k in ELO_K_GRID:
        for shrink in ELO_SHRINK_GRID:
            pre = run_elo(games.rows, k, shrink)
            p = np.array([expected(*pre[g.game_id]) for g in games.rows])
            loss = log_loss(y_game[is_train], p[is_train])
            if loss < best_loss:
                best, best_loss, elo = (k, shrink), loss, pre
    best_k, best_shrink = best
    elo_diff = np.array([(elo[g.game_id][0] - elo[g.game_id][1]) / 400 for g in games.rows])
    print(f"Elo K={best_k}, break shrink={best_shrink}")

    # --- Pre-game model: side + team strength ------------------------------------------------
    pregame = LogisticRegression().fit(elo_diff[is_train].reshape(-1, 1), y_game[is_train])
    p_pre = pregame.predict_proba(elo_diff.reshape(-1, 1))[:, 1]
    blue_rate = float(y_game[is_train].mean())
    pregame_report = {
        "elo_k": best_k,
        "elo_break_shrink": best_shrink,
        "side_intercept": round(float(pregame.intercept_[0]), 4),
        "elo_coefficient": round(float(pregame.coef_[0][0]), 4),
        "train_blue_win_rate": round(blue_rate, 4),
        "test": summarize(y_game[~is_train], p_pre[~is_train], bins=10),
        "test_baseline_blue_rate": summarize(y_game[~is_train], np.full((~is_train).sum(), blue_rate), bins=10),
    }

    # --- In-game states ----------------------------------------------------------------------
    states = load_states(con)
    rows = np.array([games.index[g] for g in states["game_id"]])
    X = ingame_matrix(states, _logit(p_pre[rows]))
    y = y_game[rows]
    minute = states["minute"].astype(int)
    train_rows = is_train[rows]
    groups = rows

    candidates, model_reports, test_preds = make_models(), {}, {}
    with threadpool_limits(2):
        for name, model in candidates.items():
            model.fit(X[train_rows], y[train_rows])
            p = model.predict_proba(X[~train_rows])[:, 1]
            test_preds[name] = p
            per_window = {}
            for label, (lo, hi) in WINDOWS.items():
                mask = (minute[~train_rows] >= lo) & (minute[~train_rows] <= hi)
                per_window[label] = summarize(y[~train_rows][mask], p[mask])
            model_reports[name] = {"test": summarize(y[~train_rows], p), "by_window": per_window}
            print(f"  {name}: test accuracy {model_reports[name]['test']['accuracy']}, "
                  f"log loss {model_reports[name]['test']['log_loss']}, ECE {model_reports[name]['test']['ece']}")

    lr, mlp = model_reports["logistic_regression"]["test"], model_reports["mlp"]["test"]
    if mlp["ece"] < lr["ece"] - 0.005 or (abs(mlp["ece"] - lr["ece"]) <= 0.005 and mlp["log_loss"] < lr["log_loss"]):
        chosen = "mlp"
        verdict = "The MLP is better calibrated on held-out games, so it is used."
    else:
        chosen = "logistic_regression"
        verdict = "The MLP does not beat logistic regression on held-out calibration, so logistic regression is used."
    print(f"Chosen: {chosen}")

    lr_model = candidates["logistic_regression"]
    coefficients = dict(zip(INGAME_FEATURES, (round(float(c), 4) for c in lr_model[-1].coef_[0])))

    # --- Out-of-fold predictions for every state (no game scores itself) -------------------
    oof = np.zeros(len(y))
    with threadpool_limits(2):
        for fit_idx, pred_idx in GroupKFold(n_splits=5).split(X, y, groups):
            model = make_models()[chosen].fit(X[fit_idx], y[fit_idx])
            oof[pred_idx] = model.predict_proba(X[pred_idx])[:, 1]

    # --- WPA per team per game ---------------------------------------------------------------
    state_p = {(gid, int(m)): float(p) for gid, m, p in zip(states["game_id"], minute, oof)}
    durations = dict(con.execute("SELECT game_id, duration_s FROM game_context").fetchall())
    team_games: dict[tuple[str, str], W.TeamGameWPA] = {}
    skipped = 0
    for i, g in enumerate(games.rows):
        outcome_blue = y_game[i]
        path = [W.path_value(m, durations.get(g.game_id), state_p.get((g.game_id, m)), outcome_blue) for m in W.PHASE_MINUTES]
        if any(v is None for v in path):
            skipped += 1
            continue
        w15, w25 = path
        team_games[(g.game_id, g.blue_team)] = W.TeamGameWPA(float(p_pre[i]), w15, w25, outcome_blue)
        team_games[(g.game_id, g.red_team)] = W.TeamGameWPA(1 - float(p_pre[i]), 1 - w15, 1 - w25, 1 - outcome_blue)

    # --- Per-pick values: WPA by phase and lane gold at 14 minutes ---------------------------
    picks = con.execute("""
        SELECT a.game_id, a.team_id, a.champion_id, a.champion_name, a.role,
               b.champion_id AS opp_champion_id, b.champion_name AS opp_champion_name,
               l.gold_diff AS lane_gold14
        FROM player_games a
        LEFT JOIN player_games b ON a.game_id = b.game_id AND a.role = b.role AND a.team_id <> b.team_id
        LEFT JOIN lane_diffs l ON l.game_id = a.game_id AND l.player_id = a.player_id AND l.minute = 14
        WHERE a.role <> 'unknown'
    """).fetchall()
    dates = {g.game_id: g.game_date for g in games.rows}
    champ_values: dict[str, dict[tuple, list]] = {m: defaultdict(list) for m in METRICS}
    matchup_values: dict[str, dict[tuple, list]] = {m: defaultdict(list) for m in METRICS}
    context: dict[tuple, list] = defaultdict(list)  # (champ, role) -> [(w0, outcome)]
    names: dict[str, str] = {}
    for game_id, team_id, champ, name, role, opp, opp_name, lane_gold in picks:
        tg = team_games.get((game_id, team_id))
        if tg is None:
            continue
        names[champ] = name
        if opp:
            names[opp] = opp_name
        values = {"early": tg.early, "mid": tg.mid, "late": tg.late, "total": tg.total, "win": tg.outcome,
                  "lane_gold14": lane_gold}
        context[(champ, role)].append((tg.w0, tg.outcome))
        for metric in METRICS:
            if values[metric] is None:
                continue
            champ_values[metric][(champ, role)].append((game_id, float(values[metric])))
            if opp:
                matchup_values[metric][(champ, opp, role)].append((game_id, float(values[metric])))

    rng = np.random.default_rng(0)
    reliability = {
        metric: {
            "random_halves": W.split_half_reliability(champ_values[metric], dates, 30, rng),
            "by_season": _season_split(champ_values[metric], dates, cutoff, 20),
        }
        for metric in METRICS
    }

    champion_rows, tau = _shrunk_rows(champ_values, context, names, matchups=False)
    matchup_rows, _ = _shrunk_rows(matchup_values, None, names, matchups=True)

    # Metric-level gate: a metric that does not repeat between random halves overall cannot be
    # shown as more than weak evidence for any single champion, whatever its own shrinkage says
    # (tau itself is a noisy estimate when true effects are tiny).
    gated = [m for m in METRICS if (reliability[m]["random_halves"]["correlation"] or 0) < MIN_METRIC_RELIABILITY]
    for row in champion_rows + matchup_rows:
        for metric in gated:
            if f"{metric}_evidence" in row:
                row[f"{metric}_evidence"] = "weak"

    con.close()
    _write_outputs(games, p_pre, elo, states, oof, team_games, champion_rows, matchup_rows)

    evidence_counts = {
        metric: {label: sum(1 for r in champion_rows if r[f"{metric}_evidence"] == label and r["games"] >= 1)
                 for label in ("strong", "some", "weak")}
        for metric in METRICS
    }
    report = {
        "cutoff": str(cutoff),
        "games": {"total": len(games.rows), "train": int(is_train.sum()), "test": int((~is_train).sum())},
        "states": {"total": int(len(y)), "train": int(train_rows.sum()), "test": int((~train_rows).sum()),
                   "sample_minutes": "every 5 minutes"},
        "pregame": pregame_report,
        "ingame": model_reports,
        "chosen_model": chosen,
        "verdict": verdict,
        "logistic_regression_coefficients_standardized": coefficients,
        "wpa": {
            "team_games": len(team_games),
            "games_skipped_missing_states": skipped,
            "champion_roles": len(champion_rows),
            "reliability": reliability,
            "true_effect_sd_by_role": tau,
            "evidence_counts": evidence_counts,
            "evidence_cutoffs": {"strong": W.STRONG, "some": W.SOME},
            "min_metric_reliability": MIN_METRIC_RELIABILITY,
            "gated_metrics": gated,
        },
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "winprob-report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (REPORT_DIR / "winprob-report.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {OUT_DB} and {REPORT_DIR / 'winprob-report.md'}")
    return report


def _season_split(values: dict, dates: dict, cutoff: date, min_per_half: int) -> dict:
    """Correlation of group means between the training seasons and the held-out season."""
    pairs = []
    for items in values.values():
        a = [v for g, v in items if dates[g] < cutoff]
        b = [v for g, v in items if dates[g] >= cutoff]
        if len(a) >= min_per_half and len(b) >= min_per_half:
            pairs.append((np.mean(a), np.mean(b)))
    if len(pairs) < 5:
        return {"correlation": None, "groups": len(pairs)}
    return {"correlation": round(float(np.corrcoef(*np.array(pairs).T)[0, 1]), 3), "groups": len(pairs)}


def _shrunk_rows(values: dict, context: dict | None, names: dict, matchups: bool) -> tuple[list[dict], dict]:
    """One row per champion-role (or matchup), each metric shrunk within its role."""
    rows: dict[tuple, dict] = {}
    tau: dict[str, dict] = defaultdict(dict)
    for metric in METRICS:
        by_role: dict[str, dict] = defaultdict(dict)
        for key, items in values[metric].items():
            by_role[key[-1]][key] = [v for _, v in items]
        for role, groups in by_role.items():
            shrunk, summary = W.shrink(groups)
            tau[role][metric] = summary["tau"]
            for key, est in shrunk.items():
                row = rows.setdefault(key, _base_row(key, names, matchups))
                low, high = est.ci
                row["games"] = max(row["games"], len(groups[key]))
                row[f"{metric}_raw"] = round(est.raw, 4)
                row[metric] = round(est.estimate, 4)
                row[f"{metric}_low"] = round(low, 4)
                row[f"{metric}_high"] = round(high, 4)
                row[f"{metric}_reliability"] = round(est.reliability, 3)
                row[f"{metric}_evidence"] = W.evidence_label(est.reliability)
    if context:
        for key, row in rows.items():
            pairs = context.get(key, [])
            row["w0_mean"] = round(float(np.mean([w for w, _ in pairs])), 4) if pairs else None
    columns = sorted({c for r in rows.values() for c in r}, key=lambda c: (c not in _KEY_COLUMNS, c))
    return [{c: r.get(c) for c in columns} for r in rows.values()], dict(tau)


_KEY_COLUMNS = ("champion_id", "champion_name", "opp_champion_id", "opp_champion_name", "role", "games")


def _base_row(key: tuple, names: dict, matchups: bool) -> dict:
    if matchups:
        champ, opp, role = key
        return {"champion_id": champ, "champion_name": names[champ], "opp_champion_id": opp,
                "opp_champion_name": names[opp], "role": role, "games": 0}
    champ, role = key
    return {"champion_id": champ, "champion_name": names[champ], "role": role, "games": 0}


def _write_outputs(games, p_pre, elo, states, oof, team_games, champion_rows, matchup_rows) -> None:
    OUT_DB.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_DB.with_suffix(".tmp.duckdb")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp), config={"threads": 2, "memory_limit": "1GB"})
    con.execute("CREATE TABLE pregame (game_id VARCHAR, p_blue DOUBLE, elo_blue DOUBLE, elo_red DOUBLE)")
    con.executemany("INSERT INTO pregame VALUES (?, ?, ?, ?)",
                    [(g.game_id, float(p), *elo[g.game_id]) for g, p in zip(games.rows, p_pre)])
    con.execute("CREATE TABLE state_winprob (game_id VARCHAR, minute INTEGER, p_blue DOUBLE)")
    con.executemany("INSERT INTO state_winprob VALUES (?, ?, ?)",
                    [(g, int(m), float(p)) for g, m, p in zip(states["game_id"], states["minute"], oof)])
    con.execute("""CREATE TABLE team_game_wpa (game_id VARCHAR, team_id VARCHAR, w0 DOUBLE, w15 DOUBLE, w25 DOUBLE,
                   outcome DOUBLE, wpa_early DOUBLE, wpa_mid DOUBLE, wpa_late DOUBLE, wpa_total DOUBLE)""")
    con.executemany("INSERT INTO team_game_wpa VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [(gid, tid, t.w0, t.w15, t.w25, t.outcome, t.early, t.mid, t.late, t.total)
                     for (gid, tid), t in team_games.items()])
    for table, rows in (("champion_wpa", champion_rows), ("matchup_wpa", matchup_rows)):
        cols = list(rows[0].keys())
        types = {c: "INTEGER" if c == "games"
                 else "VARCHAR" if c.endswith(("_id", "_name", "_evidence")) or c == "role" else "DOUBLE" for c in cols}
        con.execute(f"CREATE TABLE {table} ({', '.join(f'{c} {types[c]}' for c in cols)})")
        con.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' for _ in cols)})", [tuple(r[c] for c in cols) for r in rows])
    con.close()
    OUT_DB.unlink(missing_ok=True)
    tmp.rename(OUT_DB)


def render_markdown(r: dict) -> str:
    def row(name, m):
        return f"| {name} | {m['n']:,} | {m['accuracy']:.3f} | {m['log_loss']:.3f} | {m['brier']:.3f} | {m['ece']:.3f} |"

    head = "| Model | States | Accuracy | Log loss | Brier | ECE |\n|---|---:|---:|---:|---:|---:|"
    lines = [
        "# Win-probability model report",
        "",
        f"Generated by `uv run python -m winprob.train`. Trained on games before {r['cutoff']}, evaluated on "
        f"{r['games']['test']} held-out games from {r['cutoff']} on ({r['states']['test']:,} game states sampled every 5 minutes). "
        "Split by game, never by state. Method follows xPetu (Aalto University, 2024); see the design doc.",
        "",
        "## Pre-game model (side + team strength)",
        "",
        f"Elo with K={r['pregame']['elo_k']} and break shrink {r['pregame']['elo_break_shrink']} (chosen on training games). Blue side won {r['pregame']['train_blue_win_rate']:.1%} of training games.",
        "",
        "| Model | Games | Accuracy | Log loss | Brier | ECE |\n|---|---:|---:|---:|---:|---:|",
        row("Side + Elo (logistic)", r["pregame"]["test"]),
        row("Baseline: blue win rate", r["pregame"]["test_baseline_blue_rate"]),
        "",
        "## In-game model",
        "",
        head,
        row("Logistic regression", r["ingame"]["logistic_regression"]["test"]),
        row("MLP (32, 16)", r["ingame"]["mlp"]["test"]),
        "",
        f"**{r['verdict']}**",
        "",
        "### By game-time window (held-out)",
        "",
        "| Window | Model | States | Accuracy | Log loss | ECE |\n|---|---|---:|---:|---:|---:|",
    ]
    for window in WINDOWS:
        for name, label in (("logistic_regression", "Logistic"), ("mlp", "MLP")):
            m = r["ingame"][name]["by_window"][window]
            lines.append(f"| {window} | {label} | {m['n']:,} | {m['accuracy']:.3f} | {m['log_loss']:.3f} | {m['ece']:.3f} |")
    chosen = r["ingame"][r["chosen_model"]]["test"]["reliability"]
    lines += [
        "",
        f"### Reliability ({r['chosen_model'].replace('_', ' ')}, held-out)",
        "",
        "| Predicted | Observed | States |\n|---:|---:|---:|",
        *[f"| {b['mean_predicted']:.2f} | {b['observed']:.2f} | {b['count']:,} |" for b in chosen],
        "",
        "### Logistic regression coefficients (standardized features)",
        "",
        "| Feature | Coefficient |\n|---|---:|",
        *[f"| `{k}` | {v:+.3f} |" for k, v in r["logistic_regression_coefficients_standardized"].items()],
        "",
        "## Pick WPA, and how much of it is signal",
        "",
        f"{r['wpa']['team_games']:,} team-games scored with out-of-fold win probabilities (5-fold, grouped by game), "
        f"{r['wpa']['champion_roles']} champion-role pairs.",
        "",
        "**Reliability check.** For each per-champion metric: the correlation of champion-role averages between two halves "
        "of the games. *Random halves* (5 random splits, at least 30 games per half) measures sampling noise alone; "
        "*by season* (2025 vs 2026, at least 20 games per half) adds real meta change. Near 0 means the metric is noise "
        "at this sample size.",
        "",
        "| Metric | Random halves r | Champion-roles | By season r | Champion-roles |\n|---|---:|---:|---:|---:|",
        *[f"| {METRIC_LABELS[m]} | {_fmt(v['random_halves']['correlation'])} | {v['random_halves']['groups']} "
          f"| {_fmt(v['by_season']['correlation'])} | {v['by_season']['groups']} |"
          for m, v in r["wpa"]["reliability"].items()],
        "",
        "**Shrinkage.** Each figure is shrunk toward its role average by empirical Bayes, keeping a share "
        "tau^2 / (tau^2 + se^2) of its observed difference (its *reliability*). The evidence label shown to coaches is "
        f"*strong* at reliability >= {r['wpa']['evidence_cutoffs']['strong']}, *some* at >= {r['wpa']['evidence_cutoffs']['some']}, "
        "otherwise *weak*. A metric whose random split-half r is below "
        f"{r['wpa']['min_metric_reliability']} is shown as weak everywhere: "
        f"{', '.join(METRIC_LABELS[m] for m in r['wpa']['gated_metrics']) or 'none'}.",
        "",
        "| Metric | Strong | Some | Weak |\n|---|---:|---:|---:|",
        *[f"| {METRIC_LABELS[m]} | {c['strong']} | {c['some']} | {c['weak']} |" for m, c in r["wpa"]["evidence_counts"].items()],
        "",
        "Estimated spread of *true* champion effects within a role (tau; lane gold in gold, the rest in win probability):",
        "",
        "| Role | " + " | ".join(METRIC_LABELS[m] for m in METRICS) + " |",
        "|---|" + "---:|" * len(METRICS),
        *[f"| {role} | " + " | ".join(str(t.get(m, "")) for m in METRICS) + " |"
          for role, t in sorted(r["wpa"]["true_effect_sd_by_role"].items())],
        "",
    ]
    return "\n".join(lines)


METRIC_LABELS = {"early": "WPA 0-15 min", "mid": "WPA 15-25 min", "late": "WPA 25+ min", "total": "WPA total",
                 "win": "Raw win rate", "lane_gold14": "Lane gold diff @14"}


def _fmt(x) -> str:
    return "n/a" if x is None else f"{x:+.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cutoff", type=date.fromisoformat, default=date(2026, 1, 1),
                        help="hold out games on or after this date (default 2026-01-01: the whole 2026 season)")
    train(parser.parse_args().cutoff)


if __name__ == "__main__":
    main()
