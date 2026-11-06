'use strict';
/* D04: R8 WebGL2 runtime fallback contract. SOURCE_ONLY. No user GPU or live WebView2 claim. */
const fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.resolve(__dirname,'src','index.html'),'utf8');
const match=html.match(/<script id="nox-liquid-core">([\s\S]*?)<\/script>/);
function check(condition,label){if(!condition)throw Error('D04_GPU_FALLBACK_HOLD '+label);}
check(!!match,'GPU script');
check(html.includes('window.chrome.webview.postMessage({type,...data})'),'existing native IPC unchanged');
const render=new Function('document','window','performance','requestAnimationFrame','cancelAnimationFrame','console',match[1]);
function exercise(kind){
  let gpuFrames=0,cpuFrames=0,prevented=false,ticks=0,seq=0,userReduced=false,maxBlur=0,errorSamples=0;
  const queue=new Map(),docEvents={},sphere={dataset:{}};
  const gl={
    NO_ERROR:0,OUT_OF_MEMORY:1285,
    VERTEX_SHADER:1,FRAGMENT_SHADER:2,COMPILE_STATUS:3,LINK_STATUS:4,
    ARRAY_BUFFER:5,STATIC_DRAW:6,FLOAT:7,COLOR_BUFFER_BIT:8,TRIANGLES:9,
    createShader(){return {};},shaderSource(){},compileShader(){},
    getShaderParameter(){return kind!=='compileFail';},
    getShaderInfoLog(){return 'FAKE_SHADER_COMPILE_ERROR';},
    createProgram(){return {};},attachShader(){},linkProgram(){},
    getProgramParameter(){return true;},getProgramInfoLog(){return '';},
    deleteShader(){},getUniformLocation(){return {};},
    createBuffer(){if(kind==='setupFail')throw Error('GPU_BUFFER_ALLOC_FAILED');return {};},bindBuffer(){},bufferData(){},
    getAttribLocation(){return 0;},enableVertexAttribArray(){},vertexAttribPointer(){},
    viewport(){if(kind==='viewportFail')throw Error('GPU_VIEWPORT_DEVICE_LOST');},useProgram(){},uniform2f(){},uniform1f(){if(kind==='uniformFail')throw Error('GPU_UNIFORM_DEVICE_LOST');},
    clearColor(){},clear(){},drawArrays(){if(kind==='drawFail')throw Error('GPU_DEVICE_LOST');gpuFrames++;},
    isContextLost(){return false;},
    getError(){errorSamples++;return kind==='glError'||(kind==='lateGlError'&&errorSamples===2)?this.OUT_OF_MEMORY:this.NO_ERROR;}
  };
  function makeCanvas(){
    const events={};
    const canvas={width:0,height:0,parentElement:sphere,
      getBoundingClientRect(){return {width:900,height:900};},
      getContext(type){
        if(type==='webgl2'){if(kind==='throwContext')throw Error('WEBGL_BLOCKED');return kind==='noGpu'||kind==='reducedCpu'?null:gl;}
        if(type==='2d')return new Proxy({
          createRadialGradient(){return {addColorStop(){}};},
          clearRect(){cpuFrames++;}
        },{get(target,key){return key in target?target[key]:()=>{};},set(target,key,value){target[key]=value;if(key==='shadowBlur')maxBlur=Math.max(maxBlur,Number(value));return true;}});
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
  const media={matches:kind==='reducedGpu'||kind==='reducedCpu',handlers:[],addEventListener(name,fn){if(name==='change')this.handlers.push(fn);},fire(){this.handlers.forEach(fn=>fn({matches:this.matches}));}};
  const window={devicePixelRatio:1,matchMedia(){return media;},addEventListener(){}};
  const requestAnimationFrame=fn=>{const id=++seq;queue.set(id,fn);return id;};
  const cancelAnimationFrame=id=>queue.delete(id);
  render(document,window,{now(){return 0;}},requestAnimationFrame,cancelAnimationFrame,{warn(){}});
  function tick(){check(queue.size>0,kind+' scheduled frame');const [id,fn]=queue.entries().next().value;queue.delete(id);fn(100+(++ticks)*140);}
  if(kind==='reducedGpu'||kind==='reducedCpu'){
    tick();check(queue.size===0,kind+' first static frame stopped');
    check((kind==='reducedGpu'?gpuFrames:cpuFrames)===1,kind+' first static frame rendered');
    media.matches=false;media.fire();tick();check(queue.size===1,kind+' OS reduce off resumes');
    userReduced=true;window.noxVisual.refresh();tick();check(queue.size===0,kind+' user reduce overrides OS');
    userReduced=false;window.noxVisual.refresh();tick();check(queue.size===1,kind+' user reduce off resumes');
    media.matches=true;
    const before=kind==='reducedGpu'?gpuFrames:cpuFrames;
    media.fire();tick();
    check((kind==='reducedGpu'?gpuFrames:cpuFrames)===before+1,kind+' OS reduce redraws static pose');
    check(queue.size===0,kind+' OS reduce stops RAF');
    return;
  }
  if(['ok','contextLost','drawFail','viewportFail','uniformFail','glError','lateGlError'].includes(kind)){
    check(sphere.dataset.fx==='active','GPU path initialized');
    if(kind!=='ok'){window.noxVisual.setMode('MAX');window.noxVisual.setEnergy(true);}
    tick();
    if(kind==='ok'){check(gpuFrames>0,'GPU path drew');window.noxVisual.setMode('ECO');tick();check(gpuFrames>1,'ECO GPU mode');return;}
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
  if(['contextLost','compileFail','drawFail','setupFail','viewportFail','uniformFail','glError','lateGlError'].includes(kind))check(currentCanvas!==original,'GPU canvas replaced');
  tick();check(cpuFrames>0,kind+' 2D frame drawn');
  if(['contextLost','drawFail','viewportFail','uniformFail','glError','lateGlError'].includes(kind)){
    check(currentCanvas.width===650,kind+' MAX render resolution survived fallback');
    check(maxBlur>50,kind+' active generation energy survived fallback');
  }
  window.noxVisual.setMode('ECO');tick();
  document.hidden=true;document.fire('visibilitychange');
  check(queue.size===0,kind+' background frames paused');
  document.hidden=false;document.fire('visibilitychange');tick();
  check(cpuFrames>=3,kind+' visible redraw');
}
for(const kind of ['noGpu','throwContext','compileFail','setupFail','ok','contextLost','drawFail','viewportFail','uniformFail','glError','lateGlError','reducedGpu','reducedCpu'])exercise(kind);
check(html.includes("case 'complete':busy=false;activeChatId=null;$('generation').classList.remove('on');window.noxVisual?.setEnergy(false);"),'native completion clears renderer energy');
console.log('D04 R8 GPU failover SOURCE_ONLY: 13 scenarios PASS (GL setup, viewport, uniform, draw, context loss, MAX/energy retention, reduced motion); owner GPU NOT_TESTED');
