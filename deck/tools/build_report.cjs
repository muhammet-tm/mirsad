// Builds docs/Mirsad_Technical_Report.pdf from docs/TECHNICAL_REPORT.md (itself generated from
// docs/TECHNICAL_REPORT.src.md by scripts/build_docs.py, so every number comes from results/*.json).
// Usage: node deck/tools/build_report.cjs
// Needs Playwright with Chromium. Set PLAYWRIGHT_MODULE to its folder if it is not installed here.
const path = require('path');
const fs = require('fs');
const { marked } = require('marked');
let pw;
try { pw = require('playwright'); } catch (e) { pw = require(process.env.PLAYWRIGHT_MODULE || 'D:/gamefit-web/node_modules/playwright'); }

const REPO = path.resolve(__dirname, '..', '..');
const SRC = path.join(REPO, 'docs', 'TECHNICAL_REPORT.md');
const OUT = path.join(REPO, 'docs', 'Mirsad_Technical_Report.pdf');
const WORK = path.join(REPO, 'deck', '_render', 'report.html');

const CSS = `
@page { size: A4; margin: 18mm 19mm 19mm 19mm; }
:root { --red:#D7262E; --ink:#111; --grey:#5b5b5b; --rule:#d9d9d9; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; font-family: "Inter Tight", Arial, sans-serif; font-size: 10.2pt; line-height: 1.5; color: var(--ink); }
h1 { font-size: 22pt; line-height: 1.12; letter-spacing: -0.025em; margin: 0 0 8pt; padding-top: 9pt; border-top: 5pt solid var(--ink); }
h1 + p { font-size: 9.4pt; color: var(--grey); border-bottom: 1px solid var(--rule); padding-bottom: 8pt; margin-bottom: 12pt; }
h2 { font-size: 13.5pt; letter-spacing: -0.01em; margin: 16pt 0 5pt; break-after: avoid; }
h2::before { content: ""; display: block; width: 18pt; height: 3pt; background: var(--red); margin-bottom: 5pt; }
h3 { font-size: 10.8pt; margin: 11pt 0 3pt; break-after: avoid; }
p { margin: 0 0 6.5pt; text-align: left; }
ul, ol { margin: 2pt 0 7pt; padding-left: 15pt; }
li { margin-bottom: 2.5pt; }
code { font-family: "IBM Plex Mono", Consolas, monospace; font-size: 8.6pt; background: #f3f3f1; padding: 0 2pt; }
table { width: 100%; border-collapse: collapse; margin: 5pt 0 9pt; font-size: 8.4pt; line-height: 1.35; break-inside: auto; }
tr { break-inside: avoid; } thead { display: table-header-group; }
th { text-align: left; font-weight: 600; color: var(--grey); border-bottom: 1.4pt solid var(--ink); padding: 3pt 5pt 3pt 0; vertical-align: bottom; }
td { border-bottom: 1px solid var(--rule); padding: 3.5pt 5pt 3.5pt 0; vertical-align: top; }
a { color: var(--ink); text-decoration: none; }
h2#references + p, h2#references ~ p { font-size: 8.8pt; line-height: 1.4; }
`;

(async () => {
  let md = fs.readFileSync(SRC, 'utf8').replace(/^<!--[\s\S]*?-->\s*/, '');
  // The three credit lines under the title are separate lines in Markdown; keep them as line breaks.
  md = md.replace(/^(# .+\n\n)((?:.+\n)+?)\n/, (m, h, block) => h + block.trim().split('\n').join('  \n') + '\n\n');
  const body = marked.parse(md, { gfm: true });
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Mirsad technical report</title>
<link rel="stylesheet" href="../vendor/fonts/fonts.css"><style>${CSS}</style></head><body>${body}</body></html>`;
  fs.mkdirSync(path.dirname(WORK), { recursive: true });
  fs.writeFileSync(WORK, html, 'utf8');

  const browser = await pw.chromium.launch(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {});
  const page = await browser.newPage();
  const errors = [];
  page.on('requestfailed', (r) => errors.push('requestfailed: ' + r.url()));
  await page.goto('file:///' + WORK.replace(/\\/g, '/'));
  await page.evaluate(() => document.fonts.ready);
  const fonts = await page.evaluate(() => [...new Set([...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family))]);
  await page.pdf({
    path: OUT, format: 'A4', printBackground: true, preferCSSPageSize: true, displayHeaderFooter: true,
    headerTemplate: '<span></span>',
    footerTemplate: '<div style="width:100%;font-family:Arial,sans-serif;font-size:7.5pt;color:#777;padding:0 19mm;display:flex;justify-content:space-between">'
      + '<span>Mirsad technical report, ScamShield AI, November 2026</span><span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>',
  });
  await browser.close();
  console.log(JSON.stringify({ out: OUT, fonts, errors }));
})();
