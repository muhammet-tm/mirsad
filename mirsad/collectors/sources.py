"""Discovery channels: search results and ads, map listings, new certificates, and threat feeds.

Each collector returns `Found` items; the pipeline scores and stores them. Collection is passive and
inside each provider's terms: official APIs only (no scraping of search or map pages), rate limits
respected, and for Google Places only place IDs, coordinates (cached at most 30 days), and our
derived flags are stored, never business names or addresses.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..config import http_client, settings
from ..features.brands import BRANDS, ct_candidate, is_official, lookalike, mentioned_brand, normalize
from ..features.url import registered_domain, strip_query

# Service-intent queries that UAE residents type and scammers target (Abu Dhabi Police warnings of
# 17 April, 7 June, and 13 June 2026 point at search results and ads for exactly these services).
SEARCH_QUERIES = [
    ("salik recharge", "en"), ("pay salik fine online", "en"), ("darb toll payment abu dhabi", "en"),
    ("pay traffic fine abu dhabi", "en"), ("abu dhabi police fines payment", "en"),
    ("emirates post track parcel", "en"), ("emirates post customs fee payment", "en"),
    ("tamm services login", "en"), ("icp visa renewal online", "en"), ("emirates id renewal online", "en"),
    ("uae pass login", "en"), ("etisalat bill payment", "en"), ("du recharge online", "en"),
    ("adcb customer service number", "en"), ("fab bank customer care number", "en"),
    ("emirates nbd customer care number", "en"), ("consumer protection complaint uae", "en"),
    ("aramex track shipment uae", "en"),
    ("شحن سالك", "ar"), ("سداد مخالفات المرور أبوظبي", "ar"), ("تتبع شحنة بريد الإمارات", "ar"),
    ("تجديد الهوية الإماراتية", "ar"), ("دفع فاتورة اتصالات", "ar"),
]

MAPS_QUERIES = [
    "car rental Abu Dhabi", "Emirates Post office Abu Dhabi", "bank branch Abu Dhabi", "money exchange Abu Dhabi",
    "chalet rental Abu Dhabi", "typing center visa services Abu Dhabi", "Etisalat store Abu Dhabi",
    "du store Abu Dhabi", "courier service Abu Dhabi", "locksmith Abu Dhabi", "AC repair Abu Dhabi",
]
ABU_DHABI = {"latitude": 24.4539, "longitude": 54.3773}
PLATFORM_DOMAINS = {"facebook.com", "instagram.com", "wa.me", "whatsapp.com", "linktr.ee", "google.com",
                    "business.site", "tiktok.com", "x.com", "twitter.com", "linkedin.com", "youtube.com"}


@dataclass
class Found:
    url: str
    channel: str                      # search, maps, certificates, feeds
    channel_detail: str = ""
    query: str = ""
    rank: int | None = None
    is_ad: bool = False
    listing: dict | None = None
    first_seen: str | None = None
    reputation: dict = field(default_factory=dict)


# ---------------------------------------------------------------- search
def search(queries=SEARCH_QUERIES, max_queries: int | None = None) -> tuple[list[Found], dict]:
    """Organic results and paid ads for each query, from SerpApi (Serper as fallback)."""
    found: list[Found] = []
    used = {"serpapi": 0, "serper": 0, "errors": 0}
    for q, lang in queries[:max_queries] if max_queries else queries:
        items = _serpapi(q, lang) if settings.has("SERPAPI_API_KEY") else None
        if items is None and settings.has("SERPER_API_KEY"):
            items = _serper(q, lang)
            used["serper"] += 1 if items is not None else 0
        elif items is not None:
            used["serpapi"] += 1
        if items is None:
            used["errors"] += 1
            continue
        found.extend(items)
    return found, used


def _real_link(res: dict) -> str | None:
    """Destination of a result. Some links come back as encrypted google.ae/goto redirects; then the
    destination is rebuilt from the displayed link ("https://www.salik.ae › shared › sign-in")."""
    link = res.get("link") or ""
    host = registered_domain(link) if link else ""
    if link and not host.startswith("google."):
        return link
    shown = res.get("displayed_link") or ""
    if not shown:
        return None
    parts = [p.strip() for p in shown.split("›")]
    parts = [p for p in parts if p and p != "..."]
    # Social posts show text such as "6 interactions" instead of a host; skip anything that is not a host.
    if not parts or not re.match(r"^(?:https?://)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?::\d+)?/?$", parts[0]):
        return None
    base = parts[0] if parts[0].startswith("http") else "https://" + parts[0]
    return base.rstrip("/") + ("/" + "/".join(parts[1:]) if len(parts) > 1 else "/")


def _serpapi(q: str, lang: str) -> list[Found] | None:
    params = {"engine": "google", "q": q, "google_domain": "google.ae", "gl": "ae", "hl": lang,
              "location": "Abu Dhabi,Abu Dhabi,United Arab Emirates", "num": 10,
              "api_key": settings.key("SERPAPI_API_KEY")}
    try:
        with http_client(timeout=60) as c:
            r = c.get("https://serpapi.com/search.json", params=params)
        if r.status_code != 200:
            return None
        j = r.json()
    except Exception:
        return None
    out = []
    for ad in j.get("ads", []) or []:
        link = _real_link(ad) or ad.get("tracking_link")
        if link:
            pos = ad.get("position", 1)
            out.append(Found(link, "search", f'Search ad, position {pos}, "{q}"', q, pos, True))
    for res in (j.get("organic_results") or [])[:10]:
        link = _real_link(res)
        if link:
            pos = res.get("position")
            out.append(Found(link, "search", f'Search result, position {pos}, "{q}"', q, pos, False))
    return out


def _serper(q: str, lang: str) -> list[Found] | None:
    try:
        with http_client(timeout=40) as c:
            r = c.post("https://google.serper.dev/search", headers={"X-API-KEY": settings.key("SERPER_API_KEY")},
                       json={"q": q, "gl": "ae", "hl": lang, "num": 10, "location": "Abu Dhabi, United Arab Emirates"})
        if r.status_code != 200:
            return None
        j = r.json()
    except Exception:
        return None
    out = []
    for ad in j.get("ads", []) or []:
        if ad.get("link"):
            pos = ad.get("position", 1)
            out.append(Found(ad["link"], "search", f'Search ad, position {pos}, "{q}"', q, pos, True))
    for res in j.get("organic", [])[:10]:
        if res.get("link"):
            pos = res.get("position")
            out.append(Found(res["link"], "search", f'Search result, position {pos}, "{q}"', q, pos, False))
    return out


# ---------------------------------------------------------------- maps
def maps(queries=MAPS_QUERIES) -> tuple[list[Found], dict]:
    """Business listings around Abu Dhabi whose website or phone does not fit the business."""
    key = settings.key("PLACES_API_KEY")
    if not key:
        return [], {"error": "PLACES_API_KEY not set"}
    mask = ("places.id,places.displayName,places.websiteUri,places.nationalPhoneNumber,"
            "places.location,places.primaryType,places.businessStatus")
    listings = []
    requests = 0
    with http_client(timeout=40) as c:
        for q in queries:
            body = {"textQuery": q, "maxResultCount": 20, "languageCode": "en",
                    "locationBias": {"circle": {"center": ABU_DHABI, "radius": 40000.0}}}
            r = c.post("https://places.googleapis.com/v1/places:searchText", json=body,
                       headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": mask})
            requests += 1
            if r.status_code != 200:
                continue
            for p in r.json().get("places", []):
                p["_query"] = q
                listings.append(p)
    # Phone numbers shared across listings that point to different websites (branches of one business
    # share a number and a website legitimately). Only a hash of the number and the count are kept.
    by_phone: dict[str, set] = {}
    for p in listings:
        phone = (p.get("nationalPhoneNumber") or "").replace(" ", "")
        if phone:
            site = p.get("websiteUri")
            key = registered_domain(site) if site else "name:" + normalize(p.get("displayName", {}).get("text", "")).split(" ")[0]
            by_phone.setdefault(phone, set()).add(key)
    found: list[Found] = []
    seen = set()
    for p in listings:
        pid = p.get("id")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        name = p.get("displayName", {}).get("text", "")
        site = p.get("websiteUri")
        phone = (p.get("nationalPhoneNumber") or "").replace(" ", "")
        shared = len(by_phone.get(phone, ())) if phone else 0
        loc = p.get("location") or {}
        listing = {"place_id": pid, "category": (p.get("primaryType") or p["_query"]).replace("_", " "),
                   "website": registered_domain(site) if site else None, "lat": loc.get("latitude"),
                   "lng": loc.get("longitude"), "phone_shared_with": shared if shared >= 2 else 0,
                   "phone_group": hashlib.sha256(phone.encode()).hexdigest()[:8] if shared >= 2 else None,
                   "cached_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        brand = mentioned_brand(name)
        if site:
            dom = registered_domain(site)
            if brand and not is_official(dom):
                listing["brand_off_domain"] = f"Listing named like {brand.name} links to {dom}, not an official domain"
            listing["website_unrelated"] = dom not in PLATFORM_DOMAINS and not _related(name, dom)
            listing["mismatch"] = bool(listing.get("brand_off_domain") or listing["website_unrelated"] or shared >= 3)
            found.append(Found(site, "maps", f"Maps listing, {listing['category']}", p["_query"], None, False, listing))
        elif shared >= 3:
            listing["mismatch"] = True
            found.append(Found(f"tel:{listing['phone_group']}", "maps", f"Maps listing without website, {listing['category']}",
                               p["_query"], None, False, listing))
    return found, {"requests": requests, "listings": len(seen)}


def _related(name: str, domain: str) -> bool:
    label = normalize(domain.split(".")[0]).replace("-", "")
    words = [w for w in normalize(name).replace("-", " ").split() if len(w) >= 4]
    return any(w[:5] in label for w in words) or not words


# ---------------------------------------------------------------- certificates
CT_TOKENS = ["salik", "emiratespost", "adpolice", "uaepass", "tamm", "emiratesnbd", "etisalat", "mashreq",
             "rakbank", "aramex", "dewa", "icp", "darb"]


def certificates_crtsh(tokens=CT_TOKENS, days: int = 30) -> tuple[list[Found], dict]:
    """Recently logged certificates whose names contain a protected brand, on non-official domains."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    found: list[Found] = []
    stats = {"queries": 0, "certificates": 0, "errors": 0}
    seen = set()
    with http_client(timeout=60) as c:
        for i, t in enumerate(tokens):
            # crt.sh is often down for hours (502 on 22 and 23 November); each failed query costs about
            # 100 s of retries, so stop after two failures in a row and report the rest as skipped.
            if stats["errors"] >= 2 and stats["errors"] == stats["queries"]:
                stats["skipped"] = len(tokens) - i
                stats["note"] = "crt.sh unavailable; remaining queries skipped"
                break
            if i:
                time.sleep(12.5)
            stats["queries"] += 1
            certs = None
            for attempt in range(3):  # crt.sh often answers 502 under load; back off and retry
                try:
                    r = c.get("https://crt.sh/", params={"q": f"%{t}%", "output": "json", "exclude": "expired"})
                    if r.status_code == 200:
                        certs = r.json() if r.text.strip() else []
                        break
                    stats["last_status"] = r.status_code
                except Exception as exc:
                    stats["last_status"] = type(exc).__name__
                time.sleep(15 * (attempt + 1))
            if certs is None:
                stats["errors"] += 1
                continue
            for cert in certs:
                nb = cert.get("not_before", "")
                try:
                    issued = datetime.fromisoformat(nb).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                if issued < since:
                    continue
                stats["certificates"] += 1
                for name in cert.get("name_value", "").split("\n"):
                    name = name.strip().lstrip("*.").lower()
                    dom = registered_domain(name)
                    if not name or dom in seen or is_official(dom, name):
                        continue
                    seen.add(dom)
                    found.append(Found(f"https://{name}/", "certificates", "New certificate", t, None, False, None,
                                       first_seen=issued.isoformat(timespec="seconds")))
    return found, stats


def certificates_stream(seconds: int = 60) -> tuple[list[Found], dict]:
    """Listen to the live Certificate Transparency stream and keep lookalikes of protected brands."""
    import websockets

    found: list[Found] = []
    stats = {"certificates": 0, "domains_checked": 0, "seconds": seconds}

    import ssl

    import truststore

    from . import certstream_local

    url = settings.env.get("MIRSAD_CERTSTREAM_URL", "wss://certstream.calidog.io/")
    local = certstream_local.is_local(url)
    # A local server (started per run, see certstream_local) serves the light domains-only feed.
    feed = url.rstrip("/") + "/domains-only" if local else url
    stats["source"] = feed
    seen: set[str] = set()  # the same name arrives once per log and once as a precertificate

    def check(names) -> None:
        for name in names:
            name = name.lstrip("*.").lower()
            if not name or name in seen:
                continue
            seen.add(name)
            stats["domains_checked"] += 1
            dom = registered_domain(name)
            if is_official(dom, name):
                continue
            if ct_candidate(name) is not None:
                found.append(Found(f"https://{name}/", "certificates", "New certificate (live stream)",
                                   first_seen=datetime.now(timezone.utc).isoformat(timespec="seconds")))

    async def run():
        deadline = time.monotonic() + seconds
        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT) if feed.startswith("wss") else None
        try:
            async with websockets.connect(feed, ssl=ctx, max_size=2 ** 22, open_timeout=15) as ws:
                while time.monotonic() < deadline:
                    try:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.monotonic())))
                    except asyncio.TimeoutError:
                        break
                    except Exception as exc:
                        stats["error"] = f"{type(exc).__name__}: {str(exc)[:100]}"
                        break
                    kind = msg.get("message_type")
                    if kind == "dns_entries":
                        stats["certificates"] += 1
                        check(msg.get("data") or [])
                    elif kind == "certificate_update":
                        stats["certificates"] += 1
                        check(msg["data"]["leaf_cert"].get("all_domains", []))
        except Exception as exc:  # stream down: report, do not crash the run
            stats["error"] = str(exc)[:120]

    try:
        with certstream_local.running(url) as note:
            stats["server"] = note
            asyncio.run(run())
    except Exception as exc:  # binary missing, port taken, or server failed to start
        stats["error"] = str(exc)[:160]
    stats["per_minute"] = int(stats["certificates"] * 60 / max(seconds, 1))
    return found, stats


# ---------------------------------------------------------------- feeds
def feeds() -> tuple[list[Found], dict, list[str]]:
    """Public phishing and malware feeds. Returns UAE-relevant items for the queue and every URL for evaluation."""
    all_urls: list[str] = []
    stats = {}
    with http_client(timeout=60, follow_redirects=True) as c:
        try:
            r = c.get("https://raw.githubusercontent.com/openphish/public_feed/refs/heads/main/feed.txt")
            op = [u.strip() for u in r.text.splitlines() if u.strip().startswith("http")]
        except Exception:
            op = []
        stats["openphish"] = len(op)
        uh = []
        if settings.has("ABUSECH_AUTH_KEY"):
            try:
                r = c.get("https://urlhaus-api.abuse.ch/v1/urls/recent/limit/500/",
                          headers={"Auth-Key": settings.key("ABUSECH_AUTH_KEY")})
                uh = [x["url"] for x in r.json().get("urls", [])]
            except Exception:
                pass
        stats["urlhaus"] = len(uh)
        try:
            r = c.get("https://api.phishstats.info/api/phishing", params={"_sort": "-id", "_size": 100})
            ps = [x["url"] for x in r.json() if x.get("url")]
        except Exception:
            ps = []
        stats["phishstats"] = len(ps)
    found = []
    for source, urls in (("OpenPhish", op), ("URLhaus", uh), ("PhishStats", ps)):
        for u in urls:
            clean = strip_query(u)  # PhishStats and others carry victim data in query strings
            all_urls.append(clean)
            dom = registered_domain(clean)
            if mentioned_brand(clean) or lookalike(dom)[0] or dom.endswith(".ae"):
                rep = {"openphish": True} if source == "OpenPhish" else {"urlhaus": {"listed": True}} if source == "URLhaus" else {"phishstats": True}
                found.append(Found(clean, "feeds", f"Feed ({source})", reputation=rep))
    return found, stats, all_urls
