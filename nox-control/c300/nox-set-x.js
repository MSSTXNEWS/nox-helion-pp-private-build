/* NOX · настройки: статус-бейджи разделов (Shoelace sl-badge), глубина ответа на sl-radio-group, микроанимации sl-switch (GSAP) */
(() => {
  if (window.__nxSetX) return; window.__nxSetX = 1;
  const J = (u) => fetch(u, { cache: 'no-cache' }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const put = (side, tab, variant, text) => { const b = side.querySelector('[role=tab][data-tab="' + tab + '"]'); if (!b) return; let s = b.querySelector('sl-badge.nxm-st'); if (!s) { s = document.createElement('sl-badge'); s.className = 'nxm-st'; s.pill = true; b.appendChild(s); } s.variant = variant; s.textContent = text; s.title = text; };
  const badges = async (side) => {
    const [hl, st, ag, reg] = await Promise.all([J('/api/chat/health'), J('/glm/v1/nox/stats'), J('/api/nox/agents'), J('qa/registry.json')]);
    const h = st && st.health;
    put(side, 'personality', h ? (h.conscience === 'enforce' ? 'success' : 'warning') : 'danger', h ? (h.conscience === 'enforce' ? 'совесть' : String(h.conscience || '—')) : 'нет');
    put(side, 'models', hl && hl.core && hl.core.up ? 'success' : 'danger', hl && hl.core && hl.core.up ? 'в сети' : 'нет');
    const run = ag && ag.agents ? Object.values(ag.agents).filter((a) => a.status === 'RUNNING').length : null;
    put(side, 'autonomy', run == null ? 'danger' : (run ? 'success' : 'neutral'), run == null ? 'нет' : String(run));
    const nc = reg && reg.commands ? Object.values(reg.commands).filter((c) => c.confirm).length : null;
    put(side, 'safety', nc == null ? 'danger' : 'primary', nc == null ? 'нет' : nc + ' с подтв.');
  };
  const depth = () => {
    const old = document.getElementById('nxsDepth'); if (!old || old.dataset.x) return !!old;
    const cur = localStorage.getItem('nox.depth') || 'auto'; const g = document.createElement('sl-radio-group'); g.id = 'nxsDepth2'; g.value = cur; g.setAttribute('aria-label', 'Глубина ответа по умолчанию');
    g.innerHTML = '<sl-radio-button value="fast">Быстро</sl-radio-button><sl-radio-button value="auto">Авто</sl-radio-button><sl-radio-button value="deep">Глубоко</sl-radio-button>';
    g.addEventListener('sl-change', () => { try { localStorage.setItem('nox.depth', g.value); } catch (e) {} if (window.NOXstate && NOXstate.set) { /* без побочных эффектов */ } });
    old.dataset.x = 1; old.replaceWith(g); return true;
  };
  const pulse = (e) => { const sw = e.target; if (!sw || sw.tagName !== 'SL-SWITCH') return; if (window.gsap) window.gsap.fromTo(sw, { scale: .92 }, { scale: 1, duration: .55, ease: 'elastic.out(1,.45)', clearProps: 'transform' }); sw.classList.add('nxm-flash'); setTimeout(() => sw.classList.remove('nxm-flash'), 600); };
  document.addEventListener('sl-change', pulse);
  const go = () => { const side = document.querySelector('.nxm-side'); if (!side) return false; if (!side.dataset.bx) { side.dataset.bx = 1; badges(side); } depth(); return true; };
  let n = 0; const t = setInterval(() => { n++; const ok = go(); if (ok && n > 12) clearInterval(t); if (n > 60) clearInterval(t); }, 500);
})();
