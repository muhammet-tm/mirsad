"""API tests against a temporary database, with the model and network switched off."""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from mirsad import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    from mirsad.store import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.sqlite3")
    from mirsad.scoring import engine
    monkeypatch.setattr(engine, "_model", lambda: (None, {"threshold": 0.8}, None))
    from mirsad.sandbox import client as sb
    monkeypatch.setattr(sb, "available", lambda: False)
    from mirsad.api import app as app_module
    importlib.reload(app_module)
    store = app_module.store
    cid, _ = store.upsert_candidate("https://salik-topup-uae.top/recharge?email=a@b.com", "search",
                                    channel_detail='Search ad, position 1, "salik recharge"', query="salik recharge", rank=1, is_ad=True)
    store.save_score(cid, 0.97, 0.9, {"adaboost": 0.98, "bagging": 0.97, "stacking": 0.96, "voting": 0.95},
                     ["Name imitates Salik but is not on the official list"], ["brand_off_domain"], 0.8, 2.5)
    store.add_evidence(cid, "search_ad", 'Search ad position 1 for "salik recharge"', "Search monitor")
    return TestClient(app_module.app), cid, store


def test_health_and_status(client):
    c, _, _ = client
    assert c.get("/api/health").json()["ok"] is True
    assert {ch["id"] for ch in c.get("/api/status").json()["channels"]} == {"search", "maps", "certificates", "feeds"}


def test_queue_never_shows_raw_query_values(client):
    c, cid, _ = client
    items = c.get("/api/cases").json()["items"]
    assert items[0]["id"] == cid and "a@b.com" not in items[0]["url"]


def test_case_view_is_audited(client):
    c, cid, store = client
    case = c.get(f"/api/cases/{cid}").json()
    assert case["evidence"][0]["id"] == "E1" and case["graph"]["nodes"]
    assert store.one("SELECT * FROM audit WHERE action = 'view' AND target = ?", (cid,))


def test_decision_and_export(client):
    c, cid, store = client
    assert c.post(f"/api/cases/{cid}/decision", json={"action": "confirm"}).json()["status"] == "confirmed"
    pkg = c.get(f"/api/cases/{cid}/export").json()
    assert pkg["case"] == cid and "Articles 62 and 66" in pkg["purpose"]
    assert store.one("SELECT * FROM audit WHERE action = 'export' AND target = ?", (cid,))


def test_bad_decision_rejected(client):
    c, cid, _ = client
    assert c.post(f"/api/cases/{cid}/decision", json={"action": "delete"}).status_code == 422


def test_check_scores_a_link(client):
    c, _, _ = client
    out = c.post("/api/check", json={"url": "https://emiratesp0st-fee.com/pay?card=1"}).json()
    assert out["flagged"] and "card=1" not in out["url"]


def test_capture_path_traversal_blocked(client):
    c, _, _ = client
    assert c.get("/captures/..%2F..%2F.env").status_code == 404
