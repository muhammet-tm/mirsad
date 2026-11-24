"""Publish the public demo to a Hugging Face Space (Docker SDK).

The build folder is assembled from an allow-list, so nothing outside it can leave the machine: no
.env, no raw data, no lab database, no captures. Before uploading, every staged text file is checked
against secret patterns and against the actual values in .env (compared locally, never printed).
API keys are added by the account owner as Space secrets in the Space settings, never by this script.

Sign in first with a write token: .venv\\Scripts\\hf.exe auth login
Usage:
  python scripts/deploy_space.py --dry-run        stage and check only
  python scripts/deploy_space.py                  stage, check, and upload to <your user>/mirsad
  python scripts/deploy_space.py --repo user/name
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "deploy" / "_stage"

# (source, destination in the Space). Directories copy recursively without caches.
ALLOW = [
    ("deploy/space/Dockerfile", "Dockerfile"),
    ("deploy/space/README.md", "README.md"),
    ("requirements.txt", "requirements.txt"),
    ("deploy/requirements-deploy.txt", "requirements-deploy.txt"),
    ("deploy/start.py", "deploy/start.py"),
    ("deploy/seed.sqlite3", "deploy/seed.sqlite3"),
    ("LICENSE.md", "LICENSE.md"),
    ("mirsad", "mirsad"),
    ("web", "web"),
    ("models/dae2_deploy.joblib", "models/dae2_deploy.joblib"),
    ("models/dae2_deploy.card.json", "models/dae2_deploy.card.json"),
    ("demo/demo_links.csv", "demo/demo_links.csv"),
    ("results/numbers.json", "results/numbers.json"),
    ("scripts/load_demo.py", "scripts/load_demo.py"),
    ("deck/vendor/fonts", "deck/vendor/fonts"),
]
SKIP_DIRS = {"__pycache__", "_qa", ".pytest_cache"}
SECRET_PATTERNS = [
    re.compile(r"hf_[A-Za-z0-9]{30,}"), re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"(?i)(api[_-]?key|auth[_-]?key|secret|password|token)\s*[=:]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
TEXT = {".py", ".js", ".css", ".html", ".json", ".md", ".txt", ".csv", ".cjs", ""}


def stage() -> list[Path]:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    files = []
    for src, dst in ALLOW:
        s, d = ROOT / src, STAGE / dst
        if not s.exists():
            sys.exit(f"missing {src}; for deploy/seed.sqlite3 run: python scripts/make_snapshot.py")
        if s.is_dir():
            for f in s.rglob("*"):
                if f.is_file() and not (SKIP_DIRS & set(f.relative_to(s).parts)) and f.suffix != ".pyc":
                    t = d / f.relative_to(s)
                    t.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, t)
                    files.append(t)
        else:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)
            files.append(d)
    return files


def env_values() -> list[str]:
    """Values from the local .env files (repository and parent), only to prove none is staged."""
    vals = []
    for p in (ROOT / ".env", ROOT.parent / ".env"):
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    v = v.strip().strip("'\"")
                    # Only secrets: settings such as a local stream address may appear in code on purpose.
                    if len(v) >= 12 and re.search(r"KEY|TOKEN|SECRET|PASSWORD|ACCOUNT|CREDENTIAL", k.upper()):
                        vals.append(v)
    return vals


def check(files: list[Path]) -> None:
    secrets = env_values()
    bad = []
    for f in files:
        name = f.name.lower()
        if name.startswith(".env") or name.endswith((".key", ".pem")) or name == "kaggle.json":
            bad.append(f"{f.relative_to(STAGE)}: secret file")
            continue
        data = f.read_bytes()
        if f.suffix in TEXT:
            text = data.decode("utf-8", errors="ignore")
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    bad.append(f"{f.relative_to(STAGE)}: matches {pat.pattern[:30]}")
        for v in secrets:
            if v.encode() in data:
                bad.append(f"{f.relative_to(STAGE)}: contains a value from .env")
                break
    if bad:
        sys.exit("refusing to deploy:\n  " + "\n  ".join(bad))


def check_seed(path: Path) -> None:
    """The seed must hold no query value: every link column keeps only [redacted] placeholders."""
    import sqlite3

    leaks = []
    with sqlite3.connect(path) as c:
        for table, col in (("candidates", "url"), ("candidates", "url_redacted"), ("candidates", "canonical"),
                           ("captures", "final_url")):
            for (v,) in c.execute(f"SELECT {col} FROM {table} WHERE {col} LIKE '%?%'"):
                query = (v or "").split("?", 1)[1].split("#", 1)[0]
                if any("=" in p and p.split("=", 1)[1] not in ("", "[redacted]") for p in query.split("&")):
                    leaks.append(f"{table}.{col}")
                    break
        if c.execute("SELECT COUNT(*) FROM audit").fetchone()[0]:
            leaks.append("audit rows")
        # Free text too: a summary or an evidence line must not quote a link with its query values.
        value = re.compile(r"\?[^\s\"'<>]*?=(?!\[redacted\]|&|$)[^&\s\"'<>\]]+")
        for table, col in (("summaries", "en"), ("summaries", "ar"), ("evidence", "label"), ("evidence", "value_json"),
                           ("captures", "title"), ("decisions", "note")):
            if any(value.search(v or "") for (v,) in c.execute(f"SELECT {col} FROM {table}")):
                leaks.append(f"{table}.{col}")
    if leaks:
        sys.exit("refusing to deploy: the seed database still holds query values or audit rows in "
                 + ", ".join(sorted(set(leaks))) + "; rebuild it with scripts/make_snapshot.py")


def main() -> None:
    ap = argparse.ArgumentParser(description="Publish the Mirsad public demo to a Hugging Face Space.")
    ap.add_argument("--repo", help="Space id, user/name (default: <signed-in user>/mirsad)")
    ap.add_argument("--dry-run", action="store_true", help="stage and check only")
    a = ap.parse_args()

    files = stage()
    check(files)
    check_seed(STAGE / "deploy" / "seed.sqlite3")
    size = sum(f.stat().st_size for f in files)
    print(f"staged {len(files)} files, {size / 2**20:.1f} MB, in {STAGE}; secret check passed")
    if a.dry_run:
        return

    from huggingface_hub import HfApi

    api = HfApi()
    repo = a.repo or f"{api.whoami()['name']}/mirsad"
    api.create_repo(repo, repo_type="space", space_sdk="docker", exist_ok=True, private=False)
    api.upload_folder(folder_path=str(STAGE), repo_id=repo, repo_type="space",
                      commit_message="Deploy Mirsad public demo",
                      delete_patterns=["mirsad/**", "web/**", "deploy/**", "scripts/**", "deck/**", "demo/**", "results/**"])
    user, name = repo.split("/")
    print(f"uploaded; the Space builds at https://huggingface.co/spaces/{repo} and serves "
          f"https://{user.lower()}-{name.lower()}.hf.space")


if __name__ == "__main__":
    main()
