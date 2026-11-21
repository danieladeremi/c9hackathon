"""Load games and in-game states from the DuckDB file and turn them into model features.

All in-game features are blue minus red, so one row describes a game state from blue's side
and the label is "blue won". The red side's probability is 1 - p.

States are sampled every 5 minutes, as in the thesis, so consecutive near-identical states
do not dominate training. Item builds are deliberately excluded (as in the thesis).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .elo import GameRow

SAMPLE_MINUTES = tuple(range(5, 61, 5))

# Columns of the in-game feature matrix, in order.
INGAME_FEATURES = (
    "minute_scaled",       # minute / 30
    "gold_diff_k",         # team net worth difference, thousands
    "gold_x_time",         # gold lead scaled by game time: the same lead means less late
    "xp_diff_k",
    "kills_diff",
    "towers_diff",
    "inhibitors_diff",
    "dragons_diff",        # elemental drakes (excluding elder)
    "soul_diff",           # 4+ drakes: dragon soul
    "elders_diff",
    "barons_diff",
    "void_grubs_diff",
    "heralds_diff",
    "atakhans_diff",
    "pregame_logit",       # team-strength term from the pre-game model
)


@dataclass
class Games:
    rows: list[GameRow]
    index: dict[str, int]


def load_games(con) -> Games:
    raw = con.execute("""
        SELECT game_id, game_date, blue_team_id, red_team_id, winner_team_id = blue_team_id AS blue_won
        FROM game_context WHERE winner_team_id IS NOT NULL
        ORDER BY started_at
    """).fetchall()
    rows = [GameRow(r[0], r[1], r[2], r[3], bool(r[4])) for r in raw]
    return Games(rows, {g.game_id: i for i, g in enumerate(rows)})


def load_states(con, minutes: tuple[int, ...] = SAMPLE_MINUTES) -> dict[str, np.ndarray]:
    """Blue-minus-red team state at each sampled minute, one row per (game, minute)."""
    minute_list = ", ".join(str(m) for m in minutes)
    result = con.execute(f"""
        SELECT t.game_id, t.minute,
               sum(CASE WHEN t.team_id = g.blue_team_id THEN 1 ELSE -1 END * t.net_worth) AS gold,
               sum(CASE WHEN t.team_id = g.blue_team_id THEN 1 ELSE -1 END * t.xp) AS xp,
               sum(CASE WHEN t.team_id = g.blue_team_id THEN 1 ELSE -1 END * t.kills) AS kills,
               sum(CASE WHEN t.team_id = g.blue_team_id THEN 1 ELSE -1 END * t.towers_destroyed) AS towers,
               sum(CASE WHEN t.team_id = g.blue_team_id THEN 1 ELSE -1 END * t.inhibitors_destroyed) AS inhibitors,
               sum(CASE WHEN t.team_id = g.blue_team_id THEN 1 ELSE -1 END * t.drakes) AS dragons,
               sum(CASE WHEN t.team_id = g.blue_team_id THEN 1 ELSE -1 END
                   * CASE WHEN t.drakes >= 4 THEN 1 ELSE 0 END) AS soul,
               sum(CASE WHEN t.team_id = g.blue_team_id THEN 1 ELSE -1 END * t.elders) AS elders,
               sum(CASE WHEN t.team_id = g.blue_team_id THEN 1 ELSE -1 END * t.barons) AS barons,
               sum(CASE WHEN t.team_id = g.blue_team_id THEN 1 ELSE -1 END * t.void_grubs) AS grubs,
               sum(CASE WHEN t.team_id = g.blue_team_id THEN 1 ELSE -1 END * t.heralds) AS heralds,
               sum(CASE WHEN t.team_id = g.blue_team_id THEN 1 ELSE -1 END * t.atakhans) AS atakhans
        FROM team_minutes t JOIN game_context g USING (game_id)
        WHERE t.minute IN ({minute_list}) AND g.winner_team_id IS NOT NULL
        GROUP BY 1, 2 HAVING count(*) = 2
        ORDER BY 1, 2
    """)
    return result.fetchnumpy()


def ingame_matrix(states: dict[str, np.ndarray], pregame_logit: np.ndarray) -> np.ndarray:
    """Feature matrix for ``states``; ``pregame_logit`` is aligned row by row."""
    minute = states["minute"].astype(float)
    gold_k = states["gold"].astype(float) / 1000
    columns = [
        minute / 30,
        gold_k,
        gold_k * minute / 30,
        states["xp"].astype(float) / 1000,
        states["kills"].astype(float),
        states["towers"].astype(float),
        states["inhibitors"].astype(float),
        states["dragons"].astype(float),
        states["soul"].astype(float),
        states["elders"].astype(float),
        states["barons"].astype(float),
        states["grubs"].astype(float),
        states["heralds"].astype(float),
        states["atakhans"].astype(float),
        pregame_logit,
    ]
    return np.column_stack(columns)
