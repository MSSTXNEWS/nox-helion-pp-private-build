/* NOX · пульт (расширение, канон не меняет): STOP, глубина ответа, голос, мини-датчики.
   Команды идут через window.NOXcmd (шина, исполнитель C), если она подключена. Нет команды или эндпоинта — кнопка честно показывает «недоступно». */
(() => {
  if (window.__noxPult) return; window.__noxPult = 1;
  const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = './nox-pult.css'; document.head.appendChild(css);
  const LS = (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : v; } catch (e) { return d; } };
  const SET = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* хранилище недоступно */ } };

  /* глубина -> nox_mode в запросах к чату (только если в теле запроса его ещё нет) */
  const origFetch = window.fetch;
  window.fetch = function (input, init) {
    try {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      const m = LS('nox.depth', 'auto');
      if (m !== 'auto' && init && init.method === 'POST' && typeof init.body === 'string' && /chat\/completions|\/api\/chat/.test(url)) {
        const b = JSON.parse(init.body);
        if (b && typeof b === 'object' && !b.nox_mode) init = Object.assign({}, init, { body: JSON.stringify(Object.assign(b, { nox_mode: m })) });
      }
    } catch (e) { /* тело не JSON: отправляем как есть */ }
    return origFetch.call(this, input, init);
  };

  const DEPTH = [['fast', 'Быстро'], ['auto', 'Авто'], ['deep', 'Глубоко']];
  const el = document.createElement('div');
  el.id = 'nxpult'; el.setAttribute('aria-label', 'Пульт NOX');
  el.innerHTML = '<button type="button" class="nxpu-tog" aria-expanded="false">ПУЛЬТ'
    + ' <i class="nxpu-d" data-k="core"></i><i class="nxpu-d" data-k="gpu"></i><i class="nxpu-d" data-k="ev"></i></button>'
    + '<div class="nxpu-pan" role="group">'
    + '<div class="nxpu-row"><button type="button" class="nxpu-stop" data-act="stop">STOP</button>'
    + '<span class="nxpu-seg" role="radiogroup" aria-label="Глубина ответа">' + DEPTH.map(([v, t]) => '<button type="button" role="radio" data-depth="' + v + '">' + t + '</button>').join('') + '</span></div>'
    + '<div class="nxpu-row"><button type="button" data-act="voice">голос</button>'
    + '<button type="button" data-act="sleep" disabled title="недоступно: на сервере нет эндпоинта сна">сон</button>'
    + '<button type="button" data-act="prio" disabled title="недоступно: на сервере нет эндпоинта паузы обучения">приоритет чата</button></div>'
    + '<div class="nxpu-sens"><span data-k="core">ядро: —</span><span data-k="gpu">GPU: —</span><span data-k="ev">события: —</span></div>'
    + '<pre class="nxpu-det" hidden></pre>'
    + '<div class="nxpu-st" aria-live="polite"></div></div>';
  const mount = () => document.body && document.body.appendChild(el);
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount);

  const st = (msg, state) => { const s = el.querySelector('.nxpu-st'); s.textContent = msg; s.dataset.state = state || ''; if (state === 'ok') setTimeout(() => { if (s.textContent === msg) { s.textContent = ''; s.dataset.state = ''; } }, 2500); };
  const paintDepth = () => el.querySelectorAll('[data-depth]').forEach((b) => b.setAttribute('aria-checked', String(b.dataset.depth === LS('nox.depth', 'auto'))));
  const paintVoice = () => { const b = el.querySelector('[data-act="voice"]'), on = LS('nox.pult.voice', 'on') === 'on'; b.textContent = 'голос: ' + (on ? 'вкл' : 'выкл'); b.setAttribute('aria-pressed', String(on)); };
  paintDepth(); paintVoice();

  el.querySelector('.nxpu-tog').addEventListener('click', () => { const p = el.querySelector('.nxpu-pan'), on = p.classList.toggle('on'); el.querySelector('.nxpu-tog').setAttribute('aria-expanded', String(on)); });
  el.querySelectorAll('[data-depth]').forEach((b) => b.addEventListener('click', () => { SET('nox.depth', b.dataset.depth); paintDepth(); st('глубина: ' + b.textContent + ' (уйдёт с ближайшим запросом)', 'ok'); }));
  el.querySelector('[data-act="voice"]').addEventListener('click', () => { SET('nox.pult.voice', LS('nox.pult.voice', 'on') === 'on' ? 'off' : 'on'); paintVoice(); st('голос сохранён; озвучка ответов подключается отдельно', 'ok'); });
  el.querySelector('[data-act="stop"]').addEventListener('click', async () => {
    if (!window.NOXcmd) return st('недоступно: шина команд не подключена', 'bad');
    st('STOP: идёт…', 'busy');
    const r = await window.NOXcmd('stop', {});
    st(r && r.ok ? 'STOP: готово' : 'STOP: ошибка' + (r && r.error ? ' (' + r.error + ')' : ''), r && r.ok ? 'ok' : 'bad');
  });

  /* датчики: ядро (раз в 15 с), GPU и события из live.json (раз в 15 с) */
  const dot = (k, state, text) => { const d = el.querySelector('.nxpu-d[data-k="' + k + '"]'), t = el.querySelector('.nxpu-sens [data-k="' + k + '"]'); if (d) d.dataset.state = state; if (t) t.textContent = text; };
  let live = null;
  const readLive = async () => {
    try {
      const r = await fetch('./data/live.json', { cache: 'no-store' }); live = await r.json();
      const g = live.gpu || {};
      const gp = g.vram_pct != null ? 'GPU: ' + g.gpu_util_pct + '% · VRAM ' + g.vram_pct + '%' : 'GPU: нет данных';
      dot('gpu', g.vram_pct != null ? (g.vram_pct > 92 ? 'warn' : 'ok') : 'bad', gp);
      const ev = (live.ops_tail || []).length;
      dot('ev', ev ? 'ok' : 'warn', 'события: ' + ev);
    } catch (e) { dot('gpu', 'bad', 'GPU: нет данных'); dot('ev', 'bad', 'события: нет данных'); }
  };
  const probeCore = async () => {
    const t0 = performance.now();
    try { const r = await fetch('./glm/v1/nox/stats', { cache: 'no-store' }); const ms = Math.round(performance.now() - t0); dot('core', r.ok ? (ms > 1500 ? 'warn' : 'ok') : 'warn', 'ядро: ' + ms + ' мс'); }
    catch (e) { dot('core', 'bad', 'ядро: нет связи'); }
  };
  const tick = () => { probeCore(); readLive(); };
  tick(); setInterval(tick, 15000);
  el.querySelectorAll('.nxpu-sens [data-k]').forEach((s) => s.addEventListener('click', () => {
    const det = el.querySelector('.nxpu-det'); det.hidden = !det.hidden;
    det.textContent = live ? JSON.stringify({ ports: live.ports, gpu: live.gpu, round: live.round, ops_tail: (live.ops_tail || []).slice(-3) }, null, 1) : 'live.json не загружен';
  }));
  window.NOXpult = { depth: () => LS('nox.depth', 'auto'), voice: () => LS('nox.pult.voice', 'on') === 'on' };
})();
