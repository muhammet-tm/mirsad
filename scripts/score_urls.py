"""Score a list of URLs and write one CSV row per URL, for a test set of fraud and legitimate links.

Input: a text file with one URL per line, or a CSV file with a column named `url` (an optional column
named `label` with 1/0 or fraud/legitimate words turns on the metrics below). Output columns: url,
risk, verdict (fraud or legitimate at the frozen threshold), model_mean, the four ensemble votes,
imitates, reasons, and destination (where a short link leads, when --expand-short-links is set).

Every URL gets the same treatment as a single check in the dashboard: the four-ensemble model, the
URL-level evidence rules (a protected brand on a domain it does not own), and the official-domain
cap that keeps real banks and government sites out. No API key and no network are needed, except
for --expand-short-links, which asks the shortener services (bit.ly, tinyurl.com, and the like) where
each short link points and scores that destination instead; the destination is never contacted.

Usage:
  python scripts/score_urls.py urls.txt --out scored.csv
  python scripts/score_urls.py test.csv --out scored.csv --expand-short-links
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mirsad.enrich.redirects import expand_short_link, is_short_link  # noqa: E402
from mirsad.models.evaluate import report  # noqa: E402
from mirsad.scoring.engine import ENSEMBLE_ORDER, score_batch, threshold  # noqa: E402

FRAUD = {"1", "fraud", "fraudulent", "phish", "phishing", "malicious", "malware", "defacement", "scam", "bad", "spam", "true"}
LEGIT = {"0", "legitimate", "legit", "benign", "safe", "good", "clean", "false"}


def read_input(path: Path) -> tuple[list[str], list[int] | None]:
    text = path.read_text(encoding="utf-8-sig")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return [], None
    first = [c.strip().lower() for c in next(csv.reader([lines[0]]))]
    if "url" not in first:  # plain list, one URL per line
        return [ln.strip() for ln in lines], None
    rows = list(csv.DictReader(lines, fieldnames=None))
    key = next(k for k in rows[0] if k and k.strip().lower() == "url")
    label_key = next((k for k in rows[0] if k and k.strip().lower() in ("label", "y", "class", "type")), None)
    urls = [(r.get(key) or "").strip() for r in rows]
    labels = None
    if label_key:
        labels = []
        for r in rows:
            v = (r.get(label_key) or "").strip().lower()
            labels.append(1 if v in FRAUD else 0 if v in LEGIT else -1)
        if any(v == -1 for v in labels):
            print("note: some labels were not recognized; metrics use only rows with a known label", file=sys.stderr)
    keep = [i for i, u in enumerate(urls) if u]
    return [urls[i] for i in keep], ([labels[i] for i in keep] if labels else None)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input", type=Path)
    ap.add_argument("--out", type=Path, default=Path("scored.csv"))
    ap.add_argument("--expand-short-links", action="store_true")
    a = ap.parse_args()

    urls, labels = read_input(a.input)
    if not urls:
        sys.exit("no URLs found in the input file")
    destinations = list(urls)
    if a.expand_short_links:
        for i, u in enumerate(urls):
            if is_short_link(u):
                destinations[i], _ = expand_short_link(u)

    t0 = time.perf_counter()
    results = score_batch(destinations)
    seconds = time.perf_counter() - t0
    thr = threshold()

    with a.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["url", "risk", "verdict", "model_mean", *ENSEMBLE_ORDER, "imitates", "reasons", "destination"])
        for u, d, r in zip(urls, destinations, results):
            reasons = list(r.reasons)
            if d != u:
                reasons.insert(0, f"Short link leads to {d}")
            w.writerow([u, f"{r.risk:.4f}", "fraud" if r.risk >= thr else "legitimate", f"{r.model_mean:.4f}",
                        *[f"{r.votes.get(k, 0):.4f}" for k in ENSEMBLE_ORDER], r.imitates or "",
                        " | ".join(reasons), d if d != u else ""])

    summary = {"urls": len(urls), "flagged_as_fraud": sum(r.risk >= thr for r in results), "threshold": thr,
               "seconds": round(seconds, 1), "out": str(a.out)}
    if labels:
        known = [(lab, r.risk) for lab, r in zip(labels, results) if lab in (0, 1)]
        if known and 0 < sum(lab for lab, _ in known) < len(known):
            m = report([lab for lab, _ in known], [s for _, s in known], thr)
            summary["metrics"] = {"accuracy": m["accuracy"], "precision": m["fraud_class"]["precision"],
                                  "recall": m["fraud_class"]["recall"], "f1": m["fraud_class"]["f1"],
                                  "false_positive_rate": m["false_positive_rate"], "roc_auc": m["roc_auc"],
                                  "confusion": m["confusion"]}
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
