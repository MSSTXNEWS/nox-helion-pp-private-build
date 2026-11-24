import ForceGraph3D from '3d-force-graph';
export function graph3d(el, data, opt = {}) {
  const w = el.clientWidth || 600, h = el.clientHeight || 400;
  const g = ForceGraph3D({ controlType: 'orbit' })(el).width(w).height(h).backgroundColor('rgba(0,0,0,0)').graphData(data)
    .nodeColor((n) => n.color || '#ff8a4c').nodeVal((n) => n.val || 1).nodeLabel((n) => n.label || n.id).nodeOpacity(0.9)
    .linkColor(() => 'rgba(255,150,100,.28)').linkOpacity(0.5).linkWidth(0.4).showNavInfo(false).warmupTicks(40).cooldownTicks(120);
  g.cameraPosition({ z: opt.z || 320 });
  const ro = new ResizeObserver(() => g.width(el.clientWidth).height(el.clientHeight)); ro.observe(el);
  return { g, destroy() { ro.disconnect(); try { g._destructor && g._destructor(); } catch (e) { /* */ } } };
}
