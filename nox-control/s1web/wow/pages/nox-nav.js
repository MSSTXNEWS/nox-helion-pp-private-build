/* NOX · общая оболочка страниц: фон (три.js планета/звёзды), верхнее меню с подписями, нижнее меню-слайдер на телефоне, статус шлюза.
   Страница даёт <body data-page="home|proj|mem|train|core|sys|set"> и <main class="page">; остальное строится здесь. */
import { call, esc } from './nox-api.js';
import './nox-notify.js';
const V = './vendor/';
const NAV = [['home', 'Главная', 'index.html'], ['chat', 'Резонанс', 'chat.html'], ['proj', 'Проекты', 'projects.html'], ['mem', 'Память', 'memory.html'], ['train', 'Обучение', 'training.html'], ['core', 'Ядро', 'models.html'], ['sys', 'Система', 'system.html']];
const SET = ['set', 'Настройки', 'settings.html'];
const cur = document.body.dataset.page;
const here = cur === 'set' ? SET : NAV.find((n) => n[0] === cur) || NAV[0];
const loadScript = (src) => new Promise((res, rej) => { const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = () => rej(new Error('не загрузился ' + src)); document.head.appendChild(s); });
const small = () => innerWidth <= 760;
const cfgGet = () => { try { return JSON.parse(localStorage.getItem('nox.wow.cfg') || '{}'); } catch (e) { return {}; } };

/* ---------- разметка ---------- */
const back = document.createElement('div');
back.innerHTML = '<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs><filter id="nox-lens" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB"><feTurbulence type="fractalNoise" baseFrequency="0.012 0.02" numOctaves="2" seed="7" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="14" xChannelSelector="R" yChannelSelector="G"/></filter></defs></svg>'
  + '<canvas id="space" aria-hidden="true"></canvas><div id="dust" aria-hidden="true"></div><div class="grain" aria-hidden="true"></div><div class="vignette" aria-hidden="true"></div>';
document.body.prepend(...back.childNodes);
const app = document.getElementById('app');
const link = (n, cls) => '<a href="' + n[2] + '" data-k="' + n[0] + '"' + (n[0] === cur ? ' aria-current="page"' : '') + (cls ? ' class="' + cls + '"' : '') + '>' + n[1] + '</a>';
const bar = document.createElement('header'); bar.className = 'bar'; bar.id = 'bar';
bar.innerHTML = '<div class="bar-l"><a class="brand" href="index.html" aria-label="NOX HELION, главная"><span class="mark" aria-hidden="true"></span><b>NOX&nbsp;HELION</b><i>' + esc(here[1]) + '</i></a></div>'
  + '<nav class="seg nav" id="nav" aria-label="Разделы">' + NAV.map((n) => link(n)).join('') + '</nav>'
  + '<div class="bar-r"><span class="status" id="gwStatus" role="status"><i class="led" id="gwLed"></i><span id="gwText" class="mono">ПРОВЕРКА</span></span>'
  + '<span class="seg toplink"><a href="chat.html">Резонанс</a></span>'
  + '<span class="seg icons"><a href="settings.html" aria-label="Настройки" title="Настройки"' + (cur === 'set' ? ' aria-current="page"' : '') + '><sl-icon library="tabler" name="settings"></sl-icon></a></span></div>';
app.prepend(bar);
const mnav = document.createElement('nav'); mnav.className = 'mnav'; mnav.id = 'mnav'; mnav.setAttribute('aria-label', 'Разделы (телефон)');
mnav.innerHTML = '<div class="swiper"><div class="swiper-wrapper seg">' + NAV.filter((n) => n[0] !== 'chat').concat([SET]).map((n) => '<a class="swiper-slide" href="' + n[2] + '"' + (n[0] === cur ? ' aria-current="page"' : '') + '>' + n[1] + '</a>').join('') + '</div></div>';
app.append(mnav);

/* ---------- статус шлюза ---------- */
async function pollGw() {
  const r = await call('/glm/v1/models', { timeout: 5000 }), led = document.getElementById('gwLed'), tx = document.getElementById('gwText');
  const m = r.ok && r.data && r.data.data && r.data.data[0];
  led.className = 'led ' + (m ? 'ok' : 'bad'); tx.textContent = m ? 'GLM-5.3 · ОНЛАЙН' : 'ШЛЮЗ НЕДОСТУПЕН'; document.getElementById('gwStatus').title = m ? 'Шлюз отвечает: ' + m.id : 'Шлюз: ' + r.error;
}
pollGw(); setInterval(pollGw, 30000);

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
