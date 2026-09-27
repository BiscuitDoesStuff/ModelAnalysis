// Browser accessibility check for one ModelAnalysis bundle (offline, file:// URLs).
//
//   node tools/a11y/check.mjs <bundle> [--shots DIR] [--models N]
//
// 1. axe-core (WCAG 2 A/AA rules) on the dashboard (every tab) and the site pages,
//    in dark and light colour schemes; fails on any serious or critical violation.
// 2. Keyboard pass: skip link, tab arrow keys/Home/End, focus outline, Enter on a copy button.
// 3. Narrow screens: no page-level horizontal scroll at 390px.
// 4. --shots DIR: screenshots at 1280px and 390px in dark and light.
// Browser: Playwright's Chromium (PLAYWRIGHT_BROWSERS_PATH), or A11Y_CHROMIUM=<executable>.
import { chromium } from 'playwright';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
const AXE = require.resolve('axe-core/axe.min.js');
const args = process.argv.slice(2);
const option = name => { const i = args.indexOf(name); return i >= 0 ? args.splice(i, 2)[1] : undefined; };
const shots = option('--shots');
const modelLimit = Number(option('--models') || 12);
const bundle = args[0];
if (!bundle) {
  console.error('usage: node tools/a11y/check.mjs <bundle> [--shots DIR] [--models N]');
  process.exit(2);
}
const reports = path.join(bundle, 'reports');
const dashboard = fs.readdirSync(reports).find(f => f.endsWith('_report.html'));
const siteDir = fs.readdirSync(reports).find(f => f.endsWith('_site'));
if (!dashboard || !siteDir) throw new Error('bundle has no dashboard or site: ' + reports);
const site = path.join(reports, siteDir);
const url = file => pathToFileURL(file).href;
const modelPages = fs.readdirSync(path.join(site, 'models')).sort().slice(0, modelLimit)
  .map(f => path.join(site, 'models', f));
const sitePages = ['index.html', 'models.html', 'benchmarks.html', 'compare.html', 'methodology.html', 'confidence.html']
  .map(f => path.join(site, f)).concat(modelPages);

const failures = [];
const fail = message => { failures.push(message); console.log('FAIL ' + message); };
const ok = message => console.log('ok   ' + message);
const counts = {};

const browser = await chromium.launch(process.env.A11Y_CHROMIUM ? { executablePath: process.env.A11Y_CHROMIUM } : {});

async function axe(page, label) {
  await page.addScriptTag({ path: AXE });
  const result = await page.evaluate(() => window.axe.run(document, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'] } }));
  for (const v of result.violations) {
    counts[v.impact] = (counts[v.impact] || 0) + 1;
    const line = `${label}: [${v.impact}] ${v.id} (${v.nodes.length}) ${v.help} e.g. ${v.nodes[0].target.join(' ')}`;
    if (v.impact === 'serious' || v.impact === 'critical') fail(line);
    else console.log('note ' + line);
  }
}

async function tabs(page) {
  return page.$$eval('[role=tablist]:not([aria-label="BenchLM evidence"]) > [role=tab]', ts => ts.map(t => t.id));
}

// ---- axe, both colour schemes ----
for (const scheme of ['dark', 'light']) {
  const context = await browser.newContext({ colorScheme: scheme, viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await page.goto(url(path.join(reports, dashboard)));
  for (const id of await tabs(page)) {
    await page.click('#' + id);
    if (id === 'tab-t-graph') {  // select two models so the plot, bars and details table render
      for (let i = 0; i < 2; i++) await page.click("#g-results button[aria-pressed='false']");
    }
    await axe(page, `dashboard ${id} (${scheme})`);
  }
  for (const file of sitePages) {
    await page.goto(url(file));
    for (const id of await tabs(page)) {
      await page.click('#' + id);
      await axe(page, `site ${path.relative(site, file)} ${id} (${scheme})`);
    }
    if (!(await tabs(page)).length) await axe(page, `site ${path.relative(site, file)} (${scheme})`);
  }
  await context.close();
}
ok(`axe: ${JSON.stringify(counts)} across dashboard tabs + ${sitePages.length} site pages x 2 schemes`);

// ---- keyboard ----
{
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.grantPermissions(['clipboard-read', 'clipboard-write']).catch(() => {});
  const page = await context.newPage();
  await page.goto(url(path.join(reports, dashboard)));
  const active = () => page.evaluate(() => {
    const el = document.activeElement;
    return { tag: el.tagName.toLowerCase(), id: el.id, cls: el.className, role: el.getAttribute('role'),
             selected: el.getAttribute('aria-selected'), outline: getComputedStyle(el).outlineStyle };
  });
  await page.keyboard.press('Tab');
  let a = await active();
  a.cls === 'skip' ? ok('first Tab reaches the skip link') : fail('first Tab focused ' + JSON.stringify(a));
  a.outline !== 'none' ? ok('focused control shows an outline') : fail('no focus outline on the skip link');
  await page.keyboard.press('Enter');
  a = await active();
  a.id === 'main' ? ok('skip link moves focus to main') : fail('skip link focused ' + JSON.stringify(a));
  await page.keyboard.press('Tab');
  a = await active();
  a.role === 'tab' && a.selected === 'true' ? ok('next Tab reaches the selected tab') : fail('after skip, focus on ' + JSON.stringify(a));
  a.outline !== 'none' ? ok('tab shows a focus outline') : fail('no focus outline on tab');
  const visible = () => page.$$eval('[role=tabpanel]', ps => ps.filter(p => !p.hidden).map(p => p.id));
  await page.keyboard.press('ArrowRight');
  a = await active();
  a.id === 'tab-t-value' && a.selected === 'true' && (await visible()).includes('t-value')
    ? ok('ArrowRight selects and shows the next tab') : fail('ArrowRight -> ' + JSON.stringify(a));
  await page.keyboard.press('End');
  a = await active();
  a.id === 'tab-t-explore' && (await visible()).includes('t-explore') ? ok('End selects the last tab') : fail('End -> ' + a.id);
  await page.keyboard.press('Home');
  a = await active();
  a.id === 'tab-t-start' && (await visible()).join() === 't-start' ? ok('Home selects the first tab, one panel shown')
    : fail('Home -> ' + a.id);
  let reached = false;
  for (let i = 0; i < 80 && !reached; i++) {
    await page.keyboard.press('Tab');
    reached = (await active()).cls.includes('copy');
  }
  if (!reached) fail('Tab never reached a copy button on the Start page');
  else {
    ok('Tab reaches a copy button');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(150);
    const status = await page.textContent('#copy-status');
    status.startsWith('Copied ') || status.startsWith('Clipboard unavailable')
      ? ok(`Enter on copy announces: "${status}"`) : fail('copy announced nothing');
  }
  await page.goto(url(path.join(site, 'index.html')));
  await page.focus('#tab-l-aa');
  await page.keyboard.press('ArrowRight');
  a = await active();
  a.id === 'tab-l-b' && (await visible()).includes('l-b') ? ok('site leaderboard tabs follow arrow keys') : fail('site ArrowRight -> ' + a.id);
  await context.close();
}

// ---- narrow screens ----
{
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true });
  const page = await context.newPage();
  for (const file of [path.join(reports, dashboard), ...sitePages.slice(0, 7)]) {
    await page.goto(url(file));
    const tabIds = file.endsWith('_report.html') ? await tabs(page) : [null];
    for (const id of tabIds) {
      if (id) await page.click('#' + id);
      await axe(page, `390px ${path.basename(file)}${id ? ' ' + id : ''}`);
      const [scroll, width] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
      const name = path.basename(file) + (id ? ' ' + id : '');
      if (scroll > width + 1) fail(`${name}: page scrolls sideways at 390px (${scroll} > ${width})`);
    }
  }
  ok('390px: axe and page-level sideways scroll checked');
  await context.close();
}

// ---- screenshots ----
if (shots) {
  fs.mkdirSync(shots, { recursive: true });
  const model = modelPages.find(f => fs.readFileSync(f, 'utf8').includes('Provider routes')) || modelPages[0];
  const views = [['dashboard-start', path.join(reports, dashboard), null], ['dashboard-explore', path.join(reports, dashboard), '#tab-t-explore'],
                 ['site-index', path.join(site, 'index.html'), null], ['site-model', model, null]];
  for (const scheme of ['dark', 'light']) {
    for (const [wname, viewport] of [['desktop', { width: 1280, height: 900 }], ['phone', { width: 390, height: 844 }]]) {
      const context = await browser.newContext({ colorScheme: scheme, viewport, deviceScaleFactor: wname === 'phone' ? 2 : 1 });
      const page = await context.newPage();
      for (const [name, file, click] of views) {
        await page.goto(url(file));
        if (click) await page.click(click);
        await page.screenshot({ path: path.join(shots, `${name}-${wname}-${scheme}.png`) });
      }
      await context.close();
    }
  }
  ok('screenshots in ' + shots);
}

await browser.close();
console.log(failures.length ? `${failures.length} accessibility failure(s)` : 'a11y checks passed');
process.exit(failures.length ? 1 : 0);
