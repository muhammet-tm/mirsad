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


def test_gov_ae_hosts_count_as_government():
    r = engine.score_url("https://www.adjd.gov.ae/en/pay-fines", channel="search", query="pay traffic fine abu dhabi")
    assert r.rules == ["official_domain"] and r.risk <= 0.2


def test_brand_in_path_does_not_count_as_impersonation():
    r = engine.score(engine.Signals(url="https://www.reddit.com/r/dubai/comments/salik_recharge_help/",
                                    channel="search", query="salik recharge"))
    assert "brand_off_domain" not in r.rules


def test_model_alone_needs_evidence_on_live_channels(monkeypatch):
    class Fake:
        def votes(self, urls):
            import numpy as np
            return {k: np.array([0.9]) for k in ("adaboost", "bagging", "stacking", "voting")}
    monkeypatch.setattr(engine, "_model", lambda: (Fake(), {"threshold": 0.66}, "fake"))
    live = engine.score(engine.Signals(url="https://ordinary-shop.com/", channel="maps"))
    assert live.risk < 0.66
    reported = engine.score(engine.Signals(url="https://ordinary-shop.com/", channel="report"))
    assert reported.risk >= 0.66


def test_display_text_is_not_a_link():
    from mirsad.collectors.sources import _real_link
    assert _real_link({"link": "https://www.google.ae/goto?url=x", "displayed_link": "6 تفاعل · قبل سنة واحدة"}) is None
    assert _real_link({"link": "https://www.google.ae/goto?url=x", "displayed_link": "https://www.salik.ae › en"}) == "https://www.salik.ae/en"


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


def test_summary_fact_check():
    from mirsad.llm.summary import _facts, fact_check

    case = {"display": "info-facture-prime.com", "channel_detail": "Feed (PhishStats)", "imitates": None,
            "risk": 0.7876, "reasons": ["Domain first seen 4 days ago"],
            "evidence": [{"label": "Domain registered 19 Nov 2026"}]}
    facts = _facts(case)
    stale = "info-facture-prime.com imitates the Dubai Police and carries a risk score of 0.86."
    assert len(fact_check(stale, case, facts)) == 3  # wrong number, unnamed brand, invented imitation
    good = ("info-facture-prime.com has a risk of 0.79; the domain was registered on 19 Nov 2026. "
            "No brand imitation was identified.")
    assert fact_check(good, case, facts) == []
    arabic = "تم تسجيل النطاق في ١٩ نوفمبر ٢٠٢٦ ولم يتم تحديد أي تقليد لعلامة تجارية."
    assert fact_check(arabic, case, facts) == []
    branded = dict(case, imitates="Salik")
    assert fact_check("The site imitates Salik.", branded, _facts(branded)) == []


def test_template_summary_names_the_channel_in_arabic():
    from mirsad.llm.summary import template

    case = {"display": "salik-topup.top", "channel": "feeds", "channel_detail": "Feed (OpenPhish)",
            "imitates": "Salik", "risk": 0.8, "reasons": ["Name imitates Salik but is not on the official list"]}
    s = template(case)
    assert "Feed (OpenPhish)" in s["en"] and "Feed (OpenPhish)" not in s["ar"]
    assert "موجزات التصيّد العامة" in s["ar"] and "0.80" in s["ar"]


def test_hosting_platform():
    from mirsad.features.url import hosting_platform, registered_domain

    assert hosting_platform("http://blessed-let-256047.framer.app/") == "framer.app"
    assert hosting_platform("https://x.github.io/login") == "github.io"
    assert hosting_platform("https://info-facture-prime.com/index.php") is None
    assert hosting_platform("https://www.salik.ae/") is None
    assert registered_domain("http://blessed-let-256047.framer.app/") == "framer.app"  # unchanged for brand checks


def test_ct_candidate_precision():
    from mirsad.features.brands import ct_candidate

    # real-looking targets of UAE brands
    for host in ["salik-pay.com", "emiratespost-track.top", "adpolice-fines.ae", "tamm-pay.xyz",
                 "dubai-rta-fines.com", "emiratesp0st-delivery.com", "uaepass-login.net", "sa1ik-recharge.com",
                 "saliktopup.ae", "emiratespst-track.com", "emirates-airlines.battery.cam", "salikk-pay.com"]:
        assert ct_candidate(host) is not None, host
    # false matches seen in the first live stream runs (23 November 2026)
    for host in ["old.itc.edu", "rta.engineering.ucsc.edu", "cap-du-jour.pages.dev", "paddedmoth4.chatgpt.site",
                 "com.alt-itc.ca", "www.mariesschmuckwelt.de", "xn--80ak6aa92e.com", "t05.4-sadik.ru",
                 "nkolay-salikhov.workers.dev", "www.salia.co", "allan-salih.workers.dev",
                 "moore-elizabeth-5-00.pages.dev", "conception.ecrire-a-mes-elus.lacfdtaltice.com"]:
        assert ct_candidate(host) is None, host


def test_certstream_local_config(tmp_path, monkeypatch):
    from mirsad.collectors import certstream_local as cl

    monkeypatch.setattr(cl, "BIN_DIR", tmp_path)
    text = cl.write_config(8603).read_text(encoding="utf-8")
    assert 'listen_addr: "127.0.0.1"' in text and "listen_port: 8603" in text and "enabled: false" in text
    assert cl.is_local("ws://127.0.0.1:8603/") and not cl.is_local("wss://certstream.calidog.io/")


def test_new_ids_follow_the_highest_id_after_a_removal(tmp_path):
    from mirsad.store import Store

    s = Store(tmp_path / "ids.sqlite3")
    ids = [s.upsert_candidate(f"https://example{i}.top/", "feeds")[0] for i in range(3)]
    with s.conn() as c:
        c.execute("DELETE FROM candidates WHERE id = ?", (ids[0],))  # a false candidate removed by hand
    new, created = s.upsert_candidate("https://another.top/", "feeds")
    assert created and new not in ids and new == f"MR-{int(ids[-1][3:]) + 1:04d}"
