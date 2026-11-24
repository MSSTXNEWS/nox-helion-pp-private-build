import { createFrame, createFrameCornersSettings } from '@arwes/frames';
export function hud(sel) {
  document.querySelectorAll(sel).forEach((el) => {
    if (el.__hud) return; el.__hud = 1;
    try {
      if (getComputedStyle(el).position === 'static') el.style.position = 'relative';
      el.style.setProperty('--arwes-frames-bg-color', 'transparent'); el.style.setProperty('--arwes-frames-line-color', 'rgba(255,138,76,.55)'); el.style.setProperty('--arwes-frames-deco-color', 'rgba(255,190,120,.9)');
    } catch (e) { console.warn('[nox-hud] style', e); }
    try {
      const NS = 'http://www.w3.org/2000/svg';
      const svg = document.createElementNS(NS, 'svg');
      svg.setAttribute('class', 'nox-hud-svg');
      svg.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:visible;z-index:0';
      el.insertBefore(svg, el.firstChild);
      createFrame(svg, createFrameCornersSettings({ padding: 1, strokeWidth: 1, cornerLength: 12, styled: true }));
    } catch (e) { console.warn('[nox-hud] createFrame failed', e); }
    el.classList.add('nox-hud');
  });
}
