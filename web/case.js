/* Mirsad case page (case.html): the evidence-sheet case file.
   Loaded before app.js; app.js calls window.MirsadCase() once the shared core is ready. */
window.MirsadCase = function () {
'use strict';
const M = window.Mirsad;
const {t, esc, ltr, smart, fmtTime, fmtDate, fmtWhen, dayKey, days, num, rk, votesAbove, splitDetail, chipText, imitatesHtml, highlightDomains, I, chIcon, votesHtml, stHtml, api, Pending} = M;
const $ = id => document.getElementById(id);
const C = {status: null, kpis: null, list: null, c: null, id: null, exportedAt: null, stampAnim: false};
const WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'];
const count = n => (M.S.lang === 'en' && n < 10 ? WORDS[n] : String(n));
const KIND = {search_ad: 'Search ad', certificate: 'Certificate', domain: 'Domain', page: 'Captured page', brand: 'Imitated brand', form_target: 'Form target', listing: 'Maps listing', phone: 'Phone', link: 'Link', host: 'Hosting', network: 'Linked cases'};
const KIND_SHORT = {search_ad: 'ad', certificate: 'certificate', domain: 'domain', page: 'page', brand: 'brand', form_target: 'form target', listing: 'listing', phone: 'phone', host: 'hosting', network: 'linked cases'};
const EV_KIND = {search_ad: ['search_ad', 'search_result'], certificate: ['certificate'], domain: ['domain'], brand: ['logo_match', 'brand'], form_target: ['form_target'], listing: ['listing'], phone: ['phone'], host: ['hosting']};
const RISK_KINDS = ['brand', 'form_target', 'phone', 'network'];
const latinRuns = M.latinRuns;

/* ---------------------------------------------------------------- boot */
C.id = (M.QS.get('id') || '').trim() || null;
$('list').addEventListener('click', e => {
  const a = e.target.closest('a.q'); if (!a || e.ctrlKey || e.metaKey || e.shiftKey) return;
  e.preventDefault(); go(a.dataset.id, true);
});
window.addEventListener('popstate', () => { const id = new URLSearchParams(location.search).get('id'); if (id && id !== C.id) go(id, false); });
document.addEventListener('keydown', e => {
  if (M.isTyping(e) || e.ctrlKey || e.metaKey || e.altKey || !$('auditDlg').hidden) return;
  if (e.key === 'j' || e.key === 'J') { e.preventDefault(); step(1); }
  else if (e.key === 'k' || e.key === 'K') { e.preventDefault(); step(-1); }
});
M.wireHold($('holdBtn'), {
  getState: () => M.holdState(C.c),
  onComplete: () => { if (!C.c) return; C.stampAnim = true; M.startPending(C.c.id, renderDecision, committed); },
  onUndo: () => { M.undoPending(); },
  onTap: () => { const h = $('holdHint'); h.textContent = t('Press and hold to confirm'); setTimeout(() => { h.textContent = ''; }, 2200); }
});
$('dismissBtn').addEventListener('click', () => simple('dismiss'));
$('assignBtn').addEventListener('click', () => simple('assign'));
$('exportBtn').addEventListener('click', async () => {
  if (!C.c) return;
  $('exportBtn').disabled = true;
  const pkg = await M.exportCase(C.c.id);
  if (pkg) { C.exportedAt = (pkg && pkg.generated_at) || new Date().toISOString(); renderReceipt(false); }
  $('exportBtn').disabled = false;
});
M.onLang(() => { M.renderStatusStrip(C.status); renderLedger(); renderList(); renderAll(); renderChart(); });
M.onRetry(() => load(true));
let rz = 0;
window.addEventListener('resize', () => { cancelAnimationFrame(rz); rz = requestAnimationFrame(renderChart); });
load(true);
setInterval(() => { if (!document.hidden) load(false); }, M.REFRESH_MS);

async function load(first) {
  const [st, kp, list] = await Promise.allSettled([api('GET', '/api/status'), api('GET', '/api/kpis'), api('GET', '/api/cases?status=all&channel=all&limit=50')]);
  if (st.status === 'fulfilled') { C.status = st.value; M.renderStatusStrip(C.status); }
  if (kp.status === 'fulfilled') { C.kpis = kp.value; renderLedger(); renderChart(); }
  if (list.status === 'fulfilled') C.list = list.value;
  if (!C.id && C.list && C.list.items.length) { C.id = C.list.items[0].id; history.replaceState(null, '', M.caseHref(C.id)); }
  renderList();
  if (C.id && !(Pending.id === C.id || Pending.busy === C.id)) await loadCase(C.id, !first);
}
async function loadCase(id, quiet) {
  try {
    const c = await api('GET', '/api/cases/' + encodeURIComponent(id));
    if (quiet && C.c && JSON.stringify(C.c) === JSON.stringify(c)) return;
    const changed = !C.c || C.c.id !== c.id;
    C.c = c;
    if (changed) { C.exportedAt = null; document.title = 'Mirsad case ' + c.id; }
    syncListStatus(c);
    renderAll();
  } catch (e) {
    if (!quiet) $('sheet').innerHTML = '<p class="loading">' + esc(e.status === 404 ? t('Case {id} was not found', {id}) : e.message) + '</p>';
  }
}
function go(id, push) {
  if (!id || id === C.id) return;
  C.id = id; C.c = null; C.stampAnim = false;
  if (push) history.pushState(null, '', M.caseHref(id));
  renderList();
  $('sheet').innerHTML = '<p class="loading">' + esc(t('Loading')) + '</p>';
  loadCase(id, false).then(() => $('sheet').focus({preventScroll: true}));
}
function step(d) {
  const items = C.list ? C.list.items : []; if (!items.length) return;
  let i = items.findIndex(x => x.id === C.id);
  i = Math.max(0, Math.min(items.length - 1, i < 0 ? 0 : i + d));
  go(items[i].id, true);
  const a = $('list').querySelector('a[data-id="' + CSS.escape(items[i].id) + '"]'); if (a) a.scrollIntoView({block: 'nearest'});
}
function syncListStatus(c) {
  const it = C.list && C.list.items.find(i => i.id === c.id);
  if (it && it.status !== c.status) { it.status = c.status; renderList(); }
}
async function simple(action) {
  if (!C.c) return;
  const b = $(action === 'dismiss' ? 'dismissBtn' : 'assignBtn'); b.disabled = true;
  try {
    const u = await M.decide(C.c.id, action, action === 'assign' ? 'Assigned to the duty analyst' : '');
    committedQuiet(u);
    M.toast(t(action === 'dismiss' ? '{id} dismissed' : '{id} assigned to the duty analyst', {id: u.id}));
  } catch (e) { M.toast(t('The decision was not saved: {e}', {e: e.message}), {error: true}); }
  b.disabled = false;
}
function committed(u) {
  if (!u || !u.id) { renderDecision(); return; }
  if (C.c && C.c.id === u.id) { C.c = u; C.stampAnim = false; renderAll(true); }
  syncListStatus(u);
  api('GET', '/api/kpis').then(k => { C.kpis = k; renderLedger(); }).catch(() => {});
}
function committedQuiet(u) { if (C.c && C.c.id === u.id) { C.c = u; renderAll(); } syncListStatus(u); api('GET', '/api/kpis').then(k => { C.kpis = k; renderLedger(); }).catch(() => {}); }

/* ---------------------------------------------------------------- top line and list */
function renderLedger() {
  const k = C.kpis; if (!k) return;
  const s = k.channel_split || {};
  const cols = [['search', 'Search', '#034A89'], ['certificates', 'Certificates', '#4F7FB0'], ['maps', 'Maps', '#8FB0D2'], ['feeds', 'Feeds', '#C4D4E4']];
  if (s.report) cols.push(['report', 'Reports', '#9AA7B5']);  // checked by hand or loaded as demo cases
  const ms = k.median_scoring_ms;
  $('ledger').innerHTML = '<span class="lab">' + esc(t('Today')) + '</span>' +
    '<span class="it">' + esc(t('Links screened')) + ' <b>' + num(k.links_screened_today) + '</b></span>' +
    '<span class="it">' + esc(t('Flagged')) + ' <b class="rk">' + num(k.flagged) + '</b></span>' +
    '<span class="it">' + esc(t('Awaiting review')) + ' <b>' + num(k.awaiting_review) + '</b></span>' +
    '<span class="it">' + esc(t('Confirmed')) + ' <b>' + num(k.confirmed) + '</b></span>' +
    '<span class="it">' + esc(t('Median scoring time')) + ' <b>' + (ms == null ? 'n/a' : Math.round(ms * 10) / 10) + '</b>ms</span>' +
    '<span class="lsplit"><span class="sl">' + esc(t("Today's {n} flags by channel", {n: num(k.flagged)})) + '</span><span class="stack" aria-hidden="true">' +
    cols.map(c => '<i style="flex:' + (s[c[0]] || 0) + ';background:' + c[2] + '"></i>').join('') + '</span>' +
    cols.map(c => '<span class="sk"><i style="background:' + c[2] + '" aria-hidden="true"></i>' + esc(t(c[1])) + ' <b>' + num(s[c[0]] || 0) + '</b></span>').join('') + '</span>';
}
function renderList() {
  const L = C.list; if (!L) return;
  const th = (C.status && C.status.model && C.status.model.threshold) || 0.8;
  const keep = $('list').scrollTop;
  $('lcount').textContent = t('{n} of {total} flagged, by risk', {n: L.items.length, total: num(C.kpis ? C.kpis.flagged : L.total)});
  $('list').innerHTML = L.items.map(o => {
    const n = votesAbove(o, th);
    return '<li><a class="q" href="' + esc(M.caseHref(o.id)) + '" data-id="' + esc(o.id) + '"' + (o.id === C.id ? ' aria-current="page"' : '') + '>' +
      '<span class="qr' + (o.risk >= th ? ' hi' : '') + '"><span class="rv">' + rk(o.risk) + '</span>' + votesHtml(n) + '</span>' +
      '<span class="qb"><span class="q1"><span class="qd">' + (o.channel === 'maps' ? esc(o.display) : ltr(o.display)) + '</span><span class="age">' + I.clock + esc(days(o.age_days)) + '</span></span>' +
      '<span class="qc">' + listDetail(o) + '</span>' +
      '<span class="qm"><span class="im">' + esc(t('Imitates')) + ' ' + imitatesHtml(o.imitates) + '</span>' + stHtml(o.status, 'qs') + '</span></span></a></li>';
  }).join('');
  $('list').scrollTop = keep;
}
function listDetail(o) {
  const [chip, rest] = splitDetail(o.channel_detail);
  if (/^site /.test(rest)) return esc(chipText(chip)) + ' <bdi>(' + esc(rest) + ')</bdi>';
  return esc(chipText(chip)) + (rest ? ', <bdi>' + esc(smart(rest)) + '</bdi>' : '');
}
function renderChart() {
  if (!C.kpis) return;
  M.renderBars($('lchart'), C.kpis, {w: 264, h: 78, base: 62, per: 6.4, bw: 7, peakLabel: true, firstStart: true, labelEvery: 8, labelGap: 14, dash: true});
}

/* ---------------------------------------------------------------- case file */
function renderAll(print) {
  const c = C.c; if (!c) return;
  const rb = $('reportBtn');
  if (rb) { rb.href = '/api/cases/' + encodeURIComponent(c.id) + '/report?lang=' + M.S.lang; rb.hidden = M.S.mode !== 'live'; }
  renderSheet(c);
  renderSummary(c);
  renderDecision();
  renderReceipt(print);
}
function nowIso() { return (C.status && C.status.now) || new Date().toISOString(); }
function renderSheet(c) {
  const th = c.threshold || 0.8;
  const n = votesAbove(c, th);
  const [chip] = splitDetail(c.channel_detail);
  const isMaps = c.channel === 'maps';
  const V = c.votes || {};
  const en = (k, l) => '<div class="en"><span>' + l + '</span><span class="lead"></span><b' + (V[k] >= th ? ' class="up"' : '') + '>' + rk(V[k]) + '</b></div>';
  let h = '<div class="hd"><div class="main">' +
    '<div class="ov"><span>' + esc(t('Case file')) + ' <b class="ltr" dir="ltr">' + esc(c.id) + '</b></span><span class="dotsep" aria-hidden="true"></span>' +
    '<span class="pill">' + chIcon(c.channel) + esc(chipText(chip)) + '</span>' + stHtml(c.status, 'pill') + '</div>' +
    '<h1 class="ctitle-serif">' + (isMaps ? esc(c.display) : ltr(c.display || c.domain)) + '</h1>' +
    '<div class="sub tn">' + (isMaps && c.listing ? esc(t('Category')) + ' <b>' + esc(c.listing.category || '') + '</b>' : esc(t('Imitates')) + ' ' + imitatesHtml(c.imitates)) +
    (c.age_days != null ? ' · ' + esc(t('first seen {d}', {d: days(c.age_days)})) : '') + (n != null ? ' · ' + esc(t('votes')) + ' <b>' + esc(t('{n} of 4', {n})) + '</b>' : '') + '</div></div>' +
    '<div class="ens"><div class="h">' + esc(t('Ensemble, score per model')) + '</div>' + en('adaboost', 'AdaBoost') + en('bagging', 'Bagging') + en('stacking', 'Stacking') + en('voting', 'Voting') + '</div>' +
    '<div class="bigrisk"><div class="l">' + esc(t('Final risk')) + '</div><div class="v' + (c.risk >= th ? '' : ' lo') + '">' + rk(c.risk) + '</div><div class="th">' + esc(t('threshold')) + ' ' + rk(th) + '</div></div></div>' +
    '<div class="rule2" aria-hidden="true"></div>';
  /* timeline */
  const tl = (c.timeline || []).slice().sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  const evById = {}; (c.evidence || []).forEach(e => { evById[e.id] = e; });
  h += '<section class="tl"><div class="secT"><h3>' + esc(t('Timeline')) + '</h3><span>' + esc(tl.length === 1 ? t('one event') : t('{n} events', {n: count(tl.length)})) + '</span></div>';
  if (tl.length) {
    const cols = tl.length;
    h += '<ol class="track" style="grid-template-columns:repeat(' + cols + ',minmax(0,1fr));--trk-end:calc((100% - ' + ((cols - 1) * 14) + 'px) / ' + cols + ' - 5px)">' + tl.map((e, i) => {
      const refs = String(e.evidence || '').split(/\s*,\s*/).filter(Boolean);
      const src = refs.map(r => evById[r] && evById[r].source).filter(Boolean)[0] || '';
      const when = dayKey(e.at) === dayKey(nowIso()) ? fmtTime(e.at) : fmtDate(e.at);
      return '<li class="tk' + (i === tl.length - 1 ? ' last' : '') + '"><div class="d"><span>' + esc(when) + '</span>' + (refs.length ? '<span class="ex">' + esc(refs.join(', ')) + '</span>' : '') + '</div>' +
        '<div class="w" dir="auto">' + esc(smart(e.label)) + '</div><div class="s" dir="auto">' + esc(src) + '</div></li>';
    }).join('') + '</ol>';
  } else h += '<p class="tk s" style="padding:0;color:var(--muted)">' + esc(t('No timeline for this case yet.')) + '</p>';
  h += '</section>';
  /* graph and capture */
  const kinds = [];
  (c.graph && c.graph.nodes || []).forEach(nd => { const k = KIND_SHORT[nd.kind] || nd.kind; if (kinds.indexOf(k) < 0) kinds.push(k); });
  kinds.sort((a, b) => (a === 'domain' ? -1 : b === 'domain' ? 1 : 0));
  const real = c.capture && c.capture.available && c.capture.screenshot && M.S.mode === 'live' && !M.S.mockParts.has('cases');
  h += '<div class="mid"><section class="graph"><div class="secT"><h3>' + esc(t('How the evidence connects')) + '</h3><span>' + esc(kinds.join(', ')) + '</span></div><div id="graphBox"></div></section>' +
    '<section class="capw"><div class="secT"><h3>' + esc(t('Captured page')) + '</h3><span>' + esc(t(real ? 'screenshot' : 'drawn copy')) + '</span></div>' + capture(c) + '</section></div>';
  /* evidence table */
  const ev = c.evidence || [];
  h += '<section class="evt"><div class="secT"><h3>' + esc(t('Evidence')) + '</h3><span>' + esc(ev.length === 1 ? t('one exhibit, with its source') : t('{n} exhibits, each with its source', {n: count(ev.length)})) + '</span></div>';
  h += ev.length ? '<table><thead><tr><th scope="col">' + esc(t('Exhibit')) + '</th><th scope="col">' + esc(t('Finding')) + '</th><th scope="col">' + esc(t('Source')) + '</th></tr></thead><tbody>' +
    ev.map(e => '<tr><td class="e"><span class="ex">' + esc(e.id) + '</span></td><td dir="auto">' + highlightDomains(e.label, c.domain) + '</td><td class="s" dir="auto">' + esc(e.source) + '</td></tr>').join('') + '</tbody></table>'
    : '<p style="color:var(--muted)">' + esc(t('No exhibits yet.')) + '</p>';
  h += '</section>';
  /* reasons */
  const rs = c.reasons || [];
  if (rs.length) {
    h += '<section class="rsn"><div class="secT"><h3>' + esc(t('Reasons, in plain words')) + '</h3><span>' + esc(t('why the model flagged it')) + '</span></div><ol class="rgrid">' +
      rs.map((r, i) => '<li><span class="n">' + (i + 1) + '</span><span dir="auto">' + esc(smart(r)) + '</span></li>').join('') + '</ol></section>';
  }
  if (c._partial) h += '<p class="notice">' + esc(t('Full detail for this case is not in the demo data set. The live service provides it.')) + '</p>';
  const keepTop = C.renderedId === c.id ? $('sheet').scrollTop : 0;
  $('sheet').innerHTML = h;
  $('sheet').scrollTop = keepTop; C.renderedId = c.id;
  $('graphBox').innerHTML = graphSvg(c);
  $('graphBox').parentNode.style.flexBasis = (C.graphW || 488) + 'px';
  if (document.fonts && document.fonts.status !== 'loaded') document.fonts.ready.then(() => { const b = $('graphBox'); if (b && C.c === c) b.innerHTML = graphSvg(c); });
  $('sheet').querySelectorAll('img[data-fallback]').forEach(img => img.addEventListener('error', () => {
    const fr = img.closest('.frame'); if (!fr) return;
    const sub = fr.parentNode.querySelector('.secT span'); if (sub) sub.textContent = t('drawn copy');
    fr.outerHTML = drawn(c);
  }, {once: true}));
}
function capture(c) {
  const cap = c.capture || {};
  if (!cap.available) return '<div class="frame" style="height:150px"><div class="none">' + esc(t('No capture yet')) + '</div></div>';
  let frame;
  if (cap.screenshot && M.S.mode === 'live' && !M.S.mockParts.has('cases')) {
    frame = '<div class="frame" style="height:150px"><div class="bar">' + I.lock + '<span>' + esc((cap.final_url || '').replace(/^https?:\/\//, '')) + '</span></div><img alt="' + esc(cap.title || 'Captured page') + '" src="' + esc(cap.screenshot) + '" data-fallback="1"></div>';
  } else frame = drawn(c);
  const when = fmtTime(cap.captured_at);
  const def = !cap.note || /^Captured in sandbox, no form submitted\.?$/.test(cap.note);
  return frame + '<div class="capt">' + esc(def ? t('Captured {t} in sandbox, no form submitted', {t: when}) : cap.note.replace(/^Captured /, 'Captured ' + when + ' ')) + '</div>';
}
function drawn(c) {
  /* Same drawn copy as the Watch screen, larger, with the exhibit number on the form. */
  const cap = c.capture || {};
  const f = (cap.forms && cap.forms[0]) || null;
  const fields = f ? f.fields || [] : [];
  const lab = s => ({'card number': 'Card number', expiry: 'MM / YY', cvv: 'CVV', 'full name': 'Full name', password: 'Password', email: 'Email', phone: 'Phone number', otp: 'One-time code', username: 'Username'}[String(s).toLowerCase()] || (s.charAt(0).toUpperCase() + s.slice(1)));
  let inputs = '', i = 0;
  if (fields.length % 2 === 1) { inputs += '<div class="inp">' + esc(lab(fields[0])) + '</div>'; i = 1; }
  for (; i < fields.length; i += 2) inputs += '<div class="inr"><div class="inp">' + esc(lab(fields[i])) + '</div>' + (fields[i + 1] ? '<div class="inp">' + esc(lab(fields[i + 1])) + '</div>' : '') + '</div>';
  const exId = (c.evidence || []).find(e => e.kind === 'form_target');
  return '<div class="frame" aria-hidden="true"><div class="bar">' + I.lock + '<span>' + esc((cap.final_url || c.url || '').replace(/^https?:\/\//, '').replace(/\/$/, '')) + '</span></div>' +
    '<div class="pgh">' + I.pageico + '<span>' + esc(cap.title || 'Page') + '</span></div><div class="pgb">' +
    (f && f.posts_to ? '<div class="amt"><span>Posts to</span><b>' + esc(f.posts_to) + '</b></div>' : '') +
    (inputs ? '<div class="form">' + (exId ? '<span class="exn">' + esc(exId.id) + '</span>' : '') + inputs + '</div><div class="pay">' + (fields.some(x => /card/i.test(x)) ? 'Pay now' : 'Continue') + '</div>' : '') + '</div></div>';
}

/* ---------------------------------------------------------------- evidence graph: simple layered layout */
const GIC = {
  search_ad: '<circle cx="5" cy="5" r="3.6"/><path d="M7.7 7.7l2.6 2.6"/>',
  certificate: '<rect x="1" y="1" width="9" height="6.5" rx="1"/><path d="M3.2 10.5l.8-3M7.8 10.5l-.8-3M3 3.5h5"/>',
  page: '<path d="M2.5 1h4.5l2.5 2.5v7h-7z"/><path d="M7 1v2.5h2.5M4 6.5h3.5M4 8.5h2.5"/>',
  brand: '<path d="M1 6V1h5l4.5 4.5L6 10z"/><circle cx="3.6" cy="3.6" r=".8"/>',
  form_target: '<path d="M1 5.5h7M5.5 3l2.5 2.5L5.5 8M10 1.5v8"/>',
  listing: '<path d="M5.5 10.5s3.5-3.2 3.5-5.7a3.5 3.5 0 0 0-7 0c0 2.5 3.5 5.7 3.5 5.7z"/><circle cx="5.5" cy="4.8" r="1.1"/>',
  phone: '<rect x="2.5" y=".5" width="6" height="10" rx="1.2"/><path d="M4.5 8.8h2"/>',
  host: '<rect x="1" y="1" width="9" height="3.6" rx=".8"/><rect x="1" y="6.4" width="9" height="3.6" rx=".8"/><path d="M3 2.8h.1M3 8.2h.1"/>',
  network: '<circle cx="2.2" cy="5.5" r="1.5"/><circle cx="8.8" cy="2.2" r="1.5"/><circle cx="8.8" cy="8.8" r="1.5"/><path d="M3.6 4.8 7.4 2.9M3.6 6.2l3.8 1.9"/>',
  domain: '<circle cx="5.5" cy="5.5" r="4.5"/><path d="M1 5.5h9M5.5 1c1.4 1.3 1.4 7.7 0 9M5.5 1c-1.4 1.3-1.4 7.7 0 9"/>'
};
const MCTX = document.createElement('canvas').getContext('2d');
function mw(s, font) { try { MCTX.font = font; return MCTX.measureText(String(s)).width; } catch (e) { return String(s).length * 6; } }
function fit(s, font, max) { s = String(s); if (mw(s, font) <= max) return s; while (s.length > 1 && mw(s + '.', font) > max) s = s.slice(0, -1); return s + '.'; }
function graphSvg(c) {
  const G = c.graph || {}; const nodes = (G.nodes || []).map(n => Object.assign({}, n)); const edges = (G.edges || []).filter(e => e.from !== e.to);
  if (!nodes.length) return '<p style="color:var(--muted);font-size:12px">' + esc(t('No graph for this case yet.')) + '</p>';
  const byId = {}; nodes.forEach(n => { byId[n.id] = n; n.in = []; n.out = []; });
  edges.forEach(e => { if (byId[e.from] && byId[e.to]) { byId[e.from].out.push(e.to); byId[e.to].in.push(e.from); } });
  /* longest-path layers */
  nodes.forEach(n => { n.layer = 0; });
  for (let k = 0; k < nodes.length; k++) edges.forEach(e => { const a = byId[e.from], b = byId[e.to]; if (a && b && b.layer < a.layer + 1) b.layer = Math.min(a.layer + 1, nodes.length); });
  /* pull sources next to their first child */
  nodes.forEach(n => { if (!n.in.length && n.out.length) n.layer = Math.max(0, Math.min(...n.out.map(o => byId[o].layer)) - 1); });
  let maxL = Math.max(...nodes.map(n => n.layer));
  /* fold the last layer under its single parent when the graph is deep, so it reads like the approved sheet */
  if (maxL >= 3) {
    const leaves = nodes.filter(n => n.layer === maxL);
    const parents = [...new Set(leaves.map(n => n.in.join('|')))];
    const p = leaves.length <= 2 && parents.length === 1 && leaves.every(l => l.in.length === 1) ? byId[leaves[0].in[0]] : null;
    if (p && p.layer === maxL - 1 && nodes.filter(n => n.layer === p.layer).length === 1) {
      leaves.forEach(l => { l.layer = p.layer; l.fold = true; });
      p.foldParent = true; maxL -= 1;
    }
  }
  const cols = []; for (let i = 0; i <= maxL; i++) cols.push([]);
  nodes.forEach(n => cols[n.layer].push(n));
  /* text and sizes */
  const evOf = n => { const ks = EV_KIND[n.kind] || []; return (c.evidence || []).find(e => ks.indexOf(e.kind) >= 0); };
  nodes.forEach(n => {
    n.main = n.kind === 'domain';
    const ev = evOf(n);
    n.ex = ev ? ev.id : '';
    if (n.main) { n.t = n.label; n.s = ev ? 'registered ' + fmtDate(ev.at) : t('Domain'); }
    else { n.t = t(KIND[n.kind] || n.kind); n.s = n.label; }
    n.risk = RISK_KINDS.indexOf(n.kind) >= 0;
    n.fs = (n.risk ? '600' : '400') + ' 11px Inter';
    n.need = Math.ceil(n.main ? Math.max(mw(n.t, '600 12.5px Inter'), mw(n.s, '400 11px Inter')) + 26 : Math.max(mw(n.t, '600 12px Inter') + 42, mw(n.s, n.fs) + 24));
  });
  const gapMin = 34;
  let widths = cols.map(col => Math.max(96, ...col.map(n => n.need)));
  const sum = widths.reduce((a, b) => a + b, 0);
  const W = Math.round(Math.min(560, Math.max(488, sum + gapMin * (cols.length - 1))));
  const room = W - gapMin * (cols.length - 1);
  if (sum > room) widths = widths.map(w => Math.max(84, w * room / sum));
  const used = widths.reduce((a, b) => a + b, 0);
  const gap = cols.length > 1 ? Math.min(60, (W - used) / (cols.length - 1)) : 0;
  const totalW = used + gap * (cols.length - 1);
  const x0 = (W - totalW) / 2;
  const NH = 40, top = 14;
  const maxN = Math.max(...cols.map(col => (col.some(n => n.fold) ? 3 : col.length)));
  const H = Math.max(174, top + maxN * NH + (maxN - 1) * 14 + 4);
  const span = H - top - 4 - NH;
  let x = x0;
  cols.forEach((col, ci) => {
    const w = widths[ci];
    if (col.some(n => n.fold)) {
      const p = col.find(n => n.foldParent), leaves = col.filter(n => n.fold);
      p.y = top + span / 2;
      if (leaves.length === 2) { leaves[0].y = top; leaves[1].y = top + span; }
      else leaves[0].y = top + span;
    } else {
      col.forEach((n, i) => { n.y = col.length === 1 ? top + span / 2 : top + i * span / (col.length - 1); });
    }
    col.forEach(n => { n.x = x; n.w = w; n.h = NH; n.ci = ci; });
    x += w + gap;
  });
  /* draw */
  const COL = {edge: '#8EA2B8', risk: '#FD614B', lab: '#51657C', labRisk: '#C23D27'};
  let g = '';
  const ah = (x, y, dir, risk) => {
    const col = risk ? COL.risk : COL.edge;
    if (dir === 'r') return '<path d="M' + (x - 6).toFixed(1) + ' ' + (y - 3.5).toFixed(1) + 'L' + x.toFixed(1) + ' ' + y.toFixed(1) + 'L' + (x - 6).toFixed(1) + ' ' + (y + 3.5).toFixed(1) + 'z" fill="' + col + '"/>';
    if (dir === 'l') return '<path d="M' + (x + 6).toFixed(1) + ' ' + (y - 3.5).toFixed(1) + 'L' + x.toFixed(1) + ' ' + y.toFixed(1) + 'L' + (x + 6).toFixed(1) + ' ' + (y + 3.5).toFixed(1) + 'z" fill="' + col + '"/>';
    if (dir === 'u') return '<path d="M' + (x - 3.5).toFixed(1) + ' ' + (y + 6).toFixed(1) + 'L' + x.toFixed(1) + ' ' + y.toFixed(1) + 'L' + (x + 3.5).toFixed(1) + ' ' + (y + 6).toFixed(1) + 'z" fill="' + col + '"/>';
    return '<path d="M' + (x - 3.5).toFixed(1) + ' ' + (y - 6).toFixed(1) + 'L' + x.toFixed(1) + ' ' + y.toFixed(1) + 'L' + (x + 3.5).toFixed(1) + ' ' + (y - 6).toFixed(1) + 'z" fill="' + col + '"/>';
  };
  const lab = (x, y, s, risk, anchor) => {
    const w = mw(s, (risk ? '600' : '500') + ' 11px Inter') + 8;
    const xl = anchor === 'end' ? x - w : anchor === 'start' ? x : x - w / 2;
    return '<rect x="' + xl.toFixed(1) + '" y="' + (y - 11).toFixed(1) + '" width="' + w.toFixed(1) + '" height="15" rx="3" fill="#FEFDFE"/>' +
      '<text x="' + (xl + w / 2).toFixed(1) + '" y="' + y.toFixed(1) + '" font-family="Inter" font-size="11" font-weight="' + (risk ? 600 : 500) + '" fill="' + (risk ? COL.labRisk : COL.lab) + '" text-anchor="middle">' + esc(s) + '</text>';
  };
  let labels = '';
  edges.forEach(e => {
    const a = byId[e.from], b = byId[e.to]; if (!a || !b) return;
    const risk = b.risk;
    const st = 'fill="none" stroke="' + (risk ? COL.risk : COL.edge) + '" stroke-width="' + (risk ? 1.6 : 1.3) + '"';
    if (a.ci === b.ci) {
      const cx = a.x + a.w / 2;
      const up = b.y < a.y;
      const y1 = up ? a.y : a.y + a.h, y2 = up ? b.y + b.h : b.y;
      g += '<path d="M' + cx.toFixed(1) + ' ' + y1.toFixed(1) + ' L' + cx.toFixed(1) + ' ' + y2.toFixed(1) + '" ' + st + '/>' + ah(cx, y2, up ? 'u' : 'd', risk);
      if (e.label) labels += lab(cx - 7, (y1 + y2) / 2 + 4, e.label, risk, 'end');
    } else {
      const fwd = b.ci > a.ci;
      const x1 = fwd ? a.x + a.w : a.x, x2 = fwd ? b.x : b.x + b.w;
      const y1 = a.y + a.h / 2 + (a.out.length > 1 && !a.foldParent ? (a.out.indexOf(b.id) - (a.out.length - 1) / 2) * 6 : 0);
      const y2 = b.y + b.h / 2 + (b.in.length > 1 ? (b.in.indexOf(a.id) - (b.in.length - 1) / 2) * 12 : 0);
      const dx = (x2 - x1) / 2;
      g += '<path d="M' + x1.toFixed(1) + ' ' + y1.toFixed(1) + ' C' + (x1 + dx).toFixed(1) + ' ' + y1.toFixed(1) + ' ' + (x2 - dx).toFixed(1) + ' ' + y2.toFixed(1) + ' ' + x2.toFixed(1) + ' ' + y2.toFixed(1) + '" ' + st + '/>' + ah(x2, y2, fwd ? 'r' : 'l', risk);
      if (e.label) labels += lab((x1 + x2) / 2, (y1 + y2) / 2 + (Math.abs(y2 - y1) < 4 ? -6 : 6), e.label, risk);
    }
  });
  g += labels;
  nodes.forEach(n => {
    const fill = n.main ? '#034A89' : '#FFFFFF';
    const stroke = n.main ? '#034A89' : n.risk ? '#FD614B' : '#CBD7E4';
    const tt = n.main ? fit(n.t, '600 12.5px Inter', n.w - 14) : fit(n.t, '600 12px Inter', n.w - 34);
    const ss = fit(n.s, n.main ? '400 11px Inter' : n.fs, n.w - 18);
    g += '<g><title>' + esc(n.t + ', ' + n.s) + '</title><rect x="' + (n.x + 0.75).toFixed(1) + '" y="' + (n.y + 0.75).toFixed(1) + '" width="' + (n.w - 1.5).toFixed(1) + '" height="' + (n.h - 1.5) + '" rx="8" fill="' + fill + '" stroke="' + stroke + '" stroke-width="' + (n.risk ? 1.3 : 1) + '"/>';
    if (n.main) {
      g += '<text x="' + (n.x + n.w / 2).toFixed(1) + '" y="' + (n.y + 17) + '" font-family="Inter" font-size="12.5" font-weight="600" fill="#FEFDFE" text-anchor="middle" direction="ltr">' + esc(tt) + '</text>';
      g += '<text x="' + (n.x + n.w / 2).toFixed(1) + '" y="' + (n.y + 32) + '" font-family="Inter" font-size="11" fill="#D3E2F2" text-anchor="middle">' + esc(ss) + '</text>';
    } else {
      g += '<g transform="translate(' + (n.x + 10).toFixed(1) + ' ' + (n.y + 7) + ')" fill="none" stroke="' + (n.risk ? '#C23D27' : '#51657C') + '" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">' + (GIC[n.kind] || GIC.page) + '</g>';
      g += '<text x="' + (n.x + 26).toFixed(1) + '" y="' + (n.y + 16) + '" font-family="Inter, Noto Sans Arabic" font-size="12" font-weight="600" fill="#0D2742">' + esc(tt) + '</text>';
      g += '<text x="' + (n.x + 10).toFixed(1) + '" y="' + (n.y + 31) + '" font-family="Inter" font-size="11" font-weight="' + (n.risk ? 600 : 400) + '" fill="' + (n.risk ? '#C23D27' : '#51657C') + '" direction="ltr">' + esc(ss) + '</text>';
    }
    if (n.ex) {
      const left = n.ci === 0 && cols[0].indexOf(n) > 0;
      g += '<text x="' + (left ? n.x + 4 : n.x + n.w - 4).toFixed(1) + '" y="' + (n.y - 3) + '" font-family="Inter" font-size="11" font-weight="600" fill="#C23D27" text-anchor="' + (left ? 'start' : 'end') + '">' + esc(n.ex) + '</text>';
    }
    g += '</g>';
  });
  C.graphW = W;
  const desc = edges.map(e => (byId[e.from] ? byId[e.from].t : e.from) + ' ' + (e.label || 'to') + ' ' + (byId[e.to] ? byId[e.to].t : e.to)).join('; ');
  return '<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(desc) + '" style="direction:ltr">' + g + '</svg>';
}

/* ---------------------------------------------------------------- right column */
function renderSummary(c) {
  const s = c.summary; const box = $('sumCard');
  if (!s || (!s.en && !s.ar)) { box.hidden = true; return; }
  box.hidden = false;
  const note = !s.note || s.note === 'model writes, does not decide' ? t('model writes, does not decide') : s.note;
  box.setAttribute('aria-label', t('Summary by {m}', {m: s.model || 'Jais'}));
  box.innerHTML = '<div class="jl"><span><b>' + esc(t('Summary by {m}', {m: s.model || 'Jais'})) + '</b>, ' + esc(note) + '</span></div>' +
    (s.en ? '<div class="jen" lang="en" dir="ltr">' + esc(smart(s.en)) + '</div>' : '') + (s.ar ? '<div class="jar" lang="ar" dir="rtl">' + latinRuns(s.ar) + '</div>' : '');
}
function renderDecision() {
  const c = C.c; if (!c) return;
  const state = M.holdState(c);
  M.paintHold($('holdBtn'), state, M.lastDecisionTime(c, 'confirm'));
  const busy = state === 'pending' || state === 'busy';
  $('dismissBtn').disabled = busy || c.status === 'dismissed';
  $('assignBtn').disabled = busy;
  $('decPill').innerHTML = stHtml(c.status, 'pill');
  /* stamp */
  const z = $('stampz');
  const showConfirmed = state === 'pending' || state === 'busy' || c.status === 'confirmed';
  const showDismissed = !showConfirmed && c.status === 'dismissed';
  $('stampWord').textContent = t(showDismissed ? 'DISMISSED' : 'CONFIRMED');
  $('stampId').textContent = c.id;
  $('stamp').classList.toggle('dismissed', showDismissed);
  ['stampWord', 'stampId'].forEach(id => $(id).setAttribute('fill', showDismissed ? '#51657C' : '#034A89'));
  $('stamp').querySelectorAll('rect').forEach(r => r.setAttribute('stroke', showDismissed ? '#51657C' : '#034A89'));
  const was = z.classList.contains('landed');
  z.classList.toggle('landed', showConfirmed || showDismissed);
  if (showConfirmed && !was && C.stampAnim) { z.classList.remove('animate'); void z.offsetWidth; z.classList.add('animate'); C.stampAnim = false; }
  if (!showConfirmed && !showDismissed) z.classList.remove('animate');
  /* history */
  const ds = (c.decisions || []).slice(-3).reverse();
  $('hist').innerHTML = ds.length
    ? ds.map(d => '<li><span class="tn">' + esc(fmtWhen(d.at, nowIso())) + '</span><span><b>' + esc(t({confirm: 'Confirmed', dismiss: 'Dismissed', assign: 'Assigned', reviewing: 'Marked reviewing'}[d.action] || d.action)) + '</b>, ' + esc(d.analyst === 'Duty analyst' ? t('Duty analyst') : d.analyst || '') + '</span></li>').join('')
    : '<li>' + esc(t('The stamp lands here when the hold completes.')) + '</li>';
  renderReceipt(false);
}
const cap1 = s => (/^[a-z][a-z ]+$/.test(s) ? s.charAt(0).toUpperCase() + s.slice(1) : s);
function renderReceipt(print) {
  const c = C.c; if (!c) return;
  const state = M.holdState(c);
  const confirmed = c.status === 'confirmed';
  const ev = c.evidence || [];
  const exRange = ev.length ? (ev.length > 1 ? ev[0].id + ' to ' + ev[ev.length - 1].id : ev[0].id) : 'n/a';
  const cap = c.capture && c.capture.available ? t('{t}, sandbox', {t: fmtTime(c.capture.captured_at)}) : 'n/a';
  const targets = c.exports && c.exports.length ? c.exports : Object.keys(M.EXPORT_LABEL);
  let ft, ok = false;
  if (C.exportedAt) { ft = t('Exported {t}', {t: fmtTime(C.exportedAt)}); ok = true; }
  else if (confirmed) { ft = t('Confirmed {t}, ready to export', {t: M.lastDecisionTime(c, 'confirm')}).replace(' ,', ','); ok = true; }
  else ft = t('Waiting for hold to confirm');
  void state;
  const r = $('receipt');
  r.innerHTML = '<div class="rh"><span lang="ar" class="ar">مرصاد</span> ' + esc(t('Mirsad evidence export')) + '</div><div class="rs2">' + esc(t('Case')) + ' ' + esc(c.id) + '</div><div class="cut"></div>' +
    '<div class="rkv"><span>' + esc(t('Domain')) + '</span>' + ltr(c.domain || c.display) + '</div>' +
    '<div class="rkv"><span>' + esc(t('Final risk')) + '</span><b class="tn" style="font-weight:600">' + rk(c.risk) + '</b></div>' +
    '<div class="rkv"><span>' + esc(t('Exhibits')) + '</span>' + esc(exRange) + '</div>' +
    '<div class="rkv"><span>' + esc(t('Captured')) + '</span><span class="tn" style="color:inherit">' + esc(cap) + '</span></div><div class="cut"></div>' +
    targets.map(k => '<div class="to"><i class="' + (confirmed || C.exportedAt ? 'on' : '') + '" aria-hidden="true"></i>' + esc(cap1(t(M.EXPORT_LABEL[k] || k))) + '</div>').join('') +
    '<div class="cut"></div><div class="ft' + (ok ? ' ok' : '') + '">' + esc(ft) + '</div>';
  if (print) { r.classList.remove('printing'); void r.offsetWidth; r.classList.add('printing'); }
  $('exportBtn').classList.toggle('primary', confirmed);
}
};
