/* Реестр библиотек и ассетов (для страниц «Интеграции Диска» и «О сборке и лицензии»). Статус считается в браузере по факту:
   файл отвечает 200 (лежит) и его имя найдено в исходниках страниц (подключено). Поле lic/licUrl - лицензия и ссылка на её текст. */
export const MIT = 'https://opensource.org/license/mit', OFL = 'https://openfontlicense.org/open-font-license-official-text/', CC0 = 'https://creativecommons.org/publicdomain/zero/1.0/', CCBY = 'https://creativecommons.org/licenses/by/4.0/', APA = 'https://www.apache.org/licenses/LICENSE-2.0', ISC = 'https://opensource.org/license/isc-license-txt', BSD2 = 'https://opensource.org/license/bsd-2-clause', MPL = 'https://www.mozilla.org/MPL/2.0/';
/* g: группа; file: проверяемый файл; mark: строка, по которой ищется использование в исходниках; pkg: package.json для версии */
export const LIBS = [
  { g: 'Сцена и графика', n: 'three', file: 'vendor/three/build/three.module.js', mark: "from 'three'", pkg: 'vendor/three/package.json', lic: 'MIT', licUrl: MIT, role: 'WebGL-фон: туманность, звёзды, планета' },
  { g: 'Сцена и графика', n: 'postprocessing', file: 'vendor/postprocessing/build/index.js', mark: "'postprocessing'", pkg: 'vendor/postprocessing/package.json', lic: 'Zlib', licUrl: 'https://opensource.org/license/zlib', role: 'Bloom и виньетка фона' },
  { g: 'Сцена и графика', n: 'tsParticles', file: 'vendor/tsparticles/tsparticles.bundle.min.js', mark: 'tsparticles.bundle', pkg: 'vendor/tsparticles/package.json', lic: 'MIT', licUrl: MIT, role: 'звёздная пыль' },
  { g: 'Сцена и графика', n: 'lottie-web', file: 'vendor/lottie-web/build/player/lottie.min.js', mark: 'lottie.min.js', pkg: 'vendor/lottie-web/package.json', lic: 'MIT', licUrl: MIT, role: 'значок «ответ завершён», индикатор ожидания' },
  { g: 'Сцена и графика', n: 'Motion', file: 'vendor/motion/dist/motion.js', mark: 'motion/dist/motion.js', pkg: 'vendor/motion/package.json', lic: 'MIT', licUrl: MIT, role: 'плавное появление панелей' },
  { g: 'Сцена и графика', n: 'GSAP', file: 'vendor/fx/gsap.min.js', mark: 'gsap.min.js', lic: 'GreenSock Standard License (не MIT)', licUrl: 'https://gsap.com/standard-license/', role: 'не используется сознательно: лицензия не MIT' },
  { g: 'Сцена и графика', n: 'GlassKit', file: 'vendor/glasskit/glasskit.min.css', mark: 'glasskit', pkg: 'vendor/glasskit/package.json', lic: 'MIT', licUrl: MIT, role: 'не используется: стекло сделано собственным CSS' },
  { g: 'Интерфейс', n: 'Shoelace', file: 'vendor/shoelace/cdn/shoelace-autoloader.js', mark: 'shoelace-autoloader', pkg: 'vendor/shoelace/package.json', lic: 'MIT', licUrl: MIT, role: 'диалоги, панели, значки' },
  { g: 'Интерфейс', n: 'Tabler Icons', file: 'vendor/tabler-icons/icons/outline/settings.svg', mark: 'tabler-icons', pkg: 'vendor/tabler-icons/package.json', lic: 'MIT', licUrl: MIT, role: 'значки интерфейса' },
  { g: 'Интерфейс', n: 'Swiper', file: 'vendor/swiper/swiper-bundle.min.mjs', mark: 'swiper-bundle', pkg: 'vendor/swiper/package.json', lic: 'MIT', licUrl: MIT, role: 'нижнее меню на телефоне' },
  { g: 'Интерфейс', n: 'driver.js', file: 'vendor/driver.js/dist/driver.js.mjs', mark: 'driver.js', pkg: 'vendor/driver.js/package.json', lic: 'MIT', licUrl: MIT, role: 'тур по чату' },
  { g: 'Интерфейс', n: 'SortableJS', file: 'vendor/nox-wow/sortablejs/Sortable.min.js', mark: 'Sortable.min.js', lic: 'MIT', licUrl: MIT, role: 'канбан Проектов, порядок виджетов' },
  { g: 'Данные и графики', n: 'uPlot', file: 'vendor/fx/uPlot.iife.min.js', mark: 'uPlot.iife', lic: 'MIT', licUrl: MIT, role: 'графики Системы' },
  { g: 'Данные и графики', n: 'ECharts', file: 'vendor/nox-extra/echarts.min.js', mark: 'echarts.min.js', lic: 'Apache-2.0', licUrl: APA, role: 'графики Обучения' },
  { g: 'Данные и графики', n: 'Fuse.js', file: 'vendor/nox-extra/fuse.min.js', mark: 'fuse.min.js', lic: 'Apache-2.0', licUrl: APA, role: 'поиск по памяти' },
  { g: 'Данные и графики', n: 'Dexie', file: 'vendor/dexie/dexie.min.js', mark: 'dexie.min.js', lic: 'Apache-2.0', licUrl: APA, role: 'зеркало задач в IndexedDB' },
  { g: 'Данные и графики', n: 'Split.js', file: 'vendor/split.js/split.min.js', mark: 'split.min.js', lic: 'MIT', licUrl: MIT, role: 'разделитель панелей Памяти' },
  { g: 'Календарь, карты, медиа', n: 'FullCalendar', file: 'vendor/nox-extra/fullcalendar.global.min.js', mark: 'fullcalendar.global', lic: 'MIT', licUrl: MIT, role: 'Календарь и Проекты' },
  { g: 'Календарь, карты, медиа', n: 'Leaflet', file: 'vendor/nox-extra/leaflet.js', mark: 'nox-extra/leaflet.js', lic: 'BSD-2-Clause', licUrl: BSD2, role: 'карта в Виджетах' },
  { g: 'Календарь, карты, медиа', n: 'Plyr', file: 'vendor/nox-lib/plyr/plyr.min.js', mark: 'nox-lib/plyr', lic: 'MIT', licUrl: MIT, role: 'плеер Кинозала' },
  { g: 'Календарь, карты, медиа', n: 'wavesurfer.js', file: 'vendor/wavesurfer.js/dist/wavesurfer.esm.js', mark: 'wavesurfer.js/dist', pkg: 'vendor/wavesurfer.js/package.json', lic: 'BSD-3-Clause', licUrl: 'https://opensource.org/license/bsd-3-clause', role: 'волна голоса при записи' },
  { g: 'Календарь, карты, медиа', n: 'PDF.js', file: 'vendor/nox-extra/pdf.mjs', mark: 'pdf.mjs', lic: 'Apache-2.0', licUrl: APA, role: 'просмотр PDF в Памяти' },
  { g: 'Календарь, карты, медиа', n: 'PhotoSwipe', file: 'vendor/nox-extra/photoswipe.esm.js', mark: 'photoswipe.esm', lic: 'MIT', licUrl: MIT, role: 'просмотр изображений в Памяти' },
  { g: 'Календарь, карты, медиа', n: 'ArtPlayer', file: 'vendor/nox-wow/artplayer/artplayer.js', mark: 'artplayer', lic: 'MIT', licUrl: MIT, role: 'не используется: в Кинозале Plyr' },
  { g: 'Календарь, карты, медиа', n: 'Shaka Player', file: 'vendor/nox-extra/shaka-player.compiled.js', mark: 'shaka-player', lic: 'Apache-2.0', licUrl: APA, role: 'только старые страницы (потоковое видео)' },
  { g: 'Календарь, карты, медиа', n: 'epub.js', file: 'vendor/nox-extra/epub.min.js', mark: 'epub.min.js', lic: 'BSD-2-Clause', licUrl: BSD2, role: 'только старые страницы (книги)' },
  { g: 'Ответы чата', n: 'marked', file: 'vendor/nox-lib/marked/marked.min.js', mark: 'nox-lib/marked', lic: 'MIT', licUrl: MIT, role: 'Markdown в ответах' },
  { g: 'Ответы чата', n: 'DOMPurify', file: 'vendor/nox-lib/dompurify/purify.min.js', mark: 'nox-lib/dompurify', lic: 'Apache-2.0 / MPL-2.0', licUrl: APA, role: 'очистка HTML ответов' },
  { g: 'Ответы чата', n: 'KaTeX', file: 'vendor/nox-lib/katex/katex.min.js', mark: 'nox-lib/katex', lic: 'MIT', licUrl: MIT, role: 'формулы в ответах' },
  { g: 'Ответы чата', n: 'Mermaid', file: 'vendor/nox-lib/mermaid/mermaid.min.js', mark: 'nox-lib/mermaid', lic: 'MIT', licUrl: MIT, role: 'диаграммы в ответах' }
];
/* нужные Диску, но отсутствующие в сборке (проверяется тем же запросом: ожидаемый путь не отвечает) */
export const ABSENT = ['Vanta', 'xterm.js', 'Cytoscape', 'GridStack (вместо него собственная сетка)', 'Fabric.js', 'vis-timeline', 'Toastify', 'video.js', 'hls.js', 'dash.js', 'MapLibre GL', 'OpenLayers', 'Turf', 'highlight.js', 'Rive', 'Workbox'];
export const ASSETS = [
  { n: 'Текстуры планет (8 тел)', file: 'vendor/nox-planets/nox-mars.jpg', mark: 'nox-wow-data', lic: 'CC BY 4.0', licUrl: CCBY, by: 'Solar System Scope (данные NASA)', url: 'https://www.solarsystemscope.com/textures/', role: 'фон-планета (Меркурий, Венера, Земля, Марс, Юпитер, Сатурн, Уран, Нептун)' },
  { n: 'Текстура Луны', file: 'vendor/nox-planets/2k_moon.jpg', mark: 'nox-wow-data', lic: 'CC BY 4.0', licUrl: CCBY, by: 'Solar System Scope (данные NASA)', url: 'https://www.solarsystemscope.com/textures/', role: 'фон-планета Луна (1024x512)' },
  { n: 'Каталог звёзд HYG', file: 'vendor/nox-stars/stars.json', mark: 'nox-stars', lic: 'CC BY-SA 4.0', licUrl: 'https://creativecommons.org/licenses/by-sa/4.0/', by: 'HYG Database v4.1, David Nash (astronexus)', url: 'https://www.astronexus.com/projects/hyg', role: 'звёзды фона' },
  { n: 'HDRI Machine Shop 01', file: 'assets/nox-approved/hdr/machine_shop_01_1k.hdr', mark: 'machine_shop', lic: 'CC0', licUrl: CC0, by: 'Poly Haven', url: 'https://polyhaven.com/a/machine_shop_01', role: 'одобрен в сборке, веб Резонанс не использует' },
  { n: 'Metal012 (PBR)', file: 'assets/nox-approved/metal/Metal012_1K-JPG_Color.jpg', mark: 'Metal012', lic: 'CC0', licUrl: CC0, by: 'ambientCG', url: 'https://ambientcg.com/a/Metal012', role: 'одобрен в сборке, веб Резонанс не использует' }
];
export const FONTS = [
  { n: 'Inter', lic: 'SIL OFL 1.1', licUrl: OFL, url: 'https://rsms.me/inter/' }, { n: 'Manrope', lic: 'SIL OFL 1.1', licUrl: OFL, url: 'https://github.com/sharanda/manrope' }, { n: 'JetBrains Mono', lic: 'SIL OFL 1.1', licUrl: OFL, url: 'https://www.jetbrains.com/lp/mono/' }
];
export const SOURCES = ['nox-nav.js', 'nox-shell.js', 'nox-glass.js', 'nox-wow.js', 'nox-wow-bg.js', 'nox-wow-data.js', 'nox-notify.js', 'chat.html', 'index.html', 'projects.html', 'memory.html', 'training.html', 'models.html', 'system.html', 'settings.html', 'calendar.html', 'cinema.html', 'widgets.html', 'dispatcher.html', 'integrations.html', 'about.html',
  'nox-p-home.js', 'nox-p-projects.js', 'nox-p-memory.js', 'nox-p-memory-extra.js', 'nox-p-training.js', 'nox-p-models.js', 'nox-p-system.js', 'nox-p-settings.js', 'nox-p-calendar.js', 'nox-p-cinema.js', 'nox-p-widgets.js', 'nox-p-dispatcher.js'];

const ok = async (u) => { try { const r = await fetch(u, { method: 'HEAD', cache: 'no-store' }); return r.ok; } catch (e) { return false; } };
const txt = async (u) => { try { const r = await fetch(u, { cache: 'no-store' }); return r.ok ? await r.text() : ''; } catch (e) { return ''; } };
/* статус по факту: have = файл отвечает 200; used = в каких исходниках найдено имя; ver = версия из package.json */
export async function scan() {
  const src = {}; await Promise.all(SOURCES.map(async (f) => { src[f] = await txt('./' + f); }));
  const one = async (x) => { const have = await ok('./' + x.file); const used = Object.keys(src).filter((f) => src[f] && x.mark && src[f].includes(x.mark) && !/^nox-registry/.test(f) && !/^(integrations|about)\./.test(f) && !/nox-p-(integrations|about)/.test(f)); let ver = ''; if (x.pkg && have) { try { const j = JSON.parse(await txt('./' + x.pkg)); ver = j.version || ''; } catch (e) { /* без версии */ } } return Object.assign({}, x, { have, used, ver, st: have && used.length ? 'on' : have ? 'idle' : 'no' }); };
  return { libs: await Promise.all(LIBS.map(one)), assets: await Promise.all(ASSETS.map(one)), srcN: Object.keys(src).filter((f) => src[f]).length };
}
