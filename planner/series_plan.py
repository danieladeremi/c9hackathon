"""What-if series planner: "if we take X in game 1, what is left for games 3-5?"

A plan is a list of hypothetical picks (team, champion, game number). For a chosen later game, every
current player's comfort pool on both teams is shown with each champion's status at the start of
that game:

- ``gone``     picked in a real game already drafted (Fearless-locked for both teams)
- ``planned``  used by the plan before that game
- ``at_risk``  still open, but the *other* team is likely to take it first (the Fearless forecast)
- ``open``

Depth = share of a player's pro games on champions still open; ``expected`` depth also discounts
at-risk champions by the chance the other team takes them. Comparing depth with and without the
plan shows what the plan does to each player.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import stats
from .rules import SERIES_GAMES, Series
from .series_value import future_game_probabilities, league_rates, use_forecast

AT_RISK = 0.25        # show a champion as at risk from this chance of being taken by the other team
THIN_OPEN_COUNT = 2   # a player with this many or fewer open pool champions is flagged
THIN_SHARE = 0.35     # ...or with less than this share of their pro games still open
POOL_SIZE = 10


@dataclass(frozen=True)
class PlannedPick:
    game_number: int
    team_id: str
    champion_id: str


class PlanError(ValueError):
    pass


def _real_picks_before(series: Series, game_number: int) -> dict[str, tuple[int, str]]:
    """Champion -> (game, team) for every pick in real games numbered below ``game_number``."""
    out: dict[str, tuple[int, str]] = {}
    for number, game in enumerate(series.games[: game_number - 1], 1):
        for team, champs in game.picks().items():
            for champ in champs:
                out[champ] = (number, team)
    return out


def current_game_number(series: Series) -> int:
    index = series.current_game_index()
    return (index if index is not None else len(series.games)) + 1


def validate_plan(series: Series, plan: list[PlannedPick], names: dict[str, str] | None = None) -> None:
    name = (names or {}).get
    max_games = SERIES_GAMES[series.format]
    now = current_game_number(series)
    seen: dict[str, PlannedPick] = {}
    real_all = _real_picks_before(series, max_games + 1)
    for p in plan:
        if p.team_id not in (series.team_a, series.team_b):
            raise PlanError("planned picks must belong to one of the series' teams")
        if not now <= p.game_number <= max_games:
            raise PlanError(f"plan games must be between game {now} and game {max_games}")
        if p.champion_id in real_all:
            n, _ = real_all[p.champion_id]
            raise PlanError(f"{name(p.champion_id, p.champion_id)} was already picked in game {n}")
        if p.champion_id in seen:
            raise PlanError(f"{name(p.champion_id, p.champion_id)} is planned twice: Fearless allows one pick per series")
        seen[p.champion_id] = p
    per_game_team: dict[tuple[int, str], int] = {}
    for p in plan:
        key = (p.game_number, p.team_id)
        per_game_team[key] = per_game_team.get(key, 0) + 1
        if per_game_team[key] > 5:
            raise PlanError(f"more than 5 planned picks for one team in game {p.game_number}")


def _horizon(series: Series, at_game: int) -> tuple[float, float]:
    """(expected number of games played from now until ``at_game`` - 1, P(``at_game`` is played))."""
    now = current_game_number(series)
    if at_game <= now:
        return 0.0, 1.0
    # Score before game `now`, which is certain to be played (it is being drafted, or is next).
    before = {series.team_a: 0, series.team_b: 0}
    for game in series.games[: now - 1]:
        if game.winner in before:
            before[game.winner] += 1
    later = future_game_probabilities(series.format, before[series.team_a], before[series.team_b])
    # later[i] = P(game now + 1 + i is played)
    gap = at_game - now - 1
    played_before = 1.0 + sum(later[:gap])
    p_at_game = later[gap] if gap < len(later) else 0.0
    return played_before, p_at_game


def plan_pools(con, series: Series, plan: list[PlannedPick], at_game: int, names: dict[str, str]) -> dict:
    max_games = SERIES_GAMES[series.format]
    now = current_game_number(series)
    if not now <= at_game <= max_games:
        raise PlanError(f"choose a game between {now} and {max_games}")
    validate_plan(series, plan, names)

    gone = _real_picks_before(series, at_game)
    # The game being drafted now counts too, once it is behind the chosen game.
    planned = {p.champion_id: p for p in plan if p.game_number < at_game}
    horizon, p_at_game = _horizon(series, at_game)
    league = league_rates(con)

    teams_out = []
    for team, other in ((series.team_a, series.team_b), (series.team_b, series.team_a)):
        other_takes = use_forecast(con, other, horizon, league) if horizon > 0 else {}
        players = []
        for player in stats.champion_pools(con, team):
            pool = player["champions"][:POOL_SIZE]
            total_games = sum(c["games"] for c in pool) or 1
            champs, open_now, open_plan, expected_plan = [], 0.0, 0.0, 0.0
            open_count = 0
            for c in pool:
                cid = c["champion_id"]
                status, detail = "open", None
                if cid in gone:
                    n, by = gone[cid]
                    status, detail = "gone", {"game": n, "team_id": by}
                elif cid in planned:
                    p = planned[cid]
                    status, detail = "planned", {"game": p.game_number, "team_id": p.team_id}
                risk = 0.0
                if cid not in gone:
                    open_now += c["games"]
                if status == "open":
                    risk = round(other_takes.get(cid, 0.0), 3)
                    if risk >= AT_RISK:
                        status = "at_risk"
                    open_plan += c["games"]
                    expected_plan += c["games"] * (1 - risk)
                    open_count += 1
                champs.append({"champion_id": cid, "name": c["name"], "games": c["games"], "status": status,
                               "detail": detail, "risk": risk})
            share_plan = open_plan / total_games
            players.append({
                "player_id": player["player_id"], "name": player["name"], "role": player["role"],
                "champions": champs,
                "open_count": open_count,
                "depth_without_plan": round(open_now / total_games, 3),
                "depth_with_plan": round(share_plan, 3),
                "expected_depth": round(expected_plan / total_games, 3),
                "thin": open_count <= THIN_OPEN_COUNT or share_plan < THIN_SHARE,
            })
        teams_out.append({"team_id": team, "players": players})

    return {
        "at_game": at_game,
        "current_game": now,
        "p_at_game_played": round(p_at_game, 3),
        "expected_games_before": round(horizon, 2),
        "plan": [{"game_number": p.game_number, "team_id": p.team_id, "champion_id": p.champion_id,
                  "name": names.get(p.champion_id, p.champion_id)} for p in plan],
        "thresholds": {"at_risk": AT_RISK, "thin_open_count": THIN_OPEN_COUNT, "thin_share": THIN_SHARE},
        "teams": teams_out,
    }
