/**
 * NOX HELION · HOLO MOTION V7
 * Opt-in visuals on existing DOM, never generates telemetry or sends commands.
 * Usage: import { mountNoxHoloMotion } from './nox-holo-motion-v7.mjs';
 * const stop = mountNoxHoloMotion(document.querySelector('#nox-root'));
 * Add class .nox-holo-instrument to existing HUD instruments and
 * .nox-holo-core/.nox-holo-rim/.nox-holo-node/.nox-holo-link to SVG parts.
 * Stop removes installed listeners/attributes. Live state is explicit.
 */
export function mountNoxHoloMotion(root, {isLive = () => false, isBusy = () => false} = {}) {
  if (!(root instanceof Element)) throw new TypeError('NOX HUD root element required');
  const media = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)');
  const update = () => {
    if (!root.isConnected) return;
    const hidden = globalThis.document?.visibilityState === 'hidden';
    root.dataset.noxMotion = hidden || media?.matches ? 'off' : 'on';
    const state = root.querySelector('[data-nox-holo-state]');
    if (state) state.dataset.noxHoloState = isBusy() ? 'busy' : 'idle';
    const status = root.querySelectorAll('.nox-holo-live');
    for (const el of status) el.dataset.live = String(Boolean(isLive()));
  };
  root.classList.add('nox-holo-v7');
  const nodes = root.querySelectorAll('.nox-holo-node');
  nodes.forEach((node, i) => node.style.setProperty('--nox-delay', `-${(i % 13) * .31}s`));
  media?.addEventListener?.('change', update);
  globalThis.document?.addEventListener?.('visibilitychange', update);
  update();
  return () => {
    media?.removeEventListener?.('change', update);
    globalThis.document?.removeEventListener?.('visibilitychange', update);
    root.classList.remove('nox-holo-v7');
    delete root.dataset.noxMotion;
    nodes.forEach(n => n.style.removeProperty('--nox-delay'));
  };
}
