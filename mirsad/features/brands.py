"""UAE brands that scammers imitate, with their official domains and lookalike checks.

Source: research note 03 (22 November 2026). `verified` is True only where a source read that day
showed the domain as the brand's own; every other row exists in DNS but its ownership still needs
checking before an operational deployment. The list drives two things: the brand-mismatch rule
(a page or link that names a brand on a domain the brand does not own) and the lookalike detector
for new certificates.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein


@dataclass(frozen=True)
class Brand:
    name: str
    sector: str
    domains: tuple[str, ...]
    tokens: tuple[str, ...]
    verified: bool = False
    arabic: tuple[str, ...] = ()


BRANDS: tuple[Brand, ...] = (
    Brand("Abu Dhabi Police", "Police", ("adpolice.gov.ae",), ("adpolice", "abudhabipolice"), True, ("شرطة أبوظبي",)),
    Brand("UAE government portal", "Federal government", ("u.ae",), ("uaegov",), True),
    Brand("Dubai Police", "Police", ("dubaipolice.gov.ae", "ecrime.ae"), ("dubaipolice", "ecrime")),
    Brand("Ministry of Interior", "Federal government", ("moi.gov.ae",), ("moi", "moiuae")),
    Brand("ICP", "Federal government", ("icp.gov.ae",), ("icp", "icpuae", "emiratesid"), arabic=("الهوية والجنسية",)),
    Brand("UAE Pass", "Digital identity", ("uaepass.ae",), ("uaepass",)),
    Brand("TAMM", "Abu Dhabi government", ("tamm.abudhabi",), ("tamm",), arabic=("تم",)),
    Brand("Darb (ITC)", "Abu Dhabi tolls", ("itc.gov.ae", "admobility.gov.ae", "qmobility.ae"), ("darb", "itc"), arabic=("درب",)),
    Brand("Salik", "Dubai tolls", ("salik.ae",), ("salik",), arabic=("سالك",)),
    Brand("RTA", "Dubai transport and fines", ("rta.ae",), ("rta", "rtadubai")),
    Brand("ADDED consumer protection", "Abu Dhabi economy", ("added.gov.ae",), ("added",)),
    Brand("Ministry of Economy", "Consumer protection", ("moec.gov.ae",), ("moec",)),
    Brand("Federal Tax Authority", "Federal government", ("tax.gov.ae",), ("fta", "uaetax")),
    Brand("MOHRE", "Work permits", ("mohre.gov.ae",), ("mohre",)),
    Brand("Central Bank of the UAE", "Regulator", ("centralbank.ae",), ("centralbank", "cbuae")),
    Brand("First Abu Dhabi Bank", "Bank", ("bankfab.com",), ("bankfab", "fab")),
    Brand("ADCB", "Bank", ("adcb.com", "adcb.com.eg"), ("adcb",)),
    Brand("ADIB", "Bank", ("adib.ae", "adib.com"), ("adib",)),
    Brand("Emirates NBD", "Bank", ("emiratesnbd.com",), ("emiratesnbd", "enbd")),
    Brand("Dubai Islamic Bank", "Bank", ("dib.ae",), ("dib",)),
    Brand("Mashreq", "Bank", ("mashreq.com", "mashreqbank.com"), ("mashreq",)),
    Brand("RAKBANK", "Bank", ("rakbank.ae",), ("rakbank",)),
    Brand("e& (Etisalat)", "Telecom", ("etisalat.ae", "eand.com", "eand.ae"), ("etisalat", "eand")),
    Brand("du", "Telecom", ("du.ae",), ("du",)),
    Brand("Emirates Post", "Courier", ("emiratespost.ae",), ("emiratespost", "empost"), arabic=("بريد الإمارات",)),
    Brand("Aramex", "Courier", ("aramex.com",), ("aramex",)),
    Brand("ADDC", "Utility", ("addc.ae",), ("addc",)),
    Brand("DEWA", "Utility", ("dewa.gov.ae",), ("dewa",)),
    Brand("SEWA", "Utility", ("sewa.gov.ae",), ("sewa",)),
    Brand("Etihad Airways", "Airline", ("etihad.com",), ("etihad",)),
    Brand("Emirates", "Airline", ("emirates.com",), ("emiratesairline", "flyemirates")),
)

# Characters that scammers swap for look-alikes, mapped to the letter they imitate.
_HOMOGLYPHS = str.maketrans({
    "0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g", "$": "s", "@": "a",
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ӏ": "l", "ѕ": "s",
    "ԁ": "d", "ԛ": "q", "ԝ": "w", "ɡ": "g", "ı": "i",
})
_TOKEN = re.compile(r"[a-z0-9]+")


def normalize(text: str) -> str:
    """Lowercase, fold compatibility characters, and map common homoglyphs to plain letters."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.translate(_HOMOGLYPHS)
    return text.replace("rn", "m").replace("vv", "w")


def official_domains() -> set[str]:
    return {d for b in BRANDS for d in b.domains}


GOVERNMENT = Brand("UAE government entity", "Government", ("gov.ae",), (), False)


def is_official(registered_domain: str, host: str = "") -> Brand | None:
    """The brand that owns this domain, if any (host may be a subdomain of an official domain).

    Any name under .gov.ae counts as a government entity: the .ae registry restricts gov.ae
    registrations to government bodies (the adpolice.gov.ae WHOIS shows "Government Approved").
    """
    host = (host or registered_domain).lower().rstrip(".")
    for b in BRANDS:
        for d in b.domains:
            if host == d or host.endswith("." + d) or registered_domain == d:
                return b
    if host.endswith(".gov.ae") or registered_domain.endswith(".gov.ae"):
        return GOVERNMENT
    return None


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(normalize(text))


def mentioned_brand(text: str) -> Brand | None:
    """A brand named in a URL, host, or page title. Short tokens must match a whole token."""
    toks = _tokens(text)
    joined = "".join(toks)
    for b in BRANDS:
        for t in b.tokens:
            if len(t) <= 4:
                if t in toks:
                    return b
            elif t in joined:
                return b
        for a in b.arabic:
            if a in text:
                return b
    return None


def lookalike(registered_domain: str) -> tuple[Brand | None, int]:
    """Closest protected brand to the domain's main label, and the edit distance after homoglyph folding.

    Distance 0 means the label contains a brand token outright (for example salik-topup-uae),
    1 or 2 means a near miss such as emiratesp0st. Short brand tokens (4 letters or fewer) only
    count on an exact match, to avoid flagging ordinary words.
    """
    label = registered_domain.split(".")[0]
    norm = normalize(label)
    parts = _TOKEN.findall(norm)
    best: tuple[Brand | None, int] = (None, 99)
    for b in BRANDS:
        for t in b.tokens:
            if len(t) <= 4:
                if t in parts:
                    return b, 0
                continue
            if t in norm.replace("-", ""):
                return b, 0
            # Near misses: one edit for brand names up to 8 letters, two for longer ones, and only
            # against words of 5 letters or more (so "uae" or "framer" never match a brand).
            allowed = 1 if len(t) <= 8 else 2
            for p in parts + [norm.replace("-", "")]:
                if len(p) >= 5 and abs(len(p) - len(t)) <= allowed:
                    d = Levenshtein.distance(p, t)
                    if d <= allowed and d < best[1]:
                        best = (b, d)
    return best


# Protected tokens that are also ordinary words; on their own they say nothing about a brand.
GENERIC_TOKENS = {"added"}
# Words that make a short or generic brand token meaningful in a host name.
_UAE_WORDS = ("uae", "dubai", "abudhabi", "emirates", "sharjah", "ajman")
_SCAM_WORDS = {"pay", "payment", "fine", "fines", "toll", "tolls", "recharge", "topup", "refund", "verify",
               "login", "signin", "portal", "account", "track", "tracking", "parcel", "delivery", "visa", "gov"}


def ct_candidate(host: str) -> Brand | None:
    """The brand a newly certified host name appears to target, for the live certificate stream.

    The stream carries about 3,000 names a second, so it needs higher precision than a search result
    for a brand query. A brand token of 5 letters or more (other than an ordinary word such as
    "added"), or a near-miss spelling of one, counts on its own. A short token (itc, rta, du, tamm)
    or an ordinary word counts only together with UAE context (.ae, "dubai", "uae") or a scam word
    ("pay", "fines", "track"): so tamm-pay.xyz and dubai-rta-fines.com pass, while old.itc.edu,
    cap-du-jour.pages.dev, and paddedmoth4.chatgpt.site do not.
    """
    host = host.lower().rstrip(".")
    if host.startswith("xn--") or ".xn--" in host:
        return None  # internationalized names are left to the lookalike check of a later stage
    toks = _tokens(host)
    joined = "".join(toks)
    context = host.endswith(".ae") or any(w in joined for w in _UAE_WORDS) or any(t in _SCAM_WORDS for t in toks)
    for b in BRANDS:
        for t in b.tokens:
            hit = (t in toks) if len(t) <= 4 else (t in joined)
            if not hit:
                continue
            if (len(t) >= 5 and t not in GENERIC_TOKENS) or context:
                return b
    labels = host.split(".")
    for label in labels[:-1]:  # near misses (emiratesp0st, sallik) in any label but the top-level domain
        brand, dist = lookalike(label + ".x")
        if brand is not None and 0 < dist and not any(t in GENERIC_TOKENS for t in brand.tokens):
            return brand
    return None
