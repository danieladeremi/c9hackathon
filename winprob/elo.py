"""Team strength: Elo ratings computed game by game, with no look-ahead.

Each game gets both teams' ratings *before* it was played, so the pre-game model never sees
the result it predicts. After a long break (a new split) ratings shrink toward the mean,
because rosters and form change between splits.

Leagues in this data (LCK, LEC, LTA, LCS) barely play each other, so ratings are only
comparable within a league. That is fine here: every game is within one league.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

BASE = 1500.0
BREAK_DAYS = 30
BREAK_SHRINK = 0.25


@dataclass(frozen=True)
class GameRow:
    game_id: str
    game_date: date
    blue_team: str
    red_team: str
    blue_won: bool


def expected(r_a: float, r_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((r_b - r_a) / 400.0))


def run_elo(games: list[GameRow], k: float, shrink: float = BREAK_SHRINK) -> dict[str, tuple[float, float]]:
    """game_id -> (blue rating, red rating) before the game. ``games`` must be in time order.
    ``shrink`` is the share of a rating's distance from the mean removed after a break."""
    ratings: dict[str, float] = {}
    last_played: dict[str, date] = {}
    pre: dict[str, tuple[float, float]] = {}
    for g in games:
        for team in (g.blue_team, g.red_team):
            r = ratings.get(team, BASE)
            last = last_played.get(team)
            if last and (g.game_date - last).days > BREAK_DAYS:
                r = BASE + (r - BASE) * (1 - shrink)
            ratings[team] = r
        rb, rr = ratings[g.blue_team], ratings[g.red_team]
        pre[g.game_id] = (rb, rr)
        delta = k * ((1.0 if g.blue_won else 0.0) - expected(rb, rr))
        ratings[g.blue_team] = rb + delta
        ratings[g.red_team] = rr - delta
        last_played[g.blue_team] = last_played[g.red_team] = g.game_date
    return pre
