/* NOX real 3D cinema, secondary-only: Three.js WebGL. Source candidate, not integrated EXE. */
import * as THREE from "three";
import {EffectComposer} from "three/addons/postprocessing/EffectComposer.js";
import {RenderPass} from "three/addons/postprocessing/RenderPass.js";
import {UnrealBloomPass} from "three/addons/postprocessing/UnrealBloomPass.js";
import {OutputPass} from "three/addons/postprocessing/OutputPass.js";
import {parseApprovedGLB} from "./glb.mjs";
import {recordCinemaClip} from "./record.mjs";
export const CORE_IDS=Object.freeze(["CONSCIOUSNESS","PERSONA","ATLAS","VOICE","REFLECTION","CORE","NEXUS","FORGE"]);
export const PROFILES=Object.freeze({
 ECO:Object.freeze({fps:12,dpr:1,segments:20,stars:90,bloom:false,motion:.2}),
 BALANCED:Object.freeze({fps:24,dpr:1.25,segments:32,stars:160,bloom:false,motion:.6}),
 MAX:Object.freeze({fps:30,dpr:1.5,segments:52,stars:290,bloom:true,motion:1}),
 REDUCED:Object.freeze({fps:0,dpr:1,segments:20,stars:50,bloom:false,motion:0})
});
const CORE_COLORS=[0x8bc9e7,0xe3b1eb,0xe7b87a,0x8bdace,0xb6a5ea,0xf1a77f,0xa7d2eb,0xdac08a];
const mounted=new WeakMap();
const approved=(root)=>root&&root.nodeType===1&&root.dataset?.noxWowSlot==="secondary"&&
  !(typeof root.closest==="function"&&root.closest('[data-nox-page="home"]'));
export function budget(mode,training=false,reduced=false){
 if(!Object.hasOwn(PROFILES,mode))throw Error("INVALID_3D_MODE");
 return PROFILES[reduced?"REDUCED":training?"ECO":mode];
}
const material=(color,roughness)=>new THREE.MeshPhysicalMaterial({
 color,metalness:.68,roughness,clearcoat:.88,clearcoatRoughness:.16});
function disposeScene(scene){
 scene?.traverse(o=>{o.geometry?.dispose?.();const all=Array.isArray(o.material)?o.material:[o.material];
 for(const m of all){if(!m)continue;for(const val of Object.values(m))if(val?.isTexture)val.dispose?.();m.dispose?.();}});
}
export function mountCinema3D(root,{mode="BALANCED",trainingActive=false,reducedMotion=false,onCoreSelected=null}={}){
 if(!approved(root))throw Error("D02_HOME_LOCK");
 if(mounted.has(root))throw Error("CINEMA_3D_ALREADY_MOUNTED");
 budget(mode);
 if(onCoreSelected!==null&&typeof onCoreSelected!=="function")throw Error("INVALID_CORE_CALLBACK");
 const doc=root.ownerDocument,win=doc?.defaultView;
 if(!win||typeof doc.createElement!=="function")throw Error("WEBVIEW2_DOCUMENT_REQUIRED");
 const viewport=doc.createElement("div");viewport.className="nox-real3d-scene";
 const status=doc.createElement("output");status.className="nox-real3d-status";
 status.textContent="NOX 3D DEMO · вторичная сцена";status.setAttribute("aria-live","off");
 viewport.append(status);root.append(viewport);
 let profile=mode,training=trainingActive===true,reduce=reducedMotion===true,dead=false;
 const media=win.matchMedia?.("(prefers-reduced-motion: reduce)")??null;
 const effective=()=>budget(profile,training,reduce||media?.matches);
 let renderer=null,composer=null,scene=null,camera=null,frame=0,last=0,first=0,selected=null,lost=false;
 const groups=[],orbits=[],interactive=[];
 const fallback=(reason)=>{viewport.textContent="NOX 3D unavailable · "+reason;return Object.freeze({
  ready:false,reason,coreIds:CORE_IDS,setMode:()=>false,setTrainingActive:()=>false,
  selectCore:()=>false,status:()=>({ready:false,reason}),destroy(){viewport.remove();mounted.delete(root);}
 })};
 try{
  renderer=new THREE.WebGLRenderer({antialias:false,alpha:true,powerPreference:"low-power"});
  renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.toneMapping=THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure=1.05;
  const canvas=renderer.domElement;canvas.className="nox-real3d-canvas";
  canvas.setAttribute("aria-hidden","true");viewport.insertBefore(canvas,status);
  scene=new THREE.Scene();scene.fog=new THREE.FogExp2(0x06090e,.018);
  camera=new THREE.PerspectiveCamera(39,1,.1,120);camera.position.set(0,1.7,12);
  scene.add(new THREE.HemisphereLight(0x9bb6c5,0x1b0b07,1.5));
  const hot=new THREE.PointLight(0xff9857,40,18);hot.position.set(3,3,4);scene.add(hot);
  const ice=new THREE.PointLight(0x66c4ed,34,19);ice.position.set(-4,0,3);scene.add(ice);
  const sun=new THREE.Group();sun.name="HELION";scene.add(sun);
  sun.add(new THREE.Mesh(new THREE.SphereGeometry(1.43,56,40),material(0x070b0f,.16)));
  // Surface flux is procedural shader on the approved synthetic 3D demo sphere,
  // NOT a substitute for the original artist-approved D02 image/video assets.
  const energy=new THREE.ShaderMaterial({
   uniforms:{uTime:{value:0}},
   vertexShader:"varying vec3 vP;uniform float uTime;void main(){vec3 p=position; p+=normal*.018*sin(p.x*10.+uTime)*cos(p.y*8.-uTime*.7);vP=p;gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.);}",
   fragmentShader:"precision highp float;varying vec3 vP;uniform float uTime;void main(){float waves=sin(vP.x*13.+sin(vP.y*8.+uTime*.4)*2.+uTime*.7)*sin(vP.z*8.-uTime*.4);float fissure=pow(max(0.,waves),15.);vec3 base=vec3(.008,.011,.016);vec3 color=base+fissure*vec3(.95,.23,.04);gl_FragColor=vec4(color,1.);}"
  });
  const flux=new THREE.Mesh(new THREE.SphereGeometry(1.448,56,40),energy);sun.add(flux);
  for(let i=0;i<3;i++){
   const ring=new THREE.Mesh(new THREE.TorusGeometry(1.67+i*.11,.014,8,126),
    new THREE.MeshBasicMaterial({color:i===1?0x71c9d9:0xe9a66d,transparent:true,opacity:.2+i*.06}));
   ring.rotation.x=.45+i*.3;ring.rotation.y=i*.24;sun.add(ring);
  }
  for(let i=0;i<8;i++){
   const group=new THREE.Group();group.name=CORE_IDS[i];scene.add(group);
   const mesh=new THREE.Mesh(new THREE.SphereGeometry(.32,28,20),material(CORE_COLORS[i],.26));
   mesh.userData.coreId=CORE_IDS[i];group.add(mesh);interactive.push(mesh);
   const halo=new THREE.Mesh(new THREE.TorusGeometry(.43,.012,6,70),
    new THREE.MeshBasicMaterial({color:CORE_COLORS[i],transparent:true,opacity:.5}));
   halo.rotation.x=.35+i*.04;group.add(halo);
   group.userData.halo=halo;groups.push(group);
   orbits.push({phase:i*Math.PI/4,radius:3.0+(i%3)*.55,speed:.05+(i%4)*.01});
  }
  let seed=3481;const rand=()=>((seed=(Math.imul(seed,1664525)+1013904223)>>>0)/4294967296);
  const positions=new Float32Array(PROFILES.MAX.stars*3);
  for(let i=0;i<PROFILES.MAX.stars;i++){
   const a=rand()*Math.PI*2,r=7+rand()*23;
   positions[i*3]=Math.cos(a)*r;positions[i*3+1]=(rand()-.5)*14;positions[i*3+2]=-8-rand()*24;
  }
  const geo=new THREE.BufferGeometry();
  geo.setAttribute("position",new THREE.BufferAttribute(positions,3));
  scene.add(new THREE.Points(geo,new THREE.PointsMaterial({color:0x9fb9c8,size:.035,transparent:true,opacity:.6})));
  scene.userData={sun,energy};
  function configureBloom(){
   composer?.dispose?.();composer=null;
   if(!effective().bloom)return;
   composer=new EffectComposer(renderer);
   composer.addPass(new RenderPass(scene,camera));
   composer.addPass(new UnrealBloomPass(new THREE.Vector2(240,140),.37,.32,.9));
   composer.addPass(new OutputPass());
  }
  function resize(){
   if(dead)return;
   const r=viewport.getBoundingClientRect(),w=Math.max(1,Math.floor(r.width||900)),h=Math.max(1,Math.floor(r.height||520));
   renderer.setPixelRatio(Math.min(win.devicePixelRatio||1,effective().dpr));
   renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();composer?.setSize(w,h);
  }
  let observer=null;
  const render=(now)=>{
   if(dead||doc.hidden||lost||effective().fps===0){frame=0;return}
   frame=win.requestAnimationFrame(render);
   if(now-last<1000/effective().fps)return;
   last=now;const t=(now-first)/1000,power=effective().motion;
   sun.rotation.y=t*.055*power;sun.rotation.z=Math.sin(t*.13)*.06*power;
   energy.uniforms.uTime.value=t*power;
   for(let i=0;i<8;i++){
    const o=orbits[i],a=o.phase+t*o.speed*power,g=groups[i];
    g.position.set(Math.cos(a)*o.radius,Math.sin(a*1.7)*.52,Math.sin(a)*o.radius*.26);
    g.rotation.y=t*.1*power;
    g.userData.halo.rotation.z=t*.14*power;
   }
   const selection=CORE_IDS.indexOf(selected);
   const focus=selection<0?null:groups[selection].position;
   camera.position.x+=(((focus?.x||0)*.3)-camera.position.x)*.028;
   camera.position.y+=((focus?1.4:1.7)-camera.position.y)*.028;
   camera.position.z+=((focus?9.6:12)-camera.position.z)*.025;
   camera.lookAt(0,0,0);
   if(composer)composer.render();else renderer.render(scene,camera);
  };
  const stop=()=>{if(frame)win.cancelAnimationFrame(frame);frame=0};
  const begin=()=>{if(frame||dead||doc.hidden||lost||effective().fps===0)return;last=-Infinity;first=win.performance?.now?.()??0;frame=win.requestAnimationFrame(render)};
  const onVis=()=>doc.hidden?stop():begin();
  const onMotion=()=>updateProfile();
  const updateProfile=()=>{stop();configureBloom();resize();if(effective().fps===0)renderer.render(scene,camera);else begin()};
  const onLost=e=>{e.preventDefault();lost=true;stop();status.textContent="WebGL lost · fallback state"};
  const onRestored=()=>{lost=false;status.textContent="NOX 3D DEMO · context restored";updateProfile()};
  const onClick=e=>{
   const bounds=canvas.getBoundingClientRect();if(!bounds.width||!bounds.height)return;
   const p=new THREE.Vector2((e.clientX-bounds.left)*2/bounds.width-1,-(e.clientY-bounds.top)*2/bounds.height+1);
   const ray=new THREE.Raycaster();ray.setFromCamera(p,camera);
   const hit=ray.intersectObjects(interactive)[0];if(!hit)return;
   const id=hit.object.userData.coreId;selected=id;
   status.textContent="DEMO 3D CORE · "+id;
   // A visual selection is not a privileged action. Host must authorize routing separately.
   onCoreSelected?.(id);
  };
  canvas.addEventListener("pointerup",onClick);
  canvas.addEventListener("webglcontextlost",onLost);
  canvas.addEventListener("webglcontextrestored",onRestored);
  doc.addEventListener?.("visibilitychange",onVis);
  media?.addEventListener?.("change",onMotion);
  if(typeof win.ResizeObserver==="function"){observer=new win.ResizeObserver(resize);observer.observe(viewport);}
  else win.addEventListener?.("resize",resize);
  function teardown(){
   if(dead)return;dead=true;stop();observer?.disconnect?.();
   if(!observer)win.removeEventListener?.("resize",resize);
   doc.removeEventListener?.("visibilitychange",onVis);media?.removeEventListener?.("change",onMotion);
   canvas.removeEventListener("pointerup",onClick);
   canvas.removeEventListener("webglcontextlost",onLost);
   canvas.removeEventListener("webglcontextrestored",onRestored);
   composer?.dispose?.();disposeScene(scene);scene.clear();renderer.dispose();viewport.remove();mounted.delete(root);
  }
  configureBloom();resize();begin();
  const api=Object.freeze({ready:true,coreIds:CORE_IDS,
   async recordClip(options={}){
    if(dead)throw Error("CINEMA_DESTROYED");
    if(training)throw Error("GPU_TRAINING_PRIORITY");
    if(effective().fps===0)throw Error("REDUCED_MOTION_RECORDING_HOLD");
    return await recordCinemaClip(canvas,options);
   },
   async importApprovedGLB(asset,bytes){
    if(dead)throw Error("CINEMA_DESTROYED");
    const object=await parseApprovedGLB(asset,bytes);
    if(dead){disposeScene(object);throw Error("CINEMA_DESTROYED")}
    object.scale.setScalar(.65);object.position.set(0,-2.1,-1);scene.add(object);
    return {status:"IMPORTED_AUTHORIZED_3D",assetId:asset.id};
   },
   selectCore(id){if(dead||!CORE_IDS.includes(id))return false;selected=id;status.textContent="DEMO 3D CORE · "+id;return true},
   setMode(next){if(dead)return false;budget(next);profile=next;updateProfile();return true},
   setTrainingActive(value){if(dead||typeof value!=="boolean")return false;training=value;updateProfile();return true},
   setReducedMotion(value){if(dead)return false;reduce=value===true;updateProfile();return true},
   status(){return Object.freeze({ready:!dead&&!lost,mode:effective().fps===0?"REDUCED":training?"ECO":profile,selectedCore:selected,scope:"SECONDARY_DEMO"})},
   destroy:teardown});
  mounted.set(root,api);return api;
 }catch(err){
   disposeScene(scene);composer?.dispose?.();renderer?.dispose?.();viewport.remove();
   const error=doc.createElement("div");error.className="nox-real3d-fallback";
   error.textContent="WebGL unavailable · "+String(err?.message||"error").slice(0,80);root.append(error);
   const api=Object.freeze({ready:false,reason:"WEBGL_NOT_AVAILABLE",setMode:()=>false,setTrainingActive:()=>false,selectCore:()=>false,status:()=>({ready:false,reason:"WEBGL_NOT_AVAILABLE"}),destroy(){error.remove();mounted.delete(root)}});
   mounted.set(root,api);return api;
 }
}
