"""Predictor backtest tests use only small synthetic DuckDB tables."""

from datetime import date, timedelta
import json

import duckdb
from fastapi.testclient import TestClient

from planner import api, stats
from planner.backtest import run_backtest


def _database(path):
    con = duckdb.connect(str(path))
    con.execute("""
        CREATE TABLE game_context (
            game_id VARCHAR, game_date DATE, game_number INTEGER, series_id VARCHAR,
            draft_action_count INTEGER, blue_team_id VARCHAR, red_team_id VARCHAR,
            first_pick_team_id VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE draft_actions (
            game_id VARCHAR, seq INTEGER, team_id VARCHAR, action VARCHAR,
            champion_id VARCHAR, champion_name VARCHAR
        )
    """)
    return con


def _add_game(con, game_id, game_date, game_number, series_id, action_rows, draft_action_count=None):
    con.execute("INSERT INTO game_context VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
        game_id, game_date, game_number, series_id,
        len(action_rows) if draft_action_count is None else draft_action_count,
        "blue", "red", "blue",
    ])
    con.executemany("INSERT INTO draft_actions VALUES (?, ?, ?, ?, ?, ?)", [
        (game_id, seq, team, action, champion, champion.title() if champion else None)
        for seq, team, action, champion in action_rows
    ])


def _target_rows(team, champion, sparse_team="O"):
    rows = []
    for seq in range(1, 21):
        action = "ban" if seq <= 6 or 13 <= seq <= 16 else "pick"
        if seq == 1:
            rows.append((seq, team, action, champion))
        elif seq == 2:
            rows.append((seq, sparse_team, action, "other"))
        elif seq == 3:
            rows.append((seq, team, action, None))
        else:
            rows.append((seq, "U", action, f"target-{seq}"))
    return rows


def test_predict_next_before_excludes_same_day_and_later(tmp_path):
    con = _database(tmp_path / "draft.duckdb")
    try:
        _add_game(con, "old", date(2026, 1, 1), 1, "old-series", [(1, "T", "ban", "old")])
        _add_game(con, "same", date(2026, 1, 2), 1, "same-series", [(1, "T", "ban", "same")])
        _add_game(con, "later", date(2026, 1, 3), 1, "later-series", [(1, "T", "ban", "later")])

        prediction = stats.predict_next(
            con, "T", "ban", "ban1", set(), game_number=1, before=date(2026, 1, 2),
        )

        assert prediction["games"] == 1
        assert [candidate["champion_id"] for candidate in prediction["candidates"]] == ["old"]
    finally:
        con.close()


def test_shared_ranking_weights_game_number_and_breaks_ties_deterministically():
    ranked = stats.rank_candidates([
        {"champion_id": "a", "name": "Alpha", "count": 2, "same_game_number": 0},
        {"champion_id": "b", "name": "Bravo", "count": 1, "same_game_number": 1},
        {"champion_id": "c", "name": "Charlie", "count": 2, "same_game_number": 0},
    ], set(), top=3)

    assert [row["champion_id"] for row in ranked] == ["b", "a", "c"]
    assert [row["score"] for row in ranked] == [3, 2, 2]


def test_backtest_top_k_skips_and_fearless_locks(tmp_path):
    con = _database(tmp_path / "draft.duckdb")
    try:
        for i in range(10):
            champ = "A" if i < 5 else "B" if i < 8 else "C"
            _add_game(con, f"history-{i}", date(2026, 1, 1) + timedelta(days=i), 1,
                      f"history-series-{i}", [(1, "T", "ban", champ)], draft_action_count=1)
        _add_game(con, "sparse-history", date(2026, 1, 11), 1, "sparse-series",
                  [(1, "O", "ban", "A")], draft_action_count=1)

        # This incomplete earlier game contributes a Fearless pick, but its ban must not lock B.
        _add_game(con, "series-game-1", date(2026, 2, 1), 1, "fearless-series",
                  [(1, "P", "ban", "B"), (7, "P", "pick", "A")], draft_action_count=19)
        _add_game(con, "target-1", date(2026, 2, 1), 2, "fearless-series",
                  _target_rows("T", "B"), draft_action_count=20)
        _add_game(con, "target-2", date(2026, 2, 2), 1, "another-series",
                  _target_rows("T", "C"), draft_action_count=20)

        result = run_backtest(con, cutoff=date(2026, 1, 1), limit=2)

        ban1 = result["by_phase"]["ban1"]
        assert ban1["slots"] == 2
        assert ban1["team"]["top_1"]["hits"] == 1
        assert ban1["team"]["top_3"]["hits"] == 2
        assert ban1["team"]["top_5"]["hits"] == 2
        assert ban1["team"]["top_3"]["rate"] == 1.0
        assert ban1["skipped_null_action"] == 2
        assert ban1["skipped_insufficient_history"] == 8

        # The same deterministic team ranker is used by predict_next and the backtest;
        # A is Fearless-locked while the prior game's ban on B does not carry over.
        prediction = stats.predict_next(
            con, "T", "ban", "ban1", {"A"}, game_number=2, before=date(2026, 2, 1),
        )
        assert prediction["candidates"][0]["champion_id"] == "B"
    finally:
        con.close()


def test_backtest_keeps_same_day_games_out_of_each_others_history(tmp_path):
    con = _database(tmp_path / "draft.duckdb")
    try:
        for i, champ in enumerate(("A", "A", "A", "B", "B", "B", "C", "C", "C", "C")):
            _add_game(con, f"history-{i}", date(2026, 1, 1) + timedelta(days=i), 1,
                      f"history-series-{i}", [(1, "T", "ban", champ)], draft_action_count=1)
        _add_game(con, "same-day-a", date(2026, 2, 1), 1, "same-day-series-a",
                  _target_rows("T", "B"), draft_action_count=20)
        _add_game(con, "same-day-b", date(2026, 2, 1), 1, "same-day-series-b",
                  _target_rows("T", "B"), draft_action_count=20)

        result = run_backtest(con, cutoff=date(2026, 1, 1), limit=2)

        top1 = result["by_phase"]["ban1"]["team"]["top_1"]
        assert top1["slots"] == 2
        assert top1["hits"] == 0
    finally:
        con.close()


def test_backtest_empty_metrics_have_no_fabricated_rates(tmp_path):
    con = _database(tmp_path / "draft.duckdb")
    try:
        _add_game(con, "sparse-target", date(2026, 2, 1), 1, "sparse-target-series",
                  _target_rows("new-team", "A"), draft_action_count=20)
        result = run_backtest(con, cutoff=date(2026, 1, 1))

        top3 = result["by_phase"]["ban1"]["team"]["top_3"]
        assert top3["slots"] == 0
        assert top3["rate"] is None
        assert top3["sufficient_sample"] is False
    finally:
        con.close()


def test_predictor_accuracy_api_missing_and_present_results(tmp_path, monkeypatch):
    result_path = tmp_path / "predictor-backtest.json"
    monkeypatch.setattr(api, "BACKTEST_RESULTS_PATH", result_path)
    with TestClient(api.app) as client:
        missing = client.get("/api/predictor/accuracy")
        assert missing.status_code == 404
        assert "backtest" in missing.json()["detail"].lower()

        metric = {"hits": 1, "slots": 2, "rate": 0.5, "sufficient_sample": False}
        scope = {
            "slots": 2,
            "skipped_insufficient_history": 1,
            "skipped_null_action": 0,
            "team": {"top_1": metric, "top_3": metric, "top_5": metric},
            "league_popularity": {"top_1": metric, "top_3": metric, "top_5": metric},
        }
        payload = {
            "cutoff": "2026-01-01",
            "holdout_games": 1,
            "evaluated_slots": 2,
            "minimum_history_games": 10,
            "minimum_evaluation_slots": 30,
            "by_action": {"ban": scope, "pick": scope},
            "by_phase": {phase: scope for phase in ("ban1", "pick1", "ban2", "pick2")},
        }
        result_path.write_text(json.dumps(payload), encoding="utf-8")

        response = client.get("/api/predictor/accuracy")

    assert response.status_code == 200
    assert response.json()["by_phase"]["ban1"]["team"]["top_3"]["slots"] == 2