"""Evidence reports for download: one case, or every flagged case with the totals and the method.

Each report is an HTML page in English or Arabic, rendered to PDF by a headless Chromium when
Playwright is installed (the Docker image installs it) and served as a printable page otherwise.
Every value comes from the case store or results/*.json and is escaped, because evidence labels and
page titles can come from an attacker's page. Chromium runs with JavaScript off and every network
request blocked, so a report can never fetch anything.
"""

from __future__ import annotations

import base64
import functools
import html
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import DATA_DIR, RESULTS_DIR, ROOT, settings
from ..store import Store, now
from .cases import build_case, kpis

FONTS = ROOT / "deck" / "vendor" / "fonts"
CAPTURES = DATA_DIR / "captures"
GST = timezone(timedelta(hours=4))
_render_lock = threading.Lock()

T = {
    "en": {
        "dir": "ltr", "case_title": "Evidence report", "all_title": "Summary report",
        "generated": "Generated {t}", "public": "Public demo copy: query values in links are replaced by hashes.",
        "link": "Link", "domain": "Domain", "found": "Found through", "first_seen": "First seen", "status": "Status",
        "risk": "Final risk", "threshold": "Threshold", "imitates": "Imitates", "votes": "Ensemble votes",
        "above": "{n} of 4 above the threshold", "mean": "Mean of the four", "none": "none",
        "why": "Why it was flagged", "summary": "Summary", "summary_note": "written by {m}; the model writes and does not decide",
        "evidence": "Evidence", "ex": "Exhibit", "obs": "Observation", "src": "Source", "at": "Observed",
        "no_ev": "No exhibits for this case.", "hosting": "Hosting and linked cases",
        "linked": "Linked cases (same hosting address or same private name servers):",
        "via": {"address": "same address {v}", "name servers": "same name servers {v}"},
        "no_link": "No other case shares this case's hosting address or private name servers.",
        "capture": "Captured page", "no_capture": ("No capture. Pages are opened only in the isolated sandbox VM; the public "
                                                   "server never opens a suspect page."),
        "cap_title": "Page title", "cap_final": "Final address", "forms": "Forms",
        "timeline": "Timeline", "decisions": "Decisions", "no_dec": "No decision yet.",
        "legal": "Legal basis and handling",
        "legal_text": ("This report supports a registrar abuse report, an aeDA complaint, or an Abu Dhabi Police blocking "
                       "request under Articles 62 and 66 of Federal Decree-Law No. 34 of 2021. Mirsad recommends; an "
                       "officer decides."),
        "method": "How the risk is computed",
        "method_text": ("Four ensembles (AdaBoost, Bagging, Stacking, and Voting) score the link from its text alone. The "
                        "risk is the mean of their probabilities, adjusted by evidence rules such as a protected brand "
                        "on a domain it does not own, a card form that posts elsewhere, or a domain a few days old. A "
                        "case is flagged at or above the threshold of {thr}, which was set so that at most 1% of "
                        "legitimate links in the validation data cross it."),
        "totals": "Totals", "screened_all": "Links screened, all runs", "screened_today": "Links screened today",
        "flagged": "Flagged cases", "awaiting": "Awaiting review", "confirmed": "Confirmed", "dismissed": "Dismissed",
        "by_channel": "Flagged cases by channel", "results": "Model results",
        "results_text": ("Deployed model on later months (trained on PhreshPhish URLs from July 2024 to September 2025, "
                         "tested on September to December 2025):"),
        "accuracy": "Accuracy", "recall": "Fraud recall", "fpr": "False-positive rate", "auc": "ROC AUC",
        "cases": "Flagged cases", "case": "Case", "channel": "Channel", "details": "Case details",
        "no_cases": "No case is above the threshold yet.",
        "limits": "Limitations",
        "limits_text": ("The model reads the link only, so a scam on a clean-looking address needs a second signal. "
                        "The brand list is a prototype, and an operational version needs each brand to confirm its "
                        "domains. Search ads vary by time and place. Hosting is a dated observation and can change."),
        "page": "Mirsad prototype, Abu Dhabi University team, ScamShield AI hackathon",
        "ch": {"search": "Search", "certificates": "Certificates", "maps": "Maps", "feeds": "Feeds", "report": "Reports"},
        "st": {"new": "New", "reviewing": "Reviewing", "confirmed": "Confirmed", "dismissed": "Dismissed", "assigned": "Assigned"},
    },
    "ar": {
        "dir": "rtl", "case_title": "تقرير الأدلة", "all_title": "التقرير الموجز",
        "generated": "أُنشئ في {t}", "public": "نسخة العرض العام: استُبدلت قيم الاستعلام في الروابط بقيم تجزئة.",
        "link": "الرابط", "domain": "النطاق", "found": "مصدر الرصد", "first_seen": "أول ظهور", "status": "الحالة",
        "risk": "درجة الخطورة النهائية", "threshold": "العتبة", "imitates": "ينتحل", "votes": "أصوات النماذج",
        "above": "{n} من 4 فوق العتبة", "mean": "متوسط الأربعة", "none": "لا شيء",
        "why": "سبب الإشارة", "summary": "الملخص", "summary_note": "كتبه {m}؛ النموذج يكتب ولا يقرر",
        "evidence": "الأدلة", "ex": "الدليل", "obs": "الملاحظة", "src": "المصدر", "at": "وقت الرصد",
        "no_ev": "لا توجد أدلة لهذه القضية.", "hosting": "الاستضافة والقضايا المرتبطة",
        "linked": "قضايا مرتبطة (عنوان الاستضافة نفسه أو خوادم الأسماء الخاصة نفسها):",
        "via": {"address": "العنوان نفسه {v}", "name servers": "خوادم الأسماء نفسها {v}"},
        "no_link": "لا تشترك أي قضية أخرى مع هذه القضية في عنوان الاستضافة أو خوادم الأسماء الخاصة.",
        "capture": "الصفحة الملتقطة", "no_capture": ("لا توجد لقطة. لا تُفتح الصفحات إلا داخل بيئة العزل الافتراضية، "
                                                       "ولا يفتح الخادم العام أي صفحة مشبوهة."),
        "cap_title": "عنوان الصفحة", "cap_final": "العنوان النهائي", "forms": "النماذج",
        "timeline": "التسلسل الزمني", "decisions": "القرارات", "no_dec": "لا يوجد قرار بعد.",
        "legal": "الأساس القانوني والتعامل",
        "legal_text": ("يدعم هذا التقرير بلاغ إساءة لدى مسجّل النطاق، أو شكوى إلى إدارة نطاق ae. (aeDA)، أو طلب حجب "
                       "من شرطة أبوظبي بموجب المادتين 62 و66 من المرسوم بقانون اتحادي رقم 34 لسنة 2021. مرصاد يوصي، "
                       "والضابط يقرر."),
        "method": "كيف تُحسب درجة الخطورة",
        "method_text": ("تقيّم أربع مجموعات نماذج (AdaBoost وBagging وStacking وVoting) الرابط من نصه وحده. والخطورة هي "
                        "متوسط احتمالاتها بعد تعديله بقواعد الأدلة، مثل علامة محمية على نطاق لا تملكه، أو نموذج بطاقة "
                        "يُرسل بياناته إلى نطاق آخر، أو نطاق عمره أيام قليلة. وتُرفع القضية عند بلوغ العتبة {thr} أو "
                        "تجاوزها، وقد ضُبطت بحيث لا يتجاوزها أكثر من 1% من الروابط السليمة في بيانات التحقق."),
        "totals": "الأرقام الإجمالية", "screened_all": "الروابط المفحوصة في كل التشغيلات",
        "screened_today": "الروابط المفحوصة اليوم", "flagged": "القضايا المشبوهة", "awaiting": "بانتظار المراجعة",
        "confirmed": "مؤكدة", "dismissed": "مستبعدة", "by_channel": "القضايا المشبوهة حسب القناة",
        "results": "نتائج النموذج",
        "results_text": ("النموذج المنشور على أشهر لاحقة (دُرّب على روابط PhreshPhish من يوليو 2024 إلى سبتمبر 2025، "
                         "واختُبر على الفترة من سبتمبر إلى ديسمبر 2025):"),
        "accuracy": "الدقة", "recall": "نسبة اكتشاف الاحتيال", "fpr": "معدل الإنذارات الخاطئة", "auc": "ROC AUC",
        "cases": "القضايا المشبوهة", "case": "القضية", "channel": "القناة", "details": "تفاصيل القضايا",
        "no_cases": "لا توجد قضية فوق العتبة بعد.",
        "limits": "القيود",
        "limits_text": ("يقرأ النموذج الرابط وحده، لذا يحتاج الاحتيال على عنوان يبدو سليمًا إلى إشارة ثانية. قائمة "
                        "العلامات نموذج أولي، وتحتاج النسخة التشغيلية إلى أن تؤكد كل جهة نطاقاتها. وتختلف إعلانات "
                        "البحث باختلاف الوقت والمكان. والاستضافة ملاحظة مؤرخة قد تتغير."),
        "page": "نموذج مرصاد الأولي، فريق جامعة أبوظبي، هاكاثون ScamShield AI",
        "ch": {"search": "البحث", "certificates": "الشهادات", "maps": "الخرائط", "feeds": "الموجزات", "report": "البلاغات"},
        "st": {"new": "جديدة", "reviewing": "قيد المراجعة", "confirmed": "مؤكدة", "dismissed": "مستبعدة", "assigned": "مُسندة"},
    },
}


def e(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def ltr(v) -> str:
    """Addresses and other Latin data keep their order inside Arabic text."""
    return f'<bdi dir="ltr">{e(v)}</bdi>'


ENSEMBLE_NAMES = {"adaboost": "AdaBoost", "bagging": "Bagging", "stacking": "Stacking", "voting": "Voting"}


def day(iso: str | None) -> str:
    """A date and time that keeps its order inside Arabic text."""
    return ltr(when(iso)) if iso else ""


def when(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(GST).strftime("%d %b %Y, %H:%M GST").lstrip("0")
    except ValueError:
        return iso


@functools.lru_cache(maxsize=1)
def _font_css() -> str:
    faces = []
    for fam, files in (("Inter Tight", ("inter-tight-latin-400-normal", "inter-tight-latin-600-normal",
                                        "inter-tight-latin-700-normal")),
                       ("IBM Plex Sans Arabic", ("ibm-plex-sans-arabic-arabic-600-normal",
                                                 "ibm-plex-sans-arabic-arabic-700-normal"))):
        for f in files:
            p = FONTS / f"{f}.woff2"
            if p.exists():
                weight = f.split("-")[-2]
                b64 = base64.b64encode(p.read_bytes()).decode()
                faces.append(f"@font-face{{font-family:'{fam}';font-weight:{weight};"
                             f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return "".join(faces)


CSS = """
@page{size:A4;margin:16mm 14mm 16mm 14mm}
*{box-sizing:border-box}
body{margin:0;font:10pt/1.45 'Inter Tight','Noto Sans Arabic','Segoe UI','IBM Plex Sans Arabic',Arial,sans-serif;color:#10233A}
html[dir=rtl] body{font-family:'Noto Sans Arabic','Segoe UI','IBM Plex Sans Arabic','Inter Tight',Arial,sans-serif}
h1,h2,h3,.k b,.brand b{font-family:'Inter Tight','IBM Plex Sans Arabic','Noto Sans Arabic','Segoe UI',sans-serif}
h1{font-size:17pt;margin:0 0 2mm;color:#034A89}
h2{font-size:12pt;margin:7mm 0 2mm;color:#034A89;border-bottom:1px solid #D5DEE8;padding-bottom:1mm;break-after:avoid}
h3{font-size:11pt;margin:6mm 0 1.5mm;break-after:avoid}
.brand{display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #034A89;padding-bottom:2mm;margin-bottom:4mm}
.brand b{font-size:13pt;color:#034A89}.brand span{color:#51657C;font-size:9pt}
.note{background:#F2F5F9;border:1px solid #D5DEE8;border-radius:3px;padding:2mm 3mm;color:#51657C;font-size:9pt;margin:2mm 0}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:2mm;margin:2mm 0}
.k{border:1px solid #D5DEE8;border-radius:3px;padding:2mm 3mm}.k small{display:block;color:#51657C;font-size:8pt}
.k b{font-size:13pt}.k.hi b{color:#C23D27}
table{width:100%;border-collapse:collapse;margin:1.5mm 0;font-size:9pt}
th{background:#F2F5F9;color:#51657C;font-weight:600;text-align:start;padding:1.5mm 2mm;border-bottom:1px solid #D5DEE8}
td{padding:1.5mm 2mm;border-bottom:1px solid #EEF2F6;vertical-align:top}
tr{break-inside:avoid}
td:first-child{white-space:nowrap}
dl{display:grid;grid-template-columns:32mm 1fr;gap:1mm 3mm;margin:1.5mm 0}dt{color:#51657C}dd{margin:0}
.shot{max-width:100%;max-height:110mm;border:1px solid #D5DEE8;margin-top:2mm}
.case{break-before:page}
.muted{color:#51657C}
ul{margin:1mm 0;padding-inline-start:5mm}
footer{margin-top:8mm;color:#8EA2B8;font-size:8pt;border-top:1px solid #D5DEE8;padding-top:2mm}
"""


def _numbers() -> dict:
    try:
        return json.loads((RESULTS_DIR / "numbers.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _get(d: dict, path: str):
    """numbers.json keeps flat dotted keys, such as 'e3a.at_validation_threshold.dae2_mean.accuracy'."""
    return d.get(path)


def _pct(v, digits=1) -> str:
    return "n/a" if v is None else f"{v * 100:.{digits}f}%"


def _page(lang: str, title: str, body: str) -> str:
    L = T[lang]
    return (f'<!doctype html><html lang="{lang}" dir="{L["dir"]}"><head><meta charset="utf-8"><title>{e(title)}</title>'
            f"<style>{_font_css()}{CSS}</style></head><body>{body}<footer>{e(L['page'])}</footer></body></html>")


def _head(lang: str, title: str, sub: str) -> str:
    L = T[lang]
    h = (f'<div class="brand"><b>مرصاد Mirsad</b><span>{L["generated"].format(t=day(now()))}</span></div>'
         f"<h1>{e(title)}</h1><div class='muted'>{sub}</div>")
    if settings.public:
        h += f'<div class="note">{e(L["public"])}</div>'
    return h


def _case_section(case: dict, lang: str, level: str = "h2") -> str:
    L, thr = T[lang], case.get("threshold") or 0.8
    votes = case.get("votes") or {}
    above = sum(1 for v in votes.values() if v >= thr)
    h = []
    h.append(f"<dl><dt>{e(L['domain'])}</dt><dd>{ltr(case.get('display') or case.get('domain'))}</dd>"
             f"<dt>{e(L['link'])}</dt><dd>{ltr(case.get('url_redacted'))}</dd>"
             f"<dt>{e(L['found'])}</dt><dd>{e(L['ch'].get(case.get('channel'), case.get('channel')))}: "
             f"{ltr(case.get('channel_detail'))}</dd>"
             f"<dt>{e(L['first_seen'])}</dt><dd>{day(case.get('first_seen'))}</dd>"
             f"<dt>{e(L['status'])}</dt><dd>{e(L['st'].get(case.get('status'), case.get('status')))}</dd></dl>")
    h.append('<div class="grid">'
             f'<div class="k{" hi" if (case.get("risk") or 0) >= thr else ""}"><small>{e(L["risk"])}</small><b>{(case.get("risk") or 0):.2f}</b></div>'
             f'<div class="k"><small>{e(L["threshold"])}</small><b>{thr:.4g}</b></div>'
             f'<div class="k"><small>{e(L["imitates"])}</small><b>{e(case.get("imitates") or L["none"])}</b></div>'
             f'<div class="k"><small>{e(L["votes"])}</small><b>{e(L["above"].format(n=above))}</b></div></div>')
    if votes:
        h.append("<table><tr>" + "".join(f"<th>{e(ENSEMBLE_NAMES.get(k, k))}</th>" for k in votes) + f"<th>{e(L['mean'])}</th></tr><tr>"
                 + "".join(f"<td>{v:.2f}</td>" for v in votes.values())
                 + f"<td>{(case.get('model_mean') or 0):.2f}</td></tr></table>")
    if case.get("reasons"):
        h.append(f"<{level[0]}{int(level[1]) + 1}>{e(L['why'])}</{level[0]}{int(level[1]) + 1}><ul>"
                 + "".join(f"<li>{ltr(r) if lang == 'ar' else e(r)}</li>" for r in case["reasons"]) + "</ul>")
    s = case.get("summary")
    if s:
        first, second = (s.get("ar"), s.get("en")) if lang == "ar" else (s.get("en"), s.get("ar"))
        h.append(f"<h3>{e(L['summary'])} <span class='muted'>({e(L['summary_note'].format(m=s.get('model')))})</span></h3>"
                 f"<p>{e(first)}</p><p dir='{'ltr' if lang == 'ar' else 'rtl'}'>{e(second)}</p>")
    ev = case.get("evidence") or []
    h.append(f"<h3>{e(L['evidence'])}</h3>")
    if ev:
        h.append(f"<table><tr><th>{e(L['ex'])}</th><th>{e(L['obs'])}</th><th>{e(L['src'])}</th><th>{e(L['at'])}</th></tr>"
                 + "".join(f"<tr><td>{e(x['id'])}</td><td>{ltr(x['label'])}</td><td>{ltr(x['source'])}</td>"
                           f"<td>{day(x.get('at'))}</td></tr>" for x in ev) + "</table>")
    else:
        h.append(f"<p class='muted'>{e(L['no_ev'])}</p>")
    if any(x["kind"] in ("hosting", "whois") for x in ev):
        h.append(f"<h3>{e(L['hosting'])}</h3>")
        linked = case.get("linked") or []
        if linked:
            h.append(f"<p>{e(L['linked'])}</p><ul>"
                     + "".join(f"<li>{e(x['id'])} {ltr(x['domain'])} ({(x.get('risk') or 0):.2f}), "
                               f"{L['via'].get(x['via'], '{v}').format(v=ltr(x['shared']))}</li>" for x in linked) + "</ul>")
        else:
            h.append(f"<p class='muted'>{e(L['no_link'])}</p>")
    cap = case.get("capture") or {}
    h.append(f"<h3>{e(L['capture'])}</h3>")
    shot = _shot(cap.get("screenshot")) if cap.get("available") else None
    if cap.get("available") or cap.get("title"):
        h.append(f"<dl><dt>{e(L['cap_title'])}</dt><dd>{ltr(cap.get('title'))}</dd>"
                 f"<dt>{e(L['cap_final'])}</dt><dd>{ltr(cap.get('final_url'))}</dd>"
                 f"<dt>{e(L['forms'])}</dt><dd>{len(cap.get('forms') or [])}</dd></dl>")
        if shot:
            h.append(f'<img class="shot" alt="" src="{shot}">')
    else:
        h.append(f"<p class='muted'>{e(L['no_capture'])}</p>")
    if case.get("timeline"):
        h.append(f"<h3>{e(L['timeline'])}</h3><table>" + "".join(
            f"<tr><td style='width:42mm'>{day(x['at'])}</td><td>{ltr(x['label'])}</td></tr>" for x in case["timeline"]) + "</table>")
    h.append(f"<h3>{e(L['decisions'])}</h3>")
    dec = case.get("decisions") or []
    h.append("<table>" + "".join(f"<tr><td style='width:42mm'>{day(d['at'])}</td><td>{e(d['action'])}</td>"
                                 f"<td>{e(d['analyst'])}</td><td>{e(d.get('note'))}</td></tr>" for d in dec) + "</table>"
             if dec else f"<p class='muted'>{e(L['no_dec'])}</p>")
    return "".join(h)


def _shot(path: str | None) -> str | None:
    if not path:
        return None
    p = (CAPTURES / Path(path).name).resolve()
    if CAPTURES.resolve() not in p.parents or not p.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def case_html(store: Store, cid: str, lang: str = "en") -> str | None:
    lang = lang if lang in T else "en"
    case = build_case(store, cid)
    if not case:
        return None
    L = T[lang]
    thr = f"{case.get('threshold') or 0.8:.4g}"
    body = (_head(lang, f"{L['case_title']}: {cid}", ltr(case.get("display") or case.get("domain"))) + _case_section(case, lang)
            + f"<h2>{e(L['method'])}</h2><p>{e(L['method_text'].format(thr=thr))}</p>"
            + f"<h2>{e(L['legal'])}</h2><p>{e(L['legal_text'])}</p>")
    return _page(lang, f"Mirsad {cid}", body)


def summary_html(store: Store, lang: str = "en") -> str:
    lang = lang if lang in T else "en"
    L, k, n = T[lang], kpis(store), _numbers()
    thr = _get(n, "counts.threshold") or 0.8
    rows = store.rows("SELECT c.id FROM candidates c JOIN scores s ON s.candidate_id = c.id "
                      "WHERE s.risk >= s.threshold ORDER BY s.risk DESC, c.id")
    cases = [c for c in (build_case(store, r["id"]) for r in rows) if c]
    screened_all = (store.one("SELECT COALESCE(SUM(count), 0) AS n FROM screened") or {}).get("n", 0)
    status = {r["status"]: r["n"] for r in store.rows(
        "SELECT c.status, COUNT(*) AS n FROM candidates c JOIN scores s ON s.candidate_id = c.id "
        "WHERE s.risk >= s.threshold GROUP BY c.status")}
    by_ch: dict[str, int] = {}
    for c in cases:
        by_ch[c["channel"]] = by_ch.get(c["channel"], 0) + 1
    m = "e3a.at_validation_threshold.dae2_mean."
    body = [_head(lang, L["all_title"], "")]
    body.append(f"<h2>{e(L['totals'])}</h2><div class='grid'>"
                f"<div class='k'><small>{e(L['screened_all'])}</small><b>{screened_all:,}</b></div>"
                f"<div class='k'><small>{e(L['screened_today'])}</small><b>{k.get('links_screened_today', 0):,}</b></div>"
                f"<div class='k hi'><small>{e(L['flagged'])}</small><b>{len(cases)}</b></div>"
                f"<div class='k'><small>{e(L['awaiting'])}</small><b>{status.get('new', 0) + status.get('reviewing', 0) + status.get('assigned', 0)}</b></div>"
                f"<div class='k'><small>{e(L['confirmed'])}</small><b>{status.get('confirmed', 0)}</b></div>"
                f"<div class='k'><small>{e(L['dismissed'])}</small><b>{status.get('dismissed', 0)}</b></div></div>")
    if by_ch:
        body.append(f"<h3>{e(L['by_channel'])}</h3><table><tr>" + "".join(f"<th>{e(L['ch'].get(c, c))}</th>" for c in by_ch)
                    + "</tr><tr>" + "".join(f"<td>{v}</td>" for v in by_ch.values()) + "</tr></table>")
    body.append(f"<h2>{e(L['results'])}</h2><p>{e(L['results_text'])}</p><div class='grid'>"
                f"<div class='k'><small>{e(L['accuracy'])}</small><b>{_pct(_get(n, m + 'accuracy'))}</b></div>"
                f"<div class='k'><small>{e(L['recall'])}</small><b>{_pct(_get(n, m + 'fraud_class.recall'))}</b></div>"
                f"<div class='k'><small>{e(L['fpr'])}</small><b>{_pct(_get(n, m + 'false_positive_rate'), 2)}</b></div>"
                f"<div class='k'><small>{e(L['auc'])}</small><b>{(_get(n, m + 'roc_auc') or 0):.2f}</b></div></div>")
    body.append(f"<h2>{e(L['method'])}</h2><p>{e(L['method_text'].format(thr=f'{thr:.4g}'))}</p>")
    body.append(f"<h2>{e(L['cases'])}</h2>")
    if cases:
        body.append(f"<table><tr><th>{e(L['case'])}</th><th>{e(L['domain'])}</th><th>{e(L['imitates'])}</th>"
                    f"<th>{e(L['risk'])}</th><th>{e(L['channel'])}</th><th>{e(L['status'])}</th><th>{e(L['first_seen'])}</th></tr>"
                    + "".join(f"<tr><td>{e(c['id'])}</td><td>{ltr(c.get('display') or c['domain'])}</td><td>{e(c.get('imitates') or '')}</td>"
                              f"<td>{(c.get('risk') or 0):.2f}</td><td>{e(L['ch'].get(c['channel'], c['channel']))}</td>"
                              f"<td>{e(L['st'].get(c['status'], c['status']))}</td><td>{day(c.get('first_seen'))}</td></tr>"
                              for c in cases) + "</table>")
    else:
        body.append(f"<p class='muted'>{e(L['no_cases'])}</p>")
    body.append(f"<h2>{e(L['legal'])}</h2><p>{e(L['legal_text'])}</p><h2>{e(L['limits'])}</h2><p>{e(L['limits_text'])}</p>")
    for c in cases:
        body.append(f"<section class='case'><h2>{e(L['case'])} {e(c['id'])}: {ltr(c.get('display') or c['domain'])}</h2>{_case_section(c, lang, 'h3')}</section>")
    return _page(lang, "Mirsad summary report", "".join(body))


def to_pdf(page_html: str) -> bytes | None:
    """PDF from a report page, or None when Playwright or its Chromium is not installed."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    with _render_lock:  # one Chromium at a time keeps memory flat on a small server
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    ctx = browser.new_context(java_script_enabled=False)
                    page = ctx.new_page()
                    page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(("data:", "about:"))
                               else route.abort())
                    page.set_content(page_html, wait_until="load")
                    return page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
                finally:
                    browser.close()
        except Exception:
            return None


PRINT_HINT = ("<script>addEventListener('load',()=>setTimeout(()=>print(),300))</script>")
