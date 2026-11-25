/* S4 · Диспетчер/Система: панели в раскладке Grafana (stat + график ECharts) по живым данным /api/nox-live и /api/pc-metrics. История копится в sessionStorage; пока точек нет - честная подпись. */
(function () {
  const wrap = document.querySelector('.wrap'); if (!wrap || !window.echarts) return;
  const flat = (o, p, out) => { out = out || {}; if (o && typeof o === 'object') for (const k in o) { const v = o[k], kk = p ? p + '.' + k : k; if (typeof v === 'number' && isFinite(v)) out[kk] = v; else if (v && typeof v === 'object' && !Array.isArray(v)) flat(v, kk, out); } return out; };
  const PAN = [['gpu.util_pct', 'GPU загрузка', '%', 100], ['gpu.vram_pct', 'VRAM', '%', 100], ['gpu.temp_c', 'GPU температура', '°C'], ['gpu.power_w', 'GPU мощность', 'Вт'], ['disk.used_pct', 'Диск занят', '%', 100], ['disk.free_gb', 'Диск свободно', 'ГБ']];
  const sec = document.createElement('section'); sec.className = 'card s4gf'; sec.innerHTML = '<h2>Панели · живые данные <span class="r mono" id="s4gT">…</span></h2><div class="s4gg" id="s4gg"></div><p class="muted" id="s4gn" style="font-size:12px;margin:8px 0 0"></p>';
  wrap.appendChild(sec);
  let H = {}; try { H = JSON.parse(sessionStorage.getItem('s4h') || '{}'); } catch (e) { /* */ }
  const charts = {}, grid = sec.querySelector('#s4gg'), mk = (k, t, u) => { const d = document.createElement('div'); d.className = 's4pn'; d.innerHTML = '<div class="s4ph"><span>' + t + '</span><b class="mono" data-v>—</b></div><div class="s4pc" data-c></div>'; grid.appendChild(d); const c = echarts.init(d.querySelector('[data-c]'), null, { renderer: 'canvas' }); charts[k] = { c, d, t, u }; };
  function draw(k, max) {
    const h = H[k] || [], x = charts[k]; if (!x) return; x.d.querySelector('[data-v]').textContent = h.length ? h[h.length - 1][1] + ' ' + x.u : '—';
    x.c.setOption({ animation: false, grid: { left: 36, right: 8, top: 8, bottom: 20 }, tooltip: { trigger: 'axis', backgroundColor: 'rgba(20,16,16,.9)', borderColor: '#5a3a34', textStyle: { color: '#efe6df', fontSize: 12 } },
      xAxis: { type: 'time', axisLabel: { color: '#9a8f88', fontSize: 10 }, axisLine: { lineStyle: { color: '#3a302d' } }, splitLine: { show: false } },
      yAxis: { type: 'value', max: max || null, scale: !max, axisLabel: { color: '#9a8f88', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(255,235,220,.07)' } } },
      series: [{ type: 'line', data: h, showSymbol: false, smooth: true, lineStyle: { color: '#d6583f', width: 1.6 }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(214,88,63,.35)' }, { offset: 1, color: 'rgba(214,88,63,0)' }]) } }] });
  }
  async function tick() {
    let f = {}; try { f = flat(await (await fetch('/api/nox-live', { cache: 'no-store' })).json()); } catch (e) { /* */ }
    try { const pm = flat(await (await fetch('/api/pc-metrics', { cache: 'no-store' })).json(), 'pc'); Object.assign(f, pm); } catch (e) { /* */ }
    const now = Date.now(); let n = 0;
    const list = PAN.filter((p) => p[0] in f).concat(Object.keys(f).filter((k) => /^pc\..*(cpu|mem|load|ram)/i.test(k)).slice(0, 4).map((k) => [k, k.replace('pc.', '').toUpperCase(), '']));
    list.forEach(([k, t, u, mx]) => { if (!charts[k]) mk(k, t, u); (H[k] = H[k] || []).push([now, Math.round(f[k] * 10) / 10]); if (H[k].length > 240) H[k].shift(); draw(k, mx); n++; });
    sessionStorage.setItem('s4h', JSON.stringify(H));
    sec.querySelector('#s4gT').textContent = n ? n + ' панелей · обновление 5 с' : 'нет данных';
    sec.querySelector('#s4gn').textContent = n ? 'Серия копируется в этой вкладке: чем дольше открыта страница, тем длиннее график.' : 'Источники /api/nox-live и /api/pc-metrics не вернули числовых полей.';
  }
  tick(); setInterval(tick, 5000); addEventListener('resize', () => Object.values(charts).forEach((x) => x.c.resize()));
})();
