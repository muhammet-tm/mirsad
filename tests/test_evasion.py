"""Evasion handling (short links, redirects, cloaking), sandbox form flags, and batch scoring."""

import httpx
import pytest


def test_card_form_fires_on_sandbox_form_shape():
    # The sandbox reports has_card_like on the form and card_like only on its fields.
    from mirsad.scoring import engine

    form = {"posts_to": "pay-salik.top", "has_card_like": True, "has_password": False,
            "fields": [{"type": "text", "card_like": True}]}
    r = engine.score(engine.Signals(url="https://pay-salik.top/checkout", capture={"forms": [form]}))
    assert "card_form" in r.rules
    field_only = {"posts_to": "pay-salik.top", "fields": [{"type": "password", "password": True}]}
    r2 = engine.score(engine.Signals(url="https://pay-salik.top/login", capture={"forms": [field_only]}))
    assert "password_form" in r2.rules


def test_score_batch_matches_single_scores():
    from mirsad.scoring import engine

    urls = ["https://www.adcb.com/", "http://salik-topup-uae.top/pay?card=1", "https://example.com/about",
            "https://emiratespost-delivery-fee.com/track"]
    batch = engine.score_batch(urls, chunk=3)
    single = [engine.score(engine.Signals(url=u)) for u in urls]
    assert [b.risk for b in batch] == [s.risk for s in single]
    assert batch[0].risk <= 0.2  # official domain stays capped


def test_short_link_expansion_never_contacts_the_destination():
    from mirsad.enrich import redirects

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        if request.url.host == "bit.ly":
            return httpx.Response(301, headers={"location": "https://tinyurl.com/abc"})
        if request.url.host == "tinyurl.com":
            return httpx.Response(302, headers={"location": "https://salik-pay.top/login"})
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        dest, chain = redirects.expand_short_link("https://bit.ly/x1", client=c)
    assert dest == "https://salik-pay.top/login"
    assert chain == ["https://bit.ly/x1", "https://tinyurl.com/abc", "https://salik-pay.top/login"]
    assert "salik-pay.top" not in seen
    assert not redirects.is_short_link("https://salik.ae/")


def test_score_urls_reads_lists_and_labeled_csv(tmp_path):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("score_urls", Path(__file__).resolve().parent.parent / "scripts" / "score_urls.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    plain = tmp_path / "urls.txt"
    plain.write_text("https://a.example/\n\nhttps://b.example/x\n", encoding="utf-8")
    assert mod.read_input(plain) == (["https://a.example/", "https://b.example/x"], None)
    labeled = tmp_path / "test.csv"
    labeled.write_text("URL,Label\nhttps://a.example/,legitimate\nhttps://b.example/x,phishing\n", encoding="utf-8")
    assert mod.read_input(labeled) == (["https://a.example/", "https://b.example/x"], [0, 1])


@pytest.fixture()
def fake_world(tmp_path, monkeypatch):
    """A store in a temp folder and a simulated sandbox; no network."""
    from mirsad import pipeline
    from mirsad.enrich import passive
    from mirsad.store import Store

    monkeypatch.setattr(passive, "rdap_created", lambda d: None)
    monkeypatch.setattr(passive, "first_certificate", lambda d: None)
    monkeypatch.setattr(passive, "urlhaus_lookup", lambda u: None)
    monkeypatch.setattr(pipeline.hosting, "lookup", lambda h: None)
    monkeypatch.setattr(pipeline.sandbox, "phishpedia", lambda u, s: None)
    return Store(tmp_path / "t.sqlite3")


def test_redirect_to_scam_page_is_scored_at_the_destination(fake_world, monkeypatch):
    from mirsad import pipeline
    from mirsad.collectors.sources import Found

    form = {"posts_to": "collect-cards.top", "has_card_like": True, "fields": []}
    monkeypatch.setattr(pipeline.sandbox, "capture", lambda cid, url, device="desktop", **k: {
        "final_url": "https://salik-pay.top/pay", "forms": [form], "title": "Pay"})
    cid, risk = pipeline.process(fake_world, Found("https://harmless-looking.example/r?id=7", "report"),
                                 use_sandbox=True, summaries=False)
    labels = [e["label"] for e in fake_world.rows("SELECT label FROM evidence WHERE candidate_id=?", (cid,))]
    assert "Redirects to salik-pay.top" in labels
    assert risk >= 0.85


def test_cloaking_uses_the_mobile_capture(fake_world, monkeypatch):
    from mirsad import pipeline
    from mirsad.collectors.sources import Found

    def capture(cid, url, device="desktop", **k):
        if device == "mobile":
            return {"final_url": url, "forms": [{"posts_to": "salik-topup.top", "has_card_like": True, "fields": []}]}
        return {"final_url": url, "forms": []}

    monkeypatch.setattr(pipeline.sandbox, "capture", capture)
    cid, risk = pipeline.process(fake_world, Found("https://salik-topup.top/", "report"), use_sandbox=True, summaries=False)
    labels = [e["label"] for e in fake_world.rows("SELECT label FROM evidence WHERE candidate_id=?", (cid,))]
    assert any("possible cloaking" in lab for lab in labels)
    assert risk >= 0.85


def test_cases_on_the_same_address_are_linked_but_not_through_a_cdn(fake_world, monkeypatch):
    from mirsad import pipeline
    from mirsad.api.cases import build_case
    from mirsad.collectors.sources import Found
    from mirsad.enrich import hosting

    homes = {"salik-topup.top": ("203.0.113.7", 64500), "salik-recharge.top": ("203.0.113.7", 64500),
             "tamm-fines.top": ("198.51.100.9", 13335), "tamm-pay.top": ("198.51.100.9", 13335)}

    def lookup(host):
        ip, asn = homes[host]
        return {"host": host, "ips": [ip], "ip": ip, "asn": asn, "as_name": "TEST-NET - Example Hosting, NL",
                "cc": "NL", "cdn": asn in hosting.CDN_ASNS, "resolved_at": "2026-11-24T08:00:00+00:00"}

    monkeypatch.setattr(pipeline.hosting, "lookup", lookup)
    ids = {h: pipeline.process(fake_world, Found(f"https://{h}/pay", "report"), use_sandbox=False, summaries=False)[0]
           for h in homes}
    a = build_case(fake_world, ids["salik-topup.top"])
    assert [(x["domain"], x["via"]) for x in a["linked"]] == [("salik-recharge.top", "address")]
    assert any(n["kind"] == "network" for n in a["graph"]["nodes"])
    assert any(e["label"].startswith("Resolves to 203.0.113.7, AS64500 Example Hosting (NL)") for e in a["evidence"])
    assert build_case(fake_world, ids["tamm-fines.top"])["linked"] == []  # a shared CDN address links nothing


def test_hosting_label_and_owner_name():
    from mirsad.enrich import hosting

    assert hosting.short_owner("CLOUDFLARENET - Cloudflare, Inc., US") == "Cloudflare, Inc."
    assert hosting.short_owner("OVH, FR") == "OVH"
    assert hosting.lookup("salik-topup-uae.example") is None  # reserved names are never looked up


def test_cases_sharing_private_name_servers_are_linked(fake_world, monkeypatch):
    from mirsad import pipeline
    from mirsad.api.cases import build_case
    from mirsad.collectors.sources import Found

    ns = {"tamm-fines.top": ["ns1.fastflux-dns.top", "ns2.fastflux-dns.top"],
          "tamm-pay.top": ["ns1.fastflux-dns.top", "ns2.fastflux-dns.top"],
          "adcb-login.top": ["dns1.registrar-servers.com", "dns2.registrar-servers.com"],
          "adcb-verify.top": ["dns1.registrar-servers.com", "dns2.registrar-servers.com"]}
    monkeypatch.setattr(pipeline.passive, "rdap_created", lambda d: "2026-11-20T08:00:00Z")
    monkeypatch.setattr(pipeline.passive, "rdap_record", lambda d: {
        "domain": d, "created": "2026-11-20T08:00:00Z", "expires": "2027-11-20T08:00:00Z",
        "registrar": "Example Registrar", "nameservers": ns[d], "status": []})
    monkeypatch.setattr(pipeline.hosting, "lookup", lambda h: None)
    ids = {d: pipeline.process(fake_world, Found(f"https://{d}/pay", "report"), use_sandbox=False, summaries=False)[0]
           for d in ns}
    a = build_case(fake_world, ids["tamm-fines.top"])
    assert [(x["domain"], x["via"], x["shared"]) for x in a["linked"]] == [("tamm-pay.top", "name servers", "fastflux-dns.top")]
    assert any(e["label"].startswith("Registrar Example Registrar; expires 20 Nov 2027") for e in a["evidence"])
    assert build_case(fake_world, ids["adcb-login.top"])["linked"] == []  # a registrar's shared name servers link nothing
