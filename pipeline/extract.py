"""Turn one GRID LoL series feed into flat rows: games, draft actions, players, minute snapshots."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .feed import StateTracker, iter_events
from .roles import EARLY_END_S, EARLY_START_S, EarlyProfile, assign_roles

JUNGLE_ITEM_MARKERS = ("jungle", "hatchling", "seedling", "scorchclaw")
ROLE_SNAPSHOT_MINUTE = 10
# Each column sums these GRID objective types. 2025 feeds only record the typed drakes (no
# generic "slayDragon"), so drakes are counted by type to stay consistent across seasons.
OBJECTIVE_COLUMNS = {
    "drakes": ("slayCloudDrake", "slayOceanDrake", "slayInfernalDrake", "slayMountainDrake",
               "slayHextechDrake", "slayChemtechDrake"),
    "elders": ("slayElderDragon",),
    "barons": ("slayBaron",),
    "void_grubs": ("slayVoidGrub",),
    "heralds": ("slayRiftHerald",),
    "atakhans": ("slayVoraciousAtakhan", "slayRuinousAtakhan", "slayAtakhan"),
}


def _count_objective(entity: dict, objective_type: str) -> int:
    for obj in entity.get("objectives") or []:
        if obj.get("type") == objective_type:
            return int(obj.get("completionCount") or 0)
    return 0


def _unit_kills(player: dict, unit: str) -> int:
    for entry in player.get("unitKills") or []:
        if entry.get("unitName") == unit:
            return int(entry.get("count") or 0)
    return 0


def _has_jungle_item(player: dict) -> bool:
    items = (player.get("inventory") or {}).get("items") or []
    return any(any(m in (item.get("name") or "").lower() for m in JUNGLE_ITEM_MARKERS) for item in items)


# Some feeds briefly report nonsense clock values (seen: ~35,000,000 s). Without a guard
# the minute loop would "catch up" by writing hundreds of thousands of snapshots.
MAX_GAME_SECONDS = 6000
MAX_CLOCK_JUMP_S = 300


def _clock_seconds(game: dict) -> int | None:
    clock = game.get("clock") or {}
    seconds = clock.get("currentSeconds")
    return int(seconds) if seconds is not None else None


@dataclass
class _GameProgress:
    next_minute: int = 1
    last_seconds: int = 0
    profiles: dict[str, EarlyProfile] = field(default_factory=dict)

    def accept_clock(self, seconds: int | None) -> int | None:
        """Return the clock if plausible, else None (and keep the last good value)."""
        if seconds is None or seconds < 0 or seconds > MAX_GAME_SECONDS:
            return None
        if self.last_seconds and seconds - self.last_seconds > MAX_CLOCK_JUMP_S:
            return None
        self.last_seconds = max(self.last_seconds, seconds)
        return seconds


def _team_row(series_id: str, game: dict, team: dict, minute: int) -> dict[str, Any]:
    row: dict[str, Any] = {
        "series_id": series_id,
        "game_id": game["id"],
        "minute": minute,
        "team_id": team["id"],
        "side": team.get("side"),
        "net_worth": team.get("netWorth") or 0,
        "xp": team.get("experiencePoints") or 0,
        "kills": team.get("kills") or 0,
        "deaths": team.get("deaths") or 0,
    }
    for column, grid_types in OBJECTIVE_COLUMNS.items():
        row[column] = sum(_count_objective(team, t) for t in grid_types)
    destroyed = defaultdict(int)
    for structure in game.get("structures") or []:
        if structure.get("destroyed") and structure.get("teamId") != team["id"]:
            destroyed[structure.get("type")] += 1
    row["towers_destroyed"] = destroyed.get("tower", 0)
    row["inhibitors_destroyed"] = destroyed.get("fortifier", 0)
    return row


def _player_row(series_id: str, game: dict, team: dict, player: dict, minute: int) -> dict[str, Any]:
    position = player.get("position") or {}
    return {
        "series_id": series_id,
        "game_id": game["id"],
        "minute": minute,
        "team_id": team["id"],
        "player_id": player["id"],
        "net_worth": player.get("netWorth") or 0,
        "gold_earned": player.get("totalMoneyEarned") or 0,
        "xp": player.get("experiencePoints") or 0,
        "level": _count_objective(player, "increaseLevel") + 1,
        "kills": player.get("kills") or 0,
        "deaths": player.get("deaths") or 0,
        "assists": player.get("killAssistsGiven") or 0,
        "lane_cs": _unit_kills(player, "minion"),
        "neutral_cs": _unit_kills(player, "neutralMinion"),
        "x": position.get("x"),
        "y": position.get("y"),
        "alive": player.get("alive"),
    }


def extract_series(path: Path | str) -> dict[str, list[dict[str, Any]]]:
    tracker = StateTracker()
    progress: dict[str, _GameProgress] = defaultdict(_GameProgress)
    team_minutes: list[dict] = []
    player_minutes: list[dict] = []
    series_id = ""

    for envelope, event in iter_events(path):
        series_id = envelope.get("seriesId") or series_id
        tracker.apply(event)
        for game in tracker.games():
            if not game.get("started") or game.get("finished"):
                continue
            prog = progress[game["id"]]
            seconds = prog.accept_clock(_clock_seconds(game))
            if seconds is None:
                continue
            teams = game.get("teams") or []

            if EARLY_START_S <= seconds <= EARLY_END_S:
                for team in teams:
                    for player in team.get("players") or []:
                        pos = player.get("position")
                        if pos and pos.get("x") is not None and player.get("alive", True):
                            profile = prog.profiles.setdefault(player["id"], EarlyProfile(player["id"]))
                            profile.add_position(pos["x"], pos["y"])

            while seconds >= prog.next_minute * 60:
                minute = prog.next_minute
                for team in teams:
                    team_minutes.append(_team_row(series_id, game, team, minute))
                    for player in team.get("players") or []:
                        player_minutes.append(_player_row(series_id, game, team, player, minute))
                        if minute == ROLE_SNAPSHOT_MINUTE:
                            profile = prog.profiles.setdefault(player["id"], EarlyProfile(player["id"]))
                            profile.neutral_cs = _unit_kills(player, "neutralMinion")
                            profile.lane_cs = _unit_kills(player, "minion")
                            profile.has_jungle_item = _has_jungle_item(player)
                prog.next_minute += 1

    final = tracker.state
    games, drafts, players = [], [], []
    for game in tracker.games():
        if not game.get("finished"):
            continue
        teams = game.get("teams") or []
        actions = sorted(game.get("draftActions") or [], key=lambda a: a.get("sequenceNumber", 0))
        picks = [a for a in actions if a.get("type") == "pick"]
        winner = next((t["id"] for t in teams if t.get("won")), None)
        sides = {t.get("side"): t["id"] for t in teams}
        prog = progress.get(game["id"], _GameProgress())
        final_clock = _clock_seconds(game)
        if final_clock is None or final_clock > MAX_GAME_SECONDS:
            final_clock = prog.last_seconds or None
        games.append({
            "series_id": series_id,
            "game_id": game["id"],
            "game_number": game.get("sequenceNumber"),
            "series_format": final.get("format"),
            "started_at": game.get("startedAt"),
            "duration_s": final_clock,
            "blue_team_id": sides.get("blue"),
            "red_team_id": sides.get("red"),
            "winner_team_id": winner,
            "first_pick_team_id": picks[0]["drafter"]["id"] if picks else None,
            "draft_action_count": len(actions),
        })
        for action in actions:
            draftable = action.get("draftable") or {}
            drafts.append({
                "series_id": series_id,
                "game_id": game["id"],
                "seq": action.get("sequenceNumber"),
                "action": action.get("type"),
                "team_id": (action.get("drafter") or {}).get("id"),
                "champion_id": draftable.get("id"),
                "champion_name": draftable.get("name"),
            })

        for team in teams:
            team_profiles = [prog.profiles.get(p["id"], EarlyProfile(p["id"])) for p in team.get("players") or []]
            roles = assign_roles(team_profiles)
            for player in team.get("players") or []:
                role, confidence = roles.get(player["id"], ("unknown", 0.0))
                character = player.get("character") or {}
                players.append({
                    "series_id": series_id,
                    "game_id": game["id"],
                    "team_id": team["id"],
                    "side": team.get("side"),
                    "player_id": player["id"],
                    "player_name": (player.get("name") or "").strip(),
                    "champion_id": character.get("id"),
                    "champion_name": character.get("name"),
                    "role": role,
                    "role_confidence": round(confidence, 3),
                    "won": bool(team.get("won")),
                })

    return {
        "games": games,
        "draft_actions": drafts,
        "player_games": players,
        "team_minutes": team_minutes,
        "player_minutes": player_minutes,
    }
