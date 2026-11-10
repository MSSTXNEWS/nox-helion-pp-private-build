/* NOX HELION D02 recovery: WebGL reconstruction, NOT a recovered original source file. */
import * as THREE from 'three';
const canvas=document.getElementById('noxEclipseCanvas');
const status=document.getElementById('renderStatus');
const scene=new THREE.Scene();
let renderer,cam,core,corona,stars,frames=0,ready=false,lost=false,errors=[],raf=0;
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
window.noxHomeDiagnostics=()=>({status:lost?'WEBGL_CONTEXT_LOST':errors.length?'ERROR':ready&&frames?'READY':'LOADING',renderCount:frames,threeRevision:THREE.REVISION,sourceStatus:'RECONSTRUCTED_NOT_HISTORICAL_ORIGINAL',errors:errors.slice()});
if(canvas){try{
 renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:true,powerPreference:'high-performance'});
 renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;
 renderer.setClearColor(0x000000,0);renderer.toneMappingExposure=.9;
 cam=new THREE.PerspectiveCamera(33,1,.1,1000);cam.position.z=42;
 const light=new THREE.PointLight(0xe4a86f,100,100);light.position.set(-7,8,18);scene.add(light);
 scene.add(new THREE.AmbientLight(0x5d7181,.17));
 core=new THREE.Mesh(new THREE.SphereGeometry(7.7,96,72),new THREE.MeshPhysicalMaterial({color:0x0a0b0e,metalness:.84,roughness:.28,clearcoat:1,clearcoatRoughness:.17}));scene.add(core);
 const vertex='varying vec3 vN;varying vec3 vP;void main(){vN=normalize(normalMatrix*normal);vP=position;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}';
 const frag='uniform float uT;uniform vec3 uColor;varying vec3 vN;varying vec3 vP;void main(){float edge=pow(1.-abs(vN.z),3.);float a=atan(vP.y,vP.x);float fire=pow(max(0.,sin(a*54.+uT*.2+sin(a*13.-uT*.13)*3.)),15.);float intensity=edge*.9+fire*.27;gl_FragColor=vec4(uColor*(.2+intensity),clamp(edge*.55+fire*.16,0.,.7));}';
 corona=new THREE.Mesh(new THREE.SphereGeometry(8.05,96,64),new THREE.ShaderMaterial({vertexShader:vertex,fragmentShader:frag,uniforms:{uT:{value:0},uColor:{value:new THREE.Color('#e8aa70')}},transparent:true,blending:THREE.AdditiveBlending,depthWrite:false}));scene.add(corona);
 const starsGeo=new THREE.BufferGeometry();let s=20261110;const rnd=()=>((s=(Math.imul(s,1664525)+1013904223)>>>0)/4294967296);const points=[];for(let i=0;i<390;i++)points.push((rnd()-.5)*85,(rnd()-.5)*50,-18-rnd()*25);starsGeo.setAttribute('position',new THREE.Float32BufferAttribute(points,3));stars=new THREE.Points(starsGeo,new THREE.PointsMaterial({color:0xb5bdc8,size:.075,transparent:true,opacity:.66}));scene.add(stars);
 const resize=()=>{const r=canvas.getBoundingClientRect();renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.6));renderer.setSize(Math.max(1,r.width),Math.max(1,r.height),false);cam.aspect=Math.max(1,r.width)/Math.max(1,r.height);cam.position.z=r.width<680?60:r.width<1100?50:42;cam.updateProjectionMatrix()};resize();new ResizeObserver(resize).observe(canvas);
 canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();lost=true;ready=false;cancelAnimationFrame(raf);});canvas.addEventListener('webglcontextrestored',()=>{lost=false;ready=true;frames=0;resize();raf=requestAnimationFrame(frame)});
 const colors={gold:'#e7b273',classic:'#e7b273',copper:'#d99073',glacier:'#b5d8ed',ion:'#9fd9c5',amethyst:'#c9a7e1'};
 let last=0;function frame(ms){if(!ready||lost)return;raf=requestAnimationFrame(frame);if(document.hidden)return;if(reduced.matches&&frames>0)return;if(ms-last<25)return;last=ms;const t=ms/1000;corona.material.uniforms.uT.value=t;corona.material.uniforms.uColor.value.set(colors[document.documentElement.dataset.noxColor]||colors.gold);if(!reduced.matches){core.rotation.y=t*.008;stars.rotation.z=Math.sin(t*.006)*.002;}renderer.render(scene,cam);frames++;}
 ready=true;if(status)status.textContent='WebGL · D02 READY (восстановленный runtime)';raf=requestAnimationFrame(frame);
}catch(err){errors.push(String(err));if(status)status.textContent='WebGL · HOLD';console.error('NOX_D02_RECONSTRUCTION',err)}}
