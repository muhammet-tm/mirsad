"""Mirsad API and dashboard server.

Run: python -m uvicorn mirsad.api.app:app --host 127.0.0.1 --port 8600
The server binds to localhost by default. Every case view, decision, and export is audited.
With MIRSAD_PUBLIC=1 it runs as the public demo site (see Settings.public), and with
MIRSAD_SCHEDULE=1 it runs the free channels itself: feeds every hour, certificates every day.
"""

from __future__ import annotations

import json
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__, pipeline
from ..config import DATA_DIR, ROOT, settings
from ..sandbox import client as sandbox
from ..scoring.engine import Signals, model_info, score, score_batch, threshold
from ..store import Store, now, redact
from . import report
from .cases import build_case, kpis, list_cases, map_data

store = Store()
_running: dict[str, bool] = {}
# Public site: runs a channel may start per window, so no visitor can spend the shared API quotas.
# A search run spends 23 SerpApi queries and a maps run 11 Places calls; feeds and crt.sh are free.
DAY, HOUR = 86400, 3600
RUN_BUDGET = {"search": (3, DAY), "maps": (4, DAY), "certificates": (2, HOUR), "feeds": (4, HOUR)}
SAVED_CHECKS_PER_HOUR = 30  # each saved check may call DNS, reputation lists, and Jais
_spent: dict[str, list[float]] = {}
_batch_lock = threading.Lock()
SCHEDULE = {"feeds": 3600, "certificates": 86400}  # seconds between scheduled runs


def _within_budget(key: str, limit: int, window: int = HOUR) -> bool:
    """Count one use against a budget per window; False when it is spent (public site only)."""
    if not settings.public:
        return True
    cutoff = time.monotonic() - window
    used = [t for t in _spent.get(key, []) if t > cutoff]
    if len(used) >= limit:
        _spent[key] = used
        return False
    _spent[key] = used + [time.monotonic()]
    return True


def _launch(channel: str) -> bool:
    if _running.get(channel):
        return False

    def work():
        _running[channel] = True
        try:
            pipeline.run(channel, store)
        except Exception:
            pass  # the run row records the error for the status strip
        finally:
            _running[channel] = False

    threading.Thread(target=work, daemon=True).start()
    return True


def _scheduler(stop: threading.Event) -> None:
    while not stop.wait(30):
        for channel, every in SCHEDULE.items():
            last = store.one("SELECT started FROM runs WHERE channel = ? ORDER BY id DESC LIMIT 1", (channel,))
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(last["started"].replace("Z", "+00:00"))).total_seconds() if last else every
            except (TypeError, ValueError):
                age = every
            if age >= every:
                _launch(channel)


@asynccontextmanager
async def lifespan(_app):
    stop = threading.Event()
    if settings.env.get("MIRSAD_SCHEDULE", "").lower() in ("1", "true", "yes"):
        threading.Thread(target=_scheduler, args=(stop,), daemon=True).start()
    yield
    stop.set()


app = FastAPI(title="Mirsad", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json",
              lifespan=lifespan)
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
                             "sandbox": sandbox.available(), "llm": settings.llm_mode},
            "public": settings.public,
            "budgets": ({c: {"runs": n, "per": "day" if w == DAY else "hour"} for c, (n, w) in RUN_BUDGET.items()}
                        if settings.public else None),
            "schedule": ({c: s for c, s in SCHEDULE.items()}
                         if settings.env.get("MIRSAD_SCHEDULE", "").lower() in ("1", "true", "yes") else None)}


@app.get("/api/model")
def model_card():
    """What the model is and how it measured, for the dashboard's Model panel (numbers from results/*.json)."""
    from ..collectors.sources import MAPS_QUERIES, SEARCH_QUERIES
    from ..features.brands import BRANDS
    from ..features.url import lexical_features
    from ..scoring.engine import MODEL_ALONE

    try:
        n = json.loads((ROOT / "results" / "numbers.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        n = {}
    m = lambda e, k: n.get(f"{e}.at_validation_threshold.dae2_mean.{k}")  # noqa: E731
    info = model_info()
    return {"threshold": threshold(), "model_alone": MODEL_ALONE, "ensembles": ["AdaBoost", "Bagging", "Stacking", "Voting"],
            "lexical_features": len(lexical_features("https://example.com/")), "brands": len(BRANDS),
            "search_queries": len(SEARCH_QUERIES), "maps_queries": len(MAPS_QUERIES),
            "trained_on": info.get("trained_on"), "train_date_range": info.get("train_date_range"),
            "results": [
                {"id": "e1a", "accuracy": m("e1a", "accuracy"), "false_positive_rate": m("e1a", "false_positive_rate")},
                {"id": "e2", "accuracy": n.get("e2o.at_validation_threshold.dae2_mean.accuracy")},
                {"id": "e3a", "accuracy": m("e3a", "accuracy"), "recall": m("e3a", "fraud_class.recall"),
                 "false_positive_rate": m("e3a", "false_positive_rate"), "roc_auc": m("e3a", "roc_auc")}]}


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
    # The public site never records who looked: a visitor's address is personal data.
    store.audit("Duty analyst", "view", cid, "" if settings.public or not request.client else request.client.host)
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
        "link": {"url": case["url_redacted"] if settings.public else raw, "url_redacted": case["url_redacted"],
                 "domain": case["domain"]},
        "risk": case["risk"], "threshold": case["threshold"], "ensemble_votes": case["votes"],
        "imitates": case["imitates"], "official_domains": case["official_domains"], "reasons": case["reasons"],
        "evidence": case["evidence"], "capture": case["capture"], "channel": case["channel_detail"],
        "decisions": case["decisions"],
        "handling": ("Public demo copy: query values in the link are replaced by hashes." if settings.public else
                     "Contains a raw link that may hold personal data in its query string. Share only with the authority named above."),
    }
    store.audit("Duty analyst", "export", cid, "evidence package")
    return JSONResponse(package, headers={"Content-Disposition": f'attachment; filename="{cid}_evidence.json"'})


_pdf_cache: dict[tuple, tuple[float, bytes]] = {}


def _report_response(key: tuple, make_page, name: str, fmt: str):
    """A PDF when Chromium is available (cached for a minute), otherwise the page with a print prompt."""
    if fmt == "html":
        return HTMLResponse(make_page())
    hit = _pdf_cache.get(key)
    if hit and time.monotonic() - hit[0] < 60:
        pdf = hit[1]
    else:
        pdf = report.to_pdf(make_page())
        if pdf:
            _pdf_cache[key] = (time.monotonic(), pdf)
    if pdf:
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    return HTMLResponse(make_page().replace("</body>", report.PRINT_HINT + "</body>"))


@app.get("/api/cases/{cid}/report")
def case_report(cid: str, lang: str = "en", format: str = "pdf"):
    """Evidence report for one case, in English or Arabic, as PDF (format=pdf) or a web page (format=html)."""
    lang = "ar" if lang == "ar" else "en"
    if not build_case(store, cid):
        raise HTTPException(404, "case not found")
    store.audit("Duty analyst", "report", cid, lang)
    return _report_response(("case", cid, lang), lambda: report.case_html(store, cid, lang), f"Mirsad_{cid}_{lang}", format)


@app.get("/api/report")
def summary_report(lang: str = "en", format: str = "pdf"):
    """Summary report: totals, model results, method, and every flagged case with all its evidence."""
    lang = "ar" if lang == "ar" else "en"
    store.audit("Duty analyst", "report", "all cases", lang)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return _report_response(("all", lang), lambda: report.summary_html(store, lang), f"Mirsad_report_{stamp}_{lang}", format)


@app.post("/api/check")
def check(c: Check):
    r = score(Signals(url=c.url, channel="report"))
    out = {"url": redact(c.url), "risk": r.risk, "threshold": r.threshold, "votes": r.votes, "reasons": r.reasons,
           "imitates": r.imitates, "flagged": r.risk >= r.threshold, "scoring_ms": r.scoring_ms}
    if c.save and not _within_budget("saved_checks", SAVED_CHECKS_PER_HOUR):
        raise HTTPException(429, "This public demo saves at most 30 checked links an hour; try again later, or check without saving.")
    if c.save:
        cid, _ = pipeline.process(store, pipeline.Found(c.url, "report", "Reported link"), use_sandbox=sandbox.available())
        out["case_id"] = cid
    store.audit("Duty analyst", "check", redact(c.url), json.dumps({"risk": r.risk}))
    return out


@app.post("/api/check/batch")
def check_batch(c: CheckBatch):
    """Score up to 10,000 links at once (a test set or a bulk list); nothing is stored but an audit entry."""
    urls = [u.strip()[:2048] for u in c.urls if u and u.strip()]
    if not _batch_lock.acquire(blocking=False):  # one batch at a time keeps the server responsive
        raise HTTPException(429, "Another batch is being scored; try again in a minute.")
    try:
        results = score_batch(urls)
    finally:
        _batch_lock.release()
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
    limit, window = RUN_BUDGET[channel]
    if not _within_budget(f"run:{channel}", limit, window):
        raise HTTPException(429, f"This public demo starts at most {limit} {channel} runs "
                                 f"{'a day' if window == DAY else 'an hour'}, so the shared API quotas last; try again later.")
    _launch(channel)
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
    if not request.url.path.startswith(("/api/", "/captures/")):
        resp.headers["Cache-Control"] = "no-cache"  # browsers revalidate the page and scripts after an update
    if settings.public:  # the Hugging Face Space page shows the site in a frame
        resp.headers["Content-Security-Policy"] = "frame-ancestors 'self' https://huggingface.co"
    else:
        resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
