/* S4 · Мозг: капля-эмоция (Paper Shaders metaballs), сердцебиение (Tone.js, пульс от загрузки GPU), llm-viz в тёмной стеклянной рамке. Данные: /brain/selffeel и /api/nox-live. */
(function () {
  const $ = (s) => document.querySelector(s);
  const EMC = { joy: '#f2c14e', радость: '#f2c14e', calm: '#6aa9d8', спокойствие: '#6aa9d8', interest: '#8fc28a', интерес: '#8fc28a', fear: '#b48ad8', тревога: '#b48ad8', anger: '#d64630', злость: '#d64630', sadness: '#5a78b8', грусть: '#5a78b8', trust: '#e0954a', доверие: '#e0954a' };
  const hex = (h) => { const n = parseInt(h.slice(1), 16); return [(n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255, 1]; };
  let heart = null;
  /* капля */
  async function drop() {
    const feel = $('.nbx-feel'); if (!feel || feel.dataset.s4) return; feel.dataset.s4 = 1;
    const P = window.NOX_paper_design_shaders; if (!P || !P.ShaderMount) return;
    let top = null, lvl = .5; try { const j = await (await fetch('/brain/selffeel', { cache: 'no-store' })).json(), d = j.sources && j.sources.selfstate && j.sources.selfstate.data || {}; const k = Object.keys(d).filter((x) => typeof d[x] === 'number').sort((a, b) => d[b] - d[a])[0]; if (k) { top = k; lvl = d[k]; } } catch (e) { /* */ }
    const box = document.createElement('div'); box.className = 's4drop'; box.setAttribute('aria-hidden', 'true'); const orb = feel.querySelector('.nbx-orb'); if (orb) { orb.style.display = 'none'; orb.before(box); } else feel.prepend(box);
    const c = hex(EMC[top] || '#e0654a'), c2 = hex('#ffb070');
    try {
      const u = {}; Object.entries(P.defaultObjectSizing || {}).forEach(([k, v]) => { u['u_' + k] = k === 'fit' ? 0 : v; });
      Object.assign(u, { u_colors: [c, c2, hex('#7a2a20')], u_colorsCount: 3, u_colorBack: [0.03, 0.02, 0.02, 1], u_count: 10, u_size: .83, u_scale: 1, u_worldWidth: 0, u_worldHeight: 0 });
      window.__s4drop = new P.ShaderMount(box, P.metaballsFragmentShader, u, { alpha: true, premultipliedAlpha: false }, .6 + lvl);
    } catch (e) { box.remove(); if (orb) orb.style.display = ''; }
  }
  /* сердцебиение */
  async function beat(btn) {
    if (heart) { heart.stop(); heart = null; btn.setAttribute('aria-pressed', 'false'); btn.lastChild.textContent = 'Сердцебиение: выкл'; return; }
    if (!window.NOX_tone) await new Promise((ok, no) => { const s = document.createElement('script'); s.src = './vendor/tone/tone.iife.js'; s.onload = ok; s.onerror = no; document.head.appendChild(s); }).catch(() => 0);
    const T = window.NOX_tone; if (!T) { btn.lastChild.textContent = 'Tone недоступен'; return; }
    await T.start(); const syn = new T.MembraneSynth({ pitchDecay: .03, octaves: 4, volume: -22 }).toDestination(); let bpm = 60, alive = true, t1 = 0, t2 = 0;
    const poll = async () => { try { const j = await (await fetch('/api/nox-live', { cache: 'no-store' })).json(); const u = j.gpu && (j.gpu.util_pct != null ? j.gpu.util_pct : j.gpu.gpu_util_pct); if (typeof u === 'number') bpm = 50 + u * .7; } catch (e) { /* */ } };
    await poll(); const pi = setInterval(poll, 5000);
    const tick = () => { if (!alive) return; syn.triggerAttackRelease('C1', '16n'); document.body.classList.add('s4beat'); t2 = setTimeout(() => { syn.triggerAttackRelease('A0', '16n'); document.body.classList.remove('s4beat'); }, 170); t1 = setTimeout(tick, 60000 / bpm); };
    tick(); heart = { stop() { alive = false; clearTimeout(t1); clearTimeout(t2); clearInterval(pi); syn.dispose(); document.body.classList.remove('s4beat'); } };
    btn.setAttribute('aria-pressed', 'true'); btn.lastChild.textContent = 'Сердцебиение: вкл';
  }
  function init() {
    const acts = $('.ph .acts'); if (acts && !$('#s4hb')) { const b = document.createElement('button'); b.type = 'button'; b.id = 's4hb'; b.className = 'tag'; b.setAttribute('aria-pressed', 'false'); b.innerHTML = '<sl-icon library="tabler" name="heartbeat"></sl-icon><span>Сердцебиение: выкл</span>'; b.onclick = () => beat(b); acts.prepend(b); }
    drop();
  }
  document.addEventListener('DOMContentLoaded', () => { init(); new MutationObserver(() => { if ($('.nbx-feel') && !$('.nbx-feel').dataset.s4) drop(); }).observe(document.body, { childList: true, subtree: true }); });
})();
