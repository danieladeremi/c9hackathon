import pytest

from planner.rules import DRAFT_ORDER, DraftError, Game, Series, phase_of

A, B = "c9", "opp"


def _full_draft(prefix: str) -> list[str]:
    return [f"{prefix}{i}" for i in range(1, 21)]


def test_order_shape():
    assert len(DRAFT_ORDER) == 20
    assert [a for a, _ in DRAFT_ORDER].count("pick") == 10
    assert [w for a, w in DRAFT_ORDER if a == "pick"].count("first") == 5
    assert phase_of(1) == "ban1" and phase_of(7) == "pick1" and phase_of(13) == "ban2" and phase_of(20) == "pick2"


def test_first_pick_independent_of_side():
    game = Game(blue_team=A, red_team=B, first_pick_team=B)
    assert game.slot(1) == ("ban", B)      # first-pick team bans first, even on red side
    assert game.slot(7) == ("pick", B)
    assert game.slot(8) == ("pick", A)
    assert game.slot(13) == ("ban", A)     # second phase bans start with the other team


def test_no_duplicates_within_a_game():
    series = Series(A, B, "bo3", [Game(A, B, A)])
    series.apply(0, "Ahri")
    with pytest.raises(DraftError, match="banned this game"):
        series.apply(0, "Ahri")


def test_fearless_locks_picks_not_bans():
    g1 = Game(A, B, A, _full_draft("x"), winner=A)
    series = Series(A, B, "bo5", [g1, Game(B, A, B)])
    locked = series.fearless_locked(1)
    picked = [c for c in g1.actions if c not in sum(g1.bans().values(), [])]
    assert set(locked) == set(picked)
    series.apply(1, "x1")  # x1 was a ban in game 1: allowed
    with pytest.raises(DraftError, match="Fearless"):
        series.apply(1, "x7")  # x7 was a pick in game 1


def test_skipped_ban_only():
    series = Series(A, B, "bo1", [Game(A, B, A)])
    series.apply(0, None)
    assert series.games[0].actions == [None]
    series.games[0].actions = [f"b{i}" for i in range(6)]
    with pytest.raises(DraftError, match="only bans"):
        series.apply(0, None)


def test_series_decided():
    games = [Game(A, B, A, _full_draft(f"g{n}_"), winner=A) for n in range(2)]
    assert Series(A, B, "bo3", games).decided
    assert not Series(A, B, "bo5", games).decided
