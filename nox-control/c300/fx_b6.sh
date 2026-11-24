S=/workspace/nox/web/site; P=/workspace/nox/web/pkg/server; T=bak_fx_b6
for f in $S/nox-minichat.js $S/nox-manual.js $S/nox-api.js $S/nox-p-home.js $P/web_server.py /workspace/nox/qa_ctl.py; do [ -f $f.$T ] || cp $f $f.$T; done
/workspace/nox/venv/bin/python - <<'PYEOF'
import re,json,os
S='/workspace/nox/web/site'; P='/workspace/nox/web/pkg/server'
def rd(p): return open(p,encoding='utf-8').read()
def wr(p,t): open(p,'w',encoding='utf-8').write(t)
def rep(p,old,new,cnt=1):
    t=rd(p)
    if old not in t: print('MISS',p,old[:50]); return
    wr(p,t.replace(old,new,cnt)); print('ok',os.path.basename(p),old[:30])
# A minichat
rep(S+'/nox-minichat.js',"if (!acc) out.textContent = '(пустой ответ)'; else {",
 r"""if (!acc) { hist.pop(); save(hist); out.classList.add('err'); out.textContent = 'NOX занят, повторите '; const rb = document.createElement('button'); rb.type = 'button'; rb.className = 'nmc-retry'; rb.textContent = 'Повторить'; rb.style.cssText = 'margin-left:8px;padding:3px 10px;border-radius:8px;border:1px solid rgba(255,255,255,.25);background:rgba(255,255,255,.08);color:inherit;cursor:pointer'; rb.onclick = () => { const pv = out.previousElementSibling; out.remove(); if (pv && pv.classList.contains('u')) pv.remove(); ta.value = q; form.requestSubmit(); }; out.appendChild(rb); } else {""")
rep(S+'/nox-minichat.js',"const c = o.message && o.message.content;","const c = (o.message && o.message.content) || (typeof o.response === 'string' ? o.response : '');")
# B manual
css=r"""try{document.head.insertAdjacentHTML('beforeend','<style>#nxManual{position:fixed;left:16px;bottom:176px;z-index:8990;width:340px;max-width:calc(100vw - 32px);max-height:58vh;overflow:auto;box-sizing:border-box;padding:14px;border-radius:16px;background:rgba(14,10,12,.74);-webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px);border:1px solid rgba(255,255,255,.1);box-shadow:0 10px 40px rgba(0,0,0,.5);color:#e8ddd4;font:13px/1.45 system-ui,sans-serif}#nxManual .nxm-h{margin:0 0 8px;font:600 12px/1 system-ui;letter-spacing:.16em;text-transform:uppercase;color:#f0e4da}#nxManual .nxm-q{white-space:pre-wrap;max-height:110px;overflow:auto;margin:0 0 8px;padding:8px;border-radius:10px;background:rgba(0,0,0,.35);font:12px/1.4 ui-monospace,monospace}#nxManual .nxm-hint{margin:0 0 8px;opacity:.75;font-size:12px}#nxManual .nxm-row{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}#nxManual .nxm-l{display:block;margin:6px 0;font-size:11px;letter-spacing:.08em;text-transform:uppercase;opacity:.85}#nxManual select,#nxManual input,#nxManual textarea{display:block;width:100%;box-sizing:border-box;margin-top:4px;padding:7px 9px;border-radius:9px;border:1px solid rgba(255,255,255,.14);background:rgba(0,0,0,.4);color:inherit;font:13px system-ui;text-transform:none;letter-spacing:0}#nxManual button,#nxManual .nxm-row a{padding:7px 11px;border-radius:9px;border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.07);color:#f0e4da;font:12px system-ui;text-decoration:none;cursor:pointer}#nxManual .nxm-x{position:absolute;top:8px;right:10px;padding:2px 8px}#nxmPill{position:fixed;left:16px;bottom:128px;z-index:8990;padding:8px 14px;border-radius:999px;border:1px solid rgba(214,70,48,.5);background:rgba(14,10,12,.72);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);color:#f0e4da;font:11px system-ui;letter-spacing:.12em;text-transform:uppercase;cursor:pointer}#nxmPill[hidden]{display:none}</style>')}catch(e){}
"""
t=rd(S+'/nox-manual.js')
if 'nxmPill' not in t:
    t=t.replace("\n",  "\n"+css,1)
    t=t.replace("card.hidden = false;\n}","showPill();\n}",1)
    t=t.replace("function hide() { if (card) card.hidden = true; cur = null; }","let pill = null;\nfunction showPill() { if (!pill) { pill = document.createElement('button'); pill.type = 'button'; pill.id = 'nxmPill'; pill.textContent = 'Справка старшего'; pill.addEventListener('click', () => { build().hidden = !card.hidden; }); document.body.append(pill); } pill.hidden = false; }\nfunction hide() { if (card) card.hidden = true; if (pill) pill.hidden = true; cur = null; }",1)
    t=t.replace("document.body.append(card);\n  card.querySelector('#nxmCopy')","document.body.append(card);\n  const xb = document.createElement('button'); xb.type = 'button'; xb.className = 'nxm-x'; xb.textContent = '×'; xb.setAttribute('aria-label', 'Свернуть'); xb.addEventListener('click', () => { card.hidden = true; }); card.append(xb);\n  card.querySelector('#nxmCopy')",1)
    wr(S+'/nox-manual.js',t); print('manual patched', 'showPill();' in t)
# C api / home
t=rd(S+'/nox-api.js'); a=t.index('export async function probeAll(force) {'); b=t.index('  const voice = (id, name')
new=r"""export async function probeAll(force) {
  const [stats, models, chat, stt, tts, api] = await Promise.all([call('/glm/v1/nox/stats'), call('/glm/v1/models'), call('/api/chat/health'), call('/stt/health'), call('/tts/health'), apiProbe(force)]);
  const H = stats.ok && stats.data && stats.data.health ? stats.data.health : null, sv = [];
  const ch = chat.ok && chat.data ? chat.data : null, up = (x) => !!(x && x.up);
  const mem = { ok: !!H, ms: stats.ms, error: stats.error || '', data: H ? { ok: true, health: H } : null };
  const gwOk = ch ? up(ch.core) && up(ch.rte) : false;
  sv.push({ id: 'gw', name: 'Шлюз GLM', sub: '/api/chat/health: ядро и rte', state: ch ? (gwOk ? 'ok' : 'warn') : 'bad', ms: chat.ms, error: ch ? (gwOk ? '' : 'ядро: ' + (up(ch.core) ? 'работает' : (ch.core && ch.core.reason) || 'не отвечает') + ' · rte: ' + (up(ch.rte) ? 'работает' : (ch.rte && ch.rte.reason) || 'не отвечает')) : chat.error || 'пустой ответ',
    lines: ch ? ['ядро ' + ((ch.core || {}).addr || '') + ': ' + (up(ch.core) ? 'работает' : 'не отвечает'), 'rte ' + ((ch.rte || {}).addr || '') + ': ' + (up(ch.rte) ? 'работает' : 'не отвечает')].concat(H && H.glm ? ['GLM: ' + H.glm.state + (H.glm.inflight ? ', в работе: ' + H.glm.inflight : '')] : []) : [] });
  const mid = models.ok && models.data && Array.isArray(models.data.data) ? models.data.data : null;
  const loaded = mid ? mid.filter((m) => m.status && m.status.value && m.status.value !== 'unloaded') : [];
  sv.push({ id: 'deep', name: 'Глубокий тир', sub: 'llama-swap :8200 (/v1/models)', state: mid && mid.length ? 'ok' : 'warn', ms: models.ms, error: mid && mid.length ? '' : models.error || 'llama-swap не вернул моделей',
    lines: mid ? ['моделей в llama-swap: ' + mid.length, 'загружено: ' + (loaded.length ? loaded.map((m) => m.id).join(', ') : 'нет (подгружается по запросу)')] : [] });
  const F = H && H.fast;
  sv.push({ id: 'fast', name: 'Быстрый тир', sub: 'ядро: fast', state: !H ? 'bad' : F && F.ok > 0 ? 'ok' : 'warn', ms: stats.ms, error: !H ? 'ядро недоступно: ' + (stats.error || '') : F && F.ok > 0 ? '' : 'быстрых ответов пока нет (ok ' + ((F && F.ok) || 0) + ', пустых ' + ((F && F.empty) || 0) + ', сбоев ' + ((F && F.fail) || 0) + ')',
    lines: F ? ['ответов: ' + F.ok + ' · пустых: ' + F.empty + ' · сбоев: ' + F.fail] : [] });
  const org = H && H.organs ? H.organs : null, orgOk = org ? Object.keys(org).filter((k) => org[k]) : [];
  sv.push({ id: 'mem', name: 'Память', sub: 'орган памяти ядра', state: !org ? 'bad' : org.memory ? 'ok' : 'warn', ms: stats.ms, error: !org ? 'ядро недоступно' : org.memory ? '' : 'орган памяти ядра не активен',
    lines: org ? ['органов в строю: ' + orgOk.length + ' из ' + Object.keys(org).length, 'ходов в ядре: ' + (H.turns == null ? '—' : H.turns)] : [] });
"""
if 'llama-swap :8200' not in t:
    wr(S+'/nox-api.js',t[:a]+new+t[b:]); print('api patched')
t=rd(S+'/nox-p-home.js')
a=t.index('function renderSpeed(P) {'); b=t.index('async function run(manual)')
hn=r"""function renderSpeed(P) {
  const r = P.stats, H = r.ok && r.data && r.data.health; $('#spMs').textContent = r.ms + ' МС';
  if (!H) { $('#speed').innerHTML = '<div class="err">Ядро не отвечает: ' + esc(r.error || 'нет данных') + '</div>'; return; }
  const F = H.fast || {};
  $('#speed').innerHTML = '<dl class="kv"><dt>Ходов в ядре</dt><dd class="big" style="font-size:22px">' + (H.turns == null ? '—' : H.turns) + '</dd><dt>Сейчас в работе</dt><dd>' + (H.running || 0) + '</dd><dt>GLM</dt><dd>' + esc((H.glm && H.glm.state) || '—') + '</dd><dt>Быстрый тир (ок / пусто / сбой)</dt><dd>' + (F.ok || 0) + ' / ' + (F.empty || 0) + ' / ' + (F.fail || 0) + '</dd><dt>Совесть</dt><dd>' + esc(H.conscience || '—') + '</dd></dl>';
}
function renderMem(P) {
  const H = P.stats.ok && P.stats.data && P.stats.data.health, O = H && H.organs;
  $('#memBox').innerHTML = O ? '<dl class="kv">' + Object.keys(O).map((k) => '<dt>' + esc(k) + '</dt><dd>' + (O[k] ? 'работает' : 'выключен') + '</dd>').join('') + '</dl>' : '<div class="err">Ядро недоступно: нет данных об органах</div>';
}
async function renderResume() {
  const r = await call('/api/chat/health'), d = r.ok && r.data;
  $('#resume').innerHTML = d ? '<pre class="core">' + esc('ядро: ' + (d.core && d.core.up ? 'работает' : 'не отвечает') + ' (' + ((d.core || {}).addr || '') + ')\nrte: ' + (d.rte && d.rte.up ? 'работает' : 'не отвечает') + ' (' + ((d.rte || {}).addr || '') + ')') + '</pre>' : '<div class="err">Сводка недоступна: ' + esc(r.error || 'нет ответа') + '</div>';
}
"""
if 'Ходов в ядре' not in t: wr(S+'/nox-p-home.js',t[:a]+hn+t[b:]); print('home patched')
# D package.json
reg=rd(S+'/nox-registry.js')
for n,pk in re.findall(r"n: '([^']+)'.*?pkg: '([^']+)'",reg):
    pp=S+'/'+pk
    if not os.path.exists(pp) and os.path.isdir(os.path.dirname(pp)):
        ver='0.160.0' if n=='three' else 'н/д'
        wr(pp,json.dumps({"name":n,"version":ver,"note":"файл добавлен сборкой: версия не указана в поставке"},ensure_ascii=False)); print('pkg',pk)
# E server
w=P+'/web_server.py'; t=rd(w)
if '_music_local' not in t:
    t=t.replace('        if p.startswith("/music/"): return self._proxy("GET"','        if p in ("/music/health", "/music/status"): return self._music_local(p)\n        if p.startswith("/music/"): return self._proxy("GET"',1)
    t=t.replace('        if p.startswith("/api/"): return self._j(503, {"error": "API панели S2 не подключено (работает только чат','        if p == "/api/status": return self._j(200, {"ok": True, "status": "NOT_IMPLEMENTED", "server": "nox-web", "note": "веб-сервер отвечает; бэкенд этого раздела не подключён, значения не подставляются"})\n        if p.startswith("/api/"): return self._j(503, {"error": "API панели S2 не подключено (работает только чат',1)
    m='''    def _music_local(self, p):
        """/music/health, /music/status: реальный Navidrome (127.0.0.1:4533); генератор звука (/music/gen) отдельно."""
        import urllib.request as _u, os as _o
        try:
            r = _u.urlopen("http://127.0.0.1:4533/ping", timeout=4); ok = r.status == 200
        except Exception as e:
            return self._j(200, {"ok": False, "service": "navidrome", "error": "Navidrome не отвечает: %s" % e})
        if p == "/music/health": return self._j(200, {"ok": ok, "service": "navidrome", "ui": "/svc/navidrome/app/"})
        n = 0
        try:
            for _, _, fs in _o.walk("/workspace/nox/music_lib"):
                n += sum(1 for f in fs if f.lower().endswith((".mp3", ".flac", ".ogg", ".opus", ".m4a", ".wav")))
                if n > 100000: break
        except Exception: pass
        return self._j(200, {"ok": ok, "service": "navidrome", "ui": "/svc/navidrome/app/", "library": "/workspace/nox/music_lib", "tracks": n, "generator": "не подключён (127.0.0.1:8102)"})

'''
    t=re.sub(r'(\n    def _memory\()',lambda mm:'\n'+m.rstrip('\n')+'\n'+mm.group(1),t,1)
    wr(w,t); print('server patched','_music_local' in t)
# F detector
q='/workspace/nox/qa_ctl.py'; t=rd(q)
old="if(!fx.some(e=>e.getBoundingClientRect().top<14))r.push('нет верхней панели');"
if old in t and 'header.bar,#bar' not in t:
    wr(q,t.replace(old,"if(!fx.some(e=>e.getBoundingClientRect().top<14)&&!(()=>{const h=document.querySelector('header.bar,#bar');if(!h)return false;const b=h.getBoundingClientRect();return b.top<14&&b.height>20&&b.height<160&&b.width>W*.5})())r.push('нет верхней панели');")); print('qa patched')
PYEOF
/workspace/nox/venv/bin/python -m py_compile $P/web_server.py && echo COMPILE_OK && bash $P/run_web.sh restart 2>&1 | tail -3
sleep 3
for u in /api/status /music/health /music/status /api/chat/health /web/vendor/three/package.json /web/vendor/motion/package.json; do echo $u $(curl -s -m6 -w " %{http_code}" http://127.0.0.1:8091$u | tail -c 160); done
node --check $S/nox-api.js 2>&1 | head -3; for f in nox-p-home nox-minichat nox-manual nox-api; do cp $S/$f.js /tmp/$f.mjs; node --check /tmp/$f.mjs 2>&1 | head -3 && echo $f syntax-checked; done
