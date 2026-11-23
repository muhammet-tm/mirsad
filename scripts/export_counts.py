"""Export what the live watch found into results/counts.json, so documents and the deck quote it.

Counts only: links screened per channel, candidates stored, flagged links per channel, imitated brands,
and the rules that fired most. No raw URLs leave the database through this file; examples use the
redacted host only.
Usage: python scripts/export_counts.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mirsad.config import RESULTS_DIR  # noqa: E402
from mirsad.scoring.engine import threshold  # noqa: E402
from mirsad.store import Store  # noqa: E402


def main() -> None:
    s = Store()
    thr = threshold()
    screened = {r["channel"]: r["n"] for r in s.rows("SELECT channel, SUM(count) AS n FROM screened GROUP BY channel")}
    stored = {r["channel"]: r["n"] for r in s.rows("SELECT channel, COUNT(*) AS n FROM candidates GROUP BY channel")}
    flagged_rows = s.rows("""SELECT c.channel, c.host, c.imitates, s.risk, s.rules_json FROM candidates c
                             JOIN scores s ON s.candidate_id = c.id WHERE s.risk >= ? ORDER BY s.risk DESC""", (thr,))
    flagged = Counter(r["channel"] for r in flagged_rows)
    brands = Counter(r["imitates"] for r in flagged_rows if r["imitates"])
    rules = Counter(rule for r in flagged_rows for rule in json.loads(r["rules_json"] or "[]"))
    runs = s.rows("SELECT channel, started, finished, items, flagged, state, detail FROM runs ORDER BY id")
    out = {
        "threshold": thr, "screened_total": int(sum(screened.values())), "screened_by_channel": screened,
        "stored_total": int(sum(stored.values())), "stored_by_channel": stored,
        "flagged_total": len(flagged_rows), "flagged_by_channel": dict(flagged),
        "imitated_brands": dict(brands.most_common(10)), "rules_fired": dict(rules.most_common(12)),
        "top_flagged_hosts": [{"host": r["host"], "channel": r["channel"], "risk": r["risk"], "imitates": r["imitates"]}
                              for r in flagged_rows[:10]],
        "runs": runs, "first_run": runs[0]["started"] if runs else None, "last_run": runs[-1]["finished"] if runs else None,
        "written": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (RESULTS_DIR / "counts.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("screened_total", "flagged_total", "flagged_by_channel", "imitated_brands")}, indent=1))


if __name__ == "__main__":
    main()
