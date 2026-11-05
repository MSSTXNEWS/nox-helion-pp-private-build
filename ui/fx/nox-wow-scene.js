/* Lightweight Three.js comet field. Call mountNoxWow(canvas). */
export function mountNoxWow(canvas) {
  if (!window.THREE || !canvas) return null;
  const THREE = window.THREE;
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
  camera.position.z = 8;
  const group = new THREE.Group();
  scene.add(group);
  const geo = new THREE.SphereGeometry(0.06, 8, 8);
  const mat = new THREE.MeshBasicMaterial({ color: 0xb8f4ff });
  const comets = [];
  for (let i = 0; i < 12; i++) {
    const m = new THREE.Mesh(geo, mat);
    m.position.set((Math.random() - 0.5) * 10, (Math.random() - 0.5) * 6, (Math.random() - 0.5) * 4);
    m.userData.v = 0.01 + Math.random() * 0.03;
    group.add(m);
    comets.push(m);
  }
  function resize() {
    const w = canvas.clientWidth || 640, h = canvas.clientHeight || 360;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  function frame() {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    for (const c of comets) {
      c.position.x += c.userData.v;
      if (c.position.x > 6) c.position.x = -6;
    }
    renderer.render(scene, camera);
    requestAnimationFrame(frame);
  }
  resize();
  addEventListener('resize', resize);
  frame();
  return { renderer, scene };
}
