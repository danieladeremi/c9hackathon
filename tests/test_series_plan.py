import pytest

from planner.rules import Game, Series
from planner.series_plan import PlanError, PlannedPick, _horizon, _real_picks_before, current_game_number, validate_plan

A, B = "c9", "opp"


def _game(prefix: str, winner: str | None = A) -> Game:
    return Game(A, B, A, [f"{prefix}{i}" for i in range(1, 21)], winner)


def test_horizon_from_game_one_of_bo5():
    s = Series(A, B, "bo5", [Game(A, B, A)])
    assert current_game_number(s) == 1
    # Before game 3: games 1 and 2 are certain. Game 3 itself is certain.
    assert _horizon(s, 3) == pytest.approx((2.0, 1.0))
    # Before game 5: games 1-3 certain, game 4 at 75%. Game 5 happens 37.5% of the time.
    assert _horizon(s, 5) == pytest.approx((3.75, 0.375))


def test_horizon_after_a_two_nil_lead():
    s = Series(A, B, "bo5", [_game("a"), _game("b"), Game(B, A, B)])
    assert current_game_number(s) == 3
    # Game 3 is being drafted; game 4 is played only if the trailing team wins game 3.
    assert _horizon(s, 4) == pytest.approx((1.0, 0.5))


def test_real_picks_before_a_game_exclude_bans():
    s = Series(A, B, "bo5", [_game("a"), Game(B, A, B)])
    gone = _real_picks_before(s, 2)
    assert "a7" in gone and "a1" not in gone  # slot 7 is a pick, slot 1 a ban
    assert _real_picks_before(s, 1) == {}


def test_plan_validation():
    s = Series(A, B, "bo5", [_game("a"), Game(B, A, B)])
    validate_plan(s, [PlannedPick(2, A, "x"), PlannedPick(3, B, "y")])
    with pytest.raises(PlanError, match="already picked"):
        validate_plan(s, [PlannedPick(3, A, "a7")])
    with pytest.raises(PlanError, match="twice"):
        validate_plan(s, [PlannedPick(2, A, "x"), PlannedPick(4, B, "x")])
    with pytest.raises(PlanError, match="between game 2"):
        validate_plan(s, [PlannedPick(1, A, "x")])
