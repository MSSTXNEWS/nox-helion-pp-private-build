/* NOX V16: ACTUAL owner-approved nine-sphere D02 runtime mount.
 * Uses the existing PR30 renderer. Never creates a ninth CoreID, routes,
 * numerical training progress, new event bus, model process or storage.
 * Fail-closed if the original R13 core identity/geometry differs.
 */
import {installNoxCinemaFX} from '../proposals/NOX-CINEMA-FX/nox-cinema.mjs';

export const CANONICAL_CORES=Object.freeze([
  'CONSCIOUSNESS','PERSONA','ATLAS','VOICE','REFLECTION','CORE','NEXUS','FORGE'
]);
let mounted=null,observer=null,bodyObserver=null;

export function mountApprovedHome(doc=document){
  if(mounted)return mounted;
  const home=doc.getElementById('home');
  const stage=home?.querySelector('.nox-orbit-stage');
  if(!home||!stage||!home.classList.contains('screen'))
    throw Error('D02_HOME_APPROVED_ORBIT_STAGE_REQUIRED');
  const central=stage.querySelector('.nox-eclipse');
  const items=[...stage.querySelectorAll('.nox-orbit-core')];
  const ids=items.map(e=>e.dataset.coreId);
  if(!central||items.length!==8||ids.some((v,i)=>v!==CANONICAL_CORES[i])||
      stage.querySelectorAll('.nox-eclipse').length!==1 ||
      new Set(ids).size!==8 ||
      [...items,central].some(e=>e.getAttribute('data-nox-verified-fx')==='active'))
    throw Error('D02_EXACT_HELION_PLUS_EIGHT_CORE_LOCK');
  const orbs=[{id:'HELION',element:central},...items.map((element,i)=>({id:CANONICAL_CORES[i],element}))];
  const view=doc.defaultView;
  if(!view)throw Error('D02_WINDOW_REQUIRED');
  const reducedMotion=view.matchMedia?.('(prefers-reduced-motion: reduce)')??null;
  // A saved graphics preference is purely visual; it NEVER authorizes
  // training, download, native IPC, or a computer action.
  const choices=Object.freeze({MAX_WOW:'MAX',CINEMA:'BALANCED',
    ECO:'ECO',MINI_START:'REDUCED',AUTO:null});
  const prefKey='nox.d02.graphics.preference.v1';
  let selectedQuality='CINEMA';
  try{
    const saved=view.localStorage?.getItem(prefKey);
    if(Object.prototype.hasOwnProperty.call(choices,saved))selectedQuality=saved;
    else if(doc.body.classList.contains('nox-wow-eco'))selectedQuality='ECO';
    else if(doc.body.classList.contains('nox-wow-max'))selectedQuality='MAX_WOW';
  }catch(_){/* Local storage may be blocked: manual buttons still work. */}
  let autoQuality='BALANCED',autoRaf=0,autoLast=0,autoSamples=[],autoChanged=0;
  let dock=null;
  function chosenMode(){
    if(reducedMotion?.matches)return 'REDUCED';
    return selectedQuality==='AUTO'?autoQuality:choices[selectedQuality];
  }
  function stopAuto(){
    if(autoRaf){view.cancelAnimationFrame(autoRaf);autoRaf=0;}
    autoLast=0;autoSamples=[];
  }
  function sampleAuto(now){
    autoRaf=0;
    if(selectedQuality!=='AUTO'||disposed||doc.hidden||reducedMotion?.matches)return;
    if(autoLast>0 && now>autoLast && now-autoLast<250)autoSamples.push(now-autoLast);
    autoLast=now;
    if(autoSamples.length>=120){
      const average=autoSamples.reduce((a,b)=>a+b,0)/autoSamples.length;
      autoSamples=[];
      // Only real animation-frame timing, no guessed GPU utilization.
      // Hysteresis avoids UI mode flicker; owner may override instantly.
      if(now-autoChanged>15000){
        const next=average>43?'ECO':average>31?'BALANCED':
          average<18?'MAX':autoQuality;
        if(next!==autoQuality){autoQuality=next;autoChanged=now;sync();}
      }
    }
    autoRaf=view.requestAnimationFrame(sampleAuto);
  }
  function beginAuto(){
    if(selectedQuality==='AUTO'&&!autoRaf&&!doc.hidden&&!reducedMotion?.matches){
      autoLast=0;autoSamples=[];
      autoRaf=view.requestAnimationFrame(sampleAuto);
    }
  }
  // Existing approved PR30 source owns the visual physics of these exact nine
  // elements. No trusted events are supplied until the native bridge is attested.
  const scene=installNoxCinemaFX({root:stage,orbs,profile:chosenMode()});
  let film=null,detachMotion=()=>{};
  // FX-owned DOM markers and observers form one rollback transaction.
  let disposed=false;
  function releaseFx(){
    if(disposed)return;
    disposed=true;
    stopAuto();
    try{dock?.destroy();}catch(_){}
    try{detachMotion();}catch(_){}
    try{observer?.disconnect();}catch(_){}
    try{bodyObserver?.disconnect();}catch(_){}
    observer=null;bodyObserver=null;
    for(const element of [central,...items]){
      try{delete element.dataset.noxVerifiedFx;}catch(_){}
    }
    try{film?.destroy();}catch(_){}
    try{scene.destroy();}finally{mounted=null;}
  }
  try{
    const sync=()=>{
      const visible=home.classList.contains('active'),mode=chosenMode();
      scene.setVisible(visible);scene.setProfile(mode);
      // MINI START does not even allocate a WebGL context at first launch.
      if(mode==='REDUCED'){
        film?.destroy();film=null;
      }else{
        if(!film)film=mountNoxFilm(stage,view,doc);
        film.setVisible(visible);film.setProfile(mode,scene.snapshot().state);
      }
      dock?.render(selectedQuality,mode,reducedMotion?.matches===true);
    };
    const chooseQuality=choice=>{
      if(!Object.prototype.hasOwnProperty.call(choices,choice))return false;
      selectedQuality=choice;stopAuto();
      if(choice==='AUTO'){autoQuality='BALANCED';autoChanged=0;}
      try{view.localStorage?.setItem(prefKey,choice);}catch(_){}
      sync();
      if(choice==='AUTO')beginAuto();
      return true;
    };
    dock=mountNoxGraphicsDock(home,doc,chooseQuality);
    observer=new view.MutationObserver(sync);
    observer.observe(home,{attributes:true,attributeFilter:['class']});
    bodyObserver=new view.MutationObserver(sync);
    bodyObserver.observe(doc.body,{attributes:true,attributeFilter:['class']});
    if(typeof reducedMotion?.addEventListener==='function'){
      reducedMotion.addEventListener('change',sync);
      detachMotion=()=>reducedMotion.removeEventListener?.('change',sync);
    }else if(typeof reducedMotion?.addListener==='function'){
      reducedMotion.addListener(sync);
      detachMotion=()=>reducedMotion.removeListener?.(sync);
    }
    for(const element of [central,...items])element.dataset.noxVerifiedFx='active';
    sync();
    if(selectedQuality==='AUTO')beginAuto();
    const onAutoVisibility=()=>{if(doc.hidden)stopAuto();else beginAuto();};
    doc.addEventListener('visibilitychange',onAutoVisibility);
    const oldDetach=detachMotion;
    detachMotion=()=>{doc.removeEventListener('visibilitychange',onAutoVisibility);oldDetach();};
    mounted=Object.freeze({
      snapshot:()=>({...scene.snapshot(),kind:'decorative-d02',backendAccepted:false,source:'PR30'}),
      setProfile:mode=>{
        // An invalid public request must not poison the remembered profile.
        // Keep OS Reduced Motion dominant, even when callers request MAX.
        if(typeof mode!=='string'||
           !['ECO','BALANCED','MAX','REDUCED'].includes(mode))return false;
        const accepted=scene.setProfile(reducedMotion?.matches?'REDUCED':mode);
        if(accepted===true){
          const chosen=Object.keys(choices).find(k=>k!=='AUTO'&&choices[k]===mode);
          if(chosen)chooseQuality(chosen); // Any manual choice cancels AUTO.
        }
        return accepted;
      },
      destroy(){releaseFx();}
    });
    return mounted;
  }catch(error){try{releaseFx();}catch(_){}throw error;}
}

/* NOX SUPER WOW CINEMA LAYER V1: optional original filmic WebGL backdrop.
 * The preexisting 9-orb D02 is authoritative. No moving hitboxes, synthetic
 * telemetry, external dependencies, download transport, new backend or routes.
 * Shader methods researched alongside OGL (Unlicense), tsParticles (MIT),
 * and ashima/webgl-noise (MIT); no third-party GLSL was copied.
 */

/* NOX D02 GRAPHICS PLANET DOCK V1 — five genuine graphic BUTTONS (no dropdown).
 * Visual performance only: never changes AI learning, GPU training, model
 * queue, source patches, STOP, permissions or native owner state.
 */
function mountNoxGraphicsDock(home,doc,onSelect){
  const entries=[
    ['MAX_WOW','MAX WOW','ПОЛНЫЙ','✦'],
    ['CINEMA','CINEMA','КИНО','◉'],
    ['ECO','ECO','ЭКОНОМ','◌'],
    ['MINI_START','MINI START','МИНИ','·'],
    ['AUTO','AUTO','АДАПТИВНО','◇']
  ];
  const dock=doc.createElement('nav');
  dock.className='nox-quality-dock';dock.dataset.noxGraphicsDock='v1';
  dock.setAttribute('aria-label','Качество графики NOX');
  const top=doc.createElement('div');top.className='nox-quality-dock__head';
  const title=doc.createElement('strong');title.textContent='✦ ГРАФИКА';
  const status=doc.createElement('output');status.className='nox-quality-dock__status';
  status.setAttribute('aria-live','polite');top.append(title,status);
  const row=doc.createElement('div');row.className='nox-quality-dock__row';
  row.setAttribute('role','group');row.setAttribute('aria-label','Режим графики');
  const buttons=new Map();
  for(const [id,name,hint,glyph] of entries){
    const button=doc.createElement('button');button.type='button';
    button.className='nox-quality-planet';button.dataset.quality=id;
    button.setAttribute('aria-label',name+' — '+hint);
    button.setAttribute('aria-pressed','false');
    const sphere=doc.createElement('span');sphere.className='nox-quality-planet__sphere';
    sphere.setAttribute('aria-hidden','true');sphere.textContent=glyph;
    const label=doc.createElement('strong');label.textContent=name;
    const sub=doc.createElement('small');sub.textContent=hint;
    button.append(sphere,label,sub);
    button.addEventListener('click',()=>onSelect(id));
    buttons.set(id,button);row.append(button);
  }
  dock.append(top,row);
  home.append(dock); // Never a child of the moving orbit / hitboxes.
  return Object.freeze({
    render(selected,effective,osReduced){
      for(const [id,button] of buttons){
        const active=id===selected;
        button.setAttribute('aria-pressed',String(active));
        button.classList.toggle('is-selected',active);
      }
      status.textContent=osReduced
        ? 'СИСТЕМА · МИНИМУМ ДВИЖЕНИЯ'
        : selected==='AUTO'
          ? 'AUTO · '+({'MAX':'MAX WOW','BALANCED':'CINEMA','ECO':'ECO'}[effective]||effective)
          : 'РУЧНОЙ · '+(buttons.get(selected)?.querySelector('strong')?.textContent||'CINEMA');
    },
    destroy(){dock.remove();}
  });
}

function mountNoxFilm(stage,view,doc){
 const noop=Object.freeze({setVisible(){},setProfile(){},destroy(){}});
 let canvas=null,gl=null,program=null,buffer=null,observer=null,raf=0;
 let visible=true,disposed=false,contextLost=false,mode='BALANCED',last=0,start=0,signal=0;
 const reduced=view.matchMedia?.('(prefers-reduced-motion: reduce)');
 const forced=view.matchMedia?.('(forced-colors: active)');
 const fps=Object.freeze({MAX:30,BALANCED:18,ECO:0,REDUCED:0});
 const vertex=[
 'attribute vec2 a_pos;',
 'void main(){gl_Position=vec4(a_pos,0.,1.);}'
 ].join('\n');
 const fragment=[
 'precision mediump float;',
 'uniform vec2 u_size; uniform float u_clock; uniform float u_gain; uniform float u_signal;',
 'float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}',
 'float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);',
 'return mix(mix(h(i),h(i+vec2(1.,0.)),f.x),mix(h(i+vec2(0.,1.)),h(i+1.),f.x),f.y);}',
 'void main(){',
 'vec2 p=(gl_FragCoord.xy-.5*u_size)/max(1.,min(u_size.x,u_size.y));',
 'float r=length(p),a=atan(p.y,p.x),t=u_clock*.17;',
 'float turbulence=n(p*4.7+vec2(t,-t*.6));',
 'float warp=sin(a*4.+r*15.-t*2.)*.018+(turbulence-.5)*.055;',
 'float ring=exp(-pow((r-.29-warp)/.048,2.));',
 'float photon=exp(-pow((r-.19+sin(a*2.+t)*.01)/.018,2.));',
 'float lace=exp(-pow((r-.44+.018*sin(a*9.+t*1.6))/.043,2.));',
 'float jets=exp(-abs(p.x)*19.)*smoothstep(.18,.48,abs(p.y))*(.4+.4*sin(p.y*13.-t*3.));',
 'float veil=n(p*2.2+vec2(-t*.4,t*.18))*.45*exp(-r*2.8);',
 'float filaments=pow(max(0.,sin(a*11.-r*27.+t*3.)),8.)*exp(-r*2.2);',
 'vec2 starCell=floor((p+1.)*vec2(132.,96.));',
 'float dust=step(.994,h(starCell))*(.4+.6*sin(t*1.6+h(starCell)*6.28));',
 'vec3 cold=vec3(.12,.43,.67)*(veil+filaments*.36+dust*.21);',
 'vec3 hot=vec3(1.,.35,.09)*(ring*.57+lace*.12+jets*.18);',
 'vec3 color=(cold+hot+vec3(.68,.81,1.)*photon*.22)*u_gain*(1.+u_signal*.18);',
 'float fade=1.-smoothstep(.58,1.2,r);',
 'float alpha=clamp((ring*.28+photon*.15+lace*.06+veil*.18+jets*.06+dust*.1+filaments*.06)*u_gain*fade,0.,.57);',
 'gl_FragColor=vec4(color,alpha);',
 '}'
 ].join('\n');
 function paused(){return disposed||contextLost||!visible||doc.hidden||mode==='REDUCED'||
   reduced?.matches===true||forced?.matches===true;}
 function stop(){if(raf){view.cancelAnimationFrame(raf);raf=0;}}
 function cleanup(){
   stop();observer?.disconnect();
   view.removeEventListener('resize',onResize);
   doc.removeEventListener('visibilitychange',onVisibility);
   canvas?.removeEventListener('webglcontextlost',onLost);
   try{if(gl){if(buffer)gl.deleteBuffer(buffer);if(program)gl.deleteProgram(program);}}catch(_){}
   canvas?.remove();gl=null;canvas=null;program=null;buffer=null;
 }
 function shader(kind,code){
   const item=gl.createShader(kind);if(!item)throw Error('NOX_FILM_SHADER_ALLOC_HOLD');
   gl.shaderSource(item,code);gl.compileShader(item);
   if(!gl.getShaderParameter(item,gl.COMPILE_STATUS)){gl.deleteShader(item);throw Error('NOX_FILM_SHADER_HOLD');}
   return item;
 }
 function resize(){
   if(!canvas||!gl)return;
   const rect=stage.getBoundingClientRect();if(rect.width<=0||rect.height<=0)return;
   const scale=Math.min(1.5,Math.max(1,view.devicePixelRatio||1));
   const w=Math.max(1,Math.min(2048,Math.round(rect.width*scale)));
   const h=Math.max(1,Math.min(1200,Math.round(rect.height*scale)));
   if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);}
 }
 function paint(ms){
   if(paused()||!gl||!canvas)return;resize();gl.clear(gl.COLOR_BUFFER_BIT);
   gl.uniform2f(gl.getUniformLocation(program,'u_size'),canvas.width,canvas.height);
   gl.uniform1f(gl.getUniformLocation(program,'u_clock'),ms*.001);
   gl.uniform1f(gl.getUniformLocation(program,'u_gain'),mode==='MAX'?1.:mode==='ECO'?.33:.66);
   gl.uniform1f(gl.getUniformLocation(program,'u_signal'),signal);
   gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
 }
 function frame(now){raf=0;if(paused()||mode==='ECO')return;
   if(now-last>=1000/fps[mode]){last=now;paint(now-start);}
   raf=view.requestAnimationFrame(frame);
 }
 function wake(){stop();if(paused())return;
   if(mode==='ECO'){paint(0);return;}last=0;raf=view.requestAnimationFrame(frame);
 }
 function onResize(){if(!paused())wake();}
 function onVisibility(){if(doc.hidden)stop();else wake();}
 function onLost(event){event.preventDefault();contextLost=true;stop();
   if(canvas)canvas.dataset.noxFilm='context-lost-hold';
 }
 try{
   canvas=doc.createElement('canvas');canvas.className='nox-cinema-film';
   canvas.dataset.noxFilm='decorative-only';canvas.setAttribute('aria-hidden','true');
   stage.prepend(canvas);
   gl=canvas.getContext('webgl',{alpha:true,antialias:false,depth:false,stencil:false,
     preserveDrawingBuffer:false,powerPreference:'low-power'});
   if(!gl){canvas.remove();return noop;}
   const vs=shader(gl.VERTEX_SHADER,vertex),fs=shader(gl.FRAGMENT_SHADER,fragment);
   program=gl.createProgram();gl.attachShader(program,vs);gl.attachShader(program,fs);
   gl.linkProgram(program);gl.deleteShader(vs);gl.deleteShader(fs);
   if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error('NOX_FILM_LINK_HOLD');
   buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
   gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
   gl.useProgram(program);
   const location=gl.getAttribLocation(program,'a_pos');if(location<0)throw Error('NOX_FILM_ATTRIBUTE_HOLD');
   gl.enableVertexAttribArray(location);gl.vertexAttribPointer(location,2,gl.FLOAT,false,0,0);
   gl.disable(gl.DEPTH_TEST);gl.clearColor(0,0,0,0);
   canvas.addEventListener('webglcontextlost',onLost,false);
   view.addEventListener('resize',onResize,{passive:true});
   doc.addEventListener('visibilitychange',onVisibility);
   if(typeof view.ResizeObserver==='function'){
     observer=new view.ResizeObserver(onResize);observer.observe(stage);
   }
   start=view.performance.now();resize();wake();
   return Object.freeze({
     setVisible(value){visible=value===true;if(!visible)stop();else wake();},
     setProfile(value,nativeState){
       if(!Object.prototype.hasOwnProperty.call(fps,value))return false;
       mode=value;
       // State derived only from the existing validated renderer, never from arbitrary DOM.
       signal=['streaming','training','speaking'].includes(nativeState)?1:0;
       if(canvas)canvas.dataset.noxFilmProfile=value.toLowerCase();
       wake();return true;
     },
     destroy(){if(disposed)return;disposed=true;cleanup();}
   });
 }catch(_){cleanup();return noop;}
}

function boot(){
  try{mountApprovedHome(document)}
  catch(error){
    // Local interface should remain usable even if a visual integration is held.
    // Never overwrite a user-visible project success status or fabricate telemetry.
    const h=document.getElementById('home');
    if(h)h.dataset.noxCinemaFx='hold';
    console.warn('NOX D02 CINEMA FX HOLD',error?.message||'UNKNOWN');
  }
}
if(typeof document!=='undefined'){
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
}