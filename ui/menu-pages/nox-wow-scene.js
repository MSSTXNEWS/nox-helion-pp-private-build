/* NOX HELION WOW 01-40 · original local Three.js scene controller.
 * Runs only in MAX; never owns navigation, native bridge, telemetry or actions.
 * Source: bundled ui/menu-pages/three.min.js (Three.js, MIT).
 */
export function mountNoxWow(canvas, THREE, host=window) {
  if (!canvas || !THREE?.WebGLRenderer) return null;
  let renderer, scene, camera, points, geometry, material, observer, raf=0, ended=false;
  const doc=canvas.ownerDocument, stage=canvas.parentElement;
  const reduce=host.matchMedia?.('(prefers-reduced-motion: reduce)');
  const allowed=()=>!ended && !reduce?.matches && doc.visibilityState!=='hidden' &&
    doc.body?.dataset.fx==='MAX' && !host.navigator?.connection?.saveData;
  const clock=host.performance?.now?.bind(host.performance) || (()=>0);
  try {
    renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:false,powerPreference:'low-power'});
    renderer.setPixelRatio(Math.min(host.devicePixelRatio||1,1.5));
    scene=new THREE.Scene();
    camera=new THREE.PerspectiveCamera(52,1,.1,100);
    camera.position.z=9;
    const count=96, data=new Float32Array(count*3);
    let seed=0x4e4f5821;
    const rand=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
    for(let i=0;i<count;i++){
      const theta=rand()*Math.PI*2, radius=2.4+rand()*3.3;
      data[i*3]=Math.cos(theta)*radius;
      data[i*3+1]=Math.sin(theta)*radius*.58;
      data[i*3+2]=(rand()-.5)*3;
    }
    geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(data,3));
    material=new THREE.PointsMaterial({color:0xb8eaff,size:.045,transparent:true,opacity:.74,depthWrite:false});
    points=new THREE.Points(geometry,material);
    scene.add(points);
  } catch {
    try{renderer?.dispose();renderer?.forceContextLoss?.();}catch{}
    geometry?.dispose();material?.dispose();
    return null;
  }
  let previous=0;
  function resize(){
    if(ended)return;
    const rect=stage?.getBoundingClientRect?.();
    const width=Math.max(1,Math.floor(rect?.width||canvas.clientWidth||1));
    const height=Math.max(1,Math.floor(rect?.height||canvas.clientHeight||1));
    renderer.setSize(width,height,false);
    camera.aspect=width/height;camera.updateProjectionMatrix();
  }
  function tick(now){
    raf=0;
    if(!allowed())return;
    if(now-previous>=33){
      previous=now;
      points.rotation.z=now*.000013;
      points.rotation.y=Math.sin(now*.00012)*.12;
      renderer.render(scene,camera);
    }
    raf=host.requestAnimationFrame(tick);
  }
  function sync(){
    if(raf){host.cancelAnimationFrame(raf);raf=0;}
    canvas.hidden=!allowed();
    if(!canvas.hidden){
      resize();previous=clock()-34;
      if(typeof host.requestAnimationFrame==='function')raf=host.requestAnimationFrame(tick);
    }
  }
  function dispose(){
    if(ended)return;
    ended=true;
    if(raf)host.cancelAnimationFrame(raf);
    observer?.disconnect();
    resizeObserver?.disconnect();
    doc.removeEventListener('visibilitychange',sync);
    host.removeEventListener('resize',sync);
    host.removeEventListener('pagehide',dispose);
    reduce?.removeEventListener?.('change',sync);
    geometry.dispose();material.dispose();
    renderer.dispose();
    try{renderer.forceContextLoss();}catch{}
  }
  let resizeObserver=null;
  if(host.MutationObserver){
    observer=new host.MutationObserver(sync);
    observer.observe(doc.body,{attributes:true,attributeFilter:['data-fx']});
  }
  if(host.ResizeObserver && stage){
    resizeObserver=new host.ResizeObserver(resize);resizeObserver.observe(stage);
  }
  doc.addEventListener('visibilitychange',sync);
  host.addEventListener('resize',sync,{passive:true});
  host.addEventListener('pagehide',dispose);
  reduce?.addEventListener?.('change',sync);
  sync();
  return {dispose,sync};
}
