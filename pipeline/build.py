"""Rebuild the local DuckDB file from the GRID starter repo.

    uv run python -m pipeline.build            # all LoL series
    uv run python -m pipeline.build --limit 20 # quick run

Reads from STL_DATA_DIR; writes data/draft.duckdb (gitignored, never committed).
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

from .config import DATA_DIR, DB_PATH, WORK_DIR
from .extract import extract_series
from .resolve import resolve_roles

TABLES = ("games", "draft_actions", "player_games", "team_minutes", "player_minutes")
META_TABLES = ("games", "rosters", "teams", "players", "characters", "tournaments")

# Built on a laptop: keep the machine usable while this runs.
DEFAULT_WORKERS = 2
IN_FLIGHT_PER_WORKER = 2
TASKS_PER_WORKER = 100


def _lower_priority() -> None:
    """Run below normal priority so the rest of the computer stays responsive."""
    try:
        if sys.platform == "win32":
            import ctypes
            BELOW_NORMAL_PRIORITY_CLASS = 0x4000
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
        else:
            import os
            os.nice(10)
    except Exception:
        pass


def _extract_one(path: str) -> tuple[str, dict | None, str | None]:
    try:
        return path, extract_series(path), None
    except Exception as exc:  # keep going; report at the end
        return path, None, f"{type(exc).__name__}: {exc}"


def _series_files(limit: int | None) -> list[Path]:
    index = DATA_DIR / "lol" / "series.csv"
    with index.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    files = [DATA_DIR / row["file"] for row in rows if (DATA_DIR / row["file"]).exists()]
    return files[:limit] if limit else files


def build(limit: int | None = None, workers: int | None = None) -> None:
    if not (DATA_DIR / "lol" / "series.csv").exists():
        sys.exit(f"GRID data not found at {DATA_DIR}. Clone the starter repo beside this project or set STL_DATA_DIR.")

    files = _series_files(limit)
    staging = WORK_DIR / "staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    writers, handles = {}, {}
    for table in TABLES:
        handles[table] = (staging / f"{table}.csv").open("w", newline="", encoding="utf-8")
        writers[table] = None

    def write(result: dict) -> None:
        for table in TABLES:
            rows = result[table]
            if not rows:
                continue
            if writers[table] is None:
                writers[table] = csv.DictWriter(handles[table], fieldnames=list(rows[0].keys()))
                writers[table].writeheader()
            writers[table].writerows(rows)

    _lower_priority()
    workers = max(1, workers or DEFAULT_WORKERS)
    print(f"Extracting {len(files)} series with {workers} worker(s) at below-normal priority")
    started = time.time()
    failures = []
    done = 0
    pending_paths = [str(p) for p in files]
    with ProcessPoolExecutor(max_workers=workers, initializer=_lower_priority,
                             max_tasks_per_child=TASKS_PER_WORKER) as pool:
        in_flight = set()
        while pending_paths or in_flight:
            # Submit only a few at a time so finished results never pile up in memory.
            while pending_paths and len(in_flight) < workers * IN_FLIGHT_PER_WORKER:
                in_flight.add(pool.submit(_extract_one, pending_paths.pop(0)))
            finished, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
            for future in finished:
                path, result, error = future.result()
                done += 1
                if error:
                    failures.append((path, error))
                else:
                    write(result)
                if done % 25 == 0 or done == len(files):
                    print(f"  {done}/{len(files)} series ({time.time() - started:.0f}s)", flush=True)
    for handle in handles.values():
        handle.close()

    import duckdb  # imported here so worker processes never load it

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_db = DB_PATH.with_suffix(".tmp.duckdb")
    tmp_db.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp_db), config={"memory_limit": "1GB", "threads": 2})
    for table in TABLES:
        source = staging / f"{table}.csv"
        if writers[table] is None:
            continue
        # IDs are strings in GRID; stop DuckDB from guessing they are numbers.
        id_columns = [c for c in writers[table].fieldnames if c.endswith("_id")]
        types = ", ".join(f"'{c}': 'VARCHAR'" for c in id_columns)
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM read_csv('{source.as_posix()}', header=true, types={{{types}}})")
    if writers["player_games"] is not None:
        resolve_roles(con)
    for name in META_TABLES:
        source = (DATA_DIR / "meta" / f"{name}.csv").as_posix()
        con.execute(f"CREATE TABLE meta_{name} AS SELECT * FROM read_csv('{source}', header=true, all_varchar=true) WHERE title = 'lol'")
    series_csv = (DATA_DIR / "lol" / "series.csv").as_posix()
    con.execute(f"CREATE TABLE series AS SELECT * FROM read_csv('{series_csv}', header=true, all_varchar=true)")
    con.close()
    DB_PATH.unlink(missing_ok=True)
    tmp_db.rename(DB_PATH)
    shutil.rmtree(staging, ignore_errors=True)

    print(f"Built {DB_PATH} from {len(files) - len(failures)} series in {time.time() - started:.0f}s")
    for path, error in failures:
        print(f"  FAILED {Path(path).name}: {error}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="only the first N series (for quick runs)")
    parser.add_argument("--workers", type=int, help=f"parallel processes (default: {DEFAULT_WORKERS})")
    args = parser.parse_args()
    build(args.limit, args.workers)


if __name__ == "__main__":
    main()
