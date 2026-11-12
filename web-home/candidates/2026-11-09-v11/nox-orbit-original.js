/* NOX HELION orbital demo: 6 rocky color choices, 5 gas-giant themes, 3 asteroid quality modes.
   Uses original NOX orbital controls + their approved textures, Paper Shaders and GSAP.
   Only a stand-alone preview; no API, weights, SQLite or training are mutated. */
(()=>{'use strict';
if(document.body.dataset.page!=='index')return;
const COLOR_IDS=['black-sun','obsidian','foundry','cold','ion','amethyst'];
const THEME_IDS=['classic','velvet','graphite','metal','aurora'];
const THEME_NAMES=['HELION','OBSIDIAN','REACTOR','LIQUID METAL','AURORA'];
const MODE_IDS=['MAX','BALANCED','ECO'];
const STORE={color:'nox.demo.planet.color.v2',theme:'nox.background.v1',mode:'nox.demo.mode.v2'};
const read=(k,valid,def)=>{try{const v=localStorage.getItem(k);return valid.includes(v)?v:def;}catch{return def;}};
const save=(k,v)=>{try{localStorage.setItem(k,v);}catch{}};
let color=read(STORE.color,COLOR_IDS,'black-sun'),theme=read(STORE.theme,THEME_IDS,'classic'),mode=read(STORE.mode,MODE_IDS,'BALANCED');
let stage=null,host=null,controls=[],balls=[],on=true,hold=false,req=0,last=0,frame=0,blocked=false,pointer=false,seed=29818;
if(!window.NOX_NATIVE_OWNER&&!window.NoxBackgrounds){window.NoxBackgrounds=Object.freeze({get current(){return theme;},cycle(){const i=THEME_IDS.indexOf(theme);selectTheme(THEME_IDS[(i+1)%THEME_IDS.length]);return theme;},diagnostics(){return {current:theme,source:'PUBLIC_PREVIEW',native:false};}});}
const reduced=matchMedia('(prefers-reduced-motion:reduce)');
const rng=()=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return (seed>>>0)/4294967296;};
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const ribbon=document.createElement('div');ribbon.className='nox-preview-ribbon';ribbon.setAttribute('role','status');document.body.append(ribbon);
const helper=document.createElement('div');helper.className='nox-preview-help';helper.innerHTML='<strong>14 независимых объектов</strong><div>6 цветов планет · 5 газовых гигантов-тем · 3 астероида-режима. Золотое кольцо = выбранный.</div>';document.body.append(helper);
const glow=document.createElement('div');glow.className='nox-orbit-halo';document.body.append(glow);
const presets={'black-sun':'#d89d4a',obsidian:'#a9b6c4',foundry:'#db7d44',cold:'#a3e8ef',ion:'#65a8e5',amethyst:'#b98be1'};
function status(){document.documentElement.dataset.noxPlanetColor=color;document.documentElement.style.setProperty('--demo-glow',presets[color]);document.documentElement.dataset.noxDemoMode=mode;
 document.documentElement.dataset.noxBackground=theme;document.documentElement.dataset.noxPreviewTheme=theme; controls.forEach((b,i)=>b.setAttribute('aria-pressed',String(i<6?COLOR_IDS[i]===color:i<11?THEME_IDS[i-6]===theme:MODE_IDS[i-11]===mode)));
 ribbon.textContent=`NOX · ПРЕДПРОСМОТР · ${COLOR_IDS.indexOf(color)+1}/6 планеты · ${THEME_NAMES[THEME_IDS.indexOf(theme)]} · ${mode}`;
}
function selectTheme(id){theme=id;save(STORE.theme,id);document.documentElement.dataset.noxBackground=id;window.dispatchEvent(new CustomEvent('nox-background-change',{detail:{id}}));status();}
function install(){stage=document.querySelector('.helion-stage');host=document.querySelector('.nox-orbital-controls');if(!stage||!host)return false;
 // Place the existing controls INSIDE the stage so its coordinates match the actual canvas, not the body grid.
 if(host.parentElement!==stage)stage.append(host);
 // 390px layout: original footer must follow the 14-choice grid, never cover header or the nucleus.
 const mainNav=stage.querySelector('nav.home-primary-navigation');if(mainNav)stage.append(mainNav);
 const rocks=[...host.querySelectorAll('button.home-preset')],modes=[...host.querySelectorAll('#homeModes>button')];if(rocks.length!==6||modes.length!==3)return false;[...rocks,...modes].forEach(button=>button.removeAttribute('disabled'));
 const gasTemplate=modes[0].querySelector('svg.nox-gas-planet');
 // Reuse the original authored gas-band SVG, not a new renderer, with independent palette filters.
 const gas=[];THEME_IDS.forEach((id,i)=>{const b=document.createElement('button');b.type='button';b.className='nox-world-profile';b.dataset.profile=id;b.title='Облик NOX · '+THEME_NAMES[i];b.setAttribute('aria-label',b.title);
 const shell=document.createElement('span');shell.className='nox-world-ball';shell.setAttribute('aria-hidden','true');shell.dataset.world=id;
 if(gasTemplate){const art=gasTemplate.cloneNode(true);const suffix='Theme'+i;
 const idList=[...art.querySelectorAll('[id]')].map(x=>x.id);
 let markup=art.innerHTML;
 for(const oldId of idList){
  const nextId=oldId+suffix;
  markup=markup.replaceAll('url(#'+oldId+')','url(#'+nextId+')');
  markup=markup.replaceAll('href="#'+oldId+'"','href="#'+nextId+'"');
  markup=markup.replaceAll('id="'+oldId+'"','id="'+nextId+'"');
 }
 art.innerHTML=markup;art.classList.add('nox-theme-gas-svg');shell.append(art);}
 else{shell.classList.add('nox-world-fallback');}
 const label=document.createElement('span');label.className='nox-world-name';label.textContent=THEME_NAMES[i];b.append(shell,label);
 b.addEventListener('click',()=>selectTheme(id));host.append(b);gas.push(b);});
 // Three existing modes retain their real handlers. Visuals change to lightweight asteroid silhouettes.
 modes.forEach((b,i)=>{b.classList.add('nox-asteroid-mode');const a=document.createElement('span');a.className='nox-asteroid-stone';a.setAttribute('aria-hidden','true');a.dataset.stone=MODE_IDS[i];b.append(a);b.title='Режим графики · '+MODE_IDS[i];b.setAttribute('aria-label',b.title);});
 rocks.forEach((b,i)=>{b.addEventListener('click',()=>{color=COLOR_IDS[i];save(STORE.color,color);status();});});
 modes.forEach((b,i)=>{b.addEventListener('click',()=>{mode=MODE_IDS[i];save(STORE.mode,mode);status();});});
 controls=[...rocks,...gas,...modes];if(controls.length!==14)throw Error('14_ORBIT_CONTROLS_REQUIRED');
 // Public-only safe controls: these 14 choices are local visual settings, not commands to the missing Windows API.
 // Capture before legacy delegated listeners to prevent a misleading "save failed" from the disconnected API.
 stage.addEventListener('click',event=>{
  const button=event.target.closest('button.home-preset,button.nox-world-profile,button.nox-asteroid-mode');
  if(!button||!host.contains(button)||window.NOX_NATIVE_OWNER===true)return;
  event.preventDefault();event.stopImmediatePropagation();
  if(button.classList.contains('home-preset')){const i=rocks.indexOf(button);if(i>=0){color=COLOR_IDS[i];save(STORE.color,color);status();window.dispatchEvent(new CustomEvent('nox-preview-color-change',{detail:{color}}));}}
  else if(button.classList.contains('nox-world-profile')){selectTheme(button.dataset.profile);}
  else if(button.classList.contains('nox-asteroid-mode')){const id=button.dataset.mode;if(MODE_IDS.includes(id)){mode=id;save(STORE.mode,id);status();window.dispatchEvent(new CustomEvent('nox-settings',{detail:{mode:id}}));}}
 },true);

 controls.forEach((node,i)=>{node.dataset.orbitIndex=String(i);node.classList.add('nox-free-drift-object');node.style.setProperty('--demo-scale',i<6?'1':i<11?'1.08':'.94');});

/* Mobile strict geometry: legacy CSS cannot place this grid by desktop --demo-x/y. */
 function mobileGeometry(){
  const mobile=window.innerWidth<=1100;const narrow=window.innerWidth<=360;
  if(mobile)for(const node of controls)node.style.removeProperty('--demo-scale');
  for(const node of controls){
   for(const prop of ['position','inset','left','right','top','bottom','transform','width','height','margin','min-height','max-width']){
    if(!mobile){node.style.removeProperty(prop);continue}
    const val={
     'position':'relative','inset':'auto','left':'auto','right':'auto','top':'auto','bottom':'auto',
     'transform':'none','width':narrow?'68px':'80px','height':narrow?'70px':'76px','margin':'0 auto','min-height':narrow?'70px':'76px','max-width':narrow?'70px':'92px'
    }[prop];
    node.style.setProperty(prop,val,'important');
   }
  }
  const nav=stage.querySelector('nav.home-primary-navigation');
  if(nav){
   const settings={
    position:'relative',inset:'auto',left:'auto',top:'auto',bottom:'auto',right:'auto',
    transform:'none',width:'100%',maxWidth:'100%',height:'auto',minHeight:'0',
    display:'grid',gridTemplateColumns:'repeat(3,minmax(0,1fr))',
    gridTemplateRows:'repeat(3,58px)',gap:'5px',margin:'10px auto 2px',zIndex:'33'
   };
   for(const [k,val] of Object.entries(settings)){
    const prop=k.replace(/[A-Z]/g,a=>'-'+a.toLowerCase());
    if(mobile)nav.style.setProperty(prop,val,'important');
    else nav.style.removeProperty(prop);
   }
   for(const a of nav.querySelectorAll('a.helion-card')){
    for(const [prop,value] of [['grid-column','auto'],['grid-row','auto'],['height','58px'],['min-height','58px']]){
     if(mobile)a.style.setProperty(prop,value,'important');else a.style.removeProperty(prop);
    }
   }
  }
 }
 mobileGeometry();
 window.addEventListener('resize',mobileGeometry,{passive:true});

 balls=controls.map((node,i)=>({node,i,x:0,y:0,targetX:0,targetY:0,r:i<6?42:i<11?49:43,nextTarget:0,initialized:false,phase:rng()*6.3,orbitElapsed:0,homeX:null,homeY:null,orbitPeriod:480+i*19+(i%3)*43,pathX:35+(i%5)*9,pathY:19+(i%4)*7,pathTilt:(i*.61)%3.1,nextCourse:0,stalled:0}));
 status();/* initial color is painted locally; no network save */
 /* initial mode is painted locally; no network save */
 selectTheme(theme);
 host.addEventListener('pointerover',()=>{pointer=true;});host.addEventListener('pointerout',e=>{if(!host.contains(e.relatedTarget))pointer=false;});
 window.addEventListener('pagehide',()=>cancelAnimationFrame(req));document.addEventListener('visibilitychange',()=>{last=0;});
 window.addEventListener('nox-settings',e=>{if(MODE_IDS.includes(e.detail?.mode))mode=e.detail.mode;status();});
 window.addEventListener('resize',()=>{balls.forEach(b=>b.initialized=false);last=0;});
 const diag=()=>{const safe=safety();return {count:controls.length,colors:controls.filter(b=>b.classList.contains('home-preset')).length,giants:controls.filter(b=>b.classList.contains('nox-world-profile')).length,asteroids:controls.filter(b=>b.classList.contains('nox-asteroid-mode')).length,planetColor:color,theme,mode,notClockMotion:true,motionModel:'asymmetric blue-noise + elastic contacts',maxSpeedPxPerSecond:4.4,positions:balls.map(b=>({x:Math.round(b.x),y:Math.round(b.y),ready:b.initialized})),coreSafe:balls.every(b=>!b.initialized||!inCore(b.x,b.y,b.r,safe)),withinViewport:balls.every(b=>!b.initialized||isBounded(b.x,b.y,b.r,safe)),allVisible:balls.every(b=>b.initialized),collisionPairs:overlapPairs(),reducedMotion:reduced.matches,source:'NOX cinematic Lissajous slow local curves',previewOnly:true};};
 window.NOX_ORBIT_14_DEMO={diagnostics:diag,selectColor:id=>{const idx=COLOR_IDS.indexOf(id);if(idx>=0)rocks[idx].click();},selectTheme,selectMode:id=>{const idx=MODE_IDS.indexOf(id);if(idx>=0)modes[idx].click();}};
 req=requestAnimationFrame(tick);return true;}
function safety(){const s=stage.getBoundingClientRect(),w=s.width,h=s.height;
 const center={x:w*.5,y:h*.5,rx:clamp(w*.175,122,252),ry:clamp(h*.225,125,226)};
 const avoid=[];for(const sel of ['.helion-monitor','.helion-system','.home-primary-navigation','.nox-app-header']){
 const n=document.querySelector(sel);if(!n)continue;const r=n.getBoundingClientRect();if(r.width&&r.height)avoid.push({x:r.left-s.left,y:r.top-s.top,w:r.width,h:r.height});}
 return{w,h,c:center,avoid,margin:w<720?8:13};}
function isBounded(x,y,r,s){return x>=r+s.margin&&x<=s.w-r-s.margin&&y>=r+s.margin&&y<=s.h-r-s.margin;}
function inCore(x,y,r,s){const c=s.c;return Math.pow((x-c.x)/(c.rx+r+10),2)+Math.pow((y-c.y)/(c.ry+r+10),2)<1;}
function blocks(x,y,r,s){return s.avoid.some(a=>x+r>a.x-7&&x-r<a.x+a.w+7&&y+r>a.y-7&&y-r<a.y+a.h+7);}
function valid(x,y,r,s,self){if(!isBounded(x,y,r,s)||inCore(x,y,r,s)||blocks(x,y,r,s))return false;
 return balls.every(b=>b===self||!b.initialized||Math.hypot(x-b.x,y-b.y)>=r+b.r+10);}
// Blue-noise distribution near the nucleus: stratified random targets, not clock angles or orbital rotation.
/* Independent world positions: seeded, asymmetric and panel-safe.
   Never position on 14 equal angular intervals or one common orbit radius. */
const NOX_WORLD_SEEDS=[
 [0.16,0.23],[0.34,0.13],[0.64,0.17],[0.86,0.29],
 [0.80,0.53],[0.73,0.70],[0.50,0.78],[0.23,0.68],
 [0.11,0.48],[0.28,0.43],[0.77,0.12],[0.87,0.73],
 [0.47,0.31],[0.40,0.64]
];
const NOX_MOTION={frames:0,encounters:0,impacts:0,blocked:0,totalMotionPx:0};
function placeOne(b,s,first){
 if(s.w<=1100)return false;
 const [ax,ay]=NOX_WORLD_SEEDS[b.i];
 let best=null,bestScore=-Infinity;
 for(let attempt=0;attempt<980;attempt++){
  const wide=attempt<580?.115:.38;
  const px=(ax+(rng()-.5)*2*wide)*s.w;
  const py=(ay+(rng()-.5)*2*wide)*s.h;
  if(!valid(px,py,b.r,s,b))continue;
  let nearest=270;
  for(const other of balls)if(other!==b&&other.initialized){
   nearest=Math.min(nearest,Math.hypot(px-other.x,py-other.y)-b.r-other.r);
  }
  const spread=Math.hypot((px-ax*s.w)/s.w,(py-ay*s.h)/s.h);
  const score=Math.min(200,nearest)*.26-spread*290+(rng()-.5)*35;
  if(score>bestScore){bestScore=score;best={x:px,y:py};}
 }
 if(!best)return false;
 b.x=best.x;b.y=best.y;b.homeX=b.x;b.homeY=b.y;
 b.targetX=b.x;b.targetY=b.y;b.initialized=true;
 b.vx=0;b.vy=0;b.orbitElapsed=rng()*220;
 b.phase=rng()*Math.PI*2;b.spinDir=b.i%4===1?-1:1;
 b.nextCourse=performance.now()+95000+b.i*12000;b.stalled=0;
 return true;
}
function overlapPairs(){let n=0;for(let i=0;i<balls.length;i++)for(let j=i+1;j<balls.length;j++)if(balls[i].initialized&&balls[j].initialized&&Math.hypot(balls[i].x-balls[j].x,balls[i].y-balls[j].y)<balls[i].r+balls[j].r+10)n++;return n;}
function paint(){for(const b of balls){b.node.style.visibility=b.initialized?'visible':'hidden';if(!b.initialized)continue;b.node.style.setProperty('--demo-x',b.x.toFixed(1)+'px');b.node.style.setProperty('--demo-y',b.y.toFixed(1)+'px');}}
/* Elastic impulse for near-contact world bodies, with mass proportional to size.
   Real graphics uses measured positions; no fake movement or fake collisions. */
function noxBounce(a,b,nx,ny){
 const ma=Math.max(1,(a.r||40)**2),mb=Math.max(1,(b.r||40)**2);
 const rvx=(b.vx||0)-(a.vx||0),rvy=(b.vy||0)-(a.vy||0);
 const along=rvx*nx+rvy*ny;
 if(along>=0)return false;
 const impulse=-(1+.57)*along/(1/ma+1/mb);
 a.vx=(a.vx||0)-impulse*nx/ma;
 a.vy=(a.vy||0)-impulse*ny/ma;
 b.vx=(b.vx||0)+impulse*nx/mb;
 b.vy=(b.vy||0)+impulse*ny/mb;
 return true;
}
function tick(t){
 req=requestAnimationFrame(tick);
 if(t-last<33)return;
 const dt=last?Math.min(.08,(t-last)/1000):0;
 last=t;
 const s=safety();
 if(s.w<=1100){balls.forEach(b=>b.node.style.visibility='visible');return;}
 for(const b of balls)if(!b.initialized)placeOne(b,s,true);
 if(reduced.matches||document.hidden||pointer||document.documentElement.dataset.typing==='true'){
  paint();return;
 }
 const now=t/1000;
 const maxSpeed=mode==='ECO'?1.3:mode==='MAX'?4.4:2.8;
 for(const b of balls){
  if(!b.initialized)continue;
  const phase=b.phase,rx=b.homeX-s.c.x,ry=b.homeY-s.c.y;
  const len=Math.hypot(rx,ry)||1;
  const ux=rx/len,uy=ry/len;
  // Three independent, nonharmonic frequencies. Variable distance from nucleus.
  const radial=39*Math.sin(now*.036+phase*1.7);
  const along=26*Math.sin(now*.027+phase*.8);
  const sideways=17*Math.sin(now*.041+phase*2.3);
  b.targetX=b.homeX+ux*radial-uy*along+Math.cos(phase)*sideways;
  b.targetY=b.homeY+uy*radial+ux*along+Math.sin(phase)*sideways;

  // Occasional pair approach: no synchronized choreography or constant chase.
  if(b.i%4===1){
   if(b.meetAt===undefined)b.meetAt=now+6+b.i*4;
   if(now>=b.meetAt){
    let partner=null,nearest=240;
    for(const other of balls)if(other!==b&&other.initialized){
     const dist=Math.hypot(other.x-b.x,other.y-b.y);
     if(dist<nearest){nearest=dist;partner=other;}
    }
    if(partner){b.partner=partner.i;b.meetUntil=now+29;}
    b.meetAt=now+185+b.i*5;
   }
   if(now<(b.meetUntil||0)){
    const other=balls[b.partner];
    if(other?.initialized){
     const dist=Math.hypot(other.x-b.x,other.y-b.y);
     if(dist>b.r+other.r+17){
      b.targetX+=(other.x-b.x)*.55;
      b.targetY+=(other.y-b.y)*.55;
     }
    }
   }
  }
  const ex=b.targetX-b.x,ey=b.targetY-b.y;
  const damping=Math.exp(-dt*1.45);
  b.vx=((b.vx||0)+ex*dt*.65)*damping;
  b.vy=((b.vy||0)+ey*dt*.65)*damping;
  const sp=Math.hypot(b.vx,b.vy);
  if(sp>maxSpeed){b.vx=b.vx/sp*maxSpeed;b.vy=b.vy/sp*maxSpeed;}
  // Very slow independent re-targeting; position never jumps.
  if(t>=b.nextCourse){
   b.nextCourse=t+110000+b.i*17700;
   const candidateX=b.homeX+(rng()-.5)*25;
   const candidateY=b.homeY+(rng()-.5)*24;
   if(valid(candidateX,candidateY,b.r,s,b)){
    b.homeX=candidateX;b.homeY=candidateY;
   }
  }
 }
 // Bowling-like pair interaction: approach, exchange momentum, gently repel.
 for(let i=0;i<balls.length;i++)for(let j=i+1;j<balls.length;j++){
  const a=balls[i],b=balls[j];if(!a.initialized||!b.initialized)continue;
  const dx=b.x-a.x,dy=b.y-a.y,dist=Math.hypot(dx,dy)||.001;
  const nx=dx/dist,ny=dy/dist;
  const near=a.r+b.r+50;
  if(dist>=near)continue;
  NOX_MOTION.encounters++;
  const mag=(near-dist)/near;
  const push=(.2+2.2*mag)*dt;
  a.vx-=nx*push;a.vy-=ny*push;b.vx+=nx*push;b.vy+=ny*push;
  if(dist<a.r+b.r+12&&noxBounce(a,b,nx,ny))NOX_MOTION.impacts++;
 }
 for(const b of balls){
  if(!b.initialized)continue;
  const beforeX=b.x,beforeY=b.y;
  const xx=b.x+b.vx*dt,yy=b.y+b.vy*dt;
  if(valid(xx,yy,b.r,s,b)){b.x=xx;b.y=yy;b.stalled=0;}
  else{
   // Slide along the surface instead of freezing against core/panel boundaries.
   const moves=[
    [xx,b.y,b.vx*.65,0],
    [b.x,yy,0,b.vy*.65],
    [b.x-b.vy*dt*.7,b.y+b.vx*dt*.7,-b.vy*.7,b.vx*.7],
    [b.x+b.vy*dt*.7,b.y-b.vx*dt*.7,b.vy*.7,-b.vx*.7]
   ];
   let slid=false;
   for(const [cx,cy,vx,vy] of moves){
    if(!valid(cx,cy,b.r,s,b))continue;
    b.x=cx;b.y=cy;b.vx=vx;b.vy=vy;slid=true;NOX_MOTION.slides=(NOX_MOTION.slides||0)+1;break;
   }
   if(slid)b.stalled=0;
   else{
    b.vx*=-.38;b.vy*=-.38;b.stalled+=dt;NOX_MOTION.blocked++;
    if(b.stalled>3.5){
     b.homeX=b.x;b.homeY=b.y;b.phase+=.31*(b.i%2?1:-1);b.stalled=0;
     NOX_MOTION.repaths=(NOX_MOTION.repaths||0)+1;
    }
   }
  }
  NOX_MOTION.totalMotionPx+=Math.hypot(b.x-beforeX,b.y-beforeY);
  b.orbitElapsed+=dt;
  // Visual depth and authored material rotation: never rotate the whole label/button.
  const scale0=b.i<6?.62:b.i<11?.66:.58;
  const depth=1+.07*Math.sin(now*.033+b.phase*1.29);
  b.node.style.setProperty('--demo-scale',(scale0*depth).toFixed(3),'important');
  b.node.style.setProperty('--nox-axis-angle',((now*(1.1+(b.i%4)*.31)*(b.spinDir||1)+b.phase*30)%360).toFixed(2)+'deg');
  b.node.style.setProperty('--nox-gas-shift',(4.5*Math.sin(now*.040+b.phase)).toFixed(2)+'px');
 }
 paint();frame++;NOX_MOTION.frames++;
}
window.NOX_ORBIT_MOTION_QA=()=>({
 model:"asymmetric seeded blue-noise + independent 3-frequency trajectories + elastic contact",
 frames:NOX_MOTION.frames,nearEncounters:NOX_MOTION.encounters,
 actualImpacts:NOX_MOTION.impacts,blockedMoves:NOX_MOTION.blocked,slides:NOX_MOTION.slides||0,repaths:NOX_MOTION.repaths||0,
 totalMotionPx:+NOX_MOTION.totalMotionPx.toFixed(2),
 positions:balls.filter(b=>b.initialized).map(b=>({i:b.i,x:+b.x.toFixed(1),y:+b.y.toFixed(1),r:b.r,vx:+(b.vx||0).toFixed(2),vy:+(b.vy||0).toFixed(2)})),
 reducedMotion:reduced.matches,
 selfTest:(()=>{
  const a={r:40,vx:3,vy:0},b={r:40,vx:-3,vy:0};
  const before=[a.vx,b.vx];const hit=noxBounce(a,b,1,0);
  return {test:"head-on elastic collision",hit,before,after:[+a.vx.toFixed(3),+b.vx.toFixed(3)],
   velocitiesExchanged:a.vx<0&&b.vx>0};
 })()
});
let trials=0;const interval=setInterval(()=>{if(install()||++trials>100)clearInterval(interval)},110);
})();
