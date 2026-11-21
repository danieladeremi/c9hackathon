"""Evaluation metrics from the thesis method: accuracy, log loss, Brier score, and expected
calibration error (ECE) with the bins needed for a reliability diagram.

Calibration matters more than accuracy here: WPA is a *difference* of predicted probabilities,
so a model that is systematically over- or under-confident distorts every WPA figure.
"""

from __future__ import annotations

import numpy as np


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def reliability(y: np.ndarray, p: np.ndarray, bins: int = 15) -> tuple[float, list[dict]]:
    """ECE and per-bin (mean predicted, observed win rate, count) for equal-width bins."""
    edges = np.linspace(0, 1, bins + 1)
    index = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    ece, table = 0.0, []
    for b in range(bins):
        mask = index == b
        n = int(mask.sum())
        if n == 0:
            continue
        mean_p, observed = float(p[mask].mean()), float(y[mask].mean())
        ece += n / len(p) * abs(mean_p - observed)
        table.append({"bin_low": round(float(edges[b]), 3), "bin_high": round(float(edges[b + 1]), 3),
                      "mean_predicted": round(mean_p, 4), "observed": round(observed, 4), "count": n})
    return float(ece), table


def summarize(y: np.ndarray, p: np.ndarray, bins: int = 15) -> dict:
    ece, table = reliability(y, p, bins)
    return {
        "n": int(len(y)),
        "accuracy": round(float(np.mean((p >= 0.5) == (y == 1))), 4),
        "log_loss": round(log_loss(y, p), 4),
        "brier": round(float(np.mean((p - y) ** 2)), 4),
        "ece": round(ece, 4),
        "reliability": table,
    }
