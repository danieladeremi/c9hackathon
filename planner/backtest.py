"""Chronological holdout evaluation for the opponent next-action predictor."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import json
from typing import Any

import duckdb

from pipeline.config import DB_PATH, REPO_ROOT

from . import stats
from .rules import DRAFT_ORDER, Game, Series, phase_of

CUTOFF = date(2026, 1, 1)
MIN_HISTORY_GAMES = 10
MIN_EVALUATION_SLOTS = 30
TOP_K = (1, 3, 5)
PHASES = ("ban1", "pick1", "ban2", "pick2")
RESULTS_PATH = REPO_ROOT / "docs" / "results" / "predictor-backtest.json"


def _load_games(con) -> list[dict[str, Any]]:
    """Fetch one compact joined history so per-slot work never queries DuckDB."""
    rows = con.execute("""
        SELECT g.game_id, g.game_date, g.game_number, g.series_id, g.draft_action_count,
               g.blue_team_id, g.red_team_id, g.first_pick_team_id,
               d.seq, d.team_id, d.action, d.champion_id, d.champion_name
        FROM game_context g
        LEFT JOIN draft_actions d USING (game_id)
        WHERE g.game_date IS NOT NULL
        ORDER BY g.game_date, g.series_id, g.game_number, g.game_id, d.seq
    """).fetchall()
    columns = [column[0] for column in con.description]
    games: dict[str, dict[str, Any]] = {}
    for values in rows:
        row = dict(zip(columns, values))
        game = games.setdefault(row["game_id"], {
            "game_id": row["game_id"], "game_date": row["game_date"],
            "game_number": row["game_number"], "series_id": row["series_id"],
            "draft_action_count": row["draft_action_count"],
            "blue_team_id": row["blue_team_id"], "red_team_id": row["red_team_id"],
            "first_pick_team_id": row["first_pick_team_id"], "actions": [],
        })
        if row["seq"] is not None:
            game["actions"].append({
                "seq": row["seq"], "team_id": row["team_id"], "action": row["action"],
                "champion_id": row["champion_id"], "champion_name": row["champion_name"],
            })
    return list(games.values())


def _fearless_locks(games: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Ask the rules engine for prior-series picks, preserving recorded pick/ban types."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for game in games:
        grouped[game["series_id"] or f"game:{game['game_id']}"].append(game)

    locked_by_game: dict[str, set[str]] = {}
    pick_slots = [i for i, (action, _who) in enumerate(DRAFT_ORDER) if action == "pick"]
    for series_games in grouped.values():
        series_games.sort(key=lambda g: (
            g["game_number"] is None, g["game_number"] or 0, g["game_date"], str(g["game_id"]),
        ))
        first = series_games[0]
        team_a, team_b = first["blue_team_id"], first["red_team_id"]
        if not team_a or not team_b or team_a == team_b:
            locked_by_game.update((g["game_id"], set()) for g in series_games)
            continue

        rule_games = []
        valid_games = []
        for game in series_games:
            first_pick = game["first_pick_team_id"]
            if first_pick not in (team_a, team_b):
                locked_by_game[game["game_id"]] = set()
                continue
            picked = [a["champion_id"] for a in game["actions"]
                      if a["action"] == "pick" and a["champion_id"] is not None]
            actions = [None] * 20
            for slot, champion_id in zip(pick_slots, picked):
                actions[slot] = champion_id
            rule_games.append(Game(team_a, team_b, first_pick, actions))
            valid_games.append(game)

        if not rule_games:
            continue
        series = Series(team_a, team_b, "bo5", rule_games)
        for index, game in enumerate(valid_games):
            locked_by_game[game["game_id"]] = set(series.fearless_locked(index))
    return locked_by_game


def _scope() -> dict[str, Any]:
    return {
        "slots": 0,
        "skipped_insufficient_history": 0,
        "skipped_null_action": 0,
        "team_hits": Counter(),
        "league_hits": Counter(),
    }


def _final_scope(scope: dict[str, Any]) -> dict[str, Any]:
    slots = scope["slots"]
    output = {
        "slots": slots,
        "skipped_insufficient_history": scope["skipped_insufficient_history"],
        "skipped_null_action": scope["skipped_null_action"],
    }
    for model_key, hits_key in (("team", "team_hits"), ("league_popularity", "league_hits")):
        output[model_key] = {
            f"top_{k}": {
                "hits": scope[hits_key][k],
                "slots": slots,
                "rate": scope[hits_key][k] / slots if slots else None,
                "sufficient_sample": slots >= MIN_EVALUATION_SLOTS,
            }
            for k in TOP_K
        }
    return output


def _accumulator() -> dict[str, Any]:
    return {"by_action": defaultdict(_scope), "by_phase": defaultdict(_scope)}


def _update_history(game: dict[str, Any], team_counts: dict, team_games: dict, league_counts: dict) -> None:
    for action_row in game["actions"]:
        action = action_row["action"]
        team_id = action_row["team_id"]
        seq = action_row["seq"]
        if action not in ("ban", "pick") or not team_id or not seq:
            continue
        phase = phase_of(seq)
        team_key = (team_id, action, phase)
        team_games[team_key].add(game["game_id"])
        champion_id = action_row["champion_id"]
        if champion_id is None:
            continue

        team_champions = team_counts[team_key]
        champion = team_champions.setdefault(champion_id, {
            "champion_id": champion_id,
            "name": action_row["champion_name"] or champion_id,
            "count": 0,
            "game_numbers": Counter(),
        })
        champion["count"] += 1
        champion["game_numbers"][game["game_number"]] += 1
        if action_row["champion_name"]:
            champion["name"] = min(champion["name"], action_row["champion_name"])

        league_champions = league_counts[(action, phase)]
        league_champion = league_champions.setdefault(champion_id, {
            "champion_id": champion_id,
            "name": action_row["champion_name"] or champion_id,
            "count": 0,
            "same_game_number": 0,
        })
        league_champion["count"] += 1
        if action_row["champion_name"]:
            league_champion["name"] = min(league_champion["name"], action_row["champion_name"])


def _team_candidates(team_counts: dict, team_id: str, action: str, phase: str,
                     game_number: int | None, unavailable: set[str]) -> list[dict]:
    champions = team_counts.get((team_id, action, phase), {})
    rows = [{
        "champion_id": champion["champion_id"],
        "name": champion["name"],
        "count": champion["count"],
        "same_game_number": champion["game_numbers"].get(game_number, 0),
    } for champion in champions.values()]
    return stats.rank_candidates(rows, unavailable, top=5)


def _evaluate_game(game: dict[str, Any], locked: set[str], history: dict, result: dict) -> None:
    team_counts, team_games, league_counts = history
    unavailable = set(locked)
    for action_row in sorted(game["actions"], key=lambda row: row["seq"]):
        action = action_row["action"]
        team_id = action_row["team_id"]
        seq = action_row["seq"]
        champion_id = action_row["champion_id"]
        if action not in ("ban", "pick") or not team_id or not seq:
            if champion_id is not None:
                unavailable.add(champion_id)
            continue

        phase = phase_of(seq)
        scopes = (result["by_action"][action], result["by_phase"][phase])
        if champion_id is None:
            for scope in scopes:
                scope["skipped_null_action"] += 1
            continue

        phase_games = len(team_games.get((team_id, action, phase), ()))
        if phase_games < MIN_HISTORY_GAMES:
            for scope in scopes:
                scope["skipped_insufficient_history"] += 1
            unavailable.add(champion_id)
            continue

        actual = str(champion_id)
        game_number = game["game_number"]
        team_ranked = _team_candidates(team_counts, team_id, action, phase, game_number, unavailable)
        league_rows = league_counts.get((action, phase), {}).values()
        league_ranked = stats.rank_candidates(list(league_rows), unavailable, top=5)
        for scope in scopes:
            scope["slots"] += 1
            for k in TOP_K:
                if actual in {str(c["champion_id"]) for c in team_ranked[:k]}:
                    scope["team_hits"][k] += 1
                if actual in {str(c["champion_id"]) for c in league_ranked[:k]}:
                    scope["league_hits"][k] += 1
        unavailable.add(champion_id)


def run_backtest(con, cutoff: date = CUTOFF, limit: int | None = None) -> dict[str, Any]:
    """Evaluate complete holdout drafts while keeping all same-day games out of history."""
    games = _load_games(con)
    holdout = sorted(
        (game for game in games if game["draft_action_count"] == 20 and game["game_date"] >= cutoff),
        key=lambda game: (game["game_date"], game["game_number"] or 0, str(game["game_id"])),
    )
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be a positive number of holdout games")
        holdout = holdout[:limit]
    test_ids = {game["game_id"] for game in holdout}
    locks = _fearless_locks(games)
    aggregate = _accumulator()
    team_counts: dict = defaultdict(dict)
    team_games: dict = defaultdict(set)
    league_counts: dict = defaultdict(dict)
    history = (team_counts, team_games, league_counts)
    last_test_date = holdout[-1]["game_date"] if holdout else None
    holdout_by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
    games_by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for game in games:
        games_by_date[game["game_date"]].append(game)
        if game["game_id"] in test_ids:
            holdout_by_date[game["game_date"]].append(game)

    for game_date in sorted(games_by_date):
        if last_test_date is None or game_date > last_test_date:
            break
        # History remains fixed during a date, so every test game excludes every same-day draft.
        for game in holdout_by_date.get(game_date, ()):
            _evaluate_game(game, locks.get(game["game_id"], set()), history, aggregate)
        for game in games_by_date[game_date]:
            _update_history(game, *history)

    return {
        "cutoff": cutoff.isoformat(),
        "holdout_games": len(holdout),
        "evaluated_slots": sum(aggregate["by_action"][action]["slots"] for action in ("ban", "pick")),
        "minimum_history_games": MIN_HISTORY_GAMES,
        "minimum_evaluation_slots": MIN_EVALUATION_SLOTS,
        "by_action": {action: _final_scope(aggregate["by_action"][action]) for action in ("ban", "pick")},
        "by_phase": {phase: _final_scope(aggregate["by_phase"][phase]) for phase in PHASES},
    }


def _print_table(result: dict[str, Any]) -> None:
    print(f"Predictor backtest, game dates from {result['cutoff']} ({result['holdout_games']} holdout games)")
    print("Scope       Slots  Insufficient  Null  Team top-1/3/5       League top-1/3/5")
    for label, scope in [*result["by_action"].items(), *result["by_phase"].items()]:
        if scope["slots"] == 0:
            team_rates = league_rates = "n/a"
        else:
            team_rates = "/".join(_percent(scope["team"][f"top_{k}"]["rate"]) for k in TOP_K)
            league_rates = "/".join(_percent(scope["league_popularity"][f"top_{k}"]["rate"]) for k in TOP_K)
        print(f"{label:<11} {scope['slots']:>5}  {scope['skipped_insufficient_history']:>12}  "
              f"{scope['skipped_null_action']:>4}  {team_rates:<19} {league_rates}")


def _percent(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate * 100:.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description="Chronological backtest of draft next-action predictions")
    parser.add_argument("--cutoff", type=date.fromisoformat, default=CUTOFF,
                        help="first holdout game date (inclusive; default: 2026-01-01)")
    parser.add_argument("--limit", type=int, help="evaluate only the first N holdout games")
    args = parser.parse_args()
    if not DB_PATH.exists():
        parser.error(f"draft database not found: {DB_PATH}")

    con = duckdb.connect(str(DB_PATH), read_only=True, config={"threads": 2, "memory_limit": "1GB"})
    try:
        result = run_backtest(con, args.cutoff, args.limit)
    finally:
        con.close()

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    _print_table(result)
    print(f"Aggregate results written to {RESULTS_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()