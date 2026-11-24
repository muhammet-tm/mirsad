"""Train and evaluate the four-ensemble model under the protocol in docs/TECHNICAL_REPORT.md (Section 6).

E1  The conventional benchmark setting: malicious_phish, random 80/20 split, binary (benign vs
    malicious). E1a uses the raw representation (word TF-IDF of the raw URL); E1b uses ours.
E2  Sites never seen in training: duplicates and label conflicts removed, split grouped by
    registered domain so no domain is on both sides.
E3  Recent threats: trained on PhreshPhish train (Jul 2024 to Sep 2025), tested on PhreshPhish
    test (Sep to Dec 2025), a strictly later period. E3b applies the E1a model to the same test.
E4  Speed: median and 95th percentile scoring time per URL for the deployed model.

Thresholds are chosen on a validation slice of the training data (false-positive rate at most 1%)
and frozen before the test set is scored. Every result goes to results/*.json.

Usage: python scripts/train_eval.py --exp e1,e2,e3,e4 --sample 200000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.model_selection import GroupShuffleSplit, train_test_split  # noqa: E402

from mirsad.config import MODELS_DIR, RAW_DIR, RESULTS_DIR  # noqa: E402
from mirsad.features.url import canonical, registered_domain  # noqa: E402
from mirsad.models.dae2 import ENSEMBLES, DaE2  # noqa: E402
from mirsad.models.evaluate import report, threshold_for_fpr  # noqa: E402

SEED = 42


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def load_kaggle(sample: int | None, clean: bool) -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "malicious_phish.csv")
    df["url"] = df["url"].astype(str)
    df["y"] = (df["type"] != "benign").astype(int)
    if clean:
        df["canon"] = df["url"].map(canonical)
        conflicted = df.groupby("canon")["y"].nunique()
        df = df[~df["canon"].isin(conflicted[conflicted > 1].index)].drop_duplicates("canon")
    if sample and len(df) > sample:
        df, _ = train_test_split(df, train_size=sample, stratify=df["type"], random_state=SEED)
    return df.reset_index(drop=True)


def load_phresh(split: str, sample: int | None) -> pd.DataFrame:
    df = pd.read_parquet(RAW_DIR / f"phreshphish_{split}_urls.parquet")
    df["url"] = df["url"].astype(str)
    df["y"] = (df["label"] == "phish").astype(int)
    if sample and len(df) > sample:
        df, _ = train_test_split(df, train_size=sample, stratify=df["y"], random_state=SEED)
    return df.reset_index(drop=True)


def fit_and_score(name: str, train: pd.DataFrame, test: pd.DataFrame, representation: str, meta: dict):
    tr, val = train_test_split(train, test_size=0.1, stratify=train["y"], random_state=SEED)
    log(f"{name}: fitting DaE2 ({representation}) on {len(tr):,} URLs")
    t0 = time.perf_counter()
    model = DaE2(representation=representation, random_state=SEED).fit(tr["url"].tolist(), tr["y"].to_numpy())
    fit_s = time.perf_counter() - t0
    log(f"{name}: fitted in {fit_s:.0f} s; choosing thresholds on {len(val):,} validation URLs")
    val_votes = model.votes(val["url"].tolist())
    val_mean = np.mean(np.vstack(list(val_votes.values())), axis=0)
    thresholds = {n: threshold_for_fpr(val["y"], v, 0.01) for n, v in val_votes.items()}
    thresholds["dae2_mean"] = threshold_for_fpr(val["y"], val_mean, 0.01)

    log(f"{name}: scoring {len(test):,} test URLs")
    t1 = time.perf_counter()
    votes = model.votes(test["url"].tolist())
    score_s = time.perf_counter() - t1
    mean = np.mean(np.vstack(list(votes.values())), axis=0)
    y = test["y"].to_numpy()
    out = {
        "experiment": name, "representation": representation, **meta,
        "train_rows": int(len(tr)), "validation_rows": int(len(val)), "test_rows": int(len(test)),
        "fit_seconds": round(fit_s, 1), "score_ms_per_url_batch": round(1000 * score_s / max(len(test), 1), 3),
        "thresholds_fpr_1pct_on_validation": {k: round(v, 4) for k, v in thresholds.items()},
        "at_validation_threshold": {n: report(y, v, thresholds[n]) for n, v in votes.items()},
        "at_0_5": {n: report(y, v, 0.5) for n, v in votes.items()},
    }
    out["at_validation_threshold"]["dae2_mean"] = report(y, mean, thresholds["dae2_mean"])
    out["at_0_5"]["dae2_mean"] = report(y, mean, 0.5)
    return model, out


def save(name: str, result: dict) -> None:
    result["written"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"{name}.json").write_text(json.dumps(result, indent=1))
    best = result.get("at_validation_threshold", {})
    log(f"{name}: wrote results/{name}.json; " + "; ".join(
        f"{k} acc={v['accuracy']} f1={v['fraud_class']['f1']} fpr={v['false_positive_rate']}" for k, v in best.items()))


def e1(sample):
    df = load_kaggle(sample, clean=False)
    train, test = train_test_split(df, test_size=0.2, stratify=df["type"], random_state=SEED)
    meta = {"data": "malicious_phish (Kaggle), raw benchmark rows", "split": "random 80/20, stratified",
            "sample_rows": int(len(df))}
    model_a, res_a = fit_and_score("e1a_paper_repr_random_split", train, test, "paper", meta)
    save(res_a["experiment"], res_a)
    joblib.dump(model_a, MODELS_DIR / "dae2_e1a_paper.joblib", compress=3)
    _, res_b = fit_and_score("e1b_our_repr_random_split", train, test, "ours", meta)
    save(res_b["experiment"], res_b)


def e2(sample):
    df = load_kaggle(sample, clean=True)
    df["domain"] = df["url"].map(registered_domain)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
    tr_idx, te_idx = next(gss.split(df, df["y"], groups=df["domain"]))
    train, test = df.iloc[tr_idx], df.iloc[te_idx]
    meta = {"data": "malicious_phish, duplicates and conflicting labels removed",
            "split": "80/20 grouped by registered domain (no domain on both sides)", "sample_rows": int(len(df)),
            "domains_shared_between_train_and_test": int(len(set(train['domain']) & set(test['domain'])))}
    for repr_ in ("paper", "ours"):
        _, res = fit_and_score(f"e2_{repr_}_repr_domain_split", train, test, repr_, meta)
        save(res["experiment"], res)


def e3(sample):
    train = load_phresh("train", sample)
    test = load_phresh("test", None)
    meta = {"data": "PhreshPhish (CC BY 4.0), URL column only",
            "split": "temporal: train Jul 2024 to Sep 2025, test Sep to Dec 2025",
            "train_date_range": [str(train["date"].min()), str(train["date"].max())],
            "test_date_range": [str(test["date"].min()), str(test["date"].max())]}
    model, res = fit_and_score("e3a_our_repr_phreshphish_temporal", train, test, "ours", meta)
    save(res["experiment"], res)
    joblib.dump(model, MODELS_DIR / "dae2_deploy.joblib", compress=3)
    card = {"model": "DaE2 (four ensembles, mean of probabilities)", "representation": "ours",
            "trained_on": meta["data"], "train_rows": res["train_rows"], "train_date_range": meta["train_date_range"],
            "threshold": res["thresholds_fpr_1pct_on_validation"]["dae2_mean"],
            "threshold_rule": "false-positive rate at most 1% on a validation slice of the training data",
            "ensembles": list(ENSEMBLES), "written": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (MODELS_DIR / "dae2_deploy.card.json").write_text(json.dumps(card, indent=1))

    paper_model_path = MODELS_DIR / "dae2_e1a_paper.joblib"
    if paper_model_path.exists():
        log("e3b: applying the E1a (benchmark setting) model to the PhreshPhish test period")
        paper_model = joblib.load(paper_model_path)
        e1a = json.loads((RESULTS_DIR / "e1a_paper_repr_random_split.json").read_text())
        thr = e1a["thresholds_fpr_1pct_on_validation"]
        votes = paper_model.votes(test["url"].tolist())
        y = test["y"].to_numpy()
        mean = np.mean(np.vstack(list(votes.values())), axis=0)
        out = {"experiment": "e3b_paper_model_on_phreshphish_test", "trained_on": "malicious_phish (E1a model)",
               **{k: meta[k] for k in ("split", "test_date_range")}, "test_rows": int(len(test)),
               "at_validation_threshold": {n: report(y, v, thr[n]) for n, v in votes.items()}}
        out["at_validation_threshold"]["dae2_mean"] = report(y, mean, thr["dae2_mean"])
        save(out["experiment"], out)


def e4():
    from mirsad.models.dae2 import for_live_scoring

    t_load = time.perf_counter()
    model = for_live_scoring(joblib.load(MODELS_DIR / "dae2_deploy.joblib"))
    load_s = time.perf_counter() - t_load
    test = load_phresh("test", 2000)
    urls = test["url"].tolist()
    model.votes(urls[:20])  # warm up
    times = []
    for u in urls[:1000]:
        t0 = time.perf_counter()
        model.votes([u])
        times.append(1000 * (time.perf_counter() - t0))
    t0 = time.perf_counter()
    model.votes(urls)
    batch_ms = 1000 * (time.perf_counter() - t0) / len(urls)
    out = {"experiment": "e4_scoring_speed", "model": "dae2_deploy.joblib", "single_url_runs": len(times),
           "median_ms_single_url": round(float(np.median(times)), 2),
           "p95_ms_single_url": round(float(np.percentile(times, 95)), 2),
           "batch_ms_per_url": round(batch_ms, 3), "urls_per_second_batch": int(1000 / batch_ms),
           "model_load_seconds": round(load_s, 1),
           "model_file_mb": round((MODELS_DIR / "dae2_deploy.joblib").stat().st_size / 2 ** 20, 1),
           "machine": "AMD Ryzen 5 4600H, 6 cores, 15.4 GB RAM, Windows 11, one process"}
    save("e4_scoring_speed", out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="e1,e2,e3,e4")
    ap.add_argument("--sample", type=int, default=200_000)
    a = ap.parse_args()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    sample = a.sample or None
    for e in a.exp.split(","):
        log(f"=== {e} (sample {sample}) ===")
        {"e1": lambda: e1(sample), "e2": lambda: e2(sample), "e3": lambda: e3(sample), "e4": e4}[e.strip()]()
        log(f"=== {e} done ===")


if __name__ == "__main__":
    main()
