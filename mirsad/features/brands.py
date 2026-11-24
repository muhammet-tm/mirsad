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


_HOSTNAME = re.compile(r"[a-z0-9_-]+(?:\.[a-z0-9_-]+)*")


def valid_hostname(name: str) -> bool:
    """Letters, digits, hyphens, underscores, and dots only, after converting an international name."""
    try:
        ascii_name = name.encode("idna").decode("ascii")
    except (UnicodeError, ValueError):
        return False
    return bool(_HOSTNAME.fullmatch(ascii_name))


def is_official(registered_domain: str, host: str = "") -> Brand | None:
    """The brand that owns this domain, if any (host may be a subdomain of an official domain).

    Any name under .gov.ae counts as a government entity: the .ae registry restricts gov.ae
    registrations to government bodies (the adpolice.gov.ae WHOIS shows "Government Approved").
    A name with characters no real hostname has is never official: the cap would otherwise trust
    a string that a browser reads as a different host.
    """
    host = (host or registered_domain).lower().rstrip(".")
    registered_domain = (registered_domain or "").lower().rstrip(".")
    if not valid_hostname(host) or (registered_domain and not valid_hostname(registered_domain)):
        return None
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

    The stream carries thousands of names a second, so it needs higher precision than a search result
    for a brand query; the first live run (23 November 2026) showed which rules fail at that volume.
    Words of every language are full of short brand tokens and their one-letter neighbors: 4-sadik.ru
    (salik), salikhov (salik), moore (mohre), ecrire (ecrime). So:

    - a token of 7 letters or more (emiratespost, adpolice, uaepass) counts on its own, even inside a
      longer word, and so does a near-miss spelling of one (emiratesp0st after homoglyph folding);
    - a token of 5 or 6 letters (salik, mohre) counts as a whole word; inside a longer word, or as a
      near miss, it needs context;
    - a token of 4 letters or fewer (itc, rta, du, tamm) or an ordinary word (added) always needs context.

    Context is UAE context (.ae, "dubai", "uae") or a scam word ("pay", "fines", "track"). So
    salik-pay.com, tamm-pay.xyz, and dubai-rta-fines.com pass; 4-sadik.ru, old.itc.edu, and
    nkolay-salikhov.workers.dev do not.
    """
    host = host.lower().rstrip(".")
    if host.startswith("xn--") or ".xn--" in host:
        return None  # internationalized names are left to the lookalike check of a later stage
    toks = _tokens(host)
    joined = "".join(toks)
    context = host.endswith(".ae") or any(w in joined for w in _UAE_WORDS) or any(t in _SCAM_WORDS for t in toks)
    for b in BRANDS:
        for t in b.tokens:
            whole, inside = t in toks, len(t) > 4 and t in joined
            if not (whole or inside):
                continue
            if len(t) <= 4 or t in GENERIC_TOKENS:
                if whole and context:
                    return b
            elif len(t) >= 7 or whole or context:
                return b
    # Near misses, compared per word of 5 letters or more (after homoglyph folding).
    for b in BRANDS:
        for t in b.tokens:
            if len(t) < 5 or t in GENERIC_TOKENS or (len(t) < 7 and not context):
                continue
            allowed = 1 if len(t) <= 8 else 2
            for p in toks:
                if len(p) >= 5 and abs(len(p) - len(t)) <= allowed and 0 < Levenshtein.distance(p, t) <= allowed:
                    return b
    return None
