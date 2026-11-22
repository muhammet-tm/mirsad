"""Fill measured numbers into the documents, so no number is ever typed by hand.

Every results/*.json file is flattened into dotted keys (for example
`e1a.at_validation_threshold.dae2_mean.accuracy`) and written to results/numbers.json. Each
`*.src.md` file (README.src.md at the root, docs/*.src.md) is rendered to the matching `.md`,
replacing {{key}}, {{pct:key}} (percent, one decimal), {{pct2:key}} (two decimals),
{{int:key}} (thousands separators), and {{n2:key}} (two decimals). A missing key stops the build.

Usage: python scripts/build_docs.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
SHORT = {"e0_audit_kaggle": "e0", "e1a_paper_repr_random_split": "e1a", "e1b_our_repr_random_split": "e1b",
         "e2_paper_repr_domain_split": "e2p", "e2_ours_repr_domain_split": "e2o",
         "e3a_our_repr_phreshphish_temporal": "e3a", "e3b_paper_model_on_phreshphish_test": "e3b",
         "e4_scoring_speed": "e4", "live_eval": "live", "counts": "counts"}


def flatten(obj, prefix: str, out: dict) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(v, f"{prefix}.{k}" if prefix else str(k), out)
    elif isinstance(obj, list):
        out[prefix] = obj
        for i, v in enumerate(obj):
            flatten(v, f"{prefix}.{i}", out)
    else:
        out[prefix] = obj


def numbers() -> dict:
    out: dict = {}
    for path in sorted(RESULTS.glob("*.json")):
        if path.name == "numbers.json":
            continue
        key = SHORT.get(path.stem, path.stem)
        flatten(json.loads(path.read_text(encoding="utf-8")), key, out)
    derived(out)
    return out


def derived(n: dict) -> None:
    """Numbers computed from other numbers (never typed)."""
    a, b = "e1a.at_validation_threshold.dae2_mean.accuracy", "e1b.at_validation_threshold.dae2_mean.accuracy"
    if a in n and b in n:
        n["delta.e1.accuracy_points"] = round(100 * (n[a] - n[b]), 2)
    a, b = "e1a.at_validation_threshold.dae2_mean.accuracy", "e2p.at_validation_threshold.dae2_mean.accuracy"
    if a in n and b in n:
        n["delta.e1a_e2p.accuracy_points"] = round(100 * (n[a] - n[b]), 2)


def fmt(kind: str, value) -> str:
    if kind == "pct":
        return f"{100 * float(value):.1f}%"
    if kind == "pct2":
        return f"{100 * float(value):.2f}%"
    if kind == "int":
        return f"{int(value):,}"
    if kind == "n2":
        return f"{float(value):.2f}"
    return str(value)


LABELS = {"adaboost": "AdaBoost", "bagging": "Bagging", "stacking": "Stacking", "voting": "Voting",
          "dae2_mean": "DaE2 (mean of the four)"}


def table(prefix: str, nums: dict, block: str = "at_validation_threshold") -> str:
    """Markdown table of one experiment's ensembles at its frozen threshold."""
    head = ("| Model | Accuracy | Precision (fraud) | Recall (fraud) | F1 (fraud) | False-positive rate | ROC AUC | "
            "Precision if 1% of links are fraud |\n|---|---|---|---|---|---|---|---|\n")
    rows = []
    for m, label in LABELS.items():
        k = f"{prefix}.{block}.{m}"
        if f"{k}.accuracy" not in nums:
            continue
        g = lambda s: nums.get(f"{k}.{s}")  # noqa: E731
        p1 = g("precision_at_1pct_prevalence")
        rows.append(f"| {label} | {fmt('pct', g('accuracy'))} | {fmt('pct', g('fraud_class.precision'))} | "
                    f"{fmt('pct', g('fraud_class.recall'))} | {fmt('n2', g('fraud_class.f1'))} | "
                    f"{fmt('pct2', g('false_positive_rate'))} | {fmt('n2', g('roc_auc')) if g('roc_auc') is not None else 'n/a'} | "
                    f"{fmt('pct', p1) if p1 is not None else 'n/a'} |")
    if not rows:
        raise KeyError(prefix)
    return head + "\n".join(rows)


def render(text: str, nums: dict, source: str) -> str:
    missing = []

    def tab(m):
        try:
            return table(m.group(1), nums, m.group(2) or "at_validation_threshold")
        except KeyError:
            missing.append("table:" + m.group(1))
            return m.group(0)

    text = re.sub(r"\{\{table:([a-z0-9]+)(?::([a-z0-9_]+))?\}\}", tab, text)

    def sub(m):
        kind, key = (m.group(1) or "").rstrip(":"), m.group(2)
        if key not in nums or nums[key] is None:
            missing.append(key)
            return m.group(0)
        return fmt(kind, nums[key])

    out = re.sub(r"\{\{(?:(pct2|pct|int|n2):)?([A-Za-z0-9_.\-]+)\}\}", sub, text)
    if missing:
        sys.exit(f"{source}: missing numbers {sorted(set(missing))}")
    return out


def main() -> None:
    nums = numbers()
    (RESULTS / "numbers.json").write_text(json.dumps(nums, indent=1, default=str), encoding="utf-8")
    sources = [ROOT / "README.src.md", *sorted((ROOT / "docs").glob("*.src.md"))]
    for src in sources:
        if src.exists():
            dst = src.with_name(src.name.replace(".src.md", ".md"))
            dst.write_text("<!-- Generated from " + src.name + " by scripts/build_docs.py. Edit the source. -->\n"
                           + render(src.read_text(encoding="utf-8"), nums, src.name), encoding="utf-8")
            print(f"wrote {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
