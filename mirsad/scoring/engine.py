"""The cascade: DaE2 scores every link; evidence rules raise the risk; the official allowlist caps it.

Stage 1 is the DaE2 ensemble on the URL (milliseconds). Stage 2 adds what a URL string cannot carry:
domain age, certificate history, reputation lists, the captured page (forms, logo match), and the
channel the link was found in. Rules can only raise a score, except the allowlist rule, which caps a
link on a brand's own official domain. Every rule that fires adds one reason in plain words.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from functools import lru_cache

import joblib
import numpy as np

from ..config import MODELS_DIR, settings
from ..features.brands import Brand, is_official, lookalike, mentioned_brand
from ..features.url import canonical, host_of, registered_domain, split


@dataclass
class Signals:
    """Evidence gathered about one link before scoring."""
    url: str
    channel: str = "report"
    query: str = ""
    rank: int | None = None
    is_ad: bool = False
    domain_age_days: int | None = None
    listing: dict | None = None
    reputation: dict = field(default_factory=dict)  # {"urlhaus": {...}, "virustotal": {...}, "openphish": True}
    capture: dict | None = None                       # from the sandbox
    logo: dict | None = None                          # from Phishpedia


@dataclass
class Result:
    risk: float
    model_mean: float
    votes: dict[str, float]
    reasons: list[str]
    rules: list[str]
    imitates: str | None
    threshold: float
    scoring_ms: float


@lru_cache(maxsize=1)
def _model():
    for name in ("dae2_deploy.joblib", "dae2_e1a_paper.joblib"):
        path = MODELS_DIR / name
        if path.exists():
            card = MODELS_DIR / name.replace(".joblib", ".card.json")
            meta = json.loads(card.read_text()) if card.exists() else {}
            from ..models.dae2 import for_live_scoring
            return for_live_scoring(joblib.load(path)), meta, name
    return None, {}, None


def model_info() -> dict:
    _, meta, name = _model()
    return {"file": name, **meta}


def threshold() -> float:
    _, meta, _ = _model()
    return float(meta.get("threshold", settings.threshold))


def _query_brand(query: str) -> Brand | None:
    return mentioned_brand(query) if query else None


def score(sig: Signals) -> Result:
    t0 = time.perf_counter()
    model, _, _ = _model()
    if model is not None:
        votes = {k: float(v[0]) for k, v in model.votes([sig.url]).items()}
        model_mean = float(np.mean(list(votes.values())))
    else:
        votes, model_mean = {}, 0.0
    host = host_of(sig.url)
    domain = registered_domain(host)
    owner = is_official(domain, host)
    named = mentioned_brand(f"{host} {split(sig.url).path}")
    look, dist = lookalike(domain)
    imitates = (named or look or _query_brand(sig.query))
    floors: list[float] = []
    reasons: list[str] = []
    rules: list[str] = []

    def fire(rule: str, floor: float, reason: str) -> None:
        rules.append(rule)
        floors.append(floor)
        if reason not in reasons:
            reasons.append(reason)

    young = sig.domain_age_days is not None and sig.domain_age_days <= 30
    if sig.domain_age_days is not None and sig.domain_age_days <= 90:
        fire("young_domain", 0.0, f"Domain first seen {sig.domain_age_days} day{'s' if sig.domain_age_days != 1 else ''} ago")

    if owner is None and (named or (look and dist <= 2)):
        brand = named or look
        fire("brand_off_domain", 0.86 if young else 0.8,
             f"Name imitates {brand.name} but is not on the official list")

    cap = sig.capture or {}
    forms = cap.get("forms") or []
    if owner is None and any(f.get("card_like") for f in forms):
        fire("card_form", 0.9 if imitates else 0.75, "Page asks for a card number")
    if owner is None and any(f.get("password") for f in forms):
        fire("password_form", 0.88 if imitates else 0.72, "Page asks for a password")
    for f in forms:
        target = f.get("posts_to")
        if target and target != domain and owner is None:
            fire("form_other_domain", 0.85, f"Form posts to {target} (another domain)")
            break

    if sig.logo and sig.logo.get("brand") and not sig.logo.get("domain_matches_brand") and owner is None:
        fire("logo_mismatch", 0.95, f"Logo of {sig.logo['brand']} on a domain that brand does not use")

    qbrand = _query_brand(sig.query)
    if sig.channel == "search" and sig.is_ad and qbrand and owner is None:
        pos = f"top search ad" if (sig.rank or 9) <= 1 else "a search ad"
        fire("ad_brand_query", 0.82, f"Bought the {pos} for a {qbrand.name} query")
    elif sig.channel == "search" and qbrand and owner is None and named:
        fire("organic_brand_query", 0.7, f"Ranks for a {qbrand.name} query without being an official site")

    if owner is not None and _phone_in_query(sig.url):
        fire("search_parameter_injection", 0.85,
             f"Official {owner.name} site shows a phone number injected through the link")

    if sig.listing:
        if sig.listing.get("website_unrelated"):
            fire("listing_site_unrelated", 0.7, "Listing website is unrelated to the business name")
        if (sig.listing.get("phone_shared_with") or 0) >= 3:
            fire("listing_phone_reused", 0.75, f"Same phone number on {sig.listing['phone_shared_with']} listings")
        if sig.listing.get("brand_off_domain"):
            fire("listing_brand_off_domain", 0.85, sig.listing["brand_off_domain"])

    rep = sig.reputation or {}
    if rep.get("urlhaus"):
        fire("urlhaus", 0.95, "Listed by URLhaus (abuse.ch)")
    if rep.get("openphish"):
        fire("openphish", 0.95, "Listed by the OpenPhish feed")
    vt = rep.get("virustotal") or {}
    if vt.get("malicious", 0) >= 2:
        fire("virustotal", 0.9, f"{vt['malicious']} VirusTotal engines flag it as malicious")

    risk = max([model_mean] + floors)
    if model_mean >= threshold() and not any(r for r in rules if r != "young_domain"):
        reasons.insert(0, "Link pattern matches known fraud (DaE2 ensemble)")
    if owner is not None and "search_parameter_injection" not in rules:
        risk = min(risk, 0.2)
        reasons = [f"Domain is on the official list for {owner.name}"]
        rules = ["official_domain"]
    return Result(risk=round(float(risk), 4), model_mean=round(model_mean, 4),
                  votes={k: round(v, 4) for k, v in votes.items()}, reasons=reasons, rules=rules,
                  imitates=(imitates.name if imitates else None), threshold=threshold(),
                  scoring_ms=round(1000 * (time.perf_counter() - t0), 2))


def _phone_in_query(url: str) -> bool:
    import re
    q = split(url).query
    return bool(re.search(r"(?:\+|%2B)?(?:971|800|0?5\d)\D{0,3}\d{3}\D{0,3}\d{3,4}", q))


def score_url(url: str, **kwargs) -> Result:
    return score(Signals(url=url, **kwargs))


__all__ = ["Signals", "Result", "score", "score_url", "model_info", "threshold", "canonical"]
