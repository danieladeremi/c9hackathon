"""API routes for win-probability results (data/winprob.duckdb, built by `uv run python -m winprob.train`).

Mounted by planner/api.py with ``app.include_router(router)``. Every figure carries its sample
size, its shrunk estimate and an evidence label (strong / some / weak) from measured reliability.
"""

from __future__ import annotations

import json
import threading

import duckdb
from fastapi import APIRouter, HTTPException, Query

from pipeline.config import REPO_ROOT, WORK_DIR

WINPROB_DB = WORK_DIR / "winprob.duckdb"
REPORT_JSON = REPO_ROOT / "docs" / "results" / "winprob-report.json"
ROLES = ("top", "jungle", "mid", "bot", "support")
# Metrics a coach sees, in display order. Total WPA is shown (shrunk) but is weak evidence everywhere.
METRICS = ("lane_gold14", "early", "total")

router = APIRouter(prefix="/api/wpa", tags=["win probability"])
_local = threading.local()
_connections: list = []
_lock = threading.Lock()


def winprob_db():
    con = getattr(_local, "con", None)
    if con is None:
        if not WINPROB_DB.exists():
            raise HTTPException(503, "Win-probability tables not built. Run: uv run python -m winprob.train")
        con = duckdb.connect(str(WINPROB_DB), read_only=True, config={"threads": 2, "memory_limit": "256MB"})
        _local.con = con
        with _lock:
            _connections.append(con)
    return con


def close_connections() -> None:
    with _lock:
        for con in _connections:
            con.close()
        _connections.clear()


def _rows(con, sql: str, params: list) -> list[dict]:
    result = con.execute(sql, params)
    cols = [c[0] for c in result.description]
    return [dict(zip(cols, r)) for r in result.fetchall()]


def _metric_block(row: dict, metric: str, prefix: str = "") -> dict:
    key = f"{prefix}{metric}"
    return {
        "estimate": row.get(key),
        "raw": row.get(f"{key}_raw"),
        "low": row.get(f"{key}_low"),
        "high": row.get(f"{key}_high"),
        "evidence": row.get(f"{key}_evidence"),
    }


def _shape(row: dict) -> dict:
    return {
        "champion_id": row["champion_id"],
        "name": row["champion_name"],
        "role": row["role"],
        "games": row["games"],
        "win_rate_raw": row.get("win_raw"),
        "w0_mean": row.get("w0_mean"),
        **{m: _metric_block(row, m) for m in METRICS},
    }


@router.get("/report")
def report() -> dict:
    """Model evaluation and reliability summary (aggregate numbers only)."""
    if not REPORT_JSON.exists():
        raise HTTPException(404, "No report yet. Run: uv run python -m winprob.train")
    return json.loads(REPORT_JSON.read_text(encoding="utf-8"))


@router.get("/champions")
def champions(role: str = Query(..., pattern="^(top|jungle|mid|bot|support)$"), min_games: int = Query(1, ge=1)) -> list[dict]:
    """Every champion seen in a role, sorted by shrunk lane gold at 14 minutes."""
    rows = _rows(winprob_db(), """
        SELECT * FROM champion_wpa WHERE role = ? AND games >= ? ORDER BY lane_gold14 DESC NULLS LAST
    """, [role, min_games])
    return [_shape(r) for r in rows]


@router.get("/candidates")
def candidates(
    role: str = Query(..., pattern="^(top|jungle|mid|bot|support)$"),
    opp_champion_id: str | None = None,
    exclude: list[str] = Query(default=[]),
    limit: int = Query(15, ge=1, le=60),
    min_games: int = Query(10, ge=1),
) -> dict:
    """Pick candidates for a role in the current slot.

    With the enemy laner known (``opp_champion_id``), each candidate also gets its head-to-head
    lane result against that champion. Sorting uses the head-to-head estimate when its evidence is
    at least "some", else the champion's overall lane estimate. Unavailable champions go in ``exclude``.
    """
    con = winprob_db()
    rows = _rows(con, "SELECT * FROM champion_wpa WHERE role = ? AND games >= ?", [role, min_games])
    excluded = set(exclude)
    matchups = {}
    if opp_champion_id:
        for m in _rows(con, "SELECT * FROM matchup_wpa WHERE role = ? AND opp_champion_id = ?", [role, opp_champion_id]):
            matchups[m["champion_id"]] = m

    out = []
    for row in rows:
        if row["champion_id"] in excluded:
            continue
        item = _shape(row)
        m = matchups.get(row["champion_id"])
        item["vs"] = None
        # The figure used: head-to-head when it has at least "some" evidence, else the champion overall.
        used = item["lane_gold14"]
        if m:
            item["vs"] = {"games": m["games"], "lane_gold14": _metric_block(m, "lane_gold14"), "early": _metric_block(m, "early")}
            if m.get("lane_gold14_evidence") in ("strong", "some"):
                used = item["vs"]["lane_gold14"]
        sort_key = used["estimate"] or 0.0
        # Thin evidence sinks: rank by estimate, but weak figures after the rest.
        evidence_rank = 0 if used["evidence"] in ("strong", "some") else 1
        out.append((evidence_rank, -sort_key, item))
    out.sort(key=lambda t: (t[0], t[1]))
    opp_name = None
    if opp_champion_id:
        found = con.execute("SELECT any_value(champion_name) FROM champion_wpa WHERE champion_id = ?", [opp_champion_id]).fetchone()
        opp_name = found[0] if found else None
    return {"role": role, "opp_champion_id": opp_champion_id, "opp_name": opp_name,
            "candidates": [item for *_, item in out[:limit]]}
