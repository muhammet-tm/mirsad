# Mirsad API

FastAPI service on `http://127.0.0.1:8600`. All responses are JSON. Times are ISO 8601 in UTC; the dashboard shows Gulf Standard Time (UTC+4). Every view, decision, and export is written to the audit log.

## Read

`GET /api/health`
```json
{"ok": true, "version": "0.1.0", "model": {"name": "DaE2", "threshold": 0.8, "trained_on": "PhreshPhish 2024-07 to 2025-09"},
 "integrations": {"search": true, "maps": true, "certificates": true, "feeds": true, "sandbox": false, "llm": "jais"}}
```

`GET /api/status`: one entry per discovery channel.
```json
{"channels": [
  {"id": "search", "label": "Search monitor", "state": "live", "last_run": "2026-11-24T17:40:00Z", "detail": "52 queries"},
  {"id": "maps", "label": "Maps check", "state": "live", "last_run": "2026-11-24T17:38:00Z", "detail": "31 listings"},
  {"id": "certificates", "label": "Certificate stream", "state": "live", "last_run": "2026-11-24T17:41:00Z", "detail": "1,240 certificates a minute"},
  {"id": "feeds", "label": "Feeds", "state": "synced", "last_run": "2026-11-24T17:30:00Z", "detail": "OpenPhish, URLhaus"}],
 "model": {"name": "DaE2 v1", "threshold": 0.8}, "now": "2026-11-24T17:42:00Z"}
```
`state` is one of `live`, `synced`, `idle`, `error`, `off`.

`GET /api/kpis`
```json
{"links_screened_today": 4812, "flagged": 37, "awaiting_review": 12, "confirmed": 9, "median_scoring_ms": 3.1,
 "channel_split": {"search": 16, "certificates": 12, "maps": 6, "feeds": 3},
 "flagged_per_hour": [{"hour": "2026-11-23T18:00:00Z", "count": 1}, "... 24 entries, oldest first"]}
```

`GET /api/cases?status=open&channel=all&limit=50`: the watch queue, highest risk first. `status` is `open` (new and reviewing), `new`, `reviewing`, `confirmed`, `dismissed`, or `all`. `channel` is `all`, `search`, `maps`, `certificates`, `feeds`, or `report`.
```json
{"total": 37, "items": [
  {"id": "MR-0142", "risk": 0.97, "url": "https://salik-topup-uae.top/recharge", "display": "salik-topup-uae.top",
   "channel": "search", "channel_detail": "Search ad, position 1, \"salik recharge\"", "imitates": "Salik",
   "first_seen": "2026-11-18T09:12:00Z", "age_days": 4, "votes": {"adaboost": 0.98, "bagging": 0.97, "stacking": 0.96, "voting": 0.95},
   "votes_above": 4, "status": "new"}]}
```

`GET /api/cases/{id}`: everything the case page needs.
```json
{"id": "MR-0142", "risk": 0.97, "threshold": 0.8, "status": "new", "url": "https://salik-topup-uae.top/recharge",
 "url_redacted": "https://salik-topup-uae.top/recharge", "display": "salik-topup-uae.top", "domain": "salik-topup-uae.top",
 "channel": "search", "channel_detail": "Search ad, position 1, \"salik recharge\"", "imitates": "Salik", "official_domains": ["salik.ae"],
 "first_seen": "2026-11-18T09:12:00Z", "age_days": 4,
 "votes": {"adaboost": 0.98, "bagging": 0.97, "stacking": 0.96, "voting": 0.95}, "model_mean": 0.965,
 "reasons": ["Domain first seen 4 days ago", "Page asks for a card number", "Name imitates Salik but is not on the official list", "Bought the top search ad for a Salik query"],
 "evidence": [
   {"id": "E1", "kind": "certificate", "label": "Certificate issued 18 Nov 2026", "source": "Let's Encrypt", "at": "2026-11-18T09:12:00Z"},
   {"id": "E2", "kind": "domain", "label": "Domain registered 18 Nov 2026", "source": "RDAP", "at": "2026-11-18T00:00:00Z"},
   {"id": "E3", "kind": "search_ad", "label": "Search ad position 1 for \"salik recharge\"", "source": "Search monitor", "at": "2026-11-22T17:40:00Z"},
   {"id": "E4", "kind": "form_target", "label": "Card form posts to pay-gw-secure.top (another domain)", "source": "Sandbox capture", "at": "2026-11-22T17:41:00Z"},
   {"id": "E5", "kind": "logo_match", "label": "Logo match: toll service brand, 0.91, on a domain that is not on the official allowlist", "source": "Phishpedia", "at": "2026-11-22T17:41:00Z"}],
 "capture": {"available": true, "screenshot": "/captures/MR-0142.png", "title": "Toll account top-up", "final_url": "https://salik-topup-uae.top/recharge",
             "forms": [{"fields": ["card number", "expiry", "cvv"], "posts_to": "pay-gw-secure.top"}], "captured_at": "2026-11-22T17:41:00Z", "note": "Captured in sandbox, no form submitted"},
 "summary": {"model": "Jais", "en": "A 4-day-old site bought the top ad ...", "ar": "موقع عمره أربعة أيام ...", "note": "model writes, does not decide"},
 "listing": null,
 "graph": {"nodes": [{"id": "domain", "label": "salik-topup-uae.top", "kind": "domain"}], "edges": [{"from": "ad", "to": "domain", "label": "links to"}]},
 "timeline": [{"at": "2026-11-18T09:12:00Z", "label": "Certificate issued", "evidence": "E1"}],
 "exports": ["registrar_abuse_report", "aeda", "police_blocking_request"],
 "decisions": [{"at": "2026-11-22T17:50:00Z", "action": "reviewing", "analyst": "Duty analyst"}]}
```
For a maps case, `listing` is `{"place_id": "...", "category": "Car rental", "website": "rent-cars-ad.site", "phone_shared_with": 6, "lat": 24.47, "lng": 54.37, "mismatch": "website unrelated to business name"}`. Map business names and addresses are not stored (Google Places terms); the dashboard shows the category and the case number.

`GET /api/map`: pins for the maps view.
```json
{"bounds": {"south": 24.20, "west": 54.25, "north": 24.62, "east": 54.80},
 "listings": [{"case_id": "MR-0151", "lat": 24.47, "lng": 54.37, "mismatch": true, "risk": 0.81, "phone_group": "g1", "category": "Car rental"}],
 "checked": 31, "mismatches": 6}
```

`GET /api/audit?limit=100`: append-only log entries `{"at", "actor", "action", "target", "detail"}`.

## Act

`POST /api/cases/{id}/decision` with `{"action": "confirm" | "dismiss" | "reviewing" | "assign", "note": "...", "analyst": "Duty analyst"}` returns the updated case. Confirm is only sent after the dashboard's hold-to-confirm completes.

`GET /api/cases/{id}/export`: the evidence package (JSON) for a registrar abuse report, an aeDA complaint, or a police blocking request. Query strings are redacted; the raw URL is included only in the package, and the export is audited.

`POST /api/check` with `{"url": "https://example.top/pay", "save": false}`: scores one link on demand and returns the same shape as a case (without capture unless the sandbox is on).

`POST /api/check/batch` with `{"urls": ["https://example.top/pay", "..."]}` (1 to 10,000 links): scores every link with the same model, rules, and official-domain cap as a single check, without storing cases, and returns `{"threshold", "results": [{"url", "risk", "flagged", "votes", "reasons", "imitates"}]}`. For files, `scripts/score_urls.py` does the same from the command line and writes a CSV.

`POST /api/runs/{channel}` with channel `search`, `maps`, `feeds`, or `certificates`: starts one collector run and returns `{"run_id", "channel", "started"}`.

## Static

`/` serves the Watch screen (`web/index.html`), `/case.html?id=MR-0142` the case page, `/captures/<id>.png` stored screenshots.
