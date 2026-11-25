echo S4RUN:s6_d1
cd /workspace/nox/web/site
cat > nox-s6-sl.js <<'S6EOF_js'
/* S6: контролы страниц на Shoelace. Исходные элементы остаются в DOM (скрыты) и получают события: логика страниц не ломается.
   button -> sl-button, select -> sl-select, input/textarea -> sl-input/sl-textarea, checkbox -> sl-checkbox, range -> sl-range, статус-чипы -> sl-badge.
   Плюс «Спросить NOX» (sl-dialog, /api/chat) на каждой странице. */
(function () {
  if (window.__s6sl) return; window.__s6sl = 1;
  const page = document.body.getAttribute('data-page') || location.pathname.split('/').pop().replace('.html', '');
  const SKIP = 'sl-dialog,sl-tab-group,sl-tab,sl-button,sl-select,sl-input,sl-switch,sl-tooltip,sl-details,sl-menu,.ph .acts,.s4dlg,.s6-skip,[data-s6="skip"],[class*="FIE_"],.ps-ed,.plyr,.vjs-control-bar,.swiper-button-next,.swiper-button-prev,.u-wrap,canvas,#nxnavx,.nmc,.nox-dock,#ds-tip,header,nav,[id^="nxm"],[id^="nox-"],.s6bar,.cm-editor,.CodeMirror';
  const BTN = 'main.page button:not([data-s6])';
  const reg = new Map();
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const lbl = (b) => [...b.childNodes].filter((n) => n.nodeType === 3 || (n.nodeType === 1 && n.tagName !== 'SL-ICON' && n.tagName !== 'svg' && n.tagName !== 'SVG')).map((n) => n.textContent).join('').replace(/\s+/g, ' ').trim();
  const hide = (el) => { el.classList.add('s6h'); el.setAttribute('data-s6', '1'); el.setAttribute('tabindex', '-1'); el.setAttribute('aria-hidden', 'true'); };
  const skip = (el) => !el.isConnected || el.closest(SKIP) || el.getAttribute('data-s6') != null;
  function variantOf(b) {
    const c = b.className || '';
    if (b.getAttribute('aria-pressed') === 'true' || b.getAttribute('aria-selected') === 'true' || /(^|\s)(on|act|active|sel|selected|primary|ai|go)(\s|$)/.test(c)) return 'primary';
    if (/danger|del|stop|remove/.test(c)) return 'danger';
    return 'default';
  }
  function syncBtn(b, s) {
    const l = lbl(b), lab = s.querySelector('.s6l'); if (lab && lab.textContent !== l) lab.textContent = l;
    const v = variantOf(b); if (s.getAttribute('variant') !== v) s.setAttribute('variant', v);
    b.disabled ? s.setAttribute('disabled', '') : s.removeAttribute('disabled');
    const ic = b.querySelector('sl-icon'), mine = s.querySelector('sl-icon'); if (ic && mine && mine.getAttribute('name') !== ic.getAttribute('name')) mine.setAttribute('name', ic.getAttribute('name'));
    if (b.hasAttribute('hidden') || b.style.display === 'none') s.setAttribute('hidden', ''); else s.removeAttribute('hidden');
  }
  function convBtn(b) {
    const ic = b.querySelector('sl-icon'), l = lbl(b), s = document.createElement('sl-button');
    s.size = 'large'; s.className = 's6sl'; s.setAttribute('data-s6for', b.id || '');
    const tt = b.title || b.getAttribute('aria-label') || l || 'Действие';
    s.innerHTML = (ic ? '<sl-icon slot="prefix" library="' + esc(ic.getAttribute('library') || 'tabler') + '" name="' + esc(ic.getAttribute('name')) + '"></sl-icon>' : '') + '<span class="s6l">' + esc(l) + '</span>';
    if (!l && !ic) s.querySelector('.s6l').textContent = (b.textContent || '').trim() || '•';
    if (!l) s.setAttribute('data-icononly', '1');
    s.setAttribute('aria-label', tt);
    s.addEventListener('click', (e) => { e.stopPropagation(); e.preventDefault(); b.click(); setTimeout(() => syncBtn(b, s), 60); });
    let out = s;
    if (!l) { const t = document.createElement('sl-tooltip'); t.content = tt; t.appendChild(s); out = t; }
    b.before(out); hide(b); syncBtn(b, s);
    const mo = new MutationObserver(() => syncBtn(b, s)); mo.observe(b, { attributes: true, childList: true, characterData: true, subtree: true });
    reg.set(b, { el: out, sync: () => syncBtn(b, s) });
  }
  function fire(el, t, init) { el.dispatchEvent(new Event(t, Object.assign({ bubbles: true }, init || {}))); }
  function convSelect(sel) {
    const s = document.createElement('sl-select'); s.className = 's6sl s6f'; s.size = 'large'; s.hoist = true; s.setAttribute('data-s6for', sel.id || '');
    s.setAttribute('placeholder', sel.getAttribute('aria-label') || sel.title || 'Выбрать');
    const fill = () => { s.innerHTML = [...sel.options].map((o) => '<sl-option value="' + esc(o.value) + '">' + esc(o.textContent) + '</sl-option>').join(''); s.value = sel.value; };
    fill(); s.addEventListener('sl-change', () => { if (sel.value !== s.value) { sel.value = s.value; fire(sel, 'input'); fire(sel, 'change'); } });
    sel.before(s); hide(sel);
    const mo = new MutationObserver(fill); mo.observe(sel, { childList: true, subtree: true });
    reg.set(sel, { el: s, sync: () => { if (s.value !== sel.value) s.value = sel.value; sel.disabled ? s.setAttribute('disabled', '') : s.removeAttribute('disabled'); } });
  }
  function convText(inp) {
    const ta = inp.tagName === 'TEXTAREA', s = document.createElement(ta ? 'sl-textarea' : 'sl-input');
    s.className = 's6sl s6f'; s.size = 'large'; s.setAttribute('data-s6for', inp.id || '');
    if (!ta) s.type = inp.type === 'search' ? 'search' : (['number', 'url', 'email', 'password'].includes(inp.type) ? inp.type : 'text'); else s.rows = inp.rows || 2;
    ['placeholder', 'min', 'max', 'step', 'maxlength'].forEach((a) => { if (inp.hasAttribute(a)) s.setAttribute(a, inp.getAttribute(a)); });
    s.setAttribute('aria-label', inp.getAttribute('aria-label') || inp.placeholder || inp.title || 'Поле'); s.value = inp.value;
    if (!ta) s.clearable = inp.type === 'search';
    s.addEventListener('sl-input', () => { if (inp.value !== s.value) { inp.value = s.value; fire(inp, 'input'); } });
    s.addEventListener('sl-change', () => fire(inp, 'change'));
    s.addEventListener('keydown', (e) => { inp.dispatchEvent(new KeyboardEvent('keydown', { key: e.key, code: e.code, keyCode: e.keyCode, shiftKey: e.shiftKey, ctrlKey: e.ctrlKey, metaKey: e.metaKey, bubbles: true, cancelable: true })); });
    inp.before(s); hide(inp);
    reg.set(inp, { el: s, sync: () => { if (s.value !== inp.value) s.value = inp.value; inp.disabled ? s.setAttribute('disabled', '') : s.removeAttribute('disabled'); } });
  }
  function convCheck(inp) {
    const s = document.createElement('sl-checkbox'); s.className = 's6sl'; s.size = 'large'; s.setAttribute('data-s6for', inp.id || '');
    const lb = inp.closest('label'); const txt = lb ? [...lb.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(' ').trim() : '';
    s.textContent = txt || inp.getAttribute('aria-label') || inp.title || ''; s.checked = inp.checked;
    s.addEventListener('sl-change', () => { if (inp.checked !== s.checked) inp.click(); });
    inp.before(s); hide(inp);
    if (lb && txt) [...lb.childNodes].forEach((n) => { if (n.nodeType === 3) n.textContent = ''; });
    reg.set(inp, { el: s, sync: () => { s.checked = inp.checked; inp.disabled ? s.setAttribute('disabled', '') : s.removeAttribute('disabled'); } });
  }
  function convRange(inp) {
    const s = document.createElement('sl-range'); s.className = 's6sl s6f'; s.setAttribute('data-s6for', inp.id || '');
    ['min', 'max', 'step'].forEach((a) => { if (inp.hasAttribute(a)) s[a] = Number(inp.getAttribute(a)); }); s.value = Number(inp.value);
    s.setAttribute('aria-label', inp.getAttribute('aria-label') || inp.title || 'Значение');
    s.addEventListener('sl-input', () => { inp.value = s.value; fire(inp, 'input'); }); s.addEventListener('sl-change', () => fire(inp, 'change'));
    inp.before(s); hide(inp);
    reg.set(inp, { el: s, sync: () => { if (Number(s.value) !== Number(inp.value)) s.value = Number(inp.value); } });
  }
  const CHIP = '.s2-chip,.chip,.badge,.pill,.tag,.st-chip,.status,.stat-chip,.nox-chip';
  function convChip(c) {
    if (c.tagName === 'SL-BADGE') return;
    const s = document.createElement('sl-badge'); s.className = 's6bd'; s.pill = true;
    const sync = () => { const cl = c.className || ''; const v = /(^|\s)(ok|good|on|live|ready|success|online)(\s|$)/.test(cl) ? 'success' : /(warn|wait|busy|pending)/.test(cl) ? 'warning' : /(bad|err|fail|off|danger|down)/.test(cl) ? 'danger' : /(^|\s)(acc|primary|new|hot)(\s|$)/.test(cl) ? 'primary' : 'neutral'; if (s.variant !== v) s.variant = v; const t = c.textContent.trim(); if (s.textContent !== t) s.textContent = t; };
    sync(); c.before(s); hide(c); new MutationObserver(sync).observe(c, { attributes: true, childList: true, characterData: true, subtree: true });
    reg.set(c, { el: s, sync });
  }
  function run() {
    reg.forEach((v, k) => { if (!k.isConnected) { v.el.remove(); reg.delete(k); } });
    document.querySelectorAll(BTN).forEach((b) => { if (!skip(b) && !b.classList.contains('s6h')) { try { convBtn(b); } catch (e) { } } });
    document.querySelectorAll('main.page select:not([data-s6]),main.page textarea:not([data-s6]),main.page input:not([data-s6])').forEach((i) => {
      if (skip(i)) return; const t = (i.type || '').toLowerCase();
      try {
        if (i.tagName === 'SELECT') { if (!i.multiple) convSelect(i); }
        else if (i.tagName === 'TEXTAREA') convText(i);
        else if (['text', 'search', 'number', 'url', 'email', 'password', ''].includes(t)) convText(i);
        else if (t === 'checkbox') convCheck(i);
        else if (t === 'range') convRange(i);
      } catch (e) { }
    });
    document.querySelectorAll('main.page ' + CHIP.split(',').join(',main.page ')).forEach((c) => { if (!c.closest(SKIP) && c.getAttribute('data-s6') == null && c.tagName !== 'SL-BADGE' && !c.querySelector('button,a')) { try { convChip(c); } catch (e) { } } });
    ask();
  }
  /* «Спросить NOX»: связь страницы с ИИ */
  function ask() {
    if (document.getElementById('s6Ask')) return; const wrap = document.querySelector('main.page .wrap'); if (!wrap) return;
    const bar = document.createElement('div'); bar.className = 's6bar'; bar.innerHTML = '<sl-badge variant="neutral" pill class="s6bd">ИИ</sl-badge><sl-button id="s6Ask" size="large" variant="primary" class="s6sl"><sl-icon slot="prefix" library="tabler" name="sparkles"></sl-icon>Спросить NOX</sl-button>';
    const ph = wrap.querySelector('.ph'); (ph || wrap).insertAdjacentElement(ph ? 'afterend' : 'afterbegin', bar);
    const d = document.createElement('sl-dialog'); d.label = 'Спросить NOX · ' + (document.title.split('·').pop() || page).trim(); d.className = 's6dlg';
    d.innerHTML = '<sl-textarea class="s6q" rows="3" size="large" placeholder="Вопрос или команда по этой странице"></sl-textarea><div class="s6a" aria-live="polite"><div class="ds-empty">Ответ появится здесь.</div></div><sl-button slot="footer" class="s6go" variant="primary" size="large">Отправить</sl-button><sl-button slot="footer" class="s6x" size="large">Закрыть</sl-button>';
    document.body.appendChild(d);
    bar.querySelector('#s6Ask').addEventListener('click', () => d.show());
    d.querySelector('.s6x').addEventListener('click', () => d.hide());
    const go = d.querySelector('.s6go'), q = d.querySelector('.s6q'), out = d.querySelector('.s6a');
    async function send() {
      const text = (q.value || '').trim(); if (!text) { q.focus(); return; }
      go.loading = true; out.innerHTML = '<sl-skeleton effect="pulse" style="height:20px;margin:8px 0"></sl-skeleton><sl-skeleton effect="pulse" style="height:20px;width:70%"></sl-skeleton>';
      const full = 'Страница NOX «' + page + '». ' + text;
      try {
        const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ stream: true, nox_mode: 'fast', messages: [{ role: 'user', content: full }], message: { role: 'user', content: full } }) });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '', acc = '';
        for (;;) { const x = await rd.read(); if (x.done) break; buf += dec.decode(x.value, { stream: true }); const ls = buf.split('\n'); buf = ls.pop(); ls.forEach((ln) => { ln = ln.replace(/^data:\s*/, '').trim(); if (!ln || ln === '[DONE]') return; try { const j = JSON.parse(ln); const c = (j.message && j.message.content) || (j.choices && j.choices[0] && ((j.choices[0].delta && j.choices[0].delta.content) || (j.choices[0].message && j.choices[0].message.content))) || j.response || j.content || ''; if (typeof c === 'string') acc += c; } catch (e) { } }); out.textContent = acc; }
        if (!acc) out.innerHTML = '<div class="ds-empty">NOX не вернул текст. Повторите запрос.</div>';
      } catch (e) { out.innerHTML = '<div class="ds-empty">ИИ недоступен: ' + esc(e.message) + '</div>'; }
      go.loading = false;
    }
    go.addEventListener('click', send);
    q.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) send(); });
  }
  const go = () => { try { run(); } catch (e) { } };
  const start = () => { go(); setTimeout(go, 800); setTimeout(go, 2500); let t; new MutationObserver(() => { clearTimeout(t); t = setTimeout(go, 250); }).observe(document.body, { childList: true, subtree: true }); setInterval(() => reg.forEach((v) => { try { v.sync(); } catch (e) { } }), 500); };
  if (document.readyState !== 'loading') start(); else document.addEventListener('DOMContentLoaded', start);
})();
S6EOF_js
cat > nox-s6.css <<'S6EOF_css'
/* S6: единый слой sl-* + слои photo + ритм сетки news. Шрифт >=12, цель 44, сетка 8. */
.s6h{display:none!important}
.s6sl{--sl-input-height-large:44px;--sl-input-font-size-large:14px;max-width:100%}
sl-button.s6sl::part(base){min-height:44px;min-width:44px;font-size:14px;letter-spacing:0;background:var(--ds-glass,rgba(255,235,220,.06));border:1px solid var(--ds-line,rgba(255,255,255,.14));color:var(--ds-ink,#efe6df);box-shadow:var(--ds-e1);transition:background .15s,border-color .15s,transform .1s}
sl-button.s6sl::part(base):hover{background:var(--ds-glass-hi,rgba(255,235,220,.11))}
sl-button.s6sl[variant=primary]::part(base){background:rgba(233,180,101,.18);border-color:rgba(233,180,101,.55);color:#f6dcb0}
sl-button.s6sl[variant=danger]::part(base){background:rgba(229,100,90,.16);border-color:rgba(229,100,90,.5);color:#ffb3ab}
sl-button.s6sl[data-icononly]::part(label){padding:0 8px}
sl-button.s6sl:focus-visible::part(base){outline:2px solid #e9b465;outline-offset:2px}
.s6f{display:block;width:100%}
sl-select.s6f::part(combobox),sl-input.s6f::part(base),sl-textarea.s6f::part(base){background:rgba(2,3,10,.55);border-color:var(--ds-line,rgba(255,255,255,.14));color:var(--ds-ink,#efe6df);min-height:44px}
sl-textarea.s6f::part(textarea){font-size:14px;line-height:1.4}
.s6bd{--sl-font-size-x-small:12px;font-size:12px;min-height:24px;padding:2px 10px;letter-spacing:.02em}
.s6bar{display:flex;align-items:center;justify-content:flex-end;gap:8px;margin:8px 0 16px}
.s6dlg{--width:min(560px,94vw)}
.s6dlg::part(panel){background:rgba(16,12,12,.82);backdrop-filter:blur(22px) saturate(1.3);border:1px solid var(--ds-line,rgba(255,255,255,.14));box-shadow:var(--ds-e2)}
.s6dlg .s6a{margin-top:16px;max-height:40vh;overflow:auto;white-space:pre-wrap;font-size:14px;line-height:1.5}
.ps-row>.s6sl,.ps-row>sl-tooltip{flex:1 1 112px}
.ps-row>sl-select,.ps-row>sl-input{flex:1 1 100%}

/* PHOTO: плавающие стеклянные панели, слои */
body[data-page=photo] .ps{position:relative;display:block;height:calc(100vh - 250px);min-height:520px;isolation:isolate}
body[data-page=photo] .ps-ed{position:absolute;inset:0;z-index:1;border-radius:16px;box-shadow:var(--ds-e1)}
body[data-page=photo] .ps-ai.glass{position:absolute;z-index:3;top:72px;right:16px;bottom:16px;width:min(336px,42%);padding:8px 16px 16px;border-radius:16px;background:rgba(14,10,10,.64);backdrop-filter:blur(24px) saturate(1.4);-webkit-backdrop-filter:blur(24px) saturate(1.4);border:1px solid var(--ds-line,rgba(255,255,255,.14));box-shadow:var(--ds-e2)}
body[data-page=photo] .ps-ai .ps-box{padding:16px 0!important}
body[data-page=photo] .ps-ai .ps-box>h3{min-height:44px;font-size:12px}
body[data-page=photo] .ps-log{max-height:24vh}
body[data-page=photo] .ph .acts{padding:8px;border-radius:16px;background:rgba(14,10,10,.5);backdrop-filter:blur(18px);border:1px solid var(--ds-line,rgba(255,255,255,.14));box-shadow:var(--ds-e1)}
body[data-page=photo] .ps-th{gap:8px}
@media (max-width:900px){
 body[data-page=photo] .ps{display:flex;flex-direction:column;gap:16px;height:auto}
 body[data-page=photo] .ps-ed{position:relative;inset:auto;height:60vh!important}
 body[data-page=photo] .ps-ai.glass{position:relative;inset:auto;width:auto;box-shadow:var(--ds-e1)}
}

/* NEWS: единый ритм сетки, сетка 8 px */
body[data-page=news] .nw-grid{grid-template-columns:repeat(auto-fill,minmax(256px,1fr));grid-auto-rows:1fr;gap:24px;margin-top:24px;align-items:stretch}
body[data-page=news] .nw-cd{height:100%;border-radius:16px;box-shadow:var(--ds-e1)}
body[data-page=news] .nw-cd .im{aspect-ratio:16/10;flex:none}
body[data-page=news] .nw-cd .b{flex:1;display:flex;flex-direction:column;gap:8px;padding:16px}
body[data-page=news] .nw-cd h4{margin:0;font-size:16px;line-height:24px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;min-height:72px}
body[data-page=news] .nw-src{font-size:12px;min-height:24px}
body[data-page=news] .nw-main{gap:24px;margin-top:16px}
body[data-page=news] .nw-li{padding:16px 0;min-height:88px}
body[data-page=news] .nw-top{gap:8px;padding:8px 0}
S6EOF_css
python3 - photo,news <<'PY'
import sys,os,shutil
for p in sys.argv[1].split(','):
    f=p+'.html'
    if not os.path.exists(f): print('NOFILE',f); continue
    t=open(f).read()
    if 'nox-s6-sl.js' in t: print('already',p); continue
    if not os.path.exists(f+'.bak_s6_1'): shutil.copy(f,f+'.bak_s6_1')
    t=t.replace('</head>','<link rel="stylesheet" href="./nox-s6.css?v=1">\n</head>',1)
    t=t.replace('</body>','<script src="./vendor/shoelace/cdn/shoelace.js" type="module"></script>\n<script src="./nox-s6-sl.js?v=1" defer></script>\n</body>',1) if False else t.replace('</body>','<script src="./nox-s6-sl.js?v=1" defer></script>\n</body>',1)
    open(f,'w').write(t); print('injected',p)
PY
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; $PY -c 'import playwright' 2>/dev/null || PY=python3
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
S6P=photo,news $PY /tmp/s6_shot.py 2>&1 | tail -n 400
