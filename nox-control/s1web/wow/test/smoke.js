const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-webgl'] });
  const [w, h, tag] = [+process.argv[2] || 1440, +process.argv[3] || 900, process.argv[4] || 'd'];
  const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, permissions: ['microphone'] });
  await ctx.addInitScript(() => { try { localStorage.setItem('nox.wow.tour', '1'); } catch (e) {} });
  const p = await ctx.newPage(); const errs = [];
  p.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errs.push(m.type() + ': ' + m.text().slice(0, 300)); });
  p.on('pageerror', (e) => errs.push('PAGEERR ' + e.message.slice(0, 300)));
  p.on('requestfailed', (r) => errs.push('REQFAIL ' + r.url().slice(0, 120)));
  p.on('response', (r) => { if (r.status() >= 400) errs.push('HTTP' + r.status() + ' ' + r.url().slice(0, 120)); });
  await p.goto('http://127.0.0.1:8191/web/chat.html', { waitUntil: 'load' });
  await p.waitForTimeout(4500);
  console.log(JSON.stringify(await p.evaluate(() => ({ lib: window.__noxWow && window.__noxWow.lib, space: window.__noxWow && !!window.__noxSpace, tex: window.__noxSpace && window.__noxSpace.state.texStatus, sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }))));
  await p.screenshot({ path: `/tmp/shots/cine-${tag}-home.png` });
  console.log('ERRS', JSON.stringify(errs, null, 1));
  await b.close();
})();
