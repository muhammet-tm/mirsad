/* Mirsad dashboard.
   Part 1: shared core used by both pages (API with automatic demo fallback, language, Gulf Standard
   Time formatting, icons, hold to confirm, toasts, top bar, check a link, audit log).
   Part 2: the Watch screen (index.html). The case page logic lives in case.js.
   Plain JavaScript, no build step. */
(function () {
'use strict';

/* ================================================================ mode and config */
const QS = new URLSearchParams(location.search);
const FILE = location.protocol === 'file:';
const FORCED_MOCK = FILE || QS.get('mock') === '1';
const ANALYST = 'Duty analyst';
const GST_MS = 4 * 3600 * 1000;
const HOLD_MS = 1500;
const UNDO_S = 5;
const REFRESH_MS = 15000;
const CHANNELS = ['search', 'certificates', 'maps', 'feeds'];
const EXPORT_LABEL = {registrar_abuse_report: 'registrar abuse report', aeda: 'aeDA', police_blocking_request: 'police blocking request'};

const S = {mode: FORCED_MOCK ? 'mock' : 'unknown', mockParts: new Set(), lang: 'en', langCbs: [], retryCbs: [], conn: true};

/* ================================================================ language */
const AR = {
  'Watch': 'المراقبة', 'Cases': 'القضايا', 'Search monitor': 'مراقبة البحث', 'Maps check': 'فحص الخرائط',
  'Early warning': 'الإنذار المبكر', 'Model': 'النموذج', 'Audit log': 'سجل التدقيق', 'Settings': 'الإعدادات',
  'Duty analyst': 'المحلل المناوب', 'Cybercrime unit (demo)': 'وحدة الجرائم الإلكترونية (تجريبي)',
  'Check a link': 'افحص رابطًا', 'Check a link or open a case by number': 'افحص رابطًا أو افتح قضية برقمها',
  'Primary': 'الرئيسية', 'Language': 'اللغة', 'English': 'الإنجليزية', 'Arabic': 'العربية',
  'Skip to the watch queue': 'انتقل إلى قائمة المراقبة', 'Skip to the case file': 'انتقل إلى ملف القضية',
  'Live': 'مباشر', 'live': 'مباشر', 'Synced': 'متزامن', 'synced': 'تمت المزامنة', 'Idle': 'خامل', 'Error': 'خطأ', 'Off': 'متوقف',
  'last run {t}': 'آخر تشغيل {t}', 'synced {t}': 'تمت المزامنة {t}', 'threshold {v}': 'العتبة {v}',
  'Certificate stream': 'تدفق الشهادات', 'Feeds': 'الموجزات',
  'Demo data': 'بيانات تجريبية', 'Connection lost, showing the last data': 'انقطع الاتصال، تُعرض آخر البيانات',
  'Demo data. The live service did not answer; select to retry.': 'بيانات تجريبية. لم تستجب الخدمة المباشرة؛ اختر لإعادة المحاولة.',
  'Demo data, as requested by the address.': 'بيانات تجريبية بطلب من العنوان.',
  'Demo data, because the page was opened from a file.': 'بيانات تجريبية لأن الصفحة فُتحت من ملف.',
  'Demo data for: {list}. Select to retry the live service.': 'بيانات تجريبية لـ: {list}. اختر لإعادة محاولة الخدمة المباشرة.',
  'Links screened today': 'روابط تم فحصها اليوم', 'Flagged': 'مشبوهة', 'Awaiting review': 'بانتظار المراجعة',
  'Confirmed': 'مؤكدة', 'Median scoring time': 'الزمن الوسيط للتقييم', 'ms': 'ملّي ثانية', 'Key figures for today': 'أرقام اليوم الرئيسية',
  'Watch queue': 'قائمة المراقبة', '{n} of {total} flagged today': '{n} من {total} مشبوهة اليوم', 'Risk': 'الخطورة',
  'Sorted by risk, highest first': 'مرتبة حسب الخطورة، الأعلى أولًا', 'Filter by channel': 'تصفية حسب القناة',
  'All': 'الكل', 'Search': 'البحث', 'Certificates': 'الشهادات', 'Maps': 'الخرائط',
  'Votes: AdaBoost, Bagging, Stacking, Voting': 'الأصوات: AdaBoost وBagging وStacking وVoting', 'First seen': 'أول ظهور',
  '{n} of 4': '{n} من 4', 'Imitates': 'ينتحل', 'none': 'لا شيء',
  'New': 'جديدة', 'Reviewing': 'قيد المراجعة', 'Dismissed': 'مستبعدة',
  'Search ad': 'إعلان بحث', 'Search result': 'نتيجة بحث', 'New certificate': 'شهادة جديدة', 'Maps listing': 'إعلان على الخريطة',
  'Feed': 'موجز', 'Report': 'بلاغ', 'Checked on demand': 'فحص عند الطلب',
  'No cases in this channel today.': 'لا توجد قضايا في هذه القناة اليوم.', 'Loading': 'جارٍ التحميل',
  'Case': 'القضية', 'Case file': 'ملف القضية', 'Open case file': 'فتح ملف القضية',
  'first seen {d}': 'أول ظهور منذ {d}', 'votes': 'الأصوات', 'Category': 'الفئة', 'phone on {n} listings': 'الهاتف في {n} إعلانات',
  'Final risk': 'الخطورة النهائية', 'Why it was flagged': 'سبب الإشارة', 'Evidence': 'الأدلة', '{n} items': '{n} عناصر',
  'Captured {t} in sandbox, no form submitted': 'التُقطت {t} في بيئة معزولة، دون إرسال أي نموذج',
  'No capture yet': 'لا توجد لقطة بعد', 'Summary by {m}': 'ملخص من {m}', 'model writes, does not decide': 'النموذج يكتب ولا يقرر',
  'Hold to confirm and export evidence': 'اضغط مطولًا للتأكيد وتصدير الأدلة', 'Press and hold to confirm': 'اضغط مطولًا للتأكيد',
  'Undo, confirming in {n} s': 'تراجع، التأكيد خلال {n} ث', 'Saving the decision': 'جارٍ حفظ القرار', 'Confirmed {t}': 'تم التأكيد {t}',
  'Dismiss': 'استبعاد', 'Assign': 'إسناد', 'Exports to': 'يُصدَّر إلى',
  'registrar abuse report': 'بلاغ إساءة لدى المسجل', 'aeDA': 'aeDA', 'police blocking request': 'طلب حجب من الشرطة',
  'Full detail for this case is not in the demo data set. The live service provides it.': 'التفاصيل الكاملة لهذه القضية غير موجودة في البيانات التجريبية. توفرها الخدمة المباشرة.',
  'listings checked': 'إعلانًا تم فحصها', 'Mismatch': 'عدم تطابق', 'Verified': 'موثّق', 'Same phone number': 'رقم هاتف مشترك',
  'Same phone on {n} listings': 'الهاتف نفسه في {n} إعلانات', 'Stylized map, not to scale': 'خريطة مبسطة، ليست بمقياس رسم',
  'Zoom in': 'تكبير', 'Zoom out': 'تصغير', 'Show verified listings': 'إظهار الإعلانات الموثقة', 'Center on the selected listing': 'توسيط على الإعلان المحدد',
  'Reset the map view': 'إعادة ضبط الخريطة', 'Map of Maps check listings around Abu Dhabi': 'خريطة إعلانات فحص الخرائط حول أبوظبي',
  'Map listing {id}, {cat}, risk {r}': 'إعلان على الخريطة {id}، {cat}، الخطورة {r}',
  'Flagged links per hour': 'الروابط المشبوهة في الساعة', 'last 24 hours': 'آخر 24 ساعة', 'Peak {n} at {t}': 'الذروة {n} عند {t}',
  'Channel split': 'التوزيع حسب القناة', "today's {n} flags": '{n} إشارة اليوم',
  'Mirsad prototype. Detection engine: DaE2 (Omolara and Alawida, 2025).': 'نموذج أولي لمرصاد. محرك الكشف: DaE2 (Omolara وAlawida، 2025).',
  'All times Gulf Standard Time (UTC+4)': 'جميع الأوقات بتوقيت الخليج (UTC+4)',
  '{id} confirmed. Evidence package ready.': 'تم تأكيد {id}. حزمة الأدلة جاهزة.', 'Download': 'تنزيل', 'Undo': 'تراجع',
  'Confirming {id} in {n} s': 'تأكيد {id} خلال {n} ث', 'Confirmation of {id} undone': 'أُلغي تأكيد {id}',
  '{id} dismissed': 'تم استبعاد {id}', '{id} assigned to the duty analyst': 'أُسندت {id} إلى المحلل المناوب',
  'The decision was not saved: {e}': 'لم يُحفظ القرار: {e}', 'Export failed: {e}': 'فشل التصدير: {e}',
  'Evidence package for {id} downloaded': 'تم تنزيل حزمة أدلة {id}', 'Case {id} was not found': 'لم يُعثر على القضية {id}',
  'Not part of this prototype': 'ليس جزءًا من هذا النموذج الأولي',
  'Checking': 'جارٍ الفحص', 'Above threshold {v}': 'فوق العتبة {v}', 'Below threshold {v}': 'دون العتبة {v}',
  'Close': 'إغلاق', 'Open the case': 'فتح القضية', 'Not a link this tool can check.': 'ليس رابطًا يمكن فحصه.',
  'Demo estimate from simple rules. The DaE2 model scores links only on the live service.': 'تقدير تجريبي من قواعد بسيطة. يقيّم نموذج DaE2 الروابط على الخدمة المباشرة فقط.',
  'Matches case {id} in the queue.': 'يطابق القضية {id} في القائمة.', 'The check failed: {e}': 'فشل الفحص: {e}',
  'Time': 'الوقت', 'Actor': 'المنفّذ', 'Action': 'الإجراء', 'Target': 'الهدف', 'Detail': 'التفاصيل', 'Append-only record of views, decisions, and exports': 'سجل إلحاقي فقط للمشاهدات والقرارات والتصدير',
  /* case page */
  'Ensemble, score per model': 'المجموعة، النتيجة لكل نموذج', 'threshold': 'العتبة', 'Timeline': 'التسلسل الزمني',
  '{n} events': '{n} أحداث', 'one event': 'حدث واحد', 'one exhibit, with its source': 'دليل واحد مع مصدره', 'How the evidence connects': 'كيف ترتبط الأدلة', 'Captured page': 'الصفحة الملتقطة',
  'drawn copy': 'نسخة مرسومة', 'screenshot': 'لقطة شاشة', '{n} exhibits, each with its source': '{n} أدلة، لكل منها مصدره',
  'Exhibit': 'الدليل', 'Finding': 'النتيجة', 'Source': 'المصدر', 'Reasons, in plain words': 'الأسباب بلغة واضحة',
  'why the model flagged it': 'لماذا أشار إليه النموذج', 'Decision': 'القرار',
  'The stamp lands here when the hold completes.': 'يظهر الختم هنا عند اكتمال الضغط المطوّل.', 'No decisions yet': 'لا توجد قرارات بعد',
  'Export receipt': 'إيصال التصدير', 'preview, prints after confirm': 'معاينة، يُطبع بعد التأكيد', 'Export evidence package': 'تصدير حزمة الأدلة',
  'Waiting for hold to confirm': 'بانتظار الضغط المطوّل للتأكيد', 'Confirmed {t}, ready to export': 'أُكّد {t}، جاهز للتصدير', 'Exported {t}': 'صُدّر {t}',
  'Mirsad evidence export': 'تصدير أدلة مرصاد', 'Domain': 'النطاق', 'Exhibits': 'الأدلة', 'Captured': 'الالتقاط', '{t}, sandbox': '{t}، بيئة معزولة',
  'Today': 'اليوم', 'Links screened': 'روابط تم فحصها', "Today's {n} flags by channel": '{n} إشارة اليوم حسب القناة',
  'Activity': 'النشاط', 'flagged links per hour, last 24 hours': 'الروابط المشبوهة في الساعة، آخر 24 ساعة',
  '{n} of {total} flagged, by risk': '{n} من {total} مشبوهة، حسب الخطورة', 'Imitated brand': 'العلامة المنتحلة', 'Certificate': 'شهادة',
  'Form target': 'وجهة النموذج', 'Phone': 'الهاتف', 'Page': 'الصفحة', 'Link': 'رابط', 'Domain registered': 'تسجيل النطاق',
  'No graph for this case yet.': 'لا يوجد مخطط لهذه القضية بعد.', 'No timeline for this case yet.': 'لا يوجد تسلسل زمني لهذه القضية بعد.',
  'No exhibits yet.': 'لا توجد أدلة بعد.', 'confirm': 'تأكيد', 'dismiss': 'استبعاد', 'assign': 'إسناد', 'reviewing': 'قيد المراجعة',
  'History': 'السجل', 'Assigned': 'أُسندت', 'Marked reviewing': 'وُضعت قيد المراجعة', 'Back to the watch screen': 'العودة إلى شاشة المراقبة', 'CONFIRMED': 'مؤكدة', 'DISMISSED': 'مستبعدة'
};
const CHIP_AR = {'Search ad': 'إعلان بحث', 'Search result': 'نتيجة بحث', 'New certificate': 'شهادة جديدة', 'Maps listing': 'إعلان على الخريطة', 'Feed (OpenPhish)': 'موجز (OpenPhish)', 'Feed (URLhaus)': 'موجز (URLhaus)'};
const MON = {en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
             ar: ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']};

function t(key, vars) {
  let s = (S.lang === 'ar' && AR[key] != null) ? AR[key] : key;
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] != null ? vars[k] : m));
  return s;
}
function setLang(l, silent) {
  S.lang = l === 'ar' ? 'ar' : 'en';
  const h = document.documentElement;
  h.lang = S.lang; h.dir = S.lang === 'ar' ? 'rtl' : 'ltr';
  try { localStorage.setItem('mirsad.lang', S.lang); } catch (e) { /* storage blocked: keep in memory */ }
  applyStatic(document);
  document.querySelectorAll('[data-lang]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.lang === S.lang)));
  if (!silent) S.langCbs.forEach(cb => cb());
}
function applyStatic(root) {
  root.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll('[data-i18n-aria]').forEach(el => el.setAttribute('aria-label', t(el.dataset.i18nAria)));
  root.querySelectorAll('[data-i18n-title]').forEach(el => el.setAttribute('title', t(el.dataset.i18nTitle)));
  root.querySelectorAll('[data-i18n-ph]').forEach(el => el.setAttribute('placeholder', t(el.dataset.i18nPh)));
}

/* ================================================================ formatting */
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const ltr = s => '<bdi class="ltr" dir="ltr">' + esc(s) + '</bdi>';
/* Latin runs (domains, feed and model names) inside Arabic text: isolate each run so the browser keeps it
   left to right and never breaks a domain at its hyphen. The text is escaped first. */
const latinRuns = text => esc(text).replace(/[A-Za-z0-9][A-Za-z0-9._\/()&;: -]*[A-Za-z0-9)]/g,
  m => '<bdi class="ltr nw" dir="ltr">' + m.trim() + '</bdi>' + (m.endsWith(' ') ? ' ' : ''));
const pad = n => String(n).padStart(2, '0');
function gst(iso) { const ms = Date.parse(iso); return isNaN(ms) ? null : new Date(ms + GST_MS); }
function fmtTime(iso) { const d = gst(iso); return d ? pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes()) : ''; }
function fmtDate(iso) { const d = gst(iso); return d ? d.getUTCDate() + ' ' + MON[S.lang][d.getUTCMonth()] + ' ' + d.getUTCFullYear() : ''; }
function dayKey(iso) { const d = gst(iso); return d ? d.toISOString().slice(0, 10) : ''; }
function fmtWhen(iso, nowIso) { return dayKey(iso) && dayKey(iso) === dayKey(nowIso) ? fmtTime(iso) : fmtDate(iso) + ', ' + fmtTime(iso); }
function days(n) {
  if (n == null) return '';
  n = Math.round(n);
  if (S.lang === 'ar') return n === 0 ? 'أقل من يوم' : n === 1 ? 'يوم واحد' : n === 2 ? 'يومان' : n <= 10 ? n + ' أيام' : n + ' يومًا';
  return n === 0 ? 'under a day' : n === 1 ? '1 day' : n + ' days';
}
const num = n => (n == null || isNaN(n) ? 'n/a' : Number(n).toLocaleString('en-US'));
const rk = r => (r == null || isNaN(r) ? 'n/a' : Number(r).toFixed(2));
const smart = s => String(s == null ? '' : s).replace(/"([^"]*)"/g, '“$1”').replace(/(^|[\s(])'([^']*)'/g, '$1‘$2’');
const host = u => { try { return new URL(/^[a-z]+:\/\//i.test(u) ? u : 'https://' + u).hostname.toLowerCase(); } catch (e) { return ''; } };
const clone = o => (o == null ? o : JSON.parse(JSON.stringify(o)));
const statusLabel = s => t({new: 'New', reviewing: 'Reviewing', confirmed: 'Confirmed', dismissed: 'Dismissed'}[s] || (s ? s[0].toUpperCase() + s.slice(1) : ''));
const votesAbove = (c, th) => (c.votes_above != null ? c.votes_above : c.votes ? Object.values(c.votes).filter(v => v >= (th || 0.8)).length : null);
function splitDetail(d) {
  const s = String(d || ''); const i = s.indexOf(', ');
  return i < 0 ? [s, ''] : [s.slice(0, i), s.slice(i + 2)];
}
function chipText(label) { return S.lang === 'ar' && CHIP_AR[label] ? CHIP_AR[label] : label; }
function imitatesHtml(s) {
  if (!s) return '<b>' + esc(t('none')) + '</b>';
  const i = s.indexOf(' (');
  const head = i < 0 ? s : s.slice(0, i);
  return '<b><bdi>' + esc(head === 'none' ? t('none') : head) + '</bdi></b>' + (i < 0 ? '' : ' <bdi>' + esc(s.slice(i + 1)) + '</bdi>');
}
function highlightDomains(text, own) {
  const re = /\b((?:[a-z0-9-]+\.)+[a-z]{2,})\b/gi;
  return esc(smart(text)).replace(re, m => (m.toLowerCase() === String(own || '').toLowerCase() ? ltr(m) : '<span class="hl">' + ltr(m) + '</span>'));
}

/* ================================================================ icons */
const I = {
  search: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14"/></svg>',
  certificates: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><rect x="2.5" y="2.5" width="11" height="8" rx="1.5"/><path d="M5.5 13.5 6.5 10.5M10.5 13.5 9.5 10.5M5.5 5.5h5M5.5 7.5h3"/></svg>',
  maps: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 14s4.5-4.2 4.5-7.5a4.5 4.5 0 0 0-9 0C3.5 9.8 8 14 8 14z"/><circle cx="8" cy="6.5" r="1.5"/></svg>',
  feeds: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 3.5a9 9 0 0 1 9 9M3.5 7.5a5 5 0 0 1 5 5"/><circle cx="4" cy="12" r="1"/></svg>',
  report: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 14V2.5M3.5 3h8l-1.5 3 1.5 3h-8"/></svg>',
  clock: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.5"/><path d="M8 5v3.2l2 1.3"/></svg>',
  card: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="4" width="12" height="8.5" rx="1.5"/><path d="M2 7h12M4.5 10h2.5"/></svg>',
  tag: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 8.5V3h5.5l5.5 5.5-5 5z"/><circle cx="5.5" cy="6" r="1"/></svg>',
  phone: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><rect x="4.5" y="1.5" width="7" height="13" rx="1.5"/><path d="M7 12.5h2"/></svg>',
  alert: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.5 14 13H2z"/><path d="M8 6.5v3M8 11.2v.1"/></svg>',
  ext: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M9 3h4v4M13 3 7.5 8.5M11 9.5V13H3V5h3.5"/></svg>',
  x: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8"/></svg>',
  user: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="5.5" r="2.5"/><path d="M3 13.5c.6-2.6 2.6-4 5-4s4.4 1.4 5 4"/></svg>',
  down: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true" style="width:12px;height:12px"><path d="M8 2.5v7M5 6.5l3 3 3-3M3 11.5v2h10v-2"/></svg>',
  shot: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><rect x="2.5" y="3.5" width="11" height="9" rx="1.5"/><path d="M2.5 6h11"/></svg>',
  lines: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true" style="width:12px;height:12px"><path d="M3 4h10M3 7h10M3 10h6"/></svg>',
  sort: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true" style="width:12px;height:12px"><path d="M5 3v10M2.5 10.5 5 13l2.5-2.5M11 13V3M8.5 5.5 11 3l2.5 2.5"/></svg>',
  sync: '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true" style="width:13px;height:13px;color:#034A89"><path d="M13 5.5A5.5 5.5 0 0 0 3.2 4.6M3 2.5v2.4h2.4M3 10.5a5.5 5.5 0 0 0 9.8.9M13 13.5v-2.4h-2.4"/></svg>',
  lock: '<svg viewBox="0 0 10 10" aria-hidden="true"><rect x="2" y="4.5" width="6" height="4.5" rx="1" fill="none" stroke="#3F5369" stroke-width="1.2"/><path d="M3.4 4.5V3.4a1.6 1.6 0 0 1 3.2 0v1.1" fill="none" stroke="#3F5369" stroke-width="1.2"/></svg>',
  pageico: '<svg width="13" height="13" viewBox="0 0 14 14" aria-hidden="true"><rect x="1.5" y="2" width="11" height="10" rx="1.5" fill="none" stroke="#fff" stroke-width="1.3"/><path d="M1.5 5h11M4 8h6M4 10h3.5" stroke="#fff" stroke-width="1.2"/></svg>',
  st: {
    new: '<svg viewBox="0 0 10 10" aria-hidden="true"><circle cx="5" cy="5" r="3.3" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>',
    reviewing: '<svg viewBox="0 0 10 10" aria-hidden="true"><circle cx="5" cy="5" r="3.8" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M5 1.2a3.8 3.8 0 0 1 0 7.6z" fill="currentColor"/></svg>',
    confirmed: '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M2 5.2 4.2 7.4 8 3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    dismissed: '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M3 3l4 4M7 3 3 7" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>'
  }
};
const chIcon = ch => I[ch] || I.report;
function reasonIcon(r) {
  const s = String(r).toLowerCase();
  if (/seen|days? ago|registered|new domain/.test(s)) return I.clock;
  if (/card|form|deposit|payment|password|login/.test(s)) return I.card;
  if (/phone/.test(s)) return I.phone;
  if (/imitat|brand|logo|official/.test(s)) return I.tag;
  if (/search|\bad\b|query/.test(s)) return I.search;
  if (/listing|website|map/.test(s)) return I.maps;
  return I.alert;
}
function votesHtml(n) { let h = '<span class="votes" aria-hidden="true">'; for (let i = 0; i < 4; i++) h += '<i class="' + (n != null && i < n ? '' : 'n') + '"></i>'; return h + '</span>'; }
function stHtml(s, cls) { return '<span class="' + (cls || 'st') + ' ' + esc(s) + '">' + (I.st[s] || '') + esc(statusLabel(s)) + '</span>'; }

/* ================================================================ API with demo fallback */
class ApiError extends Error { constructor(status, msg) { super(msg); this.status = status; } }

async function liveFetch(method, path, body) {
  const opt = {method, headers: {Accept: 'application/json'}, cache: 'no-store'};
  if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  let r;
  try { r = await fetch(path, opt); } catch (e) { throw new ApiError(0, 'network error'); }
  if (!r.ok) {
    let msg = r.status + ' ' + r.statusText;
    try { const j = await r.json(); if (j && typeof j.detail === 'string') msg = j.detail; } catch (e) { /* not JSON */ }
    throw new ApiError(r.status, msg);
  }
  if (!/json/.test(r.headers.get('content-type') || '')) throw new ApiError(415, 'not JSON');
  return r.json();
}

let probeP = null;
function probe() {
  if (S.mode !== 'unknown') return Promise.resolve(S.mode);
  if (!probeP) {
    probeP = liveFetch('GET', '/api/status').then(
      j => { S.probeStatus = j; S.mode = 'live'; renderDemoBadge(); return 'live'; },
      () => { S.mode = 'mock'; renderDemoBadge(); return 'mock'; });
  }
  return probeP;
}
function markMock(part) { S.mockParts.add(part); renderDemoBadge(); }
function setConn(ok) { S.conn = ok; const el = document.getElementById('conn'); if (el) el.hidden = ok; }

async function api(method, path, body) {
  await probe();
  if (S.mode !== 'live') return Mock.handle(method, path, body);
  if (S.probeStatus && method === 'GET' && path === '/api/status') { const j = S.probeStatus; S.probeStatus = null; setConn(true); return j; }
  try {
    const j = await liveFetch(method, path, body);
    setConn(true);
    return j;
  } catch (e) {
    if (e.status === 0) setConn(false);
    const missing = e.status === 404 || e.status === 405 || e.status === 501 || e.status === 415;
    const m = path.match(/^\/api\/cases\/([^/?]+)\/export/);
    if (m && missing) { markMock('export'); return buildExport(await liveFetch('GET', '/api/cases/' + m[1]), 'browser', new Date().toISOString()); }
    if (missing && method === 'GET' && /^\/api\/(status|kpis|cases|map|audit)(\?|$)/.test(path)) { markMock(path.slice(5).split('?')[0]); return Mock.handle(method, path, body); }
    if (missing && method === 'POST' && path === '/api/check') { markMock('check'); return Mock.handle(method, path, body); }
    throw e;
  }
}

function loadScript(src) {
  return new Promise((res, rej) => { const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = () => rej(new Error('script ' + src)); document.head.appendChild(s); });
}
const OV_KEY = 'mirsad.demo.overlay';
const ACTIONS = ['confirm', 'dismiss', 'reviewing', 'assign'];

const Mock = {
  cache: {}, bundleP: null, t0: Date.now(), mem: null,
  bundle() { if (!this.bundleP) this.bundleP = window.MIRSAD_MOCK ? Promise.resolve() : loadScript('mock/mock-data.js'); return this.bundleP; },
  async file(name) {
    if (!Object.prototype.hasOwnProperty.call(this.cache, name)) {
      try { await this.bundle(); } catch (e) { /* bundle missing: try the JSON file below */ }
      const B = window.MIRSAD_MOCK || {};
      let data = B[name];
      if (!FILE && (data !== undefined || !window.MIRSAD_MOCK)) {
        try { const r = await fetch('mock/' + name, {cache: 'no-store'}); if (r.ok) data = await r.json(); } catch (e) { /* keep bundle copy */ }
      }
      this.cache[name] = data === undefined ? null : data;
    }
    return clone(this.cache[name]);
  },
  overlay() {
    try { const v = JSON.parse(sessionStorage.getItem(OV_KEY)); if (v && v.cases) return v; } catch (e) { /* blocked */ }
    return this.mem || {cases: {}, audit: []};
  },
  save(ov) { this.mem = ov; try { sessionStorage.setItem(OV_KEY, JSON.stringify(ov)); } catch (e) { /* memory only */ } },
  async now() {
    const st = await this.file('status.json');
    const base = Date.parse(st && st.now);
    return new Date((isNaN(base) ? Date.now() : base) + (Date.now() - this.t0)).toISOString().replace(/\.\d+Z$/, 'Z');
  },
  apply(c, ov) {
    const o = ov.cases[c.id];
    if (o) { c.status = o.status; if (Array.isArray(c.decisions)) c.decisions = c.decisions.concat(o.decisions); }
    return c;
  },
  async caseDetail(id, ov) {
    let c = await this.file('case_' + id + '.json');
    if (!c) {
      const list = await this.file('cases.json'); const map = await this.file('map.json');
      const item = (list && list.items || []).find(i => i.id === id);
      const pin = (map && map.listings || []).find(l => l.case_id === id);
      if (!item && !pin) throw new ApiError(404, 'Case not found');
      c = partialCase(item, pin);
    }
    return this.apply(c, ov);
  },
  async handle(method, path, body) {
    const u = new URL(path, 'http://mirsad.local'); const p = u.pathname, q = u.searchParams;
    const ov = this.overlay();
    if (method === 'GET') {
      if (p === '/api/health') return {ok: true, version: 'demo', model: {name: 'DaE2', threshold: 0.8}, integrations: {}};
      if (p === '/api/status') return this.file('status.json');
      if (p === '/api/kpis') {
        const k = await this.file('kpis.json');
        Object.values(ov.cases).forEach(o => {
          const wasOpen = o.from === 'new' || o.from === 'reviewing';
          if (wasOpen && o.status === 'confirmed') { k.confirmed += 1; k.awaiting_review = Math.max(0, k.awaiting_review - 1); }
          if (wasOpen && o.status === 'dismissed') k.awaiting_review = Math.max(0, k.awaiting_review - 1);
        });
        return k;
      }
      if (p === '/api/cases') {
        const all = await this.file('cases.json'); const kp = await this.file('kpis.json');
        const status = q.get('status') || 'open', channel = q.get('channel') || 'all', limit = parseInt(q.get('limit'), 10) || 50;
        let items = (all.items || []).map(i => this.apply(i, ov));
        if (channel !== 'all') items = items.filter(i => i.channel === channel);
        if (status === 'open') items = items.filter(i => i.status === 'new' || i.status === 'reviewing');
        else if (status !== 'all') items = items.filter(i => i.status === status);
        items.sort((a, b) => b.risk - a.risk);
        let total = channel === 'all' ? all.total : ((kp.channel_split || {})[channel] != null ? kp.channel_split[channel] : items.length);
        if (status !== 'all') total = items.length;
        return {total, items: items.slice(0, limit)};
      }
      let m = p.match(/^\/api\/cases\/([^/]+)\/export$/);
      if (m) {
        const id = decodeURIComponent(m[1]); const c = await this.caseDetail(id, ov); const at = await this.now();
        ov.audit.unshift({at, actor: ANALYST, action: 'export', target: id, detail: 'Evidence package exported (demo data)'}); this.save(ov);
        return buildExport(c, 'demo', at);
      }
      m = p.match(/^\/api\/cases\/([^/]+)$/);
      if (m) return this.caseDetail(decodeURIComponent(m[1]), ov);
      if (p === '/api/map') return this.file('map.json');
      if (p === '/api/audit') {
        const a = await this.file('audit.json');
        const base = Array.isArray(a) ? a : (a && a.items) || [];
        return {items: ov.audit.concat(base).slice(0, parseInt(q.get('limit'), 10) || 100)};
      }
    }
    if (method === 'POST') {
      const m = p.match(/^\/api\/cases\/([^/]+)\/decision$/);
      if (m) {
        const id = decodeURIComponent(m[1]); const action = body && body.action;
        if (ACTIONS.indexOf(action) < 0) throw new ApiError(422, 'Unknown action');
        const c = await this.caseDetail(id, ov); const at = await this.now();
        const o = ov.cases[id] || (ov.cases[id] = {from: c.status, status: c.status, decisions: []});
        let next = c.status;
        if (action === 'confirm') next = 'confirmed';
        else if (action === 'dismiss') next = 'dismissed';
        else if (action === 'reviewing') next = 'reviewing';
        else if (action === 'assign' && c.status === 'new') next = 'reviewing';
        o.status = next;
        const d = {at, action, analyst: (body && body.analyst) || ANALYST};
        if (body && body.note) d.note = body.note;
        o.decisions.push(d);
        ov.audit.unshift({at, actor: d.analyst, action, target: id, detail: 'Status ' + next + ' (demo data)'});
        this.save(ov);
        return this.caseDetail(id, ov);
      }
      if (p === '/api/check') return this.check(body && body.url);
      const r = p.match(/^\/api\/runs\/(\w+)$/);
      if (r) return {run_id: 'demo-' + Date.now(), channel: r[1], started: await this.now()};
    }
    throw new ApiError(404, 'Not in the demo data');
  },
  async check(raw) {
    const url = String(raw || '').trim();
    const h = host(url);
    if (!h || h.indexOf('.') < 0) throw new ApiError(422, t('Not a link this tool can check.'));
    const list = await this.file('cases.json');
    const hit = (list.items || []).find(i => host(i.url) === h);
    if (hit) { const c = await this.caseDetail(hit.id, this.overlay()); c._match = hit.id; return c; }
    const BRANDS = [['salik', 'Salik', 'salik.ae'], ['tamm', 'TAMM', 'tamm.abudhabi'], ['adpolice', 'Abu Dhabi Police', 'adpolice.gov.ae'], ['police', 'Abu Dhabi Police', 'adpolice.gov.ae'],
      ['emiratespost', 'Emirates Post', 'emiratespost.ae'], ['etisalat', 'e&', 'etisalat.ae'], ['adnoc', 'ADNOC', 'adnoc.ae'], ['emiratesnbd', 'Emirates NBD', 'emiratesnbd.com'],
      ['uaepass', 'UAE PASS', 'uaepass.ae'], ['etihad', 'Etihad', 'etihad.com'], ['aramex', 'Aramex', 'aramex.com'], ['dewa', 'DEWA', 'dewa.gov.ae'], ['rta', 'RTA', 'rta.ae']];
    const official = BRANDS.some(b => h === b[2] || h.endsWith('.' + b[2]));
    const brand = official ? null : BRANDS.find(b => h.replace(/[^a-z]/g, '').indexOf(b[0]) >= 0 && b[0].length > 3 || h.split(/[.-]/).indexOf(b[0]) >= 0);
    const tld = h.split('.').pop();
    const risky = ['top', 'xyz', 'shop', 'info', 'site', 'online', 'click', 'live', 'icu', 'buzz', 'cfd', 'sbs', 'store', 'support'].indexOf(tld) >= 0;
    const kw = (url.toLowerCase().match(/pay|topup|top-up|recharge|refund|fine|fee|verify|login|update|secure|bill|offer|wallet/g) || []);
    const hy = (h.match(/-/g) || []).length;
    let s = official ? 0.03 : 0.08 + (brand ? 0.36 : 0) + (risky ? 0.2 : 0) + Math.min(kw.length, 2) * 0.08 + (hy >= 2 ? 0.08 : 0);
    s = Math.min(0.98, s);
    const cl = v => +Math.max(0.01, Math.min(0.99, v)).toFixed(2);
    const votes = {adaboost: cl(s + 0.02), bagging: cl(s + 0.01), stacking: cl(s - 0.01), voting: cl(s - 0.03)};
    const reasons = [];
    if (official) reasons.push('Domain is on the official list for this brand');
    if (brand) reasons.push('Name imitates ' + brand[1] + ' but is not on the official list');
    if (risky) reasons.push('Uses a low-cost top-level domain (.' + tld + ')');
    if (kw.length) reasons.push('Link uses payment or account words (' + kw.slice(0, 2).join(', ') + ')');
    if (hy >= 2) reasons.push('Domain name joins several words with hyphens');
    if (!reasons.length) reasons.push('No warning signs in the link itself');
    return {id: null, risk: cl(s), threshold: 0.8, status: 'new', url, url_redacted: url.split('?')[0], display: h, domain: h, channel: 'report',
      channel_detail: 'Checked on demand', imitates: brand ? brand[1] : null, official_domains: brand ? [brand[2]] : [], first_seen: null, age_days: null,
      votes, model_mean: cl((votes.adaboost + votes.bagging + votes.stacking + votes.voting) / 4), reasons, evidence: [], capture: {available: false},
      summary: null, listing: null, graph: {nodes: [], edges: []}, timeline: [], exports: Object.keys(EXPORT_LABEL), decisions: [], _demoEstimate: true};
  }
};
function partialCase(item, pin) {
  const base = item ? clone(item) : {id: pin.case_id, risk: pin.risk, url: null, display: pin.category + ' listing', channel: 'maps', channel_detail: 'Maps listing',
    imitates: 'none (website unrelated to business)', first_seen: null, age_days: null, votes: null, votes_above: null, status: 'new'};
  const v = base.votes ? Object.values(base.votes) : [];
  return Object.assign(base, {threshold: 0.8, url_redacted: base.url, domain: host(base.url || ''), official_domains: [], model_mean: v.length ? v.reduce((a, b) => a + b, 0) / v.length : null,
    reasons: [], evidence: [], capture: {available: false}, summary: null,
    listing: pin ? {place_id: null, category: pin.category, website: null, phone_shared_with: null, lat: pin.lat, lng: pin.lng, mismatch: pin.mismatch ? 'flagged by Maps check' : null} : null,
    graph: {nodes: [], edges: []}, timeline: [], exports: Object.keys(EXPORT_LABEL), decisions: [], _partial: true});
}
function buildExport(c, origin, at) {
  return {
    package: 'mirsad-evidence', format: 1, case_id: c.id, generated_at: at, generated_by: ANALYST,
    origin: origin === 'demo' ? 'Demo data. Built in the browser because the live service was unreachable.' : 'Built in the browser from the live case record because the export endpoint did not answer.',
    targets: c.exports || [], status: c.status, url: c.url, url_redacted: c.url_redacted, domain: c.domain, display: c.display,
    imitates: c.imitates, official_domains: c.official_domains, risk: c.risk, threshold: c.threshold, votes: c.votes, model_mean: c.model_mean,
    model: 'DaE2 (Omolara and Alawida, 2025)', reasons: c.reasons, evidence: c.evidence, timeline: c.timeline, capture: c.capture,
    listing: c.listing, summary: c.summary, decisions: c.decisions
  };
}

async function exportCase(id) {
  try {
    const data = await api('GET', '/api/cases/' + encodeURIComponent(id) + '/export');
    const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'mirsad_' + id + '_evidence.json';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    toast(t('Evidence package for {id} downloaded', {id}));
    return data || true;
  } catch (e) { toast(t('Export failed: {e}', {e: e.message}), {error: true}); return false; }
}
async function decide(id, action, note) {
  return api('POST', '/api/cases/' + encodeURIComponent(id) + '/decision', {action, note: note || '', analyst: ANALYST});
}

/* ================================================================ demo badge, toasts, dialogs */
function renderDemoBadge() {
  const b = document.getElementById('demoBadge'); if (!b) return;
  const on = S.mode === 'mock' || S.mockParts.size > 0;
  b.hidden = !on;
  if (!on) return;
  let title;
  if (FILE) title = t('Demo data, because the page was opened from a file.');
  else if (FORCED_MOCK) title = t('Demo data, as requested by the address.');
  else if (S.mode === 'mock') title = t('Demo data. The live service did not answer; select to retry.');
  else title = t('Demo data for: {list}. Select to retry the live service.', {list: Array.from(S.mockParts).join(', ')});
  b.title = title; b.setAttribute('aria-label', title);
  b.querySelector('span').textContent = t('Demo data');
}
function retryLive() {
  if (FORCED_MOCK) return;
  S.mode = 'unknown'; probeP = null; S.mockParts.clear();
  probe().then(() => S.retryCbs.forEach(cb => cb()));
}
function toast(msg, opt) {
  opt = opt || {};
  const box = document.getElementById('toasts'); if (!box) return {close() {}, update() {}};
  const el = document.createElement('div');
  el.className = 'toast' + (opt.error ? ' err' : '');
  el.setAttribute('role', opt.error ? 'alert' : 'status');
  const span = document.createElement('span'); span.textContent = msg; el.appendChild(span);
  (opt.actions || []).forEach(a => { const b = document.createElement('button'); b.type = 'button'; b.textContent = a.label; b.addEventListener('click', () => { a.fn(); if (!a.keep) close(); }); el.appendChild(b); });
  box.appendChild(el);
  let timer = opt.timeout === 0 ? 0 : setTimeout(close, opt.timeout || 4200);
  function close() { clearTimeout(timer); el.remove(); }
  return {close, update(m) { span.textContent = m; }, el};
}
async function openAudit() {
  const d = document.getElementById('auditDlg'); if (!d) return;
  const body = d.querySelector('.bb');
  d.hidden = false; d.querySelector('.x').focus();
  body.innerHTML = '<p class="loading">' + esc(t('Loading')) + '</p>';
  try {
    const [a, st] = await Promise.all([api('GET', '/api/audit?limit=100'), api('GET', '/api/status').catch(() => null)]);
    const items = Array.isArray(a) ? a : (a.items || []);
    const now = st && st.now;
    body.innerHTML = '<table><thead><tr><th>' + esc(t('Time')) + '</th><th>' + esc(t('Actor')) + '</th><th>' + esc(t('Action')) + '</th><th>' + esc(t('Target')) + '</th><th>' + esc(t('Detail')) + '</th></tr></thead><tbody>' +
      items.map(i => '<tr><td class="tn">' + esc(fmtWhen(i.at, now)) + '</td><td>' + esc(i.actor) + '</td><td>' + esc(i.action) + '</td><td>' + ltr(i.target) + '</td><td dir="auto">' + esc(i.detail) + '</td></tr>').join('') + '</tbody></table>';
  } catch (e) { body.innerHTML = '<p class="loading">' + esc(e.message) + '</p>'; }
}
function closeAudit() { const d = document.getElementById('auditDlg'); if (d && !d.hidden) { d.hidden = true; const b = document.querySelector('[data-nav="audit"]'); if (b) b.focus(); } }

/* ================================================================ status strip */
function renderStatusStrip(st) {
  const box = document.getElementById('statusItems'); if (!box || !st) return;
  const LBL = {search: 'Search monitor', maps: 'Maps check', certificates: 'Certificate stream', feeds: 'Feeds'};
  box.innerHTML = (st.channels || []).map(c => {
    const label = t(LBL[c.id] || c.label);
    const when = fmtTime(c.last_run);
    const title = c.label + ': ' + c.state + (when ? ', ' + when : '') + (c.detail ? ', ' + c.detail : '');
    let inner;
    if (c.state === 'synced') inner = I.sync + '<b>' + esc(label) + '</b><span>' + esc(t('synced {t}', {t: when})) + '</span>';
    else {
      const dot = c.state === 'live' ? 'dot' : c.state === 'error' ? 'dot err' : 'dot idle';
      const word = {live: 'Live', idle: 'Idle', error: 'Error', off: 'Off'}[c.state] || c.state;
      inner = '<i class="' + dot + '"></i><b>' + esc(label) + '</b><span class="lv' + (c.state === 'error' ? ' err' : '') + '">' + esc(t(word)) + '</span>' +
        (c.state === 'live' && when && c.id === 'search' ? '<span>' + esc(t('last run {t}', {t: when})) + '</span>' : '') +
        (c.detail ? '<span class="dt"><bdi>' + esc(c.detail) + '</bdi></span>' : '');
    }
    return '<div class="it" title="' + esc(title) + '">' + inner + '</div>';
  }).join('');
  const m = document.getElementById('modelPill');
  if (m && st.model) m.innerHTML = esc(st.model.name) + '<span>' + esc(t('threshold {v}', {v: Number(st.model.threshold).toFixed(2)})) + '</span>';
}

/* ================================================================ activity chart */
function renderBars(svg, kpis, o) {
  if (!svg || !kpis) return;
  const data = kpis.flagged_per_hour || [];
  const W = Math.max(200, Math.round(svg.clientWidth || o.w)), H = Math.round(svg.clientHeight || o.h);
  svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  svg.style.direction = 'ltr';
  const base = o.base, max = Math.max(1, ...data.map(d => d.count || 0));
  const per = Math.min(o.per, (base - 12) / max);
  const slot = W / Math.max(24, data.length), bw = Math.min(o.bw, slot - 3);
  let pk = 0; data.forEach((d, i) => { if ((d.count || 0) > (data[pk].count || 0)) pk = i; });
  let c = '';
  const g4 = max > 10 ? Math.ceil(max / 2 / 5) * 5 : 4;
  [0, g4, g4 * 2].forEach(v => {
    const y = (base - v * per).toFixed(1);
    if (v * per <= base) c += '<line x1="0" x2="' + W + '" y1="' + y + '" y2="' + y + '" stroke="' + (v ? '#EDF1F5' : '#CBD7E4') + '" stroke-width="1"' + (v && o.dash ? ' stroke-dasharray="2 3"' : '') + '/>';
  });
  data.forEach((d, i) => {
    const v = d.count || 0, x = i * slot + (slot - bw) / 2, h = v * per, isPk = i === pk && v > 0;
    if (v) c += '<rect x="' + x.toFixed(1) + '" y="' + (base - h).toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + h.toFixed(1) + '" rx="1.5" fill="' + (isPk ? '#034A89' : '#86A8CB') + '"><title>' + esc(fmtTime(d.hour)) + ': ' + v + '</title></rect>';
    if (isPk && o.peakValue) c += '<text x="' + (x + bw / 2).toFixed(1) + '" y="' + (base - h - 4).toFixed(1) + '" font-family="Inter" font-size="11" font-weight="600" fill="#0D2742" text-anchor="middle">' + v + '</text>';
    if (isPk && o.peakLabel) {
      const lx = x - 6; const anchor = lx > 110 ? 'end' : 'start';
      c += '<text x="' + (anchor === 'end' ? lx : x + bw + 6).toFixed(1) + '" y="' + (base - h + 9).toFixed(1) + '" font-family="Inter" font-size="11" font-weight="600" fill="#0D2742" text-anchor="' + anchor + '">' + esc(t('Peak {n} at {t}', {n: v, t: fmtTime(d.hour)})) + '</text>';
    }
  });
  const ly = base + (o.labelGap || 15);
  const every = o.labelEvery || 4;
  data.forEach((d, i) => {
    if (i === data.length - 1) return;
    if (i % every !== 0) return;
    if ((i + 0.5) * slot > W - 48) return;
    const first = i === 0 && o.firstStart;
    c += '<text x="' + (first ? 0 : (i * slot + slot / 2)).toFixed(1) + '" y="' + ly + '" font-family="Inter" font-size="11" fill="#51657C" text-anchor="' + (first ? 'start' : 'middle') + '">' + esc(fmtTime(d.hour)) + '</text>';
  });
  if (data.length) c += '<text x="' + W + '" y="' + ly + '" font-family="Inter" font-size="11" fill="#51657C" text-anchor="end">' + esc(fmtTime(data[data.length - 1].hour)) + '</text>';
  svg.innerHTML = c;
  return {peak: data[pk]};
}

/* ================================================================ hold to confirm */
const Pending = {id: null, until: 0, timer: 0, tick: 0, toast: null, listeners: []};
function holdMarkup() {
  return '<span class="fill" aria-hidden="true"></span><svg class="ring" viewBox="0 0 18 18" aria-hidden="true"><circle class="rt" cx="9" cy="9" r="7"/><circle class="rp" cx="9" cy="9" r="7" transform="rotate(-90 9 9)" stroke-dasharray="43.98" stroke-dashoffset="32.99"/></svg><span class="lbl"></span>';
}
/* Wires a .hold button. opts: getState() -> 'idle'|'pending'|'busy'|'done', onComplete(), onUndo(), onTap() */
function wireHold(btn, opts) {
  const C = 43.98;
  let raf = 0, t0 = 0, active = false, swallow = 0;
  const rp = () => btn.querySelector('.rp'), fill = () => btn.querySelector('.fill');
  const set = p => { const r = rp(), f = fill(); if (r) r.style.strokeDashoffset = (C * (1 - p)).toFixed(2); if (f) f.style.transform = 'scaleX(' + p.toFixed(3) + ')'; };
  const idle = () => { const r = rp(), f = fill(); if (r) r.style.strokeDashoffset = (C * 0.75).toFixed(2); if (f) f.style.transform = 'scaleX(0)'; };
  const state = () => opts.getState();
  function start() {
    if (active || btn.disabled || state() !== 'idle') return;
    active = true; t0 = performance.now(); set(0); btn.classList.add('holding');
    const loop = () => {
      const p = Math.min(1, (performance.now() - t0) / HOLD_MS); set(p);
      if (p >= 1) { active = false; swallow = Date.now() + 1200; btn.classList.remove('holding'); opts.onComplete(); return; }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
  }
  function cancel(tap) {
    if (!active) return;
    const held = performance.now() - t0;
    active = false; cancelAnimationFrame(raf); btn.classList.remove('holding'); idle();
    if (tap && held < 350 && opts.onTap) opts.onTap();
  }
  btn.addEventListener('pointerdown', e => {
    if (e.button !== 0 || state() !== 'idle') return;
    e.preventDefault(); btn.focus({preventScroll: true});
    try { btn.setPointerCapture(e.pointerId); } catch (x) { /* older engines */ }
    start();
  });
  btn.addEventListener('pointerup', () => cancel(true));
  btn.addEventListener('pointercancel', () => cancel(false));
  btn.addEventListener('lostpointercapture', () => cancel(false));
  btn.addEventListener('keydown', e => {
    if ((e.key === ' ' || e.key === 'Enter') && state() === 'idle') { e.preventDefault(); if (!e.repeat) start(); }
  });
  btn.addEventListener('keyup', e => { if ((e.key === ' ' || e.key === 'Enter') && active) { e.preventDefault(); cancel(true); } });
  btn.addEventListener('blur', () => cancel(false));
  /* The release that ends a completed hold also fires a click; swallow it so it does not undo at once. */
  btn.addEventListener('click', e => {
    if (swallow && Date.now() < swallow) { swallow = 0; e.preventDefault(); return; }
    swallow = 0;
    if (state() === 'pending' && opts.onUndo) opts.onUndo();
  });
  btn.addEventListener('contextmenu', e => { if (active) e.preventDefault(); });
  return {idle, set};
}
/* Paints a hold button for a state. */
function paintHold(btn, st, extra) {
  if (!btn) return;
  btn.classList.remove('pending', 'done');
  btn.disabled = false;
  btn.removeAttribute('aria-describedby');
  const lbl = btn.querySelector('.lbl'), rp = btn.querySelector('.rp'), fill = btn.querySelector('.fill');
  if (fill) fill.style.transform = 'scaleX(0)';
  if (st === 'pending') {
    const left = Math.max(0, Pending.until - Date.now());
    btn.classList.add('pending');
    lbl.textContent = t('Undo, confirming in {n} s', {n: Math.ceil(left / 1000)});
    if (rp) rp.style.strokeDashoffset = (43.98 * (1 - left / (UNDO_S * 1000))).toFixed(2);
  } else if (st === 'busy') {
    btn.classList.add('pending'); btn.disabled = true; lbl.textContent = t('Saving the decision');
  } else if (st === 'done') {
    btn.classList.add('done'); btn.disabled = true;
    lbl.textContent = t('Confirmed {t}', {t: extra || ''}).trim();
    if (rp) rp.style.strokeDashoffset = '0';
  } else {
    lbl.textContent = t('Hold to confirm and export evidence');
    if (rp) rp.style.strokeDashoffset = (43.98 * 0.75).toFixed(2);
  }
}
/* Starts the timed undo window, then sends the confirm decision. */
function startPending(id, onChange, onCommitted) {
  if (Pending.id) commitNow();
  Pending.id = id; Pending.until = Date.now() + UNDO_S * 1000; Pending.onChange = onChange; Pending.onCommitted = onCommitted;
  Pending.toast = toast(t('Confirming {id} in {n} s', {id, n: UNDO_S}), {timeout: 0, actions: [{label: t('Undo'), fn: undoPending}]});
  Pending.tick = setInterval(() => {
    const left = Math.ceil((Pending.until - Date.now()) / 1000);
    if (Pending.toast) Pending.toast.update(t('Confirming {id} in {n} s', {id, n: Math.max(0, left)}));
    if (Pending.onChange) Pending.onChange();
  }, 200);
  Pending.timer = setTimeout(commitNow, UNDO_S * 1000);
  if (onChange) onChange();
}
function undoPending() {
  if (!Pending.id) return;
  const id = Pending.id, cb = Pending.onChange;
  clearTimeout(Pending.timer); clearInterval(Pending.tick);
  if (Pending.toast) Pending.toast.close();
  Pending.id = null;
  toast(t('Confirmation of {id} undone', {id}));
  if (cb) cb();
}
async function commitNow() {
  if (!Pending.id) return;
  const id = Pending.id, cb = Pending.onChange, done = Pending.onCommitted;
  clearTimeout(Pending.timer); clearInterval(Pending.tick);
  if (Pending.toast) Pending.toast.close();
  Pending.id = null; Pending.busy = id;
  if (cb) cb();
  try {
    const c = await decide(id, 'confirm', 'Confirmed after hold');
    Pending.busy = null;
    toast(t('{id} confirmed. Evidence package ready.', {id}), {timeout: 9000, actions: [{label: t('Download'), fn: () => exportCase(id)}]});
    if (done) done(c);
  } catch (e) {
    Pending.busy = null;
    toast(t('The decision was not saved: {e}', {e: e.message}), {error: true});
    if (cb) cb();
  }
}
function holdState(c) {
  if (!c) return 'idle';
  if (Pending.id === c.id) return 'pending';
  if (Pending.busy === c.id) return 'busy';
  if (c.status === 'confirmed') return 'done';
  return 'idle';
}
function lastDecisionTime(c, action) {
  const d = (c.decisions || []).filter(x => x.action === action).pop();
  return d ? fmtTime(d.at) : '';
}

/* ================================================================ top bar: check a link, nav, language */
function caseHref(id) { return 'case.html?id=' + encodeURIComponent(id) + (QS.get('mock') === '1' ? '&mock=1' : ''); }
function homeHref(hash) { return 'index.html' + (QS.get('mock') === '1' ? '?mock=1' : '') + (hash ? '#' + hash : ''); }

function wireTopbar() {
  document.querySelectorAll('[data-lang]').forEach(b => b.addEventListener('click', () => setLang(b.dataset.lang)));
  document.querySelectorAll('[data-href]').forEach(a => {
    const k = a.dataset.href;
    a.setAttribute('href', k === 'watch' ? homeHref() : k === 'cases' ? 'case.html' + (QS.get('mock') === '1' ? '?mock=1' : '') : homeHref(k));
  });
  document.querySelectorAll('[data-nav]').forEach(b => b.addEventListener('click', () => {
    if (b.dataset.nav === 'audit') openAudit();
    else toast(t('Not part of this prototype'));
  }));
  const dlg = document.getElementById('auditDlg');
  if (dlg) {
    dlg.addEventListener('click', e => { if (e.target === dlg) closeAudit(); });
    dlg.querySelector('.x').addEventListener('click', closeAudit);
  }
  const demo = document.getElementById('demoBadge');
  if (demo) demo.addEventListener('click', retryLive);
  const form = document.getElementById('checkForm'), input = document.getElementById('checkInput'), pop = document.getElementById('checkPop');
  if (!form) return;
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const v = input.value.trim(); if (!v) return;
    if (/^mr-\d{3,}$/i.test(v)) { location.href = caseHref(v.toUpperCase()); return; }
    pop.hidden = false;
    pop.innerHTML = '<div class="spin">' + esc(t('Checking')) + ' ' + ltr(v) + '</div>';
    try { renderCheck(await api('POST', '/api/check', {url: v, save: false})); }
    catch (err) { pop.innerHTML = '<div class="ph"><span class="pd">' + ltr(v) + '</span><button class="x" type="button" aria-label="' + esc(t('Close')) + '">' + I.x + '</button></div><p class="note">' + esc(t('The check failed: {e}', {e: err.message})) + '</p>'; wirePopClose(); }
  });
  function wirePopClose() { const x = pop.querySelector('.x'); if (x) x.addEventListener('click', () => { pop.hidden = true; input.focus(); }); }
  function renderCheck(c) {
    const th = c.threshold != null ? c.threshold : 0.8;
    const hi = c.risk >= th;
    const above = votesAbove(c, th);
    const caseId = c._match || c.id;
    pop.innerHTML = '<div class="ph"><span class="pd">' + ltr(c.display || c.domain || c.url) + '</span><button class="x" type="button" aria-label="' + esc(t('Close')) + '">' + I.x + '</button></div>' +
      '<div class="pr"><span class="big' + (hi ? ' hi' : '') + '">' + rk(c.risk) + '</span><span><span class="verdict' + (hi ? ' hi' : '') + '">' + esc(t(hi ? 'Above threshold {v}' : 'Below threshold {v}', {v: rk(th)})) + '</span><br>' +
      '<span class="sub">' + (above != null ? votesHtml(above).replace('class="votes"', 'class="votes" style="display:inline-flex;vertical-align:-1px;margin-inline-end:5px"') + esc(t('{n} of 4', {n: above})) : '') +
      (c.imitates ? ' · ' + esc(t('Imitates')) + ' ' + imitatesHtml(c.imitates) : '') + '</span></span></div>' +
      '<ul>' + (c.reasons || []).slice(0, 4).map(r => '<li dir="auto">' + esc(smart(r)) + '</li>').join('') + '</ul>' +
      (caseId ? '<div class="pa"><a class="btn primary" href="' + esc(caseHref(caseId)) + '">' + I.ext + esc(t('Open the case')) + '</a></div>' : '') +
      (c._match ? '<p class="note">' + esc(t('Matches case {id} in the queue.', {id: c._match})) + '</p>' : '') +
      (c._demoEstimate ? '<p class="note">' + esc(t('Demo estimate from simple rules. The DaE2 model scores links only on the live service.')) + '</p>' : '');
    wirePopClose();
  }
  document.addEventListener('click', e => { if (!pop.hidden && !pop.contains(e.target) && !form.contains(e.target)) pop.hidden = true; });
}

/* Global keys shared by both pages: "/" focuses the check input, Escape closes overlays. */
function isTyping(e) { const el = e.target; return el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable); }
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    const pop = document.getElementById('checkPop');
    if (pop && !pop.hidden) { pop.hidden = true; return; }
    closeAudit();
    return;
  }
  if (isTyping(e) || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key === '/') { const i = document.getElementById('checkInput'); if (i) { e.preventDefault(); i.focus(); } }
});

function initCore() {
  let l = 'en';
  try { l = localStorage.getItem('mirsad.lang') || 'en'; } catch (e) { /* storage blocked */ }
  if (QS.get('lang') === 'ar' || QS.get('lang') === 'en') l = QS.get('lang');
  setLang(l, true);
  wireTopbar();
  renderDemoBadge();
  S.langCbs.push(renderDemoBadge);
}

/* Exports for case.js */
window.Mirsad = {S, t, setLang, esc, ltr, latinRuns, smart, host, clone, fmtTime, fmtDate, fmtWhen, dayKey, days, num, rk, statusLabel, votesAbove, splitDetail, chipText,
  imitatesHtml, highlightDomains, I, chIcon, reasonIcon, votesHtml, stHtml, api, decide, exportCase, toast, renderStatusStrip, renderBars, Pending,
  holdMarkup, wireHold, paintHold, startPending, undoPending, holdState, lastDecisionTime, caseHref, homeHref, isTyping, EXPORT_LABEL, QS, CHANNELS,
  onLang: cb => S.langCbs.push(cb), onRetry: cb => S.retryCbs.push(cb), REFRESH_MS};

/* ================================================================ Watch screen */
const W = {status: null, kpis: null, list: null, map: null, sel: null, detail: {}, filter: 'all', view: {z: 1, cx: 720, cy: 408}, showVerified: true, loadingId: null};
const $ = id => document.getElementById(id);

function initWatch() {
  const h = (location.hash || '').slice(1);
  if (CHANNELS.indexOf(h) >= 0) W.filter = h;
  $('seg').addEventListener('click', e => {
    const b = e.target.closest('button[data-ch]'); if (!b) return;
    W.filter = b.dataset.ch; renderChips(); loadQueue();
  });
  $('rows').addEventListener('click', e => { const b = e.target.closest('button.row'); if (b) selectCase(b.dataset.id, {focus: false}); });
  $('rows').addEventListener('keydown', e => {
    const b = e.target.closest('button.row'); if (!b) return;
    if (e.key === 'Enter') { e.preventDefault(); location.href = caseHref(b.dataset.id); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); move(1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
  });
  document.addEventListener('keydown', e => {
    if (isTyping(e) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (!document.getElementById('auditDlg').hidden) return;
    if (e.key === 'j' || e.key === 'J') { e.preventDefault(); move(1); }
    else if (e.key === 'k' || e.key === 'K') { e.preventDefault(); move(-1); }
    else if (e.key === 'Enter' && W.sel && (e.target === document.body || e.target === document.documentElement)) { e.preventDefault(); location.href = caseHref(W.sel); }
  });
  /* map controls */
  $('zin').addEventListener('click', () => zoom(1.5));
  $('zout').addEventListener('click', () => zoom(1 / 1.5));
  $('layers').addEventListener('click', () => { W.showVerified = !W.showVerified; $('layers').setAttribute('aria-pressed', String(W.showVerified)); renderMap(); });
  $('locate').addEventListener('click', () => { const f = focusPin(); if (f) { W.view = {z: Math.max(W.view.z, 1.5), cx: f.x, cy: f.y}; renderMap(); } });
  $('compass').addEventListener('click', () => { W.view = {z: 1, cx: 720, cy: 408}; renderMap(); });
  $('tag').addEventListener('click', () => { const f = focusPin(); if (f && f.l.case_id) selectCase(f.l.case_id, {focus: false}); });
  wirePan();
  const hold = $('holdBtn');
  wireHold(hold, {
    getState: () => holdState(currentCase()),
    onComplete: () => { const c = currentCase(); if (c) startPending(c.id, renderActions, afterDecision); },
    onUndo: undoPending,
    onTap: () => { const h = $('holdHint'); h.textContent = t('Press and hold to confirm'); setTimeout(() => { h.textContent = ''; }, 2200); }
  });
  $('dismissBtn').addEventListener('click', () => simpleDecision('dismiss'));
  $('assignBtn').addEventListener('click', () => simpleDecision('assign'));
  let rz = 0;
  window.addEventListener('resize', () => { cancelAnimationFrame(rz); rz = requestAnimationFrame(() => { renderMap(); renderActivity(); }); });
  S.langCbs.push(() => { renderStatusStrip(W.status); renderKpis(); renderChips(); renderRows(); renderCase(); renderMap(); renderActivity(); });
  S.retryCbs.push(() => { W.detail = {}; refresh(true); });
  renderChips();
  refresh(true);
  setInterval(() => { if (!document.hidden) refresh(false); }, REFRESH_MS);
}

function casesPath() { return '/api/cases?status=all&channel=' + W.filter + '&limit=50'; }
async function refresh(first) {
  const [st, kp, list, map] = await Promise.allSettled([api('GET', '/api/status'), api('GET', '/api/kpis'), api('GET', casesPath()), api('GET', '/api/map')]);
  if (st.status === 'fulfilled') { W.status = st.value; renderStatusStrip(W.status); }
  if (kp.status === 'fulfilled') { W.kpis = kp.value; renderKpis(); renderChips(); renderActivity(); }
  if (map.status === 'fulfilled') W.map = map.value;
  if (list.status === 'fulfilled') {
    W.list = list.value;
    if ((!W.sel || first) && W.list.items.length && !W.list.items.some(i => i.id === W.sel)) W.sel = W.list.items[0].id;
    renderRows();
  } else if (first) $('rows').innerHTML = '<li class="empty">' + esc(list.reason && list.reason.message) + '</li>';
  renderMap();
  if (W.sel) loadCase(W.sel, !first);
}
async function loadQueue() {
  try { W.list = await api('GET', casesPath()); } catch (e) { W.list = {total: 0, items: []}; }
  renderRows();
  if (W.list.items.length && !W.list.items.some(i => i.id === W.sel)) selectCase(W.list.items[0].id, {focus: false});
}
function renderKpis() {
  const k = W.kpis; if (!k) return;
  const ms = k.median_scoring_ms;
  $('kpis').innerHTML =
    '<div class="kc"><div class="kl">' + esc(t('Links screened today')) + '</div><div class="kv">' + num(k.links_screened_today) + '</div></div>' +
    '<div class="kc"><div class="kl"><i class="sq" aria-hidden="true"></i>' + esc(t('Flagged')) + '</div><div class="kv rk">' + num(k.flagged) + '</div></div>' +
    '<div class="kc"><div class="kl">' + esc(t('Awaiting review')) + '</div><div class="kv">' + num(k.awaiting_review) + '</div></div>' +
    '<div class="kc"><div class="kl">' + esc(t('Confirmed')) + '</div><div class="kv">' + num(k.confirmed) + '</div></div>' +
    '<div class="kc"><div class="kl">' + esc(t('Median scoring time')) + '</div><div class="kv">' + (ms == null ? 'n/a' : (Math.round(ms * 10) / 10)) + '<small>' + esc(S.lang === 'ar' ? 'ms' : 'ms') + '</small></div></div>';
}
function renderChips() {
  const split = (W.kpis && W.kpis.channel_split) || {};
  const all = W.kpis ? W.kpis.flagged : (W.list ? W.list.total : null);
  const defs = [['all', 'All', all], ['search', 'Search', split.search], ['certificates', 'Certificates', split.certificates], ['maps', 'Maps', split.maps], ['feeds', 'Feeds', split.feeds]];
  $('seg').innerHTML = defs.map(d => '<button type="button" data-ch="' + d[0] + '" aria-pressed="' + (W.filter === d[0]) + '">' + esc(t(d[1])) + (d[2] != null ? ' <em>' + num(d[2]) + '</em>' : '') + '</button>').join('');
}
function itemById(id) { return W.list && W.list.items.find(i => i.id === id); }
function currentCase() { return W.detail[W.sel] || null; }
function renderRows() {
  const L = W.list; if (!L) return;
  const total = W.filter === 'all' ? (W.kpis ? W.kpis.flagged : L.total) : L.total;
  $('qcount').textContent = t('{n} of {total} flagged today', {n: L.items.length, total: num(total)});
  const focusId = document.activeElement && document.activeElement.classList.contains('row') ? document.activeElement.dataset.id : null;
  if (!L.items.length) { $('rows').innerHTML = '<li class="empty">' + esc(t('No cases in this channel today.')) + '</li>'; return; }
  const th = (W.status && W.status.model && W.status.model.threshold) || 0.8;
  const keep = $('rows').scrollTop;
  $('rows').innerHTML = L.items.map(o => {
    const hi = o.risk >= th;
    const n = votesAbove(o, th);
    const [chip, rest] = splitDetail(o.channel_detail);
    const isDomain = o.channel !== 'maps';
    return '<li><button type="button" class="row' + (o.status === 'dismissed' ? ' dim' : '') + '" data-id="' + esc(o.id) + '"' + (o.id === W.sel ? ' aria-current="true"' : '') + '>' +
      '<span class="risk' + (hi ? ' hi' : '') + '"><span class="v">' + rk(o.risk) + '</span>' + votesHtml(n) + '<span class="vt">' + esc(t('{n} of 4', {n: n == null ? '?' : n})) + '</span></span>' +
      '<span class="rb"><span class="l1"><span class="dom" title="' + esc(o.display) + '">' + (isDomain ? ltr(o.display) : esc(o.display)) + '</span>' + stHtml(o.status) + '</span>' +
      '<span class="l2"><span class="ch">' + chIcon(o.channel) + esc(chipText(chip)) + '</span>' + (rest ? '<bdi>' + (/^site /.test(rest) ? '(' + esc(rest) + ')' : esc(smart(rest))) + '</bdi>' : '') + '</span>' +
      '<span class="l3"><span class="imi">' + esc(t('Imitates')) + ' ' + imitatesHtml(o.imitates) + '</span><span class="age">' + I.clock + esc(days(o.age_days)) + '</span></span></span>' +
      '<span class="vh">' + esc(statusLabel(o.status)) + ', ' + esc(t('Risk')) + ' ' + rk(o.risk) + '</span></button></li>';
  }).join('');
  $('rows').scrollTop = keep;
  if (focusId) { const b = $('rows').querySelector('button[data-id="' + CSS.escape(focusId) + '"]'); if (b) b.focus({preventScroll: true}); }
}
function move(d) {
  const items = W.list ? W.list.items : []; if (!items.length) return;
  let i = items.findIndex(x => x.id === W.sel);
  i = Math.max(0, Math.min(items.length - 1, (i < 0 ? 0 : i + d)));
  selectCase(items[i].id, {focus: true});
}
function selectCase(id, opts) {
  if (!id) return;
  W.sel = id;
  $('rows').querySelectorAll('button.row').forEach(b => { if (b.dataset.id === id) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current'); });
  const b = $('rows').querySelector('button[data-id="' + CSS.escape(id) + '"]');
  if (b) { b.scrollIntoView({block: 'nearest'}); if (opts && opts.focus) b.focus({preventScroll: true}); }
  renderCase(); renderMap();
  loadCase(id, false);
}
async function loadCase(id, quiet) {
  if (Pending.id === id || Pending.busy === id) return;
  W.loadingId = id;
  try {
    const c = await api('GET', '/api/cases/' + encodeURIComponent(id));
    const same = quiet && W.detail[id] && JSON.stringify(W.detail[id]) === JSON.stringify(c);
    W.detail[id] = c;
    if (same) { W.loadingId = null; return; }
    const it = itemById(id); if (it && it.status !== c.status) { it.status = c.status; renderRows(); }
  } catch (e) {
    if (!quiet) { if (e.status === 404) toast(t('Case {id} was not found', {id}), {error: true}); }
  }
  if (W.sel === id) { W.loadingId = null; renderCase(); }
}
async function simpleDecision(action) {
  const c = currentCase(); if (!c) return;
  const btn = $(action === 'dismiss' ? 'dismissBtn' : 'assignBtn'); btn.disabled = true;
  try {
    const u = await decide(c.id, action, action === 'assign' ? 'Assigned to the duty analyst' : '');
    afterDecision(u);
    toast(t(action === 'dismiss' ? '{id} dismissed' : '{id} assigned to the duty analyst', {id: c.id}));
  } catch (e) { toast(t('The decision was not saved: {e}', {e: e.message}), {error: true}); }
  btn.disabled = false;
}
function afterDecision(u) {
  if (!u || !u.id) { renderActions(); return; }
  W.detail[u.id] = u;
  const it = itemById(u.id); if (it) it.status = u.status;
  renderRows(); if (W.sel === u.id) renderCase();
  api('GET', '/api/kpis').then(k => { W.kpis = k; renderKpis(); renderChips(); }).catch(() => {});
}

/* ---------- case panel ---------- */
function drawnPage(c, big) {
  const cap = c.capture || {};
  const f = (cap.forms && cap.forms[0]) || null;
  const fields = f ? f.fields || [] : [];
  const lab = s => ({'card number': 'Card number', expiry: 'MM / YY', cvv: 'CVV', 'full name': 'Full name', password: 'Password', email: 'Email', phone: 'Phone number', otp: 'One-time code', username: 'Username'}[String(s).toLowerCase()] || (s.charAt(0).toUpperCase() + s.slice(1)));
  let inputs = '';
  if (fields.length) {
    let i = 0;
    if (fields.length % 2 === 1) { inputs += '<div class="inp">' + esc(lab(fields[0])) + '</div>'; i = 1; }
    for (; i < fields.length; i += 2) inputs += '<div class="inr"><div class="inp">' + esc(lab(fields[i])) + '</div>' + (fields[i + 1] ? '<div class="inp">' + esc(lab(fields[i + 1])) + '</div>' : '') + '</div>';
  }
  const pay = fields.some(x => /card/i.test(x)) ? 'Pay now' : 'Continue';
  const urlTxt = big ? (cap.final_url || c.url || '').replace(/^https?:\/\//, '').replace(/\/$/, '') : (c.domain || host(cap.final_url || c.url || ''));
  const exId = big && c.evidence ? (c.evidence.find(e => e.kind === 'form_target') || {}).id : null;
  return '<div class="frame" aria-hidden="true"><div class="bar">' + I.lock + '<span>' + esc(urlTxt) + '</span></div>' +
    '<div class="pgh">' + I.pageico + '<span>' + esc(cap.title || 'Page') + '</span></div>' +
    '<div class="pgb">' + (f && f.posts_to ? '<div class="amt"><span>Posts to</span><b>' + esc(f.posts_to) + '</b></div>' : '') +
    (inputs ? '<div class="form">' + (exId ? '<span class="exn">' + esc(exId) + '</span>' : '') + inputs + '</div><div class="pay">' + pay + '</div>' : '') + '</div></div>';
}
function shotHtml(c, big) {
  const cap = c.capture || {};
  if (!cap.available) return '<div class="frame"><div class="none">' + esc(t('No capture yet')) + '</div></div>';
  if (cap.screenshot && S.mode === 'live' && !S.mockParts.has('cases')) {
    return '<div class="frame shotimg"><div class="bar">' + I.lock + '<span>' + esc(c.domain || host(cap.final_url || '')) + '</span></div><img alt="' + esc(cap.title || 'Captured page') + '" src="' + esc(cap.screenshot) + '" data-fallback="1"></div>';
  }
  return drawnPage(c, big);
}
function wireShotFallback(root, c, big) {
  root.querySelectorAll('img[data-fallback]').forEach(img => img.addEventListener('error', () => {
    const fr = img.closest('.frame'); if (fr) fr.outerHTML = drawnPage(c, big);
  }, {once: true}));
}
function captionHtml(c) {
  const cap = c.capture || {};
  if (!cap.available) return '';
  const when = fmtTime(cap.captured_at);
  const def = /^Captured in sandbox, no form submitted\.?$/.test(cap.note || '');
  const txt = def || !cap.note ? t('Captured {t} in sandbox, no form submitted', {t: when}) : (cap.note.replace(/^Captured /, 'Captured ' + when + ' '));
  return '<div class="capt">' + I.shot + '<span>' + esc(txt) + '</span></div>';
}
function jaisHtml(c) {
  const s = c.summary; if (!s || (!s.en && !s.ar)) return '';
  const note = !s.note || s.note === 'model writes, does not decide' ? t('model writes, does not decide') : s.note;
  return '<div class="jais"><div class="jl">' + I.lines + '<span><b>' + esc(t('Summary by {m}', {m: s.model || 'Jais'})) + '</b>, ' + esc(note) + '</span></div>' +
    (s.en ? '<div class="jen" lang="en" dir="ltr">' + esc(smart(s.en)) + '</div>' : '') + (s.ar ? '<div class="jar" lang="ar" dir="rtl">' + latinRuns(s.ar) + '</div>' : '') + '</div>';
}
function renderCase() {
  const id = W.sel; if (!id) return;
  const c = W.detail[id] || itemById(id);
  const head = $('caseHead'), body = $('caseBody');
  if (!c) { body.innerHTML = '<p class="loading">' + esc(t('Loading')) + '</p>'; return; }
  const scroller = body.parentNode, keepTop = W.renderedId === id ? scroller.scrollTop : 0;
  const th = c.threshold || (W.status && W.status.model && W.status.model.threshold) || 0.8;
  const n = votesAbove(c, th);
  const [chip] = splitDetail(c.channel_detail);
  const isMaps = c.channel === 'maps';
  head.innerHTML = '<span>' + esc(t('Case')) + ' <b class="ltr" dir="ltr">' + esc(c.id) + '</b></span><span class="ch">' + chIcon(c.channel) + esc(chipText(chip)) + '</span>' + stHtml(c.status) +
    '<a class="openbtn" href="' + esc(caseHref(c.id)) + '">' + I.ext + esc(t('Open case file')) + '</a>';
  let meta;
  if (isMaps && c.listing) {
    meta = esc(t('Category')) + ' <b>' + esc(c.listing.category || '') + '</b>' + (c.listing.phone_shared_with ? ' · ' + esc(t('phone on {n} listings', {n: c.listing.phone_shared_with})) : '') +
      (c.age_days != null ? ' · ' + esc(t('first seen {d}', {d: days(c.age_days)})) : '') + (n != null ? ' · ' + esc(t('votes')) + ' <b>' + esc(t('{n} of 4', {n})) + '</b>' : '');
  } else {
    meta = esc(t('Imitates')) + ' ' + imitatesHtml(c.imitates) + (c.age_days != null ? ' · ' + esc(t('first seen {d}', {d: days(c.age_days)})) : '') + (n != null ? ' · ' + esc(t('votes')) + ' <b>' + esc(t('{n} of 4', {n})) + '</b>' : '');
  }
  const V = c.votes || {};
  const model = (k, l) => '<div class="sc"><div class="l">' + l + '</div><div class="v">' + rk(V[k]) + '</div><div class="b"><i style="width:' + Math.round((V[k] || 0) * 100) + '%"></i><u style="left:' + Math.round(th * 100) + '%"></u></div></div>';
  const ev = c.evidence || [];
  let h = '<h2 class="ctitle" id="caseTitle">' + (isMaps ? esc(c.display) : ltr(c.display || c.domain)) + '</h2>' +
    '<div class="cmeta tn">' + meta + '</div>' +
    '<div class="score"><div class="sc' + (c.risk >= th ? '' : ' lo') + '"><div class="l">' + esc(t('Final risk')) + '</div><div class="v">' + rk(c.risk) + '</div></div>' +
    model('adaboost', 'AdaBoost') + model('bagging', 'Bagging') + model('stacking', 'Stacking') + model('voting', 'Voting') + '</div>';
  if (c._partial) {
    h += '<p class="notice">' + esc(t('Full detail for this case is not in the demo data set. The live service provides it.')) + '</p>';
  } else {
    h += '<div class="cap"><div class="shot">' + shotHtml(c, false) + '</div><div class="why"><div class="sh">' + esc(t('Why it was flagged')) + '</div>' +
      (c.reasons || []).slice(0, 4).map(r => '<div class="rs"><span class="i">' + reasonIcon(r) + '</span><span dir="auto">' + esc(smart(r)) + '</span></div>').join('') + '</div></div>' +
      captionHtml(c);
    if (ev.length) {
      h += '<div class="hr"></div><div class="sh">' + esc(t('Evidence')) + '<span class="r">' + esc(t('{n} items', {n: ev.length})) + '</span></div><ul class="ev">' +
        ev.map(e => '<li class="evr"><span class="x" dir="auto">' + highlightDomains(e.label, c.domain) + '</span><span class="src">' + esc(String(e.source || '').replace(/ capture$/, '')) + '</span></li>').join('') + '</ul>';
    }
    h += jaisHtml(c);
  }
  body.innerHTML = h;
  scroller.scrollTop = keepTop; W.renderedId = id;
  wireShotFallback(body, c, false);
  renderActions();
}
function renderActions() {
  const c = currentCase() || itemById(W.sel);
  const hold = $('holdBtn');
  paintHold(hold, holdState(c), c ? lastDecisionTime(c, 'confirm') : '');
  const busy = !c || Pending.id === (c && c.id) || Pending.busy === (c && c.id);
  $('dismissBtn').disabled = busy || (c && c.status === 'dismissed');
  $('assignBtn').disabled = busy;
  const ex = (c && c.exports) || Object.keys(EXPORT_LABEL);
  $('exportsLine').innerHTML = esc(t('Exports to')) + ' ' + ex.map(k => '<b>' + esc(t(EXPORT_LABEL[k] || k)) + '</b>').join(', ');
}

/* ---------- map ---------- */
const GEO = {
  coast: [[53.90, 24.27], [54.10, 24.28], [54.25, 24.29], [54.33, 24.31], [54.40, 24.33], [54.45, 24.355], [54.47, 24.375], [54.488, 24.392], [54.51, 24.402], [54.53, 24.424], [54.56, 24.442], [54.59, 24.455], [54.62, 24.47], [54.66, 24.49], [54.70, 24.52], [54.75, 24.56], [54.80, 24.60], [54.90, 24.66], [55.05, 24.75]],
  island: [[54.318, 24.478], [54.330, 24.488], [54.345, 24.497], [54.360, 24.507], [54.375, 24.518], [54.388, 24.526], [54.397, 24.518], [54.400, 24.500], [54.408, 24.482], [54.420, 24.465], [54.438, 24.448], [54.458, 24.432], [54.476, 24.419], [54.488, 24.410], [54.484, 24.402], [54.468, 24.403], [54.450, 24.410], [54.425, 24.420], [54.400, 24.428], [54.375, 24.434], [54.352, 24.440], [54.335, 24.450], [54.322, 24.462]],
  reem: [[54.406, 24.526], [54.418, 24.514], [54.428, 24.497], [54.422, 24.489], [54.411, 24.500], [54.403, 24.515]],
  saadiyat: [[54.405, 24.545], [54.430, 24.557], [54.460, 24.562], [54.480, 24.555], [54.475, 24.540], [54.445, 24.535], [54.420, 24.535]],
  yas: [[54.585, 24.518], [54.605, 24.522], [54.625, 24.510], [54.632, 24.490], [54.622, 24.474], [54.600, 24.472], [54.588, 24.488]],
  lulu: [[54.322, 24.500], [54.335, 24.508], [54.343, 24.502], [54.335, 24.494], [54.325, 24.494]],
  hud: [[54.300, 24.445], [54.318, 24.448], [54.325, 24.435], [54.310, 24.425], [54.298, 24.432]],
  khalifa: [[54.555, 24.432], [54.600, 24.438], [54.628, 24.420], [54.620, 24.392], [54.575, 24.385], [54.552, 24.405]],
  mussafah: [[54.462, 24.372], [54.505, 24.384], [54.540, 24.370], [54.548, 24.335], [54.505, 24.318], [54.465, 24.335]],
  roads: [
    [[54.326, 24.468], [54.346, 24.485], [54.370, 24.503], [54.386, 24.516]],
    [[54.335, 24.472], [54.370, 24.462], [54.405, 24.446], [54.440, 24.430], [54.470, 24.414], [54.490, 24.404], [54.520, 24.402], [54.560, 24.414], [54.610, 24.425], [54.660, 24.438], [54.720, 24.470], [54.790, 24.520]],
    [[54.360, 24.505], [54.380, 24.485], [54.398, 24.465], [54.420, 24.446], [54.445, 24.428]],
    [[54.405, 24.505], [54.418, 24.522], [54.432, 24.540], [54.452, 24.549]],
    [[54.490, 24.404], [54.540, 24.430], [54.590, 24.450], [54.640, 24.470], [54.700, 24.505], [54.780, 24.560]],
    [[54.490, 24.400], [54.500, 24.360], [54.505, 24.300], [54.515, 24.230]],
    [[54.330, 24.305], [54.400, 24.330], [54.460, 24.360], [54.500, 24.380]]
  ],
  labels: [
    [54.310, 24.385, 'Arabian Gulf', 'الخليج العربي', 'sea'], [54.522, 24.448, 'Khor Al Maqta', 'خور المقطع', 'water'],
    [54.403, 24.447, 'Abu Dhabi Island', 'جزيرة أبوظبي', 'main'], [54.448, 24.505, 'Al Reem', 'الريم', 'isl'],
    [54.440, 24.578, 'Saadiyat Island', 'جزيرة السعديات', 'isl'], [54.610, 24.537, 'Yas Island', 'جزيرة ياس', 'isl'],
    [54.593, 24.389, 'Khalifa City', 'مدينة خليفة', 'dist'], [54.487, 24.325, 'Mussafah', 'مصفح', 'dist'], [54.655, 24.448, 'Airport', 'المطار', 'poi']
  ]
};
const VBW = 1440, VBH = 816;
function projector(b) {
  const R = {x: 445, y: 68, w: 801, h: 672};
  b = b || {south: 24.20, west: 54.25, north: 24.62, east: 54.80};
  const k = Math.cos(((b.north + b.south) / 2) * Math.PI / 180);
  const sx = (b.east - b.west) * k, sy = b.north - b.south;
  const s = Math.min(R.w / sx, R.h / sy);
  const x0 = R.x + (R.w - sx * s) / 2, y0 = R.y + (R.h - sy * s) / 2;
  return (lng, lat) => [x0 + (lng - b.west) * k * s, y0 + (b.north - lat) * s];
}
function sm(p, closed) {
  const n = p.length, g = i => (closed ? p[(i + n) % n] : p[Math.max(0, Math.min(n - 1, i))]);
  let d = 'M' + p[0][0].toFixed(1) + ',' + p[0][1].toFixed(1);
  const last = closed ? n : n - 1;
  for (let i = 0; i < last; i++) {
    const a = g(i - 1), b = g(i), c = g(i + 1), e = g(i + 2);
    const c1 = [b[0] + (c[0] - a[0]) / 6, b[1] + (c[1] - a[1]) / 6], c2 = [c[0] - (e[0] - b[0]) / 6, c[1] - (e[1] - b[1]) / 6];
    d += 'C' + c1[0].toFixed(1) + ',' + c1[1].toFixed(1) + ' ' + c2[0].toFixed(1) + ',' + c2[1].toFixed(1) + ' ' + c[0].toFixed(1) + ',' + c[1].toFixed(1);
  }
  return d + (closed ? 'Z' : '');
}
function clipSeg(x1, y1, x2, y2, bb) {
  let t0 = 0, t1 = 1; const dx = x2 - x1, dy = y2 - y1;
  const P = [-dx, dx, -dy, dy], Q = [x1 - bb[0], bb[2] - x1, y1 - bb[1], bb[3] - y1];
  for (let i = 0; i < 4; i++) {
    if (P[i] === 0) { if (Q[i] < 0) return null; continue; }
    const r = Q[i] / P[i];
    if (P[i] < 0) { if (r > t1) return null; if (r > t0) t0 = r; } else { if (r < t0) return null; if (r < t1) t1 = r; }
  }
  return [x1 + t0 * dx, y1 + t0 * dy, x1 + t1 * dx, y1 + t1 * dy];
}
function bbox(pts) { const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]); return [Math.max(0, Math.min(...xs)), Math.max(0, Math.min(...ys)), Math.min(VBW, Math.max(...xs)), Math.min(VBH, Math.max(...ys))]; }
function grid(cx, cy, ang, len, n, gap, clip, bb) {
  const a = ang * Math.PI / 180, ux = Math.cos(a), uy = Math.sin(a), px = -uy, py = ux;
  let s = '<g clip-path="url(#' + clip + ')" stroke="#FFFFFF" stroke-width="1.2" vector-effect="non-scaling-stroke">';
  for (let i = -n; i <= n; i++) {
    const ox = cx + px * i * gap, oy = cy + py * i * gap;
    const seg = clipSeg(ox - ux * len, oy - uy * len, ox + ux * len, oy + uy * len, bb);
    if (seg) s += '<line x1="' + seg[0].toFixed(1) + '" y1="' + seg[1].toFixed(1) + '" x2="' + seg[2].toFixed(1) + '" y2="' + seg[3].toFixed(1) + '"/>';
  }
  return s + '</g>';
}
let landCache = {key: '', html: ''};
function landHtml(P) {
  const key = JSON.stringify(W.map && W.map.bounds || null);
  if (landCache.key === key) return landCache.html;
  const pr = arr => arr.map(p => P(p[0], p[1]));
  const cl = arr => arr.map(p => [Math.max(0, Math.min(VBW, p[0])), Math.max(0, Math.min(VBH, p[1]))]);
  const coast = cl(pr(GEO.coast));
  const mainPts = coast.concat([[VBW, VBH], [0, VBH]]);
  const mainD = sm(coast, false) + ' L' + VBW + ',' + VBH + ' L0,' + VBH + ' Z';
  const isl = pr(GEO.island), others = ['reem', 'saadiyat', 'yas', 'lulu', 'hud'].map(k => pr(GEO[k]));
  let h = '<defs><clipPath id="cIsl"><path d="' + sm(isl, true) + '"/></clipPath><clipPath id="cMain"><path d="' + mainD + '"/></clipPath></defs>';
  const halo = 'fill="none" stroke="#E7EFF7" stroke-linejoin="round"';
  h += '<path d="' + mainD + '" ' + halo + ' stroke-width="18"/>';
  [isl].concat(others).forEach(s => { h += '<path d="' + sm(s, true) + '" ' + halo + ' stroke-width="14"/>'; });
  h += '<path d="' + mainD + '" fill="#F3F6F9" stroke="#C4D4E4" stroke-width="1" vector-effect="non-scaling-stroke"/>';
  h += '<path d="' + sm(isl, true) + '" fill="#EDF1F6" stroke="#C4D4E4" stroke-width="1" vector-effect="non-scaling-stroke"/>';
  others.forEach(s => { h += '<path d="' + sm(s, true) + '" fill="#F0F4F8" stroke="#C4D4E4" stroke-width="1" vector-effect="non-scaling-stroke"/>'; });
  const kh = pr(GEO.khalifa), mu = pr(GEO.mussafah);
  h += '<g fill="#E9EEF4"><path d="' + sm(kh, true) + '"/><path d="' + sm(mu, true) + '"/></g>';
  const ib = bbox(isl), kb = bbox(kh), mb = bbox(mu), main = bbox(mainPts);
  const ic = [(ib[0] + ib[2]) / 2, (ib[1] + ib[3]) / 2];
  h += grid(ic[0], ic[1], 24, 190, 6, 20, 'cIsl', ib) + grid(ic[0], ic[1], -66, 120, 13, 21, 'cIsl', ib);
  const kc = [(kb[0] + kb[2]) / 2, (kb[1] + kb[3]) / 2], mc = [(mb[0] + mb[2]) / 2, (mb[1] + mb[3]) / 2];
  h += grid(kc[0], kc[1], 32, 70, 3, 17, 'cMain', kb) + grid(kc[0], kc[1], -58, 60, 3, 19, 'cMain', kb);
  h += grid(mc[0], mc[1], 8, 80, 3, 16, 'cMain', mb) + grid(mc[0], mc[1], -82, 50, 4, 20, 'cMain', mb);
  void main;
  GEO.roads.forEach((r, i) => {
    const d = sm(pr(r), false), w = [2.4, 3.2, 2.2, 2.6, 3, 2.4, 2.4][i] || 2.4;
    h += '<path d="' + d + '" fill="none" stroke="#CCD8E5" stroke-width="' + (w + 2.4) + '" stroke-linecap="round" stroke-linejoin="round"/>' +
         '<path d="' + d + '" fill="none" stroke="#FFFFFF" stroke-width="' + w + '" stroke-linecap="round" stroke-linejoin="round"/>';
  });
  const ap = P(54.651, 24.433);
  h += '<g stroke="#D2DCE7" stroke-width="5" stroke-linecap="round"><line x1="' + (ap[0] - 22).toFixed(1) + '" y1="' + (ap[1] + 12).toFixed(1) + '" x2="' + (ap[0] + 22).toFixed(1) + '" y2="' + (ap[1] - 14).toFixed(1) + '"/><line x1="' + (ap[0] - 14).toFixed(1) + '" y1="' + (ap[1] + 26).toFixed(1) + '" x2="' + (ap[0] + 30).toFixed(1) + '" y2="' + (ap[1]).toFixed(1) + '"/></g>';
  landCache = {key, html: h};
  return h;
}
function viewXY(p) { const v = W.view; return [VBW / 2 + (p[0] - v.cx) * v.z, VBH / 2 + (p[1] - v.cy) * v.z]; }
function inView(p, m) { return p[0] >= -m && p[0] <= VBW + m && p[1] >= -m && p[1] <= VBH + m; }
function focusPin() {
  const M = W.map; if (!M || !M.listings) return null;
  const P = projector(M.bounds);
  let l = M.listings.find(x => x.case_id && x.case_id === W.sel);
  if (!l) l = M.listings.filter(x => x.mismatch).sort((a, b) => b.risk - a.risk)[0];
  if (!l) return null;
  const p = P(l.lng, l.lat);
  return {l, x: p[0], y: p[1]};
}
function renderMap() {
  const svg = $('map'); if (!svg) return;
  svg.style.direction = 'ltr';
  const M = W.map;
  const P = projector(M && M.bounds);
  const v = W.view;
  let h = '<rect x="0" y="0" width="' + VBW + '" height="' + VBH + '" fill="#DCE8F3"/>';
  h += '<g transform="translate(' + (VBW / 2) + ' ' + (VBH / 2) + ') scale(' + v.z + ') translate(' + (-v.cx) + ' ' + (-v.cy) + ')">' + landHtml(P) + '</g>';
  /* labels in view space so text keeps its size */
  const LS = {sea: {s: 13, i: 1, c: '#46627F', h: '#DCE8F3', w: 500, ls: '0.05em'}, water: {s: 11, i: 1, c: '#46627F', h: '#DCE8F3', w: 500}, main: {s: 12, ls: '0.06em'},
    isl: {h: '#F0F4F8'}, dist: {h: '#E9EEF4'}, poi: {w: 500, c: '#475A70', h: '#F3F6F9'}};
  GEO.labels.forEach(L => {
    const p = viewXY(P(L[0], L[1])); const o = LS[L[4]] || {};
    if (!inView(p, -30)) return;
    h += '<text x="' + p[0].toFixed(1) + '" y="' + p[1].toFixed(1) + '" font-family="Inter, Noto Sans Arabic" font-size="' + (o.s || 11) + '" font-weight="' + (o.w || 600) + '" fill="' + (o.c || '#33475D') + '"' + (o.i && S.lang !== 'ar' ? ' font-style="italic"' : '') +
      ' text-anchor="middle" letter-spacing="' + (S.lang === 'ar' ? '0' : (o.ls || '0.03em')) + '" paint-order="stroke" stroke="' + (o.h || '#EDF1F6') + '" stroke-width="3.5" stroke-linejoin="round">' + esc(S.lang === 'ar' ? L[3] : L[2]) + '</text>';
  });
  const pinsBox = $('pins'); let btns = '';
  const tag = $('tag');
  if (M && M.listings) {
    const pts = M.listings.map(l => ({l, p: viewXY(P(l.lng, l.lat))}));
    const f = focusPin();
    const fp = f ? pts.find(q => q.l === f.l) : null;
    const groups = {};
    pts.forEach(q => { if (q.l.phone_group) (groups[q.l.phone_group] = groups[q.l.phone_group] || []).push(q); });
    let lines = '';
    Object.keys(groups).forEach(g => {
      const arr = groups[g]; if (arr.length < 2) return;
      const hub = arr.indexOf(fp) >= 0 ? fp : arr.slice().sort((a, b) => b.l.risk - a.l.risk)[0];
      const mis = arr.some(q => q.l.mismatch);
      const hy = hub === fp ? 24.3 : 18;
      arr.forEach(q => {
        if (q === hub || (!q.l.mismatch && !W.showVerified)) return;
        lines += '<line x1="' + hub.p[0].toFixed(1) + '" y1="' + (hub.p[1] - hy).toFixed(1) + '" x2="' + q.p[0].toFixed(1) + '" y2="' + (q.p[1] - (q.l.mismatch ? 13 : 0)).toFixed(1) + '" stroke="' + (mis ? '#FD614B' : '#034A89') + '" stroke-width="1.5" stroke-dasharray="4 4" opacity="' + (mis ? '.9' : '.5') + '"/>';
      });
    });
    h += lines;
    if (W.showVerified) pts.forEach(q => { if (!q.l.mismatch && inView(q.p, 0)) h += '<circle cx="' + q.p[0].toFixed(1) + '" cy="' + q.p[1].toFixed(1) + '" r="6.5" fill="#034A89" stroke="#FEFDFE" stroke-width="2"/>'; });
    const tear = (x, y, k) => '<g transform="translate(' + x.toFixed(1) + ' ' + y.toFixed(1) + ') scale(' + (k || 1) + ')"><ellipse cx="0" cy="0" rx="4.5" ry="1.6" fill="rgba(13,39,66,.22)"/>' +
      '<path d="M0 0C-1.3-3.8-7.5-8.4-7.5-13.6a7.5 7.5 0 1 1 15 0C7.5-8.4 1.3-3.8 0 0z" fill="#FD614B" stroke="#FEFDFE" stroke-width="1.6"/><circle cx="0" cy="-13.6" r="2.7" fill="#FEFDFE"/></g>';
    pts.forEach(q => { if (q.l.mismatch && q !== fp && inView(q.p, 0)) h += tear(q.p[0], q.p[1], 1); });
    if (fp && inView(fp.p, 0)) {
      const sel = fp.l.case_id === W.sel;
      h += '<circle cx="' + fp.p[0].toFixed(1) + '" cy="' + (fp.p[1] - 18).toFixed(1) + '" r="22" fill="#FD614B" opacity="' + (sel ? '.2' : '.14') + '"/>';
      h += '<circle cx="' + fp.p[0].toFixed(1) + '" cy="' + (fp.p[1] - 18).toFixed(1) + '" r="22" fill="none" stroke="#FD614B" stroke-width="' + (sel ? 1.5 : 1) + '" opacity=".6"/>';
      h += fp.l.mismatch ? tear(fp.p[0], fp.p[1], 1.35) : '<circle cx="' + fp.p[0].toFixed(1) + '" cy="' + fp.p[1].toFixed(1) + '" r="8" fill="#034A89" stroke="#FEFDFE" stroke-width="2.4"/>';
    }
    /* HTML buttons over pins that open a case, and the floating tag */
    const st = $('stage'); const SW = st.clientWidth, SH = st.clientHeight;
    const sc = Math.max(SW / VBW, SH / VBH), ox = (SW - VBW * sc) / 2, oy = (SH - VBH * sc) / 2;
    const px = p => [ox + p[0] * sc, oy + p[1] * sc];
    pts.forEach(q => {
      if (!q.l.case_id || !q.l.mismatch) return;
      const a = px(q.p); if (a[0] < 0 || a[1] < 0 || a[0] > SW || a[1] > SH) return;
      btns += '<button type="button" class="pinbtn" data-id="' + esc(q.l.case_id) + '" style="left:' + a[0].toFixed(1) + 'px;top:' + a[1].toFixed(1) + 'px" aria-label="' +
        esc(t('Map listing {id}, {cat}, risk {r}', {id: q.l.case_id, cat: q.l.category || '', r: rk(q.l.risk)})) + '"></button>';
    });
    pinsBox.innerHTML = btns;
    if (fp && inView(fp.p, 0)) {
      const it = fp.l.case_id ? (itemById(fp.l.case_id) || W.detail[fp.l.case_id]) : null;
      const grp = fp.l.phone_group ? (groups[fp.l.phone_group] || []).length : 0;
      $('tagA').textContent = it ? it.display : (fp.l.category || '') + (fp.l.case_id ? ' ' + fp.l.case_id : '');
      $('tagB').textContent = grp >= 2 ? t('Same phone on {n} listings', {n: grp}) : (fp.l.category || '');
      $('tagS').textContent = rk(fp.l.risk);
      tag.hidden = false;
      const a = px([fp.p[0], fp.p[1] - 18 * 1.35]);
      const tw = tag.offsetWidth, thh = tag.offsetHeight;
      const rtl = S.lang === 'ar';
      const leftEdge = parseFloat(getComputedStyle($('kpis')).left) || 0;
      let L = a[0] - 28 * sc - tw;
      if (L < leftEdge + 8) L = a[0] + 28 * sc;
      tag.style.left = L.toFixed(1) + 'px'; tag.style.right = 'auto';
      tag.style.top = Math.max(84, a[1] - thh / 2).toFixed(1) + 'px';
      void rtl;
    } else tag.hidden = true;
  } else { pinsBox.innerHTML = ''; tag.hidden = true; }
  svg.innerHTML = h;
  const chk = M ? M.checked : null, mis = M ? M.mismatches : null;
  $('lgdT').innerHTML = esc(t('Maps check')) + '<span>' + (chk != null ? num(chk) + ' ' + esc(t('listings checked')) : '') + '</span>';
  $('lgdM').textContent = mis != null ? num(mis) : '';
  $('lgdV').textContent = chk != null && mis != null ? num(chk - mis) : '';
}
function zoom(f) { const v = W.view; v.z = Math.max(1, Math.min(4, v.z * f)); if (v.z === 1) { v.cx = 720; v.cy = 408; } renderMap(); }
function wirePan() {
  const svg = $('map'); let drag = null;
  svg.addEventListener('pointerdown', e => { if (W.view.z <= 1) return; drag = {x: e.clientX, y: e.clientY, cx: W.view.cx, cy: W.view.cy}; svg.setPointerCapture(e.pointerId); });
  svg.addEventListener('pointermove', e => {
    if (!drag) return;
    const st = $('stage'); const sc = Math.max(st.clientWidth / VBW, st.clientHeight / VBH);
    W.view.cx = drag.cx - (e.clientX - drag.x) / (sc * W.view.z); W.view.cy = drag.cy - (e.clientY - drag.y) / (sc * W.view.z);
    renderMap();
  });
  svg.addEventListener('pointerup', () => { drag = null; });
  $('pins').addEventListener('click', e => { const b = e.target.closest('.pinbtn'); if (b) selectCase(b.dataset.id, {focus: false}); });
}
function renderActivity() {
  if (!W.kpis) return;
  const r = renderBars($('chart'), W.kpis, {w: 356, h: 84, base: 62, per: 7, bw: 9, peakValue: true, labelEvery: 4, labelGap: 15, firstStart: true});
  $('peak').textContent = r && r.peak && r.peak.count ? t('Peak {n} at {t}', {n: r.peak.count, t: fmtTime(r.peak.hour)}) : '';
  const s = W.kpis.channel_split || {};
  const max = Math.max(1, ...Object.values(s));
  const total = Object.values(s).reduce((a, b) => a + b, 0);
  $('splitSub').textContent = t("today's {n} flags", {n: num(W.kpis.flagged != null ? W.kpis.flagged : total)});
  $('split').innerHTML = [['search', 'Search'], ['certificates', 'Certificates'], ['maps', 'Maps'], ['feeds', 'Feeds']].map(d =>
    '<div class="sr"><span>' + esc(t(d[1])) + '</span><span class="b"><i style="width:' + ((s[d[0]] || 0) / max * 100).toFixed(2) + '%"></i></span><b>' + num(s[d[0]] || 0) + '</b></div>').join('');
}

/* ================================================================ boot */
function boot() {
  initCore();
  if (document.body.dataset.page === 'watch') initWatch();
  if (window.MirsadCase) window.MirsadCase();
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
