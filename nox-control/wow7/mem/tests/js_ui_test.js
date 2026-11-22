// Браузерный тест правки: ok:false не должен менять факт в UI и кэше nox.facts.text. Запуск: node js_ui_test.js [путь_к_js]
const { chromium } = require('/opt/node22/lib/node_modules/playwright');
const fs = require('fs'), path = require('path');
const js = fs.readFileSync(process.argv[2] || path.join(__dirname, '../web/nox-web-extras.js'), 'utf8');
(async () => {
  const b = await chromium.launch(); const pg = await b.newPage();
  let mode = 'fail', calls = [];
  const facts = [{ id: 'f:1', text: 'старый факт', kind: 'fact' }];
  await pg.route('**/memory/api', async r => {
    const q = JSON.parse(r.request().postData()); calls.push(q.op);
    let res;
    if (q.op === 'list') res = { ok: true, facts };
    else if (q.op === 'correct') {
      if (mode === 'fail') res = { ok: false, error: 'такой факт уже есть' };
      else { facts[0].text = q.text; res = { ok: true, item: { text: q.text } }; }
    } else if (q.op === 'get') res = { ok: true, item: { id: 'f:1', text: facts[0].text, status: 'active' } };
    else res = { ok: false, error: 'неизвестная операция' };
    await r.fulfill({ contentType: 'application/json', body: JSON.stringify(res) });
  });
  await pg.route('http://t.local/memory.html', r => r.fulfill({ contentType: 'text/html', body: '<html><body><main></main></body></html>' }));
  await pg.goto('http://t.local/memory.html');
  await pg.addScriptTag({ content: js });
  await pg.waitForSelector('#nxw-fl .nxw-fact');
  const edit = async (t) => { const d = pg.locator('#nxw-fl .nxw-fact div').first(); await d.click(); await d.fill(t); await pg.locator('#nxw-q').focus(); await pg.waitForTimeout(400); return d.textContent(); };
  let shown = await edit('новый факт');
  const cache = await pg.evaluate(() => localStorage.getItem('nox.facts.text'));
  const err = await pg.locator('#nxw-merr').count();
  console.log('ok:false ->', JSON.stringify(shown), 'cache=', JSON.stringify(cache), 'err_banner=', err);
  if (shown !== 'старый факт' || cache !== 'старый факт' || err !== 1) { console.log('FAIL'); process.exit(1); }
  mode = 'ok'; shown = await edit('новый факт 2');
  const cache2 = await pg.evaluate(() => localStorage.getItem('nox.facts.text'));
  console.log('ok:true ->', JSON.stringify(shown), 'cache=', JSON.stringify(cache2), 'calls=', calls.join(','));
  if (shown !== 'новый факт 2' || cache2 !== 'новый факт 2') { console.log('FAIL'); process.exit(1); }
  console.log('PASS'); await b.close();
})().catch(e => { console.error(e); process.exit(2); });
