// Builds deck/Mirsad_Deck.pptx, an editable copy of the presenting deck.
//
// It reads the rendered HTML deck (final state, ?still) slide by slide and writes native PowerPoint
// objects at the same positions: every text box with its runs (size, weight, color, spacing), every
// filled block and rule as a shape, and the speaker notes. Only the isometric drawings, the signal mark,
// and the product screenshots go in as pictures. Numbers therefore come from the same build as the
// HTML deck and the PDF (results/*.json through scripts/build_docs.py); nothing is typed here.
//
// Fonts: PowerPoint cannot use the deck's web fonts, so text is set in Inter (closest installed family)
// with letter spacing tightened by the measured difference to Inter Tight, Consolas for IBM Plex Mono,
// and Segoe UI for Arabic. The PDF keeps the exact type.
//
// Usage: node deck/tools/build_pptx.cjs
const path = require('path');
const fs = require('fs');
const PptxGenJS = require('pptxgenjs');
let pw;
try { pw = require('playwright'); } catch (e) { pw = require(process.env.PLAYWRIGHT_MODULE || 'D:/gamefit-web/node_modules/playwright'); }

const DECK = path.resolve(__dirname, '..');
const IMG = path.join(DECK, '_render', 'pptx');
const PX = 1 / 144;          // 1920 px = 13.333 in (LAYOUT_WIDE)
const PT = 0.5;              // 1 px = 0.5 pt at that scale
const FACE = { sans: 'Inter', mono: 'Consolas', ar: 'Segoe UI' };

function hex(css) {
  const m = /rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/.exec(css || '');
  if (!m) return null;
  const a = m[4] === undefined ? 1 : parseFloat(m[4]);
  const h = [m[1], m[2], m[3]].map((v) => Math.round(+v).toString(16).padStart(2, '0')).join('').toUpperCase();
  return { hex: h, alpha: a };
}

// Runs in the page: describe one slide as shapes, pictures, and text boxes in paint order.
function describe(index) {
  const slide = document.querySelectorAll('.slide')[index];
  const base = slide.getBoundingClientRect();
  const items = [];
  const shots = [];
  const isAbs = (el) => ['absolute', 'fixed'].includes(getComputedStyle(el).position);
  const hidden = (el) => { const cs = getComputedStyle(el); return cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0; };
  const rect = (el) => { const r = el.getBoundingClientRect(); return { x: r.left - base.left, y: r.top - base.top, w: r.width, h: r.height }; };
  const ownText = (el) => [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
  const family = (cs, el) => (el.closest('[lang="ar"]') ? 'ar' : /Mono/.test(cs.fontFamily) ? 'mono' : 'sans');

  // Runs of one text box, with a line break wherever the browser wrapped a line, so PowerPoint
  // shows the same lines (it would otherwise fill greedily and ignore text-wrap: balance).
  function runsOf(box) {
    const runs = [];
    let lineMid = null, pendingSpace = false;
    function style(el) {
      const cs = getComputedStyle(el);
      return { size: parseFloat(cs.fontSize), weight: parseInt(cs.fontWeight, 10), color: cs.color, family: family(cs, el),
        ls: cs.letterSpacing === 'normal' ? 0 : parseFloat(cs.letterSpacing), italic: cs.fontStyle === 'italic' };
    }
    function br() { if (runs.length) runs[runs.length - 1].br = true; pendingSpace = false; }
    function add(text, st) {
      const last = runs[runs.length - 1];
      if (last && !last.br && ['size', 'weight', 'color', 'family', 'ls', 'italic'].every((k) => last[k] === st[k])) last.text += text;
      else runs.push({ text, ...st });
    }
    function words(node, el) {
      const t = node.textContent, st = style(el);
      const re = /[^\s-]+-?|-/g;  // a hyphen ends a token, so a wrap after it is seen
      let m, any = false;
      if (/^\s/.test(t)) pendingSpace = true;
      while ((m = re.exec(t))) {
        const r = document.createRange();
        r.setStart(node, m.index); r.setEnd(node, m.index + m[0].length);
        const rc = r.getClientRects()[0];
        // a new line starts when a word's top lies below the middle of the current line; a smaller
        // run on the same baseline (95 then .5%) stays above that middle
        if (rc && lineMid !== null && rc.top > lineMid) { br(); lineMid = null; }
        if (rc && lineMid === null) lineMid = (rc.top + rc.bottom) / 2;
        add((pendingSpace && runs.length && !runs[runs.length - 1].br ? ' ' : '') + m[0], st);
        pendingSpace = /\s/.test(t.charAt(m.index + m[0].length));
        any = true;
      }
      if (!any && /\s/.test(t)) pendingSpace = true;
    }
    (function walk(el) {
      for (const n of el.childNodes) {
        if (n.nodeType === 3) { words(n, el); continue; }
        if (n.nodeType !== 1 || hidden(n) || n.tagName === 'svg' || isAbs(n)) continue;
        if (n.tagName === 'BR') { br(); continue; }
        walk(n);
      }
    })(box);
    if (runs.length) runs[runs.length - 1].br = false;
    return runs.filter((r) => r.text);
  }

  function visit(el, inBox) {
    if (el.nodeType !== 1 || hidden(el) || el.matches('.notes')) return;
    const cs = getComputedStyle(el);
    const r = rect(el);
    if (!r.w || !r.h) { if (el.tagName !== 'svg') [...el.children].forEach((c) => visit(c, inBox)); return; }
    // pictures
    if (el.matches('svg.iso, svg.sig, figure.shot')) {
      const id = 'pic' + shots.length;
      el.setAttribute('data-shot', id);
      shots.push(id);
      items.push({ kind: 'pic', id, ...r });
      return;
    }
    // filled shapes
    const bg = cs.backgroundColor;
    if (bg && !/rgba\(0, 0, 0, 0\)|transparent/.test(bg) && el !== slide) {
      items.push({ kind: 'rect', ...r, fill: bg, round: cs.borderRadius === '50%' });
    }
    // borders as rules
    for (const side of ['Top', 'Right', 'Bottom', 'Left']) {
      const w = parseFloat(cs['border' + side + 'Width']);
      if (!w || cs['border' + side + 'Style'] === 'none') continue;
      const col = cs['border' + side + 'Color'];
      const dash = cs['border' + side + 'Style'] === 'dashed';
      const L = side === 'Top' ? { x: r.x, y: r.y + w / 2, w: r.w, h: 0 }
        : side === 'Bottom' ? { x: r.x, y: r.y + r.h - w / 2, w: r.w, h: 0 }
        : side === 'Left' ? { x: r.x + w / 2, y: r.y, w: 0, h: r.h } : { x: r.x + r.w - w / 2, y: r.y, w: 0, h: r.h };
      items.push({ kind: 'line', ...L, width: w, color: col, dash });
    }
    // text boxes: an element with its own text, outside any other box, or an absolutely placed one
    const box = ownText(el) && (!inBox || isAbs(el));
    if (box) {
      const pad = ['Top', 'Right', 'Bottom', 'Left'].map((s) => parseFloat(cs['padding' + s]) + parseFloat(cs['border' + s + 'Width'] || 0));
      const lh = cs.lineHeight === 'normal' ? parseFloat(cs.fontSize) * 1.2 : parseFloat(cs.lineHeight);
      items.push({ kind: 'text', x: r.x + pad[3], y: r.y + pad[0], w: r.w - pad[1] - pad[3], h: r.h - pad[0] - pad[2],
        align: cs.textAlign === 'end' ? 'right' : cs.textAlign === 'start' ? 'left' : cs.textAlign, lh, rtl: cs.direction === 'rtl',
        valign: cs.verticalAlign === 'bottom' ? 'bottom' : cs.verticalAlign === 'middle' ? 'middle' : 'top',
        runs: runsOf(el) });
    }
    [...el.children].forEach((c) => visit(c, inBox || box));
  }
  [...slide.children].forEach((c) => visit(c, false));
  return { dark: slide.classList.contains('dark'), title: slide.dataset.title, items, shots,
    notes: (slide.querySelector('.notes') || {}).textContent || '' };
}

(async () => {
  fs.mkdirSync(IMG, { recursive: true });
  const browser = await pw.chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });
  await page.goto('file:///' + path.join(DECK, 'Mirsad_Deck.html').replace(/\\/g, '/') + '?still#1');
  await page.evaluate(() => document.fonts.ready);

  // Measured tracking difference between Inter Tight (deck) and Inter (PowerPoint), in em per character.
  const deltaEm = await page.evaluate(async () => {
    const s = 'Fraud finds people where they search 0123456789 Mirsad watches upstream';
    const m = (f) => { const c = document.createElement('canvas').getContext('2d'); c.font = '600 100px ' + f; return c.measureText(s).width; };
    return (m('"Inter Tight"') - m('Inter')) / (s.length * 100);
  });
  // While a picture is captured, only the picture and its ancestors' boxes stay visible; their own
  // backgrounds are cleared because those blocks are drawn as native shapes.
  await page.addStyleTag({ content: '.cap-hide > :not([data-shot-on]):not([data-shot-target]), .cap-hide [data-shot-on] > :not([data-shot-on]):not([data-shot-target]){visibility:hidden!important} .cap-hide, .cap-hide [data-shot-on]{background:transparent!important; clip-path:none!important} .cap-hide::before,.cap-hide::after{display:none!important} html,body{background:transparent!important}' });

  const n = await page.evaluate(() => document.querySelectorAll('.slide').length);
  const pptx = new PptxGenJS();
  pptx.layout = 'LAYOUT_WIDE';
  pptx.author = 'Mirsad team';
  pptx.title = 'Mirsad, ScamShield AI';
  const report = { slides: n, deltaEm: +deltaEm.toFixed(4), pictures: 0, texts: 0, shapes: 0 };

  for (let i = 0; i < n; i++) {
    await page.evaluate((i) => { location.hash = '#' + (i + 1); }, i);
    await page.waitForTimeout(150);
    const d = await page.evaluate(describe, i);
    // pictures: hide everything else on the slide, then screenshot the element with a transparent ground
    for (const id of d.shots) {
      await page.evaluate(({ i, id }) => {
        const s = document.querySelectorAll('.slide')[i];
        s.classList.add('cap-hide');
        const el = s.querySelector('[data-shot="' + id + '"]');
        el.setAttribute('data-shot-target', '');
        let a = el.parentElement; while (a && a !== s) { a.setAttribute('data-shot-on', ''); a = a.parentElement; }
      }, { i, id });
      const handle = await page.$(`.slide.on [data-shot="${id}"]`);
      await handle.screenshot({ path: path.join(IMG, `s${i + 1}_${id}.png`), omitBackground: true });
      await page.evaluate((i) => {
        const s = document.querySelectorAll('.slide')[i];
        s.classList.remove('cap-hide');
        s.querySelectorAll('[data-shot-on]').forEach((e) => e.removeAttribute('data-shot-on'));
        s.querySelectorAll('[data-shot-target]').forEach((e) => e.removeAttribute('data-shot-target'));
      }, i);
    }

    const sl = pptx.addSlide();
    sl.background = { color: d.dark ? '2B2D31' : 'FFFFFF' };
    if (d.dark) {
      const tan = 'C29B72';
      sl.addShape(pptx.ShapeType.rect, { x: 36 * PX, y: 36 * PX, w: 1848 * PX, h: 1008 * PX, fill: { type: 'none' }, line: { color: tan, width: 0.75, transparency: 65 } });
      for (const [x, y, dx, dy] of [[36, 36, 1, 1], [1884, 36, -1, 1], [36, 1044, 1, -1], [1884, 1044, -1, -1]]) {
        sl.addShape(pptx.ShapeType.line, { x: Math.min(x, x + 28 * dx) * PX, y: y * PX, w: 28 * PX, h: 0, line: { color: tan, width: 1.5 } });
        sl.addShape(pptx.ShapeType.line, { x: x * PX, y: Math.min(y, y + 28 * dy) * PX, w: 0, h: 28 * PX, line: { color: tan, width: 1.5 } });
      }
    }
    for (const it of d.items) {
      if (it.kind === 'pic') {
        sl.addImage({ path: path.join(IMG, `s${i + 1}_${it.id}.png`), x: it.x * PX, y: it.y * PX, w: it.w * PX, h: it.h * PX });
        report.pictures++;
      } else if (it.kind === 'rect') {
        const c = hex(it.fill);
        if (!c || c.alpha === 0) continue;
        sl.addShape(it.round ? pptx.ShapeType.ellipse : pptx.ShapeType.rect, { x: it.x * PX, y: it.y * PX, w: it.w * PX, h: it.h * PX,
          fill: { color: c.hex, transparency: Math.round((1 - c.alpha) * 100) }, line: { type: 'none' } });
        report.shapes++;
      } else if (it.kind === 'line') {
        const c = hex(it.color);
        if (!c || c.alpha === 0) continue;
        sl.addShape(pptx.ShapeType.line, { x: it.x * PX, y: it.y * PX, w: it.w * PX, h: it.h * PX,
          line: { color: c.hex, width: it.width * PT, transparency: Math.round((1 - c.alpha) * 100), dashType: it.dash ? 'dash' : 'solid' } });
        report.shapes++;
      } else if (it.kind === 'text' && it.runs.length) {
        const runs = it.runs.map((r) => {
          const c = hex(r.color) || { hex: '000000', alpha: 1 };
          const face = FACE[r.family];
          const track = r.family === 'sans' ? r.ls + deltaEm * r.size : r.ls;
          return { text: r.text, options: { fontFace: face, fontSize: +(r.size * PT).toFixed(1), bold: r.weight >= 600, italic: r.italic,
            color: c.hex, transparency: Math.round((1 - c.alpha) * 100), charSpacing: +(track * PT).toFixed(2), breakLine: !!r.br } };
        });
        sl.addText(runs, { x: it.x * PX, y: it.y * PX, w: (it.w + 4) * PX, h: Math.max(it.h, it.lh) * PX, margin: 0, valign: it.valign,
          align: it.align === 'justify' ? 'left' : it.align, lineSpacing: +(it.lh * PT).toFixed(1), rtlMode: it.rtl, fit: 'none', wrap: false });
        report.texts++;
      }
    }
    if (d.notes.trim()) sl.addNotes(d.notes.trim().replace(/\s+/g, ' '));
  }
  await browser.close();
  const out = path.join(DECK, 'Mirsad_Deck.pptx');
  await pptx.writeFile({ fileName: out });
  console.log(JSON.stringify({ ...report, out }));
})();
