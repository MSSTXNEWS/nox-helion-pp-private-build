import { createFrame, createFrameCornersSettings } from '@arwes/frames';
export function hud(sel) {
  document.querySelectorAll(sel).forEach((el) => {
    if (el.__hud) return; el.__hud = 1; try {
      if (getComputedStyle(el).position === 'static') el.style.position = 'relative';
      el.style.setProperty('--arwes-frames-bg-color', 'transparent'); el.style.setProperty('--arwes-frames-line-color', 'rgba(255,138,76,.55)'); el.style.setProperty('--arwes-frames-deco-color', 'rgba(255,190,120,.9)');
      createFrame(el, createFrameCornersSettings({ padding: 1, strokeWidth: 1, cornerLength: 12, styled: true }));
      el.classList.add('nox-hud');
    } catch (e) { /* рамка необязательна */ }
  });
}
