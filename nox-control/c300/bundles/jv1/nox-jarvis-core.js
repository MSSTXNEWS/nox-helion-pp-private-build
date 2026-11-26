/* NOX · JARVIS: центральная сфера (three): шейдерная сфера, орбитальные кольца со спутниками, частицы, голографическая платформа с лучом. Реагирует на NOXjv.mic.level и печать. */
import * as THREE from 'three';
export function core(cv, opt) {
  const J = window.NOXjv, SM = J.SM, RM = J.RM;
  const R = new THREE.WebGLRenderer({ canvas: cv, antialias: !SM, alpha: true }); R.setPixelRatio(Math.min(devicePixelRatio, SM ? 1.5 : 2)); R.setClearColor(0, 0);
  const S = new THREE.Scene(), cam = new THREE.PerspectiveCamera(38, 1, .1, 60); cam.position.set(0, 1.1, 10.5); cam.lookAt(0, -.15, 0);
  const U = { t: { value: 0 }, a: { value: 0 }, c: { value: new THREE.Color(0, .84, 1) } };
  const NZ = 'float h(vec3 p){p=fract(p*.3183099+.1);p*=17.;return fract(p.x*p.y*p.z*(p.x+p.y+p.z));}float n3(vec3 x){vec3 i=floor(x),f=fract(x);f=f*f*(3.-2.*f);return mix(mix(mix(h(i),h(i+vec3(1,0,0)),f.x),mix(h(i+vec3(0,1,0)),h(i+vec3(1,1,0)),f.x),f.y),mix(mix(h(i+vec3(0,0,1)),h(i+vec3(1,0,1)),f.x),mix(h(i+vec3(0,1,1)),h(i+vec3(1,1,1)),f.x),f.y),f.z);}';
  const G = new THREE.Group(); G.position.y = .55; S.add(G);
  const ball = new THREE.Mesh(new THREE.IcosahedronGeometry(1.25, SM ? 24 : 44), new THREE.ShaderMaterial({ uniforms: U, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: NZ + 'uniform float t,a;varying vec3 vN,vP,vV;void main(){vec3 p=position;p*=1.+n3(p*1.8+t*.3)*.07+a*n3(p*3.+t*1.8)*.16;vP=p;vN=normalize(normalMatrix*normal);vec4 mv=modelViewMatrix*vec4(p,1.);vV=normalize(-mv.xyz);gl_Position=projectionMatrix*mv;}',
    fragmentShader: NZ + 'uniform float t,a;uniform vec3 c;varying vec3 vN,vP,vV;void main(){float f=pow(1.-max(dot(normalize(vN),normalize(vV)),0.),2.);float la=smoothstep(.93,1.,abs(sin(vP.y*14.+t*.5)));float lo=smoothstep(.94,1.,abs(sin(atan(vP.z,vP.x)*10.-t*.35)));float cl=n3(vP*3.5+t*.25);vec3 col=c*(.12+f*1.4+(la+lo)*.45+cl*.22)+vec3(.5,.9,1.)*pow(f,5.)*(.4+a);gl_FragColor=vec4(col,clamp(.25+f+(la+lo)*.3,0.,1.));}' }));
  G.add(ball);
  const ringMat = (o) => new THREE.MeshBasicMaterial({ color: 0x00d6ff, transparent: true, opacity: o, blending: THREE.AdditiveBlending, depthWrite: false });
  const rings = [], sats = [];
  [[2.1, .014, .2, .1, .9], [2.6, .01, -.5, .6, .6], [3.1, .016, .9, -.3, .5], [1.75, .008, 1.2, .2, .7]].forEach(([r, w, rx, rz, op], i) => { const m = new THREE.Mesh(new THREE.TorusGeometry(r, w, 6, SM ? 96 : 200), ringMat(op)); m.rotation.set(rx, 0, rz); m.userData = { sp: (i % 2 ? -1 : 1) * (.12 + i * .05) }; G.add(m); rings.push(m);
    const s = new THREE.Mesh(new THREE.SphereGeometry(.05 + i * .01, 10, 10), ringMat(1)); s.userData = { r, ph: i * 1.7, sp: .5 + i * .2, par: m }; m.add(s); sats.push(s); });
  const N = SM ? 700 : 2200, pg = new THREE.BufferGeometry(), pp = new Float32Array(N * 3), ps = new Float32Array(N);
  for (let i = 0; i < N; i++) { const u = Math.random() * 2 - 1, th = Math.random() * 6.283, r = Math.sqrt(1 - u * u), k = 1.6 + Math.random() * 2.2; pp.set([r * Math.cos(th) * k, u * k * .8, r * Math.sin(th) * k], i * 3); ps[i] = Math.random(); }
  pg.setAttribute('position', new THREE.BufferAttribute(pp, 3)); pg.setAttribute('s', new THREE.BufferAttribute(ps, 1));
  const pts = new THREE.Points(pg, new THREE.ShaderMaterial({ uniforms: U, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: 'uniform float t,a;attribute float s;varying float v;void main(){vec3 p=position*(1.+a*.12*s);float c=cos(t*.1*(.3+s)),n=sin(t*.1*(.3+s));p.xz=mat2(c,-n,n,c)*p.xz;p.y+=sin(t*.5+s*20.)*.06;vec4 mv=modelViewMatrix*vec4(p,1.);gl_PointSize=(1.4+s*2.4)*(9./-mv.z);v=.2+s*.8;gl_Position=projectionMatrix*mv;}',
    fragmentShader: 'varying float v;void main(){float d=length(gl_PointCoord-.5);if(d>.5)discard;gl_FragColor=vec4(.2,.85,1.,(1.-d*2.)*v*.9);}' })); G.add(pts);
  /* платформа */
  const P = new THREE.Group(); P.position.y = -2.1; S.add(P);
  const disc = new THREE.Mesh(new THREE.CircleGeometry(3.6, 64), new THREE.ShaderMaterial({ uniforms: U, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    vertexShader: 'varying vec2 u;void main(){u=position.xy;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
    fragmentShader: 'uniform float t,a;varying vec2 u;void main(){float r=length(u)/3.6;float g=smoothstep(.02,0.,abs(fract(r*9.-t*.15)-.5)-.47)*.5;float sp=smoothstep(.02,0.,abs(fract(atan(u.y,u.x)*3.1831*3.+t*.05)-.5)-.48)*.35*r;float core=exp(-r*3.2)*(.9+a);gl_FragColor=vec4(vec3(0.,.8,1.)*(core+g*(1.-r)+sp*(1.-r)),(1.-r)*.95);}' }));
  disc.rotation.x = -Math.PI / 2; P.add(disc);
  [[3.5, .02, .8], [2.7, .015, .6], [1.5, .02, .9]].forEach(([r, w, op], i) => { const m = new THREE.Mesh(new THREE.TorusGeometry(r, w, 4, 128), ringMat(op)); m.rotation.x = Math.PI / 2; m.userData = { sp: i % 2 ? -.3 : .2 }; P.add(m); rings.push(m); });
  const beam = new THREE.Mesh(new THREE.CylinderGeometry(1.1, 1.9, 2.5, 48, 1, true), new THREE.ShaderMaterial({ uniforms: U, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    vertexShader: 'varying float y;void main(){y=position.y;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}', fragmentShader: 'uniform float a;varying float y;void main(){float k=smoothstep(1.25,-1.25,y);gl_FragColor=vec4(0.,.8,1.,k*(.16+a*.2));}' }));
  beam.position.y = 1.3; P.add(beam);
  function size() { const r = cv.getBoundingClientRect(); R.setSize(r.width, r.height, false); cam.aspect = r.width / r.height; cam.fov = r.width / r.height < 1 ? 50 : 38; cam.updateProjectionMatrix(); }
  size(); addEventListener('resize', size);
  let T = 0, last = performance.now(), amp = 0, imp = 0; opt && opt.input && opt.input.addEventListener('input', () => { imp = Math.min(1, imp + .4); });
  J.pulse = (v) => { imp = Math.max(imp, v); };
  function frame(dt) { T += dt; U.t.value = T; imp *= Math.pow(.03, dt); const lv = Math.max(J.mic.level || 0, imp); amp += ((lv + .07 + .04 * Math.sin(T * 1.4)) - amp) * Math.min(1, dt * 8); U.a.value = amp;
    ball.rotation.y = T * .15; rings.forEach((m) => { m.rotation.z += (m.userData.sp || 0) * dt; }); sats.forEach((s) => { const a = T * s.userData.sp + s.userData.ph; s.position.set(Math.cos(a) * s.userData.r, Math.sin(a) * s.userData.r, 0); }); pts.rotation.y = T * .03; G.position.y = .55 + Math.sin(T * 1.1) * .06; R.render(S, cam); }
  let vis = true; document.addEventListener('visibilitychange', () => { vis = !document.hidden; last = performance.now(); if (vis) loop(); });
  function loop() { if (!vis || RM) return; const n = performance.now(), dt = Math.min((n - last) / 1000, .05); last = n; frame(dt); requestAnimationFrame(loop); }
  frame(0); if (RM) frame(1); else loop();
  return { frame };
}
