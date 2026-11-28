/* NOX · BlackSun: единое лёгкое «чёрное солнце» (canvas 2D, без WebGL). Чёрный диск, тонкий раскалённый обод, ореол пересвета,
   мерцающая корона, дыхание обода, редкая вспышка по ободу. Состояние: один общий опрос /api/nox-live на страницу.
   API: window.NoxBS.mount(host,{size}) -> {destroy}; window.NoxBS.state. ECO/reduced-motion: статичное свечение. */
(() => {
  if (window.NoxBS) return;
  const S = { busy: false, train: false, night: false, offline: false, err: false, bt: 0 };
  const insts = new Set(); let raf = 0, lastT = 0, polling = false;
  const eco = () => document.documentElement.dataset.q === "eco" || (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  const nightNow = () => { const h = new Date().getHours(); return h >= 23 || h < 6; };
  const apply = (j, ok) => { S.offline = !ok; S.err = !!(j && (j.error || j.status === "error")); S.night = nightNow();
    S.train = !!(j && (j.training === true || j.train_running === true || j.training_running === true || (j.training && (j.training.running === true || /TRAIN/i.test(String(j.training.status || ""))))));
    if (j && j.live_turn) S.bt = performance.now() + 3000; draw1(); };
  const poll = () => { fetch("/api/nox-live", { cache: "no-store" }).then((r) => (r.ok ? r.json() : Promise.reject())).then((j) => apply(j, true)).catch(() => apply(null, false)); };
  const startPoll = () => { if (polling) return; polling = true; poll(); setInterval(() => { if (!document.hidden) poll(); }, 8000); };
  ["nox-token", "nox-think"].forEach((n) => addEventListener(n, () => { S.bt = performance.now() + 2500; }));
  const hash = (n) => { const s = Math.sin(n * 127.1) * 43758.5453; return s - Math.floor(s); };
  const vn = (x) => { const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f); return hash(i) * (1 - u) + hash(i + 1) * u; };
  /* ---- WebGL: один общий контекст на страницу, каждый экземпляр рисуется в него и копируется drawImage ---- */
  const VS = "attribute vec2 a;varying vec2 p;void main(){p=a;gl_Position=vec4(a,0.,1.);}";
  const FS = `precision highp float;varying vec2 p;uniform float uT,uBr,uBusy,uGray,uFl,uFa,uR;
float h(vec2 q){return fract(sin(dot(q,vec2(127.1,311.7)))*43758.5453);}
float vn(vec2 q){vec2 i=floor(q),f=fract(q);f=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}
float fbm(vec2 q){float a=.5,s=0.;for(int i=0;i<4;i++){s+=a*vn(q);q=q*2.03+vec2(7.1,3.7);a*=.5;}return s;}
float ad(float a,float b){return abs(mod(a-b+3.14159,6.28318)-3.14159);}
void main(){
 float L=length(p);float R=uR;float d=(L-R)/R;float a=atan(p.y,p.x);float t=uT*(.5+.5*uBusy);
 vec3 col=vec3(0.);float al=0.;
 if(d>0.){
  float wa=a+.16*(fbm(vec2(d*2.2+3.,t*.07+a))-.5)+.05*sin(d*5.-t*.4+a*3.);
  float fib=0.;float f1=vn(vec2(wa*46.,d*.9-t*.05));float f2=vn(vec2(wa*110.+9.,d*1.7+t*.04));float f3=vn(vec2(wa*22.-4.,d*.4-t*.03));
  fib=pow(f1,2.2)*.55+pow(f2,2.6)*.4+f3*.35;
  float feather=0.;for(int i=0;i<3;i++){float fi=float(i);float ca=1.1+fi*2.35+.25*sin(t*.05+fi*2.);float da=ad(a,ca);feather+=exp(-da*da*(9.+fi*5.))*(1.5-fi*.25);}
  float asym=.55+.45*vn(vec2(a*1.3,3.));
  float ext=1.+feather*2.2;
  float fall=exp(-d*(3.1/ext))*asym;
  float inner=exp(-d*14.)*1.25;
  float I=(fall*(.25+fib*1.7)+inner)*uBr;
  col=mix(vec3(1.,.55,.16),vec3(1.,.93,.8),clamp(exp(-d*9.)*1.2,0.,1.))*I;
  col*=1.+.18*uBusy;
  al=I;
  /* протуберанцы-петли на лимбе */
  for(int i=0;i<3;i++){float fi=float(i);float pa=.55+fi*2.2+uFa*.3*step(1.5,fi);float w=.07+.03*fi;float u=(a-pa);u=mod(u+3.14159,6.28318)-3.14159;float uu=u/w;
   if(abs(uu)<1.){float amp=.5+.5*sin(t*.35+fi*2.1);float hh=R*(.05+.09*amp)*(1.-uu*uu);float rd=abs(L-R-hh);float ring=exp(-rd*rd/(R*R*.00018));col+=vec3(1.,.28,.12)*ring*(.6+.4*amp)*uBr;al+=ring*.8*uBr;}}
  float fl=uFl*exp(-ad(a,uFa)*ad(a,uFa)*60.)*exp(-d*5.);col+=vec3(1.,.8,.5)*fl;al+=fl;
 }
 /* лимб */
 float limb=exp(-pow((L-R)/(R*.018),2.));col+=vec3(1.,.72,.38)*limb*(.8+.4*uBr)*uBr+vec3(1.,.9,.75)*limb*.35*uBr;al+=limb;
 if(d<0.){
  float rr=L/R;vec3 n=vec3(p/R,sqrt(max(0.,1.-rr*rr)));float fr=pow(1.-n.z,3.);
  float ang=t*.05;float cs=cos(ang),sn=sin(ang);vec3 q=vec3(cs*n.x+sn*n.z,n.y,-sn*n.x+cs*n.z);
  float tx=fbm(q.xy*3.2+q.z*1.7);float sp=pow(vn(q.xy*9.+q.z*5.),3.);
  col=vec3(.05,.014,.006)*(tx*1.6)*uBr+vec3(.1,.03,.01)*sp*uBr*.5;
  col+=vec3(1.,.42,.12)*fr*.55*uBr+vec3(1.,.8,.5)*pow(fr,5.)*.5*uBr;
  /* волокна короны перед шаром у кромки */
  float wa2=a+.16*(fbm(vec2(rr*2.2+3.,t*.07+a))-.5);float ff=pow(vn(vec2(wa2*46.,rr*1.5-t*.05)),2.4);
  col+=vec3(1.,.6,.25)*ff*smoothstep(.55,1.,rr)*.45*uBr;
  al=1.;float e=exp(-pow((L-R)/(R*.02),2.));col+=vec3(1.,.7,.35)*e*.9*uBr;}
 float ed=smoothstep(1.,.62,L);col*=ed;al*=ed;
 float g=dot(col,vec3(.33));col=mix(col,vec3(g)*vec3(.95,.95,1.),uGray);
 al=clamp(max(al,max(col.r,max(col.g,col.b))),0.,1.);
 gl_FragColor=vec4(min(col,vec3(1.)),al);
}`;
  let GL = null, glc = null, U = null, glFail = false;
  function initGL() {
    if (GL || glFail) return !!GL;
    try { glc = document.createElement("canvas"); glc.width = 16; glc.height = 16; GL = glc.getContext("webgl", { premultipliedAlpha: true, alpha: true, antialias: false, preserveDrawingBuffer: true }); if (!GL) throw 0;
      const sh = (ty, src) => { const o = GL.createShader(ty); GL.shaderSource(o, src); GL.compileShader(o); if (!GL.getShaderParameter(o, GL.COMPILE_STATUS)) throw new Error(GL.getShaderInfoLog(o)); return o; };
      const pr = GL.createProgram(); GL.attachShader(pr, sh(GL.VERTEX_SHADER, VS)); GL.attachShader(pr, sh(GL.FRAGMENT_SHADER, FS)); GL.linkProgram(pr); if (!GL.getProgramParameter(pr, GL.LINK_STATUS)) throw 0; GL.useProgram(pr);
      const bf = GL.createBuffer(); GL.bindBuffer(GL.ARRAY_BUFFER, bf); GL.bufferData(GL.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), GL.STATIC_DRAW); const al = GL.getAttribLocation(pr, "a"); GL.enableVertexAttribArray(al); GL.vertexAttribPointer(al, 2, GL.FLOAT, false, 0, 0);
      U = {}; ["uT", "uBr", "uBusy", "uGray", "uFl", "uFa", "uR"].forEach((k) => (U[k] = GL.getUniformLocation(pr, k)));
      GL.clearColor(0, 0, 0, 0); return true; } catch (e) { GL = null; glFail = true; return false; }
  }
  function render(I, t) {
    const c = I.c, g = I.g, W = c.width; if (!W) return;
    const busy = S.busy || performance.now() < S.bt, dim = S.err ? 0.7 : S.offline || S.night ? 0.45 : 1, br = dim * (busy ? 1.25 : 1);
    const still = I.still, breath = still ? 0.92 : 0.9 + 0.1 * Math.sin((t * (busy ? 1.9 : 1) * 2 * Math.PI) / 3.2);
    if (!I.still && t > I.fl.at + 1.4) I.fl = { at: t + 10 + Math.random() * 10, a: Math.random() * 6.2832 };
    const fp = !still && t > I.fl.at && t < I.fl.at + 1.4 ? Math.sin(((t - I.fl.at) / 1.4) * Math.PI) : 0;
    if (initGL()) {
      if (glc.width !== W) { glc.width = W; glc.height = W; } GL.viewport(0, 0, W, W); GL.clear(GL.COLOR_BUFFER_BIT);
      GL.uniform1f(U.uT, t); GL.uniform1f(U.uBr, br * breath); GL.uniform1f(U.uBusy, busy ? 1 : 0); GL.uniform1f(U.uGray, S.err ? 1 : 0); GL.uniform1f(U.uFl, fp * 0.9); GL.uniform1f(U.uFa, I.fl.a); GL.uniform1f(U.uR, 0.379);
      GL.drawArrays(GL.TRIANGLE_STRIP, 0, 4); g.clearRect(0, 0, W, W); g.drawImage(glc, 0, 0); return;
    }
    /* запасной вариант: canvas2D, сотни тонких штрихов */
    const cx = W / 2, r = I.size * 0.36 * I.dpr; g.clearRect(0, 0, W, W); g.globalCompositeOperation = "lighter"; g.lineCap = "round";
    const gray = S.err, N = I.size > 60 ? 360 : 140;
    for (let k = 0; k < N; k++) { const a0 = hash(k * 7.3) * 6.2832, wob = (vn(a0 * 3 + t * 0.15) - 0.5) * 0.25, a = a0 + wob; let ext = 1; [1.1, 3.45, 5.8].forEach((c0) => { const da = Math.abs(((a - c0 + 9.4248) % 6.2832) - 3.1416); ext += Math.exp(-da * da * 10) * 2.2; });
      const len = r * (0.15 + 0.9 * hash(k * 1.9) * hash(k * 3.3 + 1)) * ext * (0.7 + 0.3 * vn(k + t * 0.3)), x0 = cx + Math.cos(a) * r, y0 = cx + Math.sin(a) * r, x1 = cx + Math.cos(a) * (r + len), y1 = cx + Math.sin(a) * (r + len);
      const gr = g.createLinearGradient(x0, y0, x1, y1); const q = 0.35 * br; gr.addColorStop(0, gray ? `rgba(220,220,225,${q})` : `rgba(255,225,170,${q})`); gr.addColorStop(1, "rgba(255,120,30,0)"); g.strokeStyle = gr; g.lineWidth = Math.max(0.5, I.dpr * 0.7); g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke(); }
    g.globalCompositeOperation = "source-over"; g.fillStyle = "#000"; g.beginPath(); g.arc(cx, cx, r, 0, 6.2832); g.fill();
    g.strokeStyle = gray ? "rgba(190,190,196,.9)" : `rgba(255,200,120,${Math.min(1, 0.9 * br)})`; g.lineWidth = Math.max(1, r * 0.03); g.beginPath(); g.arc(cx, cx, r, 0, 6.2832); g.stroke();
  }
  function draw1() { insts.forEach((I) => { if (I.still || !raf) render(I, I.still ? 5 : performance.now() / 1000); }); }
  function loop(ts) { raf = requestAnimationFrame(loop); if (ts - lastT < 33) return; lastT = ts; const t = ts / 1000; insts.forEach((I) => { if (I.vis) render(I, t); }); }
  function mount(host, o) {
    o = o || {}; const I = { host, size: 0, dpr: 1, vis: true, still: eco(), fl: { at: 4 + Math.random() * 8, a: Math.random() * 6.2832 } };
    const c = document.createElement("canvas"); c.setAttribute("aria-hidden", "true"); c.style.cssText = "position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);pointer-events:none;max-width:none"; I.c = c; I.g = c.getContext("2d");
    if (getComputedStyle(host).position === "static") host.style.position = "relative"; host.appendChild(c);
    const fit = () => { const s = Math.max(24, Math.min(o.max || 200, o.size || host.clientWidth || 48)); I.size = s; I.dpr = Math.min(2, window.devicePixelRatio || 1); const side = Math.round(s * 1.9); c.style.width = side + "px"; c.style.height = side + "px"; c.width = Math.round(side * I.dpr); c.height = c.width; render(I, I.still ? 5 : performance.now() / 1000); };
    const idle = window.requestIdleCallback || ((f) => setTimeout(f, 60)); I.dead = false; idle(() => { if (!I.dead) fit(); }, { timeout: 400 }); const ro = window.ResizeObserver ? new ResizeObserver(fit) : null; ro && ro.observe(host);
    const io = window.IntersectionObserver ? new IntersectionObserver((e) => { I.vis = e[0].isIntersecting; }) : null; io && io.observe(host);
    const mo = new MutationObserver(() => { I.still = eco(); fit(); }); mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-q"] });
    insts.add(I); startPoll(); if (!raf && !I.still) raf = requestAnimationFrame(loop);
    if (!I.still && !raf) raf = requestAnimationFrame(loop);
    return { destroy() { I.dead = true; insts.delete(I); ro && ro.disconnect(); io && io.disconnect(); mo.disconnect(); c.remove(); if (!insts.size && raf) { cancelAnimationFrame(raf); raf = 0; } } };
  }
  window.NoxBS = { mount, state: S };
})();
