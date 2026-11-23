"""Re-score every stored link with the current model and rules, using stored evidence only.

Run after a new model is trained or the rules change. No collector, enrichment, or sandbox call is made.
Summaries are facts about a case, so they are rewritten for every flagged link (the language model is
called once per flagged link) and deleted for links that are no longer flagged. Use --no-summaries to
skip the model calls; stale summaries are still deleted.
Usage: python scripts/rescore.py [--no-summaries]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mirsad.api.cases import build_case  # noqa: E402
from mirsad.enrich.passive import age_days  # noqa: E402
from mirsad.llm.summary import summarize  # noqa: E402
from mirsad.scoring import engine  # noqa: E402
from mirsad.store import Store  # noqa: E402


def main() -> None:
    store = Store()
    engine._model.cache_clear()
    rows = store.rows("SELECT * FROM candidates")
    flagged, written, removed = 0, 0, 0
    rewrite = "--no-summaries" not in sys.argv
    for r in rows:
        ev = store.rows("SELECT kind, label FROM evidence WHERE candidate_id = ?", (r["id"],))
        cap = store.one("SELECT * FROM captures WHERE candidate_id = ?", (r["id"],))
        rep = {}
        for e in ev:
            if e["kind"] == "reputation" and "URLhaus" in e["label"]:
                rep["urlhaus"] = {"listed": True}
        if r["channel"] == "feeds" and "OpenPhish" in (r["channel_detail"] or ""):
            rep["openphish"] = True
        sig = engine.Signals(url=r["url"], channel=r["channel"], query=r["query"] or "", rank=r["rank"],
                             is_ad=bool(r["is_ad"]), listing=json.loads(r["listing_json"]) if r["listing_json"] else None,
                             reputation=rep, domain_age_days=age_days(r["first_seen"]),
                             capture={"forms": json.loads(cap["forms_json"] or "[]")} if cap else None,
                             logo=json.loads(cap["brand_json"] or "{}") if cap else None)
        res = engine.score(sig)
        store.save_score(r["id"], res.risk, res.model_mean, res.votes, res.reasons, res.rules, res.threshold, res.scoring_ms)
        with store.conn() as c:
            c.execute("UPDATE candidates SET imitates=? WHERE id=?", (res.imitates, r["id"]))
        is_flagged = res.risk >= res.threshold
        flagged += is_flagged
        if is_flagged and rewrite:
            s = summarize(build_case(store, r["id"]))
            store.save_summary(r["id"], s["model"], s["en"], s["ar"])
            written += 1
        else:  # not flagged, or not rewritten: a stale summary must not stay
            with store.conn() as c:
                removed += c.execute("DELETE FROM summaries WHERE candidate_id=?", (r["id"],)).rowcount
    print(json.dumps({"rescored": len(rows), "flagged": int(flagged), "summaries_written": written,
                      "summaries_removed": removed, "model": engine.model_info().get("file"),
                      "threshold": engine.threshold()}))


if __name__ == "__main__":
    main()
