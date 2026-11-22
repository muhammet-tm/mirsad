"""Download the datasets the models are trained and tested on.

Usage:
    python scripts/download_data.py kaggle        # malicious_phish (Kaggle, CC0), about 46 MB
    python scripts/download_data.py tranco        # Tranco top sites list (benign reference)
    python scripts/download_data.py phreshphish --info   # show size before downloading
    python scripts/download_data.py phreshphish --sample 20000   # recent phishing and benign URLs

Files land in data/raw/, which git ignores.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mirsad.config import RAW_DIR, http_client, settings  # noqa: E402

KAGGLE_DATASET = "sid321axn/malicious-urls-dataset"


def kaggle() -> None:
    token = settings.key("KAGGLE_API_TOKEN")
    if not token:
        sys.exit("KAGGLE_API_TOKEN is not set in .env")
    url = f"https://www.kaggle.com/api/v1/datasets/download/{KAGGLE_DATASET}"
    with http_client(follow_redirects=True, timeout=300) as c:
        r = c.get(url, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        names = z.namelist()
        z.extractall(RAW_DIR)
    print(json.dumps({"downloaded": names, "bytes": len(r.content), "to": str(RAW_DIR)}))


def tranco() -> None:
    with http_client(follow_redirects=True, timeout=120) as c:
        meta = c.get("https://tranco-list.eu/api/lists/date/latest").json()
        list_id = meta["list_id"]
        r = c.get(f"https://tranco-list.eu/download/{list_id}/1000000")
        r.raise_for_status()
    out = RAW_DIR / "tranco_top1m.csv"
    out.write_bytes(r.content)
    (RAW_DIR / "tranco_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps({"list_id": list_id, "created": meta.get("created_on"), "bytes": len(r.content)}))


def phreshphish(info: bool, sample: int | None) -> None:
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi()
    files = api.list_repo_tree("phreshphish/phreshphish", repo_type="dataset", recursive=True)
    listing = [(f.path, getattr(f, "size", 0) or 0) for f in files if hasattr(f, "size")]
    if info or sample is None:
        total = sum(s for _, s in listing)
        print(json.dumps({"files": listing, "total_bytes": total}, indent=1))
        return
    target = RAW_DIR / "phreshphish"
    target.mkdir(parents=True, exist_ok=True)
    # The test split is what our temporal evaluation needs; take its parquet files only.
    wanted = [p for p, _ in listing if p.endswith(".parquet") and "test" in p.lower()]
    for p in wanted:
        hf_hub_download("phreshphish/phreshphish", p, repo_type="dataset", local_dir=target)
    print(json.dumps({"downloaded": wanted, "to": str(target)}))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["kaggle", "tranco", "phreshphish"])
    ap.add_argument("--info", action="store_true")
    ap.add_argument("--sample", type=int)
    a = ap.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if a.what == "kaggle":
        kaggle()
    elif a.what == "tranco":
        tranco()
    else:
        phreshphish(a.info, a.sample)


if __name__ == "__main__":
    main()
