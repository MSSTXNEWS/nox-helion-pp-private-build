echo S4RUN:s6_p11
cat > /workspace/nox/web/site/nox-s6-pages.js <<'S6EOF_PG'
/* S6: реальные страницы вместо заглушек: map (Leaflet + earth), book-reader (foliate-js), notifications, benchmark (qa/audit.json + ECharts), nexus (cytoscape). */
(function () {
  const P = document.body.getAttribute('data-page'); const root = document.getElementById('s6root'); if (!root) return;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const ld = (src, mod) => new Promise((ok, no) => { const s = document.createElement('script'); s.src = src; if (mod) s.type = 'module'; s.onload = ok; s.onerror = () => no(new Error('нет ' + src)); document.head.appendChild(s); });
  const css = (h) => { const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.appendChild(l); };
  const sk = (el, n) => window.NOXds && NOXds.skeleton(el, n || 4);
  const em = (el, o) => window.NOXds ? NOXds.empty(el, o) : (el.textContent = o.title);
  const un = (el, t) => window.NOXds ? NOXds.unavailable(el, t) : (el.textContent = t);
  const toast = (m, v) => { const a = document.createElement('sl-alert'); a.variant = v || 'primary'; a.closable = true; a.duration = 3500; a.innerHTML = esc(m); a.style.cssText = 'position:fixed;top:88px;right:16px;z-index:1200;max-width:min(420px,92vw)'; document.body.appendChild(a); a.toast ? a.toast() : (a.open = true); setTimeout(() => a.remove(), 4200); };

  const H = (sel, h, mh) => { const e = document.querySelector(sel); if (e) { e.style.setProperty('height', h, 'important'); e.style.setProperty('min-height', mh, 'important'); e.style.setProperty('display', 'block', 'important'); } };
  const pages = {
    map() {
      root.innerHTML = '<sl-tab-group class="s6mp"><sl-tab slot="nav" panel="m">Карта</sl-tab><sl-tab slot="nav" panel="g">Глобус</sl-tab>' +
        '<sl-tab-panel name="m"><div class="s6mp-bar"><sl-select id="mpC" size="large" hoist value="0" class="s6f" placeholder="Город"></sl-select><sl-button id="mpMe" size="large"><sl-icon slot="prefix" library="tabler" name="current-location"></sl-icon>Моё местоположение</sl-button><sl-badge pill variant="neutral" class="s6bd" id="mpSt">загрузка плиток</sl-badge></div><div id="mpMap" class="s6mp-map"></div></sl-tab-panel>' +
        '<sl-tab-panel name="g"><iframe class="s6mp-earth" data-src="./vendor/earth/index.html" title="Глобус" loading="lazy"></iframe></sl-tab-panel></sl-tab-group>';
      H('#mpMap', 'calc(100vh - 340px)', '420px'); H('.s6mp-earth', 'calc(100vh - 340px)', '420px');
      const C = [['Севастополь', 44.6, 33.5, 11], ['Москва', 55.75, 37.62, 10], ['Санкт-Петербург', 59.94, 30.31, 10], ['Лондон', 51.5, -0.12, 10], ['Нью-Йорк', 40.71, -74.0, 10], ['Токио', 35.68, 139.69, 10], ['Сидней', -33.87, 151.21, 10]];
      const sel = document.getElementById('mpC'); sel.innerHTML = C.map((c, i) => '<sl-option value="' + i + '">' + esc(c[0]) + '</sl-option>').join(''); sel.value = '0';
      css('./vendor/nox-extra/leaflet.css'); ld('./vendor/nox-extra/leaflet.js').then(() => {
        try { L.Icon.Default.imagePath = './vendor/nox-extra/images/'; } catch (e) { }
        const m = L.map('mpMap', { zoomControl: true }).setView([C[0][1], C[0][2]], C[0][3]); let ok = 0, bad = 0; const st = document.getElementById('mpSt');
        const t = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '© OpenStreetMap' }).addTo(m);
        t.on('tileload', () => { ok++; st.textContent = 'плитки OSM: загружены'; st.variant = 'success'; }); t.on('tileerror', () => { bad++; if (!ok) { st.textContent = 'плитки недоступны'; st.variant = 'danger'; } });
        let mk = L.marker([C[0][1], C[0][2]]).addTo(m).bindPopup(C[0][0]);
        sel.addEventListener('sl-change', () => { const c = C[+sel.value]; m.setView([c[1], c[2]], c[3]); mk.setLatLng([c[1], c[2]]).bindPopup(c[0]).openPopup(); });
        document.getElementById('mpMe').addEventListener('click', () => { if (!navigator.geolocation) return toast('Геолокация недоступна в этом браузере', 'danger'); navigator.geolocation.getCurrentPosition((p) => { m.setView([p.coords.latitude, p.coords.longitude], 13); mk.setLatLng([p.coords.latitude, p.coords.longitude]).bindPopup('Вы здесь').openPopup(); }, () => toast('Доступ к местоположению запрещён', 'danger')); });
        const tg = root.querySelector('sl-tab-group'); tg.addEventListener('sl-tab-show', (e) => { if (e.detail.name === 'm') setTimeout(() => m.invalidateSize(), 50); if (e.detail.name === 'g') { const f = root.querySelector('.s6mp-earth'); if (!f.src || f.src === location.href) f.src = f.dataset.src; } });
      }).catch((e) => un(document.getElementById('mpMap'), e.message));
    },
    'book-reader'() {
      root.innerHTML = '<div class="s6bk-bar"><sl-button id="bkOpen" size="large" variant="primary"><sl-icon slot="prefix" library="tabler" name="book-upload"></sl-icon>Открыть книгу</sl-button><input type="file" id="bkF" accept=".epub,.fb2,.mobi,.azw3,.cbz" hidden><sl-button id="bkPrev" size="large" disabled><sl-icon slot="prefix" library="tabler" name="chevron-left"></sl-icon>Назад</sl-button><sl-button id="bkNext" size="large" disabled>Вперёд<sl-icon slot="suffix" library="tabler" name="chevron-right"></sl-icon></sl-button><sl-button id="bkToc" size="large" disabled><sl-icon slot="prefix" library="tabler" name="list"></sl-icon>Оглавление</sl-button><sl-badge pill variant="neutral" class="s6bd" id="bkSt">книга не открыта</sl-badge></div><sl-progress-bar id="bkPg" value="0" class="s6bk-pg">0%</sl-progress-bar><div class="s6bk-v" id="bkV"></div><sl-drawer label="Оглавление" id="bkD" placement="start"><div id="bkTc"></div></sl-drawer>';
      H('#bkV', 'calc(100vh - 360px)', '420px'); const v = document.getElementById('bkV'); em(v, { icon: 'book', title: 'Откройте книгу', text: 'Поддерживаются EPUB, FB2, MOBI, AZW3 и CBZ. Файл читается в браузере и никуда не отправляется.' });
      ld('./vendor/foliate-js/view.js', true).catch(() => { }); const f = document.getElementById('bkF');
      document.getElementById('bkOpen').addEventListener('click', () => f.click());
      f.addEventListener('change', async () => {
        const file = f.files[0]; if (!file) return; const st = document.getElementById('bkSt'); st.textContent = 'открываю…'; st.variant = 'warning';
        try { await customElements.whenDefined('foliate-view'); v.innerHTML = ''; const fv = document.createElement('foliate-view'); fv.style.cssText = 'width:100%;height:100%;display:block'; v.appendChild(fv); await fv.open(file);
          const bk = fv.book; st.textContent = (bk.metadata && (typeof bk.metadata.title === 'string' ? bk.metadata.title : Object.values(bk.metadata.title || {})[0])) || file.name; st.variant = 'success';
          ['bkPrev', 'bkNext', 'bkToc'].forEach((i) => document.getElementById(i).removeAttribute('disabled'));
          document.getElementById('bkPrev').onclick = () => fv.prev(); document.getElementById('bkNext').onclick = () => fv.next();
          fv.addEventListener('relocate', (e) => { const p = Math.round((e.detail.fraction || 0) * 100); const b = document.getElementById('bkPg'); b.value = p; b.textContent = p + '%'; });
          const tc = document.getElementById('bkTc'); const items = (bk.toc || []); tc.innerHTML = items.length ? items.map((t, i) => '<sl-button class="s6bk-t" variant="text" size="large" data-i="' + i + '">' + esc(t.label) + '</sl-button>').join('') : '<div class="ds-empty">В книге нет оглавления.</div>';
          tc.onclick = (e) => { const b = e.target.closest('[data-i]'); if (b) { fv.goTo(items[+b.dataset.i].href); document.getElementById('bkD').hide(); } };
          document.getElementById('bkToc').onclick = () => document.getElementById('bkD').show();
        } catch (e) { st.textContent = 'ошибка'; st.variant = 'danger'; un(v, 'Не удалось открыть файл: ' + e.message); }
      });
    },
    notifications() {
      root.innerHTML = '<div class="s6nt-top"><sl-card class="s6nt-c"><div class="s6nt-t">Разрешение браузера</div><sl-badge pill variant="neutral" class="s6bd" id="ntP">…</sl-badge></sl-card><sl-card class="s6nt-c"><div class="s6nt-t">Службы в строю</div><sl-badge pill variant="neutral" class="s6bd" id="ntS">…</sl-badge></sl-card><div class="s6nt-b"><sl-button id="ntAsk" size="large"><sl-icon slot="prefix" library="tabler" name="bell"></sl-icon>Разрешить уведомления</sl-button><sl-button id="ntTest" size="large" variant="primary"><sl-icon slot="prefix" library="tabler" name="send"></sl-icon>Тестовое уведомление</sl-button></div></div><h3 class="s6h3">Журнал</h3><div id="ntL" class="s6nt-l"></div>';
      const L = document.getElementById('ntL'); sk(L, 4); const KEY = 'nox.s6.notif'; const log = () => { try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch (e) { return []; } };
      const add = (t, v) => { const a = log(); a.unshift({ t, v, ts: Date.now() }); localStorage.setItem(KEY, JSON.stringify(a.slice(0, 50))); draw(); };
      let svc = []; const draw = () => { const a = svc.concat(log()); if (!a.length) return em(L, { icon: 'bell-off', title: 'Уведомлений нет', text: 'Тестовые уведомления и сбои служб появятся здесь.' }); L.innerHTML = a.map((x) => '<sl-card class="s6nt-i"><sl-badge pill variant="' + (x.v || 'neutral') + '" class="s6bd">' + (x.v === 'danger' ? 'сбой' : x.v === 'success' ? 'ок' : 'событие') + '</sl-badge><span>' + esc(x.t) + '</span><small>' + (x.ts ? new Date(x.ts).toLocaleString('ru-RU') : 'сейчас') + '</small></sl-card>').join(''); };
      const perm = () => { const p = window.Notification ? Notification.permission : 'unsupported'; const b = document.getElementById('ntP'); b.textContent = { granted: 'разрешено', denied: 'запрещено', default: 'не запрошено', unsupported: 'не поддерживается' }[p]; b.variant = p === 'granted' ? 'success' : p === 'denied' || p === 'unsupported' ? 'danger' : 'warning'; };
      perm(); document.getElementById('ntAsk').addEventListener('click', () => { if (!window.Notification) return toast('Браузер не поддерживает уведомления', 'danger'); Notification.requestPermission().then(perm); });
      document.getElementById('ntTest').addEventListener('click', () => { try { if (window.Notification && Notification.permission === 'granted') new Notification('NOX HELION', { body: 'Тестовое уведомление' }); } catch (e) { } if (window.NOXcmd) window.NOXcmd('notify.test', {}); add('Тестовое уведомление отправлено', 'success'); });
      const poll = () => fetch('/api/nox-live', { cache: 'no-store' }).then((r) => r.json()).then((j) => { const s = j.services || {}, k = Object.keys(s), bad = k.filter((x) => !s[x].ok); const b = document.getElementById('ntS'); b.textContent = (k.length - bad.length) + ' / ' + k.length; b.variant = bad.length ? 'warning' : 'success'; svc = bad.map((x) => ({ t: 'Служба «' + x + '» не отвечает', v: 'danger' })); draw(); }).catch(() => { document.getElementById('ntS').textContent = 'нет данных'; draw(); });
      poll(); setInterval(poll, 10000);
    },
    benchmark() {
      root.innerHTML = '<div class="s6bm-g"><sl-card class="s6bm-c"><div class="s6nt-t">Оценки ревизора A / R / U по страницам</div><div id="bmCh" class="s6bm-ch"></div></sl-card></div><div id="bmT" class="s6bm-t"></div>';
      H('#bmCh', '420px', '420px'); const T = document.getElementById('bmT'); sk(T, 5);
      Promise.all([fetch('qa/audit.json', { cache: 'no-cache' }).then((r) => r.json()), window.echarts ? 1 : ld('./vendor/echarts/echarts.min.js')]).then(([j]) => {
        const rows = []; Object.keys(j).forEach((p) => { const f = (j[p].fails || []).map((x) => String(x.detail)).join(' '); const m = f.match(/A\/R\/U=\[([\d.]+),\s*([\d.]+),\s*([\d.]+)\]/); if (m) rows.push([p, +m[1], +m[2], +m[3], (j[p].ts || '')]); });
        if (!rows.length) { em(document.getElementById('bmCh'), { title: 'Оценок нет', text: 'В qa/audit.json нет строк A/R/U.' }); T.innerHTML = ''; return; }
        const c = echarts.init(document.getElementById('bmCh'), 'nox'); c.setOption({ tooltip: { trigger: 'axis' }, legend: { data: ['Анимация', 'Реализм', 'Интерфейс'], textStyle: { color: '#efe6df' } }, grid: { left: 40, right: 16, top: 40, bottom: 64 }, xAxis: { type: 'category', data: rows.map((r) => r[0]), axisLabel: { rotate: 40, color: '#efe6df', fontSize: 12 } }, yAxis: { type: 'value', max: 10, axisLabel: { color: '#efe6df', fontSize: 12 } }, series: [['Анимация', 1, '#e9b465'], ['Реализм', 2, '#7fd49a'], ['Интерфейс', 3, '#e5645a']].map((s) => ({ name: s[0], type: 'bar', data: rows.map((r) => r[s[1]]), itemStyle: { color: s[2] }, markLine: s[1] === 1 ? { silent: true, symbol: 'none', data: [{ yAxis: 8 }], lineStyle: { color: '#fff', type: 'dashed' }, label: { formatter: 'порог 8' } } : undefined })) }); window.addEventListener('resize', () => c.resize());
        T.innerHTML = rows.map((r) => { const ok = r[1] >= 8 && r[2] >= 8 && r[3] >= 8; return '<sl-card class="s6bm-r"><b>' + esc(r[0]) + '</b><span>A ' + r[1] + ' · R ' + r[2] + ' · U ' + r[3] + '</span><sl-badge pill variant="' + (ok ? 'success' : 'warning') + '" class="s6bd">' + (ok ? 'принято' : 'ниже порога') + '</sl-badge></sl-card>'; }).join('');
      }).catch((e) => { un(document.getElementById('bmCh'), 'Данные аудита недоступны: ' + e.message); T.innerHTML = ''; });
    },
    nexus() {
      root.innerHTML = '<div class="s6nx-bar"><sl-badge pill variant="neutral" class="s6bd" id="nxN">граф строится</sl-badge><sl-button id="nxFit" size="large"><sl-icon slot="prefix" library="tabler" name="focus-2"></sl-icon>По размеру</sl-button><sl-button id="nxGo" size="large" variant="primary" disabled><sl-icon slot="prefix" library="tabler" name="external-link"></sl-icon>Открыть страницу</sl-button></div><div id="nxG" class="s6nx-g"></div>';
      H('#nxG', 'calc(100vh - 340px)', '420px');
      Promise.all([fetch('nav.json', { cache: 'no-cache' }).then((r) => r.json()), window.cytoscape ? 1 : ld('./vendor/cytoscape/dist/cytoscape.min.js')]).then(([nv]) => {
        const el = [{ data: { id: 'nox', label: 'NOX', t: 'core' } }]; nv.groups.forEach((g, gi) => { el.push({ data: { id: 'g' + gi, label: g.group, t: 'group' } }, { data: { source: 'nox', target: 'g' + gi } }); g.items.forEach((it) => { el.push({ data: { id: it.file, label: it.name, t: 'page', file: it.file } }, { data: { source: 'g' + gi, target: it.file } }); }); });
        const cy = cytoscape({ container: document.getElementById('nxG'), elements: el, layout: { name: 'cose', animate: false, nodeRepulsion: 9000 }, style: [{ selector: 'node', style: { label: 'data(label)', color: '#efe6df', 'font-size': 12, 'text-valign': 'bottom', 'text-margin-y': 4, 'background-color': '#e9b465', width: 18, height: 18 } }, { selector: 'node[t="core"]', style: { width: 44, height: 44, 'background-color': '#e5645a', 'font-size': 14 } }, { selector: 'node[t="group"]', style: { width: 30, height: 30, 'background-color': '#7fd49a' } }, { selector: 'edge', style: { width: 1, 'line-color': 'rgba(255,255,255,.25)' } }, { selector: ':selected', style: { 'border-width': 3, 'border-color': '#fff' } }] });
        document.getElementById('nxN').textContent = nv.groups.length + ' групп · ' + cy.nodes('[t="page"]').length + ' страниц'; document.getElementById('nxN').variant = 'success';
        let cur = null; const go = document.getElementById('nxGo'); cy.on('tap', 'node', (e) => { const f = e.target.data('file'); cur = f; if (f) go.removeAttribute('disabled'); else go.setAttribute('disabled', ''); }); go.addEventListener('click', () => { if (cur) location.href = './' + cur; });
        document.getElementById('nxFit').addEventListener('click', () => cy.fit(undefined, 32)); window.addEventListener('resize', () => cy.resize());
      }).catch((e) => un(document.getElementById('nxG'), 'Граф недоступен: ' + e.message));
    }
  };
  (pages[P] || (() => { }))();
})();
S6EOF_PG
cd /workspace/nox/web/site
grep -o ".\{50\}img.\{60\}" nox-s2-music.js | head -12
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/s6_shot.py <<'S6EOF_PY'
import asyncio,base64,io,os,json
from playwright.async_api import async_playwright
from PIL import Image
PAGES=os.environ.get("S6P","photo").split(","); CLK=os.environ.get("S6CLICK","1")=="1"
B="http://127.0.0.1:8091/web/"
def emit(name,raw,w):
    im=Image.open(io.BytesIO(raw)).convert('RGB')
    if im.width>w: im=im.resize((w,int(im.height*w/im.width)))
    b=io.BytesIO(); im.save(b,'JPEG',quality=35,optimize=True); s=base64.b64encode(b.getvalue()).decode()
    print("B64_%s_BEGIN"%name)
    for i in range(0,len(s),900): print(s[i:i+900])
    print("B64_%s_END"%name)
JS_STAT="""()=>{const v=e=>e.offsetParent&&e.getBoundingClientRect().width>0;
const nat=[...document.querySelectorAll('main.page button,main.page select,main.page textarea,main.page input:not([type=file])')].filter(v).filter(e=>!e.closest('[class*=FIE_],.plyr,.swiper,sl-dialog,.cm-editor,canvas')).map(e=>(e.id||e.className||e.tagName).toString().slice(0,22));
const sl=[...document.querySelectorAll('sl-button.s6sl,sl-select,sl-input,sl-textarea,sl-checkbox,sl-range')].filter(v).length;
const small=[...document.querySelectorAll('main.page sl-button,main.page sl-select,main.page sl-input')].filter(v).filter(e=>e.getBoundingClientRect().height<43).length;
const fs=[...document.querySelectorAll('main.page *')].filter(e=>e.children.length==0&&e.textContent.trim()&&v(e)&&parseFloat(getComputedStyle(e).fontSize)<12).length;
return {native:nat.length,nativeList:nat.slice(0,8),sl:sl,small:small,fs12:fs,ow:[document.documentElement.scrollWidth,innerWidth]}}"""
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-webgl","--ignore-gpu-blocklist"])
        for pg_ in PAGES:
            for vp,(w,h,ow) in {"d":(1440,900,1000),"m":(390,844,390)}.items():
                ctx=await b.new_context(viewport={"width":w,"height":h}); pg=await ctx.new_page(); errs=[]; reqs=[]
                pg.on("pageerror",lambda e:errs.append(str(e)[:120])); pg.on("request",lambda r:reqs.append(r.url[-40:]) if r.method=="POST" or "/api/" in r.url else None)
                pg.on("filechooser",lambda fc:None); pg.on("dialog",lambda d:asyncio.ensure_future(d.dismiss()))
                try: await pg.goto(B+pg_+".html",wait_until="load",timeout=40000)
                except Exception as e: print("GOTO",pg_,str(e)[:80])
                await pg.wait_for_timeout(5500)
                raw=await pg.screenshot(type="jpeg",quality=60); emit(pg_+"_"+vp,raw,ow)
                print("STAT",pg_,vp,json.dumps(await pg.evaluate(JS_STAT),ensure_ascii=False),"errs",errs[:3])
                if vp=="d" and CLK:
                    n=await pg.evaluate("()=>document.querySelectorAll('main.page sl-button.s6sl').length"); dead=0; e0=len(errs)
                    for i in range(min(n,45)):
                        try:
                            sig0=await pg.evaluate("()=>document.body.innerHTML.length+'|'+document.querySelectorAll('sl-dialog[open]').length"); r0=len(reqs)
                            await pg.evaluate("(i)=>{const e=document.querySelectorAll('main.page sl-button.s6sl')[i];if(e&&!e.disabled){e.scrollIntoView({block:'center'});e.click()}}",i)
                            await pg.wait_for_timeout(150)
                            sig1=await pg.evaluate("()=>document.body.innerHTML.length+'|'+document.querySelectorAll('sl-dialog[open]').length")
                            if sig0==sig1 and len(reqs)==r0: dead+=1
                            await pg.keyboard.press("Escape")
                        except Exception as e: pass
                    print("CLICK",pg_,"sl-buttons",n,"no-visible-effect",dead,"newerrs",errs[e0:e0+3])
                await ctx.close()
        await b.close()
asyncio.run(main())
S6EOF_PY
S6CLICK=0 S6P=map,book-reader,notifications,benchmark,nexus $PY /tmp/s6_shot.py 2>&1 | tail -n 700
