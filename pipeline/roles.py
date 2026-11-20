"""Infer each player's role (top, jungle, mid, bot, support) from lane positions.

The GRID LoL feed leaves ``roles`` empty and roster order is not role order, so roles
come from early-game behaviour: the jungler farms neutral camps, and the other four are
assigned by which lane they stand in between 1:30 and 14:00. Of the two bot-laners, the
one with fewer lane minions is the support.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import permutations

ROLES = ("top", "jungle", "mid", "bot", "support")

# Summoner's Rift, from map.bounds: x 0..15000, y -300..14700. Blue base bottom-left.
_MAP_MAX = 14700.0
_BLUE_BASE = (400.0, 400.0)
_RED_BASE = (14300.0, 14300.0)
_BASE_RADIUS = 3500.0
_LANE_WIDTH = 2000.0

EARLY_START_S = 90
EARLY_END_S = 840


def lane_of(x: float, y: float) -> str | None:
    """Nearest lane for a position, or None in bases, river or jungle."""
    for bx, by in (_BLUE_BASE, _RED_BASE):
        if math.hypot(x - bx, y - by) < _BASE_RADIUS:
            return None
    distances = {
        "top": min(x, _MAP_MAX - y),
        "bot": min(y, _MAP_MAX - x),
        "mid": abs(x - y) / math.sqrt(2),
    }
    lane, dist = min(distances.items(), key=lambda kv: kv[1])
    return lane if dist < _LANE_WIDTH else None


@dataclass
class EarlyProfile:
    """What one player did in the early game, enough to infer a role."""

    player_id: str
    lane_votes: dict[str, int] = field(default_factory=lambda: {"top": 0, "mid": 0, "bot": 0})
    neutral_cs: int = 0
    lane_cs: int = 0
    has_jungle_item: bool = False

    def add_position(self, x: float, y: float) -> None:
        lane = lane_of(x, y)
        if lane:
            self.lane_votes[lane] += 1

    def lane_share(self, lane: str) -> float:
        total = sum(self.lane_votes.values())
        return self.lane_votes[lane] / total if total else 0.0


def assign_roles(profiles: list[EarlyProfile]) -> dict[str, tuple[str, float]]:
    """Map player_id -> (role, confidence in 0..1) for one team's five players."""
    if len(profiles) != 5:
        return {p.player_id: ("unknown", 0.0) for p in profiles}

    jungler = max(profiles, key=lambda p: (p.has_jungle_item, p.neutral_cs))
    laners = [p for p in profiles if p is not jungler]
    jungle_conf = 1.0 if jungler.has_jungle_item else min(1.0, jungler.neutral_cs / 40)

    best_score, best = -1.0, None
    for top, mid, *bot_pair in permutations(laners):
        score = top.lane_share("top") + mid.lane_share("mid") + sum(p.lane_share("bot") for p in bot_pair)
        if score > best_score:
            best_score, best = score, (top, mid, bot_pair)

    top, mid, bot_pair = best
    support, carry = sorted(bot_pair, key=lambda p: p.lane_cs)
    lane_conf = best_score / 4
    return {
        jungler.player_id: ("jungle", jungle_conf),
        top.player_id: ("top", lane_conf),
        mid.player_id: ("mid", lane_conf),
        carry.player_id: ("bot", lane_conf),
        support.player_id: ("support", lane_conf),
    }
