/* NOX · кнопка «Транслировать» в пульте (Presentation API / Remote Playback / второй экран / полный экран). */
(() => {
  const mount = () => {
    const pan = document.querySelector('#nxpult .nxpu-pan'); if (!pan || pan.querySelector('[data-act=cast]') || !window.NOXactions) return !!pan && !window.NOXactions ? false : !!pan;
    const row = document.createElement('div'); row.className = 'nxpu-row';
    row.innerHTML = '<button type="button" data-act="cast">Транслировать</button><button type="button" data-act="second">Второй экран</button><button type="button" data-act="full">Полный экран</button><button type="button" data-act="focus">Концентрация</button>';
    const A = window.NOXactions; row.addEventListener('click', (e) => { const b = e.target.closest('[data-act]'); if (!b) return; ({ cast: A.cast, second: A.second, full: A.full, focus: () => A.focus(!document.documentElement.hasAttribute('data-nox-focus')) })[b.dataset.act](); });
    const vr = document.createElement('div'); vr.className = 'nxpu-row'; vr.innerHTML = '<span style="font-size:10px;letter-spacing:.12em;text-transform:uppercase">Громкость</span><button type="button" data-v="-1">−</button><button type="button" data-v="1">+</button>';
    vr.addEventListener('click', (e) => { const b = e.target.closest('[data-v]'); if (b) A.vol(parseFloat(localStorage.getItem('nox.volume') || '1') + .1 * +b.dataset.v); });
    pan.insertBefore(vr, pan.querySelector('.nxpu-sens')); pan.insertBefore(row, vr); return true;
  };
  let n = 0; const t = setInterval(() => { if (mount() || ++n > 40) clearInterval(t); }, 300);
})();
