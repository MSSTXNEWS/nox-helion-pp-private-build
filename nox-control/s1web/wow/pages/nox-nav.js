/* NOX · общая оболочка страниц: фон (три.js планета/звёзды), верхнее меню с подписями, нижнее меню-слайдер на телефоне, статус шлюза.
   Страница даёт <body data-page="home|proj|mem|train|core|sys|set"> и <main class="page">; остальное строится здесь. */
import './nox-api.js';
import './nox-glass.js';
import './nox-notify.js';
const V = './vendor/';
import { NAV, MORE, SET, mountShell, startTiers } from './nox-shell.js';
const cur = document.body.dataset.page;
const loadScript = (src) => new Promise((res, rej) => { const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = () => rej(new Error('не загрузился ' + src)); document.head.appendChild(s); });
const small = () => innerWidth <= 760;
const cfgGet = () => { try { return JSON.parse(localStorage.getItem('nox.wow.cfg') || '{}'); } catch (e) { return {}; } };

/* ---------- разметка ---------- */
const back = document.createElement('div');
back.innerHTML = '<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs><filter id="nox-lens" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB"><feTurbulence type="fractalNoise" baseFrequency="0.012 0.02" numOctaves="2" seed="7" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="14" xChannelSelector="R" yChannelSelector="G"/></filter></defs></svg>'
  + '<canvas id="space" aria-hidden="true"></canvas><div id="dust" aria-hidden="true"></div><div class="grain" aria-hidden="true"></div><div class="vignette" aria-hidden="true"></div>';
document.body.prepend(...back.childNodes);
const app = document.getElementById('app');
mountShell(app, cur);
startTiers();

/* ---------- Shoelace (диалоги, иконки Tabler) ---------- */
export const ready = (async () => {
  try {
    const [bp, il] = await Promise.all([import(V + 'shoelace/cdn/utilities/base-path.js'), import(V + 'shoelace/cdn/utilities/icon-library.js')]);
    bp.setBasePath(new URL(V + 'shoelace/cdn', location.href).href);
    il.registerIconLibrary('tabler', { resolver: (n) => new URL(V + 'tabler-icons/icons/outline/' + n + '.svg', location.href).href });
    await import(V + 'shoelace/cdn/shoelace-autoloader.js');
  } catch (e) { console.warn('shoelace:', e.message); }
  document.body.classList.remove('boot');
  try { await loadScript(V + 'motion/dist/motion.js'); const A = window.Motion && window.Motion.animate; if (A) A([...document.querySelectorAll('.bar, .page .card, .page .ph')].slice(0, 24), { opacity: [0, 1], transform: ['translateY(8px)', 'translateY(0px)'] }, { duration: .7, delay: window.Motion.stagger ? window.Motion.stagger(.04) : 0, ease: [.22, .8, .2, 1] }); } catch (e) { /* без анимации входа */ }
})();

/* ---------- фон: единый WebGL-контекст; запасной путь как в «Резонансе» ---------- */
export const space = import('./nox-wow-bg.js').then((m) => m.startSpace({ canvas: document.getElementById('space') })).then((s) => { s.setLevel(cfgGet().space || 'on'); window.__noxSpace = s; return s; })
  .catch(async (e) => { console.warn('фон: запасной путь,', e.message); const c = document.getElementById('space'); if (c) c.remove(); document.body.classList.add('bgfallback'); try { await loadScript('./nox-v14-real.js'); await loadScript('./nox-v14-planet.js'); } catch (x) { /* без фона */ } return null; });
(async () => { /* звёздная пыль */
  try { if (!window.tsParticles) await loadScript(V + 'tsparticles/tsparticles.bundle.min.js'); await window.tsParticles.load({ id: 'dust', options: { fullScreen: { enable: false }, background: { color: 'transparent' }, fpsLimit: 30, detectRetina: false, particles: { number: { value: small() ? 16 : 38 }, color: { value: ['#9ff7f2', '#ffffff', '#ffd9a0'] }, opacity: { value: { min: .06, max: .4 }, animation: { enable: true, speed: .35, sync: false } }, size: { value: { min: .5, max: 1.5 } }, move: { enable: true, speed: .14, direction: 'none', random: true, straight: false, outModes: { default: 'out' } }, shape: { type: 'circle' } }, interactivity: { events: { onHover: { enable: false }, onClick: { enable: false } } } } }); } catch (e) { console.warn('пыль:', e.message); }
})();

/* ---------- нижнее меню-ползунок (телефон) ---------- */
if (small()) import(V + 'swiper/swiper-bundle.min.mjs').then((m) => {
  const S = m.default || m.Swiper, idx = Math.max(0, [...document.querySelectorAll('.mnav .swiper-slide')].findIndex((a) => a.hasAttribute('aria-current')));
  new S('.mnav .swiper', { slidesPerView: 'auto', freeMode: true, spaceBetween: 0, resistanceRatio: .6, centeredSlides: true, centeredSlidesBounds: true, initialSlide: idx });
}).catch((e) => console.warn('swiper:', e.message));

/* ---------- «нет данных» вместо больших красных блоков: длинное сообщение об ошибке сворачивается в честную строку с раскрытием ---------- */
{
  const esc2 = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const foldErr = (n) => {
    if (n.dataset.folded || n.closest('details.fold') || n.closest('.svc') || n.closest('sl-dialog')) return;
    const t = n.textContent.trim(); if (t.length < 70) return; n.dataset.folded = '1';
    const head = t.split(/[:.(;]/)[0].trim().slice(0, 64) || 'Нет данных';
    const d = document.createElement('details'); d.className = 'fold nodata'; const sm = document.createElement('summary'); sm.innerHTML = '<i class="led warn"></i>' + esc2(head) + '<span class="mono">нет данных · подробнее</span>';
    n.replaceWith(d); d.append(sm, n);
  };
  const scanErr = () => document.querySelectorAll('.page .err:not([data-folded])').forEach(foldErr);
  let tm = 0; new MutationObserver(() => { clearTimeout(tm); tm = setTimeout(scanErr, 60); }).observe(document.getElementById('page') || document.body, { childList: true, subtree: true });
  scanErr();
}
