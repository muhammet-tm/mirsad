"""Client for the sandbox VM: page capture and Phishpedia logo matching run there, never on the host."""

from __future__ import annotations

import base64
from pathlib import Path

from ..config import DATA_DIR, http_client, settings

CAPTURE_DIR = DATA_DIR / "captures"


def available() -> bool:
    try:
        with http_client(timeout=3) as c:
            return c.get(f"{settings.sandbox_url}/health").json().get("ok", False)
    except Exception:
        return False


def capture(case_id: str, url: str, timeout_s: int = 15) -> dict | None:
    """Ask the sandbox to load the page once; store the screenshot locally and return the facts."""
    try:
        with http_client(timeout=timeout_s + 20) as c:
            r = c.post(f"{settings.sandbox_url}/capture", json={"url": url, "timeout_s": timeout_s})
        data = r.json()
    except Exception:
        return None
    if data.get("error"):
        return {"error": data["error"]}
    shot = data.pop("screenshot_b64", None)
    if shot:
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        path = CAPTURE_DIR / f"{case_id}.png"
        path.write_bytes(base64.b64decode(shot))
        data["screenshot"] = f"/captures/{case_id}.png"
        data["_shot_b64"] = shot
    return data


def phishpedia(url: str, screenshot_b64: str) -> dict | None:
    try:
        with http_client(timeout=60) as c:
            r = c.post(f"{settings.sandbox_url}/phishpedia", json={"url": url, "screenshot_b64": screenshot_b64})
        data = r.json()
        return data if data.get("available", True) else None
    except Exception:
        return None


def screenshot_path(case_id: str) -> Path:
    return CAPTURE_DIR / f"{case_id}.png"
