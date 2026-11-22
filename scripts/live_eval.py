"""E3 live: score fresh feed URLs (collected by the feeds channel during the event) and popular sites.

Positives: phishing and malware URLs from OpenPhish, URLhaus, and PhishStats, query strings removed,
deduplicated, collected after the deployed model was trained. Negatives: a random sample of the
Tranco top 100,000 sites (home pages), excluding any domain that appears among the positives.
The deployed model's frozen threshold is used. Output: results/live_eval.json.

Usage: python scripts/live_eval.py --negatives 5000
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from mirsad.config import MODELS_DIR, PROCESSED_DIR, RAW_DIR, RESULTS_DIR  # noqa: E402
from mirsad.features.url import registered_domain  # noqa: E402
from mirsad.models.evaluate import report  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--negatives", type=int, default=5000)
    a = ap.parse_args()
    card = json.loads((MODELS_DIR / "dae2_deploy.card.json").read_text())
    model = joblib.load(MODELS_DIR / "dae2_deploy.joblib")
    rows = [json.loads(line) for line in (PROCESSED_DIR / "live_feed_urls.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    pos = sorted({r["url"] for r in rows})
    pos_domains = {registered_domain(u) for u in pos}
    tranco = pd.read_csv(RAW_DIR / "tranco_top1m.csv", header=None, names=["rank", "domain"], nrows=100_000)
    rng = random.Random(42)
    candidates = [d for d in tranco["domain"].tolist() if d not in pos_domains]
    neg = [f"https://{d}/" for d in rng.sample(candidates, min(a.negatives, len(candidates)))]
    urls = pos + neg
    y = np.array([1] * len(pos) + [0] * len(neg))
    votes = model.votes(urls)
    mean = np.mean(np.vstack(list(votes.values())), axis=0)
    thr = float(card["threshold"])
    e3a = RESULTS_DIR / "e3a_our_repr_phreshphish_temporal.json"
    if e3a.exists():
        card["thresholds"] = json.loads(e3a.read_text())["thresholds_fpr_1pct_on_validation"]
    out = {"experiment": "live_eval", "model": "dae2_deploy.joblib", "threshold": thr,
           "positives": len(pos), "negatives": len(neg),
           "positives_source": "OpenPhish, URLhaus, PhishStats feeds collected during the event",
           "positives_first_seen": min(r["seen"] for r in rows), "positives_last_seen": max(r["seen"] for r in rows),
           "negatives_source": "random sample of Tranco top 100,000 home pages (list 46YLX)",
           "at_frozen_threshold": {"dae2_mean": report(y, mean, thr),
                                   **{n: report(y, v, card.get("thresholds", {}).get(n, thr)) for n, v in votes.items()}},
           "written": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (RESULTS_DIR / "live_eval.json").write_text(json.dumps(out, indent=1))
    m = out["at_frozen_threshold"]["dae2_mean"]
    print(json.dumps({"positives": len(pos), "negatives": len(neg), "recall": m["true_positive_rate"],
                      "fpr": m["false_positive_rate"], "roc_auc": m["roc_auc"]}))


if __name__ == "__main__":
    main()
