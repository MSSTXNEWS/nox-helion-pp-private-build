/* Память: Split.js (панели), Fuse (нечёткий поиск), просмотр вложений: PDF.js и PhotoSwipe. */
import { $, esc, toast } from './nox-api.js';
const V = './vendor/';
/* ---------- Split.js: тянущаяся граница между результатами и ядром (десктоп) ---------- */
let split = null;
function mkSplit() {
  const want = innerWidth > 1000;
  if (want && !split && window.Split) split = window.Split(['#paneL', '#paneR'], { sizes: [66, 34], minSize: [280, 240], gutterSize: 8, snapOffset: 0 });
  if (!want && split) { split.destroy(); split = null; }
}
mkSplit(); addEventListener('resize', mkSplit);
if (!window.Split) toast('Split.js не загружен: панели без перетаскиваемой границы', true);

/* ---------- Fuse: нечёткий поиск по уже загруженным записям ---------- */
export const corpus = new Map();
export const addCorpus = (ref, text, type) => { if (ref && text) corpus.set(ref, { ref, text, type: type || '' }); };
export function fuzzy(q, n = 8) {
  if (!window.Fuse) return null;
  const f = new window.Fuse([...corpus.values()], { keys: ['text'], threshold: 0.4, ignoreLocation: true, minMatchCharLength: 2, includeScore: true });
  return f.search(q, { limit: n }).map((r) => Object.assign({}, r.item, { score: +(1 - r.score).toFixed(3) }));
}

/* ---------- вложения ---------- */
const files = { imgs: [], pdfs: [] };
let lb = null, pdf = null, pno = 1, rendering = false;
const info = () => { $('#vInfo').textContent = files.imgs.length + ' ФОТО · ' + files.pdfs.length + ' PDF'; };
const imgSize = (u) => new Promise((res) => { const i = new Image(); i.onload = () => res([i.naturalWidth, i.naturalHeight]); i.onerror = () => res([0, 0]); i.src = u; });
async function addImage(f) {
  const u = URL.createObjectURL(f), [w, h] = await imgSize(u); if (!w) { toast('Не удалось прочитать изображение ' + f.name, true); return; }
  files.imgs.push(f); const a = document.createElement('a'); a.href = u; a.dataset.pswpWidth = w; a.dataset.pswpHeight = h; a.target = '_blank'; a.title = f.name; a.style.backgroundImage = 'url(' + u + ')'; a.setAttribute('aria-label', 'Фото ' + f.name); $('#gallery').appendChild(a);
}
async function ensureLb() {
  if (lb) { lb.destroy(); lb = null; }
  const [L, P] = await Promise.all([import(V + 'nox-extra/photoswipe-lightbox.esm.js'), import(V + 'nox-extra/photoswipe.esm.js')]);
  lb = new L.default({ gallery: '#gallery', children: 'a:not(.pdf)', pswpModule: P.default }); lb.init();
}
async function renderPage() {
  if (!pdf || rendering) return; rendering = true;
  try {
    const pg = await pdf.getPage(pno), box = $('#pdfBox').clientWidth || 600, v0 = pg.getViewport({ scale: 1 }), sc = Math.min(2, Math.max(.4, (box - 4) / v0.width)), v = pg.getViewport({ scale: sc }), cv = $('#pdfCv');
    cv.width = v.width; cv.height = v.height; await pg.render({ canvasContext: cv.getContext('2d'), viewport: v }).promise; $('#pInfo').textContent = 'СТРАНИЦА ' + pno + ' / ' + pdf.numPages;
    $('#pPrev').disabled = pno <= 1; $('#pNext').disabled = pno >= pdf.numPages;
  } catch (e) { toast('PDF: страница не отрисовалась: ' + e.message, true); } finally { rendering = false; }
}
async function openPdf(f) {
  try {
    const lib = await import(V + 'nox-extra/pdf.mjs'); lib.GlobalWorkerOptions.workerSrc = V + 'nox-extra/pdf.worker.mjs';
    pdf = await lib.getDocument({ data: new Uint8Array(await f.arrayBuffer()) }).promise; pno = 1; $('#pdfBox').hidden = false; await renderPage(); $('#pdfBox').scrollIntoView({ block: 'nearest' });
  } catch (e) { toast('PDF не открылся: ' + e.message, true); }
}
$('#vPick').addEventListener('click', () => $('#vFile').click());
$('#vFile').addEventListener('change', async (e) => {
  const list = [...e.target.files]; e.target.value = ''; let nImg = 0;
  for (const f of list) {
    if (/^image\//.test(f.type)) { await addImage(f); nImg++; }
    else if (f.type === 'application/pdf' || /\.pdf$/i.test(f.name)) { files.pdfs.push(f); const b = document.createElement('button'); b.type = 'button'; b.className = 'pdf'; b.textContent = 'PDF · ' + f.name; b.title = 'Открыть ' + f.name; b.addEventListener('click', () => openPdf(f)); $('#gallery').appendChild(b); await openPdf(f); }
    else toast('Тип не поддержан: ' + f.name + ' (нужны PDF и изображения)', true);
  }
  info(); if (nImg) await ensureLb();
});
$('#pPrev').addEventListener('click', () => { if (pno > 1) { pno--; renderPage(); } });
$('#pNext').addEventListener('click', () => { if (pdf && pno < pdf.numPages) { pno++; renderPage(); } });
$('#pClose').addEventListener('click', () => { $('#pdfBox').hidden = true; pdf = null; });
info();
