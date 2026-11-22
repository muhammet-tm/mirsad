"""Metrics that hold up in front of a security audience.

Accuracy on a dataset that is two-thirds benign says little, so every report carries:
- precision, recall, F1, and false-positive rate at a threshold fixed on validation data;
- macro and weighted averages, each labeled, never mixed in one table;
- ROC AUC and average precision (area under the precision-recall curve);
- precision at realistic prevalence (1% and 0.1% of screened links fraudulent), computed from the
  recall and false-positive rate: P = TPR*b / (TPR*b + FPR*(1-b)).
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import (average_precision_score, confusion_matrix, precision_recall_fscore_support,
                             roc_auc_score, roc_curve)


def threshold_for_fpr(y_true, scores, max_fpr: float = 0.01) -> float:
    """Lowest threshold whose false-positive rate on these (validation) labels is at most max_fpr."""
    fpr, _, thr = roc_curve(y_true, scores)
    ok = np.where(fpr <= max_fpr)[0]
    return float(min(1.0, thr[ok[-1]])) if len(ok) else 1.0


def at_base_rate(tpr: float, fpr: float, base_rate: float) -> float | None:
    denom = tpr * base_rate + fpr * (1 - base_rate)
    return round(tpr * base_rate / denom, 4) if denom > 0 else None


def report(y_true, scores, threshold: float) -> dict:
    y_true = np.asarray(y_true).astype(int)
    scores = np.asarray(scores, dtype=float)
    y_pred = (scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    tpr = tp / max(tp + fn, 1)
    fpr = fp / max(fp + tn, 1)
    p_bin, r_bin, f_bin, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    p_mac, r_mac, f_mac, _ = precision_recall_fscore_support(y_true, y_pred, average="macro", zero_division=0)
    p_w, r_w, f_w, _ = precision_recall_fscore_support(y_true, y_pred, average="weighted", zero_division=0)
    return {
        "n": int(len(y_true)), "positives": int(y_true.sum()), "threshold": round(float(threshold), 4),
        "accuracy": round(float((y_pred == y_true).mean()), 4),
        "fraud_class": {"precision": round(float(p_bin), 4), "recall": round(float(r_bin), 4),
                        "f1": round(float(f_bin), 4)},
        "macro_average": {"precision": round(float(p_mac), 4), "recall": round(float(r_mac), 4),
                          "f1": round(float(f_mac), 4)},
        "weighted_average": {"precision": round(float(p_w), 4), "recall": round(float(r_w), 4),
                             "f1": round(float(f_w), 4)},
        "false_positive_rate": round(float(fpr), 5),
        "true_positive_rate": round(float(tpr), 4),
        "confusion": {"tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn)},
        "roc_auc": round(float(roc_auc_score(y_true, scores)), 4) if 0 < y_true.sum() < len(y_true) else None,
        "average_precision": round(float(average_precision_score(y_true, scores)), 4) if y_true.sum() else None,
        "precision_at_1pct_prevalence": at_base_rate(tpr, fpr, 0.01),
        "precision_at_0_1pct_prevalence": at_base_rate(tpr, fpr, 0.001),
    }
