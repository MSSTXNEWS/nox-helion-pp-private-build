/* Интеграции Диска: реальный список библиотек по группам со статусом «подключено / лежит / нет» (проверка файлов и поиск использования в исходниках). */
import { $, esc } from './nox-api.js';
import './nox-nav.js';
import { scan, ABSENT } from './nox-registry.js';
const ST = { on: 'подключено', idle: 'лежит', no: 'нет' };
async function run() {
  $('#sumT').textContent = 'проверка…'; $('#groups').innerHTML = '';
  const { libs, assets, srcN } = await scan(), all = libs.concat(assets);
  const n = (k) => all.filter((x) => x.st === k).length;
  $('#sumT').textContent = 'ПОДКЛЮЧЕНО ' + n('on') + ' · ЛЕЖИТ ' + n('idle') + ' · НЕТ ' + n('no') + ' · ИСХОДНИКОВ ПРОВЕРЕНО ' + srcN;
  const gs = {}; libs.forEach((x) => { (gs[x.g] = gs[x.g] || []).push(x); }); gs['Ассеты (текстуры, каталоги, HDRI)'] = assets;
  $('#groups').innerHTML = Object.keys(gs).map((g) => { const L = gs[g], on = L.filter((x) => x.st === 'on').length;
    return '<details class="card fold c6"' + (on === L.length || g.startsWith('Ассеты') ? '' : '') + ' open><summary><span>' + esc(g) + '</span><span class="r mono">' + on + ' / ' + L.length + ' подключено</span></summary><div class="scroll-x"><table class="tbl"><tbody>'
      + L.map((x) => '<tr><td><b>' + esc(x.n) + '</b>' + (x.ver ? ' <span class="muted mono">' + esc(x.ver) + '</span>' : '') + '<div class="muted" style="font-size:12px">' + esc(x.role || '') + (x.st === 'on' ? ' · ' + esc(x.used.slice(0, 3).join(', ')) : '') + '</div></td><td class="nw"><span class="pill ' + x.st + '">' + ST[x.st] + '</span></td></tr>').join('') + '</tbody></table></div></details>'; }).join('');
  $('#absN').textContent = ABSENT.length + ' ПОЗИЦИЙ';
  $('#absBox').innerHTML = '<p class="muted" style="font-size:13px">Этих библиотек в доставленной сборке нет, и ни одна страница их не использует: ' + esc(ABSENT.join(', ')) + '. Пока нет реальной функции, которой они нужны, они не добавлялись.</p>';
}
$('#rescan').addEventListener('click', run); run();
