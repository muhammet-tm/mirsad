"""Run the watch from the command line.

Usage:
    python scripts/run_watch.py search --max-queries 2
    python scripts/run_watch.py maps
    python scripts/run_watch.py certificates
    python scripts/run_watch.py feeds
    python scripts/run_watch.py all
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mirsad import pipeline  # noqa: E402
from mirsad.store import Store  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("channel", choices=["search", "maps", "certificates", "feeds", "all"])
    ap.add_argument("--max-queries", type=int)
    ap.add_argument("--no-sandbox", action="store_true")
    ap.add_argument("--stream-seconds", type=int, default=45)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store = Store()
    channels = ["feeds", "search", "maps", "certificates"] if a.channel == "all" else [a.channel]
    for ch in channels:
        res = pipeline.run(ch, store, use_sandbox=False if a.no_sandbox else None,
                           max_queries=a.max_queries, stream_seconds=a.stream_seconds)
        print(json.dumps(res, default=str))


if __name__ == "__main__":
    main()
