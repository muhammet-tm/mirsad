"""Container entry point for the public demo: seed the database once, then serve on port 7860.

The Space's disk is not persistent, so every restart begins again from deploy/seed.sqlite3 (our lab
cases with redacted links, plus the demo links). Without a seed the demo links are loaded instead.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "mirsad.sqlite3"
SEED = ROOT / "deploy" / "seed.sqlite3"

if not DB.exists():
    if SEED.exists():
        shutil.copyfile(SEED, DB)
    else:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "load_demo.py"), "--no-feeds"], cwd=ROOT, check=False)

port = os.environ.get("PORT", "7860")
# One worker: the run budgets and the scheduler live in this process.
os.execvp(sys.executable, [sys.executable, "-m", "uvicorn", "mirsad.api.app:app", "--host", "0.0.0.0",
                           "--port", port, "--workers", "1", "--no-server-header"])
