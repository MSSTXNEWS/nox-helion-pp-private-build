'use strict';
/* D04: R8 WebGL2 -> Canvas2D -> static CSS fail-closed lifecycle. SOURCE_ONLY, no owner GPU claim. */
const fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.resolve(__dirname,'src','index.html'),'utf8');
const match=html.match(/<script id="nox-liquid-core">([\s\S]*?)<\/script>/);
function check(condition,label){if(!condition)throw Error('D04_GPU_FALLBACK_HOLD '+label);}
check(!!match,'GPU script');
// Execute the actual native WebView2 bridge wrapper. Its fail-closed dispatch
// was hardened independently by D01, so asserting a stale literal would
// wrongly block Windows compilation despite preserving native message routing.
const bridgeMatch=html.match(/const post=\(type,data=\{\}\)=>(\{[\s\S]*?\});\s*let responseBox=/);
check(!!bridgeMatch,'original native IPC wrapper present');
const makePost=new Function('window','$','return (type,data={})=>'+bridgeMatch[1]);
const nativeProbe=bridge=>{
  const status={textContent:''};
  const window=bridge===null?{}:{chrome:{webview:bridge}};
  return {post:makePost(window,id=>{check(id==='status','IPC status target');return status;}),status};
};
const sent=[];
const live=nativeProbe({postMessage:event=>sent.push(event)});
check(live.post('chat',{text:'D04 bridge probe',requestId:'req-d04'})===true,'native chat dispatch accepted');
check(sent.length===1&&sent[0].type==='chat'&&sent[0].requestId==='req-d04'&&sent[0].text==='D04 bridge probe','native chat payload preserved');
check(live.post('stop',{requestId:'req-d04'})===true&&sent.length===2&&sent[1].type==='stop'&&sent[1].requestId==='req-d04','native STOP ownership preserved');
const missing=nativeProbe(null);
check(missing.post('chat',{text:'offline'})===false&&missing.status.textContent==='NATIVE BRIDGE OFFLINE','missing native IPC must fail closed');
const broken=nativeProbe({postMessage(){throw Error('DISPATCH_REJECTED')}});
check(broken.post('chat',{text:'offline'})===false&&broken.status.textContent==='NATIVE BRIDGE DISPATCH FAILED','native dispatch exceptions must fail closed');
const render=new Function('document','window','performance','requestAnimationFrame','cancelAnimationFrame','console',match[1]);
function exercise(kind){
  let gpuFrames=0,cpuFrames=0,prevented=false,ticks=0,seq=0,userReduced=false,maxBlur=0,errorSamples=0;
  const queue=new Map(),docEvents={},sphere={dataset:{}};
  const gl={
    NO_ERROR:0,OUT_OF_MEMORY:1285,
    VERTEX_SHADER:1,FRAGMENT_SHADER:2,COMPILE_STATUS:3,LINK_STATUS:4,
    ARRAY_BUFFER:5,STATIC_DRAW:6,FLOAT:7,COLOR_BUFFER_BIT:8,TRIANGLES:9,
    createShader(){return kind==='shaderNull'?null:{};},shaderSource(){},compileShader(){},
    getShaderParameter(){return kind!=='compileFail';},
    getShaderInfoLog(){return 'FAKE_SHADER_COMPILE_ERROR';},
    createProgram(){return kind==='programNull'?null:{};},attachShader(){},linkProgram(){},
    getProgramParameter(){return true;},getProgramInfoLog(){return '';},
    deleteShader(){},getUniformLocation(){return kind==='uniformNull'?null:{};},
    createBuffer(){if(kind==='setupFail')throw Error('GPU_BUFFER_ALLOC_FAILED');return kind==='bufferNull'?null:{};},bindBuffer(){},bufferData(){},
    getAttribLocation(){return kind==='attributeMissing'?-1:0;},enableVertexAttribArray(){},vertexAttribPointer(){},
    viewport(){if(kind==='viewportFail')throw Error('GPU_VIEWPORT_DEVICE_LOST');},useProgram(){},uniform2f(){},uniform1f(){if(kind==='uniformFail')throw Error('GPU_UNIFORM_DEVICE_LOST');},
    clearColor(){},clear(){},drawArrays(){if(kind==='drawFail'||kind==='drawFail2dLoss')throw Error('GPU_DEVICE_LOST');gpuFrames++;},
    isContextLost(){return false;},
    getError(){errorSamples++;return kind==='glError'||(kind==='lateGlError'&&errorSamples===2)?this.OUT_OF_MEMORY:this.NO_ERROR;}
  };
  function makeCanvas(){
    const events={};
    const canvas={width:0,height:0,parentElement:sphere,
      getBoundingClientRect(){return {width:900,height:900};},
      getContext(type){
        if(type==='webgl2'){if(kind==='throwContext')throw Error('WEBGL_BLOCKED');return ['noGpu','noGpu2dLoss','reducedCpu','legacyReducedCpu','noMediaApiCpu','queryThrowsCpu','observerThrowsCpu','observerThrowsLegacyCpu','no2d','throw2d','draw2dFail','matchesGetterCpu'].includes(kind)?null:gl;}
        if(type==='2d'){
          if(kind==='throw2d')throw Error('CANVAS_2D_CONTEXT_BLOCKED');
          if(kind==='no2d')return null;
          return new Proxy({
          createRadialGradient(){return {addColorStop(){}};},
          clearRect(){if(kind==='draw2dFail')throw Error('CANVAS_2D_DRAW_BLOCKED');cpuFrames++;}
        },{get(target,key){return key in target?target[key]:()=>{};},set(target,key,value){target[key]=value;if(key==='shadowBlur')maxBlur=Math.max(maxBlur,Number(value));return true;}});}
        return null;
      },
      addEventListener(key,callback){events[key]=callback;},
      fire(key,event){if(events[key])events[key](event);},
      cloneNode(){return makeCanvas();},
      replaceWith(replacement){currentCanvas=replacement;}
    };
    return canvas;
  }
  const original=makeCanvas();
  let currentCanvas=original;
  const document={
    hidden:false,
    body:{classList:{contains(name){return name==='reduced'&&userReduced;}}},
    getElementById(id){return id==='helionFx'?currentCanvas:null;},
    addEventListener(name,fn){(docEvents[name]??=[]).push(fn);},
    fire(name){(docEvents[name]||[]).forEach(fn=>fn());}
  };
  const media={
    matches:['reducedGpu','reducedCpu','legacyReducedGpu','legacyReducedCpu','observerThrowsLegacyGpu','observerThrowsLegacyCpu'].includes(kind),
    handlers:[],
    addEventListener(name,fn){if(kind.startsWith('observerThrows'))throw Error('MQL_LISTENER_BLOCKED');if(name==='change')this.handlers.push(fn);},
    addListener(fn){this.handlers.push(fn);},
    fire(){this.handlers.forEach(fn=>fn({matches:this.matches}));}
  };
  if(kind.startsWith('legacyReduced'))media.addEventListener=undefined;
  if(kind==='matchesGetterGpu'||kind==='matchesGetterCpu'){
    Object.defineProperty(media,'matches',{get(){throw Error('MQL_MATCHES_BLOCKED');}});
  }
  const window={devicePixelRatio:1,matchMedia(){if(kind.startsWith('queryThrows'))throw Error('MQL_QUERY_BLOCKED');return media;},addEventListener(){}};
  if(kind.startsWith('noMediaApi'))window.matchMedia=undefined;
  const requestAnimationFrame=fn=>{const id=++seq;queue.set(id,fn);return id;};
  const cancelAnimationFrame=id=>queue.delete(id);
  const warnings=[];
  render(document,window,{now(){return 0;}},requestAnimationFrame,cancelAnimationFrame,{warn:(...args)=>warnings.push(args.map(String).join(' '))});
  function tick(){check(queue.size>0,kind+' scheduled frame');const [id,fn]=queue.entries().next().value;queue.delete(id);fn(100+(++ticks)*140);}
  if(kind==='matchesGetterGpu'||kind==='matchesGetterCpu'){
    const gpu=kind==='matchesGetterGpu';
    check(sphere.dataset.fx===(gpu?'active':'canvas2d'),kind+' renderer initialized');
    tick();
    check(queue.size===0,kind+' unknown OS motion uses static accessible pose');
    check(warnings.filter(x=>x.includes('reduced-motion state inaccessible')).length===1,kind+' only one warning');
    window.noxVisual.setMode('MAX');tick();
    window.noxVisual.setEnergy(true);tick();
    check(queue.size===0,kind+' no hot RAF loop after setting changes');
    check(warnings.filter(x=>x.includes('reduced-motion state inaccessible')).length===1,kind+' warning not repeated');
    check((gpu?gpuFrames:cpuFrames)===3,kind+' static render remains functional');
    return;
  }
  if(kind==='no2d'||kind==='throw2d'||kind==='draw2dFail'){
    if(kind==='draw2dFail')tick();
    check(sphere.dataset.fx==='disabled',kind+' must show original CSS, never fake a live Canvas2D');
    check(typeof window.noxVisual?.setMode==='function',kind+' static API remains available');
    window.noxVisual.setMode('ECO');window.noxVisual.setEnergy(true);window.noxVisual.refresh();
    check(queue.size===0,kind+' never spins retrying a failed Canvas2D');
    check(currentCanvas===original,kind+' preserves existing DOM and native IPC');
    return;
  }
  if(kind==='noGpu2dLoss'||kind==='drawFail2dLoss'){
    if(kind==='drawFail2dLoss')tick(); // Force GPU failure and Canvas2D activation.
    check(sphere.dataset.fx==='canvas2d',kind+' 2D fallback initialized');
    tick();
    const before=cpuFrames;
    currentCanvas.fire('contextlost',{});
    check(sphere.dataset.fx==='disabled',kind+' context loss reveals genuine CSS fallback');
    check(queue.size===0,kind+' context loss cancels animation rather than spinning');
    window.noxVisual.setMode('MAX');window.noxVisual.setEnergy(true);window.noxVisual.refresh();
    check(queue.size===0,kind+' cannot re-arm RAF while Canvas2D context is lost');
    document.hidden=true;document.fire('visibilitychange');
    currentCanvas.fire('contextrestored',{});
    check(queue.size===0,kind+' context restoration while hidden does not draw');
    check(sphere.dataset.fx==='canvas2d',kind+' restored 2D context');
    document.hidden=false;document.fire('visibilitychange');tick();
    check(cpuFrames===before+1,kind+' resumes with one real Canvas2D frame');
    check(currentCanvas.width===650,kind+' MAX mode retained across context loss');
    check(maxBlur>50,kind+' active generation energy retained across context loss');
    return;
  }
  if(['reducedGpu','reducedCpu','legacyReducedGpu','legacyReducedCpu','observerThrowsLegacyGpu','observerThrowsLegacyCpu'].includes(kind)){
    tick();check(queue.size===0,kind+' first static frame stopped');
    check((kind.endsWith('Gpu')?gpuFrames:cpuFrames)===1,kind+' first static frame rendered');
    media.matches=false;media.fire();tick();check(queue.size===1,kind+' OS reduce off resumes');
    userReduced=true;window.noxVisual.refresh();tick();check(queue.size===0,kind+' user reduce overrides OS');
    userReduced=false;window.noxVisual.refresh();tick();check(queue.size===1,kind+' user reduce off resumes');
    media.matches=true;
    const before=kind.endsWith('Gpu')?gpuFrames:cpuFrames;
    media.fire();tick();
    check((kind.endsWith('Gpu')?gpuFrames:cpuFrames)===before+1,kind+' OS reduce redraws static pose');
    check(queue.size===0,kind+' OS reduce stops RAF');
    return;
  }
  const healthyGpu=['ok','noMediaApiGpu','queryThrowsGpu','observerThrowsGpu'];
  if([...healthyGpu,'contextLost','drawFail','viewportFail','uniformFail','glError','lateGlError'].includes(kind)){
    check(sphere.dataset.fx==='active','GPU path initialized');
    if(!healthyGpu.includes(kind)){window.noxVisual.setMode('MAX');window.noxVisual.setEnergy(true);}
    tick();
    if(healthyGpu.includes(kind)){check(gpuFrames>0,kind+' GPU path drew');window.noxVisual.setMode('ECO');tick();check(gpuFrames>1,kind+' ECO GPU mode');document.hidden=true;document.fire('visibilitychange');window.noxVisual.setMode('MAX');window.noxVisual.setEnergy(true);window.noxVisual.refresh();check(queue.size===0,kind+' hidden GPU settings and energy must not re-arm RAF');document.hidden=false;document.fire('visibilitychange');tick();check(gpuFrames>2,kind+' GPU resumes with latest state');return;}
    if(kind==='contextLost')original.fire('webglcontextlost',{preventDefault(){prevented=true;}});
    if(kind==='lateGlError'){
      check(sphere.dataset.fx==='active','late GL error not prematurely triggered');
      for(let i=1;i<30;i++)tick();
      check(errorSamples===2,'GPU errors sampled on frames 1 and 30, not every draw');
    }
  }
  check(sphere.dataset.fx==='canvas2d',kind+' switched to live 2D');
  check(typeof window.noxVisual.setMode==='function',kind+' mode retained');
  if(kind==='contextLost')check(prevented,'context loss default prevented');
  if(['contextLost','compileFail','drawFail','setupFail','viewportFail','uniformFail','glError','lateGlError','programNull','shaderNull','uniformNull','bufferNull','attributeMissing'].includes(kind))check(currentCanvas!==original,'GPU canvas replaced');
  tick();check(cpuFrames>0,kind+' 2D frame drawn');
  if(['contextLost','drawFail','viewportFail','uniformFail','glError','lateGlError'].includes(kind)){
    check(currentCanvas.width===650,kind+' MAX render resolution survived fallback');
    check(maxBlur>50,kind+' active generation energy survived fallback');
  }
  window.noxVisual.setMode('ECO');tick();
  document.hidden=true;document.fire('visibilitychange');
  check(queue.size===0,kind+' background frames paused');
  window.noxVisual.setMode('MAX');window.noxVisual.setEnergy(true);window.noxVisual.refresh();
  check(queue.size===0,kind+' hidden Canvas2D settings and energy must not re-arm RAF');
  document.hidden=false;document.fire('visibilitychange');tick();
  check(cpuFrames>=3,kind+' visible redraw');
}
for(const kind of ['noGpu','noGpu2dLoss','drawFail2dLoss','throwContext','compileFail','setupFail','programNull','shaderNull','uniformNull','bufferNull','attributeMissing','ok','contextLost','drawFail','viewportFail','uniformFail','glError','lateGlError','reducedGpu','reducedCpu','legacyReducedGpu','legacyReducedCpu','noMediaApiGpu','noMediaApiCpu','queryThrowsGpu','queryThrowsCpu','observerThrowsGpu','observerThrowsCpu','observerThrowsLegacyGpu','observerThrowsLegacyCpu','no2d','throw2d','draw2dFail','matchesGetterGpu','matchesGetterCpu'])exercise(kind);
check(html.includes("case 'complete':busy=false;activeChatId=null;$('generation').classList.remove('on');window.noxVisual?.setEnergy(false);"),'native completion clears renderer energy');

/* A real CSS fallback must reveal the preserved original sphere, not a 14%-opacity ghost.
   This checks the production stylesheet alongside the existing GPU/2D runtime scenarios. */
check(/\.helion\[data-fx="disabled"\]\s+\.helion-core\s*\{\s*opacity\s*:\s*1\s*;?\s*\}/.test(html),'Canvas2D unavailable/lost must reveal opaque original CSS sphere');
console.log('D04 R8 GPU failover SOURCE_ONLY: 35 scenarios PASS (WebGL2, Canvas2D, CSS fallback, throwing media.matches getter, legacy/missing/rejected motion APIs, native IPC); owner GPU NOT_TESTED');
