/* NOX HELION: FIVE WORLDS · six palettes. Non-destructive all-page enhancement.
 * The original D02/14 worlds remain untouched and visible in HELION.
 * Alternative scenes use one shared Canvas2D, preserving every original button handler.
 * Respects reduced motion, visibility, and original inference/STOP states.
 */
(() => {
  'use strict';
  if (window.NOX_CINEMATIC_WORLDS) return;
  const D=document, H=D.documentElement, B=D.body;
  const WORLDS={
    helion:{label:'HELION',ru:'Чёрное солнце',kind:'Оригинальная Вселенная',skin:'obsidian',scene:'eclipse',font:'"Tektur", "Trebuchet MS", sans-serif'},
    chronos:{label:'CHRONOS',ru:'Механизм времени',kind:'Шестерни, маятники, турбийон',skin:'foundry',scene:'chrome',font:'Georgia, "Times New Roman", serif'},
    somnium:{label:'SOMNIUM',ru:'Невозможная материя',kind:'Сюрреализм, каустики, фракталы',skin:'liquid',scene:'plasma',font:'"Century Gothic", "Trebuchet MS", sans-serif'},
    forge:{label:'FORGE',ru:'Живая крепость',kind:'Сталь, огонь, поршни, пепел',skin:'foundry',scene:'crimson',font:'"Arial Narrow", "Tektur", sans-serif'},
    synapse:{label:'SYNAPSE',ru:'Нейронный организм',kind:'Связи, мембраны, импульсы',skin:'aurora',scene:'mycelium',font:'"Segoe UI", "Trebuchet MS", sans-serif'}
  };
  const PALETTES={gold:{ru:'Чёрное золото',rgb:[233,180,101]},copper:{ru:'Расплавленная медь',rgb:[241,124,77]},glacier:{ru:'Ледяной голубой',rgb:[142,201,250]},ion:{ru:'Ионный бирюзовый',rgb:[71,224,209]},amethyst:{ru:'Аметист',rgb:[191,146,251]},platinum:{ru:'Платина',rgb:[220,231,240]}};
  const reduce=matchMedia('(prefers-reduced-motion: reduce)');
  const get=(k,fallback)=>{try{return localStorage.getItem(k)||fallback}catch{return fallback}};
  let currentWorld=get('nox.cinematic.world.v3','helion');if(!WORLDS[currentWorld])currentWorld='helion';
  let currentPalette=get('nox.cinematic.palette.v3',get('nox.palette.v3','gold'));if(!PALETTES[currentPalette])currentPalette='gold';
  let host=null,canvas=null,context=null,raf=0,last=0,w=1,h=1,frame=0,observer=null,panel=null,toggle=null,resizeObserver=null;
  const css=(name)=>getComputedStyle(H).getPropertyValue(name).trim();
  const quality=()=>String(H.dataset.noxDemoMode||get('nox_visual_mode','BALANCED')).toUpperCase();
  const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
  const lerp=(a,b,t)=>a+(b-a)*t;
  const rgba=(c,a)=>`rgba(${c[0]},${c[1]},${c[2]},${a})`;
  const safe=()=>!D.hidden && !reduce.matches && H.dataset.runtimeBusy!=='true' && H.dataset.typing!=='true' && B.dataset.inferenceActive!=='true';
  let lastPointer={x:0,y:0};
  function backdrop(c,W,H,t){
    const g=c.createRadialGradient(W*.49,H*.52,0,W*.49,H*.52,Math.max(W,H)*.9);
    g.addColorStop(0,'rgba(12,14,21,.12)');g.addColorStop(.46,'rgba(9,11,17,.32)');g.addColorStop(1,'rgba(2,3,7,.8)');
    c.fillStyle=g;c.fillRect(0,0,W,H);
    // Low-cost film grain: deterministic cross-hatching, not a noisy per-pixel loop.
    c.save();c.globalAlpha=.035;c.strokeStyle='#bdc9e4';c.lineWidth=.3;
    for(let i=0;i<23;i++){let y=((i*107+Math.sin(t*.14+i)*17)%H+H)%H;c.beginPath();c.moveTo(0,y);c.lineTo(W,y);c.stroke()}
    c.restore();
  }
  function gear(c,x,y,r,teeth,rot,col,detail=1){
    c.save();c.translate(x,y);c.rotate(rot);let N=teeth*4;
    c.beginPath();
    for(let i=0;i<=N;i++){const th=i/N*Math.PI*2,phase=i%4,rr=r*(phase===0||phase===3?1.10:phase===1?1.16:1.04);const px=Math.cos(th)*rr,py=Math.sin(th)*rr;i?c.lineTo(px,py):c.moveTo(px,py)}c.closePath();
    const grad=c.createRadialGradient(-r*.45,-r*.5,r*.04,0,0,r*1.18);
    grad.addColorStop(0,rgba(col,.39));grad.addColorStop(.43,'rgba(39,37,45,.71)');grad.addColorStop(.85,'rgba(6,10,15,.94)');grad.addColorStop(1,rgba(col,.64));
    c.fillStyle=grad;c.fill();c.lineWidth=Math.max(1,r*.018);c.strokeStyle=rgba(col,.66);c.stroke();
    c.strokeStyle=rgba(col,.25);c.lineWidth=Math.max(.5,r*.01);
    for(let j=0;j<detail*2+3;j++){const rr=r*(.32+j*.12);c.beginPath();c.arc(0,0,rr,0,Math.PI*2);c.stroke()}
    for(let j=0;j<6;j++){let th=j*Math.PI/3;c.beginPath();c.moveTo(Math.cos(th)*r*.18,Math.sin(th)*r*.18);c.lineTo(Math.cos(th)*r*.76,Math.sin(th)*r*.76);c.strokeStyle=rgba(col,.45);c.lineWidth=Math.max(2,r*.057);c.stroke()}
    c.beginPath();c.arc(0,0,r*.17,0,Math.PI*2);c.fillStyle='#090c12';c.fill();c.lineWidth=Math.max(1,r*.015);c.strokeStyle=rgba(col,.85);c.stroke();
    for(let j=0;j<4;j++){let th=j*Math.PI/2; c.beginPath();c.arc(Math.cos(th)*r*.75,Math.sin(th)*r*.75,Math.max(1,r*.022),0,Math.PI*2);c.fillStyle=rgba(col,.65);c.fill()}
    c.restore();
  }
  function chronos(c,W,H,t,col){
    const S=Math.min(W/1050,H/710,1.55),cx=W*.52,cy=H*.51;
    c.save();c.translate(cx,cy);c.scale(S,S);
    for(let ring=0;ring<4;ring++){let r=ring*92+170;c.beginPath();c.arc(0,0,r,0,Math.PI*2);c.lineWidth=ring===0?1.4:.8;c.strokeStyle=rgba(col,.08+ring*.024);c.stroke()}
    const gears=[{x:0,y:0,r:102,n:34,rate:1},{x:158,y:-18,r:55,n:20,rate:-1.7},{x:-150,y:8,r:54,n:21,rate:-1.62},{x:-48,y:-163,r:57,n:21,rate:-1.61},{x:60,y:163,r:56,n:20,rate:-1.7},{x:228,y:126,r:43,n:15,rate:2.27},{x:-234,y:135,r:43,n:15,rate:2.27}];
    const k=t*.14; for(let i=0;i<gears.length;i++){const g=gears[i];gear(c,g.x,g.y,g.r,g.n,k*g.rate+i*.16,col,i===0?3:1)}
    c.beginPath();c.arc(0,0,43,0,Math.PI*2);c.strokeStyle=rgba(col,.9);c.lineWidth=3;c.stroke();
    c.textAlign='center';c.fillStyle=rgba(col,.86);c.font='600 19px Georgia, serif';c.fillText('NOX',0,6);
    // Independent pendulum: mechanical movement, not a fake telemetry gauge.
    c.save();c.translate(0,10);c.rotate(Math.sin(t*1.3)*.16);c.beginPath();c.moveTo(0,0);c.lineTo(0,240);c.lineWidth=2;c.strokeStyle=rgba(col,.68);c.stroke();c.beginPath();c.arc(0,240,19,0,Math.PI*2);c.fillStyle=rgba(col,.7);c.fill();c.restore();
    c.restore();
  }
  function somnium(c,W,H,t,col){
    c.save();c.globalCompositeOperation='screen';let cx=W*.5,cy=H*.53,base=Math.min(W,H)*.33;
    for(let layer=0;layer<6;layer++){
      let R=base*(.32+layer*.14),turn=t*.13*(layer%2?1:-1)+layer*.53;
      c.beginPath();const n=quality()==='MAX'?110:65;
      for(let k=0;k<=n;k++){let a=k/n*Math.PI*2, rr=R*(1+.28*Math.sin(a*(3+layer%3)+turn)+.17*Math.cos(a*(7+layer%2)-t*.23));let x=cx+Math.cos(a+turn*.09)*rr,y=cy+Math.sin(a+turn*.13)*rr*.75;k?c.lineTo(x,y):c.moveTo(x,y)}c.closePath();
      c.lineWidth=layer%2?1.1:2;c.strokeStyle=rgba(col,.09+layer*.042);c.stroke();
      if(layer%2===0){c.fillStyle=rgba(col,.016);c.fill()}
    }
    for(let j=0;j<14;j++){let angle=t*.17+j*2.399,R=base*(.16+.054*j);let x=cx+Math.cos(angle)*R,y=cy+Math.sin(angle*1.3)*R*.68;
       c.beginPath();c.arc(x,y,1.2+(j%4)*.6,0,Math.PI*2);c.fillStyle=rgba(col,.17+j*.006);c.fill()}
    let g=c.createRadialGradient(cx,cy,0,cx,cy,base*.9);g.addColorStop(0,rgba(col,.16));g.addColorStop(.3,'rgba(8,9,16,.1)');g.addColorStop(.8,'rgba(0,0,0,0)');c.fillStyle=g;c.fillRect(0,0,W,H);
    c.restore();
  }
  function forge(c,W,H,t,col){
    c.save();const cx=W*.5,cy=H*.52,scale=Math.min(W/920,H/610,1.55);c.translate(cx,cy);c.scale(scale,scale);
    for(let k=-3;k<=3;k++){
      let x=k*135+Math.sin(t*.11+k)*11,w=106;
      let grd=c.createLinearGradient(x,-380,x+w,380);grd.addColorStop(0,'rgba(22,29,38,.2)');grd.addColorStop(.54,rgba(col,.12));grd.addColorStop(1,'rgba(2,5,8,.65)');
      c.fillStyle=grd;c.beginPath();c.moveTo(x,-360);c.lineTo(x+w,-290);c.lineTo(x+w,360);c.lineTo(x,300);c.closePath();c.fill();c.strokeStyle=rgba(col,.12);c.lineWidth=2;c.stroke();
    }
    c.fillStyle='rgba(1,3,5,.92)';c.fillRect(-155,-150,310,300);
    let fire=c.createRadialGradient(0,0,12,0,0,220);fire.addColorStop(0,rgba(col,.39));fire.addColorStop(.4,rgba(col,.12));fire.addColorStop(1,'rgba(0,0,0,0)');c.fillStyle=fire;c.fillRect(-250,-250,500,500);
    for(let k=0;k<9;k++){let x=(k-4)*32;let height=130+70*Math.pow(Math.sin(k*1.4+t*.38),2);
      c.beginPath();c.moveTo(x,153);c.bezierCurveTo(x-18,35,x+24,-height*.35,x+Math.sin(t*.8+k)*18,-height);c.bezierCurveTo(x+29,-height*.18,x+22,53,x+16,152);c.closePath();c.fillStyle=rgba(col,.047+Math.abs(k-4)*.005);c.fill()}
    for(let j=0;j<4;j++){let yy=-200+j*126,x=-420+Math.sin(t*.16+j)*32;c.fillStyle='rgba(33,41,49,.8)';c.fillRect(x,yy,110,12);c.fillStyle=rgba(col,.2);c.fillRect(x+18,yy-4,4,22)}
    c.textAlign='center';c.font='800 28px sans-serif';c.fillStyle=rgba(col,.69);c.fillText('N O X',0,8);c.restore();
  }
  function synapse(c,W,H,t,col){
    c.save();c.globalCompositeOperation='screen';
    const N=quality()==='MAX'?42:27,coords=[];
    for(let j=0;j<N;j++){
      const colj=j%9,row=Math.floor(j/9),ph=j*1.74;
      const x=W*(.11+colj*.098)+Math.sin(ph+t*.45)*W*.022,y=H*(.13+row*.18)+Math.cos(ph*.9+t*.3)*H*.046;
      coords.push({x,y,ph})
    }
    for(let i=0;i<coords.length;i++)for(let j=i+1;j<coords.length;j++){
      let A=coords[i],Z=coords[j],dist=Math.hypot(A.x-Z.x,A.y-Z.y);if(dist>W*.18||dist<10)continue;
      c.beginPath();c.moveTo(A.x,A.y);c.quadraticCurveTo((A.x+Z.x)/2+Math.sin(t*.4+i)*14,(A.y+Z.y)/2-13,Z.x,Z.y);
      c.lineWidth=.6;c.strokeStyle=rgba(col,clamp((1-dist/(W*.18))*.17,.012,.21));c.stroke();
      if(i%7===0){const q=(t*.13+i*.03)%1;c.beginPath();c.arc(lerp(A.x,Z.x,q),lerp(A.y,Z.y,q),1.6,0,Math.PI*2);c.fillStyle=rgba(col,.55);c.fill()}
    }
    for(let j=0;j<coords.length;j++){let a=coords[j];c.beginPath();c.arc(a.x,a.y,2.2+(Math.sin(t*1.2+a.ph)+1)*1.4,0,Math.PI*2);c.fillStyle=rgba(col,.29);c.fill()}
    const g=c.createRadialGradient(W*.5,H*.52,0,W*.5,H*.52,Math.min(W,H)*.39);g.addColorStop(0,rgba(col,.15));g.addColorStop(1,'rgba(0,0,0,0)');c.fillStyle=g;c.fillRect(0,0,W,H);
    c.restore();
  }

  function paintWorldLayer(c,W,H,t,col){
    const layer=document.documentElement.dataset.noxUiLayer||'none';
    const allowed={embers:['forge'],steam:['forge','chronos'],prism:['somnium'],signals:['synapse']};
    if(!allowed[layer]?.includes(currentWorld)||quality()==='ECO'&&layer==='prism')return;
    c.save();c.globalCompositeOperation='screen';const v=quality()==='MAX'?1:.55;
    if(layer==='embers')for(let i=0;i<32;i++){
      const x=(W*(i*.61803398875%1)+Math.sin(t*.5+i)*W*.026)%W,y=((H+(H*(i*.381966%1)-t*(13+i%8)))%H+H)%H;
      c.beginPath();c.arc(x,y,.6+i%3*.5,0,Math.PI*2);c.fillStyle='rgba(255,136,72,'+(.11*v)+')';c.fill();
    }
    else if(layer==='steam')for(let i=0;i<7;i++){
      const x=W*(.14+i*.12),base=H*.95;c.beginPath();
      for(let j=0;j<24;j++){const q=j/23,xx=x+Math.sin(q*8+t*.52+i)*W*.014,yy=base-q*H*.59;j?c.lineTo(xx,yy):c.moveTo(xx,yy)}
      c.lineWidth=Math.max(1,W/900)*v;c.strokeStyle='rgba(187,205,214,'+(.08*v)+')';c.stroke();
    }
    else if(layer==='prism')for(let i=0;i<6;i++){
      const angle=t*.15+i*Math.PI/3,x=W*.5+Math.cos(angle)*W*.23,y=H*.5+Math.sin(angle)*H*.21;
      c.beginPath();c.moveTo(x,y-H*.08);c.lineTo(x+W*.06,y+H*.06);c.lineTo(x-W*.06,y+H*.06);c.closePath();c.strokeStyle=i%2?'rgba(129,210,252,.18)':'rgba(194,118,244,.17)';c.lineWidth=1.2*v;c.stroke();
    }
    else if(layer==='signals')for(let i=0;i<18;i++){
      const phase=t*.38+i*1.7,x=W*(.08+(i%9)*.102),y=H*(.16+Math.floor(i/9)*.48);
      const px=x+Math.sin(phase)*W*.09,py=y+Math.cos(phase*.83)*H*.07;
      c.beginPath();c.arc(px,py,2+(i%3),0,Math.PI*2);c.fillStyle='rgba('+col.join(',')+','+(.26*v)+')';c.fill();
    }c.restore();
  }

  function resize(){if(!canvas||!host)return;const rc=host.getBoundingClientRect();w=Math.max(1,rc.width);h=Math.max(1,rc.height);const Q=quality();const dpr=Math.min(devicePixelRatio||1,Q==='MAX'?1.5:Q==='ECO'?.75:1.1);canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);context.setTransform(dpr,0,0,dpr,0,0)}
  function draw(ms){raf=0;if(!context||!canvas||currentWorld==='helion'||!safe())return;const Q=quality(),fps=Q==='MAX'?50:Q==='ECO'?14:28;
    if(ms-last<1000/fps){raf=requestAnimationFrame(draw);return}last=ms;frame++;
    const c=context;c.clearRect(0,0,w,h);const col=PALETTES[currentPalette].rgb,t=ms*.001;
    backdrop(c,w,h,t);({chronos,somnium,forge,synapse}[currentWorld]||(()=>{}))(c,w,h,t,col);paintWorldLayer(c,w,h,t,col);raf=requestAnimationFrame(draw);
  }
  function tick(){cancelAnimationFrame(raf);raf=0;last=0;if(canvas)canvas.style.display=currentWorld==='helion'?'none':'block';if(canvas&&currentWorld!=='helion'&&safe()){draw(performance.now())}else if(context)context.clearRect(0,0,w,h)}
  function refreshUI(){H.dataset.noxWorld=currentWorld;H.dataset.noxColor=currentPalette;H.style.setProperty('--nox-world-font',WORLDS[currentWorld].font);H.style.setProperty('--nox-world-rgb',PALETTES[currentPalette].rgb.join(','));
    if(panel){for(const b of panel.querySelectorAll('[data-nox-select-world]'))b.setAttribute('aria-pressed',String(b.dataset.noxSelectWorld===currentWorld));for(const b of panel.querySelectorAll('[data-nox-select-palette]'))b.setAttribute('aria-pressed',String(b.dataset.noxSelectPalette===currentPalette))}
    if(toggle)toggle.textContent='✦ '+WORLDS[currentWorld].label;
  }
  // Palette is a visual material decision, not an undocumented training/model setting.
  // Keep the existing WebGL industrial shader aligned with the six UI palette previews.
  const paletteToShaderTheme=Object.freeze({gold:'amber',copper:'ember',glacier:'arctic',ion:'arctic',amethyst:'void-purple',platinum:'graphite'});
  function notifyMaterial(){
    const visualMode=quality();
    window.dispatchEvent(new CustomEvent('nox-settings',{detail:{theme:paletteToShaderTheme[currentPalette],...( ['MAX','BALANCED','ECO'].includes(visualMode)?{mode:visualMode}:{})}}));
  }
  function apply(world,palette,save=true){if(!WORLDS[world]||!PALETTES[palette])return false;currentWorld=world;currentPalette=palette;if(save)try{localStorage.setItem('nox.cinematic.world.v3',world);localStorage.setItem('nox.cinematic.palette.v3',palette);localStorage.setItem('nox.palette.v3',palette)}catch{}
    refreshUI();window.dispatchEvent(new CustomEvent('nox-cinematic-world-change',{detail:{world,palette}}));notifyMaterial();tick();return true;
  }
  function buildControls(){
    // V7: no collapsible world selector. Full world/palette grid lives in Studio.
    if(B.dataset.noxPage==='studio')return;
    const shell=D.createElement('nav');shell.id='noxWorldsControl';shell.className='nox-worlds-control nox-worlds-direct';shell.setAttribute('aria-label','Визуальный конструктор NOX');
    const anchor=D.createElement('a');anchor.className='nox-worlds-open nox-worlds-direct-link';
    const path=location.pathname.toLowerCase();
    anchor.href=path.includes('/pc/pages/')?'../../studio.html':'studio.html';
    anchor.textContent='✦ КОНСТРУКТОР';anchor.setAttribute('aria-label','Открыть визуальный конструктор пяти миров и двенадцати атмосфер NOX');
    shell.appendChild(anchor);B.appendChild(shell);
  }
  function init(){
    // Restore the user-selected verified Studio preset before constructing the scene.
    try {const preset=JSON.parse(get('nox.master.v4.skin','null'));
      if(preset&&WORLDS[preset.world]&&PALETTES[preset.palette]){
        currentWorld=preset.world;currentPalette=preset.palette;
        // Apply validated Studio choices to every existing page, not only Studio.
        if(['metal','gear','liquid','glass','plasma','mineral'].includes(preset.button))H.dataset.noxUiButton=preset.button;
        if(['tektur','orbitron','russo','serif','mono'].includes(preset.font))H.dataset.noxUiFont=preset.font;
        if(['max','balanced','eco'].includes(preset.quality))H.dataset.noxDemoMode=preset.quality.toUpperCase();
        const allowed={none:['helion','chronos','somnium','forge','synapse'],embers:['helion','forge'],lensing:['helion'],steam:['chronos','forge'],prism:['somnium'],signals:['synapse']};
        if(allowed[preset.layer]?.includes(preset.world)&&!(preset.quality==='eco'&&['lensing','prism'].includes(preset.layer)))H.dataset.noxUiLayer=preset.layer;
      }
    } catch {}
    host=D.querySelector('.helion-stage')||B;if(!host)return;canvas=D.createElement('canvas');canvas.id='noxCinematicWorldCanvas';canvas.setAttribute('aria-hidden','true');if(host===B){canvas.style.position='fixed';canvas.style.opacity='.20'}else canvas.style.position='absolute';
    host.insertBefore(canvas,host.firstChild);context=canvas.getContext('2d',{alpha:true,desynchronized:true});if(!context){canvas.remove();canvas=null}buildControls();refreshUI();resize();notifyMaterial();tick();
    resizeObserver=typeof ResizeObserver==='function'?new ResizeObserver(()=>{resize();tick()}):null;resizeObserver?.observe(host);
    addEventListener('resize',()=>{resize();tick()},{passive:true});D.addEventListener('visibilitychange',tick);reduce.addEventListener?.('change',tick);
    observer=new MutationObserver(list=>{if(list.some(e=>e.attributeName==='data-nox-demo-mode'||e.attributeName==='data-nox-ui-layer'||e.attributeName==='data-typing'||e.attributeName==='data-runtime-busy'))tick()});observer.observe(H,{attributes:true,attributeFilter:['data-nox-demo-mode','data-nox-ui-layer','data-typing','data-runtime-busy']});
    addEventListener('pagehide',()=>{cancelAnimationFrame(raf);observer?.disconnect();resizeObserver?.disconnect()},{once:true});
    window.NOX_CINEMATIC_WORLDS={version:'3.0.0',worlds:Object.keys(WORLDS),palettes:Object.keys(PALETTES),setWorld:v=>apply(v,currentPalette),setPalette:v=>apply(currentWorld,v),getState:()=>({world:currentWorld,palette:currentPalette,frames:frame,quality:quality(),motionPaused:!safe(),extraWebGLContexts:0,originalNOXModulesReplaced:0})};
  }
  if(D.readyState==='loading')D.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();