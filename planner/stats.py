"""Read-only statistics over the DuckDB file. Every number comes with its sample size."""

from __future__ import annotations

from datetime import date
from typing import Any

PHASE_SQL = """CASE WHEN d.seq <= 6 THEN 'ban1' WHEN d.seq <= 12 THEN 'pick1'
                    WHEN d.seq <= 16 THEN 'ban2' ELSE 'pick2' END"""


def _rows(con, sql: str, params: list | None = None) -> list[dict[str, Any]]:
    result = con.execute(sql, params or [])
    cols = [c[0] for c in result.description]
    return [dict(zip(cols, row)) for row in result.fetchall()]


def rank_candidates(rows: list[dict], unavailable: set[str], top: int | None = None) -> list[dict]:
    """Use one stable score and tie-break order for live predictions and backtests."""
    candidates = []
    for row in rows:
        if row["champion_id"] is None or row["champion_id"] in unavailable:
            continue
        candidate = dict(row)
        candidate["score"] = int(row["count"]) + 2 * int(row.get("same_game_number") or 0)
        candidates.append(candidate)
    candidates.sort(key=lambda r: (-r["score"], str(r["name"]).casefold(), str(r["champion_id"])))
    total = sum(r["score"] for r in candidates) or 1
    ranked = [{**r, "probability": round(r["score"] / total, 3)} for r in candidates]
    return ranked if top is None else ranked[:top]


def _game_filter(team_id: str, game_number: int | None, since: date | None) -> tuple[str, list]:
    clauses = ["(g.blue_team_id = ? OR g.red_team_id = ?)", "g.draft_action_count = 20"]
    params: list = [team_id, team_id]
    if game_number:
        clauses.append("g.game_number = ?")
        params.append(game_number)
    if since:
        clauses.append("g.game_date >= ?")
        params.append(since)
    return " AND ".join(clauses), params


def teams(con) -> list[dict]:
    return _rows(con, """
        WITH tg AS (
            SELECT blue_team_id AS team_id, game_date, event FROM game_context
            UNION ALL SELECT red_team_id, game_date, event FROM game_context)
        SELECT tg.team_id, t.name, count(*) AS games, max(game_date) AS last_game,
               arg_max(event, game_date) AS last_event
        FROM tg JOIN meta_teams t USING (team_id)
        GROUP BY 1, 2 ORDER BY last_game DESC, games DESC
    """)


def champions(con) -> list[dict]:
    return _rows(con, """
        SELECT pg.champion_id, any_value(pg.champion_name) AS name, count(*) AS games,
               round(avg(CASE WHEN pg.won THEN 1 ELSE 0 END), 3) AS win_rate,
               arg_max(pg.role, cnt) AS main_role
        FROM (SELECT *, count(*) OVER (PARTITION BY champion_id, role) AS cnt FROM player_games) pg
        GROUP BY 1 ORDER BY name
    """)


def tendencies(con, team_id: str, game_number: int | None = None, since: date | None = None) -> dict:
    """What a team bans and picks, overall or for one game number of a series."""
    where, params = _game_filter(team_id, game_number, since)
    n_games = con.execute(f"SELECT count(*) FROM game_context g WHERE {where}", params).fetchone()[0]
    bans = _rows(con, f"""
        SELECT d.champion_id, any_value(d.champion_name) AS name, count(*) AS count,
               round(count(*) / ?, 3) AS rate,
               sum(CASE WHEN d.seq <= 6 THEN 1 ELSE 0 END) AS phase1,
               sum(CASE WHEN d.seq > 12 THEN 1 ELSE 0 END) AS phase2
        FROM draft_actions d JOIN game_context g USING (game_id)
        WHERE {where} AND d.team_id = ? AND d.action = 'ban' AND d.champion_id IS NOT NULL
        GROUP BY 1 ORDER BY count DESC, name LIMIT 30
    """, [max(n_games, 1), *params, team_id])
    picks = _rows(con, f"""
        SELECT d.champion_id, any_value(d.champion_name) AS name, count(*) AS count,
               round(count(*) / ?, 3) AS rate,
               sum(CASE WHEN pg.won THEN 1 ELSE 0 END) AS wins,
               mode(pg.role) AS role, mode(pg.player_name) AS player,
               sum(CASE WHEN d.seq <= 12 THEN 1 ELSE 0 END) AS phase1,
               sum(CASE WHEN d.seq > 12 THEN 1 ELSE 0 END) AS phase2
        FROM draft_actions d JOIN game_context g USING (game_id)
        LEFT JOIN player_games pg ON pg.game_id = d.game_id AND pg.team_id = d.team_id AND pg.champion_id = d.champion_id
        WHERE {where} AND d.team_id = ? AND d.action = 'pick'
        GROUP BY 1 ORDER BY count DESC, name LIMIT 30
    """, [max(n_games, 1), *params, team_id])
    bans_against = _rows(con, f"""
        SELECT d.champion_id, any_value(d.champion_name) AS name, count(*) AS count,
               round(count(*) / ?, 3) AS rate
        FROM draft_actions d JOIN game_context g USING (game_id)
        WHERE {where} AND d.team_id <> ? AND d.action = 'ban' AND d.champion_id IS NOT NULL
        GROUP BY 1 ORDER BY count DESC, name LIMIT 15
    """, [max(n_games, 1), *params, team_id])
    return {"team_id": team_id, "game_number": game_number, "games": n_games,
            "bans": bans, "picks": picks, "bans_against": bans_against}


def roster(con, team_id: str) -> list[dict]:
    """Players from the team's most recent game, with their role."""
    return _rows(con, """
        WITH last AS (
            SELECT game_id FROM player_games pg JOIN game_context g USING (game_id)
            WHERE pg.team_id = ? ORDER BY g.started_at DESC LIMIT 1)
        SELECT pg.player_id, pg.player_name AS name, pg.role
        FROM player_games pg WHERE pg.game_id = (SELECT game_id FROM last) AND pg.team_id = ?
        ORDER BY array_position(['top','jungle','mid','bot','support'], pg.role)
    """, [team_id, team_id])


def champion_pools(con, team_id: str, since: date | None = None) -> list[dict]:
    """Each current player's champions in pro games (any team), most played first."""
    players = roster(con, team_id)
    if not players:
        return []
    ids = [p["player_id"] for p in players]
    placeholders = ", ".join("?" for _ in ids)
    params: list = [*ids]
    date_clause = ""
    if since:
        date_clause = "AND g.game_date >= ?"
        params.append(since)
    rows = _rows(con, f"""
        SELECT pg.player_id, pg.champion_id, any_value(pg.champion_name) AS name, count(*) AS games,
               sum(CASE WHEN pg.won THEN 1 ELSE 0 END) AS wins, max(g.game_date) AS last_played
        FROM player_games pg JOIN game_context g USING (game_id)
        WHERE pg.player_id IN ({placeholders}) {date_clause}
        GROUP BY 1, 2 ORDER BY games DESC, last_played DESC
    """, params)
    by_player: dict[str, list] = {p["player_id"]: [] for p in players}
    for row in rows:
        by_player[row.pop("player_id")].append(row)
    return [{**p, "champions": by_player[p["player_id"]]} for p in players]


def matchups(con, role: str, champion_id: str, minute: int = 14, min_games: int = 1) -> dict:
    """Lane results for a champion in a role against each opponent: gold, XP and CS difference."""
    rows = _rows(con, """
        SELECT opp_champion_id AS champion_id, any_value(opp_champion_name) AS name, count(*) AS games,
               round(avg(gold_diff)) AS gold_diff, round(avg(xp_diff)) AS xp_diff, round(avg(cs_diff), 1) AS cs_diff,
               round(stddev_samp(gold_diff) / sqrt(count(*))) AS gold_diff_se
        FROM lane_diffs WHERE role = ? AND champion_id = ? AND minute = ?
        GROUP BY 1 HAVING count(*) >= ? ORDER BY games DESC
    """, [role, champion_id, minute, min_games])
    overall = con.execute("""
        SELECT count(*), round(avg(gold_diff)) FROM lane_diffs WHERE role = ? AND champion_id = ? AND minute = ?
    """, [role, champion_id, minute]).fetchone()
    return {"role": role, "champion_id": champion_id, "minute": minute,
            "games": overall[0], "gold_diff": overall[1], "opponents": rows}


def predict_next(con, team_id: str, action: str, phase: str, unavailable: set[str],
                 game_number: int | None = None, top: int = 10, before: date | None = None) -> dict:
    """Likely next ban or pick by a team in a draft phase, from its history.

    Score = phase count over all games + 2 x phase count in the same game number
    (Fearless changes behaviour by game). Unavailable champions are removed and the
    rest renormalised. A deliberately simple baseline; its hit rate is measured offline.
    """
    seq_range = {"ban1": (1, 6), "pick1": (7, 12), "ban2": (13, 16), "pick2": (17, 20)}[phase]
    date_filter = "AND g.game_date < ?" if before is not None else ""
    date_params = [before] if before is not None else []
    rows = _rows(con, f"""
        SELECT d.champion_id, min(d.champion_name) AS name, count(*) AS count,
               sum(CASE WHEN g.game_number = ? THEN 1 ELSE 0 END) AS same_game_number
        FROM draft_actions d JOIN game_context g USING (game_id)
        WHERE d.team_id = ? AND d.action = ? AND d.seq BETWEEN ? AND ? AND d.champion_id IS NOT NULL
          {date_filter}
        GROUP BY 1
    """, [game_number or 0, team_id, action, *seq_range, *date_params])
    candidates = rank_candidates(rows, unavailable, top)
    games_in_phase = con.execute(f"""
        SELECT count(DISTINCT d.game_id)
        FROM draft_actions d JOIN game_context g USING (game_id)
        WHERE d.team_id = ? AND d.action = ? AND d.seq BETWEEN ? AND ? {date_filter}
    """, [team_id, action, *seq_range, *date_params]).fetchone()[0]
    return {
        "team_id": team_id, "action": action, "phase": phase, "games": games_in_phase,
        "candidates": candidates,
    }
