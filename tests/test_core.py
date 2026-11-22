"""Unit tests for URL parsing, brand checks, redaction, scoring rules, and metrics."""

import pytest

from mirsad.features.brands import is_official, lookalike, mentioned_brand
from mirsad.features.url import FEATURE_NAMES, canonical, lexical_features, registered_domain, split, strip_query
from mirsad.models.evaluate import at_base_rate, report, threshold_for_fpr
from mirsad.scoring import engine
from mirsad.store.db import redact


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    """Rules are tested without the trained model, so results do not depend on training runs."""
    monkeypatch.setattr(engine, "_model", lambda: (None, {"threshold": 0.8}, None))


def test_canonical_removes_source_artifacts():
    assert canonical("HTTPS://WWW.Example.COM/path/") == "example.com/path"
    assert canonical("example.com/path") == "example.com/path"
    assert canonical("http://example.com:80/a?b=1") == "example.com/a?b=1"


def test_split_never_raises_on_broken_urls():
    for bad in ["http://[broken", "http://exa mple.com:99999/x", "::::", ""]:
        split(bad)  # must not raise


def test_registered_domain_uses_public_suffix_list():
    assert registered_domain("https://a.b.salik-topup-uae.top/x") == "salik-topup-uae.top"
    assert registered_domain("https://www.adpolice.gov.ae/en") == "adpolice.gov.ae"


def test_strip_query_drops_victim_data():
    assert strip_query("https://x.top/p?email=a@b.com#f") == "https://x.top/p"


def test_redaction_hashes_query_values():
    r = redact("https://x.top/login?email=victim@example.com&id=42")
    assert "victim" not in r and "42" not in r and r.startswith("https://x.top/login?email=[")


def test_official_domains_and_subdomains():
    assert is_official("salik.ae") is not None
    assert is_official("salik.ae", "www.salik.ae") is not None
    assert is_official("salik-topup-uae.top") is None


def test_lookalikes_catch_homoglyphs_and_brand_tokens():
    assert lookalike("emiratesp0st-fee.com")[0].name == "Emirates Post"
    assert lookalike("salik-topup-uae.top")[0].name == "Salik"
    assert lookalike("weather-today.com")[0] is None


def test_short_brand_tokens_need_a_whole_token():
    assert mentioned_brand("product-catalogue.com") is None  # "du" inside a word does not count
    assert mentioned_brand("du-recharge-offer.xyz").name == "du"


def test_lexical_features_shape():
    v = lexical_features("https://salik-topup-uae.top/recharge")
    assert v.shape == (len(FEATURE_NAMES),)


def test_brand_off_domain_rule_fires_and_explains():
    r = engine.score_url("https://salik-topup-uae.top/recharge")
    assert "brand_off_domain" in r.rules and r.risk >= 0.8
    assert any("Salik" in reason for reason in r.reasons)


def test_official_domain_is_capped():
    r = engine.score_url("https://www.salik.ae/en/", reputation={"openphish": True})
    assert r.risk <= 0.2 and r.rules == ["official_domain"]


def test_search_parameter_injection_on_official_domain():
    r = engine.score_url("https://www.adcb.com/en/search?q=call+%2B971+50+123+4567")
    assert "search_parameter_injection" in r.rules and r.risk >= 0.85


def test_card_form_and_other_domain_target():
    sig = engine.Signals(url="https://emiratespost-fee.com/pay", capture={"forms": [{"card_like": True, "posts_to": "pay-gw.top"}]})
    r = engine.score(sig)
    assert {"card_form", "form_other_domain"} <= set(r.rules) and r.risk >= 0.9


def test_search_ad_for_brand_query():
    sig = engine.Signals(url="https://cheap-toll-pay.top/", channel="search", query="salik recharge", rank=1, is_ad=True)
    r = engine.score(sig)
    assert "ad_brand_query" in r.rules
    assert any("top search ad" in x for x in r.reasons)


def test_listing_phone_reuse():
    sig = engine.Signals(url="https://rent-cars-ad.site/", channel="maps", listing={"phone_shared_with": 6, "website_unrelated": True})
    r = engine.score(sig)
    assert "listing_phone_reused" in r.rules and r.risk >= 0.75


def test_young_domain_adds_reason_without_floor():
    sig = engine.Signals(url="https://neutral-blog.com/", domain_age_days=3)
    r = engine.score(sig)
    assert "young_domain" in r.rules and r.risk == 0.0


def test_base_rate_precision():
    assert at_base_rate(0.9, 0.01, 0.5) == pytest.approx(0.989, abs=1e-3)
    assert at_base_rate(0.9, 0.01, 0.001) == pytest.approx(0.0826, abs=1e-3)


def test_threshold_and_report():
    y = [0, 0, 0, 0, 1, 1, 1, 1]
    s = [0.1, 0.2, 0.3, 0.9, 0.6, 0.7, 0.8, 0.95]
    t = threshold_for_fpr(y, s, 0.0)
    rep = report(y, s, t)
    assert rep["false_positive_rate"] == 0.0 and rep["fraud_class"]["recall"] > 0
    assert rep["macro_average"] and rep["weighted_average"]
