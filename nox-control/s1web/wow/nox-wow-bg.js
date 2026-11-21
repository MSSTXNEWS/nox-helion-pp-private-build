/* NOX WOW · фон: ОДИН WebGL-контекст (three) = туманность + звёзды HYG + планета с текстурами + bloom/виньетка (postprocessing).
   Запасной вариант: если three/WebGL2 недоступны - страница подключает nox-v14-real.js (+ nox-v14-planet.js). */
import * as THREE from 'three';
import { EffectComposer, RenderPass, EffectPass, BloomEffect, VignetteEffect, BlendFunction } from 'postprocessing';
import { VS, NEB, COMP as COMP0, SVS, SFS as SFS0 } from './nox-wow-shaders.js';
/* шейдеры пишут значения «как на экране»; финальный проход postprocessing кодирует в sRGB - переводим в линейное пространство */
const sv = (s) => s.replace(/^#version 300 es\n/, '');
const SVSZ = (s) => s.replace('uPar.y*2.,0.,1.);', 'uPar.y*2.,.9999,1.);');
const COMP = sv(COMP0).replace('o=vec4(c,1.);}', 'o=vec4(pow(c,vec3(2.2)),1.);}'), SFS = sv(SFS0).replace('o=vec4(vC*a,1.);}', 'o=vec4(pow(vC*a,vec3(2.2)),1.);}');

const KEY = 'nox:planet', KEYQ = 'nox.wow.space';
import { PLANETS, byId } from './nox-wow-data.js';
export { PLANETS, byId };
const lsGet = (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : v; } catch (e) { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* нет хранилища */ } };
const base = new URL('.', import.meta.url).href;
const TEXDIR = base + 'vendor/nox-planets/';

/* ---------- процедурная текстура (запасная, если фото не загрузилось) ---------- */
function procTexture(p) {
  const W = 768, H = 384, c = document.createElement('canvas'); c.width = W; c.height = H; const g = c.getContext('2d'), im = g.createImageData(W, H);
  const hash = (x, y) => { let h = (x * 374761393 + y * 668265263) | 0; h = (h ^ (h >>> 13)) * 1274126177 | 0; return ((h ^ (h >>> 16)) >>> 0) / 4294967295; };
  const vn = (x, y) => { const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi, u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf); return (hash(xi, yi) * (1 - u) + hash(xi + 1, yi) * u) * (1 - v) + (hash(xi, yi + 1) * (1 - u) + hash(xi + 1, yi + 1) * u) * v; };
  const fbm = (x, y) => { let a = .5, s = 0; for (let i = 0; i < 5; i++) { s += a * vn(x, y); x = x * 2.03 + 7.1; y = y * 2.03 + 3.3; a *= .5; } return s; };
  const pr = p.proc || {}, b = pr.base || [.5, .5, .5], hh = pr.hi || [.8, .8, .8];
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const u = x / W, v = y / H; let n = fbm(u * 8, v * 4);
    if (pr.band) { n = n * .35 + .65 * (.5 + .5 * Math.sin(v * 38 * pr.band + fbm(u * 6, v * 20) * 5)); }
    let r, gg, bb;
    if (pr.land) { const land = n > .52; const t = land ? Math.min(1, (n - .5) * 2.4) : 0; r = land ? .16 + .4 * t : b[0]; gg = land ? .36 + .2 * t : b[1] + .12 * n; bb = land ? .14 + .1 * t : b[2] + .1 * n; const pole = Math.abs(v - .5) > .44; if (pole) { r = gg = bb = .92; } }
    else { r = b[0] + (hh[0] - b[0]) * n; gg = b[1] + (hh[1] - b[1]) * n; bb = b[2] + (hh[2] - b[2]) * n; if (pr.crater) { const cr = vn(u * 40, v * 20); if (cr > .86) { r *= .72; gg *= .72; bb *= .72; } } }
    const i = (y * W + x) * 4; im.data[i] = Math.min(255, r * 255); im.data[i + 1] = Math.min(255, gg * 255); im.data[i + 2] = Math.min(255, bb * 255); im.data[i + 3] = 255;
  }
  g.putImageData(im, 0, 0); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.wrapS = THREE.RepeatWrapping; return t;
}
function procRing() {
  const c = document.createElement('canvas'); c.width = 512; c.height = 4; const g = c.getContext('2d'), gr = g.createLinearGradient(0, 0, 512, 0);
  [[0, 0], [.08, .55], [.22, .25], [.3, .75], [.5, .85], [.62, .15], [.7, .8], [.93, .6], [1, 0]].forEach((s) => gr.addColorStop(s[0], 'rgba(226,205,160,' + s[1] + ')'));
  g.fillStyle = gr; g.fillRect(0, 0, 512, 4); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

export async function startSpace(opts) {
  const o = Object.assign({ canvas: null, onstate: () => {} }, opts || {});
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const small = () => innerWidth <= 820 || matchMedia('(pointer:coarse)').matches;
  const cv = o.canvas;
  const renderer = new THREE.WebGLRenderer({ canvas: cv, antialias: false, alpha: false, powerPreference: 'high-performance' });
  if (!renderer.capabilities.isWebGL2) throw new Error('нужен WebGL2');
  const state = { level: lsGet(KEYQ, 'on'), planet: lsGet(KEY, 'earth'), px: 0, py: 0, tx: 0, ty: 0, run: true, texStatus: {} };
  let dprCap = small() ? 1 : 1.5;
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, dprCap));
  renderer.setClearColor(0x02030a, 1);
  const scene = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(30, 1, .1, 100); cam.position.set(0, 0, 10);

  /* туманность -> маленькая цель -> композит (ACES) полноэкранным треугольником */
  const tri = new THREE.BufferGeometry(); tri.setAttribute('p', new THREE.BufferAttribute(new Float32Array([-1, -1, 3, -1, -1, 3]), 2)); tri.setDrawRange(0, 3);
  const nebRT = new THREE.WebGLRenderTarget(64, 48, { magFilter: THREE.LinearFilter, minFilter: THREE.LinearFilter, wrapS: THREE.MirroredRepeatWrapping, wrapT: THREE.MirroredRepeatWrapping });
  const nebMat = new THREE.RawShaderMaterial({ glslVersion: THREE.GLSL3, vertexShader: sv(VS), fragmentShader: sv(NEB), uniforms: { uRes: { value: new THREE.Vector2(64, 48) }, uT: { value: 40 } }, depthTest: false, depthWrite: false });
  const nebScene = new THREE.Scene(), nebMesh = new THREE.Mesh(tri, nebMat); nebMesh.frustumCulled = false; nebScene.add(nebMesh);
  const compMat = new THREE.RawShaderMaterial({ glslVersion: THREE.GLSL3, vertexShader: sv(VS), fragmentShader: COMP, uniforms: { uN: { value: nebRT.texture }, uPar: { value: new THREE.Vector2() }, uExp: { value: .34 }, uRes: { value: new THREE.Vector2(2, 2) } }, depthTest: false, depthWrite: false });
  const comp = new THREE.Mesh(tri, compMat); comp.frustumCulled = false; comp.renderOrder = -10; scene.add(comp);

  /* звёзды HYG */
  let starsPts = null; const starMat = new THREE.RawShaderMaterial({ glslVersion: THREE.GLSL3, vertexShader: SVSZ(sv(SVS)), fragmentShader: SFS, uniforms: { uRes: { value: new THREE.Vector2(2, 2) }, uDpr: { value: 1 }, uRa: { value: 0 }, uTime: { value: 0 }, uPar: { value: new THREE.Vector2() } }, transparent: true, blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor, depthTest: true, depthWrite: false });
  try {
    const j = await (await fetch(base + 'vendor/nox-stars/stars.json')).json(); const n = j.s.length, A = new Float32Array(n * 4), C = new Float32Array(n * 3);
    const bb = (bv) => { bv = Math.max(-.4, Math.min(2, bv)); const T = 4600 * (1 / (.92 * bv + 1.7) + 1 / (.92 * bv + .62)), t = T / 100; let r = t <= 66 ? 255 : 329.7 * Math.pow(t - 60, -.1332), g = t <= 66 ? 99.47 * Math.log(t) - 161.1 : 288.1 * Math.pow(t - 60, -.0755), b = t >= 66 ? 255 : (t <= 19 ? 0 : 138.5 * Math.log(t - 10) - 305); r = Math.max(0, Math.min(255, r)) / 255; g = Math.max(0, Math.min(255, g)) / 255; b = Math.max(0, Math.min(255, b)) / 255; const m = (r + g + b) / 3; return [m + (r - m) * .6, m + (g - m) * .6, m + (b - m) * .6]; };
    for (let i = 0; i < n; i++) { const s = j.s[i]; A.set(s, i * 4); C.set(bb(s[3]), i * 3); }
    const sg = new THREE.BufferGeometry(); sg.setAttribute('aS', new THREE.BufferAttribute(A, 4)); sg.setAttribute('aC', new THREE.BufferAttribute(C, 3)); sg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    starsPts = new THREE.Points(sg, starMat); starsPts.frustumCulled = false; starsPts.renderOrder = -5; scene.add(starsPts);
  } catch (e) { /* без каталога: только туманность */ }

  /* планета */
  const pg = new THREE.Group(); scene.add(pg); const tilt = new THREE.Group(); pg.add(tilt);
  const sun = new THREE.DirectionalLight(0xfff1de, 3.6); sun.position.set(-4, 3.2, 4); scene.add(sun); scene.add(new THREE.AmbientLight(0x1a2236, .7));
  let body = null, ringMesh = null, atmo = null, planetId = null, loadTok = 0;
  const loader = new THREE.TextureLoader();
  let manifest = null; const getManifest = async () => { if (manifest) return manifest; try { const r = await fetch(TEXDIR + 'manifest.json', { cache: 'no-store' }); manifest = r.ok ? new Set((await r.json()).files || []) : new Set(['*']); } catch (e) { manifest = new Set(['*']); } return manifest; };
  const loadFirst = async (all) => { const mf = await getManifest(), names = mf.has('*') ? all : all.filter((n) => mf.has(n)); return loadFirst0(names); };
  const loadFirst0 = (names) => new Promise((res) => { let i = 0; const next = () => { if (i >= names.length) return res(null); const u = TEXDIR + names[i++]; loader.load(u, (t) => res({ t, name: names[i - 1] }), undefined, next); }; next(); });
  function disposeBody() { [body, ringMesh, atmo].forEach((m) => { if (!m) return; m.parent && m.parent.remove(m); m.geometry && m.geometry.dispose(); const mt = m.material; if (mt) { mt.map && mt.map.dispose(); mt.alphaMap && mt.alphaMap.dispose(); mt.dispose(); } }); body = ringMesh = atmo = null; }
  const atmoMat = (col, k) => new THREE.ShaderMaterial({ transparent: true, side: THREE.BackSide, blending: THREE.AdditiveBlending, depthWrite: false, uniforms: { uC: { value: new THREE.Color(col[0], col[1], col[2]) }, uK: { value: k } }, vertexShader: 'varying vec3 vN;varying vec3 vP;void main(){vN=normalize(normalMatrix*normal);vec4 mv=modelViewMatrix*vec4(position,1.);vP=mv.xyz;gl_Position=projectionMatrix*mv;}', fragmentShader: 'uniform vec3 uC;uniform float uK;varying vec3 vN;varying vec3 vP;void main(){float f=pow(1.-abs(dot(normalize(vN),normalize(-vP))),3.4);gl_FragColor=vec4(uC*f*uK*1.1,f);}' });
  async function setPlanet(id) {
    const p = byId(id), tok = ++loadTok; state.planet = p.id; lsSet(KEY, p.id); planetId = p.id; disposeBody();
    if (p.id === 'none') { layout(); o.onstate(state); return; }
    const got = p.tex ? await loadFirst(p.tex) : null; if (tok !== loadTok) return;
    let map; if (got) { map = got.t; map.colorSpace = THREE.SRGBColorSpace; map.anisotropy = 4; state.texStatus[p.id] = 'photo:' + got.name; } else { map = procTexture(p); state.texStatus[p.id] = 'procedural'; }
    body = new THREE.Mesh(new THREE.SphereGeometry(1, 128, 96), new THREE.MeshStandardMaterial({ map, roughness: .92, metalness: 0 }));
    tilt.rotation.set(p.ring ? -.32 : -.7, 0, p.ring ? .1 : .3); tilt.add(body);
    const al = p.atm || [.4, .6, 1]; atmo = new THREE.Mesh(new THREE.SphereGeometry(1.05, 96, 64), atmoMat(al, p.atmK == null ? 1 : p.atmK)); pg.add(atmo);
    if (p.ring) {
      const rg = new THREE.RingGeometry(1.32, 2.45, 160, 1), pos = rg.attributes.position, uv = rg.attributes.uv; for (let i = 0; i < pos.count; i++) { const r = Math.hypot(pos.getX(i), pos.getY(i)); uv.setXY(i, (r - 1.32) / (2.45 - 1.32), .5); }
      const rt = await loadFirst([p.ring]); if (tok !== loadTok) return; let rtex; if (rt) { rtex = rt.t; rtex.colorSpace = THREE.SRGBColorSpace; state.texStatus[p.id] += '+ring:' + rt.name; } else { rtex = procRing(); state.texStatus[p.id] += '+ring:procedural'; }
      const rm = new THREE.MeshBasicMaterial({ map: rtex, color: rt ? 0xe9dcc0 : 0xffffff, transparent: true, side: THREE.DoubleSide, depthWrite: false, opacity: .92 });
      ringMesh = new THREE.Mesh(rg, rm); ringMesh.rotation.x = Math.PI / 2; tilt.add(ringMesh);
    }
    layout(); o.onstate(state);
  }

  /* компоновка: планета - горизонт по центру внизу (симметрия), на телефоне крупнее */
  function layout() {
    const W = innerWidth, H = innerHeight, m = small(), d = 10, hw = 2 * d * Math.tan(cam.fov * Math.PI / 360), wpp = hw / H, p = byId(state.planet);
    let Rpx = m ? Math.max(W * 1.05, 420) : Math.min(Math.max(W * .62, 640), 1100), top = m ? H * .80 : H * .73;
    if (p.ring) { Rpx = m ? W * .30 : Math.min(W * .17, 300); top = m ? H * .80 : H * .76; }
    const R = Rpx * wpp; pg.scale.setScalar(R); pg.position.set(0, (H / 2 - (top + Rpx)) * wpp, 0);
  }
  /* пост-обработка: bloom + виньетка */
  const composer = new EffectComposer(renderer, { frameBufferType: THREE.HalfFloatType });
  composer.addPass(new RenderPass(scene, cam));
  const bloom = new BloomEffect({ intensity: .85, luminanceThreshold: .55, luminanceSmoothing: .2, mipmapBlur: true, radius: .72 });
  const vig = new VignetteEffect({ offset: .28, darkness: .62 });
  composer.addPass(new EffectPass(cam, bloom, vig));

  function resize() {
    const W = innerWidth, H = innerHeight; dprCap = small() ? 1 : 1.5; renderer.setPixelRatio(Math.min(devicePixelRatio || 1, dprCap)); renderer.setSize(W, H, false); composer.setSize(W, H, false);
    cam.aspect = W / H; cam.updateProjectionMatrix(); const dpr = renderer.getPixelRatio(), bw = Math.round(W * dpr), bh = Math.round(H * dpr);
    nebRT.setSize(Math.max(64, Math.round(bw / (small() ? 3 : 4))), Math.max(48, Math.round(bh / (small() ? 3 : 4)))); nebMat.uniforms.uRes.value.set(nebRT.width, nebRT.height); lastNeb = -1e9;
    compMat.uniforms.uRes.value.set(bw, bh); starMat.uniforms.uRes.value.set(bw, bh); starMat.uniforms.uDpr.value = dpr * (small() ? .55 : 1); layout();
  }
  let lastNeb = -1e9, t0 = performance.now(), last = 0, fpsN = 0, fpsT = 0; state.fps = 0;
  function applyLevel() { const l = state.level; bloom.intensity = l === 'high' ? 1.5 : l === 'off' ? 0 : .85; state.paused = l === 'off' && false; }
  function frame(now, force) {
    const T = (now - t0) / 1000;
    if (force || now - lastNeb > (small() ? 400 : 250)) { renderer.setRenderTarget(nebRT); renderer.render(nebScene, cam); renderer.setRenderTarget(null); nebMat.uniforms.uT.value = reduce ? 40 : T + 40; lastNeb = now; }
    state.px += (state.tx - state.px) * .04; state.py += (state.ty - state.py) * .04;
    compMat.uniforms.uPar.value.set(state.px * .012, state.py * .012); compMat.uniforms.uExp.value = .34 + .03 * Math.sin(T * .12);
    starMat.uniforms.uPar.value.set(state.px * .02, state.py * .02); starMat.uniforms.uRa.value = reduce ? 0 : T * .00035; starMat.uniforms.uTime.value = reduce ? 0 : T;
    if (body) { body.rotation.y = reduce ? 1.1 : T * .02 + 1.1; if (atmo) atmo.rotation.y = body.rotation.y; }
    pg.position.x = state.px * .0 + 0; sun.position.x = -4 + state.px * .6;
    composer.render();
  }
  function loop(now) { if (!state.run) return; requestAnimationFrame(loop); if (now - last < (small() ? 33 : 16)) return; last = now; fpsN++; if (!fpsT) fpsT = now; if (now - fpsT >= 1000) { state.fps = fpsN; fpsN = 0; fpsT = now; } try { frame(now, false); } catch (e) { /* кадр пропущен */ } }
  addEventListener('pointermove', (e) => { state.tx = (e.clientX / innerWidth - .5) * 2; state.ty = -(e.clientY / innerHeight - .5) * 2; }, { passive: true });
  let rt; addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { resize(); frame(performance.now(), true); }, 120); });
  document.addEventListener('visibilitychange', () => { if (document.hidden) state.run = false; else if (!state.run && state.level !== 'off' && !reduce) { state.run = true; requestAnimationFrame(loop); } });
  resize(); applyLevel(); await setPlanet(state.planet); frame(performance.now(), true);
  if (!reduce && state.level !== 'off') requestAnimationFrame(loop); else state.run = false;
  const api = {
    state, setPlanet,
    setLevel(l) { state.level = l; lsSet(KEYQ, l); applyLevel(); if (l === 'off') { state.run = false; frame(performance.now(), true); } else if (!state.run && !reduce) { state.run = true; requestAnimationFrame(loop); } },
    snapshot() { frame(performance.now(), true); }
  };
  window.__noxWowSpace = api;
  return api;
}
