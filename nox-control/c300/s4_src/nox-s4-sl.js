/* S4 · кнопки шапки действий (.ph .acts) на sl-button / sl-button-group + sl-tooltip. Исходные кнопки остаются в DOM (скрыты) и получают клик: обработчики страниц не теряются. Состояние (текст, aria-pressed, disabled) зеркалится. */
(function () {
  const map = new WeakMap();
  const lbl = (b) => [...b.childNodes].filter((n) => n.nodeType === 3 || (n.nodeType === 1 && n.tagName !== 'SL-ICON')).map((n) => n.textContent).join('').replace(/\s+/g, ' ').trim();
  function sync(b, s) {
    const l = lbl(b), ic = b.querySelector('sl-icon'); const lab = s.querySelector('.s4sl-l'); if (lab && lab.textContent !== l) lab.textContent = l;
    s.setAttribute('variant', b.getAttribute('aria-pressed') === 'true' ? 'primary' : (b.style.color || b.classList.contains('danger') ? 'danger' : 'default'));
    b.disabled ? s.setAttribute('disabled', '') : s.removeAttribute('disabled');
    if (ic) { const mine = s.querySelector('sl-icon'); if (mine && mine.getAttribute('name') !== ic.getAttribute('name')) mine.setAttribute('name', ic.getAttribute('name')); }
  }
  function conv(b) {
    if (map.has(b) || b.closest('sl-dialog,.s4dlg') || b.id === 'dSave' || b.type === 'submit') return null;
    const ic = b.querySelector('sl-icon'), l = lbl(b), s = document.createElement('sl-button'); s.size = 'large'; s.className = 's4sl'; s.dataset.for = b.id || '';
    s.innerHTML = (ic ? '<sl-icon slot="prefix" library="' + (ic.getAttribute('library') || 'tabler') + '" name="' + ic.getAttribute('name') + '"></sl-icon>' : '') + '<span class="s4sl-l">' + l.replace(/[<>&]/g, '') + '</span>';
    s.addEventListener('click', (e) => { e.stopPropagation(); b.click(); setTimeout(() => sync(b, s), 50); });
    const tip = document.createElement('sl-tooltip'); tip.content = b.title || b.getAttribute('aria-label') || l || 'Действие'; tip.appendChild(s);
    map.set(b, s); sync(b, s); new MutationObserver(() => sync(b, s)).observe(b, { attributes: true, childList: true, characterData: true, subtree: true });
    b.style.display = 'none'; return tip;
  }
  function run() {
    document.querySelectorAll('.ph .acts').forEach((acts) => {
      const segs = [...acts.querySelectorAll('.seg')];
      segs.forEach((seg) => { const bs = [...seg.querySelectorAll(':scope > button')].filter((b) => !map.has(b)); if (!bs.length) return; const g = document.createElement('sl-button-group'); g.className = 's4sg'; bs.forEach((b) => { const t = conv(b); t && g.appendChild(t); }); if (g.children.length) { seg.before(g); seg.style.display = 'none'; } });
      [...acts.querySelectorAll(':scope > button')].filter((b) => !map.has(b)).forEach((b) => { const t = conv(b); if (t) b.before(t); });
    });
  }
  const go = () => { try { run(); } catch (e) { /* */ } };
  document.addEventListener('DOMContentLoaded', () => { setTimeout(go, 700); setTimeout(go, 2500); new MutationObserver(() => { clearTimeout(go.t); go.t = setTimeout(go, 400); }).observe(document.body, { childList: true, subtree: true }); });
})();
