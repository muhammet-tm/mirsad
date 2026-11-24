"""Run Mirsad with one command on Windows, macOS, or Linux.

    python run.py                  set up, load demo cases on first run, start, and open the dashboard
    python run.py --score FILE     score a list of URLs (one per line, or a CSV with a url column)
    python run.py --test           run the test suite

The first run creates a virtual environment in .venv and installs requirements.txt (about 5 minutes
and 400 MB of downloads); later runs reuse it. Python 3.11 to 3.13 is required, because the deployed
model was saved with NumPy 2.3 and scikit-learn 1.7. No API key is needed to explore the dashboard,
check links, or score a test set; keys in .env (see .env.example) switch on the live search and map
channels and the Jais summaries.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import threading
import time
import urllib.request
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
MARK = VENV / ".mirsad-requirements"


def say(msg: str) -> None:
    print(f"[mirsad] {msg}", flush=True)


def ensure_python() -> None:
    if not ((3, 11) <= sys.version_info[:2] <= (3, 13)):
        sys.exit(f"[mirsad] Python 3.11 to 3.13 is required; this is {sys.version.split()[0]}. "
                 "Install one from python.org and run it, for example: py -3.12 run.py (Windows) or python3.12 run.py")


def ensure_env() -> None:
    """Create .venv and install requirements.txt when it is missing or has changed."""
    digest = hashlib.sha256((ROOT / "requirements.txt").read_bytes()).hexdigest()
    if PY.exists() and MARK.exists() and MARK.read_text().strip() == digest:
        return
    if not PY.exists():
        say("creating the virtual environment in .venv")
        venv.EnvBuilder(with_pip=True).create(VENV)
    say("installing requirements (first run only; this takes a few minutes)")
    subprocess.run([str(PY), "-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade", "pip"], check=True)
    subprocess.run([str(PY), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r",
                    str(ROOT / "requirements.txt")], check=True)
    MARK.write_text(digest)


def in_env(*args: str) -> int:
    return subprocess.run([str(PY), *args], cwd=ROOT).returncode


def open_when_ready(url: str) -> None:
    for _ in range(120):
        try:
            with urllib.request.urlopen(url + "api/health", timeout=2):
                webbrowser.open(url)
                say(f"dashboard open at {url}  (press Ctrl+C here to stop)")
                return
        except Exception:
            time.sleep(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run Mirsad: dashboard, test-set scoring, or tests.")
    ap.add_argument("--score", type=Path, metavar="FILE", help="score a list of URLs and write a CSV")
    ap.add_argument("--out", type=Path, default=Path("scored.csv"), help="output CSV for --score")
    ap.add_argument("--expand-short-links", action="store_true", help="with --score: follow short links")
    ap.add_argument("--test", action="store_true", help="run the test suite")
    ap.add_argument("--port", type=int, default=8600)
    ap.add_argument("--no-demo", action="store_true", help="do not load demo cases into an empty database")
    ap.add_argument("--no-feeds", action="store_true", help="demo cases without the live public feeds")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    ensure_python()
    ensure_env()
    if a.test:
        sys.exit(in_env("-m", "pytest", "-q"))
    if a.score:
        extra = ["--expand-short-links"] if a.expand_short_links else []
        sys.exit(in_env("scripts/score_urls.py", str(a.score.resolve()), "--out", str(a.out.resolve()), *extra))
    if not a.no_demo:
        say("loading demo cases into an empty database (skipped when cases exist)")
        in_env("scripts/load_demo.py", *(["--no-feeds"] if a.no_feeds else []))
    url = f"http://127.0.0.1:{a.port}/"
    if not a.no_browser:
        threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    say(f"starting the service on {url}")
    try:
        in_env("-m", "uvicorn", "mirsad.api.app:app", "--host", "127.0.0.1", "--port", str(a.port))
    except KeyboardInterrupt:
        say("stopped")


if __name__ == "__main__":
    main()
