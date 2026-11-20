"""Streaming reader for GRID series feeds.

Most events carry a *partial* ``seriesState`` (only what changed, nested by ID);
a few carry the full snapshot (``includesFullState``). ``StateTracker`` keeps the
running full state by replacing on full snapshots and deep-merging partial ones.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from compression import zstd


def read_envelopes(path: Path | str) -> Iterator[dict[str, Any]]:
    with zstd.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _is_id_list(value: list) -> bool:
    return bool(value) and all(isinstance(item, dict) and "id" in item for item in value)


def merge_state(dst: dict, src: dict) -> dict:
    """Deep-merge ``src`` into ``dst``. Lists of objects with ``id`` are merged by ID."""
    for key, value in src.items():
        current = dst.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            merge_state(current, value)
        elif isinstance(value, list) and isinstance(current, list) and _is_id_list(value):
            index = {item["id"]: item for item in current if isinstance(item, dict) and "id" in item}
            for item in value:
                existing = index.get(item["id"])
                if existing is None:
                    current.append(item)
                    index[item["id"]] = item
                else:
                    merge_state(existing, item)
        else:
            dst[key] = value
    return dst


class StateTracker:
    """Running series state, updated one event at a time."""

    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.rolled_back_games: set[str] = set()

    def apply(self, event: dict[str, Any]) -> None:
        snapshot = event.get("seriesState")
        if snapshot:
            if event.get("includesFullState") or not self.state:
                self.state = snapshot
            else:
                merge_state(self.state, snapshot)
        if event.get("type") == "series-!started-game":
            target_id = (event.get("target") or {}).get("id")
            if target_id:
                self.rolled_back_games.add(target_id)

    def games(self) -> list[dict[str, Any]]:
        return [g for g in self.state.get("games", []) if g.get("id") not in self.rolled_back_games]


def iter_events(path: Path | str) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    """Yield ``(envelope, event)`` pairs in feed order."""
    for envelope in read_envelopes(path):
        for event in envelope.get("events", []):
            yield envelope, event
