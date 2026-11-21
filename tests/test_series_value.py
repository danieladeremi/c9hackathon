import pytest

from planner.series_value import calibrate, future_game_probabilities, raw_use_probability, smoothed_rate


def test_future_games_bo5_from_zero_zero():
    # Drafting game 1 of a Bo5 at 0-0 with coin-flip games: game 2 and 3 are certain,
    # game 4 needs a 2-1 score after game 3 (3/4 of the time), game 5 a 2-2 (3/8).
    assert future_game_probabilities("bo5", 0, 0) == pytest.approx([1.0, 1.0, 0.75, 0.375])


def test_future_games_when_one_win_from_the_series():
    # Bo3 at 1-0, drafting game 2: game 3 happens only if the trailing team wins game 2.
    assert future_game_probabilities("bo3", 1, 0) == pytest.approx([0.5])
    # Last possible game: nothing left after it.
    assert future_game_probabilities("bo5", 2, 2) == []
    assert future_game_probabilities("bo1", 0, 0) == []


def test_use_probability_and_smoothing():
    assert raw_use_probability(0.0, 3) == 0.0
    assert raw_use_probability(0.5, 2) == pytest.approx(0.75)
    # A champion never picked by the team still borrows the league's rate...
    assert smoothed_rate(0, 40, league_rate=0.2, prior_games=8) == pytest.approx(1.6 / 48)
    # ...and a team habit dominates once it has history.
    assert smoothed_rate(20, 40, league_rate=0.0, prior_games=8) == pytest.approx(20 / 48)


def test_identity_calibration():
    assert calibrate(0.3, 0.0, 1.0) == pytest.approx(0.3, abs=1e-6)
