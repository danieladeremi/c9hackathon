"""Data-quality report for the built DuckDB file.

    uv run python -m pipeline.checks
"""

import duckdb

from .config import DB_PATH

CHECKS = {
    "games (feed) vs games (meta)": """
        SELECT (SELECT count(*) FROM games) AS feed_games,
               (SELECT count(*) FROM meta_games WHERE finished = 'True') AS meta_finished_games,
               (SELECT count(*) FROM meta_games m WHERE finished = 'True'
                  AND game_id NOT IN (SELECT game_id FROM games)) AS meta_missing_from_feed""",
    "games with winner disagreeing with meta": """
        SELECT count(*) AS mismatches FROM games g JOIN meta_games m USING (game_id)
        WHERE g.winner_team_id IS DISTINCT FROM m.winner_team_id""",
    "draft completeness (actions per game)": """
        SELECT draft_action_count, count(*) AS games FROM games GROUP BY 1 ORDER BY 1""",
    "Fearless: repeated picks within a series": """
        SELECT count(*) AS repeated_picks FROM (
          SELECT series_id, champion_id FROM draft_actions WHERE action = 'pick'
          GROUP BY 1, 2 HAVING count(*) > 1)""",
    "first pick team side": """
        SELECT CASE WHEN first_pick_team_id = blue_team_id THEN 'blue' ELSE 'red' END AS first_pick_side,
               count(*) AS games FROM games GROUP BY 1""",
    "team-games without exactly one of each role": """
        SELECT count(*) AS bad_team_games FROM (
          SELECT game_id, team_id FROM player_games GROUP BY 1, 2
          HAVING count(DISTINCT role) <> 5 OR count(*) <> 5)""",
    "where each final role came from": """
        SELECT role_source, count(*) AS player_games FROM player_games GROUP BY 1""",
    "per-game inference agreeing with final role": """
        SELECT round(avg(CASE WHEN role = role_from_game THEN 1 ELSE 0 END), 3) AS agreement FROM player_games""",
    "role confidence": """
        SELECT role, round(avg(role_confidence), 2) AS avg_conf,
               sum(CASE WHEN role_confidence < 0.4 THEN 1 ELSE 0 END) AS low_conf
        FROM player_games GROUP BY 1 ORDER BY 1""",
    "players whose role varies (main role share < 90%)": """
        SELECT count(*) AS players, sum(CASE WHEN share < 0.9 THEN 1 ELSE 0 END) AS inconsistent FROM (
          SELECT player_id, max(n) * 1.0 / sum(n) AS share FROM (
            SELECT player_id, role, count(*) AS n FROM player_games GROUP BY 1, 2) GROUP BY 1
          HAVING sum(n) >= 10)""",
    "Cloud9 Kia games by event": """
        SELECT s.event, count(DISTINCT pg.game_id) AS games,
               round(avg(CASE WHEN pg.won THEN 1 ELSE 0 END), 2) AS win_rate
        FROM player_games pg JOIN series s USING (series_id)
        WHERE pg.team_id = '47351' GROUP BY 1 ORDER BY 1""",
}


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    for title, sql in CHECKS.items():
        print(f"\n== {title}")
        result = con.execute(sql)
        cols = [d[0] for d in result.description]
        print("  " + " | ".join(cols))
        for row in result.fetchall():
            print("  " + " | ".join(str(v) for v in row))


if __name__ == "__main__":
    main()
