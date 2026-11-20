"""Derived tables built on top of the extracted feeds (run as the last build step).

    uv run python -m pipeline.derive    # re-derive without re-reading the feeds
"""

LANE_MINUTES = (10, 14, 20)


def derive(con) -> None:
    """``con`` is a writable DuckDB connection."""
    # Game context: event, stage, patch, date. Patch comes from meta/ (the feed's titleVersion is not reliable).
    con.execute("""
        CREATE OR REPLACE TABLE game_context AS
        SELECT g.*, s.event, s.stage, m.patch,
               CAST(substr(coalesce(CAST(g.started_at AS VARCHAR), s.scheduled_start), 1, 10) AS DATE) AS game_date
        FROM games g
        JOIN series s USING (series_id)
        LEFT JOIN meta_games m USING (game_id)
    """)

    # One row per player per lane-check minute, against the opposing player in the same role.
    minutes = ", ".join(str(m) for m in LANE_MINUTES)
    con.execute(f"""
        CREATE OR REPLACE TABLE lane_diffs AS
        WITH pm AS (
            SELECT pm.game_id, pm.minute, pg.team_id, pg.role, pg.player_id,
                   pg.champion_id, pg.champion_name, pm.gold_earned, pm.xp,
                   pm.lane_cs + pm.neutral_cs AS cs
            FROM player_minutes pm
            JOIN player_games pg USING (game_id, player_id)
            WHERE pm.minute IN ({minutes}) AND pg.role <> 'unknown'
            QUALIFY count(*) OVER (PARTITION BY pm.game_id, pm.minute, pg.team_id, pg.role) = 1
        )
        SELECT a.game_id, a.minute, a.role, a.team_id, a.player_id, a.champion_id, a.champion_name,
               b.team_id AS opp_team_id, b.player_id AS opp_player_id,
               b.champion_id AS opp_champion_id, b.champion_name AS opp_champion_name,
               a.gold_earned - b.gold_earned AS gold_diff,
               a.xp - b.xp AS xp_diff,
               a.cs - b.cs AS cs_diff
        FROM pm a
        JOIN pm b ON a.game_id = b.game_id AND a.minute = b.minute AND a.role = b.role AND a.team_id <> b.team_id
    """)


def main() -> None:
    import duckdb

    from .config import DB_PATH

    con = duckdb.connect(str(DB_PATH))
    derive(con)
    for table in ("game_context", "lane_diffs"):
        print(table, con.execute(f"SELECT count(*) FROM {table}").fetchone()[0], "rows")
    con.close()


if __name__ == "__main__":
    main()
