"""E0: audit malicious_phish for shortcuts before any model is trained.

Measures, per class: share of URLs that start with a scheme or contain "www.", length, number of
unique registered domains, the top domains, exact and canonical duplicates, and how many registered
domains appear on both sides of a random 80/20 split (the split the DaE2 paper used).

Usage: python scripts/audit_dataset.py   -> results/e0_audit_kaggle.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

from mirsad.config import RAW_DIR, RESULTS_DIR  # noqa: E402
from mirsad.features.url import canonical, registered_domain  # noqa: E402


def main() -> None:
    df = pd.read_csv(RAW_DIR / "malicious_phish.csv")
    df["url"] = df["url"].astype(str)
    df["has_scheme"] = df["url"].str.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
    df["has_www"] = df["url"].str.contains(r"(?:^|//)www\.", regex=True)
    df["canon"] = df["url"].map(canonical)
    df["domain"] = df["url"].map(registered_domain)
    out: dict = {"rows": int(len(df)), "classes": df["type"].value_counts().to_dict()}

    per_class = {}
    for cls, g in df.groupby("type"):
        top = g["domain"].value_counts().head(10)
        per_class[cls] = {
            "rows": int(len(g)),
            "share_with_scheme": round(float(g["has_scheme"].mean()), 4),
            "share_with_www": round(float(g["has_www"].mean()), 4),
            "median_length": float(g["url"].str.len().median()),
            "unique_registered_domains": int(g["domain"].nunique()),
            "rows_per_domain": round(len(g) / max(g["domain"].nunique(), 1), 2),
            "top10_domains_share": round(float(top.sum() / len(g)), 4),
            "top10_domains": {k: int(v) for k, v in top.items()},
        }
    out["per_class"] = per_class

    out["exact_duplicates"] = int(df.duplicated("url").sum())
    out["canonical_duplicates"] = int(df.duplicated("canon").sum())
    conflicting = df.groupby("canon")["type"].nunique()
    out["canonical_urls_with_conflicting_labels"] = int((conflicting > 1).sum())

    # The paper's protocol: a random 80/20 split of rows.
    tr, te = train_test_split(df, test_size=0.2, random_state=42, stratify=df["type"])
    shared = set(tr["domain"]) & set(te["domain"])
    out["random_split"] = {
        "test_rows": int(len(te)),
        "test_rows_whose_domain_is_in_train": int(te["domain"].isin(shared).sum()),
        "share_test_rows_domain_seen_in_train": round(float(te["domain"].isin(shared).mean()), 4),
        "test_rows_whose_exact_url_is_in_train": int(te["url"].isin(set(tr["url"])).sum()),
    }

    # How far the scheme alone separates the classes: accuracy of predicting "malicious" from has_scheme.
    y = (df["type"] != "benign").to_numpy()
    pred = df["has_scheme"].to_numpy()
    out["scheme_only_rule"] = {
        "rule": "malicious if the URL starts with a scheme",
        "accuracy": round(float((pred == y).mean()), 4),
        "share_malicious_with_scheme": round(float(pred[y].mean()), 4),
        "share_benign_with_scheme": round(float(pred[~y].mean()), 4),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "e0_audit_kaggle.json"
    path.write_text(json.dumps(out, indent=1, default=lambda o: o.item() if isinstance(o, np.generic) else str(o)))
    print(json.dumps({k: v for k, v in out.items() if k != "per_class"}, indent=1))
    for cls, v in per_class.items():
        print(cls, {k: v[k] for k in ("rows", "share_with_scheme", "share_with_www", "unique_registered_domains", "top10_domains_share")})


if __name__ == "__main__":
    main()
