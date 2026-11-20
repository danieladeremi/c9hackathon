"""Draft rules: pick/ban order and Fearless locks across a series.

Order (verified on all 1,721 complete drafts in the GRID data): it depends on which team
has *first pick*, not on side, and first pick is chosen separately from side.
"F" is the first-pick team, "S" the other team.

    Bans 1   F S F S F S
    Picks 1  F S S F F S
    Bans 2   S F S F
    Picks 2  S F F S

Fearless (hard): a champion picked by either team in an earlier game of the series cannot
be picked again by either team. Bans do not carry over.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Action = Literal["ban", "pick"]
Who = Literal["first", "second"]

DRAFT_ORDER: tuple[tuple[Action, Who], ...] = (
    ("ban", "first"), ("ban", "second"), ("ban", "first"), ("ban", "second"), ("ban", "first"), ("ban", "second"),
    ("pick", "first"), ("pick", "second"), ("pick", "second"), ("pick", "first"), ("pick", "first"), ("pick", "second"),
    ("ban", "second"), ("ban", "first"), ("ban", "second"), ("ban", "first"),
    ("pick", "second"), ("pick", "first"), ("pick", "first"), ("pick", "second"),
)
SERIES_GAMES = {"bo1": 1, "bo3": 3, "bo5": 5}


def phase_of(seq: int) -> str:
    """Draft phase for a 1-based slot number: ban1, pick1, ban2 or pick2."""
    if seq <= 6:
        return "ban1"
    if seq <= 12:
        return "pick1"
    if seq <= 16:
        return "ban2"
    return "pick2"


class DraftError(ValueError):
    pass


@dataclass
class Game:
    blue_team: str
    red_team: str
    first_pick_team: str
    # Champion IDs in slot order; None means the slot was skipped (a missed ban).
    actions: list[str | None] = field(default_factory=list)
    winner: str | None = None

    def team_for(self, who: Who) -> str:
        second = self.red_team if self.first_pick_team == self.blue_team else self.blue_team
        return self.first_pick_team if who == "first" else second

    def slot(self, seq: int) -> tuple[Action, str]:
        action, who = DRAFT_ORDER[seq - 1]
        return action, self.team_for(who)

    @property
    def complete(self) -> bool:
        return len(self.actions) == len(DRAFT_ORDER)

    def picks(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {self.blue_team: [], self.red_team: []}
        for seq, champ in enumerate(self.actions, 1):
            action, team = self.slot(seq)
            if action == "pick" and champ:
                out[team].append(champ)
        return out

    def bans(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {self.blue_team: [], self.red_team: []}
        for seq, champ in enumerate(self.actions, 1):
            action, team = self.slot(seq)
            if action == "ban" and champ:
                out[team].append(champ)
        return out


@dataclass
class Series:
    team_a: str
    team_b: str
    format: str = "bo5"
    games: list[Game] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.format not in SERIES_GAMES:
            raise DraftError(f"unknown format {self.format!r}")
        for game in self.games:
            if {game.blue_team, game.red_team} != {self.team_a, self.team_b}:
                raise DraftError("each game must be between the series' two teams")
            if game.first_pick_team not in (game.blue_team, game.red_team):
                raise DraftError("first pick team must play in the game")

    def fearless_locked(self, before_game: int) -> dict[str, tuple[int, str]]:
        """Champions picked in games before ``before_game`` (0-based): champion -> (game number, team)."""
        locked: dict[str, tuple[int, str]] = {}
        for number, game in enumerate(self.games[:before_game], 1):
            for team, champs in game.picks().items():
                for champ in champs:
                    locked[champ] = (number, team)
        return locked

    def wins(self) -> dict[str, int]:
        out = {self.team_a: 0, self.team_b: 0}
        for game in self.games:
            if game.winner in out:
                out[game.winner] += 1
        return out

    @property
    def decided(self) -> bool:
        needed = SERIES_GAMES[self.format] // 2 + 1
        return max(self.wins().values()) >= needed

    def current_game_index(self) -> int | None:
        for index, game in enumerate(self.games):
            if not game.complete or game.winner is None:
                return index
        return None

    def unavailable(self, game_index: int) -> dict[str, str]:
        """Champions that cannot be chosen in the next slot of a game, with the reason."""
        game = self.games[game_index]
        reasons = {champ: f"Fearless: picked in game {n}" for champ, (n, _) in self.fearless_locked(game_index).items()}
        for seq, champ in enumerate(game.actions, 1):
            if champ:
                action, _ = game.slot(seq)
                reasons[champ] = "banned this game" if action == "ban" else "picked this game"
        return reasons

    def apply(self, game_index: int, champion: str | None) -> None:
        """Record the next slot of a game. ``None`` records a skipped ban."""
        game = self.games[game_index]
        if game.complete:
            raise DraftError("this game's draft is complete")
        action, _team = game.slot(len(game.actions) + 1)
        if champion is None:
            if action != "ban":
                raise DraftError("only bans can be skipped")
        elif champion in self.unavailable(game_index):
            raise DraftError(f"{champion} is unavailable: {self.unavailable(game_index)[champion]}")
        game.actions.append(champion)
