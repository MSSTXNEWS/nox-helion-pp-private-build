/* NOX · слой UI чата в духе assistant-ui / Vercel AI Elements (React). Логика отправки/STOP/истории/оценок остаётся в nox-wow.js:
   этот слой только наблюдает поток /api/turn (fetch-tap) и добавляет блоки рассуждения, ветки ответа, артефакты, источники, карту мышления, голос. */
import React, { useState, useEffect, useSyncExternalStore, Suspense, lazy } from 'react';
import { createRoot } from 'react-dom/client';
const FlowPanel = lazy(() => import('./flowpanel.jsx'));
const VoicePanel = lazy(() => import('./voice.jsx'));

/* ---------- хранилище ---------- */
export const store = { turns: [], byIdx: new Map(), versions: new Map(), view: new Map(), artifact: null, flow: false, voice: false, rev: 0, ls: new Set() };
const emit = () => { store.rev++; store.ls.forEach((f) => f()); };
export const useStore = () => useSyncExternalStore((f) => { store.ls.add(f); return () => store.ls.delete(f); }, () => store.rev);
export const splitThinkRaw = (raw) => { const i = raw.indexOf('<think>'); if (i < 0) { const e = raw.indexOf('</think>'); return e >= 0 ? { think: raw.slice(0, e), ans: raw.slice(e + 8), open: false } : { think: '', ans: raw, open: false }; } const j = raw.indexOf('</think>', i); return j < 0 ? { think: raw.slice(i + 7), ans: raw.slice(0, i), open: true } : { think: raw.slice(i + 7, j), ans: raw.slice(0, i) + raw.slice(j + 8), open: false }; };
export const urlsOf = (t) => [...new Set((String(t).match(/https?:\/\/[^\s<>)"'\]]+/g) || []).map((u) => u.replace(/[.,;:]+$/, '')))];

/* ---------- fetch-tap: читаем копию потока хода ---------- */
const ofetch = window.fetch.bind(window);
window.fetch = async function (input, init) {
  const res = await ofetch(input, init);
  try {
    const url = typeof input === 'string' ? input : input.url;
    if (/\/api\/turn(\?|$)/.test(url) && init && init.method === 'POST') tap(res.clone(), init);
  } catch (e) { /* не мешаем основному потоку */ }
  return res;
};
async function tap(res, init) {
  let body = {}; try { body = JSON.parse(init.body); } catch (e) { /* */ }
  const els = document.querySelectorAll('#msgs .m.a'); const el = els[els.length - 1];
  const idx = el ? +el.dataset.i : -1;
  const t = { idx, msg: body.message || '', cid: body.cid || body.conversation_id || '', raw: '', levels: [], t0: performance.now(), t1: 0, chunks: 0, done: false };
  store.turns.push(t); if (idx >= 0) store.byIdx.set(idx, t); emit();
  const key = t.cid + '|' + t.msg;
  try {
    const rd = res.body.getReader(), dec = new TextDecoder(); let buf = '';
    for (;;) {
      const { value, done } = await rd.read(); if (done) break; buf += dec.decode(value, { stream: true }); let k;
      while ((k = buf.indexOf('\n')) >= 0) { const line = buf.slice(0, k).trim(); buf = buf.slice(k + 1); if (!line) continue; let f; try { f = JSON.parse(line); } catch (e) { continue; }
        if (f.t === 'delta') { t.raw += f.text || ''; t.chunks++; } else if (f.t === 'level' && f.level) t.levels.push(f.level); emit(); }
    }
  } catch (e) { /* остановлено */ }
  t.done = true; t.t1 = performance.now();
  const ans = splitThinkRaw(t.raw).ans.trim();
  if (ans) { const v = store.versions.get(key) || []; if (v[v.length - 1] !== ans) v.push(ans); store.versions.set(key, v); store.view.delete(key); t.key = key; }
  emit();
}

/* ---------- блоки сообщения ---------- */
const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
function Reasoning({ t }) {
  const { think, open } = splitThinkRaw(t.raw); const [o, setO] = useState(null);
  if (!think.trim()) return null; const sec = (((t.t1 || performance.now()) - t.t0) / 1000).toFixed(1);
  const isOpen = o === null ? open : o;
  return <div className="nui-reason" data-open={isOpen}>
    <button type="button" className="nui-rh" aria-expanded={isOpen} onClick={() => setO(!isOpen)}><span className="nui-dot" data-live={open} />Рассуждение<em>{open ? 'идёт…' : sec + ' с'}</em><i aria-hidden="true">{isOpen ? '▾' : '▸'}</i></button>
    {isOpen && <div className="nui-rb">{think.trim()}</div>}
  </div>;
}
function Branch({ k }) {
  const v = store.versions.get(k) || []; if (v.length < 2) return null; const cur = store.view.has(k) ? store.view.get(k) : v.length - 1;
  const go = (d) => { store.view.set(k, Math.min(v.length - 1, Math.max(0, cur + d))); emit(); };
  return <div className="nui-branch" role="group" aria-label="Варианты ответа"><button type="button" aria-label="Предыдущий вариант" disabled={cur === 0} onClick={() => go(-1)}>‹</button><span>{cur + 1}/{v.length}</span><button type="button" aria-label="Следующий вариант" disabled={cur === v.length - 1} onClick={() => go(1)}>›</button></div>;
}
function Extras({ el }) {
  useStore(); const idx = +el.dataset.i; const t = store.byIdx.get(idx);
  const [blocks, setBlocks] = useState([]); const [links, setLinks] = useState([]);
  useEffect(() => {
    const txt = el.querySelector('.txt'); if (!txt) return; let tm = 0;
    const scan = () => { tm = 0; setBlocks([...txt.querySelectorAll('pre')].map((p) => { const c = p.querySelector('code'); return { lang: p.dataset.lang || 'code', text: (c || p).textContent }; }).filter((b) => b.text.trim()));
      setLinks(urlsOf(txt.innerText || '')); };
    const mo = new MutationObserver(() => { if (!tm) tm = setTimeout(scan, 250); }); mo.observe(txt, { childList: true, subtree: true, characterData: true }); scan(); return () => { mo.disconnect(); clearTimeout(tm); };
  }, [el]);
  const key = t && t.key; const vers = key ? store.versions.get(key) || [] : []; const cur = key ? (store.view.has(key) ? store.view.get(key) : vers.length - 1) : 0; const alt = key && vers.length > 1 && cur !== vers.length - 1;
  useEffect(() => { el.classList.toggle('nui-viewalt', !!alt); }, [alt, el]);
  const doc = t && t.done && !blocks.length ? splitThinkRaw(t.raw).ans.trim() : '';
  return <>
    {t && <Reasoning t={t} />}
    {key && <Branch k={key} />}
    {alt && <div className="nui-alt">{vers[cur].split(/\n{2,}/).map((p, i) => <p key={i}>{p}</p>)}</div>}
    {(blocks.length > 0 || doc.length > 900) && <div className="nui-art" role="group" aria-label="Артефакты">
      {blocks.map((b, i) => <button type="button" key={i} onClick={() => { store.artifact = { title: 'Код · ' + b.lang, lang: b.lang, text: b.text }; emit(); }}><b>{'</>'}</b>{b.lang} · {b.text.split('\n').length} стр.</button>)}
      {doc.length > 900 && <button type="button" onClick={() => { store.artifact = { title: 'Документ', lang: 'md', text: doc }; emit(); }}><b>¶</b>Документ · {doc.length} симв.</button>}
    </div>}
    {links.length > 0 && <div className="nui-src" role="group" aria-label="Источники"><span>Источники</span>{links.slice(0, 6).map((u, i) => { let h = u; try { h = new URL(u).hostname.replace(/^www\./, ''); } catch (e) { /* */ } return <a key={i} href={u} target="_blank" rel="noopener noreferrer">{i + 1} · {h}</a>; })}</div>}
  </>;
}
function ArtifactPanel() {
  useStore(); const a = store.artifact; if (!a) return null; const [ok, setOk] = useState(false);
  const dl = () => { const ext = { python: 'py', javascript: 'js', js: 'js', bash: 'sh', html: 'html', md: 'md', css: 'css', json: 'json' }[a.lang] || 'txt'; const u = URL.createObjectURL(new Blob([a.text], { type: 'text/plain' })); const l = document.createElement('a'); l.href = u; l.download = 'nox-artifact.' + ext; l.click(); setTimeout(() => URL.revokeObjectURL(u), 3000); };
  const cp = async () => { try { await navigator.clipboard.writeText(a.text); setOk(true); setTimeout(() => setOk(false), 1400); } catch (e) { /* */ } };
  return <aside className="nui-panel" aria-label="Артефакт"><header><b>{a.title}</b><span><button type="button" onClick={cp}>{ok ? 'Скопировано' : 'Копировать'}</button><button type="button" onClick={dl}>Скачать</button><button type="button" aria-label="Закрыть" onClick={() => { store.artifact = null; emit(); }}>×</button></span></header><pre>{a.text}</pre></aside>;
}
function Overlays() {
  useStore();
  return <Suspense fallback={null}>{store.flow && <FlowPanel store={store} emit={emit} useStore={useStore} splitThinkRaw={splitThinkRaw} urlsOf={urlsOf} />}{store.voice && <VoicePanel onClose={() => { store.voice = false; emit(); }} />}</Suspense>;
}

/* ---------- монтирование ---------- */
const roots = new Map();
function mount(el) {
  if (roots.has(el) || !el.classList.contains('a')) return; const b = el.querySelector('.bubble'); if (!b) return;
  const host = document.createElement('div'); host.className = 'nui-x'; b.prepend(host); const r = createRoot(host); roots.set(el, r); r.render(<Extras el={el} />);
}
function boot() {
  const msgs = document.querySelector('#msgs'); if (!msgs) return setTimeout(boot, 200);
  const scan = () => msgs.querySelectorAll(':scope>.m.a').forEach(mount);
  new MutationObserver((ms) => { scan(); ms.forEach((m) => m.removedNodes.forEach((n) => { const r = roots.get(n); if (r) { setTimeout(() => r.unmount(), 0); roots.delete(n); } })); }).observe(msgs, { childList: true }); scan();
  const host = document.createElement('div'); host.id = 'nui-overlays'; document.body.appendChild(host); createRoot(host).render(<><ArtifactPanel /><Overlays /></>);
  const tb = document.querySelector('#ctb .tb2');
  if (tb) {
    const mk = (id, icon, label, fn) => { const b = document.createElement('button'); b.type = 'button'; b.id = id; b.title = label; b.setAttribute('aria-label', label); b.innerHTML = '<sl-icon library="tabler" name="' + icon + '"></sl-icon>'; b.addEventListener('click', fn); tb.prepend(b); };
    mk('nuiVoice', 'headset', 'Голосовой режим', () => { store.voice = !store.voice; emit(); });
    mk('nuiFlow', 'hierarchy-2', 'Карта мышления', () => { store.flow = !store.flow; emit(); });
  }
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && (store.artifact || store.flow || store.voice)) { store.artifact = null; store.flow = false; store.voice = false; emit(); } });
}
boot();
