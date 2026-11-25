for i in $(seq 1 6); do c=$(curl -s -o /dev/null -w "%{http_code}" 127.0.0.1:8091/web/index.html); [ "$c" = 200 ] && break; sleep 8; done; echo "OUT: server $c"
S=/workspace/nox/web/site
cat > $S/nox-m-mobile.js <<'M_EOF_JS'
/* NOX · M: мобильный UX (таб-бар, шторка «Ещё», кнопка ИИ, свайп назад, pull-to-refresh, фиксы целей/шрифта). Активен только при ширине <=768. */
(() => {
  if (window.__noxM) return; window.__noxM = 1;
  const mq = matchMedia('(max-width:768px)');
  const $ = (s, r = document) => r.querySelector(s);
  const ic = (n) => '<sl-icon library="tabler" name="' + n + '"></sl-icon>';
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const CHAT = /chat\.html$/.test(location.pathname);
  const cur = (location.pathname.split('/').pop() || 'index.html').replace(/\.main\.html$/, '.html');
  if (mq.matches && cur === 'index.html' && !/[?&]home/.test(location.search) && !sessionStorage.getItem('nox_m_home')) { sessionStorage.setItem('nox_m_home', '1'); location.replace('./chat.html'); return; }
  const hap = (t) => { try { const h = window.iosHaptics || window.NOX_ios_haptics || window.haptic; if (typeof h === 'function') h(); else if (h && h.haptic) h.haptic(); else navigator.vibrate && navigator.vibrate(t || 8); } catch (e) { /* без haptics */ } };
  const MAIN = [['chat.html', 'Чат', 'message-circle'], ['index.html?home=1', 'Главная', 'home-2'], ['assistant.html', 'Помощник', 'checklist'], ['studio.html', 'Ателье', 'brush']];
  let built = false, nav = null, openSheet = null, scrim = null;
  const closeSheet = () => { if (!openSheet) return; openSheet.classList.remove('open'); scrim.classList.remove('open'); const s = openSheet; openSheet = null; setTimeout(() => s.remove(), 300); };
  const sheet = (html) => {
    closeSheet();
    const s = document.createElement('div'); s.className = 'nox-m-sheet'; s.innerHTML = '<div class="m-handle"></div>' + html; document.body.appendChild(s);
    requestAnimationFrame(() => { s.classList.add('open'); scrim.classList.add('open'); }); openSheet = s; hap();
    let y0 = null, dy = 0;
    s.addEventListener('touchstart', (e) => { if (s.scrollTop <= 0) { y0 = e.touches[0].clientY; dy = 0; } }, { passive: true });
    s.addEventListener('touchmove', (e) => { if (y0 == null) return; dy = e.touches[0].clientY - y0; if (dy > 0) { s.style.transition = 'none'; s.style.transform = 'translateY(' + dy + 'px)'; } }, { passive: true });
    s.addEventListener('touchend', () => { s.style.transition = ''; s.style.transform = ''; if (y0 != null && dy > 90) closeSheet(); y0 = null; });
    return s;
  };
  const loadNav = async () => { if (nav) return nav; try { nav = await (await fetch('./nav.json', { cache: 'no-cache' })).json(); } catch (e) { nav = { groups: [] }; } return nav; };
  const more = async () => {
    const n = await loadNav(); let h = '<h3>Все разделы</h3><div class="m-grid">';
    (n.groups || []).forEach((g) => { h += '<div class="m-grp">' + esc(g.group) + '</div>'; (g.items || []).forEach((i) => { h += '<a href="./' + esc(i.file) + '" class="' + (i.file === cur ? 'on' : '') + '">' + ic(i.icon || 'apps') + '<span>' + esc(i.name) + '</span></a>'; }); });
    sheet(h + '</div>');
  };
  const ask = () => {
    const acts = [['.nmc-fab', 'Диалог с NOX', 'message-circle'], ['.nai-btn', 'NOX, кратко о странице', 'sparkles'], ['#nxmPill', 'Справка', 'help-circle'], ['#nxnavx', 'Навигатор', 'compass']].filter((a) => $(a[0]));
    if (acts.length === 1) { hap(); $(acts[0][0]).click(); return; }
    const s = sheet('<h3>NOX</h3><div class="m-list">' + acts.map((a, i) => '<button data-i="' + i + '">' + ic(a[2]) + ' ' + esc(a[1]) + '</button>').join('') + '</div>');
    s.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => { const t = $(acts[+b.dataset.i][0]); closeSheet(); setTimeout(() => t && t.click(), 200); }));
  };
  const proxyList = (title, items) => { // items: [группа, подпись, элемент]
    let h = '<h3>' + esc(title) + '</h3><div class="m-list">', g = ''; items.forEach((it, i) => { if (it[0] !== g) { g = it[0]; h += '<div class="m-grp">' + esc(g) + '</div>'; } h += '<button data-i="' + i + '">' + esc(it[1]) + '</button>'; });
    const s = sheet(h + '</div>'); s.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => { const el = items[+b.dataset.i][2]; closeSheet(); setTimeout(() => el.click(), 220); }));
  };
  const dialogs = () => { const b = $('#btnThreads'); if (b) b.click(); else sheet('<h3>Диалоги</h3><p>Список диалогов недоступен.</p>'); };
  const commands = () => {
    const it = []; const lab = (e) => (e.textContent || e.getAttribute('aria-label') || e.title || '').trim().replace(/\s+/g, ' ').slice(0, 40);
    document.querySelectorAll('.lv-dd sl-menu-item').forEach((e) => it.push(['Память и режимы', lab(e), { click: () => { if (e.type === 'checkbox') e.checked = !e.checked; const m = e.closest('sl-menu'); if (m) m.dispatchEvent(new CustomEvent('sl-select', { bubbles: true, detail: { item: e } })); else e.click(); } }]));
    document.querySelectorAll('.lv-tag').forEach((e) => it.push(['Теги', lab(e), e]));
    
    [['.nai-btn', 'NOX, …'], ['#nuiVoice', 'Голос'], ['#nuiFlow', 'Карта мышления'], ['#btnPalette', 'Палитра'], ['#btnSettings', 'Настройки чата'], ['#nxsun', 'Пульт NOX']].forEach((a) => { const e = $(a[0]); if (e) it.push(['Функции', a[1], e]); });
    proxyList('Команды', it);
  };
  const tpls = () => { const it = []; document.querySelectorAll('#cxChips button').forEach((e) => it.push(['Заготовки', e.textContent.trim(), e])); const w = $('#tgWid'); if (w) it.push(['Система', 'Виджеты и статус', w]); [['#nxmPill', 'Справка'], ['#nxnavx', 'Навигатор'], ['#tbBell', 'Уведомления']].forEach((a) => { const e = $(a[0]); if (e) it.push(['Система', a[1], e]); }); proxyList('Заготовки и система', it); };
  const build = () => {
    if (built) return; built = true;
    scrim = document.createElement('div'); scrim.id = 'nox-m-scrim'; scrim.addEventListener('click', closeSheet); document.body.appendChild(scrim);
    const t = document.createElement('nav'); t.id = 'nox-m-tab'; t.setAttribute('aria-label', 'Основная навигация');
    if (CHAT) { document.body.classList.add('m-chat'); }
    const CT = [['chat.html', 'Чат', 'message-circle'], ['#dlg', 'Диалоги', 'messages'], ['#cmd', 'Команды', 'terminal-2'], ['#tpl', 'Заготовки', 'template']];
    t.innerHTML = (CHAT ? CT : MAIN).map((m) => '<a href="' + (m[0][0] === '#' ? m[0] : './' + m[0]) + '" class="' + (m[0] === cur || (CHAT && m[0] === 'chat.html') ? 'on' : '') + '">' + ic(m[2]) + '<span>' + m[1] + '</span></a>').join('') + '<button type="button" id="nox-m-more" aria-label="Ещё">' + ic('layout-grid') + '<span>Ещё</span></button>';
    document.body.appendChild(t);
    if (!MAIN.some((m) => m[0] === cur)) $('#nox-m-more').classList.add('on');
    $('#nox-m-more').addEventListener('click', more);
    t.addEventListener('click', (e) => { const a = e.target.closest('a[href^="#"]'); if (!a) return; e.preventDefault(); ({ '#dlg': dialogs, '#cmd': commands, '#tpl': tpls })[a.getAttribute('href')](); });
    t.addEventListener('click', (e) => { if (e.target.closest('a')) hap(); });
    const b = document.createElement('button'); b.id = 'nox-m-ai'; b.type = 'button'; b.setAttribute('aria-label', 'Спросить NOX'); b.innerHTML = ic('sparkles'); b.addEventListener('click', ask); document.body.appendChild(b); if (cur === 'chat.html') b.style.display = 'none';
    // скрыть таб-бар и ИИ при вводе (клавиатура)
    document.addEventListener('focusin', (e) => { if (e.target.matches('input,textarea,[contenteditable]')) document.body.classList.add('m-kbd'); });
    document.addEventListener('focusout', () => document.body.classList.remove('m-kbd'));
    const st = document.createElement('style'); st.textContent = '@media(max-width:768px){body.m-kbd #nox-m-tab,body.m-kbd #nox-m-ai{display:none}}'; document.head.appendChild(st);
    // свайп от левого края = назад
    let sx = null, sy = null;
    addEventListener('touchstart', (e) => { const p = e.touches[0]; sx = p.clientX < 22 ? p.clientX : null; sy = p.clientY; }, { passive: true });
    addEventListener('touchend', (e) => { if (sx == null) return; const p = e.changedTouches[0]; if (p.clientX - sx > 80 && Math.abs(p.clientY - sy) < 50) { if (openSheet) closeSheet(); else if (history.length > 1) history.back(); else location.href = './index.html'; } sx = null; }, { passive: true });
    // pull-to-refresh на страницах с данными
    if (/^(news|glance|dispatcher|downloads|training|memory|system|projects|calendar|finance|notifications|ops)\.html$/.test(cur)) {
      const sc = document.createElement('script'); sc.src = './vendor/pulltorefresh/index.umd.min.js';
      sc.onload = () => { try { window.PullToRefresh.init({ mainElement: 'body', instructionsPullToRefresh: 'Потяните для обновления', instructionsReleaseToRefresh: 'Отпустите', instructionsRefreshing: 'Обновляю…', onRefresh() { hap(); location.reload(); }, shouldPullToRefresh() { return !window.scrollY && !openSheet; } }); } catch (e) { /* без PTR */ } };
      document.head.appendChild(sc);
    }
    // диалоги Shoelace: свайп вниз закрывает
    document.addEventListener('touchstart', (e) => { const p = e.target.closest && e.target.closest('sl-dialog'); if (!p || !p.open) return; const panel = p.shadowRoot && p.shadowRoot.querySelector('[part=panel]'); if (!panel) return; const y0 = e.touches[0].clientY; if (y0 > panel.getBoundingClientRect().top + 48) return; const end = (ev) => { if (ev.changedTouches[0].clientY - y0 > 90) { hap(); p.hide(); } document.removeEventListener('touchend', end); }; document.addEventListener('touchend', end); }, { passive: true });
    document.documentElement.style.setProperty('--ds-dock-h', t.offsetHeight + 'px');
  };
  // фиксы целей >=44 и шрифта >=14
  const fix = () => {
    if (!mq.matches) return;
    const q = 'a,button,[role=button],[role=tab],input:not([type=hidden]),select,summary,label[for],sl-button,sl-icon-button,sl-tab,sl-checkbox,sl-switch';
    document.querySelectorAll(q).forEach((e) => { if (e.closest('#nox-m-tab,.nox-m-sheet,#nox-m-ai,#nxdock')) return; const r = e.getBoundingClientRect(); if (!r.width || !r.height) return; if (r.width < 44 || r.height < 44) { e.classList.add('m-t44'); if (r.height < 44) { e.style.setProperty('min-height', '44px', 'important'); e.style.setProperty('max-height', 'none', 'important'); } if (r.width < 44) e.style.setProperty('min-width', '44px', 'important'); } });
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n; const seen = new Set();
    while ((n = w.nextNode())) { if (!n.nodeValue.trim()) continue; const e = n.parentElement; if (!e || seen.has(e) || e.closest('script,style,svg,canvas')) continue; seen.add(e); const fs = parseFloat(getComputedStyle(e).fontSize); if (fs >= 1 && fs < 14) { e.classList.add('m-f14'); e.style.setProperty('font-size', '14px', 'important'); } }
    const W = innerWidth; document.querySelectorAll('body *').forEach((e) => { if (e.closest('#nox-m-tab,.nox-m-sheet,#nxdock,.swiper,[class*=carousel],[class*=scroll],[class*=track]')) return; const r = e.getBoundingClientRect(); if (r.width > W + 1 && getComputedStyle(e).position !== 'fixed') e.classList.add('m-wrap'); });
  };
  window.__noxMfix = fix;
  let tmr; const later = () => { clearTimeout(tmr); tmr = setTimeout(fix, 120); };
  const start = () => { if (!document.body) return; if (mq.matches) build(); later(); new MutationObserver(later).observe(document.body, { childList: true, subtree: true }); [300, 700, 1200, 2000, 3000, 4500, 7000, 10000].forEach((t) => setTimeout(fix, t)); setInterval(fix, 3000); };
  mq.addEventListener && mq.addEventListener('change', () => { if (mq.matches) build(); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
M_EOF_JS
sed -i "s/?v=m[1-9]/?v=m10/" $S/*.html; echo "OUT: installed"
PY=/workspace/nox/venv/bin/python; cat > /tmp/m_func.py <<'M_EOF'
import asyncio
from playwright.async_api import async_playwright
async def touch(cdp,pts):
    x,y=pts[0]
    await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
    for x,y in pts[1:]:
        await cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x,'y':y}]});await asyncio.sleep(0.03)
    await cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        ctx=await b.new_context(viewport={'width':390,'height':844},has_touch=True,is_mobile=True)
        pg=await ctx.new_page();reqs=[];pg.on('request',lambda r:reqs.append(r.method+' '+r.url[-50:]) if r.method=='POST' else None)
        errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:80]))
        await pg.goto('http://127.0.0.1:8091/web/chat.html',wait_until='load');await pg.wait_for_timeout(4000)
        inp=await pg.evaluate("(()=>{const t=document.querySelector('#form textarea,#form input[type=text],#form [contenteditable]');return t?t.tagName+'#'+t.id:'none'})()")
        print('OUT: input',inp,'tabs',await pg.evaluate("[...document.querySelectorAll('#nox-m-tab a,#nox-m-tab button')].map(e=>e.innerText.trim())"))
        async def val(): return await pg.evaluate("(()=>{const t=document.querySelector('#form textarea,#form input[type=text]');return t?t.value:''})()")
        # Команды
        await pg.click('a[href="#cmd"]');await pg.wait_for_timeout(700)
        items=await pg.evaluate("[...document.querySelectorAll('.nox-m-sheet button')].map(b=>b.innerText.trim())")
        print('OUT: cmd items',items)
        n0=len(reqs);m0=await pg.evaluate("document.querySelectorAll('#msgs > *').length")
        await pg.click('.nox-m-sheet button:has-text("/коротко")');await pg.wait_for_timeout(2500)
        print('OUT: cmd tag /коротко posts',reqs[n0:][:2],'msgs',m0,'->',await pg.evaluate("document.querySelectorAll('#msgs > *').length"))
        await pg.click('a[href="#cmd"]');await pg.wait_for_timeout(600)
        i0=await pg.evaluate("document.querySelector('.lv-inc').hidden")
        await pg.click('.nox-m-sheet button:has-text("Без памяти (временный чат)")');await pg.wait_for_timeout(1200)
        print('OUT: cmd no-memory inc hidden',i0,'->',await pg.evaluate("document.querySelector('.lv-inc').hidden"))
        # Заготовки
        await pg.click('a[href="#tpl"]');await pg.wait_for_timeout(700)
        it2=await pg.evaluate("[...document.querySelectorAll('.nox-m-sheet button')].map(b=>b.innerText.trim())")
        print('OUT: tpl items',it2)
        if it2:
            b0=await val();n0=len(reqs)
            await pg.click('.nox-m-sheet button >> nth=0');await pg.wait_for_timeout(1500)
            print('OUT: tpl click',it2[0],'input',repr(b0),'->',repr((await val())[:40]),'posts',reqs[n0:][:3],'msgs',await pg.evaluate("document.querySelectorAll('#msgs > *').length"))
        # свайп назад
        await pg.goto('http://127.0.0.1:8091/web/news.html',wait_until='load');await pg.wait_for_timeout(2500)
        await pg.goto('http://127.0.0.1:8091/web/settings.html',wait_until='load');await pg.wait_for_timeout(2500)
        cdp=await ctx.new_cdp_session(pg)
        await touch(cdp,[(4,400),(40,402),(90,404),(150,405),(200,405)]);await pg.wait_for_timeout(2500)
        print('OUT: swipe-back url',pg.url[-20:])
        # PTR
        await pg.goto('http://127.0.0.1:8091/web/news.html',wait_until='load');await pg.wait_for_timeout(3000)
        await pg.evaluate("window.__flag=1;window.scrollTo(0,0)")
        print('OUT: ptr lib',await pg.evaluate("typeof PullToRefresh"))
        await touch(cdp,[(200,120)]+[(200,120+i*25) for i in range(1,16)]);await pg.wait_for_timeout(3500)
        print('OUT: ptr reloaded',await pg.evaluate("window.__flag!==1"))
        print('OUT: errs',errs)
        await b.close()
asyncio.run(main())
M_EOF
timeout 100 $PY -I /tmp/m_func.py 2>&1 | grep -a "no-memory\|errs"
cat > /tmp/m_qa.py <<'M_EOF'
import asyncio,json,base64,sys,os
from playwright.async_api import async_playwright
nav=json.load(open('/workspace/nox/web/site/nav.json'))
pages=['index']+[i['file'][:-5] for g in nav['groups'] for i in g['items']]
if os.environ.get('PAGES'): pages=os.environ['PAGES'].split(',')
W=[int(x) for x in os.environ.get('WIDTHS','390').split(',')]
SHOT=os.environ.get('SHOTS','').split(',')
JS="""()=>{const w=innerWidth,r={};const tab=document.querySelector('#nox-m-tab');r.tab=!!tab;
const tb=tab?tab.getBoundingClientRect():null;
r.sw=document.documentElement.scrollWidth;
const q='a,button,[role=button],[role=tab],input:not([type=hidden]),select,summary,sl-button,sl-icon-button,sl-tab';
r.small=[];document.querySelectorAll(q).forEach(e=>{if(e.closest('#nxdock'))return;const b=e.getBoundingClientRect();const s=getComputedStyle(e);if(!b.width||!b.height||s.visibility==='hidden'||s.opacity==='0'||b.left<-50||b.top>innerHeight*3)return;if(e.offsetParent===null&&s.position!=='fixed')return;if(b.width<43.5||b.height<43.5)r.small.push((e.tagName+'#'+e.id+'.'+(typeof e.className==='string'?e.className.split(' ')[0]:'')+' '+Math.round(b.width)+'x'+Math.round(b.height)+' '+(e.innerText||'').slice(0,12).replace(/\\n/g,' ')))});
r.font=0;const wk=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;const seen=new Set();r.fontEx=[];while((n=wk.nextNode())){if(!n.nodeValue.trim())continue;const e=n.parentElement;if(!e||seen.has(e)||e.closest('script,style,svg,canvas,#nxdock'))continue;seen.add(e);const b=e.getBoundingClientRect();if(!b.width||!b.height||getComputedStyle(e).visibility==='hidden')continue;const fz=parseFloat(getComputedStyle(e).fontSize);if(fz>=1&&fz<13.9){r.font++;if(r.fontEx.length<2)r.fontEx.push(e.tagName+'.'+(typeof e.className==='string'?e.className.split(' ')[0]:'')+getComputedStyle(e).fontSize)}}
r.wide=[];document.querySelectorAll('body *').forEach(e=>{if(e.closest('#nxdock'))return;const b=e.getBoundingClientRect();const s=getComputedStyle(e);if(s.position==='fixed'||!b.width||s.visibility==='hidden')return;if(b.right>w+2&&b.left>=-2){let p=e.parentElement,sc=false;while(p&&p!==document.body){const o=getComputedStyle(p).overflowX;if((o==='auto'||o==='scroll'||o==='hidden')&&p.getBoundingClientRect().right<=w+2){sc=true;break}p=p.parentElement}if(!sc&&r.wide.length<4)r.wide.push(e.tagName+'#'+e.id+'.'+(typeof e.className==='string'?e.className.split(' ')[0]:'')+' r'+Math.round(b.right))}});
r.ovl=[];if(tb){document.querySelectorAll('body *').forEach(e=>{if(e.closest('#nox-m-tab,#nox-m-ai,.nox-m-sheet,#nox-m-scrim'))return;const s=getComputedStyle(e);if(s.position!=='fixed'||s.opacity==='0'||s.pointerEvents==='none')return;const b=e.getBoundingClientRect();if(b.width>300&&b.height>600)return;if(b.width<2)return;if(b.bottom>tb.top+2&&b.top<tb.bottom&&b.right>0&&b.left<w)r.ovl.push(e.tagName+'#'+e.id+'.'+(typeof e.className==='string'?e.className.split(' ')[0]:''))});
const sun=document.querySelector('#nxsun');if(sun){const b=sun.getBoundingClientRect();r.sunY=Math.round(b.bottom)}}
return r}"""
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for w in W:
            for pg in pages:
                c=await b.new_page(viewport={"width":w,"height":844 if w<500 else 1024})
                errs=[]
                c.on('pageerror',lambda e:errs.append(str(e)[:100]))
                try:
                    for t in range(3):
                        try: await c.goto("http://127.0.0.1:8091/web/%s.html"%pg,wait_until="load",timeout=25000);break
                        except Exception as e:
                            if t==2: raise
                            await asyncio.sleep(3)
                    await c.wait_for_timeout(int(os.environ.get('WAIT','3500')))
                    r=await c.evaluate(JS)
                    bad=len(errs)+(1 if r['sw']>w else 0)+len(r['small'])+len(r['ovl'])+len(r['wide'])
                    print("OUT: %d %-14s js%d sw%d tab%d small%d font%d wide%d ovl%d %s"%(w,pg,len(errs),r['sw'],r['tab'],len(r['small']),r['font'],len(r['wide']),len(r['ovl']),"OK" if not bad and not r['font'] else "!!"))
                    if bad or r['font']:
                        print("OUT:    ",errs[:2],r['small'][:5],r['wide'][:3],r['ovl'][:3],r['fontEx'])
                    if pg in SHOT:
                        await c.screenshot(path="/tmp/m_%s_%d.jpg"%(pg,w),type="jpeg",quality=38)
                        print("B64_%s%d_BEGIN"%(pg,w));print(base64.b64encode(open("/tmp/m_%s_%d.jpg"%(pg,w),'rb').read()).decode());print("B64_%s%d_END"%(pg,w))
                        if os.environ.get('SHEET'):
                            for tag,sel in (('more','#nox-m-more'),('cmd','a[href="#cmd"]')):
                                if await c.query_selector(sel):
                                    await c.click(sel);await c.wait_for_timeout(900)
                                    await c.screenshot(path="/tmp/m_s.jpg",type="jpeg",quality=38)
                                    print("B64_%s%s%d_BEGIN"%(pg,tag,w));print(base64.b64encode(open("/tmp/m_s.jpg",'rb').read()).decode());print("B64_%s%s%d_END"%(pg,tag,w))
                                    await c.keyboard.press('Escape');await c.mouse.click(200,60);await c.wait_for_timeout(400)
                except Exception as e: print("OUT: %d %s FAIL %s"%(w,pg,str(e)[:100]))
                await c.close()
        await b.close()
asyncio.run(main())
M_EOF
(PAGES=assistant,system,widgets,chat,pdf,index WAIT=6000 WIDTHS=390,430,768 $PY -I /tmp/m_qa.py > /tmp/m_qa_out4.txt 2>&1 &) ; echo OUT: qa bg
S=/workspace/nox/web/site
echo "OUT: tools.js $(wc -c < $S/nox-tools.js) pages: $(grep -l 'nox-tools.js' $S/*.html | xargs -n1 basename | tr '\n' ' ')"
head -c 1200 $S/nox-tools.js | sed 's/^/OUT: /'
echo "OUT: vendor: $(ls $S/vendor | grep -iE 'ninja|gridstack|cmdk|lazy|lozad' | tr '\n' ' ')"
echo "OUT: biggest js: $(ls -S $S/*.js | head -12 | xargs wc -c | head -12 | tr '\n' ';')"
echo "OUT: loading=lazy count $(grep -o 'loading="lazy"' $S/*.html | wc -l); img total $(grep -o '<img' $S/*.html | wc -l)"
echo "OUT: script w/o defer on news: $(grep -o '<script src[^>]*>' $S/news.html | grep -vc 'defer\|module')"
echo "OUT: 4k css: $(wc -c < $S/nox-4k.css) $(grep -c 'min-width:2560' $S/nox-4k.css)"
