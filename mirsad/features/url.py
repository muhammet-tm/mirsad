"""URL parsing and lexical features.

Two views of a URL are used. The raw string is the conventional benchmark representation, which
vectorizes the URL text as given. The canonical form removes what differs between data sources rather than between
benign and fraudulent sites (scheme, "www.", trailing slash, case of the host), so that a model
cannot score well by recognizing which list a URL came from.
"""

from __future__ import annotations

import ipaddress
import math
import re
from collections import Counter
from dataclasses import dataclass
from urllib.parse import urlsplit

import numpy as np
import tldextract

from .brands import is_official, lookalike, mentioned_brand

# Offline extractor: uses the public suffix list bundled with tldextract, no network at runtime.
_EXTRACT = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)

SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly", "cutt.ly",
              "rebrand.ly", "shorturl.at", "rb.gy", "t.ly", "s.id", "tiny.cc"}
LURE_WORDS = ("login", "signin", "verify", "verification", "update", "secure", "account", "bank",
              "pay", "payment", "fine", "fines", "refund", "invoice", "wallet", "otp", "confirm",
              "recharge", "topup", "parcel", "delivery", "customs", "fee", "reward", "gift", "visa")
# TLDs that recur in UAE-targeted lure campaigns (Resecurity, 2023) and in the feeds; a weak signal.
CHEAP_TLDS = {"top", "xyz", "shop", "site", "online", "info", "click", "live", "icu", "buzz", "cyou",
              "vip", "store", "lol", "rest", "cfd", "sbs", "bond", "win", "monster"}
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def ensure_scheme(url: str) -> str:
    url = url.strip()
    return url if _SCHEME.match(url) else "http://" + url


_TAB_NEWLINE = re.compile(r"[\t\n\r]")
_SPECIAL = ("http://", "https://", "ws://", "wss://", "ftp://")


def browser_form(url: str) -> str:
    """The URL as a browser reads it (WHATWG URL Standard), so Mirsad scores the host a victim reaches.

    Browsers drop tabs and newlines anywhere, trim control characters and spaces at both ends, and in
    http(s) URLs treat a backslash before the query as a slash. Python's urlsplit does none of this:
    with a backslash between evil.top and @adpolice.gov.ae, Python reads the host as adpolice.gov.ae
    while a browser goes to evil.top.
    """
    url = _TAB_NEWLINE.sub("", url).strip("".join(chr(c) for c in range(0x21)))
    url = ensure_scheme(url)
    if url.lower().startswith(_SPECIAL):
        cut = min((i for i in (url.find("?"), url.find("#")) if i >= 0), default=len(url))
        url = url[:cut].replace("\\", "/") + url[cut:]
    return url


def disguised_host(url: str) -> str | None:
    """How a link hides the host a browser opens, or None.

    Two tricks put a trusted name in front of the real host: a backslash in the authority (a browser
    reads it as the start of the path) and userinfo before an @ (a browser ignores it). Neither has a
    use in a link a real bank or government site would send.
    """
    raw = _TAB_NEWLINE.sub("", url).strip()
    m = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/?#]*)", raw)
    if not m or not raw.lower().startswith(_SPECIAL):
        return None
    authority = m.group(1)
    if "\\" in authority:
        return "backslash"
    if "@" in authority:
        return "userinfo"
    return None


_FALLBACK = re.compile(r"^(?:(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*)://)?(?P<netloc>[^/?#]*)(?P<path>[^?#]*)(?:\?(?P<query>[^#]*))?")


@dataclass(frozen=True)
class Parts:
    scheme: str
    host: str
    port: int | None
    path: str
    query: str


def split(url: str) -> Parts:
    """Parse a URL without ever raising: real feeds contain broken brackets, ports, and encodings."""
    url = browser_form(url)
    try:
        p = urlsplit(url)
        host = (p.hostname or "").lower().rstrip(".")
        try:
            port = p.port
        except ValueError:
            port = None
        return Parts(p.scheme.lower(), host, port, p.path, p.query)
    except ValueError:
        m = _FALLBACK.match(url)
        netloc = (m.group("netloc") or "").rsplit("@", 1)[-1]
        host = netloc.split(":")[0].strip("[]").lower().rstrip(".")
        return Parts((m.group("scheme") or "http").lower(), host, None, m.group("path") or "", m.group("query") or "")


def canonical(url: str) -> str:
    """Host lowercased without scheme, "www.", default port, or trailing slash; path and query kept."""
    p = split(url)
    host = p.host[4:] if p.host.startswith("www.") else p.host
    port = f":{p.port}" if p.port and p.port not in (80, 443) else ""
    path = p.path.rstrip("/")
    query = f"?{p.query}" if p.query else ""
    return f"{host}{port}{path}{query}"


def strip_query(url: str) -> str:
    """The URL without query string or fragment (query values often carry victim data)."""
    p = split(url)
    port = f":{p.port}" if p.port else ""
    return f"{p.scheme}://{p.host}{port}{p.path}"


def host_of(url: str) -> str:
    return split(url).host


_EXTRACT_PRIVATE = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True)


def hosting_platform(url_or_host: str) -> str | None:
    """The shared site platform a host lives on (framer.app, vercel.app, github.io), or None.

    The Public Suffix List's private section names these platforms. A site on one of them has no
    domain of its own, so the platform's registration date says nothing about the site's age.
    """
    host = host_of(url_or_host) if "/" in url_or_host or ":" in url_or_host else url_or_host.lower()
    ext = _EXTRACT_PRIVATE(host)
    return ext.suffix if getattr(ext, "is_private", False) and ext.domain else None


def registered_domain(url_or_host: str) -> str:
    host = host_of(url_or_host) if "/" in url_or_host or ":" in url_or_host else url_or_host.lower()
    ext = _EXTRACT(host)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    return host


def _entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = Counter(s)
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in counts.values())


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


FEATURE_NAMES = [
    "len_url", "len_host", "len_path", "len_query", "n_dots_host", "n_hyphens_host", "n_digits_host",
    "n_subdomains", "n_slashes", "n_params", "n_at", "n_percent", "digit_ratio", "host_entropy",
    "is_ip", "is_punycode", "has_non_ascii", "has_port", "is_shortener", "cheap_tld", "n_lure_words",
    "brand_mentioned", "brand_off_domain", "lookalike_distance", "phone_in_query",
]


def lexical_features(url: str) -> np.ndarray:
    """Handcrafted features of one URL, computed on the canonical form so the scheme cannot leak."""
    canon = canonical(url)
    parts = split(canon)
    host, path, query = parts.host, parts.path, parts.query
    rd = registered_domain(host) if host else ""
    tld = rd.rsplit(".", 1)[-1] if "." in rd else ""
    sub = host[: -len(rd)].rstrip(".") if rd and host.endswith(rd) else ""
    lowered = canon.lower()
    brand = mentioned_brand(f"{host} {path}")
    owner = is_official(rd, host)
    look_brand, look_dist = lookalike(rd) if rd else (None, 99)
    digits = sum(ch.isdigit() for ch in canon)
    return np.array([
        len(canon), len(host), len(path), len(query), host.count("."), host.count("-"),
        sum(ch.isdigit() for ch in host), sub.count(".") + (1 if sub else 0), path.count("/"),
        query.count("&") + (1 if query else 0), canon.count("@"), canon.count("%"),
        digits / max(len(canon), 1), _entropy(host), float(_is_ip(host)),
        float("xn--" in host), float(any(ord(ch) > 127 for ch in canon)), float(parts.port is not None),
        float(rd in SHORTENERS), float(tld in CHEAP_TLDS),
        float(sum(w in lowered for w in LURE_WORDS)),
        float(brand is not None), float(brand is not None and owner is None),
        float(min(look_dist, 3)) if look_brand else 3.0,
        float(bool(re.search(r"(?:\+?971|00971|800)\D?\d{3,}", query))),
    ], dtype=np.float32)


def lexical_matrix(urls) -> np.ndarray:
    return np.vstack([lexical_features(u) for u in urls])
