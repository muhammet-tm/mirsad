"""Passive enrichment: domain age, certificate history, and reputation lists.

Every lookup reads public records only (RDAP, Certificate Transparency through crt.sh, URLhaus,
VirusTotal). Nothing here contacts the suspect site itself; page capture happens in the sandbox VM.
Results are cached in memory for the life of the process to respect the providers' rate limits.
"""

from __future__ import annotations

import base64
import functools
import time
from datetime import datetime, timezone

from ..config import http_client, settings

_RDAP_BOOTSTRAP: dict[str, str] | None = None
# Top-level domains reserved for testing and examples (RFC 2606, RFC 6761): no registration or
# certificate can exist, so lookups are skipped. The bundled demo links use them on purpose.
RESERVED_TLDS = {"example", "test", "invalid", "localhost"}


def _reserved(domain_or_url: str) -> bool:
    host = domain_or_url.split("://")[-1].split("/")[0].split(":")[0].rstrip(".").lower()
    return host.rsplit(".", 1)[-1] in RESERVED_TLDS


def _rdap_base(tld: str) -> str | None:
    global _RDAP_BOOTSTRAP
    if _RDAP_BOOTSTRAP is None:
        _RDAP_BOOTSTRAP = {}
        try:
            with http_client() as c:
                data = c.get("https://data.iana.org/rdap/dns.json").json()
            for tlds, urls in data.get("services", []):
                for t in tlds:
                    _RDAP_BOOTSTRAP[t.lower()] = urls[0]
        except Exception:
            pass
    return _RDAP_BOOTSTRAP.get(tld.lower())


@functools.lru_cache(maxsize=4096)
def rdap_created(domain: str) -> str | None:
    """Registration date from RDAP (gTLDs). The .ae registry publishes no RDAP and hides dates."""
    if _reserved(domain):
        return None
    tld = domain.rsplit(".", 1)[-1]
    base = _rdap_base(tld)
    if not base:
        return None
    try:
        with http_client(follow_redirects=True, timeout=15) as c:
            r = c.get(f"{base.rstrip('/')}/domain/{domain}")
        if r.status_code != 200:
            return None
        for ev in r.json().get("events", []):
            if ev.get("eventAction") == "registration":
                return ev.get("eventDate")
    except Exception:
        return None
    return None


_last_crtsh = 0.0


@functools.lru_cache(maxsize=4096)
def first_certificate(domain: str) -> dict | None:
    """Earliest certificate logged for the domain (crt.sh), the age signal that works for .ae too."""
    global _last_crtsh
    if _reserved(domain):
        return None
    wait = 12.5 - (time.monotonic() - _last_crtsh)  # crt.sh asks for about 5 requests a minute
    if wait > 0:
        time.sleep(wait)
    _last_crtsh = time.monotonic()
    try:
        with http_client(timeout=40) as c:
            r = c.get("https://crt.sh/", params={"q": domain, "output": "json", "exclude": "expired"})
        if r.status_code != 200 or not r.text.strip():
            return None
        certs = r.json()
    except Exception:
        return None
    if not certs:
        return None
    first = min(certs, key=lambda x: x.get("not_before", "9999"))
    return {"not_before": first.get("not_before"), "issuer": first.get("issuer_name", ""),
            "count": len(certs), "names": sorted({n for x in certs[:50] for n in x.get("name_value", "").split("\n")})[:10]}


def issuer_short(issuer: str) -> str:
    for part in issuer.split(","):
        part = part.strip()
        if part.startswith("O="):
            return part[2:].strip('"')
    return issuer[:40]


def age_days(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except ValueError:
        return None


@functools.lru_cache(maxsize=4096)
def urlhaus_lookup(url: str) -> dict | None:
    key = settings.key("ABUSECH_AUTH_KEY")
    if not key or _reserved(url):
        return None
    try:
        with http_client(timeout=20) as c:
            r = c.post("https://urlhaus-api.abuse.ch/v1/url/", data={"url": url}, headers={"Auth-Key": key})
        j = r.json()
        if j.get("query_status") == "ok":
            return {"threat": j.get("threat"), "status": j.get("url_status"), "tags": j.get("tags")}
    except Exception:
        return None
    return None


_last_vt = 0.0


@functools.lru_cache(maxsize=2048)
def virustotal_url(url: str) -> dict | None:
    """VirusTotal community verdicts (public API: 4 requests a minute, non-commercial use)."""
    global _last_vt
    key = settings.key("VIRUSTOTAL_API_KEY")
    if not key:
        return None
    wait = 15.5 - (time.monotonic() - _last_vt)
    if wait > 0:
        time.sleep(wait)
    _last_vt = time.monotonic()
    uid = base64.urlsafe_b64encode(url.encode()).decode().strip("=")
    try:
        with http_client(timeout=20) as c:
            r = c.get(f"https://www.virustotal.com/api/v3/urls/{uid}", headers={"x-apikey": key})
        if r.status_code != 200:
            return None
        stats = r.json()["data"]["attributes"]["last_analysis_stats"]
        return {"malicious": stats.get("malicious", 0), "suspicious": stats.get("suspicious", 0),
                "harmless": stats.get("harmless", 0)}
    except Exception:
        return None
