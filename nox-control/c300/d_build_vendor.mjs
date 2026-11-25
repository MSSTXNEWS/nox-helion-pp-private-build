// Сборка готовых к браузеру модулей: node_modules -> /workspace/nox/web/site/vendor/<имя>/ ; пишет INDEX.json
import fs from 'fs'; import path from 'path'; import { build } from '/workspace/nox/web/build/node_modules/esbuild/lib/main.js';
const NM = '/workspace/nox/web/build/node_modules', SRC = '/workspace/nox/web/build/src', V = '/workspace/nox/web/site/vendor';
const only = process.argv[2] ? process.argv[2].split(',') : null;
const J = p => { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return null; } };
const sz = p => fs.statSync(p).size;
function walk(d, o = []) { for (const f of fs.readdirSync(d)) { const p = path.join(d, f); fs.statSync(p).isDirectory() ? walk(p, o) : o.push(p); } return o; }
function cp(src, dst) { fs.mkdirSync(path.dirname(dst), { recursive: true }); fs.cpSync(src, dst, { recursive: true }); }
function lic(dir, pj) { let l = pj && (typeof pj.license === 'string' ? pj.license : pj.license && pj.license.type); if (l) return l;
  for (const f of ['LICENSE', 'LICENSE.md', 'LICENSE.txt', 'license', 'COPYING', 'LICENCE']) { const p = path.join(dir, f); if (fs.existsSync(p)) return 'см. ' + f + ': ' + fs.readFileSync(p, 'utf8').split('\n').find(x => x.trim()).trim().slice(0, 60); } return '?'; }
// [имя, npm-пакет|'git:папка', опции]
const M = [
 ['three','three',{exist:1,page:'фон, сцена',ex:'import * as THREE from "./vendor/three/three.module.js"'}],
 ['postprocessing','postprocessing',{exist:1,page:'фон, сцена'}],
 ['tsparticles','@tsparticles/slim',{exist:1,page:'все'}],
 ['shoelace','@shoelace-style/shoelace',{exist:1,page:'все'}],
 ['motion','motion',{exist:1,page:'все'}],
 ['swiper','swiper',{exist:1,page:'кино, новости, фото'}],
 ['gridstack','gridstack',{exist:1,page:'главная'}],
 ['wavesurfer.js','wavesurfer.js',{exist:1,page:'музыка, голос'}],
 ['lottie-web','lottie-web',{exist:1,page:'все'}],
 ['ninja-keys','ninja-keys',{exist:1,page:'все (палитра команд)'}],
 ['cytoscape','cytoscape',{exist:1,page:'мозг, знания'}],
 ['gsap','gsap',{bundle:'gsap/all',copy:['dist/gsap.min.js','dist/ScrollTrigger.min.js','dist/Flip.min.js','dist/Draggable.min.js'],page:'все (анимации)',ex:'<script src="./vendor/gsap/gsap.min.js"></script> или import {gsap} from "./vendor/gsap/gsap.esm.js"',note:'лицензия GSAP Standard no-charge, не MIT'}],
 ['arwes-frames','@arwes/frames',{bundle:1,page:'HUD, все',ex:'import {createFrame} from "./vendor/arwes-frames/arwes-frames.esm.js"'}],
 ['arwes-animated','@arwes/animated',{bundle:1,page:'HUD, все'}],
 ['rive','@rive-app/canvas',{bundle:1,copy:['rive.wasm'],page:'аватар, главная',ex:'import {Rive,RuntimeLoader} from "./vendor/rive/rive.esm.js"; RuntimeLoader.setWasmUrl("./vendor/rive/rive.wasm")'}],
 ['cmdk','cmdk',{bundle:1,page:'палитра команд (React)'}],
 ['sortablejs','sortablejs',{bundle:1,copy:['Sortable.min.js'],page:'задачи, главная'}],
 ['tremor','@tremor/react',{bundle:1,page:'финансы, дашборды',note:'нужен Tailwind CSS для стилей'}],
 ['assistant-ui','@assistant-ui/react',{bundle:1,page:'чат'}],
 ['deep-chat','deep-chat',{copy:['dist/deepChat.bundle.js'],bundle:1,page:'чат, голос'}],
 ['xyflow','@xyflow/react',{bundle:1,css:['dist/style.css'],page:'карта мышления, конструктор'}],
 ['ag-ui','@ag-ui/client',{bundle:1,page:'чат (протокол агентов)'}],
 ['highlight.js','highlight.js',{bundle:'highlight.js/lib/common',copycss:'styles',copy:['styles/github-dark.min.css','styles/github.min.css','styles/atom-one-dark.min.css'],page:'чат, код'}],
 ['vidstack','vidstack',{copy:['player','icons'],bundle:'vidstack/elements',page:'кино, видео'}],
 ['vidstack-react','@vidstack/react',{bundle:1,page:'кино (React)'}],
 ['shaka-player','shaka-player',{copy:['dist/shaka-player.ui.js','dist/shaka-player.compiled.js','dist/controls.css','dist/locales.js'],page:'кино, ТВ (HLS/DASH)',ex:'<script src="./vendor/shaka-player/shaka-player.ui.js"></script>'}],
 ['dashjs','dashjs',{copy:['dist/modern/esm/dash.all.min.js','dist/modern/umd/dash.all.min.js'],page:'кино, ТВ (DASH)'}],
 ['masonry','masonry-layout',{copy:['dist/masonry.pkgd.min.js'],page:'фото, новости'}],
 ['readability','@mozilla/readability',{copy:['Readability.js','Readability-readerable.js'],bundle:1,page:'новости, читалка'}],
 ['ffmpeg','@ffmpeg/ffmpeg',{copy:['dist/esm'],page:'студия, видео'}],
 ['ffmpeg-util','@ffmpeg/util',{copy:['dist/esm'],page:'студия'}],
 ['ffmpeg-core','@ffmpeg/core',{copy:['dist/esm'],page:'студия',note:'ffmpeg-core.wasm ~30 МБ'}],
 ['fabric','fabric',{copy:['dist/index.min.js','dist/index.min.mjs'],page:'фото, доска'}],
 ['phaser','phaser',{copy:['dist/phaser.min.js'],page:'игры'}],
 ['boardgame-io','boardgame.io',{bundle:'boardgame.io/client',page:'игры'}],
 ['chessground','chessground',{bundle:1,copy:['assets'],page:'игры (шахматы)'}],
 ['grapesjs','grapesjs',{copy:['dist/grapes.min.js','dist/css/grapes.min.css'],page:'конструктор'}],
 ['blocknote','@blocknote/core',{bundle:1,css:['dist/style.css'],page:'заметки'}],
 ['ts-fsrs','ts-fsrs',{bundle:1,page:'обучение (карточки)'}],
 ['circuitsvis','circuitsvis',{copy:['dist'],page:'мозг, обучение'}],
 ['cosmos-gl','@cosmos.gl/graph',{bundle:1,page:'мозг, знания'}],
 ['sigma','sigma',{bundle:1,page:'знания (граф)'}],
 ['graphology','graphology',{bundle:1,page:'знания (граф)'}],
 ['theatre','@theatre/core',{bundle:1,page:'сцена, анимации'}],
 ['jsonforms','@jsonforms/core',{bundle:1,page:'настройки'}],
 ['three-vrm','@pixiv/three-vrm',{bundle:1,ext:['three','three/addons/*','three/examples/jsm/*'],page:'чат, ТВ (аватар)',ex:'importmap: {"imports":{"three":"./vendor/three/three.module.js"}} затем import {VRMLoaderPlugin} from "./vendor/three-vrm/three-vrm.esm.js"'}],
 ['mediapipe-tasks-vision','@mediapipe/tasks-vision',{copy:['vision_bundle.mjs','vision_bundle.cjs','wasm'],page:'вся сборка (жесты)',ex:'import {FilesetResolver,GestureRecognizer} from "./vendor/mediapipe-tasks-vision/vision_bundle.mjs"; FilesetResolver.forVisionTasks("./vendor/mediapipe-tasks-vision/wasm")'}],
 ['transformers-js','@huggingface/transformers',{copy:['dist'],page:'фото, камера',ex:'import {pipeline,env} from "./vendor/transformers-js/transformers.min.js"'}],
 ['mermaid','mermaid',{copy:['dist/mermaid.min.js','dist/mermaid.esm.min.mjs','dist/chunks/mermaid.esm.min'],page:'чат',ex:'<script src="./vendor/mermaid/mermaid.min.js"></script>'}],
 ['katex','katex',{copy:['dist/katex.min.js','dist/katex.min.css','dist/katex.min.mjs','dist/fonts','dist/contrib/auto-render.min.js'],page:'чат',ex:'<link rel="stylesheet" href="./vendor/katex/katex.min.css">'}],
 ['lightweight-charts','lightweight-charts',{copy:['dist/lightweight-charts.standalone.production.js','dist/lightweight-charts.production.mjs','dist/lightweight-charts.standalone.production.mjs'],page:'финансы, главная'}],
 ['echarts','echarts',{copy:['dist/echarts.min.js'],page:'органы, финансы'}],
 ['globe-gl','globe.gl',{copy:['dist/globe.gl.min.js'],page:'атлас'}],
 ['maplibre-gl','maplibre-gl',{copy:['dist/maplibre-gl.css','dist/maplibre-gl.mjs','dist/maplibre-gl-shared.mjs','dist/maplibre-gl-worker.mjs'],page:'атлас, карты'}],
 ['yjs','yjs',{bundle:1,page:'доска, совместная работа'}],
 ['frappe-gantt','frappe-gantt',{copy:['dist'],page:'проекты'}],
 ['xterm','@xterm/xterm',{copy:['lib','css'],page:'терминал'}],
 ['tesseract','tesseract.js',{copy:['dist'],page:'фото, документы (OCR)'}],
 ['pdfjs','pdfjs-dist',{copy:['build/pdf.min.mjs','build/pdf.worker.min.mjs'],page:'документы'}],
 ['pdf-lib','pdf-lib',{copy:['dist/pdf-lib.min.js'],page:'документы'}],
];
if (process.env.EXTRA && fs.existsSync(process.env.EXTRA)) { const have = new Set(M.map(m => m[1])); for (const pkg of fs.readFileSync(process.env.EXTRA, 'utf8').split(/\s+/).filter(Boolean)) { if (have.has(pkg) || /kokoro/.test(pkg)) continue; have.add(pkg); const n = pkg.replace(/^@/, '').replace(/\//g, '-'); M.push([n, pkg, { bundle: 1, page: 'см. IDEAS.md', extra: 1 }]); } }
const out = []; const log = (...a) => console.log(...a);
for (const [n, pkg, o] of M) {
  if (only && !only.includes(n)) continue;
  const dir = path.join(NM, pkg), pj = J(path.join(dir, 'package.json')); const dst = path.join(V, n);
  const ent = { name: n, pkg, version: pj && pj.version, license: pj ? lic(dir, pj) : null, dir: 'vendor/' + n + '/', page: o.page || '', example: o.ex || '', note: o.note || '', status: 'ok', files: [] };
  try {
    if (!pj) throw new Error('нет пакета в node_modules');
    if (o.exist && fs.existsSync(dst) && fs.readdirSync(dst).length) { ent.status = 'уже стоял'; ent.files = walk(dst).filter(f => /\.(m?js|css)$/.test(f)).slice(0, 8).map(f => path.relative(path.join(V, '..'), f)); out.push(ent); continue; }
    fs.mkdirSync(dst, { recursive: true });
    for (const c of o.copy || []) { const s = path.join(dir, c); if (fs.existsSync(s)) cp(s, fs.statSync(s).isDirectory() ? path.join(dst, path.basename(c)) : path.join(dst, path.basename(c))); else log('  нет', n, c); }
    for (const c of o.css || []) { const s = path.join(dir, c); if (fs.existsSync(s)) cp(s, path.join(dst, n + '.css')); else log('  нет css', n, c); }
    if (o.bundle) {
      const spec = o.bundle === 1 ? pkg : o.bundle; const g = 'NOX_' + n.replace(/[^A-Za-z0-9]/g, '_');
      const contents = `import * as _ from ${JSON.stringify(spec)}; export * from ${JSON.stringify(spec)}; export default (_.default!==undefined?_.default:_);`;
      const common = { stdin: { contents, resolveDir: '/workspace/nox/web/build', loader: 'js' }, bundle: true, minify: true, platform: 'browser', target: 'es2020', logLevel: 'silent', define: { 'process.env.NODE_ENV': '"production"', global: 'globalThis' }, external: o.ext || [], loader: { '.woff2': 'dataurl', '.woff': 'dataurl', '.svg': 'dataurl', '.png': 'dataurl', '.css': 'css', '.wasm': 'file' }, assetNames: 'assets/[name]-[hash]', legalComments: 'none' };
      try { await build({ ...common, format: 'esm', outfile: path.join(dst, n + '.esm.js') }); } catch (e) { log('  ESM fail', n, String(e.message).split('\n')[0]); ent.note += ' ESM-сборка не удалась'; }
      if (!(o.ext || []).length) try { await build({ ...common, format: 'iife', globalName: g, outfile: path.join(dst, n + '.iife.js') }); ent.global = g; } catch (e) { log('  IIFE fail', n, String(e.message).split('\n')[0]); }
    }
    const fl = walk(dst); if (!fl.length) throw new Error('пусто');
    ent.files = fl.map(f => path.relative(path.join(V, '..'), f) + ' ' + Math.round(sz(f) / 1024) + 'K').slice(0, 12); ent.totalKB = Math.round(fl.reduce((a, f) => a + sz(f), 0) / 1024);
    const m = fl.find(f => /\.esm\.js$/.test(f)) || fl.find(f => /\.min\.m?js$/.test(f)) || fl.find(f => /\.m?js$/.test(f)); ent.main = m && path.relative(path.join(V, '..'), m);
    if (!ent.example && ent.main) ent.example = fl.some(f => /\.esm\.js$/.test(f)) ? `import * as M from "./${ent.main}"` : `<script src="./${ent.main}"></script>`;
  } catch (e) { ent.status = 'FAIL: ' + e.message; log('FAIL', n, e.message); }
  log(n, ent.status, ent.version, ent.totalKB || '');
  out.push(ent);
}
fs.writeFileSync(path.join(V, only ? 'INDEX.part.json' : 'INDEX.json'), JSON.stringify({ generated: new Date().toISOString(), base: 'site/vendor', modules: out }, null, 1));
log('DONE', out.length);
