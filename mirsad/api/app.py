"""Mirsad API and dashboard server.

Run: python -m uvicorn mirsad.api.app:app --host 127.0.0.1 --port 8600
The server binds to localhost by default. Every case view, decision, and export is audited.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__, pipeline
from ..config import DATA_DIR, ROOT, settings
from ..sandbox import client as sandbox
from ..scoring.engine import Signals, model_info, score, score_batch, threshold
from ..store import Store, now, redact
from .cases import build_case, kpis, list_cases, map_data

app = FastAPI(title="Mirsad", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")
store = Store()
_running: dict[str, bool] = {}
WEB = ROOT / "web"
CAPTURES = DATA_DIR / "captures"
CHANNELS = {"search": "Search monitor", "maps": "Maps check", "certificates": "Certificate stream", "feeds": "Feeds"}


class Decision(BaseModel):
    action: str = Field(pattern="^(confirm|dismiss|reviewing|assign)$")
    note: str = ""
    analyst: str = "Duty analyst"


class Check(BaseModel):
    url: str = Field(min_length=4, max_length=2048)
    save: bool = False


class CheckBatch(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=10_000)


@app.get("/api/health")
def health():
    info = model_info()
    return {"ok": True, "version": __version__,
            "model": {"name": "DaE2", "file": info.get("file"), "threshold": threshold(),
                      "trained_on": info.get("trained_on"), "train_date_range": info.get("train_date_range")},
            "integrations": {"search": settings.has("SERPAPI_API_KEY") or settings.has("SERPER_API_KEY"),
                             "maps": settings.has("PLACES_API_KEY"), "certificates": True, "feeds": True,
                             "sandbox": sandbox.available(), "llm": settings.llm_mode}}


@app.get("/api/status")
def status():
    chans = []
    for cid, label in CHANNELS.items():
        last = store.one("SELECT * FROM runs WHERE channel = ? ORDER BY id DESC LIMIT 1", (cid,))
        if _running.get(cid):
            state = "live"
        elif not last:
            state = "idle"
        elif last["state"] == "error":
            state = "error"
        else:
            state = "synced" if cid == "feeds" else "live"
        chans.append({"id": cid, "label": label, "state": state,
                      "last_run": (last or {}).get("finished") or (last or {}).get("started"),
                      "detail": (last or {}).get("detail") or "not run yet"})
    return {"channels": chans, "model": {"name": "DaE2 v1", "threshold": threshold()}, "now": now()}


@app.get("/api/kpis")
def get_kpis():
    return kpis(store)


@app.get("/api/cases")
def get_cases(status: str = "open", channel: str = "all", limit: int = 50):
    return list_cases(store, status, channel, min(limit, 500))


@app.get("/api/cases/{cid}")
def get_case(cid: str, request: Request):
    case = build_case(store, cid)
    if not case:
        raise HTTPException(404, "case not found")
    store.audit("Duty analyst", "view", cid, request.client.host if request.client else "")
    return case


@app.post("/api/cases/{cid}/decision")
def decide(cid: str, d: Decision):
    if not build_case(store, cid):
        raise HTTPException(404, "case not found")
    store.decide(cid, d.action, d.analyst, d.note)
    return build_case(store, cid)


@app.get("/api/cases/{cid}/export")
def export(cid: str):
    case = build_case(store, cid)
    if not case:
        raise HTTPException(404, "case not found")
    raw = store.one("SELECT url FROM candidates WHERE id = ?", (cid,))["url"]
    package = {
        "package": "Mirsad evidence package", "version": 1, "generated_at": now(), "case": cid,
        "purpose": "Supports a registrar abuse report, an aeDA complaint, or an Abu Dhabi Police blocking request "
                   "(Federal Decree-Law No. 34 of 2021, Articles 62 and 66). Mirsad recommends; an officer decides.",
        "link": {"url": raw, "url_redacted": case["url_redacted"], "domain": case["domain"]},
        "risk": case["risk"], "threshold": case["threshold"], "ensemble_votes": case["votes"],
        "imitates": case["imitates"], "official_domains": case["official_domains"], "reasons": case["reasons"],
        "evidence": case["evidence"], "capture": case["capture"], "channel": case["channel_detail"],
        "decisions": case["decisions"],
        "handling": "Contains a raw link that may hold personal data in its query string. Share only with the authority named above.",
    }
    store.audit("Duty analyst", "export", cid, "evidence package")
    return JSONResponse(package, headers={"Content-Disposition": f'attachment; filename="{cid}_evidence.json"'})


@app.post("/api/check")
def check(c: Check):
    r = score(Signals(url=c.url, channel="report"))
    out = {"url": redact(c.url), "risk": r.risk, "threshold": r.threshold, "votes": r.votes, "reasons": r.reasons,
           "imitates": r.imitates, "flagged": r.risk >= r.threshold, "scoring_ms": r.scoring_ms}
    if c.save:
        cid, _ = pipeline.process(store, pipeline.Found(c.url, "report", "Reported link"), use_sandbox=sandbox.available())
        out["case_id"] = cid
    store.audit("Duty analyst", "check", redact(c.url), json.dumps({"risk": r.risk}))
    return out


@app.post("/api/check/batch")
def check_batch(c: CheckBatch):
    """Score up to 10,000 links at once (a test set or a bulk list); nothing is stored but an audit entry."""
    urls = [u.strip()[:2048] for u in c.urls if u and u.strip()]
    results = score_batch(urls)
    thr = threshold()
    store.audit("Duty analyst", "check_batch", f"{len(urls)} links", json.dumps({"flagged": sum(r.risk >= thr for r in results)}))
    return {"threshold": thr, "results": [
        {"url": redact(u), "risk": r.risk, "flagged": r.risk >= thr, "votes": r.votes, "reasons": r.reasons,
         "imitates": r.imitates} for u, r in zip(urls, results)]}


@app.post("/api/runs/{channel}")
def start_run(channel: str):
    if channel not in CHANNELS:
        raise HTTPException(404, "unknown channel")
    if _running.get(channel):
        return {"channel": channel, "state": "already running"}

    def work():
        _running[channel] = True
        try:
            pipeline.run(channel, store)
        finally:
            _running[channel] = False

    threading.Thread(target=work, daemon=True).start()
    return {"channel": channel, "started": now()}


@app.get("/api/map")
def get_map():
    return map_data(store)


@app.get("/api/audit")
def audit(limit: int = 100):
    return {"items": store.rows("SELECT at, actor, action, target, detail FROM audit ORDER BY id DESC LIMIT ?", (min(limit, 1000),))}


@app.get("/captures/{name}")
def capture_file(name: str):
    path = (CAPTURES / name).resolve()
    if CAPTURES.resolve() not in path.parents or not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp: Response = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
