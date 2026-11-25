/* NOX · миры и палитры: применяет html[data-nox-world], --nox-world-rgb; блок выбора внедряется в «Цвет сцены», «Эффекты» и вкладку «Интерфейс» настроек. */
(() => {
  if (window.NOXworlds) return;
  const WORLDS = [['helion', 'HELION', 'жидкий обсидиан и золото (канон)', '233,180,101'], ['chronos', 'CHRONOS', 'латунь, часовые риски', '205,160,90'], ['somnium', 'SOMNIUM', 'перламутровое стекло', '186,140,230'], ['forge', 'FORGE', 'грубый металл и жар', '235,110,60'], ['synapse', 'SYNAPSE', 'мембранные ячейки', '90,220,200']];
  const PAL = [['127,245,239', 'Циан'], ['255,180,84', 'Янтарь'], ['120,255,170', 'Мята'], ['170,150,255', 'Фиолет'], ['255,95,138', 'Малина'], ['110,170,255', 'Лазурь']];
  const g = (k, d) => { try { return localStorage.getItem(k) || d; } catch (e) { return d; } };
  const s = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* хранилище недоступно */ } };
  const apply = () => {
    const w = g('nox.world', 'helion'), p = g('nox.world.pal', ''), d = WORLDS.find((x) => x[0] === w) || WORLDS[0], root = document.documentElement;
    root.setAttribute('data-nox-world', d[0]); root.style.setProperty('--nox-world-rgb', p || d[3]);
    document.body && document.body.classList.add('nox-shared-glass');
    window.dispatchEvent(new CustomEvent('nox:world', { detail: { world: d[0], rgb: p || d[3] } }));
  };
  apply(); document.addEventListener('DOMContentLoaded', apply);
  const widget = () => {
    const el = document.createElement('div'); el.className = 'nxwd'; el.id = 'nxworlds';
    const paint = () => {
      const w = g('nox.world', 'helion'), p = g('nox.world.pal', '');
      el.innerHTML = '<h4>Мир интерфейса</h4><div class="nxwd-w" role="radiogroup" aria-label="Мир">' + WORLDS.map((x) => '<button type="button" role="radio" data-w="' + x[0] + '" aria-checked="' + (x[0] === w) + '"><b>' + x[1] + '</b><small>' + x[2] + '</small></button>').join('') + '</div>'
        + '<h4>Палитра сцены</h4><div class="nxwd-p" role="radiogroup" aria-label="Палитра"><button type="button" role="radio" data-p="" aria-checked="' + (p === '') + '" title="Цвет мира"><i style="background:conic-gradient(#e9b465,#bb86f0,#5adcc8,#eb6e3c,#e9b465)"></i></button>'
        + PAL.map((x) => '<button type="button" role="radio" data-p="' + x[0] + '" aria-checked="' + (x[0] === p) + '" title="' + x[1] + '" aria-label="' + x[1] + '"><i style="background:rgb(' + x[0] + ')"></i></button>').join('') + '</div>';
    };
    paint();
    el.addEventListener('click', (e) => { const b = e.target.closest('button'); if (!b) return; if (b.dataset.w) s('nox.world', b.dataset.w); else if (b.dataset.p !== undefined) s('nox.world.pal', b.dataset.p); else return; apply(); paint(); });
    return el;
  };
  const mount = () => {
    const f = location.pathname.split('/').pop();
    if (document.getElementById('nxworlds') || !/^(scene|effects)\.html$/.test(f)) return;
    const host = document.querySelector('.wrap') || document.querySelector('main') || document.body;
    const card = document.createElement('section'); card.className = 'card c12'; card.style.margin = '14px 0'; card.appendChild(widget()); host.appendChild(card);
  };
  window.NOXworlds = { apply, widget, WORLDS, PAL };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(mount, 600)); else setTimeout(mount, 600);
})();
