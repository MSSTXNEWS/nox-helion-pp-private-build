// Shared crownless eclipse material for contextual pages. One renderer per host/page.
import * as THREE from 'three';
import {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
import {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
import {UnrealBloomPass} from 'three/addons/postprocessing/UnrealBloomPass.js';
import {OutputPass} from 'three/addons/postprocessing/OutputPass.js';
import {planetVertex,planetFragment,skyVertex,skyFragment} from './eclipse-materials.mjs';
import {industrialUniforms,installIndustrialEffects} from './industrial-effects.mjs';
const contextualHost=document.querySelector('[data-nox-eclipse]') || document.querySelector('.chat-conversation');
const chatFullPage=document.body.dataset.page==='chat';
const globalPage=document.body.classList.contains('nox-shared-glass')||['chat','memory','system','dashboard','projects','install','cinema','settings'].includes(document.body.dataset.page);
const host=(contextualHost||globalPage)?document.body:null,starfieldOnly=false;
const fullViewport=Boolean(host);
const budgets={MAX:{fps:40,ratio:1.75,pixels:5000000,bloom:.42},BALANCED:{fps:24,ratio:1.35,pixels:2800000,bloom:.3},ECO:{fps:12,ratio:.7,pixels:480000,bloom:0}};
if(host && !host.querySelector('canvas.nox-context-eclipse'))mount(host,starfieldOnly);
function mount(host,starfieldOnly=false){
 host.classList.add(fullViewport?'nox-eclipse-page':'nox-eclipse-host');if(fullViewport)host.classList.add('nox-eclipse-fullpage');const canvas=document.createElement('canvas');canvas.className='nox-context-eclipse';canvas.setAttribute('aria-hidden','true');if(fullViewport){canvas.classList.add(starfieldOnly?'nox-page-stars':'nox-page-scene');Object.assign(canvas.style,{position:'fixed',inset:'0',width:'100vw',height:'100vh',pointerEvents:'none',zIndex:'-2'});}host.prepend(canvas);
 const reduced=matchMedia('(prefers-reduced-motion: reduce)'),activity={value:0};
 let sceneDiameter=0;
 let mode='BALANCED',motion='system',typing=document.documentElement.dataset.typing==='true'||Boolean(document.activeElement?.closest?.('input,textarea,[contenteditable="true"],loquix-chat-composer')),busy=false,runtimeKnown=false,runtimeBusy=false,runtimeActivity=false,runtimePending=false,runtimeTimer=0,runtimePhases={},voiceActive=false,memoryActive=false,mediaActive=[...document.querySelectorAll('video,audio')].some(media=>!media.paused&&!media.ended),visible=true,suspended=false,disposed=false,lost=false,raf=0,last=0,time=0,frames=0,quietUntil=0,renderer,scene,camera,composer,bloom,planet,sky,industrial,background,backgroundFailure=null,resizeObserver,intersection,trainingObserver;
 function settings(values={}){
   const requested=String(document.documentElement.dataset.noxDemoMode||values.mode||'').toUpperCase();
   if(requested in budgets)mode=requested;
   const visualTheme={gold:'amber',copper:'ember',glacier:'arctic',ion:'arctic',amethyst:'void-purple',platinum:'graphite'}[document.documentElement.dataset.noxColor];
   industrial?.palette({...window.NoxWorkspace?.settings,...(visualTheme?{theme:visualTheme}:{}),...values});
   if(['reduce','full','system'].includes(values.motion))motion=values.motion;
   resize();run();
 }
 function still(){return motion==='reduce'||(motion==='system'&&reduced.matches);}
 function budgetName(){
   // Native owner activity always wins. Unknown runtime cannot claim full MAX GPU priority.
   return busy||runtimeBusy?'ECO':!runtimeKnown&&mode==='MAX'?'BALANCED':mode;
 }
 function cap(){return budgets[budgetName()]||budgets.BALANCED;}
 function backgroundFallback(error){backgroundFailure=String(error?.message||error).slice(0,180);try{background?.dispose();}catch{}background=null;if(sky?.material.uniforms.uBackgroundMix)sky.material.uniforms.uBackgroundMix.value=0;renderer?.setRenderTarget(null);}
 function draw(){if(disposed||suspended||lost||!composer||!visible||document.hidden)return;activity.value=(mediaActive||still()||typing||performance.now()<quietUntil)?0:((busy||runtimeActivity) ? .65 : (voiceActive ? .35 : memoryActive ? .22 : 0));sky.material.uniforms.clockTime.value=time;planet.rotation.y=time*.024;planet.rotation.x=.12+Math.sin(time*.073)*.024;industrial?.update({mode:budgetName(),quiet:mediaActive||still()||typing||performance.now()<quietUntil});try{background?.update({time,mode:budgetName(),quiet:busy||runtimeBusy||!runtimeKnown||mediaActive||still()||typing||performance.now()<quietUntil,width:renderer.domElement.width,height:renderer.domElement.height});}catch(error){backgroundFallback(error);}composer.render();if(window.NoxCoreBadge?.subscribed)window.dispatchEvent(new CustomEvent('nox-scene-frame',{detail:{canvas,cx:.5,cy:.5,diameterPixels:sceneDiameter*renderer.getPixelRatio(),identity:'ACTUAL_THREE_MASTER',mode:budgetName(),reducedMotion:still()||mediaActive}}));frames++;host.dataset.sceneState='READY';}
 function resize(){if(!renderer||!composer||lost||disposed)return;const w=fullViewport?window.innerWidth:host.clientWidth,h=fullViewport?window.innerHeight:host.clientHeight;if(!w||!h)return;const budget=cap(),ratio=Math.min(devicePixelRatio||1,budget.ratio,Math.sqrt(budget.pixels/(w*h))),diameter=Math.min(h*(document.body.dataset.page==='chat'?.64:.74),w*.88),sw=w*2/diameter,sh=h*2/diameter;sceneDiameter=diameter;camera.left=-sw/2;camera.right=sw/2;camera.top=sh/2;camera.bottom=-sh/2;camera.updateProjectionMatrix();sky.material.uniforms.span.value.set(sw,sh);renderer.setPixelRatio(ratio);renderer.setSize(w,h,false);composer.setPixelRatio(ratio);composer.setSize(w,h);bloom.enabled=budget.bloom>0;bloom.strength=budget.bloom;draw();}
 function run(){cancelAnimationFrame(raf);raf=0;last=0;if(disposed||suspended||lost||!visible||document.hidden)return;if(mediaActive||still()){draw();return;}raf=requestAnimationFrame(frame);}
 function frame(now){if(disposed||suspended||lost||!visible||document.hidden||mediaActive||still())return;const period=1000/(cap().fps*(typing?.2:1));if(!last||now-last>=period-1){time+=last?Math.min((now-last)/1000,.3)*(typing?.2:1):0;last=now;draw();}raf=requestAnimationFrame(frame);}
 function busyChanged(value){if(busy===value)return;busy=value;resize();run();}
 async function pollRuntime(){
   if(disposed||suspended||document.hidden||!visible||runtimePending)return;runtimePending=true;
   try{
     if(window.NOX_NATIVE_OWNER===true){const snapshot=await window.NoxOwnerRuntime.read();runtimeKnown=snapshot.activity.workload_known;runtimeBusy=snapshot.activity.busy;runtimeActivity=snapshot.activity.inference_active||snapshot.trainer?.actual_gpu_execution_verified_by_this_read===true;runtimePhases=snapshot.activity.phases;return;}
     const snapshots=await Promise.allSettled(['/api/nox/activity','/api/training/status'].map(async url=>{const response=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(5500)});if(!response.ok)throw Error('RUNTIME_UNAVAILABLE');return response.json();}));
     const inference=snapshots[0].value,training=snapshots[1].value;runtimePhases=inference?.phases&&typeof inference.phases==='object'?inference.phases:{};
     runtimeKnown=Boolean(snapshots.every(x=>x.status==='fulfilled')&&typeof inference?.active_generations==='number'&&Number.isFinite(inference.active_generations)&&training?.process_inventory_verified===true);
     runtimeActivity=(inference?.active_generations>0)||training?.verified_live===true;
     runtimeBusy=runtimeActivity||Boolean(training?.trainer_processes?.length)||training?.phase==='RUNNING';
   }catch{runtimeKnown=false;runtimeBusy=false;runtimeActivity=false;}finally{runtimePending=false;window.dispatchEvent(new CustomEvent('nox-runtime-observed',{detail:{known:runtimeKnown,busy:busy||runtimeBusy,phases:runtimePhases}}));resize();run();}
 }
 const onMedia=e=>{const active=e.detail?.active===true;if(active===mediaActive)return;mediaActive=active;run();},onVoice=e=>{voiceActive=e.detail?.active===true;draw();},onMemory=e=>{memoryActive=e.detail?.active===true;draw();},onSettings=e=>settings(e.detail),onTyping=e=>{typing=e.detail===true;run();},onActivity=e=>busyChanged(e.detail?.active===true),onStop=()=>{quietUntil=performance.now()+2000;voiceActive=false;memoryActive=false;activity.value=0;draw();},onVisibility=()=>{run();if(!document.hidden)void pollRuntime();};
 try{
   renderer=new THREE.WebGLRenderer({canvas,antialias:false,powerPreference:'low-power'});renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=.95;
   scene=new THREE.Scene();camera=new THREE.OrthographicCamera(-2,2,2,-2,.1,30);camera.position.z=8;
   const uniforms={...industrialUniforms(),uBackgroundMap:{value:null},uBackgroundMix:{value:0},clockTime:{value:0},activity,span:{value:new THREE.Vector2()},center:{value:new THREE.Vector2(.5,.5)}};
   sky=new THREE.Mesh(new THREE.PlaneGeometry(2,2),new THREE.ShaderMaterial({vertexShader:skyVertex,fragmentShader:(starfieldOnly?'#define NOX_STARFIELD_ONLY\n':'')+skyFragment,uniforms,depthWrite:false,depthTest:false}));sky.frustumCulled=false;sky.renderOrder=-1;scene.add(sky);
   planet=new THREE.Mesh(new THREE.SphereGeometry(1,80,56),new THREE.ShaderMaterial({vertexShader:planetVertex,fragmentShader:planetFragment,uniforms,extensions:{derivatives:true}}));planet.visible=!starfieldOnly;scene.add(planet);
   composer=new EffectComposer(renderer);composer.addPass(new RenderPass(scene,camera));bloom=new UnrealBloomPass(new THREE.Vector2(1,1),.3,.49,.65);composer.addPass(bloom);composer.addPass(new OutputPass());industrial=installIndustrialEffects({scene,renderer,composer,uniforms,starfieldOnly,onChange:draw});industrial.palette(window.NoxWorkspace?.settings||{});
   import('./nox-background-engine.mjs').then(({installBackgroundEngine})=>{if(disposed)return;try{background=installBackgroundEngine({renderer,uniforms,onChange:draw});draw();}catch(error){backgroundFallback(error);draw();}}).catch(error=>{if(!disposed)backgroundFallback(error);});
   canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();lost=true;cancelAnimationFrame(raf);host.dataset.sceneState='HOLD';});
   canvas.addEventListener('webglcontextrestored',()=>{lost=false;resize();run();});
   if(fullViewport){window.addEventListener('resize',resize);}else{resizeObserver=new ResizeObserver(resize);resizeObserver.observe(host);intersection=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;run();},{threshold:0});intersection.observe(host);}
   if(document.body.dataset.page==='training'){trainingObserver=new MutationObserver(()=>busyChanged(document.body.dataset.trainingActive==='true'));trainingObserver.observe(document.body,{attributes:true,attributeFilter:['data-training-active']});busyChanged(document.body.dataset.trainingActive==='true');}
   window.addEventListener('nox-media-activity',onMedia);window.addEventListener('nox-voice-activity',onVoice);window.addEventListener('nox-memory-activity',onMemory);window.addEventListener('nox-settings',onSettings);window.addEventListener('nox-typing',onTyping);window.addEventListener('nox-chat-activity',onActivity);window.addEventListener('nox-stop-requested',onStop);document.addEventListener('visibilitychange',onVisibility);reduced.addEventListener('change',run);
   settings(window.NoxWorkspace?.settings||{});resize();run();void pollRuntime();runtimeTimer=setInterval(pollRuntime,8000);
 }catch(error){host.dataset.sceneState='HOLD';lost=true;cancelAnimationFrame(raf);canvas.hidden=true;console.warn('NOX contextual scene unavailable:',error.message);}
 window.noxContextSceneDiagnostics=()=>({starfieldOnly,fullPage:fullViewport,host:fullViewport?'page':'contextual',viewport:fullViewport?[window.innerWidth,window.innerHeight]:[host.clientWidth,host.clientHeight],state:host.dataset.sceneState||'INITIALIZING',frames,time,mode,budget:budgetName(),suspended,runtimeKnown,runtimeBusy,runtimePhases:{...runtimePhases},voiceActive,memoryActive,mediaActive,reducedMotion:still(),typing,busy,canvasCount:host.querySelectorAll('canvas.nox-context-eclipse').length,threeRevision:THREE.REVISION,industrial:industrial?.diagnostics(),background:background?.diagnostics()||{status:'CLASSIC_FALLBACK',reason:backgroundFailure},passes:composer?.passes.map(p=>({type:p.constructor.name,enabled:p.enabled}))||[]});
 window.addEventListener('pagehide',event=>{suspended=true;cancelAnimationFrame(raf);clearInterval(runtimeTimer);if(event.persisted)return;disposed=true;if(fullViewport)window.removeEventListener('resize',resize);resizeObserver?.disconnect();intersection?.disconnect();trainingObserver?.disconnect();window.removeEventListener('nox-media-activity',onMedia);window.removeEventListener('nox-voice-activity',onVoice);window.removeEventListener('nox-memory-activity',onMemory);window.removeEventListener('nox-settings',onSettings);window.removeEventListener('nox-typing',onTyping);window.removeEventListener('nox-chat-activity',onActivity);window.removeEventListener('nox-stop-requested',onStop);document.removeEventListener('visibilitychange',onVisibility);reduced.removeEventListener('change',run);background?.dispose();industrial?.dispose();scene?.traverse(o=>{o.geometry?.dispose();o.material?.dispose();});composer?.passes.forEach(p=>p.dispose?.());composer?.dispose();renderer?.dispose();});
 window.addEventListener('pageshow',event=>{if(event.persisted){suspended=false;run();void pollRuntime();clearInterval(runtimeTimer);runtimeTimer=setInterval(pollRuntime,8000);}});
}
