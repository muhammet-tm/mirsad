"""Settings and secrets.

Keys are read from a `.env` file. The loader looks in the repository root first and then in the
parent folder, so a team can keep its keys outside the repository. Values are never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = ROOT / "models"
RESULTS_DIR = ROOT / "results"
DB_PATH = DATA_DIR / "mirsad.sqlite3"

# Older spellings that a team member may still have in .env; the first name in each tuple wins.
_ALIASES = {
    "ABUSECH_AUTH_KEY": ("ABUSECH_AUTH_KEY", "ABUSE.CH_AUTH_KEY"),
    "VIRUSTOTAL_API_KEY": ("VIRUSTOTAL_API_KEY", "VIRUSTOTAL_API_KET"),
}


def _load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for candidate in (ROOT.parent / ".env", ROOT / ".env"):
        if candidate.exists():
            values.update({k: v for k, v in dotenv_values(candidate).items() if v})
    values.update({k: v for k, v in os.environ.items() if k.isupper()})
    for canonical, names in _ALIASES.items():
        for name in names:
            if values.get(name):
                values[canonical] = values[name]
                break
    return values


@dataclass(frozen=True)
class Settings:
    env: dict[str, str] = field(default_factory=_load_env, repr=False)

    def key(self, name: str) -> str | None:
        """Return a secret by name, or None when it is not set."""
        return self.env.get(name) or None

    def has(self, name: str) -> bool:
        return bool(self.env.get(name))

    # Non-secret settings with defaults that the team can override in .env.
    @property
    def threshold(self) -> float:
        return float(self.env.get("MIRSAD_THRESHOLD", "0.80"))

    @property
    def sandbox_url(self) -> str:
        return self.env.get("MIRSAD_SANDBOX_URL", "http://127.0.0.1:8601")

    @property
    def llm_mode(self) -> str:
        """'jais' (default), 'falcon' (local, zero egress), or 'off'."""
        return self.env.get("MIRSAD_LLM", "jais").lower()

    @property
    def jais_model(self) -> str:
        return self.env.get("JAIS_MODEL", "IFM/Jais-3-MoVA-36B-A4B")

    @property
    def jais_base_url(self) -> str:
        return self.env.get("JAIS_BASE_URL", "https://api.ifm.ai/v1")

    @property
    def falcon_base_url(self) -> str:
        return self.env.get("FALCON_BASE_URL", "http://127.0.0.1:8602/v1")

    def describe(self) -> dict[str, bool]:
        """Which integrations are configured, without exposing any value."""
        names = ["JAIS_API_KEY", "SERPAPI_API_KEY", "SERPER_API_KEY", "PLACES_API_KEY",
                 "ABUSECH_AUTH_KEY", "VIRUSTOTAL_API_KEY", "KAGGLE_API_TOKEN"]
        return {n: self.has(n) for n in names}


settings = Settings()

# httpx logs every request URL at INFO level, and some providers (SerpApi) take the key in the URL.
# Keep those loggers quiet everywhere Mirsad runs, so a key can never reach a log file.
import logging as _logging  # noqa: E402

for _name in ("httpx", "httpcore"):
    _logging.getLogger(_name).setLevel(_logging.WARNING)


def http_client(**kwargs):
    """An httpx client that trusts the operating system's certificate store.

    Some networks (including the development laptop's) inspect TLS with their own root
    certificate, which Python's bundled store does not know.
    """
    import ssl

    import httpx
    import truststore

    ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    kwargs.setdefault("timeout", httpx.Timeout(30.0, connect=10.0))
    kwargs.setdefault("headers", {"User-Agent": "Mirsad/0.1 (fraud link research prototype)"})
    return httpx.Client(verify=ctx, **kwargs)
