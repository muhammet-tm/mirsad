"""Read only the URL, label, and date columns of PhreshPhish's test files, without the page HTML.

PhreshPhish (CC BY 4.0, https://huggingface.co/datasets/phreshphish/phreshphish) stores full pages,
36.6 GB in all. Parquet lets us fetch single columns with HTTP range requests, a few MB in total.

Usage:
    python scripts/phreshphish_columns.py --schema
    python scripts/phreshphish_columns.py --out data/raw/phreshphish_test_urls.parquet
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import truststore  # noqa: E402

truststore.inject_into_ssl()

from huggingface_hub import HfFileSystem  # noqa: E402

REPO = "datasets/phreshphish/phreshphish"


def test_files(fs: HfFileSystem) -> list[str]:
    files = fs.glob(f"{REPO}/data/*.parquet")
    split = getattr(test_files, "split", "test")
    return sorted(f for f in files if f.rsplit("/", 1)[-1].lower().startswith(split))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--columns", default="url,label,target,date,lang")
    ap.add_argument("--split", default="test", choices=["test", "train"])
    a = ap.parse_args()
    fs = HfFileSystem()
    test_files.split = a.split
    files = test_files(fs)
    if a.schema or not a.out:
        with fs.open(files[0], "rb") as f:
            pf = pq.ParquetFile(f)
            print(json.dumps({"test_files": files, "schema": str(pf.schema_arrow),
                              "rows_first_file": pf.metadata.num_rows}, indent=1))
        return
    cols = [c.strip() for c in a.columns.split(",")]
    tables = []
    for path in files:
        with fs.open(path, "rb") as f:
            pf = pq.ParquetFile(f)
            present = [c for c in cols if c in pf.schema_arrow.names]
            tables.append(pf.read(columns=present))
    table = pa.concat_tables(tables, promote_options="default")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out)
    print(json.dumps({"files": len(files), "rows": table.num_rows, "columns": table.column_names, "to": str(out)}))


if __name__ == "__main__":
    main()


