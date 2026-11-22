/* Кинозал: локальное видео/аудио в плеере Plyr, субтитры .vtt/.srt, запоминание позиции. Файл не загружается на сервер (blob: URL в браузере). */
import { $, esc, ls, toast, pad } from './nox-api.js';
import './nox-nav.js';
const KEY = 'nox.cinema.pos', vid = $('#vid'); let player = null, fid = '', urls = [];
const pos = () => ls.json(KEY, {}); const savePos = (o) => ls.setJson(KEY, o);
const fmt = (s) => { s = Math.floor(s || 0); return (s >= 3600 ? Math.floor(s / 3600) + ':' : '') + pad(Math.floor(s / 60) % 60) + ':' + pad(s % 60); };
function recent() { const o = pos(), k = Object.keys(o).sort((a, b) => o[b].t - o[a].t); $('#recN').textContent = k.length ? k.length + ' ФАЙЛ.' : 'ПУСТО'; $('#recent').innerHTML = k.length ? k.slice(0, 20).map((x) => '<li><span class="mono">' + esc(fmt(o[x].p)) + ' / ' + esc(fmt(o[x].d)) + '</span> ' + esc(o[x].name) + '</li>').join('') : '<li class="muted">Пока ничего не смотрели.</li>'; }
function mkPlayer() { if (player || !window.Plyr) return; player = new window.Plyr(vid, { iconUrl: './vendor/nox-lib/plyr/plyr.svg', blankVideo: '', controls: ['play-large', 'play', 'progress', 'current-time', 'duration', 'mute', 'volume', 'captions', 'settings', 'pip', 'fullscreen'], settings: ['captions', 'speed'], i18n: { play: 'Пуск', pause: 'Пауза', mute: 'Без звука', unmute: 'Со звуком', captions: 'Субтитры', settings: 'Настройки', speed: 'Скорость', normal: 'Обычная', disabled: 'Выкл', enabled: 'Вкл', enterFullscreen: 'На весь экран', exitFullscreen: 'Выйти из полноэкранного режима', restart: 'Сначала', rewind: 'Назад {seektime} с', fastForward: 'Вперёд {seektime} с', currentTime: 'Сейчас', duration: 'Длительность' }, keyboard: { focused: true, global: false }, tooltips: { controls: true, seek: true } }); }
function srt2vtt(t) { return 'WEBVTT\n\n' + t.replace(/\r/g, '').replace(/(\d+:\d\d:\d\d),(\d{3})/g, '$1.$2'); }
function openFile(f) {
  if (!f) return; if (!/^(video|audio)\//.test(f.type) && !/\.(mp4|m4v|webm|mkv|mov|mp3|m4a|ogg|opus|wav|flac)$/i.test(f.name)) { toast('Это не видео и не аудио: ' + f.name, true); return; }
  urls.forEach((u) => URL.revokeObjectURL(u)); urls = []; const u = URL.createObjectURL(f); urls.push(u); fid = f.name + '|' + f.size;
  $('#drop').hidden = true; vid.hidden = false; vid.querySelectorAll('track').forEach((t) => t.remove()); vid.src = u; vid.load(); mkPlayer();
  $('#info').textContent = f.name + ' · ' + (f.size / 1048576).toFixed(1) + ' МБ · файл остаётся в браузере';
  const saved = pos()[fid]; vid.addEventListener('loadedmetadata', function once() { vid.removeEventListener('loadedmetadata', once); if (saved && saved.p > 5 && saved.p < vid.duration - 5) { vid.currentTime = saved.p; toast('Продолжаю с ' + fmt(saved.p)); } });
}
let last = 0; vid.addEventListener('timeupdate', () => { if (!fid || Date.now() - last < 4000) return; last = Date.now(); const o = pos(); o[fid] = { name: fid.split('|')[0], p: vid.currentTime, d: vid.duration || 0, t: Date.now() }; savePos(o); });
vid.addEventListener('pause', () => { last = 0; vid.dispatchEvent(new Event('timeupdate')); recent(); });
vid.addEventListener('error', () => { toast('Браузер не смог воспроизвести этот файл (кодек или контейнер не поддерживается)', true); });
$('#pickV').addEventListener('click', () => $('#fV').click()); $('#fV').addEventListener('change', (e) => { openFile(e.target.files[0]); e.target.value = ''; });
$('#drop').addEventListener('click', () => $('#fV').click());
['dragover', 'drop'].forEach((ev) => $('#stage').addEventListener(ev, (e) => { e.preventDefault(); if (ev === 'drop') openFile(e.dataTransfer.files[0]); }));
$('#pickS').addEventListener('click', () => { if (vid.hidden) { toast('Сначала откройте видео', true); return; } $('#fS').click(); });
$('#fS').addEventListener('change', async (e) => { const f = e.target.files[0]; e.target.value = ''; if (!f) return; try { let t = await f.text(); if (/\.srt$/i.test(f.name) || !/^WEBVTT/.test(t.trim())) t = srt2vtt(t); const u = URL.createObjectURL(new Blob([t], { type: 'text/vtt' })); urls.push(u); const tr = document.createElement('track'); tr.kind = 'captions'; tr.label = f.name.replace(/\.\w+$/, ''); tr.srclang = 'ru'; tr.src = u; tr.default = true; vid.appendChild(tr); if (player) { player.captions.active = true; } toast('Субтитры подключены: ' + f.name); } catch (err) { toast('Субтитры не приняты: ' + err.message, true); } });
$('#clearP').addEventListener('click', () => { savePos({}); recent(); toast('Позиции забыты'); });
if (!window.Plyr) $('#dropT').textContent = 'Plyr не загрузился (vendor/nox-lib/plyr): будет обычный проигрыватель браузера. Перетащите файл сюда.';
recent();
