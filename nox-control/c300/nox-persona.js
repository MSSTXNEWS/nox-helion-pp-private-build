/* NOX · ползунки личности (Shoelace sl-range) -> команда persona.set (реестр, /workspace/nox/state/persona.json) */
(() => {
  if (window.__nxPersona) return; window.__nxPersona = 1;
  const K = [['curiosity', 'Любопытство', 'сколько вопросов и догадок'], ['humor', 'Юмор', 'шутки и лёгкость'], ['strictness', 'Строгость', 'прямота и жёсткость оценок'], ['initiative', 'Инициатива', 'сам предлагает и начинает'], ['empathy', 'Эмпатия', 'тепло и внимание к состоянию'], ['brevity', 'Краткость', 'короткие ответы без воды']];
  const parse = (r) => { try { if (r && typeof r === 'object' && 'result' in r) r = r.result; if (typeof r === 'string') r = JSON.parse(r); return r; } catch (e) { return null; } };
  const run = (n, p) => (window.NOXcmd ? window.NOXcmd(n, p || {}) : Promise.reject(new Error('NOXcmd нет')));
  const build = async (host) => {
    host.innerHTML = '<div class="nxp-h">Ползунки личности</div><div class="nxp-g">' + K.map(([k, t, d]) => '<label class="nxp-r"><span><b>' + t + '</b><small>' + d + '</small></span><sl-range data-k="' + k + '" min="0" max="100" step="5" value="50" tooltip="none"></sl-range><output data-o="' + k + '">50</output></label>').join('') + '</div><div class="nxp-f"><sl-button size="small" data-reset>Сбросить на 50</sl-button><span class="nxp-s" aria-live="polite"></span></div>';
    const st = host.querySelector('.nxp-s'); let core = false, tm = 0;
    const msg = (ok) => { st.textContent = (ok ? 'Сохранено в persona.json. ' : '') + (core ? 'Ядро читает этот файл.' : 'Ядро этот файл пока не читает: будет применено после подключения ядра.'); };
    try { const j = parse(await run('persona.get')); if (j) { core = !!j.core_reads; K.forEach(([k]) => { const e = host.querySelector('[data-k="' + k + '"]'); e.value = j.values[k]; host.querySelector('[data-o="' + k + '"]').textContent = j.values[k]; }); } } catch (e) { st.textContent = 'Не удалось прочитать значения: ' + e.message; return; }
    msg(false);
    const save = () => { clearTimeout(tm); tm = setTimeout(async () => { const p = {}; K.forEach(([k]) => { p[k] = Number(host.querySelector('[data-k="' + k + '"]').value); }); try { const j = parse(await run('persona.set', p)); if (j) core = !!j.core_reads; msg(true); } catch (e) { st.textContent = 'Не сохранено: ' + e.message; } }, 400); };
    host.addEventListener('sl-change', (e) => { const k = e.target.dataset && e.target.dataset.k; if (!k) return; host.querySelector('[data-o="' + k + '"]').textContent = e.target.value; save(); });
    host.addEventListener('sl-input', (e) => { const k = e.target.dataset && e.target.dataset.k; if (k) host.querySelector('[data-o="' + k + '"]').textContent = e.target.value; });
    host.querySelector('[data-reset]').addEventListener('click', () => { K.forEach(([k]) => { host.querySelector('[data-k="' + k + '"]').value = 50; host.querySelector('[data-o="' + k + '"]').textContent = 50; }); save(); });
  };
  const seen = new WeakSet();
  const scan = () => { const h = document.getElementById('nxsPersona'); if (h && !seen.has(h)) { seen.add(h); build(h); } };
  new MutationObserver(scan).observe(document.documentElement, { childList: true, subtree: true }); scan();
})();
