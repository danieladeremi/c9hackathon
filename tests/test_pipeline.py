"""Pipeline tests on a tiny synthetic feed. No GRID data is used or stored here."""

import json

from compression import zstd

from pipeline.extract import extract_series
from pipeline.feed import StateTracker, merge_state
from pipeline.roles import EarlyProfile, assign_roles, lane_of

TEAM_A, TEAM_B = "100", "200"


def _players(team_id: str, seconds: int) -> list[dict]:
    # Five players per team standing in fixed spots: top, jungle, mid, bot, support.
    spots = [(1000, 11000), (4000, 7000), (7400, 7400), (11000, 1000), (11300, 1200)]
    if team_id == TEAM_B:
        spots = [(3500, 13900), (10000, 7500), (7600, 7600), (13900, 4000), (13800, 4200)]
    out = []
    for i, (x, y) in enumerate(spots):
        jungler = i == 1
        support = i == 4
        out.append({
            "id": f"{team_id}-p{i}",
            "name": f"P{i}",
            "character": {"id": f"champ-{team_id}-{i}", "name": f"Champ{team_id}{i}"},
            "position": {"x": x, "y": y},
            "alive": True,
            "netWorth": 500 + seconds,
            "unitKills": [
                {"id": "unitKills-minion", "unitName": "minion", "count": 0 if jungler else (seconds // 20 if not support else 2)},
                {"id": "unitKills-neutralMinion", "unitName": "neutralMinion", "count": seconds // 15 if jungler else 0},
            ],
            "inventory": {"items": [{"id": "j", "name": "Jungle Pet"}]} if jungler else {"items": []},
        })
    return out


def _game_state(game_id: str, seconds: int, finished: bool = False) -> dict:
    return {
        "id": game_id,
        "sequenceNumber": 1,
        "started": True,
        "finished": finished,
        "clock": {"currentSeconds": seconds},
        "teams": [
            {"id": TEAM_A, "side": "blue", "won": finished, "players": _players(TEAM_A, seconds)},
            {"id": TEAM_B, "side": "red", "won": False, "players": _players(TEAM_B, seconds)},
        ],
        "draftActions": [
            {"id": "draft-action-1", "sequenceNumber": 1, "type": "ban",
             "drafter": {"id": TEAM_A}, "draftable": {"id": "x", "name": "BanMe"}},
            {"id": "draft-action-7", "sequenceNumber": 7, "type": "pick",
             "drafter": {"id": TEAM_A}, "draftable": {"id": "champ-100-0", "name": "Champ1000"}},
        ],
    }


def _write_feed(path, states, extra_events=()):
    with zstd.open(path, "wt", encoding="utf-8") as f:
        for seq, (event_type, state, full) in enumerate(states, 1):
            env = {"id": str(seq), "seriesId": "1", "sequenceNumber": seq, "occurredAt": "2026-01-01T00:00:00Z",
                   "events": [{"id": f"e{seq}", "type": event_type, "target": {"id": state.get("_target")},
                               "seriesState": {k: v for k, v in state.items() if not k.startswith("_")},
                               "includesFullState": full}]}
            f.write(json.dumps(env) + "\n")


def test_merge_state_merges_lists_by_id():
    dst = {"games": [{"id": "g1", "clock": {"currentSeconds": 1}, "teams": [{"id": "a", "kills": 0}]}]}
    merge_state(dst, {"games": [{"id": "g1", "teams": [{"id": "a", "kills": 2}, {"id": "b", "kills": 1}]}]})
    game = dst["games"][0]
    assert game["clock"]["currentSeconds"] == 1
    assert [t["kills"] for t in game["teams"]] == [2, 1]


def test_rolled_back_games_are_dropped():
    tracker = StateTracker()
    tracker.apply({"seriesState": {"games": [{"id": "bad"}, {"id": "good"}]}, "includesFullState": True})
    tracker.apply({"type": "series-!started-game", "target": {"id": "bad"}})
    assert [g["id"] for g in tracker.games()] == ["good"]


def test_lane_geometry():
    assert lane_of(1000, 11000) == "top"
    assert lane_of(7400, 7400) == "mid"
    assert lane_of(11000, 1000) == "bot"
    assert lane_of(500, 500) is None  # fountain


def test_assign_roles():
    profiles = [EarlyProfile(f"p{i}") for i in range(5)]
    for p, lane in zip(profiles, ["top", None, "mid", "bot", "bot"]):
        if lane:
            p.lane_votes[lane] = 10
    profiles[1].neutral_cs, profiles[1].has_jungle_item = 60, True
    profiles[3].lane_cs, profiles[4].lane_cs = 80, 5
    roles = {pid: role for pid, (role, _) in assign_roles(profiles).items()}
    assert roles == {"p0": "top", "p1": "jungle", "p2": "mid", "p3": "bot", "p4": "support"}


def test_extract_series_end_to_end_with_clock_spike(tmp_path):
    feed = tmp_path / "events_1_grid.jsonl.zst"
    states = [("grid-started-feed", {"games": [_game_state("g1", 0)]}, True)]
    for s in range(30, 721, 30):
        states.append(("player-moved", {"games": [_game_state("g1", s)]}, False))
    # A corrupt clock value like those seen in real feeds must not create snapshots.
    states.append(("player-lost-statusEffect", {"games": [{"id": "g1", "clock": {"currentSeconds": 35_000_000}}]}, False))
    states.append(("player-moved", {"games": [_game_state("g1", 750)]}, False))
    states.append(("team-won-game", {"games": [_game_state("g1", 760, finished=True)]}, True))
    _write_feed(feed, states)

    result = extract_series(feed)
    assert len(result["games"]) == 1
    game = result["games"][0]
    assert game["duration_s"] == 760
    assert game["first_pick_team_id"] == TEAM_A
    assert game["winner_team_id"] == TEAM_A
    assert max(r["minute"] for r in result["team_minutes"]) == 12
    roles = {(p["team_id"], p["player_name"]): p["role"] for p in result["player_games"]}
    for team in (TEAM_A, TEAM_B):
        assert [roles[(team, f"P{i}")] for i in range(5)] == ["top", "jungle", "mid", "bot", "support"]
