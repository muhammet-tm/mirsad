"""Discover, enrich, score, and store. One run per channel; the API and the scheduler call `run`.

Expensive steps (domain age lookups, reputation checks, sandbox capture, summaries) run only for links
the first-stage model or a rule has already marked suspicious, so quotas and rate limits hold.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from .collectors import sources
from .collectors.sources import Found
from .config import PROCESSED_DIR
from .enrich import passive
from .features.url import hosting_platform, registered_domain
from .llm.summary import summarize
from .sandbox import client as sandbox
from .scoring.engine import Signals, score, threshold
from .store import Store

log = logging.getLogger("mirsad.pipeline")
NEAR = 0.15  # links within this distance of the threshold get the second stage too


def _fmt_day(iso: str | None) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d %b %Y").lstrip("0")
    except Exception:
        return iso or ""


def process(store: Store, f: Found, use_sandbox: bool, summaries: bool = True) -> tuple[str, float]:
    cid, _ = store.upsert_candidate(f.url, f.channel, channel_detail=f.channel_detail, query=f.query,
                                    rank=f.rank, is_ad=f.is_ad, listing=f.listing, first_seen=f.first_seen)
    sig = Signals(url=f.url, channel=f.channel, query=f.query, rank=f.rank, is_ad=f.is_ad,
                  listing=f.listing, reputation=dict(f.reputation))
    res = score(sig)
    thr = threshold()
    if f.channel == "search":
        store.add_evidence(cid, "search_ad" if f.is_ad else "search_result",
                           f'Search {"ad" if f.is_ad else "result"} position {f.rank} for "{f.query}"', "Search monitor")
    if f.listing:
        if f.listing.get("brand_off_domain"):
            store.add_evidence(cid, "listing", f.listing["brand_off_domain"], "Maps check")
        if f.listing.get("website_unrelated"):
            store.add_evidence(cid, "listing", "Listing website is unrelated to the business name", "Maps check")
        if f.listing.get("phone_shared_with"):
            store.add_evidence(cid, "listing", f"Same phone number on {f.listing['phone_shared_with']} listings", "Maps check")

    if res.risk >= thr - NEAR or res.rules:
        domain = registered_domain(f.url)
        platform = hosting_platform(f.url)
        created, cert = None, None
        if platform:
            # The platform's own registration date and wildcard certificate say nothing about this site.
            store.add_evidence(cid, "domain", f"Hosted on {platform}, a shared site platform; domain age does not apply",
                               "Public Suffix List")
        else:
            created = passive.rdap_created(domain)
        if created:
            store.add_evidence(cid, "domain", f"Domain registered {_fmt_day(created)}", "RDAP", observed_at=created)
        if not platform and (not created or f.channel == "certificates"):
            cert = passive.first_certificate(domain)
            if cert:
                store.add_evidence(cid, "certificate", f"Certificate issued {_fmt_day(cert['not_before'])}",
                                   passive.issuer_short(cert["issuer"]), cert, observed_at=cert["not_before"] + "Z")
        first = created or (cert["not_before"] + "Z" if cert else None) or f.first_seen
        store.set_first_seen(cid, first)
        sig.domain_age_days = passive.age_days(first)
        hit = passive.urlhaus_lookup(f.url)
        if hit:
            sig.reputation["urlhaus"] = hit
            store.add_evidence(cid, "reputation", f"Listed by URLhaus ({hit.get('threat') or 'malicious'})", "abuse.ch")
        res = score(sig)

        if use_sandbox and res.risk >= thr - NEAR and not f.url.startswith("tel:"):
            cap = sandbox.capture(cid, f.url)
            if cap and not cap.get("error"):
                sig.capture = cap
                for form in cap.get("forms", []):
                    if form.get("posts_to") and form["posts_to"] != domain:
                        kind = "Card form" if form.get("card_like") else "Form"
                        store.add_evidence(cid, "form_target", f"{kind} posts to {form['posts_to']} (another domain)", "Sandbox capture")
                shot = cap.pop("_shot_b64", None)
                logo = sandbox.phishpedia(f.url, shot) if shot else None
                if logo and logo.get("brand"):
                    sig.logo = logo
                    ok = "matches" if logo.get("domain_matches_brand") else "is not on that brand's domains"
                    store.add_evidence(cid, "logo_match", f"Logo match: {logo['brand']}, {logo.get('confidence', 0):.2f}, domain {ok}", "Phishpedia")
                store.save_capture(cid, cap.get("screenshot"), cap.get("title", ""), cap.get("final_url", f.url),
                                   cap.get("forms", []), cap.get("text", ""), logo)
                res = score(sig)

    store.save_score(cid, res.risk, res.model_mean, res.votes, res.reasons, res.rules, res.threshold, res.scoring_ms)
    with store.conn() as c:
        c.execute("UPDATE candidates SET imitates=? WHERE id=?", (res.imitates, cid))
    if summaries and res.risk >= thr:
        from .api.cases import build_case  # local import: api depends on store, not the reverse
        case = build_case(store, cid)
        s = summarize(case)
        store.save_summary(cid, s["model"], s["en"], s["ar"])
    return cid, res.risk


def run(channel: str, store: Store | None = None, use_sandbox: bool | None = None, **kw) -> dict:
    store = store or Store()
    use_sandbox = sandbox.available() if use_sandbox is None else use_sandbox
    run_id = store.start_run(channel)
    extra: dict = {}
    try:
        if channel == "search":
            found, stats = sources.search(max_queries=kw.get("max_queries"))
            detail = f"{stats.get('serpapi', 0) + stats.get('serper', 0)} queries"
        elif channel == "maps":
            found, stats = sources.maps()
            detail = f"{stats.get('listings', 0)} listings"
        elif channel == "certificates":
            found, stats = sources.certificates_crtsh(tokens=kw.get("tokens", sources.CT_TOKENS))
            live, live_stats = sources.certificates_stream(seconds=kw.get("stream_seconds", 45))
            found += live
            stats["stream"] = live_stats
            if live_stats.get("certificates"):
                detail = (f"{live_stats.get('per_minute', 0):,} certificates a minute, "
                          f"{live_stats.get('domains_checked', 0):,} names checked for lookalikes")
                if stats.get("note"):
                    detail += f"; {stats['note']}"
            elif stats["errors"] == stats["queries"]:
                detail = (f"crt.sh unavailable ({stats.get('last_status')}); stream "
                          f"{'unreachable' if live_stats.get('error') else 'idle'}")
                stats["state"] = "error"
            else:
                detail = f"{stats['certificates']} recent brand certificates"
        elif channel == "feeds":
            found, stats, all_urls = sources.feeds()
            detail = ", ".join(f"{k} {v}" for k, v in stats.items())
            _save_live_eval(all_urls)
        else:
            raise ValueError(channel)
        # Feeds screen every URL they receive (most are not UAE-related and are not stored).
        store.count_screened(channel, len(all_urls) if channel == "feeds" else len(found))
        flagged = 0
        for f in found:
            try:
                _, risk = process(store, f, use_sandbox)
                flagged += risk >= threshold()
            except Exception as exc:
                log.warning("process failed for %s: %s", f.url[:60], exc)
        store.finish_run(run_id, len(found), int(flagged), stats.get("state", "ok"), detail)
        store.audit("system", f"run:{channel}", str(run_id), json.dumps({"items": len(found), "flagged": int(flagged), **{k: v for k, v in stats.items() if not isinstance(v, dict)}}))
        return {"run_id": run_id, "channel": channel, "items": len(found), "flagged": int(flagged), "stats": stats}
    except Exception as exc:
        store.finish_run(run_id, 0, 0, "error", str(exc)[:200])
        raise


def _save_live_eval(urls: list[str]) -> None:
    """Keep feed URLs with a timestamp: the live test set for E3 is built from these."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / "live_feed_urls.jsonl"
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as fh:
        for u in urls:
            fh.write(json.dumps({"url": u, "label": 1, "seen": stamp}) + "\n")
