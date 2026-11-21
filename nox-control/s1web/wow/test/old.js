const { chromium } = require('playwright');
(async () => { const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
 for (const pg of ['index.html', 'chat-classic.html', 'settings.html']) { const p = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage(); const errs = [];
  p.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 160)); }); p.on('pageerror', (e) => errs.push('PAGEERR ' + e.message.slice(0, 160)));
  await p.goto('http://127.0.0.1:8191/web/' + pg); await p.waitForTimeout(3500);
  const st = await p.evaluate(() => window.NOXPlanet ? [window.NOXPlanet.get(), window.NOXPlanet.status && window.NOXPlanet.status()] : null);
  if (pg === 'settings.html') { await p.evaluate(() => window.NOXPlanet && window.NOXPlanet.set('mars')); await p.waitForTimeout(1500); }
  console.log(pg, JSON.stringify(st), 'errors:', errs.filter((e) => !/api\//.test(e) && !/503|S2 paused/.test(e)).slice(0, 4).join(' || ')); await p.screenshot({ path: '/tmp/shots/cine-old-' + pg.replace('.html', '') + '.png' }); }
 await b.close(); })();
