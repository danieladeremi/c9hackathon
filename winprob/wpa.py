"""Win Percentage Added (WPA) for picks, following the thesis method, with honest shrinkage.

For one team in one game, with w(t) its win probability at minute t (w(0) = the pre-game model):

    early  = w(15) - w(0)          what the team gained in the laning phase
    mid    = w(25) - w(15)
    late   = outcome - w(25)
    total  = outcome - w(0)        = early + mid + late

If the game ended before minute t, w(t) is the outcome. The mean of w(0) over a champion's
games shows selection bias: above 0.5 means it is mostly picked by teams already favoured.

**Shrinkage.** Pro samples are small. A random split-half test showed that per-champion total
WPA and raw win rate barely repeat between halves of the same data (r ~ 0-0.3), while
lane gold at 14 minutes repeats well (r ~ 0.7-0.8). So every per-champion figure is shrunk
toward its role's average by empirical Bayes: the spread of *true* champion effects (tau) is
estimated from the data, and each champion keeps a share tau^2 / (tau^2 + se^2) of its
observed difference. Noisy metrics shrink to near zero on their own; reliable ones barely move.
That share is the figure's *reliability*, shown to coaches as the strength of the evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

PHASE_MINUTES = (15, 25)
SHRINK_MIN_GAMES = 5         # groups smaller than this do not inform tau, but are still shrunk
Z90 = 1.645
STRONG, SOME = 0.6, 0.3      # reliability cut-offs for the evidence label


@dataclass(frozen=True)
class TeamGameWPA:
    w0: float
    w15: float
    w25: float
    outcome: float

    @property
    def early(self) -> float:
        return self.w15 - self.w0

    @property
    def mid(self) -> float:
        return self.w25 - self.w15

    @property
    def late(self) -> float:
        return self.outcome - self.w25

    @property
    def total(self) -> float:
        return self.outcome - self.w0


def path_value(minute: int, duration_s: float | None, state_p: float | None, outcome: float) -> float | None:
    """w(minute): the model's estimate if the game was still running, else the outcome."""
    if duration_s is not None and duration_s < minute * 60:
        return outcome
    return state_p


STRONG_MIN_GAMES, SOME_MIN_GAMES = 20, 8


def evidence_label(reliability: float, games: int | None = None) -> str:
    """Strength of evidence for one figure: needs both measured reliability and enough games,
    because tau (and so reliability) is itself uncertain for tiny groups."""
    n = games if games is not None else STRONG_MIN_GAMES
    if reliability >= STRONG and n >= STRONG_MIN_GAMES:
        return "strong"
    if reliability >= SOME and n >= SOME_MIN_GAMES:
        return "some"
    return "weak"


@dataclass(frozen=True)
class Shrunk:
    raw: float
    estimate: float
    sd: float
    reliability: float

    @property
    def ci(self) -> tuple[float, float]:
        return self.estimate - Z90 * self.sd, self.estimate + Z90 * self.sd


def shrink(groups: dict, min_games: int = SHRINK_MIN_GAMES) -> tuple[dict, dict]:
    """Empirical-Bayes shrinkage of group means toward the pooled mean.

    ``groups`` maps a key to a 1-D array of per-game values. Returns (key -> Shrunk, summary).
    Uses the pooled within-group standard deviation, so tiny groups do not get falsely small errors.
    """
    arrays = {k: np.asarray(v, dtype=float) for k, v in groups.items() if len(v)}
    if not arrays:
        return {}, {"tau": 0.0, "pooled_sd": 0.0, "grand_mean": 0.0}
    every = np.concatenate(list(arrays.values()))
    grand = float(every.mean())
    within = sum(float(((a - a.mean()) ** 2).sum()) for a in arrays.values())
    dof = sum(len(a) - 1 for a in arrays.values())
    pooled_sd = math.sqrt(within / dof) if dof > 0 else float(every.std())

    informative = [a for a in arrays.values() if len(a) >= min_games]
    if len(informative) >= 3:
        means = np.array([a.mean() for a in informative])
        se2 = np.array([pooled_sd ** 2 / len(a) for a in informative])
        tau2 = max(0.0, float(np.var(means, ddof=1) - se2.mean()))
    else:
        tau2 = 0.0

    out = {}
    for key, a in arrays.items():
        se2 = pooled_sd ** 2 / len(a)
        weight = tau2 / (tau2 + se2) if tau2 > 0 else 0.0
        estimate = grand + weight * (float(a.mean()) - grand)
        sd = math.sqrt(1 / (1 / tau2 + 1 / se2)) if tau2 > 0 else 0.0
        out[key] = Shrunk(float(a.mean()), estimate, sd, weight)
    return out, {"tau": round(math.sqrt(tau2), 4), "pooled_sd": round(pooled_sd, 4), "grand_mean": round(grand, 4)}


def split_half_reliability(values_by_group: dict, game_of: dict, min_per_half: int, rng: np.random.Generator,
                           splits: int = 5) -> dict:
    """Mean correlation of group means between two random halves of the games (sampling noise only).

    ``values_by_group`` maps key -> list of (game_id, value)."""
    games = sorted({g for pairs in values_by_group.values() for g, _ in pairs})
    correlations, counts = [], []
    for _ in range(splits):
        half = dict(zip(games, rng.integers(0, 2, size=len(games))))
        pairs = []
        for items in values_by_group.values():
            a = [v for g, v in items if half[g] == 0]
            b = [v for g, v in items if half[g] == 1]
            if len(a) >= min_per_half and len(b) >= min_per_half:
                pairs.append((np.mean(a), np.mean(b)))
        if len(pairs) >= 5:
            correlations.append(float(np.corrcoef(*np.array(pairs).T)[0, 1]))
            counts.append(len(pairs))
    if not correlations:
        return {"correlation": None, "groups": 0}
    return {"correlation": round(float(np.mean(correlations)), 3), "groups": int(np.mean(counts))}
