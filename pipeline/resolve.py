"""Second pass over roles, using each player's history.

Per-game role inference from positions is noisy (early lane swaps were common in 2025),
but a pro player's role rarely changes. So each player gets a *main role* from all their
games, and a team-game uses those main roles whenever the five are distinct. Otherwise
(a real role swap or a substitute) the per-game inference is kept.
"""

MIN_GAMES_FOR_MAIN_ROLE = 3


def resolve_roles(con) -> None:
    """``con`` is a DuckDB connection (not imported here, so build workers never load DuckDB)."""
    con.execute("ALTER TABLE player_games RENAME COLUMN role TO role_from_game")
    con.execute(f"""
        CREATE TABLE player_main_roles AS
        SELECT player_id,
               arg_max(role_from_game, n) AS main_role,
               round(max(n) * 1.0 / sum(n), 3) AS main_role_share,
               sum(n) AS games
        FROM (SELECT player_id, role_from_game, count(*) AS n
              FROM player_games WHERE role_from_game <> 'unknown' GROUP BY 1, 2)
        GROUP BY 1
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE player_games AS
        WITH team_games AS (
            SELECT pg.game_id, pg.team_id,
                   count(DISTINCT m.main_role) = 5
                   AND count(*) = 5
                   AND min(coalesce(m.games, 0)) >= {MIN_GAMES_FOR_MAIN_ROLE} AS use_main
            FROM player_games pg LEFT JOIN player_main_roles m USING (player_id)
            GROUP BY 1, 2
        )
        SELECT pg.*,
               CASE WHEN tg.use_main THEN m.main_role ELSE pg.role_from_game END AS role,
               CASE WHEN tg.use_main THEN 'player history' ELSE 'this game' END AS role_source
        FROM player_games pg
        JOIN team_games tg USING (game_id, team_id)
        LEFT JOIN player_main_roles m USING (player_id)
    """)
