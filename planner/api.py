"""HTTP API for the draft board.

    uv run uvicorn planner.api:app --reload --port 8000
"""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from datetime import date
import json
from typing import Literal

import duckdb
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from pipeline.config import DB_PATH, REPO_ROOT

from . import stats
from .rules import DRAFT_ORDER, DraftError, Game, Series, phase_of

C9_TEAM_ID = "47351"  # Cloud9 Kia in the GRID LoL data
BACKTEST_RESULTS_PATH = REPO_ROOT / "docs" / "results" / "predictor-backtest.json"

_local = threading.local()
_connections: list = []
_lock = threading.Lock()


@asynccontextmanager
async def lifespan(_app):
    yield
    with _lock:
        for con in _connections:
            con.close()
        _connections.clear()


app = FastAPI(title="C9 Draft Planner", lifespan=lifespan)


class HitRate(BaseModel):
    hits: int
    slots: int
    rate: float | None
    sufficient_sample: bool


class PredictorScope(BaseModel):
    slots: int
    skipped_insufficient_history: int
    skipped_null_action: int
    team: dict[Literal["top_1", "top_3", "top_5"], HitRate]
    league_popularity: dict[Literal["top_1", "top_3", "top_5"], HitRate]


class PredictorAccuracy(BaseModel):
    cutoff: date
    holdout_games: int
    evaluated_slots: int
    minimum_history_games: int
    minimum_evaluation_slots: int
    by_action: dict[Literal["ban", "pick"], PredictorScope]
    by_phase: dict[Literal["ban1", "pick1", "ban2", "pick2"], PredictorScope]


def db():
    """One read-only DuckDB connection per server thread."""
    con = getattr(_local, "con", None)
    if con is None:
        if not DB_PATH.exists():
            raise HTTPException(503, "Database not built. Run: uv run python -m pipeline.build")
        con = duckdb.connect(str(DB_PATH), read_only=True, config={"threads": 2, "memory_limit": "512MB"})
        _local.con = con
        with _lock:
            _connections.append(con)
    return con


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "c9_team_id": C9_TEAM_ID}


@app.get("/api/teams")
def get_teams() -> list[dict]:
    return stats.teams(db())


@app.get("/api/champions")
def get_champions() -> list[dict]:
    return stats.champions(db())


@app.get("/api/teams/{team_id}/tendencies")
def get_tendencies(team_id: str, game_number: int | None = Query(None, ge=1, le=5), since: date | None = None) -> dict:
    return stats.tendencies(db(), team_id, game_number, since)


@app.get("/api/teams/{team_id}/pools")
def get_pools(team_id: str, since: date | None = None) -> list[dict]:
    return stats.champion_pools(db(), team_id, since)


@app.get("/api/matchups")
def get_matchups(role: str, champion_id: str, minute: int = Query(14, ge=10, le=20)) -> dict:
    return stats.matchups(db(), role, champion_id, minute)


@app.get("/api/predictor/accuracy", response_model=PredictorAccuracy)
def get_predictor_accuracy() -> PredictorAccuracy:
    """Return the aggregate holdout report without exposing per-game rows."""
    if not BACKTEST_RESULTS_PATH.exists():
        raise HTTPException(404, "Predictor backtest results not found. Run: uv run python -m planner.backtest")
    return PredictorAccuracy.model_validate(json.loads(BACKTEST_RESULTS_PATH.read_text(encoding="utf-8")))


class GameIn(BaseModel):
    blue_team: str
    red_team: str
    first_pick_team: str
    actions: list[str | None] = Field(default_factory=list)
    winner: str | None = None


class SeriesIn(BaseModel):
    team_a: str
    team_b: str
    format: str = "bo5"
    games: list[GameIn] = Field(default_factory=list)
    since: date | None = None


def _series(body: SeriesIn) -> Series:
    try:
        return Series(body.team_a, body.team_b, body.format, [Game(**g.model_dump()) for g in body.games])
    except DraftError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/draft/order")
def get_order() -> list[dict]:
    return [{"seq": i, "action": a, "who": w, "phase": phase_of(i)} for i, (a, w) in enumerate(DRAFT_ORDER, 1)]


@app.post("/api/draft/state")
def draft_state(body: SeriesIn) -> dict:
    """Everything the board needs for the current slot: who acts, what is unavailable and why,
    the acting team's likely choices, and both teams' remaining Fearless pools."""
    series = _series(body)
    con = db()
    games_out = []
    for index, game in enumerate(series.games):
        unavailable = series.unavailable(index)
        next_slot = None
        if not game.complete:
            seq = len(game.actions) + 1
            action, team = game.slot(seq)
            phase = phase_of(seq)
            prediction = stats.predict_next(con, team, action, phase, set(unavailable), index + 1)
            next_slot = {"seq": seq, "action": action, "team_id": team, "phase": phase, "prediction": prediction}
        games_out.append({
            "index": index,
            "next": next_slot,
            "unavailable": unavailable,
            "fearless_locked": {c: {"game": n, "team_id": t} for c, (n, t) in series.fearless_locked(index).items()},
        })

    current = series.current_game_index()
    locked_now = set(series.unavailable(current)) if current is not None else set()
    pools = {}
    for team in (series.team_a, series.team_b):
        players = stats.champion_pools(con, team, body.since)
        for player in players:
            for champ in player["champions"]:
                champ["available"] = champ["champion_id"] not in locked_now
            player["champions"] = player["champions"][:12]
        pools[team] = players
    return {"games": games_out, "current_game": current, "wins": series.wins(),
            "decided": series.decided, "pools": pools}


@app.post("/api/draft/validate")
def validate(body: SeriesIn) -> dict:
    """Replays every action through the rules and reports the first illegal one, if any."""
    clean = Series(body.team_a, body.team_b, body.format,
                   [Game(g.blue_team, g.red_team, g.first_pick_team, [], g.winner) for g in body.games])
    for index, game in enumerate(body.games):
        for seq, champ in enumerate(game.actions, 1):
            try:
                clean.apply(index, champ)
            except DraftError as exc:
                return {"valid": False, "game": index + 1, "seq": seq, "error": str(exc)}
    return {"valid": True}
