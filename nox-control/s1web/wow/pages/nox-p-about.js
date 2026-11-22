/* О сборке и лицензии: ассеты, шрифты и библиотеки со ссылками на тексты лицензий; версии берутся из package.json в vendor. */
import { $, esc } from './nox-api.js';
import './nox-nav.js';
import { scan, FONTS } from './nox-registry.js';
const a = (u, t) => '<a href="' + esc(u) + '" target="_blank" rel="noopener noreferrer">' + esc(t) + '</a>';
(async () => {
  const { libs, assets } = await scan();
  $('#assT').innerHTML = '<thead><tr><th>Ассет</th><th>Автор / источник</th><th>Лицензия</th><th>В сборке</th></tr></thead><tbody>' + assets.map((x) => '<tr><td><b>' + esc(x.n) + '</b><div class="muted" style="font-size:12px">' + esc(x.role) + '</div></td><td>' + a(x.url, x.by) + '</td><td class="nw">' + a(x.licUrl, x.lic) + '</td><td class="nw"><span class="pill ' + x.st + '">' + (x.have ? (x.st === 'on' ? 'используется' : 'лежит') : 'нет файла') + '</span></td></tr>').join('') + '</tbody>';
  $('#assN').textContent = assets.filter((x) => x.have).length + ' / ' + assets.length + ' НА МЕСТЕ';
  $('#fontT').innerHTML = '<thead><tr><th>Шрифт</th><th>Лицензия</th><th>Сайт</th></tr></thead><tbody>' + FONTS.map((f) => '<tr><td><b>' + esc(f.n) + '</b></td><td>' + a(f.licUrl, f.lic) + '</td><td>' + a(f.url, f.url.replace(/^https?:\/\//, '')) + '</td></tr>').join('') + '</tbody>';
  $('#libT').innerHTML = '<thead><tr><th>Библиотека</th><th>Версия</th><th>Лицензия</th><th>Применение</th></tr></thead><tbody>' + libs.map((x) => '<tr><td><b>' + esc(x.n) + '</b></td><td class="mono nw">' + esc(x.ver || '—') + '</td><td class="nw">' + a(x.licUrl, x.lic) + '</td><td>' + esc(x.role) + '</td></tr>').join('') + '</tbody>';
  $('#libN').textContent = libs.length + ' ПОЗИЦИЙ';
})();
