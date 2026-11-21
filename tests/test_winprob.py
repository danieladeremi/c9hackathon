from datetime import date, timedelta

import numpy as np
import pytest

from winprob.elo import BASE, GameRow, expected, run_elo
from winprob.metrics import reliability, summarize
from winprob.wpa import TeamGameWPA, evidence_label, path_value, shrink, split_half_reliability


def test_wpa_phases_add_up():
    t = TeamGameWPA(w0=0.45, w15=0.60, w25=0.70, outcome=1.0)
    assert t.early == pytest.approx(0.15)
    assert t.mid == pytest.approx(0.10)
    assert t.late == pytest.approx(0.30)
    assert t.early + t.mid + t.late == pytest.approx(t.total)


def test_path_value_uses_outcome_after_game_end():
    assert path_value(25, duration_s=1300, state_p=None, outcome=1.0) == 1.0   # ended at 21:40
    assert path_value(15, duration_s=1300, state_p=0.62, outcome=1.0) == 0.62
    assert path_value(15, duration_s=2000, state_p=None, outcome=0.0) is None  # missing state: unknown


def test_elo_has_no_lookahead_and_moves_toward_winner():
    d = date(2025, 1, 1)
    games = [GameRow("g1", d, "A", "B", True), GameRow("g2", d + timedelta(days=1), "A", "B", True)]
    pre = run_elo(games, k=32)
    assert pre["g1"] == (BASE, BASE)  # first game: nobody has a rating yet
    assert pre["g2"][0] > BASE > pre["g2"][1]
    assert expected(*pre["g2"]) > 0.5


def test_elo_shrinks_after_a_break():
    d = date(2025, 1, 1)
    games = [GameRow("g1", d, "A", "B", True), GameRow("g2", d + timedelta(days=90), "A", "B", True)]
    full = run_elo(games, k=32, shrink=0.0)["g2"][0]
    half = run_elo(games, k=32, shrink=0.5)["g2"][0]
    assert half - BASE == pytest.approx((full - BASE) / 2)


def test_calibration_metrics():
    y = np.array([0, 1] * 50, dtype=float)
    perfect = summarize(y, np.full(100, 0.5))
    assert perfect["ece"] == pytest.approx(0.0)
    ece, table = reliability(y, np.where(y == 1, 0.9, 0.1))
    assert ece == pytest.approx(0.1) and sum(b["count"] for b in table) == 100


def test_shrinkage_pure_noise_shrinks_to_grand_mean():
    rng = np.random.default_rng(0)
    groups = {f"c{i}": rng.normal(0, 0.5, 30) for i in range(40)}  # no true differences
    est, summary = shrink(groups)
    spread = np.std([e.estimate for e in est.values()])
    raw_spread = np.std([e.raw for e in est.values()])
    assert spread < raw_spread * 0.5
    assert all(evidence_label(e.reliability) != "strong" for e in est.values())


def test_shrinkage_keeps_real_differences():
    rng = np.random.default_rng(1)
    groups = {f"c{i}": rng.normal(i * 100, 50, 40) for i in range(10)}  # big true differences
    est, summary = shrink(groups)
    assert summary["tau"] > 200
    assert all(e.reliability > 0.9 for e in est.values())
    assert est["c9"].estimate > est["c0"].estimate + 700


def test_split_half_reliability_detects_signal_and_noise():
    rng = np.random.default_rng(2)
    games = [f"g{i}" for i in range(4000)]
    signal = {f"c{k}": [(g, k * 10 + rng.normal(0, 5)) for g in games[k::20]] for k in range(20)}
    noise = {f"c{k}": [(g, rng.normal(0, 5)) for g in games[k::20]] for k in range(20)}
    assert split_half_reliability(signal, {}, 30, rng)["correlation"] > 0.9
    assert abs(split_half_reliability(noise, {}, 30, rng)["correlation"]) < 0.5


def test_evidence_needs_games_as_well_as_reliability():
    assert evidence_label(0.9, 30) == "strong"
    assert evidence_label(0.9, 10) == "some"
    assert evidence_label(0.9, 5) == "weak"
