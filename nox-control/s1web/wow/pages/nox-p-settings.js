/* Настройки: планета фона, цвет неона, режимы космоса/интерфейса, параметры чата и голоса (общие с «Резонансом»: nox.wow.cfg, nox:planet). */
import { $, $$, esc, ls, call, download, toast } from './nox-api.js';
import { space } from './nox-nav.js';
import { PLANETS, byId } from './nox-wow-data.js';
import * as NN from './nox-notify.js';
const V = './vendor/', ACC = [['127,245,239', 'Циан'], ['255,180,84', 'Янтарь'], ['120,255,170', 'Мята'], ['170,150,255', 'Фиолет'], ['255,95,138', 'Малина'], ['110,170,255', 'Лазурь']];
const DEF = { proto: 'classic', enter: 'enter', speak: 'on', lang: 'auto', auto: 'off', dens: 'cozy', space: 'on', dust: 'on' };
const cfg = Object.assign({}, DEF, ls.json('nox.wow.cfg', {})); if (cfg.space === 'off') cfg.space = 'on';
const save = () => ls.set('nox.wow.cfg', JSON.stringify(cfg));
function sync() { $$('.opt').forEach((g) => $$('button', g).forEach((b) => b.setAttribute('aria-checked', String(b.dataset.v === cfg[g.dataset.opt])))); }
$$('.opt').forEach((g) => g.addEventListener('click', async (e) => {
  const b = e.target.closest('button[data-v]'); if (!b) return; const k = g.dataset.opt; cfg[k] = b.dataset.v; save(); sync();
  if (k === 'dens') document.body.classList.toggle('tight', cfg.dens === 'tight');
  if (k === 'space') { const s = await space; if (s) s.setLevel(cfg.space); }
  toast('Сохранено');
}));
document.body.classList.toggle('tight', cfg.dens === 'tight'); sync();

/* цвет */
const accent = () => ls.get('nox.ui.accent', ACC[0][0]);
function buildAcc() { $('#accent').innerHTML = ACC.map((a) => '<button type="button" role="radio" aria-label="' + a[1] + '" title="' + a[1] + '" data-c="' + a[0] + '" aria-checked="' + (a[0] === accent()) + '" style="color:rgb(' + a[0] + ')"><i style="background:rgb(' + a[0] + ')"></i></button>').join(''); }
$('#accent').addEventListener('click', (e) => { const b = e.target.closest('button[data-c]'); if (!b) return; ls.set('nox.ui.accent', b.dataset.c); document.documentElement.style.setProperty('--cy', b.dataset.c); buildAcc(); toast('Цвет неона: ' + b.title); });
buildAcc();

/* планеты */
let MF = null;
async function planets() {
  try { const r = await fetch(V + 'nox-planets/manifest.json', { cache: 'no-store' }); if (r.ok) MF = new Set((await r.json()).files || []); } catch (e) { /* без манифеста: градиенты */ }
  const cur = ls.get('nox:planet', 'earth');
  $('#planets').innerHTML = PLANETS.map((p) => { const pr = p.proc || { base: [.1, .12, .2], hi: [.3, .35, .5] }, rgb = (a) => a.map((x) => Math.round(x * 255)).join(','), has = p.tex && MF && p.tex.find((n) => MF.has(n)); return '<button type="button" role="radio" data-id="' + p.id + '" aria-checked="' + (p.id === cur) + '"><i class="pb" style="background-image:' + (has ? 'url(' + V + 'nox-planets/' + has + '),' : '') + 'radial-gradient(circle at 35% 30%,rgb(' + rgb(pr.hi) + '),rgb(' + rgb(pr.base) + '))"></i><span>' + esc(p.name) + '</span></button>'; }).join('');
}
$('#planets').addEventListener('click', async (e) => {
  const b = e.target.closest('button[data-id]'); if (!b) return; const id = b.dataset.id; ls.set('nox:planet', id); $$('#planets button').forEach((x) => x.setAttribute('aria-checked', String(x === b)));
  const s = await space; if (s) { await s.setPlanet(id); const st = s.state.texStatus[id]; $('#planetNote').textContent = id === 'none' ? '' : st ? (String(st).startsWith('photo') ? 'ТЕКСТУРА: ' + String(st).replace('photo:', '') + ' · SOLAR SYSTEM SCOPE, CC BY 4.0' : 'ТЕКСТУРА НЕ НАЙДЕНА, ПОКАЗАНА ПРОЦЕДУРНАЯ ПЛАНЕТА') : ''; }
  else { $('#planetNote').textContent = 'ФОН В ЗАПАСНОМ РЕЖИМЕ: ПЛАНЕТА ПРИМЕНИТСЯ ПОСЛЕ ПЕРЕЗАГРУЗКИ'; }
  toast('Планета: ' + byId(id).name);
});
planets();

/* голос: реальные health */
(async () => { const [a, b] = await Promise.all([call('/stt/health'), call('/tts/health')]); const f = (n, r) => n + ' ' + (r.ok && r.data ? (r.data.ready === false ? 'НЕ ГОТОВ' : 'ГОТОВ') : 'НЕ ЗАПУЩЕН (' + r.error + ')'); $('#voiceStat').textContent = f('STT', a) + ' · ' + f('TTS', b); })();

/* экспорт / импорт / сброс (только ключи nox.*, кроме задач) */
const keys = () => { const k = []; try { for (let i = 0; i < localStorage.length; i++) { const n = localStorage.key(i); if (/^nox[.:]/.test(n) && n !== 'nox.tasks.v1' && !/^nox\.(wow\.threads|wow\.cur|apiprobe)/.test(n)) k.push(n); } } catch (e) { /* нет хранилища */ } return k; };
$('#sExp').addEventListener('click', () => { const o = {}; keys().forEach((k) => (o[k] = ls.get(k))); download('nox-settings.json', JSON.stringify({ schema: 'nox-settings-v1', settings: o }, null, 2)); toast('Экспортировано ключей: ' + Object.keys(o).length); });
$('#sImp').addEventListener('click', () => $('#sFile').click());
$('#sFile').addEventListener('change', async (e) => { const f = e.target.files[0]; e.target.value = ''; if (!f) return; try { const j = JSON.parse(await f.text()); if (!j.settings || typeof j.settings !== 'object') throw new Error('нет блока settings'); let n = 0; Object.keys(j.settings).forEach((k) => { if (/^nox[.:]/.test(k) && typeof j.settings[k] === 'string') { ls.set(k, j.settings[k]); n++; } }); toast('Импортировано ключей: ' + n + '. Перезагрузка…'); setTimeout(() => location.reload(), 900); } catch (err) { toast('Файл не принят: ' + err.message, true); } });
$('#sReset').addEventListener('click', () => { if (!confirm('Сбросить планету, цвет, режимы чата и голоса к значениям по умолчанию? Диалоги и задачи не затрагиваются.')) return; keys().forEach((k) => { try { localStorage.removeItem(k); } catch (e) { /* пропуск */ } }); toast('Настройки сброшены. Перезагрузка…'); setTimeout(() => location.reload(), 900); });

/* уведомления */
function nui() {
  const s = NN.state(), on = NN.enabled();
  $('#nState').textContent = NN.STATE_RU[s]; $('#nState').className = 'tag ' + (s === 'granted' ? 'on' : s === 'default' ? 'warn' : 'bad');
  $('#nAsk').disabled = s !== 'default'; $('#nTest').disabled = s !== 'granted'; $('#nToggle').disabled = s !== 'granted';
  $('#nToggle').setAttribute('aria-pressed', String(on)); $('#nToggle span').textContent = 'Напоминания по срокам: ' + (on ? 'вкл' : 'выкл');
  $('#nNote').textContent = s === 'denied' ? 'Браузер запретил уведомления для этого сайта: напоминаний и сигнала «NOX закончил ответ» не будет. Разрешите их в настройках сайта (значок замка в адресной строке) и обновите страницу.' : s === 'unsupported' ? 'Этот браузер не поддерживает Notification API.' : (window.isSecureContext ? '' : 'Страница открыта не по HTTPS и не с localhost: service worker и уведомления недоступны. ') + 'Уведомления приходят, пока вкладка или приложение открыты (в том числе в фоне): напоминание по сроку задачи (с 09:00 дня срока, для просроченных раз в день), начало события в календаре и «NOX закончил ответ», когда вкладка скрыта. Закрытый браузер уведомлений не получит: для этого нужен push-сервер.';
}
$('#nAsk').addEventListener('click', async () => { const r = await NN.request(); nui(); toast(r === 'granted' ? 'Уведомления разрешены' : r === 'denied' ? 'Разрешение отклонено: уведомлений не будет' : 'Разрешение не выдано', r !== 'granted'); });
$('#nTest').addEventListener('click', async () => { const ok = await NN.show('NOX', 'Тестовое уведомление: всё работает', 'nox-test', 'settings.html'); toast(ok ? 'Уведомление отправлено' : 'Не удалось показать уведомление', !ok); });
$('#nToggle').addEventListener('click', () => { NN.setEnabled(!NN.enabled()); nui(); toast('Напоминания ' + (NN.enabled() ? 'включены' : 'выключены')); });
nui();
