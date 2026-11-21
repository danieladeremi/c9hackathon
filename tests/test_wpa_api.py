"""WPA routes against a tiny synthetic results file (no GRID data)."""

import threading

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from planner import wpa_api

METRICS = ("early", "mid", "late", "total", "win", "lane_gold14")


def _row(champ, name, role, games, lane, lane_ev, **extra):
    row = {"champion_id": champ, "champion_name": name, "role": role, "games": games, "w0_mean": 0.5}
    for m in METRICS:
        for suffix in ("", "_raw", "_low", "_high", "_reliability"):
            row[f"{m}{suffix}"] = 0.0
        row[f"{m}_evidence"] = "weak"
    row.update({"lane_gold14": lane, "lane_gold14_evidence": lane_ev, **extra})
    return row


def _create(con, table, rows):
    cols = list(rows[0])
    types = {c: "INTEGER" if c == "games" else "VARCHAR" if c.endswith(("_id", "_name", "_evidence")) or c == "role" else "DOUBLE"
             for c in cols}
    con.execute(f"CREATE TABLE {table} ({', '.join(f'{c} {types[c]}' for c in cols)})")
    con.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' for _ in cols)})", [tuple(r[c] for c in cols) for r in rows])


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "winprob.duckdb"
    con = duckdb.connect(str(db))
    _create(con, "champion_wpa", [
        _row("a", "Alpha", "top", 40, 300.0, "strong"),
        _row("b", "Bravo", "top", 30, 100.0, "some"),
        _row("c", "Charlie", "top", 2, 900.0, "weak"),   # big number, thin evidence: must not top the list
        _row("z", "Zulu", "top", 50, -50.0, "strong"),
    ])
    m = _row("b", "Bravo", "top", 12, 450.0, "some")
    m.update({"opp_champion_id": "z", "opp_champion_name": "Zulu"})
    thin = _row("a", "Alpha", "top", 3, -200.0, "weak")   # thin head-to-head must not bury a strong overall figure
    thin.update({"opp_champion_id": "z", "opp_champion_name": "Zulu"})
    _create(con, "matchup_wpa", [m, thin])
    con.close()
    monkeypatch.setattr(wpa_api, "WINPROB_DB", db)
    monkeypatch.setattr(wpa_api, "_local", threading.local())
    app = FastAPI()
    app.include_router(wpa_api.router)
    yield TestClient(app)
    wpa_api.close_connections()


def test_candidates_put_thin_evidence_last(client):
    names = [c["name"] for c in client.get("/api/wpa/candidates", params={"role": "top", "min_games": 1}).json()["candidates"]]
    assert names == ["Alpha", "Bravo", "Zulu", "Charlie"]


def test_candidates_use_head_to_head_when_enemy_known(client):
    body = client.get("/api/wpa/candidates", params={"role": "top", "opp_champion_id": "z", "exclude": ["a"]}).json()
    names = [c["name"] for c in body["candidates"]]
    assert names[0] == "Bravo"           # +450 vs Zulu beats its own +100 overall
    assert "Alpha" not in names          # excluded (e.g. Fearless-locked)
    assert body["opp_name"] == "Zulu"
    assert body["candidates"][0]["vs"]["games"] == 12


def test_role_is_validated(client):
    assert client.get("/api/wpa/champions", params={"role": "carry"}).status_code == 422


def test_weak_head_to_head_falls_back_to_overall(client):
    body = client.get("/api/wpa/candidates", params={"role": "top", "opp_champion_id": "z"}).json()
    names = [c["name"] for c in body["candidates"]]
    assert names[:2] == ["Bravo", "Alpha"]  # Bravo +450 h2h (some), then Alpha's strong +300 overall
    alpha = body["candidates"][1]
    assert alpha["vs"]["lane_gold14"]["evidence"] == "weak"
