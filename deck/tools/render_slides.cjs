// Renders deck/Mirsad_Deck.html to one PNG per slide (deck/_render/NN.png) and to deck/Mirsad_Deck.pdf,
// and reports layout problems: text outside its slide, text smaller than 20 px, fonts that did not load,
// and script errors. Images for the PPTX are exported too (deck/_render/art/*.png).
// Usage: node deck/tools/render_slides.cjs [--no-pdf]
// Needs Playwright with Chromium. Set PLAYWRIGHT_MODULE to its folder if it is not installed here.
const path = require('path');
const fs = require('fs');
let pw;
try { pw = require('playwright'); } catch (e) { pw = require(process.env.PLAYWRIGHT_MODULE || 'D:/gamefit-web/node_modules/playwright'); }

const DECK = path.resolve(__dirname, '..');
const OUT = path.join(DECK, '_render');
const url = (q) => 'file:///' + path.join(DECK, 'Mirsad_Deck.html').replace(/\\/g, '/') + q;

(async () => {
  fs.mkdirSync(path.join(OUT, 'art'), { recursive: true });
  const browser = await pw.chromium.launch(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {});
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  page.on('requestfailed', (r) => errors.push('requestfailed: ' + r.url()));

  await page.goto(url('?still#1'));
  await page.evaluate(() => document.fonts.ready);
  const n = await page.evaluate(() => document.querySelectorAll('.slide').length);
  const report = [];
  for (let i = 1; i <= n; i++) {
    await page.evaluate((i) => { location.hash = '#' + i; }, i);
    await page.waitForTimeout(250);
    const r = await page.evaluate((i) => {
      const s = document.querySelectorAll('.slide')[i - 1];
      const box = s.getBoundingClientRect();
      const scale = box.width / 1920;
      const out = [], small = [];
      s.querySelectorAll('*').forEach((el) => {
        if (el.closest('.notes') || el.closest('svg')) return;
        const own = [...el.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim().length > 1);
        if (!own) return;
        const b = el.getBoundingClientRect();
        if (!b.width) return;
        const x = (b.left - box.left) / scale, y = (b.top - box.top) / scale, w = b.width / scale, h = b.height / scale;
        if (x < 40 || y < 40 || x + w > 1880 || y + h > 1040) out.push(el.tagName + ' "' + el.textContent.trim().slice(0, 40) + '" at ' + Math.round(x) + ',' + Math.round(y) + ' ' + Math.round(w) + 'x' + Math.round(h));
        const fs = parseFloat(getComputedStyle(el).fontSize);
        if (fs < 20) small.push(fs + 'px "' + el.textContent.trim().slice(0, 30) + '"');
      });
      return { slide: i, title: s.dataset.title, outside: out.slice(0, 8), small: small.slice(0, 8) };
    }, i);
    report.push(r);
    await page.screenshot({ path: path.join(OUT, String(i).padStart(2, '0') + '.png') });
  }
  const fonts = await page.evaluate(() => [...new Set([...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family + ' ' + f.weight))]);

  // Art for the PPTX: each isometric drawing on its charcoal ground, and the red signal mark.
  const arts = await page.evaluate(() => [...document.querySelectorAll('.slide')].map((s, i) => ({ i: i + 1, n: s.querySelectorAll('svg.iso').length })));
  for (const a of arts.filter((a) => a.n)) {
    await page.evaluate((i) => { location.hash = '#' + i; }, a.i);
    await page.waitForTimeout(200);
    const svgs = await page.$$('.slide.on svg.iso');
    for (let k = 0; k < svgs.length; k++) {
      await page.evaluate(() => { document.querySelectorAll('.slide.on > :not(svg.iso)').forEach((e) => { e.style.visibility = 'hidden'; }); });
      await svgs[k].screenshot({ path: path.join(OUT, 'art', `iso_s${a.i}_${k + 1}.png`), omitBackground: false });
      await page.evaluate(() => { document.querySelectorAll('.slide.on > *').forEach((e) => { e.style.visibility = ''; }); });
    }
  }

  if (!process.argv.includes('--no-pdf')) {
    const pdfPage = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    await pdfPage.goto(url('?print'));
    await pdfPage.evaluate(() => document.fonts.ready);
    await pdfPage.waitForTimeout(500);
    await pdfPage.pdf({ path: path.join(DECK, 'Mirsad_Deck.pdf'), width: '1920px', height: '1080px', printBackground: true, preferCSSPageSize: true });
  }
  console.log(JSON.stringify({ slides: n, fonts, errors, problems: report.filter((r) => r.outside.length || r.small.length) }, null, 1));
  await browser.close();
})();
