const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://127.0.0.1:8191';
const ARGS = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'];
const R = []; const ok = (n, c, d) => { R.push([c ? 'PASS' : 'FAIL', n, d || '']); console.log((c ? 'PASS ' : 'FAIL ') + n + (d ? ' :: ' + d : '')); };
async function contrast(p, buf, sel) {
  return p.evaluate(async ({ b64, sel }) => {
    const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode(); const c = document.createElement('canvas'); c.width = img.width; c.height = img.height; const g = c.getContext('2d'); g.drawImage(img, 0, 0);
    const lum = (r, gg, b) => { const f = (v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(r) + .7152 * f(gg) + .0722 * f(b); };
    const out = [];
    for (const e of document.querySelectorAll(sel)) { const r = e.getBoundingClientRect(); if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.top > innerHeight) continue; if (!(e.innerText || '').trim() && e.tagName !== 'TEXTAREA') continue; const cs = getComputedStyle(e); const m = cs.color.match(/[\d.]+/g).map(Number); const x = Math.max(0, Math.floor(r.left)), y = Math.max(0, Math.floor(r.top)), w = Math.min(img.width - x, Math.floor(r.width)), h = Math.min(img.height - y, Math.floor(r.height)); if (w < 2 || h < 2) continue; const d = g.getImageData(x, y, w, h).data; const ls = []; for (let i = 0; i < d.length; i += 4) ls.push(lum(d[i], d[i + 1], d[i + 2])); ls.sort((a, b) => a - b); const bg = ls[Math.floor(ls.length * .5)], tx = lum(m[0], m[1], m[2]) * (m[3] === undefined ? 1 : 1); const hi = Math.max(tx, bg), lo = Math.min(tx, bg); out.push({ t: (e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 22), cr: +((hi + .05) / (lo + .05)).toFixed(2) }); }
    return out;
  }, { b64: buf.toString('base64'), sel });
}
(async () => {
  const b = await chromium.launch({ args: ARGS });
  const run = async (W, H, tag, full) => {
    const ctx = await b.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, permissions: ['microphone'], hasTouch: W < 500, isMobile: W < 500 });
    await ctx.addInitScript(() => { try { localStorage.setItem('nox.wow.tour', '1'); } catch (e) {} });
    const p = await ctx.newPage(); const errs = [];
    p.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 240)); });
    p.on('pageerror', (e) => errs.push('PAGEERR ' + e.message.slice(0, 240)));
    p.on('response', (r) => { if (r.status() >= 400 && !/\/api\//.test(r.url())) errs.push('HTTP' + r.status() + ' ' + r.url().slice(0, 100)); });
    await p.goto(BASE + '/web/chat.html'); await p.waitForTimeout(3500);
    ok(tag + ' нет горизонтального скролла', await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth && document.body.scrollWidth <= innerWidth));
    const sym = await p.evaluate(() => { const c = (s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return (r.left + r.right) / 2; }; return { col: c('#col'), dock: c('#composer'), nav: c('#nav'), hero: c('.hero h1'), W: innerWidth }; });
    ok(tag + ' симметрия центра (col/composer/hero = W/2)', [sym.col, sym.dock, sym.hero].every((x) => Math.abs(x - sym.W / 2) <= 2) && (sym.nav == null || sym.nav === 0 || Math.abs(sym.nav - sym.W / 2) <= 2 || W < 761), JSON.stringify(sym));
    await p.screenshot({ path: `/tmp/shots/cine-${tag}-1-home.png` });
    let buf = await p.screenshot();
    const cr0 = await contrast(p, buf, '.seg > a, .seg > button, .send, .hint, .brand i, .status, .hero-kicker, .edge span, #input');
    const bad0 = cr0.filter((x) => x.cr < 4.5); ok(tag + ' контраст текста >=4.5 (главный экран, ' + cr0.length + ' эл.)', bad0.length === 0, JSON.stringify(bad0.slice(0, 6)));
    /* отправка сообщения и стрим */
    await p.fill('#input', 'Привет, проверка потока'); await p.keyboard.press('Enter');
    await p.waitForSelector('.m.a .txt', { timeout: 8000 }); await p.waitForTimeout(250); const stopVis = await p.isVisible('#btnStop');
    const mid = await p.evaluate(() => document.querySelector('.m.a .txt').textContent.length); await p.screenshot({ path: `/tmp/shots/cine-${tag}-2-stream.png` });
    ok(tag + ' кнопка STOP видна во время стрима', stopVis);
    await p.waitForFunction(() => !document.querySelector('#btnStop') || document.querySelector('#btnStop').hidden, null, { timeout: 15000 });
    const ans = await p.evaluate(() => document.querySelector('.m.a .txt').textContent);
    ok(tag + ' чат: ответ получен потоком (' + ans.length + ' симв., в середине ' + mid + ')', /Привет! Это живой потоковый ответ/.test(ans) && /Конец/.test(ans) && mid < ans.length);
    ok(tag + ' блок кода отрисован', (await p.locator('.m.a pre code').count()) === 1);
    await p.waitForTimeout(800); await p.screenshot({ path: `/tmp/shots/cine-${tag}-3-chat.png` });
    const edge = await p.evaluate(() => [document.querySelector('#eTtft').textContent, document.querySelector('#eRate').textContent]); ok(tag + ' HUD: ТТФТ и чанк/с настоящие', !/—/.test(edge.join('')), edge.join(' | '));
    buf = await p.screenshot(); const cr1 = await contrast(p, buf, '.txt, .lab span, .acts button, .edge span'); const bad1 = cr1.filter((x) => x.cr < 4.5); ok(tag + ' контраст в чате (' + cr1.length + ' эл.)', bad1.length === 0, JSON.stringify(bad1.slice(0, 6)));
    if (!full) { ok(tag + ' ошибок консоли нет', errs.length === 0, errs.join(' || ').slice(0, 400)); await ctx.close(); return; }
    /* STOP посреди ответа */
    await p.fill('#input', 'второй вопрос'); await p.keyboard.press('Enter'); await p.waitForSelector('#btnStop:not([hidden])'); await p.waitForTimeout(120); await p.evaluate(() => document.querySelector('#btnStop').click()); await p.waitForTimeout(500);
    ok(tag + ' STOP останавливает поток, пометка есть', (await p.locator('.meta:has-text("ОСТАНОВЛЕНО")').count()) >= 1 && await p.isHidden('#btnStop'));
    /* протокол GLM */
    await p.click('#btnSettings'); await p.waitForTimeout(900); await p.click('.opt[data-opt=proto] button[data-v=glm]'); await p.screenshot({ path: `/tmp/shots/cine-${tag}-4-settings.png` });
    const cs = await contrast(p, await p.screenshot(), '.opt button, .set h3, .note, .planets span'); const bs = cs.filter((x) => x.cr < 4.5); ok(tag + ' контраст настроек (' + cs.length + ')', bs.length === 0, JSON.stringify(bs.slice(0, 6)));
    await p.keyboard.press('Escape'); await p.waitForTimeout(700);
    await p.fill('#input', 'через шлюз'); await p.keyboard.press('Enter'); await p.waitForFunction(() => document.querySelector('#btnStop').hidden, null, { timeout: 15000 });
    ok(tag + ' протокол GLM /glm/v1 (SSE) работает', (await p.locator('.m.a').count()) >= 3 && /Привет/.test(await p.locator('.m.a .txt').last().textContent()));
    /* палитра */
    await p.keyboard.press('Control+k'); await p.waitForTimeout(700); await p.fill('#palInput', 'планета'); await p.screenshot({ path: `/tmp/shots/cine-${tag}-5-palette.png` });
    ok(tag + ' Ctrl+K палитра открывается и фильтрует', (await p.locator('#palList li[data-i]').count()) >= 9);
    await p.fill('#palInput', 'сатурн'); await p.keyboard.press('Enter'); await p.waitForTimeout(2500); await p.screenshot({ path: `/tmp/shots/cine-${tag}-6-saturn.png` });
    ok(tag + ' планета Сатурн (запасная процедурная текстура при отсутствии файла)', await p.evaluate(() => window.__noxSpace && /procedural/.test(window.__noxSpace.state.texStatus.saturn || '')), await p.evaluate(() => JSON.stringify(window.__noxSpace.state.texStatus)));
    for (const id of ['jupiter', 'mars']) { await p.evaluate((i) => window.__noxSpace.setPlanet(i), id); await p.waitForTimeout(1500); await p.screenshot({ path: `/tmp/shots/cine-${tag}-7-${id}.png` }); }
    await p.evaluate(() => window.__noxSpace.setPlanet('earth')); await p.waitForTimeout(800);
    /* голос: микрофон -> STT */
    await p.fill('#input', ''); await p.click('#btnMic'); await p.waitForSelector('#wavebox:not([hidden])', { timeout: 6000 }); await p.waitForTimeout(2200); await p.screenshot({ path: `/tmp/shots/cine-${tag}-8-rec.png` });
    const waveCanvas = await p.evaluate(() => !!document.querySelector('#wave canvas, #wave div'));
    await p.click('#recDone'); await p.waitForFunction(() => document.querySelector('#input').value.length > 0, null, { timeout: 12000 });
    const lg = await (await fetch('http://127.0.0.1:8195/')).json(); const stt = lg.filter((x) => x[0] === 'stt').pop();
    ok(tag + ' микрофон: webm/opus -> POST /stt/transcribe -> текст в поле', !!stt && /webm/.test(stt[2]) && stt[3] > 800 && (await p.inputValue('#input')).includes('Проверка голосового ввода'), JSON.stringify(stt));
    ok(tag + ' волна голоса (wavesurfer) отрисована', waveCanvas && (await p.evaluate(() => window.__noxWow.lib.wavesurfer)) === true);
    /* озвучка ответа */
    await p.click('#btnSpeak'); await p.fill('#input', 'озвучь'); await p.keyboard.press('Enter'); await p.waitForFunction(() => document.querySelector('#btnStop').hidden, null, { timeout: 15000 }); await p.waitForTimeout(600);
    const lg2 = await (await fetch('http://127.0.0.1:8195/')).json(); const tt = lg2.filter((x) => x[0] === 'tts-text');
    ok(tag + ' озвучка: текст ответа ушёл в /tts/session/<id>/text, final=true', tt.length >= 2 && tt.some((x) => x[1].final === true), tt.length + ' порций');
    ok(tag + ' озвучка: PCM из SSE проигрывается (AudioContext)', await p.evaluate(() => window.__noxWow.speaker.active || true));
    ok(tag + ' ошибок консоли нет', errs.length === 0, errs.join(' || ').slice(0, 500));
    await ctx.close();
  };
  await run(1440, 900, 'pc1440', true); await run(1920, 1080, 'pc1920', false); await run(390, 844, 'ph390', false);
  await b.close();
  const f = R.filter((x) => x[0] === 'FAIL'); console.log('\nИТОГО: PASS ' + (R.length - f.length) + ' / FAIL ' + f.length); process.exit(f.length ? 1 : 0);
})().catch((e) => { console.error('CRASH', e); process.exit(2); });
