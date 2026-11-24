"""Fill an empty Mirsad database with demo cases, so a fresh install shows a working queue.

Two sources, both run through the real pipeline (model, rules, evidence, summaries):
1. demo/demo_links.csv: invented lookalikes of UAE brands on the reserved .example domain, which can
   never belong to a real site, plus three real official sites that the official-domain cap keeps out
   of the queue.
2. The public phishing feeds (OpenPhish and PhishStats), live, if the machine is online. No API key is
   needed; skip them with --no-feeds.

Without a Jais key the case summaries use the built-in template. Nothing is loaded when the database
already has cases, unless --force is given.

Usage: python scripts/load_demo.py [--no-feeds] [--force]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mirsad import pipeline  # noqa: E402
from mirsad.collectors.sources import Found  # noqa: E402
from mirsad.sandbox import client as sandbox  # noqa: E402
from mirsad.store import Store  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Load demo cases into an empty Mirsad database.")
    ap.add_argument("--no-feeds", action="store_true", help="do not fetch the live public feeds")
    ap.add_argument("--force", action="store_true", help="load even when the database already has cases")
    a = ap.parse_args()

    store = Store()
    existing = store.one("SELECT COUNT(*) AS n FROM candidates")["n"]
    if existing and not a.force:
        print(json.dumps({"skipped": f"database already has {existing} cases"}))
        return
    use_sandbox = sandbox.available()
    loaded = 0
    with (ROOT / "demo" / "demo_links.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            pipeline.process(store, Found(row["url"], "report", channel_detail="Demo link, invented lookalike on a reserved .example domain"),
                             use_sandbox=use_sandbox)
            loaded += 1
    store.count_screened("report", loaded)
    out = {"demo_links": loaded}
    if not a.no_feeds:
        try:
            out["feeds"] = pipeline.run("feeds", store, use_sandbox=use_sandbox)
        except Exception as exc:  # offline or a feed is down: the demo links are enough to explore
            out["feeds"] = f"skipped: {type(exc).__name__}"
    print(json.dumps(out, default=str))


if __name__ == "__main__":
    main()
