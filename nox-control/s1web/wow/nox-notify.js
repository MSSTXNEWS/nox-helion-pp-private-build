/* NOX · уведомления: Notification API + service worker (sw.js в корне веба).
   Разрешение запрашивается только по клику (NoxNotify.request). Напоминания: срок задачи (с 09:00 дня срока и далее, если просрочена), начало события;
   «NOX закончил ответ» - когда вкладка скрыта. Без push-сервера закрытая вкладка/браузер уведомлений не получит: это ограничение честно показывается в Настройках. */
const LS = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* нет хранилища */ } } };
const pad = (n) => String(n).padStart(2, '0'), ymd = (d) => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
let reg = null;
async function sw() {
  if (reg) return reg;
  if (!('serviceWorker' in navigator)) throw new Error('service worker не поддерживается');
  if (!window.isSecureContext) throw new Error('нужен HTTPS или localhost');
  reg = await navigator.serviceWorker.register('./sw.js'); await navigator.serviceWorker.ready; return reg;
}
export const state = () => (!('Notification' in window) ? 'unsupported' : Notification.permission); /* unsupported | default | granted | denied */
export const enabled = () => LS.get('nox.notify.on') !== '0';
export const setEnabled = (v) => LS.set('nox.notify.on', v ? '1' : '0');
export const STATE_RU = { unsupported: 'БРАУЗЕР НЕ ПОДДЕРЖИВАЕТ УВЕДОМЛЕНИЯ', default: 'РАЗРЕШЕНИЕ НЕ ЗАПРОШЕНО', granted: 'РАЗРЕШЕНО', denied: 'ОТКАЗАНО: ВКЛЮЧИТЕ В НАСТРОЙКАХ САЙТА БРАУЗЕРА' };
export async function request() {
  if (state() === 'unsupported') return 'unsupported';
  let r = Notification.permission; if (r === 'default') { try { r = await Notification.requestPermission(); } catch (e) { r = Notification.permission; } }
  if (r === 'granted') { try { await sw(); } catch (e) { /* уведомления пойдут без SW */ } arm(); }
  return r;
}
export async function show(title, body, tag, url) {
  if (state() !== 'granted') return false;
  const o = { body, tag, icon: './favicon.svg', badge: './favicon.svg', data: { url: url || 'chat.html' } };
  try { const r = await sw(); await r.showNotification(title, o); return true; } catch (e) { /* запасной путь без SW */ }
  try { const n = new Notification(title, o); n.onclick = () => { focus(); location.href = o.data.url; n.close(); }; return true; } catch (e) { return false; }
}
function focus() { try { window.focus(); } catch (e) { /* нет */ } }
/* напоминания по задачам и событиям из localStorage 'nox.tasks.v1' */
export async function checkReminders() {
  if (state() !== 'granted' || !enabled()) return 0;
  let tasks = []; try { tasks = (JSON.parse(LS.get('nox.tasks.v1') || '{}').tasks) || []; } catch (e) { return 0; }
  const now = new Date(), today = ymd(now); let n = 0, sent = {}; try { sent = JSON.parse(LS.get('nox.notified') || '{}'); } catch (e) { sent = {}; }
  for (const t of tasks) {
    if (!t.due || t.col === 'done') continue; let key = '', msg = '';
    if (t.kind === 'event') { const st = new Date(t.due + 'T' + (t.time || '09:00') + ':00'), dt = now - st; if (dt >= 0 && dt < 12 * 3600e3) { key = t.id + '|' + t.due + '|' + (t.time || ''); msg = 'Событие началось: ' + (t.time || t.due); } }
    else if (t.due <= today && now.getHours() >= 9) { key = t.id + '|' + t.due + '|' + today; msg = t.due < today ? 'Срок прошёл ' + t.due : 'Срок сегодня'; }
    if (!key || sent[key]) continue;
    if (await show((t.kind === 'event' ? 'Событие: ' : 'Задача: ') + t.title, msg + (t.owner ? ' · ' + t.owner : '') + (t.project ? ' · ' + t.project : ''), 'task-' + t.id, 'projects.html')) { sent[key] = Date.now(); n++; }
  }
  const keys = Object.keys(sent); if (keys.length > 300) keys.sort((a, b) => sent[a] - sent[b]).slice(0, keys.length - 300).forEach((k) => delete sent[k]);
  LS.set('nox.notified', JSON.stringify(sent)); return n;
}
document.addEventListener('nox:reply-done', (e) => { if (document.hidden && enabled()) show('NOX закончил ответ', (e.detail && e.detail.text) || 'Ответ готов', 'nox-reply', 'chat.html'); });
let armed = false;
function arm() { if (armed || state() !== 'granted') return; armed = true; sw().catch(() => {}); setTimeout(checkReminders, 2500); setInterval(checkReminders, 60000); }
arm();
window.NoxNotify = { state, request, show, checkReminders, enabled, setEnabled };
