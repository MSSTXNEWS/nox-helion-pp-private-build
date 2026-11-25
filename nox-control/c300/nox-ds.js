/* NOX · дизайн-система: помощники empty/skeleton/бейдж «недоступно», тема ECharts NOX. Не трогает данные страниц. */
(() => {
  if (window.NOXds) return;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const empty = (el, o = {}) => { el.innerHTML = '<div class="ds-empty" role="status"><sl-icon library="tabler" name="' + esc(o.icon || 'inbox') + '"></sl-icon><b>' + esc(o.title || 'Пока пусто') + '</b><p>' + esc(o.text || '') + '</p>' + (o.unavailable ? '<span class="ds-badge-off">недоступно</span>' : '') + '</div>'; return el; };
  const unavailable = (el, reason) => empty(el, { icon: 'plug-off', title: 'Сервис недоступен', text: reason || 'Источник данных не отвечает. Попробуйте позже.', unavailable: true });
  const skeleton = (el, n = 3) => { el.innerHTML = '<div aria-busy="true" aria-label="Загрузка">' + Array.from({ length: n }, (_, i) => '<div class="ds-skel ds-skel-line" style="width:' + (92 - i * 14) + '%"></div>').join('') + '</div>'; return el; };
  const badge = () => '<span class="ds-badge-off">недоступно</span>';
  const TH = { color: ['#e9b465', '#6fd4cf', '#b99bff', '#ff8a5c', '#7fd49a', '#ff7aa8'], backgroundColor: 'transparent', textStyle: { color: '#efe6df', fontFamily: 'inherit', fontSize: 12 },
    title: { textStyle: { color: '#efe6df', fontSize: 16, fontWeight: 400 } }, legend: { textStyle: { color: 'rgba(240,232,226,.75)', fontSize: 12 } },
    tooltip: { backgroundColor: 'rgba(24,18,18,.92)', borderColor: 'rgba(255,255,255,.14)', textStyle: { color: '#efe6df', fontSize: 12 } },
    categoryAxis: { axisLine: { lineStyle: { color: 'rgba(255,255,255,.2)' } }, axisLabel: { color: 'rgba(240,232,226,.7)', fontSize: 12 }, splitLine: { show: false } },
    valueAxis: { axisLine: { show: false }, axisLabel: { color: 'rgba(240,232,226,.7)', fontSize: 12 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,.08)' } } },
    line: { smooth: true, lineStyle: { width: 2 } }, bar: { itemStyle: { borderRadius: [6, 6, 0, 0] } } };
  const reg = () => { if (window.echarts && echarts.registerTheme) { echarts.registerTheme('nox', TH); return true; } return false; };
  window.NOXds = { empty, unavailable, skeleton, badge, echartsTheme: TH, registerEcharts: reg };
  if (!reg()) { let n = 0; const t = setInterval(() => { if (reg() || ++n > 40) clearInterval(t); }, 500); }
  /* кнопка с loading на время промиса: NOXds.busy(btn, promise) */
  window.NOXds.busy = (btn, pr) => { btn.setAttribute('loading', ''); btn.setAttribute('aria-busy', 'true'); return Promise.resolve(pr).finally(() => { btn.removeAttribute('loading'); btn.removeAttribute('aria-busy'); }); };
})();
