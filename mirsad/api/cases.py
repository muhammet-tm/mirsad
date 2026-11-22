"""Builds the case and list shapes documented in docs/API.md from the store."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from ..features.brands import BRANDS
from ..scoring.engine import threshold
from ..store import Store


def _age_days(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except ValueError:
        return None


def _display(row: dict) -> str:
    if row["url"].startswith("tel:"):
        listing = json.loads(row["listing_json"] or "{}")
        return f"{listing.get('category', 'listing').capitalize()} listing"
    if row["channel"] == "maps":
        listing = json.loads(row["listing_json"] or "{}")
        return f"{listing.get('category', 'listing').capitalize()} listing ({row['domain']})"
    return row["host"] or row["domain"]


def list_cases(store: Store, status: str = "open", channel: str = "all", limit: int = 50, min_risk: float | None = None) -> dict:
    where, args = ["s.risk IS NOT NULL"], []
    if status == "open":
        where.append("c.status IN ('new','reviewing')")
    elif status != "all":
        where.append("c.status = ?")
        args.append(status)
    if channel != "all":
        where.append("c.channel = ?")
        args.append(channel)
    thr = threshold() if min_risk is None else min_risk
    where.append("s.risk >= ?")
    args.append(thr)
    sql = f"""SELECT c.*, s.risk, s.votes_json FROM candidates c JOIN scores s ON s.candidate_id = c.id
              WHERE {' AND '.join(where)} ORDER BY s.risk DESC, c.discovered_at DESC"""
    rows = store.rows(sql, tuple(args))
    items = []
    for r in rows[:limit]:
        votes = json.loads(r["votes_json"] or "{}")
        items.append({"id": r["id"], "risk": r["risk"], "url": r["url_redacted"], "display": _display(r),
                      "channel": r["channel"], "channel_detail": r["channel_detail"], "imitates": r["imitates"],
                      "first_seen": r["first_seen"], "age_days": _age_days(r["first_seen"]), "votes": votes,
                      "votes_above": sum(v >= threshold() for v in votes.values()), "status": r["status"]})
    return {"total": len(rows), "items": items}


def build_case(store: Store, cid: str) -> dict | None:
    r = store.one("SELECT c.*, s.* FROM candidates c LEFT JOIN scores s ON s.candidate_id = c.id WHERE c.id = ?", (cid,))
    if not r:
        return None
    votes = json.loads(r.get("votes_json") or "{}")
    ev_rows = store.rows("SELECT * FROM evidence WHERE candidate_id = ? ORDER BY observed_at", (cid,))
    evidence = [{"id": f"E{i + 1}", "kind": e["kind"], "label": e["label"], "source": e["source"], "at": e["observed_at"]}
                for i, e in enumerate(ev_rows)]
    cap = store.one("SELECT * FROM captures WHERE candidate_id = ?", (cid,))
    summ = store.one("SELECT * FROM summaries WHERE candidate_id = ?", (cid,))
    listing = json.loads(r["listing_json"]) if r.get("listing_json") else None
    official = next((list(b.domains) for b in BRANDS if b.name == r.get("imitates")), [])
    decisions = store.rows("SELECT at, action, analyst, note FROM decisions WHERE candidate_id = ? ORDER BY at", (cid,))
    case = {
        "id": cid, "risk": r.get("risk"), "threshold": r.get("threshold") or threshold(), "status": r["status"],
        "url": r["url_redacted"], "url_redacted": r["url_redacted"], "display": _display(r), "domain": r["domain"],
        "channel": r["channel"], "channel_detail": r["channel_detail"], "imitates": r.get("imitates"),
        "official_domains": official, "first_seen": r.get("first_seen"), "age_days": _age_days(r.get("first_seen")),
        "votes": votes, "model_mean": r.get("model_mean"), "reasons": json.loads(r.get("reasons_json") or "[]"),
        "evidence": evidence,
        "capture": ({"available": bool(cap.get("screenshot")), "screenshot": cap.get("screenshot"), "title": cap.get("title"),
                     "final_url": cap.get("final_url"), "forms": json.loads(cap.get("forms_json") or "[]"),
                     "captured_at": cap.get("captured_at"), "note": "Captured in sandbox, no form submitted"}
                    if cap else {"available": False}),
        "summary": ({"model": summ["model"], "en": summ["en"], "ar": summ["ar"], "note": "model writes, does not decide"}
                    if summ else None),
        "listing": listing, "decisions": decisions,
        "exports": ["registrar_abuse_report", "aeda", "police_blocking_request"],
    }
    case["timeline"] = [{"at": e["at"], "label": e["label"], "evidence": e["id"]} for e in evidence if e["at"]]
    case["graph"] = _graph(case)
    return case


def _graph(case: dict) -> dict:
    """Evidence graph in the dashboard's node vocabulary: domain (center), search_ad, certificate, page,
    form_target, brand, listing, phone, and link (reputation lists)."""
    nodes = [{"id": "domain", "label": case["domain"], "kind": "domain"}]
    edges = []
    have = set()

    def add(nid, kind, label, src, dst, rel):
        if nid not in have:
            nodes.append({"id": nid, "label": label, "kind": kind})
            have.add(nid)
        edges.append({"from": src, "to": dst, "label": rel})

    cap = case.get("capture") or {}
    page_present = cap.get("available") or any(e["kind"] in ("form_target", "logo_match") for e in case["evidence"])
    if page_present:
        add("page", "page", cap.get("title") or "Captured page", "domain", "page", "serves")
    for e in case["evidence"]:
        k = e["kind"]
        if k in ("search_ad", "search_result"):
            add("search_ad", "search_ad", e["label"].replace("Search ", "").capitalize(), "search_ad", "domain", "links to")
        elif k == "certificate":
            add("certificate", "certificate", e["label"].replace("Certificate issued ", "Issued "), "certificate", "domain", "issued for")
        elif k == "form_target":
            target = e["label"].split(" posts to ")[-1].split(" (")[0]
            add("form_target", "form_target", target, "page" if page_present else "domain", "form_target", "posts card data to")
        elif k == "logo_match":
            add("brand", "brand", case.get("imitates") or e["label"].split(":")[-1].split(",")[0].strip(),
                "page" if page_present else "domain", "brand", "imitates")
        elif k == "listing":
            if "phone" in e["label"].lower():
                add("listing", "listing", (case.get("listing") or {}).get("category", "Maps listing"), "listing", "domain", "points to")
                add("phone", "phone", e["label"], "phone", "listing", "shared phone")
            else:
                add("listing", "listing", (case.get("listing") or {}).get("category", "Maps listing"), "listing", "domain", "points to")
        elif k == "reputation":
            add("reputation", "link", e["label"], "reputation", "domain", "lists")
    if case.get("imitates") and "brand" not in have:
        add("brand", "brand", case["imitates"], "domain", "brand", "imitates")
    return {"nodes": nodes, "edges": edges}


def kpis(store: Store) -> dict:
    now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=24)).isoformat(timespec="seconds")
    thr = threshold()
    screened = store.one("SELECT COALESCE(SUM(count),0) AS n FROM screened WHERE day >= ?", (since[:10],))["n"]
    flagged_rows = store.rows("""SELECT c.channel, c.discovered_at FROM candidates c JOIN scores s ON s.candidate_id = c.id
                                 WHERE s.risk >= ? AND c.discovered_at >= ?""", (thr, since))
    split = {"search": 0, "certificates": 0, "maps": 0, "feeds": 0}
    hours = [0] * 24
    for row in flagged_rows:
        split[row["channel"]] = split.get(row["channel"], 0) + 1
        try:
            dt = datetime.fromisoformat(row["discovered_at"])
            idx = 23 - int((now - dt).total_seconds() // 3600)
            if 0 <= idx < 24:
                hours[idx] += 1
        except ValueError:
            pass
    start = (now - timedelta(hours=23)).replace(minute=0, second=0, microsecond=0)
    awaiting = store.one("""SELECT COUNT(*) AS n FROM candidates c JOIN scores s ON s.candidate_id = c.id
                            WHERE s.risk >= ? AND c.status IN ('new','reviewing')""", (thr,))["n"]
    confirmed = store.one("SELECT COUNT(*) AS n FROM candidates WHERE status = 'confirmed'")["n"]
    ms = [x["scoring_ms"] for x in store.rows("SELECT scoring_ms FROM scores WHERE scoring_ms IS NOT NULL ORDER BY scored_at DESC LIMIT 500")]
    ms.sort()
    return {"links_screened_today": int(screened), "flagged": len(flagged_rows), "awaiting_review": int(awaiting),
            "confirmed": int(confirmed), "median_scoring_ms": round(ms[len(ms) // 2], 1) if ms else None,
            "channel_split": split,
            "flagged_per_hour": [{"hour": (start + timedelta(hours=i)).isoformat(timespec="seconds"), "count": hours[i]} for i in range(24)]}


def map_data(store: Store) -> dict:
    rows = store.rows("""SELECT c.id, c.listing_json, s.risk FROM candidates c LEFT JOIN scores s ON s.candidate_id = c.id
                         WHERE c.channel = 'maps' AND c.listing_json IS NOT NULL""")
    listings = []
    for r in rows:
        l = json.loads(r["listing_json"])
        if l.get("lat") is None:
            continue
        listings.append({"case_id": r["id"], "lat": l["lat"], "lng": l["lng"], "mismatch": bool(l.get("mismatch")),
                         "risk": r["risk"], "phone_group": l.get("phone_group"), "category": l.get("category")})
    return {"bounds": {"south": 24.20, "west": 54.25, "north": 24.62, "east": 54.80}, "listings": listings,
            "checked": len(listings), "mismatches": sum(x["mismatch"] for x in listings)}
