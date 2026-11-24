"""Regression tests for the security audit of 24 November 2026 (Claude Security scan and pip-audit)."""

import pytest

from tests.test_api import client  # noqa: F401  (the API fixture, reused)


@pytest.mark.parametrize("url", [
    "http://pay-fines.top\\.adpolice.gov.ae/login",   # backslash: a browser opens pay-fines.top
    "https://pay-fines.top\\@adpolice.gov.ae/pay",
    "http://pay-fines.top\\.gov.ae/x",
    "https://adpolice.gov.ae@pay-fines.top/pay",       # userinfo: a browser ignores the part before @
])
def test_disguised_hosts_are_flagged_not_official(url):
    from mirsad.features.url import host_of
    from mirsad.scoring.engine import Signals, score

    r = score(Signals(url=url))
    assert host_of(url) == "pay-fines.top"
    assert "official_domain" not in r.rules and "disguised_host" in r.rules
    assert r.risk >= r.threshold


def test_official_sites_keep_their_cap_and_odd_names_are_never_official():
    from mirsad.features.brands import is_official
    from mirsad.scoring.engine import Signals, score

    assert score(Signals(url="https://www.salik.ae/")).rules == ["official_domain"]
    assert score(Signals(url="https://es.adpolice.gov.ae/TrafficServices?Culture=en")).rules == ["official_domain"]
    assert is_official("adpolice.gov.ae", "evil.top\\.adpolice.gov.ae") is None
    assert is_official("adpolice.gov.ae", "evil top.adpolice.gov.ae") is None


def test_redaction_has_no_public_key_and_public_echo_has_no_hash(tmp_path, monkeypatch):
    from mirsad.config import settings
    from mirsad.store import db

    monkeypatch.delitem(settings.env, "MIRSAD_REDACTION_KEY", raising=False)
    monkeypatch.setattr(db, "KEY_FILE", tmp_path / ".redaction_key")
    monkeypatch.setattr(db, "_key", None)
    hashed = db.redact("https://x.top/p?phone=0501234567", digest=True)
    assert (tmp_path / ".redaction_key").stat().st_size == 32   # a random key was made for this install
    assert "0501234567" not in hashed and len(hashed.split("[")[1].rstrip("]")) == 12
    assert db.redact("https://x.top/p?phone=0501234567&ok", digest=False) == "https://x.top/p?phone=[redacted]&ok"


def test_audit_limit_is_bounded(client):  # noqa: F811
    c, _, _ = client
    assert c.get("/api/audit?limit=-1").status_code == 422
    assert c.get("/api/audit?limit=0").status_code == 422
    assert c.get("/api/cases?limit=-1").status_code == 422
    assert c.get("/api/audit?limit=5").status_code == 200


def test_cross_site_and_non_json_posts_are_refused(client):  # noqa: F811
    c, cid, _ = client
    body = '{"action": "dismiss"}'
    evil = c.post(f"/api/cases/{cid}/decision", content=body,
                  headers={"Origin": "https://evil.example", "Content-Type": "application/json"})
    assert evil.status_code == 403
    form = c.post("/api/runs/search", headers={"Origin": "https://evil.example"})
    assert form.status_code == 403
    untyped = c.post(f"/api/cases/{cid}/decision", content=body, headers={"Content-Type": "text/plain"})
    assert untyped.status_code == 415
    ok = c.post(f"/api/cases/{cid}/decision", json={"action": "reviewing"}, headers={"Origin": "http://testserver"})
    assert ok.status_code == 200


def test_lab_server_answers_only_to_its_own_names(client):  # noqa: F811
    c, _, _ = client
    assert c.get("/api/health", headers={"Host": "rebind.attacker.example:8600"}).status_code == 400
    assert c.get("/api/health", headers={"Host": "127.0.0.1:8600"}).status_code == 200


def test_public_site_keeps_checked_links_out_of_the_audit_log(client, monkeypatch):  # noqa: F811
    from mirsad.config import settings

    c, _, store = client
    monkeypatch.setitem(settings.env, "MIRSAD_PUBLIC", "1")
    r = c.post("/api/check", json={"url": "https://adcb-verify.top/u/0501234567/claim?otp=1234"})
    assert r.status_code == 200 and r.json()["url"].endswith("otp=[redacted]")
    rows = store.rows("SELECT target FROM audit WHERE action = 'check'")
    assert rows and all("0501234567" not in (x["target"] or "") for x in rows)


def test_summary_check_rejects_text_that_clears_a_flagged_site():
    from mirsad.llm.summary import _facts, fact_check

    case = {"url": "https://salik-topup.top/pay", "domain": "salik-topup.top", "imitates": "Salik", "risk": 0.9,
            "threshold": 0.66, "reasons": ["Name imitates Salik but is not on the official list"], "evidence": []}
    facts = _facts(case)
    assert fact_check("This is the official Salik portal and is safe to dismiss.", case, facts)
    assert fact_check("الموقع رسمي وآمن.", case, facts)
    assert not fact_check("salik-topup.top imitates Salik but is not on the official list.", case, facts)
