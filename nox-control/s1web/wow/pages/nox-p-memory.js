/* Память: «Что NOX вспомнил». Поиск, подтверждение, исправление, мягкое удаление и откат через POST /memory/api (recall_api). */
import { $, $$, esc, memory, call, toast } from './nox-api.js';
import { ready } from './nox-nav.js';
import { addCorpus, fuzzy } from './nox-p-memory-extra.js';
const TYPE = { fact: 'ФАКТ', episode: 'ЭПИЗОД', profile: 'ПРОФИЛЬ' };
let last = '', hits = new Map(), cRef = null, dRef = null;
const when = (ts) => (ts ? new Date(ts * 1000).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'medium' }) : '—');
const fail = (r, what) => { const m = (r.data && r.data.error) || r.error || 'неизвестная ошибка'; toast(what + ': ' + m, true); return false; };
async function op(req, what) { const r = await memory(req); if (!r.ok || !r.data || !r.data.ok) { fail(r.ok ? { data: r.data } : r, what); return null; } return r.data; }

async function stats() {
  const r = await call('/memory/health'), s = r.ok && r.data && r.data.stats;
  $('#mStats').className = 'tag ' + (s ? 'on' : 'bad'); $('#mStats').textContent = s ? 'ФАКТОВ ' + s.facts + ' · ЭПИЗОДОВ ' + s.episodes + ' · ПРОФИЛЬ ' + s.profile : 'СЛУЖБА ПАМЯТИ НЕДОСТУПНА';
  $('#mStats').title = s ? '' : r.error || '';
}
async function search(q) {
  const box = $('#results'); q = q.trim(); last = q;
  if (!q) { box.innerHTML = '<div class="empty">Введите запрос.</div>'; $('#rInfo').textContent = ''; return; }
  box.innerHTML = '<div class="empty">Поиск…</div>';
  const r = await memory({ op: 'search', query: q, k: 20 });
  if (!r.ok || !r.data || !r.data.ok) { box.innerHTML = '<div class="err">Поиск не удался: ' + esc((r.data && r.data.error) || r.error) + '</div>'; return; }
  const d = r.data; hits = new Map(d.hits.map((h) => [h.ref, h]));
  $('#rInfo').textContent = d.hits.length + ' · ' + String(d.mode).toUpperCase();
  d.hits.forEach((h) => addCorpus(h.ref, h.text, h.type));
  let fz = [];
  if (!d.hits.length) { const z = fuzzy(q); fz = z || []; fz.forEach((h) => hits.set(h.ref, h)); $('#rInfo').textContent = fz.length ? fz.length + ' · НЕЧЁТКО (FUSE)' : '0 · ' + String(d.mode).toUpperCase(); }
  box.innerHTML = (d.hits.length || fz.length ? (d.hits.length ? d.hits : fz).map((h) => '<article class="hit" data-ref="' + esc(h.ref) + '"><div><div class="tx">' + esc(h.text) + '</div><div class="mt"><span class="tag">' + (TYPE[h.type] || esc(h.type)) + '</span>' + (h.level_name ? '<span class="tag">' + esc(h.level_name) + '</span>' : '') + '<span class="tag">' + esc(h.ref) + '</span><span class="tag">' + (h.parts ? 'релевантность ' : 'нечёткое совпадение ') + h.score + '</span></div></div>'
    + '<span class="seg"><button type="button" data-a="confirm">Верно</button><button type="button" data-a="correct">Исправить</button><button type="button" data-a="delete">Удалить</button></span></article>').join('') : '<div class="empty">По запросу «' + esc(q) + '» NOX ничего не помнит' + (window.Fuse ? ' (нечёткий поиск по уже загруженным записям тоже пуст)' : '') + '.</div>')
    + (d.warnings && d.warnings.length ? '<div class="muted" style="margin-top:6px;font-size:12px">' + d.warnings.map(esc).join('<br>') + '</div>' : '');
}
async function core() {
  const r = await memory({ op: 'core', budget_tokens: 400 });
  if (!r.ok || !r.data || !r.data.ok) { $('#core').innerHTML = '<div class="err">Ядро недоступно: ' + esc((r.data && r.data.error) || r.error) + '</div>'; return; }
  const d = r.data; $('#coreInfo').textContent = d.tokens + ' / ' + d.budget + ' ТОК';
  $('#core').innerHTML = d.text ? '<pre class="core">' + esc(d.text) + '</pre>' : '<div class="empty">Ядро пусто: подтверждённых фактов и профиля пока нет.</div>';
}
async function journal() {
  const r = await memory({ op: 'journal', limit: 40 });
  if (!r.ok || !r.data || !r.data.ok) { $('#journal').innerHTML = '<div class="err">Журнал недоступен: ' + esc((r.data && r.data.error) || r.error) + '</div>'; return; }
  const c = r.data.changes; c.forEach((x) => { if (x.action === 'correct') addCorpus(x.ref, x.new); }); $('#jInfo').textContent = c.length + ' ЗАПИСЕЙ';
  $('#journal').innerHTML = c.length ? '<table class="tbl"><thead><tr><th>Время</th><th>Кто</th><th>Действие</th><th>Запись</th><th>Было → стало</th><th></th></tr></thead><tbody>' + c.map((x) => '<tr><td>' + esc(when(x.ts)) + '</td><td>' + esc(x.actor) + '</td><td>' + esc(x.action) + '</td><td>' + esc(x.ref) + '</td><td>' + esc((x.old || '—').slice(0, 90)) + ' → ' + esc((x.new || '—').slice(0, 90)) + '</td><td>' + (x.action === 'delete' || x.action === 'correct' ? '<span class="seg"><button type="button" data-rev="' + x.id + '">Откатить</button></span>' : '') + '</td></tr>').join('') + '</tbody></table>' : '<div class="empty">Правок пока не было.</div>';
}
const refresh = () => Promise.all([stats(), core(), journal(), last ? search(last) : 0]);

$('#qForm').addEventListener('submit', (e) => { e.preventDefault(); search($('#q').value); });
$('#mRefresh').addEventListener('click', async () => { await refresh(); toast('Память обновлена'); });
$('#results').addEventListener('click', async (e) => {
  const b = e.target.closest('button[data-a]'); if (!b) return; const ref = b.closest('.hit').dataset.ref, h = hits.get(ref);
  if (b.dataset.a === 'confirm') { b.disabled = true; const d = await op({ op: 'confirm', id: ref }, 'Подтверждение'); b.disabled = false; if (d) { toast('Подтверждено: ' + ref); refresh(); } }
  else if (b.dataset.a === 'correct') { await ready; cRef = ref; $('#cRef').textContent = ref; $('#cText').value = h ? h.text : ''; $('#dlgC').show(); setTimeout(() => $('#cText').focus(), 250); }
  else { await ready; dRef = ref; $('#dRef').textContent = ref; $('#dText').textContent = h ? h.text : ''; $('#dlgD').show(); }
});
$('#cSave').addEventListener('click', async () => { const t = $('#cText').value.trim(); if (!t) { $('#cText').focus(); return; } const d = await op({ op: 'correct', id: cRef, text: t }, 'Исправление'); if (d) { $('#dlgC').hide(); toast('Исправлено: ' + cRef); refresh(); } });
$('#cCancel').addEventListener('click', () => $('#dlgC').hide());
$('#dOk').addEventListener('click', async () => { const d = await op({ op: 'delete', id: dRef }, 'Удаление'); if (d) { $('#dlgD').hide(); toast('Удалено: ' + dRef + '. Откат есть в журнале'); refresh(); } });
$('#dNo').addEventListener('click', () => $('#dlgD').hide());
$('#journal').addEventListener('click', async (e) => { const b = e.target.closest('button[data-rev]'); if (!b) return; b.disabled = true; const d = await op({ op: 'revert', change_id: +b.dataset.rev }, 'Откат'); b.disabled = false; if (d) { toast('Изменение откатено'); refresh(); } });
refresh();
