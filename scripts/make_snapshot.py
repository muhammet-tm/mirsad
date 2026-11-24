"""Build the database the public demo starts from: our lab cases, safe to publish, plus the demo links.

Steps, all on a copy (the lab database is never changed):
1. Every stored link is replaced by its redacted form, so no query value that could hold a victim's
   data leaves the lab. The audit log, which names analysts and their machines, is emptied.
2. Cases at or near the threshold get hosting (address and network) and WHOIS (registrar, expiry,
   name servers) exhibits, looked up now and dated now, so the evidence the case file shows is
   current. Reserved demo domains are never looked up.
3. The invented demo links (demo/demo_links.csv) are added through the real pipeline.

Usage: python scripts/make_snapshot.py [--out deploy/seed.sqlite3]
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mirsad import pipeline  # noqa: E402
from mirsad.collectors.sources import Found  # noqa: E402
from mirsad.config import DB_PATH  # noqa: E402
from mirsad.enrich import hosting, passive  # noqa: E402
from mirsad.features.url import hosting_platform, registered_domain  # noqa: E402
from mirsad.scoring.engine import threshold  # noqa: E402
from mirsad.store import Store  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=ROOT / "deploy" / "seed.sqlite3")
    a = ap.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    if a.out.exists():
        a.out.unlink()
    with sqlite3.connect(DB_PATH) as src, sqlite3.connect(a.out) as dst:
        src.backup(dst)
    with sqlite3.connect(a.out) as c:
        c.execute("UPDATE candidates SET url = url_redacted")
        c.execute("DELETE FROM audit")
    store = Store(a.out)

    near = threshold() - pipeline.NEAR
    rows = store.rows("SELECT c.id, c.url, c.host, c.domain FROM candidates c JOIN scores s ON s.candidate_id = c.id "
                      "WHERE s.risk >= ?", (near,))
    added = {"hosting": 0, "whois": 0}
    for r in rows:
        if hosting_platform(r["url"]):
            continue  # a shared platform's addresses and registration describe the platform, not the site
        h = hosting.lookup(r["host"] or "")
        if h:
            store.add_evidence(r["id"], "hosting", hosting.label(h), "DNS over HTTPS, Team Cymru", h, observed_at=h["resolved_at"])
            added["hosting"] += 1
        rec = passive.rdap_record(r["domain"] or registered_domain(r["url"]))
        if rec and passive.whois_label(rec):
            store.add_evidence(r["id"], "whois", passive.whois_label(rec), "RDAP (registry record)", rec)
            added["whois"] += 1

    demo = 0
    with (ROOT / "demo" / "demo_links.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            pipeline.process(store, Found(row["url"], "report", channel_detail="Demo link, invented lookalike on a reserved .example domain"),
                             use_sandbox=False)
            demo += 1
    store.count_screened("report", demo)
    with sqlite3.connect(a.out) as c:
        c.execute("UPDATE candidates SET url = url_redacted")  # the demo links are stored redacted too
        c.execute("DELETE FROM audit")
    with sqlite3.connect(a.out) as c:
        c.execute("VACUUM")
    print(json.dumps({"out": str(a.out), "near_threshold_cases": len(rows), "added": added, "demo_links": demo}))


if __name__ == "__main__":
    main()
